import math
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from numpy import ma
from scipy.interpolate import griddata
from torch.nn import ReplicationPad2d

from .backward_mapping import BackwardMapping
from ..formats import save_npz, check_array, load_npz
from ..util import check_file, resize_image


class WarpedAngle:

    def __init__(self, data: np.ndarray):
        check_array(data, shape=(data.shape[0], data.shape[0], 2), dtype=np.float32)
        self._data = data

    @property
    def resolution(self):
        return self._data.shape[0]

    @property
    def channels(self):
        return self._data.shape[2]

    def save(self, file: Path, override: bool = False):
        save_npz(file=file, data=self._data, override=override)

    def visualize(self, file: Path, mask: np.ndarray, size: int, override: bool = False):
        check_file(file, suffix=".png", exist=None if override else False)
        check_array(mask, shape=(self.resolution, self.resolution), dtype=np.bool8)

        output_shape = (self.resolution, self.resolution, 3)
        pad_width = tuple((0, a - b) for (a, b) in zip(output_shape, self._data.shape))
        padded_data = np.pad(self._data, pad_width)

        data = ma.masked_array(padded_data, mask=np.stack([mask] * 3, axis=2))

        data[..., 0] -= data[..., 0].min()
        data[..., 0] /= data[..., 0].max()
        data[..., 1] -= data[..., 1].min()
        data[..., 1] /= data[..., 1].max()
        data = (data * 255).astype("uint8")

        image = resize_image(image=data, size=size)
        cv2.imwrite(str(file), image)

    @staticmethod
    def from_file(file: Path) -> "WarpedAngle":
        return WarpedAngle(load_npz(file))

    @staticmethod
    def from_uv_file(uv_file: Path, resolution_bm: int) -> "WarpedAngle":
        bm = BackwardMapping.from_uv_file(uv_file=uv_file, resolution_bm=resolution_bm, extrapolate=False)
        bm_data = np.roll(bm.data.transpose(1, 0, 2), shift=1, axis=-1) # added for back-compatibility. BM changed its format after writing this.

        mesh = torch.from_numpy(bm_data).unsqueeze(0).float()  # Shape: N, H, W, C
        uv = torch.from_numpy(load_npz(uv_file)).unsqueeze(0).float()

        angles = WarpedAngle.calc_angles_torch(bm=mesh)

        if torch.isnan(angles).any():
            angles = angles.numpy().squeeze().transpose(1, 2, 0)
            mask = ~np.isnan(angles).any(axis=2)
            points = np.argwhere(mask)
            values = angles[mask]
            grid_y, grid_x = np.mgrid[0:mask.shape[0], 0:mask.shape[1]]
            angles = griddata(points=points, values=values, xi=(grid_y, grid_x), method='nearest')
            angles = torch.from_numpy(np.expand_dims(angles.transpose((2, 0, 1)), axis=0))

        warped_angle = WarpedAngle.warp_grid_torch(grid=angles, uv=uv)

        out = warped_angle.numpy()[0]

        return WarpedAngle(data=out)

    @staticmethod
    def calc_angles_torch(bm: torch.Tensor) -> torch.Tensor:
        """
        Create the warped angle map from existing backward map.
        :param bm: Backward map for given sample with shape N, H, W, C=2
        :return: Returns the warped angle map with shape N, C=2 H, W
        """
        assert bm.dtype == torch.float
        assert len(bm.shape) == 4
        N, H, W, C = bm.shape
        assert H == W and C == 2

        def rotate(data: torch.Tensor, rotation):
            return ((data + math.pi + rotation) % (2 * math.pi)) - math.pi

        # calculate angles to warped x-axis
        eps_x = bm[:, :-1, :-1, :] - bm[:, 1:, :-1, :]
        eps_x = eps_x[..., 0] + 1j * eps_x[..., 1]
        angles_x = torch.angle(eps_x)
        angles_x = rotate(angles_x, -math.pi)

        # calculate angles to warped y-axis
        eps_y = bm[:, :-1, :-1, :] - bm[:, :-1, 1:, :]
        eps_y = eps_y[..., 0] + 1j * eps_y[..., 1]
        angles_y = torch.angle(eps_y)
        angles_y = rotate(angles_y, math.pi / 2)

        angles = torch.stack([angles_y, angles_x], dim=1)  # N, C=2 H, W
        angles = ReplicationPad2d(1)(angles)[:, :, 1:, 1:]
        return angles

    @staticmethod
    def warp_grid_torch(grid: torch.Tensor, uv: torch.Tensor) -> torch.Tensor:
        """
        Warp a regular grid (like angles) using the UV mapping.
        :param grid: Regular grid of floats (e.g. angles) with shape N, C=2, H, W
        :param uv: UV map for given sample with shape N, H, W, C=3. Note, the y-coord channel (1) needs to be unmodified (top=1, bottom=0)!
        :return: Returns the warped angle map with shape N, H, W, C=2
        """
        assert grid.dtype == torch.float
        assert len(grid.shape) == 4
        N, C, H, W = grid.shape
        assert H == W and C == 2

        assert uv.dtype == torch.float
        assert len(uv.shape) == 4
        N, H, W, C = uv.shape
        assert H == W and C == 3

        uv.requires_grad_(requires_grad=False)  # UV map (forward map) is considered a constant

        # split uv map channels in mask and data
        bg_mask = uv[..., 0] <= 0.5
        uv_grid = uv[..., 1:]  # N=1, H, W, C=2

        uv_grid[..., 0] = 1 - uv_grid[..., 0]  # invert y-values of uv map (forward map)
        uv_grid[bg_mask] = 5  # out of bounds value for background pixels
        uv_grid = uv_grid * 2 - 1  # adapt grid range required by grid_sample

        warped_grid = F.grid_sample(input=grid, grid=uv_grid, align_corners=True)  # N, C=2, H, W
        warped_grid = warped_grid.transpose(1, 2).transpose(2, 3)  # N, H, W, C=2

        return warped_grid  # N, H, W, C=2

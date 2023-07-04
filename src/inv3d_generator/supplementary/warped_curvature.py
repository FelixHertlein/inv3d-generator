from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from numpy import ma
from scipy.interpolate import griddata
from torch.nn import ReflectionPad2d

from ..formats import save_npz, check_array, load_npz
from ..util import check_file, resize_image


class WarpedCurvature:

    def __init__(self, data: np.ndarray):
        check_array(data, shape=(data.shape[0], data.shape[0], 1), dtype=np.float32)

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

        replicated_data = np.concatenate([self._data] * 3, axis=2)

        data = ma.masked_array(replicated_data, mask=np.stack([mask] * 3, axis=2))

        data -= data.min()
        data /= data.max()
        data = (data * 255).astype("uint8")

        image = resize_image(image=data, size=size)
        cv2.imwrite(str(file), image)

    @staticmethod
    def from_file(file: Path) -> "WarpedCurvature":
        return WarpedCurvature(load_npz(file))

    @staticmethod
    def from_source_files(uv_file: Path, wc_file: Path) -> "WarpedCurvature":
        uv = load_npz(uv_file)
        wc = load_npz(wc_file)

        # gather valid UV coords and corresponding 3D values
        mask = uv[:, :, 0] > 0.5
        pixels = np.array(np.nonzero(mask))
        values = wc[pixels[0], pixels[1]]  # lists all valid 3d coords
        points = uv[pixels[0], pixels[1]][:, 1:]
        points[:, 0] = 1 - points[:, 0]

        # create grids with range zero to one to specify sample locations
        grid_y, grid_x = np.mgrid[0:1:complex(0, 128), 0:1:complex(0, 128)]

        # fill in all sample locations not already specified by point-value pairs
        mesh_3D = griddata(points=points, values=values, xi=(grid_y, grid_x), method='linear')

        # if values outside of complex hull from points are requested, fill them with nearest neighbour
        if np.isnan(mesh_3D).any():
            extrapolation = griddata(points=points, values=values, xi=(grid_y, grid_x), method='nearest')
            mesh_3D = np.where(np.isnan(mesh_3D), extrapolation, mesh_3D)

        # pad mesh of 3D coordinates to handle edge cases
        mesh_3D = torch.from_numpy(mesh_3D).permute(2, 0, 1).unsqueeze(0)
        mesh_3D_padded = ReflectionPad2d(1)(mesh_3D)

        # create deltas to neighbouring nodes
        diff_0 = mesh_3D - mesh_3D_padded[:, :, 1:-1, 2:]
        diff_1 = mesh_3D - mesh_3D_padded[:, :, 1:-1, :-2]
        diff_2 = mesh_3D - mesh_3D_padded[:, :, 2:, 1:-1]
        diff_3 = mesh_3D - mesh_3D_padded[:, :, :-2, 1:-1]

        # sum all differences
        sum_diff = (diff_0 + diff_1 + diff_2 + diff_3)

        # calculate curvature for all nodes in mesh
        curvature = torch.linalg.norm(sum_diff, ord=2, dim=1, keepdim=False).unsqueeze(0).float()  # N=1, C=1 H_bm, W_bm

        # warp curvature map according to UV mapping
        uv = torch.from_numpy(uv).unsqueeze(0).float()
        uv_grid = uv[:, :, :, 1:]  # N=1, H, W, C=2
        uv_grid[:, :, :, 0] = 1 - uv_grid[:, :, :, 0]
        uv_mask = uv[:, :, :, 0] <= 0.5
        uv_grid[uv_mask] = 5
        uv_grid = uv_grid * 2 - 1  # adapt grid range

        curvature = curvature.transpose(2, 3)

        out = F.grid_sample(input=curvature, grid=uv_grid, align_corners=True)

        # reduce noise using thresholds
        threshold = np.quantile(out[out > 0].numpy(), 0.99)
        out[out > threshold] = threshold

        threshold = np.quantile(out[out > 0].numpy(), 0.5)
        out[out < threshold] = 0

        out = out.squeeze(0).permute(1, 2, 0).numpy()

        return WarpedCurvature(data=out)

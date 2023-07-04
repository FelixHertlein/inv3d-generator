from pathlib import Path

import cv2
import numpy as np
from scipy.interpolate import griddata

from ..formats import load_npz, save_npz, check_array
from ..util import check_file, resize_image

class BackwardMapping:

    def __init__(self, data: np.ndarray):
        check_array(data, shape=(data.shape[0], data.shape[0], 2), dtype=np.float32)
        # channel 0: y-values
        # channel 1: x-values

        self._data = data

    @property
    def resolution(self):
        return self._data.shape[0]

    @property
    def data(self):
        return self._data

    def save(self, file: Path, override: bool = False):
        save_npz(file=file, data=self._data, override=override)

    def visualize(self, file: Path, size: int, override: bool = False):
        exist = None if override else False
        check_file(file, suffix=".png", exist=exist)

        output_shape = (self.resolution, self.resolution, 3)
        pad_width = tuple((0, a - b) for (a, b) in zip(output_shape, self._data.shape))
        padded_data = np.pad(self._data, pad_width)

        padded_data = (padded_data * 255).astype("uint8")

        image = resize_image(image=padded_data, size=size)
        cv2.imwrite(str(file), image)

    @staticmethod
    def from_file(file: Path):
        return BackwardMapping(data=load_npz(file))

    @staticmethod
    def from_uv_file(*, uv_file: Path, resolution_bm: int, extrapolate: bool = True):
        uv = load_npz(uv_file)

        mask = uv[:, :, 0] > 0.5
        tex_coords = uv[:, :, 1:]
        height, width, _ = uv.shape

        # collect texture coordinates (and flip y coordinate)
        points = tex_coords[mask]
        points[:, 0] = 1 - points[:, 0]  # flip y coordinate (0 should be on top)

        # collect relative positions of texture coordinates (rel_x, rel_y)
        values = np.array(np.nonzero(mask)).transpose((1, 0)).astype(float)
        values[:, 0] = values[:, 0] / height
        values[:, 1] = values[:, 1] / width

        assert points.shape == values.shape  # shape: (num_points, 2)

        # create grids with range zero to one to specify sample locations
        grid_y, grid_x = np.mgrid[0:1:complex(0, resolution_bm), 0:1:complex(0, resolution_bm)]

        # fill in all sample locations not already specified by point-value pairs
        flow_grid = griddata(points=points, values=values, xi=(grid_y, grid_x), method='linear')

        # if values outside of complex hull from points are requested, fill them with nearest neighbour
        if np.isnan(flow_grid).any() and extrapolate:
            extrapolation = griddata(points=points, values=values, xi=(grid_y, grid_x), method='nearest')
            flow_grid = np.where(np.isnan(flow_grid), extrapolation, flow_grid)

        return BackwardMapping(data=flow_grid.astype("float32"))

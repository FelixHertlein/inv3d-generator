from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

from ..formats import check_array, load_npz, load_image, save_npz
from ..util import check_file, resize_image


class WarpedTextMask:

    def __init__(self, data: np.ndarray):
        check_array(data, shape=(data.shape[0], data.shape[0], 1), dtype=np.bool8)

        self._data = data

    @property
    def resolution(self):
        return self._data.shape[0]

    @property
    def channels(self):
        return self._data.shape[2]

    def save(self, file: Path, override: bool = False):
        save_npz(file=file, data=self._data, override=override)

    def visualize(self, file: Path, size: int, override: bool = False):
        check_file(file, suffix=".png", exist=None if override else False)

        data = np.concatenate([self._data] * 3, axis=2)
        data = (data * 255).astype("uint8")

        image = resize_image(image=data, size=size)
        cv2.imwrite(str(file), image)

    @staticmethod
    def from_file(file: Path) -> "WarpedTextMask":
        return WarpedTextMask(load_npz(file))

    @staticmethod
    def from_source_files(uv_file: Path, text_only_file: Path) -> "WarpedTextMask":
        uv = load_npz(uv_file)
        text_only = load_image(text_only_file)

        source = torch.from_numpy(text_only).unsqueeze(0).transpose(3, 2).transpose(2, 1).transpose(2, 3)  # N=1,C=3,W,H
        source = 255 - source  # invert
        source = source.float()

        grid = torch.from_numpy(uv[:, :, 1:])  # H, W, C=2
        grid[:, :, 0] = 1 - grid[:, :, 0]  # invert y coordinates
        grid = grid * 2 - 1
        grid[uv[:, :, 0] <= 0] = 5  # out of range value
        grid = grid.unsqueeze(0)  # N=1, H, W, C=2

        res = F.grid_sample(input=source, grid=grid, align_corners=True)

        res = res.transpose(2, 1).transpose(3, 2).squeeze(0).numpy().astype("uint8")

        # apply filter to thicken lines
        kernel = np.ones((3, 3), np.float32) / 25
        res = cv2.filter2D(res, -1, kernel)

        res = np.logical_not(np.all(res == 0, axis=-1))  # binarize
        res = np.expand_dims(res, axis=2)

        return WarpedTextMask(data=res)

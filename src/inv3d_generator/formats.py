import json
from pathlib import Path
from typing import Optional, Tuple, Union, Dict

import cv2
import numpy as np

from .util import check_file


def load_image(file: Path):
    check_file(file, suffix=".png")
    return cv2.imread(str(file), cv2.IMREAD_COLOR)


def save_image(file: Path, data: np.ndarray, override: bool = False):
    exist = None if override else False
    check_file(file, suffix=".png", exist=exist)
    assert data.dtype == np.uint8
    assert len(data.shape) == 3
    assert data.shape[2] == 3

    cv2.imwrite(str(file), data)


def load_npz(file: Path) -> np.ndarray:
    check_file(file, suffix=".npz")
    with np.load(file) as archive:
        keys = list(archive.keys())
        assert len(keys) == 1
        return archive[keys[0]]


def save_npz(file: Path, data: np.ndarray, override: bool = False):
    exist = None if override else False
    check_file(file, suffix=".npz", exist=exist)

    params = {
        file.stem: data
    }
    np.savez_compressed(str(file), **params)


def convert_exr_to_npz(exr_file: Path, npz_file: Path, override: bool = False):
    check_file(exr_file, suffix=".exr")
    check_file(npz_file, suffix=".npz", exist=None if override else False)

    data = cv2.imread(str(exr_file.resolve()), cv2.IMREAD_UNCHANGED)
    data = data.astype("float32")

    params = {
        npz_file.stem: data
    }
    np.savez_compressed(str(npz_file), **params)


def check_array(data: np.ndarray, shape: Optional[Tuple] = None, dtype: Optional[np.dtype] = None):
    assert isinstance(data, np.ndarray), f"Object is not a numpy array! Found type is {data.dtype}"

    if shape is not None:
        assert data.shape == shape, f"Array shapes do not match! Expected shape is {shape}. Found shape is {data.shape}."

    if dtype is not None:
        assert data.dtype == dtype, f"Array dtypes do not match! Expected dtype is {dtype}. Found dtype is {data.dtype}."

    return data


def load_json(file: Union[str, Path]):
    file = check_file(file, suffix=".json", exist=True)
    with file.open("r") as fp:
        return json.load(fp)


def save_json(file: Path, data: Dict, exist=False):
    file = check_file(file, suffix=".json", exist=exist)
    with file.open("w") as f:
        json.dump(obj=data, fp=f, indent=4)

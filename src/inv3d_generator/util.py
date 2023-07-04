import os
import sys
from pathlib import Path
from typing import List, Union, Dict, Optional

import cv2
import numpy as np
from sklearn.model_selection import train_test_split


class Tee(object):
    def __init__(self, name, mode):
        self.file = open(name, mode)
        self.stdout = sys.stdout
        sys.stdout = self

    def __del__(self):
        sys.stdout = self.stdout
        self.file.close()

    def write(self, data):
        self.file.write(data)
        self.stdout.write(data)

    def flush(self):
        self.file.flush()


def check_dir(directory: Union[str, Path], exist: bool = True):
    directory = Path(directory)

    if exist:
        assert directory.is_dir(), f"Directory {directory.resolve()} does not exist!"
    else:
        assert directory.parent.is_dir(), f"Parent directory {directory.parent.resolve()} does not exist!"
        assert not directory.is_dir(), f"Directory {directory.resolve()} does exist!"

    return directory


def check_file(file: Union[str, Path], suffix: Union[None, str, List[str]] = None, exist: Optional[bool] = True):
    file = Path(file)

    if exist is None:
        pass  # No check
    elif exist:
        assert file.is_file(), f"File {file.resolve()} does not exist!"
    else:
        assert file.parent.is_dir(), f"Parent directory {file.parent.resolve()} does not exist!"
        assert not file.is_file(), f"File {file.resolve()} does exist!"

    if suffix is None:
        pass
    elif isinstance(suffix, str):
        assert file.suffix == suffix, f"File {file.resolve()} has an invalid suffix! Allowed is '{suffix}'"
    else:
        assert file.suffix in suffix, f"File {file.resolve()} has an invalid suffix! Allowed is any of '{suffix}'"

    return file


def list_files(search_dir: Path, suffixes: List[str] = None, recursive: bool = False, as_string: bool = False):
    assert search_dir.is_dir()

    if suffixes is None:
        suffixes = ['']

    glob_function = search_dir.rglob if recursive else search_dir.glob

    return [str(file) if as_string else file
            for suffix in suffixes
            for file in glob_function("*" + suffix)
            if file.is_file()]


def remove_common_path(path: Path, reference: Path) -> Path:
    path = path.expanduser().absolute()
    reference = reference.expanduser().absolute()
    common_path = os.path.commonpath([str(path), str(reference)])
    return path.relative_to(Path(common_path))


def list_dirs(search_dir: Path, recursive: bool = False, as_string: bool = False, glob_string="*"):
    glob_function = search_dir.rglob if recursive else search_dir.glob

    return [str(file) if as_string else file
            for file in glob_function(glob_string)
            if file.is_dir()]


def split_items(items: List, ratios: Dict[str, float]):
    assert sum(ratios.values()) == 1
    assert {"train", "val", "test"} == set(ratios.keys())

    all_indexes = np.arange(len(items))
    train_indexes, val_and_test_indexes = train_test_split(all_indexes, train_size=ratios["train"])
    val_indexes, test_indexes = train_test_split(val_and_test_indexes,
                                                 train_size=ratios["val"] / (ratios["val"] + ratios["test"]))

    return {
        "train": [items[idx] for idx in train_indexes],
        "val": [items[idx] for idx in val_indexes],
        "test": [items[idx] for idx in test_indexes]
    }


def resize_image(image: np.ndarray, size: int) -> np.ndarray:
    h, w, c = image.shape
    ratio = size / max(h, w)
    width = int(w * ratio)
    height = int(h * ratio)
    return cv2.resize(image, dsize=(width, height))


def print_if(verbose: bool, message: str):
    if verbose:
        print(f"PID {os.getpid()}: {message}")

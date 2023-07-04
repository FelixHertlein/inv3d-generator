import random
from pathlib import Path
from typing import *

from .blender_renderer import BlenderRenderer
from ..util import check_dir, check_file


def render_3d(output_dir: Path, tex_file: Path, assets_dir: Path, rel_env_files: Optional[List[str]],
              rel_obj_file: List[str], resolution: int, summary: Dict, verbose: bool = False):
    check_dir(output_dir)
    check_file(tex_file, suffix=".png")
    check_dir(assets_dir)

    success = False
    while not success:
        env_file = None if rel_env_files is None else assets_dir / random.choice(rel_env_files)
        blender_renderer = BlenderRenderer(output_dir=output_dir,
                                           tex_file=tex_file,
                                           env_file=env_file,
                                           obj_file=assets_dir / random.choice(rel_obj_file),
                                           chess_file=assets_dir / "chess48.png",
                                           resolution=resolution,
                                           summary=summary,
                                           verbose=verbose)
        success = blender_renderer.render()

        if not success:
            print("WARNING: Failed to render 3D warping. Retrying!")

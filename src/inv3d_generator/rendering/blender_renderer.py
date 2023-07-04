import json
import random
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Dict

from .blender_server import BlenderServer
from ..formats import convert_exr_to_npz
from ..util import check_dir, check_file, print_if


class BlenderRenderer:
    BLENDER_DIR = check_dir(Path(__file__).parent / "blender")
    BLENDER_MESH_FILE = check_file(BLENDER_DIR / "doc3D_render_mesh.py")
    BLENDER_RECON_FILE = check_file(BLENDER_DIR / "doc3D_render_recon.py")
    BLENDER_ALB_FILE = check_file(BLENDER_DIR / "doc3D_render_alb.py")
    BLENDER_DMAP_FILE = check_file(BLENDER_DIR / "doc3D_render_dmap.py")
    BLENDER_NORM_FILE = check_file(BLENDER_DIR / "doc3D_render_norm.py")

    def __init__(self, output_dir: Path, tex_file: Path, env_file: Optional[Path], obj_file: Path, chess_file: Path,
                 resolution: int, summary: Dict, verbose: bool = False):
        check_dir(output_dir)
        check_file(tex_file, suffix=".png")
        check_file(obj_file, suffix=".obj")
        check_file(chess_file, suffix=".png")
        if env_file is not None:
            check_file(env_file, suffix=[".hdr", ".exr"])

        self.output_dir = output_dir
        self.tex_file = tex_file
        self.env_file = env_file
        self.obj_file = obj_file
        self.chess_file = chess_file
        self.resolution = resolution
        self.summary = summary
        self.verbose = verbose

    def render(self) -> bool:
        print_if(self.verbose, "Start blender rendering")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dir = Path(tmp_dir)

            self._render_mesh(tmp_dir=tmp_dir)

            img_file = self._search_file(tmp_dir / "img", suffix=".png")
            uv_file = self._search_file(tmp_dir / "uv", suffix=".exr")
            bld_file = self._search_file(tmp_dir / "bld", suffix=".blend")
            wc_file = self._search_file(tmp_dir / "wc", suffix=".exr")

            if any(file is None for file in (img_file, uv_file, bld_file, wc_file)):
                print_if(self.verbose, "Abort blender rendering")
                return False

            recon_file = self._render_recon(tmp_dir=tmp_dir, blender_file=bld_file)
            alb_file = self._render_alb(tmp_dir=tmp_dir, blender_file=bld_file)
            dmap_file = self._render_dmap(tmp_dir=tmp_dir, blender_file=bld_file)
            norm_file = self._render_norm(tmp_dir=tmp_dir, blender_file=bld_file)

            if any(file is None for file in (recon_file, alb_file, dmap_file, norm_file)):
                print_if(self.verbose, "Abort blender rendering")
                return False

            # finalize
            shutil.copyfile(str(img_file), str(self.output_dir / "warped_document.png"))
            shutil.copyfile(str(recon_file), str(self.output_dir / "warped_recon.png"))
            shutil.copyfile(str(alb_file), str(self.output_dir / "warped_albedo.png"))
            convert_exr_to_npz(uv_file, self.output_dir / "warped_UV.npz")
            convert_exr_to_npz(wc_file, self.output_dir / "warped_WC.npz")
            convert_exr_to_npz(dmap_file, self.output_dir / "warped_depth.npz")
            convert_exr_to_npz(norm_file, self.output_dir / "warped_normal.npz")

            print_if(self.verbose, "Stop blender rendering with success!")
            return True

    def _render_mesh(self, tmp_dir: Path):

        config_file = tmp_dir / "blender_mesh_config.json"
        with config_file.open("w") as fp:
            self.summary["environment"] = self.env_file
            self.summary["mesh"] = self.obj_file
            self.summary["resolution"] = self.resolution

            json.dump(fp=fp, indent=4, obj={
                "output_base_dir": str(tmp_dir),
                "obj_file": str(self.obj_file.resolve()),
                "tex_file": str(self.tex_file.resolve()),
                "env_file": None if self.env_file is None else str(self.env_file.resolve()),
                "resolution": self.resolution,
                "seed": random.getrandbits(32)
            })

        BlenderServer.execute_script(code_file=self.BLENDER_MESH_FILE, config_file=config_file)

    def _render_recon(self, tmp_dir: Path, blender_file: Path) -> Optional[Path]:
        return self._render_and_collect(tmp_dir=tmp_dir, blender_file=blender_file, name="recon", config={
            "tex_file": str(self.chess_file.resolve()),
        })

    def _render_alb(self, tmp_dir: Path, blender_file: Path) -> Optional[Path]:
        return self._render_and_collect(tmp_dir=tmp_dir, blender_file=blender_file, name="alb", config={
            "tex_file": str(self.tex_file.resolve()),
            "resolution": self.resolution,
        })

    def _render_dmap(self, tmp_dir: Path, blender_file: Path) -> Optional[Path]:
        return self._render_and_collect(tmp_dir=tmp_dir, blender_file=blender_file, name="dmap", config={})

    def _render_norm(self, tmp_dir: Path, blender_file: Path) -> Optional[Path]:
        return self._render_and_collect(tmp_dir=tmp_dir, blender_file=blender_file, name="norm", config={})

    def _render_and_collect(self, tmp_dir: Path, blender_file: Path, name: str, config: Dict) -> Optional[Path]:
        output_dir = tmp_dir / name
        output_dir.mkdir()

        config["blender_file"] = str(blender_file.resolve())
        config["output_dir"] = str(output_dir.resolve())
        config["seed"] = random.getrandbits(32)

        config_file = tmp_dir / f"blender_{name}_config.json"
        with config_file.open("w") as fp:
            json.dump(fp=fp, indent=4, obj=config)

        code_file = check_file(self.BLENDER_DIR / f"doc3D_render_{name}.py")
        BlenderServer.execute_script(code_file=code_file, config_file=config_file)

        return self._search_file(output_dir, suffix="")

    @staticmethod
    def _search_file(directory: Path, suffix: str) -> Optional[Path]:
        if not directory.is_dir():
            return None

        files = list(directory.glob(f"*{suffix}"))
        if len(files) == 0:
            return None

        assert len(files) == 1
        return files[0]

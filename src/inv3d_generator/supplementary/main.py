from pathlib import Path

from .backward_mapping import BackwardMapping
from .warped_angle import WarpedAngle
from .warped_curvature import WarpedCurvature
from .warped_text_mask import WarpedTextMask
from ..util import check_dir, check_file, print_if


def create_supplementary(output_dir: Path, resolution_bm: int, verbose: bool = False):
    check_dir(output_dir)

    print_if(verbose, "Start supplementary generation")

    uv_file = check_file(output_dir / "warped_UV.npz")
    wc_file = check_file(output_dir / "warped_WC.npz")
    flat_text_mask_file = check_file(output_dir / "flat_text_mask.png")

    bm = BackwardMapping.from_uv_file(uv_file=uv_file, resolution_bm=resolution_bm)
    bm.save(output_dir / "warped_BM.npz")

    curvature = WarpedCurvature.from_source_files(uv_file=uv_file, wc_file=wc_file)
    curvature.save(output_dir / "warped_curvature.npz")

    angle = WarpedAngle.from_uv_file(uv_file=uv_file, resolution_bm=resolution_bm)
    angle.save(output_dir / "warped_angle.npz")

    text_mask = WarpedTextMask.from_source_files(uv_file=uv_file, text_only_file=flat_text_mask_file)
    text_mask.save(output_dir / "warped_text_mask.npz")

    print_if(verbose, "Stop supplementary generation")

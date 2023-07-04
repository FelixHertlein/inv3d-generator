import argparse
import concurrent.futures
import random
import re
import shutil
import traceback
from collections import defaultdict
from itertools import chain
from pathlib import Path
from typing import *

import numpy as np
import tqdm

from .formats import load_json, save_json
from .invoice.main import create_invoice
from .rendering.blender_server import BlenderServer
from .rendering.main import render_3d
from .supplementary.main import create_supplementary
from .util import check_dir, list_files, split_items, check_file, remove_common_path, list_dirs, Tee


class Inv3DGenerator:
    RATIOS = {"train": 0.7, "val": 0.15, "test": 0.15}

    def __init__(self, output_dir: Path, resume: bool = False, args: Optional[argparse.Namespace] = None):

        self.output_dir = output_dir
        self.data_dir = output_dir / "data"
        self.settings_file = output_dir / "settings.json"

        if resume:
            check_dir(output_dir, exist=True)
            check_dir(self.data_dir, exist=True)
            check_file(self.settings_file, exist=True)

        else:
            assert args is not None
            check_dir(self.output_dir, exist=False)
            self.output_dir.mkdir()
            self.data_dir.mkdir()
            if "settings_file" in args.__dict__.keys():
                self._create_tasks_from_settings_file(args=args)
            else:
                self._create_tasks(args=args)

        Tee(str(output_dir / "log.txt"), "a")

    def _create_tasks(self, args: argparse.Namespace):
        random.seed(args.seed)
        np.random.seed(random.getrandbits(32))

        assets_dir = Path(__file__).parent.parent.parent / "assets" if args.assets_dir == "" else Path(args.assets_dir)
        check_dir(assets_dir)

        asset_dirs = {asset_dir.name: asset_dir.resolve()
                      for asset_dir in assets_dir.glob("*")
                      if asset_dir.is_dir()}

        template_files = list_files(asset_dirs["templates"], suffixes=[".htm"], recursive=True)
        logo_files = list_files(asset_dirs["logos"], suffixes=[".png"], recursive=True)
        env_files = list_files(asset_dirs["environments"], suffixes=[".hdr", ".exr"], recursive=True)

        assert len(template_files) > 0, "Template files not found!"
        assert len(logo_files) > 0, "Logos not found!"
        assert len(env_files) > 0, "Environment files (.hdr or .exr) not found!"

        print("INFO: Number of available templates: {}".format(len(template_files)))
        print("INFO: Number of available logos: {}".format(len(logo_files)))
        print("INFO: Number of available environments: {}".format(len(env_files)))

        template_files = split_items(items=template_files, ratios=self.RATIOS)
        logo_files = split_items(items=logo_files, ratios=self.RATIOS)
        env_files = split_items(items=env_files, ratios=self.RATIOS)
        obj_files = self._gather_meshes(asset_dirs["meshes"])
        font_files = self._gather_fonts(asset_dirs["fonts"])

        settings = {
            split: {
                "template_files": list(map(str, template_files[split])),
                "env_files": list(map(str, env_files[split])),
                "obj_files": list(map(str, obj_files[split])),
                "logo_files": list(map(str, logo_files[split])),
                "font_files": list(map(str, font_files[split])),
            }
            for split in self.RATIOS
        }
        settings["base"] = {
            "seed": args.seed,
            "document_dpi": args.document_dpi,
            "resolution_rendering": args.resolution_rendering,
            "resolution_bm": args.resolution_bm,
            "assets_dir": str(assets_dir.resolve()),
        }

        self._create_task_files(settings=settings, num_samples=args.num_samples)

    def _create_tasks_from_settings_file(self, args: argparse.Namespace):
        settings_file = check_file(args.settings_file, suffix=".json", exist=True)
        settings = load_json(settings_file)

        random.seed(settings["base"]["seed"])
        np.random.seed(random.getrandbits(32))

        suffixes = {
            "env_files": [".hdr", ".exr"],
            "font_files": ".ttf",
            "logo_files": ".png",
            "obj_files": ".obj",
            "template_files": ".htm"
        }

        # validate settings
        check_dir(settings["base"]["assets_dir"], exist=True)
        assert isinstance(settings["base"]["document_dpi"], int)
        assert isinstance(settings["base"]["resolution_bm"], int)
        assert isinstance(settings["base"]["resolution_rendering"], int)
        assert isinstance(settings["base"]["seed"], int)

        for split in ["train", "test", "val"]:
            for resource_type, suffix in suffixes.items():
                for entry in settings[split][resource_type]:
                    check_file(entry, suffix=suffix, exist=True)

        self._create_task_files(settings=settings, num_samples=args.num_samples)

    def _create_task_files(self, settings: Dict, num_samples: int):
        save_json(self.settings_file, settings)

        all_tasks = split_items(items=list(range(num_samples)), ratios=self.RATIOS)
        fill_digits = len(str(num_samples))

        with tqdm.tqdm(total=num_samples, desc="Creating tasks", smoothing=0) as progress_bar:
            for split, tasks in all_tasks.items():
                split_dir = self.data_dir / split
                split_dir.mkdir()

                for idx in tasks:
                    task_name = str(idx).zfill(fill_digits)
                    task_file = split_dir / f"task_{task_name}.json"
                    task_settings = {
                        **settings[split],
                        **settings["base"],
                        "seed": random.getrandbits(32),
                        "name": task_name
                    }

                    # randomly switch to no background to ease learning process
                    if split in ["train", "val"] and random.random() <= 0.3:
                        task_settings["env_files"] = None

                    save_json(task_file, task_settings)

                    progress_bar.update(1)

    @classmethod
    def _gather_fonts(cls, fonts_base_dir: Path, max_styles: int = 5) -> Dict[str, List[Path]]:
        all_fonts = {
            font_dir.name: list_files(font_dir, suffixes=[".ttf"])
            for font_dir in list_dirs(fonts_base_dir)
        }

        # check if font files were found
        for font_name, font_files in all_fonts.items():
            assert len(font_files) > 0, f"No font files found for font {font_name}"

        # limit styles per font
        all_fonts = {
            font_name: random.sample(font_files, min(max_styles, len(font_files)))
            for font_name, font_files in all_fonts.items()
        }

        # collect font styles
        font_split = {
            split: [font_file
                    for font_name in font_names
                    for font_file in all_fonts[font_name]]
            for split, font_names, in split_items(items=list(all_fonts.keys()), ratios=cls.RATIOS).items()
        }

        print(f"INFO: Number of available fonts: {len(all_fonts)}")
        print(f"INFO: Number of available font styles: {sum(map(len, font_split.values()))}")
        assert len(all_fonts) > 0, "Font files (.ttf) not found!"

        return font_split

    @classmethod
    def _gather_meshes(cls, mesh_base_dir: Path) -> Dict[str, List[Path]]:
        pattern = r"^((?P<crop_id>\d+)_)?((?P<mesh_id>\d+)_(?P<augmentation_id>\d+).obj)$"

        all_meshes = defaultdict(list)
        for mesh_file in list_files(mesh_base_dir, suffixes=[".obj"], recursive=True):
            res = re.match(pattern, mesh_file.name)
            assert res is not None, f"Mesh file {mesh_file} has an unknown format!"

            mesh_id = int(res.groupdict()["mesh_id"])
            all_meshes[mesh_id].append(mesh_file)

        if len(all_meshes) < 10:
            print(f"WARNING: Found only {len(all_meshes)} different mesh types! Splits will be made on file level!")
            mesh_split = split_items(items=list(chain.from_iterable(all_meshes.values())), ratios=cls.RATIOS)
        else:
            mesh_split = {
                split: [mesh_file
                        for mesh_id in mesh_ids
                        for mesh_file in all_meshes[mesh_id]]
                for split, mesh_ids, in split_items(items=list(all_meshes.keys()), ratios=cls.RATIOS).items()
            }

        print(f"INFO: Number of available mesh types: {len(all_meshes)}")
        print(f"INFO: Number of available meshes: {sum(map(len, mesh_split.values()))}")
        assert len(all_meshes) > 0, "Mesh files (.obj) not found!"

        return mesh_split

    def process_tasks(self, num_workers: int = 0, verbose: bool = False):
        task_files = list(self.data_dir.rglob("task_*.json"))
        print(f"Found {len(task_files)} tasks to process!")

        random.shuffle(task_files)

        blender_server = BlenderServer()

        if num_workers > 0:
            self._process_tasks_parallel(task_files=task_files, num_workers=num_workers, verbose=verbose)
        else:
            self._process_tasks_sequentially(task_files=task_files, verbose=verbose)

        blender_server.stop()

    def _process_tasks_parallel(self, task_files: List[Path], num_workers: int, verbose: bool = False):
        print("Starting parallel execution with {} workers!".format(num_workers))

        with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(self.process_task, task_file, verbose) for task_file in task_files]

            print("Awaiting completion!".format(num_workers))

            try:
                with tqdm.tqdm(desc="Creating dataset", total=len(futures), smoothing=0) as progress_bar:
                    for f in concurrent.futures.as_completed(futures):
                        try:
                            f.result()
                        except Exception:
                            print("EXCEPTION: ", traceback.format_exc())
                        progress_bar.update(1)
            except KeyboardInterrupt:
                executor.shutdown(wait=False)
                exit(-1)

    def _process_tasks_sequentially(self, task_files: List[Path], verbose: bool = False):
        print("Starting sequential dataset generation!")
        for task_file in tqdm.tqdm(task_files, desc="Creating dataset", smoothing=0):
            self.process_task(task_file, verbose=verbose)

    @staticmethod
    def process_task(task_file: Path, verbose: bool = False):
        check_file(task_file, suffix=".json")

        settings = load_json(task_file)

        sample_dir = task_file.parent / str(settings["name"])
        assets_dir = Path(settings["assets_dir"])

        # recover from incomplete states
        if sample_dir.is_dir():
            shutil.rmtree(sample_dir)

        sample_dir.mkdir()

        random.seed(settings["seed"])
        np.random.seed(random.getrandbits(32))

        # gather all settings used to create the sample
        summary = {
            "invoice": {},
            "warping": {}
        }

        # create invoice
        create_invoice(output_dir=sample_dir,
                       assets_dir=assets_dir,
                       template_file=assets_dir / random.choice(settings["template_files"]),
                       logo_file=assets_dir / random.choice(settings["logo_files"]),
                       font_file=assets_dir / random.choice(settings["font_files"]),
                       dpi=settings["document_dpi"],
                       summary=summary["invoice"],
                       verbose=verbose)

        # render warped version of given invoice
        render_3d(output_dir=sample_dir,
                  tex_file=sample_dir / "flat_document.png",
                  assets_dir=assets_dir,
                  rel_env_files=settings["env_files"],
                  rel_obj_file=settings["obj_files"],
                  resolution=settings["resolution_rendering"],
                  summary=summary["warping"],
                  verbose=verbose)

        # create supplementary files using warped images
        create_supplementary(output_dir=sample_dir,
                             resolution_bm=settings["resolution_bm"],
                             verbose=verbose)

        # export sample summary
        Inv3DGenerator._export_summary(data=summary, base_dir=assets_dir, output_file=sample_dir / "details.json")

        # delete task file after successful execution
        task_file.unlink()

    @staticmethod
    def _export_summary(data: Dict, base_dir: Path, output_file: Optional[Path]) -> Dict:

        def map_value(value: Any) -> Any:
            if isinstance(value, dict):
                return Inv3DGenerator._export_summary(value, base_dir, None)
            elif isinstance(value, Path):
                return str(remove_common_path(value, base_dir))
            else:
                return value

        data = {key: map_value(value) for key, value in data.items()}

        if output_file is not None:
            save_json(output_file, data)

        return data

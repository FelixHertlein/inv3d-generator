import argparse
import shutil
from pathlib import Path

from inv3d_generator.generator import Inv3DGenerator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output_dir', nargs='?', type=str, default='./out/inv3d',
                        help='Path to store generated dataset')
    parser.add_argument('--num_workers', nargs='?', type=int, default=0,
                        help='Number of processes working in parallel to generate dataset')
    parser.add_argument('--num_samples', nargs='?', type=int, default=100,
                        help='Path to store generated dataset')
    parser.add_argument('--verbose', nargs='?', type=bool, default=False,
                        help='Display detailed information. Only applicable for sequential task generation')
    parser.add_argument('--override', nargs='?', type=bool, default=False,
                        help='CAUTION: clears existing output_path!')
    subparsers = parser.add_subparsers()

    parser_default = subparsers.add_parser('default', help='Createst tasks using parameters and starts generation')
    parser_default.add_argument('--assets_dir', nargs='?', type=str, default='',
                                help='Directory with assets (overwrites folders from project asset directory.)')
    parser_default.add_argument('--seed', nargs='?', type=int, default=42,
                                help='Seed for random generators')
    parser_default.add_argument('--document_dpi', nargs='?', type=int, default=200,
                                help='Y-resolution for warped image rendering')
    parser_default.add_argument('--resolution_rendering', nargs='?', type=int, default=1600,
                                help='X and Y-resolution for warped image rendering')
    parser_default.add_argument('--resolution_bm', nargs='?', type=int, default=512,
                                help='X and Y-resolution for backward mapping')

    parser_custom = subparsers.add_parser('custom', help='Creates tasks from a settings file and starts generation')
    parser_custom.add_argument('--settings_file', nargs='?', type=str, help='Path to the input settings file.')

    args = parser.parse_args()
    output_dir = Path(args.output_dir)

    for key, value in args.__dict__.items():
        print(f"SETTING {key}: {value}")

    if args.override:
        if output_dir.is_dir():
            shutil.rmtree(str(output_dir))

    gen = Inv3DGenerator(output_dir, resume=False, args=args)
    gen.process_tasks(num_workers=args.num_workers, verbose=args.verbose)


if __name__ == "__main__":
    main()

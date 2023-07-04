import argparse
from pathlib import Path

from inv3d_generator.generator import Inv3DGenerator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output_dir', nargs='?', type=str, default='./out/inv3d',
                        help='Path to store generated dataset')
    parser.add_argument('--num_workers', nargs='?', type=int, default=0,
                        help='Number of processes working in parallel to generate dataset')
    parser.add_argument('--verbose', nargs='?', type=bool, default=False,
                        help='Display detailed information. Only applicable for sequential task generation')
    args = parser.parse_args()
    output_dir = Path(args.output_dir)

    for key, value in args.__dict__.items():
        print(f"SETTING {key}: {value}")

    gen = Inv3DGenerator(output_dir, resume=True)
    gen.process_tasks(num_workers=args.num_workers, verbose=args.verbose)


if __name__ == "__main__":
    main()

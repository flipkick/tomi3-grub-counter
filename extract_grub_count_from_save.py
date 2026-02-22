import sys
import os
import glob
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("tomi3-grub-counter")
except PackageNotFoundError:
    try:
        from _version import __version__
    except ImportError:
        __version__ = "?"

from tomi3_save import SAVEDIR, read_grub_count


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Read the nGrubsCollected count from Tales of Monkey Island 3 save files.",
        epilog=f"Default save directory: {SAVEDIR}",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s v{__version__}")
    parser.add_argument("file", nargs="?", help="read a specific .save file instead of scanning a directory")
    parser.add_argument("--dir", dest="savedir", metavar="DIR", help="directory to scan for .save files (overrides default)")
    args = parser.parse_args()

    if args.file:
        count, err = read_grub_count(args.file)
        if err:
            print(f"Error: {err}")
            sys.exit(1)
        else:
            print(f"Grub Count: {count}")
        return

    savedir = args.savedir or SAVEDIR
    pattern = os.path.join(savedir, "*.save")
    saves = sorted(glob.glob(pattern), reverse=True)

    if not saves:
        print(f"No .save files found in:\n  {savedir}")
        if not args.savedir:
            print("Tip: use --dir <folder> to specify a different save directory")
        sys.exit(1)

    col_name  = 30
    col_count = 40
    print(f"{'File':<{col_name}} {'Grub Count':>{col_count}}")
    print("-" * (col_name + col_count + 1))

    for path in saves:
        name = os.path.basename(path)
        count, err = read_grub_count(path)
        if err:
            print(f"{name:<{col_name}} {err:>{col_count}}")
        else:
            print(f"{name:<{col_name}} {count:>{col_count}}")


if __name__ == "__main__":
    main()

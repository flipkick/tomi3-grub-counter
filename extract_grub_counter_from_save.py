import struct
import sys
import os
import glob

# TellTale .save file magic (raw, first 4 bytes)
FILE_MAGIC = bytes.fromhex('AADEAF64')

# Signature (decoded, after XOR 0xFF):
# The 16 bytes that always appear directly before the grub counter
SIGNATURE = bytes.fromhex('02000000a15a219753c00e510000000000000000'[:32])

SAVEDIR = os.path.join(os.path.expanduser("~"), "Documents", "Telltale Games", "Tales of Monkey Island 3")


def read_grub_counter(filepath):
    if not os.path.isfile(filepath):
        return None, f"file not found: {filepath}"

    try:
        with open(filepath, 'rb') as f:
            raw = f.read()
    except OSError as e:
        return None, f"read error: {e}"

    if raw[:4] != FILE_MAGIC:
        return None, "not a valid save file (invalid magic)"

    dec = bytes(b ^ 0xFF for b in raw)

    idx = dec.find(SIGNATURE)
    if idx == -1:
        return None, "no grub counter (wrong game chapter?)"

    counter_offset = idx + len(SIGNATURE)
    if counter_offset + 4 > len(dec):
        return None, "file corrupted (too short)"

    counter = struct.unpack_from('<I', dec, counter_offset)[0]
    return counter, None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Extract grub counter from TellTale save files")
    parser.add_argument("file", nargs="?", help="Path to a specific .save file")
    parser.add_argument("--dir", dest="savedir", metavar="DIR", help="Directory to search for .save files")
    args = parser.parse_args()

    if args.file:
        counter, err = read_grub_counter(args.file)
        if err:
            print(f"Error: {err}")
            sys.exit(1)
        else:
            print(f"Grub Counter: {counter}")
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
    print(f"{'File':<{col_name}} {'Grub Counter':>{col_count}}")
    print("-" * (col_name + col_count + 1))

    for path in saves:
        name = os.path.basename(path)
        counter, err = read_grub_counter(path)
        if err:
            print(f"{name:<{col_name}} {(err):>{col_count}}")
        else:
            print(f"{name:<{col_name}} {counter:>{col_count}}")


if __name__ == "__main__":
    main() 
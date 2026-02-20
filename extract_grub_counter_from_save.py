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
    if len(sys.argv) > 1:
        path = sys.argv[1]
        counter, err = read_grub_counter(path)
        if err:
            print(f"Error: {err}")
            sys.exit(1)
        else:
            print(f"Grub Counter: {counter}")
        return

    pattern = os.path.join(SAVEDIR, "*.save")
    saves = sorted(glob.glob(pattern))

    if not saves:
        print(f"No .save files found in:\n  {SAVEDIR}")
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
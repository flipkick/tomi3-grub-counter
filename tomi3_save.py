"""
Shared logic for reading Tales of Monkey Island 3 save files.
"""
import struct
import os

# TellTale .save file magic (raw, first 4 bytes)
FILE_MAGIC = bytes.fromhex('AADEAF64')

# Signature (decoded, after XOR 0xFF):
# The 16 bytes that always appear directly before the grub count
SIGNATURE = bytes.fromhex('02000000a15a219753c00e510000000000000000'[:32])

SAVEDIR = os.path.join(
    os.path.expanduser("~"), "Documents", "Telltale Games", "Tales of Monkey Island 3"
)


def read_grub_count(filepath):
    """
    Read the nGrubsCollected count from a .save file.
    Returns (count: int, error: None) on success,
            (None, error: str)  on failure.
    """
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
        return None, "no grub count (wrong chapter?)"

    count_offset = idx + len(SIGNATURE)
    if count_offset + 4 > len(dec):
        return None, "file corrupted (too short)"

    count = struct.unpack_from('<I', dec, count_offset)[0]
    return count, None

"""
Tales of Monkey Island 3 - Live Grub Count Monitor (CLI)
Reads the grub count directly from the running game process.
Works on Windows (native) and Linux (Proton/Wine).

Strategy:
  1. Scan all readable memory for the nGrubsCollected node signature:
       A1 5A 21 97  (hash1, LE)
       53 C0 0E 51  (hash2, LE)
       5C 8F 8D 00  (Int type descriptor, LE)
     Count DWORD follows at +0x0C from hash1 start.

  2. Multiple copies exist (GC history). Filter by "locality" heuristic:
     The ACTIVE node has 1-3 non-null fields at offsets -0x10, -0x0C, -0x08
     (relative to hash1 start) that are HEAP POINTERS pointing nearby
     i.e. within +/- 4MB of the node itself. Dead nodes have either
     all-zero or have unrelated values there (e.g. 0x11FBxxxx).

  3. Among active candidates, prefer the one with the most local pointers.
     If tied, prefer the highest count (the persistent zero-VM
     candidate always has value 0; the real node has the actual count).

  4. Cache the active node address. Subsequent polls read only 4 bytes at
     that address instead of doing a full scan, keeping CPU usage minimal.
     The cache is invalidated and a new full scan is triggered when:
       - the read fails (node unmapped)
       - the count decreased (save reloaded to an earlier point)
       - the count jumped by more than 1 (save reloaded to a later point,
         or stale address pointing to unrelated data)
       - the last known value was 0 (can't distinguish real 0 from a dead
         node that also reads 0)

Usage:
  python monitor_grub_count.py                               -> poll every second, write to grub_count.txt
  python monitor_grub_count.py --output <file>              -> write to a custom file instead
  python monitor_grub_count.py --once                        -> print count once
  python monitor_grub_count.py --verbose                     -> same, with debug output
  default behavior: startup-zero protection enabled
  python monitor_grub_count.py --no-preserve-on-loading-zero -> disable startup-zero protection
"""

import sys
import time
from pathlib import Path

try:
    from _version import __version__
except ImportError:
    try:
        from importlib.metadata import version, PackageNotFoundError

        __version__ = version("tomi3-grub-counter")
    except PackageNotFoundError:
        __version__ = "?"

from tomi3_ram import (
    PROCESS_NAME,
    DEFAULT_OUTPUT_FILE,
    POLL_INTERVAL,
    find_pid,
    open_process,
    close_process,
    is_process_alive,
    scan_for_count,
    read_live_count,
)


def _read_stored_count(path):
    try:
        text = Path(path).read_text().strip()
    except OSError:
        return None
    if text.isdigit():
        return int(text)
    return None


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Read the nGrubsCollected count live from the running game process. "
        "Waits for the game to launch if it is not already running. "
        "Works on Windows (native) and Linux (Proton/Wine).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s v{__version__}")
    parser.add_argument(
        "--output",
        metavar="FILE",
        default=DEFAULT_OUTPUT_FILE,
        help=f"write count to FILE instead of {DEFAULT_OUTPUT_FILE}",
    )
    parser.add_argument(
        "--once", action="store_true", help="print the count once and exit (no file written)"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="print debug info about candidate nodes"
    )
    parser.set_defaults(preserve_on_loading_zero=True)
    parser.add_argument(
        "--preserve-on-loading-zero",
        action="store_true",
        dest="preserve_on_loading_zero",
        help="keep the previous stored count when a live read is 0 during game startup/loading (default: enabled)",
    )
    parser.add_argument(
        "--no-preserve-on-loading-zero",
        action="store_false",
        dest="preserve_on_loading_zero",
        help="disable startup-zero protection and allow writing live 0 values during loading",
    )
    args = parser.parse_args()

    once = args.once
    verbose = args.verbose
    output_file = args.output
    preserve_on_loading_zero = args.preserve_on_loading_zero

    pid = find_pid(PROCESS_NAME)
    if pid is None:
        print(f"Waiting for {PROCESS_NAME} to be launched... (Ctrl+C to cancel)", end="", flush=True)
        try:
            while pid is None:
                time.sleep(1.0)
                pid = find_pid(PROCESS_NAME)
        except KeyboardInterrupt:
            print("\nCancelled.")
            sys.exit(0)
        print()

    print(f"Attached to {PROCESS_NAME} (pid={pid})")

    try:
        handle = open_process(pid)
    except OSError as e:
        print(f"Error: {e}")
        sys.exit(1)

    try:
        if once:
            value, _ = scan_for_count(handle, verbose)
            if value is None:
                print("Count not found (game not in episode 3?)")
            else:
                print(f"Grub Count: {value}")
        else:
            print(f"Counting grubs... writing to {output_file} (Ctrl+C to stop)")

            last_seen = None
            last_written = None
            if preserve_on_loading_zero:
                last_written = _read_stored_count(output_file)
                if last_written is not None and last_written > 0:
                    print(f"Preserving stored count while loading zeros: {last_written}")

            cached_node_addr = None
            holding_loading_zero = False

            while True:
                try:
                    value, cached_node_addr = read_live_count(
                        handle,
                        last_value=last_seen,
                        cached_node_addr=cached_node_addr,
                        verbose=verbose,
                    )
                except FileNotFoundError:
                    print("\nGame process ended. Exiting.")
                    break

                if not is_process_alive(handle):
                    print("\nGame process ended. Exiting.")
                    break

                if (
                    preserve_on_loading_zero
                    and value == 0
                    and last_written not in (None, 0)
                ):
                    if not holding_loading_zero:
                        print(f"Grub Count: loading (live 0, keeping {last_written})")
                        holding_loading_zero = True
                    last_seen = value
                    time.sleep(POLL_INTERVAL)
                    continue

                holding_loading_zero = False

                if value != last_written:
                    last_written = value
                    display = str(value) if value is not None else "?"
                    print(f"Grub Count: {display}")
                    with open(output_file, "w") as f:
                        f.write(display)

                last_seen = value
                time.sleep(POLL_INTERVAL)
    finally:
        close_process(handle)


if __name__ == "__main__":
    main()



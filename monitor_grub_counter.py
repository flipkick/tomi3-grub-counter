"""
Tales of Monkey Island 3 - Live Grub Counter Reader (RAM)
Reads the grub counter directly from the running game process.
Works on Windows (native) and Linux (Proton/Wine).

Strategy:
  1. Scan all readable memory for the nGrubsCollected node signature:
       A1 5A 21 97  (hash1, LE)
       53 C0 0E 51  (hash2, LE)
       5C 8F 8D 00  (Int type descriptor, LE)
     Counter DWORD follows at +0x0C from hash1 start.

  2. Multiple copies exist (GC history). Filter by "locality" heuristic:
     The ACTIVE node has 1-3 non-null fields at offsets -0x10, -0x0C, -0x08
     (relative to hash1 start) that are HEAP POINTERS pointing nearby
     i.e. within +/- 4MB of the node itself. Dead nodes have either
     all-zero or have unrelated values there (e.g. 0x11FBxxxx).

  3. Among active candidates, prefer the one with the most local pointers.
     If tied, prefer the highest counter value (the persistent zero-VM
     candidate always has value 0; the real counter has the actual count).

  4. Cache the active node address. Subsequent polls read only 4 bytes at
     that address instead of doing a full scan, keeping CPU usage minimal.
     The cache is invalidated and a new full scan is triggered when:
       - the read fails (node unmapped)
       - the counter decreased (save reloaded to an earlier point)
       - the counter jumped by more than 1 (save reloaded to a later point,
         or stale address pointing to unrelated data)
       - the last known value was 0 (can't distinguish real 0 from a dead
         node that also reads 0)

Usage:
  python monitor_grub_counter.py                        -> poll every second, write to grub_counter.txt
  python monitor_grub_counter.py --output <file>        -> write to a custom file instead
  python monitor_grub_counter.py --once                 -> print counter once
  python monitor_grub_counter.py --verbose              -> same, with debug output
"""

import os
import struct
import subprocess
import sys
import time

# Node signature: hash1 + hash2 + type descriptor (12 bytes starting at hash1)
SIGNATURE = bytes.fromhex('A15A219753C00E515C8F8D00')

# Counter DWORD is at +0x0C from hash1 start
COUNTER_OFFSET = 0x0C

# Plausible counter range (never negative)
COUNTER_MAX = 200_000

# Locality check offsets (relative to hash1 start): fields that hold
# nearby heap pointers in the active node
LOCALITY_OFFSETS = [-0x10, -0x0C, -0x08]
LOCALITY_MAX_DELTA = 4 * 1024 * 1024  # 4 MB, active node pointers stay close

PROCESS_NAME = "MonkeyIsland103.exe"
DEFAULT_OUTPUT_FILE = "grub_counter.txt"
POLL_INTERVAL = 1.0  # seconds

IS_LINUX = sys.platform.startswith("linux")

# ── Windows backend ──────────────────────────────────────────────────────────

if not IS_LINUX:
    import ctypes
    import ctypes.wintypes

    kernel32 = ctypes.windll.kernel32
    PROCESS_VM_READ = 0x0010
    PROCESS_QUERY_INFORMATION = 0x0400
    MEM_COMMIT    = 0x1000
    PAGE_NOACCESS = 0x01
    PAGE_GUARD    = 0x100
    STILL_ACTIVE  = 259

    class MEMORY_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BaseAddress",       ctypes.c_void_p),
            ("AllocationBase",    ctypes.c_void_p),
            ("AllocationProtect", ctypes.wintypes.DWORD),
            ("RegionSize",        ctypes.c_size_t),
            ("State",             ctypes.wintypes.DWORD),
            ("Protect",           ctypes.wintypes.DWORD),
            ("Type",              ctypes.wintypes.DWORD),
        ]


def find_pid(name):
    if IS_LINUX:
        try:
            out = subprocess.check_output(["pgrep", "-fi", name], text=True)
            return int(out.split()[0])
        except subprocess.CalledProcessError:
            return None
    else:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
            text=True
        )
        for line in out.splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if parts and parts[0].lower() == name.lower():
                return int(parts[1])
        return None


def open_process(pid):
    if IS_LINUX:
        # On Linux the "handle" is just the pid — /proc/<pid>/mem is opened
        # per-read. Verify access by opening maps.
        maps_path = f"/proc/{pid}/maps"
        if not os.path.exists(maps_path):
            raise OSError(f"Cannot access /proc/{pid}/maps — run as the same user or root")
        return pid
    else:
        handle = kernel32.OpenProcess(
            PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid
        )
        if not handle:
            raise OSError(f"OpenProcess failed (pid={pid}) — are you running as Administrator?")
        return handle


def read_memory(handle, address, size):
    if IS_LINUX:
        try:
            with open(f"/proc/{handle}/mem", "rb") as f:
                f.seek(address)
                data = f.read(size)
                return data if data else None
        except OSError:
            return None
    else:
        import ctypes
        buf = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t(0)
        ok = kernel32.ReadProcessMemory(
            handle, ctypes.c_void_p(address), buf, size, ctypes.byref(read)
        )
        if not ok or read.value == 0:
            return None
        return buf.raw[:read.value]


def iter_readable_regions(handle):
    """Yield (base_address, size) for all readable committed pages."""
    if IS_LINUX:
        with open(f"/proc/{handle}/maps", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 2:
                    continue
                perms = parts[1]
                if "r" not in perms:
                    continue
                addr_range = parts[0].split("-")
                start = int(addr_range[0], 16)
                end   = int(addr_range[1], 16)
                yield start, end - start
    else:
        import ctypes
        mbi = MEMORY_BASIC_INFORMATION()
        addr = 0
        while True:
            ret = kernel32.VirtualQueryEx(
                handle, ctypes.c_void_p(addr),
                ctypes.byref(mbi), ctypes.sizeof(mbi)
            )
            if not ret:
                break
            if (mbi.State == MEM_COMMIT and
                    not (mbi.Protect & PAGE_NOACCESS) and
                    not (mbi.Protect & PAGE_GUARD)):
                yield mbi.BaseAddress, mbi.RegionSize
            addr = (mbi.BaseAddress or 0) + mbi.RegionSize
            if addr >= 0xFFFFFFFF:
                break


def close_process(handle):
    if not IS_LINUX:
        import ctypes
        ctypes.windll.kernel32.CloseHandle(handle)


def is_process_alive(handle):
    if IS_LINUX:
        return os.path.exists(f"/proc/{handle}/maps")
    else:
        import ctypes
        code = ctypes.wintypes.DWORD(0)
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        return bool(ok) and code.value == STILL_ACTIVE


# ── Core logic (platform-independent) ────────────────────────────────────────

def count_local_pointers(data, idx, node_addr):
    """
    Count how many of the fields at offsets -0x10, -0x0C, -0x08 from hash1
    contain a value that looks like a nearby heap pointer (within 4MB of node).
    """
    count = 0
    for rel in LOCALITY_OFFSETS:
        field_idx = idx + rel
        if field_idx < 0 or field_idx + 4 > len(data):
            continue
        val = struct.unpack_from('<I', data, field_idx)[0]
        if val == 0:
            continue
        # Must be a plausible heap address (not in EXE/stack/kernel range)
        if val < 0x01000000 or val > 0x7FFFFFFF:
            continue
        # Must be close to the node itself
        if abs(val - node_addr) <= LOCALITY_MAX_DELTA:
            count += 1
    return count


def read_counter_at(handle, node_addr):
    """
    Fast path: read the counter DWORD directly from a known node address.
    Returns the value, or None if the read fails or the value is implausible.
    """
    data = read_memory(handle, node_addr + COUNTER_OFFSET, 4)
    if not data or len(data) < 4:
        return None
    value = struct.unpack_from('<I', data, 0)[0]
    return value if value <= COUNTER_MAX else None


def scan_for_counter(handle, verbose=False):
    """
    Scan all readable memory for nGrubsCollected nodes.
    Returns (value, node_addr) for the active node, or (None, None).
    """
    candidates = []

    for base, size in iter_readable_regions(handle):
        data = read_memory(handle, base, size)
        if not data:
            continue

        offset = 0
        while True:
            idx = data.find(SIGNATURE, offset)
            if idx == -1:
                break
            offset = idx + 1

            if idx < 0x10:
                continue

            val_offset = idx + COUNTER_OFFSET
            if val_offset + 4 > len(data):
                continue

            value = struct.unpack_from('<I', data, val_offset)[0]
            if value > COUNTER_MAX:
                continue

            node_addr   = base + idx
            local_count = count_local_pointers(data, idx, node_addr)
            candidates.append((node_addr, value, local_count))

    if not candidates:
        return None, None

    if verbose:
        for addr, val, lc in sorted(candidates):
            print(f"  candidate: addr=0x{addr:08X}  value={val:6d}  local_ptrs={lc}")

    active = [(a, v, lc) for a, v, lc in candidates if lc >= 1]

    if not active:
        return None, None

    if verbose:
        print(f"  active candidates: {[(f'0x{a:08X}', v, lc) for a, v, lc in active]}")

    if len(active) == 1:
        return active[0][1], active[0][0]

    best_lc = max(lc for _, _, lc in active)
    top = [(a, v, lc) for a, v, lc in active if lc == best_lc]

    if len(top) == 1:
        return top[0][1], top[0][0]

    # Still tied: prefer highest value (the persistent zero-VM candidate
    # always has value 0; the real counter has the actual count)
    top.sort(key=lambda x: x[1], reverse=True)
    return top[0][1], top[0][0]


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Read the nGrubsCollected counter live from the running game process. "
                    "Waits for the game to launch if it is not already running. "
                    "Works on Windows (native) and Linux (Proton/Wine).",
    )
    parser.add_argument("--output", metavar="FILE", default=DEFAULT_OUTPUT_FILE,
                        help=f"write counter to FILE instead of {DEFAULT_OUTPUT_FILE}")
    parser.add_argument("--once", action="store_true",
                        help="print the counter once and exit (no file written)")
    parser.add_argument("--verbose", action="store_true",
                        help="print debug info about candidate nodes")
    args = parser.parse_args()

    once        = args.once
    verbose     = args.verbose
    output_file = args.output

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
            value, _ = scan_for_counter(handle, verbose)
            if value is None:
                print("Counter not found (game not in episode 3?)")
            else:
                print(f"Grub Count: {value}")
        else:
            print(f"Counting grubs... writing to {output_file} (Ctrl+C to stop)")
            last = None
            cached_node_addr = None
            while True:
                try:
                    if cached_node_addr is not None and last != 0:  # last==0: can't trust cache (dead node also reads 0)
                        value = read_counter_at(handle, cached_node_addr)
                        if value is None or (last is not None and (value < last or value > last + 1)):
                            # Address stale or implausible jump (save reload) — full scan
                            value, cached_node_addr = scan_for_counter(handle, verbose)
                    else:
                        value, cached_node_addr = scan_for_counter(handle, verbose)
                except FileNotFoundError:
                    print("\nGame process ended. Exiting.")
                    break
                if not is_process_alive(handle):
                    print("\nGame process ended. Exiting.")
                    break
                if value != last:
                    last = value
                    display = str(value) if value is not None else "?"
                    print(f"Grub Count: {display}")
                    with open(output_file, "w") as f:
                        f.write(display)
                time.sleep(POLL_INTERVAL)
    finally:
        close_process(handle)


if __name__ == "__main__":
    main()

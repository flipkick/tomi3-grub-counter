"""
Tales of Monkey Island 3 - RAM reading library
Shared logic for monitor_grub_count and monitor_grub_count_gui.

Provides process attachment, memory scanning, and the nGrubsCollected
node-finding heuristic for both Windows (native) and Linux (Proton/Wine).
"""

import os
import struct
import subprocess
import sys

# ── Constants ─────────────────────────────────────────────────────────────────

# Node signature: hash1 + hash2 + type descriptor (12 bytes starting at hash1)
SIGNATURE = bytes.fromhex('A15A219753C00E515C8F8D00')

# Count DWORD is at +0x0C from hash1 start
COUNT_OFFSET = 0x0C

# Plausible count range (never negative)
COUNT_MAX = 200_000

# Locality check offsets (relative to hash1 start): fields that hold
# nearby heap pointers in the active node
LOCALITY_OFFSETS = [-0x10, -0x0C, -0x08]
LOCALITY_MAX_DELTA = 4 * 1024 * 1024  # 4 MB, active node pointers stay close

PROCESS_NAME = "MonkeyIsland103.exe"
DEFAULT_OUTPUT_FILE = "grub_count.txt"
POLL_INTERVAL = 1.0  # seconds

IS_LINUX = sys.platform.startswith("linux")

# ── Windows backend ───────────────────────────────────────────────────────────

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

# ── Process helpers ───────────────────────────────────────────────────────────

def find_pid(name):
    if IS_LINUX:
        try:
            out = subprocess.check_output(["pgrep", "-fi", name], text=True)
            return int(out.split()[0])
        except subprocess.CalledProcessError:
            return None
    else:
        # Use CreateToolhelp32Snapshot instead of spawning tasklist
        # no subprocess means no flashing console window in GUI mode.
        import ctypes

        TH32CS_SNAPPROCESS  = 0x00000002
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize",              ctypes.wintypes.DWORD),
                ("cntUsage",            ctypes.wintypes.DWORD),
                ("th32ProcessID",       ctypes.wintypes.DWORD),
                ("th32DefaultHeapID",   ctypes.c_size_t),   # ULONG_PTR
                ("th32ModuleID",        ctypes.wintypes.DWORD),
                ("cntThreads",          ctypes.wintypes.DWORD),
                ("th32ParentProcessID", ctypes.wintypes.DWORD),
                ("pcPriClassBase",      ctypes.c_long),
                ("dwFlags",             ctypes.wintypes.DWORD),
                ("szExeFile",           ctypes.c_char * 260),
            ]

        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == INVALID_HANDLE_VALUE:
            return None

        try:
            entry = PROCESSENTRY32()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
            if kernel32.Process32First(snap, ctypes.byref(entry)):
                while True:
                    if entry.szExeFile.decode(errors="replace").lower() == name.lower():
                        return entry.th32ProcessID
                    if not kernel32.Process32Next(snap, ctypes.byref(entry)):
                        break
        finally:
            kernel32.CloseHandle(snap)

        return None


def open_process(pid):
    if IS_LINUX:
        # On Linux the "handle" is just the pid, /proc/<pid>/mem is opened
        # per-read. Verify access by opening maps.
        maps_path = f"/proc/{pid}/maps"
        if not os.path.exists(maps_path):
            raise OSError(f"Cannot access /proc/{pid}/maps. Run as the same user or root.")
        return pid
    else:
        handle = kernel32.OpenProcess(
            PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid
        )
        if not handle:
            raise OSError(f"OpenProcess failed (pid={pid}). Are you running as Administrator?")
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

# ── Core scan logic (platform-independent) ────────────────────────────────────

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


def read_count_at(handle, node_addr):
    """
    Fast path: read the count DWORD directly from a known node address.
    Returns the value, or None if the read fails or the value is implausible.
    """
    data = read_memory(handle, node_addr + COUNT_OFFSET, 4)
    if not data or len(data) < 4:
        return None
    value = struct.unpack_from('<I', data, 0)[0]
    return value if value <= COUNT_MAX else None


def scan_for_count(handle, verbose=False):
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

            val_offset = idx + COUNT_OFFSET
            if val_offset + 4 > len(data):
                continue

            value = struct.unpack_from('<I', data, val_offset)[0]
            if value > COUNT_MAX:
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
    # always has value 0; the real node has the actual count)
    top.sort(key=lambda x: x[1], reverse=True)
    return top[0][1], top[0][0]

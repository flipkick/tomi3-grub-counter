# Tales of Monkey Island 3 Grub Count Reader

## Why This Exists

These tools were built for **[thewoofs](https://twitch.tv/thewoofs)**, a Twitch streamer who took on an absurd self-imposed challenge: manually collecting all 100,000 grubs in *Tales of Monkey Island: Chapter 3*.

The game itself never actually seriously asks you to do this. De Cava mentions the grubs as part of an escape plan, and Guybrush immediately finds a workaround instead. Collecting them one by one is entirely pointless, extremely tedious, and exactly the kind of thing that makes for relaxed streaming content.

thewoofs turned this into something even bigger: the **Bon-a-thon**, a charity stream where he grinds grubs for the entire event while guests come on to speedrun games. The event is a fundraiser for the [Animal Rescue Fund of the Hamptons](https://www.arfhamptons.org/) where woof's dog Bonnie is from.

Go give him a follow: **<https://twitch.tv/thewoofs>**

# Content

Three tools for reading the **grub count** from *Tales of Monkey Island: Chapter 3: Lair of the Leviathan*:

- `extract_grub_count_from_save` — Read grub count from a `.save` file (CLI)
- `extract_grub_count_from_save_gui` — Read grub count from a `.save` file (GUI)
- `monitor_grub_count` — Read grub count live from the running game (for OBS etc.)

## Installation

```
pip install tomi3-grub-counter
```

After installation, `monitor_grub_count`, `extract_grub_count_from_save`, and `extract_grub_count_from_save_gui` are available as commands directly.

## monitor_grub_count - Live RAM Reader

Attaches to the running game process and reads the grub count directly from memory. Works with and without a save file, including when the grub count is 0.

### Requirements

- Python 3.x (no third-party packages)
- Run as **Administrator** (required for `ReadProcessMemory`)
- `monkeyisland103.exe` must be running

### Usage

```
monitor_grub_count                   # poll every second, write to grub_count.txt
monitor_grub_count --output <file>   # write to a custom file instead
monitor_grub_count --once            # print grub count once and exit (no file written)
monitor_grub_count --verbose         # print debug info about candidate nodes
monitor_grub_count --help            # show all options
```

If the game is not running when the script starts, it will wait and retry every second until the process appears. Press **Ctrl+C** to cancel the wait.

The current grub count is written to `grub_count.txt` in the working directory whenever it changes. Point an OBS Text source at that file.

### How It Works

**Caveat: parts of this are educated guesses. Assume nothing, verify everything.**

TellTale's engine stores Lua scripting variables in a dynamic hash table in the heap. There is no static pointer chain to `nGrubsCollected`. The address changes every session and every time a save is loaded.

**Step 1: Signature scan**

The variable node has a fixed 12-byte signature at its start:

```
A1 5A 21 97  hash1 (engine hash of "nGrubsCollected")
53 C0 0E 51  hash2
5C 8F 8D 00  integer type descriptor (static .rdata address)
```

The count DWORD follows at `+0x0C`. The tool scans all readable memory regions for this signature.

**Step 2: Locality filter**

Multiple copies of the node exist in RAM at all times: the active entry, GC history copies from previous saves, and entries from a second persistent Lua VM (the engine/menu VM) that always runs alongside the game VM.

Active nodes are distinguished by the three fields immediately before the signature (at offsets `-0x10`, `-0x0C`, `-0x08` relative to hash1). In a live node these fields contain heap pointers that point within +/- 4 MB of the node itself, internal references of the hash table structure. In dead nodes these fields are either zero or contain unrelated values from a completely different address range.

**Step 3: Tiebreaker**

After the locality filter, two active candidates typically remain: the real game count and a `nGrubsCollected=0` entry in the engine VM (which also has valid nearby pointers). When both have the same locality score, the one with the **higher value** wins. When the real count is also 0, both candidates have value 0, so the result is correct either way.

**Step 4: Caching**

After a successful scan the node address is cached. Subsequent polls read only 4 bytes directly from that address rather than scanning all memory, keeping CPU usage negligible. The cache is invalidated and a new full scan is triggered if the read fails, the count decreases (save reloaded to an earlier point), or the count jumps by more than 1 (save reloaded to a later point). When the last known value was 0 the cache is not used, because a dead node that also reads 0 is indistinguishable from a live one.

## extract_grub_count_from_save - Save File Reader

Reads the grub count from a `.save` file without the game running.

### Usage

```
extract_grub_count_from_save                        # all saves in the default Windows game directory
extract_grub_count_from_save --dir <folder>         # all saves in a custom directory
extract_grub_count_from_save <path>.save            # single file
extract_grub_count_from_save --help                 # show all options
```

**Default save directory:**

```
C:\Users\<name>\Documents\Telltale Games\Tales of Monkey Island 3\
```

### Save File Format

| Field | Value |
|---|---|
| Magic bytes (raw) | `AA DE AF 64` |
| Encoding | XOR `0xFF` (bitwise NOT) |
| Structure | `[4-byte LE length][ASCII key][data]` repeated entries |

The count is located by searching for a fixed 16-byte signature in the decoded data:

```
02 00 00 00  A1 5A 21 97  53 C0 0E 51  00 00 00 00
```

Followed by the count as a **DWORD (uint32, Little-Endian)**.

## Reverse Engineering Notes

**Caveat: parts of this are educated guesses. Assume nothing, verify everything.**

Reversed using x32dbg attached to `monkeyisland103.exe` (32-bit, TellTale Tool engine, Lua 5.1 scripting).

**Save file format** found via `CreateFileA`/`ReadFile` breakpoints to intercept I/O. XOR `0xFF` encoding identified by manual byte analysis. Count location pinned by diffing saves at known count values.

**RAM location** no static pointer chain exists to the Lua variable; Cheat Engine pointer scanner from the EXE base found zero results. The engine manages all script variables in a dynamic hash table.

**Hash values** `0x97215AA1` and `0x510EC053` are TellTale's engine hashes of `"nGrubsCollected"`, not standard Lua string hashes. The variable name itself only appears as a literal in compiled Lua bytecode, not as an interned string in the hash table.

**Node structure** (56 bytes, offset from hash1 start):

```
-0x20  next field
-0x10  internal table pointer (nearby heap addr in active nodes)
-0x0C  internal table pointer (nearby heap addr in active nodes)
-0x08  internal table pointer (nearby heap addr in active nodes)
+0x00  hash1  A1 5A 21 97
+0x04  hash2  53 C0 0E 51
+0x08  type   5C 8F 8D 00  (integer type descriptor, .rdata)
+0x0C  value  DWORD        ← grub count
```

**Multiple copies problem** At any point 8-10 nodes matching the signature exist in RAM simultaneously: active entry, GC history from previous loads, hash-colliding variables from other tables, and a second engine Lua VM that always holds `nGrubsCollected=0`. The locality heuristic (fields at -0x10/-0x0C/-0x08 point within +/-4 MB) cleanly separates active from dead nodes. The persistent engine-VM zero entry is eliminated by the highest-value tiebreaker.

## extract_grub_count_from_save_gui - Save File Reader (GUI)

Same functionality as the CLI tool but with a graphical interface. Requires no arguments.

### Requirements

- Python 3.x with `tkinter` (included in the standard library on Windows)

### Usage

```
extract_grub_count_from_save_gui
```

- The default save directory is pre-filled and scanned automatically on launch
- Use **Browse…** to select a different directory, **Refresh** to re-scan
- Use **Open single file…** to read one specific `.save` file

## License

MIT, see [LICENSE](LICENSE).

## Author

flip - reverse engineering and tool development.  
With occasional help from Claude Code, using Claude Sonnet 4.6 (LLM). And occasional disagreement. No warranty implied.

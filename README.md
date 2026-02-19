# Tales of Monkey Island 3 - Grub Counter Reader

Reads the **grub counter** from `.save` files of *Tales of Monkey Island - Chapter 3: Lair of the Leviathan*.

---

## Usage

```
python read_grub_counter.py                   # all saves in the default game directory
python read_grub_counter.py <path>.save       # single file
```

**Default save directory:**
```
C:\Users\<name>\Documents\Telltale Games\Tales of Monkey Island 3\
```

---

## Save File Format

| Field | Value |
|---|---|
| Magic bytes (raw) | `AA DE AF 64` |
| Encoding | XOR `0xFF` (bitwise NOT) |
| Structure | `[4-byte LE length][ASCII key][data]` - repeated entries |

### Grub Counter Signature

The counter is located by searching for a fixed 16-byte signature in the decoded data that always appears directly before the grub counter DWORD:

```
02 00 00 00  A1 5A 21 97  53 C0 0E 51  00 00 00 00
```

Followed by the counter as a **DWORD (uint32, Little-Endian)**.

---

## How It Was Found

The format was reverse-engineered using x32dbg attached to `monkeyisland103.exe`:
- `CreateFileA` / `ReadFile` breakpoints to intercept save file I/O
- XOR `0xFF` encoding identified by manual byte analysis
- Counter location found by diffing saves at known counter values (49999 / 50000 / 50001)

---

## Author

flip - reverse engineering & tool development

---

## License

[MIT](LICENSE)

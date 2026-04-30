#!/usr/bin/env python3
"""dump_villager_state.py — print every villager slot's identity bytes.

Usage:
    python3 scripts/dump_villager_state.py <RVFOREST.DAT> [pack.bin]

For each occupied slot prints v_id, v_id2, exists byte, primary/secondary
name, catchphrase, species byte, personality, and (if pack.bin given) the
canonical pack values for that v_id with mismatch flags.

Used to verify whether write_villager_template actually wrote what we
expect, and to spot fields the game may be reading from somewhere we
haven't found yet.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VILLAGER_START = 0x21B20
VILLAGER_STRIDE = 0x3040
VILLAGER_COUNT = 10

PERS = {0: "Lazy", 1: "Jock", 2: "Cranky", 3: "Normal", 4: "Peppy", 5: "Snooty"}
SPECIES = {
    0: "Cat", 1: "Elephant", 2: "Sheep", 3: "Bear", 4: "Dog",
    5: "Squirrel", 6: "Rabbit", 7: "Duck", 8: "Hippo", 9: "Wolf",
    10: "Mouse", 11: "Pig", 12: "Chicken", 13: "Bull", 14: "Cow",
    15: "Bird", 16: "Frog", 17: "Alligator", 18: "Goat", 19: "Tiger",
    20: "Anteater", 21: "Koala", 22: "Horse", 23: "Octopus", 24: "Lion",
    25: "Bear Cub", 26: "Rhinoceros", 27: "Gorilla", 28: "Ostrich",
    29: "Kangaroo", 30: "Eagle", 31: "Penguin", 32: "Monkey",
}


def utf16_be(data: bytes) -> str:
    try:
        return data.decode("utf-16-be").rstrip("\x00")
    except UnicodeDecodeError:
        return f"<bytes:{data.hex()}>"


def dump_slot(data: bytes, slot: int, pack: bytes | None) -> None:
    base = VILLAGER_START + slot * VILLAGER_STRIDE
    exists = data[base + 0x0000]
    v_id = struct.unpack_from(">H", data, base + 0x1824)[0]
    v_id2 = struct.unpack_from(">H", data, base + 0x2308)[0]
    pers = data[base + 0x230A]
    species = data[base + 0x19B2]
    birth_m = data[base + 0x19B3]
    birth_d = data[base + 0x19B4]
    starter = data[base + 0x19BB]

    name_pri = utf16_be(data[base + 0x1858 : base + 0x1858 + 18])
    name_sec_ja = utf16_be(data[base + 0x2278 : base + 0x2278 + 18])
    name_sec_en = utf16_be(data[base + 0x228A : base + 0x228A + 18])
    catch = utf16_be(data[base + 0x18EC : base + 0x18EC + 22])

    occupied = exists != 0 or v_id != 0
    if not occupied:
        print(f"  slot {slot}: <empty>")
        return

    print(f"  slot {slot}: exists=0x{exists:02X}  v_id=0x{v_id:04X} v_id2=0x{v_id2:04X}")
    print(f"           name(pri)={name_pri!r:14s}  name(sec en_us)={name_sec_en!r:14s}  name(sec ja)={name_sec_ja!r}")
    print(f"           species={species} ({SPECIES.get(species, '?')})  birth={birth_m}/{birth_d}  pers={pers} ({PERS.get(pers, '?')})  starter=0x{starter:02X}")
    print(f"           catchphrase={catch!r}")

    if pack is not None and v_id != 0 and v_id != 0xFFFF:
        pack_off = 32 + v_id * 408
        if pack_off + 408 > len(pack):
            print(f"           [pack.bin: v_id 0x{v_id:04X} out of range]")
            return
        pack_species = pack[pack_off + 0x18E]
        pack_name_en = utf16_be(pack[pack_off + 0x22 + 18 : pack_off + 0x22 + 36])
        pack_catch_en = utf16_be(pack[pack_off + 0xB2 + 22 : pack_off + 0xB2 + 44])
        pack_pers = (pack[pack_off + 0x196] >> 4) & 0xF
        flags = []
        if pack_species != species:
            flags.append(f"species(save={species}!=pack={pack_species})")
        if name_sec_en != pack_name_en and name_sec_en != "":
            flags.append(f"name(sec={name_sec_en!r}!=pack={pack_name_en!r})")
        if catch != pack_catch_en and catch != "":
            flags.append(f"catch(save={catch!r}!=pack={pack_catch_en!r})")
        if pack_pers != pers:
            flags.append(f"pers(save={pers}!=pack={pack_pers})")
        if flags:
            print(f"           ✗ MISMATCH vs pack[0x{v_id:04X}={pack_name_en!r}]: " + ", ".join(flags))
        else:
            print(f"           ✓ matches pack[0x{v_id:04X}={pack_name_en!r}]")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    save_path = Path(sys.argv[1])
    if not save_path.is_file():
        print(f"save file not found: {save_path}", file=sys.stderr)
        return 1
    pack_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    if pack_path is not None and not pack_path.is_file():
        print(f"pack.bin not found: {pack_path}", file=sys.stderr)
        return 1

    data = save_path.read_bytes()
    pack = pack_path.read_bytes() if pack_path else None

    print(f"=== {save_path} ({len(data)} bytes) ===")
    for slot in range(VILLAGER_COUNT):
        dump_slot(data, slot, pack)
    return 0


if __name__ == "__main__":
    sys.exit(main())

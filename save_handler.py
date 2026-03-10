"""
save_handler.py - Core binary I/O handler for Animal Crossing: City Folk (Wii) save files.

Handles RVFOREST.DAT files (exactly 0x40F340 = 4,256,576 bytes).
All multi-byte values are big-endian (PowerPC / Wii byte order).

CRC32 implementation matches the original Delphi ACToolkit exactly:
  - Standard IEEE 802.3 CRC32 lookup table
  - Four distinct CRC regions (player, town, buildings, extended)
  - CRCs are byte-swapped before writing (native little-endian -> big-endian storage)
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAVE_SIZE = 0x40F340  # 4,256,576 bytes

PLAYER_STRIDE = 0x86C0
PLAYER_COUNT = 4

# Empty-player CRC sentinel (CRC of an all-zero/uninitialised player block)
EMPTY_PLAYER_CRC = 0xE4A45761

# CRC seeds
CRC_SEED_DEFAULT = 0xFFFFFFFF
CRC_SEED_BUILDINGS = 0x12141018

# Catalog item ranges  {name: (start_code, end_code)}
CATALOG_RANGES = {
    "furniture":  (0xB710, 0xC248),
    "paper":      (0x9640, 0x974C),
    "wallpaper":  (0x9FA0, 0xA100),
    "flooring":   (0xA2C0, 0xA418),
    "clothes":    (0xA518, 0xAA80),
    "umbrella":   (0xAA90, 0xAB18),
    "headgear1":  (0xAC20, 0xAD5C),
    "headgear2":  (0xADB0, 0xAE7C),
    "glasses":    (0xAF40, 0xAFFC),
    "gyroids":    (0xB3F0, 0xB5EC),
    "fossils":    (0xCC28, 0xCD10),
    "music":      (0xD000, 0xD138),
}

# ---------------------------------------------------------------------------
# Standard IEEE 802.3 CRC32 lookup table (256 entries)
# ---------------------------------------------------------------------------

_CRC32_TABLE: list[int] = []

def _build_crc32_table() -> list[int]:
    """Build the standard CRC32 lookup table (polynomial 0xEDB88320)."""
    if _CRC32_TABLE:
        return _CRC32_TABLE
    poly = 0xEDB88320
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ poly
            else:
                crc >>= 1
        _CRC32_TABLE.append(crc & 0xFFFFFFFF)
    return _CRC32_TABLE


def _crc32_stream(data: bytearray, start: int, end: int, seed: int) -> int:
    """
    Compute CRC32 over data[start:end] with the given seed.

    Matches the original Delphi implementation:
        TempResult = seed
        for each byte:
            TempResult = ((TempResult >> 8) & 0xFFFFFF) ^ table[(TempResult ^ byte) & 0xFF]
        return ~TempResult & 0xFFFFFFFF
    """
    table = _build_crc32_table()
    result = seed & 0xFFFFFFFF
    for i in range(start, end):
        result = ((result >> 8) & 0x00FFFFFF) ^ table[(result ^ data[i]) & 0xFF]
    return (~result) & 0xFFFFFFFF


def _byte_swap_32(value: int) -> int:
    """Swap bytes of a 32-bit integer (little-endian <-> big-endian)."""
    return (
        ((value & 0x000000FF) << 24)
        | ((value & 0x0000FF00) << 8)
        | ((value & 0x00FF0000) >> 8)
        | ((value & 0xFF000000) >> 24)
    )


# ---------------------------------------------------------------------------
# SaveHandler
# ---------------------------------------------------------------------------

class SaveHandler:
    """
    Binary handler for RVFOREST.DAT (Animal Crossing: City Folk / Wii).

    All offsets and multi-byte values follow PowerPC big-endian convention.
    Data is held in a mutable bytearray for in-place editing.
    """

    def __init__(self) -> None:
        self.data: bytearray = bytearray()
        self._filepath: Optional[Path] = None
        self.modified: bool = False

    # -- properties ---------------------------------------------------------

    @property
    def filepath(self) -> Optional[Path]:
        """Path to the currently-loaded save file (None if nothing loaded)."""
        return self._filepath

    # -- file I/O -----------------------------------------------------------

    def open(self, path: str | Path) -> bool:
        """
        Read an entire RVFOREST.DAT into ``self.data``.

        Returns ``True`` on success, ``False`` on failure (wrong size).
        Raises ``FileNotFoundError`` / ``PermissionError`` on OS errors.
        """
        path = Path(path)
        raw = path.read_bytes()
        if len(raw) != SAVE_SIZE:
            return False
        self.data = bytearray(raw)
        self._filepath = path
        self.modified = False
        return True

    def save(self, path: str | Path | None = None) -> None:
        """
        Update all CRCs, then write the save to *path*.

        If *path* is ``None``, overwrite the original file.
        """
        if len(self.data) != SAVE_SIZE:
            raise RuntimeError(
                f"Data size mismatch: expected {SAVE_SIZE} bytes, "
                f"got {len(self.data)}. Refusing to write corrupt save."
            )
        self.update_all_crc()
        target = Path(path) if path is not None else self._filepath
        if target is None:
            raise RuntimeError("No file path set; use save_as() or open() first")
        target.write_bytes(bytes(self.data))
        self._filepath = target
        self.modified = False

    def save_as(self, path: str | Path) -> None:
        """Update all CRCs and write to a new path."""
        self.save(path)

    # -- byte-level helpers (big-endian) ------------------------------------

    def _check_offset(self, offset: int, size: int) -> None:
        """Raise if offset+size would be out of bounds."""
        if not self.data:
            raise RuntimeError("No save file loaded")
        if offset < 0 or offset + size > len(self.data):
            raise ValueError(
                f"Offset 0x{offset:X} + {size} bytes exceeds save size "
                f"(0x{len(self.data):X})"
            )

    def read_u8(self, offset: int) -> int:
        self._check_offset(offset, 1)
        return self.data[offset]

    def read_u16(self, offset: int) -> int:
        self._check_offset(offset, 2)
        return struct.unpack_from(">H", self.data, offset)[0]

    def read_u32(self, offset: int) -> int:
        self._check_offset(offset, 4)
        return struct.unpack_from(">I", self.data, offset)[0]

    def write_u8(self, offset: int, val: int) -> None:
        self._check_offset(offset, 1)
        self.data[offset] = val & 0xFF
        self.modified = True

    def write_u16(self, offset: int, val: int) -> None:
        self._check_offset(offset, 2)
        struct.pack_into(">H", self.data, offset, val & 0xFFFF)
        self.modified = True

    def write_u32(self, offset: int, val: int) -> None:
        self._check_offset(offset, 4)
        struct.pack_into(">I", self.data, offset, val & 0xFFFFFFFF)
        self.modified = True

    # -- string helpers (big-endian UTF-16) ---------------------------------

    def read_string(self, offset: int, max_chars: int = 8) -> str:
        """
        Read a big-endian UTF-16 string starting at *offset*.

        Each character is stored as a 2-byte big-endian value.  Reading stops
        at a null character (0x0000) or after *max_chars* characters.
        """
        chars: list[str] = []
        for i in range(max_chars):
            code = struct.unpack_from(">H", self.data, offset + i * 2)[0]
            if code == 0:
                break
            chars.append(chr(code))
        return "".join(chars)

    def write_string(self, offset: int, text: str, max_chars: int = 8) -> None:
        """
        Write a big-endian UTF-16 string at *offset*, padded with null chars.
        """
        for i in range(max_chars):
            code = ord(text[i]) if i < len(text) else 0
            struct.pack_into(">H", self.data, offset + i * 2, code)
        self.modified = True

    # ======================================================================
    # CRC32
    # ======================================================================

    def _compute_crc(self, start: int, end: int, seed: int) -> int:
        """Return the CRC32 of data[start:end] with *seed*."""
        return _crc32_stream(self.data, start, end, seed)

    def _write_crc(self, crc_offset: int, crc_value: int) -> None:
        """Write *crc_value* at *crc_offset* as big-endian u32.

        The original Delphi code does Reverse(crc) then WriteBuffer on LE x86,
        which produces the CRC in big-endian byte order in the file.  Since we
        use struct '>I' throughout, we write the raw CRC value directly.
        """
        struct.pack_into(">I", self.data, crc_offset, crc_value & 0xFFFFFFFF)
        self.modified = True

    def _read_stored_crc(self, crc_offset: int) -> int:
        """Read the stored CRC at *crc_offset* as big-endian u32."""
        return struct.unpack_from(">I", self.data, crc_offset)[0]

    # -- CRC-A (per player) ------------------------------------------------

    def update_crc_a(self, player: int, write: bool = True) -> int:
        """
        Compute CRC-A for *player* (0-3).

        Checksum stored at ``0x1140 + player_offset``,
        covers ``0x1144 + po`` to ``0x86E0 + po``.
        """
        po = self.player_offset(player)
        crc_off = 0x1140 + po
        start = 0x1144 + po
        end = 0x86E0 + po
        crc = self._compute_crc(start, end, CRC_SEED_DEFAULT)
        if write:
            self._write_crc(crc_off, crc)
        return crc

    # -- CRC-B (town) ------------------------------------------------------

    def update_crc_b(self, write: bool = True) -> int:
        """
        Compute CRC-B (town data).

        Checksum at 0x5EC60, covers 0x5EC64 to 0x735E0.
        """
        crc = self._compute_crc(0x5EC64, 0x735E0, CRC_SEED_DEFAULT)
        if write:
            self._write_crc(0x5EC60, crc)
        return crc

    # -- CRC-C (buildings) -------------------------------------------------

    def update_crc_c(self, write: bool = True) -> int:
        """
        Compute CRC-C (buildings).

        Checksum at 0x5EB04, covers 0x5EB08 to 0x5EC5A.
        Seed is 0x12141018.
        """
        crc = self._compute_crc(0x5EB08, 0x5EC5A, CRC_SEED_BUILDINGS)
        if write:
            self._write_crc(0x5EB04, crc)
        return crc

    # -- CRC-D (extended) --------------------------------------------------

    def update_crc_d(self, write: bool = True) -> int:
        """
        Compute CRC-D (extended region).

        Checksum at 0x73600, covers 0x73604 to 0x20F320.
        """
        crc = self._compute_crc(0x73604, 0x20F320, CRC_SEED_DEFAULT)
        if write:
            self._write_crc(0x73600, crc)
        return crc

    # -- aggregate CRC helpers ----------------------------------------------

    def update_all_crc(self) -> None:
        """Recompute and write all CRC regions (4 players + town/buildings/ext)."""
        for p in range(PLAYER_COUNT):
            self.update_crc_a(p, write=True)
        self.update_crc_b(write=True)
        self.update_crc_c(write=True)
        self.update_crc_d(write=True)

    def check_all_crc(self) -> list[str]:
        """
        Verify every CRC region.

        Returns a list of human-readable mismatch descriptions.
        An empty list means all CRCs are valid.
        """
        mismatches: list[str] = []
        for p in range(PLAYER_COUNT):
            po = self.player_offset(p)
            stored = self._read_stored_crc(0x1140 + po)
            computed = self.update_crc_a(p, write=False)
            if stored != computed:
                mismatches.append(
                    f"CRC-A player {p}: stored=0x{stored:08X} computed=0x{computed:08X}"
                )
        # CRC-B
        stored = self._read_stored_crc(0x5EC60)
        computed = self.update_crc_b(write=False)
        if stored != computed:
            mismatches.append(
                f"CRC-B (town): stored=0x{stored:08X} computed=0x{computed:08X}"
            )
        # CRC-C
        stored = self._read_stored_crc(0x5EB04)
        computed = self.update_crc_c(write=False)
        if stored != computed:
            mismatches.append(
                f"CRC-C (buildings): stored=0x{stored:08X} computed=0x{computed:08X}"
            )
        # CRC-D
        stored = self._read_stored_crc(0x73600)
        computed = self.update_crc_d(write=False)
        if stored != computed:
            mismatches.append(
                f"CRC-D (extended): stored=0x{stored:08X} computed=0x{computed:08X}"
            )
        return mismatches

    # ======================================================================
    # Player data helpers
    # ======================================================================

    @staticmethod
    def player_offset(p: int) -> int:
        """Return the byte offset for player *p* (0-3)."""
        if not (0 <= p < PLAYER_COUNT):
            raise ValueError(f"Player index must be 0-3, got {p}")
        return PLAYER_STRIDE * p

    def player_exists(self, p: int) -> bool:
        """
        Return ``True`` if player slot *p* contains valid data.

        An empty/uninitialised slot produces a known CRC sentinel.
        """
        crc = self.update_crc_a(p, write=False)
        return crc != EMPTY_PLAYER_CRC

    # -- wallet / bank / points ---------------------------------------------

    def get_wallet(self, p: int) -> int:
        return self.read_u32(0x1154 + self.player_offset(p))

    def set_wallet(self, p: int, val: int) -> None:
        self.write_u32(0x1154 + self.player_offset(p), min(val, 99999))

    def get_bank(self, p: int) -> int:
        return self.read_u32(0x115C + self.player_offset(p))

    def set_bank(self, p: int, val: int) -> None:
        self.write_u32(0x115C + self.player_offset(p), min(val, 999999999))

    def get_points(self, p: int) -> int:
        return self.read_u16(0x7FC0 + self.player_offset(p))

    def set_points(self, p: int, val: int) -> None:
        self.write_u16(0x7FC0 + self.player_offset(p), min(val, 65535))

    # -- name / town info ---------------------------------------------------

    def get_player_name(self, p: int) -> str:
        return self.read_string(0x7EFA + self.player_offset(p), 8)

    def get_town_name(self, p: int) -> str:
        return self.read_string(0x7EE4 + self.player_offset(p), 8)

    def get_town_id(self, p: int) -> int:
        return self.read_u16(0x7EE2 + self.player_offset(p))

    def get_special_byte(self, p: int) -> int:
        return self.read_u8(0x7EF6 + self.player_offset(p))

    # -- donation -----------------------------------------------------------

    def get_donation(self) -> int:
        return self.read_u32(0x5EC7C)

    def set_donation(self, val: int) -> None:
        self.write_u32(0x5EC7C, val)

    # ======================================================================
    # Appearance helpers
    # ======================================================================

    def get_face(self, p: int) -> int:
        return self.read_u8(0x840A + self.player_offset(p)) & 0x0F

    def set_face(self, p: int, val: int) -> None:
        off = 0x840A + self.player_offset(p)
        current = self.read_u8(off)
        self.write_u8(off, (current & 0xF0) | (val & 0x0F))

    def get_hair(self, p: int) -> int:
        return self.read_u8(0x840B + self.player_offset(p))

    def set_hair(self, p: int, val: int) -> None:
        self.write_u8(0x840B + self.player_offset(p), min(val, 0x19))

    def get_hair_color(self, p: int) -> int:
        return self.read_u8(0x840C + self.player_offset(p))

    def set_hair_color(self, p: int, val: int) -> None:
        self.write_u8(0x840C + self.player_offset(p), min(val, 7))

    def get_tan(self, p: int) -> int:
        return self.read_u8(0x8416 + self.player_offset(p))

    def set_tan(self, p: int, val: int) -> None:
        self.write_u8(0x8416 + self.player_offset(p), val & 0xFF)

    def get_hat(self, p: int) -> int:
        return self.read_u8(0x8418 + self.player_offset(p)) >> 1

    def set_hat(self, p: int, val: int) -> None:
        self.write_u8(0x8418 + self.player_offset(p), (min(val, 7) << 1) & 0xFF)

    # ======================================================================
    # Emotions
    # ======================================================================

    def get_emotions(self, p: int) -> list[int]:
        """
        Read 4 emotion bytes.

        Stored value 0xFF means "none" -> returned as 0.
        Otherwise returned as stored_value + 1.
        """
        base = 0x8634 + self.player_offset(p)
        result: list[int] = []
        for i in range(4):
            b = self.read_u8(base + i)
            result.append(0 if b == 0xFF else b + 1)
        return result

    def set_emotions(self, p: int, emotions: list[int]) -> None:
        """
        Write 4 emotion bytes.

        Input value 0 -> stored as 0xFF (none).
        Otherwise stored as input_value - 1.
        """
        base = 0x8634 + self.player_offset(p)
        for i in range(4):
            val = emotions[i] if i < len(emotions) else 0
            self.write_u8(base + i, 0xFF if val == 0 else (val - 1) & 0xFF)

    # ======================================================================
    # Town helpers
    # ======================================================================

    def get_nook_style(self) -> int:
        return self.read_u8(0x630C3)

    def set_nook_style(self, val: int) -> None:
        self.write_u8(0x630C3, val & 0xFF)
        self.write_u8(0x630C3 + 4, val & 0xFF)

    def get_grass_style(self) -> int:
        return self.read_u8(0x6D5B7)

    def set_grass_style(self, val: int) -> None:
        self.write_u8(0x6D5B7, min(val, 2))

    def get_gate_style(self) -> int:
        return self.read_u8(0x5EAE0)

    def set_gate_style(self, val: int) -> None:
        self.write_u8(0x5EAE0, min(val, 2))

    def clear_sold_out_flags(self) -> None:
        """
        Clear the 36 sold-out flag bytes at 0x630CA.

        Each flag is separated by a 4-byte stride (write 0 at byte 0 of each
        4-byte entry).
        """
        base = 0x630CA
        for i in range(36):
            self.write_u8(base + i * 4, 0)

    # ======================================================================
    # Item grid helpers
    # ======================================================================

    def get_town_items(self) -> list[int]:
        """Read 6400 u16 town item codes (80x80 grid) starting at 0x68476."""
        base = 0x68476
        return [self.read_u16(base + i * 2) for i in range(6400)]

    def set_town_item(self, index: int, value: int) -> None:
        """Write a single u16 town item at *index* (0-6399)."""
        if not (0 <= index < 6400):
            raise ValueError(f"Town item index must be 0-6399, got {index}")
        self.write_u16(0x68476 + index * 2, value)

    def get_buried_items(self) -> list[int]:
        """Read 400 u16 buried-item codes starting at 0x6B676."""
        base = 0x6B676
        return [self.read_u16(base + i * 2) for i in range(400)]

    def get_acre_layout(self) -> list[int]:
        """Read the 7x7 (49) u16 acre layout starting at 0x68414."""
        base = 0x68414
        return [self.read_u16(base + i * 2) for i in range(49)]

    def get_grass_data(self) -> list[int]:
        """Read 6400 bytes of grass-wear data starting at 0x6BCB6."""
        base = 0x6BCB6
        return [self.read_u8(base + i) for i in range(6400)]

    def set_grass_data(self, data: list[int]) -> None:
        """Write 6400 bytes of grass-wear data."""
        base = 0x6BCB6
        for i in range(min(len(data), 6400)):
            self.write_u8(base + i, data[i])

    def set_acre_layout(self, acres: list[int]) -> None:
        """Write 49 u16 acre codes."""
        base = 0x68414
        for i in range(min(len(acres), 49)):
            self.write_u16(base + i * 2, acres[i])

    # ======================================================================
    # Building helpers
    # ======================================================================

    # Building coordinate layout in the save file:
    #   $5EB0A: Buildings 0-32 (33 entries, 2 bytes each: X, Y)
    #   $5EB8A: Building 34 (Bus Stop, 2 bytes)
    #   $5EB90: Building 33 (Pavé's Sign, 2 bytes)
    #   $5EB92: Signs 0-99 (100 entries, 2 bytes each)
    # Coordinates are stored with a +0x10 offset from grid position.

    BUILDING_NAMES = {
        0: "Player House A", 1: "Player House B",
        2: "Player House C", 3: "Player House D",
        8: "Neighbor House 1", 9: "Neighbor House 2",
        10: "Neighbor House 3", 11: "Neighbor House 4",
        12: "Neighbor House 5", 13: "Neighbor House 6",
        14: "Neighbor House 7", 15: "Neighbor House 8",
        16: "Neighbor House 9", 17: "Neighbor House 10",
        18: "Town Hall", 19: "Gate",
        20: "Nook's Store", 21: "Able Sister's Store",
        22: "Museum", 23: "Bulletin Board",
        24: "New Year's Sign", 25: "Chip's Stand",
        26: "Nat's Stand", 27: "Lighthouse",
        28: "Windmill", 29: "Fountain",
        30: "Harvest Festival Table 1", 31: "Harvest Festival Table 2",
        32: "Gulliver's UFO", 33: "Pavé's Sign",
        34: "Bus Stop", 35: "Sign",
    }

    BUILDING_COUNT = 35
    SIGN_COUNT = 100

    def get_buildings(self) -> list[tuple[int, int]]:
        """
        Read all 35 building coordinates as ``(x, y)`` tuples.

        Buildings 0-32 are at $5EB0A, building 33 (Pavé) at $5EB90,
        building 34 (Bus Stop) at $5EB8A.  Coordinates of (0, 0) mean
        the building does not exist.
        """
        buildings: list[tuple[int, int]] = []
        # Buildings 0-32 at $5EB0A
        base = 0x5EB0A
        for i in range(33):
            x = self.read_u8(base + i * 2)
            y = self.read_u8(base + i * 2 + 1)
            buildings.append((x, y))
        # Building 33 (Pavé) at $5EB90
        x = self.read_u8(0x5EB90)
        y = self.read_u8(0x5EB91)
        buildings.append((x, y))
        # Building 34 (Bus Stop) at $5EB8A
        x = self.read_u8(0x5EB8A)
        y = self.read_u8(0x5EB8B)
        buildings.append((x, y))
        return buildings

    def set_building(self, building_id: int, x: int, y: int) -> None:
        """Set coordinates for building *building_id* (0-34)."""
        if not (0 <= building_id < self.BUILDING_COUNT):
            raise ValueError(f"Building ID must be 0-34, got {building_id}")
        if building_id < 33:
            base = 0x5EB0A + building_id * 2
        elif building_id == 33:
            base = 0x5EB90
        else:  # 34
            base = 0x5EB8A
        self.write_u8(base, x & 0xFF)
        self.write_u8(base + 1, y & 0xFF)

    def get_signs(self) -> list[tuple[int, int]]:
        """Read all 100 sign coordinates as ``(x, y)`` tuples."""
        base = 0x5EB92
        signs: list[tuple[int, int]] = []
        for i in range(self.SIGN_COUNT):
            x = self.read_u8(base + i * 2)
            y = self.read_u8(base + i * 2 + 1)
            signs.append((x, y))
        return signs

    def set_sign(self, sign_id: int, x: int, y: int) -> None:
        """Set coordinates for sign *sign_id* (0-99)."""
        if not (0 <= sign_id < self.SIGN_COUNT):
            raise ValueError(f"Sign ID must be 0-99, got {sign_id}")
        base = 0x5EB92 + sign_id * 2
        self.write_u8(base, x & 0xFF)
        self.write_u8(base + 1, y & 0xFF)

    def building_exists(self, building_id: int) -> bool:
        """Return True if building has non-zero coordinates."""
        buildings = self.get_buildings()
        if not (0 <= building_id < len(buildings)):
            return False
        x, y = buildings[building_id]
        return x != 0 or y != 0

    def sign_exists(self, sign_id: int) -> bool:
        """Return True if sign has non-zero coordinates."""
        signs = self.get_signs()
        if not (0 <= sign_id < len(signs)):
            return False
        x, y = signs[sign_id]
        return x != 0 or y != 0

    def get_building_name(self, building_id: int) -> str:
        """Return the display name for a building ID."""
        return self.BUILDING_NAMES.get(building_id, f"Unknown ({building_id})")

    # ======================================================================
    # Buried item helpers
    # ======================================================================

    def get_buried_bitmap(self) -> list[int]:
        """
        Read 400 u16 buried-item bitmask words starting at 0x6B676.

        Each word is a 16-bit bitmask covering one row of 16 tiles within
        an acre.  25 acres × 16 rows = 400 words total.
        Bit N set means column N in that row has a buried item.
        """
        base = 0x6B676
        return [self.read_u16(base + i * 2) for i in range(400)]

    def set_buried_bitmap(self, bitmap: list[int]) -> None:
        """Write 400 u16 buried-item bitmask words."""
        base = 0x6B676
        for i in range(min(len(bitmap), 400)):
            self.write_u16(base + i * 2, bitmap[i])

    def is_buried(self, col: int, row: int, acre: int) -> bool:
        """Check if tile (col, row) in acre has a buried item."""
        bitmap = self.get_buried_bitmap()
        word_idx = (row % 16) + acre * 16
        if not (0 <= word_idx < 400):
            return False
        return bool(bitmap[word_idx] & (1 << (col % 16)))

    def toggle_buried(self, col: int, row: int, acre: int) -> None:
        """Toggle the buried flag for tile (col, row) in acre."""
        base = 0x6B676
        word_idx = (row % 16) + acre * 16
        if not (0 <= word_idx < 400):
            raise ValueError(f"Invalid buried bitmap index for col={col}, row={row}, acre={acre}")
        current = self.read_u16(base + word_idx * 2)
        self.write_u16(base + word_idx * 2, current ^ (1 << (col % 16)))

    # ======================================================================
    # Inventory helpers
    # ======================================================================

    def get_pockets(self, p: int) -> list[int]:
        """Read 15 u16 pocket-item codes (3 rows x 5 cols)."""
        base = 0x7F42 + self.player_offset(p)
        return [self.read_u16(base + i * 2) for i in range(15)]

    def set_pockets(self, p: int, items: list[int]) -> None:
        """Write 15 u16 pocket-item codes."""
        base = 0x7F42 + self.player_offset(p)
        for i in range(15):
            val = items[i] if i < len(items) else 0xFFF1
            self.write_u16(base + i * 2, val)

    def get_drawers(self, p: int) -> list[int]:
        """Read 160 u16 drawer-item codes (32 rows x 5 cols)."""
        base = 0x1F3038 + p * 0x140
        return [self.read_u16(base + i * 2) for i in range(160)]

    def set_drawers(self, p: int, items: list[int]) -> None:
        """Write 160 u16 drawer-item codes."""
        base = 0x1F3038 + p * 0x140
        for i in range(160):
            val = items[i] if i < len(items) else 0xFFF1
            self.write_u16(base + i * 2, val)

    def get_lost_found(self) -> list[int]:
        """Read 12 u16 lost-and-found items (2x6) at 0x72DDA."""
        base = 0x72DDA
        return [self.read_u16(base + i * 2) for i in range(12)]

    def set_lost_found(self, items: list[int]) -> None:
        """Write 12 u16 lost-and-found items."""
        base = 0x72DDA
        for i in range(12):
            val = items[i] if i < len(items) else 0xFFF1
            self.write_u16(base + i * 2, val)

    def get_recycle_bin(self) -> list[int]:
        """Read 12 u16 recycle-bin items (2x6) at 0x72DF2."""
        base = 0x72DF2
        return [self.read_u16(base + i * 2) for i in range(12)]

    def set_recycle_bin(self, items: list[int]) -> None:
        """Write 12 u16 recycle-bin items."""
        base = 0x72DF2
        for i in range(12):
            val = items[i] if i < len(items) else 0xFFF1
            self.write_u16(base + i * 2, val)

    def get_nook_items(self) -> list[int]:
        """
        Read 36 u16 Nook shop items at 0x630C8.

        Items are stored with a 4-byte stride (2 bytes item + 2 bytes padding).
        """
        base = 0x630C8
        return [self.read_u16(base + i * 4) for i in range(36)]

    def set_nook_items(self, items: list[int]) -> None:
        """Write 36 u16 Nook shop items with 4-byte stride."""
        base = 0x630C8
        for i in range(36):
            val = items[i] if i < len(items) else 0xFFF1
            self.write_u16(base + i * 4, val)

    # ======================================================================
    # House helpers
    # ======================================================================

    _HOUSE_BASE = 0x6DE6C
    _ROOM_STRIDE = 0x15C0
    _FLOOR_STRIDE = 0x458

    def get_house_room(self, room_index: int, floor: int) -> list[int]:
        """
        Read a 16x16 (256) u16 room grid.

        *room_index*: 0-3 (one per player).
        *floor*: 0-5 (three floor levels x 2 sides).
        """
        if not (0 <= room_index < PLAYER_COUNT):
            raise ValueError(f"room_index must be 0-3, got {room_index}")
        if not (0 <= floor < 6):
            raise ValueError(f"floor must be 0-5, got {floor}")
        base = (
            self._HOUSE_BASE
            + room_index * self._ROOM_STRIDE
            + floor * self._FLOOR_STRIDE
        )
        return [self.read_u16(base + i * 2) for i in range(256)]

    def get_house_items(self, room_index: int) -> list[list[int]]:
        """
        Return all 6 grids for *room_index* (3 floors x 2 sides).

        Returns a list of 6 lists, each containing 256 u16 values:
            [floor0_left, floor0_right, floor1_left, floor1_right,
             floor2_left, floor2_right]
        """
        if not (0 <= room_index < PLAYER_COUNT):
            raise ValueError(f"room_index must be 0-3, got {room_index}")
        grids: list[list[int]] = []
        for floor in range(3):
            for side in range(2):
                offset = (
                    self._HOUSE_BASE
                    + room_index * self._ROOM_STRIDE
                    + floor * self._FLOOR_STRIDE
                    + side * 256 * 2
                )
                grid = [self.read_u16(offset + i * 2) for i in range(256)]
                grids.append(grid)
        return grids

    # ======================================================================
    # Catalog helpers
    # ======================================================================

    @staticmethod
    def _catalog_bit_info(item_code: int) -> tuple[int, int]:
        """
        Return ``(byte_offset_from_catalog_base, bit_mask)`` for *item_code*.

        Bit calculation from the original Delphi source:
            index  = (item_code - 0x9000) / 4
            byte   = index >> 3
            bit    = 1 << ((index & 0xF) % 8)
        """
        index = (item_code - 0x9000) // 4
        byte_off = index >> 3
        bit_mask = 1 << ((index & 0xF) % 8)
        return byte_off, bit_mask

    def catalog_total(self, p: int, range_start: int, range_end: int) -> int:
        """Count how many catalog bits are set in the given item-code range."""
        catalog_base = 0x841A + self.player_offset(p)
        count = 0
        code = range_start
        while code <= range_end:
            byte_off, bit_mask = self._catalog_bit_info(code)
            if self.read_u8(catalog_base + byte_off) & bit_mask:
                count += 1
            code += 4  # item codes increment by 4
        return count

    def fill_catalog(self, p: int, range_start: int, range_end: int) -> None:
        """Set all catalog bits in the given item-code range."""
        catalog_base = 0x841A + self.player_offset(p)
        code = range_start
        while code <= range_end:
            byte_off, bit_mask = self._catalog_bit_info(code)
            off = catalog_base + byte_off
            self.write_u8(off, self.read_u8(off) | bit_mask)
            code += 4

    # ======================================================================
    # DLC reading
    # ======================================================================

    def read_dlc(self) -> list[dict]:
        """
        Scan the DLC region and return a list of valid DLC entries.

        Each entry is a dict with keys:
            ``"slot"``, ``"item_code"``, ``"names"`` (list of 9 strings).
        """
        base = 0x20F324
        slot_stride = 0x2000
        results: list[dict] = []

        for slot in range(256):
            off = base + slot * slot_stride
            # Check for "BITM" magic (0x4249544D)
            if off + 0x22 * 9 + 0x12 > len(self.data):
                break
            magic = self.read_u32(off)
            if magic != 0x4249544D:
                continue
            # Verify marker word at +0x10
            marker = self.read_u16(off + 0x10)
            if marker != 0x1701:
                continue
            # Item code at +0x08 (after 4-byte magic + 4-byte price)
            raw_code = self.read_u16(off + 0x08)
            item_code = raw_code * 4 + 0x9000
            # 9 language name strings, each 0x22 bytes (17 WideChars)
            names: list[str] = []
            name_base = off + 0x12
            for lang in range(9):
                name = self.read_string(name_base + lang * 0x22, 17)
                names.append(name)
            results.append({
                "slot": slot,
                "item_code": item_code,
                "names": names,
            })

        return results

    # ======================================================================
    # Name update helpers
    # ======================================================================

    def update_town_name(self, p: int, new_name: str) -> int:
        """
        Search the save for all occurrences of player *p*'s
        town_id + town_name + special_byte pattern and replace the
        town_name portion with *new_name*.

        Returns the number of replacements made.
        """
        po = self.player_offset(p)
        town_id = self.read_u16(0x7EE2 + po)
        old_name = self.get_town_name(p)
        special = self.get_special_byte(p)

        # Build the search pattern: town_id (2 bytes BE) + town_name (16 bytes BE UTF-16) + special (1 byte)
        pattern = bytearray()
        pattern += struct.pack(">H", town_id)
        for ch in old_name.ljust(8, "\x00")[:8]:
            pattern += struct.pack(">H", ord(ch))
        pattern.append(special)

        # Build the replacement name bytes (same length as old name region)
        new_name_bytes = bytearray()
        for i in range(8):
            code = ord(new_name[i]) if i < len(new_name) else 0
            new_name_bytes += struct.pack(">H", code)

        # Name starts at offset 2 within the pattern (after town_id)
        name_offset_in_pattern = 2
        name_length = 16  # 8 chars x 2 bytes

        count = 0
        search_start = 0x1140
        search_end = 0x20F320

        pos = search_start
        while pos < search_end:
            idx = self.data.find(pattern, pos, search_end)
            if idx == -1:
                break
            # Replace the town_name portion
            self.data[idx + name_offset_in_pattern:idx + name_offset_in_pattern + name_length] = new_name_bytes
            self.modified = True
            count += 1
            pos = idx + len(pattern)

        return count

    def update_player_name(self, p: int, new_name: str) -> int:
        """
        Search the save for all occurrences of player *p*'s
        town_id + town_name + special_byte + player_name pattern and replace
        the player_name portion with *new_name*.

        Returns the number of replacements made.
        """
        po = self.player_offset(p)
        town_id = self.read_u16(0x7EE2 + po)
        town_name = self.get_town_name(p)
        special = self.get_special_byte(p)
        old_player_name = self.get_player_name(p)

        # Build the search pattern:
        # town_id (2B) + town_name (16B) + special (1B) + player_name (16B)
        pattern = bytearray()
        pattern += struct.pack(">H", town_id)
        for ch in town_name.ljust(8, "\x00")[:8]:
            pattern += struct.pack(">H", ord(ch))
        pattern.append(special)
        for ch in old_player_name.ljust(8, "\x00")[:8]:
            pattern += struct.pack(">H", ord(ch))

        # Build replacement player-name bytes
        new_name_bytes = bytearray()
        for i in range(8):
            code = ord(new_name[i]) if i < len(new_name) else 0
            new_name_bytes += struct.pack(">H", code)

        # Player name starts after town_id(2) + town_name(16) + special(1) = offset 19
        name_offset_in_pattern = 19
        name_length = 16

        count = 0
        search_start = 0x1140
        search_end = 0x20F320

        pos = search_start
        while pos < search_end:
            idx = self.data.find(pattern, pos, search_end)
            if idx == -1:
                break
            self.data[idx + name_offset_in_pattern:idx + name_offset_in_pattern + name_length] = new_name_bytes
            self.modified = True
            count += 1
            pos = idx + len(pattern)

        return count

    # ======================================================================
    # Villager / NPC helpers  (ACSE CfVillagerOffsets layout)
    # ======================================================================

    # Full villager structs: 10 slots × 0x3040 bytes starting at 0x21B20.
    # Byte at base+0 is non-zero when the slot is occupied.
    VILLAGER_BASE   = 0x21B20
    VILLAGER_STRIDE = 0x3040   # 12,352 bytes per villager
    NPC_SLOT_COUNT  = 10

    # Offsets within each 0x3040 villager struct
    _VOFF_EXISTS      = 0x0000   # u8: non-zero → occupied
    _VOFF_NPC_ID      = 0x1824   # u16 BE: NPC index (0-453)
    _VOFF_SHIRT       = 0x1826   # u16 BE: item ID
    _VOFF_CARPET      = 0x1828   # u16 BE: item ID
    _VOFF_WALLPAPER   = 0x182A   # u16 BE: item ID
    _VOFF_UMBRELLA    = 0x182C   # u16 BE: item ID
    _VOFF_FURNITURE   = 0x182E   # 10 × u16 BE
    _VOFF_KK_SONG     = 0x1842   # u16 BE
    _VOFF_CATCHPHRASE = 0x18EC   # UTF-16 BE string (22 bytes)
    _VOFF_NPC_ID2     = 0x2308   # u16 BE: duplicate NPC index
    _VOFF_PERSONALITY = 0x230A   # u8: 0-5

    def _villager_offset(self, slot: int) -> int:
        """Return the absolute offset of a villager slot's struct."""
        if not 0 <= slot < self.NPC_SLOT_COUNT:
            raise ValueError(f"Villager slot must be 0-9, got {slot}")
        return self.VILLAGER_BASE + slot * self.VILLAGER_STRIDE

    def is_slot_occupied(self, slot: int) -> bool:
        """Check whether a villager slot contains a resident."""
        return self.read_u8(self._villager_offset(slot) + self._VOFF_EXISTS) != 0

    def get_resident_ids(self) -> list[int]:
        """Read the 10 resident NPC IDs from the villager structs.

        Returns a list of 10 u16 values.  0xFFFF means an empty slot.
        Slots where the existence byte is zero return 0xFFFF.
        """
        result = []
        for i in range(self.NPC_SLOT_COUNT):
            base = self._villager_offset(i)
            if self.read_u8(base + self._VOFF_EXISTS) == 0:
                result.append(0xFFFF)
            else:
                result.append(self.read_u16(base + self._VOFF_NPC_ID))
        return result

    def set_resident_id(self, slot: int, npc_id: int) -> None:
        """Write a single NPC ID into a resident slot (0-9).

        Writing 0xFFFF marks the slot as empty (clears the existence byte).
        Any other value sets the existence byte and writes the ID to both
        NPC ID fields in the struct.
        """
        if not 0 <= slot < self.NPC_SLOT_COUNT:
            raise ValueError(f"Resident slot must be 0-9, got {slot}")
        if not 0 <= npc_id <= 0xFFFF:
            raise ValueError(f"NPC ID must be 0-65535, got {npc_id}")

        base = self._villager_offset(slot)
        if npc_id == 0xFFFF:
            self.write_u8(base + self._VOFF_EXISTS, 0)
            self.write_u16(base + self._VOFF_NPC_ID, 0)
            self.write_u16(base + self._VOFF_NPC_ID2, 0)
        else:
            self.write_u8(base + self._VOFF_EXISTS, 0x10)
            self.write_u16(base + self._VOFF_NPC_ID, npc_id)
            self.write_u16(base + self._VOFF_NPC_ID2, npc_id)

    def set_resident_ids(self, ids: list[int]) -> None:
        """Write all 10 resident NPC IDs at once."""
        if len(ids) != self.NPC_SLOT_COUNT:
            raise ValueError(
                f"Expected {self.NPC_SLOT_COUNT} IDs, got {len(ids)}"
            )
        for i, npc_id in enumerate(ids):
            self.set_resident_id(i, npc_id)

    def get_villager_personality(self, slot: int) -> int:
        """Read the in-save personality byte for a villager slot (0-5)."""
        return self.read_u8(self._villager_offset(slot) + self._VOFF_PERSONALITY)

    def get_villager_catchphrase(self, slot: int) -> str:
        """Read the in-save catchphrase for a villager slot."""
        off = self._villager_offset(slot) + self._VOFF_CATCHPHRASE
        self._check_offset(off, 22)
        raw = bytes(self.data[off:off + 22])
        try:
            return raw.decode("utf-16-be").rstrip("\x00")
        except UnicodeDecodeError:
            return ""

    def set_villager_catchphrase(self, slot: int, text: str) -> None:
        """Write a catchphrase into a villager slot (max 10 chars)."""
        off = self._villager_offset(slot) + self._VOFF_CATCHPHRASE
        self._check_offset(off, 22)
        encoded = text[:10].encode("utf-16-be")
        padded = encoded.ljust(22, b"\x00")[:22]
        self.data[off:off + 22] = padded
        self.modified = True

    def get_villager_shirt(self, slot: int) -> int:
        """Read the shirt item ID for a villager slot."""
        return self.read_u16(self._villager_offset(slot) + self._VOFF_SHIRT)

    # ======================================================================
    # Stalk Market (turnip prices)
    # ======================================================================

    _STALK_BASE = 0x63200

    def get_turnip_buy_price(self) -> int:
        """Joan's Sunday buy price (u32)."""
        return self.read_u32(self._STALK_BASE)

    def set_turnip_buy_price(self, price: int) -> None:
        if not 0 <= price <= 0xFFFFFFFF:
            raise ValueError(f"Price must be 0-4294967295, got {price}")
        self.write_u32(self._STALK_BASE, price)

    def get_turnip_sell_prices(self) -> list[int]:
        """Read 14 half-day sell prices: Sun AM/PM, Mon AM/PM, ..., Sat AM/PM."""
        return [self.read_u32(self._STALK_BASE + 4 + i * 4) for i in range(14)]

    def set_turnip_sell_prices(self, prices: list[int]) -> None:
        if len(prices) != 14:
            raise ValueError(f"Expected 14 prices, got {len(prices)}")
        for i, p in enumerate(prices):
            if not 0 <= p <= 0xFFFFFFFF:
                raise ValueError(f"Price[{i}] must be 0-4294967295, got {p}")
            self.write_u32(self._STALK_BASE + 4 + i * 4, p)

    def get_turnip_pattern(self) -> int:
        """Stalk market trend type (0-3)."""
        return self.read_u32(self._STALK_BASE + 0x3C)

    def set_turnip_pattern(self, pattern: int) -> None:
        if not 0 <= pattern <= 3:
            raise ValueError(f"Turnip pattern must be 0-3, got {pattern}")
        self.write_u32(self._STALK_BASE + 0x3C, pattern)

    # ======================================================================
    # Museum donations  (nibble-packed at 0x7352A)
    # ======================================================================

    _MUSEUM_BASE = 0x7352A
    _MUSEUM_FOSSIL_OFF  = 0    # 30 bytes → 60 slots
    _MUSEUM_FOSSIL_SIZE = 30
    _MUSEUM_FISH_OFF    = 30   # 32 bytes → 64 slots
    _MUSEUM_FISH_SIZE   = 32
    _MUSEUM_INSECT_OFF  = 62   # 32 bytes → 64 slots
    _MUSEUM_INSECT_SIZE = 32
    _MUSEUM_ART_OFF     = 94   # 14 bytes → 28 slots
    _MUSEUM_ART_SIZE    = 14

    def _read_museum_nibbles(self, rel_off: int, size: int) -> list[int]:
        """Read nibble-packed donation flags. Returns list of donor values (0=none, 1-4=player)."""
        base = self._MUSEUM_BASE + rel_off
        self._check_offset(base, size)
        result = []
        for i in range(size):
            b = self.data[base + i]
            result.append((b >> 4) & 0xF)  # high nibble
            result.append(b & 0xF)          # low nibble
        return result

    def _write_museum_nibbles(self, rel_off: int, size: int, values: list[int]) -> None:
        base = self._MUSEUM_BASE + rel_off
        self._check_offset(base, size)
        for i in range(size):
            hi = values[i * 2] & 0xF if i * 2 < len(values) else 0
            lo = values[i * 2 + 1] & 0xF if i * 2 + 1 < len(values) else 0
            self.data[base + i] = (hi << 4) | lo
        self.modified = True

    def get_museum_fossils(self) -> list[int]:
        return self._read_museum_nibbles(self._MUSEUM_FOSSIL_OFF, self._MUSEUM_FOSSIL_SIZE)

    def get_museum_fish(self) -> list[int]:
        return self._read_museum_nibbles(self._MUSEUM_FISH_OFF, self._MUSEUM_FISH_SIZE)

    def get_museum_insects(self) -> list[int]:
        return self._read_museum_nibbles(self._MUSEUM_INSECT_OFF, self._MUSEUM_INSECT_SIZE)

    def get_museum_art(self) -> list[int]:
        return self._read_museum_nibbles(self._MUSEUM_ART_OFF, self._MUSEUM_ART_SIZE)

    def fill_museum(self, player: int = 0) -> None:
        """Mark all museum items as donated by *player* (0-3)."""
        if not 0 <= player <= 3:
            raise ValueError(f"Player must be 0-3, got {player}")
        donor = player + 1
        for off, size in [
            (self._MUSEUM_FOSSIL_OFF, self._MUSEUM_FOSSIL_SIZE),
            (self._MUSEUM_FISH_OFF, self._MUSEUM_FISH_SIZE),
            (self._MUSEUM_INSECT_OFF, self._MUSEUM_INSECT_SIZE),
            (self._MUSEUM_ART_OFF, self._MUSEUM_ART_SIZE),
        ]:
            vals = [donor] * (size * 2)
            self._write_museum_nibbles(off, size, vals)

    def clear_museum(self) -> None:
        """Clear all museum donations."""
        total = self._MUSEUM_FOSSIL_SIZE + self._MUSEUM_FISH_SIZE + \
                self._MUSEUM_INSECT_SIZE + self._MUSEUM_ART_SIZE
        base = self._MUSEUM_BASE
        self._check_offset(base, total)
        for i in range(total):
            self.data[base + i] = 0
        self.modified = True

    # ======================================================================
    # Encyclopedia (per-player fish/bug caught bitmask)
    # ======================================================================

    def get_encyclopedia_insects(self, p: int) -> list[bool]:
        """Read 64 insect caught flags for player *p*."""
        base = 0x8465 + self.player_offset(p)
        bits = []
        for i in range(8):
            b = self.read_u8(base + i)
            for bit in range(8):
                bits.append(bool(b & (1 << bit)))
        return bits

    def get_encyclopedia_fish(self, p: int) -> list[bool]:
        """Read 68 fish caught flags for player *p*."""
        base = 0x8471 + self.player_offset(p)
        bits = []
        # First byte: only upper 4 bits
        b = self.read_u8(base)
        for bit in range(4, 8):
            bits.append(bool(b & (1 << bit)))
        # Bytes 1-7: full bytes
        for i in range(1, 8):
            b = self.read_u8(base + i)
            for bit in range(8):
                bits.append(bool(b & (1 << bit)))
        # Last byte: only lower 4 bits
        b = self.read_u8(base + 8)
        for bit in range(4):
            bits.append(bool(b & (1 << bit)))
        return bits

    def fill_encyclopedia(self, p: int) -> None:
        """Mark all fish and insects as caught for player *p*."""
        po = self.player_offset(p)
        # Insects: 8 full bytes at 0x8465
        for i in range(8):
            self.write_u8(0x8465 + po + i, 0xFF)
        # Fish: partial first byte, 7 full bytes, partial last byte
        self.write_u8(0x8471 + po, self.read_u8(0x8471 + po) | 0xF0)
        for i in range(1, 8):
            self.write_u8(0x8471 + po + i, 0xFF)
        self.write_u8(0x8479 + po, self.read_u8(0x8479 + po) | 0x0F)

    # ======================================================================
    # Pattern helpers (8 patterns per player)
    # ======================================================================

    _PATTERN_BASE   = 0x1160   # absolute offset for player 0, slot 0
    _PATTERN_SIZE   = 0x880    # 2,176 bytes per pattern
    _PATTERN_COUNT  = 8

    # Offsets within each pattern struct
    _PAT_PIXELS     = 0x000    # 0x200 bytes (32×32 @ 4bpp, C4 block order)
    _PAT_PALETTE    = 0x800    # 16 × 2 bytes (RGB565 BE)
    _PAT_TOWN_NAME  = 0x822    # 16 bytes UTF-16 BE (8 chars)
    _PAT_CREATOR    = 0x838    # 16 bytes UTF-16 BE (8 chars)
    _PAT_TITLE      = 0x84C    # 32 bytes UTF-16 BE (16 chars)
    _PAT_PALETTE_ID = 0x86F    # u8 palette group index

    def _pattern_offset(self, p: int, slot: int) -> int:
        """Absolute offset of pattern *slot* (0-7) for player *p* (0-3)."""
        if not 0 <= slot < self._PATTERN_COUNT:
            raise ValueError(f"Pattern slot must be 0-7, got {slot}")
        return self._PATTERN_BASE + self.player_offset(p) + slot * self._PATTERN_SIZE

    def get_pattern_title(self, p: int, slot: int) -> str:
        off = self._pattern_offset(p, slot) + self._PAT_TITLE
        self._check_offset(off, 32)
        raw = bytes(self.data[off:off + 32])
        try:
            return raw.decode("utf-16-be").rstrip("\x00")
        except UnicodeDecodeError:
            return ""

    def set_pattern_title(self, p: int, slot: int, title: str) -> None:
        off = self._pattern_offset(p, slot) + self._PAT_TITLE
        self._check_offset(off, 32)
        encoded = title[:16].encode("utf-16-be")
        padded = encoded.ljust(32, b"\x00")[:32]
        self.data[off:off + 32] = padded
        self.modified = True

    def get_pattern_creator(self, p: int, slot: int) -> str:
        off = self._pattern_offset(p, slot) + self._PAT_CREATOR
        self._check_offset(off, 16)
        raw = bytes(self.data[off:off + 16])
        try:
            return raw.decode("utf-16-be").rstrip("\x00")
        except UnicodeDecodeError:
            return ""

    def get_pattern_palette_rgb(self, p: int, slot: int) -> list[tuple[int, int, int]]:
        """Read the 16-color RGB565 palette, return as list of (R, G, B) tuples."""
        off = self._pattern_offset(p, slot) + self._PAT_PALETTE
        self._check_offset(off, 32)
        colors = []
        for i in range(16):
            val = struct.unpack_from(">H", self.data, off + i * 2)[0]
            r = ((val >> 11) & 0x1F) * 255 // 31
            g = ((val >> 5) & 0x3F) * 255 // 63
            b = (val & 0x1F) * 255 // 31
            colors.append((r, g, b))
        return colors

    def get_pattern_pixels(self, p: int, slot: int) -> list[list[int]]:
        """Read 32×32 pixel indices (0-15) in raster order from C4 block data."""
        off = self._pattern_offset(p, slot) + self._PAT_PIXELS
        self._check_offset(off, 0x200)
        raw = bytes(self.data[off:off + 0x200])
        # C4: 8×8 pixel blocks, each block is 32 bytes (8 rows × 4 bytes/row)
        # 32/8 = 4 blocks wide, 32/8 = 4 blocks tall = 16 blocks
        pixels = [[0] * 32 for _ in range(32)]
        src = 0
        for block_y in range(4):
            for block_x in range(4):
                for row in range(8):
                    for col_pair in range(4):
                        if src >= len(raw):
                            break
                        byte = raw[src]
                        src += 1
                        px = block_x * 8 + col_pair * 2
                        py = block_y * 8 + row
                        pixels[py][px] = (byte >> 4) & 0xF
                        pixels[py][px + 1] = byte & 0xF
        return pixels

    # ======================================================================
    # Mail / Letters (per-player, partially documented)
    # ======================================================================

    # 10 letter slots per player, 0x390 bytes each, starting at 0x56E0 within
    # the player block.  Struct layout (reverse-engineered):
    #   +0x008: attached item (u16, 0xFFF1 = none)
    #   +0x00A: town ID (u16)
    #   +0x00C: town name (16 bytes UTF-16 BE)
    #   +0x0F0: sender names (8× 16 bytes UTF-16 BE, multi-language)
    #   +0x18A: header text (64 bytes UTF-16 BE, e.g. "Dear <name>,")
    #   +0x1D0: body text (~192 bytes UTF-16 BE)
    _LETTER_BASE    = 0x56E0   # absolute offset for player 0, slot 0
    _LETTER_SIZE    = 0x390    # 912 bytes per letter
    _LETTER_COUNT   = 10
    _LETTER_ITEM_OFF   = 0x008
    _LETTER_HEADER_OFF = 0x18E
    _LETTER_BODY_OFF   = 0x1D0

    def _letter_offset(self, p: int, slot: int) -> int:
        if not 0 <= slot < self._LETTER_COUNT:
            raise ValueError(f"Letter slot must be 0-9, got {slot}")
        return self._LETTER_BASE + self.player_offset(p) + slot * self._LETTER_SIZE

    def get_letter_item(self, p: int, slot: int) -> int:
        """Read the attached item ID for a letter (0xFFF1 = none)."""
        return self.read_u16(self._letter_offset(p, slot) + self._LETTER_ITEM_OFF)

    def get_letter_header(self, p: int, slot: int) -> str:
        """Read the letter header/greeting (e.g. 'Dear <name>,')."""
        off = self._letter_offset(p, slot) + self._LETTER_HEADER_OFF
        self._check_offset(off, 64)
        raw = bytes(self.data[off:off + 64])
        try:
            text = raw.decode("utf-16-be").rstrip("\x00")
            # Strip leading non-ASCII prefix (stationery/type bytes)
            while text and ord(text[0]) > 127:
                text = text[1:]
            return text
        except UnicodeDecodeError:
            return ""

    def get_letter_body(self, p: int, slot: int) -> str:
        """Read the letter body text."""
        off = self._letter_offset(p, slot) + self._LETTER_BODY_OFF
        size = self._LETTER_SIZE - self._LETTER_BODY_OFF  # rest of struct
        self._check_offset(off, size)
        raw = bytes(self.data[off:off + size])
        try:
            text = raw.decode("utf-16-be").split("\x00")[0]
            return text.strip()
        except UnicodeDecodeError:
            return ""

    def get_letter_sender(self, p: int, slot: int) -> str:
        """Read the letter sender name (first language slot)."""
        off = self._letter_offset(p, slot) + 0x0F0
        self._check_offset(off, 16)
        raw = bytes(self.data[off:off + 16])
        try:
            return raw.decode("utf-16-be").rstrip("\x00")
        except UnicodeDecodeError:
            return ""

    def is_letter_empty(self, p: int, slot: int) -> bool:
        """Check if a letter slot has any content."""
        base = self._letter_offset(p, slot)
        self._check_offset(base, self._LETTER_SIZE)
        return all(b == 0 for b in self.data[base:base + self._LETTER_SIZE])

    def get_letter_count(self, p: int) -> int:
        """Count non-empty letter slots for player *p*."""
        count = 0
        for i in range(self._LETTER_COUNT):
            if not self.is_letter_empty(p, i):
                count += 1
        return count

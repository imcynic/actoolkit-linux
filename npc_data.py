"""
npc_data.py - NPC pack.bin parser for ACCF (City Folk) and ACCF Deluxe Edition.

Parses the NPC setup database from Npc/Normal/Setup/pack.bin.
Format: 32-byte header + N entries of 408 bytes each (big-endian).

Supports both vanilla (210 entries) and Deluxe (454 entries).
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PACK_HEADER_SIZE = 32
PACK_ENTRY_SIZE = 408  # 0x198

# Vanilla has 210 villagers, Deluxe extends to 454
VANILLA_NPC_COUNT = 210
DELUXE_NPC_START = 210

SPECIES_NAMES = {
    0: "Cat", 1: "Elephant", 2: "Sheep", 3: "Bear", 4: "Dog",
    5: "Squirrel", 6: "Rabbit", 7: "Duck", 8: "Hippo", 9: "Wolf",
    10: "Mouse", 11: "Pig", 12: "Chicken", 13: "Bull", 14: "Cow",
    15: "Bird", 16: "Frog", 17: "Alligator", 18: "Goat", 19: "Tiger",
    20: "Anteater", 21: "Koala", 22: "Horse", 23: "Octopus", 24: "Lion",
    25: "Bear Cub", 26: "Rhinoceros", 27: "Gorilla", 28: "Ostrich",
    29: "Kangaroo", 30: "Eagle", 31: "Penguin", 32: "Monkey",
}

PERSONALITY_NAMES = {
    0: "Lazy", 1: "Jock", 2: "Cranky",
    3: "Normal", 4: "Peppy", 5: "Snooty",
}

# Language slots for names (8 slots × 18 bytes UTF-16 BE)
NAME_LANGUAGES = ("ja", "en", "es_am", "es_eu", "fr", "it", "de", "kr")

# Language slots for catchphrases (10 slots × 22 bytes UTF-16 BE)
CATCH_LANGUAGES = (
    "ja", "en_us", "es_am", "fr_ca", "en_eu", "es_eu", "fr_eu", "it", "de", "kr",
)


# ---------------------------------------------------------------------------
# Entry offsets within a 408-byte record
# ---------------------------------------------------------------------------

_OFF_MODEL       = 0x01
_OFF_SHIRT       = 0x02
_OFF_FLOOR       = 0x04
_OFF_WALL        = 0x06
_OFF_UMBRELLA    = 0x08
_OFF_FURNITURE   = 0x0A   # 11 × u16
_OFF_KK_SONG     = 0x20   # u16
_OFF_NAMES       = 0x22   # 8 × 18 bytes
_OFF_CATCH       = 0xB2   # 10 × 22 bytes
_OFF_SPECIES     = 0x18E  # u8
_OFF_BIRTH_MONTH = 0x18F  # u8
_OFF_BIRTH_DAY   = 0x190  # u8
_OFF_FAV_CLOTH   = 0x192  # u8
_OFF_LEAST_CLOTH = 0x193  # u8
_OFF_FAV_COLOR   = 0x194  # u8
_OFF_FAV_SERIES  = 0x195  # u8
_OFF_PERS_FURN   = 0x196  # u8: high nibble = personality, low = furniture style
_OFF_STARTER     = 0x197  # u8: 0x80 = can be starter


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class NpcEntry:
    """Parsed NPC entry from pack.bin."""

    __slots__ = (
        "index", "model", "shirt", "floor", "wall", "umbrella",
        "furniture", "kk_song", "names", "catchphrases",
        "species_id", "species", "personality_id", "personality",
        "birth_month", "birth_day", "fav_cloth_style", "least_cloth_style",
        "fav_color", "fav_series", "furniture_style", "is_starter",
    )

    def __init__(self, index: int, raw: bytes):
        if len(raw) < PACK_ENTRY_SIZE:
            raise ValueError(
                f"NPC entry {index}: expected {PACK_ENTRY_SIZE} bytes, got {len(raw)}"
            )

        self.index = index
        self.model = raw[_OFF_MODEL]
        self.shirt = struct.unpack_from(">H", raw, _OFF_SHIRT)[0]
        self.floor = struct.unpack_from(">H", raw, _OFF_FLOOR)[0]
        self.wall = struct.unpack_from(">H", raw, _OFF_WALL)[0]
        self.umbrella = struct.unpack_from(">H", raw, _OFF_UMBRELLA)[0]

        self.furniture = []
        for i in range(11):
            self.furniture.append(
                struct.unpack_from(">H", raw, _OFF_FURNITURE + i * 2)[0]
            )
        self.kk_song = struct.unpack_from(">H", raw, _OFF_KK_SONG)[0]

        # Names: 8 language slots × 18 bytes (UTF-16 BE, 9 chars max)
        self.names: dict[str, str] = {}
        for i, lang in enumerate(NAME_LANGUAGES):
            chunk = raw[_OFF_NAMES + i * 18 : _OFF_NAMES + i * 18 + 18]
            try:
                self.names[lang] = chunk.decode("utf-16-be").rstrip("\x00")
            except UnicodeDecodeError:
                self.names[lang] = ""

        # Catchphrases: 10 language slots × 22 bytes (UTF-16 BE, 11 chars max)
        self.catchphrases: dict[str, str] = {}
        for i, lang in enumerate(CATCH_LANGUAGES):
            chunk = raw[_OFF_CATCH + i * 22 : _OFF_CATCH + i * 22 + 22]
            try:
                self.catchphrases[lang] = chunk.decode("utf-16-be").rstrip("\x00")
            except UnicodeDecodeError:
                self.catchphrases[lang] = ""

        # Tail fields
        self.species_id = raw[_OFF_SPECIES]
        self.species = SPECIES_NAMES.get(self.species_id, f"Unknown({self.species_id})")
        self.birth_month = raw[_OFF_BIRTH_MONTH]
        self.birth_day = raw[_OFF_BIRTH_DAY]
        self.fav_cloth_style = raw[_OFF_FAV_CLOTH]
        self.least_cloth_style = raw[_OFF_LEAST_CLOTH]
        self.fav_color = raw[_OFF_FAV_COLOR]
        self.fav_series = raw[_OFF_FAV_SERIES]

        pers_byte = raw[_OFF_PERS_FURN]
        self.personality_id = (pers_byte >> 4) & 0xF
        self.personality = PERSONALITY_NAMES.get(
            self.personality_id, f"Unknown({self.personality_id})"
        )
        self.furniture_style = pers_byte & 0xF
        self.is_starter = bool(raw[_OFF_STARTER] & 0x80)

    @property
    def name_en(self) -> str:
        return self.names.get("en", "")

    @property
    def name_ja(self) -> str:
        return self.names.get("ja", "")

    @property
    def catchphrase_en(self) -> str:
        return self.catchphrases.get("en_us", "")

    @property
    def birthday_str(self) -> str:
        if self.birth_month == 0 and self.birth_day == 0:
            return ""
        return f"{self.birth_month}/{self.birth_day}"

    @property
    def is_deluxe(self) -> bool:
        return self.index >= DELUXE_NPC_START

    def to_dict(self) -> dict:
        """Convert to a serializable dictionary."""
        return {
            "index": self.index,
            "model": self.model,
            "name_en": self.name_en,
            "name_ja": self.name_ja,
            "names": dict(self.names),
            "catchphrase_en": self.catchphrase_en,
            "catchphrases": dict(self.catchphrases),
            "species": self.species,
            "species_id": self.species_id,
            "personality": self.personality,
            "personality_id": self.personality_id,
            "birthday": self.birthday_str,
            "birth_month": self.birth_month,
            "birth_day": self.birth_day,
            "shirt": self.shirt,
            "floor": self.floor,
            "wall": self.wall,
            "umbrella": self.umbrella,
            "furniture": list(self.furniture),
            "kk_song": self.kk_song,
            "fav_cloth_style": self.fav_cloth_style,
            "least_cloth_style": self.least_cloth_style,
            "fav_color": self.fav_color,
            "fav_series": self.fav_series,
            "furniture_style": self.furniture_style,
            "is_starter": self.is_starter,
            "is_deluxe": self.is_deluxe,
        }


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class NpcDatabase:
    """Parsed NPC database from pack.bin."""

    def __init__(self, entries: list[NpcEntry]):
        self.entries = entries
        self._by_index: dict[int, NpcEntry] = {e.index: e for e in entries}

    def __len__(self) -> int:
        return len(self.entries)

    def __getitem__(self, index: int) -> NpcEntry:
        return self._by_index[index]

    def __contains__(self, index: int) -> bool:
        return index in self._by_index

    def get(self, index: int) -> Optional[NpcEntry]:
        return self._by_index.get(index)

    @property
    def vanilla_entries(self) -> list[NpcEntry]:
        return [e for e in self.entries if not e.is_deluxe]

    @property
    def deluxe_entries(self) -> list[NpcEntry]:
        return [e for e in self.entries if e.is_deluxe]

    def search_by_name(self, query: str) -> list[NpcEntry]:
        """Search NPCs by name (case-insensitive, matches any language)."""
        q = query.lower()
        results = []
        for e in self.entries:
            for name in e.names.values():
                if q in name.lower():
                    results.append(e)
                    break
        return results

    def filter_by_species(self, species: str) -> list[NpcEntry]:
        """Filter NPCs by species name (case-insensitive)."""
        s = species.lower()
        return [e for e in self.entries if e.species.lower() == s]

    def filter_by_personality(self, personality: str) -> list[NpcEntry]:
        """Filter NPCs by personality name (case-insensitive)."""
        p = personality.lower()
        return [e for e in self.entries if e.personality.lower() == p]


def parse_pack_bin(data: bytes) -> NpcDatabase:
    """Parse a pack.bin file into an NpcDatabase.

    Args:
        data: Raw bytes of the pack.bin file.

    Returns:
        NpcDatabase with all parsed entries.

    Raises:
        ValueError: If the file is too small or has an invalid header.
    """
    if len(data) < PACK_HEADER_SIZE:
        raise ValueError(f"pack.bin too small: {len(data)} bytes (need >= {PACK_HEADER_SIZE})")

    entry_count = struct.unpack_from(">I", data, 0)[0]
    entry_size = struct.unpack_from(">I", data, 4)[0]

    if entry_size != PACK_ENTRY_SIZE:
        raise ValueError(
            f"Unexpected entry size: {entry_size} (expected {PACK_ENTRY_SIZE})"
        )

    min_size = PACK_HEADER_SIZE + entry_count * entry_size
    if len(data) < min_size:
        raise ValueError(
            f"pack.bin truncated: {len(data)} bytes, need {min_size} "
            f"for {entry_count} entries"
        )

    entries = []
    for i in range(entry_count):
        offset = PACK_HEADER_SIZE + i * entry_size
        raw = data[offset : offset + entry_size]
        entries.append(NpcEntry(i, raw))

    return NpcDatabase(entries)


def load_pack_bin(path: str | Path) -> NpcDatabase:
    """Load and parse a pack.bin file from disk.

    Args:
        path: Path to the pack.bin file.

    Returns:
        NpcDatabase with all parsed entries.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"pack.bin not found: {p}")
    return parse_pack_bin(p.read_bytes())

"""
save_handler.py - Core binary I/O handler for Animal Crossing save files.

Supports:
  - Animal Crossing: City Folk (Wii) - RVFOREST.DAT (0x40F340 bytes)
  - Animal Crossing (GameCube) - .gci (0x72040), .gcs (0x72150), raw (0x200000)
  - Animal Crossing Deluxe (GameCube mod) - same formats as vanilla GC
  - Doubutsu no Mori e+ (GameCube, JP) - .gci/.gcs/.raw (GAEJ/GAEE game IDs)

All multi-byte values are big-endian (PowerPC byte order).
Game type is auto-detected from file size and header.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional

from game_profiles import (
    GameType, ContainerType, GameProfile, detect_game_from_file, get_profile_for_game,
)

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
CRC_SEED_DLC = 0x04201018

# DLC region layout
DLC_CRC_OFFSET   = 0x20F320
DLC_ITEMS_OFFSET = 0x20F324
DLC_SLOT_SIZE    = 0x2000      # 8,192 bytes per slot
DLC_SLOT_COUNT   = 256
DLC_END_OFFSET   = DLC_ITEMS_OFFSET + DLC_SLOT_COUNT * DLC_SLOT_SIZE  # 0x40F324
DLC_BITM_SIZE    = 0x18C       # 396-byte BITM header
DLC_ASH0_SIZE    = 0x1E70      # ASH0 compressed data region
DLC_VALID_MARKER = 0x1701

# ACCF catalog bitmap (per-player, relative to player start)
CATALOG_BITMAP_OFF = 0x72DA
CATALOG_BITMAP_SIZE = 512      # 4096 bits

# ACCF catalog item ranges  {name: (start_code, end_code)}
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

# GC catalog sub-regions (all offsets relative to player struct start)
# From ac-decomp m_private.h and ACSE Catalog.cs
_GC_CATALOG_REGIONS = {
    "furniture": (0x1108, 172),  # 43 u32s = 1376 bits
    "wallpaper": (0x11B4, 12),   # 3 u32s = 96 bits
    "carpet":    (0x11C0, 12),   # 3 u32s = 96 bits
    "paper":     (0x11CC, 8),    # 2 u32s = 64 bits
    "music":     (0x11D4, 8),    # 2 u32s = 64 bits
}

# Encyclopedia bits overlap furniture bitfield at these player-relative offsets.
# Each entry: (offset, catalog_mask) — bits set in mask are catalog, cleared are encyclopedia.
# From ACSE Encyclopedia.cs: filling catalog must NOT overwrite encyclopedia bits.
_GC_ENCYCLOPEDIA_OVERLAP = {
    0x1164: 0x00, 0x1165: 0x03,
    0x1166: 0xFF, 0x1167: 0xFF,
    0x1168: 0x00, 0x1169: 0x00, 0x116A: 0x00, 0x116B: 0x00,
    0x116C: 0x00, 0x116D: 0x00, 0x116E: 0x00, 0x116F: 0x00,
    0x1170: 0xFF, 0x1171: 0xFF, 0x1172: 0xFF,
    0x1173: 0xFC,
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
    Binary handler for Animal Crossing save files (GC and Wii).

    All offsets and multi-byte values follow PowerPC big-endian convention.
    Data is held in a mutable bytearray for in-place editing.
    Game type is auto-detected on open().
    """

    def __init__(self) -> None:
        self.data: bytearray = bytearray()
        self._filepath: Optional[Path] = None
        self.modified: bool = False
        self.game_type: GameType = GameType.WII_ACCF
        self.container_type: ContainerType = ContainerType.RAW
        self.profile: Optional[GameProfile] = None
        self._save_data_start: int = 0  # Offset to save payload within file

    # -- properties ---------------------------------------------------------

    @property
    def filepath(self) -> Optional[Path]:
        """Path to the currently-loaded save file (None if nothing loaded)."""
        return self._filepath

    @property
    def is_gc(self) -> bool:
        """True if the loaded save is a GameCube game (incl. e+)."""
        return self.game_type in (
            GameType.GC_VANILLA, GameType.GC_DELUXE, GameType.GC_EPLUS,
        )

    @property
    def is_eplus(self) -> bool:
        """True if the loaded save is Doubutsu no Mori e+."""
        return self.game_type == GameType.GC_EPLUS

    @property
    def is_accf(self) -> bool:
        """True if the loaded save is Animal Crossing: City Folk."""
        return self.game_type in (GameType.WII_ACCF, GameType.WII_ACCF_DELUXE)

    # -- file I/O -----------------------------------------------------------

    def open(self, path: str | Path) -> bool:
        """
        Read a save file and auto-detect its game type.

        Supports ACCF (.dat), GC (.gci, .gcs, raw).
        Returns ``True`` on success, ``False`` on failure.
        """
        path = Path(path)
        try:
            raw = path.read_bytes()
        except (OSError, PermissionError) as exc:
            raise OSError(f"Cannot read save file: {exc}") from exc

        # Reject absurdly large files (real saves are ≤4.2 MB)
        if len(raw) > 8 * 1024 * 1024:
            return False

        # Try auto-detection
        try:
            game_type, container_type, save_start = detect_game_from_file(raw)
        except ValueError:
            # Fall back to ACCF size check for backwards compatibility
            if len(raw) == SAVE_SIZE:
                game_type = GameType.WII_ACCF
                container_type = ContainerType.RAW
                save_start = 0
            else:
                return False

        self.data = bytearray(raw)
        self._filepath = path
        self.modified = False
        self.game_type = game_type
        self.container_type = container_type
        self._save_data_start = save_start
        self.profile = get_profile_for_game(game_type)
        self.profile.save_data_start = save_start

        # Detect GC Deluxe (not applicable for e+ saves)
        if self.is_gc and not self.is_eplus:
            self._detect_gc_deluxe()

        return True

    def _detect_gc_deluxe(self) -> None:
        """Check if a GC save is the Deluxe mod edition."""
        try:
            # Check ordinance_flags at save+0x241A8
            off = self._save_data_start + 0x241A8
            if off < len(self.data):
                flags = self.data[off]
                if flags & 0xF0:  # Upper nibble has ordinance bits
                    self._apply_deluxe_profile()
                    return
            # Check stalk market trend type at save+0x2048E
            off = self._save_data_start + 0x2048E
            if off + 1 < len(self.data):
                trend = self.read_u16(off)
                if 3 <= trend <= 6:  # Valid Deluxe trend range (not 0xFFFF)
                    self._apply_deluxe_profile()
        except Exception:
            pass

    def _apply_deluxe_profile(self) -> None:
        """Apply Deluxe mod profile overrides."""
        self.game_type = GameType.GC_DELUXE
        self.profile.game_type = GameType.GC_DELUXE
        self.profile.display_name = "Animal Crossing Deluxe (GameCube)"
        self.profile.stalk_pattern_max = 4  # Deluxe has 5 patterns
        self.profile.p_bank = 0x1238  # Deluxe shifted bank from 0x122C

    def save(self, path: str | Path | None = None) -> None:
        """
        Update all checksums, then write the save to *path*.

        If *path* is ``None``, overwrite the original file.
        """
        if not self.data:
            raise ValueError("No save data loaded")
        self.update_all_crc()

        # For GC saves, duplicate the save data
        if self.is_gc and self.profile and self.profile.is_duplicated:
            start = self._save_data_start
            size = self.profile.save_payload_size
            end = start + size
            if end + size <= len(self.data):
                self.data[end:end + size] = self.data[start:end]

        target = Path(path) if path is not None else self._filepath
        if target is None:
            raise RuntimeError("No file path set; use save_as() or open() first")
        target.write_bytes(bytes(self.data))
        self._filepath = target
        self.modified = False

    def save_as(self, path: str | Path) -> None:
        """Update all checksums and write to a new path."""
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

    # -- string helpers -----------------------------------------------------

    # GC Animal Crossing character encoding.
    # Mostly ASCII-compatible for common characters:
    #   0x20 = space, 0x30-39 = digits, 0x41-5A = A-Z, 0x61-7A = a-z
    # The 0x00-0x1F range is European accented capitals (not control codes).
    # Full 256-entry table from ac-decomp/tools/msg_tool.py (CHAR_MAP).
    # For save editor use, we only need the printable subset — names are
    # ASCII-compatible and space-padded (0x20).

    # Byte-to-char lookup (256 entries, index = byte value)
    _GC_CHAR_TABLE: tuple[str, ...] = (
        # 0x00-0x1F: European accented capitals
        "¡", "¿", "Ä", "À", "Á", "Â", "Ã", "Å",
        "Ç", "È", "É", "Ê", "Ë", "Ì", "Í", "Î",
        "Ï", "Ð", "Ñ", "Ò", "Ó", "Ô", "Õ", "Ö",
        "Ø", "Ù", "Ú", "Û", "Ü", "ß", "Þ", "à",
        # 0x20-0x2F: space, punctuation, specials
        " ", "!", '"', "á", "â", "%", "&", "'",
        "(", ")", "~", "♥", ",", "-", ".", "♪",
        # 0x30-0x39: digits
        "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
        # 0x3A-0x40: punctuation
        ":", "💧", "<", "=", ">", "?", "@",
        # 0x41-0x5A: uppercase A-Z
        "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
        "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
        "U", "V", "W", "X", "Y", "Z",
        # 0x5B-0x60: accented/special
        "ã", "💢", "ä", "å", "_", "ç",
        # 0x61-0x7A: lowercase a-z
        "a", "b", "c", "d", "e", "f", "g", "h", "i", "j",
        "k", "l", "m", "n", "o", "p", "q", "r", "s", "t",
        "u", "v", "w", "x", "y", "z",
        # 0x7B-0x7F: accented e variants + control escape
        "è", "é", "ê", "ë", "\x7f",
        # 0x80-0x9F: accented lowercase + typographic
        "�", "ì", "í", "î", "ï", "•", "ð", "ñ",
        "ò", "ó", "ô", "õ", "ö", "œ", "ù", "ú",
        "ー", "û", "ü", "ý", "ÿ", "þ", "Ý", "¦",
        "§", "ª", "º", "‖", "µ", "³", "²", "¹",
        # 0xA0-0xAF: typographic + weather
        "¯", "¬", "Æ", "æ", "„", "»", "«", "☀",
        "☁", "☂", "🌬", "☃", "∋", "∈", "/", "∞",
        # 0xB0-0xBF: game symbols
        "○", "✕", "□", "△", "+", "⚡", "♂", "♀",
        "🍀", "★", "💀", "😮", "😄", "😣", "😠", "😃",
        # 0xC0-0xCF: more symbols
        "×", "÷", "🔨", "🎀", "✉", "💰", "🐾", "🐶",
        "🐱", "🐰", "🐦", "🐮", "🐷", "\n", "🐟", "🐞",
        # 0xD0-0xDF: misc punctuation
        ";", "#", " ", " ", "⚷", "'", "'", "—",
        "–", "Œ", "œ", "ᵉ", "ᵉʳ", "ʳᵉ", "\\",
        " ",
        # 0xE0-0xFF: reserved/unused (map to replacement char)
        "�", "�", "�", "�", "�", "�", "�", "�",
        "�", "�", "�", "�", "�", "�", "�", "�",
        "�", "�", "�", "�", "�", "�", "�", "�",
        "�", "�", "�", "�", "�", "�", "�", "�",
    )

    # DnM e+ character encoding (Japanese: hiragana, katakana, Latin)
    _EPLUS_CHAR_TABLE: tuple[str, ...] = (
        # 0x00-0x0F: Hiragana あ-た
        "あ", "い", "う", "え", "お", "か", "き", "く",
        "け", "こ", "さ", "し", "す", "せ", "そ", "た",
        # 0x10-0x1F: Hiragana ち-み
        "ち", "つ", "て", "と", "な", "に", "ぬ", "ね",
        "の", "は", "ひ", "ふ", "へ", "ほ", "ま", "み",
        # 0x20-0x2F: space, punctuation + む, め
        " ", "!", '"', "む", "め", "%", "&", "'",
        "(", ")", "~", "♥", ",", "-", ".", "♪",
        # 0x30-0x3F: digits + punctuation
        "0", "1", "2", "3", "4", "5", "6", "7",
        "8", "9", ":", "💧", "<", "+", ">", "?",
        # 0x40-0x4F: @ + A-O
        "@", "A", "B", "C", "D", "E", "F", "G",
        "H", "I", "J", "K", "L", "M", "N", "O",
        # 0x50-0x5F: P-Z + も, 💢, や, ゆ, _
        "P", "Q", "R", "S", "T", "U", "V", "W",
        "X", "Y", "Z", "も", "💢", "や", "ゆ", "_",
        # 0x60-0x6F: よ + a-o
        "よ", "a", "b", "c", "d", "e", "f", "g",
        "h", "i", "j", "k", "l", "m", "n", "o",
        # 0x70-0x7F: p-z + ら-れ + control escape
        "p", "q", "r", "s", "t", "u", "v", "w",
        "x", "y", "z", "ら", "り", "る", "れ", "\x7f",
        # 0x80-0x8F: half-width katakana punctuation + small kana
        "□", "。", "「", "」", "、", "・", "ヲ", "ァ",
        "ィ", "ゥ", "ェ", "ォ", "ャ", "ュ", "ョ", "ッ",
        # 0x90-0x9F: katakana ア-ソ (with ー)
        "ー", "ア", "イ", "ウ", "エ", "オ", "カ", "キ",
        "ク", "ケ", "コ", "サ", "シ", "ス", "セ", "ソ",
        # 0xA0-0xAF: katakana タ-マ
        "タ", "チ", "ツ", "テ", "ト", "ナ", "ニ", "ヌ",
        "ネ", "ノ", "ハ", "ヒ", "フ", "ヘ", "ホ", "マ",
        # 0xB0-0xBF: katakana ミ-ン + ヴ + smiley
        "ミ", "ム", "メ", "モ", "ヤ", "ユ", "ヨ", "ラ",
        "リ", "ル", "レ", "ロ", "ワ", "ン", "ヴ", "😄",
        # 0xC0-0xCF: hiragana ろ-っ + newline + ガギ
        "ろ", "わ", "を", "ん", "ぁ", "ぃ", "ぅ", "ぇ",
        "ぉ", "ゃ", "ゅ", "ょ", "っ", "\n", "ガ", "ギ",
        # 0xD0-0xDF: katakana dakuten グ-ブ
        "グ", "ゲ", "ゴ", "ザ", "ジ", "ズ", "ゼ", "ゾ",
        "ダ", "ヂ", "ヅ", "デ", "ド", "バ", "ビ", "ブ",
        # 0xE0-0xEF: katakana ベ-ポ + hiragana voiced が-ぜ
        "ベ", "ボ", "パ", "ピ", "プ", "ペ", "ポ", "が",
        "ぎ", "ぐ", "げ", "ご", "ざ", "じ", "ず", "ぜ",
        # 0xF0-0xFF: hiragana voiced ぞ-ぽ
        "ぞ", "だ", "ぢ", "づ", "で", "ど", "ば", "び",
        "ぶ", "べ", "ぼ", "ぱ", "ぴ", "ぷ", "ぺ", "ぽ",
    )

    # Build reverse table for encoding (char -> byte)
    _GC_REVERSE: dict[str, int] = {}
    _EPLUS_REVERSE: dict[str, int] = {}

    @classmethod
    def _build_gc_reverse(cls) -> dict[str, int]:
        if cls._GC_REVERSE:
            return cls._GC_REVERSE
        for i, ch in enumerate(cls._GC_CHAR_TABLE):
            if ch and ch != "�" and ch != "\x7f" and ch != "\n":
                if ch not in cls._GC_REVERSE:  # First mapping wins
                    cls._GC_REVERSE[ch] = i
        return cls._GC_REVERSE

    @classmethod
    def _build_eplus_reverse(cls) -> dict[str, int]:
        if cls._EPLUS_REVERSE:
            return cls._EPLUS_REVERSE
        for i, ch in enumerate(cls._EPLUS_CHAR_TABLE):
            if ch and ch != "\x7f" and ch != "\n":
                if ch not in cls._EPLUS_REVERSE:
                    cls._EPLUS_REVERSE[ch] = i
        return cls._EPLUS_REVERSE

    def _active_char_table(self) -> tuple[str, ...]:
        """Return the correct character table for the loaded game type."""
        if self.is_eplus:
            return self._EPLUS_CHAR_TABLE
        return self._GC_CHAR_TABLE

    def _active_reverse_table(self) -> dict[str, int]:
        """Return the correct reverse encoding table for the loaded game type."""
        if self.is_eplus:
            return self._build_eplus_reverse()
        return self._build_gc_reverse()

    def read_gc_string(self, offset: int, max_chars: int = 8) -> str:
        """
        Read a GC-encoded string (1 byte per char).

        Strings in GC saves are space-padded (0x20) to the max width.
        The encoding is ASCII-compatible for common characters.
        0x7F is a control escape (stop reading).  0xCD is newline
        (replaced with space for name/catchphrase contexts).

        For DnM e+, uses the Japanese character table instead.
        """
        self._check_offset(offset, max_chars)
        table = self._active_char_table()
        chars: list[str] = []
        for i in range(max_chars):
            b = self.data[offset + i]
            if b == 0x7F:
                break  # Control escape — stop
            if b < len(table):
                ch = table[b]
                if ch == "�":
                    break  # Reserved/invalid — stop
                # Replace newline with space for display
                chars.append(" " if ch == "\n" else ch)
            else:
                break
        return "".join(chars).rstrip()

    def write_gc_string(self, offset: int, text: str, max_chars: int = 8) -> None:
        """Write a GC-encoded string (1 byte per char, space-padded)."""
        self._check_offset(offset, max_chars)
        reverse = self._active_reverse_table()
        for i in range(max_chars):
            if i < len(text):
                ch = text[i]
                b = reverse.get(ch, 0x20)  # Default to space
            else:
                b = 0x20  # Space padding
            self.data[offset + i] = b
        self.modified = True

    def read_string(self, offset: int, max_chars: int = 8) -> str:
        """
        Read a string at *offset*, using the correct encoding for the
        loaded game type.

        GC: 1 byte per char, custom encoding.
        ACCF: 2 bytes per char, UTF-16 BE.
        """
        if self.is_gc:
            return self.read_gc_string(offset, max_chars)
        # ACCF: UTF-16 BE
        self._check_offset(offset, max_chars * 2)
        chars: list[str] = []
        for i in range(max_chars):
            code = struct.unpack_from(">H", self.data, offset + i * 2)[0]
            if code == 0:
                break
            chars.append(chr(code))
        return "".join(chars)

    def write_string(self, offset: int, text: str, max_chars: int = 8) -> None:
        """
        Write a string at *offset*, using the correct encoding for the
        loaded game type.
        """
        if self.is_gc:
            return self.write_gc_string(offset, max_chars=max_chars, text=text)
        # ACCF: UTF-16 BE
        self._check_offset(offset, max_chars * 2)
        for i in range(max_chars):
            code = ord(text[i]) if i < len(text) else 0
            struct.pack_into(">H", self.data, offset + i * 2, code)
        self.modified = True

    # ======================================================================
    # Checksum helpers
    # ======================================================================

    def _compute_crc(self, start: int, end: int, seed: int) -> int:
        """Return the CRC32 of data[start:end] with *seed*."""
        return _crc32_stream(self.data, start, end, seed)

    def _compute_gc_checksum(self) -> int:
        """
        Compute the GC uint16 additive checksum.

        Iterates over the save payload in 2-byte steps, summing all u16 words
        (skipping the checksum at offset 0x12).  Returns the negation.
        """
        start = self._save_data_start
        size = self.profile.save_payload_size if self.profile else 0x26000
        end = start + size
        if end > len(self.data):
            end = len(self.data) & ~1  # Clamp to even boundary
        cksum_off = start + 0x12  # Checksum location within save data
        total = 0
        for off in range(start, end, 2):
            if off == cksum_off:
                continue  # Skip the checksum itself
            word = (self.data[off] << 8) | self.data[off + 1]
            total = (total + word) & 0xFFFF
        return (-total) & 0xFFFF

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

    # -- CRC-DLC (downloadable content) ------------------------------------

    def update_crc_dlc(self, write: bool = True) -> int:
        """
        Compute the DLC region CRC.

        Checksum at 0x20F320, covers 0x20F324..0x40F324 (256 slots * 0x2000).
        Seed is 0x04201018.
        """
        end = min(DLC_END_OFFSET, len(self.data))
        crc = self._compute_crc(DLC_ITEMS_OFFSET, end, CRC_SEED_DLC)
        if write:
            self._write_crc(DLC_CRC_OFFSET, crc)
        return crc

    # -- aggregate checksum helpers -----------------------------------------

    def update_all_crc(self) -> None:
        """Recompute and write all checksum regions."""
        if self.is_gc:
            self._update_gc_checksum()
        else:
            # ACCF CRC32 regions
            for p in range(PLAYER_COUNT):
                self.update_crc_a(p, write=True)
            self.update_crc_b(write=True)
            self.update_crc_c(write=True)
            self.update_crc_d(write=True)
            self.update_crc_dlc(write=True)

    def _update_gc_checksum(self) -> None:
        """Compute and write the GC uint16 checksum."""
        cksum = self._compute_gc_checksum()
        off = self._save_data_start + 0x12
        struct.pack_into(">H", self.data, off, cksum)
        self.modified = True

    def check_all_crc(self) -> list[str]:
        """
        Verify all checksum regions.

        Returns a list of human-readable mismatch descriptions.
        An empty list means all checksums are valid.
        """
        if self.is_gc:
            return self._check_gc_checksum()

        # ACCF CRC32 checks
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
        # CRC-DLC
        stored = self._read_stored_crc(DLC_CRC_OFFSET)
        computed = self.update_crc_dlc(write=False)
        if stored != computed:
            mismatches.append(
                f"CRC-DLC: stored=0x{stored:08X} computed=0x{computed:08X}"
            )
        return mismatches

    def _check_gc_checksum(self) -> list[str]:
        """Verify the GC uint16 checksum."""
        off = self._save_data_start + 0x12
        stored = struct.unpack_from(">H", self.data, off)[0]
        computed = self._compute_gc_checksum()
        if stored != computed:
            return [f"GC checksum: stored=0x{stored:04X} computed=0x{computed:04X}"]
        return []

    # ======================================================================
    # Player data helpers
    # ======================================================================

    def _soff(self, rel_offset: int) -> int:
        """Convert a save-relative offset to an absolute file offset."""
        return self._save_data_start + rel_offset

    def player_offset(self, p: int) -> int:
        """Return the absolute byte offset for player *p* (0-3)."""
        if not (0 <= p < PLAYER_COUNT):
            raise ValueError(f"Player index must be 0-3, got {p}")
        if self.profile:
            return self._soff(self.profile.player_start) + self.profile.player_stride * p
        return PLAYER_STRIDE * p  # Legacy ACCF fallback

    def player_exists(self, p: int) -> bool:
        """
        Return ``True`` if player slot *p* contains valid data.

        ACCF: An empty slot produces a known CRC sentinel.
        GC: Check if player name is non-empty.
        """
        if self.is_gc:
            # GC: check if player name starts with a non-space byte
            # (GC names are space-padded; an empty slot is all spaces 0x20)
            if not self.profile:
                return False
            po = self.player_offset(p)
            name_off = po + self.profile.p_name
            max_len = self.profile.p_name_max
            if name_off + max_len > len(self.data):
                return False
            # Empty if all spaces (0x20) or all zeros
            name_bytes = self.data[name_off:name_off + max_len]
            return not all(b == 0x20 for b in name_bytes) and any(b != 0 for b in name_bytes)
        # ACCF
        crc = self.update_crc_a(p, write=False)
        return crc != EMPTY_PLAYER_CRC

    # -- wallet / bank / points / debt --------------------------------------

    def get_wallet(self, p: int) -> int:
        po = self.player_offset(p)
        if self.profile:
            return self.read_u32(po + self.profile.p_wallet)
        return self.read_u32(0x1154 + po)

    def set_wallet(self, p: int, val: int) -> None:
        po = self.player_offset(p)
        max_val = 99999
        if self.profile:
            self.write_u32(po + self.profile.p_wallet, min(val, max_val))
        else:
            self.write_u32(0x1154 + po, min(val, max_val))

    def get_bank(self, p: int) -> int:
        po = self.player_offset(p)
        if self.profile:
            return self.read_u32(po + self.profile.p_bank)
        return self.read_u32(0x115C + po)

    def set_bank(self, p: int, val: int) -> None:
        po = self.player_offset(p)
        if self.profile:
            self.write_u32(po + self.profile.p_bank, min(val, 999999999))
        else:
            self.write_u32(0x115C + po, min(val, 999999999))

    def get_debt(self, p: int) -> int:
        """Read Tom Nook's mortgage (GC only). Returns 0 for ACCF."""
        if self.is_gc and self.profile and self.profile.p_debt:
            return self.read_u32(self.player_offset(p) + self.profile.p_debt)
        return 0

    def set_debt(self, p: int, val: int) -> None:
        """Set Tom Nook's mortgage (GC only)."""
        if self.is_gc and self.profile and self.profile.p_debt:
            self.write_u32(self.player_offset(p) + self.profile.p_debt, val)

    def get_points(self, p: int) -> int:
        if not self.is_accf:
            return 0  # GC doesn't have HRA points
        po = self.player_offset(p)
        return self.read_u16(0x7FC0 + po)

    def set_points(self, p: int, val: int) -> None:
        if not self.is_accf:
            return
        po = self.player_offset(p)
        self.write_u16(0x7FC0 + po, min(val, 65535))

    # -- name / town info ---------------------------------------------------

    def get_player_name(self, p: int) -> str:
        po = self.player_offset(p)
        if self.profile:
            return self.read_string(po + self.profile.p_name, self.profile.p_name_max)
        return self.read_string(0x7EFA + po, 8)

    def get_town_name(self, p: int = 0) -> str:
        if self.is_gc and self.profile and self.profile.town_name_offset:
            # GC: global town name (use profile name max for e+ compat)
            name_max = self.profile.p_name_max if self.profile else 8
            return self.read_string(self._soff(self.profile.town_name_offset), name_max)
        po = self.player_offset(p)
        if self.profile:
            return self.read_string(po + self.profile.p_town_name, self.profile.p_name_max)
        return self.read_string(0x7EE4 + po, 8)

    def set_town_name(self, name: str, p: int = 0) -> None:
        if not name:
            return
        if self.is_gc and self.profile and self.profile.town_name_offset:
            name_max = self.profile.p_name_max if self.profile else 8
            self.write_string(self._soff(self.profile.town_name_offset), name, name_max)
            # Also update per-player town name fields so they stay in sync
            for i in range(self.profile.player_count):
                po = self.player_offset(i)
                if self.player_exists(i):
                    self.write_string(po + self.profile.p_town_name, name, name_max)
            return
        # ACCF: update all existing players' town name fields
        name_max = self.profile.p_name_max if self.profile else 8
        for i in range(self.profile.player_count if self.profile else 4):
            po = self.player_offset(i)
            if self.player_exists(i):
                if self.profile:
                    self.write_string(po + self.profile.p_town_name, name, name_max)
                else:
                    self.write_string(0x7EE4 + po, name, 8)

    def get_town_id(self, p: int = 0) -> int:
        if self.is_gc and self.profile and self.profile.town_id_offset:
            return self.read_u16(self._soff(self.profile.town_id_offset))
        po = self.player_offset(p)
        return self.read_u16(0x7EE2 + po)

    # -- island name --------------------------------------------------------

    def get_island_name(self) -> str:
        """Get the island name (GC/e+ only)."""
        if not self.profile or not self.profile.has_island:
            return ""
        if not self.profile.island_name_offset:
            return ""
        name_max = self.profile.island_name_max
        return self.read_string(self._soff(self.profile.island_name_offset), name_max)

    def set_island_name(self, name: str) -> None:
        """Set the island name (GC/e+ only)."""
        if not name or not self.profile or not self.profile.has_island:
            return
        if not self.profile.island_name_offset:
            return
        name_max = self.profile.island_name_max
        self.write_string(self._soff(self.profile.island_name_offset), name, name_max)

    # -- special byte -------------------------------------------------------

    def get_special_byte(self, p: int) -> int:
        if self.is_gc:
            return 0  # GC doesn't have this field
        return self.read_u8(0x7EF6 + self.player_offset(p))

    # -- donation -----------------------------------------------------------

    def get_donation(self) -> int:
        if self.is_gc:
            return 0  # GC doesn't have a donation counter
        return self.read_u32(0x5EC7C)

    def set_donation(self, val: int) -> None:
        if self.is_gc:
            return
        self.write_u32(0x5EC7C, val)

    # ======================================================================
    # Appearance helpers
    # ======================================================================

    def get_face(self, p: int) -> int:
        po = self.player_offset(p)
        if self.is_gc and self.profile:
            return self.read_u8(po + self.profile.p_face)
        return self.read_u8(po + 0x840A) & 0x0F

    def set_face(self, p: int, val: int) -> None:
        po = self.player_offset(p)
        if self.is_gc and self.profile:
            self.write_u8(po + self.profile.p_face, val & 0xFF)
            return
        off = po + 0x840A
        current = self.read_u8(off)
        self.write_u8(off, (current & 0xF0) | (val & 0x0F))

    def get_hair(self, p: int) -> int:
        if self.is_gc:
            return 0  # GC: hair is part of face type
        return self.read_u8(self.player_offset(p) + 0x840B)

    def set_hair(self, p: int, val: int) -> None:
        if self.is_gc:
            return
        self.write_u8(self.player_offset(p) + 0x840B, min(val, 0x19))

    def get_hair_color(self, p: int) -> int:
        if self.is_gc:
            return 0
        return self.read_u8(self.player_offset(p) + 0x840C)

    def set_hair_color(self, p: int, val: int) -> None:
        if self.is_gc:
            return
        self.write_u8(self.player_offset(p) + 0x840C, min(val, 7))

    def get_tan(self, p: int) -> int:
        po = self.player_offset(p)
        if self.is_gc and self.profile:
            return self.read_u8(po + self.profile.p_tan)
        return self.read_u8(po + 0x8416)

    def set_tan(self, p: int, val: int) -> None:
        po = self.player_offset(p)
        if self.is_gc and self.profile:
            self.write_u8(po + self.profile.p_tan, val & 0xFF)
            return
        self.write_u8(po + 0x8416, val & 0xFF)

    def get_hat(self, p: int) -> int:
        if self.is_gc:
            return 0  # GC: no hat system
        return self.read_u8(self.player_offset(p) + 0x8418) >> 1

    def set_hat(self, p: int, val: int) -> None:
        if self.is_gc:
            return
        self.write_u8(self.player_offset(p) + 0x8418, (min(val, 7) << 1) & 0xFF)

    # ======================================================================
    # Emotions
    # ======================================================================

    def get_emotions(self, p: int) -> list[int]:
        """
        Read 4 emotion bytes.

        Stored value 0xFF means "none" -> returned as 0.
        Otherwise returned as stored_value + 1.
        GC does not have equippable emotions.
        """
        if self.is_gc:
            return [0, 0, 0, 0]
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
        if self.is_gc:
            return
        base = 0x8634 + self.player_offset(p)
        for i in range(4):
            val = emotions[i] if i < len(emotions) else 0
            self.write_u8(base + i, 0xFF if val == 0 else (val - 1) & 0xFF)

    # ======================================================================
    # Town helpers
    # ======================================================================

    def get_nook_style(self) -> int:
        if self.is_gc and self.profile and self.profile.nook_style_offset:
            # GC: shop level is in bits [7:6] of the shop_info byte
            byte_val = self.read_u8(self._soff(self.profile.nook_style_offset))
            return (byte_val >> 6) & 3
        if self.is_gc:
            return 0
        return self.read_u8(0x630C3)

    def set_nook_style(self, val: int) -> None:
        if self.is_gc and self.profile and self.profile.nook_style_offset:
            # GC: shop level in bits [7:6], preserve lower 6 bits (paint color, flags)
            off = self._soff(self.profile.nook_style_offset)
            existing = self.read_u8(off)
            self.write_u8(off, (existing & 0x3F) | ((val & 3) << 6))
            return
        if self.is_gc:
            return
        self.write_u8(0x630C3, val & 0xFF)
        self.write_u8(0x630C3 + 4, val & 0xFF)

    def get_grass_style(self) -> int:
        if self.is_gc and self.profile:
            off = self._soff(self.profile.grass_type_offset)
            if off and off < len(self.data):
                return self.read_u8(off)
            return 0
        return self.read_u8(0x6D5B7)

    def set_grass_style(self, val: int) -> None:
        if self.is_gc and self.profile:
            off = self._soff(self.profile.grass_type_offset)
            if off and off < len(self.data):
                self.write_u8(off, min(val, 2))
            return
        self.write_u8(0x6D5B7, min(val, 2))

    def get_gate_style(self) -> int:
        if self.is_gc:
            return 0
        return self.read_u8(0x5EAE0)

    def set_gate_style(self, val: int) -> None:
        if self.is_gc:
            return
        self.write_u8(0x5EAE0, min(val, 2))

    def clear_sold_out_flags(self) -> None:
        """
        Clear the 36 sold-out flag bytes at 0x630CA.

        Each flag is separated by a 4-byte stride (write 0 at byte 0 of each
        4-byte entry).  ACCF only.
        """
        if self.is_gc:
            return
        base = 0x630CA
        for i in range(36):
            self.write_u8(base + i * 4, 0)

    # ======================================================================
    # Item grid helpers
    # ======================================================================

    def get_town_items(self) -> list[int]:
        """Read all town item codes."""
        if self.profile:
            base = self._soff(self.profile.town_data_offset)
            count = self.profile.town_item_count
        else:
            base = 0x68476
            count = 6400
        return [self.read_u16(base + i * 2) for i in range(count)]

    def set_town_item(self, index: int, value: int) -> None:
        """Write a single u16 town item at *index*."""
        count = self.profile.town_item_count if self.profile else 6400
        if not (0 <= index < count):
            raise ValueError(f"Town item index must be 0-{count-1}, got {index}")
        if self.profile:
            base = self._soff(self.profile.town_data_offset)
        else:
            base = 0x68476
        self.write_u16(base + index * 2, value)

    def get_buried_items(self) -> list[int]:
        """Read 400 u16 buried-item codes starting at 0x6B676.  ACCF only."""
        if self.is_gc:
            return []
        base = 0x6B676
        return [self.read_u16(base + i * 2) for i in range(400)]

    def get_acre_layout(self) -> list[int]:
        """Read the acre layout (u16 acre IDs)."""
        if self.profile:
            base = self._soff(self.profile.acre_data_offset)
            count = self.profile.acre_count
        else:
            base = 0x68414
            count = 49
        return [self.read_u16(base + i * 2) for i in range(count)]

    def get_grass_data(self) -> list[int]:
        """Read grass-wear data."""
        if self.is_gc:
            return []  # GC doesn't have grass wear data
        if self.profile:
            base = self._soff(self.profile.grass_data_offset)
            size = self.profile.grass_data_size
        else:
            base = 0x6BCB6
            size = 6400
        return [self.read_u8(base + i) for i in range(size)]

    def set_grass_data(self, data: list[int]) -> None:
        """Write grass-wear data."""
        if self.is_gc:
            return
        if self.profile:
            base = self._soff(self.profile.grass_data_offset)
            size = self.profile.grass_data_size
        else:
            base = 0x6BCB6
            size = 6400
        for i in range(min(len(data), size)):
            self.write_u8(base + i, data[i])

    def set_acre_layout(self, acres: list[int]) -> None:
        """Write acre layout."""
        if self.profile:
            base = self._soff(self.profile.acre_data_offset)
            count = self.profile.acre_count
        else:
            base = 0x68414
            count = 49
        for i in range(min(len(acres), count)):
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
        Read all 35 building coordinates as ``(x, y)`` tuples.  ACCF only.

        Buildings 0-32 are at $5EB0A, building 33 (Pavé) at $5EB90,
        building 34 (Bus Stop) at $5EB8A.  Coordinates of (0, 0) mean
        the building does not exist.
        """
        if self.is_gc:
            return []
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
        """Set coordinates for building *building_id* (0-34).  ACCF only."""
        if self.is_gc:
            return
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
        """Read all 100 sign coordinates as ``(x, y)`` tuples.  ACCF only."""
        if self.is_gc:
            return []
        base = 0x5EB92
        signs: list[tuple[int, int]] = []
        for i in range(self.SIGN_COUNT):
            x = self.read_u8(base + i * 2)
            y = self.read_u8(base + i * 2 + 1)
            signs.append((x, y))
        return signs

    def set_sign(self, sign_id: int, x: int, y: int) -> None:
        """Set coordinates for sign *sign_id* (0-99).  ACCF only."""
        if self.is_gc:
            return
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
        Read 400 u16 buried-item bitmask words starting at 0x6B676.  ACCF only.

        Each word is a 16-bit bitmask covering one row of 16 tiles within
        an acre.  25 acres × 16 rows = 400 words total.
        Bit N set means column N in that row has a buried item.
        """
        if self.is_gc:
            return []
        base = 0x6B676
        return [self.read_u16(base + i * 2) for i in range(400)]

    def set_buried_bitmap(self, bitmap: list[int]) -> None:
        """Write 400 u16 buried-item bitmask words.  ACCF only."""
        if self.is_gc:
            return
        base = 0x6B676
        for i in range(min(len(bitmap), 400)):
            self.write_u16(base + i * 2, bitmap[i])

    def is_buried(self, col: int, row: int, acre: int) -> bool:
        """Check if tile (col, row) in acre has a buried item."""
        if self.is_gc:
            return False
        bitmap = self.get_buried_bitmap()
        word_idx = (row % 16) + acre * 16
        if not (0 <= word_idx < 400):
            return False
        return bool(bitmap[word_idx] & (1 << (col % 16)))

    def toggle_buried(self, col: int, row: int, acre: int) -> None:
        """Toggle the buried flag for tile (col, row) in acre.  ACCF only."""
        if self.is_gc:
            return
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
        """Read pocket item codes."""
        po = self.player_offset(p)
        count = self.profile.p_pockets_count if self.profile else 15
        if self.profile:
            base = po + self.profile.p_pockets
        else:
            base = 0x7F42 + po
        return [self.read_u16(base + i * 2) for i in range(count)]

    def set_pockets(self, p: int, items: list[int]) -> None:
        """Write pocket item codes."""
        po = self.player_offset(p)
        count = self.profile.p_pockets_count if self.profile else 15
        empty = self.profile.empty_item if self.profile else 0xFFF1
        if self.profile:
            base = po + self.profile.p_pockets
        else:
            base = 0x7F42 + po
        for i in range(count):
            val = items[i] if i < len(items) else empty
            self.write_u16(base + i * 2, val)

    def get_drawers(self, p: int) -> list[int]:
        """Read 160 u16 drawer-item codes (32 rows x 5 cols).  ACCF only."""
        if self.is_gc:
            return []
        base = 0x1F3038 + p * 0x140
        return [self.read_u16(base + i * 2) for i in range(160)]

    def set_drawers(self, p: int, items: list[int]) -> None:
        """Write 160 u16 drawer-item codes.  ACCF only."""
        if self.is_gc:
            return
        base = 0x1F3038 + p * 0x140
        for i in range(160):
            val = items[i] if i < len(items) else 0xFFF1
            self.write_u16(base + i * 2, val)

    def get_lost_found(self) -> list[int]:
        """Read lost-and-found items.

        ACCF: 12 items at 0x72DDA (gate lost & found).
        GC:   up to 20 items at profile offset (police station).
        """
        if self.is_gc and self.profile and self.profile.lost_found_offset:
            base = self._soff(self.profile.lost_found_offset)
            count = self.profile.lost_found_count or 20
            result = []
            for i in range(count):
                try:
                    result.append(self.read_u16(base + i * 2))
                except (IndexError, struct.error):
                    break
            return result
        if self.is_gc:
            return []
        base = 0x72DDA
        return [self.read_u16(base + i * 2) for i in range(12)]

    def set_lost_found(self, items: list[int]) -> None:
        """Write lost-and-found items.

        ACCF: 12 items at 0x72DDA, empty = 0xFFF1.
        GC:   up to 20 items at profile offset, empty = 0x0000.
        """
        if self.is_gc and self.profile and self.profile.lost_found_offset:
            base = self._soff(self.profile.lost_found_offset)
            count = self.profile.lost_found_count or 20
            for i in range(count):
                val = items[i] if i < len(items) else 0x0000
                try:
                    self.write_u16(base + i * 2, val & 0xFFFF)
                except (IndexError, struct.error):
                    break
            return
        if self.is_gc:
            return
        base = 0x72DDA
        for i in range(12):
            val = items[i] if i < len(items) else 0xFFF1
            self.write_u16(base + i * 2, val)

    def get_recycle_bin(self) -> list[int]:
        """Read 12 u16 recycle-bin items (2x6) at 0x72DF2.  ACCF only."""
        if self.is_gc:
            return []
        base = 0x72DF2
        return [self.read_u16(base + i * 2) for i in range(12)]

    def set_recycle_bin(self, items: list[int]) -> None:
        """Write 12 u16 recycle-bin items.  ACCF only."""
        if self.is_gc:
            return
        base = 0x72DF2
        for i in range(12):
            val = items[i] if i < len(items) else 0xFFF1
            self.write_u16(base + i * 2, val)

    def get_nook_items(self) -> list[int]:
        """Read Nook shop items.

        ACCF: 36 items at 0x630C8 with 4-byte stride.
        GC:   up to 39 items at profile offset with 2-byte stride.
        """
        if self.is_gc and self.profile and self.profile.nook_items_offset:
            base = self._soff(self.profile.nook_items_offset)
            count = self.profile.nook_item_count or 39
            stride = self.profile.nook_item_stride or 2
            result = []
            for i in range(count):
                try:
                    result.append(self.read_u16(base + i * stride))
                except (IndexError, struct.error):
                    break
            return result
        if self.is_gc:
            return []
        base = 0x630C8
        return [self.read_u16(base + i * 4) for i in range(36)]

    def set_nook_items(self, items: list[int]) -> None:
        """Write Nook shop items.

        ACCF: 36 items at 0x630C8 with 4-byte stride, empty = 0xFFF1.
        GC:   up to 39 items at profile offset with 2-byte stride, empty = 0x0000.
        """
        if self.is_gc and self.profile and self.profile.nook_items_offset:
            base = self._soff(self.profile.nook_items_offset)
            count = self.profile.nook_item_count or 39
            stride = self.profile.nook_item_stride or 2
            for i in range(count):
                val = items[i] if i < len(items) else 0x0000
                try:
                    self.write_u16(base + i * stride, val & 0xFFFF)
                except (IndexError, struct.error):
                    break
            return
        if self.is_gc:
            return
        base = 0x630C8
        for i in range(36):
            val = items[i] if i < len(items) else 0xFFF1
            self.write_u16(base + i * 4, val)

    # ======================================================================
    # House helpers
    # ======================================================================

    # ACCF-specific house layout constants (used when profile is unavailable)
    _ACCF_HOUSE_BASE = 0x6DE6C
    _ACCF_ROOM_STRIDE = 0x15C0
    _ACCF_FLOOR_STRIDE = 0x458

    def _house_base_offset(self, house_index: int) -> int:
        """Return absolute offset for a house, using profile when available."""
        if self.profile and self.profile.house_start:
            return self._soff(self.profile.house_start
                              + house_index * self.profile.house_stride)
        return self._ACCF_HOUSE_BASE + house_index * self._ACCF_ROOM_STRIDE

    def get_house_room(self, room_index: int, floor: int) -> list[int]:
        """
        Read a 16x16 (256) u16 room grid.

        *room_index*: 0-3 (one per player / house).
        *floor*: room sub-index within the house.
          - ACCF: 0-5 (three floor levels x 2 sides).
          - GC/e+: 0-2 (entry room, second floor, basement).
        """
        if self.profile and self.profile.house_start:
            max_rooms = self.profile.room_count
            if not (0 <= room_index < self.profile.house_count):
                raise ValueError(f"room_index must be 0-{self.profile.house_count - 1}, got {room_index}")
            if not (0 <= floor < max_rooms):
                raise ValueError(f"floor must be 0-{max_rooms - 1}, got {floor}")
            hdr_size = self.profile.house_stride - self.profile.room_count * self.profile.room_stride
            if hdr_size < 0:
                return []
            base = (self._soff(self.profile.house_start)
                    + room_index * self.profile.house_stride
                    + hdr_size
                    + floor * self.profile.room_stride)
            item_count = min(self.profile.room_stride // 2, 256)
            return [self.read_u16(base + i * 2) for i in range(item_count)]

        # ACCF fallback (no profile loaded)
        if not (0 <= room_index < PLAYER_COUNT):
            raise ValueError(f"room_index must be 0-3, got {room_index}")
        if not (0 <= floor < 6):
            raise ValueError(f"floor must be 0-5, got {floor}")
        base = (
            self._ACCF_HOUSE_BASE
            + room_index * self._ACCF_ROOM_STRIDE
            + floor * self._ACCF_FLOOR_STRIDE
        )
        return [self.read_u16(base + i * 2) for i in range(256)]

    def get_house_items(self, room_index: int) -> list[list[int]]:
        """
        Return all room grids for *room_index*.

        - ACCF: 6 lists (3 floors x 2 sides), each 256 u16 values.
        - GC/e+: 3 lists (entry, upstairs, basement), each room_stride//2 u16 values.
        """
        if self.profile and self.profile.house_start:
            if not (0 <= room_index < self.profile.house_count):
                raise ValueError(f"room_index must be 0-{self.profile.house_count - 1}, got {room_index}")
            return [self.get_house_room(room_index, r)
                    for r in range(self.profile.room_count)]

        # ACCF fallback
        if not (0 <= room_index < PLAYER_COUNT):
            raise ValueError(f"room_index must be 0-3, got {room_index}")
        grids: list[list[int]] = []
        for floor in range(3):
            for side in range(2):
                offset = (
                    self._ACCF_HOUSE_BASE
                    + room_index * self._ACCF_ROOM_STRIDE
                    + floor * self._ACCF_FLOOR_STRIDE
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
        """Count how many catalog bits are set in the given item-code range.  ACCF only."""
        if self.is_gc:
            return 0
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
        """Set all catalog bits in the given item-code range.  ACCF only."""
        if self.is_gc:
            return
        catalog_base = 0x841A + self.player_offset(p)
        code = range_start
        while code <= range_end:
            byte_off, bit_mask = self._catalog_bit_info(code)
            off = catalog_base + byte_off
            self.write_u8(off, self.read_u8(off) | bit_mask)
            code += 4

    # --- GC catalog (bitmap-based, split into sub-regions) ----------------

    def fill_gc_catalog(self, p: int) -> None:
        """Fill all GC catalog sub-regions (furniture, wallpaper, carpet, paper).

        Does NOT fill music — use fill_gc_music() for that.
        Preserves encyclopedia bits that overlap the furniture bitfield.
        """
        if not self.is_gc or not self.profile:
            return
        if not (0 <= p < (self.profile.player_count or 4)):
            return
        try:
            po = self.player_offset(p)
        except (ValueError, IndexError):
            return

        for name, (off, size) in _GC_CATALOG_REGIONS.items():
            if name == "music":
                continue
            base = po + off
            for i in range(size):
                addr = base + i
                abs_off = off + i  # player-relative offset
                if abs_off in _GC_ENCYCLOPEDIA_OVERLAP:
                    mask = _GC_ENCYCLOPEDIA_OVERLAP[abs_off]
                    if mask == 0x00:
                        continue  # pure encyclopedia byte — don't touch
                    # Mixed byte: set only catalog bits, preserve encyclopedia
                    self.write_u8(addr, self.read_u8(addr) | mask)
                else:
                    self.write_u8(addr, 0xFF)
        self.modified = True

    def fill_gc_music(self, p: int) -> None:
        """Fill the GC music catalog bitfield (55 K.K. songs)."""
        if not self.is_gc or not self.profile:
            return
        if not (0 <= p < (self.profile.player_count or 4)):
            return
        try:
            base = self.player_offset(p) + _GC_CATALOG_REGIONS["music"][0]
        except (ValueError, IndexError):
            return
        size = _GC_CATALOG_REGIONS["music"][1]
        for i in range(size):
            self.write_u8(base + i, 0xFF)
        self.modified = True

    def gc_catalog_total(self, p: int) -> int:
        """Count total catalog bits set across all GC sub-regions for a player."""
        if not self.is_gc or not self.profile:
            return 0
        if not (0 <= p < (self.profile.player_count or 4)):
            return 0
        try:
            po = self.player_offset(p)
        except (ValueError, IndexError):
            return 0
        total = 0
        for _name, (off, size) in _GC_CATALOG_REGIONS.items():
            base = po + off
            for i in range(size):
                try:
                    byte_val = self.read_u8(base + i)
                except (IndexError, struct.error):
                    continue
                abs_off = off + i
                if abs_off in _GC_ENCYCLOPEDIA_OVERLAP:
                    byte_val &= _GC_ENCYCLOPEDIA_OVERLAP[abs_off]
                total += bin(byte_val).count('1')
        return total

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
        town_name portion with *new_name*.  ACCF only.

        Returns the number of replacements made.
        """
        if self.is_gc:
            return 0  # TODO: implement GC town name update
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
        the player_name portion with *new_name*.  ACCF only.

        Returns the number of replacements made.
        """
        if self.is_gc:
            return 0  # TODO: implement GC player name update
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
    # Villager / NPC helpers
    # ======================================================================

    # ACCF legacy constants (used when no profile is loaded)
    VILLAGER_BASE   = 0x21B20
    VILLAGER_STRIDE = 0x3040
    NPC_SLOT_COUNT  = 10

    # ACCF offsets within each villager struct
    _VOFF_EXISTS      = 0x0000
    _VOFF_NPC_ID      = 0x1824
    _VOFF_SHIRT       = 0x1826
    _VOFF_CARPET      = 0x1828
    _VOFF_WALLPAPER   = 0x182A
    _VOFF_UMBRELLA    = 0x182C
    _VOFF_FURNITURE   = 0x182E
    _VOFF_KK_SONG     = 0x1842
    _VOFF_CATCHPHRASE = 0x18EC
    _VOFF_NPC_ID2     = 0x2308
    _VOFF_PERSONALITY = 0x230A

    def _villager_offset(self, slot: int) -> int:
        """Return the absolute offset of a villager slot's struct."""
        if self.profile:
            count = self.profile.villager_count
            if not 0 <= slot < count:
                raise ValueError(f"Villager slot must be 0-{count-1}, got {slot}")
            return self._soff(self.profile.villager_start) + slot * self.profile.villager_stride
        if not 0 <= slot < self.NPC_SLOT_COUNT:
            raise ValueError(f"Villager slot must be 0-9, got {slot}")
        return self.VILLAGER_BASE + slot * self.VILLAGER_STRIDE

    def _villager_count(self) -> int:
        """Return the number of villager slots for the current game."""
        if self.profile:
            return self.profile.villager_count
        return self.NPC_SLOT_COUNT

    def is_slot_occupied(self, slot: int) -> bool:
        """Check whether a villager slot contains a resident."""
        base = self._villager_offset(slot)
        if self.is_gc and self.profile:
            # GC: villager ID at +0x00, 0 = empty
            npc_id = self.read_u16(base + self.profile.v_id)
            return npc_id != 0
        v_exists = self.profile.v_exists if self.profile else self._VOFF_EXISTS
        if self.read_u8(base + v_exists) != 0:
            return True
        # ACCF "moved-in but model not built yet" case: exists byte is 0
        # but the villager ID at +0x1824 is set.  The game still renders
        # this villager (initializing the model on next load), so the
        # editor must show it too.
        v_id = self.profile.v_id if self.profile else self._VOFF_NPC_ID
        return self.read_u16(base + v_id) != 0

    def get_resident_ids(self) -> list[int]:
        """Read all resident NPC IDs from the villager structs.

        Returns a list of u16 values.  0xFFFF means an empty slot.
        """
        count = self._villager_count()
        result = []
        for i in range(count):
            base = self._villager_offset(i)
            if not self.is_slot_occupied(i):
                result.append(0xFFFF)
            else:
                v_id = self.profile.v_id if self.profile else self._VOFF_NPC_ID
                result.append(self.read_u16(base + v_id))
        return result

    def set_resident_id(self, slot: int, npc_id: int) -> None:
        """Write a single NPC ID into a resident slot.

        Writing 0xFFFF marks the slot as empty.
        """
        count = self._villager_count()
        if not 0 <= slot < count:
            raise ValueError(f"Resident slot must be 0-{count-1}, got {slot}")
        if not 0 <= npc_id <= 0xFFFF:
            raise ValueError(f"NPC ID must be 0-65535, got {npc_id}")

        base = self._villager_offset(slot)
        v_id = self.profile.v_id if self.profile else self._VOFF_NPC_ID

        if self.is_gc:
            # GC: just write the ID (0 = empty)
            self.write_u16(base + v_id, 0 if npc_id == 0xFFFF else npc_id)
        else:
            # ACCF: set exists byte + both ID fields
            v_exists = self.profile.v_exists if self.profile else self._VOFF_EXISTS
            v_id2 = self.profile.v_id2 if self.profile else self._VOFF_NPC_ID2
            if npc_id == 0xFFFF:
                self.write_u8(base + v_exists, 0)
                self.write_u16(base + v_id, 0)
                if v_id2 >= 0:
                    self.write_u16(base + v_id2, 0)
            else:
                # ACCF villager replace: ALWAYS zero the per-slot
                # model/init block (everything before v_id) and leave the
                # exists byte at 0 — the "moving in" state.  The empirical
                # working pattern observed in real saves is:
                #   exists = 0x00, model block = all zeros, v_id = new id.
                # On next load the game re-initializes the villager from
                # v_id and re-populates the model block itself.
                #
                # This is unconditional (not gated on existing_id != npc_id)
                # because saves previously written by a buggy editor can
                # have a stale model block whose v_id matches the new id —
                # in that case the model is wrong but the id check would
                # incorrectly skip the reset, leaving the game rendering
                # the old villager forever.
                #
                # All editable per-villager fields (personality, catchphrase,
                # shirt, furniture, wallpaper, carpet, umbrella, kk_song)
                # live AFTER v_id (offsets 0x1826+), so they are not
                # affected by zeroing 0x00..v_id.
                if v_id > 0:
                    self._check_offset(base, v_id)
                    self.data[base : base + v_id] = b"\x00" * v_id
                    self.modified = True
                self.write_u16(base + v_id, npc_id)
                if v_id2 >= 0:
                    self.write_u16(base + v_id2, npc_id)

    def set_resident_ids(self, ids: list[int]) -> None:
        """Write all resident NPC IDs at once."""
        count = self._villager_count()
        if len(ids) != count:
            raise ValueError(f"Expected {count} IDs, got {len(ids)}")
        for i, npc_id in enumerate(ids):
            self.set_resident_id(i, npc_id)

    def get_villager_personality(self, slot: int) -> int:
        """Read the in-save personality byte for a villager slot (0-5)."""
        base = self._villager_offset(slot)
        v_pers = self.profile.v_personality if self.profile else self._VOFF_PERSONALITY
        return self.read_u8(base + v_pers)

    def get_villager_catchphrase(self, slot: int) -> str:
        """Read the in-save catchphrase for a villager slot."""
        base = self._villager_offset(slot)
        v_cp = self.profile.v_catchphrase if self.profile else self._VOFF_CATCHPHRASE
        off = base + v_cp

        if self.is_gc:
            max_chars = self.profile.v_catchphrase_max if self.profile else 10
            return self.read_gc_string(off, max_chars)

        # ACCF: UTF-16 BE
        self._check_offset(off, 22)
        raw = bytes(self.data[off:off + 22])
        try:
            return raw.decode("utf-16-be").rstrip("\x00")
        except UnicodeDecodeError:
            return ""

    def set_villager_catchphrase(self, slot: int, text: str) -> None:
        """Write a catchphrase into a villager slot."""
        base = self._villager_offset(slot)
        v_cp = self.profile.v_catchphrase if self.profile else self._VOFF_CATCHPHRASE
        off = base + v_cp

        if self.is_gc:
            max_chars = self.profile.v_catchphrase_max if self.profile else 10
            self.write_gc_string(off, text, max_chars)
            return

        # ACCF: UTF-16 BE
        self._check_offset(off, 22)
        encoded = text[:10].encode("utf-16-be")
        padded = encoded.ljust(22, b"\x00")[:22]
        self.data[off:off + 22] = padded
        self.modified = True

    def get_villager_shirt(self, slot: int) -> int:
        """Read the shirt item ID for a villager slot."""
        base = self._villager_offset(slot)
        v_shirt = self.profile.v_shirt if self.profile else self._VOFF_SHIRT
        return self.read_u16(base + v_shirt)

    def set_villager_personality(self, slot: int, personality: int) -> None:
        """Write the in-save personality byte for a villager slot (0-5)."""
        if not 0 <= personality <= 5:
            raise ValueError(f"Personality must be 0-5, got {personality}")
        base = self._villager_offset(slot)
        v_pers = self.profile.v_personality if self.profile else self._VOFF_PERSONALITY
        self.write_u8(base + v_pers, personality)

    def set_villager_shirt(self, slot: int, item_id: int) -> None:
        """Write the shirt item ID for a villager slot."""
        base = self._villager_offset(slot)
        v_shirt = self.profile.v_shirt if self.profile else self._VOFF_SHIRT
        self.write_u16(base + v_shirt, item_id)

    def _v_field_offset(self, field: str) -> int:
        """Resolve a villager field offset from profile or legacy constants."""
        if self.profile:
            val = getattr(self.profile, field, -1)
            if val < 0:
                raise ValueError(f"Field '{field}' not supported for this game type")
            return val
        legacy = {
            "v_carpet": self._VOFF_CARPET,
            "v_wallpaper": self._VOFF_WALLPAPER,
            "v_umbrella": self._VOFF_UMBRELLA,
            "v_furniture": self._VOFF_FURNITURE,
            "v_kk_song": self._VOFF_KK_SONG,
        }
        val = legacy.get(field, -1)
        if val < 0:
            raise ValueError(f"Field '{field}' not supported for this game type")
        return val

    def get_villager_umbrella(self, slot: int) -> int:
        """Read the umbrella item ID for a villager slot."""
        base = self._villager_offset(slot)
        return self.read_u16(base + self._v_field_offset("v_umbrella"))

    def set_villager_umbrella(self, slot: int, item_id: int) -> None:
        """Write the umbrella item ID for a villager slot."""
        base = self._villager_offset(slot)
        self.write_u16(base + self._v_field_offset("v_umbrella"), item_id)

    def get_villager_wallpaper(self, slot: int) -> int:
        """Read the wallpaper item ID for a villager slot."""
        base = self._villager_offset(slot)
        return self.read_u16(base + self._v_field_offset("v_wallpaper"))

    def set_villager_wallpaper(self, slot: int, item_id: int) -> None:
        """Write the wallpaper item ID for a villager slot."""
        base = self._villager_offset(slot)
        self.write_u16(base + self._v_field_offset("v_wallpaper"), item_id)

    def get_villager_carpet(self, slot: int) -> int:
        """Read the flooring item ID for a villager slot."""
        base = self._villager_offset(slot)
        return self.read_u16(base + self._v_field_offset("v_carpet"))

    def set_villager_carpet(self, slot: int, item_id: int) -> None:
        """Write the flooring item ID for a villager slot."""
        base = self._villager_offset(slot)
        self.write_u16(base + self._v_field_offset("v_carpet"), item_id)

    def get_villager_kk_song(self, slot: int) -> int:
        """Read the K.K. Song item ID for a villager slot."""
        base = self._villager_offset(slot)
        return self.read_u16(base + self._v_field_offset("v_kk_song"))

    def set_villager_kk_song(self, slot: int, item_id: int) -> None:
        """Write the K.K. Song item ID for a villager slot."""
        base = self._villager_offset(slot)
        self.write_u16(base + self._v_field_offset("v_kk_song"), item_id)

    def get_villager_furniture(self, slot: int) -> list[int]:
        """Read the 11 furniture item IDs for a villager slot."""
        base = self._villager_offset(slot)
        furn_off = base + self._v_field_offset("v_furniture")
        return [self.read_u16(furn_off + i * 2) for i in range(11)]

    def set_villager_furniture(self, slot: int, items: list[int]) -> None:
        """Write the 11 furniture item IDs for a villager slot."""
        if len(items) != 11:
            raise ValueError(f"Expected 11 furniture items, got {len(items)}")
        base = self._villager_offset(slot)
        furn_off = base + self._v_field_offset("v_furniture")
        for i, item_id in enumerate(items):
            self.write_u16(furn_off + i * 2, item_id)

    def supports_villager_room(self) -> bool:
        """Check if the current game type supports per-villager room editing."""
        if self.profile:
            return self.profile.v_furniture >= 0
        return not self.is_gc

    # ======================================================================
    # Stalk Market (turnip prices)
    # ======================================================================

    _STALK_BASE = 0x63200  # Legacy ACCF

    def _stalk_base(self) -> int:
        """Return the absolute stalk market base offset."""
        if self.profile:
            return self._soff(self.profile.stalk_base)
        return self._STALK_BASE

    def get_turnip_buy_price(self) -> int:
        """Joan's Sunday buy price."""
        base = self._stalk_base()
        buy_off = self.profile.stalk_buy_offset if self.profile else 0
        if self.is_gc:
            return self.read_u16(base + buy_off)
        return self.read_u32(base + buy_off)

    def set_turnip_buy_price(self, price: int) -> None:
        base = self._stalk_base()
        buy_off = self.profile.stalk_buy_offset if self.profile else 0
        if self.is_gc:
            self.write_u16(base + buy_off, min(price, 0xFFFF))
        else:
            self.write_u32(base + buy_off, min(price, 0xFFFFFFFF))

    def get_turnip_sell_prices(self) -> list[int]:
        """Read sell prices (GC: 6 daily u16; ACCF: 14 half-day u32)."""
        base = self._stalk_base()
        sell_off = self.profile.stalk_sell_offset if self.profile else 4
        count = self.profile.stalk_sell_count if self.profile else 14
        if self.is_gc:
            return [self.read_u16(base + sell_off + i * 2) for i in range(count)]
        return [self.read_u32(base + sell_off + i * 4) for i in range(count)]

    def set_turnip_sell_prices(self, prices: list[int]) -> None:
        count = self.profile.stalk_sell_count if self.profile else 14
        if len(prices) != count:
            raise ValueError(f"Expected {count} prices, got {len(prices)}")
        base = self._stalk_base()
        sell_off = self.profile.stalk_sell_offset if self.profile else 4
        if self.is_gc:
            for i, p in enumerate(prices):
                self.write_u16(base + sell_off + i * 2, min(p, 0xFFFF))
        else:
            for i, p in enumerate(prices):
                self.write_u32(base + sell_off + i * 4, min(p, 0xFFFFFFFF))

    def get_turnip_pattern(self) -> int:
        """Stalk market trend type."""
        base = self._stalk_base()
        pat_off = self.profile.stalk_pattern_offset if self.profile else 0x3C
        if self.is_gc:
            return self.read_u16(base + pat_off)  # GC: u16
        return self.read_u32(base + pat_off)

    def set_turnip_pattern(self, pattern: int) -> None:
        max_pat = self.profile.stalk_pattern_max if self.profile else 3
        if not 0 <= pattern <= max_pat:
            raise ValueError(f"Turnip pattern must be 0-{max_pat}, got {pattern}")
        base = self._stalk_base()
        pat_off = self.profile.stalk_pattern_offset if self.profile else 0x3C
        if self.is_gc:
            self.write_u16(base + pat_off, pattern)
        else:
            self.write_u32(base + pat_off, pattern)

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
        if self.is_gc:
            return []
        return self._read_museum_nibbles(self._MUSEUM_FOSSIL_OFF, self._MUSEUM_FOSSIL_SIZE)

    def get_museum_fish(self) -> list[int]:
        if self.is_gc:
            return []
        return self._read_museum_nibbles(self._MUSEUM_FISH_OFF, self._MUSEUM_FISH_SIZE)

    def get_museum_insects(self) -> list[int]:
        if self.is_gc:
            return []
        return self._read_museum_nibbles(self._MUSEUM_INSECT_OFF, self._MUSEUM_INSECT_SIZE)

    def get_museum_art(self) -> list[int]:
        if self.is_gc:
            return []
        return self._read_museum_nibbles(self._MUSEUM_ART_OFF, self._MUSEUM_ART_SIZE)

    def fill_museum(self, player: int = 0) -> None:
        """Mark all museum items as donated by *player* (0-3).  ACCF only."""
        if self.is_gc:
            return
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
        """Clear all museum donations.  ACCF only."""
        if self.is_gc:
            return
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
        """Read 64 insect caught flags for player *p*.  ACCF only."""
        if self.is_gc:
            return []
        base = 0x8465 + self.player_offset(p)
        bits = []
        for i in range(8):
            b = self.read_u8(base + i)
            for bit in range(8):
                bits.append(bool(b & (1 << bit)))
        return bits

    def get_encyclopedia_fish(self, p: int) -> list[bool]:
        """Read 68 fish caught flags for player *p*.  ACCF only."""
        if self.is_gc:
            return []
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
        """Mark all fish and insects as caught for player *p*.  ACCF only."""
        if self.is_gc:
            return
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
        if self.profile and self.profile.pattern_base:
            count = self.profile.pattern_count or 8
            if not 0 <= slot < count:
                raise ValueError(f"Pattern slot must be 0-{count - 1}, got {slot}")
            return (self._soff(self.profile.player_start)
                    + p * self.profile.player_stride
                    + self.profile.pattern_base
                    + slot * self.profile.pattern_stride)
        # ACCF fallback
        if not 0 <= slot < self._PATTERN_COUNT:
            raise ValueError(f"Pattern slot must be 0-7, got {slot}")
        return self._PATTERN_BASE + self.player_offset(p) + slot * self._PATTERN_SIZE

    def get_pattern_title(self, p: int, slot: int) -> str:
        if self.profile and self.profile.pattern_base and self.is_gc:
            # GC/e+: 1-byte-per-char encoding
            off = self._pattern_offset(p, slot) + self.profile.pat_title
            size = self.profile.pat_title_size
            return self.read_gc_string(off, size)
        if self.is_gc:
            return ""
        off = self._pattern_offset(p, slot) + self._PAT_TITLE
        self._check_offset(off, 32)
        raw = bytes(self.data[off:off + 32])
        try:
            return raw.decode("utf-16-be").rstrip("\x00")
        except UnicodeDecodeError:
            return ""

    def set_pattern_title(self, p: int, slot: int, title: str) -> None:
        if self.profile and self.profile.pattern_base and self.is_gc:
            off = self._pattern_offset(p, slot) + self.profile.pat_title
            size = self.profile.pat_title_size
            self.write_gc_string(off, title[:size], size)
            self.modified = True
            return
        if self.is_gc:
            return
        off = self._pattern_offset(p, slot) + self._PAT_TITLE
        self._check_offset(off, 32)
        encoded = title[:16].encode("utf-16-be")
        padded = encoded.ljust(32, b"\x00")[:32]
        self.data[off:off + 32] = padded
        self.modified = True

    def get_pattern_creator(self, p: int, slot: int) -> str:
        if self.profile and self.profile.pattern_base and self.is_gc:
            if self.profile.pat_creator_size:
                off = self._pattern_offset(p, slot) + self.profile.pat_creator
                return self.read_gc_string(off, self.profile.pat_creator_size)
            return ""  # GC patterns have no separate creator field
        if self.is_gc:
            return ""
        off = self._pattern_offset(p, slot) + self._PAT_CREATOR
        self._check_offset(off, 16)
        raw = bytes(self.data[off:off + 16])
        try:
            return raw.decode("utf-16-be").rstrip("\x00")
        except UnicodeDecodeError:
            return ""

    def get_pattern_palette_rgb(self, p: int, slot: int) -> list[tuple[int, int, int]]:
        """Read the 16-color palette as (R, G, B) tuples.

        ACCF: RGB565 BE (16 x 2 bytes).
        GC/e+: 1-byte palette index (not an inline RGB palette).
        Returns empty list for GC since palette is index-based, not embedded RGB.
        """
        if self.is_gc:
            return []  # GC uses palette index, not embedded RGB565
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

    def get_pattern_palette_index(self, p: int, slot: int) -> int:
        """Read the palette index byte for a GC/e+ pattern. Returns -1 for ACCF."""
        if not self.is_gc:
            return -1
        if self.profile and self.profile.pattern_base and self.profile.pat_palette:
            off = self._pattern_offset(p, slot) + self.profile.pat_palette
            return self.read_u8(off)
        return 0

    def get_pattern_pixels(self, p: int, slot: int) -> list[list[int]]:
        """Read 32x32 pixel indices (0-15) in raster order.

        ACCF: C4 block order (8x8 blocks).
        GC/e+: Linear raster order (row by row, 2 pixels per byte).
        """
        if self.profile and self.profile.pattern_base and self.is_gc:
            off = self._pattern_offset(p, slot) + self.profile.pat_pixels
            size = self.profile.pat_pixels_size
            if off + size > len(self.data):
                return []
            raw = bytes(self.data[off:off + size])
            # GC: linear raster, 2 pixels per byte (high nibble first)
            pixels = [[0] * 32 for _ in range(32)]
            src = 0
            for y in range(32):
                for x in range(0, 32, 2):
                    if src >= len(raw):
                        break
                    byte = raw[src]
                    src += 1
                    pixels[y][x] = (byte >> 4) & 0xF
                    pixels[y][x + 1] = byte & 0xF
            return pixels
        if self.is_gc:
            return []
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

    # ======================================================================
    # DLC (Downloadable Content) — 256 BITM slots at 0x20F324
    # ======================================================================
    #
    # Each slot is 0x2000 bytes:
    #   +0x000: "BITM" magic (4 bytes)
    #   +0x004: Price (u32 BE)
    #   +0x008: Base item ID (u16 BE)
    #   +0x00A: Icon index (u16 BE)
    #   +0x00C: UnkC (u16), +0x00E: UnkE (u16)
    #   +0x010: Valid marker (u16, must be 0x1701)
    #   +0x012: 10 language name slots (0x22 bytes each, UTF-16 BE)
    #          JPN, ENG_US, ESP_US, FRA_US, ENG_EU, DEU, ITA, ESP_EU, FRA_EU, KOR
    #   +0x166: Class index (u8), +0x167: unk (u8), +0x168: drop model (u8)
    #   +0x169: Extended metadata (35 bytes)
    #   +0x18C: ASH0 compressed model/icon data (0x1E70 bytes)
    #   +0x1FFC: Per-slot CRC32 (4 bytes, seed 0x04201018)
    #
    # In-game item code = (base_item_id * 4) + 0x9000

    _DLC_NAME_LANGS = (
        "ja", "en_us", "es_us", "fra_us",
        "en_eu", "de", "it", "es_eu", "fra_eu", "kr",
    )
    _DLC_NAME_OFF  = 0x012   # first name slot within BITM
    _DLC_NAME_SIZE = 0x22    # 34 bytes per name (17 chars UTF-16 BE)

    def _dlc_slot_offset(self, slot: int) -> int:
        """Absolute offset of DLC slot *slot* (0-255)."""
        if not 0 <= slot < DLC_SLOT_COUNT:
            raise ValueError(f"DLC slot must be 0-255, got {slot}")
        return DLC_ITEMS_OFFSET + slot * DLC_SLOT_SIZE

    def is_dlc_slot_valid(self, slot: int) -> bool:
        """Check if a DLC slot contains a valid BITM item."""
        off = self._dlc_slot_offset(slot)
        magic = bytes(self.data[off:off + 4])
        if magic != b"BITM":
            return False
        marker = self.read_u16(off + 0x10)
        return marker == DLC_VALID_MARKER

    def get_dlc_item_count(self) -> int:
        """Count the number of valid DLC items in the save."""
        return sum(1 for i in range(DLC_SLOT_COUNT) if self.is_dlc_slot_valid(i))

    def get_dlc_base_id(self, slot: int) -> int:
        """Read the base item ID from a DLC slot (u16 BE at +0x08)."""
        return self.read_u16(self._dlc_slot_offset(slot) + 0x08)

    def get_dlc_item_code(self, slot: int) -> int:
        """Convert a DLC slot's base ID to the in-game item code."""
        return (self.get_dlc_base_id(slot) * 4) + 0x9000

    def get_dlc_price(self, slot: int) -> int:
        """Read the price in bells from a DLC slot (u32 BE at +0x04)."""
        return self.read_u32(self._dlc_slot_offset(slot) + 0x04)

    def set_dlc_price(self, slot: int, price: int) -> None:
        if not 0 <= price <= 0xFFFFFFFF:
            raise ValueError(f"Price must fit in u32, got {price}")
        self.write_u32(self._dlc_slot_offset(slot) + 0x04, price)

    def get_dlc_name(self, slot: int, lang: str = "en_us") -> str:
        """Read a DLC item name for the given language."""
        if lang not in self._DLC_NAME_LANGS:
            raise ValueError(f"Unknown lang '{lang}', use one of {self._DLC_NAME_LANGS}")
        lang_idx = self._DLC_NAME_LANGS.index(lang)
        off = self._dlc_slot_offset(slot) + self._DLC_NAME_OFF + lang_idx * self._DLC_NAME_SIZE
        self._check_offset(off, self._DLC_NAME_SIZE)
        raw = bytes(self.data[off:off + self._DLC_NAME_SIZE])
        try:
            return raw.decode("utf-16-be").rstrip("\x00")
        except UnicodeDecodeError:
            return ""

    def set_dlc_name(self, slot: int, name: str, lang: str = "en_us") -> None:
        """Write a DLC item name for the given language (max 16 chars)."""
        if lang not in self._DLC_NAME_LANGS:
            raise ValueError(f"Unknown lang '{lang}', use one of {self._DLC_NAME_LANGS}")
        lang_idx = self._DLC_NAME_LANGS.index(lang)
        off = self._dlc_slot_offset(slot) + self._DLC_NAME_OFF + lang_idx * self._DLC_NAME_SIZE
        self._check_offset(off, self._DLC_NAME_SIZE)
        encoded = name[:16].encode("utf-16-be")
        padded = encoded.ljust(self._DLC_NAME_SIZE, b"\x00")[:self._DLC_NAME_SIZE]
        self.data[off:off + self._DLC_NAME_SIZE] = padded
        self.modified = True

    def get_dlc_names(self, slot: int) -> dict[str, str]:
        """Read all 10 language names for a DLC slot."""
        return {lang: self.get_dlc_name(slot, lang) for lang in self._DLC_NAME_LANGS}

    def get_dlc_class_index(self, slot: int) -> int:
        """Furniture/item class index (u8 at +0x166)."""
        return self.read_u8(self._dlc_slot_offset(slot) + 0x166)

    def get_dlc_drop_model(self, slot: int) -> int:
        """Drop model index (u8 at +0x168)."""
        return self.read_u8(self._dlc_slot_offset(slot) + 0x168)

    def get_dlc_summary(self, slot: int) -> dict:
        """Return a summary dict for a DLC slot, or None if empty."""
        if not self.is_dlc_slot_valid(slot):
            return None
        return {
            "slot": slot,
            "base_id": self.get_dlc_base_id(slot),
            "item_code": self.get_dlc_item_code(slot),
            "price": self.get_dlc_price(slot),
            "name_en": self.get_dlc_name(slot, "en_us"),
            "name_ja": self.get_dlc_name(slot, "ja"),
            "class_idx": self.get_dlc_class_index(slot),
            "drop_model": self.get_dlc_drop_model(slot),
        }

    def get_all_dlc(self) -> list[dict]:
        """Return summaries of all valid DLC items."""
        result = []
        for i in range(DLC_SLOT_COUNT):
            s = self.get_dlc_summary(i)
            if s is not None:
                result.append(s)
        return result

    def clear_dlc_slot(self, slot: int) -> None:
        """Zero out a DLC slot entirely."""
        off = self._dlc_slot_offset(slot)
        self._check_offset(off, DLC_SLOT_SIZE)
        self.data[off:off + DLC_SLOT_SIZE] = b"\x00" * DLC_SLOT_SIZE
        self.modified = True

    def write_dlc_slot(self, slot: int, bitm_data: bytes) -> None:
        """Write raw BITM + ASH0 data into a DLC slot.

        *bitm_data* should be exactly 0x2000 bytes (BITM header + ASH0 + CRC),
        or up to 0x1FFC bytes (without trailing CRC, which will be computed).
        """
        if not 0 <= slot < DLC_SLOT_COUNT:
            raise ValueError(f"DLC slot must be 0-255, got {slot}")
        if len(bitm_data) > DLC_SLOT_SIZE:
            raise ValueError(
                f"DLC data too large: {len(bitm_data)} bytes (max {DLC_SLOT_SIZE})"
            )
        off = self._dlc_slot_offset(slot)
        self._check_offset(off, DLC_SLOT_SIZE)
        # Zero the slot first, then write data
        self.data[off:off + DLC_SLOT_SIZE] = b"\x00" * DLC_SLOT_SIZE
        self.data[off:off + len(bitm_data)] = bitm_data
        # Compute and write per-slot CRC at the last 4 bytes
        slot_crc = _crc32_stream(
            self.data, off, off + DLC_SLOT_SIZE - 4, CRC_SEED_DLC
        )
        struct.pack_into(">I", self.data, off + DLC_SLOT_SIZE - 4, slot_crc)
        self.modified = True

    def import_dlc_file(self, slot: int, path: str) -> str:
        """Import a raw DLC .bin file (BITM format) into a slot.

        Returns the item name on success, raises on failure.
        """
        from pathlib import Path
        p = Path(path)
        raw = p.read_bytes()
        if len(raw) < 0x18C:
            raise ValueError(f"File too small for BITM header: {len(raw)} bytes")
        if raw[:4] != b"BITM":
            raise ValueError(f"Not a BITM file (magic: {raw[:4]!r})")
        self.write_dlc_slot(slot, raw)
        return self.get_dlc_name(slot, "en_us")

    def find_empty_dlc_slot(self) -> int:
        """Find the first empty DLC slot, or -1 if all are used."""
        for i in range(DLC_SLOT_COUNT):
            if not self.is_dlc_slot_valid(i):
                return i
        return -1

    def patch_catalog_for_dlc(self, p: int) -> int:
        """Mark all valid DLC items in player *p*'s catalog bitmap.

        Returns the number of items patched.
        """
        po = self.player_offset(p)
        cat_base = CATALOG_BITMAP_OFF + po
        self._check_offset(cat_base, CATALOG_BITMAP_SIZE)
        count = 0
        for slot in range(DLC_SLOT_COUNT):
            if not self.is_dlc_slot_valid(slot):
                continue
            base_id = self.get_dlc_base_id(slot)
            # Catalog bit position = base_id
            byte_off = cat_base + (base_id >> 3)
            bit_mask = 1 << (base_id & 7)
            if byte_off < cat_base + CATALOG_BITMAP_SIZE:
                self.data[byte_off] |= bit_mask
                count += 1
        self.modified = True
        return count

    def clone_dlc_slot(self, src_slot: int, dst_slot: int) -> None:
        """Copy a DLC slot's raw data to another slot, recomputing CRC."""
        if not 0 <= src_slot < DLC_SLOT_COUNT:
            raise ValueError(f"Source slot must be 0-255, got {src_slot}")
        if not 0 <= dst_slot < DLC_SLOT_COUNT:
            raise ValueError(f"Destination slot must be 0-255, got {dst_slot}")
        src_off = self._dlc_slot_offset(src_slot)
        raw = bytes(self.data[src_off:src_off + DLC_SLOT_SIZE])
        self.write_dlc_slot(dst_slot, raw)

    def read_dlc_slot_raw(self, slot: int) -> bytes:
        """Return the raw 0x2000 bytes of a DLC slot."""
        off = self._dlc_slot_offset(slot)
        return bytes(self.data[off:off + DLC_SLOT_SIZE])

    def create_dlc_entry(
        self,
        slot: int,
        name: str,
        base_id: int,
        price: int = 0,
        class_idx: int = 0,
        sub_id: int = 0x0000,
        drop_model: int = 16,
        template_slot: int = -1,
    ) -> None:
        """Create a new HDLC (Hacked DLC) entry in the given slot.

        If *template_slot* is >= 0 and valid, its ASH0 data and extended
        metadata are copied into the new entry (visual clone with new identity).
        Otherwise, the slot is created with an empty ASH0 region.
        """
        if not 0 <= slot < DLC_SLOT_COUNT:
            raise ValueError(f"Slot must be 0-255, got {slot}")
        if not 0 <= base_id <= 0xFFFF:
            raise ValueError(f"Base ID must be 0-65535, got {base_id}")
        price = max(0, min(price, 0xFFFFFFFF))
        class_idx = class_idx & 0xFF
        sub_id = sub_id & 0xFFFF
        drop_model = drop_model & 0xFF

        buf = bytearray(DLC_SLOT_SIZE)

        # Copy template ASH0 + extended metadata if provided
        if 0 <= template_slot < DLC_SLOT_COUNT and self.is_dlc_slot_valid(template_slot):
            src_off = self._dlc_slot_offset(template_slot)
            # Copy extended metadata (+0x169, 35 bytes)
            buf[0x169:0x169 + 35] = self.data[src_off + 0x169:src_off + 0x169 + 35]
            # Copy ASH0 data (+0x18C, 0x1E70 bytes)
            buf[0x18C:0x18C + DLC_ASH0_SIZE] = self.data[
                src_off + 0x18C:src_off + 0x18C + DLC_ASH0_SIZE
            ]

        # BITM header
        buf[0:4] = b"BITM"
        struct.pack_into(">I", buf, 0x04, price & 0xFFFFFFFF)
        struct.pack_into(">H", buf, 0x08, base_id & 0xFFFF)
        struct.pack_into(">H", buf, 0x0A, sub_id & 0xFFFF)
        struct.pack_into(">H", buf, 0x10, DLC_VALID_MARKER)
        buf[0x166] = class_idx & 0xFF
        buf[0x167] = slot & 0xFF
        buf[0x168] = drop_model & 0xFF

        # Write name to all 10 language slots
        encoded = name[:16].encode("utf-16-be")
        padded = encoded.ljust(self._DLC_NAME_SIZE, b"\x00")[:self._DLC_NAME_SIZE]
        for lang_idx in range(10):
            off = self._DLC_NAME_OFF + lang_idx * self._DLC_NAME_SIZE
            buf[off:off + self._DLC_NAME_SIZE] = padded

        self.write_dlc_slot(slot, bytes(buf))

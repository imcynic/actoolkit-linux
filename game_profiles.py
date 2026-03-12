"""
Game profile definitions for Animal Crossing save editors.

Each profile contains all offset constants and structural metadata for a
specific game version.  The SaveHandler uses the active profile to locate
data within the save file.

Supported games:
  - Animal Crossing (GameCube, NTSC-U: GAFE)
  - Doubutsu no Mori e+ (GameCube, JP: GAEJ / fan translation: GAEE)
  - Animal Crossing: City Folk (Wii: RUUE / ACCF)

Offsets marked "rel:player" are relative to the player struct start.
Offsets marked "rel:save" are relative to the save data start.
Offsets marked "rel:villager" are relative to the villager struct start.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum, auto


# ---------------------------------------------------------------------------
# Game type enumeration
# ---------------------------------------------------------------------------

class GameType(Enum):
    GC_VANILLA = auto()       # Animal Crossing (GAFE/GAFP/GAFU)
    GC_DELUXE = auto()        # Animal Crossing Deluxe (GAFE modded)
    GC_EPLUS = auto()         # Doubutsu no Mori e+ (GAEJ/GAEE)
    WII_ACCF = auto()         # Animal Crossing: City Folk
    WII_ACCF_DELUXE = auto()  # ACCF Deluxe Edition


# ---------------------------------------------------------------------------
# Container format enumeration
# ---------------------------------------------------------------------------

class ContainerType(Enum):
    RAW = auto()        # No container, raw save data (ACCF .dat)
    GCI = auto()        # GameCube .gci file
    GCS = auto()        # GameCube .gcs file
    GC_RAW = auto()     # GameCube raw/Nintendont format (0x200000)


# ---------------------------------------------------------------------------
# String encoding types
# ---------------------------------------------------------------------------

class StringEncoding(Enum):
    UTF16_BE = auto()     # ACCF: 2 bytes per char, big-endian UTF-16
    GC_CUSTOM = auto()    # GC AC: 1 byte per char, custom encoding (Latin)
    GC_EPLUS = auto()     # DnM e+: 1 byte per char, custom encoding (Japanese)


# ---------------------------------------------------------------------------
# Checksum types
# ---------------------------------------------------------------------------

class ChecksumType(Enum):
    CRC32 = auto()       # ACCF: CRC32 with multiple regions
    UINT16_SUM = auto()  # GC: 16-bit additive checksum


# ---------------------------------------------------------------------------
# Game profile dataclass
# ---------------------------------------------------------------------------

@dataclass
class GameProfile:
    """Complete offset and structural profile for a game version."""

    game_type: GameType
    display_name: str

    # --- Save metadata ---
    save_payload_size: int        # Size of one copy of save data
    string_encoding: StringEncoding
    checksum_type: ChecksumType
    is_duplicated: bool           # GC saves store two copies
    empty_item: int               # Empty item sentinel (0x0000 GC, 0xFFF1 ACCF)

    # --- Container format offsets (set at load time) ---
    # These may vary by container type (.gci, .gcs, raw)
    save_data_start: int = 0     # Byte offset to save data within file

    # --- Checksum (rel:save) ---
    checksum_offset: int = 0     # GC: uint16 at this offset; ACCF: N/A (multiple)

    # --- Player ---
    player_start: int = 0        # Offset of first player (rel:save)
    player_stride: int = 0
    player_count: int = 4

    # Player field offsets (rel:player struct)
    p_name: int = 0              # Player name
    p_name_max: int = 8          # Max characters in name
    p_town_name: int = 0         # Town name within player struct
    p_wallet: int = 0            # Wallet (bells on hand)
    p_bank: int = 0              # Bank savings
    p_debt: int = 0              # Tom Nook mortgage (GC) / points (ACCF)
    p_pockets: int = 0           # Inventory start
    p_pockets_count: int = 15    # Number of inventory slots
    p_face: int = 0              # Face type
    p_hair: int = 0
    p_hair_color: int = 0
    p_tan: int = 0
    p_hat: int = 0
    p_shirt: int = 0             # Equipped shirt (GC)
    p_held_item: int = 0         # Currently held item (GC)
    p_emotions: int = 0          # Emotion slots
    p_emotion_count: int = 4
    p_catalog: int = 0           # Catalog bitmap start

    # --- Global town name (rel:save, for games where it's not per-player) ---
    town_name_offset: int = 0    # GC: global town name
    town_id_offset: int = 0      # GC: global town ID

    # --- Donation (rel:save, ACCF-specific) ---
    donation_offset: int = 0

    # --- Town / World ---
    town_data_offset: int = 0    # Town item grid (rel:save)
    town_data_size: int = 0
    town_grid_width: int = 0     # Items per row
    town_grid_height: int = 0    # Number of rows
    town_item_count: int = 0     # Total items in grid
    acre_data_offset: int = 0    # Acre ID array (rel:save)
    acre_count: int = 0
    acre_x_count: int = 0        # Columns of acres
    acre_y_count: int = 0        # Rows of acres
    grass_data_offset: int = 0   # Grass wear (rel:save)
    grass_data_size: int = 0
    grass_type_offset: int = 0   # Grass style byte (rel:save)
    buried_data_offset: int = 0  # Buried item bitmask (rel:save)
    buried_data_size: int = 0

    # --- Nook's shop (rel:save) ---
    nook_style_offset: int = 0
    nook_items_offset: int = 0
    nook_item_count: int = 0
    nook_item_stride: int = 0    # Bytes between shop items

    # --- Gate ---
    gate_style_offset: int = 0

    # --- Buildings (rel:save) ---
    building_base: int = 0
    building_count: int = 0
    sign_base: int = 0
    sign_count: int = 0

    # --- Houses (rel:save) ---
    house_start: int = 0
    house_stride: int = 0
    house_count: int = 0
    room_count: int = 0          # Rooms per house
    room_stride: int = 0

    # --- Villagers (rel:save) ---
    villager_start: int = 0
    villager_stride: int = 0
    villager_count: int = 0

    # Villager field offsets (rel:villager struct)
    v_exists: int = 0            # Existence byte
    v_id: int = 0                # NPC ID
    v_personality: int = 0
    v_catchphrase: int = 0
    v_catchphrase_max: int = 10
    v_shirt: int = 0
    v_carpet: int = -1           # Flooring (-1 = not supported)
    v_wallpaper: int = -1        # Wallpaper (-1 = not supported)
    v_umbrella: int = -1         # Umbrella (-1 = not supported)
    v_furniture: int = -1        # Base of 11 × u16 array (-1 = not supported)
    v_kk_song: int = -1          # K.K. Song (-1 = not supported)
    v_id2: int = -1              # Second NPC ID field (ACCF only, -1 = none)

    # --- Stalk market (rel:save) ---
    stalk_base: int = 0
    stalk_buy_offset: int = 0    # Relative to stalk_base
    stalk_sell_offset: int = 4   # Relative to stalk_base
    stalk_sell_count: int = 14
    stalk_pattern_offset: int = 0  # Relative to stalk_base
    stalk_pattern_max: int = 3   # Max valid pattern value

    # --- Museum / Encyclopedia ---
    museum_base: int = 0
    has_museum: bool = False

    # --- Patterns (rel:player) ---
    pattern_base: int = 0        # Offset within player struct
    pattern_stride: int = 0
    pattern_count: int = 8
    pat_pixels: int = 0          # Pixel data offset within pattern
    pat_pixels_size: int = 0
    pat_palette: int = 0         # Palette offset within pattern
    pat_title: int = 0
    pat_title_size: int = 0
    pat_creator: int = 0
    pat_creator_size: int = 0

    # --- Letters (rel:player) ---
    letter_base: int = 0
    letter_stride: int = 0
    letter_count: int = 10
    has_letters: bool = False

    # --- Drawers / Storage (may not be rel:player for ACCF) ---
    drawers_base: int = 0
    drawers_per_player_stride: int = 0
    drawers_count: int = 0
    drawers_is_global: bool = False  # True if drawers_base is absolute

    # --- Lost & Found / Recycle ---
    lost_found_offset: int = 0
    lost_found_count: int = 0
    recycle_offset: int = 0
    recycle_count: int = 0

    # --- DLC (ACCF only) ---
    has_dlc: bool = False

    # --- Feature flags ---
    has_island: bool = False
    has_emotions: bool = True
    has_catalog: bool = True
    has_points: bool = False     # ACCF has HRA points, GC has debt


# ---------------------------------------------------------------------------
# GC Animal Crossing profile (GAFE / GAFP / GAFU)
# ---------------------------------------------------------------------------

GC_PROFILE = GameProfile(
    game_type=GameType.GC_VANILLA,
    display_name="Animal Crossing (GameCube)",

    # Save metadata
    save_payload_size=0x26000,
    string_encoding=StringEncoding.GC_CUSTOM,
    checksum_type=ChecksumType.UINT16_SUM,
    is_duplicated=True,
    empty_item=0x0000,

    # Checksum
    checksum_offset=0x12,

    # Player (rel:save)
    player_start=0x20,
    player_stride=0x2440,
    player_count=4,

    # Player fields (rel:player)
    p_name=0x00,
    p_name_max=8,
    p_town_name=0x08,
    p_wallet=0x8C,
    p_bank=0x122C,          # "Savings" at post office
    p_debt=0x90,            # Tom Nook mortgage
    p_pockets=0x68,
    p_pockets_count=15,
    p_face=0x15,            # Face type byte
    p_hair=0x15,            # GC: face byte encodes hair too (combined)
    p_hair_color=0x15,      # GC: no separate hair color
    p_tan=0x23C8,           # Sunburn rank
    p_hat=0x00,             # GC: no separate hat field
    p_shirt=0x108A,         # Equipped shirt
    p_held_item=0x4A4,      # Currently held item
    p_emotions=0x00,        # GC doesn't have the same emotion system
    p_emotion_count=0,
    p_catalog=0x00,         # GC catalog is different

    # Global town name (rel:save)
    town_name_offset=0x9120,
    town_id_offset=0x912A,

    # Town items (rel:save)
    town_data_offset=0x137A8,
    town_data_size=0x3C00,
    town_grid_width=16,       # 16 items per acre row
    town_grid_height=16,      # 16 rows per acre
    town_item_count=7680,     # 30 acres × 256 items
    acre_data_offset=0x173A8,
    acre_count=70,
    acre_x_count=7,
    acre_y_count=10,
    grass_data_offset=0,      # GC: no grass wear
    grass_data_size=0,
    grass_type_offset=0x24184,
    buried_data_offset=0x20F1C,
    buried_data_size=0x3C0,

    # Nook's shop (rel:save) - TODO: find exact offsets
    nook_style_offset=0,
    nook_items_offset=0,
    nook_item_count=0,
    nook_item_stride=0,

    # Gate
    gate_style_offset=0,

    # Houses (rel:save)
    house_start=0x9CE8,
    house_stride=0x26B0,
    house_count=4,
    room_count=3,           # First floor, second floor, basement
    room_stride=0x8A8,

    # Villagers (rel:save)
    villager_start=0x17438,
    villager_stride=0x988,
    villager_count=16,       # 15 normal + 1 islander

    # Villager fields (rel:villager)
    v_exists=0x00,           # GC: villager_id != 0 means occupied
    v_id=0x00,               # Villager ID is at offset 0 (u16)
    v_personality=0x0D,
    v_catchphrase=0x89D,
    v_catchphrase_max=10,
    v_shirt=0x8E4,
    v_id2=-1,                # No second ID field

    # Stalk market (Kabu_price_c: 7 daily u16 prices + u16 pattern + 8B time)
    stalk_base=0x20480,      # Kabu_price_c struct
    stalk_buy_offset=0x00,   # daily_price[0] = Sunday (Joan's buy price)
    stalk_sell_offset=0x02,  # daily_price[1..6] = Mon-Sat sell prices
    stalk_sell_count=6,      # 6 sell prices (Mon-Sat), NOT 14 half-days
    stalk_pattern_offset=0x0E,  # trade_market field (u16, not u32)
    stalk_pattern_max=2,     # Vanilla: 0-2 (Deluxe: 0-4)

    # Patterns (rel:player)
    pattern_base=0x1240,
    pattern_stride=0x220,
    pattern_count=8,
    pat_pixels=0x20,         # Pixel data at +0x20
    pat_pixels_size=0x200,   # 32x32 @ 4bpp
    pat_palette=0x10,        # Palette index byte at +0x10
    pat_title=0x00,          # Title at +0x00
    pat_title_size=16,       # 16 bytes (1 byte per char)
    pat_creator=0x00,        # GC patterns don't have separate creator name
    pat_creator_size=0,

    # Letters - GC has a different mail format
    letter_base=0x00,
    letter_stride=0x00,
    letter_count=0,
    has_letters=False,        # TODO: implement GC mail

    # Drawers - GC has no dresser storage
    drawers_base=0,
    drawers_per_player_stride=0,
    drawers_count=0,
    drawers_is_global=False,

    # Lost & Found - TODO
    lost_found_offset=0,
    lost_found_count=0,
    recycle_offset=0,
    recycle_count=0,

    # Feature flags
    has_dlc=False,
    has_island=True,
    has_emotions=False,       # GC doesn't have equippable emotions
    has_catalog=False,        # GC catalog is different format
    has_points=False,
    has_museum=False,         # TODO: implement GC museum
)


# ---------------------------------------------------------------------------
# Doubutsu no Mori e+ profile (GAEJ / GAEE)
# ---------------------------------------------------------------------------

EPLUS_PROFILE = GameProfile(
    game_type=GameType.GC_EPLUS,
    display_name="Doubutsu no Mori e+ (GameCube)",

    # Save metadata
    save_payload_size=0x2E000,
    string_encoding=StringEncoding.GC_EPLUS,
    checksum_type=ChecksumType.UINT16_SUM,
    is_duplicated=True,
    empty_item=0x0000,

    # Checksum
    checksum_offset=0x12,

    # Player (rel:save)
    player_start=0x1C0,
    player_stride=0x26A0,
    player_count=4,

    # Player fields (rel:player)
    p_name=0x00,
    p_name_max=6,            # e+ uses 6-byte names
    p_town_name=0x06,
    p_wallet=0x94,
    p_bank=0x11B4,           # Savings at post office
    p_debt=0x98,             # Tom Nook mortgage
    p_pockets=0x64,
    p_pockets_count=15,
    p_face=0x11,             # Face type byte
    p_hair=0x11,             # e+: face byte encodes hair too (combined)
    p_hair_color=0x11,       # e+: no separate hair color
    p_tan=0x2348,            # Sunburn rank
    p_hat=0x00,              # e+: no separate hat field
    p_shirt=0xFF6,           # Equipped shirt
    p_held_item=0x874,       # Currently held item
    p_emotions=0x00,         # e+ doesn't have equippable emotions
    p_emotion_count=0,
    p_catalog=0x00,          # e+ catalog not supported yet

    # Global town name (rel:save)
    town_name_offset=0x14,
    town_id_offset=0x1C,

    # Town items (rel:save)
    town_data_offset=0x184C0,
    town_data_size=0x3C00,
    town_grid_width=16,       # 16 items per acre row
    town_grid_height=16,      # 16 rows per acre
    town_item_count=7680,     # 30 acres x 256 items
    acre_data_offset=0x1C0C0,
    acre_count=70,
    acre_x_count=7,
    acre_y_count=10,
    grass_data_offset=0,      # e+: no grass wear
    grass_data_size=0,
    grass_type_offset=0x24484,
    buried_data_offset=0x22B1C,
    buried_data_size=0x3C0,

    # Nook's shop (rel:save)
    nook_style_offset=0x22302,
    nook_items_offset=0,      # Not fully mapped yet
    nook_item_count=0,
    nook_item_stride=0,

    # Gate
    gate_style_offset=0,

    # Houses (rel:save)
    house_start=0xA340,
    house_stride=0x1A28,      # 0x30 header + 3 rooms x 0x8A8
    house_count=4,
    room_count=3,             # Entry room, second floor, basement
    room_stride=0x8A8,

    # Villagers (rel:save)
    villager_start=0x1C150,
    villager_stride=0x680,
    villager_count=15,

    # Villager fields (rel:villager)
    v_exists=0x00,            # e+: villager_id != 0 means occupied
    v_id=0x00,                # Villager ID is at offset 0 (u16)
    v_personality=0x0B,
    v_catchphrase=0x595,
    v_catchphrase_max=4,      # e+ has shorter catchphrases
    v_shirt=0x5DA,
    v_id2=-1,                 # No second ID field

    # Stalk market (Kabu_price_c at save+0x223C8)
    stalk_base=0x223C8,
    stalk_buy_offset=0x00,   # Sunday (Joan's buy price)
    stalk_sell_offset=0x02,  # Mon-Sat sell prices
    stalk_sell_count=6,
    stalk_pattern_offset=0x0E,
    stalk_pattern_max=2,

    # Patterns (rel:player)
    pattern_base=0x11C0,
    pattern_stride=0x220,
    pattern_count=8,
    pat_pixels=0x20,          # Pixel data at +0x20
    pat_pixels_size=0x200,    # 32x32 @ 4bpp
    pat_palette=0x0A,         # 1-byte palette index
    pat_title=0x00,           # Pattern name at +0x00
    pat_title_size=10,        # 10 bytes (1 byte per char)
    pat_creator=0x00,         # No separate creator name
    pat_creator_size=0,

    # Letters - e+ mail not implemented yet
    letter_base=0x00,
    letter_stride=0x00,
    letter_count=0,
    has_letters=False,

    # Drawers - e+ has no dresser storage
    drawers_base=0,
    drawers_per_player_stride=0,
    drawers_count=0,
    drawers_is_global=False,

    # Lost & Found
    lost_found_offset=0,
    lost_found_count=0,
    recycle_offset=0,
    recycle_count=0,

    # Feature flags
    has_dlc=False,
    has_island=True,
    has_emotions=False,       # e+ doesn't have equippable emotions
    has_catalog=False,        # e+ catalog not implemented
    has_points=False,
    has_museum=False,         # e+ museum not implemented yet
)


# ---------------------------------------------------------------------------
# ACCF (Wii) profile
# ---------------------------------------------------------------------------

ACCF_PROFILE = GameProfile(
    game_type=GameType.WII_ACCF,
    display_name="Animal Crossing: City Folk (Wii)",

    # Save metadata
    save_payload_size=0x40F340,
    string_encoding=StringEncoding.UTF16_BE,
    checksum_type=ChecksumType.CRC32,
    is_duplicated=False,
    empty_item=0xFFF1,

    # Checksum (multiple CRC regions - handled specially)
    checksum_offset=0,  # N/A - ACCF has multiple CRC regions

    # Player (rel:save, but save_data_start=0 for ACCF)
    player_start=0,
    player_stride=0x86C0,
    player_count=4,

    # Player fields (rel:player)
    p_name=0x7EFA,
    p_name_max=8,
    p_town_name=0x7EE4,
    p_wallet=0x1154,
    p_bank=0x115C,
    p_debt=0,             # No debt in ACCF (it's not exposed)
    p_pockets=0x7F42,
    p_pockets_count=15,
    p_face=0x840A,
    p_hair=0x840B,
    p_hair_color=0x840C,
    p_tan=0x8416,
    p_hat=0x8418,
    p_shirt=0,
    p_held_item=0,
    p_emotions=0x8634,
    p_emotion_count=4,
    p_catalog=0x841A,

    # Global town (ACCF stores town name per-player, not globally)
    town_name_offset=0,
    town_id_offset=0,

    # Donation
    donation_offset=0x5EC7C,

    # Town items
    town_data_offset=0x68476,
    town_data_size=0x3200,     # 6400 u16 = 12800 bytes
    town_grid_width=80,
    town_grid_height=80,
    town_item_count=6400,
    acre_data_offset=0x68414,
    acre_count=49,
    acre_x_count=7,
    acre_y_count=7,
    grass_data_offset=0x6BCB6,
    grass_data_size=6400,
    grass_type_offset=0x6D5B7,
    buried_data_offset=0x6B676,
    buried_data_size=800,      # 400 u16

    # Nook's shop
    nook_style_offset=0x630C3,
    nook_items_offset=0x630C8,
    nook_item_count=36,
    nook_item_stride=4,

    # Gate
    gate_style_offset=0x5EAE0,

    # Buildings
    building_base=0x5EB0A,
    building_count=35,
    sign_base=0x5EB92,
    sign_count=100,

    # Houses
    house_start=0x6DE6C,
    house_stride=0x15C0,
    house_count=4,
    room_count=6,           # 3 floors × 2 sides
    room_stride=0x458,

    # Villagers
    villager_start=0x21B20,
    villager_stride=0x3040,
    villager_count=10,

    # Villager fields (rel:villager)
    v_exists=0x0000,
    v_id=0x1824,
    v_personality=0x230A,
    v_catchphrase=0x18EC,
    v_catchphrase_max=10,
    v_shirt=0x1826,
    v_carpet=0x1828,
    v_wallpaper=0x182A,
    v_umbrella=0x182C,
    v_furniture=0x182E,
    v_kk_song=0x1842,
    v_id2=0x2308,

    # Stalk market
    stalk_base=0x63200,
    stalk_buy_offset=0x00,
    stalk_sell_offset=0x04,
    stalk_sell_count=14,
    stalk_pattern_offset=0x3C,
    stalk_pattern_max=3,

    # Museum
    museum_base=0x7352A,
    has_museum=True,

    # Patterns (rel:player)
    pattern_base=0x1160,
    pattern_stride=0x880,
    pattern_count=8,
    pat_pixels=0x000,
    pat_pixels_size=0x200,
    pat_palette=0x800,
    pat_title=0x84C,
    pat_title_size=32,       # 16 chars × 2 bytes UTF-16
    pat_creator=0x838,
    pat_creator_size=16,     # 8 chars × 2 bytes UTF-16

    # Letters (rel:player)
    letter_base=0x56E0,
    letter_stride=0x390,
    letter_count=10,
    has_letters=True,

    # Drawers
    drawers_base=0x1F3038,
    drawers_per_player_stride=0x140,
    drawers_count=160,
    drawers_is_global=True,

    # Lost & Found / Recycle
    lost_found_offset=0x72DDA,
    lost_found_count=12,
    recycle_offset=0x72DF2,
    recycle_count=12,

    # Feature flags
    has_dlc=True,
    has_island=False,
    has_emotions=True,
    has_catalog=True,
    has_points=True,
)


# ---------------------------------------------------------------------------
# Container format detection tables
# ---------------------------------------------------------------------------

# GC container: data start offsets by format (GAFE/GAFP/GAFU)
GC_CONTAINER_OFFSETS = {
    ContainerType.GCI: 0x26040,
    ContainerType.GCS: 0x26150,
    ContainerType.GC_RAW: 0x30000,
}

# e+ container: data start offsets (smaller banner area)
EPLUS_CONTAINER_OFFSETS = {
    ContainerType.GCI: 0x10040,
    ContainerType.GCS: 0x10150,
    ContainerType.GC_RAW: 0x1A000,
}

# Expected file sizes for each container format
FILE_SIZE_MAP: dict[int, tuple[ContainerType, str]] = {
    0x72040:  (ContainerType.GCI, "GAFE"),     # GC .gci
    0x72150:  (ContainerType.GCS, "GAFE"),     # GC .gcs
    0x200000: (ContainerType.GC_RAW, "GAFE"),  # GC raw/Nintendont
    0x40F340: (ContainerType.RAW, "ACCF"),     # ACCF
}

# Game IDs
GC_GAME_IDS = {"GAFE", "GAFP", "GAFU"}  # US, PAL, AU
EPLUS_GAME_IDS = {"GAEJ", "GAEE"}        # JP e+, fan translation


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def detect_game_from_file(data: bytes) -> tuple[GameType, ContainerType, int]:
    """
    Detect the game type, container format, and save data start offset
    from raw file bytes.

    Returns (game_type, container_type, save_data_start).
    Raises ValueError if the file is not recognized.
    """
    size = len(data)

    # ACCF (Wii) - raw .dat file
    if size == 0x40F340:
        return GameType.WII_ACCF, ContainerType.RAW, 0

    # Also support ACCF variant size
    if size == 0x47A0DA:
        return GameType.WII_ACCF, ContainerType.RAW, 0

    # GC .gci format (shared size for GAFE and GAEJ)
    if size == 0x72040:
        game_id = data[0:4].decode("ascii", errors="replace")
        if game_id in GC_GAME_IDS:
            return GameType.GC_VANILLA, ContainerType.GCI, 0x26040
        if game_id in EPLUS_GAME_IDS:
            return GameType.GC_EPLUS, ContainerType.GCI, 0x10040
        raise ValueError(f"Unrecognized GCI game ID: {game_id!r}")

    # GC .gcs format (shared size for GAFE and GAEJ)
    if size == 0x72150:
        game_id = data[0x110:0x114].decode("ascii", errors="replace")
        if game_id in GC_GAME_IDS:
            return GameType.GC_VANILLA, ContainerType.GCS, 0x26150
        if game_id in EPLUS_GAME_IDS:
            return GameType.GC_EPLUS, ContainerType.GCS, 0x10150
        raise ValueError(f"Unrecognized GCS game ID: {game_id!r}")

    # GC raw/Nintendont format
    if size == 0x200000:
        game_id = data[0x2000:0x2004].decode("ascii", errors="replace")
        if game_id in GC_GAME_IDS:
            return GameType.GC_VANILLA, ContainerType.GC_RAW, 0x30000
        if game_id in EPLUS_GAME_IDS:
            return GameType.GC_EPLUS, ContainerType.GC_RAW, 0x1A000
        raise ValueError(f"Unrecognized raw GC game ID: {game_id!r}")

    raise ValueError(
        f"Unrecognized save file size: {size} (0x{size:X}) bytes. "
        f"Expected ACCF (0x40F340), GC (.gci=0x72040, .gcs=0x72150, raw=0x200000), "
        f"or DnM e+ (same sizes as GC with GAEJ/GAEE game ID)."
    )


def get_profile_for_game(game_type: GameType) -> GameProfile:
    """Return a mutable copy of the appropriate profile for a game type."""
    if game_type in (GameType.GC_VANILLA, GameType.GC_DELUXE):
        src = GC_PROFILE
    elif game_type == GameType.GC_EPLUS:
        src = EPLUS_PROFILE
    elif game_type in (GameType.WII_ACCF, GameType.WII_ACCF_DELUXE):
        src = ACCF_PROFILE
    else:
        raise ValueError(f"No profile for game type: {game_type}")
    return GameProfile(**{f.name: getattr(src, f.name) for f in fields(src)})

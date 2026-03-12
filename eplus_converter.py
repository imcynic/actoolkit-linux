"""
eplus_converter.py - Convert between Doubutsu no Mori e+ and Animal Crossing
(GameCube) save formats.

Converts e+ (GAEJ) saves to Animal Crossing (GAFE) format for use with
the US/PAL game or Deluxe mod. Also supports converting GAFE saves back
to e+ format.

The conversion maps player data, town items, villager data, patterns,
house interiors, and acre layouts between the two different save structures
while recalculating checksums.
"""

from __future__ import annotations

import struct

from game_profiles import (
    GameType, ContainerType, GameProfile,
    get_profile_for_game,
)
from save_handler import SaveHandler


def _copy_player_patterns(
    src: SaveHandler, dst: SaveHandler,
    sp: GameProfile, dp: GameProfile,
    s_po: int, d_po: int,
) -> None:
    """Copy all 8 custom design patterns for a single player.

    Handles different title sizes (16 bytes GC vs 10 bytes e+) and
    palette offset differences (0x10 GC vs 0x0A e+). Pixel data
    (0x200 bytes at +0x20) is identical format in both games.
    """
    if not (sp.pattern_base and dp.pattern_base):
        return

    for slot in range(min(sp.pattern_count, dp.pattern_count)):
        s_pat = s_po + sp.pattern_base + slot * sp.pattern_stride
        d_pat = d_po + dp.pattern_base + slot * dp.pattern_stride

        # Pattern title (truncate to dest max)
        if sp.pat_title_size and dp.pat_title_size:
            title_len = min(sp.pat_title_size, dp.pat_title_size)
            title = src.read_gc_string(s_pat + sp.pat_title, title_len)
            dst.write_gc_string(d_pat + dp.pat_title, title[:dp.pat_title_size], dp.pat_title_size)

        # Palette index byte
        if sp.pat_palette and dp.pat_palette:
            pal = src.read_u8(s_pat + sp.pat_palette)
            dst.write_u8(d_pat + dp.pat_palette, pal)

        # Pixel data (both use 0x200 bytes at +0x20, identical format)
        if sp.pat_pixels_size and dp.pat_pixels_size:
            copy_size = min(sp.pat_pixels_size, dp.pat_pixels_size)
            s_px = s_pat + sp.pat_pixels
            d_px = d_pat + dp.pat_pixels
            if (s_px + copy_size <= len(src.data)
                    and d_px + copy_size <= len(dst.data)):
                dst.data[d_px:d_px + copy_size] = src.data[s_px:s_px + copy_size]


def _copy_houses(
    src: SaveHandler, dst: SaveHandler,
    sp: GameProfile, dp: GameProfile,
    s_base: int, d_base: int,
) -> None:
    """Copy all player house data (room furniture/items).

    Both GC vanilla and e+ use 4 houses x 3 rooms. Each room is 0x8A8 bytes
    in both formats. The house header size differs (strides differ) but the
    room data within is the same binary layout.
    """
    if not (sp.house_start and dp.house_start):
        return
    if not (sp.room_stride and dp.room_stride):
        return

    house_count = min(sp.house_count, dp.house_count)
    room_count = min(sp.room_count, dp.room_count)
    copy_room_size = min(sp.room_stride, dp.room_stride)

    # House header size = stride - (room_count * room_stride)
    s_hdr_size = sp.house_stride - sp.room_count * sp.room_stride
    d_hdr_size = dp.house_stride - dp.room_count * dp.room_stride
    if s_hdr_size < 0 or d_hdr_size < 0:
        return  # Malformed profile

    for h in range(house_count):
        s_house = s_base + sp.house_start + h * sp.house_stride
        d_house = d_base + dp.house_start + h * dp.house_stride

        # Copy house header (min of both header sizes)
        hdr_copy = min(s_hdr_size, d_hdr_size)
        if hdr_copy > 0:
            s_hdr = s_house
            d_hdr = d_house
            if (s_hdr + hdr_copy <= len(src.data)
                    and d_hdr + hdr_copy <= len(dst.data)):
                dst.data[d_hdr:d_hdr + hdr_copy] = src.data[s_hdr:s_hdr + hdr_copy]

        # Copy each room's data
        for r in range(room_count):
            s_room = s_house + s_hdr_size + r * sp.room_stride
            d_room = d_house + d_hdr_size + r * dp.room_stride
            if (s_room + copy_room_size <= len(src.data)
                    and d_room + copy_room_size <= len(dst.data)):
                dst.data[d_room:d_room + copy_room_size] = src.data[s_room:s_room + copy_room_size]


def _copy_stalk_market(
    src: SaveHandler, dst: SaveHandler,
    sp: GameProfile, dp: GameProfile,
    s_base: int, d_base: int,
) -> None:
    """Copy turnip/stalk market prices if both profiles support it."""
    if not (sp.stalk_base and dp.stalk_base):
        return

    # Buy price (Joan's Sunday price)
    buy = src.read_u16(s_base + sp.stalk_base + sp.stalk_buy_offset)
    dst.write_u16(d_base + dp.stalk_base + dp.stalk_buy_offset, buy)

    # Sell prices (Mon-Sat)
    sell_count = min(sp.stalk_sell_count, dp.stalk_sell_count)
    for i in range(sell_count):
        price = src.read_u16(s_base + sp.stalk_base + sp.stalk_sell_offset + i * 2)
        dst.write_u16(d_base + dp.stalk_base + dp.stalk_sell_offset + i * 2, price)

    # Pattern type
    if sp.stalk_pattern_offset and dp.stalk_pattern_offset:
        pat = src.read_u16(s_base + sp.stalk_base + sp.stalk_pattern_offset)
        pat = min(pat, dp.stalk_pattern_max)
        dst.write_u16(d_base + dp.stalk_base + dp.stalk_pattern_offset, pat)


def _copy_core_data(
    src: SaveHandler, dst: SaveHandler,
    sp: GameProfile, dp: GameProfile,
    s_base: int, d_base: int,
) -> None:
    """Copy all data fields common to both conversion directions.

    This includes: town name/ID, player data (name, wallet, bank, debt,
    pockets, face, shirt, held item, tan, patterns), town items, acres,
    buried items, villagers, houses, stalk market, nook style, grass type.
    """
    # --- Town name ---
    if sp.town_name_offset and dp.town_name_offset:
        src_town = src.get_town_name()
        dst_town = src_town[:dp.p_name_max].ljust(dp.p_name_max)
        dst.write_gc_string(d_base + dp.town_name_offset, dst_town, dp.p_name_max)

    # --- Town ID ---
    if sp.town_id_offset and dp.town_id_offset:
        town_id = src.read_u16(s_base + sp.town_id_offset)
        dst.write_u16(d_base + dp.town_id_offset, town_id)

    # --- Player data ---
    for p in range(min(sp.player_count, dp.player_count)):
        s_po = s_base + sp.player_start + p * sp.player_stride
        d_po = d_base + dp.player_start + p * dp.player_stride

        # Name (truncate/pad to dest max)
        name = src.read_gc_string(s_po + sp.p_name, sp.p_name_max)
        dst.write_gc_string(d_po + dp.p_name, name[:dp.p_name_max], dp.p_name_max)

        # Town name within player struct
        town = src.read_gc_string(s_po + sp.p_town_name, sp.p_name_max)
        dst.write_gc_string(d_po + dp.p_town_name, town[:dp.p_name_max], dp.p_name_max)

        # Wallet
        wallet = src.read_u32(s_po + sp.p_wallet)
        dst.write_u32(d_po + dp.p_wallet, min(wallet, 99999))

        # Bank
        bank = src.read_u32(s_po + sp.p_bank)
        dst.write_u32(d_po + dp.p_bank, min(bank, 999999999))

        # Debt
        if sp.p_debt and dp.p_debt:
            debt = src.read_u32(s_po + sp.p_debt)
            dst.write_u32(d_po + dp.p_debt, debt)

        # Pockets (15 items)
        for i in range(min(sp.p_pockets_count, dp.p_pockets_count)):
            item = src.read_u16(s_po + sp.p_pockets + i * 2)
            dst.write_u16(d_po + dp.p_pockets + i * 2, item)

        # Face type
        face = src.read_u8(s_po + sp.p_face)
        dst.write_u8(d_po + dp.p_face, face)

        # Shirt
        if sp.p_shirt and dp.p_shirt:
            shirt = src.read_u16(s_po + sp.p_shirt)
            dst.write_u16(d_po + dp.p_shirt, shirt)

        # Held item
        if sp.p_held_item and dp.p_held_item:
            held = src.read_u16(s_po + sp.p_held_item)
            dst.write_u16(d_po + dp.p_held_item, held)

        # Tan
        if sp.p_tan and dp.p_tan:
            tan = src.read_u8(s_po + sp.p_tan)
            dst.write_u8(d_po + dp.p_tan, tan)

        # Custom design patterns (8 per player)
        _copy_player_patterns(src, dst, sp, dp, s_po, d_po)

    # --- Town item grid (7680 items) ---
    src_items = src.get_town_items()
    count = min(len(src_items), dp.town_item_count)
    d_town = d_base + dp.town_data_offset
    if d_town + count * 2 <= len(dst.data):
        for i in range(count):
            struct.pack_into(">H", dst.data, d_town + i * 2, src_items[i])

    # --- Acre layout ---
    src_acres = src.get_acre_layout()
    acre_count = min(len(src_acres), dp.acre_count)
    d_acre = d_base + dp.acre_data_offset
    if d_acre + acre_count * 2 <= len(dst.data):
        for i in range(acre_count):
            struct.pack_into(">H", dst.data, d_acre + i * 2, src_acres[i])

    # --- Buried item data ---
    if sp.buried_data_offset and dp.buried_data_offset:
        copy_size = min(sp.buried_data_size, dp.buried_data_size)
        s_buried = s_base + sp.buried_data_offset
        d_buried = d_base + dp.buried_data_offset
        if (s_buried + copy_size <= len(src.data)
                and d_buried + copy_size <= len(dst.data)):
            dst.data[d_buried:d_buried + copy_size] = src.data[s_buried:s_buried + copy_size]

    # --- Villager data ---
    src_count = min(sp.villager_count, dp.villager_count)
    for v in range(src_count):
        s_vo = s_base + sp.villager_start + v * sp.villager_stride
        d_vo = d_base + dp.villager_start + v * dp.villager_stride

        # Villager ID
        vid = src.read_u16(s_vo + sp.v_id)
        dst.write_u16(d_vo + dp.v_id, vid)

        if vid == 0:
            continue  # Empty slot

        # Personality
        pers = src.read_u8(s_vo + sp.v_personality)
        dst.write_u8(d_vo + dp.v_personality, pers)

        # Catchphrase (truncate to dest max)
        cp = src.read_gc_string(s_vo + sp.v_catchphrase, sp.v_catchphrase_max)
        dst.write_gc_string(d_vo + dp.v_catchphrase, cp[:dp.v_catchphrase_max], dp.v_catchphrase_max)

        # Shirt
        shirt = src.read_u16(s_vo + sp.v_shirt)
        dst.write_u16(d_vo + dp.v_shirt, shirt)

    # --- House data (4 houses x 3 rooms) ---
    _copy_houses(src, dst, sp, dp, s_base, d_base)

    # --- Stalk market / turnip prices ---
    _copy_stalk_market(src, dst, sp, dp, s_base, d_base)

    # --- Nook shop style ---
    if sp.nook_style_offset and dp.nook_style_offset:
        nook = src.read_u8(s_base + sp.nook_style_offset)
        dst.write_u8(d_base + dp.nook_style_offset, nook)

    # --- Grass type ---
    if sp.grass_type_offset and dp.grass_type_offset:
        grass = src.read_u8(s_base + sp.grass_type_offset)
        dst.write_u8(d_base + dp.grass_type_offset, grass)


def convert_eplus_to_gafe(src: SaveHandler) -> SaveHandler:
    """
    Convert a Doubutsu no Mori e+ save (GAEJ) to an Animal Crossing (GAFE)
    GCI save file.

    Creates a new SaveHandler with a fresh GAFE-format GCI file populated
    with data from the e+ source.

    Returns the new SaveHandler (not yet written to disk).
    """
    if not src.is_eplus:
        raise ValueError("Source save is not a Doubutsu no Mori e+ save")
    if src.profile is None:
        raise ValueError("Source save has no loaded profile")

    sp = src.profile  # source profile (e+)
    dp = get_profile_for_game(GameType.GC_VANILLA)  # dest profile (GAFE)

    # Create a new GAFE GCI file (0x72040 bytes)
    dst_data = bytearray(0x72040)
    dst_data[0:4] = b"GAFE"

    dst = SaveHandler()
    dst.data = dst_data
    dst.game_type = GameType.GC_VANILLA
    dst.container_type = ContainerType.GCI
    dst._save_data_start = 0x26040
    dst.profile = dp
    dst.profile.save_data_start = 0x26040

    _copy_core_data(
        src, dst, sp, dp,
        src._save_data_start, dst._save_data_start,
    )

    dst.modified = True
    return dst


def convert_gafe_to_eplus(src: SaveHandler) -> SaveHandler:
    """
    Convert an Animal Crossing (GAFE) save to Doubutsu no Mori e+ (GAEJ)
    GCI save file format.

    Creates a new SaveHandler with a fresh GAEJ-format GCI file populated
    with data from the GAFE source.

    Returns the new SaveHandler (not yet written to disk).
    """
    if src.game_type not in (GameType.GC_VANILLA, GameType.GC_DELUXE):
        raise ValueError("Source save is not an Animal Crossing (GC) save")
    if src.profile is None:
        raise ValueError("Source save has no loaded profile")

    sp = src.profile  # source profile (GAFE)
    dp = get_profile_for_game(GameType.GC_EPLUS)  # dest profile (e+)

    # Create a new GAEJ GCI file (0x72040 bytes)
    dst_data = bytearray(0x72040)
    dst_data[0:4] = b"GAEJ"

    dst = SaveHandler()
    dst.data = dst_data
    dst.game_type = GameType.GC_EPLUS
    dst.container_type = ContainerType.GCI
    dst._save_data_start = 0x10040
    dst.profile = dp
    dst.profile.save_data_start = 0x10040

    _copy_core_data(
        src, dst, sp, dp,
        src._save_data_start, dst._save_data_start,
    )

    dst.modified = True
    return dst

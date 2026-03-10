"""Slot / free-space analyzer for Animal Crossing save files.

Scans every slot-based data structure in the save to report used vs free
capacity.  Works for both ACCF (Wii) and GC (vanilla/Deluxe).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from save_handler import SaveHandler, CATALOG_RANGES, DLC_SLOT_COUNT


# ---------------------------------------------------------------------------
# Result structures
# ---------------------------------------------------------------------------

@dataclass
class SlotInfo:
    """Counts for a single category."""
    name: str
    total: int
    used: int
    game: str = "both"  # "accf", "gc", or "both"

    @property
    def free(self) -> int:
        return self.total - self.used

    @property
    def pct(self) -> float:
        return (self.used / self.total * 100) if self.total else 0.0


@dataclass
class PlayerSlots:
    """Per-player slot breakdown."""
    index: int
    name: str
    categories: list[SlotInfo] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Complete analysis result."""
    game_label: str
    global_categories: list[SlotInfo] = field(default_factory=list)
    players: list[PlayerSlots] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

def analyze_save(sh: SaveHandler) -> AnalysisResult:
    """Run a full slot analysis on an open save file.

    Returns an ``AnalysisResult`` with global and per-player breakdowns.
    """
    is_gc = sh.is_gc
    empty = sh.profile.empty_item if sh.profile else 0xFFF1

    result = AnalysisResult(
        game_label=sh.profile.display_name if sh.profile else "Unknown",
    )

    # -- Global categories --------------------------------------------------

    # Town map items
    try:
        town = sh.get_town_items()
        count = len(town)
        used = sum(1 for v in town if v != empty)
        result.global_categories.append(SlotInfo("Town Items", count, used, "both"))
    except Exception:
        pass

    # Acres
    try:
        acres = sh.get_acre_layout()
        result.global_categories.append(
            SlotInfo("Acres", len(acres), sum(1 for a in acres if a != 0), "both")
        )
    except Exception:
        pass

    # Villager/NPC slots
    try:
        ids = sh.get_resident_ids()
        total_v = len(ids)
        used_v = sum(1 for v in ids if v != 0xFFFF)
        result.global_categories.append(SlotInfo("Villager Slots", total_v, used_v, "both"))
    except Exception:
        pass

    # -- ACCF-only global categories ----------------------------------------
    if not is_gc:
        # Lost & Found
        try:
            lf = sh.get_lost_found()
            result.global_categories.append(
                SlotInfo("Lost & Found", len(lf), sum(1 for v in lf if v != empty), "accf")
            )
        except Exception:
            pass

        # Recycle Bin
        try:
            rb = sh.get_recycle_bin()
            result.global_categories.append(
                SlotInfo("Recycle Bin", len(rb), sum(1 for v in rb if v != empty), "accf")
            )
        except Exception:
            pass

        # Nook's Store
        try:
            nook = sh.get_nook_items()
            result.global_categories.append(
                SlotInfo("Nook's Store", len(nook), sum(1 for v in nook if v != empty), "accf")
            )
        except Exception:
            pass

        # Buildings
        try:
            bldgs = sh.get_buildings()
            result.global_categories.append(
                SlotInfo("Buildings", len(bldgs), sum(1 for x, y in bldgs if (x, y) != (0, 0)), "accf")
            )
        except Exception:
            pass

        # Signs
        try:
            signs = sh.get_signs()
            result.global_categories.append(
                SlotInfo("Signs", len(signs), sum(1 for x, y in signs if (x, y) != (0, 0)), "accf")
            )
        except Exception:
            pass

        # Grass wear (count non-degraded tiles)
        try:
            grass = sh.get_grass_data()
            if grass:
                pristine = sum(1 for g in grass if g == 0)
                result.global_categories.append(
                    SlotInfo("Grass Tiles (Worn)", len(grass), len(grass) - pristine, "accf")
                )
        except Exception:
            pass

        # Museum
        _museum_cats = [
            ("Museum: Fossils", sh.get_museum_fossils),
            ("Museum: Fish", sh.get_museum_fish),
            ("Museum: Insects", sh.get_museum_insects),
            ("Museum: Art", sh.get_museum_art),
        ]
        for label, getter in _museum_cats:
            try:
                data = getter()
                if data:
                    result.global_categories.append(
                        SlotInfo(label, len(data), sum(1 for v in data if v != 0), "accf")
                    )
            except Exception:
                pass

        # DLC slots
        try:
            dlc_used = sh.get_dlc_item_count()
            result.global_categories.append(
                SlotInfo("DLC Slots", DLC_SLOT_COUNT, dlc_used, "accf")
            )
        except Exception:
            pass

    # -- Per-player categories ----------------------------------------------
    for p in range(4):
        if not sh.player_exists(p):
            continue

        pname = sh.get_player_name(p)
        ps = PlayerSlots(index=p, name=pname if pname else f"Player {p}")

        # Pockets
        try:
            pockets = sh.get_pockets(p)
            ps.categories.append(
                SlotInfo("Pockets", len(pockets), sum(1 for v in pockets if v != empty), "both")
            )
        except Exception:
            pass

        # Drawers (ACCF)
        if not is_gc:
            try:
                drawers = sh.get_drawers(p)
                if drawers:
                    ps.categories.append(
                        SlotInfo("Drawers", len(drawers), sum(1 for v in drawers if v != empty), "accf")
                    )
            except Exception:
                pass

        # House rooms (ACCF) - all 6 grids per player
        if not is_gc:
            try:
                grids = sh.get_house_items(p)
                if grids:
                    total_h = sum(len(g) for g in grids)
                    used_h = sum(1 for g in grids for v in g if v != empty)
                    ps.categories.append(
                        SlotInfo("House Items", total_h, used_h, "accf")
                    )
            except Exception:
                pass

        # Letters (ACCF)
        if not is_gc:
            try:
                letter_total = 10
                letter_used = sum(1 for s in range(letter_total) if not sh.is_letter_empty(p, s))
                ps.categories.append(
                    SlotInfo("Letters", letter_total, letter_used, "accf")
                )
            except Exception:
                pass

        # Patterns (ACCF)
        if not is_gc:
            try:
                pat_total = 8
                pat_used = 0
                for s in range(pat_total):
                    title = sh.get_pattern_title(p, s)
                    if title and title.strip():
                        pat_used += 1
                ps.categories.append(
                    SlotInfo("Patterns", pat_total, pat_used, "accf")
                )
            except Exception:
                pass

        # Encyclopedia (ACCF)
        if not is_gc:
            try:
                fish = sh.get_encyclopedia_fish(p)
                if fish:
                    ps.categories.append(
                        SlotInfo("Encyclopedia: Fish", len(fish), sum(fish), "accf")
                    )
            except Exception:
                pass
            try:
                insects = sh.get_encyclopedia_insects(p)
                if insects:
                    ps.categories.append(
                        SlotInfo("Encyclopedia: Insects", len(insects), sum(insects), "accf")
                    )
            except Exception:
                pass

        # Catalog (ACCF)
        if not is_gc:
            try:
                cat_used = 0
                cat_total = 0
                for _name, (start, end) in CATALOG_RANGES.items():
                    items_in_range = ((end - start) // 4) + 1
                    cat_total += items_in_range
                    cat_used += sh.catalog_total(p, start, end)
                ps.categories.append(
                    SlotInfo("Catalog", cat_total, cat_used, "accf")
                )
            except Exception:
                pass

        result.players.append(ps)

    return result

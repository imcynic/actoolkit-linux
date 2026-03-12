<div align="center">

<img src="assets/mascot_logo.png" alt="ACToolkit Mascot" width="180">

# ACToolkit Linux

**Cross-platform Animal Crossing save editor for ACCF (Wii), GameCube, and Doubutsu no Mori e+**

[![Python 3.7+](https://img.shields.io/badge/Python-3.7%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52?logo=qt&logoColor=white)](https://www.riverbankcomputing.com/software/pyqt/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

<br>

*Edit players, inventories, towns, villagers, turnip prices, DLC, and more. Convert between e+ and GAFE saves.*

</div>

---

## Supported Games

| Game | Platform | Format | Status |
|------|----------|--------|--------|
| **Animal Crossing: City Folk** | Wii | `.dat` | Full support |
| **ACCF Deluxe** (Revolution Forest Plus) | Wii | `.dat` | Full support + 131 mod items |
| **Animal Crossing** | GameCube | `.gci` `.gcs` raw | Full support |
| **AC Deluxe** (GC mod) | GameCube | `.gci` `.gcs` raw | Full support, auto-detected |
| **Doubutsu no Mori e+** | GameCube | `.gci` `.gcs` raw | Full support + bidirectional conversion |

Container formats: `.dat` (Wii raw), `.gci` (Dolphin/GC), `.gcs` (GC export), `.bin`/`.sav` (Nintendont 2MB raw)

---

## Features

### Player
- **Wallet & Bank** — set bells on hand and savings
- **Debt / HRA Points** — mortgage (GC) or Happy Room Academy score (ACCF)
- **Appearance** — face style, hair style & color, skin tone, hat
- **Emotions** — 4 equippable emotion slots with 20 types (ACCF)
- **Name & Town** — edit player and town names

### Inventory & Storage
- **Pockets** — 15 item slots with drag-and-drop item selector
- **Drawers** — 160 storage slots (ACCF)
- **Lost & Found / Recycle Bin** — 12 slots each (ACCF)
- **Nook's Store** — 36 shop inventory slots (ACCF)

### Town
- **Town Map** — full 80x80 tile grid editor with pan, zoom, and acre overlay
- **Acre Editor** — 7x7 acre type grid (terrain, ocean, river, transitions)
- **Buildings** — 35 building placements + 100 signs with X/Y coordinates
- **Grass Wear** — color-mapped visualization from dead (brown) to lush (green)
- **Buried Items** — toggle buried state on any tile

### Villagers
- **10-16 Resident Slots** — 10 (ACCF), 15 (e+), 16 (GC) villager slots
- **Catchphrase & Personality** — per-villager editing
- **210 Vanilla + 244 Deluxe + 311 GC + 33 Special** NPCs in database
- **Entity ID support** — GC 0xE000+ range and ACCF index-based IDs

### Stalk Market
- **Buy Price** — Joan's Sunday turnip price
- **Sell Prices** — 14 half-day prices Mon-Sat (ACCF) / 6 daily prices (GC)
- **Pattern Type** — decreasing, random, spike, etc.

### Collections
- **Museum** — fossils (60), fish (64), insects (64), art (28) with per-player donation tracking
- **Encyclopedia** — fish and insect completion
- **Catalog** — full bitmap-based item discovery tracking
- **Fill / Clear** buttons for bulk operations

### Patterns
- **8 Designs Per Player** — 32x32 pixel editor at 4bpp
- **16-Color Palette** — per-pattern color editing
- **Title Editing** — rename your custom designs

### DLC (ACCF)
- **256 Slots** — BITM-format DLC region
- **Create, Clone, Export, Clear** — full lifecycle management with all 256 slots visible
- **EZ_DLC_Install** compatible

### Save Conversion
- **e+ to GAFE** — convert Doubutsu no Mori e+ saves to Animal Crossing format
- **GAFE to e+** — convert Animal Crossing saves to e+ format
- **Full data transfer** — players, patterns, houses, villagers, stalk market, town items, acres, buried items, nook style

### Mail
- **10 Letter Slots** — read-only viewer with sender, attached item, header, and body

### Tools
- **Slot Analyzer** — save file free-space breakdown across all regions

---

## Integrity

- **CRC32 validation** on open for all ACCF regions (player, town, buildings, extended, DLC)
- **16-bit additive checksum** for GameCube saves (GAFE and GAEJ)
- **Automatic CRC recalculation** on save
- **Save duplication** for GC saves (dual-copy format)
- **Deluxe-aware warnings** — DLC CRC mismatches on modded saves are flagged as expected rather than corruption
- **Japanese text encoding** — full hiragana/katakana support for e+ saves

---

## Quick Start

### Requirements

- Python 3.7+
- PyQt6
- Git (optional — for cloning; you can also download the ZIP)

### Install & Run

```bash
git clone https://github.com/imcynic/actoolkit-linux.git
cd actoolkit-linux
pip install PyQt6
python3 actoolkit.py
```

**No Git?** Click the green **Code** button on GitHub > **Download ZIP**, extract, and run.

**Windows?** Use `python -m pip install PyQt6` and `python actoolkit.py` in PowerShell.

Then **File > Open** and select your save file.

---

## Item Databases

| Database | Entries | Source |
|----------|---------|--------|
| ACCF Items | ~1,600 | `items.pas` (9 languages) |
| GC Items | 6,379 | `ac-decomp` + Nika's AC_Item_List |
| Deluxe Items | 131 | Revolution Forest Plus v1.1.2 |
| Vanilla Villagers | 210 | `pack.bin` NPC data |
| Deluxe Villagers | 244 | Deluxe mod `pack.bin` |
| GC Villagers | 311 | Nika's AC_Sender_List |
| GC Special NPCs | 33 | Nika's AC_Sender_List |

---

## Project Structure

```
actoolkit-linux/
  actoolkit.py          # Entry point
  save_handler.py       # Core binary I/O + CRC
  game_profiles.py      # Game detection + offset profiles
  items_db.py           # ACCF + GC item names (6,379 entries, 9 languages)
  gc_items_db.py        # GC item names (legacy)
  deluxe_items.py       # Deluxe mod items + villagers
  vanilla_npcs.py       # GC villager + special NPC name databases
  npc_data.py           # Villager species/personality/birthday
  eplus_converter.py    # Bidirectional e+ <-> GAFE save converter
  slot_analyzer.py      # Save file region usage analyzer
  gui/
    main_window.py      # Primary application window
    town_editor.py      # 80x80 tile map editor
    inventory_editor.py # Pockets, drawers, lost & found
    house_editor.py     # 3-floor house room editor
    npc_editor.py       # Villager roster manager
    pattern_editor.py   # Design pattern pixel editor
    museum_editor.py    # Fossil/fish/insect/art tracker
    stalk_editor.py     # Turnip price editor
    building_editor.py  # Building & sign placement
    acre_editor.py      # Terrain acre type editor
    grass_editor.py     # Grass wear visualizer
    face_editor.py      # Player appearance editor
    emotions_editor.py  # Emotion slot editor
    dlc_editor.py       # DLC BITM manager
    letter_viewer.py    # Mail viewer (read-only)
    item_selector.py    # Category-based item picker
    slot_analyzer_dialog.py # Save region analyzer UI
  references/             # Nika's AC_Item_List + AC_Sender_List
```

---

## Credits

Based on the original **ACToolkit** Delphi source. GC string encoding and item data from the [Animal Crossing decompilation project](https://github.com/practice-1/ac-decomp). GC item and NPC reference data contributed by Nika.

---

<div align="center">
<sub>Not affiliated with Nintendo. Animal Crossing is a trademark of Nintendo.</sub>
</div>

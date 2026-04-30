"""
NPC / Villager Editor Dialog for Animal Crossing: City Folk Save Editor.

Shows the 10 resident villager slots and allows editing of:
  - Character type (NPC ID from pack.bin database)
  - Personality override (Lazy, Jock, Cranky, Normal, Peppy, Snooty)
  - Catchphrase
  - Shirt, umbrella
  - Room contents: wallpaper, flooring, 11 furniture items, K.K. song

The save stores the NPC index plus per-villager overrides for personality,
catchphrase, equipped items, and house contents.  Template data (name,
species, birthday) comes from the pack.bin ROM database.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLabel, QLineEdit, QGroupBox,
    QAbstractItemView, QMessageBox, QWidget,
    QFormLayout, QComboBox, QTreeWidget, QTreeWidgetItem,
    QFileDialog, QScrollArea, QGridLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from save_handler import SaveHandler

# Try to import npc_data for pack.bin parsing
try:
    from npc_data import NpcDatabase, load_pack_bin, PERSONALITY_NAMES, SPECIES_NAMES
except ImportError:
    NpcDatabase = None

# Try to import villager data as fallback when pack.bin is not available
try:
    from vanilla_npcs import VANILLA_VILLAGERS, GC_VILLAGER_NAMES
except ImportError:
    VANILLA_VILLAGERS = {}
    GC_VILLAGER_NAMES = {}

try:
    from deluxe_items import DELUXE_VILLAGERS
except ImportError:
    DELUXE_VILLAGERS = {}

# Items database for translating item codes to names
try:
    from items_db import ITEMS
except ImportError:
    ITEMS = {}


# ---------------------------------------------------------------------------
# Personality colours
# ---------------------------------------------------------------------------

PERSONALITY_COLORS = {
    "Lazy":    QColor(200, 230, 255),   # Light blue
    "Jock":    QColor(255, 200, 200),   # Light red
    "Cranky":  QColor(220, 200, 255),   # Light purple
    "Normal":  QColor(200, 255, 200),   # Light green
    "Peppy":   QColor(255, 255, 180),   # Light yellow
    "Snooty":  QColor(255, 200, 240),   # Light pink
}

EMPTY_NPC_ID = 0xFFFF
EMPTY_ITEM = 0xFFF1

# Personality ID -> Name (must match npc_data.py)
_PERS_NAMES = {0: "Lazy", 1: "Jock", 2: "Cranky", 3: "Normal", 4: "Peppy", 5: "Snooty"}
_PERS_IDS = {v: k for k, v in _PERS_NAMES.items()}


def _personality_color(personality: str) -> QColor:
    return PERSONALITY_COLORS.get(personality, QColor(240, 240, 240))


def _item_name(code: int) -> str:
    """Return a human-readable name for an item code."""
    if code == EMPTY_ITEM or code == 0:
        return "(empty)"
    info = ITEMS.get(code)
    if info:
        return info.get("name_ea", f"0x{code:04X}")
    return f"0x{code:04X}"


# ---------------------------------------------------------------------------
# Item Picker Dialog
# ---------------------------------------------------------------------------

class _ItemPickerDialog(QDialog):
    """Small dialog wrapping ItemSelectorWidget for picking a single item."""

    def __init__(
        self,
        title: str = "Pick Item",
        current_code: int = EMPTY_ITEM,
        show_items: bool = True,
        show_furniture: bool = True,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.selected_code: Optional[int] = None

        layout = QVBoxLayout(self)

        try:
            from gui.item_selector import ItemSelectorWidget
        except ImportError:
            from item_selector import ItemSelectorWidget

        self._selector = ItemSelectorWidget(
            show_terrain=False,
            show_items=show_items,
            show_furniture=show_furniture,
            show_acres=False,
            show_dlc=True,
        )
        self._selector.item_double_clicked.connect(self._on_pick)
        layout.addWidget(self._selector, stretch=1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_pick = QPushButton("Select")
        btn_pick.clicked.connect(self._on_select)
        btn_clear = QPushButton("Clear (Empty)")
        btn_clear.clicked.connect(self._on_clear)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(btn_pick)
        btn_row.addWidget(btn_clear)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        self.resize(450, 550)

        # Pre-select current item
        if current_code != EMPTY_ITEM and current_code != 0:
            self._selector.select_by_code(current_code)

    def _on_pick(self, code: int):
        self.selected_code = code
        self.accept()

    def _on_select(self):
        code = self._selector.get_selected_code()
        if code is not None:
            self.selected_code = code
            self.accept()

    def _on_clear(self):
        self.selected_code = EMPTY_ITEM
        self.accept()


# ---------------------------------------------------------------------------
# Per-slot editable data
# ---------------------------------------------------------------------------

class _SlotData:
    """Working copy of all editable fields for one villager slot."""

    def __init__(self):
        self.personality: int = 0
        self.catchphrase: str = ""
        self.shirt: int = EMPTY_ITEM
        self.umbrella: int = EMPTY_ITEM
        self.wallpaper: int = EMPTY_ITEM
        self.carpet: int = EMPTY_ITEM
        self.kk_song: int = EMPTY_ITEM
        self.furniture: list[int] = [EMPTY_ITEM] * 11

    @staticmethod
    def from_save(handler: SaveHandler, slot: int) -> "_SlotData":
        """Read all editable villager fields from the save."""
        d = _SlotData()
        try:
            d.personality = handler.get_villager_personality(slot)
        except Exception:
            pass
        try:
            d.catchphrase = handler.get_villager_catchphrase(slot)
        except Exception:
            pass
        try:
            d.shirt = handler.get_villager_shirt(slot)
        except Exception:
            pass
        if handler.supports_villager_room():
            try:
                d.umbrella = handler.get_villager_umbrella(slot)
            except Exception:
                pass
            try:
                d.wallpaper = handler.get_villager_wallpaper(slot)
            except Exception:
                pass
            try:
                d.carpet = handler.get_villager_carpet(slot)
            except Exception:
                pass
            try:
                d.kk_song = handler.get_villager_kk_song(slot)
            except Exception:
                pass
            try:
                d.furniture = handler.get_villager_furniture(slot)
            except Exception:
                pass
        return d

    def write_to_save(self, handler: SaveHandler, slot: int) -> None:
        """Write all editable villager fields to the save."""
        handler.set_villager_personality(slot, self.personality)
        handler.set_villager_catchphrase(slot, self.catchphrase)
        handler.set_villager_shirt(slot, self.shirt)
        if handler.supports_villager_room():
            handler.set_villager_umbrella(slot, self.umbrella)
            handler.set_villager_wallpaper(slot, self.wallpaper)
            handler.set_villager_carpet(slot, self.carpet)
            handler.set_villager_kk_song(slot, self.kk_song)
            handler.set_villager_furniture(slot, self.furniture)


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class NpcEditorDialog(QDialog):
    """Dialog for viewing and editing town residents."""

    def __init__(
        self,
        save_handler: SaveHandler,
        npc_db: Optional[NpcDatabase] = None,
        is_deluxe: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.save_handler = save_handler
        self.npc_db = npc_db
        self.is_deluxe = is_deluxe
        self._supports_room = save_handler.supports_villager_room()
        self.setWindowTitle("Villager Editor")

        # Working copy of the 10 resident NPC IDs
        self.resident_ids: list[int] = list(save_handler.get_resident_ids())

        # Working copy of per-slot editable data
        count = len(self.resident_ids)
        self._slot_data: list[Optional[_SlotData]] = []
        for i in range(count):
            if self.resident_ids[i] != EMPTY_NPC_ID and self.resident_ids[i] != 0:
                self._slot_data.append(_SlotData.from_save(save_handler, i))
            else:
                self._slot_data.append(None)

        # Pack.bin entries pending write per slot — populated by _on_replace
        # when the user picks a new villager from the database.  On Apply
        # these entries' identity data (names, catchphrases, outfit) gets
        # written into the slot via SaveHandler.write_villager_template;
        # without this the game keeps rendering the previous resident
        # because v_id alone doesn't determine what the game displays.
        self._pending_replace: dict[int, object] = {}

        # Snapshot of original resident ids for visual change tracking.
        # Slots whose id differs from this baseline get a "*" indicator
        # in the resident table and contribute to the Apply button's
        # pending-change count, so the user has obvious feedback that
        # their Replace clicks actually registered.
        self._original_resident_ids: list[int] = list(self.resident_ids)

        self._current_slot = -1

        self._build_ui()
        self._populate_residents()
        self._populate_npc_tree()

        self.resize(1150, 750)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Left: resident table + editable details ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("Town Residents:"))

        self.resident_table = QTableWidget(10, 4)
        self.resident_table.setHorizontalHeaderLabels(
            ["Slot", "ID", "Name", "Personality"]
        )
        self.resident_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.resident_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.resident_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.resident_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.resident_table.verticalHeader().setVisible(False)
        self.resident_table.currentCellChanged.connect(self._on_resident_selected)
        left_layout.addWidget(self.resident_table, stretch=2)

        # --- Editable detail panel (scrollable) ---
        detail_group = QGroupBox("Villager Properties")
        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_inner = QWidget()
        detail_layout = QFormLayout(detail_inner)
        detail_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Read-only fields (from pack.bin)
        self.lbl_name = QLabel("-")
        self.lbl_species = QLabel("-")
        self.lbl_birthday = QLabel("-")
        detail_layout.addRow("Name:", self.lbl_name)
        detail_layout.addRow("Species:", self.lbl_species)
        detail_layout.addRow("Birthday:", self.lbl_birthday)

        # Editable: Personality
        self.cmb_personality = QComboBox()
        for pid in sorted(_PERS_NAMES.keys()):
            self.cmb_personality.addItem(_PERS_NAMES[pid])
        self.cmb_personality.currentIndexChanged.connect(self._on_personality_changed)
        detail_layout.addRow("Personality:", self.cmb_personality)

        # Editable: Catchphrase
        self.txt_catchphrase = QLineEdit()
        self.txt_catchphrase.setMaxLength(10)
        self.txt_catchphrase.setPlaceholderText("Max 10 characters")
        self.txt_catchphrase.editingFinished.connect(self._on_catchphrase_changed)
        detail_layout.addRow("Catchphrase:", self.txt_catchphrase)

        # Editable: Shirt
        self.btn_shirt = QPushButton("(empty)")
        self.btn_shirt.clicked.connect(lambda: self._pick_item("shirt", "Pick Shirt", True, False))
        detail_layout.addRow("Shirt:", self.btn_shirt)

        # Editable: Umbrella
        self.btn_umbrella = QPushButton("(empty)")
        self.btn_umbrella.clicked.connect(lambda: self._pick_item("umbrella", "Pick Umbrella", True, False))
        detail_layout.addRow("Umbrella:", self.btn_umbrella)

        # Editable: Wallpaper
        self.btn_wallpaper = QPushButton("(empty)")
        self.btn_wallpaper.clicked.connect(lambda: self._pick_item("wallpaper", "Pick Wallpaper", True, False))
        detail_layout.addRow("Wallpaper:", self.btn_wallpaper)

        # Editable: Flooring
        self.btn_carpet = QPushButton("(empty)")
        self.btn_carpet.clicked.connect(lambda: self._pick_item("carpet", "Pick Flooring", True, False))
        detail_layout.addRow("Flooring:", self.btn_carpet)

        # Editable: K.K. Song
        self.btn_kk_song = QPushButton("(empty)")
        self.btn_kk_song.clicked.connect(lambda: self._pick_item("kk_song", "Pick K.K. Song", True, False))
        detail_layout.addRow("K.K. Song:", self.btn_kk_song)

        # Editable: Furniture (11 slots)
        furn_group = QGroupBox("House Furniture (11 slots)")
        furn_layout = QGridLayout(furn_group)
        self._furn_buttons: list[QPushButton] = []
        for i in range(11):
            lbl = QLabel(f"#{i + 1}:")
            btn = QPushButton("(empty)")
            idx = i  # capture
            btn.clicked.connect(lambda checked, ii=idx: self._pick_furniture(ii))
            furn_layout.addWidget(lbl, i, 0)
            furn_layout.addWidget(btn, i, 1)
            self._furn_buttons.append(btn)
        detail_layout.addRow(furn_group)

        detail_scroll.setWidget(detail_inner)
        detail_group_layout = QVBoxLayout(detail_group)
        detail_group_layout.setContentsMargins(0, 0, 0, 0)
        detail_group_layout.addWidget(detail_scroll)
        left_layout.addWidget(detail_group, stretch=3)

        splitter.addWidget(left_widget)

        # --- Right: NPC browser + search ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Load pack.bin button (if no db loaded)
        if self.npc_db is None:
            load_row = QHBoxLayout()
            self.btn_load_pack = QPushButton("Load pack.bin...")
            self.btn_load_pack.setToolTip(
                "Load Npc/Normal/Setup/pack.bin from extracted game files"
            )
            self.btn_load_pack.clicked.connect(self._on_load_pack)
            load_row.addWidget(self.btn_load_pack)
            load_row.addStretch()
            right_layout.addLayout(load_row)

        right_layout.addWidget(QLabel("NPC Database:"))

        # Filter row
        filter_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name...")
        self.search_input.textChanged.connect(self._on_filter_changed)

        self.species_filter = QComboBox()
        self.species_filter.addItem("All Species")
        for sid in sorted(SPECIES_NAMES.keys()):
            self.species_filter.addItem(SPECIES_NAMES[sid])
        self.species_filter.currentTextChanged.connect(self._on_filter_changed)

        self.personality_filter = QComboBox()
        self.personality_filter.addItem("All Personalities")
        for pid in sorted(PERSONALITY_NAMES.keys()):
            self.personality_filter.addItem(PERSONALITY_NAMES[pid])
        self.personality_filter.currentTextChanged.connect(self._on_filter_changed)

        filter_row.addWidget(self.search_input, stretch=2)
        filter_row.addWidget(self.species_filter, stretch=1)
        filter_row.addWidget(self.personality_filter, stretch=1)
        right_layout.addLayout(filter_row)

        # NPC tree
        self.npc_tree = QTreeWidget()
        self.npc_tree.setHeaderLabels(["ID", "Name", "Species", "Personality"])
        self.npc_tree.setColumnWidth(0, 50)
        self.npc_tree.setColumnWidth(1, 120)
        self.npc_tree.setColumnWidth(2, 80)
        self.npc_tree.setAlternatingRowColors(True)
        self.npc_tree.setRootIsDecorated(False)
        self.npc_tree.setSortingEnabled(True)
        right_layout.addWidget(self.npc_tree, stretch=1)

        # Replace button
        btn_row = QHBoxLayout()
        self.btn_replace = QPushButton("Replace Selected Resident")
        self.btn_replace.setToolTip(
            "Replace the selected resident slot with the NPC selected in the tree"
        )
        self.btn_replace.clicked.connect(self._on_replace)
        self.btn_clear = QPushButton("Clear Slot")
        self.btn_clear.setToolTip("Set the selected slot to empty (0xFFFF)")
        self.btn_clear.clicked.connect(self._on_clear_slot)
        btn_row.addWidget(self.btn_replace)
        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch()
        right_layout.addLayout(btn_row)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter, stretch=1)

        # --- Bottom buttons ---
        bottom = QHBoxLayout()
        bottom.addStretch()
        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setMinimumWidth(140)
        self.btn_apply.clicked.connect(self._on_apply)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setMinimumWidth(90)
        btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(self.btn_apply)
        bottom.addWidget(btn_cancel)
        root.addLayout(bottom)

        # Status
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            "padding: 6px; font-weight: bold; color: #1a5;"
        )
        root.addWidget(self.status_label)

        # Disable editing widgets initially
        self._set_edit_enabled(False)
        self._update_apply_button()

    def _pending_change_count(self) -> int:
        """Return the number of resident slots whose ID differs from
        what's in the loaded save."""
        if len(self._original_resident_ids) != len(self.resident_ids):
            return 0
        return sum(
            1 for orig, curr in zip(self._original_resident_ids, self.resident_ids)
            if orig != curr
        )

    def _update_apply_button(self):
        """Reflect pending-change count in the Apply button label and
        window title so the user has obvious feedback that their
        Replace/Clear actions registered."""
        n = self._pending_change_count()
        if n == 0:
            self.btn_apply.setText("Apply")
            self.btn_apply.setStyleSheet("")
            self.setWindowTitle("Villager Editor")
        else:
            self.btn_apply.setText(f"Apply ({n} pending)")
            self.btn_apply.setStyleSheet("font-weight: bold;")
            self.setWindowTitle(f"Villager Editor — {n} unsaved change{'s' if n != 1 else ''}")

    def _set_edit_enabled(self, enabled: bool):
        """Enable or disable all editable widgets."""
        self.cmb_personality.setEnabled(enabled)
        self.txt_catchphrase.setEnabled(enabled)
        self.btn_shirt.setEnabled(enabled)
        self.btn_umbrella.setEnabled(enabled and self._supports_room)
        self.btn_wallpaper.setEnabled(enabled and self._supports_room)
        self.btn_carpet.setEnabled(enabled and self._supports_room)
        self.btn_kk_song.setEnabled(enabled and self._supports_room)
        for btn in self._furn_buttons:
            btn.setEnabled(enabled and self._supports_room)

    # ------------------------------------------------------------------
    # Resident table
    # ------------------------------------------------------------------

    def _populate_residents(self):
        self.resident_table.blockSignals(True)
        for slot in range(len(self.resident_ids)):
            npc_id = self.resident_ids[slot]
            entry = self._get_npc_entry(npc_id)

            # Slot number — prefix with "*" if this slot has a pending
            # change vs. what's currently in the save, so users have an
            # at-a-glance indicator that their Replace clicked through.
            changed = (
                slot < len(self._original_resident_ids)
                and self._original_resident_ids[slot] != npc_id
            )
            slot_label = f"* {slot}" if changed else str(slot)
            slot_item = QTableWidgetItem(slot_label)
            slot_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.resident_table.setItem(slot, 0, slot_item)

            # ID
            id_item = QTableWidgetItem(
                f"{npc_id}" if npc_id != EMPTY_NPC_ID else "---"
            )
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.resident_table.setItem(slot, 1, id_item)

            if entry is not None:
                # Use save personality override if available
                sd = self._slot_data[slot]
                pers_name = _PERS_NAMES.get(sd.personality, entry.personality) if sd else entry.personality
                name_item = QTableWidgetItem(entry.name_en)
                pers_item = QTableWidgetItem(pers_name)
                bg = _personality_color(pers_name)
                for item in (slot_item, id_item, name_item, pers_item):
                    item.setBackground(QBrush(bg))
            else:
                name_item = QTableWidgetItem(
                    "(empty)" if npc_id == EMPTY_NPC_ID else f"Unknown ({npc_id})"
                )
                pers_item = QTableWidgetItem("-")

            name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            pers_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.resident_table.setItem(slot, 2, name_item)
            self.resident_table.setItem(slot, 3, pers_item)

        self.resident_table.blockSignals(False)

    def _on_resident_selected(self, row: int, _col: int, _prev_row: int, _prev_col: int):
        if row < 0 or row >= len(self.resident_ids):
            return
        self._current_slot = row
        npc_id = self.resident_ids[row]
        entry = self._get_npc_entry(npc_id)
        self._show_details(entry, npc_id, row)

    def _show_details(self, entry, npc_id: int, slot: int = -1):
        """Populate the detail panel from NPC database + save data."""
        if entry is None or npc_id == EMPTY_NPC_ID:
            label = "(empty)" if npc_id == EMPTY_NPC_ID else f"Unknown NPC #{npc_id}"
            self.lbl_name.setText(label)
            self.lbl_species.setText("-")
            self.lbl_birthday.setText("-")
            self.cmb_personality.blockSignals(True)
            self.cmb_personality.setCurrentIndex(0)
            self.cmb_personality.blockSignals(False)
            self.txt_catchphrase.blockSignals(True)
            self.txt_catchphrase.clear()
            self.txt_catchphrase.blockSignals(False)
            self.btn_shirt.setText("(empty)")
            self.btn_umbrella.setText("(empty)")
            self.btn_wallpaper.setText("(empty)")
            self.btn_carpet.setText("(empty)")
            self.btn_kk_song.setText("(empty)")
            for btn in self._furn_buttons:
                btn.setText("(empty)")
            self._set_edit_enabled(False)
            return

        # Read-only fields from NPC database
        self.lbl_name.setText(
            f"{entry.name_en}  /  {entry.name_ja}"
            if entry.name_ja else entry.name_en
        )
        self.lbl_species.setText(entry.species)
        self.lbl_birthday.setText(entry.birthday_str or "-")

        # Editable fields from save data
        sd = self._slot_data[slot] if 0 <= slot < len(self._slot_data) else None
        if sd is None:
            self._set_edit_enabled(False)
            return

        self._set_edit_enabled(True)

        # Personality
        self.cmb_personality.blockSignals(True)
        pers_idx = max(0, min(sd.personality, 5))
        self.cmb_personality.setCurrentIndex(pers_idx)
        self.cmb_personality.blockSignals(False)

        # Catchphrase
        self.txt_catchphrase.blockSignals(True)
        self.txt_catchphrase.setText(sd.catchphrase)
        self.txt_catchphrase.blockSignals(False)

        # Item buttons
        self.btn_shirt.setText(_item_name(sd.shirt))
        self.btn_umbrella.setText(_item_name(sd.umbrella))
        self.btn_wallpaper.setText(_item_name(sd.wallpaper))
        self.btn_carpet.setText(_item_name(sd.carpet))
        self.btn_kk_song.setText(_item_name(sd.kk_song))

        # Furniture
        for i, btn in enumerate(self._furn_buttons):
            code = sd.furniture[i] if i < len(sd.furniture) else EMPTY_ITEM
            btn.setText(_item_name(code))

    # ------------------------------------------------------------------
    # Edit handlers
    # ------------------------------------------------------------------

    def _on_personality_changed(self, index: int):
        slot = self._current_slot
        if slot < 0 or slot >= len(self._slot_data):
            return
        sd = self._slot_data[slot]
        if sd is None:
            return
        sd.personality = index
        # Update the resident table to reflect new personality
        self._populate_residents()
        self.resident_table.setCurrentCell(slot, 0)
        self.status_label.setText(
            f"Slot {slot}: personality set to {_PERS_NAMES.get(index, '?')}"
        )

    def _on_catchphrase_changed(self):
        slot = self._current_slot
        if slot < 0 or slot >= len(self._slot_data):
            return
        sd = self._slot_data[slot]
        if sd is None:
            return
        sd.catchphrase = self.txt_catchphrase.text()[:10]

    def _pick_item(self, field: str, title: str, show_items: bool, show_furniture: bool):
        """Open item picker for a single-item field."""
        slot = self._current_slot
        if slot < 0 or slot >= len(self._slot_data):
            return
        sd = self._slot_data[slot]
        if sd is None:
            return

        current = getattr(sd, field, EMPTY_ITEM)
        dlg = _ItemPickerDialog(
            title=title,
            current_code=current,
            show_items=show_items,
            show_furniture=show_furniture,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_code is not None:
            setattr(sd, field, dlg.selected_code)
            # Update button text
            btn_map = {
                "shirt": self.btn_shirt,
                "umbrella": self.btn_umbrella,
                "wallpaper": self.btn_wallpaper,
                "carpet": self.btn_carpet,
                "kk_song": self.btn_kk_song,
            }
            btn = btn_map.get(field)
            if btn:
                btn.setText(_item_name(dlg.selected_code))
            self.status_label.setText(
                f"Slot {slot}: {field} set to {_item_name(dlg.selected_code)}"
            )

    def _pick_furniture(self, furn_idx: int):
        """Open item picker for a furniture slot."""
        slot = self._current_slot
        if slot < 0 or slot >= len(self._slot_data):
            return
        sd = self._slot_data[slot]
        if sd is None:
            return

        current = sd.furniture[furn_idx] if furn_idx < len(sd.furniture) else EMPTY_ITEM
        dlg = _ItemPickerDialog(
            title=f"Pick Furniture #{furn_idx + 1}",
            current_code=current,
            show_items=True,
            show_furniture=True,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_code is not None:
            while len(sd.furniture) <= furn_idx:
                sd.furniture.append(EMPTY_ITEM)
            sd.furniture[furn_idx] = dlg.selected_code
            self._furn_buttons[furn_idx].setText(_item_name(dlg.selected_code))
            self.status_label.setText(
                f"Slot {slot}: furniture #{furn_idx + 1} set to "
                f"{_item_name(dlg.selected_code)}"
            )

    # ------------------------------------------------------------------
    # NPC tree (browser)
    # ------------------------------------------------------------------

    def _get_all_entries(self):
        """Return all NPC entries from pack.bin or embedded fallback databases.

        Version-aware: vanilla saves only show IDs 0-209, Deluxe shows all.
        """
        if self.npc_db is not None:
            if self.is_deluxe:
                return list(self.npc_db.entries)
            # Vanilla save: only show vanilla villagers (IDs 0-209)
            return [e for e in self.npc_db.entries if not e.is_deluxe]
        # Fallback: use cached entries built from embedded databases
        if not hasattr(self, "_fallback_cache"):
            combined: dict[int, dict] = {}
            combined.update(VANILLA_VILLAGERS)
            if self.is_deluxe:
                combined.update(DELUXE_VILLAGERS)
            self._fallback_cache = [
                _FallbackNpcEntry(npc_id, data)
                for npc_id, data in sorted(combined.items())
            ] if combined else []
        return self._fallback_cache

    def _populate_npc_tree(self):
        self.npc_tree.clear()
        entries = self._get_all_entries()
        if entries:
            self._fill_tree(entries)

    def _fill_tree(self, entries):
        self.npc_tree.clear()
        self.npc_tree.setSortingEnabled(False)
        for entry in entries:
            item = QTreeWidgetItem([
                str(entry.index),
                entry.name_en,
                entry.species,
                entry.personality,
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, entry.index)
            bg = _personality_color(entry.personality)
            for col in range(4):
                item.setBackground(col, QBrush(bg))
            self.npc_tree.addTopLevelItem(item)
        self.npc_tree.setSortingEnabled(True)

    def _on_filter_changed(self):
        all_entries = self._get_all_entries()
        if not all_entries:
            return

        query = self.search_input.text().strip().lower()
        species = self.species_filter.currentText()
        personality = self.personality_filter.currentText()

        filtered = list(all_entries)

        if query:
            filtered = [
                e for e in filtered
                if any(query in n.lower() for n in e.names.values())
            ]
        if species != "All Species":
            filtered = [e for e in filtered if e.species == species]
        if personality != "All Personalities":
            filtered = [e for e in filtered if e.personality == personality]

        self._fill_tree(filtered)
        total = len(self._get_all_entries())
        self.status_label.setText(f"Showing {len(filtered)} of {total} NPCs")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_replace(self):
        # Get selected resident slot
        row = self.resident_table.currentRow()
        if row < 0 or row >= len(self.resident_ids):
            self.status_label.setText("Select a resident slot first.")
            return

        # Get selected NPC from tree
        current = self.npc_tree.currentItem()
        if current is None:
            self.status_label.setText("Select an NPC from the database.")
            return

        new_id = current.data(0, Qt.ItemDataRole.UserRole)
        if new_id is None:
            return

        entry = self._get_npc_entry(new_id)
        name = entry.name_en if entry else f"#{new_id}"

        self.resident_ids[row] = new_id

        # Remember the pack.bin entry so _on_apply can write the full
        # identity template (names + catchphrases + default outfit).
        # Only entries with raw_bytes (real pack.bin entries) qualify;
        # fallback entries from the embedded VANILLA_VILLAGERS dict
        # don't have the multi-language data we'd need.
        if entry is not None and getattr(entry, "raw_bytes", None):
            self._pending_replace[row] = entry
        else:
            self._pending_replace.pop(row, None)

        # Create slot data for the new villager (preserve save data if slot
        # was already occupied, otherwise create from NPC template defaults)
        if self._slot_data[row] is None:
            self._slot_data[row] = _SlotData()
        sd = self._slot_data[row]

        # Set personality from NPC template
        if entry:
            pers_id = _PERS_IDS.get(entry.personality, 0)
            sd.personality = pers_id
            sd.catchphrase = entry.catchphrase_en or ""
            sd.shirt = entry.shirt
            if hasattr(entry, "umbrella"):
                sd.umbrella = entry.umbrella
            if hasattr(entry, "wall"):
                sd.wallpaper = entry.wall
            if hasattr(entry, "floor"):
                sd.carpet = entry.floor
            if hasattr(entry, "kk_song"):
                sd.kk_song = entry.kk_song
            if hasattr(entry, "furniture") and entry.furniture:
                sd.furniture = list(entry.furniture)
                while len(sd.furniture) < 11:
                    sd.furniture.append(EMPTY_ITEM)

        self._populate_residents()
        self.resident_table.setCurrentCell(row, 0)
        self._show_details(entry, new_id, row)
        self._update_apply_button()
        self.status_label.setText(
            f"✓ Slot {row}: replaced with {name} (ID {new_id}) — "
            f"click Apply to commit, then File ▸ Save (Ctrl+S)"
        )

    def _on_clear_slot(self):
        row = self.resident_table.currentRow()
        if row < 0 or row >= len(self.resident_ids):
            self.status_label.setText("Select a resident slot first.")
            return

        self.resident_ids[row] = EMPTY_NPC_ID
        self._slot_data[row] = None
        self._pending_replace.pop(row, None)
        self._populate_residents()
        self.resident_table.setCurrentCell(row, 0)
        self._show_details(None, EMPTY_NPC_ID, row)
        self._update_apply_button()
        self.status_label.setText(f"✓ Slot {row}: cleared")

    def _on_load_pack(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open pack.bin", "", "Binary files (*.bin);;All files (*)"
        )
        if not path:
            return
        try:
            self.npc_db = load_pack_bin(path)
            # Invalidate fallback cache now that real data is loaded
            if hasattr(self, "_fallback_cache"):
                del self._fallback_cache
            self._populate_npc_tree()
            self._populate_residents()
            self.status_label.setText(
                f"Loaded {len(self.npc_db)} NPCs from {Path(path).name}"
            )
            # Hide the load button
            if hasattr(self, "btn_load_pack"):
                self.btn_load_pack.setVisible(False)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load pack.bin:\n{e}")

    def _on_apply(self):
        change_count = self._pending_change_count()
        try:
            # First, write any pending template replacements.  This zeros
            # the model block, writes v_id/v_id2, and copies all 8 names
            # + 10 catchphrases + default outfit + personality from the
            # pack.bin entry into the slot.  The game uses the slot-
            # internal name strings to render the villager, so without
            # this the game keeps showing the previous resident even
            # though v_id has been changed.
            for slot, entry in self._pending_replace.items():
                npc_id = self.resident_ids[slot]
                if npc_id == EMPTY_NPC_ID or npc_id == 0:
                    continue
                raw = getattr(entry, "raw_bytes", None)
                if not raw:
                    continue
                self.save_handler.write_villager_template(slot, npc_id, raw)

            # For non-replaced slots (or fallback-DB replacements without
            # raw_bytes), fall back to the legacy v_id-only writer which
            # zeros the model block but leaves the rest of the slot alone.
            written_slots = set(self._pending_replace.keys())
            for i, npc_id in enumerate(self.resident_ids):
                if i in written_slots:
                    continue
                self.save_handler.set_resident_id(i, npc_id)

            # Write per-slot editable data (personality, catchphrase,
            # shirt, etc.) on top of the template — this lets the user's
            # custom catchphrase/personality/etc. overwrite the
            # pack.bin defaults.
            for i, sd in enumerate(self._slot_data):
                if sd is not None and self.resident_ids[i] != EMPTY_NPC_ID:
                    sd.write_to_save(self.save_handler, i)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to write villager data:\n{e}")
            return

        # Confirmation dialog reminding the user to actually save the
        # file — Apply only updates the in-memory save; the changes
        # aren't persisted to disk until File ▸ Save.  Skipping this
        # final step was the most common source of "I changed villagers
        # but the game didn't change them" reports.
        if change_count > 0:
            QMessageBox.information(
                self,
                "Villager changes applied",
                f"Applied {change_count} villager change"
                f"{'s' if change_count != 1 else ''} to the in-memory save.\n\n"
                f"⚠ These are NOT yet written to disk.\n"
                f"Use File ▸ Save (Ctrl+S) in the main window to save the file.\n\n"
                f"After loading the save in your game, the new villagers will\n"
                f"arrive in the 'moving in' state (boxes in their houses)."
            )
        self.accept()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_npc_entry(self, npc_id: int):
        """Look up an NPC entry by index from the database or embedded fallback."""
        if npc_id == EMPTY_NPC_ID or npc_id == 0:
            return None
        if self.npc_db is not None and npc_id in self.npc_db:
            return self.npc_db[npc_id]
        # Fallback: build a minimal NpcEntry-like object from embedded databases
        # GC/e+ saves use entity IDs (0xE000+), check GC_VILLAGER_NAMES first
        if npc_id in GC_VILLAGER_NAMES:
            return _FallbackNpcEntry(npc_id, {"name_en": GC_VILLAGER_NAMES[npc_id]})
        if npc_id in VANILLA_VILLAGERS:
            return _FallbackNpcEntry(npc_id, VANILLA_VILLAGERS[npc_id])
        if npc_id in DELUXE_VILLAGERS:
            return _FallbackNpcEntry(npc_id, DELUXE_VILLAGERS[npc_id])
        return None


class _FallbackNpcEntry:
    """Minimal NpcEntry stand-in when pack.bin is not loaded."""

    def __init__(self, index: int, data: dict):
        self.index = index
        self.name_en = data.get("name_en", "")
        self.name_ja = data.get("name_ja", "")
        self.names = {
            "en": self.name_en,
            "ja": self.name_ja,
            "es_am": data.get("name_es_am", self.name_en),
            "es_eu": data.get("name_es_eu", self.name_en),
            "fr": data.get("name_fr", self.name_en),
            "it": data.get("name_it", self.name_en),
            "de": data.get("name_de", self.name_en),
            "kr": data.get("name_kr", self.name_en),
        }
        self.species = data.get("species", "Unknown")
        self.personality = data.get("personality", "Unknown")
        self.birth_month = data.get("birth_month", 0)
        self.birth_day = data.get("birth_day", 0)
        self.catchphrase_en = data.get("catchphrase_en", "")
        self.catchphrases = {"en_us": self.catchphrase_en}
        self.shirt = data.get("shirt", 0xFFF1)
        self.umbrella = data.get("umbrella", 0xFFF1)
        self.wall = data.get("wall", 0xFFF1)
        self.floor = data.get("floor", 0xFFF1)
        self.kk_song = data.get("kk_song", 0xFFF1)
        self.furniture = data.get("furniture", [])
        self.is_starter = data.get("is_starter", False)
        self.is_deluxe = index >= 210

    @property
    def birthday_str(self) -> str:
        if self.birth_month == 0 and self.birth_day == 0:
            return ""
        return f"{self.birth_month}/{self.birth_day}"

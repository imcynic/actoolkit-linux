"""
NPC / Villager Editor Dialog for Animal Crossing: City Folk Save Editor.

Shows the 10 resident villager slots and their details (species, personality,
birthday, catchphrase, furniture).  Allows swapping villagers by selecting
from the full NPC database (pack.bin).

The save stores only the NPC index (u16) per slot.  All other villager data
(name, species, personality, etc.) comes from the pack.bin ROM database.
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
    QFileDialog,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from save_handler import SaveHandler

# Try to import npc_data for pack.bin parsing
try:
    from npc_data import NpcDatabase, NpcEntry, load_pack_bin, PERSONALITY_NAMES, SPECIES_NAMES
except ImportError:
    NpcDatabase = None

# Try to import deluxe villager data as fallback
try:
    from deluxe_items import DELUXE_VILLAGERS
except ImportError:
    DELUXE_VILLAGERS = {}


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


def _personality_color(personality: str) -> QColor:
    return PERSONALITY_COLORS.get(personality, QColor(240, 240, 240))


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class NpcEditorDialog(QDialog):
    """Dialog for viewing and editing town residents."""

    def __init__(
        self,
        save_handler: SaveHandler,
        npc_db: Optional[NpcDatabase] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.save_handler = save_handler
        self.npc_db = npc_db
        self.setWindowTitle("Villager Editor")

        # Working copy of the 10 resident NPC IDs
        self.resident_ids: list[int] = list(save_handler.get_resident_ids())

        self._build_ui()
        self._populate_residents()
        self._populate_npc_tree()

        self.resize(1050, 680)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Left: resident table + details ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("Town Residents (10 slots):"))

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
        left_layout.addWidget(self.resident_table, stretch=1)

        # Detail panel
        detail_group = QGroupBox("Villager Details")
        detail_layout = QFormLayout(detail_group)

        self.lbl_name = QLabel("-")
        self.lbl_species = QLabel("-")
        self.lbl_personality = QLabel("-")
        self.lbl_birthday = QLabel("-")
        self.lbl_catchphrase = QLabel("-")
        self.lbl_shirt = QLabel("-")
        self.lbl_umbrella = QLabel("-")
        self.lbl_wallfloor = QLabel("-")
        self.lbl_kk_song = QLabel("-")
        self.lbl_starter = QLabel("-")

        detail_layout.addRow("Name:", self.lbl_name)
        detail_layout.addRow("Species:", self.lbl_species)
        detail_layout.addRow("Personality:", self.lbl_personality)
        detail_layout.addRow("Birthday:", self.lbl_birthday)
        detail_layout.addRow("Catchphrase:", self.lbl_catchphrase)
        detail_layout.addRow("Shirt:", self.lbl_shirt)
        detail_layout.addRow("Umbrella:", self.lbl_umbrella)
        detail_layout.addRow("Wall / Floor:", self.lbl_wallfloor)
        detail_layout.addRow("K.K. Song:", self.lbl_kk_song)
        detail_layout.addRow("Can be Starter:", self.lbl_starter)

        left_layout.addWidget(detail_group)
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
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        root.addWidget(splitter, stretch=1)

        # --- Bottom buttons ---
        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_apply = QPushButton("Apply")
        btn_apply.setMinimumWidth(90)
        btn_apply.clicked.connect(self._on_apply)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setMinimumWidth(90)
        btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(btn_apply)
        bottom.addWidget(btn_cancel)
        root.addLayout(bottom)

        # Status
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("padding: 4px; color: #666;")
        root.addWidget(self.status_label)

    # ------------------------------------------------------------------
    # Resident table
    # ------------------------------------------------------------------

    def _populate_residents(self):
        self.resident_table.blockSignals(True)
        for slot in range(10):
            npc_id = self.resident_ids[slot]
            entry = self._get_npc_entry(npc_id)

            # Slot number
            slot_item = QTableWidgetItem(str(slot))
            slot_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.resident_table.setItem(slot, 0, slot_item)

            # ID
            id_item = QTableWidgetItem(
                f"{npc_id}" if npc_id != EMPTY_NPC_ID else "---"
            )
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.resident_table.setItem(slot, 1, id_item)

            if entry is not None:
                name_item = QTableWidgetItem(entry.name_en)
                pers_item = QTableWidgetItem(entry.personality)
                bg = _personality_color(entry.personality)
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
        if row < 0 or row >= 10:
            return
        npc_id = self.resident_ids[row]
        entry = self._get_npc_entry(npc_id)
        self._show_details(entry, npc_id)

    def _show_details(self, entry: Optional[NpcEntry], npc_id: int):
        if entry is None:
            label = "(empty)" if npc_id == EMPTY_NPC_ID else f"Unknown NPC #{npc_id}"
            self.lbl_name.setText(label)
            for lbl in (self.lbl_species, self.lbl_personality, self.lbl_birthday,
                        self.lbl_catchphrase, self.lbl_shirt, self.lbl_umbrella,
                        self.lbl_wallfloor, self.lbl_kk_song, self.lbl_starter):
                lbl.setText("-")
            return

        self.lbl_name.setText(
            f"{entry.name_en}  /  {entry.name_ja}"
            if entry.name_ja else entry.name_en
        )
        self.lbl_species.setText(entry.species)
        self.lbl_personality.setText(entry.personality)
        self.lbl_birthday.setText(entry.birthday_str or "-")
        self.lbl_catchphrase.setText(
            f'"{entry.catchphrase_en}"'
            if entry.catchphrase_en else "-"
        )
        self.lbl_shirt.setText(f"0x{entry.shirt:04X}")
        self.lbl_umbrella.setText(f"0x{entry.umbrella:04X}")
        self.lbl_wallfloor.setText(f"0x{entry.wall:04X} / 0x{entry.floor:04X}")
        self.lbl_kk_song.setText(f"0x{entry.kk_song:04X}")
        self.lbl_starter.setText("Yes" if entry.is_starter else "No")

    # ------------------------------------------------------------------
    # NPC tree (browser)
    # ------------------------------------------------------------------

    def _get_all_entries(self):
        """Return all NPC entries from pack.bin or DELUXE_VILLAGERS fallback."""
        if self.npc_db is not None:
            return list(self.npc_db.entries)
        # Fallback: use cached entries built from embedded DELUXE_VILLAGERS
        if not hasattr(self, "_fallback_cache"):
            self._fallback_cache = [
                _FallbackNpcEntry(npc_id, data)
                for npc_id, data in sorted(DELUXE_VILLAGERS.items())
            ] if DELUXE_VILLAGERS else []
        return self._fallback_cache

    def _populate_npc_tree(self):
        self.npc_tree.clear()
        entries = self._get_all_entries()
        if entries:
            self._fill_tree(entries)

    def _fill_tree(self, entries: list[NpcEntry]):
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
        total = len(self.npc_db) if self.npc_db else len(DELUXE_VILLAGERS)
        self.status_label.setText(f"Showing {len(filtered)} of {total} NPCs")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_replace(self):
        # Get selected resident slot
        row = self.resident_table.currentRow()
        if row < 0 or row >= 10:
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
        self._populate_residents()
        self.resident_table.setCurrentCell(row, 0)
        self._show_details(entry, new_id)
        self.status_label.setText(f"Slot {row}: replaced with {name} (ID {new_id})")

    def _on_clear_slot(self):
        row = self.resident_table.currentRow()
        if row < 0 or row >= 10:
            self.status_label.setText("Select a resident slot first.")
            return

        self.resident_ids[row] = EMPTY_NPC_ID
        self._populate_residents()
        self.resident_table.setCurrentCell(row, 0)
        self._show_details(None, EMPTY_NPC_ID)
        self.status_label.setText(f"Slot {row}: cleared")

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
        try:
            self.save_handler.set_resident_ids(self.resident_ids)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to write villager data:\n{e}")
            return
        self.accept()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_npc_entry(self, npc_id: int) -> Optional[NpcEntry]:
        """Look up an NPC entry by index from the database or DELUXE_VILLAGERS fallback."""
        if npc_id == EMPTY_NPC_ID or npc_id == 0:
            return None
        if self.npc_db is not None and npc_id in self.npc_db:
            return self.npc_db[npc_id]
        # Fallback: build a minimal NpcEntry-like object from DELUXE_VILLAGERS
        if npc_id in DELUXE_VILLAGERS:
            return _FallbackNpcEntry(npc_id, DELUXE_VILLAGERS[npc_id])
        return None


class _FallbackNpcEntry:
    """Minimal NpcEntry stand-in when pack.bin is not loaded."""

    def __init__(self, index: int, data: dict):
        self.index = index
        self.name_en = data.get("name_en", "")
        self.name_ja = data.get("name_ja", "")
        self.names = {"en": self.name_en, "ja": self.name_ja}
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
        self.is_deluxe = True

    @property
    def birthday_str(self) -> str:
        if self.birth_month == 0 and self.birth_day == 0:
            return ""
        return f"{self.birth_month}/{self.birth_day}"

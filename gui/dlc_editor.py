"""
DLC (Downloadable Content) Editor Dialog for Animal Crossing: City Folk Save Editor.

Allows viewing, editing, importing, and clearing DLC items stored in the save
file's 256-slot BITM region.  Supports custom DLC creation based on the
aibohack.com documentation and EZ_DLC_Install format.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLabel, QLineEdit, QSpinBox,
    QGroupBox, QFormLayout, QWidget, QMessageBox,
    QFileDialog, QAbstractItemView, QComboBox,
)
from PyQt6.QtCore import Qt

from save_handler import SaveHandler

DLC_SLOT_COUNT = 256

# Item class descriptions (from EZ_DLC_Install reverse engineering)
ITEM_CLASSES = {
    0: "Furniture",
    1: "Wallpaper",
    2: "Carpet",
    3: "Clothing (Top)",
    4: "Clothing (Hat)",
    5: "Clothing (Accessory)",
    6: "Stationery",
}

LANG_NAMES = (
    "Japanese", "English (US)", "Spanish (US)", "French (US)",
    "English (EU)", "German", "Italian", "Spanish (EU)", "French (EU)", "Korean",
)
LANG_KEYS = (
    "ja", "en_us", "es_us", "fra_us",
    "en_eu", "de", "it", "es_eu", "fra_eu", "kr",
)


class DlcEditorDialog(QDialog):
    """Dialog for viewing and editing DLC items in the save file."""

    def __init__(
        self,
        save_handler: SaveHandler,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.save_handler = save_handler
        self.setWindowTitle("DLC Editor")

        self._dirty = False
        self._current_slot = -1

        self._build_ui()
        self._populate_table()

        self.resize(900, 620)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)

        # Summary bar
        summary_row = QHBoxLayout()
        self.summary_label = QLabel("DLC Items: 0 / 256")
        self.summary_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        summary_row.addWidget(self.summary_label)
        summary_row.addStretch()
        root.addLayout(summary_row)

        # Splitter: table on left, detail on right
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Left: DLC slot table ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.dlc_table = QTableWidget(0, 4)
        self.dlc_table.setHorizontalHeaderLabels(["Slot", "Name", "Price", "Item Code"])
        self.dlc_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.dlc_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.dlc_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.dlc_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.dlc_table.currentCellChanged.connect(self._on_table_selection)
        left_layout.addWidget(self.dlc_table)

        # Table action buttons
        table_btns = QHBoxLayout()
        self.btn_import = QPushButton("Import DLC...")
        self.btn_import.setToolTip("Import a raw DLC .bin file into an empty slot")
        self.btn_import.clicked.connect(self._on_import)
        table_btns.addWidget(self.btn_import)

        self.btn_clear = QPushButton("Clear Slot")
        self.btn_clear.setToolTip("Remove the selected DLC item")
        self.btn_clear.clicked.connect(self._on_clear_slot)
        self.btn_clear.setEnabled(False)
        table_btns.addWidget(self.btn_clear)

        table_btns.addStretch()
        left_layout.addLayout(table_btns)

        splitter.addWidget(left_widget)

        # --- Right: Detail panel ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Item info group
        info_group = QGroupBox("Item Details")
        info_form = QFormLayout(info_group)

        self.lbl_slot = QLabel("-")
        info_form.addRow("Slot:", self.lbl_slot)

        self.lbl_base_id = QLabel("-")
        info_form.addRow("Base ID:", self.lbl_base_id)

        self.lbl_item_code = QLabel("-")
        info_form.addRow("Item Code:", self.lbl_item_code)

        self.lbl_class = QLabel("-")
        info_form.addRow("Class:", self.lbl_class)

        self.lbl_drop_model = QLabel("-")
        info_form.addRow("Drop Model:", self.lbl_drop_model)

        right_layout.addWidget(info_group)

        # Editable fields group
        edit_group = QGroupBox("Editable Fields")
        edit_form = QFormLayout(edit_group)

        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(16)
        self.name_edit.setPlaceholderText("(no name)")
        self.name_edit.setEnabled(False)
        edit_form.addRow("Name (EN):", self.name_edit)

        self.price_spin = QSpinBox()
        self.price_spin.setRange(0, 999_999)
        self.price_spin.setSuffix(" Bells")
        self.price_spin.setEnabled(False)
        edit_form.addRow("Price:", self.price_spin)

        self.btn_save_edits = QPushButton("Save Changes")
        self.btn_save_edits.setEnabled(False)
        self.btn_save_edits.clicked.connect(self._on_save_edits)
        edit_form.addRow("", self.btn_save_edits)

        right_layout.addWidget(edit_group)

        # All names group
        names_group = QGroupBox("Localized Names")
        names_layout = QVBoxLayout(names_group)

        self.name_labels: list[QLabel] = []
        for i, lang_name in enumerate(LANG_NAMES):
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{lang_name}:"))
            lbl = QLabel("-")
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(lbl, stretch=1)
            names_layout.addLayout(row)
            self.name_labels.append(lbl)

        right_layout.addWidget(names_group)

        # Catalog patch button
        catalog_group = QGroupBox("Catalog")
        catalog_layout = QHBoxLayout(catalog_group)

        self.player_combo = QComboBox()
        for p in range(4):
            if self.save_handler.player_exists(p):
                name = self.save_handler.get_player_name(p)
                label = f"Player {p + 1}: {name}" if name else f"Player {p + 1}"
                self.player_combo.addItem(label, userData=p)
        catalog_layout.addWidget(self.player_combo)

        self.btn_patch_catalog = QPushButton("Patch Catalog for All DLC")
        self.btn_patch_catalog.setToolTip(
            "Mark all valid DLC items as owned in the selected player's catalog"
        )
        self.btn_patch_catalog.clicked.connect(self._on_patch_catalog)
        catalog_layout.addWidget(self.btn_patch_catalog)

        right_layout.addWidget(catalog_group)

        right_layout.addStretch()

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter, stretch=1)

        # --- Bottom buttons ---
        bottom = QHBoxLayout()
        bottom.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setMinimumWidth(90)
        btn_close.clicked.connect(self._on_close)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

        # Status
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("padding: 4px; color: #666;")
        root.addWidget(self.status_label)

    # ------------------------------------------------------------------
    # Table population
    # ------------------------------------------------------------------

    def _populate_table(self):
        """Fill the table with all valid DLC slots."""
        try:
            all_dlc = self.save_handler.get_all_dlc()
        except Exception as e:
            self.summary_label.setText("DLC Items: error reading")
            self.status_label.setText(f"Error loading DLC data: {e}")
            return

        self.dlc_table.setRowCount(len(all_dlc))
        for row, entry in enumerate(all_dlc):
            slot_item = QTableWidgetItem(str(entry["slot"]))
            slot_item.setData(Qt.ItemDataRole.UserRole, entry["slot"])
            slot_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.dlc_table.setItem(row, 0, slot_item)

            name_item = QTableWidgetItem(entry.get("name_en", ""))
            self.dlc_table.setItem(row, 1, name_item)

            price_item = QTableWidgetItem(f"{entry.get('price', 0):,}")
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.dlc_table.setItem(row, 2, price_item)

            code_item = QTableWidgetItem(f"0x{entry.get('item_code', 0):04X}")
            code_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.dlc_table.setItem(row, 3, code_item)

        count = len(all_dlc)
        self.summary_label.setText(f"DLC Items: {count} / {DLC_SLOT_COUNT}")
        self.status_label.setText(f"Loaded {count} DLC items.")

    # ------------------------------------------------------------------
    # Detail panel
    # ------------------------------------------------------------------

    def _show_detail(self, slot: int):
        """Display details for the given DLC slot."""
        if not isinstance(slot, int) or not 0 <= slot < DLC_SLOT_COUNT:
            self._clear_detail()
            return
        self._current_slot = slot

        try:
            summary = self.save_handler.get_dlc_summary(slot)
        except Exception as e:
            self._clear_detail()
            self.status_label.setText(f"Error reading slot {slot}: {e}")
            return

        if summary is None:
            self._clear_detail()
            return

        self.lbl_slot.setText(str(slot))
        self.lbl_base_id.setText(f"0x{summary['base_id']:04X}")
        self.lbl_item_code.setText(f"0x{summary['item_code']:04X}")

        class_idx = summary.get("class_idx", summary.get("class_index", 0))
        class_name = ITEM_CLASSES.get(class_idx, f"Unknown ({class_idx})")
        self.lbl_class.setText(f"{class_idx} - {class_name}")

        self.lbl_drop_model.setText(str(summary.get("drop_model", 0)))

        # Editable fields
        self.name_edit.setEnabled(True)
        self.name_edit.setText(summary.get("name_en", ""))
        self.price_spin.setEnabled(True)
        self.price_spin.setValue(summary.get("price", 0))
        self.btn_save_edits.setEnabled(True)
        self.btn_clear.setEnabled(True)

        # Localized names
        try:
            names = self.save_handler.get_dlc_names(slot)
        except Exception:
            names = {}
        for i, key in enumerate(LANG_KEYS):
            text = names.get(key, "")
            self.name_labels[i].setText(text if text else "-")

    def _clear_detail(self):
        """Reset the detail panel."""
        self._current_slot = -1
        self.lbl_slot.setText("-")
        self.lbl_base_id.setText("-")
        self.lbl_item_code.setText("-")
        self.lbl_class.setText("-")
        self.lbl_drop_model.setText("-")
        self.name_edit.setEnabled(False)
        self.name_edit.clear()
        self.price_spin.setEnabled(False)
        self.price_spin.setValue(0)
        self.btn_save_edits.setEnabled(False)
        self.btn_clear.setEnabled(False)
        for lbl in self.name_labels:
            lbl.setText("-")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_table_selection(self, row: int, _col: int, _prev_row: int, _prev_col: int):
        if row < 0:
            self._clear_detail()
            return
        item = self.dlc_table.item(row, 0)
        if item is None:
            self._clear_detail()
            return
        slot = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(slot, int) or not 0 <= slot < DLC_SLOT_COUNT:
            self._clear_detail()
            return
        self._show_detail(slot)

    def _on_save_edits(self):
        """Write edited name and price to the current slot."""
        slot = self._current_slot
        if slot < 0:
            return

        try:
            new_name = self.name_edit.text()
            new_price = self.price_spin.value()
            self.save_handler.set_dlc_name(slot, new_name, lang="en_us")
            self.save_handler.set_dlc_price(slot, new_price)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save edits:\n{e}")
            return

        self._dirty = True
        self._populate_table()
        self.status_label.setText(f"Slot {slot} updated: {new_name}, {new_price:,} Bells")

    def _on_clear_slot(self):
        """Clear the selected DLC slot."""
        slot = self._current_slot
        if slot < 0:
            return

        name = self.name_edit.text() or f"Slot {slot}"
        reply = QMessageBox.question(
            self,
            "Clear DLC Slot",
            f"Remove DLC item \"{name}\" from slot {slot}?\n\n"
            "This cannot be undone (until you close without saving).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.save_handler.clear_dlc_slot(slot)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to clear slot:\n{e}")
            return

        self._dirty = True
        self._clear_detail()
        self._populate_table()
        self.status_label.setText(f"Slot {slot} cleared.")

    def _on_import(self):
        """Import a raw DLC .bin file into an empty slot."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import DLC File",
            "",
            "DLC Files (*.bin *.dlc *.bitm);;All Files (*)",
        )
        if not path:
            return

        # Guard against reading excessively large files
        import os
        try:
            file_size = os.path.getsize(path)
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Cannot read file:\n{e}")
            return
        max_size = 0x2000  # DLC_SLOT_SIZE
        if file_size > max_size * 2:
            QMessageBox.warning(
                self, "File Too Large",
                f"File is {file_size:,} bytes, expected at most {max_size:,}.\n"
                "This does not appear to be a valid DLC file.",
            )
            return

        slot = self.save_handler.find_empty_dlc_slot()
        if slot < 0:
            QMessageBox.warning(
                self, "No Empty Slots",
                "All 256 DLC slots are occupied. Clear a slot first.",
            )
            return

        try:
            name = self.save_handler.import_dlc_file(slot, path)
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to import DLC:\n{e}")
            return

        self._dirty = True
        self._populate_table()
        self.status_label.setText(f"Imported \"{name}\" into slot {slot}.")

    def _on_patch_catalog(self):
        """Patch the selected player's catalog to include all DLC items."""
        idx = self.player_combo.currentIndex()
        if idx < 0:
            return
        player = self.player_combo.itemData(idx)
        if player is None:
            return

        reply = QMessageBox.question(
            self,
            "Patch Catalog",
            f"Mark all valid DLC items as owned in Player {player + 1}'s catalog?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            count = self.save_handler.patch_catalog_for_dlc(player)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to patch catalog:\n{e}")
            return

        self._dirty = True
        self.status_label.setText(
            f"Patched {count} DLC items into Player {player + 1}'s catalog."
        )

    def _on_close(self):
        if self._dirty:
            self.accept()
        else:
            self.reject()

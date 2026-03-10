"""
DLC (Downloadable Content) Editor Dialog for Animal Crossing: City Folk Save Editor.

Shows all 256 DLC slots (free and used), allows viewing, editing, importing,
cloning, and creating HDLC (Hacked DLC) items.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLabel, QLineEdit, QSpinBox,
    QGroupBox, QFormLayout, QWidget, QMessageBox,
    QFileDialog, QAbstractItemView, QComboBox,
    QInputDialog,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from save_handler import SaveHandler

DLC_SLOT_COUNT = 256

ITEM_CLASSES = {
    0: "Furniture",
    1: "Wallpaper",
    2: "Carpet",
    3: "Clothing (Top)",
    4: "Clothing (Hat)",
    5: "Clothing (Accessory)",
    6: "Stationery",
}

SUB_IDS = {
    0x0000: "Furniture (General)",
    0x0133: "Wallpaper",
    0x0134: "Carpet",
    0x0138: "Clothing",
    0x0139: "Umbrella",
    0x013A: "Headgear (Hat)",
    0x013B: "Headgear (Helmet)",
    0x013C: "Accessory",
    0x0166: "Furniture (Event)",
}

LANG_NAMES = (
    "Japanese", "English (US)", "Spanish (US)", "French (US)",
    "English (EU)", "German", "Italian", "Spanish (EU)", "French (EU)", "Korean",
)
LANG_KEYS = (
    "ja", "en_us", "es_us", "fra_us",
    "en_eu", "de", "it", "es_eu", "fra_eu", "kr",
)

_CLR_FREE = QColor("#60C060")
_CLR_USED = QColor("#E0E8E8")
_CLR_FREE_BG = QColor("#1A2E1A")


class DlcEditorDialog(QDialog):
    """Dialog for viewing and editing DLC items in all 256 slots."""

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

        self.resize(960, 660)

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

        # --- Left: DLC slot table (all 256 slots) ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.dlc_table = QTableWidget(0, 4)
        self.dlc_table.setHorizontalHeaderLabels(["Slot", "Status", "Name", "Item Code"])
        self.dlc_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        for col in (0, 1, 3):
            self.dlc_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
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
        self.btn_import = QPushButton("Import...")
        self.btn_import.setToolTip("Import a DLC .bin file into the selected slot")
        self.btn_import.clicked.connect(self._on_import)
        table_btns.addWidget(self.btn_import)

        self.btn_clone = QPushButton("Clone...")
        self.btn_clone.setToolTip("Copy this DLC item into a free slot")
        self.btn_clone.clicked.connect(self._on_clone)
        self.btn_clone.setEnabled(False)
        table_btns.addWidget(self.btn_clone)

        self.btn_create = QPushButton("Create HDLC...")
        self.btn_create.setToolTip("Create a new Hacked DLC item in the selected free slot")
        self.btn_create.clicked.connect(self._on_create_hdlc)
        table_btns.addWidget(self.btn_create)

        self.btn_export = QPushButton("Export...")
        self.btn_export.setToolTip("Export this DLC slot to a .bin file")
        self.btn_export.clicked.connect(self._on_export)
        self.btn_export.setEnabled(False)
        table_btns.addWidget(self.btn_export)

        self.btn_clear = QPushButton("Clear")
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

        self.lbl_status = QLabel("-")
        info_form.addRow("Status:", self.lbl_status)

        self.lbl_base_id = QLabel("-")
        info_form.addRow("Base ID:", self.lbl_base_id)

        self.lbl_item_code = QLabel("-")
        info_form.addRow("Item Code:", self.lbl_item_code)

        self.lbl_class = QLabel("-")
        info_form.addRow("Class:", self.lbl_class)

        self.lbl_sub_id = QLabel("-")
        info_form.addRow("Category:", self.lbl_sub_id)

        self.lbl_drop_model = QLabel("-")
        info_form.addRow("Drop Model:", self.lbl_drop_model)

        self.lbl_price = QLabel("-")
        info_form.addRow("Price:", self.lbl_price)

        right_layout.addWidget(info_group)

        # Editable fields group
        edit_group = QGroupBox("Edit")
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

        # Localized names group
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

        # Catalog patch
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
        self.btn_patch_catalog.clicked.connect(self._on_patch_catalog)
        catalog_layout.addWidget(self.btn_patch_catalog)

        right_layout.addWidget(catalog_group)

        right_layout.addStretch()

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter, stretch=1)

        # --- Bottom ---
        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setMinimumWidth(90)
        btn_close.clicked.connect(self._on_close)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("padding: 4px; color: #8AACAC;")
        root.addWidget(self.status_label)

    # ------------------------------------------------------------------
    # Table population — all 256 slots
    # ------------------------------------------------------------------

    def _populate_table(self):
        """Fill the table with all 256 DLC slots."""
        self.dlc_table.setRowCount(DLC_SLOT_COUNT)
        used_count = 0

        for slot in range(DLC_SLOT_COUNT):
            valid = False
            try:
                valid = self.save_handler.is_dlc_slot_valid(slot)
            except Exception:
                pass

            # Slot number
            slot_item = QTableWidgetItem(str(slot))
            slot_item.setData(Qt.ItemDataRole.UserRole, slot)
            slot_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            if valid:
                used_count += 1
                status_item = QTableWidgetItem("Used")
                try:
                    name_en = self.save_handler.get_dlc_name(slot, "en_us")
                    item_code = self.save_handler.get_dlc_item_code(slot)
                except Exception:
                    name_en = "(read error)"
                    item_code = 0
                name_item = QTableWidgetItem(name_en)
                code_item = QTableWidgetItem(f"0x{item_code:04X}")
                code_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                status_item = QTableWidgetItem("Free")
                status_item.setForeground(QBrush(_CLR_FREE))
                name_item = QTableWidgetItem("")
                code_item = QTableWidgetItem("")

                for col_item in (slot_item, status_item, name_item, code_item):
                    col_item.setBackground(QBrush(_CLR_FREE_BG))

            self.dlc_table.setItem(slot, 0, slot_item)
            self.dlc_table.setItem(slot, 1, status_item)
            self.dlc_table.setItem(slot, 2, name_item)
            self.dlc_table.setItem(slot, 3, code_item)

        free_count = DLC_SLOT_COUNT - used_count
        self.summary_label.setText(
            f"DLC Items: {used_count} used, {free_count} free / {DLC_SLOT_COUNT} total"
        )
        self.status_label.setText(f"Loaded {used_count} DLC items, {free_count} slots available.")

    # ------------------------------------------------------------------
    # Detail panel
    # ------------------------------------------------------------------

    def _show_detail(self, slot: int):
        if not isinstance(slot, int) or not 0 <= slot < DLC_SLOT_COUNT:
            self._clear_detail()
            return
        self._current_slot = slot

        valid = self.save_handler.is_dlc_slot_valid(slot)

        self.lbl_slot.setText(str(slot))

        if not valid:
            self.lbl_status.setText('<span style="color: #60C060;">Free</span>')
            self.lbl_base_id.setText("-")
            self.lbl_item_code.setText("-")
            self.lbl_class.setText("-")
            self.lbl_sub_id.setText("-")
            self.lbl_drop_model.setText("-")
            self.lbl_price.setText("-")
            self.name_edit.setEnabled(False)
            self.name_edit.clear()
            self.price_spin.setEnabled(False)
            self.price_spin.setValue(0)
            self.btn_save_edits.setEnabled(False)
            self.btn_clear.setEnabled(False)
            self.btn_clone.setEnabled(False)
            self.btn_export.setEnabled(False)
            for lbl in self.name_labels:
                lbl.setText("-")
            return

        try:
            summary = self.save_handler.get_dlc_summary(slot)
        except Exception as e:
            self._clear_detail()
            self.status_label.setText(f"Error reading slot {slot}: {e}")
            return

        if summary is None:
            self._clear_detail()
            return

        self.lbl_status.setText("Used")
        self.lbl_base_id.setText(f"0x{summary['base_id']:04X}")
        self.lbl_item_code.setText(f"0x{summary['item_code']:04X}")

        class_idx = summary.get("class_idx", 0)
        class_name = ITEM_CLASSES.get(class_idx, f"Unknown ({class_idx})")
        self.lbl_class.setText(f"{class_idx} - {class_name}")

        # Read sub_id for category display
        try:
            sub_id = self.save_handler.read_u16(
                self.save_handler._dlc_slot_offset(slot) + 0x0A
            )
            sub_name = SUB_IDS.get(sub_id, f"Unknown (0x{sub_id:04X})")
            self.lbl_sub_id.setText(f"0x{sub_id:04X} - {sub_name}")
        except Exception:
            self.lbl_sub_id.setText("-")

        self.lbl_drop_model.setText(str(summary.get("drop_model", 0)))
        self.lbl_price.setText(f"{summary.get('price', 0):,} Bells")

        # Editable fields
        self.name_edit.setEnabled(True)
        self.name_edit.setText(summary.get("name_en", ""))
        self.price_spin.setEnabled(True)
        self.price_spin.setValue(summary.get("price", 0))
        self.btn_save_edits.setEnabled(True)
        self.btn_clear.setEnabled(True)
        self.btn_clone.setEnabled(True)
        self.btn_export.setEnabled(True)

        # Localized names
        try:
            names = self.save_handler.get_dlc_names(slot)
        except Exception:
            names = {}
        for i, key in enumerate(LANG_KEYS):
            text = names.get(key, "")
            self.name_labels[i].setText(text if text else "-")

    def _clear_detail(self):
        self._current_slot = -1
        self.lbl_slot.setText("-")
        self.lbl_status.setText("-")
        self.lbl_base_id.setText("-")
        self.lbl_item_code.setText("-")
        self.lbl_class.setText("-")
        self.lbl_sub_id.setText("-")
        self.lbl_drop_model.setText("-")
        self.lbl_price.setText("-")
        self.name_edit.setEnabled(False)
        self.name_edit.clear()
        self.price_spin.setEnabled(False)
        self.price_spin.setValue(0)
        self.btn_save_edits.setEnabled(False)
        self.btn_clear.setEnabled(False)
        self.btn_clone.setEnabled(False)
        self.btn_export.setEnabled(False)
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
        self._select_slot(slot)
        self.status_label.setText(f"Slot {slot} updated: {new_name}, {new_price:,} Bells")

    def _on_clear_slot(self):
        slot = self._current_slot
        if slot < 0:
            return
        name = self.name_edit.text() or f"Slot {slot}"
        reply = QMessageBox.question(
            self, "Clear DLC Slot",
            f'Remove DLC item "{name}" from slot {slot}?',
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
        self._populate_table()
        self._select_slot(slot)
        self.status_label.setText(f"Slot {slot} cleared.")

    def _on_import(self):
        """Import a raw DLC .bin file into the selected or first free slot."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import DLC File", "",
            "DLC Files (*.bin *.dlc *.bitm);;All Files (*)",
        )
        if not path:
            return

        import os
        try:
            file_size = os.path.getsize(path)
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Cannot read file:\n{e}")
            return
        if file_size > 0x2000 * 2:
            QMessageBox.warning(
                self, "File Too Large",
                f"File is {file_size:,} bytes, expected at most 8,192.",
            )
            return

        # Use selected slot if free, otherwise find first free
        target = self._current_slot
        if target < 0 or self.save_handler.is_dlc_slot_valid(target):
            target = self.save_handler.find_empty_dlc_slot()
        if target < 0:
            QMessageBox.warning(self, "No Empty Slots", "All 256 DLC slots are occupied.")
            return

        try:
            name = self.save_handler.import_dlc_file(target, path)
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to import DLC:\n{e}")
            return

        self._dirty = True
        self._populate_table()
        self._select_slot(target)
        self.status_label.setText(f'Imported "{name}" into slot {target}.')

    def _on_export(self):
        """Export the selected DLC slot to a .bin file."""
        slot = self._current_slot
        if slot < 0 or not self.save_handler.is_dlc_slot_valid(slot):
            return
        try:
            name_en = self.save_handler.get_dlc_name(slot, "en_us") or f"slot_{slot}"
        except Exception:
            name_en = f"slot_{slot}"
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in name_en).strip()
        path, _ = QFileDialog.getSaveFileName(
            self, "Export DLC Slot", f"{safe_name}.bin",
            "DLC Files (*.bin);;All Files (*)",
        )
        if not path:
            return
        try:
            raw = self.save_handler.read_dlc_slot_raw(slot)
            with open(path, "wb") as f:
                f.write(raw)
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export:\n{e}")
            return
        self.status_label.setText(f"Exported slot {slot} to {path}")

    def _on_clone(self):
        """Clone the selected DLC item into a free slot."""
        src = self._current_slot
        if src < 0 or not self.save_handler.is_dlc_slot_valid(src):
            return

        dst = self.save_handler.find_empty_dlc_slot()
        if dst < 0:
            QMessageBox.warning(self, "No Empty Slots", "All 256 DLC slots are occupied.")
            return

        try:
            src_name = self.save_handler.get_dlc_name(src, "en_us")
        except Exception:
            src_name = f"Slot {src}"

        reply = QMessageBox.question(
            self, "Clone DLC Item",
            f'Clone "{src_name}" (slot {src}) into slot {dst}?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.save_handler.clone_dlc_slot(src, dst)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to clone:\n{e}")
            return

        self._dirty = True
        self._populate_table()
        self._select_slot(dst)
        self.status_label.setText(f'Cloned "{src_name}" from slot {src} to slot {dst}.')

    def _on_create_hdlc(self):
        """Create a new HDLC entry in the selected or first free slot."""
        # Find target slot
        target = self._current_slot
        if target >= 0 and self.save_handler.is_dlc_slot_valid(target):
            target = self.save_handler.find_empty_dlc_slot()
        elif target < 0:
            target = self.save_handler.find_empty_dlc_slot()
        if target < 0:
            QMessageBox.warning(self, "No Empty Slots", "All 256 DLC slots are occupied.")
            return

        # Get item name
        name, ok = QInputDialog.getText(
            self, "Create HDLC Item",
            f"Item name for slot {target}:",
        )
        if not ok or not name.strip():
            return
        name = name.strip()[:16]

        # Get base ID
        base_id_str, ok = QInputDialog.getText(
            self, "Create HDLC Item",
            "Base Item ID (hex, e.g. 0x0100):\n\n"
            "The in-game item code will be (base_id * 4) + 0x9000.",
            text="0x0100",
        )
        if not ok or not base_id_str.strip():
            return
        try:
            base_id = int(base_id_str.strip(), 0)
        except ValueError:
            QMessageBox.warning(self, "Invalid ID", f"Cannot parse '{base_id_str}' as a number.")
            return
        if not 0 <= base_id <= 0xFFFF:
            QMessageBox.warning(self, "Invalid ID", "Base ID must be 0x0000 - 0xFFFF.")
            return

        # Check for duplicate base ID
        for s in range(DLC_SLOT_COUNT):
            if s == target:
                continue
            try:
                if self.save_handler.is_dlc_slot_valid(s) and self.save_handler.get_dlc_base_id(s) == base_id:
                    existing_name = self.save_handler.get_dlc_name(s, "en_us")
                    reply = QMessageBox.question(
                        self, "Duplicate Base ID",
                        f'Base ID 0x{base_id:04X} is already used by "{existing_name}" in slot {s}.\n'
                        "Create anyway?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        return
                    break
            except Exception:
                pass

        # Get category
        categories = list(ITEM_CLASSES.items())
        cat_names = [f"{idx} - {name}" for idx, name in categories]
        cat_choice, ok = QInputDialog.getItem(
            self, "Create HDLC Item", "Item class:", cat_names, 0, False,
        )
        if not ok:
            return
        class_idx = categories[cat_names.index(cat_choice)][0]

        # Price
        price, ok = QInputDialog.getInt(
            self, "Create HDLC Item", "Price (Bells):", 0, 0, 999_999,
        )
        if not ok:
            return

        # Template: offer to clone visuals from existing item
        template_slot = -1
        all_dlc = self.save_handler.get_all_dlc()
        if all_dlc:
            template_names = ["(None — blank item)"]
            template_slots = [-1]
            for d in all_dlc:
                template_names.append(f"Slot {d['slot']}: {d.get('name_en', '?')}")
                template_slots.append(d["slot"])
            choice, ok = QInputDialog.getItem(
                self, "Create HDLC Item",
                "Clone visuals (ASH0 texture + metadata) from:",
                template_names, 0, False,
            )
            if not ok:
                return
            template_slot = template_slots[template_names.index(choice)]

        try:
            self.save_handler.create_dlc_entry(
                slot=target,
                name=name,
                base_id=base_id,
                price=price,
                class_idx=class_idx,
                template_slot=template_slot,
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create HDLC:\n{e}")
            return

        item_code = (base_id * 4) + 0x9000
        self._dirty = True
        self._populate_table()
        self._select_slot(target)
        self.status_label.setText(
            f'Created HDLC "{name}" in slot {target} (item code 0x{item_code:04X}).'
        )

    def _on_patch_catalog(self):
        idx = self.player_combo.currentIndex()
        if idx < 0:
            return
        player = self.player_combo.itemData(idx)
        if player is None:
            return
        reply = QMessageBox.question(
            self, "Patch Catalog",
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _select_slot(self, slot: int):
        """Select and scroll to the given slot row in the table."""
        if 0 <= slot < self.dlc_table.rowCount():
            self.dlc_table.selectRow(slot)
            self.dlc_table.scrollToItem(
                self.dlc_table.item(slot, 0),
                QAbstractItemView.ScrollHint.PositionAtCenter,
            )

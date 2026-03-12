"""Acre Layout Editor dialog for Animal Crossing: City Folk save editor."""

import struct
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QPushButton, QToolButton, QGroupBox, QFileDialog, QMessageBox,
    QHeaderView, QAbstractItemView, QButtonGroup,
)
from PyQt6.QtCore import Qt

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from items_db import ITEMS, CATEGORIES

ACRE_CATEGORIES = {
    "Barrier":    "a_barrier",
    "Normal":     "a_normal",
    "Oceanfront": "a_ocean",
    "River":      "a_river",
    "Transition": "a_transition",
}

GRID_ROWS = 7
GRID_COLS = 7


class AcreEditorDialog(QDialog):
    """Dialog for editing the 7x7 acre grid layout."""

    def __init__(self, save_handler, player=0, parent=None):
        super().__init__(parent)
        self.save_handler = save_handler
        self.player = player
        self.acres = list(save_handler.get_acre_layout())

        self.setWindowTitle("Acre Layout Editor")
        self.setMinimumSize(780, 520)
        self._build_ui()
        self._populate_tree()
        self._refresh_grid()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: acre grid
        left_widget = QGroupBox("Acre Grid (7x7)")
        left_layout = QVBoxLayout(left_widget)

        self.table = QTableWidget(GRID_ROWS, GRID_COLS)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        left_layout.addWidget(self.table)

        # Tool buttons
        tool_layout = QHBoxLayout()

        self.check_btn = QToolButton()
        self.check_btn.setText("Check")
        self.check_btn.setCheckable(True)
        self.check_btn.setToolTip("Click a cell to inspect its acre code")

        self.replace_btn = QToolButton()
        self.replace_btn.setText("Replace")
        self.replace_btn.setCheckable(True)
        self.replace_btn.setToolTip("Click a cell to replace with selected acre")

        self.delete_btn = QToolButton()
        self.delete_btn.setText("Delete")
        self.delete_btn.setCheckable(True)
        self.delete_btn.setToolTip("Click a cell to clear it (set to 0x0000)")

        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_group.addButton(self.check_btn, 0)
        self.tool_group.addButton(self.replace_btn, 1)
        self.tool_group.addButton(self.delete_btn, 2)
        self.check_btn.setChecked(True)

        tool_layout.addWidget(self.check_btn)
        tool_layout.addWidget(self.replace_btn)
        tool_layout.addWidget(self.delete_btn)
        tool_layout.addStretch()
        left_layout.addLayout(tool_layout)

        splitter.addWidget(left_widget)

        # Right: acre type tree
        right_widget = QGroupBox("Acre Types")
        right_layout = QVBoxLayout(right_widget)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Acre"])
        self.tree.setColumnCount(1)
        right_layout.addWidget(self.tree)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

        # Connect cell click
        self.table.cellClicked.connect(self._on_cell_clicked)

        # Import/Export + Apply/Cancel
        bottom_layout = QHBoxLayout()

        import_btn = QPushButton("Import...")
        import_btn.clicked.connect(self._import_layout)
        export_btn = QPushButton("Export...")
        export_btn.clicked.connect(self._export_layout)

        bottom_layout.addWidget(import_btn)
        bottom_layout.addWidget(export_btn)
        bottom_layout.addStretch()

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        bottom_layout.addWidget(apply_btn)
        bottom_layout.addWidget(cancel_btn)
        layout.addLayout(bottom_layout)

    def _populate_tree(self):
        """Fill the QTreeWidget with acre categories from items_db."""
        for display_name, cat_key in ACRE_CATEGORIES.items():
            parent = QTreeWidgetItem(self.tree, [display_name])
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)

            acre_ids = CATEGORIES.get(cat_key, [])
            for acre_id in acre_ids:
                item_info = ITEMS.get(acre_id, {})
                name = item_info.get("name_ea", "Unknown")
                label = f"0x{acre_id:04X} - {name}"
                child = QTreeWidgetItem(parent, [label])
                child.setData(0, Qt.ItemDataRole.UserRole, acre_id)

    def _refresh_grid(self):
        """Update all table cells from the internal acres list."""
        self.table.blockSignals(True)
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                idx = row * GRID_COLS + col
                code = self.acres[idx] if idx < len(self.acres) else 0

                item_info = ITEMS.get(code, {})
                name = item_info.get("name_ea", "")
                text = f"0x{code:04X}"
                if name:
                    text += f"\n{name}"

                cell = QTableWidgetItem(text)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col, cell)
        self.table.blockSignals(False)

    def _get_selected_acre(self):
        """Return the acre code selected in the tree, or None."""
        items = self.tree.selectedItems()
        if not items:
            return None
        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        return data

    def _on_cell_clicked(self, row, col):
        idx = row * GRID_COLS + col
        tool = self.tool_group.checkedId()

        if tool == 0:  # Check
            code = self.acres[idx]
            item_info = ITEMS.get(code, {})
            name = item_info.get("name_ea", "Unknown")
            QMessageBox.information(
                self,
                "Acre Info",
                f"Position: ({row}, {col})\n"
                f"Code: 0x{code:04X}\n"
                f"Name: {name}",
            )
        elif tool == 1:  # Replace
            acre_id = self._get_selected_acre()
            if acre_id is None:
                QMessageBox.warning(self, "No Selection", "Select an acre type from the tree first.")
                return
            self.acres[idx] = acre_id
            self._refresh_grid()
        elif tool == 2:  # Delete
            self.acres[idx] = 0x0000
            self._refresh_grid()

    def _import_layout(self):
        """Import acre layout from a raw .bin file (98 bytes = 49 x u16 big-endian)."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Acre Layout", "", "Binary Files (*.bin);;All Files (*)"
        )
        if not path:
            return
        data = Path(path).read_bytes()
        if len(data) != 98:
            QMessageBox.warning(
                self,
                "Invalid File",
                f"Expected 98 bytes (49 x 2-byte codes), got {len(data)} bytes.",
            )
            return
        self.acres = list(struct.unpack(">49H", data))
        self._refresh_grid()

    def _export_layout(self):
        """Export acre layout to a raw .bin file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Acre Layout", "acres.bin", "Binary Files (*.bin);;All Files (*)"
        )
        if not path:
            return
        data = struct.pack(">49H", *self.acres[:49])
        Path(path).write_bytes(data)

    def _apply(self):
        """Write the modified acre layout back to save_handler and accept."""
        try:
            self.save_handler.set_acre_layout(self.acres[:49])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to write acre layout:\n{e}")
            return
        self.accept()

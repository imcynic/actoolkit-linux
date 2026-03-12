"""
Building Editor Dialog for Animal Crossing: City Folk Save Editor.

Manages 35 buildings and 100 signs in the town.  Each entry is stored as
a pair of (X, Y) byte coordinates in the save file.  Grid position is
``stored_value - 0x10``; a coordinate of (0, 0) means the slot is empty.

Save-file layout (from towneditor.pas reverse engineering):
    $5EB0A  Buildings 0-32   (33 × 2 bytes)
    $5EB8A  Building 34      (Bus Stop, 2 bytes)
    $5EB90  Building 33      (Pavé's Sign, 2 bytes)
    $5EB92  Signs 0-99       (100 × 2 bytes)
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QComboBox, QSpinBox,
    QGroupBox, QAbstractItemView, QMessageBox,
    QWidget, QToolButton, QButtonGroup, QFormLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QFont

from save_handler import SaveHandler


# Grid constants  (town grid is 80×80, but buildings use +0x10 stored coords)
GRID_COORD_OFFSET = 0x10
GRID_W = 80
GRID_H = 80


def _grid_coord(stored: int) -> int:
    """Convert stored coordinate to 0-based grid position."""
    return max(0, stored - GRID_COORD_OFFSET)


def _stored_coord(grid: int) -> int:
    """Convert 0-based grid position to stored coordinate."""
    return grid + GRID_COORD_OFFSET


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class BuildingEditorDialog(QDialog):
    """Dialog for viewing and editing building/sign positions."""

    TOOL_CHECK = 0
    TOOL_MOVE = 1
    TOOL_PLACE = 2
    TOOL_DELETE = 3

    def __init__(
        self,
        save_handler: SaveHandler,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.save_handler = save_handler
        self.active_tool = self.TOOL_CHECK
        self.selected_building: Optional[int] = None  # building being moved

        self.setWindowTitle("Building Editor")
        self.resize(960, 640)

        # Working copies
        self.buildings: list[tuple[int, int]] = list(save_handler.get_buildings())
        self.signs: list[tuple[int, int]] = list(save_handler.get_signs())

        self._build_ui()
        self._populate_table()
        self._populate_place_combo()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Left: building table ---
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("Buildings"))
        self.bld_table = self._make_table(35, ["ID", "Name", "Grid X", "Grid Y", "Status"])
        self.bld_table.setColumnWidth(0, 36)
        self.bld_table.setColumnWidth(1, 200)
        self.bld_table.setColumnWidth(2, 60)
        self.bld_table.setColumnWidth(3, 60)
        self.bld_table.setColumnWidth(4, 70)
        self.bld_table.cellClicked.connect(self._on_building_clicked)
        left_layout.addWidget(self.bld_table, stretch=3)

        left_layout.addWidget(QLabel("Signs"))
        self.sign_table = self._make_table(100, ["ID", "Grid X", "Grid Y", "Status"])
        self.sign_table.setColumnWidth(0, 40)
        self.sign_table.setColumnWidth(1, 60)
        self.sign_table.setColumnWidth(2, 60)
        self.sign_table.setColumnWidth(3, 70)
        self.sign_table.cellClicked.connect(self._on_sign_clicked)
        left_layout.addWidget(self.sign_table, stretch=2)

        splitter.addWidget(left)

        # --- Right: tools panel ---
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)

        # Tool buttons
        tool_box = QGroupBox("Tools")
        tool_inner = QVBoxLayout(tool_box)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)

        tools = [
            (self.TOOL_CHECK, "Check", "Select a building to view info"),
            (self.TOOL_MOVE, "Move", "Select a building, then set new coordinates"),
            (self.TOOL_PLACE, "Place", "Place a new building from the list below"),
            (self.TOOL_DELETE, "Delete", "Select a building to remove it"),
        ]
        for tid, label, tip in tools:
            btn = QToolButton()
            btn.setText(label)
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.setMinimumWidth(90)
            if tid == self.TOOL_CHECK:
                btn.setChecked(True)
            self.tool_group.addButton(btn, tid)
            tool_inner.addWidget(btn)

        self.tool_group.idToggled.connect(self._on_tool_changed)
        right_layout.addWidget(tool_box)

        # Place building selector
        place_box = QGroupBox("Place Building")
        place_layout = QVBoxLayout(place_box)
        self.place_combo = QComboBox()
        place_layout.addWidget(self.place_combo)
        right_layout.addWidget(place_box)

        # Coordinate editor
        coord_box = QGroupBox("Set Coordinates")
        coord_form = QFormLayout(coord_box)
        self.x_spin = QSpinBox()
        self.x_spin.setRange(0, GRID_W - 1)
        self.y_spin = QSpinBox()
        self.y_spin.setRange(0, GRID_H - 1)
        coord_form.addRow("Grid X:", self.x_spin)
        coord_form.addRow("Grid Y:", self.y_spin)
        self.apply_coord_btn = QPushButton("Apply Coordinates")
        self.apply_coord_btn.clicked.connect(self._on_apply_coords)
        coord_form.addRow(self.apply_coord_btn)
        right_layout.addWidget(coord_box)

        # Info label
        self.info_label = QLabel("Select a building or sign.")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("padding: 6px;")
        right_layout.addWidget(self.info_label)

        right_layout.addStretch()

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        apply_btn = QPushButton("Apply")
        apply_btn.setMinimumWidth(90)
        apply_btn.clicked.connect(self._on_apply)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(90)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(cancel_btn)
        right_layout.addLayout(btn_row)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter)

    @staticmethod
    def _make_table(rows: int, headers: list[str]) -> QTableWidget:
        table = QTableWidget(rows, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.setFont(QFont("Monospace", 8))
        return table

    # ------------------------------------------------------------------
    # Populate
    # ------------------------------------------------------------------

    def _populate_table(self):
        # Buildings
        self.bld_table.blockSignals(True)
        for i in range(min(35, len(self.buildings))):
            x, y = self.buildings[i]
            exists = (x != 0 or y != 0)
            name = self.save_handler.get_building_name(i)
            gx, gy = (_grid_coord(x), _grid_coord(y)) if exists else (0, 0)
            status = "Active" if exists else "Empty"

            self.bld_table.setItem(i, 0, self._cell(str(i)))
            self.bld_table.setItem(i, 1, self._cell(name))
            self.bld_table.setItem(i, 2, self._cell(str(gx) if exists else "-"))
            self.bld_table.setItem(i, 3, self._cell(str(gy) if exists else "-"))

            status_item = self._cell(status)
            if exists:
                status_item.setBackground(QBrush(QColor(144, 238, 144)))
            else:
                status_item.setBackground(QBrush(QColor(220, 220, 220)))
            self.bld_table.setItem(i, 4, status_item)
        self.bld_table.blockSignals(False)

        # Signs
        self.sign_table.blockSignals(True)
        for i in range(min(100, len(self.signs))):
            x, y = self.signs[i]
            exists = (x != 0 or y != 0)
            gx, gy = (_grid_coord(x), _grid_coord(y)) if exists else (0, 0)
            status = "Active" if exists else "Empty"

            self.sign_table.setItem(i, 0, self._cell(f"S{i}"))
            self.sign_table.setItem(i, 1, self._cell(str(gx) if exists else "-"))
            self.sign_table.setItem(i, 2, self._cell(str(gy) if exists else "-"))

            status_item = self._cell(status)
            if exists:
                status_item.setBackground(QBrush(QColor(173, 216, 230)))
            else:
                status_item.setBackground(QBrush(QColor(220, 220, 220)))
            self.sign_table.setItem(i, 3, status_item)
        self.sign_table.blockSignals(False)

    @staticmethod
    def _cell(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item

    def _populate_place_combo(self):
        """Fill combo with buildings that don't currently exist."""
        self.place_combo.clear()
        for i in range(35):
            x, y = self.buildings[i]
            if x == 0 and y == 0:
                name = self.save_handler.get_building_name(i)
                self.place_combo.addItem(f"[{i}] {name}", i)
        # Count available sign slots
        free_signs = sum(1 for x, y in self.signs if x == 0 and y == 0)
        if free_signs > 0:
            self.place_combo.addItem(f"[Sign] ({free_signs} slots free)", 35)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_tool_changed(self, tool_id: int, checked: bool):
        if checked:
            self.active_tool = tool_id
            self.selected_building = None

    def _on_building_clicked(self, row: int, _col: int):
        if row < 0 or row >= 35:
            return

        x, y = self.buildings[row]
        exists = (x != 0 or y != 0)
        name = self.save_handler.get_building_name(row)

        if self.active_tool == self.TOOL_CHECK:
            if exists:
                gx, gy = _grid_coord(x), _grid_coord(y)
                self.info_label.setText(
                    f"Building {row}: {name}\n"
                    f"Grid: ({gx}, {gy})\n"
                    f"Raw: (0x{x:02X}, 0x{y:02X})"
                )
                self.x_spin.setValue(gx)
                self.y_spin.setValue(gy)
            else:
                self.info_label.setText(f"Building {row}: {name}\n(empty)")

        elif self.active_tool == self.TOOL_MOVE:
            if exists:
                self.selected_building = row
                gx, gy = _grid_coord(x), _grid_coord(y)
                self.x_spin.setValue(gx)
                self.y_spin.setValue(gy)
                self.info_label.setText(
                    f"Moving: {name}\n"
                    f"Set new coordinates and click 'Apply Coordinates'"
                )
            else:
                self.info_label.setText(f"{name} doesn't exist. Use Place tool.")

        elif self.active_tool == self.TOOL_DELETE:
            if exists:
                reply = QMessageBox.question(
                    self, "Delete Building",
                    f"Delete {name} at grid ({_grid_coord(x)}, {_grid_coord(y)})?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.buildings[row] = (0, 0)
                    self.info_label.setText(f"Deleted {name}.")
                    self._populate_table()
                    self._populate_place_combo()
            else:
                self.info_label.setText(f"{name} is already empty.")

    def _on_sign_clicked(self, row: int, _col: int):
        if row < 0 or row >= 100:
            return

        x, y = self.signs[row]
        exists = (x != 0 or y != 0)

        if self.active_tool == self.TOOL_CHECK:
            if exists:
                gx, gy = _grid_coord(x), _grid_coord(y)
                self.info_label.setText(
                    f"Sign S{row}\n"
                    f"Grid: ({gx}, {gy})\n"
                    f"Raw: (0x{x:02X}, 0x{y:02X})"
                )
                self.x_spin.setValue(gx)
                self.y_spin.setValue(gy)
            else:
                self.info_label.setText(f"Sign S{row}: (empty)")

        elif self.active_tool == self.TOOL_MOVE:
            if exists:
                self.selected_building = (100 + row)  # encode as sign
                gx, gy = _grid_coord(x), _grid_coord(y)
                self.x_spin.setValue(gx)
                self.y_spin.setValue(gy)
                self.info_label.setText(
                    f"Moving Sign S{row}\n"
                    f"Set new coordinates and click 'Apply Coordinates'"
                )
            else:
                self.info_label.setText(f"Sign S{row} is empty.")

        elif self.active_tool == self.TOOL_DELETE:
            if exists:
                self.signs[row] = (0, 0)
                self.info_label.setText(f"Deleted Sign S{row}.")
                self._populate_table()
                self._populate_place_combo()
            else:
                self.info_label.setText(f"Sign S{row} is already empty.")

    def _on_apply_coords(self):
        """Apply coordinate spinbox values to the selected building."""
        if self.selected_building is None:
            self.info_label.setText("No building selected. Use Move or Check tool first.")
            return

        gx = self.x_spin.value()
        gy = self.y_spin.value()
        sx = _stored_coord(gx)
        sy = _stored_coord(gy)

        # Check for collisions
        if not self._check_collision(gx, gy, exclude=self.selected_building):
            self.info_label.setText("Collision: another building/sign is already at that position.")
            return

        if self.selected_building < 100:
            # It's a building
            bid = self.selected_building
            name = self.save_handler.get_building_name(bid)
            self.buildings[bid] = (sx, sy)
            self.info_label.setText(f"Moved {name} to grid ({gx}, {gy}).")
        else:
            # It's a sign
            sid = self.selected_building - 100
            self.signs[sid] = (sx, sy)
            self.info_label.setText(f"Moved Sign S{sid} to grid ({gx}, {gy}).")

        self.selected_building = None
        self._populate_table()

    def _check_collision(self, gx: int, gy: int, exclude: Optional[int] = None) -> bool:
        """Return True if position is free (no collision)."""
        sx = _stored_coord(gx)
        sy = _stored_coord(gy)

        for i, (bx, by) in enumerate(self.buildings):
            if exclude is not None and i == exclude:
                continue
            if bx == sx and by == sy and (bx != 0 or by != 0):
                return False

        for i, (bx, by) in enumerate(self.signs):
            eid = 100 + i
            if exclude is not None and eid == exclude:
                continue
            if bx == sx and by == sy and (bx != 0 or by != 0):
                return False

        return True

    # ------------------------------------------------------------------
    # Apply / Cancel
    # ------------------------------------------------------------------

    def _on_apply(self):
        """Write all building and sign data back to save handler."""
        try:
            for i in range(35):
                x, y = self.buildings[i]
                self.save_handler.set_building(i, x, y)
            for i in range(100):
                x, y = self.signs[i]
                self.save_handler.set_sign(i, x, y)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to write building data:\n{e}")
            return
        self.accept()

"""Grass Quality Editor dialog for Animal Crossing: City Folk save editor."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QPushButton, QSpinBox, QLabel, QGroupBox,
    QToolButton, QButtonGroup, QSizePolicy,
)
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QPainter, QColor, QMouseEvent

GRID_SIZE = 80
CELL_COUNT = GRID_SIZE * GRID_SIZE  # 6400

# Endpoint colors for interpolation
COLOR_DEAD = (139, 90, 43)     # brown, value 0
COLOR_ALIVE = (34, 139, 34)    # green, value 255


def _grass_color(value):
    """Interpolate between dead brown and alive green based on 0-255 value."""
    t = value / 255.0
    r = int(COLOR_DEAD[0] + (COLOR_ALIVE[0] - COLOR_DEAD[0]) * t)
    g = int(COLOR_DEAD[1] + (COLOR_ALIVE[1] - COLOR_DEAD[1]) * t)
    b = int(COLOR_DEAD[2] + (COLOR_ALIVE[2] - COLOR_DEAD[2]) * t)
    return QColor(r, g, b)


class GrassGridWidget(QWidget):
    """Custom widget that renders the 80x80 grass grid with QPainter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = [0] * CELL_COUNT
        self.cell_size = 5
        self.setMinimumSize(GRID_SIZE * self.cell_size, GRID_SIZE * self.cell_size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._tool_mode = 0  # 0 = Check, 1 = Set
        self._set_value = 255
        self._on_check = None  # callback(x, y, value)

    def set_data(self, data):
        self.data = list(data)
        self.update()

    def set_tool_mode(self, mode):
        self._tool_mode = mode

    def set_paint_value(self, value):
        self._set_value = value

    def set_check_callback(self, cb):
        self._on_check = cb

    def sizeHint(self):
        side = GRID_SIZE * self.cell_size
        return QSize(side, side)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        rect = event.rect()
        cs = self.cell_size

        # Determine visible cell range to avoid painting the entire grid every frame
        col_start = max(0, rect.left() // cs)
        col_end = min(GRID_SIZE, rect.right() // cs + 1)
        row_start = max(0, rect.top() // cs)
        row_end = min(GRID_SIZE, rect.bottom() // cs + 1)

        for row in range(row_start, row_end):
            base = row * GRID_SIZE
            for col in range(col_start, col_end):
                val = self.data[base + col]
                painter.fillRect(
                    col * cs, row * cs, cs, cs,
                    _grass_color(val),
                )
        painter.end()

    def _cell_from_pos(self, pos):
        """Return (col, row) grid coordinates from a mouse position, or None."""
        x = pos.x() // self.cell_size
        y = pos.y() // self.cell_size
        if 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE:
            return x, y
        return None

    def mousePressEvent(self, event: QMouseEvent):
        cell = self._cell_from_pos(event.position().toPoint())
        if cell is None:
            return
        col, row = cell
        idx = row * GRID_SIZE + col

        if self._tool_mode == 0:  # Check
            if self._on_check:
                self._on_check(col, row, self.data[idx])
        elif self._tool_mode == 1:  # Set
            self.data[idx] = self._set_value
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._tool_mode != 1:
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        cell = self._cell_from_pos(event.position().toPoint())
        if cell is None:
            return
        col, row = cell
        idx = row * GRID_SIZE + col
        if self.data[idx] != self._set_value:
            self.data[idx] = self._set_value
            # Repaint just the affected cell
            cs = self.cell_size
            self.update(QRect(col * cs, row * cs, cs, cs))


class GrassEditorDialog(QDialog):
    """Dialog for editing the 80x80 grass quality grid."""

    def __init__(self, save_handler, player=0, parent=None):
        super().__init__(parent)
        self.save_handler = save_handler
        self.player = player

        self.setWindowTitle("Grass Quality Editor")
        self.setMinimumSize(540, 520)
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QHBoxLayout(self)

        # Left: grass grid
        self.grid_widget = GrassGridWidget()
        self.grid_widget.set_check_callback(self._on_check)
        layout.addWidget(self.grid_widget)

        # Right: controls
        controls = QVBoxLayout()

        # Tool mode
        tool_group_box = QGroupBox("Tool")
        tool_layout = QVBoxLayout(tool_group_box)

        self.check_tool = QToolButton()
        self.check_tool.setText("Check")
        self.check_tool.setCheckable(True)
        self.check_tool.setChecked(True)
        self.check_tool.setToolTip("Click a cell to view its value")

        self.set_tool = QToolButton()
        self.set_tool.setText("Set")
        self.set_tool.setCheckable(True)
        self.set_tool.setToolTip("Click/drag to paint cells with the value below")

        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_group.addButton(self.check_tool, 0)
        self.tool_group.addButton(self.set_tool, 1)
        self.tool_group.idToggled.connect(self._on_tool_changed)

        tool_layout.addWidget(self.check_tool)
        tool_layout.addWidget(self.set_tool)
        controls.addWidget(tool_group_box)

        # Value spinner
        val_group = QGroupBox("Brush Value")
        val_layout = QVBoxLayout(val_group)
        self.value_spin = QSpinBox()
        self.value_spin.setRange(0, 255)
        self.value_spin.setValue(255)
        self.value_spin.setToolTip("Grass health value (0=dead, 255=full)")
        self.value_spin.valueChanged.connect(self._on_value_changed)
        val_layout.addWidget(self.value_spin)
        controls.addWidget(val_group)

        # Info label (for check mode)
        self.info_label = QLabel("Click a cell to inspect")
        self.info_label.setWordWrap(True)
        controls.addWidget(self.info_label)

        # Preset buttons
        preset_group = QGroupBox("Presets")
        preset_layout = QVBoxLayout(preset_group)

        restore_btn = QPushButton("Restore All (255)")
        restore_btn.setToolTip("Set all grass to maximum health")
        restore_btn.clicked.connect(self._restore_all)

        remove_btn = QPushButton("Remove All (0)")
        remove_btn.setToolTip("Set all grass to dead/bare")
        remove_btn.clicked.connect(self._remove_all)

        preset_layout.addWidget(restore_btn)
        preset_layout.addWidget(remove_btn)
        controls.addWidget(preset_group)

        controls.addStretch()

        # Apply / Cancel
        btn_layout = QVBoxLayout()
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(apply_btn)
        btn_layout.addWidget(cancel_btn)
        controls.addLayout(btn_layout)

        layout.addLayout(controls)

    def _load_data(self):
        """Load grass data from save_handler into the grid widget."""
        data = self.save_handler.get_grass_data()
        self.grid_widget.set_data(data)

    def _on_tool_changed(self, button_id, checked):
        if checked:
            self.grid_widget.set_tool_mode(button_id)

    def _on_value_changed(self, value):
        self.grid_widget.set_paint_value(value)

    def _on_check(self, x, y, value):
        pct = value / 255.0 * 100
        self.info_label.setText(
            f"Cell ({x}, {y})\n"
            f"Value: {value} / 255\n"
            f"Health: {pct:.0f}%"
        )

    def _restore_all(self):
        self.grid_widget.set_data([255] * CELL_COUNT)

    def _remove_all(self):
        self.grid_widget.set_data([0] * CELL_COUNT)

    def _apply(self):
        """Write the modified grass data back to save_handler and accept."""
        try:
            self.save_handler.set_grass_data(self.grid_widget.data[:CELL_COUNT])
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to write grass data:\n{e}")
            return
        self.accept()

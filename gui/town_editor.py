"""
Town Editor for Animal Crossing: City Folk (ACCF)
80x80 tile grid editor with QPainter-based rendering.
"""

import struct
import sys
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QScrollArea, QTreeWidget,
    QTreeWidgetItem, QLabel, QRadioButton, QButtonGroup, QGroupBox,
    QMenuBar, QFileDialog, QMessageBox, QCheckBox, QSplitter, QFrame,
    QLineEdit, QApplication, QSizePolicy,
)
from PyQt6.QtCore import Qt, QRect, QPoint, QSize, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QPainter, QPixmap, QColor, QPen, QBrush, QAction, QFont,
    QWheelEvent, QMouseEvent, QPaintEvent, QResizeEvent, QKeyEvent,
)

# ---------------------------------------------------------------------------
# Try to import items database; provide stubs if unavailable so the module
# can still be loaded for development/testing.
# ---------------------------------------------------------------------------
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from items_db import ITEMS, CATEGORIES
except ImportError:
    ITEMS = {0xFFF1: {"name_ea": "Empty", "category": "special", "subcategory": "hardcoded"}}
    CATEGORIES = {}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRID_W = 80
GRID_H = 80
ACRE_SIZE = 16  # tiles per acre edge
TOTAL_TILES = GRID_W * GRID_H  # 6400
EMPTY_ITEM = 0xFFF1

MIN_CELL_PX = 2
MAX_CELL_PX = 32
DEFAULT_CELL_PX = 7

# Tool modes
TOOL_CHECK = 0
TOOL_REPLACE = 1
TOOL_DELETE = 2
TOOL_COORDS = 3
TOOL_BURY = 4

# Building tool modes
BLDG_CHECK = 10
BLDG_MOVE = 11
BLDG_PLACE = 12
BLDG_DELETE = 13

# ---------------------------------------------------------------------------
# Colour mapping helpers
# ---------------------------------------------------------------------------

def _item_color(code: int) -> QColor:
    """Return the display colour for a 16-bit item code."""
    if code == EMPTY_ITEM:
        return QColor(255, 255, 255)

    # Trees
    if 0x0001 <= code <= 0x0056:
        return QColor(0, 255, 0)

    # Weeds
    if code in range(0x0057, 0x005B) or code in range(0x00DE, 0x00E2):
        return QColor(206, 134, 0)

    # Rocks
    if 0x005B <= code <= 0x0073:
        return QColor(0, 0, 0)

    # Patterns
    if 0x0074 <= code <= 0x0093:
        return QColor(255, 221, 170)

    # Flowers
    if 0x009E <= code <= 0x00BD:
        return QColor(255, 51, 153)

    # Parched flowers
    if 0x00BE <= code <= 0x00DD:
        return QColor(153, 102, 204)

    # Items (holdable)
    if (0x9000 <= code <= 0xB2E4) or (0xCE80 <= code <= 0xCF54):
        return QColor(255, 255, 0)

    # Furniture
    if 0xB2E5 <= code <= 0xCE50:
        return QColor(0, 255, 255)

    # Buildings / everything else
    return QColor(128, 5, 23)


# ---------------------------------------------------------------------------
# Grid Widget  (the performance-critical piece)
# ---------------------------------------------------------------------------

class TownGridWidget(QWidget):
    """Custom widget that draws the 80x80 town grid using QPainter.

    Rendering strategy:
      - A full-size QPixmap is maintained as a back-buffer.
      - Individual cells are redrawn on demand via ``invalidate_cell``.
      - ``paintEvent`` simply blits the pixmap to screen.
    """

    cell_clicked = pyqtSignal(int, int)  # grid_x, grid_y

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cell_px: int = DEFAULT_CELL_PX
        self._items: list[int] = [EMPTY_ITEM] * TOTAL_TILES
        self._buried: list[int] = [0] * ((TOTAL_TILES + 7) // 8)  # bit flags
        self._grass: list[int] = [0] * TOTAL_TILES

        self._show_grid = True
        self._show_acre_grid = True
        self._show_grass = False
        self._show_background = True

        self._pixmap: QPixmap | None = None
        self._hover_x: int = -1
        self._hover_y: int = -1

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._rebuild_pixmap()

    # -- Data access --------------------------------------------------------

    def set_items(self, items: list[int]):
        self._items = list(items)
        self._full_redraw()

    def get_items(self) -> list[int]:
        return list(self._items)

    def set_item(self, x: int, y: int, code: int):
        idx = y * GRID_W + x
        if 0 <= idx < TOTAL_TILES:
            self._items[idx] = code
            self._invalidate_cell(x, y)

    def get_item(self, x: int, y: int) -> int:
        idx = y * GRID_W + x
        if 0 <= idx < TOTAL_TILES:
            return self._items[idx]
        return EMPTY_ITEM

    def set_buried_data(self, data: list[int]):
        self._buried = list(data)
        self._full_redraw()

    def get_buried_data(self) -> list[int]:
        return list(self._buried)

    def is_buried(self, x: int, y: int) -> bool:
        idx = y * GRID_W + x
        byte_idx = idx // 8
        bit_idx = idx % 8
        if byte_idx < len(self._buried):
            return bool(self._buried[byte_idx] & (1 << bit_idx))
        return False

    def set_buried(self, x: int, y: int, buried: bool):
        idx = y * GRID_W + x
        byte_idx = idx // 8
        bit_idx = idx % 8
        if byte_idx < len(self._buried):
            if buried:
                self._buried[byte_idx] |= (1 << bit_idx)
            else:
                self._buried[byte_idx] &= ~(1 << bit_idx)
            self._invalidate_cell(x, y)

    def set_grass_data(self, data: list[int]):
        self._grass = list(data)
        if self._show_grass:
            self._full_redraw()

    def get_grass_data(self) -> list[int]:
        return list(self._grass)

    # -- View toggles -------------------------------------------------------

    def set_show_grid(self, v: bool):
        self._show_grid = v
        self._full_redraw()

    def set_show_acre_grid(self, v: bool):
        self._show_acre_grid = v
        self._full_redraw()

    def set_show_grass(self, v: bool):
        self._show_grass = v
        self._full_redraw()

    def set_show_background(self, v: bool):
        self._show_background = v
        self._full_redraw()

    # -- Zoom ---------------------------------------------------------------

    @property
    def cell_px(self) -> int:
        return self._cell_px

    def set_zoom(self, px: int):
        px = max(MIN_CELL_PX, min(MAX_CELL_PX, px))
        if px != self._cell_px:
            self._cell_px = px
            self._rebuild_pixmap()
            self._full_redraw()

    # -- Size ---------------------------------------------------------------

    def _grid_pixel_size(self) -> QSize:
        return QSize(GRID_W * self._cell_px, GRID_H * self._cell_px)

    def sizeHint(self) -> QSize:
        return self._grid_pixel_size()

    def minimumSizeHint(self) -> QSize:
        return self._grid_pixel_size()

    # -- Coordinate helpers -------------------------------------------------

    def _pixel_to_grid(self, px: int, py: int) -> tuple[int, int]:
        gx = px // self._cell_px
        gy = py // self._cell_px
        return (max(0, min(GRID_W - 1, gx)), max(0, min(GRID_H - 1, gy)))

    # -- Pixmap management --------------------------------------------------

    def _rebuild_pixmap(self):
        sz = self._grid_pixel_size()
        self._pixmap = QPixmap(sz)
        self._pixmap.fill(QColor(200, 200, 200))
        self.setFixedSize(sz)

    def _full_redraw(self):
        if self._pixmap is None:
            self._rebuild_pixmap()
        p = QPainter(self._pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self._paint_all_cells(p)
        self._paint_overlays(p)
        p.end()
        self.update()

    def _invalidate_cell(self, x: int, y: int):
        """Redraw a single cell on the back-buffer, then schedule repaint."""
        if self._pixmap is None:
            return
        p = QPainter(self._pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self._paint_cell(p, x, y)
        # Redraw grid lines that touch this cell
        self._paint_grid_for_cell(p, x, y)
        p.end()
        cx, cy = x * self._cell_px, y * self._cell_px
        self.update(QRect(cx, cy, self._cell_px, self._cell_px))

    # -- Painting -----------------------------------------------------------

    def _paint_all_cells(self, p: QPainter):
        cp = self._cell_px
        bg_color = QColor(225, 210, 170) if self._show_background else QColor(200, 200, 200)
        p.fillRect(0, 0, GRID_W * cp, GRID_H * cp, bg_color)

        for idx in range(TOTAL_TILES):
            x = idx % GRID_W
            y = idx // GRID_W
            self._paint_cell(p, x, y)

    def _paint_cell(self, p: QPainter, x: int, y: int):
        cp = self._cell_px
        idx = y * GRID_W + x
        code = self._items[idx] if idx < len(self._items) else EMPTY_ITEM
        color = _item_color(code)

        # Grass overlay: modulate alpha based on grass quality
        if self._show_grass and idx < len(self._grass):
            grass_val = self._grass[idx]
            if grass_val > 0:
                # Blend green overlay proportional to grass value
                alpha = int((grass_val / 255) * 120)
                grass_color = QColor(34, 139, 34, alpha)
                # Draw base colour first, then overlay
                rx = x * cp
                ry = y * cp
                p.fillRect(rx, ry, cp, cp, color)
                p.fillRect(rx, ry, cp, cp, grass_color)
            else:
                p.fillRect(x * cp, y * cp, cp, cp, color)
        else:
            p.fillRect(x * cp, y * cp, cp, cp, color)

        # Buried item indicator: small blue dot in centre
        byte_idx = idx // 8
        bit_idx = idx % 8
        if byte_idx < len(self._buried) and (self._buried[byte_idx] & (1 << bit_idx)):
            dot_sz = max(2, cp // 3)
            cx = x * cp + (cp - dot_sz) // 2
            cy = y * cp + (cp - dot_sz) // 2
            p.fillRect(cx, cy, dot_sz, dot_sz, QColor(0, 80, 255))

    def _paint_overlays(self, p: QPainter):
        """Draw grid lines and acre boundaries on top of cells."""
        cp = self._cell_px
        total_w = GRID_W * cp
        total_h = GRID_H * cp

        # Thin grid lines
        if self._show_grid and cp >= 5:
            pen = QPen(QColor(80, 80, 80, 40))
            pen.setWidth(1)
            p.setPen(pen)
            for gx in range(1, GRID_W):
                px = gx * cp
                p.drawLine(px, 0, px, total_h)
            for gy in range(1, GRID_H):
                py = gy * cp
                p.drawLine(0, py, total_w, py)

        # Acre boundaries (every 16 cells)
        if self._show_acre_grid:
            pen = QPen(QColor(255, 0, 0, 180))
            pen.setWidth(2)
            p.setPen(pen)
            for ax in range(1, GRID_W // ACRE_SIZE):
                px = ax * ACRE_SIZE * cp
                p.drawLine(px, 0, px, total_h)
            for ay in range(1, GRID_H // ACRE_SIZE):
                py = ay * ACRE_SIZE * cp
                p.drawLine(0, py, total_w, py)

    def _paint_grid_for_cell(self, p: QPainter, x: int, y: int):
        """Repaint grid lines touching a single cell after it was redrawn."""
        cp = self._cell_px
        total_w = GRID_W * cp
        total_h = GRID_H * cp

        if self._show_grid and cp >= 5:
            pen = QPen(QColor(80, 80, 80, 40))
            pen.setWidth(1)
            p.setPen(pen)
            # Right edge
            if x < GRID_W - 1:
                px = (x + 1) * cp
                p.drawLine(px, y * cp, px, (y + 1) * cp)
            # Bottom edge
            if y < GRID_H - 1:
                py = (y + 1) * cp
                p.drawLine(x * cp, py, (x + 1) * cp, py)
            # Left edge
            if x > 0:
                px = x * cp
                p.drawLine(px, y * cp, px, (y + 1) * cp)
            # Top edge
            if y > 0:
                py = y * cp
                p.drawLine(x * cp, py, (x + 1) * cp, py)

        if self._show_acre_grid:
            pen = QPen(QColor(255, 0, 0, 180))
            pen.setWidth(2)
            p.setPen(pen)
            # Check if any acre boundary touches this cell
            for dx in (0, 1):
                gx = x + dx
                if gx > 0 and gx < GRID_W and gx % ACRE_SIZE == 0:
                    px = gx * cp
                    p.drawLine(px, y * cp, px, (y + 1) * cp)
            for dy in (0, 1):
                gy = y + dy
                if gy > 0 and gy < GRID_H and gy % ACRE_SIZE == 0:
                    py = gy * cp
                    p.drawLine(x * cp, py, (x + 1) * cp, py)

    # -- Qt events ----------------------------------------------------------

    def paintEvent(self, ev: QPaintEvent):
        if self._pixmap is not None:
            p = QPainter(self)
            p.drawPixmap(0, 0, self._pixmap)
            # Draw hover highlight
            if 0 <= self._hover_x < GRID_W and 0 <= self._hover_y < GRID_H:
                cp = self._cell_px
                p.setPen(QPen(QColor(255, 255, 255, 200), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(self._hover_x * cp, self._hover_y * cp, cp - 1, cp - 1)
            p.end()

    def mousePressEvent(self, ev: QMouseEvent):
        if ev.button() == Qt.MouseButton.LeftButton:
            pos = ev.position()
            gx, gy = self._pixel_to_grid(int(pos.x()), int(pos.y()))
            self.cell_clicked.emit(gx, gy)

    def mouseMoveEvent(self, ev: QMouseEvent):
        pos = ev.position()
        gx, gy = self._pixel_to_grid(int(pos.x()), int(pos.y()))
        if gx != self._hover_x or gy != self._hover_y:
            old_hx, old_hy = self._hover_x, self._hover_y
            self._hover_x, self._hover_y = gx, gy
            cp = self._cell_px
            # Repaint old hover
            if 0 <= old_hx < GRID_W and 0 <= old_hy < GRID_H:
                self.update(QRect(old_hx * cp - 1, old_hy * cp - 1, cp + 2, cp + 2))
            # Repaint new hover
            self.update(QRect(gx * cp - 1, gy * cp - 1, cp + 2, cp + 2))

    def leaveEvent(self, ev):
        if self._hover_x >= 0:
            cp = self._cell_px
            old_hx, old_hy = self._hover_x, self._hover_y
            self._hover_x, self._hover_y = -1, -1
            self.update(QRect(old_hx * cp - 1, old_hy * cp - 1, cp + 2, cp + 2))

    def wheelEvent(self, ev: QWheelEvent):
        delta = ev.angleDelta().y()
        if delta > 0:
            self.set_zoom(self._cell_px + 1)
        elif delta < 0:
            self.set_zoom(self._cell_px - 1)
        ev.accept()


# ---------------------------------------------------------------------------
# Item Tree Builder
# ---------------------------------------------------------------------------

def _build_item_tree(tree: QTreeWidget):
    """Populate a QTreeWidget with items organised by category/subcategory."""
    tree.setHeaderLabels(["Item", "Code"])
    tree.setColumnWidth(0, 220)

    # Group items by (category, subcategory) - normalize to lowercase
    groups: dict[str, dict[str, list[tuple[int, str]]]] = {}
    for code, info in ITEMS.items():
        cat = info.get("category", "unknown").lower()
        sub = info.get("subcategory", "misc").lower()
        groups.setdefault(cat, {}).setdefault(sub, []).append((code, info.get("name_ea", f"0x{code:04X}")))

    # Desired top-level order
    cat_order = ["terrain", "items", "furniture", "acres", "special", "other"]
    seen = set()

    for cat in cat_order:
        if cat not in groups:
            continue
        seen.add(cat)
        cat_item = QTreeWidgetItem(tree, [cat.title()])
        cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        font = cat_item.font(0)
        font.setBold(True)
        cat_item.setFont(0, font)

        for sub in sorted(groups[cat].keys()):
            sub_item = QTreeWidgetItem(cat_item, [sub.replace("_", " ").title()])
            sub_item.setFlags(sub_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for code, name in sorted(groups[cat][sub], key=lambda t: t[0]):
                leaf = QTreeWidgetItem(sub_item, [name, f"0x{code:04X}"])
                leaf.setData(0, Qt.ItemDataRole.UserRole, code)

    # Any remaining categories
    for cat in sorted(groups.keys()):
        if cat in seen:
            continue
        cat_item = QTreeWidgetItem(tree, [cat.title()])
        cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        for sub in sorted(groups[cat].keys()):
            sub_item = QTreeWidgetItem(cat_item, [sub.replace("_", " ").title()])
            sub_item.setFlags(sub_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for code, name in sorted(groups[cat][sub], key=lambda t: t[0]):
                leaf = QTreeWidgetItem(sub_item, [name, f"0x{code:04X}"])
                leaf.setData(0, Qt.ItemDataRole.UserRole, code)


def _get_item_name(code: int) -> str:
    info = ITEMS.get(code)
    if info:
        return info.get("name_ea", f"Unknown (0x{code:04X})")
    return f"Unknown (0x{code:04X})"


# ---------------------------------------------------------------------------
# Main Dialog
# ---------------------------------------------------------------------------

class TownEditorDialog(QDialog):
    """Modal dialog for editing the ACCF 80x80 town grid."""

    def __init__(self, save_handler, parent=None):
        super().__init__(parent)
        self._save_handler = save_handler
        self._dirty = False
        self._current_tool = TOOL_CHECK
        self._current_bldg_tool = -1  # no building tool active initially
        self._selected_item_code: int = EMPTY_ITEM

        self.setWindowTitle("Town Editor - Animal Crossing: City Folk")
        self.setMinimumSize(960, 640)
        self.resize(1280, 800)
        self.setModal(True)

        self._build_ui()
        self._load_data()

    # -----------------------------------------------------------------------
    # UI Construction
    # -----------------------------------------------------------------------

    def _build_ui(self):
        # Create the grid widget early so menu actions can reference it
        self._grid = TownGridWidget()
        self._grid.cell_clicked.connect(self._on_cell_clicked)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Menu bar
        self._menu_bar = QMenuBar(self)
        root_layout.addWidget(self._menu_bar)
        self._build_menus()

        # Main content area
        body = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(body, stretch=1)

        # -- Left panel: tools + grid ----------------------------------------
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(4, 4, 4, 4)

        # Tool bar
        tool_frame = self._build_tool_bar()
        left_layout.addWidget(tool_frame)

        self._scroll = QScrollArea()
        self._scroll.setWidget(self._grid)
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self._scroll, stretch=1)

        # Status bar
        self._status_label = QLabel("Ready")
        self._status_label.setFrameStyle(QFrame.Shape.Panel | QFrame.Shadow.Sunken)
        self._status_label.setMinimumHeight(24)
        left_layout.addWidget(self._status_label)

        body.addWidget(left_panel)

        # -- Right panel: item tree + item search ----------------------------
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)

        # Search box
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Filter items...")
        self._search_box.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self._search_box)
        right_layout.addLayout(search_layout)

        # Item tree
        self._item_tree = QTreeWidget()
        _build_item_tree(self._item_tree)
        self._item_tree.currentItemChanged.connect(self._on_tree_selection)
        right_layout.addWidget(self._item_tree, stretch=1)

        # Selected item display
        self._selected_label = QLabel("Selected: Empty (0xFFF1)")
        self._selected_label.setWordWrap(True)
        right_layout.addWidget(self._selected_label)

        body.addWidget(right_panel)
        body.setStretchFactor(0, 3)
        body.setStretchFactor(1, 1)

    def _build_menus(self):
        # --- File-like actions ---
        action_menu = self._menu_bar.addMenu("&Action")

        apply_act = QAction("&Apply", self)
        apply_act.setShortcut("Ctrl+S")
        apply_act.triggered.connect(self._apply_changes)
        action_menu.addAction(apply_act)

        cancel_act = QAction("&Cancel", self)
        cancel_act.setShortcut("Escape")
        cancel_act.triggered.connect(self._cancel)
        action_menu.addAction(cancel_act)

        # --- Tasks ---
        task_menu = self._menu_bar.addMenu("&Tasks")

        remove_weeds_act = QAction("Remove All &Weeds", self)
        remove_weeds_act.triggered.connect(self._task_remove_weeds)
        task_menu.addAction(remove_weeds_act)

        revive_flowers_act = QAction("Revive &Flowers", self)
        revive_flowers_act.triggered.connect(self._task_revive_flowers)
        task_menu.addAction(revive_flowers_act)

        replenish_fruit_act = QAction("Replenish Fr&uit", self)
        replenish_fruit_act.triggered.connect(self._task_replenish_fruit)
        task_menu.addAction(replenish_fruit_act)

        task_menu.addSeparator()

        restore_grass_act = QAction("Restore &Grass", self)
        restore_grass_act.triggered.connect(self._task_restore_grass)
        task_menu.addAction(restore_grass_act)

        remove_grass_act = QAction("Remove Gras&s", self)
        remove_grass_act.triggered.connect(self._task_remove_grass)
        task_menu.addAction(remove_grass_act)

        # --- View ---
        view_menu = self._menu_bar.addMenu("&View")

        self._bg_action = QAction("Show &Background", self)
        self._bg_action.setCheckable(True)
        self._bg_action.setChecked(True)
        self._bg_action.toggled.connect(self._grid.set_show_background)
        view_menu.addAction(self._bg_action)

        self._grid_action = QAction("Show &Grid Lines", self)
        self._grid_action.setCheckable(True)
        self._grid_action.setChecked(True)
        self._grid_action.toggled.connect(self._grid.set_show_grid)
        view_menu.addAction(self._grid_action)

        self._acre_action = QAction("Show &Acre Grid", self)
        self._acre_action.setCheckable(True)
        self._acre_action.setChecked(True)
        self._acre_action.toggled.connect(self._grid.set_show_acre_grid)
        view_menu.addAction(self._acre_action)

        self._grass_action = QAction("Show Gra&ss Overlay", self)
        self._grass_action.setCheckable(True)
        self._grass_action.setChecked(False)
        self._grass_action.toggled.connect(self._grid.set_show_grass)
        view_menu.addAction(self._grass_action)

        # --- Import / Export ---
        io_menu = self._menu_bar.addMenu("&Import/Export")

        export_act = QAction("&Export Town Layout...", self)
        export_act.triggered.connect(self._export_layout)
        io_menu.addAction(export_act)

        import_act = QAction("&Import Town Layout...", self)
        import_act.triggered.connect(self._import_layout)
        io_menu.addAction(import_act)

    def _build_tool_bar(self) -> QWidget:
        outer = QWidget()
        outer_layout = QHBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # --- Tile tools ---
        tile_group_box = QGroupBox("Tile Tools")
        tile_layout = QHBoxLayout(tile_group_box)
        tile_layout.setContentsMargins(6, 2, 6, 2)
        self._tool_group = QButtonGroup(self)

        tool_defs = [
            (TOOL_CHECK, "Check"),
            (TOOL_REPLACE, "Replace"),
            (TOOL_DELETE, "Delete"),
            (TOOL_COORDS, "Coords"),
            (TOOL_BURY, "Bury/Unbury"),
        ]
        for tid, label in tool_defs:
            rb = QRadioButton(label)
            if tid == TOOL_CHECK:
                rb.setChecked(True)
            self._tool_group.addButton(rb, tid)
            tile_layout.addWidget(rb)

        self._tool_group.idToggled.connect(self._on_tool_changed)
        outer_layout.addWidget(tile_group_box)

        # --- Building tools ---
        bldg_group_box = QGroupBox("Building Tools")
        bldg_layout = QHBoxLayout(bldg_group_box)
        bldg_layout.setContentsMargins(6, 2, 6, 2)
        self._bldg_group = QButtonGroup(self)
        self._bldg_group.setExclusive(False)  # allow deselection

        bldg_defs = [
            (BLDG_CHECK, "Check Bldg"),
            (BLDG_MOVE, "Move Bldg"),
            (BLDG_PLACE, "Place Bldg"),
            (BLDG_DELETE, "Del Bldg"),
        ]
        for bid, label in bldg_defs:
            rb = QRadioButton(label)
            self._bldg_group.addButton(rb, bid)
            bldg_layout.addWidget(rb)

        self._bldg_group.idToggled.connect(self._on_bldg_tool_changed)
        outer_layout.addWidget(bldg_group_box)

        outer_layout.addStretch()
        return outer

    # -----------------------------------------------------------------------
    # Data I/O
    # -----------------------------------------------------------------------

    def _load_data(self):
        """Read town data from save handler into the grid widget."""
        sh = self._save_handler
        try:
            items = sh.get_town_items()
            self._grid.set_items(items)
        except Exception as exc:
            self._status(f"Error loading town items: {exc}")

        try:
            buried = sh.get_buried_items()
            self._grid.set_buried_data(buried)
        except Exception:
            pass

        try:
            grass = sh.get_grass_data()
            self._grid.set_grass_data(grass)
        except Exception:
            pass

        self._dirty = False
        self._status("Town data loaded.")

    def _apply_changes(self):
        """Write modified data back to save handler."""
        sh = self._save_handler
        items = self._grid.get_items()
        try:
            for idx, code in enumerate(items):
                sh.set_town_item(idx, code)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to write town items:\n{exc}")
            return

        try:
            sh.set_buried_items(self._grid.get_buried_data())
        except Exception:
            pass  # handler may not support this yet

        try:
            sh.set_grass_data(self._grid.get_grass_data())
        except Exception:
            pass

        self._dirty = False
        self._status("Changes applied to save buffer.")
        QMessageBox.information(self, "Town Editor", "Changes applied. Remember to save the file.")

    def _cancel(self):
        if self._dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Discard them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.reject()

    # -----------------------------------------------------------------------
    # Tool Handling
    # -----------------------------------------------------------------------

    def _on_tool_changed(self, tool_id: int, checked: bool):
        if checked:
            self._current_tool = tool_id
            # Deselect any building tool
            checked_bldg = self._bldg_group.checkedButton()
            if checked_bldg:
                self._bldg_group.setExclusive(False)
                checked_bldg.setChecked(False)
                self._bldg_group.setExclusive(False)
            self._current_bldg_tool = -1
            self._status(f"Tool: {self._tool_group.button(tool_id).text()}")

    def _on_bldg_tool_changed(self, tool_id: int, checked: bool):
        if checked:
            self._current_bldg_tool = tool_id
            # Deselect tile tools visually (but keep group exclusive internally)
            # The tile tool group stays as-is; we just override behaviour via _current_bldg_tool
            self._status(f"Building Tool: {self._bldg_group.button(tool_id).text()}")
        else:
            if self._bldg_group.checkedId() == -1:
                self._current_bldg_tool = -1

    def _on_cell_clicked(self, gx: int, gy: int):
        idx = gy * GRID_W + gx
        code = self._grid.get_item(gx, gy)
        acre_x, acre_y = gx // ACRE_SIZE, gy // ACRE_SIZE
        tile_x, tile_y = gx % ACRE_SIZE, gy % ACRE_SIZE

        # Building tools take priority if active
        if self._current_bldg_tool >= 0:
            self._handle_building_tool(gx, gy)
            return

        if self._current_tool == TOOL_CHECK:
            name = _get_item_name(code)
            buried = self._grid.is_buried(gx, gy)
            buried_str = " [BURIED]" if buried else ""
            self._status(
                f"({gx}, {gy}) Acre({acre_x},{acre_y}) Tile({tile_x},{tile_y}) | "
                f"0x{code:04X} - {name}{buried_str}"
            )

        elif self._current_tool == TOOL_REPLACE:
            old_code = code
            new_code = self._selected_item_code
            self._grid.set_item(gx, gy, new_code)
            self._dirty = True
            self._status(
                f"({gx}, {gy}) Replaced 0x{old_code:04X} with "
                f"0x{new_code:04X} ({_get_item_name(new_code)})"
            )

        elif self._current_tool == TOOL_DELETE:
            old_code = code
            self._grid.set_item(gx, gy, EMPTY_ITEM)
            self._dirty = True
            self._status(f"({gx}, {gy}) Deleted 0x{old_code:04X} ({_get_item_name(old_code)})")

        elif self._current_tool == TOOL_COORDS:
            self._status(
                f"Grid: ({gx}, {gy}) | Acre: ({acre_x}, {acre_y}) | "
                f"Tile in acre: ({tile_x}, {tile_y}) | Index: {idx}"
            )

        elif self._current_tool == TOOL_BURY:
            currently_buried = self._grid.is_buried(gx, gy)
            self._grid.set_buried(gx, gy, not currently_buried)
            self._dirty = True
            state = "Unburied" if currently_buried else "Buried"
            self._status(f"({gx}, {gy}) {state} item 0x{code:04X} ({_get_item_name(code)})")

    def _handle_building_tool(self, gx: int, gy: int):
        """Handle clicks when a building tool is active.

        Building data would come from save_handler.get_buildings() etc.
        For now, provide the framework and status messages.
        """
        code = self._grid.get_item(gx, gy)
        acre_x, acre_y = gx // ACRE_SIZE, gy // ACRE_SIZE

        if self._current_bldg_tool == BLDG_CHECK:
            self._status(
                f"Building Check @ ({gx},{gy}) Acre({acre_x},{acre_y}) | "
                f"Tile: 0x{code:04X} ({_get_item_name(code)})"
            )

        elif self._current_bldg_tool == BLDG_MOVE:
            self._status(
                f"Building Move: select building at ({gx},{gy}), "
                f"then click destination. (Not yet wired to save_handler.)"
            )

        elif self._current_bldg_tool == BLDG_PLACE:
            new_code = self._selected_item_code
            self._grid.set_item(gx, gy, new_code)
            self._dirty = True
            self._status(
                f"Placed building/item 0x{new_code:04X} ({_get_item_name(new_code)}) "
                f"at ({gx},{gy})"
            )

        elif self._current_bldg_tool == BLDG_DELETE:
            reply = QMessageBox.question(
                self, "Delete Building",
                f"Remove item 0x{code:04X} ({_get_item_name(code)}) at ({gx},{gy})?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._grid.set_item(gx, gy, EMPTY_ITEM)
                self._dirty = True
                self._status(f"Deleted building at ({gx},{gy})")

    # -----------------------------------------------------------------------
    # Item Tree
    # -----------------------------------------------------------------------

    def _on_tree_selection(self, current: QTreeWidgetItem, _previous):
        if current is None:
            return
        code = current.data(0, Qt.ItemDataRole.UserRole)
        if code is not None:
            self._selected_item_code = code
            name = _get_item_name(code)
            self._selected_label.setText(f"Selected: {name} (0x{code:04X})")

    def _on_search_changed(self, text: str):
        """Filter the item tree to show only matching items."""
        text = text.strip().lower()
        root = self._item_tree.invisibleRootItem()
        self._filter_tree_item(root, text)

    def _filter_tree_item(self, item: QTreeWidgetItem, text: str) -> bool:
        """Recursively show/hide tree items. Returns True if any child is visible."""
        if item.childCount() == 0:
            # Leaf node
            if not text:
                item.setHidden(False)
                return True
            name = (item.text(0) or "").lower()
            code_str = (item.text(1) or "").lower()
            match = text in name or text in code_str
            item.setHidden(not match)
            return match

        any_visible = False
        for i in range(item.childCount()):
            child = item.child(i)
            if self._filter_tree_item(child, text):
                any_visible = True

        item.setHidden(not any_visible)
        if any_visible and text:
            item.setExpanded(True)
        return any_visible

    # -----------------------------------------------------------------------
    # Tasks
    # -----------------------------------------------------------------------

    def _task_remove_weeds(self):
        """Replace all weed tiles with empty."""
        count = 0
        for idx in range(TOTAL_TILES):
            code = self._grid._items[idx]
            if code in range(0x0057, 0x005B) or code in range(0x00DE, 0x00E2):
                self._grid._items[idx] = EMPTY_ITEM
                count += 1
        if count:
            self._dirty = True
            self._grid._full_redraw()
        self._status(f"Removed {count} weeds.")

    def _task_revive_flowers(self):
        """Convert parched flowers (0x00BE-0x00DD) back to living flowers.

        Parched flowers map to their living counterparts by subtracting 0x20.
        """
        count = 0
        for idx in range(TOTAL_TILES):
            code = self._grid._items[idx]
            if 0x00BE <= code <= 0x00DD:
                revived = code - 0x20
                if 0x009E <= revived <= 0x00BD:
                    self._grid._items[idx] = revived
                    count += 1
        if count:
            self._dirty = True
            self._grid._full_redraw()
        self._status(f"Revived {count} parched flowers.")

    def _task_replenish_fruit(self):
        """Convert bare fruit trees back to fruiting trees.

        In ACCF, tree codes 0x0001-0x0056 include both bare and fruit variants.
        Fruit trees have specific patterns -- for simplicity, trees that are odd-coded
        (bare) get incremented to even (fruit-bearing).  This is a heuristic; the
        actual mapping depends on tree sub-type.
        """
        count = 0
        # Simple heuristic: fruit trees typically follow a pattern where
        # bare = base+1, fruit = base.  Adjust as needed for exact game data.
        for idx in range(TOTAL_TILES):
            code = self._grid._items[idx]
            # Non-fruit trees typically are at odd offsets in their group
            if 0x0001 <= code <= 0x0056:
                # If code is a bare fruit tree (odd offset from group start)
                if code % 2 == 0:
                    self._grid._items[idx] = code - 1  # fruit variant
                    count += 1
        if count:
            self._dirty = True
            self._grid._full_redraw()
        self._status(f"Replenished {count} fruit trees (heuristic).")

    def _task_restore_grass(self):
        """Set all grass values to maximum (255)."""
        self._grid._grass = [255] * TOTAL_TILES
        self._dirty = True
        if self._grid._show_grass:
            self._grid._full_redraw()
        self._status("All grass restored to maximum quality.")

    def _task_remove_grass(self):
        """Set all grass values to zero."""
        self._grid._grass = [0] * TOTAL_TILES
        self._dirty = True
        if self._grid._show_grass:
            self._grid._full_redraw()
        self._status("All grass removed.")

    # -----------------------------------------------------------------------
    # Import / Export
    # -----------------------------------------------------------------------

    def _export_layout(self):
        """Save the 80x80 town grid as a raw binary file (6400 x 2 bytes, big-endian)."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Town Layout", "town_layout.bin",
            "Binary files (*.bin);;All files (*)",
        )
        if not path:
            return
        try:
            items = self._grid.get_items()
            data = bytearray()
            for code in items:
                data += struct.pack(">H", code & 0xFFFF)
            with open(path, "wb") as f:
                f.write(data)
            self._status(f"Exported {len(items)} tiles to {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    def _import_layout(self):
        """Load a raw binary town layout (expected: 12800 bytes = 6400 x 2)."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Town Layout", "",
            "Binary files (*.bin);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            expected = TOTAL_TILES * 2
            if len(data) != expected:
                QMessageBox.warning(
                    self, "Import Warning",
                    f"File is {len(data)} bytes, expected {expected}. Truncating/padding.",
                )
            items = []
            for i in range(TOTAL_TILES):
                offset = i * 2
                if offset + 2 <= len(data):
                    code = struct.unpack(">H", data[offset:offset + 2])[0]
                else:
                    code = EMPTY_ITEM
                items.append(code)
            self._grid.set_items(items)
            self._dirty = True
            self._status(f"Imported {len(items)} tiles from {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", str(exc))

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _status(self, msg: str):
        self._status_label.setText(msg)

    def closeEvent(self, ev):
        if self._dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Discard them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                ev.ignore()
                return
        ev.accept()

    def keyPressEvent(self, ev: QKeyEvent):
        # Prevent Escape from closing the dialog without confirmation
        if ev.key() == Qt.Key.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(ev)


# ---------------------------------------------------------------------------
# Standalone test harness
# ---------------------------------------------------------------------------

class _MockSaveHandler:
    """Minimal stub for testing the editor without a real save file."""

    def __init__(self):
        import random
        self._items = [EMPTY_ITEM] * TOTAL_TILES
        # Sprinkle some sample data
        for i in range(TOTAL_TILES):
            r = random.random()
            if r < 0.05:
                self._items[i] = random.choice([0x0010, 0x0030])  # trees
            elif r < 0.07:
                self._items[i] = 0x0058  # weed
            elif r < 0.09:
                self._items[i] = random.choice([0x00A0, 0x00A5, 0x00AB])  # flowers
            elif r < 0.10:
                self._items[i] = 0x9100  # item
        self._buried = [0] * ((TOTAL_TILES + 7) // 8)
        self._grass = [random.randint(0, 255) for _ in range(TOTAL_TILES)]

    def get_town_items(self):
        return list(self._items)

    def set_town_item(self, index, value):
        self._items[index] = value

    def get_buried_items(self):
        return list(self._buried)

    def set_buried_items(self, data):
        self._buried = list(data)

    def get_grass_data(self):
        return list(self._grass)

    def set_grass_data(self, data):
        self._grass = list(data)


def main():
    app = QApplication(sys.argv)
    handler = _MockSaveHandler()
    dlg = TownEditorDialog(handler)
    dlg.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

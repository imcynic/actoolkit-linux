"""
House Room Editor Dialog for Animal Crossing: City Folk Save Editor.

Each player has one room with 3 floors. Every floor consists of two
side-by-side 16x16 grids (left and right halves) of u16 item codes.

Offsets:
    House base:    0x6DE6C
    Room stride:   0x15C0  (per player / room index 0-3)
    Floor stride:  0x458   (between floor levels within a room)
    Each floor:    2 x 256 items = 512 items = 1024 bytes
                   Left half  = first 256 items  (512 bytes)
                   Right half = next  256 items  (512 bytes)
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QLineEdit, QAbstractItemView, QHeaderView,
    QWidget, QToolButton, QButtonGroup,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QBrush, QFont

from items_db import ITEMS, CATEGORIES


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HOUSE_BASE   = 0x6DE6C
ROOM_STRIDE  = 0x15C0
FLOOR_STRIDE = 0x0458
GRID_DIM     = 16          # 16 x 16
HALF_ITEMS   = GRID_DIM * GRID_DIM   # 256 items per half
HALF_BYTES   = HALF_ITEMS * 2        # 512 bytes per half
NUM_FLOORS   = 3

CELL_SIZE    = 24           # pixels per grid cell


# ---------------------------------------------------------------------------
# Colour helpers (shared logic with inventory_editor)
# ---------------------------------------------------------------------------

def get_item_color(code: int) -> QColor:
    if 0x9000 <= code <= 0xB2E4 or 0xCE80 <= code <= 0xCF54:
        return QColor(0, 255, 255)      # Items - Cyan
    if 0xB2E5 <= code <= 0xCE50:
        return QColor(255, 255, 0)      # Furniture - Yellow
    if 0x009E <= code <= 0x00BD:
        return QColor(153, 51, 255)     # Flowers
    if 0x0057 <= code <= 0x005A:
        return QColor(0, 134, 206)      # Weeds
    if 0x0001 <= code <= 0x0056:
        return QColor(0, 255, 0)        # Trees
    if 0x00BE <= code <= 0x00DD:
        return QColor(204, 102, 153)    # Parched flowers
    if 0x0074 <= code <= 0x0093:
        return QColor(170, 221, 255)    # Patterns
    if 0x005B <= code <= 0x0073:
        return QColor(0, 0, 0)          # Rocks
    if code == 0xFFF1:
        return QColor(255, 255, 255)    # Empty
    return QColor(128, 5, 23)           # Other/building


def _item_name(code: int) -> str:
    return ITEMS.get(code, {}).get("name_ea", f"Unknown (0x{code:04X})")


def _contrasting_text(bg: QColor) -> QColor:
    lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
    return QColor(0, 0, 0) if lum > 128 else QColor(255, 255, 255)


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class HouseEditorDialog(QDialog):
    """Room editor for one player's house (3 floors, 2 halves each)."""

    TOOL_CHECK   = 0
    TOOL_REPLACE = 1
    TOOL_DELETE  = 2

    def __init__(
        self,
        save_handler,
        imode: int = 0,
        parent: Optional[QWidget] = None,
    ):
        """
        Parameters
        ----------
        save_handler : object
            Must expose ``read_u16(offset)`` and ``write_u16(offset, value)``.
        imode : int
            Room / player index (0-3).
        """
        super().__init__(parent)
        self.save_handler = save_handler
        self.room_idx = imode
        self.active_tool = self.TOOL_CHECK
        self.setWindowTitle(f"House Editor - Room {self.room_idx + 1}")

        # Working data: floor -> (left_items[256], right_items[256])
        self.floor_data: list[tuple[list[int], list[int]]] = []
        self._read_all_floors()

        # Grid widget refs: floor -> (left_table, right_table)
        self.grids: list[tuple[QTableWidget, QTableWidget]] = []

        self._build_ui()
        self._populate_all_grids()
        self._populate_tree()

        self.resize(1100, 700)

    # ------------------------------------------------------------------
    # Offset math
    # ------------------------------------------------------------------

    def _floor_base(self, floor: int) -> int:
        return HOUSE_BASE + (ROOM_STRIDE * self.room_idx) + (FLOOR_STRIDE * floor)

    # ------------------------------------------------------------------
    # Data I/O
    # ------------------------------------------------------------------

    def _read_all_floors(self):
        self.floor_data.clear()
        for floor in range(NUM_FLOORS):
            base = self._floor_base(floor)
            left: list[int] = []
            right: list[int] = []
            for i in range(HALF_ITEMS):
                left.append(self.save_handler.read_u16(base + i * 2))
            for i in range(HALF_ITEMS):
                right.append(self.save_handler.read_u16(base + HALF_BYTES + i * 2))
            self.floor_data.append((left, right))

    def _write_all_floors(self):
        for floor in range(NUM_FLOORS):
            base = self._floor_base(floor)
            left, right = self.floor_data[floor]
            for i, code in enumerate(left):
                self.save_handler.write_u16(base + i * 2, code)
            for i, code in enumerate(right):
                self.save_handler.write_u16(base + HALF_BYTES + i * 2, code)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- left side: tabs with grids ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Tool bar
        tool_bar = QHBoxLayout()
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)

        btn_check = QToolButton()
        btn_check.setText("Check")
        btn_check.setToolTip("Click a cell to see the item name")
        btn_check.setCheckable(True)
        btn_check.setChecked(True)

        btn_replace = QToolButton()
        btn_replace.setText("Replace")
        btn_replace.setToolTip("Click a cell to place the selected item")
        btn_replace.setCheckable(True)

        btn_delete = QToolButton()
        btn_delete.setText("Delete")
        btn_delete.setToolTip("Click a cell to clear it (set to Empty)")
        btn_delete.setCheckable(True)

        self.tool_group.addButton(btn_check, self.TOOL_CHECK)
        self.tool_group.addButton(btn_replace, self.TOOL_REPLACE)
        self.tool_group.addButton(btn_delete, self.TOOL_DELETE)
        self.tool_group.idToggled.connect(self._on_tool_changed)

        for btn in (btn_check, btn_replace, btn_delete):
            btn.setMinimumWidth(70)
            tool_bar.addWidget(btn)
        tool_bar.addStretch()

        left_layout.addLayout(tool_bar)

        # Tabs for each floor
        self.tabs = QTabWidget()
        for floor in range(NUM_FLOORS):
            page = QWidget()
            page_layout = QHBoxLayout(page)
            page_layout.setContentsMargins(4, 4, 4, 4)

            left_grid = self._make_grid(floor, "left")
            right_grid = self._make_grid(floor, "right")

            # Labels above each grid
            left_col = QVBoxLayout()
            left_col.addWidget(QLabel("Left Side"))
            left_col.addWidget(left_grid, stretch=1)

            right_col = QVBoxLayout()
            right_col.addWidget(QLabel("Right Side"))
            right_col.addWidget(right_grid, stretch=1)

            page_layout.addLayout(left_col, stretch=1)
            page_layout.addLayout(right_col, stretch=1)

            self.grids.append((left_grid, right_grid))
            self.tabs.addTab(page, f"Floor {floor + 1}")

        left_layout.addWidget(self.tabs, stretch=1)

        # Status label
        self.status_label = QLabel("Select a cell or item.")
        self.status_label.setStyleSheet("padding: 4px;")
        left_layout.addWidget(self.status_label)

        splitter.addWidget(left_widget)

        # --- right side: search + item tree ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search items...")
        self.search_input.returnPressed.connect(self._on_search)
        btn_search = QPushButton("Search")
        btn_search.clicked.connect(self._on_search)
        search_row.addWidget(self.search_input, stretch=1)
        search_row.addWidget(btn_search)
        right_layout.addLayout(search_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Code", "Name"])
        self.tree.setColumnWidth(0, 70)
        self.tree.setAlternatingRowColors(True)
        self.tree.currentItemChanged.connect(self._on_tree_selection)
        right_layout.addWidget(self.tree, stretch=1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter, stretch=1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_apply = QPushButton("Apply")
        btn_apply.setMinimumWidth(90)
        btn_apply.clicked.connect(self._on_apply)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setMinimumWidth(90)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_apply)
        btn_row.addWidget(btn_cancel)
        root.addLayout(btn_row)

    def _make_grid(self, floor: int, side: str) -> QTableWidget:
        grid = QTableWidget(GRID_DIM, GRID_DIM)
        grid.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Compact cells
        grid.horizontalHeader().setMinimumSectionSize(CELL_SIZE)
        grid.horizontalHeader().setDefaultSectionSize(CELL_SIZE)
        grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        grid.verticalHeader().setMinimumSectionSize(CELL_SIZE)
        grid.verticalHeader().setDefaultSectionSize(CELL_SIZE)
        grid.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

        grid.horizontalHeader().setVisible(False)
        grid.verticalHeader().setVisible(False)
        grid.setFont(QFont("Monospace", 6))
        grid.setShowGrid(True)

        # Size the widget to fit exactly
        total = GRID_DIM * CELL_SIZE + 2  # +2 for frame
        grid.setMinimumSize(QSize(total, total))
        grid.setMaximumSize(QSize(total + 20, total + 20))

        # Store metadata so the click handler knows which floor/side
        grid.setProperty("_floor", floor)
        grid.setProperty("_side", side)
        grid.cellClicked.connect(self._on_grid_cell_clicked)

        return grid

    # ------------------------------------------------------------------
    # Grid helpers
    # ------------------------------------------------------------------

    def _populate_all_grids(self):
        for floor in range(NUM_FLOORS):
            left_grid, right_grid = self.grids[floor]
            left_items, right_items = self.floor_data[floor]
            self._fill_grid(left_grid, left_items)
            self._fill_grid(right_grid, right_items)

    def _fill_grid(self, grid: QTableWidget, items: list[int]):
        grid.blockSignals(True)
        for idx, code in enumerate(items):
            row = idx // GRID_DIM
            col = idx % GRID_DIM
            self._set_cell(grid, row, col, code)
        grid.blockSignals(False)

    @staticmethod
    def _set_cell(grid: QTableWidget, row: int, col: int, code: int):
        text = f"{code:04X}"
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        bg = get_item_color(code)
        item.setBackground(QBrush(bg))
        item.setForeground(QBrush(_contrasting_text(bg)))
        item.setData(Qt.ItemDataRole.UserRole, code)
        grid.setItem(row, col, item)

    # ------------------------------------------------------------------
    # Item tree
    # ------------------------------------------------------------------

    # Human-readable category labels
    _CAT_LABELS = {
        "t_flowers": "Flowers", "t_flowers2": "Flowers (parched)",
        "t_misc": "Terrain Misc.", "t_patterns": "Patterns",
        "t_rocks": "Rocks", "t_trees": "Trees",
        "t_turnips": "Turnips", "t_weeds": "Weeds",
        "i_bells": "Bell Bags", "i_equipment": "Tools / Equipment",
        "i_fish": "Fish", "i_flooring": "Flooring",
        "i_flowers": "Flowers", "i_flowerbags": "Flower Bags",
        "i_fruits": "Fruits, Misc.", "i_glasses": "Glasses",
        "i_hats": "Hats", "i_insects": "Insects",
        "i_songs": "K.K. Songs", "i_mushrooms": "Mushrooms",
        "i_paper": "Paper", "i_seashells": "Seashells",
        "i_shirts": "Shirts", "i_umbrellas": "Umbrellas",
        "i_wallpaper": "Wallpaper", "i_series": "Series",
        "i_boxing": "Boxing Theme", "i_classroom": "Classroom Theme",
        "i_construction": "Construction Theme", "i_lab": "Mad Scientist Theme",
        "i_mario": "Mario Theme", "i_garden": "Mossy Garden Theme",
        "i_nursery": "Nursery Theme", "i_ship": "Pirate Ship Theme",
        "i_space": "Space Theme", "i_western": "Western Theme",
        "i_other1": "Other Sets 1", "i_other2": "Other Sets 2",
        "i_other3": "Other Sets 3", "i_nintendo": "Nintendo Items",
        "i_gyroids": "Gyroids", "i_fossils": "Fossils",
        "i_paintings": "Paintings", "i_plants": "Plants",
        "i_notused": "Not Used Items", "i_deluxe": "Deluxe Items",
        "a_barrier": "Barrier", "a_normal": "Normal",
        "a_ocean": "Oceanfront", "a_river": "River",
        "a_transition": "Transition",
    }

    def _populate_tree(self):
        self.tree.clear()
        for cat_key, code_list in CATEGORIES.items():
            label = self._CAT_LABELS.get(cat_key, cat_key)
            parent = QTreeWidgetItem([label, ""])
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for code in code_list:
                name = _item_name(code)
                child = QTreeWidgetItem([f"0x{code:04X}", name])
                child.setData(0, Qt.ItemDataRole.UserRole, code)
                parent.addChild(child)
            self.tree.addTopLevelItem(parent)

        # Uncategorized items
        categorized: set[int] = set()
        for codes in CATEGORIES.values():
            categorized.update(codes)
        uncategorized = [c for c in sorted(ITEMS.keys()) if c not in categorized]
        if uncategorized:
            parent = QTreeWidgetItem(["uncategorized", ""])
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for code in uncategorized:
                name = _item_name(code)
                child = QTreeWidgetItem([f"0x{code:04X}", name])
                child.setData(0, Qt.ItemDataRole.UserRole, code)
                parent.addChild(child)
            self.tree.addTopLevelItem(parent)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_tool_changed(self, tool_id: int, checked: bool):
        if checked:
            self.active_tool = tool_id

    def _on_grid_cell_clicked(self, row: int, col: int):
        grid: QTableWidget = self.sender()
        floor: int = grid.property("_floor")
        side: str = grid.property("_side")
        idx = row * GRID_DIM + col

        if side == "left":
            items = self.floor_data[floor][0]
        else:
            items = self.floor_data[floor][1]

        if self.active_tool == self.TOOL_CHECK:
            code = items[idx]
            name = _item_name(code)
            self.status_label.setText(
                f"Floor {floor+1} {side} [{row},{col}] 0x{code:04X}  -  {name}"
            )

        elif self.active_tool == self.TOOL_REPLACE:
            selected_code = self._get_tree_selected_code()
            if selected_code is None:
                self.status_label.setText("No item selected in tree.")
                return
            items[idx] = selected_code
            self._set_cell(grid, row, col, selected_code)
            name = _item_name(selected_code)
            self.status_label.setText(
                f"Placed 0x{selected_code:04X} ({name}) at "
                f"Floor {floor+1} {side} [{row},{col}]"
            )

        elif self.active_tool == self.TOOL_DELETE:
            items[idx] = 0xFFF1
            self._set_cell(grid, row, col, 0xFFF1)
            self.status_label.setText(
                f"Cleared Floor {floor+1} {side} [{row},{col}]"
            )

    def _on_tree_selection(self, current: QTreeWidgetItem, _previous):
        if current is None:
            return
        code = current.data(0, Qt.ItemDataRole.UserRole)
        if code is not None:
            name = _item_name(code)
            self.status_label.setText(f"Selected: 0x{code:04X}  -  {name}")

    def _get_tree_selected_code(self) -> Optional[int]:
        current = self.tree.currentItem()
        if current is None:
            return None
        return current.data(0, Qt.ItemDataRole.UserRole)

    def _on_search(self):
        query = self.search_input.text().strip().lower()
        if not query:
            return

        hex_code: Optional[int] = None
        try:
            if query.startswith("0x"):
                hex_code = int(query, 16)
            elif all(c in "0123456789abcdef" for c in query) and len(query) == 4:
                hex_code = int(query, 16)
        except ValueError:
            pass

        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                code = child.data(0, Qt.ItemDataRole.UserRole)
                if code is None:
                    continue
                name = _item_name(code).lower()
                matched = False
                if hex_code is not None and code == hex_code:
                    matched = True
                elif query in name:
                    matched = True
                if matched:
                    parent.setExpanded(True)
                    self.tree.setCurrentItem(child)
                    self.tree.scrollToItem(child)
                    self.status_label.setText(
                        f"Found: 0x{code:04X}  -  {_item_name(code)}"
                    )
                    return

        self.status_label.setText(
            f"No match for \"{self.search_input.text().strip()}\""
        )

    def _on_apply(self):
        try:
            self._write_all_floors()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to write house data:\n{e}")
            return
        self.accept()

"""
Inventory Editor Dialog for Animal Crossing: City Folk Save Editor.

Supports multiple inventory modes:
  0 = Pockets (3x5 = 15 items)
  1 = Drawers (32x5 = 160 items, scrollable)
  2 = Lost & Found (2x6 = 12 items)
  3 = Recycle Bin (2x6 = 12 items)
  4 = Nook's Store (6x6 = 36 items)
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QLineEdit, QAbstractItemView, QHeaderView,
    QWidget, QToolButton, QButtonGroup, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QFont

from items_db import ITEMS, CATEGORIES


# ---------------------------------------------------------------------------
# Mode configuration
# ---------------------------------------------------------------------------

MODE_CONFIG = {
    0: {"title": "Pockets",      "rows": 3,  "cols": 5, "count": 15},
    1: {"title": "Drawers",      "rows": 8, "cols": 20, "count": 160},
    2: {"title": "Lost & Found", "rows": 2,  "cols": 6, "count": 12},
    3: {"title": "Recycle Bin",  "rows": 2,  "cols": 6, "count": 12},
    4: {"title": "Nook's Store", "rows": 6,  "cols": 6, "count": 36},
}

# ---------------------------------------------------------------------------
# Colour helpers
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
    """Return black or white depending on background luminance."""
    lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
    return QColor(0, 0, 0) if lum > 128 else QColor(255, 255, 255)


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class InventoryEditorDialog(QDialog):
    """Grid-based inventory editor for ACCF saves."""

    TOOL_CHECK   = 0
    TOOL_REPLACE = 1
    TOOL_DELETE  = 2

    def __init__(
        self,
        save_handler,
        imode: int,
        player: int = 0,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.save_handler = save_handler
        self.imode = imode
        self.player = player
        self.active_tool = self.TOOL_CHECK

        cfg = MODE_CONFIG[imode]
        self.grid_rows = cfg["rows"]
        self.grid_cols = cfg["cols"]
        self.item_count = cfg["count"]
        self.setWindowTitle(f"Inventory Editor - {cfg['title']}")

        # Working copy of the item codes
        self.items: list[int] = self._read_items()

        self._build_ui()
        self._populate_grid()
        self._populate_tree()

        self.resize(960, 620)

    # ------------------------------------------------------------------
    # Data I/O helpers
    # ------------------------------------------------------------------

    def _read_items(self) -> list[int]:
        if self.imode == 0:
            return list(self.save_handler.get_pockets(self.player))
        if self.imode == 1:
            return list(self.save_handler.get_drawers(self.player))
        if self.imode == 2:
            return list(self.save_handler.get_lost_found())
        if self.imode == 3:
            return list(self.save_handler.get_recycle_bin())
        if self.imode == 4:
            return list(self.save_handler.get_nook_items())
        return []

    def _write_items(self):
        if self.imode == 0:
            self.save_handler.set_pockets(self.player, self.items)
        elif self.imode == 1:
            self.save_handler.set_drawers(self.player, self.items)
        elif self.imode == 2:
            self.save_handler.set_lost_found(self.items)
        elif self.imode == 3:
            self.save_handler.set_recycle_bin(self.items)
        elif self.imode == 4:
            self.save_handler.set_nook_items(self.items)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)

        # ---------- splitter: grid | tree ----------
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- left: grid + tools ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Tool buttons
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

        # Grid table
        self.grid = QTableWidget(self.grid_rows, self.grid_cols)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.grid.horizontalHeader().setMinimumSectionSize(52)
        self.grid.verticalHeader().setMinimumSectionSize(28)
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.grid.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.grid.verticalHeader().setDefaultSectionSize(28)
        self.grid.setFont(QFont("Monospace", 8))
        self.grid.cellClicked.connect(self._on_cell_clicked)

        # Drawers: label sections (4 drawers of 5 columns each)
        if self.imode == 1 and self.grid_cols == 20:
            headers = []
            for section in range(4):
                for col in range(5):
                    headers.append(f"D{section + 1}-{col + 1}")
            self.grid.setHorizontalHeaderLabels(headers)

        left_layout.addWidget(self.grid, stretch=1)

        # Status label
        self.status_label = QLabel("Select a cell or item.")
        self.status_label.setStyleSheet("padding: 4px;")
        left_layout.addWidget(self.status_label)

        splitter.addWidget(left_widget)

        # --- right: search + item tree ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Search bar
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
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter, stretch=1)

        # ---------- bottom buttons ----------
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

    # ------------------------------------------------------------------
    # Grid helpers
    # ------------------------------------------------------------------

    def _populate_grid(self):
        self.grid.blockSignals(True)
        for idx, code in enumerate(self.items):
            row = idx // self.grid_cols
            col = idx % self.grid_cols
            self._set_cell(row, col, code)
        self.grid.blockSignals(False)

    def _set_cell(self, row: int, col: int, code: int):
        text = f"{code:04X}"
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        bg = get_item_color(code)
        item.setBackground(QBrush(bg))
        item.setForeground(QBrush(_contrasting_text(bg)))
        item.setData(Qt.ItemDataRole.UserRole, code)
        self.grid.setItem(row, col, item)

    def _cell_index(self, row: int, col: int) -> int:
        return row * self.grid_cols + col

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
        # Group items by category
        cat_nodes: dict[str, QTreeWidgetItem] = {}
        for cat_key, code_list in CATEGORIES.items():
            label = self._CAT_LABELS.get(cat_key, cat_key)
            parent = QTreeWidgetItem([label, ""])
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            cat_nodes[cat_key] = parent
            for code in code_list:
                name = _item_name(code)
                child = QTreeWidgetItem([f"0x{code:04X}", name])
                child.setData(0, Qt.ItemDataRole.UserRole, code)
                parent.addChild(child)
            self.tree.addTopLevelItem(parent)

        # Also add any items not in a category (that exist in ITEMS dict)
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

    def _on_cell_clicked(self, row: int, col: int):
        idx = self._cell_index(row, col)
        if idx >= len(self.items):
            return

        if self.active_tool == self.TOOL_CHECK:
            code = self.items[idx]
            name = _item_name(code)
            self.status_label.setText(f"[{row},{col}] 0x{code:04X}  -  {name}")

        elif self.active_tool == self.TOOL_REPLACE:
            selected_code = self._get_tree_selected_code()
            if selected_code is None:
                self.status_label.setText("No item selected in tree.")
                return
            self.items[idx] = selected_code
            self._set_cell(row, col, selected_code)
            name = _item_name(selected_code)
            self.status_label.setText(
                f"Placed 0x{selected_code:04X} ({name}) at [{row},{col}]"
            )

        elif self.active_tool == self.TOOL_DELETE:
            self.items[idx] = 0xFFF1
            self._set_cell(row, col, 0xFFF1)
            self.status_label.setText(f"Cleared cell [{row},{col}]")

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
        code = current.data(0, Qt.ItemDataRole.UserRole)
        return code

    def _on_search(self):
        query = self.search_input.text().strip().lower()
        if not query:
            return

        # Try hex code first
        hex_code: Optional[int] = None
        try:
            if query.startswith("0x"):
                hex_code = int(query, 16)
            elif all(c in "0123456789abcdef" for c in query) and len(query) == 4:
                hex_code = int(query, 16)
        except ValueError:
            pass

        # Walk tree and find first match
        iterator = self._tree_item_iterator()
        found = False
        for tree_item in iterator:
            code = tree_item.data(0, Qt.ItemDataRole.UserRole)
            if code is None:
                continue
            name = _item_name(code).lower()
            if hex_code is not None and code == hex_code:
                found = True
            elif query in name:
                found = True
            else:
                continue

            if found:
                self.tree.setCurrentItem(tree_item)
                self.tree.scrollToItem(tree_item)
                parent = tree_item.parent()
                if parent:
                    parent.setExpanded(True)
                self.status_label.setText(
                    f"Found: 0x{code:04X}  -  {_item_name(code)}"
                )
                return

        self.status_label.setText(f"No match for \"{self.search_input.text().strip()}\"")

    def _tree_item_iterator(self):
        """Yield every leaf QTreeWidgetItem."""
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            for j in range(parent.childCount()):
                yield parent.child(j)

    def _on_apply(self):
        try:
            self._write_items()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to write inventory:\n{e}")
            return
        self.accept()

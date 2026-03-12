"""Reusable item selector widget for Animal Crossing: City Folk editors.

Provides a searchable, categorized QTreeWidget populated from the ACCF item
database.  Used by the town editor, house editor, inventory editor, and acre
editor.
"""

from __future__ import annotations

import sys
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QLineEdit,
    QPushButton,
    QLabel,
    QSizePolicy,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal

# ---------------------------------------------------------------------------
# Resolve the items database import regardless of how this module is loaded.
# ---------------------------------------------------------------------------
try:
    from items_db import ITEMS, CATEGORIES
except ImportError:
    import os
    _pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _pkg_dir not in sys.path:
        sys.path.insert(0, _pkg_dir)
    from items_db import ITEMS, CATEGORIES  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Language index -> field name in ITEMS entries.
_LANG_FIELDS: tuple[str, ...] = (
    "name_ea",  # 0: English (Americas)
    "name_sa",  # 1: Spanish (Americas)
    "name_fc",  # 2: French (Canada)
    "name_eu",  # 3: English (Europe)
    "name_se",  # 4: Spanish (Europe)
    "name_fe",  # 5: French (Europe)
    "name_it",  # 6: Italian
    "name_ge",  # 7: German
    "name_ja",  # 8: Japanese
)

# Which CATEGORIES keys belong to terrain-only items (English names only).
_TERRAIN_ONLY_CATS: frozenset[str] = frozenset((
    "t_flowers",
    "t_flowers2",
    "t_misc",
    "t_patterns",
    "t_rocks",
    "t_trees",
    "t_turnips",
    "t_weeds",
))

# Which CATEGORIES keys belong to acre entries.
_ACRE_CATS: frozenset[str] = frozenset((
    "a_barrier",
    "a_normal",
    "a_ocean",
    "a_river",
    "a_transition",
))

# ---------------------------------------------------------------------------
# Tree structure definition.
#
# Each top-level entry is (display_name, visibility_flag_name,
#   [(subcategory_display_name, CATEGORIES_key), ...])
#
# The order here matches the tree structure in the spec.
# ---------------------------------------------------------------------------

_TREE_SPEC: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("Terrain", "show_terrain", [
        ("Flowers", "t_flowers"),
        ("Flowers (parched)", "t_flowers2"),
        ("Misc.", "t_misc"),
        ("Patterns", "t_patterns"),
        ("Rocks", "t_rocks"),
        ("Trees", "t_trees"),
        ("Turnips", "t_turnips"),
        ("Weeds", "t_weeds"),
    ]),
    ("Items", "show_items", [
        ("Bell Bags", "i_bells"),
        ("Equipment", "i_equipment"),
        ("Fish", "i_fish"),
        ("Flooring", "i_flooring"),
        ("Flowers", "i_flowers"),
        ("Flower Bags", "i_flowerbags"),
        ("Fruits, Misc.", "i_fruits"),
        ("Glasses", "i_glasses"),
        ("Hats", "i_hats"),
        ("Insects", "i_insects"),
        ("K.K. Songs", "i_songs"),
        ("Mushrooms", "i_mushrooms"),
        ("Paper", "i_paper"),
        ("Seashells", "i_seashells"),
        ("Shirts", "i_shirts"),
        ("Umbrellas", "i_umbrellas"),
        ("Wallpaper", "i_wallpaper"),
        ("Deluxe Items", "i_deluxe"),
    ]),
    ("Furniture", "show_furniture", [
        ("Series", "i_series"),
        ("Boxing Theme", "i_boxing"),
        ("Classroom Theme", "i_classroom"),
        ("Construction Theme", "i_construction"),
        ("Mad Scientist Theme", "i_lab"),
        ("Mario Theme", "i_mario"),
        ("Mossy Garden Theme", "i_garden"),
        ("Nursery Theme", "i_nursery"),
        ("Pirate Ship Theme", "i_ship"),
        ("Space Theme", "i_space"),
        ("Western Theme", "i_western"),
        ("Other Sets 1", "i_other1"),
        ("Other Sets 2", "i_other2"),
        ("Other Sets 3", "i_other3"),
        ("Nintendo Items", "i_nintendo"),
        ("Gyroids", "i_gyroids"),
        ("Fossils", "i_fossils"),
        ("Paintings", "i_paintings"),
        ("Plants", "i_plants"),
        ("Not Used Items", "i_notused"),
    ]),
    ("Acres", "show_acres", [
        ("Barrier", "a_barrier"),
        ("Normal", "a_normal"),
        ("Oceanfront", "a_ocean"),
        ("River", "a_river"),
        ("Transition", "a_transition"),
    ]),
]


# ---------------------------------------------------------------------------
# ItemSelectorWidget
# ---------------------------------------------------------------------------

class ItemSelectorWidget(QWidget):
    """Searchable, categorized item-selector tree.

    Parameters
    ----------
    show_terrain : bool
        Include terrain categories (flowers, trees, rocks, ...).
    show_items : bool
        Include holdable-item categories (bells, equipment, fish, ...).
    show_furniture : bool
        Include furniture categories (series, themes, gyroids, ...).
    show_acres : bool
        Include acre categories (barrier, normal, oceanfront, ...).
    show_dlc : bool
        Reserve a "Downloaded Content" node under *Items* for DLC items.
    language : int
        Initial display language (0-8).  See module-level ``_LANG_FIELDS``.
    parent : QWidget | None
        Optional parent widget.
    """

    # Signals -----------------------------------------------------------------
    item_selected = pyqtSignal(int)
    item_double_clicked = pyqtSignal(int)

    # Construction ------------------------------------------------------------

    def __init__(
        self,
        *,
        show_terrain: bool = True,
        show_items: bool = True,
        show_furniture: bool = True,
        show_acres: bool = True,
        show_dlc: bool = True,
        language: int = 0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._show_terrain = show_terrain
        self._show_items = show_items
        self._show_furniture = show_furniture
        self._show_acres = show_acres
        self._show_dlc = show_dlc
        self._language = max(0, min(language, len(_LANG_FIELDS) - 1))

        # DLC items added dynamically via add_dlc_items().
        self._dlc_items: list[tuple[int, str]] = []

        # Map visibility flag names to booleans for easy lookup.
        self._flag_map: dict[str, bool] = {
            "show_terrain": show_terrain,
            "show_items": show_items,
            "show_furniture": show_furniture,
            "show_acres": show_acres,
        }

        self._build_ui()
        self._populate_tree()
        self._connect_signals()

    # UI construction ---------------------------------------------------------

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(4)

        # --- Tree widget ---
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setAnimated(False)
        self._tree.setIndentation(18)
        self._tree.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        root_layout.addWidget(self._tree, stretch=1)

        # --- Info label ---
        self._info_label = QLabel("No item selected")
        self._info_label.setStyleSheet("color: gray; padding: 2px 4px;")
        root_layout.addWidget(self._info_label)

        # --- Search bar ---
        search_layout = QHBoxLayout()
        search_layout.setSpacing(4)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search items...")
        self._search_input.setClearButtonEnabled(True)
        search_layout.addWidget(self._search_input, stretch=1)

        self._find_btn = QPushButton("Find")
        self._find_btn.setFixedWidth(56)
        search_layout.addWidget(self._find_btn)

        self._find_next_btn = QPushButton("Find Next")
        self._find_next_btn.setFixedWidth(72)
        search_layout.addWidget(self._find_next_btn)

        root_layout.addLayout(search_layout)

    # Signal wiring -----------------------------------------------------------

    def _connect_signals(self) -> None:
        self._tree.currentItemChanged.connect(self._on_current_changed)
        self._tree.itemDoubleClicked.connect(self._on_double_clicked)
        self._find_btn.clicked.connect(self._on_find)
        self._find_next_btn.clicked.connect(self._on_find_next)
        self._search_input.returnPressed.connect(self._on_find)

    # Tree population ---------------------------------------------------------

    def _populate_tree(self) -> None:
        """(Re-)build the entire tree from the database."""
        self._tree.setUpdatesEnabled(False)
        self._tree.clear()

        lang_field = _LANG_FIELDS[self._language]

        for top_name, flag_name, subcats in _TREE_SPEC:
            if not self._flag_map.get(flag_name, False):
                continue

            top_item = QTreeWidgetItem(self._tree, [top_name])
            top_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )
            font = top_item.font(0)
            font.setBold(True)
            top_item.setFont(0, font)

            for sub_name, cat_key in subcats:
                codes = CATEGORIES.get(cat_key)
                if codes is None:
                    continue

                # Determine if this is a terrain/acre category (English only).
                use_english_only = cat_key in _TERRAIN_ONLY_CATS or cat_key in _ACRE_CATS

                sub_item = QTreeWidgetItem(top_item, [
                    f"{sub_name} ({len(codes)})"
                ])
                sub_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )

                for code in codes:
                    info = ITEMS.get(code)
                    if info is None:
                        continue

                    if use_english_only:
                        display_name = info.get("name_ea", f"0x{code:04X}")
                    else:
                        display_name = info.get(lang_field) or info.get("name_ea", f"0x{code:04X}")

                    leaf = QTreeWidgetItem(sub_item, [
                        f"{display_name}  [0x{code:04X}]"
                    ])
                    leaf.setData(0, Qt.ItemDataRole.UserRole, code)
                    leaf.setFlags(
                        Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                    )

            # Append DLC node under Items if applicable.
            if flag_name == "show_items" and self._show_dlc and self._dlc_items:
                self._create_dlc_node(top_item, lang_field)

        self._tree.setUpdatesEnabled(True)

    def _create_dlc_node(
        self,
        parent: QTreeWidgetItem,
        lang_field: str,
    ) -> None:
        """Create or recreate the Downloaded Content node under *parent*."""
        dlc_node = QTreeWidgetItem(parent, [
            f"Downloaded Content ({len(self._dlc_items)})"
        ])
        dlc_node.setFlags(
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        )

        for code, name in self._dlc_items:
            leaf = QTreeWidgetItem(dlc_node, [f"{name}  [0x{code:04X}]"])
            leaf.setData(0, Qt.ItemDataRole.UserRole, code)
            leaf.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )

    # Selection helpers -------------------------------------------------------

    @staticmethod
    def _code_of(item: Optional[QTreeWidgetItem]) -> Optional[int]:
        """Return the item code stored on a leaf node, or ``None``."""
        if item is None:
            return None
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            return None
        return int(data)

    # Slots -------------------------------------------------------------------

    def _on_current_changed(
        self,
        current: Optional[QTreeWidgetItem],
        _previous: Optional[QTreeWidgetItem],
    ) -> None:
        code = self._code_of(current)
        if code is not None:
            info = ITEMS.get(code)
            if info:
                name = info.get("name_ea", "???")
                self._info_label.setText(f"{name}  (0x{code:04X})")
                self._info_label.setStyleSheet("padding: 2px 4px;")
            else:
                self._info_label.setText(f"0x{code:04X}")
                self._info_label.setStyleSheet("padding: 2px 4px;")
            self.item_selected.emit(code)
        else:
            self._info_label.setText("No item selected")
            self._info_label.setStyleSheet("color: gray; padding: 2px 4px;")

    def _on_double_clicked(
        self,
        item: QTreeWidgetItem,
        _column: int,
    ) -> None:
        code = self._code_of(item)
        if code is not None:
            self.item_double_clicked.emit(code)

    # Search ------------------------------------------------------------------

    def _collect_leaf_items(self) -> list[QTreeWidgetItem]:
        """Return all visible leaf items in tree order."""
        leaves: list[QTreeWidgetItem] = []
        self._tree.itemAt(0, 0)  # not needed -- use manual walk

        def _walk(parent_item: QTreeWidgetItem) -> None:
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                if child is None:
                    continue
                if child.childCount() == 0:
                    leaves.append(child)
                else:
                    _walk(child)

        for i in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(i)
            if top is not None:
                _walk(top)

        return leaves

    def _on_find(self) -> None:
        """Start a new search from the beginning of the tree."""
        query = self._search_input.text().strip().lower()
        if not query:
            return

        for leaf in self._collect_leaf_items():
            text = leaf.text(0).lower()
            if query in text:
                self._tree.setCurrentItem(leaf)
                self._tree.scrollToItem(
                    leaf, QAbstractItemView.ScrollHint.PositionAtCenter,
                )
                return

    def _on_find_next(self) -> None:
        """Continue search from after the currently selected item."""
        query = self._search_input.text().strip().lower()
        if not query:
            return

        leaves = self._collect_leaf_items()
        if not leaves:
            return

        current = self._tree.currentItem()
        start_index = 0

        if current is not None:
            try:
                idx = leaves.index(current)
                start_index = idx + 1
            except ValueError:
                pass

        # Search from start_index to end, then wrap around.
        for i in range(len(leaves)):
            leaf = leaves[(start_index + i) % len(leaves)]
            text = leaf.text(0).lower()
            if query in text:
                self._tree.setCurrentItem(leaf)
                self._tree.scrollToItem(
                    leaf, QAbstractItemView.ScrollHint.PositionAtCenter,
                )
                return

    # Public API --------------------------------------------------------------

    def get_selected_code(self) -> Optional[int]:
        """Return the hex code of the currently selected item, or ``None``."""
        return self._code_of(self._tree.currentItem())

    def select_by_code(self, code: int) -> None:
        """Find the item with *code* in the tree and select it.

        If the code appears multiple times (e.g. in both terrain and acres),
        the first occurrence is selected.
        """
        for leaf in self._collect_leaf_items():
            if self._code_of(leaf) == code:
                self._tree.setCurrentItem(leaf)
                self._tree.scrollToItem(
                    leaf, QAbstractItemView.ScrollHint.PositionAtCenter,
                )
                return

    def set_language(self, lang: int) -> None:
        """Rebuild the tree using a different display language (0-8)."""
        lang = max(0, min(lang, len(_LANG_FIELDS) - 1))
        if lang == self._language:
            return
        self._language = lang
        self._populate_tree()

    def add_dlc_items(self, dlc_list: list[tuple[int, str]]) -> None:
        """Add DLC items and rebuild the tree.

        Parameters
        ----------
        dlc_list : list of (code, display_name) tuples
            The DLC items to show under *Items > Downloaded Content*.
        """
        self._dlc_items = list(dlc_list)
        self._populate_tree()

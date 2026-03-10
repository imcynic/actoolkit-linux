"""ACToolkit main application window.

Provides the primary GUI for editing Animal Crossing: City Folk save files,
including player stats, town settings, catalog, and Nook's shop configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QTabWidget, QMenuBar, QMenu,
    QStatusBar, QFileDialog, QInputDialog, QMessageBox, QSizePolicy,
    QSpacerItem, QApplication, QDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QSize
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence, QIcon

try:
    from save_handler import SaveHandler
except ImportError:
    SaveHandler = None  # type: ignore[misc, assignment]


class PlayerInfoPanel(QGroupBox):
    """Left-side panel displaying current player statistics and action buttons."""

    wallet_set_requested = pyqtSignal()
    bank_set_requested = pyqtSignal()
    points_set_requested = pyqtSignal()
    pockets_requested = pyqtSignal()
    drawers_requested = pyqtSignal()
    appearance_requested = pyqtSignal()
    emotions_requested = pyqtSignal()
    house_requested = pyqtSignal(str)  # room letter A/B/C/D

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Player Info", parent)
        self.setMinimumWidth(280)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 16, 12, 12)

        # --- Header ---
        self.header_label = QLabel("No file loaded")
        self.header_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.header_label)

        # --- Stats grid ---
        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(8)
        stats_grid.setVerticalSpacing(6)

        row = 0
        # Wallet
        stats_grid.addWidget(QLabel("Wallet:"), row, 0, Qt.AlignmentFlag.AlignRight)
        self.wallet_label = QLabel("--- Bells")
        stats_grid.addWidget(self.wallet_label, row, 1)
        self.wallet_btn = QPushButton("Set")
        self.wallet_btn.setFixedWidth(48)
        self.wallet_btn.clicked.connect(self.wallet_set_requested)
        stats_grid.addWidget(self.wallet_btn, row, 2)

        row += 1
        # Bank
        stats_grid.addWidget(QLabel("Bank:"), row, 0, Qt.AlignmentFlag.AlignRight)
        self.bank_label = QLabel("--- Bells")
        stats_grid.addWidget(self.bank_label, row, 1)
        self.bank_btn = QPushButton("Set")
        self.bank_btn.setFixedWidth(48)
        self.bank_btn.clicked.connect(self.bank_set_requested)
        stats_grid.addWidget(self.bank_btn, row, 2)

        row += 1
        # Points
        stats_grid.addWidget(QLabel("Points:"), row, 0, Qt.AlignmentFlag.AlignRight)
        self.points_label = QLabel("---")
        stats_grid.addWidget(self.points_label, row, 1)
        self.points_btn = QPushButton("Set")
        self.points_btn.setFixedWidth(48)
        self.points_btn.clicked.connect(self.points_set_requested)
        stats_grid.addWidget(self.points_btn, row, 2)

        row += 1
        # Town
        stats_grid.addWidget(QLabel("Town:"), row, 0, Qt.AlignmentFlag.AlignRight)
        self.town_label = QLabel("---")
        stats_grid.addWidget(self.town_label, row, 1)

        row += 1
        # Donations
        stats_grid.addWidget(QLabel("Donations:"), row, 0, Qt.AlignmentFlag.AlignRight)
        self.donations_label = QLabel("--- Bells")
        stats_grid.addWidget(self.donations_label, row, 1)

        layout.addLayout(stats_grid)

        # --- Separator ---
        layout.addSpacing(8)

        # --- Action buttons ---
        btn_grid = QGridLayout()
        btn_grid.setSpacing(6)

        self.pockets_btn = QPushButton("Pockets")
        self.drawers_btn = QPushButton("Drawers")
        self.appearance_btn = QPushButton("Appearance")
        self.emotions_btn = QPushButton("Emotions")

        self.pockets_btn.clicked.connect(self.pockets_requested)
        self.drawers_btn.clicked.connect(self.drawers_requested)
        self.appearance_btn.clicked.connect(self.appearance_requested)
        self.emotions_btn.clicked.connect(self.emotions_requested)

        btn_grid.addWidget(self.pockets_btn, 0, 0)
        btn_grid.addWidget(self.drawers_btn, 0, 1)
        btn_grid.addWidget(self.appearance_btn, 1, 0)
        btn_grid.addWidget(self.emotions_btn, 1, 1)

        layout.addLayout(btn_grid)

        # --- House buttons ---
        house_layout = QHBoxLayout()
        house_layout.setSpacing(6)
        self.house_buttons: dict[str, QPushButton] = {}
        for room in ("A", "B", "C", "D"):
            btn = QPushButton(f"House {room}")
            btn.clicked.connect(lambda checked, r=room: self.house_requested.emit(r))
            house_layout.addWidget(btn)
            self.house_buttons[room] = btn
        layout.addLayout(house_layout)

        layout.addStretch()

    # --- Public update methods ---

    def set_player_info(
        self,
        index: int,
        name: str,
        wallet: int,
        bank: int,
        points: int,
        town: str,
        donations: int,
    ) -> None:
        self.header_label.setText(f"Resident {index + 1} ({name})")
        self.wallet_label.setText(f"{wallet:,} Bells")
        self.bank_label.setText(f"{bank:,} Bells")
        self.points_label.setText(f"{points:,}")
        self.town_label.setText(town)
        self.donations_label.setText(f"{donations:,} Bells")

    def clear_info(self) -> None:
        self.header_label.setText("No file loaded")
        for lbl in (self.wallet_label, self.bank_label, self.points_label,
                     self.town_label, self.donations_label):
            lbl.setText("---")


class MainWindow(QMainWindow):
    """Primary application window for ACToolkit."""

    WALLET_MAX = 99_999
    BANK_MAX = 999_999_999
    POINTS_MAX = 999_999

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.save_handler: Optional[SaveHandler] = SaveHandler() if SaveHandler else None  # type: ignore[assignment]
        self.current_player: int = 0

        self._setup_window()
        self._build_menus()
        self._build_central_widget()
        self._build_status_bar()
        self._connect_signals()
        self._set_file_dependent_state(False)

    # ------------------------------------------------------------------
    # Window setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.setWindowTitle("ACToolkit - Animal Crossing: City Folk Save Editor")
        self.setMinimumSize(QSize(800, 600))
        self.resize(960, 640)

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _build_menus(self) -> None:
        menubar = self.menuBar()
        assert menubar is not None

        # --- File ---
        file_menu = menubar.addMenu("&File")
        assert file_menu is not None

        self.action_open = QAction("&Open...", self)
        self.action_open.setShortcut(QKeySequence.StandardKey.Open)
        file_menu.addAction(self.action_open)

        self.action_save = QAction("&Save", self)
        self.action_save.setShortcut(QKeySequence.StandardKey.Save)
        file_menu.addAction(self.action_save)

        self.action_save_as = QAction("Save &As...", self)
        self.action_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        file_menu.addAction(self.action_save_as)

        file_menu.addSeparator()

        self.action_exit = QAction("E&xit", self)
        self.action_exit.setShortcut(QKeySequence("Ctrl+Q"))
        file_menu.addAction(self.action_exit)

        # --- Player ---
        self.player_menu = menubar.addMenu("&Player")
        assert self.player_menu is not None
        self.player_action_group = QActionGroup(self)
        self.player_actions: list[QAction] = []
        for i in range(4):
            action = QAction(f"Player &{i + 1}", self)
            action.setCheckable(True)
            action.setEnabled(False)
            action.setData(i)
            self.player_action_group.addAction(action)
            self.player_menu.addAction(action)
            self.player_actions.append(action)
        self.player_actions[0].setChecked(True)

        # --- Town ---
        town_menu = menubar.addMenu("&Town")
        assert town_menu is not None

        self.action_town_editor = QAction("Town &Editor...", self)
        town_menu.addAction(self.action_town_editor)

        self.action_acre_editor = QAction("&Acre Editor...", self)
        town_menu.addAction(self.action_acre_editor)

        self.action_map_view = QAction("&Grass Editor...", self)
        town_menu.addAction(self.action_map_view)

        self.action_building_editor = QAction("&Building Editor...", self)
        town_menu.addAction(self.action_building_editor)

        self.action_npc_editor = QAction("&Villager Editor...", self)
        town_menu.addAction(self.action_npc_editor)

        self.action_stalk_editor = QAction("&Stalk Market...", self)
        town_menu.addAction(self.action_stalk_editor)

        self.action_museum_editor = QAction("&Museum && Encyclopedia...", self)
        town_menu.addAction(self.action_museum_editor)

        self.action_pattern_editor = QAction("&Pattern Editor...", self)
        town_menu.addAction(self.action_pattern_editor)

        self.action_letter_viewer = QAction("Mai&l Viewer...", self)
        town_menu.addAction(self.action_letter_viewer)

        self.action_dlc_editor = QAction("&DLC Editor...", self)
        town_menu.addAction(self.action_dlc_editor)

        town_menu.addSeparator()

        self.action_lost_found = QAction("&Lost && Found...", self)
        town_menu.addAction(self.action_lost_found)

        self.action_recycle_bin = QAction("&Recycle Bin...", self)
        town_menu.addAction(self.action_recycle_bin)

        town_menu.addSeparator()

        self.action_remove_weeds = QAction("Remove &Weeds", self)
        town_menu.addAction(self.action_remove_weeds)

        self.action_revive_flowers = QAction("Revive &Flowers", self)
        town_menu.addAction(self.action_revive_flowers)

        self.action_replenish_fruit = QAction("Replenish Fr&uit", self)
        town_menu.addAction(self.action_replenish_fruit)

        self.action_restore_grass = QAction("Restore &Grass", self)
        town_menu.addAction(self.action_restore_grass)

        self.action_remove_grass = QAction("Remove Gra&ss", self)
        town_menu.addAction(self.action_remove_grass)

        # --- Nook's ---
        nook_menu = menubar.addMenu("&Nook's")
        assert nook_menu is not None

        self.action_nook_items = QAction("Nook's &Items...", self)
        nook_menu.addAction(self.action_nook_items)

        self.action_clear_sold_out = QAction("&Clear Sold-out Flags", self)
        nook_menu.addAction(self.action_clear_sold_out)

        nook_menu.addSeparator()

        self.nook_style_group = QActionGroup(self)
        self.nook_style_actions: list[QAction] = []
        nook_styles = ["Nook's &Cranny", "Nook 'n' &Go", "Nook&way", "Nooking&ton's"]
        for idx, name in enumerate(nook_styles):
            action = QAction(name, self)
            action.setCheckable(True)
            action.setData(idx)
            self.nook_style_group.addAction(action)
            nook_menu.addAction(action)
            self.nook_style_actions.append(action)
        self.nook_style_actions[0].setChecked(True)

        # --- Catalog ---
        catalog_menu = menubar.addMenu("&Catalog")
        assert catalog_menu is not None

        self.action_fill_catalog = QAction("Fill &Catalog", self)
        catalog_menu.addAction(self.action_fill_catalog)

        self.action_fill_music = QAction("Fill &Music", self)
        catalog_menu.addAction(self.action_fill_music)

        # --- Settings ---
        settings_menu = menubar.addMenu("S&ettings")
        assert settings_menu is not None

        # Gate Style sub-menu
        gate_submenu = settings_menu.addMenu("&Gate Style")
        assert gate_submenu is not None
        self.gate_style_group = QActionGroup(self)
        self.gate_style_actions: list[QAction] = []
        for idx, style in enumerate(("&Stone", "&Wood", "&Brick")):
            action = QAction(style, self)
            action.setCheckable(True)
            action.setData(idx)
            self.gate_style_group.addAction(action)
            gate_submenu.addAction(action)
            self.gate_style_actions.append(action)
        self.gate_style_actions[0].setChecked(True)

        # Grass Style sub-menu
        grass_submenu = settings_menu.addMenu("G&rass Style")
        assert grass_submenu is not None
        self.grass_style_group = QActionGroup(self)
        self.grass_style_actions: list[QAction] = []
        for idx in range(3):
            action = QAction(f"Style &{idx + 1}", self)
            action.setCheckable(True)
            action.setData(idx)
            self.grass_style_group.addAction(action)
            grass_submenu.addAction(action)
            self.grass_style_actions.append(action)
        self.grass_style_actions[0].setChecked(True)

        # --- Help ---
        help_menu = menubar.addMenu("&Help")
        assert help_menu is not None

        self.action_about = QAction("&About", self)
        help_menu.addAction(self.action_about)

    # ------------------------------------------------------------------
    # Central widget
    # ------------------------------------------------------------------

    def _build_central_widget(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Left panel
        self.player_panel = PlayerInfoPanel()
        main_layout.addWidget(self.player_panel)

        # Right panel -- tabbed area / stretch
        self.tab_widget = QTabWidget()
        self.tab_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )

        placeholder = QWidget()
        placeholder_layout = QVBoxLayout(placeholder)
        placeholder_label = QLabel("Open a save file to begin editing.")
        placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_label.setStyleSheet("color: gray; font-size: 13px;")
        placeholder_layout.addWidget(placeholder_label)

        self.tab_widget.addTab(placeholder, "Overview")
        main_layout.addWidget(self.tab_widget, stretch=1)

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _build_status_bar(self) -> None:
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.file_label = QLabel("No file loaded")
        self.mod_label = QLabel("")
        self.status_bar.addWidget(self.file_label, stretch=1)
        self.status_bar.addPermanentWidget(self.mod_label)

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        # File menu
        self.action_open.triggered.connect(self._on_open)
        self.action_save.triggered.connect(self._on_save)
        self.action_save_as.triggered.connect(self._on_save_as)
        self.action_exit.triggered.connect(self.close)

        # Player menu
        self.player_action_group.triggered.connect(self._on_player_switched)

        # Town menu
        self.action_town_editor.triggered.connect(self._on_town_editor)
        self.action_acre_editor.triggered.connect(self._on_acre_editor)
        self.action_map_view.triggered.connect(self._on_grass_editor)
        self.action_building_editor.triggered.connect(self._on_building_editor)
        self.action_npc_editor.triggered.connect(self._on_npc_editor)
        self.action_stalk_editor.triggered.connect(self._on_stalk_editor)
        self.action_museum_editor.triggered.connect(self._on_museum_editor)
        self.action_pattern_editor.triggered.connect(self._on_pattern_editor)
        self.action_letter_viewer.triggered.connect(self._on_letter_viewer)
        self.action_dlc_editor.triggered.connect(self._on_dlc_editor)
        self.action_lost_found.triggered.connect(self._on_lost_found)
        self.action_recycle_bin.triggered.connect(self._on_recycle_bin)
        self.action_remove_weeds.triggered.connect(lambda: self._town_action("remove_weeds"))
        self.action_revive_flowers.triggered.connect(lambda: self._town_action("revive_flowers"))
        self.action_replenish_fruit.triggered.connect(lambda: self._town_action("replenish_fruit"))
        self.action_restore_grass.triggered.connect(lambda: self._town_action("restore_grass"))
        self.action_remove_grass.triggered.connect(lambda: self._town_action("remove_grass"))

        # Nook's menu
        self.action_nook_items.triggered.connect(self._on_nook_items)
        self.action_clear_sold_out.triggered.connect(self._on_clear_sold_out)
        self.nook_style_group.triggered.connect(self._on_nook_style_changed)

        # Catalog menu
        self.action_fill_catalog.triggered.connect(self._on_fill_catalog)
        self.action_fill_music.triggered.connect(self._on_fill_music)

        # Settings menu
        self.gate_style_group.triggered.connect(self._on_gate_style_changed)
        self.grass_style_group.triggered.connect(self._on_grass_style_changed)

        # Help menu
        self.action_about.triggered.connect(self._on_about)

        # Player info panel
        self.player_panel.wallet_set_requested.connect(self._on_set_wallet)
        self.player_panel.bank_set_requested.connect(self._on_set_bank)
        self.player_panel.points_set_requested.connect(self._on_set_points)
        self.player_panel.pockets_requested.connect(self._on_pockets)
        self.player_panel.drawers_requested.connect(self._on_drawers)
        self.player_panel.appearance_requested.connect(self._on_appearance)
        self.player_panel.emotions_requested.connect(self._on_emotions)
        self.player_panel.house_requested.connect(self._on_house)

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _set_file_dependent_state(self, enabled: bool) -> None:
        """Enable or disable controls that require a loaded save file."""
        self.action_save.setEnabled(enabled)
        self.action_save_as.setEnabled(enabled)
        self.action_town_editor.setEnabled(enabled)
        self.action_acre_editor.setEnabled(enabled)
        self.action_map_view.setEnabled(enabled)
        self.action_building_editor.setEnabled(enabled)
        self.action_npc_editor.setEnabled(enabled)
        self.action_stalk_editor.setEnabled(enabled)
        self.action_museum_editor.setEnabled(enabled)
        self.action_pattern_editor.setEnabled(enabled)
        self.action_letter_viewer.setEnabled(enabled)
        self.action_dlc_editor.setEnabled(enabled)
        self.action_lost_found.setEnabled(enabled)
        self.action_recycle_bin.setEnabled(enabled)
        self.action_remove_weeds.setEnabled(enabled)
        self.action_revive_flowers.setEnabled(enabled)
        self.action_replenish_fruit.setEnabled(enabled)
        self.action_restore_grass.setEnabled(enabled)
        self.action_remove_grass.setEnabled(enabled)
        self.action_nook_items.setEnabled(enabled)
        self.action_clear_sold_out.setEnabled(enabled)
        self.action_fill_catalog.setEnabled(enabled)
        self.action_fill_music.setEnabled(enabled)

        for action in self.nook_style_actions:
            action.setEnabled(enabled)
        for action in self.gate_style_actions:
            action.setEnabled(enabled)
        for action in self.grass_style_actions:
            action.setEnabled(enabled)

    def _game_display_name(self) -> str:
        """Return a human-readable name for the loaded game type."""
        if self.save_handler and self.save_handler.profile:
            return self.save_handler.profile.display_name
        return "Animal Crossing: City Folk"

    def _update_title_bar(self) -> None:
        base = "ACToolkit - Animal Crossing Save Editor"
        if self.save_handler and self.save_handler.filepath:
            name = Path(self.save_handler.filepath).name
            game = self._game_display_name()
            deluxe = " [Deluxe]" if getattr(self, "_is_deluxe", False) else ""
            mod = " *" if self.save_handler.modified else ""
            self.setWindowTitle(f"{base} - {name} ({game}){deluxe}{mod}")
        else:
            self.setWindowTitle(base)

    def _update_status_bar(self) -> None:
        if self.save_handler and self.save_handler.filepath:
            game = self._game_display_name()
            deluxe = " [Deluxe]" if getattr(self, "_is_deluxe", False) else ""
            self.file_label.setText(f"{self.save_handler.filepath} ({game}{deluxe})")
            self.mod_label.setText("Modified" if self.save_handler.modified else "")
        else:
            self.file_label.setText("No file loaded")
            self.mod_label.setText("")

    def _apply_game_type_restrictions(self) -> None:
        """Disable menu items that don't apply to the loaded game type."""
        if not self.save_handler:
            return
        is_gc = self.save_handler.is_gc

        # GC doesn't have these features
        self.action_dlc_editor.setEnabled(not is_gc)
        self.action_museum_editor.setEnabled(not is_gc)
        self.action_letter_viewer.setEnabled(not is_gc)
        self.action_pattern_editor.setEnabled(not is_gc)  # TODO: add GC pattern support
        self.action_restore_grass.setEnabled(not is_gc)
        self.action_remove_grass.setEnabled(not is_gc)
        self.action_fill_catalog.setEnabled(not is_gc)
        self.action_fill_music.setEnabled(not is_gc)

        # Buildings are different on GC
        # self.action_building_editor.setEnabled(not is_gc)  # TODO: adapt

        # Nook's style is different on GC
        for action in self.nook_style_actions:
            action.setEnabled(not is_gc)

    def _merge_deluxe_items(self) -> None:
        """Merge Deluxe Edition items into the global items_db when a Deluxe save is detected."""
        try:
            import items_db
            from deluxe_items import DELUXE_ITEMS, PREVIOUSLY_UNOBTAINABLE
            items_db.ITEMS.update(DELUXE_ITEMS)
            items_db.ITEMS.update(PREVIOUSLY_UNOBTAINABLE)
        except Exception:
            pass

    def _refresh_player_info(self) -> None:
        """Reload the player info panel from the save handler."""
        if not self.save_handler or not self.save_handler.filepath:
            self.player_panel.clear_info()
            return

        p = self.current_player
        if not self.save_handler.player_exists(p):
            self.player_panel.clear_info()
            return

        self.player_panel.set_player_info(
            index=p,
            name=self.save_handler.get_player_name(p),
            wallet=self.save_handler.get_wallet(p),
            bank=self.save_handler.get_bank(p),
            points=self.save_handler.get_points(p),
            town=self.save_handler.get_town_name(p),
            donations=self.save_handler.get_donation(),
        )

    def _sync_settings_menus(self) -> None:
        """Sync radio menus to match current save data."""
        if not self.save_handler:
            return

        nook = self.save_handler.get_nook_style() % 4  # values 4-7 map to 0-3
        if 0 <= nook < len(self.nook_style_actions):
            self.nook_style_actions[nook].setChecked(True)

        gate = self.save_handler.get_gate_style()
        if 0 <= gate < len(self.gate_style_actions):
            self.gate_style_actions[gate].setChecked(True)

        grass = self.save_handler.get_grass_style()
        if 0 <= grass < len(self.grass_style_actions):
            self.grass_style_actions[grass].setChecked(True)

    def _enable_player_menus(self) -> None:
        """Enable player radio actions based on which players exist."""
        if not self.save_handler:
            return

        first_valid: Optional[int] = None
        for i, action in enumerate(self.player_actions):
            exists = self.save_handler.player_exists(i)
            action.setEnabled(exists)
            if exists and first_valid is None:
                first_valid = i

        if first_valid is not None:
            self.player_actions[first_valid].setChecked(True)
            self.current_player = first_valid

    # ------------------------------------------------------------------
    # File actions
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Save File",
            "",
            "AC Save Files (*.dat *.bin *.sav *.gci *.gcs);;All Files (*)",
        )
        if not path:
            return

        if not self.save_handler:
            QMessageBox.critical(self, "Error", "Save handler is not available.")
            return

        if not self.save_handler.open(path):
            QMessageBox.critical(self, "Error", f"Failed to open:\n{path}")
            return

        # Detect Deluxe save early (before CRC warning, so we can contextualise)
        self._is_deluxe = False
        try:
            if self.save_handler.is_accf:
                from deluxe_items import is_deluxe_save
                self._is_deluxe = is_deluxe_save(self.save_handler)
            else:
                from game_profiles import GameType
                self._is_deluxe = self.save_handler.game_type in (
                    GameType.GC_DELUXE, GameType.WII_ACCF_DELUXE,
                )
        except Exception:
            pass

        # Checksum verification with Deluxe-aware messaging
        try:
            crc_errors: list[str] = self.save_handler.check_all_crc()
        except Exception:
            crc_errors = ["(checksum computation failed — file may be truncated)"]
        if crc_errors:
            dlc_only = all("DLC" in e for e in crc_errors)
            detail = "\n".join(crc_errors)
            if dlc_only and self._is_deluxe:
                QMessageBox.information(
                    self,
                    "DLC Checksum Notice",
                    f"DLC checksum mismatch detected:\n\n{detail}\n\n"
                    "This is expected for Deluxe / modded saves whose DLC "
                    "region has been modified by the mod. Your save is fine.",
                )
            else:
                msg = f"The following checksum checks failed:\n\n{detail}\n\n"
                if self._is_deluxe and any("DLC" in e for e in crc_errors):
                    non_dlc = [e for e in crc_errors if "DLC" not in e]
                    msg += (
                        "Note: DLC checksum mismatches are expected on "
                        "Deluxe / modded saves.\n"
                    )
                    if non_dlc:
                        msg += (
                            "However, other checksums also failed — "
                            "the file may be corrupted.\n"
                        )
                else:
                    msg += "The file may be corrupted. Proceed with caution."
                QMessageBox.warning(self, "Checksum Warning", msg)

        if self._is_deluxe and self.save_handler.is_accf:
            self._merge_deluxe_items()

        self._set_file_dependent_state(True)
        self._apply_game_type_restrictions()
        self._enable_player_menus()
        self._sync_settings_menus()
        self._refresh_player_info()

        self._update_title_bar()
        self._update_status_bar()

    @pyqtSlot()
    def _on_save(self) -> None:
        if not self.save_handler:
            return
        try:
            self.save_handler.save()
            self._update_title_bar()
            self._update_status_bar()
            self.status_bar.showMessage("File saved successfully.", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")

    @pyqtSlot()
    def _on_save_as(self) -> None:
        if not self.save_handler:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save As",
            "",
            "ACCF Save Files (*.dat *.bin *.sav);;All Files (*)",
        )
        if not path:
            return
        try:
            self.save_handler.save_as(path)
            self._update_title_bar()
            self._update_status_bar()
            self.status_bar.showMessage(f"File saved to {path}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")

    # ------------------------------------------------------------------
    # Player switching
    # ------------------------------------------------------------------

    @pyqtSlot(QAction)
    def _on_player_switched(self, action: QAction) -> None:
        player_index = action.data()
        if player_index is None:
            return
        self.current_player = int(player_index)
        self._refresh_player_info()

    # ------------------------------------------------------------------
    # Set Wallet / Bank / Points
    # ------------------------------------------------------------------

    def _input_value(self, title: str, label: str, current: int, maximum: int) -> Optional[int]:
        value, ok = QInputDialog.getInt(
            self, title, label, current, 0, maximum,
        )
        return value if ok else None

    @pyqtSlot()
    def _on_set_wallet(self) -> None:
        if not self.save_handler:
            return
        p = self.current_player
        current = self.save_handler.get_wallet(p)
        value = self._input_value("Set Wallet", "Bells (0 - 99,999):", current, self.WALLET_MAX)
        if value is not None:
            self.save_handler.set_wallet(p, value)
            self._refresh_player_info()
            self._mark_modified()

    @pyqtSlot()
    def _on_set_bank(self) -> None:
        if not self.save_handler:
            return
        p = self.current_player
        current = self.save_handler.get_bank(p)
        value = self._input_value("Set Bank", "Bells (0 - 999,999,999):", current, self.BANK_MAX)
        if value is not None:
            self.save_handler.set_bank(p, value)
            self._refresh_player_info()
            self._mark_modified()

    @pyqtSlot()
    def _on_set_points(self) -> None:
        if not self.save_handler:
            return
        p = self.current_player
        current = self.save_handler.get_points(p)
        value = self._input_value("Set Points", "Points (0 - 999,999):", current, self.POINTS_MAX)
        if value is not None:
            self.save_handler.set_points(p, value)
            self._refresh_player_info()
            self._mark_modified()

    # ------------------------------------------------------------------
    # Nook's
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_clear_sold_out(self) -> None:
        if not self.save_handler:
            return
        self.save_handler.clear_sold_out_flags()
        self._mark_modified()
        self.status_bar.showMessage("Sold-out flags cleared.", 3000)

    @pyqtSlot(QAction)
    def _on_nook_style_changed(self, action: QAction) -> None:
        if not self.save_handler:
            return
        style = action.data()
        if style is not None:
            self.save_handler.set_nook_style(int(style))
            self._mark_modified()

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_fill_catalog(self) -> None:
        if not self.save_handler:
            return
        p = self.current_player
        from save_handler import CATALOG_RANGES
        for name, (start, end) in CATALOG_RANGES.items():
            if name != "music":
                self.save_handler.fill_catalog(p, start, end)
        self._mark_modified()
        self.status_bar.showMessage("Catalog filled.", 3000)

    @pyqtSlot()
    def _on_fill_music(self) -> None:
        if not self.save_handler:
            return
        p = self.current_player
        from save_handler import CATALOG_RANGES
        start, end = CATALOG_RANGES["music"]
        self.save_handler.fill_catalog(p, start, end)
        self._mark_modified()
        self.status_bar.showMessage("Music catalog filled.", 3000)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    @pyqtSlot(QAction)
    def _on_gate_style_changed(self, action: QAction) -> None:
        if not self.save_handler:
            return
        style = action.data()
        if style is not None:
            self.save_handler.set_gate_style(int(style))
            self._mark_modified()

    @pyqtSlot(QAction)
    def _on_grass_style_changed(self, action: QAction) -> None:
        if not self.save_handler:
            return
        style = action.data()
        if style is not None:
            self.save_handler.set_grass_style(int(style))
            self._mark_modified()

    # ------------------------------------------------------------------
    # Town actions
    # ------------------------------------------------------------------

    def _town_action(self, action_name: str) -> None:
        """Execute a bulk town modification."""
        if not self.save_handler:
            return
        items = self.save_handler.get_town_items()
        count = 0
        for i, code in enumerate(items):
            if action_name == "remove_weeds" and 0x0057 <= code <= 0x005A:
                self.save_handler.set_town_item(i, 0xFFF1)
                count += 1
            elif action_name == "remove_weeds" and 0x00DE <= code <= 0x00E1:
                self.save_handler.set_town_item(i, 0xFFF1)
                count += 1
            elif action_name == "revive_flowers" and 0x00BE <= code <= 0x00DD:
                # Parched flower -> normal flower (subtract 0x20)
                self.save_handler.set_town_item(i, code - 0x20)
                count += 1
            elif action_name == "replenish_fruit":
                # Bare fruit trees (0x0019-0x0020) -> fruiting (0x0003-0x000A)
                if 0x0019 <= code <= 0x0020:
                    self.save_handler.set_town_item(i, code - 0x16)
                    count += 1
        if action_name == "restore_grass":
            grass = [255] * 6400
            self.save_handler.set_grass_data(grass)
            count = 6400
        elif action_name == "remove_grass":
            grass = [0] * 6400
            self.save_handler.set_grass_data(grass)
            count = 6400
        self._mark_modified()
        labels = {
            "remove_weeds": "Remove Weeds",
            "revive_flowers": "Revive Flowers",
            "replenish_fruit": "Replenish Fruit",
            "restore_grass": "Restore Grass",
            "remove_grass": "Remove Grass",
        }
        self.status_bar.showMessage(f"{labels.get(action_name, action_name)}: {count} tiles modified.", 3000)

    # ------------------------------------------------------------------
    # Editor dialogs
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_town_editor(self) -> None:
        if not self.save_handler:
            return
        from gui.town_editor import TownEditorDialog
        dlg = TownEditorDialog(self.save_handler, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_modified()

    @pyqtSlot()
    def _on_acre_editor(self) -> None:
        if not self.save_handler:
            return
        from gui.acre_editor import AcreEditorDialog
        dlg = AcreEditorDialog(self.save_handler, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_modified()

    @pyqtSlot()
    def _on_grass_editor(self) -> None:
        if not self.save_handler:
            return
        from gui.grass_editor import GrassEditorDialog
        dlg = GrassEditorDialog(self.save_handler, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_modified()

    @pyqtSlot()
    def _on_building_editor(self) -> None:
        if not self.save_handler:
            return
        from gui.building_editor import BuildingEditorDialog
        dlg = BuildingEditorDialog(self.save_handler, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_modified()

    @pyqtSlot()
    def _on_npc_editor(self) -> None:
        if not self.save_handler:
            return
        from gui.npc_editor import NpcEditorDialog
        # Try to load pack.bin from same directory as the save file
        npc_db = None
        try:
            from npc_data import load_pack_bin
            if self.save_handler.filepath:
                save_dir = self.save_handler.filepath.parent
                for candidate in (
                    save_dir / "pack.bin",
                    save_dir / "Npc" / "Normal" / "Setup" / "pack.bin",
                ):
                    if candidate.is_file():
                        npc_db = load_pack_bin(candidate)
                        break
        except Exception:
            pass
        dlg = NpcEditorDialog(self.save_handler, npc_db=npc_db, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_modified()

    @pyqtSlot()
    def _on_stalk_editor(self) -> None:
        if not self.save_handler:
            return
        from gui.stalk_editor import StalkEditorDialog
        dlg = StalkEditorDialog(self.save_handler, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_modified()

    @pyqtSlot()
    def _on_museum_editor(self) -> None:
        if not self.save_handler:
            return
        from gui.museum_editor import MuseumEditorDialog
        dlg = MuseumEditorDialog(self.save_handler, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_modified()

    @pyqtSlot()
    def _on_pattern_editor(self) -> None:
        if not self.save_handler:
            return
        from gui.pattern_editor import PatternEditorDialog
        dlg = PatternEditorDialog(self.save_handler, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_modified()

    @pyqtSlot()
    def _on_letter_viewer(self) -> None:
        if not self.save_handler:
            return
        from gui.letter_viewer import LetterViewerDialog
        dlg = LetterViewerDialog(self.save_handler, parent=self)
        dlg.exec()

    @pyqtSlot()
    def _on_dlc_editor(self) -> None:
        if not self.save_handler:
            return
        from gui.dlc_editor import DlcEditorDialog
        dlg = DlcEditorDialog(self.save_handler, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_modified()

    @pyqtSlot()
    def _on_lost_found(self) -> None:
        if not self.save_handler:
            return
        from gui.inventory_editor import InventoryEditorDialog
        dlg = InventoryEditorDialog(self.save_handler, imode=2, player=self.current_player, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_modified()

    @pyqtSlot()
    def _on_recycle_bin(self) -> None:
        if not self.save_handler:
            return
        from gui.inventory_editor import InventoryEditorDialog
        dlg = InventoryEditorDialog(self.save_handler, imode=3, player=self.current_player, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_modified()

    @pyqtSlot()
    def _on_nook_items(self) -> None:
        if not self.save_handler:
            return
        from gui.inventory_editor import InventoryEditorDialog
        dlg = InventoryEditorDialog(self.save_handler, imode=4, player=self.current_player, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_modified()

    @pyqtSlot()
    def _on_pockets(self) -> None:
        if not self.save_handler:
            return
        from gui.inventory_editor import InventoryEditorDialog
        dlg = InventoryEditorDialog(self.save_handler, imode=0, player=self.current_player, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_player_info()
            self._mark_modified()

    @pyqtSlot()
    def _on_drawers(self) -> None:
        if not self.save_handler:
            return
        from gui.inventory_editor import InventoryEditorDialog
        dlg = InventoryEditorDialog(self.save_handler, imode=1, player=self.current_player, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_modified()

    @pyqtSlot()
    def _on_appearance(self) -> None:
        if not self.save_handler:
            return
        from gui.face_editor import FaceEditorDialog
        dlg = FaceEditorDialog(self.save_handler, self.current_player, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_modified()

    @pyqtSlot()
    def _on_emotions(self) -> None:
        if not self.save_handler:
            return
        from gui.emotions_editor import EmotionsEditorDialog
        dlg = EmotionsEditorDialog(self.save_handler, self.current_player, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_modified()

    @pyqtSlot(str)
    def _on_house(self, room: str) -> None:
        if not self.save_handler:
            return
        room_map = {"A": 0, "B": 1, "C": 2, "D": 3}
        room_idx = room_map.get(room, 0)
        from gui.house_editor import HouseEditorDialog
        dlg = HouseEditorDialog(self.save_handler, imode=room_idx, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_modified()

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About ACToolkit",
            "<h3>ACToolkit v2.0.0</h3>"
            "<p>Animal Crossing: City Folk Save Editor for Linux</p>"
            "<p>Supports vanilla ACCF and ACCF Deluxe Edition v1.1.2</p>"
            "<p>Built with PyQt6. Based on original ACToolkit by Virus (Game-Hackers.com).</p>",
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _mark_modified(self) -> None:
        if self.save_handler:
            self.save_handler.modified = True
        self._update_title_bar()
        self._update_status_bar()

    # ------------------------------------------------------------------
    # Close event
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.save_handler and self.save_handler.modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before exiting?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if reply == QMessageBox.StandardButton.Save:
                self._on_save()
                event.accept()
            elif reply == QMessageBox.StandardButton.Discard:
                event.accept()
            else:
                event.ignore()
                return
        super().closeEvent(event)

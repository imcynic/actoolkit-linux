"""
Museum & Encyclopedia Editor Dialog for Animal Crossing: City Folk Save Editor.

Displays donation counts for Fossils, Fish, Insects, and Art across the four
museum wings.  Provides bulk fill/clear actions and encyclopedia completion.

Each museum category stores nibble values per slot: 0 = not donated,
1-4 = donated by player 1-4.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QComboBox, QGroupBox,
    QWidget, QMessageBox, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from save_handler import SaveHandler


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MUSEUM_CATEGORIES = {
    "Fossils":  {"total": 60, "getter": "get_museum_fossils"},
    "Fish":     {"total": 64, "getter": "get_museum_fish"},
    "Insects":  {"total": 64, "getter": "get_museum_insects"},
    "Art":      {"total": 28, "getter": "get_museum_art"},
}

PLAYER_NAMES = ["Player 1", "Player 2", "Player 3", "Player 4"]


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class MuseumEditorDialog(QDialog):
    """Dialog for viewing and editing museum donations and encyclopedia."""

    def __init__(
        self,
        save_handler: SaveHandler,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.save_handler = save_handler
        self.setWindowTitle("Museum & Encyclopedia Editor")

        self._dirty = False

        self._build_ui()
        self._refresh_all()

        self.resize(520, 420)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)

        # --- Tab widget for museum categories ---
        self.tab_widget = QTabWidget()
        self.tab_labels: dict[str, dict[str, QLabel]] = {}

        for category, info in MUSEUM_CATEGORIES.items():
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setContentsMargins(16, 16, 16, 16)

            # Summary label (large text)
            summary_label = QLabel()
            summary_font = QFont()
            summary_font.setPointSize(18)
            summary_font.setBold(True)
            summary_label.setFont(summary_font)
            summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(summary_label)

            # Per-player breakdown
            breakdown_group = QGroupBox("Donations by Player")
            breakdown_layout = QVBoxLayout(breakdown_group)

            player_labels = {}
            for i, name in enumerate(PLAYER_NAMES):
                row = QHBoxLayout()
                name_lbl = QLabel(f"{name}:")
                name_lbl.setMinimumWidth(80)
                count_lbl = QLabel("0")
                count_lbl.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                row.addWidget(name_lbl)
                row.addStretch()
                row.addWidget(count_lbl)
                breakdown_layout.addLayout(row)
                player_labels[f"player_{i}"] = count_lbl

            layout.addWidget(breakdown_group)
            layout.addStretch()

            self.tab_labels[category] = {
                "summary": summary_label,
                **player_labels,
            }

            self.tab_widget.addTab(tab, category)

        root.addWidget(self.tab_widget, stretch=1)

        # --- Separator ---
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(sep)

        # --- Quick actions ---
        actions_group = QGroupBox("Quick Actions")
        actions_layout = QVBoxLayout(actions_group)

        # Fill museum row
        fill_row = QHBoxLayout()
        fill_row.addWidget(QLabel("Fill all museum donations as:"))
        self.player_combo = QComboBox()
        for name in PLAYER_NAMES:
            self.player_combo.addItem(name)
        fill_row.addWidget(self.player_combo)
        btn_fill = QPushButton("Fill Museum")
        btn_fill.setToolTip("Donate every item in all museum wings as the selected player")
        btn_fill.clicked.connect(self._on_fill_museum)
        fill_row.addWidget(btn_fill)
        actions_layout.addLayout(fill_row)

        # Clear + Encyclopedia row
        misc_row = QHBoxLayout()
        btn_clear = QPushButton("Clear All Donations")
        btn_clear.setToolTip("Remove all museum donations")
        btn_clear.clicked.connect(self._on_clear_museum)
        misc_row.addWidget(btn_clear)

        btn_encyclopedia = QPushButton("Fill Encyclopedia")
        btn_encyclopedia.setToolTip(
            "Mark all fish and insects as caught for the selected player"
        )
        btn_encyclopedia.clicked.connect(self._on_fill_encyclopedia)
        misc_row.addWidget(btn_encyclopedia)

        misc_row.addStretch()
        actions_layout.addLayout(misc_row)

        root.addWidget(actions_group)

        # --- Bottom buttons ---
        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_apply = QPushButton("Apply")
        btn_apply.setMinimumWidth(90)
        btn_apply.clicked.connect(self._on_apply)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setMinimumWidth(90)
        btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(btn_apply)
        bottom.addWidget(btn_cancel)
        root.addLayout(bottom)

        # Status bar
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("padding: 4px; color: #666;")
        root.addWidget(self.status_label)

    # ------------------------------------------------------------------
    # Data refresh
    # ------------------------------------------------------------------

    def _refresh_all(self):
        """Re-read museum data from the save handler and update all tabs."""
        for category, info in MUSEUM_CATEGORIES.items():
            getter = getattr(self.save_handler, info["getter"])
            values = getter()
            total = info["total"]

            donated = sum(1 for v in values if v != 0)
            labels = self.tab_labels[category]
            labels["summary"].setText(f"{donated} / {total} donated")

            # Per-player counts
            for pid in range(4):
                count = sum(1 for v in values if v == pid + 1)
                labels[f"player_{pid}"].setText(str(count))

        # Encyclopedia summary in status
        enc_parts = []
        for pid in range(4):
            try:
                insects = self.save_handler.get_encyclopedia_insects(pid)
                fish = self.save_handler.get_encyclopedia_fish(pid)
                caught_insects = sum(insects)
                caught_fish = sum(fish)
                if caught_insects > 0 or caught_fish > 0:
                    enc_parts.append(
                        f"P{pid + 1}: {caught_fish} fish, {caught_insects} bugs"
                    )
            except Exception:
                pass

        if enc_parts:
            self.status_label.setText("Encyclopedia: " + "  |  ".join(enc_parts))
        else:
            self.status_label.setText("")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_fill_museum(self):
        player = self.player_combo.currentIndex()
        reply = QMessageBox.question(
            self,
            "Fill Museum",
            f"Fill all museum donations as {PLAYER_NAMES[player]}?\n\n"
            "This will overwrite existing donations.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.save_handler.fill_museum(player)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to fill museum:\n{e}")
            return

        self._dirty = True
        self._refresh_all()
        self.status_label.setText(
            f"All museum donations filled as {PLAYER_NAMES[player]}."
        )

    def _on_clear_museum(self):
        reply = QMessageBox.question(
            self,
            "Clear Museum",
            "Remove all museum donations?\n\n"
            "This cannot be undone (until you close without applying).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.save_handler.clear_museum()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to clear museum:\n{e}")
            return

        self._dirty = True
        self._refresh_all()
        self.status_label.setText("All museum donations cleared.")

    def _on_fill_encyclopedia(self):
        player = self.player_combo.currentIndex()
        reply = QMessageBox.question(
            self,
            "Fill Encyclopedia",
            f"Mark all fish and insects as caught for {PLAYER_NAMES[player]}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.save_handler.fill_encyclopedia(player)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to fill encyclopedia:\n{e}")
            return

        self._dirty = True
        self._refresh_all()
        self.status_label.setText(
            f"Encyclopedia filled for {PLAYER_NAMES[player]}."
        )

    def _on_apply(self):
        # The fill/clear actions write directly to the save handler's buffer,
        # so there is nothing extra to commit here -- just accept the dialog.
        self.accept()

"""
Mail / Letter Viewer Dialog for Animal Crossing: City Folk Save Editor.

Read-only viewer for the 10 letter slots per player.  Shows sender,
attached item, header, and full body text.  The mail binary format is
not fully documented for writes, so this dialog intentionally offers
no editing capability.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QPushButton, QLabel,
    QTextEdit, QGroupBox, QFormLayout, QComboBox, QWidget,
)
from PyQt6.QtCore import Qt

from save_handler import SaveHandler

LETTER_SLOTS = 10
NO_ITEM = 0xFFF1


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class LetterViewerDialog(QDialog):
    """Read-only viewer for player mail / letters."""

    def __init__(
        self,
        save_handler: SaveHandler,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.save_handler = save_handler
        self.setWindowTitle("Mail Viewer")

        self._build_ui()
        self._populate_players()

        self.resize(700, 520)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)

        # Player selector
        player_row = QHBoxLayout()
        player_row.addWidget(QLabel("Player:"))
        self.player_combo = QComboBox()
        self.player_combo.currentIndexChanged.connect(self._on_player_changed)
        player_row.addWidget(self.player_combo, stretch=1)
        player_row.addStretch()
        root.addLayout(player_row)

        # Splitter: letter list | detail panel
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Left: letter slot list ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("Letters:"))

        self.letter_list = QListWidget()
        self.letter_list.currentRowChanged.connect(self._on_letter_selected)
        left_layout.addWidget(self.letter_list, stretch=1)

        splitter.addWidget(left_widget)

        # --- Right: detail panel ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        detail_group = QGroupBox("Letter Details")
        detail_form = QFormLayout(detail_group)

        self.lbl_sender = QLabel("-")
        self.lbl_item = QLabel("-")
        self.lbl_header = QLabel("-")
        self.lbl_header.setWordWrap(True)

        detail_form.addRow("Sender:", self.lbl_sender)
        detail_form.addRow("Attached Item:", self.lbl_item)
        detail_form.addRow("Header:", self.lbl_header)

        right_layout.addWidget(detail_group)

        body_label = QLabel("Body:")
        right_layout.addWidget(body_label)

        self.body_edit = QTextEdit()
        self.body_edit.setReadOnly(True)
        right_layout.addWidget(self.body_edit, stretch=1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter, stretch=1)

        # --- Bottom: close button ---
        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setMinimumWidth(90)
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

    # ------------------------------------------------------------------
    # Population helpers
    # ------------------------------------------------------------------

    def _populate_players(self):
        """Fill the player combo box with existing players only."""
        self.player_combo.blockSignals(True)
        self.player_combo.clear()
        for p in range(4):
            if self.save_handler.player_exists(p):
                self.player_combo.addItem(f"Player {p}", p)
        self.player_combo.blockSignals(False)

        if self.player_combo.count() > 0:
            self.player_combo.setCurrentIndex(0)
            self._on_player_changed(0)
        else:
            self._clear_detail()

    def _populate_letters(self, player: int):
        """Fill the letter list for the given player index."""
        self.letter_list.blockSignals(True)
        self.letter_list.clear()

        for slot in range(LETTER_SLOTS):
            try:
                if self.save_handler.is_letter_empty(player, slot):
                    label = f"Slot {slot}: (empty)"
                else:
                    sender = self.save_handler.get_letter_sender(player, slot)
                    label = f"Slot {slot}: from {sender}" if sender else f"Slot {slot}: (no sender)"
            except Exception:
                label = f"Slot {slot}: (read error)"

            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, slot)
            self.letter_list.addItem(item)

        self.letter_list.blockSignals(False)
        self._clear_detail()

    # ------------------------------------------------------------------
    # Detail display
    # ------------------------------------------------------------------

    def _show_letter(self, player: int, slot: int):
        """Display full details for a single letter."""
        try:
            if self.save_handler.is_letter_empty(player, slot):
                self._clear_detail()
                return

            sender = self.save_handler.get_letter_sender(player, slot)
            header = self.save_handler.get_letter_header(player, slot)
            body = self.save_handler.get_letter_body(player, slot)
            item_id = self.save_handler.get_letter_item(player, slot)
        except Exception:
            self._clear_detail()
            self.body_edit.setPlainText("(Error reading letter data)")
            return

        self.lbl_sender.setText(sender if sender else "-")
        self.lbl_header.setText(header if header else "-")

        if item_id == NO_ITEM or item_id == 0:
            self.lbl_item.setText("None")
        else:
            self.lbl_item.setText(f"0x{item_id:04X}")

        self.body_edit.setPlainText(body if body else "")

    def _clear_detail(self):
        """Reset the detail panel to its default empty state."""
        self.lbl_sender.setText("-")
        self.lbl_item.setText("-")
        self.lbl_header.setText("-")
        self.body_edit.clear()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _current_player(self) -> int:
        """Return the player index from the combo box, or -1."""
        idx = self.player_combo.currentIndex()
        if idx < 0:
            return -1
        return self.player_combo.itemData(idx)

    def _on_player_changed(self, _index: int):
        player = self._current_player()
        if player < 0:
            self.letter_list.clear()
            self._clear_detail()
            return
        self._populate_letters(player)

    def _on_letter_selected(self, row: int):
        if row < 0:
            self._clear_detail()
            return
        player = self._current_player()
        if player < 0:
            return
        item = self.letter_list.item(row)
        if item is None:
            return
        slot = item.data(Qt.ItemDataRole.UserRole)
        self._show_letter(player, slot)

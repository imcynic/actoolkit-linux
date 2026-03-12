"""
Pattern Viewer/Editor Dialog for Animal Crossing: City Folk Save Editor.

Shows the 8 design pattern slots per player as thumbnail previews rendered
from the C4-decoded pixel data and RGB565 palette stored in the save file.
Clicking a thumbnail opens a detail panel with a larger preview, editable
title, read-only creator name, and the 16-color palette.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QGroupBox,
    QWidget, QFormLayout, QComboBox, QFrame,
    QMessageBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QImage, QPixmap, QColor, QIcon

from save_handler import SaveHandler

PATTERN_SLOTS = 8
PATTERN_SIZE = 32
THUMB_SIZE = 64
PREVIEW_SIZE = 192
PALETTE_SWATCH = 20
TITLE_MAX_LEN = 16


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _render_pattern_image(
    pixels: list[list[int]],
    palette: list[tuple[int, int, int]],
) -> QImage:
    """Build a 32x32 QImage from pixel indices and an RGB palette."""
    img = QImage(PATTERN_SIZE, PATTERN_SIZE, QImage.Format.Format_RGB32)
    for y in range(PATTERN_SIZE):
        for x in range(PATTERN_SIZE):
            idx = pixels[y][x] & 0xF
            r, g, b = palette[idx]
            img.setPixelColor(x, y, QColor(r, g, b))
    return img


def _scaled_pixmap(img: QImage, size: int) -> QPixmap:
    """Scale a QImage to *size* x *size* with nearest-neighbor interpolation."""
    return QPixmap.fromImage(
        img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                   Qt.TransformationMode.FastTransformation)
    )


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class PatternEditorDialog(QDialog):
    """Dialog for viewing and editing player design patterns."""

    def __init__(
        self,
        save_handler: SaveHandler,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.save_handler = save_handler
        self.setWindowTitle("Pattern Editor")

        # Pending edits: {(player, slot): new_title}
        self._pending_titles: dict[tuple[int, int], str] = {}

        # Currently selected player / slot
        self._current_player: int = -1
        self._current_slot: int = -1

        self._build_ui()
        self._populate_player_combo()

        self.resize(640, 560)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)

        # --- Player selector ---
        player_row = QHBoxLayout()
        player_row.addWidget(QLabel("Player:"))
        self.player_combo = QComboBox()
        self.player_combo.currentIndexChanged.connect(self._on_player_changed)
        player_row.addWidget(self.player_combo, stretch=1)
        player_row.addStretch(2)
        root.addLayout(player_row)

        # --- Main content: thumbnails on left, detail on right ---
        content = QHBoxLayout()

        # Thumbnail grid (2 columns x 4 rows = 8 slots)
        thumb_group = QGroupBox("Patterns")
        thumb_layout = QGridLayout(thumb_group)
        thumb_layout.setSpacing(6)
        self.thumb_buttons: list[QPushButton] = []
        for i in range(PATTERN_SLOTS):
            btn = QPushButton()
            btn.setFixedSize(QSize(THUMB_SIZE + 8, THUMB_SIZE + 8))
            btn.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
            btn.setToolTip(f"Pattern slot {i}")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, slot=i: self._on_thumb_clicked(slot))
            row = i // 2
            col = i % 2
            thumb_layout.addWidget(btn, row, col)
            self.thumb_buttons.append(btn)

        content.addWidget(thumb_group)

        # Detail panel
        detail_group = QGroupBox("Details")
        detail_layout = QVBoxLayout(detail_group)

        # Large preview
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet(
            "background: #222; border: 1px solid #555;"
        )
        detail_layout.addWidget(self.preview_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Metadata form
        form = QFormLayout()

        self.title_edit = QLineEdit()
        self.title_edit.setMaxLength(TITLE_MAX_LEN)
        self.title_edit.setPlaceholderText("(no title)")
        self.title_edit.textEdited.connect(self._on_title_edited)
        form.addRow("Title:", self.title_edit)

        self.creator_label = QLabel("-")
        form.addRow("Creator:", self.creator_label)

        detail_layout.addLayout(form)

        # Palette display
        palette_label = QLabel("Palette:")
        detail_layout.addWidget(palette_label)

        self.palette_frame = QFrame()
        self.palette_frame.setFixedHeight(PALETTE_SWATCH * 2 + 6)
        self.palette_layout = QGridLayout(self.palette_frame)
        self.palette_layout.setContentsMargins(2, 2, 2, 2)
        self.palette_layout.setSpacing(2)

        self.palette_swatches: list[QLabel] = []
        for i in range(16):
            swatch = QLabel()
            swatch.setFixedSize(PALETTE_SWATCH, PALETTE_SWATCH)
            swatch.setAutoFillBackground(True)
            swatch.setStyleSheet("border: 1px solid #888;")
            swatch.setToolTip(f"Color {i}")
            row = i // 8
            col = i % 8
            self.palette_layout.addWidget(swatch, row, col)
            self.palette_swatches.append(swatch)

        detail_layout.addWidget(self.palette_frame)
        detail_layout.addStretch()

        detail_group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        content.addWidget(detail_group, stretch=1)

        root.addLayout(content, stretch=1)

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
    # Player combo
    # ------------------------------------------------------------------

    def _populate_player_combo(self):
        self.player_combo.blockSignals(True)
        self.player_combo.clear()
        for p in range(4):
            if self.save_handler.player_exists(p):
                name = self.save_handler.get_player_name(p)
                label = f"Player {p + 1}: {name}" if name else f"Player {p + 1}"
                self.player_combo.addItem(label, userData=p)
        self.player_combo.blockSignals(False)

        if self.player_combo.count() > 0:
            self.player_combo.setCurrentIndex(0)
            self._on_player_changed(0)

    def _on_player_changed(self, combo_index: int):
        if combo_index < 0:
            return
        player = self.player_combo.itemData(combo_index)
        if player is None:
            return
        self._current_player = player
        self._current_slot = -1
        self._refresh_thumbnails()
        self._clear_detail()

    # ------------------------------------------------------------------
    # Thumbnail grid
    # ------------------------------------------------------------------

    def _refresh_thumbnails(self):
        p = self._current_player
        if p < 0:
            return

        for slot in range(PATTERN_SLOTS):
            btn = self.thumb_buttons[slot]
            try:
                pixels = self.save_handler.get_pattern_pixels(p, slot)
                palette = self.save_handler.get_pattern_palette_rgb(p, slot)
                img = _render_pattern_image(pixels, palette)
                pix = _scaled_pixmap(img, THUMB_SIZE)
                btn.setIcon(QIcon(pix))
                title = self._get_effective_title(p, slot)
                btn.setToolTip(f"Slot {slot}: {title}" if title else f"Slot {slot}")
            except Exception:
                btn.setIcon(QIcon())
                btn.setToolTip(f"Slot {slot}: (error)")

            btn.setChecked(slot == self._current_slot)

    def _on_thumb_clicked(self, slot: int):
        # Uncheck all others
        for i, btn in enumerate(self.thumb_buttons):
            btn.setChecked(i == slot)

        self._current_slot = slot
        self._show_detail(self._current_player, slot)

    # ------------------------------------------------------------------
    # Detail panel
    # ------------------------------------------------------------------

    def _show_detail(self, p: int, slot: int):
        if p < 0 or slot < 0:
            self._clear_detail()
            return

        try:
            pixels = self.save_handler.get_pattern_pixels(p, slot)
            palette = self.save_handler.get_pattern_palette_rgb(p, slot)
        except Exception as e:
            self.status_label.setText(f"Error reading pattern: {e}")
            self._clear_detail()
            return

        # Large preview
        img = _render_pattern_image(pixels, palette)
        pix = _scaled_pixmap(img, PREVIEW_SIZE)
        self.preview_label.setPixmap(pix)

        # Title (use pending edit if present, otherwise from save)
        title = self._get_effective_title(p, slot)
        self.title_edit.blockSignals(True)
        self.title_edit.setText(title)
        self.title_edit.blockSignals(False)
        self.title_edit.setEnabled(True)

        # Creator
        creator = self.save_handler.get_pattern_creator(p, slot)
        self.creator_label.setText(creator if creator else "-")

        # Palette swatches
        for i, (r, g, b) in enumerate(palette):
            swatch = self.palette_swatches[i]
            swatch.setStyleSheet(
                f"background-color: rgb({r},{g},{b}); border: 1px solid #888;"
            )
            swatch.setToolTip(f"Color {i}: ({r}, {g}, {b})")

        self.status_label.setText(f"Player {p + 1}, Slot {slot}")

    def _clear_detail(self):
        self.preview_label.clear()
        self.title_edit.blockSignals(True)
        self.title_edit.clear()
        self.title_edit.blockSignals(False)
        self.title_edit.setEnabled(False)
        self.creator_label.setText("-")
        for swatch in self.palette_swatches:
            swatch.setStyleSheet("background-color: #333; border: 1px solid #888;")
            swatch.setToolTip("")

    # ------------------------------------------------------------------
    # Title editing
    # ------------------------------------------------------------------

    def _on_title_edited(self, text: str):
        p = self._current_player
        slot = self._current_slot
        if p < 0 or slot < 0:
            return
        self._pending_titles[(p, slot)] = text
        # Update the tooltip on the thumbnail
        btn = self.thumb_buttons[slot]
        btn.setToolTip(f"Slot {slot}: {text}" if text else f"Slot {slot}")

    def _get_effective_title(self, p: int, slot: int) -> str:
        """Return the pending title if edited, otherwise the saved one."""
        key = (p, slot)
        if key in self._pending_titles:
            return self._pending_titles[key]
        return self.save_handler.get_pattern_title(p, slot)

    # ------------------------------------------------------------------
    # Apply / Cancel
    # ------------------------------------------------------------------

    def _on_apply(self):
        try:
            for (p, slot), title in self._pending_titles.items():
                self.save_handler.set_pattern_title(p, slot, title)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to write pattern data:\n{e}")
            return
        self.accept()

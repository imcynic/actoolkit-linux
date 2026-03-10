"""Emotions Editor dialog for Animal Crossing: City Folk save editor."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QPushButton, QGroupBox,
)
from PyQt6.QtCore import Qt


EMOTION_NAMES = [
    "(none)",
    "Happiness",
    "Laughter",
    "Glee",
    "Sadness",
    "Surprise",
    "Outrage",
    "Disbelief",
    "Sleepiness",
    "Thought",
    "Inspiration",
    "Agreement",
    "Distress",
    "Bewilderment",
    "Coldness",
    "Shock",
    "Passion",
    "Delight",
    "Bashfulness",
    "Resignation",
    "Mischief",
    "Joy",
    "Scheming",
    "Anger",
    "Worry",
    "Sighing",
    "Amazement",
    "Giddiness",
    "Flourish",
    "Shrunk Funk Shuffle",
    "Mistaken",
]


class EmotionsEditorDialog(QDialog):
    """Dialog for editing the 4 equipped emotion slots."""

    def __init__(self, save_handler, player, parent=None):
        super().__init__(parent)
        self.save_handler = save_handler
        self.player = player

        self.setWindowTitle(f"Emotions Editor - Player {player + 1}")
        self.setMinimumWidth(340)
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        group = QGroupBox("Emotion Slots")
        form = QFormLayout()

        self.slot_combos = []
        for slot in range(4):
            combo = QComboBox()
            for idx, name in enumerate(EMOTION_NAMES):
                combo.addItem(f"{idx}: {name}" if idx > 0 else name, idx)
            form.addRow(f"Slot {slot + 1}:", combo)
            self.slot_combos.append(combo)

        group.setLayout(form)
        layout.addWidget(group)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(apply_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _load_values(self):
        """Load current emotion slots from save_handler."""
        emotions = self.save_handler.get_emotions(self.player)
        for i, combo in enumerate(self.slot_combos):
            val = emotions[i] if i < len(emotions) else 0
            # Clamp to valid range
            val = max(0, min(val, len(EMOTION_NAMES) - 1))
            combo.setCurrentIndex(val)

    def _apply(self):
        """Write selected emotions back to save_handler and accept."""
        values = [combo.currentData() for combo in self.slot_combos]
        try:
            self.save_handler.set_emotions(self.player, values)
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to write emotions:\n{e}")
            return
        self.accept()

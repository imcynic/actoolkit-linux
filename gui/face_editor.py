"""Face/Appearance Editor dialog for Animal Crossing: City Folk save editor."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QLabel, QPushButton, QGroupBox,
)
from PyQt6.QtCore import Qt


class FaceEditorDialog(QDialog):
    """Dialog for editing player face, hair, skin, and hat appearance."""

    def __init__(self, save_handler, player, parent=None):
        super().__init__(parent)
        self.save_handler = save_handler
        self.player = player

        self.setWindowTitle(f"Appearance Editor - Player {player + 1}")
        self.setMinimumWidth(360)
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        group = QGroupBox("Player Appearance")
        form = QFormLayout()

        # Face Style: 0-15
        self.face_combo = QComboBox()
        for i in range(16):
            self.face_combo.addItem(f"Style {i}", i)
        self.face_label = QLabel()
        row_face = QHBoxLayout()
        row_face.addWidget(self.face_combo, 1)
        row_face.addWidget(self.face_label)
        form.addRow("Face Style:", row_face)
        self.face_combo.currentIndexChanged.connect(self._update_face_label)

        # Hair Style: 0-25
        self.hair_combo = QComboBox()
        for i in range(26):
            self.hair_combo.addItem(f"Style {i}", i)
        self.hair_label = QLabel()
        row_hair = QHBoxLayout()
        row_hair.addWidget(self.hair_combo, 1)
        row_hair.addWidget(self.hair_label)
        form.addRow("Hair Style:", row_hair)
        self.hair_combo.currentIndexChanged.connect(self._update_hair_label)

        # Hair Color: 0-7
        self.hair_color_combo = QComboBox()
        hair_color_names = [
            "Dark Brown", "Light Brown", "Orange", "Light Blue",
            "Gold", "Light Green", "Pink", "Black",
        ]
        for i in range(8):
            self.hair_color_combo.addItem(f"{i} - {hair_color_names[i]}", i)
        self.hair_color_label = QLabel()
        row_hc = QHBoxLayout()
        row_hc.addWidget(self.hair_color_combo, 1)
        row_hc.addWidget(self.hair_color_label)
        form.addRow("Hair Color:", row_hc)
        self.hair_color_combo.currentIndexChanged.connect(self._update_hair_color_label)

        # Tan/Skin: 0-7
        self.tan_combo = QComboBox()
        for i in range(8):
            self.tan_combo.addItem(f"Tone {i}", i)
        self.tan_label = QLabel()
        row_tan = QHBoxLayout()
        row_tan.addWidget(self.tan_combo, 1)
        row_tan.addWidget(self.tan_label)
        form.addRow("Tan/Skin:", row_tan)
        self.tan_combo.currentIndexChanged.connect(self._update_tan_label)

        # Hat: 0-7
        self.hat_combo = QComboBox()
        for i in range(8):
            self.hat_combo.addItem(f"Hat {i}", i)
        self.hat_label = QLabel()
        row_hat = QHBoxLayout()
        row_hat.addWidget(self.hat_combo, 1)
        row_hat.addWidget(self.hat_label)
        form.addRow("Hat:", row_hat)
        self.hat_combo.currentIndexChanged.connect(self._update_hat_label)

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
        """Load current values from save_handler into combo boxes."""
        self.face_combo.setCurrentIndex(self.save_handler.get_face(self.player))
        self.hair_combo.setCurrentIndex(self.save_handler.get_hair(self.player))
        self.hair_color_combo.setCurrentIndex(self.save_handler.get_hair_color(self.player))
        self.tan_combo.setCurrentIndex(self.save_handler.get_tan(self.player))
        self.hat_combo.setCurrentIndex(self.save_handler.get_hat(self.player))

        self._update_face_label()
        self._update_hair_label()
        self._update_hair_color_label()
        self._update_tan_label()
        self._update_hat_label()

    def _update_face_label(self):
        val = self.face_combo.currentData()
        self.face_label.setText(f"[{val}]")

    def _update_hair_label(self):
        val = self.hair_combo.currentData()
        self.hair_label.setText(f"[{val}]")

    def _update_hair_color_label(self):
        val = self.hair_color_combo.currentData()
        self.hair_color_label.setText(f"[{val}]")

    def _update_tan_label(self):
        val = self.tan_combo.currentData()
        self.tan_label.setText(f"[{val}]")

    def _update_hat_label(self):
        val = self.hat_combo.currentData()
        self.hat_label.setText(f"[{val}]")

    def _apply(self):
        """Write selected values back to save_handler and accept."""
        try:
            self.save_handler.set_face(self.player, self.face_combo.currentData())
            self.save_handler.set_hair(self.player, self.hair_combo.currentData())
            self.save_handler.set_hair_color(self.player, self.hair_color_combo.currentData())
            self.save_handler.set_tan(self.player, self.tan_combo.currentData())
            self.save_handler.set_hat(self.player, self.hat_combo.currentData())
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to write appearance:\n{e}")
            return
        self.accept()

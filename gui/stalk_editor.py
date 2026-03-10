"""
Stalk Market Editor Dialog for Animal Crossing: City Folk Save Editor.

Displays and edits turnip prices for the week: Joan's Sunday buy price,
the 14 half-day sell prices (Sun AM through Sat PM), and the trend pattern.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QGroupBox, QFormLayout, QLabel,
    QSpinBox, QComboBox, QPushButton,
    QTableWidget, QHeaderView, QWidget,
    QAbstractItemView, QMessageBox,
)
from PyQt6.QtCore import Qt

from save_handler import SaveHandler

DAYS = [
    "Sunday", "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday",
]

PATTERN_NAMES = {
    0: "Decreasing",
    1: "Random",
    2: "Small Spike",
    3: "Large Spike",
}


class StalkEditorDialog(QDialog):
    """Dialog for viewing and editing the stalk market (turnip prices)."""

    def __init__(
        self,
        save_handler: SaveHandler,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.save_handler = save_handler
        self.setWindowTitle("Stalk Market Editor")

        self._build_ui()
        self._load_data()

        self.resize(420, 520)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)

        # --- Buy price ---
        buy_group = QGroupBox("Joan's Buy Price (Sunday)")
        buy_layout = QFormLayout(buy_group)
        self.buy_spin = QSpinBox()
        self.buy_spin.setRange(0, 999)
        self.buy_spin.setSuffix(" Bells")
        buy_layout.addRow("Buy Price:", self.buy_spin)
        root.addWidget(buy_group)

        # --- Weekly sell prices table ---
        sell_group = QGroupBox("Nook's Sell Prices")
        sell_layout = QVBoxLayout(sell_group)

        self.price_table = QTableWidget(7, 2)
        self.price_table.setHorizontalHeaderLabels(["AM", "PM"])
        self.price_table.setVerticalHeaderLabels(DAYS)
        self.price_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.price_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        self.price_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )

        # Create a QSpinBox for every cell
        self.price_spins: list[list[QSpinBox]] = []
        for row in range(7):
            row_spins: list[QSpinBox] = []
            for col in range(2):
                spin = QSpinBox()
                spin.setRange(0, 999)
                spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.price_table.setCellWidget(row, col, spin)
                row_spins.append(spin)
            self.price_spins.append(row_spins)

        sell_layout.addWidget(self.price_table)
        root.addWidget(sell_group, stretch=1)

        # --- Pattern selector ---
        pattern_group = QGroupBox("Trend Pattern")
        pattern_layout = QFormLayout(pattern_group)
        self.pattern_combo = QComboBox()
        for pid in sorted(PATTERN_NAMES.keys()):
            self.pattern_combo.addItem(PATTERN_NAMES[pid], pid)
        pattern_layout.addRow("Pattern:", self.pattern_combo)
        root.addWidget(pattern_group)

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

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_data(self):
        # Buy price
        self.buy_spin.setValue(self.save_handler.get_turnip_buy_price())

        # Sell prices: 14 values ordered Sun AM, Sun PM, Mon AM, Mon PM, ...
        prices = self.save_handler.get_turnip_sell_prices()
        for i, price in enumerate(prices):
            row = i // 2
            col = i % 2
            self.price_spins[row][col].setValue(price)

        # Pattern
        pattern = self.save_handler.get_turnip_pattern()
        idx = self.pattern_combo.findData(pattern)
        if idx >= 0:
            self.pattern_combo.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_apply(self):
        try:
            # Write buy price
            self.save_handler.set_turnip_buy_price(self.buy_spin.value())

            # Collect sell prices from table
            prices: list[int] = []
            for row in range(7):
                for col in range(2):
                    prices.append(self.price_spins[row][col].value())
            self.save_handler.set_turnip_sell_prices(prices)

            # Write pattern
            pattern = self.pattern_combo.currentData()
            self.save_handler.set_turnip_pattern(pattern)
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to write stalk market data:\n{e}"
            )
            return
        self.accept()

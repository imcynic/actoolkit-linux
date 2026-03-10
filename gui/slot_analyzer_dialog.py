"""Slot Analyzer dialog — visual breakdown of used vs free save slots."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QProgressBar, QWidget,
    QHeaderView, QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from save_handler import SaveHandler
from slot_analyzer import analyze_save, SlotInfo, AnalysisResult


# -- Colour thresholds for the usage bars ----------------------------------

_CLR_LOW = QColor("#489090")     # teal  (< 50%)
_CLR_MID = QColor("#D8A848")     # gold  (50-79%)
_CLR_HIGH = QColor("#D87848")    # orange (80-99%)
_CLR_FULL = QColor("#C04040")    # red   (100%)


def _bar_color(pct: float) -> str:
    if pct >= 100:
        return _CLR_FULL.name()
    if pct >= 80:
        return _CLR_HIGH.name()
    if pct >= 50:
        return _CLR_MID.name()
    return _CLR_LOW.name()


def _bar_stylesheet(pct: float) -> str:
    color = _bar_color(pct)
    return (
        f"QProgressBar {{ background-color: #2A3C3C; border: 1px solid #3D5858; "
        f"border-radius: 3px; text-align: center; color: #E0E8E8; height: 16px; }}"
        f"QProgressBar::chunk {{ background-color: {color}; border-radius: 2px; }}"
    )


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class SlotAnalyzerDialog(QDialog):
    """Shows a tree-view breakdown of save file slot usage."""

    def __init__(
        self,
        save_handler: SaveHandler,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Save Slot Analyzer")
        self.save_handler = save_handler
        self._build_ui()
        self._run_analysis()
        self.resize(700, 560)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Header
        self.header = QLabel("Analyzing...")
        self.header.setStyleSheet("font-size: 15px; font-weight: bold; color: #6BB0B0;")
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.header)

        # Summary bar
        summary_row = QHBoxLayout()
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("color: #8AACAC;")
        summary_row.addWidget(self.summary_label)
        summary_row.addStretch()
        root.addLayout(summary_row)

        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Category", "Used", "Free", "Total", "Usage"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setColumnCount(5)

        header = self.tree.header()
        if header:
            header.setStretchLastSection(True)
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            for col in (1, 2, 3):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(4, 160)

        root.addWidget(self.tree, stretch=1)

        # Bottom
        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setMinimumWidth(90)
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _run_analysis(self) -> None:
        try:
            result = analyze_save(self.save_handler)
        except Exception as e:
            self.header.setText("Analysis Failed")
            self.summary_label.setText(str(e))
            return

        self.header.setText(f"Slot Analysis: {result.game_label}")

        total_slots = 0
        total_used = 0

        # -- Global section --
        if result.global_categories:
            global_node = QTreeWidgetItem(self.tree, ["Global / Town"])
            global_node.setExpanded(True)
            _set_bold(global_node, 0)

            for cat in result.global_categories:
                self._add_slot_row(global_node, cat)
                total_slots += cat.total
                total_used += cat.used

        # -- Per-player sections --
        for ps in result.players:
            player_node = QTreeWidgetItem(
                self.tree, [f"Player {ps.index}: {ps.name}"]
            )
            player_node.setExpanded(True)
            _set_bold(player_node, 0)

            for cat in ps.categories:
                self._add_slot_row(player_node, cat)
                total_slots += cat.total
                total_used += cat.used

        # Summary
        total_free = total_slots - total_used
        pct = (total_used / total_slots * 100) if total_slots else 0
        self.summary_label.setText(
            f"Total: {total_used:,} / {total_slots:,} slots used "
            f"({total_free:,} free, {pct:.1f}% full)"
        )

    def _add_slot_row(self, parent: QTreeWidgetItem, cat: SlotInfo) -> None:
        item = QTreeWidgetItem(parent)
        item.setText(0, cat.name)
        item.setText(1, f"{cat.used:,}")
        item.setText(2, f"{cat.free:,}")
        item.setText(3, f"{cat.total:,}")
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight)
        item.setTextAlignment(2, Qt.AlignmentFlag.AlignRight)
        item.setTextAlignment(3, Qt.AlignmentFlag.AlignRight)

        # Color the "Free" column green if > 0, red if 0
        if cat.free == 0 and cat.total > 0:
            item.setForeground(2, QBrush(QColor("#C04040")))
        elif cat.free > 0:
            item.setForeground(2, QBrush(QColor("#60C060")))

        # Usage progress bar
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(cat.pct))
        bar.setFormat(f"{cat.pct:.0f}%")
        bar.setFixedHeight(18)
        bar.setStyleSheet(_bar_stylesheet(cat.pct))
        self.tree.setItemWidget(item, 4, bar)


def _set_bold(item: QTreeWidgetItem, col: int) -> None:
    font = item.font(col)
    font.setBold(True)
    item.setFont(col, font)

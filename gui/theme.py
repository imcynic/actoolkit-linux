"""ACToolkit mascot-themed colour palette and stylesheet.

Derived from the mascot's dominant colours:
  Teal    #489090  (head / body)
  Dark    #2D5F5F  (shadow teal)
  Orange  #D87848  (beak / feet)
  Cream   #E8E0D0  (shirt)
  Steel   #3A506B  (shirt pattern)
"""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication

# -- Palette constants (importable by other modules) -----------------------

TEAL        = "#489090"
TEAL_DARK   = "#2D5F5F"
TEAL_LIGHT  = "#6BB0B0"
ORANGE      = "#D87848"
ORANGE_DARK = "#B86030"
CREAM       = "#E8E0D0"
STEEL       = "#3A506B"

BG_DARK     = "#1E2A2A"
BG_MID      = "#253535"
BG_LIGHT    = "#2E4242"
BG_WIDGET   = "#2A3C3C"
TEXT        = "#E0E8E8"
TEXT_DIM    = "#8AACAC"
BORDER      = "#3D5858"

# -- Stylesheet ------------------------------------------------------------

_QSS = f"""
/* ---- Global ---- */
QMainWindow, QDialog {{
    background-color: {BG_DARK};
    color: {TEXT};
}}

QWidget {{
    color: {TEXT};
    font-family: "Segoe UI", "Noto Sans", "Cantarell", sans-serif;
    font-size: 13px;
}}

/* ---- Menu bar ---- */
QMenuBar {{
    background-color: {TEAL_DARK};
    color: {TEXT};
    border-bottom: 2px solid {TEAL};
    padding: 2px;
}}
QMenuBar::item:selected {{
    background-color: {TEAL};
    border-radius: 3px;
}}
QMenu {{
    background-color: {BG_MID};
    color: {TEXT};
    border: 1px solid {BORDER};
}}
QMenu::item:selected {{
    background-color: {TEAL};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 4px 8px;
}}

/* ---- Group boxes ---- */
QGroupBox {{
    background-color: {BG_MID};
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 14px;
    padding: 12px 8px 8px 8px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
    color: {TEAL_LIGHT};
}}

/* ---- Buttons ---- */
QPushButton {{
    background-color: {TEAL};
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 5px 14px;
    font-weight: bold;
    min-height: 22px;
}}
QPushButton:hover {{
    background-color: {TEAL_LIGHT};
}}
QPushButton:pressed {{
    background-color: {TEAL_DARK};
}}
QPushButton:disabled {{
    background-color: {BG_LIGHT};
    color: {TEXT_DIM};
}}

/* ---- Accent / danger buttons ---- */
QPushButton[accessibleName="accent"] {{
    background-color: {ORANGE};
}}
QPushButton[accessibleName="accent"]:hover {{
    background-color: {ORANGE_DARK};
}}

/* ---- Input fields ---- */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {BG_WIDGET};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 3px 6px;
    selection-background-color: {TEAL};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {TEAL_LIGHT};
}}

/* ---- Combo box ---- */
QComboBox {{
    background-color: {BG_WIDGET};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 3px 8px;
    min-height: 22px;
}}
QComboBox:hover {{
    border-color: {TEAL};
}}
QComboBox QAbstractItemView {{
    background-color: {BG_MID};
    color: {TEXT};
    selection-background-color: {TEAL};
    border: 1px solid {BORDER};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

/* ---- Lists & Trees ---- */
QListWidget, QTreeWidget, QTableWidget {{
    background-color: {BG_WIDGET};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 3px;
    alternate-background-color: {BG_MID};
}}
QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {{
    background-color: {TEAL};
    color: #FFFFFF;
}}
QListWidget::item:hover, QTreeWidget::item:hover {{
    background-color: {BG_LIGHT};
}}
QHeaderView::section {{
    background-color: {TEAL_DARK};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px;
    font-weight: bold;
}}

/* ---- Text edits ---- */
QTextEdit, QPlainTextEdit {{
    background-color: {BG_WIDGET};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 3px;
    selection-background-color: {TEAL};
}}

/* ---- Tabs ---- */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    background-color: {BG_MID};
}}
QTabBar::tab {{
    background-color: {BG_LIGHT};
    color: {TEXT_DIM};
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 6px 16px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: {TEAL};
    color: #FFFFFF;
}}
QTabBar::tab:hover:!selected {{
    background-color: {BG_WIDGET};
    color: {TEXT};
}}

/* ---- Splitter ---- */
QSplitter::handle {{
    background-color: {BORDER};
    width: 3px;
    height: 3px;
}}
QSplitter::handle:hover {{
    background-color: {TEAL};
}}

/* ---- Scroll bars ---- */
QScrollBar:vertical, QScrollBar:horizontal {{
    background-color: {BG_DARK};
    border: none;
    width: 10px;
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background-color: {BORDER};
    border-radius: 4px;
    min-height: 30px;
    min-width: 30px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background-color: {TEAL};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}

/* ---- Status bar ---- */
QStatusBar {{
    background-color: {TEAL_DARK};
    color: {TEXT};
    border-top: 1px solid {TEAL};
    padding: 2px;
}}
QStatusBar QLabel {{
    color: {TEXT};
}}

/* ---- Labels ---- */
QLabel {{
    color: {TEXT};
}}

/* ---- Tooltips ---- */
QToolTip {{
    background-color: {BG_MID};
    color: {TEXT};
    border: 1px solid {TEAL};
    padding: 4px;
}}

/* ---- Message boxes ---- */
QMessageBox {{
    background-color: {BG_DARK};
}}
QMessageBox QLabel {{
    color: {TEXT};
}}

/* ---- Check / Radio ---- */
QCheckBox, QRadioButton {{
    color: {TEXT};
    spacing: 6px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {BORDER};
    border-radius: 3px;
    background-color: {BG_WIDGET};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {TEAL};
    border-color: {TEAL_LIGHT};
}}
QRadioButton::indicator {{
    border-radius: 9px;
}}

/* ---- Progress bar ---- */
QProgressBar {{
    background-color: {BG_WIDGET};
    border: 1px solid {BORDER};
    border-radius: 4px;
    text-align: center;
    color: {TEXT};
    height: 18px;
}}
QProgressBar::chunk {{
    background-color: {TEAL};
    border-radius: 3px;
}}

/* ---- Frame ---- */
QFrame {{
    color: {TEXT};
}}
"""


def apply_theme(app: QApplication) -> None:
    """Apply the mascot-themed dark stylesheet to *app*."""
    app.setStyleSheet(_QSS)

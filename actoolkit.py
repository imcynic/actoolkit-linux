#!/usr/bin/env python3
"""ACToolkit - Animal Crossing Save Editor (Linux)

Supports ACCF (Wii), GameCube vanilla, and Deluxe mod editions.
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from gui.main_window import MainWindow
from gui.theme import apply_theme

_ASSETS = Path(__file__).resolve().parent / "assets"


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ACToolkit")
    app.setApplicationVersion("2.0.0")

    # Application icon
    icon_path = _ASSETS / "actoolkit.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    apply_theme(app)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

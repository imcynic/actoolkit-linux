#!/usr/bin/env python3
"""ACToolkit - Animal Crossing: City Folk Save Editor (Linux)

Supports vanilla ACCF and ACCF Deluxe Edition v1.1.2
"""

import sys

from PyQt6.QtWidgets import QApplication

from gui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ACToolkit")
    app.setApplicationVersion("2.0.0")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

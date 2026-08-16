"""MdDesk — application entry point.

Stage 1 scope:
- create QApplication
- create MainWindow
- show window
- enter Qt event loop
- return exit code

No business logic here.
"""

import sys

from PySide6.QtWidgets import QApplication

from src.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MdDesk")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

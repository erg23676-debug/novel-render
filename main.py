"""应用入口。

GUI（默认）:  python main.py
终端版:       python main.py --tui   （或直接 python cli.py）
"""
import sys


def main() -> None:
    if "--tui" in sys.argv or "-t" in sys.argv:
        from cli import TerminalReader
        TerminalReader().run()
        return

    from PyQt6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

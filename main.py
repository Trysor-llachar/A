import sys
from PyQt6.QtWidgets import QApplication
from src.main_window import FloatingMenu

if __name__ == '__main__':
    app = QApplication(sys.argv)
    menu = FloatingMenu()
    menu.show()
    sys.exit(app.exec())

import sys
import json
import pytesseract
import pyperclip
import cv2
import numpy as np
from mss import mss
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QHBoxLayout,
                             QWidget, QRubberBand, QVBoxLayout, QTextEdit, QLabel,
                             QSlider, QDialog)
from PyQt6.QtCore import Qt, QPoint, QRect, QSize

NOTES_FILE = "notes_data.json"

class NoteWindow(QWidget):
    def __init__(self, parent_menu, content="", geometry=None, opacities=None):
        super().__init__()
        self.parent_menu = parent_menu
        self.id = id(self) # Unique identifier for the note

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit(content)
        layout.addWidget(self.text_edit)

        controls_layout = QHBoxLayout()
        self.complete_button = QPushButton("Hoàn thành")
        self.delete_button = QPushButton("Xóa")
        self.settings_button = QPushButton("Cài đặt")
        controls_layout.addWidget(self.complete_button)
        controls_layout.addWidget(self.delete_button)
        controls_layout.addWidget(self.settings_button)
        layout.addLayout(controls_layout)

        opacities = opacities or (200, 255)
        self.background_opacity, self.text_opacity = opacities
        self.settings_dialog = self.create_settings_dialog()
        self.settings_button.clicked.connect(self.settings_dialog.exec)

        self.delete_button.clicked.connect(self.delete_note)
        self.complete_button.clicked.connect(self.complete_note)
        self.text_edit.textChanged.connect(self.parent_menu.save_notes)

        self._drag_start_position = None
        self.update_style()

        if geometry:
            self.setGeometry(*geometry)

    def to_dict(self):
        return {
            "content": self.text_edit.toPlainText(),
            "geometry": (self.x(), self.y(), self.width(), self.height()),
            "opacities": (self.background_opacity, self.text_opacity)
        }

    def create_settings_dialog(self):
        # ... (unchanged from previous step)
        dialog = QDialog(self)
        dialog.setWindowTitle("Cài đặt Ghi chú")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Độ trong suốt nền:"))
        bg_slider = QSlider(Qt.Orientation.Horizontal)
        bg_slider.setRange(50, 255)
        bg_slider.setValue(self.background_opacity)
        bg_slider.valueChanged.connect(self.set_background_opacity)
        layout.addWidget(bg_slider)
        layout.addWidget(QLabel("Độ trong suốt chữ:"))
        text_slider = QSlider(Qt.Orientation.Horizontal)
        text_slider.setRange(50, 255)
        text_slider.setValue(self.text_opacity)
        text_slider.valueChanged.connect(self.set_text_opacity)
        layout.addWidget(text_slider)
        return dialog

    def set_background_opacity(self, value):
        self.background_opacity = value
        self.update_style()
        self.parent_menu.save_notes()

    def set_text_opacity(self, value):
        self.text_opacity = value
        self.update_style()
        self.parent_menu.save_notes()

    def update_style(self):
        # ... (unchanged from previous step)
        self.setStyleSheet(f"""
            QWidget {{ background-color: rgba(45, 45, 45, {self.background_opacity}); border: 1px solid #777; border-radius: 10px; }}
            QTextEdit {{ background-color: transparent; border: none; color: rgba(255, 255, 255, {self.text_opacity}); font-size: 14px; }}
            QPushButton {{ background-color: #555; color: white; border: 1px solid #777; padding: 5px; border-radius: 5px; }}
            QPushButton:hover {{ background-color: #777; }}
        """)

    def complete_note(self):
        self.delete_note() # For now, "complete" is the same as deleting

    def delete_note(self):
        self.parent_menu.remove_note(self)
        self.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_position = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_start_position:
            self.move(event.globalPosition().toPoint() - self._drag_start_position)

    def mouseReleaseEvent(self, event):
        if self._drag_start_position:
            self.parent_menu.save_notes()
        self._drag_start_position = None

    def resizeEvent(self, event):
        self.parent_menu.save_notes()
        super().resizeEvent(event)

class ScreenSelector(QWidget):
    # ... (unchanged from previous step)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        screen_geometry = QApplication.primaryScreen().geometry()
        self.setGeometry(screen_geometry)
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.origin = QPoint()
    def mousePressEvent(self, event):
        self.origin = event.pos()
        self.rubber_band.setGeometry(QRect(self.origin, QSize()))
        self.rubber_band.show()
    def mouseMoveEvent(self, event):
        self.rubber_band.setGeometry(QRect(self.origin, event.pos()).normalized())
    def mouseReleaseEvent(self, event):
        self.hide()
        QApplication.instance().processEvents()
        selected_rect = self.rubber_band.geometry()
        self.parent().capture_and_ocr(selected_rect)
        self.close()

class FloatingMenu(QMainWindow):
    def __init__(self):
        super().__init__()
        self.notes = []
        # ... (init code from previous step, modified) ...
        self.setWindowTitle("Floating Menu")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        self.extract_button = QPushButton("Trích xuất văn bản")
        self.create_note_button = QPushButton("Tạo Ghi chú")
        layout.addWidget(self.extract_button)
        layout.addWidget(self.create_note_button)
        self.setStyleSheet("""
            QMainWindow { background-color: rgba(30, 30, 30, 200); border-radius: 10px; }
            QPushButton { background-color: #555; color: white; border: 1px solid #777; padding: 8px; border-radius: 5px; }
            QPushButton:hover { background-color: #777; }
        """)
        self.extract_button.clicked.connect(self.start_selection)
        self.create_note_button.clicked.connect(self.create_note)
        self._drag_start_position = None
        self.selector = None

        self.load_notes()

    def create_note(self, content="", geometry=None, opacities=None):
        note = NoteWindow(self, content, geometry, opacities)
        self.notes.append(note)
        note.show()
        self.save_notes()

    def remove_note(self, note):
        if note in self.notes:
            self.notes.remove(note)
        self.save_notes()

    def save_notes(self):
        data = [note.to_dict() for note in self.notes]
        with open(NOTES_FILE, 'w') as f:
            json.dump(data, f, indent=4)

    def load_notes(self):
        try:
            with open(NOTES_FILE, 'r') as f:
                data = json.load(f)
                for note_data in data:
                    self.create_note(**note_data)
        except FileNotFoundError:
            pass # No notes to load
        except json.JSONDecodeError:
            print("Error reading notes file.")

    def closeEvent(self, event):
        self.save_notes()
        super().closeEvent(event)

    # ... (rest of the code from previous step, unchanged) ...
    def start_selection(self):
        self.hide()
        self.selector = ScreenSelector(self)
        self.selector.show()
    def capture_and_ocr(self, rect):
        try:
            with mss() as sct:
                monitor = {"top": rect.y(), "left": rect.x(), "width": rect.width(), "height": rect.height()}
                sct_img = sct.grab(monitor)
                img = np.array(sct_img)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                text = pytesseract.image_to_string(img)
                pyperclip.copy(text)
                print(f"Extracted Text:\n{text}")
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            self.show()
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_position = event.globalPosition().toPoint() - self.pos()
    def mouseMoveEvent(self, event):
        if self._drag_start_position:
            self.move(event.globalPosition().toPoint() - self.pos())
    def mouseReleaseEvent(self, event):
        self._drag_start_position = None

if __name__ == '__main__':
    app = QApplication(sys.argv)
    menu = FloatingMenu()
    menu.show()
    sys.exit(app.exec())

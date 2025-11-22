from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QHBoxLayout,
                             QPushButton, QLabel, QSlider, QDialog)
from PyQt6.QtCore import Qt, QPoint

class NoteWindow(QWidget):
    def __init__(self, parent_menu, content="", geometry=None, opacities=None):
        super().__init__()
        self.parent_menu = parent_menu
        self.id = id(self)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
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
        self.setStyleSheet(f"""
            QWidget {{
                background-color: rgba(45, 45, 45, {self.background_opacity});
                border: 1px solid #777;
                border-radius: 10px;
            }}
            QTextEdit {{
                background-color: transparent;
                border: none;
                color: rgba(255, 255, 255, {self.text_opacity});
                font-size: 14px;
            }}
            QPushButton {{
                background-color: #555;
                color: white;
                border: 1px solid #777;
                padding: 5px;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: #777;
            }}
        """)

    def complete_note(self):
        self.parent_menu.backup_note(self.text_edit.toPlainText())
        self.delete_note()

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

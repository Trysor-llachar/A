import json
from PyQt6.QtWidgets import (QApplication, QDialog, QListWidget, QVBoxLayout,
                             QLabel, QDialogButtonBox, QWidget, QRubberBand)
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, QTimer, pyqtSignal

class SuggestionDialog(QDialog):
    def __init__(self, suggestions, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gợi ý Hành động")
        self.selected_action = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Tôi đã phân tích văn bản. Bạn có muốn thực hiện một trong các hành động sau?"))
        self.list_widget = QListWidget()
        for suggestion in suggestions:
            self.list_widget.addItem(suggestion)
        self.list_widget.addItem("Chỉ sao chép văn bản")
        self.list_widget.addItem("Tạo Quy trình mới...")
        layout.addWidget(self.list_widget)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def accept(self):
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            self.selected_action = selected_items[0].text()
        super().accept()

class HighlightWindow(QWidget):
    def __init__(self, rect):
        super().__init__()
        self.setGeometry(rect)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("border: 3px solid red;")
        QTimer.singleShot(3000, self.close)

class StatusOverlay(QWidget):
    def __init__(self, identifier, status_text, geometry):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        self.label = QLabel(f"{identifier}\n{status_text}")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        self.setFixedSize(self.label.sizeHint() + QSize(20, 10))
        self.setGeometry(geometry)

        bg_color = "rgba(45, 136, 45, 220)" if "Đã" in status_text else "rgba(204, 120, 50, 220)"
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg_color};
                border: 1px solid #AAAAAA;
                border-radius: 10px;
            }}
            QLabel {{
                color: white;
                font-size: 12px;
                font-weight: bold;
            }}
        """)
        QTimer.singleShot(5000, self.close)

class ScreenSelector(QWidget):
    def __init__(self, parent=None, callback=None):
        super().__init__(parent)
        self.callback = callback if callback else self.parent().capture_and_ocr
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
        self.callback(selected_rect)
        self.close()

class PositionSelector(QWidget):
    position_selected = pyqtSignal(int, int)
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setCursor(Qt.CursorShape.CrossCursor)
        screen_geometry = QApplication.primaryScreen().geometry()
        self.setGeometry(screen_geometry)
        self.setWindowOpacity(0.3)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.position_selected.emit(event.globalPosition().toPoint().x(), event.globalPosition().toPoint().y())
            self.close()

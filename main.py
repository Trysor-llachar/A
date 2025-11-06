import sys
import json
import time
from datetime import datetime
import pytesseract
import pyperclip
import cv2
import numpy as np
import pyautogui
from mss import mss
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QHBoxLayout,
                             QWidget, QRubberBand, QVBoxLayout, QTextEdit, QLabel,
                             QSlider, QDialog, QListWidget, QLineEdit, QFormLayout,
                             QDialogButtonBox, QListWidgetItem, QComboBox)
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, QThread, pyqtSignal

NOTES_FILE = "notes_data.json"
RULES_FILE = "rules.json"
BACKUP_FILE = "backup_notes.json"

class PositionSelector(QWidget):
    """A temporary, full-screen widget to select a screen coordinate."""
    position_selected = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setCursor(Qt.CursorShape.CrossCursor)
        screen_geometry = QApplication.primaryScreen().geometry()
        self.setGeometry(screen_geometry)
        self.setWindowOpacity(0.3) # Make it semi-transparent

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.position_selected.emit(event.globalPosition().toPoint().x(), event.globalPosition().toPoint().y())
            self.close()

class RuleEditorDialog(QDialog):
    def __init__(self, rule=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chỉnh sửa Quy tắc")
        self.form_layout = QFormLayout(self)

        self.condition_text = QLineEdit()
        self.action_type = QComboBox()
        self.action_type.addItems(["Tạo Ghi chú", "Tự động điền"])

        # Widgets for "Create Note" action
        self.note_content_text = QLineEdit()

        # Widgets for "Autofill" action
        self.autofill_widget = QWidget()
        autofill_layout = QHBoxLayout(self.autofill_widget)
        self.autofill_text = QLineEdit()
        self.select_pos_button = QPushButton("Chọn vị trí")
        self.pos_label = QLabel("Chưa chọn")
        autofill_layout.addWidget(self.autofill_text)
        autofill_layout.addWidget(self.select_pos_button)
        autofill_layout.addWidget(self.pos_label)

        self.form_layout.addRow("Nếu thấy văn bản:", self.condition_text)
        self.form_layout.addRow("Thì hành động:", self.action_type)
        self.form_layout.addRow("Nội dung Ghi chú:", self.note_content_text)
        self.form_layout.addRow("Nội dung Tự động điền:", self.autofill_widget)

        self.action_type.currentIndexChanged.connect(self.update_action_widgets)
        self.select_pos_button.clicked.connect(self.select_position)

        self.autofill_pos = None

        if rule:
            self.condition_text.setText(rule.get("condition", ""))
            action_type = rule.get("action_type", "Tạo Ghi chú")
            self.action_type.setCurrentText(action_type)
            if action_type == "Tạo Ghi chú":
                self.note_content_text.setText(rule.get("action_data", ""))
            elif action_type == "Tự động điền":
                self.autofill_text.setText(rule.get("action_data", {}).get("text", ""))
                self.autofill_pos = rule.get("action_data", {}).get("position")
                if self.autofill_pos:
                    self.pos_label.setText(f"({self.autofill_pos[0]}, {self.autofill_pos[1]})")

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.form_layout.addWidget(button_box)
        self.update_action_widgets()

    def update_action_widgets(self):
        current_action = self.action_type.currentText()
        self.note_content_text.setVisible(current_action == "Tạo Ghi chú")
        self.autofill_widget.setVisible(current_action == "Tự động điền")

    def select_position(self):
        self.parent().hide() # Hide rule manager to see the screen
        self.pos_selector = PositionSelector()
        self.pos_selector.position_selected.connect(self.on_position_selected)
        self.pos_selector.show()

    def on_position_selected(self, x, y):
        self.autofill_pos = (x, y)
        self.pos_label.setText(f"({x}, {y})")
        self.parent().show() # Show rule manager again

    def get_rule(self):
        action_type = self.action_type.currentText()
        action_data = None
        if action_type == "Tạo Ghi chú":
            action_data = self.note_content_text.text()
        elif action_type == "Tự động điền":
            action_data = {
                "text": self.autofill_text.text(),
                "position": self.autofill_pos
            }
        return {
            "condition": self.condition_text.text(),
            "action_type": action_type,
            "action_data": action_data
        }

# ... (RuleManagerWindow is mostly unchanged, just how it displays rule text) ...
class RuleManagerWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quản lý Quy tắc")
        self.setMinimumSize(500, 350)
        self.rules = []
        layout = QVBoxLayout(self)
        self.rule_list = QListWidget()
        self.rule_list.itemDoubleClicked.connect(self.edit_rule)
        layout.addWidget(self.rule_list)
        buttons_layout = QHBoxLayout()
        self.add_button = QPushButton("Thêm Mới")
        self.edit_button = QPushButton("Chỉnh Sửa")
        self.delete_button = QPushButton("Xóa")
        buttons_layout.addWidget(self.add_button)
        buttons_layout.addWidget(self.edit_button)
        buttons_layout.addWidget(self.delete_button)
        layout.addLayout(buttons_layout)
        self.add_button.clicked.connect(self.add_rule)
        self.edit_button.clicked.connect(self.edit_rule)
        self.delete_button.clicked.connect(self.delete_rule)
        self.load_rules()
    def load_rules(self):
        try:
            with open(RULES_FILE, 'r') as f: self.rules = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): self.rules = []
        self.refresh_list()
    def save_rules(self):
        with open(RULES_FILE, 'w') as f: json.dump(self.rules, f, indent=4)
        self.parent().on_rules_changed(self.rules)
    def refresh_list(self):
        self.rule_list.clear()
        for rule in self.rules:
            if rule['action_type'] == "Tạo Ghi chú":
                display_text = f"Nếu thấy \"{rule['condition']}\" -> Tạo ghi chú \"{rule['action_data']}\""
            else: # Autofill
                pos = rule['action_data']['position']
                display_text = f"Nếu thấy \"{rule['condition']}\" -> Tự động điền tại {pos}"
            self.rule_list.addItem(QListWidgetItem(display_text))
    def add_rule(self):
        dialog = RuleEditorDialog(parent=self)
        if dialog.exec():
            new_rule = dialog.get_rule()
            if new_rule['condition']:
                self.rules.append(new_rule)
                self.save_rules()
                self.refresh_list()
    def edit_rule(self):
        current_row = self.rule_list.currentRow()
        if current_row < 0: return
        rule_to_edit = self.rules[current_row]
        dialog = RuleEditorDialog(rule=rule_to_edit, parent=self)
        if dialog.exec():
            updated_rule = dialog.get_rule()
            if updated_rule['condition']:
                self.rules[current_row] = updated_rule
                self.save_rules()
                self.refresh_list()
    def delete_rule(self):
        current_row = self.rule_list.currentRow()
        if current_row < 0: return
        del self.rules[current_row]
        self.save_rules()
        self.refresh_list()

# ... (AutomationEngine, NoteWindow, ScreenSelector classes are unchanged) ...
class AutomationEngine(QThread):
    text_found = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True
    def run(self):
        while self.running:
            try:
                with mss() as sct:
                    monitor = sct.monitors[1]
                    sct_img = sct.grab(monitor)
                    img = np.array(sct_img)
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    text = pytesseract.image_to_string(img, timeout=4)
                    if text.strip(): self.text_found.emit(text)
            except Exception as e: print(f"Error in automation engine: {e}")
            time.sleep(5)
    def stop(self):
        self.running = False
        self.wait()
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
        if geometry: self.setGeometry(*geometry)
    def to_dict(self):
        return {"content": self.text_edit.toPlainText(), "geometry": (self.x(), self.y(), self.width(), self.height()), "opacities": (self.background_opacity, self.text_opacity)}
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
        self.setStyleSheet(f"""QWidget {{ background-color: rgba(45, 45, 45, {self.background_opacity}); border: 1px solid #777; border-radius: 10px; }} QTextEdit {{ background-color: transparent; border: none; color: rgba(255, 255, 255, {self.text_opacity}); font-size: 14px; }} QPushButton {{ background-color: #555; color: white; border: 1px solid #777; padding: 5px; border-radius: 5px; }} QPushButton:hover {{ background-color: #777; }}""")
    def complete_note(self):
        self.parent_menu.backup_note(self.text_edit.toPlainText())
        self.delete_note()
    def delete_note(self):
        self.parent_menu.remove_note(self)
        self.close()
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self._drag_start_position = event.globalPosition().toPoint() - self.pos()
    def mouseMoveEvent(self, event):
        if self._drag_start_position: self.move(event.globalPosition().toPoint() - self._drag_start_position)
    def mouseReleaseEvent(self, event):
        if self._drag_start_position: self.parent_menu.save_notes()
        self._drag_start_position = None
    def resizeEvent(self, event):
        self.parent_menu.save_notes()
        super().resizeEvent(event)
class ScreenSelector(QWidget):
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
    # ... (init and other methods mostly unchanged) ...
    def __init__(self):
        super().__init__()
        self.notes = []
        self.rules = []
        self.recently_triggered = {}
        self.setWindowTitle("Floating Menu")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        self.extract_button = QPushButton("Trích xuất văn bản")
        self.create_note_button = QPushButton("Tạo Ghi chú")
        self.rules_button = QPushButton("Quản lý Quy tắc")
        layout.addWidget(self.extract_button)
        layout.addWidget(self.create_note_button)
        layout.addWidget(self.rules_button)
        self.setStyleSheet("""QMainWindow {{ background-color: rgba(30, 30, 30, 200); border-radius: 10px; }} QPushButton {{ background-color: #555; color: white; border: 1px solid #777; padding: 8px; border-radius: 5px; }} QPushButton:hover {{ background-color: #777; }}""")
        self.rule_manager = RuleManagerWindow(self)
        self.extract_button.clicked.connect(self.start_selection)
        self.create_note_button.clicked.connect(self.create_note)
        self.rules_button.clicked.connect(self.rule_manager.exec)
        self._drag_start_position = None
        self.selector = None
        self.load_notes()
        self.on_rules_changed(self.rule_manager.rules)
        self.automation_engine = AutomationEngine(self)
        self.automation_engine.text_found.connect(self.process_screen_text)
        self.automation_engine.start()

    def on_rules_changed(self, new_rules):
        self.rules = new_rules

    def process_screen_text(self, text):
        current_time = time.time()
        for rule in self.rules:
            condition = rule['condition']
            if condition in text:
                last_triggered = self.recently_triggered.get(condition, 0)
                if current_time - last_triggered > 60:
                    print(f"Rule triggered: Found '{condition}'")
                    self.execute_action(rule)
                    self.recently_triggered[condition] = current_time
                    break

    def execute_action(self, rule):
        action_type = rule['action_type']
        action_data = rule['action_data']

        if action_type == "Tạo Ghi chú":
            self.create_note(content=action_data)
        elif action_type == "Tự động điền":
            pos = action_data.get("position")
            text_to_type = action_data.get("text", "")
            if pos:
                pyautogui.click(x=pos[0], y=pos[1])
                pyautogui.write(text_to_type, interval=0.05)

    def backup_note(self, content):
        try:
            with open(BACKUP_FILE, 'r') as f: backup_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): backup_data = {}
        today_str = datetime.now().strftime("%Y-%m-%d")
        now_str = datetime.now().strftime("%H:%M:%S")
        if today_str not in backup_data: backup_data[today_str] = []
        backup_data[today_str].append({"time": now_str, "content": content})
        with open(BACKUP_FILE, 'w') as f: json.dump(backup_data, f, indent=4)

    def create_note(self, content="", geometry=None, opacities=None):
        note = NoteWindow(self, content, geometry, opacities)
        self.notes.append(note)
        note.show()
        self.save_notes()
    def remove_note(self, note):
        if note in self.notes: self.notes.remove(note)
        self.save_notes()
    def save_notes(self):
        data = [note.to_dict() for note in self.notes]
        with open(NOTES_FILE, 'w') as f: json.dump(data, f, indent=4)
    def load_notes(self):
        try:
            with open(NOTES_FILE, 'r') as f:
                data = json.load(f)
                for note_data in data: self.create_note(**note_data)
        except (FileNotFoundError, json.JSONDecodeError): pass
    def closeEvent(self, event):
        self.automation_engine.stop()
        self.save_notes()
        super().closeEvent(event)
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
        except Exception as e: print(f"An error occurred: {e}")
        finally: self.show()
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self._drag_start_position = event.globalPosition().toPoint() - self.pos()
    def mouseMoveEvent(self, event):
        if self._drag_start_position: self.move(event.globalPosition().toPoint() - self.pos())
    def mouseReleaseEvent(self, event):
        self._drag_start_position = None

if __name__ == '__main__':
    app = QApplication(sys.argv)
    menu = FloatingMenu()
    menu.show()
    sys.exit(app.exec())

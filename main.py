import sys
import json
import time
import re
import subprocess
from datetime import datetime, timedelta
from dateutil.parser import parse
import pytesseract
import pandas as pd
from io import StringIO
import pyperclip
import cv2
import numpy as np
import pyautogui
import pygetwindow as gw
from mss import mss
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QHBoxLayout,
                             QWidget, QRubberBand, QVBoxLayout, QTextEdit, QLabel,
                             QSlider, QDialog, QListWidget, QLineEdit, QFormLayout,
                             QDialogButtonBox, QListWidgetItem, QComboBox, QMessageBox,
                             QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, QThread, pyqtSignal, QTimer, QEventLoop

# --- Constants ---
NOTES_FILE = "notes_data.json"; RULES_FILE = "rules.json"; BACKUP_FILE = "backup_notes.json"; PROCESSES_FILE = "processes.json"
KB_FILE = "knowledge.json"; STATE_MEMORY_FILE = "state_memory.json"

# --- State Manager ---
class StateManager:
    def __init__(self):
        self.memory = {}; self.load_memory()
    def load_memory(self):
        try:
            with open(STATE_MEMORY_FILE, 'r') as f: self.memory = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): self.memory = {}
    def save_memory(self):
        with open(STATE_MEMORY_FILE, 'w') as f: json.dump(self.memory, f, indent=4)
    def check_status(self, identifier): return self.memory.get(identifier)
    def update_status(self, identifier):
        timestamp = datetime.now().strftime("%H:%M %d/%b/%Y"); self.memory[identifier] = timestamp; self.save_memory()

# --- UI Components ---
class SuggestionDialog(QDialog):
    def __init__(self, suggestions, parent=None):
        super().__init__(parent); self.setWindowTitle("Gợi ý Hành động"); self.selected_action = None; layout = QVBoxLayout(self); layout.addWidget(QLabel("Tôi đã phân tích văn bản. Bạn có muốn thực hiện một trong các hành động sau?")); self.list_widget = QListWidget()
        for suggestion in suggestions: self.list_widget.addItem(suggestion)
        self.list_widget.addItem("Chỉ sao chép văn bản"); self.list_widget.addItem("Tạo Quy trình mới..."); layout.addWidget(self.list_widget); button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); button_box.accepted.connect(self.accept); button_box.rejected.connect(self.reject); layout.addWidget(button_box)
    def accept(self):
        selected_items = self.list_widget.selectedItems()
        if selected_items: self.selected_action = selected_items[0].text()
        super().accept()
class HighlightWindow(QWidget):
    def __init__(self, rect): super().__init__(); self.setGeometry(rect); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground); self.setStyleSheet("border: 3px solid red;"); QTimer.singleShot(3000, self.close)
class StatusOverlay(QWidget):
    def __init__(self, identifier, status_text, geometry):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        self.label = QLabel(f"{identifier}\n{status_text}")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        # Adjust size to fit content
        self.setFixedSize(self.label.sizeHint() + QSize(20, 10)) # Add some padding
        self.setGeometry(geometry)

        # Set style based on status
        bg_color = "rgba(45, 136, 45, 220)" if "Đã" in status_text else "rgba(204, 120, 50, 220)" # Green for 'On board', Orange for 'Not yet'
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
        super().__init__(parent); self.callback = callback if callback else self.parent().capture_and_ocr; self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground); self.setCursor(Qt.CursorShape.CrossCursor); screen_geometry = QApplication.primaryScreen().geometry(); self.setGeometry(screen_geometry); self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self); self.origin = QPoint()
    def mousePressEvent(self, event): self.origin = event.pos(); self.rubber_band.setGeometry(QRect(self.origin, QSize())); self.rubber_band.show()
    def mouseMoveEvent(self, event): self.rubber_band.setGeometry(QRect(self.origin, event.pos()).normalized())
    def mouseReleaseEvent(self, event): self.hide(); QApplication.instance().processEvents(); selected_rect = self.rubber_band.geometry(); self.callback(selected_rect); self.close()
class PositionSelector(QWidget):
    position_selected = pyqtSignal(int, int)
    def __init__(self): super().__init__(); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint); self.setCursor(Qt.CursorShape.CrossCursor); screen_geometry = QApplication.primaryScreen().geometry(); self.setGeometry(screen_geometry); self.setWindowOpacity(0.3)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.position_selected.emit(event.globalPosition().toPoint().x(), event.globalPosition().toPoint().y()); self.close()
class NoteWindow(QWidget):
    def __init__(self, parent_menu, content="", geometry=None, opacities=None):
        super().__init__(); self.parent_menu = parent_menu; self.id = id(self); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground); layout = QVBoxLayout(self); self.text_edit = QTextEdit(content); layout.addWidget(self.text_edit); controls_layout = QHBoxLayout(); self.complete_button = QPushButton("Hoàn thành"); self.delete_button = QPushButton("Xóa"); self.settings_button = QPushButton("Cài đặt"); controls_layout.addWidget(self.complete_button); controls_layout.addWidget(self.delete_button); controls_layout.addWidget(self.settings_button); layout.addLayout(controls_layout); opacities = opacities or (200, 255); self.background_opacity, self.text_opacity = opacities; self.settings_dialog = self.create_settings_dialog(); self.settings_button.clicked.connect(self.settings_dialog.exec); self.delete_button.clicked.connect(self.delete_note); self.complete_button.clicked.connect(self.complete_note); self.text_edit.textChanged.connect(self.parent_menu.save_notes); self._drag_start_position = None; self.update_style()
        if geometry: self.setGeometry(*geometry)
    def to_dict(self): return {"content": self.text_edit.toPlainText(), "geometry": (self.x(), self.y(), self.width(), self.height()), "opacities": (self.background_opacity, self.text_opacity)}
    def create_settings_dialog(self):
        dialog = QDialog(self); dialog.setWindowTitle("Cài đặt Ghi chú"); layout = QVBoxLayout(dialog); layout.addWidget(QLabel("Độ trong suốt nền:")); bg_slider = QSlider(Qt.Orientation.Horizontal); bg_slider.setRange(50, 255); bg_slider.setValue(self.background_opacity); bg_slider.valueChanged.connect(self.set_background_opacity); layout.addWidget(bg_slider); layout.addWidget(QLabel("Độ trong suốt chữ:")); text_slider = QSlider(Qt.Orientation.Horizontal); text_slider.setRange(50, 255); text_slider.setValue(self.text_opacity); text_slider.valueChanged.connect(self.set_text_opacity); layout.addWidget(text_slider); return dialog
    def set_background_opacity(self, value): self.background_opacity = value; self.update_style(); self.parent_menu.save_notes()
    def set_text_opacity(self, value): self.text_opacity = value; self.update_style(); self.parent_menu.save_notes()
    def update_style(self): self.setStyleSheet(f"""QWidget {{ background-color: rgba(45, 45, 45, {self.background_opacity}); border: 1px solid #777; border-radius: 10px; }} QTextEdit {{ background-color: transparent; border: none; color: rgba(255, 255, 255, {self.text_opacity}); font-size: 14px; }} QPushButton {{ background-color: #555; color: white; border: 1px solid #777; padding: 5px; border-radius: 5px; }} QPushButton:hover {{ background-color: #777; }}""")
    def complete_note(self): self.parent_menu.backup_note(self.text_edit.toPlainText()); self.delete_note()
    def delete_note(self): self.parent_menu.remove_note(self); self.close()
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self._drag_start_position = event.globalPosition().toPoint() - self.pos()
    def mouseMoveEvent(self, event):
        if self._drag_start_position: self.move(event.globalPosition().toPoint() - self._drag_start_position)
    def mouseReleaseEvent(self, event):
        if self._drag_start_position: self.parent_menu.save_notes()
        self._drag_start_position = None
    def resizeEvent(self, event): self.parent_menu.save_notes(); super().resizeEvent(event)
class ActionEditorDialog(QDialog):
    def __init__(self, action=None, parent=None):
        super().__init__(parent); self.setWindowTitle("Chỉnh sửa Hành động"); layout = QFormLayout(self); self.action_type = QComboBox(); self.action_type.addItems(["Nhấp vào", "Gõ vào", "Tìm và Ghi nhớ", "Tra cứu Tri thức", "Tính toán Ngày tháng", "Cập nhật Trạng thái"]); self.target_text = QLineEdit(); self.value_text = QLineEdit(); self.param1_label = QLabel("Label 1"); self.param2_label = QLabel("Label 2"); self.action_type.currentTextChanged.connect(self.update_ui); layout.addRow("Hành động:", self.action_type); layout.addRow(self.param1_label, self.target_text); layout.addRow(self.param2_label, self.value_text)
        if action: self.action_type.setCurrentText(action.get("type", "Nhấp vào")); self.target_text.setText(action.get("param1", "")); self.value_text.setText(action.get("param2", ""))
        self.update_ui(self.action_type.currentText())
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); button_box.accepted.connect(self.accept); button_box.rejected.connect(self.reject); layout.addWidget(button_box)
    def update_ui(self, action_type):
        self.param1_label.setVisible(True); self.target_text.setVisible(True); self.param2_label.setVisible(True); self.value_text.setVisible(True)
        if action_type == "Nhấp vào": self.param1_label.setText("Tìm văn bản:"); self.param2_label.setVisible(False); self.value_text.setVisible(False)
        elif action_type == "Gõ vào": self.param1_label.setText("Tìm văn bản (nhãn):"); self.param2_label.setText("Văn bản cần gõ:")
        elif action_type == "Tìm và Ghi nhớ": self.param1_label.setText("Tìm văn bản (nhãn):"); self.param2_label.setText("Lưu vào biến:")
        elif action_type == "Tra cứu Tri thức": self.param1_label.setText("Tên bảng & cột (Bảng.Cột):"); self.target_text.setPlaceholderText("e.g., COSCO_Rules.Service"); self.param2_label.setText("Giá trị tra cứu (biến):"); self.value_text.setPlaceholderText("e.g., $service_name")
        elif action_type == "Tính toán Ngày tháng": self.param1_label.setText("Ngày ETD (biến):"); self.param2_label.setText("Thời gian CY (biến):")
        elif action_type == "Cập nhật Trạng thái": self.param1_label.setText("Biến định danh:"); self.param2_label.setVisible(False); self.value_text.setVisible(False)
    def get_action(self): return {"type": self.action_type.currentText(), "param1": self.target_text.text(), "param2": self.value_text.text()}
class ProcessEditorDialog(QDialog):
    def __init__(self, process=None, parent=None):
        super().__init__(parent); self.setWindowTitle("Chỉnh sửa Quy trình"); self.setMinimumSize(600, 400); self.process = process if process else {"name": "Quy trình Mới", "mode": "Tự động", "actions": []}; main_layout = QVBoxLayout(self); form_layout = QFormLayout(); self.process_name = QLineEdit(self.process["name"]); self.execution_mode = QComboBox(); self.execution_mode.addItems(["Tự động", "Hỗ trợ"]); self.execution_mode.setCurrentText(self.process["mode"]); form_layout.addRow("Tên Quy trình:", self.process_name); form_layout.addRow("Chế độ thực thi:", self.execution_mode); main_layout.addLayout(form_layout); main_layout.addWidget(QLabel("Các bước thực hiện:")); self.actions_list = QListWidget(); self.actions_list.itemDoubleClicked.connect(self.edit_action); main_layout.addWidget(self.actions_list); actions_buttons_layout = QHBoxLayout(); add_btn = QPushButton("Thêm"); edit_btn = QPushButton("Sửa"); remove_btn = QPushButton("Xóa"); actions_buttons_layout.addWidget(add_btn); actions_buttons_layout.addWidget(edit_btn); actions_buttons_layout.addWidget(remove_btn); main_layout.addLayout(actions_buttons_layout); add_btn.clicked.connect(self.add_action); edit_btn.clicked.connect(self.edit_action); remove_btn.clicked.connect(self.remove_action); button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); button_box.accepted.connect(self.accept); button_box.rejected.connect(self.reject); main_layout.addWidget(button_box); self.refresh_actions_list()
    def add_action(self):
        dialog = ActionEditorDialog(parent=self)
        if dialog.exec(): self.process["actions"].append(dialog.get_action()); self.refresh_actions_list()
    def edit_action(self):
        current_row = self.actions_list.currentRow()
        if current_row < 0: return
        action_to_edit = self.process["actions"][current_row]; dialog = ActionEditorDialog(action=action_to_edit, parent=self)
        if dialog.exec(): self.process["actions"][current_row] = dialog.get_action(); self.refresh_actions_list()
    def remove_action(self):
        current_row = self.actions_list.currentRow()
        if current_row < 0: return
        del self.process["actions"][current_row]; self.refresh_actions_list()
    def refresh_actions_list(self):
        self.actions_list.clear()
        for i, action in enumerate(self.process["actions"]): self.actions_list.addItem(f"{i+1}. {action['type']}: '{action.get('param1', '')}' | '{action.get('param2', '')}'")
    def get_process(self): self.process["name"] = self.process_name.text(); self.process["mode"] = self.execution_mode.currentText(); return self.process
class ProcessManagerWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Quản lý Quy trình"); self.setMinimumSize(400, 300); self.processes = []; layout = QVBoxLayout(self); self.process_list = QListWidget(); self.process_list.itemDoubleClicked.connect(self.edit_process); layout.addWidget(self.process_list); buttons_layout = QHBoxLayout(); add_btn = QPushButton("Thêm Mới"); edit_btn = QPushButton("Chỉnh Sửa"); delete_btn = QPushButton("Xóa"); buttons_layout.addWidget(add_btn); buttons_layout.addWidget(edit_btn); buttons_layout.addWidget(delete_btn); layout.addLayout(buttons_layout); add_btn.clicked.connect(self.add_process); edit_btn.clicked.connect(self.edit_process); delete_btn.clicked.connect(self.delete_process); self.load_processes()
    def load_processes(self):
        try:
            with open(PROCESSES_FILE, 'r') as f: self.processes = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): self.processes = []
        self.refresh_list()
    def save_processes(self):
        with open(PROCESSES_FILE, 'w') as f: json.dump(self.processes, f, indent=4)
        self.parent().on_processes_changed(self.processes)
    def refresh_list(self):
        self.process_list.clear()
        for process in self.processes: self.process_list.addItem(f"{process['name']} ({process['mode']})")
    def add_process(self):
        dialog = ProcessEditorDialog(parent=self)
        if dialog.exec(): self.processes.append(dialog.get_process()); self.save_processes(); self.refresh_list()
    def edit_process(self):
        current_row = self.process_list.currentRow()
        if current_row < 0: return
        process_to_edit = self.processes[current_row]; dialog = ProcessEditorDialog(process=process_to_edit, parent=self)
        if dialog.exec(): self.processes[current_row] = dialog.get_process(); self.save_processes(); self.refresh_list()
    def delete_process(self):
        current_row = self.process_list.currentRow()
        if current_row < 0: return
        del self.processes[current_row]; self.save_processes(); self.refresh_list()
class RuleEditorDialog(QDialog):
    def __init__(self, rule=None, parent=None, processes=[]):
        super().__init__(parent); self.setWindowTitle("Chỉnh sửa Quy tắc"); self.form_layout = QFormLayout(self); self.condition_text = QLineEdit(); self.context_text = QLineEdit(); self.action_type = QComboBox(); self.action_type.addItems(["Tạo Ghi chú", "Tự động điền", "Làm nổi bật", "Chạy Quy trình"]); self.note_content_text = QLineEdit(); self.autofill_widget = QWidget(); autofill_layout = QHBoxLayout(self.autofill_widget); self.autofill_text = QLineEdit(); self.select_pos_button = QPushButton("Chọn vị trí"); self.pos_label = QLabel("Chưa chọn"); autofill_layout.addWidget(self.autofill_text); autofill_layout.addWidget(self.select_pos_button); autofill_layout.addWidget(self.pos_label); self.process_selector = QComboBox();
        for p in processes: self.process_selector.addItem(p["name"])
        self.form_layout.addRow("Nếu thấy văn bản:", self.condition_text); self.form_layout.addRow("Và tiêu đề cửa sổ chứa:", self.context_text); self.form_layout.addRow("Thì hành động:", self.action_type); self.form_layout.addRow("Nội dung Ghi chú:", self.note_content_text); self.form_layout.addRow("Nội dung Tự động điền:", self.autofill_widget); self.form_layout.addRow("Chọn Quy trình:", self.process_selector); self.action_type.currentIndexChanged.connect(self.update_action_widgets); self.select_pos_button.clicked.connect(self.select_position); self.autofill_pos = None
        if rule:
            self.condition_text.setText(rule.get("condition", "")); self.context_text.setText(rule.get("context", "")); action_type = rule.get("action_type", "Tạo Ghi chú"); self.action_type.setCurrentText(action_type)
            if action_type == "Tạo Ghi chú": self.note_content_text.setText(rule.get("action_data", ""))
            elif action_type == "Tự động điền": self.autofill_text.setText(rule.get("action_data", {}).get("text", "")); self.autofill_pos = rule.get("action_data", {}).get("position");
            if self.autofill_pos: self.pos_label.setText(f"({self.autofill_pos[0]}, {self.autofill_pos[1]})")
            elif action_type == "Chạy Quy trình": self.process_selector.setCurrentText(rule.get("action_data", ""))
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); button_box.accepted.connect(self.accept); button_box.rejected.connect(self.reject); self.form_layout.addWidget(button_box); self.update_action_widgets()
    def update_action_widgets(self): current_action = self.action_type.currentText(); self.note_content_text.setVisible(current_action == "Tạo Ghi chú"); self.autofill_widget.setVisible(current_action == "Tự động điền"); self.process_selector.setVisible(current_action == "Chạy Quy trình")
    def get_rule(self):
        action_type = self.action_type.currentText(); action_data = None
        if action_type == "Tạo Ghi chú": action_data = self.note_content_text.text()
        elif action_type == "Tự động điền": action_data = {"text": self.autofill_text.text(), "position": self.autofill_pos}
        elif action_type == "Chạy Quy trình": action_data = self.process_selector.currentText()
        return {"condition": self.condition_text.text(), "context": self.context_text.text(), "action_type": action_type, "action_data": action_data}
    def select_position(self): self.parent().hide(); self.pos_selector = PositionSelector(); self.pos_selector.position_selected.connect(self.on_position_selected); self.pos_selector.show()
    def on_position_selected(self, x, y): self.autofill_pos = (x, y); self.pos_label.setText(f"({x}, {y})"); self.parent().show()
class RuleManagerWindow(QDialog):
    def __init__(self, parent=None, processes=[]):
        super().__init__(parent); self.setWindowTitle("Quản lý Quy tắc"); self.setMinimumSize(500, 350); self.rules = []; self.processes = processes; layout = QVBoxLayout(self); self.rule_list = QListWidget(); self.rule_list.itemDoubleClicked.connect(self.edit_rule); layout.addWidget(self.rule_list); buttons_layout = QHBoxLayout(); self.add_button = QPushButton("Thêm Mới"); self.edit_button = QPushButton("Chỉnh Sửa"); self.delete_button = QPushButton("Xóa"); buttons_layout.addWidget(self.add_button); buttons_layout.addWidget(self.edit_button); buttons_layout.addWidget(self.delete_button); layout.addLayout(buttons_layout); self.add_button.clicked.connect(self.add_rule); self.edit_button.clicked.connect(self.edit_rule); self.delete_button.clicked.connect(self.delete_rule); self.load_rules()
    def refresh_list(self):
        self.rule_list.clear()
        for rule in self.rules:
            context_str = f" trong \"{rule['context']}\"" if rule.get('context') else ""; display_text = f"Nếu thấy \"{rule['condition']}\"{context_str} -> "
            action_type = rule['action_type']
            if action_type == "Tạo Ghi chú": display_text += f"Tạo ghi chú \"{rule['action_data']}\""
            elif action_type == "Làm nổi bật": display_text += "Làm nổi bật văn bản"
            elif action_type == "Chạy Quy trình": display_text += f"Chạy quy trình \"{rule['action_data']}\""
            elif action_type == "Tự động điền": pos = rule.get('action_data', {}).get('position'); display_text += f"Tự động điền tại {pos}"
            self.rule_list.addItem(QListWidgetItem(display_text))
    def add_rule(self):
        dialog = RuleEditorDialog(parent=self, processes=self.processes)
        if dialog.exec():
            new_rule = dialog.get_rule()
            if new_rule['condition']: self.rules.append(new_rule); self.save_rules(); self.refresh_list()
    def edit_rule(self):
        current_row = self.rule_list.currentRow()
        if current_row < 0: return
        rule_to_edit = self.rules[current_row]; dialog = RuleEditorDialog(rule=rule_to_edit, parent=self, processes=self.processes)
        if dialog.exec():
            updated_rule = dialog.get_rule()
            if updated_rule['condition']: self.rules[current_row] = updated_rule; self.save_rules(); self.refresh_list()
    def load_rules(self):
        try:
            with open(RULES_FILE, 'r') as f: self.rules = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): self.rules = []
        self.refresh_list()
    def save_rules(self):
        with open(RULES_FILE, 'w') as f: json.dump(self.rules, f, indent=4)
        self.parent().on_rules_changed(self.rules)
    def delete_rule(self):
        current_row = self.rule_list.currentRow()
        if current_row < 0: return
        del self.rules[current_row]; self.save_rules(); self.refresh_list()
class TableEditorDialog(QDialog):
    def __init__(self, table_data, parent=None):
        super().__init__(parent); self.table_data = table_data; self.setWindowTitle(f"Chỉnh sửa Bảng: {self.table_data['name']}"); self.setMinimumSize(500, 400); layout = QVBoxLayout(self); self.table_widget = QTableWidget(); self.table_widget.setColumnCount(len(self.table_data['columns'])); self.table_widget.setHorizontalHeaderLabels(self.table_data['columns'])
        for row_data in self.table_data['data']:
            row_position = self.table_widget.rowCount(); self.table_widget.insertRow(row_position)
            for col_index, cell_data in enumerate(row_data): self.table_widget.setItem(row_position, col_index, QTableWidgetItem(str(cell_data)))
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); layout.addWidget(self.table_widget); button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok); button_box.accepted.connect(self.accept); layout.addWidget(button_box)
class KnowledgeBaseManager(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Quản lý Kho Tri thức"); self.setMinimumSize(400, 300); self.kb = {}
        layout = QVBoxLayout(self); self.table_list = QListWidget(); self.table_list.itemDoubleClicked.connect(self.edit_table); layout.addWidget(self.table_list)
        buttons_layout = QHBoxLayout(); add_btn = QPushButton("Thêm Bảng"); edit_btn = QPushButton("Sửa Bảng"); del_btn = QPushButton("Xóa Bảng"); buttons_layout.addWidget(add_btn); buttons_layout.addWidget(edit_btn); buttons_layout.addWidget(del_btn); layout.addLayout(buttons_layout)
        edit_btn.clicked.connect(self.edit_table); self.load_kb()
    def load_kb(self):
        try:
            with open(KB_FILE, 'r') as f: self.kb = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.kb = {"COSCO_CY_Rules": {"name": "COSCO_CY_Rules", "columns": ["Service", "CY Time"], "data": [["I16", "Friday 06:00 AM"], ["SV1", "Sunday 08:00 AM"]]}}
            self.save_kb()
        self.refresh_list()
    def save_kb(self):
        with open(KB_FILE, 'w') as f: json.dump(self.kb, f, indent=4)
        self.parent().on_kb_changed(self.kb)
    def refresh_list(self):
        self.table_list.clear()
        for table_name in self.kb.keys(): self.table_list.addItem(table_name)
    def edit_table(self):
        selected_items = self.table_list.selectedItems()
        if not selected_items: return
        table_name = selected_items[0].text(); table_data = self.kb[table_name]
        dialog = TableEditorDialog(table_data, self); dialog.exec()
class AutomationEngine(QThread):
    scan_complete = pyqtSignal(object, str)
    identifier_found = pyqtSignal(str, QRect)
    def __init__(self, parent=None): super().__init__(parent); self.running = True; self.monitoring_mode = False
    def get_active_window_title(self):
        try:
            active_window = gw.getActiveWindow()
            return active_window.title if active_window else ""
        except Exception:
            # Fallback for headless environments or other issues
            return ""
    def run(self):
        while self.running:
            try:
                window_title = self.get_active_window_title()
                with mss() as sct:
                    monitor = sct.monitors[1]; sct_img = sct.grab(monitor); img = np.array(sct_img); img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    ocr_data_str = pytesseract.image_to_data(img, timeout=4); df = pd.read_csv(StringIO(ocr_data_str), sep='\t'); df.dropna(subset=['conf'], inplace=True); df = df[df.conf > 30]
                    self.scan_complete.emit(df, window_title)
                    if self.monitoring_mode: self.find_and_emit_identifiers(df)
            except Exception as e: print(f"Error in automation engine: {e}")
            time.sleep(5)
    def find_and_emit_identifiers(self, df):
        booking_regex = re.compile(r'^[A-Z]{3}\d{7}$')
        for index, row in df.iterrows():
            text = str(row['text']).strip()
            if booking_regex.match(text):
                rect = QRect(int(row['left']), int(row['top']), int(row['width']), int(row['height']))
                self.identifier_found.emit(text, rect)
    def stop(self): self.running = False; self.wait()
class ProcessRunner(QThread):
    log_message = pyqtSignal(str); request_highlight = pyqtSignal(QRect); request_suggestion = pyqtSignal(str, QPoint); request_correction = pyqtSignal(dict, str)
    def __init__(self, process, ocr_df, kb, state_manager, parent=None):
        super().__init__(parent); self.process = process; self.ocr_df = ocr_df; self.kb = kb; self.state_manager = state_manager; self.variables = {}; self.continue_event = QEventLoop(); self.corrected_action = None
    def find_text_location(self, text_to_find):
        words = text_to_find.split()
        if not words: return None
        df = self.ocr_df; df['text_str'] = df['text'].astype(str)
        for i in range(len(df) - len(words) + 1):
            chunk = df.iloc[i:i+len(words)]; sequence = " ".join(chunk['text_str'])
            if sequence == text_to_find:
                x_min = chunk['left'].min(); y_min = chunk['top'].min(); x_max = (chunk['left'] + chunk['width']).max(); y_max = (chunk['top'] + chunk['height']).max()
                return QRect(int(x_min), int(y_min), int(x_max - x_min), int(y_max - y_min))
        return None
    def find_text_to_right_of(self, rect):
        df = self.ocr_df; same_line_df = df[ (df['top'] >= rect.top() - 10) & (df['top'] <= rect.bottom() + 10) & (df['left'] > rect.right())]
        if same_line_df.empty: return ""
        return " ".join(same_line_df.sort_values('left')['text'].astype(str))
    def resume_with_correction(self, new_action): self.corrected_action = new_action; self.continue_event.quit()
    def run(self):
        self.log_message.emit(f"Bắt đầu quy trình '{self.process['name']}' ({self.process['mode']})")
        for i, action in enumerate(self.process['actions']):
            param1 = self.variables.get(action.get('param1', ''), action.get('param1', ''))
            param2 = self.variables.get(action.get('param2', ''), action.get('param2', ''))
            self.log_message.emit(f"Bước {i+1}: {action['type']} '{param1}'")
            target_rect = None
            if action['type'] in ["Nhấp vào", "Gõ vào", "Tìm và Ghi nhớ"]: target_rect = self.find_text_location(param1)
            if not target_rect and action['type'] in ["Nhấp vào", "Gõ vào", "Tìm và Ghi nhớ"]:
                self.log_message.emit(f"Lỗi: Không tìm thấy '{param1}' trên màn hình."); self.request_correction.emit(action, self.process['name']); self.continue_event.exec()
                if self.corrected_action:
                    self.log_message.emit("Đã nhận được chỉnh sửa. Thử lại..."); action = self.corrected_action; self.process['actions'][i] = action; param1 = action['param1']; target_rect = self.find_text_location(param1)
                    if not target_rect: self.log_message.emit("Vẫn không tìm thấy mục tiêu sau khi sửa. Dừng quy trình."); break
                else: self.log_message.emit("Người dùng đã hủy. Dừng quy trình."); break
            if self.process['mode'] == "Tự động": self.execute_action_auto(action, target_rect, param1, param2)
            else: self.execute_action_assist(action, target_rect); break
            time.sleep(1)
        self.log_message.emit("Hoàn thành quy trình.")
    def execute_action_auto(self, action, rect, param1, param2):
        action_type = action['type']
        if action_type == "Nhấp vào": pyautogui.click(rect.center().x(), rect.center().y())
        elif action_type == "Gõ vào": pyautogui.click(rect.center().x() + rect.width(), rect.center().y()); pyautogui.write(param2, interval=0.05)
        elif action_type == "Tìm và Ghi nhớ":
            found_text = self.find_text_to_right_of(rect)
            self.variables[param2] = found_text.split()[0] if found_text else ""
            self.log_message.emit(f"Đã ghi nhớ '{self.variables[param2]}' vào biến '{param2}'")
        elif action_type == "Tra cứu Tri thức":
            table_name, column_name = param1.split('.'); lookup_value = param2
            result_col_name = "CY Time"
            table = self.kb.get(table_name)
            if table:
                lookup_col_index = table['columns'].index(column_name); result_col_index = table['columns'].index(result_col_name)
                for row in table['data']:
                    if str(row[lookup_col_index]) == lookup_value:
                        self.variables['$cy_time'] = row[result_col_index]
                        self.log_message.emit(f"Tra cứu thành công: found '{row[result_col_index]}' in '{table_name}'"); return
            self.log_message.emit(f"Lỗi: Không tìm thấy kết quả cho '{lookup_value}' trong '{table_name}'")
        elif action_type == "Tính toán Ngày tháng":
            etd_str = param1; cy_time_str = param2
            try:
                etd_date = parse(etd_str); cy_day_str, cy_time_part, cy_am_pm = cy_time_str.split(' ')
                cy_weekday = {"MONDAY": 0, "TUESDAY": 1, "WEDNESDAY": 2, "THURSDAY": 3, "FRIDAY": 4, "SATURDAY": 5, "SUNDAY": 6}[cy_day_str.upper()]
                final_cy_date = etd_date + timedelta(days=cy_weekday - etd_date.weekday())
                if final_cy_date > etd_date: final_cy_date -= timedelta(days=7)
                final_cy_datetime_str = f"{final_cy_date.strftime('%d/%m/%Y')} {cy_time_part} {cy_am_pm}"
                self.variables['$final_cy_date'] = final_cy_datetime_str
                self.log_message.emit(f"Đã tính toán CY: {final_cy_datetime_str}")
            except Exception as e: self.log_message.emit(f"Lỗi tính toán ngày: {e}")
        elif action_type == "Cập nhật Trạng thái":
            identifier_to_update = self.variables.get(param1)
            if identifier_to_update:
                self.state_manager.update_status(identifier_to_update)
                self.log_message.emit(f"Đã cập nhật trạng thái cho '{identifier_to_update}'")
            else:
                self.log_message.emit(f"Lỗi: Không tìm thấy biến '{param1}' để cập nhật trạng thái.")

    def execute_action_assist(self, action, rect):
        self.request_highlight.emit(rect); action_type = action['type']; suggestion_text = ""
        self.request_suggestion.emit(suggestion_text, rect.topRight())

class FloatingMenu(QMainWindow):
    def __init__(self):
        super().__init__(); self.notes = []; self.rules = []; self.processes = []; self.kb = {}; self.recently_triggered = {}; self.highlight_windows = []; self.status_overlays = []
        self.setWindowTitle("Floating Menu"); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        central_widget = QWidget(); self.setCentralWidget(central_widget); layout = QHBoxLayout(central_widget)
        self.extract_button = QPushButton("Trích xuất văn bản"); self.create_note_button = QPushButton("Tạo Ghi chú"); self.rules_button = QPushButton("Quản lý Quy tắc"); self.processes_button = QPushButton("Quản lý Quy trình"); self.kb_button = QPushButton("Kho Tri thức"); self.monitor_button = QPushButton("Bắt đầu Giám sát"); self.monitor_button.setCheckable(True)
        layout.addWidget(self.extract_button); layout.addWidget(self.create_note_button); layout.addWidget(self.rules_button); layout.addWidget(self.processes_button); layout.addWidget(self.kb_button); layout.addWidget(self.monitor_button)
        self.setStyleSheet("""QMainWindow {{ background-color: rgba(30, 30, 30, 200); border-radius: 10px; }} QPushButton {{ background-color: #555; color: white; border: 1px solid #777; padding: 8px; border-radius: 5px; }} QPushButton:hover {{ background-color: #777; }} QPushButton:checked {{ background-color: #0078D7; border-color: #005A9E; }}""")
        self.process_manager = ProcessManagerWindow(self); self.rule_manager = RuleManagerWindow(self, processes=self.process_manager.processes); self.kb_manager = KnowledgeBaseManager(self); self.state_manager = StateManager()
        self.extract_button.clicked.connect(self.start_selection); self.create_note_button.clicked.connect(self.create_note); self.rules_button.clicked.connect(self.rule_manager.exec); self.processes_button.clicked.connect(self.process_manager.exec); self.kb_button.clicked.connect(self.kb_manager.exec); self.monitor_button.clicked.connect(self.toggle_monitoring)
        self._drag_start_position = None; self.selector = None
        self.load_notes(); self.on_rules_changed(self.rule_manager.rules); self.on_processes_changed(self.process_manager.processes); self.on_kb_changed(self.kb_manager.kb)
        self.automation_engine = AutomationEngine(self); self.automation_engine.scan_complete.connect(self.process_screen_data); self.automation_engine.identifier_found.connect(self.handle_identifier); self.automation_engine.start()
        self.process_runner = None
    def toggle_monitoring(self, checked):
        self.automation_engine.monitoring_mode = checked
        self.monitor_button.setText("Dừng Giám sát" if checked else "Bắt đầu Giám sát")
    def handle_identifier(self, identifier, rect):
        timestamp = self.state_manager.check_status(identifier)
        status_text = f"Đã lên tàu lúc: {timestamp}" if timestamp else "Chưa lên tàu"

        # Position the overlay slightly above the found identifier
        overlay_geom = QRect(rect.x(), rect.y() - 35, 150, 30) # A fixed size for now

        overlay = StatusOverlay(identifier, status_text, overlay_geom)
        overlay.show()
        self.status_overlays.append(overlay)
        # Clean up closed overlays
        self.status_overlays = [o for o in self.status_overlays if o.isVisible()]
    def analyze_and_suggest(self, text, ocr_df):
        pyperclip.copy(text); suggestions = []
        for process in self.processes:
            if process['name'].lower() in text.lower(): suggestions.append(f"Chạy quy trình: {process['name']}")
        dialog = SuggestionDialog(suggestions, self)
        if dialog.exec():
            action = dialog.selected_action
            if action and action.startswith("Chạy quy trình:"):
                process_name = action.replace("Chạy quy trình: ", "")
                process_to_run = next((p for p in self.processes if p['name'] == process_name), None)
                if process_to_run:
                    self.process_runner = ProcessRunner(process_to_run, ocr_df, self.kb, self.state_manager, self); self.process_runner.log_message.connect(print); self.process_runner.request_highlight.connect(self.show_highlight); self.process_runner.request_suggestion.connect(self.show_suggestion); self.process_runner.request_correction.connect(self.handle_correction_request); self.process_runner.start()
            elif action == "Tạo Quy trình mới...":
                self.process_manager.exec()
        self.show()
    def find_text_location(self, df, text_to_find):
        words = text_to_find.split()
        if not words: return None
        df['text_str'] = df['text'].astype(str)
        for i in range(len(df) - len(words) + 1):
            chunk = df.iloc[i:i+len(words)]; sequence = " ".join(chunk['text_str'])
            if sequence == text_to_find:
                x_min = chunk['left'].min(); y_min = chunk['top'].min(); x_max = (chunk['left'] + chunk['width']).max(); y_max = (chunk['top'] + chunk['height']).max()
                return QRect(int(x_min), int(y_min), int(x_max - x_min), int(y_max - y_min))
        return None
    def process_screen_data(self, ocr_df, window_title):
        if self.process_runner and self.process_runner.isRunning(): return
        current_time = time.time(); full_text = " ".join(ocr_df['text'].astype(str))
        for rule in self.rules:
            context_condition_met = (not rule.get('context')) or (rule.get('context', '') in window_title)
            if not context_condition_met: continue
            text_condition = rule['condition']
            if text_condition in full_text:
                trigger_key = f"{text_condition}|{rule.get('context', '')}"; last_triggered = self.recently_triggered.get(trigger_key, 0)
                if current_time - last_triggered > 60: self.execute_action(rule, ocr_df); self.recently_triggered[trigger_key] = current_time; break
    def execute_action(self, rule, ocr_df):
        action_type = rule['action_type']
        if action_type == "Chạy Quy trình":
            process_name = rule['action_data']
            process_to_run = next((p for p in self.processes if p['name'] == process_name), None)
            if process_to_run:
                self.process_runner = ProcessRunner(process_to_run, ocr_df, self.kb, self.state_manager, self); self.process_runner.log_message.connect(print); self.process_runner.request_highlight.connect(self.show_highlight); self.process_runner.request_suggestion.connect(self.show_suggestion); self.process_runner.request_correction.connect(self.handle_correction_request); self.process_runner.start()
        elif action_type == "Tạo Ghi chú": self.create_note(content=rule['action_data'])
        elif action_type == "Tự động điền":
            pos = rule['action_data'].get("position"); text_to_type = rule['action_data'].get("text", "")
            if pos: pyautogui.click(x=pos[0], y=pos[1]); pyautogui.write(text_to_type, interval=0.05)
        elif action_type == "Làm nổi bật":
            rect = self.find_text_location(ocr_df, rule['condition'])
            if rect: self.show_highlight(rect)
    def handle_correction_request(self, failed_action, process_name):
        msg_box = QMessageBox(self); msg_box.setWindowTitle("Quy trình Tạm dừng"); msg_box.setText(f"Không thể tìm thấy văn bản: '{failed_action['param1']}'.\nBạn có muốn chỉ lại không?"); msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No); msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
        if msg_box.exec() == QMessageBox.StandardButton.Yes:
            self.start_selection(callback=lambda rect: self.process_correction(rect, failed_action, process_name))
        else:
            self.process_runner.resume_with_correction(None)
    def process_correction(self, rect, failed_action, process_name):
        new_text = self.capture_and_ocr(rect, copy_to_clipboard=False)
        if not new_text:
            self.process_runner.resume_with_correction(None); return
        confirm_msg = QMessageBox(self); confirm_msg.setWindowTitle("Xác nhận Học"); confirm_msg.setText(f"Bạn có muốn cập nhật hành động này để tìm văn bản mới '{new_text}' không?"); confirm_msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm_msg.exec() == QMessageBox.StandardButton.Yes:
            corrected_action = failed_action.copy(); corrected_action['param1'] = new_text
            for p in self.processes:
                if p['name'] == process_name:
                    for i, act in enumerate(p['actions']):
                        if act['param1'] == failed_action['param1']: p['actions'][i] = corrected_action; break
                    break
            self.process_manager.save_processes()
            self.process_runner.resume_with_correction(corrected_action)
        else: self.process_runner.resume_with_correction(None)
    def show_highlight(self, rect): hw = HighlightWindow(rect); hw.show(); self.highlight_windows.append(hw)
    def show_suggestion(self, text, pos): self.create_note(content=text, geometry=(pos.x(), pos.y(), 250, 80))
    def on_rules_changed(self, new_rules): self.rules = new_rules
    def on_processes_changed(self, new_processes): self.processes = new_processes; self.rule_manager.processes = new_processes
    def on_kb_changed(self, new_kb): self.kb = new_kb
    def backup_note(self, content):
        try:
            with open(BACKUP_FILE, 'r') as f: backup_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): backup_data = {}
        today_str = datetime.now().strftime("%Y-%m-%d"); now_str = datetime.now().strftime("%H:%M:%S")
        if today_str not in backup_data: backup_data[today_str] = []
        backup_data[today_str].append({"time": now_str, "content": content})
        with open(BACKUP_FILE, 'w') as f: json.dump(backup_data, f, indent=4)
    def create_note(self, content="", geometry=None, opacities=None): note = NoteWindow(self, content, geometry, opacities); self.notes.append(note); note.show(); self.save_notes()
    def remove_note(self, note):
        if note in self.notes: self.notes.remove(note)
        self.save_notes()
    def save_notes(self):
        data = [note.to_dict() for note in self.notes]
        with open(NOTES_FILE, 'w') as f: json.dump(data, f, indent=4)
    def load_notes(self):
        try:
            with open(NOTES_FILE, 'r') as f: data = json.load(f);
            for note_data in data: self.create_note(**note_data)
        except (FileNotFoundError, json.JSONDecodeError): pass
    def closeEvent(self, event): self.automation_engine.stop(); self.save_notes(); super().closeEvent(event)
    def start_selection(self, callback=None):
        if not callback:
            callback = lambda rect: self.analyze_and_suggest_wrapper(rect)
        self.hide(); self.selector = ScreenSelector(self, callback=callback); self.selector.show()
    def analyze_and_suggest_wrapper(self, rect):
        with mss() as sct:
            monitor = sct.monitors[1]; sct_img = sct.grab(monitor); img = np.array(sct_img)
            full_screen_df = pd.read_csv(StringIO(pytesseract.image_to_data(img)), sep='\t')
        text_in_rect = self.capture_and_ocr(rect, copy_to_clipboard=False)
        self.analyze_and_suggest(text_in_rect, full_screen_df)
    def capture_and_ocr(self, rect, copy_to_clipboard=True):
        try:
            with mss() as sct:
                monitor = {"top": rect.y(), "left": rect.x(), "width": rect.width(), "height": rect.height()}; sct_img = sct.grab(monitor)
                img = np.array(sct_img); img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR); text = pytesseract.image_to_string(img).strip()
                if copy_to_clipboard: pyperclip.copy(text)
                return text
        except Exception as e: print(f"An error occurred: {e}"); return ""
        finally:
            if not self.process_runner or not self.process_runner.isRunning(): self.show()
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self._drag_start_position = event.globalPosition().toPoint() - self.pos()
    def mouseMoveEvent(self, event):
        if self._drag_start_position: self.move(event.globalPosition().toPoint() - self.pos())
    def mouseReleaseEvent(self, event): self._drag_start_position = None

if __name__ == '__main__':
    app = QApplication(sys.argv)
    menu = FloatingMenu()
    menu.show()
    sys.exit(app.exec())

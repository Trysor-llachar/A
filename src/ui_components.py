import sys
import json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QHBoxLayout,
                             QWidget, QRubberBand, QVBoxLayout, QTextEdit, QLabel,
                             QSlider, QDialog, QListWidget, QLineEdit, QFormLayout,
                             QDialogButtonBox, QListWidgetItem, QComboBox, QMessageBox,
                             QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox)
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from src.config import PROCESSES_FILE, RULES_FILE, KB_FILE, NAVIGATION_PATHS_FILE

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
        super().__init__(parent); self.setWindowTitle("Quản lý Quy trình"); self.setMinimumSize(400, 300); self.processes = []; layout = QVBoxLayout(self); self.process_list = QListWidget(); self.process_list.itemDoubleClicked.connect(self.edit_process); layout.addWidget(self.process_list); buttons_layout = QHBoxLayout(); add_btn = QPushButton("Thêm Mới"); edit_btn = QPushButton("Chỉnh Sửa"); delete_btn = QPushButton("Xóa"); buttons_layout.addWidget(add_btn); buttons_layout.addWidget(edit_btn); buttons_layout.addWidget(delete_btn); layout.addLayout(buttons_layout); add_btn.clicked.connect(self.add_process); edit_btn.clicked.connect(self.edit_process); delete_btn.clicked.connect(self.delete_process)

    def exec(self):
        self.load_processes()
        return super().exec()

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
        super().__init__(parent); self.setWindowTitle("Quản lý Quy tắc"); self.setMinimumSize(500, 350); self.rules = []; self.processes = processes; layout = QVBoxLayout(self); self.rule_list = QListWidget(); self.rule_list.itemDoubleClicked.connect(self.edit_rule); layout.addWidget(self.rule_list); buttons_layout = QHBoxLayout(); self.add_button = QPushButton("Thêm Mới"); self.edit_button = QPushButton("Chỉnh Sửa"); self.delete_button = QPushButton("Xóa"); buttons_layout.addWidget(self.add_button); buttons_layout.addWidget(self.edit_button); buttons_layout.addWidget(self.delete_button); layout.addLayout(buttons_layout); self.add_button.clicked.connect(self.add_rule); self.edit_button.clicked.connect(self.edit_rule); self.delete_button.clicked.connect(self.delete_rule)

    def exec(self):
        self.load_rules()
        return super().exec()

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
        edit_btn.clicked.connect(self.edit_table)

    def exec(self):
        self.load_kb()
        return super().exec()

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

class PatternEditorDialog(QDialog):
    def __init__(self, pattern=None, parent=None):
        super().__init__(parent)
        self.pattern = pattern if pattern else {"name": "", "regex": ""}
        self.setWindowTitle("Chỉnh sửa Mẫu")

        layout = QFormLayout(self)
        self.name_edit = QLineEdit(self.pattern["name"])
        self.regex_edit = QLineEdit(self.pattern["regex"])
        layout.addRow("Tên Mẫu:", self.name_edit)
        layout.addRow("Regex:", self.regex_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(button_box)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

    def get_pattern(self):
        return {"name": self.name_edit.text(), "regex": self.regex_edit.text()}

class LineEditorDialog(QDialog):
    def __init__(self, line_data=None, parent=None):
        super().__init__(parent)
        self.line_data = line_data if line_data else {"name": "", "patterns": []}
        self.setWindowTitle("Chỉnh sửa Line")

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.name_edit = QLineEdit(self.line_data["name"])
        form_layout.addRow("Tên Line:", self.name_edit)
        layout.addLayout(form_layout)

        layout.addWidget(QLabel("Mẫu Mã (Regex):"))
        self.patterns_list = QListWidget()
        for p in self.line_data["patterns"]:
            self.patterns_list.addItem(f"{p['name']}: {p['regex']}")
        layout.addWidget(self.patterns_list)

        patterns_buttons_layout = QHBoxLayout()
        add_pattern_btn = QPushButton("Thêm Mẫu")
        edit_pattern_btn = QPushButton("Sửa Mẫu")
        remove_pattern_btn = QPushButton("Xóa Mẫu")
        patterns_buttons_layout.addWidget(add_pattern_btn)
        patterns_buttons_layout.addWidget(edit_pattern_btn)
        patterns_buttons_layout.addWidget(remove_pattern_btn)
        layout.addLayout(patterns_buttons_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(button_box)

        add_pattern_btn.clicked.connect(self.add_pattern)
        edit_pattern_btn.clicked.connect(self.edit_pattern)
        remove_pattern_btn.clicked.connect(self.remove_pattern)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

    def add_pattern(self):
        dialog = PatternEditorDialog(parent=self)
        if dialog.exec():
            self.line_data["patterns"].append(dialog.get_pattern())
            self.refresh_patterns_list()

    def edit_pattern(self):
        current_row = self.patterns_list.currentRow()
        if current_row < 0:
            return
        pattern_to_edit = self.line_data["patterns"][current_row]
        dialog = PatternEditorDialog(pattern=pattern_to_edit, parent=self)
        if dialog.exec():
            self.line_data["patterns"][current_row] = dialog.get_pattern()
            self.refresh_patterns_list()

    def remove_pattern(self):
        current_row = self.patterns_list.currentRow()
        if current_row >= 0:
            del self.line_data["patterns"][current_row]
            self.refresh_patterns_list()

    def refresh_patterns_list(self):
        self.patterns_list.clear()
        for p in self.line_data["patterns"]:
            self.patterns_list.addItem(f"{p['name']}: {p['regex']}")

    def get_line_data(self):
        self.line_data["name"] = self.name_edit.text()
        return self.line_data

class LineManagerWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quản lý Lines")
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout(self)
        self.lines_list = QListWidget()
        self.lines_list.itemDoubleClicked.connect(self.edit_line)
        layout.addWidget(self.lines_list)

        buttons_layout = QHBoxLayout()
        add_btn = QPushButton("Thêm Mới")
        edit_btn = QPushButton("Chỉnh Sửa")
        delete_btn = QPushButton("Xóa")
        buttons_layout.addWidget(add_btn)
        buttons_layout.addWidget(edit_btn)
        buttons_layout.addWidget(delete_btn)
        layout.addLayout(buttons_layout)

        add_btn.clicked.connect(self.add_line)
        edit_btn.clicked.connect(self.edit_line)
        delete_btn.clicked.connect(self.delete_line)

    def exec(self):
        self.refresh_lines_list()
        return super().exec()

    def refresh_lines_list(self):
        self.lines_list.clear()
        lines = self.parent().line_manager.get_all_lines()
        for line_name in lines:
            self.lines_list.addItem(line_name)

    def add_line(self):
        dialog = LineEditorDialog(parent=self)
        if dialog.exec():
            new_line_data = dialog.get_line_data()
            if new_line_data["name"]:
                self.parent().line_manager.add_line(new_line_data)
                self.refresh_lines_list()

    def edit_line(self):
        selected_items = self.lines_list.selectedItems()
        if not selected_items:
            return
        line_name = selected_items[0].text()
        line_data = self.parent().line_manager.get_line(line_name)

        dialog = LineEditorDialog(line_data, self)
        if dialog.exec():
            updated_line_data = dialog.get_line_data()
            self.parent().line_manager.update_line(line_name, updated_line_data)
            self.refresh_lines_list()

    def delete_line(self):
        selected_items = self.lines_list.selectedItems()
        if not selected_items:
            return
        line_name = selected_items[0].text()
        self.parent().line_manager.delete_line(line_name)
        self.refresh_lines_list()

# --- Navigation Path Components ---

class PathActionEditorDialog(QDialog):
    """Dialog for editing a single action in a Navigation Path."""
    def __init__(self, action=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chỉnh sửa Bước Điều hướng")
        layout = QFormLayout(self)

        self.action_type = QComboBox()
        self.action_type.addItems(["Nhấp vào văn bản", "Nhấp vào hình ảnh"])
        layout.addRow("Hành động:", self.action_type)

        self.param1_label = QLabel("Văn bản:")
        self.param1_edit = QLineEdit()
        self.select_button = QPushButton("Chọn trên màn hình")
        param1_layout = QHBoxLayout()
        param1_layout.addWidget(self.param1_edit)
        param1_layout.addWidget(self.select_button)
        layout.addRow(self.param1_label, param1_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.action_type.currentTextChanged.connect(self.update_ui)

        if action:
            self.action_type.setCurrentText(action.get("type", "Nhấp vào văn bản"))
            self.param1_edit.setText(action.get("value", ""))

        self.update_ui(self.action_type.currentText())

    def update_ui(self, action_type):
        if action_type == "Nhấp vào văn bản":
            self.param1_label.setText("Văn bản:")
            self.select_button.setText("Trích xuất...")
            # self.select_button.clicked.connect(self.select_text_on_screen)
        elif action_type == "Nhấp vào hình ảnh":
            self.param1_label.setText("Tệp hình ảnh:")
            self.select_button.setText("Chọn vùng...")
            # self.select_button.clicked.connect(self.select_image_on_screen)

    def get_action(self):
        return {
            "type": self.action_type.currentText(),
            "value": self.param1_edit.text()
        }

class PathEditorDialog(QDialog):
    """Dialog for editing a Navigation Path (name and list of actions)."""
    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chỉnh sửa Lộ trình Điều hướng")
        self.setMinimumSize(500, 350)
        self.path = path if path else {"name": "Lộ trình Mới", "actions": []}

        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.path_name_edit = QLineEdit(self.path["name"])
        form_layout.addRow("Tên Lộ trình:", self.path_name_edit)
        main_layout.addLayout(form_layout)

        main_layout.addWidget(QLabel("Các bước thực hiện:"))
        self.actions_list = QListWidget()
        self.actions_list.itemDoubleClicked.connect(self.edit_action)
        main_layout.addWidget(self.actions_list)

        actions_buttons_layout = QHBoxLayout()
        add_btn = QPushButton("Thêm")
        edit_btn = QPushButton("Sửa")
        remove_btn = QPushButton("Xóa")
        actions_buttons_layout.addWidget(add_btn)
        actions_buttons_layout.addWidget(edit_btn)
        actions_buttons_layout.addWidget(remove_btn)
        main_layout.addLayout(actions_buttons_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        main_layout.addWidget(button_box)

        add_btn.clicked.connect(self.add_action)
        edit_btn.clicked.connect(self.edit_action)
        remove_btn.clicked.connect(self.remove_action)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        self.refresh_actions_list()

    def add_action(self):
        dialog = PathActionEditorDialog(parent=self)
        if dialog.exec():
            self.path["actions"].append(dialog.get_action())
            self.refresh_actions_list()

    def edit_action(self):
        current_row = self.actions_list.currentRow()
        if current_row < 0: return
        action_to_edit = self.path["actions"][current_row]
        dialog = PathActionEditorDialog(action=action_to_edit, parent=self)
        if dialog.exec():
            self.path["actions"][current_row] = dialog.get_action()
            self.refresh_actions_list()

    def remove_action(self):
        current_row = self.actions_list.currentRow()
        if current_row >= 0:
            del self.path["actions"][current_row]
            self.refresh_actions_list()

    def refresh_actions_list(self):
        self.actions_list.clear()
        for i, action in enumerate(self.path["actions"]):
            self.actions_list.addItem(f"{i + 1}. {action['type']}: {action['value']}")

    def get_path(self):
        self.path["name"] = self.path_name_edit.text()
        return self.path

class NavigationPathManagerWindow(QDialog):
    """Main window for managing all Navigation Paths."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quản lý Lộ trình Điều hướng")
        self.setMinimumSize(400, 300)
        self.paths = []

        layout = QVBoxLayout(self)
        self.paths_list = QListWidget()
        self.paths_list.itemDoubleClicked.connect(self.edit_path)
        layout.addWidget(self.paths_list)

        buttons_layout = QHBoxLayout()
        add_btn = QPushButton("Thêm Mới")
        edit_btn = QPushButton("Chỉnh Sửa")
        delete_btn = QPushButton("Xóa")
        buttons_layout.addWidget(add_btn)
        buttons_layout.addWidget(edit_btn)
        buttons_layout.addWidget(delete_btn)
        layout.addLayout(buttons_layout)

        add_btn.clicked.connect(self.add_path)
        edit_btn.clicked.connect(self.edit_path)
        delete_btn.clicked.connect(self.delete_path)

    def exec(self):
        self.load_paths()
        return super().exec()

    def load_paths(self):
        try:
            with open(NAVIGATION_PATHS_FILE, 'r') as f:
                self.paths = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.paths = []
        self.refresh_paths_list()

    def save_paths(self):
        with open(NAVIGATION_PATHS_FILE, 'w') as f:
            json.dump(self.paths, f, indent=4)

    def refresh_paths_list(self):
        self.paths_list.clear()
        for path in self.paths:
            self.paths_list.addItem(path.get("name", "Unnamed Path"))

    def add_path(self):
        dialog = PathEditorDialog(parent=self)
        if dialog.exec():
            new_path = dialog.get_path()
            if new_path["name"]:
                self.paths.append(new_path)
                self.save_paths()
                self.refresh_paths_list()

    def edit_path(self):
        current_row = self.paths_list.currentRow()
        if current_row < 0: return
        path_to_edit = self.paths[current_row]
        dialog = PathEditorDialog(path=path_to_edit, parent=self)
        if dialog.exec():
            self.paths[current_row] = dialog.get_path()
            self.save_paths()
            self.refresh_paths_list()

    def delete_path(self):
        current_row = self.paths_list.currentRow()
        if current_row >= 0:
            del self.paths[current_row]
            self.save_paths()
            self.refresh_paths_list()

class PathSelectionDialog(QDialog):
    """Dialog to select a Navigation Path to execute."""
    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chọn Lộ trình để Thực thi")
        self.selected_path_name = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Vui lòng chọn một Lộ trình Điều hướng để bắt đầu đồng bộ:"))

        self.path_list = QListWidget()
        for path in paths:
            self.path_list.addItem(path.get("name", "Unnamed Path"))
        layout.addWidget(self.path_list)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def accept(self):
        selected_items = self.path_list.selectedItems()
        if selected_items:
            self.selected_path_name = selected_items[0].text()
        super().accept()

class ComparisonDialog(QDialog):
    """Dialog to display data comparison and get user approval."""
    def __init__(self, comparison_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Xác nhận Thay đổi Dữ liệu")
        self.setMinimumSize(800, 600)
        self.comparison_data = comparison_data
        self.approved_changes = []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Vui lòng xem lại các thay đổi và chọn những thay đổi cần áp dụng:"))

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Trạng thái", "Áp dụng", "Mã định danh", "Dữ liệu Thay đổi"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        self.populate_table()

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def populate_table(self):
        self.table.setRowCount(len(self.comparison_data))
        status_colors = {
            'new': QColor(200, 255, 200),
            'modified': QColor(255, 255, 200),
            'deleted': QColor(255, 200, 200)
        }

        for i, change in enumerate(self.comparison_data):
            status = change['status']
            identifier = change['identifier']
            data = change['data']

            status_item = QTableWidgetItem(status)
            status_item.setBackground(status_colors.get(status, QColor(255, 255, 255)))

            approve_checkbox = QCheckBox()
            approve_checkbox.setChecked(True)

            identifier_item = QTableWidgetItem(str(identifier))

            if status == 'modified':
                change_str = "\n".join([f"{k}: '{v['old']}' -> '{v['new']}'" for k, v in data.items()])
            else:
                change_str = "\n".join([f"{k}: {v}" for k, v in data.items() if not k.endswith('_old') and k not in ['identifier', '_merge']])

            data_item = QTableWidgetItem(change_str)

            self.table.setItem(i, 0, status_item)
            self.table.setCellWidget(i, 1, approve_checkbox)
            self.table.setItem(i, 2, identifier_item)
            self.table.setItem(i, 3, data_item)

        self.table.resizeRowsToContents()

    def accept(self):
        for i in range(self.table.rowCount()):
            if self.table.cellWidget(i, 1).isChecked():
                self.approved_changes.append(self.comparison_data[i])
        super().accept()

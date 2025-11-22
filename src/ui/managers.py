import json
from PyQt6.QtWidgets import (QApplication, QDialog, QListWidget, QVBoxLayout,
                             QLabel, QDialogButtonBox, QWidget, QRubberBand, QHBoxLayout,
                             QLineEdit, QFormLayout, QComboBox, QTableWidget,
                             QTableWidgetItem, QHeaderView, QCheckBox, QPushButton)
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor

from src.config import (PROCESSES_FILE, RULES_FILE, KB_FILE,
                        NAVIGATION_PATHS_FILE, LINES_FILE)
from src.ui.dialogs import PositionSelector

# --- Action/Process Editors ---
class ActionEditorDialog(QDialog):
    def __init__(self, action=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chỉnh sửa Hành động")
        layout = QFormLayout(self)
        self.action_type = QComboBox()
        self.action_type.addItems(["Nhấp vào", "Gõ vào", "Tìm và Ghi nhớ", "Tra cứu Tri thức", "Tính toán Ngày tháng", "Cập nhật Trạng thái"])
        self.target_text = QLineEdit()
        self.value_text = QLineEdit()
        self.param1_label = QLabel("Label 1")
        self.param2_label = QLabel("Label 2")
        self.action_type.currentTextChanged.connect(self.update_ui)
        layout.addRow("Hành động:", self.action_type)
        layout.addRow(self.param1_label, self.target_text)
        layout.addRow(self.param2_label, self.value_text)
        if action:
            self.action_type.setCurrentText(action.get("type", "Nhấp vào"))
            self.target_text.setText(action.get("param1", ""))
            self.value_text.setText(action.get("param2", ""))
        self.update_ui(self.action_type.currentText())
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def update_ui(self, action_type):
        self.param1_label.setVisible(True)
        self.target_text.setVisible(True)
        self.param2_label.setVisible(True)
        self.value_text.setVisible(True)
        if action_type == "Nhấp vào":
            self.param1_label.setText("Tìm văn bản:")
            self.param2_label.setVisible(False)
            self.value_text.setVisible(False)
        elif action_type == "Gõ vào":
            self.param1_label.setText("Tìm văn bản (nhãn):")
            self.param2_label.setText("Văn bản cần gõ:")
        elif action_type == "Tìm và Ghi nhớ":
            self.param1_label.setText("Tìm văn bản (nhãn):")
            self.param2_label.setText("Lưu vào biến:")
        elif action_type == "Tra cứu Tri thức":
            self.param1_label.setText("Tên bảng & cột (Bảng.Cột):")
            self.target_text.setPlaceholderText("e.g., COSCO_Rules.Service")
            self.param2_label.setText("Giá trị tra cứu (biến):")
            self.value_text.setPlaceholderText("e.g., $service_name")
        elif action_type == "Tính toán Ngày tháng":
            self.param1_label.setText("Ngày ETD (biến):")
            self.param2_label.setText("Thời gian CY (biến):")
        elif action_type == "Cập nhật Trạng thái":
            self.param1_label.setText("Biến định danh:")
            self.param2_label.setVisible(False)
            self.value_text.setVisible(False)

    def get_action(self):
        return {"type": self.action_type.currentText(), "param1": self.target_text.text(), "param2": self.value_text.text()}

class ProcessEditorDialog(QDialog):
    def __init__(self, process=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chỉnh sửa Quy trình")
        self.setMinimumSize(600, 400)
        self.process = process if process else {"name": "Quy trình Mới", "mode": "Tự động", "actions": []}

        main_layout = QVBoxLayout(self)

        form_layout = QFormLayout()
        self.process_name = QLineEdit(self.process["name"])
        self.execution_mode = QComboBox()
        self.execution_mode.addItems(["Tự động", "Hỗ trợ"])
        self.execution_mode.setCurrentText(self.process["mode"])
        form_layout.addRow("Tên Quy trình:", self.process_name)
        form_layout.addRow("Chế độ thực thi:", self.execution_mode)
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

        add_btn.clicked.connect(self.add_action)
        edit_btn.clicked.connect(self.edit_action)
        remove_btn.clicked.connect(self.remove_action)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        self.refresh_actions_list()

    def add_action(self):
        dialog = ActionEditorDialog(parent=self)
        if dialog.exec():
            self.process["actions"].append(dialog.get_action())
            self.refresh_actions_list()

    def edit_action(self):
        current_row = self.actions_list.currentRow()
        if current_row < 0:
            return
        action_to_edit = self.process["actions"][current_row]
        dialog = ActionEditorDialog(action=action_to_edit, parent=self)
        if dialog.exec():
            self.process["actions"][current_row] = dialog.get_action()
            self.refresh_actions_list()

    def remove_action(self):
        current_row = self.actions_list.currentRow()
        if current_row < 0:
            return
        del self.process["actions"][current_row]
        self.refresh_actions_list()

    def refresh_actions_list(self):
        self.actions_list.clear()
        for i, action in enumerate(self.process["actions"]):
            self.actions_list.addItem(f"{i+1}. {action['type']}: '{action.get('param1', '')}' | '{action.get('param2', '')}'")

    def get_process(self):
        self.process["name"] = self.process_name.text()
        self.process["mode"] = self.execution_mode.currentText()
        return self.process

class ProcessManagerWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quản lý Quy trình")
        self.setMinimumSize(400, 300)
        self.processes = []

        layout = QVBoxLayout(self)
        self.process_list = QListWidget()
        self.process_list.itemDoubleClicked.connect(self.edit_process)
        layout.addWidget(self.process_list)

        buttons_layout = QHBoxLayout()
        add_btn = QPushButton("Thêm Mới")
        edit_btn = QPushButton("Chỉnh Sửa")
        delete_btn = QPushButton("Xóa")
        buttons_layout.addWidget(add_btn)
        buttons_layout.addWidget(edit_btn)
        buttons_layout.addWidget(delete_btn)
        layout.addLayout(buttons_layout)

        add_btn.clicked.connect(self.add_process)
        edit_btn.clicked.connect(self.edit_process)
        delete_btn.clicked.connect(self.delete_process)

    def exec(self):
        self.load_processes()
        return super().exec()

    def load_processes(self):
        try:
            with open(PROCESSES_FILE, 'r') as f:
                self.processes = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.processes = []
        self.refresh_list()

    def save_processes(self):
        with open(PROCESSES_FILE, 'w') as f:
            json.dump(self.processes, f, indent=4)
        self.parent().on_processes_changed(self.processes)

    def refresh_list(self):
        self.process_list.clear()
        for process in self.processes:
            self.process_list.addItem(f"{process['name']} ({process['mode']})")

    def add_process(self):
        dialog = ProcessEditorDialog(parent=self)
        if dialog.exec():
            self.processes.append(dialog.get_process())
            self.save_processes()
            self.refresh_list()

    def edit_process(self):
        current_row = self.process_list.currentRow()
        if current_row < 0:
            return
        process_to_edit = self.processes[current_row]
        dialog = ProcessEditorDialog(process=process_to_edit, parent=self)
        if dialog.exec():
            self.processes[current_row] = dialog.get_process()
            self.save_processes()
            self.refresh_list()

    def delete_process(self):
        current_row = self.process_list.currentRow()
        if current_row < 0:
            return
        del self.processes[current_row]
        self.save_processes()
        self.refresh_list()

class RuleEditorDialog(QDialog):
    def __init__(self, rule=None, parent=None, processes=[]):
        super().__init__(parent)
        self.setWindowTitle("Chỉnh sửa Quy tắc")
        self.form_layout = QFormLayout(self)
        self.condition_text = QLineEdit()
        self.context_text = QLineEdit()
        self.action_type = QComboBox()
        self.action_type.addItems(["Tạo Ghi chú", "Tự động điền", "Làm nổi bật", "Chạy Quy trình"])
        self.note_content_text = QLineEdit()
        self.autofill_widget = QWidget()
        autofill_layout = QHBoxLayout(self.autofill_widget)
        self.autofill_text = QLineEdit()
        self.select_pos_button = QPushButton("Chọn vị trí")
        self.pos_label = QLabel("Chưa chọn")
        autofill_layout.addWidget(self.autofill_text)
        autofill_layout.addWidget(self.select_pos_button)
        autofill_layout.addWidget(self.pos_label)
        self.process_selector = QComboBox()
        for p in processes:
            self.process_selector.addItem(p["name"])
        self.form_layout.addRow("Nếu thấy văn bản:", self.condition_text)
        self.form_layout.addRow("Và tiêu đề cửa sổ chứa:", self.context_text)
        self.form_layout.addRow("Thì hành động:", self.action_type)
        self.form_layout.addRow("Nội dung Ghi chú:", self.note_content_text)
        self.form_layout.addRow("Nội dung Tự động điền:", self.autofill_widget)
        self.form_layout.addRow("Chọn Quy trình:", self.process_selector)
        self.action_type.currentIndexChanged.connect(self.update_action_widgets)
        self.select_pos_button.clicked.connect(self.select_position)
        self.autofill_pos = None
        if rule:
            self.condition_text.setText(rule.get("condition", ""))
            self.context_text.setText(rule.get("context", ""))
            action_type = rule.get("action_type", "Tạo Ghi chú")
            self.action_type.setCurrentText(action_type)
            if action_type == "Tạo Ghi chú":
                self.note_content_text.setText(rule.get("action_data", ""))
            elif action_type == "Tự động điền":
                self.autofill_text.setText(rule.get("action_data", {}).get("text", ""))
                self.autofill_pos = rule.get("action_data", {}).get("position")
                if self.autofill_pos:
                    self.pos_label.setText(f"({self.autofill_pos[0]}, {self.autofill_pos[1]})")
            elif action_type == "Chạy Quy trình":
                self.process_selector.setCurrentText(rule.get("action_data", ""))
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.form_layout.addWidget(button_box)
        self.update_action_widgets()

    def update_action_widgets(self):
        current_action = self.action_type.currentText()
        self.note_content_text.setVisible(current_action == "Tạo Ghi chú")
        self.autofill_widget.setVisible(current_action == "Tự động điền")
        self.process_selector.setVisible(current_action == "Chạy Quy trình")

    def get_rule(self):
        action_type = self.action_type.currentText()
        action_data = None
        if action_type == "Tạo Ghi chú":
            action_data = self.note_content_text.text()
        elif action_type == "Tự động điền":
            action_data = {"text": self.autofill_text.text(), "position": self.autofill_pos}
        elif action_type == "Chạy Quy trình":
            action_data = self.process_selector.currentText()
        return {"condition": self.condition_text.text(), "context": self.context_text.text(), "action_type": action_type, "action_data": action_data}

    def select_position(self):
        self.parent().hide()
        self.pos_selector = PositionSelector()
        self.pos_selector.position_selected.connect(self.on_position_selected)
        self.pos_selector.show()

    def on_position_selected(self, x, y):
        self.autofill_pos = (x, y)
        self.pos_label.setText(f"({x}, {y})")
        self.parent().show()

class RuleManagerWindow(QDialog):
    def __init__(self, parent=None, processes=[]):
        super().__init__(parent)
        self.setWindowTitle("Quản lý Quy tắc")
        self.setMinimumSize(500, 350)
        self.rules = []
        self.processes = processes
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

    def exec(self):
        self.load_rules()
        return super().exec()

    def refresh_list(self):
        self.rule_list.clear()
        for rule in self.rules:
            context_str = f" trong \"{rule['context']}\"" if rule.get('context') else ""
            display_text = f"Nếu thấy \"{rule['condition']}\"{context_str} -> "
            action_type = rule['action_type']
            if action_type == "Tạo Ghi chú":
                display_text += f"Tạo ghi chú \"{rule['action_data']}\""
            elif action_type == "Làm nổi bật":
                display_text += "Làm nổi bật văn bản"
            elif action_type == "Chạy Quy trình":
                display_text += f"Chạy quy trình \"{rule['action_data']}\""
            elif action_type == "Tự động điền":
                pos = rule.get('action_data', {}).get('position')
                display_text += f"Tự động điền tại {pos}"
            self.rule_list.addItem(display_text)

    def add_rule(self):
        dialog = RuleEditorDialog(parent=self, processes=self.processes)
        if dialog.exec():
            new_rule = dialog.get_rule()
            if new_rule['condition']:
                self.rules.append(new_rule)
                self.save_rules()
                self.refresh_list()

    def edit_rule(self):
        current_row = self.rule_list.currentRow()
        if current_row < 0:
            return
        rule_to_edit = self.rules[current_row]
        dialog = RuleEditorDialog(rule=rule_to_edit, parent=self, processes=self.processes)
        if dialog.exec():
            updated_rule = dialog.get_rule()
            if updated_rule['condition']:
                self.rules[current_row] = updated_rule
                self.save_rules()
                self.refresh_list()

    def load_rules(self):
        try:
            with open(RULES_FILE, 'r') as f:
                self.rules = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.rules = []
        self.refresh_list()

    def save_rules(self):
        with open(RULES_FILE, 'w') as f:
            json.dump(self.rules, f, indent=4)
        self.parent().on_rules_changed(self.rules)

    def delete_rule(self):
        current_row = self.rule_list.currentRow()
        if current_row < 0:
            return
        del self.rules[current_row]
        self.save_rules()
        self.refresh_list()

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

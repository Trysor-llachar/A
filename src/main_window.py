import sys
import json
import time
from datetime import datetime
import pyperclip
import pandas as pd
from io import StringIO
import pytesseract
import pyautogui
from mss import mss
import cv2
import numpy as np

from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QHBoxLayout, QWidget, QMessageBox
from PyQt6.QtCore import Qt, QRect

from src.ui_components import (NoteWindow, ScreenSelector, ProcessManagerWindow,
                               RuleManagerWindow, KnowledgeBaseManager, StatusOverlay,
                               SuggestionDialog, HighlightWindow, LineManagerWindow,
                               NavigationPathManagerWindow, PathSelectionDialog)
from src.automation import AutomationEngine, ProcessRunner, ComprehensiveScanner, PathRunner
from src.data_management import StateManager, LineManager, DatabaseManager
from src.config import NOTES_FILE, BACKUP_FILE

class FloatingMenu(QMainWindow):
    def __init__(self):
        super().__init__()
        self.notes = []
        self.rules = []
        self.processes = []
        self.kb = {}
        self.recently_triggered = {}
        self.highlight_windows = []
        self.status_overlays = []

        self.setWindowTitle("Floating Menu")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)

        self.extract_button = QPushButton("Trích xuất văn bản")
        self.create_note_button = QPushButton("Tạo Ghi chú")
        self.rules_button = QPushButton("Quản lý Quy tắc")
        self.processes_button = QPushButton("Quản lý Quy trình")
        self.kb_button = QPushButton("Kho Tri thức")
        self.lines_button = QPushButton("Cấu hình Lines")
        self.nav_path_button = QPushButton("Lộ trình Điều hướng")
        self.monitor_button = QPushButton("Giám sát")
        self.monitor_button.setCheckable(True)
        self.start_sync_button = QPushButton("Bắt đầu Đồng bộ")


        layout.addWidget(self.extract_button)
        layout.addWidget(self.create_note_button)
        layout.addWidget(self.rules_button)
        layout.addWidget(self.processes_button)
        layout.addWidget(self.kb_button)
        layout.addWidget(self.lines_button)
        layout.addWidget(self.nav_path_button)
        layout.addWidget(self.monitor_button)
        layout.addWidget(self.start_sync_button)

        self.setStyleSheet("""
            QMainWindow { background-color: rgba(30, 30, 30, 200); border-radius: 10px; }
            QPushButton { background-color: #555; color: white; border: 1px solid #777; padding: 8px; border-radius: 5px; }
            QPushButton:hover { background-color: #777; }
            QPushButton:checked { background-color: #0078D7; border-color: #005A9E; }
        """)

        self.process_manager = ProcessManagerWindow(self)
        self.rule_manager = RuleManagerWindow(self, processes=self.process_manager.processes)
        self.kb_manager = KnowledgeBaseManager(self)
        self.state_manager = StateManager()
        self.line_manager = LineManager()
        self.db_manager = DatabaseManager()
        self.line_manager_window = LineManagerWindow(self)
        self.nav_path_manager = NavigationPathManagerWindow(self)


        # Special note for new identifiers
        # self.new_identifiers_note = NoteWindow(self, content="Mã Mới Phát Hiện:\n", geometry=(10, 500, 300, 200)) # Temporarily disabled
        # self.new_identifiers_note.show() # Temporarily disabled


        self.extract_button.clicked.connect(self.start_selection)
        self.create_note_button.clicked.connect(self.create_note)
        self.rules_button.clicked.connect(self.rule_manager.exec)
        self.processes_button.clicked.connect(self.process_manager.exec)
        self.kb_button.clicked.connect(self.kb_manager.exec)
        self.lines_button.clicked.connect(self.line_manager_window.exec)
        self.nav_path_button.clicked.connect(self.nav_path_manager.exec)
        self.monitor_button.clicked.connect(self.toggle_monitoring)
        self.start_sync_button.clicked.connect(self.start_active_sync)

        self._drag_start_position = None
        self.selector = None

        self.load_notes()
        # Initialize with empty lists/dicts first, they will be loaded when dialogs are opened
        self.on_rules_changed([])
        self.on_processes_changed([])
        self.on_kb_changed({})

        self.automation_engine = AutomationEngine(self.line_manager, self)
        self.automation_engine.scan_complete.connect(self.process_screen_data)
        self.automation_engine.identifier_found.connect(self.handle_identifier)
        self.automation_engine.start()

        self.process_runner = None

    def toggle_monitoring(self, checked):
        self.automation_engine.monitoring_mode = checked
        self.monitor_button.setText("Dừng Giám sát" if checked else "Bắt đầu Giám sát")

    def handle_identifier(self, identifier, line_name, rect):
        pass
        # if not self.db_manager.identifier_exists(identifier):
        #     print(f"New identifier found: {identifier} for line {line_name}")
        #     self.db_manager.add_record(identifier, data={"line": line_name, "status": "new"})

        #     current_text = self.new_identifiers_note.text_edit.toPlainText()
        #     self.new_identifiers_note.text_edit.setText(current_text + f"- {identifier} ({line_name})\n")

        # The new logic for "entered" / "not entered" status will be handled in a later phase.
        # For now, we disable the old status overlay.
        # timestamp = self.state_manager.check_status(identifier)
        # status_text = f"Đã lên tàu lúc: {timestamp}" if timestamp else "Chưa lên tàu"
        # overlay_geom = QRect(rect.x(), rect.y() - 35, 150, 30)
        # overlay = StatusOverlay(identifier, status_text, overlay_geom)
        # overlay.show()
        # self.status_overlays.append(overlay)
        # self.status_overlays = [o for o in self.status_overlays if o.isVisible()]

    def analyze_and_suggest(self, text, ocr_df):
        pyperclip.copy(text)
        suggestions = [f"Chạy quy trình: {p['name']}" for p in self.processes if p['name'].lower() in text.lower()]

        dialog = SuggestionDialog(suggestions, self)
        if dialog.exec():
            action = dialog.selected_action
            if action and action.startswith("Chạy quy trình:"):
                process_name = action.replace("Chạy quy trình: ", "")
                process_to_run = next((p for p in self.processes if p['name'] == process_name), None)
                if process_to_run:
                    self.process_runner = ProcessRunner(process_to_run, ocr_df, self.kb, self.state_manager, self)
                    self.process_runner.log_message.connect(print)
                    self.process_runner.request_highlight.connect(self.show_highlight)
                    self.process_runner.request_suggestion.connect(self.show_suggestion)
                    self.process_runner.request_correction.connect(self.handle_correction_request)
                    self.process_runner.start()
            elif action == "Tạo Quy trình mới...":
                self.process_manager.exec()
        self.show()

    def find_text_location(self, df, text_to_find):
        words = text_to_find.split()
        if not words: return None
        df['text_str'] = df['text'].astype(str)
        for i in range(len(df) - len(words) + 1):
            chunk = df.iloc[i:i + len(words)]
            sequence = " ".join(chunk['text_str'])
            if sequence == text_to_find:
                x_min = chunk['left'].min()
                y_min = chunk['top'].min()
                x_max = (chunk['left'] + chunk['width']).max()
                y_max = (chunk['top'] + chunk['height']).max()
                return QRect(int(x_min), int(y_min), int(x_max - x_min), int(y_max - y_min))
        return None

    def process_screen_data(self, ocr_df, window_title):
        if self.process_runner and self.process_runner.isRunning():
            return
        current_time = time.time()
        full_text = " ".join(ocr_df['text'].astype(str))
        for rule in self.rules:
            context_condition_met = (not rule.get('context')) or (rule.get('context', '') in window_title)
            if not context_condition_met:
                continue
            text_condition = rule['condition']
            if text_condition in full_text:
                trigger_key = f"{text_condition}|{rule.get('context', '')}"
                last_triggered = self.recently_triggered.get(trigger_key, 0)
                if current_time - last_triggered > 60:
                    self.execute_action(rule, ocr_df)
                    self.recently_triggered[trigger_key] = current_time
                    break

    def execute_action(self, rule, ocr_df):
        action_type = rule['action_type']
        if action_type == "Chạy Quy trình":
            process_name = rule['action_data']
            process_to_run = next((p for p in self.processes if p['name'] == process_name), None)
            if process_to_run:
                self.process_runner = ProcessRunner(process_to_run, ocr_df, self.kb, self.state_manager, self)
                self.process_runner.log_message.connect(print)
                self.process_runner.request_highlight.connect(self.show_highlight)
                self.process_runner.request_suggestion.connect(self.show_suggestion)
                self.process_runner.request_correction.connect(self.handle_correction_request)
                self.process_runner.start()
        elif action_type == "Tạo Ghi chú":
            self.create_note(content=rule['action_data'])
        elif action_type == "Tự động điền":
            pos = rule['action_data'].get("position")
            text_to_type = rule['action_data'].get("text", "")
            if pos:
                pyautogui.click(x=pos[0], y=pos[1])
                pyautogui.write(text_to_type, interval=0.05)
        elif action_type == "Làm nổi bật":
            rect = self.find_text_location(ocr_df, rule['condition'])
            if rect:
                self.show_highlight(rect)

    def handle_correction_request(self, failed_action, process_name):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Quy trình Tạm dừng")
        msg_box.setText(f"Không thể tìm thấy văn bản: '{failed_action['param1']}'.\nBạn có muốn chỉ lại không?")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
        if msg_box.exec() == QMessageBox.StandardButton.Yes:
            self.start_selection(callback=lambda rect: self.process_correction(rect, failed_action, process_name))
        else:
            self.process_runner.resume_with_correction(None)

    def process_correction(self, rect, failed_action, process_name):
        new_text = self.capture_and_ocr(rect, copy_to_clipboard=False)
        if not new_text:
            self.process_runner.resume_with_correction(None)
            return
        confirm_msg = QMessageBox(self)
        confirm_msg.setWindowTitle("Xác nhận Học")
        confirm_msg.setText(f"Bạn có muốn cập nhật hành động này để tìm văn bản mới '{new_text}' không?")
        confirm_msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm_msg.exec() == QMessageBox.StandardButton.Yes:
            corrected_action = failed_action.copy()
            corrected_action['param1'] = new_text
            for p in self.processes:
                if p['name'] == process_name:
                    for i, act in enumerate(p['actions']):
                        if act['param1'] == failed_action['param1']:
                            p['actions'][i] = corrected_action
                            break
                    break
            self.process_manager.save_processes()
            self.process_runner.resume_with_correction(corrected_action)
        else:
            self.process_runner.resume_with_correction(None)

    def show_highlight(self, rect):
        hw = HighlightWindow(rect)
        hw.show()
        self.highlight_windows.append(hw)

    def show_suggestion(self, text, pos):
        self.create_note(content=text, geometry=(pos.x(), pos.y(), 250, 80))

    def on_rules_changed(self, new_rules):
        self.rules = new_rules

    def on_processes_changed(self, new_processes):
        self.processes = new_processes
        self.rule_manager.processes = new_processes

    def on_kb_changed(self, new_kb):
        self.kb = new_kb

    def backup_note(self, content):
        try:
            with open(BACKUP_FILE, 'r') as f:
                backup_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            backup_data = {}
        today_str = datetime.now().strftime("%Y-%m-%d")
        now_str = datetime.now().strftime("%H:%M:%S")
        if today_str not in backup_data:
            backup_data[today_str] = []
        backup_data[today_str].append({"time": now_str, "content": content})
        with open(BACKUP_FILE, 'w') as f:
            json.dump(backup_data, f, indent=4)

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
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def closeEvent(self, event):
        self.automation_engine.stop()
        self.save_notes()
        super().closeEvent(event)

    def start_selection(self, callback=None):
        if not callback:
            callback = lambda rect: self.analyze_and_suggest_wrapper(rect)
        self.hide()
        self.selector = ScreenSelector(self, callback=callback)
        self.selector.show()

    def analyze_and_suggest_wrapper(self, rect):
        with mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            img = np.array(sct_img)
            full_screen_df = pd.read_csv(StringIO(pytesseract.image_to_data(img)), sep='\t')
        text_in_rect = self.capture_and_ocr(rect, copy_to_clipboard=False)
        self.analyze_and_suggest(text_in_rect, full_screen_df)

    def capture_and_ocr(self, rect, copy_to_clipboard=True):
        try:
            with mss() as sct:
                monitor = {"top": rect.y(), "left": rect.x(), "width": rect.width(), "height": rect.height()}
                sct_img = sct.grab(monitor)
                img = np.array(sct_img)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                text = pytesseract.image_to_string(img).strip()
                if copy_to_clipboard:
                    pyperclip.copy(text)
                return text
        except Exception as e:
            print(f"An error occurred: {e}")
            return ""
        finally:
            if not self.process_runner or not self.process_runner.isRunning():
                self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_position = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_start_position:
            self.move(event.globalPosition().toPoint() - self._drag_start_position)

    def mouseReleaseEvent(self, event):
        self._drag_start_position = None

    def start_active_sync(self):
        path_loader = NavigationPathManagerWindow()
        path_loader.load_paths()

        if not path_loader.paths:
            QMessageBox.information(self, "Không có Lộ trình", "Chưa có Lộ trình Điều hướng nào được định nghĩa.")
            return

        dialog = PathSelectionDialog(path_loader.paths, self)
        if dialog.exec():
            selected_path_name = dialog.selected_path_name
            if selected_path_name:
                self.execute_navigation_path(selected_path_name, path_loader.paths)

    def execute_navigation_path(self, path_name, available_paths):
        # Find the full path object from the name
        path_to_run = next((p for p in available_paths if p['name'] == path_name), None)

        if not path_to_run:
            QMessageBox.warning(self, "Lỗi", f"Không tìm thấy chi tiết cho lộ trình '{path_name}'.")
            return

        self.hide()
        self.path_runner = PathRunner(path_to_run, self)
        self.path_runner.log_message.connect(print) # For debugging
        self.path_runner.path_complete.connect(self.prompt_for_scan_area)
        self.path_runner.start()

    def prompt_for_scan_area(self):
        QMessageBox.information(self, "Điều hướng Hoàn tất", "Lộ trình đã được thực thi.\nVui lòng chọn khu vực bảng để bắt đầu quét.")
        self.selector = ScreenSelector(self, callback=self.start_comprehensive_scan)
        self.selector.show()

    def start_comprehensive_scan(self, selected_rect):
        self.show()
        QMessageBox.information(self, "Bắt đầu Quét", "Đã chọn khu vực. Bắt đầu Quét Toàn diện.")

        self.scanner = ComprehensiveScanner(selected_rect, self)
        self.scanner.log_message.connect(print) # For debugging
        self.scanner.scan_complete.connect(self.handle_scan_completion)
        self.scanner.start()

    def handle_scan_completion(self, scanned_df):
        self.show()
        print("Scan complete. Received DataFrame with shape:", scanned_df.shape)

        # Basic data cleaning and structuring from raw OCR output.
        # This is a placeholder for a more robust table extraction logic.
        # We'll try to find 'identifier' and 'status' columns based on text.
        # This logic is highly dependent on the scanned table's format.
        try:
            structured_df = self.structure_scanned_data(scanned_df)
            print("Structured DataFrame columns:", structured_df.columns)
            # If scan is empty but DB is not, create an empty DF with 'identifier' to allow comparison
            if structured_df.empty and self.db_manager.database:
                 structured_df = pd.DataFrame(columns=['identifier'])

            if 'identifier' not in structured_df.columns and self.db_manager.database:
                 QMessageBox.critical(self, "Lỗi Xử lý", "Không thể tự động xác định cột 'identifier' từ dữ liệu đã quét.")
                 return
        except Exception as e:
            QMessageBox.critical(self, "Lỗi Xử lý", f"Đã xảy ra lỗi khi xử lý dữ liệu OCR: {e}")
            return

        # Load real data from the database
        self.db_manager.load_database()
        if not self.db_manager.database:
            db_df = pd.DataFrame(columns=structured_df.columns)
        else:
            db_df = pd.DataFrame(self.db_manager.database)
            # Ensure columns match for comparison
            db_df = db_df[db_df.columns.intersection(structured_df.columns)]


        comparison_results = self._compare_dataframes(structured_df, db_df, on='identifier')

        if not comparison_results:
            QMessageBox.information(self, "Không có thay đổi", "Không tìm thấy sự khác biệt nào giữa dữ liệu được quét và cơ sở dữ liệu.")
            return

        dialog = ComparisonDialog(comparison_results, self)
        if dialog.exec():
            approved_changes = dialog.approved_changes
            if approved_changes:
                self._apply_approved_changes(approved_changes)
            else:
                print("No changes were approved.")

    def _apply_approved_changes(self, changes):
        """Applies the user-approved changes to the database."""
        self.db_manager.load_database() # Ensure we have the latest data

        for change in changes:
            status = change['status']
            identifier = change['identifier']
            data = change['data']

            if status == 'new':
                # Reconstruct the data dictionary from the change log
                new_data = {k: v for k, v in data.items() if not k.endswith('_old') and k not in ['identifier', '_merge']}
                self.db_manager.add_record(identifier, new_data)
                print(f"Added new record: {identifier}")

            elif status == 'modified':
                # Extract only the new values for the update
                update_data = {k: v['new'] for k, v in data.items()}
                self.db_manager.update_record(identifier, update_data)
                print(f"Updated record: {identifier}")

            elif status == 'deleted':
                self.db_manager.delete_record(identifier)
                print(f"Deleted record: {identifier}")

        QMessageBox.information(self, "Cập nhật Thành công", "Cơ sở dữ liệu đã được cập nhật với các thay đổi đã được phê duyệt.")

    def structure_scanned_data(self, df):
        """A simple heuristic to structure raw OCR data into a table-like DataFrame."""
        if df.empty:
            return pd.DataFrame()

        df = df.sort_values(by=['top', 'left']).reset_index()

        # Group words into lines based on vertical position
        lines = df.groupby(df['top'].diff().gt(15).cumsum()) # Increased tolerance for line breaks

        if not lines:
            return pd.DataFrame()

        # A simple assumption: The line with the most words is likely the header.
        header_line = max(lines, key=lambda item: len(item[1]))[1]

        headers = {}
        for _, row in header_line.iterrows():
            col_name = str(row['text']).lower()
            # Basic normalization for identifier column
            if 'id' in col_name or 'code' in col_name or 'mã' in col_name:
                col_name = 'identifier'
            headers[row['left']] = col_name

        structured_data = []
        for _, line_df in lines:
            # Skip the header line itself
            if line_df.index.equals(header_line.index):
                continue

            row_data = {}
            for _, word_row in line_df.iterrows():
                # Find the header with the smallest horizontal distance
                closest_header_pos = min(headers.keys(), key=lambda x: abs(x - word_row['left']))
                col_name = headers[closest_header_pos]

                if col_name in row_data:
                    row_data[col_name] += " " + str(word_row['text'])
                else:
                    row_data[col_name] = str(word_row['text'])

            # Only add rows that have some data
            if any(row_data.values()):
                structured_data.append(row_data)

        return pd.DataFrame(structured_data)

    def _compare_dataframes(self, new_df, old_df, on='identifier'):
        """Compares two dataframes and identifies new, modified, and deleted rows."""
        comparison = []

        merged_df = pd.merge(new_df, old_df, on=on, how='outer', indicator=True, suffixes=('_new', '_old'))

        # New rows
        new_rows = merged_df[merged_df['_merge'] == 'left_only']
        for _, row in new_rows.iterrows():
            comparison.append({
                'status': 'new',
                'identifier': row[on],
                'data': row.to_dict()
            })

        # Deleted rows
        deleted_rows = merged_df[merged_df['_merge'] == 'right_only']
        for _, row in deleted_rows.iterrows():
            comparison.append({
                'status': 'deleted',
                'identifier': row[on],
                'data': row.to_dict()
            })

        # Potentially modified rows
        both_rows = merged_df[merged_df['_merge'] == 'both']
        for _, row in both_rows.iterrows():
            is_modified = False
            changes = {}
            for col in new_df.columns:
                if col == on: continue
                old_col, new_col = f"{col}_old", f"{col}_new"
                if row[old_col] != row[new_col]:
                    is_modified = True
                    changes[col] = {'old': row[old_col], 'new': row[new_col]}

            if is_modified:
                comparison.append({
                    'status': 'modified',
                    'identifier': row[on],
                    'data': changes
                })

        return comparison

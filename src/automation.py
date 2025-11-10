import time
import re
import subprocess
import sys
from io import StringIO
import pandas as pd
import pytesseract
import pyautogui
# import pygetwindow as gw # Conditional import below
from mss import mss
import numpy as np
import cv2
from PyQt6.QtCore import QThread, pyqtSignal, QRect, QEventLoop, QPoint
from dateutil.parser import parse
from datetime import timedelta


class AutomationEngine(QThread):
    scan_complete = pyqtSignal(object, str)
    identifier_found = pyqtSignal(str, str, QRect) # identifier, line_name, rect

    def __init__(self, line_manager, parent=None):
        super().__init__(parent)
        self.running = True
        self.monitoring_mode = False
        self.line_manager = line_manager

    def get_active_window_title(self):
        try:
            if sys.platform == "win32":
                import pygetwindow as gw
                active_window = gw.getActiveWindow()
                return active_window.title if active_window else ""
            elif sys.platform == "linux":
                command = "xdotool getactivewindow getwindowname"
                result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, text=True)
                return result.stdout.strip()
            else:
                return "" # Unsupported OS
        except Exception:
            return ""

    def run(self):
        while self.running:
            try:
                window_title = self.get_active_window_title()
                with mss() as sct:
                    monitor = sct.monitors[1]
                    sct_img = sct.grab(monitor)
                    img = np.array(sct_img)
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    ocr_data_str = pytesseract.image_to_data(img, timeout=4)
                    df = pd.read_csv(StringIO(ocr_data_str), sep='\t')
                    df.dropna(subset=['conf'], inplace=True)
                    df = df[df.conf > 30]
                    self.scan_complete.emit(df, window_title)
                    if self.monitoring_mode:
                        self.find_and_emit_identifiers(df)
            except Exception as e:
                print(f"Error in automation engine: {e}")
            time.sleep(5)

    def find_and_emit_identifiers(self, df):
        lines = self.line_manager.lines
        for line_name, line_data in lines.items():
            for pattern in line_data.get("patterns", []):
                try:
                    regex = re.compile(pattern["regex"])
                    for index, row in df.iterrows():
                        text = str(row['text']).strip()
                        if regex.match(text):
                            rect = QRect(int(row['left']), int(row['top']), int(row['width']), int(row['height']))
                            self.identifier_found.emit(text, line_name, rect)
                except re.error as e:
                    print(f"Invalid regex for {line_name} - {pattern['name']}: {e}")

    def stop(self):
        self.running = False
        self.wait()


class PathRunner(QThread):
    path_complete = pyqtSignal()
    log_message = pyqtSignal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        self.log_message.emit(f"Bắt đầu thực thi Lộ trình: {self.path.get('name', '')}")

        for i, action in enumerate(self.path.get('actions', [])):
            self.log_message.emit(f"Bước {i + 1}: {action['type']} -> '{action['value']}'")
            action_type = action.get('type')
            action_value = action.get('value')

            if not action_value:
                self.log_message.emit("Lỗi: Giá trị hành động bị thiếu. Bỏ qua.")
                continue

            success = False
            if action_type == "Nhấp vào văn bản":
                success = self.click_text(action_value)
            elif action_type == "Nhấp vào hình ảnh":
                success = self.click_image(action_value)

            if not success:
                self.log_message.emit(f"Không thể thực thi bước {i + 1}. Dừng lộ trình.")
                break

            time.sleep(1.5) # Wait for UI to update

        self.log_message.emit("Thực thi Lộ trình hoàn tất.")
        self.path_complete.emit()

    def find_text_location(self, text_to_find):
        # This requires a full screen scan, similar to AutomationEngine
        # For simplicity, we'll re-scan here. In a future refactor, this could be shared.
        with mss() as sct:
            sct_img = sct.grab(sct.monitors[1])
            img = np.array(sct_img)
            ocr_df = pd.read_csv(StringIO(pytesseract.image_to_data(img)), sep='\t')

        words = text_to_find.split()
        if not words: return None

        ocr_df['text_str'] = ocr_df['text'].astype(str)
        for i in range(len(ocr_df) - len(words) + 1):
            chunk = ocr_df.iloc[i:i + len(words)]
            sequence = " ".join(chunk['text_str'])
            if sequence == text_to_find:
                x_min = chunk['left'].min()
                y_min = chunk['top'].min()
                x_max = (chunk['left'] + chunk['width']).max()
                y_max = (chunk['top'] + chunk['height']).max()
                return QRect(int(x_min), int(y_min), int(x_max - x_min), int(y_max - y_min))
        return None

    def click_text(self, text_to_find):
        rect = self.find_text_location(text_to_find)
        if rect:
            self.log_message.emit(f"Đã tìm thấy văn bản '{text_to_find}' tại {rect}. Đang nhấp...")
            pyautogui.click(rect.center().x(), rect.center().y())
            return True
        self.log_message.emit(f"Không tìm thấy văn bản '{text_to_find}' trên màn hình.")
        return False

    def click_image(self, image_path):
        try:
            # The confidence might need adjustment depending on the environment
            location = pyautogui.locateCenterOnScreen(image_path, confidence=0.8)
            if location:
                self.log_message.emit(f"Đã tìm thấy hình ảnh '{image_path}' tại {location}. Đang nhấp...")
                pyautogui.click(location)
                return True
            else:
                self.log_message.emit(f"Không tìm thấy hình ảnh '{image_path}' trên màn hình.")
                return False
        except Exception as e:
            # pyautogui.locateCenterOnScreen raises an exception if the file is not found
            self.log_message.emit(f"Lỗi khi tìm hình ảnh '{image_path}': {e}")
            return False


class ProcessRunner(QThread):
    log_message = pyqtSignal(str)
    request_highlight = pyqtSignal(QRect)
    request_suggestion = pyqtSignal(str, QPoint)
    request_correction = pyqtSignal(dict, str)

    def __init__(self, process, ocr_df, kb, state_manager, parent=None):
        super().__init__(parent)
        self.process = process
        self.ocr_df = ocr_df
        self.kb = kb
        self.state_manager = state_manager
        self.variables = {}
        self.continue_event = QEventLoop()
        self.corrected_action = None

    def find_text_location(self, text_to_find):
        words = text_to_find.split()
        if not words:
            return None
        df = self.ocr_df
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

    def find_text_to_right_of(self, rect):
        df = self.ocr_df
        same_line_df = df[(df['top'] >= rect.top() - 10) & (df['top'] <= rect.bottom() + 10) & (df['left'] > rect.right())]
        if same_line_df.empty:
            return ""
        return " ".join(same_line_df.sort_values('left')['text'].astype(str))

    def resume_with_correction(self, new_action):
        self.corrected_action = new_action
        self.continue_event.quit()

    def run(self):
        self.log_message.emit(f"Bắt đầu quy trình '{self.process['name']}' ({self.process['mode']})")
        for i, action in enumerate(self.process['actions']):
            param1 = self.variables.get(action.get('param1', ''), action.get('param1', ''))
            param2 = self.variables.get(action.get('param2', ''), action.get('param2', ''))
            self.log_message.emit(f"Bước {i + 1}: {action['type']} '{param1}'")
            target_rect = None
            if action['type'] in ["Nhấp vào", "Gõ vào", "Tìm và Ghi nhớ"]:
                target_rect = self.find_text_location(param1)
            if not target_rect and action['type'] in ["Nhấp vào", "Gõ vào", "Tìm và Ghi nhớ"]:
                self.log_message.emit(f"Lỗi: Không tìm thấy '{param1}' trên màn hình.")
                self.request_correction.emit(action, self.process['name'])
                self.continue_event.exec()
                if self.corrected_action:
                    self.log_message.emit("Đã nhận được chỉnh sửa. Thử lại...")
                    action = self.corrected_action
                    self.process['actions'][i] = action
                    param1 = action['param1']
                    target_rect = self.find_text_location(param1)
                    if not target_rect:
                        self.log_message.emit("Vẫn không tìm thấy mục tiêu sau khi sửa. Dừng quy trình.")
                        break
                else:
                    self.log_message.emit("Người dùng đã hủy. Dừng quy trình.")
                    break
            if self.process['mode'] == "Tự động":
                self.execute_action_auto(action, target_rect, param1, param2)
            else:
                self.execute_action_assist(action, target_rect)
                break
            time.sleep(1)
        self.log_message.emit("Hoàn thành quy trình.")

    def execute_action_auto(self, action, rect, param1, param2):
        action_type = action['type']
        if action_type == "Nhấp vào":
            pyautogui.click(rect.center().x(), rect.center().y())
        elif action_type == "Gõ vào":
            pyautogui.click(rect.center().x() + rect.width(), rect.center().y())
            pyautogui.write(param2, interval=0.05)
        elif action_type == "Tìm và Ghi nhớ":
            found_text = self.find_text_to_right_of(rect)
            self.variables[param2] = found_text.split()[0] if found_text else ""
            self.log_message.emit(f"Đã ghi nhớ '{self.variables[param2]}' vào biến '{param2}'")
        elif action_type == "Tra cứu Tri thức":
            table_name, column_name = param1.split('.')
            lookup_value = param2
            result_col_name = "CY Time"
            table = self.kb.get(table_name)
            if table:
                lookup_col_index = table['columns'].index(column_name)
                result_col_index = table['columns'].index(result_col_name)
                for row in table['data']:
                    if str(row[lookup_col_index]) == lookup_value:
                        self.variables['$cy_time'] = row[result_col_index]
                        self.log_message.emit(f"Tra cứu thành công: found '{row[result_col_index]}' in '{table_name}'")
                        return
            self.log_message.emit(f"Lỗi: Không tìm thấy kết quả cho '{lookup_value}' trong '{table_name}'")
        elif action_type == "Tính toán Ngày tháng":
            etd_str = param1
            cy_time_str = param2
            try:
                etd_date = parse(etd_str)
                cy_day_str, cy_time_part, cy_am_pm = cy_time_str.split(' ')
                cy_weekday = {"MONDAY": 0, "TUESDAY": 1, "WEDNESDAY": 2, "THURSDAY": 3, "FRIDAY": 4, "SATURDAY": 5, "SUNDAY": 6}[cy_day_str.upper()]
                final_cy_date = etd_date + timedelta(days=cy_weekday - etd_date.weekday())
                if final_cy_date > etd_date:
                    final_cy_date -= timedelta(days=7)
                final_cy_datetime_str = f"{final_cy_date.strftime('%d/%m/%Y')} {cy_time_part} {cy_am_pm}"
                self.variables['$final_cy_date'] = final_cy_datetime_str
                self.log_message.emit(f"Đã tính toán CY: {final_cy_datetime_str}")
            except Exception as e:
                self.log_message.emit(f"Lỗi tính toán ngày: {e}")
        elif action_type == "Cập nhật Trạng thái":
            identifier_to_update = self.variables.get(param1)
            if identifier_to_update:
                self.state_manager.update_status(identifier_to_update)
                self.log_message.emit(f"Đã cập nhật trạng thái cho '{identifier_to_update}'")
            else:
                self.log_message.emit(f"Lỗi: Không tìm thấy biến '{param1}' để cập nhật trạng thái.")

    def execute_action_assist(self, action, rect):
        self.request_highlight.emit(rect)
        suggestion_text = ""
        self.request_suggestion.emit(suggestion_text, rect.topRight())


class ComprehensiveScanner(QThread):
    scan_complete = pyqtSignal(pd.DataFrame)
    log_message = pyqtSignal(str)

    def __init__(self, initial_scan_area, parent=None):
        super().__init__(parent)
        self.scan_area = initial_scan_area
        self.running = False
        self.full_df = pd.DataFrame()

    def run(self):
        self.running = True
        self.log_message.emit("Bắt đầu Quét Toàn diện...")

        # --- Vertical Scrolling ---
        self.log_message.emit("Bắt đầu cuộn dọc...")
        previous_img_v = None
        all_vertical_dfs = []
        while self.running:
            img = self.capture_screen_area(self.scan_area)
            if previous_img_v is not None and self.is_image_same(previous_img_v, img):
                self.log_message.emit("Phát hiện cuối khu vực cuộn dọc.")
                break

            ocr_df = self.perform_ocr(img)
            all_vertical_dfs.append(ocr_df)

            previous_img_v = img
            pyautogui.scroll(-500) # Scroll down a smaller amount
            time.sleep(1)

        # Combine vertical scans
        if all_vertical_dfs:
            self.full_df = pd.concat(all_vertical_dfs).drop_duplicates(subset=['page_num', 'block_num', 'par_num', 'line_num', 'word_num', 'text'])

        # --- Horizontal Scrolling ---
        self.log_message.emit("Bắt đầu cuộn ngang...")
        # Reset vertical scroll to the top before starting horizontal scan
        pyautogui.scroll(10000) # Scroll a large amount up
        time.sleep(1)

        previous_img_h = None
        all_horizontal_dfs = []
        while self.running:
            img = self.capture_screen_area(self.scan_area)
            if previous_img_h is not None and self.is_image_same(previous_img_h, img):
                self.log_message.emit("Phát hiện cuối khu vực cuộn ngang.")
                break

            ocr_df = self.perform_ocr(img)
            all_horizontal_dfs.append(ocr_df)

            previous_img_h = img
            pyautogui.hscroll(-500) # Scroll right
            time.sleep(1)

        # Merge horizontal data with vertical data (this is a complex problem)
        # For now, we will just concatenate and drop duplicates.
        # A more sophisticated approach would be needed for perfect table reconstruction.
        if all_horizontal_dfs:
            horizontal_df = pd.concat(all_horizontal_dfs).drop_duplicates(subset=['page_num', 'block_num', 'par_num', 'line_num', 'word_num', 'text'])
            self.full_df = pd.concat([self.full_df, horizontal_df]).drop_duplicates(subset=['text', 'top', 'left'])

        self.log_message.emit("Quét Toàn diện hoàn tất.")
        self.scan_complete.emit(self.full_df)
        self.running = False

    def capture_screen_area(self, rect):
        with mss() as sct:
            monitor = {"top": rect.y(), "left": rect.x(), "width": rect.width(), "height": rect.height()}
            sct_img = sct.grab(monitor)
            return np.array(sct_img)

    def perform_ocr(self, img):
        img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        ocr_data_str = pytesseract.image_to_data(img_bgr, timeout=5)
        df = pd.read_csv(StringIO(ocr_data_str), sep='\t')
        df.dropna(subset=['conf'], inplace=True)
        return df

    def is_image_same(self, img1, img2):
        if img1.shape != img2.shape:
            return False
        # Use Mean Squared Error to check for similarity
        mse = np.mean((img1 - img2) ** 2)
        return mse < 100 # Threshold for similarity

    def stop(self):
        self.running = False
        self.wait()

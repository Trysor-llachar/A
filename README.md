# Agent - Trợ lý Dữ liệu Ngữ cảnh

Đây là một ứng dụng máy tính để bàn dành cho Windows hoạt động như một trợ lý công việc thông minh, sử dụng giám sát màn hình và OCR để tự động hóa các quy trình công việc.

## Thiết lập

Để chạy ứng dụng này, bạn cần cài đặt một số phụ thuộc hệ thống và Python.

### 1. Phụ thuộc Hệ thống

Ứng dụng này yêu cầu Tesseract OCR engine.

**Trên Windows:**
Tải xuống và cài đặt Tesseract từ [trang chính thức](https://github.com/UB-Mannheim/tesseract/wiki). Đảm bảo thêm thư mục cài đặt Tesseract vào PATH hệ thống của bạn trong quá trình cài đặt.

**Trên Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr
```

### 2. Phụ thuộc Python

Sau khi cài đặt các phụ thuộc hệ thống, hãy cài đặt các thư viện Python cần thiết bằng pip:

```bash
pip install -r requirements.txt
```

## Cách chạy

Sau khi tất cả các phụ thuộc đã được cài đặt, hãy chạy ứng dụng bằng lệnh sau:

```bash
python main.py
```

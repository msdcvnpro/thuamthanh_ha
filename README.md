# 🗣️ Trợ lý nhận biết âm lượng khi đọc bài (Streamlit)

Ứng dụng web giúp học sinh luyện đọc: nếu đọc to đủ sẽ được khen, nếu đọc nhỏ sẽ được khuyến khích. Ứng dụng truy cập trực tiếp micro của máy tính (trên trình duyệt) và đo âm lượng theo thời gian thực.

## Cài đặt

Yêu cầu: Python 3.9+ (đề xuất 3.10/3.11), trình duyệt Chromium/Chrome/Edge/Firefox.

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows PowerShell
pip install -r requirements.txt
```

## Chạy ứng dụng

```bash
streamlit run app.py
```

Mở đường dẫn được in ra (thường là `http://localhost:8501`). Khi trình duyệt hỏi quyền micro, hãy bấm Cho phép (Allow).

## Cách sử dụng

- Nhập tên học sinh ở thanh bên trái.
- Điều chỉnh mức mục tiêu dBFS (đề xuất: -25 dBFS) và thời gian duy trì.
- Nhấn Start ở khung “Kết nối micro” để cấp quyền micro.
- Bắt đầu đọc. Khi âm lượng đạt và giữ trên ngưỡng trong thời gian cài đặt, ứng dụng sẽ hiển thị lời khen. Nếu nhỏ hơn, ứng dụng đưa ra lời khuyến khích.

## Ghi chú kỹ thuật

- Ứng dụng dùng `streamlit-webrtc` để lấy âm thanh từ trình duyệt.
- dBFS (decibels full scale) càng gần 0 càng to; giá trị âm, ví dụ -25 dBFS là mức đọc vừa đủ rõ.
- Thanh tiến độ hiển thị ước lượng cường độ (RMS) đã làm mượt theo thời gian.



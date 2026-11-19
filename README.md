# Operation Management System (OMS)

Website nội bộ cho broker: theo dõi margin khách hàng, báo cáo hằng ngày, soạn tin/mail nghiệp vụ. Viết bằng Streamlit, dữ liệu lưu SQLite trên máy.

## Chạy trên máy (Windows)
1. Cài Python 3.10+ rồi chạy một lần: `python -m pip install -r requirements.txt`
2. Tạo file `team_password.txt` (một dòng là mật khẩu vào app).
3. Nhấp đúp `chay_app.bat` (tự mở trình duyệt tại http://localhost:8501).

Chạy tay: `python -m streamlit run app.py --server.port 8501`. Bản demo dữ liệu giả: `run_demo.bat`.

## Các trang
- **Trang chủ**: tổng quan, NAV qua các ngày.
- **Báo cáo hằng ngày**: đọc ảnh OPT (OCR), cập nhật số dư, SLCP, giá; xuất lại file Excel.
- **KH & Margin**: tổng quan theo nhóm, chi tiết, công cụ nộp/rút/mua/bán (ghi nhận và xuất Excel), soạn tin call margin, cú pháp chuyển tiền, danh mục cho vay, nguồn dữ liệu theo nhóm.
- **Sổ lệnh**: sổ lệnh và soạn email lệnh thỏa thuận (có đọc ảnh, nhiều KH/CTCK trong một email).
- **Archive**: kho file mẫu theo thư mục, mẫu trả lời.
- **Tin tức**, **Cài đặt** (ngưỡng margin, danh bạ KH, danh sách CTCK, sao lưu).

## Dữ liệu và bảo mật
- Toàn bộ dữ liệu KH nằm trong thư mục `data/` (không đưa lên Git, đã chặn bằng `.gitignore`). Sao lưu ở Cài đặt.
- Mật khẩu vào app: biến môi trường `OMS_PASSWORD` hoặc `team_password.txt`; trên Streamlit Cloud dùng Secrets (`OMS_PASSWORD = "..."`).
- Không commit file `.xlsx`, `.csv`, `.db`, ảnh/giấy tờ của khách.

## Kiểm thử
`python tests/smoke_test.py "<file Excel KH>" "<file danh mục cho vay>"` và `python tests/smoke_daily_flow.py "<file Excel KH>"`.

## Triển khai
Xem `DEPLOY_CLOUD.md`. Lưu ý Streamlit Cloud không giữ dữ liệu lâu dài.

# Đưa app lên Streamlit Community Cloud

## Lưu ý trước khi làm
- Cloud chỉ nhận CODE. Dữ liệu KH (thư mục data/, file Excel, danh bạ) KHÔNG được đưa lên GitHub (đã chặn bằng .gitignore).
- Trên cloud app bắt đầu rỗng. Bạn nạp file Excel/danh bạ trong app như bình thường.
- Cloud có thể tự khởi động lại/ngủ khi không dùng, khi đó dữ liệu đã nạp bị mất, phải nạp lại.
- Bắt buộc đặt mật khẩu (bước 4) và để repo ở chế độ Private.

## Các bước
1. Vào github.com, tạo tài khoản (nếu chưa có), bấm New repository, đặt tên `oms`, chọn **Private**.
2. Cài GitHub Desktop, đăng nhập, chọn File > Add local repository > thư mục `broker-workspace`
   (hoặc "Create repository" tại thư mục này), bấm **Publish repository**, tick **Keep this code private**.
   Kiểm tra trong danh sách file thay đổi KHÔNG có thư mục `data`, file .xlsx, .csv, .db.
3. Vào share.streamlit.io, đăng nhập bằng GitHub, bấm **Create app**, chọn repo `oms`, branch `main`,
   Main file path: `app.py`.
4. Trước khi Deploy, mở **Advanced settings > Secrets**, dán:
   `OMS_PASSWORD = "mat-khau-cua-ban"`
5. Bấm Deploy, chờ vài phút (lần đầu cài thư viện OCR khá lâu). Xong có link dạng `https://ten-app.streamlit.app`.
6. Vào Settings của app trên Streamlit, chọn Sharing > chỉ cho phép email được mời (Private).

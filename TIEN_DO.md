# Tiến độ dự án Workspace Broker (cập nhật 14/11/2026)

## 1. Cách chạy lại website
```
cd "C:\Users\MY PC\Documents\broker-workspace"
python -m pip install -r requirements.txt
python -m streamlit run app.py
```
Mở `localhost:8501`. Sau mỗi lần được cập nhật file mã nguồn, dừng (Ctrl+C) rồi chạy lại.

## 2. Quy trình "Báo cáo hằng ngày" (tab 1. Cập nhật từ ảnh OPT)
1. Tải file Excel gốc (mỗi sheet một KH) → "Dùng file này làm file gốc".
2. Trong OPT: gõ số tài khoản `011C` + 6 số → Enter → Win+Shift+S chụp cửa sổ Quản lý danh mục.
3. Bước 3: bấm "📋 Dán ảnh từ clipboard" (tự nhận tài khoản theo số tài khoản trong ảnh), hoặc dán/tải từng ảnh vào đúng tài khoản.
4. Bước 4: website tự đọc ảnh (OCR chạy trên máy). Kiểm tra số dư tiền, NAV, SLCP, Giá TT; xem bảng đối chiếu File Excel với số mới; bấm "Xác nhận & cập nhật".
5. Bước 5: tải file Excel đã cập nhật (giữ ảnh/định dạng; ghi B3, cột D, cột E).

## 3. Những điều đã xác định về file Excel thật
- Sheet khách có tên dạng "Khánh 551798" (tên + 6 số cuối tài khoản). Sheet ẩn/bản sao "(2)" bị bỏ qua.
- B3 (số dư tiền) và D2 (SLCP) là công thức có phần điều chỉnh, ví dụ `=-142154666561+6.4*10^6*E2-110*10^9`, D2 `=...-6.4*10^6`.
- Giá cột E của các sheet là liên kết `='Duyên 814345'!E2`; chỉ ô số (sheet Duyên) được ghi.
- NAV (B4) = B3 + SUM(G2:G4): chỉ cộng dòng 2–4, tối đa 3 mã mỗi sheet.
- Quyết định của người dùng: file xuất phải khớp OPT. Mặc định ghi đúng số OPT (B3, D, E), BỎ phần điều chỉnh cũ. Có ô tick "Giữ phần điều chỉnh" nếu cần giữ.
- Kết quả thử trên file thật (mở bằng LibreOffice): NAV khớp OPT cho Duyên, Khánh, Phong, T.Xuân (Đ.Xuân đúng theo phép tính).

## 4. Mã nguồn chính (thư mục broker-workspace)
- `views/daily.py`: giao diện báo cáo hằng ngày (5 bước, dán nhanh, đối chiếu, xuất Excel).
- `core/snapshot_ocr.py`: đọc ảnh OPT (RapidOCR), đọc theo nhãn chữ hoặc theo khung đã khoanh, tự chốt dấu số dư (NAV = số dư + GTTT), suy giá TT = GTTT / GD.
- `core/xlsxpatch.py`: sửa trực tiếp ô trong .xlsx gốc (giữ ảnh), ghi số hoặc công thức, thêm dòng mã mới bằng cách nhân bản dòng mẫu.
- `core/xlsxformula.py`: tách/tính công thức B3, D.
- `core/importer.py`: đọc file Excel (bỏ sheet ẩn, tách tên + số tài khoản).
- `core/db.py`, `core/margin.py`, `core/service.py`, `core/dailyreport.py`: DB SQLite và tính margin theo công thức file.
- `data/daily_original.xlsx`: file gốc đã nạp. `data/roi.json`: khung đọc ảnh đã lưu.

## 5. Lỗi đã gặp và đã xử lý
- Thư mục sai khi chạy pip → phải `cd` vào thư mục dự án.
- OCR hết bộ nhớ ("bad allocation") → dùng chung một bộ đọc ảnh cho cả phiên (không nạp lại mỗi lần chạy).
- Số dư đọc thành số dương khi mất dấu ngoặc → tự chốt dấu theo NAV.
- Một số lần chép file vào máy báo "đã ghi" nhưng file cũ vẫn còn → luôn ghi đè bằng force và kiểm tra lại kích thước trên máy.
- Danh sách tài khoản lệch (tên cũ trong DB) → website tự đồng bộ theo file gốc.

## 6. Việc dự kiến làm tiếp
- Chạy thử trọn quy trình trên dữ liệu thật hằng ngày; ghi lại ô nào còn lệch (sheet, ô, giá trị đúng).
- Kiểm tra tab "2. Kết quả": check sức mua / SLCP mua tối đa sau khi file đã khớp OPT.
- Mã mới chưa có trong Danh mục cho vay: nạp danh mục để có tỉ lệ ký quỹ và hạn mức đúng.
- Sheet có hơn 3 mã: mở rộng công thức `=SUM(G2:G4)`.
- Chưa làm: tin tức theo mã trong danh mục, bản tin cuối ngày (Bán lẻ, BĐS, Thép), quản lý lệnh, mẫu nghiệp vụ hoàn chỉnh.
- Bot chụp OPT tự động: công cụ điều khiển máy không nhận ra OPT (chạy từ `C:\HSC\OPT_Laucher.exe`); hiện dùng Win+Shift+S. Có skill `hsc-opt-portfolio-capture` (cần 2 script PowerShell đi kèm) nếu muốn nạp ảnh theo thư mục.

## 7. Bổ sung ngày 15/11/2026: công cụ Margin
- Tab "Công cụ nộp / rút tiền" (views/margin.py): nộp thêm tiền để MR về ngưỡng; bán cổ phiếu theo giá KH đưa thì rút được bao nhiêu (rút theo EE DT, IM DT = IM × tỷ lệ tài khoản, VIP 0.55); chế độ tự chọn mã bán ít SLCP nhất.
- Tab "Nhiều tài khoản" (core/multi.py): A nộp tiền mua tối đa; B nhận về N cổ phiếu, chia vol, tiền nộp làm tròn lên 0,5 tỷ; C rút tổng X tỷ (ít SLCP nhất hoặc "Không chia nhiều tài khoản"); D bán hết 1 mã rút / mua mã khác. Có ô cú pháp trả lời mẫu để sao chép.
- Quy tắc: hạn mức mã còn lại ≤ 0 thì sức mua = 0; "vay ~X" = dư nợ sau mua.
- Cần test: nạp danh mục cho vay + cập nhật giá rồi thử các ví dụ trong file "Luyện tập tình huống Margin" (Cường 84 tỷ, rút 20 tỷ GMD), báo ô lệch.

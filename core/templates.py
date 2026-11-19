"""Mẫu nghiệp vụ mặc định.

QUAN TRỌNG: các trường dưới đây chỉ là gợi ý ban đầu. Quy trình và biểu mẫu thật của công ty
bạn có thể khác — hãy sửa trong trang "Archive" > "Format trả lời KH" cho khớp form bạn đang nhập.
Trong nội dung mẫu, dùng {tên_trường} để chèn dữ liệu; {thieu} = danh sách trường còn thiếu.
"""

DEFAULT_PROCEDURES = {
    "mo_tk": {
        "name": "Mở tài khoản",
        "fields": [
            {"key": "ho_ten", "label": "Họ và tên", "required": True, "kind": "text"},
            {"key": "ngay_sinh", "label": "Ngày sinh", "required": True, "kind": "text"},
            {"key": "cccd", "label": "Số CCCD", "required": True, "kind": "cccd"},
            {"key": "ngay_cap", "label": "Ngày cấp CCCD", "required": True, "kind": "text"},
            {"key": "noi_cap", "label": "Nơi cấp", "required": True, "kind": "text"},
            {"key": "sdt", "label": "Số điện thoại", "required": True, "kind": "phone"},
            {"key": "email", "label": "Email", "required": True, "kind": "email"},
            {"key": "dia_chi", "label": "Địa chỉ thường trú", "required": True, "kind": "text"},
            {"key": "ngan_hang", "label": "Ngân hàng + số TK nhận tiền", "required": False, "kind": "text"},
            {"key": "dich_vu", "label": "Dịch vụ đăng ký thêm (margin, ...)", "required": False, "kind": "text"},
        ],
        "msg_customer": "Chào anh/chị {ho_ten_hoac_kh}, để mở tài khoản em cần anh/chị bổ sung:\n{thieu}\nAnh/chị gửi giúp em nhé. Em cảm ơn!",
        "data_block": "Họ tên: {ho_ten}\nNgày sinh: {ngay_sinh}\nCCCD: {cccd} | Cấp ngày: {ngay_cap} | Nơi cấp: {noi_cap}\nSĐT: {sdt}\nEmail: {email}\nĐịa chỉ: {dia_chi}\nNgân hàng: {ngan_hang}\nDịch vụ thêm: {dich_vu}",
    },
    "margin": {
        "name": "Đăng ký / điều chỉnh margin",
        "fields": [
            {"key": "tk", "label": "Số tài khoản", "required": True, "kind": "text"},
            {"key": "loai", "label": "Nội dung (đăng ký mới / tăng hạn mức / gia hạn / đóng)", "required": True, "kind": "text"},
            {"key": "han_muc", "label": "Hạn mức đề nghị (VND)", "required": False, "kind": "text"},
            {"key": "ghi_chu", "label": "Ghi chú", "required": False, "kind": "text"},
        ],
        "msg_customer": "Chào anh/chị {ho_ten_hoac_kh}, để xử lý yêu cầu margin em cần thêm:\n{thieu}\nEm cảm ơn!",
        "data_block": "TK: {tk}\nNội dung: {loai}\nHạn mức đề nghị: {han_muc}\nGhi chú: {ghi_chu}",
    },
    "nop_rut": {
        "name": "Nộp / rút tiền",
        "fields": [
            {"key": "tk", "label": "Số tài khoản", "required": True, "kind": "text"},
            {"key": "loai", "label": "Nộp hay rút", "required": True, "kind": "text"},
            {"key": "so_tien", "label": "Số tiền (VND)", "required": True, "kind": "text"},
            {"key": "ngan_hang", "label": "Ngân hàng + số TK nhận (nếu rút)", "required": False, "kind": "text"},
            {"key": "ghi_chu", "label": "Ghi chú", "required": False, "kind": "text"},
        ],
        "msg_customer": "Chào anh/chị {ho_ten_hoac_kh}, để thực hiện giao dịch tiền em cần thêm:\n{thieu}\nEm cảm ơn!",
        "data_block": "TK: {tk}\nLoại: {loai}\nSố tiền: {so_tien}\nNgân hàng nhận: {ngan_hang}\nGhi chú: {ghi_chu}",
    },
    "ck": {
        "name": "Chuyển khoản chứng khoán",
        "fields": [
            {"key": "tk_chuyen", "label": "TK chuyển", "required": True, "kind": "text"},
            {"key": "tk_nhan", "label": "TK nhận (và nơi mở)", "required": True, "kind": "text"},
            {"key": "ma", "label": "Mã chứng khoán", "required": True, "kind": "text"},
            {"key": "sl", "label": "Số lượng", "required": True, "kind": "text"},
            {"key": "ly_do", "label": "Lý do chuyển", "required": False, "kind": "text"},
        ],
        "msg_customer": "Chào anh/chị {ho_ten_hoac_kh}, để chuyển khoản chứng khoán em cần thêm:\n{thieu}\nEm cảm ơn!",
        "data_block": "TK chuyển: {tk_chuyen}\nTK nhận: {tk_nhan}\nMã: {ma}\nSố lượng: {sl}\nLý do: {ly_do}",
    },
}

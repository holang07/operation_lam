"""Soạn email lệnh thỏa thuận (MUA / BÁN) theo mẫu gửi phòng giao dịch. Chỉ tạo nội dung, không gửi."""
from __future__ import annotations

from html import escape

FONT = "Cambria,'Times New Roman',serif"
SEP = "=" * 32


def n0(v) -> str:
    return f"{int(round(float(v))):,}"


def build(kind: str, *, prefix: str, kh_acct: str, kh_name: str, cp_acct: str, cp_name: str, orders: list[dict],
          initiator: str = "Bên bán", foreign: tuple = (), need_margin: bool | None = None, approver: str = "Hà") -> dict:
    """kind: 'MUA' (KH là bên mua) hoặc 'BÁN' (KH là bên bán).
    orders: [{ticker, qty, price}]. Trả về dict(subject, html, text, rows)."""
    mua = kind.upper() == "MUA"
    if need_margin is None:
        need_margin = mua
    orders = [o for o in orders if o.get("ticker") and o.get("qty") and o.get("price")]
    tks = []
    for o in orders:
        if o["ticker"] not in tks:
            tks.append(o["ticker"])
    accts = []
    for o in orders:
        a_ = o.get("kh_acct") or kh_acct
        if a_ and a_ not in accts:
            accts.append(a_)
    subject = f"{prefix}_THỎA THUẬN {'MUA' if mua else 'BÁN'} {', '.join(tks)}_{', '.join(accts) or kh_acct}_{len(orders)} LỆNH"

    box = lambda on: "☑" if on else "☐"
    td = f"border:1px solid #666;padding:4px 7px;font-family:{FONT};font-size:14px;"
    p = f"margin:0 0 12px 0;font-family:{FONT};font-size:14px;"

    def row(label, value, align="left", bold=False):
        v = f"<b>{value}</b>" if bold else value
        return (f"<tr><td style=\"{td}width:46%;\">{label}</td>"
                f"<td style=\"{td}text-align:{align};\">{v}</td></tr>")

    parts = [f'<p style="{p}">Kính gửi anh chị,<br>Nhờ anh chị thực hiện lệnh thỏa thuận giúp em như bên dưới. Cảm ơn anh chị.</p>',
             f'<p style="{p}">{SEP}</p>']
    if need_margin:
        parts += [f'<p style="{p}">Kính gửi anh {escape(approver)},<br>Em có KH thực hiện lệnh thỏa thuận có sử dụng margin Dtrade '
                  f'như bên dưới. TK đủ tỷ lệ để thực hiện, nhờ anh {escape(approver)} xét duyệt giúp em ạ.<br><br>'
                  f'Cảm ơn anh {escape(approver)}.</p>', f'<p style="{p}">{SEP}</p>']
    rows = []
    for i, o in enumerate(orders, 1):
        total = float(o["qty"]) * float(o["price"])
        c_acct, c_name = o.get("cp_acct") or cp_acct, o.get("cp_name") or cp_name       # mỗi lệnh có thể một CTCK đối tác
        k_acct, k_name = o.get("kh_acct") or kh_acct, o.get("kh_name") or kh_name         # mỗi lệnh có thể một KH
        ban_acct, ban_name = (c_acct, c_name) if mua else (k_acct, k_name)
        mua_acct, mua_name = (k_acct, k_name) if mua else (c_acct, c_name)
        init_html = f"{box(initiator == 'Bên bán')}Bên bán &nbsp;&nbsp;{box(initiator == 'Bên mua')}Bên mua"
        frn_html = f"{box('Bên bán' in foreign)}Bên bán &nbsp;&nbsp;{box('Bên mua' in foreign)}Bên mua"
        parts.append(f'<p style="{p}margin-bottom:6px;"><b>Lệnh{"" if len(orders) == 1 else f" {i}"}:</b></p>')
        parts.append(f'<table style="border-collapse:collapse;width:540px;margin-bottom:18px;">'
                     + row("Bên khởi tạo lệnh", init_html) + row("NĐT nước ngoài", frn_html)
                     + row("Số tài khoản Bán", escape(ban_acct)) + row("Tên khách hàng BÁN", escape(ban_name))
                     + row("Mã chứng khoán", escape(o["ticker"]), "right") + row("Khối lượng", n0(o["qty"]), "right", True)
                     + row("Giá (VND)", n0(o["price"]), "right") + row("Tổng giá trị (VND)", n0(total), "right")
                     + row("Số tài khoản MUA", escape(mua_acct)) + row("Tên khách hàng MUA", escape(mua_name))
                     + "</table>")
        rows.append({"Loại lệnh": "MUA" if mua else "BÁN", "Subject": subject, "Bên khởi tạo": initiator,
                     "Số TK Bán": ban_acct, "Tên KH BÁN": ban_name, "Mã CK": o["ticker"], "Khối lượng": o["qty"],
                     "Giá": o["price"], "Tổng giá trị": total, "Số TK Mua": mua_acct, "Tên KH MUA": mua_name,
                     "Cần duyệt Margin Dtrade?": "CÓ" if need_margin else "KHÔNG"})
    return dict(subject=subject, html="".join(parts), rows=rows)

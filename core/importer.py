"""Đọc file Excel dạng "mỗi sheet = một khách hàng" (giống file demo của bạn)."""
from __future__ import annotations

import re
from collections import Counter

from openpyxl import load_workbook

_SAFE = re.compile(r"^[\d\.\+\-\*/\^\(\) ]+$")


def _num(cached, formula=None):
    """Lấy số: ưu tiên giá trị đã tính sẵn, nếu không có thì thử đọc công thức số học đơn giản."""
    if isinstance(cached, (int, float)):
        return float(cached)
    if isinstance(formula, (int, float)):
        return float(formula)
    if isinstance(formula, str) and formula.startswith("="):
        expr = formula[1:].replace("^", "**")
        if _SAFE.match(formula[1:]):
            try:
                return float(eval(expr, {"__builtins__": {}}, {}))  # chỉ chứa số và + - * / ( )
            except Exception:
                return None
    return None


def _split_name(title: str):
    # "Tên - 123456", "Tên 123456", "Tên - 011C123456": tên + số tài khoản ở cuối
    m = re.match(r"^(.*?)[\s\-–]+((?:\d{3}C)?\d{4,})\s*$", title.strip())
    if m:
        return m.group(1).strip(), m.group(2)
    return title.strip(), ""


def parse_workbook(file) -> tuple[list[dict], dict, list[str]]:
    """Trả về (danh sách KH, bảng giá theo mã, cảnh báo)."""
    wv = load_workbook(file, data_only=True)
    try:
        file.seek(0)
    except Exception:
        pass
    wf = load_workbook(file, data_only=False)

    customers, warnings = [], []
    price_votes: dict[str, list[tuple[float, bool]]] = {}

    for ws in wv:
        if ws.sheet_state != "visible":      # sheet ẩn (bản nháp/bản sao) không phải tài khoản đang theo dõi
            continue
        if str(ws["C1"].value).strip() != "Cổ phiếu" or str(ws["D1"].value).strip() != "Q=SL":
            continue
        wsf = wf[ws.title]
        name, account = _split_name(ws.title)
        cash = _num(ws["B3"].value, wsf["B3"].value)
        if cash is None:
            warnings.append(f"[{ws.title}] Không đọc được số dư tiền (B3), đặt tạm = 0.")
            cash = 0.0
        mm = _num(ws["A23"].value, wsf["A23"].value)
        if mm is None or not (0 < mm <= 1):
            warnings.append(f"[{ws.title}] Không đọc được tỷ lệ tài khoản (A23), dùng mặc định.")
            mm = None

        positions = []
        for r in range(2, 10):
            ticker = ws.cell(r, 3).value
            if not isinstance(ticker, str) or not ticker.strip():
                continue
            qty = _num(ws.cell(r, 4).value, wsf.cell(r, 4).value)
            price = _num(ws.cell(r, 5).value, wsf.cell(r, 5).value) or 0.0
            im = _num(ws.cell(r, 6).value, wsf.cell(r, 6).value)
            limit = _num(ws.cell(r, 15).value, wsf.cell(r, 15).value) or 0.0
            if qty is None or im is None:
                warnings.append(f"[{ws.title}] Dòng {r} ({ticker}) thiếu số lượng hoặc tỉ lệ ký quỹ, bỏ qua.")
                continue
            t = ticker.strip().upper()
            positions.append(dict(ticker=t, qty=qty, im_pct=im, limit=limit, row=r, price=price,
                                  qty_raw=wsf.cell(r, 4).value, price_raw=wsf.cell(r, 5).value))
            if price > 0:
                price_votes.setdefault(t, []).append((price, qty > 0))

        customers.append(dict(name=name, account_no=account, cash=cash, mm=mm, positions=positions, sheet=ws.title,
                              cash_raw=wsf["B3"].value))

    prices, conflicts = {}, []
    for t, votes in price_votes.items():
        pool = [p for p, held in votes if held] or [p for p, _ in votes]
        counts = Counter(pool)
        best = counts.most_common(1)[0][0]
        prices[t] = best
        if len(set(p for p, _ in votes)) > 1:
            conflicts.append(f"Mã {t} có nhiều giá khác nhau trong file: "
                             f"{sorted(set(p for p, _ in votes))}; dùng {best:,.0f}.")
    warnings.extend(conflicts)
    return customers, prices, warnings

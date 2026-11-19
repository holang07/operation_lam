"""Đọc file "Danh mục cho vay" (sheet "0"): tỉ lệ ký quỹ công bố, hạn mức theo mã, IM đề xuất."""
from __future__ import annotations

import re

from openpyxl import load_workbook

_TICKER = re.compile(r"^[A-Z0-9]{2,5}$")


def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def list_candidate_sheets(file) -> list[str]:
    wb = load_workbook(file, data_only=True, read_only=False)
    out = []
    for ws in wb:
        if any(str(ws.cell(r, 2).value or "").strip() == "MÃ" for r in range(1, 12)):
            out.append(ws.title)
    return out


def parse_loan_list(file, sheet: str | None = None) -> dict:
    """Trả về dict(sheet, account_ratio, items{ticker: {...}}, warnings)."""
    wb = load_workbook(file, data_only=True)
    names = [ws.title for ws in wb if any(str(ws.cell(r, 2).value or "").strip() == "MÃ" for r in range(1, 12))]
    if not names:
        raise ValueError("Không tìm thấy bảng có cột 'MÃ' trong file.")
    sheet = sheet if sheet in names else ("0" if "0" in names else names[0])
    ws = wb[sheet]
    warnings: list[str] = []

    # Tỷ lệ tài khoản: số đầu tiên cùng dòng với nhãn "Tỷ lệ tài khoản"
    ratio = None
    for r in range(1, 12):
        if "tỷ lệ tài khoản" in str(ws.cell(r, 2).value or "").lower():
            for c in range(3, 12):
                if _is_num(ws.cell(r, c).value):
                    ratio = float(ws.cell(r, c).value)
                    break
    if ratio is None:
        warnings.append("Không đọc được 'Tỷ lệ tài khoản', dùng 0.55.")
        ratio = 0.55

    # Cột IM đề xuất: ô có chữ "ĐỀ XUẤT" ở các dòng đầu
    prop_col = None
    for r in range(1, 6):
        for c in range(1, ws.max_column + 1):
            if "ĐỀ XUẤT" in str(ws.cell(r, c).value or "").upper():
                prop_col = c

    items: dict[str, dict] = {}
    for r in range(1, ws.max_row + 1):
        t = ws.cell(r, 2).value
        ck = ws.cell(r, 3).value
        if not isinstance(t, str) or not _TICKER.match(t.strip()) or t.strip() == "MÃ" or not _is_num(ck):
            continue
        t = t.strip()
        im = 100.0 if ck <= 0 else float(ck) * 100
        limit = float(ws.cell(r, 8).value or 0) if ck > 0 else 0.0
        proposed = None
        if prop_col:
            pv = ws.cell(r, prop_col).value
            if _is_num(pv) and pv > 0:
                proposed = float(pv) * 100
        new = dict(im_pct=im, limit=limit, im_proposed_pct=proposed, row=r)
        if t in items:
            old = items[t]
            both_full = old["im_pct"] >= 100 and new["im_pct"] >= 100   # cùng ký quỹ 100%: hạn mức không còn ý nghĩa
            if not both_full and (old["im_pct"], old["limit"]) != (new["im_pct"], new["limit"]):
                warnings.append(f"Mã {t} xuất hiện 2 lần (dòng {old['row']} và {r}) với giá trị khác nhau, "
                                "giữ cách thận trọng hơn (IM cao hơn, hạn mức thấp hơn).")
                new = dict(im_pct=max(old["im_pct"], new["im_pct"]), limit=min(old["limit"], new["limit"]),
                           im_proposed_pct=new["im_proposed_pct"] or old["im_proposed_pct"], row=r)
            else:
                new["im_proposed_pct"] = new["im_proposed_pct"] or old["im_proposed_pct"]
        items[t] = new
    return dict(sheet=sheet, sheets=names, account_ratio=ratio, items=items, warnings=warnings)

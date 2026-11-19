"""Xuất lại file Excel gốc từ dữ liệu đang có trong app: chỉ ghi phần CHÊNH so với file gốc (số dư tiền B3, SLCP cột D; giá cột E không đụng tới).
Phần chênh được CỘNG vào công thức cũ (ví dụ =-36069390310+2300000000) nên lịch sử điều chỉnh trong ô vẫn còn."""
from __future__ import annotations

import io

from core import service, xlsxformula, xlsxpatch
from core.importer import parse_workbook


def _sum_formula(raw, old: float, delta: float) -> str:
    d = xlsxformula.fmt_num(delta)
    add = d if d.startswith("-") else "+" + d
    if isinstance(raw, str) and raw.startswith("="):
        return raw.replace(" ", "") + add
    return "=" + xlsxformula.fmt_num(old) + add


def build(orig_bytes: bytes) -> tuple[bytes, list[str], list[str], int]:
    """Trả về (file xlsx mới, ghi chú, ô không ghi được, số tài khoản có thay đổi)."""
    cs, _, _ = parse_workbook(io.BytesIO(orig_bytes))
    fresh = {c["name"]: c for c in service.load_customers()}
    edits, newrows, notes = {}, {}, []
    changed = 0
    for sh in cs:
        cu = fresh.get(sh["name"])
        if not cu:
            continue
        cells = {}
        d_cash = (cu["cash"] or 0.0) - (sh["cash"] or 0.0)
        if abs(d_cash) > 0.5:
            cells["B3"] = _sum_formula(sh.get("cash_raw"), sh["cash"] or 0.0, d_cash)
        rowof = {p["ticker"]: p for p in sh["positions"]}
        for p in cu["positions"]:
            fp = rowof.get(p.ticker)
            if fp:
                dq = p.qty - fp["qty"]
                if abs(dq) > 0.5:
                    cells[f"D{fp['row']}"] = _sum_formula(fp.get("qty_raw"), fp["qty"], dq)
            elif p.qty > 0:
                used = {x["row"] for x in sh["positions"]} | {r for r, _, _ in newrows.get(sh["sheet"], [])}
                free = [r for r in (2, 3, 4) if r not in used]
                if rowof and free:
                    newrows.setdefault(sh["sheet"], []).append(
                        (free[0], min(x["row"] for x in sh["positions"]),
                         {"C": p.ticker, "D": p.qty, "E": p.price, "F": p.im_pct, "O": p.limit}))
                else:
                    notes.append(f"{sh['name']}: mã mới {p.ticker} ({p.qty:,.0f} cp) hết dòng trống 2–4, cần thêm tay vào Excel.")
        for t, fp in rowof.items():
            if t not in {p.ticker for p in cu["positions"]}:
                cells[f"D{fp['row']}"] = _sum_formula(fp.get("qty_raw"), fp["qty"], -fp["qty"])
        if cells or newrows.get(sh["sheet"]):
            edits[sh["sheet"]] = cells
            changed += 1
    out, failed = xlsxpatch.patch_workbook(orig_bytes, edits, newrows)
    return out, notes, failed, changed

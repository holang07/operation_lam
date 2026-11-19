"""Đối chiếu kết quả của app với giá trị đã tính sẵn trong file Excel.

Chạy: python tests/check_against_workbook.py "đường_dẫn_file.xlsx"
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import load_workbook

from core.importer import parse_workbook
from core.margin import Position, Settings, compute

path = sys.argv[1]
with open(path, "rb") as f:
    customers, prices, warnings = parse_workbook(f)
wv = load_workbook(path, data_only=True)

by_title = {}
for ws in wv:
    from core.importer import _split_name
    by_title[_split_name(ws.title)[0]] = ws

def close(a, b, tol=1e-6):
    if a is None or b is None or isinstance(b, str):
        return False
    return math.isclose(a, b, rel_tol=tol, abs_tol=1.0)

ok = bad = 0
for c in customers:
    ws = by_title[c["name"]]
    # Dùng đúng giá trong từng sheet (file có thể lệch giá giữa các sheet)
    pos = []
    for i, p in enumerate(c["positions"]):
        row = 2 + i
        pos.append(Position(p["ticker"], p["qty"], ws.cell(row, 5).value or 0, p["im_pct"], p["limit"]))
    res = compute(c["cash"], pos, c["mm"] or 0.6, Settings())
    checks = {
        "NAV (B4)": (res["nav"], ws["B4"].value),
        "IMR (H6)": (res["imr"], ws["H6"].value),
        "EE (I6)": (res["ee"], ws["I6"].value),
        "MR (J6)": (res["mr"], ws["J6"].value),
        "IMR DT (L6)": (res["imr_dt"], ws["L6"].value),
        "EE DT (M6)": (res["ee_dt"], ws["M6"].value),
        "MR DT (N6)": (res["mr_dt"], ws["N6"].value),
        "Tình trạng (B12)": (res["status"], ws["B12"].value),
        "Tiền nộp (B13)": (res["call_amount"], ws["B13"].value),
    }
    for label, (mine, ref) in checks.items():
        good = (mine == ref) if isinstance(ref, str) else close(mine, ref)
        ok += good
        bad += (not good)
        if not good:
            print(f"LỆCH  {c['name']:<20} {label:<18} app={mine}  excel={ref}")
print(f"\nKhớp {ok} / {ok + bad} chỉ số trên {len(customers)} khách hàng.")
print("Cảnh báo khi import:", *warnings, sep="\n - ")

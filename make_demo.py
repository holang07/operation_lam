"""Tạo dữ liệu DEMO (khách hàng, giá, danh mục cho vay, task) vào demo_data/workspace.db.
Toàn bộ là số giả, KHÔNG liên quan dữ liệu thật. Chạy: python make_demo.py"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("OMS_DB", str(ROOT / "demo_data" / "workspace.db"))
sys.path.insert(0, str(ROOT))

from core import db, tasks  # noqa: E402

LOAN = {  # mã: (IM %, hạn mức tỷ)
    "EIB": (60, 50), "HAH": (70, 30), "GMD": (60, 40), "MWG": (50, 60), "DMX": (60, 30), "VSC": (70, 20),
    "GEX": (70, 30), "MSB": (60, 40), "VIX": (70, 30), "PDR": (70, 20), "NKG": (70, 20), "HPG": (50, 80),
    "SSI": (50, 100), "VNM": (50, 50), "PNJ": (50, 30), "FRT": (60, 20),
}
PRICE = {"EIB": 20500, "HAH": 50700, "GMD": 66000, "MWG": 82000, "DMX": 60000, "VSC": 20000, "GEX": 36000,
         "MSB": 13500, "VIX": 15500, "PDR": 21000, "NKG": 14500, "HPG": 27500, "SSI": 29000, "VNM": 62000,
         "PNJ": 90000, "FRT": 150000}
# (tên, số TK, tiền, tỷ lệ TK, {mã: SLCP})
CUST = [
    ("Demo An", "100101", -3.0e9, 0.55, {"EIB": 300000, "HAH": 60000}),
    ("Demo Bình", "100202", -8.0e9, 0.55, {"MWG": 250000, "DMX": 150000}),
    ("Demo Chi", "100303", -16.0e9, 0.55, {"GMD": 250000, "HAH": 100000, "VSC": 150000}),
    ("Demo Dũng", "100404", -2.0e9, 0.55, {"MSB": 400000}),
    ("Demo Em", "100505", -13.5e9, 0.55, {"VIX": 500000, "GEX": 400000}),
    ("Demo Giang", "100606", -1.5e9, 0.55, {"PDR": 120000, "NKG": 150000}),
    ("Demo Hà", "100707", -20.9e9, 0.55, {"HPG": 500000, "SSI": 400000}),
    ("Demo Khoa", "100808", -5.0e9, 0.65, {"VNM": 100000, "PNJ": 40000}),
    ("Demo Lan", "100909", -22.9e9, 0.55, {"EIB": 600000, "MWG": 150000, "FRT": 40000}),
    ("Demo Minh", "101010", 3.0e9, 0.55, {"HPG": 200000, "VNM": 30000}),
]

db.init()
items = {t: {"im_pct": float(im), "limit": lim * 1e9, "im_proposed_pct": None} for t, (im, lim) in LOAN.items()}
db.import_loan_list(items, 0.55)
customers = [{"name": n, "account_no": a, "cash": c, "mm": mm, "sheet": n,
              "positions": [{"ticker": t, "qty": float(q), "im_pct": LOAN[t][0], "limit": LOAN[t][1] * 1e9}
                            for t, q in pos.items()]} for n, a, c, mm, pos in CUST]
db.import_customers(customers, {t: float(p) for t, p in PRICE.items()})
if not tasks.list_tasks(include_done=True):
    tasks.add("Gọi KH bổ sung hồ sơ margin", priority="Cao", due="2026-11-20", note="Task mẫu")
    tasks.add("Gửi báo cáo cuối ngày", target="Báo cáo")
    tasks.add("Đọc tin vĩ mô buổi sáng", target="Việc cá nhân", priority="Thấp")
print("Đã tạo dữ liệu demo:", os.environ["OMS_DB"])

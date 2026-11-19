"""Đối chiếu danh mục cho vay với các sheet KH.

Chạy: python tests/check_loan_list.py "danh_muc_cho_vay.xlsx" "file_KH.xlsx"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.importer import parse_workbook
from core.loanlist import parse_loan_list

ll = parse_loan_list(open(sys.argv[1], "rb"))
print(f"Sheet {ll['sheet']}: {len(ll['items'])} mã, tỷ lệ tài khoản {ll['account_ratio']}")
for w in ll["warnings"]:
    print(" - cảnh báo:", w)
cust, _, _ = parse_workbook(open(sys.argv[2], "rb"))
bad = 0
for c in cust:
    for p in c["positions"]:
        l = ll["items"].get(p["ticker"])
        im, lim = (l["im_pct"], l["limit"]) if l else (100.0, 0.0)
        if abs(im - p["im_pct"]) > 1e-6:
            bad += 1
            print(f"LỆCH IM  {c['name']} {p['ticker']}: file KH {p['im_pct']} vs danh mục {im}")
        if abs(lim - p["limit"]) > 1:
            bad += 1
            print(f"HẠN MỨC RIÊNG  {c['name']} {p['ticker']}: file KH {p['limit']/1e9:g} tỷ vs danh mục {lim/1e9:g} tỷ")
print("Xong, số dòng khác biệt:", bad)

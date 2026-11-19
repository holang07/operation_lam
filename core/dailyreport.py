"""Số liệu báo cáo hằng ngày: tổng dư nợ, tổng NAV, check sức mua, báo cáo sức mua."""
from __future__ import annotations

import math

LOT = 100


def total_debt(results: list[dict]) -> float:
    """Tổng dư nợ = tổng phần âm của số dư tiền (số dư âm = đang vay)."""
    return sum(max(0.0, -r["cash"]) for r in results)


def buying_rows(res: dict) -> list[dict]:
    """Các mã còn sức mua dương của một tài khoản. SLCP mua tối đa làm tròn xuống lô 100."""
    out = []
    for r in res["rows"]:
        qty = math.floor(r["max_qty"] / LOT) * LOT
        if r["buying_power"] > 0 and qty >= LOT:
            out.append(dict(ticker=r["ticker"], price=r["price"], remaining=max(0.0, r["remaining"]),
                            max_qty=qty, buying_power=r["buying_power"]))
    return out


def check_note(res: dict) -> str:
    if res["status"] == "fs":
        return f"FS: cần nộp {res['call_amount']:,.0f}"
    if res["status"] == "call":
        return f"Call: cần nộp {res['call_amount']:,.0f}"
    if res["ee_dt"] <= 0:
        return "Hết sức mua"
    if not buying_rows(res):
        return "Còn thừa ký quỹ nhưng mã không còn hạn mức/sức mua"
    return "Còn sức mua"

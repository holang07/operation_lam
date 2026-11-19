"""Lõi tính margin — bám sát công thức trong file Excel của bạn.

Quy ước (giống file Excel):
- im_pct: tỉ lệ ký quỹ theo mã, đơn vị % (ví dụ 75 = 75%)
- limit: hạn mức theo mã (cột "Hạn mức/mã"), đơn vị VND
- mm: hệ số duy trì của tài khoản (ô A23 trong file, ví dụ 0.55 hoặc 0.6)
- cash: số dư tiền, âm = dư nợ vay
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Settings:
    fs_threshold: float = 0.40      # MR < 40% -> bán giải chấp (FS)
    call_threshold: float = 0.50    # MR < 50% -> margin call
    call_target: float = 0.505      # đưa MR về mức này khi tính tiền nộp (file: 50.5%)
    default_mm: float = 0.60
    sell_im_options: tuple = (0.3, 0.4, 0.5, 0.6)


@dataclass
class Position:
    ticker: str
    qty: float
    price: float
    im_pct: float
    limit: float = 0.0
    limit_custom: bool = False      # hạn mức riêng của KH (không bị ghi đè khi đồng bộ danh mục)


def _imr(g: float, im_pct: float, limit: float) -> float:
    """IMR: phần vay vượt hạn mức mã thì phải ký quỹ 100% (cột H trong file)."""
    loan = g - g * im_pct / 100
    return g - limit if loan > limit else g * im_pct / 100


def compute(cash: float, positions: list[Position], mm: float,
            s: Settings | None = None, deposit: float = 0.0, shock: float = 0.0) -> dict:
    """Tính toàn bộ chỉ số của một tài khoản.

    deposit: tiền nộp thêm (what-if). shock: biến động giá toàn bộ mã, -0.1 = giảm 10%.
    """
    s = s or Settings()
    cash = cash + deposit
    rows = []
    for p in positions:
        price = p.price * (1 + shock)
        g = p.qty * price
        im = p.im_pct / 100
        k_pct = p.im_pct if p.im_pct >= 100 else p.im_pct * mm        # IM DT (%)
        imr = _imr(g, p.im_pct, p.limit)
        imr_dt = _imr(g, k_pct, p.limit)
        used = g - imr_dt                                              # "Đã dùng"
        remaining = p.limit - used                                     # "Còn lại"
        rows.append(dict(ticker=p.ticker, qty=p.qty, price=price, im_pct=p.im_pct,
                         limit=p.limit, value=g, imr=imr, im_dt_pct=k_pct,
                         imr_dt=imr_dt, used=used, remaining=remaining, im=im))

    total_value = sum(r["value"] for r in rows)
    imr_total = sum(r["imr"] for r in rows)
    imr_dt_total = sum(r["imr_dt"] for r in rows)
    nav = cash + total_value
    ee = nav - imr_total
    ee_dt = nav - imr_dt_total
    mr = nav / imr_total if imr_total > 0 else None
    mr_dt = nav / imr_dt_total if imr_dt_total > 0 else None

    if mr is None:
        status = "bình thường"
    elif mr < s.fs_threshold:
        status = "fs"
    elif mr < s.call_threshold:
        status = "call"
    else:
        status = "bình thường"

    call_amount = 0.0 if status == "bình thường" else (s.call_target - mr) * imr_total

    # Sức mua theo từng mã (cột B24:B26 trong file)
    for r in rows:
        r["buying_power"], r["max_qty"] = _buying_power(r, ee_dt, mm)

    # Bán giải chấp để đưa MR về mức mục tiêu: call / (im * mm) theo từng mã đang giữ
    for r in rows:
        if call_amount > 0 and r["qty"] > 0 and r["price"] > 0:
            denom = r["im"] * mm if r["im"] < 1 else 1.0
            val = call_amount / denom
            r["sell_value"] = val
            r["sell_qty"] = min(r["qty"], math.ceil(val / r["price"] / 100) * 100)
        else:
            r["sell_value"], r["sell_qty"] = 0.0, 0

    sell_by_im = {}
    if call_amount > 0:
        for im in s.sell_im_options:
            sell_by_im[im] = call_amount / im

    return dict(rows=rows, cash=cash, total_value=total_value, nav=nav,
                imr=imr_total, ee=ee, mr=mr,
                imr_dt=imr_dt_total, ee_dt=ee_dt, mr_dt=mr_dt,
                status=status, call_amount=call_amount, mm=mm,
                sell_by_im=sell_by_im)


def _buying_power(r: dict, ee_dt: float, mm: float):
    """Sức mua: công thức cột B24:B26 trong file. Mã im>=100% thì không có đòn bẩy."""
    im = r["im"]
    k = r["im_dt_pct"] / 100
    if r["price"] <= 0:
        return 0.0, 0.0
    if im >= 1 or k >= 1:
        bp = ee_dt                      # file Excel báo #DIV/0! ở trường hợp này
    else:
        unconstrained = ee_dt / (mm * im)
        if unconstrained > r["remaining"] / (1 - k):
            bp = ee_dt + r["remaining"]
        else:
            bp = unconstrained
    # sức mua âm vẫn hiển thị (EE DT âm = đã vượt mức ký quỹ); SL mua tối đa thì không âm
    return bp, max(0.0, bp) / r["price"]


def max_drop_before_call(cash: float, positions: list[Position], mm: float,
                         s: Settings | None = None) -> float | None:
    """Mức giảm giá đồng loạt (0..0.95) làm MR chạm ngưỡng call. 0 nếu đã chạm."""
    s = s or Settings()

    def below(shock):
        res = compute(cash, positions, mm, s, shock=-shock)
        return res["status"] != "bình thường"

    if below(0):
        return 0.0
    if not below(0.95):
        return None
    lo, hi = 0.0, 0.95
    for _ in range(40):
        mid = (lo + hi) / 2
        if below(mid):
            hi = mid
        else:
            lo = mid
    return hi


def deposit_for_target(cash: float, positions: list[Position], mm: float,
                       target_mr: float, s: Settings | None = None) -> dict:
    """Tiền cần nộp thêm để MR đạt target_mr. Nộp tiền chỉ tăng NAV, không đổi IMR."""
    base = compute(cash, positions, mm, s)
    imr = base["imr"]
    need = max(0.0, target_mr * imr - base["nav"]) if imr > 0 else 0.0
    after = compute(cash, positions, mm, s, deposit=need)
    return dict(need=need, before=base, after=after)


def sell_and_withdraw(cash: float, positions: list[Position], mm: float, ticker: str,
                      qty: float, sale_price: float, fee_pct: float = 0.0,
                      s: Settings | None = None) -> dict:
    """Bán `qty` cổ phiếu `ticker` ở giá KH đưa, trả về tiền có thể rút sau bán.

    Tiền rút tối đa = thừa ký quỹ EE sau bán (EE = NAV − IMR, giống điều kiện sức mua).
    Giá thị trường của phần còn lại giữ nguyên.
    """
    held = next((p for p in positions if p.ticker == ticker), None)
    if held is None:
        raise ValueError("KH không giữ mã này")
    qty = min(max(qty, 0), held.qty)
    proceeds = qty * sale_price * (1 - fee_pct / 100)
    new_pos = [Position(p.ticker, p.qty - qty if p.ticker == ticker else p.qty, p.price,
                        p.im_pct, p.limit, p.limit_custom) for p in positions]
    before = compute(cash, positions, mm, s)
    after = compute(cash + proceeds, new_pos, mm, s)
    return dict(qty=qty, proceeds=proceeds, before=before, after=after,
                withdraw=max(0.0, after["ee_dt"]))


def qty_to_withdraw(cash: float, positions: list[Position], mm: float, ticker: str,
                    sale_price: float, amount: float, fee_pct: float = 0.0,
                    lot: int = 100, s: Settings | None = None) -> dict | None:
    """Số lượng tối thiểu (làm tròn lô) cần bán để rút được `amount`. None nếu bán hết vẫn không đủ."""
    held = next((p for p in positions if p.ticker == ticker), None)
    if held is None:
        return None
    max_lots = int(held.qty // lot)
    if sell_and_withdraw(cash, positions, mm, ticker, max_lots * lot, sale_price, fee_pct, s)["withdraw"] < amount:
        if held.qty % lot and sell_and_withdraw(cash, positions, mm, ticker, held.qty, sale_price, fee_pct, s)["withdraw"] >= amount:
            return sell_and_withdraw(cash, positions, mm, ticker, held.qty, sale_price, fee_pct, s)
        return None
    lo, hi = 0, max_lots
    while lo < hi:
        mid = (lo + hi) // 2
        if sell_and_withdraw(cash, positions, mm, ticker, mid * lot, sale_price, fee_pct, s)["withdraw"] >= amount:
            hi = mid
        else:
            lo = mid + 1
    return sell_and_withdraw(cash, positions, mm, ticker, lo * lot, sale_price, fee_pct, s)


def _apply_sale(cash, positions, ticker, qty, price, fee_pct):
    proceeds = qty * price * (1 - fee_pct / 100)
    new_pos = [Position(p.ticker, p.qty - qty if p.ticker == ticker else p.qty, p.price,
                        p.im_pct, p.limit, p.limit_custom) for p in positions]
    return cash + proceeds, new_pos, proceeds


def plan_withdraw(cash: float, positions: list[Position], mm: float, amount: float,
                  sale_prices: dict, fee_pct: float = 0.0, lot: int = 100,
                  s: Settings | None = None, only: set | None = None) -> dict:
    """Danh mục nhiều mã: bán mã nào để rút `amount` với ít SLCP nhất.

    Mỗi bước: thử từng mã (giá bán trong sale_prices, mặc định giá thị trường) xem bán RIÊNG mã đó
    có đủ rút không; chọn mã cần ÍT SLCP nhất. Nếu không mã nào đủ một mình thì bán hết mã có giá trị
    bán lớn nhất rồi xét tiếp với phần còn lại.
    """
    cur_cash, cur_pos = cash, [Position(p.ticker, p.qty, p.price, p.im_pct, p.limit, p.limit_custom)
                               for p in positions]
    steps, options = [], []
    for step_no in range(len(positions) + 1):
        cur = compute(cur_cash, cur_pos, mm, s)
        if cur["ee_dt"] >= amount:
            break
        cands = []
        for p in cur_pos:
            if p.qty <= 0 or (only and p.ticker not in only):
                continue
            px = sale_prices.get(p.ticker, p.price)
            o = qty_to_withdraw(cur_cash, cur_pos, mm, p.ticker, px, amount, fee_pct, lot, s)
            cands.append(dict(ticker=p.ticker, price=px, held=p.qty, qty=o["qty"] if o else None,
                              value=o["qty"] * px if o else None, plan=o))
        if step_no == 0:
            options = cands
        ok = [c for c in cands if c["qty"] is not None]
        if ok:
            best = min(ok, key=lambda c: (c["qty"], c["value"]))
            qty, tk, px = best["qty"], best["ticker"], best["price"]
            full = False
        else:
            live = [c for c in cands]
            if not live:
                break
            best = max(live, key=lambda c: c["held"] * c["price"])
            qty, tk, px = best["held"], best["ticker"], best["price"]
            full = True
        cur_cash, cur_pos, proceeds = _apply_sale(cur_cash, cur_pos, tk, qty, px, fee_pct)
        steps.append(dict(ticker=tk, qty=qty, price=px, value=qty * px, proceeds=proceeds, sell_all=full))
        if not full:
            break
    final = compute(cur_cash, cur_pos, mm, s)
    return dict(steps=steps, options=options, before=compute(cash, positions, mm, s),
                final=final, ok=final["ee_dt"] >= amount)

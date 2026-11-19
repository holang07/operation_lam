"""Công cụ tính nhiều tài khoản: mua tối đa khi nộp tiền, chia vol nhận cổ phiếu, rút tiền / bán hết một mã.

Dùng chung lõi core.margin (EE DT = NAV − IMR DT, IM DT = IM × tỷ lệ tài khoản).
"account" ở đây là dict: name, acct (6 số cuối STK), cash, mm, positions (list[Position]).
Quy tắc đã chốt với người dùng:
- Hạn mức mã còn lại ≤ 0 thì sức mua mã đó = 0.
- Chọn tk để nộp: tk có sức mua dương (EE DT > 0) và hạn mức còn lại của mã lớn nhất; người dùng được đổi.
- Rút tiền nhiều tk: tổng SLCP bán ít nhất.
"""
from __future__ import annotations

import math

from .margin import Position, Settings, _apply_sale, compute, qty_to_withdraw, sell_and_withdraw


def acct_from(cu: dict, default_mm: float) -> dict:
    no = (cu.get("account_no") or "")
    return dict(name=cu["name"], acct=no[-6:] if no else "", cash=cu["cash"],
                mm=cu.get("mm") or default_mm, positions=cu["positions"])


def _with_ticker(positions: list[Position], ticker: str, price: float, im_pct: float, limit: float) -> list[Position]:
    out, found = [], False
    for p in positions:
        if p.ticker == ticker:
            out.append(Position(p.ticker, p.qty, price, p.im_pct, p.limit, p.limit_custom))
            found = True
        else:
            out.append(p)
    if not found:
        out.append(Position(ticker, 0, price, im_pct, limit))
    return out


def buy_capacity(acc: dict, ticker: str, price: float, im_pct: float, limit: float,
                 deposit: float = 0.0, lot: int = 100, s: Settings | None = None,
                 cash: float | None = None, positions: list[Position] | None = None) -> dict:
    """Sức mua mã `ticker` sau khi nộp `deposit`. Hạn mức mã còn lại ≤ 0 thì sức mua = 0."""
    cash0 = acc["cash"] if cash is None else cash
    pos = _with_ticker(positions if positions is not None else acc["positions"], ticker, price, im_pct, limit)
    r = compute(cash0, pos, acc["mm"], s, deposit=deposit)
    row = next(x for x in r["rows"] if x["ticker"] == ticker)
    bp = row["buying_power"] if row["remaining"] > 0 else min(row["buying_power"], 0.0)
    qty = math.floor(max(bp, 0.0) / price / lot) * lot if price > 0 else 0
    value = qty * price
    debt_after = max(0.0, -(cash0 + deposit - value))
    return dict(qty=qty, value=value, bp=bp, remaining=row["remaining"], ee_dt=r["ee_dt"],
                debt_after=debt_after, hm_out=row["remaining"] <= 0, k=row["im_dt_pct"] / 100)


def deposit_for_qty(acc: dict, ticker: str, price: float, im_pct: float, limit: float, qty: float,
                    lot: int = 100, s: Settings | None = None) -> float | None:
    """Tiền nộp tối thiểu để mua được `qty`. None nếu hạn mức mã không cho mua."""
    target = qty * price

    def ok(d):
        return buy_capacity(acc, ticker, price, im_pct, limit, d, lot, s)["qty"] >= qty

    hi = target
    if not ok(hi):
        return None
    lo = 0.0
    if ok(0):
        return 0.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if ok(mid):
            hi = mid
        else:
            lo = mid
    return hi


def round_up(x: float, step: float) -> float:
    return math.ceil(x / step - 1e-9) * step if step > 0 else x


def alloc_buy(accounts: list[dict], ticker: str, price: float, im_pct: float, limit: float,
              target_qty: float, step: float = 500_000_000, lot: int = 100, s: Settings | None = None) -> dict:
    """Nhận về `target_qty` cổ phiếu: chia vol theo thứ tự tk (đã xếp), mỗi tk tối đa theo hạn mức mã còn lại.

    Mỗi tk nhận tối đa q_hm = hạn mức còn lại / ((1 − IM DT) × giá) cổ phiếu có vay; phần còn lại nộp tiền.
    Tiền nộp làm tròn LÊN theo `step`, rồi tính lại số mua tối đa với tiền nộp đó.
    """
    left, lines = target_qty, []
    for a in accounts:
        if left <= 0:
            break
        base = buy_capacity(a, ticker, price, im_pct, limit, 0.0, lot, s)
        if base["hm_out"]:
            continue
        k = max(base["k"], 1e-9)
        q_hm = base["remaining"] / ((1 - k) * price) if k < 1 else float("inf")
        q = min(left, max(lot, math.floor(q_hm / lot) * lot))
        d = deposit_for_qty(a, ticker, price, im_pct, limit, q, lot, s)
        if d is None:
            continue
        dep = round_up(d, step)
        cap = buy_capacity(a, ticker, price, im_pct, limit, dep, lot, s)
        got = min(cap["qty"], q) if cap["qty"] >= q else cap["qty"]
        got = got if got else 0
        lines.append(dict(acc=a, deposit=dep, qty=got, value=got * price,
                          debt_after=max(0.0, -(a["cash"] + dep - got * price))))
        left -= got
    return dict(lines=lines, missing=max(0.0, left))


def suggest_accounts(accounts: list[dict], ticker: str, price: float, im_pct: float, limit: float,
                     lot: int = 100, s: Settings | None = None) -> list[dict]:
    """Tk đủ điều kiện (sức mua dương, mã còn hạn mức), xếp theo hạn mức còn lại giảm dần."""
    out = []
    for a in accounts:
        c = buy_capacity(a, ticker, price, im_pct, limit, 0.0, lot, s)
        if c["ee_dt"] > 0 and not c["hm_out"]:
            out.append((c["remaining"], a))
    return [a for _, a in sorted(out, key=lambda x: -x[0])]


def sell_buy_table(accounts: list[dict], sell_ticker: str, sell_price: float, sell_qty: dict,
                   buy_ticker: str | None, buy_price: float, buy_im: float, buy_limit: float,
                   want_qty: dict | None = None, fee_pct: float = 0.0, lot: int = 100,
                   s: Settings | None = None) -> list[dict]:
    """Bán `sell_qty[nhãn tk]` cổ phiếu `sell_ticker`: rút được bao nhiêu, mua tối đa bao nhiêu `buy_ticker`,
    và nếu muốn nhận `want_qty` cổ phiếu mã mua thì cần nộp thêm bao nhiêu."""
    rows = []
    for a in accounts:
        lb = f"{a['acct']} - {a['name']}"
        held = next((p for p in a["positions"] if p.ticker == sell_ticker and p.qty > 0), None)
        if held is None:
            continue
        q = min(max(float(sell_qty.get(lb, held.qty)), 0.0), held.qty)
        o = sell_and_withdraw(a["cash"], a["positions"], a["mm"], sell_ticker, q, sell_price, fee_pct, s)
        cash2, pos2, _ = _apply_sale(a["cash"], a["positions"], sell_ticker, q, sell_price, fee_pct)
        acc2 = dict(a, cash=cash2, positions=pos2)
        buy = want = None
        if buy_ticker:
            buy = buy_capacity(acc2, buy_ticker, buy_price, buy_im, buy_limit, 0.0, lot, s)
            w = float((want_qty or {}).get(lb, 0) or 0)
            if w > 0:
                d = deposit_for_qty(acc2, buy_ticker, buy_price, buy_im, buy_limit, w, lot, s)
                want = dict(qty=w, deposit=d, debt_after=None if d is None else max(0.0, -(cash2 + d - w * buy_price)))
        rows.append(dict(acc=a, label=lb, held=held.qty, qty=q, proceeds=o["proceeds"], withdraw=o["withdraw"],
                         buy=buy, want=want))
    return rows


def alloc_withdraw(accounts: list[dict], tickers: list[str], prices: dict, amount: float,
                   fee_pct: float = 0.0, lot: int = 100, use_free_ee: bool = False,
                   one_account: bool = False, s: Settings | None = None) -> dict:
    """Rút tổng `amount`: bán mã có TỈ LỆ KÝ QUỸ (IM) THẤP trước.

    Lý do: IM thấp thì cho vay nhiều, mỗi cổ phiếu bán giải phóng nhiều ký quỹ, SLCP bán ít mà rút được nhiều.
    - Xếp các (tk, mã) theo IM tăng dần (cùng IM thì tk giữ mã giá trị lớn hơn trước).
    - Bán dần: nếu (tk, mã) đủ phần còn lại thì bán vừa đủ rồi dừng, nếu không thì bán hết rồi sang (tk, mã) kế.
    - one_account=True (không chia nhiều tk): xong hẳn một tk (bán hết các mã IM thấp → cao) mới sang tk khác;
      tk xếp theo IM thấp nhất mà tk đang giữ, rồi theo khả năng rút lớn hơn.
    """
    state = {}
    for a in accounts:
        key = a["acct"] + a["name"]
        state[key] = dict(acc=a, cash=a["cash"], pos=list(a["positions"]), sales=[], w=0.0,
                          cap=_acct_cap(a, tickers, prices, fee_pct, s))
    left = amount

    def used_free(st):
        return compute(st["cash"], st["pos"], st["acc"]["mm"], s)["ee_dt"]

    if use_free_ee:
        for st in state.values():
            e = used_free(st)
            if e > 0 and left > 0:
                w = min(e, left)
                st["w"] += w
                st["cash"] -= w
                left -= w

    def pairs_of(st):
        out = []
        for p in st["pos"]:
            if p.ticker in tickers and p.qty > 0 and prices.get(p.ticker, 0) > 0:
                out.append((p.im_pct, -p.qty * prices[p.ticker], p.ticker))
        return sorted(out)

    if one_account:
        order = sorted((st for st in state.values() if st["cap"] > 0 or st["w"] > 0),
                       key=lambda st: ((pairs_of(st) or [(999,)])[0][0], -st["cap"]))
        seq = [(st, t_) for st in order for _, _, t_ in pairs_of(st)]
    else:
        allp = [(im, v, key, t_) for key, st in state.items() if st["cap"] > 0
                for im, v, t_ in pairs_of(st)]
        seq = [(state[key], t_) for _, _, key, t_ in sorted(allp, key=lambda x: (x[0], x[1]))]

    for st, tk in seq:
        if left <= 0.5:
            break
        px = prices[tk]
        held = next((p for p in st["pos"] if p.ticker == tk and p.qty > 0), None)
        if held is None:
            continue
        o = qty_to_withdraw(st["cash"], st["pos"], st["acc"]["mm"], tk, px, left, fee_pct, lot, s)
        if o is not None:
            q, inc = o["qty"], left
        else:
            q = held.qty
            full = sell_and_withdraw(st["cash"], st["pos"], st["acc"]["mm"], tk, q, px, fee_pct, s)
            inc = full["withdraw"]
        st["cash"], st["pos"], _ = _apply_sale(st["cash"], st["pos"], tk, q, px, fee_pct)
        if q > 0:
            st["sales"].append((tk, q, px))
        st["cash"] -= inc
        st["w"] += inc
        left -= inc

    lines = [dict(acc=st["acc"], sales=st["sales"], withdraw=st["w"]) for st in state.values() if st["w"] > 0.5]
    return dict(lines=lines, missing=max(0.0, left))


# ------------------------------------------------------------------ cú pháp trả lời mẫu
def _ty(x: float, nd: int = 1) -> str:
    v = round(x / 1e9, nd)
    return f"{v:.{nd}f}".rstrip("0").rstrip(".") if nd else f"{v:.0f}"


def _tr(q: float) -> str:
    return f"{round(q / 1e6, 1):.1f}".rstrip("0").rstrip(".") if q >= 1e6 else f"{q/1e3:,.0f}k"


def _px(p: float) -> str:
    return f"{p/1000:g}"


def _id(a: dict) -> str:
    return f"{a['acct']} - {a['name']}".strip(" -")


def text_buy(lines: list[dict], ticker: str, price: float) -> str:
    """'801115 - Chung nộp 55 tỷ mua tối đa 7.4 triệu EIB 17.6 tương đương 130.3 tỷ, vay ~79 tỷ'"""
    out = []
    for l in lines:
        out.append(f"{_id(l['acc'])} nộp {_ty(l['deposit'])} tỷ mua tối đa {_tr(l['qty'])}"
                   f"{' triệu' if l['qty'] >= 1e6 else ''} {ticker} {_px(price)} tương đương {_ty(l['value'])} tỷ, "
                   f"vay ~{_ty(l['debt_after'], 0)} tỷ")
    if len(lines) > 1:
        td, tq, tv, tdebt = (sum(l[k] for l in lines) for k in ("deposit", "qty", "value", "debt_after"))
        out.append(f"Tổng: nộp {_ty(td)} tỷ mua tối đa {_tr(tq)}{' triệu' if tq >= 1e6 else ''} {ticker} {_px(price)} "
                   f"tương đương {_ty(tv)} tỷ, vay ~{_ty(tdebt, 0)} tỷ")
    return "\n".join(out)


def text_withdraw(lines: list[dict], ticker_default: str = "") -> str:
    """'123456 - Tên bán 300,000 ABC 77.3 -> rút được 6.6 tỷ' + 'Tổng rút: 20 tỷ'"""
    out = []
    for l in lines:
        sales = [x for x in l.get("sales", []) if x[1] > 0]
        if sales:
            sold = " + ".join(f"{q:,.0f} {tk} {_px(px)}" for tk, q, px in sales)
            out.append(f"{_id(l['acc'])} bán {sold} -> rút được {_ty(l['withdraw'], 2)} tỷ ({l['withdraw']:,.0f})")
        else:
            out.append(f"{_id(l['acc'])} không cần bán -> rút được {_ty(l['withdraw'], 2)} tỷ ({l['withdraw']:,.0f})")
    tot = sum(l['withdraw'] for l in lines)
    out.append(f"Tổng rút: {_ty(tot, 2)} tỷ ({tot:,.0f})")
    return "\n".join(out)


def text_sell_all(rows: list[dict], sell_ticker: str, price: float, buy_ticker: str | None, buy_price: float) -> str:
    out = []
    for r in rows:
        line = (f"{_id(r['acc'])} bán {r['qty']:,.0f} {sell_ticker} {_px(price)} "
                f"-> rút được {_ty(r['withdraw'], 2)} tỷ ({r['withdraw']:,.0f})")
        if r["buy"]:
            line += f" hoặc mua được {r['buy']['qty']:,.0f} {buy_ticker} {_px(buy_price)}"
        if r.get("want"):
            w = r["want"]
            if w["deposit"] is None:
                line += f"; nhận {w['qty']:,.0f} {buy_ticker}: hạn mức mã không đủ"
            elif w["deposit"] > 0:
                line += f"; nhận {w['qty']:,.0f} {buy_ticker}: cần nộp thêm {_ty(w['deposit'], 2)} tỷ ({w['deposit']:,.0f})"
            else:
                line += f"; nhận {w['qty']:,.0f} {buy_ticker}: không cần nộp thêm"
        out.append(line)
    tot = sum(r['withdraw'] for r in rows)
    out.append(f"Tổng rút: {_ty(tot, 2)} tỷ ({tot:,.0f})")
    return "\n".join(out)


def _acct_cap(a: dict, tickers: list[str], prices: dict, fee_pct: float, s) -> float:
    """Tiền rút tối đa của tk nếu bán hết các mã được phép."""
    cash, pos = a["cash"], a["positions"]
    for tk in tickers:
        held = next((p for p in pos if p.ticker == tk and p.qty > 0), None)
        px = prices.get(tk, 0)
        if held and px > 0:
            proceeds = held.qty * px * (1 - fee_pct / 100)
            cash += proceeds
            pos = [Position(p.ticker, 0 if p.ticker == tk else p.qty, p.price, p.im_pct, p.limit, p.limit_custom)
                   for p in pos]
    return max(0.0, compute(cash, pos, a["mm"], s)["ee_dt"])


def loan_price(vay_pct: float, ref_price: float) -> float:
    """Giá vay = tỉ lệ vay × giá tham chiếu, làm tròn xuống 100đ (HSC cho vay theo giá thị trường, không chặn)."""
    return math.floor(vay_pct / 100 * ref_price / 100 + 1e-9) * 100


def text_loan(ticker: str, lim_from: float, lim_to: float | None, vay_pct: float, ref_price: float) -> str:
    """Mẫu trả lời KH về mã cho vay:
    *HAH*
    Hạn mức/tk: 20,000,000,000 - 30,000,000,000
    Tỉ lệ vay: 61%
    Giá vay: 30,900 (= 61% * 50,700 - HSC cho vay theo giá thị trường, không chặn)
    """
    lim = f"{lim_from:,.0f}" + (f" - {lim_to:,.0f}" if lim_to and lim_to > lim_from else "")
    out = [f"*{ticker}*", f"Hạn mức/tk: {lim}", f"Tỉ lệ vay: {vay_pct:.0f}%"]
    if ref_price and ref_price > 0:
        out.append(f"Giá vay: {loan_price(vay_pct, ref_price):,.0f} (= {vay_pct:.0f}% * {ref_price:,.0f} - "
                   f"HSC cho vay theo giá thị trường, không chặn)")
    else:
        out.append("Giá vay: chưa có giá tham chiếu")
    return "\n".join(out)

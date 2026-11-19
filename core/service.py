"""Gom dữ liệu từ DB và tính margin cho tất cả KH."""
from __future__ import annotations

from dataclasses import replace

from . import db
from .margin import Position, Settings, compute


def settings() -> Settings:
    return Settings(
        fs_threshold=db.get_setting("fs_threshold", 0.40),
        call_threshold=db.get_setting("call_threshold", 0.50),
        call_target=db.get_setting("call_target", 0.505),
        default_mm=db.get_setting("default_mm", 0.60),
    )


def prices() -> dict[str, float]:
    with db.conn() as c:
        return {r["ticker"]: r["price"] for r in c.execute("SELECT ticker, price FROM prices")}


def load_customers() -> list[dict]:
    px = prices()
    out = []
    with db.conn() as c:
        for cu in c.execute("SELECT * FROM customers ORDER BY name"):
            pos = c.execute("SELECT * FROM positions WHERE customer_id=? ORDER BY id", (cu["id"],)).fetchall()
            out.append(dict(
                id=cu["id"], name=cu["name"], account_no=cu["account_no"], cash=cu["cash"],
                mm=cu["mm"], extra_watch=cu["extra_watch"], note=cu["note"], updated_at=cu["updated_at"],
                group_name=cu["group_name"] or "", cash_date=cu["cash_date"],
                positions=[Position(p["ticker"], p["qty"], px.get(p["ticker"], 0.0), p["im_pct"], p["limit_vnd"], bool(p["limit_custom"]))
                           for p in pos],
            ))
    return out


def compute_all(proposed: bool = False) -> list[dict]:
    """proposed=True: thay tỉ lệ ký quỹ bằng IM đề xuất (nếu danh mục cho vay có) để xem tác động."""
    s = settings()
    ll = db.get_loan_list() if proposed else {}
    res = []
    for cu in load_customers():
        mm = cu["mm"] or s.default_mm
        positions = cu["positions"]
        if proposed:
            positions = [replace(p, im_pct=ll[p.ticker]["im_proposed_pct"])
                         if p.ticker in ll and ll[p.ticker]["im_proposed_pct"] else p for p in positions]
        r = compute(cu["cash"], positions, mm, s)
        r.update(id=cu["id"], name=cu["name"], account_no=cu["account_no"], customer=cu)
        res.append(r)
    return res


def watchlist(customer: dict | None = None) -> set[str]:
    """Mã quan tâm: mã đang giữ + mã thêm tay. customer=None -> của tất cả KH."""
    custs = [customer] if customer else load_customers()
    tickers = set()
    for cu in custs:
        tickers |= {p.ticker for p in cu["positions"]}
        tickers |= {t.strip().upper() for t in (cu["extra_watch"] or "").split(",") if t.strip()}
    return tickers


STATUS_LABEL = {"fs": "FS (bán giải chấp)", "call": "Call", "bình thường": "Bình thường"}
STATUS_ICON = {"fs": "🔴", "call": "🟠", "bình thường": "🟢"}


def acct_label(name, acct) -> str:
    """Tên hiển thị thống nhất: '810918 - Cường' (thiếu một phần thì hiện phần còn lại)."""
    name, acct = (name or "").strip(), (acct or "").strip()
    acct = acct[-6:] if len(acct) > 6 else acct  # 011C123456 -> 123456
    if name and acct and name != acct:
        return f"{acct} - {name}"
    return acct or name


def label_map() -> dict:
    """{tên KH trong dữ liệu: 'số TK - tên'} để hiển thị; khóa nội bộ vẫn là tên."""
    return {c["name"]: acct_label(c["name"], c["account_no"]) for c in load_customers()}


def fmt_vnd(x) -> str:
    if x is None:
        return "-"
    return f"{x:,.0f}"


def fmt_pct(x) -> str:
    return "-" if x is None else f"{x*100:.1f}%"

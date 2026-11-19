"""Lưu trữ SQLite: một file duy nhất data/workspace.db trên máy bạn."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .templates import DEFAULT_PROCEDURES

import os

# Mặc định: data/workspace.db. Đặt biến môi trường OMS_DB để dùng file dữ liệu khác (VD: bản demo để chia sẻ).
DB_PATH = Path(os.environ.get("OMS_DB") or Path(__file__).resolve().parents[1] / "data" / "workspace.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  account_no TEXT DEFAULT '',
  cash REAL DEFAULT 0,
  mm REAL,
  extra_watch TEXT DEFAULT '',
  note TEXT DEFAULT '',
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS kh_directory(
  account_no TEXT PRIMARY KEY,
  acct TEXT NOT NULL,
  full_name TEXT,
  short_name TEXT,
  grp TEXT
);
CREATE TABLE IF NOT EXISTS nav_history(
  day TEXT NOT NULL,
  acct TEXT NOT NULL,
  name TEXT,
  nav REAL,
  cash REAL,
  gttt REAL,
  source TEXT,
  updated_at TEXT,
  PRIMARY KEY(day, acct)
);
CREATE TABLE IF NOT EXISTS tasks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  note TEXT DEFAULT '',
  scope TEXT DEFAULT 'Chung',      -- Chung | Nhóm | KH
  target TEXT DEFAULT '',          -- tên nhóm hoặc tên KH (khóa nội bộ)
  priority TEXT DEFAULT 'Thường',  -- Cao | Thường | Thấp
  due TEXT DEFAULT '',             -- yyyy-mm-dd hoặc rỗng
  status TEXT DEFAULT 'Chưa làm',  -- Chưa làm | Đang làm | Chờ KH | Xong
  created_at TEXT, updated_at TEXT, done_at TEXT
);
CREATE TABLE IF NOT EXISTS archive_files(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  category TEXT DEFAULT '',
  note TEXT DEFAULT '',
  filename TEXT NOT NULL,
  stored TEXT NOT NULL,
  size INTEGER DEFAULT 0,
  uploaded_at TEXT
);
CREATE TABLE IF NOT EXISTS archive_replies(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  category TEXT DEFAULT '',
  channel TEXT DEFAULT 'Email',
  to_addr TEXT DEFAULT '',
  cc_addr TEXT DEFAULT '',
  subject TEXT DEFAULT '',
  body TEXT DEFAULT '',
  note TEXT DEFAULT '',
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS positions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  ticker TEXT NOT NULL,
  qty REAL DEFAULT 0,
  im_pct REAL DEFAULT 100,
  limit_vnd REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS loan_list(
  ticker TEXT PRIMARY KEY,
  im_pct REAL NOT NULL,
  limit_vnd REAL DEFAULT 0,
  im_proposed_pct REAL,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS prices(
  ticker TEXT PRIMARY KEY,
  price REAL NOT NULL,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
  customer_name TEXT,
  ticker TEXT, side TEXT, qty REAL, price REAL,
  order_type TEXT, session TEXT, channel TEXT,
  status TEXT DEFAULT 'Chờ đặt',
  note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS procedures(
  key TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  config TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cases(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  procedure_key TEXT NOT NULL,
  customer_name TEXT,
  data TEXT NOT NULL,
  status TEXT DEFAULT 'Đang chờ KH',
  note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS snapshots(
  day TEXT NOT NULL,
  customer_id INTEGER NOT NULL,
  cash REAL, nav REAL, mr REAL, status TEXT,
  data TEXT,
  created_at TEXT,
  PRIMARY KEY(day, customer_id)
);
CREATE TABLE IF NOT EXISTS report_log(
  day TEXT NOT NULL,
  customer_id INTEGER NOT NULL,
  status TEXT DEFAULT 'Chưa gửi',
  sent_at TEXT,
  PRIMARY KEY(day, customer_id)
);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS feeds(url TEXT PRIMARY KEY, name TEXT, enabled INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS news(
  link TEXT PRIMARY KEY,
  title TEXT, summary TEXT, source TEXT, published TEXT,
  tickers TEXT DEFAULT '', fetched_at TEXT,
  flagged INTEGER DEFAULT 0, seen INTEGER DEFAULT 0
);
"""

DEFAULT_FEEDS = [
    ("https://cafef.vn/thi-truong-chung-khoan.rss", "CafeF - Thị trường chứng khoán"),
    ("https://vietstock.vn/830/chung-khoan/co-phieu.rss", "Vietstock - Cổ phiếu"),
    ("https://vnexpress.net/rss/kinh-doanh.rss", "VnExpress - Kinh doanh"),
    ("https://vneconomy.vn/chung-khoan.rss", "VnEconomy - Chứng khoán"),
    ("https://vneconomy.vn/tai-chinh.rss", "VnEconomy - Tài chính"),
    ("https://vneconomy.vn/nhip-cau-doanh-nghiep.rss", "VnEconomy - Doanh nghiệp"),
]
# Nguồn thêm sau lần cài đầu: tự chèn một lần cho DB đã có sẵn (không chèn lại nếu bạn xóa đi)
FEEDS_V2 = DEFAULT_FEEDS[3:]


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def init() -> None:
    with conn() as c:
        c.executescript(SCHEMA)
        cols = [r["name"] for r in c.execute("PRAGMA table_info(positions)")]
        if "limit_custom" not in cols:
            c.execute("ALTER TABLE positions ADD COLUMN limit_custom INTEGER DEFAULT 0")
        ccols = [r["name"] for r in c.execute("PRAGMA table_info(customers)")]
        if "group_name" not in ccols:
            c.execute("ALTER TABLE customers ADD COLUMN group_name TEXT DEFAULT ''")
        if "cash_date" not in ccols:
            c.execute("ALTER TABLE customers ADD COLUMN cash_date TEXT")
        ncols = [r["name"] for r in c.execute("PRAGMA table_info(news)")]
        if "topics" not in ncols:
            c.execute("ALTER TABLE news ADD COLUMN topics TEXT DEFAULT ''")
        if c.execute("SELECT COUNT(*) FROM procedures").fetchone()[0] == 0:
            for key, proc in DEFAULT_PROCEDURES.items():
                c.execute("INSERT INTO procedures(key,name,config) VALUES(?,?,?)",
                          (key, proc["name"], json.dumps(proc, ensure_ascii=False)))
        if c.execute("SELECT COUNT(*) FROM feeds").fetchone()[0] == 0:
            c.executemany("INSERT INTO feeds(url,name) VALUES(?,?)", DEFAULT_FEEDS)
            c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('feeds_v2','1')")
        elif not c.execute("SELECT 1 FROM settings WHERE key='feeds_v2'").fetchone():
            c.executemany("INSERT OR IGNORE INTO feeds(url,name) VALUES(?,?)", FEEDS_V2)
            c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('feeds_v2','1')")


# ---------- cấu hình ----------
    seed_directory()


def get_setting(key: str, default: float) -> float:
    with conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return float(row["value"]) if row else default


def set_setting(key: str, value: float) -> None:
    with conn() as c:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


# ---------- import ----------
def import_customers(customers: list[dict], prices: dict) -> tuple[int, int]:
    """Thêm mới hoặc cập nhật KH theo tên; thay toàn bộ danh mục của KH đó."""
    ts = now()
    with conn() as c:
        for cu in customers:
            row = c.execute("SELECT id, extra_watch, note FROM customers WHERE name=?", (cu["name"],)).fetchone()
            if row:
                cid = row["id"]
                c.execute("UPDATE customers SET account_no=?, cash=?, mm=?, updated_at=? WHERE id=?",
                          (cu["account_no"], cu["cash"], cu["mm"], ts, cid))
                c.execute("DELETE FROM positions WHERE customer_id=?", (cid,))
            else:
                cur = c.execute("INSERT INTO customers(name,account_no,cash,mm,updated_at) VALUES(?,?,?,?,?)",
                                (cu["name"], cu["account_no"], cu["cash"], cu["mm"], ts))
                cid = cur.lastrowid
            ll = {r["ticker"]: r for r in c.execute("SELECT ticker, limit_vnd FROM loan_list")}
            c.executemany(
                "INSERT INTO positions(customer_id,ticker,qty,im_pct,limit_vnd,limit_custom) VALUES(?,?,?,?,?,?)",
                [(cid, p["ticker"], p["qty"], p["im_pct"], p["limit"],
                  int(p["ticker"] in ll and abs(ll[p["ticker"]]["limit_vnd"] - p["limit"]) > 1))
                 for p in cu["positions"]])
        for t, p in prices.items():
            c.execute("INSERT INTO prices(ticker,price,updated_at) VALUES(?,?,?) "
                      "ON CONFLICT(ticker) DO UPDATE SET price=excluded.price, updated_at=excluded.updated_at",
                      (t, p, ts))
    return len(customers), len(prices)


def adjust_cash(name: str, delta: float) -> bool:
    """Cộng (nộp, +) hoặc trừ (rút, −) tiền vào số dư của KH."""
    with conn() as c:
        r = c.execute("UPDATE customers SET cash = cash + ?, cash_date=?, updated_at=? WHERE name=?",
                      (float(delta), today(), now(), name))
        return r.rowcount > 0


def apply_ops(ops: list[dict]) -> int:
    """Ghi nhận giao dịch đã thực hiện. Mỗi op: name, ticker (hoặc None), dqty (+mua/−bán), dcash (+/− tiền),
    im, lim (VND) dùng khi mở vị thế mới. Mã về 0 cp thì bỏ khỏi danh mục KH."""
    n = 0
    with conn() as c:
        for o in ops:
            r = c.execute("SELECT id FROM customers WHERE name=?", (o["name"],)).fetchone()
            if not r:
                continue
            cid = r["id"]
            if o.get("dcash"):
                c.execute("UPDATE customers SET cash=cash+?, cash_date=?, updated_at=? WHERE id=?",
                          (float(o["dcash"]), today(), now(), cid))
            tk, dq = o.get("ticker"), float(o.get("dqty") or 0)
            if tk and o.get("price") and not c.execute("SELECT 1 FROM prices WHERE ticker=? AND price>0", (tk,)).fetchone():
                c.execute("INSERT INTO prices(ticker,price,updated_at) VALUES(?,?,?) "
                          "ON CONFLICT(ticker) DO UPDATE SET price=excluded.price, updated_at=excluded.updated_at",
                          (tk, float(o["price"]), now()))
            if tk and dq:
                p = c.execute("SELECT id, qty FROM positions WHERE customer_id=? AND ticker=?", (cid, tk)).fetchone()
                if p:
                    nq = p["qty"] + dq
                    if nq <= 0.5:
                        c.execute("DELETE FROM positions WHERE id=?", (p["id"],))
                    else:
                        c.execute("UPDATE positions SET qty=? WHERE id=?", (nq, p["id"]))
                elif dq > 0:
                    c.execute("INSERT INTO positions(customer_id,ticker,qty,im_pct,limit_vnd,limit_custom) VALUES(?,?,?,?,?,0)",
                              (cid, tk, dq, float(o.get("im") or 100), float(o.get("lim") or 0)))
                c.execute("UPDATE customers SET updated_at=? WHERE id=?", (now(), cid))
            n += 1
    return n


# ---------- danh mục cho vay ----------
def import_loan_list(items: dict, account_ratio: float | None = None) -> int:
    """Thay toàn bộ danh mục cho vay bằng dữ liệu mới."""
    ts = now()
    with conn() as c:
        c.execute("DELETE FROM loan_list")
        c.executemany("INSERT INTO loan_list(ticker,im_pct,limit_vnd,im_proposed_pct,updated_at) VALUES(?,?,?,?,?)",
                      [(t, v["im_pct"], v["limit"], v["im_proposed_pct"], ts) for t, v in items.items()])
        # đánh dấu lại hạn mức riêng của KH so với danh mục mới
        c.execute("""UPDATE positions SET limit_custom = CASE
                       WHEN EXISTS (SELECT 1 FROM loan_list l WHERE l.ticker=positions.ticker
                                    AND ABS(l.limit_vnd - positions.limit_vnd) > 1) THEN 1 ELSE 0 END""")
    if account_ratio:
        set_setting("default_mm", account_ratio)
    return len(items)


def get_loan_list() -> dict:
    with conn() as c:
        return {r["ticker"]: dict(r) for r in c.execute("SELECT * FROM loan_list")}


def sync_positions_with_list(apply: bool = False, customer_id: int | None = None) -> list[dict]:
    """So khớp (và áp dụng nếu apply=True) tỉ lệ ký quỹ/hạn mức của danh mục KH với danh mục cho vay.

    Hạn mức đã đánh dấu 'riêng KH' (limit_custom) được giữ nguyên.
    """
    diffs = []
    with conn() as c:
        ll = {r["ticker"]: r for r in c.execute("SELECT * FROM loan_list")}
        q = ("SELECT p.id, p.ticker, p.im_pct, p.limit_vnd, p.limit_custom, c.name FROM positions p "
             "JOIN customers c ON c.id=p.customer_id")
        args = ()
        if customer_id:
            q += " WHERE c.id=?"
            args = (customer_id,)
        for p in c.execute(q, args).fetchall():
            l = ll.get(p["ticker"])
            new_im = l["im_pct"] if l else 100.0
            new_lim = (l["limit_vnd"] if l else 0.0) if not p["limit_custom"] else p["limit_vnd"]
            if abs(new_im - p["im_pct"]) > 1e-6 or abs(new_lim - p["limit_vnd"]) > 1:
                diffs.append(dict(id=p["id"], customer=p["name"], ticker=p["ticker"],
                                  im_old=p["im_pct"], im_new=new_im, limit_old=p["limit_vnd"], limit_new=new_lim,
                                  in_list=bool(l)))
                if apply:
                    c.execute("UPDATE positions SET im_pct=?, limit_vnd=? WHERE id=?", (new_im, new_lim, p["id"]))
    return diffs


# ---------- nhập liệu hằng ngày ----------
def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def save_cash(rows: list[dict]) -> int:
    """rows: [{id, cash, confirm}]. Lưu số dư; KH đổi số dư hoặc được xác nhận => đã cập nhật hôm nay."""
    n = 0
    with conn() as c:
        for r in rows:
            old = c.execute("SELECT cash FROM customers WHERE id=?", (r["id"],)).fetchone()
            changed = old is not None and abs((old["cash"] or 0) - r["cash"]) > 0.5
            if changed or r["confirm"]:
                c.execute("UPDATE customers SET cash=?, cash_date=?, updated_at=? WHERE id=?",
                          (r["cash"], today(), now(), r["id"]))
                n += 1
    return n


def replace_quantities(rows: list[tuple[str, str, float]]) -> tuple[int, int, int]:
    """rows: [(tên KH, mã, SL)]. Cập nhật SL, thêm mã mới (tỉ lệ/hạn mức lấy từ danh mục cho vay), xoá mã bị bỏ."""
    added = updated = removed = 0
    wanted: dict[str, dict[str, float]] = {}
    for name, t, q in rows:
        wanted.setdefault(name, {})[t.strip().upper()] = float(q or 0)
    with conn() as c:
        ll = {r["ticker"]: r for r in c.execute("SELECT * FROM loan_list")}
        for name, tickers in wanted.items():
            cu = c.execute("SELECT id FROM customers WHERE name=?", (name,)).fetchone()
            if not cu:
                continue
            cid = cu["id"]
            existing = {r["ticker"]: r for r in c.execute("SELECT * FROM positions WHERE customer_id=?", (cid,))}
            for t, q in tickers.items():
                if t in existing:
                    if abs(existing[t]["qty"] - q) > 1e-9:
                        c.execute("UPDATE positions SET qty=? WHERE id=?", (q, existing[t]["id"]))
                        updated += 1
                else:
                    l = ll.get(t)
                    c.execute("INSERT INTO positions(customer_id,ticker,qty,im_pct,limit_vnd,limit_custom) VALUES(?,?,?,?,?,0)",
                              (cid, t, q, l["im_pct"] if l else 100.0, l["limit_vnd"] if l else 0.0))
                    c.execute("INSERT OR IGNORE INTO prices(ticker,price,updated_at) VALUES(?,0,?)", (t, now()))
                    added += 1
            for t, r in existing.items():
                if t not in tickers:
                    c.execute("DELETE FROM positions WHERE id=?", (r["id"],))
                    removed += 1
    return added, updated, removed


def drop_customers_not_in(names: list[str]) -> list[str]:
    """Xoá KH không còn trong file (tên cũ/sheet đã bỏ). Trả về danh sách tên đã xoá."""
    removed = []
    with conn() as c:
        for r in c.execute("SELECT id, name FROM customers").fetchall():
            if r["name"] not in names:
                c.execute("DELETE FROM positions WHERE customer_id=?", (r["id"],))
                c.execute("DELETE FROM customers WHERE id=?", (r["id"],))
                removed.append(r["name"])
    return removed


# ---------- lịch sử NAV (dashboard) ----------
def acct_key(account_no, name) -> str:
    """Khóa tài khoản cho lịch sử: 6 số cuối của số tài khoản, thiếu thì dùng tên."""
    a = (account_no or "").strip()
    return a[-6:] if a else (name or "").strip()


def save_nav(day: str, acct: str, name: str, nav, cash=None, gttt=None, source: str = "") -> None:
    """Mỗi tài khoản một dòng mỗi ngày; lưu lại trong ngày thì ghi đè."""
    if nav is None:
        return
    with conn() as c:
        c.execute("INSERT INTO nav_history(day,acct,name,nav,cash,gttt,source,updated_at) VALUES(?,?,?,?,?,?,?,?) "
                  "ON CONFLICT(day,acct) DO UPDATE SET name=excluded.name, nav=excluded.nav, cash=excluded.cash, "
                  "gttt=excluded.gttt, source=excluded.source, updated_at=excluded.updated_at",
                  (day, acct, name, float(nav), None if cash is None else float(cash),
                   None if gttt is None else float(gttt), source, now()))


def nav_history() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM nav_history ORDER BY day, acct")]


# ---------- danh bạ KH (tra cứu số tài khoản -> tên, nhóm) ----------
def short_name(full: str) -> str:
    """Tên gọi ngắn: từ cuối của họ tên (Bùi Duy Cường -> Cường). Tài khoản tổ chức giữ nguyên tên đầy đủ."""
    f = (full or "").strip()
    if not f or f.lower().startswith(("công ty", "cty", "tổng công ty")):
        return f
    return f.split()[-1]


def import_directory(rows: list[dict]) -> int:
    """rows: dict có Số tài khoản, Tên khách hàng, Nhóm. Thêm mới hoặc cập nhật theo số tài khoản."""
    n = 0
    with conn() as c:
        for r in rows:
            no = str(r.get("Số tài khoản") or r.get("account_no") or "").strip()
            full = str(r.get("Tên khách hàng") or r.get("full_name") or "").strip()
            if not no:
                continue
            c.execute("INSERT INTO kh_directory(account_no,acct,full_name,short_name,grp) VALUES(?,?,?,?,?) "
                      "ON CONFLICT(account_no) DO UPDATE SET acct=excluded.acct, full_name=excluded.full_name, "
                      "short_name=excluded.short_name, grp=excluded.grp",
                      (no, no[-6:], full, short_name(full), str(r.get("Nhóm") or r.get("grp") or "").strip()))
            n += 1
    return n


def directory() -> dict:
    """{6 số cuối tài khoản: dict(account_no, full_name, short_name, grp)}"""
    with conn() as c:
        return {r["acct"]: dict(r) for r in c.execute("SELECT * FROM kh_directory")}


def seed_directory() -> None:
    """Lần đầu (bảng trống) nạp danh bạ từ data/kh_directory.csv nếu có."""
    import csv
    f = DB_PATH.parent / "kh_directory.csv"
    with conn() as c:
        empty = c.execute("SELECT COUNT(*) FROM kh_directory").fetchone()[0] == 0
    if empty and f.exists():
        with open(f, encoding="utf-8-sig", newline="") as fh:
            import_directory(list(csv.DictReader(fh)))


def get_text(key: str, default: str = "") -> str:
    with conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return str(row["value"]) if row else default


def set_text(key: str, value: str) -> None:
    with conn() as c:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, str(value)))


def set_group_for(names: list[str], group: str) -> None:
    """Gán nhóm cho các KH (dùng cho thư mục nhóm và task theo nhóm)."""
    with conn() as c:
        for n in names:
            c.execute("UPDATE customers SET group_name=? WHERE name=?", (group, n))


def delete_customers(names: list[str]) -> int:
    """Xóa KH (và danh mục) khỏi hệ thống. Lịch sử NAV và file đã lưu không bị đụng tới."""
    n = 0
    with conn() as c:
        for r in c.execute("SELECT id, name FROM customers").fetchall():
            if r["name"] in names:
                c.execute("DELETE FROM positions WHERE customer_id=?", (r["id"],))
                c.execute("DELETE FROM customers WHERE id=?", (r["id"],))
                n += 1
    return n

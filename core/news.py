"""Lấy tin từ RSS, gắn mã chứng khoán, lọc theo danh mục KH quan tâm."""
from __future__ import annotations

import calendar
import re
import socket
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from urllib.parse import urljoin, urlparse
from datetime import datetime

import feedparser

from . import db

_TICKER = re.compile(r"(?<![A-Za-z0-9])([A-Z]{3,4})(?![A-Za-z0-9])")
_TAGS = re.compile(r"<[^>]+>")


# ---- Mã bắt buộc phải có tin (luôn tìm, dù không nằm trong danh mục cho vay) ----
PRIORITY = {
    "MWG": ["Thế giới Di động"], "DMX": ["Điện máy Xanh"], "VSC": ["Viconship"], "GMD": ["Gemadept"],
    "HAH": ["Hải An"], "EIB": ["Eximbank"], "GEX": ["Gelex"], "GEL": ["Gelex Electric"],
    "MSB": ["Hàng Hải"], "VIX": ["Chứng khoán VIX"], "PDR": ["Phát Đạt"], "NKG": ["Nam Kim"],
}

# ---- Ngành bán lẻ: tập mã chính (tin của các mã này tự gắn chủ đề "Bán lẻ") ----
RETAIL = {
    "VNM": ["Vinamilk"], "PNJ": ["Phú Nhuận Jewelry", "PNJ"], "PET": ["Petrosetco"],
    "MWG": ["Thế giới Di động"], "MSN": ["Masan"], "MCH": ["Masan Consumer", "Hàng tiêu dùng Masan"],
    "FRT": ["FPT Retail", "Long Châu"], "DMX": ["Điện máy Xanh"], "DGW": ["Digiworld"],
}
ALIASES = {**RETAIL, **PRIORITY}

# ---- Chủ đề vĩ mô / ngành: tìm theo từ khóa ----
TOPIC_KEYWORDS = {
    "Vĩ mô": ["vĩ mô", "gdp", "lạm phát", "cpi", "lãi suất", "tỷ giá", "ngân hàng nhà nước", "nhnn", "fed",
              "tăng trưởng kinh tế", "xuất khẩu", "nhập khẩu", "fdi", "đầu tư công", "chính sách tiền tệ",
              "trái phiếu chính phủ", "tín dụng", "thuế quan"],
    "BĐS": ["bất động sản", "bđs", "căn hộ", "chung cư", "đất nền", "nhà ở xã hội", "luật đất đai",
            "địa ốc", "khu đô thị", "dự án nhà ở"],
    "Bán lẻ": ["bán lẻ", "siêu thị", "chuỗi cửa hàng", "tiêu dùng", "thương mại điện tử", "điện máy",
               "thế giới di động", "bách hóa xanh", "retail", "vinamilk", "masan", "long châu", "digiworld"],
    "Thép": ["thép", "hòa phát", "hoà phát", "phôi thép", "quặng sắt", "than cốc", "hrc", "tôn mạ"],
}
TOPIC_QUERY = {"Vĩ mô": "kinh tế vĩ mô Việt Nam", "BĐS": "bất động sản", "Bán lẻ": "ngành bán lẻ Việt Nam",
               "Thép": "ngành thép"}
_TOPIC_RE = {k: re.compile("|".join(r"(?<!\w)" + re.escape(w) + r"(?!\w)" for w in v)) for k, v in TOPIC_KEYWORDS.items()}


def extract_topics(text: str) -> list[str]:
    low = (text or "").lower()
    return [k for k, rx in _TOPIC_RE.items() if rx.search(low)]


def _pub(e) -> str:
    """Giờ đăng theo giờ máy (feedparser trả UTC)."""
    if e.get("published_parsed"):
        return datetime.fromtimestamp(calendar.timegm(e.published_parsed)).strftime("%Y-%m-%d %H:%M")
    return ""


def _gnews_url(q: str) -> str:
    return f"https://news.google.com/rss/search?q={quote(q + ' when:7d')}&hl=vi&gl=VN&ceid=VN:vi"


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", _TAGS.sub(" ", s or "")).strip()


def extract_tickers(text: str, universe: set[str]) -> list[str]:
    return sorted({m for m in _TICKER.findall(text) if m in universe})


def test_feed(url: str) -> tuple[bool, str]:
    socket.setdefaulttimeout(10)
    d = feedparser.parse(url)
    if d.entries:
        return True, f"OK - {len(d.entries)} bài"
    err = getattr(d, "bozo_exception", None)
    return False, f"Không đọc được ({err or 'feed rỗng'})"


def _parse(url: str):
    return feedparser.parse(url)


def fetch_all(universe: set[str]) -> tuple[int, list[str]]:
    """Tải tin: (1) các nguồn RSS đang bật, (2) Google News theo từng mã bắt buộc + mã trong danh mục,
    (3) Google News theo chủ đề vĩ mô / BĐS / bán lẻ / thép. Trả về (số bài mới, danh sách cảnh báo)."""
    socket.setdefaulttimeout(15)
    universe = set(universe) | set(PRIORITY) | set(RETAIL)
    new, errors = 0, []

    with db.conn() as c:
        feeds = c.execute("SELECT url, name FROM feeds WHERE enabled=1").fetchall()

    # danh sách việc cần tải: (loại, khóa, tên nguồn, url)
    jobs = [("feed", None, f["name"], f["url"]) for f in feeds]
    for tk, alias in ALIASES.items():
        q = f'{tk} OR "{alias[0]}" cổ phiếu'
        jobs.append(("ticker", tk, f"Google News ({tk})", _gnews_url(q)))
    for tk in sorted(universe - set(ALIASES)):
        jobs.append(("ticker", tk, f"Google News ({tk})", _gnews_url(f'"{tk}" cổ phiếu')))
    for tp, q in TOPIC_QUERY.items():
        jobs.append(("topic", tp, f"Google News ({tp})", _gnews_url(q)))

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda j: _parse(j[3]), jobs))

    got = {tk: 0 for tk in ALIASES}
    failed: list[str] = []
    with db.conn() as c:
        for (kind, key, name, _url), d in zip(jobs, results):
            if not d.entries:
                if kind != "ticker" or key in ALIASES:
                    failed.append(name)
                continue
            for e in d.entries[: (30 if kind == "feed" else 15)]:
                link = e.get("link")
                if not link:
                    continue
                title = _clean(e.get("title", ""))
                summary = _clean(e.get("summary", ""))
                text = f"{title} {summary}"
                tks = set(extract_tickers(text, universe))
                if kind == "ticker":
                    aliases = ALIASES.get(key, [])
                    if key in text or any(a.lower() in text.lower() for a in aliases) or key not in ALIASES:
                        tks.add(key)
                    else:
                        continue  # kết quả tìm kiếm không thật sự nhắc tới mã
                tps = set(extract_topics(text))
                if tks & set(RETAIL):
                    tps.add("Bán lẻ")
                if kind == "topic":
                    tps.add(key)
                src = (e.get("source") or {}).get("title") if kind != "feed" else None
                cur = c.execute(
                    "INSERT OR IGNORE INTO news(link,title,summary,source,published,tickers,topics,fetched_at) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (link, title, summary[:500], src or name, _pub(e), ",".join(sorted(tks)),
                     ",".join(sorted(tps)), db.now()))
                new += cur.rowcount
                if kind == "ticker" and key in got and cur.rowcount:
                    got[key] += 1
    if failed:
        errors.append(f"{len(failed)} nguồn không trả tin (rỗng hoặc lỗi mạng): " + "; ".join(failed))
    miss = [k for k, v in got.items() if v == 0]
    if miss:
        errors.append("Mã chưa có tin mới (có thể đã có từ trước hoặc không có bài trong 7 ngày): " + ", ".join(miss))
    return new, errors


def retag(universe: set[str]) -> None:
    """Gắn lại mã và chủ đề cho tin đã lưu (khi danh mục thay đổi)."""
    universe = set(universe) | set(PRIORITY) | set(RETAIL)
    with db.conn() as c:
        for r in c.execute("SELECT link, title, summary, tickers, topics FROM news").fetchall():
            text = f"{r['title']} {r['summary']}"
            tks = set(extract_tickers(text, universe)) | set(filter(None, (r["tickers"] or "").split(",")))
            tks = {x for x in tks if x in universe}
            tps = set(extract_topics(text)) | set(filter(None, (r["topics"] or "").split(",")))
            if tks & set(RETAIL):
                tps.add("Bán lẻ")
            c.execute("UPDATE news SET tickers=?, topics=? WHERE link=?",
                      (",".join(sorted(tks)), ",".join(sorted(tps)), r["link"]))


_LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
_ATTR = re.compile(r'([a-zA-Z\-:]+)\s*=\s*["\']([^"\']*)["\']')
_COMMON = ["/rss", "/rss.html", "/rss.xml", "/feed", "/feed.xml", "/rss/home.rss", "/rss/chung-khoan.rss",
           "/chung-khoan.rss", "/rss/thi-truong-chung-khoan.rss", "/thi-truong-chung-khoan.rss",
           "/rss/tai-chinh-chung-khoan.rss"]


def _get(url: str, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; WorkspaceBroker)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(600_000).decode("utf-8", "ignore")


def discover_feeds(site_url: str, max_probe: int = 25) -> list[tuple[str, str]]:
    """Tìm RSS của một trang: đọc thẻ <link rel=alternate>, các link .rss trong trang, rồi thử đường dẫn phổ biến.

    Trả về [(url_rss, mô_tả)] chỉ gồm feed thật sự đọc được (có bài).
    """
    if not site_url.startswith("http"):
        site_url = "https://" + site_url
    base = f"{urlparse(site_url).scheme}://{urlparse(site_url).netloc}"
    cands: list[str] = []
    try:
        html = _get(site_url)
        for tag in _LINK_TAG.findall(html):
            at = {k.lower(): v for k, v in _ATTR.findall(tag)}
            if "alternate" in at.get("rel", "").lower() and ("rss" in at.get("type", "") or "atom" in at.get("type", "")):
                cands.append(urljoin(site_url, at.get("href", "")))
        for href in re.findall(r'href=["\']([^"\']+)["\']', html):
            if re.search(r"\.rss$|/rss(/|\.html|\.xml)?$|/feed/?$", href, re.I):
                cands.append(urljoin(site_url, href))
    except Exception:
        pass
    cands += [base + p for p in _COMMON]
    seen, out = set(), []
    socket.setdefaulttimeout(10)
    for u in cands:
        if u in seen or len(seen) >= max_probe:
            continue
        seen.add(u)
        d = feedparser.parse(u)
        if d.entries:
            out.append((u, f"{len(d.entries)} bài, ví dụ: {_clean(d.entries[0].get('title', ''))[:70]}"))
    return out

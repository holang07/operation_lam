"""Lấy giá thị trường hiện tại (public, không cần đăng nhập). Lỗi thì trả về lý do, không làm hỏng app."""
from __future__ import annotations

import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def _get(url: str, timeout: float = 8.0):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _norm(p) -> float | None:
    """Giá về VND: nguồn trả 25.5 hoặc 25500 đều ra 25500."""
    try:
        p = float(p)
    except (TypeError, ValueError):
        return None
    if p <= 0:
        return None
    return p * 1000 if p < 1000 else p


def _vndirect(t: str) -> float | None:
    j = _get(f"https://api-finfo.vndirect.com.vn/v4/stock_prices?sort=date&q=code:{t}&size=5")
    rows = j.get("data") or []
    if not rows:
        return None
    last = max(rows, key=lambda r: str(r.get("date", "")))
    return _norm(last.get("close") or last.get("adClose"))


def _ssi(t: str) -> float | None:
    j = _get(f"https://iboard-query.ssi.com.vn/v2/stock/{t}")
    d = j.get("data", j) if isinstance(j, dict) else {}
    for k in ("matchedPrice", "lastPrice", "closePrice", "refPrice"):
        v = _norm(d.get(k))
        if v:
            return v
    return None


SOURCES = [("VNDirect", _vndirect), ("SSI", _ssi)]


def fetch_one(t: str, sources=None) -> tuple[float | None, str, list[str]]:
    errs = []
    for name, fn in (sources or SOURCES):
        try:
            v = fn(t)
            if v:
                return v, name, errs
            errs.append(f"{name}: không có giá")
        except Exception as e:  # noqa: BLE001
            errs.append(f"{name}: {type(e).__name__}")
    return None, "", errs


def fetch_all(tickers, sources=None) -> dict:
    """{'prices': {mã: giá}, 'source': {mã: nguồn}, 'failed': [mã], 'errors': [str]}"""
    tickers = sorted({t.upper() for t in tickers})
    out = {"prices": {}, "source": {}, "failed": [], "errors": []}
    if not tickers:
        return out
    with ThreadPoolExecutor(8) as ex:
        for t, (v, src, errs) in zip(tickers, ex.map(lambda x: fetch_one(x, sources), tickers)):
            if v:
                out["prices"][t], out["source"][t] = v, src
            else:
                out["failed"].append(t)
                out["errors"].append(f"{t}: " + "; ".join(errs))
    return out

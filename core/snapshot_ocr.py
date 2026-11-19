"""Đọc ảnh chụp màn hình OPT bằng OCR chạy trên máy (RapidOCR). Kết quả chỉ là ĐỀ XUẤT, người dùng xác nhận."""
from __future__ import annotations

import io
import re

_engine = None


def available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def _make_engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()


try:                                        # một engine dùng chung cho cả phiên Streamlit (tạo mới mỗi lần chạy sẽ hết bộ nhớ)
    import streamlit as _st
    _get_engine = _st.cache_resource(show_spinner=False)(_make_engine)
except Exception:                           # chạy ngoài Streamlit (test)
    def _get_engine():
        global _engine
        if _engine is None:
            _engine = _make_engine()
        return _engine


def _ocr(img_bytes: bytes):
    try:
        res, _ = _get_engine()(img_bytes)
    except Exception as e:
        if "allocation" not in str(e).lower() and "memory" not in str(e).lower():
            raise
        try:                                # hết bộ nhớ tạm: dựng lại engine rồi thử một lần nữa
            if hasattr(_get_engine, "clear"):
                _get_engine.clear()
            res, _ = _get_engine()(img_bytes)
        except Exception as e2:
            raise RuntimeError("Hết bộ nhớ khi đọc ảnh. Hãy đóng bớt chương trình/tab, khởi động lại website rồi thử lại.") from e2
    return res or []


def to_lines(img_bytes: bytes) -> list[str]:
    """Gom các ô chữ OCR thành từng dòng (theo toạ độ dọc), sắp trái -> phải."""
    boxes = []
    for pts, text, _conf in _ocr(img_bytes):
        ys = [p[1] for p in pts]; xs = [p[0] for p in pts]
        boxes.append((sum(ys) / 4, min(xs), max(ys) - min(ys), str(text)))
    boxes.sort()
    lines, cur, cur_y, cur_h = [], [], None, 0
    for y, x, h, t in boxes:
        if cur_y is not None and abs(y - cur_y) > max(cur_h, h) * 0.6:
            lines.append(" ".join(b[1] for b in sorted(cur)))
            cur = []
        if not cur:
            cur_y, cur_h = y, h
        cur.append((x, t))
    if cur:
        lines.append(" ".join(b[1] for b in sorted(cur)))
    return lines


_NUM = re.compile(r"\(?-?\d[\d.,]*\d\)?|\(?-?\d\)?")


def parse_number(tok: str) -> float | None:
    """'1,234,567' / '1.234.567' / '(1,234)' / '-5' -> số. Dấu , hoặc . đứng trước đúng 3 chữ số = ngăn nghìn."""
    t = tok.strip()
    neg = t.startswith("-") or (t.startswith("(") and t.endswith(")"))
    t = t.strip("()-")
    if not t or not t[0].isdigit():
        return None
    parts = re.split(r"[.,]", t)
    if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
        v = float("".join(parts))
    elif len(parts) > 1 and len(parts[-1]) != 3 and len(parts) == 2:
        v = float(parts[0] + "." + parts[1])
    else:
        try:
            v = float("".join(parts))
        except ValueError:
            return None
    return -v if neg else v


def numbers(line: str) -> list[float]:
    out = []
    for m in _NUM.finditer(line):
        v = parse_number(m.group(0))
        if v is not None:
            out.append(v)
    return out


def _plain(text: str) -> str:
    """Bỏ dấu tiếng Việt, đổi về chữ thường nhưng GIỮ NGUYÊN độ dài (để dò vị trí). OCR hay làm rơi dấu."""
    import unicodedata
    out = []
    for ch in text:
        if ch in "đĐ":
            out.append("d")
            continue
        base = unicodedata.normalize("NFKD", ch)
        out.append(base[0] if base else ch)
    return "".join(out).lower()


_ACC = re.compile(r"\b\d{3}[A-Z]\d{6}\b")
_LBL_NAV = re.compile(r"tong\s*tai\s*san")
_LBL_GTTT = re.compile(r"tong\s*gttt")
_LBL_CASH = re.compile(r"tong\s*so\s*d\w{1,2}\s*tien")


def _first_after(line: str, m) -> float | None:
    nums = numbers(line[m.end():])
    return nums[0] if nums else None


_LOOK = {"1": "IL", "0": "O", "5": "S", "8": "B", "2": "Z"}


def _fix_tk(tok: str, known: set[str]) -> str:
    """OCR hay đọc chữ thành số (EIB -> E1B). Thử đổi số về chữ giống nhau để khớp mã đã biết."""
    if tok in known or not known:
        return tok
    cands = [tok]
    for i, ch in enumerate(tok):
        if ch in _LOOK:
            cands = [c[:i] + r + c[i + 1:] for c in cands for r in _LOOK[ch]] + cands
    return next((c for c in cands if c in known), tok)


def parse_lines(lines: list[str], known: set[str]) -> dict:
    """Đề xuất từ màn hình "Quản lý danh mục" của OPT:
    Tổng tài sản -> NAV, Tổng số dư tiền -> số dư tiền (số trong ngoặc = âm),
    dòng bảng có mã -> SLCP (cột GD, số đầu tiên sau mã), số tài khoản dạng 011C123456."""
    cash = nav = gttt = None
    account = None
    hold: dict[str, float] = {}
    prices: dict[str, float] = {}
    pending: dict[str, float] = {}
    for ln in lines:
        low = _plain(ln)
        a = _ACC.search(ln)
        if a and not account:
            account = a.group(0)
        m = _LBL_NAV.search(low)
        if m and nav is None:
            nav = _first_after(ln, m)
            low_rest = low[:m.start()]
        m2 = _LBL_CASH.search(low)
        if m2 and cash is None:
            cash = _first_after(ln, m2)
            if cash is not None and cash > 0 and ln[m2.end():].lstrip().startswith(("(", "（")):
                cash = -cash
        m3 = _LBL_GTTT.search(low)
        if m3 and gttt is None:
            gttt = _first_after(ln, m3)
        if m or m2 or m3:
            continue
        toks = [_fix_tk(t, known) for t in re.findall(r"\b[A-Z][A-Z0-9]{2}\b", ln)]
        known_tk = next((t for t in toks if t in known), None)
        tk = known_tk or (toks[0] if toks and len(numbers(ln)) >= 3 else None)
        if tk:
            src = next((t for t in re.findall(r"\b[A-Z][A-Z0-9]{2}\b", ln) if _fix_tk(t, known) == tk), tk)
            after = numbers(ln.split(src, 1)[1])
            q = next((n for n in after if n >= 1 and float(n).is_integer()), None)   # cột GD
            if q is not None:
                # SLCP = GD + Chờ về. GTTT (cột lớn nhất) = (GD + Chờ về) x Giá TT, nên suy SLCP từ GTTT / Giá TT:
                # OCR hay làm rơi các cột 0 nên không dò cột "Chờ về" theo vị trí được.
                total, price = q, None
                g = max(after) if after else 0
                for p_ in after:
                    if p_ != q and p_ != g and 500 <= p_ <= 1_000_000 and float(p_).is_integer() and g > 0:
                        t_ = g / p_
                        if abs(t_ - round(t_)) < 0.01 and round(t_) >= q:
                            total, price = float(round(t_)), float(p_)
                            break
                if price is None:                      # không có GTTT/giá để suy ra: giữ cách cũ (chỉ GD)
                    for g2 in after:
                        if g2 != q and 500 <= g2 / q <= 1_000_000 and abs(g2 / q - round(g2 / q)) < 0.01:
                            price = float(round(g2 / q))
                            break
                hold.setdefault(tk, total)
                if total > q:
                    pending[tk] = total - q
                if price:
                    prices.setdefault(tk, price)
    # OCR hay làm rơi dấu ngoặc của số âm. NAV = số dư tiền + GTTT nên chọn dấu cho khớp NAV.
    if gttt is None and hold and prices:
        gttt = sum(q * prices.get(t, 0) for t, q in hold.items()) or None
    if cash is not None and nav and gttt:
        c = abs(cash)
        err_pos, err_neg = abs(nav - (c + gttt)), abs(nav - (-c + gttt))
        best = min(err_pos, err_neg)
        if best <= max(1000.0, abs(nav) * 0.001):
            cash = c if err_pos < err_neg else -c
    return dict(cash=cash, nav=nav, gttt=gttt, holdings=hold, prices=prices, pending=pending, account=account, lines=lines)


def _upscale(img_bytes: bytes, factor: float = 2.0, max_side: int = 2600) -> bytes | None:
    """Phóng ảnh nhỏ/mờ lên để OCR đọc chữ nhỏ tốt hơn."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        f = min(factor, max_side / max(im.size))
        if f <= 1.05:
            return None
        im = im.resize((int(im.width * f), int(im.height * f)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()
    except Exception:
        return None


# Nhãn "nới lỏng": dùng khi nhãn chuẩn không khớp vì OCR đọc sai vài ký tự
_FUZZY_NAV = re.compile(r"t.{1,3}ng\s*t.{1,3}i\s*s.{1,3}n")
_FUZZY_CASH = re.compile(r"t.{1,3}ng\s*s.{0,3}\s*d.{1,3}\s*t.{1,3}n")


def _fuzzy_fill(lines: list[str], d: dict) -> None:
    for ln in lines:
        low = _plain(ln)
        if d["nav"] is None:
            m = _FUZZY_NAV.search(low)
            if m:
                d["nav"] = _first_after(ln, m)
        if d["cash"] is None:
            m = _FUZZY_CASH.search(low)
            if m:
                v = _first_after(ln, m)
                if v is not None and v > 0 and ln[m.end():].lstrip().startswith(("(", "（")):
                    v = -v
                d["cash"] = v


def _infer_nav(d: dict) -> dict:
    """OCR bỏ sót ô "Tổng tài sản" nhưng có số dư tiền + danh mục: NAV = số dư tiền + GTTT
    (GTTT đọc từ ảnh, hoặc cộng SLCP x giá). Đánh dấu nav_inferred để giao diện báo rõ là số suy ra."""
    if d.get("nav") is None and d.get("cash") is not None and d.get("holdings"):
        g = d.get("gttt") or sum(q * (d.get("prices") or {}).get(t, 0) for t, q in d["holdings"].items())
        if g:
            d["nav"] = d["cash"] + g
            d["nav_inferred"] = True
    return d


def read_snapshot(img_bytes: bytes, known: set[str]) -> dict:
    return _infer_nav(_read_snapshot(img_bytes, known))


def _read_snapshot(img_bytes: bytes, known: set[str]) -> dict:
    d = parse_lines(to_lines(img_bytes), known)
    if d["cash"] is None or d["nav"] is None:            # thử lại: nhãn nới lỏng, rồi phóng to ảnh
        _fuzzy_fill(d["lines"], d)
    if d["cash"] is None or d["nav"] is None:
        big = _upscale(img_bytes)
        if big:
            d2 = parse_lines(to_lines(big), known)
            if d2["cash"] is None or d2["nav"] is None:
                _fuzzy_fill(d2["lines"], d2)
            for k in ("cash", "nav", "gttt", "account"):
                if d.get(k) is None and d2.get(k) is not None:
                    d[k] = d2[k]
            if not d["holdings"]:
                d["holdings"], d["prices"] = d2["holdings"], d2["prices"]
            d["lines"] = d["lines"] + d2["lines"]
            # chọn lại dấu của số dư tiền theo NAV, giống parse_lines
            if d["cash"] is not None and d["nav"] and d.get("gttt"):
                c = abs(d["cash"]); g = d["gttt"]; n = d["nav"]
                ep, en = abs(n - (c + g)), abs(n - (-c + g))
                if min(ep, en) <= max(1000.0, abs(n) * 0.001):
                    d["cash"] = c if ep < en else -c
    return d


# ---------------------------------------------------------------- vùng đọc do người dùng chỉ định
import json
from pathlib import Path

ROI_PATH = Path(__file__).resolve().parents[1] / "data" / "roi.json"
# Toạ độ theo tỉ lệ ảnh: [trái, trên, phải, dưới] (0..1). Mặc định theo ảnh mẫu "Quản lý danh mục" của OPT.
DEFAULT_ROI = {
    "nav": [0.80, 0.35, 0.92, 0.45],
    "cash": [0.80, 0.46, 0.92, 0.56],
    "holdings": [0.00, 0.24, 1.00, 0.40],
}
ROI_LABEL = {"nav": "Tổng tài sản (NAV)", "cash": "Tổng số dư tiền", "holdings": "Bảng danh mục (mã + SLCP)"}


def load_roi() -> dict:
    try:
        d = json.loads(ROI_PATH.read_text(encoding="utf-8"))
        return {k: [float(x) for x in d.get(k, v)] for k, v in DEFAULT_ROI.items()}
    except Exception:
        return {k: list(v) for k, v in DEFAULT_ROI.items()}


def save_roi(roi: dict) -> None:
    ROI_PATH.parent.mkdir(exist_ok=True)
    ROI_PATH.write_text(json.dumps(roi), encoding="utf-8")


def crop_png(img_bytes: bytes, box: list[float], scale: int = 3) -> bytes:
    """Cắt vùng, phóng to và thêm viền trắng để OCR đọc chắc hơn."""
    from PIL import Image, ImageOps
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = im.size
    c = im.crop((int(box[0] * w), int(box[1] * h), max(int(box[2] * w), int(box[0] * w) + 2), max(int(box[3] * h), int(box[1] * h) + 2)))
    if c.width < 600:                       # vùng hẹp mới cần phóng to; vùng rộng giữ nguyên cho OCR khỏi mất chữ
        c = c.resize((c.width * scale, c.height * scale), Image.LANCZOS)
    # OCR hay bỏ sót khi ảnh quá mỏng: thêm viền trắng cho tới khi đủ cao/rộng
    px = max(20, (280 - c.height) // 2, (280 - c.width) // 2)
    c = ImageOps.expand(c, border=px, fill="white")
    buf = io.BytesIO(); c.save(buf, format="PNG")
    return buf.getvalue()


def draw_boxes(img_bytes: bytes, roi: dict) -> bytes:
    from PIL import Image, ImageDraw
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = im.size
    d = ImageDraw.Draw(im)
    colors = {"nav": (220, 0, 0), "cash": (0, 140, 0), "holdings": (0, 90, 220)}
    for k, b in roi.items():
        d.rectangle([b[0] * w, b[1] * h, b[2] * w, b[3] * h], outline=colors.get(k, (255, 0, 255)), width=3)
        d.text((b[0] * w + 4, max(b[1] * h - 12, 0)), k, fill=colors.get(k, (255, 0, 255)))
    buf = io.BytesIO(); im.save(buf, format="PNG")
    return buf.getvalue()


def read_value(img_bytes: bytes, box: list[float]) -> tuple[float | None, str]:
    """Đọc MỘT số trong vùng; trả (số, chữ OCR thô). Số trong ngoặc hoặc có dấu - là âm."""
    txt = " ".join(to_lines(crop_png(img_bytes, box)))
    txt = txt.replace("（", "(").replace("）", ")")
    txt = re.sub(r"(?<=\d[.,])\s+(?=\d)", "", txt)       # OCR hay tách "84,053,109, 004" thành hai mảnh
    txt = re.sub(r"(?<=\d)\s+(?=[.,]\d)", "", txt)
    nums = numbers(txt)
    return (nums[0] if nums else None), txt


def read_snapshot_roi(img_bytes: bytes, known: set[str], roi: dict | None = None) -> dict:
    """Đọc đúng ba vùng người dùng chỉ định. Vùng nào đọc không ra thì rơi về cách đọc toàn ảnh."""
    roi = roi or load_roi()
    nav, t_nav = read_value(img_bytes, roi["nav"])
    cash, t_cash = read_value(img_bytes, roi["cash"])
    lines = to_lines(crop_png(img_bytes, roi["holdings"]))
    _p = parse_lines(lines, known)
    hold, hprices = _p["holdings"], _p["prices"]
    full = None
    if nav is None or cash is None or not hold:
        full = read_snapshot(img_bytes, known)
    gt = None
    if hold and hprices:
        gt = sum(q * hprices.get(t, 0) for t, q in hold.items()) or None
    if cash is not None and nav and gt:
        c_ = abs(cash)
        ep, en = abs(nav - (c_ + gt)), abs(nav - (-c_ + gt))
        if min(ep, en) <= max(1000.0, abs(nav) * 0.001):
            cash = c_ if ep < en else -c_
    return _infer_nav(dict(cash=cash if cash is not None else (full or {}).get("cash"),
                nav=nav if nav is not None else (full or {}).get("nav"),
                holdings=hold or (full or {}).get("holdings", {}),
                prices=hprices or (full or {}).get("prices", {}),
                account=(full or {}).get("account"), lines=lines,
                raw=dict(nav=t_nav, cash=t_cash)))

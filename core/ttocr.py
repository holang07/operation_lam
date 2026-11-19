"""Đọc ảnh chụp dòng thỏa thuận (bảng Excel: CTCK | Cá nhân | TK giao dịch | Giao dịch | Số lượng | Giá |
Bên đối ứng | Mã TV | Lệnh | Giá trị) để điền sẵn form Lệnh thỏa thuận. Kết quả chỉ là ĐỀ XUẤT, người dùng kiểm tra."""
import io
import re

from core import snapshot_ocr as so


def _tiles(img_bytes: bytes):
    """Ảnh bảng rất dẹt (rộng, thấp) làm OCR bỏ sót: phóng to rồi cắt thành các đoạn ngang chồng nhau."""
    from PIL import Image
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = im.size
    s = max(1.0, min(4.0, 160.0 / max(h, 1))) if h < 120 else (2.0 if h < 300 else 1.0)
    im = im.resize((int(w * s), int(h * s)), Image.LANCZOS)
    W, H = im.size
    pad_y = 60
    tw = max(int(H * 6), 500)                    # mỗi đoạn dài tối đa ~6 lần chiều cao
    step = max(tw - 80, 300)
    out, x = [], 0
    while True:
        part = im.crop((x, 0, min(x + tw, W), H))
        canvas = Image.new("RGB", (part.width, H + 2 * pad_y), "white")
        canvas.paste(part, (0, pad_y))
        buf = io.BytesIO()
        canvas.save(buf, "PNG")
        out.append((x, s, pad_y, buf.getvalue()))
        if x + tw >= W:
            break
        x += step
    return out


def boxes(img_bytes: bytes) -> list[tuple[float, float, str]]:
    """[(x_giữa, y_giữa, chữ)] theo toạ độ ảnh gốc, đã bỏ trùng ở chỗ chồng nhau."""
    res = []
    for x0, s, pad, b in _tiles(img_bytes):
        for p, txt, _c in so._ocr(b):
            xs = [q[0] for q in p]
            ys = [q[1] for q in p]
            res.append(((x0 + (min(xs) + max(xs)) / 2) / s, ((min(ys) + max(ys)) / 2 - pad) / s, str(txt).strip()))
    res.sort(key=lambda t: (t[0], t[1]))
    out = []
    for x, y, t in res:
        if any(abs(x - x2) < 14 and abs(y - y2) < 8 and (t in t2 or t2 in t) for x2, y2, t2 in out):
            continue
        out.append((x, y, t))
    return out


def _num(t: str):
    d = re.sub(r"[^\d]", "", t)
    return int(d) if d else None


def parse_rows(bx: list[tuple[float, float, str]]) -> list[dict]:
    """Gom ô chữ theo hàng (toạ độ dọc) rồi tách các trường của từng hàng dữ liệu."""
    rows: list[list] = []
    for x, y, t in sorted(bx, key=lambda b: b[1]):
        for r in rows:
            if abs(r[0] - y) < 12:
                r[1].append((x, t))
                break
        else:
            rows.append([y, [(x, t)]])
    out = []
    for _y, toks in rows:
        toks.sort()
        text = "  ".join(t for _, t in toks)
        m_acct = re.search(r"(?:0?1?1?C|\b)\s?(\d{6})\b", text)
        m_tv = re.search(r"(?<![\d,.])(\d{3})\s*[-–—]\s*(\d{4,5})(?![\d,])", text)
        if not m_tv:                                       # OCR làm rơi dấu gạch: chỉ nhận khi cả ô chữ là mã TV
            for _, t in toks:
                m_tv = re.fullmatch(r"\s*(\d{3})\s+(\d{4,5})\s*", t)
                if m_tv:
                    text = text.replace(t, f"{m_tv.group(1)} - {m_tv.group(2)}")
                    m_tv = re.search(r"(?<![\d,.])(\d{3})\s*[-–—]\s*(\d{4,5})(?![\d,])", text)
                    break
        if not (m_tv and m_acct):
            continue
        acct6 = None
        for t in re.findall(r"[0-9Cc]{0,4}C?\s?\d{6}\b", text):
            d = re.sub(r"\D", "", t)
            if len(d) >= 6 and d[-6:] != m_tv.group(2)[-5:].rjust(6, "0"):
                acct6 = d[-6:]
                break
        side = None
        if re.search(r"\b(B[aáàảãạâấ]n)\b", text, re.I):
            side = "Bán"
        elif re.search(r"\bMua\b", text, re.I):
            side = "Mua"
        # số: xét từng ô chữ, bỏ mã TK, mã TV và mảnh vụn toàn số 0 do ô chồng nhau
        nums, frags = [], []
        for _, t in toks:
            if re.search(r"C\s?\d{6}", t) or re.search(r"(?<![\d,.])\d{3}\s*[-–—]\s*\d{4,5}(?![\d,])", t):
                continue
            if not re.fullmatch(r"[\(\s]*[\d][\d,.\s]*[\)\s]*", t.strip()):
                continue
            v = _num(t)
            dg = re.sub(r"\D", "", t)
            if v and set(dg) == {"0"} and len(dg) <= 4 and nums:     # mảnh '000' của ô bị tách đôi
                frags.append((nums[-1][0], dg))
            elif v and set(dg) != {"0"}:
                nums.append((v, t.strip().startswith("(")))
        qty = price = val = None
        base = [v for v, _ in nums]

        def _solve(cand: set):
            best = None
            for a_ in sorted(cand):
                for b_ in sorted(cand):
                    if a_ != b_ and a_ * b_ in cand:
                        q_, p_ = (a_, b_) if b_ < 200000 else (b_, a_)
                        if best is None or a_ * b_ > best[2]:
                            best = (q_, p_, a_ * b_)
            return best

        cand = set(base)
        sol = _solve(cand)
        if sol is None and frags:                           # ô bị tách đôi (vd 11,445,000 + 000)
            for v0, z in frags:
                cand.add(int(str(v0) + z))
            sol = _solve(cand)
        if sol:
            qty, price, val = sol
        elif cand:
            val = max(cand)
            px_c = [v for v in cand if 1000 <= v <= 500000 and val % v == 0 and v != val]
            if px_c:
                price = min(px_c, key=lambda v: abs(v - 20000))
                qty = val // price
            else:
                others = sorted(v for v in cand if v != val)
                if len(others) >= 2:
                    price, qty = others[0], others[-1]
        ok = bool(qty and price and val and qty * price == val)
        neg = any(p for v, p in nums if v == qty)
        if side is None and qty is not None:
            side = "Bán" if neg else "Mua"
        # CTCK đối ứng: chữ in hoa ngay trước mã TV
        pre = text[:m_tv.start()]
        mf = re.findall(r"\b([A-Z]{2,6})\b", pre)
        firm = mf[-1] if mf else ""
        name = ""
        for _, t in toks:
            if re.search(r"[A-Za-zÀ-ỹ]{2,}", t) and " " in t.strip() and not re.search(r"\d", t):
                name = t.strip()
                break
        stop = {"HSC", "CTCK", "TV", "MUA", "BAN", "BÁN"}
        ticker = ""
        for _, t in toks:
            t2 = t.strip()
            if re.fullmatch(r"[A-Z][A-Z0-9]{2}", t2) and t2 not in stop and t2 != firm:
                ticker = t2
                break
        out.append(dict(ok=ok, ticker=ticker, acct6=acct6, name=name, side=side, qty=qty, price=price, value=val,
                        firm=firm, tv=f"{m_tv.group(1)} - {m_tv.group(2)}", margin="Margin" in text or "margin" in text.lower(),
                        raw=text))
    return out


def read(img_bytes: bytes) -> list[dict]:
    return parse_rows(boxes(img_bytes))

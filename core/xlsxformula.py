"""Đọc/ghép công thức số học đơn giản trong ô Excel (vd =-70001930996+900*10^3*E2-14*10^9)."""
from __future__ import annotations

import re

_SAFE = re.compile(r"^[\d\.\+\-\*/\^\(\) ]*$")


def split_terms(expr: str) -> list[str]:
    """'5798000+2000000-2689000' -> ['+5798000','+2000000','-2689000'] (chỉ tách + và - ở ngoài ngoặc)."""
    e = expr.strip().lstrip("=").replace(" ", "")
    terms, cur, depth = [], "", 0
    for i, ch in enumerate(e):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch in "+-" and depth == 0 and i > 0 and e[i - 1] not in "*/^(" and cur:
            terms.append(cur)
            cur = ""
        cur += ch
    if cur:
        terms.append(cur)
    return [t if t[0] in "+-" else "+" + t for t in terms]


def evaluate(expr: str, e_price: float | None = None) -> float | None:
    """Tính biểu thức; tham chiếu E<n> được thay bằng e_price. Có tham chiếu khác -> None."""
    t = expr.strip().lstrip("=")
    if e_price is not None:
        t = re.sub(r"\bE\d+\b", repr(float(e_price)), t)
    t = t.replace("^", "**")
    if not t.strip():
        return 0.0
    if not _SAFE.match(t.replace("**", "^")):
        return None
    try:
        return float(eval(t, {"__builtins__": {}}, {}))
    except Exception:
        return None


def fmt_num(v: float) -> str:
    return str(int(round(v))) if abs(v - round(v)) < 1e-9 else repr(float(v))


def split_cash(raw) -> tuple[str, str] | None:
    """B3 dạng '=-70001930996+900*10^3*E2-14*10^9' -> ('-70001930996', '+900*10^3*E2-14*10^9')."""
    if isinstance(raw, (int, float)):
        return fmt_num(raw), ""
    if not isinstance(raw, str):
        return None
    m = re.match(r"^=\s*([+-]?\s*\d[\d.]*)(.*)$", raw.strip())
    if not m:
        return None
    # 'số đầu tiên' không được là phần đầu của phép nhân/chia/luỹ thừa (vd =5*10^9)
    rest = m.group(2)
    if rest and rest[0] in "*/^":
        return None
    return m.group(1).replace(" ", ""), rest.replace(" ", "")


def split_qty(raw, opt_qty: float) -> dict:
    """Công thức SLCP (cột D). Trả {'keep': True/False, 'adj': phần điều chỉnh chờ, 'formula': công thức mới}.

    Nếu có phần đầu của công thức cộng đúng bằng SLCP OPT thì phần còn lại là điều chỉnh chờ (giữ nguyên công thức cũ).
    Nếu không, giữ lại các số hạng ÂM ở cuối (lệnh bán chờ) làm điều chỉnh mặc định và dựng '=SLCP OPT + điều chỉnh'."""
    if not isinstance(raw, str) or not raw.startswith("="):
        return dict(keep=False, adj="", formula=fmt_num(opt_qty), matched=isinstance(raw, (int, float)) and abs(raw - opt_qty) < 1)
    terms = split_terms(raw)
    vals = [evaluate(t) for t in terms]
    if any(v is None for v in vals):
        return dict(keep=False, adj="", formula=fmt_num(opt_qty), unreadable=True)
    run = 0.0
    for k, v in enumerate(vals, 1):
        run += v
        if abs(run - opt_qty) < 0.5:
            return dict(keep=True, adj="".join(terms[k:]), formula=raw, matched=True)
    j = len(terms)
    while j > 0 and vals[j - 1] < 0:
        j -= 1
    adj = "".join(terms[j:])
    return dict(keep=False, adj=adj, formula="=" + fmt_num(opt_qty) + adj, matched=False)

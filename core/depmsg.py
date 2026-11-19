"""Cú pháp chuyển tiền nộp vào tài khoản chứng khoán của KH."""
import math
import unicodedata

from core import db

DEFAULT_BANK = "BIDV Nam Kỳ Khởi Nghĩa"


def no_accent(s: str) -> str:
    s = (s or "").replace("đ", "d").replace("Đ", "D")
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn").strip()


def stk(account_no: str) -> str:
    a = (account_no or "").strip().upper()
    if len(a) >= 10 and a[:4] == "011C":
        return a
    return "011C" + a[-6:] if a else ""


def holder(name: str, acct: str, directory: dict | None = None) -> str:
    """Họ tên đầy đủ không dấu (lấy từ danh bạ KH, thiếu thì dùng tên ngắn)."""
    d = (directory if directory is not None else db.directory()).get((acct or "")[-6:])
    return no_accent((d or {}).get("full_name") or name)


def round_up(v: float, step: int) -> int:
    return int(math.ceil(max(float(v), 0.0) / step - 1e-9) * step) if step > 0 else int(v)


def text(account_no: str, full_name: str, bank: str, amount: float) -> str:
    s = stk(account_no)
    return (f"STK: {s}\nNgười thụ hưởng: {full_name}\nTại Ngân hàng {bank}\n"
            f"Nội dung: {s} {full_name}\nSố tiền: {int(round(amount)):,}")

"""Danh sách CTCK và mã ID (mã thành viên) dùng cho lệnh thỏa thuận. Sửa được trong Cài đặt."""
import json
import re

from core import db

OTHER = "(Khác, nhập tay)"

DEFAULT = [
    ("020 - 00201", "CTCK OCBS"), ("081 - 00811", "CTCK SHINHAN"), ("050 - 00501", "CTCK JBSV"),
    ("068 - 00681", "CTCK VCI"), ("072 - 00721", "CTCK VIX"), ("116 - 01161", "CTCK VPBankS"),
    ("011 - 0111", "CTCK HSC"), ("105 - 01051", "CTCK TCBS"), ("003 - 00031", "CTCK SSI"),
    ("002 - 00021", "CTCK BSC"), ("005 - 0053", "CTCK MBS"), ("006 - 0062", "CTCK ACBS"),
    ("007 - 0071", "CTCK CTS"), ("022 - 0221", "CTCK PHS"), ("009 - 0091", "CTCK VCBS"),
    ("064 - 0641", "CTCK DNSE"), ("049 - 0491", "CTCK Kafi"), ("069 - 0691", "CTCK SHS"),
    ("021 - 0211", "CTCK VNDS"), ("045 - 00451", "CTCK PSI"), ("007 - 00071", "CTCK CTS"),
    ("032 - 00321", "CTCK ASEAN"), ("061 - 00611", "CTCK GUOTAI JUNAN"), ("057 - 00571", "CTCK KIS"),
    ("091 - 00912", "CTCK KBS"), ("103 - 01031", "CTCK LPBS"), ("077 - 00772", "CTCK MIRAE ASSET"),
]


def norm_id(s: str) -> str:
    """'007-00071' hoặc '007  -00071' thành '007 - 00071'."""
    m = re.match(r"\s*(\d{3})\s*[-–—]?\s*(\d{2,6})\s*$", s or "")
    return f"{m.group(1)} - {m.group(2)}" if m else (s or "").strip()


def entries() -> list[tuple[str, str]]:
    try:
        raw = json.loads(db.get_text("ctck_list", ""))
        out = [(norm_id(i), n.strip()) for i, n in raw if i and n]
        if out:
            return out
    except Exception:  # noqa: BLE001
        pass
    return list(DEFAULT)


def save(rows: list[tuple[str, str]]) -> None:
    db.set_text("ctck_list", json.dumps([[norm_id(i), n.strip()] for i, n in rows if i and n], ensure_ascii=False))


def reset() -> None:
    db.set_text("ctck_list", "")


def names() -> list[str]:
    return sorted({n for _, n in entries()}, key=str.lower)


def ids_for(name: str) -> list[str]:
    return [i for i, n in entries() if n == name]


def find_by_id(i: str):
    i = norm_id(i)
    for a, n in entries():
        if a == i:
            return n
    return None

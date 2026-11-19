"""Lưu file Excel dữ liệu theo thư mục riêng từng nhóm: data/groups/<tên nhóm>/<ngày giờ>_<loại>_<tên file>.xlsx"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from core import db

KINDS = {"goc": "File gốc", "capnhat": "File đã cập nhật"}


def root() -> Path:
    return db.DB_PATH.parent / "groups"


def safe(name: str) -> str:
    n = re.sub(r'[\\/:*?"<>|]+', " ", (name or "").strip())
    return re.sub(r"\s+", " ", n).strip(" .")[:60] or "Chung"


def groups() -> list[str]:
    r = root()
    return sorted(p.name for p in r.iterdir() if p.is_dir()) if r.exists() else []


def files(group: str) -> list[dict]:
    d = root() / safe(group)
    out = []
    if d.exists():
        for p in sorted(d.glob("*.xlsx"), key=lambda x: x.stat().st_mtime, reverse=True):
            m = re.match(r"^\d{8}_\d{6}_(goc|capnhat)_(.*)\.xlsx$", p.name)
            kind, orig = (m.group(1), m.group(2)) if m else ("goc", p.stem)
            out.append(dict(name=p.name, kind=kind, orig=orig, size=p.stat().st_size,
                            time=datetime.fromtimestamp(p.stat().st_mtime)))
    return out


def label(f: dict) -> str:
    return f"{f['time']:%d/%m/%Y %H:%M} · {KINDS.get(f['kind'], f['kind'])} · {f['orig']}"


def save(group: str, raw: bytes, kind: str = "goc", orig_name: str = "file") -> Path:
    d = root() / safe(group)
    d.mkdir(parents=True, exist_ok=True)
    stem = safe(Path(orig_name).stem)
    p = d / f"{datetime.now():%Y%m%d_%H%M%S}_{kind}_{stem}.xlsx"
    p.write_bytes(raw)
    return p


def read(group: str, fname: str) -> bytes:
    p = (root() / safe(group) / Path(fname).name)
    return p.read_bytes()


def delete_file(group: str, fname: str) -> None:
    p = root() / safe(group) / Path(fname).name
    if p.exists():
        p.unlink()


def delete_group(group: str) -> None:
    d = root() / safe(group)
    if d.exists() and d.parent == root():
        shutil.rmtree(d)


def rename(group: str, fname: str, new_name: str) -> str:
    """Đổi tên hiển thị của file (giữ nguyên tiền tố ngày giờ và loại). Trả về tên file mới."""
    d = root() / safe(group)
    src = d / Path(fname).name
    m = re.match(r"^(\d{8}_\d{6}_(?:goc|capnhat)_)", src.name)
    prefix = m.group(1) if m else f"{datetime.fromtimestamp(src.stat().st_mtime):%Y%m%d_%H%M%S}_goc_"
    dst = d / f"{prefix}{safe(Path(new_name).stem)}.xlsx"
    if dst != src:
        if dst.exists():
            raise FileExistsError(dst.name)
        src.rename(dst)
    return dst.name

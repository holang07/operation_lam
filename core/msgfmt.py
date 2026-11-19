"""Định dạng số tiền cho tin nhắn gửi KH: >= 1 tỷ ghi 'tỷ', dưới 1 tỷ ghi 'triệu'."""
from __future__ import annotations

import math

TY, TRIEU = 1_000_000_000, 1_000_000


def _dec(x: float, nd: int = 1) -> str:
    s = f"{x:.{nd}f}".rstrip("0").rstrip(".")
    return s


def fmt_floor(v: float, step: int = 10 * TRIEU) -> str:
    """Làm tròn XUỐNG theo `step` (mặc định 10 triệu). Từ 1 tỷ: ghi tỷ; dưới 1 tỷ: ghi triệu."""
    v = float(v)
    if v < 0:                       # sức mua âm: làm tròn theo giá trị tuyệt đối, thêm dấu trừ
        return "-" + fmt_floor(-v, step)
    x = int(v // step * step)
    if x >= TY:
        nd = 1 if step >= 100 * TRIEU else 2
        return _dec((x // (TY // 10 ** nd)) / 10 ** nd, nd) + " tỷ"
    return f"{x // TRIEU:,} triệu"


def fmt_limit(v: float) -> str:
    """Hạn mức: làm tròn xuống hàng tỷ; dưới 1 tỷ thì ghi triệu (làm tròn xuống triệu)."""
    v = max(0.0, float(v))
    if v >= TY:
        return f"{int(v // TY):,} tỷ"
    return f"{int(v // TRIEU):,} triệu"


def fmt_debt(v: float) -> str:
    """Dư nợ: 1 số lẻ theo tỷ (19.7 tỷ); dưới 1 tỷ ghi triệu."""
    v = max(0.0, float(v))
    if v >= TY:
        return _dec(round(v / TY, 1)) + " tỷ"
    return f"{round(v / TRIEU):,} triệu"


def loan_pct(im_dt_pct: float) -> int:
    """Tỉ lệ vay hiển thị = 100 - IM DT (%), làm tròn xuống."""
    return int(math.floor(100 - im_dt_pct + 1e-9))

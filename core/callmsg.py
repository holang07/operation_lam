"""Soạn tin nhắc KH nộp tiền khi bị call margin (gom theo ngày hạn nộp)."""
import json
import math
import re
from datetime import date, timedelta

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from core import db, service
from core.service import STATUS_LABEL

TRIEU, TY = 10 ** 6, 10 ** 9
HEADER = "Dạ các chị ơi, do thị trường biến động nên các tk KH đang bị call margin"


def fmt_amount(v: float, step: int = 50 * TRIEU) -> str:
    """Làm tròn LÊN theo `step`; từ 1 tỷ ghi tỷ (tối đa 2 số lẻ), dưới 1 tỷ ghi triệu."""
    x = math.ceil(max(float(v), 0.0) / step - 1e-9) * step if step > 0 else float(v)
    if x >= TY:
        t = f"{x / TY:.2f}".rstrip("0").rstrip(".")
        return t + " tỷ"
    return f"{int(round(x / TRIEU)):,} triệu"


def _key(d: str):
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})", d or "")
    return (int(m.group(2)), int(m.group(1))) if m else (99, 99)


def build_text(items: list[dict], header: str = HEADER, cutoff: str = "14h") -> str:
    """items: label, amount (VND, đã làm tròn), due ('19/11')."""
    groups: dict[str, list] = {}
    for it in items:
        groups.setdefault(it["due"].strip(), []).append(it)
    blocks = []
    for d in sorted(groups, key=_key):
        its = groups[d]
        lines = [f"*Ngày {d} trước {cutoff}*"]
        lines += [f"{i['label']} nộp tối thiểu {fmt_amount(i['amount'], 1)}  " for i in its]
        lines += ["", f"*Tổng nộp {d}: {fmt_amount(sum(i['amount'] for i in its), 1)}*"]
        blocks.append("\n".join(lines))
    return header + "\n\n" + "\n----\n".join(blocks) if blocks else header


def _copy_button(text: str) -> None:
    components.html(f"""
<div style="font-family:Inter,Arial,sans-serif">
<button id="b" style="padding:7px 14px;border:1px solid #2F6BFF;background:#2F6BFF;color:#fff;border-radius:8px;cursor:pointer">Sao chép tin nhắn</button>
<span id="m" style="margin-left:10px;color:#15803D;font-size:13px"></span></div>
<script>
const t = {json.dumps(text)};
document.getElementById('b').onclick = async () => {{
  const m = document.getElementById('m');
  try {{ await navigator.clipboard.writeText(t); }}
  catch(e) {{ const a=document.createElement('textarea'); a.value=t; document.body.appendChild(a); a.select(); document.execCommand('copy'); a.remove(); }}
  m.textContent='Đã sao chép'; setTimeout(()=>m.textContent='',2500);
}};
</script>""", height=48)


def render(res: list[dict]) -> None:
    st.markdown("#### Soạn tin call margin gửi nhóm")
    calls = [r for r in res if r["status"] != "bình thường" and r["call_amount"] > 0]
    if not calls:
        st.info("Hiện không có tài khoản nào bị call hoặc FS.")
        return
    c1, c2, c3 = st.columns(3)
    step_lbl = c1.radio("Làm tròn tiền nộp LÊN", ["50 triệu", "100 triệu", "10 triệu"], horizontal=True, key="cm_step")
    step = {"50 triệu": 50, "100 triệu": 100, "10 triệu": 10}[step_lbl] * TRIEU
    days = c2.number_input("Hạn nộp mặc định sau (ngày)", value=2, min_value=0, max_value=5, key="cm_days")
    cutoff = c3.text_input("Giờ chốt", value="14h", key="cm_cut")
    due0 = (date.today() + timedelta(days=int(days))).strftime("%d/%m")
    base = pd.DataFrame([{
        "Gửi": True,
        "Tài khoản": service.acct_label(r["name"], r["account_no"]),
        "Tình trạng": STATUS_LABEL[r["status"]],
        "Cần nộp (tính toán)": round(r["call_amount"]),
        "Nộp tối thiểu (VND)": int(math.ceil(r["call_amount"] / step - 1e-9) * step),
        "Hạn nộp (dd/mm)": due0,
    } for r in sorted(calls, key=lambda x: x["mr"])])
    sig = f"{step}|{due0}|" + "|".join(base["Tài khoản"])
    st.caption("Sửa số tiền, ngày hạn nộp của từng KH (ví dụ KH bị call hôm qua thì hạn là ngày mai), bỏ tick nếu không gửi.")
    ed = st.data_editor(
        base, hide_index=True, width="stretch", key=f"cm_ed_{sig}",
        disabled=["Tài khoản", "Tình trạng", "Cần nộp (tính toán)"],
        column_config={
            "Gửi": st.column_config.CheckboxColumn(width="small"),
            "Cần nộp (tính toán)": st.column_config.NumberColumn(format="%d"),
            "Nộp tối thiểu (VND)": st.column_config.NumberColumn(min_value=0, step=10 * TRIEU, format="%d"),
        })
    items = [dict(label=r["Tài khoản"], amount=float(r["Nộp tối thiểu (VND)"] or 0), due=str(r["Hạn nộp (dd/mm)"] or due0))
             for _, r in ed.iterrows() if r["Gửi"] and (r["Nộp tối thiểu (VND)"] or 0) > 0]
    text = build_text(items, cutoff=cutoff.strip() or "14h")
    txt = st.text_area("Tin nhắn (sửa trực tiếp được; sửa xong bấm ra ngoài ô trước khi sao chép)",
                       value=text, height=300, key=f"cm_txt_{hash(text) & 0xffffffff}")
    _copy_button(txt)

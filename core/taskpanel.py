"""Ô Task cá nhân (to-do) cho Trang chủ: gọn, tự do đặt nhãn, không phụ thuộc nhóm KH."""
from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from . import service
from . import tasks as tk


def _iso(v) -> str:
    if not v:
        return ""
    return (v.date() if isinstance(v, datetime) else v).isoformat()


def _tag(t: dict, lm: dict) -> str:
    """Nhãn hiển thị: task cũ gắn KH/nhóm vẫn hiện được, task mới là chữ tự do."""
    tg = (t.get("target") or "").strip()
    return lm.get(tg, tg) if t.get("scope") == "KH" else tg


def _bump():
    st.session_state["tk_ver"] = st.session_state.get("tk_ver", 0) + 1


def render() -> None:
    ss = st.session_state
    ver = ss.get("tk_ver", 0)
    lm = service.label_map()
    all_rows = tk.list_tasks(include_done=True)
    tags = sorted({_tag(r, lm) for r in all_rows if _tag(r, lm)})

    with st.container(border=True):
        cnt = tk.counts()
        st.markdown("#### Task của tôi" + f" · {cnt['open']} mở"
                    + (f" · :red[{cnt['overdue']} quá hạn]" if cnt["overdue"] else ""))

        # ---- thêm nhanh
        with st.form("tk_quick", clear_on_submit=True, border=False):
            title = st.text_input("Việc mới", placeholder="Thêm việc mới… (Enter để lưu)", label_visibility="collapsed")
            with st.expander("Nhãn · ưu tiên · hạn (tùy chọn)"):
                tag = st.selectbox("Nhãn (gõ nhãn mới hoặc chọn nhãn đã dùng)", tags, index=None,
                                   accept_new_options=True, placeholder="VD: KH B9, Việc cá nhân, Báo cáo")
                c1, c2 = st.columns(2)
                pri = c1.selectbox("Ưu tiên", tk.PRIORITIES, index=1)
                due = c2.date_input("Hạn xong", value=None, format="DD/MM/YYYY")
                note = st.text_input("Ghi chú")
            if st.form_submit_button("➕ Thêm", type="primary") and (title or "").strip():
                tk.add(title, "Chung", (tag or "").strip(), priority=pri, due=_iso(due), note=note or "")
                _bump()
                st.rerun()

        # ---- lọc
        f1, f2 = st.columns([3, 2])
        flt = f1.selectbox("Nhãn", ["Tất cả"] + tags, label_visibility="collapsed")
        show_done = f2.checkbox("Cả task xong", value=False)
        rows = [r for r in all_rows if (show_done or r["status"] != "Xong") and (flt == "Tất cả" or _tag(r, lm) == flt)]
        if not rows:
            st.caption("Chưa có task nào." if flt == "Tất cả" else "Không có task với nhãn này.")

        # ---- danh sách
        for r in rows[:30]:
            done = r["status"] == "Xong"
            c_chk, c_txt, c_more = st.columns([1, 7, 2], vertical_alignment="center")

            def _toggle(rid=r["id"], key=f"td_{r['id']}_{ver}"):
                tk.update(rid, status="Xong" if ss[key] else "Đang làm")
                _bump()

            c_chk.checkbox("xong", value=done, key=f"td_{r['id']}_{ver}", on_change=_toggle, label_visibility="collapsed")
            with c_txt:
                over = tk.is_overdue(r)
                head = f"~~{r['title']}~~" if done else r["title"]
                st.markdown(head)
                meta = [m for m in [_tag(r, lm), None if r["priority"] == "Thường" else r["priority"],
                                    r["status"] if r["status"] in ("Đang làm", "Chờ KH") else None] if m]
                if r["due"]:
                    d = date.fromisoformat(r["due"]).strftime("%d/%m")
                    meta.append((":red[⏰ " + d + "]") if over else "hạn " + d)
                if meta:
                    st.caption(" · ".join(meta))
            with c_more.popover("✎"):
                nt = st.text_input("Việc", r["title"], key=f"e_t_{r['id']}_{ver}")
                ns = st.selectbox("Trạng thái", tk.STATUSES, index=tk.STATUSES.index(r["status"]) if r["status"] in tk.STATUSES else 0,
                                  key=f"e_s_{r['id']}_{ver}")
                e1, e2 = st.columns(2)
                npri = e1.selectbox("Ưu tiên", tk.PRIORITIES, index=tk.PRIORITIES.index(r["priority"]) if r["priority"] in tk.PRIORITIES else 1,
                                    key=f"e_p_{r['id']}_{ver}")
                ndue = e2.date_input("Hạn", value=date.fromisoformat(r["due"]) if r["due"] else None,
                                     format="DD/MM/YYYY", key=f"e_d_{r['id']}_{ver}")
                cur_tag = _tag(r, lm)
                ntag = st.selectbox("Nhãn", sorted(set(tags) | ({cur_tag} if cur_tag else set())),
                                    index=(sorted(set(tags) | {cur_tag}).index(cur_tag) if cur_tag else None),
                                    accept_new_options=True, key=f"e_g_{r['id']}_{ver}")
                nn = st.text_area("Ghi chú", r["note"] or "", key=f"e_n_{r['id']}_{ver}", height=70)
                b1, b2 = st.columns(2)
                if b1.button("Lưu", key=f"e_save_{r['id']}_{ver}", type="primary"):
                    f = dict(title=(nt or "").strip() or r["title"], priority=npri, due=_iso(ndue), note=nn or "")
                    if ntag != cur_tag:
                        f.update(scope="Chung", target=(ntag or "").strip())
                    if ns != r["status"]:
                        f["status"] = ns
                    tk.update(r["id"], **f)
                    _bump()
                    st.rerun()
                if b2.button("Xóa", key=f"e_del_{r['id']}_{ver}"):
                    tk.delete(r["id"])
                    _bump()
                    st.rerun()
        if len(rows) > 30:
            st.caption(f"… còn {len(rows) - 30} task nữa, lọc theo nhãn để xem.")

"""Archive: kho file mẫu (upload để tải về in) và kho mẫu trả lời (email, tin nhắn)."""
import json
import re
from pathlib import Path
from urllib.parse import quote

import streamlit as st

from core import db

st.title("Archive")

ARCHIVE_DIR = db.DB_PATH.parent / "archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
CHANNELS = ["Email", "Tin nhắn (Zalo/SMS)", "Khác"]
NEW_CAT = "➕ Danh mục mới…"
VAR_RE = re.compile(r"\{([A-Za-z0-9_]+)\}")


def _q(sql: str, args: tuple = ()) -> list[dict]:
    with db.conn() as c:
        return [dict(r) for r in c.execute(sql, args)]


def _exec(sql: str, args: tuple = ()) -> int:
    with db.conn() as c:
        return c.execute(sql, args).lastrowid


def _safe(name: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE).strip("._") or "file"


def _size(n: int) -> str:
    return f"{n/1024/1024:.1f} MB" if n >= 1024 * 1024 else f"{max(n/1024, 0.1):.0f} KB"


def _folders() -> list[str]:
    try:
        return [x for x in json.loads(db.get_text("archive_folders", "[]")) if x]
    except Exception:  # noqa: BLE001
        return []


def _save_folders(lst: list[str]) -> None:
    db.set_text("archive_folders", json.dumps(sorted(set(lst)), ensure_ascii=False))


def _cat_picker(label: str, table: str, key: str, current: str = "") -> str:
    cats = {r["category"] for r in _q(f"SELECT DISTINCT category FROM {table} WHERE category!=''")}
    if table == "archive_files":
        cats |= set(_folders())
    cats = sorted(cats)
    opts = cats + [NEW_CAT]
    idx = opts.index(current) if current in opts else (len(opts) - 1 if not cats else 0)
    sel = st.selectbox(label, opts, index=idx, key=f"{key}_sel")
    if sel == NEW_CAT:
        return st.text_input("Tên danh mục mới", value=current if current not in cats else "", key=f"{key}_new",
                             placeholder="Ví dụ: Mở tài khoản, Margin, Rút tiền…").strip()
    return sel


tab_files, tab_replies = st.tabs(["File mẫu", "Format mẫu trả lời"])

# ====================================================================== File mẫu
with tab_files:
    st.caption("Lưu các file mẫu trống (Word, PDF, Excel…) để khi cần tải về cho KH in.")
    files = _q("SELECT * FROM archive_files ORDER BY category, name")

    with st.expander("➕ Thêm file mẫu", expanded=not files):
        ups = st.file_uploader("Chọn file (có thể chọn nhiều file)", accept_multiple_files=True, key="af_up")
        one = len(ups) == 1
        nm = st.text_input("Tên hiển thị", value=Path(ups[0].name).stem if one else "", key=f"af_name_{ups[0].name if one else ''}",
                           disabled=not one, placeholder="Mỗi file dùng tên gốc" if not one else "")
        cat = _cat_picker("Lưu vào thư mục", "archive_files", "af_cat")
        note = st.text_input("Ghi chú (dùng cho trường hợp nào, lưu ý khi in…)", key="af_note")
        if st.button("Lưu file mẫu", type="primary", disabled=not ups, key="af_save"):
            for u in ups:
                fid = _exec("INSERT INTO archive_files(name,category,note,filename,stored,size,uploaded_at) VALUES(?,?,?,?,?,?,?)",
                            ((nm if one and nm else Path(u.name).stem), cat, note, u.name, "", u.size, db.now()))
                stored = f"{fid}_{_safe(u.name)}"
                (ARCHIVE_DIR / stored).write_bytes(u.getvalue())
                _exec("UPDATE archive_files SET stored=? WHERE id=?", (stored, fid))
            st.success(f"Đã lưu {len(ups)} file.")
            st.rerun()

    with st.expander("📁 Quản lý thư mục (tạo thư mục theo chủ đề)"):
        n1, n2 = st.columns([3, 1])
        newf = n1.text_input("Tên thư mục mới", key="afd_new", placeholder="Ví dụ: Mở tài khoản, Margin, Rút tiền…").strip()
        n2.write("")
        n2.write("")
        if n2.button("Tạo thư mục", type="primary", key="afd_create", disabled=not newf):
            if newf in _folders() or any(f["category"] == newf for f in files):
                st.warning("Thư mục này đã có.")
            else:
                _save_folders(_folders() + [newf])
                st.rerun()
        allf = sorted(set(_folders()) | {f["category"] for f in files if f["category"]})
        if not allf:
            st.caption("Chưa có thư mục nào.")
        for fd in allf:
            cnt = sum(1 for f in files if f["category"] == fd)
            r1, r2, r3 = st.columns([3, 3, 2])
            r1.markdown(f"📁 **{fd}** · {cnt} file")
            rn = r2.text_input("Đổi tên", value=fd, key=f"afd_rn_{fd}", label_visibility="collapsed")
            with r3:
                if st.button("Đổi tên", key=f"afd_rnb_{fd}", disabled=not rn.strip() or rn.strip() == fd):
                    _exec("UPDATE archive_files SET category=? WHERE category=?", (rn.strip(), fd))
                    _save_folders([x for x in _folders() if x != fd] + [rn.strip()])
                    st.rerun()
                with st.popover("🗑 Xóa"):
                    st.caption("Xóa thư mục, các file bên trong chuyển về “Chưa phân loại” (không bị xóa).")
                    if st.button("Xác nhận xóa thư mục", key=f"afd_del_{fd}"):
                        _exec("UPDATE archive_files SET category='' WHERE category=?", (fd,))
                        _save_folders([x for x in _folders() if x != fd])
                        st.rerun()

    if not files:
        st.info("Chưa có file mẫu nào. Bấm “Thêm file mẫu” ở trên để tải lên.")
    else:
        c1, c2 = st.columns([2, 1])
        kw = c1.text_input("Tìm theo tên / ghi chú", key="af_kw").strip().lower()
        cats = sorted({f["category"] for f in files if f["category"]} | set(_folders()))
        fc = c2.selectbox("Thư mục", ["Tất cả"] + cats + (["(chưa phân loại)"] if any(not f["category"] for f in files) else []),
                          key="af_fc")
        shown = [f for f in files
                 if (not kw or kw in f["name"].lower() or kw in (f["note"] or "").lower() or kw in f["filename"].lower())
                 and (fc == "Tất cả" or (fc == "(chưa phân loại)" and not f["category"]) or f["category"] == fc)]
        st.caption(f"{len(shown)}/{len(files)} file")
        def file_card(f):
            path = ARCHIVE_DIR / f["stored"]
            with st.container(border=True):
                a, b, c_ = st.columns([5, 2, 1])
                a.markdown(f"**{f['name']}**" + (f"  ·  `{f['category']}`" if f["category"] else ""))
                a.caption(f"{f['filename']} · {_size(f['size'])} · {f['uploaded_at'] or ''}"
                          + (f"  \n{f['note']}" if f["note"] else ""))
                if path.exists():
                    b.download_button("⬇ Tải về", data=path.read_bytes(), file_name=f["filename"], key=f"af_dl_{f['id']}")
                else:
                    b.warning("Mất file gốc")
                with c_.popover("⋯"):
                    new_name = st.text_input("Tên hiển thị", value=f["name"], key=f"af_en_{f['id']}")
                    new_cat = _cat_picker("Danh mục", "archive_files", f"af_ec_{f['id']}", f["category"])
                    new_note = st.text_input("Ghi chú", value=f["note"] or "", key=f"af_eno_{f['id']}")
                    rep = st.file_uploader("Thay file mới (tuỳ chọn)", key=f"af_rep_{f['id']}")
                    if st.button("Lưu thay đổi", key=f"af_es_{f['id']}"):
                        if rep is not None:
                            if path.exists():
                                path.unlink()
                            stored = f"{f['id']}_{_safe(rep.name)}"
                            (ARCHIVE_DIR / stored).write_bytes(rep.getvalue())
                            _exec("UPDATE archive_files SET filename=?, stored=?, size=?, uploaded_at=? WHERE id=?",
                                  (rep.name, stored, rep.size, db.now(), f["id"]))
                        _exec("UPDATE archive_files SET name=?, category=?, note=? WHERE id=?",
                              (new_name or f["name"], new_cat, new_note, f["id"]))
                        st.rerun()
                    st.divider()
                    if st.checkbox("Xác nhận xóa file này", key=f"af_cf_{f['id']}"):
                        if st.button("🗑 Xóa", key=f"af_del_{f['id']}"):
                            if path.exists():
                                path.unlink()
                            _exec("DELETE FROM archive_files WHERE id=?", (f["id"],))
                            st.rerun()


        order = sorted(set(cats) if fc == "Tất cả" else {fc if fc != "(chưa phân loại)" else ""})
        if fc == "Tất cả" or fc == "(chưa phân loại)":
            order = [c_ for c_ in order if c_] + [""]
        for fd in order:
            inside = [f for f in shown if (f["category"] or "") == fd]
            if not inside and (kw or fd == ""):
                continue
            with st.expander(f"📁 {fd or 'Chưa phân loại'} ({len(inside)})", expanded=bool(kw) or fc != "Tất cả" or len(order) <= 3):
                if not inside:
                    st.caption("Thư mục trống. Thêm file ở trên rồi chọn thư mục này.")
                for f in inside:
                    file_card(f)

# ====================================================================== Format mẫu trả lời
with tab_replies:
    st.caption("Lưu email, câu trả lời mẫu. Trong nội dung dùng `{ten_kh}`, `{stk}`… để điền nhanh khi dùng mẫu.")

    def reply_form(prefix: str, r: dict | None = None):
        r = r or {}
        c1, c2 = st.columns(2)
        name = c1.text_input("Tên mẫu *", value=r.get("name", ""), key=f"{prefix}_name",
                             placeholder="Ví dụ: Email CS mở tài khoản")
        with c2:
            cat = _cat_picker("Danh mục", "archive_replies", f"{prefix}_cat", r.get("category", ""))
        c3, c4, c5 = st.columns(3)
        channel = c3.selectbox("Kênh", CHANNELS, index=CHANNELS.index(r["channel"]) if r.get("channel") in CHANNELS else 0,
                               key=f"{prefix}_ch")
        to_addr = c4.text_input("Gửi đến (To)", value=r.get("to_addr", ""), key=f"{prefix}_to",
                                placeholder="cs@hsc.com.vn")
        cc_addr = c5.text_input("CC", value=r.get("cc_addr", ""), key=f"{prefix}_cc")
        subject = st.text_input("Tiêu đề", value=r.get("subject", ""), key=f"{prefix}_sub")
        body = st.text_area("Nội dung", value=r.get("body", ""), height=240, key=f"{prefix}_body",
                            placeholder="Kính gửi Customer Service,\n\nĐề nghị mở tài khoản cho KH {ten_kh}, CCCD {cccd}…")
        note = st.text_input("Ghi chú (khi nào dùng, lưu ý)", value=r.get("note", ""), key=f"{prefix}_note")
        return dict(name=name.strip(), category=cat, channel=channel, to_addr=to_addr.strip(), cc_addr=cc_addr.strip(),
                    subject=subject, body=body, note=note)

    with st.expander("➕ Tạo mẫu mới", expanded=not _q("SELECT id FROM archive_replies LIMIT 1")):
        nv = reply_form("rn")
        if st.button("Lưu mẫu", type="primary", key="rn_save", disabled=not nv["name"] or not nv["body"]):
            _exec("INSERT INTO archive_replies(name,category,channel,to_addr,cc_addr,subject,body,note,updated_at) "
                  "VALUES(?,?,?,?,?,?,?,?,?)", (*nv.values(), db.now()))
            for k in [k for k in st.session_state if k.startswith("rn_")]:
                del st.session_state[k]
            st.success("Đã lưu mẫu.")
            st.rerun()

    reps = _q("SELECT * FROM archive_replies ORDER BY category, name")
    if not reps:
        st.info("Chưa có mẫu trả lời nào. Tạo mẫu đầu tiên ở trên (ví dụ email cho Customer Service khi mở tài khoản).")
    else:
        c1, c2, c3 = st.columns([2, 1, 1])
        kw = c1.text_input("Tìm mẫu", key="ar_kw").strip().lower()
        cats = sorted({r["category"] for r in reps if r["category"]})
        fc = c2.selectbox("Danh mục", ["Tất cả"] + cats, key="ar_fc")
        fch = c3.selectbox("Kênh", ["Tất cả"] + CHANNELS, key="ar_fch")
        shown = [r for r in reps if (not kw or kw in (r["name"] + r["subject"] + r["body"]).lower())
                 and (fc == "Tất cả" or r["category"] == fc) and (fch == "Tất cả" or r["channel"] == fch)]
        if not shown:
            st.caption("Không có mẫu khớp bộ lọc.")
        else:
            pick = st.selectbox("Chọn mẫu", [r["id"] for r in shown], key="ar_pick",
                                format_func=lambda i: next(f"{r['category'] + ' / ' if r['category'] else ''}{r['name']}"
                                                           for r in shown if r["id"] == i))
            r = next(x for x in shown if x["id"] == pick)
            mode = st.radio("Chế độ", ["Dùng mẫu", "Sửa mẫu"], horizontal=True, key=f"ar_mode_{pick}", label_visibility="collapsed")
            if mode == "Dùng mẫu":
                if r["note"]:
                    st.info(r["note"])
                vars_ = list(dict.fromkeys(VAR_RE.findall(" ".join([r["subject"], r["body"], r["to_addr"], r["cc_addr"]]))))
                vals = {}
                if vars_:
                    st.markdown("**Điền thông tin** (bỏ trống thì giữ nguyên `{tên}` trong nội dung)")
                    cols = st.columns(min(len(vars_), 3))
                    for i, v in enumerate(vars_):
                        vals[v] = cols[i % len(cols)].text_input(v, key=f"ar_v_{pick}_{v}")

                def fill(s: str) -> str:
                    return VAR_RE.sub(lambda m: vals.get(m.group(1)) or m.group(0), s)

                if r["to_addr"]:
                    st.markdown("**Đến:**")
                    st.code(fill(r["to_addr"]), language=None)
                if r["cc_addr"]:
                    st.markdown("**CC:**")
                    st.code(fill(r["cc_addr"]), language=None)
                if r["subject"]:
                    st.markdown("**Tiêu đề:**")
                    st.code(fill(r["subject"]), language=None)
                st.markdown("**Nội dung:**")
                st.code(fill(r["body"]), language=None)
                st.caption("Bấm biểu tượng sao chép ở góc phải mỗi khung.")
                if r["channel"] == "Email":
                    href = (f"mailto:{quote(fill(r['to_addr']))}?subject={quote(fill(r['subject']))}"
                            f"&body={quote(fill(r['body']))}" + (f"&cc={quote(fill(r['cc_addr']))}" if r["cc_addr"] else ""))
                    st.link_button("✉ Mở trong ứng dụng email", href)
            else:
                ed = reply_form(f"re_{pick}", r)
                b1, b2, b3 = st.columns(3)
                if b1.button("Lưu thay đổi", type="primary", key=f"re_save_{pick}", disabled=not ed["name"]):
                    _exec("UPDATE archive_replies SET name=?,category=?,channel=?,to_addr=?,cc_addr=?,subject=?,body=?,note=?,"
                          "updated_at=? WHERE id=?", (*ed.values(), db.now(), pick))
                    st.rerun()
                if b2.button("Nhân bản", key=f"re_dup_{pick}"):
                    _exec("INSERT INTO archive_replies(name,category,channel,to_addr,cc_addr,subject,body,note,updated_at) "
                          "VALUES(?,?,?,?,?,?,?,?,?)", (ed["name"] + " (bản sao)", *list(ed.values())[1:], db.now()))
                    st.rerun()
                with b3.popover("Xóa mẫu"):
                    if st.button("Xác nhận xóa", key=f"re_del_{pick}"):
                        _exec("DELETE FROM archive_replies WHERE id=?", (pick,))
                        st.rerun()

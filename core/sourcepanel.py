import io

import pandas as pd
import streamlit as st

from core import db, groupstore, service
from core.importer import parse_workbook
from core.service import fmt_pct, fmt_vnd

NEW = "➕ Nhóm mới..."


def group_picker(key: str, label: str = "Nhóm") -> str:
    """Chọn nhóm có sẵn (thư mục đã tạo, nhóm trong danh bạ) hoặc gõ tên nhóm mới."""
    opts = list(dict.fromkeys(groupstore.groups() + sorted({v["grp"] for v in db.directory().values() if v["grp"]})))
    last = st.session_state.get("last_group")
    idx = opts.index(last) if last in opts else 0
    sel = st.selectbox(label, opts + [NEW], index=idx if opts else 0, key=f"{key}_sel")
    if sel == NEW or not opts:
        sel = st.text_input("Tên nhóm mới", key=f"{key}_new", placeholder="Ví dụ: G39, QT, Nhóm Nh...")
    sel = groupstore.safe(sel) if sel else ""
    if sel:
        st.session_state["last_group"] = sel
    return sel


def _preview(customers, prices, warns):
    """Bảng xem trước: mỗi KH một nhóm dòng gồm Tên CP, SLCP; kèm số dư nợ, NAV, tỉ lệ MR của KH."""
    from core.margin import Position, compute
    px_db = service.prices()
    s = service.settings()
    rows = []
    for i, c in enumerate(customers, 1):
        pos = [Position(p["ticker"], p["qty"], prices.get(p["ticker"]) or px_db.get(p["ticker"], 0.0), p["im_pct"],
                        p.get("limit", 0.0)) for p in c["positions"]]
        r = compute(c["cash"], pos, c["mm"] or s.default_mm, s)
        first = True
        for p in (c["positions"] or [{"ticker": "", "qty": None}]):
            rows.append({
                "STT": str(i) if first else "", "Tài khoản": service.acct_label(c["name"], c["account_no"]) if first else "",
                "Tên CP": p["ticker"], "SLCP": fmt_vnd(p["qty"]) if p["qty"] is not None else "",
                "Số dư nợ": fmt_vnd(max(0.0, -c["cash"])) if first else "",
                "NAV": fmt_vnd(r["nav"]) if first else "",
                "Tỉ lệ MR": fmt_pct(r["mr"]) if first else ""})
            first = False
    st.write(f"Tìm thấy **{len(customers)}** khách hàng và **{len(prices)}** mã.")
    if warns:
        with st.expander(f"{len(warns)} cảnh báo cần xem", expanded=False):
            for w in warns:
                st.write("• " + w)
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("Số dư nợ = số dư tiền âm. NAV và tỉ lệ MR tính theo giá trong file (mã thiếu giá dùng giá đang lưu trong app).")


def _set_active(raw: bytes) -> None:
    """File vừa nạp trở thành file gốc để xuất lại Excel."""
    path = db.DB_PATH.parent / "daily_original.xlsx"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(raw)


def _load(customers, prices, group, replace):
    n, m = db.import_customers(customers, prices)
    names = [c["name"] for c in customers]
    if group:
        db.set_group_for(names, group)
    removed = db.drop_customers_not_in(names) if replace else []
    return n, m, removed


def render() -> None:
    st.caption(f"File được lưu trong thư mục riêng của từng nhóm: `{groupstore.root()}`")
    mode = st.radio("Lấy dữ liệu từ đâu?", ["Dữ liệu đã lưu theo nhóm", "Tải file lên"], horizontal=True, key="src_mode")

    if mode.startswith("Dữ liệu"):
        gs = groupstore.groups()
        if not gs:
            st.info("Chưa có file nào được lưu. Hãy chọn **Tải file lên** (bật lưu vào thư mục nhóm) hoặc lưu từ trang Báo cáo hằng ngày.")
        else:
            c1, c2 = st.columns([1, 2])
            g = c1.selectbox("Nhóm", gs, key="src_g")
            fl = groupstore.files(g)
            if not fl:
                c2.info("Thư mục nhóm này chưa có file.")
            else:
                f = c2.selectbox("File", fl, format_func=groupstore.label, key=f"src_f_{g}")
                r1, r2 = st.columns([3, 1])
                nn = r1.text_input("Đổi tên file (không cần đuôi .xlsx)", value=f["orig"], key=f"src_rn_{g}_{f['name']}")
                r2.write("")
                r2.write("")
                if r2.button("Đổi tên", key="src_rn_btn", disabled=not nn.strip() or nn.strip() == f["orig"]):
                    try:
                        groupstore.rename(g, f["name"], nn)
                        st.rerun()
                    except FileExistsError:
                        st.error("Đã có file trùng tên này trong thư mục nhóm.")
                replace = st.checkbox("Thay thế: chỉ giữ các KH trong file này, bỏ KH khác đang có", value=False, key="src_rep1")
                try:
                    cs, pxs, warns = parse_workbook(io.BytesIO(groupstore.read(g, f["name"])))
                except Exception as e:  # noqa: BLE001
                    st.error(f"Không đọc được file: {e}")
                    cs = None
                if cs is not None:
                    _preview(cs, pxs, warns)
                    if st.button("Nạp dữ liệu này vào hệ thống", type="primary", key="src_load"):
                        n, m, rm = _load(cs, pxs, g, replace)
                        _set_active(groupstore.read(g, f["name"]))
                        st.success(f"Đã nạp {n} KH và {m} giá từ nhóm {g}." + (f" Đã bỏ {len(rm)} KH khác." if rm else ""))
                        st.rerun()
    else:
        group = group_picker("src_up")
        up = st.file_uploader("File Excel (mỗi sheet là một KH)", type=["xlsx"], key="src_file")
        if up is not None:
            try:
                cs, pxs, warns = parse_workbook(io.BytesIO(up.getvalue()))
            except Exception as e:  # noqa: BLE001
                st.error(f"Không đọc được file: {e}")
                cs = None
            if cs is not None:
                _preview(cs, pxs, warns)
                a, b = st.columns(2)
                keep = a.checkbox("Lưu file vào thư mục nhóm", value=True, key="src_keep", disabled=not group)
                fname = st.text_input("Tên file lưu (không cần đuôi .xlsx)", value=up.name.rsplit(".", 1)[0], key=f"src_name_{up.name}")
                replace = b.checkbox("Thay thế: chỉ giữ các KH trong file này", value=False, key="src_rep2")
                if keep and not group:
                    st.warning("Nhập tên nhóm để lưu file.")
                if st.button("Xác nhận import", type="primary", key="src_import"):
                    n, m, rm = _load(cs, pxs, group, replace)
                    _set_active(up.getvalue())
                    if keep and group:
                        groupstore.save(group, up.getvalue(), "goc", fname or up.name)
                    st.success(f"Đã nạp {n} KH và {m} giá." + (f" Đã lưu file vào nhóm {group}." if keep and group else ""))
                    st.rerun()

    with st.expander("🧹 Xóa dữ liệu không mong muốn"):
        st.markdown("**Khách hàng đang nạp trong hệ thống**")
        custs = service.load_customers()
        lm = {c["name"]: service.acct_label(c["name"], c["account_no"]) + (f" · {c['group_name']}" if c.get("group_name") else "")
              for c in custs}
        pick = st.multiselect("Chọn KH cần xóa", list(lm), format_func=lambda n: lm[n], key="clr_c")
        ok1 = st.checkbox("Tôi chắc chắn muốn xóa các KH đã chọn khỏi hệ thống", key="clr_ok1")
        x1, x2 = st.columns(2)
        if x1.button("Xóa KH đã chọn", disabled=not (pick and ok1), key="clr_btn1"):
            st.success(f"Đã xóa {db.delete_customers(pick)} KH.")
            st.rerun()
        ok_all = x2.checkbox("Xóa TẤT CẢ KH (dọn sạch để nạp lại)", key="clr_okall")
        if x2.button("Xóa tất cả KH", disabled=not ok_all, key="clr_all"):
            st.success(f"Đã xóa {db.delete_customers([c['name'] for c in custs])} KH.")
            st.rerun()
        st.caption("Chỉ xóa dữ liệu KH và danh mục trong hệ thống. Lịch sử NAV và các file đã lưu theo nhóm không bị ảnh hưởng.")

        st.divider()
        st.markdown("**File đã lưu theo nhóm**")
        gs = groupstore.groups()
        if not gs:
            st.caption("Chưa có file nào được lưu.")
        else:
            g = st.selectbox("Nhóm", gs, key="clr_g")
            fl = groupstore.files(g)
            fp = st.multiselect("Chọn file cần xóa", [f["name"] for f in fl],
                                format_func=lambda n: groupstore.label(next(f for f in fl if f["name"] == n)), key=f"clr_f_{g}")
            ok2 = st.checkbox("Tôi chắc chắn muốn xóa các file đã chọn (không khôi phục được)", key="clr_ok2")
            y1, y2 = st.columns(2)
            if y1.button("Xóa file đã chọn", disabled=not (fp and ok2), key="clr_btn2"):
                for n in fp:
                    groupstore.delete_file(g, n)
                st.success(f"Đã xóa {len(fp)} file.")
                st.rerun()
            ok3 = y2.checkbox(f"Xóa cả thư mục nhóm {g}", key="clr_ok3")
            if y2.button("Xóa thư mục nhóm", disabled=not ok3, key="clr_btn3"):
                groupstore.delete_group(g)
                st.success(f"Đã xóa thư mục nhóm {g}.")
                st.rerun()

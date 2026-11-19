from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from core import db, news, service

st.title("Cài đặt")

st.subheader("Ngưỡng margin")
s = service.settings()
with st.form("thr"):
    a, b, c_, d = st.columns(4)
    fs = a.number_input("FS khi MR dưới (%)", value=s.fs_threshold * 100, step=0.5)
    cl = b.number_input("Call khi MR dưới (%)", value=s.call_threshold * 100, step=0.5)
    tg = c_.number_input("Đưa MR về (%) khi tính tiền nộp", value=s.call_target * 100, step=0.5)
    mm = d.number_input("Tỷ lệ tài khoản mặc định", value=s.default_mm, step=0.05, min_value=0.1, max_value=1.0)
    if st.form_submit_button("Lưu ngưỡng", type="primary"):
        db.set_setting("fs_threshold", fs / 100)
        db.set_setting("call_threshold", cl / 100)
        db.set_setting("call_target", tg / 100)
        db.set_setting("default_mm", mm)
        st.success("Đã lưu.")
        st.rerun()
st.caption("Giá trị mặc định lấy từ file Excel của bạn: 40% / 50% / 50.5%. "
           "Lưu ý: trong file, tỷ lệ tài khoản từng KH (ô A23) là 55% hoặc 60% nhưng ngưỡng call lại cố định 50%. "
           "Hãy chốt số đúng theo chính sách công ty rồi chỉnh ở đây.")

st.subheader("Danh bạ khách hàng (tra cứu số tài khoản / tên)")
kd_ = db.directory()
q_ = st.text_input("Tìm theo số tài khoản, tên hoặc nhóm", key="kd_q")
kdf = pd.DataFrame([{"Số tài khoản": v["account_no"], "Tên khách hàng": v["full_name"], "Tên gọi": v["short_name"],
                     "Nhóm": v["grp"]} for v in kd_.values()], columns=["Số tài khoản", "Tên khách hàng", "Tên gọi", "Nhóm"])
if q_.strip():
    m_ = kdf.apply(lambda r: q_.strip().lower() in " ".join(map(str, r.values)).lower(), axis=1)
    kdf = kdf[m_]
st.dataframe(kdf, hide_index=True, width="stretch")
st.caption(f"{len(kd_)} tài khoản trong danh bạ. Tên gọi là từ cuối của họ tên (Bùi Duy Cường thành Cường), tài khoản tổ chức giữ tên đầy đủ. "
           "Danh bạ dùng để hiện tên khi đọc ảnh OPT và trên Dashboard NAV.")
kup = st.file_uploader("Cập nhật danh bạ từ file CSV (cột Nhóm, Số tài khoản, Tên khách hàng)", type=["csv"], key="kd_up")
if kup is not None and st.button("Nạp danh bạ", key="kd_btn"):
    import csv, io
    rows_ = list(csv.DictReader(io.StringIO(kup.getvalue().decode("utf-8-sig"))))
    st.success(f"Đã nạp {db.import_directory(rows_)} tài khoản.")
    st.rerun()

st.subheader("Danh sách CTCK và mã ID (lệnh thỏa thuận)")
import pandas as _pd
from core import ctck as _ctck
_cdf = _pd.DataFrame(_ctck.entries(), columns=["ID", "Tên CTCK"])
_ced = st.data_editor(_cdf, num_rows="dynamic", hide_index=True, width="stretch", key="ctck_ed",
                      column_config={"ID": st.column_config.TextColumn(help="Dạng 007 - 00071"),
                                     "Tên CTCK": st.column_config.TextColumn()})
_b1, _b2 = st.columns([1, 1])
if _b1.button("Lưu danh sách CTCK", type="primary", key="ctck_save"):
    _ctck.save([(r["ID"], r["Tên CTCK"]) for _, r in _ced.iterrows() if r["ID"] and r["Tên CTCK"]])
    st.success("Đã lưu danh sách CTCK.")
if _b2.button("Khôi phục danh sách mặc định", key="ctck_reset"):
    _ctck.reset()
    st.rerun()
st.caption("Một CTCK có thể có nhiều ID (ví dụ CTS): thêm mỗi ID một dòng, cùng tên CTCK. Khi soạn thỏa thuận bạn chọn tên CTCK rồi chọn ID.")

st.subheader("Nguồn tin RSS")
with db.conn() as c:
    feeds = pd.DataFrame([dict(r) for r in c.execute("SELECT url, name, enabled FROM feeds")])
if feeds.empty:
    feeds = pd.DataFrame(columns=["url", "name", "enabled"])
feeds["enabled"] = feeds["enabled"].astype(bool)
ed = st.data_editor(feeds, num_rows="dynamic", hide_index=True, width="stretch",
                    column_config={"url": "Địa chỉ RSS", "name": "Tên nguồn",
                                   "enabled": st.column_config.CheckboxColumn("Bật")})
c1, c2 = st.columns(2)
if c1.button("Lưu nguồn tin"):
    with db.conn() as c:
        c.execute("DELETE FROM feeds")
        for _, r in ed.dropna(subset=["url"]).iterrows():
            if str(r["url"]).strip():
                c.execute("INSERT OR REPLACE INTO feeds(url,name,enabled) VALUES(?,?,?)",
                          (r["url"].strip(), r["name"] or r["url"], int(bool(r["enabled"]))))
    st.success("Đã lưu.")
if c2.button("Kiểm tra từng nguồn"):
    for _, r in ed.dropna(subset=["url"]).iterrows():
        ok, msg = news.test_feed(r["url"])
        (st.success if ok else st.error)(f"{r['name']}: {msg}")
st.caption("Địa chỉ RSS mặc định chưa được kiểm tra trên máy bạn. Hãy bấm Kiểm tra, "
           "nguồn nào lỗi thì sửa hoặc tắt.")

with st.expander("Tìm RSS tự động từ địa chỉ trang web"):
    st.caption("Dán địa chỉ trang (mỗi dòng một trang). Website tìm thẻ RSS và thử các đường dẫn phổ biến "
               "ngay trên máy bạn, chỉ hiện feed đọc được. Trang nào không có RSS thì sẽ không ra kết quả.")
    sites = st.text_area("Các trang cần tìm RSS", value="https://www.tinnhanhchungkhoan.vn/\nhttps://antt.nguoiduatin.vn/",
                         height=90, key="disc_sites")
    if st.button("Tìm RSS"):
        found = {}
        with st.spinner("Đang tìm..."):
            for line in [x.strip() for x in sites.splitlines() if x.strip()]:
                found[line] = news.discover_feeds(line)
        st.session_state["disc_found"] = found
    for site, items in st.session_state.get("disc_found", {}).items():
        if not items:
            st.warning(f"{site}: không tìm thấy RSS đọc được (trang có thể không cung cấp RSS).")
            continue
        st.markdown(f"**{site}**")
        for i, (u, desc) in enumerate(items):
            c_a, c_b = st.columns([5, 1])
            c_a.markdown(f"`{u}`  \n{desc}")
            if c_b.button("Thêm", key=f"disc_add_{site}_{i}"):
                nm = urlparse(site).netloc.replace("www.", "") + " - " + (urlparse(u).path.strip("/") or "RSS")
                with db.conn() as c:
                    c.execute("INSERT OR IGNORE INTO feeds(url,name) VALUES(?,?)", (u, nm))
                st.success(f"Đã thêm {u}. Tải lại trang để thấy trong bảng nguồn tin.")

st.subheader("Sao lưu dữ liệu")
if db.DB_PATH.exists():
    st.download_button("Tải file sao lưu (workspace.db)", data=db.DB_PATH.read_bytes(),
                       file_name=f"workspace_{db.now()[:10]}.db")
st.caption(f"Dữ liệu nằm tại: {db.DB_PATH}")

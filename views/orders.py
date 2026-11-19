import pandas as pd
import streamlit as st

from core import db, service

st.title("Sổ lệnh")
from core import ttpanel
tab_o, tab_tt = st.tabs(["Sổ lệnh", "Lệnh thỏa thuận"])
with tab_tt:
    ttpanel.render()
with tab_o:
    st.caption("Chỉ ghi nhận và nhắc việc. Lệnh thật vẫn đặt trên hệ thống công ty.")

    STATUSES = ["Chờ đặt", "Đã đặt", "Khớp một phần", "Khớp hết", "Hủy", "Từ chối"]
    TYPES = ["LO", "ATO", "ATC", "MP", "MTL", "MOK", "MAK", "PLO"]
    CHANNELS = ["Gọi điện", "Zalo", "Trực tiếp", "Khác"]

    custs = service.load_customers()
    names = [c["name"] for c in custs]
    LM = service.label_map()
    lab = lambda n: LM.get(n, n)

    with st.form("new_order", clear_on_submit=True):
        st.markdown("**Ghi lệnh mới**")
        a, b, c_, d = st.columns(4)
        cust = a.selectbox("Khách hàng", names, format_func=lab) if names else a.text_input("Khách hàng")
        ticker = b.text_input("Mã").upper().strip()
        side = c_.selectbox("Mua/Bán", ["Mua", "Bán"])
        qty = d.number_input("Khối lượng", min_value=0, step=100)
        e, f, g, h = st.columns(4)
        price = e.number_input("Giá (0 nếu lệnh thị trường)", min_value=0, step=50)
        otype = f.selectbox("Loại lệnh", TYPES)
        session = g.selectbox("Phiên", ["Trong phiên", "Ngoài phiên"])
        channel = h.selectbox("Kênh nhận", CHANNELS)
        note = st.text_input("Ghi chú")
        if st.form_submit_button("Ghi lệnh", type="primary"):
            if not ticker or qty <= 0:
                st.error("Cần nhập mã và khối lượng.")
            else:
                cid = next((x["id"] for x in custs if x["name"] == cust), None)
                with db.conn() as c:
                    c.execute("INSERT INTO orders(created_at,customer_id,customer_name,ticker,side,qty,price,"
                              "order_type,session,channel,status,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                              (db.now(), cid, cust, ticker, side, qty, price, otype, session, channel, "Chờ đặt", note))
                st.success("Đã ghi lệnh.")
                st.rerun()

    st.divider()
    f1, f2, f3 = st.columns(3)
    fs = f1.multiselect("Trạng thái", STATUSES, default=["Chờ đặt", "Đã đặt", "Khớp một phần"])
    fk = f2.selectbox("Khách hàng", ["Tất cả"] + names, format_func=lambda n: n if n == "Tất cả" else lab(n))
    fp = f3.selectbox("Phiên", ["Tất cả", "Trong phiên", "Ngoài phiên"])

    q = "SELECT * FROM orders WHERE 1=1"
    args = []
    if fs:
        q += f" AND status IN ({','.join('?' * len(fs))})"
        args += fs
    if fk != "Tất cả":
        q += " AND customer_name=?"
        args.append(fk)
    if fp != "Tất cả":
        q += " AND session=?"
        args.append(fp)
    q += " ORDER BY created_at DESC LIMIT 500"
    with db.conn() as c:
        rows = [dict(r) for r in c.execute(q, args)]

    if not rows:
        st.caption("Không có lệnh nào khớp bộ lọc.")
    else:
        df = pd.DataFrame(rows)[["id", "created_at", "customer_name", "ticker", "side", "qty", "price",
                                  "order_type", "session", "channel", "status", "note"]]
        df["customer_name"] = df["customer_name"].map(lab)
        df.columns = ["id", "Nhận lúc", "KH", "Mã", "M/B", "KL", "Giá", "Loại", "Phiên", "Kênh", "Trạng thái", "Ghi chú"]
        ed = st.data_editor(df, hide_index=True, width="stretch",
                            disabled=[c for c in df.columns if c not in ("Trạng thái", "Ghi chú")],
                            column_config={"Trạng thái": st.column_config.SelectboxColumn(options=STATUSES, required=True)},
                            key="orders_ed")
        if st.button("Lưu thay đổi trạng thái"):
            with db.conn() as c:
                for _, r in ed.iterrows():
                    c.execute("UPDATE orders SET status=?, note=? WHERE id=?", (r["Trạng thái"], r["Ghi chú"] or "", int(r["id"])))
            st.success("Đã lưu.")
            st.rerun()

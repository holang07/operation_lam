from datetime import date

import pandas as pd
import streamlit as st

from core import db, service, ui
from core.service import fmt_vnd


def render() -> None:
    st.caption("Lịch sử NAV của khách hàng theo ngày, lưu mỗi khi bạn xác nhận báo cáo hằng ngày, đọc ảnh OPT hoặc bấm lưu NAV hôm nay.")

    res = service.compute_all()
    b1, b2 = st.columns([1, 3])
    if b1.button("💾 Lưu NAV hôm nay (số liệu hiện tại)", type="primary", disabled=not res):
        for r in res:
            cu = r["customer"]
            gttt = (r["nav"] - r["cash"]) if r["nav"] is not None and r["cash"] is not None else None
            db.save_nav(db.today(), db.acct_key(r["account_no"], r["name"]), r["name"], r["nav"], r["cash"], gttt, "app")
        st.success(f"Đã lưu NAV hôm nay của {len(res)} tài khoản.")
    b2.caption("Dùng số dư tiền và giá đang lưu trong app. Nếu hôm nay đã có số từ ảnh OPT thì bấm nút này sẽ ghi đè số đó.")

    hist = db.nav_history()
    if not hist:
        st.info("Chưa có lịch sử NAV. Bấm **Lưu NAV hôm nay**, hoặc xác nhận một tài khoản ở Báo cáo hằng ngày, "
                "hoặc dùng trang Đọc ảnh OPT rồi lưu.")
        return

    LM = {db.acct_key(c["account_no"], c["name"]): service.acct_label(c["name"], c["account_no"]) for c in service.load_customers()}
    df = pd.DataFrame(hist)
    KD = db.directory()
    df["label"] = df.apply(lambda r: LM.get(r["acct"])
                           or (service.acct_label(KD[r["acct"]]["short_name"], r["acct"]) if r["acct"] in KD else None)
                           or (service.acct_label(r["name"], r["acct"]) if r["name"] else r["acct"]), axis=1)

    f1, f2 = st.columns([3, 1])
    all_labels = sorted(df["label"].unique())
    chosen = f1.multiselect("Tài khoản", all_labels, default=all_labels, key="dash_acc")
    rng = f2.selectbox("Khoảng thời gian", ["30 ngày", "7 ngày", "90 ngày", "Tất cả"], key="dash_rng")
    if not chosen:
        st.info("Chọn ít nhất một tài khoản.")
        return
    df = df[df["label"].isin(chosen)]
    df["day"] = pd.to_datetime(df["day"])
    if rng != "Tất cả":
        df = df[df["day"] >= df["day"].max() - pd.Timedelta(days=int(rng.split()[0]))]

    nav = df.pivot_table(index="day", columns="label", values="nav", aggfunc="last").sort_index()
    nav_f = nav.ffill()                                  # ngày thiếu số của một tài khoản thì giữ số gần nhất
    total = nav_f.sum(axis=1)
    debt = df.pivot_table(index="day", columns="label", values="cash", aggfunc="last").sort_index().ffill().clip(upper=0).abs().sum(axis=1)

    last, prev = total.iloc[-1], (total.iloc[-2] if len(total) > 1 else None)
    chg = (last - prev) if prev is not None else None
    cards = [
        ui.stat_card("Tổng NAV", f"{last/1e9:,.2f} tỷ", f"ngày {total.index[-1].strftime('%d/%m/%Y')}", "blue"),
        ui.stat_card("So với ngày trước", "-" if chg is None else f"{chg/1e9:+,.2f} tỷ",
                     "chưa có ngày trước" if chg is None else f"{chg/prev*100:+.2f}%", "green" if (chg or 0) >= 0 else "red"),
        ui.stat_card("Tổng dư nợ", f"{debt.iloc[-1]/1e9:,.2f} tỷ", "theo số dư tiền âm", "orange"),
        ui.stat_card("Số tài khoản", len(nav.columns), f"{len(nav)} ngày có số liệu", "blue"),
    ]
    for col, h in zip(st.columns(4, gap="medium"), cards):
        col.markdown(h, unsafe_allow_html=True)
    st.write("")

    st.markdown("#### Tổng NAV theo ngày (tỷ VND)")
    st.line_chart((total / 1e9).rename("Tổng NAV"), height=280)
    st.markdown("#### NAV từng tài khoản (tỷ VND)")
    st.line_chart(nav_f / 1e9, height=320)

    with st.expander("Bảng số liệu NAV theo ngày", expanded=False):
        tb = nav_f.copy()
        tb["TỔNG"] = total
        tb = tb.sort_index(ascending=False)
        tb.index = tb.index.strftime("%d/%m/%Y")
        st.dataframe(tb.map(lambda v: "-" if pd.isna(v) else fmt_vnd(v)), width="stretch")
    st.caption("Một ngày chỉ có một số cho mỗi tài khoản (lưu lại trong ngày thì ghi đè). "
               "Tài khoản thiếu số ở một ngày được giữ số gần nhất trước đó khi cộng tổng.")


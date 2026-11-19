from datetime import date

import pandas as pd
import streamlit as st

from core import db, service, ui
from core import taskpanel, navpanel
from core.service import STATUS_LABEL, acct_label, fmt_pct, fmt_vnd

WEEKDAY = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "CN"]
today = date.today()
ui.page_header(
    f"{ui.greeting()}!",
    "Hôm nay bạn muốn xử lý gì? Số liệu margin là số tham khảo, đối chiếu hệ thống công ty trước khi xử lý.",
    f"{WEEKDAY[today.weekday()]}, {today.strftime('%d/%m/%Y')}",
)

res = service.compute_all()
s = service.settings()

if res:
    n = len(res)
    n_fs = sum(r["status"] == "fs" for r in res)
    n_call = sum(r["status"] == "call" for r in res)
    watch_zone = [r for r in res if r["status"] == "bình thường" and r["mr"] is not None
                  and r["mr"] < s.call_threshold + 0.10]
    n_ok = n - n_fs - n_call - len(watch_zone)
    pct = lambda k: 100.0 * k / n if n else 0.0

    cards = [
        ui.stat_card("Khách hàng", n, f"{n_ok} an toàn", "blue", pct(n_ok)),
        ui.stat_card("Đang Call", n_call, "cần nộp thêm", "orange", pct(n_call)),
        ui.stat_card("Đang FS", n_fs, "bán giải chấp", "red", pct(n_fs)),
        ui.stat_card("Gần ngưỡng", len(watch_zone), f"MR < {(s.call_threshold + 0.10) * 100:.0f}%", "green", pct(len(watch_zone))),
    ]
    cols = st.columns(4, gap="medium")
    for col, html_ in zip(cols, cards):
        col.markdown(html_, unsafe_allow_html=True)
    st.write("")


left, right = st.columns([2, 1], gap="large")


# ---------------- cột phải: thao tác nhanh + Archive ----------------
with right:
    with db.conn() as c:
        n_f = c.execute("SELECT COUNT(*) FROM archive_files").fetchone()[0]
        reps = c.execute("SELECT category, name FROM archive_replies ORDER BY updated_at DESC LIMIT 5").fetchall()
    body = "".join(
        ui.notice(r_["name"], r_["category"] or "", icon="✉️", tone="gray") for r_ in reps)
    ui.panel(f"Archive · {n_f} file mẫu", body, "Chưa có mẫu trả lời nào. Vào Archive để thêm.")

    taskpanel.render()   # Task cá nhân, nằm dưới khung Archive

# ---------------- cột trái ----------------
with left:
    if not res:
        st.info("Chưa có khách hàng. Vào **KH & Margin** để import file Excel của bạn.")
    else:
        watch_zone = [r for r in res if r["status"] == "bình thường" and r["mr"] is not None
                      and r["mr"] < s.call_threshold + 0.10]
        items = []
        for r in sorted(res, key=lambda x: (x["mr"] if x["mr"] is not None else 9)):
            near = r["status"] == "bình thường" and r["mr"] is not None and r["mr"] < s.call_threshold + 0.10
            if r["status"] == "bình thường" and not near:
                continue
            tone, icon, tag = (("blue", "🟡", "GẦN NGƯỠNG") if near else
                               ("red", "🔴", "FS") if r["status"] == "fs" else ("orange", "🟠", "CALL"))
            need = f" · cần nộp {fmt_vnd(r['call_amount'])}" if r["call_amount"] else ""
            items.append(ui.notice(f"{len(items) + 1}. " + acct_label(r["name"], r["account_no"]),
                                   f"MR {fmt_pct(r['mr'])} · NAV {fmt_vnd(r['nav'])}{need}",
                                   tag, tone, icon))
        more = len(items) - 8
        body = "".join(items[:8]) + (f'<div class="empty">… và {more} tài khoản khác (xem ở KH & Margin)</div>' if more > 0 else "")
        ui.panel("Cần xử lý / theo dõi sát", body, "Không có tài khoản nào dưới hoặc gần ngưỡng call. ✅")

    with st.container(border=True):
        st.markdown("#### Lệnh cần chú ý")
        with db.conn() as c:
            orders = c.execute(
                "SELECT created_at, customer_name, ticker, side, qty, price, order_type, session, status "
                "FROM orders WHERE status IN ('Chờ đặt','Đã đặt','Khớp một phần') "
                "ORDER BY (session='Ngoài phiên') DESC, created_at DESC").fetchall()
        if orders:
            lm_ = service.label_map()
            df = pd.DataFrame([dict(o) for o in orders])
            df["customer_name"] = df["customer_name"].map(lambda n: lm_.get(n, n))
            df = df.rename(columns={
                "created_at": "Nhận lúc", "customer_name": "KH", "ticker": "Mã", "side": "M/B",
                "qty": "KL", "price": "Giá", "order_type": "Loại", "session": "Phiên", "status": "Trạng thái"})
            st.dataframe(df, hide_index=True, width="stretch")
        else:
            st.caption("Không có lệnh đang chờ.")

    with db.conn() as c:
        news = c.execute("SELECT title, source, published, tickers, link FROM news WHERE tickers!='' "
                         "ORDER BY published DESC LIMIT 6").fetchall()
    body = "".join(ui.notice(n_["title"], n_["source"] or "", n_["tickers"], "blue", "📰",
                             when=(n_["published"] or "")[:16], link=n_["link"]) for n_ in news)
    ui.panel("Tin liên quan đến mã KH đang giữ", body, "Chưa có tin. Vào Tin tức và bấm Cập nhật tin.")

# ---------------- NAV theo ngày (dashboard) ----------------
st.divider()
st.subheader("Dashboard NAV")
navpanel.render()

import pandas as pd
import streamlit as st

from core import db, news, service

st.title("Tin tức: mã theo dõi, vĩ mô & ngành")

# Mã để tìm tin: danh mục cho vay (hoặc mã KH đang giữ nếu chưa import) + các mã bắt buộc.
loan = set(db.get_loan_list().keys())
universe = (loan or service.watchlist()) | set(news.PRIORITY) | set(news.RETAIL)
src = "danh mục cho vay" if loan else "mã KH đang giữ"

top1, top2, top3 = st.columns([1, 1, 2])
if top1.button("Cập nhật tin", type="primary"):
    if not universe:
        st.warning("Chưa có mã nào. Hãy import danh mục cho vay hoặc KH trước.")
    else:
        with st.spinner("Đang tải tin từ các nguồn..."):
            n, errs = news.fetch_all(universe)
            news.retag(universe)
        st.success(f"Có {n} tin mới.")
        for e in errs:
            st.warning(e)
if top2.button("Gắn lại mã cho tin đã lưu"):
    news.retag(universe)
    st.success("Đã gắn lại mã theo danh mục hiện tại.")
top3.caption(f"Mã bắt buộc: {', '.join(news.PRIORITY)}. Cộng thêm {len(universe - set(news.PRIORITY) - set(news.RETAIL))} mã khác từ {src}. "
             f"Chủ đề: {', '.join(news.TOPIC_KEYWORDS)}. Bán lẻ chủ yếu theo mã: {', '.join(news.RETAIL)}.")

# Mở trang lần đầu: gắn lại mã một lần cho tin đã lưu theo danh sách hiện tại
if universe and not st.session_state.get("news_retagged"):
    news.retag(universe)
    st.session_state["news_retagged"] = True

with db.conn() as c:
    all_rows = [dict(r) for r in c.execute(
        "SELECT * FROM news ORDER BY published DESC, fetched_at DESC LIMIT 600")]

# Mã nào có tin mới nhất thì đứng đầu danh sách lọc
latest: dict[str, str] = {}
for r in all_rows:
    for t in filter(None, r["tickers"].split(",")):
        latest.setdefault(t, r["published"] or "")
tick_order = sorted(latest, key=lambda t: latest[t], reverse=True)

f1, f2 = st.columns(2)
pick = f1.multiselect("Lọc theo mã (mã có tin mới nhất xếp trước)", tick_order)
pick_tp = f2.multiselect("Lọc theo chủ đề", list(news.TOPIC_KEYWORDS))
g1, g2 = st.columns(2)
only_match = g1.checkbox("Chỉ tin có mã hoặc chủ đề theo dõi", value=True)
unread = g2.checkbox("Chỉ tin chưa đọc", value=False)

rows = all_rows
if pick or pick_tp:
    rows = [r for r in rows if (pick and set(r["tickers"].split(",")) & set(pick))
            or (pick_tp and set((r["topics"] or "").split(",")) & set(pick_tp))]
elif only_match:
    rows = [r for r in rows if r["tickers"] or r["topics"]]
if unread:
    rows = [r for r in rows if not r["seen"]]

if not rows:
    st.info("Chưa có tin phù hợp. Bấm **Cập nhật tin**. Nếu vẫn trống, kiểm tra nguồn tin trong **Cài đặt**.")
else:
    df = pd.DataFrame([{
        "STT": i, "Cần báo KH": bool(r["flagged"]), "Đã đọc": bool(r["seen"]), "Mã": r["tickers"], "Chủ đề": r["topics"],
        "Tiêu đề": r["title"], "Nguồn": r["source"], "Giờ đăng": r["published"], "Link": r["link"],
    } for i, r in enumerate(rows, 1)])
    ed = st.data_editor(df, hide_index=True, width="stretch",
                        disabled=["STT", "Mã", "Chủ đề", "Tiêu đề", "Nguồn", "Giờ đăng", "Link"],
                        column_config={"STT": st.column_config.NumberColumn(width="small"),
                                       "Link": st.column_config.LinkColumn("Link", display_text="Mở"),
                                       "Tiêu đề": st.column_config.TextColumn(width="large")},
                        key="news_ed")
    if st.button("Lưu đánh dấu"):
        with db.conn() as c:
            for _, r in ed.iterrows():
                c.execute("UPDATE news SET flagged=?, seen=? WHERE link=?",
                          (int(r["Cần báo KH"]), int(r["Đã đọc"]), r["Link"]))
        st.success("Đã lưu.")
        st.rerun()

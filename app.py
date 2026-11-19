import hmac
import os

import streamlit as st

from core import db, ui

st.set_page_config(page_title="Operation Management System", page_icon=":material/monitoring:", layout="wide")
ui.inject_css()

# Chia sẻ cho người khác test: đặt biến môi trường OMS_PASSWORD thì phải nhập mật khẩu mới vào được.
_pw = os.environ.get("OMS_PASSWORD")
if not _pw:  # chạy trên Streamlit Cloud: mật khẩu lưu trong Secrets
    try:
        _pw = st.secrets.get("OMS_PASSWORD")
    except Exception:  # noqa: BLE001
        _pw = None
if _pw and not st.session_state.get("authed"):
    st.title("Operation Management System")
    _in = st.text_input("Mật khẩu", type="password")
    if _in and hmac.compare_digest(_in.encode(), _pw.encode()):
        st.session_state["authed"] = True
        st.rerun()
    elif _in:
        st.error("Sai mật khẩu.")
    st.stop()

db.init()

pages = [
    st.Page("views/today.py", title="Trang chủ", icon=":material/home:", default=True),
    st.Page("views/daily.py", title="Báo cáo hằng ngày", icon=":material/summarize:"),
    st.Page("views/margin.py", title="KH & Margin", icon=":material/account_balance:"),
    st.Page("views/orders.py", title="Sổ lệnh", icon=":material/receipt_long:"),
    st.Page("views/procedures.py", title="Archive", icon=":material/inventory_2:"),
    st.Page("views/news.py", title="Tin tức", icon=":material/newspaper:"),
    st.Page("views/settings.py", title="Cài đặt", icon=":material/settings:"),
]
st.navigation(pages).run()

"""Ô nhập số nguyên tự hiện dấu phẩy ngăn cách nghìn (16200 -> 16,200) khi nhập xong (Enter hoặc bấm ra ngoài)."""
from __future__ import annotations

import streamlit as st


def _parse(txt, default):
    t = str(txt).strip().replace(",", "").replace(" ", "")
    if t in ("", "-"):
        return default if t == "" else 0
    try:
        return int(round(float(t)))
    except ValueError:
        return None


def _fmt(n) -> str:
    return f"{int(n):,}"


def _on_change(key: str, last_key: str, min_value):
    v = _parse(st.session_state.get(key, ""), None)
    if v is None:                       # gõ sai: quay về số hợp lệ trước đó
        v = st.session_state.get(last_key, 0)
    if min_value is not None and v < min_value:
        v = min_value
    st.session_state[last_key] = v
    st.session_state[key] = _fmt(v)


def money_input(label: str, value: int = 0, *, key: str, container=None, min_value=None, help=None, in_form=False) -> int:
    """Trả về số nguyên. key bắt buộc. container: st hoặc một cột (mặc định st)."""
    box = container if container is not None else st
    last = key + "__n"
    cur = st.session_state.get(key)
    if cur is None:
        st.session_state[last] = int(value)
        st.session_state[key] = _fmt(value)
    elif not isinstance(cur, str):      # nơi khác gán số vào key -> đổi sang chuỗi có dấu phẩy
        st.session_state[last] = int(round(float(cur)))
        st.session_state[key] = _fmt(st.session_state[last])
    if in_form:   # trong st.form không cho callback: số vẫn đọc đúng, dấu phẩy hiện sau khi lưu
        txt = box.text_input(label, key=key, help=help)
    else:
        txt = box.text_input(label, key=key, help=help, on_change=_on_change, args=(key, last, min_value))
    v = _parse(txt, 0)
    if v is None:
        v = st.session_state.get(last, 0)
    if min_value is not None and v < min_value:
        v = min_value
    st.session_state[last] = v
    return v

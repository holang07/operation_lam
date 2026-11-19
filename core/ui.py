"""Giao diện chung (theo template HR Portal): CSS + vài hàm dựng thẻ HTML.

Gọi `inject_css()` một lần trong app.py. Các trang dùng `page_header`, `stat_card`,
`notice`, `panel_title` nếu muốn có bố cục giống template.
"""
from __future__ import annotations

import html
from datetime import datetime

import streamlit as st

NAVY = "#0F1B33"
NAVY_2 = "#16264A"
BLUE = "#2F6BFF"
GREEN = "#16A34A"
ORANGE = "#F59E0B"
RED = "#EF4444"
INK = "#1B2430"
MUTED = "#6B7785"
LINE = "#E3E8EF"
BG = "#F4F7FB"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
.stApp, .stApp *:not([data-testid="stIconMaterial"]):not(.material-icons):not([class*="material"]) {{
  font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
}}
/* ---------- nền & chữ ---------- */
.stApp {{ background: {BG}; }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 100% !important; padding-left: 2.2rem; padding-right: 2.2rem; }}
[data-testid="stMainBlockContainer"] {{ max-width: 100% !important; }}
h1, h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}
h1 {{ font-size: 1.7rem !important; font-weight: 700 !important; }}
h2, h3 {{ font-weight: 650 !important; }}
header[data-testid="stHeader"] {{ background: transparent; }}

/* ---------- sidebar navy ---------- */
section[data-testid="stSidebar"] {{ background: {NAVY}; border-right: none; }}
section[data-testid="stSidebar"] * {{ color: #C9D3E6; }}
[data-testid="stSidebarNav"]::before {{
  content: "Operation Management System"; display: block; color: #fff;
  font-weight: 700; font-size: .95rem; padding: 1.1rem 1.2rem .9rem;
  border-bottom: 1px solid rgba(255,255,255,.08); margin-bottom: .6rem;
}}
[data-testid="stSidebarNav"] {{ padding-top: 0; }}
[data-testid="stSidebarNavLink"] {{
  border-radius: 8px; margin: 2px 10px; padding: .5rem .7rem; font-size: .92rem;
}}
[data-testid="stSidebarNavLink"]:hover {{ background: rgba(255,255,255,.07); }}
[data-testid="stSidebarNavLink"][aria-current="page"] {{
  background: {BLUE}; box-shadow: 0 2px 8px rgba(47,107,255,.35);
}}
[data-testid="stSidebarNavLink"][aria-current="page"] * {{ color: #fff !important; font-weight: 600; }}

/* ---------- thẻ số liệu (st.metric) ---------- */
[data-testid="stMetric"] {{
  background: #fff; border: 1px solid {LINE}; border-left: 4px solid {BLUE};
  border-radius: 12px; padding: .9rem 1.1rem; box-shadow: 0 1px 2px rgba(16,24,40,.04);
}}
[data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"] {{ border-left-color: {GREEN}; }}
[data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"] {{ border-left-color: {ORANGE}; }}
[data-testid="stColumn"]:nth-child(4) [data-testid="stMetric"] {{ border-left-color: {RED}; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; font-weight: 600; }}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * {{
  overflow: visible !important; text-overflow: clip !important; white-space: normal !important; word-break: break-word;
}}
[data-testid="stMetricValue"] {{ font-weight: 700; color: {INK}; font-size: clamp(.95rem, 1.2vw, 1.35rem); line-height: 1.3; white-space: nowrap !important; }}
[data-testid="stMetricValue"] * {{ white-space: nowrap !important; }}
.st-key-bp_box [data-testid="stMetric"] {{ background: #ECFDF3 !important; border: 1px solid #86EFAC; border-left: 4px solid {GREEN} !important;
  box-shadow: 0 0 0 3px rgba(22,163,74,.12); }}
.st-key-bp_box [data-testid="stMetricLabel"] p {{ color: #15803D; }}

/* ---------- khung có viền (st.container(border=True)), expander, form ---------- */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{ border-radius: 12px; }}
div[data-testid="stExpander"] {{ background: #fff; border: 1px solid {LINE}; border-radius: 12px; }}
div[data-testid="stForm"] {{ background: #fff; border: 1px solid {LINE}; border-radius: 12px; }}
[data-testid="stDataFrame"] {{ border: 1px solid {LINE}; border-radius: 12px; overflow: hidden; background: #fff; }}

h4, h4 * {{ font-size: 1rem !important; font-weight: 700 !important; }}
h4 {{ margin: 0 0 .5rem !important; padding: 0 !important; }}
div[data-testid="stForm"].st-key-tk_quick, .st-key-tk_quick div[data-testid="stForm"] {{ border: none !important; background: transparent !important; padding: 0 !important; }}

/* ---------- tab ---------- */
button[data-baseweb="tab"] {{ font-weight: 600; color: {MUTED}; }}
button[data-baseweb="tab"][aria-selected="true"] {{ color: {BLUE}; }}
div[data-baseweb="tab-highlight"] {{ background: {BLUE}; height: 3px; border-radius: 3px; }}

/* ---------- nút ---------- */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{
  border-radius: 10px; font-weight: 600; border: 1px solid {LINE}; background: #fff; color: {INK};
}}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color: {BLUE}; color: {BLUE}; }}
.stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] > button[kind="primary"],
.stDownloadButton > button[kind="primary"] {{
  background: {BLUE}; border-color: {BLUE}; color: #fff;
}}
.stButton > button[kind="primary"]:hover {{ background: #1F56E0; color: #fff; }}

/* ---------- ô nhập ---------- */
div[data-baseweb="input"], div[data-baseweb="select"] > div, div[data-baseweb="textarea"] {{
  border-radius: 10px !important; background: #fff !important; border-color: {LINE} !important;
}}

/* ---------- khối tùy biến: tiêu đề trang, thẻ, thông báo ---------- */
.pg-head {{ display:flex; justify-content:space-between; align-items:flex-start; gap:1rem; margin-bottom:1.1rem; }}
.pg-head h1 {{ margin:0; padding:0; }}
.pg-head .sub {{ color:{MUTED}; font-size:.9rem; margin-top:.15rem; }}
.pg-date {{ background:#fff; border:1px solid {LINE}; border-radius:10px; padding:.45rem .8rem;
  font-size:.82rem; font-weight:600; color:{INK}; white-space:nowrap; }}

.kpi {{ background:#fff; border:1px solid {LINE}; border-left:4px solid var(--c); border-radius:12px;
  padding:1rem 1.1rem; display:flex; align-items:center; gap:.95rem; box-shadow:0 1px 2px rgba(16,24,40,.04); height:100%; }}
.kpi .ring {{ --p:0; width:58px; height:58px; border-radius:50%; flex:none; display:grid; place-items:center;
  background: conic-gradient(var(--c) calc(var(--p)*1%), #E8EDF5 0); }}
.kpi .ring::before {{ content:""; width:44px; height:44px; border-radius:50%; background:#fff; grid-area:1/1; }}
.kpi .ring span {{ grid-area:1/1; font-size:.72rem; font-weight:700; color:var(--c); z-index:1; }}
.kpi .lbl {{ white-space:nowrap; color:{MUTED}; font-size:.72rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase; }}
.kpi .num {{ color:{INK}; font-size:1.7rem; font-weight:800; line-height:1.15; }}
.kpi .hint {{ color:{MUTED}; font-size:.78rem; }}

.panel {{ background:#fff; border:1px solid {LINE}; border-radius:14px; padding:1rem 1.1rem; margin-bottom:1rem;
  box-shadow:0 1px 2px rgba(16,24,40,.04); }}
.panel h4 {{ margin:0 0 .7rem; font-size:1rem; font-weight:700; color:{INK}; }}
.panel .empty {{ color:{MUTED}; font-size:.88rem; padding:.3rem 0; }}

.ntc {{ display:flex; gap:.8rem; align-items:flex-start; border:1px solid {LINE}; border-radius:12px;
  padding:.75rem .9rem; margin-bottom:.6rem; background:#fff; }}
.ntc .ic {{ width:34px; height:34px; border-radius:50%; flex:none; display:grid; place-items:center; font-size:1rem;
  background:var(--bg); color:var(--c); }}
.ntc .bd {{ flex:1; min-width:0; }}
.ntc .t {{ font-weight:650; color:{INK}; font-size:.92rem; }}
.ntc .d {{ color:{MUTED}; font-size:.82rem; margin-top:.1rem; }}
.ntc .tag {{ display:inline-block; margin-top:.35rem; padding:.1rem .5rem; border-radius:6px; font-size:.68rem;
  font-weight:700; letter-spacing:.03em; background:var(--bg); color:var(--c); }}
.ntc .when {{ color:{MUTED}; font-size:.72rem; white-space:nowrap; }}
.ntc a {{ color:{INK}; text-decoration:none; }}
.ntc a:hover {{ color:{BLUE}; }}

/* thao tác nhanh: st.page_link thành hàng bấm được */
[data-testid="stPageLink"], [data-testid="stPageLink"] > div, [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) {{ width:100% !important; }}
[data-testid="stPageLink-NavLink"] {{ width:100% !important; box-sizing:border-box; }}
[data-testid="stPageLink"] a {{ width:100%; box-sizing:border-box; background:#fff; border:1px solid {LINE}; border-radius:12px; padding:.7rem .9rem;
  margin-bottom:.45rem; font-weight:600; color:{INK}; }}
[data-testid="stPageLink"] a:hover {{ border-color:{BLUE}; background:#F2F6FF; }}

.st-key-sec_buy {{ background:#F0FDF4; border:1px solid #BBF7D0; border-left:4px solid #86EFAC; border-radius:12px; padding:.9rem 1rem .4rem; margin:.4rem 0 .8rem; }}
.st-key-sec_sell {{ background:#FEF2F2; border:1px solid #FECACA; border-left:4px solid #FCA5A5; border-radius:12px; padding:.9rem 1rem .4rem; margin:.4rem 0 .8rem; }}
.st-key-sec_buy h5 {{ color:#15803D; margin:0 0 .5rem; }} .st-key-sec_sell h5 {{ color:#B91C1C; margin:0 0 .5rem; }}
</style>
"""

TONES = {
    "blue": (BLUE, "#E8EFFF"),
    "green": (GREEN, "#DCFCE7"),
    "orange": (ORANGE, "#FEF3C7"),
    "red": (RED, "#FEE2E2"),
    "gray": ("#64748B", "#EEF1F6"),
}


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def greeting(now: datetime | None = None) -> str:
    h = (now or datetime.now()).hour
    return "Chào buổi sáng" if h < 11 else "Chào buổi trưa" if h < 14 else "Chào buổi chiều" if h < 18 else "Chào buổi tối"


def page_header(title: str, sub: str = "", date_text: str = "") -> None:
    pill = f'<div class="pg-date">📅 {esc(date_text)}</div>' if date_text else ""
    subh = f'<div class="sub">{esc(sub)}</div>' if sub else ""
    st.markdown(f'<div class="pg-head"><div><h1>{esc(title)}</h1>{subh}</div>{pill}</div>',
                unsafe_allow_html=True)


def stat_card(label: str, value, hint: str = "", tone: str = "blue", percent: float | None = None) -> str:
    """Trả về HTML một thẻ số liệu; percent (0-100) vẽ vòng tròn tiến độ."""
    c, _ = TONES[tone]
    p = 0 if percent is None else max(0, min(100, percent))
    ring = f'<div class="ring" style="--p:{p:.0f}"><span>{p:.0f}%</span></div>' if percent is not None else ""
    return (f'<div class="kpi" style="--c:{c}">{ring}<div><div class="lbl">{esc(label)}</div>'
            f'<div class="num">{esc(value)}</div><div class="hint">{esc(hint)}</div></div></div>')


def notice(title: str, desc: str = "", tag: str = "", tone: str = "blue", icon: str = "●",
           when: str = "", link: str = "") -> str:
    c, bg = TONES[tone]
    t = f'<a href="{esc(link)}" target="_blank">{esc(title)}</a>' if link else esc(title)
    tg = f'<div class="tag">{esc(tag)}</div>' if tag else ""
    wh = f'<div class="when">{esc(when)}</div>' if when else ""
    return (f'<div class="ntc" style="--c:{c};--bg:{bg}"><div class="ic">{icon}</div>'
            f'<div class="bd"><div class="t">{t}</div><div class="d">{esc(desc)}</div>{tg}</div>{wh}</div>')


def panel(title: str, body_html: str, empty: str = "") -> None:
    inner = body_html or f'<div class="empty">{esc(empty)}</div>'
    st.markdown(f'<div class="panel"><h4>{esc(title)}</h4>{inner}</div>', unsafe_allow_html=True)

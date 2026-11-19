import hashlib
import io

import pandas as pd
import streamlit as st

from core import db, service, snapshot_ocr, ui
from core.numfmt import money_input
from core.service import fmt_vnd

ui.page_header("Đọc ảnh OPT", "Dán ảnh danh mục bất kỳ để đọc số dư tiền, dư nợ, NAV và SLCP. Không cần file Excel.")

if not snapshot_ocr.available():
    st.error("Máy chưa cài thư viện đọc ảnh. Trong terminal gõ: python -m pip install rapidocr-onnxruntime streamlit-paste-button "
             "rồi chạy lại website.")
    st.stop()

ss = st.session_state
ss.setdefault("ocr_items", {})        # hash -> dict(img, res)
known = set(service.prices()) | set(db.get_loan_list())
by_acct = {db.acct_key(c["account_no"], c["name"]): c for c in service.load_customers() if c["account_no"]}

try:
    from streamlit_paste_button import paste_image_button as _pib
    can_paste = True
except Exception:
    can_paste = False


def _png(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _add(b: bytes):
    h = hashlib.md5(b).hexdigest()
    if h in ss["ocr_items"]:
        return
    try:
        res = snapshot_ocr.read_snapshot(b, known)
    except Exception as e:  # noqa: BLE001
        st.error(f"Không đọc được ảnh: {e}")
        return
    ss["ocr_items"][h] = dict(img=b, res=res)


a, b_ = st.columns([1, 3])
if can_paste:
    with a:
        try:
            pr = _pib("📋 Dán ảnh từ clipboard", key="ocr_paste")
            if pr.image_data is not None:
                _add(_png(pr.image_data))
        except Exception:
            st.caption("⚠️ Clipboard chưa có ảnh. Chụp màn hình (Win + Shift + S) rồi bấm Dán ảnh lại.")
with b_:
    ups = st.file_uploader("Hoặc kéo thả / chọn nhiều ảnh", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="ocr_up")
    for f in ups or []:
        _add(f.getvalue())

items = ss["ocr_items"]
if not items:
    st.info("Chưa có ảnh. Chụp phần **Quản lý danh mục** trong OPT (thấy bảng mã và khung Tổng tài sản, Tổng số dư tiền) rồi dán vào đây.")
    st.stop()

day = st.date_input("Ngày của số liệu", value=pd.Timestamp(db.today()).date(), key="ocr_day").strftime("%Y-%m-%d")
if st.button("Xóa hết ảnh", key="ocr_clear"):
    ss["ocr_items"] = {}
    st.rerun()

summary, to_save = [], []
for h, it in list(items.items()):
    r = it["res"]
    acc = r.get("account") or ""
    key = acc[-6:] if acc else ""
    cu = by_acct.get(key)
    title = service.acct_label(cu["name"], cu["account_no"]) if cu else (acc or "Chưa nhận ra tài khoản")
    with st.expander(f"🖼️ {title}", expanded=True):
        c1, c2 = st.columns([1, 1])
        c1.image(it["img"], width="stretch")
        with c2:
            if not acc:
                st.warning("Không đọc được số tài khoản trong ảnh. Nhập tay bên dưới để lưu vào Dashboard.")
            acc_in = st.text_input("Số tài khoản", value=acc, key=f"ocr_acc_{h}")
            if r.get("nav_inferred"):
                st.info("Không đọc được ô Tổng tài sản; NAV được suy ra = số dư tiền + giá trị danh mục. Hãy đối chiếu với ảnh.")
            elif r.get("nav") is None:
                st.warning("Không đọc được NAV. Nhập tay từ ảnh.")
            if r.get("cash") is None:
                st.warning("Không đọc được số dư tiền. Nhập tay từ ảnh.")
            cash = money_input("Số dư tiền (âm = dư nợ)", int(r.get("cash") or 0), key=f"ocr_cash_{h}")
            nav = money_input("NAV (Tổng tài sản)", int(r.get("nav") or 0), key=f"ocr_nav_{h}")
        hold = pd.DataFrame([{"Mã": t, "SLCP": float(q), "Giá TT": float((r.get("prices") or {}).get(t, 0))}
                             for t, q in (r.get("holdings") or {}).items()], columns=["Mã", "SLCP", "Giá TT"])
        if r.get("pending"):
            st.caption("SLCP = GD + Chờ về. Mã có hàng chờ về: " + ", ".join(f"{t} (+{fmt_vnd(q)})" for t, q in r["pending"].items()))
        hd = st.data_editor(hold, num_rows="dynamic", hide_index=True, width="stretch", key=f"ocr_hold_{h}",
                            column_config={"SLCP": st.column_config.NumberColumn(format="%d", min_value=0, step=100),
                                           "Giá TT": st.column_config.NumberColumn(format="%d", min_value=0, step=50)})
        gttt = float(sum((x["SLCP"] or 0) * (x["Giá TT"] or 0) for _, x in hd.iterrows()))
        debt = max(0.0, -cash)
        m1, m2, m3 = st.columns(3)
        m1.metric("Dư nợ", fmt_vnd(debt))
        m2.metric("NAV", fmt_vnd(nav))
        m3.metric("Giá trị danh mục (SLCP × giá)", fmt_vnd(gttt))
        if nav and gttt and abs(cash + gttt - nav) > max(1000.0, abs(nav) * 0.0005):
            st.warning(f"Số dư tiền + giá trị danh mục = {fmt_vnd(cash + gttt)}, lệch NAV {fmt_vnd(cash + gttt - nav)}. "
                       "Kiểm tra lại số đã đọc (hoặc thiếu mã trong bảng).")
        rec = dict(acct=(acc_in[-6:] if acc_in else ""), name=(cu["name"] if cu else ""), nav=nav, cash=cash, gttt=gttt)
        summary.append({"Tài khoản": title, "Dư nợ": fmt_vnd(debt), "NAV": fmt_vnd(nav), "Giá trị danh mục": fmt_vnd(gttt)})
        if rec["acct"] and nav:
            to_save.append(rec)
        if st.button("Xóa ảnh này", key=f"ocr_del_{h}"):
            del ss["ocr_items"][h]
            st.rerun()

st.subheader("Tổng hợp")
st.dataframe(pd.DataFrame(summary), hide_index=True, width="stretch")
if st.button("💾 Lưu NAV vào Dashboard", type="primary", disabled=not to_save):
    for rec in to_save:
        db.save_nav(day, rec["acct"], rec["name"], rec["nav"], rec["cash"], rec["gttt"], "ocr")
    st.success(f"Đã lưu NAV ngày {day} của {len(to_save)} tài khoản.")
st.caption("Trang này chỉ đọc ảnh và lưu NAV cho Dashboard, không sửa số dư tiền hay SLCP trong danh sách khách hàng. "
           "Muốn cập nhật cả file Excel, dùng trang Báo cáo hằng ngày.")

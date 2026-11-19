import io
import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import hashlib

from core import db, service, ttmail, ttocr, snapshot_ocr, ctck
from core.numfmt import money_input


def _kh_options() -> dict:
    """{nhãn hiển thị: (số TK đầy đủ, tên đầy đủ viết hoa)} từ danh bạ + khách hàng trong app."""
    out = {}
    for v in db.directory().values():
        out[service.acct_label(v["short_name"], v["acct"])] = (v["account_no"], (v["full_name"] or "").upper())
    for c in service.load_customers():
        if c["account_no"]:
            lb = service.acct_label(c["name"], c["account_no"])
            if not any(k.startswith(c["account_no"][-6:]) for k in out):
                out[lb] = ("011C" + c["account_no"][-6:] if len(c["account_no"]) <= 6 else c["account_no"], c["name"].upper())
    return dict(sorted(out.items()))


def _copy_box(subject: str, html: str, height: int) -> None:
    sj = json.dumps(subject)
    components.html(f"""
<div style="font-family:Inter,Arial,sans-serif;margin-bottom:8px">
  <button id="b1" style="padding:7px 12px;margin-right:8px;border:1px solid #2F6BFF;background:#2F6BFF;color:#fff;border-radius:8px;cursor:pointer">Sao chép tiêu đề</button>
  <button id="b2" style="padding:7px 12px;border:1px solid #2F6BFF;background:#fff;color:#2F6BFF;border-radius:8px;cursor:pointer">Sao chép nội dung email</button>
  <span id="msg" style="margin-left:10px;color:#15803D;font-size:13px"></span>
</div>
<div style="border:1px solid #D7DEEA;border-radius:10px;padding:10px 14px 4px;background:#fff">
  <div style="font-family:Inter,Arial,sans-serif;font-size:19px;margin-bottom:10px">{subject}</div>
  <div id="mail">{html}</div>
</div>
<script>
const subj = {sj};
const msg = document.getElementById('msg');
function ok(t){{ msg.textContent = t; setTimeout(()=>msg.textContent='', 2500); }}
document.getElementById('b1').onclick = async () => {{
  try {{ await navigator.clipboard.writeText(subj); ok('Đã sao chép tiêu đề'); }}
  catch(e) {{ const t=document.createElement('textarea'); t.value=subj; document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove(); ok('Đã sao chép tiêu đề'); }}
}};
document.getElementById('b2').onclick = () => {{
  const el = document.getElementById('mail'); const r = document.createRange(); r.selectNodeContents(el);
  const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
  let done = false; try {{ done = document.execCommand('copy'); }} catch(e) {{}}
  s.removeAllRanges(); ok(done ? 'Đã sao chép nội dung, dán vào Gmail' : 'Không sao chép được, hãy bôi đen nội dung rồi Ctrl+C');
}};
</script>""", height=height, scrolling=True)


def _on_pick() -> None:
    ss = st.session_state
    nm = ss.get("tt_cpick")
    if nm and nm != ctck.OTHER:
        ids = ctck.ids_for(nm)
        ss["tt_cpid"] = ids[0] if ids else ""
        ss["tt_cpa"] = ids[0] if ids else ""
        ss["tt_cpn"] = nm


def _on_id() -> None:
    st.session_state["tt_cpa"] = st.session_state.get("tt_cpid", "")


def _fill(info: dict) -> None:
    """Callback: điền form từ kết quả đọc ảnh (chạy trước khi vẽ lại trang)."""
    ss = st.session_state
    ss["tt_kind"] = "Thỏa thuận BÁN (KH là bên bán)" if info["side"] == "Bán" else "Thỏa thuận MUA (KH là bên mua)"
    if info.get("kh_label"):
        ss["tt_kh"] = info["kh_label"]
    if info.get("tv"):
        ss["tt_cpa"] = ctck.norm_id(info["tv"])
        nm = ctck.find_by_id(info["tv"])
        if nm:
            ss["tt_cpick"], ss["tt_cpid"], ss["tt_cpn"] = nm, ctck.norm_id(info["tv"]), nm
        else:
            ss["tt_cpick"] = ctck.OTHER
            if info.get("firm"):
                ss["tt_cpn"] = "CTCK " + info["firm"]
    ss["tt_fill"] = info["orders"]
    if info.get("ticker"):
        ss["tt_tk"] = info["ticker"]
    if info.get("price"):
        ss["tt_px"] = f"{int(info['price']):,}"
        ss["tt_px__n"] = int(info["price"])
    ss["tt_ver"] = ss.get("tt_ver", 0) + 1


def _scan_box() -> None:
    with st.expander("📷 Điền nhanh từ ảnh (dán ảnh dòng thỏa thuận)", expanded=False):
        if not snapshot_ocr.available():
            st.error("Máy chưa cài thư viện đọc ảnh. Trong terminal gõ: python -m pip install rapidocr-onnxruntime streamlit-paste-button")
            return
        st.caption("Chụp dòng thỏa thuận (cột CTCK, TK giao dịch, Số lượng, Giá, Bên đối ứng, Mã TV, Lệnh) rồi dán vào đây. "
                   "App đọc ảnh và đề xuất điền form, bạn kiểm tra lại trước khi dùng. Ảnh không có mã CK thì bạn nhập mã sau.")
        data = None
        try:
            from streamlit_paste_button import paste_image_button as _pib
            pr = _pib("📋 Dán ảnh từ clipboard", key="tt_paste")
            if pr.image_data is not None:
                buf = io.BytesIO()
                pr.image_data.save(buf, format="PNG")
                data = buf.getvalue()
        except Exception:  # noqa: BLE001
            st.caption("Chưa dán được ảnh từ clipboard, dùng ô tải ảnh bên dưới.")
        up = st.file_uploader("Hoặc chọn file ảnh", type=["png", "jpg", "jpeg"], key="tt_scan_up")
        if up is not None:
            data = up.getvalue()
        if data is not None:
            h = hashlib.md5(data).hexdigest()
            if st.session_state.get("tt_scan_hash") != h:
                with st.spinner("Đang đọc ảnh..."):
                    try:
                        st.session_state["tt_scan_rows"] = ttocr.read(data)
                    except Exception as e:  # noqa: BLE001
                        st.session_state["tt_scan_rows"] = []
                        st.error(f"Không đọc được ảnh: {e}")
                st.session_state["tt_scan_hash"] = h
        rows = st.session_state.get("tt_scan_rows")
        if rows is None:
            return
        if not rows:
            st.warning("Không nhận ra dòng thỏa thuận nào trong ảnh. Thử chụp rõ hơn (đủ cột TK giao dịch và Mã TV).")
            return
        opts = _kh_options()
        first = rows[0]
        label = next((lb for lb, (a, _n) in opts.items() if first["acct6"] and a.endswith(first["acct6"])), "")
        same = [r for r in rows if r["side"] == first["side"]]

        def _kh_of(r):
            lb = next((l_ for l_, (a_, _n) in opts.items() if r["acct6"] and a_.endswith(r["acct6"])), "")
            return lb, opts.get(lb, (f"011C{r['acct6']}" if r["acct6"] else "", ""))

        orders = [dict(kh_label=_kh_of(r)[0], kh_acct=_kh_of(r)[1][0], kh_name=_kh_of(r)[1][1],
                       qty=r["qty"] or 0, price=r["price"] or 0, ticker=r.get("ticker", ""),
                       cp_name=ctck.find_by_id(r["tv"]) or ("CTCK " + r["firm"] if r["firm"] else ""),
                       cp_id=ctck.norm_id(r["tv"])) for r in same]
        st.dataframe(pd.DataFrame([{
            "TK KH": f"011C{r['acct6']}" if r["acct6"] else "?", "Mã CK": r.get("ticker") or "?", "Lệnh (HSC)": r["side"], "Số lượng": r["qty"], "Giá": r["price"],
            "Giá trị": r["value"], "Bên đối ứng": r["firm"], "Mã TV": r["tv"]} for r in rows]),
            hide_index=True, width="stretch")
        bad = [i + 1 for i, r in enumerate(rows) if not r.get("ok")]
        if bad:
            st.warning("Dòng " + ", ".join(map(str, bad)) + ": Số lượng × Giá không khớp Giá trị, app có thể đọc sai số. "
                       "Hãy đối chiếu với ảnh và sửa trong bảng Các lệnh bên dưới.")
        if not label:
            st.warning(f"Chưa thấy tài khoản 011C{first['acct6']} trong danh bạ/KH của app, bạn chọn KH thủ công bên dưới.")
        if len(same) < len(rows):
            st.caption(f"Ảnh có {len(rows)} dòng, chỉ điền {len(same)} dòng cùng chiều lệnh với dòng đầu (mua/bán không trộn chung một email).")
        st.button("Điền vào form bên dưới", type="primary", key="tt_fillbtn", on_click=_fill,
                  args=(dict(side=first["side"], kh_label=label, tv=first["tv"], firm=first["firm"], orders=orders,
                        ticker=first.get("ticker", ""), price=first.get("price")),))


def render() -> None:
    st.caption("Nhập thông số như file Excel thỏa thuận, app tạo tiêu đề và nội dung email giống mẫu để dán vào Gmail. App chỉ soạn, không tự gửi.")
    _scan_box()
    kind = st.radio("Loại thỏa thuận", ["Thỏa thuận MUA (KH là bên mua)", "Thỏa thuận BÁN (KH là bên bán)"], horizontal=True, key="tt_kind")
    mua = kind.startswith("Thỏa thuận MUA")
    k = "MUA" if mua else "BÁN"

    opts = _kh_options()
    c1, c2 = st.columns(2)
    sel = c1.selectbox("Khách hàng của mình", list(opts) or [""], key="tt_kh")
    kh_acct, kh_name = opts.get(sel, ("", ""))
    kh_acct = c1.text_input("Số tài khoản KH", value=kh_acct, key=f"tt_kacct_{sel}")
    kh_name = c1.text_input("Tên KH (viết hoa)", value=kh_name, key=f"tt_kname_{sel}")
    st.session_state.setdefault("tt_cpa", db.get_text("tt_cp_acct", "009 - 0091"))
    st.session_state.setdefault("tt_cpn", db.get_text("tt_cp_name", "CTCK VCBS"))
    cnames = ctck.names()
    st.session_state.setdefault("tt_cpick", st.session_state["tt_cpn"] if st.session_state["tt_cpn"] in cnames else ctck.OTHER)
    c2.selectbox(f"CTCK đối tác (bên {'bán' if mua else 'mua'})", cnames + [ctck.OTHER], key="tt_cpick", on_change=_on_pick)
    pick = st.session_state["tt_cpick"]
    ids_ = ctck.ids_for(pick) if pick != ctck.OTHER else []
    if ids_:
        if st.session_state.get("tt_cpid") not in ids_:
            st.session_state["tt_cpid"] = ids_[0]
        c2.selectbox("Mã ID (một CTCK có thể có nhiều mã, chọn theo nhu cầu KH)", ids_, key="tt_cpid", on_change=_on_id)
    cp_acct = c2.text_input(f"Số tài khoản bên {'bán' if mua else 'mua'} (đối tác)", key="tt_cpa")
    cp_name = c2.text_input(f"Tên KH bên {'bán' if mua else 'mua'} (đối tác)", key="tt_cpn")

    d1, d2, d3 = st.columns(3)
    prefix = d1.text_input("Tiền tố tiêu đề", value=db.get_text("tt_prefix", "[HCM2 NSG1]"), key="tt_prefix")
    init = d2.selectbox("Bên khởi tạo lệnh", ["Bên bán", "Bên mua"], key="tt_init")
    frn = d3.multiselect("NĐT nước ngoài", ["Bên bán", "Bên mua"], key="tt_frn")
    e1, e2 = st.columns(2)
    margin = e1.selectbox("Cần duyệt Margin Dtrade?", ["CÓ", "KHÔNG"], index=0 if mua else 1, key=f"tt_mg_{k}")
    appr = e2.text_input("Người duyệt (anh/chị ...)", value=db.get_text("tt_approver", "Hà"), key="tt_appr",
                         disabled=margin == "KHÔNG")

    f1, f2 = st.columns(2)
    tk = f1.text_input("Mã chứng khoán", value="", key="tt_tk").upper().strip()
    px = money_input("Giá (VND)", 0, key="tt_px", container=f2)
    st.markdown("**Các lệnh** (mỗi dòng một lệnh; Mã CK hoặc Giá để trống thì dùng mã và giá ở trên)")
    fill = st.session_state.get("tt_fill")
    cn_all = ctck.names()
    for o in fill or []:                                    # CTCK ngoài danh sách thì thêm vào để hiển thị được
        if o.get("cp_name") and o["cp_name"] not in cn_all:
            cn_all = cn_all + [o["cp_name"]]
    kh_labels = list(opts)
    ss = st.session_state
    if ss.get("tt_tbl_ver") != ss.get("tt_ver", 0) or "tt_tbl" not in ss:     # ảnh vừa điền: dựng lại bảng
        ss["tt_tbl"] = (pd.DataFrame({"Khách hàng": [o.get("kh_label") or None for o in fill],
                                      "STK KH": [o.get("kh_acct") or None for o in fill],
                                      "Tên KH": [o.get("kh_name") or None for o in fill],
                                      "Mã CK": [o.get("ticker", "") for o in fill], "Khối lượng": [o["qty"] for o in fill],
                                      "Giá": [o["price"] for o in fill], "CTCK đối tác": [o.get("cp_name") or None for o in fill],
                                      "Mã ID": [o.get("cp_id") or None for o in fill]})
                        if fill else pd.DataFrame({"Khách hàng": [None], "STK KH": [None], "Tên KH": [None], "Mã CK": [""],
                                                   "Khối lượng": [0], "Giá": [0], "CTCK đối tác": [None], "Mã ID": [None]}))
        ss["tt_prev"] = ss["tt_tbl"].copy()
        ss["tt_tbl_ver"] = ss.get("tt_ver", 0)
    st.caption("Một email có thể nhiều KH, mỗi lệnh một KH và một CTCK đối tác: chọn ở cột **Khách hàng** (tự điền **STK KH** và **Tên KH**) "
               "và cột **CTCK đối tác** (tự điền **Mã ID**). STK, Tên KH, Mã ID đều sửa tay được. "
               "Để trống thì dùng KH và CTCK đã chọn ở phía trên.")
    ed = st.data_editor(ss["tt_tbl"], num_rows="dynamic", hide_index=True, width="stretch",
                        key=f"tt_ed_{k}_{ss.get('tt_ver', 0)}_{ss.get('tt_tbl_n', 0)}",
                        column_config={"Khách hàng": st.column_config.SelectboxColumn(options=kh_labels),
                                       "STK KH": st.column_config.TextColumn(help="Dạng 011C123456; sửa tay được"),
                                       "Tên KH": st.column_config.TextColumn(help="Viết hoa; sửa tay được"),
                                       "Khối lượng": st.column_config.NumberColumn(format="%d", min_value=0, step=100),
                                       "Giá": st.column_config.NumberColumn(format="%d", min_value=0, step=50),
                                       "CTCK đối tác": st.column_config.SelectboxColumn(options=cn_all),
                                       "Mã ID": st.column_config.TextColumn(help="Dạng 007 - 00071; sửa tay được")})
    # chọn/đổi CTCK ở dòng nào thì Mã ID của dòng đó nhảy theo danh sách
    prev = ss.get("tt_prev")
    ed = ed.reset_index(drop=True)
    changed = False
    for i in range(len(ed)):
        cn_new = ed.at[i, "CTCK đối tác"]
        cn_old = prev.at[i, "CTCK đối tác"] if prev is not None and i < len(prev) else None
        if pd.notna(cn_new) and cn_new != cn_old:
            ids_ = ctck.ids_for(cn_new)
            if ids_ and ed.at[i, "Mã ID"] != ids_[0]:
                ed.at[i, "Mã ID"] = ids_[0]
                changed = True
    for i in range(len(ed)):
        kh_new = ed.at[i, "Khách hàng"]
        kh_old = prev.at[i, "Khách hàng"] if prev is not None and i < len(prev) else None
        if pd.notna(kh_new) and kh_new != kh_old and kh_new in opts:
            a_, n_ = opts[kh_new]
            if ed.at[i, "STK KH"] != a_ or ed.at[i, "Tên KH"] != n_:
                ed.at[i, "STK KH"], ed.at[i, "Tên KH"] = a_, n_
                changed = True
    ss["tt_prev"] = ed.copy()
    if changed:
        ss["tt_tbl"] = ed.copy()
        ss["tt_tbl_n"] = ss.get("tt_tbl_n", 0) + 1
        st.rerun()
    orders = []
    for _, r in ed.iterrows():
        q = float(r["Khối lượng"] or 0)
        if q <= 0:
            continue
        cname = r.get("CTCK đối tác") if pd.notna(r.get("CTCK đối tác")) else ""
        cid = r.get("Mã ID") if pd.notna(r.get("Mã ID")) else ""
        if cname and not cid:
            ids_ = ctck.ids_for(cname)
            cid = ids_[0] if ids_ else ""
        if cid and not cname:
            cname = ctck.find_by_id(cid) or ""
        klb = r.get("Khách hàng") if pd.notna(r.get("Khách hàng")) else ""
        kac = r.get("STK KH") if pd.notna(r.get("STK KH")) else ""
        knm = r.get("Tên KH") if pd.notna(r.get("Tên KH")) else ""
        if klb in opts:
            kac, knm = kac or opts[klb][0], knm or opts[klb][1]
        orders.append(dict(ticker=(str(r["Mã CK"] or "").upper().strip() or tk), qty=q, price=float(r["Giá"] or 0) or float(px),
                           cp_name=cname or cp_name, cp_acct=cid or cp_acct, kh_acct=str(kac).strip(), kh_name=str(knm).strip()))

    if any(not ((o["kh_acct"] or kh_acct) and (o["kh_name"] or kh_name)) for o in orders) or (not orders and not (kh_acct and kh_name)):
        st.info("Chọn khách hàng hoặc nhập số tài khoản và tên KH.")
        return
    if not orders or any(not o["ticker"] or not o["price"] for o in orders):
        st.info("Nhập mã chứng khoán, giá và khối lượng của ít nhất một lệnh.")
        return

    db.set_text("tt_prefix", prefix)
    db.set_text("tt_cp_acct", cp_acct)
    db.set_text("tt_cp_name", cp_name)
    if appr:
        db.set_text("tt_approver", appr)
    out = ttmail.build(k, prefix=prefix, kh_acct=kh_acct, kh_name=kh_name, cp_acct=cp_acct, cp_name=cp_name, orders=orders,
                       initiator=init, foreign=tuple(frn), need_margin=(margin == "CÓ"), approver=appr or "Hà")
    st.markdown("##### Email")
    _copy_box(out["subject"], out["html"], 330 + len(orders) * 285 + (150 if margin == "CÓ" else 0))
    buf = io.BytesIO()
    pd.DataFrame(out["rows"]).to_excel(buf, index=False)
    x1, x2 = st.columns(2)
    x1.download_button("Tải bảng Excel các lệnh", buf.getvalue(), file_name=f"thoa_thuan_{k.lower()}_{kh_acct}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    x2.download_button("Tải email (.html)", ("<meta charset='utf-8'><h3>" + out["subject"] + "</h3>" + out["html"]).encode("utf-8"),
                       file_name=f"thoa_thuan_{k.lower()}_{kh_acct}.html", mime="text/html")

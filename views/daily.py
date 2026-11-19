import io
import json

import pandas as pd
import streamlit as st

from core import dailyreport, db, service, snapshot_ocr, xlsxformula, xlsxpatch
from core.numfmt import money_input
from core import ocrpanel, groupstore, sourcepanel
import importlib
import core.importer as _imp
for _m in (_imp, xlsxformula, xlsxpatch):   # luôn dùng mã mới nhất, tránh Streamlit giữ bản cũ trong bộ nhớ
    importlib.reload(_m)
from core.importer import parse_workbook
from core.service import STATUS_ICON, STATUS_LABEL, fmt_pct, fmt_vnd

LM = service.label_map()
acc_lab = lambda n: LM.get(n, n)

today = db.today()

st.title("Báo cáo hằng ngày")
st.caption("Tải file Excel chưa cập nhật → dán ảnh OPT từng tài khoản → cập nhật số dư tiền, SLCP, kiểm tra NAV → xuất lại Excel.")

ORIG = db.DB_PATH.parent / "daily_original.xlsx"
custs = service.load_customers()

tab_flow, tab_in, tab_out, tab_ocr = st.tabs(["1. Cập nhật từ ảnh OPT", "Nhập tay (dự phòng)", "2. Kết quả", "Đọc ảnh OPT (không cần file)"])

with tab_ocr:
    st.caption("Dán ảnh danh mục OPT bất kỳ để đọc số dư tiền, dư nợ, NAV, SLCP và lưu NAV vào Dashboard (Trang chủ). Không cần file Excel.")
    ocrpanel.render()

# ============================================================ 1. CẬP NHẬT TỪ ẢNH
def _flow():
    ss = st.session_state
    ss.setdefault("snap_img", {})      # tên KH -> bytes PNG
    ss.setdefault("snap_applied", set())

    # ---------- Bước 1
    st.subheader("Bước 1 · Tải file Excel chưa cập nhật")
    import io as _io

    def _use_raw(raw: bytes, fname: str, save_copy: bool):
        try:
            cs, pxs, warns = parse_workbook(_io.BytesIO(raw))
        except Exception as e:
            st.error(f"Không đọc được file: {e}")
            return
        ORIG.parent.mkdir(exist_ok=True)
        ORIG.write_bytes(raw)
        db.import_customers(cs, pxs)
        db.drop_customers_not_in([c_["name"] for c_ in cs])
        if grp:
            db.set_group_for([c_["name"] for c_ in cs], grp)
            if save_copy:
                groupstore.save(grp, raw, "goc", fname)
        ss["snap_img"] = {}; ss["snap_applied"] = set(); ss["seen_img"] = set(); ss["unmatched"] = []
        st.success(f"Đã nạp {len(cs)} tài khoản và {len(pxs)} mã từ file."
                   + (f" Đã lưu file vào thư mục nhóm {grp}." if grp and save_copy else ""))
        for w in warns[:5]:
            st.caption("⚠️ " + w)
        st.rerun()

    grp = sourcepanel.group_picker("dly", "Nhóm (file được lưu vào thư mục riêng của nhóm)")
    ss["daily_group"] = grp
    up = st.file_uploader("File Excel (mỗi sheet một KH)", type=["xlsx"], key="orig_up")
    sname = (st.text_input("Tên file lưu (không cần đuôi .xlsx)", value=up.name.rsplit(".", 1)[0], key=f"dly_name_{up.name}")
             if up is not None else "")
    if up is not None and st.button("Dùng file này làm file gốc", type="primary"):
        _use_raw(up.getvalue(), sname or up.name, True)
    saved = groupstore.files(grp) if grp else []
    if saved:
        sf = st.selectbox("Hoặc dùng file đã lưu của nhóm này", saved, format_func=groupstore.label, key=f"dly_saved_{grp}")
        if st.button("Dùng file đã lưu làm file gốc", key="dly_use_saved"):
            _use_raw(groupstore.read(grp, sf["name"]), sf["orig"], False)
    if not ORIG.exists():
        st.info("Chưa có file gốc. Tải file Excel lên rồi bấm **Dùng file này làm file gốc**.")
        return
    orig_bytes = ORIG.read_bytes()
    import io as _io
    orig_cs, orig_px, _ = parse_workbook(_io.BytesIO(orig_bytes))
    sheet_of = {c["name"]: c for c in orig_cs}
    custs = service.load_customers()
    if {c["name"] for c in custs} != set(sheet_of):
        # danh sách trong app lệch với file (tên cũ, sheet đã bỏ...): đồng bộ lại theo file gốc
        db.import_customers(orig_cs, orig_px)
        db.drop_customers_not_in(list(sheet_of))
        custs = service.load_customers()
        LM.update(service.label_map())
    names = [c["name"] for c in custs if c["name"] in sheet_of]
    st.caption(f"File gốc đang dùng: {len(names)} tài khoản · ghi lúc {pd.Timestamp(ORIG.stat().st_mtime, unit='s').strftime('%d/%m %H:%M')}")

    # ---------- Bước 2
    st.subheader("Bước 2 · Chụp danh mục từ OPT")
    st.markdown(
        "- **Cách nhanh:** mở OPT, bấm **Win + Shift + S**, chụp vùng danh mục của một tài khoản "
        "(thấy rõ số dư tiền, NAV, mã và số lượng).\n"
        "- **Nhờ Claude chụp:** trong cuộc trò chuyện Claude (app máy tính), cấp quyền màn hình rồi nhờ Claude "
        "chụp từng tài khoản và lưu ảnh vào thư mục `anh_snapshot`; sau đó bạn kéo ảnh vào ô tải lên ở bước 3. "
        "Website không tự chụp màn hình OPT được.")

    # ---------- Bước 3
    st.subheader("Bước 3 · Dán ảnh theo từng tài khoản")
    try:
        from streamlit_paste_button import paste_image_button as _pib
        can_paste = True

        class _NoImg:
            image_data = None

        def paste_image_button(label, key):
            """Clipboard chưa có ảnh thì thư viện báo lỗi PIL; ở đây chỉ nhắc nhẹ, không làm hỏng trang."""
            try:
                return _pib(label, key=key)
            except Exception:
                st.caption("⚠️ Clipboard chưa có ảnh. Chụp màn hình (Win + Shift + S) rồi bấm Dán ảnh lại, hoặc tải file ảnh lên.")
                return _NoImg()
    except Exception:
        can_paste = False
        st.caption("Chưa cài `streamlit-paste-button` nên chỉ tải ảnh lên được (chạy: python -m pip install -r requirements.txt).")
    st.caption("Chọn tài khoản, bấm **Dán ảnh** (hoặc tải file ảnh). Mỗi tài khoản một ảnh.")

    known = {p.ticker for c in custs for p in c["positions"]} | set(service.prices())
    def put_image(name, b):
        ss["snap_img"][name] = b
        ss.pop("snap_read_" + name, None)

    def _png(img):
        import io as _o
        buf = _o.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()

    # ---- dán nhanh nhiều ảnh: tự nhận tài khoản theo số tài khoản in trong ảnh
    import hashlib
    st.markdown("**Dán nhanh (tự nhận tài khoản từ số tài khoản trong ảnh)**")
    qa, qb = st.columns([1, 3])
    new_imgs = list(ss.pop("_inject", []))
    if can_paste:
        with qa:
            pr_a = paste_image_button("📋 Dán ảnh từ clipboard", key="paste_auto")
            if pr_a.image_data is not None:
                new_imgs.append(_png(pr_a.image_data))
    with qb:
        multi = st.file_uploader("Hoặc kéo thả / chọn nhiều ảnh cùng lúc", type=["png", "jpg", "jpeg"],
                                 accept_multiple_files=True, key="multi_up")
        new_imgs += [f_.getvalue() for f_ in (multi or [])]
    seen = ss.setdefault("seen_img", set())
    ss.setdefault("unmatched", [])
    changed = False
    for b in new_imgs:
        h = hashlib.md5(b).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        changed = True
        d = None
        if snapshot_ocr.available():
            try:
                d = snapshot_ocr.read_snapshot(b, known)
            except Exception as e:
                st.error(f"Không đọc được ảnh vừa dán: {e}")
        acc = (d or {}).get("account") or ""
        target = next((nm for nm in names if sheet_of[nm]["account_no"] and acc.endswith(sheet_of[nm]["account_no"][-6:])), None)
        if target:
            put_image(target, b)
            if d:
                ss["snap_pre_" + target] = d
            ss.setdefault("auto_msg", []).append(f"✅ Ảnh tài khoản {acc} đã gán cho {target}")
        else:
            ss["unmatched"].append((h, b, acc))
    if changed:
        st.rerun()
    for m_ in ss.pop("auto_msg", []):
        st.success(m_)
    for h, b, acc in list(ss["unmatched"]):
        u1, u2 = st.columns([1, 2])
        u1.image(b, width="stretch")
        u2.warning(f"Chưa nhận ra tài khoản trong ảnh{(' (đọc được: ' + acc + ')') if acc else ''}. Chọn tài khoản để gán:")
        pick = u2.selectbox("Gán cho tài khoản", names, key=f"pick_{h}", format_func=acc_lab)
        if u2.button("Gán ảnh này", key=f"assign_{h}"):
            put_image(pick, b)
            ss["unmatched"] = [x for x in ss["unmatched"] if x[0] != h]
            st.rerun()
    st.caption("Hoặc dán / tải từng ảnh vào đúng tài khoản bên dưới.")

    cols = st.columns(2)
    for i, name in enumerate(names):
        with cols[i % 2]:
            c1, c2, c3 = st.columns([2, 2, 1])
            c1.markdown(f"**{acc_lab(name)}**" + (" ✅" if name in ss["snap_img"] else ""))
            if can_paste:
                with c2:
                    pr = paste_image_button("Dán ảnh", key=f"paste_{name}")
                    if pr.image_data is not None:
                        b = _png(pr.image_data)
                        if ss["snap_img"].get(name) != b:
                            put_image(name, b)
                            st.rerun()
            f = st.file_uploader("Hoặc tải ảnh", type=["png", "jpg", "jpeg"], key=f"up_{name}", label_visibility="collapsed")
            if f is not None and ss["snap_img"].get(name) != f.getvalue():
                put_image(name, f.getvalue())
                st.rerun()

    have = [n for n in names if n in ss["snap_img"]]
    st.caption(f"Đã có ảnh: {len(have)}/{len(names)} tài khoản.")

    # ---------- Bước 4
    st.subheader("Bước 4 · Đọc ảnh, đối chiếu và cập nhật (ảnh dán xong tự được đọc)")
    if not snapshot_ocr.available():
        st.warning("Chưa cài thư viện đọc ảnh. Chạy: python -m pip install rapidocr-onnxruntime. "
                   "Trong lúc chờ vẫn có thể gõ tay ở bảng dưới, ảnh hiện cạnh để đối chiếu.")
    with st.expander("Chỉ vị trí đọc dữ liệu trên ảnh (làm một lần, dùng cho mọi ảnh sau)", expanded=False):
        st.caption("Màn hình OPT luôn có bố cục giống nhau, nên chỉ cần khoanh một lần. Kéo các thanh trượt cho khung "
                   "(đỏ = NAV, xanh lá = số dư tiền, xanh dương = bảng mã + SLCP) bao đúng vùng cần đọc, rồi bấm Lưu.")
        if not have:
            st.info("Dán ít nhất một ảnh ở bước 3 để khoanh vùng.")
        elif not snapshot_ocr.available():
            st.warning("Cần cài thư viện đọc ảnh trước.")
        else:
            ref = st.selectbox("Ảnh dùng để khoanh vùng", have, key="roi_ref", format_func=acc_lab)
            roi = snapshot_ocr.load_roi()
            new = {}
            for k, lab in snapshot_ocr.ROI_LABEL.items():
                c1, c2 = st.columns(2)
                x0, x1 = c1.slider(f"{lab} · ngang (%)", 0, 100, (int(roi[k][0] * 100), int(roi[k][2] * 100)), key=f"roi_x_{k}")
                y0, y1 = c2.slider(f"{lab} · dọc (%)", 0, 100, (int(roi[k][1] * 100), int(roi[k][3] * 100)), key=f"roi_y_{k}")
                new[k] = [x0 / 100, y0 / 100, x1 / 100, y1 / 100]
            img_ref = ss["snap_img"][ref]
            st.image(snapshot_ocr.draw_boxes(img_ref, new), width="stretch")
            if st.button("Thử đọc với các vùng này"):
                try:
                    r_ = snapshot_ocr.read_snapshot_roi(img_ref, known, new)
                    st.write({"NAV": r_["nav"], "Số dư tiền": r_["cash"], "SLCP": r_["holdings"],
                              "Chữ đọc được ở ô NAV": r_["raw"]["nav"], "Chữ đọc được ở ô số dư": r_["raw"]["cash"]})
                except Exception as e:
                    st.error(f"Không đọc được: {e}")
            if st.button("Lưu vị trí này", type="primary"):
                snapshot_ocr.save_roi(new)
                st.success("Đã lưu. Các lần đọc sau dùng vùng này.")

    st.checkbox("Đọc theo nhãn chữ (khuyên dùng khi chiều cao ảnh mỗi tài khoản khác nhau)", value=True, key="ocr_by_label",
                help="Tìm chữ 'Tổng tài sản', 'Tổng số dư tiền' và các dòng mã ngay trong ảnh. Bỏ tick để đọc theo khung đã khoanh ở trên.")
    cash_now = {c["name"]: c["cash"] for c in custs}

    def read_one(n: str) -> bool:
        """Đọc ảnh của tài khoản n và điền sẵn vào form. Lỗi thì ghi lại để hiện trong form."""
        ss.pop("snap_err_" + n, None)
        try:
            d = ss.pop("snap_pre_" + n, None) if ss.get("ocr_by_label", True) else None
            if d is None:
                d = (snapshot_ocr.read_snapshot(ss["snap_img"][n], known) if ss.get("ocr_by_label", True)
                     else snapshot_ocr.read_snapshot_roi(ss["snap_img"][n], known, snapshot_ocr.load_roi()))
        except Exception as e:
            ss["snap_err_" + n] = f"{type(e).__name__}: {e}"
            return False
        ss["snap_read_" + n] = d
        ss[f"cash_in_{n}"] = float(d["cash"] if d["cash"] is not None else cash_now.get(n, 0) or 0)
        ss[f"nav_in_{n}"] = float(d["nav"] or 0)
        ss[f"hold_in_{n}"] = pd.DataFrame(
            [{"Mã": t, "SLCP": float(q), "Giá TT": float(d.get("prices", {}).get(t, 0))} for t, q in d["holdings"].items()],
            columns=["Mã", "SLCP", "Giá TT"])
        return True

    if st.button("Đọc lại ảnh (OCR) các tài khoản đã dán", disabled=not have or not snapshot_ocr.available()):
        for n in have:
            read_one(n)
        st.rerun()
    # ảnh mới dán thì tự đọc ngay, không cần bấm nút
    if snapshot_ocr.available():
        todo = [n for n in have if "snap_read_" + n not in ss and "snap_err_" + n not in ss]
        if todo:
            with st.spinner(f"Đang đọc ảnh {', '.join(todo)} ..."):
                for n in todo:
                    read_one(n)
            st.rerun()

    px = service.prices()
    cmap = {c["name"]: c for c in custs}
    for n in have:
        cu = cmap[n]
        ss.setdefault(f"cash_in_{n}", float(cu["cash"] or 0))
        ss.setdefault(f"nav_in_{n}", 0.0)
        ss.setdefault(f"hold_in_{n}", pd.DataFrame([{"Mã": p.ticker, "SLCP": float(p.qty), "Giá TT": float(p.price or 0)} for p in cu["positions"]]))
        with st.expander(acc_lab(n), expanded=n not in ss["snap_applied"]):
            if not snapshot_ocr.available():
                st.error("CHƯA đọc được ảnh: máy chưa cài thư viện đọc ảnh. Trong terminal gõ: python -m pip install rapidocr-onnxruntime streamlit-paste-button "
                         "rồi chạy lại website. Các số bên dưới là số CŨ trong file Excel, chưa phải số trong ảnh.")
            elif ss.get("snap_err_" + n):
                st.error(f"Đọc ảnh bị lỗi: {ss['snap_err_' + n]}. Các số bên dưới là số CŨ trong file Excel.")
            elif ss.get("snap_read_" + n):
                _d = ss["snap_read_" + n]
                miss_ = [k for k, v in (("số dư tiền", _d["cash"]), ("NAV", _d["nav"]), ("mã/SLCP", _d["holdings"])) if not v]
                if _d.get("pending"):
                    st.caption("SLCP = GD + Chờ về. Mã có hàng chờ về: " + ", ".join(
                        f"{t} (+{fmt_vnd(q)})" for t, q in _d["pending"].items()))
                if _d.get("nav_inferred"):
                    st.info("Không đọc được ô **Tổng tài sản** trên ảnh, nên NAV bên dưới được **suy ra** = số dư tiền + giá trị danh mục "
                            "(đọc từ ảnh). Số dư tiền và danh mục đã đọc được. Bạn nhìn ô Tổng tài sản trên ảnh, nếu khác thì sửa ô NAV.")
                if miss_:
                    st.warning("Đã đọc ảnh nhưng KHÔNG thấy: " + ", ".join(miss_) + ". Hãy kiểm tra ảnh có đủ cả bảng mã VÀ khung bên dưới (Tổng tài sản, Tổng số dư tiền) chưa, "
                                   "chụp lại cho đủ và rõ hơn, hoặc nhập tay phần thiếu.")
                else:
                    st.caption("✅ Các số bên dưới được đọc từ ảnh. Hãy đối chiếu với ảnh trước khi xác nhận.")
            l, r = st.columns([1, 1])
            l.image(ss["snap_img"][n], width="stretch")
            with r:
                rd = ss.get("snap_read_" + n)
                if rd and rd.get("account"):
                    acc_no = str(cu["account_no"] or "")
                    if acc_no and not rd["account"].endswith(acc_no[-6:]):
                        st.error(f"Ảnh ghi tài khoản {rd['account']} nhưng KH này là {acc_no}. Có thể dán nhầm ảnh.")
                    else:
                        st.caption(f"Tài khoản trong ảnh: {rd['account']}")
                cash_v = money_input("Số dư tiền (âm = dư nợ)", 0, key=f"cash_in_{n}")
                nav_v = money_input("NAV theo OPT (để đối chiếu)", 0, key=f"nav_in_{n}")
                hdf = st.data_editor(ss[f"hold_in_{n}"], num_rows="dynamic", hide_index=True, width="stretch",
                                     key=f"hold_ed_{n}",
                                     column_config={"SLCP": st.column_config.NumberColumn(format="%d", min_value=0, step=100),
                                                    "Giá TT": st.column_config.NumberColumn(format="%d", min_value=0, step=50,
                                                        help="Giá thị trường trong OPT (suy từ GTTT / GD). Để 0 = dùng giá đang lưu trong app.")})
                # (mã, SLCP, giá dùng để tính): giá lấy từ ảnh OPT, nếu trống thì dùng giá app đang lưu
                rows3 = [(str(r_["Mã"]).strip().upper(), float(r_["SLCP"] or 0), float(r_["Giá TT"] or 0)) for _, r_ in hdf.iterrows()
                         if isinstance(r_["Mã"], str) and r_["Mã"].strip()]
                rows = [(t, q) for t, q, _ in rows3]
                nav_calc = cash_v + sum(q * (g or px.get(t, 0)) for t, q, g in rows3)
                if nav_v:
                    diff = nav_calc - nav_v
                    if abs(diff) <= max(1000.0, abs(nav_v) * 0.0005):
                        st.success(f"NAV khớp OPT: {fmt_vnd(nav_calc)}")
                    else:
                        st.error(f"NAV app = {fmt_vnd(nav_calc)} · OPT = {fmt_vnd(nav_v)} · lệch {fmt_vnd(diff)}. "
                                 "Kiểm tra lại số dư, SLCP và cột Giá TT.")
                else:
                    st.caption(f"NAV app tính: {fmt_vnd(nav_calc)} (nhập NAV theo OPT để đối chiếu)")
                # ---- phần điều chỉnh giữ lại từ công thức của file (lệnh bán chờ, rút/nạp tiền dự kiến...)
                sh_ = sheet_of[n]
                has_read = bool(ss.get("snap_read_" + n))
                pos_ = {p_["ticker"]: p_ for p_ in sh_["positions"]}
                cs_ = xlsxformula.split_cash(sh_.get("cash_raw"))
                old_adj_cash = cs_[1] if cs_ else ""
                old_adj_q = {t: xlsxformula.split_qty(pos_[t].get("qty_raw"), q)["adj"] for t, q, g in rows3 if t in pos_}
                has_old_adj = bool(old_adj_cash) or any(old_adj_q.values())
                keep_adj = False
                if has_old_adj:
                    keep_adj = st.checkbox("Giữ phần điều chỉnh trong công thức của file (lệnh chờ, rút/nạp dự kiến)", value=False,
                                           key=f"keepadj_{n}",
                                           help="Mặc định TẮT: file được ghi đúng số OPT (số dư tiền, SLCP, giá) nên NAV trong Excel khớp NAV OPT. "
                                                "Bật nếu bạn muốn giữ phần điều chỉnh cũ như +6.4*10^6*E2-110*10^9 hay -6400000.")
                    if not keep_adj:
                        st.caption("File sẽ được ghi đúng số OPT. Phần điều chỉnh cũ sẽ bị bỏ: "
                                   + "; ".join(x for x in [f"tiền {old_adj_cash}" if old_adj_cash else "",
                                                           *[f"SLCP {t} {v}" for t, v in old_adj_q.items() if v]] if x))
                qs_, adj_q = {}, {}
                adj_cash = ""
                if keep_adj:
                    adj_cash = st.text_input("Điều chỉnh tiền (ô B3)", value=old_adj_cash, key=f"adjc_{n}",
                                             help="Phần công thức đứng sau số dư OPT, ví dụ +900*10^3*E2-14*10^9. Để trống nếu không có.")
                if cs_ is None:
                    st.warning("Ô B3 của sheet này có công thức khác dạng thường gặp, nên sẽ được ghi bằng số thường.")
                for t, q, g in rows3:
                    if t in pos_:
                        qs_[t] = xlsxformula.split_qty(pos_[t].get("qty_raw"), q)
                        adj_q[t] = ""
                        if keep_adj:
                            adj_q[t] = st.text_input(f"Điều chỉnh SLCP · {t}", value=qs_[t]["adj"], key=f"adjq_{n}_{t}",
                                                     help="Phần công thức đứng sau SLCP OPT, ví dụ -900000 (lệnh bán chờ). Để trống nếu không có.")
                row_first = min((p_["row"] for p_ in pos_.values()), default=2)
                eprice = next((g or px.get(t, 0) for t, q, g in rows3 if pos_.get(t, {}).get("row") == row_first), 0)
                ac_ = xlsxformula.evaluate(adj_cash, eprice)
                adj_ok = ac_ is not None
                if not adj_ok:
                    st.error("Không tính được 'Điều chỉnh tiền'. Chỉ dùng số, + - * / ^ ( ) và E2.")
                cash_total = cash_v + (ac_ or 0.0)
                qty_total = {}
                for t, q, g in rows3:
                    av = xlsxformula.evaluate(adj_q.get(t, "")) if t in adj_q else 0.0
                    if av is None:
                        adj_ok = False
                        st.error(f"Không tính được 'Điều chỉnh SLCP' của {t}.")
                        av = 0.0
                    qty_total[t] = q + av
                nav_model = cash_total + sum(qty_total[t] * (g or px.get(t, 0)) for t, q, g in rows3)
                # ---- đối chiếu FILE EXCEL hiện tại với (OPT + điều chỉnh)
                fx_price = {t: p_["price"] for t, p_ in pos_.items()}
                fx_qty = {t: p_["qty"] for t, p_ in pos_.items()}
                fx_nav = sh_["cash"] + sum(p_["qty"] * p_["price"] for p_ in pos_.values() if p_["row"] <= 4)
                if not has_read:
                    st.warning("Ảnh này CHƯA được đọc, nên cột bên dưới chỉ là số đang có trong form (số cũ của file), chưa phải số trong ảnh.")
                elif not nav_v:
                    st.warning("Chưa có NAV theo OPT nên chưa đối chiếu được NAV với ảnh. Nhập NAV từ ảnh vào ô trên.")
                cmp_rows = [("Số dư tiền (B3)", sh_["cash"], cash_total), ("NAV (B4)", fx_nav, nav_model)]
                for t, q, g in rows3:
                    cmp_rows.append((f"{t} · SLCP", fx_qty.get(t, 0.0), qty_total[t]))
                    cmp_rows.append((f"{t} · Giá", fx_price.get(t, 0.0), g or px.get(t, 0)))
                for t in fx_qty:
                    if t not in {r_[0] for r_ in rows3} and fx_qty[t]:
                        cmp_rows.append((f"{t} · SLCP", fx_qty[t], 0.0))
                cdf = pd.DataFrame([{"Mục": k, "File Excel (hiện tại)": fmt_vnd(a_), "Mới (OPT + điều chỉnh)": fmt_vnd(b_),
                                     "Lệch": fmt_vnd(b_ - a_), "": "✅ khớp" if abs(b_ - a_) < 1 else "❌ lệch"} for k, a_, b_ in cmp_rows])
                n_bad = sum(abs(b_ - a_) >= 1 for _, a_, b_ in cmp_rows)
                if n_bad:
                    st.warning(f"File Excel hiện tại lệch số mới ở {n_bad} mục. Bấm Xác nhận để cập nhật, rồi xuất file ở bước 5.")
                else:
                    st.success("File Excel hiện tại đã khớp (OPT + điều chỉnh), không cần cập nhật.")
                st.dataframe(cdf, hide_index=True, width="stretch")
                st.caption(f"Số OPT thô: số dư tiền {fmt_vnd(cash_v)} · NAV OPT {fmt_vnd(nav_v) if nav_v else 'chưa có'}. "
                           "NAV trong Excel = (OPT + điều chỉnh), nên có thể khác NAV OPT đúng bằng phần điều chỉnh.")
                miss = [t for t, _ in rows if px.get(t, 0) <= 0 and t not in [p.ticker for p in cu["positions"]]]
                if miss:
                    st.warning("Mã chưa có giá trong file: " + ", ".join(miss))
                nav_bad = bool(nav_v) and abs(nav_calc - nav_v) > max(1000.0, abs(nav_v) * 0.0005)
                force = False
                if nav_bad:
                    force = st.checkbox("NAV đang lệch OPT, tôi đã kiểm tra và vẫn muốn cập nhật", key=f"force_{n}")
                can_apply = has_read and (force or not nav_bad) and adj_ok
                if not has_read:
                    st.caption("Cần đọc ảnh trước khi xác nhận (hoặc gõ tay rồi tick đã kiểm tra bên dưới).")
                    can_apply = st.checkbox("Tôi đã gõ tay đúng số theo ảnh", key=f"manual_{n}") and adj_ok
                if st.button("Xác nhận & cập nhật tài khoản này", key=f"apply_{n}", type="primary", disabled=not can_apply):
                    db.save_cash([{"id": cu["id"], "cash": float(cash_total), "confirm": True}])
                    merged = {t: qty_total[t] for t, _ in rows}
                    for p in cu["positions"]:
                        merged.setdefault(p.ticker, 0.0)   # mã không còn trong ảnh -> SL = 0 (giữ dòng trong file)
                    db.replace_quantities([(n, t, q) for t, q in merged.items()])
                    newpx = {t: g for t, _, g in rows3 if g > 0}
                    if newpx:
                        with db.conn() as c_:
                            for t, g in newpx.items():
                                c_.execute("INSERT INTO prices(ticker,price,updated_at) VALUES(?,?,?) "
                                           "ON CONFLICT(ticker) DO UPDATE SET price=excluded.price, updated_at=excluded.updated_at",
                                           (t, g, db.now()))
                    ss.setdefault("snap_px", {})[n] = newpx
                    ss.setdefault("snap_nav", {})[n] = float(nav_v or 0)
                    # công thức sẽ ghi vào file: thay số OPT, giữ phần điều chỉnh
                    fm = {}
                    if cs_ is not None:
                        fm["B3"] = ("=" + xlsxformula.fmt_num(cash_v) + adj_cash) if adj_cash else float(cash_v)
                    else:
                        fm["B3"] = float(cash_total)
                    for t, q, g in rows3:
                        if t in pos_:
                            if qs_[t].get("keep") and adj_q[t] == qs_[t]["adj"]:
                                continue
                            fm[f"D{pos_[t]['row']}"] = ("=" + xlsxformula.fmt_num(q) + adj_q[t]) if adj_q[t] else float(q)
                    for t, p_ in pos_.items():
                        if t not in {r_[0] for r_ in rows3}:
                            fm[f"D{p_['row']}"] = 0.0          # mã không còn trong ảnh
                    ss.setdefault("snap_formulas", {})[n] = fm
                    ss.setdefault("snap_model", {})[n] = dict(cash=float(cash_total), nav=float(nav_model))
                    ss["snap_applied"].add(n)
                    db.save_nav(today, db.acct_key(cu["account_no"], n), n, float(nav_model), float(cash_total),
                                float(nav_model) - float(cash_total), "daily")   # lưu NAV cho dashboard
                    st.success("Đã cập nhật.")
                    st.rerun()

    # ---------- Bước 5
    st.subheader("Bước 5 · Xuất lại file Excel")
    st.caption("Ghi lại **số dư tiền (B3)** và **SLCP (cột D)** của các tài khoản đã xác nhận: số OPT được thay vào công thức, "
               "phần điều chỉnh giữ nguyên. Giá (cột E) chỉ ghi vào ô đang là số; ô là liên kết sang sheet khác "
               "(vd ='Duyên 814345'!E2) được giữ nguyên liên kết. Mọi ô khác (công thức, tỉ lệ, hạn mức, ảnh) giữ nguyên; Excel tự tính lại khi mở file.")
    write_px = st.checkbox("Cập nhật giá thị trường (cột E) theo OPT", value=True)
    gp: dict[str, float] = {}
    for d_ in ss.get("snap_px", {}).values():
        gp.update(d_)
    all_px = st.checkbox("Cập nhật giá (cột E) cả cho các tài khoản CHƯA có ảnh, theo giá OPT của các mã đã đọc", value=True,
                         help="Giá thị trường là chung cho mọi tài khoản. Ô giá là liên kết thì giữ nguyên liên kết.")
    chosen = st.multiselect("Tài khoản ghi vào file", names, format_func=acc_lab, default=[n for n in names if n in ss["snap_applied"]])

    def _is_link(v) -> bool:
        return isinstance(v, str) and v.startswith("=")

    if chosen or (write_px and all_px and gp):
        fresh = {c["name"]: c for c in service.load_customers()}
        px_all = service.prices()
        edits, notes, newrows = {}, [], {}
        for n in chosen:
            sh = sheet_of[n]
            cells = dict(ss.get("snap_formulas", {}).get(n, {}))
            rowof = {p["ticker"]: p["row"] for p in sh["positions"]}
            raw_px = {p["ticker"]: p.get("price_raw") for p in sh["positions"]}
            for p in fresh[n]["positions"]:
                if p.ticker not in rowof and p.qty > 0:
                    used = set(rowof.values()) | {r for r, _, _ in newrows.get(sh["sheet"], [])}
                    free = [r for r in (2, 3, 4) if r not in used]
                    if rowof and free:
                        g_ = ss.get("snap_px", {}).get(n, {}).get(p.ticker) or px_all.get(p.ticker, 0)
                        newrows.setdefault(sh["sheet"], []).append(
                            (free[0], min(rowof.values()), {"C": p.ticker, "D": p.qty, "E": g_, "F": p.im_pct, "O": p.limit}))
                        rowof[p.ticker] = free[0]
                        notes.append(f"{acc_lab(n)}: thêm mã mới {p.ticker} vào dòng {free[0]} (công thức copy từ dòng có sẵn; tỉ lệ ký quỹ {p.im_pct:g}%, hạn mức {p.limit:,.0f}).")
                    else:
                        notes.append(f"{acc_lab(n)}: mã {p.ticker} chưa có dòng và sheet hết dòng trống 2–4, cần thêm tay vào Excel (SL {p.qty:,.0f}).")
            if write_px:
                for t, g in ss.get("snap_px", {}).get(n, {}).items():
                    if t in rowof and g > 0 and t in raw_px and not _is_link(raw_px[t]):
                        cells[f"E{rowof[t]}"] = g
            maxrow = max([p_["row"] for p_ in sh["positions"]], default=2)
            if maxrow > 4:
                notes.append(f"{acc_lab(n)}: file chỉ cộng giá trị thị trường ở dòng 2–4 (=SUM(G2:G4)) nhưng có mã ở dòng {maxrow}; NAV trong Excel sẽ thiếu mã đó, cần sửa công thức G6.")
            if n not in ss.get("snap_formulas", {}):
                notes.append(f"{acc_lab(n)}: chưa xác nhận ở bước 4 trong phiên này nên chỉ cập nhật giá (nếu có), chưa ghi số dư và SLCP.")
            mm_ = ss.get("snap_model", {}).get(n)
            if mm_:
                notes.append(f"{acc_lab(n)}: NAV trong Excel dự kiến sau khi mở = {fmt_vnd(mm_['nav'])} (đã gồm phần điều chỉnh).")
            if cells:
                edits[sh["sheet"]] = cells
        # tài khoản không chọn: chỉ cập nhật giá cột E (ô là số), KHÔNG đụng số dư và SLCP
        others = []
        if write_px and all_px and gp:
            for n in names:
                if n in chosen:
                    continue
                sh = sheet_of[n]
                cells = {f"E{p_['row']}": gp[p_["ticker"]] for p_ in sh["positions"]
                         if gp.get(p_["ticker"], 0) > 0 and not _is_link(p_.get("price_raw"))}
                if cells:
                    edits[sh["sheet"]] = cells
                    others.append(n)
        if others:
            st.caption("Chỉ cập nhật giá, giữ nguyên số dư và SLCP: " + ", ".join(others))
        out_bytes, failed = xlsxpatch.patch_workbook(orig_bytes, edits, newrows)
        for x in notes:
            st.info(x) if "dự kiến" in x else st.warning(x)
        if failed:
            st.warning("Không ghi được ô: " + ", ".join(failed))
        st.download_button("Tải file Excel đã cập nhật", out_bytes, file_name=f"cap_nhat_{today}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
        _g = ss.get("daily_group")
        if _g and st.button(f"Lưu file đã cập nhật vào thư mục nhóm {_g}", key="dly_save_out"):
            groupstore.save(_g, out_bytes, "capnhat", f"cap_nhat_{today}")
            st.success(f"Đã lưu vào thư mục nhóm {_g}.")
    else:
        st.info("Chưa có tài khoản nào được xác nhận ở bước 4.")


with tab_flow:
    _flow()

# ============================================================ NHẬP TAY (DỰ PHÒNG)
with tab_in:
    if not custs:
        st.info('Chưa có khách hàng.')
        st.stop()
    st.subheader("Số dư tiền")
    st.caption("Gõ số dư từ OPT (âm = dư nợ). Có thể copy một cột từ Excel rồi dán vào bảng. "
               "KH giữ nguyên số cũ thì tick **Xác nhận**.")
    cash_df = pd.DataFrame([{
        "id": c["id"], "Tài khoản": service.acct_label(c["name"], c["account_no"]),
        "Số dư tiền": float(c["cash"] or 0), "Xác nhận": False,
        "Cập nhật": "hôm nay" if c["cash_date"] == today else (c["cash_date"] or "chưa bao giờ"),
    } for c in custs])
    ed_cash = st.data_editor(
        cash_df, hide_index=True, width="stretch", key="cash_editor",
        disabled=["id", "Tài khoản", "Cập nhật"],
        column_config={"id": None, "Số dư tiền": st.column_config.NumberColumn(format="%d", step=1)})
    stale = [service.acct_label(c["name"], c["account_no"]) for c in custs if c["cash_date"] != today]
    if stale:
        st.caption(f"Chưa cập nhật số dư hôm nay: {', '.join(stale)}")
    if st.button("Lưu số dư", type="primary"):
        n = db.save_cash([{"id": int(r["id"]), "cash": float(r["Số dư tiền"] or 0), "confirm": bool(r["Xác nhận"])}
                          for _, r in ed_cash.iterrows()])
        st.success(f"Đã cập nhật {n} tài khoản.")
        st.rerun()

    st.divider()
    st.subheader("SLCP (số lượng cổ phiếu đang giữ)")
    st.caption("Sửa khối lượng, thêm dòng mới (chọn KH, gõ mã) hoặc xoá dòng nếu KH đã bán hết. "
               "Mã mới tự lấy tỉ lệ ký quỹ và hạn mức từ danh mục cho vay.")
    names = [acc_lab(c["name"]) for c in custs]
    pos_df = pd.DataFrame([{"Khách hàng": acc_lab(c["name"]), "Mã": p.ticker, "SLCP": float(p.qty)}
                           for c in custs for p in c["positions"]])
    ed_pos = st.data_editor(
        pos_df, num_rows="dynamic", hide_index=True, width="stretch", key="pos_editor",
        column_config={"Khách hàng": st.column_config.SelectboxColumn(options=names, required=True),
                       "SLCP": st.column_config.NumberColumn(format="%d", min_value=0, step=100)})
    if st.button("Lưu SLCP"):
        back_ = {v: k for k, v in LM.items()}
        rows = [(back_.get(r["Khách hàng"], r["Khách hàng"]), str(r["Mã"]), r["SLCP"]) for _, r in ed_pos.iterrows()
                if isinstance(r["Khách hàng"], str) and isinstance(r["Mã"], str) and r["Mã"].strip()]
        a, u, d = db.replace_quantities(rows)
        st.success(f"Thêm {a} mã, sửa {u} mã, xoá {d} mã.")
        st.rerun()

    st.divider()
    st.subheader("Giá đóng cửa")
    px = service.prices()
    with db.conn() as c:
        px_dt = {r["ticker"]: (r["updated_at"] or "")[:10] for r in c.execute("SELECT ticker, updated_at FROM prices")}
    used = sorted({p.ticker for cu in custs for p in cu["positions"]})
    px_df = pd.DataFrame([{"Mã": t, "Giá đóng cửa (VND)": float(px.get(t, 0)),
                           "Cập nhật": "hôm nay" if px_dt.get(t) == today else (px_dt.get(t) or "-")} for t in used])
    ed_px = st.data_editor(px_df, hide_index=True, width="stretch", key="px_daily",
                           disabled=["Mã", "Cập nhật"],
                           column_config={"Giá đóng cửa (VND)": st.column_config.NumberColumn(format="%d", step=50)})
    if st.button("Lưu giá đóng cửa"):
        with db.conn() as c:
            for _, r in ed_px.iterrows():
                # Giá không đổi so với hôm qua vẫn được coi là đã cập nhật: ghi đè mốc thời gian mỗi lần lưu
                c.execute("INSERT INTO prices(ticker,price,updated_at) VALUES(?,?,?) "
                          "ON CONFLICT(ticker) DO UPDATE SET price=excluded.price, updated_at=excluded.updated_at",
                          (r["Mã"], float(r["Giá đóng cửa (VND)"]), db.now()))
        st.success("Đã lưu giá đóng cửa.")
        st.rerun()

# ============================================================ 2. KẾT QUẢ
with tab_out:
    custs = service.load_customers()
    results = service.compute_all()
    s = service.settings()

    # ---- cảnh báo dữ liệu cũ
    stale_cash = [service.acct_label(c["name"], c["account_no"]) for c in custs if c["cash_date"] != today]
    with db.conn() as c:
        px_dt = {r["ticker"]: (r["updated_at"] or "")[:10] for r in c.execute("SELECT ticker, updated_at FROM prices")}
    held = {p.ticker for cu in custs for p in cu["positions"] if p.qty > 0}
    stale_px = sorted(t for t in held if px_dt.get(t) != today)
    if stale_cash:
        st.warning("Chưa cập nhật số dư hôm nay: " + ", ".join(stale_cash))
    if stale_px:
        st.warning("Chưa cập nhật giá đóng cửa hôm nay: " + ", ".join(stale_px))

    # ---- tổng
    debt = dailyreport.total_debt(results)
    nav = sum(r["nav"] for r in results)
    stock_value = sum(r["total_value"] for r in results)
    def ty(x):
        return f"{x / 1e9:,.2f} tỷ"

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tổng dư nợ", ty(debt), help=fmt_vnd(debt) + " VND")
    m2.metric("Tổng NAV", ty(nav), help=fmt_vnd(nav) + " VND")
    m3.metric("Tổng giá trị CK", ty(stock_value), help=fmt_vnd(stock_value) + " VND")
    m4.metric("KH Call / FS", f"{sum(r['status'] == 'call' for r in results)} / {sum(r['status'] == 'fs' for r in results)}")

    st.caption(f"Tổng dư nợ: {fmt_vnd(debt)} · Tổng NAV: {fmt_vnd(nav)} · Tổng giá trị CK: {fmt_vnd(stock_value)} (VND)")

    # ---- check sức
    st.subheader("Check sức mua")
    rows = []
    for r in sorted(results, key=lambda x: (x["mr"] if x["mr"] is not None else 9)):
        rows.append({
            "": STATUS_ICON[r["status"]], "Tài khoản": service.acct_label(r["name"], r["account_no"]), "Dư nợ": fmt_vnd(max(0.0, -r["cash"])),
            "NAV": fmt_vnd(r["nav"]), "MR": fmt_pct(r["mr"]), "Thừa KQ duy trì": fmt_vnd(r["ee_dt"]),
            "Số mã còn sức mua": len(dailyreport.buying_rows(r)), "Kết luận": dailyreport.check_note(r),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    # ---- báo cáo sức mua
    st.subheader("Báo cáo sức mua (chỉ mã có sức mua dương)")
    rep = []
    for r in sorted(results, key=lambda x: x["name"]):
        for b in dailyreport.buying_rows(r):
            rep.append({"Khách hàng": service.acct_label(r["name"], r["account_no"]), "Mã": b["ticker"], "Giá tạm tính": b["price"],
                        "Hạn mức còn lại": b["remaining"], "SLCP mua tối đa": b["max_qty"],
                        "Sức mua": b["buying_power"]})
    if not rep:
        st.info("Hiện không KH nào còn sức mua dương.")
    else:
        rdf = pd.DataFrame(rep)
        show = rdf.copy()
        for col in ["Giá tạm tính", "Hạn mức còn lại", "SLCP mua tối đa", "Sức mua"]:
            show[col] = show[col].map(fmt_vnd)
        st.dataframe(show, hide_index=True, width="stretch")
        st.caption("SLCP mua tối đa làm tròn xuống lô 100. Sức mua tính theo thừa ký quỹ duy trì (giống file Excel).")

        # bản text để copy dán sang Zalo/Excel: mỗi KH một khối
        lines = []
        for name, g in rdf.groupby("Khách hàng", sort=True):
            lines.append(name)
            for _, x in g.iterrows():
                lines.append(f"  {x['Mã']}: giá {fmt_vnd(x['Giá tạm tính'])} · HM còn lại {fmt_vnd(x['Hạn mức còn lại'])}"
                             f" · SLCP tối đa {fmt_vnd(x['SLCP mua tối đa'])}")
            lines.append("")
        with st.expander("Bản text để copy"):
            st.code("\n".join(lines).strip(), language=None)

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            rdf.to_excel(xw, sheet_name="Sức mua", index=False)
            pd.DataFrame([{"Tổng dư nợ": debt, "Tổng NAV": nav, "Tổng giá trị CK": stock_value}]).to_excel(
                xw, sheet_name="Tổng", index=False)
        st.download_button("Tải Excel báo cáo", buf.getvalue(), file_name=f"bao_cao_suc_mua_{today}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ---- snapshot
    if st.button("Lưu snapshot hôm nay"):
        with db.conn() as c:
            for r in results:
                c.execute("INSERT INTO snapshots(day,customer_id,cash,nav,mr,status,data,created_at) VALUES(?,?,?,?,?,?,?,?) "
                          "ON CONFLICT(day,customer_id) DO UPDATE SET cash=excluded.cash, nav=excluded.nav, mr=excluded.mr, "
                          "status=excluded.status, data=excluded.data, created_at=excluded.created_at",
                          (today, r["id"], r["cash"], r["nav"], r["mr"], r["status"],
                           json.dumps({"holdings": [x for x in r["rows"] if x["qty"] > 0],
                                       "buying": dailyreport.buying_rows(r)}, ensure_ascii=False), db.now()))
        st.success(f"Đã lưu snapshot ngày {today} cho {len(results)} KH.")

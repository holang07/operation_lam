import hashlib
import math
import io

import pandas as pd
import streamlit as st

from core import db, service
from core.importer import parse_workbook
from core.loanlist import list_candidate_sheets, parse_loan_list
from core.margin import (compute, deposit_for_target, max_drop_before_call, qty_to_withdraw,
                         sell_and_withdraw, plan_withdraw)
from core import multi, livequote
from core.numfmt import money_input
from core import msgfmt, sourcepanel, callmsg, depmsg
from datetime import datetime
from dataclasses import replace as _repl
from core.service import STATUS_ICON, STATUS_LABEL, fmt_pct, fmt_vnd


def _apply_box(key: str, ops: list, desc: list) -> None:
    """Nút ghi nhận giao dịch đã thực hiện: cập nhật tiền + SLCP rồi tính lại toàn hệ thống."""
    st.markdown("##### ✅ Ghi nhận giao dịch đã thực hiện (cập nhật toàn hệ thống)")
    for d_ in desc:
        st.write("• " + d_)
    if st.button("Ghi nhận giao dịch này", type="primary", key=f"ap_{key}", disabled=not ops):
        db.apply_ops(ops)
        st.session_state["apdep_msg"] = "Đã cập nhật " + str(len({o['name'] for o in ops})) + " tài khoản: " + "; ".join(desc)
        st.rerun()
    if st.session_state.get("apdep_msg"):
        st.success(st.session_state["apdep_msg"])
    _export_box()


def _export_box() -> None:
    """Nút xuất lại file Excel gốc đã cập nhật theo dữ liệu trong app."""
    from core import xlsxexport
    orig = db.DB_PATH.parent / "daily_original.xlsx"
    st.markdown("##### 📥 Xuất lại file Excel đã cập nhật")
    if not orig.exists():
        st.info("Chưa có file Excel gốc. Hãy nạp file ở tab **Nguồn dữ liệu** (hoặc trang Báo cáo hằng ngày) để xuất lại được.")
        return
    try:
        out, notes, failed, changed = xlsxexport.build(orig.read_bytes())
    except Exception as e:  # noqa: BLE001
        st.error(f"Không xuất được file: {e}")
        return
    st.caption(f"File gốc: ghi lúc {pd.Timestamp(orig.stat().st_mtime, unit='s').strftime('%d/%m %H:%M')} · "
               f"{changed} tài khoản có thay đổi so với file gốc.")
    for n_ in notes:
        st.write("• " + n_)
    for f_ in failed:
        st.warning(f_)
    st.download_button("Tải file Excel đã cập nhật", out, file_name=f"MR_capnhat_{db.today()}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       disabled=not changed, key="exp_dl")

st.title("Khách hàng & Margin")

tab_list, tab_detail, tab_tools, tab_prices, tab_loan, tab_import = st.tabs(
    ["Tổng quan", "Chi tiết & thử giả định", "Công cụ nộp / rút tiền", "Giá cổ phiếu",
     "Danh mục cho vay", "Nguồn dữ liệu"])

res = service.compute_all()
s = service.settings()

# ---------------------------------------------------------------- Tổng quan
with tab_list:
    res_full = res
    if res_full:
        grp_of = lambda r_: (r_["customer"].get("group_name") or "").strip()  # noqa: E731
        gcount: dict[str, int] = {}
        for r_ in res_full:
            gcount[grp_of(r_) or "(chưa có nhóm)"] = gcount.get(grp_of(r_) or "(chưa có nhóm)", 0) + 1
        gopts = ["Tất cả nhóm"] + [f"{g} ({n})" for g, n in sorted(gcount.items(), key=lambda x: (x[0] == "(chưa có nhóm)", x[0]))]
        gsel = st.selectbox("Xem theo nhóm", gopts, key="ov_group")
        if gsel != "Tất cả nhóm":
            gname = gsel.rsplit(" (", 1)[0]
            res = [r_ for r_ in res_full if (grp_of(r_) or "(chưa có nhóm)") == gname]
        else:
            res = res_full
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Số tài khoản", len(res))
        m2.metric("Tổng NAV", fmt_vnd(sum(r_["nav"] for r_ in res)))
        m3.metric("Tổng dư nợ", fmt_vnd(sum(-r_["cash"] for r_ in res if r_["cash"] < 0)))
        n_call = sum(1 for r_ in res if r_["status"] != "bình thường")
        m4.metric("Đang Call / FS", n_call)
    if not res:
        st.info("Chưa có dữ liệu. Sang tab **Import từ Excel**.")
    else:
        rows = []
        for i_, r in enumerate(sorted(res, key=lambda x: (x["mr"] if x["mr"] is not None else 9)), 1):
            rows.append({
                "STT": i_, "": STATUS_ICON[r["status"]], "Tài khoản": service.acct_label(r["name"], r["account_no"]),
                "Số dư tiền": fmt_vnd(r["cash"]), "NAV": fmt_vnd(r["nav"]),
                "IMR DT": fmt_vnd(r["imr_dt"]), "MR": fmt_pct(r["mr"]), "EE DT": fmt_vnd(r["ee_dt"]),
                "Tình trạng": STATUS_LABEL[r["status"]],
                "Tiền cần nộp": fmt_vnd(r["call_amount"]) if r["call_amount"] else "-",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Các số hiển thị theo Dtrade (DT): IM DT = IM × tỷ lệ tài khoản. "
                   "MR là MR thường như file Excel; IMR, EE và sức mua tính theo DT.")
        st.caption(f"Ngưỡng: FS khi MR < {s.fs_threshold*100:.0f}%, Call khi MR < {s.call_threshold*100:.0f}%, "
                   f"tiền nộp tính để đưa MR về {s.call_target*100:.1f}%. Đổi trong **Cài đặt**.")

        st.divider()
        callmsg.render(res)
        # ---- Giá TT: xem nhanh tài khoản ra sao khi giá thị trường đổi
        st.divider()
        st.markdown("#### Giá thị trường hiện tại: kiểm tra MR trong phiên")
        held = sorted({p.ticker for r_ in res for p in r_["customer"]["positions"]})
        px_db = service.prices()
        b1, b2 = st.columns([1, 3])
        if b1.button("🔄 Cập nhật giá TT", type="primary", key="lq_btn"):
            with st.spinner("Đang lấy giá thị trường..."):
                got = livequote.fetch_all(held)
            old = st.session_state.get("live_px", {})
            st.session_state["live_px"] = {**old, **got["prices"]}
            st.session_state["live_ts"] = datetime.now().strftime("%H:%M:%S")
            st.session_state["live_fail"] = got["failed"]
            st.session_state["live_err"] = got["errors"]
            st.session_state["lq_ver"] = st.session_state.get("lq_ver", 0) + 1
        live = st.session_state.get("live_px", {})
        if st.session_state.get("live_fail"):
            b2.warning("Không lấy được giá: " + ", ".join(st.session_state["live_fail"]) +
                       ". Bạn có thể nhập tay vào bảng bên dưới; mã chưa có giá TT vẫn dùng giá Excel.")
            with b2.expander("Chi tiết lỗi"):
                st.write("\n".join(st.session_state.get("live_err", [])))
        if live:
            b2.caption(f"Giá cập nhật lúc {st.session_state.get('live_ts', '-')}. Nguồn công khai có thể chậm vài phút "
                       "so với bảng giá công ty, hãy đối chiếu trước khi báo KH.")
        with st.expander("Giá TT từng mã (sửa tay được)", expanded=bool(live) and bool(st.session_state.get("live_fail"))):
            dfp = pd.DataFrame({"Mã": held, "Giá Excel": [px_db.get(t, 0) for t in held],
                                "Giá TT": [live.get(t) for t in held]})
            edp = st.data_editor(dfp, hide_index=True, width="stretch", disabled=["Mã", "Giá Excel"],
                                 key=f"lq_ed_{st.session_state.get('lq_ver', 0)}")
            live = {r_["Mã"]: float(r_["Giá TT"]) for _, r_ in edp.iterrows()
                    if pd.notna(r_["Giá TT"]) and float(r_["Giá TT"]) > 0}
            if st.button("Xóa giá TT", key="lq_clear"):
                for k in ("live_px", "live_ts", "live_fail", "live_err"):
                    st.session_state.pop(k, None)
                st.session_state["lq_ver"] = st.session_state.get("lq_ver", 0) + 1
                st.rerun()
        if live:
            rows2, n_call2, n_fs2 = [], 0, 0
            for r_ in res:
                cu_ = r_["customer"]
                pos2 = [_repl(p, price=live.get(p.ticker, p.price)) for p in cu_["positions"]]
                r2 = compute(cu_["cash"], pos2, cu_["mm"] or s.default_mm, s)
                n_call2 += r2["status"] == "call"
                n_fs2 += r2["status"] == "fs"
                chg = (r2["nav"] - r_["nav"]) if r_["nav"] is not None and r2["nav"] is not None else None
                rows2.append((r2["mr"] if r2["mr"] is not None else 9, {
                    "": STATUS_ICON[r2["status"]], "Tài khoản": service.acct_label(r_["name"], r_["account_no"]),
                    "NAV (giá Excel)": fmt_vnd(r_["nav"]), "NAV (giá TT)": fmt_vnd(r2["nav"]),
                    "Chênh NAV": fmt_vnd(chg), "MR (giá Excel)": fmt_pct(r_["mr"]),
                    "MR (giá TT)": fmt_pct(r2["mr"]), "Tình trạng (giá TT)": STATUS_LABEL[r2["status"]],
                    "Tiền cần nộp": fmt_vnd(r2["call_amount"]) if r2["call_amount"] else "-"}))
            m1, m2, m3 = st.columns(3)
            m1.metric("Call theo giá TT", n_call2, delta=n_call2 - sum(r_["status"] == "call" for r_ in res), delta_color="inverse")
            m2.metric("FS theo giá TT", n_fs2, delta=n_fs2 - sum(r_["status"] == "fs" for r_ in res), delta_color="inverse")
            m3.metric("Số mã có giá TT", len(live))
            out2 = [dict(STT=i, **d) for i, (_, d) in enumerate(sorted(rows2, key=lambda x: x[0]), 1)]
            st.dataframe(pd.DataFrame(out2), hide_index=True, width="stretch")
            st.caption("Bảng này chỉ để tham khảo, không ghi đè giá trong hệ thống. "
                       "Tình trạng và tiền cần nộp xét theo MR thường như phần trên.")

    res = res_full

# ---------------------------------------------------------------- Chi tiết
with tab_detail:
    if not res:
        st.info("Chưa có dữ liệu.")
    else:
        names = [service.acct_label(r["name"], r["account_no"]) for r in res]
        idx = st.selectbox("Chọn khách hàng", range(len(res)), format_func=lambda i: names[i])
        cu = res[idx]["customer"]
        mm = cu["mm"] or s.default_mm

        c1, c2, c3 = st.columns(3)
        deposit = money_input("Thử nộp thêm tiền (VND)", 0, key="try_dep", container=c1)
        shock_pct = c2.slider("Thử giá toàn bộ mã tăng/giảm (%)", -30, 20, 0)

        r = compute(cu["cash"], cu["positions"], mm, s, deposit=deposit, shock=shock_pct / 100)
        base = res[idx]

        tks_ = [x["ticker"] for x in r["rows"]]
        if tks_:
            best_ = max(range(len(tks_)), key=lambda i: r["rows"][i]["buying_power"] if r["rows"][i]["remaining"] > 0 else -1)
            bp_tk = c3.selectbox("Mã tính sức mua", tks_, index=best_, key=f"bp_tk_{cu['id']}")
            bp_row = next(x for x in r["rows"] if x["ticker"] == bp_tk)
            bp_val = bp_row["buying_power"] if bp_row["remaining"] > 0 else min(bp_row["buying_power"], 0.0)
            bp_qty = bp_row["max_qty"] if bp_row["remaining"] > 0 else 0
        else:
            bp_tk, bp_val, bp_qty = "-", 0.0, 0
        c3.caption(f"Tỷ lệ tài khoản: **{mm:.2f}** (sửa ở khung bên dưới)")

        m1, m2, m3, m4, m5 = st.columns([1.15, 0.9, 1.15, 1.25, 1.0])
        m1.metric("NAV", fmt_vnd(r["nav"]), delta=fmt_vnd(r["nav"] - base["nav"]) if (deposit or shock_pct) else None)
        m2.metric("MR", fmt_pct(r["mr"]))
        m3.metric("Thừa ký quỹ (EE DT)", fmt_vnd(r["ee_dt"]))
        with m4.container(key="bp_box"):
            st.metric(f"Sức mua · {bp_tk}", fmt_vnd(bp_val))
        m5.metric("Tình trạng", STATUS_ICON[r["status"]] + " " + STATUS_LABEL[r["status"]])

        if bp_row["remaining"] <= 0 if tks_ else False:
            st.warning(f"Mã {bp_tk} đã hết hạn mức còn lại nên sức mua = 0.")
        elif tks_:
            st.success(f"**Sức mua {bp_tk}: {fmt_vnd(bp_val)}** (mua tối đa khoảng {fmt_vnd(bp_qty)} cp), "
                       f"hạn mức còn lại của mã: {fmt_vnd(bp_row['remaining'])}.")
        st.caption("Số liệu theo Dtrade (DT): IM DT = IM × tỷ lệ tài khoản. EE DT âm nghĩa là đã dùng vượt mức ký quỹ; "
                   "tình trạng call/FS vẫn xét theo MR thường (giống file Excel của bạn).")
        if r["call_amount"] > 0:
            st.warning(f"Cần nộp **{fmt_vnd(r['call_amount'])}** VND để đưa MR về {s.call_target*100:.1f}%, "
                       "hoặc bán theo bảng dưới.")

        drop = max_drop_before_call(cu["cash"] + deposit, cu["positions"], mm, s)
        if drop is None:
            st.caption("Giá toàn bộ mã giảm tới 95% vẫn chưa chạm ngưỡng call.")
        elif drop == 0:
            st.caption("Tài khoản đang ở dưới ngưỡng call.")
        else:
            st.caption(f"Nếu giá **toàn bộ mã** cùng giảm khoảng **{drop*100:.1f}%** thì chạm ngưỡng call.")

        st.markdown("**Danh mục**")
        pos_df = pd.DataFrame([{
            "Mã": x["ticker"], "SL": x["qty"], "Giá": x["price"], "Tỉ lệ KQ %": x["im_pct"],
            "Giá trị": x["value"], "IMR DT": x["imr_dt"], "Hạn mức/mã": x["limit"],
            "Còn lại (HM)": x["remaining"], "Sức mua": x["buying_power"], "SL mua tối đa": x["max_qty"],
            "SL bán nếu call": x["sell_qty"],
        } for x in r["rows"]])
        show = pos_df.copy()
        for col in ["SL", "Giá", "Giá trị", "IMR DT", "Hạn mức/mã", "Còn lại (HM)", "Sức mua", "SL mua tối đa", "SL bán nếu call"]:
            show[col] = show[col].map(fmt_vnd)
        st.dataframe(show, hide_index=True, width="stretch")

        if r["sell_by_im"]:
            st.caption("Giá trị cần bán theo tỉ lệ ký quỹ của mã bán (tiền cần nộp ÷ tỉ lệ): " +
                       " · ".join(f"IM {int(k*100)}%: {fmt_vnd(v)}" for k, v in r["sell_by_im"].items()))

        with st.expander("Sửa số dư, tỷ lệ tài khoản, danh mục của KH này"):
            with st.form(f"edit_{cu['id']}"):
                e1, e2, e3 = st.columns(3)
                cash = money_input("Số dư tiền (âm = dư nợ)", int(cu["cash"]), key=f"cash_ed_{cu['id']}_{int(cu['cash'])}", container=e1, in_form=True)
                mm_in = e2.number_input("Tỷ lệ tài khoản", value=float(mm), min_value=0.1, max_value=1.0, step=0.05)
                extra = e3.text_input("Mã quan tâm thêm (cách nhau bằng dấu phẩy)", value=cu["extra_watch"] or "")
                note = st.text_area("Ghi chú", value=cu["note"] or "")
                ed = st.data_editor(
                    pd.DataFrame([{"Mã": p.ticker, "SL": p.qty, "Tỉ lệ KQ %": p.im_pct, "Hạn mức/mã": p.limit,
                                   "HM riêng KH": p.limit_custom} for p in cu["positions"]]),
                    num_rows="dynamic", hide_index=True, width="stretch", key=f"ed_{cu['id']}")
                if st.form_submit_button("Lưu thay đổi", type="primary"):
                    with db.conn() as c:
                        c.execute("UPDATE customers SET cash=?, mm=?, extra_watch=?, note=?, updated_at=? WHERE id=?",
                                  (cash, mm_in, extra.upper(), note, db.now(), cu["id"]))
                        c.execute("DELETE FROM positions WHERE customer_id=?", (cu["id"],))
                        for _, row in ed.dropna(subset=["Mã"]).iterrows():
                            if str(row["Mã"]).strip():
                                c.execute("INSERT INTO positions(customer_id,ticker,qty,im_pct,limit_vnd,limit_custom) VALUES(?,?,?,?,?,?)",
                                          (cu["id"], str(row["Mã"]).strip().upper(), float(row["SL"] or 0),
                                           float(row["Tỉ lệ KQ %"] or 100), float(row["Hạn mức/mã"] or 0),
                                           int(bool(row["HM riêng KH"]))))
                                c.execute("INSERT OR IGNORE INTO prices(ticker,price,updated_at) VALUES(?,0,?)",
                                          (str(row["Mã"]).strip().upper(), db.now()))
                    st.success("Đã lưu.")
                    st.rerun()

# ---------------------------------------------------------------- Công cụ (gộp 1 tab)
with tab_tools:
    if not res:
        st.info("Chưa có dữ liệu.")
    else:
        accs = [multi.acct_from(r_["customer"], s.default_mm) for r_ in res]
        labels = [service.acct_label(a_['name'], a_['acct']) for a_ in accs]
        px_all, ll_all = service.prices(), db.get_loan_list()
        all_t = sorted(set(px_all) | set(ll_all))
        held_t = sorted({p.ticker for a_ in accs for p in a_["positions"] if p.qty > 0})

        def _buy_inputs(prefix):
            a, b, c_, d_ = st.columns(4)
            tk_ = a.selectbox("Mã mua", all_t, key=f"{prefix}_tk")
            price_ = money_input("Giá (VND)", int(px_all.get(tk_, 0)) or 1000, key=f"{prefix}_px_{tk_}", container=b)
            inf = ll_all.get(tk_)
            im_ = c_.number_input("Tỉ lệ KQ (%)", value=float(inf["im_pct"]) if inf else 100.0, step=5.0,
                                  key=f"{prefix}_im_{tk_}")
            lim_ = d_.number_input("Hạn mức mã (tỷ)", value=(float(inf["limit_vnd"]) / 1e9) if inf else 0.0,
                                   step=10.0, key=f"{prefix}_lm_{tk_}") * 1e9
            if not inf and not any(p.ticker == tk_ for a_ in accs for p in a_["positions"]):
                st.warning(f"{tk_} chưa có trong danh mục cho vay nên IM 100%, hạn mức 0 và sức mua = 0. "
                           "Nhập IM, hạn mức ở đây hoặc nạp danh mục cho vay.")
            return tk_, float(price_), float(im_), float(lim_)

        def _after(a_, sales, w, fee=0.0):
            """MR DT và EE DT của tk sau khi bán `sales` và rút `w`."""
            cash, pos = a_["cash"], a_["positions"]
            for tk, q, px in sales:
                cash += q * px * (1 - fee / 100)
                pos = [type(p)(p.ticker, p.qty - q if p.ticker == tk else p.qty, p.price, p.im_pct, p.limit,
                               p.limit_custom) for p in pos]
            r2 = compute(cash - w, pos, a_["mm"], s)
            return r2

        tool = st.radio("Bạn muốn tính gì?", [
            "Hạn mức còn lại & sức mua của 1 mã",
            "Nộp tiền để đưa MR về mức an toàn",
            "Nộp tiền mua cổ phiếu (mua tối đa / chia vol)",
            "Rút tiền (bán mã nào, bao nhiêu)",
            "Bán 1 mã, nhận về mã khác (rút được / mua được)",
            "Soạn tin sức mua gửi KH (theo mẫu)",
            "Cú pháp chuyển tiền nộp"], key="mt_tool")

        # ---- 0. Hạn mức còn lại & sức mua của 1 mã
        if tool.startswith("Hạn mức còn lại"):
            with st.container(key="sec_buy"):
                st.markdown("##### 🟢 MUA")
                chosen = st.multiselect("Tài khoản", labels, default=labels, key="t0_acc")
                tk0, px0, im0, lim0 = _buy_inputs("t0")
            rows0, t_rem, t_bp, t_dep, t_val = [], 0.0, 0.0, 0.0, 0.0
            for nm in chosen:
                a_ = accs[labels.index(nm)]
                c0 = multi.buy_capacity(a_, tk0, px0, im0, lim0, 0.0, 100, s)
                held_q = sum(p.qty for p in a_["positions"] if p.ticker == tk0)
                if c0["hm_out"] or px0 <= 0:
                    q_hm, dep_max, val_hm = 0, 0.0, 0.0
                else:
                    k0 = c0["k"]
                    q_hm = (c0["remaining"] / ((1 - k0) * px0)) if k0 < 1 else (c0["remaining"] / px0)
                    q_hm = math.floor(q_hm / 100) * 100
                    dep_max = multi.deposit_for_qty(a_, tk0, px0, im0, lim0, q_hm, 100, s) if q_hm > 0 else 0.0
                    dep_max = dep_max or 0.0
                    val_hm = q_hm * px0
                t_rem += max(c0["remaining"], 0.0); t_bp += c0["bp"]; t_dep += dep_max; t_val += val_hm
                _z = lambda v: "-" if not v else fmt_vnd(v)
                rows0.append({"Tài khoản": nm, "Đang giữ (cp)": _z(held_q),
                              "Còn lại HM": fmt_vnd(c0["remaining"]) if not c0["hm_out"] else "HẾT HM",
                              "Sức mua": _z(c0["bp"]), "Nộp tối đa": _z(dep_max),
                              "Mua được nếu nộp tối đa": _z(val_hm), "EE DT": _z(c0["ee_dt"])})
            if rows0:
                rows0.append({"Tài khoản": "TỔNG", "Đang giữ (cp)": "", "Còn lại HM": _z(t_rem),
                              "Sức mua": _z(t_bp), "Nộp tối đa": _z(t_dep),
                              "Mua được nếu nộp tối đa": _z(t_val), "EE DT": ""})
                df0 = pd.DataFrame(rows0)
                _red = lambda row: ["color: #DC2626; font-weight: 700" if (c == "Còn lại HM" and row[c] == "HẾT HM")
                                    else "" for c in row.index]
                sty = (df0.style
                       .set_properties(subset=["Còn lại HM"], **{"background-color": "#FEF3C7", "font-weight": "700"})
                       .set_properties(subset=["Sức mua"], **{"background-color": "#DCFCE7", "font-weight": "700"})
                       .set_properties(subset=["Nộp tối đa"], **{"background-color": "#DBEAFE", "font-weight": "700"})
                       .apply(_red, axis=1))
                st.dataframe(sty, hide_index=True, width="stretch")
                st.success(f"**{tk0}** · {len(chosen)} tài khoản: còn lại hạn mức **{fmt_vnd(t_rem)}**, "
                           f"sức mua **{fmt_vnd(t_bp)}**, nộp tối đa **{fmt_vnd(t_dep)}** "
                           f"(để mua hết hạn mức còn lại, khoảng {fmt_vnd(t_val)} giá trị).")
            st.caption("Còn lại HM = hạn mức mã − phần vay đang dùng của mã. Nộp tối đa = số tiền tối thiểu cần nộp "
                       "để mua hết phần hạn mức còn lại; nộp thêm nữa cũng không mua thêm được mã này. "
                       "Sức mua tính theo EE DT, hạn mức hết thì sức mua = 0.")

        # ---- 1. Nộp để đưa MR về mức
        elif tool.startswith("Nộp tiền để"):
            chosen = st.multiselect("Tài khoản", labels, default=labels[:1], key="t1_acc")
            opts = {f"Về ngưỡng FS ({s.fs_threshold*100:.0f}%)": s.fs_threshold,
                    f"Về ngưỡng call ({s.call_threshold*100:.0f}%)": s.call_threshold,
                    f"Về mục tiêu ({s.call_target*100:.1f}%)": s.call_target, "MR tự nhập": None}
            pick = st.radio("Nộp để đưa MR về", list(opts), index=2, horizontal=True, key="dep_pick")
            target = opts[pick]
            if target is None:
                target = st.number_input("MR mong muốn (%)", value=60.0, min_value=1.0, step=1.0, key="dep_mr") / 100
            rows1, tot_need = [], 0.0
            for nm in chosen:
                a_ = accs[labels.index(nm)]
                d = deposit_for_target(a_["cash"], a_["positions"], a_["mm"], target, s)
                tot_need += d["need"]
                rows1.append({"Tài khoản": nm, "MR trước": fmt_pct(d["before"]["mr"]),
                              "Cần nộp": fmt_vnd(d["need"]), "MR sau": fmt_pct(d["after"]["mr"]),
                              "EE DT sau": fmt_vnd(d["after"]["ee_dt"])})
            if rows1:
                rows1.append({"Tài khoản": "TỔNG", "MR trước": "", "Cần nộp": fmt_vnd(tot_need), "MR sau": "", "EE DT sau": ""})
                st.dataframe(pd.DataFrame(rows1), hide_index=True, width="stretch")
                st.success(f"Tổng cần nộp: **{fmt_vnd(tot_need)}** VND ({len(chosen)} tài khoản).")
            st.caption("Cần nộp = MR mục tiêu × IMR − NAV (nộp tiền chỉ tăng NAV).")
            if chosen:
                st.markdown("##### ✅ Ghi nhận KH đã nộp tiền (cập nhật toàn hệ thống)")
                st.caption("Số tiền mặc định = cần nộp; sửa lại nếu KH nộp số khác. Bấm ghi nhận thì số dư tiền được cộng vào, "
                           "MR, trạng thái, sức mua... của tài khoản tự tính lại.")
                dep_in = {}
                cols_ = st.columns(min(len(chosen), 3))
                for i_, nm in enumerate(chosen):
                    a_ = accs[labels.index(nm)]
                    need_ = deposit_for_target(a_["cash"], a_["positions"], a_["mm"], target, s)["need"]
                    with cols_[i_ % len(cols_)]:
                        dep_in[nm] = money_input(f"Đã nộp - {nm} (VND)", int(round(need_)),
                                                 key=f"apdep_{nm}_{pick}_{int(round(need_))}")
                if st.button("Ghi nhận đã nộp", type="primary", key="apdep_btn",
                             disabled=not any(v > 0 for v in dep_in.values())):
                    done = []
                    for nm, v in dep_in.items():
                        if v > 0 and db.adjust_cash(accs[labels.index(nm)]["name"], v):
                            done.append(f"{nm}: +{fmt_vnd(v)}")
                    st.session_state["apdep_msg"] = "Đã cập nhật: " + "; ".join(done)
                    st.rerun()
            if st.session_state.get("apdep_msg"):
                st.success(st.session_state["apdep_msg"])
            _export_box()

        # ---- 2. Nộp tiền mua cổ phiếu
        elif tool.startswith("Nộp tiền mua"):
            tk_, price_, im_, lim_ = _buy_inputs("mb")
            sug = multi.suggest_accounts(accs, tk_, price_, im_, lim_, s=s)
            sug_l = [service.acct_label(a_['name'], a_['acct']) for a_ in sug]
            mode = st.radio("Cách tính", ["Biết số tiền nộp, tính mua tối đa", "Cần nhận N cổ phiếu, tính chia vol và tiền nộp"],
                            horizontal=True, key="mb_mode")
            st.caption("Gợi ý sẵn: tk sức mua dương (EE DT > 0) và hạn mức mã còn lại lớn nhất; bạn có thể đổi.")
            if mode.startswith("Biết"):
                chosen = st.multiselect("Tài khoản", labels, default=sug_l[:1], key="mb_acc_a")
                lines = []
                if chosen:
                    cols = st.columns(min(len(chosen), 4))
                    for i_, nm in enumerate(chosen):
                        dep = cols[i_ % len(cols)].number_input(f"Nộp vào {nm} (tỷ)", value=10.0, step=1.0,
                                                                key=f"mb_dep_{nm}") * 1e9
                        a_ = accs[labels.index(nm)]
                        cap = multi.buy_capacity(a_, tk_, price_, im_, lim_, dep, s=s)
                        if cap["hm_out"]:
                            st.warning(f"{nm}: hạn mức {tk_} đã hết nên sức mua = 0.")
                        lines.append(dict(acc=a_, deposit=dep, qty=cap["qty"], value=cap["value"], debt_after=cap["debt_after"]))
                missing = 0
            else:
                nq = money_input("Số cổ phiếu cần nhận", 1_000_000, key="mb_nq")
                step = st.number_input("Làm tròn tiền nộp lên (tỷ)", value=0.5, min_value=0.1, step=0.1, key="mb_step") * 1e9
                chosen = st.multiselect("Tài khoản (xếp theo hạn mức còn lại)", labels, default=sug_l, key="mb_acc_b")
                al = multi.alloc_buy([accs[labels.index(nm)] for nm in chosen], tk_, price_, im_, lim_, nq, step, s=s)
                lines, missing = al["lines"], al["missing"]
            if lines:
                st.dataframe(pd.DataFrame([{
                    "Tài khoản": service.acct_label(l_['acc']['name'], l_['acc']['acct']), "Nộp": fmt_vnd(l_["deposit"]),
                    "SLCP mua tối đa": fmt_vnd(l_["qty"]), "Giá trị mua": fmt_vnd(l_["value"]),
                    "Dư nợ sau mua": fmt_vnd(l_["debt_after"])} for l_ in lines] + [{
                    "Tài khoản": "TỔNG", "Nộp": fmt_vnd(sum(l_["deposit"] for l_ in lines)),
                    "SLCP mua tối đa": fmt_vnd(sum(l_["qty"] for l_ in lines)),
                    "Giá trị mua": fmt_vnd(sum(l_["value"] for l_ in lines)),
                    "Dư nợ sau mua": fmt_vnd(sum(l_["debt_after"] for l_ in lines))}]),
                    hide_index=True, width="stretch")
                st.markdown("**Cú pháp trả lời mẫu** (bấm biểu tượng sao chép góc phải ô):")
                st.code(multi.text_buy(lines, tk_, price_), language=None)
            if missing > 0:
                st.error(f"Chưa đủ: còn thiếu {fmt_vnd(missing)} cổ phiếu. Thêm tk hoặc kiểm tra hạn mức mã.")
            st.caption("Sức mua theo EE DT; hạn mức mã còn lại ≤ 0 thì sức mua = 0. Vay ~ = dư nợ sau mua. "
                       "Tiền nộp làm tròn lên theo bước đã chọn.")
            if lines:
                ops_, desc_ = [], []
                for l_ in lines:
                    if l_["qty"] > 0:
                        ops_.append(dict(name=l_["acc"]["name"], ticker=tk_, dqty=l_["qty"],
                                         dcash=l_["deposit"] - l_["qty"] * price_, im=im_, lim=lim_, price=price_))
                        desc_.append(f"{service.acct_label(l_['acc']['name'], l_['acc']['acct'])}: nộp {fmt_vnd(l_['deposit'])}, "
                                     f"mua {fmt_vnd(l_['qty'])} {tk_} giá {fmt_vnd(price_)}")
                _apply_box("buy", ops_, desc_)

        # ---- 3. Rút tiền
        elif tool.startswith("Rút tiền"):
            mode = st.radio("Cách tính", ["Biết số tiền muốn rút, tính bán mã nào / bao nhiêu",
                                          "Biết số lượng bán, tính tiền rút được"], horizontal=True, key="mw_mode")
            fee_ = st.number_input("Phí + thuế bán (%)", value=0.0, min_value=0.0, step=0.05, key="mw_fee")
            if mode.startswith("Biết số tiền"):
                sel_t = st.multiselect("Mã được phép bán", held_t, default=held_t, key="mw_t")
                prs = {}
                if sel_t:
                    pc = st.columns(min(len(sel_t), 4))
                    for i_, tk in enumerate(sel_t):
                        prs[tk] = float(money_input(f"Giá bán {tk}", int(px_all.get(tk, 0)) or 1000, key=f"mw_px_{tk}",
                                                    container=pc[i_ % len(pc)]))
                chosen = st.multiselect("Tài khoản", labels, default=labels, key="mw_acc")
                amt_ = st.number_input("Tổng tiền cần rút (tỷ)", value=20.0, step=1.0, key="mw_amt") * 1e9
                c1_, c2_ = st.columns(2)
                one = c1_.checkbox("Không chia nhiều tài khoản (xong hẳn 1 tk mới sang tk khác)", value=False, key="mw_one")
                free = c2_.checkbox("Tính cả EE DT dương sẵn có (rút không cần bán)", value=False, key="mw_free")
                sub = [accs[labels.index(nm)] for nm in chosen]
                if sel_t and sub:
                    r_ = multi.alloc_withdraw(sub, sel_t, prs, amt_, fee_, use_free_ee=free, one_account=one, s=s)
                    if r_["missing"] > 0:
                        st.error(f"Bán hết các mã đã chọn vẫn thiếu {fmt_vnd(r_['missing'])} VND.")
                    sug = {(l_["acc"]["acct"] + l_["acc"]["name"], tk): q
                           for l_ in r_["lines"] for tk, q, _ in l_.get("sales", [])}
                    drows, tcols = [], []
                    for a_ in sub:
                        held_ = {p_.ticker: p_ for p_ in a_["positions"]
                                 if p_.ticker in sel_t and p_.qty > 0 and prs.get(p_.ticker, 0) > 0}
                        if not held_:
                            continue
                        row = {"Tài khoản": service.acct_label(a_['name'], a_['acct']),
                               "Đang giữ": " · ".join(f"{tk} {p_.qty:,.0f}" for tk, p_ in held_.items())}
                        for tk in held_:
                            if tk not in tcols:
                                tcols.append(tk)
                        for tk in sel_t:
                            row[tk] = float(sug.get((a_["acct"] + a_["name"], tk), 0)) if tk in held_ else None
                        drows.append(row)
                    tcols = [tk for tk in sorted(tcols, key=lambda x: min(
                        (p_.im_pct for a_ in sub for p_ in a_["positions"] if p_.ticker == x), default=999))]
                    if drows:
                        st.markdown("**Điều chỉnh SLCP muốn bán** (gợi ý tự động, bạn sửa số trong các cột mã để cân đối lại; "
                                    "ô trống là tk không giữ mã đó, cột xếp theo IM thấp trước):")
                        sig = hashlib.md5(repr((chosen, sel_t, sorted(prs.items()), amt_, fee_, one, free)).encode()).hexdigest()[:10]
                        dfe = pd.DataFrame(drows)[["Tài khoản", "Đang giữ"] + tcols]
                        ed3 = st.data_editor(
                            dfe, hide_index=True, width="stretch", disabled=["Tài khoản", "Đang giữ"],
                            column_config={tk: st.column_config.NumberColumn(f"Bán {tk}", min_value=0, step=100,
                                                                              format="%d") for tk in tcols},
                            key=f"mw_adj_{sig}")
                        held_map = {service.acct_label(a_['name'], a_['acct']): {p_.ticker: p_.qty for p_ in a_["positions"]}
                                    for a_ in sub}
                        by_acc = {}
                        for _, rw in ed3.iterrows():
                            for tk in tcols:
                                v = rw[tk]
                                if v is None or pd.isna(v):
                                    continue
                                q = min(max(float(v), 0.0), float(held_map[rw["Tài khoản"]].get(tk, 0)))
                                if q > 0:
                                    by_acc.setdefault(rw["Tài khoản"], []).append((tk, q, prs[tk]))
                        left_w, lines3, trows, tq, tv = amt_, [], [], 0.0, 0.0
                        for a_ in sub:
                            lb = service.acct_label(a_['name'], a_['acct'])
                            sales = by_acc.get(lb, [])
                            if not sales:
                                continue
                            af0 = _after(a_, sales, 0.0, fee_)
                            w_ = max(0.0, af0["ee_dt"])          # số rút thực tế = EE DT sau bán
                            left_w -= w_
                            af = _after(a_, sales, w_, fee_)
                            lines3.append(dict(acc=a_, sales=sales, withdraw=w_))
                            val = sum(q * px for _, q, px in sales)
                            tq += sum(q for _, q, _ in sales)
                            tv += val
                            trows.append({"Tài khoản": lb, "Giá trị bán": fmt_vnd(val), "Rút": fmt_vnd(w_),
                                          "MR sau": fmt_pct(af["mr"])})
                        if trows:
                            trows.append({"Tài khoản": "TỔNG", "Giá trị bán": fmt_vnd(tv), "Rút": fmt_vnd(amt_ - left_w),
                                          "MR sau": ""})
                            st.dataframe(pd.DataFrame(trows), hide_index=True, width="stretch")
                            got_ = amt_ - left_w
                            if got_ + 0.5 < amt_:
                                st.warning(f"Với khối lượng bán này mới rút được **{fmt_vnd(got_)}**, "
                                           f"còn thiếu {fmt_vnd(amt_ - got_)} so với yêu cầu {fmt_vnd(amt_)}.")
                            else:
                                st.success(f"Rút được thực tế **{fmt_vnd(got_)}** VND "
                                           f"(yêu cầu {fmt_vnd(amt_)}, dư {fmt_vnd(got_ - amt_)}).")
                            st.markdown("**Cú pháp trả lời mẫu**:")
                            st.code(multi.text_withdraw(lines3), language=None)
                            ops_, desc_ = [], []
                            for l_ in lines3:
                                for tk, q, px in l_["sales"]:
                                    ops_.append(dict(name=l_["acc"]["name"], ticker=tk, dqty=-q, dcash=q * px * (1 - fee_ / 100)))
                                if l_["withdraw"] > 0:
                                    ops_.append(dict(name=l_["acc"]["name"], ticker=None, dqty=0, dcash=-l_["withdraw"]))
                                desc_.append(f"{service.acct_label(l_['acc']['name'], l_['acc']['acct'])}: bán "
                                             + ", ".join(f"{fmt_vnd(q)} {tk}" for tk, q, _ in l_["sales"])
                                             + f", rút {fmt_vnd(l_['withdraw'])}")
                            _apply_box("wd1", ops_, desc_)
                        else:
                            st.info("Chưa bán mã nào (SL bán = 0).")
                st.caption("Quy tắc: bán mã có tỉ lệ ký quỹ (IM) THẤP trước, vì giá trị cao hơn, SLCP bán ít hơn mà rút được nhiều. "
                           "Đủ tiền thì dừng, chưa đủ thì bán hết mã đó rồi sang mã IM cao hơn. Tick 'Không chia nhiều tài khoản': "
                           "hoàn tất một tk (mã IM thấp rồi cao) trước khi sang tk khác. Rút theo EE DT "
                           "(IM DT = IM × tỷ lệ tài khoản), làm tròn lô 100.")
            else:
                tk = st.selectbox("Mã bán", held_t, key="mw_tk1") if held_t else None
                if tk:
                    sp = money_input("Giá bán KH đưa (VND)", int(px_all.get(tk, 0)) or 1000, key=f"mw_sp_{tk}")
                    has = [lb for a_, lb in zip(accs, labels) if any(p.ticker == tk and p.qty > 0 for p in a_["positions"])]
                    chosen = st.multiselect("Tài khoản", has, default=has[:1], key="mw_acc1")
                    base = pd.DataFrame([{"Tài khoản": nm, "SL đang giữ": next(p.qty for p in accs[labels.index(nm)]["positions"]
                                                                              if p.ticker == tk),
                                          "SL bán": next(p.qty for p in accs[labels.index(nm)]["positions"] if p.ticker == tk)}
                                         for nm in chosen])
                    if not base.empty:
                        ed1 = st.data_editor(base, hide_index=True, width="stretch", disabled=["Tài khoản", "SL đang giữ"],
                                             key=f"mw_ed_{tk}_{'|'.join(chosen)}")
                        lines, rows3 = [], []
                        for _, rw in ed1.iterrows():
                            a_ = accs[labels.index(rw["Tài khoản"])]
                            o = sell_and_withdraw(a_["cash"], a_["positions"], a_["mm"], tk, float(rw["SL bán"]), sp, fee_, s)
                            lines.append(dict(acc=a_, sales=[(tk, o["qty"], sp)], withdraw=o["withdraw"]))
                            rows3.append({"Tài khoản": rw["Tài khoản"], "SL bán": fmt_vnd(o["qty"]),
                                          "Tiền thu": fmt_vnd(o["proceeds"]), "Rút tối đa": fmt_vnd(o["withdraw"]),
                                          "EE DT sau bán": fmt_vnd(o["after"]["ee_dt"]), "MR sau bán": fmt_pct(o["after"]["mr"])})
                        rows3.append({"Tài khoản": "TỔNG", "SL bán": fmt_vnd(sum(l_["sales"][0][1] for l_ in lines)),
                                      "Tiền thu": fmt_vnd(sum(l_["sales"][0][1] * sp * (1 - fee_ / 100) for l_ in lines)),
                                      "Rút tối đa": fmt_vnd(sum(l_["withdraw"] for l_ in lines)),
                                      "EE DT sau bán": "", "MR sau bán": ""})
                        st.dataframe(pd.DataFrame(rows3), hide_index=True, width="stretch")
                        st.markdown("**Cú pháp trả lời mẫu**:")
                        st.code(multi.text_withdraw(lines), language=None)
                        ops_, desc_ = [], []
                        for l_ in lines:
                            tk_s, q_s, px_s = l_["sales"][0]
                            if q_s > 0:
                                ops_.append(dict(name=l_["acc"]["name"], ticker=tk_s, dqty=-q_s, dcash=q_s * px_s * (1 - fee_ / 100)))
                                if l_["withdraw"] > 0:
                                    ops_.append(dict(name=l_["acc"]["name"], ticker=None, dqty=0, dcash=-l_["withdraw"]))
                                desc_.append(f"{service.acct_label(l_['acc']['name'], l_['acc']['acct'])}: bán {fmt_vnd(q_s)} {tk_s}, "
                                             f"rút {fmt_vnd(l_['withdraw'])}")
                        _apply_box("wd2", ops_, desc_)

        # ---- 5. Soạn tin sức mua gửi KH
        elif tool.startswith("Soạn tin"):
            with st.container(key="sec_buy"):
                st.markdown("##### 🟢 SỨC MUA")
                chosen = st.multiselect("Tài khoản", labels, default=labels[:1], key="t5_acc")
                dflt = [t for t in ["EIB", "HAH", "VSC", "VIX", "GEX"] if t in ll_all]
                tks = st.multiselect("Mã cần báo sức mua", sorted(ll_all), default=dflt, key="t5_tk")
                rnd = st.radio("Làm tròn sức mua xuống", ["10 triệu", "100 triệu", "1 triệu"], horizontal=True, key="t5_rnd")
            step_ = {"10": 10_000_000, "100": 100_000_000}.get(rnd.split()[0], 1_000_000)
            blocks, warns = [], []
            for nm in chosen:
                a_ = accs[labels.index(nm)]
                acct6 = (a_.get("acct") or "")[-6:]
                head = f"{a_['name']} {acct6}".strip()
                debt_ = max(0.0, -a_["cash"])
                lines_ = [head, f"Dư nợ: {msgfmt.fmt_debt(debt_)}", ""]
                for tk in tks:
                    inf = ll_all.get(tk)
                    px_ = float(px_all.get(tk, 0))
                    if not inf or px_ <= 0:
                        warns.append(f"{tk}: chưa có giá (nhập ở tab Giá cổ phiếu) hoặc chưa có trong danh mục cho vay nên bị bỏ qua.")
                        continue
                    c5 = multi.buy_capacity(a_, tk, px_, float(inf["im_pct"]), float(inf["limit_vnd"]), 0.0, 100, s)
                    pct = msgfmt.loan_pct(c5["k"] * 100)
                    if c5["hm_out"]:
                        lines_.append(f"* Sức mua {tk} ({pct}%) hết hạn mức")
                    else:
                        lines_.append(f"* Sức mua {tk} ({pct}%) {msgfmt.fmt_floor(c5['bp'], step_)} - "
                                      f"Hạn mức còn lại {msgfmt.fmt_limit(c5['remaining'])}")
                blocks.append("\n".join(lines_).rstrip())
            for w_ in sorted(set(warns)):
                st.warning(w_)
            if blocks:
                st.markdown("**Nội dung gửi KH** (bấm biểu tượng sao chép ở góc phải khung):")
                st.code("\n\n".join(blocks), language=None)
                st.caption("Sức mua tính theo EE DT của tài khoản và hạn mức còn lại của mã (số DT). "
                           "Số trong ngoặc là tỉ lệ vay = 100% − IM DT, làm tròn xuống. "
                           "Hạn mức làm tròn xuống hàng tỷ. Từ 1 tỷ ghi tỷ, dưới 1 tỷ ghi triệu.")

        # ---- 6. Cú pháp chuyển tiền nộp (độc lập)
        elif tool.startswith("Cú pháp chuyển tiền"):
            bank_ = st.text_input("Ngân hàng nhận", value=db.get_text("dep_bank", depmsg.DEFAULT_BANK), key="dm_bank")
            if bank_ != db.get_text("dep_bank", depmsg.DEFAULT_BANK):
                db.set_text("dep_bank", bank_)
            call_by = {service.acct_label(r_["name"], r_["account_no"]): r_["call_amount"] for r_ in res}
            chosen = st.multiselect("Tài khoản", labels, default=[], key="dm_acc")
            dir_ = db.directory()
            st.caption("Số tiền tự nhập (mặc định gợi ý bằng tiền cần nộp nếu tài khoản đang call, không thì 0). "
                       "Tên người thụ hưởng lấy từ danh bạ KH, bỏ dấu, sửa được.")
            for nm in chosen:
                a_ = accs[labels.index(nm)]
                amt_ = int(round(call_by.get(nm, 0) or 0))
                cc1, cc2 = st.columns([1, 2])
                nm_in = cc1.text_input(f"Người thụ hưởng - {nm}", value=depmsg.holder(a_["name"], a_["acct"], dir_),
                                       key=f"dm_nm_{nm}")
                v_ = money_input(f"Số tiền - {nm} (VND)", amt_, key=f"dm_amt_{nm}_{amt_}", container=cc1)
                acct_no = (dir_.get((a_["acct"] or "")[-6:]) or {}).get("account_no") or a_["acct"]
                if not depmsg.stk(acct_no):
                    cc2.warning(f"{nm} chưa có số tài khoản, hãy cập nhật số tài khoản trong file Excel/danh bạ KH.")
                cc2.code(depmsg.text(acct_no, nm_in, bank_, v_), language=None)

        # ---- 4. Bán 1 mã, nhận về mã khác
        elif tool.startswith("Bán 1 mã"):
            if not held_t:
                st.info("Chưa có KH nào giữ mã.")
            else:
                with st.container(key="sec_sell"):
                    st.markdown("##### 🔴 BÁN")
                    c1, c2 = st.columns(2)
                    st_ = c1.selectbox("Mã bán", held_t, key="md_sell")
                    sp_ = money_input("Giá bán (VND)", int(px_all.get(st_, 0)) or 1000, key=f"md_sp_{st_}", container=c2)
                    has = [lb for a_, lb in zip(accs, labels) if any(p.ticker == st_ and p.qty > 0 for p in a_["positions"])]
                    sel_a = st.multiselect("Tài khoản", has, default=has[:1], key="md_acc")
                with st.container(key="sec_buy"):
                    st.markdown("##### 🟢 MUA")
                    want_buy = st.checkbox("Nhận về mã khác (tính mua được / cần nộp thêm)", value=True, key="md_wb")
                    btk, bpx, bim, blim = (None, 0.0, 100.0, 0.0)
                    if want_buy:
                        btk, bpx, bim, blim = _buy_inputs("md")
                held_of = {nm: next(p.qty for p in accs[labels.index(nm)]["positions"] if p.ticker == st_) for nm in sel_a}
                if sel_a:
                    st.markdown(f"**Điều chỉnh SLCP muốn bán {st_}**" + (f" và SLCP muốn nhận {btk}" if btk else "")
                                + " (mặc định bán hết; để SL nhận = 0 nếu chỉ muốn xem mua tối đa):")
                    base4 = pd.DataFrame([{"Tài khoản": nm, f"Đang giữ {st_}": held_of[nm], f"Bán {st_}": held_of[nm],
                                           **({f"Muốn nhận {btk}": 0} if btk else {})} for nm in sel_a])
                    ed4 = st.data_editor(
                        base4, hide_index=True, width="stretch", disabled=["Tài khoản", f"Đang giữ {st_}"],
                        column_config={c_: st.column_config.NumberColumn(min_value=0, step=100, format="%d")
                                       for c_ in base4.columns[2:]},
                        key=f"md_ed_{st_}_{btk}_{'|'.join(sel_a)}")
                    sq = {r_["Tài khoản"]: float(r_[f"Bán {st_}"]) for _, r_ in ed4.iterrows()}
                    wq = {r_["Tài khoản"]: float(r_[f"Muốn nhận {btk}"]) for _, r_ in ed4.iterrows()} if btk else {}
                    sub = [accs[labels.index(nm)] for nm in sel_a]
                    rows_ = multi.sell_buy_table(sub, st_, float(sp_), sq, btk, bpx, bim, blim, wq, 0.0, s=s)
                    if rows_:
                        d4 = []
                        for r_ in rows_:
                            row = {"Tài khoản": r_["label"], "SL bán": fmt_vnd(r_["qty"]), "Tiền thu": fmt_vnd(r_["proceeds"]),
                                   "Rút được": fmt_vnd(r_["withdraw"])}
                            if btk:
                                row[f"Mua tối đa {btk}"] = fmt_vnd(r_["buy"]["qty"])
                                if r_["want"]:
                                    dep = r_["want"]["deposit"]
                                    row[f"Cần nộp thêm (nhận {fmt_vnd(r_['want']['qty'])})"] = (
                                        "Hết hạn mức" if dep is None else fmt_vnd(dep))
                            d4.append(row)
                        tot4 = {"Tài khoản": "TỔNG", "SL bán": fmt_vnd(sum(r_["qty"] for r_ in rows_)),
                                "Tiền thu": fmt_vnd(sum(r_["proceeds"] for r_ in rows_)),
                                "Rút được": fmt_vnd(sum(r_["withdraw"] for r_ in rows_))}
                        if btk:
                            tot4[f"Mua tối đa {btk}"] = fmt_vnd(sum(r_["buy"]["qty"] for r_ in rows_))
                            wk = [k for k in d4[0] if k.startswith("Cần nộp thêm")]
                            if wk:
                                tot4[wk[0]] = fmt_vnd(sum(r_["want"]["deposit"] for r_ in rows_
                                                          if r_["want"] and r_["want"]["deposit"] is not None))
                        st.dataframe(pd.DataFrame(d4 + [tot4]).fillna(""), hide_index=True, width="stretch")
                        st.markdown("**Cú pháp trả lời mẫu**:")
                        st.code(multi.text_sell_all(rows_, st_, float(sp_), btk, bpx), language=None)
                        st.caption("Rút được = EE DT sau khi bán. Mua tối đa = sức mua mã nhận sau khi bán, chưa nộp thêm. "
                                   "Cần nộp thêm = tiền nộp tối thiểu để nhận đủ SLCP mong muốn (0 nếu đã đủ).")
                        ops_, desc_ = [], []
                        for r_ in rows_:
                            nm_ = r_["acc"]["name"]
                            if r_["qty"] > 0:
                                ops_.append(dict(name=nm_, ticker=st_, dqty=-r_["qty"], dcash=r_["proceeds"]))
                                desc_.append(f"{r_['label']}: bán {fmt_vnd(r_['qty'])} {st_} thu {fmt_vnd(r_['proceeds'])}")
                            w_ = r_.get("want")
                            if btk and w_ and w_["qty"] > 0 and w_["deposit"] is not None:
                                ops_.append(dict(name=nm_, ticker=btk, dqty=w_["qty"],
                                                 dcash=w_["deposit"] - w_["qty"] * bpx, im=bim, lim=blim, price=bpx))
                                desc_.append(f"{r_['label']}: nộp {fmt_vnd(w_['deposit'])}, nhận {fmt_vnd(w_['qty'])} {btk} giá {fmt_vnd(bpx)}")
                        _apply_box("swap", ops_, desc_)

# ---------------------------------------------------------------- Giá
with tab_prices:
    st.caption("Một giá cho mỗi mã, áp dụng cho mọi KH, nên không còn lệch giá giữa các sheet. "
               "Sửa giá rồi bấm Lưu để tính lại toàn bộ.")
    px = service.prices()
    if not px:
        st.info("Chưa có mã nào.")
    else:
        df = pd.DataFrame(sorted(px.items()), columns=["Mã", "Giá (VND)"])
        ed = st.data_editor(df, hide_index=True, width="stretch", disabled=["Mã"], key="px_ed")
        if st.button("Lưu giá", type="primary"):
            with db.conn() as c:
                for _, row in ed.iterrows():
                    c.execute("UPDATE prices SET price=?, updated_at=? WHERE ticker=?",
                              (float(row["Giá (VND)"]), db.now(), row["Mã"]))
            st.success("Đã cập nhật giá.")
            st.rerun()

# ---------------------------------------------------------------- Danh mục cho vay
with tab_loan:
    ll = db.get_loan_list()
    ratio = s.default_mm
    st.markdown("Danh mục cho vay là nguồn **tỉ lệ ký quỹ** và **hạn mức theo mã**. "
                "Tỉ lệ ký quỹ tài khoản VIP/duy trì = tỉ lệ công bố × tỷ lệ tài khoản.")

    up_l = st.file_uploader("File danh mục cho vay (sheet '0')", type=["xlsx"], key="loan_up")
    if up_l is not None:
        raw = up_l.getvalue()
        sheets = list_candidate_sheets(io.BytesIO(raw))
        sheet = st.selectbox("Sheet", sheets, index=sheets.index("0") if "0" in sheets else 0)
        parsed = parse_loan_list(io.BytesIO(raw), sheet)
        n_prop = sum(1 for v in parsed["items"].values() if v["im_proposed_pct"])
        st.write(f"Sheet **{parsed['sheet']}**: **{len(parsed['items'])}** mã, "
                 f"tỷ lệ tài khoản **{parsed['account_ratio']:.2f}**, **{n_prop}** mã có IM đề xuất.")
        for w in parsed["warnings"]:
            st.warning(w)
        set_ratio = st.checkbox(f"Đặt tỷ lệ tài khoản mặc định = {parsed['account_ratio']:.2f}", value=True)
        if st.button("Xác nhận nạp danh mục cho vay", type="primary"):
            db.import_loan_list(parsed["items"], parsed["account_ratio"] if set_ratio else None)
            st.success("Đã nạp danh mục cho vay.")
            st.rerun()

    if not ll:
        st.info("Chưa có danh mục cho vay. Chọn file ở trên để nạp.")
    else:
        q = st.text_input("Tìm mã").upper().strip()
        def _vip(im):
            return min(im * ratio if im < 100 else 100, 100)

        df = pd.DataFrame([{
            "Mã": t, "IM thường %": v["im_pct"], "IM VIP/duy trì %": _vip(v["im_pct"]),
            "Tỉ lệ vay %": math.floor(100 - _vip(v["im_pct"]) + 1e-9),
            "Hạn mức (tỷ)": v["limit_vnd"] / 1e9,
        } for t, v in sorted(ll.items()) if q in t])
        for col in ["IM thường %", "IM VIP/duy trì %", "Hạn mức (tỷ)"]:
            df[col] = df[col].map(lambda x: "" if pd.isna(x) else f"{x:.1f}")
        df["Tỉ lệ vay %"] = df["Tỉ lệ vay %"].map(lambda x: f"{x:.0f}")
        st.dataframe(df, hide_index=True, width="stretch")
        st.caption(f"Tỉ lệ vay = 100% − IM VIP/duy trì (IM thường × tỷ lệ tài khoản {ratio:.2f}), làm tròn xuống. "
                   "Ví dụ IM thường 70% thì IM VIP 38,5% và tỉ lệ vay 61%.")
        st.caption("Mã không có trong danh mục hoặc tỉ lệ công bố = 0 được xử lý như ký quỹ 100%, hạn mức 0 "
                   "(giống cách file KH của bạn đang làm).")

        st.subheader("Mẫu trả lời KH về mã cho vay")
        px_ref = service.prices()
        pick_t = st.multiselect("Chọn mã", sorted(ll), default=[q] if q in ll else [], key="lt_pick")
        if pick_t:
            base_t = pd.DataFrame([{"Mã": tk, "Giá tham chiếu": float(px_ref.get(tk, 0)),
                                    "Hạn mức tối đa/tk (tỷ, để 0 nếu chỉ 1 mức)": 0.0} for tk in pick_t])
            ed_t = st.data_editor(base_t, hide_index=True, width="stretch", disabled=["Mã"],
                                  column_config={"Giá tham chiếu": st.column_config.NumberColumn(min_value=0, step=100, format="%d")},
                                  key=f"lt_ed_{'|'.join(pick_t)}")
            texts = []
            for _, r_ in ed_t.iterrows():
                v_ = ll[r_["Mã"]]
                vay_ = math.floor(100 - _vip(v_["im_pct"]) + 1e-9)
                hi_ = float(r_.iloc[2]) * 1e9
                texts.append(multi.text_loan(r_["Mã"], v_["limit_vnd"], hi_ if hi_ > 0 else None, vay_, float(r_["Giá tham chiếu"])))
            st.markdown("**Cú pháp trả lời mẫu** (bấm biểu tượng sao chép góc phải ô):")
            st.code("\n\n".join(texts), language=None)
            st.caption("Giá vay = tỉ lệ vay × giá tham chiếu (giá ở tab Giá cổ phiếu), làm tròn xuống 100đ. "
                       "Hạn mức/tk: số đầu lấy từ danh mục cho vay, số sau nhập thêm nếu có.")

        st.subheader("Đồng bộ danh mục KH theo danh mục cho vay")
        diffs = db.sync_positions_with_list(apply=False)
        if not diffs:
            st.success("Tỉ lệ ký quỹ và hạn mức của mọi KH đã khớp danh mục cho vay.")
        else:
            st.write(f"Có **{len(diffs)}** dòng khác danh mục:")
            st.dataframe(pd.DataFrame([{
                "Tài khoản": service.label_map().get(d["customer"], d["customer"]), "Mã": d["ticker"],
                "IM hiện tại %": d["im_old"], "IM theo danh mục %": d["im_new"],
                "Hạn mức hiện tại (tỷ)": d["limit_old"] / 1e9, "Hạn mức theo danh mục (tỷ)": d["limit_new"] / 1e9,
            } for d in diffs]), hide_index=True, width="stretch")
            if st.button("Áp dụng đồng bộ", type="primary"):
                db.sync_positions_with_list(apply=True)
                st.success("Đã đồng bộ.")
                st.rerun()
        n_custom = sum(1 for c in service.load_customers() for p in c["positions"] if p.limit_custom)
        st.caption(f"{n_custom} dòng có **hạn mức riêng của KH** (khác danh mục) được giữ nguyên khi đồng bộ.")

        st.subheader("Tác động nếu áp IM đề xuất")
        if not any(v["im_proposed_pct"] for v in ll.values()):
            st.caption("Danh mục không có cột IM đề xuất.")
        else:
            cur, new = service.compute_all(), service.compute_all(proposed=True)
            rows = []
            for a, b in zip(cur, new):
                if abs((a["imr"] or 0) - (b["imr"] or 0)) < 1:
                    continue
                rows.append({
                    "Tài khoản": service.acct_label(a["name"], a.get("account_no")), "MR hiện tại": fmt_pct(a["mr"]), "MR đề xuất": fmt_pct(b["mr"]),
                    "Tình trạng hiện tại": STATUS_ICON[a["status"]] + " " + STATUS_LABEL[a["status"]],
                    "Tình trạng đề xuất": STATUS_ICON[b["status"]] + " " + STATUS_LABEL[b["status"]],
                    "Tiền cần nộp thêm": fmt_vnd(max(0, b["call_amount"] - a["call_amount"])) if b["call_amount"] else "-",
                    "_mr": b["mr"] if b["mr"] is not None else 9,
                })
            if rows:
                out = pd.DataFrame(sorted(rows, key=lambda x: x["_mr"])).drop(columns="_mr")
                out.insert(0, "STT", range(1, len(out) + 1))
                st.dataframe(out, hide_index=True, width="stretch")
            else:
                st.caption("Không KH nào đang giữ mã có IM đề xuất.")

# ---------------------------------------------------------------- Import
with tab_import:
    sourcepanel.render()

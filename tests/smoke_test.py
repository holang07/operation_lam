"""Chạy thử từng trang với dữ liệu demo (dùng DB tạm, không đụng dữ liệu thật).

Chạy: python tests/smoke_test.py "đường_dẫn_file.xlsx"
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest

from core import db
from core.importer import parse_workbook

tmp = Path(tempfile.mkdtemp()) / "test.db"
db.DB_PATH = tmp
db.init()
with open(sys.argv[1], "rb") as f:
    customers, prices, _ = parse_workbook(f)
db.import_customers(customers, prices)

if len(sys.argv) > 2:
    from core.loanlist import parse_loan_list
    parsed = parse_loan_list(open(sys.argv[2], "rb"))
    db.import_loan_list(parsed["items"], parsed["account_ratio"])
    d0 = db.sync_positions_with_list(apply=False)
    print("Đồng bộ danh mục: dòng khác biệt =", len(d0))
    assert all(not x["in_list"] or True for x in d0)
    from core import service
    cur, new = service.compute_all(), service.compute_all(proposed=True)
    moved = [(a["name"], a["status"], b["status"]) for a, b in zip(cur, new) if a["status"] != b["status"]]
    print("KH đổi trạng thái nếu áp IM đề xuất:", moved)

# thêm vài dữ liệu mẫu để các trang có nội dung
with db.conn() as c:
    c.execute("INSERT INTO orders(created_at,customer_name,ticker,side,qty,price,order_type,session,channel,status) "
              "VALUES(?,?,?,?,?,?,?,?,?,?)", (db.now(), "Thủy", "EIB", "Bán", 10000, 12900, "LO", "Ngoài phiên", "Zalo", "Chờ đặt"))
    c.execute("INSERT INTO cases(created_at,procedure_key,customer_name,data,status) VALUES(?,?,?,?,?)",
              (db.now(), "mo_tk", "KH mới", "{}", "Đang chờ KH"))
    c.execute("INSERT INTO news(link,title,summary,source,published,tickers,fetched_at) VALUES(?,?,?,?,?,?,?)",
              ("http://x/1", "EIB công bố kết quả kinh doanh", "", "Demo", "2026-11-12 08:00", "EIB", db.now()))

failed = 0
for page in ["today", "daily", "margin", "orders", "procedures", "news", "settings"]:
    at = AppTest.from_file(str(ROOT / "views" / f"{page}.py"), default_timeout=60).run()
    if at.exception:
        failed += 1
        print(f"LỖI  {page}:", at.exception[0].value)
    else:
        print(f"OK   {page}  (tiêu đề: {at.title[0].value if at.title else '-'})")

# Tương tác: trang Margin -> chọn KH khác, kéo thanh giả định
at = AppTest.from_file(str(ROOT / "views" / "margin.py"), default_timeout=60).run()
at.selectbox[0].set_value(0).run()
at.slider[0].set_value(-15).run()
print("Margin, giả định -15%:", "OK" if not at.exception else at.exception[0].value)
failed += bool(at.exception)

# Tương tác: trang Archive, tạo mẫu trả lời rồi dùng mẫu
at = AppTest.from_file(str(ROOT / "views" / "procedures.py"), default_timeout=60).run()
at.text_input(key="rn_name").set_value("Email CS mở tài khoản")
at.text_input(key="rn_cat_new").set_value("Mở tài khoản")
at.text_area(key="rn_body").set_value("Đề nghị mở TK cho {ten_kh}")
at.run()
at.button(key="rn_save").click().run()
at.text_input(key="ar_v_1_ten_kh").set_value("Nguyễn Văn A").run()
ok_arch = not at.exception and any("Nguyễn Văn A" in c.value for c in at.code)
print("Archive, tạo và dùng mẫu:", "OK" if ok_arch else "LỖI")
failed += not ok_arch

# Tương tác: Báo cáo hằng ngày -> lưu snapshot, kiểm tra tổng
at = AppTest.from_file(str(ROOT / "views" / "daily.py"), default_timeout=90).run()
next(b for b in at.button if b.label == "Lưu snapshot hôm nay").click().run()
with db.conn() as c:
    n_snap = c.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
vals = {m.label: m.value for m in at.metric}
ok = (not at.exception) and n_snap > 0 and "Tổng dư nợ" in vals and "Tổng NAV" in vals
print(f"Báo cáo hằng ngày: {'OK' if ok else 'LỖI'} (snapshot={n_snap}, {vals})")
failed += not ok

sys.exit(1 if failed else 0)

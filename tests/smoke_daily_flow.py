"""Thử luồng tab Báo cáo hằng ngày: nạp file gốc -> nhập số -> xuất Excel. Chạy: python tests/smoke_daily_flow.py file.xlsx"""
import io, sys, tempfile, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest
from core import db, service, xlsxpatch
from core.importer import parse_workbook

d = Path(tempfile.mkdtemp()); db.DB_PATH = d / "t.db"; db.init()
raw = open(sys.argv[1], "rb").read()
(d / "daily_original.xlsx").write_bytes(raw)
cs, px, _ = parse_workbook(io.BytesIO(raw)); db.import_customers(cs, px)
at = AppTest.from_file(str(ROOT / "views" / "daily.py"), default_timeout=60)
at.run(); assert not at.exception, at.exception
print("tabs:", [t.label for t in at.tabs])
c0 = cs[0]; sh = c0["sheet"]
edits = {sh: {"B3": -123456789, f"D{c0['positions'][0]['row']}": 4200}}
out, failed = xlsxpatch.patch_workbook(raw, edits)
assert not failed
from openpyxl import load_workbook
wb = load_workbook(io.BytesIO(out)); assert wb[sh]["B3"].value == -123456789
assert any("media" in n for n in zipfile.ZipFile(io.BytesIO(out)).namelist())
print("OK: xuất Excel giữ ảnh, ghi đúng ô")

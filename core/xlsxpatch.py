"""Sửa trực tiếp vài ô trong file .xlsx gốc (không qua openpyxl) để giữ nguyên ảnh, định dạng, công thức."""
from __future__ import annotations

import io
import re
import zipfile
from xml.sax.saxutils import unescape

_NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def sheet_paths(z: zipfile.ZipFile) -> dict[str, str]:
    """Tên sheet -> đường dẫn xml trong file."""
    wb = z.read("xl/workbook.xml").decode("utf-8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    rid_target = {}
    for m in re.finditer(r"<Relationship\b([^>]*)/?>", rels):
        a = m.group(1)
        i, t = re.search(r'Id="([^"]+)"', a), re.search(r'Target="([^"]+)"', a)
        if i and t:
            tgt = t.group(1).lstrip("/")
            rid_target[i.group(1)] = tgt if tgt.startswith("xl/") else "xl/" + tgt
    out = {}
    for m in re.finditer(r"<sheet\b([^>]*)/?>", wb):
        a = m.group(1)
        n = re.search(r'name="([^"]*)"', a)
        r = re.search(r'r:id="([^"]+)"', a) or re.search(r'id="([^"]+)"', a)
        if n and r and r.group(1) in rid_target:
            out[unescape(n.group(1), {"&quot;": '"', "&apos;": "'"})] = rid_target[r.group(1)]
    return out


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else repr(float(v))


def _body(value) -> str:
    """Số -> <v>; chuỗi bắt đầu bằng '=' -> công thức <f> (Excel tự tính khi mở)."""
    if isinstance(value, str) and value.startswith("="):
        from xml.sax.saxutils import escape
        return f"<f>{escape(value[1:])}</f>"
    return f"<v>{_fmt(value)}</v>"


def _set_cell(xml: str, ref: str, value: float) -> tuple[str, bool]:
    """Thay ô ref bằng giá trị số, giữ nguyên style (s=). Trả về (xml mới, có thay được không)."""
    pat = re.compile(r'<c r="%s"((?:\s[^>]*?)?)(?:/>|>.*?</c>)' % re.escape(ref), re.S)
    m = pat.search(xml)
    if not m:
        return _insert_cell(xml, ref, value)
    attrs = re.sub(r'\s(?:t|cm|vm)="[^"]*"', "", m.group(1))
    return xml[:m.start()] + f'<c r="{ref}"{attrs}>{_body(value)}</c>' + xml[m.end():], True


def _col_idx(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n


def _insert_cell(xml: str, ref: str, value: float) -> tuple[str, bool]:
    return _insert_raw(xml, ref, f'<c r="{ref}">{_body(value)}</c>')


def _insert_raw(xml: str, ref: str, new: str) -> tuple[str, bool]:
    """Ô chưa có trong file: thêm vào đúng dòng, đúng thứ tự cột."""
    row = re.search(r"\d+", ref).group(0)
    m = re.search(r'(<row r="%s"[^>]*?)(/>|>(.*?)</row>)' % row, xml, re.S)
    if not m:
        return xml, False
    if m.group(2) == "/>":
        return xml[:m.start()] + m.group(1) + ">" + new + "</row>" + xml[m.end():], True
    body = m.group(3)
    pos = len(body)
    for cm in re.finditer(r'<c r="([A-Z]+)\d+"', body):
        if _col_idx(cm.group(1)) > _col_idx(ref):
            pos = cm.start()
            break
    body = body[:pos] + new + body[pos:]
    return xml[:m.start()] + m.group(1) + ">" + body + "</row>" + xml[m.end():], True


def _shift_rows(formula: str, src: int, dst: int) -> str:
    """Đổi tham chiếu tương đối dòng src -> dst (E2 -> E3); giữ nguyên tham chiếu tuyệt đối ($A$23)."""
    return re.sub(r"(?<![$A-Za-z'!])(\$?[A-Z]{1,2})%d(?!\d)" % src, lambda m: m.group(1) + str(dst), formula)


def _clone_row(xml: str, src: int, dst: int, vals: dict) -> tuple[str, bool]:
    from xml.sax.saxutils import escape
    m = re.search(r'<row r="%d"[^>]*>(.*?)</row>' % src, xml, re.S)
    if not m:
        return xml, False
    cells = re.findall(r'<c r="([A-Z]+)%d"([^>]*?)(?:/>|>(.*?)</c>)' % src, m.group(1), re.S)
    for col, attrs, inner in cells:
        if _col_idx(col) < 3:          # giữ cột A, B (nhãn Số dư tiền/NAV nằm ở dòng 3-4)
            continue
        ref = f"{col}{dst}"
        sm = re.search(r'\ss="(\d+)"', attrs)
        sattr = f' s="{sm.group(1)}"' if sm else ""
        if col in vals:
            v = vals[col]
            body = (f' t="inlineStr"><is><t>{escape(str(v))}</t></is></c>' if isinstance(v, str) and not v.startswith("=")
                    else f">{_body(v)}</c>")
            new = f'<c r="{ref}"{sattr}{body}'
        else:
            f = re.search(r"<f>(.*?)</f>", inner or "", re.S)
            new = f'<c r="{ref}"{sattr}><f>{_shift_rows(f.group(1), src, dst)}</f></c>' if f else f'<c r="{ref}"{sattr}/>'
        pat = re.compile(r'<c r="%s"(?:\s[^>]*?)?(?:/>|>.*?</c>)' % ref, re.S)
        if pat.search(xml):
            xml = pat.sub(lambda _m: new, xml, count=1)
        else:
            xml, ok = _insert_raw(xml, ref, new)
            if not ok:
                return xml, False
    return xml, True


def patch_workbook(original: bytes, edits: dict[str, dict[str, float]],
                   new_rows: dict[str, list] | None = None) -> tuple[bytes, list[str]]:
    """edits: {tên sheet: {ô: giá trị số}}. Trả về (bytes xlsx mới, danh sách ô không sửa được)."""
    zin = zipfile.ZipFile(io.BytesIO(original))
    paths = sheet_paths(zin)
    new_xml: dict[str, str] = {}
    failed: list[str] = []
    for sheet, cells in edits.items():
        path = paths.get(sheet)
        if not path:
            failed += [f"{sheet}!{c}" for c in cells]
            continue
        xml = new_xml.get(path) or zin.read(path).decode("utf-8")
        for ref, val in cells.items():
            xml, ok = _set_cell(xml, ref, val)
            if not ok:
                failed.append(f"{sheet}!{ref}")
        new_xml[path] = xml

    # thêm mã mới: nhân bản dòng mẫu (công thức, định dạng) sang dòng trống rồi điền mã/SL/giá/tỉ lệ/hạn mức
    for sheet, items in (new_rows or {}).items():
        path = paths.get(sheet)
        if not path:
            failed += [f"{sheet}: dòng {r}" for r, _, _ in items]
            continue
        xml = new_xml.get(path) or zin.read(path).decode("utf-8")
        for r, tpl, vals in items:
            xml, ok = _clone_row(xml, tpl, r, vals)
            if not ok:
                failed.append(f"{sheet}: dòng {r}")
        new_xml[path] = xml

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            name = item.filename
            if name == "xl/calcChain.xml":      # chuỗi tính toán cũ không còn khớp -> bỏ, Excel tự dựng lại
                continue
            data = zin.read(name)
            if name in new_xml:
                # bỏ giá trị tính sẵn cũ của công thức trong sheet đã sửa để mọi trình xem đều tính lại, không hiện số cũ
                x = re.sub(r"(<f(?:\s[^>]*)?>[^<]*</f>|<f(?:\s[^>]*)?/>)<v>[^<]*</v>", r"\1", new_xml[name])
                data = x.encode("utf-8")
            elif name == "xl/workbook.xml":
                t = data.decode("utf-8")
                if "<calcPr" in t:
                    t = re.sub(r"<calcPr\b([^>]*?)\s*/>", lambda m: "<calcPr" + re.sub(r'\sfullCalcOnLoad="[^"]*"', "", m.group(1)) + ' fullCalcOnLoad="1"/>', t)
                else:
                    t = t.replace("</workbook>", '<calcPr fullCalcOnLoad="1"/></workbook>')
                data = t.encode("utf-8")
            elif name == "[Content_Types].xml":
                data = re.sub(rb'<Override[^>]*calcChain[^>]*/>', b"", data)
            elif name == "xl/_rels/workbook.xml.rels":
                data = re.sub(rb'<Relationship[^>]*calcChain[^>]*/>', b"", data)
            zout.writestr(item, data)
    return out.getvalue(), failed

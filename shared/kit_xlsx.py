"""kit_xlsx: write a small .xlsx workbook with the standard library only (no openpyxl, no Excel needed).

  kit_xlsx.write(path, [Sheet("Matrix", header, rows, widths=[...], flag_col=6), ...], title="...")

Each sheet gets a bold, shaded header row that stays put when you scroll (a frozen pane), a filter on every
column, wrapped text, and the column widths given (in characters; otherwise worked out from the text). A row
whose flag_col cell isn't empty or "none" is shaded light red, so gaps stand out. Cells are text or numbers,
written inline (no shared-strings table); characters XML can't hold are dropped. The file opens in Excel,
Numbers, LibreOffice, and Google Sheets.
"""
import datetime as dt
import re
import zipfile
from xml.sax.saxutils import escape

BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
MAX_CELL = 32000                     # Excel's limit is 32,767 characters per cell


class Sheet:
    def __init__(self, name, header, rows, widths=None, flag_col=None):
        self.name = re.sub(r"[\[\]:*?/\\]", "-", name)[:31] or "Sheet"
        self.header = list(header)
        self.rows = [list(r) for r in rows]
        self.widths = widths
        self.flag_col = flag_col


def col_name(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(ref, v, style):
    if isinstance(v, bool):
        v = "yes" if v else "no"
    if isinstance(v, (int, float)):
        return f'<c r="{ref}" s="{style}"><v>{v}</v></c>'
    text = BAD_XML.sub("", "" if v is None else str(v))[:MAX_CELL]
    return (f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>')


def _widths(sheet):
    if sheet.widths:
        return sheet.widths
    out = []
    for i, h in enumerate(sheet.header):
        longest = max([len(str(h))] + [len(str(r[i])) if i < len(r) and r[i] is not None else 0 for r in sheet.rows])
        out.append(max(8, min(60, longest + 2)))
    return out


def _sheet_xml(sheet):
    n = len(sheet.header)
    last = col_name(max(n, 1) - 1)
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(_widths(sheet)))
    rows = ['<row r="1">' + "".join(_cell(f"{col_name(i)}1", h, 1) for i, h in enumerate(sheet.header)) + "</row>"]
    for r_i, row in enumerate(sheet.rows, start=2):
        row = row + [""] * (n - len(row))
        flagged = (sheet.flag_col is not None and str(row[sheet.flag_col] or "").strip().lower() not in ("", "none"))
        style = 3 if flagged else 2
        rows.append(f'<row r="{r_i}">' + "".join(_cell(f"{col_name(i)}{r_i}", v, style) for i, v in enumerate(row))
                    + "</row>")
    ref = f"A1:{last}{len(sheet.rows) + 1}"
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<dimension ref="{ref}"/>'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" '
            'state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/>'
            f'<cols>{cols}</cols><sheetData>{"".join(rows)}</sheetData>'
            + (f'<autoFilter ref="{ref}"/>' if sheet.rows else "")
            + '<pageMargins left="0.5" right="0.5" top="0.6" bottom="0.6" header="0.3" footer="0.3"/>'
            '<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/></worksheet>')


STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
          '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
          '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
          '<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
          '<fill><patternFill patternType="solid"><fgColor rgb="FFDCE6F0"/><bgColor indexed="64"/></patternFill></fill>'
          '<fill><patternFill patternType="solid"><fgColor rgb="FFFBE3E4"/><bgColor indexed="64"/></patternFill></fill>'
          '</fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
          '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
          '<cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
          '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">'
          '<alignment vertical="top" wrapText="1"/></xf>'
          '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
          '<alignment vertical="top" wrapText="1"/></xf>'
          '<xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1" applyAlignment="1">'
          '<alignment vertical="top" wrapText="1"/></xf></cellXfs>'
          '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')


def _filters(names, sheets):
    """The hidden names Excel keeps for each sheet's filter range."""
    items = "".join(
        f'<definedName name="_xlnm._FilterDatabase" localSheetId="{i}" hidden="1">'
        f"'{escape(n.replace(chr(39), chr(39) * 2))}'!$A$1:${col_name(len(s.header) - 1)}${len(s.rows) + 1}</definedName>"
        for i, (n, s) in enumerate(zip(names, sheets)) if s.rows)
    return f"<definedNames>{items}</definedNames>" if items else ""


def write(path, sheets, title="", author="Kit"):
    """Write SHEETS (a list of Sheet) to PATH, replacing it atomically."""
    import os
    import pathlib
    path = pathlib.Path(path)
    names, seen = [], set()
    for s in sheets:                                       # sheet names must be unique, case-insensitively
        base, n = s.name, 2
        while s.name.lower() in seen:
            s.name = f"{base[:28]} {n}"
            n += 1
        seen.add(s.name.lower())
        names.append(s.name)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
          + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                    for i in range(1, len(sheets) + 1))
          + '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
          '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
            '</Relationships>')
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
          + "".join(f'<sheet name="{escape(n, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>'
                    for i, n in enumerate(names, 1))
          + '</sheets>' + _filters(names, sheets) + '</workbook>')
    wbrels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                        f'relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1))
              + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
              'relationships/styles" Target="styles.xml"/></Relationships>')
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{escape(title)}</dc:title><dc:creator>{escape(author)}</dc:creator>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>')
    app = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
           '<Application>Kit</Application></Properties>')
    tmp = path.with_name(path.name + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", wbrels)
        z.writestr("xl/styles.xml", STYLES)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
        for i, s in enumerate(sheets, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(s))
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return path

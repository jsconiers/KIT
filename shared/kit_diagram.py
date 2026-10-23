"""kit_diagram: read draw.io and Visio diagram files, page by page. Python standard library only.

Shared by kit-diagram-diff and kit-diaglint.

  drawio_pages(path)  -> [(page name, mxGraphModel element or None)]   .drawio / .xml, compressed or not
  vsdx_pages(zip)     -> [(page name, page XML member, PageSheet element or None)]
  vsdx_page_root(zip, member) -> parsed page XML
  vsdx_masters(zip)   -> {master id: master name}
  clean(label)        -> plain text from an HTML label
  shape_kind(style)   -> the draw.io shape name in a style string
  parse_style(style)  -> draw.io style string as a dict (a bare first token is stored under "")
"""
import base64
import html
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

VNS = "{http://schemas.microsoft.com/office/visio/2012/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def clean(label):
    text = html.unescape(re.sub(r"<br\s*/?>", " ", label or "", flags=re.I))
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def shape_kind(style):
    style = style or ""
    first = style.split(";")[0]
    if "=" not in first and first:
        return first
    m = re.search(r"shape=([^;]+)", style)
    return m.group(1) if m else ("ellipse" if "ellipse" in style else "rectangle")


def parse_style(style):
    out = {}
    for part in (style or "").split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
        elif "" not in out:
            out[""] = part
        else:
            out[part] = "1"
    return out


# ---------------------------------------------------------------- draw.io
def drawio_page_model(diagram):
    model = diagram.find("mxGraphModel")
    if model is not None:
        return model
    text = (diagram.text or "").strip()
    if not text:
        return None
    raw = base64.b64decode(text)
    try:
        xml_text = urllib.parse.unquote(zlib.decompress(raw, -15).decode("utf-8"))
    except zlib.error:
        xml_text = urllib.parse.unquote(raw.decode("utf-8", "ignore"))
    return ET.fromstring(xml_text)


def drawio_pages(path):
    root = ET.parse(path).getroot()
    if root.tag == "mxGraphModel":
        return [("Page-1", root)]
    if root.tag != "mxfile":
        raise ValueError(f"not a draw.io file (root element <{root.tag}>)")
    out = []
    for i, d in enumerate(root.findall("diagram"), 1):
        out.append((d.get("name") or f"Page-{i}", drawio_page_model(d)))
    return out


# ---------------------------------------------------------------- Visio
def vsdx_pages(z):
    names = set(z.namelist())
    order = []
    if "visio/pages/pages.xml" in names:
        rels = {}
        if "visio/pages/_rels/pages.xml.rels" in names:
            for r in ET.fromstring(z.read("visio/pages/_rels/pages.xml.rels")):
                rels[r.get("Id")] = r.get("Target")
        for i, p in enumerate(ET.fromstring(z.read("visio/pages/pages.xml")).iter(VNS + "Page"), 1):
            rel = p.find(VNS + "Rel")
            target = rels.get(rel.get(RNS + "id")) if rel is not None else None
            order.append((p.get("NameU") or p.get("Name") or f"Page-{i}",
                          f"visio/pages/{target}" if target else f"visio/pages/page{i}.xml",
                          p.find(VNS + "PageSheet")))
    else:
        members = sorted((n for n in names if re.match(r"visio/pages/page\d+\.xml$", n)),
                         key=lambda n: int(re.findall(r"\d+", n)[-1]))
        order = [(f"Page-{i}", n, None) for i, n in enumerate(members, 1)]
    return [o for o in order if o[1] in names]


def vsdx_page_root(z, member):
    return ET.fromstring(z.read(member))


def vsdx_masters(z):
    names = set(z.namelist())
    out = {}
    if "visio/masters/masters.xml" in names:
        for m in ET.fromstring(z.read("visio/masters/masters.xml")).iter(VNS + "Master"):
            out[m.get("ID")] = m.get("NameU") or m.get("Name") or ""
    return out

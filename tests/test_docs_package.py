#!/usr/bin/env python3
"""Checks that the Word copies in docs/ are packages Word will open: every entry's CRC is right, each part
is named once in [Content_Types].xml (a duplicate Override makes Word refuse the file, as the 1.7.0 and
1.7.1 copies did), every part has a content type, every internal relationship points at a part that
exists, and every XML part parses. Standard library only.

  python3 tests/test_docs_package.py
"""
import collections
import pathlib
import posixpath
import re
import sys
import zipfile
import xml.dom.minidom as minidom

REPO = pathlib.Path(__file__).resolve().parent.parent
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


docs = sorted((REPO / "docs").glob("*.docx"))
ok(bool(docs), "docs/ has Word copies to check", list((REPO / "docs").iterdir()))
for path in docs:
    n = path.name
    with zipfile.ZipFile(path) as z:
        ok(z.testzip() is None, f"{n}: every entry's CRC is right", z.testzip())
        names = [i.filename for i in z.infolist()]
        ok(len(names) == len(set(names)), f"{n}: no entry appears twice",
           [x for x, c in collections.Counter(names).items() if c > 1])
        ct = z.read("[Content_Types].xml").decode("utf8")
        parts = [p.lower() for p in re.findall(r'<Override [^>]*PartName="([^"]+)"', ct)]
        ok(len(parts) == len(set(parts)), f"{n}: each part named once in [Content_Types].xml",
           sorted(p for p, c in collections.Counter(parts).items() if c > 1))
        defaults = {d.lower() for d in re.findall(r'<Default [^>]*Extension="([^"]+)"', ct)}
        untyped = [x for x in names if not x.endswith("/") and x != "[Content_Types].xml"
                   and "/" + x.lower() not in parts and x.rsplit(".", 1)[-1].lower() not in defaults]
        ok(not untyped, f"{n}: every part has a content type", untyped)
        missing = []
        for rels in (x for x in names if x.endswith(".rels")):
            base = posixpath.dirname(posixpath.dirname(rels))
            for tag in re.findall(r"<Relationship [^>]*>", z.read(rels).decode("utf8")):
                target = re.search(r'Target="([^"]+)"', tag).group(1)
                if 'TargetMode="External"' in tag or target.startswith(("http:", "https:", "mailto:")):
                    continue
                part = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(base, target))
                if part not in names:
                    missing.append(f"{rels} -> {target}")
        ok(not missing, f"{n}: every relationship points at a part that exists", missing)
        bad = []
        for x in (x for x in names if x.endswith((".xml", ".rels"))):
            try:
                minidom.parseString(z.read(x))
            except Exception as e:  # noqa: BLE001 - any parse failure is the finding
                bad.append(f"{x}: {e}")
        ok(not bad, f"{n}: every XML part parses", bad)

print(f"\ndocs package tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)

#!/usr/bin/env python3
"""test_kit_letter.py: kit-letter builds valid Word letters, and signs only with `sign`.

  python3 tests/test_kit_letter.py

Runs shared/bin/kit-letter in a temporary home with made-up signature images. Checks that build makes
a letter with room for a pen signature and no picture; that sign embeds the saved signature (and
--short the shorter one) at 2.2 inches wide; that every XML part is well formed and the text is
escaped; and that signing refuses a letter without a {{SIGNATURE}} line or with no saved signature.
With python-docx installed it also opens each file the way Word-compatible tools do. Runs on macOS,
Linux, and Windows; CI runs it on Linux and Windows.
"""
import os
import pathlib
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "shared" / "bin" / "kit-letter"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
fails = 0


def check(cond, name, detail=""):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f" -- {detail}"))
    fails += 0 if cond else 1


def png(width, height, shade):
    """A small, valid RGBA PNG: one flat colour."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes((shade, shade, shade, 255)) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


tmp = pathlib.Path(tempfile.mkdtemp())
home = tmp / "home"
sig_dir = home / "Claude" / "Agents" / "kit" / "letters" / "signature"
sig_dir.mkdir(parents=True)
full, short = png(400, 100, 20), png(300, 100, 40)
(sig_dir / "signature.png").write_bytes(full)
(sig_dir / "signature-short.png").write_bytes(short)
env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))

letter = tmp / "letter.md"
letter.write_text("Alex Rivera\n1 Example Street\nAnytown, ST 00000\n\nOctober 28, 2026\n\n"
                  "**Subject: A <test> & a check**\n\nDear Sir or Madam:\n\n"
                  "Please confirm by November 30, 2026.\n\nSincerely,\n{{SIGNATURE}}\nAlex Rivera\n",
                  encoding="utf-8")


def run(*args):
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, env=env)


def parts(path):
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        xml_ok = all(ET.fromstring(z.read(n)) is not None for n in z.namelist() if n.endswith((".xml", ".rels")))
        return bad is None and xml_ok, {n: z.read(n) for n in z.namelist()}


r = run("build", str(letter))
out = tmp / "letter.docx"
check(r.returncode == 0 and out.exists(), "build makes letter.docx", r.stderr.strip())
ok, files = parts(out)
check(ok, "letter.docx is a valid zip with well-formed XML")
check(not any(n.startswith("word/media/") for n in files), "build adds no picture")
body = ET.fromstring(files["word/document.xml"])
text = "".join(t.text or "" for t in body.iter(W + "t"))
check("A <test> & a check" in text, "special characters come through", text[:120])
check(any(b.tag == W + "b" for b in body.iter()), "bold text stays bold")
breaks = sum(1 for _ in body.iter(W + "br"))
check(breaks >= 3, "room for a pen signature (line breaks)", f"{breaks} breaks")

r = run("sign", str(letter))
signed = tmp / "letter-signed.docx"
check(r.returncode == 0 and signed.exists(), "sign makes letter-signed.docx", r.stderr.strip())
ok, files = parts(signed)
check(ok, "letter-signed.docx is a valid zip with well-formed XML")
check(files.get("word/media/signature.png") == full, "sign embeds the saved signature exactly")
ext = next(ET.fromstring(files["word/document.xml"]).iter(WP + "extent"))
cx, cy = int(ext.get("cx")), int(ext.get("cy"))
check(cx == int(2.2 * 914400) and abs(cy - cx * 100 // 400) <= 1, "the signature is 2.2 inches wide, in proportion", f"{cx} x {cy}")

r = run("sign", str(letter), "--short", "--out", str(tmp / "short.docx"))
ok, files = parts(tmp / "short.docx")
check(r.returncode == 0 and files.get("word/media/signature.png") == short, "sign --short uses signature-short.png")

bare = tmp / "bare.md"
bare.write_text("No signature line here.\n", encoding="utf-8")
r = run("sign", str(bare))
check(r.returncode == 1 and not (tmp / "bare-signed.docx").exists(), "sign refuses a letter without {{SIGNATURE}}")

(sig_dir / "signature.png").unlink()
r = run("sign", str(letter), "--out", str(tmp / "none.docx"))
check(r.returncode == 1 and not (tmp / "none.docx").exists(), "sign refuses when no signature is saved")

r = run(str(letter))
check(r.returncode == 2, "a bare file name isn't accepted: build or sign has to be said")

try:
    import docx
except ImportError:
    print("     (python-docx not installed: skipped opening the files with it)")
else:
    for name, pictures in (("letter.docx", 0), ("letter-signed.docx", 1), ("short.docx", 1)):
        d = docx.Document(str(tmp / name))
        check(len(d.inline_shapes) == pictures, f"python-docx opens {name} ({pictures} picture)")

print(f"\n{'all passed' if not fails else f'{fails} failed'}")
sys.exit(1 if fails else 0)

#!/usr/bin/env python3
"""Tests for kit-docs-archive: superseded .docx, .pptx, .pdf, and .xlsx move to archive/; open and locked files are
skipped; archive copies are never overwritten; the folder comes from KIT_DOCS_DIR or kit-docs' manifest."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-docs-archive"
passed = failed = 0


def ok(cond, name, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"ok   {name}")
    else:
        failed += 1
        print(f"FAIL {name}\n     {detail}")


def run(env, *args):
    e = {k: v for k, v in os.environ.items() if not k.startswith("KIT_DOCS")}
    e.update(env)
    p = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, env=e, timeout=120)
    return p.returncode, p.stdout + p.stderr


with tempfile.TemporaryDirectory() as t:
    d = pathlib.Path(t) / "docs"
    (d / "archive").mkdir(parents=True)
    for n in ("Kit-matrix-v1.8.0.xlsx", "Kit-matrix-v1.8.1.xlsx", "Kit-matrix-v1.8.0.docx", "Kit-matrix-v1.8.1.docx",
              "Kit-matrix-v1.8.0.pdf", "Kit-matrix-v1.8.1.pdf", "Kit-deck-v1.8.0.pptx", "Kit-deck-v1.8.1.pptx",
              "Kit-guide-v1.8.0.docx", "Kit-guide-v1.8.1.docx", "Kit-guide.docx", "notes.txt"):
        (d / n).write_text(n)
    (d / "~$Kit-guide-v1.8.0.docx").write_text("lock")
    (d / "archive/Kit-matrix-v1.8.0.docx").write_text("older archive copy")
    env = {"KIT_DOCS_DIR": str(d)}

    rc, out = run(env)
    ok(rc == 0 and "would move Kit-matrix-v1.8.0.xlsx" in out, "a superseded workbook is listed", out)
    ok("Nothing changed" in out and (d / "Kit-matrix-v1.8.0.xlsx").exists(), "the preview moves nothing", out)

    rc, out = run(env, "--yes")
    ok(rc == 0 and (d / "archive/Kit-matrix-v1.8.0.xlsx").exists() and not (d / "Kit-matrix-v1.8.0.xlsx").exists(),
       "--yes moves the workbook", out)
    ok((d / "archive/Kit-matrix-v1.8.0.pdf").exists() and (d / "archive/Kit-deck-v1.8.0.pptx").exists(),
       "PDF and deck copies move too", out)
    ok((d / "archive/Kit-matrix-v1.8.0.docx").read_text() == "older archive copy"
       and (d / "archive/Kit-matrix-v1.8.0-dup.docx").read_text() == "Kit-matrix-v1.8.0.docx",
       "an existing archive copy is never overwritten", out)
    ok((d / "Kit-guide-v1.8.0.docx").exists() and "skipped Kit-guide-v1.8.0.docx" in out,
       "a file with an Office lock file is skipped", out)
    ok((d / "archive/Kit-guide.docx").exists(), "the unversioned original moves once a versioned copy exists", out)
    ok(all((d / n).exists() for n in ("Kit-matrix-v1.8.1.xlsx", "Kit-matrix-v1.8.1.docx", "Kit-deck-v1.8.1.pptx",
                                     "notes.txt")), "current versions and other files stay")

    (d / "~$Kit-guide-v1.8.0.docx").unlink()
    (d / "Kit-matrix-v1.8.0.docx").write_text("again")
    (d / "archive/Kit-matrix-v1.8.0-dup.docx").exists()
    rc, out = run(env, "--yes")
    ok((d / "archive/Kit-guide-v1.8.0.docx").exists(), "once the lock is gone, the file moves", out)
    ok((d / "archive/Kit-matrix-v1.8.0-dup2.docx").read_text() == "again", "a second clash gets -dup2", out)

    rc, out = run(env)
    ok(rc == 0 and "nothing superseded" in out, "then nothing is left to move", out)

    man = pathlib.Path(t) / "docs-build.json"
    man.write_text(json.dumps({"docs_dir": str(d)}))
    (d / "Kit-x-v1.0.xlsx").write_text("a")
    (d / "Kit-x-v1.1.xlsx").write_text("b")
    rc, out = run({"KIT_DOCS_MANIFEST": str(man)})
    ok(rc == 0 and "would move Kit-x-v1.0.xlsx" in out, "the folder comes from the manifest's docs_dir", out)

    rc, out = run({"KIT_DOCS_MANIFEST": str(pathlib.Path(t) / "missing.json")})
    ok(rc != 0 and "no docs folder" in out, "no folder and no manifest: a clear stop", out)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)

#!/usr/bin/env python3
"""Tests for kit-docs, the internal docs builder, with stand-in build, PDF, qpdf, pdfinfo, check, archive, and
stamp commands (no Office): plan runs nothing; build runs each document's steps, makes and repairs the PDFs, runs
the checks, counts pages, copies the files (keeping a different file it replaces), prints the table, and saves the
result; a document whose script says another version isn't built; a failed step, a missing output, a failed check,
or a page count out of range fails it; --archive and --stamp run only when everything passed, and --stamp only for
a full build; bump changes labels but not revision-history rows or prose, and only with --write (keeping the old
script); status says what's behind the code; the manifest must use command lists, never shell strings.

  python3 tests/test_kit_docs.py
"""
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-docs"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-docs-"))
BUILD = TMP / "docs/build"
DOCS = TMP / "docs"
OUTDIR = TMP / "docs/Output"
FAKEBIN = TMP / "bin"
CODE = TMP / "code"
for d in (BUILD, OUTDIR, FAKEBIN, CODE):
    d.mkdir(parents=True, exist_ok=True)
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:1200])


def exe(path, body):
    path.write_text("#!" + sys.executable + "\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


# A code repository at version 1.8.0
subprocess.run(["git", "init", "-q", str(CODE)], check=True)
(CODE / "VERSION").write_text("1.8.0\n")
subprocess.run(["git", "-C", str(CODE), "add", "VERSION"], check=True)
subprocess.run(["git", "-C", str(CODE), "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "v"],
               check=True)

# Stand-in tools on the PATH the manifest prepends
exe(FAKEBIN / "qpdf", "import shutil, sys\nshutil.copy(sys.argv[1], sys.argv[2])\nopen(sys.argv[2], 'a').write('%qpdf\\n')\n")
exe(FAKEBIN / "pdfinfo", "import sys\ntext = open(sys.argv[1]).read()\nprint('Pages:', text.count('PAGE'))\n")
(BUILD / "fake_pdf.py").write_text(
    "import sys, pathlib\nsrc = pathlib.Path(sys.argv[1])\nn = int(src.read_text().split('pages=')[1].split()[0])\n"
    "src.with_suffix('.pdf').write_text('%PDF\\n' + 'PAGE\\n' * n)\n")
(BUILD / "check.py").write_text("import sys\nsys.exit(1 if 'BAD' in open(sys.argv[1]).read() else 0)\n")
(BUILD / "archive.py").write_text("open('archived.txt', 'w').write('yes')\nprint('archived')\n")
(BUILD / "stamp.py").write_text("open('stamped.txt', 'w').write('yes')\nprint('stamped')\n")
BUILDER = '''import sys
VERSION, DATE = "1.8.0", "10-Nov-2026"
OUT = f"Doc-{NAME}-v{VERSION}.docx"
META = {"footer": "Confidential | Doc {NAME} v1.8.0"}
RELATED = "see the Other Doc v1.8.0"
NOTE = "Since Kit 1.8.0 the installer keeps your rules"
REV = [
    ["1.8.0", "2026-11-10", "me", "First at 1.8.0"]]
pages = int(sys.argv[1]) if len(sys.argv) > 1 else 5
open(OUT, "w").write(f"docx pages={pages} " + ("BAD" if "--bad" in sys.argv else ""))
'''
for name in ("alpha", "beta"):
    (BUILD / f"build_{name}.py").write_text(BUILDER.replace("{NAME}", name), encoding="utf-8")
(BUILD / "build_gamma.py").write_text(BUILDER.replace("{NAME}", "gamma").replace('"1.8.0", "10-Nov', '"1.7.0", "10-Nov'),
                                      encoding="utf-8")


def manifest(**over):
    m = {"docs_dir": str(DOCS), "build_dir": str(BUILD), "copy_to": [str(DOCS), str(OUTDIR)], "code_repo": str(CODE),
         "path_prepend": [str(FAKEBIN)],
         "pdf": {"command": ["python3", "fake_pdf.py", "{file}"], "repair": True},
         "checks": [{"name": "fake", "command": ["python3", "check.py", "{file}"], "applies": [".docx"]}],
         "archive": ["python3", "archive.py"], "stamp": ["python3", "stamp.py"],
         "documents": [
             {"name": "alpha", "steps": [["python3", "build_alpha.py", "7"]], "outputs": ["Doc-alpha-v{version}.docx"],
              "version_from": {"file": "build_alpha.py", "regex": "^VERSION, DATE = \"([0-9.]+)\""},
              "require": ["First at {version}"]},
             {"name": "beta", "steps": [["python3", "build_beta.py", "3"]], "outputs": ["Doc-beta-v{version}.docx"],
              "version_from": {"file": "build_beta.py", "regex": "^VERSION, DATE = \"([0-9.]+)\""},
              "expect_pages": [2, 4]}]}
    m.update(over)
    return m


MAN = TMP / "docs-build.json"


def write(m):
    MAN.write_text(json.dumps(m), encoding="utf-8")


def kd(*args):
    env = dict(os.environ, KIT_DOCS_MANIFEST=str(MAN), PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, env=env, timeout=120)
    return r.returncode, r.stdout + r.stderr


write(manifest())
# ---- plan --------------------------------------------------------------------------------------------------------
code, out = kd("plan")
ok(code == 0 and "alpha: ready" in out and "beta: ready" in out and "Nothing was run" in out, "plan lists each document", out)
ok(not list(BUILD.glob("Doc-*.docx")), "plan runs nothing")

# ---- build -------------------------------------------------------------------------------------------------------
(DOCS / "Doc-alpha-v1.8.0.docx").write_text("an older, different copy")
code, out = kd("build", "--archive")
ok(code == 0, "a build where everything passes exits 0", out)
ok("alpha" in out and "1.8.0" in out and " 7 " in out + " " and "ok" in out, "the table has the document, version, pages",
   out)
pdf = BUILD / "Doc-alpha-v1.8.0.pdf"
ok(pdf.is_file() and "%qpdf" in pdf.read_text(), "the PDF was made and rewritten with qpdf")
ok((DOCS / "Doc-alpha-v1.8.0.docx").read_text().startswith("docx pages=7") and (OUTDIR / "Doc-alpha-v1.8.0.pdf").is_file(),
   "the files are copied to each copy_to folder")
kept = list((BUILD / "kit-docs-backups").rglob("Doc-alpha-v1.8.0.docx"))
ok(kept and kept[0].read_text() == "an older, different copy", "a different file it replaced is kept first", kept)
res = json.loads((BUILD / "kit-docs-result.json").read_text())
ok(res["ok"] and res["documents"]["alpha"]["pages"] == {"Doc-alpha-v1.8.0.docx": 7}, "the result is saved", res)
ok((BUILD / "archived.txt").exists(), "--archive ran when everything passed")
ok("no revision-history row" not in out and "missing:" not in out, "no reminders when the rows are there", out)

# status: current, then behind after a code commit
code, out = kd("status")
ok(code == 0 and "alpha" in out and "current" in out, "status: current after a build", out)
(CODE / "x.txt").write_text("change")
subprocess.run(["git", "-C", str(CODE), "add", "x.txt"], check=True)
subprocess.run(["git", "-C", str(CODE), "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "c"],
               check=True)
code, out = kd("status", "--json")
st = {r["name"]: r for r in json.loads(out)["documents"]}
ok(st["alpha"]["state"] == "behind" and "1 commit(s) behind" in st["alpha"]["why"], "status: behind after a commit", st)
code, out = kd("--check")
ok(code == 0 and "0 of 2 internal documents current" in out, "--check gives one line", out)

# ---- failures ----------------------------------------------------------------------------------------------------
m = manifest()
m["documents"][1]["expect_pages"] = [10, 20]
write(m)
code, out = kd("build", "--archive", "--stamp")
ok(code == 1 and "outside the expected 10 to 20" in out, "a page count out of range fails the document", out)
ok(not (BUILD / "stamped.txt").exists(), "--stamp doesn't run when a document failed")

m = manifest()
m["documents"][0]["steps"] = [["python3", "build_alpha.py", "7", "--bad"]]
write(m)
code, out = kd("build", "--keep-going")
ok(code == 1 and "check fake failed" in out and "beta" in out, "a failed check fails the document; --keep-going goes on",
   out)
m = manifest()
m["documents"][0]["steps"] = [["python3", "-c", "import sys; sys.exit(4)"]]
write(m)
code, out = kd("build")
ok(code == 1 and "exited 4" in out and "beta: ok" not in out, "a failed step stops the build", out)
m = manifest()
m["documents"][0]["steps"] = [["python3", "-c", "pass"]]
m["documents"][0]["outputs"] = ["Nope-v{version}.docx"]
write(m)
code, out = kd("build", "--only", "alpha")
ok(code == 1 and "didn't make Nope-v1.8.0.docx" in out, "a missing output fails the document", out)

write(manifest())
code, out = kd("build", "--only", "alpha", "--stamp")
ok(code == 0 and "needs a full build" in out and not (BUILD / "stamped.txt").exists(), "--stamp needs a full build", out)
code, out = kd("build", "--stamp")
ok(code == 0 and (BUILD / "stamped.txt").exists(), "--stamp runs after a full build that passed", out)
code, out = kd("build", "--only", "nope")
ok(code == 2 and "no document called nope" in out, "an unknown document is refused", out)

# a document whose script says another version
m = manifest()
m["documents"].append({"name": "gamma", "steps": [["python3", "build_gamma.py"]], "outputs": ["Doc-gamma-v{version}.docx"],
                       "version_from": {"file": "build_gamma.py", "regex": "^VERSION, DATE = \"([0-9.]+)\""},
                       "require": ["What's new in Kit {version}"]})
write(m)
code, out = kd("plan")
ok("gamma: says 1.7.0: run kit-docs bump 1.8.0" in out, "plan says which scripts need a bump", out)
code, out = kd("build", "--only", "gamma")
ok(code == 1 and "run kit-docs bump 1.8.0 first" in out and not (BUILD / "Doc-gamma-v1.8.0.docx").exists(),
   "a document at another version isn't built", out)

# ---- bump --------------------------------------------------------------------------------------------------------
before = (BUILD / "build_gamma.py").read_text()
code, out = kd("bump", "1.8.0", "--only", "gamma")
ok(code == 0 and "Nothing written" in out and (BUILD / "build_gamma.py").read_text() == before, "bump previews only", out)
ok("missing: What's new in Kit 1.8.0" in out, "bump says what still needs writing", out)
code, out = kd("bump", "1.8.0", "--only", "gamma", "--write")
after = (BUILD / "build_gamma.py").read_text()
ok('VERSION, DATE = "1.8.0"' in after, "bump --write moves the version label", after)
ok("Doc gamma v1.8.0" in after and "Other Doc v1.8.0" in after, "and the v-labels (footer, cross-references)", after)
ok('["1.8.0", "2026-11-10", "me", "First at 1.8.0"]' in after, "revision-history rows stay as they are")
ok("Since Kit 1.8.0 the installer" in before.replace("1.7.0", "1.8.0") and after.count("Since Kit 1.8.0") == 1,
   "a release named in prose isn't a label", after)
ok('"10-Nov-2026"' not in after.split("\n")[1], "the date on the version line becomes today's", after.split("\n")[1])
ok(list((BUILD / "kit-docs-backups").rglob("build_gamma.py")), "the old script is kept")

# ---- the manifest --------------------------------------------------------------------------------------------------
m = manifest()
m["documents"][0]["steps"] = ["python3 build_alpha.py; rm -rf /"]
write(m)
code, out = kd("plan")
ok(code == 2 and "never a shell string" in out, "a shell-string step is refused", out)
MAN.unlink()
code, out = kd("plan")
ok(code == 2 and "no manifest" in out and "docs-build.example.json" in out, "no manifest: says where to start", out)
ex = json.loads((REPO / "kit/templates/docs-build.example.json").read_text())
ok(ex["documents"] and all(isinstance(s, list) for d in ex["documents"] for s in d["steps"]),
   "the example manifest is valid and uses command lists")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{P} passed, {F} failed")
sys.exit(1 if F else 0)

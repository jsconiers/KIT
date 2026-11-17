#!/usr/bin/env python3
"""Tests for kit-drift: same-named documents whose contents differ across libraries (with version, " - Copy", and
"(1)" suffixes ignored; identical copies and versions side by side in one folder not reported; same-library notes
files not reported), template copies (placeholder names, byte-identical and near-identical Word copies of a
template), --since, roots from the Drift roots field, lock and empty files skipped, --json, --check, exit codes, and
nothing changed on disk. Synthetic folders.

  python3 tests/test_drift.py
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-drift"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


def docx(path, text):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document><w:body>" + "".join(
            f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text.split("\n")) + "</w:body></w:document>")


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-drift-"))
KIT, PROJ, PUB, TPL = TMP / "kit", TMP / "projects", TMP / "published", TMP / "templates"
for d in (KIT / "memory/context", PROJ / "alpha", PROJ / "beta", PUB, TPL):
    d.mkdir(parents=True)
ENV = dict(os.environ, KIT_DIR=str(KIT), PYTHONDONTWRITEBYTECODE="1")

body = "\n".join(f"Section {i}: describe the scope, the systems affected, and the risks in plain words." for i in range(40))
docx(TPL / "DOC template.docx", body)
docx(PROJ / "alpha/Payments hub @ DOC-###.docx", "Payments hub draft\n" + body)      # placeholder name
shutil.copy(TPL / "DOC template.docx", PROJ / "beta/Scope.docx")                     # byte-identical
docx(PROJ / "beta/Near copy.docx", body.replace("Section 3:", "Part 3:"))            # near-identical
docx(PROJ / "beta/Real design.docx", "A finished design about storage tiering, unrelated to the template.")
(PROJ / "alpha/Payments hub IA v0.3.md").write_text("project copy, edited\n")
(PUB / "Payments hub IA v1.0.md").write_text("published copy\n")
(PUB / "Payments hub IA - Copy.md").write_text("published copy\n")                    # same as the published one
(PROJ / "alpha/Same everywhere.pdf").write_bytes(b"%PDF same")
(PUB / "Same everywhere (1).pdf").write_bytes(b"%PDF same")
(PROJ / "alpha/questions.md").write_text("alpha notes\n")
(PROJ / "beta/questions.md").write_text("beta notes\n")
(PROJ / "alpha/Plan v1.docx").write_bytes(b"one")
(PROJ / "alpha/Plan v2.docx").write_bytes(b"two")
(PROJ / "alpha/~$Lock.docx").write_bytes(b"lock")
(PROJ / "alpha/Empty.docx").write_bytes(b"")
(PROJ / "alpha/Budget.xlsx").write_bytes(b"budget one")
(PROJ / "beta/Budget.xlsx").write_bytes(b"budget two")
old = time.time() - 400 * 86400
os.utime(PROJ / "alpha/Budget.xlsx", (old, old))
os.utime(PROJ / "beta/Budget.xlsx", (old, old))


def snapshot():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for r in (PROJ, PUB, TPL) for p in r.rglob("*") if p.is_file()}


def run(*a):
    r = subprocess.run([sys.executable, str(TOOL), *map(str, a)], capture_output=True, text=True, env=ENV, timeout=60)
    return r.returncode, r.stdout, r.stderr


try:
    before = snapshot()
    code, out, err = run(PROJ, PUB, "--templates", TPL, "--json")
    d = json.loads(out)
    names = {g["name"]: g for g in d["same_name_different_contents"]}
    ok(code == 1, "exit 1 when something drifted", code)
    ok("payments hub ia.md" in names, "same name across libraries, suffixes ignored", list(names))
    g = names.get("payments hub ia.md", {"copies": []})
    ok(len(g["copies"]) == 3 and g.get("versions") == 2, "copies and distinct versions counted", g)
    ok(g["copies"] and g["copies"][0]["path"].endswith("Payments hub IA - Copy.md") or
       g["copies"][0]["modified"] >= g["copies"][-1]["modified"], "newest first", g)
    ok("same everywhere.pdf" not in names, "identical copies not reported", list(names))
    ok("questions.md" not in names, "one library's notes files not reported", list(names))
    ok("plan.docx" not in names, "versions in one folder not reported", list(names))
    ok("budget.xlsx" in names, "office documents in two folders of one library reported", list(names))
    ok(d["skipped"]["empty"] == 1, "empty files skipped and counted", d["skipped"])
    ok(not any("~$" in c["path"] for g in names.values() for c in g["copies"]), "lock files skipped")

    t = {pathlib.Path(x["path"]).name: x for x in d["template_copies"]}
    ok("Payments hub @ DOC-###.docx" in t, "placeholder in the name", list(t))
    ok("Scope.docx" in t and "byte-identical" in " ".join(t["Scope.docx"]["reasons"]), "byte-identical template", t)
    ok("Near copy.docx" in t and "same text" in " ".join(t["Near copy.docx"]["reasons"]), "near-identical template", t)
    ok("Real design.docx" not in t, "a real document isn't a template copy", list(t))
    ok(not any("templates" in x["path"].split(os.sep)[-2] for x in d["template_copies"]),
       "the templates folder itself isn't reported", list(t))

    code, out, _ = run(PROJ, PUB, "--templates", TPL, "--near", "1", "--json")
    t = {pathlib.Path(x["path"]).name for x in json.loads(out)["template_copies"]}
    ok("Near copy.docx" not in t and "Scope.docx" in t, "--near threshold", t)

    since = time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400))
    code, out, _ = run(PROJ, PUB, "--templates", TPL, "--since", since, "--json")
    ok("budget.xlsx" not in {g["name"] for g in json.loads(out)["same_name_different_contents"]},
       "--since leaves out older drift", out[:300])

    code, out, _ = run(PROJ, PUB, "--templates", TPL)
    ok("Same name, different contents: 2" in out and "Template copies in project folders: 3" in out,
       "text report counts", out)
    ok("changes nothing" in out and "->" in out, "text report suggests, never acts", out)

    (KIT / "memory/context/library.md").write_text(
        f"- **Drift roots:**\n  - `{PUB}`\n  - `{TMP / 'missing'}`\n- **Template placeholders:**\n  - `ZZZ`\n"
        f"- **Templates folder:** `{TPL}`\n")
    code, out, _ = run("--json")
    d = json.loads(out)
    ok(d["roots_from"] == "Drift roots" and d["missing"], "roots from library.md, missing reported", d)
    code, out, _ = run(PROJ / "alpha", "--near", "1", "--json")
    t = {pathlib.Path(x["path"]).name for x in json.loads(out)["template_copies"]}
    ok("Payments hub @ DOC-###.docx" not in t, "Template placeholders field replaces the defaults", t)
    code, out, _ = run("--check")
    ok(code == 0 and out.startswith("kit-drift:"), "--check one line", out)

    (KIT / "memory/context/library.md").write_text("")
    code, out, err = run()
    ok(code == 2 and "Drift roots" in err, "no roots is a usage problem", out + err)
    code, out, _ = run("--check")
    ok("not set" in out, "--check says not set", out)
    code, out, err = run(PUB, "--since", "yesterday")
    ok(code == 2, "bad --since", err)

    ok(snapshot() == before, "nothing on disk changed")
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{P} passed, {F} failed")
sys.exit(1 if F else 0)

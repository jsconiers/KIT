#!/bin/bash
# test_templates.sh: the templates folder is consistent with the README index, the agents, and the
# setup files. Run from anywhere: bash tests/test_templates.sh
cd "$(dirname "$0")/.." || exit 1
exec python3 - <<'PY'
import pathlib, re, sys
root = pathlib.Path("kit")
tdir = root / "templates"
ok = fail = 0
def check(cond, msg):
    global ok, fail
    if cond:
        ok += 1; print("ok  ", msg)
    else:
        fail += 1; print("FAIL", msg)

templates = sorted(p.name for p in tdir.glob("*-template.md"))
readme = (tdir / "README.md").read_text()
indexed = set(re.findall(r"`([\w-]+-template\.md)`", readme))
for t in templates:
    check(t in indexed, f"README indexes {t}")
for t in sorted(indexed):
    check((tdir / t).exists(), f"README entry {t} exists")

refs = set()
for p in list((root / "agents").glob("*.md")) + list((root / "memory/context").glob("*.md")):
    refs |= set(re.findall(r"([\w-]+-template\.md)", p.read_text()))
for t in sorted(refs):
    check((tdir / t).exists(), f"referenced template {t} exists")
for t in templates:
    if t == "adr-template.md":
        continue
    check(t in refs, f"{t} is pointed at by an agent or setup file")

for t in templates:
    text = re.sub(r"\s+", " ", (tdir / t).read_text())
    check(text.startswith("# "), f"{t} has a title")
    check("Copy it" in text, f"{t} says to copy and adapt it")
    check(re.search(r"Classification", text) is not None, f"{t} has a classification field")
    check("DD-Mmm-YYYY" in text, f"{t} uses the DD-Mmm-YYYY date format")

print(f"templates tests: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
PY

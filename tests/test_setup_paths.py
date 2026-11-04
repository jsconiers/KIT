#!/usr/bin/env python3
"""Tests for doctor.py's "Setup paths" check: path fields in memory/context/*.md that look set but won't
be read the way they're written. The bug it guards against: tools took the first backticked word on a
setup line as the path, and after the fix (only a value that starts with a backticked path counts), a
line like "the register at `compliance/x.md`" reads as not set without a word.

  python3 tests/test_setup_paths.py
"""
import importlib.util
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SHARED = REPO / "shared"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:600])


spec = importlib.util.spec_from_file_location("doctor", SHARED / "doctor.py")
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)

TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-setup-paths-"))
try:
    # ---- the shipped setup files: every listed field is there, and none is flagged
    shipped = REPO / "kit/memory/context"
    for name, field, _ in doctor.SETUP_PATH_FIELDS:
        if field == "Vendor evaluations":       # an optional line kit-vendors documents; not shipped
            continue
        text = (shipped / name).read_text(encoding="utf-8")
        ok(re.search(r"^- \*\*" + re.escape(field) + r":\*\*", text, re.M),
           f"the shipped {name} has the field the check reads: {field}")
    ok(doctor.setup_path_problems(shipped) == [], "the shipped setup files pass as they are",
       doctor.setup_path_problems(shipped))

    # ---- a copy with the field values edited
    ctx = TMP / "context"
    shutil.copytree(shipped, ctx)

    def edit(name, field, value):
        f = ctx / name
        text = f.read_text(encoding="utf-8")
        text, n = re.subn(r"^(- \*\*" + re.escape(field) + r":\*\*)[^\n]*$", lambda m: m.group(1) + " " + value,
                          text, count=1, flags=re.M)
        assert n == 1, (name, field)
        f.write_text(text, encoding="utf-8")

    edit("compliance.md", "Exception register", "the register at `compliance/waivers.md`.")
    edit("compliance.md", "PBC tracker", "`compliance/pbc.md`. The register kit-pbc keeps.")
    edit("compliance.md", "Control map", "optional. Start from `control-map.example.json`.")
    edit("demands.md", "Register", "`<library root>/demands/REGISTER.md`.")
    edit("sharing.md", "Shared root", "not set. The shared folder, for example `~/Team/Kit`.")
    edit("decisions.md", "Folder", "Kit's ADRs go in `decisions/`, in the library root.")
    edit("library.md", "Library root", "`~/Library-Root/`. Work documents stay here.")
    edit("future-tech.md", "Folder", "a folder with no backticks at all")
    probs = {(n, f): p for n, f, p in doctor.setup_path_problems(ctx)}
    ok(("compliance.md", "Exception register") in probs and "reads it as not set" in probs[("compliance.md", "Exception register")]
       and "kit-exceptions" in probs[("compliance.md", "Exception register")],
       "a path named later in the line is flagged, with the tool that reads it", probs)
    ok(("decisions.md", "Folder") in probs, "decisions.md Folder: the same, for another file", probs)
    ok(("demands.md", "Register") in probs and "placeholder" in probs[("demands.md", "Register")],
       "a backticked <library root> placeholder is flagged: it's read as it stands", probs)
    ok(("compliance.md", "PBC tracker") not in probs and ("library.md", "Library root") not in probs,
       "a value that starts with the backticked path passes", probs)
    ok(("compliance.md", "Control map") not in probs and ("sharing.md", "Shared root") not in probs,
       "optional and not set values are unset on purpose and pass, even with an example in backticks", probs)
    ok(("future-tech.md", "Folder") not in probs, "plain text with no backticks isn't this check's business", probs)
    ok(len(probs) == 3, "nothing else is flagged", probs)
    ok(not any("`compliance/waivers.md`" in p for p in probs.values()),
       "the report names the field and file, not the value it found later", probs)

    # ---- description fields that aren't paths are never read
    edit("compliance.md", "Regulatory watch folder", "`~/Watch/`")
    with open(ctx / "compliance.md", "a", encoding="utf-8") as f:
        f.write("- **Risk scale:** the team's, see `risk-matrix.md` in the library.\n")
    probs2 = {(n, f) for n, f, _ in doctor.setup_path_problems(ctx)}
    ok(("compliance.md", "Risk scale") not in probs2, "a description field that isn't a path isn't flagged", probs2)

    # ---- wired into the full check, as a warning that never fails it
    doctor.results.clear()
    doctor.check_setup_paths(ctx)
    ok(doctor.results and doctor.results[0][0] == "warn" and doctor.results[0][1] == "Setup paths"
       and "demands.md Register" in doctor.results[0][2], "check_setup_paths reports a warning", doctor.results)
    doctor.results.clear()
    doctor.check_setup_paths(shipped)
    ok(doctor.results == [("ok", "Setup paths", doctor.results[0][2])], "and ok when nothing is wrong", doctor.results)
    src = (SHARED / "doctor.py").read_text(encoding="utf-8")
    ok(re.search(r"for fn in \([^)]*check_setup_paths", src), "main() runs the check with the others")

    # ---- the readers follow the same rule: only a value that starts with the path counts
    kit = TMP / "kit"
    (kit / "memory").mkdir(parents=True)
    shutil.copytree(shipped, kit / "memory/context")
    root = TMP / "lib"
    (kit / "memory/context/library.md").write_text(f"- **Library root:** `{root}`\n", encoding="utf-8")
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import kit_compliance as kc; "
                        "print(kc.setup_path(sys.argv[2], 'Exception register', 'compliance/exception-register.md'))",
                        str(SHARED), str(kit)], capture_output=True, text=True)
    ok(r.stdout.strip() == str(root / "compliance/exception-register.md"),
       "kit_compliance: the shipped Exception register line gives the default", r.stdout + r.stderr)
    src = {n: (SHARED / "bin" / n).read_text(encoding="utf-8") for n in ("kit-decisions", "kit-stakeholders", "kit-audit-export")}
    ok('m = re.match(r"`([^`]+)`", val)' in src["kit-decisions"], "kit-decisions reads Folder only from the start of the value")
    ok('rel = re.match(r"`([^`]+)`"' in src["kit-stakeholders"], "kit-stakeholders reads Register only from the start")
    ok(src["kit-audit-export"].count('m = re.match(r"`([^`]+)`", val)') == 2,
       "kit-audit-export reads Folder and Control map only from the start")
    root.mkdir(parents=True, exist_ok=True)
    (root / "kit-audit-export --controls").write_text("{}", encoding="utf-8")   # what the old reader picked up
    cm = kit / "memory/context/compliance.md"
    cm.write_text(re.sub(r"^- \*\*Control map:\*\*[^\n]*$", "- **Control map:** the map for `kit-audit-export --controls`, "
                         "kept by the team.", cm.read_text(encoding="utf-8"), count=1, flags=re.M), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SHARED / "bin/kit-audit-export"), "--controls", "", "--from", "2026-10-01",
                        "--to", "2026-10-31", "--out", str(TMP / "pack")], capture_output=True, text=True,
                       env=dict(os.environ, KIT_DIR=str(kit), HOME=str(TMP), USERPROFILE=str(TMP)))
    ok("no control map" in (r.stdout + r.stderr), "kit-audit-export: a Control map line that names the command first means no map, "
       "not a file named after the command", (r.stdout + r.stderr)[-300:])
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\nsetup paths: {P} passed, {F} failed")
sys.exit(1 if F else 0)

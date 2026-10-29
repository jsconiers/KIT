#!/usr/bin/env python3
"""Tests for the Windows fixes: doctor.py's scheduled-job check (Task Scheduler instead of launchd, no
os.getuid), its folder-privacy check (the access list instead of file modes), the personal notes index after
a clean scaffold, and JSON files that start with a UTF-8 byte-order mark (as Windows PowerShell 5.1 writes
them). The Windows parts run against canned schtasks and icacls output, so this runs anywhere.

Run: python3 tests/test_windows_fixes.py
"""
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SHARED = REPO / "shared"
PASS = FAIL = 0


def ok(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))     # works for the tools with no .py too
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class FakeOS:
    """os, as seen on another platform: only the name changes."""
    def __init__(self, name):
        self.name = name

    def __getattr__(self, attr):
        return getattr(os, attr)


tmp = pathlib.Path(tempfile.mkdtemp())
doc = load("doctor", SHARED / "doctor.py")
canned = {}
doc.run = lambda cmd, timeout=30: canned.get(cmd[0], (1, "not found"))

# ---- 1. scheduled jobs on Windows: Task Scheduler's \Kit\ folder, and no os.getuid
doc.os = FakeOS("nt")
canned["schtasks"] = (0, '"\\Kit\\Kit Morning Brief","10/30/2026 7:00:00 AM","Ready"\n'
                         '"\\Kit\\Kit Backup","N/A","Disabled"\n'
                         '"\\Microsoft\\Windows\\Defrag\\ScheduledDefrag","N/A","Ready"\n')
doc.results.clear()
try:
    doc.check_jobs()
    crashed = None
except Exception as e:  # noqa: BLE001
    crashed = e
r = {name: (level, detail) for level, name, detail in doc.results}
ok(crashed is None, "check_jobs runs on Windows (no os.getuid)", str(crashed))
ok(r.get("Scheduled task Kit Morning Brief", ("",))[0] == "ok" and r.get("Scheduled task Kit Backup", ("",))[0] == "warn"
   and not any("Defrag" in n for n in r), "Kit's tasks are checked; a disabled one warns; others are ignored", str(r))

# ---- 4. folder privacy on Windows: the access list, not 0o777
doc.KIT = "C:\\Users\\nick\\Claude\\Agents\\kit"
os.environ["USERNAME"] = "nick"
for label, out, want, text in [
    ("locked to the owner", "C:\\Users\\nick\\Claude\\Agents\\kit DESKTOP-1\\nick:(OI)(CI)(F)\n\n"
     "Successfully processed 1 files; Failed processing 0 files\n", "ok", "only your account"),
    ("others can open it", "C:\\Users\\nick\\Claude\\Agents\\kit BUILTIN\\Users:(I)(OI)(CI)(RX)\n"
     "                                  DESKTOP-1\\nick:(I)(OI)(CI)(F)\n\nSuccessfully processed 1 files\n",
     "warn", "others can open it: BUILTIN\\Users"),
    ("inherited from above", "C:\\Users\\nick\\Claude\\Agents\\kit DESKTOP-1\\nick:(I)(OI)(CI)(F)\n", "warn",
     "takes its access from the folder above")]:
    canned["icacls"] = (0, out)
    doc.results.clear()
    doc.check_permissions()
    level, name, detail = doc.results[0]
    ok(level == want and text in detail and "0o777" not in detail, f"privacy check: {label}", detail)

# ---- 2. a clean scaffold has a personal notes index, and doctor's memory check passes
home = tmp / "home"
home.mkdir()
r = subprocess.run([sys.executable, str(SHARED / "kit_setup.py"), "scaffold"], capture_output=True, text=True,
                   env=dict(os.environ, HOME=str(home), USERPROFILE=str(home)), timeout=300)
kit = home / "Claude/Agents/kit"
ok(r.returncode == 0 and (kit / "memory/personal/INDEX.md").exists() and (kit / "memory/personal/decisions").is_dir(),
   "the scaffold makes memory/personal/ and its index", (r.stdout + r.stderr)[-300:])
doc.os = os
doc.KIT, doc.MEM = kit, kit / "memory"
doc.results.clear()
doc.check_index()
r = {name: (level, detail) for level, name, detail in doc.results}
ok(r.get("Memory index", ("",))[0] == "ok", "doctor's memory index check passes right after a scaffold", str(r))
(kit / "memory/personal/INDEX.md").unlink()
doc.results.clear()
doc.check_index()
r = {name: (level, detail) for level, name, detail in doc.results}
ok(r.get("Memory index", ("",))[0] == "ok" and r.get("Personal notes index", ("",))[0] == "warn",
   "a missing personal index is a warning with the fix, not a failure", str(r))

# ---- 3. JSON with a UTF-8 byte-order mark
bom = "\ufeff"
claude_dir = tmp / "bomhome/.claude"
claude_dir.mkdir(parents=True)
(claude_dir / "settings.json").write_text(bom + json.dumps({"permissions": {"allow": ["Read(~/Claude/Agents/kit/**)"]}}),
                                          encoding="utf-8")
(tmp / "bomhome/.claude.json").write_text(bom + json.dumps({"mcpServers": {"logos": {"command": "x"}}}), encoding="utf-8")
setup = load("kit_setup", SHARED / "kit_setup.py")
setup.SETTINGS = claude_dir / "settings.json"
try:
    data, existed = setup.load_settings()
    got = data.get("permissions", {}).get("allow")
except Exception as e:  # noqa: BLE001
    got = e
ok(got == ["Read(~/Claude/Agents/kit/**)"], "the installer reads a settings.json that starts with a BOM", str(got))
doc.HOME = tmp / "bomhome"
doc.results.clear()
doc.check_settings()
ok(not any(level == "FAIL" and "can't read" in detail for level, _, detail in doc.results),
   "doctor reads it too", str(doc.results))
kc = load("kit_claude", SHARED / "kit_claude.py")
kc.HOME = tmp / "bomhome"
path = kc.mcp_config_for("logos")
ok(path and json.loads(pathlib.Path(path).read_text())["mcpServers"]["logos"]["command"] == "x",
   "a BOM'd ~/.claude.json still gives its MCP servers")
if path:
    os.unlink(path)
lib = load("kit_library", SHARED / "bin/kit-library")
cfgdir = tmp / "kitbom/library"
cfgdir.mkdir(parents=True)
(cfgdir / "collections.json").write_text(bom + json.dumps({"version": 1, "collections": [], "tags": {}}), encoding="utf-8")
lib.CONFIG = cfgdir / "collections.json"
try:
    cfg = lib.load_config()
    got = isinstance(cfg.get("collections"), list)
except Exception as e:  # noqa: BLE001
    got = e
ok(got is True, "kit-library reads a collections.json with a BOM", str(got))

shutil.rmtree(tmp, ignore_errors=True)
print(f"Windows fixes tests: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)

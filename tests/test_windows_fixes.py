#!/usr/bin/env python3
"""Tests for the Windows fixes: doctor.py's scheduled-job check (Task Scheduler instead of launchd, no
os.getuid), its folder-privacy check (the access list instead of file modes), the personal notes index after
a clean scaffold, and JSON files that start with a UTF-8 byte-order mark (as Windows PowerShell 5.1 writes
them). The Windows parts run against canned schtasks, icacls, and PowerShell output, so this runs anywhere; CI also
runs it on Windows, with python-docx installed. Also: kit-library's Word file without textutil, Windows
calendar commands (kit-wrap, kit-meetprep, kit-holds, kit-degraded, the dashboard), and finding kitcal.

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
import zipfile

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
# ... by SID (Get-Acl through PowerShell), so an Entra account whose name isn't USERNAME passes
ME_SID = "S-1-12-1-1111-2222-3333-4444"
os.environ["USERNAME"] = "jsmith"
for label, out, want, text in [
    ("an Entra account, locked to it", f"ME {ME_SID}\nACE {ME_SID}\tFalse\tAllow\tAzureAD\\JohnSmith\n", "ok",
     "only your account"),
    ("others by SID", f"ME {ME_SID}\nACE {ME_SID}\tFalse\tAllow\tAzureAD\\JohnSmith\n"
     "ACE S-1-5-32-545\tFalse\tAllow\tBUILTIN\\Users\n", "warn", "others can open it: BUILTIN\\Users"),
    ("a deny entry isn't access", f"ME {ME_SID}\nACE {ME_SID}\tFalse\tAllow\tAzureAD\\JohnSmith\n"
     "ACE S-1-1-0\tFalse\tDeny\tEveryone\n", "ok", "only your account"),
    ("inherited, by SID", f"ME {ME_SID}\nACE {ME_SID}\tTrue\tAllow\tAzureAD\\JohnSmith\n", "warn",
     "takes its access from the folder above")]:
    canned["powershell"] = (0, out)
    canned["icacls"] = (0, "C:\\Users\\jsmith\\Claude\\Agents\\kit AzureAD\\JohnSmith:(OI)(CI)(F)\n")
    doc.results.clear()
    doc.check_permissions()
    level, name, detail = doc.results[0]
    ok(level == want and text in detail, f"privacy check by SID: {label}", detail)
canned["powershell"] = (1, "Get-Acl failed")
doc.results.clear()
doc.check_permissions()
ok(doc.results[0][0] == "warn" and "AzureAD\\JohnSmith" in doc.results[0][2],
   "privacy check: without PowerShell it falls back to icacls names", str(doc.results))
del canned["powershell"]
os.environ["USERNAME"] = "nick"

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

# ---- 5. kit-library deliver: markdown to Word without macOS's textutil
MD = "# Pre-read\n\nSome **bold** and *italic* text.\n\n- one\n- two\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
os.environ["KIT_DIR"] = str(tmp / "libkit")
lib2 = load("kit_library_deliver", SHARED / "bin/kit-library")
del os.environ["KIT_DIR"]
lib2.TEXTUTIL = str(tmp / "no-textutil")
out_dir = tmp / "libout"
out_dir.mkdir()
try:
    import docx  # noqa: F401
    have_docx = True
except ImportError:
    have_docx = False
if have_docx:
    made, why = lib2.md_to_docx(MD, "Pre-read", out_dir / "a.docx")
    with zipfile.ZipFile(out_dir / "a.docx") as z:
        body = z.read("word/document.xml").decode("utf-8")
    ok(made and "Pre-read" in body and "bold" in body and "<w:tbl>" in body and not (out_dir / ".page.html").exists(),
       "kit-library: python-docx makes the Word file (headings, bold, lists, tables)", why)
else:
    print("skip kit-library python-docx path (python-docx isn't installed here)")


def no_docx(page, dest):
    raise ImportError("no python-docx")


lib2.html_to_docx = no_docx
calls = []


def fake_word(cmd, env=None, **kw):
    calls.append((cmd, dict(env or {}), pathlib.Path(env["KIT_DOCX_IN"]).read_text(encoding="utf-8")))
    pathlib.Path(env["KIT_DOCX_OUT"]).write_bytes(b"PK fake docx")
    return subprocess.CompletedProcess(cmd, 0, b"", b"")


real_run, real_os = lib2.subprocess.run, lib2.os
lib2.os = FakeOS("nt")
lib2.subprocess.run = fake_word
made, why = lib2.md_to_docx(MD, "Pre-read", out_dir / "b.docx")
cmd, env, page = calls[-1] if calls else ([], {}, "")
ok(made and cmd[:1] == ["powershell"] and "Word.Application" in cmd[-1] and "SaveAs2" in cmd[-1]
   and env.get("KIT_DOCX_OUT") == str(out_dir / "b.docx") and "<h1>Pre-read</h1>" in page
   and not (out_dir / ".page.html").exists(),
   "kit-library: on Windows without python-docx, Word itself (COM) saves the page", why)
lib2.subprocess.run = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b"no Word")
made, why = lib2.md_to_docx(MD, "Pre-read", out_dir / "c.docx")
ok(not made and "python-docx isn't installed" in why and "Word" in why, "kit-library: no converter says why", why)
lib2.os = FakeOS("posix")
made, why = lib2.md_to_docx(MD, "Pre-read", out_dir / "d.docx")
ok(not made and "Word" not in why, "kit-library: Word is tried only on Windows", why)
lib2.subprocess.run, lib2.os = real_run, FakeOS("posix")   # not Windows, so no Word either, on any runner
# The whole deliver, with no converter: the Markdown is delivered, and it says so.
lib2.CONFIG.parent.mkdir(parents=True, exist_ok=True)
lib2.CONFIG.write_text(json.dumps({"version": 1, "collections": [], "tags": {},
                                   "output": {"folder": str(tmp / "Kit Output")}}), encoding="utf-8")
src = tmp / "preread.md"
src.write_text(MD, encoding="utf-8")
import contextlib  # noqa: E402
import io  # noqa: E402
err = io.StringIO()
with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
    rc = lib2.cmd_deliver([str(src), "--kind", "reports", "--no-date"])
got = sorted(p.name for p in (tmp / "Kit Output").rglob("*") if p.is_file())
ok(rc == 0 and got == ["preread.md"] and "delivering the Markdown instead" in err.getvalue(),
   "kit-library deliver: with no converter, the Markdown arrives and it says why", f"{got} {err.getvalue()!r}")

# ---- 6. calendar commands on Windows: backslashes kept, quotes taken off, kitcal found through PATHEXT
class FakeShutil:
    def __init__(self, found):
        self.found = found

    def which(self, name):
        return self.found.get(name)


SHIM = "C:\\Users\\nick\\Claude\\Agents\\kit\\.install\\platform\\windows\\bin\\kitcal.cmd"
WINCMD = "py -3 C:\\Users\\nick\\Claude\\Agents\\kit\\.install\\platform\\windows\\calendar\\kitcal.py events --from today"
for tool in ("kit-wrap", "kit-meetprep", "kit-holds", "kit-degraded"):
    m = load(tool.replace("-", "_") + "_cmd", SHARED / "bin" / tool)
    m.os = FakeOS("nt")
    m.shutil = FakeShutil({"kitcal": SHIM, "py": "C:\\Windows\\py.exe"})
    w1 = m.command_words(WINCMD)
    w2 = m.command_words('"C:\\Program Files\\Python312\\python.exe" C:\\k\\kitcal.py events')
    w3 = m.command_words("kitcal events --from today --to today")
    ok(w1 == ["C:\\Windows\\py.exe", "-3", "C:\\Users\\nick\\Claude\\Agents\\kit\\.install\\platform\\windows\\calendar\\kitcal.py",
              "events", "--from", "today"]
       and w2 == ["C:\\Program Files\\Python312\\python.exe", "C:\\k\\kitcal.py", "events"] and w3[0] == SHIM,
       f"{tool}: a Windows calendar command keeps its backslashes, and kitcal is found as kitcal.cmd", f"{w1} {w2} {w3}")
    m.os = FakeOS("posix")
    ok(m.command_words("~/bin/kitcal events 'a b'") == [os.path.expanduser("~/bin/kitcal"), "events", "a b"],
       f"{tool}: macOS splitting is unchanged")

# The dashboard's Today panel splits CALENDAR_JSON_CMD the same way
dash = load("dashboard_cal", SHARED / "dashboard.py")
dash.KIT = tmp / "dashkit"
(dash.KIT / ".install/shared/morning").mkdir(parents=True)
dcfg = dash.KIT / ".install/shared/morning/config"
dcfg.write_text('CALENDAR_JSON_CMD="\'C:\\Program Files\\Kit\\kitcal.exe\' events --from today"\n', encoding="utf-8")
dash.os = FakeOS("nt")
w_nt = dash.calendar_cmd()
dash.os = os
dcfg.write_text('CALENDAR_JSON_CMD="\'/opt/My Tools/cal\' events"\n', encoding="utf-8")
w_px = dash.calendar_cmd()
ok(w_nt == ["C:\\Program Files\\Kit\\kitcal.exe", "events", "--from", "today"] and w_px == ["/opt/My Tools/cal", "events"],
   "dashboard: a quoted calendar path with spaces stays one word (Windows and macOS)", f"{w_nt} {w_px}")

# ---- 7. calendar output that isn't clean UTF-8 doesn't stop kit-meetprep or kit-holds
cal = tmp / "badcal.py"
cal.write_text("import sys\nsys.stdout.buffer.write(b'[{\"title\": \"Caf\\xe9 sync\", \"start\": \"2026-11-02T10:00:00\", "
               "\"end\": \"2026-11-02T11:00:00\", \"has_attendees\": true}]')\n", encoding="utf-8")
cfg = tmp / "calcfg"
cfg.write_text(f'CALENDAR_JSON_CMD="{sys.executable} {cal}"\n', encoding="utf-8")
mp = load("kit_meetprep_dec", SHARED / "bin/kit-meetprep")
mp.kd.CONFIG = cfg
try:
    evs = mp.load_events(type("A", (), {"json": None})())
    got = [e.get("title") for e in evs]
except Exception as e:  # noqa: BLE001
    got = e
ok(isinstance(got, list) and len(got) == 1 and got[0].startswith("Caf"), "kit-meetprep: stray bytes in calendar output are replaced", str(got))
kh = load("kit_holds_dec", SHARED / "bin/kit-holds")
kh.kd.CONFIG = cfg
try:
    got = [e["title"] for e in kh.busy_events(None)]
except Exception as e:  # noqa: BLE001
    got = e
ok(isinstance(got, list) and len(got) == 1, "kit-holds: stray bytes in calendar output are replaced", str(got))

# ---- 8. kit-touch and kit-feedback find kitcal where the Windows installer puts it
wk = tmp / "winkit"
for tool in ("kit-touch", "kit-feedback"):
    m = load(tool.replace("-", "_") + "_cal", SHARED / "bin" / tool)
    m.os, m.shutil, m.KIT = FakeOS("nt"), FakeShutil({}), wk
    shim = wk / ".install/platform/windows/bin/kitcal.cmd"
    py = wk / ".install/platform/windows/calendar/kitcal.py"
    shim.parent.mkdir(parents=True, exist_ok=True)
    py.parent.mkdir(parents=True, exist_ok=True)
    shim.write_text("@echo off\n")
    py.write_text("")
    a = m.kitcal_command()
    shim.unlink()
    b = m.kitcal_command()
    py.unlink()
    c = m.kitcal_command()
    m.shutil = FakeShutil({"kitcal": "C:\\k\\kitcal.CMD"})
    d = m.kitcal_command()
    ok(a == [str(shim)] and b == [sys.executable, str(py)] and c is None and d == ["C:\\k\\kitcal.CMD"],
       f"{tool}: kitcal on PATH, else the installer's shim, else kitcal.py, else none", f"{a} {b} {c} {d}")

shutil.rmtree(tmp, ignore_errors=True)
print(f"Windows fixes tests: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)

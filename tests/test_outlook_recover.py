#!/usr/bin/env python3
"""Tests kit-outlook's deeper calendar probe and OUTLOOK_RECOVER (off, notify, restart), with fake pgrep,
osascript, pkill, and open on the PATH: no real Outlook is touched. Also the settings allowlist entry and the
dashboard banner."""
import datetime as dt
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent.parent
BIN = HERE / "shared/bin/kit-outlook"
passed = failed = 0


def ok(cond, name, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"ok   {name}")
    else:
        failed += 1
        print(f"FAIL {name} {detail}")


FAKES = {
    "pgrep": '#!/bin/bash\n[ -f "$OFAKE/running" ]\n',
    # A probe prints the version and the calendar part by mode; a quit closes Outlook unless it ignores quits.
    "osascript": r'''#!/bin/bash
script=$(cat)
echo "osascript $(echo "$script" | grep -q ' to quit' && echo quit || echo probe)" >> "$OFAKE/calls"
mode=$(cat "$OFAKE/mode")
if echo "$script" | grep -q ' to quit'; then
  case "$mode" in ignore-quit*|stuck) ;; *) rm -f "$OFAKE/running" ;; esac
  exit 0
fi
if [ "$mode" = oldfake ]; then echo "16.89"; exit 0; fi
if [ "$mode" = ok ] || [ -f "$OFAKE/restarted" ]; then echo "16.89|CAL:3"; exit 0; fi
echo "16.89|CAL-HUNG"; exit 0
''',
    "pkill": r'''#!/bin/bash
echo "pkill $*" >> "$OFAKE/calls"
mode=$(cat "$OFAKE/mode")
[ "$mode" = stuck ] || rm -f "$OFAKE/running"
''',
    "open": r'''#!/bin/bash
echo "open $*" >> "$OFAKE/calls"
touch "$OFAKE/running" "$OFAKE/restarted"
''',
}


def setup(tmp):
    fb = tmp / "fakebin"
    fb.mkdir()
    for name, body in FAKES.items():
        (fb / name).write_text(body)
        (fb / name).chmod(0o755)
    kit = tmp / "kit"
    (kit / ".install/logs").mkdir(parents=True)
    (kit / "briefs").mkdir()
    of = tmp / "ofake"
    of.mkdir()
    return fb, kit, of


def run(fb, kit, of, mode, recover, running=True, args=("--retry", "--recover"), fresh=True):
    if fresh:
        for f in ("calls", "restarted"):
            (of / f).unlink(missing_ok=True)
    (of / "mode").write_text(mode)
    if running:
        (of / "running").touch()
    else:
        (of / "running").unlink(missing_ok=True)
    env = {**os.environ, "PATH": f"{fb}:{os.environ['PATH']}", "OFAKE": str(of), "KIT_DIR": str(kit),
           "KIT_OUTLOOK_ANY_OS": "1", "OUTLOOK_RETRY_WAITS": "0", "OUTLOOK_QUIT_WAIT": "0",
           "OUTLOOK_RESTART_SETTLE": "0", "OUTLOOK_RECOVER": recover}
    out = kit / "briefs/outlook.txt"
    r = subprocess.run([sys.executable, str(BIN), "check", *args, "--write", str(out)], env=env,
                       capture_output=True, text=True, timeout=60)
    calls = (of / "calls").read_text() if (of / "calls").exists() else ""
    return r.returncode, out.read_text().strip(), calls


def main():
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        fb, kit, of = setup(tmp)
        stamp = kit / f".install/logs/outlook-restart-{dt.date.today().isoformat()}"

        rc, line, calls = run(fb, kit, of, "ok", "notify")
        ok(rc == 0 and line.startswith("ok ") and "16.89 answered" in line, "calendar answers -> ok", line)

        rc, line, calls = run(fb, kit, of, "oldfake", "notify")
        ok(rc == 0 and line.startswith("ok "), "a version-only answer still counts as ok", line)

        rc, line, calls = run(fb, kit, of, "hung", "notify")
        ok(rc == 1 and line.startswith("hung ") and "calendar didn't answer" in line and "Quit and reopen" in line
           and "after 2 tries" in line, "version answers, calendar hangs -> hung, with the fix", line)
        ok("quit" not in calls and "pkill" not in calls and "open" not in calls, "notify touches nothing", calls)

        rc, line, calls = run(fb, kit, of, "hung", "off")
        ok(line.startswith("hung ") and "quit" not in calls and not stamp.exists(), "off: check only", calls)

        rc, line, calls = run(fb, kit, of, "hung", "restart", running=False)
        ok(line.startswith("not-running") and calls == "" and not stamp.exists(),
           "restart mode never starts Outlook that wasn't open", calls)

        rc, line, calls = run(fb, kit, of, "hung", "restart")
        ok(rc == 0 and line.startswith("ok ") and "Kit restarted it" in line, "restart: quit, reopen, ok", line)
        ok("osascript quit" in calls and "open -g -b com.microsoft.Outlook" in calls and "pkill" not in calls,
           "restart: polite quit was enough, reopened in the background", calls)
        ok(stamp.exists() and "restarted, ok" in stamp.read_text(), "restart: today's stamp records the outcome")
        log = (kit / ".install/logs/outlook-recover.log").read_text()
        ok("recovery started" in log and "recovery finished: restarted, ok" in log, "restart: logged")

        rc, line, calls = run(fb, kit, of, "hung", "restart")
        ok(line.startswith("hung ") and "already restarted Outlook once today" in line and "quit" not in calls,
           "restart: at most once a day", line)

        stamp.unlink()
        rc, line, calls = run(fb, kit, of, "ignore-quit", "restart")
        ok(rc == 0 and "pkill -TERM -x Microsoft Outlook" in calls and "open -g" in calls,
           "restart: Outlook ignores quit -> SIGTERM to Outlook alone, then reopen", calls)

        stamp.unlink()
        rc, line, calls = run(fb, kit, of, "stuck", "restart")
        ok(rc == 1 and "wouldn't close" in line and "Force Quit" in line, "restart: won't close -> asks for Force Quit",
           line)
        ok("open" not in calls.replace("osascript", "") and "-KILL" not in calls and "-9" not in calls,
           "restart: never force-kills, never reopens a closed-but-stuck Outlook", calls)

        # Settings allowlist.
        sys.path.insert(0, str(HERE / "shared"))
        spec = importlib.util.spec_from_file_location("kit_settings", HERE / "shared/kit_settings.py")
        ks = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ks)
        s = {"name": "OUTLOOK_RECOVER", "editable": True, "kind": "config", "type": ks.EDITABLE_CONFIG["OUTLOOK_RECOVER"]}
        ok(ks.validate(s, "restart") == "restart", "settings: restart is allowed")
        try:
            ks.validate(s, "force")
            ok(False, "settings: a mode outside off/notify/restart is refused")
        except ks.Invalid:
            ok(True, "settings: a mode outside off/notify/restart is refused")
        ok(ks.config_area("CALENDAR_CACHE_DAYS") == "delivery and briefs", "settings: cache keys sit with the briefs")

        # Dashboard banner for today's hung check.
        (kit / "briefs/outlook.txt").write_text(f"hung {dt.date.today().isoformat()} 07:45 Outlook is open and answers, "
                                                "but its calendar didn't answer in 20 seconds (it's hung).\n")
        spec = importlib.util.spec_from_file_location("dashboard", HERE / "shared/dashboard.py")
        dash = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dash)
        dash.KIT = kit
        ok("Outlook is hung" in dash.outlook_banner(), "dashboard: banner for a hung Outlook")
        (kit / "briefs/outlook.txt").write_text("hung 2020-01-01 07:45 old\n")
        ok(dash.outlook_banner() == "", "dashboard: an old check raises no banner")

    print(f"outlook recovery tests: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

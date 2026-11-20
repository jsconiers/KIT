#!/usr/bin/env python3
"""Tests the calendar cache (kit-calcache, shared/kit_calcache.py) and kit-degraded's fallback to it: saving
(owner-only, pruned), choosing the copy that covers today, last week's recurring meetings when none does,
declined meetings left out, bad output refused, and run.sh handing the cached events to the model run when
Outlook is hung (a fake claude records the prompt)."""
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent.parent
CAL = HERE / "shared/bin/kit-calcache"
DEG = HERE / "shared/bin/kit-degraded"
passed = failed = 0


def ok(cond, name, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"ok   {name}")
    else:
        failed += 1
        print(f"FAIL {name} {detail}")


def run(tool, kit, *args, now="2026-11-16T07:45", env_extra=None):
    env = {**os.environ, "KIT_DIR": str(kit), "KIT_NOW": now, "KIT_TODAY": now[:10], **(env_extra or {})}
    return subprocess.run([sys.executable, str(tool), *args], env=env, capture_output=True, text=True, timeout=60)


def mode(p):
    return stat.S_IMODE(p.stat().st_mode)


def events_file(tmp, name, events):
    f = tmp / name
    f.write_text(json.dumps(events))
    return f


def main():
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        kit = tmp / "kit"
        (kit / ".install/shared/morning").mkdir(parents=True)
        (kit / "briefs").mkdir()
        (kit / "QUEUE.md").write_text("# Queue\n\n## Owner\n\n- [ ] something\n")
        cache = kit / ".install/cache"

        # Monday 16-Nov: a week of events, three of them repeating.
        week = [
            {"start": "2026-11-16 09:00", "end": "2026-11-16 09:30", "title": "Altiris weekly", "recurring": True},
            {"start": "2026-11-16 11:00", "end": "2026-11-16 12:00", "title": "Vendor demo", "recurring": False},
            {"start": "2026-11-16 14:00", "end": "2026-11-16 14:30", "title": "Declined sync", "recurring": True,
             "my_response": "declined"},
            {"start": "2026-11-17 13:00", "end": "2026-11-17 13:30", "title": "AAP GDS True-Up", "recurring": False},
            {"start": "2026-11-17 00:00", "all_day": True, "title": "Personal day"},
        ]
        f = events_file(tmp, "week.json", week)
        r = run(CAL, kit, "save", "--file", str(f), "--days", "7")
        saved = cache / "calendar-2026-11-16.json"
        ok(r.returncode == 0 and saved.exists() and "saved 5 event(s)" in r.stdout, "save: writes today's copy",
           r.stdout + r.stderr)
        if os.name != "nt":
            ok(mode(saved) == 0o600 and mode(cache) == 0o700, "save: owner-only file and folder")
        doc = json.loads(saved.read_text())
        ok(doc["covers_from"] == "2026-11-16" and doc["covers_to"] == "2026-11-22", "save: covers --days from today")

        # Tuesday, Outlook hung: the Monday copy covers it.
        r = run(CAL, kit, "show", "--json", now="2026-11-17T07:45")
        got = json.loads(r.stdout)
        ok(got["kind"] == "cache" and "as of 16-Nov-2026 07:45; may be stale" in got["label"]
           and {e["title"] for e in got["events"]} == {"AAP GDS True-Up", "Personal day"},
           "lookup: the newest copy covering today, labelled may be stale", r.stdout)
        r = run(CAL, kit, "brief", now="2026-11-17T07:45")
        ok(r.stdout.splitlines()[0].startswith("Calendar from the calendar as of 16-Nov-2026 07:45")
           and "- all day  Personal day" in r.stdout and "- 13:00  AAP GDS True-Up" in r.stdout,
           "brief: label, then one line per event, all-day first", r.stdout)

        # Monday 23-Nov: nothing covers it, so last Monday's recurring meetings, declined left out.
        r = run(CAL, kit, "show", "--json", now="2026-11-23T07:45")
        got = json.loads(r.stdout)
        ok(got["kind"] == "recurring" and [e["title"] for e in got["events"]] == ["Altiris weekly"]
           and got["events"][0]["start"] == "2026-11-23 09:00" and "likely only" in got["label"]
           and "Monday 16-Nov-2026" in got["label"], "lookup: last week's recurring meetings, moved to today",
           r.stdout)

        # A copy with no recurring flags: last week's timed meetings, all-day ones left out.
        kit2 = tmp / "kit2"
        (kit2 / ".install/shared/morning").mkdir(parents=True)
        f2 = events_file(tmp, "noflags.json", [{"start": "2026-11-16 10:00", "title": "Standup"},
                                               {"start": "2026-11-16 00:00", "all_day": True, "title": "Holiday"}])
        run(CAL, kit2, "save", "--file", str(f2))
        r = run(CAL, kit2, "show", "--json", now="2026-11-23T07:45")
        got = json.loads(r.stdout)
        ok(got["kind"] == "recurring" and [e["title"] for e in got["events"]] == ["Standup"]
           and "doesn't say which repeat" in got["label"], "lookup: no recurring flags -> last week's timed meetings")
        r = run(CAL, kit2, "show", now="2026-11-17T07:45")
        ok(r.returncode == 1 and "No saved calendar" in r.stdout, "lookup: a today-only copy doesn't cover tomorrow")

        # Bad output is refused; nothing saved.
        bad = tmp / "bad.json"
        bad.write_text('{"not": "a list"}')
        r = run(CAL, kit2, "save", "--file", str(bad), now="2026-11-18T07:45")
        ok(r.returncode == 1 and not (kit2 / ".install/cache/calendar-2026-11-18.json").exists(),
           "save: refuses output that isn't a JSON list", r.stdout)

        # A command that fails saves nothing; a working command is used (CALENDAR_JSON_CMD).
        fake = tmp / "cal.sh"
        fake.write_text("#!/bin/sh\necho '[{\"start\": \"2026-11-18 08:00\", \"title\": \"From the command\"}]'\n")
        fake.chmod(0o755)
        (kit2 / ".install/shared/morning/config").write_text(f'CALENDAR_JSON_CMD="{fake}"\n')
        r = run(CAL, kit2, "save", now="2026-11-18T07:45")
        ok(r.returncode == 0 and "From the command" in (kit2 / ".install/cache/calendar-2026-11-18.json").read_text(),
           "save: runs CALENDAR_JSON_CMD", r.stdout)
        failing = tmp / "fail.sh"
        failing.write_text("#!/bin/sh\nexit 3\n")
        failing.chmod(0o755)
        (kit2 / ".install/shared/morning/config").write_text(f'CALENDAR_JSON_CMD="{failing}"\n')
        r = run(CAL, kit2, "save", now="2026-11-19T07:45")
        ok(r.returncode == 1 and "failed" in r.stdout and not (kit2 / ".install/cache/calendar-2026-11-19.json").exists(),
           "save: a failing command saves nothing", r.stdout)

        # Pruning: copies older than CALENDAR_CACHE_KEEP days go.
        r = run(CAL, kit, "save", "--file", str(f), now="2026-12-01T07:45", env_extra={"CALENDAR_CACHE_KEEP": "14"})
        ok(not saved.exists() and (cache / "calendar-2026-12-01.json").exists(), "save: drops copies past the keep days")

        # kit-degraded: Outlook hung (--no-calendar) uses the saved copy; --no-calendar-cache doesn't.
        shutil.rmtree(cache)
        run(CAL, kit, "save", "--file", str(f), "--days", "7")
        r = run(DEG, kit, "--reason", "test", "--no-calendar", "--print", now="2026-11-17T07:45")
        ok("Stale: From the calendar as of 16-Nov-2026 07:45; may be stale" in r.stdout
           and "13:00  AAP GDS True-Up" in r.stdout, "degraded: Outlook out -> the saved calendar, marked stale",
           r.stdout + r.stderr)
        r = run(DEG, kit, "--reason", "test", "--no-calendar", "--no-calendar-cache", "--print", now="2026-11-17T07:45")
        ok("Calendar left out" in r.stdout and "AAP GDS" not in r.stdout, "degraded: --no-calendar-cache leaves it out")
        r = run(DEG, kit, "--reason", "test", "--no-calendar", now="2026-11-17T07:45")
        txt = (kit / "briefs/latest-text-work.txt").read_text()
        ok("saved calendar, may be stale" in txt, "degraded: the short text says the meetings are from the saved copy",
           txt)

        # run.sh: a hung Outlook hands the cached events to the model run; an ok Outlook saves a copy.
        if shutil.which("zsh") and os.name != "nt":
            home = tmp / "home"
            lb = home / ".local/bin"
            lb.mkdir(parents=True)
            k = home / "Claude/Agents/kit"
            shutil.copytree(kit / ".install/cache", k / ".install/cache")
            (k / "briefs").mkdir(parents=True)
            (k / ".install/logs").mkdir(parents=True)
            sb = k / ".install/shared/bin"
            sb.mkdir(parents=True)
            for n in ("kit-outlook", "kit-calcache"):
                shutil.copy(HERE / "shared/bin" / n, sb / n)
            for n in ("kit_calcache.py", "kit_daily.py"):
                shutil.copy(HERE / "shared" / n, k / ".install/shared" / n)
            (k / ".install/shared/morning").mkdir(parents=True)
            shutil.copy(HERE / "shared/morning/prompt.md", k / ".install/shared/morning/prompt.md")
            (k / ".install/shared/morning/config").write_text(
                f'OUTLOOK_RETRY_WAITS="0"\nCALENDAR_JSON_CMD="{fake}"\nCONNECTOR_CHECK="off"\nCONNECTION_CHECK="off"\n')
            of = tmp / "ofake"
            of.mkdir()
            (lb / "pgrep").write_text('#!/bin/bash\nexit 0\n')
            (lb / "osascript").write_text('#!/bin/bash\ncat >/dev/null\necho "16.89|$(cat "$OFAKE/cal")"\n')
            (lb / "claude").write_text(f'#!/bin/bash\nprintf "%s\\n" "$@" > "{tmp}/claude-args.txt"\n')
            for n in ("pgrep", "osascript", "claude"):
                (lb / n).chmod(0o755)
            env = {**os.environ, "HOME": str(home), "OFAKE": str(of), "KIT_OUTLOOK_ANY_OS": "1",
                   "KIT_TODAY": "", "KIT_NOW": ""}
            env.pop("KIT_DIR", None)
            # The Monday copy covers the real today only if today is within its range, so write one for today.
            import datetime as dt
            today = dt.date.today().isoformat()
            evs = [{"start": f"{today} 10:30", "title": "Cached standup"}]
            for p in (k / ".install/cache").glob("*.json"):
                p.unlink()
            subprocess.run([sys.executable, str(CAL), "save", "--file", str(events_file(tmp, "today.json", evs))],
                           env={**os.environ, "KIT_DIR": str(k)}, capture_output=True)
            (of / "cal").write_text("CAL-HUNG")
            subprocess.run(["zsh", str(HERE / "platform/mac/morning/run.sh"), "morning"], env=env,
                           capture_output=True, timeout=120)
            args = (tmp / "claude-args.txt").read_text() if (tmp / "claude-args.txt").exists() else ""
            ok("Stale: Outlook is open and answers, but its calendar didn't answer" in args
               and "Kit's saved copy of the calendar" in args and "10:30  Cached standup" in args,
               "run.sh: hung Outlook -> stale notice plus the cached events in the prompt", args[-600:])
            (of / "cal").write_text("CAL:2")
            (tmp / "claude-args.txt").unlink(missing_ok=True)
            for p in (k / ".install/logs").glob("*.done"):
                p.unlink()
            for p in (k / ".install/cache").glob("*.json"):
                p.unlink()
            subprocess.run(["zsh", str(HERE / "platform/mac/morning/run.sh"), "morning"], env=env,
                           capture_output=True, timeout=120)
            args = (tmp / "claude-args.txt").read_text() if (tmp / "claude-args.txt").exists() else ""
            c = k / f".install/cache/calendar-{today}.json"
            ok("Stale:" not in args and c.exists() and "From the command" in c.read_text(),
               "run.sh: Outlook ok -> no stale notice, and a fresh copy saved", args[-300:])

    print(f"calendar cache tests: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

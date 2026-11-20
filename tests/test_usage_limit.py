#!/usr/bin/env python3
"""Tests the usage-limit guard: shared/kit_limits.py (detector, reset parsing, the state file), kit-cost limit,
the health score's usage-limit line, and run.sh standing down with a fake claude (macOS zsh runner; skipped
where zsh isn't installed). Everything runs in throwaway folders; nothing real is touched.
  python3 tests/test_usage_limit.py
"""
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "shared"))
import kit_limits as kl  # noqa: E402
import kit_health  # noqa: E402

PASS = FAIL = 0


def ok(cond, name, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL += 1
        print(f"FAIL {name} {extra}")


UTC = dt.timezone.utc
REAL = ("API Error: 400 You have reached your specified per-user API usage limits. "
        "You will regain access on 2026-11-01 at 00:00 UTC.")
os.environ["KIT_LIMITS_NOW"] = "2026-10-27T11:45:00+00:00"

# ---- detector --------------------------------------------------------------------------------------------
hit = kl.detect("some log line\n" + REAL + "\nmore")
ok(hit and hit[0] == REAL, "the 26-Oct message is recognised, and only its line kept", hit)
ok(hit and hit[1] == dt.datetime(2026, 11, 1, tzinfo=UTC), "its reset is 2026-11-01 00:00 UTC", hit)
for text, want in [
    ("Claude AI usage limit reached|1793491200", dt.datetime.fromtimestamp(1793491200, UTC)),
    ("Your credit balance is too low to access the Anthropic API.", None),
    ("You have hit your limit. Your limit will reset at 2026-11-01T00:00:00Z", dt.datetime(2026, 11, 1, tzinfo=UTC)),
    ("Usage limit reached. Access resets on Nov 1 at 9am (Europe/London)", dt.datetime(2026, 11, 1, 9, tzinfo=UTC)),
    ("5-hour limit reached - resets 3pm (America/New_York)", dt.datetime(2026, 10, 27, 19, tzinfo=UTC)),
    ("Monthly usage limit exceeded", None),
]:
    h = kl.detect(text)
    ok(h is not None and h[1] == want, f"recognised with reset {want}: {text[:50]}", h)
for text in ["API Error: 429 rate limit exceeded", "overloaded_error: Overloaded", "API Error: 500 internal",
             "Rate limit reached for requests", "the brief mentions the budget", ""]:
    ok(kl.detect(text) is None, f"not a usage limit: {text[:40]!r}")
ok(kl.parse_reset("resets at 5pm (UTC)") == dt.datetime(2026, 10, 27, 17, tzinfo=UTC), "bare time: today's 5pm UTC")
ok(kl.parse_reset("resets at 9am (UTC)") == dt.datetime(2026, 10, 28, 9, tzinfo=UTC), "a bare time already past: tomorrow")
ok(kl.parse_reset("regain access on 2026-11-01") == dt.datetime(2026, 11, 1, tzinfo=UTC), "date only: midnight UTC")

# ---- state file lifecycle --------------------------------------------------------------------------------
tmp = pathlib.Path(tempfile.mkdtemp())
kit = tmp / "kit"
(kit / ".install/logs").mkdir(parents=True)
os.environ["KIT_DIR"] = str(kit)
P = kl.paths()


def cli(*args, env=None):
    e = {**os.environ, **(env or {})}
    r = subprocess.run([sys.executable, "-I", str(HERE / "shared/kit_limits.py"), *args],
                       capture_output=True, text=True, env=e)
    return r.returncode, r.stdout.strip()


rc, out = cli("check")
ok(rc == 0 and out == "ok", "no state: check says ok", (rc, out))
errf = tmp / "run.err"
errf.write_text(REAL + "\n")
outf = tmp / "run.json"
outf.write_text('{"type":"result","is_error":true,"result":"' + REAL + '"}')
rc, out = cli("detect", "--source", "morning", str(errf), str(outf))
ok(rc == 0 and out == "limit 2026-11-01T00:00:00+00:00", "detect records the limit", (rc, out))
st = json.loads(P["state"].read_text())
ok(st["source"] == "morning" and st["reset"] == "2026-11-01T00:00:00+00:00" and st["first_seen"], "state: source, reset, first seen", st)
ok(oct(P["state"].stat().st_mode)[-3:] in ("600", "644", "664"), "state file written")
rc, _ = cli("detect", "--source", "weekly", str(tmp / "missing"))
ok(rc == 1, "detect on no limit text exits 1")
cli("detect", "--source", "weekly", str(errf))
st2 = json.loads(P["state"].read_text())
ok(st2["source"] == "morning" and st2["last_source"] == "weekly" and st2["first_seen"] == st["first_seen"],
   "a second hit keeps the first source and first-seen time", st2)
rc, out = cli("check", "--mode", "weekly")
ok(rc == 2 and out.startswith("limited 2026-11-01T00:00:00+00:00"), "before the reset: check says limited", (rc, out))
rc, out = cli("check", "--probe")
ok(rc == 2, "a known reset: preflight's probe isn't spent", (rc, out))
rc, out = cli("notice")
ok("standing down" in out and "01-Nov-2026" in out, "the notice names the return date", out)
rc, out = cli("check", env={"KIT_LIMITS_NOW": "2026-11-01T00:00:01+00:00"})
ok(rc == 0 and not P["state"].exists(), "after the reset: check clears it", (rc, out))
ok("usage limit cleared" in P["log"].read_text(), "clearing is logged as 'usage limit cleared'")

# unknown reset: preflight probes once a day; a success clears it
cli("detect", "--source", "preflight", str(tmp / "credit.txt"))
(tmp / "credit.txt").write_text("Your credit balance is too low to access the Anthropic API.")
rc, _ = cli("detect", "--source", "preflight", str(tmp / "credit.txt"))
ok(rc == 0 and json.loads(P["state"].read_text())["reset"] is None, "unknown reset recorded as null")
rc, out = cli("check")
ok(rc == 2, "unknown reset: the runs stand down")
rc, out = cli("check", "--probe")
ok(rc == 0 and out == "probe", "unknown reset: the first preflight of the day may probe", (rc, out))
rc, out = cli("check", "--probe")
ok(rc == 2, "unknown reset: only once a day", (rc, out))
rc, out = cli("check", "--probe", env={"KIT_LIMITS_NOW": "2026-10-28T06:45:00+00:00"})
ok(rc == 0 and out == "probe", "the next day it may probe again", (rc, out))
P["marker"].write_text("sent")
rc, _ = cli("success", "--source", "preflight")
ok(rc == 0 and not P["state"].exists() and not P["marker"].exists(), "a success clears the state and the notice marker")

# ---- kit-cost limit --------------------------------------------------------------------------------------
cfgdir = kit / ".install/shared/morning"
cfgdir.mkdir(parents=True)
ledger = kit / ".install/logs/cost.jsonl"
ledger.write_text("".join(json.dumps({"date": f"2026-10-{d:02d}T07:45:00", "mode": "morning", "cost_usd": 2.0}) + "\n"
                          for d in range(1, 21)))


def cost(*args, cfg=""):
    (cfgdir / "config").write_text(cfg)
    r = subprocess.run([sys.executable, "-I", str(HERE / "shared/bin/kit-cost"), "limit", *args],
                       capture_output=True, text=True, env={**os.environ, "KIT_COST_TODAY": "2026-10-20"})
    return r.returncode, r.stdout.strip()


rc, out = cost("--brief")
ok(rc == 0 and out == "", "no limit set and none recorded: no brief line", out)
rc, out = cost(cfg='USAGE_LIMIT_MONTHLY_USD="100"\n')
ok(rc == 0 and "$40.00 used (40%)" in out and "projected $62.00" in out, "status: spend and projection against the limit", out)
rc, out = cost("--brief", cfg='USAGE_LIMIT_MONTHLY_USD="70"\n')
ok("projected $62.00" in out and "of the $70.00 API limit" in out, "projection at 89% of the limit: early warning", out)
rc, out = cost("--brief", cfg='USAGE_LIMIT_MONTHLY_USD="55"\n')
ok("runs stop before the month ends" in out, "projection over the limit: says the runs will stop", out)
rc, out = cost("--brief", cfg='USAGE_LIMIT_MONTHLY_USD="45"\n')
ok("$40.00 of the $45.00 monthly API limit used" in out, "spend itself past COST_WARN_PCT", out)
cli("detect", "--source", "morning", str(errf))
rc, out = cost("--brief")
ok("Claude usage limit reached; access returns 01-Nov-2026" in out, "a recorded limit: the brief line says when access returns", out)
rc, out = cost("--json")
ok(rc == 2 and json.loads(out)["active"] is True, "limit --json: active, exit 2", out)
rc, out = cost("clear")
ok(rc == 0 and "cleared" in out and not P["state"].exists(), "kit-cost limit clear forgets it", out)

# ---- health score ----------------------------------------------------------------------------------------
cli("detect", "--source", "morning", str(errf))
st = json.loads(P["state"].read_text())
st["reset"] = "2099-11-01T00:00:00+00:00"
P["state"].write_text(json.dumps(st))
line = kit_health.usage_limit(kit)
ok("Claude usage limit reached" in line, "health: an active limit gives a problem line", line)
fake = {"windows": {"7": {"morning": {"runs": 4, "success": 4}}}}
part = kit_health.runs(kit, fake)
ok(part["score"] == 15 and part["problems"][0].startswith("Claude usage limit"), "health: 10 points off the runs part", part)
st = json.loads(P["state"].read_text())
st["reset"] = "2020-01-01T00:00:00+00:00"
P["state"].write_text(json.dumps(st))
ok(kit_health.usage_limit(kit) == "", "health: a reset that has passed shows nothing")
P["state"].unlink()

# ---- run.sh stands down ----------------------------------------------------------------------------------
zsh = shutil.which("zsh")
if not zsh:
    print("skip run.sh tests: zsh isn't installed")
else:
    del os.environ["KIT_LIMITS_NOW"]
    del os.environ["KIT_DIR"]   # run.sh's tools find Kit under HOME, as on a real install
    home = tmp / "home"
    k2 = home / "Claude/Agents/kit"
    sh = k2 / ".install/shared"
    (sh / "morning").mkdir(parents=True)
    (sh / "bin").mkdir()
    (k2 / ".install/logs").mkdir(parents=True)
    (k2 / "briefs").mkdir()
    (home / ".local/bin").mkdir(parents=True)
    for f in ("prompt.md", "prompt-weekly.md", "prompt-worklist.md"):
        shutil.copy(HERE / "shared/morning" / f, sh / "morning" / f)
    shutil.copy(HERE / "shared/kit_limits.py", sh / "kit_limits.py")
    (sh / "morning/config").write_text('OUTLOOK_CHECK="off"\nCONNECTION_CHECK="off"\nRETRY_DELAY="1"\nRUN_ALERTS="off"\n')
    # fake deliver.py and kit-degraded record what they were asked to do
    (sh / "deliver.py").write_text("import sys,pathlib\nargs=sys.argv[1:]\nt=pathlib.Path(args[args.index('--text')+1]).read_text()\n"
                                   f"open({str(tmp / 'delivered.txt')!r},'a').write(t.strip()+'\\n')\n")
    (sh / "bin/kit-degraded").write_text(f"import sys\nopen({str(tmp / 'degraded.txt')!r},'a').write(' '.join(sys.argv[1:])+'\\n')\n"
                                         f"open({str(k2 / 'briefs/latest-text.txt')!r},'w').write('degraded brief')\n")
    REALF = REAL.replace("2026-11-01", "2099-11-01")
    claude = home / ".local/bin/claude"
    claude.write_text(f"""#!/bin/bash
n=$(cat "{tmp}/calls" 2>/dev/null || echo 0); echo $((n+1)) > "{tmp}/calls"
if [ -n "${{FAKE_LIMIT:-}}" ]; then echo "{REALF}" >&2; echo '{{"type":"result","is_error":true,"result":"{REALF}"}}'; exit 1; fi
echo "Kit test" > "{k2}/briefs/latest-text.txt"; echo "Kit test" > "{k2}/briefs/worklist-text.txt"
echo '{{"type":"result","result":"OK","total_cost_usd":0.01,"usage":{{}}}}'
""")
    claude.chmod(0o755)
    logs = k2 / ".install/logs"

    def run(mode, **env):
        for f in logs.glob("*.done"):
            f.unlink()
        subprocess.run([zsh, str(HERE / "platform/mac/morning/run.sh"), mode], capture_output=True, text=True,
                       env={**os.environ, "HOME": str(home), **env}, timeout=120)

    def calls():
        try:
            return int((tmp / "calls").read_text())
        except OSError:
            return 0

    def read(p):
        try:
            return p.read_text()
        except OSError:
            return ""

    run("worklist", FAKE_LIMIT="1")
    log = "\n".join(read(p) for p in logs.glob("2*.log"))
    ok((logs / "usage-limit.json").exists(), "run.sh: a usage-limit failure is recorded")
    ok(calls() == 1, "run.sh: no retry after a usage limit (it isn't transient)", calls())
    ok("later runs stand down" in log, "run.sh: logged that later runs stand down")
    n = calls()
    run("worklist")
    ok(calls() == n, "run.sh: the next non-morning run skips without calling claude", calls())
    log = "\n".join(read(p) for p in logs.glob("2*.log"))
    ok("worklist run skipped: usage limit" in log, "run.sh: the skip is logged")
    ok(read(tmp / "delivered.txt").count("Claude usage limit reached") == 1, "run.sh: one notice", read(tmp / "delivered.txt"))
    run("weekly")
    ok(calls() == n and read(tmp / "delivered.txt").count("Claude usage limit reached") == 1,
       "run.sh: a second skipped run sends no second notice")
    run("morning")
    ok(calls() == n, "run.sh: the morning run makes no model call while limited", calls())
    ok("Claude usage limit reached; access returns" in read(tmp / "degraded.txt") and "2099" in read(tmp / "degraded.txt"),
       "run.sh: the morning brief goes to kit-degraded with the limit as the reason", read(tmp / "degraded.txt"))
    # the reset passes: the next run goes ahead and the state clears
    st = json.loads((logs / "usage-limit.json").read_text())
    st["reset"] = "2020-01-01T00:00:00+00:00"
    (logs / "usage-limit.json").write_text(json.dumps(st))
    run("worklist")
    ok(calls() == n + 1 and not (logs / "usage-limit.json").exists(), "run.sh: after the reset the run goes ahead")
    ok("usage limit cleared" in read(logs / "usage-limit.log"), "run.sh: 'usage limit cleared' logged")
    # unknown reset, then a run succeeds (cleared by hand elsewhere, or a manual test run): the success clears it
    (logs / "usage-limit.json").write_text(json.dumps({"reason": "x", "first_seen": "2026-10-27T00:00:00+00:00",
                                                       "reset": None, "source": "morning"}))
    (sh / "morning/config").write_text('OUTLOOK_CHECK="off"\nCONNECTION_CHECK="off"\nRUN_ALERTS="off"\nUSAGE_LIMIT_GUARD="off"\n')
    run("worklist")
    ok(calls() == n + 2, "run.sh: USAGE_LIMIT_GUARD=off lets runs go ahead", calls())
    ok(not (logs / "usage-limit.json").exists(), "run.sh: a successful run clears a recorded limit")

    # preflight.sh: a known reset skips the paid login check; an unknown one probes once a day
    (sh / "morning/config").write_text("")

    def preflight(**env):
        subprocess.run([zsh, str(HERE / "platform/mac/morning/preflight.sh")], capture_output=True, text=True,
                       env={**os.environ, "HOME": str(home), **env}, timeout=120)

    known = {"reason": "x", "first_seen": "2026-10-27T00:00:00+00:00", "reset": "2099-11-01T00:00:00+00:00",
             "source": "morning"}
    (logs / "usage-limit.json").write_text(json.dumps(known))
    n = calls()
    preflight()
    ok(calls() == n and "login check skipped: Claude usage limit" in read(logs / "preflight.log"),
       "preflight: a known reset skips the paid login check", calls())
    known["reset"] = None
    (logs / "usage-limit.json").write_text(json.dumps(known))
    preflight(FAKE_LIMIT="1")
    ok(calls() == n + 1 and (logs / "usage-limit.json").exists(), "preflight: an unknown reset probes, and a failure keeps it")
    preflight()
    ok(calls() == n + 1, "preflight: only one probe a day", calls())
    st = json.loads((logs / "usage-limit.json").read_text())
    st["last_probe"] = "2000-01-01"
    st["reset"] = None
    (logs / "usage-limit.json").write_text(json.dumps(st))
    preflight()
    ok(calls() == n + 2 and not (logs / "usage-limit.json").exists(), "preflight: a successful probe clears it")

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)

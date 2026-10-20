#!/bin/bash
# Tests kit-reliability against fixture run logs dated relative to today (no real logs are read).
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
exec python3 - "$HERE" "$S" <<'PY'
import datetime as dt, json, os, pathlib, subprocess, sys
here, s = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
kit = s / "kit"; logs = kit / ".install/logs"; logs.mkdir(parents=True); (kit / "briefs").mkdir()
(kit / ".install/shared/morning").mkdir(parents=True)
(kit / ".install/shared/morning/config").write_text('RELIABILITY_MIN_PCT="90"\n')
now = dt.datetime.now().replace(microsecond=0)
def stamp(t): return t.strftime("%a %b %d %H:%M:%S EDT %Y")
def log(day, lines): 
    p = logs / f"{day:%Y-%m-%d}.log"
    with p.open("a") as f: f.write("\n".join(lines) + "\n")
def run(mode, t, secs, rc=0, after=("== delivered",), timeout=False, retried=False):
    out = [f"== {stamp(t)} start {mode} "]
    if retried: out.append(f"== {stamp(t + dt.timedelta(seconds=5))} retrying {mode} after transient failure (Overloaded)")
    if timeout: out.append(f"== {stamp(t + dt.timedelta(seconds=secs))} {mode} run hit its time limit (20 min) and was stopped")
    out.append(f"== {stamp(t + dt.timedelta(seconds=secs))} end {mode} rc={rc}")
    out += list(after)
    log(t.date(), out)
# morning: successes over 14 days at ~120s, but last 7 days at ~300s (slowdown), and nothing since 4 weekdays ago
for d in range(5, 15):
    t = (now - dt.timedelta(days=d)).replace(hour=7, minute=45, second=0)
    run("morning", t, 300 if d < 8 else 120)
# worklist: 2 failures in the last 7 days, 1 retried success, 1 timeout with degraded? (degraded is morning-only; use failure)
for d, kw in ((1, dict(rc=1, after=("== sent failure notice",))), (2, dict(rc=1, after=("== delivery failed",))),
              (3, dict(retried=True)), (4, dict(rc=142, timeout=True, after=("== sent failure notice",)))):
    run("worklist", (now - dt.timedelta(days=d)).replace(hour=9, minute=0, second=0), 50, **kw)
# a degraded morning brief 6 days ago
run("morning", (now - dt.timedelta(days=6)).replace(hour=7, minute=45, second=0), 200, rc=1,
    after=("== degraded brief written (the model run failed (exit 1))", "== delivered"))
# a skipped run
log(now.date() - dt.timedelta(days=1), [f"== {stamp(now - dt.timedelta(days=1))} worklist run skipped: 97% of the monthly budget used (stop at 95%)"])
# backup: success 3 days ago, failure 2 days ago (so last success > 36 h)
b = []
for d, ok in ((3, True), (2, False)):
    t = now - dt.timedelta(days=d)
    b += [f"== {stamp(t)} backup", "kit-backup: /x/kit-backup.tar.gz.enc (10 files, 1 MB, encrypted), checked" if ok else "kit-backup: database credential not found"]
(logs / "backup.log").write_text("\n".join(b) + "\n")
(logs / "sync.log").write_text("".join(f"{(now - dt.timedelta(hours=h)):%Y-%m-%d %H:%M} sync failed: timeout\n" for h in range(1, 10)))
(logs / "cost.jsonl").write_text("".join(json.dumps({"date": (now - dt.timedelta(days=d)).isoformat(), "mode": "morning", "cost_usd": c}) + "\n"
                                         for d, c in ((5, 0.5), (6, 0.7), (9, 0.4))))
env = dict(os.environ, KIT_DIR=str(kit))
tool = str(here / "shared/bin/kit-reliability")
r = subprocess.run([sys.executable, tool, "--json"], env=env, capture_output=True, text=True)
rep = json.loads(r.stdout)
P = F = 0
def ok(cond, name, detail=""):
    global P, F
    if cond: P += 1; print("ok  ", name)
    else: F += 1; print("FAIL", name, detail)
w7 = rep["windows"]["7"]
ok(w7["worklist"]["failure"] == 3 and w7["worklist"]["success"] == 1, "worklist outcomes: 3 failures (notice, delivery failed, timeout), 1 success", w7["worklist"])
ok(w7["worklist"]["timeout"] == 1 and w7["worklist"]["retried"] == 1 and w7["worklist"]["skipped"] == 1, "timeouts, retries and skips counted", w7["worklist"])
ok(w7["morning"]["degraded"] == 1, "a degraded brief is counted as degraded", w7["morning"])
ok(w7["morning"]["median_cost_usd"] == 0.6, "median cost from the ledger", w7["morning"])
ok(w7["morning"]["median_seconds"] == 300 and w7["morning"]["previous_median_seconds"] == 120, "median duration and the week before", w7["morning"])
ok(w7["backup"]["success"] == 1 and w7["backup"]["failure"] == 1, "backup log: one success, one failure", w7["backup"])
ok(rep["sync_failures"]["7"] == 9, "sync failures counted", rep["sync_failures"])
a = " | ".join(rep["alerts"])
ok("worklist: 3 failures in the last 7 days" in a, "alert: 2+ failures in 7 days", a)
ok("morning: median run time up 150%" in a, "alert: duration up more than 50%", a)
ok("worklist:" in a and "success over 30 days (under 90%)" in a, "alert: success rate under the threshold", a)
ok("backup: last successful run" in a, "alert: no successful backup in 36 hours", a)
ok("morning: last successful run" in a, "alert: no successful morning run lately", a)
ok("sync: 9 failures" in a, "alert: sync failing", a)
ok((kit / "briefs/reliability.json").exists(), "writes briefs/reliability.json")
(kit / "briefs/reliability.json").unlink()
r2 = subprocess.run([sys.executable, tool, "--no-write"], env=env, capture_output=True, text=True)
ok(not (kit / "briefs/reliability.json").exists() and "Last 7 days" in r2.stdout and "Alerts:" in r2.stdout, "--no-write prints the summary and writes nothing", r2.stdout[:200])
print(f"reliability tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)
PY

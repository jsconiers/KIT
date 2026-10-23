#!/bin/bash
# Tests the run and cost alerts (shared/morning/run_alerts.py, shared/bin/kit-alerts): a run type
# failing RUN_FAIL_STREAK times running, the stale windows (RUN_WINDOW_<MODE>), the cost warning,
# stop, and spike rules, one owner queue item per outage (or per level per month) through
# `todo work`, the dashboard banners, clearing on success or at the month's end, and that a bad log
# or ledger never fails the run. Synthetic logs and ledgers in a throwaway folder; no model, no
# connector, nothing real is touched. Ends with run.sh wired end to end with a fake claude.
#   bash tests/test_run_alerts.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'chmod -R u+rw "$S" 2>/dev/null; rm -rf "$S"' EXIT
export HOME="$S/home"
KIT="$HOME/Claude/Agents/kit"; export KIT_DIR="$KIT"
mkdir -p "$KIT/briefs" "$KIT/.install/logs" "$KIT/.install/shared/morning"
python3 - "$HERE" "$KIT" <<'PY'
import datetime as dt, json, os, pathlib, re, subprocess, sys
here, kit = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
logs, briefs = kit / ".install/logs", kit / "briefs"
cfg = kit / ".install/shared/morning/config"
Q = kit / "QUEUE.md"
RA = here / "shared/morning/run_alerts.py"
P = F = 0

def ok(cond, name, detail=""):
    global P, F
    if cond: P += 1; print("ok  ", name)
    else: F += 1; print("FAIL", name, str(detail)[:400])

def config(text):
    cfg.write_text('OWNER_NAME="Alex"\n' + text)

def reset_queue():
    Q.write_text("# Queue\n\n## Alex\n\n- [ ] **Existing item** (added 01-Oct-2026)\n\n## Kit\n\n## Waiting on others\n\n## Done\n")

def stamp(t):
    return t.strftime("%a %b %d %H:%M:%S EDT %Y")

def run_log(mode, t, good=True):
    lines = [f"== {stamp(t)} start {mode} ", f"== {stamp(t + dt.timedelta(seconds=60))} end {mode} rc={0 if good else 1}",
             "== delivered" if good else "== sent failure notice"]
    with (logs / f"{t:%Y-%m-%d}.log").open("a") as f:
        f.write("\n".join(lines) + "\n")

def alerts(now, *extra, env=None):
    r = subprocess.run([sys.executable, str(RA), "--kit", str(kit), "--now", now, "--out", str(briefs / "alerts.txt"),
                        "--no-dashboard", *extra], capture_output=True, text=True, env=dict(os.environ, **(env or {})))
    return r

def state():
    try:
        return json.loads((briefs / "alerts.json").read_text())["alerts"]
    except Exception:
        return {}

def items(pat):
    return len(re.findall(r"^- \[ \] \*\*" + pat, Q.read_text(), re.M))

def banner():
    import importlib.util
    spec = importlib.util.spec_from_file_location("dash", here / "shared/dashboard.py")
    d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
    return d.alerts_banner()

def clear_logs():
    for p in logs.iterdir():
        if p.is_file(): p.unlink()

config("")
reset_queue()
D = dt.datetime

# ---- two consecutive failures -> one item and a banner ------------------------------------------
run_log("worklist", D(2026, 10, 19, 9, 0), good=False)
r = alerts("2026-10-19T09:10")
ok(r.returncode == 0 and items("Fix Kit's worklist") == 0 and not state(), "one failure: nothing raised", r.stderr)
run_log("worklist", D(2026, 10, 20, 9, 0), good=False)
r = alerts("2026-10-20T09:10")
ok(items(re.escape("Fix Kit's worklist run, failing since 19-Oct-2026 (kit-reliability)") + r"\*\* \[work\]") == 1,
   "two failures in a row: one [work] queue item for the owner", Q.read_text())
sec = Q.read_text().split("## Alex")[1].split("## ")[0]
ok("Fix Kit's worklist" in sec, "the item sits in the owner's section", sec)
ok(re.search(r"^  20-Oct-2026: worklist run failed 2 times running since Mon 19-Oct 09:01\. Kit clears its alert", Q.read_text(), re.M),
   "the item has a detail line with the reason", Q.read_text())
a = state().get("run:worklist", {})
ok(a.get("streak") == 2 and a.get("since") == "2026-10-19" and a.get("queued"), "alert recorded (streak, since, queued)", a)
b = banner()
ok('class="banner" role="alert"' in b and "Scheduled run" in b and "worklist: failed 2 times running" in b,
   "dashboard: red Scheduled run banner", b)
txt = (briefs / "alerts.txt").read_text()
ok(txt.startswith("Run alert: worklist failed 2 times running") and txt.count("\n") == 1, "brief: one line per open alert", txt)
r = alerts("2026-10-20T17:40")
run_log("worklist", D(2026, 10, 21, 9, 0), good=False)
alerts("2026-10-21T09:10")
ok(items("Fix Kit's worklist") == 1 and state()["run:worklist"]["streak"] == 3, "third failure: no duplicate, streak 3")
(briefs / "alerts.json").unlink()
alerts("2026-10-21T09:20")
ok(items("Fix Kit's worklist") == 1 and "run:worklist" in state(), "alert file lost, item still open: no duplicate")

# ---- success clears ---------------------------------------------------------------------------------
run_log("worklist", D(2026, 10, 22, 9, 0), good=True)
alerts("2026-10-22T09:10")
ok("run:worklist" not in state() and banner() == "" and (briefs / "alerts.txt").read_text() == "",
   "success: alert, banner, and brief line cleared", state())
ok(re.search(r"^  Recovered 22-Oct-2026: the worklist run succeeded again", Q.read_text(), re.M)
   and re.search(r"^- \[ \] \*\*Fix Kit's worklist.*updated 22-Oct-2026", Q.read_text(), re.M),
   "success: a Recovered line, item stamped and left for the owner", Q.read_text())
# RUN_FAIL_STREAK=3: two failures aren't enough
run_log("worklist", D(2026, 10, 26, 9, 0), good=False); run_log("worklist", D(2026, 10, 27, 9, 0), good=False)
alerts("2026-10-27T09:10", env={"RUN_FAIL_STREAK": "3"})
ok("run:worklist" not in state(), "RUN_FAIL_STREAK=3: two failures don't raise it", state())
run_log("worklist", D(2026, 10, 28, 9, 0), good=True); alerts("2026-10-28T09:10")

# Windows run logs (run.ps1 stamps lines with Get-Date: "10/26/2026 9:00:00 AM")
clear_logs(); (briefs / "alerts.json").unlink(); reset_queue()
for day in (26, 27):
    (logs / f"2026-10-{day}.log").write_text(f"== 10/{day}/2026 9:00:00 AM start eod \n== 10/{day}/2026 9:01:00 AM end eod rc=0\n== sent failure notice\n")
alerts("2026-10-27T09:10")
ok(state().get("run:eod", {}).get("streak") == 2, "run.ps1's Get-Date log stamps are read too", state())

# ---- stale windows ----------------------------------------------------------------------------------
clear_logs(); reset_queue(); (briefs / "alerts.json").unlink()
(logs / "backup.log").write_text(f"== {stamp(D(2026, 10, 15, 12, 30))} backup\nkit-backup: /x/b.tar.gz.enc (3 files, encrypted), checked\n")
alerts("2026-10-17T11:00")
ok("run:backup" not in state(), "backup 47 h ago: inside its 2-day window")
alerts("2026-10-17T13:00")
ok(items(re.escape("Check Kit's backup run, no success since 15-Oct-2026 (kit-reliability)")) == 1
   and "no success since Thu 15-Oct 12:30 (window 2 days)" in state().get("run:backup", {}).get("reason", ""),
   "stale backup (over 2 days): one item and an alert", state())
ok("Scheduled run" in banner() and "backup" in banner(), "stale backup: banner")
with (logs / "backup.log").open("a") as f:
    f.write(f"== {stamp(D(2026, 10, 17, 14, 0))} backup\nkit-backup: /x/b.tar.gz.enc (3 files, encrypted), checked\n")
alerts("2026-10-17T14:05")
ok("run:backup" not in state() and "Recovered 17-Oct-2026: the backup run succeeded again" in Q.read_text(),
   "a backup success clears it", state())
# morning: weekdays, not hours (Mon success; Wed before 08:15 = 1 missed, after = 2 missed)
run_log("morning", D(2026, 10, 16, 7, 50))   # Friday
alerts("2026-10-19T09:00")                     # Monday: 1 weekday missed
ok("run:morning" not in state(), "morning: a weekend doesn't count against the 2-weekday window", state())
run_log("morning", D(2026, 10, 19, 7, 50))
alerts("2026-10-21T07:30")
ok("run:morning" not in state(), "morning: Wednesday before 08:15 counts only Tuesday as missed", state())
alerts("2026-10-21T09:00")
ok("run:morning" in state() and items("Check Kit's morning run, no success since 19-Oct-2026") == 1,
   "morning: Tuesday and Wednesday missed -> stale alert", state())
alerts("2026-10-21T09:05", env={"SKIP_DAYS": "3"})
ok("run:morning" not in state(), "morning: SKIP_DAYS days don't count (and a cleared window clears it)", state())
# sync: hours, from sync.ok and sync.log
(logs / "sync.ok").write_text("2026-10-21T06:00:00\n")
alerts("2026-10-21T07:00")
ok("run:sync" not in state(), "sync: last clean run an hour ago is fine", state())
alerts("2026-10-21T09:00")
ok("run:sync" in state() and "window 2 hours" in state()["run:sync"]["reason"], "sync: no success in 3 hours -> stale", state())
alerts("2026-10-21T09:01", env={"RUN_WINDOW_SYNC": "4"})
ok("run:sync" not in state(), "RUN_WINDOW_SYNC=4: inside the window again, cleared", state())
(logs / "sync.log").write_text("2026-10-21 09:15 sync failed: Outlook isn't running\n2026-10-21 09:15 sync failed: work (outlook): x\n"
                               "2026-10-21 09:30 sync failed: Outlook isn't running\n")
alerts("2026-10-21T09:31", env={"RUN_WINDOW_SYNC": "off"})
ok(state().get("run:sync", {}).get("streak") == 2 and items("Fix Kit's sync run") == 1,
   "sync: two failed runs (two lines in one minute count once) -> failing alert", state())
(logs / "sync.ok").write_text("2026-10-21T09:45:00\n")
alerts("2026-10-21T09:46")
ok("run:sync" not in state(), "sync: a clean run (sync.ok) clears it")
for p in ("sync.ok", "sync.log", "backup.log"): (logs / p).unlink()
clear_logs(); alerts("2026-10-21T10:00")
ok(not state(), "no runs logged: nothing is watched, everything cleared", state())

# ---- cost: projection over warn -> one item; no duplicate; back under clears; month change -------
reset_queue()
config('COST_BUDGET_MONTHLY="100"\nCOST_WARN_PCT="80"\nCOST_STOP_PCT="95"\n')
led = logs / "cost.jsonl"
def ledger(rows):
    led.write_text("".join(json.dumps({"date": f"{d}T08:00:00", "mode": m, "cost_usd": c}) + "\n" for d, m, c in rows))
ledger([(f"2026-10-{d:02d}", "morning", 4.0) for d in range(1, 11)])   # $40 by the 10th: projected $124
alerts("2026-10-10T09:00")
ok(items(re.escape("Review Kit's spend: Oct-2026 projected over the warning level (kit-cost)")) == 1,
   "projection over the warning level: one [work] item", Q.read_text())
a = state().get("cost:warn", {})
ok("projected at $124.00, over $80.00 (80% of the $100.00 budget); $40.00 so far" in a.get("reason", ""), "warn reason", a)
ok("cost:stop" not in state(), "40% used: no stop alert")
ok("Cost" in banner() and "warn: Oct-2026 spend projected" in banner(), "dashboard: red Cost banner", banner())
alerts("2026-10-10T17:00"); alerts("2026-10-11T09:00")
ok(items("Review Kit's spend") == 1, "no duplicate item on later runs")
alerts("2026-10-11T09:05", env={"COST_ALERT_PROJECTION": "1.5"})
ok("cost:warn" not in state() and "back under the warning level" in Q.read_text(),
   "COST_ALERT_PROJECTION=1.5 ($150): projection back under, cleared", state())
# check the item off, then cross again in the same month: banner, but no second item
Q.write_text(Q.read_text().replace("- [ ] **Review Kit's spend", "- [x] **Review Kit's spend"))
alerts("2026-10-11T09:10")
ok("cost:warn" in state() and items("Review Kit's spend") == 0, "same month again: alert back, no second item (once a month)", Q.read_text())
# stop level
ledger([(f"2026-10-{d:02d}", "weekly", 8.0) for d in range(1, 13)])   # $96
alerts("2026-10-12T09:00")
ok("cost:stop" in state() and items(re.escape("Review Kit's spend: Oct-2026 over the stop level")) == 1,
   "spend over the stop level: its own item", state())
ok("96% of the $100.00 budget (stop at 95%)" in state()["cost:stop"]["reason"] and "stop:" in banner(), "stop reason and banner")
txt = (briefs / "alerts.txt").read_text()
ok("Cost alert (stop)" in txt and "Cost alert (warn)" in txt, "brief lines for both levels", txt)
# month change clears everything cost
alerts("2026-11-02T09:00")
ok(not [k for k in state() if k.startswith("cost:")] and "a new month started" in Q.read_text(), "month change clears the cost alerts", state())
ok(banner() == "", "month change: no banner")

# ---- spike rule with no budget -----------------------------------------------------------------
reset_queue(); config("")
ledger([(f"2026-11-{d:02d}", "morning", 1.0) for d in range(2, 16)] + [("2026-11-16", "weekly", 5.0)])
alerts("2026-11-16T09:00")
ok(items(re.escape("Review Kit's spend: cost spike in Nov-2026 (kit-cost)")) == 1
   and "Mon 16-Nov cost $5.00, over 3x the 14-day median of $1.00" in state().get("cost:spike", {}).get("reason", ""),
   "no budget: a day over 3x the 14-day median raises a spike", state())
r = subprocess.run([sys.executable, str(here / "shared/bin/kit-alerts"), "check", "--dry-run", "--now", "2026-11-16T09:00", "--only", "cost"],
                   capture_output=True, text=True, env=dict(os.environ, COST_SPIKE_FACTOR="6"))
ok("nothing open" in r.stdout, "COST_SPIKE_FACTOR=6: no spike (kit-alerts check --dry-run)", r.stdout + r.stderr)
ledger([(f"2026-11-{d:02d}", "morning", 1.0) for d in range(2, 16)] + [("2026-11-16", "weekly", 5.0), ("2026-11-17", "morning", 1.0)])
alerts("2026-11-17T09:00")
ok("cost:spike" not in state(), "the next normal day clears the spike", state())
config('COST_BUDGET_MONTHLY="1000"\n')
ledger([(f"2026-11-{d:02d}", "morning", 1.0) for d in range(2, 16)] + [("2026-11-18", "weekly", 9.0)])
alerts("2026-11-18T09:00")
ok("cost:spike" not in state(), "with a budget set, no spike rule", state())

# ---- kit-alerts show ---------------------------------------------------------------------------
config(""); run_log("eod", D(2026, 11, 17, 17, 30), good=False); run_log("eod", D(2026, 11, 18, 17, 30), good=False)
(briefs / "connectors-alerts.json").write_text(json.dumps({"wiki": {"since": "2026-11-17", "streak": 2, "reason": "health: down"}}))
r = subprocess.run([sys.executable, str(here / "shared/bin/kit-alerts"), "check", "--now", "2026-11-18T17:40"], capture_output=True, text=True)
ok(r.returncode == 0 and "Run alert: eod failed 2 times" in r.stdout, "kit-alerts check recomputes and records", r.stdout + r.stderr)
r = subprocess.run([sys.executable, str(here / "shared/bin/kit-alerts")], capture_output=True, text=True)
ok("Run alert: eod" in r.stdout and "Connector outage: wiki" in r.stdout, "kit-alerts shows run and connector alerts", r.stdout)
r = subprocess.run([sys.executable, str(here / "shared/bin/kit-alerts"), "--json", "--only", "runs"], capture_output=True, text=True)
ok(list(json.loads(r.stdout)["alerts"]) == ["run:eod"], "kit-alerts --json --only runs", r.stdout)

# ---- a bad ledger, log, alert file, or queue never fails the run ----------------------------------
led.write_text("not json\n{\"date\": \"garbage\", \"cost_usd\": \"x\"}\n[1,2]\n")
(logs / "2026-11-19.log").write_text("== Xyz Abc 99 99:99:99 EDT 2026 start morning \n== end morning rc=\x00\n")
(logs / "backup.log").write_text("== garbage backup\n")
(logs / "sync.log").write_text("2026-99-99 99:99 sync failed: x\n")
(briefs / "alerts.json").write_text("{not json")
Q.chmod(0o000)
r = alerts("2026-11-19T09:00")
Q.chmod(0o644)
ok(r.returncode == 0, "bad ledger, logs, alert file, unreadable queue: exit 0", r.stderr)
ok("run_alerts:" in r.stderr, "problems are reported on stderr", r.stderr)
r = subprocess.run([sys.executable, str(RA), "--kit", "/nonexistent/kit", "--out", "/nonexistent/x.txt"], capture_output=True, text=True)
ok(r.returncode == 0, "a missing Kit folder: exit 0", r.stderr)
r = subprocess.run([sys.executable, str(RA), "--bogus-flag"], capture_output=True, text=True)
ok(r.returncode == 0, "a bad argument: exit 0", r.stderr)

print(f"run alerts tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)
PY
rc=$?

# ---- wiring: run.sh, run.ps1, config.example -------------------------------------------------------
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }
RS="$HERE/platform/mac/morning/run.sh"; RP="$HERE/platform/windows/morning/run.ps1"; CE="$HERE/shared/morning/config.example"
grep -q 'run_alerts.py" --kit "$KIT" --no-dashboard' "$RS" && grep -q 'RUN_ALERTS_TIMEOUT:-60' "$RS" && grep -q '^run_alerts$' "$RS" \
  && ok "run.sh calls run_alerts.py at the end of every run, time-limited" || bad "run.sh wiring"
grep -q 'Open alerts (kit-alerts)' "$RS" && ok "run.sh puts open alerts in the morning and weekly prompt" || bad "run.sh prompt"
grep -q 'run_alerts.py' "$RP" && grep -q '"RUN_ALERTS" "on"' "$RP" && grep -q '^Invoke-RunAlerts$' "$RP" && grep -q 'Open alerts (kit-alerts)' "$RP" \
  && ok "run.ps1 parity (end of run, prompt line, RUN_ALERTS)" || bad "run.ps1 wiring"
for k in RUN_ALERTS RUN_ALERTS_TIMEOUT RUN_FAIL_STREAK RUN_WINDOW_MORNING RUN_WINDOW_WEEKLY RUN_WINDOW_SYNC RUN_WINDOW_BACKUP COST_ALERT_PROJECTION COST_SPIKE_FACTOR; do
  grep -q "^$k=" "$CE" || { bad "config.example: $k"; continue; }
done
grep -q '^RUN_FAIL_STREAK="2"' "$CE" && grep -q '^COST_SPIKE_FACTOR="3"' "$CE" && ok "config.example documents the keys and defaults" || bad "config.example defaults"

# ---- run.sh end to end with a fake claude ----------------------------------------------------------
if command -v zsh >/dev/null && command -v perl >/dev/null; then
  K2="$S/h2/Claude/Agents/kit"; M2="$K2/.install/shared/morning"
  mkdir -p "$M2" "$K2/.install/shared/bin" "$K2/.install/logs" "$K2/briefs" "$S/h2/.local/bin"
  cp "$HERE/shared/morning/run_alerts.py" "$HERE/shared/morning/connector_health.py" "$HERE/shared/morning/prompt.md" \
     "$HERE/shared/morning/prompt-worklist.md" "$M2/"
  cp "$HERE/shared/bin/kit-reliability" "$HERE/shared/bin/kit-cost" "$HERE/shared/bin/todo" "$K2/.install/shared/bin/"
  cp "$HERE/shared/kit_queue.py" "$K2/.install/shared/"
  printf 'OWNER_NAME="Alex"\nOUTLOOK_CHECK="off"\nCONNECTOR_CHECK="off"\nDEGRADED_MODE="off"\nRETRY_ON="off"\n' > "$M2/config"
  printf '# Queue\n\n## Alex\n\n## Kit\n\n## Waiting on others\n\n## Done\n' > "$K2/QUEUE.md"
  cat > "$S/h2/.local/bin/claude" <<EOF
#!/bin/bash
printf "%s\\n" "\$@" > "$S/claude-args.txt"
[ -n "\${FAKE_FAIL:-}" ] && exit 3
echo "Kit test" > "$K2/briefs/latest-text.txt"
echo '{"type":"result","result":"done","total_cost_usd":0.01,"usage":{}}'
EOF
  chmod +x "$S/h2/.local/bin/claude"
  run2() { HOME="$S/h2" KIT_DIR="$K2" zsh "$HERE/platform/mac/morning/run.sh" "$1" >/dev/null 2>&1; }
  FAKE_FAIL=1 run2 worklist; FAKE_FAIL=1 run2 worklist
  grep -q "Fix Kit's worklist run, failing since" "$K2/QUEUE.md" && grep -q '"run:worklist"' "$K2/briefs/alerts.json" \
    && ok "run.sh: two failed worklist runs -> queue item and alert" || bad "run.sh end to end: $(cat "$K2/QUEUE.md")"
  run2 morning
  grep -q "Open alerts (kit-alerts)" "$S/claude-args.txt" && grep -q "Run alert: worklist failed 2 times running" "$S/claude-args.txt" \
    && ok "run.sh: the morning prompt names the open alert" || bad "morning prompt: $(grep -c alert "$S/claude-args.txt")"
  printf 'RUN_ALERTS="off"\n' >> "$M2/config"; rm -f "$K2/briefs/alerts.json" "$K2/.install/logs/"*.done
  FAKE_FAIL=1 run2 worklist
  [ ! -f "$K2/briefs/alerts.json" ] && ok "run.sh: RUN_ALERTS=off skips it" || bad "RUN_ALERTS=off"
else
  echo "run.sh end-to-end: skipped (needs zsh and perl)"
fi
# ---- run.ps1 end to end under pwsh (when pwsh and a 'python' command are present) ------------------
if command -v pwsh >/dev/null 2>&1 && command -v python >/dev/null 2>&1; then
  K3="$S/h3/Claude/Agents/kit"; M3="$K3/.install/shared/morning"
  mkdir -p "$M3" "$K3/.install/shared/bin" "$K3/.install/logs" "$K3/briefs" "$S/b3"
  cp "$M2/run_alerts.py" "$M2/connector_health.py" "$M2/prompt.md" "$M2/prompt-worklist.md" "$M3/"
  cp "$K2/.install/shared/bin/kit-reliability" "$K2/.install/shared/bin/kit-cost" "$K2/.install/shared/bin/todo" "$K3/.install/shared/bin/"; cp "$HERE/shared/kit_queue.py" "$K3/.install/shared/"
  printf 'OWNER_NAME="Alex"\nCONNECTOR_CHECK="off"\nDEGRADED_MODE="off"\nRETRY_ON="off"\nDELIVERY="local"\n' > "$M3/config"
  printf '# Queue\n\n## Alex\n\n## Kit\n\n## Waiting on others\n\n## Done\n' > "$K3/QUEUE.md"
  cat > "$S/b3/claude" <<EOF
#!/bin/bash
printf "%s\\n" "\$@" > "$S/claude-args3.txt"
[ -n "\${FAKE_FAIL:-}" ] && exit 3
echo "Kit test" > "$K3/briefs/latest-text.txt"
echo '{"type":"result","result":"done","total_cost_usd":0.01,"usage":{}}'
EOF
  chmod +x "$S/b3/claude"
  run3() { USERPROFILE="$S/h3" HOME="$S/h3" KIT_DIR="$K3" PATH="$S/b3:$PATH" pwsh -NoProfile -File "$HERE/platform/windows/morning/run.ps1" "$1" >/dev/null 2>&1; }
  FAKE_FAIL=1 run3 worklist; FAKE_FAIL=1 run3 worklist
  grep -q "Fix Kit's worklist run, failing since" "$K3/QUEUE.md" && grep -q '"run:worklist"' "$K3/briefs/alerts.json" \
    && ok "run.ps1: two failed worklist runs -> queue item and alert" || bad "run.ps1 end to end: $(tail -5 "$K3/.install/logs/"*.log)"
  run3 morning
  grep -q "Run alert: worklist failed 2 times running" "$S/claude-args3.txt" \
    && ok "run.ps1: the morning prompt names the open alert" || bad "run.ps1 morning prompt"
else
  echo "run.ps1 end-to-end: skipped (needs pwsh and a 'python' command)"
fi
echo "run alerts wiring tests: $pass passed, $fail failed"
[ "$rc" -eq 0 ] && [ "$fail" -eq 0 ]

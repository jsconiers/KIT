#!/bin/bash
# Tests the connector-guard integrity monitor (shared/morning/monitor_guard.py, alert kind "guard" in
# run_alerts.py): installed agents keep all three guard hooks pointing at an existing script, the guard
# settings are readable, the audit folder exists and is writable (probe file removed; permission bits only
# on a dry run), and allowed calls have result records (kit-audit's no-result check). One alert listing
# the problems, one queue item per outage, the brief line, the dashboard banner, kit-alerts --only guard,
# recovery, MONITOR_GUARD=off, and that nothing breaks with no connectors at all. Synthetic Kit folders in
# a throwaway place; no model, no connector, no web, nothing real is touched.
#   bash tests/test_guard_monitor.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'chmod -R u+rwx "$S" 2>/dev/null; rm -rf "$S"' EXIT
export HOME="$S/home"
KIT="$HOME/Claude/Agents/kit"; export KIT_DIR="$KIT"
unset KIT_CONNECTOR_GUARD_CONFIG
mkdir -p "$KIT/briefs" "$KIT/.install/logs" "$KIT/.install/shared/morning" "$KIT/.install/shared/bin" \
         "$KIT/memory/context" "$KIT/.install/kit/agents" "$KIT/agents" "$HOME/.claude/agents"
cp "$HERE/shared/bin/connector-guard" "$KIT/.install/shared/bin/connector-guard"
python3 - "$HERE" "$KIT" "$HOME" "$S" <<'PY'
import datetime as dt, json, os, pathlib, re, shutil, subprocess, sys
here, kit, home, tmp = (pathlib.Path(a) for a in sys.argv[1:5])
briefs = kit / "briefs"
cfg = kit / ".install/shared/morning/config"
Q = kit / "QUEUE.md"
RA = here / "shared/morning/run_alerts.py"
KA = here / "shared/bin/kit-alerts"
GJ = kit / "memory/context/connector-guard.json"
AUDIT = tmp / "audit"
SCRIPT = kit / ".install/shared/bin/connector-guard"
P = F = 0

def ok(cond, name, detail=""):
    global P, F
    if cond: P += 1; print("ok  ", name)
    else: F += 1; print("FAIL", name, str(detail)[:700])

cfg.write_text('OWNER_NAME="Alex"\n')
Q.write_text("# Queue\n\n## Alex\n\n- [ ] **Existing item** (added 01-Oct-2026)\n\n## Kit\n\n## Waiting on others\n\n## Done\n")

def alerts(*extra, env=None):
    args = [sys.executable, str(RA), "--kit", str(kit), "--out", str(briefs / "alerts.txt"), "--no-dashboard",
            "--only", "guard", *extra]
    return subprocess.run(args, capture_output=True, text=True, env=dict(os.environ, **(env or {})), timeout=120)

def state():
    try:
        return json.loads((briefs / "alerts.json").read_text())["alerts"]
    except Exception:
        return {}

def brief():
    try:
        return (briefs / "alerts.txt").read_text()
    except OSError:
        return ""

def items(pat):
    return len(re.findall(r"^- \[ \] \*\*" + pat, Q.read_text(), re.M))

def banner():
    import importlib.util
    spec = importlib.util.spec_from_file_location("dash", here / "shared/dashboard.py")
    d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
    return d.alerts_banner()

def hook(event, arg, name):
    return (f"  {event}:\n    - matcher: \"mcp__.*\"\n      hooks:\n        - type: command\n"
            f"          command: 'python3 \"$HOME/Claude/Agents/kit/.install/shared/bin/connector-guard\" {arg} {name}'\n")

def agent(name, events=(("PreToolUse", "pre"), ("PostToolUse", "post"), ("PostToolUseFailure", "fail"), ("Stop", "stop"))):
    hooks = "hooks:\n" + "".join(hook(e, a, name) for e, a in events) if events else ""
    return (f"---\nname: {name}\ndescription: The {name}.\ndisallowedTools: Write, Edit\nmodel: inherit\n{hooks}---\n\n"
            f"You are the {name}.\n")

ship, live, inst = kit / ".install/kit/agents", kit / "agents", home / ".claude/agents"
for n in ("gateway", "status-reporter"):
    for d in (ship, live, inst):
        (d / f"{n}.md").write_text(agent(n))
for d in (ship, live, inst):
    (d / "librarian.md").write_text(agent("librarian", events=()))

def guard_cfg(**kw):
    c = {"audit_dir": str(AUDIT), "allowed_servers": ["wiki"], "allow_tools": [], "deny_tools": []}
    c.update(kw)
    GJ.write_text(json.dumps(c))

# ---------------------------------------------------------------- nothing configured
GJ.unlink(missing_ok=True)
r = alerts()
st = state()
ok("guard settings missing" in st.get("guard", {}).get("reason", ""), "guarded agents but no connector-guard.json -> alert", st)

# ---------------------------------------------------------------- all good
AUDIT.mkdir()
guard_cfg()
r = alerts()
ok(r.returncode == 0 and "guard" not in state(), "hooks, settings, audit folder, records all fine -> no alert", (state(), r.stderr))
ok(re.search(r"^  Recovered \d\d-[A-Z][a-z]{2}-\d{4}: the connector guard", Q.read_text(), re.M),
   "settings restored -> Recovered line on the queue item", Q.read_text())
ok(not list(AUDIT.iterdir()), "audit probe file removed", list(AUDIT.iterdir()))

# ---------------------------------------------------------------- a hook removed from the installed copy
(inst / "gateway.md").write_text(agent("gateway", events=(("PreToolUse", "pre"), ("PostToolUse", "post"), ("Stop", "stop"))))
Q.write_text("# Queue\n\n## Alex\n\n- [ ] **Existing item** (added 01-Oct-2026)\n\n## Kit\n\n## Waiting on others\n\n## Done\n")
r = alerts()
a = state().get("guard", {})
ok(a.get("problems") == ["gateway: PostToolUseFailure hook missing"], "installed agent lost its fail hook -> listed", (a, r.stderr))
ok(items(r"Restore Kit's connector guard, broken since \d\d-[A-Z][a-z]{2}-\d{4} \(kit-alerts check --only guard\)\*\* \[work\]") == 1,
   "one [work] queue item", Q.read_text())
ok(brief().startswith("Guard alert: 1 problem: gateway: PostToolUseFailure hook missing (on your list;"), "brief line", brief())
b = banner()
ok("<strong>Connector guard</strong>" in b and "PostToolUseFailure" in b, "dashboard banner", b)
alerts()
ok(items(r"Restore Kit's connector guard") == 1, "second run: no duplicate queue item", Q.read_text())
k = subprocess.run([sys.executable, str(KA), "--only", "guard"], capture_output=True, text=True, timeout=60)
ok(k.returncode == 0 and "Guard alert" in k.stdout, "kit-alerts --only guard shows it", k.stdout + k.stderr)

# a second problem joins the same alert, no new queue item
(inst / "status-reporter.md").unlink()
alerts()
a = state().get("guard", {})
ok(a.get("problems") == ["gateway: PostToolUseFailure hook missing", "status-reporter: installed copy missing"]
   and items(r"Restore Kit's connector guard") == 1, "more problems -> one alert listing them, still one item", a)
# an unguarded agent (librarian) never counts
ok("librarian" not in json.dumps(a), "agents shipped without guard hooks are left alone")

# ---------------------------------------------------------------- script missing
for n in ("gateway", "status-reporter"):
    (inst / f"{n}.md").write_text(agent(n))
SCRIPT.rename(SCRIPT.with_name("connector-guard.moved"))
alerts()
a = state().get("guard", {})
ok(len(a.get("problems", [])) == 2 and all("points at a missing script" in p for p in a["problems"])
   and "PreToolUse points at a missing script" in a["problems"][0], "hooks pointing at a missing script", a)
SCRIPT.with_name("connector-guard.moved").rename(SCRIPT)

# ---------------------------------------------------------------- settings unreadable, audit folder problems
GJ.write_text("{ not json")
alerts()
ok("guard settings unreadable" in state().get("guard", {}).get("reason", ""), "unreadable connector-guard.json", state())
guard_cfg(audit_dir=str(tmp / "nowhere"))
alerts()
ok("doesn't exist" in state().get("guard", {}).get("reason", ""), "audit folder missing", state())
guard_cfg()
os.chmod(AUDIT, 0o500)
alerts()
ok("isn't writable" in state().get("guard", {}).get("reason", ""), "audit folder not writable (probe fails)", state())
before = (briefs / "alerts.json").read_text()
r = alerts("--no-track")
ok("isn't writable" in r.stdout and (briefs / "alerts.json").read_text() == before,
   "dry run: permission bits checked, nothing recorded", (r.stdout, r.stderr))
os.chmod(AUDIT, 0o700)
guard_cfg(allowed_servers=[], audit_dir=str(tmp / "nowhere"))
alerts()
ok("guard" not in state(), "no connectors configured -> a missing audit folder isn't a problem", state())
guard_cfg()

# ---------------------------------------------------------------- records: an allowed call with no result
now = dt.datetime.now().astimezone()
log = AUDIT / f"connectors-{now:%Y-%m}.jsonl"
def rec(**kw):
    with open(log, "a") as f:
        f.write(json.dumps(kw) + "\n")
t0 = (now - dt.timedelta(hours=5)).isoformat(timespec="seconds")
rec(time=t0, event="pre", agent="gateway", session="s1", tool="mcp__wiki__get_page", tool_use_id="u1",
    decision="allow", reason="read-only", input={})
r = alerts()
a = state().get("guard", {})
ok(any("no result record" in p and "mcp__wiki__get_page" in p for p in a.get("problems", [])),
   "allowed call older than the threshold with no post/fail -> problem (kit-audit's check)", (a, r.stderr))
alerts(env={"GUARD_NORESULT_HOURS": "8"})
ok("guard" not in state(), "GUARD_NORESULT_HOURS raises the threshold", state())
alerts()
ok("guard" in state(), "back at the default threshold -> open again", state())
rec(time=(now - dt.timedelta(hours=5) + dt.timedelta(seconds=3)).isoformat(timespec="seconds"), event="post",
    agent="gateway", session="s1", tool="mcp__wiki__get_page", tool_use_id="u1", result_bytes=10, is_error=False)

# ---------------------------------------------------------------- recovery and off
alerts()
ok("guard" not in state() and "Guard" not in brief(), "result recorded -> cleared", state())
ok(len(re.findall(r"^  Recovered .*: the connector guard", Q.read_text(), re.M)) >= 2, "Recovered line on each recovery", Q.read_text())
(inst / "gateway.md").unlink()
alerts()
ok("guard" in state(), "broken again -> reopened", state())
alerts(env={"MONITOR_GUARD": "off"})
ok("guard" not in state(), "MONITOR_GUARD=off clears it", state())
ok(not [p for p in AUDIT.iterdir() if p.name.startswith(".guard-probe")], "no probe files left behind", list(AUDIT.iterdir()))

# ---------------------------------------------------------------- no connectors anywhere
bare = home / "bare-kit"
(bare / "agents").mkdir(parents=True)
(bare / "agents/librarian.md").write_text(agent("librarian", events=()))
r = subprocess.run([sys.executable, str(RA), "--kit", str(bare), "--only", "guard", "--no-dashboard"],
                   capture_output=True, text=True, timeout=60)
ok(r.returncode == 0 and r.stdout.strip() == "", "no guarded agents, no settings -> nothing", (r.stdout, r.stderr))
r = subprocess.run([sys.executable, str(here / "shared/morning/monitor_guard.py"), "--kit", str(kit), "--dry-run"],
                   capture_output=True, text=True, timeout=60)
ok(r.returncode == 0 and "gateway: installed copy missing" in r.stdout, "monitor_guard.py runs standalone", r.stdout + r.stderr)

print(f"\n{P} passed, {F} failed")
sys.exit(1 if F else 0)
PY

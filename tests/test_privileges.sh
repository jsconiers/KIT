#!/bin/bash
# Tests kit-audit privileges, the least-privilege review: tools held (tools list, disallowedTools and the
# connectors it leaves reachable, Agent(...) limits) against connector use in the guard's audit log over a
# window; findings for unused connector tools, unguarded connector reach, unrestricted Agent/SendMessage,
# and disallowedTools leaving new servers reachable; "no usage data" for built-ins; Markdown and --json;
# never edits an agent. Synthetic Kit folder in a throwaway place; no model, connector, or web.
#   bash tests/test_privileges.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
export HOME="$S/home"
KIT="$HOME/Claude/Agents/kit"
mkdir -p "$KIT/agents" "$KIT/memory/context" "$S/audit"
unset KIT_CONNECTOR_GUARD_CONFIG
python3 - "$HERE" "$KIT" "$S" <<'PY'
import hashlib, json, os, pathlib, subprocess, sys
here, kit, tmp = (pathlib.Path(a) for a in sys.argv[1:4])
KA = here / "shared/bin/kit-audit"
P = F = 0

def ok(cond, name, detail=""):
    global P, F
    if cond: P += 1; print("ok  ", name)
    else: F += 1; print("FAIL", name, str(detail)[:900])

(kit / "memory/context/connector-guard.json").write_text(json.dumps(
    {"audit_dir": str(tmp / "audit"), "allowed_servers": ["wiki", "tickets"], "allow_tools": [], "deny_tools": []}))
GUARD = ("hooks:\n  PreToolUse:\n    - matcher: \"mcp__.*\"\n      hooks:\n        - type: command\n"
         "          command: 'python3 \"$HOME/Claude/Agents/kit/.install/shared/bin/connector-guard\" pre {n}'\n")
def agent(n, fields, guard=False):
    (kit / "agents" / f"{n}.md").write_text(f"---\nname: {n}\ndescription: The {n}.\n{fields}model: inherit\n"
                                            + (GUARD.format(n=n) if guard else "") + "---\n\nYou are the {n}.\n")
agent("gateway", "disallowedTools: Write, Edit, Bash, Agent, SendMessage\n", guard=True)
agent("tracker", "tools: Read, Grep, mcp__tickets__get_ticket, mcp__wiki\n", guard=True)
agent("writer", "disallowedTools: WebSearch, WebFetch\n")
agent("reader", "tools: Read, Glob, Grep\n")
agent("router", "tools:\n  - Read\n  - Agent(librarian, curator)\n  - SendMessage\n")
agent("sealed", "disallowedTools: Agent, SendMessage, mcp__wiki, mcp__tickets, mcp__*\n")
before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (kit / "agents").glob("*.md")}

log = tmp / "audit" / "connectors-2026-10.jsonl"
recs = [
    {"time": "2026-10-20T10:00:00-04:00", "event": "pre", "agent": "gateway", "session": "s1",
     "tool": "mcp__wiki__get_page", "decision": "allow", "tool_use_id": "a"},
    {"time": "2026-10-20T10:00:02-04:00", "event": "post", "agent": "gateway", "session": "s1",
     "tool": "mcp__wiki__get_page", "tool_use_id": "a", "result_bytes": 10, "is_error": False},
    {"time": "2026-10-20T10:01:00-04:00", "event": "pre", "agent": "gateway", "session": "s1",
     "tool": "mcp__tickets__create_ticket", "decision": "deny", "reason": "looks like a write"},
    {"time": "2026-10-21T10:00:00-04:00", "event": "pre", "agent": "tracker", "session": "s2",
     "tool": "mcp__tickets__get_ticket", "decision": "allow", "tool_use_id": "b"},
    {"time": "2026-06-01T10:00:00-04:00", "event": "pre", "agent": "tracker", "session": "s0",
     "tool": "mcp__wiki__get_page", "decision": "allow", "tool_use_id": "c"},
]
log.write_text("".join(json.dumps(r) + "\n" for r in recs))

def run(*args):
    return subprocess.run([sys.executable, str(KA), "privileges", "--kit-dir", str(kit),
                           "--now", "2026-10-23T09:00:00-04:00", *args], capture_output=True, text=True, timeout=60)

r = run("--json")
ok(r.returncode == 0, "privileges --json exits 0", r.stderr)
d = json.loads(r.stdout)
A = d["agents"]
ok(d["known_servers"] == ["tickets", "wiki"] and d["window_days"] == 90, "known servers and the default window", d["known_servers"])
ok(A["gateway"]["connector_servers"] == ["tickets", "wiki"] and A["gateway"]["any_new_server"]
   and A["gateway"]["holds"].startswith("all tools except Write"), "disallowedTools: every known connector reachable, plus new ones", A["gateway"])
ok(A["gateway"]["used_tools"] == {"mcp__wiki__get_page": 1} and A["gateway"]["denied_tools"] == {"mcp__tickets__create_ticket": 1},
   "usage from allowed calls; denied attempts kept apart", A["gateway"])
ok(A["gateway"]["unused_servers"] == ["tickets"], "a denied write isn't use: tickets unused for the gateway", A["gateway"])
ok(A["tracker"]["connector_servers"] == ["tickets", "wiki"] and not A["tracker"]["any_new_server"]
   and A["tracker"]["connector_tools_listed"] == ["mcp__tickets__get_ticket"], "tools list: servers named, tool-level entries kept", A["tracker"])
ok(A["tracker"]["unused_servers"] == ["wiki"], "a call outside the window doesn't count (wiki unused in 90 days)", A["tracker"])
ok(A["writer"]["connector_usage"].startswith("no usage data: not guarded"), "unguarded agent: no usage data, never 'unused'", A["writer"])
ok(A["reader"]["connector_usage"] == "holds no connector tools" and A["reader"]["builtin_usage"].startswith("no usage data"),
   "built-in tools: no usage data", A["reader"])
ok(A["router"]["reach"]["Agent"] == {"level": "limited", "targets": ["librarian", "curator"]}
   and A["router"]["reach"]["SendMessage"]["level"] == "all", "YAML list tools; Agent(a, b) limited, SendMessage unrestricted", A["router"])
ok(A["sealed"]["connector_servers"] == [] and not A["sealed"]["any_new_server"]
   and A["sealed"]["reach"]["Agent"]["level"] == "none", "connectors and reach disallowed -> none", A["sealed"])
ok(A["writer"]["reach"]["Agent"]["level"] == "all", "disallowedTools without Agent -> unrestricted Agent", A["writer"]["reach"])

checks = {(f["check"], f["agent"]) for f in d["findings"]}
ok(("unused-connectors", "gateway") in checks and ("unused-connectors", "tracker") in checks, "unused connector findings", checks)
ok(("unguarded-connectors", "writer") in checks and ("unguarded-connectors", "reader") not in checks, "unguarded reach finding", checks)
ok(("agent-reach", "writer") in checks and ("agent-reach", "router") in checks and ("agent-reach", "sealed") not in checks
   and ("agent-reach", "gateway") not in checks, "unrestricted Agent/SendMessage findings", checks)
ok(("open-connectors", "gateway") in checks and ("open-connectors", "tracker") not in checks, "disallowedTools leaves new servers open", checks)
ok(all(f.get("suggestion") for f in d["findings"]), "every finding has a suggestion")

r = run("--days", "200", "--json")
ok(json.loads(r.stdout)["agents"]["tracker"].get("unused_servers") == [], "--days widens the window", r.stdout[:300])

r = run()
t = r.stdout
ok(r.returncode == 0 and t.startswith("# Least-privilege review, 23-Oct-2026") and "## Findings" in t and "## By agent" in t
   and "| gateway |" in t and "no usage data" in t and "never edits an agent" in t, "Markdown report", t[:800])
ok("Suggestion: Add mcp__tickets to its disallowedTools" in t, "Markdown suggestion names the unused server", t)
out = tmp / "priv.md"
run("--out", str(out))
ok(out.exists() and out.read_text().startswith("# Least-privilege review"), "--out writes the report")
after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (kit / "agents").glob("*.md")}
ok(before == after, "agents untouched")
ok(not (kit / "briefs").exists(), "privileges writes no audit status")

# no log at all: still a report
log.unlink()
r = run("--json")
d = json.loads(r.stdout)
ok(r.returncode == 0 and d["connector_calls_in_window"] == 0 and d["agents"]["gateway"]["unused_servers"] == ["tickets", "wiki"],
   "no audit log: runs, everything guarded is unused", r.stderr)
r = subprocess.run([sys.executable, str(KA), "privileges", "--days", "0"], capture_output=True, text=True)
ok(r.returncode != 0, "--days 0 is a usage error")
r = subprocess.run([sys.executable, str(KA), "--daily", "--kit-dir", str(kit), "--out-dir", str(tmp / "o")], capture_output=True, text=True)
ok(r.returncode == 0 and (tmp / "o/audit.txt").exists(), "kit-audit --daily still works")

print(f"\n{P} passed, {F} failed")
sys.exit(1 if F else 0)
PY

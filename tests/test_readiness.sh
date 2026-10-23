#!/bin/bash
# Tests doctor.py --readiness, the source of Kit's agent-readiness figures: no known limit, limits, and
# blocked, with causes (setup fields "not set", a missing setup file, the library root, connector state
# from outages, the last check, and credential names, named Kit tools and outside commands), the text and
# --json output, and the one-line "Agent readiness" check in the full report. Synthetic Kit folder in a
# throwaway place; reads only; no model, connector, or web.
#   bash tests/test_readiness.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
export HOME="$S/home"
KIT="$HOME/Claude/Agents/kit"
mkdir -p "$KIT/agents" "$KIT/memory/context" "$KIT/briefs" "$KIT/.install/shared/bin" "$S/library"
unset KIT_CONNECTOR_GUARD_CONFIG DOC_TEST_TOKEN
python3 - "$HERE" "$KIT" "$S" <<'PY'
import importlib.util, json, os, pathlib, subprocess, sys
here, kit, tmp = (pathlib.Path(a) for a in sys.argv[1:4])
ctx = kit / "memory/context"
P = F = 0

def ok(cond, name, detail=""):
    global P, F
    if cond: P += 1; print("ok  ", name)
    else: F += 1; print("FAIL", name, str(detail)[:900])

def agent(n, body, front=""):
    (kit / "agents" / f"{n}.md").write_text(f"---\nname: {n}\ndescription: The {n}.\n{front}model: inherit\n---\n\n{body}\n")

GUARD = ("hooks:\n  PreToolUse:\n    - matcher: \"mcp__.*\"\n      hooks:\n        - type: command\n"
         "          command: 'python3 \"$HOME/Claude/Agents/kit/.install/shared/bin/connector-guard\" pre {n}'\n")
(ctx / "library.md").write_text(f"# Library\n\n- **Library root:** `{tmp}/library/`. Work documents.\n")
(ctx / "writing.md").write_text("# Writing\n\n- **Templates:** DOC-100 template.\n- **Output:** not set. Format.\n"
                                "- **Examples:** none yet.\n")
(ctx / "standards.md").write_text("# Standards\n\n- **Engineering standards:** not set.\n- **Waivers:** `not set`\n")
(ctx / "connectors.md").write_text("# Connectors\n\n- **Systems:** wiki, tickets.\n")
(ctx / "connector-guard.json").write_text(json.dumps({"audit_dir": str(tmp / "audit"), "allowed_servers": ["wiki", "tickets"],
                                                      "credential_env": {"wiki": ["DOC_TEST_TOKEN"]}}))
(kit / ".install/shared/bin/kit-trace").write_text("#!/bin/sh\n")
agent("librarian", "Read memory/context/library.md first.")
agent("writer", "Read `writing.md` and `library.md`. Run kit-trace.")
agent("checker", "Read memory/context/standards.md and library.md. Run kit-nothere.")
agent("gateway", "Read connectors.md and connector-guard.json.", front="disallowedTools: Write\n" + GUARD.format(n="gateway"))
agent("auditor", "Read connectors.md for the callers.", front="tools: Read, Grep\n")
agent("drawer", "Draw with `drawio-nothere-xyz`... and `drawio` if present.")
agent("planner", "Read poc.md first.")
(kit / ".install/kit/memory/context").mkdir(parents=True)
(kit / ".install/kit/memory/context/poc.md").write_text("# POC\n")

spec = importlib.util.spec_from_file_location("doctor", here / "shared/doctor.py")
doc = importlib.util.module_from_spec(spec); spec.loader.exec_module(doc)

env = {"PATH": "/nonexistent"}
r = doc.readiness(kit, env)
A = r["agents"]
ok(r["total"] == 7, "every live agent counted", r["total"])
ok(A["librarian"]["status"] == "ready" and A["librarian"]["setup_files"] == ["library.md"], "librarian: no known limit", A["librarian"])
ok(A["writer"]["status"] == "limited" and A["writer"]["limits"] == [
    {"cause": "setup", "blocking": False, "detail": "writing.md: Output not set"}],
   "writer: one setup field not set; an installed kit tool isn't a limit", A["writer"])
ch = {x["cause"]: x for x in A["checker"]["limits"]}
ok(A["checker"]["status"] == "limited" and ch["setup"]["detail"] == "standards.md: Engineering standards, Waivers not set"
   and ch["tool"]["detail"] == "kit-nothere not installed", "checker: setup fields (plain and backticked) and a missing kit tool", A["checker"])
gw = A["gateway"]["limits"]
ok(A["gateway"]["status"] == "limited" and gw[0]["cause"] == "connector" and "wiki (credential not set: DOC_TEST_TOKEN)" in gw[0]["detail"]
   and "tickets" not in gw[0]["detail"], "gateway: one of two connectors failing by credential name -> limited", gw)
ok(A["auditor"]["status"] == "ready", "auditor: names connectors.md but can't reach a connector -> no connector limit", A["auditor"])
ok(A["drawer"]["status"] == "limited" and A["drawer"]["limits"][0] == {"cause": "command", "blocking": False, "detail": "drawio not on the PATH"},
   "drawer: a named outside command missing from the PATH", A["drawer"])
ok(A["planner"]["status"] == "blocked" and A["planner"]["limits"][0]["cause"] == "setup-missing",
   "planner: a shipped setup file missing from the live folder -> blocked", A["planner"])
ok(r["counts"] == {"ready": 2, "limited": 4, "blocked": 1} and r["summary"] == "7 agents: 2 with no known limit, 4 with limits, 1 blocked",
   "counts and summary line", (r["counts"], r["summary"]))
ok(r["by_cause"]["setup"]["agents"] == ["checker", "writer"] and r["by_cause"]["setup-missing"]["blocking"] == ["planner"]
   and list(r["by_cause"])[0] == "setup", "by cause, largest first, with blocking agents", r["by_cause"])

# credential set by name -> connector fine; history and outages win over credential names
r = doc.readiness(kit, dict(env, DOC_TEST_TOKEN="x"))
ok(r["agents"]["gateway"]["status"] == "ready", "credential variable present -> gateway ready", r["agents"]["gateway"])
(kit / "briefs/connectors-history.jsonl").write_text(
    json.dumps({"date": "2026-10-20", "server": "wiki", "pass": False}) + "\n"
    + json.dumps({"date": "2026-10-22", "server": "wiki", "pass": True}) + "\n"
    + json.dumps({"date": "2026-10-22", "server": "tickets", "pass": False}) + "\n")
r = doc.readiness(kit, env)
ok(r["agents"]["gateway"]["limits"][0]["detail"] == "tickets (failed the check on 2026-10-22)",
   "the latest check result wins over the credential name", r["agents"]["gateway"])
(kit / "briefs/connectors-alerts.json").write_text(json.dumps({"wiki": {"since": "2026-10-21"}, "tickets": {"since": "2026-10-22"}}))
r = doc.readiness(kit, env)
g = r["agents"]["gateway"]
ok(g["status"] == "blocked" and g["limits"][0]["detail"].startswith("all connectors failing:"), "every connector in an outage -> blocked", g)
(ctx / "connector-guard.json").write_text("{bad")
ok(doc.readiness(kit, env)["agents"]["gateway"]["limits"][0]["detail"] == "connector-guard.json unreadable", "unreadable guard settings -> blocked")
(ctx / "connector-guard.json").write_text(json.dumps({"allowed_servers": []}))
ok(doc.readiness(kit, env)["agents"]["gateway"]["status"] == "blocked", "no connectors configured -> gateway blocked")

# library root missing blocks everyone who reads library.md
(ctx / "library.md").write_text("# Library\n\n- **Library root:** `" + str(tmp / "gone") + "/`.\n")
r = doc.readiness(kit, env)
ok(r["agents"]["librarian"]["status"] == "blocked" and "library" in r["by_cause"] and r["by_cause"]["library"]["count"] == 3,
   "library root missing -> blocked, by cause", r["by_cause"].get("library"))
(ctx / "library.md").write_text(f"# Library\n\n- **Library root:** `{tmp}/library/`.\n")

# CLI: text and --json, KIT_DIR override, read-only
before = sorted((p.relative_to(kit).as_posix(), p.stat().st_mtime_ns) for p in kit.rglob("*") if p.is_file())
cli = lambda *a: subprocess.run([sys.executable, str(here / "shared/doctor.py"), "--readiness", *a], capture_output=True, text=True,
                                env=dict(os.environ, KIT_DIR=str(kit), PATH="/usr/bin:/bin"), timeout=60)
t = cli()
ok(t.returncode == 0 and t.stdout.startswith("Agent readiness, ") and "By cause" in t.stdout and "planner" in t.stdout
   and "BLOCKED" in t.stdout, "--readiness text", t.stdout + t.stderr)
j = cli("--json")
d = json.loads(j.stdout)
ok(j.returncode == 0 and d["total"] == 7 and set(d["counts"]) == {"ready", "limited", "blocked"} and "method" in d,
   "--readiness --json", j.stdout[:400])
after = sorted((p.relative_to(kit).as_posix(), p.stat().st_mtime_ns) for p in kit.rglob("*") if p.is_file())
ok(before == after, "nothing written")

# the full report's one-line check
doc.KIT = kit; doc.results.clear(); doc.check_readiness()
ok(doc.results and doc.results[0][1] == "Agent readiness" and doc.results[0][2].startswith("7 agents: ")
   and "doctor.py --readiness" in doc.results[0][2], "full report: Agent readiness line", doc.results)

# no agents: nothing to say
empty = tmp / "empty"; (empty / "agents").mkdir(parents=True)
ok(doc.readiness(empty, env)["total"] == 0, "no agents -> zero, no crash")

print(f"\n{P} passed, {F} failed")
sys.exit(1 if F else 0)
PY

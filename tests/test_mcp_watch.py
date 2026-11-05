#!/usr/bin/env python3
"""Tests for kit-mcp-watch, the long-session token watchdog: the hooks (a failed MCP call that reads as a stale
session or a lapsed sign-in is logged and gets advice to reconnect through /mcp, once per server per session every
30 minutes; normal results and other errors are left alone; nothing credential-like is kept; MCP_WATCH="off"), its
status and brief, and the installer adding its hooks to settings.json (alongside the owner's own, once) and taking
only them out again. Throwaway folders; no model or connector call.

  python3 tests/test_mcp_watch.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-mcp-watch"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-mcp-watch-"))
HOME = TMP / "home"
KIT = HOME / "Claude/Agents/kit"
(KIT / ".install/shared/morning").mkdir(parents=True)
ENV = dict(os.environ, KIT_DIR=str(KIT), HOME=str(HOME), USERPROFILE=str(HOME), PYTHONDONTWRITEBYTECODE="1")
LOG = KIT / ".install/logs/mcp-watch.jsonl"


def hook(event, payload, at="2026-11-05T09:00:00", **env):
    r = subprocess.run([sys.executable, str(TOOL), event], input=json.dumps(payload), capture_output=True, text=True,
                       env=dict(ENV, KIT_NOW=at, **env), timeout=30)
    return r.returncode, r.stdout, r.stderr


def cli(*a, at="2026-11-05T12:00:00"):
    r = subprocess.run([sys.executable, str(TOOL), *a], capture_output=True, text=True, env=dict(ENV, KIT_NOW=at),
                       timeout=30)
    return r.returncode, r.stdout


S1 = "session-aaa"
# The session is first seen at 00:30 (a successful call), then a failure nine hours later.
rc, out, _ = hook("post", {"session_id": S1, "tool_name": "mcp__onenote__list_pages",
                           "tool_response": {"content": [{"type": "text", "text": "x" * 2000}]}}, at="2026-11-05T00:30:00")
ok(rc == 0 and out == "" and not LOG.exists(), "a normal result: nothing said, nothing logged")
rc, out, _ = hook("fail", {"session_id": S1, "tool_name": "mcp__onenote__search_pages",
                           "error": "MCP error -32000: Connection closed"}, at="2026-11-05T09:30:00")
j = json.loads(out) if out else {}
ctx = j.get("hookSpecificOutput", {}).get("additionalContext", "")
ok(rc == 0 and j.get("hookSpecificOutput", {}).get("hookEventName") == "PostToolUseFailure"
   and "onenote connector's session looks stale" in ctx and "/mcp, pick onenote, and choose Reconnect" in ctx,
   "a stale session: advice to reconnect through /mcp", out)
ok("open about 9 hours" in ctx, "a long session is called out", ctx)
recs = [json.loads(x) for x in LOG.read_text().splitlines()]
ok(len(recs) == 1 and recs[0]["kind"] == "stale" and recs[0]["server"] == "onenote" and recs[0]["session"] != S1
   and recs[0]["session_hours"] == 9.0, "it's logged by server, kind, and a hash of the session", recs)
rc, out, _ = hook("fail", {"session_id": S1, "tool_name": "mcp__onenote__get_page",
                           "error": "Not connected"}, at="2026-11-05T09:40:00")
ok(out == "" and len(LOG.read_text().splitlines()) == 2, "within 30 minutes: logged, but not said again")
rc, out, _ = hook("fail", {"session_id": S1, "tool_name": "mcp__onenote__get_page",
                           "error": "Not connected"}, at="2026-11-05T10:15:00")
ok("session looks stale" in out, "after 30 minutes it's said again")

rc, out, _ = hook("fail", {"session_id": "s2", "tool_name": "mcp__jira__search_issues",
                           "error": "HTTP 401 Unauthorized: token expired. Authorization: Bearer abcdefghijklmnop12345 "
                                    "for alex@example.com"})
ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
ok("jira connector's sign-in looks expired" in ctx and "Authenticate" in ctx and "kit-mcp-env" in ctx,
   "a lapsed sign-in: advice to authenticate", ctx)
raw = LOG.read_text()
ok("abcdefghijklmnop12345" not in raw and "alex@example.com" not in raw and "abcdefghijklmnop12345" not in ctx,
   "nothing credential-like or personal is kept or repeated", raw[-400:])
rc, out, _ = hook("post", {"session_id": "s2", "tool_name": "mcp__wiki__get_page",
                           "tool_response": {"isError": True, "content": [{"type": "text", "text": "Session not found"}]}})
ok("wiki connector's session looks stale" in out and '"PostToolUse"' in out, "an isError result is checked too", out)
rc, out, _ = hook("fail", {"session_id": "s2", "tool_name": "mcp__jira__get_issue", "error": "Issue ABC-1 does not exist"})
ok(out == "", "other errors are left alone")
rc, out, _ = hook("post", {"session_id": "s2", "tool_name": "mcp__wiki__search",
                           "tool_response": {"content": [{"type": "text", "text": "Page: How to fix 401 unauthorized errors in our API gateway. " * 20}]}})
ok(out == "", "a long, normal result that mentions an error isn't taken for one")
rc, out, _ = hook("fail", {"session_id": "s2", "tool_name": "Bash", "error": "Not connected"})
ok(out == "", "only MCP tools count")
rc, out, _ = hook("fail", {"tool_name": "mcp__x__y", "error": "Connection closed"}, MCP_WATCH="off")
ok(out == "", 'MCP_WATCH="off": the hooks do nothing')
ok(hook("fail", "not json")[0] == 0, "a hook never fails the call, whatever it's given")

rc, out = cli("status", "--json")
by = json.loads(out)["servers"]
ok(by["onenote"]["stale"] == 3 and by["jira"]["sign-in"] == 1 and by["wiki"]["stale"] == 1, "status counts by server",
   by)
rc, out = cli("brief")
ok(out.startswith("Connector sessions\n") and "onenote: 3 stale-session failures" in out
   and "in a session open 10 hours" in out and "/mcp, pick jira, Authenticate" in out
   and "Text: Connectors: reconnect jira, onenote, wiki" in out, "the brief's section", out)
rc, out = cli("brief", at="2026-11-07T12:00:00")
ok(rc == 0 and out == "", "nothing in the last day: no section")

# ---- the installer's hooks --------------------------------------------------------------------------------------
SET = HOME / ".claude/settings.json"
SET.parent.mkdir(parents=True)
mine = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo mine"}]}
SET.write_text(json.dumps({"hooks": {"PostToolUse": [mine]}, "permissions": {"allow": ["Bash(ls)"]}}))
SETUP = REPO / "shared/kit_setup.py"


def setup(cmd):
    r = subprocess.run([sys.executable, str(SETUP), cmd], capture_output=True, text=True, env=ENV, timeout=60)
    return r.returncode, r.stdout + r.stderr


rc, out = setup("activate")
data = json.loads(SET.read_text())
post = data["hooks"]["PostToolUse"]
cmds = [h["command"] for g in post for h in g["hooks"]]
ok(rc == 0 and mine in post and any("kit-mcp-watch post" in c for c in cmds)
   and any("kit-mcp-watch fail" in h["command"] for g in data["hooks"]["PostToolUseFailure"] for h in g["hooks"]),
   "activate adds the watchdog's hooks beside the owner's own", out)
ok(all(g["matcher"] == "mcp__.*" for g in post if g != mine) and all(c.endswith("|| exit 1") for c in cmds if "kit" in c),
   "they match MCP tools only and can never block a call", post)
setup("activate")
data = json.loads(SET.read_text())
ok(sum("kit-mcp-watch" in h["command"] for e in data["hooks"].values() for g in e for h in g["hooks"]) == 2,
   "activating again doesn't add them twice")
rc, out = setup("deactivate")
data = json.loads(SET.read_text())
ok(rc == 0 and data.get("hooks") == {"PostToolUse": [mine]} and data["permissions"]["allow"] == ["Bash(ls)"],
   "deactivate takes out only Kit's hooks; the owner's stay", data)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nkit-mcp-watch tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)

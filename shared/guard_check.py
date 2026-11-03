#!/usr/bin/env python3
"""guard_check: run each guarded agent's connector-guard hooks the way Claude Code would, and say
whether they really block. The installers (kit_setup.py guardcheck) and doctor.py use it.

  python3 guard_check.py [--agents DIR]     DIR defaults to ~/.claude/agents, the copies Claude Code loads

Claude Code blocks a tool call only when a PreToolUse hook exits 2 or answers "deny"; a hook that
can't start is a non-blocking error, and the call goes ahead. Reading the agent files can't show
that, so for each agent whose frontmatter runs connector-guard this runs its hooks (through
kit_hooks, which follows Claude Code's rules, with /bin/sh or Git Bash on Windows):

  write   a PreToolUse for a write tool (mcp__kit-selftest__create_check) must be blocked
  read    a PreToolUse for a read tool (mcp__kit-selftest__list_checks) must be allowed, unless Kit
          is paused; that shows the guard itself ran, rather than a failure blocking everything
  logged  the guard writes both calls, and the read's result (PostToolUse), to its audit log
  stop    the Stop hook must not exit 2, which would keep the agent from finishing

Each run gets a throwaway guard config (KIT_CONNECTOR_GUARD_CONFIG) whose only allowed server is
kit-selftest and whose audit folder is temporary, so Kit's real audit log is untouched and no
connector is called. An agent that runs connector-guard with Python directly, not through kit-hook,
gets a note: it works only while that Python does. Exit 1 when any agent's hooks fail.
"""
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit_hooks  # noqa: E402

WRITE_TOOL = "mcp__kit-selftest__create_check"
READ_TOOL = "mcp__kit-selftest__list_checks"
HOOK_TIMEOUT = 60


def frontmatter(text):
    m = re.match(r"---\s*\n(.*?)\n---", text or "", re.S)
    return m.group(1) if m else ""


def capped(timeout):
    """A hook's own timeout, at most HOOK_TIMEOUT seconds, so a hung hook can't stall an install."""
    try:
        return min(float(timeout or HOOK_TIMEOUT), HOOK_TIMEOUT)
    except ValueError:
        return HOOK_TIMEOUT


def guard_hooks(text):
    """The agent's hooks, keeping only the commands that run connector-guard; {} when there are none."""
    cfg = kit_hooks.parse_hooks(frontmatter(text))
    out = {}
    for event, entries in cfg.items():
        kept = []
        for e in entries:
            hooks = [dict(h, timeout=capped(h.get("timeout")))
                     for h in e.get("hooks") or [] if "connector-guard" in (h.get("command") or "")]
            if hooks:
                kept.append({"matcher": e.get("matcher"), "hooks": hooks})
        if kept:
            out[event] = kept
    return out


def direct(cfg):
    """True when a connector-guard command runs Python itself instead of going through kit-hook."""
    return any("kit-hook" not in (h.get("command") or "")
               for entries in cfg.values() for e in entries for h in e["hooks"])


def why(outcome):
    if outcome.errors:
        cmd, code, err = outcome.errors[0]
        return f"the hook exited {code}" + (f": {err.splitlines()[0][:160]}" if err else "")
    return "the hook allowed it"


def check_agent(name, text, env=None):
    """{"agent", "problems", "notes"} for one agent file's text."""
    cfg = guard_hooks(text)
    problems, notes = [], []
    tmp = tempfile.mkdtemp(prefix="kit-guard-check-")
    try:
        audit = os.path.join(tmp, "audit")
        conf = os.path.join(tmp, "connector-guard.json")
        with open(conf, "w", encoding="utf-8") as f:
            json.dump({"audit_dir": audit, "allowed_servers": ["kit-selftest"], "allow_tools": [], "deny_tools": []}, f)
        run_env = dict(os.environ if env is None else env, KIT_CONNECTOR_GUARD_CONFIG=conf)
        base = {"session_id": "kit-guard-check", "transcript_path": "", "cwd": tmp,
                "permission_mode": "default", "agent_type": name}
        hooks = kit_hooks.Hooks(cfg, base, env=run_env)
        if cfg.get("PreToolUse"):
            w = hooks.run("PreToolUse", tool=WRITE_TOOL, tool_input={"note": "Kit's guard self-test; never sent"},
                          tool_use_id="kit-guard-check-write")
            if not w.block:
                problems.append(f"a write would go through ({why(w)})")
            r = hooks.run("PreToolUse", tool=READ_TOOL, tool_input={}, tool_use_id="kit-guard-check-read")
            if r.block and "paused" in (r.reason or ""):
                notes.append("Kit is paused, so reads are blocked too")
            elif r.block:
                reason = re.sub(r",? so the call is blocked\.?$", "", r.reason.strip())
                problems.append(f"the guard can't run, so every call is blocked: {reason[:200]}")
            elif not problems:
                post = hooks.run("PostToolUse", tool=READ_TOOL, tool_input={}, tool_use_id="kit-guard-check-read",
                                 tool_response={"content": []}) if cfg.get("PostToolUse") else None
                logged = set()
                for p in pathlib.Path(audit).glob("connectors-*.jsonl"):
                    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                        try:
                            rec = json.loads(line)
                        except ValueError:
                            continue
                        logged.add((rec.get("event"), rec.get("tool_use_id")))
                if not {("pre", "kit-guard-check-write"), ("pre", "kit-guard-check-read")} <= logged:
                    problems.append("the guard ran but didn't log the calls")
                elif post and ("post", "kit-guard-check-read") not in logged:
                    problems.append("the PostToolUse hook didn't log the result" + (f" ({why(post)})" if post.errors else ""))
        else:
            problems.append("no PreToolUse hook runs connector-guard")
        if cfg.get("Stop"):
            s = hooks.run("Stop", stop_hook_active=False, last_assistant_message="")
            if s.block:
                problems.append("the Stop hook exits 2, which keeps the agent from finishing")
        if direct(cfg):
            notes.append("runs connector-guard with Python directly, not through kit-hook")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"agent": name, "problems": problems, "notes": notes}


def check_all(agents_dir=None, env=None):
    """(results, skipped): results for every agent in agents_dir that runs connector-guard; skipped is
    the reason nothing was run (on Windows, no Git Bash), else None."""
    d = pathlib.Path(agents_dir or pathlib.Path.home() / ".claude" / "agents")
    files = sorted(d.glob("*.md")) if d.is_dir() else []
    texts = [(f.stem, f.read_text(encoding="utf-8", errors="replace")) for f in files]
    texts = [(n, t) for n, t in texts if guard_hooks(t)]
    if texts and os.name == "nt" and not kit_hooks.git_bash():
        return [], "Git Bash wasn't found, so the hooks couldn't be run the way Claude Code runs them"
    return [check_agent(n, t, env) for n, t in texts], None


def grouped(results, key="problems"):
    """One line per distinct list of problems (or notes), naming the agents that share it."""
    groups = {}
    for r in results:
        if r[key]:
            groups.setdefault("; ".join(r[key]), []).append(r["agent"])
    return [f"{', '.join(agents)}: {text}" for text, agents in groups.items()]


def summary(results):
    """(the results with problems, a line for each distinct problem)."""
    return [r for r in results if r["problems"]], grouped(results)


def main(argv):
    d = argv[argv.index("--agents") + 1] if "--agents" in argv else None
    results, skipped = check_all(d)
    if skipped:
        print(f"guard check skipped: {skipped}")
        return 0
    if not results:
        print("No agent runs connector-guard.")
        return 0
    for r in results:
        state = "FAIL" if r["problems"] else "ok"
        detail = "; ".join(r["problems"]) or "blocks a write, allows a read, and logs the calls and the result"
        print(f"{state:4}  {r['agent']}: {detail}" + (f" (note: {'; '.join(r['notes'])})" if r["notes"] else ""))
    return 1 if any(r["problems"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

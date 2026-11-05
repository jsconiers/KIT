#!/usr/bin/env python3
"""ticket_watch.py: sets up the morning brief's ticket watcher for run.sh and run.ps1.

With TICKET_WATCH="on" in the config, the weekday morning run has the gateway agent search the service-management
system (ServiceNow, through its connector) for the owner's own tickets, read-only and under the gateway's
connector-guard hooks; the run saves what comes back to briefs/tickets-today.json, and `kit-tickets diff` (no model
or connector call) compares it with yesterday's and writes the brief's "Your tickets" section: new tickets, state
and priority changes, reassignments, updates, and tickets that left the search. This script makes no connector call
and no model call. It checks the settings, works out which connector tools the unattended run may use, and writes
the prompt text to add.

  python3 ticket_watch.py --server NAME [--tools "t1;t2"] [--query TEXT] [--max 40] [--days 14]
                          --timeout SECS [--cost-level ok|warn|stop] [--owner NAME] [--home DIR]
                          [--guard FILE] [--guard-script FILE] [--python python3|python|"py -3"]
                          --prompt FILE --out FILE

Prints "on" and then one permission rule per line (the read-only tools, the Agent tool, and the kit-tickets diff
command), or "skip <reason>". Either way it writes the prompt text to --out: the instructions, or one line telling
Kit to say the ticket check was skipped. The tools are chosen the way the demand refresh chooses them
(demand_refresh.py): TICKET_TOOLS, or the server's entries in connector-guard.json's allow_tools, each kept only if
connector-guard would allow it and its name doesn't read as a write. If the guard can't be loaded, it's skipped (it
fails closed).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demand_refresh as dr  # noqa: E402  (the same tool rules as the weekly demand refresh)

TICKETS_CMD = "{py} ~/Claude/Agents/kit/.install/shared/bin/kit-tickets diff"
SAFE_QUERY = re.compile(r"^[^`\n\r]{0,300}$")


def read_only_tools(a):
    """(reason, tools): reason is empty when there are tools to use."""
    if a.cost_level == "stop":
        return "the monthly budget is at its stop level", []
    if not a.server:
        return "TICKET_SERVER isn't set", []
    if not dr.NAME.match(a.server):
        return "TICKET_SERVER isn't a valid connector name", []
    if a.timeout < 600:
        return "the run's time limit is too short", []
    if not SAFE_QUERY.match(a.query or ""):
        return "TICKET_QUERY has a backtick or a line break, or is over 300 characters", []
    try:
        with open(a.guard, encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return "connector-guard.json can't be read", []
    if a.server not in (cfg.get("allowed_servers") or []):
        return f"'{a.server}' isn't in connector-guard.json's allowed_servers", []
    try:
        guard = dr.load_guard(a.guard_script)
    except Exception:  # noqa: BLE001
        return "connector-guard can't be loaded", []
    gcfg = {"allowed_servers": list(cfg.get("allowed_servers") or []),
            "allow_tools": list(cfg.get("allow_tools") or []),
            "deny_tools": list(cfg.get("deny_tools") or [])}
    names = ([t.strip() for t in a.tools.split(";") if t.strip()] if a.tools.strip()
             else [t for t in gcfg["allow_tools"] if isinstance(t, str)])
    prefix = f"mcp__{a.server}__"
    tools = []
    for t in names:
        if not t.startswith(prefix) or not dr.NAME.match(t[len(prefix):]) or t in tools:
            continue
        try:
            verdict, _ = guard.decide(gcfg, t)
            if any(w in guard.WRITE_WORDS for w in guard.words(t[len(prefix):])):
                verdict = "deny"
        except Exception:  # noqa: BLE001
            verdict = "deny"
        if verdict == "allow":
            tools.append(t)
    if not tools:
        return ("no read-only tools named for it (TICKET_TOOLS, or its entries in connector-guard.json's "
                "allow_tools)"), []
    return "", tools


def main():
    p = argparse.ArgumentParser(description="Set up the morning ticket watcher (no connector call).")
    p.add_argument("--server", default="")
    p.add_argument("--tools", default="")
    p.add_argument("--query", default="")
    p.add_argument("--max", type=int, default=40)
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--timeout", type=int, default=1200)
    p.add_argument("--cost-level", default="ok")
    p.add_argument("--owner", default="the owner")
    p.add_argument("--home", default=os.path.expanduser("~"))
    p.add_argument("--guard", default="")
    p.add_argument("--guard-script", default="")
    p.add_argument("--prompt", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--python", default="python3", choices=["python3", "python", "py -3"],
                   help="how the run calls Python (run.ps1 passes python)")
    a = p.parse_args()
    kit = os.path.join(a.home, "Claude", "Agents", "kit")
    a.guard = a.guard or os.path.join(kit, "memory", "context", "connector-guard.json")
    a.guard_script = a.guard_script or os.path.join(kit, ".install", "shared", "bin", "connector-guard")
    a.max = max(1, min(a.max, 100))
    a.days = max(1, min(a.days, 60))

    reason, tools = read_only_tools(a)
    if not reason:
        try:
            with open(a.prompt, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            reason = "its prompt file is missing"
    if reason:
        text = (f"Ticket watcher: skipped today ({reason}). Add a \"Your tickets\" section with only the line "
                f"\"[work] Not checked today: {reason}.\" Don't call the gateway or any connector for it.")
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"skip {reason}")
        return 0
    cmd = TICKETS_CMD.format(py=a.python)
    subs = {"{{OWNER}}": a.owner, "{{SERVER}}": a.server, "{{TOOLS}}": ", ".join(tools), "{{MAX}}": str(a.max),
            "{{DAYS}}": str(a.days), "{{TICKETS_CMD}}": cmd,
            "{{QUERY}}": a.query.strip() or "tickets where {{OWNER}} is the caller, the requester, or the assignee"}
    for k, v in subs.items():
        text = text.replace(k, v)
    text = text.replace("{{OWNER}}", a.owner)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")
    print("on")
    for rule in tools + ["Agent", f"Bash({cmd})", f"Bash({cmd} *)"]:
        print(rule)
    return 0


if __name__ == "__main__":
    sys.exit(main())

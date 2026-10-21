#!/usr/bin/env python3
"""demand_refresh.py: sets up the weekly review's demand refresh for run.sh and run.ps1.

With DEMAND_REFRESH="on" in the config, the Monday weekly review has the demand tracker re-check
the demands already in its register through its connector (read-only, under its connector-guard
hooks), record what changed in the register and LOG.md, and give the review a "Demands: what
changed" section. This script makes no connector call and no model call. It checks the settings,
works out which connector tools the unattended run may use, and writes the prompt text to add.

  python3 demand_refresh.py --server NAME [--tools "t1;t2"] --register-dir DIR --timeout SECS
                            [--cost-level ok|warn|stop] [--max 25] [--min-left 10] [--owner NAME]
                            [--home DIR] [--guard FILE] [--guard-script FILE] --prompt FILE --out FILE

Prints "on" and then one permission rule per line (the tools, the Agent tool, and Edit on the
register folder), or "skip <reason>". Either way it writes the prompt text to --out: the refresh
instructions, or one line telling Kit to note the skip in the review.

Tools: --tools (full names, mcp__<server>__<tool>, semicolon-separated), or, when empty, that
server's entries in connector-guard.json's allow_tools. Every tool must belong to --server, and the
server must be in allowed_servers. A tool is kept only if connector-guard itself would allow it
(its decide() rule, loaded from --guard-script) and its name doesn't read as a write, so a write
tool never reaches the run's allowed tools. If the guard can't be loaded, the refresh is skipped
(it fails closed).
"""
import argparse
import importlib.machinery
import importlib.util
import json
import os
import re
import sys

NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
BAD_PATH = re.compile(r"[()*?\[\]\n\r\"'`;]")


def load_guard(path):
    loader = importlib.machinery.SourceFileLoader("kit_connector_guard", path)
    spec = importlib.util.spec_from_loader("kit_connector_guard", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def edit_rules(folder, home):
    """Edit rules for the register folder, spelled the way the runners spell their own rules."""
    fwd = folder.replace("\\", "/").rstrip("/")
    home_fwd = home.replace("\\", "/").rstrip("/")
    rules = []
    if home_fwd and (fwd == home_fwd or fwd.startswith(home_fwd + "/")):
        rules.append(f"Edit(~{fwd[len(home_fwd):]}/**)")
    if re.match(r"^[A-Za-z]:/", fwd):          # Windows: the form run.ps1 uses for its own rules
        rules.append(f"Edit({fwd}/**)")
    elif not rules:                             # outside the home folder: Claude Code's absolute form
        rules.append(f"Edit(/{fwd}/**)")
    return rules


def settings(a):
    """(reason, tools, register folder): reason is empty when the refresh can go ahead."""
    if a.cost_level == "stop":
        return "the monthly budget is at its stop level", [], ""
    if not a.server:
        return "DEMAND_SERVER isn't set", [], ""
    if not NAME.match(a.server):
        return "DEMAND_SERVER isn't a valid connector name", [], ""
    if not a.register_dir:
        return "DEMAND_REGISTER_DIR isn't set", [], ""
    folder = a.register_dir.strip()
    if folder.startswith("~"):
        folder = a.home.rstrip("/\\") + folder[1:]
    if BAD_PATH.search(folder) or not (os.path.isabs(folder) or re.match(r"^[A-Za-z]:[\\/]", folder)):
        return "DEMAND_REGISTER_DIR must be a plain full path", [], ""
    if a.timeout <= a.min_left * 60:
        return "the run's time limit is too short", [], ""
    try:
        with open(a.guard, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return "connector-guard.json can't be read", [], ""
    if a.server not in (cfg.get("allowed_servers") or []):
        return f"'{a.server}' isn't in connector-guard.json's allowed_servers", [], ""
    try:
        guard = load_guard(a.guard_script)
    except Exception:
        return "connector-guard can't be loaded", [], ""
    gcfg = {"allowed_servers": list(cfg.get("allowed_servers") or []),
            "allow_tools": list(cfg.get("allow_tools") or []),
            "deny_tools": list(cfg.get("deny_tools") or [])}
    if a.tools.strip():
        names = [t.strip() for t in a.tools.split(";") if t.strip()]
    else:
        names = [t for t in gcfg["allow_tools"] if isinstance(t, str)]
    prefix = f"mcp__{a.server}__"
    tools = []
    for t in names:
        if not t.startswith(prefix) or not NAME.match(t[len(prefix):]) or t in tools:
            continue
        try:
            verdict, _ = guard.decide(gcfg, t)
            # The main run isn't under the guard's hooks, so a write-sounding name stays out even
            # when allow_tools lists it.
            if any(w in guard.WRITE_WORDS for w in guard.words(t[len(prefix):])):
                verdict = "deny"
        except Exception:
            verdict = "deny"
        if verdict == "allow":
            tools.append(t)
    if not tools:
        return ("no read-only tools named for it (DEMAND_TOOLS, or its entries in "
                "connector-guard.json's allow_tools)"), [], ""
    return "", tools, folder


def main():
    p = argparse.ArgumentParser(description="Set up the weekly demand refresh (no connector call).")
    p.add_argument("--server", default="")
    p.add_argument("--tools", default="")
    p.add_argument("--register-dir", default="")
    p.add_argument("--timeout", type=int, default=3000)
    p.add_argument("--cost-level", default="ok")
    p.add_argument("--max", type=int, default=25)
    p.add_argument("--min-left", type=int, default=10)
    p.add_argument("--owner", default="the owner")
    p.add_argument("--home", default=os.path.expanduser("~"))
    p.add_argument("--guard", default="")
    p.add_argument("--guard-script", default="")
    p.add_argument("--prompt", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    kit = os.path.join(a.home, "Claude", "Agents", "kit")
    a.guard = a.guard or os.path.join(kit, "memory", "context", "connector-guard.json")
    a.guard_script = a.guard_script or os.path.join(kit, ".install", "shared", "bin", "connector-guard")
    a.max = max(1, a.max)
    a.min_left = max(0, a.min_left)

    reason, tools, folder = settings(a)
    if not reason:
        try:
            with open(a.prompt, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            reason = "its prompt file is missing"
    if reason:
        text = (f"Demand refresh: skipped this week ({reason}). Add a \"Demands: what changed\" section "
                f"to the review with only the line \"Refresh skipped: {reason}.\" Don't call the demand "
                f"tracker or any connector for it.")
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"skip {reason}")
        return 0
    subs = {"{{OWNER}}": a.owner, "{{SERVER}}": a.server, "{{TOOLS}}": ", ".join(tools),
            "{{MAX}}": str(a.max), "{{MIN_LEFT}}": str(a.min_left),
            "{{RUN_MINUTES}}": str(a.timeout // 60), "{{REGISTER_DIR}}": folder.replace("\\", "/")}
    for k, v in subs.items():
        text = text.replace(k, v)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")
    print("on")
    for rule in tools + ["Agent"] + edit_rules(folder, a.home):
        print(rule)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""monitor_guard.py: connector-guard integrity, an alert kind for run_alerts.py (kind "guard").

  python3 monitor_guard.py [--kit DIR] [--dry-run]

The connector guard only protects and logs a connector call when three things hold: the agent Claude
Code loads still runs the guard's hooks, the guard can read its settings, and it can write its audit
log. This monitor checks all three, plus the log itself:

  hooks     For each agent whose shipped copy (.install/kit/agents, or agents/ when there's no shipped
            package) carries connector-guard hooks in its frontmatter, the INSTALLED copy in
            ~/.claude/agents must still have all three: PreToolUse (pre), PostToolUse (post), and
            PostToolUseFailure (fail), each a command that runs connector-guard with that event,
            pointing at a connector-guard script that exists ($HOME and ~ are expanded).
  settings  connector-guard.json (KIT_CONNECTOR_GUARD_CONFIG, else memory/context/) is readable JSON
            with an allowed_servers list. Checked when any agent is guarded or the file exists.
  audit dir When connectors are configured (allowed_servers isn't empty), the guard's audit_dir
            exists and is writable: a temporary file is created there and removed at once. On a dry
            run (kit-alerts check --dry-run) only the permission bits are checked, so nothing is
            written.
  records   Allowed connector calls with no result record (no post or fail line), older than
            GUARD_NORESULT_HOURS (default: open_session_hours in audit.md, else 2), in the last
            GUARD_WINDOW_DAYS (2). This is kit-audit's own "no-result" check, reused; an unreadable
            audit log counts too.

One alert ("guard") lists every problem; run_alerts adds one [work] item per outage, the dashboard
shows a red "Connector guard" banner, the brief gets one line, and the alert clears (with a Recovered
line on the queue item) when every check passes again. MONITOR_GUARD="off" turns it off. Never edits
an agent, the settings, or the log; never calls a connector; never fails a run.
"""
import argparse
import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.dirname(HERE)
HOOKS = (("PreToolUse", "pre"), ("PostToolUse", "post"), ("PostToolUseFailure", "fail"))
GUARD_ARG = re.compile(r"connector-guard[\"']?\s+(pre|post|fail|stop)\b")
SCRIPT = re.compile(r"""["']?((?:\$\{HOME\}|\$HOME|~|/)[^"'\s]*connector-guard)["']?""")


def read(path):
    try:
        return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def frontmatter(text):
    m = re.match(r"---\s*\n(.*?)\n---", text or "", re.S)
    return m.group(1) if m else ""


def hook_commands(fm, event):
    """The command lines under one hook event in an agent's frontmatter (YAML read by indentation)."""
    lines = fm.splitlines()
    out = []
    for i, ln in enumerate(lines):
        m = re.match(rf"^(\s*){event}:\s*$", ln)
        if not m:
            continue
        indent = len(m.group(1))
        for nxt in lines[i + 1:]:
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                break
            c = re.search(r"\bcommand:\s*(.+)$", nxt)
            if c:
                out.append(c.group(1).strip())
    return out


def guard_hooks(text):
    """{event: [connector-guard commands run with that event's argument]} for one agent file."""
    fm = frontmatter(text)
    out = {}
    for event, arg in HOOKS:
        cmds = [c for c in hook_commands(fm, event) if (GUARD_ARG.search(c) or [None, None])[1] == arg]
        if cmds:
            out[event] = cmds
    return out


def script_path(cmd, home):
    m = SCRIPT.search(cmd)
    if not m:
        found = shutil.which("connector-guard")
        return found
    p = m.group(1).replace("${HOME}", str(home)).replace("$HOME", str(home))
    if p.startswith("~"):
        p = str(home) + p[1:]
    return p


def shipped_agents(kit):
    sd = pathlib.Path(kit) / ".install" / "kit" / "agents"
    if not sd.is_dir():
        sd = pathlib.Path(kit) / "agents"
    return sorted(sd.glob("*.md")) if sd.is_dir() else []


def guarded(kit):
    """Agent names whose shipped copy carries any connector-guard hook (pre, post, or fail)."""
    return [f.stem for f in shipped_agents(kit) if guard_hooks(read(f) or "")]


def hook_problems(kit, home):
    """{agent: [what's wrong]} for the installed copies of the guarded agents."""
    out = {}
    for name in guarded(kit):
        inst = pathlib.Path(home) / ".claude" / "agents" / f"{name}.md"
        text = read(inst)
        if text is None:
            out[name] = ["installed copy missing"]
            continue
        have = guard_hooks(text)
        bad = []
        for event, _arg in HOOKS:
            cmds = have.get(event)
            if not cmds:
                bad.append(f"{event} hook missing")
                continue
            paths = [script_path(c, home) for c in cmds]
            if not any(p and os.path.isfile(p) for p in paths):
                where = next((p for p in paths if p), "no path")
                bad.append(f"{event} points at a missing script ({where})")
        if bad:
            out[name] = bad
    return out


def guard_config_path(kit):
    return os.environ.get("KIT_CONNECTOR_GUARD_CONFIG") or os.path.join(kit, "memory", "context",
                                                                         "connector-guard.json")


def config_problems(kit, any_guarded, dry_run):
    """([problems], config or None)."""
    path = guard_config_path(kit)
    if not os.path.exists(path):
        return ([f"guard settings missing ({path}), so the guard blocks every connector call"]
                if any_guarded else []), None
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict) or not isinstance(cfg.get("allowed_servers"), list):
            raise ValueError("allowed_servers isn't a list")
    except (OSError, ValueError) as ex:
        return [f"guard settings unreadable ({os.path.basename(path)}: {str(ex)[:80]}), so the guard blocks "
                "every connector call"], None
    probs = []
    if cfg["allowed_servers"]:
        audit = os.path.expanduser(cfg.get("audit_dir") or os.path.join(kit, "audit"))
        if not os.path.isdir(audit):
            probs.append(f"audit folder {audit} doesn't exist (a cloud-synced folder that stopped syncing?), "
                         "so the guard can't log and blocks calls")
        elif dry_run:
            if not os.access(audit, os.W_OK | os.X_OK):
                probs.append(f"audit folder {audit} isn't writable, so the guard blocks calls")
        else:
            try:
                fd, tmp = tempfile.mkstemp(prefix=".guard-probe-", dir=audit)
                os.close(fd)
                os.remove(tmp)
            except OSError as ex:
                probs.append(f"audit folder {audit} isn't writable ({ex.strerror or ex}), so the guard blocks calls")
    return probs, cfg


def load_audit():
    path = os.path.join(SHARED, "bin", "kit-audit")
    loader = importlib.machinery.SourceFileLoader("kit_audit_for_guard", path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def record_problems(kit, cfg, now):
    """kit-audit's no-result and unreadable-log findings over the recent window, as problem strings."""
    ka = load_audit()
    aware = now if now.tzinfo else now.astimezone()
    args = argparse.Namespace(kit_dir=kit, out_dir=None, now=aware.isoformat(), log_dir=None)
    audit = ka.Audit(args)
    audit.load_setup()
    hours = cfg.number("GUARD_NORESULT_HOURS", 0.0) if cfg else 0.0
    if hours > 0:
        audit.th["open_session_hours"] = hours
    days = (cfg.number("GUARD_WINDOW_DAYS", 2.0) if cfg else 2.0) or 2.0
    audit.read_logs()
    audit.findings = []
    audit.check_window(aware - dt.timedelta(days=days), aware)
    out = []
    for f in audit.findings:
        if f["check"] == "no-result":
            detail = f.get("detail", "")
            out.append(f"{f.get('count', '?')} allowed connector call(s) with no result record in the last "
                       f"{days:g} days ({detail.split('.')[0]}): the result hooks may not be running")
        elif f["check"] == "log-unreadable":
            out.append(f"audit log unreadable: {f.get('detail', '')}")
    return out


def names(items, n=6):
    return ", ".join(items[:n]) + (f" (+{len(items) - n} more)" if len(items) > n else "")


def check(kit, cfg=None, now=None, home=None, dry_run=False):
    """[problem strings], in a stable order."""
    home = home or pathlib.Path.home()
    now = now or dt.datetime.now()
    probs = []
    hooks = hook_problems(kit, home)
    for agent in sorted(hooks):
        probs.append(f"{agent}: " + "; ".join(hooks[agent]))
    cp, gcfg = config_problems(kit, bool(guarded(kit)), dry_run)
    probs += cp
    if gcfg is not None and gcfg.get("allowed_servers"):
        try:
            probs += record_problems(kit, cfg, now)
        except Exception as ex:  # noqa: BLE001  (kit-audit missing or broken: say so, don't fail)
            probs.append(f"audit records not checked (kit-audit: {str(ex)[:80]})")
    return probs


def problems(kit, cfg=None, now=None, deadline=None, home=None):
    """{key: problem} for run_alerts.track_monitor. Never raises past run_alerts' guard."""
    probs = check(kit, cfg, now, home, dry_run=bool(getattr(cfg, "dry_run", False)))
    if not probs:
        return {}
    reason = f"{len(probs)} problem{'s' if len(probs) != 1 else ''}: " + "; ".join(probs)
    return {"guard": {
        "problems": probs, "reason": reason,
        "title": "Restore Kit's connector guard, broken since {since} (kit-alerts check --only guard)",
        "detail": f"{{today}}: {reason}. Installed agents: copy the live ones with doctor.py --fix-agents "
                  "(and compare the live ones with kit-alerts drift --diff <agent>); settings and audit folder: "
                  "see memory/context/connectors.md. Kit clears its alert when every guard check passes.",
        "recovered": "Recovered {today}: the connector guard's hooks, settings, audit folder, and records check "
                     "out again; check this off when you're satisfied."}}


def line(a):
    """The brief line for an open (or previewed) guard alert."""
    listed = "" if a.get("preview") else "on your list; "
    return (f"Guard alert: {a.get('reason')} ({listed}connector calls may be unguarded or unlogged; "
            "see kit-alerts check --only guard).")


def main(argv):
    ap = argparse.ArgumentParser(prog="monitor_guard.py")
    ap.add_argument("--kit", default=os.environ.get("KIT_DIR", os.path.expanduser("~/Claude/Agents/kit")))
    ap.add_argument("--dry-run", action="store_true", help="don't write the audit-folder probe file")
    a = ap.parse_args(argv)
    probs = check(a.kit, dry_run=a.dry_run)
    print("\n".join(f"guard: {p}" for p in probs) or "guard: all checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

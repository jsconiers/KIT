#!/usr/bin/env python3
"""Kit's health check.

  python3 ~/Claude/Agents/kit/.install/doctor.py             full report
  python3 ~/Claude/Agents/kit/.install/doctor.py --brief     problems only, one per line
  python3 ~/Claude/Agents/kit/.install/doctor.py --servers   also start each MCP server (slow)

Exits 1 when anything fails. Warnings don't fail the check.
"""
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys

HOME = pathlib.Path.home()
KIT = HOME / "Claude/Agents/kit"
MEM = KIT / "memory"
LOGS = KIT / ".install/morning/logs"
LABELS = ["morning", "open", "weekly", "sync", "scalper", "guard", "journal"]
ORDER_TOOLS = [
    "mcp__robinhood-local__rh_place_order", "mcp__tastytrade__place_order",
    "mcp__tastytrade__place_complex_order", "mcp__tastytrade__replace_order",
    "mcp__tastytrade__cancel_order", "mcp__tastytrade__cancel_all_orders",
    "mcp__tastytrade__cancel_complex_order", "mcp__alpaca",
]
SECRET_PATTERNS = [
    (r"\bgh[pousr]_[A-Za-z0-9]{20,}", "GitHub token"),
    (r"\bsk-[A-Za-z0-9_-]{20,}", "API key"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS key"),
    (r"\bxox[abprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "Social Security number"),
    (r"\b\d{12,19}\b", "account or card number"),
]
results = []


def add(level, name, detail=""):
    results.append((level, name, detail))


def check(cond, name, good, bad, level="FAIL"):
    add("ok", name, good) if cond else add(level, name, bad)


def label(name):
    return f"com.{os.environ.get('USER', 'user')}.kit.{name}"


def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


def check_import():
    p = HOME / ".claude/CLAUDE.md"
    t = p.read_text() if p.exists() else ""
    check("@~/Claude/Agents/kit/KIT.md" in t, "Kit loads in Claude Code",
          "import line present", "import line missing from ~/.claude/CLAUDE.md; re-run the installer")


def check_settings():
    p = HOME / ".claude/settings.json"
    try:
        s = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        add("FAIL", "Claude Code settings", f"can't read {p}: {e}")
        return
    perm = s.get("permissions", {})
    allow, ask = perm.get("allow", []), perm.get("ask", [])
    check(any(r.startswith("Read(") and "Claude/Agents/kit" in r for r in allow),
          "Kit can read its notes", "allowed", "no Read rule for Kit's folder")
    check(any(r.startswith("Edit(") and "Claude/Agents/kit/memory" in r for r in allow),
          "Kit can save notes", "allowed", "no Edit rule for Kit's memory")
    loose = [t for t in ORDER_TOOLS if t in allow]
    check(not loose, "Order tools ask first", "none pre-approved",
          "pre-approved without asking: " + ", ".join(loose))
    missing = [t for t in ORDER_TOOLS if t not in ask]
    if missing:
        add("warn", "Order tools on ask", "no explicit ask rule for: " + ", ".join(missing))


def check_index():
    problems, orphans = [], []
    listed = set()
    for ix in [MEM / "INDEX.md", MEM / "personal/INDEX.md"]:
        if not ix.exists():
            problems.append(f"{ix.relative_to(KIT)} missing")
            continue
        for path in re.findall(r"^- `([^`]+)`", ix.read_text(), re.M):
            listed.add(path)
            if not (MEM / path).exists():
                problems.append(f"{path} is indexed but missing")
    for f in MEM.rglob("*.md"):
        rel = f.relative_to(MEM).as_posix()
        if rel not in listed and rel not in ("INDEX.md", "personal/INDEX.md"):
            orphans.append(rel)
    check(not problems, "Memory index", "every indexed note exists", "; ".join(problems))
    if orphans:
        add("warn", "Unindexed notes", ", ".join(sorted(orphans)))


def check_jobs():
    uid = os.getuid()
    for name in LABELS:
        plist = HOME / f"Library/LaunchAgents/{label(name)}.plist"
        if not plist.exists():
            continue
        code, _ = run(["launchctl", "print", f"gui/{uid}/{label(name)}"])
        check(code == 0, f"Scheduled {name} run", "loaded",
              f"not loaded; run: launchctl bootstrap gui/$(id -u) {plist}")


def check_runs():
    now = dt.datetime.now()
    issues = []
    for back in range(0, 4):
        day = (now - dt.timedelta(days=back)).date()
        log = LOGS / f"{day:%Y-%m-%d}.log"
        if not log.exists():
            continue
        mode = None
        for line in log.read_text(errors="ignore").splitlines():
            m = re.match(r"== .* start (\w+)?\s*(\[Test\])?", line)
            if m:
                mode = (m.group(1) or "morning") + (" test" if m.group(2) else "")
            elif line.startswith("== text failed") and mode:
                issues.append(f"{day:%a %d-%b} {mode}: text didn't send")
            elif line.startswith("== sent failure notice") and mode:
                issues.append(f"{day:%a %d-%b} {mode}: run didn't finish")
    check(not issues, "Recent runs", "texts delivered", "; ".join(issues[:4]), level="warn")
    unsent = sorted((KIT / "briefs").glob("unsent-*.txt"))
    if unsent:
        add("warn", "Unsent texts", ", ".join(p.name for p in unsent))
    if now.weekday() < 5 and now.hour * 60 + now.minute > 8 * 60 + 15:
        today = LOGS / f"{now:%Y-%m-%d}.log"
        ran = today.exists() and re.search(r"start (morning|\s)", today.read_text(errors="ignore"))
        check(bool(ran), "Today's morning run", "ran", "hasn't run yet; was the Mac asleep?", "warn")


def check_tokens():
    tok = HOME / ".etrade/tokens.pickle"
    if tok.exists():
        midnight = dt.datetime.combine(dt.date.today(), dt.time())
        fresh = dt.datetime.fromtimestamp(tok.stat().st_mtime) >= midnight
        check(fresh, "E*TRADE login", "renewed today",
              "token is from before midnight, so the SPX print stays down until you renew it",
              "warn")


def check_secrets():
    hits = []
    targets = list(MEM.rglob("*.md")) + [KIT / "QUEUE.md", KIT / "STATUS.md"]
    for f in targets:
        if not f.exists():
            continue
        for n, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
            for pat, what in SECRET_PATTERNS:
                if re.search(pat, line):
                    hits.append(f"{f.relative_to(KIT)}:{n} looks like a {what}")
    check(not hits, "No secrets in Kit's notes", "clean", "; ".join(hits[:5]))


def check_permissions():
    mode = KIT.stat().st_mode & 0o777
    check(mode & 0o077 == 0, "Kit's folder is private", "only you can read it",
          f"permissions are {oct(mode)}; run: chmod 700 ~/Claude/Agents/kit", "warn")


def check_agents():
    src = KIT / "agents"
    if not src.exists():
        return
    drift = []
    for f in src.glob("*.md"):
        dest = HOME / ".claude/agents" / f.name
        if not dest.exists() or dest.read_text() != f.read_text():
            drift.append(f.stem)
    check(not drift, "Kit's staff installed", "all subagents current",
          "out of date in ~/.claude/agents: " + ", ".join(drift)
          + " (run: python3 ~/Claude/Agents/kit/.install/doctor.py --fix-agents)", "warn")


def fix_agents():
    dest = HOME / ".claude/agents"
    dest.mkdir(parents=True, exist_ok=True)
    for f in (KIT / "agents").glob("*.md"):
        (dest / f.name).write_text(f.read_text())
    print("Copied Kit's staff into ~/.claude/agents")


def check_git():
    if not (KIT / ".git").exists():
        add("warn", "Kit's history", "no local git repo in ~/Claude/Agents/kit")
        return
    code, out = run(["git", "-C", str(KIT), "log", "-1", "--format=%ct"])
    if code == 0 and out.strip().isdigit():
        age = (dt.datetime.now() - dt.datetime.fromtimestamp(int(out.strip()))).days
        check(age <= 3, "Kit's history", f"last saved {age} day(s) ago",
              f"last saved {age} days ago", "warn")


def check_mail():
    tool = HOME / ".local/bin/kitmail"
    if not tool.exists() or run(["pgrep", "-x", "Mail"])[0] != 0:
        return  # don't open Mail just to check it
    code, out = run([str(tool), "accounts"], timeout=60)
    try:
        ok = code == 0 and len(json.loads(out)) > 0
    except Exception:  # noqa: BLE001
        ok = False
    check(ok, "Mail access", "kitmail can read Mail", "kitmail can't read Mail: " + out.strip()[:120], "warn")


def check_calendar():
    tool = HOME / ".local/bin/kitcal"
    if not tool.exists():
        return
    code, out = run([str(tool), "calendars"], timeout=60)
    try:
        ok = code == 0 and len(json.loads(out)) > 0
    except Exception:  # noqa: BLE001
        ok = False
    check(ok, "Calendar access", "kitcal can read your calendars",
          "kitcal can't read your calendars: " + out.strip()[:120], "warn")


def check_servers():
    code, out = run([str(HOME / ".local/bin/claude"), "mcp", "list"], timeout=180)
    bad = [ln.split(":")[0] for ln in out.splitlines() if "✗" in ln or "Failed" in ln]
    check(code == 0 and not bad, "MCP servers", "all connected", "not connecting: " + ", ".join(bad),
          "warn")


def check_guard():
    import json as _json
    import plistlib as _plistlib
    cfgp = HOME / "Claude/MCP/scalper-bot/guard.json"
    if not cfgp.exists():
        return
    cfg = _json.loads(cfgp.read_text())
    armed = False
    try:
        with open(HOME / f"Library/LaunchAgents/{label('guard')}.plist", "rb") as f:
            armed = (_plistlib.load(f).get("EnvironmentVariables") or {}).get("TRAIL_GUARD_ALLOW_LIVE") == "1"
    except Exception:  # noqa: BLE001
        pass
    accts = cfg.get("live_accounts") or []
    live = cfg.get("mode") == "live" and armed and accts
    add("ok", "Trail guard", ("LIVE for " + ", ".join("..." + a[-4:] for a in accts)) if live
        else "shadow mode, no orders")
    logs = sorted((HOME / "Claude/MCP/scalper-bot/logs").glob("guard-2*.log"))
    if logs:
        last = logs[-1]
        fails = sum(1 for line in last.read_text(errors="ignore").splitlines()
                    if "check failed" in line or ": error " in line)
        if fails >= 3:
            add("warn", "Trail guard errors", f"{fails} in {last.name}; run: trail-guard log {last.stem[6:]}")


def main(argv):
    if "--fix-agents" in argv:
        fix_agents()
        return 0
    for fn in (check_import, check_settings, check_index, check_jobs, check_runs, check_tokens,
               check_secrets, check_permissions, check_agents, check_git, check_calendar, check_mail,
               check_guard):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            add("warn", fn.__name__, f"check crashed: {e}")
    if "--servers" in argv:
        check_servers()
    if "--brief" in argv:
        for level, name, detail in results:
            if level != "ok":
                print(f"{level.upper()}: {name}: {detail}")
    else:
        for level, name, detail in results:
            print(f"  {level:<4}  {name}: {detail}")
    return 1 if any(r[0] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Kit's health check.

  python3 ~/Claude/Agents/kit/.install/shared/doctor.py             full report
  python3 ~/Claude/Agents/kit/.install/shared/doctor.py --brief     problems only, one per line
  python3 ~/Claude/Agents/kit/.install/shared/doctor.py --servers   also start each MCP server (slow)
  python3 ~/Claude/Agents/kit/.install/shared/doctor.py --readiness [--json]
                                     agent readiness: no known limit, limits, blocked, and why by cause
                                     (the source for readiness figures in documents; KIT_DIR overrides
                                     the Kit folder). Read-only.

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
LOGS = KIT / ".install/logs"
LABELS = ["morning", "open", "weekly", "worklist", "eod", "meetprep", "backup", "sync", "scalper", "guard", "journal", "preflight", "catchup"]
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
            e = re.match(r"== .* end (\w+) rc=", line)
            if m:
                mode = (m.group(1) or "morning") + (" test" if m.group(2) else "")
            elif e:
                # Delivery lines follow the run that just ended; runs can overlap, so the end line,
                # not the last start line, says whose delivery comes next.
                mode = e.group(1)
            elif line.startswith("== text failed") and mode:
                issues.append(f"{day:%a %d-%b} {mode}: text didn't send")
            elif line.startswith("== sent failure notice") and mode:
                issues.append(f"{day:%a %d-%b} {mode}: run didn't finish")
            elif line.startswith("== delivered") and mode:
                # A later run of the same kind that day succeeded, so drop that day's failure for it.
                issues = [i for i in issues if i != f"{day:%a %d-%b} {mode}: run didn't finish"]
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


def agent_drift(kit=None, home=None):
    """Live agents (kit/agents) missing from or different in ~/.claude/agents, sorted. None when
    Kit has no agents folder. Shared with the drift monitor (shared/morning/monitor_drift.py)."""
    src = pathlib.Path(kit or KIT) / "agents"
    if not src.exists():
        return None
    drift = []
    for f in src.glob("*.md"):
        dest = pathlib.Path(home or HOME) / ".claude/agents" / f.name
        if not dest.exists() or dest.read_text() != f.read_text():
            drift.append(f.stem)
    return sorted(drift)


def check_agents():
    drift = agent_drift()
    if drift is None:
        return
    check(not drift, "Kit's staff installed", "all subagents current",
          "out of date in ~/.claude/agents: " + ", ".join(drift)
          + " (run: python3 ~/Claude/Agents/kit/.install/shared/doctor.py --fix-agents)", "warn")


def check_delivery():
    """How briefs and to-dos are routed (kit-settings), and anything that would stop them."""
    import importlib.machinery, importlib.util
    path = KIT / ".install/shared/bin/kit-settings"
    if not path.exists():
        return
    loader = importlib.machinery.SourceFileLoader("kit_settings", str(path))
    spec = importlib.util.spec_from_loader("kit_settings", loader)
    ks = importlib.util.module_from_spec(spec)
    loader.exec_module(ks)
    cfg = ks.read()
    p, w, split = ks.delivery(cfg)
    tp, tw, tsplit = ks.todos(cfg)
    add("ok", "Delivery", f"personal {p}, work {w}" if split else p)
    add("ok", "To-do sync", f"personal {tp}, work {tw}" if tsplit else tp)
    for msg in ks.problems(cfg):
        add("warn", "Settings", msg + " (see: kit-settings)")


def check_paused():
    marker = KIT / ".install/PAUSED"
    if marker.exists():
        why = (marker.read_text(errors="ignore").splitlines() or ["no reason given"])[0]
        add("warn", "Kit paused", f"{why}; scheduled runs and connector calls are stopped (kit-pause resume)")


def check_outlook():
    """The result of the last Outlook check a run made (kit-outlook writes briefs/outlook.txt)."""
    f = KIT / "briefs/outlook.txt"
    if not f.exists():
        return
    parts = f.read_text(errors="ignore").strip().split(" ", 3)
    if len(parts) < 4:
        return
    status, day, msg = parts[0], parts[1], parts[3]
    if day != dt.date.today().isoformat():
        return   # only today's check counts
    if status in ("ok", "skipped", "not-running"):
        add("ok", "Outlook", msg)
    else:
        add("warn", "Outlook", msg)


def check_holds():
    f = KIT / "memory/context/legal-holds.json"
    try:
        holds = json.loads(f.read_text()) if f.exists() else {}
    except Exception:  # noqa: BLE001
        add("warn", "Legal holds", f"{f} can't be read; treat every project as held until it's fixed")
        return
    if holds:
        add("ok", "Legal holds", "active: " + ", ".join(sorted(holds)) + " (kit-retention holds)")


def check_cost():
    """Scheduled-run spend this month against the budget (kit-cost reads .install/logs/cost.jsonl)."""
    tool = KIT / ".install/shared/bin/kit-cost"
    if not tool.exists():
        return
    try:
        r = subprocess.run([sys.executable, str(tool), "check", "--json"], capture_output=True, text=True, timeout=30)
        st = json.loads(r.stdout)
    except Exception:  # noqa: BLE001
        add("warn", "Cost", "kit-cost check didn't run")
        return
    spend = f"${st['spend_usd']:.2f} this month over {st['runs']} scheduled run(s), projected ${st['projection_usd']:.2f}"
    if st.get("budget_usd"):
        level = "ok" if st["level"] == "ok" else "warn"
        extra = " (non-essential runs are skipping)" if st["level"] == "stop" else ""
        add(level, "Cost", f"{spend}; {st['pct_used']}% of ${st['budget_usd']:.0f} budget{extra} (kit-cost)")
    else:
        add("ok", "Cost", f"{spend}; no budget set (kit-cost)")


def check_version():
    """Installed Kit version, and whether the install matches the repo clone's commit."""
    import json as _json
    try:
        v = _json.loads((KIT / ".install/VERSION.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        add("warn", "Kit version", "not recorded yet (rerun the installer)")
        return
    label = f"{v.get('version')} ({(v.get('commit') or 'unknown')[:7]}), installed {v.get('installed')}"
    repo = pathlib.Path(os.environ.get("KIT_REPO", HOME / "KIT")).expanduser()
    if (repo / ".git").exists():
        code, out = run(["git", "-C", str(repo), "rev-parse", "HEAD"])
        head = out.strip() if code == 0 else ""
        if head and v.get("commit") not in ("unknown", head):
            add("warn", "Kit version", label + f"; the repo clone is at {head[:7]} "
                "(rerun the installer, or kit-update --apply)")
            return
    add("ok", "Kit version", label)


def check_models():
    """Model config (kit-models): valid, and the installed agents match it."""
    import importlib.util
    path = KIT / ".install/shared/kit_models.py"
    if not path.exists():
        return
    spec = importlib.util.spec_from_file_location("kit_models", str(path))
    km = importlib.util.module_from_spec(spec); spec.loader.exec_module(km)
    try:
        cfg = km.load(KIT)
    except km.ConfigError as e:
        add("warn", "Models", f"{e} (see: kit-models check)"); return
    names = sorted(p.stem for p in (KIT / "agents").glob("*.md"))
    errors, warnings = km.check(cfg, names)
    if errors:
        add("warn", "Models", f"{len(errors)} config error(s) (run: kit-models check)"); return
    drift = []
    for n in names:
        want = km.resolve_agent(cfg, n)["model"]
        line = next((l for l in (KIT / "agents" / f"{n}.md").read_text().split("\n") if l.startswith("model:")), "")
        if line.split(":", 1)[-1].strip() != want:
            drift.append(n)
    if drift:
        add("warn", "Models", f"{len(drift)} agent(s) don't match models.json (run: kit-models apply)")
    else:
        add("ok", "Models", f"default {cfg.get('default_profile', 'built-in opus')}; "
            f"{len(names)} agents match{'; ' + str(len(warnings)) + ' warning(s)' if warnings else ''}")


def check_direct_models():
    """Phase 2 and 3: which providers direct calls may reach, and whether their credentials are named."""
    import importlib.util
    path = KIT / ".install/shared/kit_models.py"
    if not path.exists():
        return
    spec = importlib.util.spec_from_file_location("kit_models", str(path))
    km = importlib.util.module_from_spec(spec); spec.loader.exec_module(km)
    try:
        cfg = km.load(KIT)
    except km.ConfigError:
        return
    phase = km.enabled_phase(cfg)
    reach = [n for n, p in (cfg.get("providers") or {}).items()
             if int(p.get("phase", 1 if p.get("kind") == "anthropic" else 2)) <= phase]
    missing = [n for n in reach if (cfg["providers"][n].get("kind") not in ("ollama", "lmstudio", "local")
               and cfg["providers"][n].get("credential_required", True)
               and not (os.environ.get(cfg["providers"][n].get("credential_env") or "")
                        or cfg["providers"][n].get("keychain_entry")))]
    # Missing credentials matter only once phase 2 is on; in phase 1 nothing calls a provider directly
    # unless someone runs kit-delegate or kit-run by hand.
    add("warn" if missing and phase >= 2 else "ok", "Direct model calls",
        f"enabled_phase {phase}; reachable: {', '.join(reach) or 'none'}"
        + (f"; no credential found for {', '.join(missing)} (kit-delegate and kit-run only)" if missing else ""))


def check_sharing_policy():
    """The organization profile for sharing between Kits (sharing-policy.json)."""
    import importlib.util
    path = KIT / ".install/shared/kit_transport.py"
    if not path.exists():
        return
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("kit_transport", str(path))
    kt = importlib.util.module_from_spec(spec); spec.loader.exec_module(kt)
    pol = kt.load_policy(KIT)
    add("warn" if pol.get("_broken") else "ok", "Sharing policy", kt.describe_policy(pol))


def check_connectors_quick():
    """Connector credentials by name (no claude call, no network): which allowed servers name a
    credential variable that isn't set. The full check is: kit-connect test."""
    try:
        cfg = json.loads((KIT / "memory/context/connector-guard.json").read_text())
    except (OSError, ValueError):
        return
    missing = [f"{s} ({v})" for s in cfg.get("allowed_servers") or []
               for v in (cfg.get("credential_env") or {}).get(s, []) if not os.environ.get(v)]
    add("warn" if missing else "ok", "Connector credentials",
        ("missing by name: " + ", ".join(missing) + " (run: kit-connect test)") if missing
        else "every named credential variable is set (full check: kit-connect test)")


def check_phone():
    """Phone and remote access phase 1: publishing folder and pending requests/approvals."""
    import importlib.util
    path = KIT / ".install/shared/kit_inbox.py"
    if not path.exists():
        return
    spec = importlib.util.spec_from_file_location("kit_inbox", str(path))
    ki = importlib.util.module_from_spec(spec); spec.loader.exec_module(ki)
    cfg = {}
    conf = KIT / ".install/shared/morning/config"
    if conf.exists():
        for line in conf.read_text().splitlines():
            m = re.match(r'^(\w+)="?([^"]*)"?', line.strip())
            if m:
                cfg[m.group(1)] = m.group(2)
    target, why = ki.check_publish_dir(cfg)
    if why and why.startswith("refused"):
        add("warn", "Phone publishing", why)
    else:
        add("ok", "Phone publishing", str(target) if target else why)


def check_reliability():
    """Scheduled-run reliability (kit-reliability): warn on any alert."""
    import importlib.machinery, importlib.util
    path = KIT / ".install/shared/bin/kit-reliability"
    if not path.exists():
        return
    loader = importlib.machinery.SourceFileLoader("kit_reliability", str(path))
    spec = importlib.util.spec_from_loader("kit_reliability", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    rep = mod.analyse()
    alerts = rep["alerts"]
    w = rep["windows"]["7"]
    ok_runs = sum(s["success"] for s in w.values())
    all_runs = sum(s["runs"] for s in w.values())
    if alerts:
        add("warn", "Run reliability", "; ".join(alerts[:3]) + (f" (+{len(alerts) - 3} more)" if len(alerts) > 3 else "")
            + " (see: kit-reliability)")
    else:
        add("ok", "Run reliability", f"{ok_runs} of {all_runs} scheduled runs succeeded in 7 days")


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


def check_grammar():
    """Optional: LanguageTool and Java for the reviewer's grammar pass. Missing is fine, never a warning."""
    tool = pathlib.Path(__file__).resolve().parent / "bin" / "kit-grammar"
    if not tool.exists():
        return
    code, out = run([sys.executable, str(tool), "--where"], timeout=60)
    found = code == 0 and "not found" not in out
    add("ok", "Grammar check", "LanguageTool and Java found: " + " | ".join(out.split("\n")[:2]).strip()
        if found else "LanguageTool or Java not installed; optional, reviews skip the grammar pass")


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


# ---- agent readiness (doctor.py --readiness) ------------------------------------------------------
# The source of Kit's agent-readiness figures: how many agents have no known limit, have limits, or are
# blocked, and why, by cause. Computed from what each agent reads and needs, never from notes:
#   setup      fields in the setup files the agent names (memory/context/<file>) whose value is "not set"
#              ("- **Field:** not set"); a limit. A named setup file that's missing blocks the agent.
#   library    agents that name library.md need the library root it names to exist; blocks.
#   connector  agents with connector-guard hooks, or that name connectors.md and can reach a connector or the
#              gateway (no explicit tools list, or one with mcp__ tools or Agent), need connector-guard.json and
#              working connectors. A server fails when the morning check has an open outage for it
#              (briefs/connectors-alerts.json), else when its latest result in connectors-history.jsonl
#              failed, else when a credential variable it names (credential_env) isn't set (by name
#              only; values are never read). Some failing: a limit; all failing, none configured, or
#              settings unreadable: blocked.
#   tool       a kit-* tool the agent names that isn't in .install/shared/bin; a limit.
#   command    an outside command the agent names in backticks, alone or with arguments (`drawio`,
#              `soffice --headless ...`; drawio, soffice, pdftotext, java), that isn't on the PATH; a limit.
READINESS_COMMANDS = ("drawio", "soffice", "pdftotext", "java")
NOT_SET = re.compile(r"^\s*[-*]\s+\*\*([^*\n]+?)\*\*\s*:?\s*[`_]*not set\b", re.M | re.I)
CAUSES = {"setup": "setup fields not set", "setup-missing": "setup file missing", "library": "library root missing",
          "connector": "connectors not working", "tool": "Kit tool missing", "command": "outside command missing"}


def _read(path):
    try:
        return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def not_set_fields(text):
    return [m.group(1).strip().rstrip(":") for m in NOT_SET.finditer(text or "")]


def _connector_state(kit, env):
    """(problem blocking everything or None, {server: reason failing}, [servers])."""
    path = env.get("KIT_CONNECTOR_GUARD_CONFIG") or str(kit / "memory/context/connector-guard.json")
    if not os.path.exists(path):
        return "connector-guard.json missing", {}, []
    try:
        cfg = json.loads(_read(path) or "")
        servers = list(cfg.get("allowed_servers") or [])
    except (ValueError, AttributeError):
        return "connector-guard.json unreadable", {}, []
    if not servers:
        return "no connectors configured (allowed_servers is empty)", {}, []
    alerts = {}
    try:
        alerts = json.loads(_read(kit / "briefs/connectors-alerts.json") or "{}")
    except ValueError:
        pass
    latest = {}
    for line in (_read(kit / "briefs/connectors-history.jsonl") or "").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("server") and str(rec.get("date", "")) >= str(latest.get(rec["server"], {}).get("date", "")):
            latest[rec["server"]] = rec
    failing = {}
    for s in servers:
        if isinstance(alerts, dict) and s in alerts:
            failing[s] = "outage since " + str((alerts[s] or {}).get("since", "?"))
        elif s in latest:
            if not latest[s].get("pass"):
                failing[s] = f"failed the check on {latest[s].get('date', '?')}"
        else:
            miss = [v for v in (cfg.get("credential_env") or {}).get(s, []) if not env.get(v)]
            if miss:
                failing[s] = "credential not set: " + ", ".join(miss)
    return None, failing, servers


def readiness(kit=None, env=None):
    """{"total", "counts", "by_cause", "agents", ...} for the live agents (kit/agents)."""
    import shutil
    kit = pathlib.Path(kit or os.environ.get("KIT_DIR") or KIT).expanduser()
    env = os.environ if env is None else env
    ctx = kit / "memory/context"
    names = {p.name for p in ctx.glob("*") if p.is_file()} if ctx.is_dir() else set()
    names |= {p.name for p in (kit / ".install/kit/memory/context").glob("*") if p.is_file()}
    names.discard("INDEX.md")
    bindir = kit / ".install/shared/bin"
    lib_text = _read(ctx / "library.md") or ""
    m = re.search(r"\*\*Library root:\*\*\s*`([^`]+)`", lib_text)
    lib_root = pathlib.Path(os.path.expanduser(m.group(1))) if m else None
    conn = None
    agents = {}
    for path in sorted((kit / "agents").glob("*.md")):
        text = _read(path) or ""
        fm = re.match(r"---\s*\n(.*?)\n---", text, re.S)
        front = fm.group(1) if fm else ""
        name = (re.search(r"^name:\s*(\S+)", front, re.M) or [None, path.stem])[1]
        body = text[fm.end():] if fm else text
        files = sorted(n for n in names if re.search(rf"(?<![\w.-]){re.escape(n)}(?![\w-])", body))
        limits = []
        for f in files:
            t = _read(ctx / f)
            if t is None:
                limits.append({"cause": "setup-missing", "blocking": True, "detail": f"{f} missing"})
                continue
            unset = not_set_fields(t) if f.endswith(".md") else []
            if unset:
                limits.append({"cause": "setup", "blocking": False,
                               "detail": f"{f}: " + ", ".join(unset) + " not set"})
        if "library.md" in files and (ctx / "library.md").exists() and (lib_root is None or not lib_root.is_dir()):
            limits.append({"cause": "library", "blocking": True,
                           "detail": "library root not set" if lib_root is None else f"library root {lib_root} missing"})
        guarded = bool(re.search(r"connector-guard\S*\"?\s+pre\b", front))
        tl = re.search(r"^tools:[ \t]*(.+)$", front, re.M)
        can_reach = tl is None or bool(re.search(r"mcp__|\bAgent\b", tl.group(1)))
        if guarded or ("connectors.md" in files and can_reach):
            if conn is None:
                conn = _connector_state(kit, env)
            whole, failing, servers = conn
            if whole:
                limits.append({"cause": "connector", "blocking": True, "detail": whole})
            elif failing:
                detail = "; ".join(f"{s} ({why})" for s, why in sorted(failing.items()))
                limits.append({"cause": "connector", "blocking": len(failing) == len(servers),
                               "detail": ("all connectors failing: " if len(failing) == len(servers) else "") + detail})
        if bindir.is_dir():
            missing = sorted({t for t in re.findall(r"\bkit-[a-z][a-z-]*[a-z]\b", body) if not (bindir / t).exists()})
            if missing:
                limits.append({"cause": "tool", "blocking": False, "detail": ", ".join(missing) + " not installed"})
        cmds = sorted({c for c in READINESS_COMMANDS if re.search(rf"`{c}(?:`|\s[^`\n]*`)", body) and not shutil.which(c, path=env.get("PATH", os.defpath))})
        if cmds:
            limits.append({"cause": "command", "blocking": False, "detail": ", ".join(cmds) + " not on the PATH"})
        status = "blocked" if any(x["blocking"] for x in limits) else ("limited" if limits else "ready")
        agents[name] = {"status": status, "setup_files": files, "limits": limits}
    counts = {k: sum(a["status"] == k for a in agents.values()) for k in ("ready", "limited", "blocked")}
    by_cause = {}
    for name, a in agents.items():
        for x in a["limits"]:
            c = by_cause.setdefault(x["cause"], {"label": CAUSES[x["cause"]], "agents": [], "blocking": []})
            if name not in c["agents"]:
                c["agents"].append(name)
            if x["blocking"] and name not in c["blocking"]:
                c["blocking"].append(name)
    for c in by_cause.values():
        c["count"] = len(c["agents"])
    return {"generated": dt.datetime.now().isoformat(timespec="minutes"), "kit": str(kit), "total": len(agents),
            "counts": counts, "by_cause": dict(sorted(by_cause.items(), key=lambda kv: -kv[1]["count"])),
            "agents": agents,
            "summary": readiness_line(len(agents), counts),
            "method": "doctor.py --readiness: setup fields marked 'not set' in the setup files each agent names, "
                      "missing setup files, the library root, connector state (outages, last check, credential "
                      "names), and named Kit tools and commands. A limit the files don't record isn't seen."}


def readiness_line(total, counts):
    return (f"{total} agents: {counts['ready']} with no known limit, {counts['limited']} with limits, "
            f"{counts['blocked']} blocked")


def render_readiness(r):
    out = [f"Agent readiness, {dt.date.today():%d-%b-%Y}: {r['summary']}.", "",
           "By cause (agents affected; an agent can have more than one):"]
    for cause, c in r["by_cause"].items():
        blk = f", blocking {len(c['blocking'])}" if c["blocking"] else ""
        out.append(f"  {c['label']}: {c['count']}{blk} ({', '.join(c['agents'])})")
    if not r["by_cause"]:
        out.append("  none")
    out += ["", "By agent:"]
    label = {"ready": "no known limit", "limited": "limited", "blocked": "BLOCKED"}
    for name, a in r["agents"].items():
        out.append(f"  {name:<24} {label[a['status']]}")
        for x in a["limits"]:
            out.append(f"      {x['cause']}{' (blocks)' if x['blocking'] else ''}: {x['detail']}")
    out += ["", r["method"]]
    return "\n".join(out)


def check_readiness():
    r = readiness(KIT)
    if r["total"]:
        causes = ", ".join(f"{c['label']} {c['count']}" for c in r["by_cause"].values())
        add("ok", "Agent readiness", r["summary"] + (f" (by cause: {causes}; doctor.py --readiness)" if causes else ""))


def main(argv):
    if "--fix-agents" in argv:
        fix_agents()
        return 0
    if "--readiness" in argv:
        r = readiness()
        print(json.dumps(r, indent=1) if "--json" in argv else render_readiness(r))
        return 0
    for fn in (check_import, check_settings, check_index, check_jobs, check_runs, check_tokens,
               check_secrets, check_permissions, check_agents, check_git, check_calendar, check_mail,
               check_guard, check_grammar, check_delivery, check_paused, check_outlook, check_holds,
               check_cost, check_version, check_models, check_direct_models, check_sharing_policy,
               check_connectors_quick, check_phone, check_reliability, check_readiness):
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

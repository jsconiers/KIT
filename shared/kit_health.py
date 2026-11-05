"""kit_health: one health number for Kit, 0 to 100, for the dashboard's badge and `doctor.py --score`.

Four parts, 25 points each, from files Kit already keeps (it reads them and changes nothing):

  connectors  the servers in connector-guard.json's allowed_servers: each one's latest result in
              briefs/connectors-history.jsonl (the morning connector check). A pass counts 1, a server with
              an open outage (briefs/connectors-alerts.json) or a failed check counts 0, and a server with no
              result in the last 3 days counts half. No servers configured: full marks.
  runs        Kit's scheduled runs over the last 7 days (kit-reliability): a success counts 1, a degraded run
              half, a failure or timeout 0. Each open run alert (briefs/alerts.json) takes 5 points off. No
              runs in 7 days: half marks.
  audit       today's audit findings (briefs/audit-status.json, from kit-audit --daily): 10 points off per
              critical, 3 per warning; and 3 off per open integrity alert in briefs/alerts.json (agent drift,
              connector guard, library index, cost). No audit status yet: half marks.
  setup       the open setup questions: fields marked "not set" in the setup files the agents name
              (memory/context/*.md), as a share of all the fields in those files. Every field set: full marks.

Bands: 90 and up "healthy", 70 to 89 "needs attention", under 70 "unhealthy". Every part says why it lost
points, so the badge's detail reads as a to-do list. Nothing here calls a model, a connector, or the web.
"""
import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import re

PART = 25.0
FIELD = re.compile(r"^\s*[-*]\s+\*\*([^*\n]+?)\*\*\s*:?(.*)$", re.M)
NOT_SET = re.compile(r"^[\s`_*]*not set\b", re.I)


def _kit(kit=None):
    return pathlib.Path(os.path.expanduser(str(kit or os.environ.get("KIT_DIR") or "~/Claude/Agents/kit")))


def _json(path, default=None):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def _read(path):
    try:
        return pathlib.Path(path).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def _part(name, score, detail, problems=None):
    score = max(0.0, min(PART, float(score)))
    return {"name": name, "score": round(score, 1), "max": PART, "detail": detail, "problems": problems or []}


def connectors(kit, today):
    cfg = _json(kit / "memory/context/connector-guard.json", {}) or {}
    servers = [s for s in (cfg.get("allowed_servers") or []) if isinstance(s, str)] if isinstance(cfg, dict) else []
    if not servers:
        return _part("Connectors", PART, "none configured")
    alerts = _json(kit / "briefs/connectors-alerts.json", {}) or {}
    latest = {}
    for line in _read(kit / "briefs/connectors-history.jsonl").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("server") in servers:
            if str(rec.get("date", "")) >= str(latest.get(rec["server"], {}).get("date", "")):
                latest[rec["server"]] = rec
    got, problems = 0.0, []
    for s in servers:
        rec = latest.get(s)
        if isinstance(alerts, dict) and s in alerts:
            problems.append(f"{s}: outage since {(alerts[s] or {}).get('since', '?')}")
            continue
        try:
            fresh = rec and (today - dt.date.fromisoformat(str(rec.get("date"))[:10])).days <= 3
        except ValueError:
            fresh = False
        if not fresh:
            got += 0.5
            problems.append(f"{s}: no check in the last 3 days")
        elif rec.get("pass"):
            got += 1
        else:
            problems.append(f"{s}: failed the check on {rec.get('date')}")
    ok = sum(1 for s in servers if latest.get(s, {}).get("pass") and s not in alerts)
    return _part("Connectors", PART * got / len(servers), f"{ok} of {len(servers)} passing", problems)


def _reliability(kit):
    for path in (kit / ".install/shared/bin/kit-reliability",
                 pathlib.Path(__file__).resolve().parent / "bin/kit-reliability"):
        if path.exists():
            loader = importlib.machinery.SourceFileLoader("kit_reliability_health", str(path))
            spec = importlib.util.spec_from_loader("kit_reliability_health", loader)
            mod = importlib.util.module_from_spec(spec)
            loader.exec_module(mod)
            return mod
    return None


def runs(kit, report=None):
    alerts = (_json(kit / "briefs/alerts.json", {}) or {}).get("alerts") or {}
    open_runs = [a for a in alerts.values() if isinstance(a, dict) and a.get("kind") == "run"] \
        if isinstance(alerts, dict) else []
    if report is None:
        try:
            mod = _reliability(kit)
            report = mod.analyse() if mod else None
        except Exception:  # noqa: BLE001  (a reliability problem shouldn't break the dashboard)
            report = None
    if report is None:
        return _part("Runs", PART / 2, "run history couldn't be read", ["kit-reliability couldn't be read"])
    w7 = (report.get("windows") or {}).get("7") or {}
    total = sum(s.get("runs", 0) for s in w7.values())
    problems = [f"{a.get('mode', '?')}: {a.get('reason', 'alert open')}" for a in open_runs]
    if not total:
        return _part("Runs", PART / 2 - 5 * len(open_runs), "no scheduled runs in the last 7 days",
                     problems or ["no scheduled runs in the last 7 days"])
    good = sum(s.get("success", 0) + 0.5 * s.get("degraded", 0) for s in w7.values())
    fails = sum(s.get("failure", 0) for s in w7.values())
    if fails:
        problems.append(f"{fails} failed run(s) in the last 7 days")
    return _part("Runs", PART * good / total - 5 * len(open_runs),
                 f"{int(sum(s.get('success', 0) for s in w7.values()))} of {total} runs succeeded (7 days)", problems)


MONITORS = {"drift": "agent drift", "guard": "connector guard", "library": "library index", "cost": "cost"}


def audit(kit):
    alerts = (_json(kit / "briefs/alerts.json", {}) or {}).get("alerts") or {}
    mon = [a for a in alerts.values() if isinstance(a, dict) and a.get("kind") in MONITORS] \
        if isinstance(alerts, dict) else []
    mon_problems = [f"{MONITORS[a['kind']]}: {str(a.get('reason', 'alert open'))[:90]}" for a in mon]
    st = _json(kit / "briefs/audit-status.json")
    if not isinstance(st, dict):
        return _part("Audit", PART / 2 - 3 * len(mon), "no audit status yet",
                     ["no audit status yet (kit-audit --daily)"] + mon_problems)
    sc = (st.get("daily") or {}).get("severity_counts") or st.get("severity_counts") or {}
    crit, warn = int(sc.get("critical", 0) or 0), int(sc.get("warning", 0) or 0)
    problems = []
    for f in st.get("findings") or []:
        if isinstance(f, dict) and f.get("severity") in ("critical", "warning"):
            problems.append(f"{f.get('severity')}: {f.get('title', '')}")
    detail = f"{crit} critical, {warn} warning" + (f"; {len(mon)} integrity alert{'s' if len(mon) != 1 else ''} open"
                                                   if mon else "")
    return _part("Audit", PART - 10 * crit - 3 * warn - 3 * len(mon), detail, problems + mon_problems)


def setup(kit):
    """Not-set fields in the setup files that at least one agent names."""
    ctx = kit / "memory/context"
    files = sorted(p for p in ctx.glob("*.md") if p.name != "INDEX.md") if ctx.is_dir() else []
    bodies = "\n".join(_read(p) for p in (kit / "agents").glob("*.md")) if (kit / "agents").is_dir() else ""
    named = [p for p in files if re.search(rf"(?<![\w.-]){re.escape(p.name)}(?![\w-])", bodies)] or files
    total, unset = 0, []
    for p in named:
        for m in FIELD.finditer(_read(p)):
            total += 1
            if NOT_SET.match(m.group(2)):
                unset.append(f"{p.name}: {m.group(1).strip().rstrip(':')}")
    if not total:
        return _part("Setup", PART, "no setup fields found")
    detail = f"{len(unset)} open setup question{'s' if len(unset) != 1 else ''} ({total - len(unset)} of {total} fields set)"
    shown = unset[:8] + ([f"and {len(unset) - 8} more (kit-settings show --not-set)"] if len(unset) > 8 else [])
    return _part("Setup", PART * (total - len(unset)) / total, detail, shown)


def band(score):
    return "healthy" if score >= 90 else "needs attention" if score >= 70 else "unhealthy"


def score(kit=None, today=None, reliability_report=None):
    kit = _kit(kit)
    today = today or dt.date.today()
    parts = [connectors(kit, today), runs(kit, reliability_report), audit(kit), setup(kit)]
    total = round(sum(p["score"] for p in parts))
    return {"score": total, "band": band(total), "parts": parts,
            "generated": dt.datetime.now().isoformat(timespec="minutes"),
            "method": "kit_health: connectors, runs, audit, setup, 25 points each"}


def render(res):
    out = [f"Kit health: {res['score']}/100 ({res['band']})"]
    for p in res["parts"]:
        out.append(f"  {p['name']:<11} {p['score']:>4g}/{p['max']:g}  {p['detail']}")
        out += [f"      - {x}" for x in p["problems"]]
    return "\n".join(out)


def badge(res, href="#p-health"):
    """The dashboard's badge: a link with the score and a hover title naming where points were lost."""
    import html
    cls = {"healthy": "ok", "needs attention": "warn", "unhealthy": "fail"}[res["band"]]
    lost = [f"{p['name']} {p['score']:g}/{p['max']:g}: {p['detail']}" for p in res["parts"]]
    title = f"{res['band'].capitalize()}. " + "; ".join(lost)
    return (f'<a class="hbadge {cls}" href="{href}" title="{html.escape(title)}" '
            f'aria-label="Kit health {res["score"]} out of 100, {html.escape(res["band"])}">'
            f'<span class="hnum">{res["score"]}</span><span class="hlabel">health</span></a>')


def panel(res):
    """The parts, for the top of the Health panel."""
    import html
    e = html.escape
    rows = "".join(
        f'<li class="check {"ok" if p["score"] >= p["max"] * 0.9 else "warn" if p["score"] >= p["max"] * 0.7 else "fail"}">'
        f'<span class="light"></span><span class="cname">{e(p["name"])} {p["score"]:g}/{p["max"]:g}</span>'
        f'<span class="cdetail">{e(p["detail"])}' + (f": {e('; '.join(p['problems'][:4]))}" if p["problems"] else "")
        + "</span></li>" for p in res["parts"])
    return (f'<p class="meta">Health score {res["score"]}/100, {e(res["band"])} '
            f'(<code>doctor.py --score</code> explains it)</p><ul class="checks hparts">{rows}</ul>')

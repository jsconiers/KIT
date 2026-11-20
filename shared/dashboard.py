#!/usr/bin/env python3
"""Build Kit's dashboard: ~/Claude/Agents/kit/dashboard.html (open it in any browser).

The page comes from an HTML template (see kit_template.py): your copy in
~/Claude/Agents/kit/templates/dashboard.html if it exists, else shared/templates/dashboard.html.
  python3 ~/Claude/Agents/kit/.install/shared/dashboard.py --template my.html    try another one

  python3 ~/Claude/Agents/kit/.install/shared/dashboard.py          rebuild
  python3 ~/Claude/Agents/kit/.install/shared/dashboard.py --open   rebuild and open

The scheduled runs and the todo command rebuild it; the page reloads itself every 5 minutes.
"""
import datetime as dt
import html
import json
import os
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import kit_template  # noqa: E402  (shared/kit_template.py)
import kit_queue  # noqa: E402  (shared/kit_queue.py)
import kit_settings  # noqa: E402  (shared/kit_settings.py: the Settings panel)
import kit_health  # noqa: E402  (shared/kit_health.py: the health score badge)

# strftime no-pad hour: glibc/BSD use %-I, the Windows CRT uses %#I.
HOUR = "%#I" if os.name == "nt" else "%-I"

HOME = pathlib.Path.home()
KIT = HOME / "Claude/Agents/kit"
OUT = KIT / "dashboard.html"
LOGS = KIT / ".install/logs"
NOW = dt.datetime.now()
TODAY = NOW.date()
e = html.escape


# Used only when no template is found: plain, but every section still shows.
FALLBACK = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="300">
<title>Kit</title><style>body{font:16px/1.5 system-ui,Arial,sans-serif;margin:1.5rem;max-width:70rem}
.banner{background:#7a0000;color:#fff;padding:.6rem 1rem}section{margin-top:1.5rem}</style></head>
<body><h1>Kit</h1>$health_badge<p><time datetime="$now_iso">$now_text</time> (built-in page: no template found)</p>
$audit_banner<div>$hero</div>$lane_you $lane_kit $lane_wait
<section><h2>Today</h2>$schedule</section><section><h2>Briefs</h2>$briefs</section>
<section><h2>Health</h2>$health_score<ul>$health_checks</ul><table><thead><tr><th></th>$runs_head</tr></thead><tbody>$runs_rows</tbody></table></section>
<section><h2>Sprint</h2>$sprint</section><section><h2>Reviews</h2>$reviews</section><section><h2>Reliability</h2>$reliability</section><section><h2>Audit</h2>$audit</section><section><h2>Kit's staff</h2><ul>$staff</ul></section>
<section id="settings"><h2>Settings</h2>$settings</section>
</body></html>
"""


def owner():
    """The owner's lane: OWNER_NAME when QUEUE.md has a section by that name, otherwise the queue's own owner
    section, as `todo` finds it."""
    cfg = KIT / ".install/shared/morning/config"
    name = kit_queue.configured_owner(cfg.read_text()) if cfg.exists() else None
    q = KIT / "QUEUE.md"
    lines = q.read_text().splitlines() if q.exists() else []
    return kit_queue.owner_section(lines, name) or name or "You"


def parse_queue():
    lanes, current, item = {}, None, None
    path = KIT / "QUEUE.md"
    for ln in (path.read_text().splitlines() if path.exists() else []):
        if ln.startswith("## "):
            current, item = ln[3:].strip(), None
            lanes[current] = []
        elif current and ln.startswith("- [ ]"):
            m = re.match(r"- \[ \] \*\*(.+?)\*\*(.*)", ln)
            title, rest = (m.group(1), m.group(2)) if m else (ln[6:], "")
            due = re.search(r"due (\d{2}-\w{3}-\d{4})", rest)
            added = re.search(r"added (\d{2}-\w{3}-\d{4})", rest)
            wait = re.search(r"waiting on ([^,(]+)", rest, re.I)
            item = {"title": title, "detail": [], "rest": rest.strip(" :"),
                    "due": dt.datetime.strptime(due.group(1), "%d-%b-%Y").date() if due else None,
                    "added": added.group(1) if added else "",
                    "wait": wait.group(1).strip() if wait else ""}
            lanes[current].append(item)
        elif current and item and ln.startswith("  - "):
            item["detail"].append(ln.strip()[2:])
        elif not ln.startswith("  "):
            item = None
    return lanes


def due_tag(d):
    if not d:
        return ""
    days = (d - TODAY).days
    if days < 0:
        return f'<span class="tag late">Overdue {abs(days)} day{"s" if days != -1 else ""}</span>'
    if days == 0:
        return '<span class="tag soon">Due today</span>'
    if days <= 3:
        return f'<span class="tag soon">Due {d:%a %d-%b}</span>'
    return f'<span class="tag">Due {d:%a %d-%b}</span>'


def strip(item):
    meta = due_tag(item["due"])
    if item["wait"]:
        meta += f'<span class="tag">Waiting on {e(item["wait"])}</span>'
    if item["added"]:
        meta += f'<span class="added">Added {e(item["added"])}</span>'
    detail = "".join(f"<li>{e(d)}</li>" for d in item["detail"])
    return (f'<li class="strip"><p class="strip-title">{e(item["title"])}</p>'
            f'<div class="meta">{meta}</div>{f"<ul class=detail>{detail}</ul>" if detail else ""}</li>')


def lane(name, css, items, empty):
    body = "".join(strip(i) for i in items) or f'<li class="empty">{e(empty)}</li>'
    return (f'<section class="lane {css}" aria-labelledby="lane-{css}">'
            f'<h2 id="lane-{css}">{e(name)} <span class="count">{len(items)}</span></h2>'
            f'<ul class="strips">{body}</ul></section>')


def health():
    try:
        r = subprocess.run([sys.executable, str(KIT / ".install/shared/doctor.py")],
                           capture_output=True, text=True, timeout=60)
        rows = []
        for ln in r.stdout.splitlines():
            m = re.match(r"\s+(ok|warn|FAIL)\s+([^:]+):\s*(.*)", ln)
            if m:
                rows.append((m.group(1).lower(), m.group(2), m.group(3)))
        return rows
    except Exception as ex:  # noqa: BLE001
        return [("fail", "Health check", f"couldn't run: {ex}")]


def runs():
    grid = {}
    for back in range(6, -1, -1):
        day = TODAY - dt.timedelta(days=back)
        grid[day] = {}
        log = LOGS / f"{day:%Y-%m-%d}.log"
        if not log.exists():
            continue
        mode = None
        for ln in log.read_text(errors="ignore").splitlines():
            m = re.match(r"== .* start (\w+)?\s*(\[Test\])?", ln)
            if m:
                mode = None if m.group(2) else (m.group(1) or "morning")
                if mode:
                    grid[day][mode] = "ran"
            elif mode and (ln.startswith("== texted") or ln.startswith("== delivered")):
                grid[day][mode] = "texted"
            elif mode and (ln.startswith("== text failed") or ln.startswith("== sent failure")
                          or ln.startswith("== delivery failed")):
                grid[day][mode] = "failed"
            elif mode and ln.startswith("== market closed"):
                grid[day][mode] = "closed"
    return grid


def brief_text():
    parts = []
    for name, label in (("latest-text.txt", "Morning"), ("open-text.txt", "After the open"),
                        ("weekly-text.txt", "Weekly review")):
        p = KIT / "briefs" / name
        if p.exists() and dt.date.fromtimestamp(p.stat().st_mtime) >= TODAY - dt.timedelta(days=6):
            when = dt.datetime.fromtimestamp(p.stat().st_mtime)
            parts.append(f'<article class="brief"><h3>{label} <span class="when">{when:%a %d-%b %H:%M}</span></h3>'
                         f'<pre>{e(p.read_text().strip())}</pre></article>')
    full = KIT / "briefs" / f"{TODAY:%Y-%m-%d}.md"
    link = f'<p class="full"><a href="briefs/{full.name}">Open today\'s full brief</a></p>' if full.exists() else ""
    return "".join(parts) + link or '<p class="empty">No brief yet today. The next one runs at 7:45 on weekdays.</p>'


def calendar_cmd():
    """The calendar command for the Today panel: CALENDAR_JSON_CMD from the run settings (any command
    that prints today's events as a JSON list), else kitcal (macOS ~/.local/bin/kitcal; on Windows the
    installer's kitcal.cmd). Quoted words keep their spaces, and Windows paths keep their backslashes."""
    import shlex
    import shutil
    cfg = KIT / ".install/shared/morning/config"
    if cfg.exists():
        m = re.search(r'^CALENDAR_JSON_CMD="([^"]+)"', cfg.read_text(errors="ignore"), re.M)
        if m:
            try:
                if os.name == "nt":
                    words = [w[1:-1] if len(w) > 1 and w[0] == w[-1] and w[0] in "\"'" else w
                             for w in shlex.split(m.group(1), posix=False)]
                else:
                    words = shlex.split(m.group(1))
            except ValueError:
                words = m.group(1).split()
            words = [os.path.expanduser(w) for w in words]
            if os.name == "nt" and words and not os.path.dirname(words[0]):
                words[0] = shutil.which(words[0]) or words[0]    # kitcal -> kitcal.cmd, through PATHEXT
            return words
    exe = str(HOME / ".local/bin/kitcal")
    if os.name == "nt":
        shim = KIT / ".install/platform/windows/bin/kitcal.cmd"
        exe = shutil.which("kitcal") or (str(shim) if shim.exists() else "kitcal")
    return [exe, "events", "--from", "today", "--to", "today"]


def when_of(stamp):
    """Parse an event time written as 'YYYY-MM-DD HH:MM' or ISO 8601."""
    stamp = stamp.replace("T", " ")[:16]
    return dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M")


def schedule():
    try:
        r = subprocess.run(calendar_cmd(), capture_output=True, text=True, timeout=90)
        evs = json.loads(r.stdout or "[]")
    except Exception:  # noqa: BLE001
        return ('<p class="empty">Calendar unavailable. Check the calendar command (CALENDAR_JSON_CMD in '
                'the run settings, or kitcal) and that the calendar app is running.</p>')
    if not evs:
        return '<p class="empty">Nothing on the calendar today.</p>'
    rows = []
    for ev in evs:
        if ev.get("all_day"):
            when = "All day"
        else:
            a, b = when_of(ev["start"]), when_of(ev["end"])
            when = f"{a.strftime(HOUR + ':%M')}–{b.strftime(HOUR + ':%M %p')}"
        cal = ev.get("calendar", "").split("|")[0]
        rows.append(f'<li><time>{e(when)}</time> {e(ev.get("title") or ev.get("subject", ""))} <span class="cal">{e(cal)}</span></li>')
    return '<ul class="sched">' + "".join(rows) + "</ul>"


def staff():
    rows = []
    for f in sorted((KIT / "agents").glob("*.md")):
        t = f.read_text()
        m = re.search(r"description:\s*>-?\s*\n((?:\s+.+\n)+)", t)
        desc = " ".join(m.group(1).split()) if m else ""
        first = desc.split(". ")[0].rstrip(".") + "." if desc else ""
        rows.append(f'<li><span class="agent">{e(f.stem.replace("-", " "))}</span> {e(first)}</li>')
    return "".join(rows) or '<li class="empty">No staff yet.</li>'


def connector_banner():
    """The connector-outage banner, from briefs/connectors-alerts.json (written by the morning run's
    connector_health.py when a connector fails CONNECTOR_FAIL_STREAK mornings running; cleared when it
    passes again)."""
    path = KIT / "briefs" / "connectors-alerts.json"
    try:
        alerts = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    except Exception:  # noqa: BLE001
        return ""
    if not isinstance(alerts, dict) or not alerts:
        return ""
    parts = []
    for name, a in sorted(alerts.items()):
        a = a if isinstance(a, dict) else {}
        since = a.get("since", "?")
        try:
            since = dt.date.fromisoformat(since).strftime("%d-%b")
        except (TypeError, ValueError):
            pass
        parts.append(f"{name} (failing since {since}, {a.get('streak', '?')} mornings running"
                     + (f": {a['reason']}" if a.get("reason") else "") + ")")
    return (f'<div class="banner" role="alert"><strong>Connector outage</strong> {e("; ".join(parts))}. '
            'It\'s on your list; run kit-connect test to check. The alert clears when the morning check '
            'passes again.</div>')


def alerts_banner():
    """The run and cost banners, from briefs/alerts.json (written by run_alerts.py at the end of each
    scheduled run, and by kit-alerts check): one red banner for failing or overdue scheduled runs, one
    for cost, one each for the monitors (agent drift, library freshness, items waiting too long,
    connector-guard integrity), and a generic one for any other monitor kind. Each alert clears itself (next success, projection back under, a new month, or back in sync)."""
    path = KIT / "briefs" / "alerts.json"
    try:
        alerts = (json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}).get("alerts") or {}
    except Exception:  # noqa: BLE001
        return ""
    if not isinstance(alerts, dict):
        return ""
    runs, costs, drift, library, waiting, guard, other = [], [], [], [], [], [], []
    for _key, a in sorted(alerts.items()):
        if not isinstance(a, dict):
            continue
        if a.get("kind") == "run":
            runs.append(f"{a.get('mode', '?')}: {a.get('reason', '')}")
        elif a.get("kind") == "cost":
            costs.append(f"{a.get('level', '?')}: {a.get('reason', '')}")
        elif a.get("kind") == "drift":
            drift.append(a.get("reason", ""))
        elif a.get("kind") == "library":
            library.append(a.get("reason", ""))
        elif a.get("kind") == "waiting":
            what = "decision" if a.get("type") == "decision" else "waiting on others"
            waiting.append(f"{a.get('item', '?')} ({what}, {a.get('days', '?')} days"
                           + (f"; draft {a['draft']}" if a.get("draft") else "")
                           + (f"; {a['file']}" if a.get("file") else "") + ")")
        elif a.get("kind") == "guard":
            guard.append(a.get("reason", ""))
        elif a.get("kind") and a.get("reason"):
            other.append((str(a.get("kind")), a.get("reason", "")))
    out = ""
    if runs:
        out += (f'<div class="banner" role="alert"><strong>Scheduled run</strong> {e("; ".join(runs))}. '
                "It's on your list; see kit-reliability. The alert clears after the next successful run.</div>")
    if costs:
        out += (f'<div class="banner" role="alert"><strong>Cost</strong> {e("; ".join(costs))}. '
                "It's on your list; see kit-cost. The alert clears when the spend is back under, or when the "
                "month ends.</div>")
    if drift:
        out += (f'<div class="banner" role="alert"><strong>Agent drift</strong> {e("; ".join(drift))}. '
                "Compare with kit-alerts drift --diff &lt;agent&gt;; nothing is overwritten automatically. The "
                "alert clears when the copies match.</div>")
    if library:
        out += (f'<div class="banner" role="alert"><strong>Library</strong> {e("; ".join(library))}. '
                "The indexes are never edited automatically; the alert clears when they match the folders.</div>")
    if waiting:
        out += (f'<div class="banner" role="alert"><strong>Waiting too long</strong> {e("; ".join(waiting))}. '
                "Follow-up drafts are never sent. The alert clears when the item is checked off or updated.</div>")
    if guard:
        out += (f'<div class="banner" role="alert"><strong>Connector guard</strong> {e("; ".join(guard))}. '
                "Connector calls may be unguarded or unlogged until it's fixed. It's on your list; see kit-alerts "
                "check --only guard. The alert clears when every guard check passes.</div>")
    for kind, reason in other:     # a monitor kind this page doesn't know yet
        out += (f'<div class="banner" role="alert"><strong>{e(kind.capitalize())}</strong> {e(reason)}. '
                "See kit-alerts.</div>")
    return out


def cost_stop_alert_open():
    try:
        alerts = json.loads((KIT / "briefs" / "alerts.json").read_text(encoding="utf-8-sig")).get("alerts") or {}
        return any(isinstance(a, dict) and a.get("kind") == "cost" and a.get("level") == "stop"
                   for a in alerts.values())
    except Exception:  # noqa: BLE001
        return False


def outlook_banner():
    """A banner when today's Outlook check (kit-outlook, briefs/outlook.txt) found Outlook open but hung."""
    try:
        parts = (KIT / "briefs/outlook.txt").read_text(errors="ignore").strip().split(" ", 3)
    except OSError:
        return ""
    if len(parts) < 4 or parts[1] != dt.date.today().isoformat() or parts[0] not in ("hung", "not-responding"):
        return ""
    return (f'<div class="banner" role="alert"><strong>Outlook is hung</strong> {e(parts[3])} Calendar and mail in '
            "today's brief are stale or from Kit's saved copy.</div>")


def state_banners():
    """Banners for a paused Kit (kit-pause), active legal holds (kit-retention), connector outages
    (connector_health.py), failing scheduled runs and cost alerts (run_alerts.py), and the budget's
    stop level (kit-cost; left out when a cost alert already says so)."""
    out = ""
    marker = KIT / ".install/PAUSED"
    if marker.exists():
        why = (marker.read_text(errors="ignore").splitlines() or ["no reason given"])[0]
        out += (f'<div class="banner" role="alert"><strong>Kit is paused</strong> {e(why)}. Scheduled runs and '
                'connector calls are stopped; run kit-pause resume to restart.</div>')
    holds_file = KIT / "memory/context/legal-holds.json"
    try:
        holds = json.loads(holds_file.read_text(encoding="utf-8-sig")) if holds_file.exists() else {}
    except Exception:  # noqa: BLE001
        holds = {"(unreadable holds file)": {}}
    if holds:
        names = ", ".join(f"{p} (since {h.get('since', '?')})" if isinstance(h, dict) else p
                          for p, h in sorted(holds.items()))
        out += (f'<div class="banner" role="alert"><strong>Legal hold</strong> {e(names)}. Nothing in these '
                'projects may be deleted, moved, or rewritten.</div>')
    out += connector_banner()
    out += outlook_banner()
    out += alerts_banner()
    limited = kit_health.usage_limit(KIT)
    if limited:
        out += (f'<div class="banner" role="alert"><strong>Usage limit</strong> {e(limited)}. Scheduled runs stand '
                'down until then; the morning brief is written without a model call.</div>')
    try:
        if cost_stop_alert_open():
            return out
        r = subprocess.run([sys.executable, str(KIT / ".install/shared/bin/kit-cost"), "check", "--json"],
                           capture_output=True, text=True, timeout=30)
        st = json.loads(r.stdout)
        if st.get("level") == "stop":
            out += (f'<div class="banner" role="alert"><strong>Budget</strong> {e(str(st.get("pct_used")))}% of this '
                    "month's budget for scheduled runs is used; only the essential runs go ahead (kit-cost).</div>")
    except Exception:  # noqa: BLE001
        pass
    return out


def audit():
    """The banner and the Audit panel, from briefs/audit-status.json (written by kit-audit)."""
    path = KIT / "briefs" / "audit-status.json"
    try:
        st = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return "", '<p class="empty">No audit status yet. The morning run writes it with kit-audit --daily.</p>'
    sev_class = {"critical": "fail", "warning": "warn", "info": "ok"}

    def when(r):
        try:
            return dt.datetime.fromisoformat(r["generated"]).strftime("%a %d-%b %H:%M")
        except Exception:  # noqa: BLE001
            return ""

    def findings(r, info=False):
        rows = [f for f in r.get("findings", []) if info or f.get("severity") != "info"]
        return "".join(
            f'<li class="check {sev_class.get(f.get("severity"), "warn")}">'
            f'<span class="light" aria-label="{e(f.get("severity", ""))}"></span>'
            f'<span class="cname">{e(f.get("severity", "").capitalize())}: {e(f.get("title", ""))}</span>'
            f'<span class="cdetail">{e(f.get("detail", ""))}</span></li>' for f in rows)

    banner = ""
    if st.get("open_issue"):
        sc = st.get("severity_counts", {})
        top = next((f for f in st.get("findings", []) if f.get("severity") in ("critical", "warning")), {})
        banner = (f'<div class="banner" role="alert"><strong>Audit issue</strong> '
                  f'{sc.get("critical", 0)} critical, {sc.get("warning", 0)} warning: {e(top.get("title", ""))}. '
                  f'See the Audit panel and briefs/audit.txt.</div>')
    parts = []
    daily, weekly = st.get("daily"), st.get("weekly")
    if daily:
        sc, c = daily.get("severity_counts", {}), daily.get("counts", {})
        issues = findings(daily)
        parts.append(f'<article class="brief"><h3>Daily <span class="when">{when(daily)}</span></h3>'
                     f'<p>{sc.get("critical", 0)} critical, {sc.get("warning", 0)} warning, {sc.get("info", 0)} info. '
                     f'{c.get("calls", 0)} calls, {c.get("denied", 0)} denied, {c.get("failures", 0)} failed.</p>'
                     + (f'<ul class="checks">{issues}</ul>' if issues else '<p class="empty">No audit issues.</p>')
                     + '</article>')
    if weekly:
        txt = weekly.get("text", "")
        m = re.search(r"^Weekly audit summary.*?(?=\n\n|\Z)", txt, re.M | re.S)
        parts.append(f'<article class="brief"><h3>Weekly <span class="when">{when(weekly)}</span></h3>'
                     f'<pre>{e(m.group(0) if m else txt.strip())}</pre></article>')
    head = KIT / "briefs" / "audit-weekly.md"
    if head.exists():
        lines = [ln for ln in head.read_text().splitlines() if ln.strip()][:8]
        parts.append(f'<article class="brief"><h3>Auditor\'s headline <span class="when">'
                     f'{dt.datetime.fromtimestamp(head.stat().st_mtime):%a %d-%b}</span></h3>'
                     f'<pre>{e(chr(10).join(lines))}</pre>'
                     f'<p class="full"><a href="briefs/audit-weekly.md">Open the weekly audit</a></p></article>')
    return banner, "".join(parts) or '<p class="empty">No audit status yet.</p>'


def burndown_svg(sp, total, hist):
    """Ideal line from all points at the start to none at the end, and the remaining points on
    each day a snapshot was saved."""
    days = max((sp["end"] - sp["start"]).days, 1)
    w, h, pad = 300, 110, 22
    def xy(day, pts):
        x = pad + (w - 2 * pad) * min(max(day, 0), days) / days
        y = pad / 2 + (h - pad * 1.5) * (1 - (pts / total if total else 0))
        return f"{x:.1f},{y:.1f}"
    actual = []
    for d, rem in sorted(hist.items()):
        day = (dt.datetime.strptime(d, "%Y-%m-%d").date() - sp["start"]).days
        if 0 <= day <= days:
            actual.append(xy(day, rem))
    pts = " ".join(actual)
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-label="Burndown: points left each day against the ideal line">'
            f'<line x1="{pad}" y1="{h - pad}" x2="{w - pad}" y2="{h - pad}" stroke="currentColor" stroke-opacity=".3"/>'
            f'<polyline points="{xy(0, total)} {xy(days, 0)}" fill="none" stroke="currentColor" '
            f'stroke-dasharray="4 3" stroke-opacity=".5"/>'
            + (f'<polyline points="{pts}" fill="none" stroke="currentColor" stroke-width="2.5"/>' if pts else "")
            + f'<text x="{pad}" y="{h - 4}" font-size="10" fill="currentColor">{sp["start"]:%d-%b}</text>'
            f'<text x="{w - pad}" y="{h - 4}" font-size="10" fill="currentColor" text-anchor="end">'
            f'{sp["end"]:%d-%b}</text></svg>')


def reliability_panel():
    """Run reliability for the last 7 days, from kit-reliability (read-only)."""
    import importlib.machinery, importlib.util
    path = KIT / ".install/shared/bin/kit-reliability"
    if not path.exists():
        path = pathlib.Path(__file__).resolve().parent / "bin/kit-reliability"
    if not path.exists():
        return '<p class="empty">kit-reliability isn\'t installed.</p>'
    try:
        loader = importlib.machinery.SourceFileLoader("kit_reliability", str(path))
        spec = importlib.util.spec_from_loader("kit_reliability", loader)
        kr_mod = importlib.util.module_from_spec(spec)
        loader.exec_module(kr_mod)
        rep = kr_mod.analyse()
    except Exception as ex:  # noqa: BLE001
        return f'<p class="empty">Reliability couldn\'t be read: {e(str(ex)[:120])}</p>'
    w = rep["windows"]["7"]
    rows = ""
    for mode, s in sorted(w.items()):
        rate = s["success_rate"]
        rate_text = "-" if rate is None else f"{rate:g}%"
        late = " late" if rate is not None and rate < 90 else ""
        rows += (f'<li class="strip"><p class="strip-title">{e(mode)}</p><div class="meta">'
                 f'<span class="tag{late}">{rate_text} of {s["runs"]}</span>'
                 f'<span class="tag">median {e(kr_mod.fmt_secs(s["median_seconds"]))}</span></div></li>')
    rows = rows or '<li class="empty">No scheduled runs in the last 7 days.</li>'
    alerts = "".join(f"<li>{e(a)}</li>" for a in rep["alerts"])
    return (f'<ul class="strips">{rows}</ul>'
            + (f'<p class="meta">Alerts:</p><ul>{alerts}</ul>' if alerts else '<p class="meta">No reliability alerts.</p>'))


def sprint_panel():
    """The Sprint panel; also saves today's points-left snapshot for the burndown."""
    path = KIT / "QUEUE.md"
    sp = kit_queue.sprint(path.read_text().splitlines()) if path.exists() else None
    if not sp or not sp["name"]:
        carry = (f'<p class="meta">Carried over: {e("; ".join(c["title"] for c in sp["carry"]))}</p>'
                 if sp and sp["carry"] else "")
        return ('<p class="empty">No sprint running. Start one with '
                '<code>todo sprint start &lt;name&gt; &lt;start&gt; &lt;end&gt;</code>.</p>' + carry)
    total, done_pts = kit_queue.sprint_points(sp)
    hist_file = KIT / ".install/cache/sprint-history.json"
    try:
        hist_all = json.loads(hist_file.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        hist_all = {}
    key = f'{sp["name"]}|{sp["start"]:%Y-%m-%d}'
    hist = hist_all.setdefault(key, {})
    if sp["start"] <= TODAY <= sp["end"] + dt.timedelta(days=1):
        hist[f"{TODAY:%Y-%m-%d}"] = total - done_pts
        try:
            hist_file.parent.mkdir(parents=True, exist_ok=True)
            hist_file.write_text(json.dumps(hist_all, indent=1))
        except OSError:
            pass
    left = (sp["end"] - TODAY).days
    days_text = (f"{left} day{'s' if left != 1 else ''} left" if left > 0 else
                 "ends today" if left == 0 else f"ended {abs(left)} day{'s' if left != -1 else ''} ago")
    by = {}
    for it in sp["items"]:
        st = "done" if it["done"] else it["status"]
        by.setdefault(st, []).append(it)
    rows = "".join(
        f'<li class="strip"><p class="strip-title">{"&#10003; " if it["done"] else ""}{e(it["title"])}</p>'
        f'<div class="meta"><span class="tag">{e(it["size"])}</span>'
        f'<span class="tag{" late" if it["status"] == "blocked" else ""}">{e("done" if it["done"] else it["status"])}</span></div></li>'
        for it in sp["items"]) or '<li class="empty">No items yet. Add one with <code>todo sprint add</code>.</li>'
    counts = ", ".join(f"{len(v)} {k}" for k, v in sorted(by.items()))
    return (f'<p class="next-label">Sprint {e(sp["name"])}</p>'
            f'<p class="meta">{sp["start"]:%d-%b} to {sp["end"]:%d-%b-%Y} &middot; {days_text} &middot; '
            f'{done_pts}/{total} points done' + (f" &middot; {e(counts)}" if counts else "") + '</p>'
            + burndown_svg(sp, total, hist) + f'<ul class="strips">{rows}</ul>')


def health_score():
    """(badge, Health panel lines, score dict): the one-number health score (shared/kit_health.py)."""
    try:
        res = kit_health.score(KIT, TODAY)
        return kit_health.badge(res), kit_health.panel(res), res
    except Exception as ex:  # noqa: BLE001  (the score must never stop the page)
        return "", f'<p class="empty">Health score couldn\'t be worked out: {e(str(ex)[:120])}</p>', None


def add_badge(page, badge):
    """A template from before the health badge has no $health_badge: put it just after the page's first heading."""
    i = page.find("</h1>")
    return page[:i + 5] + badge + page[i + 5:] if i >= 0 and badge else page


def reviews_panel():
    """The Reviews panel: each project with review notes, its readiness for the review board, and links to the
    notes and decisions (kit-review-loop status). Run the loop from kit-settings ui's Review loop section."""
    import importlib.machinery, importlib.util
    path = KIT / ".install/shared/bin/kit-review-loop"
    if not path.exists():
        path = pathlib.Path(__file__).resolve().parent / "bin/kit-review-loop"
    if not path.exists():
        return '<p class="empty">kit-review-loop isn\'t installed.</p>'
    try:
        loader = importlib.machinery.SourceFileLoader("kit_review_loop_dash", str(path))
        spec = importlib.util.spec_from_loader("kit_review_loop_dash", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        projects = mod.status_all(limit=8)
    except Exception as ex:  # noqa: BLE001
        return f'<p class="empty">Reviews couldn\'t be read: {e(str(ex)[:120])}</p>'
    if not projects:
        return ('<p class="empty">No review notes yet. Start a review loop from <code>kit-settings ui</code> '
                '(Review loop), or run <code>kit-review-loop run PROJECT DRAFT</code>.</p>')
    rows = ""
    for p in projects:
        sc = p["score"]
        cls = "" if sc["verdict"] == "ready" else " soon" if sc["verdict"] == "almost" else " late"
        links = " ".join(f'<a href="{e(pathlib.Path(n["path"]).as_uri())}">{e(n["label"])}</a>' for n in p["links"])
        rows += (f'<li class="strip"><p class="strip-title">{e(p["project"])}</p><div class="meta">'
                 f'<span class="tag{cls}">{e(sc["headline"])}</span>'
                 f'<span class="added">last review {e(p["last"])}</span></div>'
                 + (f'<ul class="detail"><li>{links}</li></ul>' if links else "") + "</li>")
    return (f'<ul class="strips">{rows}</ul><p class="meta">Run the loop in one click from <code>kit-settings ui</code> '
            '(Review loop); <code>kit-review-loop score PROJECT</code> explains a score.</p>')


def add_settings(page, panel):
    """A template from before the Settings panel has no $settings: add the panel at the end of its main area."""
    return add_panel(page, "settings", "Settings", panel)


def add_panel(page, pid, title, panel):
    """Add a panel at the end of the template's main area (for sections newer than the template)."""
    block = f'<section class="panel" id="{pid}" aria-labelledby="p-{pid}"><h2 id="p-{pid}">{title}</h2>{panel}</section>'
    for mark in ("</main>", "</body>"):
        i = page.rfind(mark)
        if i >= 0:
            return page[:i] + block + "\n" + page[i:]
    return page + block


def main(argv):
    template_arg, argv = kit_template.args_template(argv)
    me = owner()
    lanes = parse_queue()
    mine = lanes.get(me, [])
    order = sorted(mine, key=lambda i: (i["due"] is None, i["due"] or TODAY))
    nxt = order[0] if order else None
    hero = (f'<p class="next-label">Next for you</p><p class="next">{e(nxt["title"])}</p>'
            f'<div class="meta">{due_tag(nxt["due"])}</div>') if nxt else \
        '<p class="next-label">Next for you</p><p class="next">Your list is clear. Add something with <code>todo</code>.</p>'
    checks = health()
    bad = [c for c in checks if c[0] != "ok"]
    health_html = "".join(
        f'<li class="check {c[0]}"><span class="light" aria-label="{c[0]}"></span>'
        f'<span class="cname">{e(c[1])}</span><span class="cdetail">{e(c[2])}</span></li>'
        for c in (bad + [c for c in checks if c[0] == "ok"]))
    badge, score_html, _score = health_score()
    audit_banner, audit_html = audit()
    audit_banner = state_banners() + audit_banner
    grid = runs()
    head = "".join(f"<th scope=col>{d:%a}<br>{d:%d}</th>" for d in grid)
    rows = ""
    for mode, label in (("morning", "Morning"), ("open", "After open"), ("weekly", "Weekly")):
        cells = ""
        for d, modes in grid.items():
            state = modes.get(mode, "")
            title = {"texted": "Delivered", "failed": "Didn't send", "ran": "Ran",
                     "closed": "Market closed", "": "No run"}[state]
            cells += f'<td><span class="cell {state or "none"}" title="{title}" aria-label="{title}"></span></td>'
        rows += f"<tr><th scope=row>{label}</th>{cells}</tr>"

    values = {
        "now_iso": f"{NOW:%Y-%m-%dT%H:%M}", "now_text": f"{NOW:%A %d-%b, %H:%M}",
        "audit_banner": audit_banner, "hero": hero,
        "lane_you": lane(me, "you", mine, "Nothing on your list."),
        "lane_kit": lane("Kit", "kit", lanes.get("Kit", []), "Nothing on Kit's list."),
        "lane_wait": lane("Waiting on others", "wait", lanes.get("Waiting on others", []),
                          "Nobody owes you anything."),
        "schedule": schedule(), "briefs": brief_text(), "health_checks": health_html,
        "runs_head": head, "runs_rows": rows, "audit": audit_html, "staff": staff(),
        "sprint": sprint_panel(), "reliability": reliability_panel(),
        "health_badge": badge, "health_score": score_html, "reviews": reviews_panel(),
    }
    tpl = kit_template.find("dashboard.html", template_arg, "KIT_DASHBOARD_TEMPLATE")
    text = tpl.read_text(encoding="utf-8") if tpl else FALLBACK
    settings = kit_settings.dashboard_panel(KIT)
    if re.search(r"\$\{?settings\b", text):
        values["settings"] = settings
    # Sections added after a template was copied: put them in anyway, so an owner's copy still shows them.
    late = {k: values.pop(k) for k in ("health_badge", "health_score", "reviews")
            if not re.search(r"\$\{?" + k + r"\b", text)}
    if "health_score" in late and _score:
        values["health_checks"] = "".join(
            f'<li class="check {"ok" if p["score"] >= p["max"] * 0.9 else "warn" if p["score"] >= p["max"] * 0.7 else "fail"}">'
            f'<span class="light"></span><span class="cname">Health score: {e(p["name"])} {p["score"]:g}/{p["max"]:g}</span>'
            f'<span class="cdetail">{e(p["detail"])}</span></li>' for p in _score["parts"]) + values["health_checks"]
    page = kit_template.render(text, values, str(tpl) if tpl else "built-in page")
    if "settings" not in values:
        page = add_settings(page, settings)
    if "health_badge" in late:
        page = add_badge(page, late["health_badge"])
    if "reviews" in late:
        page = add_panel(page, "reviews", "Reviews", late["reviews"])
    OUT.write_text(page)
    if "--open" in argv:
        if os.name == "nt":
            os.startfile(str(OUT))  # noqa: S606  (Windows-only)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(OUT)])
        else:
            subprocess.run(["xdg-open", str(OUT)])
    print(f"Dashboard: {OUT}")


if __name__ == "__main__":
    main(sys.argv[1:])

#!/usr/bin/env python3
"""Build Kit's dashboard: ~/Claude/Agents/kit/dashboard.html (open it in any browser).

  python3 ~/Claude/Agents/kit/.install/dashboard.py          rebuild
  python3 ~/Claude/Agents/kit/.install/dashboard.py --open   rebuild and open

The scheduled runs and the todo command rebuild it; the page reloads itself every 5 minutes.
"""
import datetime as dt
import html
import json
import pathlib
import re
import subprocess
import sys

HOME = pathlib.Path.home()
KIT = HOME / "Claude/Agents/kit"
OUT = KIT / "dashboard.html"
LOGS = KIT / ".install/morning/logs"
NOW = dt.datetime.now()
TODAY = NOW.date()
e = html.escape


def owner():
    cfg = KIT / ".install/morning/config"
    if cfg.exists():
        m = re.search(r'^OWNER_NAME="?([^"\n]+)"?', cfg.read_text(), re.M)
        if m:
            return m.group(1).strip()
    return "You"


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
        r = subprocess.run([sys.executable, str(KIT / ".install/doctor.py")],
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
            elif mode and ln.startswith("== texted"):
                grid[day][mode] = "texted"
            elif mode and (ln.startswith("== text failed") or ln.startswith("== sent failure")):
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


def schedule():
    try:
        r = subprocess.run([str(HOME / ".local/bin/kitcal"), "events", "--from", "today", "--to", "today"],
                           capture_output=True, text=True, timeout=60)
        evs = json.loads(r.stdout or "[]")
    except Exception:  # noqa: BLE001
        return '<p class="empty">Calendar unavailable. Run kitcal calendars to check access.</p>'
    if not evs:
        return '<p class="empty">Nothing on the calendar today.</p>'
    rows = []
    for ev in evs:
        if ev.get("all_day"):
            when = "All day"
        else:
            a = dt.datetime.strptime(ev["start"], "%Y-%m-%d %H:%M")
            b = dt.datetime.strptime(ev["end"], "%Y-%m-%d %H:%M")
            when = f"{a:%-I:%M}–{b:%-I:%M %p}"
        cal = ev.get("calendar", "").split("|")[0]
        rows.append(f'<li><time>{e(when)}</time> {e(ev.get("title", ""))} <span class="cal">{e(cal)}</span></li>')
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


def main(argv):
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
    grid = runs()
    head = "".join(f"<th scope=col>{d:%a}<br>{d:%d}</th>" for d in grid)
    rows = ""
    for mode, label in (("morning", "Morning"), ("open", "After open"), ("weekly", "Weekly")):
        cells = ""
        for d, modes in grid.items():
            state = modes.get(mode, "")
            title = {"texted": "Texted", "failed": "Didn't send", "ran": "Ran",
                     "closed": "Market closed", "": "No run"}[state]
            cells += f'<td><span class="cell {state or "none"}" title="{title}" aria-label="{title}"></span></td>'
        rows += f"<tr><th scope=row>{label}</th>{cells}</tr>"

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>Kit</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600&family=Barlow+Condensed:wght@500;600;700&display=swap">
<style>
:root {{
  --board: #E3E7EA; --strip: #FFFFFF; --ink: #15202B; --muted: #566573; --line: #C9D0D6;
  --you: #1F4E79; --kit: #C1121F; --wait: #B7791F; --ok: #2E7D4F;
  --cond: "Barlow Condensed", "Arial Narrow", sans-serif; --body: "Barlow", system-ui, sans-serif;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --board: #11171D; --strip: #1A222A; --ink: #E4EAEE; --muted: #9AA8B4; --line: #2A353F;
          --you: #6FA8DC; --kit: #F0464F; --wait: #E3A73C; --ok: #5CC28A; }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--board); color: var(--ink); font: 16px/1.5 var(--body); }}
.scanner {{ height: 6px; background: var(--strip); overflow: hidden; position: relative; }}
.scanner::after {{ content: ""; position: absolute; top: 0; left: -30%; width: 30%; height: 100%;
  background: linear-gradient(90deg, transparent, var(--kit), transparent);
  animation: sweep 1.6s ease-in-out 2 alternate both; }}
@keyframes sweep {{ to {{ left: 100%; }} }}
@media (prefers-reduced-motion: reduce) {{ .scanner::after {{ animation: none; left: 35%; }} }}
header {{ display: flex; justify-content: space-between; align-items: baseline; gap: 1rem;
  padding: 1.25rem 2rem 0; }}
header h1 {{ font: 700 2rem/1 var(--cond); margin: 0; letter-spacing: .02em; }}
header time {{ color: var(--muted); font-family: var(--cond); font-size: 1.1rem; }}
.hero {{ padding: .75rem 2rem 1.5rem; border-bottom: 1px solid var(--line); }}
.next-label {{ margin: 0; color: var(--muted); }}
.next {{ font: 600 clamp(1.6rem, 4vw, 2.6rem)/1.1 var(--cond); margin: .15rem 0 .4rem; max-width: 30ch; }}
main {{ padding: 1.5rem 2rem 3rem; display: grid; gap: 1.75rem; }}
.lanes {{ display: grid; grid-template-columns: 1.4fr 1fr 1fr; gap: 1.25rem; align-items: start; }}
.lane h2 {{ font: 600 1.35rem/1.2 var(--cond); margin: 0 0 .6rem; display: flex; gap: .5rem; align-items: baseline; }}
.count {{ color: var(--muted); font-weight: 500; }}
.strips {{ list-style: none; margin: 0; padding: 0; display: grid; gap: .5rem; }}
.strip {{ background: var(--strip); border-left: 6px solid var(--lane); padding: .6rem .8rem .65rem; }}
.lane.you {{ --lane: var(--you); }} .lane.kit {{ --lane: var(--kit); }} .lane.wait {{ --lane: var(--wait); }}
.strip-title {{ margin: 0; font: 600 1.15rem/1.25 var(--cond); }}
.meta {{ display: flex; flex-wrap: wrap; gap: .4rem .75rem; align-items: center; margin-top: .2rem;
  font-size: .9rem; color: var(--muted); }}
.tag {{ font-weight: 500; }} .tag.soon {{ color: var(--wait); }} .tag.late {{ color: var(--kit); font-weight: 600; }}
.detail {{ margin: .35rem 0 0; padding-left: 1rem; font-size: .92rem; color: var(--muted); }}
.empty {{ color: var(--muted); padding: .6rem 0; list-style: none; }}
.panels {{ display: grid; grid-template-columns: 1.4fr 1fr; gap: 1.25rem; align-items: start; }}
.panel {{ background: var(--strip); padding: 1rem 1.2rem 1.2rem; }}
.panel h2 {{ font: 600 1.35rem/1.2 var(--cond); margin: 0 0 .75rem; }}
.brief h3 {{ font: 600 1.05rem/1.2 var(--cond); margin: 0 0 .3rem; }}
.when {{ color: var(--muted); font-weight: 500; }}
.brief + .brief {{ margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--line); }}
pre {{ white-space: pre-wrap; font: .95rem/1.5 var(--body); margin: 0; max-width: 75ch; }}
.full a {{ color: var(--you); font-weight: 600; }}
a:focus-visible {{ outline: 3px solid var(--you); outline-offset: 2px; }}
.checks {{ list-style: none; margin: 0; padding: 0; display: grid; gap: .45rem; }}
.check {{ display: grid; grid-template-columns: .8rem 1fr; gap: 0 .6rem; align-items: baseline; }}
.light {{ width: .65rem; height: .65rem; border-radius: 50%; background: var(--ok); }}
.check.warn .light {{ background: var(--wait); }} .check.fail .light {{ background: var(--kit); }}
.cname {{ font-weight: 600; }} .cdetail {{ grid-column: 2; color: var(--muted); font-size: .9rem; }}
.check.ok .cdetail {{ display: none; }}
table {{ border-collapse: collapse; margin-top: 1.25rem; font-family: var(--cond); }}
th, td {{ padding: .25rem .4rem; text-align: center; font-weight: 500; }}
th[scope=row] {{ text-align: left; padding-right: .8rem; }}
thead th {{ color: var(--muted); line-height: 1.1; }}
.cell {{ display: inline-block; width: 1.1rem; height: 1.1rem; border: 2px solid var(--line); }}
.cell.texted {{ background: var(--ok); border-color: var(--ok); }}
.cell.failed {{ border-color: var(--kit); background: transparent; }}
.cell.ran, .cell.closed {{ background: var(--line); }}
.stack {{ display: grid; gap: 1.25rem; align-content: start; }}
.sched {{ list-style: none; margin: 0; padding: 0; display: grid; gap: .45rem; }}
.sched time {{ font: 600 1rem var(--cond); display: inline-block; min-width: 7.5rem; }}
.sched .cal {{ color: var(--muted); font-size: .88rem; }}
.staff {{ list-style: none; padding: 0; margin: 0; display: grid; gap: .35rem; }}
.agent {{ font: 600 1.05rem var(--cond); text-transform: capitalize; margin-right: .35rem; }}
code {{ font-size: .9em; }}
@media (max-width: 900px) {{ .lanes, .panels {{ grid-template-columns: 1fr; }}
  header, .hero, main {{ padding-left: 1rem; padding-right: 1rem; }} }}
</style></head>
<body>
<div class="scanner" aria-hidden="true"></div>
<header><h1>Kit</h1><time datetime="{NOW:%Y-%m-%dT%H:%M}">{NOW:%A %d-%b, %H:%M}</time></header>
<div class="hero">{hero}</div>
<main>
<div class="lanes">
{lane(me, "you", mine, "Nothing on your list.")}
{lane("Kit", "kit", lanes.get("Kit", []), "Nothing on Kit's list.")}
{lane("Waiting on others", "wait", lanes.get("Waiting on others", []), "Nobody owes you anything.")}
</div>
<div class="panels">
<div class="stack"><section class="panel" aria-labelledby="p-today"><h2 id="p-today">Today</h2>{schedule()}</section>
<section class="panel" aria-labelledby="p-brief"><h2 id="p-brief">Briefs</h2>{brief_text()}</section></div>
<section class="panel" aria-labelledby="p-health"><h2 id="p-health">Health</h2>
<ul class="checks">{health_html}</ul>
<table aria-label="Scheduled runs, last seven days"><thead><tr><th></th>{head}</tr></thead><tbody>{rows}</tbody></table>
</section>
</div>
<section class="panel" aria-labelledby="p-staff"><h2 id="p-staff">Kit's staff</h2><ul class="staff">{staff()}</ul></section>
</main>
</body></html>
"""
    OUT.write_text(page)
    if "--open" in argv:
        subprocess.run(["open", str(OUT)])
    print(f"Dashboard: {OUT}")


if __name__ == "__main__":
    main(sys.argv[1:])

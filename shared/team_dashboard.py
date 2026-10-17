#!/usr/bin/env python3
"""Build the team dashboard: one read-only HTML page from the records several Kits publish.

  python3 ~/Claude/Agents/kit/.install/shared/team_dashboard.py              sync, then render the cache
  python3 ~/Claude/Agents/kit/.install/shared/team_dashboard.py --no-sync    render the cache as it is
  python3 ~/Claude/Agents/kit/.install/shared/team_dashboard.py --source DIR --source DIR2
  python3 ~/Claude/Agents/kit/.install/shared/team_dashboard.py --out page.html --open

By default it pulls records from the shared folder in sharing.md (or, with no Shared root, this
Kit's outbox) into the local cache (.install/cache/team.db, see shared/kit_transport.py), then
renders the page from the cache. Each --source instead reads a folder directly: a shared folder
(one with a kits/ folder) is read through the transport's checks; any other folder is searched
recursively, one record per .json file. The page shows status snapshots by project, open waiting items and demand roll-ups,
recent decisions, shared lessons, artifact and handoff pointers, how old each Kit's latest record
is, and warnings for records it couldn't accept. Filters by project and Kit need JavaScript;
without it, everything shows. No external assets. Default output:
~/Claude/Agents/kit/team-dashboard.html.

It accepts the current major version of each record schema and the previous one; records in a
newer minor version are shown with unknown fields ignored. Record formats:
shared/records/README.md.
"""
import argparse
import datetime as dt
import html
import json
import os
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import kit_records as kr  # noqa: E402
import kit_template  # noqa: E402
import kit_transport as kt  # noqa: E402

HOME = pathlib.Path.home()
KIT = kt.KIT
OUT = KIT / "team-dashboard.html"
NOW = dt.datetime.now(dt.timezone.utc)
TODAY = dt.date.today()
MAX_BYTES = 256 * 1024
e = html.escape


# ---------- loading ----------

accept = kr.accept   # the version rules live in kit_records, shared with kit_transport


def load(sources, schemas):
    recs, warnings = {}, []
    for src in sources:
        if (src / "kits").is_dir():
            got, warns = kt.FolderTransport(src, layout="shared").scan(schemas)
            warnings += warns
            for rec, _ in got:
                prev = recs.get(rec["id"])
                if prev and kr.parse_iso(prev["updated"]) >= kr.parse_iso(rec["updated"]):
                    continue
                recs[rec["id"]] = rec
            continue
        if not src.is_dir():
            warnings.append(("source", str(src), "folder not found"))
            continue
        for f in sorted(src.rglob("*.json")):
            where = f"{src.name}/{f.relative_to(src).as_posix()}"
            try:
                if f.stat().st_size > MAX_BYTES:
                    raise ValueError("file too large")
                rec = json.loads(f.read_text())
            except (OSError, ValueError) as ex:
                warnings.append(("file", where, f"unreadable: {ex}"))
                continue
            ok, why = accept(rec, schemas) if isinstance(rec, dict) else (False, "not a JSON object")
            if why:
                warnings.append(("schema" if ok else "rejected", where, why))
            if not ok:
                continue
            prev = recs.get(rec["id"])
            if prev:
                warnings.append(("duplicate", rec["id"], "found in more than one place; showing the newest"))
                if kr.parse_iso(prev["updated"]) >= kr.parse_iso(rec["updated"]):
                    continue
            recs[rec["id"]] = rec
    return list(recs.values()), warnings


# ---------- formatting ----------

def age(when):
    secs = (NOW - when).total_seconds()
    if secs < 3600:
        return "under an hour"
    if secs < 86400:
        return f"{int(secs // 3600)} h"
    days = int(secs // 86400)
    return f"{days} day{'s' if days != 1 else ''}"


def day(s):
    try:
        return dt.date.fromisoformat(s).strftime("%d-%b-%Y") if s else ""
    except ValueError:
        return ""


def attrs(r):
    return f'data-project="{e(r["project"])}" data-kit="{e(r["kit_id"])}"'


def chips(r):
    conf = '<span class="tag conf">Confidential</span>' if r["classification"] == "confidential" else ""
    return f'<span class="kit-chip">{e(r["kit_id"])}</span>{conf}'


def items(lst, empty=""):
    return "<ul>" + "".join(f"<li>{e(x)}</li>" for x in lst) + "</ul>" if lst else empty


HEALTH = {"on-track": ("ok", "On track"), "at-risk": ("soon", "At risk"),
          "off-track": ("late", "Off track"), "unknown": ("", "")}


def snapshot(r):
    b = r["body"]
    css, label = HEALTH.get(b.get("health"), ("", ""))
    health = f'<span class="tag {css}">{label}</span>' if label else ""
    asof = f'<span class="added">As of {day(b.get("as_of"))}</span>' if b.get("as_of") else ""
    blocked = [f'{x["item"]}' + (f' (on {x["waiting_on"]})' if x.get("waiting_on") else "")
               for x in b.get("blocked", [])]
    parts = [(f'<p class="headline">{e(b["headline"])}</p>' if b.get("headline") else ""),
             (f'<h4>In progress</h4>{items(b["in_progress"])}' if b.get("in_progress") else ""),
             (f'<h4>Blocked</h4>{items(blocked)}' if blocked else ""),
             (f'<h4>Next</h4>{items(b["next"])}' if b.get("next") else "")]
    if not any(parts) and not b.get("waiting"):
        return ""
    waiting = f'<p class="added">{len(b["waiting"])} waiting item(s), listed below</p>' if b.get("waiting") else ""
    return (f'<li class="strip" {attrs(r)}><div class="meta">{chips(r)}{health}{asof}</div>'
            f'{"".join(parts)}{waiting}</li>')


def rollup(r):
    b = r["body"]
    open_items = [i for i in b.get("items", []) if i.get("open")]
    overdue = [i for i in open_items if i.get("due") and dt.date.fromisoformat(i["due"]) < TODAY]
    soon = [i for i in open_items if i.get("due") and 0 <= (dt.date.fromisoformat(i["due"]) - TODAY).days <= 14]
    tags = (f'<span class="tag">{b.get("open", 0)} open of {b.get("total", 0)}</span>'
            + (f'<span class="tag late">{len(overdue)} overdue</span>' if overdue else "")
            + (f'<span class="tag soon">{len(soon)} due in 14 days</span>' if soon else ""))
    rows = "".join(f'<li><b>{e(i["number"])}</b> {e(i["title"])} <span class="added">{e(i["status"])}'
                   f'{", due " + day(i["due"]) if i.get("due") else ""}</span></li>' for i in open_items[:6])
    more = f'<p class="added">and {len(open_items) - 6} more</p>' if len(open_items) > 6 else ""
    asof = f'<span class="added">Checked {day(b.get("as_of"))}</span>' if b.get("as_of") else ""
    return (f'<li class="strip demand" {attrs(r)}><div class="meta">{chips(r)}<span class="tag">Demands</span>'
            f'{tags}{asof}</div><ul>{rows}</ul>{more}</li>')


def projects(recs):
    by = {}
    for r in recs:
        if r["schema"] in ("status-snapshot", "demand-rollup"):
            by.setdefault(r["project"], []).append(r)
    cards = []
    for proj in sorted(by):
        rs = sorted(by[proj], key=lambda r: (r["schema"] != "status-snapshot", r["kit_id"], r["id"]))
        body = "".join(snapshot(r) if r["schema"] == "status-snapshot" else rollup(r) for r in rs)
        if body:
            cards.append(f'<section class="lane card" data-project="{e(proj)}" aria-label="{e(proj)}">'
                         f'<h3>{e(proj)}</h3><ul class="strips">{body}</ul></section>')
    return "".join(cards) or '<p class="empty">No status snapshots or demand roll-ups yet.</p>'


def table(head, rows, empty):
    if not rows:
        return f'<p class="empty">{e(empty)}</p>'
    th = "".join(f"<th scope=col>{e(h)}</th>" for h in head)
    return f'<div class="scroll"><table><thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def waiting(recs):
    rows = []
    for r in recs:
        if r["schema"] != "status-snapshot":
            continue
        for w in r["body"].get("waiting", []):
            since = w.get("since")
            days = (TODAY - dt.date.fromisoformat(since)).days if since else None
            late = w.get("due") and dt.date.fromisoformat(w["due"]) < TODAY
            rows.append((w.get("due") or "9999", f'<tr {attrs(r)}><td>{e(w["item"])}</td><td>{e(w["waiting_on"])}</td>'
                         f'<td>{day(since)}{f" ({days} d)" if days is not None else ""}</td>'
                         f'<td class="{"late" if late else ""}">{day(w.get("due"))}</td>'
                         f'<td>{e(r["project"])}</td><td>{chips(r)}</td></tr>'))
    return table(["Item", "Waiting on", "Since", "Due", "Project", "Kit"],
                 [x[1] for x in sorted(rows, key=lambda x: x[0])], "Nothing waiting on anyone.")


def decisions(recs):
    ds = sorted((r for r in recs if r["schema"] == "decision"),
                key=lambda r: (r["body"].get("decided") or r["updated"][:10]), reverse=True)[:40]
    out = []
    for r in ds:
        b = r["body"]
        css = {"current": "ok", "proposed": "soon", "superseded": "muted"}[b["status"]]
        extra = "".join(f"<p><b>{k}:</b> {e(v)}</p>" for k, v in
                        (("Why", b.get("why")), ("Options", ", ".join(b.get("options", []))),
                         ("Revisit", b.get("revisit")), ("Sources", ", ".join(b.get("sources", [])))) if v)
        out.append(f'<li class="strip" {attrs(r)}><p class="strip-title">{e(b["title"])}</p>'
                   f'<div class="meta">{chips(r)}<span class="tag {css}">{b["status"].capitalize()}</span>'
                   f'<span class="added">{day(b.get("decided"))}</span><span class="added">{e(r["project"])}</span></div>'
                   f'<p>{e(b["summary"])}</p>{extra}</li>')
    return f'<ul class="strips">{"".join(out)}</ul>' if out else '<p class="empty">No shared decisions yet.</p>'


def lessons(recs):
    out = []
    for r in sorted((r for r in recs if r["schema"] == "lesson"), key=lambda r: r["updated"], reverse=True):
        b = r["body"]
        out.append(f'<li class="strip" {attrs(r)}><p class="strip-title">{e(b["title"])}</p>'
                   f'<div class="meta">{chips(r)}<span class="added">{e(r["owner_role"])}</span></div>'
                   f'<p>{e(b["rule"])}</p>'
                   + (f'<p><b>Why:</b> {e(b["why"])}</p>' if b.get("why") else "")
                   + (f'<p><b>How to apply:</b> {e(b["how_to_apply"])}</p>' if b.get("how_to_apply") else "")
                   + "</li>")
    return f'<ul class="strips">{"".join(out)}</ul>' if out else '<p class="empty">No shared lessons yet.</p>'


def artifacts(recs):
    rows = []
    for r in sorted((r for r in recs if r["schema"] == "artifact-pointer"),
                    key=lambda r: (r["project"], r["body"]["accession"])):
        b = r["body"]
        rows.append(f'<tr {attrs(r)}><td>{e(b["accession"])}</td><td>{e(b["doc_number"])}</td><td>{e(b["title"])}</td>'
                    f'<td>{e(b["type"])}</td><td>{e(b["status"])}</td><td>{e(b["version"])}</td>'
                    f'<td>{day(b.get("last_update"))}</td><td><code>{e(b.get("path") or "")}</code></td>'
                    f'<td>{e(r["project"])}</td><td>{chips(r)}</td></tr>')
    return table(["Accession", "Doc no.", "Title", "Type", "Status", "Version", "Updated", "Library path",
                  "Project", "Kit"], rows, "No artifact pointers yet.")


def handoffs(recs):
    rows = []
    for r in sorted((r for r in recs if r["schema"] == "handoff-pointer"),
                    key=lambda r: r["body"].get("date") or "", reverse=True):
        b = r["body"]
        rows.append(f'<tr {attrs(r)}><td>{day(b.get("date"))}</td><td>{e(b["title"])}</td>'
                    f'<td>{e(b["where_it_stands"])}</td><td><code>{e(b.get("path") or "")}</code></td>'
                    f'<td>{e(r["project"])}</td><td>{chips(r)}</td></tr>')
    return table(["Date", "Brief", "Where it stands", "Library path", "Project", "Kit"], rows, "No handoff briefs yet.")


def kits(recs, stale_days):
    by = {}
    for r in recs:
        by.setdefault(r["kit_id"], []).append(r)
    rows = []
    for kid in sorted(by):
        rs = by[kid]
        latest = max(kr.parse_iso(r["updated"]) for r in rs)
        old = (NOW - latest).days >= stale_days
        roles = ", ".join(sorted({r["owner_role"] for r in rs}))
        rows.append(f'<tr data-kit="{e(kid)}"><td><span class="kit-chip">{e(kid)}</span></td><td>{e(roles)}</td>'
                    f'<td>{len(rs)}</td><td>{latest:%d-%b-%Y %H:%M} UTC</td>'
                    f'<td class="{"late" if old else ""}">{age(latest)}{" (stale)" if old else ""}</td></tr>')
    return table(["Kit", "Owner role", "Records", "Latest record", "Age"], rows, "No records found.")


def warn_list(warnings):
    if not warnings:
        return '<p class="empty">All records accepted.</p>'
    return '<ul class="checks">' + "".join(
        f'<li class="check {"warn" if kind in ("schema", "duplicate") else "fail"}"><span class="light"></span>'
        f'<span class="cname">{e(where)}</span><span class="cdetail">{e(why)}</span></li>'
        for kind, where, why in warnings) + "</ul>"


def options(values, label):
    return f'<option value="">All {label}</option>' + "".join(f'<option>{e(v)}</option>' for v in values)


JS = """
(function () {
  var p = document.getElementById('f-project'), k = document.getElementById('f-kit');
  function apply() {
    document.querySelectorAll('[data-project],[data-kit]').forEach(function (el) {
      var okP = !p.value || !el.dataset.project || el.dataset.project === p.value;
      var okK = !k.value || !el.dataset.kit || el.dataset.kit === k.value;
      el.hidden = !(okP && okK);
    });
    document.querySelectorAll('.card').forEach(function (c) {
      if (!c.hidden && !c.querySelector('.strip:not([hidden])')) { c.hidden = true; }
    });
  }
  p.addEventListener('change', apply); k.addEventListener('change', apply);
})();
"""



TEMPLATE_ARG = None  # set from --template in main()

# Used only when no template is found: plain, but every section still shows.
FALLBACK = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>Kit team dashboard</title><style>body{font:16px/1.5 system-ui,Arial,sans-serif;margin:1.5rem}</style></head>
<body><h1>Kit team</h1><p>$record_count records from $kit_count Kit(s), <time datetime="$now_iso">$now_text</time>
(built-in page: no template found)</p>$banner
<p><label for="f-project">Project</label> <select id="f-project">$project_options</select>
<label for="f-kit">Kit</label> <select id="f-kit">$kit_options</select> Sources: $sources</p>
<h2>Projects</h2>$projects<h2>Waiting on others</h2>$waiting<h2>Recent decisions</h2>$decisions
<h2>Shared lessons</h2>$lessons<h2>Artifacts</h2>$artifacts<h2>Handoff briefs</h2>$handoffs
<h2>Kits</h2>$kits<h2>Warnings ($warning_count)</h2>$warnings<script>$script</script>
</body></html>
"""

def page(recs, warnings, sources, stale_days):
    conf = any(r["classification"] == "confidential" for r in recs)
    banner = ('<p class="banner">Contains confidential records. Share this page only with people cleared '
              'for every project on it.</p>') if conf else ""
    proj_opts = options(sorted({r["project"] for r in recs}), "projects")
    kit_opts = options(sorted({r["kit_id"] for r in recs}), "Kits")
    srcs = ", ".join(s.name or str(s) for s in sources)
    local = dt.datetime.now()
    values = {
        "banner": banner, "record_count": str(len(recs)), "kit_count": str(len({r["kit_id"] for r in recs})),
        "now_iso": f"{local:%Y-%m-%dT%H:%M}", "now_text": f"{local:%A %d-%b, %H:%M}",
        "project_options": proj_opts, "kit_options": kit_opts, "sources": e(srcs),
        "projects": projects(recs), "waiting": waiting(recs), "decisions": decisions(recs),
        "lessons": lessons(recs), "artifacts": artifacts(recs), "handoffs": handoffs(recs),
        "kits": kits(recs, stale_days), "warning_count": str(len(warnings)), "warnings": warn_list(warnings),
        "script": JS,
    }
    tpl = kit_template.find("team-dashboard.html", TEMPLATE_ARG, "KIT_TEAM_DASHBOARD_TEMPLATE")
    return kit_template.render(tpl.read_text(encoding="utf-8") if tpl else FALLBACK, values,
                               str(tpl) if tpl else "built-in page")


def main(argv):
    ap = argparse.ArgumentParser(prog="team_dashboard.py", description=__doc__.split("\n")[0])
    ap.add_argument("--source", action="append", help="record folder to read directly (repeatable)")
    ap.add_argument("--cache", default=str(kt.DEFAULT_DB), help="the local cache to sync and render from")
    ap.add_argument("--no-sync", action="store_true", help="render the cache without pulling first")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--stale-days", type=int, default=7, help="mark a Kit stale after this many days")
    ap.add_argument("--template", help="HTML template to render into (default: your copy, then the packaged one)")
    a = ap.parse_args(argv)
    global TEMPLATE_ARG
    TEMPLATE_ARG = a.template
    schemas = kr.load_schemas()
    if a.source:
        sources = [pathlib.Path(s).expanduser() for s in a.source]
        recs, warnings = load(sources, schemas)
    else:
        cache = kt.Cache(a.cache)
        transports = kt.sources(KIT)
        if not a.no_sync:
            cache.sync(transports, schemas)
        recs, warnings = cache.records(), cache.warnings()
        sources = [t.root for t in transports]
        cache.close()
    out = pathlib.Path(a.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(recs, warnings, sources, a.stale_days))
    if a.open:
        if os.name == "nt":
            os.startfile(str(out))  # noqa: S606  (Windows-only)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(out)])
        else:
            subprocess.run(["xdg-open", str(out)])
    print(f"Team dashboard: {out} ({len(recs)} records, {len(warnings)} warnings)")


if __name__ == "__main__":
    main(sys.argv[1:])

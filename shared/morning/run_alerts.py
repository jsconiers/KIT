#!/usr/bin/env python3
"""run_alerts.py: alerts for failed scheduled runs, cost, and Kit's monitors, kept like the connector outages.

  python3 run_alerts.py [--kit DIR] [--only runs|cost|<monitor>] [--no-track] [--no-dashboard]
                        [--json]
                        [--out briefs/alerts.txt] [--now YYYY-MM-DDTHH:MM]

Run at the end of every scheduled run (run.sh and run.ps1, all modes) and before the model in the
morning brief and the weekly review, so the brief can name what's open; `kit-alerts` shows and
recomputes the same alerts on demand. It reads only Kit's own logs, through kit-reliability (the
day logs, backup.log, sync.log) and kit-cost (the ledger, .install/logs/cost.jsonl). It never calls
a model or a connector, and it always exits 0: any error is reported on stderr and the run goes on.

Failed scheduled runs. For each run type (morning, weekly, worklist, eod, open, journal, backup,
sync), from kit-reliability's outcomes (a degraded brief counts as a success, since a brief still
arrived), an outage opens when
  - the run type failed RUN_FAIL_STREAK times in a row (default 2), or
  - it hasn't succeeded within its window: RUN_WINDOW_MORNING weekdays (2; SKIP_DAYS don't count,
    nor today before 08:15), RUN_WINDOW_WEEKLY days (8), RUN_WINDOW_SYNC hours (2),
    RUN_WINDOW_BACKUP days (2). RUN_WINDOW_WORKLIST, _EOD, _OPEN, _JOURNAL (days) are empty by
    default (no window). "0" or "off" turns a window off. Only run types that ran at all in the last
    90 days are watched. Sync successes come from the sync's change lines in sync.log and from
    .install/logs/sync.ok, which the sync writes after each clean run.
It adds one [work] item to the owner's section of QUEUE.md through `todo work` ("Fix Kit's <mode>
run, failing since DD-Mmm-YYYY (kit-reliability)", or "Check Kit's <mode> run, no success since
..."), once per outage, and raises the dashboard's red "Scheduled run" banner. The next success
clears it, with a "Recovered" line on the queue item for the owner to check off.

Cost (kit-cost). With COST_BUDGET_MONTHLY set:
  - warn: the month's projection is at or over COST_ALERT_PROJECTION x the budget (a fraction such
    as 0.9), or, when that's empty, over COST_WARN_PCT of it. Clears when the projection falls back
    under, or at the month's end.
  - stop: spend is at or over COST_STOP_PCT of the budget, so the non-essential runs skip and the
    morning brief may be degraded. Clears at the month's end (or if the budget is raised).
With no budget: spike, when one day's cost (today, or yesterday if today has none yet) is over
COST_SPIKE_FACTOR (default 3) times the median of the days with spend in the 14 days before it
(needs 3 such days). Clears when the latest day is back under, or at the month's end.
One queue item per level per month ("Review Kit's spend: ... (kit-cost)"), never repeated in the
same month, and a red "Cost" banner on the dashboard.

Monitors (roadmap F), each in its own module, recomputed with the others and time-limited by
MONITOR_TIMEOUT (seconds each, default 20); MONITOR_DRIFT, MONITOR_LIBRARY, MONITOR_WAITING,
MONITOR_GUARD="off" turn one off (and clear what it had open):
  drift    monitor_drift.py: agents whose live copy differs from the shipped one after normalising
           (owner name, model line), and live agents out of date in ~/.claude/agents (doctor's check).
           One alert and one queue item per kind of drift. `kit-alerts drift --diff <agent>` compares.
  library  monitor_library.py: published library folders against their indexes (unindexed or missing
           files, LIBRARY_UNINDEXED_MAX, LIBRARY_INDEX_MAX_DAYS; a queue item asks the librarian to
           reindex), and an inferred cloud-sync stall (LIBRARY_SYNC_MAX_DAYS; brief and banner only).
  waiting  monitor_waiting.py: waiting-on-others items and the owner's decisions older than
           WAITING_MAX_DAYS (7); a follow-up draft in briefs/followups/ for the former; no queue item.
  guard    monitor_guard.py: connector-guard integrity. The installed copies (~/.claude/agents) of the
           agents shipped with guard hooks still run all three hooks (pre, post, fail) against an
           existing connector-guard script; connector-guard.json is readable; its audit_dir exists and
           is writable (a probe file, removed at once; permission bits only on a dry run); and allowed
           calls have result records (kit-audit's no-result check, GUARD_NORESULT_HOURS,
           GUARD_WINDOW_DAYS). One alert listing every problem, one queue item per outage.

Files: briefs/alerts.json (the open alerts, for the dashboard and kit-alerts) and, with --out, one
line per open alert for the brief (empty when nothing is open). The connector outages stay in
briefs/connectors-alerts.json (connector_health.py). RUN_ALERTS="off" in the config turns this off
in the scheduled runs. To undo: set RUN_ALERTS="off" and delete briefs/alerts.json.
"""
import argparse
import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
import re
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.dirname(HERE)
BIN = os.path.join(SHARED, "bin")
DEFAULT_TODO = os.path.join(BIN, "todo")
RUN_TYPES = ("morning", "weekly", "worklist", "eod", "open", "journal", "backup", "sync")
WINDOWS = {"morning": "2", "weekly": "8", "sync": "2", "backup": "2"}   # weekdays, days, hours, days
UNIT = {"morning": "weekday", "sync": "hour"}                           # others: days
MORNING_DUE = dt.time(8, 15)
HORIZON_DAYS = 90


def short(text, n=100):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 3].rstrip() + "..."


def warn(msg):
    print(f"run_alerts: {msg}", file=sys.stderr)


def fmt(d):
    return d.strftime("%d-%b-%Y")


def money(x):
    return f"${x:,.2f}"


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


class Config:
    """KEY="value" lines from .install/shared/morning/config; the environment wins, as in kit-cost."""

    def __init__(self, kit):
        try:
            with open(os.path.join(kit, ".install/shared/morning/config"), encoding="utf-8", errors="ignore") as f:
                self.text = f.read()
        except OSError:
            self.text = ""

    def get(self, key, default=""):
        if os.environ.get(key):
            return os.environ[key]
        m = re.search(rf'^{key}="?([^"\n#]*)"?', self.text, re.M)
        return m.group(1).strip() if m and m.group(1).strip() else default

    def number(self, key, default):
        try:
            return float(self.get(key, ""))
        except ValueError:
            return default


def load_tool(name):
    """Load a shared/bin tool (no .py suffix) as a module. Each reads KIT_DIR when it's loaded."""
    path = os.path.join(BIN, name)
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- run outcomes

def sync_events(logs, since):
    """[(time, ok)] for the reminders sync: failure lines from sync.log (one per minute, however
    many sides failed), its change lines as successes, and sync.ok (the last clean run)."""
    fails, oks = set(), set()
    try:
        with open(os.path.join(logs, "sync.log"), encoding="utf-8", errors="ignore") as f:
            for raw in f:
                m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d) (.*)", raw)
                if not m:
                    continue
                t = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")
                if t >= since:
                    (fails if m.group(2).startswith("sync failed") else oks).add(t)
    except OSError:
        pass
    ok_file = os.path.join(logs, "sync.ok")
    if os.path.exists(ok_file):
        t = None
        try:
            with open(ok_file, encoding="utf-8") as f:
                t = dt.datetime.fromisoformat(f.read().strip()[:19])
        except (OSError, ValueError):
            t = dt.datetime.fromtimestamp(os.path.getmtime(ok_file))
        if t >= since:
            oks.add(t)
    oks -= fails
    return sorted([(t, False) for t in fails] + [(t, True) for t in oks])


def run_events(rel, logs, now):
    """{run type: [(time, ok)]} over the last HORIZON_DAYS, oldest first, from kit-reliability."""
    since = now - dt.timedelta(days=HORIZON_DAYS)
    runs, _ = rel.scheduled_runs(since)
    runs += rel.backup_runs(since)
    out = {}
    for r in runs:
        t = r.get("end") or r.get("start")
        if not t or t < since or t > now:
            continue
        out.setdefault(r["mode"], []).append((t, r.get("outcome") in ("success", "degraded")))
    sync = sync_events(logs, since)
    if sync:
        out["sync"] = [e for e in sync if e[0] <= now]
    return {m: sorted(v) for m, v in out.items() if v}


def streak(events):
    """(failures in a row at the end, time the streak began)."""
    n, since = 0, None
    for t, ok in reversed(events):
        if ok:
            break
        n, since = n + 1, t
    return n, since


def missed_weekdays(last, now, skip):
    n, d = 0, last.date() + dt.timedelta(days=1)
    while d <= now.date():
        if d.weekday() < 5 and str(d.isoweekday()) not in skip:
            n += not (d == now.date() and now.time() < MORNING_DUE)
        d += dt.timedelta(days=1)
    return n


def window_of(cfg, mode):
    raw = cfg.get(f"RUN_WINDOW_{mode.upper()}", WINDOWS.get(mode, "")).lower()
    if raw in ("", "0", "off"):
        return None
    try:
        w = float(raw)
    except ValueError:
        return None
    return w if w > 0 else None


def overdue(mode, last, now, w, skip):
    """True when the last success is outside the run type's window."""
    unit = UNIT.get(mode, "day")
    if unit == "weekday":
        return missed_weekdays(last, now, skip) >= w
    if unit == "hour":
        return now - last > dt.timedelta(hours=w)
    return now - last > dt.timedelta(days=w)


def window_text(mode, w):
    unit = UNIT.get(mode, "day")
    return plural(int(w) if w == int(w) else w, unit)


def run_problems(events, cfg, now):
    """{run type: {"since", "streak", "stale", "reason", "fail_since"}} for run types in trouble."""
    n_streak = max(int(cfg.number("RUN_FAIL_STREAK", 2)), 1)
    skip = cfg.get("SKIP_DAYS", "").split()
    out = {}
    for mode, ev in events.items():
        n, began = streak(ev)
        oks = [t for t, ok in ev if ok]
        last = max(oks) if oks else None
        w = window_of(cfg, mode)
        stale = w is not None and (last is None or overdue(mode, last, now, w, skip))
        failing = n >= n_streak
        if not (failing or stale):
            continue
        parts = []
        if failing:
            parts.append(f"failed {n} times running since {began:%a %d-%b %H:%M}")
        if stale:
            parts.append(f"no success since {last:%a %d-%b %H:%M}" if last else
                         f"no success in the last {HORIZON_DAYS} days")
            parts[-1] += f" (window {window_text(mode, w)})"
        since = began if failing else (last or ev[0][0])
        out[mode] = {"since": since, "streak": n, "stale": stale, "failing": failing, "reason": "; ".join(parts)}
    return out


def run_title(mode, p):
    if p["failing"]:
        return f"Fix Kit's {mode} run, failing since {fmt(p['since'])} (kit-reliability)"
    return f"Check Kit's {mode} run, no success since {fmt(p['since'])} (kit-reliability)"


# ---------------------------------------------------------------- cost

def daily_totals(kc):
    out = {}
    for rec in kc.entries():
        d = str(rec.get("date", ""))[:10]
        try:
            dt.date.fromisoformat(d)
        except ValueError:
            continue
        out[d] = out.get(d, 0.0) + kc.cost(rec)
    return out


def spike(kc, cfg, today):
    """(day, cost, median) when the latest day's cost is a spike, else None."""
    factor = cfg.number("COST_SPIKE_FACTOR", 3.0)
    if factor <= 0:
        return None
    totals = daily_totals(kc)
    for day in (today, today - dt.timedelta(days=1)):
        if day.isoformat() in totals:
            break
    else:
        return None
    base = [totals[d.isoformat()] for d in (day - dt.timedelta(days=i) for i in range(1, 15))
            if totals.get(d.isoformat(), 0) > 0]
    if len(base) < 3:
        return None
    med = statistics.median(base)
    c = totals[day.isoformat()]
    return (day, c, med) if med > 0 and c > factor * med else None


def cost_problems(kc, cfg, today):
    """(month, {level: reason}) from kit-cost."""
    st = kc.status()
    month = st["month"]
    label = dt.date.fromisoformat(month + "-01").strftime("%b-%Y")
    out = {}
    budget = st.get("budget_usd")
    if budget:
        frac = cfg.number("COST_ALERT_PROJECTION", 0.0)
        if frac <= 0:
            frac = st["warn_pct"] / 100
        threshold = frac * budget
        if st["projection_usd"] >= threshold:
            out["warn"] = (f"{label} spend projected at {money(st['projection_usd'])}, over {money(threshold)} "
                           f"({frac * 100:g}% of the {money(budget)} budget); {money(st['spend_usd'])} so far")
        if st["pct_used"] is not None and st["pct_used"] >= st["stop_pct"]:
            ess = " ".join(st.get("essential") or []) or "none"
            out["stop"] = (f"{label} spend {money(st['spend_usd'])} is {st['pct_used']:g}% of the {money(budget)} "
                           f"budget (stop at {st['stop_pct']:g}%): only the essential runs ({ess}) go ahead, "
                           "and the morning brief may be degraded")
    else:
        s = spike(kc, cfg, today)
        if s:
            day, c, med = s
            out["spike"] = (f"{day:%a %d-%b} cost {money(c)}, over {cfg.number('COST_SPIKE_FACTOR', 3.0):g}x "
                            f"the 14-day median of {money(med)} (no budget set)")
    return month, label, out


COST_TITLES = {"warn": "Review Kit's spend: {label} projected over the warning level (kit-cost)",
               "stop": "Review Kit's spend: {label} over the stop level, runs are being skipped (kit-cost)",
               "spike": "Review Kit's spend: cost spike in {label} (kit-cost)"}
COST_CLEARS = {"warn": "the projection falls back under or the month ends",
               "stop": "the month ends",
               "spike": "the daily cost is back under or the month ends"}


# ---------------------------------------------------------------- tracking

def load_state(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            st = json.load(f)
        if isinstance(st, dict) and isinstance(st.get("alerts", {}), dict):
            st.setdefault("alerts", {})
            return st
        warn(f"{path} isn't in the expected shape; starting afresh")
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as ex:
        warn(f"couldn't read {path} ({short(ex)}); starting afresh")
    return {"alerts": {}}


def queue_open(ch, kit, todo, a, detail, today):
    if a.get("queued"):
        return
    try:
        a["queued"] = ch.queue_add(kit, todo, a["title"], a.get("reason", ""), today, detail=detail, who="run_alerts")
    except Exception as ex:  # noqa: BLE001  (the alert stands; the queue is tried again next run)
        warn(f"couldn't add the queue item: {short(ex)}")


def queue_close(ch, kit, a, note, today):
    try:
        ch.queue_note(kit, a.get("title", ""), note, today)
    except Exception as ex:  # noqa: BLE001
        warn(f"couldn't note the queue item: {short(ex)}")


def track_runs(state, problems, watched, ch, kit, todo, now):
    alerts, today = state["alerts"], now.date()
    for mode, p in problems.items():
        key = f"run:{mode}"
        a = alerts.get(key)
        if not a:
            a = {"kind": "run", "mode": mode, "since": p["since"].date().isoformat(), "title": run_title(mode, p),
                 "opened": now.isoformat(timespec="minutes"), "queued": False}
            alerts[key] = a
        a.update({"streak": p["streak"], "stale": p["stale"], "reason": p["reason"],
                  "last": now.isoformat(timespec="minutes")})
        queue_open(ch, kit, todo, a, f"{fmt(today)}: {mode} run {short(p['reason'])}. Kit clears its alert "
                                     f"after the next successful {mode} run (see: kit-reliability).", today)
    for key in [k for k, a in alerts.items() if a.get("kind") == "run" and a.get("mode") not in problems]:
        a = alerts.pop(key)
        if a.get("mode") in watched:
            note = f"Recovered {fmt(today)}: the {a.get('mode')} run succeeded again; check this off when you're satisfied."
        else:
            note = f"Cleared {fmt(today)}: the {a.get('mode')} run hasn't run in {HORIZON_DAYS} days, so it's no longer watched."
        queue_close(ch, kit, a, note, today)


def track_cost(state, month, label, problems, ch, kit, todo, now):
    alerts, today = state["alerts"], now.date()
    queued = state.get("cost_queued") if isinstance(state.get("cost_queued"), dict) else {}
    if queued.get("month") != month:
        queued = {"month": month, "levels": []}
    for level, reason in problems.items():
        key = f"cost:{level}"
        a = alerts.get(key)
        if a and a.get("month") != month:
            alerts.pop(key)
            a = None
        if not a:
            a = {"kind": "cost", "level": level, "month": month, "since": today.isoformat(),
                 "title": COST_TITLES[level].format(label=label), "opened": now.isoformat(timespec="minutes"),
                 "queued": level in queued["levels"]}
            alerts[key] = a
        a.update({"reason": reason, "last": now.isoformat(timespec="minutes")})
        queue_open(ch, kit, todo, a, f"{fmt(today)}: {short(reason, 160)}. Kit clears its alert when "
                                     f"{COST_CLEARS[level]} (see: kit-cost).", today)
        if a.get("queued") and level not in queued["levels"]:
            queued["levels"].append(level)
    for key in [k for k, a in alerts.items() if a.get("kind") == "cost"]:
        a = alerts[key]
        if a.get("month") == month and a.get("level") in problems:
            continue
        alerts.pop(key)
        if a.get("month") != month:
            note = f"Cleared {fmt(today)}: a new month started, so this alert is closed."
        else:
            note = {"warn": f"Cleared {fmt(today)}: the month's projection is back under the warning level.",
                    "spike": f"Cleared {fmt(today)}: the daily cost is back under the spike level."}.get(
                a.get("level"), f"Cleared {fmt(today)}: the spend is no longer over this level.")
        queue_close(ch, kit, a, note + " Check this off when you're satisfied.", today)
    state["cost_queued"] = queued


# ---------------------------------------------------------------- monitors

# The monitor kinds, in run order. To add one: put its name here and write shared/morning/monitor_<kind>.py
# with problems(kit, cfg, now, deadline) -> {key: problem} (see track_monitor for the problem's fields) and,
# optionally, line(alert) -> the brief line; MONITOR_<KIND>="off" in the config turns it off. The dashboard
# shows a generic banner for a kind it doesn't know.
MONITORS = ("drift", "library", "waiting", "guard", "exceptions")
KEEP = ("reason", "agents", "drift", "check", "inferred", "type", "item", "days", "date", "draft", "file",
        "problems")


def load_monitor(kind):
    """shared/morning/monitor_<kind>.py, imported fresh."""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    return importlib.import_module(f"monitor_{kind}")


def sha(text):
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_draft(kit, a, text):
    """Write a follow-up draft once (never over one that's there); remember its hash."""
    path = os.path.join(kit, a["draft"])
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    a["draft_sha"] = sha(text)


def remove_draft(kit, a):
    """Remove a follow-up draft Kit wrote, unless it has been edited since."""
    if not a.get("draft") or not a.get("draft_sha"):
        return
    path = os.path.join(kit, a["draft"])
    try:
        with open(path, encoding="utf-8") as f:
            if sha(f.read()) == a["draft_sha"]:
                os.remove(path)
    except OSError:
        pass


def track_monitor(state, kind, problems, ch, kit, todo, now):
    """Open, refresh, and clear one monitor's alerts. A problem with a "title" gets one owner [work] item
    per outage ({since} in it becomes the opening date); "recovered" is the note added when it clears."""
    alerts, today = state["alerts"], now.date()
    for key, p in problems.items():
        a = alerts.get(key)
        if not a:
            a = {"kind": kind, "since": today.isoformat(), "opened": now.isoformat(timespec="minutes"), "queued": False}
            if p.get("title"):
                a["title"] = p["title"].replace("{since}", fmt(today))
            alerts[key] = a
        a.update({k: p[k] for k in KEEP if k in p})
        a["last"] = now.isoformat(timespec="minutes")
        if p.get("recovered"):
            a["recovered"] = p["recovered"]
        if p.get("draft_text") and a.get("draft"):
            try:
                write_draft(kit, a, p["draft_text"])
            except OSError as ex:
                warn(f"couldn't write {a['draft']}: {short(ex)}")
        if a.get("title"):
            queue_open(ch, kit, todo, a, (p.get("detail") or "{today}: " + a.get("reason", "")).replace(
                "{today}", fmt(today)), today)
    for key in [k for k, a in alerts.items() if isinstance(a, dict) and a.get("kind") == kind and k not in problems]:
        a = alerts.pop(key)
        if a.get("draft"):
            remove_draft(kit, a)
        if a.get("title") and a.get("queued"):
            note = (a.get("recovered") or "Cleared {today}: the condition has passed; check this off when you're "
                    "satisfied.").replace("{today}", fmt(today))
            queue_close(ch, kit, a, note, today)


def preview_monitor(state, kind, problems, now):
    """Dry run: the alerts these problems would open, in state["preview"], without recording anything."""
    prev = state.setdefault("preview", {})
    for key, p in problems.items():
        a = {"kind": kind, "since": now.date().isoformat(), "preview": True}
        a.update({k: p[k] for k in KEEP if k in p})
        prev[key] = a


def run_monitors(state, cfg, kit, only, track, ch, todo, now):
    cfg.dry_run = not track          # monitors that would write a probe file check permissions instead
    for kind in MONITORS:
        if only not in (None, kind):
            continue
        try:
            if cfg.get(f"MONITOR_{kind.upper()}", "on").lower() == "off":
                problems = {}
            else:
                limit = cfg.number("MONITOR_TIMEOUT", 20.0)
                deadline = time.monotonic() + (limit if limit > 0 else 20.0)
                problems = load_monitor(kind).problems(kit, cfg, now, deadline)
            if problems is None:          # not checked (out of time): leave open alerts as they are
                continue
            if track:
                track_monitor(state, kind, problems, ch, kit, todo, now)
            else:
                preview_monitor(state, kind, problems, now)
        except Exception as ex:  # noqa: BLE001  (a monitor never fails the run)
            warn(f"{kind} alerts skipped: {short(ex)}")


def monitor_line(a):
    k = a.get("kind")
    listed = "" if a.get("preview") else "on your list; "
    if k == "drift":
        if a.get("drift") == "installed":
            return f"Drift alert: {a.get('reason')} ({listed}run doctor.py --fix-agents)."
        return f"Drift alert: {a.get('reason')} ({listed}compare with kit-alerts drift --diff <agent>)."
    if k == "library":
        if a.get("check") == "sync":
            return f"Library alert (inferred): {a.get('reason')}."
        return f"Library alert: {a.get('reason')}" + (" (on your list)." if listed else ".")
    if k == "exceptions":
        if a.get("type") == "expired":
            return f"Exception alert: {a.get('reason')} ({listed}renew or close it; kit-exceptions due)."
        return f"Exception alert: {a.get('reason')} (kit-exceptions due)."
    if k == "waiting":
        days = a.get("days", "?")
        if a.get("type") == "decision":
            where = f" ({a['file']})" if a.get("file") else ""
            return f"Decision waiting {days} days: {a.get('item')}{where}."
        draft = a.get("draft")
        note = (f"; follow-up draft would go to {draft}" if a.get("preview") else
                f"; follow-up draft in {draft}") if draft else ""
        return f"Waiting {days} days: {a.get('item')}{note} (never sent)."
    try:
        mod = load_monitor(k) if k in MONITORS else None
        if mod is not None and hasattr(mod, "line"):
            return mod.line(a)
    except Exception as ex:  # noqa: BLE001
        warn(f"{k} line skipped: {short(ex)}")
    return f"{str(k).capitalize()} alert: {a.get('reason')}." if a.get("reason") else None


def kind_of(only):
    return {"runs": "run"}.get(only, only)


def lines(state, only=None, key="alerts"):
    """One brief line per open alert (or per previewed one, with key="preview")."""
    out = []
    for _k, a in sorted(state.get(key, {}).items()):
        if not isinstance(a, dict) or (only and a.get("kind") != kind_of(only)):
            continue
        if a.get("kind") == "run":
            out.append(f"Run alert: {a.get('mode')} {a.get('reason')} (on your list; see kit-reliability).")
        elif a.get("kind") == "cost":
            out.append(f"Cost alert ({a.get('level')}): {a.get('reason')} (on your list; see kit-cost).")
        else:
            ln = monitor_line(a)
            if ln:
                out.append(ln)
    return out


def preview_lines(state, only=None):
    """Dry-run lines: what's wrong now, recording nothing."""
    out = []
    if only in (None, "runs"):
        out += [f"Run alert: {m} {r}." for m, r in sorted(state.get("preview_runs", {}).items())]
    if only in (None, "cost"):
        out += [f"Cost alert ({lv}): {r}." for lv, r in sorted(state.get("preview_cost", {}).items())]
    return out + lines(state, only, key="preview")


def save_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, sort_keys=True, default=str)
    os.replace(tmp, path)


def compute(kit, now, only=None, track=True, todo=DEFAULT_TODO, dashboard=True):
    """Recompute and (with track) record the alerts. Returns the state dict. Never raises."""
    os.environ["KIT_DIR"] = kit
    os.environ["KIT_COST_TODAY"] = now.date().isoformat()   # kit-cost's "today", for the projection
    if SHARED not in sys.path:
        sys.path.insert(0, SHARED)
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    cfg = Config(kit)
    path = os.path.join(kit, "briefs", "alerts.json")
    state = load_state(path)
    before = json.dumps(state, sort_keys=True, default=str)
    try:
        import connector_health as ch  # queue_add and queue_note, shared with the connector outages
    except Exception as ex:  # noqa: BLE001
        warn(f"connector_health.py didn't load ({short(ex)}); no queue items this time")
        ch = None
    if ch is None:
        class _NoQueue:
            @staticmethod
            def queue_add(*_a, **_k):
                return False

            @staticmethod
            def queue_note(*_a, **_k):
                return False
        ch = _NoQueue
    if only in (None, "runs"):
        try:
            rel = load_tool("kit-reliability")
            events = run_events(rel, os.path.join(kit, ".install/logs"), now)
            problems = run_problems(events, cfg, now)
            if track:
                track_runs(state, problems, set(events), ch, kit, todo, now)
            else:
                state["preview_runs"] = {m: p["reason"] for m, p in problems.items()}
        except Exception as ex:  # noqa: BLE001  (a bad log never fails the run)
            warn(f"run alerts skipped: {short(ex)}")
    if only in (None, "cost"):
        try:
            kc = load_tool("kit-cost")
            month, label, problems = cost_problems(kc, cfg, now.date())
            if track:
                track_cost(state, month, label, problems, ch, kit, todo, now)
            else:
                state["preview_cost"] = problems
        except Exception as ex:  # noqa: BLE001  (a bad ledger never fails the run)
            warn(f"cost alerts skipped: {short(ex)}")
    run_monitors(state, cfg, kit, only, track, ch, todo, now)
    if track and json.dumps(state, sort_keys=True, default=str) != before:
        try:
            if os.path.isdir(os.path.dirname(path)):
                save_state(path, state)
            if dashboard:
                dash = os.path.join(SHARED, "dashboard.py")
                if os.path.exists(dash):
                    subprocess.run([sys.executable, dash], capture_output=True, stdin=subprocess.DEVNULL,
                                   env=dict(os.environ, KIT_DIR=kit), timeout=120)
        except Exception as ex:  # noqa: BLE001
            warn(f"couldn't save the alerts: {short(ex)}")
    return state


def main(argv):
    ap = argparse.ArgumentParser(prog="run_alerts.py", description="Alerts for failed scheduled runs and cost.")
    ap.add_argument("--kit", default=os.environ.get("KIT_DIR", os.path.expanduser("~/Claude/Agents/kit")))
    ap.add_argument("--only", choices=["runs", "cost", *MONITORS])
    ap.add_argument("--out", help="write one line per open alert here (for the brief)")
    ap.add_argument("--no-track", action="store_true", help="show what's wrong without recording anything")
    ap.add_argument("--no-dashboard", action="store_true", help="don't rebuild the dashboard after a change")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--todo", default=DEFAULT_TODO)
    ap.add_argument("--now", help=argparse.SUPPRESS)   # tests: pretend it's this YYYY-MM-DDTHH:MM
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return 0
    try:
        now = dt.datetime.fromisoformat(a.now) if a.now else dt.datetime.now()
        state = compute(a.kit, now, a.only, not a.no_track, a.todo, not a.no_dashboard)
        text = preview_lines(state, a.only) if a.no_track else lines(state)
    except Exception as ex:  # noqa: BLE001  (never fail the scheduled run)
        warn(f"failed: {short(ex)}")
        state, text = {"alerts": {}}, []
    if a.out:
        try:
            with open(a.out, "w", encoding="utf-8") as f:
                f.write("".join(t + "\n" for t in text))
        except OSError as ex:
            warn(f"couldn't write {a.out}: {ex}")
    if a.json:
        print(json.dumps({"alerts": state.get("alerts", {}), "lines": text}, indent=1, sort_keys=True, default=str))
    else:
        print("\n".join(text))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

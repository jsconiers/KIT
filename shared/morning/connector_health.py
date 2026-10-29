#!/usr/bin/env python3
"""connector_health.py: one line on Kit's connectors for the top of the morning brief.

  python3 connector_health.py [--out briefs/connectors.txt] [--timeout 120] [--kit-connect <path>]
                              [--streak 2] [--history <file>] [--no-track] [--date YYYY-MM-DD]

Runs `kit-connect test --json` (no --read, so no model run and no cost: it checks the guard
settings, credential names, and Claude Code's own `claude mcp list`), and writes one line such as

  Connectors: jira PASS; wiki FAIL (health: Failed to connect)

It never fails the run that calls it: a timeout, a missing kit-connect, or output it can't read
becomes "Connectors: not checked (...)", and it always exits 0. With no servers configured it
writes nothing, so the brief gets no line. The run.sh and run.ps1 morning runs call it before the
model and pass the line in; set CONNECTOR_CHECK="off" in the config to skip it.

Outage tracking (proactive monitoring). With --out, each checked server's result is also kept in
connectors-history.jsonl next to it (one line per server per date: date, server, pass, reason; a
rerun on the same date replaces that date's line; a "not checked" morning records nothing). When a
server has failed --streak mornings running (CONNECTOR_FAIL_STREAK, default 2), it:
  - adds one [work] item for the owner to QUEUE.md through `todo work` ("Fix connector <name>,
    failing since DD-Mmm-YYYY (kit-connect test)", with the last reason as a detail line), once per
    outage: connectors-alerts.json remembers the outage, and an open item with the same title is
    never added twice;
  - raises the dashboard's red "Connector outage" banner (dashboard.py reads connectors-alerts.json).
When the server passes again, the queue item gets a "Recovered" line (the owner checks it off) and
the alert is cleared. A server that's no longer checked is cleared the same way. The brief line
says "N mornings running" for a server in a streak. None of this can fail the run: any error is
reported on stderr and the line is still written. --no-track turns it off.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import signal
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.dirname(HERE)
DEFAULT_KC = os.path.join(SHARED, "bin", "kit-connect")
DEFAULT_TODO = os.path.join(SHARED, "bin", "todo")
KEEP_DAYS = 90


def short(text, n=80):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 3].rstrip() + "..."


def run(kc, timeout):
    """(returncode, stdout, stderr), or None on a timeout. The whole process tree is stopped on a
    timeout, since kit-connect starts claude, which could otherwise hold the pipes open."""
    kw = {"start_new_session": True} if os.name != "nt" else \
        {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    p = subprocess.Popen([sys.executable, kc, "test", "--json"], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, **kw)
    try:
        out, err = p.communicate(timeout=timeout)
        return p.returncode, out, err
    except subprocess.TimeoutExpired:
        try:
            if os.name != "nt":
                os.killpg(p.pid, signal.SIGKILL)
            else:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        except OSError:
            p.kill()
        try:
            p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return None


def check(kc, timeout):
    """(results, line): results is a list of (server, passed, reason), or None when nothing was
    checked (so nothing is recorded); line is the brief line without outage notes."""
    if not os.path.exists(kc):
        return None, "Connectors: not checked (kit-connect isn't installed)."
    try:
        r = run(kc, timeout)
    except OSError as ex:
        return None, f"Connectors: not checked ({short(ex)})."
    if r is None:
        return None, f"Connectors: not checked (kit-connect didn't finish in {timeout} s)."
    rc, out, err = r
    try:
        servers = json.loads(out).get("servers") or []
    except (ValueError, AttributeError):
        servers = None
    if servers is None:
        msg = (err or out or "").strip().splitlines()
        if rc == 2 and msg and "no servers to check" in msg[0]:
            return [], ""
        return None, f"Connectors: not checked ({short(msg[0] if msg else f'kit-connect exited {rc}')})."
    if not servers:
        return [], ""
    results = []
    for s in servers:
        name = str(s.get("server") or "?")
        if s.get("pass"):
            results.append((name, True, ""))
        else:
            bad = next((c for c in s.get("checks") or [] if not c.get("pass")), {})
            why = f"{bad.get('check', 'check')}: {short(bad.get('detail'), 60)}" if bad else "failed"
            results.append((name, False, why))
    return results, render(results)


def render(results, streaks=None):
    streaks = streaks or {}
    parts = []
    for name, ok, why in results:
        if ok:
            parts.append(f"{name} PASS")
        else:
            n = streaks.get(name, 1)
            parts.append(f"{name} FAIL ({why}" + (f"; {n} mornings running" if n > 1 else "") + ")")
    return ("Connectors: " + "; ".join(parts) + ".") if parts else ""


def line(kc, timeout):
    return check(kc, timeout)[1]


# ---------------------------------------------------------------- outage tracking

def fmt(d):
    return d.strftime("%d-%b-%Y")


def load_history(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                try:
                    r = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(r, dict) and r.get("date") and r.get("server"):
                    rows.append(r)
    except OSError:
        pass
    return rows


def save_json_lines(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    os.replace(tmp, path)


def record(history, results, today):
    """History with today's results in place of any earlier ones for today, trimmed to KEEP_DAYS."""
    day = today.isoformat()
    cutoff = (today - dt.timedelta(days=KEEP_DAYS)).isoformat()
    names = {n for n, _, _ in results}
    rows = [r for r in history if str(r["date"]) >= cutoff and not (r["date"] == day and r["server"] in names)]
    rows += [{"date": day, "server": n, "pass": bool(ok), "reason": why} for n, ok, why in results]
    rows.sort(key=lambda r: (str(r["date"]), str(r["server"])))
    return rows


def streak(history, server):
    """(mornings failing in a row, ending with the latest record; date the streak began)."""
    rows = sorted((r for r in history if r["server"] == server), key=lambda r: str(r["date"]))
    n, since = 0, None
    for r in reversed(rows):
        if r.get("pass"):
            break
        n, since = n + 1, str(r["date"])
    return n, since


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-") or "unnamed"


def queue_title(server, since):
    try:
        d = fmt(dt.date.fromisoformat(since))
    except (TypeError, ValueError):
        d = since
    return f"Fix connector {safe_name(server)}, failing since {d} (kit-connect test)"


def queue_add(kit, todo, title, reason, today, detail=None, who="connector_health"):
    """Add the owner's [work] item through `todo work`, unless an open one with that title exists,
    then a detail line with the last reason (or `detail`, as written). True if the item is (now) on
    the queue. run_alerts.py uses it too, with its own detail line and name for messages."""
    import kit_queue as kq  # shared/kit_queue.py, imported here so a missing one can't stop the check
    q = os.path.join(kit, "QUEUE.md")
    if not os.path.exists(q):
        print(f"{who}: no QUEUE.md, so no queue item", file=sys.stderr)
        return False
    lines = kq.load(pathlib.Path(q))
    if any(it["title"] == title and it["parent"] is None for it in kq.open_items(lines)):
        return True
    env = dict(os.environ, KIT_DIR=kit)
    r = subprocess.run([sys.executable, todo, "work", title], capture_output=True, text=True, env=env,
                       stdin=subprocess.DEVNULL, timeout=120)
    if r.returncode != 0:
        print(f"{who}: todo failed: {short(r.stderr or r.stdout)}", file=sys.stderr)
        return False
    lines = kq.load(pathlib.Path(q))
    for it in kq.open_items(lines):
        if it["title"] == title and it["parent"] is None:
            lines.insert(it["end"], f"  {detail}" if detail else
                         f"  Last check {fmt(today)}: {short(reason, 100)}. Kit clears its alert when the check passes again.")
            kq.write(lines, pathlib.Path(q))
            break
    return True


def queue_note(kit, title, note, today):
    """Add a detail line to the open item with this title (if it's still open) and stamp it."""
    import kit_queue as kq
    q = pathlib.Path(os.path.join(kit, "QUEUE.md"))
    if not q.exists():
        return False
    lines = kq.load(q)
    for it in kq.open_items(lines):
        if it["title"] == title and it["parent"] is None:
            lines.insert(it["end"], f"  {note}")
            lines[it["line"]] = kq.stamp(lines[it["line"]], today)
            kq.write(lines, q)
            return True
    return False


def track(results, out_dir, kit, todo, n_streak, today):
    """Record today's results, raise and clear outages. Returns {server: streak} for the line."""
    hist_path = os.path.join(out_dir, "connectors-history.jsonl")
    alerts_path = os.path.join(out_dir, "connectors-alerts.json")
    history = record(load_history(hist_path), results, today)
    save_json_lines(hist_path, history)
    try:
        with open(alerts_path, encoding="utf-8-sig") as f:
            alerts = json.load(f)
        if not isinstance(alerts, dict):
            alerts = {}
    except (OSError, ValueError):
        alerts = {}
    before = json.dumps(alerts, sort_keys=True)
    streaks, checked = {}, set()
    for name, ok, why in results:
        checked.add(name)
        n, since = streak(history, name)
        streaks[name] = n
        a = alerts.get(name)
        if ok:
            if a:
                queue_note(kit, a.get("title", ""), f"Recovered {fmt(today)}: the connector check passed again; "
                           "check this off when you're satisfied.", today)
                del alerts[name]
            continue
        if n < n_streak:
            continue
        if not a:
            a = {"since": since, "title": queue_title(name, since), "queued": False}
            alerts[name] = a
        a.update({"streak": n, "reason": why, "last": today.isoformat()})
        if not a.get("queued"):
            try:
                a["queued"] = queue_add(kit, todo, a["title"], why, today)
            except Exception as ex:  # noqa: BLE001  (the alert stands; the queue is tried again tomorrow)
                print(f"connector_health: couldn't add the queue item: {short(ex)}", file=sys.stderr)
    for name in [k for k in alerts if k not in checked]:
        queue_note(kit, alerts[name].get("title", ""), f"Cleared {fmt(today)}: the connector is no longer checked.",
                   today)
        del alerts[name]
    if json.dumps(alerts, sort_keys=True) != before:
        tmp = alerts_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(alerts, f, indent=1, sort_keys=True)
        os.replace(tmp, alerts_path)
        dash = os.path.join(SHARED, "dashboard.py")
        if os.path.exists(dash):
            subprocess.run([sys.executable, dash], capture_output=True, stdin=subprocess.DEVNULL,
                           env=dict(os.environ, KIT_DIR=kit), timeout=120)
    return streaks


def main(argv):
    ap = argparse.ArgumentParser(prog="connector_health.py", description="One brief line on Kit's connectors.")
    ap.add_argument("--out")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--kit-connect", default=os.environ.get("KIT_CONNECT", DEFAULT_KC))
    ap.add_argument("--streak", type=int, default=2, help="failed mornings in a row before an outage is raised")
    ap.add_argument("--history", help="folder for connectors-history.jsonl and connectors-alerts.json "
                                      "(default: the --out file's folder)")
    ap.add_argument("--no-track", action="store_true", help="don't keep history or raise outages")
    ap.add_argument("--kit", default=os.environ.get("KIT_DIR", os.path.expanduser("~/Claude/Agents/kit")))
    ap.add_argument("--todo", default=DEFAULT_TODO)
    ap.add_argument("--date", help=argparse.SUPPRESS)   # tests: pretend today is this YYYY-MM-DD
    a = ap.parse_args(argv)
    results = None
    try:
        results, text = check(a.kit_connect, max(a.timeout, 1))
    except Exception as ex:  # noqa: BLE001  (never fail the scheduled run)
        text = f"Connectors: not checked ({short(ex)})."
    out_dir = a.history or (os.path.dirname(os.path.abspath(a.out)) if a.out else None)
    if results and out_dir and not a.no_track:
        try:
            sys.path.insert(0, SHARED)
            os.environ["KIT_DIR"] = a.kit
            today = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
            streaks = track(results, out_dir, a.kit, a.todo, max(a.streak, 1), today)
            text = render(results, streaks)
        except Exception as ex:  # noqa: BLE001  (tracking is best-effort; the line still goes out)
            print(f"connector_health: outage tracking failed: {short(ex)}", file=sys.stderr)
    if a.out:
        try:
            with open(a.out, "w", encoding="utf-8") as f:
                f.write(text + ("\n" if text else ""))
        except OSError as ex:
            print(f"connector_health: couldn't write {a.out}: {ex}", file=sys.stderr)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""monitor_exceptions.py: policy exceptions near or past expiry, an alert kind for run_alerts.py
(kind "exceptions").

  python3 monitor_exceptions.py [--kit DIR]

Reads the exception register that **Exception register** in memory/context/compliance.md names
(default compliance/exception-register.md in the library root) with kit_compliance.py, the same parser
as kit-exceptions. Only granted and renewal-requested exceptions are watched (and rows marked expired
but never closed):
  expired   the expiry date has passed. One [work] queue item for the owner per exception asks them
            to renew or close it; it clears when the row is renewed (a later expiry) or closed.
  expiring  the expiry is within EXCEPTIONS_WARN_DAYS (default 30). Brief line and dashboard only.
  review    the review is overdue: last reviewed (else granted) plus the review frequency is before
            today. Brief line and dashboard only.
Read-only: it never edits the register, requests a renewal, or contacts anyone. No register, or no
library root, means nothing to report. MONITOR_EXCEPTIONS="off" turns it off.
"""
import argparse
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.dirname(HERE)


def problems(kit, cfg=None, now=None, deadline=None):
    if SHARED not in sys.path:
        sys.path.insert(0, SHARED)
    import kit_compliance as kc  # noqa: E402
    now = now or dt.datetime.now()
    days = cfg.number("EXCEPTIONS_WARN_DAYS", 30) if cfg else 30
    path = kc.exception_register(kit)
    if not path or not path.exists():
        return {}
    _, _, recs = kc.load_exceptions(path)
    out = {}
    for kind, r, n, d in kc.exception_due(recs, now.date(), int(days)):
        what = f"{r['id']} ({r['policy'][:60]}; {r['system'][:40]})"
        if kind == "expired":
            reason = f"{what}: expired {n} day(s) ago ({kc.fmt(d)})"
        elif kind == "expiring":
            reason = f"{what}: expires in {n} day(s) ({kc.fmt(d)})"
        else:
            reason = f"{what}: review overdue by {n} day(s) (due {kc.fmt(d)})"
        p = {"type": kind, "item": r["id"], "days": n, "date": d.isoformat(), "reason": reason,
             "file": str(path)}
        if kind == "expired":
            p["title"] = f"Renew or close policy exception {r['id']}, expired {kc.fmt(d)} (kit-exceptions due)"
            p["recovered"] = "Cleared {today}: the exception was renewed or closed; check this off when you're satisfied."
        out[f"exceptions:{kind}:{r['id']}"] = p
    return out


def main(argv):
    ap = argparse.ArgumentParser(prog="monitor_exceptions.py")
    ap.add_argument("--kit", default=os.environ.get("KIT_DIR", os.path.expanduser("~/Claude/Agents/kit")))
    a = ap.parse_args(argv)
    for key, p in sorted(problems(a.kit).items()):
        print(f"{key}: {p['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

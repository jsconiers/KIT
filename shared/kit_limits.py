#!/usr/bin/env python3
"""kit_limits: notice when Claude's usage limit stops Kit's runs, and stand the scheduled runs down until it resets.

From 26 to 30 Oct 2026 every scheduled run failed with "API Error: 400 You have reached your specified per-user
API usage limits. You will regain access on 2026-11-01 at 00:00 UTC." and Kit tried again at every run. This is
not the dollar budget (kit-cost's COST_BUDGET_MONTHLY, which Kit sets for itself); it's the limit the API or the
plan sets, and nothing Kit does gets past it before the reset.

  python3 kit_limits.py detect --source MODE FILE...   read a failed run's output; on a usage-limit message,
                                                       record it and print "limit RESET" (exit 0); else exit 1
  python3 kit_limits.py check [--mode MODE] [--probe]  exit 0 "ok" (no active limit, or it just cleared),
                                                       2 "limited RESET-or-unknown; MESSAGE" while it holds;
                                                       --probe (preflight): exit 0 "probe" once a day when
                                                       the reset time is unknown, so one small call can test it
  python3 kit_limits.py success --source MODE          a run succeeded: clear an active limit
  python3 kit_limits.py clear [--why TEXT]             clear it by hand
  python3 kit_limits.py status [--json]                what's recorded
  python3 kit_limits.py notice                         the one-line notice for the owner (empty if none)
  python3 kit_limits.py when                           when access returns, as text (empty if no limit)

The state is .install/logs/usage-limit.json: the reason (the matched message, cut to one line), when it was first
and last seen, the reset time (ISO, UTC) or null when the message didn't give one, the run that hit it, and the day
of the last probe. Clearing it deletes the file and the once-per-lapse notice marker
(.install/logs/usage-limit-notified), and appends "usage limit cleared" to .install/logs/usage-limit.log.

A known reset time clears itself when it passes. An unknown one holds until a run succeeds; preflight's small
daily call (check --probe) is what tests it, once a day, so the runs don't each fail in turn.

Nothing here calls a model or the network. KIT_DIR overrides the Kit folder and KIT_LIMITS_NOW (ISO time) the
clock, for tests.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover  (Python before 3.9)
    ZoneInfo = None

UTC = dt.timezone.utc

# Messages that mean "no more calls until the limit resets", most specific first. Rate limits (429, "too many
# requests", overload) are transient and stay with run.sh's retry; they aren't here.
PATTERNS = [
    r"reached your (?:specified )?(?:per-user )?(?:api )?usage limits?",
    r"(?:claude(?: ai)?|api|plan|weekly|monthly|daily|5-hour)?\s*usage limits? (?:has been |was )?(?:reached|exceeded|hit)",
    r"(?:exceeded|hit|reached) (?:your |the )?(?:\w+ )?usage limits?",
    r"you'?ve (?:hit|reached) your (?:\w+ )?limit",
    r"credit balance is (?:too low|insufficient)",
    r"(?:out of|no) (?:extra )?(?:usage|credits)\b",
    r"(?:will )?regain access (?:on|at)",
    r"limit (?:will )?resets? (?:at|on)",
    r"spend(?:ing)? limit (?:reached|exceeded)",
    r"(?:5-hour|weekly|daily|monthly|session|opus|sonnet) limit (?:reached|exceeded|hit)",
    r"limit reached\W+(?:\w+\W+)?resets?\b",
]
MATCH = re.compile("|".join(f"(?:{p})" for p in PATTERNS), re.I)
MONTHS = {m: i for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


def kit_dir(kit=None):
    return pathlib.Path(os.path.expanduser(str(kit or os.environ.get("KIT_DIR") or "~/Claude/Agents/kit")))


def now():
    fake = os.environ.get("KIT_LIMITS_NOW")
    if fake:
        t = dt.datetime.fromisoformat(fake.replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=UTC)
    return dt.datetime.now(UTC)


def paths(kit=None):
    logs = kit_dir(kit) / ".install/logs"
    return {"state": logs / "usage-limit.json", "marker": logs / "usage-limit-notified",
            "log": logs / "usage-limit.log"}


def _tz(name):
    if not name:
        return None
    n = name.strip().strip("()").strip()
    if n.upper() in ("UTC", "GMT", "Z"):
        return UTC
    m = re.fullmatch(r"(?:UTC|GMT)?\s*([+-])(\d{1,2}):?(\d{2})?", n, re.I)
    if m:
        off = dt.timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0))
        return dt.timezone(off if m.group(1) == "+" else -off)
    if ZoneInfo and "/" in n:
        try:
            return ZoneInfo(n)
        except Exception:  # noqa: BLE001  (an unknown zone name: fall back to local time)
            return None
    return None


def _clock(text):
    """'00:00', '3pm', '3:30 pm', '15:00' -> (hour, minute), or None."""
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?", text.strip(), re.I)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    ap = (m.group(3) or "").lower().replace(".", "")
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return (h, mi) if h < 24 and mi < 60 else None


def parse_reset(text, ref=None):
    """The reset time a limit message gives, as an aware UTC datetime, or None.

    Understands: "regain access on 2026-11-01 at 00:00 UTC", ISO stamps ("resets at 2026-11-01T00:00:00Z"),
    "resets on Nov 1 at 3pm (America/New_York)", a bare time ("limit will reset at 5pm", the next one after
    ref), and Claude Code's "usage limit reached|1730419200" epoch form."""
    ref = ref or now()
    m = re.search(r"limit reached\|(\d{9,11})", text, re.I)
    if m:
        return dt.datetime.fromtimestamp(int(m.group(1)), UTC)
    tail = r"(?:\s*\(?\s*(?P<tz>UTC|GMT|Z|[A-Za-z]+/[A-Za-z_]+(?:/[A-Za-z_]+)?|[+-]\d{1,2}:?\d{2})\s*\)?)?"
    m = re.search(r"(?P<d>\d{4}-\d{2}-\d{2})(?:[T ]|\s+at\s+)(?P<t>\d{1,2}:\d{2}(?::\d{2})?(?:\s*[ap]m)?)"
                  r"(?:\.\d+)?" + tail, text, re.I)
    if m:
        t = m.group("t")
        hm = _clock(t[:5] if re.match(r"\d{1,2}:\d{2}:\d{2}", t) else t) or (0, 0)
        tz = _tz(m.group("tz")) or dt.datetime.now().astimezone().tzinfo
        d = dt.date.fromisoformat(m.group("d"))
        return dt.datetime(d.year, d.month, d.day, hm[0], hm[1], tzinfo=tz).astimezone(UTC)
    m = re.search(r"(?:regain access|resets?)\s+(?:on\s+)?(?P<d>\d{4}-\d{2}-\d{2})\b" + tail, text, re.I)
    if m:
        tz = _tz(m.group("tz")) or UTC
        d = dt.date.fromisoformat(m.group("d"))
        return dt.datetime(d.year, d.month, d.day, tzinfo=tz).astimezone(UTC)
    m = re.search(r"(?:regain access|resets?)\s+(?:on\s+)?(?P<mon>[A-Za-z]{3})[a-z]*\.?\s+(?P<day>\d{1,2})"
                  r"(?:,?\s*(?P<y>\d{4}))?(?:,?\s+at\s+(?P<t>\d{1,2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?))?" + tail,
                  text, re.I)
    if m and m.group("mon").lower() in MONTHS:
        tz = _tz(m.group("tz")) or dt.datetime.now().astimezone().tzinfo
        hm = _clock(m.group("t")) if m.group("t") else (0, 0)
        year = int(m.group("y") or ref.year)
        cand = dt.datetime(year, MONTHS[m.group("mon").lower()], int(m.group("day")), *(hm or (0, 0)), tzinfo=tz)
        if not m.group("y") and cand.astimezone(UTC) < ref - dt.timedelta(days=1):
            cand = cand.replace(year=year + 1)
        return cand.astimezone(UTC)
    m = re.search(r"(?:regain access|resets?)\s+(?:at\s+)?(?P<t>\d{1,2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?)" + tail,
                  text, re.I)
    if m:
        hm = _clock(m.group("t"))
        if hm and (m.group("tz") or re.search(r"[ap]\.?m|:", m.group("t"), re.I)):
            tz = _tz(m.group("tz")) or dt.datetime.now().astimezone().tzinfo
            local = ref.astimezone(tz)
            cand = local.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
            if cand <= local:
                cand += dt.timedelta(days=1)
            return cand.astimezone(UTC)
    return None


def detect(text):
    """(matched line, reset or None) when the text says a usage limit was hit; else None."""
    if not text:
        return None
    m = MATCH.search(text)
    if not m:
        return None
    start = text.rfind("\n", 0, m.start()) + 1
    end = text.find("\n", m.end())
    line = text[start:end if end != -1 else len(text)].strip()
    line = re.sub(r"\s+", " ", line)
    line = re.sub(r"(?i)\b(sk-[\w-]{6})[\w-]+", r"\1...", line)[:240]
    return line, parse_reset(text)


def load(kit=None):
    try:
        st = json.loads(paths(kit)["state"].read_text(encoding="utf-8"))
        return st if isinstance(st, dict) else None
    except (OSError, ValueError):
        return None


def _write(st, kit=None):
    p = paths(kit)["state"]
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def _log(msg, kit=None):
    p = paths(kit)["log"]
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{now().isoformat(timespec='seconds')} {msg}\n")
    except OSError:
        pass


def record(reason, reset, source, kit=None):
    st = load(kit) or {}
    t = now().isoformat(timespec="seconds")
    new = not st
    st.update({"reason": reason, "first_seen": st.get("first_seen") or t, "last_seen": t,
               "reset": reset.astimezone(UTC).isoformat(timespec="seconds") if reset else st.get("reset"),
               "source": source if new else st.get("source") or source, "last_source": source})
    st.setdefault("last_probe", None)
    _write(st, kit)
    if new:
        _log(f"usage limit recorded ({source}): reset {st['reset'] or 'unknown'}: {reason}", kit)
    return st


def clear(why, kit=None):
    p = paths(kit)
    had = p["state"].exists()
    for k in ("state", "marker"):
        try:
            p[k].unlink()
        except OSError:
            pass
    if had:
        _log(f"usage limit cleared ({why})", kit)
    return had


def reset_of(st):
    try:
        return dt.datetime.fromisoformat(st["reset"]) if st and st.get("reset") else None
    except ValueError:
        return None


def when_text(st):
    r = reset_of(st)
    if not r:
        return "an unknown time (Kit tests once a day)"
    local = r.astimezone(dt.datetime.now().astimezone().tzinfo) if not os.environ.get("KIT_LIMITS_NOW") else r
    return local.strftime("%d-%b-%Y %H:%M ") + (local.tzname() or "UTC")


def active(kit=None):
    """The recorded limit if it still holds; clears one whose reset has passed."""
    st = load(kit)
    if not st:
        return None
    r = reset_of(st)
    if r and now() >= r:
        clear(f"the reset time {st['reset']} passed", kit)
        return None
    return st


def notice(st):
    if not st:
        return ""
    return (f"Kit · Claude usage limit reached, so Kit's scheduled runs are standing down until access returns "
            f"{when_text(st)}. The morning brief still comes, written from Kit's files. See: kit-cost limit")


def cmd_detect(args):
    blob = ""
    for f in args.files:
        try:
            blob += pathlib.Path(f).read_text(errors="ignore") + "\n"
        except OSError:
            pass
    hit = detect(blob)
    if not hit:
        return 1
    st = record(hit[0], hit[1], args.source)
    print(f"limit {st['reset'] or 'unknown'}")
    return 0


def cmd_check(args):
    st = active()
    if not st:
        print("ok")
        return 0
    if args.probe and not reset_of(st):
        today = now().date().isoformat()
        if st.get("last_probe") != today:
            st["last_probe"] = today
            _write(st)
            print("probe")
            return 0
    print(f"limited {st.get('reset') or 'unknown'}; {st.get('reason', '')}")
    return 2


def cmd_status(args):
    st = load()
    if args.json:
        out = dict(st or {})
        out["active"] = bool(active())
        out["returns"] = when_text(st) if st else None
        print(json.dumps(out))
        return 0
    if not st:
        print("No usage limit recorded: Kit's scheduled runs go ahead.")
        return 0
    st = active()
    if not st:
        print("The recorded usage limit has reset: Kit's scheduled runs go ahead.")
        return 0
    print(f"Usage limit reached ({st.get('source')} run, first seen {st.get('first_seen')}).")
    print(f"  Message: {st.get('reason')}")
    print(f"  Access returns: {when_text(st)}")
    print("  Only the morning brief runs, without a model call, until then. Clear it by hand: kit-cost limit clear")
    return 2


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kit_limits", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect")
    d.add_argument("--source", default="run")
    d.add_argument("files", nargs="*")
    c = sub.add_parser("check")
    c.add_argument("--mode")
    c.add_argument("--probe", action="store_true")
    s = sub.add_parser("success")
    s.add_argument("--source", default="run")
    cl = sub.add_parser("clear")
    cl.add_argument("--why", default="cleared by hand")
    st = sub.add_parser("status")
    st.add_argument("--json", action="store_true")
    sub.add_parser("notice")
    sub.add_parser("when")
    args = ap.parse_args(argv)
    if args.cmd == "detect":
        return cmd_detect(args)
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "success":
        clear(f"a {args.source} run succeeded", None)
        return 0
    if args.cmd == "clear":
        print("Usage limit cleared." if clear(args.why) else "No usage limit was recorded.")
        return 0
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "when":
        st = active()
        print(when_text(st) if st else "")
        return 0
    if args.cmd == "notice":
        print(notice(active()))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

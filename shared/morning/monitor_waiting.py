#!/usr/bin/env python3
"""monitor_waiting.py: items waiting too long, an alert kind for run_alerts.py (kind "waiting").

  python3 monitor_waiting.py [--kit DIR]

Reads QUEUE.md with kit_queue.py's parser. Two kinds of item are watched:
  other     every open item in "Waiting on others";
  decision  the owner's own items that are decisions: titles starting with Approve or Decide, or lines
            containing "decide by".
An item's date is the latest of its "added", "updated", and "since DD-Mmm-YYYY" dates. It alerts when
that's more than WAITING_MAX_DAYS old (default 7). For a waiting-on-others item, run_alerts.py writes a
short, polite follow-up draft to briefs/followups/<slug>.md naming the request and any ticket numbers
exactly as the queue does (never sent, and no names beyond the queue line's own words); for a decision,
the brief line says how many days it has waited and points at the draft or file the item names. No queue
item (these already are queue items). An alert clears when the item is checked off or its line gets a
newer date; its follow-up draft is then removed, unless it was edited.
"""
import argparse
import datetime as dt
import os
import pathlib
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.dirname(HERE)
DATE = r"\d{2}-[A-Z][a-z]{2}-\d{4}"
NOT_OWNER = {"Kit", "Waiting on others", "Sprint", "Someday", "Done"}
TICKET = re.compile(r"\b(?:[A-Z]{2,8}\d{4,}|[A-Z]{2,8}-\d{2,})\b")


def slug(text, n=60):
    s = re.sub(r"[`*_]", "", text).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s[:n].rstrip("-") or "item")


def pdate(s):
    try:
        return dt.datetime.strptime(s, "%d-%b-%Y").date()
    except (TypeError, ValueError):
        return None


def item_date(it, line):
    dates = [d for d in (it.get("added"), it.get("updated")) if d]
    dates += [d for d in (pdate(m) for m in re.findall(r"since (" + DATE + ")", line)) if d]
    return max(dates) if dates else None


def is_decision(title, line):
    return bool(re.match(r"(?:Approve|Decide)\b", title.strip())) or "decide by" in line.lower()


def who_text(rest):
    """What the queue line says after the title, without its trailing (added ...) note or [tags]."""
    rest = re.sub(r"\([^()]*\b(?:added|updated) " + DATE + r"[^()]*\)", "", rest)
    rest = re.sub(r"\[[a-z]+\]", "", rest)
    rest = re.sub(r"\bsince " + DATE, "", rest)
    rest = rest.strip().lstrip(":").strip().rstrip(",;").strip()
    return " ".join(rest.split())


def file_named(line):
    for m in re.findall(r"`([^`]+)`", line):
        if "/" in m or re.search(r"\.[A-Za-z0-9]{2,5}$", m):
            return m
    return None


def items(kit, cfg=None):
    import kit_queue as kq  # noqa: E402
    q = pathlib.Path(kit) / "QUEUE.md"
    if not q.exists():
        return []
    lines = kq.load(q)
    owner = (cfg.get("OWNER_NAME", "") if cfg else "").strip()
    heads = kq.heads(lines)
    owner_sections = [owner] if owner in heads else [h for h in heads if h not in NOT_OWNER]
    out = []
    for it in kq.open_items(lines):
        if it["parent"] is not None:
            continue
        line = lines[it["line"]]
        detail = lines[it["line"] + 1:it["end"]]
        if it["section"] == "Waiting on others":
            kind = "other"
        elif it["section"] in owner_sections and is_decision(it["title"], line):
            kind = "decision"
        else:
            continue
        tickets = []
        for t in TICKET.findall(" ".join([line] + detail)):
            if t not in tickets:
                tickets.append(t)
        out.append({"type": kind, "title": it["title"], "rest": it["rest"], "line": line,
                    "date": item_date(it, line), "tickets": tickets, "file": file_named(line)})
    return out


def draft_text(it, today):
    title = re.sub(r"[`*]", "", it["title"]).strip()
    who = who_text(it["rest"])
    refs = ", ".join(it["tickets"])
    since = it["date"].strftime("%d-%b-%Y")
    ref = f" (reference {refs})" if refs else ""
    return (f"# Follow-up draft: {title}\n\n"
            "Draft only: Kit never sends this. Edit it, and send it yourself if a nudge is due.\n\n"
            + (f"To: {who}\n" if who else "")
            + f"Subject: Following up: {title}{ref}\n\n"
            "Hello,\n\n"
            f"I'm following up on {title}{ref}, open since {since}. Could you let me know where it stands, and "
            "whether you need anything more from me to move it forward?\n\n"
            "Thank you.\n\n"
            "---\n"
            f"From the queue line: {re.sub(r'[*]', '', it['line'][6:]).strip()}\n"
            f"Drafted {today.strftime('%d-%b-%Y')} by Kit (kit-alerts waiting). Removed when the item is checked "
            "off or updated, unless you've edited it.\n")


def problems(kit, cfg=None, now=None, deadline=None):
    now = now or dt.datetime.now()
    max_days = cfg.number("WAITING_MAX_DAYS", 7) if cfg else 7
    out = {}
    for it in items(kit, cfg):
        if not it["date"]:
            continue
        days = (now.date() - it["date"]).days
        if days <= max_days:
            continue
        key = f"waiting:{slug(it['title'])}"
        title = re.sub(r"[`*]", "", it["title"]).strip()
        p = {"type": it["type"], "item": title, "days": days, "date": it["date"].isoformat(),
             "reason": f"{title}: waiting {days} days (since {it['date'].strftime('%d-%b-%Y')})"}
        if it["type"] == "other":
            p["draft"] = f"briefs/followups/{slug(it['title'])}.md"
            p["draft_text"] = draft_text(it, now.date())
        else:
            p["file"] = it["file"]
        out[key] = p
    return out


def main(argv):
    ap = argparse.ArgumentParser(prog="monitor_waiting.py")
    ap.add_argument("--kit", default=os.environ.get("KIT_DIR", os.path.expanduser("~/Claude/Agents/kit")))
    a = ap.parse_args(argv)
    if SHARED not in sys.path:
        sys.path.insert(0, SHARED)
    for key, p in sorted(problems(a.kit).items()):
        print(f"{key}: {p['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

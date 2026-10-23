#!/usr/bin/env python3
"""reg_watch.py: sets up the monthly regulatory watch for the weekly review (run.sh and run.ps1).

With REG_WATCH="on" in the config, the first weekly review of each month (the first Monday, day 1
to 7) asks the researcher for a regulatory watch brief: public changes in the last month to the
regimes and topics in compliance.md's "Regulatory watch" field, from public sources only, each
cited, written from regulatory-watch-template.md and saved in the library, with a three-line
summary in the review. This script makes no web, connector, or model call. It checks the date, the
setup, the budget level, and the time left, and writes the prompt text to add.

  python3 reg_watch.py --prompt FILE --out FILE [--date YYYY-MM-DD] [--when first-monday|every-run]
                       [--cost-level ok|warn|stop] [--timeout SECS] [--min-left 15]
                       [--owner NAME] [--home DIR] [--compliance FILE] [--library FILE]

Prints one of:
  not-due             not the first Monday of the month (REG_WATCH_WHEN="every-run" runs it on
                      every weekly review, for a test); nothing is written to --out
  skip <reason>       due, but the regimes aren't set, the budget is at its warning or stop level,
                      or the time limit is too short; --out gets one line telling Kit to note the
                      skip in the review
  on                  then one permission rule per line: Agent, WebSearch, WebFetch, and Edit on
                      the output folder (when it's outside briefs/); --out gets the brief
"""
import argparse
import datetime as dt
import os
import re
import sys

BAD_PATH = re.compile(r"[()*?\[\]\n\r\"'`;]")
TOPIC_BAD = re.compile(r"[`\"{}<>\\]")


def field(text, name):
    """The value of a '- **<name>:** value' line, with its indented continuation lines."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        m = re.match(r"^- \*\*" + re.escape(name) + r":\*\*\s*(.*)$", ln)
        if m:
            parts = [m.group(1)]
            for nxt in lines[i + 1:]:
                if not nxt.startswith("  ") or nxt.lstrip().startswith("- "):
                    break
                parts.append(nxt.strip())
            return " ".join(p for p in parts if p).strip()
    return ""


def unset(value):
    v = value.strip().lower()
    return not v or v.startswith("not set") or v.startswith("optional") or v.startswith("none")


def regimes(compliance_text):
    """The watch list as one clean string, or '' when it isn't set."""
    v = field(compliance_text, "Regulatory watch")
    if unset(v):
        return ""
    v = TOPIC_BAD.sub("", v).strip().rstrip(".").strip()
    items = [t.strip() for t in re.split(r"[;,]", v) if t.strip()]
    out = "; ".join(items)
    return out[:400].rstrip("; ")


def path_value(value):
    """A folder path from a setup value: backtick-quoted text if there is some, else the value."""
    if unset(value):
        return ""
    m = re.search(r"`([^`]+)`", value)
    v = (m.group(1) if m else value).strip().rstrip(".").strip()
    return v if re.match(r"^(~[\\/]|/|[A-Za-z]:[\\/])", v) else ""


def expand(folder, home):
    folder = folder.strip()
    if folder.startswith("~"):
        folder = home.rstrip("/\\") + folder[1:]
    return folder


def edit_rules(folder, home):
    """Edit rules for the output folder, spelled the way the runners spell their own rules."""
    fwd = folder.replace("\\", "/").rstrip("/")
    home_fwd = home.replace("\\", "/").rstrip("/")
    rules = []
    if home_fwd and (fwd == home_fwd or fwd.startswith(home_fwd + "/")):
        rules.append(f"Edit(~{fwd[len(home_fwd):]}/**)")
    if re.match(r"^[A-Za-z]:/", fwd):
        rules.append(f"Edit({fwd}/**)")
    elif not rules:
        rules.append(f"Edit(/{fwd}/**)")
    return rules


def first_monday(d):
    return d.weekday() == 0 and d.day <= 7


def prev_month(d):
    last = d.replace(day=1) - dt.timedelta(days=1)
    return last.strftime("%Y-%m"), last.strftime("%B %Y")


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def main(argv):
    p = argparse.ArgumentParser(description="Set up the monthly regulatory watch (no web or model call).")
    p.add_argument("--prompt", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--date", default="")
    p.add_argument("--when", default="first-monday")
    p.add_argument("--cost-level", default="ok")
    p.add_argument("--timeout", type=int, default=3000)
    p.add_argument("--min-left", type=int, default=15)
    p.add_argument("--owner", default="the owner")
    p.add_argument("--home", default=os.path.expanduser("~"))
    p.add_argument("--compliance", default="")
    p.add_argument("--library", default="")
    a = p.parse_args(argv)
    kit = os.path.join(a.home, "Claude", "Agents", "kit")
    a.compliance = a.compliance or os.path.join(kit, "memory", "context", "compliance.md")
    a.library = a.library or os.path.join(kit, "memory", "context", "library.md")
    try:
        today = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    except ValueError:
        today = dt.date.today()

    if a.when != "every-run" and not first_monday(today):
        print("not-due")
        return 0

    month, month_name = prev_month(today)
    min_left = max(0, a.min_left)
    topics = regimes(read(a.compliance))
    reason = ""
    if not topics:
        reason = "no regimes set in compliance.md (Regulatory watch)"
    elif a.cost_level in ("warn", "stop"):
        reason = f"the monthly budget is at its {a.cost_level} level"
    elif a.timeout <= min_left * 60:
        reason = "the run's time limit is too short"
    text = read(a.prompt) if not reason else ""
    if not reason and not text:
        reason = "its prompt file is missing"

    # Where the watch goes: the setup's folder, else regulatory-watch/ in the library root, else briefs/.
    folder = path_value(field(read(a.compliance), "Regulatory watch folder"))
    if not folder:
        root = path_value(field(read(a.library), "Library root"))
        if root:
            folder = root.rstrip("/\\") + "/regulatory-watch"
    folder = expand(folder, a.home) if folder else ""
    if folder and (BAD_PATH.search(folder) or not (os.path.isabs(folder) or re.match(r"^[A-Za-z]:[\\/]", folder))):
        folder = ""
    fallback = not folder
    out_file = (f"{kit}/briefs/regulatory-watch-{month}.md" if fallback
                else f"{folder.rstrip('/')}/regulatory-watch-{month}.md").replace("\\", "/")

    if reason:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(f"Monthly regulatory watch: skipped this month ({reason}). Add a \"Regulatory watch\" section "
                    f"to the review with only the line \"Skipped: {reason}.\" Don't ask the researcher for it.\n")
        print(f"skip {reason}")
        return 0

    subs = {"{{OWNER}}": a.owner, "{{REGIMES}}": topics, "{{MONTH}}": month, "{{MONTH_NAME}}": month_name,
            "{{TODAY}}": today.strftime("%d-%b-%Y"), "{{OUT_FILE}}": out_file,
            "{{TEMPLATE}}": "~/Claude/Agents/kit/templates/regulatory-watch-template.md",
            "{{RUN_MINUTES}}": str(a.timeout // 60), "{{MIN_LEFT}}": str(min_left),
            "{{FALLBACK}}": (" (no library folder is set, so it goes in briefs/; say so in the review)"
                             if fallback else "")}
    for k, v in subs.items():
        text = text.replace(k, v)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")
    print("on")
    rules = ["Agent", "WebSearch", "WebFetch"] + ([] if fallback else edit_rules(folder, a.home))
    for r in rules:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""kit_settings: every Kit setting in one place, for the dashboard's Settings panel, `kit-settings show --all`,
and the local editing page (`kit-settings ui`, kit_settings_ui.py).

It gathers three kinds of setting, by area:
  - the run config (.install/shared/morning/config, shell KEY="value" lines), described by
    shared/morning/config.example and INSTALL.md's settings tables
  - the setup fields ("- **Field:** value") in the setup files in memory/context/ (only the files Kit ships,
    so Kit's own memory notes there are left out); memory/personal/ is never read
  - the JSON configs in memory/context/ and models.json (read-only)

Credentials appear by name only: a value whose key says it's a token, secret, or password is masked unless the
key ends in _ENV, _KEYCHAIN, or _NAME (those hold the name of an environment variable or a Keychain entry), and
any value that looks like a credential (kit_records.SECRET_PATTERNS) is masked wherever it is.

Editing goes through plan_edit() and apply_edit(): one setting at a time, only those on the allowlist, each value
checked by its type. A config edit changes one line; a setup-field edit replaces that field's own line (and its
wrapped continuation lines, as kit-oneonone --done does), keeping every other byte. The file is backed up first
and the change committed to Kit's private repo where the file is tracked. Standard library only.
"""
import datetime as dt
import difflib
import hashlib
import html
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import kit_compliance as kc  # noqa: E402  (kit_dir, setting, MONTHS)
import kit_records  # noqa: E402  (SECRET_PATTERNS)

try:  # the health check's list of path fields, and what "unset on purpose" looks like
    import doctor as _doctor
    SETUP_PATH_FIELDS = {(f, n) for f, n, _ in _doctor.SETUP_PATH_FIELDS}
    SETUP_UNSET = _doctor.SETUP_UNSET
except Exception:  # pragma: no cover  (doctor.py ships next to this file)
    SETUP_PATH_FIELDS = set()
    SETUP_UNSET = re.compile(r"^[_*`]*(?:not set|optional|none)\b", re.I)

e = html.escape
AREAS = ["delivery and briefs", "connectors and guard", "library and documents", "compliance",
         "agents and models", "sharing", "scheduling", "other"]
CONFIG_REL = ".install/shared/morning/config"
MASK = "•••• (masked)"

# The same config line rule kit-settings uses (KEY=value, optional quotes).
CONFIG_LINE = re.compile(r'^\s*([A-Z_][A-Z0-9_]*)=(.*?)\s*$')
FIELD_LINE = re.compile(r"^- \*\*(.+?):\*\*[ \t]?(.*)$")

# ---------------------------------------------------------------------------------------------------------------
# Secrets: by key name, and by what the value looks like.

SECRET_KEY = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|PASSPHRASE|(^|_)PAT($|_)|API_?KEY|PRIVATE_KEY|CREDENTIAL)", re.I)
NAME_SUFFIX = re.compile(r"(_ENV|_KEYCHAIN|_NAME|_VAR|_ENTRY)$|(^|_)(env|keychain_entry|credential_env)$", re.I)


def secret_key(key):
    """True when the key says its value is a credential itself (not the name of one)."""
    return bool(SECRET_KEY.search(key or "")) and not NAME_SUFFIX.search(key or "")


def looks_secret(text):
    """True when the text holds something credential-shaped (kit_records.SECRET_PATTERNS, less the long-number
    rule, which phone numbers and IDs trip)."""
    t = str(text or "")
    return any(re.search(p, t) for p, what in kit_records.SECRET_PATTERNS if what != "account or card number")


def mask_text(text):
    """The text with anything credential-shaped replaced by the mask."""
    out = str(text or "")
    for pat, what in kit_records.SECRET_PATTERNS:
        if what == "account or card number":
            continue
        out = re.sub(pat, MASK, out)
    return out


# ---------------------------------------------------------------------------------------------------------------
# Where things are.

def kit_dir(kit=None):
    return pathlib.Path(kc.kit_dir(str(kit) if kit else None))


def _first(*paths):
    for p in paths:
        if p and pathlib.Path(p).is_file():
            return pathlib.Path(p)
    return None


def shipped_context(kit):
    """The folder holding the setup files as Kit ships them (the installed package, else this repo)."""
    for c in (kit / ".install/kit/memory/context", HERE.parent / "kit/memory/context"):
        if c.is_dir():
            return c
    return None


def read_text(path):
    try:
        return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def sentence(text, limit=220):
    t = " ".join(str(text or "").split())
    m = re.match(r"(.+?[.!?])(\s|$)", t)
    t = m.group(1) if m else t
    return t if len(t) <= limit else t[:limit - 1].rstrip() + "…"


# ---------------------------------------------------------------------------------------------------------------
# The run config: what's documented, and what's set.

def config_catalog(kit):
    """{KEY: {"example": value or None, "commented": bool, "desc": str, "default": str}} from config.example
    and INSTALL.md's settings tables."""
    cat = {}
    ex = _first(kit / ".install/shared/morning/config.example", HERE / "morning/config.example")
    block, header = [], True          # the file's opening comment describes the file, not a key
    for line in (read_text(ex).splitlines() if ex else []):
        s = line.strip()
        if not s:
            block, header = [], False
            continue
        m = re.match(r'^(#\s*)?([A-Z_][A-Z0-9_]*)=(.*)$', s)
        if m:
            key, val = m.group(2), _unquote(m.group(3))
            text = " ".join(block)
            sents = re.split(r"(?<=[.!?])\s+", text)
            pick = next((x for x in sents if key in x), sents[0] if sents else "")
            cat.setdefault(key, {"example": None if m.group(1) else val, "commented": bool(m.group(1)),
                                 "desc": sentence(pick), "default": "" if m.group(1) else val})
            continue
        if s.startswith("#") and not header:
            block.append(s.lstrip("#").strip())
    inst = _first(kit / ".install/INSTALL.md", HERE.parent / "INSTALL.md")
    for line in (read_text(inst).splitlines() if inst else []):
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        keys = re.findall(r"`([A-Z][A-Z0-9_]+)`", cells[0])
        if not keys or len(cells) < 2:
            continue
        default, desc = (cells[1], cells[2]) if len(cells) >= 3 else ("", cells[1])
        default = default.replace("`", "").strip()
        if default.lower() in ("unset", "empty", "none"):
            default = ""
        for k in keys:
            c = cat.setdefault(k, {"example": None, "commented": True, "desc": "", "default": ""})
            if len(cells) >= 3 or not c["desc"]:     # the per-key tables say more than the grouped one
                c["desc"] = sentence(desc.replace("`", "")) or c["desc"]
            if len(cells) >= 3 and c["example"] is None and not c["default"]:
                c["default"] = default
    return cat


def _unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def config_entries(kit):
    """[(key, raw value, line number)] in the live config, in file order."""
    out = []
    for n, line in enumerate(read_text(kit / CONFIG_REL).splitlines(), 1):
        m = CONFIG_LINE.match(line)
        if m:
            out.append((m.group(1), _unquote(m.group(2)), n))
    return out


# Delivery channels and to-do apps, as kit-settings knows them.
CHANNELS = ("local", "imessage", "outlook-drafts", "outlook-review", "sms")
TODO_APPS = ("apple", "outlook")
OUTSIDE_M365 = {"imessage", "sms", "apple"}
PLACEHOLDERS = {"you@example.com", "+15555550123"}
RUN_MODES = ("morning", "open", "weekly", "worklist", "eod", "journal", "backup", "sync", "meetprep", "letters")

# The run config keys the editing page may change, and the type each must be. Everything else is read-only.
EDITABLE_CONFIG = {
    "OWNER_NAME": ("name",),
    "DELIVERY": ("channels", "all"), "DELIVERY_PERSONAL": ("channels", "personal"),
    "DELIVERY_WORK": ("channels", "work"), "DELIVERY_EMAIL_TO": ("email",),
    "IMESSAGE_TO": ("phone_or_email",), "IMESSAGE_TO_ALT": ("phone_or_email",),
    "TEXTBACK_MAX_PER_HOUR": ("int", 1, 600),
    "REMINDERS_BACKEND": ("todo", "all"), "TODOS_PERSONAL": ("todo", "personal"), "TODOS_WORK": ("todo", "work"),
    "SKIP_DAYS": ("days", True), "WRAP_WORKDAYS": ("days", False),
    "DEMAND_REFRESH": ("onoff",), "DEMAND_REGISTER_DIR": ("path",),
    "DEMAND_REFRESH_MAX": ("int", 1, 500), "DEMAND_REFRESH_MIN_LEFT": ("int", 0, 240),
    "REG_WATCH_WHEN": ("choice", ("first-monday", "every-run")), "REG_WATCH_MIN_LEFT": ("int", 0, 240),
    "BACKUP_KEEP": ("int", 1, 365), "SNAPSHOT_KEEP": ("int", 1, 500),
    "OUTLOOK_RETRY_WAITS": ("waits",), "OUTLOOK_CHECK": ("onoff",),
    "OUTLOOK_RECOVER": ("choice", ("off", "notify", "restart")), "OUTLOOK_DEEP_TIMEOUT": ("int", 5, 120),
    "OUTLOOK_QUIT_WAIT": ("int", 5, 600), "OUTLOOK_RESTART_SETTLE": ("int", 5, 600),
    "CALENDAR_CACHE": ("onoff",), "CALENDAR_CACHE_DAYS": ("int", 1, 31), "CALENDAR_CACHE_KEEP": ("int", 1, 60),
    "CALENDAR_CACHE_TIMEOUT": ("int", 5, 600),
    "CONNECTOR_CHECK": ("onoff",), "CONNECTOR_CHECK_TIMEOUT": ("int", 5, 1800), "CONNECTOR_FAIL_STREAK": ("int", 1, 30),
    "COST_BUDGET_MONTHLY": ("float", 0, 100000, True), "COST_WARN_PCT": ("int", 1, 100),
    "COST_STOP_PCT": ("int", 1, 200), "COST_ESSENTIAL_MODES": ("modes",),
    "COST_ALERT_PROJECTION": ("float", 0.1, 5, True), "COST_SPIKE_FACTOR": ("float", 1, 100),
    "DEGRADED_MODE": ("onoff",),
    "USAGE_LIMIT_MONTHLY_USD": ("float", 0, 100000, True), "USAGE_LIMIT_GUARD": ("onoff",),
    "RUN_TIMEOUT": ("int", 60, 14400, True), "RUN_TIMEOUT_WEEKLY": ("int", 60, 14400, True),
    "RUN_TIMEOUT_WORKLIST": ("int", 60, 14400, True), "RUN_TIMEOUT_EOD": ("int", 30, 14400, True),
    "RUN_LOCK_WAIT": ("int", 0, 14400, True),
    "EOD": ("onoff",), "EOD_MODEL": ("onoff",), "WRAP_CALENDAR_SIDE": ("choice", ("work", "personal")),
    "PPMX_PULSE": ("onoff",), "PPMX_PULSE_DAY": ("int", 1, 7), "PPMX_PULSE_SCOPE": ("scope",),
    "PPMX_PULSE_TIMEOUT": ("int", 10, 3600), "PPMX_TASK_DUE_FIELD": ("ident",),
    "REHEARSE_TIMEOUT": ("int", 60, 14400), "PREREAD_TIMEOUT": ("int", 60, 14400),
    "REVIEW_LOOP_TIMEOUT": ("int", 60, 14400), "READINESS_THRESHOLD": ("int", 1, 100),
    "TICKET_MAX": ("int", 1, 100), "TICKET_DAYS": ("int", 1, 60),
    "TICKET_UNASSIGNED_DAYS": ("int", 0, 90), "TICKET_BOUNCE_MOVES": ("int", 0, 20), "TICKET_ROUTING_FILE": ("path",),
    "QUEUE_DUP_THRESHOLD": ("float", 0.5, 1, True),
    "MCP_WATCH": ("onoff",), "MCP_WATCH_LONG_HOURS": ("int", 1, 168),
    "ARCH_DIGEST": ("onoff",), "ARCH_DIGEST_WHEN": ("choice", ("first-week", "every-run")),
    "ARCH_DIGEST_TIMEOUT": ("int", 10, 3600),
    "TEAMMAP_MAX_LOAD": ("int", 1, 1000), "TEAMMAP_MAX_ITEMS": ("int", 1, 1000), "TEAMMAP_COVERAGE": ("path",),
    "RETRY_ON": ("onoff",), "RETRY_DELAY": ("int", 0, 3600), "RELIABILITY_MIN_PCT": ("int", 0, 100),
    "RUN_ALERTS": ("onoff",), "RUN_ALERTS_TIMEOUT": ("int", 5, 600), "RUN_FAIL_STREAK": ("int", 1, 30),
    "MONITOR_DRIFT": ("onoff",), "MONITOR_LIBRARY": ("onoff",), "MONITOR_WAITING": ("onoff",),
    "MONITOR_EXCEPTIONS": ("onoff",), "MONITOR_TIMEOUT": ("int", 1, 600),
    "LIBRARY_UNINDEXED_MAX": ("int", 0, 100000), "LIBRARY_INDEX_MAX_DAYS": ("int", 1, 3650),
    "LIBRARY_SYNC_MAX_DAYS": ("int", 0, 3650), "WAITING_MAX_DAYS": ("int", 1, 365),
    "EXCEPTIONS_WARN_DAYS": ("int", 1, 365),
    "PREFLIGHT_CONNECTORS": ("names",), "CONNECTION_CHECK": ("onoff",), "CONNECTION_WAIT": ("int", 0, 3600),
}

# ---------------------------------------------------------------------------------------------------------------
# How the settings page presents each setting: the page's groups, then one line per run config key with its group,
# a plain-English label, and a line of help (and a default where config.example doesn't give one). The type, and
# whether the page may change it at all, stays in EDITABLE_CONFIG above (the allowlist); a key listed here but not
# there shows read-only. A key in neither shows in Advanced under its raw name, so nothing is ever hidden.
# To add a setting: one line here, and one in EDITABLE_CONFIG if the page may change it.

GROUPS = [
    ("delivery", "Delivery", "Where the brief, alerts, and texts reach you."),
    ("briefs", "Briefs & schedule", "What the scheduled runs do, and when."),
    ("todos", "To-dos & sync", "Which apps your to-dos sync with, and the queue's checks."),
    ("connectors", "Connectors", "Outlook, PPM Express, ServiceNow, and the checks before each run."),
    ("budget", "Budget & limits", "What Kit may spend, time limits, and retries."),
    ("documents", "Documents", "The library, templates, writing, diagrams, and reviews."),
    ("agents", "Agents & reviews", "What Kit's staff of agents read: standards, compliance, estimating, labs."),
    ("privacy", "Privacy & retention", "What leaves this computer, backups, and records retention."),
    ("advanced", "Advanced", "Everything else, including keys the page has no description for."),
]
GROUP_IDS = [g for g, _, _ in GROUPS]

# KEY: (group, label, help[, default]).
META = {
    "OWNER_NAME": ("delivery", "Your name", "The name Kit uses for you in briefs, drafts, and the queue."),
    "DELIVERY": ("delivery", "Brief delivery (all items)", "Where the morning brief goes when work and personal go the same way."),
    "DELIVERY_PERSONAL": ("delivery", "Brief delivery: personal items", "Overrides Brief delivery for personal items."),
    "DELIVERY_WORK": ("delivery", "Brief delivery: work items", "Overrides Brief delivery for work items; only Microsoft 365 channels."),
    "DELIVERY_EMAIL_TO": ("delivery", "Email address for drafts", "The address the Outlook draft is addressed to (you)."),
    "IMESSAGE_TO": ("delivery", "Text messages to", "Your phone number or Apple ID for iMessage texts."),
    "IMESSAGE_TO_ALT": ("delivery", "Text messages: second address", "Another number or Apple ID Kit may text."),
    "TEXTBACK": ("delivery", "Text Kit commands", "Lets you text \"kit ...\" to yourself to ask Kit or change its lists."),
    "TEXTBACK_ASK": ("delivery", "Text Kit questions", "Lets a texted question start a read-only model run."),
    "TEXTBACK_MAX_PER_HOUR": ("delivery", "Texts answered per hour", "A cap on how many texted commands Kit answers in an hour."),
    "PHONE_APPROVALS": ("delivery", "Approvals from the phone", "Whether approval codes can arrive from the phone."),
    "SKIP_DAYS": ("briefs", "Days with no brief", "Weekdays (1 Monday to 7 Sunday) when the morning run doesn't run."),
    "WRAP_WORKDAYS": ("briefs", "End-of-day wrap days", "Weekdays the end-of-day wrap runs."),
    "EOD": ("briefs", "End-of-day wrap", "A short wrap of the day at its end."),
    "EOD_MODEL": ("briefs", "End-of-day wrap uses the model", "Off writes the wrap from Kit's files alone, with no model call."),
    "WRAP_CALENDAR_SIDE": ("briefs", "Wrap's calendar", "Which calendar the wrap reads."),
    "WRAP_CALENDAR_CMD": ("briefs", "Wrap's calendar command", "The command the wrap runs to read the calendar."),
    "CALENDAR_JSON_CMD": ("briefs", "Calendar command", "The command the degraded brief runs to read today's calendar."),
    "DEGRADED_MODE": ("briefs", "Brief without the model", "When the model can't run, write a shorter brief from Kit's files."),
    "DEMAND_REFRESH": ("briefs", "Weekly demand refresh", "The weekly review refreshes the demand register from ServiceNow."),
    "DEMAND_REGISTER_DIR": ("briefs", "Demand register folder", "Where the demand register is kept."),
    "DEMAND_REFRESH_MAX": ("briefs", "Demands per refresh", "The most demands one refresh reads."),
    "DEMAND_REFRESH_MIN_LEFT": ("briefs", "Minutes needed for the refresh", "Skip the refresh if less run time than this is left."),
    "DEMAND_SERVER": ("briefs", "Demand refresh connector", "The connector the demand refresh calls."),
    "DEMAND_TOOLS": ("briefs", "Demand refresh tools", "The connector tools the demand refresh may call."),
    "REG_WATCH": ("briefs", "Regulatory watch", "The weekly review's web search for regulatory changes."),
    "REG_WATCH_WHEN": ("briefs", "Regulatory watch: when", "First Monday of the month, or every weekly review."),
    "REG_WATCH_MIN_LEFT": ("briefs", "Minutes needed for the watch", "Skip the watch if less run time than this is left."),
    "ARCH_DIGEST": ("briefs", "Monthly architecture digest", "The first weekly review of the month drafts last month's digest."),
    "ARCH_DIGEST_WHEN": ("briefs", "Digest: when", "First week of the month, or every run."),
    "ARCH_DIGEST_TIMEOUT": ("briefs", "Digest time limit (s)", "Seconds the digest may take."),
    "MONTH_REPORT_MODES": ("briefs", "Monthly report: runs counted", "Which runs the monthly report counts."),
    "TICKET_WATCH": ("briefs", "Ticket watcher", "The brief's \"Your tickets\" section, from ServiceNow, read-only."),
    "TICKET_SERVER": ("briefs", "Ticket watcher connector", "The connector the ticket watcher searches."),
    "TICKET_TOOLS": ("briefs", "Ticket watcher tools", "The connector tools the ticket watcher may call."),
    "TICKET_QUERY": ("briefs", "Ticket watcher search", "What the ticket watcher searches for."),
    "TICKET_MAX": ("briefs", "Tickets per brief", "The most tickets the brief lists."),
    "TICKET_DAYS": ("briefs", "Ticket look-back (days)", "How far back the ticket watcher looks."),
    "TICKET_UNASSIGNED_DAYS": ("briefs", "Unassigned ticket warning (days)", "Flag a ticket still unassigned after this many days."),
    "TICKET_ROUTING_FILE": ("briefs", "Ticket routing rules", "The file that says which queue each kind of ticket belongs in."),
    "PPMX_PULSE": ("briefs", "PPM Express weekly pulse", "A weekly line on your PPM Express work, read-only."),
    "PPMX_PULSE_DAY": ("briefs", "Pulse day", "The weekday (1 Monday to 7 Sunday) the pulse runs."),
    "PPMX_PULSE_SCOPE": ("briefs", "Pulse scope", "\"all\", \"mine\", or portfolio and program names."),
    "PPMX_PULSE_TIMEOUT": ("briefs", "Pulse time limit (s)", "Seconds the pulse may take."),
    "PPMX_TASK_DUE_FIELD": ("briefs", "PPM Express due-date field", "The task field that holds the due date."),
    "REMINDERS_BACKEND": ("todos", "To-do app (all items)", "Where your to-dos sync when work and personal go the same way."),
    "TODOS_PERSONAL": ("todos", "To-do app: personal", "Overrides the to-do app for personal items."),
    "TODOS_WORK": ("todos", "To-do app: work", "Overrides the to-do app for work items; Outlook only."),
    "QUEUE_DUP_THRESHOLD": ("todos", "Duplicate to-do warning", "How alike a new to-do must be to an open one before todo warns."),
    "WAITING_MAX_DAYS": ("todos", "Waiting items: nudge after (days)", "An item waiting on someone this long gets a nudge drafted."),
    "MONITOR_WAITING": ("todos", "Watch waiting items", "Check the waiting list in each run."),
    "OUTLOOK_CHECK": ("connectors", "Check Outlook before runs", "Make sure classic Outlook answers before a run relies on it."),
    "OUTLOOK_RETRY_WAITS": ("connectors", "Outlook retry waits (s)", "Seconds to wait between tries when Outlook is slow, e.g. \"30 90\"."),
    "OUTLOOK_RECOVER": ("connectors", "Outlook recovery", "What Kit does when Outlook is running but hung."),
    "OUTLOOK_DEEP_TIMEOUT": ("connectors", "Outlook calendar check time limit", "Seconds the calendar part of the Outlook check may take before Outlook counts as hung (default 20)."),
    "OUTLOOK_QUIT_WAIT": ("connectors", "Outlook restart: wait to close", "Seconds to wait for a hung Outlook to close during a restart (default 60)."),
    "OUTLOOK_RESTART_SETTLE": ("connectors", "Outlook restart: wait to settle", "Seconds to wait after reopening Outlook before checking it again (default 45)."),
    "CALENDAR_CACHE": ("briefs", "Keep a calendar copy for the brief", "Save each good calendar read so a brief on an Outlook-down morning still has meetings, marked stale."),
    "CALENDAR_CACHE_DAYS": ("briefs", "Calendar copy: days ahead", "How many days from today the calendar copy command covers (default 1)."),
    "CALENDAR_CACHE_KEEP": ("briefs", "Calendar copy: days kept", "How many days of saved calendar copies to keep (default 14)."),
    "CALENDAR_CACHE_TIMEOUT": ("briefs", "Calendar copy: time limit", "Seconds the calendar copy may take before it's skipped."),
    "USAGE_LIMIT_GUARD": ("budget", "Usage-limit guard", "Stand the scheduled runs down while Claude's usage limit holds, with one notice and a brief from Kit's own files."),
    "TICKET_BOUNCE_MOVES": ("connectors", "Ticket bounced after N moves", "Flag a ticket moved between groups this many times (default 2; 0 turns it off)."),
    "CONNECTOR_CHECK": ("connectors", "Morning connector check", "One PASS/FAIL line per connector at the top of the brief."),
    "CONNECTOR_CHECK_TIMEOUT": ("connectors", "Connector check time limit (s)", "Seconds the connector check may take."),
    "CONNECTOR_FAIL_STREAK": ("connectors", "Alert after failed checks", "Alert when a connector fails this many mornings in a row."),
    "PREFLIGHT_CONNECTORS": ("connectors", "Sign-in checks before runs", "Connectors whose sign-in the preflight checks."),
    "CONNECTION_CHECK": ("connectors", "Internet check", "Check the internet connection before a model run."),
    "CONNECTION_WAIT": ("connectors", "Wait for the internet (s)", "How long to wait for a connection before a degraded brief."),
    "CONNECTION_URL": ("connectors", "Internet check address", "The address the internet check tries."),
    "MCP_WATCH": ("connectors", "Connector session watchdog", "Notice stale or signed-out connector sessions."),
    "MCP_WATCH_LONG_HOURS": ("connectors", "Long session after (hours)", "A connector session older than this is called long."),
    "PPMX_BASE_URL": ("connectors", "PPM Express address", "Where the PPM Express connector connects (kit-ppmx setup)."),
    "PPMX_MY_NAME": ("connectors", "Your name in PPM Express", "How PPM Express names you."),
    "PPMX_TOKEN_ENV": ("connectors", "PPM Express token variable", "The environment variable holding the token (its name only)."),
    "PPMX_TOKEN_KEYCHAIN": ("connectors", "PPM Express token Keychain entry", "The Keychain entry holding the token (its name only)."),
    "MONITOR_GUARD": ("connectors", "Connector guard monitor", "Check the connector guard's integrity in each run."),
    "GUARD_NORESULT_HOURS": ("connectors", "Guard: call with no result after (hours)", "When a logged call with no result counts as a problem."),
    "GUARD_WINDOW_DAYS": ("connectors", "Guard monitor window (days)", "How many days of the audit log the monitor reads."),
    "COST_BUDGET_MONTHLY": ("budget", "Monthly budget (USD)", "What Kit's scheduled runs may spend in a month; empty for no budget."),
    "COST_WARN_PCT": ("budget", "Warn at (% of budget)", "The brief says how much is used from this share on."),
    "COST_STOP_PCT": ("budget", "Stop at (% of budget)", "Runs other than the essential ones skip from this share on."),
    "COST_ESSENTIAL_MODES": ("budget", "Runs that always go ahead", "Run kinds that still run at the stop level."),
    "COST_ALERT_PROJECTION": ("budget", "Projection alert", "Alert when the month is projected over this multiple of the budget."),
    "COST_SPIKE_FACTOR": ("budget", "Spike alert", "Alert when a day costs this many times the usual."),
    "USAGE_LIMIT_MONTHLY_USD": ("budget", "API usage limit (USD a month)", "Your account's monthly API limit, so Kit slows down before it's hit."),
    "RUN_TIMEOUT": ("budget", "Morning run time limit (s)", "Seconds the morning run may take."),
    "RUN_TIMEOUT_WEEKLY": ("budget", "Weekly review time limit (s)", "Seconds the weekly review may take."),
    "RUN_TIMEOUT_WORKLIST": ("budget", "Work list time limit (s)", "Seconds the work-list run may take."),
    "RUN_TIMEOUT_EOD": ("budget", "End-of-day time limit (s)", "Seconds the end-of-day wrap may take."),
    "RUN_LOCK_WAIT": ("budget", "Wait for another run (s)", "How long a run waits when another is still going."),
    "RETRY_ON": ("budget", "Retry after a passing failure", "Retry once after an overload, rate limit, or network error."),
    "RETRY_DELAY": ("budget", "Retry delay (s)", "Seconds before the retry."),
    "RELIABILITY_MIN_PCT": ("budget", "Run reliability floor (%)", "Warn when fewer runs than this succeed in a week."),
    "RUN_ALERTS": ("budget", "Run failure alerts", "Alert when runs fail repeatedly."),
    "RUN_ALERTS_TIMEOUT": ("budget", "Run alerts time limit (s)", "Seconds the alerts check may take."),
    "RUN_FAIL_STREAK": ("budget", "Alert after failed runs", "Alert after this many failed runs in a row."),
    "REHEARSE_TIMEOUT": ("budget", "Rehearsal time limit (s)", "Seconds a review rehearsal may take."),
    "PREREAD_TIMEOUT": ("budget", "Pre-read time limit (s)", "Seconds a pre-read may take."),
    "REVIEW_LOOP_TIMEOUT": ("budget", "Review loop time limit (s)", "Seconds each review in the loop may take."),
    "MONITOR_TIMEOUT": ("budget", "Monitor time limit (s)", "Seconds each monitor may take."),
    "LIBRARY_UNINDEXED_MAX": ("documents", "Unindexed documents allowed", "Warn when more documents than this aren't indexed."),
    "LIBRARY_INDEX_MAX_DAYS": ("documents", "Index age warning (days)", "Warn when the library index is older than this."),
    "LIBRARY_SYNC_MAX_DAYS": ("documents", "Sync age warning (days)", "Warn when a synced library hasn't synced in this long."),
    "MONITOR_LIBRARY": ("documents", "Watch the library", "Check the library in each run."),
    "MONITOR_DRIFT": ("documents", "Watch for drifted copies", "Check for same-named documents that differ."),
    "READINESS_THRESHOLD": ("documents", "Ready for ARB at", "The readiness score a draft needs to be called ready."),
    "TEAMMAP_COVERAGE": ("documents", "Team coverage list", "The file listing who knows which system."),
    "TEAMMAP_MAX_LOAD": ("documents", "Team member overloaded at", "Hours of assigned work that count as overloaded."),
    "TEAMMAP_MAX_ITEMS": ("documents", "Team member overloaded at (items)", "Assigned items that count as overloaded."),
    "MONITOR_EXCEPTIONS": ("agents", "Watch standards exceptions", "Check for exceptions coming up for renewal."),
    "EXCEPTIONS_WARN_DAYS": ("agents", "Exception warning (days)", "Warn this many days before an exception expires."),
    "REHEARSE_MODEL": ("agents", "Rehearsal model", "The model a review rehearsal uses (kit-models)."),
    "PREREAD_MODEL": ("agents", "Pre-read model", "The model a pre-read uses (kit-models)."),
    "REVIEW_LOOP_MODEL": ("agents", "Review loop model", "The model the review loop uses (kit-models)."),
    "TEXTBACK_MODEL": ("agents", "Text answers model", "The model texted questions use."),
    "TEXTBACK_PARSE_MODEL": ("agents", "Text commands model", "The model that reads texted commands."),
    "BACKUP_KEEP": ("privacy", "Backups kept", "How many daily backups to keep."),
    "BACKUP_DIR": ("privacy", "Backup folder", "Where the encrypted backups go (kit-backup)."),
    "BACKUP_ENCRYPT": ("privacy", "Encrypt backups", "Whether backups are encrypted."),
    "BACKUP_KEY_ENV": ("privacy", "Backup key variable", "The environment variable holding the backup key (its name only)."),
    "BACKUP_KEY_KEYCHAIN": ("privacy", "Backup key Keychain entry", "The Keychain entry holding the backup key (its name only)."),
    "SNAPSHOT_KEEP": ("privacy", "Configuration snapshots kept", "How many kit-config snapshots to keep (default 30)."),
    "ONEDRIVE_PUBLISH_DIR": ("privacy", "OneDrive publish folder", "Where kit-publish puts what you share."),
    "ONEDRIVE_ALLOWED_PREFIX": ("privacy", "OneDrive allowed path", "Publishing is allowed only under this path."),
    "PUBLISH_PERSONAL": ("privacy", "Publish personal items", "Whether anything personal may be published (normally off)."),
    "ALLOW_TOOLS": ("advanced", "Extra tools for the morning run", "Permission rules the unattended morning run gets."),
    "ALLOW_TOOLS_WEEKLY": ("advanced", "Extra tools for the weekly review", "Permission rules the unattended weekly review gets."),
    "BLOCK_TOOLS": ("advanced", "Tools the runs may never use", "Permission rules the unattended runs are denied."),
}
for _k in ("MORNING", "WEEKLY", "WORKLIST", "EOD", "SYNC", "BACKUP"):
    META.setdefault(f"RUN_WINDOW_{_k}", ("briefs", f"Catch-up window: {_k.lower()} (min)",
                                         f"If the {_k.lower()} run was missed, run it if it's no later than this "
                                         "many minutes; \"off\" never catches up."))

# Setup files and JSON configs, by group.
SETUP_GROUPS = {
    "briefs": ("calendar", "meetings", "oneonone", "triage", "status", "worklist", "letters", "timeoff", "reviews"),
    "todos": ("demands", "intake"),
    "connectors": ("connectors", "audit", "graph"),
    "documents": ("library", "writing", "diagrams", "decisions", "knowledge", "precedent", "project-types",
                  "onboarding", "changeboard"),
    "agents": ("agents", "standards", "compliance", "costs", "estimating", "poc", "labs", "training", "future-tech",
               "exploration", "expertise"),
    "privacy": ("retention", "sharing"),
}
JSON_GROUPS = {"connector-guard.json": "connectors", "models.json": "agents", "sharing-policy.json": "privacy",
               "sharing-db.json": "privacy", "retention.json": "privacy", "drawio-styles.json": "documents",
               "diagram-lint-rules.json": "documents", "vsdx-finish.json": "documents"}


def group_of(s):
    """The settings page's group for a setting."""
    if s["kind"] == "config":
        m = META.get(s["name"])
        return m[0] if m and m[0] in GROUP_IDS else "advanced"
    if s["kind"] == "setup":
        stem = pathlib.PurePosixPath(s["source"]).stem
        return next((g for g, names in SETUP_GROUPS.items() if stem in names), "advanced")
    if s["kind"] == "json":
        name = pathlib.PurePosixPath(s["source"]).name
        return JSON_GROUPS.get("models.json" if s["source"].startswith("models") else name, "advanced")
    return "advanced"


def label_of(s):
    if s["kind"] == "config":
        m = META.get(s["name"])
        return m[1] if m else s["name"]
    return s["name"]


def help_of(s):
    if s["kind"] == "config":
        m = META.get(s["name"])
        if m and m[2]:
            return m[2]
    return s["description"]


def default_of(s, cat=None):
    """The value 'Reset to default' writes, or None when there's no default the page can write."""
    if s["kind"] == "config":
        m = META.get(s["name"])
        if m and len(m) > 3:
            return m[3]
        c = (cat or {}).get(s["name"])
        if c is None:
            return None
        return c["example"] if c.get("example") is not None else (c.get("default") or "")
    if s["kind"] == "setup":
        return s.get("shipped")
    return None


BY_HAND = "Edit .install/shared/morning/config by hand, or ask Kit in a session (Claude Code asks before it edits .install)."
# Why a run config key is read-only here, and how to change it (first match wins).
CONFIG_READONLY = [
    (r"^(ALLOW_TOOLS|BLOCK_TOOLS)", "Permission rules for the unattended runs. " + BY_HAND),
    (r"_MODEL$", "A model choice (model routing): see kit-models. " + BY_HAND),
    (r"^TEXTBACK(_ASK)?$", "Turns on taking commands by text. See kit-textback status. " + BY_HAND),
    (r"_CMD$", "A command Kit runs. " + BY_HAND),
    (r"^DEMAND_(SERVER|TOOLS)$", "Which connector tools a run may call; must match connector-guard.json. " + BY_HAND),
    (r"^REG_WATCH$", "Gives the weekly review web search tools. " + BY_HAND),
    (r"^TICKET_(WATCH|SERVER|TOOLS|QUERY)$", "Gives the morning run connector tools through the gateway, and what it "
                                             "searches for; must match connector-guard.json. " + BY_HAND),
    (r"^BACKUP_(DIR|ENCRYPT|KEY_)", "Where backups go and how they're protected: see kit-backup. " + BY_HAND),
    (r"^PHONE_APPROVALS$", "An approval route from the phone. " + BY_HAND),
    (r"^(ONEDRIVE_|PUBLISH_PERSONAL)", "What leaves this computer. " + BY_HAND),
    (r"^(MONITOR_GUARD|GUARD_)", "The connector guard's integrity monitor. " + BY_HAND),
    (r"^PPMX_(BASE_URL|TOKEN|MY_NAME)", "The PPM Express connection: kit-ppmx setup."),
    (r"(_URL|_HOST|_ENDPOINT)$", "Where Kit connects. " + BY_HAND),
]


def config_area(key):
    for pat, area in (
            (r"^(OWNER_NAME|DELIVERY|IMESSAGE|TEXTBACK|REMINDERS_BACKEND|TODOS_|EOD|WRAP_|DEGRADED_MODE|ARCH_DIGEST|"
             r"REG_WATCH|PHONE_APPROVALS|CALENDAR_JSON_CMD|CALENDAR_CACHE)", "delivery and briefs"),
            (r"^(CONNECTOR_|DEMAND_|PPMX_|PREFLIGHT_|CONNECTION_|MONITOR_GUARD|GUARD_|OUTLOOK_)", "connectors and guard"),
            (r"^(LIBRARY_|MONITOR_LIBRARY)", "library and documents"),
            (r"^(MONITOR_EXCEPTIONS|EXCEPTIONS_)", "compliance"),
            (r"(_MODEL$|^REHEARSE_|^PREREAD_|^REVIEW_LOOP_)", "agents and models"),
            (r"^(ONEDRIVE_|PUBLISH_PERSONAL)", "sharing"),
            (r"^(SKIP_DAYS|RUN_|RETRY_|RELIABILITY_|COST_|USAGE_LIMIT_|BLOCK_TOOLS|ALLOW_TOOLS|MONITOR_|WAITING_)", "scheduling")):
        if re.search(pat, key):
            return area
    return "other"


def config_settings(kit):
    cat = config_catalog(kit)
    entries = config_entries(kit)
    counts = {}
    for k, _, _ in entries:
        counts[k] = counts.get(k, 0) + 1
    seen, out = set(), []
    live = {}
    for k, v, n in entries:
        live[k] = (v, n)          # the shell takes the last one, so this does too
    exists = (kit / CONFIG_REL).is_file()
    for key in list(dict.fromkeys(list(cat) + [k for k, _, _ in entries])):
        if key in seen:
            continue
        seen.add(key)
        c = cat.get(key, {})
        if key in live:
            raw, line, source = live[key][0], live[key][1], CONFIG_REL
            ex = c.get("example")
            if raw in PLACEHOLDERS:
                status = "not set"
            elif ex is not None and raw == ex:
                status = "default"
            elif not raw and not c.get("default"):
                status = "default"
            else:
                status = "set"
        else:
            raw, line, source = c.get("default", "") or "", None, CONFIG_REL
            status = "not set" if raw in PLACEHOLDERS else "default"
        secret = secret_key(key) or looks_secret(raw)
        spec = EDITABLE_CONFIG.get(key)
        if not spec and re.match(r"^RUN_WINDOW_[A-Z]+$", key):
            spec = ("window",)
        note = ""
        if secret:
            note = "A credential: shown by name only, never edited here."
        elif counts.get(key, 0) > 1:
            note = f"Set {counts[key]} times in the config (the last one counts); tidy the file by hand."
        elif not spec:
            note = next((n for p, n in CONFIG_READONLY if re.search(p, key)),
                        ("Not a documented key. " + BY_HAND) if key not in cat else BY_HAND)
        editable = bool(spec) and not secret and counts.get(key, 0) <= 1 and exists
        if spec and not exists:
            note = "No run config yet: run kit-settings setup first."
        desc = c.get("desc", "")
        if desc and not desc.endswith((".", "?", "!", "\u2026")):
            desc += "."
        if key not in live and c.get("default"):
            desc = (desc + " " if desc else "") + f"Default: {c['default']}."
        out.append(_setting(
            id=f"config|{key}", kind="config", area=config_area(key), name=key, raw=raw, secret=secret,
            source=source, line=line, description=desc, status=status, editable=editable, note=note,
            type=spec or ("text",), section="",
            default=(c["example"] if c.get("example") is not None else (c.get("default") or "")) if c else None))
    return out


# ---------------------------------------------------------------------------------------------------------------
# Setup fields in memory/context/*.md.

def parse_fields(text):
    """[{field, section, n, start, end, value, nested}] for each '- **Field:** value' item: start and end are line
    indexes (end exclusive) of the item's own line and its wrapped continuation lines."""
    lines = text.splitlines()
    out, section, counts = [], "", {}
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("#"):
            section = ln.lstrip("#").strip()
        m = FIELD_LINE.match(ln)
        if not m:
            i += 1
            continue
        j, nested, parts = i + 1, False, [m.group(2).strip()]
        while j < len(lines) and lines[j].strip() and lines[j][:1] in (" ", "\t"):
            s = lines[j].strip()
            if re.match(r"([-*+]|\d+[.)])\s", s):
                nested = True
            parts.append(s)
            j += 1
        key = (section, m.group(1))
        counts[key] = counts.get(key, 0) + 1
        out.append({"field": m.group(1), "section": section, "n": counts[key], "start": i, "end": j,
                    "first": m.group(2).strip(), "value": " ".join(p for p in parts if p), "nested": nested})
        i = j
    return out


def setup_area(fname):
    for area, names in (
            ("delivery and briefs", ("calendar", "meetings", "oneonone", "triage", "status", "letters", "worklist")),
            ("connectors and guard", ("connectors", "audit", "demands")),
            ("library and documents", ("library", "writing", "diagrams", "decisions", "knowledge", "precedent",
                                       "project-types", "onboarding", "intake")),
            ("compliance", ("compliance", "standards", "retention", "changeboard")),
            ("agents and models", ("agents",)),
            ("sharing", ("sharing", "expertise"))):
        if fname[:-3] in names:
            return area
    return "other"


SESSION = "Change it in the file in a Claude Code session, where Kit asks before editing."
# (file, field or None for every field) -> why it's read-only here.
SETUP_READONLY = {
    ("agents.md", None): "Kit's staff: who may brief whom. " + SESSION,
    ("connectors.md", None): "Which outside systems the gateway may reach; see kit-connect and connector-guard.json. " + SESSION,
    ("audit.md", "Allowed callers"): "Who may call connectors; see connectors.md. " + SESSION,
    ("audit.md", "Thresholds"): "kit-audit's thresholds. " + SESSION,
    ("retention.md", None): "Records retention: see kit-retention. " + SESSION,
    ("sharing.md", None): "What leaves this computer: see kit-publish and sharing-policy.json. " + SESSION,
    ("knowledge.md", "Sharing"): "Who may see the knowledge base. " + SESSION,
    ("training.md", "Sharing"): "What team views may show. " + SESSION,
    ("onboarding.md", "Sharing"): "What onboarding answers may share. " + SESSION,
    ("onboarding.md", "Off limits"): "What the onboarding guide must never share. " + SESSION,
    ("labs.md", "Data rule"): "A data-handling control. " + SESSION,
    ("labs.md", "Data rule check terms"): "A data-handling control used by kit-labcheck. " + SESSION,
    ("poc.md", "Data rule"): "A data-handling control. " + SESSION,
    ("letters.md", "Saved signature"): "Your signature: see kit-letter. " + SESSION,
}
SHARING_EDITABLE = {"Kit id", "Owner role", "Overload threshold", "Default project"}

# Field types beyond plain text. Paths: the health check's list plus the folder and template fields.
PATH_FIELDS = SETUP_PATH_FIELDS | {
    ("library.md", "Library root"), ("decisions.md", "Template"), ("decisions.md", "Build, buy, or partner"),
    ("demands.md", "Register"), ("estimating.md", "Estimates"), ("knowledge.md", "Knowledge base"),
    ("labs.md", "Folder"), ("labs.md", "Template"), ("labs.md", "Request template"), ("training.md", "Folder"),
    ("training.md", "Template"), ("meetings.md", "Vendor meeting template"), ("audit.md", "Audit folder"),
    ("audit.md", "Reports"), ("diagrams.md", "Lint rules"), ("sharing.md", "Shared root"), ("sharing.md", "Outbox"),
}
FIELD_TYPES = {
    ("oneonone.md", "Last 1:1"): ("date",),
    ("oneonone.md", "Look back"): ("days_text",),
    ("labs.md", "Idle after"): ("days_text",),
    ("future-tech.md", "Renewal warning"): ("days_text",),
    ("meetings.md", "Awaiting reply after"): ("days_text",),
    ("status.md", "Window"): ("days_text",),
    ("diagrams.md", "draw.io output"): ("yesno",),
    ("sharing.md", "Kit id"): ("kit_id",),
    ("sharing.md", "Overload threshold"): ("int_text", 1, 1000),
    ("writing.md", "Quality loop"): ("quality",),
    ("costs.md", "Term"): ("int_text", 1, 30),
}


def field_type(fname, field):
    if (fname, field) in FIELD_TYPES:
        return FIELD_TYPES[(fname, field)]
    if (fname, field) in PATH_FIELDS:
        return ("setup_path",)
    return ("setup_text",)


def _unset_kind(value):
    v = (value or "").strip().lower().lstrip("_*`")
    if not v or v.startswith("not set") or v.startswith("none yet"):
        return "not set"
    if v.startswith("optional"):
        return "optional"
    return ""


def setup_settings(kit):
    ctx = kit / "memory/context"
    shipped_dir = shipped_context(kit)
    shipped_names = {p.name for p in shipped_dir.glob("*.md")} if shipped_dir else set()
    out = []
    for path in sorted(ctx.glob("*.md")) if ctx.is_dir() else []:
        if path.name not in shipped_names:      # Kit's own memory notes, not a setup file
            continue
        fields = parse_fields(read_text(path))
        shipped = {(f["section"], f["field"], f["n"]): f for f in parse_fields(read_text(shipped_dir / path.name))}
        for f in fields:
            sh = shipped.get((f["section"], f["field"], f["n"]))
            kind = _unset_kind(f["value"])
            if kind == "not set":
                status = "not set"
            elif sh and " ".join(sh["value"].split()) == " ".join(f["value"].split()):
                status = "default"
            elif kind == "optional":
                status = "default"
            else:
                status = "set"
            src = sh["value"] if sh else f["value"]
            sk = _unset_kind(src)
            if sk:
                desc = re.sub(r"^[_*`]*(not set|none yet|optional)[.,:;]?\s*", "", src, flags=re.I)
                desc = sentence(desc)
            else:
                desc = "Shipped default: " + sentence(src, 180) if sh else ""
            ro = SETUP_READONLY.get((path.name, f["field"])) or SETUP_READONLY.get((path.name, None))
            if path.name == "sharing.md" and f["field"] in SHARING_EDITABLE:
                ro = None
            secret = looks_secret(f["value"])
            note = ro or ""
            if not ro and f["nested"]:
                note = "This field holds a list; edit the file. " + SESSION
            if secret:
                note = "Looks like a credential: masked, and never edited here."
            out.append(_setting(
                id=f"setup|{path.name}|{f['section']}|{f['field']}|{f['n']}", kind="setup", area=setup_area(path.name),
                name=f["field"], section=f["section"], raw=f["value"], first=f["first"], secret=secret,
                source=f"memory/context/{path.name}", line=f["start"] + 1, description=desc, status=status,
                editable=not (ro or f["nested"] or secret), note=note, type=field_type(path.name, f["field"]),
                default=(sh["value"] if sh and not looks_secret(sh["value"]) else None)))
    return out


# ---------------------------------------------------------------------------------------------------------------
# JSON configs (read-only).

JSON_NOTES = {
    "connector-guard.json": ("connectors and guard", "The connector guard's rules: change them in a session, with "
                             "approval, then check with kit-connect test and connector-guard."),
    "models.json": ("agents and models", "Model routing: kit-models (kit-models apply)."),
    "sharing-policy.json": ("sharing", "The organization's sharing policy: set by whoever owns it, not here."),
    "sharing-db.json": ("sharing", "The sharing database's connection: kit-publish; the credential is named only."),
    "retention.json": ("compliance", "Retention rules: kit-retention."),
    "drawio-styles.json": ("library and documents", "Diagram styles: edit the file (kit-drawio reads it)."),
    "diagram-lint-rules.json": ("library and documents", "Diagram lint rules: edit the file (kit-diaglint reads it)."),
    "vsdx-finish.json": ("library and documents", "Visio finishing: edit the file."),
}


def _json_lines(text):
    """{top-level key: line number} where each key first appears, for the source column."""
    out = {}
    for n, ln in enumerate(text.splitlines(), 1):
        m = re.match(r'\s*"([^"]+)"\s*:', ln)
        if m and m.group(1) not in out:
            out[m.group(1)] = n
    return out


def json_settings(kit):
    files = sorted((kit / "memory/context").glob("*.json")) if (kit / "memory/context").is_dir() else []
    files += [p for p in [kit / "models.json"] + sorted((kit / "models").glob("*.json")) if p.is_file()]
    out = []
    for path in files:
        rel = path.relative_to(kit).as_posix()
        name = "models.json" if rel.startswith("models") else path.name
        area, note = JSON_NOTES.get(name, ("other", "Edit the file."))
        text = read_text(path)
        try:
            data = json.loads(text)
        except ValueError:
            out.append(_setting(id=f"json|{rel}|", kind="json", area=area, name=path.name, raw="(not valid JSON)",
                                source=rel, line=1, description="", status="set", editable=False,
                                note="The file isn't valid JSON. " + note, type=("json",), section=""))
            continue
        lines = _json_lines(text)
        about = data.get("_about", "") if isinstance(data, dict) else ""

        def add(keypath, value, desc):
            last = keypath.split(".")[-1]
            secret = secret_key(last) or looks_secret(json.dumps(value))
            shown = value if isinstance(value, str) else json.dumps(value)
            status = "not set" if (value in ("", None, [], {}) or str(value).lower().startswith("not set")) else "set"
            out.append(_setting(id=f"json|{rel}|{keypath}", kind="json", area=area, name=f"{path.name}: {keypath}",
                                raw=shown, secret=secret, source=rel, line=lines.get(keypath.split(".")[0]),
                                description=desc, status=status, editable=False, note=note, type=("json",),
                                section=""))

        if not isinstance(data, dict):
            add("(whole file)", data, "")
            continue
        for k, v in data.items():
            if k.startswith("_"):
                continue
            if isinstance(v, dict) and v and len(v) <= 40:
                sub_about = v.get("_about", "")
                for k2, v2 in v.items():
                    if not k2.startswith("_"):
                        add(f"{k}.{k2}", v2, sentence(sub_about or about))
            else:
                add(k, v, sentence(about))
    return out


# ---------------------------------------------------------------------------------------------------------------

def _setting(**kw):
    s = {"id": "", "kind": "", "area": "other", "name": "", "section": "", "raw": "", "first": "", "secret": False,
         "source": "", "line": None, "description": "", "status": "set", "editable": False, "note": "",
         "type": ("text",), "default": None}
    s.update(kw)
    s["value"] = MASK if s["secret"] else mask_text(s["raw"])
    if s["kind"] == "setup" and s["status"] == "not set" and not s["secret"]:
        s["value"] = "not set"            # the rest of the shipped line is the description, shown beside it
    if s["secret"]:
        s["editable"] = False
    return s


def collect(kit=None):
    """Every setting, grouped by area (in AREAS order), then by source."""
    kit = kit_dir(kit)
    items = config_settings(kit) + setup_settings(kit) + json_settings(kit)
    items.append(_setting(
        id="info|permissions", kind="info", area="agents and models", name="Claude Code permission and ask rules",
        raw="managed by the installer", source="~/.claude/settings.json", status="set", editable=False,
        description="The allow, ask, and deny rules Kit adds to Claude Code (kit_setup.py activate).",
        note="Never edited here: kit_setup.py activate adds them and Claude Code asks before any change."))
    for s in items:
        s["group"], s["label"], s["help"] = group_of(s), label_of(s), help_of(s)
    order = {a: i for i, a in enumerate(AREAS)}
    kinds = {"config": 0, "setup": 1, "json": 2, "info": 3}
    return sorted(items, key=lambda s: (order.get(s["area"], 99), kinds.get(s["kind"], 9),
                                        "" if s["kind"] == "config" else s["source"]))


def public(s):
    """A setting as the page and the JSON output may show it: no raw value for a masked one."""
    d = {k: v for k, v in s.items() if k not in ("raw", "first", "default")}
    d["type"] = list(s["type"])
    d["changed"] = s["status"] == "set"
    d["default"] = None
    if s["editable"] and s.get("default") is not None and not looks_secret(s["default"]):
        d["default"] = mask_text(s["default"])
        d["can_reset"] = s["default"] != s["raw"] and _valid(s, s["default"])
    if s["editable"]:
        d["edit_value"] = s["raw"]
        d["expect"] = fingerprint(s["raw"])
        opts = options(s)
        if opts:
            d["options"] = opts
    return d


def options(s):
    t = s["type"]
    if t[0] == "onoff":
        return ["on", "off"]
    if t[0] == "yesno":
        return ["yes", "no"]
    if t[0] == "choice":
        return list(t[1])
    if t[0] == "todo":
        return [a for a in TODO_APPS if not (t[1] in ("work", "all") and a in OUTSIDE_M365)]
    return None


def _valid(s, value):
    try:
        validate(s, value)
        return True
    except Invalid:
        return False


def fingerprint(raw):
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()[:16]


def counts(items):
    c = {"set": 0, "not set": 0, "default": 0}
    for s in items:
        c[s["status"]] = c.get(s["status"], 0) + 1
    return c


# ---------------------------------------------------------------------------------------------------------------
# Text output (kit-settings show --all).

def text_report(items, only_not_set=False, area=None):
    out, cur = [], None
    c = counts(items)
    out.append(f"Kit settings: {len(items)} in all, {c['set']} set, {c['not set']} not set, {c['default']} default. "
               "Credentials show by name only; masked values never print.")
    for s in items:
        if only_not_set and s["status"] != "not set":
            continue
        if area and s["area"] != area:
            continue
        if s["area"] != cur:
            cur = s["area"]
            out += ["", cur.capitalize()]
        where = s["source"] + (f":{s['line']}" if s["line"] else " (not in the file)")
        val = s["value"] if len(s["value"]) <= 100 else s["value"][:99] + "…"
        name = s["name"] + (f" ({s['section']})" if s["section"] and s["kind"] == "setup" else "")
        flag = "editable in kit-settings ui" if s["editable"] else "read-only"
        out.append(f"  [{s['status']}] {name} = {val or '(empty)'}")
        out.append(f"      {where}; {flag}")
        if s["description"]:
            out.append(f"      {s['description']}")
        if not s["editable"] and s["note"]:
            out.append(f"      To change: {s['note']}")
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------------------------
# HTML (the dashboard's panel, and the editing page's table).

CSS = """
.kset{--ks-line:var(--line,#C9D0D6);--ks-muted:var(--muted,#566573);--ks-warn:var(--wait,#B7791F)}
.kset-tools{display:flex;flex-wrap:wrap;gap:.5rem 1rem;align-items:center;margin:0 0 .75rem}
.kset-tools input,.kset-tools select{font:inherit;padding:.25rem .4rem}
.kset table{border-collapse:collapse;width:100%;margin:0;font-family:inherit}
.kset th,.kset td{text-align:left;vertical-align:top;padding:.35rem .5rem;border-top:1px solid var(--ks-line);font-weight:400}
.kset thead th{font-weight:600;color:var(--ks-muted)}
.kset .kset-area-head th{font-weight:700;padding-top:1rem;border-top:0}
.kset .kname{font-weight:600;overflow-wrap:anywhere;min-width:11ch}
.kset .kval{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.88rem;word-break:break-word;max-width:38ch}
.kset .ksrc,.kset .kdesc,.kset .knote{color:var(--ks-muted);font-size:.85rem}
.kset .kstat{white-space:nowrap;font-weight:600}
.kset tr[data-status="not set"] .kstat{color:var(--ks-warn)}
.kset tr[data-status="not set"]{background:rgba(183,121,31,.08)}
.kset .kro{font-size:.8rem;color:var(--ks-muted)}
.kset .kedit{margin-top:.3rem;display:flex;flex-wrap:wrap;gap:.3rem}
.kset .kedit input{min-width:18rem;font:inherit}
.kset pre.kdiff{white-space:pre-wrap;font:.82rem/1.35 ui-monospace,Menlo,Consolas,monospace;background:rgba(0,0,0,.05);padding:.4rem;margin:.3rem 0}
.kset .kmsg{font-size:.88rem;margin-top:.25rem}
.kset .kmsg.bad{color:var(--kit,#C1121F)}
"""

FILTER_JS = """
(function(){var root=document.getElementById('kset');if(!root)return;
var q=root.querySelector('.kset-q'),st=root.querySelector('.kset-status'),ar=root.querySelector('.kset-area'),
n=root.querySelector('.kset-shown');
function apply(){var t=(q.value||'').toLowerCase(),s=st.value,a=ar.value,shown=0;
root.querySelectorAll('tr[data-status]').forEach(function(r){
var ok=(!s||r.getAttribute('data-status')===s||(s==='editable'&&r.getAttribute('data-editable')==='1'))&&
(!a||r.getAttribute('data-area')===a)&&(!t||r.textContent.toLowerCase().indexOf(t)>=0);r.hidden=!ok;if(ok)shown++;});
root.querySelectorAll('tbody.kset-group').forEach(function(g){var any=g.querySelector('tr[data-status]:not([hidden])');
g.hidden=!any;});if(n)n.textContent=shown+' shown';}
q.addEventListener('input',apply);st.addEventListener('change',apply);ar.addEventListener('change',apply);apply();})();
"""


def render_table(items, editing=False):
    """The filter bar and the table. editing=True adds the edit controls (the editing page only)."""
    c = counts(items)
    area_opts = "".join(f'<option value="{e(a)}">{e(a.capitalize())}</option>' for a in AREAS
                        if any(s["area"] == a for s in items))
    tools = (f'<div class="kset-tools"><label>Search <input type="search" class="kset-q" placeholder="name, value, file"></label>'
             f'<label>Show <select class="kset-status"><option value="">All ({len(items)})</option>'
             f'<option value="not set">Not set ({c["not set"]})</option><option value="set">Set ({c["set"]})</option>'
             f'<option value="default">Default ({c["default"]})</option>'
             f'<option value="editable">Editable in kit-settings ui</option></select></label>'
             f'<label>Area <select class="kset-area"><option value="">All areas</option>{area_opts}</select></label>'
             f'<span class="kset-shown"></span></div>')
    groups = []
    for a in AREAS:
        rows = [s for s in items if s["area"] == a]
        if not rows:
            continue
        body = "".join(_row(s, editing) for s in rows)
        groups.append(f'<tbody class="kset-group"><tr class="kset-area-head"><th colspan="5" scope="rowgroup">'
                      f'{e(a.capitalize())}</th></tr>{body}</tbody>')
    return (tools + '<table><thead><tr><th scope="col">Setting</th><th scope="col">Value</th>'
            '<th scope="col">Status</th><th scope="col">Source</th><th scope="col">About</th></tr></thead>'
            + "".join(groups) + "</table>")


def _row(s, editing):
    where = e(s["source"]) + (f":{s['line']}" if s["line"] else " <em>(not in the file)</em>")
    name = e(s["name"]) + (f'<div class="ksrc">{e(s["section"])}</div>' if s["section"] and s["kind"] == "setup" else "")
    about = (f'<div class="kdesc">{e(s["description"])}</div>' if s["description"] else "")
    if s["editable"]:
        about += '<div class="kro">Editable in <code>kit-settings ui</code>.</div>' if not editing else ""
    elif s["note"]:
        about += f'<div class="kro">Read-only here. {e(s["note"])}</div>'
    v = s["value"]
    val = (f'<span title="{e(v)}">{e(v[:199])}\u2026</span>' if len(v) > 200 else e(v)) if v else '<em>(empty)</em>'
    edit = ""
    if editing and s["editable"]:
        p = public(s)
        opts = p.get("options")
        if opts:
            cur = s["raw"]
            ctl = ('<select class="kin">' + "".join(
                f'<option{" selected" if o == cur else ""}>{e(o)}</option>' for o in ([cur] if cur not in opts and cur else []) + opts)
                + "</select>")
        else:
            cur = "" if s["status"] == "not set" and s["kind"] == "setup" else s["raw"]
            ctl = (f'<input class="kin" type="text" value="{e(cur)}" placeholder="new value" '
                   f'aria-label="New value for {e(s["name"])}">')
        edit = (f'<div class="kedit" data-id="{e(s["id"])}" data-expect="{e(p["expect"])}">{ctl}'
                '<button type="button" data-act="preview">Preview</button></div>'
                '<div class="kpreview"></div>')
    return (f'<tr data-status="{e(s["status"])}" data-area="{e(s["area"])}" data-editable="{1 if s["editable"] else 0}">'
            f'<th scope="row" class="kname">{name}</th><td class="kval">{val}{edit}</td>'
            f'<td class="kstat">{e(s["status"])}</td><td class="ksrc">{where}</td><td>{about}</td></tr>')


def dashboard_panel(kit=None):
    """The Settings panel for dashboard.html: static, read-only, with an inline filter and search."""
    try:
        items = collect(kit)
    except Exception as ex:  # noqa: BLE001  (the dashboard must always render)
        return f'<p class="empty">Settings couldn\'t be read: {e(str(ex)[:160])}</p>'
    c = counts(items)
    return (f'<style>{CSS}</style><details class="kset" id="kset"><summary>{len(items)} settings: '
            f'<strong>{c["not set"]} not set</strong>, {c["set"]} set, {c["default"]} default. '
            'Open to filter and search; change them with <code>kit-settings ui</code>.</summary>'
            + render_table(items) + f'</details><script>{FILTER_JS}</script>')


# ---------------------------------------------------------------------------------------------------------------
# Validation.

DATE = re.compile(r"^(\d{2})-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(\d{4})\.?$")
EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PHONE = re.compile(r"^\+?[0-9]{7,15}$")


class Invalid(ValueError):
    pass


def _num(v, lo, hi, kind, allow_empty=False):
    if v == "" and allow_empty:
        return v
    try:
        x = int(v) if kind == "int" else float(v)
        if kind == "int" and not re.fullmatch(r"\d+", v):
            raise ValueError
    except ValueError:
        raise Invalid(f"must be {'a whole number' if kind == 'int' else 'a number'} from {lo} to {hi}"
                      + (", or empty" if allow_empty else ""))
    if not lo <= x <= hi:
        raise Invalid(f"must be from {lo} to {hi}")
    return v


def validate(s, value, platform=None):
    """The value to write for setting s, or raise Invalid with a message."""
    platform = platform or sys.platform
    if not s.get("editable"):
        raise Invalid(f"{s['name']} is read-only here. {s.get('note', '')}".strip())
    if not isinstance(value, str):
        raise Invalid("the value must be text")
    value = value.strip()
    if re.search(r"[\x00-\x1f\x7f]", value):
        raise Invalid("line breaks and control characters aren't allowed")
    if looks_secret(value):
        raise Invalid("that looks like a credential; Kit never writes one into a file. Store it in the Keychain or "
                      "Credential Manager, or an environment variable, and name it instead")
    t = s["type"]
    kind = t[0]
    if s["kind"] == "config":
        if re.search(r'["$`\\\']', value):
            raise Invalid("quotes, $, backticks, and backslashes aren't allowed in the run config (the scheduled runs "
                          "read it as shell)")
        if len(value) > 300:
            raise Invalid("at most 300 characters")
    elif len(value) > 1000:
        raise Invalid("at most 1000 characters")
    if kind == "onoff" and value not in ("on", "off"):
        raise Invalid('must be "on" or "off"')
    if kind == "yesno" and value.rstrip(".") not in ("yes", "no"):
        raise Invalid('must be "yes" or "no"')
    if kind == "choice" and value not in t[1]:
        raise Invalid("must be one of: " + ", ".join(t[1]))
    if kind in ("int", "float"):
        _num(value, t[1], t[2], kind, len(t) > 3 and t[3])
    if kind == "window" and value not in ("", "off"):
        _num(value, 1, 1000, "int")
    if kind == "name" and not re.fullmatch(r"[^\W\d_][\w .'-]{0,59}", value):
        raise Invalid("must be a name: letters, spaces, hyphens, and apostrophes, up to 60 characters")
    if kind == "ident" and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,60}", value):
        raise Invalid("must be a field name: letters, digits, and underscores")
    if kind == "email" and not EMAIL.match(value):
        raise Invalid("must be an email address")
    if kind == "phone_or_email" and value and not (EMAIL.match(value) or PHONE.match(value.replace(" ", ""))):
        raise Invalid("must be a phone number like +15551234567 or an email address")
    if kind == "days":
        parts = value.split()
        if (not parts and not t[1]) or any(p not in "1234567" or len(p) != 1 for p in parts) or len(set(parts)) != len(parts):
            raise Invalid("must be weekday numbers 1 (Monday) to 7 (Sunday), separated by spaces"
                          + ("" if t[1] else ", at least one"))
    if kind == "waits":
        if not value.split() or any(not re.fullmatch(r"\d{1,4}", p) or int(p) > 3600 for p in value.split()):
            raise Invalid("must be seconds (0 to 3600) separated by spaces")
    if kind == "modes":
        if not value.split() or any(p not in RUN_MODES for p in value.split()):
            raise Invalid("must be run kinds separated by spaces, from: " + ", ".join(RUN_MODES))
    if kind == "names" and value and not all(re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", p) for p in value.split()):
        raise Invalid("must be connector names separated by spaces")
    if kind == "scope" and not re.fullmatch(r"[\w ,&.()/-]{1,200}", value):
        raise Invalid('must be "all", "mine", or portfolio and program names separated by commas')
    if kind == "path" and value and not (value.startswith("~/") or os.path.isabs(value) or re.match(r"^[A-Za-z]:[\\/]", value)):
        raise Invalid("must be a full path, or one starting with ~/ (or empty)")
    if kind == "channels":
        side = t[1]
        chans = value.split()
        if not chans:
            raise Invalid("name at least one channel: " + ", ".join(CHANNELS))
        for ch in chans:
            if ch not in CHANNELS:
                raise Invalid(f"unknown channel {ch!r}; choose from: " + ", ".join(CHANNELS))
            if ch == "imessage" and platform != "darwin":
                raise Invalid("imessage works on macOS only")
            if ch == "sms" and not platform.startswith("win"):
                raise Invalid("sms works on Windows only")
        if side in ("work", "all") and set(chans) & OUTSIDE_M365:
            raise Invalid(f"{', '.join(sorted(set(chans) & OUTSIDE_M365))} runs outside Microsoft 365, so it's not used "
                          "for work items. Set DELIVERY_PERSONAL instead, or use kit-settings delivery ... --force")
        value = " ".join(dict.fromkeys(chans))
    if kind == "todo":
        if value not in TODO_APPS:
            raise Invalid("must be apple or outlook")
        if value == "apple" and platform != "darwin":
            raise Invalid("Apple Reminders works on macOS only")
        if t[1] in ("work", "all") and value in OUTSIDE_M365:
            raise Invalid("Apple Reminders syncs through iCloud, outside Microsoft 365, so it's not used for work to-dos. "
                          "Set TODOS_PERSONAL instead, or use kit-settings todos ... --force")
    if s["kind"] == "setup":
        value = _validate_setup(s, value, kind, t)
    return value


def _validate_setup(s, value, kind, t):
    if not value:
        raise Invalid('can\'t be empty; write "not set." to clear it')
    if re.match(r"^\s*(#|- |\* |>)", value) or "**" in value:
        raise Invalid("can't start a new heading or list item, or contain **")
    if SETUP_UNSET.match(value) and kind not in ("date", "yesno"):
        return value                       # "not set." / "optional. ..." / "none." clear any field
    if kind == "setup_path":
        m = re.match(r"`([^`]+)`", value)
        if not m:
            raise Invalid("a path must start with a backticked path, for example `~/Documents/Library` "
                          '(or write "not set." to clear it)')
        if re.match(r"\s*<[^>]+>", m.group(1)):
            raise Invalid("write the real path, not a <placeholder>")
    if kind == "date":
        m = DATE.match(value)
        if not m:
            raise Invalid("must be a date as DD-Mmm-YYYY, for example 02-Oct-2026")
        try:
            dt.date(int(m.group(3)), kc.MONTHS.index(m.group(2)) + 1, int(m.group(1)))
        except ValueError:
            raise Invalid("that date doesn't exist")
    if kind == "days_text":
        m = re.match(r"^(\d+)\b", value)
        if not m or not 1 <= int(m.group(1)) <= 3650:
            raise Invalid("must start with a number of days from 1 to 3650, for example \"14 days\"")
    if kind == "int_text":
        m = re.match(r"^(\d+)\b", value)
        if not m or not t[1] <= int(m.group(1)) <= t[2]:
            raise Invalid(f"must start with a whole number from {t[1]} to {t[2]}")
    if kind == "kit_id" and not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,39}\.?", value):
        raise Invalid("must be 3 to 40 lowercase letters, digits, and hyphens")
    if kind == "quality" and not re.fullmatch(r"min \d{1,3}, days \d{1,4}\.?", value):
        raise Invalid('must read "min N, days N", for example "min 3, days 90"')
    return value


# ---------------------------------------------------------------------------------------------------------------
# Editing: plan (a diff to preview), then apply (backup, one-line write, commit, log, dashboard rebuild).

class Refused(Exception):
    """A request the page must refuse (read-only, unknown, or changed since it was shown)."""


def find(items, sid):
    for s in items:
        if s["id"] == sid:
            return s
    return None


def _newline(text):
    return "\r\n" if "\r\n" in text else "\n"


def plan_edit(kit, sid, value, expect=None, platform=None):
    """(setting, path, old text, new text, value, diff) for an edit; raises Refused or Invalid."""
    kit = kit_dir(kit)
    items = collect(kit)
    s = find(items, sid)
    if not s:
        raise Refused("no such setting")
    if not s["editable"]:
        raise Refused(f"{s['name']} is read-only here. {s['note']}".strip())
    if expect is not None and expect != fingerprint(s["raw"]):
        raise Refused(f"{s['name']} changed since the page was loaded; reload and try again")
    value = validate(s, value, platform)
    path = kit / s["source"]
    data = path.read_bytes() if path.exists() else b""
    old = data.decode("utf-8")
    lines = old.splitlines(keepends=True)
    if s["kind"] == "config":
        new_line = f'{s["name"]}="{value}"'
        idx = [i for i, ln in enumerate(lines) if (CONFIG_LINE.match(ln.rstrip("\r\n")) or [None, None])[1] == s["name"]]
        if len(idx) > 1:
            raise Refused(f"{s['name']} is in the config more than once; tidy the file by hand")
        if idx:
            i = idx[0]
            end = lines[i][len(lines[i].rstrip("\r\n")):]
            lines[i] = new_line + end
        else:
            nl = _newline(old)
            if lines and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += nl
            lines.append(new_line + nl)
    else:
        f = next((f for f in parse_fields(old) if f"setup|{path.name}|{f['section']}|{f['field']}|{f['n']}" == sid), None)
        if not f:
            raise Refused("the field moved; reload and try again")
        if f["nested"]:
            raise Refused("this field holds a list; edit the file")
        last = lines[f["end"] - 1]
        end = last[len(last.rstrip("\r\n")):]
        lines[f["start"]:f["end"]] = [f"- **{f['field']}:** {value}" + end]
    new = "".join(lines)
    if new == old:
        raise Invalid("that's the value it already has")
    diff = "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                        f"a/{s['source']}", f"b/{s['source']}", n=1))
    return s, path, old, new, value, mask_text(diff)


def log_path(kit):
    return kit_dir(kit) / ".install/logs/settings-ui.log"


def log_edit(kit, s, old_value, new_value, outcome):
    shown = lambda v: MASK if (s["secret"] or looks_secret(v)) else v  # noqa: E731
    line = (f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {s['source']} {s['name']}"
            + (f" ({s['section']})" if s.get("section") else "")
            + f": {json.dumps(shown(old_value))} -> {json.dumps(shown(new_value))}; {outcome}")
    print("kit-settings ui: " + line, file=sys.stderr)
    p = log_path(kit)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def backup(kit, path):
    kit = kit_dir(kit)
    d = kit / ".install/backups/settings"
    d.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(d, 0o700)
    rel = path.relative_to(kit).as_posix().replace("/", "__")
    dest = d / f"{dt.datetime.now():%Y%m%d-%H%M%S-%f}-{rel}"
    if path.exists():
        shutil.copy2(str(path), str(dest))
    else:
        dest.write_bytes(b"")
    return dest


def git_commit(kit, path, message):
    """(committed?, message)."""
    kit = kit_dir(kit)
    if not (kit / ".git").exists():
        return False, "Kit's folder isn't a git repo, so there's no commit"
    rel = path.relative_to(kit).as_posix()
    try:
        ign = subprocess.run(["git", "-C", str(kit), "check-ignore", "-q", "--", rel], capture_output=True, timeout=30)
        if ign.returncode == 0:
            return False, f"{rel} isn't in Kit's history (the private repo leaves it out), so there's no commit"
        add = subprocess.run(["git", "-C", str(kit), "add", "--", rel], capture_output=True, text=True, timeout=60)
        if add.returncode:
            return False, "git commit failed (at git add): " + (add.stderr.strip().splitlines() or ["?"])[-1]
        r = subprocess.run(["git", "-C", str(kit), "commit", "-q", "-m", message, "--", rel],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as ex:
        return False, f"git didn't run: {ex}"
    if r.returncode:
        return False, "git commit failed: " + ((r.stderr or r.stdout).strip().splitlines() or ["?"])[-1]
    return True, "committed to Kit's private repo"


def rebuild_dashboard(kit):
    """Start a dashboard rebuild in the background (it runs the health check, so it can take a while)."""
    script = HERE / "dashboard.py"
    if not script.exists():
        return False
    try:
        kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
        if os.name == "nt":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            kw["start_new_session"] = True
        subprocess.Popen([sys.executable, str(script)], **kw)
        return True
    except OSError:
        return False


def apply_edit(kit, sid, value, expect=None, platform=None, rebuild=True):
    """Write one setting. Returns a dict: ok, message, backup, committed, diff."""
    kit = kit_dir(kit)
    s, path, old, new, value, diff = plan_edit(kit, sid, value, expect, platform)
    bak = backup(kit, path)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    tmp = path.with_name(path.name + ".kit-settings.tmp")
    tmp.write_bytes(new.encode("utf-8"))
    if os.name != "nt":
        os.chmod(tmp, mode)
    os.replace(str(tmp), str(path))
    where = f"{s['source']}" + (f" ({s['section']})" if s["section"] else "")
    committed, cmsg = git_commit(kit, path, f"Settings: {s['name']} in {where}")
    old_value = s["raw"]
    log_edit(kit, s, old_value, value, cmsg)
    started = rebuild_dashboard(kit) if rebuild else False
    msg = (f"Saved {s['name']}. A copy of the old file is in {bak.relative_to(kit).as_posix()}. "
           + (cmsg[0].upper() + cmsg[1:] + "." if committed else f"The change is saved, but {cmsg}.")
           + (" The dashboard is being rebuilt." if started else ""))
    return {"ok": True, "message": msg, "backup": str(bak), "committed": committed, "diff": diff}

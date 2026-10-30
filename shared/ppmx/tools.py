"""The tools, shared by both servers: reads (get_, list_) and, unless the server is read-only
(PPMX_WRITES=off), creates and updates (create_, update_, set_). Each takes a Context (the client, the
settings, the code tables, the caller's token) and its arguments, and returns a dict ready for JSON.

Read tool names start with a read word and write tool names with a write word, so Kit's connector guard
lets Kit's agents read and stops them writing: a change comes only from a person's own session, where
the client asks before each one. Lists come back a page at a time: total, offset, limit, sort, and
next_offset while there are more. PPM Express's API has no delete, and neither do these tools.
"""
import datetime
import json
import re

from . import codes as codes_mod
from .client import PARAMS, UUID, records

# Which attribute holds what, by the names PPM Express is expected to use. PROVISIONAL: check them
# against your tenant (get_fields) and correct them here. The first name a record has wins.
FIELDS = {
    "name": ["Name", "Title"],
    "status": ["OverallStatus", "Status", "State"],
    "manager": ["Manager", "ProjectManager", "Owner"],
    "start": ["StartDate", "Start"],
    "finish": ["FinishDate", "Finish", "EndDate"],
    "due": ["DueDate", "FinishDate", "Finish", "Date"],
    "date": ["Date", "DueDate", "FinishDate"],
    "portfolio": ["Portfolios", "Portfolio"],
    "program": ["Programs", "Program"],
    "assignee": ["AssignedTo", "Assignee", "Resource", "Owner"],
    "progress": ["Progress", "PercentComplete"],
    "stage": ["Stage", "IdeaStage"],
    "type": ["Type", "KeyDateType"],
    "email": ["Email"],
}
# What a list shows for each record, besides its id.
SUMMARY = {
    "portfolios": ["name", "manager", "status"],
    "programs": ["name", "manager", "portfolio", "status"],
    "projects": ["name", "status", "manager", "start", "finish", "portfolio", "program", "progress"],
    "tasks": ["name", "status", "assignee", "start", "due", "progress"],
    "key_dates": ["name", "type", "date", "status"],
    "ideas": ["name", "stage", "status"],
    "challenges": ["name", "status"],
    "resources": ["name", "email"],
}
ENTITIES = ["Project", "Program", "Portfolio", "Task", "KeyDate", "Idea", "Challenge", "Resource"]
# The kind of record each endpoint holds, for code tables that apply to one kind ("KeyDate.Type").
ENTITY_OF = {"portfolios": "Portfolio", "portfolio": "Portfolio", "programs": "Program", "program": "Program",
             "projects": "Project", "project": "Project", "tasks": "Task", "task": "Task", "tasks_bulk": "Task",
             "key_dates": "KeyDate", "key_date": "KeyDate", "ideas": "Idea", "idea": "Idea", "idea_stage": "Idea",
             "challenges": "Challenge", "challenge": "Challenge", "resources": "Resource", "resource": "Resource"}
DATE_ROLES = ("start", "finish", "due", "date")
DONE_WORDS = ("complete", "done", "closed", "finished", "cancel")
# Fields that name people or other records take a list of {"search": a name or email} or {"id": an ID}
# (PPM Express's format); plain text is turned into that. Tags take "#tag" text.
PEOPLE = {"Manager", "Managers", "ProjectManager", "Owner", "Owners", "AssignedTo", "Sponsor", "Sponsors",
          "Resource", "Resources"}
LINKS = {"Portfolios", "Programs", "Predecessor", "Predecessors"}
FIELD_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_ .-]{0,79}$")
# Record kinds the general create_record and update_record tools take: (list endpoint, item endpoint,
# entity).
RECORDS = {"portfolio": ("portfolios", "portfolio", "Portfolio"), "program": ("programs", "program", "Program"),
           "resource": ("resources", "resource", "Resource"), "challenge": ("challenges", "challenge", "Challenge")}
READ_ONLY = "This PPM Express server is read-only (PPMX_WRITES is off), so it makes no changes."


class ToolError(Exception):
    """A problem with a tool call, safe to show to the caller."""


class Context:
    def __init__(self, client, settings, tables, token, hint=""):
        self.client, self.settings, self.tables = client, settings, tables
        self.token, self.hint = token, hint

    @property
    def today(self):
        return self.settings.today or datetime.date.today()

    def fetch(self, name, params=None, **parts):
        if not self.token:
            raise ToolError(self.hint or "no personal access token")
        return self.client.get(self.token, name, params, **parts)

    def rows(self, name, params=None, **parts):
        entity = ENTITY_OF.get(name)
        return [codes_mod.decode(r, self.tables, entity) for r in records(self.fetch(name, params, **parts))]

    def write(self, method, name, body, params=None, **parts):
        """POST or PATCH to PPM Express; refused when the server is read-only."""
        if not self.settings.writes:
            raise ToolError(READ_ONLY)
        if not self.token:
            raise ToolError(self.hint or "no personal access token")
        return self.client.send(self.token, method, name, body, params, **parts)


# ---------------------------------------------------------------- helpers

def pick(row, role):
    """(attribute name, value) for a role, or (None, None)."""
    for key in FIELDS.get(role, [role]):
        if key in row and row[key] not in (None, "", []):
            return key, row[key]
    return None, None


def text_of(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(text_of(value.get(k)) for k in ("name", "Name", "title", "email", "id") if value.get(k))
    if isinstance(value, (list, tuple)):
        return " ".join(text_of(v) for v in value)
    return str(value)


def matches(row, role, wanted):
    if not wanted:
        return True
    return wanted.lower() in text_of(pick(row, role)[1]).lower()


def day(value):
    try:
        return datetime.date.fromisoformat(text_of(value)[:10])
    except ValueError:
        return None


def role_day(row, role):
    return day(pick(row, role)[1])


def is_done(row):
    """True when the status or the progress says finished (Done, Completed, Canceled); False when they
    say otherwise; None when it can't be told (only codes with no label)."""
    told = False
    for role in ("status", "progress"):
        key, value = pick(row, role)
        if value is None:
            continue
        if isinstance(value, bool):
            if value:
                return True
            told = True
        elif isinstance(value, (int, float)):
            if key == "PercentComplete":
                if value >= 100:
                    return True
                told = True
            # otherwise a code the tables have no label for: it tells nothing
        elif text_of(value):
            if any(w in text_of(value).lower() for w in DONE_WORDS):
                return True
            told = True
    if row.get("IsCompleted") is True:
        return True
    if isinstance(row.get("IsCompleted"), bool):
        told = True
    return False if told else None


def open_rows(rows):
    """(rows not known to be finished, how many of them couldn't be told)."""
    states = [(r, is_done(r)) for r in rows]
    return [r for r, s in states if s is not True], sum(1 for _, s in states if s is None)


def summarize(row, roles, extra):
    out = {"id": row.get("id")}
    for role in roles:
        key, value = pick(row, role)
        if key:
            out[key] = value
    for key in extra or []:
        if key in row:
            out[key] = row[key]
    if isinstance(row.get("codes"), dict):
        kept = {k: v for k, v in row["codes"].items() if k in out}
        if kept:
            out["codes"] = kept
    return out


def sort_value(row, role):
    value = pick(row, role)[1]
    if value is None:
        return None
    if role in DATE_ROLES:
        d = day(value)
        if d:
            return d.isoformat()
    return text_of(value).lower()


def page(rows, args, ctx, default_sort, roles):
    total = len(rows)
    limit = min(int(args.get("limit") or ctx.settings.page_size), ctx.settings.max_rows)
    offset = min(int(args.get("offset") or 0), total)
    role = args.get("sort") or default_sort
    desc = bool(args.get("descending"))
    keyed = [(sort_value(r, role), r) for r in rows]
    ordered = [r for _, r in sorted([k for k in keyed if k[0] is not None], key=lambda k: k[0], reverse=desc)]
    ordered += [r for v, r in keyed if v is None]     # records without the value come last either way
    out = {"total": total, "offset": offset, "limit": limit, "sort": f"{role} {'desc' if desc else 'asc'}",
           "items": [summarize(r, roles, args.get("fields")) for r in ordered[offset:offset + limit]]}
    if offset + limit < total:
        out["next_offset"] = offset + limit
    return out


# ---------------------------------------------------------------- the tools

def t_current_user(ctx, args):
    rec = (records(ctx.fetch("me")) or [{}])[0]
    token = rec.get("token") if isinstance(rec.get("token"), dict) else {}
    out = {k: rec[k] for k in ("id", "name", "displayName", "email", "logonAccount") if rec.get(k) is not None}
    out["token"] = {k: token[k] for k in ("name", "expirationDate", "scopes") if token.get(k) is not None}
    return out


def t_portfolios(ctx, args):
    rows = [r for r in ctx.rows("portfolios")
            if matches(r, "name", args.get("name_contains")) and matches(r, "manager", args.get("manager"))]
    return page(rows, args, ctx, "name", SUMMARY["portfolios"])


def t_programs(ctx, args):
    rows = [r for r in ctx.rows("programs")
            if matches(r, "name", args.get("name_contains")) and matches(r, "portfolio", args.get("portfolio"))
            and matches(r, "manager", args.get("manager"))]
    return page(rows, args, ctx, "name", SUMMARY["programs"])


def t_projects(ctx, args):
    rows = [r for r in ctx.rows("projects")
            if all(matches(r, role, args.get(arg)) for arg, role in (
                ("name_contains", "name"), ("portfolio", "portfolio"), ("program", "program"),
                ("manager", "manager"), ("status", "status")))]
    return page(rows, args, ctx, "name", SUMMARY["projects"])


def t_project(ctx, args):
    pid = args["project_id"]
    found = ctx.rows("project", id=pid)
    if not found:
        raise ToolError("PPM Express returned no project for that ID")
    out = {"project": found[0]}
    include = args.get("include") or []
    each = {"limit": args.get("limit_each") or ctx.settings.page_size}
    if "key_dates" in include:
        out["key_dates"] = page(ctx.rows("key_dates", id=pid), each, ctx, "date", SUMMARY["key_dates"])
    if "tasks" in include:
        tasks = ctx.rows("tasks", id=pid)
        if args.get("open_tasks_only", True):
            tasks, unknown = open_rows(tasks)
            if unknown:
                out["notes"] = [f"{unknown} task(s) kept as open: their status is a code with no label yet"]
        out["tasks"] = page(tasks, each, ctx, "due", SUMMARY["tasks"])
    return out


def t_tasks(ctx, args):
    rows = [r for r in ctx.rows("tasks", id=args["project_id"])
            if matches(r, "name", args.get("name_contains")) and matches(r, "assignee", args.get("assignee"))]
    notes = []
    if args.get("open_only") or args.get("overdue_only"):
        rows, unknown = open_rows(rows)
        if unknown:
            notes.append(f"{unknown} task(s) kept as open: their status is a code with no label yet")
    if args.get("overdue_only"):
        rows = [r for r in rows if role_day(r, "due") and role_day(r, "due") < ctx.today]
    if args.get("due_within_days") is not None:
        end = ctx.today + datetime.timedelta(days=args["due_within_days"])
        rows = [r for r in rows if role_day(r, "due") and ctx.today <= role_day(r, "due") <= end]
    out = page(rows, args, ctx, "due", SUMMARY["tasks"])
    if notes:
        out["notes"] = notes
    return out


def t_key_dates(ctx, args):
    rows = ctx.rows("key_dates", id=args["project_id"])
    if args.get("overdue_only"):
        rows = [r for r in open_rows(rows)[0] if role_day(r, "date") and role_day(r, "date") < ctx.today]
    if args.get("upcoming_days") is not None:
        end = ctx.today + datetime.timedelta(days=args["upcoming_days"])
        rows = [r for r in rows if role_day(r, "date") and ctx.today <= role_day(r, "date") <= end]
    return page(rows, args, ctx, "date", SUMMARY["key_dates"])


def t_ideas(ctx, args):
    params = {PARAMS["challenge"]: args["challenge_id"]} if args.get("challenge_id") else None
    rows = [r for r in ctx.rows("ideas", params)
            if matches(r, "name", args.get("name_contains")) and matches(r, "stage", args.get("stage"))]
    return page(rows, args, ctx, "name", SUMMARY["ideas"])


def t_challenges(ctx, args):
    rows = [r for r in ctx.rows("challenges") if matches(r, "name", args.get("name_contains"))]
    return page(rows, args, ctx, "name", SUMMARY["challenges"])


def t_resources(ctx, args):
    rows = [r for r in ctx.rows("resources") if matches(r, "name", args.get("name_contains"))]
    return page(rows, args, ctx, "name", SUMMARY["resources"])


def t_fields(ctx, args):
    value = ctx.fetch("fields", entity=args["entity"])
    items = value.get("data") if isinstance(value, dict) else value
    fields = []
    for f in items if isinstance(items, list) else []:
        if isinstance(f, dict):
            f = dict(f.get("attributes") or {}, **{k: v for k, v in f.items() if k != "attributes"})
            fields.append({k: f.get(k) for k in ("key", "label", "type", "isMultiChoice", "isReadonly", "settings")
                           if f.get(k) is not None})
    return {"entity": args["entity"], "fields": fields}




# ---------------------------------------------------------------- writes

def _ref(value):
    """A reference to a person or record: its ID, or text PPM Express searches for (a name or email)."""
    if isinstance(value, str):
        text = value.strip()
        return {"id": text} if UUID.match(text) else {"search": text}
    return value


def attributes(ctx, entity, fields, name=None):
    """The fields to send, in PPM Express's terms: coded labels as their numbers, people and linked
    records as references, tags with their #. A name given on its own wins over one in fields."""
    out = {}
    for key, value in (fields or {}).items():
        if key in PEOPLE or key in LINKS:
            items = value if isinstance(value, list) else [value]
            value = [_ref(v) for v in items if v not in (None, "")]
        elif key == "Group" and isinstance(value, str):
            value = _ref(value)
        elif key == "Tags":
            items = value if isinstance(value, list) else str(value).split(",")
            value = ["#" + str(t).strip().lstrip("#") for t in items if str(t).strip().lstrip("#")]
        else:
            value = codes_mod.encode(key, value, ctx.tables, entity)
        out[key] = value
    if name is not None:
        out["Name"] = name
    return out


def changes(ctx, entity, fields):
    upd = attributes(ctx, entity, fields)
    if not upd:
        raise ToolError("fields must name at least one field to change")
    return upd


def written(ctx, action, kind, value, sent, entity, known_id=None):
    """What a write tool returns: what happened, to which record, the field names sent (never their
    values, which the audit log leaves out too), and the record as PPM Express now has it."""
    recs = records(value) if value is not None else []
    rec = codes_mod.decode(recs[0], ctx.tables, entity) if recs else {}
    out = {"result": action, "kind": kind, "id": rec.get("id") or known_id, "fields": sorted(sent)}
    if rec:
        out["record"] = rec
    return out


def t_create_project(ctx, args):
    attrs = attributes(ctx, "Project", args.get("fields"), args["name"])
    return written(ctx, "created", "project", ctx.write("POST", "projects", {"attributes": attrs}), attrs, "Project")


def t_update_project(ctx, args):
    upd = changes(ctx, "Project", args["fields"])
    value = ctx.write("PATCH", "project", {"updates": upd}, id=args["project_id"])
    return written(ctx, "updated", "project", value, upd, "Project", args["project_id"])


def t_create_task(ctx, args):
    attrs = attributes(ctx, "Task", args.get("fields"), args["name"])
    if args.get("parent_task_id"):
        value = ctx.write("POST", "tasks_bulk", [{"ParentID": args["parent_task_id"], "attributes": attrs}],
                          id=args["project_id"])
    else:
        value = ctx.write("POST", "tasks", {"attributes": attrs}, id=args["project_id"])
    return written(ctx, "created", "task", value, attrs, "Task")


def t_update_task(ctx, args):
    upd = changes(ctx, "Task", args["fields"])
    value = ctx.write("PATCH", "task", {"updates": upd}, id=args["project_id"], task_id=args["task_id"])
    return written(ctx, "updated", "task", value, upd, "Task", args["task_id"])


def t_create_key_date(ctx, args):
    fields = dict(args.get("fields") or {}, Date=args["date"])
    if args.get("type") is not None:
        fields["Type"] = args["type"]
    attrs = attributes(ctx, "KeyDate", fields, args["name"])
    value = ctx.write("POST", "key_dates", {"attributes": attrs}, id=args["project_id"])
    return written(ctx, "created", "key_date", value, attrs, "KeyDate")


def t_update_key_date(ctx, args):
    upd = changes(ctx, "KeyDate", args["fields"])
    value = ctx.write("PATCH", "key_date", {"updates": upd}, id=args["project_id"], key_date_id=args["key_date_id"])
    return written(ctx, "updated", "key_date", value, upd, "KeyDate", args["key_date_id"])


def t_create_idea(ctx, args):
    attrs = attributes(ctx, "Idea", args.get("fields"), args["name"])
    params = {PARAMS["challenge"]: args["challenge_id"]} if args.get("challenge_id") else None
    return written(ctx, "created", "idea", ctx.write("POST", "ideas", {"attributes": attrs}, params), attrs, "Idea")


def t_update_idea(ctx, args):
    upd = changes(ctx, "Idea", args["fields"])
    value = ctx.write("PATCH", "idea", {"updates": upd}, id=args["idea_id"])
    return written(ctx, "updated", "idea", value, upd, "Idea", args["idea_id"])


def t_idea_stage(ctx, args):
    stage = codes_mod.encode("Stage", str(args["stage"]), ctx.tables, "Idea")
    if isinstance(stage, bool) or not isinstance(stage, int):
        table = codes_mod.table_for(ctx.tables, "Stage", "Idea") or {}
        raise ToolError("stage must be one of: " + ", ".join(table.values()) + " (or its number)")
    value = ctx.write("POST", "idea_stage", {"Stage": stage}, id=args["idea_id"])
    return written(ctx, "updated", "idea", value, ["Stage"], "Idea", args["idea_id"])


def t_create_record(ctx, args):
    plural, _, entity = RECORDS[args["kind"]]
    attrs = attributes(ctx, entity, args.get("fields"), args["name"])
    return written(ctx, "created", args["kind"], ctx.write("POST", plural, {"attributes": attrs}), attrs, entity)


def t_update_record(ctx, args):
    _, single, entity = RECORDS[args["kind"]]
    upd = changes(ctx, entity, args["fields"])
    value = ctx.write("PATCH", single, {"updates": upd}, id=args["record_id"])
    return written(ctx, "updated", args["kind"], value, upd, entity, args["record_id"])


# ---------------------------------------------------------------- definitions

def _paging(sorts):
    return {
        "limit": {"type": "integer", "minimum": 1, "maximum": 5000,
                  "description": "Rows to return (default 25; the server caps it, 200 unless set otherwise)."},
        "offset": {"type": "integer", "minimum": 0, "description": "Rows to skip: use next_offset for the next page."},
        "sort": {"type": "string", "enum": sorts, "description": "What to sort by."},
        "descending": {"type": "boolean", "description": "Sort high to low (latest dates first)."},
        "fields": {"type": "array", "maxItems": 20, "items": {"type": "string", "maxLength": 80},
                   "description": "More attribute names to include in each row (get_fields lists them)."},
    }


def _text(desc, longest=200):
    return {"type": "string", "maxLength": longest, "description": desc}


def _id(desc):
    return {"type": "string", "format": "uuid", "maxLength": 36, "description": desc}


ID = _id("The project's PPM Express ID.")
NAME = _text("The name (or title).", 255)
CHANGES = ("The fields by their keys (get_fields lists a tenant's keys, custom fields included), for example "
           '{"Description": "...", "StartDate": "2026-11-02", "Status": "At Risk", "Manager": "alex@example.com"}. '
           "Coded fields (Status, Progress, Priority, Risk, and the like) take their label or number; people "
           "(Manager, AssignedTo) take a name, an email, or an ID; Portfolios and Programs take names or IDs; "
           "Tags take text. Dates are YYYY-MM-DD.")
CONFIRM = " Changes PPM Express: say what you'll do and get the user's go-ahead first."


def _fields(required):
    return {"type": "object", "maxProperties": 50, "minProperties": 1 if required else 0,
            "description": CHANGES if required else "Other fields to set. " + CHANGES}


TOOLS = [
    {"name": "get_current_user", "title": "PPM Express: who the token belongs to", "kind": "read",
     "description": "Who the personal access token belongs to in PPM Express, and the token's name, scopes, "
                    "and expiry date. Use it first to check the connection, and to see whether the token can "
                    "write.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
     "handler": t_current_user},
    {"name": "list_portfolios", "title": "PPM Express: portfolios", "kind": "read",
     "description": "Portfolios the token can see, filtered by name or manager, a page at a time.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "name_contains": _text("Part of the portfolio's name."), "manager": _text("Part of the manager's name."),
         **_paging(["name", "manager", "status"])}},
     "handler": t_portfolios},
    {"name": "list_programs", "title": "PPM Express: programs", "kind": "read",
     "description": "Programs the token can see, filtered by name, portfolio, or manager.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "name_contains": _text("Part of the program's name."), "portfolio": _text("Part of a portfolio's name."),
         "manager": _text("Part of the manager's name."), **_paging(["name", "manager", "status"])}},
     "handler": t_programs},
    {"name": "list_projects", "title": "PPM Express: projects", "kind": "read",
     "description": "Projects the token can see, filtered by name, portfolio, program, manager, or status, "
                    "sorted and a page at a time. Coded fields (status, progress) come as labels, with the "
                    "numbers under codes.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "name_contains": _text("Part of the project's name."), "portfolio": _text("Part of a portfolio's name."),
         "program": _text("Part of a program's name."), "manager": _text("Part of the manager's name."),
         "status": _text("A status label (or code)."),
         **_paging(["name", "status", "manager", "start", "finish"])}},
     "handler": t_projects},
    {"name": "get_project", "title": "PPM Express: one project", "kind": "read",
     "description": "One project's details, optionally with its key dates and its tasks (open ones unless "
                    "open_tasks_only is false).",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["project_id"], "properties": {
         "project_id": ID,
         "include": {"type": "array", "maxItems": 2, "items": {"type": "string", "enum": ["key_dates", "tasks"]},
                     "description": "Also return the project's key dates, tasks, or both."},
         "open_tasks_only": {"type": "boolean", "description": "Only tasks not finished (default true)."},
         "limit_each": {"type": "integer", "minimum": 1, "maximum": 5000,
                        "description": "Rows of key dates and of tasks (default 25)."}}},
     "handler": t_project},
    {"name": "list_tasks", "title": "PPM Express: a project's tasks", "kind": "read",
     "description": "A project's tasks, filtered by name, assignee, open, overdue, or due within some days. "
                    "Tasks synced from Jira or Azure DevOps are included (read-only in PPM Express).",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["project_id"], "properties": {
         "project_id": ID, "name_contains": _text("Part of the task's name."),
         "assignee": _text("Part of the assignee's name."),
         "open_only": {"type": "boolean", "description": "Leave out finished tasks."},
         "overdue_only": {"type": "boolean", "description": "Only unfinished tasks past their due date."},
         "due_within_days": {"type": "integer", "minimum": 0, "maximum": 3650,
                             "description": "Only tasks due between today and this many days from now."},
         **_paging(["due", "start", "name", "status", "assignee"])}},
     "handler": t_tasks},
    {"name": "list_key_dates", "title": "PPM Express: a project's key dates", "kind": "read",
     "description": "A project's key dates (key dates, milestones, releases), filtered to upcoming or overdue "
                    "ones.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["project_id"], "properties": {
         "project_id": ID,
         "upcoming_days": {"type": "integer", "minimum": 0, "maximum": 3650,
                           "description": "Only key dates between today and this many days from now."},
         "overdue_only": {"type": "boolean", "description": "Only key dates in the past that aren't finished."},
         **_paging(["date", "name", "status", "type"])}},
     "handler": t_key_dates},
    {"name": "list_ideas", "title": "PPM Express: ideas", "kind": "read",
     "description": "Ideas (the demand pipeline), optionally for one challenge, filtered by stage or name.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "challenge_id": _id("Only ideas for this challenge (its PPM Express ID)."),
         "stage": _text("A stage label (or code)."), "name_contains": _text("Part of the idea's name."),
         **_paging(["name", "stage", "status"])}},
     "handler": t_ideas},
    {"name": "list_challenges", "title": "PPM Express: challenges", "kind": "read",
     "description": "Challenges, the campaigns ideas are collected under, filtered by name.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "name_contains": _text("Part of the challenge's name."), **_paging(["name", "status"])}},
     "handler": t_challenges},
    {"name": "list_resources", "title": "PPM Express: resources", "kind": "read",
     "description": "Resources (people and roles), filtered by name.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "name_contains": _text("Part of the resource's name."), **_paging(["name", "email"])}},
     "handler": t_resources},
    {"name": "get_fields", "title": "PPM Express: an entity's fields", "kind": "read",
     "description": "The fields of one kind of record (key, label, type, read-only, options), custom fields "
                    "included. Use it to learn which keys to read and to send in a create or update.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["entity"], "properties": {
         "entity": {"type": "string", "enum": ENTITIES, "description": "Which kind of record."}}},
     "handler": t_fields},
    # ---- writes
    {"name": "create_project", "title": "PPM Express: create a project", "kind": "create",
     "description": "Create a project, with any fields." + CONFIRM,
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["name"], "properties": {
         "name": NAME, "fields": _fields(False)}},
     "handler": t_create_project},
    {"name": "update_project", "title": "PPM Express: update a project", "kind": "update",
     "description": "Change fields of a project (only the ones given). A status set by auto-calculation can't "
                    "be changed here." + CONFIRM,
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["project_id", "fields"],
                     "properties": {"project_id": ID, "fields": _fields(True)}},
     "handler": t_update_project},
    {"name": "create_task", "title": "PPM Express: create a task", "kind": "create",
     "description": "Create a task in a project, optionally as a sub-task of another task." + CONFIRM,
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["project_id", "name"],
                     "properties": {"project_id": ID, "name": NAME, "fields": _fields(False),
                                    "parent_task_id": _id("Make it a sub-task of this task.")}},
     "handler": t_create_task},
    {"name": "update_task", "title": "PPM Express: update a task", "kind": "update",
     "description": "Change fields of a task (only the ones given): status, progress, dates, assignee, and so "
                    "on. Tasks synced from Jira or Azure DevOps can't be changed here." + CONFIRM,
     "inputSchema": {"type": "object", "additionalProperties": False,
                     "required": ["project_id", "task_id", "fields"],
                     "properties": {"project_id": ID, "task_id": _id("The task's PPM Express ID."),
                                    "fields": _fields(True)}},
     "handler": t_update_task},
    {"name": "create_key_date", "title": "PPM Express: create a key date", "kind": "create",
     "description": "Create a key date, milestone, or release in a project." + CONFIRM,
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["project_id", "name", "date"],
                     "properties": {
                         "project_id": ID, "name": NAME,
                         "date": {"type": "string", "format": "date", "maxLength": 10, "description": "YYYY-MM-DD."},
                         "type": {"type": "string", "enum": ["Key Date", "Milestone", "Release"],
                                  "description": "What it is (default: a key date)."},
                         "fields": _fields(False)}},
     "handler": t_create_key_date},
    {"name": "update_key_date", "title": "PPM Express: update a key date", "kind": "update",
     "description": "Change fields of a key date (only ones created in PPM Express can be changed)." + CONFIRM,
     "inputSchema": {"type": "object", "additionalProperties": False,
                     "required": ["project_id", "key_date_id", "fields"],
                     "properties": {"project_id": ID, "key_date_id": _id("The key date's PPM Express ID."),
                                    "fields": _fields(True)}},
     "handler": t_update_key_date},
    {"name": "create_idea", "title": "PPM Express: create an idea", "kind": "create",
     "description": "Create an idea, optionally under a challenge." + CONFIRM,
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["name"], "properties": {
         "name": NAME, "challenge_id": _id("The challenge it belongs to."), "fields": _fields(False)}},
     "handler": t_create_idea},
    {"name": "update_idea", "title": "PPM Express: update an idea", "kind": "update",
     "description": "Change fields of an idea (only the ones given). Its stage changes with set_idea_stage."
                    + CONFIRM,
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["idea_id", "fields"],
                     "properties": {"idea_id": _id("The idea's PPM Express ID."), "fields": _fields(True)}},
     "handler": t_update_idea},
    {"name": "set_idea_stage", "title": "PPM Express: move an idea to a stage", "kind": "update",
     "description": "Move an idea to another stage: Draft, Proposed, Active, Selected, Not Selected, or "
                    "Archived. PPM Express allows only its own order of stages and says so when a move "
                    "isn't allowed." + CONFIRM,
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["idea_id", "stage"],
                     "properties": {"idea_id": _id("The idea's PPM Express ID."),
                                    "stage": {"type": ["string", "integer"], "maxLength": 40,
                                              "description": "The stage's name or number."}}},
     "handler": t_idea_stage},
    {"name": "create_record", "title": "PPM Express: create a portfolio, program, resource, or challenge",
     "kind": "create",
     "description": "Create a portfolio, program, resource, or challenge (projects, tasks, key dates, and "
                    "ideas have their own tools)." + CONFIRM,
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["kind", "name"], "properties": {
         "kind": {"type": "string", "enum": sorted(RECORDS), "description": "What to create."},
         "name": NAME, "fields": _fields(False)}},
     "handler": t_create_record},
    {"name": "update_record", "title": "PPM Express: update a portfolio, program, resource, or challenge",
     "kind": "update",
     "description": "Change fields of a portfolio, program, resource, or challenge (only the ones given)."
                    + CONFIRM,
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["kind", "record_id", "fields"],
                     "properties": {"kind": {"type": "string", "enum": sorted(RECORDS), "description": "What it is."},
                                    "record_id": _id("Its PPM Express ID."), "fields": _fields(True)}},
     "handler": t_update_record},
]
BY_NAME = {t["name"]: t for t in TOOLS}
WRITE_TOOLS = [t["name"] for t in TOOLS if t["kind"] != "read"]
ANNOTATIONS = {
    "read": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    "create": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    "update": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
}


def public_tools(writes=True):
    """The tool definitions as MCP's tools/list gives them; the reads only when writes are off."""
    return [{"name": t["name"], "title": t["title"], "description": t["description"],
             "inputSchema": t["inputSchema"], "annotations": ANNOTATIONS[t["kind"]]}
            for t in TOOLS if writes or t["kind"] == "read"]


def run_tool(name, args, ctx):
    tool = BY_NAME.get(name)
    if tool is None:
        raise ToolError(f"unknown tool {name!r}")
    if tool["kind"] != "read" and not ctx.settings.writes:
        raise ToolError(READ_ONLY)
    args = validate(tool["inputSchema"], dict(args or {}))
    return tool["handler"](ctx, args)


def validate(schema, args):
    props = schema.get("properties", {})
    for key in args:
        if key not in props:
            raise ToolError(f"unknown argument {key!r}")
    for key in schema.get("required", []):
        if args.get(key) in (None, "") or (isinstance(args.get(key), dict) and not args[key]
                                           and props[key].get("minProperties")):
            raise ToolError(f"{key} is required")
    for key, value in list(args.items()):
        spec = props[key]
        if spec.get("type") == "integer" and isinstance(value, float) and value.is_integer():
            args[key] = value = int(value)
        _check(key, spec, value)
    return args


def _check(name, spec, value):
    kind = spec.get("type")
    if value is None:
        return
    if isinstance(kind, list):                        # either type will do
        for k in kind:
            try:
                return _check(name, dict(spec, type=k), value)
            except ToolError:
                pass
        raise ToolError(f"{name} must be " + " or ".join({"string": "text", "integer": "a whole number"}.get(k, k)
                                                         for k in kind))
    if kind == "string":
        if not isinstance(value, str):
            raise ToolError(f"{name} must be text")
        if len(value) > spec.get("maxLength", 200):
            raise ToolError(f"{name} is too long")
        if spec.get("format") == "uuid" and not UUID.match(value):
            raise ToolError(f"{name} must be a PPM Express ID (a UUID)")
        if spec.get("format") == "date":
            try:
                datetime.date.fromisoformat(value)
            except ValueError:
                raise ToolError(f"{name} must be a date, YYYY-MM-DD") from None
        if "enum" in spec and value not in spec["enum"]:
            raise ToolError(f"{name} must be one of: {', '.join(spec['enum'])}")
    elif kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ToolError(f"{name} must be a whole number")
        if value < spec.get("minimum", -10 ** 9) or value > spec.get("maximum", 10 ** 9):
            raise ToolError(f"{name} is out of range")
    elif kind == "boolean":
        if not isinstance(value, bool):
            raise ToolError(f"{name} must be true or false")
    elif kind == "array":
        if not isinstance(value, list):
            raise ToolError(f"{name} must be a list")
        if len(value) > spec.get("maxItems", 50):
            raise ToolError(f"{name} has too many items")
        for item in value:
            _check(name, spec.get("items", {}), item)
    elif kind == "object":
        if not isinstance(value, dict):
            raise ToolError(f"{name} must be an object of field keys and values")
        if len(value) > spec.get("maxProperties", 50):
            raise ToolError(f"{name} has too many fields")
        if len(value) < spec.get("minProperties", 0):
            raise ToolError(f"{name} must name at least one field")
        for key in value:
            if not FIELD_KEY.match(key):
                raise ToolError(f"{name}: {key[:40]!r} isn't a field key (get_fields lists them)")
        try:
            size = len(json.dumps(value, ensure_ascii=False))
        except (TypeError, ValueError):
            raise ToolError(f"{name} must hold only text, numbers, true or false, lists, and objects") from None
        if size > 65536:
            raise ToolError(f"{name} is too large")

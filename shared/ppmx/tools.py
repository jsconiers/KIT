"""The read-only tools, shared by both servers. Each takes a Context (the client, the settings, the code
tables, the caller's token) and its arguments, and returns a dict ready for JSON.

Every tool name starts with a read word (get, list): Kit's connector guard lets a connector tool through
only when its name reads as read-only. Lists come back a page at a time: total, offset, limit, sort, and
next_offset while there are more.
"""
import datetime

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
    "resources": ["name", "email"],
}
ENTITIES = ["Project", "Program", "Portfolio", "Task", "KeyDate", "Idea", "Challenge", "Resource"]
DATE_ROLES = ("start", "finish", "due", "date")
DONE_WORDS = ("complete", "done", "closed", "finished", "cancel")


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
        return [codes_mod.decode(r, self.tables) for r in records(self.fetch(name, params, **parts))]


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
    """True or False when the record says; None when it can't be told (a code with no label yet)."""
    for role in ("status", "progress"):
        key, value = pick(row, role)
        if value is None:
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if key == "PercentComplete":
                return value >= 100
            continue                                  # a code: codes.py has no label for it yet
        text = text_of(value).lower()
        if text:
            return any(w in text for w in DONE_WORDS)
    if isinstance(row.get("IsCompleted"), bool):
        return row["IsCompleted"]
    return None


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


def _text(desc):
    return {"type": "string", "maxLength": 200, "description": desc}


ID = {"type": "string", "format": "uuid", "maxLength": 36, "description": "The project's PPM Express ID."}

TOOLS = [
    {"name": "get_current_user", "title": "PPM Express: who the token belongs to",
     "description": "Who the personal access token belongs to in PPM Express, and the token's name, scopes, "
                    "and expiry date. Use it first to check the connection.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
     "handler": t_current_user},
    {"name": "list_portfolios", "title": "PPM Express: portfolios",
     "description": "Portfolios the token can see, filtered by name or manager, a page at a time.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "name_contains": _text("Part of the portfolio's name."), "manager": _text("Part of the manager's name."),
         **_paging(["name", "manager", "status"])}},
     "handler": t_portfolios},
    {"name": "list_programs", "title": "PPM Express: programs",
     "description": "Programs the token can see, filtered by name, portfolio, or manager.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "name_contains": _text("Part of the program's name."), "portfolio": _text("Part of a portfolio's name."),
         "manager": _text("Part of the manager's name."), **_paging(["name", "manager", "status"])}},
     "handler": t_programs},
    {"name": "list_projects", "title": "PPM Express: projects",
     "description": "Projects the token can see, filtered by name, portfolio, program, manager, or status, "
                    "sorted and a page at a time. Status and progress are labels when the code tables know "
                    "them, numbers otherwise.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "name_contains": _text("Part of the project's name."), "portfolio": _text("Part of a portfolio's name."),
         "program": _text("Part of a program's name."), "manager": _text("Part of the manager's name."),
         "status": _text("A status label (or code)."),
         **_paging(["name", "status", "manager", "start", "finish"])}},
     "handler": t_projects},
    {"name": "get_project", "title": "PPM Express: one project",
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
    {"name": "list_tasks", "title": "PPM Express: a project's tasks",
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
    {"name": "list_key_dates", "title": "PPM Express: a project's key dates",
     "description": "A project's key dates (milestones), filtered to upcoming or overdue ones.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["project_id"], "properties": {
         "project_id": ID,
         "upcoming_days": {"type": "integer", "minimum": 0, "maximum": 3650,
                           "description": "Only key dates between today and this many days from now."},
         "overdue_only": {"type": "boolean", "description": "Only key dates in the past that aren't finished."},
         **_paging(["date", "name", "status", "type"])}},
     "handler": t_key_dates},
    {"name": "list_ideas", "title": "PPM Express: ideas",
     "description": "Ideas (the demand pipeline), optionally for one challenge, filtered by stage or name.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "challenge_id": {"type": "string", "format": "uuid", "maxLength": 36,
                          "description": "Only ideas for this challenge (its PPM Express ID)."},
         "stage": _text("A stage label (or code)."), "name_contains": _text("Part of the idea's name."),
         **_paging(["name", "stage", "status"])}},
     "handler": t_ideas},
    {"name": "list_resources", "title": "PPM Express: resources",
     "description": "Resources (people and roles), filtered by name.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "name_contains": _text("Part of the resource's name."), **_paging(["name", "email"])}},
     "handler": t_resources},
    {"name": "get_fields", "title": "PPM Express: an entity's fields",
     "description": "The fields of one kind of record (key, label, type, read-only), custom fields included. "
                    "Use it to learn which attribute names a tenant uses.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["entity"], "properties": {
         "entity": {"type": "string", "enum": ENTITIES, "description": "Which kind of record."}}},
     "handler": t_fields},
]
BY_NAME = {t["name"]: t for t in TOOLS}
ANNOTATIONS = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}


def public_tools():
    """The tool definitions as MCP's tools/list gives them."""
    return [{"name": t["name"], "title": t["title"], "description": t["description"],
             "inputSchema": t["inputSchema"], "annotations": ANNOTATIONS} for t in TOOLS]


def run_tool(name, args, ctx):
    tool = BY_NAME.get(name)
    if tool is None:
        raise ToolError(f"unknown tool {name!r}")
    args = validate(tool["inputSchema"], dict(args or {}))
    return tool["handler"](ctx, args)


def validate(schema, args):
    props = schema.get("properties", {})
    for key in args:
        if key not in props:
            raise ToolError(f"unknown argument {key!r}")
    for key in schema.get("required", []):
        if args.get(key) in (None, ""):
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
    if kind == "string":
        if not isinstance(value, str):
            raise ToolError(f"{name} must be text")
        if len(value) > spec.get("maxLength", 200):
            raise ToolError(f"{name} is too long")
        if spec.get("format") == "uuid" and not UUID.match(value):
            raise ToolError(f"{name} must be a PPM Express ID (a UUID)")
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

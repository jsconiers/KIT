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
import time

from . import codes as codes_mod
from .client import PARAMS, UUID, PPMXError, records

# Which attribute holds what. CONFIRMED on 02-Nov-2026 against a live tenant and PPM Express's OpenAPI
# description for projects, portfolios, programs, tasks, key dates, and deliverables (Name, OverallStatus,
# Status, Manager, AssignedTo, StartDate, FinishDate, DueDate, Date, Portfolio, Program, Progress, Type,
# IsComplete); the other names are fallbacks for other tenants. People fields (Manager, AssignedTo,
# Sponsor) are lists of {"id", "fullName", "imageId"}; Portfolio and Program lists of {"id", "name"}. The
# first name a record has wins; get_fields lists a tenant's own keys.
FIELDS = {
    "name": ["Name", "Title"],
    "status": ["OverallStatus", "Status", "State"],
    "manager": ["Manager", "ProjectManager", "Owner"],
    "start": ["StartDate", "Start"],
    "finish": ["FinishDate", "Finish", "EndDate"],
    "due": ["DueDate", "FinishDate", "Finish", "Date"],
    "date": ["Date", "DueDate", "FinishDate"],
    "portfolio": ["Portfolio", "Portfolios"],
    "program": ["Program", "Programs"],
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
    "deliverables": ["name", "status", "assignee", "due", "progress"],
}
ENTITIES = ["Project", "Program", "Portfolio", "Task", "KeyDate", "Deliverable", "Idea", "Challenge", "Resource"]
# The kind of record each endpoint holds, for code tables that apply to one kind ("KeyDate.Type").
ENTITY_OF = {"portfolios": "Portfolio", "portfolio": "Portfolio", "programs": "Program", "program": "Program",
             "projects": "Project", "project": "Project", "tasks": "Task", "task": "Task", "tasks_bulk": "Task",
             "key_dates": "KeyDate", "key_date": "KeyDate", "ideas": "Idea", "idea": "Idea", "idea_stage": "Idea",
             "challenges": "Challenge", "challenge": "Challenge", "resources": "Resource", "resource": "Resource",
             "deliverables": "Deliverable", "deliverable": "Deliverable"}
DATE_ROLES = ("start", "finish", "due", "date")
DONE_WORDS = ("complete", "done", "closed", "finished", "cancel")
# Fields that name people or other records take a list of {"search": a name or email} or {"id": an ID}
# (PPM Express's format); plain text is turned into that. Tags take "#tag" text.
PEOPLE = {"Manager", "Managers", "ProjectManager", "Owner", "Owners", "AssignedTo", "Sponsor", "Sponsors",
          "Resource", "Resources"}
LINKS = {"Portfolio", "Portfolios", "Program", "Programs", "Predecessor", "Predecessors"}
FIELD_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_ .-]{0,79}$")
# Record kinds the general create_record and update_record tools take: (list endpoint, item endpoint,
# entity).
RECORDS = {"portfolio": ("portfolios", "portfolio", "Portfolio"), "program": ("programs", "program", "Program"),
           "resource": ("resources", "resource", "Resource"), "challenge": ("challenges", "challenge", "Challenge")}
READ_ONLY = "This PPM Express server is read-only (PPMX_WRITES is off), so it makes no changes."
# The scope a read needs, by list endpoint, as PPM Express names its token scopes.
SCOPE_OF = {"resources": "resource:read", "ideas": "idea:read", "challenges": "challenge:read"}
WHAT_OF = {"resources": "resources", "ideas": "ideas", "challenges": "challenges"}


class ToolError(Exception):
    """A problem with a tool call, safe to show to the caller."""


class Context:
    """One caller's view. owner=True on the single-user (stdio) servers, where PPMX_MY_NAME names the one
    person they serve; the multi-user HTTP service leaves it False, so "me" is only ever the token's own
    user there."""

    def __init__(self, client, settings, tables, token, hint="", owner=False):
        self.client, self.settings, self.tables = client, settings, tables
        self.token, self.hint, self.owner = token, hint, owner
        self._me = None

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

    def me(self):
        """The token's own user, for "me": its user ID, the names it can go by, and how each was found."""
        if self._me is None:
            if not self.token:
                raise ToolError(self.hint or "no personal access token")
            who = self.client.whoami(self.token)
            names, how = [], []
            if who.get("fullName"):
                names.append(who["fullName"])
                how.append("full name from PPM Express")
            if self.owner and self.settings.my_name:
                names.append(self.settings.my_name)
                how.append("PPMX_MY_NAME")
            local = (who.get("email") or who.get("logonAccount") or "").split("@")[0].split("\\")[-1]
            self._me = {"id": who.get("id"), "names": [norm(n) for n in names if norm(n)],
                        "handle": re.sub(r"[^a-z]", "", local.lower()), "how": how, "scopes": who.get("scopes")}
        return self._me

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
        return " ".join(text_of(value.get(k)) for k in ("fullName", "name", "Name", "title", "email", "id")
                        if value.get(k))
    if isinstance(value, (list, tuple)):
        return " ".join(text_of(v) for v in value)
    return str(value)


def matches(row, role, wanted):
    if not wanted:
        return True
    return wanted.lower() in text_of(pick(row, role)[1]).lower()


def norm(name):
    return " ".join(str(name or "").lower().split())


def name_forms(name):
    """Ways an email or logon name is often made from a full name: alexrivera, arivera, riveraa, alexr."""
    w = [x for x in re.split(r"[^a-z]+", str(name).lower()) if x]
    if not w:
        return set()
    return {"".join(w), w[0][0] + w[-1], w[0] + w[-1], w[-1] + w[0][0], w[0] + w[-1][0]}


def people(value):
    """A people field's entries as a list, whatever shape it came in."""
    if value in (None, "", []):
        return []
    return value if isinstance(value, list) else [value]


def is_me(me, value):
    """True when a people field holds the token's own user: by user ID, by a name it goes by (exactly,
    any case), or by a full name its email or logon name is made from."""
    for p in people(value):
        pid = p.get("id") if isinstance(p, dict) else None
        name = norm(p.get("fullName") or p.get("name") or p.get("Name")) if isinstance(p, dict) else norm(p)
        if (pid and me.get("id") and str(pid).lower() == str(me["id"]).lower()) or (name and name in me["names"]):
            return True
        if name and len(me["handle"]) >= 3 and me["handle"] in name_forms(name):
            return True
    return False


def person_matches(ctx, row, role, wanted):
    """A person filter: "me" for the token's own user, otherwise part of a name (any case), matched
    against each person's fullName (or name or email) in the field."""
    if not wanted:
        return True
    value = pick(row, role)[1]
    if norm(wanted) == "me":
        return is_me(ctx.me(), value)
    w = wanted.lower()
    return any(w in text_of(p).lower() for p in people(value))


def me_report(ctx):
    """What a result says about "me": how the token's user was matched, and what to do when only the ID
    and email were there to go on."""
    me = ctx.me()
    out = {"user_id": me.get("id"), "matched_by": ["user ID", "email or logon name"] + me["how"]}
    if not me["names"]:
        out["note"] = ("PPM Express's /me gives no full name, and people fields can hold resource IDs that "
                       "differ from the user ID, so \"me\" matched by user ID and by names your email or logon "
                       "name could be made from. " + (
                           "Set PPMX_MY_NAME to your name as PPM Express shows it for an exact match."
                           if ctx.owner else "If that misses you, filter by your name instead."))
    return out


def empty_note(ctx, name):
    """Why a list PPM Express answered with nothing may be empty: a missing scope, or the account's own
    PPM Express permissions (the endpoint takes no filters, per PPM Express's API description)."""
    scope, what = SCOPE_OF[name], WHAT_OF[name]
    try:
        scopes = ctx.me().get("scopes") or []
    except (PPMXError, ToolError):
        scopes = []
    if scopes and scope not in scopes:
        return (f"PPM Express returned no {what}: the token doesn't have the {scope} scope. Create a token "
                f"with {scope} in PPM Express > Automation.")
    has = f"The token has the {scope} scope" if scopes else "PPM Express didn't list the token's scopes"
    return (f"PPM Express returned no {what} at all. {has}, and this endpoint takes no filters or paging "
            f"(per PPM Express's API description), so the empty list is what your PPM Express account may "
            f"see: PPM Express applies the account's own permissions (its role and license) as well as the "
            f"token's scopes. If you expect {what}, ask a PPM Express administrator for permission to view "
            f"them; otherwise this tenant has none.")


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
    for flag in ("IsCompleted", "IsComplete"):           # key dates: IsComplete (a Flag)
        if row.get(flag) is True:
            return True
        if isinstance(row.get(flag), bool):
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
        if key in row and key not in codes_mod.INTERNAL:
            out[key] = row[key]
    return out


def add_notes(out, notes):
    """Add notes to a result, after any it has."""
    notes = [n for n in notes if n]
    if notes:
        out.setdefault("notes", []).extend(notes)
    return out


def record(row, entity=None):
    """(the record as a tool returns it, a note about codes in it with no label or None)."""
    return codes_mod.public(row), codes_mod.unlabeled_note([row], entity)


def sort_value(row, role):
    value = pick(row, role)[1]
    if value is None:
        return None
    if role in DATE_ROLES:
        d = day(value)
        if d:
            return d.isoformat()
    return text_of(value).lower()


def page(rows, args, ctx, default_sort, roles, keep=()):
    total = len(rows)
    limit = min(int(args.get("limit") or ctx.settings.page_size), ctx.settings.max_rows)
    offset = min(int(args.get("offset") or 0), total)
    role = args.get("sort") or default_sort
    desc = bool(args.get("descending"))
    keyed = [(sort_value(r, role), r) for r in rows]
    ordered = [r for _, r in sorted([k for k in keyed if k[0] is not None], key=lambda k: k[0], reverse=desc)]
    ordered += [r for v, r in keyed if v is None]     # records without the value come last either way
    shown = ordered[offset:offset + limit]
    items = [summarize(r, roles, list(keep) + list(args.get("fields") or [])) for r in shown]
    out = {"total": total, "offset": offset, "limit": limit, "sort": f"{role} {'desc' if desc else 'asc'}",
           "items": items}
    if offset + limit < total:
        out["next_offset"] = offset + limit
    # codes with no label, among the fields shown
    return add_notes(out, [codes_mod.unlabeled_note(
        [{"unlabeled": {f: c for f, c in (r.get("unlabeled") or {}).items() if f in item}}
         for r, item in zip(shown, items)])])


# ---------------------------------------------------------------- the tools

def t_current_user(ctx, args):
    rec = (records(ctx.fetch("me")) or [{}])[0]
    token = rec.get("token") if isinstance(rec.get("token"), dict) else {}
    out = {k: rec[k] for k in ("id", "name", "displayName", "email", "logonAccount") if rec.get(k) is not None}
    out["token"] = {k: token[k] for k in ("name", "expirationDate", "scopes") if token.get(k) is not None}
    return out


def with_me(out, ctx, args, keys):
    """Add what "me" matched to a result when a person filter asked for "me"."""
    if any(norm(args.get(k)) == "me" for k in keys):
        out["me"] = me_report(ctx)
    return out


def t_portfolios(ctx, args):
    rows = [r for r in ctx.rows("portfolios")
            if matches(r, "name", args.get("name_contains")) and person_matches(ctx, r, "manager", args.get("manager"))]
    return with_me(page(rows, args, ctx, "name", SUMMARY["portfolios"]), ctx, args, ["manager"])


def t_programs(ctx, args):
    rows = [r for r in ctx.rows("programs")
            if matches(r, "name", args.get("name_contains")) and matches(r, "portfolio", args.get("portfolio"))
            and person_matches(ctx, r, "manager", args.get("manager"))]
    return with_me(page(rows, args, ctx, "name", SUMMARY["programs"]), ctx, args, ["manager"])


def project_rows(ctx, args):
    return [r for r in ctx.rows("projects")
            if all(matches(r, role, args.get(arg)) for arg, role in (
                ("name_contains", "name"), ("portfolio", "portfolio"), ("program", "program"), ("status", "status")))
            and person_matches(ctx, r, "manager", args.get("manager"))]


def t_projects(ctx, args):
    return with_me(page(project_rows(ctx, args), args, ctx, "name", SUMMARY["projects"]), ctx, args, ["manager"])


def t_project(ctx, args):
    pid = args["project_id"]
    found = ctx.rows("project", id=pid)
    if not found:
        raise ToolError("PPM Express returned no project for that ID")
    project, note = record(found[0], "Project")
    out = add_notes({"project": project}, [note])
    include = args.get("include") or []
    each = {"limit": args.get("limit_each") or ctx.settings.page_size}
    if "key_dates" in include:
        out["key_dates"] = page(ctx.rows("key_dates", id=pid), each, ctx, "date", SUMMARY["key_dates"])
    if "tasks" in include:
        tasks = ctx.rows("tasks", id=pid)
        if args.get("open_tasks_only", True):
            tasks, unknown = open_rows(tasks)
            if unknown:
                add_notes(out, [f"{unknown} task(s) kept as open: their status is a code with no label yet"])
        out["tasks"] = page(tasks, each, ctx, "due", SUMMARY["tasks"])
    if "deliverables" in include:
        out["deliverables"] = page(ctx.rows("deliverables", id=pid), each, ctx, "due", SUMMARY["deliverables"])
    return out


def due_filters(rows, args, ctx, notes, what="item"):
    """open_only, overdue_only, and due_within_days, on the "due" role."""
    if args.get("open_only") or args.get("overdue_only"):
        rows, unknown = open_rows(rows)
        if unknown:
            notes.append(f"{unknown} {what}(s) kept as open: their status is a code with no label yet")
    if args.get("overdue_only"):
        rows = [r for r in rows if role_day(r, "due") and role_day(r, "due") < ctx.today]
    if args.get("due_within_days") is not None:
        end = ctx.today + datetime.timedelta(days=args["due_within_days"])
        rows = [r for r in rows if role_day(r, "due") and ctx.today <= role_day(r, "due") <= end]
    return rows


def t_tasks(ctx, args):
    rows = [r for r in ctx.rows("tasks", id=args["project_id"])
            if matches(r, "name", args.get("name_contains")) and person_matches(ctx, r, "assignee", args.get("assignee"))]
    notes = []
    rows = due_filters(rows, args, ctx, notes, "task")
    out = add_notes(page(rows, args, ctx, "due", SUMMARY["tasks"]), notes)
    return with_me(out, ctx, args, ["assignee"])


def t_deliverables(ctx, args):
    rows = [r for r in ctx.rows("deliverables", id=args["project_id"])
            if matches(r, "name", args.get("name_contains")) and matches(r, "status", args.get("status"))
            and person_matches(ctx, r, "assignee", args.get("assignee"))]
    notes = []
    rows = due_filters(rows, args, ctx, notes, "deliverable")
    out = add_notes(page(rows, args, ctx, "due", SUMMARY["deliverables"]), notes)
    return with_me(out, ctx, args, ["assignee"])


def t_deliverable(ctx, args):
    found = ctx.rows("deliverable", id=args["project_id"], deliverable_id=args["deliverable_id"])
    if not found:
        raise ToolError("PPM Express returned no deliverable for that ID")
    deliverable, note = record(found[0], "Deliverable")
    return add_notes({"project_id": args["project_id"], "deliverable": deliverable}, [note])


def t_my_work(ctx, args):
    """Tasks and deliverables assigned to the token's own user, across projects, bounded: at most
    max_projects projects (PPMX_WORK_MAX_PROJECTS) and PPMX_WORK_SECONDS of scanning, and the client's
    per-token rate limit throughout. The result says how many projects were in scope and scanned."""
    started = time.monotonic()                        # the time limit counts the project list and /me too
    me = ctx.me()
    include = args.get("include") or ["tasks", "deliverables"]
    cap = min(int(args.get("max_projects") or ctx.settings.work_max_projects), ctx.settings.work_max_projects)
    projects = [r for r in project_rows(ctx, args) if r.get("id")]
    if args.get("project_ids"):
        wanted = {str(x).lower() for x in args["project_ids"]}
        projects = [r for r in projects if str(r["id"]).lower() in wanted]
    if args.get("open_only", True):
        projects = [r for r in projects if is_done(r) is not True]
    # Projects the user manages first, then the latest finishing: the likeliest to hold their work.
    projects.sort(key=lambda r: (not is_me(me, pick(r, "manager")[1]), -(role_day(r, "finish") or
                                                                         datetime.date.min).toordinal()))
    items, scanned, failed, stopped = [], 0, 0, False
    for proj in projects[:cap]:
        # >=, not >: Windows' clock ticks about every 16 ms, so a fast scan can read 0 seconds, and a 0-second
        # limit must still stop after the first project.
        if scanned and time.monotonic() - started >= ctx.settings.work_seconds:
            stopped = True
            break
        scanned += 1
        pname = text_of(pick(proj, "name")[1])
        for kind, name in (("task", "tasks"), ("deliverable", "deliverables")):
            if name not in include:
                continue
            try:
                rows = ctx.rows(name, id=proj["id"])
            except PPMXError as e:
                if e.status == 429:
                    stopped = True
                    break
                failed += 1
                continue
            for r in rows:
                if is_me(me, pick(r, "assignee")[1]):
                    items.append(dict(r, kind=kind, project_id=proj["id"], project=pname))
        if stopped:
            break
    notes = []
    items = due_filters(items, dict(args, open_only=args.get("open_only", True)), ctx, notes)
    out = page(items, args, ctx, "due", ["name", "status", "assignee", "due", "progress"],
               keep=["kind", "project_id", "project"])
    complete = scanned == len(projects) and not failed
    out.update(projects_in_scope=len(projects), projects_scanned=scanned, complete=complete, me=me_report(ctx))
    if len(projects) > scanned:
        notes.append(f"Scanned {scanned} of {len(projects)} projects in scope"
                     + (" before the time or rate limit" if stopped else f" (the cap is {cap})")
                     + ": narrow it with name_contains, portfolio, program, manager, or project_ids.")
    if failed:
        notes.append(f"{failed} list(s) couldn't be read and were skipped.")
    return add_notes(out, notes)


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
    every = ctx.rows("ideas", params)
    rows = [r for r in every if matches(r, "name", args.get("name_contains")) and matches(r, "stage", args.get("stage"))]
    out = page(rows, args, ctx, "name", SUMMARY["ideas"])
    if not every and not params:
        out["explanation"] = empty_note(ctx, "ideas")
    return out


def t_challenges(ctx, args):
    every = ctx.rows("challenges")
    out = page([r for r in every if matches(r, "name", args.get("name_contains"))], args, ctx, "name",
               SUMMARY["challenges"])
    if not every:
        out["explanation"] = empty_note(ctx, "challenges")
    return out


def t_resources(ctx, args):
    every = ctx.rows("resources")
    out = page([r for r in every if matches(r, "name", args.get("name_contains"))], args, ctx, "name",
               SUMMARY["resources"])
    if not every:
        out["explanation"] = empty_note(ctx, "resources")
    return out


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
    rec, note = record(codes_mod.decode(recs[0], ctx.tables, entity), entity) if recs else ({}, None)
    out = {"result": action, "kind": kind, "id": rec.get("id") or known_id, "fields": sorted(sent)}
    if rec:
        out["record"] = rec
    return add_notes(out, [note])


def t_create_project(ctx, args):
    attrs = attributes(ctx, "Project", args.get("fields"), args["name"])
    return written(ctx, "created", "project", ctx.write("POST", "projects", {"attributes": attrs}), attrs, "Project")


def t_update_project(ctx, args):
    upd = changes(ctx, "Project", args["fields"])
    value = ctx.write("PATCH", "project", {"updates": upd}, id=args["project_id"])
    return written(ctx, "updated", "project", value, upd, "Project", args["project_id"])


def t_create_task(ctx, args):
    attrs = attributes(ctx, "Task", args.get("fields"), args["name"])
    body = {"attributes": attrs}
    if args.get("parent_task_id"):
        body = {"parentId": args["parent_task_id"], "attributes": attrs}   # a sub-task (CreateTaskRequest)
    value = ctx.write("POST", "tasks", body, id=args["project_id"])
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
    """POST {"stage": name}: PPM Express takes the stage's name (Draft, Proposed, Active, Selected,
    NotSelected, Archived), given here as a name in any case and spacing, or as its number."""
    table = codes_mod.table_for(ctx.tables, "Stage", "Idea") or codes_mod.TABLES["Idea.Stage"]
    given = str(args["stage"]).strip()
    label = table.get(int(given)) if given.lstrip("-").isdigit() else next(
        (v for v in table.values() if v.replace(" ", "").lower() == given.replace(" ", "").lower()), None)
    if label is None:
        raise ToolError("stage must be one of: " + ", ".join(table.values()) + " (or its number)")
    value = ctx.write("POST", "idea_stage", {"stage": label.replace(" ", "")}, id=args["idea_id"])
    return written(ctx, "updated", "idea", value, ["stage"], "Idea", args["idea_id"])


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


def PERSON(role):  # noqa: N802 - a schema, like ID
    return _text(f"Part of the {role}'s name (any case), or \"me\" for the token's own user.")


def DUE(what):  # noqa: N802
    return {"open_only": {"type": "boolean", "description": f"Leave out finished {what}."},
            "overdue_only": {"type": "boolean", "description": f"Only unfinished {what} past their due date."},
            "due_within_days": {"type": "integer", "minimum": 0, "maximum": 3650,
                                "description": f"Only {what} due between today and this many days from now."}}
NAME = _text("The name (or title).", 255)
CHANGES = ("The fields by their keys (get_fields lists a tenant's keys, custom fields included), for example "
           '{"Description": "...", "StartDate": "2026-11-02", "Status": "At Risk", "Manager": "alex@example.com"}. '
           "Coded fields (Status, Progress, Priority, Risk, and the like) take their label or number; people "
           "(Manager, AssignedTo) take a name, an email, or an ID; Portfolio and Program take names or IDs; "
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
         "name_contains": _text("Part of the portfolio's name."), "manager": PERSON("manager"),
         **_paging(["name", "manager", "status"])}},
     "handler": t_portfolios},
    {"name": "list_programs", "title": "PPM Express: programs", "kind": "read",
     "description": "Programs the token can see, filtered by name, portfolio, or manager.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "name_contains": _text("Part of the program's name."), "portfolio": _text("Part of a portfolio's name."),
         "manager": PERSON("manager"), **_paging(["name", "manager", "status"])}},
     "handler": t_programs},
    {"name": "list_projects", "title": "PPM Express: projects", "kind": "read",
     "description": "Projects the token can see, filtered by name, portfolio, program, manager, or status, "
                    "sorted and a page at a time. Coded fields (status, progress, priority, and the like) come as "
                    "their labels: On Track, At Risk, In Progress.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "name_contains": _text("Part of the project's name."), "portfolio": _text("Part of a portfolio's name."),
         "program": _text("Part of a program's name."), "manager": PERSON("manager"),
         "status": _text("A status label (or code)."),
         **_paging(["name", "status", "manager", "start", "finish"])}},
     "handler": t_projects},
    {"name": "get_project", "title": "PPM Express: one project", "kind": "read",
     "description": "One project's details, optionally with its key dates, deliverables, and tasks (open ones "
                    "unless open_tasks_only is false).",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["project_id"], "properties": {
         "project_id": ID,
         "include": {"type": "array", "maxItems": 3,
                     "items": {"type": "string", "enum": ["key_dates", "tasks", "deliverables"]},
                     "description": "Also return the project's key dates, tasks, deliverables, or any of them."},
         "open_tasks_only": {"type": "boolean", "description": "Only tasks not finished (default true)."},
         "limit_each": {"type": "integer", "minimum": 1, "maximum": 5000,
                        "description": "Rows of key dates and of tasks (default 25)."}}},
     "handler": t_project},
    {"name": "list_tasks", "title": "PPM Express: a project's tasks", "kind": "read",
     "description": "A project's tasks, filtered by name, assignee, open, overdue, or due within some days. "
                    "Tasks synced from Jira or Azure DevOps are included (read-only in PPM Express).",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["project_id"], "properties": {
         "project_id": ID, "name_contains": _text("Part of the task's name."),
         "assignee": PERSON("assignee"), **DUE("tasks"),
         **_paging(["due", "start", "name", "status", "assignee"])}},
     "handler": t_tasks},
    {"name": "list_deliverables", "title": "PPM Express: a project's deliverables", "kind": "read",
     "description": "A project's deliverables, filtered by name, status, assignee (\"me\" for yourself), open, "
                    "overdue, or due within some days.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["project_id"], "properties": {
         "project_id": ID, "name_contains": _text("Part of the deliverable's name."),
         "status": _text("A status label (or code)."), "assignee": PERSON("assignee"), **DUE("deliverables"),
         **_paging(["due", "name", "status", "assignee"])}},
     "handler": t_deliverables},
    {"name": "get_deliverable", "title": "PPM Express: one deliverable", "kind": "read",
     "description": "One deliverable of a project, with all its fields.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["project_id", "deliverable_id"],
                     "properties": {"project_id": ID, "deliverable_id": _id("The deliverable's PPM Express ID.")}},
     "handler": t_deliverable},
    {"name": "list_my_work", "title": "PPM Express: my tasks and deliverables", "kind": "read",
     "description": "Tasks and deliverables assigned to the token's own user, across projects: open ones unless "
                    "open_only is false, optionally due within some days. Bounded: it scans at most "
                    "max_projects projects (projects you manage first) within a time limit, and says how many "
                    "it scanned; narrow it with the project filters to cover more.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "include": {"type": "array", "maxItems": 2, "items": {"type": "string", "enum": ["tasks", "deliverables"]},
                     "description": "What to look for (default both)."},
         "open_only": {"type": "boolean", "description": "Only unfinished work in unfinished projects (default true)."},
         "overdue_only": {"type": "boolean", "description": "Only unfinished work past its due date."},
         "due_within_days": {"type": "integer", "minimum": 0, "maximum": 3650,
                             "description": "Only work due between today and this many days from now."},
         "name_contains": _text("Only projects whose name has this."), "portfolio": _text("Only this portfolio's projects."),
         "program": _text("Only this program's projects."), "manager": PERSON("project manager"),
         "status": _text("Only projects with this status label (or code)."),
         "project_ids": {"type": "array", "maxItems": 50, "items": {"type": "string", "format": "uuid", "maxLength": 36},
                         "description": "Only these projects (their PPM Express IDs)."},
         "max_projects": {"type": "integer", "minimum": 1, "maximum": 200,
                          "description": "Projects to scan at most (default and ceiling: PPMX_WORK_MAX_PROJECTS, 25)."},
         **_paging(["due", "name", "status"])}},
     "handler": t_my_work},
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
     "description": "Resources (people and roles), filtered by name. When PPM Express sends none, the answer "
                    "says why (a missing scope, or the account's own PPM Express permissions).",
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

"""Meeting actions into PPM Express: proposals for tasks, from the meeting scribe's Actions block.

The scribe ends its minutes with one line per action:

    - [action] <action> | owner: <role, or "owner"> | due: <DD-Mmm-YYYY or no date> | project: <slug> | source: <...>

and Kit copies those lines into briefs/pending-actions.md. Each action becomes a proposal: create a task in
the project's PPM Express project, or update the open task it matches (its due date, its assignee when it has
none, or Completed when the action says it's done), or nothing when PPM Express already has it. Proposing
only reads PPM Express; each proposal is made later, one at a time, through the create_task or update_task
tool, after the person says yes. Standard library only.
"""
import datetime
import re

from .tools import is_done, pick, role_day, text_of

ACTION = re.compile(r"^\s*[-*]\s*\[action\]\s*(?P<body>.+?)\s*$", re.I)
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
STOP = set("""a an and are as at be by for from has have in is it of on or the to with our your we this that will
can not get set up out off do does via per into onto about after before all any new""".split())
MATCH = 0.5            # how alike an action and a task's name must be (shared words over all words) to match


def words(text):
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2 and w not in STOP}


def likeness(a, b):
    wa, wb = words(a), words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def due_date(text):
    """YYYY-MM-DD from DD-Mmm-YYYY or YYYY-MM-DD, or "" (for "no date" and anything else)."""
    t = (text or "").strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    try:
        if m:
            return datetime.date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        m = re.search(r"\b(\d{1,2})-([A-Za-z]{3})-(\d{4})\b", t)
        if m and m[2].lower() in MONTHS:
            return datetime.date(int(m[3]), MONTHS.index(m[2].lower()) + 1, int(m[1])).isoformat()
    except ValueError:
        return ""
    return ""


def parse(text):
    """The actions in minutes or in pending-actions.md, numbered from 1, with their status there: proposed,
    confirmed (in Kit's queue already), or dropped."""
    out = []
    for line in (text or "").splitlines():
        m = ACTION.match(line)
        if not m:
            continue
        parts = [p.strip() for p in m.group("body").split("|")]
        fields = {}
        for p in parts[1:]:
            key, sep, value = p.partition(":")
            if sep:
                fields[key.strip().lower()] = value.strip()
        tail = " | ".join(parts[1:]).lower()                # after the action: its words never set the status
        status = ("dropped" if re.search(r"\bdropped\b", tail) else
                  "confirmed" if re.search(r"\bconfirmed\b", tail) else "proposed")
        done = bool(re.search(r"\b(done|complete|completed|finished)\b", fields.get("status", "").lower()))
        what = parts[0].strip()
        if not what:
            continue
        out.append({"n": len(out) + 1, "action": what, "owner": fields.get("owner", ""),
                    "due": due_date(fields.get("due", "")), "project": fields.get("project", ""),
                    "source": fields.get("source", ""), "status": status, "done": done})
    return out


def find_project(projects, slug, project_map, given=None):
    """(project row, how): how is "given", "mapped", or "matched"; (None, why) when there's no clear one."""
    def by(ident):
        ident = (ident or "").strip()
        for p in projects:
            if str(p.get("id")) == ident:
                return p
        hits = [p for p in projects if text_of(pick(p, "name")[1]).strip().lower() == ident.lower()]
        return hits[0] if len(hits) == 1 else None
    if given:
        p = by(given)
        return (p, "given") if p else (None, f"no project {given!r} that this token can see")
    target = (project_map or {}).get(slug) or (project_map or {}).get((slug or "").lower())
    if target:
        p = by(target)
        return (p, "mapped") if p else (None, f"the project mapped to {slug!r} ({target}) isn't visible")
    sw = words((slug or "").replace("-", " ").replace("_", " "))
    if not sw:
        return None, "the action names no project"
    scored = sorted(((len(sw & words(text_of(pick(p, "name")[1]))) / len(sw), i) for i, p in enumerate(projects)),
                    reverse=True)
    if scored and scored[0][0] >= 0.6 and (len(scored) == 1 or scored[1][0] < scored[0][0]):
        return projects[scored[0][1]], "matched"
    return None, f"no PPM Express project clearly matches {slug!r}"


def best_task(tasks, action, finished=False):
    """(task, likeness) for the open task most like the action (with finished=True, the finished task most
    like it), or (None, 0)."""
    best, score = None, 0.0
    for t in tasks:
        if (is_done(t) is True) != finished or t.get("sourceType"):   # synced from Jira or Azure DevOps: not here
            continue
        s = likeness(action, text_of(pick(t, "name")[1]))
        if s > score:
            best, score = t, s
    return (best, score) if score >= MATCH else (None, 0.0)


def _assignee(task):
    """Whether someone is assigned, in whatever form PPM Express gives it back (a person, or the reference
    a change sent: {"search": ...} or {"id": ...})."""
    return pick(task, "assignee")[1] is not None


def propose_one(a, project, how, tasks, me, due_key):
    """One proposal: the tool to run and its arguments, and what it does, in words."""
    pid = str(project["id"])
    pname = text_of(pick(project, "name")[1])
    base = {"n": a["n"], "action": a["action"], "owner": a["owner"], "due": a["due"], "source": a["source"],
            "project": {"id": pid, "name": pname, "how": how}, "status": "proposed"}
    mine = a["owner"].strip().lower() in ("owner", "me", "you", "") and bool(me)
    task, score = best_task(tasks, a["action"])
    if a["done"] and not task:                          # done already: never a new task for it
        done, _ = best_task(tasks, a["action"], finished=True)
        says = (f"already done in PPM Express as the task \"{text_of(pick(done, 'name')[1])}\"" if done
                else "done, per the minutes; no PPM Express task to mark")
        return dict(base, kind="none", says=says)
    if task:
        fields, said = {}, []
        key = pick(task, "due")[0] or due_key
        current = role_day(task, "due")
        if a["due"] and (not current or current.isoformat() != a["due"]):
            fields[key] = a["due"]
            said.append(f"due {a['due']}" + (f" (was {current.isoformat()})" if current else ""))
        if mine and not _assignee(task):
            fields["AssignedTo"] = me
            said.append("assigned to you")
        if a["done"]:
            fields["Progress"] = "Completed"
            said.append("Completed")
        tname = text_of(pick(task, "name")[1])
        base["task"] = {"id": str(task["id"]), "name": tname, "likeness": round(score, 2)}
        if not fields:
            return dict(base, kind="none", says=f"already in PPM Express as the task \"{tname}\"; nothing to change")
        return dict(base, kind="update", tool="update_task",
                    args={"project_id": pid, "task_id": str(task["id"]), "fields": fields},
                    says=f"update the task \"{tname}\" in {pname}: " + ", ".join(said))
    fields, said = {}, []
    if a["due"]:
        fields[due_key] = a["due"]
        said.append(f"due {a['due']}")
    if mine:
        fields["AssignedTo"] = me
        said.append("assigned to you")
    elif a["owner"]:
        said.append(f"owner {a['owner']}: assign it in PPM Express")
    name = a["action"][:255]
    args = {"project_id": pid, "name": name}
    if fields:
        args["fields"] = fields
    return dict(base, kind="create", tool="create_task", args=args,
                says=f"create the task \"{name}\" in {pname}" + (f": {', '.join(said)}" if said else ""))


def propose(ctx, actions, project_map=None, me=None, given_project=None, due_key="FinishDate"):
    """Proposals for the actions that aren't dropped, reading PPM Express (projects, and each project's
    tasks once). Actions with no clear project come back as kind "no-project", with the reason."""
    projects = [p for p in ctx.rows("projects") if p.get("id")]
    tasks_of, out = {}, []
    for a in actions:
        if a["status"] == "dropped":
            continue
        project, how = find_project(projects, a["project"], project_map, given_project)
        if not project:
            out.append({"n": a["n"], "action": a["action"], "owner": a["owner"], "due": a["due"],
                        "source": a["source"], "slug": a["project"], "kind": "no-project", "says": how,
                        "status": "proposed"})
            continue
        pid = str(project["id"])
        if pid not in tasks_of:
            tasks_of[pid] = ctx.rows("tasks", id=pid)
        keys = [pick(t, "due")[0] for t in tasks_of[pid] if pick(t, "due")[0]]
        key = max(set(keys), key=keys.count) if keys else due_key
        out.append(propose_one(a, project, how, tasks_of[pid], me, key))
    return out

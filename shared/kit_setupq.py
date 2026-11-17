"""kit_setupq: the open setup questions, for the first-run wizard in `kit-settings ui` and `kit-settings questions`.

A setup question is a field in a setup file in memory/context/ ("- **Field:** not set. ...") that is still not set.
kit_settings reads the fields (and knows which are editable, their type, and how to write one); this module turns
the not-set ones into questions: which file and field, which agents read that file, a one-line question, an example
answer, and a priority, then orders them so the ones that hold an agent back most come first:

  high    a path the health check reads (the library root, templates, folders), or a field in a file where nothing
          is set yet, so the agents that read it have nothing to work with
  normal  everything else

Within a priority, fields read by more agents come first. The wizard's own state (questions saved for later or
skipped, whether it has run) is in .install/setup-wizard.json; it never holds an answer. Answers are written by
kit_settings.apply_edit: a preview first, a backup, a one-field write, a commit in Kit's private repo, and a log line.
"""
import datetime as dt
import json
import os
import pathlib
import re

import kit_settings as ks

STATE = ".install/setup-wizard.json"

# Example answers for common fields, by (file, field). The rest get an example from the field's type.
EXAMPLES = {
    ("library.md", "Library root"): "`~/Documents/Library`",
    ("calendar.md", "Working hours and time zone"): "08:00 to 18:00, Monday to Friday, America/New_York",
    ("audit.md", "Working hours"): "07:00 to 19:00, Monday to Friday",
    ("costs.md", "Currency"): "USD",
    ("costs.md", "Contingency"): "15% on the likely figure, 25% when a vendor price is assumed",
    ("costs.md", "Labor rates"): "architect $150/h, engineer $120/h, blended internal",
    ("costs.md", "Rate cards and price lists"): "`~/Documents/Rates/rate-card-2026.xlsx` (FY2026)",
    ("compliance.md", "Control frameworks"): "NIST CSF 2.0, PCI DSS v4.0.1, SOX ITGC",
    ("compliance.md", "Data classes"): "Public, Internal, Confidential, Restricted",
    ("compliance.md", "Sign-off"): "information security officer for security policy; data owner for data classes",
    ("changeboard.md", "Cadence"): "Tuesdays 10:00; freeze the last two weeks of December",
    ("changeboard.md", "Lead times"): "normal changes 5 working days; major changes 10",
    ("standards.md", "Engineering standards"): "`~/Documents/Standards/` (the published standards library)",
    ("oneonone.md", "Cadence"): "every two weeks",
    ("oneonone.md", "Manager role"): "director of architecture",
    ("triage.md", "Priority senders"): "my manager, the project managers on my projects",
    ("future-tech.md", "Voting rule"): "simple majority of the architects present, quorum 3",
    ("labs.md", "Approver"): "the infrastructure manager, by role",
    ("poc.md", "Approvers"): "the architecture lead and the sponsor, by role",
    ("estimating.md", "Phase model"): "initiate, design, build, test, deploy, close",
}
TYPE_EXAMPLES = {
    "setup_path": "`~/Documents/...` (a backticked path)",
    "date": "02-Oct-2026",
    "days_text": "14 days",
    "int_text": "3",
    "yesno": "yes",
    "kit_id": "my-kit",
    "quality": "min 3, days 90",
}


def kit_dir(kit=None):
    return ks.kit_dir(kit)


def _agents(kit):
    """{setup file name: [agent names that mention it]} from the live agents (kit/agents), else the shipped ones."""
    dirs = [kit / "agents", kit / ".install/kit/agents", ks.HERE.parent / "kit/agents"]
    d = next((p for p in dirs if p.is_dir() and any(p.glob("*.md"))), None)
    bodies = {}
    for path in sorted(d.glob("*.md")) if d else []:
        text = ks.read_text(path)
        m = re.search(r"^name:\s*(\S+)", text, re.M)
        bodies[m.group(1) if m else path.stem] = text
    return bodies


def _readers(bodies, fname):
    pat = re.compile(rf"(?<![\w.-]){re.escape(fname)}(?![\w-])")
    return sorted(n for n, t in bodies.items() if pat.search(t))


def _question(field, fname):
    topic = fname[:-3].replace("-", " ")
    return f"{field} for {topic}: what should Kit use?"


def _example(fname, field, typ):
    return EXAMPLES.get((fname, field)) or TYPE_EXAMPLES.get(typ[0]) or ""


def questions(kit=None, items=None):
    """Every not-set setup field as a question, highest priority first."""
    kit = kit_dir(kit)
    items = [s for s in (items if items is not None else ks.collect(kit)) if s["kind"] == "setup"]
    bodies = _agents(kit)
    by_file = {}
    for s in items:
        by_file.setdefault(s["source"], []).append(s)
    out = []
    for s in items:
        if s["status"] != "not set" or s["secret"]:
            continue
        fname = pathlib.PurePosixPath(s["source"]).name
        readers = _readers(bodies, fname)
        empty_file = all(x["status"] == "not set" for x in by_file[s["source"]])
        path_field = (fname, s["name"]) in ks.PATH_FIELDS
        prio = "high" if (path_field or empty_file) else "normal"
        why = ("a path the health check reads" if path_field else
               "nothing in this file is set yet" if empty_file else "")
        out.append({
            "id": s["id"], "file": fname, "source": s["source"], "line": s["line"], "field": s["name"],
            "section": s["section"], "agents": readers, "question": _question(s["name"], fname),
            "hint": s["description"], "example": _example(fname, s["name"], s["type"]), "type": s["type"][0],
            "priority": prio, "why": why, "editable": s["editable"], "note": s["note"],
            "expect": ks.fingerprint(s["raw"]),
        })
    out.sort(key=lambda q: (q["priority"] != "high", -len(q["agents"]), q["file"], q["line"] or 0))
    return out


def counts(qs):
    return {"not set": len(qs), "high": sum(q["priority"] == "high" for q in qs),
            "editable": sum(q["editable"] for q in qs), "in a session": sum(not q["editable"] for q in qs)}


# ---- the wizard's state ----------------------------------------------------------------------------------------

def state_path(kit=None):
    return kit_dir(kit) / STATE


def load_state(kit=None):
    try:
        st = json.loads(state_path(kit).read_text(encoding="utf-8"))
        if isinstance(st, dict):
            st.setdefault("later", [])
            st.setdefault("skipped", [])
            return st
    except (OSError, ValueError):
        pass
    return {"later": [], "skipped": [], "new": True}


def save_state(kit, st):
    p = state_path(kit)
    p.parent.mkdir(parents=True, exist_ok=True)
    st = {k: v for k, v in st.items() if k != "new"}
    st["updated"] = dt.datetime.now().isoformat(timespec="minutes")
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(st, indent=1), encoding="utf-8")
    os.replace(str(tmp), str(p))
    return st


def first_run(kit=None):
    """True on a new install: the wizard has never been used here."""
    return not state_path(kit).exists()


def mark(kit, qid, how):
    """Record skip, later, or answered for one question (by id); 'done' closes the wizard; 'reset' brings back the
    questions saved for later."""
    st = load_state(kit)
    for k in ("later", "skipped"):
        st[k] = [x for x in st[k] if x != qid]
    if how == "later":
        st["later"].append(qid)
    elif how == "skip":
        st["skipped"].append(qid)
    elif how == "answered":
        st["answered"] = int(st.get("answered", 0)) + 1
    elif how == "done":
        st["closed"] = True
    elif how == "reset":
        st["later"], st["closed"] = [], False
    elif how == "open":
        st["closed"] = False
    return save_state(kit, st)


def walk(kit=None, items=None):
    """(the questions the wizard walks, in order: editable, not saved for later, skipped ones last; the rest)."""
    st = load_state(kit)
    qs = questions(kit, items)
    later, skipped = set(st["later"]), st["skipped"]
    todo = [q for q in qs if q["editable"] and q["id"] not in later]
    todo.sort(key=lambda q: skipped.index(q["id"]) + 1 if q["id"] in skipped else 0)
    return todo, qs, st


def text_report(qs):
    c = counts(qs)
    if not qs:
        return "No open setup questions: every setup field is set."
    out = [f"{c['not set']} setup field{'s' if c['not set'] != 1 else ''} not set ({c['high']} high priority, "
           f"{c['editable']} answerable here, {c['in a session']} to change in a Claude Code session).",
           "Answer one: kit-settings answer FILE FIELD VALUE   (a preview; add --write to save it)", ""]
    for q in qs:
        who = ", ".join(q["agents"]) if q["agents"] else "no agent names this file"
        out.append(f"[{q['priority']}] {q['file']}: {q['field']}" + (f" ({q['section']})" if q["section"] else ""))
        out.append(f"    {q['question']}  Read by: {who}.")
        if q["hint"]:
            out.append(f"    {q['hint']}")
        if q["example"]:
            out.append(f"    For example: {q['example']}")
        if not q["editable"]:
            out.append(f"    {q['note'] or 'Change it in the file in a Claude Code session.'}")
    return "\n".join(out)


def find_field(kit, fname, field, section=None):
    """The setup setting for FILE FIELD (and SECTION when the field name repeats); raises ks.Refused."""
    fname = pathlib.PurePosixPath(fname.replace("\\", "/")).name
    if not fname.endswith(".md"):
        fname += ".md"
    hits = [s for s in ks.collect(kit) if s["kind"] == "setup" and pathlib.PurePosixPath(s["source"]).name == fname
            and s["name"].lower() == field.lower().rstrip(":")
            and (section is None or s["section"].lower() == section.lower())]
    if not hits:
        raise ks.Refused(f"no field {field!r} in memory/context/{fname}" + (f" under {section!r}" if section else ""))
    if len(hits) > 1:
        raise ks.Refused(f"{field!r} appears more than once in {fname}; say which with --section: "
                         + ", ".join(repr(s["section"]) for s in hits))
    return hits[0]

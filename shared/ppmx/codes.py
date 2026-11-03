"""Labels for the numbers PPM Express uses in coded fields, both ways: numbers to labels when reading,
labels to numbers when writing.

PPM Express returns numbers for statuses, progress, key date type, idea stage, and the rating fields
(priority, risk, cost, and the like). TABLES has the values from PPM Express's Public API article (Help
Center); check them against your tenant (get_fields shows a field's options). A key "Entity.Field"
applies to one kind of record only ("KeyDate.Type"); a plain "Field" applies to every kind; null for an
"Entity.Field" says that kind's field isn't coded at all ("Task.Effort": a task's effort is hours).
Field names match in any case. A deployment can add to or override the tables with a JSON file named by
PPMX_CODES_FILE:

    {"OverallStatus": {"0": "On Track"}, "KeyDate.Type": {"1": "Milestone"}, "Task.Status": {"7": "Blocked"}}

Reading turns a number (1), a number written as text ("1"), or a label written any way ("AtRisk", "at
risk") into the label ("At Risk"). The numbers go to row["codes"], for code that needs them (the pulse);
what a tool returns leaves them out (public()), so people see labels only. A number with no label stays a
number, and row["unlabeled"] lists it so the answer can say how to label it (unlabeled_note()).
"""
import json
import re

STATUS = {0: "On Track", 1: "At Risk", 2: "Critical", 10: "Done", -1: "N/A"}
PROGRESS = {0: "Not Started", 1: "Completed", 2: "In Progress", 3: "On Hold", 4: "Canceled"}
SCALE = {0: "N/A", 1: "Low", 2: "Normal", 3: "Moderate", 4: "Strong", 5: "Extreme"}
TABLES = {
    "OverallStatus": STATUS,                     # projects, programs, portfolios
    "Status": STATUS,                            # tasks, key dates, deliverables
    "Progress": PROGRESS,
    "Priority": SCALE, "Risk": SCALE, "Cost": SCALE, "Effort": SCALE, "Impact": SCALE,
    "Revenue": SCALE, "BusinessPriority": SCALE,
    "Task.Effort": None,                         # hours of work, not a rating
    "Idea.Stage": {0: "Draft", 1: "Proposed", 2: "Active", 3: "Selected", 4: "Not Selected", 5: "Archived"},
    "KeyDate.Type": {0: "Key Date", 1: "Milestone", 2: "Release"},
}
INTERNAL = ("codes", "unlabeled")                # added by decode(); public() takes them out
SPELLINGS = {"cancelled": "canceled"}            # other spellings of a label, as compared (see _key)
NUMBER = re.compile(r"[+-]?\d{1,9}")


class CodesError(Exception):
    pass


def load(path=None):
    """TABLES, with the labels in `path` (when one is given) added and taking precedence."""
    tables = {field: (dict(table) if table is not None else None) for field, table in TABLES.items()}
    if not path:
        return tables
    try:
        with open(path, encoding="utf-8-sig") as f:
            extra = json.load(f)
        for field, table in (extra or {}).items():
            tables[str(field)] = {**(tables.get(str(field)) or {}),
                                  **{int(code): str(label) for code, label in (table or {}).items()}}
    except (OSError, ValueError, TypeError, AttributeError) as e:
        raise CodesError(f"can't use the code tables in {path}: {e.__class__.__name__}") from None
    return tables


def table_for(tables, field, entity=None):
    """A field's labels: the "Entity.Field" table first, then the "Field" one, names matched in any case.
    None when the field isn't coded."""
    if not tables or not field:
        return None
    keys = ([f"{entity}.{field}"] if entity else []) + [field]
    folded = None
    for key in keys:
        if key in tables:
            return tables[key]
        if folded is None:
            folded = {}
            for k in tables:
                folded.setdefault(str(k).casefold(), k)
        if key.casefold() in folded:
            return tables[folded[key.casefold()]]
    return None


def _key(text):
    """A label as compared: any case, without spaces or punctuation ("N/A" and "NA", "On Track" and
    "OnTrack")."""
    key = re.sub(r"[^0-9a-z]", "", str(text).casefold())
    return SPELLINGS.get(key, key)


def code_of(value, table):
    """(code, is_number) for a coded field's value: a number, a number written as text, or a label the
    table has (any case, spaces or not). (None, False) for anything else (other text, dates, lists)."""
    if isinstance(value, bool):
        return None, False
    if isinstance(value, int):
        return value, True
    if isinstance(value, str):
        text = value.strip()
        if NUMBER.fullmatch(text):
            return int(text), True
        key = _key(text)
        if key:
            for code, label in table.items():
                if _key(label) == key:
                    return code, False
    return None, False


def decode(row, tables, entity=None):
    """The row with each coded field's value replaced by its label; the numbers go to row["codes"], and a
    number the tables have no label for stays as it is and is listed in row["unlabeled"]."""
    if not tables:
        return row
    out = dict(row)
    found = dict(row.get("codes") or {}) if isinstance(row.get("codes"), dict) else {}
    missing = {}
    for field, value in row.items():
        if field in INTERNAL or field == "id":
            continue
        table = table_for(tables, field, entity)
        if not table:
            continue
        code, is_number = code_of(value, table)
        if code is None:
            continue
        if code in table:
            found[field] = code
            out[field] = table[code]
        elif is_number:
            missing[field] = code
    if found:
        out["codes"] = found
    if missing:
        out["unlabeled"] = missing
    return out


def public(row):
    """A record as a tool returns it: labels, without the numbers decode() keeps for Kit's own use."""
    if not isinstance(row, dict):
        return row
    return {k: v for k, v in row.items() if k not in INTERNAL}


def unlabeled_note(rows, entity=None):
    """What to say about codes with no label in ROWS (decoded rows, or {"unlabeled": ...} parts): which
    ones, and how to label them. None when every code had a label."""
    seen = {}
    for row in rows:
        for field, code in ((row or {}).get("unlabeled") or {}).items():
            seen.setdefault(field, set()).add(code)
    if not seen:
        return None
    which = "; ".join(f"{field} {', '.join(str(c) for c in sorted(codes))}" for field, codes in sorted(seen.items()))
    field, codes = sorted(seen.items())[0]
    example = json.dumps({f"{entity}.{field}" if entity else field: {str(min(codes)): "<its label>"}})
    return (f"No label for {which}, so it shows as a number: PPM Express's published codes don't have it (a "
            f"status your tenant added, perhaps). To label it, add it to the code tables file that "
            f"PPMX_CODES_FILE names, like {example}; get_fields shows the field's options.")


def encode(field, value, tables, entity=None):
    """The number to send for a coded field given its label, written any way ("In Progress", "inprogress"
    -> 2), or a number written as text ("2" -> 2). Anything else goes as it is: PPM Express takes some
    labels itself and says what it doesn't accept."""
    table = table_for(tables or {}, field, entity)
    if not table or not isinstance(value, str):
        return value
    code, _ = code_of(value, table)
    return value if code is None else code

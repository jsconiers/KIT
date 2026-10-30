"""Labels for the numbers PPM Express uses in coded fields, both ways: numbers to labels when reading,
labels to numbers when writing.

PPM Express returns numbers for statuses, progress, key date type, idea stage, and the rating fields
(priority, risk, cost, and the like). TABLES has the values from PPM Express's Public API article (Help
Center); check them against your tenant (get_fields shows a field's options). A key "Entity.Field"
applies to one kind of record only ("KeyDate.Type"); a plain "Field" applies to every kind. A deployment
can add to or override the tables with a JSON file named by PPMX_CODES_FILE:

    {"OverallStatus": {"0": "On Track"}, "KeyDate.Type": {"1": "Milestone"}}
"""
import json

STATUS = {0: "On Track", 1: "At Risk", 2: "Critical", 10: "Done", -1: "N/A"}
PROGRESS = {0: "Not Started", 1: "Completed", 2: "In Progress", 3: "On Hold", 4: "Canceled"}
SCALE = {0: "N/A", 1: "Low", 2: "Normal", 3: "Moderate", 4: "Strong", 5: "Extreme"}
TABLES = {
    "OverallStatus": STATUS,                     # projects, programs, portfolios
    "Status": STATUS,                            # tasks, key dates, deliverables
    "Progress": PROGRESS,
    "Priority": SCALE, "Risk": SCALE, "Cost": SCALE, "Effort": SCALE, "Impact": SCALE,
    "Revenue": SCALE, "BusinessPriority": SCALE,
    "Idea.Stage": {0: "Draft", 1: "Proposed", 2: "Active", 3: "Selected", 4: "Not Selected", 5: "Archived"},
    "KeyDate.Type": {0: "Key Date", 1: "Milestone", 2: "Release"},
}


class CodesError(Exception):
    pass


def load(path=None):
    """TABLES, with the labels in `path` (when one is given) added and taking precedence."""
    tables = {field: dict(table) for field, table in TABLES.items()}
    if not path:
        return tables
    try:
        with open(path, encoding="utf-8-sig") as f:
            extra = json.load(f)
        for field, table in (extra or {}).items():
            tables[str(field)] = {**tables.get(str(field), {}),
                                  **{int(code): str(label) for code, label in (table or {}).items()}}
    except (OSError, ValueError, TypeError, AttributeError) as e:
        raise CodesError(f"can't use the code tables in {path}: {e.__class__.__name__}") from None
    return tables


def table_for(tables, field, entity=None):
    if entity and f"{entity}.{field}" in tables:
        return tables[f"{entity}.{field}"]
    return tables.get(field)


def decode(row, tables, entity=None):
    """The row with each coded field's number replaced by its label; the numbers move to row["codes"]."""
    if not tables:
        return row
    out, codes = dict(row), {}
    for field, value in row.items():
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        table = table_for(tables, field, entity)
        if table and value in table:
            codes[field] = value
            out[field] = table[value]
    if codes:
        out["codes"] = codes
    return out


def encode(field, value, tables, entity=None):
    """The number to send for a coded field given its label ("In Progress" -> 2) or a number written as
    text ("2" -> 2). Anything else goes as it is: PPM Express takes some labels itself and says what
    it doesn't accept."""
    table = table_for(tables or {}, field, entity)
    if not table or not isinstance(value, str):
        return value
    text = value.strip()
    if text.lstrip("-").isdigit():
        return int(text)
    for code, label in table.items():
        if label.lower() == text.lower():
            return code
    return value

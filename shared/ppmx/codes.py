"""Plain labels for the numbers PPM Express returns in coded fields.

PPM Express takes text when writing but returns numbers for statuses, progress, key date type, idea
stage, and the rating fields (priority, risk, cost, and the like). Its API page has the mapping tables.

STUB: TABLES is empty until it's filled in from that page (or from the tenant's Fields feed); until
then coded values pass through as numbers. A deployment can also supply tables in a JSON file named by
PPMX_CODES_FILE, which adds to (and overrides) TABLES:

    {"OverallStatus": {"0": "Not set", "1": "On track"}, "Stage": {"0": "Draft"}}
"""
import json

TABLES = {
    # "FieldName": {0: "Label", 1: "Label"},      filled in from PPM Express's API page
}


class CodesError(Exception):
    pass


def load(path=None):
    """TABLES, plus the tables in `path` when one is given."""
    tables = {field: dict(table) for field, table in TABLES.items()}
    if not path:
        return tables
    try:
        with open(path, encoding="utf-8-sig") as f:
            extra = json.load(f)
        for field, table in (extra or {}).items():
            tables[str(field)] = {int(code): str(label) for code, label in (table or {}).items()}
    except (OSError, ValueError, TypeError, AttributeError) as e:
        raise CodesError(f"can't use the code tables in {path}: {e.__class__.__name__}") from None
    return tables


def decode(row, tables):
    """The row with each coded field's number replaced by its label; the numbers move to row["codes"]."""
    if not tables:
        return row
    out, codes = dict(row), {}
    for field, table in tables.items():
        value = out.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        if value in table:
            codes[field] = value
            out[field] = table[value]
    if codes:
        out["codes"] = codes
    return out

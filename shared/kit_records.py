#!/usr/bin/env python3
"""kit_records: shared Kit record helpers used by bin/kit-publish and team_dashboard.py.

  load_schemas()            {type: {major: (version, schema)}} from shared/records/schema/
  validate(record, schemas) list of problems; empty means valid
  secret_hits(text)         names of credential patterns found in text
  accept(record, schemas)   (ok, warning) with the version rules readers use (current and previous major)

The validator covers the JSON Schema subset the record schemas use: type, enum, const, pattern,
minLength, maxLength, minimum, maxItems, items, properties, required, additionalProperties
(boolean or schema), allOf, $ref to a sibling file, and format date or date-time.
Record formats and the versioning rule are in shared/records/README.md.
"""
import datetime as dt
import json
import pathlib
import re

SCHEMA_DIR = pathlib.Path(__file__).resolve().parent / "records" / "schema"
TYPES = ("status-snapshot", "decision", "lesson", "artifact-pointer", "demand-rollup", "handoff-pointer",
         "expertise")
# Record types kit-publish produces are TYPES; message records are written only by kit-team send.
MESSAGE_TYPES = ("message",)
ALL_TYPES = TYPES + MESSAGE_TYPES

# Credential-shaped text. Anything matching blocks the whole record from publishing.
SECRET_PATTERNS = [
    (r"\bgh[pousr]_[A-Za-z0-9]{20,}", "GitHub token"),
    (r"\bgithub_pat_[A-Za-z0-9_]{20,}", "GitHub token"),
    (r"\bsk-[A-Za-z0-9_-]{20,}", "API key"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS key"),
    (r"\bxox[abprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"\bAIza[0-9A-Za-z_-]{30,}", "Google API key"),
    (r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.", "JWT"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key"),
    (r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}", "bearer token"),
    (r"(?i)\b(pass(word|wd|phrase)?|pwd|secret|api[_ -]?key|access[_ -]?key|"
     r"client[_ -]?secret|token)\s*[:=]\s*\S{4,}", "credential assignment"),
    (r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@", "password in a URL"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "Social Security number"),
    (r"\b\d{12,19}\b", "account or card number"),
]


def secret_hits(text):
    return sorted({what for pat, what in SECRET_PATTERNS if re.search(pat, text)})


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(s):
    """ISO 8601 date-time to an aware datetime, or None."""
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def split_version(v):
    try:
        major, minor = (int(x) for x in str(v).split("."))
        return major, minor
    except ValueError:
        return None


def load_schemas(folder=SCHEMA_DIR):
    """Current schemas are <type>.schema.json; a kept previous major is <type>.v<major>.schema.json."""
    out = {}
    for f in sorted(folder.glob("*.schema.json")):
        name = f.name[:-len(".schema.json")]
        t = re.sub(r"\.v\d+$", "", name)
        if t not in ALL_TYPES:
            continue
        sch = json.loads(f.read_text())
        ver = split_version(sch.get("x-kit-version", ""))
        if ver:
            out.setdefault(t, {})[ver[0]] = (ver, sch)
    return out


def _type_ok(value, want):
    kinds = want if isinstance(want, list) else [want]
    for k in kinds:
        if (k == "string" and isinstance(value, str)) or (k == "null" and value is None) \
                or (k == "boolean" and isinstance(value, bool)) \
                or (k == "integer" and isinstance(value, int) and not isinstance(value, bool)) \
                or (k == "number" and isinstance(value, (int, float)) and not isinstance(value, bool)) \
                or (k == "array" and isinstance(value, list)) or (k == "object" and isinstance(value, dict)):
            return True
    return False


def _format_ok(value, fmt):
    if not isinstance(value, str):
        return True
    if fmt == "date":
        try:
            dt.date.fromisoformat(value)
            return len(value) == 10
        except ValueError:
            return False
    if fmt == "date-time":
        return "T" in value and parse_iso(value) is not None
    return True


def _check(value, sch, path, folder, lenient, problems):
    if "$ref" in sch:
        _check(value, json.loads((folder / sch["$ref"]).read_text()), path, folder, lenient, problems)
    for sub in sch.get("allOf", []):
        _check(value, sub, path, folder, lenient, problems)
    where = path or "record"
    if "type" in sch and not _type_ok(value, sch["type"]):
        problems.append(f"{where}: expected {sch['type']}")
        return
    if "const" in sch and value != sch["const"]:
        problems.append(f"{where}: must be {sch['const']!r}")
    if "enum" in sch and value not in sch["enum"]:
        problems.append(f"{where}: {value!r} is not one of {sch['enum']}")
    if isinstance(value, str):
        if len(value) < sch.get("minLength", 0):
            problems.append(f"{where}: too short")
        if "maxLength" in sch and len(value) > sch["maxLength"]:
            problems.append(f"{where}: longer than {sch['maxLength']}")
        if "pattern" in sch and not re.search(sch["pattern"], value):
            problems.append(f"{where}: doesn't match the required pattern")
    if "format" in sch and not _format_ok(value, sch["format"]):
        problems.append(f"{where}: not a valid {sch['format']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value < sch.get("minimum", value):
        problems.append(f"{where}: below {sch['minimum']}")
    if isinstance(value, list):
        if "maxItems" in sch and len(value) > sch["maxItems"]:
            problems.append(f"{where}: more than {sch['maxItems']} items")
        for i, v in enumerate(value):
            if "items" in sch:
                _check(v, sch["items"], f"{where}[{i}]", folder, lenient, problems)
    if isinstance(value, dict):
        props = sch.get("properties", {})
        for k in sch.get("required", []):
            if k not in value:
                problems.append(f"{where}: missing {k}")
        extra = sch.get("additionalProperties", True)
        for k, v in value.items():
            sub = f"{path}.{k}" if path else k
            if k in props:
                _check(v, props[k], sub, folder, lenient, problems)
            elif extra is False and not lenient:
                problems.append(f"{where}: unexpected field {k}")
            elif isinstance(extra, dict):
                _check(v, extra, sub, folder, lenient, problems)


def validate(record, schemas, lenient=False, folder=SCHEMA_DIR):
    """Check a record against its type's schema for the record's major version.

    lenient ignores unknown fields, for records written under a newer minor version.
    """
    if not isinstance(record, dict):
        return ["record: not a JSON object"]
    t, ver = record.get("schema"), split_version(record.get("schema_version", ""))
    if t not in schemas:
        return [f"schema: unknown record type {t!r}"]
    if not ver or ver[0] not in schemas[t]:
        return [f"schema_version: no {t} schema for version {record.get('schema_version')!r}"]
    problems = []
    _check(record, schemas[t][ver[0]][1], "", folder, lenient, problems)
    kit, rid = record.get("kit_id"), record.get("id", "")
    if isinstance(rid, str) and not rid.startswith(f"{kit}:{t}:"):
        problems.append("id: must start with <kit_id>:<schema>:")
    return problems


def accept(rec, schemas):
    """(ok, warning or ''). Current and previous majors are accepted; a newer minor is read leniently."""
    t, ver = rec.get("schema"), split_version(rec.get("schema_version", ""))
    if t not in schemas or not ver:
        return False, f"unknown record type or version ({t!r} {rec.get('schema_version')!r})"
    current = max(schemas[t])
    (cmaj, cmin), _ = schemas[t][current]
    if ver[0] > cmaj:
        return False, f"{t} {ver[0]}.{ver[1]} is newer than this dashboard ({cmaj}.{cmin}); update it"
    if ver[0] < cmaj - 1:
        return False, f"{t} {ver[0]}.{ver[1]} is too old (this dashboard reads {cmaj - 1}.x and {cmaj}.x)"
    if ver[0] not in schemas[t]:
        return False, f"{t} {ver[0]}.{ver[1]}: no schema kept for that major version"
    known_minor = schemas[t][ver[0]][0][1]
    lenient = ver[1] > known_minor
    problems = validate(rec, schemas, lenient=lenient)
    if problems:
        return False, "invalid: " + "; ".join(problems[:3])
    if lenient:
        return True, f"{t} {ver[0]}.{ver[1]} is newer than {ver[0]}.{known_minor}; extra fields ignored"
    if ver[0] < cmaj:
        return True, f"{t} {ver[0]}.{ver[1]} is the previous major version; ask its Kit to update"
    return True, ""


def current_version(schemas, t, default="1.0"):
    """The current schema version string for record type t (what a publisher stamps)."""
    try:
        (maj, mi), _ = schemas[t][max(schemas[t])]
        return f"{maj}.{mi}"
    except (KeyError, ValueError):
        return default

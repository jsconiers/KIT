#!/usr/bin/env python3
"""Live test of the SQL transport against a real database. Not part of the regular suites (it
needs a server): run it by hand with python3 tests/live/test_sql_live.py.

It reads Kit's own memory/context/sharing-db.json (or KIT_DIR), creates the database and tables if
missing, then uses two test Kit ids (sqltest-a, sqltest-b) to check publishing, reading across Kits,
write isolation, the organization profile, messages and acks, and tamper detection. It removes its
test rows at the end. The credential is read from the named Keychain entry or variable and never
printed. Needs "sql" in the organization profile's allowed transports.
"""
import sys, pathlib, json, datetime as dt
SH = pathlib.Path(__file__).resolve().parents[2] / "shared"
sys.path.insert(0, str(SH))
import kit_records as kr, kit_transport as kt, kit_sql_transport as ks
import os
KIT = pathlib.Path(os.environ.get("KIT_DIR", pathlib.Path.home() / "Claude/Agents/kit"))
ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    ok += bool(cond); fail += (not cond)
    print(("ok  " if cond else "FAIL"), name, ("" if cond else detail))

s = ks.load_settings(KIT)
schemas = kr.load_schemas()
# 1. Kit creates its database and tables (kit-team db-init uses the same call)
tables = ks.SQLTransport(s).init_schema()
check("database and tables created", set(["kits","records","messages","acks"]) <= set(tables), tables)

def rec(kit, local, title):
    stamp = kr.now_iso()
    return {"schema": "lesson", "schema_version": kr.current_version(schemas, "lesson"),
            "id": f"{kit}:lesson:{local}", "kit_id": kit, "owner_role": "solutions architect", "project": "general",
            "created": stamp, "updated": stamp, "classification": "internal", "source": "kit:lessons/x.md",
            "body": {"title": title, "rule": title + ".", "why": "Test.", "how_to_apply": "Test."}}

A = ks.SQLTransport(s, kit_id="sqltest-a"); B = ks.SQLTransport(s, kit_id="sqltest-b")
try:
    one = rec("sqltest-a", "one", "Check dates first")
    ref, w = A.publish(one); A.finish()
    check("kit A publishes a record", w, ref)
    ref2, w2 = A.publish(dict(one)); A.finish()
    check("republishing an unchanged record writes nothing", not w2)
    B.publish(rec("sqltest-b", "two", "Name roles not people")); B.finish()
    recs, warns = B.scan(schemas)
    ids = {r["id"] for r, _ in recs}
    check("kit B reads both Kits' records", {"sqltest-a:lesson:one", "sqltest-b:lesson:two"} <= ids, (ids, warns))
    try:
        B.publish(rec("sqltest-a", "forged", "Forged")); check("kit B can't write kit A's record", False)
    except kt.TransportError as ex:
        check("kit B can't write kit A's record", "belongs to" in str(ex), str(ex))
    conf = rec("sqltest-a", "secret", "Confidential one"); conf["classification"] = "confidential"
    try:
        A.publish(conf); check("policy refuses confidential over sql", False)
    except kt.TransportError as ex:
        check("policy refuses confidential over sql", "organization profile" in str(ex), str(ex))
    exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=3)).replace(microsecond=0).isoformat().replace("+00:00","Z")
    stamp = kr.now_iso()
    msg = {"schema": "message", "schema_version": "1.0", "id": "sqltest-a:message:m1", "kit_id": "sqltest-a",
           "owner_role": "solutions architect", "project": "general", "created": stamp, "updated": stamp,
           "classification": "internal", "source": "kit:messages/m1",
           "body": {"from_kit": "sqltest-a", "to": ["sqltest-b"], "subject": "Review moved", "text": "Heads up.",
                    "kind": "info", "expires": exp}}
    sent = A.send_message(msg, schemas); A.finish()
    check("kit A sends a message", bool(sent), sent)
    inbox = B.inbox(schemas)
    items = inbox[0] if isinstance(inbox, tuple) else inbox
    check("kit B sees the message in its inbox", any("m1" in json.dumps(x, default=str) for x in items), inbox)
    names = [x["name"] for x in items if isinstance(x, dict) and "name" in x]
    try:
        B.ack(names[0]); B.finish()
        acks = A.acks_from("sqltest-b")
        check("kit B acknowledges it, and kit A sees the ack", acks.get(names[0]) == "seen", acks)
    except Exception as ex:
        check("kit B acknowledges it", False, repr(ex))
    # tamper detection: change a row's JSON behind the adapter's back
    A._exec("UPDATE records SET json = REPLACE(json, 'Check dates first', 'Tampered') WHERE kit_id = ? AND local_id = ?",
            ("sqltest-a", "one")); A.finish()
    recs, warns = B.scan(schemas)
    check("a tampered row is detected and skipped", any(wk == "tampered" for wk, *_ in warns) and
          "sqltest-a:lesson:one" not in {r["id"] for r, _ in recs}, warns)
finally:
    for t, col in [("acks","by_kit"), ("messages","from_kit"), ("records","kit_id"), ("kits","kit_id")]:
        A._exec(f"DELETE FROM {t} WHERE {col} IN (?, ?)", ("sqltest-a", "sqltest-b"))
    A.finish(); A.close(); B.close()
    print("test rows removed")
print(f"live MySQL test: {ok} passed, {fail} failed")

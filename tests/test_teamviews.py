#!/usr/bin/env python3
"""Tests for the team load view and the expertise finder (shared/kit_teamviews.py, kit-team load and
experts, the team dashboard's Team load panel, kit-publish's kind/stage/opened and expertise records).
Three fake Kits share one temporary folder. Run: python3 tests/test_teamviews.py [load|experts|all]"""
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
os.environ["KIT_DIR"] = tempfile.mkdtemp(prefix="kit-teamviews-test-")
sys.path.insert(0, str(REPO / "shared"))
import kit_records as kr  # noqa: E402
import kit_teamviews as tv  # noqa: E402
import kit_transport as kt  # noqa: E402

PASS, FAIL = 0, 0
TODAY = dt.date.today()


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


def d(days):
    return (TODAY + dt.timedelta(days=days)).isoformat()


def rec(kit, typ, local, body, role="solutions architect", project="general", updated=None, version=None):
    stamp = (updated or kr.now_iso())
    return {"schema": typ, "schema_version": version or kr.current_version(SCHEMAS, typ), "id": f"{kit}:{typ}:{local}",
            "kit_id": kit, "owner_role": role, "project": project, "created": stamp, "updated": stamp,
            "classification": "internal", "source": "kit:x.md", "body": body}


def item(num, title, status="in progress", due=None, kind=None, stage=None, opened=None, open_=True):
    i = {"number": num, "title": title, "status": status, "role": "architect", "due": due, "open": open_}
    if kind:
        i["kind"] = kind
    if stage:
        i["stage"] = stage
    if opened:
        i["opened"] = opened
    return i


def rollup(items):
    return {"as_of": d(0), "total": len(items), "open": sum(i["open"] for i in items),
            "by_status": {"in progress": len(items)}, "items": items}


def run(*args, env=None):
    e = dict(os.environ, **(env or {}))
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, env=e)


def test_load(tmp, kit_env):
    # schema compatibility
    old = rec("kit-alpha", "demand-rollup", "p1", rollup([{"number": "D-1", "title": "x", "status": "new",
                                                           "role": "a", "due": None, "open": True}]), version="1.0")
    check("1.0 demand roll-up still valid", not kr.validate(old, SCHEMAS), kr.validate(old, SCHEMAS))
    new = rec("kit-alpha", "demand-rollup", "p1", rollup([item("IA-7", "Kafka IA", kind="ia", stage="draft",
                                                                opened=d(-40), due=d(-2))]))
    check("1.1 roll-up with kind, stage, opened is valid", not kr.validate(new, SCHEMAS), kr.validate(new, SCHEMAS))
    check("kit-publish stamps the type's current version", new["schema_version"] == "1.1")
    bad = rec("kit-alpha", "demand-rollup", "p1", rollup([item("X", "y", kind="epic")]))
    check("unknown kind refused", bool(kr.validate(bad, SCHEMAS)))
    ok, warn = kr.accept(dict(new, schema_version="1.9"), SCHEMAS)
    check("a newer minor is read leniently", ok and "newer" in warn, warn)

    # load view
    alpha = [item("IA-7", "Kafka IA", kind="ia", stage="draft", opened=d(-40), due=d(-2)),
             item("GDS-3", "Kafka GDS", kind="gds", stage="review", opened=d(-10), due=d(5)),
             item("D-11", "New demand", opened=d(-3), due=d(20)),
             item("D-12", "Closed one", status="closed", open_=False)]
    bravo = [item(f"D-{n}", f"Demand {n}", due=None) for n in range(9)] + [item("POC-1", "Mesh POC", kind="poc")]
    recs = [rec("kit-alpha", "demand-rollup", "proj-a", rollup(alpha), role="solutions architect", project="proj-a"),
            rec("kit-bravo", "demand-rollup", "proj-b", rollup(bravo), role="network architect", project="proj-b")]
    view = tv.load_view(recs, threshold=8, today=TODAY)
    by = {k["kit_id"]: k for k in view}
    check("one row per Kit", set(by) == {"kit-alpha", "kit-bravo"})
    a, b = by["kit-alpha"], by["kit-bravo"]
    check("closed items don't count", a["open"] == 3, a["open"])
    check("by kind", a["by_kind"]["ia"] == 1 and a["by_kind"]["gds"] == 1 and a["by_kind"]["demand"] == 1, a["by_kind"])
    check("by stage (stage, else status)", a["by_stage"].get("draft") == 1 and a["by_stage"].get("in progress") == 1,
          a["by_stage"])
    check("due windows", a["due"]["overdue"] == 1 and a["due"]["7 days"] == 1 and a["due"]["30 days"] == 1, a["due"])
    check("aging max and median", a["aging"]["max_days"] == 40 and a["aging"]["median_days"] == 10, a["aging"])
    check("items with no opened date counted as unknown age", b["aging"]["unknown"] == 10, b["aging"])
    check("overload flag at the threshold", b["overloaded"] and not a["overloaded"])
    check("ordered by open count", view[0]["kit_id"] == "kit-bravo")
    check("POC kind counted", b["by_kind"]["poc"] == 1)
    check("by role, never a name", a["owner_role"] == "solutions architect" and "name" not in json.dumps(view))

    # threshold from sharing.md
    kd = pathlib.Path(kit_env["KIT_DIR"])
    (kd / "memory/context").mkdir(parents=True, exist_ok=True)
    (kd / "memory/context/sharing.md").write_text("- **Overload threshold:** 3. Open items per Kit.\n")
    check("threshold read from sharing.md", tv.overload_threshold(kd) == 3)
    (kd / "memory/context/sharing.md").write_text("- **Overload threshold:** not set.\n")
    check("default threshold 8", tv.overload_threshold(kd) == 8)

    # kit-team load and the dashboard, through a shared folder and the cache
    shared = tmp / "shared"
    for kit, r in (("kit-alpha", recs[0]), ("kit-bravo", recs[1])):
        t = kt.FolderTransport(shared, kit, "shared")
        t.publish(r)
        t.finish()
    env = dict(kit_env, KIT_SHARED_ROOT=str(shared), KIT_TRANSPORT="folder")
    cache = tmp / "team.db"
    r = run(REPO / "shared/bin/kit-team", "sync", "--cache", cache, env=env)
    check("kit-team sync", r.returncode == 0, r.stderr)
    r = run(REPO / "shared/bin/kit-team", "load", "--cache", cache, "--threshold", "8", env=env)
    check("kit-team load table", r.returncode == 0 and "kit-bravo" in r.stdout and "overloaded" in r.stdout,
          r.stdout + r.stderr)
    r = run(REPO / "shared/bin/kit-team", "load", "--cache", cache, "--json", env=env)
    j = json.loads(r.stdout) if r.returncode == 0 else {}
    check("kit-team load --json", j.get("threshold") == 8 and len(j.get("kits", [])) == 2, r.stderr)
    out = tmp / "team.html"
    r = run(REPO / "shared/team_dashboard.py", "--cache", cache, "--no-sync", "--out", out, env=env)
    page = out.read_text() if out.exists() else ""
    check("dashboard has the Team load panel", r.returncode == 0 and "Team load" in page and "kit-bravo" in page
          and "overloaded" in page, r.stdout + r.stderr)

    # kit-publish: kind from a column or the number's prefix, stage, opened
    kit = tmp / "pubkit"
    lib = tmp / "lib"
    (kit / "memory/context").mkdir(parents=True)
    (lib / "demands").mkdir(parents=True)
    (kit / "memory/context/sharing.md").write_text(
        "- **Kit id:** kit-charlie\n- **Owner role:** data architect\n- **Publish:** demand-rollup\n")
    (kit / "memory/context/library.md").write_text(f"- **Library root:** `{lib}`\n")
    (kit / "memory/context/demands.md").write_text("- **Register:** `demands/REGISTER.md`\n")
    (lib / "demands/REGISTER.md").write_text(
        "| Number | Title | Status | Role | Due | Project | Checked | Kind | Stage | Opened |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
        f"| DMND-1 | Storage refresh | new | architect | {d(10)} | proj-c | {d(0)} |  | intake | {d(-5)} |\n"
        f"| IA-7 | Storage IA | drafting | architect | {d(3)} | proj-c | {d(0)} |  |  |  |\n"
        f"| 77 | Mesh trial | assess | architect |  | proj-c | {d(0)} | Proof of concept |  |  |\n")
    outbox = tmp / "outbox"
    r = run(REPO / "shared/bin/kit-publish", "--kit-dir", kit, "--outbox", outbox,
            env=dict(kit_env, KIT_DIR=str(kit)))
    files = list(outbox.rglob("demand-rollup/*.json"))
    body = json.loads(files[0].read_text())["body"] if files else {}
    kinds = {i["number"]: i.get("kind") for i in body.get("items", [])}
    check("kit-publish wrote a roll-up", r.returncode == 0 and files, r.stdout + r.stderr)
    check("kind from the number's prefix and the Kind column",
          kinds == {"DMND-1": "demand", "IA-7": "ia", "77": "poc"}, kinds)
    first = [i for i in body.get("items", []) if i["number"] == "DMND-1"]
    check("stage and opened carried", first and first[0].get("stage") == "intake" and first[0].get("opened") == d(-5),
          first)
    v = json.loads(files[0].read_text())["schema_version"] if files else ""
    check("published roll-up stamped 1.1", v == "1.1", v)


def test_experts(tmp, kit_env):
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=730)).replace(microsecond=0).isoformat()
    old = old.replace("+00:00", "Z")
    recs = [
        rec("kit-alpha", "decision", "kafka-adopt", {"title": "Adopt Kafka for trade events", "decided": d(-20),
            "status": "current", "summary": "Kafka replaces the old bus", "options": ["Kafka", "MQ"],
            "why": "throughput", "revisit": "", "sources": [], "origin": "decision-record"}),
        rec("kit-alpha", "artifact-pointer", "gds-kafka", {"accession": "LIB-1", "doc_number": "DS-9",
            "title": "Kafka platform design", "type": "GDS", "status": "published", "version": "1.0",
            "last_update": d(-30), "path": "x.pdf"}),
        rec("kit-bravo", "lesson", "kafka-lesson", {"title": "Size Kafka partitions early",
            "rule": "Plan partitions up front.", "why": "Rebalancing hurts.", "how_to_apply": "Estimate first."},
            role="network architect", updated=old),
        rec("kit-charlie", "expertise", "profile", {"as_of": d(0), "topics": [
            {"topic": "Kafka", "level": "expert", "evidence": ["kit-charlie:decision:x"]}]}, role="data architect"),
        rec("kit-delta", "lesson", "dns", {"title": "DNS TTLs", "rule": "Lower TTL before cutover.",
            "why": "Caches.", "how_to_apply": "A day ahead."}, role="network architect"),
    ]
    for r in recs:
        check(f"fixture {r['id']} valid", not kr.validate(r, SCHEMAS), kr.validate(r, SCHEMAS))
    ranked = tv.experts(recs, "kafka", today=TODAY)
    ids = [k["kit_id"] for k in ranked]
    check("Kits with evidence ranked first", ids[:2] == ["kit-alpha", "kit-bravo"], ids)
    check("self-declared only comes after evidence", ids[-1] == "kit-charlie" and ranked[-1]["score"] == 0, ranked[-1])
    check("declared level shown, not counted", ranked[-1]["declared"] == "expert" and ranked[-1]["evidence"] == 0)
    a = ranked[0]
    check("evidence counted with citations", a["evidence"] == 2 and
          {c["id"] for c in a["citations"]} == {"kit-alpha:decision:kafka-adopt", "kit-alpha:artifact-pointer:gds-kafka"},
          a)
    check("decision cited before the artifact", a["citations"][0]["type"] == "decision")
    b = ranked[1]
    check("old evidence weighs less (two years: quarter weight)", 0.4 < b["score"] < 0.6, b["score"])
    check("unrelated Kit not listed", "kit-delta" not in ids)
    check("multi-word topic needs every word", [k["kit_id"] for k in tv.experts(recs, "kafka partitions")] ==
          ["kit-bravo"])
    check("no evidence gives an empty list", tv.experts(recs, "mainframe") == [])
    check("by role and Kit id, never names", all(set(k) == {"kit_id", "owner_role", "score", "evidence",
                                                            "citations", "declared"} for k in ranked))

    shared = tmp / "shared-x"
    for r in recs:
        t = kt.FolderTransport(shared, r["kit_id"], "shared")
        t.publish(r)
        t.finish()
    env = dict(kit_env, KIT_SHARED_ROOT=str(shared), KIT_TRANSPORT="folder")
    cache = tmp / "team-x.db"
    run(REPO / "shared/bin/kit-team", "sync", "--cache", cache, env=env)
    r = run(REPO / "shared/bin/kit-team", "experts", "kafka", "--cache", cache, env=env)
    check("kit-team experts lists Kits and cites ids", r.returncode == 0 and "kit-alpha:decision:kafka-adopt" in r.stdout
          and "declares expert" in r.stdout, r.stdout + r.stderr)
    r = run(REPO / "shared/bin/kit-team", "experts", "mainframe", "--cache", cache, env=env)
    check("kit-team experts says no evidence plainly", r.returncode == 0 and "no evidence" in r.stdout, r.stdout)
    r = run(REPO / "shared/bin/kit-team", "experts", "kafka", "--json", "--cache", cache, env=env)
    check("kit-team experts --json", r.returncode == 0 and json.loads(r.stdout)["kits"][0]["kit_id"] == "kit-alpha",
          r.stderr)

    # kit-publish expertise: only when turned on, levels checked
    kit = tmp / "expkit"
    (kit / "memory/context").mkdir(parents=True)
    (kit / "memory/context/expertise.md").write_text(
        "| Topic | Level | Evidence |\n|---|---|---|\n| Kafka | expert | kit-echo:decision:a; DS-9 |\n"
        "| Guessing | guru |  |\n")
    base = "- **Kit id:** kit-echo\n- **Owner role:** integration architect\n"
    for publish, want in (("lesson", 0), ("expertise", 1)):
        (kit / "memory/context/sharing.md").write_text(base + f"- **Publish:** {publish}\n")
        outbox = tmp / f"out-{publish}"
        run(REPO / "shared/bin/kit-publish", "--kit-dir", kit, "--outbox", outbox, env=dict(kit_env, KIT_DIR=str(kit)))
        files = list(outbox.rglob("expertise/*.json"))
        check(f"expertise published only when turned on ({publish})", len(files) == want, files)
        if files:
            body = json.loads(files[0].read_text())["body"]
            check("invalid level skipped, evidence split", body["topics"] == [
                {"topic": "Kafka", "level": "expert", "evidence": ["kit-echo:decision:a", "DS-9"]}], body)


def main():
    global SCHEMAS
    SCHEMAS = kr.load_schemas()
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    tmp = pathlib.Path(tempfile.mkdtemp())
    kit_env = {"KIT_DIR": os.environ["KIT_DIR"]}
    try:
        if which in ("load", "all"):
            test_load(tmp, kit_env)
        if which in ("experts", "all"):
            test_experts(tmp, kit_env)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(os.environ["KIT_DIR"], ignore_errors=True)
    label = {"load": "team load", "experts": "experts"}.get(which, "team views")
    print(f"{label} tests: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

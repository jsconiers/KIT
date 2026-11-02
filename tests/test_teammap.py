#!/usr/bin/env python3
"""Tests for kit-teammap (the team coverage map): the coverage file (add, remove, import, person), loads from the
fake PPM Express (tests/fake_ppmx.py), single points of knowledge with a suggested backup from related expertise
(other systems, PPM Express projects, and the team's shared records in the kit-team cache), the cross-training
plan, and what happens when PPM Express can't be reached. The token is never printed or stored. Nothing reaches
the network, the Keychain, or a real PPM Express.

Run: python3 tests/test_teammap.py
"""
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
SHARED = REPO / "shared"
sys.path[:0] = [str(SHARED), str(HERE)]
import fake_ppmx as F  # noqa: E402

PASS = FAIL = 0
TOKEN = "token-alex-0001"


def ok(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


server, fake, BASE = F.start()
tmp = pathlib.Path(tempfile.mkdtemp())
kit = tmp / "kit"
(kit / ".install/shared/morning").mkdir(parents=True)
CONFIG = kit / ".install/shared/morning/config"
CONFIG.write_text(f'OWNER_NAME="Alex"\nPPMX_BASE_URL="{BASE}"\n')
(kit / "memory/context").mkdir(parents=True)
(kit / "briefs").mkdir()
COVER = kit / "briefs/team/coverage.json"
ENV = {k: v for k, v in os.environ.items() if not k.startswith(("PPMX_", "TEAMMAP_"))}
ENV.update(KIT_DIR=str(kit), PPMX_TOKEN_KEYCHAIN="off", PPMX_TOKEN=TOKEN, PPMX_CACHE_SECONDS="0", KIT_TODAY="2026-11-02",
           PPMX_TODAY="2026-11-02", PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")

# The fake's people: Sam Lee is 130% allocated; Alex appears as "Rivera, Alex" on a task; Dana only by address;
# Blake Chen isn't on the team.
for r in fake.data["resources"]["alex"]:
    if r["attributes"]["Name"] == "Sam Lee":
        r["attributes"]["Allocation"] = 130
tasks = {t["id"]: t for t in fake.data["tasks"][F.A1]}
tasks[F.T3]["attributes"]["AssignedTo"] = "Rivera, Alex"
fake.data["tasks"][F.A1] += [
    F.item("f0000000-0000-4000-8000-000000000005", Name="Runbook review", Status=0, Progress=0,
           AssignedTo={"email": "dana@example.com"}, DueDate="2026-11-20T00:00:00"),
    F.item("f0000000-0000-4000-8000-000000000006", Name="Firmware test", Status=0, Progress=0,
           AssignedTo={"name": "Blake Chen"}, DueDate="2026-11-25T00:00:00")]


def tm(*args, **extra):
    r = subprocess.run([sys.executable, str(SHARED / "bin/kit-teammap"), *map(str, args)], capture_output=True,
                       text=True, encoding="utf-8", timeout=120, env={**ENV, **extra})
    return r.returncode, r.stdout, r.stderr


def mapjson(*args, **extra):
    rc, o, e = tm("--json", *args, **extra)
    try:
        return json.loads(o), o + e
    except ValueError:
        return {}, o + e


# ---- an empty map ------------------------------------------------------------------------------------------------
rc, o, e = tm("coverage")
ok(rc == 0 and "no coverage file yet" in o, "coverage with no file says how to start one")
rc, o, e = tm("--no-ppmx")
ok(rc == 0 and "Nobody yet" in o and "Nothing to check until the coverage file has entries" in o,
   "the map with nothing to read says so", o)

# ---- the coverage file ---------------------------------------------------------------------------------------------
rc, o, e = tm("add", "Payments gateway", "--who", "Alex", "--tags", "payments")
ok(rc == 0 and "added Payments gateway: Alex; nobody else knows it yet" in o, "add a system known by one person", o + e)
tm("add", "Billing API", "--who", "Dana", "--backup", "Alex, Dana", "--tags", "payments, billing")
tm("add", "--who", "Sam Lee", "--tags", "network", "Network", "core")
tm("add", "Mobile app", "--who", "Dana")
rc, o, e = tm("add", "Mobile app", "--who", "Dana", "--tags", "mobile")
ok(rc == 0 and "replaced Mobile app" in o, "adding one that's there replaces it")
cov = json.loads(COVER.read_text(encoding="utf-8"))
ok([s["name"] for s in cov["systems"]] == ["Billing API", "Mobile app", "Network core", "Payments gateway"],
   "the file keeps one entry per system, sorted; options can come before the name", [s["name"] for s in cov["systems"]])
ok([s for s in cov["systems"] if s["name"] == "Billing API"][0]["backup"] == ["Alex"],
   "a backup who is also the primary is dropped")
if os.name != "nt":
    ok(oct(COVER.stat().st_mode)[-3:] == "600" and oct(COVER.parent.stat().st_mode)[-3:] == "700",
       "the coverage file is readable only by you")
rc, o, e = tm("add", "Secret thing", "--who", "Alex", "--tags", "password: hunter2xx")
ok(rc == 1 and "credential" in e, "text that looks like a credential is refused")
rc, o, e = tm("add", "No one")
ok(rc == 2 and "--who" in e, "add needs --who")
imp = tmp / "coverage.csv"
imp.write_text("System,Primary expert,Backup expert,Tags,Kind\n"
               "Mainframe batch,Erin,,cobol,system\n"
               "Data protection,Erin;Alex,,privacy,domain\n"
               "Orphan,,,x,\n"
               ",Nobody,,,\n", encoding="utf-8")
rc, o, e = tm("import", imp)
ok(rc == 0 and "2 added, 0 replaced, 2 row(s) skipped" in o, "import: a Backup expert column isn't taken for Who; rows "
   "with no system or no one named are skipped", o + e)
cov = json.loads(COVER.read_text(encoding="utf-8"))
ok([s for s in cov["systems"] if s["name"] == "Data protection"][0]["kind"] == "domain", "a domain is kept as one")
bad = tmp / "bad.csv"
bad.write_text("Thing,Person\nx,y\n")
rc, o, e = tm("import", bad)
ok(rc == 1 and "needs a System (or Domain) column and a Who column" in e, "import needs System and Who columns", e)
rc, o, e = tm("remove", "nothing", "here")
ok(rc == 1 and "no 'nothing here'" in e, "remove of an unknown system says so")
tm("add", "Temp", "--who", "Alex")
rc, o, e = tm("remove", "temp")
ok(rc == 0 and "removed Temp" in o, "remove, whatever the case")
rc, o, e = tm("person", "Dana", "--kit", "kit-d4n4", "--alias", "D. Diaz")
ok(rc == 0 and "Kit id kit-d4n4" in o, "person: a Kit id for someone", o + e)
rc, o, e = tm("person", "Dana", "--kit", "Not A Kit")
ok(rc == 1 and "isn't a Kit id" in e, "a bad Kit id is refused")
rc, o, e = tm("coverage")
ok(rc == 0 and "Network core [system]: Sam Lee; tags network" in o and "person Dana: Kit id kit-d4n4" in o
   and "[work]" in o, "coverage lists the file", o)

# The people you lead, from kit-feedback's list.
(kit / "feedback").mkdir()
(kit / "feedback/people.json").write_text(json.dumps({"people": [{"name": "Erin Cho", "aliases": ["Erin"]}]}))

# The team's shared records: Dana's Kit declares network; another Kit, not matched to anyone, has a decision on it.
import kit_transport as kt  # noqa: E402
(kit / ".install/cache").mkdir(parents=True)
cache = kt.Cache(kit / ".install/cache/team.db")
for rec in ({"schema": "expertise", "id": "kit-d4n4:expertise:profile", "kit_id": "kit-d4n4",
             "owner_role": "network engineer", "project": "general", "updated": "2026-10-01T00:00:00Z",
             "body": {"as_of": "2026-10-01", "topics": [{"topic": "network", "level": "expert"}]}},
            {"schema": "decision", "id": "kit-x9z9:decision:net-1", "kit_id": "kit-x9z9", "owner_role": "network architect",
             "project": "general", "updated": "2026-09-01T00:00:00Z",
             "body": {"title": "Network segmentation for branch sites", "summary": "Segment branch networks",
                      "why": "blast radius"}}):
    cache.db.execute("INSERT INTO records (id, kit_id, type, project, updated, json) VALUES (?, ?, ?, ?, ?, ?)",
                     (rec["id"], rec["kit_id"], rec["schema"], rec["project"], rec["updated"], json.dumps(rec)))
cache.db.commit()
cache.close()

# ---- the map, with PPM Express ----------------------------------------------------------------------------------------
m, raw = mapjson()
ok(m.get("ppmx", {}).get("reached") and m["ppmx"]["projects"] == 3, "PPM Express is read: three open projects", raw[:600])
people = {p["name"]: p for p in m.get("people", [])}
ok(set(people) == {"Alex", "Dana", "Sam Lee", "Erin"}, "the team: the coverage file and the people you lead "
   "(Erin Cho is Erin)", sorted(people))
ok(m["ppmx"]["others_left_out"] == 1, "someone on the projects who isn't on the team is left out, and counted")
ok(people["Sam Lee"]["load"] == "130% allocated" and people["Sam Lee"]["over"], "allocation from PPM Express; over 100%")
ok(people["Alex"]["load"] == "2 projects, 1 open task" and not people["Alex"]["over"],
   "no allocation: projects and open tasks; \"Rivera, Alex\" and Alex Rivera are Alex", people["Alex"])
ok(people["Dana"]["projects"] == ["Network refresh"] and people["Dana"]["open_tasks"] == 1,
   "an assignee known only by address is matched to Dana")
ok(people["Erin"]["load"] == "nothing open in PPM Express", "someone with nothing open")
ok([x["name"] for x in m["over_limit"]] == ["Sam Lee"], "over the limit: Sam Lee")
sp = {x["system"]: x for x in m["single_points"]}
ok(set(sp) == {"Payments gateway", "Network core", "Mobile app", "Mainframe batch"},
   "single points of knowledge: systems one person knows (a backup or two people take it off)", sorted(sp))
ok(sp["Network core"]["backup"] == "Dana" and any("declares expert" in w for w in sp["Network core"]["why"]),
   "Network core: Dana, related by her shared records and her project, with a lower load than Alex", sp["Network core"])
ok("kit-x9z9 (network architect)" in sp["Network core"]["plan"] and "person NAME --kit" in sp["Network core"]["plan"],
   "a Kit with related records that isn't matched to anyone is named, with how to match it")
ok("over the load limit, so plan the handover time first" in sp["Network core"]["plan"], "the primary is over the limit")
ok(sp["Payments gateway"]["backup"] == "Dana" and "knows Billing API (payments)" in sp["Payments gateway"]["why"][0],
   "Payments gateway: Dana, who knows Billing API (payments)", sp["Payments gateway"])
ok(sp["Mobile app"]["backup"] == "Alex" and "is on Mobile app in PPM Express" in sp["Mobile app"]["why"],
   "Mobile app: Alex, on the Mobile app project", sp["Mobile app"])
ok(sp["Mainframe batch"]["backup"] is None and sp["Mainframe batch"]["plan"].startswith("Pair someone with Erin for a "
                                                                                        "quarter"),
   "no related expertise: pair someone for a quarter", sp["Mainframe batch"])
ok([x["system"] for x in m["single_points"]][0] == "Network core", "the worst gap first: its only person is over the limit")
rc, o, e = tm()
ok(rc == 0 and o.startswith("# Team coverage map, 02-Nov-2026") and "[work]" in o, "the map in Markdown, tagged [work]")
ok("| Sam Lee | 130% allocated (over) |" in o and "## Cross-training plan" in o and "1. **Network core** (only Sam Lee)"
   in o, "who's on what, and the plan", o[:1500])
ok("Network core (only them)" in o and "Billing API (backup)" in o, "what each person knows, and where they're backup")
ok("dana@example.com" not in o and "example.com" not in o, "no address reaches the map")
everything = o + e + raw
ok(TOKEN not in everything, "the token is never printed")
audit = "".join(f.read_text() for f in (kit / "audit").glob("ppmx-*.jsonl"))
ok('"via": "kit-teammap"' in audit and TOKEN not in audit, "the read leaves an audit line, without the token")

rc, o, e = tm("--write")
out = kit / "briefs/teammap-2026-11-02.md"
ok(rc == 0 and out.exists() and "wrote briefs/teammap-2026-11-02.md [work]" in o, "--write saves the map", o + e)
ok(TOKEN not in out.read_text(encoding="utf-8") and TOKEN not in COVER.read_text(encoding="utf-8"),
   "the token isn't in the map or the coverage file")
if os.name != "nt":
    ok(oct(out.stat().st_mode)[-3:] == "600", "the saved map is readable only by you")

# ---- limits from Kit's config ------------------------------------------------------------------------------------------------
CONFIG.write_text(f'PPMX_BASE_URL="{BASE}"\nTEAMMAP_MAX_LOAD="150"\nTEAMMAP_MAX_ITEMS="2"\n')
m, raw = mapjson()
people = {p["name"]: p for p in m.get("people", [])}
ok(not people["Sam Lee"]["over"] and people["Alex"]["over"] and not people["Dana"]["over"],
   "TEAMMAP_MAX_LOAD and TEAMMAP_MAX_ITEMS come from Kit's config", raw[:300])
sp = {x["system"]: x for x in m["single_points"]}
ok(sp["Mobile app"]["backup"] is None and "Alex has related work but is over the load limit" in sp["Mobile app"]["plan"],
   "a related person over the limit isn't suggested; the plan says why", sp["Mobile app"])
CONFIG.write_text(f'OWNER_NAME="Alex"\nPPMX_BASE_URL="{BASE}"\n')

# ---- a first name is one person, and a share is read the same way for the whole tenant ---------------------------
# Alex is on the team by first name only; PPM Express has Alex Rivera and now Alex Chen too.
chen = F.item("f0000000-0000-4000-8000-000000000007", Name="Switch audit", Status=0, Progress=0,
              AssignedTo={"name": "Alex Chen"}, DueDate="2026-11-28T00:00:00")
fake.data["tasks"][F.A1].append(chen)
m, raw = mapjson()
people = {p["name"]: p for p in m.get("people", [])}
ok(people["Alex"]["load"] == "nothing open in PPM Express" and people["Alex"]["projects"] == [],
   "two full names share Alex's first name: neither is counted as Alex", people.get("Alex"))
ok(m["names_to_check"] == [{"name": "Alex", "ppmx_names": ["Alex Chen", "Alex Rivera"]}]
   and m["ppmx"]["others_left_out"] == 3, "the map names both and leaves them out", (m.get("names_to_check"), m["ppmx"]))
rc, o, e = tm()
ok("## Names to check" in o and "- Alex: PPM Express has Alex Chen and Alex Rivera, so none of them was counted as "
   "Alex." in o and 'kit-teammap person Alex --alias "FULL NAME"' in o, "the Markdown says which names to check", o[:1600])
tm("person", "Alex", "--alias", "Alex Rivera")
m, raw = mapjson()
people = {p["name"]: p for p in m.get("people", [])}
ok(people["Alex"]["load"] == "2 projects, 1 open task" and m["names_to_check"] == []
   and m["ppmx"]["others_left_out"] == 2, "once you say which, Alex is Alex Rivera and Alex Chen stays out",
   (people.get("Alex"), m["ppmx"]))
# Sam is on another team's file by first name only; PPM Express has Sam Lee and Sam Ortiz.
alt = tmp / "alt-coverage.json"
rc, o, e = tm("add", "Storage", "--who", "Sam", TEAMMAP_COVERAGE=str(alt))
ok(rc == 0 and alt.exists() and "Storage" not in COVER.read_text(encoding="utf-8"),
   "TEAMMAP_COVERAGE names another coverage file", o + e)
ortiz = F.item("f0000000-0000-4000-8000-000000000008", Name="Storage tiering", Status=0, Progress=0,
               AssignedTo={"name": "Sam Ortiz"}, DueDate="2026-11-28T00:00:00")
fake.data["tasks"][F.A1].append(ortiz)
m, raw = mapjson(TEAMMAP_COVERAGE=str(alt))
people = {p["name"]: p for p in m.get("people", [])}
ok(people["Sam"]["load"] == "nothing open in PPM Express" and m["names_to_check"] == [
    {"name": "Sam", "ppmx_names": ["Sam Lee", "Sam Ortiz"]}], "Sam takes neither Sam Lee nor Sam Ortiz",
   (people.get("Sam"), m.get("names_to_check")))
fake.data["tasks"][F.A1].remove(ortiz)
m, raw = mapjson(TEAMMAP_COVERAGE=str(alt))
people = {p["name"]: p for p in m.get("people", [])}
ok(people["Sam"]["load"] == "130% allocated" and people["Sam"]["projects"] == ["Data center exit", "Network refresh"]
   and m["names_to_check"] == [], "with one full name only, Sam is Sam Lee", people.get("Sam"))
tm("add", "Backups", "--who", "Alex", TEAMMAP_COVERAGE=str(alt))
tm("add", "Firewalls", "--who", "Alex Rivera", TEAMMAP_COVERAGE=str(alt))
m, raw = mapjson(TEAMMAP_COVERAGE=str(alt))
people = {p["name"]: p for p in m.get("people", [])}
ok(people["Alex Rivera"]["load"] == "2 projects, 1 open task" and people["Alex"]["load"] == "nothing open in PPM "
   "Express" and {"name": "Alex", "ppmx_names": ["Alex Chen", "Alex Rivera"]} in m["names_to_check"],
   "with Alex Rivera on the team too, Alex doesn't take Alex Chen as the one left over",
   (people.get("Alex"), people.get("Alex Rivera"), m.get("names_to_check")))
# Shares: 1.0 and 0.6 in one tenant are 100% and 60%; next to 130, 1.0 is 1%.
res = {r["attributes"]["Name"]: r["attributes"] for r in fake.data["resources"]["alex"]}
res["Sam Lee"]["Allocation"], res["Alex Rivera"]["Allocation"] = 1.0, 0.6
m, raw = mapjson()
people = {p["name"]: p for p in m.get("people", [])}
ok(people["Sam Lee"]["load"] == "100% allocated" and not people["Sam Lee"]["over"]
   and people["Alex"]["load"] == "60% allocated", "a tenant that writes shares: 1.0 is 100% and 0.6 is 60%",
   (people["Sam Lee"], people["Alex"]))
res["Sam Lee"]["Allocation"], res["Alex Rivera"]["Allocation"] = 130, 1.0
m, raw = mapjson()
people = {p["name"]: p for p in m.get("people", [])}
ok(people["Alex"]["load"] == "1% allocated" and people["Sam Lee"]["load"] == "130% allocated"
   and people["Sam Lee"]["over"], "a tenant that writes percent: 1.0 is 1%", (people["Sam Lee"], people["Alex"]))
res["Alex Rivera"].pop("Allocation")
fake.data["tasks"][F.A1].remove(chen)

# ---- PPM Express not reached -------------------------------------------------------------------------------------------------------
rc, o, e = tm("--no-ppmx")
ok(rc == 0 and "not reached: left out (--no-ppmx); loads unknown" in o and "Unknown: PPM Express wasn't read" in o,
   "--no-ppmx: the map without it", o[:500])
m, raw = mapjson("--no-ppmx")
ok({x["system"]: x["backup"] for x in m["single_points"]}["Network core"] == "Dana",
   "without loads, related expertise still picks a backup")
m, raw = mapjson(PPMX_TOKEN="not a token")
ok(not m["ppmx"]["reached"] and "personal access token isn't valid" in m["ppmx"]["note"] and len(m["people"]) == 4,
   "a bad token: PPM Express not reached, the map built without it", m.get("ppmx"))
ok("not a token" not in raw, "and the bad token isn't printed either")
m, raw = mapjson(PPMX_TOKEN="")
ok(not m["ppmx"]["reached"] and "No personal access token" in m["ppmx"]["note"], "no token at all")
s = socket.socket()
s.bind(("127.0.0.1", 0))
port = s.getsockname()[1]
s.close()
CONFIG.write_text(f'PPMX_BASE_URL="http://127.0.0.1:{port}/@test/v1.0"\nPPMX_TIMEOUT="2"\n')
m, raw = mapjson()
ok(m and not m["ppmx"]["reached"] and "couldn't reach PPM Express" in m["ppmx"]["note"], "PPM Express down: not reached",
   raw[:400])
CONFIG.write_text("")
m, raw = mapjson()
ok(m and not m["ppmx"]["reached"] and "PPMX_BASE_URL isn't set" in m["ppmx"]["note"], "not set up: not reached")
ok(TOKEN not in raw, "no token in any of it")
CONFIG.write_text(f'PPMX_BASE_URL="{BASE}"\n')

# ---- nobody named: everyone PPM Express shows -------------------------------------------------------------------------------------
COVER.unlink()
shutil.rmtree(kit / "feedback")
m, raw = mapjson()
names = {p["name"] for p in m.get("people", [])}
ok(names == {"Alex Rivera", "Sam Lee", "dana", "Blake Chen"} and m["ppmx"]["others_left_out"] == 0,
   "with nobody named, the team is everyone in PPM Express (an address shows as its name only)", sorted(names))
ok(m["single_points"] == [] and m["systems"] == 0, "no coverage file: no single points to check")
hand = {"version": 1, "people": [], "systems": [{"name": "Tape library", "kind": "system", "who": [], "backup": [],
                                                 "tags": []},
                                                {"name": "Print queue", "who": "", "backup": ["Erin"]},
                                                {"name": "Badge system", "who": "Gus; Hana", "tags": "access"},
                                                {"who": ["Nameless"]}, "not an entry"]}
COVER.write_text(json.dumps(hand))
rc, o, e = tm("--no-ppmx")
ok(rc == 0 and "## Nobody named" in o and "Tape library" in o, "a system with nobody named is listed apart", o + e)
ok("**Print queue** (only Erin)" in o and "Badge system" not in o.split("## Known by one person only")[1].split("##")[0],
   "a hand-edited file: a backup alone is still one person; names as a string are read; broken entries are skipped",
   o[-900:])
COVER.write_text("{broken")
rc, o, e = tm()
ok(rc == 1 and "can't read" in e, "a broken coverage file is a clear error, not a traceback", e)

# ---- Kit's permission rules ------------------------------------------------------------------------------------------
import kit_setup  # noqa: E402
ok({"Bash(kit-teammap)", "Bash(kit-teammap *)"} <= set(kit_setup.ALLOW),
   "kit-teammap reads PPM Express only and writes only Kit's own files, so it doesn't ask")

server.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
print(f"\nkit-teammap tests: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)

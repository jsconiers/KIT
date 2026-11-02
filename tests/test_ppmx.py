#!/usr/bin/env python3
"""Tests for the PPM Express MCP server (shared/ppmx) and Kit's command for it (kit-ppmx), against the fake
PPM Express in tests/fake_ppmx.py: the settings, the client (tokens, paging, retries, the per-caller cache,
pacing, no redirects, writes never sent twice), the code tables both ways, the read and write tools and
their arguments, the read-only switch, the MCP side, both servers (stdio and HTTP, with two callers) and
their audit lines, the connector guard's view of the tool names, kit-ppmx (checks, calls, Claude Desktop's
config, setup), Windows Credential Manager (on Windows), and how Kit installs kit-ppmx (the install lists
and Claude Code's permission rules). Nothing reaches the network, the Keychain, or a real Claude Desktop.

Run: python3 tests/test_ppmx.py
"""
import importlib.machinery
import importlib.util
import http.client
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import uuid

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
SHARED = REPO / "shared"
sys.path[:0] = [str(SHARED), str(HERE)]
import fake_ppmx  # noqa: E402
from ppmx import codes  # noqa: E402
from ppmx.client import Client, PPMXError  # noqa: E402
from ppmx.config import Settings  # noqa: E402
from ppmx.mcp_core import PROTOCOL_VERSIONS, Dispatcher  # noqa: E402
from ppmx.server_http import make_app  # noqa: E402
from ppmx.tools import READ_ONLY, TOOLS, WRITE_TOOLS, Context, ToolError, run_tool  # noqa: E402

PASS = FAIL = 0
ALEX, BLAKE, BUSY, CAROL = "token-alex-0001", "token-blake-0002", "token-busy-0003", "token-carol-0005"
F = fake_ppmx
READS = [t["name"] for t in TOOLS if t["kind"] == "read"]


def ok(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


def raises(fn, kind, text=""):
    try:
        fn()
    except kind as e:
        return text.lower() in str(e).lower()
    return False


server, fake, BASE = F.start()
ENV = {"PPMX_BASE_URL": BASE, "PPMX_TODAY": "2026-10-30"}
tmp = pathlib.Path(tempfile.mkdtemp())
CODES = tmp / "codes.json"
CODES.write_text(json.dumps({"OverallStatus": {"1": "Watch"}}))

# ---- settings
s = Settings({})
ok(not s.ready and "PPMX_BASE_URL" in s.problem, "no address: not ready, and says what to set")
ok(Settings({"PPMX_BASE_URL": "https://ppm.example.com/@acme/v1.0/"}).base_url == "https://ppm.example.com/@acme/v1.0",
   "an https address is used, without its trailing slash")
ok("https" in Settings({"PPMX_BASE_URL": "http://ppm.example.com/@acme/v1.0"}).problem, "plain http is refused")
ok(Settings({"PPMX_BASE_URL": "http://127.0.0.1:1/@t/v1.0"}).ready, "plain http to a loopback test server is allowed")
ok("user name" in Settings({"PPMX_BASE_URL": "https://u:p@example.com/@a/v1.0"}).problem,
   "an address with a password in it is refused")
ok(Settings({"PPMX_PAGE_SIZE": "lots", "PPMX_MAX_ROWS": "999999"}).page_size == 25
   and Settings({"PPMX_MAX_ROWS": "999999"}).max_rows == 5000, "bad or huge numbers fall back or are capped")
ok(Settings({}).writes and not Settings({"PPMX_WRITES": "off"}).writes, "changes are on unless PPMX_WRITES is off")

# ---- client
settings = Settings(ENV)
naps = []
client = Client(settings, sleep=naps.append)
got = client.get(ALEX, "projects")
ok(len(got["data"]) == 3 and client.requests == 1, "a list comes whole, in one request (the API doesn't page)", str(got)[:200])
before = client.requests
client.get(ALEX, "projects")
ok(client.requests == before, "the same caller's repeat is answered from the cache")
client.get(BLAKE, "projects")
ok(client.requests == before + 1, "another caller's request is never answered from the first caller's cache")
ok(raises(lambda: client.get("token-nobody-999", "projects"), PPMXError, "Automation"),
   "a rejected token: says to make a new one")
ok(raises(lambda: client.get("two words", "projects"), PPMXError, "isn't valid"), "a token with a space is refused")
ok(raises(lambda: client.get("", "projects"), PPMXError, "no personal access token"), "no token at all")
ok(raises(lambda: client.get(ALEX, "project", id="../Me"), PPMXError, "UUID"), "an ID that isn't a UUID never reaches a path")
ok(raises(lambda: client.get(ALEX, "task", id=F.A1, task_id="../../Me"), PPMXError, "UUID"),
   "every ID in a path is checked, not just the first")
naps.clear()
client.get(BUSY, "me")
ok(naps == [0], "429 with Retry-After: waits as told, then retries", str(naps))
ok(raises(lambda: client._request(ALEX, BASE + "/redirect"), PPMXError, "redirected"), "a redirect isn't followed")
ok(raises(lambda: Client(Settings({})).get(ALEX, "me"), PPMXError, "PPMX_BASE_URL"), "no address: says so")
tries = []


def timing_out(req, timeout=None):
    tries.append(req.get_method())
    raise TimeoutError("timed out")


slow = Client(settings, opener=timing_out, sleep=lambda s: None)
ok(raises(lambda: slow.send(ALEX, "POST", "tasks", {"attributes": {"Name": "x"}}, id=F.A1), PPMXError, "check there")
   and tries == ["POST"], "a write that times out is never sent again, and says to check PPM Express", str(tries))
tries.clear()
ok(raises(lambda: slow.get(ALEX, "me"), PPMXError, "couldn't reach") and tries == ["GET"] * 3,
   "a read that times out is tried three times", str(tries))
for exc in (lambda req: urllib.error.HTTPError(req.full_url, 500, "boom", {}, None),
            lambda req: urllib.error.HTTPError(req.full_url, 502, "bad gateway", {}, None),
            lambda req: ConnectionResetError("reset"),
            lambda req: http.client.IncompleteRead(b"")):
    tries.clear()

    def failing(req, timeout=None, exc=exc):
        tries.append(req.get_method())
        raise exc(req)
    e5 = Client(settings, opener=failing, sleep=lambda s: None)
    ok(raises(lambda: e5.send(ALEX, "POST", "tasks", {"attributes": {"Name": "x"}}, id=F.A1), PPMXError,
              "couldn't confirm") and tries == ["POST"],
       f"a write that ends in {type(exc(urllib.request.Request(BASE))).__name__} is unconfirmed and never resent",
       str(tries))
ok(raises(lambda: client.send(ALEX, "DELETE", "project", {}, id=F.A1), PPMXError, "isn't a write"),
   "no deletes: the client sends only POST and PATCH")


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


clk = Clock()
paced = Client(Settings({**ENV, "PPMX_RATE_PER_MINUTE": "2", "PPMX_CACHE_SECONDS": "0"}), sleep=clk.sleep, clock=clk.now)
for _ in range(3):
    paced.get(ALEX, "me")
    clk.t += 20
ok(len(clk.slept) == 1 and 19 <= clk.slept[0] <= 20, "a caller over the rate waits for the window", str(clk.slept))
paced.get(ALEX, "me")
ok(raises(lambda: paced.get(ALEX, "me"), PPMXError, "too many requests"),
   "a caller who would wait more than 30 seconds is told to try again")
ok(len(paced.get(BLAKE, "me")["data"]) > 0, "one caller's pace doesn't slow another")

# ---- code tables
T = codes.load()
ok(codes.decode({"Status": 10, "Progress": 1, "Priority": 4}, T, "Task")
   == {"Status": "Done", "Progress": "Completed", "Priority": "Strong", "codes": {"Status": 10, "Progress": 1, "Priority": 4}},
   "PPM Express's published codes: labels for numbers, the numbers kept")
ok(codes.decode({"Type": 1}, T, "KeyDate")["Type"] == "Milestone" and codes.decode({"Type": 1}, T, "Project") == {"Type": 1},
   "a table for one kind of record (KeyDate.Type) leaves the others alone")
ok(codes.encode("Progress", "in progress", T) == 2 and codes.encode("Status", "Done", T) == 10
   and codes.encode("Stage", "Selected", T, "Idea") == 3 and codes.encode("Status", "7", T) == 7,
   "labels (any case) and numbers in text become the numbers PPM Express takes")
ok(codes.encode("Status", "Unheard of", T) == "Unheard of" and codes.encode("Name", "Done", T) == "Done"
   and codes.encode("Stage", "Selected", T, "Project") == "Selected",
   "anything else is sent as it is, for PPM Express to judge")
ok(codes.load(str(CODES))["OverallStatus"][1] == "Watch" and codes.load(str(CODES))["Progress"][1] == "Completed",
   "a codes file adds to and overrides the published tables")
ok(raises(lambda: codes.load(str(tmp / "missing.json")), codes.CodesError), "a missing code file is a clear error")

# ---- read tools
bare = Context(client, settings, {}, ALEX)
plain = Context(client, settings, codes.load(), ALEX)
coded = Context(client, settings, codes.load(str(CODES)), ALEX)
me = run_tool("get_current_user", {}, plain)
ok(me["email"] == "arivera@example.com" and "project:write" in me["token"]["scopes"]
   and ALEX not in json.dumps(me), "get_current_user: who, scopes, expiry, and never the token")
r = run_tool("list_projects", {"manager": "rivera"}, plain)
ok(r["total"] == 2 and {i["Name"] for i in r["items"]} == {"Network refresh", "Mobile app"}, "filter by manager", str(r)[:300])
r = run_tool("list_projects", {"portfolio": "digital"}, plain)
ok(r["total"] == 1 and r["items"][0]["Name"] == "Mobile app", "filter by portfolio")
r = run_tool("list_projects", {"sort": "finish", "descending": True}, plain)
ok([i["Name"] for i in r["items"]] == ["Network refresh", "Data center exit", "Mobile app"],
   "sort by finish, latest first, with no-finish-date last", str([i["Name"] for i in r["items"]]))
r = run_tool("list_projects", {"limit": 1, "offset": 1}, plain)
ok(r["total"] == 3 and len(r["items"]) == 1 and r["next_offset"] == 2 and r["sort"] == "name asc", "paging: limit, offset, next_offset")
r = run_tool("list_projects", {"status": "on track"}, plain)
ok(r["total"] == 2 and r["items"][0]["OverallStatus"] == "On Track" and r["items"][0]["codes"]["OverallStatus"] == 0,
   "status as a label, the number kept in codes, and filtering by label", str(r["items"][:1]))
r = run_tool("list_portfolios", {"name_contains": "infra"}, coded)
ok(r["items"][0]["OverallStatus"] == "Watch", "a codes file's label wins")
r = run_tool("list_projects", {"fields": ["Description"], "name_contains": "network"}, plain)
ok(r["items"][0]["Description"] == "Replace the core switches.", "fields: more attributes when asked")
r = run_tool("get_project", {"project_id": F.A1, "include": ["key_dates", "tasks"]}, bare)
ok(r["project"]["Name"] == "Network refresh" and r["key_dates"]["total"] == 3 and r["tasks"]["total"] == 4
   and "notes" in r, "without code tables, tasks are kept open, and the answer says so")
r = run_tool("get_project", {"project_id": F.A1, "include": ["tasks"]}, plain)
ok(r["tasks"]["total"] == 3 and "notes" not in r, "with the code tables, done tasks drop out")
r = run_tool("list_tasks", {"project_id": F.A1, "overdue_only": True}, plain)
ok(r["total"] == 1 and r["items"][0]["Name"] == "Order switches", "overdue tasks (today 30-Oct-2026)", str(r)[:300])
r = run_tool("list_tasks", {"project_id": F.A1, "due_within_days": 14}, plain)
ok(r["total"] == 1 and r["items"][0]["Name"] == "Cutover plan", "tasks due within 14 days")
r = run_tool("list_tasks", {"project_id": F.A1, "assignee": "sam"}, plain)
ok(r["total"] == 1 and r["items"][0]["AssignedTo"][0]["fullName"] == "Sam Lee", "filter tasks by assignee (a person record)")
r = run_tool("list_key_dates", {"project_id": F.A1, "upcoming_days": 45}, plain)
ok(r["total"] == 1 and r["items"][0]["Name"] == "Go-live" and r["items"][0]["Type"] == "Milestone", "upcoming key dates")
r = run_tool("list_key_dates", {"project_id": F.A1, "overdue_only": True}, plain)
ok(r["total"] == 1 and r["items"][0]["Name"] == "Vendor contract", "overdue key dates leave out finished ones")
r = run_tool("list_ideas", {"challenge_id": F.C1}, plain)
ok(r["total"] == 1 and r["items"][0]["Name"] == "AI triage" and r["items"][0]["Stage"] == "Active", "ideas for one challenge")
r = run_tool("list_challenges", {}, plain)
ok(r["total"] == 1 and r["items"][0]["id"] == F.C1, "challenges")
r = run_tool("list_resources", {"name_contains": "lee"}, plain)
ok(r["total"] == 1 and r["items"][0]["Email"] == "sam@example.com", "resources by name")
r = run_tool("get_fields", {"entity": "Project"}, plain)
ok([f["key"] for f in r["fields"]] == ["Name", "OverallStatus"], "get_fields lists a tenant's field keys")
ok(raises(lambda: run_tool("list_projects", {"colour": "red"}, plain), ToolError, "unknown argument"), "an unknown argument is refused")
ok(raises(lambda: run_tool("get_project", {"project_id": "nope"}, plain), ToolError, "UUID"), "a bad ID is refused")
ok(raises(lambda: run_tool("get_project", {}, plain), ToolError, "required"), "a missing required argument is refused")
ok(raises(lambda: run_tool("list_projects", {"limit": 0}, plain), ToolError, "range"), "out-of-range numbers are refused")
ok(raises(lambda: run_tool("get_fields", {"entity": "Secrets"}, plain), ToolError, "one of"), "only known entities")
ok(run_tool("list_projects", {"limit": 2.0}, plain)["limit"] == 2, "a whole number sent as 2.0 is fine")
ok(raises(lambda: run_tool("list_projects", {}, Context(client, settings, {}, "", hint="Set PPMX_TOKEN.")), ToolError,
          "Set PPMX_TOKEN"), "no token: the tool says where to set one")

# ---- endpoints: every path is one PPM Express's OpenAPI description has (GET, as listed on 02-Nov-2026)
from ppmx import client as client_mod  # noqa: E402
SPEC_GET = {"me", "users/{id}", "portfolios", "portfolios/{id}", "programs", "programs/{id}", "projects",
            "projects/{id}", "projects/{id}/tasks", "projects/{id}/tasks/{taskId}", "projects/{id}/keydates",
            "projects/{id}/keydates/{keyDateId}", "projects/{id}/deliverables",
            "projects/{id}/deliverables/{deliverableId}", "ideas", "ideas/{id}", "challenges", "challenges/{id}",
            "resources", "resources/{id}", "fields/{entity}"}
SPEC_POST_ONLY = {"ideas/{id}/stage"}
import re as _re  # noqa: E402
generic = {n: _re.sub(r"\{[a-z_]*_id\}", "{x}", p) for n, p in client_mod.ENDPOINTS.items()}
spec = {_re.sub(r"\{(taskId|keyDateId|deliverableId)\}", "{x}", p) for p in SPEC_GET | SPEC_POST_ONLY}
ok(all(p in spec for p in generic.values()) and all(p == p.lower() for p in client_mod.ENDPOINTS.values()),
   "every endpoint is a path in PPM Express's API description, lowercase", str({n: p for n, p in generic.items() if p not in spec}))
ok("tasks_bulk" not in client_mod.ENDPOINTS and not hasattr(client_mod, "next_link"),
   "no made-up endpoints or paging: sub-tasks go to the task list, and lists come whole")

# ---- person filters: a person's fullName inside a list of {id, fullName}, or "me"
r = run_tool("list_projects", {"manager": "RIVERA"}, plain)
ok(r["total"] == 2 and "me" not in r, "manager: part of a fullName in the list of people, any case", str(r)[:200])
fake.data["projects"]["blake"][0]["attributes"]["Manager"].append(F.person(F.R2, "Sam Lee"))
r = run_tool("list_projects", {"manager": "lee"}, Context(Client(settings), settings, {}, BLAKE))
fake.data["projects"]["blake"][0]["attributes"]["Manager"].pop()
ok(r["total"] == 1 and r["items"][0]["Name"] == "Payments upgrade", "manager: a project with two managers matches either")
r = run_tool("list_projects", {"manager": "me"}, Context(client, settings, codes.load(), ALEX))
ok(r["total"] == 2 and {i["Name"] for i in r["items"]} == {"Network refresh", "Mobile app"}
   and "full name from PPM Express" in r["me"]["matched_by"] and r["me"]["user_id"] == F.U_ALEX,
   "manager \"me\": the token's user, by the full name users/{id} gives", str(r)[:300])
r = run_tool("list_tasks", {"project_id": F.A1, "assignee": "me"}, Context(client, settings, codes.load(), ALEX))
ok(r["total"] == 2 and {i["id"] for i in r["items"]} == {F.T2, F.T3},
   "assignee \"me\": by user ID (any name) and by full name (a resource ID)", str(r)[:300])
bl = Context(client, settings, codes.load(), BLAKE, owner=True)
r = run_tool("list_projects", {"manager": "me"}, bl)
ok(r["total"] == 1 and r["items"][0]["Name"] == "Payments upgrade" and "PPMX_MY_NAME" in r["me"]["note"],
   "\"me\" without users/{id} access: by the name the email is made from, and the answer says how to be exact",
   str(r)[:300])
ok("filter by your name" in run_tool("list_projects", {"manager": "me"}, Context(client, settings, {}, BLAKE, owner=False))["me"]["note"],
   "on the multi-user service the note says to filter by name (PPMX_MY_NAME is the owner's alone)")
sam = Settings({**ENV, "PPMX_MY_NAME": "Sam Lee"})
ok({i["id"] for i in run_tool("list_tasks", {"project_id": F.A1, "assignee": "me"}, Context(client, sam, {}, ALEX, owner=True))["items"]}
   == {F.T1, F.T2, F.T3}
   and {i["id"] for i in run_tool("list_tasks", {"project_id": F.A1, "assignee": "me"}, Context(client, sam, {}, ALEX))["items"]}
   == {F.T2, F.T3}, "PPMX_MY_NAME counts as \"me\" for the owner's own server only, never on the shared one")
r = run_tool("list_portfolios", {"manager": "me"}, Context(client, settings, {}, ALEX))
ok(r["total"] == 1 and r["items"][0]["Name"] == "Digital", "list_portfolios: manager \"me\"")
r = run_tool("list_programs", {"manager": "sam"}, plain)
ok(r["total"] == 1, "list_programs: manager by part of a fullName")
mc = Client(settings)
mc.whoami(ALEX)
n0 = mc.requests
mc.whoami(ALEX)
mc.whoami(ALEX)
ok(mc.requests == n0 and mc.whoami(BLAKE)["id"] == F.U_BLAKE and mc.whoami(ALEX)["id"] == F.U_ALEX,
   "who \"me\" is: cached per token, never one token's answer for another")

# ---- deliverables
r = run_tool("list_deliverables", {"project_id": F.A1}, plain)
ok(r["total"] == 2 and r["sort"] == "due asc" and r["items"][0]["Name"] == "Cabling survey"
   and r["items"][0]["Status"] == "Done", "list_deliverables: a project's deliverables, by due date, labels for codes", str(r)[:300])
r = run_tool("list_deliverables", {"project_id": F.A1, "open_only": True}, plain)
ok(r["total"] == 1 and r["items"][0]["id"] == F.D1, "list_deliverables: open only")
r = run_tool("list_deliverables", {"project_id": F.A1, "assignee": "me"}, Context(client, settings, {}, ALEX))
ok(r["total"] == 1 and r["items"][0]["id"] == F.D1 and "me" in r, "list_deliverables: assignee \"me\"")
r = run_tool("list_deliverables", {"project_id": F.A1, "assignee": "lee", "status": "done"}, plain)
ok(r["total"] == 1 and r["items"][0]["id"] == F.D2, "list_deliverables: by assignee name and status")
r = run_tool("list_deliverables", {"project_id": F.A1, "overdue_only": True}, plain)
ok(r["total"] == 0, "list_deliverables: overdue leaves out finished ones")
r = run_tool("get_deliverable", {"project_id": F.A1, "deliverable_id": F.D1}, plain)
ok(r["deliverable"]["Name"] == "Switch design pack" and r["deliverable"]["sourceType"] == "Ppmx", "get_deliverable")
ok(raises(lambda: run_tool("get_deliverable", {"project_id": F.A1, "deliverable_id": "x"}, plain), ToolError, "UUID"),
   "get_deliverable: a bad ID is refused")
ok(run_tool("get_project", {"project_id": F.A1, "include": ["deliverables"]}, plain)["deliverables"]["total"] == 2,
   "get_project can include deliverables")
ok([f["key"] for f in run_tool("get_fields", {"entity": "Deliverable"}, plain)["fields"]] == ["Name", "AssignedTo"],
   "get_fields knows deliverables")

# ---- list_my_work: bounded, and says what it covered
mine = Context(Client(settings), settings, codes.load(), ALEX)
r = run_tool("list_my_work", {}, mine)
ok(r["total"] == 2 and {(i["kind"], i["id"]) for i in r["items"]} == {("task", F.T3), ("deliverable", F.D1)}
   and all(i["project_id"] == F.A1 and i["project"] == "Network refresh" for i in r["items"])
   and r["projects_in_scope"] == 3 and r["projects_scanned"] == 3 and r["complete"] and "notes" not in r,
   "list_my_work: open tasks and deliverables assigned to me, with their project", str(r)[:400])
ok(run_tool("list_my_work", {"open_only": False}, mine)["total"] == 3, "list_my_work: open_only false adds finished work")
r = run_tool("list_my_work", {"due_within_days": 7}, mine)
ok(r["total"] == 1 and r["items"][0]["id"] == F.D1, "list_my_work: due within 7 days")
ok(run_tool("list_my_work", {"include": ["tasks"]}, mine)["total"] == 1, "list_my_work: tasks only")
cnt = Client(settings)
r = run_tool("list_my_work", {"max_projects": 1}, Context(cnt, settings, codes.load(), ALEX))
ok(r["projects_scanned"] == 1 and not r["complete"] and any("cap is 1" in n for n in r["notes"]) and r["total"] == 2
   and cnt.requests <= 3 + 2, "list_my_work: at most max_projects scanned (projects I manage first), and it says so",
   str(r)[:400] + f" requests={cnt.requests}")
capped = Settings({**ENV, "PPMX_WORK_MAX_PROJECTS": "2"})
r = run_tool("list_my_work", {"max_projects": 200}, Context(Client(capped), capped, {}, ALEX))
ok(r["projects_scanned"] == 2, "list_my_work: PPMX_WORK_MAX_PROJECTS is the ceiling, whatever the caller asks")
quick = Settings({**ENV, "PPMX_WORK_SECONDS": "0"})
r = run_tool("list_my_work", {}, Context(Client(quick), quick, {}, ALEX))
ok(r["projects_scanned"] == 1 and any("time or rate limit" in n for n in r["notes"]), "list_my_work: stops at PPMX_WORK_SECONDS and says so")
r = run_tool("list_my_work", {"project_ids": [F.A2]}, mine)
ok(r["projects_in_scope"] == 1 and r["total"] == 0, "list_my_work: a project scope")
r = run_tool("list_my_work", {}, Context(Client(settings), settings, codes.load(), BLAKE))
ok(r["total"] == 1 and r["items"][0]["Name"] == "Card vault review", "list_my_work: another token, its own work")

# ---- an empty list says why
r = run_tool("list_resources", {}, plain)
ok(r["total"] == 2 and "explanation" not in r, "list_resources: no explanation when there are resources")
r = run_tool("list_resources", {}, Context(client, settings, {}, BLAKE))
ok(r["total"] == 0 and "doesn't have the resource:read scope" in r["explanation"], "list_resources: a missing scope is named")
r = run_tool("list_resources", {}, Context(client, settings, {}, CAROL))
ok(r["total"] == 0 and "has the resource:read scope" in r["explanation"] and "permissions" in r["explanation"],
   "list_resources: with the scope, an empty list is put down to the account's PPM Express permissions", str(r))
ok("explanation" in run_tool("list_ideas", {}, Context(client, settings, {}, CAROL))
   and "explanation" in run_tool("list_challenges", {}, Context(client, settings, {}, CAROL)),
   "list_ideas and list_challenges explain an empty list the same way")

# ---- the connector guard: Kit's agents may read, never write
guard_path = SHARED / "bin/connector-guard"
loader = importlib.machinery.SourceFileLoader("connector_guard", str(guard_path))
spec = importlib.util.spec_from_loader("connector_guard", loader)
guard = importlib.util.module_from_spec(spec)
loader.exec_module(guard)
cfg = {"allowed_servers": ["ppmx"], "allow_tools": [], "deny_tools": []}
verdicts = {t["name"]: guard.decide(cfg, f"mcp__ppmx__{t['name']}")[0] for t in TOOLS}
ok(all(verdicts[n] == "allow" for n in READS) and all(verdicts[n] == "deny" for n in WRITE_TOOLS),
   "the connector guard lets agents read and stops every write", str(verdicts))

ok(all(guard.decide(cfg, f"mcp__ppmx__{n}")[0] == "allow" for n in
        ("list_deliverables", "get_deliverable", "list_my_work", "list_resources", "get_current_user"))
   and all(guard.decide(cfg, f"mcp__ppmx__{n}")[0] == "deny" for n in
           ("set_idea_stage", "create_task", "update_project", "create_record", "update_record")),
   "the guard by name: the new reads pass; create_, update_, and set_ are denied")
tmpl = json.loads((REPO / "kit/memory/context/connector-guard.json").read_text(encoding="utf-8"))
tmpl["allowed_servers"] = tmpl.get("allowed_servers", []) + ["ppmx"]   # as kit-ppmx setup says to add it
ok(all(guard.decide(tmpl, f"mcp__ppmx__{t['name']}")[0] == ("allow" if t["kind"] == "read" else "deny") for t in TOOLS),
   "the repo's guard template with ppmx allowed: every ppmx read passes and every ppmx write is denied")

# ---- the MCP side
d = Dispatcher(lambda t: Context(client, settings, codes.load(), t, hint="no token"))
init = d.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
ok(init["result"]["protocolVersion"] == "2025-06-18" and init["result"]["capabilities"] == {"tools": {"listChanged": False}}
   and "go ahead only when they agree" in init["result"]["instructions"],
   "initialize: the caller's protocol version, and instructions to confirm changes")
init = d.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
ok(init["id"] == 0 and init["result"]["protocolVersion"] == PROTOCOL_VERSIONS[0], "an unknown version gets the newest (and id 0 works)")
listed = {t["name"]: t for t in d.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]}
ok(len(listed) == len(TOOLS) == 25 and len(WRITE_TOOLS) == 11
   and all(listed[n]["annotations"]["readOnlyHint"] for n in READS)
   and not any(listed[n]["annotations"]["readOnlyHint"] for n in WRITE_TOOLS)
   and all(t["inputSchema"]["additionalProperties"] is False for t in listed.values()),
   "tools/list: 14 reads and 11 writes, each marked for what it does, closed schemas")
ok(listed["update_task"]["annotations"]["destructiveHint"] and not listed["create_task"]["annotations"]["destructiveHint"]
   and not any("delete" in n for n in listed), "updates are marked as changing data; there's no delete")
ok(d.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None, "notifications get no answer")
ok(d.handle({"id": 3, "method": "ping"})["error"]["code"] == -32600, "a message without jsonrpc 2.0 is invalid")
ok(d.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "delete_project"}})["error"]["code"] == -32602,
   "an unknown tool is a protocol error")
res = d.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "list_projects", "arguments": {}}}, ALEX)["result"]
ok(res["isError"] is False and json.loads(res["content"][0]["text"])["total"] == 3, "tools/call returns the tool's JSON")
res = d.handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "list_projects"}}, "")["result"]
ok(res["isError"] is True and res["content"][0]["text"] == "no token", "a tool error comes back as isError")
ok(d.handle({"jsonrpc": "2.0", "id": 7, "method": "resources/list"})["error"]["code"] == -32601, "other methods: not found")
ro = Dispatcher(lambda t: Context(client, Settings({**ENV, "PPMX_WRITES": "off"}), {}, t), writes=False)
init = ro.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})["result"]
names = [t["name"] for t in ro.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]]
facts = {}
res = ro.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
    "name": "create_task", "arguments": {"project_id": F.A1, "name": "x"}}}, ALEX, facts.update)["result"]
ok(names == READS and "read-only" in init["serverInfo"]["title"] and res["isError"] and res["content"][0]["text"] == READ_ONLY
   and facts.get("outcome") == "refused", "read-only (PPMX_WRITES=off): only the reads are listed, and a write is refused")

# ---- writes, on a fake of their own
wserver, wfake, WBASE = F.start()
wsettings = Settings({"PPMX_BASE_URL": WBASE, "PPMX_TODAY": "2026-10-30"})
wnaps = []
wclient = Client(wsettings, sleep=wnaps.append)
w = Context(wclient, wsettings, codes.load(), ALEX)


def last_write():
    return wfake.writes[-1] if wfake.writes else None


ok(run_tool("list_tasks", {"project_id": F.A1}, w)["total"] == 4, "four tasks before")
r = run_tool("create_task", {"project_id": F.A1, "name": "Rack the switches", "fields": {
    "Status": "At Risk", "Progress": "In Progress", "AssignedTo": "sam@example.com", "DueDate": "2026-11-20",
    "Tags": "network, #infra"}}, w)
ok(last_write() == ("alex", "POST", f"projects/{F.A1}/tasks", {"attributes": {
    "Status": 1, "Progress": 2, "AssignedTo": [{"search": "sam@example.com"}], "DueDate": "2026-11-20",
    "Tags": ["#network", "#infra"], "Name": "Rack the switches"}}),
   "create_task: POST {attributes}, labels sent as numbers, a person as a search, tags with #", str(last_write()))
ok(r["result"] == "created" and r["kind"] == "task" and len(r["id"]) == 36 and r["record"]["Status"] == "At Risk"
   and r["fields"] == ["AssignedTo", "DueDate", "Name", "Progress", "Status", "Tags"],
   "create_task: the new ID, the record as PPM Express has it, and the field names", str(r)[:300])
ok(run_tool("list_tasks", {"project_id": F.A1}, w)["total"] == 5, "a write clears the caller's cache: the next read sees it")
r = run_tool("update_task", {"project_id": F.A1, "task_id": F.T1, "fields": {"Status": "Done", "Progress": "Completed"}}, w)
ok(last_write() == ("alex", "PATCH", f"projects/{F.A1}/tasks/{F.T1}", {"updates": {"Status": 10, "Progress": 1}})
   and r["result"] == "updated" and r["id"] == F.T1 and r["record"]["Status"] == "Done",
   "update_task: PATCH {updates} with only the fields given", str(last_write()))
ok(raises(lambda: run_tool("update_task", {"project_id": F.A1, "task_id": F.T4, "fields": {"Status": "Done"}}, w),
          PPMXError, "synced from Jira"), "PPM Express's own refusal comes through (a Jira-synced task)")
run_tool("create_task", {"project_id": F.A1, "name": "Label the cables", "parent_task_id": F.T3}, w)
ok(last_write() == ("alex", "POST", f"projects/{F.A1}/tasks", {"parentId": F.T3, "attributes": {"Name": "Label the cables"}}),
   "a sub-task goes to the task list with parentId (CreateTaskRequest)", str(last_write()))
r = run_tool("create_key_date", {"project_id": F.A1, "name": "Cutover", "date": "2026-12-05", "type": "Milestone"}, w)
ok(last_write()[3] == {"attributes": {"Date": "2026-12-05", "Type": 1, "Name": "Cutover"}} and r["record"]["Type"] == "Milestone",
   "create_key_date: the date, and the type as its number", str(last_write()))
run_tool("update_key_date", {"project_id": F.A1, "key_date_id": F.K2, "fields": {"Date": "2026-12-01"}}, w)
ok(last_write()[1:] == ("PATCH", f"projects/{F.A1}/keydates/{F.K2}", {"updates": {"Date": "2026-12-01"}}), "update_key_date")
r = run_tool("create_project", {"name": "Badge readers", "fields": {
    "Manager": "Alex Rivera", "Portfolio": ["Infrastructure", F.P2], "StartDate": "2027-01-04"}}, w)
ok(last_write()[1:] == ("POST", "projects", {"attributes": {
    "Manager": [{"search": "Alex Rivera"}], "Portfolio": [{"search": "Infrastructure"}, {"id": F.P2}],
    "StartDate": "2027-01-04", "Name": "Badge readers"}}), "create_project: the manager and portfolios as references (an ID as an id)",
   str(last_write()))
run_tool("update_project", {"project_id": F.A2, "fields": {"OverallStatus": "At Risk"}}, w)
ok(last_write()[1:] == ("PATCH", f"projects/{F.A2}", {"updates": {"OverallStatus": 1}}), "update_project")
run_tool("create_idea", {"name": "Chat intake", "challenge_id": F.C1}, w)
ok(last_write()[1:3] == ("POST", "ideas"), "create_idea")
ok(any(i["attributes"]["Name"] == "Chat intake" and i.get("challengeId") == F.C1 for i in wfake.data["ideas"]["alex"]),
   "create_idea under a challenge (challengeId in the query)")
run_tool("update_idea", {"idea_id": F.I1, "fields": {"Description": "One place to ask."}}, w)
ok(last_write()[1:] == ("PATCH", f"ideas/{F.I1}", {"updates": {"Description": "One place to ask."}}), "update_idea")
r = run_tool("set_idea_stage", {"idea_id": F.I1, "stage": "Selected"}, w)
ok(last_write()[1:] == ("POST", f"ideas/{F.I1}/stage", {"stage": "Selected"}) and r["record"]["Stage"] == "Selected",
   "set_idea_stage: POST {stage: name}, as the API takes it")
run_tool("set_idea_stage", {"idea_id": F.I1, "stage": "not selected"}, w)
ok(last_write()[3] == {"stage": "NotSelected"}, "set_idea_stage: a name with a space goes as PPM Express spells it")
ok(raises(lambda: run_tool("set_idea_stage", {"idea_id": F.I1, "stage": 1}, w), PPMXError, "can't move back"),
   "a stage move PPM Express won't make: its reason comes through")
ok(raises(lambda: run_tool("set_idea_stage", {"idea_id": F.I1, "stage": "Maybe"}, w), ToolError, "one of: Draft"),
   "an unknown stage is refused before anything is sent")
run_tool("create_record", {"kind": "resource", "name": "Pat Kim", "fields": {"Email": "pat@example.com"}}, w)
ok(last_write()[1:] == ("POST", "resources", {"attributes": {"Email": "pat@example.com", "Name": "Pat Kim"}}), "create_record: a resource")
run_tool("update_record", {"kind": "portfolio", "record_id": F.P2, "fields": {"OverallStatus": "On Track"}}, w)
ok(last_write()[1:] == ("PATCH", f"portfolios/{F.P2}", {"updates": {"OverallStatus": 0}}), "update_record: a portfolio")
n = len(wfake.writes)
ok(raises(lambda: run_tool("update_task", {"project_id": F.A1, "task_id": F.T1, "fields": {}}, w), ToolError, "required")
   and raises(lambda: run_tool("update_task", {"project_id": F.A1, "task_id": F.T1, "fields": {"bad key!": 1}}, w),
              ToolError, "isn't a field key")
   and raises(lambda: run_tool("create_key_date", {"project_id": F.A1, "name": "x", "date": "05/12/2026"}, w), ToolError, "YYYY-MM-DD")
   and len(wfake.writes) == n, "empty changes, odd field keys, and bad dates are refused before anything is sent")
ok(raises(lambda: run_tool("create_task", {"project_id": F.A1, "name": "x"}, Context(wclient, wsettings, {}, BLAKE)),
          PPMXError, "write scope"), "a token without write scopes: PPM Express refuses, and the message says why")
wnaps.clear()
run_tool("create_task", {"project_id": F.A1, "name": "Retry me"}, Context(wclient, wsettings, {}, BUSY))
ok(wnaps == [0] and sum(1 for x in wfake.writes if x[3] == {"attributes": {"Name": "Retry me"}}) == 1,
   "a write PPM Express answered 429 is sent again, once it says to", str(wnaps))
ro_ctx = Context(wclient, Settings({"PPMX_BASE_URL": WBASE, "PPMX_WRITES": "off"}), {}, ALEX)
n = len(wfake.writes)
ok(raises(lambda: run_tool("create_task", {"project_id": F.A1, "name": "x"}, ro_ctx), ToolError, "read-only")
   and len(wfake.writes) == n, "PPMX_WRITES=off: a write tool is refused before anything is sent")

# ---- stdio: python -m ppmx stdio
lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
         {"jsonrpc": "2.0", "method": "notifications/initialized"},
         {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
         {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_projects", "arguments": {"limit": 1}}}]
env = {k: v for k, v in os.environ.items() if not k.startswith(("PPMX_", "CLAUDE_DESKTOP"))}
env["PYTHONUTF8"] = "1"
p = subprocess.run([sys.executable, "-m", "ppmx", "stdio"], cwd=SHARED, input="\n".join(json.dumps(x) for x in lines) + "\n",
                   capture_output=True, text=True, encoding="utf-8", timeout=60, env={**env, **ENV, "PPMX_TOKEN": ALEX})
out = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]
ok(p.returncode == 0 and [o["id"] for o in out] == [1, 2, 3] and json.loads(out[2]["result"]["content"][0]["text"])["total"] == 3,
   "stdio: initialize, tools/list, and a call, one line each", p.stdout[-300:] + p.stderr[-300:])
ok('"tool": "list_projects"' in p.stderr and '"via": "stdio"' in p.stderr and ALEX not in p.stderr,
   "stdio: an audit line per tool call on standard error, without the token", p.stderr[-300:])
p = subprocess.run([sys.executable, "-m", "ppmx", "stdio"], cwd=SHARED, input=json.dumps(lines[3]) + "\n",
                   capture_output=True, text=True, encoding="utf-8", timeout=60, env={**env, **ENV})
res = json.loads(p.stdout)["result"]
ok(res["isError"] and "PPMX_TOKEN" in res["content"][0]["text"], "stdio without a token: says which variable to set")

# ---- HTTP: the standalone app, two callers
audit = []
app = make_app(Settings({"PPMX_BASE_URL": WBASE, "PPMX_TODAY": "2026-10-30"}), log=audit.append)
from wsgiref.simple_server import WSGIRequestHandler, make_server  # noqa: E402


class Quiet(WSGIRequestHandler):
    def log_message(self, *a):
        pass


httpd = make_server("127.0.0.1", 0, app, handler_class=Quiet)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{httpd.server_address[1]}"


def post(body, headers=None, raw=None, path="/mcp"):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", **(headers or {})}
    req = urllib.request.Request(URL + path, data=raw if raw is not None else json.dumps(body).encode(), headers=h,
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
            return r.status, json.loads(data) if data else None
    except urllib.error.HTTPError as e:
        data = e.read()
        return e.code, json.loads(data) if data else None


def tool(name, args, headers):
    s, b = post({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}, headers)
    return b["result"]["isError"], b["result"]["content"][0]["text"]


err, a = tool("list_projects", {}, {"X-PPMX-Token": ALEX})
err2, b = tool("list_projects", {}, {"X-PPMX-Token": BLAKE})
ok(not err and not err2 and json.loads(a)["total"] == 4 and json.loads(b)["total"] == 1, "HTTP: each caller sees only their own",
   a[:200])
err, a = tool("get_current_user", {}, {"Authorization": f"Bearer {BLAKE}"})
ok(not err and json.loads(a)["email"] == "blake.chen@example.com", "HTTP: a token as Authorization: Bearer")
err, a = tool("get_current_user", {}, {"X-PPMX-Token": ALEX, "Authorization": "Bearer something-for-sso"})
ok(not err and json.loads(a)["email"] == "arivera@example.com", "HTTP: X-PPMX-Token wins over Authorization (left to sign-on)")
err, a = tool("list_projects", {}, {})
ok(err and "X-PPMX-Token" in a, "HTTP: no token, and the tool says how to send one")
err, a = tool("list_projects", {}, {"X-PPMX-Token": "bad token"})
ok(err and "isn't valid" in a, "HTTP: a malformed token is refused")
err, a = tool("create_task", {"project_id": F.A1, "name": "Order fiber"}, {"X-PPMX-Token": ALEX})
err2, b = tool("create_task", {"project_id": F.A1, "name": "Order fiber"}, {"X-PPMX-Token": BLAKE})
ok(not err and json.loads(a)["result"] == "created" and err2 and "write scope" in b,
   "HTTP: each caller's change is made with their own token (Blake's can't write)")
ok(post({"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"Origin": "https://evil.example.com"})[0] == 403,
   "HTTP: a request from a browser origin is refused")
ok(post({"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"MCP-Protocol-Version": "1999-01-01"})[0] == 400,
   "HTTP: an unsupported protocol version is refused")
ok(post({"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"Content-Type": "text/plain"})[0] == 415, "HTTP: JSON only")
ok(post(None, raw=b"{not json")[0] == 400, "HTTP: a body that isn't JSON")
ok(post(None, {"Content-Length": "2000000"}, raw=b"{}")[0] == 413, "HTTP: an oversized body is refused before it's read")
s, body = post([{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
ok(s == 200 and [m["id"] for m in body] == [1, 2], "HTTP: a batch gets a list of answers, notifications left out")
ok(post({"jsonrpc": "2.0", "method": "notifications/initialized"}) == (202, None), "HTTP: a lone notification gets 202")
try:
    urllib.request.urlopen(URL + "/mcp", timeout=5)
    status = 200
except urllib.error.HTTPError as e:
    status, allow = e.code, e.headers.get("Allow")
ok(status == 405 and allow == "POST", "HTTP: GET /mcp is 405 (no event stream)")
with urllib.request.urlopen(URL + "/healthz", timeout=5) as r:
    ok(r.status == 200, "HTTP: /healthz")
with urllib.request.urlopen(URL + "/readyz", timeout=5) as r:
    ok(r.status == 200, "HTTP: /readyz when configured")
unset = make_server("127.0.0.1", 0, make_app(Settings({}), log=lambda e: None), handler_class=Quiet)
threading.Thread(target=unset.serve_forever, daemon=True).start()
try:
    urllib.request.urlopen(f"http://127.0.0.1:{unset.server_address[1]}/readyz", timeout=5)
    status = 200
except urllib.error.HTTPError as e:
    status, why = e.code, json.loads(e.read())["reason"]
ok(status == 503 and "PPMX_BASE_URL" in why, "HTTP: /readyz is 503 until PPMX_BASE_URL is set")
text = json.dumps(audit)
ok(audit and ALEX not in text and BLAKE not in text and any(e.get("tool") == "list_projects" and e.get("user", "").startswith("u:")
                                                            for e in audit),
   "HTTP: the audit log has calls by a user hash, and no token", text[:300])
ok(all("arguments" not in e and "args" in e for e in audit if e.get("tool")) and "Order fiber" not in text,
   "HTTP: the audit log names arguments, not their values")
made = [e for e in audit if e.get("tool") == "create_task" and e.get("outcome") == "ok"]
ok(len(made) == 1 and made[0]["write"] == "create" and made[0]["fields"] == ["Name"] and len(made[0]["id"]) == 36,
   "HTTP: a change's audit line has its kind, the record's ID, and the field names", str(made))
users = {e["user"] for e in audit if e.get("tool") == "list_projects" and e.get("outcome") == "ok"}
ok(len(users) == 2, "HTTP: two callers, two user hashes", str(users))

# ---- the new reads on both servers: HTTP (multi-user, one shared client) and stdio (the owner's)
haudit = []
happ2 = make_app(Settings({"PPMX_BASE_URL": BASE, "PPMX_TODAY": "2026-10-30", "PPMX_MY_NAME": "Sam Lee"}), log=haudit.append)
hsrv2 = make_server("127.0.0.1", 0, happ2, handler_class=Quiet)
threading.Thread(target=hsrv2.serve_forever, daemon=True).start()
URL2 = f"http://127.0.0.1:{hsrv2.server_address[1]}"


def htool(name, args, token, url=None):
    req = urllib.request.Request((url or URL2) + "/mcp", method="POST", data=json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json", "X-PPMX-Token": token})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read())["result"]
    return res["isError"], json.loads(res["content"][0]["text"]) if not res["isError"] else res["content"][0]["text"]


e1, a = htool("list_my_work", {}, ALEX)
e2, b = htool("list_my_work", {}, BLAKE)
ok(not e1 and not e2 and {i["id"] for i in a["items"]} == {F.T3, F.D1} and [i["Name"] for i in b["items"]] == ["Card vault review"]
   and a["me"]["user_id"] == F.U_ALEX and b["me"]["user_id"] == F.U_BLAKE,
   "HTTP: list_my_work, \"me\" per request token through one shared client", str(a)[:200] + str(b)[:200])
_, a = htool("list_projects", {"manager": "me"}, ALEX)
_, b = htool("list_projects", {"manager": "me"}, BLAKE)
ok(a["total"] == 2 and b["total"] == 1 and "filter by your name" in b["me"]["note"], "HTTP: manager \"me\" for each caller")
_, a = htool("list_tasks", {"project_id": F.A1, "assignee": "me"}, ALEX)
ok({i["id"] for i in a["items"]} == {F.T2, F.T3}, "HTTP: PPMX_MY_NAME is ignored on the shared service", str(a)[:200])
_, a = htool("list_tasks", {"project_id": F.A1, "assignee": "rivera"}, ALEX)
ok(a["total"] == 2, "HTTP: assignee by part of a fullName")
_, a = htool("list_deliverables", {"project_id": F.A1, "open_only": True}, ALEX)
_, b = htool("get_deliverable", {"project_id": F.A1, "deliverable_id": F.D1}, ALEX)
ok(a["total"] == 1 and b["deliverable"]["Name"] == "Switch design pack", "HTTP: list_deliverables and get_deliverable")
_, a = htool("list_resources", {}, CAROL)
_, b = htool("list_resources", {}, BLAKE)
ok(a["total"] == 0 and "permissions" in a["explanation"] and "resource:read scope" in b["explanation"],
   "HTTP: list_resources explains an empty list")
capapp = make_app(Settings({"PPMX_BASE_URL": BASE, "PPMX_TODAY": "2026-10-30", "PPMX_WORK_MAX_PROJECTS": "1"}), log=lambda e: None)
csrv = make_server("127.0.0.1", 0, capapp, handler_class=Quiet)
threading.Thread(target=csrv.serve_forever, daemon=True).start()
_, a = htool("list_my_work", {"max_projects": 50}, ALEX, f"http://127.0.0.1:{csrv.server_address[1]}")
ok(a["projects_scanned"] == 1 and not a["complete"] and a["notes"], "HTTP: PPMX_WORK_MAX_PROJECTS bounds one request, and it says so")
csrv.shutdown()
seen = {e.get("tool") for e in haudit if e.get("outcome") == "ok"}
ok({"list_my_work", "list_deliverables", "get_deliverable", "list_resources", "list_projects", "list_tasks"} <= seen
   and ALEX not in json.dumps(haudit) and all("ms" in e and e["user"].startswith("u:") for e in haudit if e.get("tool")),
   "HTTP: an audit line for each new tool, by user hash, never the token", str(seen))
hsrv2.shutdown()
calls = [{"jsonrpc": "2.0", "id": i + 1, "method": "tools/call", "params": {"name": n, "arguments": a}} for i, (n, a) in enumerate([
    ("list_my_work", {}), ("list_deliverables", {"project_id": F.A1}),
    ("get_deliverable", {"project_id": F.A1, "deliverable_id": F.D1}), ("list_resources", {}),
    ("list_tasks", {"project_id": F.A1, "assignee": "me"}), ("list_projects", {"manager": "me"})])]
p = subprocess.run([sys.executable, "-m", "ppmx", "stdio"], cwd=SHARED, input="\n".join(json.dumps(x) for x in calls) + "\n",
                   capture_output=True, text=True, encoding="utf-8", timeout=60,
                   env={**env, **ENV, "PPMX_TOKEN": ALEX, "PPMX_MY_NAME": "Sam Lee"})
outs = [json.loads(json.loads(x)["result"]["content"][0]["text"]) for x in p.stdout.splitlines() if x.strip()]
ok(len(outs) == 6 and {i["id"] for i in outs[0]["items"]} >= {F.T3, F.D1} and outs[1]["total"] == 2
   and outs[2]["deliverable"]["id"] == F.D1 and outs[3]["total"] == 2
   and {i["id"] for i in outs[4]["items"]} == {F.T1, F.T2, F.T3} and "PPMX_MY_NAME" in outs[4]["me"]["matched_by"],
   "stdio: the new reads, and PPMX_MY_NAME counts as \"me\" on the owner's own server", p.stdout[-400:] + p.stderr[-300:])
logged = [json.loads(x).get("tool") for x in p.stderr.splitlines() if x.startswith("{")]
ok(all(n in logged for n in ("list_my_work", "list_deliverables", "get_deliverable", "list_resources")) and ALEX not in p.stderr,
   "stdio: an audit line for each new tool on standard error, without the token", str(logged))

# ---- kit-ppmx
kit = tmp / "kit"
(kit / ".install/shared/morning").mkdir(parents=True)
KP = [sys.executable, str(SHARED / "bin/kit-ppmx")]
DESKTOP = tmp / "Claude" / "claude_desktop_config.json"
kenv = {**env, "KIT_DIR": str(kit), "PPMX_TOKEN_KEYCHAIN": "off", "PPMX_TODAY": "2026-10-30",
        "CLAUDE_DESKTOP_CONFIG": str(DESKTOP)}


def kp(*args, **extra):
    r = subprocess.run(KP + list(args), capture_output=True, text=True, encoding="utf-8", timeout=60,
                       env={**kenv, **extra})
    return r.returncode, r.stdout, r.stderr


rc, o, e = kp("tools")
ok(rc == 0 and len(o.splitlines()) == 25 and o.startswith("get_current_user") and o.count("[changes PPM Express]") == 11,
   "kit-ppmx tools: all 25, the 11 that change PPM Express marked")
rc, o, e = kp("check")
ok(rc == 2 and "PPMX_BASE_URL" in e, "kit-ppmx check with no address: exit 2, says what to set", e)
(kit / ".install/shared/morning/config").write_text(f'OWNER_NAME="Alex"\nPPMX_BASE_URL="{BASE}"\nPPMX_TOKEN="{ALEX}"\n')
rc, o, e = kp("check")
ok(rc == 2 and "No personal access token" in e, "a token in Kit's config is ignored", o + e)
rc, o, e = kp("check", PPMX_TOKEN=ALEX)
ok(rc == 0 and "arivera@example.com" in o and "31-Jan-2027" in o and "project:write" in o and "scopes allow them" in o
   and ALEX not in o + e, "kit-ppmx check: who, when the token expires, its scopes, whether it can change things", o + e)
rc, o, e = kp("check", PPMX_TOKEN=BLAKE)
ok(rc == 0 and "no write scopes" in o, "kit-ppmx check: a read-only token is called that")
rc, o, e = kp("check", PPMX_TOKEN="token-nobody-999")
ok(rc == 1 and "Automation" in e, "kit-ppmx check with a rejected token: exit 1", e)
rc, o, e = kp("call", "list_projects", '{"limit": 1}', PPMX_TOKEN=ALEX)
ok(rc == 0 and json.loads(o)["total"] == 3, "kit-ppmx call prints a tool's JSON", o + e)
rc, o, e = kp("call", "list_projects", "{oops", PPMX_TOKEN=ALEX)
ok(rc == 2 and "JSON" in e, "kit-ppmx call with bad JSON")
rc, o, e = kp("call", "create_task", json.dumps({"project_id": F.A1, "name": "x"}), PPMX_TOKEN=ALEX, PPMX_WRITES="off")
ok(rc == 1 and "read-only" in e, "kit-ppmx call: a change with PPMX_WRITES=off is refused")
rc, o, e = kp("setup", PPMX_TOKEN=ALEX, PPMX_TOKEN_KEYCHAIN="PPMX_TOKEN")
ok(rc == 0 and "claude mcp add --scope user ppmx --env PYTHONUTF8=1 --" in o and "kit-ppmx desktop" in o
   and "mcp__ppmx__get_current_user" in o and "now: found" in o and ALEX not in o
   and ("cmdkey /generic:" in o if os.name == "nt" else "cmdkey" not in o),
   "kit-ppmx setup: Claude Code, Claude Desktop, the guard, the token found and never shown", o[-400:])
p = subprocess.run(KP + ["serve"], input=json.dumps(lines[3]) + "\n", capture_output=True, text=True, encoding="utf-8", timeout=60,
                   env={**kenv, "PPMX_TOKEN": BLAKE})
res = json.loads(p.stdout)["result"]
ok(not res["isError"] and json.loads(res["content"][0]["text"])["total"] == 1, "kit-ppmx serve: stdio with the address from Kit's config")
logs = list((kit / "audit").glob("ppmx-*.jsonl"))
entries = [json.loads(x) for f in logs for x in f.read_text(encoding="utf-8").splitlines()]
ok(any(x.get("via") == "stdio" and x.get("tool") == "list_projects" for x in entries)
   and BLAKE not in json.dumps(entries) and ALEX not in json.dumps(entries),
   "kit-ppmx serve records each call in Kit's audit folder (ppmx-YYYY-MM.jsonl), with no token", str(entries)[:300])
p = subprocess.run(KP + ["serve"], input=json.dumps(lines[3]) + "\n", capture_output=True, text=True, encoding="utf-8", timeout=60, env=kenv)
res = json.loads(p.stdout)["result"]
ok(res["isError"] and "kit-ppmx setup" in res["content"][0]["text"], "kit-ppmx serve without a token: points to setup")

p = subprocess.run(KP + ["serve"], input="\n".join(json.dumps(x) for x in calls[:4]) + "\n", capture_output=True, text=True,
                   encoding="utf-8", timeout=60, env={**kenv, "PPMX_TOKEN": ALEX})
outs = [json.loads(x)["result"] for x in p.stdout.splitlines() if x.strip()]
ok(len(outs) == 4 and not any(o["isError"] for o in outs) and '"tool": "list_my_work"' in p.stderr,
   "kit-ppmx serve: the new reads work, each logged", p.stdout[-300:] + p.stderr[-300:])

# Claude Desktop's config
DESKTOP.parent.mkdir(parents=True)
DESKTOP.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}))
rc, o, e = kp("desktop")
cfgd = json.loads(DESKTOP.read_text())
entry = cfgd["mcpServers"].get("ppmx", {})
ok(rc == 0 and cfgd["mcpServers"]["other"] == {"command": "x"} and cfgd["theme"] == "dark"
   and entry.get("command") == sys.executable and entry.get("args", [None])[-1] == "serve"
   and pathlib.Path(entry["args"][0]).name == "kit-ppmx" and "env" in entry and "PPMX_TOKEN" not in json.dumps(entry),
   "kit-ppmx desktop: adds the server, keeps everything else, and holds no token", o + e)
ok(any((kit / ".install/backups").glob("*-claude-desktop/claude_desktop_config.json")), "kit-ppmx desktop: backs up the config first")
rc, o, e = kp("desktop")
ok(rc == 0 and "already" in o, "kit-ppmx desktop again: nothing to change")
rc, o, e = kp("desktop", "--print")
ok(rc == 0 and json.loads(o)["mcpServers"]["ppmx"] == entry, "kit-ppmx desktop --print: shows the entry")
rc, o, e = kp("desktop", "--remove")
ok(rc == 0 and json.loads(DESKTOP.read_text())["mcpServers"] == {"other": {"command": "x"}}, "kit-ppmx desktop --remove")
DESKTOP.write_text("{not json")
rc, o, e = kp("desktop")
ok(rc == 2 and DESKTOP.read_text() == "{not json", "a config that isn't JSON is left as it is")

# Windows Credential Manager, for real, on Windows
if os.name == "nt" and shutil.which("cmdkey"):
    target = f"kit-ppmx-test-{uuid.uuid4().hex[:8]}"
    added = subprocess.run(["cmdkey", f"/generic:{target}", "/user:kit", f"/pass:{ALEX}"], capture_output=True, text=True)
    if added.returncode != 0:
        print(f"skip Windows Credential Manager: cmdkey couldn't store a credential here ({added.stdout.strip()[:100]})")
    else:
        try:
            rc, o, e = kp("check", PPMX_TOKEN_KEYCHAIN=target)
            ok(rc == 0 and "arivera@example.com" in o and ALEX not in o + e, "Windows: the token from Credential Manager", o + e)
        finally:
            subprocess.run(["cmdkey", f"/delete:{target}"], capture_output=True, text=True)
        rc, o, e = kp("check", PPMX_TOKEN_KEYCHAIN=target)
        ok(rc == 2 and "Credential Manager entry" in e, "Windows: no entry, and the message names the store", e)

# ---- every path logs both reads and writes: one audit line per tool call, no token, no values
READ = {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "list_projects", "arguments": {"limit": 1}}}
WRITE = {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
         "params": {"name": "create_task", "arguments": {"project_id": F.A1, "name": "Audit both ways"}}}


def per_tool(entries):
    return [sum(1 for x in entries if x.get("tool") == t) for t in ("list_projects", "create_task")]


both = "\n".join(json.dumps(x) for x in (READ, WRITE)) + "\n"
p = subprocess.run([sys.executable, "-m", "ppmx", "stdio"], cwd=SHARED, input=both, capture_output=True, text=True,
                   encoding="utf-8", timeout=60, env={**env, "PPMX_BASE_URL": WBASE, "PPMX_TOKEN": ALEX})
lines_ = [json.loads(x) for x in p.stderr.splitlines() if x.startswith("{")]
ok(per_tool(lines_) == [1, 1] and ALEX not in p.stderr and "Audit both ways" not in p.stderr,
   "python -m ppmx stdio: one audit line for a read and one for a write, on standard error", p.stderr[-300:])
hlog = []
happ = make_app(Settings({"PPMX_BASE_URL": WBASE}), log=hlog.append)
hsrv = make_server("127.0.0.1", 0, happ, handler_class=Quiet)
threading.Thread(target=hsrv.serve_forever, daemon=True).start()
for body in (READ, WRITE):
    urllib.request.urlopen(urllib.request.Request(
        f"http://127.0.0.1:{hsrv.server_address[1]}/mcp", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                 "X-PPMX-Token": ALEX}), timeout=20).read()
hsrv.shutdown()
ok(per_tool(hlog) == [1, 1] and ALEX not in json.dumps(hlog) and "Audit both ways" not in json.dumps(hlog),
   "server_http (OpenShift): one audit line for a read and one for a write", str(hlog)[:300])
ok(Settings({}).audit and not Settings({"PPMX_AUDIT": "off"}).audit, "PPMX_AUDIT is on unless set off")


def kit_audit_lines():
    return [json.loads(x) for f in (kit / "audit").glob("ppmx-*.jsonl") for x in f.read_text(encoding="utf-8").splitlines()]


before = kit_audit_lines()
p = subprocess.run(KP + ["serve"], input=both, capture_output=True, text=True, encoding="utf-8", timeout=60,
                   env={**kenv, "PPMX_BASE_URL": WBASE, "PPMX_TOKEN": ALEX})
new = kit_audit_lines()[len(before):]
ok(per_tool(new) == [1, 1] and per_tool([json.loads(x) for x in p.stderr.splitlines() if x.startswith("{")]) == [1, 1]
   and ALEX not in json.dumps(new) + p.stderr, "kit-ppmx serve: a read and a write each logged, in the file and on stderr",
   str(new)[:300])
before = kit_audit_lines()
kp("call", "list_projects", '{"limit": 1}', PPMX_BASE_URL=WBASE, PPMX_TOKEN=ALEX)
kp("call", "create_task", json.dumps({"project_id": F.A1, "name": "Audit both ways"}), PPMX_BASE_URL=WBASE, PPMX_TOKEN=ALEX)
new = kit_audit_lines()[len(before):]
ok(per_tool(new) == [1, 1] and "Audit both ways" not in json.dumps(new),
   "kit-ppmx call: a read and a write each logged", str(new)[:300])
before = kit_audit_lines()
kp("call", "list_projects", '{"limit": 1}', PPMX_BASE_URL=WBASE, PPMX_TOKEN=ALEX, PPMX_AUDIT="off")
ok(per_tool(kit_audit_lines()[len(before):]) == [1, 0], "PPMX_AUDIT=off quiets standard error, never Kit's audit file")

# ---- wired into Kit: a command on both platforms, and Claude Code's permission rules
import kit_setup  # noqa: E402

loop = [ln for ln in (REPO / "platform/mac/install.sh").read_text(encoding="utf-8").splitlines()
        if ln.startswith("for tool in ")]
ok(bool(loop) and "kit-ppmx" in loop[0].split(";")[0].split(), "install.sh links kit-ppmx into ~/.local/bin")
ok('"kit-ppmx"' in (REPO / "platform/windows/install.ps1").read_text(encoding="utf-8"),
   "install.ps1 makes a kit-ppmx command")
ok({"Bash(kit-ppmx check)", "Bash(kit-ppmx tools)", "Bash(kit-ppmx setup)"} <= set(kit_setup.ALLOW)
   and {"Bash(kit-ppmx call *)", "Bash(kit-ppmx desktop)", "Bash(kit-ppmx desktop *)"} <= set(kit_setup.ASK)
   and not any(w in r for r in kit_setup.ALLOW for w in ("kit-ppmx call", "kit-ppmx serve", "kit-ppmx desktop", "mcp__ppmx")),
   "Claude Code may run kit-ppmx check, tools, and setup; call and desktop ask first")
ok({f"mcp__ppmx__{n}" for n in WRITE_TOOLS} <= set(kit_setup.ASK), "every PPM Express change asks in Claude Code")

for srv in (httpd, unset, wserver, server):
    srv.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
print(f"\nppmx tests: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)

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
ALEX, BLAKE, BUSY = "token-alex-0001", "token-blake-0002", "token-busy-0003"
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
ok(len(got["data"]) == 3, "a paged list is followed through its next link", str(got)[:200])
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
ok(raises(lambda: client._request(ALEX, BASE + "/Redirect"), PPMXError, "redirected"), "a redirect isn't followed")
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
ok(me["email"] == "alex@example.com" and "Write Projects" in me["token"]["scopes"]
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
ok(r["total"] == 1 and r["items"][0]["AssignedTo"]["name"] == "Sam Lee", "filter tasks by assignee (a person record)")
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

# ---- the MCP side
d = Dispatcher(lambda t: Context(client, settings, codes.load(), t, hint="no token"))
init = d.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
ok(init["result"]["protocolVersion"] == "2025-06-18" and init["result"]["capabilities"] == {"tools": {"listChanged": False}}
   and "go ahead only when they agree" in init["result"]["instructions"],
   "initialize: the caller's protocol version, and instructions to confirm changes")
init = d.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
ok(init["id"] == 0 and init["result"]["protocolVersion"] == PROTOCOL_VERSIONS[0], "an unknown version gets the newest (and id 0 works)")
listed = {t["name"]: t for t in d.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]}
ok(len(listed) == len(TOOLS) == 22 and len(WRITE_TOOLS) == 11
   and all(listed[n]["annotations"]["readOnlyHint"] for n in READS)
   and not any(listed[n]["annotations"]["readOnlyHint"] for n in WRITE_TOOLS)
   and all(t["inputSchema"]["additionalProperties"] is False for t in listed.values()),
   "tools/list: 11 reads and 11 writes, each marked for what it does, closed schemas")
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
ok(last_write() == ("alex", "POST", f"Projects/{F.A1}/Tasks", {"attributes": {
    "Status": 1, "Progress": 2, "AssignedTo": [{"search": "sam@example.com"}], "DueDate": "2026-11-20",
    "Tags": ["#network", "#infra"], "Name": "Rack the switches"}}),
   "create_task: POST {attributes}, labels sent as numbers, a person as a search, tags with #", str(last_write()))
ok(r["result"] == "created" and r["kind"] == "task" and len(r["id"]) == 36 and r["record"]["Status"] == "At Risk"
   and r["fields"] == ["AssignedTo", "DueDate", "Name", "Progress", "Status", "Tags"],
   "create_task: the new ID, the record as PPM Express has it, and the field names", str(r)[:300])
ok(run_tool("list_tasks", {"project_id": F.A1}, w)["total"] == 5, "a write clears the caller's cache: the next read sees it")
r = run_tool("update_task", {"project_id": F.A1, "task_id": F.T1, "fields": {"Status": "Done", "Progress": "Completed"}}, w)
ok(last_write() == ("alex", "PATCH", f"Projects/{F.A1}/Tasks/{F.T1}", {"updates": {"Status": 10, "Progress": 1}})
   and r["result"] == "updated" and r["id"] == F.T1 and r["record"]["Status"] == "Done",
   "update_task: PATCH {updates} with only the fields given", str(last_write()))
ok(raises(lambda: run_tool("update_task", {"project_id": F.A1, "task_id": F.T4, "fields": {"Status": "Done"}}, w),
          PPMXError, "synced from Jira"), "PPM Express's own refusal comes through (a Jira-synced task)")
run_tool("create_task", {"project_id": F.A1, "name": "Label the cables", "parent_task_id": F.T3}, w)
ok(last_write() == ("alex", "POST", f"Projects/{F.A1}/Tasks/bulk", [{"ParentID": F.T3, "attributes": {"Name": "Label the cables"}}]),
   "a sub-task goes as a list of {ParentID, attributes}", str(last_write()))
r = run_tool("create_key_date", {"project_id": F.A1, "name": "Cutover", "date": "2026-12-05", "type": "Milestone"}, w)
ok(last_write()[3] == {"attributes": {"Date": "2026-12-05", "Type": 1, "Name": "Cutover"}} and r["record"]["Type"] == "Milestone",
   "create_key_date: the date, and the type as its number", str(last_write()))
run_tool("update_key_date", {"project_id": F.A1, "key_date_id": F.K2, "fields": {"Date": "2026-12-01"}}, w)
ok(last_write()[1:] == ("PATCH", f"Projects/{F.A1}/KeyDates/{F.K2}", {"updates": {"Date": "2026-12-01"}}), "update_key_date")
r = run_tool("create_project", {"name": "Badge readers", "fields": {
    "Manager": "Alex Rivera", "Portfolios": ["Infrastructure", F.P2], "StartDate": "2027-01-04"}}, w)
ok(last_write()[1:] == ("POST", "Projects", {"attributes": {
    "Manager": [{"search": "Alex Rivera"}], "Portfolios": [{"search": "Infrastructure"}, {"id": F.P2}],
    "StartDate": "2027-01-04", "Name": "Badge readers"}}), "create_project: the manager and portfolios as references (an ID as an id)",
   str(last_write()))
run_tool("update_project", {"project_id": F.A2, "fields": {"OverallStatus": "At Risk"}}, w)
ok(last_write()[1:] == ("PATCH", f"Projects/{F.A2}", {"updates": {"OverallStatus": 1}}), "update_project")
run_tool("create_idea", {"name": "Chat intake", "challenge_id": F.C1}, w)
ok(last_write()[1:3] == ("POST", "Ideas"), "create_idea")
ok(any(i["attributes"]["Name"] == "Chat intake" and i.get("challengeId") == F.C1 for i in wfake.data["ideas"]),
   "create_idea under a challenge (challengeId in the query)")
run_tool("update_idea", {"idea_id": F.I1, "fields": {"Description": "One place to ask."}}, w)
ok(last_write()[1:] == ("PATCH", f"Ideas/{F.I1}", {"updates": {"Description": "One place to ask."}}), "update_idea")
r = run_tool("set_idea_stage", {"idea_id": F.I1, "stage": "Selected"}, w)
ok(last_write()[1:] == ("POST", f"Ideas/{F.I1}/Stage", {"Stage": 3}) and r["record"]["Stage"] == "Selected",
   "set_idea_stage: POST {Stage: n} from the stage's name")
ok(raises(lambda: run_tool("set_idea_stage", {"idea_id": F.I1, "stage": 1}, w), PPMXError, "can't move back"),
   "a stage move PPM Express won't make: its reason comes through")
ok(raises(lambda: run_tool("set_idea_stage", {"idea_id": F.I1, "stage": "Maybe"}, w), ToolError, "one of: Draft"),
   "an unknown stage is refused before anything is sent")
run_tool("create_record", {"kind": "resource", "name": "Pat Kim", "fields": {"Email": "pat@example.com"}}, w)
ok(last_write()[1:] == ("POST", "Resources", {"attributes": {"Email": "pat@example.com", "Name": "Pat Kim"}}), "create_record: a resource")
run_tool("update_record", {"kind": "portfolio", "record_id": F.P2, "fields": {"OverallStatus": "On Track"}}, w)
ok(last_write()[1:] == ("PATCH", f"Portfolios/{F.P2}", {"updates": {"OverallStatus": 0}}), "update_record: a portfolio")
n = len(wfake.writes)
ok(raises(lambda: run_tool("update_task", {"project_id": F.A1, "task_id": F.T1, "fields": {}}, w), ToolError, "required")
   and raises(lambda: run_tool("update_task", {"project_id": F.A1, "task_id": F.T1, "fields": {"bad key!": 1}}, w),
              ToolError, "isn't a field key")
   and raises(lambda: run_tool("create_key_date", {"project_id": F.A1, "name": "x", "date": "05/12/2026"}, w), ToolError, "YYYY-MM-DD")
   and len(wfake.writes) == n, "empty changes, odd field keys, and bad dates are refused before anything is sent")
ok(raises(lambda: run_tool("create_task", {"project_id": F.A1, "name": "x"}, Context(wclient, wsettings, {}, BLAKE)),
          PPMXError, "write scopes"), "a token without write scopes: PPM Express refuses, and the message says why")
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
ok(not err and json.loads(a)["email"] == "blake@example.com", "HTTP: a token as Authorization: Bearer")
err, a = tool("get_current_user", {}, {"X-PPMX-Token": ALEX, "Authorization": "Bearer something-for-sso"})
ok(not err and json.loads(a)["email"] == "alex@example.com", "HTTP: X-PPMX-Token wins over Authorization (left to sign-on)")
err, a = tool("list_projects", {}, {})
ok(err and "X-PPMX-Token" in a, "HTTP: no token, and the tool says how to send one")
err, a = tool("list_projects", {}, {"X-PPMX-Token": "bad token"})
ok(err and "isn't valid" in a, "HTTP: a malformed token is refused")
err, a = tool("create_task", {"project_id": F.A1, "name": "Order fiber"}, {"X-PPMX-Token": ALEX})
err2, b = tool("create_task", {"project_id": F.A1, "name": "Order fiber"}, {"X-PPMX-Token": BLAKE})
ok(not err and json.loads(a)["result"] == "created" and err2 and "write scopes" in b,
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
ok(rc == 0 and len(o.splitlines()) == 22 and o.startswith("get_current_user") and o.count("[changes PPM Express]") == 11,
   "kit-ppmx tools: all 22, the 11 that change PPM Express marked")
rc, o, e = kp("check")
ok(rc == 2 and "PPMX_BASE_URL" in e, "kit-ppmx check with no address: exit 2, says what to set", e)
(kit / ".install/shared/morning/config").write_text(f'OWNER_NAME="Alex"\nPPMX_BASE_URL="{BASE}"\nPPMX_TOKEN="{ALEX}"\n')
rc, o, e = kp("check")
ok(rc == 2 and "No personal access token" in e, "a token in Kit's config is ignored", o + e)
rc, o, e = kp("check", PPMX_TOKEN=ALEX)
ok(rc == 0 and "alex@example.com" in o and "31-Jan-2027" in o and "Write Projects" in o and "scopes allow them" in o
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
ok(rc == 0 and "claude mcp add --scope user --env PYTHONUTF8=1 ppmx --" in o and "kit-ppmx desktop" in o
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
            ok(rc == 0 and "alex@example.com" in o and ALEX not in o + e, "Windows: the token from Credential Manager", o + e)
        finally:
            subprocess.run(["cmdkey", f"/delete:{target}"], capture_output=True, text=True)
        rc, o, e = kp("check", PPMX_TOKEN_KEYCHAIN=target)
        ok(rc == 2 and "Credential Manager entry" in e, "Windows: no entry, and the message names the store", e)

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

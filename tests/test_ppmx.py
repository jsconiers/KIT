#!/usr/bin/env python3
"""Tests for the PPM Express MCP server (shared/ppmx) and Kit's command for it (kit-ppmx), against the fake
PPM Express in tests/fake_ppmx.py: the settings, the client (tokens, paging, retries, the per-caller cache,
pacing, no redirects), the tools and their arguments, the code tables, the MCP side, both servers (stdio
and HTTP, with two callers), the connector guard's view of the tool names, and how Kit installs kit-ppmx
(the install lists and Claude Code's permission rules). Nothing reaches the network or the Keychain.

Run: python3 tests/test_ppmx.py
"""
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request

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
from ppmx.tools import TOOLS, Context, ToolError, run_tool  # noqa: E402

PASS = FAIL = 0
ALEX, BLAKE, BUSY = "token-alex-0001", "token-blake-0002", "token-busy-0003"
F = fake_ppmx


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
CODES.write_text(json.dumps({"Status": {"1": "In progress", "2": "Completed"},
                             "OverallStatus": {"1": "On track", "2": "At risk", "3": "Late"}}))

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
naps.clear()
client.get(BUSY, "me")
ok(naps == [0], "429 with Retry-After: waits as told, then retries", str(naps))
ok(raises(lambda: client._request(ALEX, BASE + "/Redirect"), PPMXError, "redirected"), "a redirect isn't followed")
ok(raises(lambda: Client(Settings({})).get(ALEX, "me"), PPMXError, "PPMX_BASE_URL"), "no address: says so")


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

# ---- tools
plain = Context(client, settings, codes.load(), ALEX)
coded = Context(client, settings, codes.load(str(CODES)), ALEX)
me = run_tool("get_current_user", {}, plain)
ok(me["email"] == "alex@example.com" and me["token"]["scopes"] == ["Read Projects", "Read Resources"]
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
r = run_tool("list_projects", {"status": "on track"}, coded)
ok(r["total"] == 2 and r["items"][0]["OverallStatus"] == "On track" and r["items"][0]["codes"] == {"OverallStatus": 1},
   "code tables: labels for numbers, the number kept in codes, and filtering by label", str(r["items"][:1]))
r = run_tool("list_projects", {"fields": ["Description"], "name_contains": "network"}, plain)
ok(r["items"][0]["Description"] == "Replace the core switches.", "fields: more attributes when asked")
r = run_tool("get_project", {"project_id": F.A1, "include": ["key_dates", "tasks"]}, plain)
ok(r["project"]["Name"] == "Network refresh" and r["key_dates"]["total"] == 3 and r["tasks"]["total"] == 4
   and "notes" in r, "get_project with key dates and tasks; unmapped codes keep tasks open, and say so")
r = run_tool("get_project", {"project_id": F.A1, "include": ["tasks"]}, coded)
ok(r["tasks"]["total"] == 3 and "notes" not in r, "with code tables, finished tasks drop out")
r = run_tool("list_tasks", {"project_id": F.A1, "overdue_only": True}, coded)
ok(r["total"] == 1 and r["items"][0]["Name"] == "Order switches", "overdue tasks (today 30-Oct-2026)", str(r)[:300])
r = run_tool("list_tasks", {"project_id": F.A1, "due_within_days": 14}, coded)
ok(r["total"] == 1 and r["items"][0]["Name"] == "Cutover plan", "tasks due within 14 days")
r = run_tool("list_tasks", {"project_id": F.A1, "assignee": "sam"}, plain)
ok(r["total"] == 1 and r["items"][0]["AssignedTo"]["name"] == "Sam Lee", "filter tasks by assignee (a person record)")
r = run_tool("list_key_dates", {"project_id": F.A1, "upcoming_days": 45}, plain)
ok(r["total"] == 1 and r["items"][0]["Name"] == "Go-live", "upcoming key dates")
r = run_tool("list_key_dates", {"project_id": F.A1, "overdue_only": True}, coded)
ok(r["total"] == 1 and r["items"][0]["Name"] == "Vendor contract", "overdue key dates leave out finished ones")
r = run_tool("list_ideas", {"challenge_id": F.C1}, plain)
ok(r["total"] == 1 and r["items"][0]["Name"] == "AI triage", "ideas for one challenge")
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
ok(raises(lambda: codes.load(str(tmp / "missing.json")), codes.CodesError), "a missing code file is a clear error")

# ---- the connector guard lets every tool through as read-only
guard_path = SHARED / "bin/connector-guard"
loader = importlib.machinery.SourceFileLoader("connector_guard", str(guard_path))
spec = importlib.util.spec_from_loader("connector_guard", loader)
guard = importlib.util.module_from_spec(spec)
loader.exec_module(guard)
cfg = {"allowed_servers": ["ppmx"], "allow_tools": [], "deny_tools": []}
verdicts = {t["name"]: guard.decide(cfg, f"mcp__ppmx__{t['name']}")[0] for t in TOOLS}
ok(set(verdicts.values()) == {"allow"}, "the connector guard reads every tool name as read-only", str(verdicts))

# ---- the MCP side
d = Dispatcher(lambda t: Context(client, settings, {}, t, hint="no token"))
init = d.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
ok(init["result"]["protocolVersion"] == "2025-06-18" and init["result"]["capabilities"] == {"tools": {"listChanged": False}},
   "initialize: the caller's protocol version when it's known")
init = d.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
ok(init["id"] == 0 and init["result"]["protocolVersion"] == PROTOCOL_VERSIONS[0], "an unknown version gets the newest (and id 0 works)")
listed = d.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
ok(len(listed) == len(TOOLS) == 10 and all(t["annotations"]["readOnlyHint"] and not t["annotations"]["destructiveHint"]
                                           and t["inputSchema"]["additionalProperties"] is False for t in listed),
   "tools/list: ten tools, all read-only, closed schemas")
ok(d.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None, "notifications get no answer")
ok(d.handle({"id": 3, "method": "ping"})["error"]["code"] == -32600, "a message without jsonrpc 2.0 is invalid")
ok(d.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "delete_project"}})["error"]["code"] == -32602,
   "an unknown tool is a protocol error")
res = d.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "list_projects", "arguments": {}}}, ALEX)["result"]
ok(res["isError"] is False and json.loads(res["content"][0]["text"])["total"] == 3, "tools/call returns the tool's JSON")
res = d.handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "list_projects"}}, "")["result"]
ok(res["isError"] is True and res["content"][0]["text"] == "no token", "a tool error comes back as isError")
ok(d.handle({"jsonrpc": "2.0", "id": 7, "method": "resources/list"})["error"]["code"] == -32601, "other methods: not found")

# ---- stdio: python -m ppmx stdio
lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
         {"jsonrpc": "2.0", "method": "notifications/initialized"},
         {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
         {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_projects", "arguments": {"limit": 1}}}]
env = {k: v for k, v in os.environ.items() if not k.startswith("PPMX_")}
p = subprocess.run([sys.executable, "-m", "ppmx", "stdio"], cwd=SHARED, input="\n".join(json.dumps(x) for x in lines) + "\n",
                   capture_output=True, text=True, timeout=60, env={**env, **ENV, "PPMX_TOKEN": ALEX})
out = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]
ok(p.returncode == 0 and [o["id"] for o in out] == [1, 2, 3] and json.loads(out[2]["result"]["content"][0]["text"])["total"] == 3,
   "stdio: initialize, tools/list, and a call, one line each", p.stdout[-300:] + p.stderr[-300:])
p = subprocess.run([sys.executable, "-m", "ppmx", "stdio"], cwd=SHARED, input=json.dumps(lines[3]) + "\n",
                   capture_output=True, text=True, timeout=60, env={**env, **ENV})
res = json.loads(p.stdout)["result"]
ok(res["isError"] and "PPMX_TOKEN" in res["content"][0]["text"], "stdio without a token: says which variable to set")

# ---- HTTP: the standalone app, two callers
audit = []
app = make_app(Settings(ENV), log=audit.append)
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
ok(not err and not err2 and json.loads(a)["total"] == 3 and json.loads(b)["total"] == 1, "HTTP: each caller sees only their own")
err, a = tool("get_current_user", {}, {"Authorization": f"Bearer {BLAKE}"})
ok(not err and json.loads(a)["email"] == "blake@example.com", "HTTP: a token as Authorization: Bearer")
err, a = tool("get_current_user", {}, {"X-PPMX-Token": ALEX, "Authorization": "Bearer something-for-sso"})
ok(not err and json.loads(a)["email"] == "alex@example.com", "HTTP: X-PPMX-Token wins over Authorization (left to sign-on)")
err, a = tool("list_projects", {}, {})
ok(err and "X-PPMX-Token" in a, "HTTP: no token, and the tool says how to send one")
err, a = tool("list_projects", {}, {"X-PPMX-Token": "bad token"})
ok(err and "isn't valid" in a, "HTTP: a malformed token is refused")
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
bare = make_server("127.0.0.1", 0, make_app(Settings({}), log=lambda e: None), handler_class=Quiet)
threading.Thread(target=bare.serve_forever, daemon=True).start()
try:
    urllib.request.urlopen(f"http://127.0.0.1:{bare.server_address[1]}/readyz", timeout=5)
    status = 200
except urllib.error.HTTPError as e:
    status, why = e.code, json.loads(e.read())["reason"]
ok(status == 503 and "PPMX_BASE_URL" in why, "HTTP: /readyz is 503 until PPMX_BASE_URL is set")
text = json.dumps(audit)
ok(audit and ALEX not in text and BLAKE not in text and any(e.get("tool") == "list_projects" and e.get("user", "").startswith("u:")
                                                            for e in audit),
   "HTTP: the audit log has calls by a user hash, and no token", text[:300])
ok(all("arguments" not in e and "args" in e for e in audit if e.get("tool")), "HTTP: the audit log names arguments, not values")
users = {e["user"] for e in audit if e.get("tool") == "list_projects" and e.get("outcome") == "ok"}
ok(len(users) == 2, "HTTP: two callers, two user hashes", str(users))

# ---- kit-ppmx
kit = tmp / "kit"
(kit / ".install/shared/morning").mkdir(parents=True)
KP = [sys.executable, str(SHARED / "bin/kit-ppmx")]
kenv = {**env, "KIT_DIR": str(kit), "PPMX_TOKEN_KEYCHAIN": "off", "PPMX_TODAY": "2026-10-30"}


def kp(*args, **extra):
    r = subprocess.run(KP + list(args), capture_output=True, text=True, timeout=60, env={**kenv, **extra})
    return r.returncode, r.stdout, r.stderr


rc, o, e = kp("tools")
ok(rc == 0 and len(o.splitlines()) == 10 and o.startswith("get_current_user"), "kit-ppmx tools")
rc, o, e = kp("check")
ok(rc == 2 and "PPMX_BASE_URL" in e, "kit-ppmx check with no address: exit 2, says what to set", e)
(kit / ".install/shared/morning/config").write_text(f'OWNER_NAME="Alex"\nPPMX_BASE_URL="{BASE}"\nPPMX_TOKEN="{ALEX}"\n')
rc, o, e = kp("check")
ok(rc == 2 and "No personal access token" in e, "a token in Kit's config is ignored", o + e)
rc, o, e = kp("check", PPMX_TOKEN=ALEX)
ok(rc == 0 and "alex@example.com" in o and "31-Jan-2027" in o and "Read Projects" in o and ALEX not in o + e,
   "kit-ppmx check: who, when the token expires, its scopes, and never the token", o + e)
rc, o, e = kp("check", PPMX_TOKEN="token-nobody-999")
ok(rc == 1 and "Automation" in e, "kit-ppmx check with a rejected token: exit 1", e)
rc, o, e = kp("call", "list_projects", '{"limit": 1}', PPMX_TOKEN=ALEX)
ok(rc == 0 and json.loads(o)["total"] == 3, "kit-ppmx call prints a tool's JSON", o + e)
rc, o, e = kp("call", "list_projects", "{oops", PPMX_TOKEN=ALEX)
ok(rc == 2 and "JSON" in e, "kit-ppmx call with bad JSON")
rc, o, e = kp("setup", PPMX_TOKEN=ALEX)
ok(rc == 0 and "claude mcp add --scope user --env PYTHONUTF8=1 ppmx --" in o and "mcp__ppmx__get_current_user" in o
   and "now: found" in o and ALEX not in o, "kit-ppmx setup: the steps, the token found, and never shown", o[-400:])
p = subprocess.run(KP + ["serve"], input=json.dumps(lines[3]) + "\n", capture_output=True, text=True, timeout=60,
                   env={**kenv, "PPMX_TOKEN": BLAKE})
res = json.loads(p.stdout)["result"]
ok(not res["isError"] and json.loads(res["content"][0]["text"])["total"] == 1, "kit-ppmx serve: stdio with the address from Kit's config")
p = subprocess.run(KP + ["serve"], input=json.dumps(lines[3]) + "\n", capture_output=True, text=True, timeout=60, env=kenv)
res = json.loads(p.stdout)["result"]
ok(res["isError"] and "kit-ppmx setup" in res["content"][0]["text"], "kit-ppmx serve without a token: points to setup")

# ---- wired into Kit: a command on both platforms, and Claude Code's permission rules
import kit_setup  # noqa: E402

loop = [ln for ln in (REPO / "platform/mac/install.sh").read_text(encoding="utf-8").splitlines()
        if ln.startswith("for tool in ")]
ok(bool(loop) and "kit-ppmx" in loop[0].split(";")[0].split(), "install.sh links kit-ppmx into ~/.local/bin")
ok('"kit-ppmx"' in (REPO / "platform/windows/install.ps1").read_text(encoding="utf-8"),
   "install.ps1 makes a kit-ppmx command")
ok({"Bash(kit-ppmx check)", "Bash(kit-ppmx tools)", "Bash(kit-ppmx setup)"} <= set(kit_setup.ALLOW)
   and "Bash(kit-ppmx call *)" in kit_setup.ASK
   and not any("kit-ppmx call" in r or "kit-ppmx serve" in r for r in kit_setup.ALLOW),
   "Claude Code may run kit-ppmx check, tools, and setup; call asks first")

httpd.shutdown()
bare.shutdown()
server.shutdown()
print(f"\nppmx tests: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)

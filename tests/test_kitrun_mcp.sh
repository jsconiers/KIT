#!/bin/bash
# Tests kit-run's parity features against fakes only (a fake model server and a fake MCP server on
# 127.0.0.1 or stdio, in a throwaway Kit folder): MCP connectors over stdio and HTTP, the connector
# guard and other hooks, subagents along direct pairs, skills, KIT.md @imports, and approvals.
# No real API, no real MCP server, no real credential.
#   bash tests/test_kitrun_mcp.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'pkill -f "$S/" 2>/dev/null; pkill -f "fake_mcp_server.py --http $S" 2>/dev/null; rm -rf "$S"' EXIT
export KIT_PROVIDER_BACKOFF=0.05 KIT_PROVIDER_RETRIES=0 HERE S
python3 - <<'PY'
import importlib.machinery, json, os, pathlib, subprocess, sys, time
HERE = pathlib.Path(os.environ["HERE"]); S = pathlib.Path(os.environ["S"])
home = S / "home"; kit = S / "kit"; lib = S / "lib"
for d in ("agents", "briefs", "memory/context", ".install/logs", ".install/shared/bin"):
    (kit / d).mkdir(parents=True, exist_ok=True)
lib.mkdir(); home.mkdir()
(kit / "memory/context/library.md").write_text(f"- **Library root:** `{lib}`\n")
(kit / "memory/context/notes.md").write_text("Notes.\n")
for n in ("blocked.md", "denyjson.md", "askme.md", "flag.md", "fine.md"):
    (kit / "briefs" / n).write_text(f"content of {n}\n")
# KIT.md with imports: a nested import, a cycle back to KIT.md, a missing file, and one in a fence
(kit / "KIT.md").write_text("# Kit\nTop instructions.\n@prefs/INDEX.md\n@missing.md\n```\n@prefs/fenced.md\n```\n")
(kit / "prefs").mkdir()
(kit / "prefs/INDEX.md").write_text("Prefs index.\n@one.md\n@../KIT.md\n")
(kit / "prefs/one.md").write_text("Pref one: be brief.\n")
(kit / "prefs/fenced.md").write_text("SHOULD NOT APPEAR\n")
GUARD = HERE / "shared/bin/connector-guard"
HOOK = S / "hook.py"
HOOK.write_text('''import json, os, sys
d = json.load(sys.stdin)
open(os.environ["HOOK_LOG"], "a").write(json.dumps(d) + "\\n")
ev, path = d["hook_event_name"], str((d.get("tool_input") or {}).get("path", ""))
if ev == "PreToolUse":
    if path.endswith("blocked.md"):
        print("nope, not that file", file=sys.stderr); sys.exit(2)
    if path.endswith("denyjson.md"):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                          "permissionDecisionReason": "json says no"}})); sys.exit(0)
    if path.endswith("askme.md"):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                          "permissionDecisionReason": "check this one"}})); sys.exit(0)
if ev == "PostToolUse" and path.endswith("flag.md"):
    print(json.dumps({"decision": "block", "reason": "post-check flagged it"}))
if ev == "Stop":
    marker = os.environ["HOOK_LOG"] + ".stopped"
    if not os.path.exists(marker):
        open(marker, "w").write("1")
        print(json.dumps({"decision": "block", "reason": "write the summary line first"}))
sys.exit(0)
''')

def agent(name, extra="", body=None):
    (kit / "agents" / f"{name}.md").write_text(f"---\nname: {name}\ndescription: test\nmodel: opus\n{extra}---\n\n# {name}\n{body or 'Test agent ' + name + '.'}\n")

def guard_hooks(who):
    out = "hooks:\n"
    for ev, arg in (("PreToolUse", "pre"), ("PostToolUse", "post"), ("PostToolUseFailure", "fail")):
        out += (f"  {ev}:\n    - matcher: \"mcp__.*\"\n      hooks:\n        - type: command\n"
                f"          command: 'python3 \"{GUARD}\" {arg} {who}'\n")
    out += f"  Stop:\n    - hooks:\n        - type: command\n          command: 'python3 \"{GUARD}\" stop {who}'\n"
    return out

agent("guarded", "disallowedTools: Write, Bash\n" + guard_hooks("guarded"))
agent("unguarded", "disallowedTools: Write, Bash\n")
agent("hooked", "disallowedTools: Bash\nhooks:\n  PreToolUse:\n    - matcher: \"Read\"\n      hooks:\n        - type: command\n"
      f"          command: 'python3 \"{HOOK}\"'\n  PostToolUse:\n    - matcher: \"Read|Write\"\n      hooks:\n        - type: command\n"
      f"          command: 'python3 \"{HOOK}\"'\n  Stop:\n    - hooks:\n        - type: command\n          command: 'python3 \"{HOOK}\"'\n")
for n in ("ia-writer", "gds-writer", "librarian", "curator"):
    agent(n)
agent("skiller")
(kit / "memory/context/agents.md").write_text("""# Kit's staff

Work between agents goes through Kit, except for these direct pairs:

- The IA writer and the GDS writer talk to each other.
- The curator can go to the librarian, one way: the librarian answers but can't start a
  conversation.

Agents not named in a pair can't start or message other agents at all.
""")
skills = S / "skills/demo"; skills.mkdir(parents=True)
(skills / "SKILL.md").write_text("# Demo skill\nDemo skill instructions.\n")
(skills / "run.py").write_text("print('script ran')\n")
GCONF = S / "guard.json"
GCONF.write_text(json.dumps({"audit_dir": str(S / "audit"), "allowed_servers": ["fake"], "allow_tools": ["mcp__fake__fail_tool", "mcp__fake__err_tool"]}))

P = F = 0
def ok(c, name, detail=""):
    global P, F
    if c: P += 1; print("ok  ", name)
    else: F += 1; print("FAIL", name, str(detail)[:400])

def tool_use(name, inp, tid="t1"):
    return {"model": "claude-opus-5-5", "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}], "usage": {"input_tokens": 10, "output_tokens": 2}}
def done(text="Finished."):
    return {"model": "claude-opus-5-5", "stop_reason": "end_turn", "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 12, "output_tokens": 3}}

MCP_LOG = S / "mcp.jsonl"; HOOK_LOG = S / "hooks.jsonl"
def stdio_server(allow=("get_item", "search_items", "fail_tool", "err_tool")):
    return {"type": "stdio", "command": sys.executable, "args": [str(HERE / "tests/fake_mcp_server.py")],
            "env_from": {"FAKE_MCP_LOG": "TEST_MCP_LOG_PATH"}, "allow_tools": list(allow)}

n = [0]
def scenario(agent_name, anthropic, args=(), runcfg=None):
    n[0] += 1
    d = S / f"s{n[0]}"; d.mkdir()
    (d / "script.json").write_text(json.dumps({"anthropic": anthropic, "openai": []}))
    srv = subprocess.Popen([sys.executable, str(HERE / "tests/fake_llm_server.py"), str(d / "script.json"),
                            str(d / "port"), str(d / "log.jsonl")], env={**os.environ, "FAKE_EXPECT_CREDENTIAL": "test-credential"})
    for _ in range(50):
        if (d / "port").exists() and (d / "port").read_text(): break
        time.sleep(0.1)
    port = (d / "port").read_text()
    cfg = json.loads((HERE / "kit/models.json").read_text())
    cfg["providers"]["anthropic"].update(base_url=f"http://127.0.0.1:{port}", credential_env="KIT_TEST_CRED")
    (kit / "models.json").write_text(json.dumps(cfg))
    (kit / "kit-run.json").write_text(json.dumps(runcfg or {}))
    env = {**os.environ, "KIT_DIR": str(kit), "KIT_TEST_CRED": "test-credential", "HOME": str(home),
           "KIT_CONNECTOR_GUARD_CONFIG": str(GCONF), "TEST_MCP_LOG_PATH": str(MCP_LOG), "HOOK_LOG": str(HOOK_LOG)}
    env.pop("FAKE_MCP_LOG", None)
    r = subprocess.run([sys.executable, str(HERE / "shared/bin/kit-run"), agent_name, "Do the thing.", *args],
                       capture_output=True, text=True, env=env, timeout=90, stdin=subprocess.DEVNULL)
    srv.terminate(); srv.wait()
    reqs = [json.loads(l) for l in (d / "log.jsonl").read_text().splitlines()] if (d / "log.jsonl").exists() else []
    return r, reqs

def last_result(req):
    return req["body"]["messages"][-1]["content"][0]
def audit():
    f = sorted((kit / ".install/logs").glob("kit-run-*.jsonl"))
    return [json.loads(l) for l in f[-1].read_text().splitlines()] if f else []
def guard_log():
    f = sorted((S / "audit").glob("connectors-*.jsonl"))
    return [json.loads(l) for l in f[-1].read_text().splitlines()] if f else []
def mcp_log():
    return [json.loads(l) for l in MCP_LOG.read_text().splitlines()] if MCP_LOG.exists() else []

# ---- MCP over stdio, guarded by the connector guard -----------------------------------------
mcp = {"mcp": {"servers": {"fake": stdio_server()}}}
r, reqs = scenario("guarded", [tool_use("mcp__fake__get_item", {"id": "A1"}),
                               tool_use("mcp__fake__delete_item", {"id": "A1"}, "t2"),
                               tool_use("mcp__fake__fail_tool", {}, "t3"),
                               tool_use("mcp__fake__err_tool", {}, "t4"), done("Got it.")], runcfg=mcp)
offered = [t["name"] for t in reqs[0]["body"]["tools"]] if reqs else []
ok(r.returncode == 0 and r.stdout.strip() == "Got it.", "MCP: run finishes", r.stderr)
ok("mcp__fake__get_item" in offered and "mcp__fake__search_items" in offered, "MCP: allowlisted tools offered as mcp__<server>__<tool>", offered)
ok("mcp__fake__delete_item" not in offered, "MCP: a tool not on allow_tools isn't offered", offered)
res1 = last_result(reqs[1]); res2 = last_result(reqs[2]); res3 = last_result(reqs[3]); res4 = last_result(reqs[4])
ok("item A1: a test item" in res1["content"] and "Untrusted content" in res1["content"], "MCP: allowed call returns the server's text, marked untrusted", res1)
ok(res2.get("is_error") and "isn't allowed" in res2["content"], "MCP: calling a tool off the allowlist is refused", res2)
ok(res3.get("is_error") and "failed" in res3["content"] and "backend unavailable" in res3["content"], "MCP: a server error is reported as a failed call", res3)
ok("connector reported an error" in res4["content"], "MCP: an isError result is passed back flagged", res4)
calls = [m["recv"] for m in mcp_log() if m.get("recv", {}).get("method") == "tools/call"]
ok([c["params"]["name"] for c in calls] == ["get_item", "fail_tool", "err_tool"], "MCP: the refused tool never reached the server", calls)
methods = [m["recv"].get("method") for m in mcp_log() if "recv" in m]
ok(methods[:3] == ["initialize", "notifications/initialized", "tools/list"], "MCP: initialize, initialized notification, then tools/list", methods[:4])
init = next(m["recv"] for m in mcp_log() if m.get("recv", {}).get("method") == "initialize")
ok(init["params"]["protocolVersion"] == "2025-06-18" and init["params"]["clientInfo"]["name"] == "kit-run", "MCP: initialize sends protocolVersion and clientInfo")
ok(MCP_LOG.exists(), "MCP: env_from passed the named variable to the server")
g = guard_log()
pre = [e for e in g if e["event"] == "pre"]; post = [e for e in g if e["event"] == "post"]
ok([e["tool"] for e in pre] == ["mcp__fake__get_item", "mcp__fake__fail_tool", "mcp__fake__err_tool"] and all(e["decision"] == "allow" for e in pre),
   "hooks: connector guard pre ran on each connector call", [(e["tool"], e.get("decision")) for e in pre])
ok(any(e.get("hook") == "failure" and e["tool"] == "mcp__fake__fail_tool" for e in post), "hooks: PostToolUseFailure reached the guard as a failure record", post)
ok(any(e["tool"] == "mcp__fake__err_tool" and e.get("is_error") for e in post), "hooks: PostToolUse passed the isError result to the guard", post)
ok(any(e["event"] == "stop" for e in g), "hooks: Stop hook logged the end of the session")
ok(all(e.get("tool_use_id") for e in pre), "hooks: tool_use_id passed to the guard")

# guard denies a server that isn't allowed, even if kit-run's config allows it
GCONF.write_text(json.dumps({"audit_dir": str(S / "audit"), "allowed_servers": []}))
r, reqs = scenario("guarded", [tool_use("mcp__fake__get_item", {"id": "B2"}), done()], runcfg=mcp)
res = last_result(reqs[1])
ok(res.get("is_error") and "blocked by a hook" in res["content"] and "connector-guard" in res["content"], "hooks: guard deny (JSON permissionDecision) blocks the call", res)
GCONF.write_text(json.dumps({"audit_dir": str(S / "audit"), "allowed_servers": ["fake"], "allow_tools": ["mcp__fake__fail_tool", "mcp__fake__err_tool"]}))

# an agent with no guard hook gets no connector tools (require_guard), unless the config turns that off
r, reqs = scenario("unguarded", [done()], runcfg=mcp)
offered = [t["name"] for t in reqs[0]["body"]["tools"]]
ok(not any(t.startswith("mcp__") for t in offered), "MCP: unguarded agent gets no connector tools by default", offered)
r, reqs = scenario("unguarded", [done()], runcfg={"mcp": {"require_guard": False, "servers": {"fake": stdio_server()}}})
offered = [t["name"] for t in reqs[0]["body"]["tools"]]
ok("mcp__fake__get_item" in offered, "MCP: require_guard false offers them", offered)
# frontmatter disallowedTools can remove a whole server
agent("guarded2", "disallowedTools: Write, Bash, mcp__fake\n" + guard_hooks("guarded2"))
r, reqs = scenario("guarded2", [done()], runcfg=mcp)
ok(not any(t["name"].startswith("mcp__") for t in reqs[0]["body"]["tools"]), "MCP: disallowedTools mcp__<server> removes that server's tools")
# a server that won't start: reported, run continues
r, reqs = scenario("guarded", [done("ok anyway")], runcfg={"mcp": {"servers": {"fake": {"type": "stdio", "command": str(S / "no-such-cmd"), "allow_tools": ["get_item"]}}}})
ok(r.returncode == 0 and "connector fake unavailable" in reqs[0]["body"]["system"], "MCP: an unavailable server is noted, the run continues", r.stderr)

# ---- MCP over Streamable HTTP (JSON and SSE answers, session header, DELETE) ---------------------
for sse in ("0", "1"):
    MCP_LOG.unlink(missing_ok=True)
    pf = S / f"http-port-{sse}"
    hs = subprocess.Popen([sys.executable, str(HERE / "tests/fake_mcp_server.py"), "--http", str(pf)],
                          env={**os.environ, "FAKE_MCP_LOG": str(MCP_LOG), "FAKE_MCP_SSE": sse})
    for _ in range(50):
        if pf.exists() and pf.read_text(): break
        time.sleep(0.1)
    url = f"http://127.0.0.1:{pf.read_text()}/mcp"
    r, reqs = scenario("guarded", [tool_use("mcp__fake__get_item", {"id": "H" + sse}), done()],
                       runcfg={"mcp": {"servers": {"fake": {"type": "http", "url": url, "headers_env": {"X-Test-Header": "TEST_MCP_LOG_PATH"}, "allow_tools": ["get_item"]}}}})
    hs.terminate(); hs.wait()
    hl = mcp_log()
    posts = [m for m in hl if m.get("http") == "POST"]
    ok(f"item H{sse}: a test item" in last_result(reqs[1])["content"], f"HTTP ({'SSE' if sse == '1' else 'JSON'}): call works")
    ok(posts and posts[0]["session"] is None and all(p["session"] == "test-session-1" for p in posts[1:]), f"HTTP ({sse}): Mcp-Session-Id sent after initialize", posts)
    ok(posts[0]["protocol"] is None and all(p["protocol"] == "2025-06-18" for p in posts[1:]), f"HTTP ({sse}): MCP-Protocol-Version on later requests")
    ok(all("text/event-stream" in p["accept"] and "application/json" in p["accept"] for p in posts), f"HTTP ({sse}): Accept lists both types")
    ok(any(m.get("http") == "DELETE" and m["session"] == "test-session-1" for m in hl), f"HTTP ({sse}): DELETE ends the session")
sys.path.insert(0, str(HERE / "shared")); import kit_mcp_client
try:
    kit_mcp_client.HttpServer("x", {"url": "http://example.com/mcp"}); ok(False, "HTTP: plain http to another host refused")
except kit_mcp_client.McpError:
    ok(True, "HTTP: plain http to another host refused")

# ---- other hooks: exit 2, JSON deny, ask, PostToolUse block, input fields, Stop continue ----------
HOOK_LOG.unlink(missing_ok=True)
r, reqs = scenario("hooked", [tool_use("read_file", {"path": "briefs/blocked.md"}),
                              tool_use("read_file", {"path": "briefs/denyjson.md"}, "t2"),
                              tool_use("read_file", {"path": "briefs/askme.md"}, "t3"),
                              tool_use("read_file", {"path": "briefs/flag.md"}, "t4"),
                              tool_use("read_file", {"path": "briefs/fine.md"}, "t5"),
                              done("first stop"), done("Summary line. Done.")])
c = [last_result(q)["content"] for q in reqs[1:6]]
ok("blocked by a hook: nope, not that file" in c[0] and "content of blocked.md" not in c[0], "hooks: exit 2 blocks with stderr as the reason", c[0])
ok("json says no" in c[1], "hooks: JSON permissionDecision deny blocks", c[1])
ok("no one is at the keyboard" in c[2], "hooks: ask goes to approval (refused with no one at the keyboard)", c[2])
ok("content of flag.md" in c[3] and "post-check flagged it" in c[3], "hooks: PostToolUse decision block shown to the model", c[3])
ok("content of fine.md" in c[4], "hooks: exit 0 lets the call through", c[4])
ok(r.stdout.strip() == "Summary line. Done." and "write the summary line first" in str(reqs[6]["body"]["messages"][-1]),
   "hooks: Stop decision block keeps the agent going once", r.stdout)
hl = [json.loads(l) for l in HOOK_LOG.read_text().splitlines()]
p0 = hl[0]
ok(p0["hook_event_name"] == "PreToolUse" and p0["tool_name"] == "Read" and p0["tool_use_id"] == "t1" and p0["session_id"] and p0["agent_type"] == "hooked"
   and "cwd" in p0 and "permission_mode" in p0, "hooks: input carries Claude Code's fields, tool named Read", p0)
stops = [h for h in hl if h["hook_event_name"] == "Stop"]
ok(len(stops) == 2 and stops[0]["stop_hook_active"] is False and stops[1]["stop_hook_active"] is True and stops[0]["last_assistant_message"] == "first stop",
   "hooks: Stop input has stop_hook_active and last_assistant_message", stops)
ok(any(e["event"] == "hook" and e.get("exit") == 2 for e in audit()), "hooks: each hook run is in kit-run's audit log")

# ---- subagents: allowed pair, refused pair, depth limit --------------------------------------
r, reqs = scenario("ia-writer", [tool_use("agent", {"agent": "gds-writer", "task": "sub task"}),
                                 tool_use("agent", {"agent": "ia-writer", "task": "sub sub"}),
                                 tool_use("agent", {"agent": "gds-writer", "task": "too deep"}),
                                 done("deep done"), done("mid done"),
                                 tool_use("agent", {"agent": "librarian", "task": "x"}, "t9"), done("top done")])
names = lambda q: [t["name"] for t in q["body"].get("tools") or []]
ok(r.returncode == 0 and r.stdout.strip() == "top done", "subagents: run finishes", r.stderr)
ok("agent" in names(reqs[0]) and "agent" in names(reqs[1]) and "agent" not in names(reqs[2]), "subagents: depth 2 agent isn't offered the agent tool",
   [names(q) for q in reqs[:3]])
ok("isn't allowed" in last_result(reqs[3])["content"], "subagents: calling it anyway at depth 2 is refused", last_result(reqs[3]))
ok("report from agent ia-writer" in last_result(reqs[4])["content"] and "deep done" in last_result(reqs[4])["content"], "subagents: the report comes back as untrusted text")
ok("Test agent gds-writer." in reqs[1]["body"]["system"], "subagents: each runs with its own definition")
ok("can't brief librarian" in last_result(reqs[6])["content"], "subagents: a pair not in agents.md is refused", last_result(reqs[6]))
ev = audit()
ok(sum(1 for e in ev if e["event"] == "start") >= 3 and any(e.get("parent_run") for e in ev), "subagents: each run logged with its parent run")
r, reqs = scenario("librarian", [done()])
ok("agent" not in names(reqs[0]), "subagents: one-way pair: the librarian can't start a conversation")

# ---- skills -----------------------------------------------------------------------------------
sk = {"skills": {"dirs": [str(S / "skills")]}}
r, reqs = scenario("skiller", [tool_use("skill", {"name": "demo"}), tool_use("skill_script", {"skill": "demo", "script": "run.py"}, "t2"), done()], runcfg=sk)
ok("Demo skill instructions." in last_result(reqs[1])["content"] and "run.py" in last_result(reqs[1])["content"], "skills: SKILL.md and its file list returned")
ok("allow_scripts" in last_result(reqs[2])["content"], "skills: script refused when not on the allowlist", last_result(reqs[2]))
sk2 = {"skills": {"dirs": [str(S / "skills")], "allow_scripts": ["demo/run.py"]}}
r, reqs = scenario("skiller", [tool_use("skill_script", {"skill": "demo", "script": "run.py"}), done()], runcfg=sk2)
ok("no one is at the keyboard" in last_result(reqs[1])["content"], "skills: allowlisted script still needs approval")
r, reqs = scenario("skiller", [tool_use("skill_script", {"skill": "demo", "script": "run.py"}), done()], runcfg=sk2, args=["--yes-ask"])
ok("script ran" in last_result(reqs[1])["content"], "skills: allowlisted and approved script runs", last_result(reqs[1]))
r, reqs = scenario("skiller", [tool_use("skill_script", {"skill": "demo", "script": "../../hook.py"}), done()], runcfg=sk2, args=["--yes-ask"])
ok("no script" in last_result(reqs[1])["content"], "skills: a path out of the skill folder is refused")
ok("skill_script" not in names(scenario("guarded", [done()], runcfg=sk)[1][0]), "skills: no skill_script when Bash is disallowed")

# ---- @imports ------------------------------------------------------------------------------------
kr = importlib.machinery.SourceFileLoader("kr", str(HERE / "shared/bin/kit-run")).load_module()
txt = kr.expand_imports(kit / "KIT.md")
ok("Prefs index." in txt and "Pref one: be brief." in txt, "imports: nested imports followed, relative to the importing file")
ok("already included" in txt, "imports: a cycle back to KIT.md is reported, not followed", txt)
ok("[import not found: missing.md]" in txt, "imports: missing file noted")
ok("SHOULD NOT APPEAR" not in txt and "@prefs/fenced.md" in txt, "imports: not followed inside a code fence")
deep = kit / "deep"; deep.mkdir()
for i in range(8):
    (deep / f"d{i}.md").write_text(f"level {i}\n@d{i+1}.md\n")
dt_ = kr.expand_imports(deep / "d0.md")
ok("level 5" in dt_ and "level 6" not in dt_ and "levels deep" in dt_, "imports: stops after five levels")
r, reqs = scenario("librarian", [done()])
ok("Pref one: be brief." in reqs[0]["body"]["system"], "imports: KIT.md imports reach the system prompt")

# ---- approvals -----------------------------------------------------------------------------------
logged = []
def aud(event, **kw): logged.append((event, kw))
def answers(seq):
    it = iter(seq); return lambda prompt: next(it)
import io
a = kr.Approver("x", aud, interactive=True, input_fn=answers(["d", "y"]), err=io.StringIO()); a.ask("write_file", "write f", "diff here")
ok(logged[-1][1]["decision"] == "allow" and logged[-1][1]["how"] == "asked", "approvals: d shows details, then y approves")
a = kr.Approver("x", aud, interactive=True, input_fn=answers(["n"]), err=io.StringIO())
try: a.ask("write_file", "write f"); ok(False, "approvals: n refuses")
except kr.Refused: ok(logged[-1][1]["decision"] == "deny", "approvals: n refuses and is logged")
a = kr.Approver("x", aud, interactive=True, input_fn=answers(["a"]), err=io.StringIO()); a.ask("write_file", "w1"); a.ask("write_file", "w2")
ok(logged[-1][1]["how"] == "always for this run", "approvals: a approves the rest of this run's calls to that tool")
try: a.ask("skill_script", "s"); ok(False, "approvals: always is per tool")
except (StopIteration, kr.Refused): ok(True, "approvals: always is per tool")
a = kr.Approver("x", aud, interactive=False)
try: a.ask("write_file", "w"); ok(False, "approvals: non-interactive refuses")
except kr.Refused as e: ok("no one is at the keyboard" in str(e), "approvals: non-interactive refuses")
a = kr.Approver("x", aud, yes_ask=True); a.ask("write_file", "w")
ok(logged[-1][1]["how"] == "--yes-ask", "approvals: --yes-ask approves and is logged")
f = kit / "briefs/fine.md"
ok("+new line" in kr.write_diff(f, "content of fine.md\nnew line\n"), "approvals: writes show a unified diff")
ok("test-credential" not in r.stdout + r.stderr, "no credential in any output")
print(f"kit-run parity tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)
PY

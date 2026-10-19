#!/bin/bash
# Tests kit-run (experimental) against a fake model server on 127.0.0.1 and a throwaway Kit folder:
# read then write with ask-first refused and approved, disallowed tools, writes outside the
# allowlist, credential-looking files, max turns, data-class policy, pause, the audit log, the
# ledger, and an OpenAI-compatible (local) provider. No real API, no real credential.
#   bash tests/test_kitrun.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'pkill -f "$S/" 2>/dev/null; rm -rf "$S"' EXIT
export KIT_PROVIDER_BACKOFF=0.05 KIT_PROVIDER_RETRIES=0 HERE S
python3 - <<'PY'
import json, os, pathlib, subprocess, sys, time
HERE = pathlib.Path(os.environ["HERE"]); S = pathlib.Path(os.environ["S"])
kit = S / "kit"; lib = S / "lib"
for d in ("agents", "briefs", "memory/context", ".install/logs", ".install/shared/bin"):
    (kit / d).mkdir(parents=True, exist_ok=True)
lib.mkdir()
(kit / "KIT.md").write_text("# Kit\nTest instructions.\n")
(kit / "memory/context/library.md").write_text(f"- **Library root:** `{lib}`\n")
(kit / "memory/context/notes.md").write_text("The answer is 42.\n")
(kit / ".env").write_text("NOT_A_REAL=thing\n")
(lib / "doc.md").write_text("Library doc.\n")
(kit / "agents/test-agent.md").write_text("""---
name: test-agent
description: test
disallowedTools: WebSearch, WebFetch, Bash
model: opus
kit_run:
  write:
    - briefs/
---

# Test agent
Read notes and write a brief.
""")
P = F = 0
def ok(c, name, detail=""):
    global P, F
    if c: P += 1; print("ok  ", name)
    else: F += 1; print("FAIL", name, detail)

def tool_use(name, inp, tid="t1"):
    return {"model": "claude-opus-5-5", "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}], "usage": {"input_tokens": 10, "output_tokens": 2}}
def done(text="Finished."):
    return {"model": "claude-opus-5-5", "stop_reason": "end_turn", "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 12, "output_tokens": 3}}

n = [0]
def scenario(anthropic, openai=None, args=(), stdin="", enabled_phase=2, paused=False, org=None):
    n[0] += 1
    d = S / f"s{n[0]}"; d.mkdir()
    (d / "script.json").write_text(json.dumps({"anthropic": anthropic, "openai": openai or []}))
    srv = subprocess.Popen([sys.executable, str(HERE / "tests/fake_llm_server.py"), str(d / "script.json"),
                            str(d / "port"), str(d / "log.jsonl")], env={**os.environ, "FAKE_EXPECT_CREDENTIAL": "test-credential"})
    for _ in range(50):
        if (d / "port").exists() and (d / "port").read_text(): break
        time.sleep(0.1)
    port = (d / "port").read_text()
    cfg = json.loads((HERE / "kit/models.json").read_text())
    cfg["enabled_phase"] = enabled_phase
    cfg["providers"]["anthropic"].update(base_url=f"http://127.0.0.1:{port}", credential_env="KIT_TEST_CRED")
    cfg["providers"]["local-ollama"]["base_url"] = f"http://127.0.0.1:{port}/v1"
    if org: cfg["org_profile"].update(org)
    (kit / "models.json").write_text(json.dumps(cfg))
    (kit / ".install/PAUSED").unlink(missing_ok=True)
    if paused: (kit / ".install/PAUSED").write_text("test\n")
    env = {**os.environ, "KIT_DIR": str(kit), "KIT_TEST_CRED": "test-credential"}
    r = subprocess.run([sys.executable, str(HERE / "shared/bin/kit-run"), "test-agent", "Do the thing.", *args],
                       capture_output=True, text=True, env=env, input=stdin, timeout=60)
    srv.terminate(); srv.wait()
    reqs = [json.loads(l) for l in (d / "log.jsonl").read_text().splitlines()] if (d / "log.jsonl").exists() else []
    return r, reqs

def audit():
    f = sorted((kit / ".install/logs").glob("kit-run-*.jsonl"))
    return [json.loads(l) for l in f[-1].read_text().splitlines()] if f else []

# A: read, then write; no one at the keyboard -> write refused
r, reqs = scenario([tool_use("read_file", {"path": "memory/context/notes.md"}),
                    tool_use("write_file", {"path": "briefs/out.md", "content": "brief"}, "t2"), done("Couldn't write.")])
ok(r.returncode == 0 and r.stdout.strip() == "Couldn't write.", "A: run finishes", r.stderr)
ok(not (kit / "briefs/out.md").exists(), "A: write refused with no one at the keyboard")
second = reqs[1]["body"]["messages"][-1]["content"][0]
ok("The answer is 42." in second["content"] and "Untrusted content" in second["content"], "A: read result sent back, marked untrusted")
third = reqs[2]["body"]["messages"][-1]["content"][0]
ok(third.get("is_error") and "no one is at the keyboard" in third["content"], "A: refusal reported to the model as a tool error")
tools_sent = [t["name"] for t in reqs[0]["body"]["tools"]]
ok("run_kit_tool" not in tools_sent and "read_file" in tools_sent, "A: disallowedTools Bash removes run_kit_tool from the tools offered", tools_sent)
ok("Read notes and write a brief." in reqs[0]["body"]["system"] and "Test instructions." in reqs[0]["body"]["system"],
   "A: agent body and KIT.md in the system prompt")
ev = audit()
ok([e["event"] for e in ev][:4] == ["start", "tool", "tool", "end"] and ev[1]["decision"] == "allow" and ev[2]["decision"] == "deny",
   "A: audit log: start, read allowed, write denied, end", [e["event"] for e in ev])

# B: same with --yes-ask -> written; existing file backed up
(kit / "briefs/out.md").write_text("old\n")
r, reqs = scenario([tool_use("write_file", {"path": "briefs/out.md", "content": "new brief"}), done()], args=["--yes-ask"])
ok(r.returncode == 0 and (kit / "briefs/out.md").read_text() == "new brief", "B: --yes-ask approves the write")
ok(any(p.read_text() == "old\n" for p in (kit / ".install/backups/kit-run").glob("*out.md")), "B: previous file backed up")

# C: a disallowed tool called anyway is refused
r, reqs = scenario([tool_use("run_kit_tool", {"tool": "kit-version"}), done()])
res = reqs[1]["body"]["messages"][-1]["content"][0]
ok(res.get("is_error") and "isn't allowed" in res["content"], "C: disallowed tool refused even if the model calls it")

# D: write outside the agent's write paths
r, reqs = scenario([tool_use("write_file", {"path": "memory/context/hack.md", "content": "x"}), done()], args=["--yes-ask"])
ok(not (kit / "memory/context/hack.md").exists() and "outside the allowed folders" in reqs[1]["body"]["messages"][-1]["content"][0]["content"],
   "D: write outside the allowlist refused")

# E: credential-looking file and a path outside the roots
r, reqs = scenario([tool_use("read_file", {"path": ".env"}), tool_use("read_file", {"path": "/etc/hosts"}, "t2"),
                    tool_use("read_file", {"path": f"{S}/lib/doc.md"}, "t3"), done()])
c1 = reqs[1]["body"]["messages"][-1]["content"][0]["content"]; c2 = reqs[2]["body"]["messages"][-1]["content"][0]["content"]
c3 = reqs[3]["body"]["messages"][-1]["content"][0]["content"]
ok("credential file" in c1 and "NOT_A_REAL" not in c1, "E: .env refused")
ok("outside the allowed folders" in c2, "E: path outside the Kit folder and library refused")
ok("Library doc." in c3, "E: library root readable")

# F: max turns
r, reqs = scenario([tool_use("list_dir", {"path": "briefs"})], args=["--max-turns", "3"])
ok(r.returncode == 4 and len(reqs) == 3 and "stopped after 3 turns" in r.stderr, "F: stops at --max-turns with exit 4", r.stderr)

# G: policy
r, reqs = scenario([done()], args=["--profile", "local", "--data-class", "confidential", "--no-fallback"])
ok(r.returncode == 2 and "takes data up to 'public'" in r.stderr and not reqs, "G: confidential on a non-Claude profile refused with --no-fallback", r.stderr)
r, reqs = scenario([done("From Claude.")], args=["--profile", "local", "--data-class", "confidential"])
ok(r.returncode == 0 and r.stdout.strip() == "From Claude." and all(q["kind"] == "anthropic" for q in reqs),
   "G: without --no-fallback it falls back to Claude; the local model sees nothing")
r, reqs = scenario([done()], args=["--profile", "local", "--data-class", "public"], enabled_phase=1, openai=[])
ok(all(q["kind"] == "anthropic" for q in reqs), "G: enabled_phase 1 keeps non-Claude providers off")

# H: paused
r, reqs = scenario([done()], paused=True)
ok(r.returncode == 2 and "paused" in r.stderr and not reqs, "H: nothing runs while Kit is paused")

# I: ledger
rec = json.loads((kit / ".install/logs/cost.jsonl").read_text().splitlines()[-1])
ok(rec["source"] == "kit-run:test-agent" and rec["provider"] == "anthropic" and rec["turns"] == 1, "I: usage recorded in the ledger", rec)

# J: OpenAI-compatible provider (local) for public data, tool loop in that API's shape
openai = [{"model": "llama", "choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
           "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": json.dumps({"path": "memory/context/notes.md"})}}]}}],
           "usage": {"prompt_tokens": 5, "completion_tokens": 2}},
          {"model": "llama", "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "42, locally."}}],
           "usage": {"prompt_tokens": 9, "completion_tokens": 3}}]
r, reqs = scenario([done()], openai=openai, args=["--profile", "local", "--data-class", "public"])
ok(r.returncode == 0 and r.stdout.strip() == "42, locally." and all(q["kind"] == "openai" for q in reqs)
   and "The answer is 42." in reqs[1]["body"]["messages"][-1]["content"], "J: local OpenAI-compatible provider runs the tool loop", r.stderr)
ok("test-credential" not in r.stdout + r.stderr, "no credential in any output")
print(f"kit-run tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)
PY

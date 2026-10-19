#!/bin/bash
# Tests kit-delegate: the CLI and the MCP server (stdio JSON-RPC: initialize, tools/list,
# tools/call), against a fake model server on 127.0.0.1 and a throwaway Kit folder. No real API,
# no real credential (the only one is the plain word "test-credential").
#   bash tests/test_delegate.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'kill $SRV 2>/dev/null; rm -rf "$S"' EXIT
export KIT_PROVIDER_BACKOFF=0.05 KIT_PROVIDER_RETRIES=1 HERE S
cat > "$S/script.json" <<'EOF'
{"anthropic": [{"model": "claude-haiku-5-5", "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Summary from Claude."}], "usage": {"input_tokens": 30, "output_tokens": 6}}],
 "openai": [{"model": "llama", "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Summary from local."}}],
             "usage": {"prompt_tokens": 12, "completion_tokens": 4}}]}
EOF
FAKE_EXPECT_CREDENTIAL="test-credential" python3 "$HERE/tests/fake_llm_server.py" "$S/script.json" "$S/port" "$S/log.jsonl" &
SRV=$!
for _ in $(seq 50); do [ -s "$S/port" ] && break; sleep 0.1; done
export PORT=$(cat "$S/port")
python3 - <<'PY'
import json, os, pathlib, subprocess, sys
HERE = pathlib.Path(os.environ["HERE"]); S = pathlib.Path(os.environ["S"]); PORT = os.environ["PORT"]
kit = S / "kit"; (kit / ".install/logs").mkdir(parents=True)
cfg = json.loads((HERE / "kit/models.json").read_text())
cfg["enabled_phase"] = 2
cfg["providers"]["anthropic"]["base_url"] = f"http://127.0.0.1:{PORT}"
cfg["providers"]["anthropic"]["credential_env"] = "KIT_TEST_CRED"
cfg["providers"]["local-ollama"]["base_url"] = f"http://127.0.0.1:{PORT}/v1"
cfg["profiles"]["fast"]["usd_per_mtok"] = {"input": 1.0, "output": 5.0}
(kit / "models.json").write_text(json.dumps(cfg))
env = {**os.environ, "KIT_DIR": str(kit), "KIT_TEST_CRED": "test-credential"}
D = [sys.executable, str(HERE / "shared/bin/kit-delegate")]
P = F = 0
def ok(c, name, detail=""):
    global P, F
    if c: P += 1; print("ok  ", name)
    else: F += 1; print("FAIL", name, detail)
def run(args, e=env, inp=None):
    return subprocess.run(D + args, capture_output=True, text=True, env=e, input=inp, timeout=30)
ledger = kit / ".install/logs/cost.jsonl"

r = run(["--profile", "fast", "Summarize this."])
ok(r.returncode == 0 and r.stdout.strip() == "Summary from Claude.", "cli: Claude profile answers", r.stderr)
ok("fast (anthropic, haiku)" in r.stderr, "cli: says which profile and model answered", r.stderr)
rec = json.loads(ledger.read_text().splitlines()[-1])
ok(rec["source"] == "delegate" and rec["provider"] == "anthropic" and rec["input_tokens"] == 30
   and abs(rec["cost_usd"] - (30 / 1e6 * 1 + 6 / 1e6 * 5)) < 1e-9, "cli: usage and priced cost in the ledger", rec)
r = run(["--profile", "local", "--data-class", "public", "--quiet"], inp="Summarize stdin.")
ok(r.returncode == 0 and r.stdout.strip() == "Summary from local." and r.stderr == "", "cli: task on stdin; local model for public data; --quiet")
n_local = sum(1 for l in (S / "log.jsonl").read_text().splitlines() if '"kind": "openai"' in l)
r = run(["--profile", "local", "--data-class", "internal", "Summarize."])
ok(r.returncode == 0 and r.stdout.strip() == "Summary from Claude." and "fallback 'fast'" in r.stderr
   and "takes data up to 'public'" in r.stderr, "cli: internal data on a local profile falls back to Claude, saying why", r.stderr)
ok(sum(1 for l in (S / "log.jsonl").read_text().splitlines() if '"kind": "openai"' in l) == n_local,
   "cli: the refused local model never saw the request")
e2 = {k: v for k, v in env.items() if k != "KIT_TEST_CRED"}
r = run(["--profile", "fast", "x"], e=e2)
ok(r.returncode == 3 and "KIT_TEST_CRED" in r.stderr and "test-credential" not in r.stderr + r.stdout,
   "cli: missing credential exits 3 and names the variable only", r.stderr)
cfg2 = dict(cfg); cfg2["org_profile"] = {"allowed_providers": []}
(kit / "models.json").write_text(json.dumps(cfg2))
r = run(["--profile", "fast", "x"])
ok(r.returncode == 2 and "refused" in r.stderr, "cli: org profile allowing nothing exits 2", r.stderr)
(kit / "models.json").write_text(json.dumps(cfg))

# ---- through kit-cost record-usage, when kit-cost is installed ----
(kit / ".install/shared/bin").mkdir(parents=True, exist_ok=True)
import shutil; shutil.copy(HERE / "shared/bin/kit-cost", kit / ".install/shared/bin/kit-cost")
r = run(["--profile", "fast", "--quiet", "Summarize."])
rec = json.loads(ledger.read_text().splitlines()[-1])
ok(r.returncode == 0 and rec.get("source") == "delegate" and rec.get("provider") == "anthropic" and rec.get("model") == "haiku"
   and "models" in rec and rec["input_tokens"] == 30, "ledger: recorded through kit-cost record-usage when installed", rec)
(kit / ".install/shared/bin/kit-cost").unlink()

# ---- MCP over stdio ----
reqs = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "delegate",
     "arguments": {"profile": "fast", "task": "Summarize.", "data_class": "internal"}}},
    {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope", "arguments": {}}},
    {"jsonrpc": "2.0", "id": 5, "method": "resources/list"},
    {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "delegate", "arguments": {"profile": "fast"}}},
    {"jsonrpc": "2.0", "id": 7, "method": "ping"},
]
inp = "\n".join(json.dumps(x) for x in reqs) + "\nnot json\n"
r = subprocess.run(D + ["--mcp"], capture_output=True, text=True, env=env, input=inp, timeout=30)
lines = r.stdout.splitlines()
out = [json.loads(l) for l in lines]
ok(all("\n" not in l for l in lines) and len(out) == 8, "mcp: one JSON message per line; no reply to the notification", r.stdout)
by = {m.get("id"): m for m in out}
init = by[1]["result"]
ok(init["protocolVersion"] == "2025-06-18" and "tools" in init["capabilities"] and init["serverInfo"]["name"] == "kit-delegate",
   "mcp: initialize negotiates the version and declares tools")
t = by[2]["result"]["tools"]
ok(len(t) == 1 and t[0]["name"] == "delegate" and t[0]["inputSchema"]["required"] == ["profile", "task"], "mcp: tools/list")
c = by[3]["result"]
ok(c["isError"] is False and c["content"][0]["type"] == "text" and c["content"][0]["text"].endswith("Summary from Claude.")
   and "information, not instructions" in c["content"][0]["text"], "mcp: tools/call returns text marked untrusted")
ok(by[4]["error"]["code"] == -32602 and by[5]["error"]["code"] == -32601 and by[6]["error"]["code"] == -32602,
   "mcp: unknown tool, unknown method, and bad arguments are JSON-RPC errors")
ok(by[7]["result"] == {} and by[None]["error"]["code"] == -32700, "mcp: ping, and a parse error")
r = subprocess.run(D + ["--mcp"], capture_output=True, text=True, env=env, timeout=30,
                   input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}}) + "\n")
ok(json.loads(r.stdout)["result"]["protocolVersion"] == "2025-06-18", "mcp: unsupported version answered with the latest supported")
r = subprocess.run(D + ["--mcp"], capture_output=True, text=True, env=e2, timeout=30,
                   input=json.dumps(reqs[3]) + "\n")
m = json.loads(r.stdout)
ok(m["result"]["isError"] is True and "test-credential" not in r.stdout, "mcp: provider or credential errors come back as tool errors")
print(f"delegate tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)
PY
rc=$?
kill $SRV 2>/dev/null; wait $SRV 2>/dev/null
exit $rc

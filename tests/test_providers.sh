#!/bin/bash
# Tests kit_providers (Anthropic and OpenAI-compatible clients), kit_secrets, and the phase 2
# dispatch policy in kit_models, against a fake server on 127.0.0.1. No real API is called and no
# real credential is read; the only credential is the plain word "test-credential".
#   bash tests/test_providers.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'kill $SRV 2>/dev/null; rm -rf "$S"' EXIT
export KIT_PROVIDER_BACKOFF=0.05 HERE S
cat > "$S/script.json" <<'EOF'
{"anthropic": [
  {"_status": 529},
  {"model": "claude-haiku-5-5", "stop_reason": "tool_use",
   "content": [{"type": "text", "text": "Checking."},
               {"type": "tool_use", "id": "tu_1", "name": "lookup", "input": {"q": "x"}}],
   "usage": {"input_tokens": 11, "output_tokens": 7, "cache_read_input_tokens": 3}},
  {"model": "claude-haiku-5-5", "stop_reason": "end_turn",
   "content": [{"type": "text", "text": "Done: x"}], "usage": {"input_tokens": 20, "output_tokens": 5}}],
 "openai": [
  {"model": "llama", "choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": null,
     "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "lookup", "arguments": "{\"q\": \"y\"}"}}]}}],
   "usage": {"prompt_tokens": 9, "completion_tokens": 4}},
  {"model": "llama", "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Done: y"}}],
   "usage": {"prompt_tokens": 15, "completion_tokens": 3}}]}
EOF
FAKE_EXPECT_CREDENTIAL="test-credential" python3 "$HERE/tests/fake_llm_server.py" "$S/script.json" "$S/port" "$S/log.jsonl" &
SRV=$!
for _ in $(seq 50); do [ -s "$S/port" ] && break; sleep 0.1; done
export PORT=$(cat "$S/port")
mkdir -p "$S/bin"
cat > "$S/bin/security" <<'EOF'
#!/bin/bash
# stub of macOS `security find-generic-password -s NAME -w`
[ "$1" = "find-generic-password" ] && [ "$3" = "kit-test-entry" ] && { echo "test-credential"; exit 0; }
exit 44
EOF
chmod +x "$S/bin/security"
PATH="$S/bin:$PATH" python3 - <<'PY'
import io, json, os, pathlib, sys
HERE = pathlib.Path(os.environ["HERE"]); S = pathlib.Path(os.environ["S"]); PORT = os.environ["PORT"]
sys.path.insert(0, str(HERE / "shared"))
import kit_models, kit_providers, kit_secrets
P = F = 0
def ok(c, name, detail=""):
    global P, F
    if c: P += 1; print("ok  ", name)
    else: F += 1; print("FAIL", name, detail)
log = lambda: [json.loads(l) for l in (S / "log.jsonl").read_text().splitlines()]

# ---- secrets ----
os.environ["KIT_TEST_CRED"] = "test-credential"
c = kit_secrets.resolve({"kind": "openai-compatible", "credential_env": "KIT_TEST_CRED"})
ok(c.reveal() == "test-credential" and "test-credential" not in repr(c) and "test-credential" not in str(c),
   "secrets: env credential resolves; repr and str hide it")
ok(kit_secrets.resolve({"kind": "ollama"}) is None, "secrets: local provider needs none")
try:
    kit_secrets.resolve({"kind": "openai-compatible", "credential_env": "KIT_NOT_SET_X"}, "p")
    ok(False, "secrets: missing credential raises")
except kit_secrets.CredentialError as e:
    ok("KIT_NOT_SET_X" in str(e), "secrets: missing credential names where it looked")
if sys.platform == "darwin":
    c = kit_secrets.resolve({"kind": "openai-compatible", "keychain_entry": "kit-test-entry"})
    ok(c.reveal() == "test-credential" and c.source == "keychain kit-test-entry", "secrets: Keychain entry via `security`")
    try:
        kit_secrets.resolve({"kind": "openai-compatible", "keychain_entry": "no-such-entry"})
        ok(False, "secrets: missing Keychain entry raises")
    except kit_secrets.CredentialError as e:
        ok("no-such-entry" in str(e) and "test-credential" not in str(e), "secrets: missing Keychain entry error names the entry only")

# ---- Anthropic client: retry on 529, tool_use round trip, usage ----
cred = kit_secrets.Credential("test-credential", "env KIT_TEST_CRED")
a = kit_providers.AnthropicClient(f"http://127.0.0.1:{PORT}", cred, timeout=5)
tools = [{"name": "lookup", "description": "look", "parameters": {"type": "object", "properties": {"q": {"type": "string"}}}}]
r = a.complete("haiku", "sys", [{"role": "user", "content": "go"}], tools)
ok(r.stop == "tool_use" and r.tool_calls == [{"id": "tu_1", "name": "lookup", "input": {"q": "x"}}] and r.text == "Checking.",
   "anthropic: tool_use parsed")
ok(r.usage["input_tokens"] == 11 and r.usage["output_tokens"] == 7 and r.usage["cache_read_tokens"] == 3, "anthropic: usage")
L = log()
ok(L[0]["kind"] == "anthropic" and len([x for x in L if x["kind"] == "anthropic"]) == 2, "anthropic: retried after 529")
ok(L[1]["body"]["model"] == "claude-haiku-5-5" and L[1]["anthropic_version"] == "2023-06-01", "anthropic: alias mapped to model ID; version header")
ok(L[1]["auth"] == {"x-api-key": True}, "anthropic: credential sent as x-api-key", L[1]["auth"])
ok(L[1]["body"]["tools"][0]["input_schema"]["properties"]["q"]["type"] == "string" and L[1]["body"]["system"] == "sys",
   "anthropic: tools and system in Messages API shape")
msgs = [{"role": "user", "content": "go"},
        {"role": "assistant", "content": "Checking.", "tool_calls": r.tool_calls},
        {"role": "tool", "tool_call_id": "tu_1", "name": "lookup", "content": "x=1"}]
r2 = a.complete("haiku", "sys", msgs, tools)
b = log()[-1]["body"]["messages"]
ok(r2.text == "Done: x" and r2.stop == "end", "anthropic: final answer")
ok(b[1]["content"][1]["type"] == "tool_use" and b[2]["role"] == "user" and b[2]["content"][0]["type"] == "tool_result"
   and b[2]["content"][0]["tool_use_id"] == "tu_1", "anthropic: tool result sent as a user tool_result block")
ok("test-credential" not in repr(a.__dict__.get("credential")), "anthropic: client repr hides the credential")

# ---- OpenAI-compatible client: tool call round trip, bearer auth, usage ----
o = kit_providers.OpenAICompatibleClient(f"http://127.0.0.1:{PORT}/v1", cred, timeout=5)
r = o.complete("llama", "sys", [{"role": "user", "content": "go"}], tools)
ok(r.stop == "tool_use" and r.tool_calls[0]["input"] == {"q": "y"} and r.tool_calls[0]["id"] == "c1", "openai: tool call parsed")
ok(r.usage == {"input_tokens": 9, "output_tokens": 4}, "openai: usage mapped")
last = log()[-1]
ok(last["path"] == "/v1/chat/completions" and last["auth"] == {"authorization": True}, "openai: bearer credential on /chat/completions")
ok(last["body"]["messages"][0] == {"role": "system", "content": "sys"} and last["body"]["tools"][0]["type"] == "function",
   "openai: system message and function tools")
r2 = o.complete("llama", "sys", [{"role": "user", "content": "go"},
                                 {"role": "assistant", "content": "", "tool_calls": r.tool_calls},
                                 {"role": "tool", "tool_call_id": "c1", "name": "lookup", "content": "y=2"}], tools)
m = log()[-1]["body"]["messages"]
ok(r2.text == "Done: y" and m[2]["tool_calls"][0]["function"]["arguments"] == '{"q": "y"}' and m[3]["role"] == "tool",
   "openai: tool result round trip")
az = kit_providers.OpenAICompatibleClient(f"http://127.0.0.1:{PORT}", cred, kind="azure-openai", api_version="2024-10-21")
az.complete("dep1", None, [{"role": "user", "content": "hi"}])
last = log()[-1]
ok(last["path"] == "/openai/deployments/dep1/chat/completions?api-version=2024-10-21" and last["auth"] == {"api-key": True},
   "azure: deployment URL, api-version, api-key header")
ol = kit_providers.client_for({"kind": "ollama"})
ok(ol.base == "http://localhost:11434/v1" and ol.credential is None, "ollama: default local URL, no credential")
try:
    kit_providers.OpenAICompatibleClient(f"http://127.0.0.1:{PORT}/reject", None, timeout=5).complete("m", None, [{"role": "user", "content": "x"}])
    ok(False, "non-retryable HTTP error raises")
except kit_providers.ProviderError as e:
    ok("400" in str(e) and "test-credential" not in str(e) and sum(1 for l in log() if "/reject/" in l["path"]) == 1,
       "non-retryable 400 raises at once (no retry), no credential in the error")

# ---- dispatch policy ----
cfg = json.loads((HERE / "kit/models.json").read_text()); cfg["_per_agent"] = {}; cfg["_path"] = "x"
ok(kit_models.resolve_dispatch(cfg, profile="local", data_class="public")["provider_name"] == "anthropic",
   "policy: enabled_phase 1 (shipped) keeps local off and falls back to Claude")
cfg["enabled_phase"] = 2
ok(kit_models.resolve_dispatch(cfg, profile="local", data_class="public")["provider_name"] == "local-ollama",
   "policy: phase 2 on, public data may go to a local model")
ch = kit_models.resolve_dispatch(cfg, profile="local", data_class="confidential")
ok(ch["provider_name"] == "anthropic" and any("takes data up to 'public'" in n for n in ch["notes"]),
   "policy: confidential refused for non-Claude (org cap public) and falls back to Claude", ch["notes"])
cfg["org_profile"]["non_claude_max_data_class"] = "confidential"
ok(kit_models.resolve_dispatch(cfg, profile="local", data_class="confidential")["provider_name"] == "local-ollama",
   "policy: org profile can raise the non-Claude cap")
ch = kit_models.resolve_dispatch(cfg, profile="local", data_class="confidential")
cfg["providers"]["approved-api"]["max_data_class"] = "internal"
ok(kit_models.resolve_dispatch(cfg, profile="local", data_class="internal")["provider_name"] == "local-ollama", "policy: within cap")
cfg["org_profile"]["allowed_providers"] = ["anthropic"]
ok(kit_models.resolve_dispatch(cfg, profile="local", data_class="public")["provider_name"] == "anthropic",
   "policy: allowed_providers excludes local -> Claude")
cfg["org_profile"]["allowed_providers"] = []
try:
    kit_models.resolve_dispatch(cfg, profile="local", data_class="public"); ok(False, "policy: nothing allowed raises")
except kit_models.PolicyError:
    ok(True, "policy: nothing allowed raises PolicyError")
try:
    kit_models.resolve_dispatch(cfg, data_class="secret"); ok(False, "policy: unknown data class")
except kit_models.PolicyError:
    ok(True, "policy: unknown data class refused")
print(f"providers tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)
PY
rc=$?
kill $SRV 2>/dev/null; wait $SRV 2>/dev/null
exit $rc

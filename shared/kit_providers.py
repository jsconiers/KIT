"""kit_providers: two small model clients behind one interface, standard library only.

  AnthropicClient          the Anthropic Messages API (POST {base_url}/v1/messages)
  OpenAICompatibleClient   chat completions (POST {base_url}/chat/completions), which covers
                           OpenAI, Azure OpenAI (kind "azure-openai": deployment URL, api-version,
                           api-key header), Ollama, LM Studio, vLLM, and a LiteLLM proxy

Both take Kit's neutral messages and tools and return a Result, so kit-delegate and kit-run don't
care which provider answers.

Neutral messages, oldest first:
  {"role": "user", "content": "text"}
  {"role": "assistant", "content": "text", "tool_calls": [{"id", "name", "input": {...}}]}
  {"role": "tool", "tool_call_id": "...", "name": "...", "content": "text"}
Neutral tools: {"name", "description", "parameters": <JSON Schema object>}

Result: text, tool_calls (same shape as above), stop ("end", "tool_use", "max_tokens", or the
provider's own word), usage {"input_tokens", "output_tokens"}, model.

Network errors and HTTP 408, 409, 429, and 5xx are retried with backoff (KIT_PROVIDER_RETRIES,
default 3); other HTTP errors raise ProviderError at once. Credentials go only into request
headers and never into errors, logs, or reprs.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ANTHROPIC_VERSION = "2023-06-01"
# Claude Code takes aliases; the API takes model IDs. A provider's "model_ids" map overrides these.
CLAUDE_MODEL_IDS = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5",
                    "haiku": "claude-haiku-5-5", "fable": "claude-fable-5-1"}
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}


class ProviderError(Exception):
    pass


class Result:
    def __init__(self, text="", tool_calls=None, stop="end", usage=None, model=None):
        self.text = text
        self.tool_calls = tool_calls or []
        self.stop = stop
        self.usage = usage or {"input_tokens": None, "output_tokens": None}
        self.model = model

    def __repr__(self):
        return f"<Result stop={self.stop} tools={len(self.tool_calls)} chars={len(self.text)}>"


def _post(url, headers, body, timeout, retries=None):
    retries = int(os.environ.get("KIT_PROVIDER_RETRIES", "3")) if retries is None else retries
    data = json.dumps(body).encode("utf-8")
    delay = float(os.environ.get("KIT_PROVIDER_BACKOFF", "1.0"))
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"content-type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
            except Exception:  # noqa: BLE001
                pass
            last = f"HTTP {e.code} from {urllib.parse.urlsplit(url).netloc}: {detail}"
            if e.code not in RETRY_STATUS:
                raise ProviderError(last) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = f"couldn't reach {urllib.parse.urlsplit(url).netloc}: {getattr(e, 'reason', e)}"
        except ValueError:
            raise ProviderError(f"{urllib.parse.urlsplit(url).netloc} didn't return JSON") from None
        if attempt < retries:
            time.sleep(delay * (2 ** attempt))
    raise ProviderError(last or "request failed")


class AnthropicClient:
    def __init__(self, base_url="https://api.anthropic.com", credential=None, timeout=120,
                 model_ids=None):
        self.base = base_url.rstrip("/")
        self.credential = credential
        self.timeout = timeout
        self.model_ids = {**CLAUDE_MODEL_IDS, **(model_ids or {})}

    def model_id(self, model):
        return self.model_ids.get(model, model)

    def _messages(self, messages):
        out = []
        for m in messages:
            role = m["role"]
            if role == "tool":
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"],
                         "content": m.get("content", "")}
                if m.get("is_error"):
                    block["is_error"] = True
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list) \
                        and out[-1]["content"] and out[-1]["content"][0].get("type") == "tool_result":
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
            elif role == "assistant" and m.get("tool_calls"):
                blocks = [{"type": "text", "text": m["content"]}] if m.get("content") else []
                blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c.get("input") or {}}
                           for c in m["tool_calls"]]
                out.append({"role": "assistant", "content": blocks})
            else:
                out.append({"role": role, "content": m.get("content", "")})
        return out

    def complete(self, model, system, messages, tools=None, max_output=4096):
        body = {"model": self.model_id(model), "max_tokens": max_output, "messages": self._messages(messages)}
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [{"name": t["name"], "description": t.get("description", ""),
                              "input_schema": t.get("parameters") or {"type": "object", "properties": {}}}
                             for t in tools]
        headers = {"anthropic-version": ANTHROPIC_VERSION}
        if self.credential:
            headers["x-api-key"] = self.credential.reveal()
        data = _post(self.base + "/v1/messages", headers, body, self.timeout)
        text, calls = [], []
        for block in data.get("content") or []:
            if block.get("type") == "text":
                text.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append({"id": block.get("id"), "name": block.get("name"), "input": block.get("input") or {}})
        stop = {"end_turn": "end", "tool_use": "tool_use", "max_tokens": "max_tokens",
                "stop_sequence": "end"}.get(data.get("stop_reason"), data.get("stop_reason") or "end")
        u = data.get("usage") or {}
        return Result("".join(text), calls, stop,
                      {"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
                       "cache_read_tokens": u.get("cache_read_input_tokens"),
                       "cache_write_tokens": u.get("cache_creation_input_tokens")},
                      data.get("model") or body["model"])


class OpenAICompatibleClient:
    def __init__(self, base_url, credential=None, timeout=120, kind="openai-compatible",
                 api_version=None, model_ids=None):
        self.base = base_url.rstrip("/")
        self.credential = credential
        self.timeout = timeout
        self.kind = kind
        self.api_version = api_version
        self.model_ids = model_ids or {}

    def _url(self, model):
        if self.kind == "azure-openai":
            q = urllib.parse.urlencode({"api-version": self.api_version or "2024-10-21"})
            return f"{self.base}/openai/deployments/{urllib.parse.quote(model)}/chat/completions?{q}"
        return self.base + "/chat/completions"

    def _messages(self, system, messages):
        out = [{"role": "system", "content": system}] if system else []
        for m in messages:
            if m["role"] == "tool":
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m.get("content", "")})
            elif m["role"] == "assistant" and m.get("tool_calls"):
                out.append({"role": "assistant", "content": m.get("content") or None,
                            "tool_calls": [{"id": c["id"], "type": "function",
                                            "function": {"name": c["name"],
                                                         "arguments": json.dumps(c.get("input") or {})}}
                                           for c in m["tool_calls"]]})
            else:
                out.append({"role": m["role"], "content": m.get("content", "")})
        return out

    def complete(self, model, system, messages, tools=None, max_output=4096):
        model = self.model_ids.get(model, model)
        body = {"model": model, "messages": self._messages(system, messages), "max_tokens": max_output}
        if tools:
            body["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t.get("description", ""),
                "parameters": t.get("parameters") or {"type": "object", "properties": {}}}} for t in tools]
        headers = {}
        if self.credential:
            if self.kind == "azure-openai":
                headers["api-key"] = self.credential.reveal()
            else:
                headers["authorization"] = "Bearer " + self.credential.reveal()
        data = _post(self._url(model), headers, body, self.timeout)
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        calls = []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {"_unparsed": fn.get("arguments")}
            calls.append({"id": c.get("id") or f"call_{len(calls)}", "name": fn.get("name"), "input": args})
        reason = choice.get("finish_reason")
        stop = "tool_use" if calls or reason == "tool_calls" else {"stop": "end", "length": "max_tokens"}.get(
            reason, reason or "end")
        u = data.get("usage") or {}
        return Result(msg.get("content") or "", calls, stop,
                      {"input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens")},
                      data.get("model") or model)


def client_for(provider, credential=None):
    """A client for a provider entry from models.json."""
    kind = provider.get("kind", "")
    timeout = float(provider.get("timeout_seconds", 120))
    if kind == "anthropic":
        return AnthropicClient(provider.get("base_url") or "https://api.anthropic.com", credential, timeout,
                               provider.get("model_ids"))
    if kind in ("openai", "openai-compatible", "azure-openai", "ollama", "lmstudio", "vllm", "litellm", "local"):
        base = provider.get("base_url")
        if not base:
            base = {"ollama": "http://localhost:11434/v1", "lmstudio": "http://localhost:1234/v1",
                    "openai": "https://api.openai.com/v1"}.get(kind)
        if not base:
            raise ProviderError(f"provider kind '{kind}' needs a base_url")
        return OpenAICompatibleClient(base, credential, timeout, kind, provider.get("api_version"),
                                      provider.get("model_ids"))
    raise ProviderError(f"unknown provider kind '{kind}'")

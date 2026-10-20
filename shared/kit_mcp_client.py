"""kit_mcp_client: a small MCP client for kit-run (Python standard library only).

Speaks the Model Context Protocol, version 2025-06-18, over the two standard transports:

  stdio            kit-run launches the server as a subprocess and exchanges JSON-RPC 2.0 messages
                   on its stdin and stdout, one message per line with no embedded newlines; the
                   server's stderr is captured, never parsed. Shutdown: close stdin, wait, then
                   SIGTERM, then SIGKILL.
  Streamable HTTP  every message is a POST to the server's one MCP endpoint, with
                   Accept: application/json, text/event-stream. A request's answer comes back as
                   one JSON object or as an SSE stream; notifications get 202 Accepted. The
                   Mcp-Session-Id the server returns at initialize goes on every later request, as
                   does MCP-Protocol-Version. Closing sends DELETE (405 is fine).

Lifecycle: initialize (protocolVersion, capabilities, clientInfo), then the
notifications/initialized notification, then tools/list and tools/call; ping is supported.
Spec: modelcontextprotocol.io/specification/2025-06-18 (basic/transports, basic/lifecycle).

Servers come only from kit-run's own config (kit-run.json in the Kit folder), never from Claude
Code's settings. Environment values and HTTP header values are named there by environment
variable, read at launch, and never logged, printed, or put in an error message.

  {"mcp": {"require_guard": true,
           "servers": {"jira": {"type": "stdio", "command": "node", "args": ["server.js"],
                                "env_from": {"SERVER_VAR": "MY_ENV_VAR"},
                                "allow_tools": ["get_issue", "search_issues"]},
                       "wiki": {"type": "http", "url": "https://wiki.example.com/mcp",
                                "headers_env": {"Authorization": "WIKI_AUTH_HEADER"},
                                "allow_tools": ["search"]}}}}
"""
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
CLIENT_INFO = {"name": "kit-run", "title": "Kit's experimental runtime", "version": "0.2"}


class McpError(Exception):
    """A transport, protocol, or server error. Messages never carry environment or header values."""


def tool_name(server, tool):
    return f"mcp__{server}__{tool}"


def split_name(name):
    if not name.startswith("mcp__") or "__" not in name[5:]:
        return None, None
    server, tool = name[5:].split("__", 1)
    return server, tool


class _Base:
    def __init__(self, name, spec, timeout=60):
        self.name, self.spec, self.timeout = name, spec, timeout
        self._id = 0
        self.protocol = PROTOCOL_VERSION
        self.server_info = {}

    def _next_id(self):
        self._id += 1
        return self._id

    def initialize(self):
        res = self.request("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                          "clientInfo": CLIENT_INFO})
        ver = res.get("protocolVersion")
        if ver not in SUPPORTED_VERSIONS:
            self.close()
            raise McpError(f"{self.name}: server answered with protocol version {ver!r}, which kit-run doesn't support")
        self.protocol = ver
        self.server_info = res.get("serverInfo") or {}
        self.notify("notifications/initialized")
        return res

    def list_tools(self):
        tools, cursor = [], None
        for _ in range(20):                     # pagination, bounded
            res = self.request("tools/list", {"cursor": cursor} if cursor else {})
            tools += res.get("tools") or []
            cursor = res.get("nextCursor")
            if not cursor:
                break
        return tools

    def call_tool(self, tool, arguments):
        return self.request("tools/call", {"name": tool, "arguments": arguments or {}})

    def ping(self):
        return self.request("ping", {})


class StdioServer(_Base):
    def __init__(self, name, spec, timeout=60):
        super().__init__(name, spec, timeout)
        cmd = [spec["command"], *[str(a) for a in spec.get("args") or []]]
        env = dict(os.environ)
        for target, source in (spec.get("env_from") or {}).items():
            if source in os.environ:
                env[target] = os.environ[source]
        try:
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, env=env, cwd=spec.get("cwd") or None,
                                         text=True, encoding="utf-8", bufsize=1)
        except OSError as e:
            raise McpError(f"{name}: couldn't start the server ({e.strerror or e})") from None
        self.stderr_tail = []
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        self._lines = []
        self._cv = threading.Condition()
        threading.Thread(target=self._read_stdout, daemon=True).start()

    def _drain_stderr(self):
        for line in self.proc.stderr:
            self.stderr_tail = (self.stderr_tail + [line.rstrip()])[-20:]

    def _read_stdout(self):
        for line in self.proc.stdout:
            with self._cv:
                self._lines.append(line)
                self._cv.notify_all()
        with self._cv:
            self._lines.append(None)            # end of stream
            self._cv.notify_all()

    def _send(self, msg):
        data = json.dumps(msg, separators=(",", ":"))
        if "\n" in data:
            raise McpError("message would contain a newline")
        try:
            self.proc.stdin.write(data + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            raise McpError(f"{self.name}: the server closed its input") from None

    def notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})})

    def request(self, method, params=None):
        rid = self._next_id()
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        deadline = time.time() + self.timeout
        with self._cv:
            while True:
                while self._lines:
                    line = self._lines.pop(0)
                    if line is None:
                        self._lines.insert(0, None)
                        raise McpError(f"{self.name}: the server exited before answering {method}")
                    try:
                        msg = json.loads(line)
                    except ValueError:
                        continue                # not a message; servers must not do this, so skip it
                    if msg.get("id") == rid and ("result" in msg or "error" in msg):
                        if "error" in msg:
                            err = msg["error"] or {}
                            raise McpError(f"{self.name}: {method} failed ({err.get('code')}): {str(err.get('message'))[:300]}")
                        return msg["result"]
                    if "method" in msg and "id" in msg:
                        # A request from the server (sampling, elicitation, roots): kit-run offers none.
                        self._send({"jsonrpc": "2.0", "id": msg["id"],
                                    "error": {"code": -32601, "message": "kit-run doesn't support server requests"}})
                left = deadline - time.time()
                if left <= 0:
                    raise McpError(f"{self.name}: no answer to {method} within {self.timeout}s")
                self._cv.wait(left)

    def close(self):
        p = getattr(self, "proc", None)
        if not p or p.poll() is not None:
            return
        try:
            p.stdin.close()
        except OSError:
            pass
        for sig in ("wait", "terminate", "kill"):
            try:
                if sig != "wait":
                    getattr(p, sig)()
                p.wait(timeout=3)
                return
            except subprocess.TimeoutExpired:
                continue


class HttpServer(_Base):
    def __init__(self, name, spec, timeout=60):
        super().__init__(name, spec, timeout)
        url = spec.get("url") or ""
        local = url.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]"))
        if not (url.startswith("https://") or local):
            raise McpError(f"{name}: an HTTP server's url must be https:// (or http:// on this computer)")
        self.url = url
        self.session = None
        self.headers = {}
        for header, env_name in (spec.get("headers_env") or {}).items():
            if env_name in os.environ:
                self.headers[header] = os.environ[env_name]

    def _post(self, msg, expect_response):
        hdrs = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                **self.headers}
        if self.session:
            hdrs["Mcp-Session-Id"] = self.session
        if msg.get("method") != "initialize":
            hdrs["MCP-Protocol-Version"] = self.protocol
        req = urllib.request.Request(self.url, data=json.dumps(msg).encode(), headers=hdrs, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            raise McpError(f"{self.name}: HTTP {e.code} for {msg.get('method') or 'message'}") from None
        except (urllib.error.URLError, OSError) as e:
            raise McpError(f"{self.name}: couldn't reach the server ({getattr(e, 'reason', e)})") from None
        with resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid and msg.get("method") == "initialize":
                self.session = sid
            if not expect_response:
                return None
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
            if ctype == "text/event-stream":
                return self._from_sse(resp, msg["id"])
            body = resp.read().decode("utf-8", "replace")
            return json.loads(body) if body.strip() else None

    def _from_sse(self, resp, rid):
        data = []
        for raw in resp:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith("data:"):
                data.append(line[5:].lstrip())
            elif line == "" and data:
                try:
                    msg = json.loads("\n".join(data))
                except ValueError:
                    msg = None
                data = []
                if isinstance(msg, dict) and msg.get("id") == rid and ("result" in msg or "error" in msg):
                    return msg
        raise McpError(f"{self.name}: the event stream ended without an answer")

    def notify(self, method, params=None):
        self._post({"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}, False)

    def request(self, method, params=None):
        rid = self._next_id()
        msg = self._post({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}, True)
        if not isinstance(msg, dict):
            raise McpError(f"{self.name}: no answer to {method}")
        if "error" in msg:
            err = msg["error"] or {}
            raise McpError(f"{self.name}: {method} failed ({err.get('code')}): {str(err.get('message'))[:300]}")
        return msg.get("result") or {}

    def close(self):
        if not self.session:
            return
        hdrs = {"Mcp-Session-Id": self.session, "MCP-Protocol-Version": self.protocol, **self.headers}
        try:
            urllib.request.urlopen(urllib.request.Request(self.url, headers=hdrs, method="DELETE"), timeout=5).close()
        except (urllib.error.URLError, OSError):
            pass                                 # 405 and network errors: nothing to do


def connect(name, spec, timeout=60):
    """Start (stdio) or reach (http) a server and run the initialize handshake."""
    kind = spec.get("type") or ("http" if spec.get("url") else "stdio")
    if kind == "stdio":
        if not spec.get("command"):
            raise McpError(f"{name}: a stdio server needs a command")
        srv = StdioServer(name, spec, timeout)
    elif kind == "http":
        srv = HttpServer(name, spec, timeout)
    else:
        raise McpError(f"{name}: unknown server type {kind!r} (stdio or http)")
    try:
        srv.initialize()
    except McpError:
        srv.close()
        raise
    return srv


def result_text(result):
    """The text parts of a tools/call result, for the model."""
    parts = []
    for c in (result or {}).get("content") or []:
        if c.get("type") == "text":
            parts.append(c.get("text") or "")
        elif c.get("type") == "resource" and isinstance(c.get("resource"), dict):
            parts.append(c["resource"].get("text") or f"[resource {c['resource'].get('uri')}]")
        else:
            parts.append(f"[{c.get('type')} content not shown]")
    if not parts and (result or {}).get("structuredContent") is not None:
        parts.append(json.dumps(result["structuredContent"])[:20000])
    return "\n".join(parts)

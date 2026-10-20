#!/usr/bin/env python3
"""A fake MCP server for kit-run's tests. Never contacts anything.

  fake_mcp_server.py                 stdio transport (newline-delimited JSON-RPC 2.0)
  fake_mcp_server.py --http PORTFILE Streamable HTTP on 127.0.0.1 (FAKE_MCP_SSE=1 answers as an
                                     event stream; otherwise one JSON object per request)

Tools: get_item and search_items (read-only), delete_item (a write), fail_tool (answers with a
JSON-RPC error), err_tool (a result with isError true). If FAKE_MCP_LOG is set, every message and,
for HTTP, the session and protocol headers seen, are appended to it as JSON lines.
"""
import http.server
import json
import os
import sys

LOG = os.environ.get("FAKE_MCP_LOG")
TOOLS = [
    {"name": "get_item", "description": "Get an item by id.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "search_items", "description": "Search items.",
     "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}}},
    {"name": "delete_item", "description": "Delete an item.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}}},
    {"name": "fail_tool", "description": "Always fails.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "err_tool", "description": "Reports an error result.", "inputSchema": {"type": "object", "properties": {}}},
]


def log(rec):
    if LOG:
        with open(LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")


def handle(msg):
    """The response for one message, or None for a notification."""
    log({"recv": msg})
    method, rid = msg.get("method"), msg.get("id")
    if rid is None:
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake-mcp", "version": "0.1"}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name, args = msg["params"]["name"], msg["params"].get("arguments") or {}
        if name == "get_item":
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": f"item {args.get('id')}: a test item"}]}}
        if name == "search_items":
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": "2 results"}]}}
        if name == "delete_item":
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": "deleted"}]}}
        if name == "fail_tool":
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": "backend unavailable"}}
        if name == "err_tool":
            return {"jsonrpc": "2.0", "id": rid, "result": {"isError": True, "content": [{"type": "text", "text": "permission problem"}]}}
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": f"Unknown tool: {name}"}}
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}}


def stdio():
    print("fake-mcp starting", file=sys.stderr, flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        resp = handle(json.loads(line))
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        msg = json.loads(self.rfile.read(n))
        log({"http": "POST", "session": self.headers.get("Mcp-Session-Id"),
             "protocol": self.headers.get("MCP-Protocol-Version"), "accept": self.headers.get("Accept"),
             "method": msg.get("method")})
        resp = handle(msg)
        if resp is None:
            self.send_response(202)
            self.send_header("content-length", "0")
            self.end_headers()
            return
        body = json.dumps(resp)
        sse = os.environ.get("FAKE_MCP_SSE") == "1"
        data = (f"event: message\ndata: {body}\n\n" if sse else body).encode()
        self.send_response(200)
        self.send_header("content-type", "text/event-stream" if sse else "application/json")
        if msg.get("method") == "initialize":
            self.send_header("Mcp-Session-Id", "test-session-1")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_DELETE(self):
        log({"http": "DELETE", "session": self.headers.get("Mcp-Session-Id")})
        self.send_response(204)
        self.end_headers()


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--http":
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        with open(sys.argv[2], "w") as f:
            f.write(str(srv.server_address[1]))
        srv.serve_forever()
    else:
        stdio()

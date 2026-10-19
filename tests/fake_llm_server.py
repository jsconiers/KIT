#!/usr/bin/env python3
"""A fake model server for Kit's tests: speaks just enough of the Anthropic Messages API
(POST .../v1/messages) and the OpenAI chat-completions API (POST .../chat/completions) to test
kit_providers, kit-delegate, and kit-run. Binds 127.0.0.1 only; never forwards anything.

  fake_llm_server.py SCRIPT.json PORTFILE LOG.jsonl

SCRIPT.json: {"anthropic": [response, ...], "openai": [response, ...]}. Each response is either a
JSON body to return with HTTP 200, or {"_status": N} to fail with that status. Responses are used
in order; when a list runs out, the last one repeats. Any path containing /reject/ gets HTTP
400, for testing errors that aren't retried. Each request is logged (path, which auth
header was present and whether it matched FAKE_EXPECT_CREDENTIAL, and the body).
"""
import http.server
import json
import os
import sys
import threading

script = json.load(open(sys.argv[1]))
portfile, logfile = sys.argv[2], sys.argv[3]
lock = threading.Lock()
pos = {"anthropic": 0, "openai": 0}
expect = os.environ.get("FAKE_EXPECT_CREDENTIAL", "")


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        kind = "anthropic" if self.path.split("?")[0].endswith("/v1/messages") else \
            "openai" if "/chat/completions" in self.path else None
        auth = {}
        for h in ("x-api-key", "api-key"):
            if self.headers.get(h) is not None:
                auth[h] = self.headers.get(h) == expect
        if self.headers.get("authorization") is not None:
            auth["authorization"] = self.headers.get("authorization") == "Bearer " + expect
        with lock:
            items = script.get(kind) or [{"_status": 404}]
            resp = items[min(pos.get(kind, 0), len(items) - 1)]
            pos[kind] = pos.get(kind, 0) + 1
            with open(logfile, "a") as f:
                f.write(json.dumps({"path": self.path, "kind": kind, "auth": auth,
                                    "anthropic_version": self.headers.get("anthropic-version"),
                                    "body": body}) + "\n")
        status = resp.get("_status", 200) if isinstance(resp, dict) else 200
        if "/reject/" in self.path:
            status = 400                        # a non-retryable error, for tests
        data = json.dumps(resp if status == 200 else {"error": {"message": "fake failure"}}).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
with open(portfile, "w") as f:
    f.write(str(srv.server_address[1]))
srv.serve_forever()

#!/usr/bin/env python3
"""ppmx_container_smoke: run the standalone PPM Express MCP server the way OpenShift runs it, against the
fake PPM Express, and check it over HTTP. GitHub's checks run it on every push.

  python3 tests/ppmx_container_smoke.py --image ppmx-mcp:ci
        the container image, run as a random non-root user in group 0 with a read-only filesystem, no
        capabilities, and /tmp in memory (needs docker or podman, and host networking)
  python3 tests/ppmx_container_smoke.py --gunicorn PATH/TO/gunicorn
        the same server under a local gunicorn, without a container

It checks health and readiness, MCP initialize and tools/list, that each caller sees only their own data
(two tokens, two answers), that a change is made with the caller's own token (one that can't write is
refused by PPM Express), that a call without a token or from a browser origin is refused, and that no token
appears anywhere in the server's output while every call, changes included, is in the audit log. Exit 1 if
anything failed.
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fake_ppmx  # noqa: E402

FAKE_PORT, PORT = 18080, 8080
URL = f"http://127.0.0.1:{PORT}"
ALEX, BLAKE = "token-alex-0001", "token-blake-0002"
FAILS = []


def ok(cond, name, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f": {detail}"))
    if not cond:
        FAILS.append(name)


def get(path):
    try:
        with urllib.request.urlopen(URL + path, timeout=5) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def mcp(message, token=None, headers=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if token:
        h["X-PPMX-Token"] = token
    h.update(headers or {})
    req = urllib.request.Request(URL + "/mcp", data=json.dumps(message).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def call(tool, args, token=None, headers=None):
    status, body = mcp({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                        "params": {"name": tool, "arguments": args}}, token, headers)
    res = (body or {}).get("result") or {}
    text = (res.get("content") or [{}])[0].get("text", "")
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    return status, res.get("isError"), data, text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image")
    ap.add_argument("--gunicorn")
    ap.add_argument("--engine", default=shutil.which("docker") or shutil.which("podman") or "docker")
    a = ap.parse_args()
    if not (a.image or a.gunicorn):
        ap.error("give --image or --gunicorn")
    server, _, base = fake_ppmx.start(FAKE_PORT)
    env = {"PPMX_BASE_URL": base, "PPMX_TODAY": "2026-10-30"}
    log = tempfile.NamedTemporaryFile("w+", suffix=".log", delete=False)
    if a.image:
        subprocess.run([a.engine, "rm", "-f", "ppmx-smoke"], capture_output=True)
        cmd = [a.engine, "run", "-d", "--name", "ppmx-smoke", "--network", "host",
               "--user", "1000770000:0", "--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges"]
        for k, v in env.items():
            cmd += ["-e", f"{k}={v}"]
        r = subprocess.run(cmd + [a.image], capture_output=True, text=True)
        ok(r.returncode == 0, "the container starts", r.stderr.strip()[-300:])
        proc = None
    else:
        proc = subprocess.Popen([a.gunicorn, "--bind", f"127.0.0.1:{PORT}", "--workers", "2", "--threads", "4",
                                 "--no-control-socket", "--chdir", str(HERE.parent / "shared"),
                                 "ppmx.server_http:application"],
                                env={**os.environ, **env}, stdout=log, stderr=subprocess.STDOUT)
    try:
        status = None
        for _ in range(60):
            try:
                status, _ = get("/healthz")
                break
            except (urllib.error.URLError, OSError, ValueError):
                time.sleep(1)
        ok(status == 200, "/healthz answers", str(status))
        ok(get("/readyz") == (200, {"status": "ready"}), "/readyz: configured")
        s, b = mcp({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "1"}}})
        ok(s == 200 and b["result"]["protocolVersion"] == "2025-06-18" and b["result"]["serverInfo"]["name"] == "ppmx",
           "initialize", json.dumps(b)[:200])
        s, b = mcp({"jsonrpc": "2.0", "method": "notifications/initialized"})
        ok(s == 202, "a notification gets 202 and no body", str(s))
        s, b = mcp({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers={"MCP-Protocol-Version": "2025-06-18"})
        tools = (b or {}).get("result", {}).get("tools", [])
        reads = [t for t in tools if t["annotations"]["readOnlyHint"]]
        ok(len(tools) == 22 and len(reads) == 11 and all(t["name"].startswith(("get_", "list_")) for t in reads),
           "tools/list: 11 reads and 11 changes", str([t["name"] for t in tools]))
        _, err, alex, _ = call("list_projects", {}, ALEX)
        _, err2, blake, _ = call("list_projects", {}, BLAKE)
        ok(not err and alex["total"] == 3 and not err2 and blake["total"] == 1
           and blake["items"][0]["Name"] == "Payments upgrade", "each caller sees only their own projects")
        _, err, made, _ = call("create_task", {"project_id": fake_ppmx.A1, "name": "Smoke test task",
                                               "fields": {"Status": "At Risk"}}, ALEX)
        _, err2, _, text = call("create_task", {"project_id": fake_ppmx.A1, "name": "Not allowed"}, BLAKE)
        ok(not err and made["result"] == "created" and made["record"]["Status"] == "At Risk"
           and err2 and "write scopes" in text, "a change is made with the caller's own token", text)
        _, err, _, text = call("list_projects", {}, None)
        ok(err and "X-PPMX-Token" in text, "no token: the tool says how to send one", text)
        _, err, me, _ = call("get_current_user", {}, None, {"Authorization": f"Bearer {BLAKE}"})
        ok(not err and me["email"] == "blake@example.com", "a token as Authorization: Bearer works too")
        s, _ = mcp({"jsonrpc": "2.0", "id": 3, "method": "ping"}, ALEX, {"Origin": "https://evil.example.com"})
        ok(s == 403, "a request from a browser origin is refused", str(s))
        s, _ = get("/mcp")
        ok(s == 405, "GET /mcp: 405, no event stream", str(s))
    finally:
        if a.image:
            out = subprocess.run([a.engine, "logs", "ppmx-smoke"], capture_output=True, text=True)
            logs = out.stdout + out.stderr
            subprocess.run([a.engine, "rm", "-f", "ppmx-smoke"], capture_output=True)
        else:
            proc.terminate()
            proc.wait(timeout=20)
            log.seek(0)
            logs = log.read()
        server.shutdown()
    ok(ALEX not in logs and BLAKE not in logs, "no token in the server's output")
    ok('"tool": "list_projects"' in logs and '"user": "u:' in logs and '"write": "create"' in logs
       and "Smoke test task" not in logs, "the audit log records calls and changes by user hash, never values",
       logs[-400:])
    os.unlink(log.name)
    print(f"\nppmx container smoke: {'all passed' if not FAILS else f'{len(FAILS)} failed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())

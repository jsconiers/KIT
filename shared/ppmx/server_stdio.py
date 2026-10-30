"""The one-person way to run the server: MCP over standard input and output, one JSON message per line,
started on the person's own computer by Claude Code or Claude Desktop (`kit-ppmx serve`, or
`python -m ppmx stdio`). The token comes from token_source, asked for the first time a tool is called.
"""
import datetime
import json
import sys
import time

from .client import token_key
from .mcp_core import error


def serve(dispatcher, token_source, stdin=None, stdout=None, log=None):
    """Answer messages until standard input closes. token_source() returns the token, or "" when there
    is none (the tools then say where to set one). log, when given, receives one audit line (a dict)
    per tool call: no token and no argument values."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for stream in (stdin, stdout):                    # MCP's stdio is UTF-8, whatever the platform's default
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    token = None
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            _write(stdout, error(None, -32700, "parse error"))
            continue
        batch = msg if isinstance(msg, list) else [msg]
        replies = []
        for m in batch:
            if token is None and isinstance(m, dict) and m.get("method") == "tools/call":
                token = token_source() or ""
            facts, started = {}, time.monotonic()
            reply = dispatcher.handle(m, token, facts.update)
            if reply is not None:
                replies.append(reply)
            if log and facts.get("tool"):
                _audit(log, facts, token, started)
        if replies:
            _write(stdout, replies if isinstance(msg, list) else replies[0])
    return 0


def _audit(log, facts, token, started):
    try:
        log({"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "via": "stdio",
             "user": f"u:{token_key(token)[:12]}" if token else "-", **facts,
             "ms": round((time.monotonic() - started) * 1000)})
    except Exception:  # noqa: BLE001 - a full disk or a closed log mustn't stop the server answering
        pass


def stderr_log(entry):
    sys.stderr.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    sys.stderr.flush()


def _write(stdout, msg):
    stdout.write(json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n")
    stdout.flush()

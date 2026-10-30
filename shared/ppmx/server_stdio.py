"""Kit's way to run the server: MCP over standard input and output, one JSON message per line, started by
Claude Code on the owner's computer (`kit-ppmx serve`, or `python -m ppmx stdio`). One user: the token
comes from token_source, asked for the first time a tool is called.
"""
import json
import sys

from .mcp_core import error


def serve(dispatcher, token_source, stdin=None, stdout=None):
    """Answer messages until standard input closes. token_source() returns the token, or "" when there
    is none (the tools then say where to set one)."""
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
            reply = dispatcher.handle(m, token)
            if reply is not None:
                replies.append(reply)
        if replies:
            _write(stdout, replies if isinstance(msg, list) else replies[0])
    return 0


def _write(stdout, msg):
    stdout.write(json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n")
    stdout.flush()

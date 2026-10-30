"""The standalone server: MCP over Streamable HTTP, stateless (each POST to /mcp gets one JSON answer), for
a container platform such as OpenShift. It's a WSGI application; run it with gunicorn:

    gunicorn --bind 0.0.0.0:8080 ppmx.server_http:application

or, for a quick local try, `python -m ppmx http` (the standard library's server, not for production).

Each caller sends their own PPM Express personal access token on every request, in the X-PPMX-Token
header, or as Authorization: Bearer when nothing in front of the server uses that header. The server
passes it to PPM Express and never stores or logs it. Answers are cached per caller, never across
callers. The audit log (standard error, one JSON line per message) records who (a one-way hash of the
token), which method and tool, the argument names (not their values), the outcome, rows returned, and
the time taken.

  POST /mcp     MCP messages (one, or a batch)
  GET  /healthz the process is up
  GET  /readyz  the server is configured (PPMX_BASE_URL is usable)
  GET  /mcp     405: the server sends no messages of its own, so there's no stream to open
"""
import datetime
import json
import sys
import time
import uuid

from .client import Client, token_key, valid_token
from .codes import load as load_codes
from .config import Settings
from .mcp_core import PROTOCOL_VERSIONS, Dispatcher, error
from .tools import Context

HINT = ("No personal access token came with this request: send yours in the X-PPMX-Token header "
        "(create one in PPM Express > Automation).")
BAD_TOKEN = "The personal access token in this request isn't valid."
REASONS = {200: "OK", 202: "Accepted", 400: "Bad Request", 403: "Forbidden", 404: "Not Found",
           405: "Method Not Allowed", 406: "Not Acceptable", 413: "Payload Too Large",
           415: "Unsupported Media Type", 503: "Service Unavailable"}


def stderr_log(entry):
    sys.stderr.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    sys.stderr.flush()


def caller_token(environ):
    """(token, hint): the caller's token, or "" and why there's none."""
    token = (environ.get("HTTP_X_PPMX_TOKEN") or "").strip()
    if not token:
        auth = (environ.get("HTTP_AUTHORIZATION") or "").strip()
        if auth[:7].lower() == "bearer ":
            token = auth[7:].strip()
    if not token:
        return "", HINT
    if not valid_token(token):
        return "", BAD_TOKEN
    return token, ""


def make_app(settings=None, client=None, log=None):
    settings = settings or Settings()
    client = client or Client(settings)
    tables = load_codes(settings.codes_file)          # a bad codes file stops the server at start
    log = log or stderr_log

    def respond(start_response, status, body=None, extra=()):
        data = b"" if body is None else json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        headers = [("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                   ("Content-Length", str(len(data)))]
        if body is not None:
            headers.insert(0, ("Content-Type", "application/json"))
        start_response(f"{status} {REASONS[status]}", headers + list(extra))
        return [data]

    def app(environ, start_response):
        path = environ.get("PATH_INFO") or "/"
        method = environ.get("REQUEST_METHOD", "GET")
        if path == "/healthz":
            return respond(start_response, 200, {"status": "ok"})
        if path == "/readyz":
            if settings.ready:
                return respond(start_response, 200, {"status": "ready"})
            return respond(start_response, 503, {"status": "not ready", "reason": settings.problem})
        if path != "/mcp":
            return respond(start_response, 404, {"error": "not found"})
        if method != "POST":
            return respond(start_response, 405, {"error": "this server takes MCP messages by POST only"},
                           [("Allow", "POST")])
        origin = (environ.get("HTTP_ORIGIN") or "").rstrip("/")
        if origin and origin not in settings.allowed_origins:
            return respond(start_response, 403, {"error": "this origin isn't allowed"})
        ctype = (environ.get("CONTENT_TYPE") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            return respond(start_response, 415, {"error": "send application/json"})
        accept = (environ.get("HTTP_ACCEPT") or "").lower()
        if accept and "application/json" not in accept and "*/*" not in accept:
            return respond(start_response, 406, {"error": "this server answers with application/json"})
        version = (environ.get("HTTP_MCP_PROTOCOL_VERSION") or "").strip()
        if version and version not in PROTOCOL_VERSIONS:
            return respond(start_response, 400, {"error": f"unsupported MCP protocol version {version}"})
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > settings.max_body:
            return respond(start_response, 413, {"error": "request body too large"})
        try:
            msg = json.loads((environ["wsgi.input"].read(length) if length else b"").decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return respond(start_response, 400, error(None, -32700, "parse error"))

        token, hint = caller_token(environ)
        dispatcher = Dispatcher(lambda t: Context(client, settings, tables, t, hint=hint))
        who = f"u:{token_key(token)[:12]}" if token else "-"
        rid = (environ.get("HTTP_X_REQUEST_ID") or uuid.uuid4().hex[:12])[:64]
        ip = (environ.get("HTTP_X_FORWARDED_FOR") or environ.get("REMOTE_ADDR") or "").split(",")[0].strip()
        replies = []
        for m in (msg if isinstance(msg, list) else [msg]):
            facts, started = {}, time.monotonic()
            reply = dispatcher.handle(m, token, facts.update)
            if reply is not None:
                replies.append(reply)
            if settings.audit and facts:
                log({"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                     "rid": rid, "ip": ip[:64], "user": who, **facts,
                     "ms": round((time.monotonic() - started) * 1000)})
        if not replies:
            return respond(start_response, 202)
        return respond(start_response, 200, replies if isinstance(msg, list) else replies[0])

    return app


application = make_app()

"""A small client for PPM Express's public REST API, shared by the stdio and HTTP servers: GET to read,
POST to create, PATCH to update. PPM Express's API has no delete.

Every request carries the caller's personal access token (Authorization: Bearer). Answers are cached per
caller, never shared between callers, and a caller's write clears their cache. Each caller's requests
are paced (PPMX_RATE_PER_MINUTE). Redirects aren't followed, so a token never goes to another address.
A write is retried only when PPM Express said it didn't take it (429 or 503), never after a timeout or
a dropped connection, so nothing is created twice. Errors come back as PPMXError with a message that's
safe to show: never the token, and at most a short excerpt of what PPM Express said.
"""
import collections
import copy
import email.utils
import hashlib
import http.client
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

# Paths under the tenant's base URL (https://<host>/@<tenant>/v1.0). CONFIRMED on 02-Nov-2026 against PPM
# Express's OpenAPI 3.0 description (<host>/v1.0/swagger.json, 72 paths, all lowercase) and, for the reads,
# against a live tenant. This table is the one place to correct them. Reads use GET; the same paths take
# POST (a new record, under "attributes"; a sub-task adds "parentId") and PATCH (a change, under "updates").
# Lists come back whole as {"data": [...]}: the API takes no paging parameters on any list used here (only
# the external-system task list pages, with pageSize and pageNumber, and Kit doesn't use it).
ENDPOINTS = {
    "me": "me",
    "user": "users/{id}",                              # needs user-list permission in PPM Express (often 403)
    "portfolios": "portfolios",
    "portfolio": "portfolios/{id}",
    "programs": "programs",
    "program": "programs/{id}",
    "projects": "projects",
    "project": "projects/{id}",
    "tasks": "projects/{id}/tasks",
    "task": "projects/{id}/tasks/{task_id}",
    "key_dates": "projects/{id}/keydates",
    "key_date": "projects/{id}/keydates/{key_date_id}",
    "deliverables": "projects/{id}/deliverables",
    "deliverable": "projects/{id}/deliverables/{deliverable_id}",
    "ideas": "ideas",
    "idea": "ideas/{id}",
    "idea_stage": "ideas/{id}/stage",                  # body {"stage": "Active"}: the stage's name, no spaces
    "challenges": "challenges",
    "challenge": "challenges/{id}",
    "resources": "resources",
    "resource": "resources/{id}",
    "fields": "fields/{entity}",
}
# Query parameter names (confirmed: GET and POST ideas take challengeId).
PARAMS = {"challenge": "challengeId"}
# The token's /me answer is kept this long per token (for "me" in person filters), never across tokens.
ME_SECONDS = 600

UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ENTITY = re.compile(r"^[A-Za-z]{1,40}$")
TOKEN = re.compile(r"^[\x21-\x7e]{8,4096}$")        # printable, no spaces: nothing that could split a header
RETRY_STATUS = {429, 502, 503, 504}
WRITE_RETRY_STATUS = {429, 503}                      # PPM Express said it didn't take the request
MAX_BODY = 262144                                    # the largest create or update this client sends
MAX_REPLY = 16 * 1048576
CACHE_ENTRIES = 1000


class PPMXError(Exception):
    """A failed PPM Express request. str() is safe to show to the caller."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def token_key(token):
    """A short one-way name for a token, for the cache and the audit log. Never reveals the token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def valid_token(token):
    return bool(token) and bool(TOKEN.match(token))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None                                   # the 3xx surfaces as an HTTPError instead


class Client:
    def __init__(self, settings, opener=None, sleep=time.sleep, clock=time.monotonic):
        self.settings = settings
        self._open = opener or urllib.request.build_opener(_NoRedirect()).open
        self._sleep, self._clock = sleep, clock
        self._lock = threading.Lock()
        self._cache = collections.OrderedDict()       # (token key, url) -> (expires, value)
        self._calls = {}                              # token key -> times of recent requests
        self._me = {}                                 # token key -> (expires, who the token is)
        self.requests = 0                             # requests sent to PPM Express (tests read it)

    # ---- paths
    def path(self, name, **parts):
        template = ENDPOINTS[name]
        for key, value in parts.items():
            value = str(value)
            if (key == "id" or key.endswith("_id")) and not UUID.match(value):
                raise PPMXError(400, f"{value!r} isn't a PPM Express ID (a UUID)")
            if key == "entity" and not ENTITY.match(value):
                raise PPMXError(400, f"{value!r} isn't an entity name")
            template = template.replace("{" + key + "}", urllib.parse.quote(value, safe=""))
        return template

    # ---- requests
    def _url(self, token, name, params, parts):
        if not self.settings.ready:
            raise PPMXError(503, self.settings.problem or "the server isn't configured")
        if not valid_token(token):
            raise PPMXError(401, "no personal access token" if not token else "the personal access token isn't valid")
        url = f"{self.settings.base_url}/{self.path(name, **parts)}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return url

    def get(self, token, name, params=None, **parts):
        """The JSON PPM Express returns for one endpoint (a list comes whole, as {"data": [...]})."""
        url = self._url(token, name, params, parts)
        key = (token_key(token), url)
        hit = self._cached(key)
        if hit is not None:
            return hit
        value = self._request(token, url)
        self._store(key, value)
        return copy.deepcopy(value)

    def whoami(self, token):
        """Who a token belongs to, for "me" in person filters: {"id", "email", "logonAccount", "fullName",
        "scopes"}, from /me (and users/{id} for the full name, where PPM Express allows it). Kept for
        ME_SECONDS per token, never shared between tokens."""
        tk = token_key(token)
        with self._lock:
            hit = self._me.get(tk)
            if hit and hit[0] > self._clock():
                return copy.deepcopy(hit[1])
        rec = (records(self.get(token, "me")) or [{}])[0]
        who = {k: rec.get(k) for k in ("id", "email", "logonAccount") if rec.get(k)}
        tok = rec.get("token") if isinstance(rec.get("token"), dict) else {}
        who["scopes"] = [str(x) for x in tok.get("scopes") or []]
        who["fullName"] = rec.get("fullName") or rec.get("displayName") or rec.get("name") or ""
        if not who["fullName"] and who.get("id") and UUID.match(str(who["id"])):
            try:
                user = (records(self.get(token, "user", id=who["id"])) or [{}])[0]
                who["fullName"] = user.get("fullName") or ""
            except PPMXError:
                pass                                  # 403 without user-list permission: go without
        with self._lock:
            self._me[tk] = (self._clock() + ME_SECONDS, copy.deepcopy(who))
            if len(self._me) > CACHE_ENTRIES:
                self._me.pop(next(iter(self._me)))
        return who

    def send(self, token, method, name, body, params=None, **parts):
        """POST (create) or PATCH (update) one endpoint with a JSON body; the JSON PPM Express answers
        with (None when it sends nothing back). The caller's cached answers are dropped either way."""
        if method not in ("POST", "PATCH"):
            raise PPMXError(400, f"{method} isn't a write this client makes")
        url = self._url(token, name, params, parts)
        data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        if len(data) > MAX_BODY:
            raise PPMXError(413, "that change is too large to send")
        try:
            return self._request(token, url, method, data)
        finally:
            self.forget(token)

    def forget(self, token):
        """Drop one caller's cached answers (after a write, so the next read sees it)."""
        tk = token_key(token)
        with self._lock:
            for key in [k for k in self._cache if k[0] == tk]:
                del self._cache[key]

    def _request(self, token, url, method="GET", data=None):
        tk = token_key(token)
        write = method != "GET"
        for attempt in range(4):
            self._pace(tk)
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json",
                       "User-Agent": f"ppmx-mcp/{__version__}"}
            if data is not None:
                headers["Content-Type"] = "application/json"
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with self._lock:
                    self.requests += 1
                with self._open(req, timeout=self.settings.timeout) as r:
                    body = r.read(MAX_REPLY + 1)
            except urllib.error.HTTPError as e:
                if e.code in (WRITE_RETRY_STATUS if write else RETRY_STATUS) and attempt < 3:
                    self._sleep(retry_after(e.headers.get("Retry-After") if e.headers else None, attempt))
                    continue
                if write and e.code >= 500:           # a server error after it got the change: it may be made
                    raise PPMXError(e.code, f"couldn't confirm PPM Express made the change ({http_message(e)}); "
                                            "check there before trying again") from None
                raise PPMXError(e.code, http_message(e)) from None
            except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as e:
                if write:                             # it may have arrived: never send it twice
                    raise PPMXError(504, f"couldn't confirm PPM Express made the change ({reason(e)}); check "
                                         "there before trying again") from None
                if attempt < 2:
                    self._sleep(2 ** attempt)
                    continue
                raise PPMXError(504, f"couldn't reach PPM Express ({reason(e)})") from None
            if len(body) > MAX_REPLY:
                raise PPMXError(502, "PPM Express's reply was too large")
            try:
                return json.loads(body.decode("utf-8-sig") or "null")
            except (ValueError, UnicodeDecodeError):
                if write:
                    raise PPMXError(502, "PPM Express accepted the change but its reply isn't JSON; check "
                                         "there") from None
                raise PPMXError(502, "PPM Express sent a reply that isn't JSON") from None
        raise PPMXError(503, "PPM Express kept asking to wait; try again shortly")

    def _pace(self, tk):
        """Hold one caller to PPMX_RATE_PER_MINUTE requests in any 60 seconds."""
        while True:
            with self._lock:
                now = self._clock()
                recent = self._calls.setdefault(tk, collections.deque())
                while recent and now - recent[0] >= 60:
                    recent.popleft()
                if len(recent) < self.settings.rate_per_minute:
                    recent.append(now)
                    if len(self._calls) > 1000:       # forget callers who've gone quiet
                        for k in [k for k, q in self._calls.items() if not q]:
                            self._calls.pop(k, None)
                    return
                wait = 60 - (now - recent[0])
            if wait > 30:
                raise PPMXError(429, "this token has made too many requests to PPM Express in the last "
                                     "minute; try again shortly")
            self._sleep(max(wait, 0.05))

    # ---- the per-caller cache
    def _cached(self, key):
        if self.settings.cache_seconds <= 0:
            return None
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] > self._clock():
                return copy.deepcopy(hit[1])
            self._cache.pop(key, None)
        return None

    def _store(self, key, value):
        if self.settings.cache_seconds <= 0:
            return
        with self._lock:
            self._cache[key] = (self._clock() + self.settings.cache_seconds, copy.deepcopy(value))
            while len(self._cache) > CACHE_ENTRIES:
                self._cache.popitem(last=False)


def records(value):
    """The items of a PPM Express answer, each flattened to {"id": ..., <attributes>, <other fields>}."""
    data = value.get("data") if isinstance(value, dict) and "data" in value else value
    if isinstance(data, dict):
        data = [data]
    out = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        row = {"id": item.get("id")}
        if isinstance(item.get("attributes"), dict):
            row.update(item["attributes"])
        for key, val in item.items():
            if key not in ("id", "attributes", "type", "links", "relationships"):
                row.setdefault(key, val)
        out.append(row)
    return out


def retry_after(value, attempt):
    """Seconds to wait before retrying: the server's Retry-After (seconds or a date), at most 10."""
    if value:
        value = value.strip()
        if value.isdigit():
            return min(int(value), 10)
        try:
            when = email.utils.parsedate_to_datetime(value)
            return min(max(when.timestamp() - time.time(), 0), 10)
        except (TypeError, ValueError, OverflowError):
            pass
    return min(2 ** attempt, 10)


def scrub(text, limit=200):
    text = re.sub(r"(?i)(bearer\s+)\S+", r"\1[hidden]", text or "")
    text = re.sub(r"(?i)(token|password|secret|key)(\W{1,3})[^\s\"',;]+", r"\1\2[hidden]", text)
    return " ".join(text.split())[:limit]


def http_message(e):
    code = e.code
    if code == 401:
        return ("PPM Express rejected the token: it may have expired or been revoked. Create a new personal "
                "access token in PPM Express > Automation.")
    if code == 403:
        return ("PPM Express refused: the token's scopes or your PPM Express permissions don't allow this "
                "(a read needs the matching read scope, such as project:read, and a change its write scope, "
                "such as project:write; PPM Express's own permissions for your account apply too).")
    if code == 404:
        return "PPM Express has no such item, or this tenant doesn't offer that endpoint."
    if code == 429:
        return "PPM Express is limiting requests; try again in a minute."
    if 300 <= code < 400:
        return "PPM Express redirected the request; check PPMX_BASE_URL."
    detail = ""
    try:
        detail = scrub(e.read(600).decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        pass
    return f"PPM Express answered {code}" + (f": {detail}" if detail else "")


def reason(e):
    r = getattr(e, "reason", None)
    return scrub(str(r) if r else e.__class__.__name__, 120)

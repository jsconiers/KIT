"""A small read-only client for PPM Express's public REST API, shared by the stdio and HTTP servers.

Every request carries the caller's personal access token (Authorization: Bearer). Answers are cached per
caller, never shared between callers, and each caller's requests are paced (PPMX_RATE_PER_MINUTE).
Redirects aren't followed, so a token never goes to another address. Errors come back as PPMXError with
a message that's safe to show: never the token, and at most a short excerpt of what PPM Express said.
"""
import collections
import copy
import email.utils
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

# Paths under the tenant's base URL (https://<host>/@<tenant>/v1.0), from PPM Express's published API
# description. PROVISIONAL: check each against your tenant's endpoint reference (PPM Express >
# Automation > Swagger) before live use. This table is the one place to correct them.
ENDPOINTS = {
    "me": "Me",
    "portfolios": "Portfolios",
    "programs": "Programs",
    "projects": "Projects",
    "project": "Projects/{id}",
    "tasks": "Projects/{id}/Tasks",
    "key_dates": "Projects/{id}/KeyDates",
    "ideas": "Ideas",
    "challenges": "Challenges",
    "resources": "Resources",
    "fields": "Fields/{entity}",
}
# Query parameter names, equally provisional.
PARAMS = {"challenge": "challengeId"}

UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ENTITY = re.compile(r"^[A-Za-z]{1,40}$")
TOKEN = re.compile(r"^[\x21-\x7e]{8,4096}$")        # printable, no spaces: nothing that could split a header
RETRY_STATUS = {429, 502, 503, 504}
MAX_PAGES = 50
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
        self.requests = 0                             # requests sent to PPM Express (tests read it)

    # ---- paths
    def path(self, name, **parts):
        template = ENDPOINTS[name]
        for key, value in parts.items():
            value = str(value)
            if key == "id" and not UUID.match(value):
                raise PPMXError(400, f"{value!r} isn't a PPM Express ID (a UUID)")
            if key == "entity" and not ENTITY.match(value):
                raise PPMXError(400, f"{value!r} isn't an entity name")
            template = template.replace("{" + key + "}", urllib.parse.quote(value, safe=""))
        return template

    # ---- requests
    def get(self, token, name, params=None, **parts):
        """The JSON PPM Express returns for one endpoint. A list that pages is followed through its
        next links on the same base URL (up to MAX_PAGES) and returned as one {"data": [...]}."""
        if not self.settings.ready:
            raise PPMXError(503, self.settings.problem or "the server isn't configured")
        if not valid_token(token):
            raise PPMXError(401, "no personal access token" if not token else "the personal access token isn't valid")
        url = f"{self.settings.base_url}/{self.path(name, **parts)}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        key = (token_key(token), url)
        hit = self._cached(key)
        if hit is not None:
            return hit
        value = self._request(token, url)
        if isinstance(value, dict) and isinstance(value.get("data"), list):
            items, page, pages = list(value["data"]), value, 1
            while pages < MAX_PAGES:
                nxt = next_link(page)
                if not nxt or not nxt.startswith(self.settings.base_url + "/"):
                    break
                page = self._request(token, nxt)
                items.extend((page.get("data") or []) if isinstance(page, dict) else [])
                pages += 1
            value = {"data": items}
        self._store(key, value)
        return copy.deepcopy(value)

    def _request(self, token, url):
        tk = token_key(token)
        for attempt in range(4):
            self._pace(tk)
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {token}", "Accept": "application/json",
                "User-Agent": f"ppmx-mcp/{__version__}"})
            try:
                with self._lock:
                    self.requests += 1
                with self._open(req, timeout=self.settings.timeout) as r:
                    body = r.read(MAX_REPLY + 1)
            except urllib.error.HTTPError as e:
                if e.code in RETRY_STATUS and attempt < 3:
                    self._sleep(retry_after(e.headers.get("Retry-After") if e.headers else None, attempt))
                    continue
                raise PPMXError(e.code, http_message(e)) from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt < 2:
                    self._sleep(2 ** attempt)
                    continue
                raise PPMXError(504, f"couldn't reach PPM Express ({reason(e)})") from None
            if len(body) > MAX_REPLY:
                raise PPMXError(502, "PPM Express's reply was too large")
            try:
                return json.loads(body.decode("utf-8-sig") or "null")
            except (ValueError, UnicodeDecodeError):
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


def next_link(page):
    if not isinstance(page, dict):
        return None
    links = page.get("links") if isinstance(page.get("links"), dict) else {}
    for value in (page.get("nextLink"), page.get("@odata.nextLink"), links.get("next")):
        if isinstance(value, str) and value:
            return value
    return None


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
        return "PPM Express refused: the token's scopes or your PPM Express permissions don't allow this."
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

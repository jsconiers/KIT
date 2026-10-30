"""Settings for the PPM Express MCP server, from environment variables (a container's ConfigMap, or
Kit's config through kit-ppmx). Nothing here holds a token.
"""
import datetime
import ipaddress
import os
import urllib.parse

DEFAULTS = {
    "PPMX_BASE_URL": "",            # https://<host>/@<tenant>/v1.0, shown in PPM Express > Automation
    "PPMX_TIMEOUT": "20",           # seconds for each request to PPM Express
    "PPMX_CACHE_SECONDS": "60",     # how long one caller's answers are reused; 0 turns caching off
    "PPMX_RATE_PER_MINUTE": "90",   # requests per caller per minute (Microsoft's connector stops at 100)
    "PPMX_PAGE_SIZE": "25",         # rows a list returns unless the caller asks for more
    "PPMX_MAX_ROWS": "200",         # the most rows one call returns
    "PPMX_ALLOW_HTTP": "",          # "1" allows a plain-HTTP base URL (tests); loopback addresses always may
    "PPMX_ALLOWED_ORIGINS": "",     # browser origins the HTTP server accepts; a request from any other is refused
    "PPMX_MAX_BODY": "1048576",     # the largest request body the HTTP server reads, in bytes
    "PPMX_CODES_FILE": "",          # optional JSON file of code tables (see codes.py)
    "PPMX_AUDIT": "on",             # the HTTP server's audit lines on standard error ("off" stops them)
    "PPMX_TODAY": "",               # tests only: the date to treat as today (YYYY-MM-DD)
}


class Settings:
    def __init__(self, env=None):
        env = os.environ if env is None else env

        def get(key):
            value = (env.get(key) or "").strip()
            return value if value else DEFAULTS[key]

        self.timeout = _number(get("PPMX_TIMEOUT"), 20, 1, 120)
        self.cache_seconds = _number(get("PPMX_CACHE_SECONDS"), 60, 0, 3600)
        self.rate_per_minute = int(_number(get("PPMX_RATE_PER_MINUTE"), 90, 1, 6000))
        self.page_size = int(_number(get("PPMX_PAGE_SIZE"), 25, 1, 1000))
        self.max_rows = int(_number(get("PPMX_MAX_ROWS"), 200, 1, 5000))
        self.allow_http = get("PPMX_ALLOW_HTTP").lower() in ("1", "true", "yes", "on")
        self.allowed_origins = {o.strip().rstrip("/") for o in get("PPMX_ALLOWED_ORIGINS").split(",")
                                if o.strip()}
        self.max_body = int(_number(get("PPMX_MAX_BODY"), 1048576, 1024, 16 * 1048576))
        self.codes_file = get("PPMX_CODES_FILE")
        self.audit = get("PPMX_AUDIT").lower() not in ("off", "0", "false", "no")
        try:
            self.today = datetime.date.fromisoformat(get("PPMX_TODAY")) if get("PPMX_TODAY") else None
        except ValueError:
            self.today = None
        self.base_url, self.problem = check_base_url(get("PPMX_BASE_URL"), self.allow_http)

    @property
    def ready(self):
        return bool(self.base_url) and not self.problem


def _number(text, default, low, high):
    try:
        n = float(text)
    except (TypeError, ValueError):
        return default
    return min(max(n, low), high)


def check_base_url(url, allow_http=False):
    """(clean URL, problem); the problem is None when the URL is usable."""
    if not url:
        return "", "PPMX_BASE_URL isn't set (your tenant's API address, from PPM Express > Automation)"
    try:
        p = urllib.parse.urlsplit(url)
        host = p.hostname or ""
    except ValueError:
        return "", "PPMX_BASE_URL isn't a valid address"
    if p.username or p.password:
        return "", "PPMX_BASE_URL must not contain a user name or password"
    if p.query or p.fragment:
        return "", "PPMX_BASE_URL must not have a query or a fragment"
    if not host:
        return "", "PPMX_BASE_URL has no host"
    if p.scheme == "http":
        if not (allow_http or _loopback(host)):
            return "", "PPMX_BASE_URL must use https (http only for a local test server)"
    elif p.scheme != "https":
        return "", "PPMX_BASE_URL must start with https://"
    return url.rstrip("/"), None


def _loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False

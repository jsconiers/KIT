"""kit_settings_ui: the local editing page behind `kit-settings ui`.

A small HTTP server (Python's http.server, standard library only) that runs only while you use it:

  - it listens on 127.0.0.1 only, on a free port the system picks
  - a random token, made fresh for each run, is in the URL it opens; the first page load trades it for a cookie
    (HttpOnly, SameSite=Strict) and the token in the URL stops working; an X-Kit-Token header works too
  - every request without the cookie or header gets 403, and so does any whose Host isn't 127.0.0.1:<port> or
    localhost:<port> (DNS rebinding)
  - a POST must also come from the page itself (Origin, else Referer, is http://127.0.0.1:<port>), carry the page's
    CSRF token in X-CSRF-Token, and be JSON
  - it changes only settings on kit_settings' allowlist, each checked by type, previewed as a diff first
  - it stops after IDLE seconds with no request (15 minutes by default) or when you press Stop
  - every change is logged to stderr and .install/logs/settings-ui.log (field, old and new value; credential-shaped
    values masked)

It handles one request at a time, so two edits can't interleave.
"""
import hmac
import html
import http.server
import json
import secrets
import sys
import time
import urllib.parse

import kit_settings as ks

e = html.escape
MAX_BODY = 64 * 1024


class State:
    def __init__(self, kit, idle):
        self.kit = ks.kit_dir(kit)
        self.idle = idle
        self.token = secrets.token_urlsafe(32)        # in the URL, once
        self.session = secrets.token_urlsafe(32)      # in the cookie
        self.csrf = secrets.token_urlsafe(32)         # in the page, sent back on every POST
        self.token_used = False
        self.last = time.monotonic()
        self.stop = False
        self.port = None
        self.platform = None                          # tests set this; None means this computer's

    @property
    def cookie_name(self):
        return f"kit_settings_{self.port}"

    def origins(self):
        return {f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}"}

    def hosts(self):
        return {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    def url(self):
        return f"http://127.0.0.1:{self.port}/?token={self.token}"


PAGE_JS = """
(function(){var csrf=document.querySelector('meta[name=kit-csrf]').content;
function post(path,body){return fetch(path,{method:'POST',credentials:'same-origin',
headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body||{})})
.then(function(r){return r.json().then(function(j){j.status=r.status;return j;});});}
function msg(box,text,bad){var p=document.createElement('div');p.className='kmsg'+(bad?' bad':'');p.textContent=text;box.appendChild(p);}
document.addEventListener('click',function(ev){var b=ev.target.closest('button[data-act]');if(!b)return;
var act=b.getAttribute('data-act');
if(act==='stop'){post('/api/stop').then(function(){document.body.innerHTML='<p>Stopped. You can close this tab.</p>';});return;}
var ed=b.closest('td').querySelector('.kedit'),box=b.closest('td').querySelector('.kpreview');
var body={id:ed.getAttribute('data-id'),value:ed.querySelector('.kin').value,expect:ed.getAttribute('data-expect')};
if(act==='preview'){box.textContent='';post('/api/preview',body).then(function(j){
if(!j.ok){msg(box,j.error||'Refused',true);return;}
var pre=document.createElement('pre');pre.className='kdiff';pre.textContent=j.diff;box.appendChild(pre);
msg(box,'Writes '+j.source+', backs it up first, and commits it where the file is in Kit\\'s history.');
var c=document.createElement('button');c.type='button';c.textContent='Confirm and save';c.setAttribute('data-act','apply');
box.appendChild(c);var x=document.createElement('button');x.type='button';x.textContent='Cancel';
x.addEventListener('click',function(){box.textContent='';});box.appendChild(x);});}
if(act==='apply'){post('/api/apply',body).then(function(j){box.textContent='';
if(!j.ok){msg(box,j.error||'Refused',true);return;}msg(box,j.message);
setTimeout(function(){location.reload();},1800);});}
});})();
"""


def page(state):
    items = ks.collect(state.kit)
    c = ks.counts(items)
    nonce = secrets.token_urlsafe(16)
    body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="kit-csrf" content="{e(state.csrf)}"><title>Kit settings</title>'
            f'<style nonce="{nonce}">body{{font:15px/1.45 system-ui,"Segoe UI",Arial,sans-serif;margin:1.2rem 2rem;'
            f'color:#15202B}}header{{display:flex;gap:1rem;align-items:baseline;flex-wrap:wrap}}'
            f'h1{{margin:0;font-size:1.6rem}}.note{{color:#566573}}{ks.CSS}</style></head><body>'
            f'<header><h1>Kit settings</h1><span class="note">{len(items)} settings, {c["not set"]} not set. '
            f'Only this computer can reach this page; it stops after {_span(state.idle)} idle.</span>'
            f'<button type="button" data-act="stop">Stop</button></header>'
            f'<p class="note">Edit a setting, press Preview to see the change, then Confirm. Read-only settings say how '
            f'to change them. Credentials show by name only.</p>'
            f'<div class="kset" id="kset">{ks.render_table(items, editing=True)}</div>'
            f'<script nonce="{nonce}">{ks.FILTER_JS}{PAGE_JS}</script></body></html>')
    return body, nonce


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "KitSettings"
    sys_version = ""
    timeout = 15                                   # a stalled client can't hold the one thread for long
    protocol_version = "HTTP/1.0"

    @property
    def st(self):
        return self.server.state

    def log_message(self, fmt, *args):             # never log the query string (it holds the token)
        pass

    # --- responses ------------------------------------------------------------------------------------------
    def _send(self, code, body, ctype="application/json; charset=utf-8", nonce=None, headers=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        csp = "default-src 'none'; connect-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'"
        if nonce:
            csp += f"; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'"
        self.send_header("Content-Security-Policy", csp)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj))

    def _deny(self, why="forbidden"):
        self._send(403, json.dumps({"ok": False, "error": why}))

    # --- checks ---------------------------------------------------------------------------------------------
    def _host_ok(self):
        return (self.headers.get("Host") or "").strip().lower() in self.st.hosts()

    def _cookie(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == self.st.cookie_name:
                return v
        return ""

    def _authed(self):
        tok = self.headers.get("X-Kit-Token") or ""
        if tok and hmac.compare_digest(tok, self.st.token):
            return True
        c = self._cookie()
        return bool(c) and hmac.compare_digest(c, self.st.session)

    def _same_origin(self):
        origin = self.headers.get("Origin")
        if origin:
            return origin in self.st.origins()
        ref = self.headers.get("Referer") or ""
        return any(ref == o or ref.startswith(o + "/") for o in self.st.origins())

    # --- methods --------------------------------------------------------------------------------------------
    def do_GET(self):
        if not self._host_ok():
            return self._deny("bad Host")
        url = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(url.query)
        tok = (q.get("token") or [""])[0]
        if tok:
            if self.st.token_used or not hmac.compare_digest(tok, self.st.token):
                return self._deny("this link has been used or isn't valid; run kit-settings ui again")
            self.st.token_used = True
            self.st.last = time.monotonic()
            cookie = f"{self.st.cookie_name}={self.st.session}; HttpOnly; SameSite=Strict; Path=/"
            return self._send(303, "", "text/plain", headers={"Location": "/", "Set-Cookie": cookie})
        if not self._authed():
            return self._deny("no session: open the link kit-settings ui printed")
        self.st.last = time.monotonic()
        if url.path == "/":
            body, nonce = page(self.st)
            return self._send(200, body, "text/html; charset=utf-8", nonce=nonce)
        if url.path == "/api/settings":
            return self._json(200, {"ok": True, "settings": [ks.public(s) for s in ks.collect(self.st.kit)]})
        return self._json(404, {"ok": False, "error": "not found"})

    do_HEAD = do_GET

    def do_POST(self):
        if not self._host_ok():
            return self._deny("bad Host")
        if not self._authed():
            return self._deny("no session")
        if not self._same_origin():
            return self._deny("bad Origin or Referer")
        csrf = self.headers.get("X-CSRF-Token") or ""
        if not (csrf and hmac.compare_digest(csrf, self.st.csrf)):
            return self._deny("missing or wrong CSRF token")
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._json(415, {"ok": False, "error": "send JSON"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0 or n > MAX_BODY:
            return self._json(413, {"ok": False, "error": "too large"})
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            if not isinstance(body, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"ok": False, "error": "not valid JSON"})
        self.st.last = time.monotonic()
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/stop":
            self.st.stop = True
            print("kit-settings ui: stopped from the page", file=sys.stderr)
            return self._json(200, {"ok": True})
        if path not in ("/api/preview", "/api/apply"):
            return self._json(404, {"ok": False, "error": "not found"})
        sid, value, expect = body.get("id"), body.get("value"), body.get("expect")
        if not isinstance(sid, str) or not isinstance(value, str) or (expect is not None and not isinstance(expect, str)):
            return self._json(400, {"ok": False, "error": "id and value must be text"})
        try:
            if path == "/api/preview":
                s, p, _, _, v, diff = ks.plan_edit(self.st.kit, sid, value, expect, self.st.platform)
                return self._json(200, {"ok": True, "diff": diff, "source": s["source"], "value": v})
            res = ks.apply_edit(self.st.kit, sid, value, expect, self.st.platform,
                                rebuild=getattr(self.server, "rebuild", True))
            return self._json(200, res)
        except ks.Refused as ex:
            return self._json(403, {"ok": False, "error": str(ex)})
        except ks.Invalid as ex:
            return self._json(400, {"ok": False, "error": str(ex)})
        except OSError as ex:
            return self._json(500, {"ok": False, "error": f"couldn't write: {ex}"})

    def _method_not_allowed(self):
        self._json(405, {"ok": False, "error": "method not allowed"})

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _method_not_allowed


class Server(http.server.HTTPServer):
    allow_reuse_address = False

    def handle_error(self, request, client_address):   # keep tracebacks (and any header) out of the terminal
        print("kit-settings ui: a request failed", file=sys.stderr)


def make_server(kit=None, idle=900, port=0):
    st = State(kit, idle)
    srv = Server(("127.0.0.1", port), Handler)
    st.port = srv.server_address[1]
    srv.state = st
    srv.timeout = 0.5
    return srv, st


def _span(secs):
    if secs < 60:
        return f"{int(secs)} second{'s' if int(secs) != 1 else ''}"
    m = round(secs / 60)
    return f"{m} minute{'s' if m != 1 else ''}"


def serve(srv, st):
    """Handle requests until Stop, the idle timeout, or Ctrl-C. Returns why it stopped."""
    why = "stopped"
    try:
        while not st.stop:
            srv.handle_request()
            if time.monotonic() - st.last > st.idle:
                why = f"idle for {_span(st.idle)}"
                break
    except KeyboardInterrupt:
        why = "interrupted"
    finally:
        srv.server_close()
    print(f"kit-settings ui: closed ({why})", file=sys.stderr)
    return why


def main(kit=None, idle=900, open_browser=True):
    srv, st = make_server(kit, idle)
    print(f"Kit settings: {st.url()}", flush=True)
    print(f"Only this computer can reach it; the link works once. It stops after {_span(idle)} idle, when you "
          "press Stop, or with Ctrl-C.", flush=True)
    if open_browser:
        import webbrowser
        try:
            webbrowser.open(st.url())
        except Exception:  # noqa: BLE001
            print("Couldn't open a browser; open the link above.")
    serve(srv, st)
    return 0

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

The Review loop section runs kit-review-loop from the page, in one click: pick a project in the library and a
draft, press Start, then confirm the paid runs (the page shows how many and about what they'll cost). It starts
`kit-review-loop run PROJECT DRAFT --yes` in the background (one at a time; its output goes to
.install/logs/review-loop-ui-<time>.log, and it keeps going if the page stops), shows its progress, and links
each note it saved. Merge writes the decisions file. Each project shows its "ready for ARB" score
(kit-review-loop score) and links its latest notes, decisions, and feedback, which open read-only here: only
Markdown files inside that project's folder in the library, nothing else.
"""
import hmac
import html
import http.server
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import re
import secrets
import subprocess
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
        self.job = None                               # the review loop run started from this page (Popen)
        self.job_info = {}
        self._review = None

    @property
    def cookie_name(self):
        return f"kit_settings_{self.port}"

    def origins(self):
        return {f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}"}

    def hosts(self):
        return {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    def url(self):
        return f"http://127.0.0.1:{self.port}/?token={self.token}"

    def review(self):
        """kit-review-loop, loaded once, pointed at this Kit folder."""
        if self._review is None:
            os.environ["KIT_DIR"] = str(self.kit)
            path = REVIEW_TOOL
            loader = importlib.machinery.SourceFileLoader("kit_review_loop_ui", str(path))
            spec = importlib.util.spec_from_loader("kit_review_loop_ui", loader)
            mod = importlib.util.module_from_spec(spec)
            loader.exec_module(mod)
            self._review = mod
        return self._review


REVIEW_TOOL = pathlib.Path(__file__).resolve().parent / "bin" / "kit-review-loop"
DRAFT_EXT = {".md", ".docx", ".txt"}
NOTE_MAX = 2 * 1024 * 1024


def review_projects(st):
    """{name: folder} for each project folder in the library that has drafts/ or reviews/."""
    try:
        rv = st.review()
        root = rv.kd.library_root()
    except Exception:  # noqa: BLE001
        return {}
    base = root / "artifacts" if root else None
    if not base or not base.is_dir():
        return {}
    return {p.name: p for p in sorted(base.iterdir(), key=lambda x: x.name.lower())
            if p.is_dir() and ((p / "drafts").is_dir() or (p / "reviews").is_dir())}


def review_drafts(proj):
    d = proj / "drafts"
    files = [f for f in d.iterdir() if f.is_file() and f.suffix.lower() in DRAFT_EXT] if d.is_dir() else []
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


def job_state(st):
    """The current or last review run: {running, project, draft, log, tail, rc}."""
    info = dict(st.job_info)
    if not info:
        return {"running": False}
    rc = st.job.poll() if st.job else info.get("rc")
    info["running"] = st.job is not None and rc is None
    info["rc"] = rc
    try:
        lines = pathlib.Path(info["log"]).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    info["tail"] = "\n".join(lines[-30:])
    info["saved"] = [ln.split("saved ", 1)[1].strip() for ln in lines if ln.strip().startswith("saved ")]
    return info


def note_link(st, proj, path):
    try:
        rel = pathlib.Path(path).resolve().relative_to(proj.resolve()).as_posix()
    except ValueError:
        return ""
    return "/note?" + urllib.parse.urlencode({"p": proj.name, "f": rel})


def review_section(st):
    projects = review_projects(st)
    if not projects:
        return ('<section class="krev" aria-labelledby="krev-h"><h2 id="krev-h">Review loop</h2><p class="note">No '
                'project in the library has a drafts/ or reviews/ folder yet (or the library root isn\'t set in '
                'library.md).</p></section>')
    rv = st.review()
    try:
        each, how = rv.per_run_cost()
    except Exception:  # noqa: BLE001
        each, how = rv.ASSUMED_RUN_USD, "assumed"
    job = job_state(st)
    status = ""
    if job.get("project"):
        state = ("running" if job["running"] else "finished" if job.get("rc") == 0 else
                 "stopped: Kit's budget is used up" if job.get("rc") == 75 else f"failed (exit {job.get('rc')})")
        status = (f'<div class="kjob" id="kjob"><p><strong>{e(job["project"])}</strong>, {e(job["draft"])}: '
                  f'<span id="kjob-state">{e(state)}</span> <button type="button" data-act="rv-status">Refresh</button>'
                  f'</p><pre class="kdiff" id="kjob-tail">{e(job["tail"])}</pre></div>')
    rows = ""
    for name, proj in projects.items():
        try:
            sc = rv.readiness(proj)
            head = sc["headline"] if sc["notes"] else "No review notes yet"
            cls = {"ready": "ok", "almost": "warn"}.get(sc["verdict"], "bad") if sc["notes"] else ""
            links = [(src, path) for src, path in sc["notes"].items()]
            if sc["decisions"]:
                links.append(("decisions", sc["decisions"]))
        except Exception as ex:  # noqa: BLE001
            head, cls, links = f"couldn't read the notes: {ex}", "bad", []
        fb = sorted(proj.glob("feedback-v*.md"), key=lambda f: f.stat().st_mtime)
        if fb:
            links.append((fb[-1].stem, str(fb[-1])))
        alink = " ".join(f'<a href="{e(note_link(st, proj, path))}" target="_blank" rel="noopener">{e(lbl)}</a>'
                         for lbl, path in links if note_link(st, proj, path))
        drafts = review_drafts(proj)
        opts = "".join(f'<option value="{e(d.name)}">{e(d.name)}</option>' for d in drafts)
        start = (f'<select class="kdraft" aria-label="Draft for {e(name)}">{opts}</select> '
                 f'<select class="konly" aria-label="Which reviews"><option value="">all four reviews</option>'
                 f'<option value="reviewer">reviewer only</option></select> '
                 f'<button type="button" data-act="rv-start">Start</button>') if drafts else \
            '<span class="note">no draft in drafts/</span>'
        rows += (f'<tr data-project="{e(name)}"><th scope="row">{e(name)}</th>'
                 f'<td><span class="kscore {cls}">{e(head)}</span><div class="klinks">{alink}</div></td>'
                 f'<td>{start} <button type="button" data-act="rv-merge">Merge</button><div class="kpreview"></div></td></tr>')
    return (f'<section class="krev" aria-labelledby="krev-h"><h2 id="krev-h">Review loop</h2>'
            f'<p class="note">One click runs the reviewer, then the red team, threat modeler, and standards checker, '
            f'as unattended Claude Code runs (about ${each:.2f} each; {e(how)}). Each asks you to confirm first. '
            f'Merge then writes the ranked decisions file. Notes open read-only.</p>{status}'
            f'<table class="kreview"><thead><tr><th scope="col">Project</th><th scope="col">Ready for ARB</th>'
            f'<th scope="col">Run</th></tr></thead><tbody>{rows}</tbody></table></section>')


def start_review(st, project, draft, only):
    """Start kit-review-loop run in the background; (ok, message)."""
    cur = job_state(st)
    if cur.get("running"):
        return False, f"a review of {cur['project']} is still running"
    projects = review_projects(st)
    if project not in projects:
        return False, "no such project in the library"
    proj = projects[project]
    names = {d.name: d for d in review_drafts(proj)}
    if draft not in names:
        return False, "no such draft in that project's drafts/ folder"
    if only not in ("", "reviewer"):
        return False, "only can be empty or reviewer"
    logs = pathlib.Path(st.kit) / ".install/logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"review-loop-ui-{time.strftime('%Y-%m-%d-%H%M%S')}.log"
    argv = [sys.executable, str(REVIEW_TOOL), "run", str(proj), str(names[draft]), "--yes"]
    if only:
        argv += ["--only", only]
    env = dict(os.environ, KIT_DIR=str(st.kit), PYTHONUNBUFFERED="1")
    kw = {"start_new_session": True} if os.name != "nt" else \
        {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    with open(log, "w", encoding="utf-8") as fh:
        st.job = subprocess.Popen(argv, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  cwd=str(st.kit), env=env, **kw)
    st.job_info = {"project": project, "draft": draft, "only": only, "log": str(log),
                   "started": time.strftime("%H:%M")}
    print(f"kit-settings ui: started the review loop for {project} ({draft}); log {log}", file=sys.stderr)
    return True, f"Started: {'the reviewer' if only else 'four reviews'} on {draft}. This takes a while; Refresh shows progress."


def merge_review(st, project):
    projects = review_projects(st)
    if project not in projects:
        return False, "no such project in the library", ""
    r = subprocess.run([sys.executable, str(REVIEW_TOOL), "merge", str(projects[project])], capture_output=True,
                       text=True, timeout=120, cwd=str(st.kit), env=dict(os.environ, KIT_DIR=str(st.kit)))
    out = (r.stdout + r.stderr).strip()
    m = re.search(r"wrote (.+?review-decisions-[0-9-]+\.md)", out)
    link = note_link(st, projects[project], m.group(1)) if m else ""
    return r.returncode == 0, out, link


PAGE_JS = """
(function(){var csrf=document.querySelector('meta[name=kit-csrf]').content;
function post(path,body){return fetch(path,{method:'POST',credentials:'same-origin',
headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body||{})})
.then(function(r){return r.json().then(function(j){j.status=r.status;return j;});});}
function msg(box,text,bad){var p=document.createElement('div');p.className='kmsg'+(bad?' bad':'');p.textContent=text;box.appendChild(p);}
document.addEventListener('click',function(ev){var b=ev.target.closest('button[data-act]');if(!b)return;
var act=b.getAttribute('data-act');
if(act.indexOf('rv-')===0){review(b,act);return;}
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

REVIEW_CSS = (".krev{margin-top:2rem}.krev h2{font-size:1.3rem}.kreview{border-collapse:collapse;width:100%}"
              ".kreview th,.kreview td{text-align:left;vertical-align:top;padding:.4rem .5rem;border-top:1px solid #C9D0D6}"
              ".kscore{font-weight:600}.kscore.ok{color:#2E7D4F}.kscore.warn{color:#B7791F}.kscore.bad{color:#C1121F}"
              ".klinks a{margin-right:.6rem}.kjob{background:#EEF2F5;padding:.5rem .8rem;margin:.6rem 0}")

REVIEW_JS = """
function review(b,act){var csrf=document.querySelector('meta[name=kit-csrf]').content;
function post(path,body){return fetch(path,{method:'POST',credentials:'same-origin',
headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body||{})})
.then(function(r){return r.json();});}
if(act==='rv-status'){post('/api/review/status').then(function(j){
document.getElementById('kjob-state').textContent=j.state||'';document.getElementById('kjob-tail').textContent=j.tail||'';});return;}
var tr=b.closest('tr'),box=tr.querySelector('.kpreview'),proj=tr.getAttribute('data-project');
function say(t,bad){var p=document.createElement('div');p.className='kmsg'+(bad?' bad':'');p.textContent=t;box.textContent='';box.appendChild(p);return p;}
if(act==='rv-merge'){post('/api/review/merge',{project:proj}).then(function(j){var p=say(j.message||j.error,!j.ok);
if(j.link){var a=document.createElement('a');a.href=j.link;a.target='_blank';a.textContent=' Open it';p.appendChild(a);}});return;}
var draft=tr.querySelector('.kdraft').value,only=tr.querySelector('.konly').value;
if(act==='rv-start'){post('/api/review/plan',{project:proj,draft:draft,only:only}).then(function(j){
if(!j.ok){say(j.error,true);return;}var p=say(j.message);var c=document.createElement('button');c.type='button';
c.textContent='Confirm and start';c.setAttribute('data-act','rv-go');p.appendChild(document.createTextNode(' '));p.appendChild(c);});return;}
if(act==='rv-go'){post('/api/review/start',{project:proj,draft:draft,only:only}).then(function(j){say(j.message||j.error,!j.ok);
if(j.ok){setTimeout(function(){location.reload();},1500);}});}}
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
            f'h1{{margin:0;font-size:1.6rem}}.note{{color:#566573}}{ks.CSS}{REVIEW_CSS}</style></head><body>'
            f'<header><h1>Kit settings</h1><span class="note">{len(items)} settings, {c["not set"]} not set. '
            f'Only this computer can reach this page; it stops after {_span(state.idle)} idle.</span>'
            f'<button type="button" data-act="stop">Stop</button></header>'
            f'<p class="note">Edit a setting, press Preview to see the change, then Confirm. Read-only settings say how '
            f'to change them. Credentials show by name only.</p>'
            f'<div class="kset" id="kset">{ks.render_table(items, editing=True)}</div>'
            f'{review_section(state)}'
            f'<script nonce="{nonce}">{ks.FILTER_JS}{REVIEW_JS}{PAGE_JS}</script></body></html>')
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
        if url.path == "/note":
            return self._note(q)
        return self._json(404, {"ok": False, "error": "not found"})

    def _note(self, q):
        """A review note, decisions, or feedback file, read-only: Markdown inside that project's folder only."""
        proj = review_projects(self.st).get((q.get("p") or [""])[0])
        rel = (q.get("f") or [""])[0]
        if not proj or not rel or rel.startswith(("/", "\\")) or ".." in pathlib.PurePosixPath(rel).parts:
            return self._json(404, {"ok": False, "error": "not found"})
        f = (proj / rel).resolve()
        try:
            f.relative_to(proj.resolve())
        except ValueError:
            return self._json(404, {"ok": False, "error": "not found"})
        if f.suffix.lower() != ".md" or not f.is_file() or f.is_symlink() or f.stat().st_size > NOTE_MAX:
            return self._json(404, {"ok": False, "error": "not found"})
        return self._send(200, f.read_text(encoding="utf-8", errors="replace"), "text/plain; charset=utf-8")

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
        if path.startswith("/api/review/"):
            return self._review_api(path, body)
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

    def _review_api(self, path, body):
        project, draft, only = body.get("project", ""), body.get("draft", ""), body.get("only", "")
        if not all(isinstance(x, str) for x in (project, draft, only)):
            return self._json(400, {"ok": False, "error": "project, draft, and only must be text"})
        try:
            if path == "/api/review/status":
                j = job_state(self.st)
                state = ("" if not j.get("project") else "running" if j["running"] else
                         "finished" if j.get("rc") == 0 else f"ended (exit {j.get('rc')})")
                return self._json(200, {"ok": True, "state": state, "tail": j.get("tail", ""), "saved": j.get("saved", [])})
            if path == "/api/review/plan":
                projects = review_projects(self.st)
                if project not in projects or draft not in {d.name for d in review_drafts(projects[project])}:
                    return self._json(400, {"ok": False, "error": "pick a project and a draft in its drafts/ folder"})
                n = 1 if only == "reviewer" else 4
                each, how = self.st.review().per_run_cost()
                return self._json(200, {"ok": True, "message": f"{n} paid Claude Code run(s) on {draft}, about "
                                                               f"${each * n:.2f} ({how}), each checked against Kit's budget."})
            if path == "/api/review/start":
                good, msg = start_review(self.st, project, draft, only)
                return self._json(200 if good else 409, {"ok": good, "message" if good else "error": msg})
            if path == "/api/review/merge":
                good, msg, link = merge_review(self.st, project)
                return self._json(200 if good else 409, {"ok": good, "message" if good else "error": msg, "link": link})
        except (OSError, subprocess.SubprocessError) as ex:
            return self._json(500, {"ok": False, "error": f"couldn't run kit-review-loop: {ex}"})
        return self._json(404, {"ok": False, "error": "not found"})

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

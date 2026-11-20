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

The page itself (kit_settings_page) groups the settings by kit_settings.GROUPS with a section list, search, and
filters. Edits are held on the page and checked as you type (/api/preview), then saved together: /api/batch/preview
shows every change's diff, and /api/batch/apply, after re-checking all of them (any refusal saves nothing), takes a
configuration snapshot (kit_config) and writes each one through kit_settings.apply_edit. A single /api/apply (the
wizard's) takes a snapshot first too. The Snapshots section lists kit-config snapshots: compare one with now, take
one, or restore one (/api/snapshots/restore-preview first, then /api/snapshots/restore with confirm; never Kit's
permission rules, which only kit-config restore --include-permissions puts back). Every POST goes through the same
session, Origin, CSRF, JSON, and size checks.

The Review loop section runs kit-review-loop from the page, in one click: pick a project in the library and a
draft, press Start, then confirm the paid runs (the page shows how many and about what they'll cost). It starts
`kit-review-loop run PROJECT DRAFT --yes` in the background (one at a time; its output goes to
.install/logs/review-loop-ui-<time>.log, and it keeps going if the page stops), shows its progress, and links
each note it saved. Merge writes the decisions file. Each project shows its "ready for ARB" score
(kit-review-loop score) and links its latest notes, decisions, and feedback, which open read-only here: only
Markdown files inside that project's folder in the library, nothing else.

The Setup section is the first-run wizard: it walks the setup fields still "not set" one at a time (kit_setupq
orders them, the ones that hold agents back most first), with the agents that read each one, a hint, and an example.
Answer previews the change and saves it the same way as any other setting here; Skip moves the question to the end,
Later puts it aside until "Bring back"; Done for now closes the wizard. On a new install (no
.install/setup-wizard.json yet) it is open, at the top of the page.
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

import kit_config as kcfg
import kit_settings as ks
import kit_settings_page as kp
import kit_setupq as sq

e = html.escape
MAX_BODY = 64 * 1024
MAX_BATCH = 50


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


SETUP_JS = """
function setupq(b,act){var csrf=document.querySelector('meta[name=kit-csrf]').content;
function post(path,body){return fetch(path,{method:'POST',credentials:'same-origin',
headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body||{})})
.then(function(r){return r.json();});}
var card=document.getElementById('kwiz-card'),box=document.getElementById('kwiz-box');
function say(t,bad){var p=document.createElement('div');p.className='kmsg'+(bad?' bad':'');p.textContent=t;box.appendChild(p);return p;}
function again(){location.hash='kwiz';location.reload();}
var id=card?card.getAttribute('data-id'):'';
if(act==='sq-preview'){box.textContent='';var v=card.querySelector('.kin').value;
post('/api/preview',{id:id,value:v,expect:card.getAttribute('data-expect')}).then(function(j){
if(!j.ok){say(j.error||'Refused',true);return;}var pre=document.createElement('pre');pre.className='kdiff';
pre.textContent=j.diff;box.appendChild(pre);say('Writes '+j.source+', backs it up first, and commits it where the file is in Kit\\'s history.');
var c=document.createElement('button');c.type='button';c.textContent='Confirm and save';c.setAttribute('data-act','sq-apply');box.appendChild(c);});return;}
if(act==='sq-apply'){var v2=card.querySelector('.kin').value;post('/api/apply',{id:id,value:v2,expect:card.getAttribute('data-expect')})
.then(function(j){box.textContent='';if(!j.ok){say(j.error||'Refused',true);return;}say(j.message);
post('/api/setup/mark',{id:id,how:'answered'}).then(function(){setTimeout(again,1200);});});return;}
var how={'sq-skip':'skip','sq-later':'later','sq-done':'done','sq-reset':'reset','sq-open':'open'}[act];
if(how){post('/api/setup/mark',{id:id,how:how}).then(function(j){if(!j.ok){say(j.error||'Refused',true);return;}again();});}}
"""


def setup_section(st, items):
    """The first-run wizard: one open setup question at a time."""
    todo, qs, state = sq.walk(st.kit, items)
    c = sq.counts(qs)
    total = len([s for s in items if s["kind"] == "setup"])
    done_pct = round(100 * (total - c["not set"]) / total) if total else 100
    is_open = sq.first_run(st.kit) or not state.get("closed")
    later = len([q for q in qs if q["id"] in set(state["later"])])
    head = (f'<summary>Setup: <span id="kwiz-left">{c["not set"]}</span> not set'
            f'{" (" + str(c["high"]) + " high priority)" if c["high"] else ""}</summary>')
    bar = (f'<progress class="kbar" max="100" value="{done_pct}" aria-label="Setup fields set">{done_pct}%</progress>'
           f'<p class="note">{total - c["not set"]} of {total} setup fields set. '
           f'{int(state.get("answered", 0))} answered here so far.'
           f'{" " + str(later) + " saved for later." if later else ""}'
           f'{" " + str(c["in a session"]) + " can only be changed in a Claude Code session." if c["in a session"] else ""}'
           f'</p>')
    if not todo:
        body = ('<p>Nothing left to walk through here.' +
                (' <button type="button" data-act="sq-reset">Bring back the ones saved for later</button>' if later else '')
                + '</p>')
    else:
        q = todo[0]
        who = ", ".join(q["agents"]) or "no agent names this file yet"
        prio = f'<span class="kprio">High priority</span> ({e(q["why"])}). ' if q["priority"] == "high" else ""
        hint = f'<p class="note">{e(q["hint"])}</p>' if q["hint"] else ""
        ex = f'<p class="note">For example: <code>{e(q["example"])}</code></p>' if q["example"] else ""
        body = (f'<div id="kwiz-card" data-id="{e(q["id"])}" data-expect="{e(q["expect"])}">'
                f'<p class="note">Question 1 of {len(todo)} &middot; {prio}{e(q["source"])}, line {q["line"]}'
                f'{" (" + e(q["section"]) + ")" if q["section"] else ""} &middot; read by {e(who)}</p>'
                f'<p class="kq"><label for="kwiz-in">{e(q["question"])}</label></p>{hint}{ex}'
                f'<input id="kwiz-in" class="kin" type="text" autocomplete="off" maxlength="2000">'
                f'<div><button type="button" data-act="sq-preview">Preview</button>'
                f'<button type="button" data-act="sq-skip">Skip</button>'
                f'<button type="button" data-act="sq-later">Later</button>'
                f'<button type="button" data-act="sq-done">Done for now</button>'
                + (' <button type="button" data-act="sq-reset">Bring back later ones</button>' if later else '')
                + '</div><div id="kwiz-box" aria-live="polite"></div></div>')
    return (f'<details class="kwiz" id="kwiz"{" open" if is_open else ""}>{head}{bar}{body}</details>')


def take_snapshot(state, note):
    """(snapshot id or None, warning or ""): a configuration snapshot before a save. A failed snapshot doesn't
    stop the save (the file's own backup is still taken); the message says so."""
    try:
        return kcfg.snapshot(state.kit, note=note)["id"], ""
    except (OSError, ValueError, kcfg.Error) as ex:
        print(f"kit-settings ui: snapshot failed: {ex}", file=sys.stderr)
        return None, f"(No configuration snapshot was taken: {ex}. The file's own backup was.)"


def page(state):
    items = ks.collect(state.kit)
    wizard = setup_section(state, items)
    nonce = secrets.token_urlsafe(16)
    try:
        snaps = kcfg.listing(state.kit)
    except (OSError, ValueError, kcfg.Error):
        snaps = []
    body = kp.render(items, wizard, review_section(state), snaps, state.csrf, nonce, _span(state.idle),
                     extra_js=REVIEW_JS + SETUP_JS)
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
        if path == "/api/setup/mark":
            return self._setup_mark(body)
        if path.startswith("/api/batch/"):
            return self._batch(path, body)
        if path.startswith("/api/snapshots/"):
            return self._snapshots(path, body)
        if path not in ("/api/preview", "/api/apply"):
            return self._json(404, {"ok": False, "error": "not found"})
        sid, value, expect = body.get("id"), body.get("value"), body.get("expect")
        if not isinstance(sid, str) or not isinstance(value, str) or (expect is not None and not isinstance(expect, str)):
            return self._json(400, {"ok": False, "error": "id and value must be text"})
        try:
            if path == "/api/preview":
                s, p, _, _, v, diff = ks.plan_edit(self.st.kit, sid, value, expect, self.st.platform)
                return self._json(200, {"ok": True, "diff": diff, "source": s["source"], "value": v})
            ks.plan_edit(self.st.kit, sid, value, expect, self.st.platform)     # refuse before taking a snapshot
            snap, warn = take_snapshot(self.st, "before a save in the settings page")
            res = ks.apply_edit(self.st.kit, sid, value, expect, self.st.platform,
                                rebuild=getattr(self.server, "rebuild", True))
            res["snapshot"] = snap
            if warn:
                res["message"] += " " + warn
            return self._json(200, res)
        except ks.Refused as ex:
            return self._json(403, {"ok": False, "error": str(ex)})
        except ks.Invalid as ex:
            return self._json(400, {"ok": False, "error": str(ex)})
        except OSError as ex:
            return self._json(500, {"ok": False, "error": f"couldn't write: {ex}"})

    def _changes(self, body):
        """The batch's changes as [(id, value, expect)], or raise ValueError with why."""
        ch = body.get("changes")
        if not isinstance(ch, list) or not ch:
            raise ValueError("send at least one change")
        if len(ch) > MAX_BATCH:
            raise ValueError(f"at most {MAX_BATCH} changes at once")
        out, seen = [], set()
        for c in ch:
            if not isinstance(c, dict):
                raise ValueError("each change must be an object")
            sid, value, expect = c.get("id"), c.get("value"), c.get("expect")
            if not isinstance(sid, str) or not isinstance(value, str) or (expect is not None and not isinstance(expect, str)):
                raise ValueError("each change needs an id and a value as text")
            if sid in seen:
                raise ValueError("a setting is in the batch twice")
            seen.add(sid)
            out.append((sid, value, expect))
        return out

    def _plan_batch(self, changes):
        """[{id, label, source, ok, diff or error}] and whether all passed."""
        items = {s["id"]: s for s in ks.collect(self.st.kit)}
        out, good = [], True
        for sid, value, expect in changes:
            s = items.get(sid)
            label = (s["label"] if s else sid)
            try:
                s2, _, _, _, v, diff = ks.plan_edit(self.st.kit, sid, value, expect, self.st.platform)
                out.append({"id": sid, "label": label, "source": s2["source"], "ok": True, "diff": diff, "value": v})
            except (ks.Refused, ks.Invalid) as ex:
                good = False
                out.append({"id": sid, "label": label, "source": s["source"] if s else "", "ok": False, "error": str(ex)})
        return out, good

    def _batch(self, path, body):
        try:
            changes = self._changes(body)
        except ValueError as ex:
            return self._json(400, {"ok": False, "error": str(ex)})
        try:
            plan, good = self._plan_batch(changes)
        except OSError as ex:
            return self._json(500, {"ok": False, "error": f"couldn't read: {ex}"})
        files = sorted({p["source"] for p in plan if p["ok"]})
        if path == "/api/batch/preview":
            msg = (f"Saving writes {len(files)} file(s) ({', '.join(files)}), backs each up, takes a configuration "
                   "snapshot first, and commits where the file is in Kit's history." if good else
                   "Fix the changes marked above first; nothing has been saved.")
            return self._json(200, {"ok": good, "items": plan, "message": msg})
        if path != "/api/batch/apply":
            return self._json(404, {"ok": False, "error": "not found"})
        if not good:
            return self._json(400, {"ok": False, "error": "nothing was saved: some changes aren't allowed",
                                    "results": [{"label": p["label"], "ok": p["ok"], "error": p.get("error", "")}
                                                for p in plan if not p["ok"]]})
        snap, warn = take_snapshot(self.st, f"before saving {len(changes)} change(s) in the settings page")
        results, saved = [], 0
        labels = {p["id"]: p["label"] for p in plan}
        for sid, value, expect in changes:
            try:
                ks.apply_edit(self.st.kit, sid, value, expect, self.st.platform, rebuild=False)
                results.append({"label": labels.get(sid, sid), "ok": True})
                saved += 1
            except (ks.Refused, ks.Invalid, OSError) as ex:
                results.append({"label": labels.get(sid, sid), "ok": False, "error": str(ex)})
        if saved and getattr(self.server, "rebuild", True):
            ks.rebuild_dashboard(self.st.kit)
        undo = f" To undo: Snapshots, then restore {snap}." if snap else ""
        if saved == len(changes):
            return self._json(200, {"ok": True, "results": results, "snapshot": snap,
                                    "message": f"Saved {saved} change(s).{undo} {warn}".strip()})
        return self._json(409, {"ok": False, "results": results, "snapshot": snap,
                                "error": f"Saved {saved} of {len(changes)}; the rest were refused.{undo} {warn}".strip()})

    def _snapshots(self, path, body):
        sid = body.get("id", "")
        if not isinstance(sid, str):
            return self._json(400, {"ok": False, "error": "id must be text"})
        try:
            if path == "/api/snapshots/take":
                note = body.get("note", "")
                if not isinstance(note, str):
                    return self._json(400, {"ok": False, "error": "note must be text"})
                r = kcfg.snapshot(self.st.kit, note=note or "taken from the settings page")
                ks.log_edit(self.st.kit, {"source": kcfg.SNAP_REL, "name": "snapshot", "section": "", "secret": False},
                            "", r["id"], "taken" if r["new"] else "unchanged")
                return self._json(200, {"ok": True, "id": r["id"], "new": r["new"],
                                        "message": f"Snapshot {r['id']} taken." if r["new"] else
                                        f"Nothing changed since snapshot {r['id']}; kept that one."})
            kcfg.check_id(self.st.kit, sid)
            if path == "/api/snapshots/diff":
                return self._json(200, {"ok": True, "diff": kcfg.diff(self.st.kit, sid, "current")})
            if path == "/api/snapshots/restore-preview":
                plan = kcfg.plan_restore(self.st.kit, sid)
                n = len(plan["changes"])
                return self._json(200, {"ok": True, "diff": plan["diff"], "changes": n,
                                        "message": (f"{n} file(s) would change. A snapshot of the current state is "
                                                    "taken first, so this can be undone." if n else
                                                    "The configuration already matches this snapshot.")})
            if path == "/api/snapshots/restore":
                if body.get("confirm") is not True:
                    return self._json(400, {"ok": False, "error": "confirm the restore"})
                r = kcfg.restore(self.st.kit, sid)
                ks.log_edit(self.st.kit, {"source": kcfg.SNAP_REL, "name": "restore", "section": "", "secret": False},
                            r.get("before") or "", sid, ", ".join(r["written"]) or "nothing to restore")
                if r["written"] and getattr(self.server, "rebuild", True):
                    ks.rebuild_dashboard(self.st.kit)
                return self._json(200, r)
        except kcfg.Error as ex:
            return self._json(400, {"ok": False, "error": str(ex)})
        except (OSError, ValueError) as ex:
            return self._json(500, {"ok": False, "error": f"couldn't read or write the snapshot: {ex}"})
        return self._json(404, {"ok": False, "error": "not found"})

    def _setup_mark(self, body):
        qid, how = body.get("id", ""), body.get("how", "")
        if not isinstance(qid, str) or how not in ("skip", "later", "answered", "done", "reset", "open"):
            return self._json(400, {"ok": False, "error": "id must be text and how one of skip, later, answered, done, reset, open"})
        if how in ("skip", "later") and qid not in {q["id"] for q in sq.questions(self.st.kit)}:
            return self._json(400, {"ok": False, "error": "no such open setup question"})
        try:
            sq.mark(self.st.kit, qid if how in ("skip", "later") else "", how)
        except OSError as ex:
            return self._json(500, {"ok": False, "error": f"couldn't save the wizard's state: {ex}"})
        return self._json(200, {"ok": True, "left": len(sq.questions(self.st.kit))})

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

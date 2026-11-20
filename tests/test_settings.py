#!/usr/bin/env python3
"""Tests for the settings view and editor: kit_settings (collection, masking, personal notes left out, the
dashboard's Settings panel, kit-settings show --all) and kit_settings_ui (the local page: token, Host, Origin and
CSRF checks, read-only settings refused, validation, a one-line edit with every other byte kept, the backup, the
commit, and the idle and Stop shutdowns). Everything happens in a fake Kit folder under a temp HOME.

  python3 tests/test_settings.py
"""
import hashlib
import re
import http.client
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse

REPO = pathlib.Path(__file__).resolve().parent.parent
TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-settings-"))
HOME = TMP / "home"
KIT = HOME / "Claude/Agents/kit"
# Point everything at the fake folder before any Kit module is imported (some read HOME at import).
os.environ.update(HOME=str(HOME), USERPROFILE=str(HOME), KIT_DIR=str(KIT), PYTHONDONTWRITEBYTECODE="1")
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / "shared"))
import kit_settings as ks  # noqa: E402
import kit_settings_ui as ui  # noqa: E402

P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------------------------------------------
# The fake Kit folder.
CTX = KIT / "memory/context"
for d in (CTX, KIT / "memory/personal", KIT / ".install/shared/morning", KIT / ".install/logs", KIT / "agents"):
    d.mkdir(parents=True, exist_ok=True)
CONFIG = KIT / ".install/shared/morning/config"
CONFIG.write_bytes(b'# my run settings\nOWNER_NAME="Sam"\nDELIVERY="local"\nDELIVERY_EMAIL_TO="you@example.com"\n'
                   b'COST_WARN_PCT="80"\nALLOW_TOOLS="Bash(kitmail search *)"\nFAKE_API_TOKEN="zz-test-value-123"\n'
                   b'PPMX_TOKEN_ENV="PPMX_PAT"\nDUP_KEY="1"\nDUP_KEY="2"\n# trailing comment, no newline')
for name in ("library.md", "compliance.md", "connectors.md", "sharing.md", "meetings.md"):
    shutil.copy(REPO / "kit/memory/context" / name, CTX / name)
(CTX / "library.md").write_text((CTX / "library.md").read_text().replace(
    "- **Library root:** not set. Pick a folder for the library. For work documents, use storage your\n"
    "  employer manages, not Kit's own folder.", f"- **Library root:** `{TMP / 'library'}`"))
comp = (CTX / "compliance.md").read_text()
comp = comp.replace("- **Records:** optional.", "- **Records:** token: abcdefgh, optional.")
(CTX / "compliance.md").write_text(comp)
# oneonone.md: CRLF line ends, a wrapped field, and no newline at the end, to prove the rest is byte-exact.
ONE = CTX / "oneonone.md"
ONE.write_bytes(b"# One-to-one setup\r\n\r\n- **Manager role:** not set. For example \"engineering manager\" or\r\n"
                b"  \"head of architecture\".\r\n- **Cadence:** weekly\r\n- **Day:** not set.\r\n"
                b"- **Last 1:1:** not set. The date of the last one (DD-Mmm-YYYY).\r\n"
                b"- **Look back:** 14 days, when the last 1:1 isn't set.\r\n\r\nTrailing text \xe2\x80\x94 kept")
# A field holding a nested list stays read-only.
(CTX / "triage.md").write_text("# Triage\n\n- **Priority senders:** these:\n  - the CTO\n  - my manager\n"
                               "- **Delegated topics:** optional.\n")
(CTX / "my-notes.md").write_text("- **Secretish:** a memory note, not a setup file\n")
(KIT / "memory/personal/health.md").write_text("- **Doctor:** Dr. Who-Personal\n")
shutil.copy(REPO / "kit/memory/context/connector-guard.json", CTX / "connector-guard.json")
shutil.copy(REPO / "kit/memory/context/sharing-policy.json", CTX / "sharing-policy.json")
shutil.copy(REPO / "kit/models.json", KIT / "models.json")
(KIT / "QUEUE.md").write_text("# Queue\n\n## Alex\n\n## Kit\n\n## Waiting on others\n")
(KIT / ".gitignore").write_text(".install/\n")

GIT = ["git", "-C", str(KIT), "-c", "user.name=Kit Test", "-c", "user.email=kit@example.com",
       "-c", "commit.gpgsign=false"]
subprocess.run(["git", "init", "-q", str(KIT)], check=True)
subprocess.run(["git", "-C", str(KIT), "config", "user.name", "Kit Test"], check=True)
subprocess.run(["git", "-C", str(KIT), "config", "user.email", "kit@example.com"], check=True)
subprocess.run(["git", "-C", str(KIT), "config", "commit.gpgsign", "false"], check=True)
subprocess.run(["git", "-C", str(KIT), "add", "-A"], check=True)
subprocess.run(["git", "-C", str(KIT), "commit", "-q", "-m", "start"], check=True)

# ---------------------------------------------------------------------------------------------------------------
# Phase 1: collection, masking, personal left out, text and HTML.
items = ks.collect(KIT)
by = {s["id"]: s for s in items}
names = {s["name"] for s in items}
ok(all(s["area"] in ks.AREAS for s in items), "every setting has a known area")
ok({"config", "setup", "json"} <= {s["kind"] for s in items}, "config, setup fields, and JSON are all collected")
ok("Doctor" not in names and not any("personal" in s["source"] for s in items), "memory/personal is never shown")
ok("Secretish" not in names, "memory notes that aren't shipped setup files are left out")
tok = by["config|FAKE_API_TOKEN"]
ok(tok["secret"] and tok["value"] == ks.MASK and not tok["editable"], "a credential-named key is masked and read-only")
ok(by["config|PPMX_TOKEN_ENV"]["value"] == "PPMX_PAT" and not by["config|PPMX_TOKEN_ENV"]["secret"],
   "a credential's environment-variable name shows by name")
rec = next(s for s in items if s["name"] == "Records")
ok(rec["secret"] and "abcdefgh" not in rec["value"] and not rec["editable"], "a credential-shaped value is masked")
ok(by["config|DELIVERY_EMAIL_TO"]["status"] == "not set", "a placeholder address is not set")
ok(by["config|DELIVERY"]["status"] == "default", "a value matching config.example is default")
ok(by["config|OWNER_NAME"]["status"] == "set" and by["config|OWNER_NAME"]["line"] == 2, "a changed value is set, with its line")
ok(by["config|RETRY_DELAY"]["line"] is None and by["config|RETRY_DELAY"]["status"] == "default",
   "a documented key missing from the config shows its default")
ok("Default: 120" in by["config|RETRY_DELAY"]["description"], "and says what the default is")
ok(by["config|COST_WARN_PCT"]["description"], "config keys get a description from config.example or INSTALL.md")
ok(not by["config|DUP_KEY"]["editable"] and "2 times" in by["config|DUP_KEY"]["note"], "a key set twice is read-only")
lib = next(s for s in items if s["name"] == "Library root")
ok(lib["status"] == "set" and lib["editable"] and lib["type"] == ("setup_path",), "Library root: set, editable path")
mgr = next(s for s in items if s["name"] == "Manager role")
ok(mgr["status"] == "not set" and "engineering manager" in mgr["description"], "not set, with the setup file's own description")
ok(mgr["line"] == 3 and mgr["source"] == "memory/context/oneonone.md", "source file and line")
ps = next(s for s in items if s["name"] == "Priority senders")
ok(not ps["editable"] and "list" in ps["note"], "a field holding a list is read-only")
ok(not any(s["editable"] for s in items if s["source"].endswith("connectors.md")), "connectors.md is read-only")
ok(not any(s["editable"] for s in items if s["kind"] == "json"), "every JSON config is read-only")
ok(not by["config|ALLOW_TOOLS"]["editable"] and "Permission" in by["config|ALLOW_TOOLS"]["note"],
   "ALLOW_TOOLS is read-only, with how to change it")
ok(next(s for s in items if s["name"] == "Kit id")["editable"] and
   not next(s for s in items if s["name"] == "Classification")["editable"], "sharing.md: Kit id editable, Classification not")

text = ks.text_report(items)
ok("zz-test-value-123" not in text and "abcdefgh" not in text and "Dr. Who" not in text, "the text report shows no secret or personal value")
ok("[not set]" in text and "memory/context/oneonone.md:3" in text, "the text report has statuses and sources")
r = subprocess.run([sys.executable, str(REPO / "shared/bin/kit-settings"), "show", "--all", "--not-set"],
                   capture_output=True, text=True, env=os.environ, timeout=60)
ok(r.returncode == 0 and "Manager role" in r.stdout and "[set]" not in r.stdout, "kit-settings show --all --not-set", r.stderr)
r = subprocess.run([sys.executable, str(REPO / "shared/bin/kit-settings"), "show", "--all", "--json"],
                   capture_output=True, text=True, env=os.environ, timeout=60)
rows = json.loads(r.stdout or "[]")
ok(rows and not any("raw" in x for x in rows) and "zz-test-value-123" not in r.stdout, "show --all --json has no raw values")
ok(not any("edit_value" in x for x in rows if x["secret"]), "no edit value for a masked setting")
r = subprocess.run([sys.executable, str(REPO / "shared/bin/kit-settings")], capture_output=True, text=True,
                   env=os.environ, timeout=60)
ok(r.returncode == 0 and "Morning brief" in r.stdout, "plain kit-settings still shows the delivery summary", r.stderr)

panel = ks.dashboard_panel(KIT)
ok('id="kset"' in panel and "kset-q" in panel and "kset-status" in panel and "<script>" in panel,
   "the panel has a search box, a status filter, and inline script")
ok("http" not in panel.split("<script>")[1].split("</script>")[0] and "src=" not in panel, "no outside assets")
ok('data-status="not set"' in panel and "not set</strong>" in panel, "not-set rows are marked for highlighting")
ok("zz-test-value-123" not in panel and "Dr. Who" not in panel, "the panel shows no secret or personal value")
ok("<input class=\"kin\"" not in panel and "Preview" not in panel, "the dashboard panel has no edit controls")
ok("&lt;" in ks.render_table([ks._setting(id="x", name="<b>x</b>", raw="<script>", status="set")]),
   "names and values are escaped")

env = dict(os.environ)
r = subprocess.run([sys.executable, str(REPO / "shared/dashboard.py")], capture_output=True, text=True, env=env, timeout=300)
dash = (KIT / "dashboard.html").read_text() if (KIT / "dashboard.html").exists() else ""
ok(r.returncode == 0 and 'id="settings"' in dash and "kset" in dash, "dashboard.py renders the Settings panel", r.stderr[-500:])
ok("zz-test-value-123" not in dash and "Dr. Who" not in dash, "the dashboard shows no secret or personal value")
ok("aren't in the template" not in r.stderr, "the shipped template has the settings placeholder", r.stderr[-300:])
(KIT / "templates").mkdir(exist_ok=True)
(KIT / "templates/dashboard.html").write_text("<html><body><main>$hero $lane_you $lane_kit $lane_wait $schedule $briefs "
                                              "$health_checks $runs_head $runs_rows $audit_banner $audit $staff $sprint "
                                              "$reliability $now_iso $now_text</main></body></html>")
r = subprocess.run([sys.executable, str(REPO / "shared/dashboard.py")], capture_output=True, text=True, env=env, timeout=300)
dash2 = (KIT / "dashboard.html").read_text()
ok('id="settings"' in dash2 and dash2.index('id="settings"') < dash2.index("</main>"),
   "an owner's template without $settings still gets the panel, inside main")
shutil.copy(KIT / "dashboard.html", TMP / "dashboard-owner-template.html")
(KIT / "templates/dashboard.html").unlink()
subprocess.run([sys.executable, str(REPO / "shared/dashboard.py")], capture_output=True, text=True, env=env, timeout=300)
shutil.copy(KIT / "dashboard.html", TMP / "dashboard-render.html")

ok('"Bash(kit-settings ui)"' in (REPO / "shared/kit_setup.py").read_text() and
   '"Bash(kit-settings ui *)"' in (REPO / "shared/kit_setup.py").read_text(),
   "the installer makes Claude Code ask before kit-settings ui")

# ---------------------------------------------------------------------------------------------------------------
# Validation, straight through kit_settings.
def bad(sid, value, why, platform="darwin"):
    try:
        ks.plan_edit(KIT, sid, value, platform=platform)
        ok(False, why, "accepted")
    except (ks.Invalid, ks.Refused) as ex:
        ok(True, f"{why}: {str(ex)[:70]}")


bad("config|COST_WARN_PCT", "abc", "a number must be a number")
bad("config|COST_WARN_PCT", "150", "a number must be in range")
bad("config|DELIVERY", "carrier-pigeon", "a channel must be a known value")
bad("config|DELIVERY_WORK", "imessage", "work items never go outside Microsoft 365")
bad("config|DELIVERY", "sms", "sms is Windows only", platform="darwin")
bad("config|DELIVERY_EMAIL_TO", "not-an-address", "an email must be an email")
bad("config|OWNER_NAME", "$(touch /tmp/x)", "shell characters are refused in the run config")
bad("config|OWNER_NAME", 'Al"ex', "quotes are refused in the run config")
bad("config|SKIP_DAYS", "8", "weekdays are 1 to 7")
bad("config|EOD", "maybe", "on/off fields take on or off")
bad("config|TODOS_WORK", "apple", "work to-dos never go to Apple Reminders")
bad(lib["id"], "~/Library", "a path must start with a backticked path")
bad(lib["id"], "`<library root>/x`", "a backticked placeholder is refused")
last = next(s for s in items if s["name"] == "Last 1:1")
bad(last["id"], "2026-11-04", "a date must be DD-Mmm-YYYY")
bad(last["id"], "31-Feb-2026", "a date must exist")
bad(mgr["id"], "head of\narchitecture", "line breaks are refused")
bad(mgr["id"], "- **Injected:** x", "a value can't start a new list item")
bad(mgr["id"], "token: abcdefgh", "a credential-shaped value is never written")
bad(next(s for s in items if s["name"] == "Kit id")["id"], "Alex Rivera", "a Kit id must be lowercase")
try:
    ks.plan_edit(KIT, "config|DELIVERY_PERSONAL", "imessage local", platform="darwin")
    ok(True, "personal items may go by iMessage on macOS")
except ks.Invalid as ex:
    ok(False, "personal items may go by iMessage on macOS", ex)

# ---------------------------------------------------------------------------------------------------------------
# Phase 2: the server.
srv, st = ui.make_server(KIT, idle=120)
st.platform = "darwin"
srv.rebuild = False
th = threading.Thread(target=ui.serve, args=(srv, st), daemon=True)
th.start()
PORT = st.port
ORIGIN = f"http://127.0.0.1:{PORT}"


def req(method, path, body=None, headers=None, host=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=20)
    h = {"Host": host or f"127.0.0.1:{PORT}"}
    h.update(headers or {})
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    c.request(method, path, body=data, headers=h)
    r = c.getresponse()
    out = r.status, dict(r.getheaders()), r.read().decode("utf-8", "replace")
    c.close()
    return out


ok(st.url().startswith("http://127.0.0.1:") and srv.server_address[0] == "127.0.0.1", "binds 127.0.0.1 only")
code, _, _ = req("GET", "/")
ok(code == 403, "no token: 403")
code, _, _ = req("GET", "/?token=wrong")
ok(code == 403, "a wrong token: 403")
code, _, _ = req("GET", "/?token=" + st.token, host=f"evil.example:{PORT}")
ok(code == 403 and not st.token_used, "a bad Host (DNS rebinding) is refused before the token is used")
code, hdr, _ = req("GET", "/?token=" + st.token, host="localhost:%d" % PORT)
cookie = hdr.get("Set-Cookie", "")
ok(code == 303 and hdr.get("Location") == "/" and "HttpOnly" in cookie and "SameSite=Strict" in cookie,
   "the token is traded for an HttpOnly, SameSite=Strict cookie", (code, hdr))
COOKIE = cookie.split(";")[0]
code, _, _ = req("GET", "/?token=" + st.token)
ok(code == 403, "the link works once")
code, hdr, body = req("GET", "/", headers={"Cookie": COOKIE})
ok(code == 200 and st.csrf in body and "Preview" in body, "the page loads with the cookie", code)
csp = hdr.get("Content-Security-Policy", "")
ok("default-src 'none'" in csp and "frame-ancestors 'none'" in csp and "nonce-" in csp, "a strict CSP with a nonce")
ok(hdr.get("X-Frame-Options") == "DENY" and hdr.get("Cache-Control") == "no-store", "no framing, no caching")
ok("zz-test-value-123" not in body and "Dr. Who" not in body and "abcdefgh" not in body, "the page shows no secret or personal value")
code, _, _ = req("GET", "/", headers={"Cookie": COOKIE}, host=f"attacker.test:{PORT}")
ok(code == 403, "a bad Host is refused even with the cookie")
code, _, _ = req("GET", "/", headers={"Cookie": COOKIE.split("=")[0] + "=forged"})
ok(code == 403, "a forged cookie: 403")
code, _, b = req("GET", "/api/settings", headers={"X-Kit-Token": st.token})
ok(code == 200 and "zz-test-value-123" not in b, "the X-Kit-Token header works, and the JSON has no secret")

GOOD = {"Cookie": COOKIE, "Origin": ORIGIN, "X-CSRF-Token": st.csrf, "Content-Type": "application/json"}


def post(path, body, **over):
    h = dict(GOOD)
    for k, v in over.items():
        k = k.replace("_", "-")
        if v is None:
            h.pop(k, None)
        else:
            h[k] = v
    code, _, b = req("POST", path, body, headers=h)
    try:
        return code, json.loads(b)
    except ValueError:
        return code, {"raw": b}


before = sha(CONFIG)
pv = {"id": "config|COST_WARN_PCT", "value": "70"}
ok(post("/api/preview", pv, X_CSRF_Token=None)[0] == 403, "a POST without the CSRF token: 403")
ok(post("/api/preview", pv, X_CSRF_Token="nope")[0] == 403, "a POST with a wrong CSRF token: 403")
ok(post("/api/preview", pv, Origin="http://evil.example")[0] == 403, "a POST from another origin: 403")
ok(post("/api/preview", pv, Origin=None)[0] == 403, "a POST with no Origin or Referer: 403")
ok(post("/api/preview", pv, Origin=None, Referer=ORIGIN + "/")[0] == 200, "a same-origin Referer is enough")
ok(post("/api/preview", pv, Cookie=None)[0] == 403, "a POST without the session: 403")
ok(post("/api/preview", pv, Content_Type="text/plain")[0] == 415, "a POST that isn't JSON: 415")
code, _, _ = req("POST", "/api/preview", b"x" * (ui.MAX_BODY + 10), headers=GOOD)
ok(code == 413, "an oversized body: 413")
ok(req("PUT", "/api/apply", pv, headers=GOOD)[0] == 405, "other methods: 405")
code, j = post("/api/preview", pv)
ok(code == 200 and '-COST_WARN_PCT="80"' in j["diff"] and '+COST_WARN_PCT="70"' in j["diff"], "preview shows the diff", j)
ok(sha(CONFIG) == before, "a preview writes nothing")

# Read-only settings are refused, and nothing changes.
guarded = [CTX / "connector-guard.json", KIT / "models.json", CTX / "sharing-policy.json", CTX / "connectors.md",
           CTX / "sharing.md", CONFIG]
sums = {p: sha(p) for p in guarded}
conn = next(s for s in items if s["source"].endswith("connectors.md"))
classif = next(s for s in items if s["name"] == "Classification")
for sid, why in (("json|memory/context/connector-guard.json|allowed_servers", "connector-guard.json"),
                 ("json|models.json|default_profile", "models.json (model routing)"),
                 ("json|memory/context/sharing-policy.json|allowed_transports", "sharing-policy.json"),
                 ("config|ALLOW_TOOLS", "ALLOW_TOOLS (permission rules)"),
                 ("config|TEXTBACK_MODEL", "a model choice"),
                 ("config|FAKE_API_TOKEN", "a credential"),
                 ("info|permissions", "Claude Code's permission rules"),
                 (conn["id"], "connectors.md"), (classif["id"], "sharing.md Classification"),
                 ("setup|../../../.claude/settings.json||permissions|1", "a path outside memory/context"),
                 ("config|NOT_A_KEY", "an unknown key")):
    for ep in ("/api/preview", "/api/apply"):
        code, j = post(ep, {"id": sid, "value": "anything"})
        ok(code == 403 and not j.get("ok"), f"{ep} refuses {why}", (code, j))
ok(all(sha(p) == s for p, s in sums.items()), "and none of those files changed")
code, j = post("/api/apply", {"id": "config|COST_WARN_PCT", "value": "abc"})
ok(code == 400 and "whole number" in j.get("error", ""), "validation errors come back with a message", j)

# A config edit: one line, every other byte kept, a backup, a log line, no commit (the config isn't tracked).
old = CONFIG.read_bytes()
s0 = {x["id"]: x for x in ks.collect(KIT)}["config|COST_WARN_PCT"]
ok(post("/api/apply", {"id": "config|COST_WARN_PCT", "value": "70", "expect": "0" * 16})[0] == 403,
   "a stale page (the value changed since) is refused")
code, j = post("/api/apply", {"id": "config|COST_WARN_PCT", "value": "70", "expect": ks.fingerprint(s0["raw"])})
new = CONFIG.read_bytes()
ok(code == 200 and j.get("ok"), "a config edit is saved", j)
ok(new == old.replace(b'COST_WARN_PCT="80"\n', b'COST_WARN_PCT="70"\n'), "only that line changed, byte for byte")
ok(not j["committed"] and "isn't in Kit's history" in j["message"], "the config isn't tracked: saved, and it says so", j)
bak = pathlib.Path(j["backup"])
ok(bak.exists() and bak.read_bytes() == old and ".install/backups/settings" in bak.as_posix(), "the old file is backed up")
logtext = ks.log_path(KIT).read_text()
ok('COST_WARN_PCT: "80" -> "70"' in logtext, "the edit is logged with old and new values", logtext[-300:])
# A key missing from the config is added as one line; the unterminated last line gets its line end.
code, j = post("/api/apply", {"id": "config|RETRY_DELAY", "value": "300"})
ok(code == 200 and CONFIG.read_bytes() == new + b'\nRETRY_DELAY="300"\n', "a missing key is added as one new line")

# A setup field edit: the field's own lines replaced, CRLF kept, the rest byte-exact, committed.
one_old = ONE.read_bytes()
code, j = post("/api/apply", {"id": next(s for s in ks.collect(KIT) if s["name"] == "Manager role")["id"],
                              "value": "head of architecture"})
one_new = ONE.read_bytes()
want = one_old.replace(b"- **Manager role:** not set. For example \"engineering manager\" or\r\n"
                       b"  \"head of architecture\".\r\n", b"- **Manager role:** head of architecture\r\n")
ok(code == 200 and one_new == want, "a wrapped setup field becomes one line; every other byte is kept", (code, j))
ok(one_new.endswith(b"Trailing text \xe2\x80\x94 kept"), "the file's last line, with no newline, is untouched")
logmsg = subprocess.run(["git", "-C", str(KIT), "log", "-1", "--format=%s"], capture_output=True, text=True).stdout
ok(j.get("committed") and "Manager role" in logmsg and "oneonone.md" in logmsg, "committed, naming the field", logmsg)
dirty = subprocess.run(["git", "-C", str(KIT), "status", "--porcelain", "--", "memory/context/oneonone.md"],
                       capture_output=True, text=True).stdout
ok(not dirty.strip(), "nothing left uncommitted for that file")
# Only that file is in the commit, even with other changes lying around.
(KIT / "QUEUE.md").write_text("# Queue\n\n## Alex\n- [ ] something unrelated\n")
subprocess.run(["git", "-C", str(KIT), "add", "QUEUE.md"], check=True)
lastid = next(s for s in ks.collect(KIT) if s["name"] == "Last 1:1")["id"]
code, j = post("/api/apply", {"id": lastid, "value": "03-Nov-2026"})
files = subprocess.run(["git", "-C", str(KIT), "show", "--name-only", "--format=", "HEAD"], capture_output=True,
                       text=True).stdout.split()
ok(code == 200 and files == ["memory/context/oneonone.md"], "the commit holds only the edited file", files)
ok(b"- **Last 1:1:** 03-Nov-2026\r\n" in ONE.read_bytes(), "a DD-Mmm-YYYY date is written")
# A failed commit keeps the write and says so.
lock = KIT / ".git/index.lock"
lock.write_text("")
code, j = post("/api/apply", {"id": next(s for s in ks.collect(KIT) if s["name"] == "Day")["id"], "value": "Thursday"})
lock.unlink()
ok(code == 200 and not j["committed"] and "commit failed" in j["message"] and b"- **Day:** Thursday\r\n" in ONE.read_bytes(),
   "when git fails the write is kept and the message says so", j)
# A path field.
code, j = post("/api/apply", {"id": lib["id"], "value": "`~/Documents/Library` (work storage)"})
ok(code == 200 and ks.kc.library_root(KIT) == pathlib.Path.home() / "Documents/Library",
   "a path written here reads back through kit_compliance's own parser", j)

# The redesigned page: section list, cards, labels, badges, controls, and no secret.
code, _, body = req("GET", "/", headers={"Cookie": COOKIE})
ok(all(f'id="p-{g}"' in body for g in ("delivery", "budget", "documents")) and 'id="knav"' in body,
   "the page has a section list and a panel per group")
ok('id="kq"' in body and 'id="kchanged"' in body and 'id="kshow"' in body, "search, Only changed, and the Show filter")
ok("Monthly budget (USD)" in body and "COST_BUDGET_MONTHLY" in body, "plain-English labels, with the raw key small")
ok('type="checkbox" role="switch"' in body, "on/off settings are switches")
ok('type="number"' in body and 'min="1" max="100"' in body, "numbers get a number box with their range")
ok('class="kbadge changed"' in body and 'class="kbadge notset"' in body and 'class="kbadge ro"' in body,
   "changed, not set, and read-only badges")
ok('data-act="reset"' in body, "a Reset to default button where there's a default to go back to")
ok('id="kbar"' in body and 'data-act="batch-preview"' in body, "the sticky unsaved-changes bar")
ok('id="p-snapshots"' in body and 'id="p-review"' in body, "Snapshots and Review loop sections")
ok("zz-test-value-123" not in body and "abcdefgh" not in body and "Dr. Who" not in body, "still no secret or personal value")
ok(not re.search(r"<(script|link|img|iframe)[^>]*\s(src|href)=", body) and "@import" not in body
   and "url(" not in body, "no external script, style, image, or link")
ok(body.count("<script nonce=") == 1 and body.count("<style nonce=") == 1 and " style=" not in body,
   "one nonce'd script and style, and no inline style attributes (the CSP would block them)")
items_now = ks.collect(KIT)
ok(all(s["group"] in ks.GROUP_IDS for s in items_now), "every setting has a page group")
unk = next(s for s in items_now if s["name"] == "DUP_KEY")
ok(unk["group"] == "advanced" and unk["label"] == "DUP_KEY", "a key with no description shows in Advanced by its raw name")
ok(ks.public(next(s for s in items_now if s["name"] == "COST_WARN_PCT")).get("default") is not None,
   "an editable setting reports its default")

# Batch save: preview, refused batches, then one confirmed save with a snapshot first.
cfg0 = CONFIG.read_bytes()
s_warn = next(s for s in items_now if s["name"] == "COST_WARN_PCT")
s_stop = next(s for s in items_now if s["name"] == "COST_STOP_PCT")
batch = {"changes": [{"id": s_warn["id"], "value": "65", "expect": ks.fingerprint(s_warn["raw"])},
                     {"id": s_stop["id"], "value": "90"}]}
ok(post("/api/batch/preview", batch, X_CSRF_Token=None)[0] == 403, "batch: no CSRF token, 403")
ok(post("/api/batch/apply", batch, Origin="http://evil.example")[0] == 403, "batch: another origin, 403")
code, j = post("/api/batch/preview", batch)
ok(code == 200 and j["ok"] and len(j["items"]) == 2 and all(x["ok"] for x in j["items"]) and
   '+COST_WARN_PCT="65"' in j["items"][0]["diff"], "batch preview: a diff per change", j)
ok(CONFIG.read_bytes() == cfg0, "batch preview writes nothing")
bad = {"changes": batch["changes"] + [{"id": "config|COST_SPIKE_FACTOR", "value": "abc"}]}
code, j = post("/api/batch/preview", bad)
ok(code == 200 and not j["ok"] and not j["items"][2]["ok"] and "number" in j["items"][2]["error"],
   "batch preview marks the invalid one", j)
code, j = post("/api/batch/apply", bad)
ok(code == 400 and not j["ok"] and CONFIG.read_bytes() == cfg0, "a batch with any invalid change saves nothing", j)
code, j = post("/api/batch/apply", {"changes": [{"id": "config|ALLOW_TOOLS", "value": "Bash(*)"}]})
ok(code == 400 and CONFIG.read_bytes() == cfg0, "a batch with a read-only setting saves nothing", j)
code, j = post("/api/batch/apply", {"changes": [batch["changes"][0], batch["changes"][0]]})
ok(code == 400 and "twice" in j.get("error", ""), "the same setting twice in a batch is refused")
ok(post("/api/batch/apply", {"changes": []})[0] == 400 and
   post("/api/batch/apply", {"changes": [{"id": 1, "value": "x"}]})[0] == 400, "malformed batches: 400")
ok(post("/api/batch/apply", {"changes": [{"id": "x", "value": "1"}] * (ui.MAX_BATCH + 1)})[0] == 400, "too many changes: 400")
import kit_config as kcfg  # noqa: E402
n_snaps = len(kcfg.ids(KIT))
code, j = post("/api/batch/apply", batch)
txt = CONFIG.read_text()
ok(code == 200 and j["ok"] and 'COST_WARN_PCT="65"' in txt and 'COST_STOP_PCT="90"' in txt, "batch apply saves both", j)
ok(j.get("snapshot") and len(kcfg.ids(KIT)) == n_snaps + 1 and f'COST_WARN_PCT="{s_warn["raw"]}"' in
   kcfg.snap_file(KIT, j["snapshot"], ks.CONFIG_REL), "a snapshot of the state before is taken first")
ok("zz-test-value-123" not in kcfg.snap_file(KIT, j["snapshot"], ks.CONFIG_REL), "and it holds no credential")
code, j = post("/api/batch/apply", batch)
ok(code == 400 and not j["ok"], "an old batch is refused once its settings changed (the expect check)", j)

# A single save takes a snapshot too.
n_snaps = len(kcfg.ids(KIT))
code, j = post("/api/apply", {"id": "config|COST_WARN_PCT", "value": "60"})
ok(code == 200 and j.get("snapshot") and len(kcfg.ids(KIT)) == n_snaps + 1, "a single save takes a snapshot first", j)

# Snapshots from the page: take, diff, restore preview, restore (confirm needed), undo.
code, j = post("/api/snapshots/take", {"note": "from the test"})
ok(code == 200 and j["ok"] and j["new"], "take a snapshot from the page", j)
mark = j["id"]
code, j = post("/api/snapshots/take", {"note": "again"})
ok(code == 200 and not j["new"] and j["id"] == mark, "an unchanged state isn't snapshotted twice", j)
ks.apply_edit(KIT, "config|COST_WARN_PCT", "55", rebuild=False)
code, j = post("/api/snapshots/diff", {"id": mark})
ok(code == 200 and '-COST_WARN_PCT="60"' in j["diff"] and '+COST_WARN_PCT="55"' in j["diff"], "diff against now", j)
ok(post("/api/snapshots/diff", {"id": "../../etc"})[0] == 400 and post("/api/snapshots/diff", {"id": "20990101-000000"})[0] == 400,
   "an unknown or path-like snapshot id is refused")
code, j = post("/api/snapshots/restore-preview", {"id": mark})
ok(code == 200 and j["changes"] == 1 and 'COST_WARN_PCT="55"' in CONFIG.read_text(), "restore preview writes nothing", j)
ok(post("/api/snapshots/restore", {"id": mark})[0] == 400, "restore without confirm: 400")
code, j = post("/api/snapshots/restore", {"id": mark, "confirm": True})
ok(code == 200 and j["ok"] and 'COST_WARN_PCT="60"' in CONFIG.read_text() and 'FAKE_API_TOKEN="zz-test-value-123"' in
   CONFIG.read_text(), "restore puts the value back and keeps the credential line", j)
code, j = post("/api/snapshots/restore", {"id": j["before"], "confirm": True})
ok(code == 200 and 'COST_WARN_PCT="55"' in CONFIG.read_text(), "the snapshot taken before a restore undoes it", j)
code, _, body = req("GET", "/", headers={"Cookie": COOKIE})
ok(mark in body and 'data-act="snap-restore"' in body, "the Snapshots section lists them")
logtxt = (KIT / ".install/logs/settings-ui.log").read_text()
ok("restore" in logtxt and "zz-test-value-123" not in logtxt, "restores are in the change log, without secrets")

# Stop.
code, j = post("/api/stop", {})
th.join(10)
ok(code == 200 and not th.is_alive(), "the Stop button shuts the server down")

# Idle shutdown.
srv2, st2 = ui.make_server(KIT, idle=1)
th2 = threading.Thread(target=ui.serve, args=(srv2, st2), daemon=True)
t0 = time.monotonic()
th2.start()
th2.join(15)
ok(not th2.is_alive() and time.monotonic() - t0 < 10, "it shuts down by itself when idle")

# The dashboard rebuild after a write (in the background, in the fake folder).
(KIT / "dashboard.html").unlink()
res = ks.apply_edit(KIT, "config|RETRY_DELAY", "240", rebuild=True)
for _ in range(240):
    if (KIT / "dashboard.html").exists() and "RETRY_DELAY" in (KIT / "dashboard.html").read_text(errors="ignore"):
        break
    time.sleep(0.5)
ok("being rebuilt" in res["message"] and (KIT / "dashboard.html").exists(), "the dashboard is rebuilt after a write")

print(f"\n{P} passed, {F} failed. Renders: {TMP / 'dashboard-render.html'}")
if F == 0 and not os.environ.get("KIT_KEEP_TMP"):
    shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if F else 0)

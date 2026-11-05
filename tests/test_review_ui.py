#!/usr/bin/env python3
"""Tests for the Review loop section of kit-settings ui and the dashboard's Reviews panel and health badge:
the projects in the library with their "ready for ARB" score and note links; notes opening read-only (Markdown
inside the project's own folder only: no "..", absolute paths, other files, or symlinks out); Start asking for
confirmation with the cost first, then running kit-review-loop in the background (a stand-in here) with its
progress; one run at a time; Merge writing the decisions file; and the dashboard built from the same folder,
from the default template and from an owner's older copy without the new placeholders. Synthetic folders only;
no model or connector call.

  python3 tests/test_review_ui.py
"""
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

REPO = pathlib.Path(__file__).resolve().parent.parent
TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-review-ui-"))
HOME = TMP / "home"
KIT = HOME / "Claude/Agents/kit"
LIB = TMP / "library"
PROJ = LIB / "artifacts/payments-hub"
os.environ.update(HOME=str(HOME), USERPROFILE=str(HOME), KIT_DIR=str(KIT), PYTHONDONTWRITEBYTECODE="1",
                  KIT_TODAY="2026-11-05")
sys.dont_write_bytecode = True
for d in (KIT / "memory/context", KIT / ".install/shared/morning", KIT / ".install/logs", KIT / "agents",
          KIT / "briefs", PROJ / "reviews", PROJ / "drafts", LIB / "artifacts/empty-one"):
    d.mkdir(parents=True, exist_ok=True)
(KIT / "memory/context/library.md").write_text(f"# Library\n\n- **Library root:** `{LIB}`\n", encoding="utf-8")
(KIT / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\n', encoding="utf-8")
(PROJ / "drafts/Payments IA v0.2.md").write_text("# IA v0.2\n", encoding="utf-8")
time.sleep(0.05)
(PROJ / "reviews/payments-review-v0.2.md").write_text(
    "# Review\nDate: 04-Nov-2026\n\n## Findings\n\n| ID | Severity | Category | Template | Section | Finding | Fix |\n"
    "|---|---|---|---|---|---|---|\n| F-01 | critical | template | IA | 3 | No RTO. | State it. |\n"
    "| F-02 | minor | style | IA | 4 | Wordy. | Trim. |\n", encoding="utf-8")
(LIB / "secret.md").write_text("outside the project\n", encoding="utf-8")
(PROJ / "drafts/notes.csv").write_text("not a draft\n", encoding="utf-8")
try:
    os.symlink(LIB / "secret.md", PROJ / "reviews/link.md")
    LINKED = True
except (OSError, NotImplementedError):
    LINKED = False

sys.path.insert(0, str(REPO / "shared"))
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


srv, st = ui.make_server(KIT, idle=120)
srv.rebuild = False
th = threading.Thread(target=ui.serve, args=(srv, st), daemon=True)
th.start()
PORT = st.port
ORIGIN = f"http://127.0.0.1:{PORT}"


def req(method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    h = {"Host": f"127.0.0.1:{PORT}"}
    h.update(headers or {})
    c.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=h)
    r = c.getresponse()
    out = r.status, dict(r.getheaders()), r.read().decode("utf-8", "replace")
    c.close()
    return out


code, hdr, _ = req("GET", "/?token=" + st.token)
COOKIE = hdr.get("Set-Cookie", "").split(";")[0]
GOOD = {"Cookie": COOKIE, "Origin": ORIGIN, "X-CSRF-Token": st.csrf, "Content-Type": "application/json"}


def post(path, body):
    code, _, b = req("POST", path, body, GOOD)
    return code, json.loads(b)


# ---- the page --------------------------------------------------------------------------------------------------
code, _, page = req("GET", "/", headers={"Cookie": COOKIE})
ok(code == 200 and "Review loop" in page and 'data-project="payments-hub"' in page, "the page has the Review loop section",
   page[-1500:])
ok("Not ready: " in page and "1 must fix" in page, "each project shows its ready-for-ARB score", page[-1500:])
ok("empty-one" not in page, "folders with no drafts/ or reviews/ aren't listed")
ok("Payments IA v0.2.md" in page and "notes.csv" not in page, "the draft list has the drafts (Markdown, Word, text)")
ok("/note?p=payments-hub&amp;f=reviews%2Fpayments-review-v0.2.md" in page, "each note is linked", page[-1500:])

# ---- notes open read-only, inside the project only ------------------------------------------------------------
code, hdr, body = req("GET", "/note?p=payments-hub&f=reviews/payments-review-v0.2.md", headers={"Cookie": COOKIE})
ok(code == 200 and "No RTO." in body and hdr.get("Content-Type", "").startswith("text/plain"),
   "a note opens as plain text", (code, hdr))
for bad in ("../../secret.md", "reviews/../../../secret.md", str(LIB / "secret.md"), "drafts/notes.csv",
            "reviews/nope.md"):
    code, _, _ = req("GET", "/note?" + __import__("urllib.parse").parse.urlencode({"p": "payments-hub", "f": bad}),
                     headers={"Cookie": COOKIE})
    ok(code == 404, f"refused: {bad}")
code, _, _ = req("GET", "/note?p=elsewhere&f=reviews/payments-review-v0.2.md", headers={"Cookie": COOKIE})
ok(code == 404, "refused: a project that isn't in the library")
if LINKED:
    code, _, _ = req("GET", "/note?p=payments-hub&f=reviews/link.md", headers={"Cookie": COOKIE})
    ok(code == 404, "refused: a symlink out of the project")
code, _, _ = req("GET", "/note?p=payments-hub&f=reviews/payments-review-v0.2.md")
ok(code == 403, "notes need the session like everything else")

# ---- start: confirm first, then one run in the background -------------------------------------------------------
code, j = post("/api/review/plan", {"project": "payments-hub", "draft": "Payments IA v0.2.md", "only": ""})
ok(code == 200 and "4 paid Claude Code run(s)" in j["message"] and "$8.00" in j["message"],
   "Start first says how many paid runs and about what they cost", j)
code, j = post("/api/review/plan", {"project": "payments-hub", "draft": "../../secret.md", "only": ""})
ok(code == 400, "a draft outside drafts/ is refused", j)
code, _, _ = req("POST", "/api/review/start", {"project": "payments-hub", "draft": "Payments IA v0.2.md"},
                 dict(GOOD, **{"X-CSRF-Token": "nope"}))
ok(code == 403, "starting a run needs the page's CSRF token")

FAKE = TMP / "fake-review-loop"
FAKE.write_text("import sys, time\nprint('kit-review-loop: reviewer ...', flush=True)\ntime.sleep(1.5)\n"
                "print('  reviewer: done, about $0.40')\nprint('    saved /tmp/x/reviews/note.md')\n"
                "print('ARGS ' + ' '.join(sys.argv[1:]))\n", encoding="utf-8")
real = ui.REVIEW_TOOL
st.review()                                  # loaded from the real tool before the stand-in takes its place
ui.REVIEW_TOOL = FAKE
code, j = post("/api/review/start", {"project": "payments-hub", "draft": "Payments IA v0.2.md", "only": "reviewer"})
ok(code == 200 and j["ok"], "Start (after confirming) starts the loop", j)
code, j2 = post("/api/review/start", {"project": "payments-hub", "draft": "Payments IA v0.2.md", "only": ""})
ok(code == 409 and "still running" in j2.get("error", ""), "one run at a time", j2)
code, j = post("/api/review/status", {})
ok(j["state"] == "running", "status: running", j)
for _ in range(40):
    time.sleep(0.25)
    j = post("/api/review/status", {})[1]
    if j["state"] != "running":
        break
ok(j["state"] == "finished" and "/tmp/x/reviews/note.md" in j["saved"], "status: finished, with the notes it saved", j)
ok("ARGS run" in j["tail"] and "--yes" in j["tail"] and "--only reviewer" in j["tail"]
   and str(PROJ) in j["tail"], "it ran kit-review-loop run PROJECT DRAFT --yes --only reviewer", j["tail"])
logs = list((KIT / ".install/logs").glob("review-loop-ui-*.log"))
ok(len(logs) == 1, "its output is kept in a log", logs)
ui.REVIEW_TOOL = real

# ---- merge --------------------------------------------------------------------------------------------------
code, j = post("/api/review/merge", {"project": "payments-hub"})
dec = PROJ / "review-decisions-2026-11-05.md"
ok(code == 200 and dec.is_file() and "review-decisions-2026-11-05.md" in j["link"], "Merge writes the decisions file "
   "and links it", j)
code, j = post("/api/review/merge", {"project": "nope"})
ok(code == 409, "Merge: only projects in the library", j)

post("/api/stop", {})
th.join(10)

# ---- dashboard: the Reviews panel and the health badge -----------------------------------------------------------
(KIT / ".install/shared").mkdir(parents=True, exist_ok=True)
r = subprocess.run([sys.executable, str(REPO / "shared/dashboard.py")], capture_output=True, text=True, timeout=180,
                   env=dict(os.environ))
html = (KIT / "dashboard.html").read_text(encoding="utf-8") if (KIT / "dashboard.html").exists() else ""
ok(r.returncode == 0 and 'class="hbadge' in html and "health</span>" in html, "the dashboard has the health badge",
   r.stderr[-800:])
ok('id="reviews"' in html and "payments-hub" in html and "Not ready:" in html and "review-decisions-2026-11-05.md" in html,
   "the dashboard's Reviews panel lists the project, its score, and its files", html[-2500:])
ok("Health score" in html and "Setup" in html and "Connectors" in html, "the Health panel shows the score's parts")
own = KIT / "templates/dashboard.html"
own.parent.mkdir(parents=True, exist_ok=True)
own.write_text("<html><body><header><h1>Kit</h1></header>$audit_banner $hero $lane_you $lane_kit $lane_wait $schedule "
               "$briefs <ul>$health_checks</ul> $runs_head $runs_rows $sprint $reliability $audit $staff $settings"
               "</body></html>", encoding="utf-8")
r = subprocess.run([sys.executable, str(REPO / "shared/dashboard.py")], capture_output=True, text=True, timeout=180,
                   env=dict(os.environ))
html = (KIT / "dashboard.html").read_text(encoding="utf-8")
ok(r.returncode == 0 and "<h1>Kit</h1><a class=\"hbadge" in html and 'id="reviews"' in html
   and "Health score: Setup" in html, "an owner's older template still gets the badge, the parts, and the Reviews panel",
   html[:1500])

print(f"\nreview UI tests: {P} passed, {F} failed")
if not F:
    shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if F else 0)

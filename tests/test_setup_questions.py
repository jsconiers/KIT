#!/usr/bin/env python3
"""Tests for the open setup questions (kit_setupq), `kit-settings questions` and `kit-settings answer`, and the
first-run Setup wizard in kit-settings ui: every "not set" field is a question with the agents that read its file,
high priority first; answer previews without writing, and --write changes only that field (the rest of the file
byte-identical), backs the file up, and the count of open questions, the health score's setup part, and doctor's
readiness all drop; bad values and ambiguous fields are refused; the wizard is open and first on a new install,
walks one question at a time, Skip and Later work, Done for now closes it, and its POSTs need the session and CSRF
token like every other change. Synthetic Kit folder (the shipped setup files and agents); no model or connector call.

  python3 tests/test_setup_questions.py
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

REPO = pathlib.Path(__file__).resolve().parent.parent
TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-setupq-"))
HOME = TMP / "home"
KIT = HOME / "Claude/Agents/kit"
os.environ.update(HOME=str(HOME), USERPROFILE=str(HOME), KIT_DIR=str(KIT), PYTHONDONTWRITEBYTECODE="1")
sys.dont_write_bytecode = True
(KIT / ".install/shared/morning").mkdir(parents=True)
(KIT / ".install/logs").mkdir(parents=True)
shutil.copytree(REPO / "kit/memory/context", KIT / "memory/context")
shutil.copytree(REPO / "kit/memory/context", KIT / ".install/kit/memory/context")
shutil.copytree(REPO / "kit/agents", KIT / "agents")
(KIT / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\n', encoding="utf-8")

sys.path.insert(0, str(REPO / "shared"))
import kit_setupq as sq  # noqa: E402
import kit_health  # noqa: E402
import doctor  # noqa: E402
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


def cli(*args):
    r = subprocess.run([sys.executable, str(REPO / "shared/bin/kit-settings"), *args], capture_output=True, text=True,
                       env=dict(os.environ), timeout=120)
    return r.returncode, r.stdout + r.stderr


# ---- the questions ---------------------------------------------------------------------------------------------
qs = sq.questions(KIT)
ok(len(qs) > 10, "the shipped setup files have open questions", len(qs))
ok(all(q["question"] and q["file"].endswith(".md") and q["field"] for q in qs), "each has a file, field, and question")
prios = [q["priority"] for q in qs]
ok(prios == sorted(prios, key=lambda p: p != "high"), "high priority questions come first", prios[:12])
cur = next((q for q in qs if q["file"] == "costs.md" and q["field"] == "Currency"), None)
ok(cur is not None, "costs.md Currency is a question", [(q["file"], q["field"]) for q in qs][:20])
ok(cur and "cost-estimator" in cur["agents"], "it names the agent that reads costs.md", cur)
ok(cur and cur["example"] == "USD", "it has an example answer", cur)
lib = next((q for q in qs if q["file"] == "library.md" and q["field"] == "Library root"), None)
if lib:
    ok(lib["priority"] == "high", "a path the health check reads is high priority", lib)
code, out = cli("questions", "--json")
j = json.loads(out) if code == 0 else {}
ok(code == 0 and j.get("counts", {}).get("not set") == len(qs), "kit-settings questions --json lists them", out[:400])
code, out = cli("questions")
ok(code == 0 and "not set" in out and "Currency" in out and "Read by:" in out, "kit-settings questions prints them", out[:400])

# ---- answer ----------------------------------------------------------------------------------------------------
costs = KIT / "memory/context/costs.md"
before = costs.read_bytes()
health_before = kit_health.setup(KIT)
ready_before = json.dumps(doctor.readiness(KIT))
code, out = cli("answer", "costs.md", "Currency", "USD")
ok(code == 0 and "+- **Currency:** USD" in out and "Nothing written" in out, "answer without --write shows the change", out)
ok(costs.read_bytes() == before, "and writes nothing")
code, out = cli("answer", "costs.md", "Currency", "USD", "--write")
ok(code == 0 and "Saved Currency" in out, "answer --write saves it", out)
after = costs.read_bytes()
bl, al = before.decode().splitlines(keepends=True), after.decode().splitlines(keepends=True)
i = next(n for n, ln in enumerate(bl) if ln.startswith("- **Currency:**"))
j_ = next(n for n, ln in enumerate(al) if ln.startswith("- **Currency:**"))
ok(al[j_] == "- **Currency:** USD\n", "only that field's line changed", al[j_])
end = i + 1
while end < len(bl) and bl[end].strip() and bl[end][:1] in " \t":
    end += 1
ok(bl[:i] == al[:j_] and bl[end:] == al[j_ + 1:], "every other line is byte-identical")
ok(any((KIT / ".install/backups/settings").glob("*costs.md")), "the old file was backed up")
qs2 = sq.questions(KIT)
ok(len(qs2) == len(qs) - 1 and not any(q["file"] == "costs.md" and q["field"] == "Currency" for q in qs2),
   "one fewer open question", (len(qs), len(qs2)))
health_after = kit_health.setup(KIT)
ok(health_after["score"] > health_before["score"] and "Currency" not in json.dumps(health_after),
   "the health score's setup part rises", (health_before["detail"], health_after["detail"]))
ok("Currency" in ready_before and "Currency" not in json.dumps(doctor.readiness(KIT)),
   "doctor's readiness no longer lists it")
st_file = json.loads((KIT / sq.STATE).read_text())
ok(st_file.get("answered") == 1, "the wizard's state counts the answer (and holds no value)", st_file)
ok("USD" not in (KIT / sq.STATE).read_text(), "the state file never holds an answer")

code, out = cli("answer", "costs.md", "No such field", "x")
ok(code != 0 and "no field" in out, "an unknown field is refused", out)
code, out = cli("answer", "library.md", "Library root", "not a path", "--write")
ok(code != 0 and "backticked path" in out, "a bad value is refused (a path must be backticked)", out)
ok(costs.read_bytes() == after, "a refused answer writes nothing")
dup = KIT / "memory/context/standards.md"
code, out = cli("answer", "costs.md", "Currency", "EUR", "--section", "Nope")
ok(code != 0, "a section that doesn't hold the field is refused", out)

# ---- the wizard in kit-settings ui -----------------------------------------------------------------------------
(KIT / sq.STATE).unlink()                    # back to a new install
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


def post(path, body, headers=None):
    code, _, b = req("POST", path, body, headers or GOOD)
    return code, json.loads(b)


def first_id(page):
    import re
    m = re.search(r'id="kwiz-card" data-id="([^"]+)" data-expect="([^"]+)"', page)
    return (m.group(1).replace("&amp;", "&"), m.group(2)) if m else (None, None)


code, _, page = req("GET", "/", headers={"Cookie": COOKIE})
ok(code == 200 and '<details class="kwiz" id="kwiz" open>' in page, "on a new install the wizard is open", page[:1500])
ok(0 <= page.find('id="kwiz"') < page.find('id="p-delivery"') and 'data-first="setup"' in page,
   "and comes first: its section opens before the settings groups")
ok("style=" not in page.split("<body>", 1)[1], "no inline style attributes (the page's CSP blocks them)")
left = len(sq.questions(KIT))
ok(f'<span id="kwiz-left">{left}</span> not set' in page, "it shows how many are not set", left)
q1, exp1 = first_id(page)
walk, _, _ = sq.walk(KIT)
ok(q1 == walk[0]["id"], "it shows one question: the first in priority order", (q1, walk[0]["id"]))

code, j = post("/api/setup/mark", {"id": q1, "how": "later"}, dict(GOOD, **{"X-CSRF-Token": "wrong"}))
ok(code == 403, "marking a question needs the CSRF token")
code, _, b = req("POST", "/api/setup/mark", {"id": q1, "how": "later"}, {"Origin": ORIGIN, "X-CSRF-Token": st.csrf,
                                                                          "Content-Type": "application/json"})
ok(code == 403, "and the session")
code, j = post("/api/setup/mark", {"id": q1, "how": "bogus"})
ok(code == 400, "an unknown action is refused", j)
code, j = post("/api/setup/mark", {"id": "setup|nope.md||X|1", "how": "later"})
ok(code == 400, "an unknown question is refused", j)
code, j = post("/api/setup/mark", {"id": q1, "how": "later"})
ok(code == 200 and j["ok"], "Later saves it for later", j)
_, _, page = req("GET", "/", headers={"Cookie": COOKIE})
q2, exp2 = first_id(page)
ok(q2 and q2 != q1 and "1 saved for later" in page, "the next question shows, and one is saved for later", page[:2000])
code, j = post("/api/setup/mark", {"id": q2, "how": "skip"})
_, _, page = req("GET", "/", headers={"Cookie": COOKIE})
q3, exp3 = first_id(page)
w, _, _ = sq.walk(KIT)
ok(q3 != q2 and w[-1]["id"] == q2, "Skip moves a question to the end", (q2, q3, w[-1]["id"]))
code, j = post("/api/setup/mark", {"id": "", "how": "reset"})
w, _, _ = sq.walk(KIT)
ok(any(q["id"] == q1 for q in w), "Bring back returns the ones saved for later")

# answer the current one through the page, the same way as any setting
target = next(q for q in sq.walk(KIT)[0] if q["type"] == "setup_text")
code, j = post("/api/preview", {"id": target["id"], "value": "Answered from the wizard.", "expect": target["expect"]})
ok(code == 200 and j["ok"] and "Answered from the wizard." in j["diff"], "Preview shows the change", j)
code, j = post("/api/apply", {"id": target["id"], "value": "Answered from the wizard.", "expect": target["expect"]})
ok(code == 200 and j["ok"], "Confirm saves it", j)
code, j = post("/api/setup/mark", {"id": target["id"], "how": "answered"})
ok(code == 200 and j["left"] == left - 1, "and the count of open questions drops", j)
_, _, page = req("GET", "/", headers={"Cookie": COOKIE})
ok(f'<span id="kwiz-left">{left - 1}</span> not set' in page, "the page shows the new count")
code, j = post("/api/setup/mark", {"id": "", "how": "done"})
_, _, page = req("GET", "/", headers={"Cookie": COOKIE})
ok('<details class="kwiz" id="kwiz">' in page, "Done for now closes the wizard (it's still on the page)")

post("/api/stop", {})
th.join(5)
shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{P} passed, {F} failed")
sys.exit(1 if F else 0)

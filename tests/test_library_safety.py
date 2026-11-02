#!/usr/bin/env python3
"""Tests what keeps work, confidential, and closed material off the phone and out of texts: kit-library's
phone mirror and fetch --to-phone (collections and output kinds marked work or confidential, and the
sharing policy), its text-safe mode for show and search, the ask rules for mirror and fetch, and
kit-textback's side: kit send confirmed by code, the dry-run test, the config reader, the rate limit,
state saved before answering, and the question's tools confined to Kit's folder.

Everything happens in a temp HOME; nothing is sent. Run: python3 tests/test_library_safety.py
"""
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
LIB = REPO / "shared/bin/kit-library"
PASS = FAIL = 0


def ok(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


tmp = pathlib.Path(tempfile.mkdtemp())
home = tmp / "home"
kit = home / "Claude/Agents/kit"
(kit / "library").mkdir(parents=True)
(kit / "letters").mkdir()
(kit / "letters/bank.txt").write_text("A letter to the bank about the mortgage escrow.\n")
work = tmp / "work"; work.mkdir()
(work / "design.txt").write_text("Work design notes about the escrow service cutover.\n")
sermons = tmp / "sermons"; sermons.mkdir()
(sermons / "grace.txt").write_text("A sermon on grace and escrow of the heart.\n")
icloud = tmp / "icloud"
cfg = {"version": 1, "output": {"folder": str(home / "Kit Output"), "mirror": str(icloud),
                                "classification": {"reports": "work"}},
       "collections": [{"name": "work-docs", "folders": [str(work)], "classification": "work"},
                       {"name": "sermons", "folders": [str(sermons)]},
                       {"name": "kit-letters", "folders": [str(kit / "letters")]}]}
(kit / "library/collections.json").write_text(json.dumps(cfg))
ENV = dict(os.environ, HOME=str(home), KIT_DIR=str(kit), KIT_LIBRARY_APP=str(tmp / "no-app"))
ENV.pop("KIT_LIBRARY_SAFE", None)


def lib(*args, **env):
    r = subprocess.run([sys.executable, str(LIB), *args], capture_output=True, text=True, env=dict(ENV, **env))
    return r.returncode, r.stdout + r.stderr


rc, out = lib("index", "--quiet")
ok(rc == 0, "catalog built", out)


def doc_id(word):
    rc, out = lib("search", word, "--json")
    hits = json.loads(out)["results"] if rc == 0 else []
    return str(hits[0]["id"]) if hits else None


ids = {w: doc_id(w) for w in ("mortgage", "cutover", "sermon")}
ok(all(ids.values()), "every document cataloged", str(ids))

# ---- text-safe mode: show and search
rc, out = lib("show", ids["mortgage"], "--text")
ok(rc == 0 and "mortgage" in out, "show reads a letter in a session")
rc, out = lib("show", ids["mortgage"], "--text", KIT_LIBRARY_SAFE="1")
ok(rc != 0 and "closed to texts" in out and "mortgage" not in out, "text-safe show refuses Kit's letters/", out)
rc, out = lib("show", ids["cutover"], "--text", "--safe")
ok(rc != 0 and "work" in out and "cutover service" not in out, "--safe refuses a work collection", out)
rc, out = lib("show", ids["sermon"], "--text", KIT_LIBRARY_SAFE="1")
ok(rc == 0 and "grace" in out, "text-safe show still reads an open document", out)
rc, out = lib("search", "escrow", "--json", KIT_LIBRARY_SAFE="1")
titles = [h["title"].lower() for h in json.loads(out)["results"]] if rc == 0 else []
ok(titles == ["grace"], "text-safe search leaves out closed and work documents", str(titles))
rc, out = lib("search", "escrow", "--json")
ok(len(json.loads(out)["results"]) == 3, "a session's search finds all three")

# ---- the phone mirror and fetch --to-phone
rc, out = lib("fetch", ids["cutover"], "--to-phone", "--json")
ok(rc != 0 and "can't go to the phone" in out, "fetch --to-phone refuses work", out)
ok(not (icloud / "Sent to phone/design.txt").exists(), "nothing of the work document on the phone")
rc, out = lib("fetch", ids["sermon"], "--to-phone", "--json")
ok(rc == 0 and (icloud / "Sent to phone/grace.txt").exists(), "fetch --to-phone sends an open document", out)

note = tmp / "note.txt"; note.write_text("A plain note.\n")
rc, out = lib("deliver", str(note), "--kind", "research", "--name", "plain.txt", "--no-date")
ok(rc == 0 and (icloud / "Research/plain.txt").exists(), "a normal delivery is mirrored", out)
rc, out = lib("deliver", str(work / "design.txt"), "--kind", "research", "--name", "from-work.txt", "--no-date")
ok(rc == 0 and (home / "Kit Output/Research/from-work.txt").exists(), "work material is still delivered", out)
ok(not (icloud / "Research/from-work.txt").exists(), "work material is not mirrored")
rc, out = lib("deliver", str(note), "--kind", "reports", "--name", "status.txt", "--no-date")
ok(rc == 0 and not (icloud / "Reports/status.txt").exists(), "a kind marked work is not mirrored", out)
rc, out = lib("mirror")
ok(rc == 0 and not (icloud / "Research/from-work.txt").exists() and not (icloud / "Reports/status.txt").exists(),
   "a full mirror still leaves work out", out)

(kit / "memory/context").mkdir(parents=True)
(kit / "memory/context/sharing-policy.json").write_text(json.dumps({"blocked_root_patterns": [str(icloud.name)]}))
rc, out = lib("deliver", str(note), "--kind", "research", "--name", "blocked.txt", "--no-date")
ok(rc == 0 and not (icloud / "Research/blocked.txt").exists(), "a mirror the sharing policy blocks gets nothing", out)
rc, out = lib("mirror")
ok(rc != 0 and "blocked pattern" in out, "mirror says why it refused", out)
rc, out = lib("fetch", ids["sermon"], "--to-phone")
ok(rc != 0 and "isn't allowed" in out, "fetch --to-phone refuses a blocked mirror", out)
(kit / "memory/context/sharing-policy.json").unlink()

# ---- ask rules
sys.path.insert(0, str(REPO / "shared"))
import kit_setup  # noqa: E402
for rule in ("Bash(kit-library mirror *)", "Bash(kit-library fetch *)"):
    ok(rule not in kit_setup.ALLOW and rule in kit_setup.ASK, f"{rule} asks")
ok("Bash(kit-library deliver *)" in kit_setup.ALLOW, "deliver stays allowed")
ok(set(kit_setup.RETIRED_ALLOW) >= {"Bash(kit-library mirror *)", "Bash(kit-library fetch *)"},
   "the old allow rules are retired on activate")

# ---- kit-textback
os.environ.update(HOME=str(home), KIT_DIR=str(kit))
loader = importlib.machinery.SourceFileLoader("kit_textback", str(REPO / "shared/bin/kit-textback"))
spec = importlib.util.spec_from_loader("kit_textback", loader)
tb = importlib.util.module_from_spec(spec)
loader.exec_module(tb)
tb.CONFIG.parent.mkdir(parents=True, exist_ok=True)
tb.CONFIG.write_text('export TEXTBACK="on"   # answer texts\nTEXTBACK_MODEL=haiku # cheap\n'
                     'TEXTBACK_MAX_PER_HOUR=lots\nIMESSAGE_TO="me@example.com"\n')
c = tb.read_config()
ok(c.get("TEXTBACK") == "on" and c.get("TEXTBACK_MODEL") == "haiku", "config: export and # comments", str(c))
ok(tb.max_per_hour(c) == 30, "a rate limit that isn't a number falls back to 30")

cmd = tb.ask_command("q", "sonnet")
allowed = cmd[cmd.index("--allowedTools") + 1:cmd.index("--disallowedTools")]
ok("Glob" not in allowed and "Grep" not in allowed, "no bare Glob or Grep for texted questions", str(allowed))
ok(all(f"Read(~/Claude/Agents/kit/{d}/**)" in cmd for d in tb.TEXT_CLOSED), "every closed folder denied")
ok(set(tb.TEXT_CLOSED) == set(json.loads(subprocess.run(
    [sys.executable, "-c", "import importlib.machinery as m,json;mod=m.SourceFileLoader('l',%r).load_module();"
     "print(json.dumps(mod.TEXT_CLOSED))" % str(LIB)], capture_output=True, text=True, env=ENV).stdout)),
   "kit-library and kit-textback close the same folders")

# kit send proposes; nothing leaves until "kit yes CODE"
sent = []
tb.send_file = lambda path, cfg: sent.append(path) or True
tb.library = lambda args: ({"title": "Grace"}, None) if args[0] == "show" else (None, "no")
ctx = tb.context(c)
ctx["state"] = {"last_ids": {"1": int(ids["sermon"])}}
reply = tb.cmd_send(["1"], ctx)
ok("kit yes" in reply and not sent, "kit send asks for a code first", reply)
code = reply.split("kit yes ")[1].split()[0]
ok("library-send" in json.loads(tb.PENDING.read_text())[code]["kind"], "the send waits as a pending change")

# the dry run: no change, no send, no pending action run
tb.DRY = True
r = tb.run(tb.tool("todo") + ["call", "the", "bank"])
ok(r[0] == 0 and "would run: todo call the bank" in r[1], "dry run describes a to-do instead of adding it", str(r))
ok(not tb.changes(tb.tool("kit-dates") + ["--json", "--days", "1"]), "dry run still reads")
reply = tb.cmd_yes([code], ctx)
ok("test: would confirm" in reply and not sent, "dry run doesn't carry out a waiting code", reply)
ok(code in json.loads(tb.PENDING.read_text()), "dry run leaves the code waiting")
ok("nothing was" in tb.propose("x", {}, "Do a thing.") and len(json.loads(tb.PENDING.read_text())) == 1,
   "dry run saves no new code")
ok(tb.send("hello", c) == "Kit · hello", "dry run sends nothing")
tb.DRY = False
reply = tb.cmd_yes([code], ctx)
ok(bool(sent) and "Sent" in reply, "kit yes CODE sends it", reply)

# state is saved before a text is answered
saved = []
tb.APP = tmp                                  # "built"
tb.fetch = lambda since, chats, wait: (11, [{"rowid": 11, "date": __import__("time").time(), "text": "kit help",
                                             "service": "iMessage"}], None)
tb.save_state = lambda st: saved.append(dict(st))
tb.answer = lambda *a: (_ for _ in ()).throw(RuntimeError("crash while answering"))
st = {"last_rowid": 10, "since_time": 0}
try:
    tb.check(st, c, ctx, wait=0)
except RuntimeError:
    pass
ok(saved and saved[-1]["last_rowid"] == 11, "state saved before answering, so a crash never answers twice",
   str(saved))

print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)

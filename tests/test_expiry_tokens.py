#!/usr/bin/env python3
"""Tests for credential expiry in kit-expiry: a "keychain" item's date from its Keychain entry's metadata (the
comment's date, else a lifetime from when the entry was last changed, else a date set by hand), `kit-expiry
tokens` (the credentials connector-guard.json names, tracked or not, and --add), and the brief listing a token
inside its warning window, with its to-do. A stand-in `security` plays the Keychain and records its arguments,
so the test also checks that no value is ever asked for (-w or -g never appears). Runs on any OS.

  python3 tests/test_expiry_tokens.py
"""
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-expiry"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-expiry-tokens-"))
KIT = TMP / "kit"
(KIT / "memory/context").mkdir(parents=True)
FAKE = TMP / "bin"
FAKE.mkdir()
CALLS = TMP / "calls.log"
TODAY = dt.date.today()
SOON = TODAY + dt.timedelta(days=9)
FAR = TODAY + dt.timedelta(days=200)
MOD = TODAY - dt.timedelta(days=80)          # stored 80 days ago: a 90-day token has 10 left

# The stand-in Keychain: three entries. JIRA has a dated comment, CONF a plain comment and an old change date,
# PPMX no comment at all. Anything else isn't there (exit 44, as `security` does).
entries = {
    "JIRA_PERSONAL_TOKEN": (f"expires {SOON.isoformat()}", TODAY),
    "CONFLUENCE_TOKEN": ("work wiki", MOD),
    "PPMX_TOKEN": (None, TODAY - dt.timedelta(days=5)),
}
script = ["#!/usr/bin/env python3", "import sys, json",
          f"open({str(CALLS)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')",
          f"E = json.loads({json.dumps(json.dumps({k: [c, m.strftime('%Y%m%d')] for k, (c, m) in entries.items()}))})",
          "a = sys.argv[1:]",
          "if '-w' in a or '-g' in a: sys.exit(99)",
          "name = a[a.index('-s') + 1] if '-s' in a else ''",
          "if name not in E: sys.exit(44)",
          "c, m = E[name]",
          "print('keychain: \"/tmp/login.keychain-db\"')",
          "print('attributes:')",
          "print('    \"acct\"<blob>=\"alex\"')",
          "print('    \"cdat\"<timedate>=0x00  \"' + m + '120000Z\\\\000\"')",
          "print('    \"icmt\"<blob>=' + ('<NULL>' if c is None else '\"' + c + '\"'))",
          "print('    \"mdat\"<timedate>=0x00  \"' + m + '120000Z\\\\000\"')",
          "print('    \"svce\"<blob>=\"' + name + '\"')"]
(FAKE / "security").write_text("\n".join(script) + "\n")
os.chmod(FAKE / "security", 0o755)
(FAKE / "todo").write_text("")

(KIT / "memory/context/connector-guard.json").write_text(json.dumps({
    "allowed_servers": ["jira", "wiki", "ppmx"],
    "credential_env": {"jira": ["JIRA_PERSONAL_TOKEN"], "wiki": ["CONFLUENCE_TOKEN"], "ppmx": ["PPMX_TOKEN"]}}))

# Run kit-expiry as macOS would: a small runner that sets kit_secrets.STORE to the Keychain and puts the stand-in
# `security` first on the PATH, then runs the tool's main().
RUNNER = TMP / "run.py"
RUNNER.write_text(f"""import importlib.machinery, importlib.util, sys
sys.path.insert(0, {str(REPO / 'shared')!r})
import kit_secrets
kit_secrets.STORE = "Keychain"
loader = importlib.machinery.SourceFileLoader("kit_expiry", {str(TOOL)!r})
spec = importlib.util.spec_from_loader("kit_expiry", loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)
mod.TODO = __import__("pathlib").Path({str(FAKE / 'todo')!r})
sys.exit(mod.main(sys.argv[1:]))
""")
ENV = dict(os.environ, KIT_DIR=str(KIT), PATH=f"{FAKE}{os.pathsep}{os.environ.get('PATH', '')}",
           PYTHONDONTWRITEBYTECODE="1")


def run(*args):
    r = subprocess.run([sys.executable, str(RUNNER), *args], capture_output=True, text=True, env=ENV, timeout=60)
    return r.returncode, r.stdout, r.stderr


# ---- tokens: what the connectors name, before anything is tracked
rc, out, err = run("tokens")
ok(rc == 0, "tokens runs", err)
ok("untracked JIRA_PERSONAL_TOKEN" in out and "used by jira" in out, "tokens lists an untracked credential", out)
ok("kit-claude-token" not in out, "tokens leaves out kit-claude-token when it isn't stored", out)
ok(not (KIT / "expiry.json").exists(), "tokens without --add writes nothing")

rc, out, err = run("tokens", "--add", "--warn", "14")
cfg = json.loads((KIT / "expiry.json").read_text())
items = {i["entry"]: i for i in cfg["items"]}
ok(rc == 0 and set(items) == {"JIRA_PERSONAL_TOKEN", "CONFLUENCE_TOKEN", "PPMX_TOKEN"},
   "tokens --add tracks each credential the connectors name", out + err)
ok(all(i["check"] == "keychain" and i["side"] == "work" and i["warn_days"] == 14 for i in items.values()),
   "tracked tokens are Keychain items, work, with the warning window given", items)
rc, out, _ = run("tokens", "--add")
ok("Nothing to add" in out and len(json.loads((KIT / "expiry.json").read_text())["items"]) == 3,
   "tokens --add is safe to repeat", out)

# ---- dates from the metadata
items["CONFLUENCE_TOKEN"]["lifetime"] = "90d"
(KIT / "expiry.json").write_text(json.dumps(cfg, indent=2))
rc, out, _ = run("--json")
rows = {r["name"]: r for r in json.loads(out)}
by_entry = {i["entry"]: rows[i["name"]] for i in cfg["items"]}
ok(by_entry["JIRA_PERSONAL_TOKEN"]["date"] == SOON.isoformat() and by_entry["JIRA_PERSONAL_TOKEN"]["state"] == "SOON",
   "the date in the entry's comment is read, and inside the window it's SOON", by_entry["JIRA_PERSONAL_TOKEN"])
want = (MOD + dt.timedelta(days=90)).isoformat()
ok(by_entry["CONFLUENCE_TOKEN"]["date"] == want and "from when it was stored" in by_entry["CONFLUENCE_TOKEN"]["note"],
   "with no date in the comment, the lifetime counts from the entry's last change", by_entry["CONFLUENCE_TOKEN"])
ok(by_entry["PPMX_TOKEN"]["date"] is None and by_entry["PPMX_TOKEN"]["state"] == "UNKNOWN"
   and "-j" in by_entry["PPMX_TOKEN"]["note"], "no comment and no lifetime: unknown, saying how to fix it",
   by_entry["PPMX_TOKEN"])

rc, out, err = run("set", "PPMX_TOKEN", FAR.isoformat())
rc, out, _ = run("--json")
row = [r for r in json.loads(out) if "PPMX_TOKEN" in r["name"]][0]
ok(row["date"] == FAR.isoformat() and row["state"] == "ok", "kit-expiry set gives a Keychain item a fallback date", row)
rc, out, err = run("renewed", "JIRA_PERSONAL_TOKEN")
ok(rc == 1 and "Keychain" in err, "renewed without --to points at storing the token with its date", err)

# ---- the brief: a token inside its window shows, with a to-do; the far one doesn't
rc, out, err = run("brief", "--queue")
ok(rc == 0 and "[work] DUE" in out and "JIRA_PERSONAL_TOKEN" in out, "the brief lists a token due soon", out + err)
ok("CONFLUENCE_TOKEN" in out, "the brief lists the token whose lifetime runs out soon", out)
ok("PPMX_TOKEN" not in out, "the brief leaves out a token that isn't due", out)
cfg = json.loads((KIT / "expiry.json").read_text())
ok(any(i.get("queued") for i in cfg["items"] if i["entry"] == "JIRA_PERSONAL_TOKEN"),
   "the brief's --queue records the to-do once", cfg)
rc, out, _ = run("--check", "--health")
ok("SOON" in out and "JIRA_PERSONAL_TOKEN" in out, "the health check sees the token too", out)

# ---- never a value
calls = CALLS.read_text()
ok(calls and all("-w" not in ln.split() and "-g" not in ln.split() for ln in calls.splitlines()),
   "the Keychain is only asked for attributes, never a value", calls)

print(f"\n{P} passed, {F} failed")
sys.exit(1 if F else 0)

#!/usr/bin/env python3
"""Tests for kit-config (shared/kit_config.py): what a snapshot covers, credentials left out (by key, by value, and
whole files by name), private permissions, an unchanged state kept as one snapshot, diffs, restore previewing first,
taking a snapshot of the state before and keeping the current credential lines, Kit's permission rules restored only
with --include-permissions and the owner's own rules never touched, prune, refused ids, the CLI, and the hooks in
the installers and kit-update. Everything happens in a fake Kit folder under a temp HOME.

  python3 tests/test_kit_config.py
"""
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-config-"))
HOME = TMP / "home"
KIT = HOME / "Claude/Agents/kit"
SETTINGS = HOME / ".claude/settings.json"
os.environ.update(HOME=str(HOME), USERPROFILE=str(HOME), KIT_DIR=str(KIT), PYTHONDONTWRITEBYTECODE="1",
                  KIT_CLAUDE_SETTINGS=str(SETTINGS))
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / "shared"))
import kit_config as kc  # noqa: E402
import kit_settings as ks  # noqa: E402

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
    r = subprocess.run([sys.executable, str(REPO / "shared/bin/kit-config"), *args], capture_output=True, text=True,
                       env=os.environ, timeout=60)
    return r.returncode, r.stdout + r.stderr


# The fake Kit folder.
CTX = KIT / "memory/context"
for d in (CTX, KIT / ".install/shared/morning", KIT / ".install/logs", HOME / ".claude"):
    d.mkdir(parents=True, exist_ok=True)
CONFIG = KIT / ".install/shared/morning/config"
CONFIG.write_text('OWNER_NAME="Sam"\nCOST_WARN_PCT="80"\nFAKE_API_TOKEN="zz-secret-value-987"\n'
                  'PPMX_TOKEN_ENV="PPMX_PAT"\nEMPTY_TOKEN=""\n', encoding="utf-8")
for name in ("calendar.md", "library.md"):
    shutil.copy(REPO / "kit/memory/context" / name, CTX / name)
(CTX / "my-notes.md").write_text("- **Note:** a memory note, not a setup file\n", encoding="utf-8")
(CTX / "audit.md").write_text("# Audit\n- **Reviewers:** the security lead\n- **Reviewer:** token ghp_" + "a" * 36 + "\n- **Working hours:** 09:00-17:00\n", encoding="utf-8")
shutil.copy(REPO / "kit/memory/context/audit.md", KIT / "audit-shipped.md")  # unrelated file, not covered
shutil.copy(REPO / "kit/memory/context/connector-guard.json", CTX / "connector-guard.json")
DB_PW, DB_PW_NEW = "zz-db-" + "pass-123", "zz-db-" + "pass-NEW"  # fixtures, built so no literal sits in the file
(CTX / "sharing-db.json").write_text(json.dumps({"host": "db.example", "password": DB_PW,
                                                 "credential_env": "KIT_DB", "enabled": True}, indent=1), encoding="utf-8")
(CTX / "credentials.json").write_text('{"x": 1}\n', encoding="utf-8")
shutil.copy(REPO / "kit/models.json", KIT / "models.json")
(KIT / ".install/setup-wizard.json").write_text('{"later": [], "skipped": []}\n', encoding="utf-8")
(KIT / ".install/manifest.json").write_text(json.dumps({"settings": {"added": {"allow": ["Bash(kit-test *)"], "ask": []}}}),
                                            encoding="utf-8")
SETTINGS.write_text(json.dumps({"permissions": {"allow": ["Bash(kit-test *)", "Bash(owner-tool *)"],
                                                "ask": ["Bash(rm *)"]}, "theme": "dark"}, indent=2), encoding="utf-8")

# ---------------------------------------------------------------------------------------------------------------
cov = dict(kc.covered(KIT))
ok(ks.CONFIG_REL in cov and "memory/context/connector-guard.json" in cov and "models.json" in cov
   and ".install/setup-wizard.json" in cov and "memory/context/calendar.md" in cov, "covers the configs", cov)
ok("memory/context/my-notes.md" not in cov and "audit-shipped.md" not in cov, "leaves out memory notes and other files")

r = kc.snapshot(KIT, note="first")
S1 = r["id"]
ok(r["new"] and kc.ID_RE.match(S1), "a snapshot is taken", r)
d = KIT / ".install/snapshots" / S1
stored = (d / "files" / ks.CONFIG_REL).read_text()
ok("zz-secret-value-987" not in stored and kc.OMIT + "FAKE_API_TOKEN" in stored, "a credential line is left out", stored)
ok('PPMX_TOKEN_ENV="PPMX_PAT"' in stored and 'EMPTY_TOKEN=""' in stored, "a credential's name and an empty one stay")
db = (d / "files/memory/context/sharing-db.json").read_text()
ok("zz-db-pass-123" not in db and '"credential_env": "KIT_DB"' in db and '"enabled": true' in db,
   "a credential key in JSON is left out; names and flags stay", db)
ok("memory/context/credentials.json" in r["skipped"], "a file whose name says secrets is skipped", r["skipped"])
aud = (d / "files/memory/context/audit.md").read_text() if (d / "files/memory/context/audit.md").exists() else ""
ok("memory/context/audit.md" not in r["skipped"] and kc.OMIT_LINE in aud and "**Reviewers:**" in aud,
   "a setup file keeps its other lines; only the credential-shaped line is left out", aud)
kit_aud = KIT / "memory/context/audit.md"
ok(all(not ks.looks_secret(x) for x in aud.splitlines()), "nothing credential-shaped is stored")
ok(kc._merge_lines(aud, kit_aud.read_text()) == kit_aud.read_text(), "a restore puts the current line back in its place")
ok(kc.OMIT_LINE not in kc._merge_lines(aud, ""), "with no current file, the left-out line is dropped")
allfiles = "".join(p.read_text(errors="ignore") for p in d.rglob("*") if p.is_file())
ok("zz-secret" not in allfiles and "zz-db-pass" not in allfiles and "ghp_" not in allfiles, "no credential anywhere in it")
m = json.loads((d / "manifest.json").read_text())
ok(m["note"] == "first" and all(len(f["sha256"]) == 64 for f in m["files"].values()), "a manifest with a SHA-256 per file")
ok(m["files"][ks.CONFIG_REL]["omitted"] == ["FAKE_API_TOKEN"], "and what was left out")
ok(m["permissions"] == {"allow": ["Bash(kit-test *)"], "ask": ["Bash(rm *)"], "deny": []},
   "Kit's own rules only (its manifest's and its ask list), not the owner's", m["permissions"])
if os.name != "nt":
    ok(stat.S_IMODE(d.stat().st_mode) == 0o700 and stat.S_IMODE((d / "manifest.json").stat().st_mode) == 0o600
       and stat.S_IMODE((d / "files" / ks.CONFIG_REL).stat().st_mode) == 0o600, "private: 0700 folders, 0600 files")

r = kc.snapshot(KIT, note="again")
ok(not r["new"] and r["id"] == S1, "an unchanged state isn't snapshotted twice")
r = kc.snapshot(KIT, note="forced", force=True)
ok(r["new"] and r["id"] != S1, "--force takes one anyway")

# Diff and restore.
CONFIG.write_text(CONFIG.read_text().replace('COST_WARN_PCT="80"', 'COST_WARN_PCT="65"')
                  .replace("zz-secret-value-987", "zz-secret-value-NEW") + 'NEW_KEY="x"\n', encoding="utf-8")
(CTX / "sharing-db.json").write_text(json.dumps({"host": "db2.example", "password": DB_PW_NEW,
                                                 "credential_env": "KIT_DB", "enabled": True}, indent=1), encoding="utf-8")
dd = kc.diff(KIT, S1)
ok('-COST_WARN_PCT="80"' in dd and '+COST_WARN_PCT="65"' in dd and "db2.example" in dd, "diff against now", dd)
ok("zz-secret-value" not in dd and "zz-db-pass" not in dd, "the diff shows no credential")
before = CONFIG.read_bytes()
code, out = cli("restore", S1)
ok(code == 0 and "would change" in out and CONFIG.read_bytes() == before, "restore without --yes only previews", out)
n0 = len(kc.ids(KIT))
code, out = cli("restore", S1, "--yes")
txt = CONFIG.read_text()
ok(code == 0 and 'COST_WARN_PCT="80"' in txt and 'NEW_KEY' not in txt, "restore --yes writes the snapshot back", out)
ok('FAKE_API_TOKEN="zz-secret-value-NEW"' in txt, "and keeps the current credential line, never an old one", txt)
dbnow = json.loads((CTX / "sharing-db.json").read_text())
ok(dbnow["host"] == "db.example" and dbnow["password"] == "zz-db-pass-NEW", "JSON restored, its current credential kept")
ok(len(kc.ids(KIT)) == n0 + 1, "a snapshot of the state before was taken")
undo = kc.ids(KIT)[-1]
ok(kc.manifest(KIT, undo)["note"] == f"before restoring {S1}", "named for the restore", kc.manifest(KIT, undo))
kc.restore(KIT, undo)
ok('COST_WARN_PCT="65"' in CONFIG.read_text() and "NEW_KEY" in CONFIG.read_text(), "restoring that snapshot undoes it")
models_before = (KIT / "models.json").read_bytes()
kc.restore(KIT, S1)
ok((KIT / "models.json").read_bytes() == models_before, "a JSON file with the same data isn't rewritten")
r = kc.restore(KIT, S1)
ok(r["ok"] and not r["written"] and "Nothing to restore" in r["message"], "restoring a matching state writes nothing")

# Permissions: only with --include-permissions, and only Kit's own rules.
SETTINGS.write_text(json.dumps({"permissions": {"allow": ["Bash(owner-tool *)", "Bash(owner-two *)"], "ask": ["Bash(rm *)"]},
                                "theme": "dark"}, indent=2), encoding="utf-8")
plan = kc.plan_restore(KIT, S1)
ok(plan["permissions"] is None and "--include-permissions" in plan["diff"], "permissions aren't restored by default")
code, out = cli("restore", S1, "--yes", "--include-permissions")
sj = json.loads(SETTINGS.read_text())
ok(code == 0 and "Bash(kit-test *)" in sj["permissions"]["allow"], "--include-permissions puts Kit's rule back", out)
ok("Bash(owner-tool *)" in sj["permissions"]["allow"] and "Bash(owner-two *)" in sj["permissions"]["allow"]
   and sj["permissions"]["ask"] == ["Bash(rm *)"] and sj["theme"] == "dark", "the owner's own rules and settings untouched", sj)

# Prune, ids, and the CLI.
for i in range(5):
    kc.snapshot(KIT, note=f"n{i}", force=True, prune_after=False)
total = len(kc.ids(KIT))
gone = kc.prune(KIT, 3)
ok(len(gone) == total - 3 and len(kc.ids(KIT)) == 3 and S1 in gone, "prune keeps the newest N", (total, gone))
(KIT / ".install/snapshots/not-a-snapshot").mkdir()
kc.prune(KIT, 1)
ok((KIT / ".install/snapshots/not-a-snapshot").is_dir(), "prune removes only folders named like a snapshot")
CONFIG.write_text(CONFIG.read_text() + 'SNAPSHOT_KEEP="2"\n', encoding="utf-8")
for i in range(3):
    kc.snapshot(KIT, note=f"k{i}", force=True)
ok(len(kc.ids(KIT)) == 2, "SNAPSHOT_KEEP prunes after each new snapshot")
for bad in ("../../etc", "20990101-000000", "x", ""):
    try:
        kc.check_id(KIT, bad)
        ok(False, f"id {bad!r} refused")
    except kc.Error:
        ok(True, f"id {bad!r} refused")
code, out = cli("show", "../x")
ok(code == 1 and "no snapshot" in out, "the CLI refuses a bad id with exit 1", out)
code, out = cli("list")
ok(code == 0 and kc.ids(KIT)[-1] in out, "kit-config list", out)
code, out = cli("show", kc.ids(KIT)[-1])
ok(code == 0 and "left out: FAKE_API_TOKEN" in out and "skipped memory/context/credentials.json" in out, "kit-config show", out)
code, out = cli("diff", kc.ids(KIT)[0], kc.ids(KIT)[-1])
ok(code == 0, "kit-config diff ID ID2", out)
code, out = cli("snapshot", "--note", "ghp_" + "b" * 36)
ok(code == 1 and "credential" in out, "a credential-shaped note is refused", out)
code, out = cli("prune", "--keep", "0")
ok(code == 2, "prune --keep 0 is a usage error")

# The hooks: the installers and kit-update take a snapshot first, only when kit-config is installed.
mac = (REPO / "platform/mac/install.sh").read_text()
win = (REPO / "platform/windows/install.ps1").read_text()
upd = (REPO / "shared/bin/kit-update").read_text()
ok("kit-config" in mac and mac.index("kit-config") < mac.index("kit_setup.py\" check"), "install.sh snapshots first")
ok("kit-config" in win and win.index("kit-config") < win.index('foreach ($step in @("check"'), "install.ps1 snapshots first")
ok("pre_snapshot(" in upd, "kit-update snapshots before it changes anything")
ok("kit-config" in mac.split("for tool in", 1)[1].split("\n", 1)[0], "install.sh links kit-config onto the PATH")
ok('"kit-config"' in win, "install.ps1 links kit-config too")

print(f"\n{P} passed, {F} failed")
if F == 0 and not os.environ.get("KIT_KEEP_TMP"):
    shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if F else 0)

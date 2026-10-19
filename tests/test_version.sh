#!/bin/bash
# test_version.sh: version stamp, install history, release notes, kit-version, and kit-update's
# version preview, in a temp HOME with temp git clones. Run from anywhere: bash tests/test_version.sh
cd "$(dirname "$0")/.." || exit 1
exec python3 - "$PWD" <<'PY'
import json, os, pathlib, shutil, subprocess, sys, tempfile
SRC = pathlib.Path(sys.argv[1])
PASS = FAIL = 0
def ok(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("ok  ", name)
    else:
        FAIL += 1; print("FAIL", name, ("-- " + str(detail)[:300]) if detail else "")
def sh(cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
def git(repo, *a):
    return sh(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a])

tmp = pathlib.Path(tempfile.mkdtemp())
home = tmp / "home"; home.mkdir()
env = dict(os.environ, HOME=str(home), KIT_OWNER="Tester")
origin = tmp / "origin.git"
sh(["git", "init", "-q", "--bare", "-b", "main", str(origin)])
work = tmp / "work"
# a copy of the package as it is now (including uncommitted files), committed in a fresh repo
shutil.copytree(SRC, work, ignore=shutil.ignore_patterns(".git", "__pycache__"))
git(work, "init", "-q", "-b", "main"); git(work, "add", "-A"); git(work, "commit", "-qm", "base")
git(work, "remote", "add", "origin", str(origin)); git(work, "push", "-q", "origin", "main")
kit = home / "Claude/Agents/kit"; inst = kit / ".install"
def install(repo=work):
    return sh([sys.executable, str(repo / "shared/kit_setup.py"), "scaffold"], env=env)
def vj():
    return json.loads((inst / "VERSION.json").read_text())
notes = kit / "briefs/kit-release-notes.md"

r = install()
ok(r.returncode == 0, "first install runs", r.stderr)
v = vj(); head = git(work, "rev-parse", "HEAD").stdout.strip()
ok(v["version"] == (SRC / "VERSION").read_text().strip() and v["commit"] == head, "VERSION.json has version and commit", v)
ok(v["previous"] is None and v["history"] == [], "first install has no previous or history", v)
ok(not notes.exists(), "no release notes on a first install")
ok((inst / "VERSION").exists() and (inst / "CHANGELOG.md").exists(), "VERSION and CHANGELOG copied into .install")

r = install(); v = vj()
ok(v["previous"]["commit"] == head and len(v["history"]) == 1, "reinstall records previous and history", v)
ok(not notes.exists(), "no release notes on an identical reinstall")

# a commit change with a new agent and a new command
(work / "kit/agents/zz-test-agent.md").write_text("---\nname: zz-test-agent\n---\n")
(work / "shared/bin/kit-zztest").write_text("#!/bin/sh\n")
git(work, "add", "-A"); git(work, "commit", "-qm", "Add a test agent and command")
r = install(); text = notes.read_text() if notes.exists() else ""
ok(notes.exists(), "release notes written on a commit change", r.stdout)
ok("Add a test agent and command" in text, "notes list the commit subjects", text)
ok("`zz-test-agent`" in text and "`kit-zztest`" in text, "notes list new agents and commands", text)

# a version change with a changelog section
notes.write_text("Shown in the brief for 2026-01-01.\n")
(work / "VERSION").write_text("9.9.0\n")
cl = (work / "CHANGELOG.md").read_text().replace("## [Unreleased]", "## [Unreleased]\n\n## [9.9.0] - 2026-12-31\n\n### Added\n- Testing release notes.", 1)
(work / "CHANGELOG.md").write_text(cl)
git(work, "add", "-A"); git(work, "commit", "-qm", "Release 9.9.0")
r = install(); text = notes.read_text()
ok(vj()["version"] == "9.9.0" and vj()["previous"]["version"] != "9.9.0", "version change recorded", vj())
ok("## [9.9.0]" in text and "Testing release notes." in text, "notes carry the changelog section", text)
ok("[1.4.0]" not in text, "notes leave out older versions", text)

# a rerun from the installed copy (not a git repo) keeps the commit and writes no notes
notes.write_text("Shown in the brief for 2026-01-02.\n")
r = install(inst); v = vj()
ok(r.returncode == 0 and v["commit"] == git(work, "rev-parse", "HEAD").stdout.strip(), "rerun from .install keeps the commit", v)
ok(notes.read_text().startswith("Shown in the brief"), "no new notes from a rerun of the same version")

# history is capped
data = vj(); data["history"] = [{"version": "0", "commit": "x", "installed": str(i)} for i in range(30)]
(inst / "VERSION.json").write_text(json.dumps(data))
install(); ok(len(vj()["history"]) == 20, "history keeps the last 20", len(vj()["history"]))

# the morning prompt step
prompt = (SRC / "shared/morning/prompt.md").read_text()
ok("kit-release-notes.md" in prompt and "What changed in Kit" in prompt, "morning prompt has the release-notes step")

# kit-version
kv = [sys.executable, str(SRC / "shared/bin/kit-version")]
r = sh(kv, env=dict(env, KIT_REPO=str(work)))
ok(r.returncode == 0 and "Kit 9.9.0" in r.stdout, "kit-version prints the installed version", r.stdout + r.stderr)
r = sh(kv + ["--json", "--history"], env=dict(env, KIT_REPO=str(work)))
j = json.loads(r.stdout)
ok(j["installed"]["version"] == "9.9.0" and j["history"], "kit-version --json --history", r.stdout)

# kit-update preview shows old -> new version
up = tmp / "upstream"
sh(["git", "clone", "-q", str(origin), str(up)])
git(work, "push", "-q", "origin", "main")
git(up, "pull", "-q")
(up / "VERSION").write_text("9.10.0\n"); git(up, "commit", "-qam", "Bump"); git(up, "push", "-q", "origin", "main")
r = sh([sys.executable, str(SRC / "shared/bin/kit-update")], env=dict(env, KIT_REPO=str(work)))
ok("Version: 9.9.0 -> 9.10.0" in r.stdout, "kit-update preview shows the version change", r.stdout + r.stderr)
r = sh(kv + ["--check"], env=dict(env, KIT_REPO=str(work)))
ok("GitHub is 1 commit(s) ahead" in r.stdout, "kit-version --check sees GitHub ahead", r.stdout)

shutil.rmtree(tmp)
print(f"version tests: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
PY

#!/bin/bash
# test_models.sh: model routing phase 1 (models.json, per-agent files, kit-models check and apply).
# Run from anywhere: bash tests/test_models.sh
cd "$(dirname "$0")/.." || exit 1
REPO="$(pwd)"
exec python3 - "$REPO" <<'PY'
import json, os, pathlib, shutil, subprocess, sys, tempfile
repo = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(repo / "shared"))
import kit_models as km
PASS = FAIL = 0
def ok(cond, name, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print("ok  ", name)
    else: FAIL += 1; print("FAIL", name, detail)

tmp = pathlib.Path(tempfile.mkdtemp())
kit = tmp / "kit"
(kit / "agents").mkdir(parents=True)
(kit / ".install/shared/morning").mkdir(parents=True)
for a in ("gateway", "reviewer", "meeting-scribe"):
    shutil.copy(repo / f"kit/agents/{a}.md", kit / f"agents/{a}.md")
(kit / "agents/no-model.md").write_text("---\nname: no-model\ndescription: x\n---\n\nBody\n")
shutil.copy(repo / "kit/models.json", kit / "models.json")
env = dict(os.environ, KIT_DIR=str(kit))
cli = [sys.executable, str(repo / "shared/bin/kit-models")]
def run(*a):
    return subprocess.run(cli + list(a), capture_output=True, text=True, env=env)
def cfg():
    return km.load(kit)
def write(obj):
    (kit / "models.json").write_text(json.dumps(obj))
base = json.loads((repo / "kit/models.json").read_text())

# defaults
c = cfg()
r = km.resolve_agent(c, "reviewer")
ok(r["model"] == "opus" and r["source"] == "default_profile", "default is deep (opus)", r)
ok(km.resolve_run(c, "weekly")["model"] == "opus", "runs default to opus")
shutil.move(str(kit / "models.json"), str(tmp / "m.json"))
r = km.resolve_agent(cfg(), "reviewer")
ok(r["model"] == "opus" and "built-in" in r["source"], "no config falls back to built-in opus", r)
shutil.move(str(tmp / "m.json"), str(kit / "models.json"))

# precedence
b = json.loads(json.dumps(base)); b["agents"] = {"gateway": "fast", "meeting-scribe": "standard"}
b["runs"] = {"weekly": "standard"}; write(b)
c = cfg()
ok(km.resolve_agent(c, "gateway")["model"] == "haiku", "combined agents map applies")
ok(km.resolve_run(c, "weekly")["model"] == "sonnet" and km.resolve_run(c, "morning")["model"] == "opus",
   "runs map applies per run")
(kit / "models").mkdir()
(kit / "models/meeting-scribe.json").write_text(json.dumps({"profile": "fast"}))
c = cfg()
r = km.resolve_agent(c, "meeting-scribe")
ok(r["model"] == "haiku" and r["source"] == "models/meeting-scribe.json", "per-agent file wins over combined", r)
r = km.resolve_agent(c, "meeting-scribe", override="deep")
ok(r["model"] == "opus" and "override" in r["source"], "per-run profile override wins", r)
r = km.resolve_agent(c, "gateway", override="sonnet")
ok(r["model"] == "sonnet", "per-run model override wins", r)
try:
    km.resolve_agent(c, "gateway", override="gpt-4o"); ok(False, "bad override refused")
except km.ConfigError:
    ok(True, "bad override refused")
b2 = json.loads(json.dumps(b)); b2["default_profile"] = "standard"; write(b2)
ok(km.resolve_agent(cfg(), "reviewer")["model"] == "sonnet", "changing default_profile changes the default")
write(b)

# org profile ceiling
b3 = json.loads(json.dumps(b)); b3["org_profile"] = {"allowed_providers": []}; write(b3)
r = km.resolve_agent(cfg(), "gateway")
ok(r["model"] == "opus" and any("organization profile" in n for n in r["notes"]),
   "org profile ceiling refuses a provider", r)
write(b)

# phase-2 provider refused, with and without fallback
b4 = json.loads(json.dumps(b)); b4["agents"]["gateway"] = "local"; write(b4)
r = km.resolve_agent(cfg(), "gateway")
ok(r["model"] == "haiku" and r["profile"] == "fast" and any("phase" in n for n in r["notes"]),
   "phase-2 provider refused, uses its fallback", r)
b4["profiles"]["local"].pop("fallback"); write(b4)
r = km.resolve_agent(cfg(), "gateway")
ok(r["model"] == "opus" and any("default_profile" in n for n in r["notes"]),
   "phase-2 provider without fallback uses the default", r)
p = run("check")
ok(p.returncode == 0 and "warning" in p.stdout and "phase" in p.stdout, "check warns on a refused provider",
   p.stdout + p.stderr)

# check errors
b5 = json.loads(json.dumps(b)); b5["agents"]["nobody"] = "fast"; b5["agents"]["reviewer"] = "turbo"; write(b5)
p = run("check")
ok(p.returncode == 1 and "unknown agent 'nobody'" in p.stdout and "unknown profile 'turbo'" in p.stdout,
   "check flags unknown agents and profiles", p.stdout)
p = run("apply")
ok(p.returncode != 0 and "nothing was changed" in (p.stdout + p.stderr), "apply refuses a config with errors")
b6 = json.loads(json.dumps(b)); b6["runs"]["nightly"] = "fast"; write(b6)
ok(run("check").returncode == 1, "check flags an unknown run")
b7 = json.loads(json.dumps(b)); b7["profiles"]["deep"]["model"] = "gpt-4o"; write(b7)
ok(run("check").returncode == 1, "check flags a model Claude Code doesn't accept")
write(b)

# apply: dry run, real, idempotent, models.env, only the model line
before = {f.name: f.read_text() for f in (kit / "agents").glob("*.md")}
p = run("apply", "--dry-run")
ok(p.returncode == 0 and "would change gateway: inherit -> haiku" in p.stdout and "dry run" in p.stdout,
   "apply --dry-run shows the diff", p.stdout)
ok(before == {f.name: f.read_text() for f in (kit / "agents").glob("*.md")}, "dry run writes nothing")
ok(not (kit / ".install/shared/morning/models.env").exists(), "dry run writes no models.env")
p = run("apply")
ok(p.returncode == 0 and "originals in" in p.stdout, "apply writes and backs up", p.stdout + p.stderr)
g = (kit / "agents/gateway.md").read_text()
ok("\nmodel: haiku\n" in g and "model: inherit" not in g, "gateway model line set to haiku")
ok((kit / "agents/meeting-scribe.md").read_text().count("\nmodel: haiku\n") == 1, "per-agent file applied")
ok("\nmodel: opus\n" in (kit / "agents/reviewer.md").read_text(), "default agent set to opus")
nm = (kit / "agents/no-model.md").read_text()
ok(nm.startswith("---\nname: no-model\ndescription: x\nmodel: opus\n---"), "missing model line is added", nm)
strip = lambda t: "\n".join(l for l in t.split("\n") if not l.startswith("model:"))
ok(strip(before["gateway.md"]) == strip(g), "only the model line changed")
envtxt = (kit / ".install/shared/morning/models.env").read_text()
ok("MODEL_WEEKLY=sonnet" in envtxt and "MODEL_MORNING=opus" in envtxt and "MODEL_WORKLIST=opus" in envtxt,
   "models.env has the runs", envtxt)
backups = list((kit / ".install/backups").glob("models-*"))
ok(len(backups) == 1 and (backups[0] / "gateway.md").exists(), "backup holds the originals")
p = run("apply")
ok(p.returncode == 0 and "nothing to change" in p.stdout, "apply is idempotent", p.stdout)
ok(len(list((kit / ".install/backups").glob("models-*"))) == 1, "second apply makes no backup")

# show and resolve
p = run()
ok(p.returncode == 0 and "run:weekly" in p.stdout and "models/meeting-scribe.json" in p.stdout, "show lists sources")
p = run("resolve", "run:weekly", "--json")
ok(json.loads(p.stdout)["model"] == "sonnet", "resolve run:weekly")
p = run("--json")
ok(len(json.loads(p.stdout)) == 4 + len(km.RUN_MODES), "show --json lists agents and runs")

# the shipped template is valid and keeps public agents on inherit
write(base); shutil.rmtree(kit / "models")
ok(run("check").returncode == 0, "shipped models.json passes check")
ok(all("model: inherit" in f.read_text() for f in (repo / "kit/agents").glob("*.md")),
   "public agent templates still say model: inherit")
ex = json.loads((repo / "kit/models.example-routing.json").read_text())
names = {f.stem for f in (repo / "kit/agents").glob("*.md")}
ok(set(ex["agents"]) <= names and set(ex["agents"].values()) <= set(base["profiles"]),
   "example routing names real agents and profiles")
shutil.rmtree(tmp)
print(f"\nmodels tests: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
PY

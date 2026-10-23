#!/bin/bash
# Tests the monitors in run_alerts.py (roadmap F): agent drift three ways (monitor_drift.py), library
# freshness (monitor_library.py), and items waiting too long (monitor_waiting.py): alerts opened and
# cleared, one owner queue item per outage where the kind has one, follow-up drafts, the brief lines,
# the dashboard banners, kit-alerts (--only, drift --diff, check --dry-run), and that missing or broken
# files never fail the run. Synthetic Kit folders in a throwaway place; no model, no connector, no web,
# nothing real is touched.
#   bash tests/test_monitors.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'chmod -R u+rw "$S" 2>/dev/null; rm -rf "$S"' EXIT
export HOME="$S/home"
KIT="$HOME/Claude/Agents/kit"; export KIT_DIR="$KIT"
mkdir -p "$KIT/briefs" "$KIT/.install/logs" "$KIT/.install/shared/morning"
python3 - "$HERE" "$KIT" "$HOME" <<'PY'
import datetime as dt, json, os, pathlib, re, shutil, subprocess, sys, time, unicodedata
here, kit, home = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
briefs = kit / "briefs"
cfg = kit / ".install/shared/morning/config"
Q = kit / "QUEUE.md"
RA = here / "shared/morning/run_alerts.py"
KA = here / "shared/bin/kit-alerts"
P = F = 0

def ok(cond, name, detail=""):
    global P, F
    if cond: P += 1; print("ok  ", name)
    else: F += 1; print("FAIL", name, str(detail)[:600])

def config(text=""):
    cfg.write_text('OWNER_NAME="Alex"\n' + text)

def reset_queue(waiting="", owner=""):
    Q.write_text("# Queue\n\n## Alex\n\n- [ ] **Existing item** (added 01-Oct-2026)\n" + owner +
                 "\n## Kit\n\n- [ ] **Decide by Friday which font to use** (added 01-Sep-2026)\n\n"
                 "## Waiting on others\n" + waiting + "\n## Done\n")

def alerts(*extra, env=None, now=None):
    args = [sys.executable, str(RA), "--kit", str(kit), "--out", str(briefs / "alerts.txt"), "--no-dashboard", *extra]
    if now:
        args += ["--now", now]
    return subprocess.run(args, capture_output=True, text=True, env=dict(os.environ, **(env or {})), timeout=120)

def ka(*args):
    return subprocess.run([sys.executable, str(KA), *args], capture_output=True, text=True, timeout=120)

def state():
    try:
        return json.loads((briefs / "alerts.json").read_text())["alerts"]
    except Exception:
        return {}

def brief():
    try:
        return (briefs / "alerts.txt").read_text()
    except OSError:
        return ""

def items(pat):
    return len(re.findall(r"^- \[ \] \*\*" + pat, Q.read_text(), re.M))

def banner():
    import importlib.util
    spec = importlib.util.spec_from_file_location("dash", here / "shared/dashboard.py")
    d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
    return d.alerts_banner()

config()
reset_queue()

# ================================================================ drift
ship, live, inst = kit / ".install/kit/agents", kit / "agents", home / ".claude/agents"
for d in (ship, live, inst):
    d.mkdir(parents=True, exist_ok=True)
BODY = ("---\nname: {n}\ndescription: >-\n  The {n}.\ntools: Read\nmodel: {m}\n---\n\n"
        "You are the {n} on Kit's staff. Kit is {o}'s AI personal assistant.\nReport to {o}.\n")
for n in ("librarian", "scheduler"):
    (ship / f"{n}.md").write_text(BODY.format(n=n, m="inherit", o="{{OWNER}}"))
    (live / f"{n}.md").write_text(BODY.format(n=n, m="opus", o="Alex"))
    shutil.copy(live / f"{n}.md", inst / f"{n}.md")
(live / "my-own-agent.md").write_text("---\nname: my-own-agent\n---\nMine.\n")
shutil.copy(live / "my-own-agent.md", inst / "my-own-agent.md")

r = alerts("--only", "drift")
ok(r.returncode == 0 and not state(), "drift: owner name and model line only differ -> no alert", (r.stderr, state()))
ok(ka("drift", "--diff", "librarian").stdout.startswith("librarian: the live copy matches"), "drift --diff: in sync says so")

# owner inferred from the live copy when OWNER_NAME isn't set
cfg.write_text("")
alerts("--only", "drift")
ok(not state(), "drift: owner inferred from the live copy when OWNER_NAME is unset", state())
config()

# a real change in the live copy
(live / "librarian.md").write_text(BODY.format(n="librarian", m="opus", o="Alex") + "Also keep a reading list.\n")
r = alerts("--only", "drift")
st = state()
a = st.get("drift:shipped", {})
ok(a.get("agents") == ["librarian"] and "differs from the shipped version (librarian): review and sync" in a.get("reason", ""),
   "drift: shipped vs live differs after normalising -> alert listing the agent", (st, r.stderr))
ok(st.get("drift:installed", {}).get("agents") == ["librarian"], "drift: live vs installed differs -> doctor's check alerts", st)
ok(items(r"Review Kit's agents that differ from the shipped version, since \d\d-[A-Z][a-z]{2}-\d{4} \(kit-alerts drift\)\*\* \[work\]") == 1,
   "drift: one [work] queue item for the shipped drift", Q.read_text())
ok(items(r"Copy Kit's staff into ~/.claude/agents") == 1, "drift: one [work] queue item for the installed drift", Q.read_text())
ok("Drift alert: 1 live agent differs from the shipped version (librarian): review and sync (on your list; compare with kit-alerts drift --diff <agent>)." in brief(),
   "drift: brief line", brief())
ok("my-own-agent" not in json.dumps(st.get("drift:shipped", {})), "drift: an agent with no shipped copy is left alone")
alerts("--only", "drift")
ok(items(r"Review Kit's agents") == 1 and items(r"Copy Kit's staff") == 1, "drift: second run, no duplicate items")
d = ka("drift", "--diff", "librarian")
ok(d.returncode == 0 and "+Also keep a reading list." in d.stdout and "--- shipped/librarian.md" in d.stdout
   and "model:" not in "".join(l for l in d.stdout.splitlines(True) if l[:1] in "+-" and not l.startswith(("+++", "---")))
   and "{{OWNER}}" not in d.stdout and "Nothing was changed" in d.stdout,
   "drift --diff: unified diff of shipped vs live, owner filled in, no model-line noise", d.stdout)
ok(ka("drift", "--diff", "nobody").returncode == 1, "drift --diff: unknown agent exits 1")
ok((live / "librarian.md").read_text().endswith("reading list.\n"), "drift --diff: nothing overwritten")
kd = ka("drift")
ok("Drift alert" in kd.stdout and "Run alert" not in kd.stdout, "kit-alerts drift: shows the drift alerts", kd.stdout)
b = banner()
ok("<strong>Agent drift</strong>" in b and "librarian" in b, "drift: dashboard banner", b)
# installed brought up to date -> installed clears, shipped stays
shutil.copy(live / "librarian.md", inst / "librarian.md")
alerts("--only", "drift")
ok("drift:installed" not in state() and "drift:shipped" in state(), "drift: installed synced -> that alert clears", state())
ok(re.search(r"^  Recovered \d\d-[A-Z][a-z]{2}-\d{4}: ~/.claude/agents matches", Q.read_text(), re.M), "drift: Recovered line", Q.read_text())
# a shipped agent the live folder lacks
(ship / "poc-lead.md").write_text(BODY.format(n="poc-lead", m="inherit", o="{{OWNER}}"))
alerts("--only", "drift")
ok("1 shipped agent not in the live folder (poc-lead)" in state()["drift:shipped"]["reason"], "drift: missing live agent reported", state())
# back in sync
(ship / "poc-lead.md").unlink()
(live / "librarian.md").write_text(BODY.format(n="librarian", m="sonnet", o="Alex"))
shutil.copy(live / "librarian.md", inst / "librarian.md")
alerts("--only", "drift")
ok(not [k for k in state() if k.startswith("drift")] and "Drift" not in brief(), "drift: in sync -> cleared", state())
ok(re.search(r"^  Recovered .*: the live agents match the shipped version", Q.read_text(), re.M), "drift: shipped Recovered line")

# ================================================================ library
reset_queue()
for p in briefs.glob("alerts.json"): p.unlink()
lib = kit.parent / "lib"            # not under CloudStorage
gds = kit.parent / "GDS folder"
for d in (lib / "published", gds):
    d.mkdir(parents=True, exist_ok=True)
today = dt.date.today()
def T(d): return d.strftime("%d-%b-%Y")
def libmd(root, folder):
    (kit / "memory/context").mkdir(parents=True, exist_ok=True)
    (kit / "memory/context/library.md").write_text(
        f"# Library setup\n\n- **Library root:** `{root}/`. Work documents.\n\n## Published libraries\n\n"
        f"- **GDS (General Design Specifications):** index `published/gds-index.md`\n  `{folder}/`\n  Web: https://example.invalid\n"
        "- Files download on demand.\n\n## Working folders\n\n- **Primary:** `~/Docs/`\n")
def index(root, files, built):
    rows = "".join(f"| LIB-{i:04d} | GDS-{100+i} | T{i} | {T(built)} | `{f}` |  |\n" for i, f in enumerate(files, 1))
    (root / "published/gds-index.md").write_text(
        f"# Published index: GDS\n\nBuilt {T(built)} from file names only.\n\n| Accession | Number | Title | Modified | File | Notes |\n"
        "|---|---|---|---|---|---|\n" + rows)
libmd(lib, gds)
for f in ("Alpha @ DOC-101.pdf", "Beta @ DOC-102.pdf"):
    (gds / f).write_text("x")
(gds / ".DS_Store").write_text("x"); (gds / "~$Alpha.docx").write_text("x")
index(lib, ["Alpha @ DOC-101.pdf", "Beta @ DOC-102.pdf"], today)
r = alerts("--only", "library")
ok(r.returncode == 0 and not state(), "library: folder matches its index -> no alert (hidden and lock files ignored)", (state(), r.stderr))
(gds / "Gamma @ DOC-103.pdf").write_text("x")
r = alerts("--only", "library")
a = state().get("library:index", {})
ok("GDS: 1 file not in gds-index.md" in a.get("reason", "") and "ask the librarian to reindex" in a.get("reason", ""),
   "library: unindexed file -> alert", (state(), r.stderr))
ok(items(r"Ask the librarian to reindex the published libraries, out of date since .*\(kit-alerts library\)\*\* \[work\]") == 1,
   "library: one [work] queue item asking the librarian to reindex", Q.read_text())
ok("not indexed: Gamma @ DOC-103.pdf" in Q.read_text(), "library: the queue detail names the unindexed file", Q.read_text())
ok(brief().startswith("Library alert: GDS: 1 file not in gds-index.md"), "library: brief line", brief())
ok("<strong>Library</strong>" in banner(), "library: dashboard banner")
alerts("--only", "library", env={"LIBRARY_UNINDEXED_MAX": "1"})
ok("library:index" not in state(), "library: LIBRARY_UNINDEXED_MAX=1 tolerates one", state())
(gds / "Beta @ DOC-102.pdf").unlink()
alerts("--only", "library")
reason = state().get("library:index", {}).get("reason", "")
ok("1 indexed file no longer in the folder" in reason and "1 file not in" in reason, "library: missing indexed file reported", reason)
ok(items(r"Ask the librarian to reindex") == 1, "library: still one queue item for the outage")
index(lib, ["Alpha @ DOC-101.pdf", "Gamma @ DOC-103.pdf"], today)
alerts("--only", "library")
ok("library:index" not in state() and "Library" not in brief(), "library: reindexed -> clears", state())
ok(re.search(r"^  Recovered .*: the published indexes match their folders again", Q.read_text(), re.M), "library: Recovered line")
ok((lib / "published/gds-index.md").read_text().count("LIB-") == 2, "library: the index is never edited")
# an old index with files changed since
old = today - dt.timedelta(days=40)
index(lib, ["Alpha @ DOC-101.pdf", "Gamma @ DOC-103.pdf"], old)
alerts("--only", "library")
ok("index 40 days old with 2 files changed since" in state().get("library:index", {}).get("reason", ""),
   "library: index older than LIBRARY_INDEX_MAX_DAYS with changed files -> alert", state())
past = time.time() - 50 * 86400
for f in gds.iterdir(): os.utime(f, (past, past))
alerts("--only", "library")
ok("library:index" not in state(), "library: old index but nothing changed since -> no alert", state())
# Unicode: a decomposed name on disk matches a composed one in the index
(gds / unicodedata.normalize("NFD", "Café @ DOC-104.pdf")).write_text("x")
index(lib, ["Alpha @ DOC-101.pdf", "Gamma @ DOC-103.pdf", unicodedata.normalize("NFC", "Café @ DOC-104.pdf")], today)
alerts("--only", "library")
ok("library:index" not in state(), "library: NFD file name matches the NFC index entry", state())

# sync staleness under a CloudStorage root
cloud = home / "Library/CloudStorage/OneDrive-Test"
clib, cgds = cloud / "TeamLibrary", cloud / "GDS"
for d in (clib / "published", cgds): d.mkdir(parents=True, exist_ok=True)
libmd(clib, cgds)
(cgds / "Alpha @ DOC-101.pdf").write_text("x")
index(clib, ["Alpha @ DOC-101.pdf"], old)
for f in cgds.iterdir(): os.utime(f, (past, past))
(clib / "CATALOG.md").write_text("Kit wrote this today\n")
reset_queue()
alerts("--only", "library")
a = state().get("library:sync", {})
ok(a.get("inferred") and "no file in the published folders has changed in 50 days (limit 14)" in a.get("reason", "")
   and "today" in a.get("reason", ""), "library: cloud folders quiet while Kit writes -> inferred sync alert", state())
ok(not a.get("title") and items(r"Ask the librarian") == 0 and Q.read_text().count("- [ ]") == 2,
   "library: the sync alert adds no queue item", Q.read_text())
ok("Library alert (inferred): no file in the published folders" in brief(), "library: inferred brief line", brief())
alerts("--only", "library", env={"LIBRARY_SYNC_MAX_DAYS": "0"})
ok("library:sync" not in state(), "library: LIBRARY_SYNC_MAX_DAYS=0 turns the sync check off")
(cgds / "Alpha @ DOC-101.pdf").write_text("y")      # the sync brought a change
alerts("--only", "library")
ok("library:sync" not in state(), "library: a recent change in the published folder clears the sync alert", state())
# not set, or broken
(kit / "memory/context/library.md").write_text("# Library setup\n\n- **Library root:** not set.\n- **Published libraries:** none yet.\n")
r = alerts("--only", "library")
ok(r.returncode == 0 and not state(), "library: not set up -> nothing, no error", (r.stderr, state()))
libmd(clib, cgds); (clib / "published/gds-index.md").unlink()
r = alerts("--only", "library")
ok(r.returncode == 0 and "GDS: no index (gds-index.md)" in state().get("library:index", {}).get("reason", ""),
   "library: a missing index is reported, not a crash", (r.stderr, state()))
(kit / "memory/context/library.md").unlink()
alerts("--only", "library")
ok(not state(), "library: no library.md -> alerts cleared, no error", state())

# ================================================================ waiting
for p in briefs.glob("alerts.json"): p.unlink()
NOW = "2026-10-21T09:00"
W = ("- [ ] **Java JRE install**: EUC - Global Support, since 13-Oct-2026 (added 13-Oct-2026)\n"
     "  - INC35958470. Ask for a current update instead.\n"
     "- [ ] **Graph admin consent**: request submitted 20-Oct-2026 (added 20-Oct-2026)\n")
DEC = ("- [ ] **Approve the intake rule** [work] (draft: `drafts/2026-10-11-intake-rule.md`) (added 11-Oct-2026)\n"
       "- [ ] **Server OS lifecycle: decide by Dec-2026 for the old servers** [work] (added 20-Oct-2026)\n")
reset_queue(W, DEC)
before = Q.read_text()
dry = ka("check", "--dry-run", "--only", "waiting", "--now", NOW)
ok("Waiting 8 days: Java JRE install; follow-up draft would go to briefs/followups/java-jre-install.md" in dry.stdout
   and not (briefs / "alerts.json").exists() and not (briefs / "followups").exists(),
   "waiting: kit-alerts check --dry-run says what it would flag and writes nothing", dry.stdout)
r = alerts("--only", "waiting", now=NOW)
st = state()
ok(st.get("waiting:java-jre-install", {}).get("days") == 8, "waiting: 8-day-old waiting item -> alert", (st, r.stderr))
ok("waiting:graph-admin-consent" not in st, "waiting: a recent waiting item -> no alert", st)
draft = briefs / "followups/java-jre-install.md"
txt = draft.read_text() if draft.exists() else ""
ok("INC35958470" in txt and "Java JRE install" in txt and "To: EUC - Global Support" in txt and "never sends" in txt
   and "open since 13-Oct-2026" in txt and "Ask for a current update" not in txt,
   "waiting: follow-up draft names the request and ticket as the queue does, nothing more", txt)
ok("Waiting 8 days: Java JRE install; follow-up draft in briefs/followups/java-jre-install.md (never sent)." in brief(),
   "waiting: brief line mentions the draft", brief())
dec = st.get("waiting:approve-the-intake-rule", {})
ok(dec.get("type") == "decision" and dec.get("days") == 10 and not dec.get("draft"), "waiting: decision item -> alert, no draft", st)
ok("Decision waiting 10 days: Approve the intake rule (drafts/2026-10-11-intake-rule.md)." in brief(),
   "waiting: decision brief line gives the days and the file it names", brief())
ok(not (briefs / "followups/approve-the-intake-rule.md").exists(), "waiting: no follow-up draft for a decision")
ok("waiting:server-os-lifecycle-decide-by-dec-2026-for-the-old-servers" not in st, "waiting: recent 'decide by' item -> no alert")
ok(not any("font" in k for k in st), "waiting: Kit's own 'decide by' items are not the owner's decisions", st)
ok(Q.read_text() == before, "waiting: no queue items added or changed", Q.read_text())
b = banner()
ok("<strong>Waiting too long</strong>" in b and "Java JRE install (waiting on others, 8 days" in b and "Approve the intake rule (decision, 10 days" in b,
   "waiting: dashboard banner lists them", b)
ow = ka("--only", "waiting")
ok(ow.stdout.count("\n  - ") == 2 and "Waiting 8 days" in ow.stdout and "Drift" not in ow.stdout, "kit-alerts --only waiting", ow.stdout)
alerts("--only", "waiting", now=NOW)
ok(sorted(p.name for p in (briefs / "followups").iterdir()) == ["java-jre-install.md"], "waiting: rerun, one draft")
# 'decide by' in the owner's section gets old
reset_queue(W, DEC.replace("added 20-Oct-2026", "added 01-Oct-2026"))
alerts("--only", "waiting", now=NOW)
ok(state().get("waiting:server-os-lifecycle-decide-by-dec-2026-for-the-old-servers", {}).get("type") == "decision",
   "waiting: an old 'decide by' item -> decision alert", state())
# the waiting item's line gets a newer date -> clears, draft removed
reset_queue(W.replace("(added 13-Oct-2026)", "(added 13-Oct-2026, updated 20-Oct-2026)"), DEC)
alerts("--only", "waiting", now=NOW)
ok("waiting:java-jre-install" not in state() and not draft.exists(), "waiting: updated date -> clears and removes the draft", state())
# an edited draft is kept when its alert clears
reset_queue(W, DEC)
alerts("--only", "waiting", now=NOW)
draft.write_text(draft.read_text() + "\nMy own note.\n")
reset_queue(W.replace("- [ ] **Java", "- [x] **Java"), DEC)
alerts("--only", "waiting", now=NOW)
ok("waiting:java-jre-install" not in state() and draft.exists(), "waiting: checked off -> clears, an edited draft is kept", state())
# decision checked off
reset_queue("", DEC.replace("- [ ] **Approve", "- [x] **Approve"))
alerts("--only", "waiting", now=NOW)
ok("waiting:approve-the-intake-rule" not in state(), "waiting: decision checked off -> clears", state())
alerts("--only", "waiting", now=NOW, env={"MONITOR_WAITING": "off"})
ok(not [k for k in state() if k.startswith("waiting")], "waiting: MONITOR_WAITING=off clears it", state())

# ================================================================ never fails
empty = home / "empty-kit"
empty.mkdir()
r = subprocess.run([sys.executable, str(RA), "--kit", str(empty), "--no-dashboard", "--now", NOW],
                   capture_output=True, text=True, timeout=120)
ok(r.returncode == 0 and r.stdout.strip() == "", "missing everything: exits 0, nothing flagged", (r.stdout, r.stderr))
(empty / "QUEUE.md").write_text("garbage \x00 ## \n- [ ] **x** (added 99-Zzz-2026)\n")
(empty / "agents").mkdir(); (empty / ".install/kit/agents").mkdir(parents=True)
(empty / ".install/kit/agents/a.md").write_bytes(b"\xff\xfe broken")
r = subprocess.run([sys.executable, str(RA), "--kit", str(empty), "--no-dashboard", "--now", NOW, "--no-track"],
                   capture_output=True, text=True, timeout=120)
ok(r.returncode == 0, "broken files: exits 0", r.stderr)
r = alerts("--only", "bogus")
ok(r.returncode == 0, "unknown --only: still exits 0")
r = ka("check", "--dry-run", "--now", NOW)
ok(r.returncode == 0 and "dry run" in r.stdout, "kit-alerts check --dry-run (all kinds) runs", r.stdout + r.stderr)

print(f"\n{P} passed, {F} failed")
sys.exit(1 if F else 0)
PY

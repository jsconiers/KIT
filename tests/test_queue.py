#!/usr/bin/env python3
"""Tests for queue hygiene (kit_queue, kit-queue, todo touch/edit) and the sprint view
(todo sprint, the dashboard's Sprint panel, the work-list and weekly prompts).

Runs everything against a throwaway HOME, so the real Kit is never touched. Optional: pass the
path of a real QUEUE.md to also check that a copy of it parses and gets a hygiene report.

  python3 tests/test_queue.py [path/to/QUEUE.md]
"""
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SHARED = REPO / "shared"
TODAY = dt.date.today()
PASS = FAIL = 0


def ok(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


def d(days_ago):
    return (TODAY - dt.timedelta(days=days_ago)).strftime("%d-%b-%Y")


FIXTURE = f"""# Queue

Intro text.

## Sprint

No sprint running. Start one with `todo sprint start <name> <start> <end>`.

## Owner

- [ ] **Write the network design note**: due TBD (added {d(20)})
- [ ] **Renew the certificate** (added {d(2)})
- [ ] **Draft the vendor letter** (added {d(15)})

## Kit

- [ ] **Shared connectivity between Kits: build** (added {d(1)})
  - [ ] Transport interface; move kit-publish and team_dashboard onto it
  - [ ] Folder adapter for shared folders
- [ ] **Kit roadmap: next phases** (added {d(10)}, updated {d(9)})
  - [ ] Cost control agent
  - [ ] Kit publish
  - [ ] Sprint view
  - [ ] Fix and test Jira connection
  - [ ] Fix and test Confluence connection
- [ ] **Old cleanup task** (added {d(30)})
  - Some detail line

## Waiting on others

- [ ] **Credits**: Support, since {d(3)} (added {d(3)})

## Someday

## Done
- [x] **Earlier thing**: Kit, done {d(1)} (added {d(4)})
"""


def run(cmd, home, **kw):
    env = dict(os.environ, HOME=str(home))
    env.pop("KIT_DIR", None)
    return subprocess.run(cmd, capture_output=True, text=True, env=env, **kw)


def main():
    tmp = pathlib.Path(tempfile.mkdtemp())
    home = tmp / "home"
    kit = home / "Claude/Agents/kit"
    (kit / "briefs").mkdir(parents=True)
    queue = kit / "QUEUE.md"
    queue.write_text(FIXTURE)
    todo = [sys.executable, str(SHARED / "bin/todo")]
    kq = [sys.executable, str(SHARED / "bin/kit-queue")]

    # --- stamping
    sys.path.insert(0, str(SHARED))
    import kit_queue as q
    s = q.stamp(f"- [ ] **A** (added {d(5)})", TODAY)
    ok(s.endswith(f"(added {d(5)}, updated {d(0)})"), "stamp adds updated to the added note", s)
    s = q.stamp(f"- [ ] **A** (added {d(5)}, updated {d(4)})", TODAY)
    ok(s.count("updated") == 1 and f"updated {d(0)}" in s, "stamp replaces an old updated date", s)
    s = q.stamp("- [ ] **A**: due TBD", TODAY)
    ok(s.endswith(f"(updated {d(0)})"), "stamp works on an item with no dates", s)
    s = q.stamp(f"- [ ] **A** (recurring from {d(-3)}, added {d(5)})", TODAY)
    ok(s.endswith(f"added {d(5)}, updated {d(0)})"), "stamp keeps other notes in the parentheses", s)

    r = run(todo + ["touch", "1"], home)
    line = [ln for ln in queue.read_text().splitlines() if "Write the network design note" in ln][0]
    ok(r.returncode == 0 and f"updated {d(0)}" in line, "todo touch stamps the item", line + r.stderr)
    r = run(todo + ["edit", "2", "Renew", "the", "TLS", "certificate"], home)
    text = queue.read_text()
    ok("**Renew the TLS certificate** (added" in text and f"added {d(2)}, updated {d(0)}" in text,
       "todo edit rewords and stamps, keeping dates", r.stderr)
    r = run(todo + ["kit", "touch", "9"], home)
    ok(r.returncode != 0, "todo touch refuses a number that doesn't exist")

    # --- hygiene
    r = run(kq + ["hygiene", "--json"], home)
    ok(r.returncode == 0, "kit-queue hygiene --json runs", r.stderr)
    h = json.loads(r.stdout)
    saved = json.loads((kit / "briefs/hygiene.json").read_text())
    ok(saved == h, "hygiene --json saves briefs/hygiene.json")
    stale = {e["item"]["title"] for e in h["entries"] if e["kind"] == "stale"}
    ok("Old cleanup task" in stale and "Kit roadmap: next phases" in stale, "stale items found", str(stale))
    ok("Write the network design note" not in stale, "a touched item isn't stale")
    ok("Shared connectivity between Kits: build" not in stale, "a recent item isn't stale")
    pairs = {(e["a"]["title"], e["b"]["title"]) for e in h["entries"] if e["kind"] == "duplicate"}
    flat = {t for p in pairs for t in p}
    ok(any("Kit publish" in p and any("kit-publish" in t for t in p) for p in pairs),
       "duplicate: 'Kit publish' and the item that moves kit-publish", str(pairs))
    ok(not any("Jira" in a and "Confluence" in b or "Confluence" in a and "Jira" in b for a, b in pairs),
       "sibling items (Fix and test Jira / Confluence) aren't flagged", str(pairs))
    ok(not any(("Folder adapter" in a and "Shared connectivity" in b) or ("Folder adapter" in b and
               "Shared connectivity" in a) for a, b in pairs), "an item and its own sub-item aren't paired")
    ids = [e["id"] for e in h["entries"]]
    ok(ids == [f"H{i}" for i in range(1, len(ids) + 1)], "entries are numbered H1, H2, ... in order", str(ids))
    ok(h["open_items"] == 7 and h["size"]["Kit"]["sub_items"] == 7, "queue size counted",
       json.dumps(h["size"]))
    ok(any(w["added"] for w in h["trend"]) and any(w["closed"] for w in h["trend"]), "trend has added and closed")
    r = run(kq + ["hygiene"], home)
    ok("H1" in r.stdout and "Trend" in r.stdout and "kit-queue apply" in r.stdout, "plain hygiene report reads well")

    # --- apply
    by = {e["item"]["title"]: e["id"] for e in h["entries"] if e["kind"] == "stale"}
    dup = next(e for e in h["entries"] if e["kind"] == "duplicate" and "Kit publish" in (e["a"]["title"], e["b"]["title"]))
    before = queue.read_text()
    r = run(kq + ["apply", "--dry-run", f"{by['Old cleanup task']} drop"], home)
    ok(queue.read_text() == before and "would:" in r.stdout, "apply --dry-run changes nothing", r.stdout)
    r = run(kq + ["apply", "H99 keep"], home)
    ok(queue.read_text() == before and "skipped H99" in r.stdout, "apply skips numbers not in the saved list")
    r = run(kq + ["apply", "everything"], home)
    ok(r.returncode != 0 and queue.read_text() == before, "apply refuses text without H numbers")
    r = run(kq + ["apply", f"{by['Old cleanup task']} drop, {by['Kit roadmap: next phases']} keep, "
                  f"{by['Draft the vendor letter']} rewrite, {dup['id']} merge"], home)
    after = queue.read_text()
    ok(r.returncode == 0, "apply runs", r.stdout + r.stderr)
    backups = list((kit / ".install/backups").glob("QUEUE-*.md"))
    ok(len(backups) == 1 and backups[0].read_text() == before, "apply backs up QUEUE.md first")
    done_sec = after.split("## Done", 1)[1]
    ok("**Old cleanup task**: Kit, dropped" in done_sec and "Some detail line" in done_sec,
       "drop moves the item and its detail to Done")
    road = [ln for ln in after.splitlines() if ln.startswith("- [ ] **Kit roadmap")][0]
    ok(f"updated {d(0)}" in road, "keep stamps the item", road)
    src, dst = dup["a"]["title"], dup["b"]["title"]
    ok(f"  - [ ] {src}\n" not in after and f"(merged: {src}" in after and dst in after,
       "merge moves the first of the pair into the second and records it", f"{src} -> {dst}")
    vl = after.split("**Draft the vendor letter**", 1)[1].split("\n- [", 1)[0]
    ok("Needs rewrite" in vl and f"updated {d(0)}" in vl, "rewrite adds a note and stamps", vl)

    # --- sprint
    r = run(todo + ["sprint"], home)
    ok("No sprint running" in r.stdout, "todo sprint shows the empty sprint")
    r = run(todo + ["sprint", "start", "S1", d(2), d(-11)], home)
    ok(r.returncode == 0 and f"Sprint S1: {d(2)} to {d(-11)}" in queue.read_text(), "sprint start", r.stderr)
    road_items = q.roadmap_subitems(queue.read_text().splitlines())
    n_cost = [i for i, it in enumerate(road_items, 1) if it["title"] == "Cost control agent"][0]
    r = run(todo + ["sprint", "add", str(n_cost), "M"], home)
    ok(r.returncode == 0 and "**Cost control agent** (M) [open] (roadmap)" in queue.read_text(),
       "sprint add by roadmap number", r.stdout + r.stderr)
    r = run(todo + ["sprint", "add", "Write", "the", "runbook", "S"], home)
    r2 = run(todo + ["sprint", "add", "Sprint", "view", "L"], home)
    ok(r.returncode == 0 and r2.returncode == 0 and "**Write the runbook** (S) [open]" in queue.read_text(),
       "sprint add by text")
    r = run(todo + ["sprint", "mark", "3", "blocked"], home)
    ok("**Sprint view** (L) [blocked]" in queue.read_text(), "sprint mark sets a status")
    r = run(todo + ["sprint", "done", "1"], home)
    text = queue.read_text()
    ok(f"- [x] **Cost control agent** (M) [done {d(0)}] (roadmap)" in text, "sprint done checks it off", r.stderr)
    ok("  - [ ] Cost control agent" not in text and "**Cost control agent**: Kit, done" in text,
       "sprint done closes the roadmap item it came from")
    sp = q.sprint(text.splitlines())
    ok(q.sprint_points(sp) == (9, 3), "points: S=1, M=3, L=5", str(q.sprint_points(sp)))
    r = run(todo + ["sprint", "start", "S2", d(0), d(-5)], home)
    ok(r.returncode != 0, "can't start a sprint while one is open")

    # --- dashboard panel
    (kit / ".install/shared").mkdir(parents=True, exist_ok=True)
    r = run([sys.executable, str(SHARED / "dashboard.py")], home, timeout=120)
    page = (kit / "dashboard.html").read_text() if (kit / "dashboard.html").exists() else ""
    ok(r.returncode == 0 and "Sprint S1" in page and "3/9 points done" in page and "<svg" in page,
       "dashboard shows the sprint panel with a burndown", r.stderr[-400:])
    hist = json.loads((kit / ".install/cache/sprint-history.json").read_text())
    ok(any(v.get(TODAY.isoformat()) == 6 for v in hist.values()), "dashboard saves today's points-left snapshot",
       json.dumps(hist))

    # --- close and carry over
    r = run(todo + ["sprint", "close"], home)
    text = queue.read_text()
    summary = kit / "briefs/sprint-s1.md"
    ok(r.returncode == 0 and summary.exists() and "Points done: 3 of 9" in summary.read_text(),
       "sprint close writes the summary", r.stdout + r.stderr)
    ok("Carry-over from S1:" in text and "**Write the runbook** (S) [carried over]" in text and
       "No sprint running" in text, "unfinished items carry over")
    r = run(todo + ["sprint", "start", "S2", d(0), d(-13)], home)
    sp = q.sprint(queue.read_text().splitlines())
    ok(sp["name"] == "S2" and len(sp["items"]) == 2 and not sp["carry"], "the next sprint starts with the carry-over",
       json.dumps([i["title"] for i in sp["items"]]))
    r = run(todo, home)
    ok(r.returncode == 0 and "Owner" in r.stdout, "plain todo still lists the sections")

    # --- the owner's section when OWNER_NAME isn't set (a fresh install), or names someone else
    lines = ["# Queue", "", "## Sprint", "", "## Testy", "- [ ] **Call the bank** (added 01-Oct-2026)", "",
             "## Kit", "", "## Waiting on others", "", "## Someday", "", "## Done"]
    ok(q.owner_section(lines) == "Testy" and q.owner_section(lines, "Testy") == "Testy"
       and q.owner_section(lines, "Alex") == "Testy" and q.owner_section(["## Kit", "## Done"], "Alex") is None,
       "owner_section: OWNER_NAME when the queue has it, otherwise the queue's own owner section")
    ok(q.configured_owner('OWNER_NAME="Testy"\n') == "Testy" and q.configured_owner('OWNER_NAME=""\n') is None
       and q.configured_owner("") is None, "configured_owner reads OWNER_NAME")
    home3 = tmp / "home3"
    k3 = home3 / "Claude/Agents/kit"
    (k3 / "briefs").mkdir(parents=True)
    (k3 / "QUEUE.md").write_text("\n".join(lines) + "\n")
    r = run(todo, home3)
    ok(r.returncode == 0 and "Testy (1)" in r.stdout and "Call the bank" in r.stdout,
       "with no config, todo lists the queue's owner section", r.stdout + r.stderr)
    r = run(todo + ["Renew", "the", "passport"], home3)
    t3 = (k3 / "QUEUE.md").read_text()
    ok(r.returncode == 0 and "Added for Testy" in r.stdout and "**Renew the passport**" in t3
       and t3.index("## Testy") < t3.index("**Renew the passport**") < t3.index("## Kit"),
       "and todo adds to it", r.stdout + r.stderr)
    (k3 / ".install/shared/morning").mkdir(parents=True)
    (k3 / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\n')
    r = run(todo, home3)
    ok(r.returncode == 0 and "Testy (2)" in r.stdout, "a config naming someone else falls back the same way",
       r.stdout + r.stderr)
    r = run([sys.executable, str(SHARED / "dashboard.py")], home3, timeout=120)
    page = (k3 / "dashboard.html").read_text() if (k3 / "dashboard.html").exists() else ""
    ok(r.returncode == 0 and "Call the bank" in page and "Your list is clear" not in page,
       "the dashboard finds the owner's items the same way", r.stderr[-300:])

    # --- starter file and prompts
    starter = (REPO / "kit/QUEUE.md").read_text()
    own = q.owner_section(starter.splitlines())
    ok(own and starter.index("## Sprint") < starter.index("## " + own), "starter QUEUE.md has Sprint before the owner",
       str(own))
    wl = (SHARED / "morning/prompt-worklist.md").read_text()
    ok("Start with the sprint" in wl and "(sprint)" in wl, "work-list prompt proposes sprint items first")
    wk = (SHARED / "morning/prompt-weekly.md").read_text()
    ok("Sprint review" in wk and "kit-queue hygiene --json" in wk, "weekly prompt has the sprint review and hygiene")
    mp = (SHARED / "morning/prompt.md").read_text()
    ok("Queue hygiene" in mp and "apply verdicts H1 keep" in mp, "morning prompt has the hygiene section")
    rs = (REPO / "platform/mac/morning/run.sh").read_text()
    ok("kit-queue hygiene:*" in rs, "run.sh allows kit-queue hygiene")

    # --- a roadmap split into groups numbers across all groups, in order
    sys.path.insert(0, str(SHARED))
    import kit_queue as kqm
    grouped = """# Queue

## Kit
- [ ] **Roadmap A: Connections** (added 16-Oct-2026)
  - [ ] Fix Confluence
  - [ ] Fix Jira
- [ ] **Something else** (added 16-Oct-2026)
  - [ ] Not a roadmap item
- [ ] **Roadmap B: Labs** (added 16-Oct-2026)
  - [ ] Lab register

## Done
""".splitlines()
    titles = [it["title"] for it in kqm.roadmap_subitems(grouped)]
    ok(titles == ["Fix Confluence", "Fix Jira", "Lab register"], "grouped roadmap numbers across groups", str(titles))

    # --- a copy of a real queue
    if len(sys.argv) > 1 and pathlib.Path(sys.argv[1]).exists():
        home2 = tmp / "home2"
        k2 = home2 / "Claude/Agents/kit"
        (k2 / "briefs").mkdir(parents=True)
        shutil.copy(sys.argv[1], k2 / "QUEUE.md")
        r = run(kq + ["hygiene", "--json", "--no-save"], home2)
        ok(r.returncode == 0 and json.loads(r.stdout)["open_items"] > 0, "a copy of the real queue parses",
           r.stderr)
        r = run(todo + ["sprint"], home2)
        ok(r.returncode == 0, "todo sprint works on the real queue's copy (adds an empty Sprint view only on write)")
    shutil.rmtree(tmp)
    print(f"\nqueue tests: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

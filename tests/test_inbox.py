#!/usr/bin/env python3
"""Tests for phone and remote access phase 1 (shared/kit_inbox.py, its use in reminders_sync.py
and deliver.py). Everything runs in a temp folder with a fake Kit and a fake to-do app; no real
Outlook, OneDrive, or notification is touched."""
import datetime as dt
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SHARED = REPO / "shared"
PASS = FAIL = 0


def ok(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


def main():
    tmp = pathlib.Path(tempfile.mkdtemp())
    home = tmp / "home"
    kit = home / "Claude/Agents/kit"
    (kit / "briefs").mkdir(parents=True)
    (kit / ".install/shared/bin").mkdir(parents=True)
    (kit / "memory/personal").mkdir(parents=True)
    shutil.copy(SHARED / "bin/todo", kit / ".install/shared/bin/todo")
    for f in ("kit_queue.py",):
        if (SHARED / f).exists():
            shutil.copy(SHARED / f, kit / ".install/shared/" / f)
    (kit / "QUEUE.md").write_text(
        "# Queue\n\n## Alex\n\n- [ ] **Existing work item** [work] (added 01-Oct-2026)\n"
        "- [ ] **Personal errand** (added 01-Oct-2026)\n\n## Kit\n\n- [ ] **Kit thing** (added 01-Oct-2026)\n\n"
        "## Waiting on others\n\n- [ ] **Ticket** (added 01-Oct-2026)\n\n## Done\n")
    os.environ["KIT_DIR"] = str(kit)
    os.environ["HOME"] = str(home)
    sys.path.insert(0, str(SHARED))
    import kit_inbox as ki

    # ---- classify
    ok(ki.classify("Buy milk") == ("todo", "Buy milk"), "plain text is a to-do")
    ok(ki.classify("Kit: draft the agenda") == ("kit", "draft the agenda"), "kit: is a Kit request")
    ok(ki.classify("ASK : what's due?") == ("ask", "what's due?"), "ask: is a question (any case, spaces)")
    ok(ki.classify("approve ABC123 1,3")[0] == "approve", "approve is an approval")
    ok(ki.classify("approvement plan")[0] == "todo", "a word starting with approve isn't an approval")

    # ---- codes: issue, hash only, single use, expiry, scope
    code = ki.issue_code("worklist")
    store = json.loads((kit / ".install/cache/phone-codes.json").read_text())
    ok(len(code) == 6 and code not in json.dumps(store), "code issued; only a hash is stored")
    ok(oct((kit / ".install/cache/phone-codes.json").stat().st_mode)[-3:] == "600", "code store is owner-only")
    acc, msg = ki.handle_approval(f"approve {code.lower()} 3, 1")
    ok(acc and "approve 1,3" in msg, "valid code approves work-list items (case-insensitive, sorted)", msg)
    acc, msg = ki.handle_approval(f"approve {code} 2")
    ok(not acc and "already used" in msg, "a code works once", msg)
    acc, msg = ki.handle_approval("approve ZZZZZZ all")
    ok(not acc and "not recognised" in msg, "an unknown code is refused", msg)
    old = ki.issue_code("worklist", today=dt.date.today() - dt.timedelta(days=1))
    acc, msg = ki.handle_approval(f"approve {old} all")
    ok(not acc and ("expired" in msg or "not recognised" in msg), "yesterday's code doesn't work today", msg)
    c2 = ki.issue_code("worklist")
    acc, msg = ki.handle_approval(f"approve {c2} commit and push the changes")
    ok(not acc and "can't approve" in msg, "a medium/high-tier action is refused (commit, push)", msg)
    acc, _ = ki.handle_approval(f"approve {c2} all")
    ok(acc, "a refused payload doesn't burn the code")
    c3 = ki.issue_code("worklist")
    for bad in ("install the agents", "send the draft", "delete file 3", "change settings", "1,3 then send"):
        acc, msg = ki.handle_approval(f"approve {c3} {bad}")
        ok(not acc, f"refused: '{bad}'", msg)
    h = ki.issue_code("morning")
    acc, msg = ki.handle_approval(f"approve {h} H1 keep, h2 merge into H5")
    ok(acc and "H1 keep, H2 merge into H5" in msg, "hygiene code approves H-numbered verdicts", msg)
    h2 = ki.issue_code("morning")
    acc, msg = ki.handle_approval(f"approve {h2} 1,3")
    ok(not acc, "a hygiene code can't approve work-list numbers", msg)
    w = ki.issue_code("worklist")
    acc, msg = ki.handle_approval(f"approve {w} H1 keep")
    ok(not acc, "a work-list code can't approve hygiene verdicts", msg)
    log = (kit / "briefs/phone-approvals.md").read_text()
    ok("accepted (work list): approve 1,3" in log and "refused" in log, "outcomes recorded in phone-approvals.md")
    try:
        ki.issue_code("weekly")
        ok(False, "no codes for other runs")
    except ValueError:
        ok(True, "no codes for other runs")
    sec = ki.code_section("worklist", "ABC234")
    ok("ABC234" in sec and "can't approve commits" in sec, "code section names the code and the limits")

    # ---- reminders_sync routing with a fake backend
    class Fake:
        def __init__(self, items):
            self.items = items
            self.mirrored = []

        def pull_open(self, name):
            out, self.items = self.items, []
            return out

        def mirror(self, want, name):
            self.mirrored = want
            return []

    code = ki.issue_code("worklist")
    spec = importlib.util.spec_from_file_location("reminders_sync", str(SHARED / "reminders_sync.py"))
    rs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rs)
    fake = Fake([{"name": "Pick up badge", "due": None}, {"name": "kit: draft the agenda", "due": None},
                 {"name": "ask: what's due Friday?", "due": None}, {"name": f"approve {code} all", "due": None}])
    changed = rs.reconcile(fake, "Alex", "Kit Inbox", "Kit: Alex")
    q = (kit / "QUEUE.md").read_text()
    ok("**Pick up badge**" in q, "sync: plain inbox item becomes the owner's to-do")
    ok("**draft the agenda**" in q, "sync: kit: item becomes a Kit to-do")
    ok("what's due Friday" not in q and "approve" not in q.lower(), "sync: ask: and approve items never become to-dos")
    req = (kit / "briefs/requests.md").read_text()
    ok("kit: draft the agenda" in req and "ask: what's due Friday?" in req, "sync: requests recorded in requests.md")
    ok(any("phone approval accepted" in c for c in changed), "sync: approval checked and reported", str(changed))

    # ---- publishing
    od = tmp / "OneDriveFake"
    (od / "Kit").mkdir(parents=True)
    cfg = {"ONEDRIVE_PUBLISH_DIR": str(od / "Kit"), "ONEDRIVE_ALLOWED_PREFIX": str(od)}
    t, why = ki.check_publish_dir(cfg)
    ok(t == (od / "Kit").resolve(), "publish dir inside the allowed root is accepted", str(why))
    t, why = ki.check_publish_dir({"ONEDRIVE_PUBLISH_DIR": str(tmp / "elsewhere"), "ONEDRIVE_ALLOWED_PREFIX": str(od)})
    ok(t is None and "inside your OneDrive" in why, "publish dir outside OneDrive is refused", str(why))
    t, why = ki.check_publish_dir({"ONEDRIVE_PUBLISH_DIR": str(od), "ONEDRIVE_ALLOWED_PREFIX": str(od)})
    ok(t is None, "the OneDrive root itself is refused (a subfolder is required)")
    t, why = ki.check_publish_dir({"ONEDRIVE_PUBLISH_DIR": str(kit / "out"), "ONEDRIVE_ALLOWED_PREFIX": str(home)})
    ok(t is None and "Kit's own folder" in why, "a folder inside Kit is refused", str(why))
    t, why = ki.check_publish_dir({})
    ok(t is None and why.startswith("off"), "empty setting means off")

    brief = kit / "briefs/2026-10-19.md"
    brief.write_text("# Brief\n\n## To-dos\n\n- Review GDS [work]\n- Dentist (personal)\n\n## Pastoral care\n\n"
                     "- Visit someone\n\n## Trading read\n\nRegime calm.\n\n## Calendar\n\n- 09:00 standup\n")
    (kit / "dashboard.html").write_text("<html>full dashboard with Personal errand</html>")
    okp, msg = ki.publish(brief, "morning", cfg)
    out = (od / "Kit/latest-morning.html").read_text()
    ok(okp and "Review GDS" in out and "standup" in out, "brief published as HTML", msg)
    ok("Dentist" not in out and "Visit someone" not in out and "Regime" not in out,
       "personal lines and sections (pastoral, trading) left out by default")
    idx = (od / "Kit/index.html").read_text()
    ok("Existing work item" in idx and "Personal errand" not in idx and "Kit thing" in idx,
       "summary page has work items, Kit's items, no personal to-dos")
    ok(not (od / "Kit/dashboard.html").exists(), "full dashboard not published without PUBLISH_PERSONAL")
    ok(oct((od / "Kit/latest-morning.html").stat().st_mode)[-3:] == "600"
       and oct((od / "Kit").stat().st_mode)[-3:] == "700", "published files and folder are owner-only")
    okp, msg = ki.publish(brief, "morning", dict(cfg, PUBLISH_PERSONAL="on"))
    out = (od / "Kit/latest-morning.html").read_text()
    ok("Dentist" in out and (od / "Kit/dashboard.html").exists(), "PUBLISH_PERSONAL=on includes personal and the dashboard")
    pb = kit / "memory/personal/secret-notes.md"
    pb.write_text("# private\n")
    okp, msg = ki.publish(pb, "morning", cfg)
    ok(not okp and "memory/personal" in msg, "nothing from memory/personal is published", msg)

    # ---- deliver.py: code goes in the brief, not the text; publish runs; unknown channel = no side effects
    conf = tmp / "config"
    conf.write_text(f'PHONE_APPROVALS="on"\nONEDRIVE_PUBLISH_DIR="{od / "Kit"}"\nONEDRIVE_ALLOWED_PREFIX="{od}"\n')
    wl = kit / "briefs/worklist-2026-10-19.md"
    wl.write_text("# Work list\n\n1. **Item one**: S\n")
    txt = kit / "briefs/worklist-text.txt"
    txt.write_text("Kit work list · Mon 19-Oct\n2 items\n")
    env = dict(os.environ, HOME=str(home), KIT_DIR=str(kit))
    r = subprocess.run([sys.executable, str(SHARED / "deliver.py"), "--mode", "worklist", "--text", str(txt),
                        "--brief", str(wl), "--channels", "none", "--config", str(conf)],
                       capture_output=True, text=True, env=env)
    body = wl.read_text()
    ok("## Phone approval" in body and "approval code added" in r.stdout, "deliver: code section added to the work list", r.stdout + r.stderr)
    ok("Phone approval" not in txt.read_text(), "deliver: code never goes in the notification text")
    ok("onedrive: published" in r.stdout and (od / "Kit/latest-worklist.html").exists(), "deliver: published to OneDrive", r.stdout)
    r = subprocess.run([sys.executable, str(SHARED / "deliver.py"), "--mode", "worklist", "--text", str(txt),
                        "--brief", str(wl), "--channels", "none", "--config", str(conf), "--test"],
                       capture_output=True, text=True, env=env)
    ok(wl.read_text().count("## Phone approval") == 1 and "onedrive" not in r.stdout, "deliver --test: no code, no publish")

    # ---- prompts
    mp = (SHARED / "morning/prompt.md").read_text()
    ok("From your phone" in mp and "Commitments," in mp and "unconfirmed commitments (count" in mp,
       "morning prompt lists phone requests, approvals, and commitments")
    wp = (SHARED / "morning/prompt-worklist.md").read_text()
    ok("approval code" in wp, "work-list prompt points to the phone approval code")

    shutil.rmtree(tmp)
    print(f"\ninbox tests: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

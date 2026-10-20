#!/usr/bin/env python3
"""Tests for messages and trust rules between Kits (roadmap item 7): kit-team send drafts and asks,
the organization profile, verified inboxes, the hash chain, history rewrites, acks, expiry, and
retention with legal holds in the cache. Two fake Kits share a temporary folder; nothing real is
touched. Run: python3 tests/test_trust.py"""
import datetime as dt
import json
import os
import pathlib
import select
import shutil
import subprocess
import sys
import tempfile
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
TEAM = REPO / "shared/bin/kit-team"
os.environ["KIT_DIR"] = tempfile.mkdtemp(prefix="kit-trust-test-")
sys.path.insert(0, str(REPO / "shared"))
import kit_records as kr  # noqa: E402
import kit_transport as kt  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


def make_kit(base, kid, shared):
    kit = base / kid
    (kit / "memory/context").mkdir(parents=True)
    (kit / "memory/context/sharing.md").write_text(
        f"# Sharing\n\n- **Kit id:** {kid}\n- **Owner role:** solutions architect\n"
        f"- **Transport:** folder\n- **Shared root:** {shared}\n- **Outbox:** {kit / 'outbox'}\n")
    return kit


def env_for(kit):
    return dict(os.environ, KIT_DIR=str(kit), KIT_SHARED_ROOT="", KIT_TRANSPORT="")


def team(kit, *args, stdin_text=None):
    """kit-team with no keyboard (stdin and stdout are pipes)."""
    return subprocess.run([sys.executable, str(TEAM), *args, "--cache", str(kit / "team.db")],
                          input=stdin_text or "", capture_output=True, text=True, env=env_for(kit))


def team_tty(kit, *args, answer=None, timeout=20):
    """kit-team on a pseudo-terminal, answering the prompt with `answer` (or nothing)."""
    master, slave = os.openpty()
    p = subprocess.Popen([sys.executable, str(TEAM), *args, "--cache", str(kit / "team.db")],
                         stdin=slave, stdout=slave, stderr=slave, env=env_for(kit), close_fds=True)
    os.close(slave)
    out, sent, end = b"", False, time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([master], [], [], 0.2)
        if r:
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
            if answer is not None and not sent and b"[y/N]" in out:
                os.write(master, (answer + "\n").encode())
                sent = True
        elif p.poll() is not None:
            break
    p.wait(timeout=5)
    os.close(master)
    return p.returncode, out.decode("utf-8", "replace")


def message(kit, to, local, expires, project="general", text="Heads up: the design review moved."):
    stamp = kr.now_iso()
    return {"schema": "message", "schema_version": "1.0", "id": f"{kit}:message:{local}", "kit_id": kit,
            "owner_role": "solutions architect", "project": project, "created": stamp, "updated": stamp,
            "classification": "internal", "source": f"kit:messages/{local}",
            "body": {"from_kit": kit, "to": to, "subject": "Review moved", "text": text, "kind": "info",
                     "expires": expires}}


def iso(days):
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=days)).replace(microsecond=0) \
        .isoformat().replace("+00:00", "Z")


def main():
    schemas = kr.load_schemas()
    base = pathlib.Path(tempfile.mkdtemp())
    try:
        shared = base / "shared"
        alpha, bravo = make_kit(base, "kit-alpha", shared), make_kit(base, "kit-bravo", shared)
        a = kt.FolderTransport(shared, "kit-alpha", "shared")
        b = kt.FolderTransport(shared, "kit-bravo", "shared")
        inbox_b = shared / "kits/kit-bravo/inbox"

        check("message schema loads", "message" in schemas)
        m0 = message("kit-alpha", ["kit-bravo"], "schema-check", iso(30))
        check("a message record is valid", not kr.validate(m0, schemas), kr.validate(m0, schemas))
        check("kit-publish types don't include message", "message" not in kr.TYPES)

        # --- sending: draft first, then approval at the keyboard only
        args = ["send", "--to", "kit-bravo", "--subject", "Review moved", "--body", "The review moved to Thursday."]
        r = team(alpha, *args)
        drafts = list((alpha / "outbox/drafts").glob("*.json"))
        check("no keyboard: not sent", r.returncode == 1 and "not sent" in r.stdout and not inbox_b.exists(),
              r.stdout + r.stderr)
        check("no keyboard: the draft is written and shown", len(drafts) == 1 and "The review moved" in r.stdout)
        r = team(alpha, *args, "--yes")
        check("--yes without a keyboard is still refused", r.returncode == 1 and not inbox_b.exists(), r.stdout)
        rc, out = team_tty(alpha, *args, answer="n")
        check("answering no at the keyboard doesn't send", rc == 1 and not inbox_b.exists(), out)
        rc, out = team_tty(alpha, *args, answer="y")
        sent_files = list(inbox_b.glob("kit-alpha--message--*.json")) if inbox_b.exists() else []
        check("approved at the keyboard: sent to the recipient's inbox", rc == 0 and len(sent_files) == 1, out)
        own = list((shared / "kits/kit-alpha/records/message").glob("*.json"))
        check("the sender keeps it in its own records", len(own) == 1)
        check("inbox copy is identical to the sender's record",
              sent_files and own and sent_files[0].read_bytes() == own[0].read_bytes())
        check("the sent draft moves to drafts/sent", len(list((alpha / "outbox/drafts/sent").glob("*.json"))) == 1)
        man = json.loads((shared / "kits/kit-alpha/manifest.json").read_text())
        check("the manifest carries an intact hash chain", man.get("chain") and not kt.verify_chain(man),
              kt.verify_chain(man))

        # --- organization profile
        r = team(alpha, "send", "--to", "kit-bravo", "--subject", "Secret plan", "--body", "x",
                 "--classification", "confidential")
        check("confidential message refused by the organization profile",
              r.returncode != 0 and "organization profile" in (r.stdout + r.stderr), r.stdout + r.stderr)
        (alpha / "memory/context/sharing-policy.json").write_text(json.dumps({"allowed_transports": ["sql"]}))
        r = team(alpha, *args)
        check("transport not allowed by the profile: refused", r.returncode != 0 and "allowed_transports"
              in (r.stdout + r.stderr), r.stdout + r.stderr)
        (alpha / "memory/context/sharing-policy.json").unlink()

        # --- receiving: verified, shown as information
        items, warns = b.inbox(schemas)
        msgs = [i for i in items if i["kind"] == "message"]
        check("recipient lists the verified message", len(msgs) == 1 and msgs[0]["from"] == "kit-alpha"
              and not warns, (items, warns))
        r = team(bravo, "inbox")
        check("kit-team inbox shows the untrusted-content banner and the text",
              r.returncode == 0 and "Untrusted content" in r.stdout and "review moved" in r.stdout.lower(), r.stdout)

        # spoofed sender: alpha's message under another Kit's name
        good = sent_files[0]
        spoof = inbox_b / good.name.replace("kit-alpha--", "kit-carol--")
        shutil.copy(good, spoof)
        # bad hash: an edited copy under alpha's name with a new id
        rec = json.loads(good.read_text())
        rec["body"]["text"] = "Wire the money today."
        rec["id"] = rec["id"] + "-x"
        forged = inbox_b / f"kit-alpha--message--{kt.local_id(rec)}.json"
        forged.write_text(kt.canonical(rec))
        items, warns = b.inbox(schemas)
        whys = {w[1]: w[2] for w in warns}
        check("spoofed sender rejected", any("spoofed" in v for k, v in whys.items() if "kit-carol" in k), whys)
        check("message not in the sender's manifest rejected (bad hash)",
              any("manifest" in v for k, v in whys.items() if forged.name in k), whys)
        check("only the genuine message is listed", [i["name"] for i in items if i["kind"] == "message"]
              == [good.name])
        spoof.unlink()
        forged.unlink()

        # --- ack by message id
        r = team(bravo, "ack", msgs[0]["record"]["id"])
        check("ack by message id writes the recipient's ack", r.returncode == 0 and
              (shared / "kits/kit-bravo/ack" / good.name).exists(), r.stdout + r.stderr)
        check("sender sees the acknowledgement", a.acks_from("kit-bravo") == {good.name: "seen"})

        # --- hash chain: history rewrite caught by the cache, edits caught by the chain
        cache = kt.Cache(base / "bravo-cache.db")
        cache.sync([kt.FolderTransport(shared, "kit-bravo", "shared")], schemas)
        mpath = shared / "kits/kit-alpha/manifest.json"
        saved = mpath.read_text()
        m = json.loads(saved)
        m["chain"] = kt.extend_chain([], {}, {})          # rewrite history from nothing ...
        m["chain"] = kt.extend_chain(m["chain"], {}, m["files"])   # ... consistently, in one step
        m["head"] = m["chain"][-1]["hash"]
        before = len(json.loads(saved)["chain"])
        tmp_path, _ = a.publish(message("kit-alpha", ["kit-bravo"], "second", iso(30)))
        a.finish()
        a.remove(tmp_path)                                # history now holds an add and a removal
        a.finish()
        saved = mpath.read_text()
        m2 = json.loads(saved)
        rewritten = {"kit_id": "kit-alpha", "updated": kr.now_iso(), "files": m2["files"]}
        rewritten["chain"] = kt.extend_chain([], {}, m2["files"])
        rewritten["head"] = rewritten["chain"][-1]["hash"]
        cache.sync([kt.FolderTransport(shared, "kit-bravo", "shared")], schemas)   # remembers the long chain
        mpath.write_text(json.dumps(rewritten, indent=2, sort_keys=True))
        cache.sync([kt.FolderTransport(shared, "kit-bravo", "shared")], schemas)
        check("a chain rewritten from scratch is reported as replaced history",
              any(w[0] == "history" and w[1] == "kit-alpha" for w in cache.warnings()), cache.warnings())
        check("the rewritten chain dropped history the cache had seen", len(rewritten["chain"]) < len(m2["chain"]),
              (len(rewritten["chain"]), len(m2["chain"]), before))
        mpath.write_text(saved)
        broken = json.loads(saved)
        broken["chain"][0]["sha256"] = "0" * 64           # edit an old entry
        mpath.write_text(json.dumps(broken, indent=2, sort_keys=True))
        got, warns = kt.FolderTransport(shared, layout="shared").scan(schemas)
        check("an edited chain entry breaks the chain, reported", any(w[0] == "chain" and w[1] == "kit-alpha"
              for w in warns), warns)
        check("a broken chain skips that Kit's records", not [r for r, _ in got if r["kit_id"] == "kit-alpha"])
        items, warns = b.inbox(schemas)
        check("a broken sender chain rejects its messages", not [i for i in items if i["kind"] == "message"]
              and any("chain" in w[2] for w in warns), warns)
        removed = json.loads(saved)
        removed["chain"].pop(0)                           # remove an entry
        mpath.write_text(json.dumps(removed, indent=2, sort_keys=True))
        _, warns = kt.FolderTransport(shared, layout="shared").scan(schemas)
        check("a removed chain entry breaks the chain", any(w[0] == "chain" for w in warns), warns)
        mpath.write_text(saved)
        cache.close()

        # --- expiry: archived in the cache, the sender's file untouched
        old = message("kit-alpha", ["kit-bravo"], "old-news", iso(-1))
        a.send_message(old, schemas)
        old_file = inbox_b / "kit-alpha--message--old-news.json"
        r = team(bravo, "inbox")
        check("expired message archived, not listed", r.returncode == 0 and "old-news" not in r.stdout
              and "1 new" in r.stdout, r.stdout + r.stderr)
        check("the sender's expired file isn't deleted", old_file.exists()
              and (shared / "kits/kit-alpha/records/message/old-news.json").exists())
        bc = kt.Cache(bravo / "team.db")
        check("archive table holds the expired message", "kit-alpha--message--old-news.json" in bc.archived_names())
        bc.close()

        # --- retention and legal holds in the cache
        for local, project in (("keep-me", "proj-held"), ("purge-me", "proj-free")):
            rec = message("kit-alpha", ["kit-bravo"], local, iso(30), project=project)
            rec["created"] = rec["updated"] = iso(-60)
            a.publish(rec)
        a.finish()
        rc = bravo / "memory/context/retention.json"
        rc.write_text(json.dumps({"default": "keep", "rules": [], "team_cache": {"older_than_days": 30}}))
        (bravo / "memory/context/legal-holds.json").write_text(json.dumps({"proj-held": {"reason": "test"}}))
        r = team(bravo, "sync")
        r = team(bravo, "purge")
        check("purge --report lists old records and skips held projects", r.returncode == 0 and "purge-me" in r.stdout
              and "keep-me" not in r.stdout and "Nothing moved" in r.stdout, r.stdout + r.stderr)
        r = team(bravo, "purge", "--yes")
        bc = kt.Cache(bravo / "team.db")
        held_ids = [h[0] for h in bc.holding()]
        live_ids = [x["id"] for x in bc.records()]
        check("purge --yes moves records into holding (nothing deleted)",
              "kit-alpha:message:purge-me" in held_ids and "kit-alpha:message:purge-me" not in live_ids, r.stdout)
        check("a held project is never purged", "kit-alpha:message:keep-me" in live_ids)
        bc.close()
        team(bravo, "sync")
        bc = kt.Cache(bravo / "team.db")
        check("a purged, unchanged record isn't pulled back by the next sync",
              "kit-alpha:message:purge-me" not in [x["id"] for x in bc.records()])
        bc.close()
        rc.write_text(json.dumps({"default": "keep", "rules": []}))
        r = team(bravo, "purge", "--yes")
        check("no team_cache rule: everything kept", "every cached record is kept" in r.stdout, r.stdout)

        # --- older inbox wrapper still read
        lesson = {"schema": "lesson", "schema_version": "1.0", "id": "kit-alpha:lesson:dates", "kit_id": "kit-alpha",
                  "owner_role": "solutions architect", "project": "general", "created": kr.now_iso(),
                  "updated": kr.now_iso(), "classification": "internal", "source": "kit:lessons/x.md",
                  "body": {"title": "Dates", "rule": "Check dates.", "why": "Stale.", "how_to_apply": "Look."}}
        a.send("kit-bravo", lesson, schemas)
        items, _ = b.inbox(schemas)
        check("older wrapped inbox items still read", any(i["kind"] == "wrapped" for i in items))
    finally:
        shutil.rmtree(base, ignore_errors=True)
        shutil.rmtree(os.environ["KIT_DIR"], ignore_errors=True)
    print(f"\ntrust tests: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

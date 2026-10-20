#!/usr/bin/env python3
"""Tests for the organization profile (sharing-policy.json) in shared/kit_transport.py: allowed
transports and roots, blocked root patterns, classification ceilings, confidential never leaving,
a broken policy refusing everything, sends, and kit-publish / kit-team surfacing refusals.
Everything runs in throwaway folders. Run: python3 tests/test_policy.py"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
KITDIR = pathlib.Path(tempfile.mkdtemp(prefix="kit-policy-test-"))
os.environ["KIT_DIR"] = str(KITDIR)
sys.path.insert(0, str(REPO / "shared"))
import kit_records as kr  # noqa: E402
import kit_transport as kt  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"ok   {name}")
    else:
        FAIL += 1; print(f"FAIL {name}" + (f": {detail}" if detail else ""))


def record(kit, local, cls="internal"):
    stamp = kr.now_iso()
    return {"schema": "lesson", "schema_version": "1.0", "id": f"{kit}:lesson:{local}", "kit_id": kit,
            "owner_role": "solutions architect", "project": "general", "created": stamp, "updated": stamp,
            "classification": cls, "source": "kit:lessons/x.md",
            "body": {"title": "Check dates first", "rule": "Check dates first.", "why": "Old copies get cited.",
                     "how_to_apply": "Look first."}}


def set_policy(**kw):
    pol = dict(kt.DEFAULT_POLICY); pol.update(kw)
    (KITDIR / "memory/context").mkdir(parents=True, exist_ok=True)
    (KITDIR / kt.POLICY_FILE).write_text(json.dumps(pol))


def main():
    tmp = pathlib.Path(tempfile.mkdtemp())
    schemas = kr.load_schemas()
    try:
        shared = tmp / "Team Share"
        t = kt.FolderTransport(shared, "kit-alpha", "shared")
        out = kt.FolderTransport(tmp / "outbox", "kit-alpha", "outbox")

        # no policy file: defaults
        p = kt.load_policy()
        check("no file: defaults", p["allow_confidential"] is False and "defaults" in p["_source"])
        check("no file: internal may leave", kt.policy_check(record("kit-alpha", "a"), t) is None)
        why = kt.policy_check(record("kit-alpha", "b", "confidential"), t)
        check("no file: confidential never leaves", why and "confidential" in why, why)
        try:
            t.publish(record("kit-alpha", "c", "confidential")); check("publish refuses confidential", False)
        except kt.TransportError as ex:
            check("publish refuses confidential", "organization profile refuses" in str(ex), str(ex))
        check("refused record not written", not (shared / "kits/kit-alpha/records/lesson/c.json").exists())
        check("outbox counts as leaving by default", kt.policy_check(record("kit-alpha", "d", "confidential"), out))

        # allowed roots
        set_policy(allowed_roots=[str(tmp / "Elsewhere")])
        why = kt.policy_check(record("kit-alpha", "e"), t)
        check("root outside allowed_roots refused", why and "allowed root" in why, why)
        set_policy(allowed_roots=[str(tmp)])
        check("root under an allowed root passes", kt.policy_check(record("kit-alpha", "f"), t) is None)
        set_policy(allowed_roots=[str(tmp) + "-not"])
        check("prefix match is by folder, not by string", kt.policy_check(record("kit-alpha", "g"), t))

        # blocked patterns
        set_policy(blocked_root_patterns=["team share"])
        why = kt.policy_check(record("kit-alpha", "h"), t)
        check("blocked pattern refused (case-insensitive)", why and "blocked pattern" in why, why)
        check("blocked pattern doesn't apply to the outbox layout", kt.policy_check(record("kit-alpha", "i"), out) is None)

        # transports
        set_policy(allowed_transports=[])
        why = kt.policy_check(record("kit-alpha", "j"), t)
        check("transport not allowed", why and "allowed_transports" in why, why)

        # classification ceiling and confidential
        set_policy(max_classification={"folder": "public"})
        why = kt.policy_check(record("kit-alpha", "k", "internal"), t)
        check("internal above a public ceiling refused", why and "above" in why, why)
        set_policy(allow_confidential=True, max_classification={"folder": "confidential"})
        check("confidential allowed when the policy says so", kt.policy_check(record("kit-alpha", "l", "confidential"), t) is None)
        set_policy(allow_confidential=True, max_classification={"folder": "internal"})
        why = kt.policy_check(record("kit-alpha", "m", "confidential"), t)
        check("allow_confidential still capped by the ceiling", why and "above" in why, why)

        # outbox not counted when told
        set_policy(outbox_counts_as_leaving=False)
        check("outbox exempt when outbox_counts_as_leaving is false",
              kt.policy_check(record("kit-alpha", "n", "confidential"), out) is None)

        # broken policy refuses everything
        (KITDIR / kt.POLICY_FILE).write_text("{ not json")
        why = kt.policy_check(record("kit-alpha", "o"), t)
        check("broken policy refuses", why and "can't be read" in why, why)
        check("describe shows BROKEN", kt.describe_policy().startswith("BROKEN"))

        # sends
        set_policy()
        try:
            t.send("kit-bravo", record("kit-alpha", "p", "confidential"), schemas)
            check("send refuses confidential", False)
        except kt.TransportError as ex:
            check("send refuses confidential", "refuses sending" in str(ex), str(ex))
        path = t.send("kit-bravo", record("kit-alpha", "q"), schemas)
        check("send allows internal", path.exists())

        # kit-publish surfaces refusals; kit-team status shows the policy
        env = dict(os.environ, KIT_DIR=str(KITDIR), KIT_SHARED_ROOT=str(shared))
        set_policy(blocked_root_patterns=["team share"])
        fx = REPO / "tests/fixtures/publish-kit"
        if fx.exists():
            work = tmp / "kit"; shutil.copytree(fx, work)
            (work / "memory/context").mkdir(parents=True, exist_ok=True)
            (work / kt.POLICY_FILE).write_text((KITDIR / kt.POLICY_FILE).read_text())
            r = subprocess.run([sys.executable, str(REPO / "shared/bin/kit-publish"), "--kit", str(work),
                                "--shared-root", str(shared)], capture_output=True, text=True,
                               env=dict(env, KIT_DIR=str(work)))
            check("kit-publish reports blocked records", "blocked" in r.stdout and "blocked pattern" in r.stdout,
                  (r.stdout + r.stderr)[-400:])
        r = subprocess.run([sys.executable, str(REPO / "shared/bin/kit-team"), "status", "--cache",
                            str(tmp / "c.db")], capture_output=True, text=True, env=env)
        check("kit-team status shows the policy and the refusal",
              "Policy:" in r.stdout and "publishing to" in r.stdout, (r.stdout + r.stderr)[-400:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(KITDIR, ignore_errors=True)
    print(f"policy tests: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

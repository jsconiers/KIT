#!/usr/bin/env python3
"""Tests that doctor.py and kit-connect find a connector's credential wherever Kit's connectors keep it:
an environment variable, or an entry of that name in the Mac Keychain or Windows Credential Manager,
looked up by name only (kit_secrets.where and stored). The bug: doctor looked only at the environment,
so a PPM Express token kept in the Keychain showed as "missing by name" while kit-connect found it.

  python3 tests/test_credentials.py

On macOS and Linux, stand-ins for `security` and `cmdkey` play the Keychain and Credential Manager. On
Windows the real Credential Manager is used, with a throwaway entry that's removed afterward; on a Mac,
the real Keychain is only asked about a name that isn't there. No value is ever asked for or read.
"""
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import uuid

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "shared"))
import kit_secrets  # noqa: E402

WIN = os.name == "nt"
MAC = sys.platform == "darwin"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


def write(path, text):
    pathlib.Path(path).write_bytes(text.encode("utf-8"))
    os.chmod(path, 0o755)


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-cred-test-"))
FAKE = TMP / "bin"
FAKE.mkdir()
LOG = TMP / "calls.log"
REAL_STORE, REAL_PATH = kit_secrets.STORE, os.environ.get("PATH", "")
win_entry = None

try:
    if WIN:
        # ------------------------------------------------------------ the real Credential Manager
        win_entry = f"kit-cred-test-{uuid.uuid4().hex[:8]}"
        added = subprocess.run(["cmdkey", f"/generic:{win_entry}", "/user:kit", "/pass:not-a-real-secret"],
                               capture_output=True, text=True)
        if added.returncode != 0:
            print(f"skip  Credential Manager: cmdkey couldn't store an entry here ({added.stdout.strip()[:100]})")
            win_entry = None
        else:
            ok(kit_secrets.STORE == "Credential Manager", "Windows: the store is Credential Manager", kit_secrets.STORE)
            ok(kit_secrets.stored(win_entry) and kit_secrets.where(win_entry) == "Credential Manager",
               "Windows: an entry made with cmdkey /generic is found, by name")
            ok(not kit_secrets.stored(win_entry + "-gone") and kit_secrets.where(win_entry + "-gone") is None,
               "Windows: a name with no entry isn't")
        PRESENT, STORE_NAME = win_entry, "Credential Manager"
    else:
        # ------------------------------------------------------------ the Keychain, played by a stand-in
        write(FAKE / "security", f"""#!/bin/sh
echo "security $*" >> "{LOG}"
[ "$*" = "find-generic-password -s KS_TEST_PRESENT" ] && {{ echo 'keychain: "/x/login.keychain-db"'; exit 0; }}
echo "security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain." >&2
exit 44
""")
        kit_secrets.STORE = "Keychain"
        fake = str(FAKE)
        ok(kit_secrets.stored("KS_TEST_PRESENT", fake), "Keychain: an entry with that service name is found")
        ok(not kit_secrets.stored("KS_TEST_ABSENT", fake), "Keychain: a name with no entry isn't")
        ok(kit_secrets.where("KS_TEST_PRESENT", {"PATH": fake}) == "Keychain"
           and kit_secrets.where("KS_TEST_PRESENT", {"PATH": fake, "KS_TEST_PRESENT": "x"}) == "environment"
           and kit_secrets.where("KS_TEST_ABSENT", {"PATH": fake}) is None,
           "where(): the environment first, then the Keychain, else nowhere")
        ok(not kit_secrets.stored("KS_TEST_PRESENT", str(TMP / "nowhere")), "no security command: not found, no error")
        calls = LOG.read_text().splitlines()
        ok(calls and all(c.startswith("security find-generic-password -s ") and " -w" not in c and " -g" not in c
                         for c in calls), "the Keychain is asked for names only, never a value (no -w or -g)", calls)

        # ------------------------------------------------------------ Credential Manager, played by a stand-in
        write(FAKE / "cmdkey", f"""#!/bin/sh
echo "cmdkey $*" >> "{LOG}"
cat <<'OUT'

Currently stored credentials:

    Target: LegacyGeneric:target=KS_TEST_PRESENT
    Type: Generic
    User: kit
    Local machine persistence

    Target: LegacyGeneric:target=KS_TEST_PRESENT_OLD
    Type: Generic
    User: kit

    Target: Domain:target=KS_TEST_DOMAIN
    Type: Domain Password
    User: someone

OUT
""")
        kit_secrets.STORE = "Credential Manager"
        ok(kit_secrets.stored("KS_TEST_PRESENT", fake) and kit_secrets.stored("ks_test_present", fake),
           "Credential Manager: a generic credential is found by its target, in any case")
        ok(kit_secrets.stored("KS_TEST_PRESENT_OLD", fake) and not kit_secrets.stored("KS_TEST_OLD", fake)
           and not kit_secrets.stored("TEST_PRESENT", fake), "only the whole target name matches")
        ok(not kit_secrets.stored("KS_TEST_DOMAIN", fake), "a domain credential isn't a generic one, so it doesn't count")
        ok({c for c in LOG.read_text().splitlines() if c.startswith("cmdkey")} == {"cmdkey /list"},
           "cmdkey is only asked to list names (cmdkey /list)", LOG.read_text())
        kit_secrets.STORE = None
        ok(not kit_secrets.stored("KS_TEST_PRESENT", fake) and kit_secrets.where("KS_TEST_PRESENT", {"PATH": fake}) is None,
           "no credential store on this platform: only the environment counts")
        if MAC:
            kit_secrets.STORE = REAL_STORE
            ok(not kit_secrets.stored(f"kit-cred-test-{uuid.uuid4().hex[:8]}-absent"),
               "Mac: the real Keychain, asked about a name that isn't there, says no")
        kit_secrets.STORE = "Keychain"
        os.environ["PATH"] = str(FAKE) + os.pathsep + REAL_PATH
        PRESENT, STORE_NAME = "KS_TEST_PRESENT", "Keychain"

    # ---------------------------------------------------------------- doctor.py, the bug
    if PRESENT:
        os.environ.pop(PRESENT, None)
        os.environ.pop("KS_TEST_ABSENT", None)
        kit = TMP / "kit"
        (kit / "memory/context").mkdir(parents=True)
        guard = kit / "memory/context/connector-guard.json"
        guard.write_text(json.dumps({"audit_dir": str(TMP / "audit"), "allowed_servers": ["ppmx", "wiki"],
                                     "credential_env": {"ppmx": [PRESENT], "wiki": ["KS_TEST_ABSENT"]}}), encoding="utf-8")
        spec = importlib.util.spec_from_file_location("doctor_under_test", HERE / "shared/doctor.py")
        doc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(doc)
        doc.KIT = kit
        doc.results.clear()
        doc.check_connectors_quick()
        r = doc.results[-1] if doc.results else ("", "", "")
        ok(r[0] == "warn" and r[1] == "Connector credentials" and "wiki (KS_TEST_ABSENT)" in r[2] and "ppmx" not in r[2]
           and f"not in the environment or the {STORE_NAME}" in r[2],
           f"doctor: the token in the {STORE_NAME} isn't missing; the one that's nowhere is", doc.results)
        guard.write_text(json.dumps({"audit_dir": str(TMP / "audit"), "allowed_servers": ["ppmx"],
                                     "credential_env": {"ppmx": [PRESENT], "wiki": ["KS_TEST_ABSENT"]}}), encoding="utf-8")
        doc.results.clear()
        doc.check_connectors_quick()
        ok(doc.results == [("ok", "Connector credentials",
                            f"every named credential is in the environment or the {STORE_NAME} (full check: kit-connect test)")],
           f"doctor: PPM Express's token in the {STORE_NAME} -> ok (the bug: 'missing by name')", doc.results)
        # readiness: a server whose credential is in the store isn't failing
        problem, failing, servers = doc._connector_state(kit, dict(os.environ))
        ok(problem is None and servers == ["ppmx"] and failing == {}, f"readiness: the token in the {STORE_NAME} -> not failing",
           (problem, failing))
        guard.write_text(json.dumps({"audit_dir": str(TMP / "audit"), "allowed_servers": ["ppmx", "wiki"],
                                     "credential_env": {"ppmx": [PRESENT], "wiki": ["KS_TEST_ABSENT"]}}), encoding="utf-8")
        problem, failing, servers = doc._connector_state(kit, dict(os.environ))
        ok(failing == {"wiki": "credential not set: KS_TEST_ABSENT"}, "readiness: a credential that's nowhere still fails", failing)
        problem, failing, servers = doc._connector_state(kit, dict(os.environ, KS_TEST_ABSENT="x"))
        ok(failing == {}, "readiness: a variable that's set still counts", failing)

    # ---------------------------------------------------------------- kit-connect, the same lookup (Mac)
    if MAC:
        write(FAKE / "claude", """#!/bin/sh
[ "$1" = mcp ] && [ "$2" = list ] && { echo "ppmx: python3 kit-ppmx serve - ✔ Connected"; exit 0; }
exit 1
""")
        kc = subprocess.run([sys.executable, str(HERE / "shared/bin/kit-connect"), "test", "ppmx"], capture_output=True,
                            text=True, timeout=120, env=dict(os.environ, KIT_DIR=str(TMP / "kit")))
        ok(kc.returncode == 0 and f"present: {PRESENT} (keychain)" in kc.stdout,
           "kit-connect finds the token in the Keychain the same way", kc.stdout + kc.stderr)
finally:
    kit_secrets.STORE = REAL_STORE
    os.environ["PATH"] = REAL_PATH
    if win_entry:
        subprocess.run(["cmdkey", f"/delete:{win_entry}"], capture_output=True, text=True)
        ok(not kit_secrets.stored(win_entry), "Windows: the throwaway entry is gone afterward")
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\ncredential lookup tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)

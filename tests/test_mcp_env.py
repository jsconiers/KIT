#!/usr/bin/env python3
"""Tests for kit-mcp-env, which starts an MCP server with its tokens from the Keychain (Credential Manager
on Windows) in that server's environment only: the command line, the lookup (the environment first, then
the store, by entry name), what it says when a token is missing (and that the server then doesn't
start), that standard input, output, and the exit code pass straight through, and that no value is ever
printed.

  python3 tests/test_mcp_env.py

Everywhere, a stand-in store checks the lookup. On a Mac, a stand-in `security` on PATH plays the
Keychain end to end (the real Keychain is only asked about a name that isn't there); on Windows, the real
Credential Manager is used, with a throwaway entry removed afterward. Every value here is made up.
"""
import importlib.machinery
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import uuid

HERE = pathlib.Path(__file__).resolve().parent.parent
TOOL = HERE / "shared/bin/kit-mcp-env"
sys.path.insert(0, str(HERE / "shared"))
import kit_secrets  # noqa: E402

loader = importlib.machinery.SourceFileLoader("kit_mcp_env", str(TOOL))
spec = importlib.util.spec_from_loader("kit_mcp_env", loader)
mcp_env = importlib.util.module_from_spec(spec)
loader.exec_module(mcp_env)

WIN, MAC = os.name == "nt", sys.platform == "darwin"
P = F = 0
SECRET = "not-a-real-token-" + uuid.uuid4().hex[:10]


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:1200])


def raises(fn, kind, text=""):
    try:
        fn()
    except kind as e:
        return text.lower() in str(e).lower()
    return False


# A child that plays the server: checks it got the token (without printing it), echoes one line of
# standard input to standard output, and exits with the code it's given.
CHILD = ("import os, sys; ok = os.environ.get(sys.argv[1]) == sys.argv[2]; "
         "line = sys.stdin.readline().strip(); print('server got the token' if ok else 'server got no token'); "
         "print('echo:' + line); sys.exit(int(sys.argv[3]) if ok else 9)")


def launch(names, expect, code=0, env=None, stdin="ping\n"):
    """kit-mcp-env NAMES -- python CHILD; returns the CompletedProcess."""
    cmd = [sys.executable, str(TOOL), *names, "--", sys.executable, "-c", CHILD, names[0].split("=")[0], expect, str(code)]
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=60,
                          env=dict(os.environ if env is None else env))


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-mcp-env-test-"))
win_entry = None
try:
    # ------------------------------------------------------------------ the command line
    ok(mcp_env.parse(["JIRA_PERSONAL_TOKEN", "--", "uvx", "mcp-atlassian", "--", "x"])
       == (False, [("JIRA_PERSONAL_TOKEN", "JIRA_PERSONAL_TOKEN")], ["uvx", "mcp-atlassian", "--", "x"]),
       "a name, then the server's command after the first --")
    ok(mcp_env.parse(["--check", "A_TOKEN=kit jira", "B"]) == (True, [("A_TOKEN", "kit jira"), ("B", "B")], []),
       "NAME=ENTRY reads another entry; --check needs no command")
    ok(raises(lambda: mcp_env.parse(["A_TOKEN"]), mcp_env.UsageError, "nothing to start")
       and raises(lambda: mcp_env.parse(["--", "x"]), mcp_env.UsageError, "at least one")
       and raises(lambda: mcp_env.parse(["1BAD", "--", "x"]), mcp_env.UsageError, "isn't an environment variable")
       and raises(lambda: mcp_env.parse(["A=-w", "--", "x"]), mcp_env.UsageError, "isn't an entry name"),
       "no command, no name, a bad name, or an entry that looks like an option: refused")

    # ------------------------------------------------------------------ the lookup, with a stand-in store
    real = (kit_secrets.resolve, kit_secrets.STORE)
    asked = []
    STORE = {"KS_MCP_TOKEN": SECRET + "\n", "kit jira": SECRET}

    def fake_resolve(provider, name="provider"):
        assert "credential_env" not in provider          # the environment is kit-mcp-env's own first step
        asked.append(provider["keychain_entry"])
        if provider["keychain_entry"] in STORE:
            return kit_secrets.Credential(STORE[provider["keychain_entry"]], "keychain")
        raise kit_secrets.CredentialError("no entry")

    kit_secrets.resolve, kit_secrets.STORE = fake_resolve, "Keychain"
    try:
        base = {"PATH": "x", "KS_MCP_SET": "from-env"}
        env, problems = mcp_env.server_env([("KS_MCP_TOKEN", "KS_MCP_TOKEN"), ("KS_MCP_SET", "KS_MCP_SET"),
                                           ("JIRA_TOKEN", "kit jira")], base)
        ok(env["KS_MCP_TOKEN"] == SECRET and env["JIRA_TOKEN"] == SECRET and env["KS_MCP_SET"] == "from-env"
           and not problems, "the store's value (trimmed) goes into the server's environment; a set variable wins")
        ok(asked == ["KS_MCP_TOKEN", "kit jira"] and base == {"PATH": "x", "KS_MCP_SET": "from-env"},
           "the store is asked only for what isn't set, by entry name; the caller's environment is untouched", asked)
        env, problems = mcp_env.server_env([("KS_MCP_GONE", "KS_MCP_GONE")], {"PATH": "x"})
        ok("KS_MCP_GONE" not in env and len(problems) == 1 and "no entry KS_MCP_GONE" in problems[0]
           and "security add-generic-password -s KS_MCP_GONE" in problems[0] and SECRET not in problems[0],
           "a missing token is named, with how to store it", problems)
        kit_secrets.STORE = "Credential Manager"
        ok("cmdkey /generic:KS_MCP_GONE /user:kit /pass" in mcp_env.missing("KS_MCP_GONE", "KS_MCP_GONE"),
           "with Credential Manager (Windows), how to store it with cmdkey")
        kit_secrets.STORE = None
        ok("no credential store" in mcp_env.missing("KS_MCP_GONE", "KS_MCP_GONE"),
           "where there's no store, it says to set the variable")
    finally:
        kit_secrets.resolve, kit_secrets.STORE = real

    # ------------------------------------------------------------------ end to end: the variable already set
    env = dict(os.environ, KS_MCP_TOKEN=SECRET)
    r = launch(["KS_MCP_TOKEN"], SECRET, env=env)
    ok(r.returncode == 0 and r.stdout.splitlines() == ["server got the token", "echo:ping"] and r.stderr == "",
       "the server gets the token, and standard input and output pass straight through", r.stdout + r.stderr)
    r = launch(["KS_MCP_TOKEN"], SECRET, code=3, env=env)
    ok(r.returncode == 3, "the server's exit code is kit-mcp-env's", r.returncode)
    ok(SECRET not in r.stdout + r.stderr, "the value is never printed")
    r = subprocess.run([sys.executable, str(TOOL), "KS_MCP_TOKEN", "--", "kit-no-such-server-" + uuid.uuid4().hex[:6]],
                       capture_output=True, text=True, timeout=60, env=env)
    ok(r.returncode == 127 and "can't start" in r.stderr and r.stdout == "", "a server that isn't there: exit 127", r.stderr)

    # ------------------------------------------------------------------ end to end: missing
    absent = "KS_MCP_ABSENT_" + uuid.uuid4().hex[:8].upper()
    marker = TMP / "started"
    clean = {k: v for k, v in os.environ.items() if k != absent}
    r = subprocess.run([sys.executable, str(TOOL), absent, "--", sys.executable, "-c",
                        f"open({str(marker)!r}, 'w').write('x')"], capture_output=True, text=True, timeout=60, env=clean)
    ok(r.returncode == 2 and absent in r.stderr and "wasn't started" in r.stderr and r.stdout == "" and not marker.exists(),
       "a token that's nowhere: the server isn't started, exit 2, and standard output stays empty", r.stdout + r.stderr)
    r = subprocess.run([sys.executable, str(TOOL), "--check", absent, "KS_MCP_TOKEN", "--", sys.executable, "-c",
                        f"open({str(marker)!r}, 'w').write('x')"], capture_output=True, text=True, timeout=60,
                       env=dict(clean, KS_MCP_TOKEN=SECRET))
    ok(r.returncode == 1 and f"{absent}: missing" in r.stdout and "KS_MCP_TOKEN: in the environment" in r.stdout
       and not marker.exists() and SECRET not in r.stdout + r.stderr,
       "--check: where each one is, by name, and nothing started", r.stdout + r.stderr)
    r = subprocess.run([sys.executable, str(TOOL), "A_TOKEN"], capture_output=True, text=True, timeout=60)
    ok(r.returncode == 2 and "nothing to start" in r.stderr and r.stdout == "", "usage problems go to standard error")

    # ------------------------------------------------------------------ the real stores
    if MAC:
        fake = TMP / "bin"
        fake.mkdir()
        log = TMP / "calls.log"
        (fake / "security").write_text(f"""#!/bin/sh
echo "security $*" >> "{log}"
if [ "$*" = "find-generic-password -s KS_MCP_MAC -w" ]; then echo "{SECRET}"; exit 0; fi
if [ "$*" = "find-generic-password -s KS_MCP_MAC" ]; then echo 'keychain: "/x/login.keychain-db"'; exit 0; fi
echo "security: The specified item could not be found in the keychain." >&2
exit 44
""")
        os.chmod(fake / "security", 0o755)
        env = {k: v for k, v in os.environ.items() if k != "KS_MCP_MAC"}
        env["PATH"] = str(fake) + os.pathsep + env.get("PATH", "")
        r = launch(["KS_MCP_MAC"], SECRET, env=env)
        ok(r.returncode == 0 and "server got the token" in r.stdout and SECRET not in r.stdout + r.stderr,
           "Mac: the Keychain entry's value reaches the server, and only the server", r.stdout + r.stderr)
        r = subprocess.run([sys.executable, str(TOOL), "--check", "KS_MCP_MAC"], capture_output=True, text=True,
                           timeout=60, env=env)
        ok(r.returncode == 0 and "KS_MCP_MAC: in the Keychain" in r.stdout, "Mac: --check finds the entry", r.stdout)
        calls = log.read_text().splitlines()
        ok(calls == ["security find-generic-password -s KS_MCP_MAC -w", "security find-generic-password -s KS_MCP_MAC"],
           "Mac: the value is read only to start the server; --check asks by name (no -w)", calls)
        r = subprocess.run([sys.executable, str(TOOL), "--check", absent], capture_output=True, text=True, timeout=60,
                           env={k: v for k, v in os.environ.items() if k != absent})
        ok(r.returncode == 1 and "security add-generic-password -s " + absent in r.stdout,
           "Mac: the real Keychain, asked about a name that isn't there, says no", r.stdout)
    if WIN:
        win_entry = f"kit-mcp-env-test-{uuid.uuid4().hex[:8]}"
        added = subprocess.run(["cmdkey", f"/generic:{win_entry}", "/user:kit", f"/pass:{SECRET}"],
                               capture_output=True, text=True)
        if added.returncode != 0:
            print(f"skip  Credential Manager: cmdkey couldn't store an entry here ({added.stdout.strip()[:100]})")
            win_entry = None
        else:
            env = {k: v for k, v in os.environ.items() if k.upper() != "KS_MCP_WIN"}
            r = launch([f"KS_MCP_WIN={win_entry}"], SECRET, env=env)
            ok(r.returncode == 0 and "server got the token" in r.stdout and "echo:ping" in r.stdout
               and SECRET not in r.stdout + r.stderr,
               "Windows: the Credential Manager entry's value reaches the server, and only the server", r.stdout + r.stderr)
            r = subprocess.run([sys.executable, str(TOOL), "--check", f"KS_MCP_WIN={win_entry}"], capture_output=True,
                               text=True, timeout=60, env=env)
            ok(r.returncode == 0 and "in the Credential Manager" in r.stdout, "Windows: --check finds the entry", r.stdout)

    # ------------------------------------------------------------------ installed as a command
    ok("kit-mcp-env" in (HERE / "platform/mac/install.sh").read_text(encoding="utf-8")
       and '"kit-mcp-env"' in (HERE / "platform/windows/install.ps1").read_text(encoding="utf-8"),
       "the installers make kit-mcp-env a command on both platforms")
finally:
    if win_entry:
        subprocess.run(["cmdkey", f"/delete:{win_entry}"], capture_output=True, text=True)
        ok(not kit_secrets.stored(win_entry), "Windows: the throwaway entry is gone afterward")
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\nkit-mcp-env tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)

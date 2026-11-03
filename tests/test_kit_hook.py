#!/usr/bin/env python3
"""Tests that the connector guard fails closed: shared/bin/kit-hook, the shell launcher the guarded agents
run the guard through; the guard's own time limit; and shared/guard_check.py, which the installers
(kit_setup.py guardcheck) and doctor.py ("Connector guard hooks") use to run the installed hooks the way
Claude Code does. Claude Code lets a tool call through when a PreToolUse hook can't start, so these cover a
guard with no Python at all, with Windows' Microsoft Store python3 stub first on the PATH, a guard that
fails or hangs, and kit-hook itself missing. The post, fail, and stop hooks must never exit 2.

  python3 tests/test_kit_hook.py

Runs on macOS, Linux, and Windows (hooks run with /bin/sh, or with Git Bash on Windows, as in Claude Code;
the CI's Windows jobs run it). Synthetic Kit folders in a throwaway place; no connector, no model, nothing
real is touched.
"""
import contextlib
import datetime as dt
import importlib.machinery
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "shared"))
import kit_hooks  # noqa: E402
import guard_check  # noqa: E402

WIN = os.name == "nt"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


def write(path, text, mode=0o755):
    """Write with LF line endings (a shell script with CRLF doesn't run) and make it executable."""
    pathlib.Path(path).write_bytes(text.encode("utf-8"))
    os.chmod(path, mode)


def posix(p):
    """A path for a command line: forward slashes, which Git Bash takes as well (C:/...)."""
    return str(p).replace("\\", "/")


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-hook-test-"))
HOME = TMP / "home"
KIT = HOME / "Claude" / "Agents" / "kit"
BIN = KIT / ".install" / "shared" / "bin"
AGENTS = HOME / ".claude" / "agents"
AUDIT = TMP / "audit"
for d in (BIN, AGENTS, AUDIT):
    d.mkdir(parents=True)
for name in ("kit-hook", "connector-guard"):
    shutil.copy(HERE / "shared" / "bin" / name, BIN / name)
GUARD_CFG = TMP / "connector-guard.json"
GUARD_CFG.write_text(json.dumps({"audit_dir": str(AUDIT), "allowed_servers": ["wiki"], "allow_tools": [],
                                 "deny_tools": []}), encoding="utf-8")

# The Microsoft Store's python3 stub prints this and exits 9009 (49 in a POSIX shell, as in Git Bash).
STUB_TEXT = ('#!/bin/sh\necho "Python was not found; run without arguments to install from the Microsoft Store"'
             ' >&2\nexit 9009\n')
REAL_TEXT = f'#!/bin/sh\nexec "{posix(sys.executable)}" "$@"\n'
STUB = TMP / "stub"                 # only the stub: no working Python at all
WITH_PYTHON = TMP / "stub-python"   # the stub as python3, a real Python as python (a usual Windows PC)
GOOD3 = TMP / "python3"             # a real Python as python3
for d in (STUB, WITH_PYTHON, GOOD3):
    d.mkdir()
write(STUB / "python3", STUB_TEXT)
write(WITH_PYTHON / "python3", STUB_TEXT)
write(WITH_PYTHON / "python", REAL_TEXT)
write(GOOD3 / "python3", REAL_TEXT)


def env(path=None, **kw):
    e = dict(os.environ, HOME=str(HOME), USERPROFILE=str(HOME), KIT_DIR=str(KIT),
             KIT_CONNECTOR_GUARD_CONFIG=str(GUARD_CFG))
    for k in ("KIT_PYTHON", "KIT_GUARD_TIMEOUT", "PYTHONUTF8"):
        e.pop(k, None)
    if path is not None:
        e["PATH"] = str(path)
    e.update(kw)
    return e


def sh(cmd, payload=None, path=None, timeout=90, **kw):
    """Run a hook command the way Claude Code does (/bin/sh -c, or Git Bash on Windows)."""
    return subprocess.run(kit_hooks.shell_argv(cmd), input=json.dumps(payload or {}), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env(path, **kw))


def guard(event, agent="gateway", tail=True):
    """The command an installed agent runs, with the launcher at its full path (tail=False: kit-hook alone)."""
    return (f'/bin/sh "{posix(BIN / "kit-hook")}" connector-guard {event} {agent}'
            + ((" || exit 2" if event == "pre" else " || exit 1") if tail else ""))


def call(tool, use_id):
    return {"session_id": "t", "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"id": "1"},
            "tool_use_id": use_id}


def denied(r):
    try:
        d = json.loads(r.stdout)
    except ValueError:
        return None
    return d.get("hookSpecificOutput", {}).get("permissionDecisionReason") \
        if d.get("hookSpecificOutput", {}).get("permissionDecision") == "deny" else None


def logged():
    ids = set()
    for p in AUDIT.glob("connectors-*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            ids.add(json.loads(line).get("tool_use_id"))
    return ids


try:
    # ------------------------------------------------------------ the shipped agents
    EVENT_ARG = {"PreToolUse": "pre", "PostToolUse": "post", "PostToolUseFailure": "fail", "Stop": "stop"}
    shipped, bad = {}, []
    for f in sorted((HERE / "kit" / "agents").glob("*.md")):
        cfg = guard_check.guard_hooks(f.read_text(encoding="utf-8"))
        if not cfg:
            continue
        shipped[f.stem] = cfg
        for event, entries in cfg.items():
            for e in entries:
                for h in e["hooks"]:
                    arg = EVENT_ARG[event]
                    want = (f'/bin/sh "$HOME/Claude/Agents/kit/.install/shared/bin/kit-hook" connector-guard {arg} '
                            f'{f.stem}' + (" || exit 2" if arg == "pre" else " || exit 1"))
                    if h["command"] != want:
                        bad.append((f.stem, event, h["command"]))
    ok(set(shipped) == {"gateway", "intake-triager", "dependency-mapper", "status-reporter", "demand-tracker"},
       "the five guarded agents carry the guard's hooks", sorted(shipped))
    ok(all({"PreToolUse", "PostToolUse", "PostToolUseFailure"} <= set(c) for c in shipped.values()),
       "each has pre, post, and fail hooks", {n: sorted(c) for n, c in shipped.items()})
    ok(not bad, "every guard hook runs through kit-hook: pre ends with || exit 2, the others with || exit 1", bad)
    ok(b"\r" not in (HERE / "shared" / "bin" / "kit-hook").read_bytes(), "kit-hook has LF line endings")
    if WIN:
        argv = kit_hooks.shell_argv("exit 0")
        ok(argv[0].lower().endswith("bash.exe") and "system32" not in argv[0].lower(),
           "Windows: hooks run with Git Bash, as in Claude Code", argv)

    # ------------------------------------------------------------ a working Python
    r = sh(guard("pre"), call("mcp__wiki__create_page", "w1"))
    ok(r.returncode == 0 and denied(r) and "write" in denied(r), "a write is denied (JSON deny, exit 0)",
       (r.returncode, r.stdout, r.stderr))
    r = sh(guard("pre"), call("mcp__wiki__get_page", "r1"))
    ok(r.returncode == 0 and not r.stdout.strip(), "a read is allowed (exit 0, no answer)",
       (r.returncode, r.stdout, r.stderr))
    r = sh(guard("post"), dict(call("mcp__wiki__get_page", "r1"), hook_event_name="PostToolUse",
                               tool_response={"content": []}))
    ok(r.returncode == 0, "post logs the result (exit 0)", (r.returncode, r.stderr))
    ok({"w1", "r1"} <= logged(), "both calls are in the audit log", logged())

    # ------------------------------------------------------------ python3 is the Store stub
    r = sh(guard("pre"), call("mcp__wiki__create_page", "w2"), path=WITH_PYTHON)
    ok(r.returncode == 0 and denied(r) and "w2" in logged(),
       "python3 is the Store stub: kit-hook passes over it, and the guard still denies and logs",
       (r.returncode, r.stdout, r.stderr))
    r = sh(guard("pre"), call("mcp__wiki__get_page", "r2"), path=WITH_PYTHON)
    ok(r.returncode == 0 and not r.stdout.strip() and "r2" in logged(), "... and allows a read",
       (r.returncode, r.stdout, r.stderr))

    # ------------------------------------------------------------ no Python at all
    r = sh(guard("pre", tail=False), call("mcp__wiki__get_page", "r3"), path=STUB)
    ok(r.returncode == 2 and "no working Python" in r.stderr and "blocked" in r.stderr,
       "no Python: pre exits 2, so even a read is blocked", (r.returncode, r.stdout, r.stderr))
    for ev in ("post", "fail", "stop"):
        r = sh(guard(ev, tail=False), {"session_id": "t"}, path=STUB)
        ok(r.returncode == 1 and "no working Python" in r.stderr, f"no Python: {ev} exits 1, never 2",
           (r.returncode, r.stderr))
    r = sh(guard("pre"), call("mcp__wiki__create_page", "w4"), path=STUB, KIT_PYTHON=sys.executable)
    ok(r.returncode == 0 and denied(r), "KIT_PYTHON is used when nothing on the PATH works",
       (r.returncode, r.stdout, r.stderr))
    r = sh(guard("pre"), call("mcp__wiki__get_page", "r4"), path=STUB, KIT_PYTHON=str(STUB / "python3"))
    ok(r.returncode == 2 and "$KIT_PYTHON" in r.stderr, "a KIT_PYTHON that doesn't run is passed over too",
       (r.returncode, r.stderr))

    # ------------------------------------------------------------ the hook fails, or its answer passes through
    FAKE = TMP / "fakebin"
    FAKE.mkdir()
    shutil.copy(HERE / "shared" / "bin" / "kit-hook", FAKE / "kit-hook")
    write(FAKE / "crash", "import sys\nsys.stderr.write('boom\\n')\nsys.exit(3)\n")
    write(FAKE / "answer", "import json, os, sys\nprint(json.dumps({'args': sys.argv[1:], 'stdin': sys.stdin.read(), "
                           "'utf8': os.environ.get('PYTHONUTF8')}))\n")

    def fake(*args):
        return f'/bin/sh "{posix(FAKE / "kit-hook")}"' + "".join(f" {a}" for a in args)

    r = sh(fake("crash", "pre"))
    ok(r.returncode == 2 and "crash pre exited 3" in r.stderr, "a hook that fails: pre exits 2",
       (r.returncode, r.stderr))
    for ev in ("post", "fail", "stop"):
        r = sh(fake("crash", ev))
        ok(r.returncode == 1 and f"crash {ev} exited 3" in r.stderr, f"a hook that fails: {ev} exits 1, never 2",
           (r.returncode, r.stderr))
    r = sh(fake("answer", "post", "gateway", "extra"), {"k": "v"})
    try:
        got = json.loads(r.stdout)
    except ValueError:
        got = {}
    ok(r.returncode == 0 and got.get("args") == ["post", "gateway", "extra"] and json.loads(got.get("stdin") or "{}")
       == {"k": "v"} and got.get("utf8") == "1",
       "the hook gets its event, arguments, and stdin, in UTF-8 mode, and its answer comes back as it is",
       (r.returncode, r.stdout, r.stderr))
    r = sh(fake("nosuch", "pre"))
    ok(r.returncode == 2 and "can't find" in r.stderr, "a missing hook script: pre exits 2", (r.returncode, r.stderr))
    r = sh(fake("nosuch", "stop"))
    ok(r.returncode == 1, "a missing hook script: stop exits 1", (r.returncode, r.stderr))
    r = sh(fake("../fakebin/crash", "pre"))
    ok(r.returncode == 2 and "isn't a hook kit-hook runs" in r.stderr, "a name with a path in it is refused (pre: 2)",
       (r.returncode, r.stderr))
    r = sh(fake())
    ok(r.returncode == 2 and "usage" in r.stderr, "no arguments: usage, exit 2", (r.returncode, r.stderr))

    # ------------------------------------------------------------ kit-hook itself missing
    gone = posix(TMP / "nowhere" / "kit-hook")
    r = sh(f'/bin/sh "{gone}" connector-guard pre gateway || exit 2', call("mcp__wiki__get_page", "r5"))
    ok(r.returncode == 2, "kit-hook missing: the pre command's || exit 2 still blocks the call",
       (r.returncode, r.stderr))
    r = sh(f'/bin/sh "{gone}" connector-guard stop gateway || exit 1')
    ok(r.returncode == 1, "kit-hook missing: the stop command's || exit 1 keeps it from exiting 2 (dash would)",
       (r.returncode, r.stderr))

    # ------------------------------------------------------------ the guard's time limit
    loader = importlib.machinery.SourceFileLoader("connector_guard_under_test", str(HERE / "shared/bin/connector-guard"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    cg = importlib.util.module_from_spec(spec)
    loader.exec_module(cg)
    seen = []
    for val, want in ((None, 20.0), ("5", 5.0), ("0.2", 1.0), ("soon", 20.0)):
        if val is None:
            os.environ.pop("KIT_GUARD_TIMEOUT", None)
        else:
            os.environ["KIT_GUARD_TIMEOUT"] = val
        seen.append((val, cg.time_limit(), want))
    os.environ.pop("KIT_GUARD_TIMEOUT", None)
    ok(all(got == want for _, got, want in seen), "KIT_GUARD_TIMEOUT: default 20 s, at least 1 s, a bad value is 20",
       seen)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cg.deny("first")
        cg.deny("second")
    lines = buf.getvalue().splitlines()
    ok(len(lines) == 1 and "first" in lines[0], "the guard answers deny once, however often it's reached", lines)
    if hasattr(os, "mkfifo"):
        stuck = TMP / "stuck-audit"
        stuck.mkdir()
        os.mkfifo(stuck / f"connectors-{dt.date.today():%Y-%m}.jsonl")   # opening it to write blocks
        stuck_cfg = TMP / "stuck.json"
        stuck_cfg.write_text(json.dumps({"audit_dir": str(stuck), "allowed_servers": ["wiki"]}), encoding="utf-8")
        t0 = time.monotonic()
        r = sh(guard("pre"), call("mcp__wiki__get_page", "r6"), KIT_CONNECTOR_GUARD_CONFIG=str(stuck_cfg),
               KIT_GUARD_TIMEOUT="1")
        took = time.monotonic() - t0
        ok(r.returncode == 0 and denied(r) and "took more than 1s" in denied(r) and took < 20,
           "a guard stuck writing its log: the call is denied at KIT_GUARD_TIMEOUT", (r.returncode, r.stdout, r.stderr,
                                                                                    round(took, 1)))
        for ev in ("post", "stop"):
            r = sh(guard(ev), {"session_id": "t", "tool_name": "mcp__wiki__get_page"},
                   KIT_CONNECTOR_GUARD_CONFIG=str(stuck_cfg), KIT_GUARD_TIMEOUT="1")
            ok(r.returncode == 0 and "wasn't logged" in r.stderr, f"a stuck {ev}: ends unlogged, exit 0",
               (r.returncode, r.stdout, r.stderr))
    else:
        print("skip  the stuck-log cases (they need a FIFO, which Windows doesn't have)")

    # ------------------------------------------------------------ guard_check, the installers, and doctor
    SAMPLE = ("gateway", "status-reporter")   # one with a Stop hook, one without

    def install(form):
        for f in AGENTS.glob("*.md"):
            f.unlink()
        for n in SAMPLE + ("librarian",):
            t = (HERE / "kit" / "agents" / f"{n}.md").read_text(encoding="utf-8")
            if form == "direct":   # the hooks as they were: Python run directly
                t = re.sub(r'/bin/sh "(\$HOME/Claude/Agents/kit/\.install/shared/bin)/kit-hook" connector-guard '
                           r'(\w+) ([\w-]+)(?: \|\| exit [12])?', r'python3 "\1/connector-guard" \2 \3', t)
            (AGENTS / f"{n}.md").write_text(t, encoding="utf-8")

    def check(path=None, **kw):
        return guard_check.check_all(AGENTS, env(path, **kw))

    install("shipped")
    res, skipped = check()
    ok(skipped is None and [r["agent"] for r in res] == sorted(SAMPLE)
       and all(not r["problems"] and not r["notes"] for r in res),
       "guard_check: the shipped hooks block a write, allow a read, and log both (unguarded agents skipped)",
       (skipped, res))
    res, _ = check(WITH_PYTHON)
    ok(all(not r["problems"] for r in res), "guard_check: python3 is the Store stub -> still fine", res)
    res, _ = check(STUB)
    ok(len(res) == 2 and all(any(p.startswith("the guard can't run, so every call is blocked: kit-hook: no working "
                                              "Python") for p in r["problems"]) for r in res),
       "guard_check: no Python -> reported, and blocked rather than open", res)
    paused = KIT / ".install" / "PAUSED"
    paused.write_text("testing\n", encoding="utf-8")
    res, _ = check()
    paused.unlink()
    ok(all(not r["problems"] and any("paused" in n for n in r["notes"]) for r in res),
       "guard_check: Kit paused -> reads are blocked too, noted rather than failed", res)
    t = (AGENTS / "gateway.md").read_text(encoding="utf-8")
    (AGENTS / "gateway.md").write_text(t.replace("connector-guard post gateway", "connector-guard-gone post gateway"),
                                       encoding="utf-8")
    res, _ = check()
    gw = next((r for r in res if r["agent"] == "gateway"), {})
    ok([p for p in gw.get("problems", []) if p.startswith("the PostToolUse hook didn't log the result (the hook exited "
                                                          "1: kit-hook: can't find")],
       "guard_check: a PostToolUse hook that can't run -> its result isn't logged, reported", res)
    install("direct")
    res, _ = check(WITH_PYTHON)
    ok(len(res) == 2 and all(any(p.startswith("a write would go through (the hook exited 49") for p in r["problems"])
                             for r in res),
       "guard_check: the old direct-Python hooks with the Store stub -> a write would go through (the bug)", res)
    res, _ = check(GOOD3)
    ok(all(not r["problems"] and any("kit-hook" in n for n in r["notes"]) for r in res),
       "guard_check: the old hooks with a working python3 -> pass, with a note", res)

    def setup(path=None):
        return subprocess.run([sys.executable, str(HERE / "shared" / "kit_setup.py"), "guardcheck"],
                              capture_output=True, text=True, env=env(path), timeout=600)

    r = setup(WITH_PYTHON)
    ok(r.returncode == 1 and "a write would go through" in r.stderr and "KIT_PYTHON" in r.stderr,
       "kit_setup.py guardcheck: the bug -> exit 1, with the fix", (r.returncode, r.stdout, r.stderr))
    import doctor  # noqa: E402
    doctor.results.clear()
    doctor.check_connector_hooks(AGENTS, env(WITH_PYTHON))
    ok(doctor.results and doctor.results[0][:2] == ("FAIL", "Connector guard hooks")
       and "gateway, status-reporter: a write would go through" in doctor.results[0][2],
       "doctor.py: the bug -> FAIL, one line for both agents", doctor.results)
    doctor.results.clear()
    doctor.check_connector_hooks(AGENTS, env(GOOD3))
    ok(doctor.results and doctor.results[0][0] == "warn" and "kit-hook" in doctor.results[0][2],
       "doctor.py: the old hooks with a working python3 -> warn", doctor.results)
    install("shipped")
    r = setup()
    ok(r.returncode == 0 and "each blocks a write and allows a read" in r.stdout,
       "kit_setup.py guardcheck: the shipped hooks -> exit 0", (r.returncode, r.stdout, r.stderr))
    doctor.results.clear()
    doctor.check_connector_hooks(AGENTS, env())
    ok(doctor.results == [("ok", "Connector guard hooks", "2 guarded agents block a write and allow a read")],
       "doctor.py: the shipped hooks -> ok", doctor.results)
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\nkit-hook tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)

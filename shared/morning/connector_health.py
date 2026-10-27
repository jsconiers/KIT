#!/usr/bin/env python3
"""connector_health.py: one line on Kit's connectors for the top of the morning brief.

  python3 connector_health.py [--out briefs/connectors.txt] [--timeout 120] [--kit-connect <path>]

Runs `kit-connect test --json` (no --read, so no model run and no cost: it checks the guard
settings, credential names, and Claude Code's own `claude mcp list`), and writes one line such as

  Connectors: jira PASS; wiki FAIL (health: Failed to connect)

It never fails the run that calls it: a timeout, a missing kit-connect, or output it can't read
becomes "Connectors: not checked (...)", and it always exits 0. With no servers configured it
writes nothing, so the brief gets no line. The run.sh and run.ps1 morning runs call it before the
model and pass the line in; set CONNECTOR_CHECK="off" in the config to skip it.
"""
import argparse
import json
import os
import signal
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_KC = os.path.join(os.path.dirname(HERE), "bin", "kit-connect")


def short(text, n=80):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 3].rstrip() + "..."


def run(kc, timeout):
    """(returncode, stdout, stderr), or None on a timeout. The whole process tree is stopped on a
    timeout, since kit-connect starts claude, which could otherwise hold the pipes open."""
    kw = {"start_new_session": True} if os.name != "nt" else \
        {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    p = subprocess.Popen([sys.executable, kc, "test", "--json"], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, **kw)
    try:
        out, err = p.communicate(timeout=timeout)
        return p.returncode, out, err
    except subprocess.TimeoutExpired:
        try:
            if os.name != "nt":
                os.killpg(p.pid, signal.SIGKILL)
            else:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        except OSError:
            p.kill()
        try:
            p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return None


def line(kc, timeout):
    if not os.path.exists(kc):
        return "Connectors: not checked (kit-connect isn't installed)."
    try:
        r = run(kc, timeout)
    except OSError as ex:
        return f"Connectors: not checked ({short(ex)})."
    if r is None:
        return f"Connectors: not checked (kit-connect didn't finish in {timeout} s)."
    rc, out, err = r
    try:
        servers = json.loads(out).get("servers") or []
    except (ValueError, AttributeError):
        servers = None
    if servers is None:
        msg = (err or out or "").strip().splitlines()
        if rc == 2 and msg and "no servers to check" in msg[0]:
            return ""
        return f"Connectors: not checked ({short(msg[0] if msg else f'kit-connect exited {rc}')})."
    if not servers:
        return ""
    parts = []
    for s in servers:
        name = s.get("server") or "?"
        if s.get("pass"):
            parts.append(f"{name} PASS")
        else:
            bad = next((c for c in s.get("checks") or [] if not c.get("pass")), {})
            why = f"{bad.get('check', 'check')}: {short(bad.get('detail'), 60)}" if bad else "failed"
            parts.append(f"{name} FAIL ({why})")
    return "Connectors: " + "; ".join(parts) + "."


def main(argv):
    ap = argparse.ArgumentParser(prog="connector_health.py", description="One brief line on Kit's connectors.")
    ap.add_argument("--out")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--kit-connect", default=os.environ.get("KIT_CONNECT", DEFAULT_KC))
    a = ap.parse_args(argv)
    try:
        text = line(a.kit_connect, max(a.timeout, 1))
    except Exception as ex:  # noqa: BLE001  (never fail the scheduled run)
        text = f"Connectors: not checked ({short(ex)})."
    if a.out:
        try:
            with open(a.out, "w", encoding="utf-8") as f:
                f.write(text + ("\n" if text else ""))
        except OSError as ex:
            print(f"connector_health: couldn't write {a.out}: {ex}", file=sys.stderr)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

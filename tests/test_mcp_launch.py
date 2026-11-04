#!/usr/bin/env python3
"""Tests for doctor.py's MCP launch checks, with a fake home: for each user-scope MCP server in
~/.claude.json, (a) a kit-mcp-env launcher whose credentials are neither set nor in the credential store
(by name; no value is ever read), (b) TLS checking turned off in the server entry or its launcher script,
and (c) npx with @latest or no version. Reports name the server only. Before this check, launchers that
couldn't start failed silently for days.

  python3 tests/test_mcp_launch.py

The credential store is a stand-in: kit_secrets.stored answers from a list of names, and any attempt to
read a value fails the test. Runs the same on macOS, Linux, and Windows.
"""
import importlib.util
import json
import os
import pathlib
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SHARED = REPO / "shared"
sys.path.insert(0, str(SHARED))
import kit_secrets  # noqa: E402

P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:800])


spec = importlib.util.spec_from_file_location("doctor", SHARED / "doctor.py")
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)

STORED = {"jira-mcp-token", "WIKI_TOKEN"}
ASKED = []


def fake_stored(name, path=None):
    ASKED.append(name)
    return name in STORED


def no_values(*a, **k):
    raise AssertionError("a credential value was asked for")


kit_secrets.stored = fake_stored
kit_secrets.resolve = no_values
kit_secrets._keychain = no_values
kit_secrets._wincred = no_values
kit_secrets.STORE = "Keychain"

TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-mcp-launch-"))
try:
    home = TMP / "home"
    launchers = home / ".mcp-servers/launchers"
    launchers.mkdir(parents=True)
    kme = "/x/.install/shared/bin/kit-mcp-env"

    def launcher(name, body):
        p = launchers / name
        p.write_text(body, encoding="utf-8")
        return str(p)

    good = launcher("jira.sh", f"""#!/bin/sh
# Holds names only. NODE_TLS_REJECT_UNAUTHORIZED=0 in a comment doesn't count.
exec python3 {kme} \\
  JIRA_MCP_TOKEN=jira-mcp-token -- \\
  node --use-system-ca /x/mcp-remote/dist/proxy.js https://tracker.example.com/mcp \\
  --header 'Authorization:Token ${{JIRA_MCP_TOKEN}}'
""")
    missing = launcher("wiki.sh", f"""#!/bin/sh
export NODE_TLS_REJECT_UNAUTHORIZED=0
exec python3 {kme} WIKI_MCP_TOKEN=wiki-mcp-token2 -- node /x/proxy.js https://wiki.example.com/mcp
""")
    ps1 = launcher("docs.ps1", f"""# PowerShell launcher
$env:CONFLUENCE_SSL_VERIFY = "false"
python {kme} `
  WIKI_TOKEN -- `
  npx -y @example/docs-mcp@2.1.0
""")
    insecure = launcher("tracker2.sh", "#!/bin/sh\nJIRA_SSL_VERIFY=false exec node /x/server.js\n")
    servers = {
        "jira-good": {"type": "stdio", "command": "sh", "args": [good]},
        "wiki-missing": {"type": "stdio", "command": "sh", "args": [missing]},
        "docs-ps": {"type": "stdio", "command": "powershell", "args": ["-File", ps1]},
        "tracker-insecure": {"type": "stdio", "command": "sh", "args": [insecure]},
        "latest": {"type": "stdio", "command": "npx", "args": ["-y", "@example/desk-mcp@latest"]},
        "unversioned": {"type": "stdio", "command": "npx", "args": ["example-browser-mcp"]},
        "pinned": {"type": "stdio", "command": "npx", "args": ["-y", "@example/draw-mcp@1.10.0"]},
        "tagged": {"type": "stdio", "command": "cmd", "args": ["/c", "npx", "-y", "tool-mcp@next"]},
        "package-flag": {"type": "stdio", "command": "npx", "args": ["-p", "pkg-mcp@3.0.1", "pkg-mcp"]},
        "env-tls": {"type": "stdio", "command": "node", "args": ["/x/a.js"],
                    "env": {"NODE_TLS_REJECT_UNAUTHORIZED": "0", "SECRET_THING": "not-a-real-value"}},
        "env-ok": {"type": "stdio", "command": "node", "args": ["/x/b.js"], "env": {"NODE_TLS_REJECT_UNAUTHORIZED": "1"}},
        "gone": {"type": "stdio", "command": "sh", "args": [str(launchers / "gone.sh")]},
        "inline": {"type": "stdio", "command": "python3",
                   "args": [kme, "INLINE_TOKEN", "--", "node", "/x/c.js"]},
        "inline-env": {"type": "stdio", "command": "python3",
                       "args": [kme, "ENV_TOKEN", "--", "node", "/x/d.js"]},
        "remote": {"type": "http", "url": "https://mcp.example.com/"},
    }
    (home / ".claude.json").write_text(json.dumps({"mcpServers": servers, "projects": {
        "/p": {"mcpServers": {"project-only": {"command": "npx", "args": ["x@latest"]}}}}}), encoding="utf-8")
    env = {"PATH": os.environ.get("PATH", ""), "ENV_TOKEN": "set-in-the-environment"}

    found = doctor.mcp_launch_problems(home, env)
    ok(found is not None and found["checked"] == len(servers), "every user-scope server is checked", found)
    ok(sorted(found["credentials"]) == ["inline", "wiki-missing"],
       "(a) a kit-mcp-env credential in neither the environment nor the store is reported, launcher or inline",
       found["credentials"])
    ok("jira-mcp-token" in ASKED and "wiki-mcp-token2" in ASKED and "WIKI_TOKEN" in ASKED,
       "(a) the store is asked about the ENTRY name (NAME=ENTRY), by name", ASKED)
    ok("ENV_TOKEN" not in ASKED and "inline-env" not in found["credentials"],
       "(a) a variable already set in the environment counts, as kit-mcp-env uses it", ASKED)
    ok(sorted(found["tls"]) == ["docs-ps", "env-tls", "tracker-insecure", "wiki-missing"],
       "(b) TLS off in a launcher (sh export, PowerShell $env:, inline VAR=) or the entry's env is reported; "
       "a comment and =1 aren't", found["tls"])
    unp = dict(found["unpinned"])
    ok(unp.get("latest") == "@latest" and unp.get("unversioned") == "no version",
       "(c) npx with @latest, and with no version, are reported", unp)
    ok("tagged" in unp and "next" in unp["tagged"], "(c) a dist-tag through cmd /c npx is reported as a tag", unp)
    ok(not {"pinned", "package-flag", "docs-ps"} & set(unp), "(c) pinned packages pass (scoped, -p, in a launcher)", unp)
    ok("project-only" not in json.dumps(found), "project-scope servers aren't this check's business", found)
    ok(found["launcher"] == ["gone"], "a launcher script that isn't there is reported", found["launcher"])

    doctor.results.clear()
    doctor.check_mcp_launch(home, env)
    out = "\n".join(f"{lv} {n}: {d}" for lv, n, d in doctor.results)
    ok(all(lv == "warn" for lv, _, _ in doctor.results) and len(doctor.results) == 4,
       "four warnings (launcher, credentials, TLS, versions), never a failure", out)
    for leak in ("example.com", "jira-mcp-token", "wiki-mcp-token2", "WIKI_MCP_TOKEN", "not-a-real-value",
                 "set-in-the-environment", "/x/", "proxy.js"):
        ok(leak not in out, f"the report names servers only: no {leak}", out)
    ok("wiki-missing" in out and "tracker-insecure" in out and "latest (@latest)" in out, "it names the servers", out)

    # ---- all well: one ok line
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {k: servers[k] for k in ("jira-good", "pinned", "remote")}}),
                                       encoding="utf-8")
    doctor.results.clear()
    doctor.check_mcp_launch(home, env)
    ok([r[:2] for r in doctor.results] == [("ok", "MCP launch setup")], "a clean setup gives one ok line", doctor.results)

    # ---- where it doesn't apply, it says nothing
    doctor.results.clear()
    (home / ".claude.json").unlink()
    doctor.check_mcp_launch(home, env)
    ok(doctor.results == [], "no ~/.claude.json: skipped quietly", doctor.results)
    (home / ".claude.json").write_text("{not json", encoding="utf-8")
    doctor.check_mcp_launch(home, env)
    ok(doctor.results == [], "an unreadable ~/.claude.json: skipped quietly", doctor.results)
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"wiki-missing": servers["wiki-missing"]}}), encoding="utf-8")
    kit_secrets.STORE = None
    found = doctor.mcp_launch_problems(home, env)
    ok(found["credentials"] == [] and found["tls"] == ["wiki-missing"],
       "no credential store on this computer: the credential part is skipped, the rest still runs", found)
    kit_secrets.STORE = "Keychain"

    src = (SHARED / "doctor.py").read_text(encoding="utf-8")
    ok("check_mcp_launch," in src.split("def main", 1)[1], "main() runs the check, so its warnings reach the brief")
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\nMCP launch checks: {P} passed, {F} failed")
sys.exit(1 if F else 0)

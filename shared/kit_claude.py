"""kit_claude: run Claude Code headless for one of Kit's small jobs, the way Kit's scheduled runs do.

    from kit_claude import ask_claude
    rc, text = ask_claude(prompt, mode="receipts", allowed=["Read(~/Claude/Agents/kit/receipts/**)"])

- Login: CLAUDE_CODE_OAUTH_TOKEN, or the "kit-claude-token" Keychain entry, as run.sh uses.
- Budget: kit-cost check --mode MODE first; at the stop level the job doesn't run (rc 75, text "").
- Tools: only the ones named in `allowed`. Everything else that changes or reaches out is denied, and no
  MCP servers load unless mcp=True (the user's own MCP configuration, as in a session) or mcp is the
  path of an MCP config file (only the servers in it; see mcp_config_for).
- Cost: kit-cost record --mode MODE afterward, so the job shows in Kit's spend like any run.
- rc 142 means it hit the time limit. The text is Claude's final answer ("result" in the JSON output).
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

HOME = pathlib.Path.home()
KIT = pathlib.Path(os.path.expanduser(os.environ.get("KIT_DIR", "~/Claude/Agents/kit")))
COST = pathlib.Path(__file__).resolve().parent / "bin" / "kit-cost"
PATH = f"{HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
DENY = ["Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Task", "Agent",
        "Read(~/Claude/Agents/kit/care/**)", "Read(~/Claude/Agents/kit/letters/signature/**)",
        "Read(~/Claude/Agents/kit/feedback/**)"]


def environment():
    env = dict(os.environ, PATH=PATH)
    if not env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        try:
            r = subprocess.run(["security", "find-generic-password", "-s", "kit-claude-token", "-w"],
                               capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and r.stdout.strip():
                env["CLAUDE_CODE_OAUTH_TOKEN"] = r.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return env


def budget_stopped(mode):
    if not COST.exists():
        return False
    try:
        r = subprocess.run([sys.executable, str(COST), "check", "--mode", mode], capture_output=True, text=True,
                           timeout=30)
        return r.stdout.strip().startswith("stop")
    except (OSError, subprocess.SubprocessError):
        return False


def ask_claude(prompt, mode, allowed=(), deny=None, model=None, timeout=600, cwd=None, mcp=False, log=None,
               extra_args=()):
    """(rc, final text). rc 75: skipped for the budget; 142: time limit; otherwise claude's exit code."""
    if budget_stopped(mode):
        return 75, ""
    deny = list(DENY if deny is None else deny)
    allowed = list(allowed)
    deny = [d for d in deny if d not in allowed and not any(a.startswith(d + "(") for a in allowed)]
    cmd = ["claude", "-p", prompt, "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    if isinstance(mcp, (str, os.PathLike)):
        cmd += ["--strict-mcp-config", "--mcp-config", str(mcp)]      # just the servers in that file
    elif not mcp:
        cmd += ["--strict-mcp-config", "--mcp-config", '{"mcpServers": {}}']
    if allowed:
        cmd += ["--allowedTools", *allowed]
    if deny:
        cmd += ["--disallowedTools", *deny]
    cmd += list(extra_args)
    fd, out_path = tempfile.mkstemp(prefix=f"kit-{mode}-", suffix=".json")
    os.close(fd)
    started = time.time()
    try:
        with open(out_path, "w") as f:
            r = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True, timeout=timeout,
                               cwd=str(cwd or KIT), env=environment(), stdin=subprocess.DEVNULL)
        rc = r.returncode
        err = (r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        rc, err = 142, "time limit"
    raw = pathlib.Path(out_path).read_text(errors="replace")
    if COST.exists():
        args = [sys.executable, str(COST), "record", "--mode", mode, "--rc", str(rc), "--json-file", out_path]
        if log:
            args += ["--log", str(log)]
        try:
            subprocess.run(args, capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass
    os.unlink(out_path)
    try:
        text = (json.loads(raw).get("result") or "").strip()
    except ValueError:
        text = ""
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} claude ({mode}): rc {rc}, {time.time() - started:.0f}s"
                    + (f", {err[:200]}" if rc and err else "") + "\n")
    return rc, text


def json_from(text):
    """The first JSON object in Claude's answer (it may wrap it in a code fence or a sentence)."""
    if not text:
        return None
    start = text.find("{")
    while start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except ValueError:
                        break
        start = text.find("{", start + 1)
    return None


def mcp_config_for(*names):
    """A temporary MCP config file (mode 600) holding just the named servers from the user's Claude Code
    configuration, so a job loads only what it needs and no key is written into Kit's own files. The caller
    deletes it. None if none of the servers is configured."""
    try:
        servers = json.loads((HOME / ".claude.json").read_text()).get("mcpServers", {})
    except (OSError, ValueError):
        return None
    chosen = {n: servers[n] for n in names if n in servers}
    if not chosen:
        return None
    fd, path = tempfile.mkstemp(prefix="kit-mcp-", suffix=".json")
    os.write(fd, json.dumps({"mcpServers": chosen}).encode())
    os.close(fd)
    os.chmod(path, 0o600)
    return path

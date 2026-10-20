"""kit_hooks: run Claude Code-style command hooks for kit-run (Python standard library only).

An agent's frontmatter `hooks:` block is read the way Claude Code reads it, so the same hooks (the
connector guard above all) govern an agent whether it runs in Claude Code or under kit-run:

  hooks:
    PreToolUse:
      - matcher: "mcp__.*"
        hooks:
          - type: command
            command: 'python3 "$HOME/..../connector-guard" pre gateway'
    PostToolUse / PostToolUseFailure:  the same shape
    Stop:
      - hooks:
          - type: command
            command: '...'

Semantics, per Claude Code's hooks reference (code.claude.com/docs/en/hooks):
  input     JSON on stdin: session_id, transcript_path, cwd, permission_mode, hook_event_name,
            agent_type; for tool events tool_name, tool_input, tool_use_id; PostToolUse adds
            tool_response and duration_ms; PostToolUseFailure adds error, is_interrupt, and
            duration_ms; MCP tools add mcp_server; Stop adds stop_hook_active and
            last_assistant_message.
  matcher   "*", "" or none: everything. Only letters, digits, _, -, spaces, "," and "|": an exact
            name, or a list of names split on "|" or ",". Anything else: an unanchored regular
            expression on tool_name. Stop ignores matchers.
  exit 0    success; stdout that parses as JSON is applied.
  exit 2    PreToolUse: the call is blocked, stderr is the reason. PostToolUse: stderr is shown to
            the model. Stop: the agent keeps going with stderr as its next instruction.
  other     a non-blocking error: logged, and the call goes ahead.
  JSON      PreToolUse: hookSpecificOutput.permissionDecision allow | deny | ask | defer, with
            permissionDecisionReason, and optional updatedInput. PostToolUse: decision "block" with
            reason, and optional updatedToolOutput. Stop: decision "block" with reason, or
            hookSpecificOutput.additionalContext.
  timeout   600 seconds by default, or the hook's own "timeout" (seconds).

Only "command" hooks run; "prompt", "agent", "http", and "mcp_tool" hooks are logged as skipped.
"""
import json
import os
import re
import subprocess

EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure", "Stop")
DEFAULT_TIMEOUT = 600
EXACT = re.compile(r"^[A-Za-z0-9_\- ,|]*$")


def _scalar(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
    return v


def parse_hooks(frontmatter):
    """Parse the hooks: block out of an agent's raw frontmatter text.

    Returns {event: [{"matcher": str|None, "hooks": [{"type": ..., "command": ..., "timeout": ...}]}]}.
    Handles the shape Kit's agents use (and Claude Code documents); not general YAML.
    """
    lines = frontmatter.split("\n")
    out, i = {}, 0
    while i < len(lines) and not re.match(r"^hooks:\s*$", lines[i]):
        i += 1
    if i == len(lines):
        return out
    i += 1
    event = entry = hook = None
    for line in lines[i:]:
        if line.strip() == "" or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            break                               # the next top-level key
        s = line.strip()
        m = re.match(r"^([A-Za-z]+):\s*$", s)
        if indent <= 2 and m:
            event = m.group(1)
            out.setdefault(event, [])
            entry = hook = None
            continue
        if event is None:
            continue
        if s.startswith("- "):
            body = s[2:]
            key, _, val = body.partition(":")
            key = key.strip()
            if key in ("matcher", "hooks") and (entry is None or indent <= entry["_indent"]):
                entry = {"matcher": None, "hooks": [], "_indent": indent}
                out[event].append(entry)
                hook = None
                if key == "matcher":
                    entry["matcher"] = _scalar(val)
                continue
            if entry is not None and key in ("type", "command", "timeout"):
                hook = {}
                entry["hooks"].append(hook)
                hook[key] = _scalar(val)
                continue
        else:
            key, _, val = s.partition(":")
            key = key.strip()
            if hook is not None and key in ("type", "command", "timeout") and val.strip():
                hook[key] = _scalar(val)
            elif entry is not None and key == "matcher":
                entry["matcher"] = _scalar(val)
            elif entry is not None and key == "hooks":
                hook = None
    for ev in out:
        for e in out[ev]:
            e.pop("_indent", None)
    return out


def matches(matcher, tool):
    if matcher in (None, "", "*"):
        return True
    if EXACT.match(matcher):
        return tool in [x.strip() for x in re.split(r"[|,]", matcher) if x.strip()]
    try:
        return re.search(matcher, tool or "") is not None
    except re.error:
        return False


class Outcome:
    """What the hooks for one event decided."""

    def __init__(self):
        self.block = False          # PreToolUse deny / exit 2; Stop block
        self.ask = False            # PreToolUse ask
        self.reason = ""
        self.updated_input = None
        self.updated_output = None
        self.feedback = []          # text to show the model (PostToolUse exit 2 / block reason, Stop context)
        self.ran = []               # (command, exit code) for the audit log


class Hooks:
    def __init__(self, config, base_input, audit=None, env=None):
        self.config = config or {}
        self.base = base_input
        self.audit = audit
        self.env = env

    def has(self, event, tool=None):
        return any(matches(e.get("matcher"), tool) or event == "Stop"
                   for e in self.config.get(event) or [] if e.get("hooks"))

    def run(self, event, tool=None, **fields):
        out = Outcome()
        payload = {**self.base, "hook_event_name": event, **fields}
        if tool is not None:
            payload["tool_name"] = tool
        for entry in self.config.get(event) or []:
            if event != "Stop" and not matches(entry.get("matcher"), tool):
                continue
            for h in entry.get("hooks") or []:
                if (h.get("type") or "command") != "command" or not h.get("command"):
                    if self.audit:
                        self.audit("hook", hook_event=event, skipped=h.get("type"))
                    continue
                self._one(event, h, payload, out)
        return out

    def _one(self, event, h, payload, out):
        try:
            timeout = float(h.get("timeout") or DEFAULT_TIMEOUT)
        except ValueError:
            timeout = DEFAULT_TIMEOUT
        try:
            r = subprocess.run(h["command"], shell=True, input=json.dumps(payload), capture_output=True,
                               text=True, timeout=timeout, env=self.env)
            code, stdout, stderr = r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            code, stdout, stderr = -1, "", f"hook timed out after {timeout:g}s"
        except OSError as e:
            code, stdout, stderr = -1, "", f"hook couldn't start: {e}"
        out.ran.append((h["command"][:120], code))
        if self.audit:
            self.audit("hook", hook_event=event, command=h["command"][:200], exit=code,
                       tool=payload.get("tool_name"), tool_use_id=payload.get("tool_use_id"))
        if code == 2:
            reason = stderr.strip() or "blocked by a hook"
            if event == "PreToolUse":
                out.block, out.reason = True, reason
            elif event == "Stop":
                out.block, out.reason = True, reason
            else:
                out.feedback.append(reason)
            return
        if code != 0:
            return                              # non-blocking error: the call goes ahead
        try:
            data = json.loads(stdout) if stdout.strip() else {}
        except ValueError:
            return                              # plain text output: nothing to apply
        if not isinstance(data, dict):
            return
        hso = data.get("hookSpecificOutput") or {}
        if event == "PreToolUse":
            decision = hso.get("permissionDecision")
            if decision == "deny":
                out.block, out.reason = True, hso.get("permissionDecisionReason") or "denied by a hook"
            elif decision == "ask":
                out.ask = True
                out.reason = hso.get("permissionDecisionReason") or out.reason
            if isinstance(hso.get("updatedInput"), dict):
                out.updated_input = hso["updatedInput"]
        elif event == "PostToolUse":
            if data.get("decision") == "block":
                out.feedback.append(data.get("reason") or "a hook flagged this result")
            if "updatedToolOutput" in data:
                out.updated_output = data["updatedToolOutput"]
        elif event == "Stop":
            if data.get("decision") == "block":
                out.block, out.reason = True, data.get("reason") or "a stop hook asked to continue"
            elif hso.get("additionalContext"):
                out.feedback.append(hso["additionalContext"])

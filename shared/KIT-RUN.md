# kit-delegate and kit-run: calling models directly

Model routing phase 1 sets which Claude model each agent uses inside Claude Code (`kit-models`).
Phases 2 and 3 add two tools that call a provider's API directly, so a task can go to another
model, or an agent can run without Claude Code at all.

| Tool | Phase | What it does | Status |
|---|---|---|---|
| `kit-delegate` | 2 | One bounded task (summarize, classify, extract, draft) to a named profile; one turn, no tools. A command, and an MCP server Kit can call from Claude Code | Ready to try once a provider is approved |
| `kit-run` | 3 | Runs one of Kit's agents outside Claude Code, on any profile, with a tool loop and Kit's guardrails rebuilt | **Experimental.** Check its output |

Both follow the rules in `models/README.md`: `enabled_phase`, data class, the organization
profile, fallback to Claude, credentials by name only, and usage in kit-cost's ledger.

## kit-delegate

```
kit-delegate --profile fast "Summarize the following in five bullets: ..."
kit-delegate --profile local --data-class public < notes.txt
kit-delegate --mcp            # MCP server on stdio: one tool, "delegate"
```

Exit codes: 0 answered, 2 refused (policy or config), 3 provider or credential error. The answer
goes to standard output; which profile answered, and any fallback, goes to standard error.

**As an MCP server.** It speaks MCP over stdio (JSON-RPC 2.0, one message per line;
`initialize`, `tools/list`, `tools/call`, `ping`), protocol versions 2025-06-18, 2025-03-26, and
2024-11-05. Its one tool, `delegate`, takes `profile`, `task`, and optional `data_class` and
`system`. Answers come back prefixed with a note that they're untrusted model output.

To make it available in Claude Code (this isn't done for you), add an MCP server entry such as:

```
claude mcp add kit-delegate -- python3 ~/Claude/Agents/kit/.install/shared/bin/kit-delegate --mcp
```

Then add `kit-delegate` to the connector guard's allowed servers if agents that run under the
guard should use it, and its tool to `allow_tools` (it doesn't look read-only by name).

## kit-run (experimental)

```
kit-run researcher "Background on vendor X's support model" --profile deep
kit-run lab-planner "Runbook for LAB-0003" --data-class internal
kit-run meeting-scribe "Minutes from inbox file 2026-10-19-pm.md" --yes-ask
```

It loads `agents/<agent>.md` and `KIT.md` as the system prompt, resolves the profile, and loops:
the model asks for tools, kit-run checks and runs them, and sends back the results until the model
answers or `--max-turns` (default 20) is reached. Exit codes: 0 done, 2 refused, 3 provider or
credential error, 4 stopped at the turn limit.

**Tools**

| Tool | Allowed |
|---|---|
| `read_file`, `list_dir`, `search` | Under the Kit folder and the library root (from `library.md`). Credential-looking files (`.env`, keys, credential stores, token files) are refused |
| `write_file` | Only under the agent's write paths, and only with the owner's approval (see Approvals). An existing file is backed up to `.install/backups/kit-run/` first |
| `run_kit_tool` | `kit-precedent`, `kit-labcheck`, `kit-version`, `kit-queue hygiene`, `kit-models check` and `resolve`, `kit-cost report` and `check` |
| `mcp__<server>__<tool>` | MCP connectors named in `kit-run.json`; only each server's `allow_tools`; and, by default, only for agents whose frontmatter hooks guard that tool (the connector guard) |
| `agent` | Brief another Kit agent, only along the direct pairs in `memory/context/agents.md` or the agent's own `kit_run: agents:` list; at most two levels deep |
| `skill`, `skill_script` | Read a skill's `SKILL.md`; run one of its `.py` or `.sh` scripts only if it's on `skills.allow_scripts` and the owner approves |

An agent's write paths (and extra agents it may brief) come from a `kit_run:` block in its
frontmatter; without one, only `briefs/` in the Kit folder:

```
kit_run:
  write:
    - briefs/
    - <library root>/artifacts/
  agents:
    - librarian
```

The agent's `tools` and `disallowedTools` are honoured: Read, Glob, and Grep map to the read tools;
Write and Edit to `write_file`; Bash to `run_kit_tool` (and, with Skill, `skill_script`); Agent or
Task to `agent`; Skill to `skill`. MCP tools follow Claude Code's rules: an exact name,
`mcp__<server>`, or `mcp__<server>__*`.

**kit-run.json** (in the Kit folder; optional). Connectors and skills come only from here, never
from Claude Code's settings. Environment values and HTTP header values are named by environment
variable and read at launch; they're never logged or printed.

```
{"mcp": {"require_guard": true,
         "servers": {"jira": {"type": "stdio", "command": "node", "args": ["server.js"],
                              "env_from": {"SERVER_VAR": "MY_ENV_VAR"},
                              "allow_tools": ["get_issue", "search_issues"]},
                     "wiki": {"type": "http", "url": "https://wiki.example.com/mcp",
                              "headers_env": {"Authorization": "WIKI_AUTH_HEADER"},
                              "allow_tools": ["search"]}}},
 "skills": {"dirs": ["~/.claude/skills"], "allow_scripts": ["xlsx/recalc.py"]}}
```

**MCP.** Version 2025-06-18 over stdio (one JSON-RPC message per line; shutdown closes stdin, then
SIGTERM, then SIGKILL) or Streamable HTTP (POST with `Accept: application/json, text/event-stream`,
JSON or event-stream answers, `Mcp-Session-Id` and `MCP-Protocol-Version` on later requests, DELETE
at the end). HTTP servers must be `https://`, or `http://` on this computer. Server requests
(sampling, elicitation, roots) are declined. A server that won't start is noted to the model and
the run continues.

**Hooks.** The agent's frontmatter `hooks:` run as in Claude Code: PreToolUse, PostToolUse,
PostToolUseFailure, and Stop, with the same matchers, stdin JSON fields, exit codes (2 blocks), and
JSON decisions (deny, ask, updatedInput; block and updatedToolOutput; Stop block, up to 8 times).
kit-run's tools go by their Claude Code names in hooks (Read, Glob, Grep, Write, Bash, Agent,
Skill), so a matcher like `Edit|Write` works. So the connector guard governs kit-run's connector
calls and writes the same audit log. Only `command` hooks run. Hooks can only tighten: kit-run's own
rules still apply after a hook allows a call.

**Approvals.** kit-run shows the action (tool, arguments, and a diff for writes) and asks
`[y]es / [n]o / [a]lways for this tool this run / [d]etails`. Each answer is logged. With no one at
the keyboard it refuses, unless `--yes-ask`. A hook's "ask" decision goes through the same prompt.

**Context.** KIT.md is loaded with its `@` imports followed (relative to the importing file, `~`
expanded, not inside code fences, five levels at most, each file once), so preferences, lessons,
and the memory index load as in Claude Code.

**Guardrails kit-run enforces itself:** no tools to send, delete, or install; ask-first for writes
and skill scripts; the allowlists above; data-class and organization-profile policy; nothing runs
while Kit is paused (`kit-pause`); every tool result wrapped as untrusted content; an audit line per
tool call, hook, and approval in `.install/logs/kit-run-YYYY-MM.jsonl`; and the run's usage in the
cost ledger.

**Parity with Claude Code**

| Area | Status |
|---|---|
| MCP connectors | At parity for tools (stdio and Streamable HTTP). Not supported: resources, prompts, sampling, elicitation, OAuth sign-in flows, the old HTTP+SSE transport |
| Hooks | At parity for command hooks on PreToolUse, PostToolUse, PostToolUseFailure, and Stop. Not supported: other events (SessionStart, UserPromptSubmit, SubagentStop, ...) and prompt, agent, http, and mcp_tool hooks; `defer` is treated as allow |
| Subagents | Supported along direct pairs, two levels deep. Stricter than Claude Code: an unrestricted Agent permission alone doesn't let an agent brief anyone |
| Skills | Instructions load on demand. Scripts run only from an allowlist with approval; Claude Code runs them through Bash under its own permissions |
| KIT.md imports | At parity |
| Approvals | Interactive y / n / always / details, logged. Not supported: settings-based permission rules (allow and deny lists in settings.json), permission modes |
| Built-in tools | No web search or fetch, no general Bash, no notebook editing |
| Smaller models | Tool calling on local and smaller models is less reliable. Move an agent to a non-Claude profile only after it passes its evals there |

## Turning phase 2 on

1. Get the provider approved by your organization (work data goes only to endpoints it approves;
   a local model runner may need a software catalogue approval first).
2. In `models.json`: set the provider's `base_url`, its `credential_env` or `keychain_entry`, its
   `max_data_class`, and `"enabled_phase": 2`. Raise `org_profile.non_claude_max_data_class` only
   if the organization allows internal or confidential data to reach it.
3. Store the credential where the provider entry says (an environment variable, or
   `security add-generic-password -s <entry> -a "$USER" -w` for the Keychain, typed by you).
4. Try `kit-delegate --profile <name> --data-class public "Say hello"`, then check
   `kit-cost report` shows the call.

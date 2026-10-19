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

**Tools in this version**

| Tool | Allowed |
|---|---|
| `read_file`, `list_dir`, `search` | Under the Kit folder and the library root (from `library.md`). Credential-looking files (`.env`, keys, credential stores, token files) are refused |
| `write_file` | Only under the agent's write paths, and only after the owner says yes at the keyboard, or with `--yes-ask`. With no one at the keyboard, writes are refused. An existing file is backed up to `.install/backups/kit-run/` first |
| `run_kit_tool` | `kit-precedent`, `kit-labcheck`, `kit-version`, `kit-queue hygiene`, `kit-models check` and `resolve`, `kit-cost report` and `check` |

An agent's write paths come from a `kit_run:` block in its frontmatter; without one, only
`briefs/` in the Kit folder:

```
kit_run:
  write:
    - briefs/
    - <library root>/artifacts/
```

The agent's `tools` and `disallowedTools` are honoured: Read, Glob, and Grep map to the read tools;
Write and Edit to `write_file`; Bash to `run_kit_tool`.

**Guardrails kit-run enforces itself:** no tools to send, delete, install, or reach outside
systems; ask-first for every write; the allowlists above; data-class and organization-profile
policy; nothing runs while Kit is paused (`kit-pause`); every tool result wrapped as untrusted
content; an audit line per tool call in `.install/logs/kit-run-YYYY-MM.jsonl`; and the run's
usage in the cost ledger.

**Not at parity with Claude Code**

- **No MCP connectors.** Agents that need the gateway, Jira, Confluence, or ServiceNow can't run
  under kit-run yet; it says what it would need instead.
- **No subagents.** An agent can't call another agent; the routing pairs in `agents.md` don't apply.
- **No hooks.** The connector guard isn't involved because there are no connectors; kit-run's own
  audit log stands in for its records.
- **No skills.** The document skills (docx, pptx, xlsx, pdf) and style skills aren't available, so
  agents that build Office files can't finish those jobs.
- **Plain prompts for approval.** Ask-first is a y/N at the terminal, with no settings-based
  permission rules, and no remembered approvals.
- **Smaller models vary.** Tool calling on local and smaller models is less reliable. Move an
  agent to a non-Claude profile only after it passes its evals there.
- **Context.** KIT.md is included as text (its `@` imports aren't followed), so preferences,
  lessons, and the memory index don't load the way they do in Claude Code.

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

# Connectivity

How Kit reaches outside systems, how each route is controlled, and how to keep a connectivity matrix for
your own install. The template workbook `connectivity-matrix-template.xlsx` has the same sheets as the
matrix described here.

## Kinds of connection

| Kind | What it is | Examples | Main control |
|---|---|---|---|
| MCP server, organization system | A Model Context Protocol server that reads or changes a work system | IT service management, issue tracker, wiki, portfolio tool | Connector guard and audit log for guarded agents, permission rules for everyone |
| MCP server, local machine | A server that works on the computer itself | Shell and files, filesystem, browser automation, diagram editor | Permission rules (ask or deny), narrow roots, pinned versions |
| MCP server, vendor plugin | A server a Claude Code plugin brings with it | Low-code platform plugins (flow runners, app authoring, documentation search), extra browser-automation copies | Permission rules, plugin review on first use, turn off when not needed |
| Local app | A script that drives a desktop app | Mail and calendar (kitmail, kitcal), to-do sync, brief delivery, text-back (macOS) | Ask rule on the automation command, no-send rule, confirm codes for texted changes |
| Synced folder | A folder the sync client keeps in step | The Kit library, published document libraries, sharing between Kits | Folder must sit in the work tenant, sharing policy |
| Web call | A script that calls a public service | Model providers, kit-expiry live lookups, the researcher's web access, the scheduled runs' connection check | Off unless asked for (`--live`); names only leave the machine; the researcher is the only agent with web tools |

## The guard model

Kit has one guarded path to outside systems.

1. **The gateway agent** is the one agent meant to call outside systems. Three agents (the intake
   triager, dependency mapper, and status reporter) can call it directly, one way. The demand tracker
   reaches its connector itself, under its own guard hooks.
2. **The connector guard** runs on every MCP call by an agent that carries it in its frontmatter hooks:
   `PreToolUse`, `PostToolUse`, and `PostToolUseFailure` on `mcp__.*`, and `Stop`. Five agents carry it:
   the gateway, demand tracker, intake triager, dependency mapper, and status reporter. Before the call it
   allows only the servers listed in `memory/context/connector-guard.json` (`allowed_servers`), denies any
   tool whose name reads as a write (create, update, delete, add, set, link, upload, send, run, and
   similar) or that it doesn't recognize as read-only, lets `allow_tools` and `deny_tools` (full tool
   names) win over those name rules, and fails closed: it denies the call if it can't read its settings or
   write the audit log. After the call (or the failure) it writes one JSON line with the result's size,
   whether it was an error, and any total the result states, never its contents, to
   `connectors-YYYY-MM.jsonl` in `audit_dir`.
3. **kit-connect test** runs in the shell before every morning brief (`kit-connect test --json`, no model
   cost): each server is allowed, its credential variables are set (by name), and Claude Code's own health
   check passes. `kit-connect test --read` goes further, making one read call per server with its
   `probe_tools` tool as the gateway, under the guard (a few cents each). Credentials are named in
   `credential_env`, never stored. The preflight check at 06:45 and 15:45 also checks that the connectors in
   `PREFLIGHT_CONNECTORS` are signed in.
4. **kit-audit** reads the audit log daily and weekly, and the guard integrity check confirms the guarded
   agents still carry their hooks. Issues go to the top of the morning brief.
5. **kit-pause** stops scheduled runs and makes the guard deny every connector call.

### The standing enforcement gap

The guard runs only in the agents that carry it. An agent with no `tools:` line, or only a
`disallowedTools:` list, inherits **every** MCP tool on the machine, and so does Kit's own session and any
built-in agent (general-purpose, Explore, Plan). Their calls are not filtered or audited; Claude Code's
permission prompt is the only control, and an unattended run has no one to answer it.

Ways to close it, once your connections work:

- a global `PreToolUse` hook on `mcp__.*` in `~/.claude/settings.json` that runs the guard for every caller;
- an explicit `tools:` line on every agent, listing only what its job needs;
- deny rules for destructive tools, so no caller can run them.

## Permission rules

Permission rules in `~/.claude/settings.json` apply to every caller, guarded or not. Use them for the
tools the guard can't see:

```json
{
  "permissions": {
    "ask":  ["mcp__<tracker>__create_issue", "mcp__ppmx__create_task", "mcp__ppmx__update_task"],
    "deny": ["mcp__<tracker>__delete_issue", "mcp__<wiki>__delete_page",
             "mcp__plugin_<flow-plugin>__run_flow",
             "mcp__<shell-server>__start_process"]
  }
}
```

Rules match the full tool name, `mcp__<server>__<tool>`. A deny rule wins over ask and allow.

## PPM Express (kit-ppmx)

PPM Express is the one outside system Kit changes, and only when the owner asks in a session: Kit states the
record, the fields, and the new values, and makes the change on the owner's yes. Claude Code asks for each
create or update too (the installer adds ask rules on all 11 change tools, and on `kit-ppmx actions apply`).
Scheduled runs, texts, and agents make no changes: the guard denies change tools to guarded agents (with
`ppmx` in `allowed_servers` they may read), and an unattended run can't answer a prompt. There is no
delete tool. The guard doesn't see calls from Kit's own session, so there the ask rules are the control
and `kit-ppmx`'s own log is the audit.

- `PPMX_WRITES="off"` turns writes off.
- Every PPM Express read and write is logged, with no token and no argument values: `kit-ppmx` (and the
  stdio server it runs) writes `ppmx-YYYY-MM.jsonl` in Kit's audit folder and standard error; the
  standalone OpenShift service writes to standard error. `kit-audit` reads Kit's file and reports PPM
  Express calls, changes, refusals, and failures.
- A write that ends in a server error (5xx), a time-out, or a dropped connection counts as unconfirmed and
  is never resent; `kit-ppmx actions apply N --again` is needed once you've checked PPM Express.
- The token is `PPMX_TOKEN`, from the environment, the Mac Keychain, or Windows Credential Manager.
- Confirmed on 02-Nov-2026 (version 0.3.0): the endpoint paths against PPM Express's OpenAPI description
  (lowercase paths, whole lists with no paging), and the reads, response shapes, and field names against a
  live tenant, read-only. The writes follow the description and are tested against the fake server.
- The read tools, including `list_deliverables`, `get_deliverable`, and `list_my_work`, pass the guard (read
  names); `create_`, `update_`, and `set_` names are denied. `kit-connect test ppmx --read` names the server and
  its probe tool (`probe_tools`) in the prompt it gives the gateway.

## Credentials

Name a credential, never write its value: an environment variable (`TRACKER_MCP_TOKEN`), or a Keychain or
Credential Manager entry (`PPMX_TOKEN`). Don't put a token literally in an MCP server's `args` or `env`;
use `${VAR}` expansion or a headers helper. Don't add allow rules that print the MCP configuration.

## Hardening checklist

| Check | Why | Change |
|---|---|---|
| Pin every `npx`, `dnx`, or `uvx` package | `@latest` fetches new code on every start | `@<reviewed version>` with no known advisories |
| Keep TLS checking on | `NODE_TLS_REJECT_UNAUTHORIZED=0` exposes token headers | `NODE_EXTRA_CA_CERTS=<path to your org CA bundle>` |
| Narrow filesystem roots | A home-folder root reaches credential files | List only the folders the work needs |
| Shell and file servers | They skip Bash and Edit ask rules | Remove, or deny shell and write tools |
| Browser automation | Signed-in sessions, run-code and upload tools | One pinned stack, ask rules on run-code and upload |
| Flow and connector tools | Can send data anywhere a connector reaches | Deny run, invoke, delete, publish |
| Remove stale servers | Old sign-ins can lock shared accounts | `claude mcp remove <name>` |
| Record every server | Undocumented servers aren't audited | One row per server in the matrix |
| Hooks on every event | A hook binary sees every tool payload | Confirm its signer, keep only the events it needs |

## Keeping the matrix

The template has six sheets:

| Sheet | One row per | Columns |
|---|---|---|
| Read me | note | what the workbook holds, as of when |
| Matrix | MCP server | system, owner, transport, endpoint, authentication by name, tool counts, guard, gateway use, callers, permission rules, status, main risk |
| Tools | server and tool | read or write, guard allows, rule today, proposed rule |
| Agent reach | agent | one column per server: Guarded (read only), Unguarded, Denied by guard, No MCP tools, Not registered |
| Non-MCP | integration | system, method, direction, authentication by name, controls |
| Risks | risk | rank by consequence, detail, mitigation, proposal item |

Take the inventory statically: list servers with `claude mcp list` (names and status only), read tool
names from the session, read guard settings and permission rules, and don't call a tool or read a
credential value. Re-run it after adding a server, a plugin, or an agent.

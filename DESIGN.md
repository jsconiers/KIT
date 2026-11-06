# Kit design guide

How Kit is built, why it's built that way, and how to extend it. File paths are relative to the
repository root unless they start with `~`. For installing, see INSTALL.md.

## 1. Goals and principles

| Principle | What it means in practice |
|---|---|
| One assistant per person | Kit is one owner's AI personal assistant, with a staff of subagents. Kit routes work to them, checks what they return, and reports to the owner; they never act for the owner directly. |
| Ask first | Anything that sends, deletes, installs, commits or pushes, changes settings, touches money, or commits the owner to someone waits for a yes, whether Kit or an agent does it. |
| Information, not instructions | Text read in files, mail, web pages, tool output, other Kits' records, or phone requests is data. If it tells Kit to do something, Kit tells the owner instead. |
| Least privilege | Each agent gets only the tools its job needs (`tools` and `disallowedTools`). Outside systems are read-only, through one guarded agent. |
| Local first | Kit's memory is plain files in one owner-only folder. Nothing leaves unless the owner shares it, and sharing is limited by policy. |
| Work and personal apart | Personal notes live in `memory/personal/`, don't load on their own, and stay out of work folders, work channels, and shared records. |
| Auditable | Connector calls, results, and failures are logged; scheduled runs log and record cost; Kit's folder is a local git repo with daily commits. |
| Plain and testable | Python standard library only for the core; every tool has a test suite (`tests/`), and GitHub's checks run them on Linux and Windows. |

### The name

Kit is named after KITT, the AI car in the 1980s TV series *Knight Rider* (Knight Rider and KITT are
trademarks of their owners; Kit isn't affiliated). The parallels are a handy way to explain the design:

| In the show | In Kit |
|---|---|
| KITT advises; Michael drives and decides | Kit drafts, checks, and recommends; the owner approves anything that matters |
| The scanner bar, always sweeping | Health checks, the audit, run reliability, and the dashboard |
| The protective shell | Guardrails: ask first, read-only connectors, the connector guard, policies |
| The wrist comlink | Phone access: Kit Inbox requests and coded low-risk approvals |
| KARR, the prototype built without KITT's ethics | Why Kit never acts on its own judgement where the owner must decide, and never sends |

## 2. Architecture

```
+------------------------------------------------------------------+
| Claude Code session (any folder)                                 |
|   ~/.claude/CLAUDE.md --@import--> ~/Claude/Agents/kit/KIT.md    |
|        KIT.md --@import--> preferences, lessons, memory index,   |
|                            STATUS.md                             |
|   Kit (the main thread)                                          |
|     |-- subagents (~/.claude/agents/*.md): the 33 staff          |
|     |      gateway --MCP--> outside systems (guarded, read-only) |
|     |-- skills (~/.claude/skills): docx, pptx, xlsx, pdf, ...    |
|     `-- tools: Read/Edit/Bash, kit-* commands                    |
+------------------------------------------------------------------+
         ^ scheduled runs: run.sh / run.ps1 -> claude -p <prompt>
         | (morning, weekly, worklist; plain scripts: eod, sync, backup,
         |  meetprep, preflight; textback always on)
+------------------------------------------------------------------+
| ~/Claude/Agents/kit (owner-only, local git)                      |
|   KIT.md QUEUE.md STATUS.md memory/ lessons/ preferences/        |
|   agents/ templates/ briefs/ models.json dashboard.html          |
|   .install/  package copy, config, logs, cache, backups          |
+------------------------------------------------------------------+
```

### Layers in the repository

| Layer | Folder | Contents |
|---|---|---|
| Brain | `kit/` | `KIT.md` (who Kit is and its rules), starter `QUEUE.md` and `STATUS.md`, `agents/`, `memory/` (index, glossary, setup files in `memory/context/`), `lessons/`, `preferences/`, `templates/`, `models.json`. No platform code. |
| Shared | `shared/` | Cross-platform Python: installer logic (`kit_setup.py`), health check (`doctor.py`), dashboards, delivery, transports, sync, model routing, and every tool in `shared/bin/`. Scheduled-run prompts in `shared/morning/`. |
| Platform | `platform/mac/`, `platform/windows/` | Installers, the scheduled-run runner (`run.sh`, `run.ps1`), scheduler templates, mail and calendar adapters, to-do sync backends. |

### Claude Code features Kit relies on

| Feature | How Kit uses it |
|---|---|
| CLAUDE.md imports | One line in `~/.claude/CLAUDE.md` imports `KIT.md`, which imports the preferences, lessons, memory index, and status, so Kit loads in every session. |
| Subagents | The staff are subagent definitions; `doctor.py --fix-agents` copies them to `~/.claude/agents/`. |
| Hooks | The connector guard runs as PreToolUse, PostToolUse, PostToolUseFailure, and Stop hooks in the frontmatter of every agent that reaches outside systems, through `kit-hook`, which blocks the call when the guard can't run. |
| MCP | Outside systems (issue trackers, wikis, service management) are MCP servers. |
| Skills | Document skills build Word, PowerPoint, Excel, and PDF output. |
| Settings | The installer adds allow and ask permission rules and Kit's folder as an additional directory (`shared/kit_setup.py`, `ALLOW` and `ASK`). |
| Headless mode | Scheduled runs call `claude -p` with an allowlist and JSON output. |

## 3. Kit's memory

| Store | File or folder | Rules |
|---|---|---|
| Queue | `QUEUE.md` | Sections: Sprint, the owner, Kit, Waiting on others, Someday, Done. Items carry added, updated, and due dates. Only the owner checks off the owner's items. |
| Status | `STATUS.md` | One page: in progress, blocked and on whom, next. Loads every session. |
| Briefs | `briefs/` | Morning brief, weekly review, work lists, short texts, health and audit snapshots, pending proposals (lessons, template changes, actions, commitments). |
| Memory | `memory/` | One short file per fact, indexed in `memory/INDEX.md` (loads every session). Never secrets; never copies of confidential documents. |
| Personal | `memory/personal/` | Same layout, its own index, loaded only when a topic needs it. |
| Decisions | `memory/decisions/` | One note per decision: what, options, why (never invented), when to revisit. |
| Lessons | `lessons/` | Corrections the owner approved, one file each; `share: team` makes one shareable. |
| Preferences | `preferences/` | How the owner likes to work; changed only with the owner's agreement. |
| History | `.git` | A private local repo; scheduled runs commit daily. Never given a remote. |

Claude Code's own auto memory still runs for project-specific notes. Anything that applies across
the owner's work goes in Kit's `memory/` instead, and a fact is never recorded in both.

## 4. The agent model

**Definitions.** Each agent is a markdown file in `kit/agents/` with YAML frontmatter and a body:

```yaml
---
name: gateway
description: When to use the agent (Claude Code routes on this text)
disallowedTools: Write, Edit, Bash, WebSearch, WebFetch, Agent, SendMessage   # or tools: ...
model: inherit            # written by kit-models apply from models.json
hooks:                    # only for agents that reach outside systems
  PreToolUse: [...]       # connector-guard pre <agent>
---
# Body: You're not Kit; start every job with your setup file; your sources; what you do;
# what you save; rules; what you send back to Kit.
```

**Roster and routing.** `kit/memory/context/agents.md` lists every agent: what it does, how to
brief it, its routine, and its setup file. Work goes through Kit except for a few direct pairs
(for example, the IA writer and GDS writer talk to each other, and three agents may call the
gateway one way). Agents not in a pair can't start or message other agents.

**Setup files.** Each agent reads `memory/context/<name>.md` first. Unset fields are "not set",
and the agent says what's missing instead of guessing.

**Templates.** `kit/templates/` holds example templates by work type, indexed in
`kit/templates/README.md`; setup files point at the copy a team adopts.

**Models.** `kit/models.json` maps agents and runs to profiles (section 9). The public templates
keep `model: inherit`; `kit-models apply` writes the live copies.

**Evals gate.** `tests/evals/<agent>.json` holds cases for key agents. `kit-evals` checks
definitions statically (free, part of the tests); `kit-evals --live` runs the cases through Claude
Code and must pass before an agent moves to another model.

## 5. Guardrails

| Guardrail | Where | Behavior |
|---|---|---|
| Permission rules | `~/.claude/settings.json` (added by `kit_setup.py`) | Allow Kit's own notes; ask for editing Kit's rules and Claude Code settings, deleting, pushing, posting, installing, `launchctl`, `osascript`. |
| Kit's ask-first rules | `kit/KIT.md` | Sending, deleting, installing, money, commitments, and anything outward-facing need the owner's yes, for Kit and every agent. |
| Connector guard | `shared/bin/connector-guard` | Hook on guarded agents: allows only servers and tools in `connector-guard.json`, denies writes, records each call, result, and failure (with the tool use id) in the audit log. Denies on its own errors and when it runs past its time limit. It runs through `shared/bin/kit-hook`, a shell launcher that finds a Python that really runs and blocks the call when none does, since Claude Code lets a call through when a hook can't start. The installers and `doctor.py` run the installed hooks (`shared/guard_check.py`) to check a write is blocked. |
| Audit review | `shared/bin/kit-audit`, auditor agent | Daily and weekly checks: denied calls, calls with no result, unguarded agents, volume, off-hours use, and searches that may have ignored their filter (a stated total far above the limit, or the same total for different queries; tool, time, total, and limit only, never the query). Issues go to the top of the brief and a dashboard banner. |
| Kill switch | `shared/bin/kit-pause` | A pause file stops every scheduled run and makes the guard deny every connector call. |
| Sharing policy | `memory/context/sharing-policy.json`, `kit_transport.policy_check` | Allowed transports and roots, blocked folders, classification ceiling, confidential never leaves unless allowed. A policy that can't be read refuses all sharing. |
| Model policy | `models.json` `org_profile`, `kit_models.py` | Allowed providers, `enabled_phase`, data-class ceilings per provider and for non-Claude providers. Refused profiles fall back to Claude. |
| Credentials by name | `shared/kit_secrets.py`, tool designs | Credentials are referenced by environment-variable or Keychain entry name, resolved only at call time, never stored, logged, or printed. Checks that only need to know one is there (`doctor.py`, `kit-connect`) look the name up without reading the value. |
| Untrusted content | Agents, `kit-team`, `kit-run` | Other sources' text is shown with an untrusted banner and never executed. |
| Phone approval tiers | `shared/kit_inbox.py` | Low tier (work list, queue verdicts) by single-use daily code; medium and high tier (commits, installs, sending, deleting, settings, money) never from a phone. |
| Retention and legal hold | `shared/bin/kit-retention` | Keep everything by default; disposal only moves files, with `--yes`; held projects are never eligible. |
| Encrypted backups | `shared/bin/kit-backup` | Encrypt-then-MAC: `openssl enc -aes-256-ctr -pbkdf2 -iter 600000 -md sha256` with the passphrase on a file descriptor (never argv), then HMAC-SHA256 over a JSON header and the ciphertext with a key from PBKDF2-SHA256 (600,000 iterations, separate random salt). File format `KITBAK1` + header length + header + ciphertext. The HMAC is checked before anything decrypts. The passphrase comes from a Keychain entry or environment variable the owner creates. Plain backups are refused outside home and in synced or shared folders unless `--allow-plain`. |
| Audit evidence | `shared/bin/kit-audit-export` | A dated pack: guard log lines in range, `kit-audit` outputs, approvals, guard and sharing policies, `models.json` policy fields, permission lists only, agents' tools and models, version, health check, SHA-256 manifest. Scanned for credential-like text before it's kept; never personal notes, briefs, mail, library documents, or environment values. |
| Calendar stays read-only | `shared/bin/kit-holds` | Holds are RFC 5545 files (METHOD:PUBLISH, no attendees or organizer, VTIMEZONE from the zone's transitions, stable UIDs) placed inside working hours and around busy times; the owner opens and saves them. A clashing block is skipped, never moved. |
| Mail stays untouched | `shared/bin/kit-triage`, `kit-awaiting`, `kit-commitments` | Suggestions and drafts only: never move, flag, answer, or send; addresses masked; at most 80 characters quoted. |
| PPM Express writes | `shared/bin/kit-ppmx`, `shared/ppmx/`, ask rules in `kit_setup.py` | The only outside system Kit changes, by the owner's design: writes are confirmed, not disallowed. Claude Code asks before every `create_` and `update_` tool (and `kit-ppmx actions apply`), even when the server is allowed as a whole; agents can't make one (the connector guard denies write names) and scheduled runs can't answer the prompt. `PPMX_WRITES="off"` removes the change tools. A write that ends in a 5xx or a dropped connection or timeout is reported as unconfirmed and never resent; `kit-ppmx actions apply N --again` is needed after checking. Every read and write is logged without the token or any value: `kit-ppmx` (and its stdio server) to `ppmx-YYYY-MM.jsonl` in Kit's audit folder and standard error, the HTTP service to standard error. `kit-audit` reads the file. |
| Closed Claude runs | `shared/kit_claude.py`, `kit-preread`, `kit-rehearse` | Small headless jobs get the document's text in the prompt, with no shell, web, or MCP servers (`--strict-mcp-config` with an empty config) and none of the owner's permission rules; a budget check before and a cost record after; Claude Code asks before the owner starts one. |
| Text-back | `shared/bin/kit-textback` (macOS) | Answers only texts the owner sends themselves that start with "Kit". Questions run `claude -p --setting-sources project,local` (the owner's allow rules don't apply), read-only, inside Kit's folder, with the library in text-safe mode (`KIT_LIBRARY_SAFE=1`: work and confidential documents refused) and Kit's closed folders denied. Changes and `kit send N` reply with a one-time code and happen only on "kit yes CODE" (15 minutes, single use). Work content is never texted. `kit-textback test` is a dry run that sends and changes nothing. |
| Letter signing | `shared/bin/kit-letter`, ask rule | `kit-letter build` is allowed; `kit-letter sign` (which adds the saved signature) asks every time. The letters desk signs only a letter the owner asks it to sign, and never sends one. |
| Library mirror and fetch | `shared/bin/kit-library`, ask rules | `mirror` and `fetch` ask first. Work and confidential material (collections or output kinds marked so, or tagged so) is never mirrored to the synced phone folder, and nothing is when the sharing policy blocks the mirror folder. Long digit runs are blanked from the stored text. |
| Network lookups | `shared/bin/kit-expiry` | Looks certificates up over TLS and domains over RDAP only with `--live`; the health check and brief read the saved results. |
| Release zips | `shared/bin/kit-update --zip` | A zip is checked before extraction (paths, links and special files, one top-level folder, size and entry caps, layout, optional `--sha256`), extracted into a new temporary folder, and never run or imported, apart from its installer on `--apply` after a yes. No network. Rollback copies live only in `.install/releases/`, and pruning deletes only folders there that carry Kit's note. |
| Settings page | `shared/kit_settings.py`, `shared/kit_settings_ui.py`, `kit-settings ui`, ask rule | A local server started on demand that edits an allowlist of settings; threats and mitigations below. |
| Plugin builds | `shared/bin/kit-plugin` | Builds in a temporary folder and swaps it in; refuses to replace a plugin folder holding files it didn't write unless `--force`; never pushes or publishes. |

### The settings page's security model

`kit-settings show --all` and the dashboard's Settings panel only read. `kit-settings ui` writes, so it is
built as a small attack surface: Python's `http.server`, one request at a time, standard library only.

| Threat | Mitigation |
|---|---|
| Another computer on the network reaches the page | Binds `127.0.0.1` only, on a port the system picks; nothing listens once it stops. |
| Another local user or web page guesses its way in | A random token per run (`secrets.token_urlsafe(32)`) is in the opened link. The first load trades it for a session cookie (HttpOnly, SameSite=Strict, named for the port) and the link then stops working, so a copy in browser history or a terminal log is useless. Every request without the cookie (or an `X-Kit-Token` header) gets 403. Tokens are compared in constant time. |
| DNS rebinding (an outside site resolving its name to 127.0.0.1) | The Host header must be `127.0.0.1:<port>` or `localhost:<port>`, checked before anything else, the token included. |
| Cross-site request forgery from a page open in the same browser | Every POST needs an Origin (or, without one, a Referer) of the page itself, a CSRF token that is only in the page, and a JSON content type (which a plain cross-site form can't send). SameSite=Strict keeps the cookie off cross-site requests anyway. |
| Clickjacking and injected script | Content-Security-Policy `default-src 'none'`, script and style only with a per-page nonce, `frame-ancestors 'none'`, `X-Frame-Options: DENY`; every value is HTML-escaped; `Cache-Control: no-store`. |
| Changing a security setting through the page | Writes go only through `kit_settings.apply_edit`, which re-reads the settings and refuses any id that isn't on the allowlist: the connector guard, model routing, sharing policy and sharing fields, permission rules and `ALLOW_TOOLS`, commands Kit runs, backup location and encryption, phone approvals and publishing, connectors and agent reach, data rules, retention, and credentials stay read-only, each with how to change it (tests/test_settings.py posts to each and checks the files are unchanged). Adding to the allowlist is a code change. |
| A value that runs code or breaks a parser | The run config is shell, so its values may not hold quotes, `$`, backticks, backslashes, or control characters; setup values can't hold line breaks, start a heading or list item, or contain `**`. Each field is checked by type (channel, on/off, number range, weekdays, DD-Mmm-YYYY date, backticked path the way `kit_compliance.setup_path` reads it). Work delivery and work to-dos can't be routed outside Microsoft 365 here. |
| A credential written into a file or shown on screen | Values matching `kit_records.SECRET_PATTERNS` are refused on write and masked on display; keys named for a token, secret, or password are masked unless they hold a name (`_ENV`, `_KEYCHAIN`). The log masks the same way, and the server never logs request lines (the link holds the token). |
| A bad or lost edit | Preview first; a stale page (the value changed since it loaded) is refused; one line changes and every other byte stays; the old file goes to `.install/backups/settings/`; the change is committed (only that file) to Kit's private repo where it's tracked, and the page says when it isn't or the commit fails. |
| A page left open | It stops after 15 minutes with no request (`--idle`), on Stop, or on Ctrl-C. Claude Code asks before `kit-settings ui` starts (ask rule in `kit_setup.py`), so no agent or scheduled run opens it unasked. |

Not covered: a process already running as the owner can read Kit's files directly, so the page doesn't
try to defend against one; the cookie is visible to other servers on 127.0.0.1 the browser visits while
the page runs, which is why it's per run and useless once the server stops.

## 6. Scheduled runs

`platform/mac/morning/run.sh` (and `platform/windows/morning/run.ps1`) runs one mode per call:

```
launchd/Task Scheduler -> run.sh <mode>
  paused?  -> skip and log
  test-run marker or not done today? -> continue
  budget guard (kit-cost check): stop -> skip non-essential modes
  kit-outlook check (morning, weekly) -> stale notice if Outlook doesn't answer
  doctor --brief, kit-audit (morning, weekly)
  connector_health.py -> kit-connect test --json (morning; time-limited, no model cost)
  demand_refresh.py (weekly, DEMAND_REFRESH on) -> brief + guard-allowed read tools for the demand tracker
  prompt = shared/morning/prompt[-<mode>].md + notices (budget, stale, legal holds)
  allowlist = base rules + ALLOW_TOOLS (+ ALLOW_TOOLS_WEEKLY); ~/ rules get full-path twins
  model = MODEL_<MODE> from models.env (kit-models apply)
  lock (one run at a time; wait up to RUN_LOCK_WAIT; dead locks cleared)
  claude -p ... --output-format json   under a per-mode time limit
     (morning at the budget's stop level with DEGRADED_MODE on: no model call)
  kit-cost record -> cost ledger; text result -> log
  transient failure and no text? -> one retry after RETRY_DELAY (RETRY_ON); never after a
     time-out (rc 142/124) or a permission or policy refusal; the retry's cost is recorded
  morning only: no short text, a time-out, or a stop-level budget -> kit-degraded writes the
     brief and short texts from Kit's files (same privacy rules; never overwrites a model brief)
  deliver.py -> local notification / Outlook draft (never sent); optional OneDrive publish
  auto-commit Kit's folder; rebuild the dashboard
```

| Mode | Prompt | Default limit |
|---|---|---|
| `morning` | `prompt.md` | 1200 s |
| `weekly` | `prompt-weekly.md` | 3000 s |
| `worklist` | `prompt-worklist.md` | 900 s |
| `eod` | none: `kit-wrap`, no model call (Mon to Thu 17:30, Fri 15:30); `EOD_MODEL="on"` runs `prompt-eod.md` | 300 s (`RUN_TIMEOUT_EOD`); 1200 s with the model |
| `open`, `journal` | optional trading prompts | 1200 s |

Plain scripts with no model call: `kit-wrap` (the end-of-day run, through `run.sh eod`), `kit-digest`
and `kit-ppmx pulse` (sections `run.sh` adds to the weekly review and morning brief when turned on),
`preflight.sh` (06:45 and 15:45: one tiny Claude call and a sign-in check per connector in
`PREFLIGHT_CONNECTORS`, each problem told once per lapse), `kit-textback watch` (an always-on job that
calls Claude only for texted questions), `kit-backup` (the daily `backup` job at 12:30),
`kit-meetprep` (optional `meetprep` job,
weekdays every 30 minutes, honours `kit-pause`), `kit-holds`, `kit-triage`, `kit-awaiting`,
`kit-oneonone`, and `kit-wins` (the weekly review runs `kit-wins collect`). They read local files and
the calendar or mail tool's output, write only into `briefs/` (and `memory/accomplishments.md`), and
share helpers in `shared/kit_daily.py`.

The to-do sync is separate: `shared/reminders_sync.py` (macOS) and
`platform/windows/reminders/reminders_sync_win.py` are thin device backends over
`shared/kit_sync_core.py`, which reconciles `QUEUE.md` with "Kit Inbox" and "Kit: <owner>" lists
and routes `kit:`, `ask:`, and `approve <code>` items.

## 7. Sharing between Kits

```
Kit A                         shared root (synced folder)                Kit B
kit-publish --> kits/A/records/<type>/<id>.json + manifest.json  <-- kit-team sync
               kits/A/inbox/   kits/A/ack/                           (validate, cache)
kit-team send ---------------> kits/B/inbox/A--message--<id>.json --> kit-team inbox
```

- **Transport interface** (`shared/kit_transport.py`): publish, list, read, send to inbox, list
  inbox, acknowledge. `FolderTransport` serves any folder; `kit_sql_transport.SQLTransport` serves
  PostgreSQL, SQL Server, and MySQL (MySQL and PostgreSQL tested; SQL Server untested). `kit-team db-init` creates
  the database and tables; MySQL sessions use READ COMMITTED so readers see other Kits' commits.
- **Records** (`shared/records/`, `shared/kit_records.py`): JSON with a shared envelope; types are
  status-snapshot, decision, lesson, artifact-pointer, demand-rollup, handoff-pointer, and message.
  Summaries only; never document text, credentials, or personal notes.
- **Integrity:** each Kit writes only its own folder (except dropping into another Kit's inbox),
  atomically. Its manifest lists every record's sha256 and a hash chain of every change, so edits,
  removals, and rewritten history are detected.
- **Reading:** every record is schema-checked, must name the Kit whose folder it's in, and must
  match the manifest and chain. Failures are skipped and listed (`kit-team warnings`).
- **Cache:** `.install/cache/team.db` (SQLite, local only) holds validated records; the team
  dashboard renders from it. Retention and legal holds apply (`kit-team purge`).
- **Messages:** drafts first, sent only with the owner's yes at the keyboard; shown as information.
- **Team views** (`shared/kit_teamviews.py`, local cache only): `kit-team load` rolls each Kit's
  demand-rollup records (schema 1.1 adds optional kind, stage, opened) into open work per owner role,
  due windows, aging, and an overload flag; `kit-team experts` ranks Kits by shared evidence
  (decisions, artifact pointers, shared lessons, handoffs, roll-ups), recency-weighted, citing record
  ids. The optional `expertise` record (1.0) carries self-declared topics, listed beside the evidence
  and never counted as evidence. `kit-publish` stamps each record with its type's current schema
  version so older readers stay lenient.

### Architecture tools

All read-only, standard library, and local: `kit-refarch` scores the reference-architecture index
named in `standards.md` on the demand's terms (technologies and systems, content words,
non-functional requirements), phrases, and recency, marks superseded rows, and says "no good match"
below a threshold; related precedent comes from `kit-precedent`. `kit-sysprofile` assembles a
one-page system profile from the library's indexes and registers and an inventory export, citing
every line, and writes only with `--write`. `kit-sizing` is arithmetic from stated inputs and
overridable per-unit assumptions, with low, likely, and high ranges, handed to the cost estimator.
`kit-diagram-diff` parses draw.io (including compressed pages) and Visio `.vsdx`, matches pages by
name, compares components by id and connections by component id, so a rename doesn't look like
rewiring. `kit-diaglint` shares that parser (`shared/kit_diagram.py`) and checks each page against a
JSON rules file named in `diagrams.md`, so the team's standard stays in the owner's setup, not the
repo; it checks values set on the element itself (not defaults, masters, or style sheets) and exits 1
only on errors. The diagrammer lints before reporting; the reviewer lints diagrams beside a document.

`kit-onepager` extracts by heading and labelled field rather than with a model, so every line cites
its section and gaps read "not stated"; it writes only with `--write` or `--docx`. `kit-decisions`
classifies each minuted decision with explainable keyword rules and drafts proposed ADRs (numbers
never reused, duplicates caught by minutes file and row, nothing accepted). `kit-stakeholders`
matches entries against a fixed role list, so names can't get through, and marks influence and
interest as inferred.

`kit-viewpoints` extracts OV-1, SV-1, SV-4, and DIV-2 elements from headings, tables, and labelled
fields (keyword inference only for gaps, marked "(inferred)"), never invents an element, and builds
draw.io only through kit-drawio's JSON spec, so styles stay in one place. `kit-coverage` reads Kit's
existing artifacts, reuses kit-csf's math, and leaves required-ness to the framework profile; its
numbers are reading aids, not compliance scores. The TOGAF-style templates follow the structure of
TOGAF deliverables with headings paraphrased (TOGAF is a trademark of The Open Group) and say which IA
and GDS parts already supply each section.

`kit-lifecycle` stays local: `--import` reads a file the gateway already produced. A version past
standard support with an `extended` date still ahead is flagged `extended`, with its own urgency,
and the summary says it only counts if the subscription is held; `kit-roadmap` carries those items
too. A data-quality section counts records with no OS, duplicates, blank owners and environments,
and production names that look non-production (inferred).

Framework coverage is set per team: the framework profile in `compliance.md` says which frameworks
apply, and the risk and compliance mapper maps only against those. Frameworks are cited by name, ID,
and version; no benchmark or standard text is copied. The reviewer asks ten Secure by Design
questions paraphrased from CISA; the standards checker checks for a named hardening baseline and,
on request, fills in `zero-trust-rating-template.md` (CISA ZTMM 2.0); `kit-labcheck` warns when a
lab runbook names none. FEAF reference-model tags are optional on system profiles and catalog notes.

`kit-csf` reads a filled NIST CSF 2.0 mapping, checks Category IDs against `shared/data/csf2.json`
(IDs and names only, NIST CSWP 29), counts yes as 1 and partial as half over applicable categories,
and lists blanks without counting them; `--portfolio` aggregates mappings. The percentage is a
reading aid; compliance stays the framework owner's call. `kit-trace` traces each IA requirement to
the GDS section, test cases, change steps, and POC verdict (ID first, then cited section, then a
conservative keyword match marked "(inferred)") and flags requirements not addressed, untested, or
with no change step, plus orphan tests; missing documents show as "not checked".

**Design review pipeline.** A GDS draft goes to the red team first (it assumes the design is wrong
and ranks failure scenarios by consequence), then the threat modeler (STRIDE per data flow), then
the reviewer and standards checker. Both new agents run on a tools allowlist (no connector, web, or
agent tools) and write only to their own project folders (`red-team/`, `threat-model/`, and the
standards checker's `standards/`) plus a copy of each note, same file name, in the project's `reviews/`,
so every review of a draft is in one place. Nothing enforces the paths beyond the agents' rules: they
have no hooks, and Claude Code's permission rules aren't scoped per agent. kit-quality reads only the
reviewer's Findings tables and passes over the copies (`-red-team-v`, `-threat-model-v`,
`-standards-check-v` in the name), and kit-coverage reads them from their own folders, so nothing
counts twice. Threat-model controls go to the risk and
compliance mapper and test cases to the implementation planner, through Kit. `kit-review-loop`
runs the reviewer and then the three security agents on a draft, merges their findings into one
ranked list for the owner's decisions, and turns the decisions into the writer's feedback file.

**Connector health.** The morning run calls `connector_health.py`, which runs `kit-connect test
--json` (no `--read`, so no model cost) in the shell before the model and adds one PASS/FAIL line per
connector to the top of the brief. It's time-limited (`CONNECTOR_CHECK_TIMEOUT`, default 120 s),
never fails the run, and `CONNECTOR_CHECK="off"` skips it.

**Connector outages.** `connector_health.py` records one result per server per morning in
`briefs/connectors-history.jsonl` (nothing on a "not checked" morning). A streak at
`CONNECTOR_FAIL_STREAK` opens one outage in `briefs/connectors-alerts.json`, adds one owner work item
through `todo work` (de-duplicated by title), and `dashboard.py` shows a banner; a pass closes it. None
of this can fail the run.

**Run and cost alerts.** `run_alerts.py` runs at the end of every scheduled run and before the morning
and weekly model runs, time-limited and never failing the run. It reads only kit-reliability's run
outcomes and kit-cost's ledger, keeps open alerts in `briefs/alerts.json` (kinds `run` and `cost`),
adds one owner work item per outage (cost: one per level per month), and `dashboard.py` shows banners.
The sync writes `.install/logs/sync.ok` after a clean run, and kit-reliability reads run.ps1's
timestamps.

**Monitors.** `run_alerts.py` also hosts `monitor_drift.py`, `monitor_library.py`, and
`monitor_waiting.py`, each returning problems that one shared function turns into alerts (a queue
item per outage where the kind has one, a Recovered line, dry-run preview). Drift compares three
copies of each agent: `.install/kit/agents` (shipped), `agents/` (live), and `~/.claude/agents`
(installed, via `doctor.agent_drift`), after normalising the owner name and model line. Library
compares folder listings with the indexes' file columns without opening documents. Waiting reuses
`kit_queue`'s parser. All are read-only apart from follow-up drafts and queue items, time-limited,
and never fail a run.

**Guard integrity and least privilege.** `monitor_guard.py` checks every agent shipped with
connector-guard hooks still has all three installed (through `kit-hook` when the shipped copy uses it),
the guard's settings are readable, its audit folder is writable, and calls have result records (reusing
kit-audit's no-result check).
`kit-audit privileges` compares each agent's reachable tools with the connector calls the audit log
shows and suggests removals; it never edits an agent, and built-in tools show as "no usage data".
Readiness figures come from `doctor.py --readiness --json`, never hand counts.

**Compliance records.** `kit-exceptions`, `kit-pbc`, and `kit-audit-export --controls` share one
Markdown table parser (`kit_compliance.py`); registers live in the library and are read-only unless
`--write`. Evidence packs list each control's evidence for the period and name the gaps plainly; a
mapping is never evidence that a control is in place. Nothing calls a connector, the network, or a
model.

**Control frameworks as data.** `kit-controls` reads three compact derived files: NIST SP 800-53
Rev 5 (OSCAL 5.2.0; IDs, titles, one-line summaries, baselines; public domain), MITRE ATT&CK
Enterprise v20.0 (techniques, mitigations, links; MITRE's licence and notice kept in the file and in
outputs that show ATT&CK), and the Center for Threat-Informed Defense ATT&CK-to-800-53 mapping (Apache
2.0). Each records its source, commit, version, and retrieval date. `map` suggestions are keyword
matches labelled "(suggested)". CRI Profile content isn't bundled (different licence); it's cited by
name, version, and statement ID. ATT&CK: © 2026 The MITRE Corporation. This work is reproduced and
distributed with the permission of The MITRE Corporation.

**Questions, templates, and skills.** `kit-questions` keeps a per-project tracker; drafting messages
never marks questions asked (that happens after sending). `kit-templatecheck` compares a draft's heading
outline with its template. Skills install only where a name is free; a `.kit-installed.json` hash lets
a later install refresh Kit's own unedited copy.

**Monthly regulatory watch.** `reg_watch.py`, like `demand_refresh.py`, makes no outside call: it
decides due, skip, or on (first Monday, regimes set, budget below warn, enough time left) and adds
WebSearch, WebFetch, and Agent only when on, so the web is otherwise never in the weekly run's allowed
tools. The researcher searches with regime names only.

**Weekly demand refresh.** With `DEMAND_REFRESH` on, the weekly review delegates a scoped refresh to
the demand tracker after the audit: register rows only, one get per demand under its guard hooks,
never a whole-table search, a whole-table total treated as "filter ignored", stop on an
authentication failure. `demand_refresh.py` validates the settings against connector-guard.json and
adds only guard-allowed read tools; it skips with a line in the review at the budget stop level, when
settings are incomplete, or when time is short.

### Added in 1.5 and 1.6

| Feature | Design |
|---|---|
| PPM Express (`kit-ppmx`, `shared/ppmx/`) | One standard-library MCP server package run two ways: stdio for Claude Code and Claude Desktop with the owner's own token, and Streamable HTTP for a team on OpenShift, each caller sending their own token. Reads and writes (no delete); see the guardrail above. `pulse` keeps a weekly snapshot and diffs it; `actions` turns minuted actions into proposals made one at a time. |
| End-of-day wrap (`kit-wrap`) | Built from Kit's files with no model call, so it costs nothing and still runs at the budget's stop level; hooks in `.install/wrap.d/` add sections. |
| Review loop (`kit-review-loop`) | The IA and GDS review loop as one tool. `run` starts each agent as an unattended Claude Code run (`claude -p BRIEF --agent NAME` through `kit_claude.ask_claude`, as `kit-connect test --read` runs the gateway): Kit's login, the budget check before and a cost record after (mode `review-loop`), no MCP servers, Bash and web denied, reads allowed in Kit's folder and the library, writes only in the project folder. The reviewer runs first, then the three security agents in parallel threads; a note an agent saved in its own folder but not in `reviews/` is copied there. `merge` (no model call) takes the latest note of each kind in `reviews/`, found by its table (Findings; Consequence and Failure scenario; STRIDE and Threat; Result and Standard), and ranks every open finding: critical, high, and standards gaps are must fix; major, medium, partial, and not stated should fix; minor and low nits; fixed rows, threats with no gap, and conforming or not-applicable results are left out. It never overwrites a decisions file that has a decision. `feedback` keeps accepted and changed rows only, stops on a blank decision or a change with no note unless `--partial`, and numbers the file after the highest version among the feedback files and drafts. Plan estimates cost from the ledger's review-loop average, else an assumed $2 a run. |
| Pre-read and rehearsal (`kit-preread`, `kit-rehearse`) | Closed Claude runs through `kit_claude.py`: the document's text, the red team's playbook, and the team's standards in the prompt; output to `briefs/preread/` and `briefs/rehearse/`; never texted. |
| Library (`kit-library`) | Collections cataloged into an owner-only SQLite full-text index (`.install/library/index.db`, rebuilt from the folders, never committed or backed up); Office, PDF (through `kit-pdftext`, with on-device OCR for scans), web, EPUB, and Scrivener text; an output folder fed by `deliver`. On macOS, KitLibrary.app holds the folder permission and runs only index, flush, mirror, fetch, and check. Markdown is delivered as Word through textutil (macOS), python-docx, or Word over COM (Windows), else kept as Markdown with the reason. |
| Letters (`kit-letter`, letters desk) | A Word letter from plain text with the standard library; signing is its own command so it can ask every time. |
| Text-back (`kit-textback`, macOS) | KitMessages.app (Full Disk Access, nothing else) reads the owner's own conversation; commands answer from Kit's files, questions go to a read-only Claude run, and changes wait for a one-time code. |
| Vendor desk (`kit-vendors`) | Weighted RFP questions with must-haves, imported answers (CSV, XLSX, Markdown, DOCX), scores, dodge detection, and a drafted recommendation; no model call, nothing sent. |
| Team coverage map (`kit-teammap`) | Load from PPM Express (read only) or open items, single-person knowledge from a coverage file, and a cross-training plan. |
| Architecture digest (`kit-digest`) | One page from Kit's registers with no model call; a missing source only empties its section. |
| Expiry list (`kit-expiry`) | Everything that expires, soonest first; network lookups only with `--live`; the health check warns on Kit's own items. A `keychain` item's date comes from its Keychain entry's metadata (`security find-generic-password -s NAME` without `-w`: the comment's date, else a lifetime from the entry's last change), so no value is read and nothing prompts; Credential Manager keeps no such metadata, so Windows uses a date set by hand. Tokens due go in the brief's Renewals with a to-do. |
| Health score (`shared/kit_health.py`) | One number, 0 to 100, from four parts of 25 points: connectors (the morning check's latest result per server), runs (7-day outcomes, less open run alerts), audit (critical and warning findings and open integrity alerts), and setup (the share of setup fields set in the files the agents name). Read-only; the dashboard's badge, the Health panel, and `doctor.py --score`. |
| Readiness score (`kit-review-loop score`) | 100 less 12 per open must fix, 4 per should fix, 1 per nit, and 15 per review with no note, from the same parsing as `merge`, leaving out what the latest decisions file rejected. Ready for ARB needs all four notes, no must fix, notes newer than the latest draft, and `READINESS_THRESHOLD`. |
| Review loop page (`kit-settings ui`) | The settings page's Review loop section lists the library's projects with their score and note links (served read-only: Markdown inside that project's folder only, symlinks and `..` refused), confirms the paid runs with their estimated cost, starts `kit-review-loop run --yes` in the background (one at a time, logged), shows progress, and runs `merge`. Same token, cookie, Host, Origin, and CSRF checks as the rest of the page. |
| Ticket watcher (`ticket_watch.py`, `kit-tickets`) | The demand refresh's pattern for the morning run: the read-only tools come from connector-guard's own rules, only the gateway calls the connector, the run saves the gateway's JSON answer, and `kit-tickets diff` (no model or connector call) compares it with the saved baseline. Ticket text is cut to one line with addresses masked; texts get numbers and counts only. |
| MCP watchdog (`kit-mcp-watch`) | PostToolUse and PostToolUseFailure hooks on `mcp__.*` in `~/.claude/settings.json` (added and removed by the installer, recorded in its manifest), through `kit-hook` with `|| exit 1`, so they can never block. A failure that reads as a stale session or a lapsed sign-in is logged (server, tool, kind, a scrubbed summary, a hash of the session id) and Claude is told, once per server per session every 30 minutes, to stop retrying and ask for `/mcp` Reconnect or Authenticate. It suggests rather than reconnects: only Claude Code's `/mcp` can reconnect a server. |
| Monthly report (`kit-wins month`) | The month's wins from the log plus source items not collected yet, Kit's updates folded into one line, and the cost ledger's runs and spend against the month before; work run kinds by name (`MONTH_REPORT_MODES`), every other run as "other runs". Markdown and a self-contained print-ready HTML page. |
| Traceability workbook (`kit-trace --xlsx`, `shared/kit_xlsx.py`) | A standard-library .xlsx writer (inline strings, a frozen header, filters, wrapped text, shaded gap rows) so reviewers get the matrix in Excel with no add-ins. |
| Sign-off ledger (`kit-signoff`) | One Markdown table per project (`signoffs.md`), by role, with a Required line. Each sign-off keeps the approved file's SHA-256, so `check` tells an approved copy (by bytes, wherever it is) from an edited one and `status` notices an edit after approval. A document is its file name without the version and date. Read-only unless `--write`; nothing sent. |
| Trading insights (`kit-tradeinsights`) | Reads only the journals' tables of the owner's own trades (Close time, contract, P&L), skipping the trail guard, scalper, bot, and agentic-account sections, and the rule lines however they're bolded; when a journal is silent on the 13:00 rule, the close times decide it. Groups under 5 trades say so and never make a leak. Personal; no model, broker, or connector call. |
| Release cutting (`kit-release`) | From a clean clone: checks, edits VERSION, the CHANGELOG heading, and the docs' version rows, commits, tags, `git archive`s the zip into `dist/` with the commit in its comment, checks the zip the way `kit-update --zip` expects, and writes its SHA-256; puts the edits back if the commit fails; never pushes. |
| Personal rhythm (`kit-dates`, `kit-touch`, `kit-feedback`, `kit-meetload`) | Local lists and calendar reads that feed brief lines; nothing is sent; the feedback log is owner-only and never committed, exported, or texted. |

## 8. Model routing and kit-run

| Phase | What | Where |
|---|---|---|
| 1 | Profiles in `models.json`; `kit-models apply` writes agents' `model:` lines and `models.env` for runs | `shared/kit_models.py`, `shared/bin/kit-models` |
| 2 | Direct calls to Anthropic or OpenAI-compatible providers (OpenAI, Azure OpenAI, Ollama, LM Studio, vLLM, LiteLLM) through `kit-delegate` (command and MCP server), with dispatch policy | `shared/kit_providers.py`, `kit_secrets.py`, `kit_usage.py`, `shared/bin/kit-delegate` |
| 3 | `kit-run`: an agent loop outside Claude Code with rebuilt guardrails: MCP connectors from `kit-run.json`, frontmatter hooks, subagents along direct pairs, skills, KIT.md imports, ask-first approvals, audit log, cost ledger | `shared/bin/kit-run`, `kit_mcp_client.py`, `kit_hooks.py`, `shared/KIT-RUN.md` |

Claude Code itself runs only Claude models, so non-Claude models serve Kit through `kit-delegate`
or `kit-run`, never as Claude Code's own model. Precedence: organization ceiling, per-run override,
`models/<agent>.json`, the `agents`/`runs` maps, `default_profile`, built-in Opus.

## 9. Quality and measurement

| Measure | Where |
|---|---|
| Test suites | `tests/test_*.sh` (one per tool or module), run before every release |
| Agent evals | `tests/evals/`, `kit-evals` |
| Quality loop | Reviewer findings tables, `kit-quality` proposals for lessons and template changes |
| Health | `shared/doctor.py`: install, settings, schedules, runs, agents, models, connectors, policy, cost, version, MCP launch setup (for each user-scope server in `~/.claude.json`, without starting it, by server name only: `kit-mcp-env` credentials missing by entry name, in the entry or the launcher script it runs; TLS checking turned off; `npx` unpinned or `@latest`; a missing launcher script; `--env-file` files are never opened), and setup paths (path fields in `memory/context/*.md`, listed in `SETUP_PATH_FIELDS`, that look set but won't read as written: a value that doesn't start with a backticked path but has one later, or a backticked `<placeholder>`; "not set", "optional", and "none" are unset on purpose). Every reader of a path field takes only a value that starts with the backticked path. |
| Cost | `kit-cost` ledger per run and per model; budget guard |
| Metrics | `kit-metrics` page: spend, runs, queue trend, work lists, sprints, health, reliability |
| Run reliability | `kit-reliability` reads the run logs, `backup.log`, `sync.log`, and the cost ledger: success, degraded, and failure counts, time-outs, retries, and skips per run type over 7, 30, and 90 days against the window before; alerts on 2+ failures in 7 days, a 30-day success rate under `RELIABILITY_MIN_PCT`, median duration up more than 50%, no recent success of a morning, weekly, or backup run, or 8+ sync failures in 7 days; writes `briefs/reliability.json` for the dashboard panel, the metrics page, and the health check |
| Queue hygiene | `kit-queue`: stale items, duplicates, weekly trend |

## 10. Versioning, release, and patching

- `VERSION` is the release; `CHANGELOG.md` records changes under **Unreleased** until a release.
- The installer records version, commit, and install history in `.install/VERSION.json` and writes
  release notes when they change (`shared/kit_version.py`); the next brief shows them once.
- `kit-update` previews and applies updates from GitHub, keeping a backup branch. For installs with no
  git clone, `kit-update --zip FILE` updates from a release zip (`git archive` output: one top-level
  folder, the commit in the zip comment). The zip is untrusted input: entries are checked before
  anything is extracted (no absolute paths, `..`, drive letters, backslashes, symlinks, special or
  encrypted entries; one top-level folder; at most 200 MB and 20,000 entries; the expected layout), then
  extracted into a new temporary folder with fresh files and no set-id bits, and nothing from it is run
  or imported except, on `--apply` after confirmation, its own installer. `--apply` keeps the release
  in `.install/releases/<version>-<commit>/` with a `.kit-release.json` note (only folders with that
  note are pruned, to the last three) and records the zip's name, SHA-256, and commit in
  `VERSION.json` under `source`; `kit_version.py` reads the note too, so rerunning a kept release's
  installer (the rollback) records the right commit. The git path compares a zip install by version
  when the clone doesn't know its commit, and doesn't install the clone over a newer one.
- `.github/workflows/checks.yml` runs on every push and pull request: syntax for shell, Python, and
  PowerShell, job templates and JSON, a scan for personal details (patterns held in a repository
  secret), and named Python suites on Linux; the Windows installer for real (install, reinstall, repair)
  under Windows PowerShell 5.1 and PowerShell 7, with the PPM Express, wrap, rehearsal, vendor, team map,
  digest, and letter suites; and the PPM Express server's tests, its OpenShift files rendered, and its
  container image built and run the way OpenShift runs it.
- Kit isn't open source: `LICENSE` reserves all rights, and using Kit takes the copyright holder's
  written permission.
- The public repository carries no organization details, names, internal hosts, home paths, or
  credentials. Before anything is published, the maintainer's patch step scans every added line,
  file name, and commit message against a denylist and credential patterns, and refuses to publish
  on any hit (see GOVERNANCE.md).

## 11. Extending Kit

**Add an agent**
1. Write `kit/agents/<name>.md` in the standard format (frontmatter, then the body sections in
   section 4). Give it the fewest tools that work; add connector-guard hooks if it touches MCP.
2. Write its setup file `kit/memory/context/<name>.md` (fields "not set" or "optional").
3. Add a roster entry to `kit/memory/context/agents.md` (Does, Reach it, Routine, Setup), and a
   section to `DEPENDENCIES.md`.
4. Add eval cases in `tests/evals/<name>.json` and run `kit-evals <name>`.
5. Reinstall, then `doctor.py --fix-agents`.

**Add a tool**
1. Write `shared/bin/<tool>` in Python (standard library), with a usage docstring.
2. Add a test suite `tests/test_<tool>.sh`.
3. Add it to the link loop in `platform/mac/install.sh` (and a shim in `platform/windows/install.ps1`).
4. Document it in README.md's tools table and DEPENDENCIES.md; add a doctor check if it has state.

**Add a template**
1. Write `kit/templates/<name>-template.md`: an opening note ("Copy it, change it to suit the
   team"), a field table with a Classification row, DD-Mmm-YYYY dates, roles not names.
2. Index it in `kit/templates/README.md` and point a setup file or agent at it.
3. Run `bash tests/test_templates.sh`.

**Add a connector**
1. Add the MCP server to Claude Code.
2. Add it to `connector-guard.json` (`allowed_servers`, `allow_tools`, `deny_tools`; optionally
   `credential_env` and `probe_tools`) and to `memory/context/connectors.md`.
3. Use it only from guarded agents; run `kit-connect test`.

**Share content as a plugin**
1. `kit-plugin build <name> --agents ... --templates ... --lessons ... --skills ...` writes
   `.claude-plugin/plugin.json`, `agents/`, templates and lessons shipped as skills (a plugin's
   `CLAUDE.md` isn't loaded), and `REVIEW.md`, and adds the entry to
   `.claude-plugin/marketplace.json` (sources relative to the marketplace root; entry name equals the
   manifest name).
2. `kit-plugin check <dir>`: manifests, the public denylist, the credential scan, only `share: team`
   lessons, and a recorded human review for any hook, script, `bin/` file, MCP or LSP server, or
   monitor. Format per Claude Code's plugins reference and plugin marketplaces docs.
3. Merge through review on an internal git repo; `kit-plugin` never pushes.

**Add a scheduled run**
1. Write `shared/morning/prompt-<mode>.md`.
2. Add the mode to the `case` in `platform/mac/morning/run.sh` (prompt and text file) and to
   `run.ps1`.
3. Add a launchd template `com.USER.kit.<mode>.plist.template` and a Task Scheduler entry.
4. Add any tools it needs to `ALLOW_TOOLS`; add a test in `tests/test_runsh.sh`.

**Add a CI step**
1. Add a step to the right job in `.github/workflows/checks.yml` (`checks` on Linux, `windows-install`
   on Windows, `ppmx` for the PPM Express server). On Windows, one test per step: PowerShell fails a
   step only on its last command's exit code.
2. Say what the step runs in the comment at the top of the file.

## 12. Known limits

- `kit-update --zip` trusts a zip that passes its checks as far as running its installer; the SHA-256
  check is only as good as where the published value comes from, and zips aren't signed.
- Windows is narrower: the installer and the listed suites run in CI on Windows, but the Outlook COM
  adapters, the Task Scheduler tasks, `preflight.ps1`, and `uninstall.ps1` haven't run on a real Windows
  machine, and there's no text-back or Outlook check before runs.
- PPM Express's reads were confirmed against the live API on 02-Nov-2026 (paths against its OpenAPI
  description; shapes and field names against a tenant); its writes follow the description and are
  tested only against the fake server (`shared/ppmx/README.md`).
- The connector guard doesn't see PPM Express writes from Kit's own session; there the control is
  Claude Code's ask rules, and the audit is `kit-ppmx`'s own log.
- The SQL transport is tested on MySQL and PostgreSQL (password login over SCRAM tested; one shared
  role, so row-level security policies untested); SQL Server is untested.
- `kit-run` lacks MCP resources, prompts, sampling, OAuth sign-in, several hook types, web tools,
  and general shell access (see `shared/KIT-RUN.md`).
- Small and local models call tools less reliably; agents stay on Claude until evals pass.
- Standing enforcement gap: the connector guard covers only the five agents that carry its hooks (the
  gateway, demand tracker, intake triager, dependency mapper, and status reporter). Kit's own session,
  built-in agents, and the other agents whose tools aren't limited to a `tools:` list can reach MCP
  servers unguarded and unlogged; Claude Code's permission prompts are the only control there
  (`kit-audit` reports this gap; see docs/CONNECTIVITY.md).
- `kit-lifecycle` can't tell whether a paid extended-support subscription is held; `extended` items
  count as covered only once the owner confirms it.
- With the weekly demand refresh on, the connector's read tools are allowed for the whole unattended
  weekly session; only the prompt keeps Kit from calling them outside the guarded demand tracker.
- The filter check needs a connector to state a total at the top of its result; for one that
  doesn't, `kit-audit` reports "not checkable".
- Interactive session costs aren't in the cost ledger; Claude Code's `/cost` and `/usage` show them.
- Phone access is limited to Microsoft 365 routes and low-tier approvals until remote sessions are
  allowed.
- `kit-awaiting` needs a mail tool that lists sent items; meeting prep packs show attendees by role
  only where a stakeholder map matches, since the calendar feed carries no attendee list.
- Encrypted backups were exercised with OpenSSL 3 only (not LibreSSL) and with an
  environment-variable passphrase; a real Keychain read and Windows are untested. Generated holds'
  time zone blocks cover one year and haven't been imported into every calendar app.

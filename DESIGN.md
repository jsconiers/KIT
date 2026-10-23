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
| Plain and testable | Python standard library only for the core; every tool has a test suite (`tests/`). |

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
|     |-- subagents (~/.claude/agents/*.md): the 32 staff          |
|     |      gateway --MCP--> outside systems (guarded, read-only) |
|     |-- skills (~/.claude/skills): docx, pptx, xlsx, pdf, ...    |
|     `-- tools: Read/Edit/Bash, kit-* commands                    |
+------------------------------------------------------------------+
         ^ scheduled runs: run.sh / run.ps1 -> claude -p <prompt>
         | (morning, weekly, worklist, eod, sync)
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
| Hooks | The connector guard runs as PreToolUse, PostToolUse, PostToolUseFailure, and Stop hooks in the frontmatter of every agent that reaches outside systems. |
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
| Connector guard | `shared/bin/connector-guard` | Hook on guarded agents: allows only servers and tools in `connector-guard.json`, denies writes, records each call, result, and failure (with the tool use id) in the audit log. Denies on its own errors. |
| Audit review | `shared/bin/kit-audit`, auditor agent | Daily and weekly checks: denied calls, calls with no result, unguarded agents, volume, off-hours use, and searches that may have ignored their filter (a stated total far above the limit, or the same total for different queries; tool, time, total, and limit only, never the query). Issues go to the top of the brief and a dashboard banner. |
| Kill switch | `shared/bin/kit-pause` | A pause file stops every scheduled run and makes the guard deny every connector call. |
| Sharing policy | `memory/context/sharing-policy.json`, `kit_transport.policy_check` | Allowed transports and roots, blocked folders, classification ceiling, confidential never leaves unless allowed. A policy that can't be read refuses all sharing. |
| Model policy | `models.json` `org_profile`, `kit_models.py` | Allowed providers, `enabled_phase`, data-class ceilings per provider and for non-Claude providers. Refused profiles fall back to Claude. |
| Credentials by name | `shared/kit_secrets.py`, tool designs | Credentials are referenced by environment-variable or Keychain entry name, resolved only at call time, never stored, logged, or printed. |
| Untrusted content | Agents, `kit-team`, `kit-run` | Other sources' text is shown with an untrusted banner and never executed. |
| Phone approval tiers | `shared/kit_inbox.py` | Low tier (work list, queue verdicts) by single-use daily code; medium and high tier (commits, installs, sending, deleting, settings, money) never from a phone. |
| Retention and legal hold | `shared/bin/kit-retention` | Keep everything by default; disposal only moves files, with `--yes`; held projects are never eligible. |
| Encrypted backups | `shared/bin/kit-backup` | Encrypt-then-MAC: `openssl enc -aes-256-ctr -pbkdf2 -iter 600000 -md sha256` with the passphrase on a file descriptor (never argv), then HMAC-SHA256 over a JSON header and the ciphertext with a key from PBKDF2-SHA256 (600,000 iterations, separate random salt). File format `KITBAK1` + header length + header + ciphertext. The HMAC is checked before anything decrypts. The passphrase comes from a Keychain entry or environment variable the owner creates. Plain backups are refused outside home and in synced or shared folders unless `--allow-plain`. |
| Audit evidence | `shared/bin/kit-audit-export` | A dated pack: guard log lines in range, `kit-audit` outputs, approvals, guard and sharing policies, `models.json` policy fields, permission lists only, agents' tools and models, version, health check, SHA-256 manifest. Scanned for credential-like text before it's kept; never personal notes, briefs, mail, library documents, or environment values. |
| Calendar stays read-only | `shared/bin/kit-holds` | Holds are RFC 5545 files (METHOD:PUBLISH, no attendees or organizer, VTIMEZONE from the zone's transitions, stable UIDs) placed inside working hours and around busy times; the owner opens and saves them. A clashing block is skipped, never moved. |
| Mail stays untouched | `shared/bin/kit-triage`, `kit-awaiting`, `kit-commitments` | Suggestions and drafts only: never move, flag, answer, or send; addresses masked; at most 80 characters quoted. |

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
| `eod` | `prompt-eod.md` | 1200 s |
| `open`, `journal` | optional trading prompts | 1200 s |

Plain scripts run outside `run.sh` with no model call: `kit-backup` (the daily `backup` job at 12:30),
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
agent tools) and write only to their own project folders (`red-team/`, `threat-model/`), outside
`reviews/`, so kit-quality reads only the reviewer's notes. Threat-model controls go to the risk and
compliance mapper and test cases to the implementation planner, through Kit.

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
connector-guard hooks still has all three installed, the guard's settings are readable, its audit
folder is writable, and calls have result records (reusing kit-audit's no-result check).
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
| Health | `shared/doctor.py`: install, settings, schedules, runs, agents, models, connectors, policy, cost, version |
| Cost | `kit-cost` ledger per run and per model; budget guard |
| Metrics | `kit-metrics` page: spend, runs, queue trend, work lists, sprints, health, reliability |
| Run reliability | `kit-reliability` reads the run logs, `backup.log`, `sync.log`, and the cost ledger: success, degraded, and failure counts, time-outs, retries, and skips per run type over 7, 30, and 90 days against the window before; alerts on 2+ failures in 7 days, a 30-day success rate under `RELIABILITY_MIN_PCT`, median duration up more than 50%, no recent success of a morning, weekly, or backup run, or 8+ sync failures in 7 days; writes `briefs/reliability.json` for the dashboard panel, the metrics page, and the health check |
| Queue hygiene | `kit-queue`: stale items, duplicates, weekly trend |

## 10. Versioning, release, and patching

- `VERSION` is the release; `CHANGELOG.md` records changes under **Unreleased** until a release.
- The installer records version, commit, and install history in `.install/VERSION.json` and writes
  release notes when they change (`shared/kit_version.py`); the next brief shows them once.
- `kit-update` previews and applies updates from GitHub, keeping a backup branch.
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

## 12. Known limits

- Windows support is built and logic-tested on macOS only; real Windows, Outlook COM, and Task
  Scheduler behavior is untested.
- The SQL transport is tested on MySQL and PostgreSQL (password login over SCRAM tested; one shared
  role, so row-level security policies untested); SQL Server is untested.
- `kit-run` lacks MCP resources, prompts, sampling, OAuth sign-in, several hook types, web tools,
  and general shell access (see `shared/KIT-RUN.md`).
- Small and local models call tools less reliably; agents stay on Claude until evals pass.
- The connector guard only governs agents that carry its hooks (the gateway, demand tracker,
  intake triager, dependency mapper, and status reporter); Kit's own session and other agents with connector tools can still call connectors
  unlogged (`kit-audit` reports this standing gap).
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

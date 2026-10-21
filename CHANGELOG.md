# Changelog

What changed in each Kit release. The installed version is in
`~/Claude/Agents/kit/.install/VERSION.json` (`kit-version` prints it). After an update, the next
morning brief summarizes the new entries once. Format: [Keep a Changelog](https://keepachangelog.com),
versions follow [semantic versioning](https://semver.org).

## [Unreleased]

### Added
- red-team agent (roadmap G1): adversarial architecture critic before peer review, with
  `red-team-review-template.md`; threat-modeler agent (G2): STRIDE threat model per data flow,
  feeding the risk and compliance mapper and implementation planner, with
  `threat-model-template.md`. Staff is now 32 subagents.
- `kit-trace` (G3): traceability matrix from IA requirements to GDS sections, test cases, change
  steps, and POC verdicts, with gap counts, `--json`, and `--write`; the implementation planner and
  GDS writer run it; `traceability-matrix-template.md`.
- NIST CSF 2.0 mapping (J5): `csf-mapping-template.md` (6 Functions, 22 Categories) and `kit-csf`
  (coverage per Function, gaps, blanks, ID checks against `shared/data/csf2.json`, `--portfolio`).
- Weekly demand refresh (off by default): the Monday review has the demand tracker re-check its
  register's demands, read-only and guarded, and adds "Demands: what changed". Keys `DEMAND_REFRESH`,
  `DEMAND_SERVER`, `DEMAND_TOOLS`, `DEMAND_REGISTER_DIR`, `DEMAND_REFRESH_MAX`,
  `DEMAND_REFRESH_MIN_LEFT`.
- `kit-lifecycle --import FILE`: turns a CMDB export (JSON list, records, result, rows and columns,
  or CSV) into `inventory.json`, with OS aliases, skip counts, and duplicate marking; a data-quality
  section in the lifecycle summary.
- `kit-audit`: "Searches that may have ignored their filter" warning (a stated total far above the
  limit, or the same total for different queries); "not checkable" when the log has no totals.
  connector-guard now logs a result's stated total (`result_total`, a count only).
- Morning brief: a connector health line at the top (kit-connect test, no model cost, 120-second
  limit, never fails the run; `CONNECTOR_CHECK`, `CONNECTOR_CHECK_TIMEOUT`).
- Framework profile in the `compliance.md` setup; the risk and compliance mapper maps only against
  frameworks that apply.
- `zero-trust-rating-template.md` (CISA ZTMM 2.0); the standards checker fills it in on request.
- Reviewer: ten Secure by Design questions (CISA 2023/2024) in the design-risk step.
- Hardening baseline field in the lab runbook template; the standards checker checks designs for one;
  `kit-labcheck` warns when a runbook has none.
- Optional FEAF reference-model tags on system profiles, curator system pages, and catalog notes.
- `kit-reliability`: success rate, duration, cost, timeouts, degraded briefs, retries, and skips per run
  type over 7, 30, and 90 days, with alerts; dashboard panel, metrics section, health check.
- Auto-retry in run.sh and run.ps1: one retry after a transient failure (RETRY_ON, RETRY_DELAY).
- The private mail tool gained read-only sent-items commands (for kit-commitments and kit-awaiting),
  retries an Outlook timeout (-1712), and never starts Outlook itself. (The mail tool lives outside the
  public package.)
- `kit-team db-init`: creates the sharing database and Kit's tables (MySQL, PostgreSQL), safe to
  rerun; a live test for real servers (`tests/live/test_sql_live.py`) and an offline test of db-init.
- Daily backup job (`com.USER.kit.backup`, 12:30; Windows task "Kit Backup"): runs `kit-backup` with the
  config's settings; the health check confirms it's loaded.
- Encrypted backups to a location you choose (local, network share, or synced folder): AES-256 via
  openssl with PBKDF2, passphrase from the Keychain or an env var on a file descriptor, HMAC-SHA256
  checked before decrypting; unencrypted backups refused outside home or in shared folders unless
  --allow-plain; `kit-backup --dir`, `--encrypt`, `--no-encrypt`.
- `kit-audit-export`: dated evidence pack for compliance or security reviews, with a SHA-256 manifest
  and a credential scan.
- `kit-holds`: draft calendar holds as RFC 5545 .ics files (focus, study, deadline prep, meeting
  prep) inside working hours and around busy times; the owner opens and saves them. Kit stays
  read-only on the calendar.
- Degraded mode (`kit-degraded`, DEGRADED_MODE): at the budget's stop level, and when the morning run
  fails or times out, the brief is written from Kit's files with no model call. In run.sh and run.ps1.
- Architecture tools: `kit-refarch` (reference architecture matcher), `kit-sysprofile` (system
  profile from the library's records, cited), `kit-sizing` (rough-order sizing with every
  assumption), and `kit-diagram-diff` (draw.io and Visio diagram comparison); templates for system
  profiles and sizing.
- Daily tools: `kit-wins` (accomplishments log), `kit-oneonone` (1:1 prep), `kit-meetprep` (meeting
  prep packs, optional 30-minute job), `kit-triage` (inbox suggestions), `kit-awaiting` (sent mail
  awaiting a reply; needs a mail tool with sent-items commands).
- Team demand load view (`kit-team load`, Team load panel on the team dashboard): open demands, IAs,
  GDSs, and POCs per Kit by owner role, by stage and due window, with aging and an overload flag.
  demand-rollup schema 1.1 (optional kind, stage, opened); kit-publish stamps each record with its
  type's current schema version.
- Expertise finder (`kit-team experts <topic>`): Kits ranked by shared evidence with record ids cited;
  optional `expertise` record type for self-declared topics (`memory/context/expertise.md`).
- `kit-plugin`: package agents, templates, shared lessons, and skills as a Claude Code plugin
  marketplace for an internal git repo, with a review gate (manifests, public denylist, credential
  scan, share: team lessons, recorded review of hooks and scripts). Never publishes or pushes.
- Distribution docs: `INSTALL.md` (complete install and configuration guide) and `DESIGN.md`
  (design guide and extension steps); README.md rewritten for newcomers. The installer copies both
  into `.install`.
- Version stamp and release notes: `VERSION`, this changelog, `VERSION.json` with install history,
  `kit-version`, and a "What changed in Kit" section in the first brief after an update.
- Model routing phase 1: `models.json` (profiles deep, standard, fast; default deep = Opus),
  optional `models/<agent>.json`, and `kit-models` (show, check, apply). Scheduled runs take their
  model from `models.env`. Claude models only for now.
- Labs: request and approval workflow (no final runbook without approval), lab register with
  hardware on loan and idle and overdue flags, and `kit-labcheck` for production or confidential
  data in lab requests and runbooks.
- Researcher vendor evaluation mode; curator records POC and lab outcomes as precedents.
- Future tech: tech debt register, vendor landscape with renewal warnings, and a standards feedback
  loop (adopt or hold votes list the standards to update; the standards checker flags stale ones).
- Templates: tech debt register and vendor landscape.
- Model routing phase 2 (off until `enabled_phase` is 2): Anthropic and OpenAI-compatible clients
  (OpenAI, Azure OpenAI, Ollama, LM Studio, vLLM, LiteLLM), credentials by environment-variable or
  Keychain entry name, dispatch policy by provider and data class, and `kit-delegate` (command and
  MCP server).
- `kit-run` (experimental, phase 3): run one of Kit's agents outside Claude Code with rebuilt
  guardrails (read and search limits, ask-first writes to the agent's paths, read-only Kit
  commands, audit log, cost ledger); connectors, hooks, subagents, and skills followed (below).
- Cost by model: each ledger line records per-model cost and tokens; `kit-cost report --by model`;
  `kit-cost record-usage` for kit-delegate and kit-run.
- Windows runner parity: work list, kit-pause, budget guard, cost recording, model from models.env,
  time limits that end a stopped run's process, and the run lock; new task and command shims.
  Untested on a real Windows machine.
- Training: protected focus time, training kits, learning paths, and a skills matrix by role.
- Radar views for three audiences, and an innovation intake funnel with gates.
- Meeting action loop: the scribe's actions become proposals in `briefs/pending-actions.md`, added
  to the queue only once confirmed.
- End-of-day wrap-up (`run.sh eod`, weekdays 17:30; job template only).
- `kit-metrics` (one-page metrics view) and `kit-project` (project folder skeleton by type).
- `kit-run` parity: MCP connectors from `kit-run.json` (allowlisted tools, guarded by the connector
  guard), Claude Code-style hooks, subagents along the direct pairs, skills (scripts only from an
  allowlist with approval), KIT.md imports, and richer approvals.
- Future tech: `kit-lifecycle` (end-of-support early warning from an inventory and sourced EOL
  dates; never calls an outside service), `kit-roadmap` (draft 1-to-3-year roadmap), and a weekly
  regulatory and industry watch; templates for both.
- Governance (`GOVERNANCE.md`, draft) and onboarding (`ONBOARDING.md`); the onboarding guide answers
  "how do I use Kit".
- Organization profile for sharing between Kits (`sharing-policy.json`), enforced on publish and send.
- `kit-connect` (connector check: credentials by name, Claude Code health, optional single read) and
  `kit-evals` (static agent checks, and live runs with `--live --yes`; gates model changes).
- Phone access phase 1: Kit Inbox keywords ("kit:", "ask:"), single-use daily codes for low-tier
  approvals, and briefs published to a private OneDrive folder (off until set).
- `kit-commitments`: proposes to-dos from promises in your own sent mail or minutes, confirmed in a
  session.
- Messages between Kits (`kit-team send`, with the owner's yes), inbox verification against the
  sender's manifest and a per-Kit hash chain, acks, expiry archive, and retention and legal holds on
  the team cache (`kit-team purge`).
- SQL transport for PostgreSQL, SQL Server, and MySQL (UNTESTED; DDL and grants in shared/sql/).
- `kit-quality`: recurring reviewer findings become proposed lessons and template changes; a weekly
  quality step; the reviewer writes a Findings table.
- The to-do sync lives once in `shared/kit_sync_core.py`; Windows gains Kit Inbox routing. Mac
  behaviour is unchanged (checked against a frozen copy of the old code).

### Changed
- `kit-lifecycle` flags versions past standard support but inside paid extended support as
  `extended` (urgency from the extended end) instead of `past`; `counts` gains `extended`, other
  keys unchanged. `kit-roadmap` includes them (year 1 when the extended end is within 12 months).
- Gateway: pages large results with an explicit sort order and offsets, and says whether ordering
  was guaranteed.
- Intake triager: checks precedent (through Kit) before the impact-assessment call and cites it, or
  records "Precedent check requested".
- To-do sync: confirmed both platform entries call the one `reconcile()` in
  `shared/kit_sync_core.py`; nothing duplicated remains (issue #2).
- First live connector runs: the demand tracker, intake triager, status reporter, and a lifecycle
  review (kit-lifecycle with researcher-sourced end-of-support dates) ran on real ServiceNow data
  through the gateway. INSTALL now says to check that a filtered search's count is plausible, since
  a filter on an unknown field can be silently ignored.
- The demand tracker runs under the connector guard (pre, post, and failure hooks), so its ServiceNow
  calls are checked and logged like the gateway's. Closes one of the two standing enforcement gaps.
- The MySQL SQL transport (PyMySQL) is now tested against MySQL 8.0; PostgreSQL and SQL Server stay
  untested.
- Unencrypted backups to a folder outside home or to a synced or shared folder now need
  `--allow-plain` (or encryption).

### Fixed
- `kit-connect --read` reported a working connector as failed: the gateway reads its setup before the
  call and hit the 3-turn limit. Turns raised to 10, and the connector guard's audit log now decides.
- MySQL sharing: readers kept a stale snapshot (REPEATABLE READ) and missed other Kits' newer
  messages and changes; MySQL sessions now use READ COMMITTED. Found in the first live test.
- Weekly review timed out (20-minute limit) and overlapped the morning brief. Runs now have their
  own time limits (weekly 50 minutes), wait for each other through a lock, report a timeout
  plainly, and the weekly review moves to Monday 06:30.
- The health check credited a failure notice to the wrong run when runs overlapped.
- `kit-connect list` crashed when a server had no probe tool.

## [1.4.0] - 2026-10-17

### Added
- Staff of 30 subagents, including the POC lead, training lead, future tech planner, lab planner,
  and precedent finder, with setup templates in `kit/memory/context/`.
- Templates folder with 15 document templates indexed by work type (POC, labs, training, research,
  future tech, decisions, stakeholder maps).
- Sharing between Kits, phase 1: transport interface, folder adapter (per-Kit folders, hash
  manifest, sync-conflict handling, inbox and acknowledgements), local SQLite cache, `kit-team`.
- Cost control: `kit-cost` ledger from scheduled runs and a monthly budget guard.
- Queue hygiene (`kit-queue`: stale items, likely duplicates, verdicts applied with a backup) and
  sprints (`todo sprint`, dashboard panel with a burndown).
- Operations: `kit-update`, `kit-pause`, `kit-backup`, `kit-retention` with legal holds,
  `kit-outlook`, `kit-precedent`, and the Monday-to-Thursday work list.
- Weekly review additions: horizon scan, sprint review, cost section, monthly retrospective.

### Changed
- Connector guard logs failed calls through a PostToolUseFailure hook; `kit-audit` pairs calls and
  results by `tool_use_id`.

## [1.3.0] - 2026-10-15

### Added
- Morning brief, weekly review with the auditor, cross-platform delivery (`kit-settings`), work and
  personal split, and Outlook Tasks sync.
- Windows adapters (first draft, untested on Windows).

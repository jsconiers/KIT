# Changelog

What changed in each Kit release. The installed version is in
`~/Claude/Agents/kit/.install/VERSION.json` (`kit-version` prints it). After an update, the next
morning brief summarizes the new entries once. Format: [Keep a Changelog](https://keepachangelog.com),
versions follow [semantic versioning](https://semver.org).

## [Unreleased]

## [1.5.0] - 2026-10-29

### Added
- `kit-preread`: a pre-read for a design or architecture review. Kit's red team reads the document (Word,
  PowerPoint, Excel, OpenDocument, text, or PDF) in a closed run: its text goes in the prompt with the
  red team's playbook and the team's standards, with no shell, web, MCP servers, or your own permission
  rules (a PDF Kit can't turn into text is read from a temporary copy, with private folders denied). It
  writes briefs/preread/: a verdict, the five findings that matter most, what the document doesn't say,
  and five questions to ask, each tied to a finding. `--meeting`, `--date`, `--deliver` (Kit Output >
  Reports > Pre-reads), `--dry-run`, `--list`. Work content: never texted. Claude Code asks before it
  runs (it's a paid run).
- `kit-meetprep`: a design or architecture review's pack links its pre-read, or says how to make one.
- `kit_claude`: `prompt_stdin=True` sends a long prompt on standard input (Windows caps a command line at
  32,767 characters); `agent_prompt(NAME)` gives a closed job one of Kit's staff playbooks; a missing
  `claude` command is exit 127 instead of a crash; on Windows the PATH is left as it is.
- `kit-touch`: keep in touch. Who you haven't talked to in a while, each with their own rhythm; past
  calls and meals on the calendar ("Call with NAME", "Lunch with NAME") count as talking, coming ones
  mean it's planned; `talked`, `snooze`, `scan [--add]`, and brief lines (work contacts tagged [work]).
  Texting Kit: `touch`, `talked to NAME [yesterday]` (also `called`, `texted`).
- `kit-feedback`: a private feedback log on the people you lead (praise, coaching, observations,
  goals, concerns): `prep NAME` for a 1:1, `review NAME` for a review period, `met`, `done`, and [work]
  brief lines (today's 1:1s from the calendar; who's had no note lately). Kept in feedback/,
  owner-only, never committed, exported, or texted.
- `kit-meetload`: a meeting load audit, week by week: hours and share of working hours, recurring
  meetings and their weekly cost (and the ones you run), back-to-back runs, focus blocks left,
  meetings outside working hours, double bookings, and suggestions; `--holds` drafts focus-time holds
  through `kit-holds`; `--json` and `--ics` inputs (daily, weekly, and monthly repeats expanded);
  `work` and `personal` profiles; `brief` lines. Windows `kitcal` events now carry `my_response`,
  `i_organize`, and `show_as`.
- `kit-library`: scanned PDFs are read with on-device OCR (Apple Vision, `kit-pdftext --ocr`; settings
  `ocr.pdf` and `ocr.max_pages`); `mirror` copies Kit Output one way to a synced folder (`output.mirror`,
  for example iCloud Drive) after each delivery; `fetch ID [--to-phone]` stages a cataloged file for
  sending. KitLibrary.app also runs mirror and fetch. A kind added in a later version now appears in an
  existing collections.json on its own.
- Texting Kit: `send N` texts the Nth document of the last `find` or `sermons` list as an attachment
  (and copies it to the synced "Sent to phone" folder); `kit-textback propose KIND JSON SUMMARY` lets
  Kit's own jobs ask for a code-confirmed change by text.
- `kit-library`: collections (folders you choose, each with a name, description, tags, tag rules, and
  exclusions) cataloged into a full-text index with each document's text (Word, RTF, OpenDocument,
  PowerPoint, Excel, PDF through the new `kit-pdftext`, web pages, EPUB, Scrivener) and the scripture
  passages it cites; `search` (phrases, OR, prefixes, `--in`, `--tag`, `--type`, `--year`, `--ref`),
  `show --text` (agents read Office files from the catalog), `recent`, `tags`. An output folder with kinds
  (`deliver`: markdown arrives as Word, never overwrites without `--replace`, cataloged on arrival).
  macOS: KitLibrary.app holds the Documents permission and runs only index, flush, and check; a
  nightly job and a WatchPaths refresh. Long digit runs are blanked from the stored text.
- Texting Kit: `week`, `mail`, `find` / `find more`, `sermons on PASSAGE`, `approve CODE ITEMS`; changes
  confirmed by a one-time code (`event`, `move`, `draft` (a Mail draft only), and plug-in ACTIONS), with
  `yes CODE` / `no`; `TEXTBACK_PARSE_MODEL` (default haiku) for reading events out of texts; questions by
  text can search the library.
- `kitmail inbox` reads Mail's own index (headers only) through KitMessages.app when it has Full Disk
  Access: allowed accounts only, failing closed when an exclusion can't be verified; otherwise it asks
  Mail as before. Doctor checks for the library and the quick inbox.
- `kit_claude.py`: one helper for small headless Claude jobs (budget check, cost record, tool limits,
  just the MCP servers a job needs).
- Letters desk (`kit/agents/letters-desk.md`, setup in `memory/context/letters.md`, log in
  `letters/log.md`): formal personal letters from draft to reply, a log of what went out (date,
  method, certified tracking, reply due), and follow-ups. Never sends anything.
- `kit-letter`: a Word letter from plain text, standard library only. `kit-letter build` leaves room
  for a pen signature; `kit-letter sign` adds your saved signature (a transparent PNG in
  `letters/signature/`), and Kit's settings ask you to approve every signing. The letters desk signs
  only a letter you ask it to sign, and logs it. Tested on Linux and Windows in CI.
- The installers now link `kit-letter` and `kit-expiry` (`kit-expiry` was missing from both lists).
- `kit-controls`: NIST SP 800-53 Rev 5 (OSCAL 5.2.0), MITRE ATT&CK Enterprise v20.0, and the CTID
  ATT&CK-to-800-53 mapping as compact data; lookups, search, and suggestions for a threat model. Threat
  models get ATT&CK and 800-53 columns; red-team notes optional ones. The framework profile lists the
  CRI Profile v2.x and NIST SP 800-53 Rev 5.
- `kit-exceptions` (policy exception register with an exceptions monitor), `kit-audit-export
  --controls/--request/--only` (control evidence packs), `kit-pbc` (audit request tracker); compliance.md
  fields Exception register, Control map, PBC tracker; templates exception-register, pbc-tracker,
  control-map.example.json.
- Guard integrity monitor (`MONITOR_GUARD`); `kit-audit privileges` least-privilege review with a
  quarterly weekly-review line; `doctor.py --readiness [--json]` as the source of readiness figures.
- `kit-questions` open-question tracker (question-tracker template); the IA writer, GDS writer, and
  intake triager use it.
- Skills `exec-summary` and `requirements-extraction`, installed without overwriting; `kit-templatecheck`
  template drift check used by the writers and reviewer.
- Monitors (roadmap F, slice 3): agent drift (shipped vs live vs installed; `kit-alerts drift --diff`),
  library freshness (published documents missing from the indexes, an inferred cloud-sync stall),
  and items waiting too long (follow-up drafts in `briefs/followups/`, never sent); dashboard banners
  and brief lines; keys `MONITOR_DRIFT`, `MONITOR_LIBRARY`, `MONITOR_WAITING`, `MONITOR_TIMEOUT`,
  `LIBRARY_UNINDEXED_MAX`, `LIBRARY_INDEX_MAX_DAYS`, `LIBRARY_SYNC_MAX_DAYS`, `WAITING_MAX_DAYS`.
- Run and cost alerts (`run_alerts.py`, `kit-alerts`): failed or overdue scheduled runs, a cost
  projection over the warning level, spend over the stop level, and daily spikes with no budget each
  get a queue item, a dashboard banner, and a brief line, cleared on recovery. Keys `RUN_ALERTS`,
  `RUN_ALERTS_TIMEOUT`, `RUN_FAIL_STREAK`, `RUN_WINDOW_<MODE>`, `COST_ALERT_PROJECTION`,
  `COST_SPIKE_FACTOR`.
- `kit-viewpoints` (J4): DoDAF-style OV-1, SV-1, SV-4, and DIV-2 drafts from a GDS, cited, with draw.io
  output and optional lint; `viewpoints-template.md`; the diagrammer offers it on request.
- `kit-coverage` (J10): framework coverage per design and across the portfolio, HTML and JSON in
  `briefs/`, respecting the framework profile.
- TOGAF-style deliverable templates (J2): architecture vision, statement of architecture work,
  architecture definition document, architecture requirements specification, transition
  architecture, implementation and migration plan; on request, named in `writing.md`.
- `kit-diaglint`: lints draw.io (compressed or not) and Visio diagrams against a JSON rules file
  (palette, fonts, minimum text size, title block, legend, connectors, line types, shapes, page and
  view labels); example rules in `templates/diagram-lint-rules.example.json`; optional Lint rules field
  in `diagrams.md`; the diagrammer lints before reporting and the reviewer lints diagrams beside a
  document. `kit-diagram-diff` now shares its parser through `shared/kit_diagram.py`.
- `kit-onepager`: cited one-page executive summary of an IA or GDS (Markdown, JSON, Word);
  `executive-onepager-template.md`; the deck builder offers it with decks.
- `kit-decisions`: proposed ADR drafts from architectural decisions in meeting minutes; the meeting
  scribe flags them and the decision recorder reviews each draft.
- `kit-stakeholders`: role-only stakeholder maps from the library; the status reporter asks for one
  and the handoff agent uses it.
- Connector outage alerts: two failed morning checks in a row (`CONNECTOR_FAIL_STREAK`) add one work
  item and a dashboard banner; recovery clears them.
- Monthly regulatory watch (`REG_WATCH`, off by default): first-Monday researcher brief on the regimes
  in `compliance.md`, public sources only, saved in the library.
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
- The GitHub checks use `actions/checkout@v7` and `actions/setup-python@v7`, which run on Node.js 24,
  so the Node.js 20 deprecation warnings are gone.
- Kit is now marked all rights reserved. `LICENSE` says it isn't open source and that using,
  copying, changing, or sharing it takes the copyright holder's written permission; the README says
  so up front, and GOVERNANCE.md separates the Owner role (releases and changes) from ownership of
  the code. The personal-details check skips the copyright line in `LICENSE`, which names the
  copyright holder on purpose.
- `kit-drawio` uses the team style file (`memory/context/drawio-styles.json`) by default when present.
- `kit-sysprofile` fills the optional FEAF reference models row from catalog tags or the curator's
  system page.
- Red team and threat modeler, after their first real run: retrospective mode for published
  documents, figures read as images, shared high-availability and IA-drift checks, a rule for missing
  RTO and RPO, a follow-on designs section; controls named only by reference count as "inherited,
  unverified", fix owners for other teams' systems, and a conflicts-and-defects section.
- The PostgreSQL SQL transport (psycopg) is now tested against PostgreSQL 17.0: `kit-team db-init` and
  the live test passed. SQL Server stays untested.
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
- Windows: `doctor.py` stopped with an error at the scheduled-jobs check, because Windows has no
  `os.getuid`. It now checks Kit's tasks in Task Scheduler (`\Kit\`) and warns on a disabled one.
- Windows: `doctor.py` warned that the Kit folder was open to everyone (0o777), a file mode Windows
  doesn't keep. It now reads the folder's access list with icacls and warns on another account's entry
  or an inherited one, with the command that fixes it.
- A clean install now makes `memory/personal/`, with its `INDEX.md` and `decisions/`, so `doctor.py`
  no longer fails on a missing personal index right after the install; on an older install it's a
  warning that says to run the installer again.
- JSON saved with a UTF-8 byte-order mark (Windows PowerShell 5.1's `-Encoding UTF8` writes one) was
  refused. Everywhere Kit reads JSON now accepts one, and Kit's own writers say utf-8 explicitly.
- Windows: Kit's command shims, its scheduled runs (`run.ps1`, `preflight.ps1`, and the backup and sync
  tasks), and the installer run Python in UTF-8 mode (`PYTHONUTF8=1`). Before Python 3.15, Python on
  Windows reads and writes text in the ANSI code page, so a curly quote or an emoji in a note could stop
  a tool (`todo` couldn't read a QUEUE.md with a closing curly quote in it). After updating, run
  `register-tasks.ps1` again so the backup and sync tasks get the setting too.
- `kit-library`, and the tools that use it, load on Windows: the index lock uses msvcrt where there's
  no fcntl. `kit_claude` finds `claude` through the PATH (`claude.cmd` too) and looks in the Keychain
  only on macOS.
- `kit-touch` and `kit-feedback`: a date without a year ("26-Oct", "10/26") works again. Python 3.15 no
  longer reads a day and month on their own, so the year is added before the date is read.
- Texting Kit: questions really are read-only now. The question run, and the small parse and draft
  runs, start with `--setting-sources project,local`, so the allow rules in `~/.claude/settings.json`
  no longer add to their tool lists: Bash is limited to `kit-library search` and `show`, and commands
  such as `kit-feedback`, `kit-visits`, `kit-touch`, and `kitmail` are refused. Letters, receipts, the
  trading journal, and personal notes are closed to text questions too.
- Texting Kit: in `date NAME MM-DD birthday card`, the action word (card, call, gift, note) was read
  as part of what the date is, because a later setting reused its name.
- Windows installer: Kit 1.4.0 left every file in `%USERPROFILE%\Claude\Agents\kit` with no access
  entries, so Kit couldn't read its own files and stopped loading, while the installer reported
  success. It applied the kit home's `(OI)(CI)` grant to each file with `/T`, where it can't apply.
  Now the kit home alone gets one entry, full control for your account (by SID), inherited by
  everything inside, and the files are reset to inherit it. Each `icacls` result is checked, a rerun
  first repairs an install with this problem, and the installer opens every file before it reports
  success. A real Windows install, reinstall, and repair now run in CI under Windows PowerShell 5.1
  and PowerShell 7. To repair an existing install by hand:
  `icacls "$env:USERPROFILE\Claude\Agents\kit\*" /reset /T /C /Q`.
- Owner name on Windows: the templates used the login (a name like `arivera`) where the owner's first
  name belongs. Kit now uses `KIT_OWNER`, then the account's display name (`Rivera, Alex` gives
  `Alex`), then asks when someone's at the keyboard; never the login. The templates also say "PC" on
  Windows instead of "Mac" (new placeholder `{{COMPUTER}}`).
- `kit-coverage` read the CRI Profile row as NIST CSF; its CSF pattern is anchored now.
- kit-reliability now reads Windows (run.ps1) log timestamps; the to-do sync records clean runs in
  `sync.ok`, so a quiet working sync isn't mistaken for a stalled one.
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

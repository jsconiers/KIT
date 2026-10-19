# Changelog

What changed in each Kit release. The installed version is in
`~/Claude/Agents/kit/.install/VERSION.json` (`kit-version` prints it). After an update, the next
morning brief summarizes the new entries once. Format: [Keep a Changelog](https://keepachangelog.com),
versions follow [semantic versioning](https://semver.org).

## [Unreleased]

### Added
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
  commands, audit log, cost ledger). No connectors, subagents, hooks, or skills.
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

### Fixed
- Weekly review timed out (20-minute limit) and overlapped the morning brief. Runs now have their
  own time limits (weekly 50 minutes), wait for each other through a lock, report a timeout
  plainly, and the weekly review moves to Monday 06:30.
- The health check credited a failure notice to the wrong run when runs overlapped.

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

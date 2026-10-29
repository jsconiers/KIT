# Kit

Kit is an AI personal assistant that lives in Claude Code, with a staff of specialist subagents. It's
one agent working for one person. It keeps your to-do list and its own, a one-page status, notes on your work,
lessons from its own mistakes, and your preferences, and it directs a staff of 33 specialist
agents (Claude Code subagents) for you.

**Why Kit?** Kit is named after KITT, the AI car in the 1980s TV series *Knight Rider* that helped its
driver, Michael Knight, figure things out and save the day. Like KITT, Kit advises and assists while
the person drives and decides. (Knight Rider and KITT are trademarks of their owners; Kit isn't
affiliated with them.)

- **New here?** Read this page, then [INSTALL.md](INSTALL.md) and [ONBOARDING.md](ONBOARDING.md).
- **Changing Kit?** Read [DESIGN.md](DESIGN.md) and [GOVERNANCE.md](GOVERNANCE.md).
- **Using Kit?** It isn't open source. All rights are reserved, and installing or using Kit takes
  the copyright holder's written permission. See [LICENSE](LICENSE).

## What Kit does

- **Keeps your commitments.** A running queue (`QUEUE.md`) for you, for Kit, and for what's
  waiting on others, with sprints, stale-item checks, and duplicate detection.
- **Briefs you.** A morning brief on weekdays, a weekly review on Mondays, a daily work list for
  your approval, and an optional end-of-day wrap-up, delivered as a desktop notification or an
  Outlook draft (never sent).
- **Runs your staff.** Routes work to the right agent with a brief, checks what comes back, and
  reports to you.
- **Helps with architecture work.** Matches a new demand to published reference architectures,
  profiles a system from the library's records, sizes a workload, and compares diagram versions.
  Before peer review, the red team attacks a design and the threat modeler runs STRIDE per data flow;
  `kit-trace` traces each requirement to the design, tests, and change.
- **Maps designs to frameworks.** A framework profile says which frameworks apply (NIST CSF 2.0,
  PCI DSS, CIS, CISA Zero Trust and Secure by Design, SOX ITGC); the compliance mapper maps only
  those, with a CSF 2.0 coverage check (`kit-csf`), a Zero Trust maturity rating, Secure by Design
  review questions, and a hardening-baseline check.
- **Watches the connections, runs, cost, and rules.** A connector that fails two mornings running, a
  scheduled run that fails twice or goes overdue, or a cost projection over the warning level becomes
  a work item, a dashboard banner, and a brief line, cleared on recovery (`kit-alerts`). Kit also
  flags agents that drifted from the shipped version, published documents missing from the library
  indexes, and queue items waiting more than a week (with a follow-up draft, never sent). An optional monthly regulatory watch has the researcher brief you
  on public changes to the regimes you list.
- **Turns meetings and designs into records.** Architectural decisions in minutes become proposed
  ADR drafts (`kit-decisions`); a stakeholder map by role comes from the library
  (`kit-stakeholders`); any IA or GDS gets a cited one-page executive summary (`kit-onepager`);
  diagrams are linted against your standard (`kit-diaglint`); a GDS yields DoDAF-style viewpoints
  (`kit-viewpoints`); `kit-coverage` shows framework coverage across designs. TOGAF-style deliverable
  templates are there on request.
- **Supports audits and compliance.** A policy exception register with expiry alerts, evidence packs
  organised by control, an audit request tracker, and a quarterly least-privilege review of the
  agents' tools (`kit-audit privileges`). NIST SP 800-53 Rev 5 and MITRE ATT&CK ship as data
  (`kit-controls`), and threat models and red-team notes cite them.
- **Watches your estate.** `kit-lifecycle` flags operating systems and products past or near end of
  support, including those only covered by paid extended support, from a CMDB export.
- **Prepares your day.** Meeting prep packs, inbox triage suggestions, mail still awaiting a reply,
  1:1 prep, an accomplishments log, and calendar holds as drafts you open and save.
- **Asks before acting.** Anything that sends, deletes, installs, commits, pushes, changes
  settings, touches money, or commits you to someone waits for your yes.
- **Stays private.** Everything lives in one folder only your account can read. Personal notes
  stay separate from work notes.

## Kit's staff

Thirty-three agents in five groups. Each reads its own setup file in `memory/context/`, and
`memory/context/agents.md` describes them all.

| Group | Agents |
|---|---|
| Knowledge and documents | researcher, librarian, curator, precedent finder, onboarding guide, handoff |
| Writing and review | IA writer, GDS writer, reviewer, red team, threat modeler, standards checker, risk and compliance mapper, diagrammer, deck builder |
| Delivery and planning | intake triager, dependency mapper, implementation planner, change board prep, cost estimator, PMO estimator, decision recorder, status reporter, meeting scribe |
| Outside systems and oversight | gateway, demand tracker, auditor, scheduler, letters desk |
| Exploration | POC lead, lab planner, training lead, future tech planner |

Work goes through Kit, apart from a few direct pairs listed in `agents.md`. The gateway is the
agent meant to reach outside systems; the connector guard keeps its calls read-only and logs them.

## Daily rhythm

| When | Run | What you get |
|---|---|---|
| Weekdays 07:45 | Morning brief | A connector health line, to-dos, calendar, mail needing you, health and audit issues, queue hygiene |
| Mon to Thu 09:00 | Work list | What Kit can do on its own today; you approve it in a session |
| Monday 06:30 | Weekly review | The week, the queue, audit, what changed on your demands (optional refresh), horizon scan, watch, sprint review, cost, quality, retrospective (first Monday) |
| Weekdays 17:30 | End-of-day wrap-up (optional) | What moved, what's due tomorrow, commitments not yet in the queue |
| Weekdays, every 30 minutes (optional) | Meeting prep | A prep pack per upcoming meeting (a plain script; no Claude run) |
| Daily 12:30 | Backup | An encrypted, checked archive of Kit's folder and history, in the folder you choose |
| Every 15 minutes | To-do sync | Your queue mirrored to Outlook Tasks or Apple Reminders, and the "Kit Inbox" list pulled in |

Scheduled runs use launchd on macOS and Task Scheduler on Windows. See INSTALL.md. If the
budget's stop level is reached, or the morning run fails or times out, the brief still arrives:
`kit-degraded` writes it from Kit's files with no model call, marked as degraded (`DEGRADED_MODE` in
the config). A run that fails in a way that looks transient (overload, rate limit, network, an API 5xx
or 529) is retried once after two minutes (`RETRY_ON`, `RETRY_DELAY`); time-outs and refusals are never
retried. `kit-reliability` tracks every run's outcome, and the health check and the dashboard's
Reliability panel flag a run type that keeps failing, slows down, or hasn't succeeded lately.

## Command-line tools

The installer links these into `~/.local/bin` (all in `shared/bin/`):

**Your queue and day**

| Tool | What it does |
|---|---|
| `todo` | Your to-do list from the shell; shares `QUEUE.md`. Also sprints (`todo sprint ...`). |
| `kit-queue` | Queue hygiene: stale items, likely duplicates, the trend; applies verdicts you approve |
| `kit-meetprep` | A prep pack per upcoming meeting: roles, related items, documents, what to decide |
| `kit-triage` | Suggests reply, decide, delegate, read later, or ignore per inbox message; never acts |
| `kit-awaiting` | Sent mail that asked for something and got no reply after N days, with draft nudges (needs a mail tool with sent-items commands) |
| `kit-commitments` | Proposes to-dos from promises in your sent mail or minutes; you confirm |
| `kit-holds` | Draft calendar holds as .ics files you open and save; Kit never writes to the calendar |
| `kit-oneonone` | One-page prep for your 1:1 with your manager (by role); `--done` records the date |
| `kit-wins` | Accomplishments log for reviews and 1:1s: collect, this month, report by theme |
| `kit-feedback` | A private log of feedback on the people you lead (praise, coaching, goals): 1:1 prep, review notes, and who's had no note lately; never shared or texted |
| `kit-meetload` | Meeting load audit: hours and share of working hours, recurring meetings' weekly cost, back-to-back runs, focus time left, after-hours meetings, double bookings, suggestions; `--holds` drafts focus time; reads the calendar, a JSON file, or an .ics export |
| `kit-dates` | Important dates (birthdays, anniversaries, work anniversaries), with a to-do and a drafted card or note when one comes up |
| `kit-touch` | Keep in touch: who you haven't talked to in a while, by your own rhythm for each; calls and meals on the calendar count |
| `kit-library` | Catalogs folders you choose (collections): tags, full-text and scripture search, scanned PDFs read on the Mac; delivers finished work to an output folder, mirrored to a synced folder if you like |
| `kit-textback` | macOS: text Kit from your phone ("kit today", "kit find ..."); changes come back with a code to confirm |
| `kit-letter` | A Word letter from plain text: `build` leaves room for a pen signature; `sign` adds your saved signature, and Claude Code asks you each time |
| `kit-settings` | How briefs reach you and which app your to-dos sync with, work and personal |

**Architecture work**

| Tool | What it does |
|---|---|
| `kit-refarch` | Suggests which published reference architectures fit a demand, ranked, with why |
| `kit-precedent` | Ranked search of the library's indexes and registers for precedent |
| `kit-sysprofile` | One-page profile of a system from the library's records, every line cited |
| `kit-trace` | Requirement-to-evidence matrix: IA requirement to GDS section, test case, change step, and POC verdict, with gaps flagged |
| `kit-csf` | Coverage of a NIST CSF 2.0 mapping per Function, with gaps, blanks, and ID checks; `--portfolio` across projects |
| `kit-sizing` | Rough-order compute, storage, and network sizing, every assumption shown |
| `kit-diagram-diff` | What changed between two versions of a draw.io or Visio diagram |
| `kit-diaglint` | Checks draw.io and Visio diagrams against your team's diagramming standard (a JSON rules file): palette, fonts, title block, legend, line types, connectors, shapes, view labels |
| `kit-onepager` | One-page executive summary of an IA or GDS (Markdown, .docx, or PDF), every line cited, "not stated" where the document is silent; Markdown, JSON, or Word |
| `kit-decisions` | Drafts proposed ADRs from architectural decisions in meeting minutes, with the classifying rule shown; never accepts anything |
| `kit-viewpoints` | DoDAF-style viewpoint drafts (OV-1, SV-1, SV-4, DIV-2) from a GDS, every element cited, with a draw.io file per view in the team style |
| `kit-coverage` | Framework coverage per design and across the portfolio (CSF 2.0, Zero Trust, Secure by Design, standards, threat models, red team, waivers), filtered by your framework profile; HTML and JSON |
| `kit-controls` | Look up NIST SP 800-53 Rev 5 controls and MITRE ATT&CK techniques and mitigations, search both, and suggest techniques and controls for a threat model (marked "suggested"); offline |
| `kit-exceptions` | Policy exception register: list, add, and what's expired, expiring, or overdue for review (with a morning alert) |
| `kit-pbc` | Audit request (PBC) tracker: track auditors' requests, gather an evidence pack per request, draft responses (never sent) |
| `kit-questions` | Open-question tracker per project: extract questions from drafts and notes, draft messages by owner (never sent), record answers, show where each answer goes |
| `kit-templatecheck` | Template drift check: sections missing, renamed, reordered, or added, the template version, and leftover placeholder text |
| `doctor.py --readiness` | Agent readiness (no known limit, limits, blocked) and why, by cause; the source for readiness figures in the docs |
| `kit-alerts` | Open alerts (runs, cost, connectors, connector-guard integrity, agent drift, library indexes, items waiting too long, policy exceptions); `check` recomputes; `drift --diff <agent>` shows a drifted agent |
| `kit-stakeholders` | Stakeholder map by role (never names) from the demand register, minutes, status reports, intake notes, and RACI tables |
| `kit-labcheck` | Flags production or confidential data in lab requests and runbooks; warns when a runbook names no hardening baseline |
| `kit-lifecycle` | End-of-support early warning from an inventory and sourced dates: past, extended (inside paid extended support), urgent, warning; a data-quality section; `--import` turns a CMDB export into the inventory |
| `kit-roadmap` | Drafts a 1-to-3-year technology roadmap |
| `kit-project` | Creates a project's folder skeleton by type (dry run unless `--yes`) |
| `kit-quality` | Recurring review findings become proposed lessons and template changes |

**Team and sharing**

| Tool | What it does |
|---|---|
| `kit-team` | Sharing between Kits: sync, list, search, inbox, send (with your yes), ack, purge, `load` (team demand load), `experts` (who has done X) |
| `kit-plugin` | Packages agents, templates, shared lessons, and skills as a Claude Code plugin marketplace; checks it before merging; never publishes |

**Models and agents**

| Tool | What it does |
|---|---|
| `kit-models` | Which model each agent and run uses, from `models.json`; `apply` writes them |
| `kit-delegate` | Sends one bounded task to a model profile; also an MCP server (`--mcp`) |
| `kit-run` | Experimental: runs one of Kit's agents outside Claude Code |
| `kit-evals` | Agent checks: static (free) and live (`--live --yes`, costs money) |

**Safety and operations**

| Tool | What it does |
|---|---|
| `kit-pause` | Kill switch: stops scheduled runs and connector calls until `kit-pause resume` |
| `kit-connect` | Connector check: guard, credential variables by name, Claude Code health |
| `kit-backup` | Checked archive of Kit's folder and history to a folder you choose (local or shared), encrypted on request; `verify`, `restore` |
| `kit-audit-export` | A dated evidence pack of Kit's controls for a compliance or security review; `--controls` organises it by control for an audit request, with gaps listed |
| `kit-retention` | Retention rules with legal holds; reports, and only moves files with `--yes` |
| `kit-outlook` | Checks Outlook answers before a run, retrying; never starts it |
| `kit-degraded` | The morning brief from Kit's files with no model call (budget stop, failed or timed-out run) |
| `kit-reliability` | How reliably the scheduled runs work: success rate, duration, cost, and alerts, by run type |
| `kit-cost` | What scheduled runs cost, by run and model, against an optional monthly budget |
| `kit-expiry` | Everything that expires (tokens, logins, domains, certificates), soonest first, from `expiry.json`; the health check warns before each is due |
| `kit-metrics` | One-page metrics view: spend, runs, queue trend, work lists, sprints, health |
| `kit-update` | Shows what's new on GitHub; `--apply` moves your clone and reinstalls |
| `kit-version` | Installed version and commit, and whether GitHub is ahead |

Also in `shared/bin/`, called by Kit or the scheduled runs rather than by hand:
`connector-guard` (the read-only hook and audit log, with each result's size and stated total), `kit-audit` (daily and weekly audit
checks), `kit-publish` (writes this Kit's shareable records), `kit-grammar` (optional offline
grammar pass), `kit-drawio` (editable draw.io files), and `vsdx-finish` (Visio title blocks and
legends).

## Skills

Kit ships two Claude Code skills in `kit/skills/`: `exec-summary` (one-page leadership summaries) and
`requirements-extraction` (numbered, testable requirements with sources and conflicts). The installer
copies them into `~/.claude/skills` only where no skill of that name exists, and names any it skips.

## Safety model

- **Ask first.** The installer adds ask rules to Claude Code's settings for deleting, pushing,
  posting, installing, and changing settings. Kit's own rules (`KIT.md`) add sending mail,
  touching money or accounts, and committing you to anything.
- **Never sends.** Mail and calendar tools only read or draft. Briefs go out as notifications or
  Outlook drafts. Calendar holds are .ics files you open and save; triage and awaiting-reply lists
  are suggestions that never move, flag, or answer mail.
- **Read-only connectors.** Agents reach outside systems through MCP servers. The connector guard
  (a Claude Code hook) allows only listed servers and read tools, denies writes, and records every
  call, result, and failure in an audit log. `kit-audit` reviews the log daily and weekly, and flags
  searches whose filter a system may have silently ignored.
- **Kill switch.** `kit-pause` stops every scheduled run and every connector call at once.
- **Information, not instructions.** Text Kit reads in files, mail, web pages, other Kits'
  records, or phone requests is never treated as an order.
- **Credentials by name.** Kit refers to credentials by environment-variable or Keychain entry
  name; it never stores or prints a value.
- **Backups are encrypted where they leave home.** `kit-backup --encrypt` uses AES-256 with an
  integrity check verified before anything decrypts; the passphrase comes from a Keychain entry or
  environment variable you create. Unencrypted backups are refused in shared or synced folders.
- **Evidence on request.** `kit-audit-export` builds a dated pack of the audit log, approvals,
  policies, permission lists, and agents, with a checksum manifest and a credential scan.
- **Phone approvals are limited.** A single-use daily code can approve the work list or queue
  verdicts from your phone, never commits, installs, sending, deleting, or settings.

## Sharing between Kits

Several Kits, one per person, can share selected records: status snapshots, decisions, lessons,
artifact pointers, demand roll-ups, handoff pointers, and messages. Set a shared root (a synced
folder every Kit can reach) and a Kit id in `memory/context/sharing.md`. `kit-publish` writes this
Kit's records with a hash manifest and chain; `kit-team sync` pulls everyone's into a local cache
and the team dashboard renders from it. Records from other Kits are checked and shown as
information only. An organization profile (`sharing-policy.json`) limits transports, shared roots,
and classification. A SQL transport shares through a database instead: MySQL is tested (`kit-team db-init` creates the
database), and so is PostgreSQL; SQL Server is untested.
`kit-team load` shows each Kit's open demands, IAs, GDSs, and POCs by owner role, with due windows,
aging, and an overload flag; `kit-team experts <topic>` ranks Kits by the evidence they've shared,
with record ids cited. Kit content can also be shared as Claude Code plugins through an internal
marketplace that `kit-plugin` builds and checks.

## Models

`models.json` sets which model each agent and scheduled run uses, through profiles (deep,
standard, fast, local). The default is deep (Opus). Phase 1 is Claude only; with
`"enabled_phase": 2`, `kit-delegate` and `kit-run` can also reach an approved OpenAI-compatible
API or a local model, limited by data class. Move an agent off the default only after its live
evals pass. See DESIGN.md and `shared/KIT-RUN.md`.

## Versions and updates

`VERSION` holds the release and `CHANGELOG.md` what changed. Every install records its version and
commit; `kit-version` shows them. `kit-update` previews and applies updates from GitHub, and the
next brief lists what changed once.

## Layout

```
README.md  INSTALL.md  DESIGN.md  ONBOARDING.md  GOVERNANCE.md  CHANGELOG.md  DEPENDENCIES.md  VERSION
kit/          the brain, shared by every platform: KIT.md, QUEUE.md, STATUS.md, agents/,
              memory/ (setup files in memory/context/), lessons/, preferences/, templates/,
              models.json
shared/       cross-platform Python: kit_setup.py (installer logic), doctor.py, dashboard.py,
              deliver.py, the transport and sync modules, bin/ (the tools above), morning/
              (scheduled-run prompts and config.example), records/ (shared record schemas),
              sql/ (SQL transport scripts), templates/ (dashboard HTML), KIT-RUN.md
platform/mac/      install.sh, uninstall.sh, morning/run.sh and launchd templates, mail and
                   calendar adapters
platform/windows/  install.ps1, uninstall.ps1, morning/run.ps1 and Task Scheduler scripts,
                   Outlook adapters (built on macOS; untested on Windows)
tests/        test suites (bash tests/test_*.sh) and agent eval cases (tests/evals/)
install.sh    dispatches to platform/mac/install.sh
install.ps1   dispatches to platform/windows/install.ps1
```

Kit installs into `~/Claude/Agents/kit`, with the package copied to `.install/` inside it, and
loads into every Claude Code session through one import line in `~/.claude/CLAUDE.md`.

## Quick start (macOS)

```bash
git clone https://github.com/<you>/KIT.git
cd KIT
KIT_OWNER=Alex bash install.sh
```

Then start `claude`, run `/context` to confirm `KIT.md` loaded, and say "Kit, introduce
yourself." INSTALL.md covers Windows, scheduled runs, connectors, and the rest.

## Where to go next

| Document | For |
|---|---|
| [INSTALL.md](INSTALL.md) | Installing, configuring, updating, troubleshooting |
| [ONBOARDING.md](ONBOARDING.md) | Your first day and first week with Kit |
| [DESIGN.md](DESIGN.md) | How Kit is built and how to extend it |
| [GOVERNANCE.md](GOVERNANCE.md) | Roles and how changes are made (draft) |
| [CHANGELOG.md](CHANGELOG.md) | What each release changed |
| [DEPENDENCIES.md](DEPENDENCIES.md) | What each agent and tool needs, and what happens without it |
| [shared/KIT-RUN.md](shared/KIT-RUN.md) | Running agents outside Claude Code, and its limits |
| `shared/records/README.md` | Shared record formats and trust rules |
| `shared/sql/README.md` | The SQL transport (MySQL and PostgreSQL tested; SQL Server untested) |

## Privacy

Kit's notes stay on your computer in a folder only you can read (`chmod 700` on macOS, owner-only
NTFS permissions on Windows). Personal notes live in `memory/personal/` and don't load on their
own, and `protect_folder.py` keeps them out of work folders. Your settings stay in
`.install/shared/morning/config`, which git ignores.

## License

Copyright in Kit is held by its author, and all rights are reserved. Kit isn't open source: no
license is granted to use, copy, change, or share it, and installing or using it takes the
copyright holder's written permission. [LICENSE](LICENSE) has the full terms. Third-party data
files keep their own licenses; see [DEPENDENCIES.md](DEPENDENCIES.md).

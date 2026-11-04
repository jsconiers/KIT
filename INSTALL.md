# Installing Kit

This guide takes you from nothing to a working Kit: install, first checks, setup, scheduled runs,
connectors, and day-two tasks (updating, backups, pausing, uninstalling, troubleshooting).
`~` means your home folder. Commands assume `~/.local/bin` is on your `PATH`; if it isn't, run a
tool by its full path, `python3 ~/Claude/Agents/kit/.install/shared/bin/<tool>`.

macOS is the supported platform. On Windows, the installer (install, reinstall, and repair) and the
suites the checks list run in CI on GitHub's Windows runners, under Windows PowerShell 5.1 and
PowerShell 7. The Outlook COM adapters and the Task Scheduler tasks haven't run on a real Windows machine
yet: treat those steps as a first trial and report what breaks.

## 1. Prerequisites

| Need | Why | Check |
|---|---|---|
| Claude Code | Kit and its staff run inside it | `claude --version` |
| Python 3.8 or newer | The installer and every tool (standard library only) | `python3 --version` |
| git | Kit's private local history, updates | `git --version` |

Optional components, each skipped cleanly when missing (details in DEPENDENCIES.md):

- **Classic Outlook** (macOS or Windows): calendar and mail in the brief, Outlook draft delivery,
  Outlook Tasks sync, phone requests through "Kit Inbox".
- **draw.io Desktop**: diagram exports; **LanguageTool with Java 17+**: offline grammar checks.
- **MCP servers** for the outside systems you want Kit to read (issue tracker, wiki, service
  management).
- **A shared folder** every teammate's Kit can reach, for sharing between Kits.
- **PowerShell 7** only if you want to run the Windows runner's tests on a Mac.

If your organization runs a software catalogue, request missing components there first.

## 2. Get the package

```bash
git clone https://github.com/<you>/KIT.git
cd KIT
```

or download and unzip a release into a folder named `kit-agent` in your Downloads folder (the
installer then offers to delete the download afterward).

A release zip is made from a clone with
`git archive --format=zip --prefix=KIT-<version>/ -o KIT-<version>-<sha>.zip HEAD`: one top-level
folder, with the commit written in the zip comment. Publish its SHA-256 with it (`shasum -a 256` on
macOS, `Get-FileHash` on Windows) so whoever installs it can check it. Once Kit is installed, later
zips go through `kit-update --zip` (section 11, "Updating from a zip"), not by hand.

## 3. Run the installer

**macOS**

```bash
KIT_OWNER=Alex bash install.sh
```

**Windows** (installer tested in CI; see above)

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

`KIT_OWNER` is the name Kit calls you; without it Kit uses your account's first name. The
installer is safe to rerun: it never overwrites Kit's memory, queue, status, lessons, or
preferences.

### What the installer changes

| Where | What |
|---|---|
| `~/Claude/Agents/kit/` | Created, owner-only. Starter files are copied in only if missing. |
| `~/Claude/Agents/kit/.install/` | A full copy of the package (`kit/`, `shared/`, `platform/`, the top-level docs, `tests/evals/`), so the download can be deleted |
| `~/.claude/CLAUDE.md` | One import line, `@~/Claude/Agents/kit/KIT.md`, with a comment marking when it was added |
| `~/.claude/settings.json` | Allow rules so Kit can read its folder and keep its notes; ask rules for editing Kit's rules and Claude Code's own settings, and for `rm`, `sudo`, `git push`, `git reset --hard`, `gh` posts, package installs, `launchctl`, `defaults write`, and `osascript`; Kit's folder as an additional directory |
| `~/.local/bin/` (macOS) | Links to the everyday tools |
| `~/.claude/skills/` | Kit's skills, copied only where no skill of that name exists |
| `~/.claude/agents/` | Kit's staff. Agents you haven't edited are refreshed to the new version; ones you edited are kept and named. What Kit last wrote is recorded in `.install/agents-installed.json`; `python3 shared/kit_setup.py agents` does this step alone |
| Windows | `.cmd` shims for the same tools, and owner-only NTFS permissions on Kit's folder |

Both Claude Code files are backed up to `.install/backups/` first, and the installer records exactly
what it added in `.install/manifest.json` so the uninstaller can remove just that. It also records
the version and commit in `.install/VERSION.json`.

The installer then runs `kit-settings setup`, which asks (only when someone is at the keyboard) how
briefs should reach you and which app your to-dos sync with.

Last, it runs the connector guard's hooks in `~/.claude/agents/` the way Claude Code does
(`kit_setup.py guardcheck`): each guarded agent must block a write and allow a read. Claude Code lets a
call through when a hook can't start, so if the check fails the installer stops with the reason
(see Troubleshooting).

If your Claude Code settings run with permission prompts bypassed, the installer warns you: Kit's
ask rules only work with prompts on.

### The agents in Claude Code

The installer puts Kit's staff in `~/Claude/Agents/kit/agents/` and copies them into
`~/.claude/agents/`, where Claude Code finds them, keeping any you edited. To copy them again by hand
(for example after `kit-models apply`):

```bash
python3 ~/Claude/Agents/kit/.install/shared/doctor.py --fix-agents
```

## 4. First checks

```bash
claude                      # then run /context and confirm KIT.md is listed under Memory files
python3 ~/Claude/Agents/kit/.install/shared/doctor.py          # full health check
python3 ~/Claude/Agents/kit/.install/shared/doctor.py --brief  # problems only
kit-version                 # installed version and commit
kit-connect test            # connectors: guard, credentials by name, Claude Code health
kit-evals                   # static agent checks (free)
kit-models                  # which model each agent and run uses
kit-reliability             # how the scheduled runs have been doing (after a few days)
```

Then say "Kit, introduce yourself."

## 5. Fill in the setup files

Each agent reads a setup file in `~/Claude/Agents/kit/memory/context/` before every job. Fields
marked "not set" limit what the agent can do; the health check and the agents themselves say what's
missing. A path field (a folder or file) is read only when its value starts with the backticked path,
for example `- **Exception register:** \`compliance/waivers.md\`. Kept by ...`; a path named later in
the line reads as not set, and the health check's "Setup paths" warning names the field and file.
Fill in what applies to you, in roughly this order:

| File | Used by | What to fill in |
|---|---|---|
| `library.md` | librarian and most agents | The library root folder, published document libraries, read-only sources |
| `writing.md` | IA and GDS writers, reviewer, planner, deck builder, `kit-trace` | Templates, examples, style skills, output format, quality loop thresholds, traceability matrix template |
| `calendar.md` | scheduler, `kit-holds`, `kit-meetprep` | Calendar command, working hours and time zone (for example `09:00-17:00 America/New_York`; holds assume 09:00 to 17:00 until set), habits |
| `meetings.md` | meeting scribe, `kit-awaiting` | Meeting inbox, your notes folders, project managers, mail commands, vendor template, "Awaiting reply after" (days) |
| `connectors.md` | gateway and its callers | Which outside systems, which records to read first |
| `demands.md` | demand tracker | Where demands and tickets live, the register |
| `intake.md` | intake triager | Intake checklist, when an impact assessment is needed, project naming |
| `knowledge.md` | curator, handoff, `kit-sysprofile` | Knowledge base location and first topics, where system profiles go |
| `standards.md` | standards checker, `kit-refarch` | Engineering standards, reference architectures (the index `kit-refarch` reads, for example `published/<library>-index.md`), security baselines, DR tiers, waivers |
| `compliance.md` | risk and compliance mapper | Control frameworks, policies, data classes, sign-off roles, risk rating, and a framework profile: which frameworks apply (NIST CSF 2.0, PCI DSS, CIS, CISA Zero Trust and Secure by Design, SOX ITGC, others), to what, and the owner role; the mapper maps only against those, and fills the NIST CSF 2.0 mapping (`csf-mapping-template.md`, `kit-csf`) when CSF 2.0 applies; optional Regulatory watch regimes and folder |
| `costs.md` | cost estimator | Rate cards, labor rates, currency, contingency, sizing basis (`kit-sizing`) |
| `estimating.md` | PMO estimator | Past project data, phase model, roles |
| `changeboard.md` | change board prep | Template, risk scoring, checklist, lead times, cadence |
| `decisions.md` | decision recorder | ADR template and folder, who can accept a decision |
| `diagrams.md` | diagrammer, reviewer, `kit-diaglint` | Diagramming standard, stencils, formats, and the optional Lint rules file (start from `templates/diagram-lint-rules.example.json`) |
| `status.md` | status reporter | Report format, window, audiences, stakeholder maps, exploration section |
| `onboarding.md` | onboarding guide | Core reading by role, conventions, Kit training path |
| `poc.md` | POC lead | Charter approvers and verdict deciders, NDA owner, data rule |
| `labs.md` | lab planner | Environments, lab approver, data-check terms, idle threshold |
| `training.md` | training lead | Who plans are for, team roles, learning platform, templates |
| `future-tech.md` | future tech planner | Radar audiences, voting rule, lifecycle data, roadmap approvers, watch list |
| `precedent.md` | precedent finder, `kit-precedent` | Sources, what counts as current, ranking |
| `project-types.md` | `kit-project`, all agents | Folder layout and stages per project type |
| `oneonone.md` | `kit-oneonone` | Manager role (not a name), cadence, day, last 1:1, look-back |
| `triage.md` | `kit-triage` | Your name or address (to tell direct mail from copies), priority senders, delegated topics |
| `expertise.md` | `kit-publish`, `kit-team experts` | Optional self-declared topics (Topic, Level, Evidence); shared only if `expertise` is in Publish |
| `audit.md` | auditor, `kit-audit`, `kit-audit-export` | Audit folder, reviewers, working hours, thresholds (including the filter check: `filter_total_min`, `filter_limit_factor`, `filter_same_min`, `filter_same_pct`) |
| `retention.md` + `retention.json` | `kit-retention` | Records rules from your policy (default: keep everything) |
| `sharing.md` + `sharing-policy.json` (+ `sharing-db.json` for SQL) | `kit-publish`, `kit-team` | Kit id, role, what to publish, transport, shared root, overload threshold (default 8), organization limits |
| `connector-guard.json` | connector guard, `kit-connect` | Allowed servers and tools, denied tools, audit folder, optional probe tools and credential variable names |
| `agents.md` | Kit | The staff roster; edit only to add an agent |
| `letters.md` | letters desk, `kit-letter` | Return address, letter style, the saved signature (a transparent PNG in `letters/signature/`), where incoming letters arrive; the log is `letters/log.md` |
| `ppmx-projects.json` | `kit-ppmx actions` | Which PPM Express project each library project is (written by `kit-ppmx actions map`) |

Two lists live in Kit's folder rather than in `memory/context/`: `expiry.json` (`kit-expiry`: tokens,
logins, domains, certificates, and renewals) and `library/collections.json` (`kit-library`: the folders
cataloged as collections, their tags, rules, and the output folder).

Kit also keeps `kit-setup.md` (how this install was set up) and `glossary.md` (your shorthand).

## 6. Scheduled runs

The runs are optional. On macOS each is a launchd job built from a template in
`.install/platform/mac/morning/`; replace `{{USER}}` and `{{HOME}}`, save it in
`~/Library/LaunchAgents/`, and load it:

```bash
cd ~/Claude/Agents/kit/.install/platform/mac/morning
for job in morning weekly worklist sync; do
  sed -e "s|{{USER}}|$USER|g" -e "s|{{HOME}}|$HOME|g" com.USER.kit.$job.plist.template \
    > ~/Library/LaunchAgents/com.$USER.kit.$job.plist
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.$USER.kit.$job.plist
done
```

| Template | When | Notes |
|---|---|---|
| `morning` | Weekdays 07:45 | The morning brief |
| `weekly` | Monday 06:30 | Finishes before the brief; 50-minute limit |
| `worklist` | Monday to Thursday 09:00 | Proposes the day's work for your approval |
| `sync` | Every 15 minutes | To-do sync with Outlook Tasks or Apple Reminders |
| `eod` | Monday to Thursday 17:30, Friday 15:30 | Optional end-of-day wrap: `kit-wrap`, no model call (`EOD="off"` skips it; `EOD_MODEL="on"` uses Claude instead) |
| `backup` | Daily 12:30 | `kit-backup` with the config's `BACKUP_*` settings (encrypted when `BACKUP_ENCRYPT` is on); runs on wake if the Mac was asleep; logs to `.install/logs/backup.log` |
| `meetprep` | Weekdays, every 30 minutes 07:00 to 18:00 | Optional meeting prep packs (`kit-meetprep`); a plain script, no Claude run; honours `kit-pause` |
| `preflight` | Daily 06:45 and 15:45 | Login check before the runs: Claude Code can run (one tiny call) and the connectors in `PREFLIGHT_CONNECTORS` are signed in; each problem reaches you once per lapse (`platform/mac/morning/preflight.sh`, log `preflight.log`) |
| `textback` | Always on (KeepAlive) | Optional texting Kit from your phone (`kit-textback watch`; `TEXTBACK="on"` turns it on). Build its reader first with `platform/mac/textback/build.sh` and give KitMessages.app Full Disk Access |
| `open` | Weekdays 09:45 | Optional, for a trading setup only |

**Library helpers (macOS).** `kit-library` reads PDFs through `kit-pdftext` and reaches protected
folders such as Documents through KitLibrary.app. Build both with `platform/mac/library/build.sh`
(`build.sh pdftext` rebuilds only the PDF reader), then allow KitLibrary in System Settings > Privacy &
Security > Files and Folders when macOS asks. No scheduled job for the library ships with Kit: run
`kit-library index` yourself, or schedule it with a launchd job of your own.

**Long-lived login (optional).** A token from `claude setup-token`, stored in the login Keychain as
`kit-claude-token`, keeps scheduled runs and the preflight check working when the interactive login
lapses. On Windows, set the user environment variable `CLAUDE_CODE_OAUTH_TOKEN` instead. Either way,
treat it like a password, and list its expiry in `expiry.json`.

To test a run without using up the day's run:

```bash
touch ~/Claude/Agents/kit/.install/platform/mac/morning/test-run
launchctl kickstart gui/$(id -u)/com.$USER.kit.morning
```

Logs are in `~/Claude/Agents/kit/.install/logs/` (one file per day), and every run's cost goes to
`cost.jsonl` there.

**Degraded mode.** With `DEGRADED_MODE="on"` (the default), the morning run still delivers a brief
when the budget's stop level is reached (no model call at all) or when the model run fails or times
out: `kit-degraded --reason "..."` writes it from Kit's files, marked "Degraded brief", following the
same privacy rules as the normal short texts. It never overwrites a brief the model run wrote.

**Auto-retry.** With `RETRY_ON="on"` (the default), a run whose model call fails in a way that looks
transient (overload, rate limit, too many requests, an API 429, 5xx, or 529, a network error) and that
wrote no text is retried once after `RETRY_DELAY` seconds (default 120). Time-outs, permission or policy
refusals, a budget stop, and a pause are never retried. The log shows `retrying <mode> after transient
failure (<why>)`, and the retry's cost is recorded. A second failure falls back to the degraded brief
(morning) or a failure notice.

**Windows:** `platform\windows\morning\register-tasks.ps1` registers the same runs in Task Scheduler
("Kit Morning Brief", "Kit Weekly Review", "Kit Work List", "Kit End of Day", "Kit Backup", "Kit
Reminders Sync", "Kit Login Check", the optional "Kit Meeting Prep" (weekdays every 30 minutes, 07:00 to
18:00; set `$RegisterMeetprep = $false` at the top of the script to skip it), and optional trading tasks);
`unregister-tasks.ps1` removes them. Registering and running the tasks hasn't been tried on a real
Windows machine yet. There's no text-back on Windows. See `platform/windows/morning/README.md`.

### Allowing tools in unattended runs

An unattended run can't ask you for approval, so it only uses tools allowed in the config
(`ALLOW_TOOLS`, plus `ALLOW_TOOLS_WEEKLY` for the weekly review), as Claude Code permission rules
separated by semicolons. `run.sh` adds a full-path twin for every `Bash(...~/...)` rule, because a
rule written with `~/` doesn't match a command spelled with the full home path.

## 7. Settings

`kit-settings` changes delivery and to-do sync; everything else is a key in
`~/Claude/Agents/kit/.install/shared/morning/config` (every key is documented in
`shared/morning/config.example`). Every key is described there; the ones most often changed are:

| Key | What it does |
|---|---|
| `RUN_TIMEOUT`, `RUN_TIMEOUT_WEEKLY`, `RUN_TIMEOUT_WORKLIST`, `RUN_LOCK_WAIT` | Time limits per run and how long a run waits for another to finish |
| `SKIP_DAYS`, `EOD`, `EOD_MODEL`, `WRAP_CALENDAR_CMD`, `WRAP_CALENDAR_SIDE` | Days with no scheduled runs; the optional end-of-day wrap, and where it reads the next working day's calendar |
| `ALLOW_TOOLS`, `ALLOW_TOOLS_WEEKLY`, `BLOCK_TOOLS` | Extra tools a run may or may not use |
| `COST_BUDGET_MONTHLY`, `COST_WARN_PCT`, `COST_STOP_PCT`, `COST_ESSENTIAL_MODES` | The monthly budget, its warn and stop levels, and the runs that continue at the stop level |
| `OUTLOOK_CHECK`, `OUTLOOK_RETRY_WAITS`, `CALENDAR_JSON_CMD` | Outlook health check, retry waits, and an alternative calendar command |
| `PHONE_APPROVALS`, `PUBLISH_PERSONAL`, `ONEDRIVE_PUBLISH_DIR`, `ONEDRIVE_ALLOWED_PREFIX`, `IMESSAGE_TO`, `IMESSAGE_TO_ALT` | Phone approvals and publishing routes |
| `RUN_WINDOW_WORKLIST`, `RUN_WINDOW_EOD`, `RUN_ALERTS_TIMEOUT` | Optional run-alert windows for the work list and wrap-up; the alert check's time limit |
| `OWNER_NAME` | Your name as Kit uses it in briefs and agents |
| `DELIVERY`, `DELIVERY_WORK`, `DELIVERY_PERSONAL`, `DELIVERY_EMAIL_TO` | How briefs are delivered (set with `kit-settings delivery` and `kit-settings email`) |
| `REMINDERS_BACKEND`, `TODOS_PERSONAL`, `TODOS_WORK` | Which app the to-do sync uses, overall and for personal and work items (set with `kit-settings todos`) |

The morning brief opens with a connector health line (each connector PASS or FAIL, from
`kit-connect test`, no model cost). It gives up after `CONNECTOR_CHECK_TIMEOUT` seconds (default
120) and never fails the run; `CONNECTOR_CHECK="off"` skips it.

**Weekly demand refresh** (off by default). Set `DEMAND_REFRESH="on"`, `DEMAND_SERVER` (the
connector name, also in connector-guard.json `allowed_servers`), and `DEMAND_REGISTER_DIR` (the
folder holding the demand tracker's REGISTER.md and LOG.md). `DEMAND_TOOLS` names the read tools
the Monday run may call (`mcp__<server>__<tool>`, separated by semicolons); empty uses that
server's `allow_tools`. Only tools the guard would allow, and whose names don't read as writes, are
used. `DEMAND_REFRESH_MAX` (25) caps the demands checked; `DEMAND_REFRESH_MIN_LEFT` (10) skips it
when the run is nearly out of time.

**Connector outages.** `CONNECTOR_FAIL_STREAK` (default 2) sets how many failed morning checks in a
row raise an outage: one work item in your queue and a dashboard banner, both cleared (the item gets a
"Recovered" line) when the connector passes again.

**Run and cost alerts** (on by default, `RUN_ALERTS`). `RUN_FAIL_STREAK` (2) failed runs in a row, or
no success within `RUN_WINDOW_MORNING` (2 weekdays), `RUN_WINDOW_WEEKLY` (8 days), `RUN_WINDOW_SYNC` (2
hours), or `RUN_WINDOW_BACKUP` (2 days), raise a run alert ("off" disables a window). Cost alerts fire
when the month's projection reaches `COST_ALERT_PROJECTION` of the budget (or `COST_WARN_PCT`), when
spend reaches the stop level, or, with no budget, when a day costs `COST_SPIKE_FACTOR` (3) times the
recent median. Check with `kit-alerts check --dry-run`; undo with `RUN_ALERTS="off"`.

**Monitors** (on by default): `MONITOR_DRIFT` (agents that differ from the shipped version or are out
of date in `~/.claude/agents`), `MONITOR_LIBRARY` (published documents missing from the library
indexes: `LIBRARY_UNINDEXED_MAX` 0, `LIBRARY_INDEX_MAX_DAYS` 30; an inferred cloud-sync stall:
`LIBRARY_SYNC_MAX_DAYS` 14, 0 turns it off), and `MONITOR_WAITING` (queue items waiting more than
`WAITING_MAX_DAYS`, 7, with follow-up drafts in `briefs/followups/`). `MONITOR_TIMEOUT` (20 s) limits
each. The library monitor needs `library.md`'s library root and published libraries. Set a key to
"off" to undo.

**Compliance setup** (optional, in `memory/context/compliance.md`): **Exception register** (default
`compliance/exception-register.md` in the library root), **Control map** (JSON or Markdown; start from
`templates/control-map.example.json`) for `kit-audit-export --controls`, and **PBC tracker** (default
`compliance/audit-requests/pbc-tracker.md`). `MONITOR_EXCEPTIONS` and `EXCEPTIONS_WARN_DAYS` (30) drive the
exception alert. `MONITOR_GUARD` checks that guarded agents keep their hooks, the guard's settings are
readable, its audit folder is writable, and calls have result records (`GUARD_NORESULT_HOURS`,
`GUARD_WINDOW_DAYS`). For the quarterly least-privilege review to run unattended, allow
`kit-audit privileges` in `ALLOW_TOOLS_WEEKLY`.

The installer copies Kit's skills (`kit/skills/`) into `~/.claude/skills`, never over a skill you
already have. `kit-templatecheck` finds templates through writing.md's **Templates** line in the form
`IA: <path>; GDS: <path>` (relative paths from the library root); until it's set, pass `--template`.

`kit-drawio` (and so `kit-viewpoints`) uses the team style file `memory/context/drawio-styles.json`
when no `--styles` or `KIT_DRAWIO_STYLES` is given, so diagrams follow your standard by default.

**Monthly regulatory watch** (off by default). Set the "Regulatory watch" field in
`memory/context/compliance.md` to public regime names (for example "SEC Reg SCI, CFTC, DORA, NIST"),
optionally a "Regulatory watch folder", then `REG_WATCH="on"`. It runs on the first Monday's weekly
review (`REG_WATCH_WHEN="every-run"` to test it on any weekly review) and is skipped at the budget's
warn level or when fewer than `REG_WATCH_MIN_LEFT` (15) minutes remain. It's separate from the weekly
review's horizon watch, which follows the future tech planner's watch list.

**Monthly architecture digest** (off by default). With `ARCH_DIGEST="on"`, the first weekly review of
each month (day 1 to 7) runs `kit-digest --write --month last --brief`: last month's one-page digest goes
to `briefs/digest-YYYY-MM.md` for your edit (one already there is kept), and the review points at it. It
reads the decisions folder, the reference architecture index, the radar, and the exception register, so set
the library root first; a missing source only empties its section. No model call; the same on macOS
and Windows.

The red team and threat modeler need no setup beyond `standards.md` and `compliance.md`; name a
team copy of their templates under "Design review templates" in `standards.md`. They and the standards
checker save each note in their own project folder (`red-team/`, `threat-model/`, `standards/`) and a
copy, same file name, in the project's `reviews/`, next to the reviewer's notes. Rerun
`doctor.py --fix-agents` after updating so the installed agents have this.

To start the lifecycle radar, save a configuration-management export (JSON or CSV with fields such
as name, os, os_version, support_group, environment) and run
`kit-lifecycle --import FILE --source "where it came from"`. It writes `radar/inventory.json`
(`--force` replaces one, `--out` writes elsewhere); then `kit-lifecycle` writes the summary. OS
names are tidied with the tool's alias map; `radar/os-aliases.json` extends it.

```bash
kit-settings                                  # show current choices
kit-settings delivery local                   # desktop notification and dashboard (default)
kit-settings delivery outlook-drafts          # a draft saved in Outlook, never sent
kit-settings delivery work outlook-drafts     # work items one way...
kit-settings delivery personal local          # ...personal items another
kit-settings todos outlook                    # Outlook Tasks (reaches your phone through Microsoft To Do)
kit-settings email you@example.com            # where Outlook drafts are addressed
kit-settings show --all                       # every setting, by area, with source, status, and description
kit-settings show --all --not-set             # only the ones still to fill in (--area AREA, --json also work)
kit-settings ui                               # open the settings page in your browser (Claude Code asks first)
```

**Seeing every setting.** The dashboard has a Settings panel (at the bottom; open it to search and
filter): the run config, every `- **Field:** value` line in the setup files in `memory/context/`, and
the JSON configs (`connector-guard.json`, `models.json`, `sharing-policy.json`, `retention.json`, and the
diagram files), grouped by area, each with its value, its file and line, a one-line description, and a
status: **set**, **not set** (highlighted), or **default**. Credentials show by name only, and anything
that looks like a credential is masked. `memory/personal/` is never shown, and neither are Kit's own
memory notes in `memory/context/` (only the setup files Kit ships are listed). `kit-settings show --all`
prints the same list. An owner copy of the dashboard template without `$settings` still gets the panel,
at the end of its main area.

**Changing settings in a page.** `kit-settings ui` starts a small local server on 127.0.0.1, on a free
port, and opens a one-time link in your browser (`--no-open` prints it instead; `--idle MINUTES`, default
15, sets when it stops by itself; the Stop button or Ctrl-C stops it sooner). Change a value, press
Preview to see the diff, then Confirm. Each change touches one line of one file (a wrapped setup field
becomes one line), keeps every other byte, backs the old file up to `.install/backups/settings/`, is
logged to `.install/logs/settings-ui.log`, is committed to Kit's private repo when the file is tracked
there (the run config lives in `.install/`, which isn't, and the page says so), and rebuilds the
dashboard. If the commit fails the change is kept and the page says so.

The page edits only an allowlist: run config preferences (delivery and to-do routing, with work items
kept inside Microsoft 365; timings, budgets and alert thresholds, on/off switches for checks, monitors,
the wrap, the digest, and the pulse) and the setup-file fields. It checks each value by type: a path
field must start with a backticked path, a date must be DD-Mmm-YYYY, a channel must be a known one, a
number must be in range, and nothing credential-shaped is ever written. Read-only there, each with how to
change it instead: `connector-guard.json`, `models.json` and the `*_MODEL` keys, `sharing-policy.json`
and `sharing.md` (except Kit id, Owner role, Overload threshold, Default project), `connectors.md`,
`agents.md`, `retention.md`, the data rules, `ALLOW_TOOLS`/`BLOCK_TOOLS`, the commands Kit runs
(`*_CMD`), backup location and encryption, phone approvals and publishing, the guard monitor, connector
endpoints, Claude Code's permission rules, and every credential. Undo a change from the backup, or with
`git -C ~/Claude/Agents/kit revert <commit>`.

| Key | Default | What it does |
|---|---|---|
| `COST_BUDGET_MONTHLY` | empty | Monthly budget for scheduled runs in US dollars; empty records cost but never skips a run |
| `COST_WARN_PCT`, `COST_STOP_PCT` | 80, 95 | From warn, the brief shows budget used; from stop, only `COST_ESSENTIAL_MODES` (morning) runs |
| `RUN_TIMEOUT`, `RUN_TIMEOUT_WEEKLY`, `RUN_TIMEOUT_WORKLIST` | 1200, 3000, 900 s | Time limit per run kind |
| `RUN_LOCK_WAIT` | 1800 s | How long a run waits for another to finish before going ahead |
| `OUTLOOK_CHECK`, `OUTLOOK_RETRY_WAITS` | on, "30 90" | Check Outlook answers before the morning and weekly runs |
| `EOD` | on | End-of-day wrap on or off |
| `EOD_MODEL` | off | "on" writes the wrap with Claude (prompt-eod.md) instead of kit-wrap |
| `WRAP_CALENDAR_CMD` | empty | A command that prints one day's events as JSON, with `{day}` for the date; without it the wrap uses `CALENDAR_JSON_CMD`, which can't see past tomorrow (so Friday's wrap has no Monday meetings) |
| `WRAP_CALENDAR_SIDE` | work | Which short text the calendar line goes in: work or personal |
| `ARCH_DIGEST`, `ARCH_DIGEST_WHEN`, `ARCH_DIGEST_TIMEOUT` | off, first-week, 300 s | The monthly architecture digest on the first weekly review of each month (`every-run` runs it on every weekly review, to test it), and its time limit |
| `TEAMMAP_MAX_LOAD`, `TEAMMAP_MAX_ITEMS` | 100, 8 | kit-teammap's limits: more than this percent allocated, or more than this many open projects and tasks when PPM Express gives no allocation, is over |
| `PHONE_APPROVALS` | on | Single-use daily approval code in delivered work lists and briefs |
| `ONEDRIVE_PUBLISH_DIR` | empty | Folder inside your OneDrive where briefs are published for your phone; empty is off |
| `PUBLISH_PERSONAL` | off | Include personal items when publishing |
| `BACKUP_DIR`, `BACKUP_KEEP` | next to Kit, 14 | Where `kit-backup` writes (any local folder, network share, or synced folder), and how many to keep |
| `BACKUP_ENCRYPT` | off | Encrypt backups (needs a passphrase source below) |
| `BACKUP_KEY_KEYCHAIN`, `BACKUP_KEY_ENV` | empty | Name of the Keychain entry (macOS) or environment variable holding the backup passphrase; never the passphrase itself |
| `DEGRADED_MODE` | on | Write the morning brief without a model when the budget stops runs or the model run fails |
| `RETRY_ON`, `RETRY_DELAY` | on, 120 | Retry a scheduled run once after a transient failure, after this many seconds |
| `RELIABILITY_MIN_PCT` | 90 | `kit-reliability` alerts when a run type's 30-day success rate falls below this |
| `SKIP_DAYS`, `BLOCK_TOOLS` | empty | Days with no morning run; tools unattended runs may never call |
| `DELIVERY` | local | How briefs reach you: any of `local`, `outlook-drafts`, `outlook-review` (and the legacy `imessage` on macOS, `sms` stub on Windows), space-separated; Kit never sends mail |
| `DELIVERY_WORK`, `DELIVERY_PERSONAL` | unset | When either is set it replaces `DELIVERY`: work items (tagged [work]) and personal items go their own ways, each as its own short text |
| `DELIVERY_EMAIL_TO` | you@example.com | The address Outlook drafts are made out to (usually your own) |
| `REMINDERS_BACKEND` | outlook | To-do sync with Outlook Tasks, or `apple` for Apple Reminders (macOS only; syncs through iCloud, so keep work out of it) |
| `TODOS_PERSONAL`, `TODOS_WORK` | unset | macOS only: personal and work to-dos in different apps, each with its own "Kit Inbox" and "Kit: <name>" lists |
| `PREFLIGHT_CONNECTORS` | empty | Space-separated `claude mcp` names of connectors that sign in with OAuth, for the login check at 06:45 and 15:45 |
| `CONNECTION_CHECK`, `CONNECTION_WAIT` | on, 300 s | Before each run's model call, check the API can be reached; wait up to this long, then skip the model run (the morning still gets its degraded brief) |
| `CONNECTION_URL` | unset | The address the connection check probes; unset uses `ANTHROPIC_BASE_URL`, else the Anthropic API, through `HTTPS_PROXY` when set |
| `WRAP_WORKDAYS` | "1 2 3 4 5" | The end-of-day wrap's working days (1 = Monday), for "the next working day" |
| `RUN_TIMEOUT_EOD` | 300 s | macOS: time limit for `kit-wrap` in the end-of-day run (with `EOD_MODEL="on"`, `RUN_TIMEOUT` applies instead) |
| `PPMX_PULSE`, `PPMX_PULSE_DAY`, `PPMX_PULSE_SCOPE`, `PPMX_PULSE_TIMEOUT` | off, 1, all, 300 s | The PPM Express pulse in the morning brief on this weekday (1 = Monday), for all projects, `mine`, or named portfolios and programs, and its time limit |
| `PPMX_TASK_DUE_FIELD` | FinishDate | The task field a meeting action's due date goes in when a project has no tasks to copy it from |
| `PREREAD_MODEL`, `PREREAD_TIMEOUT` | opus, 900 s | `kit-preread`'s model and time limit |
| `REHEARSE_MODEL`, `REHEARSE_TIMEOUT` | opus, 900 s | `kit-rehearse`'s model and time limit |
| `REVIEW_LOOP_MODEL`, `REVIEW_LOOP_TIMEOUT` | each agent's own, 1800 s | `kit-review-loop run`'s model (empty: the agent's) and time limit per agent run |
| `TEAMMAP_COVERAGE` | empty | Another coverage file for `kit-teammap` (empty: `briefs/team/coverage.json`) |
| `TEXTBACK` | off | macOS only: answer texts you send yourself that start with "Kit" |
| `TEXTBACK_ASK` | on | Let texted questions go to Claude (read-only, Kit's folder only); "off" allows commands only |
| `TEXTBACK_MODEL`, `TEXTBACK_PARSE_MODEL` | sonnet, haiku | The model for texted questions, and the quick one that reads a date or event out of a text |
| `TEXTBACK_MAX_PER_HOUR` | 30 | Most texts answered in an hour (a value that isn't a number means 30) |

### Day-to-day tools

- **Meeting prep:** `kit-meetprep --from-config` (or the optional `meetprep` job) writes a pack per
  meeting in the next two hours to `briefs/meetprep/`; attendees appear by role, never by name or
  address.
- **Inbox triage:** pipe your mail tool's inbox listing to `kit-triage -`; suggestions go to
  `briefs/triage-<date>.md`. It never moves, flags, or answers mail.
- **Awaiting replies:** `kit-awaiting --sent FILE --inbox FILE` needs your mail tool to list sent
  items; without that, it says so.
- **Calendar holds:** `kit-holds propose --from-plan FILE` (or `--block "YYYY-MM-DD HH:MM 90m Title"`,
  `--from-queue`, `--meeting-prep 30m`) writes draft .ics files to `briefs/holds/<date>/`; `kit-holds
  open all` hands them to your calendar app to review and save.
- **1:1 and wins:** `kit-oneonone` before a 1:1 (`--done` after it); `kit-wins collect` weekly (the
  weekly review runs it), `kit-wins report --from ... --to ...` for reviews. Edit `memory/accomplishments.md` freely: collect remembers
  what it took (`memory/.accomplishments-seen.json`), and `kit-wins mark` records the sources as collected if
  you rewrite the log before that record exists.
- **Letters:** write the letter as plain text (`letters/<folder>/letter.md`, blocks separated by blank
  lines, `{{SIGNATURE}}` where the signature goes), then `kit-letter build FILE` (room for a pen
  signature) or `kit-letter sign FILE` (your saved PNG from `letters/signature/`; Claude Code asks every
  time). The letters desk drafts and logs letters; it never sends one.
- **Dates and keeping in touch:** `kit-dates add NAME MM-DD --what birthday --action card` (or a full
  date for an age; `--work` for work dates); `kit-touch add NAME --every 30`, `kit-touch talked NAME`,
  and `kit-touch scan --add` to read "Call with NAME" and "Lunch with NAME" events. Both feed brief
  lines; nothing is ever sent.
- **Expiry list:** `kit-expiry add NAME --date YYYY-MM-DD --warn 30` for tokens, logins, domains,
  certificates, and renewals; `kit-expiry` lists them soonest first. It looks certificates and domains
  up over the network only with `--live`; the health check and the brief read the saved results.
- **Feedback on your team:** `kit-feedback add-person NAME --role R`, `kit-feedback add NAME TEXT --kind
  praise`, `kit-feedback prep NAME` before a 1:1, `kit-feedback review NAME --from ... --to ...` for a
  review. Owner-only, never committed, exported, or texted.
- **Meeting load:** `kit-meetload` (the last two weeks; `--ahead`, `--profile work|personal`, `--ics FILE`
  for a calendar kitcal can't read, `--holds` to draft focus time). It reads the calendar and changes
  nothing.
- **Library:** `kit-library add NAME FOLDER --about "TEXT"`, then `kit-library index` and `kit-library
  search WORDS`; `kit-library deliver FILE --kind reports` puts finished work in the output folder
  (Markdown arrives as Word). Mark a collection `"classification": "work"` in `library/collections.json`
  to keep it off the phone mirror and out of texts.
- **Design reviews:** `kit-preread FILE --meeting "TITLE"` before reviewing someone else's design;
  `kit-rehearse FILE --board "NAME"` before defending your own. Both are closed, paid Claude runs that
  Claude Code asks before; `--dry-run` shows what would be sent.
- **The review loop on your own draft:** `kit-review-loop plan PROJECT DRAFT` (the steps, each agent's
  command, the cost), `kit-review-loop run PROJECT DRAFT` (the reviewer, then the red team, threat
  modeler, and standards checker side by side; it asks first, and Claude Code does too, `--yes` for no
  prompt), `kit-review-loop merge PROJECT` (writes `review-decisions-<date>.md`: fill in Decision with
  accept, change, or reject, and a note for each change), then `kit-review-loop feedback PROJECT`
  (writes `feedback-v<next>.md` for the writer). After the writer's next version,
  `kit-review-loop run PROJECT NEXT-DRAFT --only reviewer`. The runs read Kit's folder and the
  library and write only in the project; they get no shell, web, or MCP servers, so the reviewer's
  document QA scripts and `kit-exceptions` are skipped (the notes say so).
- **Vendor evaluations:** `kit-vendors new SLUG --title T --vendors "A, B"`, `kit-vendors questions SLUG
  --csv FILE` (for you to send), `kit-vendors import SLUG VENDOR FILE`, `kit-vendors score ...`, and
  `kit-vendors show SLUG`. Nothing is sent to a vendor.

## 8. Connectors

Kit reads outside systems through MCP servers you add to Claude Code (`claude mcp add ...`; see
Claude Code's docs). Then:

1. List each server in `memory/context/connector-guard.json` under `allowed_servers`, with the read
   tools in `allow_tools` and anything that writes in `deny_tools`.
2. Set each server's credential as an environment variable, or an entry in the Keychain (Credential
   Manager on Windows); record only its **name** (optionally under `credential_env` in
   `connector-guard.json`). Never write a value into a file.
3. Run `kit-connect test`. It checks each server is allowed, that each credential it names is in the
   environment or the Keychain or Credential Manager (by name only), and Claude Code's own health check.
4. Optionally pick one cheap read-only tool per server under `probe_tools`, then
   `kit-connect test --read` makes one read call per server as the gateway agent, under the guard
   (a few cents each). The connector guard's audit log decides the result: a logged call with no
   error passes even if the run's own answer is cut short.
5. Check a filtered search returns a plausible count before you trust it. Some systems (ServiceNow
   among them) silently ignore a filter on a field name they don't recognise and return the whole
   table; a reference field can also hold a different type than its name suggests. Look up one
   record's fields first, then scope by the fields it actually has.

The health check (`doctor.py`) looks credentials up the same way, and warns about one it finds in neither place.

### Tokens in the Keychain for any server (kit-mcp-env)

Most MCP servers read their token from an environment variable. `kit-mcp-env` lets that variable come from
the Keychain (Credential Manager on Windows), the way `kit-ppmx` gets `PPMX_TOKEN`: it reads the entry as
the server starts and puts the value in that server's environment only, so neither the MCP configuration,
your shell profile, nor Kit's config holds it, and scheduled runs find it too. For Jira and Confluence
through mcp-atlassian on Server or Data Center, for example:

1. **TLS checking on first.** A token should never travel over a connection that isn't checked. Remove
   any setting that turns checking off (`JIRA_SSL_VERIFY=false`, `CONFLUENCE_SSL_VERIFY=false`,
   `NODE_TLS_REJECT_UNAUTHORIZED=0`), and if your company's certificates need its own CA bundle, name it:
   `REQUESTS_CA_BUNDLE` for Python servers such as mcp-atlassian, `NODE_EXTRA_CA_CERTS` for Node servers
   (the hardening checklist in `docs/CONNECTIVITY.md`).
2. **The tokens.** Store each under the name of the variable the server reads; each command asks for the
   value, so it never lands in your shell history:

   ```bash
   security add-generic-password -s JIRA_PERSONAL_TOKEN -a "$USER" -w          # macOS: the Keychain
   security add-generic-password -s CONFLUENCE_PERSONAL_TOKEN -a "$USER" -w
   ```

   ```powershell
   cmdkey /generic:JIRA_PERSONAL_TOKEN /user:kit /pass                          # Windows: Credential Manager
   cmdkey /generic:CONFLUENCE_PERSONAL_TOKEN /user:kit /pass
   ```
3. **The server.** Remove the old entry (`claude mcp remove atlassian`, and with it any token it held),
   then add it back through `kit-mcp-env`: the variable names before the second `--`, the server's own
   command after it, pinned to a version you've reviewed:

   ```bash
   claude mcp add --scope user atlassian --env JIRA_URL=https://jira.example.com \
     --env CONFLUENCE_URL=https://wiki.example.com --env REQUESTS_CA_BUNDLE=/path/to/ca-bundle.pem -- \
     python3 ~/Claude/Agents/kit/.install/shared/bin/kit-mcp-env JIRA_PERSONAL_TOKEN CONFLUENCE_PERSONAL_TOKEN \
     -- uvx mcp-atlassian@<version>
   ```

   On Windows, use the full paths to `python.exe` and to `kit-mcp-env` under `%USERPROFILE%`.
4. **Check.** `kit-mcp-env --check JIRA_PERSONAL_TOKEN CONFLUENCE_PERSONAL_TOKEN` says where each one is,
   by name only. Add `"credential_env": {"atlassian": ["JIRA_PERSONAL_TOKEN", "CONFLUENCE_PERSONAL_TOKEN"]}`
   to `connector-guard.json`, then run `kit-connect test`.

When a token can't be found, the server doesn't start and `claude mcp list` shows it failed; Claude Code's
MCP log has `kit-mcp-env`'s note naming the entry to store. `NAME=ENTRY` reads an entry with another name,
but then `kit-connect` can't find it by the variable's name.

The health check, and so the morning brief, looks at how each user-scope server in `~/.claude.json` starts,
without starting it, and warns by server name only: **MCP credentials** (a `kit-mcp-env` credential, in the
entry or in a launcher script it runs, that's neither set nor in the Keychain or Credential Manager, looked
up by entry name, never read), **MCP TLS checking** (`NODE_TLS_REJECT_UNAUTHORIZED=0` or an `SSL_VERIFY` of
false in the entry's `env`, its arguments, or its launcher), **MCP versions** (`npx` with `@latest`, a tag,
or no version), and **MCP launchers** (a launcher script the entry names that isn't there). A launcher is
any `.sh`, `.ps1`, `.cmd`, or `.bat` file in the entry's command line, such as
`~/.mcp-servers/launchers/NAME.sh` running `kit-mcp-env NAME=ENTRY -- node --use-system-ca ...`. Files
passed with `--env-file` aren't opened: they hold tokens.

### PPM Express (kit-ppmx)

Kit ships its own PPM Express connector, `kit-ppmx`: an MCP server that reads portfolios, programs,
projects, tasks, key dates, deliverables, ideas, challenges, and resources, and creates and updates them
(PPM Express's API has no delete). It runs on your computer, macOS or Windows, for Claude Code and Claude
Desktop, with your own personal access token. `kit-ppmx setup` prints these steps with this computer's
paths filled in, and changes nothing.

Version 0.3.0 was confirmed against the live API on 02-Nov-2026: the endpoint paths against PPM
Express's OpenAPI description, and the reads, response shapes, and field names against a live tenant
(read-only). The writes follow the description and are tested against the fake server. Person filters
take part of a name or `"me"` (your token's user); `list_my_work` gathers your tasks and deliverables
across projects, bounded by `PPMX_WORK_MAX_PROJECTS` and `PPMX_WORK_SECONDS`. PPM Express's `/me` gives
no name, so set `PPMX_MY_NAME` in Kit's config to your name as PPM Express shows it for an exact `"me"`
match. `shared/ppmx/README.md` has the details.

1. **A token.** In PPM Express > Automation, create a personal access token: read scopes to look, and
   write scopes (such as Write Projects) if Kit should make the changes you approve. Store it where only
   you can read it; each command asks for the token, so it never lands in your shell history:

   ```bash
   security add-generic-password -s PPMX_TOKEN -a "$USER" -w     # macOS: the Keychain
   ```

   ```powershell
   cmdkey /generic:PPMX_TOKEN /user:kit /pass                    # Windows: Credential Manager
   ```

   An environment variable `PPMX_TOKEN` works too, but Claude Desktop doesn't see variables set in a
   terminal.
2. **The address.** In Kit's config (`~/Claude/Agents/kit/.install/shared/morning/config`), add your
   tenant's API address from PPM Express > Automation:

   ```bash
   PPMX_BASE_URL="https://<host>/@<tenant>/v1.0"
   ```

   Changes are on. `PPMX_WRITES="off"` on another line makes the connector read-only.
3. **Claude Code.** Add the server for your user (`kit-ppmx setup` prints the line with your Python and
   path):

   ```bash
   claude mcp add --scope user ppmx --env PYTHONUTF8=1 -- python3 ~/Claude/Agents/kit/.install/shared/bin/kit-ppmx serve
   ```

   On Windows, use the full path to `python.exe` and to `kit-ppmx` under `%USERPROFILE%`.
4. **Claude Desktop** (optional). Run `kit-ppmx desktop`: it adds the same server to Desktop's config
   (`~/Library/Application Support/Claude/claude_desktop_config.json` on a Mac,
   `%APPDATA%\Claude\claude_desktop_config.json` on Windows) after saving a copy of it, keeping every
   other server. Quit and reopen Desktop. `kit-ppmx desktop --remove` takes it out again.
5. **Kit's agents.** So Kit's agents can read PPM Express through the gateway, add `ppmx` to
   `allowed_servers` in `memory/context/connector-guard.json`, with `"credential_env": {"ppmx":
   ["PPMX_TOKEN"]}` and `"probe_tools": {"ppmx": "mcp__ppmx__get_current_user"}`, and list PPM Express
   under Systems in `connectors.md`. The guard never lets an agent make a change.
6. **Check:** `kit-ppmx check` (who the token belongs to, its scopes, whether it can make changes, when it
   expires), then `kit-connect test ppmx`.
7. **The Monday pulse** (optional). Set `PPMX_PULSE="on"` in Kit's config, and `PPMX_PULSE_SCOPE` to
   `mine` or to portfolio names if you don't want every project your token sees. The first Monday saves a
   snapshot; from the second on, the brief says what changed. `kit-ppmx pulse` shows it any time.
8. **Meeting actions** (optional). After the meeting scribe writes minutes, `kit-ppmx actions MINUTES.md`
   proposes a PPM Express task for each action. If an action's project isn't matched, `kit-ppmx actions map
   SLUG "PROJECT NAME"` remembers it (in `memory/context/ppmx-projects.json`). Kit makes each proposal only
   on your yes, one at a time (`kit-ppmx actions apply N`), and Claude Code asks before each.

How changes stay yours: in Claude Code, Kit's permission rules make every `create_` and `update_` tool ask
you first, even if you allow the rest of the server, and a scheduled run can't answer, so it never makes a
change. Claude Desktop asks before each tool runs unless you tell it to always allow one; leave the
`create_` and `update_` tools on asking. Before a change, Claude says what it will create or change. Every
call, from either app, is recorded without its values in Kit's audit folder (`ppmx-YYYY-MM.jsonl`).
Rerun Kit's installer after an update so Claude Code picks up new rules.

For a team, the same server also runs as a service on OpenShift: `shared/ppmx/openshift/INSTALL.md`.

## 9. Model routing

`~/Claude/Agents/kit/models.json` maps agents and scheduled runs to profiles: `deep` (Opus, the
default), `standard` (Sonnet), `fast` (Haiku), and `local`. A file in `models/<agent>.json`
overrides it for one agent.

```bash
kit-models                 # effective model per agent and run, and where it came from
kit-models check           # validate the config
kit-models apply --dry-run # show what would change
kit-models apply           # write each agent's model line and the runs' models.env
python3 ~/Claude/Agents/kit/.install/shared/doctor.py --fix-agents
```

`"enabled_phase": 1` keeps everything on Claude. With `2`, `kit-delegate` and `kit-run` may also
reach the other providers in `models.json` (an OpenAI-compatible API, or a local model through
Ollama or LM Studio), each limited by `max_data_class` and `org_profile.non_claude_max_data_class`.
Direct calls need the provider's credential by name (`credential_env` or `keychain_entry`); direct
Anthropic calls need `ANTHROPIC_API_KEY`, separate from Claude Code's sign-in. Move an agent to a
cheaper profile only after `kit-evals --live <agent> --profile <profile> --yes` passes.

## 10. Sharing between Kits

1. In `memory/context/sharing.md`, set **Kit id** (not your name), **Owner role**, **Publish** (the
   record types), and **Shared root** (a folder every Kit can reach).
2. Check `sharing-policy.json`: allowed transports and roots, blocked folders, the classification
   ceiling, and whether confidential records may ever leave (default: never).
3. Publish and read:

```bash
python3 ~/Claude/Agents/kit/.install/shared/bin/kit-publish --dry-run
python3 ~/Claude/Agents/kit/.install/shared/bin/kit-publish
kit-team sync
kit-team status
```

Messages: `kit-team send --to <kit id> --subject "..." --body-file note.txt` writes a draft and sends
only after your yes at the keyboard; `kit-team inbox` and `kit-team ack <id>` read and acknowledge.
The SQL transport (`Transport: sql`, `sharing-db.json`) is tested on MySQL and PostgreSQL; SQL Server
is untested. Store the database password in a Keychain entry (`security add-generic-password -s
kit-sharing-db -a <db user> -w`), name it in `sharing-db.json` with the host, port, database, and
user, install the driver (`PyMySQL`), add `sql` to the policy's allowed transports, and run
`kit-team db-init`. See `shared/sql/README.md`.

Team views read only the local cache: `kit-team load` shows open demands, IAs, GDSs, and POCs per Kit
by owner role (the demand register's optional Kind, Stage, and Opened columns feed it; without Kind,
IA-, GDS-, and POC- number prefixes decide), and `kit-team experts <topic>` ranks Kits by the evidence
they've shared. To share your declared topics, list them in `memory/context/expertise.md` and add
`expertise` to **Publish**.

### Sharing Kit content as plugins

```bash
kit-plugin build team-kit --agents poc-lead,lab-planner --templates poc-charter-template \
  --lessons my-lesson --marketplace ./marketplace
kit-plugin check ./marketplace          # manifests, public denylist, credential scan, review gate
kit-plugin list --marketplace ./marketplace
```

Fill in each plugin's `REVIEW.md` (hooks, scripts, `bin/`, and servers need a recorded human review;
only lessons marked `share: team` are packed), commit to a branch of an internal git repo, and merge
after a second reviewer. Teammates add it with `claude plugin marketplace add <repo URL>` and
`claude plugin install <plugin>@<marketplace>`; `claude plugin validate <dir>` is a useful second
check. `kit-plugin` never pushes or publishes.

## 11. Updating

```bash
kit-update              # fetch GitHub and show new commits and files; changes nothing
kit-update --apply      # back up, move the clone onto GitHub's main, rerun the installer
kit-update --reinstall  # rerun the installer even when the install matches the clone
kit-version --check     # installed version vs GitHub
```

When the clone is already up to date with GitHub but the install isn't from its commit (the clone
moved without the installer, after `kit-patch --sync` or a `git pull`), `kit-update` says so and
`--apply` reruns the installer without moving the clone. `kit-update` stops if your clone has
uncommitted work or commits GitHub doesn't have, except when GitHub already applied your patch: one of
its commits has the same files, or differs only in binary files both have (the Word and PDF documents
rebuilt on publishing), which it names; your versions stay on the backup branch. After an update, the
next brief adds "What changed in Kit" once. Rerun `doctor.py --fix-agents` if agents changed.

### Updating from a zip

For an install with no git clone (you received Kit as a zip):

```bash
kit-update --zip KIT-1.7.0-abc1234.zip                      # check it and show what changes; changes nothing
kit-update --zip KIT-1.7.0-abc1234.zip --sha256 <published>  # the same, and check the published SHA-256
kit-update --zip KIT-1.7.0-abc1234.zip --apply               # install it (asks first; --yes skips that)
```

Without `--apply`, `kit-update` checks the zip, extracts it into a new temporary folder, and deletes
that folder afterward; it runs nothing from the zip and changes nothing in the install. It prints the
zip's SHA-256, its version and commit (from the zip comment; it says so when there's none), the
installed version and commit, whether the zip is newer, the same, or older, the CHANGELOG entries in
between, and how many files are added or changed against the installed copy, with the main ones.

It refuses the zip, changing nothing, when an entry has an absolute path, a `..` part, a drive letter,
a backslash, or a name Windows can't hold; when it holds a symbolic link, a device, or another special
file, or an encrypted entry; when there isn't exactly one top-level folder; when it's over 200 MB
uncompressed or 20,000 entries; when VERSION, `kit/`, `shared/`, or the installers are missing; or
when `--sha256` doesn't match. An older zip needs `--allow-downgrade`; the same version has nothing to
do unless you add `--reinstall` (with `--zip`, `--reinstall` doesn't imply `--apply`).

`--apply` keeps the release in `~/Claude/Agents/kit/.install/releases/<version>-<commit>/` (the last
three; older ones are deleted, only from that folder), runs that copy's installer
(`platform/mac/install.sh`, or `platform/windows/install.ps1` on Windows) with your name from the
existing settings as `KIT_OWNER`, and records in `.install/VERSION.json` that the install came from
the zip: its file name, SHA-256, and commit (`kit-version` shows them). Nothing is fetched from the
network.

To roll back, rerun an earlier release's installer, which `kit-update` prints, for example
`bash ~/Claude/Agents/kit/.install/releases/1.6.3-9488927/platform/mac/install.sh`, or install the
earlier zip with `kit-update --zip FILE --apply --allow-downgrade`.

If you also have a git clone, `--zip` leaves it as it is and warns that it now differs from the
install. `kit-update` without `--zip` then reports the install as newer than, or different from, the
clone and won't install the clone over it unless you pass `--reinstall`; if GitHub has moved on but is
still behind the zip, `--apply` moves the clone and skips the installer.

## 12. Backup and restore

```bash
kit-backup                                   # checked archive of Kit's folder and history
kit-backup list
kit-backup verify
kit-backup restore <archive> --to <empty folder>
```

Choose where backups go with `BACKUP_DIR` (any local folder, a network share, or a synced folder),
or `kit-backup --dir DIR` for one run. Pick a location that survives losing the computer.

To encrypt them, create the passphrase yourself (Kit never creates, stores, or shows it):

```bash
security add-generic-password -s kit-backup -a "$USER" -w     # asks for the passphrase (macOS)
```

then set `BACKUP_ENCRYPT="on"` and `BACKUP_KEY_KEYCHAIN="kit-backup"` in the config. On Windows, put
the passphrase in an environment variable and set `BACKUP_KEY_ENV` to that variable's name. Keep the
passphrase somewhere else as well: without it an encrypted backup can't be restored. `kit-backup
--encrypt` or `--no-encrypt` overrides the setting for one run. An unencrypted backup is refused
outside your home folder or in a synced or shared folder unless you pass `--allow-plain`, because
backups hold your personal notes.

### Audit evidence

```bash
kit-audit-export --from 2026-01-01 --to 2026-01-31 --zip      # default: the last 30 days, next to Kit
```

The pack holds the connector audit log for the range, `kit-audit` outputs, approvals, the guard and
sharing policies, permission lists (allow, ask, deny only), each agent's tools and model, the version,
the health check, and a SHA-256 manifest. It's scanned for credential-like text before it's kept, and
never includes personal notes, briefs, mail, or library documents.

## 13. Pausing

```bash
kit-pause "audit in progress"   # no scheduled run starts; every connector call is denied
kit-pause status
kit-pause resume
kit-pause "incident" --hard     # also unload the launchd jobs (shows the commands; needs --yes)
```

## 14. Uninstalling

```bash
bash ~/Claude/Agents/kit/.install/platform/mac/uninstall.sh
```

This removes Kit's line from `~/.claude/CLAUDE.md` and exactly the settings entries the installer
added (backing both up). Kit's own folder is left alone; delete it yourself if you want it gone.
Unload any launchd jobs first (`launchctl bootout gui/$(id -u)/com.$USER.kit.<job>`). On Windows,
run `platform\windows\uninstall.ps1` and `unregister-tasks.ps1`. To reinstall later, run
`bash ~/Claude/Agents/kit/.install/platform/mac/install.sh`.

## 15. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `/context` doesn't list KIT.md | The import line is missing; rerun the installer |
| "Kit's staff installed: out of date" | Run `doctor.py --fix-agents` |
| "Connector guard hooks" fails, or the installer stops at the guard check | "a write would go through": the agent runs the guard with Python directly and that Python can't start (on Windows, often the Microsoft Store's `python3` stub). Copy Kit's current agents (`doctor.py --fix-agents`); for an agent you edited, copy its `hooks:` block from `.install/kit/agents/`. "the guard can't run": `kit-hook` found no Python 3.8 or newer; install one so `python3`, `py -3`, or `python` runs it, or set `KIT_PYTHON` to its full path (in your environment, or in the `env` block of `~/.claude/settings.json`). Then rerun the installer or `doctor.py` |
| "Models: N agents don't match" | Run `kit-models apply`, then `--fix-agents` |
| "Scheduled X run: not loaded" | `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.$USER.kit.X.plist` |
| "Recent runs: ... run didn't finish" | Read that day's log. A later successful run of the same kind clears it. |
| A run "hit its time limit" (exit 142) | Raise `RUN_TIMEOUT` (morning and every other run), `RUN_TIMEOUT_WEEKLY`, or `RUN_TIMEOUT_WORKLIST` in the config, or trim the run. The end-of-day wrap uses `RUN_TIMEOUT` only with `EOD_MODEL="on"`; otherwise `RUN_TIMEOUT_EOD` (300 s) limits `kit-wrap` |
| "KitMessages needs Full Disk Access" | Allow KitMessages.app in System Settings > Privacy & Security > Full Disk Access (again after a rebuild) |
| `kit-library` says it needs folder permission | Build KitLibrary.app (`platform/mac/library/build.sh`) and allow it under Files and Folders |
| "waiting for another run to finish" in the log | The lock is working; a run that died leaves a lock that's cleared automatically |
| Calendar and mail marked stale, AppleEvent error -1712 | Outlook didn't answer; restart Outlook. `kit-outlook` retries before each run. |
| A tool "needed approval" in an unattended run | Add it to `ALLOW_TOOLS` or `ALLOW_TOOLS_WEEKLY` |
| "Setup paths: FILE FIELD: doesn't start with a backticked path" | Put the path first on the field's line (`- **Field:** \`path\` ...`): the tools read only a value that starts with it, so the line reads as not set. "starts with the placeholder": replace `<library root>/...` with the real path, relative to the library root or in full |
| "MCP credentials: SERVER: a credential kit-mcp-env starts it with is neither set nor in the Keychain" | The server won't start. `kit-mcp-env --check NAME=ENTRY` (the names in its launcher or entry) says which; store it with the command it prints |
| "MCP TLS checking: turned off for SERVER" | Remove `NODE_TLS_REJECT_UNAUTHORIZED=0` or `..._SSL_VERIFY=false` from the entry or its launcher; for a company CA, run node with `--use-system-ca` or name the bundle (`NODE_EXTRA_CA_CERTS`, `REQUESTS_CA_BUNDLE`) |
| "MCP versions: npx runs an unpinned package" | Pin the package to a reviewed version with no known advisories (`npx -y pkg@1.2.3`) in `~/.claude.json` |
| "Connector credentials: missing by name" | The name in `credential_env` is neither a variable that's set nor a Keychain (Credential Manager) entry: set the variable or store the entry under that name; `kit-connect test` confirms |
| "Direct model calls: no credential found" | Only matters with `enabled_phase` 2: set the provider's credential variable |
| "Kit version: the repo clone is at ..." | Rerun the installer, or `kit-update --apply` |
| "Kit is paused" banner | `kit-pause resume` |
| Sync conflict copies in the shared folder | Ignored and reported by `kit-team warnings`; delete them in the sync client |
| A brief marked "Degraded brief" | No model run that morning: the log says why (budget stop, failure, time limit) |
| `kit-backup` refuses a plain backup | The folder is outside home or synced/shared: encrypt, or pass `--allow-plain` deliberately |
| `kit-backup verify` fails on an encrypted backup | Wrong passphrase source, or the file changed; nothing is restored |
| `kit-awaiting` finds no sent messages | Your mail tool needs sent-items commands |
| `kit-holds` skips a block | It clashed with a busy event or fell outside working hours; holds are never moved |
| `kit-plugin check` fails | Fix the listed manifest, denylist, credential, or lesson issue, or record the review in REVIEW.md |
| The log shows "retrying <mode> after transient failure" | Auto-retry at work. A second failure falls back to the degraded brief (morning) or a failure notice. |
| "Run reliability" warning in the health check | Run `kit-reliability` for the detail by run type (failures, time-outs, slow runs, no recent success) |

Still stuck: run `doctor.py`, check the day's log in `.install/logs/`, and ask Kit to explain.

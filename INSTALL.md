# Installing Kit

This guide takes you from nothing to a working Kit: install, first checks, setup, scheduled runs,
connectors, and day-two tasks (updating, backups, pausing, uninstalling, troubleshooting).
`~` means your home folder. Commands assume `~/.local/bin` is on your `PATH`; if it isn't, run a
tool by its full path, `python3 ~/Claude/Agents/kit/.install/shared/bin/<tool>`.

macOS is the supported platform. **Windows is built but untested** on a real Windows machine; treat
every Windows step as a first trial and report what breaks.

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

## 3. Run the installer

**macOS**

```bash
KIT_OWNER=Alex bash install.sh
```

**Windows (untested)**

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
| Windows | `.cmd` shims for the same tools, and owner-only NTFS permissions on Kit's folder |

Both Claude Code files are backed up to `.install/backups/` first, and the installer records exactly
what it added in `.install/manifest.json` so the uninstaller can remove just that. It also records
the version and commit in `.install/VERSION.json`.

The installer then runs `kit-settings setup`, which asks (only when someone is at the keyboard) how
briefs should reach you and which app your to-dos sync with.

If your Claude Code settings run with permission prompts bypassed, the installer warns you: Kit's
ask rules only work with prompts on.

### Install the agents into Claude Code

The installer puts Kit's staff in `~/Claude/Agents/kit/agents/`. Copy them where Claude Code finds
them:

```bash
python3 ~/Claude/Agents/kit/.install/shared/doctor.py --fix-agents
```

Rerun this after any update that changes an agent, or after `kit-models apply`.

## 4. First checks

```bash
claude                      # then run /context and confirm KIT.md is listed under Memory files
python3 ~/Claude/Agents/kit/.install/shared/doctor.py          # full health check
python3 ~/Claude/Agents/kit/.install/shared/doctor.py --brief  # problems only
kit-version                 # installed version and commit
kit-connect test            # connectors: guard, credential variables by name, Claude Code health
kit-evals                   # static agent checks (free)
kit-models                  # which model each agent and run uses
kit-reliability             # how the scheduled runs have been doing (after a few days)
```

Then say "Kit, introduce yourself."

## 5. Fill in the setup files

Each agent reads a setup file in `~/Claude/Agents/kit/memory/context/` before every job. Fields
marked "not set" limit what the agent can do; the health check and the agents themselves say what's
missing. Fill in what applies to you, in roughly this order:

| File | Used by | What to fill in |
|---|---|---|
| `library.md` | librarian and most agents | The library root folder, published document libraries, read-only sources |
| `writing.md` | IA and GDS writers, reviewer, planner, deck builder | Templates, examples, style skills, output format, quality loop thresholds |
| `calendar.md` | scheduler, `kit-holds`, `kit-meetprep` | Calendar command, working hours and time zone (for example `09:00-17:00 America/New_York`; holds assume 09:00 to 17:00 until set), habits |
| `meetings.md` | meeting scribe, `kit-awaiting` | Meeting inbox, your notes folders, project managers, mail commands, vendor template, "Awaiting reply after" (days) |
| `connectors.md` | gateway and its callers | Which outside systems, which records to read first |
| `demands.md` | demand tracker | Where demands and tickets live, the register |
| `intake.md` | intake triager | Intake checklist, when an impact assessment is needed, project naming |
| `knowledge.md` | curator, handoff, `kit-sysprofile` | Knowledge base location and first topics, where system profiles go |
| `standards.md` | standards checker, `kit-refarch` | Engineering standards, reference architectures (the index `kit-refarch` reads, for example `published/<library>-index.md`), security baselines, DR tiers, waivers |
| `compliance.md` | risk and compliance mapper | Control frameworks, policies, data classes, sign-off roles, risk rating |
| `costs.md` | cost estimator | Rate cards, labor rates, currency, contingency, sizing basis (`kit-sizing`) |
| `estimating.md` | PMO estimator | Past project data, phase model, roles |
| `changeboard.md` | change board prep | Template, risk scoring, checklist, lead times, cadence |
| `decisions.md` | decision recorder | ADR template and folder, who can accept a decision |
| `diagrams.md` | diagrammer | Diagramming standard, stencils, formats |
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
| `audit.md` | auditor, `kit-audit`, `kit-audit-export` | Audit folder, reviewers, working hours, thresholds |
| `retention.md` + `retention.json` | `kit-retention` | Records rules from your policy (default: keep everything) |
| `sharing.md` + `sharing-policy.json` (+ `sharing-db.json` for SQL) | `kit-publish`, `kit-team` | Kit id, role, what to publish, transport, shared root, overload threshold (default 8), organization limits |
| `connector-guard.json` | connector guard, `kit-connect` | Allowed servers and tools, denied tools, audit folder, optional probe tools and credential variable names |
| `agents.md` | Kit | The staff roster; edit only to add an agent |

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
| `eod` | Weekdays 17:30 | Optional end-of-day wrap-up (`EOD="off"` skips it) |
| `backup` | Daily 12:30 | `kit-backup` with the config's `BACKUP_*` settings (encrypted when `BACKUP_ENCRYPT` is on); runs on wake if the Mac was asleep; logs to `.install/logs/backup.log` |
| `meetprep` | Weekdays, every 30 minutes 07:00 to 18:00 | Optional meeting prep packs (`kit-meetprep`); a plain script, no Claude run; honours `kit-pause` |
| `open` | Weekdays 09:45 | Optional, for a trading setup only |

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

**Windows (untested):** `platform\windows\morning\register-tasks.ps1` registers the same runs in
Task Scheduler ("Kit Morning Brief", "Kit Weekly Review", "Kit Work List", "Kit Reminders Sync",
and optional trading tasks); `unregister-tasks.ps1` removes them. See
`platform/windows/morning/README.md`.

### Allowing tools in unattended runs

An unattended run can't ask you for approval, so it only uses tools allowed in the config
(`ALLOW_TOOLS`, plus `ALLOW_TOOLS_WEEKLY` for the weekly review), as Claude Code permission rules
separated by semicolons. `run.sh` adds a full-path twin for every `Bash(...~/...)` rule, because a
rule written with `~/` doesn't match a command spelled with the full home path.

## 7. Settings

`kit-settings` changes delivery and to-do sync; everything else is a key in
`~/Claude/Agents/kit/.install/shared/morning/config` (every key is documented in
`shared/morning/config.example`).

```bash
kit-settings                                  # show current choices
kit-settings delivery local                   # desktop notification and dashboard (default)
kit-settings delivery outlook-drafts          # a draft saved in Outlook, never sent
kit-settings delivery work outlook-drafts     # work items one way...
kit-settings delivery personal local          # ...personal items another
kit-settings todos outlook                    # Outlook Tasks (reaches your phone through Microsoft To Do)
kit-settings email you@example.com            # where Outlook drafts are addressed
```

| Key | Default | What it does |
|---|---|---|
| `COST_BUDGET_MONTHLY` | empty | Monthly budget for scheduled runs in US dollars; empty records cost but never skips a run |
| `COST_WARN_PCT`, `COST_STOP_PCT` | 80, 95 | From warn, the brief shows budget used; from stop, only `COST_ESSENTIAL_MODES` (morning) runs |
| `RUN_TIMEOUT`, `RUN_TIMEOUT_WEEKLY`, `RUN_TIMEOUT_WORKLIST` | 1200, 3000, 900 s | Time limit per run kind |
| `RUN_LOCK_WAIT` | 1800 s | How long a run waits for another to finish before going ahead |
| `OUTLOOK_CHECK`, `OUTLOOK_RETRY_WAITS` | on, "30 90" | Check Outlook answers before the morning and weekly runs |
| `EOD` | on | End-of-day wrap-up on or off |
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
  weekly review runs it), `kit-wins report --from ... --to ...` for reviews.

## 8. Connectors

Kit reads outside systems through MCP servers you add to Claude Code (`claude mcp add ...`; see
Claude Code's docs). Then:

1. List each server in `memory/context/connector-guard.json` under `allowed_servers`, with the read
   tools in `allow_tools` and anything that writes in `deny_tools`.
2. Set each server's credential as an environment variable or Keychain entry; record only its
   **name** (optionally under `credential_env` in `connector-guard.json`). Never write a value into a
   file.
3. Run `kit-connect test`. It checks each server is allowed, that its credential variables are set
   (by name only), and Claude Code's own health check.
4. Optionally pick one cheap read-only tool per server under `probe_tools`, then
   `kit-connect test --read` makes one read call per server as the gateway agent, under the guard
   (a few cents each). The connector guard's audit log decides the result: a logged call with no
   error passes even if the run's own answer is cut short.
5. Check a filtered search returns a plausible count before you trust it. Some systems (ServiceNow
   among them) silently ignore a filter on a field name they don't recognise and return the whole
   table; a reference field can also hold a different type than its name suggests. Look up one
   record's fields first, then scope by the fields it actually has.

The health check (`doctor.py`) also warns about missing credential variables by name.

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
The SQL transport (`Transport: sql`, `sharing-db.json`) is tested on MySQL; PostgreSQL and SQL Server
are untested. Store the database password in a Keychain entry (`security add-generic-password -s
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
kit-update            # fetch GitHub and show new commits and files; changes nothing
kit-update --apply    # back up, move the clone onto GitHub's main, rerun the installer
kit-version --check   # installed version vs GitHub
```

`kit-update` stops if your clone has uncommitted work or commits GitHub doesn't have, except when
GitHub already applied a patch with the same files. After an update, the next brief adds "What
changed in Kit" once. Rerun `doctor.py --fix-agents` if agents changed.

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
| "Models: N agents don't match" | Run `kit-models apply`, then `--fix-agents` |
| "Scheduled X run: not loaded" | `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.$USER.kit.X.plist` |
| "Recent runs: ... run didn't finish" | Read that day's log. A later successful run of the same kind clears it. |
| A run "hit its time limit" (exit 142) | Raise `RUN_TIMEOUT_<MODE>` in the config, or trim the run |
| "waiting for another run to finish" in the log | The lock is working; a run that died leaves a lock that's cleared automatically |
| Calendar and mail marked stale, AppleEvent error -1712 | Outlook didn't answer; restart Outlook. `kit-outlook` retries before each run. |
| A tool "needed approval" in an unattended run | Add it to `ALLOW_TOOLS` or `ALLOW_TOOLS_WEEKLY` |
| "Connector credentials: missing by name" | Set the named environment variable; `kit-connect test` confirms |
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

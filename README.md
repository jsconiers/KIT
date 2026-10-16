# Kit

Kit is a personal assistant and chief of staff that lives in Claude Code. It's one agent
working for one person. It keeps notes on you and your work, a running to-do list for you and
for itself, a one-page status, lessons from its own mistakes, and your preferences, and it
directs your other AI agents (Claude Code subagents) for you.

It's named for KITT from Knight Rider: loyal, a little dry, and willing to warn the driver.

## Layout

Kit is organized so that nearly everything is shared across operating systems, and only the
thin OS-integration layer is platform-specific.

```
kit/                 The agent "brain" — 100% shared, no platform code:
                       KIT.md (who Kit is), QUEUE.md (to-do), STATUS.md,
                       memory/, lessons/, preferences/, agents/ (sub-agents).
shared/              Cross-platform Python + assets:
  kit_setup.py         install/activate/deactivate logic
  bin/todo             command-line to-do that shares QUEUE.md
  bin/kit-settings     how briefs reach you and which app to-dos sync with, work and personal
  bin/connector-guard  read-only guard and audit log for agents that reach outside systems
  bin/vsdx-finish      fills in title blocks and builds legends in Visio diagrams
  bin/kit-grammar      optional offline spelling and grammar pass (LanguageTool), skipped if absent
  bin/kit-drawio       editable draw.io files from a diagram spec or a PowerPoint diagram
  bin/kit-publish      writes selected records to an outbox for a team dashboard (off by default)
  bin/kit-audit        daily and weekly checks of the connector audit log, for the brief and dashboard
  team_dashboard.py    read-only team dashboard built from one or more outboxes
  templates/           HTML templates for both dashboards; copy one to ~/Claude/Agents/kit/templates/
                       to restyle it (your copy wins and survives reinstalls)
  kit_template.py      finds and fills the dashboard templates
  kit_records.py       record validator and credential checks used by kit-publish
  records/             shared record formats (JSON Schema) and their rules
  doctor.py            health check for the install, schedules, notes, secrets
  dashboard.py         one-page dashboard (to-do, briefs, health, runs)
  reminders_sync.py    two-way to-do sync (device backend is per-OS)
  protect_folder.py    keeps Kit out of personal notes inside work folders
  research/run_ta.py   TradingAgents runner
  mail/, calendar/     shared config schemas
  morning/             shared scheduled-run prompts + config.example
platform/
  mac/                 macOS integration:
    install.sh, uninstall.sh
    mail/kitmail.swift        Apple Mail tool (drafts only, no send)
    calendar/kitcal.swift     EventKit calendar tool (safe: skips excluded cals & events with attendees)
    morning/run.sh + *.plist  launchd scheduled runs (brief texted via Messages)
    research/kit-research
  windows/             Windows port — planned; see platform/windows/PORTING.md
install.sh             top-level dispatcher (→ platform/mac/install.sh on macOS)
install.ps1            top-level dispatcher (→ platform/windows/install.ps1 on Windows)
```

Everything installs into `~/Claude/Agents/kit`, with the package copied to
`~/Claude/Agents/kit/.install/` and the brain loaded into every Claude Code session through one
import line in `~/.claude/CLAUDE.md`.

## Install (macOS)

```bash
git clone https://github.com/<you>/KIT.git
cd KIT
KIT_OWNER=Alex bash install.sh
```

`KIT_OWNER` is the name Kit calls you; without it, Kit uses your account's first name. Then
start `claude`, run `/context` to confirm `KIT.md` loaded, and say "Kit, introduce yourself."

The installer asks how you want the morning brief delivered and which app your to-dos sync with
(see Settings below), and puts `todo` and `kit-settings` in `~/.local/bin`. The optional scheduled
runs (morning brief, post-open market read, weekly review) install as launchd jobs from
`platform/mac/morning/`. The market reads in the prompts call the author's own MCP server — edit
or remove those steps to fit your tools.

## Install (Windows)

Not yet implemented. The agent brain and the shared Python already run on Windows; the
integration layer (mail, calendar, reminders, scheduling, folder privacy) still needs a Windows
backend. See `platform/windows/PORTING.md` for the roadmap, then:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

## Settings

`kit-settings` chooses how the morning brief and weekly review reach you, and which app your to-dos
sync with. Run it with no arguments to see the current choices; the installer asks the same
questions once. Your answers go in `~/Claude/Agents/kit/.install/shared/morning/config`, which stays
on your computer (`shared/morning/config.example` documents every key).

```bash
kit-settings                                   # show the current choices
kit-settings delivery local                    # desktop notification (the default)
kit-settings delivery imessage                 # text to your phone (macOS)
kit-settings delivery outlook-drafts           # a draft saved in Outlook, never sent
kit-settings todos apple                       # Apple Reminders (macOS)
kit-settings todos outlook                     # Outlook Tasks (reaches your phone via Microsoft To Do)
kit-settings email you@example.com             # where Outlook drafts are addressed
kit-settings text +15551234567                 # where iMessage texts go
```

**Work and personal, separately.** A to-do tagged `[work]` (add one with `todo work Review the GDS
fri`) is a work item; everything else is personal. Each side can use its own channel and app, so
work stays inside Microsoft 365 while personal items come to your phone:

```bash
kit-settings delivery personal imessage
kit-settings delivery work outlook-drafts      # or local, if Outlook isn't set up on this computer
kit-settings todos personal apple
kit-settings todos work outlook
```

With a split, each run writes a personal-only and a work-only short text, and work channels never
get the full brief. iMessage, SMS, and Apple Reminders run outside Microsoft 365, so `kit-settings`
refuses them for work items unless you add `--force`. The Outlook channels need classic Outlook
running with your work account; Kit never starts Outlook and never sends mail. On Windows, run it as
`python %USERPROFILE%\Claude\Agents\kit\.install\shared\bin\kit-settings`; Windows uses Outlook
for to-dos.

## Kit's staff

`kit/agents/` holds Kit's staff, Claude Code subagents that Kit directs: a researcher, a
librarian, a curator, an IA writer and a GDS writer, a reviewer, a diagrammer, a scheduler, a
demand tracker, a connector gateway, an intake triager, a dependency mapper, a status reporter,
an implementation planner, a deck builder, a handoff agent, a meeting scribe, a standards
checker, a risk and compliance mapper, a cost estimator, a change board prep agent, a decision
recorder, a PMO estimator, an onboarding guide, and an auditor. They work
through Kit, apart from a few direct pairings listed in `memory/context/agents.md`. The gateway
is the agent meant to reach outside systems: `shared/bin/connector-guard` runs as a hook on it
to keep connectors read-only and record every request in an audit log.
Each reads a setup file in `memory/context/`, and `memory/context/agents.md` describes them all.

The installer copies the agents into `~/Claude/Agents/kit/agents/`. To make them available
in Claude Code, copy them into `~/.claude/agents/`:

```bash
python3 ~/Claude/Agents/kit/.install/shared/doctor.py --fix-agents
```

For the diagrammer, draw.io Desktop works well: its command line exports PNG, SVG, and PDF
without opening a window. JGraph's draw.io skill (`plugins/claude-code/skills/drawio` in
github.com/jgraph/drawio-mcp) can be copied into `~/.claude/skills/drawio/`. It fetches
reference files from GitHub, so keep local copies next to it for agents without web access.

## Optional: grammar checks

The reviewer runs an offline spelling and grammar pass when LanguageTool and Java are installed, and
skips it, saying so, when they aren't. Nothing else changes either way. On macOS:

```bash
brew install languagetool    # brings a Java runtime with it
python3 ~/Claude/Agents/kit/.install/shared/bin/kit-grammar --where
```

`kit-grammar` looks in Homebrew's folder, then `~/Claude/Agents/kit/tools/LanguageTool*`, and on
Windows in Program Files, AppData, and Scoop. Set `KIT_LANGUAGETOOL` to the folder holding
`languagetool-commandline.jar` if it's elsewhere. LanguageTool 6 and later needs Java 17 or later.
The health check reports whether it's available, and never counts its absence as a problem.

## Sharing with a team (preview)

Several Kits, one per architect, can share selected records for a team dashboard and shared
lessons. Turn it on in `memory/context/sharing.md`: set a Kit id (not your name), your role, and
the record types to publish. Nothing is shared until you do.

```bash
python3 ~/Claude/Agents/kit/.install/shared/bin/kit-publish --dry-run   # see what would be shared
python3 ~/Claude/Agents/kit/.install/shared/bin/kit-publish             # write records to the outbox
python3 ~/Claude/Agents/kit/.install/shared/team_dashboard.py --source <outbox> --source <teammate outbox> --open
```

Records are small JSON summaries, never document text, credentials, or personal notes. Lessons
are shared only when tagged `share: team`. Formats and rules: `shared/records/README.md`. Syncing
outboxes through a shared folder comes later; for now, copy them.

## Privacy

Kit's notes stay on your machine in a folder only you can read (POSIX `chmod 700` on macOS;
NTFS ACLs on Windows once implemented). Personal notes live in `memory/personal/` and don't
load on their own, and `protect_folder.py` keeps them out of work folders. Your settings,
including where Kit texts you, go in `shared/morning/config`, which git ignores.

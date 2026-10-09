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
                       memory/, lessons/, preferences/, sub-agents.
shared/              Cross-platform Python + assets:
  kit_setup.py         install/activate/deactivate logic
  bin/todo             command-line to-do that shares QUEUE.md
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

The optional scheduled runs (morning brief, post-open market read, weekly review) install as
launchd jobs from `platform/mac/morning/`; they text you via Messages and the first run asks for
permission to control Messages. The market reads in the prompts call the author's own MCP
server — edit or remove those steps to fit your tools.

## Install (Windows)

Not yet implemented. The agent brain and the shared Python already run on Windows; the
integration layer (mail, calendar, reminders, scheduling, folder privacy) still needs a Windows
backend. See `platform/windows/PORTING.md` for the roadmap, then:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

## Privacy

Kit's notes stay on your machine in a folder only you can read (POSIX `chmod 700` on macOS;
NTFS ACLs on Windows once implemented). Personal notes live in `memory/personal/` and don't
load on their own, and `protect_folder.py` keeps them out of work folders. Your settings,
including where Kit texts you, go in `shared/morning/config`, which git ignores.

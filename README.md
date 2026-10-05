# Kit

Kit is a personal assistant and chief of staff that lives in Claude Code on your Mac. It's one
agent working for one person. It keeps notes on you and your work, a running to-do list for you
and for itself, a one-page status, lessons from its own mistakes, and your preferences, and it
directs your other AI agents (Claude Code subagents) for you.

It's named for KITT from Knight Rider: loyal, a little dry, and willing to warn the driver.

## What's here

- `install.sh`, `uninstall.sh`, `kit_setup.py`: install Kit into `~/Claude/Agents/kit` and load
  it into every Claude Code session through one import line in `~/.claude/CLAUDE.md`.
- `kit/`: Kit's starting files. `KIT.md` says who Kit is and how it works; `QUEUE.md` is the
  to-do list; `STATUS.md` is the one-page status; plus folders for memory, lessons, and
  preferences.
- `bin/todo`: a command-line to-do list that shares `QUEUE.md` with Kit.
- `doctor.py`: a health check for the install, the schedules, the notes, and secrets.
- `dashboard.py`: a one-page dashboard of the to-do list, briefs, health, and runs.
- `reminders_sync.py`: keeps the to-do list in Apple Reminders, so it's on your phone.
- `protect_folder.py`: keeps Kit out of your personal notes inside work folders.
- `morning/`: scheduled runs (a morning brief, a post-open market read, and a weekly review)
  that text you through Messages.

## Install

```bash
git clone https://github.com/<you>/KIT.git
cd KIT
KIT_OWNER=Alex bash install.sh
```

`KIT_OWNER` is the name Kit calls you; without it, Kit uses your Mac account's first name.
Then start `claude`, run `/context` to check that `KIT.md` loaded, and say "Kit, introduce
yourself."

## Extras

To-do command, health check, dashboard, and Reminders sync:

```bash
mkdir -p ~/Claude/Agents/kit/.install/bin
cp bin/todo ~/Claude/Agents/kit/.install/bin/
cp doctor.py protect_folder.py dashboard.py reminders_sync.py ~/Claude/Agents/kit/.install/
ln -s ~/Claude/Agents/kit/.install/bin/todo ~/.local/bin/todo
python3 ~/Claude/Agents/kit/.install/doctor.py
```

Scheduled runs (macOS launchd):

```bash
mkdir -p ~/Claude/Agents/kit/.install/morning
cp morning/run.sh morning/prompt*.md ~/Claude/Agents/kit/.install/morning/
cp morning/config.example ~/Claude/Agents/kit/.install/morning/config   # then edit it
for job in morning open weekly sync; do
  sed -e "s|{{HOME}}|$HOME|g" -e "s|{{USER}}|$USER|g" morning/com.USER.kit.$job.plist.template \
    > ~/Library/LaunchAgents/com.$USER.kit.$job.plist
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.$USER.kit.$job.plist
done
```

The market reads in the prompts call the author's own traders-edge MCP server; edit or remove
those steps to fit your tools. The first text asks for permission to control Messages.

## Privacy

Kit's notes stay on your Mac in a folder only you can read. Personal notes live in
`memory/personal/` and don't load on their own, and `protect_folder.py` keeps them out of work
folders. Your settings, including where Kit texts you, go in `morning/config`, which git ignores.

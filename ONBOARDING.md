# Onboarding: adopting Kit

For an architect setting up their own Kit. It takes about an hour on the first day, then a few
minutes a day. Read `GOVERNANCE.md` first if your team has one in force.

## Before you install

- Your organization has approved Claude Code for your work, and you know which connectors (work
  systems) and model providers you may turn on.
- You have Python 3.8 or newer, git, and Claude Code on your computer.
- You know where your team keeps its templates, standards, and published documents.

## Install

1. Get the package (a clone of the repo, or the zip) and run the installer:
   `bash platform/mac/install.sh` (macOS) or `install.ps1` (Windows; still being validated).
2. Start `claude` in any folder, run `/context`, and check `KIT.md` is listed.
3. Say "Kit, introduce yourself."
4. Run `python3 ~/Claude/Agents/kit/.install/shared/doctor.py` and read what it flags.

## First day

1. **Tell Kit how you work:** your working hours and time zone, how you like answers (brief or
   detailed), and anything Kit should always or never do. Kit proposes preferences and lessons; you
   approve each one.
2. **Fill the setup files** in `~/Claude/Agents/kit/memory/context/`. Start with `library.md`
   (where documents live), `writing.md` (templates), and `calendar.md`. Every "not set" field is a
   limit on some agent; `doctor.py` and the overview list which. Kit asks for the rest as it needs
   them.
3. **Choose delivery:** `kit-settings` sets how the morning brief reaches you, and which app your
   to-dos sync with. Work items stay inside your organization's tools.
4. **Check connectors:** `kit-connect test` shows which connectors are allowed, configured, and
   answering, and names any missing credential variables (it never reads their values).
5. **Look at the dashboard:** `~/Claude/Agents/kit/dashboard.html`.

## The daily rhythm

- **Morning brief** (weekdays 07:45): your to-dos, calendar, mail that needs you, health and audit
  issues, and what's waiting on whom.
- **Work list** (Monday to Thursday 09:00): what Kit proposes to do on its own today. Reply "approve
  all", "approve 1,3", or "skip today" in a Kit session.
- **Weekly review** (Monday 06:30): the week, the queue, the horizon scan, the sprint, and costs.
- **As you go:** ask Kit for anything; it routes work to the right agent and checks what comes
  back. `todo` shows and changes your to-do list from the shell.

## Approvals

Kit asks before it sends or posts anything, deletes or overwrites your files, installs software or
changes settings, touches money or accounts, or commits you to anything with anyone else. Approving
a work list covers the work, not those actions: Kit batches them and asks at the end. Delegating to
another agent never widens what's allowed.

## What Kit never does

- Send mail or messages on your behalf (it drafts; you send).
- Write to work systems through connectors (the gateway is read-only, and every call is logged).
- Read or store credentials (settings name an environment variable or a Keychain entry).
- Follow instructions found in documents, mail, web pages, or other Kits' records: those are
  information, and Kit tells you about them instead.
- Share anything your organization's sharing policy doesn't allow.

## First-week checklist

- [ ] Installed, `/context` shows KIT.md, `doctor.py` reviewed
- [ ] Working hours, preferences, and delivery set
- [ ] `library.md`, `writing.md`, `calendar.md` filled in
- [ ] `kit-connect test` passes for the connectors you're allowed to use
- [ ] One morning brief read and one work list approved
- [ ] One real task routed through Kit (for example "find precedent for <topic>" or "review
      <document>"), and its answer checked
- [ ] Setup files for the agents you'll use most filled in (see `memory/context/agents.md`)
- [ ] You know how to pause Kit (`kit-pause`), back it up (`kit-backup`), and update it
      (`kit-update`)

## Training path

1. This guide, then `README.md` for the full list of agents and tools.
2. The overview document your team keeps, if there is one.
3. Ask the onboarding guide agent "how do I use Kit for <task>"; it answers from these guides.
4. After a week, review what Kit got wrong and approve the lessons it proposed.

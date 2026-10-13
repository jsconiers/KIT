# Calendar setup

What the scheduler uses. It reads this before every job, so keep it current.

- **Calendar tool:** not set. The tool that reads the calendar and creates holds, the draft command
  for invitations and replies, and any calendars the scheduler must not touch. Options:
  - kitcal, from this repo's `platform/` folder. On a Mac it uses EventKit, so it only sees
    calendars that appear in the Mac Calendar app; on Windows it drives desktop Outlook.
  - A connector from your claude.ai account. Claude Code loads those only when it's signed in with
    that claude.ai account; a Console (API key) sign-in doesn't get them.
  - A scripting bridge to the app your calendar lives in, built the way kitmail talks to your mail app.
- **Working hours and time zone:** not set.
- **Habits:** optional. Focus time, meeting-free blocks, buffers, and how far ahead to plan.

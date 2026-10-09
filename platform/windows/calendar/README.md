# kitcal (Windows)

Kit's calendar tool for Windows. It drives the **installed desktop Outlook** via
COM (`win32com.client` / pywin32), and is the Windows counterpart to the macOS
EventKit tool at `platform/mac/calendar/kitcal.swift`. The CLI, the JSON output,
and the safety guards are intended to match the Mac tool exactly.

> **UNTESTED on Windows.** This file was written on macOS, where pywin32 and
> Outlook do not exist, so it has not been executed. Validate it on a real
> Windows box with Outlook installed before relying on it. See **Manual test**.

## Dependency

```
pip install pywin32
```

Requirements:

- Windows with the **desktop Outlook** client installed and signed in (this is
  classic Outlook / Outlook for Microsoft 365 with MAPI — not "new Outlook" and
  not Outlook on the web, neither of which exposes the COM automation model).
- Python 3.8+.

pywin32 is a build dependency installed via `pip`, which the ICE policy permits
for project toolchains; pin the version the installer specifies if one is set,
otherwise install the latest pywin32 with no known advisories.

## How the installer exposes it as `kitcal`

On macOS the installer compiles `kitcal.swift` into `KitCal.app` and symlinks a
`kitcal` wrapper onto `PATH`. On Windows there is no app bundle or permission
prompt — COM runs as the logged-in user — so the Windows installer
(`platform/windows/install.ps1`, over the shared `kit_setup.py`) should instead:

1. Copy this folder into `.install/platform/windows/calendar/` alongside the
   rest of the scaffold (the shared setup already copies the full `platform/`
   payload into `.install/`).
2. Ensure pywin32 is present (`pip install pywin32`).
3. Drop a `kitcal.cmd` shim onto a directory on `PATH` (e.g.
   `%USERPROFILE%\.local\bin`, the same place the other shims live) that runs:

   ```bat
   @echo off
   python "%USERPROFILE%\Claude\Agents\kit\.install\platform\windows\calendar\kitcal.py" %*
   ```

   so that `kitcal events`, `kitcal free`, etc. work from any shell exactly as on
   the Mac.

The config is shared and read from the same logical location as on macOS:
`%USERPROFILE%\Claude\Agents\kit\.install\calendar\config.json`
(`{"default": "...", "exclude": ["..."]}`). See `shared/calendar/config.example.json`.

## Subcommands

Identical surface to the Mac tool:

```
kitcal calendars
kitcal events [--from DATE] [--to DATE] [--cal NAME ...]
kitcal free [--date DATE] [--from HH:MM] [--to HH:MM]
kitcal add --title T (--start "DATE HH:MM" --end "DATE HH:MM" | --all-day --date DATE)
           [--cal NAME] [--location L] [--notes N] [--alert MINUTES]
kitcal move --id ID --start "DATE HH:MM" [--end "DATE HH:MM"] [--span this|future]
kitcal update --id ID [--title T] [--location L] [--notes N] [--cal NAME] [--span this|future]
kitcal delete --id ID [--span this|future]
```

`DATE` is `YYYY-MM-DD`, `today`, or `tomorrow`. Output is pretty-printed JSON
with sorted keys (matching the Swift tool). A calendar is referenced as
`Name` or `Name|Account`; a bare name that matches more than one calendar is
refused with the list of candidates.

## Safety guards (same guarantees as macOS)

- **Exclude list.** Calendars/accounts listed under `"exclude"` in the config
  are never read or written. Matching is case-insensitive on both the calendar
  name and the account (Outlook Store display name).
- **Attendee events are never modified or deleted.** Any event whose
  `Recipients` list is non-empty is refused, so kitcal can never send a meeting
  update/cancellation. (We also never add attendees, and Outlook does not send
  on `Save` for an attendee-less appointment.)
- **Read-only calendars are refused for writes.** Writability is read from the
  folder's MAPI `PR_ACCESS` rights via `PropertyAccessor`. If the property is
  readable and lacks create/modify rights, the write is refused; if it can't be
  read, kitcal lets Outlook's own `Save` enforce it.
- **Default calendar.** `add`/`update --cal` fall back to the config `default`
  when no `--cal` is given.

## What is fully replicated vs. TODO

**Fully replicated from the Mac tool:**

- All seven subcommands, their flags, and the JSON shapes
  (`calendars`, `events`, `free`, and the `added`/`moved`/`updated`/`deleted`
  wrappers).
- Date/time parsing (`today`/`tomorrow`/`YYYY-MM-DD`, `"YYYY-MM-DD HH:MM"`) in
  local time, and the `events` range semantics (`--to` is inclusive; internally
  `+1 day`, default window is just today).
- Free/busy: busy = non-all-day events whose `BusyStatus` is not *free*, clamped
  to the window, sorted, overlaps merged, open gaps emitted — same algorithm as
  the Swift tool.
- The composite `id` = `<EntryID>|<start>`, and `find_event` re-locating an event
  by EntryID + start-within-60s over a -1d/+2d window.
- Attendee guard, read-only guard, exclude list, default-calendar fallback, and
  the "ambiguous calendar name" refusal.
- Recurring **single-occurrence** edits (`--span this`, the default): editing or
  deleting the occurrence object creates an Outlook exception, mirroring
  EventKit's `.thisEvent`.

**Safe subset / TODO (left clearly marked in the code):**

- **`move`/`update` with `--span future` on a recurring event is refused.**
  Outlook COM has no clean "this and future" edit for arbitrary field/time
  changes (it would require splitting the series into two masters). The code
  refuses with a clear message pointing the user to `--span this` or to Outlook.
  TODO: implement the series split once it can be tested on Windows.
- **`delete --span future` on a recurring event truncates the series** by setting
  the master's `PatternEndDate` to the day before the occurrence (or deleting the
  master if it's the first occurrence). This is the closest COM equivalent of
  EventKit's `.futureEvents` delete, but the `PatternEndDate` off-by-one across
  daily/weekly/monthly patterns is marked TODO to validate on a real series.

## Assumptions

- "Calendar" == any Outlook folder whose `DefaultItemType` is appointment, found
  by walking every store (account). The "account" portion of a ref is the Store
  `DisplayName`, which is the closest analogue to EventKit's source title.
- Recurring occurrences share the master's `EntryID` (like EventKit's shared
  identifier), so the start time in the id disambiguates an occurrence.
- Event querying uses `Items.Sort("[Start]")` + `IncludeRecurrences = True` +
  iterate-until-`Start`-passes-window, rather than `Items.Restrict(...)`, to
  avoid Outlook's locale-dependent date-filter string format. It is correct but
  can be slower on very large calendars.
- All times are handled in local time (matching the Mac tool's
  `TimeZone.current`); pywin32's tz-aware datetimes are normalised to naive local.
- All-day events are written as a proper one-day span (`AllDayEvent = True`,
  `End = Start + 1 day`); their displayed `end` is the date Outlook stores, which
  may read as the exclusive next day for pre-existing all-day events.

## Manual test

Run these on a Windows machine with Outlook installed and signed in. Replace the
calendar name to match your profile.

1. **Dependency + connection**

   ```
   pip install pywin32
   python kitcal.py calendars
   ```

   Expect a JSON array of `{ "ref": "Name|Account", "writable": true/false,
   "default": true/false }`. Confirm your real calendars appear, that any name in
   the config `exclude` list is absent, and that `default` is `true` for the
   configured default calendar. With Outlook closed/unavailable, expect a clear
   "Couldn't reach Outlook" error (exit 1); with pywin32 missing, expect the
   "needs pywin32" error.

2. **List events**

   ```
   python kitcal.py events --from today --to tomorrow
   python kitcal.py events --from 2026-10-12 --cal "Calendar"
   ```

   Confirm events are sorted by start, recurring events are expanded into
   occurrences within the range, and each has an `id` of the form
   `<EntryID>|YYYY-MM-DD HH:MM`.

3. **Free/busy**

   ```
   python kitcal.py free --date today
   python kitcal.py free --date today --from 09:00 --to 17:00
   ```

   Create two overlapping events in Outlook, re-run, and confirm they merge into
   one busy interval and that the `free` gaps complement the `busy` intervals
   within the window. Mark an event as "Free" in Outlook and confirm it does not
   appear as busy.

4. **Add (round-trip)**

   ```
   python kitcal.py add --title "Kit test" --start "2026-10-12 14:00" --end "2026-10-12 14:30" --cal "Calendar" --location "Desk" --notes "created by kitcal" --alert 10
   python kitcal.py add --title "Kit all-day" --all-day --date 2026-10-13 --cal "Calendar"
   ```

   Confirm both appear in Outlook with the right times/reminder, then verify
   `events` lists them. Note the `id` returned under `"added"`.

5. **Move / update**

   ```
   python kitcal.py move --id "<id from step 4>" --start "2026-10-12 15:00"
   python kitcal.py update --id "<id>" --title "Kit test 2" --location "Room B"
   ```

   Confirm the change in Outlook. The duration should be preserved on `move` when
   `--end` is omitted.

6. **Delete**

   ```
   python kitcal.py delete --id "<id>"
   ```

   Confirm the event is gone from Outlook and the JSON echoes the deleted event.

7. **Safety guards**

   - Try `move`/`update`/`delete` against an event that has attendees (a real
     meeting invite) and confirm it is refused with the attendee message, and
     that **no** meeting update is sent.
   - Put a calendar name in the config `exclude` list and confirm it never shows
     in `calendars`/`events` and is refused as a `--cal` target.
   - Target a read-only/subscribed calendar for `add` and confirm the read-only
     refusal (or, if `PR_ACCESS` can't be read, that Outlook's own save error is
     surfaced).

8. **Recurrence spans**

   - On a recurring event, `delete --id <occurrence id> --span this` should remove
     only that occurrence (an exception), leaving the rest of the series.
   - `delete --id <occurrence id> --span future` should remove that occurrence and
     all later ones (series truncated). **Verify the boundary** against daily,
     weekly, and monthly series.
   - `move`/`update ... --span future` on a recurring event should be refused with
     the "not supported through Outlook COM yet" message.

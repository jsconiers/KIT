# kitmail (Windows)

Kit's mail tool for Windows. It drives the **installed desktop Outlook client** over COM
(via `win32com.client` / pywin32) and mirrors the macOS tool
(`platform/mac/mail/kitmail.swift`) exactly: same subcommands, same flags, same JSON output.

> **UNTESTED on Windows** -- this was written on a Mac with no Outlook/pywin32 available.
> Validate on a real Windows box with Outlook installed before relying on it.

## Safety guarantees (identical to the Mac tool)

- Accounts listed under `"exclude"` in the config are **never read**.
- There is **no send command** and **no `.Send()` call** anywhere in the code. `draft`
  creates the mail and calls `.Display()`, opening it in an Outlook window for the owner to
  review and send himself.

## Dependency

```
pip install pywin32
```

pywin32 provides `win32com.client` (the COM bridge) and `pythoncom`. Python 3.8+.
If pywin32 is missing, or Outlook is not installed/configured, `kitmail` exits with a clear
error instead of a traceback.

> Per work policy, `pip install` of a project dependency is allowed, but do not install
> "latest" blindly -- pin the version your environment has standardized on, or the latest
> with no known advisories.

## Commands (mirror of the Swift tool)

```
kitmail accounts
kitmail inbox [--hours 24] [--unread] [--limit 50]
kitmail read --id ID
kitmail draft --to ADDRESS [--to ADDRESS ...] --subject S (--body TEXT | --body-file PATH) [--from ADDRESS]
```

- `accounts` -- JSON array of `{name, emails, enabled}`, excluding configured accounts.
- `inbox` -- JSON array of `{id, account, from, subject, received, read, flagged}` across all
  (non-excluded) account inboxes, newest first, within `--hours` (default 24), optionally
  `--unread` only, capped at `--limit` (default 50). `id` is `"<account name>|<EntryID>"`.
- `read --id ID` -- JSON `{from, to, subject, received, body}` (body truncated to 8000 chars).
  Refuses if the account is on the exclude-list.
- `draft` -- opens a draft window and prints `{opened, to, subject}`. Never sends.

`received` timestamps use `YYYY-MM-DD HH:MM`, matching the Mac tool.

## Config

Same relative location and schema as macOS, under the Windows home dir:

```
%USERPROFILE%\Claude\Agents\kit\.install\mail\config.json
```

```json
{ "exclude": ["account name or address"] }
```

An entry matches an account by its display name **or** any of its email addresses
(case-insensitive). See `shared/mail/config.example.json`.

## How the installer should expose it as `kitmail`

`kitmail.py` is a plain script; it needs to be callable as `kitmail` on the user's PATH.
Recommended approach for `platform/windows/install.ps1` (to be wired up there):

1. Copy the Kit payload into `%USERPROFILE%\Claude\Agents\kit\.install\` (as the shared
   `kit_setup.py` scaffold already does), so the tool lives at
   `...\.install\platform\windows\mail\kitmail.py`.
2. Create a `kitmail.cmd` shim in a directory that is on the user's PATH
   (e.g. `%USERPROFILE%\.local\bin`, the same convention the Mac installer uses, or a
   dedicated `%USERPROFILE%\Claude\Agents\kit\bin`). The shim forwards all args to Python:

   ```bat
   @echo off
   python "%USERPROFILE%\Claude\Agents\kit\.install\platform\windows\mail\kitmail.py" %*
   ```

   Use `py -3` instead of `python` if the launcher is the standardized entry point on the box.

3. Ensure that shim directory is on PATH (the installer can add it via
   `[Environment]::SetEnvironmentVariable("Path", ..., "User")`).

PowerShell snippet the installer can adapt:

```powershell
$binDir = Join-Path $env:USERPROFILE ".local\bin"
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
$target = Join-Path $env:USERPROFILE ".install\platform\windows\mail\kitmail.py" `
  -Resolve -ErrorAction SilentlyContinue
$shim = Join-Path $binDir "kitmail.cmd"
Set-Content -Path $shim -Encoding ASCII -Value @"
@echo off
python "%USERPROFILE%\Claude\Agents\kit\.install\platform\windows\mail\kitmail.py" %*
"@
# add `$binDir` to the user PATH if it isn't already present
```

## Manual test

Run these on a Windows machine with Outlook installed, configured, and at least one message
in an inbox.

1. **Install the dependency**
   ```
   pip install pywin32
   ```

2. **Graceful degradation (no Outlook / no pywin32)**
   - Temporarily rename or uninstall pywin32 and run `python kitmail.py accounts`.
     Expect: a one-line error telling you to `pip install pywin32`, exit code 1 -- not a
     traceback.
   - With pywin32 present but Outlook closed/unconfigured, expect a clear
     "Could not connect to Outlook..." error.

3. **List accounts**
   ```
   python kitmail.py accounts
   ```
   Expect a JSON array of your Outlook accounts with `name`, `emails`, `enabled`.

4. **Exclude-list**
   - Create `%USERPROFILE%\Claude\Agents\kit\.install\mail\config.json` with
     `{ "exclude": ["<one of your account names or addresses>"] }`.
   - Re-run `accounts`; confirm that account is gone from the output.
   - Run `inbox` and confirm no messages from the excluded account appear.

5. **Inbox**
   ```
   python kitmail.py inbox --hours 72 --limit 10
   python kitmail.py inbox --unread
   ```
   Expect newest-first JSON with `id`, `account`, `from`, `subject`, `received`
   (`YYYY-MM-DD HH:MM`), `read`, `flagged`. Copy an `id` for the next step.

6. **Read a message**
   ```
   python kitmail.py read --id "Account Name|<EntryID>"
   ```
   Expect `{from, to, subject, received, body}`; body truncated at 8000 chars.
   Confirm that reading an id whose account is excluded prints "That account is off-limits."

7. **Draft (NEVER sends)**
   ```
   python kitmail.py draft --to you@example.com --subject "Kit test" --body "hello"
   python kitmail.py draft --to a@example.com --to b@example.com --subject "Two" --body-file msg.txt --from you@example.com
   ```
   Expect an Outlook compose window to **open** with the recipients, subject, and body
   filled in, and the command to print `{"opened":true,...}`. **Nothing is sent** -- you
   close or send it yourself. Confirm the source has no `.Send()` call:
   ```
   findstr /i ".Send(" kitmail.py
   ```
   should return nothing.

8. **Shim on PATH** (after the installer wires it up)
   ```
   kitmail accounts
   ```
   should work from any directory.

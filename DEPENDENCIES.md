# Kit dependencies

What Kit, its shared tools, and each agent on its staff need to work, on macOS and Windows, and
what happens when something is missing. Paths use `~` for your home folder. Setup files are in
`~/Claude/Agents/kit/memory/context/` once Kit is installed (templates in `kit/memory/context/`).

Support levels used below:

- **Supported**: built and used on that platform.
- **Untested adapter**: an adapter exists for that platform but hasn't been run on it yet.
- **Not supported**: no adapter; the feature is skipped or unavailable.
- **Same code**: pure Python or a Claude Code feature with no platform-specific part; expected
  to work, but only exercised on macOS so far.

## 1. Platform requirements

### Both platforms

| Requirement | Why | Notes |
|---|---|---|
| Claude Code (`claude` on the PATH) | Kit and its staff run inside it; subagents, hooks, skills, and MCP connectors are Claude Code features | The installer warns but continues if `claude` isn't on the PATH yet |
| Python 3.8 or newer | The installer (`kit_setup.py`), every shared tool, and the connector guard hook | Standard library only, except the optional extras in section 4 |
| git | Kit's private local history (`~/Claude/Agents/kit/.git`), `protect_folder.py` (adds its file to a repo's ignore list), the health check's history age | Kit's own repo must never get a remote |
| A Claude Code account with subagent support | The 30 agents in `kit/agents/` | Copy them into `~/.claude/agents/` with `doctor.py --fix-agents` |

### Kit's command-line tools

| Tool | Needs | Platforms | If missing or failing |
|---|---|---|---|
| `kit-pause` | Python 3.8 | Same code; `--hard` is macOS launchd only (Windows: disable the tasks in Task Scheduler) | No kill switch; stop jobs by hand |
| `kit-backup` | Python 3.8, git | Same code; permissions set on macOS only | No backups; BACKUP_DIR unset means a folder next to Kit, which doesn't survive a lost computer |
| `kit-retention` | Python 3.8 | Same code | Everything is kept (the default anyway) |
| `kit-outlook` | `osascript`, `pgrep`, classic Outlook | macOS; reports "skipped" elsewhere | run.sh skips the check; calendar and mail fail the old way |
| `kit-team` | Python 3.8 (sqlite3 is in the standard library) | Same code; owner-only permissions on macOS only | No team view; kit-publish still writes records |
| `kit-precedent` | Python 3.8 | Same code | The precedent finder searches the indexes by hand |
| `kit-cost` | Python 3.8; Claude Code with `--output-format json` | Same code; run.sh guard is macOS (the Windows runner doesn't record cost yet) | No ledger or budget guard; runs go ahead as before |
| `kit-queue` | Python 3.8 | Same code | No hygiene report; the brief falls back to listing items untouched for seven days |

### macOS

| Requirement | Used by | Notes |
|---|---|---|
| `python3` (Xcode Command Line Tools or a package-manager Python) | Installer, all tools | `install.sh` stops if it's missing or older than 3.8 and suggests `xcode-select --install` |
| `osascript` (built in) | Reminders sync (JXA), Messages delivery of the morning brief | First run asks for Automation permission |
| `launchctl` (built in) | Scheduled runs (morning, open, weekly, sync) from the plist templates | Optional; `doctor.py` checks each job only if its plist is installed |
| `swiftc` (Xcode Command Line Tools) | Building `kitmail` (Apple Mail) and `kitcal` (EventKit) from `platform/mac/*/build.sh` | Optional; only for the Apple Mail and Calendar tools |
| `chmod` (built in) | Owner-only folder privacy | Applied by the installer |

### Windows

| Requirement | Used by | Notes |
|---|---|---|
| Python 3.8+ through the `py -3` launcher or `python` | Installer and all tools | `install.ps1` prefers `py -3`. Agent hook commands call `python3`, which many Windows machines lack (see the gaps in section 6) |
| PowerShell 5.1 or 7 | `install.ps1`, `run.ps1`, task registration | Run with `-ExecutionPolicy Bypass -File` for the installer only |
| `icacls` (built in) | Owner-only NTFS permissions on Kit's folder | Applied by `install.ps1` |
| Task Scheduler (built in) | Scheduled runs (`register-tasks.ps1`) | Untested adapter |
| Classic desktop Outlook | Mail, calendar, and reminders adapters (COM) | The new Outlook and Outlook on the web have no COM interface. `install.ps1` warns when it isn't registered |
| `pywin32` | Mail, calendar, and reminders adapters (`win32com.client`) | Install with pip, pinned to a version with no known advisories |
| BurntToast PowerShell module | Toast delivery of the morning brief | Optional; without it, delivery falls back to a file |

## 2. Shared tools

| Tool | What it needs | Optional? | macOS | Windows |
|---|---|---|---|---|
| `shared/kit_setup.py` (install, activate, deactivate) | Python 3.8+ stdlib | Required | Supported | Untested adapter (called by `install.ps1`) |
| `shared/doctor.py` (health check) | Python stdlib; `git`; `launchctl` for job checks; `claude` for `--servers`; `kit-grammar` for the grammar line | Recommended | Supported | Partly: job checks use `launchctl` and `os.getuid`, so they report a crashed check on Windows |
| `shared/dashboard.py` | Python stdlib; `open`, `xdg-open`, or `os.startfile` to open the page | Optional | Supported | Same code (uses `os.startfile`) |
| `shared/bin/todo` | Python stdlib; rebuilds the dashboard | Recommended | Supported | Same code |
| `shared/reminders_sync.py` | `osascript` and Apple Reminders | Optional | Supported | Not supported; Windows uses `platform/windows/reminders/reminders_sync_win.py` (Outlook Tasks over COM, untested adapter) |
| `shared/protect_folder.py` | Python stdlib; `git` when the folder is a repo | Recommended for work folders | Supported | Same code |
| `shared/bin/connector-guard` | Python stdlib; runs as a Claude Code hook | Required for agents that reach outside systems | Supported | Untested: hook commands call `python3` and `$HOME` |
| `shared/bin/vsdx-finish` | Python stdlib; a `.vsdx` made from a stencil with title-block and legend masters; settings in `vsdx-finish.json` | Optional (diagrammer) | Supported | Same code; pass `--author`, since the default uses the POSIX `id` command |
| `shared/bin/kit-drawio` | Python stdlib for JSON specs; `python-pptx` only for PowerPoint input | Optional (diagrammer) | Supported | Same code |
| `shared/bin/kit-grammar` | LanguageTool (folder with `languagetool-commandline.jar`) and Java (17+ for LanguageTool 6+); `pdftotext` for PDFs | Optional (reviewer) | Supported | Same code (looks in Program Files, AppData, and Scoop) |
| `shared/bin/kit-publish` | Python stdlib; `kit_records.py`; `sharing.md` settings | Optional (off until a Kit id and record types are set) | Supported | Same code |
| `shared/team_dashboard.py` | Python stdlib; `kit_records.py`; one or more outbox folders | Optional | Supported | Same code |
| `shared/kit_records.py` | Python stdlib; `shared/records/schema/` | Library for the two above | Supported | Same code |
| `shared/research/run_ta.py`, `platform/mac/research/kit-research` | An external TradingAgents checkout run with `uv`, and an API key in that project's own environment | Optional, author-specific | Supported | Not supported |
| Mail tool | macOS: `kitmail.swift` (Apple Mail, built with `swiftc`). Windows: `kitmail.py` (classic Outlook over COM, `pywin32`) | Optional; the scheduler and meeting scribe use whatever mail command their setup files name | Supported (Apple Mail) | Untested adapter |
| Calendar tool | macOS: `kitcal.swift` (EventKit). Windows: `kitcal.py` (classic Outlook over COM) | Optional; the scheduler works from Kit's brief without one | Supported (EventKit) | Untested adapter |
| Scheduled runs | macOS: `run.sh` + launchd plists, Messages for delivery. Windows: `run.ps1` + Task Scheduler, toast or file delivery | Optional | Supported | Untested adapter |

A mail or calendar that lives only in a desktop client the macOS tools don't cover (for example,
classic Outlook for Mac, which doesn't sync to Apple Calendar) needs its own local tool; name it in
`calendar.md` and `meetings.md`.

## 3. Agents

Every agent needs Claude Code, its setup file(s), and Kit's install at `~/Claude/Agents/kit`. Most
agents write into the **library root** named in `library.md`, so that folder must exist and be
writable. "Requests" means the agent asks Kit to route the need to another agent.

Tools are from each agent's frontmatter. "All except ..." means every tool Claude Code offers the
session, including MCP connectors, minus the ones listed.

### gateway

| | |
|---|---|
| Setup | `connectors.md`, `connector-guard.json` |
| Tools | All except Write, Edit, NotebookEdit, Bash, WebSearch, WebFetch, Agent, SendMessage, Skill (so: read tools and MCP connectors) |
| Hooks | `connector-guard` pre, post, and stop on every `mcp__*` call |
| Skills | None |
| Outside systems | The connectors `connectors.md` lists (service management, issue tracker, wiki), read-only, each with its own credential |
| Commands | `python3` (for the hook) |
| Other agents | None; answers Kit and the direct callers `connectors.md` names |
| If missing | Either setup file missing: stops. Connector not listed or not read-only: the guard denies the call. Sign-in fails: stops after the first failure and reports it |

### librarian

| | |
|---|---|
| Setup | `library.md` |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Skills | Document skills (pdf, docx, pptx, xlsx) to read Office and PDF files |
| Outside systems | Published libraries, reached only the way `library.md` says (for example a synced folder) |
| Commands | None required |
| Other agents | None; answers Kit and the curator |
| Optional | A synced copy of each published library |
| If missing | `library.md` missing or incomplete: stops. A published library unreachable: reports what's missing and doesn't work around it |

### curator

| | |
|---|---|
| Setup | `library.md`, `knowledge.md` |
| Tools | Read, Glob, Grep, Write, Edit, Agent, SendMessage, Skill |
| Skills | Document skills, as needed |
| Outside systems | None |
| Other agents | Librarian (direct) |
| If missing | Either setup file missing: stops. No librarian: reads the catalog itself and lists what it couldn't check |

### researcher

| | |
|---|---|
| Setup | None |
| Tools | Read, Glob, Grep, WebSearch, WebFetch |
| Skills | None |
| Outside systems | The public web |
| Other agents | Librarian and curator, through Kit (Requests) |
| If missing | No web access: answers from what Kit supplies and says so |

### ia-writer and gds-writer

| | |
|---|---|
| Setup | `writing.md`, `library.md`; the review-lessons file `writing.md` names |
| Tools | All except WebSearch, WebFetch |
| Skills | The style and brand skills `writing.md` names; docx |
| Outside systems | None |
| Commands | The skills Python (`~/.claude/skills/.venv`) for the docx skill's scripts |
| Other agents | Each other (direct, two rounds at most); the GDS writer also answers the implementation planner; librarian, curator, researcher, reviewer, and diagrammer through Kit |
| Optional | An organization-specific document generator, only if `writing.md` names one |
| If missing | `writing.md` incomplete: reports what's missing. No template: can't follow the template. No review-lessons file: says it doesn't exist yet. Without the docx skill's dependencies: can't build `.docx` files |

### reviewer

| | |
|---|---|
| Setup | `writing.md`, `library.md`; the review-lessons file |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Skills | The QA skill and style skills `writing.md` names |
| Commands | The QA skill's script with the skills Python; `kit-grammar` |
| Other agents | Librarian, curator, and the writers through Kit |
| Optional | LanguageTool + Java (grammar pass); Poppler (`pdftotext`) for PDFs; a browser for auth-gated links |
| If missing | QA skill missing: skips the scan and says so; never installs anything. LanguageTool or Java missing: `kit-grammar` prints `skipped:` and the review carries on |

### diagrammer

| | |
|---|---|
| Setup | `diagrams.md`, `library.md`; optional `drawio-styles.json`, `vsdx-finish.json` |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Skills | draw.io skill (with local reference copies) |
| Commands | `kit-drawio`, `vsdx-finish`; the draw.io desktop CLI for PNG/SVG export; any Mermaid-to-Visio converter `diagrams.md` names |
| Other agents | None directly |
| Optional | draw.io desktop; Visio or OmniGraffle to check the source of record; the team's stencils |
| If missing | `kit-drawio` not installed: skips the `.drawio` copy and says so. No draw.io CLI: no rendered previews. No Visio/OmniGraffle: can't verify the source file; says so |

### deck-builder

| | |
|---|---|
| Setup | `writing.md`, `library.md` |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Skills | pptx; the brand skill `writing.md` names |
| Commands | The skills Python with `python-pptx` |
| Other agents | Diagrammer (images) and librarian through Kit |
| Optional | LibreOffice for slide previews; `pptxgenjs` (Node) for decks without a template |
| If missing | No deck template: plain structure. No LibreOffice: no previews; reads the deck back with python-pptx and says previews weren't available. Missing diagram: labeled placeholder |

### scheduler

| | |
|---|---|
| Setup | `calendar.md` |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Commands | The calendar and mail commands `calendar.md` names (read and draft only) |
| Other agents | Librarian through Kit |
| If missing | No calendar tool: says so and works only from Kit's brief. Mail client not running: reports it and doesn't launch it |

### demand-tracker

| | |
|---|---|
| Setup | `demands.md`, `library.md` |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage (no connector-guard hook today) |
| Outside systems | Service-management and issue-tracker connectors, read-only, when `demands.md` lists them |
| Commands | Mail search command, as a fallback source |
| Other agents | Librarian through Kit |
| If missing | Connectors not ready: uses mail, folder names, the catalog, and Kit's brief, and says which sources it used |

### intake-triager

| | |
|---|---|
| Setup | `intake.md`, `connectors.md`, `library.md` |
| Tools | All except WebSearch, WebFetch; connector-guard hooks on `mcp__*` |
| Skills | xlsx (if the checklist is a spreadsheet) |
| Outside systems | Service-management records and configuration records, through the gateway (or directly, guarded) |
| Commands | The skills Python (`openpyxl`) to read a spreadsheet checklist; mail search as a fallback |
| Other agents | Gateway (direct); librarian and curator through Kit |
| If missing | `intake.md` incomplete: says what's missing and continues. No record: works from Kit's brief and says why |

### dependency-mapper

| | |
|---|---|
| Setup | `connectors.md`, `library.md`, `diagrams.md` |
| Tools | All except WebSearch, WebFetch; connector-guard hooks on `mcp__*` |
| Skills | The connectivity-map skill `connectors.md` names, if any |
| Outside systems | Configuration-management records, through the gateway (or directly, guarded) |
| Other agents | Gateway (direct); librarian, curator, and diagrammer through Kit |
| Optional | Connectivity exports Kit provides |
| If missing | Connectivity-map skill not installed: says so and continues. No configuration records: only what documents and exports say, with the gaps listed |

### status-reporter

| | |
|---|---|
| Setup | `status.md`, `connectors.md`, `library.md` |
| Tools | All except WebSearch, WebFetch; connector-guard hooks on `mcp__*` |
| Outside systems | Issue tracker, service management, and wiki, through the gateway |
| Other agents | Gateway (direct); others through Kit |
| If missing | Connectors not ready: reports from the library (catalog, log, demand register, minutes) and names the single-source risk |

### meeting-scribe

| | |
|---|---|
| Setup | `meetings.md`, `library.md` |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Skills | docx, pptx (to read notes) |
| Commands | The mail search and draft commands `meetings.md` names |
| Other agents | None directly; Kit has the librarian and curator file the output |
| If missing | No mail tool: uses the inbox folder and Kit's brief only |

### handoff

| | |
|---|---|
| Setup | `library.md`, `knowledge.md` |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Other agents | Any, through Kit (for example a fresh status report) |
| If missing | Missing register, minutes, or status reports: notes the gap in the brief |

### implementation-planner

| | |
|---|---|
| Setup | `writing.md`, `library.md` |
| Tools | All except WebSearch, WebFetch |
| Skills | The skills `writing.md` names; docx |
| Other agents | GDS writer (direct, one way); dependency mapper, reviewer, librarian, and curator through Kit |
| If missing | No change-request template: plain structure, and says so |

### change-board-prep

| | |
|---|---|
| Setup | `changeboard.md`, `writing.md`, `library.md` |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Skills | The skills `writing.md` names |
| Other agents | Implementation planner, deck builder, writers through Kit |
| If missing | `changeboard.md` "not set": plain structure, reasoned risk rating without a matrix, missing items listed |

### cost-estimator

| | |
|---|---|
| Setup | `costs.md`, `library.md` |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Skills | xlsx |
| Commands | The skills Python (`openpyxl`) |
| Other agents | Writers, PMO estimator, librarian through Kit |
| If missing | `costs.md` "not set": every price marked assumed; no contingency line without a rule |

### decision-recorder

| | |
|---|---|
| Setup | `decisions.md`, `library.md` |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Skills | docx, pptx (to read sources) |
| If missing | Either setup file missing: stops. No template: uses its default ADR layout |

### pmo-estimator

| | |
|---|---|
| Setup | `estimating.md`, `library.md` |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Skills | docx, xlsx, pptx (to read past projects) |
| Outside systems | Issue-tracker work logs, through Kit and the gateway |
| If missing | No actuals or comparables: says there are too few and widens the range. No phase model: default phases |

### onboarding-guide

| | |
|---|---|
| Setup | `onboarding.md`, `library.md`, `knowledge.md` |
| Tools | Read, Glob, Grep (read-only, saves nothing) |
| If missing | `onboarding.md` missing: stops |

### standards-checker

| | |
|---|---|
| Setup | `standards.md`, `library.md` |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Skills | Document skills (to read the design) |
| Other agents | Librarian and curator through Kit |
| If missing | `standards.md` "not set": checks only what Kit's brief supplies and lists what's missing |

### risk-compliance-mapper

| | |
|---|---|
| Setup | `compliance.md`, `writing.md`, `library.md` |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Skills | The skills `writing.md` names |
| Outside systems | Records (for example vendor risk), through Kit and the gateway |
| If missing | `compliance.md` "not set": maps only to what the brief supplies and lists what's missing |

### auditor

| | |
|---|---|
| Setup | `audit.md`, `connectors.md`, `connector-guard.json`, `library.md` |
| Tools | Read, Glob, Grep, Bash, Write, Edit (no web, cannot start or message other agents, no connector calls) |
| Skills | None |
| Outside systems | None. Reads the connector audit log in the library's audit folder |
| Commands | `python3` with `shared/bin/kit-audit` (`--daily`, `--weekly`) |
| Other agents | None; reports to Kit, and the weekly review asks it for the weekly audit |
| If missing | No audit log: reports "no audit logs" as a warning. Guard settings missing: a critical finding. `kit-audit` missing: says so and reviews the log by hand |

### poc-lead

| | |
|---|---|
| Setup | `poc.md`, `library.md`; `standards.md` for the security baseline |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Skills | docx, pptx, xlsx, pdf (to read sources and vendor material) |
| Templates | `templates/poc-charter-template.md`, `poc-test-plan-template.md`, `poc-scorecard-template.md` |
| Other agents | Meeting scribe (vendor claims to verify), librarian, curator, decision recorder, IA writer, all through Kit |
| If missing | `poc.md` missing or approvers and NDA owner "not set": drafts only, marked "approvers not set". No templates: uses its default layout. Vendor POC without a confirmed NDA: stops before the test plan |

### training-lead

| | |
|---|---|
| Setup | `training.md`, `library.md`; `labs.md` when a plan uses labs |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Skills | docx, pptx, xlsx, pdf (to read sources) |
| Other agents | Researcher (outside material), lab planner (lab steps), deck builder (slides), scheduler (study blocks), librarian, all through Kit |
| If missing | `training.md` missing: plans for {{OWNER}} only, no team view. No learning platform: plans kept in the library |

### future-tech-planner

| | |
|---|---|
| Setup | `future-tech.md`, `library.md`; `standards.md` for standards impact |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Skills | docx, pptx, xlsx, pdf (to read sources) |
| Templates | `templates/radar-ballot-template.md`, `tech-lifecycle-review-template.md`, `strategy-brief-template.md` |
| Outside systems | None directly. Configuration-management data comes from the gateway through Kit |
| Other agents | Gateway, researcher, training lead, deck builder, curator, decision recorder, librarian, all through Kit |
| If missing | `future-tech.md` missing or voting rule "not set": drafts ballots and reviews marked "voting rule not set", records no placements. No templates: uses its default layout |

### lab-planner

| | |
|---|---|
| Setup | `labs.md`, `library.md`; `standards.md` for the security baseline |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Skills | docx, pptx, xlsx, pdf (to read sources) |
| Templates | `templates/lab-runbook-template.md` |
| Other agents | Researcher (vendor steps), POC lead (charter and test plan), librarian, all through Kit |
| If missing | `labs.md` missing or approver "not set": drafts runbooks marked "approver not set". No template: uses its default layout |

### precedent-finder

| | |
|---|---|
| Setup | `precedent.md`, `library.md`; `standards.md` for what counts as a standard |
| Tools | All except WebSearch, WebFetch, Agent, SendMessage |
| Skills | docx, pptx, xlsx, pdf (to confirm a hit in a document) |
| Commands | `python3` with `shared/bin/kit-precedent` |
| Other agents | Intake triager and POC lead (precedents through Kit), librarian, curator, writers, all through Kit |
| If missing | No library root: stops. `precedent.md` missing: `kit-precedent` uses its default sources. A source missing: reported and skipped. `kit-precedent` missing: searches the indexes by hand |

## 4. Optional components

Install with a package manager already on the machine, pinned to a version with no known
advisories. Don't pipe downloaded scripts into a shell. If your organization runs a software
catalogue, request the component there first; the commands below are for machines where a package
manager is allowed.

| Component | Used for | macOS | Windows |
|---|---|---|---|
| LanguageTool + Java 17+ | `kit-grammar`, the reviewer's grammar pass | `brew install languagetool` (pulls in OpenJDK) | `winget install EclipseAdoptium.Temurin.21.JRE` for Java; LanguageTool from Chocolatey or Scoop if your catalogue carries it, then set `KIT_LANGUAGETOOL` to the folder holding `languagetool-commandline.jar` |
| draw.io desktop | PNG/SVG/PDF export without a window; opening `.drawio` files | `brew install --cask drawio` | `winget install JGraph.Draw` |
| Poppler (`pdftotext`, `pdftoppm`) | `kit-grammar` on PDFs; the pdf skill's page images (`pdf2image`) | `brew install poppler` | `choco install poppler` or `scoop install poppler` |
| LibreOffice (`soffice`) | Slide and document previews, format conversion in the document skills | `brew install --cask libreoffice` | `winget install TheDocumentFoundation.LibreOffice` |
| Microsoft Office | Opening and checking `.docx`/`.pptx` output; desktop Outlook for the Outlook-based mail and calendar tools | Your organization's catalogue | Your organization's catalogue |
| Visio or OmniGraffle | Verifying the diagram source of record, if your standard requires one | Catalogue | Catalogue |
| Skills Python venv | The document skills and the QA skill, kept apart from your base Python | `python3 -m venv ~/.claude/skills/.venv`, then `~/.claude/skills/.venv/bin/pip install` with pinned versions of `python-pptx`, `openpyxl`, `pypdf`, `pdfplumber`, `pdf2image`, `lxml`, `defusedxml`, `Pillow`, `XlsxWriter` | `py -3 -m venv %USERPROFILE%\.claude\skills\.venv`, then `...\.venv\Scripts\pip install` the same pinned packages |
| `python-docx` | Optional alternative for reading `.docx` | Same venv | Same venv |
| Node.js + `pptxgenjs` / `docx` | The document skills' from-scratch builders | `brew install node`, then a pinned `npm install` | `winget install OpenJS.NodeJS.LTS`, then a pinned `npm install` |
| `pywin32` | Windows mail, calendar, reminders adapters | n/a | `py -3 -m pip install pywin32==<pinned>` |
| BurntToast | Windows toast delivery | n/a | `Install-Module BurntToast -Scope CurrentUser -RequiredVersion <pinned>` |

### Shared folder for team sharing (optional)

| Requirement | Used by | Notes |
|---|---|---|
| A shared folder every Kit can reach | kit-publish, kit-team, team dashboard | Synced SharePoint/OneDrive library, network share, or synced Dropbox/Google Drive where policy allows. Each Kit needs write access to its own `kits/<kit id>/` folder and read access to the rest |

## 5. Credentials and access (names only)

Kit never stores credentials in its notes, and the gateway never asks for, reads, or repeats them.

| What | How it's referenced | Used by |
|---|---|---|
| MCP connector tokens | Environment variables referenced from the Claude Code MCP config as `${VAR_NAME}` (one per connector, for example `<TRACKER>_MCP_TOKEN`, `<WIKI>_MCP_TOKEN`) | Gateway, and the guarded direct callers |
| Service accounts for local MCP servers | The server's own env file or the OS credential store (Keychain / Credential Manager), never Kit's notes | Gateway |
| Network access | Corporate network or VPN for internal connectors | Gateway |
| Mail and calendar | The signed-in desktop client; macOS Automation permission for the terminal | Scheduler, meeting scribe, Kit |
| Messages / Reminders | macOS Automation permission on first run | Scheduled runs, reminders sync |
| Synced document libraries | The signed-in sync client | Librarian, curator, writers |
| Git hosting | Your git credential helper | Publishing the public repo only |
| `KIT_CONNECTOR_GUARD_CONFIG`, `KIT_LANGUAGETOOL`, `JAVA_HOME` | Optional path overrides, not secrets | connector-guard, kit-grammar |

A failed sign-in can count against a shared account: the gateway stops after one failure.

## 6. Check it

Run `python3 ~/Claude/Agents/kit/.install/shared/doctor.py` (add `--servers` to start each MCP
server, `--brief` for problems only).

### What `doctor.py` checks today

- Kit's import line in `~/.claude/CLAUDE.md`.
- Claude Code permission rules for Kit's notes, and that order-placing tools aren't pre-approved
  (author-specific tool list).
- Every note in the memory indexes exists; unindexed notes (warning).
- Scheduled jobs loaded in launchd (only for installed plists) and recent run logs.
- No credential-shaped strings in Kit's notes, queue, or status.
- Kit's folder is private (POSIX mode).
- Agents in `~/.claude/agents/` match Kit's copies (`--fix-agents` copies them).
- Kit's git history saved in the last three days.
- Calendar (`~/.local/bin/kitcal`) and Apple Mail (`~/.local/bin/kitmail`, only when Mail is running).
- LanguageTool and Java for `kit-grammar` (informational; absence is never a problem).
- With `--servers`: every MCP server connects.
- Author-specific checks (a trading token, a trading guard) that are skipped when absent.
- Kit paused (warn while `kit-pause` is on).
- Outlook: today's result from `kit-outlook` (warn if not responding, blocked, or an error).
- Legal holds: lists active holds (ok; warn if the holds file can't be read).
- Cost: this month's scheduled-run spend and projection, and the share of the budget used (warn
  at the warning level or above).

### Gaps it doesn't check

- Python version, and whether `python3` resolves (the hook commands depend on it; on Windows it
  often doesn't).
- Each agent's setup file exists, and how many fields are still "not set".
- The library root in `library.md` exists and is writable; published library folders are reachable.
- `connector-guard.json` is valid, its `audit_dir` is writable, and every agent that can reach
  connectors carries the guard hooks (the demand tracker doesn't today).
- Environment variables referenced by the MCP config (`${VAR}`) are set (existence only).
- A server that "connects" may still fail to sign in; `--servers` doesn't make a read call.
- Skills and plugins that setup files name are installed (QA, style, brand, draw.io,
  connectivity-map), and versioned paths in setup files match what's installed.
- The skills venv exists and imports its packages.
- Optional CLIs: draw.io, Poppler, LibreOffice, any diagram converter.
- `vsdx-finish.json` and `drawio-styles.json` are valid JSON.
- Mail and calendar tools other than the Apple ones (for example an Outlook-based tool), and
  whether the desktop client is the scriptable classic version.
- Windows: job checks use `launchctl`, and there's no Task Scheduler, ACL, `pywin32`, or classic
  Outlook check.

### Fails open or closed

The connector guard blocks the call if it hits an internal error. If the hook command itself can't
start (for example `python3` isn't on the PATH), Claude Code treats that as a non-blocking hook
error, so the call likely proceeds unguarded and unlogged. Check `python3` resolves in the shell
Claude Code uses for hooks, on every machine.

- connector-guard while paused: closed (every connector call denied).
- kit-retention: closed (no rules, an unreadable file, or a held project means nothing is eligible;
  an unreadable text file counts as held).
- kit-backup: an archive that fails its check is kept, but older backups aren't pruned.
- kit-team and the team dashboard: closed per record (a record that fails its schema, names the
  wrong Kit, sits under the wrong name, or doesn't match its Kit's manifest is skipped and listed
  in `kit-team warnings`); open per Kit with no manifest yet (shown, marked unverified).
- Budget guard: open (no budget, an unreadable ledger, or kit-cost missing means every run goes
  ahead; output that isn't JSON is logged as is and no cost is recorded).
- kit-queue apply: closed (only H numbers from the saved briefs/hygiene.json, matched by title; a
  missing item is skipped and reported; QUEUE.md is backed up before any change).

# Kit's staff

The agents Kit directs for {{OWNER}}. Each is a Claude Code subagent: its definition lives in
`~/Claude/Agents/kit/agents/` and is installed into `~/.claude/agents/`, where Claude Code finds it
(`python3 ~/Claude/Agents/kit/.install/shared/doctor.py --fix-agents` copies them over).

Work between agents goes through Kit, except for these direct pairs:

- The IA writer and the GDS writer talk to each other.
- The curator can go to the librarian, one way: the librarian answers but can't start a
  conversation.
- The implementation planner can go to the GDS writer, one way.
- The intake triager, the dependency mapper, and the status reporter can go to the gateway, one
  way.

Agents not named in a pair can't start or message other agents at all.

The gateway is the agent meant to reach outside systems. It's read-only and least privilege, and
the connector guard (`~/Claude/Agents/kit/.install/shared/bin/connector-guard`) enforces that with
hooks and records every request in an audit log. The guard also runs on the three agents that call
the gateway. Connectors aren't locked to the gateway yet: other agents can still use them directly.

Each agent reads its setup file in `memory/context/` before every job. Delegate with a brief: the
goal, the context, constraints, what done looks like, and when it's due. When a report ends with a
**Requests**, **Librarian requests**, or **Curator requests** section, route each request to the right agent, then brief
the requester again with the answers. All of them may see their setup files, the library, and
what Kit gives them, never personal notes, and all run for {{OWNER}} on this computer.

## researcher

- **Does:** research only, with sources and a confidence level on each finding. Read-only.
- **Reach it:** a brief with the question and why it matters. For anything that touches internal
  documents, ask the librarian first and put what it finds in the brief.
- **Note:** its searches go to outside search engines, so briefs shouldn't invite confidential
  details into a query.

## librarian

- **Does:** houses and catalogs everything the staff creates or {{OWNER}} submits, indexes the
  published libraries, searches working folders, and answers lookups with citations.
- **Reach it:** "file this", "find" or "pull", or "refresh the published index".
- **Routine:** after any agent saves a document, diagram, review, or brief, have the librarian
  catalog it, then have the curator catch up.
- **Talks directly to:** no one. It answers the curator when the curator comes to it.
- **Setup:** `memory/context/library.md`.

## curator

- **Does:** keeps the knowledge that spans documents: decisions, standards and reusable
  patterns, system profiles, and conflicts or superseded decisions, each cited to library
  holdings. Writes only in the library's `knowledge/` folder.
- **Reach it:** "what have we decided about...", "what's our standard for...", "catch up on
  new filings", or "check this document against our decisions".
- **Talks directly to:** the librarian, one way. It can ask the librarian anything; the
  librarian can't start a conversation with it.
- **Setup:** `memory/context/knowledge.md`.

## ia-writer

- **Does:** drafts and revises impact assessments (IAs) from the template, and records what the
  GDS must carry in the project's IA-GDS handoff file.
- **Reach it:** the project name, the demand or request, the source material, and what's needed
  (a first draft, a revision, or specific sections).
- **Talks directly to:** the gds-writer.
- **Setup:** `memory/context/writing.md`.

## gds-writer

- **Does:** drafts and revises general design specifications (GDSs), usually from a completed IA,
  and traces every IA requirement into the design.
- **Reach it:** the project name, the IA it's based on, and what's needed.
- **Talks directly to:** the ia-writer. The implementation planner may also come to it, one way.
- **Setup:** `memory/context/writing.md`.

## reviewer

- **Does:** reviews documents before they go out: a QA scan with the QA skill in its setup,
  template and style checks, a GDS checked against its IA, and design risks. Read-only on the
  document.
- **Reach it:** the document, its type, its project, and what it's based on.
- **Routine:** send each IA and GDS draft to the reviewer before {{OWNER}} shares it, then send the
  findings to the writer that owns the draft.
- **Setup:** `memory/context/writing.md`.

## diagrammer

- **Does:** draws architecture, network, and data-flow diagrams to the team's standard, with an
  editable file and a rebuildable spec.
- **Reach it:** what the diagram must show, the documents it comes from, and the project.
- **Setup:** `memory/context/diagrams.md`.

## scheduler

- **Does:** calendar work: what's coming, finding time, prep and focus time, meeting preparation,
  and drafts of invitations and replies. Never sends, accepts, or declines.
- **Reach it:** the period or meeting, and the deadlines from the queue that matter.
- **Setup:** `memory/context/calendar.md`.

## demand-tracker

- **Does:** tracks demands and tickets: what's open, what changed, what's stuck, and how they link
  to projects and documents. Read-only on the systems it checks; keeps a register in the library.
- **Reach it:** "what's open", "status of <number>", "what changed", or "what's stuck".
- **Routine:** put new dates and waiting items from its reports in the queue.
- **Setup:** `memory/context/demands.md`.

## gateway

- **Does:** reaches outside systems, such as service management, issue trackers, and wikis, for
  lookups. Read-only, and the connector guard logs every request.
- **Reach it:** the system, the records or search, the fields needed, and why.
- **Talks directly to:** no one. It answers Kit and its three direct callers.
- **Setup:** `memory/context/connectors.md` and `connector-guard.json`.

## intake-triager

- **Does:** triages new demands and requests: the record, the intake checklist, precedent, whether
  an impact assessment is needed, and draft questions for the requester.
- **Reach it:** the demand or ticket number, or the request itself.
- **Talks directly to:** the gateway, one way.
- **Routine:** run it on every new demand before any writing starts.
- **Setup:** `memory/context/intake.md`.

## dependency-mapper

- **Does:** maps what a change touches, upstream and downstream, from configuration records and
  documents, with a spec the diagrammer can draw from.
- **Reach it:** the systems in scope, the depth, and the project.
- **Talks directly to:** the gateway, one way.
- **Setup:** `memory/context/connectors.md`.

## status-reporter

- **Does:** project and weekly status from every source: completed, in progress, blockers, issues,
  escalations needed, and a timeline.
- **Reach it:** the project and the window, or "weekly status".
- **Talks directly to:** the gateway, one way.
- **Setup:** `memory/context/status.md`.

## implementation-planner

- **Does:** turns an approved GDS into a test plan, a change request, a runbook, and a cutover
  checklist.
- **Reach it:** the project and the GDS version.
- **Talks directly to:** the gds-writer, one way.
- **Setup:** `memory/context/writing.md`.

## deck-builder

- **Does:** slides for leadership, review boards, or change boards, from finished documents.
- **Reach it:** the source documents, the audience, and the project.
- **Setup:** `memory/context/writing.md`.

## handoff

- **Does:** handoff briefs for a project changing hands, or for when {{OWNER}} will be away.
- **Reach it:** the project, the reason, and who's taking over, by role.
- **Setup:** `memory/context/library.md` and `knowledge.md`.

## meeting-scribe

- **Does:** minutes from the project manager's notes, the architect's notes, and transcripts, with
  decisions, actions, and disagreements between the sources flagged.
- **Reach it:** the meeting (project and date), or "process the meeting inbox".
- **Routine:** after it reports, have the librarian catalog the minutes and the curator record the
  decisions, and put the actions in the queue.
- **Setup:** `memory/context/meetings.md`.

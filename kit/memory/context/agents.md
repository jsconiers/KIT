# Kit's staff

The agents Kit directs for {{OWNER}}. Each is a Claude Code subagent: its definition lives in
`~/Claude/Agents/kit/agents/` and is installed into `~/.claude/agents/`, where Claude Code finds it
(`python3 ~/Claude/Agents/kit/.install/shared/doctor.py --fix-agents` copies them over). Work between
agents goes through Kit, with one exception: the IA writer and the GDS writer also talk to each
other directly. The other agents can't start or message agents at all.

Each agent reads its setup file in `memory/context/` before every job. Delegate with a brief: the
goal, the context, constraints, what done looks like, and when it's due. When a report ends with a
**Requests** or **Librarian requests** section, route each request to the right agent, then brief
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
  catalog it.
- **Setup:** `memory/context/library.md`.

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
- **Talks directly to:** the ia-writer.
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

# Shared Kit records

Each architect runs their own Kit on their own machine. To give the team one dashboard and a
shared set of lessons, each Kit publishes a small set of **records** to an outbox folder, and the
team dashboard reads the outboxes of every Kit. For now you copy outboxes into a common folder
yourself. Syncing them through a shared folder comes later.

```
your Kit ── kit-publish ──> <outbox>/<kit id>/<type>/<local id>.json ──> team_dashboard.py ──> team-dashboard.html
```

Records carry metadata and short summaries only. They never carry full document text,
credentials, or personal notes, and their `source` is a path relative to the Kit or the library,
never the document itself.

## Record types

| Type | What it holds | Where kit-publish gets it |
|---|---|---|
| `status-snapshot` | One project's in-progress, blocked, and next items, waiting items, and health | `STATUS.md`, the waiting section of `QUEUE.md`, and the latest `artifacts/<project>/status/status-*.md` in the library |
| `decision` | A decision, its options, why, when to revisit, and its citations | `memory/decisions/*.md`; and, when `knowledge.md` doesn't say the knowledge base is private, the decision recorder's `ADR-*.md` (the folder in `decisions.md`, default `decisions/` in the library) and `knowledge/decisions.md` |
| `lesson` | A lesson's rule, **Why:**, and **How to apply:** | `lessons/*.md` tagged `share: team` |
| `artifact-pointer` | A library holding's accession and document number, title, type, status, version, date, and library path | `CATALOG.md` in the library |
| `demand-rollup` | Per project, counts of demands and tickets by status, and a short list with due dates | `demands/REGISTER.md` in the library, or the register named in `demands.md` |
| `handoff-pointer` | A handoff brief's date, title, one-paragraph standing, and section names | `artifacts/<project>/handoff/handoff-*.md` in the library |

The library is the folder named under **Library root** in `memory/context/library.md`.
kit-publish skips quietly what isn't there. The schemas are in `schema/`, one per type.
`envelope.schema.json` holds the fields every record shares.

## The envelope

Every record is one JSON object in its own file, with these fields:

| Field | Meaning |
|---|---|
| `schema` | The record type, for example `lesson` |
| `schema_version` | `MAJOR.MINOR`, for example `1.0` |
| `id` | `<kit id>:<type>:<local id>`, stable across runs, for example `kit-7f3a:lesson:check-dates-first` |
| `kit_id` | An opaque id for the Kit, never a person's name |
| `owner_role` | The owner's role, never a name |
| `project` | A project slug (lowercase, hyphens); `general` when the item names none |
| `created`, `updated` | ISO 8601 date-times in UTC. `updated` changes only when the content changes |
| `classification` | `internal` or `confidential` |
| `source` | `kit:<path>` or `library:<path>[#anchor]`, relative, never absolute, never under `personal/` |
| `body` | The type-specific fields, defined in that type's schema |

Dates inside `body` are `YYYY-MM-DD` or `null`. Text fields have length limits in the schemas, so
summaries stay summaries.

## Versioning

- An **additive** change, such as a new optional field, bumps the minor version (1.0 to 1.1). An
  older dashboard still shows the record, ignores the new field, and warns.
- A **breaking** change, such as removing, renaming, or retyping a field, bumps the major
  version (1.x to 2.0). Keep the old schema as `<type>.v1.schema.json` next to the new
  `<type>.schema.json`: the dashboard must accept the current and the previous major version, and
  it rejects older or newer majors with a warning.
- The current version of each type is `x-kit-version` in its schema file. kit-publish writes
  that version, and validates every record against it before writing.

## Tagging lessons and decisions for sharing

A lesson is shared only when its first line, or its frontmatter, says `share: team`:

```
share: team

Check the change calendar before proposing a cutover date.

**Why:** A proposed date fell in a freeze window and cost a week.

**How to apply:** Before any date goes in a draft, look up freezes for that month.
```

or

```
---
share: team
---
Check the change calendar before proposing a cutover date.
...
```

A lesson without a tag, or tagged `share: private`, stays private. The same leading lines can
also set `project: <name>` and `classification: confidential`.

Decision notes in `memory/decisions/` are shared when the `decision` type is turned on, unless the
note says `share: private`. kit-publish reads these labels when they're there: a `# Title`
heading, **Decision:**, **Options:** (bullets), **Why:**, **Revisit:**, and **Status:**. It takes
the date from the file name.

To tag an item in `STATUS.md` or `QUEUE.md` with its project, start it with the project name in
square brackets: `- [payments-upgrade] Firewall change approved`.

## What's never shared

- Anything under `memory/personal/`. kit-publish never opens it, and the schemas reject any
  `source` under a `personal/` folder.
- Lessons that aren't tagged `share: team`, and decision notes tagged `share: private`.
- Any record with credential-shaped text: tokens, keys, private keys, `password: ...`-style
  assignments, passwords in URLs, and long digit runs that look like account numbers. kit-publish
  blocks the whole record, names the pattern, and exits 1. Reword the source and run it again.
- Projects excluded in `sharing.md`. Projects listed as confidential there are always marked
  `confidential`.

## Settings

`memory/context/sharing.md`: the outbox, the Kit id, the owner role, which types to publish
(none until you turn them on), projects to include or exclude, and the default classification.

## Commands

```bash
kit=~/Claude/Agents/kit/.install/shared
python3 $kit/bin/kit-publish --dry-run           # list what would be written
python3 $kit/bin/kit-publish                     # write new and changed records
python3 $kit/bin/kit-publish --prune             # also remove records this run no longer produces
python3 $kit/bin/kit-publish --types all --dry-run   # preview every type, whatever sharing.md says
python3 $kit/team_dashboard.py --source DIR --source DIR2 --open
```

kit-publish is idempotent: a second run with the same input changes no file. Records that are no
longer produced (the source is gone, the lesson was untagged, the type was turned off) are
reported as stale, and removed with `--prune`. A blocked record's earlier clean copy is kept until
you fix the source.

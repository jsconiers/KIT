# Sharing setup

What `kit-publish` shares with your team, and where it puts it. Nothing is shared until you set a
Kit id and turn on at least one record type below. Record formats are in
`.install/shared/records/README.md`.

- **Outbox:** `~/Claude/Agents/kit/outbox`. kit-publish writes records under `<outbox>/<kit id>/`.
  Later this can be a folder your team shares; for now, copy the folder there yourself.
- **Kit id:** not set. A short id for this Kit that isn't your name, 3 to 40 lowercase letters,
  digits, or hyphens, for example `kit-7f3a`. Keep it once records are shared: it's part of every
  record's id.
- **Owner role:** not set. Your role, not your name, for example `solutions architect`.
- **Publish:** none. Any of: status-snapshot, decision, lesson, artifact-pointer, demand-rollup,
  handoff-pointer.
- **Include projects:** all. Or a comma-separated list of project names.
- **Exclude projects:** none. Projects never to share, even when included above.
- **Classification:** internal. The default for every record: internal or confidential.
- **Confidential projects:** none. Projects whose records are always marked confidential.
- **Default project:** general. The project for items that don't name one.

To tag an item in `STATUS.md` or `QUEUE.md` with its project, start it with the project name in
square brackets, for example `- [payments-upgrade] Firewall change approved` or
`- [ ] **[payments-upgrade] Change window**: waiting on the network team since 02-Oct-2026`.
Lessons are shared only when they say `share: team`, and decision notes are skipped when they say
`share: private` (see the records README). Nothing under `memory/personal/` is ever read.

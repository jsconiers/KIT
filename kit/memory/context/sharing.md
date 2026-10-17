# Sharing setup

What `kit-publish` shares with your team, and where it puts it. Nothing is shared until you set a
Kit id and turn on at least one record type below. Record formats are in
`.install/shared/records/README.md`.

- **Transport:** folder. How Kits share records. `folder` works with any folder your team can
  reach: a synced SharePoint or OneDrive library, a network share, or (outside a company that
  forbids it) a synced Dropbox or Google Drive folder. Other transports aren't built yet.
- **Shared root:** not set. The shared folder's path on this computer. When set, kit-publish writes
  to `<shared root>/kits/<kit id>/` with a manifest of hashes, and `kit-team` and the team
  dashboard read every Kit's folder there into this Kit's local cache. Never put the cache there.
- **Outbox:** `~/Claude/Agents/kit/outbox`. Used when Shared root isn't set: kit-publish writes
  records under `<outbox>/<kit id>/`, and you copy the folder to your team yourself.
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

# Records retention setup

What `kit-retention` uses. Kit's briefs, minutes, drafts, and notes may count as business records,
so their retention follows your organization's records policy, not Kit's defaults.

- **Policy source:** not set. The records policy or schedule these rules come from, and who owns
  it (a role, such as the records manager). Until it's set, keep everything.
- **Rules:** none, so nothing is ever eligible for disposal. Rules go in `retention.json` next to
  this file: for each kind of record, where it lives, how long to keep it, and the action
  (`dispose`). Get each period from the policy, never from a guess.
- **Holding folder:** `.install/retention-holding/` in Kit's folder, unless `retention.json` says
  otherwise. Disposal moves files here first; empty it only once disposal is confirmed under the
  policy.
- **Legal holds:** set with `kit-retention hold <project> --reason "<matter>"` and ended with
  `kit-retention release <project>`, only when the hold's owner (often Legal) says so. Held
  projects are listed in the morning brief and on the dashboard, and no agent may delete, move, or
  rewrite their files.
- **Git history:** older versions of files stay in Kit's local history. Ask the policy owner
  whether the history needs the same treatment before relying on disposal.

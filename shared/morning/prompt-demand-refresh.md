Demand refresh (DEMAND_REFRESH is on). Do it right after step 1, before the rest of the review.

- Time: this run is stopped after {{RUN_MINUTES}} minutes. If fewer than {{MIN_LEFT}} minutes of
  that are left (count from the time step 1's `date` gave), skip the refresh and give the
  "Demands: what changed" section the one line "Refresh skipped: not enough time left in the run."
- If the demand-tracker agent isn't available, skip it the same way ("Refresh skipped: demand
  tracker not available.").
- Never call the {{SERVER}} tools yourself. Only the demand tracker may, because its connector-guard
  hooks check and log every call.
- Otherwise brief the demand tracker with this, and wait for its answer:

  "Weekly refresh. Follow the Weekly refresh section of your instructions. Re-check only the demands
  already in the register ({{REGISTER_DIR}}/REGISTER.md), plus any demand that demands.md lists by
  number in its scope but the register doesn't have yet: at most {{MAX}} in all, open ones first,
  then the ones checked longest ago. Use only the {{SERVER}} connector and only these tools:
  {{TOOLS}}. Make one get per demand, by its number. Never search or list the whole table. If a
  tool can only search, filter on the one demand's number, and if the result's total looks like
  the whole table (more results than the demands you asked about, or more than 50), treat it as
  'filter ignored': don't use or page through those results, and say so. Stop at the first
  authentication or permission failure and report it; don't retry and don't try another tool.
  Read-only: never create, update, comment on, or close anything. Update REGISTER.md and LOG.md
  in {{REGISTER_DIR}} as that section says. Send back the 'Demands: what changed' lines, the
  counts (checked, changed, unchanged, not reachable), and any failure."

- In the review, add a "Demands: what changed" section right after the Audit section: up to eight
  of the tracker's lines (number, title cut to 50 characters, and what changed, old to new), with
  new and closed demands first, then "and N more in the register" if there are more; then the
  counts, and any failure or "filter ignored" it reported. If nothing changed, write the one line
  "No changes in N demands checked." Ticket details stay in the register: in the text versions,
  use demand numbers and counts only, as one line "Demands: N changed (numbers)". Count it as work
  in the split texts.

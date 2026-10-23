Monthly regulatory watch (REG_WATCH is on; first weekly review of the month). Do it after the
horizon scan (step 8), before step 9's weekly watch. It's separate from that watch: if both run,
don't repeat an item in both sections.

- Time: this run is stopped after {{RUN_MINUTES}} minutes. If fewer than {{MIN_LEFT}} minutes of
  that are left (count from the time step 1's `date` gave), skip it and give the "Regulatory
  watch" section the one line "Skipped: not enough time left in the run."
- If the researcher agent isn't available, skip it the same way ("Skipped: researcher not
  available.").
- Only the researcher searches the web. Don't call WebSearch or WebFetch yourself.
- Otherwise brief the researcher with this, and wait for its answer:

  "Monthly regulatory watch for {{MONTH_NAME}}. What changed in the last month (from the first of
  {{MONTH_NAME}} to {{TODAY}}) for these public regimes and topics: {{REGIMES}}. Look for rules,
  guidance, standards, and advisories published, proposed, finalised, or taking effect, and comment
  periods opening or closing. Public sources only, preferring the regulator's or standards body's
  own pages, each cited with its URL and the date checked, and a confidence (high, medium, or low,
  with the reason). Search only with the regime and topic names above: never add a company,
  system, project, client, or document name, or anything from this computer's files. At most 15
  changes, most consequential first; say which topics had nothing new. Draw no compliance
  conclusions. Keep what the sources say apart from your own inferences."

- Write the result from {{TEMPLATE}} to {{OUT_FILE}}{{FALLBACK}}: the template is weekly, so
  title it "Regulatory watch: {{MONTH}}", put the month in place of the week, list the regimes
  under "Topics covered", and keep its sections (changes, for the risk and compliance mapper, radar
  candidates, inferences). If you can't write there, write
  ~/Claude/Agents/kit/briefs/regulatory-watch-{{MONTH}}.md and say so. Flag changes that may touch
  controls for the risk and compliance mapper and changes that may move a technology for the
  future tech planner; never decide compliance yourself.
- In the review, add a "Regulatory watch" section with exactly three lines: the most consequential
  change (regime, what changed, date, source), the next two in one line, and the count of changes
  plus the file's path. In the text versions, one line: "Reg watch: N changes ({{MONTH}})". Count
  it as work in the split texts.

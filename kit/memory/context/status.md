# Status setup

What the status reporter uses. It reads this before every job, so keep it current.

- **Format:** completed, in progress, blockers, issues, and escalations needed, plus a timeline of
  dated commitments and a "Since last report" section (slipped dates, blockers by age, reopened
  items, and the trend), unless you set another here.
- **Window:** the last 14 days, unless you set another.
- **Audiences:** optional. Who reads each kind of report, such as a leadership summary or a team
  view, and how long each should be.
- **Stakeholder map:** `<library root>/artifacts/<project>/stakeholders.md`, one per project, from
  `~/Claude/Agents/kit/templates/stakeholder-map-template.md`. Optional; when it exists, report
  audiences and who signs off each gate come from it.
- **Sources:** optional. Anything beyond the connectors in `connectors.md` and the library.
- **Exploration section:** on, for team and weekly reports and for projects with a POC or lab.
  Set "off" to leave it out.

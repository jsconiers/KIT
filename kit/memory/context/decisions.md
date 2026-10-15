# Decision records setup

What the decision recorder uses. It reads this before every job, so keep it current.

- **Folder:** `decisions/` in the library root (see `library.md`), unless you set another place
  here.
- **Numbering:** ADR-0001 and up, never reused. `INDEX.md` in the folder holds the next free number.
- **Template:** `~/Claude/Agents/kit/templates/adr-template.md`, an example to adapt. Point here
  to your team's own template if it has one. The recorder fills in every field and keeps the
  section order.
- **Sources to scan:** meeting minutes, reviews, and IA and GDS drafts in the library's project
  folders, plus Kit's briefs, unless you set others here.
- **Who can accept a decision:** optional. The roles whose decisions count as accepted, such as an
  architecture review board or a design authority. Until set, the recorder takes the decider from
  the source.

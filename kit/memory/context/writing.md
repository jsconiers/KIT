# Writing setup

What the IA writer, the GDS writer, the reviewer, the implementation planner, and the deck
builder use. Each reads this before every job, so keep
it current.

- **Templates:** not set. The current template for each document type, and any guide to what goes
  in each section.
- **Examples:** not set. Past or published documents worth modeling.
- **Skills:** not set. Writing, style, and brand skills the writers apply, and the QA skill the
  reviewer runs, with the exact way to run it and where its reports must go.
  If the QA skill needs LanguageTool, `kit-grammar --where` prints the folder to point it at.
  Without a QA skill, the reviewer runs `kit-grammar` on its own when LanguageTool is installed.
- **Review lessons:** not set. The file where the reviewer keeps one-line rules from findings that
  recur across reviews, which the IA and GDS writers read before every draft. For example
  `<library root>/knowledge/review-lessons.md`.
- **Quality loop:** min 3, days 90. How often a finding must recur (same category, template, and
  section, in at least two reviews) within how many days before `kit-quality` proposes a lesson and
  a template change. Proposals go to `briefs/pending-lessons.md` and
  `briefs/pending-template-changes.md` for {{OWNER}} to approve.
- **Output:** not set. The file format for drafts, and how to name them.
- **Tools:** optional. Document-generation tools the writers may use, and any limits on them.
- **Implementation documents:** optional. Templates for test plans, change requests, runbooks, and
  cutover checklists, for the implementation planner.
- **Traceability matrix:** optional. `~/Claude/Agents/kit/templates/traceability-matrix-template.md`
  is the layout `kit-trace` follows, tracing each IA requirement to the GDS, the test plan, the
  change request, and any POC. Point this at the team's copy.
- **Decks:** optional. The slide template, the IA and GDS deck templates with their slide order, the
  brand and slide skills, and slide counts by audience, for the deck builder.
- **Research briefs:** optional. `~/Claude/Agents/kit/templates/research-brief-template.md` is the
  layout for research briefs filed in the library, in the order the researcher reports.
- **TOGAF deliverables:** optional, on request only. `togaf-architecture-vision-template.md`,
  `togaf-statement-of-architecture-work-template.md`, `togaf-architecture-definition-document-template.md`,
  `togaf-architecture-requirements-specification-template.md`, `togaf-transition-architecture-template.md`,
  and `togaf-implementation-migration-plan-template.md` follow the structure of TOGAF deliverables
  (headings paraphrased; TOGAF is a trademark of The Open Group). Each says which IA and GDS parts
  already supply it; the IA and GDS stay the documents of record.

# Implementation and migration plan: <initiative name>

An example template for a TOGAF-style implementation and migration plan: how the gaps between
baseline and target are closed through work packages and projects, in what order, at what cost,
and under what governance. Private to this Kit and used only on request; the implementation
planner's test plan, change request, runbook, and cutover checklist remain the delivery documents
and this plan sits above them. Copy it, change it to suit the team, and point
`memory/context/writing.md` at the copy. Delete the guidance lines in angle brackets when filling
it in.

Based on the structure of TOGAF deliverables (The Open Group); headings paraphrased. TOGAF is a
trademark of The Open Group. This template uses section structure only, written in our own words.

| Field | Value |
|---|---|
| Initiative | <project name or slug> |
| Demand or ticket | <number> |
| Version | <0.1, 0.2, 1.0> |
| Prepared | <DD-Mmm-YYYY> |
| Prepared by | <role> |
| Project manager | <role> |
| Reviewed by | <role or forum> |
| Approved | <DD-Mmm-YYYY, or "not approved"> |
| Related documents | <architecture definition document, transition architectures, GDS, cost estimate, PMO estimate> |
| Classification | <internal or confidential> |

## 1. Summary

<The approach in three to five sentences: how many plateaus, how long, the critical path, and the
main risk.>

## 2. Implementation approach

<Big bang, phased, parallel run, or pilot then roll-out, and why. Build, buy, or partner choices
and where they were decided (link the build-buy-partner analysis or ADR).>

## 3. Work packages

| ID | Work package | Gaps closed (ADD IDs) | Plateau | Owner (role) | Effort range |
|---|---|---|---|---|---|
| WP-01 | | | | | <low, likely, high> |

## 4. Dependencies

| From | To | Type | Note |
|---|---|---|---|
| WP-01 | WP-02 | <finish to start, data, environment, procurement, external> | |

<Include dependencies on other projects and on vendors.>

## 5. Sequence and timeline

| Plateau | Work packages | Start | End | Gate |
|---|---|---|---|---|
| 1 | | <DD-Mmm-YYYY> | <DD-Mmm-YYYY> | <your project lifecycle|

<Reference a roadmap view if one exists (`tech-roadmap-template.md`).>

## 6. Resources and skills

<Teams by role, environments, labs, and vendor support needed, and any skills gap with a plan.>

## 7. Cost

<Summary of the cost estimate with low, likely, and high figures, and its source. Never a quote.>

## 8. Value realisation

| Benefit | Measure (from the requirements spec) | Realised at | Owner (role) |
|---|---|---|---|
| | | <plateau or date> | |

## 9. Risks and issues

| # | Risk or issue | Likelihood | Impact | Mitigation | Owner (role) |
|---|---|---|---|---|---|
| 1 | | | | | |

## 10. Testing and acceptance

<Test stages per plateau, who accepts, and the evidence. Link the test plan.>

## 11. Change and release governance

<Change requests per work package, change board lead times, freeze periods, go/no-go points, and
how architecture conformance is checked during build.>

## 12. Cutover, rollback, and decommission

<Cutover approach per plateau, rollback limits, and what is decommissioned when, including data
deletion and licence return.>

## 13. Handover to operations

<Runbooks, monitoring, support model, and the operations sign-off needed.>

## Maps to your IA and GDS

| Plan part | Usually supplied by |
|---|---|
| 2 Approach | GDS Migration (Functional Overview) |
| 3-5 Work packages, dependencies, timeline | project charter (timeline); PMO estimate; GDS Migration Flows (partly) |
| 7 Cost | Cost estimator's ROM estimate (from the GDS bill of materials) |
| 9 Risks | IA Risks / Issues List |
| 10 Testing | Implementation planner's test plan; your project lifecycle|
| 11 Governance | Change board pack; your project lifecycle|
| 12 Cutover and rollback | Implementation planner's runbook, cutover checklist, change request (rollback and back-out); GDS Failure/Recovery |
| 12 Decommission | your project lifecycle|
| 13 Handover | your project lifecycle|

**New beyond IA and GDS:** work packages tied to gap IDs, dependencies across work packages and
other projects, a plateau-by-plateau sequence with gates, value realisation tracked against
success measures, and one plan joining cost, effort, testing, change, and decommission that today
live in separate documents.

## Sources

<Every document cited, with its library accession number or location.>

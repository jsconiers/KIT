# Statement of architecture work: <initiative name>

An example template for a TOGAF-style statement of architecture work: the agreement between the
sponsor and the architecture team on what architecture work will be done, by whom, by when, and how
it will be accepted. Private to this Kit and used only on request. Copy it, change it to suit the
team, and point `memory/context/writing.md` at the copy. Delete the guidance lines in angle
brackets when filling it in. Aim for three to five pages.

Based on the structure of TOGAF deliverables (The Open Group); headings paraphrased. TOGAF is a
trademark of The Open Group. This template uses section structure only, written in our own words.

| Field | Value |
|---|---|
| Initiative | <project name or slug> |
| Demand or ticket | <number> |
| Version | <0.1, 0.2, 1.0> |
| Prepared | <DD-Mmm-YYYY> |
| Prepared by | <role, for example principal architect> |
| Sponsor | <role> |
| Architecture lead | <role> |
| Agreed | <DD-Mmm-YYYY, or "not agreed"> |
| Related documents | <demand, project charter, architecture vision> |
| Classification | <internal or confidential> |

## Request and background

<Who asked for the work, what triggered it, and the demand or charter it comes from. Two or three
sentences.>

## Objectives of the architecture work

<What the architecture work must produce or decide, stated as outcomes, for example "an approved
target design for X that the build team can estimate from".>

## Scope of the work

| Dimension | In scope | Out of scope |
|---|---|---|
| Organisations and locations | | |
| Architecture domains | <business, data, application, technology> | |
| Depth | <conceptual, logical, physical> | |
| Time horizon | <for example current year to target in 18 months> | |
| Environments | <production, non-production, DR, lab> | |

## Approach

<How the work will run: which phases or steps, which existing documents are reused (IA, GDS,
reference architectures), whether a POC is expected, and how reviews happen.>

## Roles and responsibilities

| Activity | Responsible (role) | Accountable (role) | Consulted | Informed |
|---|---|---|---|---|
| Architecture vision | | | | |
| Requirements | | | | |
| Target design | | | | |
| Reviews and sign-off | | | | |

## Deliverables

| # | Deliverable | Format | Owner (role) | Due |
|---|---|---|---|---|
| 1 | <for example IA, GDS, architecture definition document> | | | <DD-Mmm-YYYY> |

## Plan and milestones

| Milestone | Date | Depends on |
|---|---|---|
| | <DD-Mmm-YYYY> | |

## Acceptance criteria and procedure

<How each deliverable is judged done: who reviews, against what (template, standards, requirement
coverage), and who signs off. Name the forum and the evidence of approval.>

## Assumptions, constraints, and dependencies

<Including people availability, access to systems or data, and decisions owed by others.>

## Risks to the architecture work

| # | Risk | Impact on the work | Mitigation | Owner (role) |
|---|---|---|---|---|
| 1 | | | | |

## Change procedure

<How a change to scope, deliverables, or dates is requested and agreed, and who can approve it.>

## Agreement

| Role | Decision | Date |
|---|---|---|
| Sponsor | <agreed, agreed with changes, not agreed> | <DD-Mmm-YYYY> |
| Architecture lead | | |

## Maps to your IA and GDS

| Statement part | Usually supplied by |
|---|---|
| Request and background | Demand record (your project lifecycle; intake checklist |
| Objectives, scope, deliverables, roles | project charter (Phase 2, an approval gate Sponsor Charter Sign-off): scope, timeline, stakeholders, required documents (IA, GDS, LLD) |
| Document history and supporting documents | GDS Preface (Document History, Supporting Documents) |
| Assumptions and risks | project charter (assumptions and risks); IA Assumptions, Risks and Issues |

**New beyond IA and GDS:** neither template covers the architecture work itself. New here are the
architecture-specific scope (domains, depth, horizon), a RACI for architecture activities, per-
deliverable acceptance criteria, and a change procedure for the architecture scope. Most of the
rest overlaps the project charter, so reuse the charter's wording where it exists.

## Sources

<Every document cited, with its library accession number or location.>

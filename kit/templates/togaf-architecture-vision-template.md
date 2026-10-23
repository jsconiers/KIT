# Architecture vision: <initiative name>

An example template for a TOGAF-style architecture vision, the short, early statement of what the
change is for, who cares about it, and what the end state looks like at a high level. Private to
this Kit and used only on request; the IA remains the team's standard first document. Copy it,
change it to suit the team, and point `memory/context/writing.md` at the copy. Delete the guidance
lines in angle brackets when filling it in. Aim for four to six pages.

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
| Reviewed by | <role or forum> |
| Approved | <DD-Mmm-YYYY, or "not approved"> |
| Related documents | <demand, project charter, IA, statement of architecture work> |
| Classification | <internal or confidential> |

## Summary

<Five bullets: the problem, the proposed end state, the main benefit, the biggest risk, and the
decision needed now.>

## Problem and drivers

<What is wrong or missing today, what forces the change now (regulation, end of support, growth,
incident, strategy), and what happens if nothing is done. Cite sources.>

## Business goals and measures of success

| Goal | Measure | Today | Target | By when |
|---|---|---|---|---|
| | | | | <DD-Mmm-YYYY> |

## Scope

<In scope and out of scope: business units, locations, environments, systems, and architecture
domains (business, data, application, technology). Name what is deliberately left for later.>

## Stakeholders and their concerns

| Stakeholder (role) | Concern | How the vision addresses it | Involvement |
|---|---|---|---|
| | | | <decides, approves, consulted, informed> |

<For a full view, use `stakeholder-map-template.md` and link it here.>

## Principles that apply

<The enterprise or team principles this work must follow, and any it proposes to bend, with why.
Point to the team's standards rather than restating them.>

## Constraints and assumptions

<Budget, dates, mandated technologies, contracts, regulatory limits, skills. Assumptions to
confirm, each with an owner role.>

## Current state in brief

<One paragraph and, if useful, one diagram reference: how things work today and the pain points.>

## Target state in brief

<One paragraph and one diagram reference: the end state in business terms first, then the main
technology moves. Keep it high level; detail belongs in the architecture definition document.>

## Key high-level requirements

<The handful of requirements that shape the design most. Full detail goes in the architecture
requirements specification.>

## Options considered

| Option | Summary | Fit to goals | Main risk | Rough cost signal |
|---|---|---|---|---|
| | | | | |

## Risks

| # | Risk | Likelihood | Impact | Mitigation | Owner (role) |
|---|---|---|---|---|---|
| 1 | | | | | |

## Next steps and decisions needed

| # | Decision or step | Who (role) | Needed by |
|---|---|---|---|
| 1 | | | <DD-Mmm-YYYY> |

## Maps to your IA and GDS

| Vision part | Usually supplied by |
|---|---|
| Summary, problem, drivers | IA Executive Summary; IA Solution Overview; GDS Preface (Background) |
| Business goals | IA Business Requirements; project charter (business justification) |
| Scope | project charter (scope); IA Solution Overview |
| Stakeholders | project charter (key stakeholders); GDS Preface (Target Audience) |
| Principles | GDS Guiding Principles; IA Compliance Summary (standards) |
| Constraints and assumptions | IA Project Assumptions |
| Key requirements | IA Summary of Requirements |
| Risks | IA Impact Assessment Risks / Issues List |

**New beyond IA and GDS:** measurable goals with a baseline and target, stakeholder concerns tied
to how the design answers them, an explicit current-state versus target-state contrast before any
design detail, and options compared at vision level.

## Sources

<Every document cited, with its library accession number or location.>

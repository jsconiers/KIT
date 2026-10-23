# Transition architecture: <initiative name>, <plateau name or number>

An example template for a TOGAF-style transition architecture: a stable, usable intermediate state
between the baseline and the target, what it delivers, and what is temporary in it. Write one per
plateau. Private to this Kit and used only on request. Copy it, change it to suit the team, and
point `memory/context/writing.md` at the copy. Delete the guidance lines in angle brackets when
filling it in.

Based on the structure of TOGAF deliverables (The Open Group); headings paraphrased. TOGAF is a
trademark of The Open Group. This template uses section structure only, written in our own words.

| Field | Value |
|---|---|
| Initiative | <project name or slug> |
| Plateau | <for example 1 of 3: coexistence> |
| Version | <0.1, 0.2, 1.0> |
| Prepared | <DD-Mmm-YYYY> |
| Prepared by | <role> |
| Reviewed by | <role or forum> |
| Planned start and end | <DD-Mmm-YYYY to DD-Mmm-YYYY> |
| Previous and next state | <baseline or plateau n-1; plateau n+1 or target> |
| Related documents | <architecture definition document, implementation and migration plan, GDS> |
| Classification | <internal or confidential> |

## 1. Purpose of this plateau

<Why stop here: the business value delivered, the risk retired, or the dependency it unblocks.>

## 2. What is in place at this plateau

| Domain | State at this plateau | Change from previous state |
|---|---|---|
| Business | | |
| Data | | |
| Application | | |
| Technology | | |
| Security | | |

<Reference a diagram for this plateau by file name.>

## 3. Gaps closed and gaps still open

| Gap ID (from the ADD) | Closed here | Still open, planned for |
|---|---|---|
| | <yes or partly> | <plateau or target> |

## 4. Work packages delivered

| Work package | Delivers | Owner (role) | Done when |
|---|---|---|---|
| | | | |

## 5. Coexistence and interoperability

<How old and new run side by side: data synchronisation, dual running, routing or cut-over of
traffic, user impact, and what must stay compatible.>

## 6. Temporary components

| Component | Why needed | Removed at | Removal owner (role) |
|---|---|---|---|
| | | <plateau or date> | |

## 7. Operations at this plateau

<Support model, monitoring, DR position, and runbooks that differ from the target, and any
reduced resilience accepted while here.>

## 8. Risks while in this state

| # | Risk | Likelihood | Impact | Mitigation | Owner (role) |
|---|---|---|---|---|---|
| 1 | | | | | |

## 9. Entry and exit criteria

<Entry: what must be true before moving into this state. Exit: the evidence needed to move on,
for example tests passed, operations acceptance, data reconciled.>

## 10. Rollback

<How to return to the previous state if this plateau fails, and the point after which that is no
longer possible.>

## Maps to your IA and GDS

| Transition part | Usually supplied by |
|---|---|
| 2 State at this plateau | GDS Migration (Functional Overview, Migration Flows), partly |
| 5 Coexistence | GDS Migration Flows; GDS Product Service Flows |
| 7 Operations | GDS Observability; GDS Disaster Recovery; GDS Failure/Recovery |
| 9 Entry and exit | your project lifecycle; an approval gate Go/No-Go |
| 10 Rollback | Implementation planner's change request (rollback and back-out) |
| Lab or pilot plateau | IA Lab Infrastructure; GDS Non-Prod Environment |

**New beyond IA and GDS:** this deliverable is mostly new. The GDS has one migration section;
neither template describes a named interim state with its own architecture, temporary components
and their removal dates, reduced-resilience risks while in the interim, or per-plateau entry and
exit criteria.

## Sources

<Every document cited, with its library accession number or location.>

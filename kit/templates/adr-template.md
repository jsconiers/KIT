# ADR-<nnnn>: <short decision title, stated as the choice made>

An example template for architecture decision records. Copy it, change it to suit the team, and
point `memory/context/decisions.md` at the copy. Delete the guidance lines in angle brackets when
filling it in.

| Field | Value |
|---|---|
| Status | <proposed, accepted, superseded by ADR-nnnn, or withdrawn> |
| Date decided | <DD-Mmm-YYYY, or "not decided" while proposed> |
| Decided by | <role or forum, for example architecture review board; not a person's name> |
| Project | <project name or slug> |
| Demand or ticket | <number, if any> |
| Related documents | <IA, GDS, or other documents, with version and section> |
| Related ADRs | <ADR-nnnn (supersedes / superseded by / relates to)> |
| Revisit by | <DD-Mmm-YYYY or the event that should trigger a review> |
| Classification | <internal or confidential> |

## Context

<The problem or need, in two to five sentences. What is happening, what forces the decision now,
and what is in and out of scope. Cite sources.>

## Decision drivers

- <Requirement, constraint, or quality attribute that matters most, for example availability
  target, cost ceiling, security baseline, delivery date>
- <...>

## Options considered

| Option | Summary | Pros | Cons |
|---|---|---|---|
| A. <name> | <one line> | <...> | <...> |
| B. <name> | <one line> | <...> | <...> |
| C. Do nothing | <what happens if nothing changes> | <...> | <...> |

## Decision

<The option chosen, stated plainly: "We will ...". Include any conditions or limits on it.>

## Rationale

<Why this option over the others, tied to the decision drivers. Say which drivers it trades off.>

## Consequences

- **Positive:** <what gets better>
- **Negative:** <costs, limits, or debt accepted>
- **Risks and mitigations:** <risk, and how it will be handled>
- **Standards and compliance:** <standards met, exceptions or waivers needed, controls affected>
- **Follow-up actions:** <action, owner by role, due date>

## Sources

- <Meeting minutes, review, or document, with date and section or page>
- <...>

## Change log

| Date | Change | By (role) |
|---|---|---|
| <DD-Mmm-YYYY> | Created as proposed | <role> |

# Red-team review: <document title>

An example template for an adversarial review of an impact assessment (IA) or design
specification (GDS) before peer review. The red team fills it in; the architect checks it and sends
the findings to the writers. Copy it, change it to suit the team, and point
`memory/context/standards.md` at the copy. Delete the guidance lines in angle brackets when filling
it in.

| Field | Value |
|---|---|
| Document | <document title, number, and version> |
| Based on | <the IA a GDS is based on, with its version, or "n/a"> |
| Project | <project id or name> |
| Reviewed by | <role, or "red team, checked by (role)"> |
| Date | <DD-Mmm-YYYY> |
| Version | <v1, v2, ...; never overwrite an earlier one> |
| Availability or DR tier | <as the design states it, or "not stated"> |
| Classification | <internal or confidential> |

## Verdict

<Survives, survives with fixes, or breaks, in one line. Then the worst failure scenario in one or two
lines.>

## What has to work

<The components, data stores, external dependencies, people, and scheduled jobs the design relies
on, and the main paths through them. Every finding below refers back to this list.>

## How findings are rated

- **Consequence:** critical (outage of a critical service, data loss beyond the RPO, a regulatory
  or security breach), major (degraded service, recovery beyond the RTO, costly rework), or minor
  (inconvenience, a workaround exists).
- **Likelihood:** likely, possible, or unlikely, with the reason.
- Findings are ordered by consequence, then likelihood. Ease of fix never changes the order.

## Findings, most consequential first

| ID | Consequence | Likelihood | Area | Failure scenario | Evidence | Mitigation |
|---|---|---|---|---|---|---|
| RT-01 | <critical, major, or minor> | <likely, possible, or unlikely: reason> | <area> | <what breaks, what happens next, who notices, how long until service is back> | <section or page, or "not stated"> | <suggested mitigation> |

<Area is one of: single point of failure, DR and recovery, scaling, blast radius, concentration,
operations, abuse path, or assumption.>

## RTO and RPO

| Measure | Stated | Achievable by the design | Gap | Evidence |
|---|---|---|---|---|
| RTO | <target, or "not stated"> | <what the restore or failover steps can achieve, or "can't tell"> | | |
| RPO | | | | |

## Assumptions that would break it

| Assumption | Stated or implied | What happens if it's false | Finding |
|---|---|---|---|
| <for example "peak volume stays under 500 requests a second"> | <section, or "implied"> | | <RT-nn> |

## Can't tell

<Each area the design doesn't say enough to judge, with the question that would settle it and who
should answer, by role.>

## Since the last red team

<For a second or later version: each earlier finding as fixed, partly fixed, or open. Delete this
section for a first review.>

## Handed on

<Abuse paths that need a full threat model (threat modeler), and anything for the standards
checker or the risk and compliance mapper, through Kit.>

## Sources

<The document and its version, the IA, diagram specs, and dependency maps used.>

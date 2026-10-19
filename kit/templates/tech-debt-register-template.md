# Tech debt register

An example template for the team's tech debt register. The future tech planner keeps it at
`radar/tech-debt.md` and links each item to the technology's lifecycle review, so debt shows up
when a verdict is due. Copy it, change it to suit the team, and point
`memory/context/future-tech.md` at the copy. Delete the guidance lines in angle brackets when
filling it in.

| Field | Value |
|---|---|
| Updated | <DD-Mmm-YYYY> |
| Kept by | <role> |
| Classification | <internal or confidential> |

## How to fill it in

- **Type:** architecture, code, infrastructure, security, data, documentation, or process.
- **Impact:** what it costs the business now, in one line: incidents, slower change, manual work,
  audit findings. Cite the source.
- **Risk:** high, medium, or low, from the likelihood and consequence of leaving it alone.
- **Rough cost to fix:** low, likely, and high effort or money, from the cost estimator where
  possible. Mark it "assumed" without a source.
- **Lifecycle link:** the lifecycle review (`lifecycle/<technology>.md`) and its verdict, so debt
  on a technology marked retire or migrate is visible when that work is planned.
- **Status:** open, planned, in progress, accepted (living with it, with a reason and a review
  date), or closed.
- People appear by role only. Dates are DD-Mmm-YYYY.

## Register

| Id | Item | System | Type | Impact | Risk | Rough cost to fix | Lifecycle link and verdict | Owner | Target date | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| TD-001 | <one line> | <system> | <type> | <impact, with source> | <high / medium / low> | <low / likely / high> | <lifecycle/<technology>.md: retire> | <role> | <DD-Mmm-YYYY> | <open> |

## Accepted debt

<Items the team has chosen to live with: why, who accepted it by role, and when to look again.>

| Id | Reason accepted | Accepted by | Review by |
|---|---|---|---|
| | | | |

## Closed

<Items fixed or retired, with the date and what closed them. Never delete a row; move it here.>

| Id | Closed | How |
|---|---|---|
| | | |

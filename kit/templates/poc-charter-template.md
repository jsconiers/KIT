# POC charter: <technology or product> for <problem>

An example template for proof-of-concept charters. Copy it, change it to suit the team, and point
`memory/context/poc.md` at the copy. Delete the guidance lines in angle brackets when filling it in.
A charter fits on two pages. No testing starts until it is approved.

| Field | Value |
|---|---|
| POC id | <POC-nnnn> |
| Status | <draft, approved, running, closed> |
| Sponsor | <role, not a person's name> |
| POC lead | <role; usually the architect> |
| Build lead | <role; usually engineering> |
| Vendor | <name, or "internal only"> |
| NDA | <"not needed" (internal), or "confirmed current by Legal on DD-Mmm-YYYY, expires DD-Mmm-YYYY"> |
| Start and timebox | <DD-Mmm-YYYY, N weeks> |
| Environment | <lab name or id, on-premises or cloud> |
| Data used | <synthetic, masked, or public; never production or confidential without written approval> |
| Classification | <internal or confidential> |
| Related | <demand, IA, radar entry, or ADR> |

## Problem and why now

<Two to four sentences: the business or technical problem, and what forces the question now.>

## Hypothesis

<One sentence that the POC proves or disproves, for example "Product X can replace Y for Z with
latency under N ms and no change to the upstream systems.">

## Success criteria

<Measurable criteria, each with a target and how it will be measured. Mark the must-haves; a
must-have that fails means no-go.>

| # | Criterion | Target | How measured | Must-have |
|---|---|---|---|---|
| 1 | | | | yes / no |

## Scope

- **In:** <what will be tested>
- **Out:** <what won't, and why>

## Roles (RACI)

| Activity | Responsible | Accountable | Consulted | Informed |
|---|---|---|---|---|
| Charter and test plan | | | | |
| Build and run tests | | | | |
| Security and data review | | | | |
| Verdict | | | | |

## Resources and cost

<People and time by role, lab resources, licences or trial terms, and any cloud spend cap.>

## Risks and constraints

<Security, data, vendor, schedule, and dependency risks, each with a mitigation.>

## Exit criteria

<When the POC stops: timebox reached, a must-have fails, or all criteria are measured. Who decides
an extension.>

## Teardown

<What gets deleted or returned when the POC closes, and by when: lab resources, accounts, data,
licences, loaned hardware.>

## Approval

| Role | Decision | Date |
|---|---|---|
| Sponsor | <approved / changes needed> | |
| Build lead | | |

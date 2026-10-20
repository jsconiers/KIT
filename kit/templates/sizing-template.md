# Sizing: <system or change>

An example template for recording a rough-order sizing. `kit-sizing` produces the figures from the
workload inputs and lists every assumption; this template keeps them with the reasoning, ready for
the cost estimator. Copy it, change it to suit the team, and point `memory/context/costs.md` at the
copy. Delete the guidance lines in angle brackets when filling it in. Rough order only: confirm with
load testing before committing to numbers.

| Field | Value |
|---|---|
| System or change | <name> |
| Prepared by | <role> |
| Date | <DD-Mmm-YYYY> |
| Related | <demand, IA, GDS, POC> |
| Classification | <internal or confidential> |

## Workload

| Input | Value | Source |
|---|---|---|
| Users, or average requests per second | | <requirement, measurement, or assumption> |
| Peak factor and headroom | | |
| Read share | | |
| Request and response size | | |
| Data stored per write, retention | | |
| Growth per year, horizon | | |
| HA/DR tier | | |

## Results

<Paste kit-sizing's tables (low, likely, high) for compute, storage, and network.>

## Assumptions

<Paste kit-sizing's assumption list, and mark the ones that matter most and how they were chosen.>

## Risks

<Where the estimate could be badly wrong: unknown load, unusual payloads, batch jobs, licensing tied
to cores.>

## Hand-off

<Figures passed to the cost estimator on DD-Mmm-YYYY, with the tier and horizon.>

# POC test plan: <POC id> <short title>

An example template for POC test plans. The POC lead agent fills it in from an approved charter:
one or more test cases for every success criterion, so nothing in the charter goes untested. Copy
it, change it to suit the team, and point `memory/context/poc.md` at the copy. Delete the guidance
lines in angle brackets when filling it in.

| Field | Value |
|---|---|
| POC id and charter | <POC-nnnn, charter version and date> |
| Version | <0.1, 0.2, ...> |
| Environment | <lab id; on-premises or cloud; versions under test> |
| Test data | <synthetic, masked, or public, and where it comes from> |
| Testers | <roles> |
| Status | <draft, approved, running, complete> |
| Date | <DD-Mmm-YYYY> |
| Classification | <internal or confidential> |

## Coverage

<Every charter criterion maps to at least one test case. A criterion with no test case is a gap
and blocks approval.>

| Criterion # | Criterion | Test cases |
|---|---|---|
| 1 | | T-01, T-02 |

## Entry criteria

<What must be true before testing starts: charter approved, NDA confirmed (vendor POCs), lab built
and checked, test data loaded, monitoring in place.>

## Test cases

<One block per test case. Keep steps short enough that someone else could repeat them.>

### T-01: <title>

- **Criterion:** <#>
- **Type:** <functional, performance, resilience, security, operability, integration>
- **Preconditions:** <state before the test>
- **Steps:** <numbered steps>
- **Expected result:** <what passes, with the target from the charter>
- **Evidence to capture:** <metrics, logs, screenshots, config exported>
- **Result:** <pass, fail, blocked, not run> | **Actual:** <measured value> | **Evidence:** <log ref>

## Negative and failure tests

<What happens when a component fails, a credential expires, the network drops, or input is bad.
Required for anything that might go to production.>

## Security checks

<Authentication, authorization, encryption in transit and at rest, logging, and secrets handling,
checked against the team's security baseline.>

## Schedule

| Week | Activities | Owner |
|---|---|---|
| 1 | | |

## Exit and suspension criteria

<When testing stops early (a must-have fails, the environment is unusable, the vendor can't
support) and how a pause or restart is decided.>

## Evidence log

<Where evidence lives (the POC's library folder, `evidence/`) and how each item is named:
`T-nn-<date>-<what>`.>

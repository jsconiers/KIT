# Traceability matrix: <project>

An example template for tracing each requirement in an impact assessment (IA) to the design, the
tests, the change, and any POC. Copy it, change it to suit the team, and point
`memory/context/writing.md` at the copy. `kit-trace <project>` drafts one from the project's
documents, marking keyword matches "(inferred)" for a person to check; `kit-trace <project> --write`
saves it in the project's `traceability/` folder. Delete the guidance lines in angle brackets when
filling it in.

| Field | Value |
|---|---|
| Project | <project name> |
| Impact assessment | <document and version> |
| Design specification | <document and version> |
| Test plan | <document and version> |
| Change request | <document and version, or "not yet written"> |
| POC | <POC id and verdict, or "none"> |
| Prepared by | <role, not a person's name> |
| Updated | <DD-Mmm-YYYY> |
| Classification | <internal or confidential> |

## Summary

<Counts: requirements in the IA, addressed in the GDS, tested, with a change step, and each kind of
gap. One line on what has to happen before the change board.>

## Matrix

| Requirement | Statement | GDS section | Test cases | Change steps | POC / verdict | Gaps |
|---|---|---|---|---|---|---|
| <REQ-001> | <the requirement, as the IA states it> | <section number and title> | <TC-nn> | <step n> | <POC-nnnn: go, no-go, or pivot; or none> | <none, or the gap> |

## Gaps

### Not addressed in the GDS

<Each requirement the design doesn't carry, with the decision: add it to the GDS, or record why not
and who agreed, by role.>

### Addressed but untested

<Each requirement with no test case. Every requirement gets a test case or a stated reason why not
(for example, "covered by the platform's certification"), recorded in the test plan.>

### Tested but no change step

<Each tested requirement that no step in the change request delivers or validates.>

### Orphan test cases

<Each test case that traces to no requirement: link it, or mark it as a regression or rollback test
with the reason.>

## How it was matched

<First by requirement ID, then by a cited section ("IA 3.1", "GDS section 4.2"), then by shared
keywords, marked "(inferred)". Confirm each inferred link, or add the requirement's ID to the
document so the next run matches it directly.>

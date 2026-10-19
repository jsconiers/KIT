# Innovation intake: <idea>

An example template for an idea entering the innovation funnel. Every idea passes each gate in
order, assess, then POC, then pilot, then adopt or kill, and no gate is skipped. The future tech
planner keeps the funnel at `radar/innovation.md`. Copy it, change it to suit the team, and point
`memory/context/future-tech.md` at the copy. Delete the guidance lines in angle brackets.

| Field | Value |
|---|---|
| Idea id | <IDEA-nnnn> |
| Raised by | <role> |
| Raised on | <DD-Mmm-YYYY> |
| Stage | <intake, assess, POC, pilot, adopted, killed> |
| Classification | <internal or confidential> |

## The idea

<What it is, in two sentences.>

## Problem and who benefits

<The problem it solves, who has it (roles or teams), and how they cope today.>

## Rough value and effort

| | Low | Likely | High |
|---|---|---|---|
| Value (time, cost, risk reduced) | | | |
| Effort to try | | | |

## Risks

<Security, data, cost, vendor, and adoption risks. Note precedent: has it been tried before?>

## Gates

<Each gate records the decision, the approver by role, the date, and the evidence. An idea moves
only after a "go" at its current gate.>

| Gate | Question | Approver (role) | Decision | Date | Evidence |
|---|---|---|---|---|---|
| Assess | Is it worth a POC? | | go / kill / park | | research brief, precedent |
| POC | Does it work here? | | go / kill / pivot | | POC findings |
| Pilot | Does it work at small scale in real use? | | go / kill | | pilot results |
| Adopt | Do we adopt it? | | adopt / kill | | radar ballot, ADR |

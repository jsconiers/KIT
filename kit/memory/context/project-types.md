# Project types

The kinds of project Kit's staff work on, the folder each gets under the library, its pipeline
stages, and which agents and templates it uses. `kit-project new <type> <slug>` creates the folder
skeleton (dry run by default). Every project lives at `<library root>/artifacts/<slug>/` (see
`library.md`).

## delivery

A change to a production system: demand to change board.

- **Folders:** `intake/`, `ia/`, `gds/`, `diagrams/`, `reviews/`, `implementation/`, `changeboard/`,
  `meetings/`, `status/`, `estimates/`, `precedent/`.
- **Stages:** intake, impact assessment, design specification, review, implementation plan, change
  board, done.
- **Agents:** intake triager, precedent finder, IA writer, GDS writer, diagrammer, reviewer,
  standards checker, risk and compliance mapper, cost estimator, PMO estimator, implementation
  planner, change board prep, decision recorder, status reporter.
- **Templates:** your team's IA and GDS templates (see `writing.md`), stakeholder map, build, buy,
  or partner, ADR.

## poc

A proof of concept: charter to verdict.

- **Folders:** `poc/`, `labs/`, `meetings/`, `research/`, `precedent/`, `status/`.
- **Stages:** charter, lab request and runbook, test plan, running, scoring, findings, verdict.
- **Agents:** precedent finder, researcher, POC lead, lab planner, meeting scribe, decision
  recorder, curator, training lead (knowledge transfer after the verdict).
- **Templates:** POC charter, test plan, scorecard, findings, lab request, lab runbook, vendor
  meeting.

## lab

A lab environment on its own, not tied to one POC.

- **Folders:** `labs/`, `meetings/`, `status/`.
- **Stages:** request, approval, build, running, teardown, closed.
- **Agents:** lab planner, standards checker, curator (outcome as precedent).
- **Templates:** lab request, lab runbook.

## training

A learning effort for the owner or the team.

- **Folders:** `training/`, `materials/`, `labs/`.
- **Stages:** skills gap, plan, learning, checkpoints, done.
- **Agents:** training lead, lab planner, deck builder, scheduler (focus time).
- **Templates:** learning plan, learning path, training kit, skills matrix.

## research

A question that needs investigation before a decision.

- **Folders:** `research/`, `precedent/`, `meetings/`.
- **Stages:** question, precedent check, research, brief, decision.
- **Agents:** precedent finder, researcher, curator, decision recorder.
- **Templates:** research brief, build, buy, or partner, ADR.

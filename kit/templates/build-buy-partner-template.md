# Build, buy, or partner: <capability>

An example template for comparing ways to get a capability: build it in-house, buy a product or
service, or partner with another team or company. The completed analysis becomes the main source
for an ADR, which the decision recorder writes once the decision is made. Copy it, change it to
suit the team, and point `memory/context/decisions.md` at the copy. Delete the guidance lines in
angle brackets when filling it in. It fits on three pages.

| Field | Value |
|---|---|
| Capability | <what's needed, in one line> |
| Requested by | <role> |
| Decides | <role or forum, for example architecture review board> |
| Date | <DD-Mmm-YYYY> |
| Related | <demand, IA, POC id, radar entry, precedent note> |
| Status | <draft, recommended, decided (ADR-nnnn)> |
| Classification | <internal or confidential> |

## Need

<The problem, who has it, and what happens if nothing is done. Two to four sentences.>

## Requirements

<The must-haves (a failed must-have rules an option out) and the nice-to-haves. Number them so the
options can be scored against them.>

| # | Requirement | Must-have |
|---|---|---|
| R1 | | yes / no |

## Options

<At least one of each kind where it's realistic. "Do nothing" is a valid baseline.>

### Build

<What would be built, by whom (role or team), on what platform, and how long it would take.>

### Buy

<Candidate products or services, with the evidence behind each: POC findings, research briefs,
vendor meeting notes (claims shown, documented, or only claimed).>

### Partner

<Who (an internal team, a subsidiary, a vendor relationship), what each side provides, and how the
arrangement is governed.>

## Comparison

<Score 0 to 5 per criterion, with evidence. Weights add up to 100. Adjust the criteria to the
decision; keep the must-have gate.>

| Criterion | Weight | Build | Buy | Partner |
|---|---|---|---|---|
| Meets the must-haves (gate) | gate | pass / fail | pass / fail | pass / fail |
| Fit to requirements | 20 | | | |
| Time to deliver | 15 | | | |
| Total cost of ownership, 3 to 5 years | 15 | | | |
| Security, compliance, and data handling | 15 | | | |
| Operability and support | 10 | | | |
| Strategic control and lock-in | 10 | | | |
| Skills: have them, can get them | 10 | | | |
| Exit and reversibility | 5 | | | |
| **Total** | **100** | | | |

## Total cost of ownership

<Rough order of magnitude, low, likely, and high, from the cost estimator where possible. Include
build effort, licences or fees, infrastructure, support, and exit costs. Mark assumptions.>

| Cost | Build | Buy | Partner |
|---|---|---|---|
| One-time | | | |
| Yearly | | | |
| Exit | | | |

## Risks

<The top risks for each option, with a mitigation.>

## Recommendation

<The recommended option, the three main reasons tied to the comparison, and what would change the
answer. This is a recommendation; the decider in the table above decides.>

## Decision

| Decided by (role) | Option | Date | ADR |
|---|---|---|---|
| | | | ADR-nnnn |

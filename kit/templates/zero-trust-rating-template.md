# Zero Trust rating: <design or system>

An example template for rating a design against the CISA Zero Trust Maturity Model (version 2.0,
2023). The standards checker fills it in when Kit asks for one; the architect checks it. Copy it,
change it to suit the team, and point `memory/context/standards.md` at the copy. Delete the
guidance lines in angle brackets when filling it in. The stage descriptions below are a short
paraphrase for orientation; read the model itself for the full criteria.

| Field | Value |
|---|---|
| Design | <document title, number, and version> |
| Project | <project id or name> |
| Rated by | <role, or "standards checker, checked by (role)"> |
| Date | <DD-Mmm-YYYY> |
| Model | CISA Zero Trust Maturity Model, version 2.0 (2023) |
| Scope | <the systems, environments, and users the rating covers> |
| Target stage | <the stage the team is aiming for, if set; otherwise "not set"> |
| Classification | <internal or confidential> |

## Stages

- **Traditional:** set up by hand, static policies, broad implicit trust inside the network,
  little sharing of signals between pillars.
- **Initial:** some automation and central policy, early use of context (who, what device, where)
  in access decisions, some pillars starting to share data.
- **Advanced:** automated, centrally managed controls across pillars, access decisions that use
  several signals, and responses partly automated.
- **Optimal:** fully automated, dynamic, least-privilege access decided per request from
  continuous signals, with pillars integrated end to end.

Rate on what the design says. A row the design doesn't cover is "can't rate", with the question that
would settle it; never rate up on silence.

## Ratings

| Area | Stage | Evidence (design section or page) | Gaps to the next stage | Question or owner (role) |
|---|---|---|---|---|
| Identity | <Traditional, Initial, Advanced, Optimal, or can't rate> | <section and a short paraphrase> | <what's missing> | <question, or owner by role> |
| Devices | | | | |
| Networks | | | | |
| Applications and Workloads | | | | |
| Data | | | | |
| Visibility and Analytics (cross-cutting) | | | | |
| Automation and Orchestration (cross-cutting) | | | | |
| Governance (cross-cutting) | | | | |

## Summary

<The overall picture in two or three lines: the lowest-rated areas first, and whether the design
reaches the target stage. Don't average the stages into one score.>

## Gaps, most consequential first

<Each gap with the area, what the design would need to change, and whether it's a standards gap
(see the standards check) or a waiver candidate.>

## Sources

<The design and its version, the standards check it goes with, and the model by name and version.>

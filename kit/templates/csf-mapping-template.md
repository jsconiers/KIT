# NIST CSF 2.0 mapping: <design or system>

An example template for mapping a design, an impact assessment (IA) or a general design
specification (GDS), to the six Functions and 22 Categories of NIST CSF 2.0 (NIST CSWP 29, Feb
2024). The risk and compliance mapper fills it in when the framework profile in
`memory/context/compliance.md` marks NIST CSF 2.0 as applying, then runs `kit-csf` on it; the
architect checks it. Copy it, change it to suit the team, and point `memory/context/compliance.md`
at the copy. Delete the guidance lines in angle brackets when filling it in. The Function notes below
are a short paraphrase for orientation; read the framework itself for the Subcategories and their
full text.

| Field | Value |
|---|---|
| Design | <document title, number, and version> |
| Project | <project id or name> |
| Mapped by | <role, or "risk and compliance mapper, checked by (role)"> |
| Date | <DD-Mmm-YYYY> |
| Framework | NIST CSF 2.0 (NIST CSWP 29, Feb 2024) |
| Scope | <the systems, environments, and data classes the mapping covers, from the framework profile> |
| Profile or target tier | <the team's target profile or tier (1 Partial, 2 Risk Informed, 3 Repeatable, 4 Adaptive), if set; otherwise "not set"> |
| Framework owner | <role, from the framework profile> |
| Classification | <internal or confidential> |

## Functions

- **Govern (GV):** the organization's context, risk strategy, roles, policy, oversight, and supply
  chain risk; it frames the other five.
- **Identify (ID):** knowing the assets and the risks to them, and improving from what's learned.
- **Protect (PR):** safeguards: identity and access, training, data, platforms, and resilient
  infrastructure.
- **Detect (DE):** finding and analyzing possible attacks and compromises.
- **Respond (RS):** acting on a detected incident: managing, analyzing, reporting, and containing
  it.
- **Recover (RC):** restoring assets and operations after an incident, and communicating about it.

## How to fill it in

- **Addressed?** is one of: **yes** (the design covers it; cite the section), **partial**, **no**,
  or **not applicable** (say why in the Gap column). Leave nothing blank: `kit-csf` lists blanks.
- **Design evidence:** the section or page, and a short paraphrase. Rate on what the design says;
  silence is "no" or a question, never "yes".
- **Gap:** what's missing, in one line, for "partial" and "no".
- **Owner (role):** who closes the gap or answers the question, by role, not by name.
- **Tier or target note:** optional. Where this category needs to reach, if the team sets targets.
- These statuses describe the document, not a compliance decision; that's the framework owner's.
- Keep the Category IDs as they are. `kit-csf` checks them against `shared/data/csf2.json`.

## Mapping

| Function | ID | Category | Addressed? | Design evidence (section) | Gap | Owner (role) | Tier or target note |
|---|---|---|---|---|---|---|---|
| Govern | GV.OC | Organizational Context | <yes, partial, no, or not applicable> | <section and a short paraphrase> | <what's missing> | <role> | <optional> |
| Govern | GV.RM | Risk Management Strategy | | | | | |
| Govern | GV.RR | Roles, Responsibilities, and Authorities | | | | | |
| Govern | GV.PO | Policy | | | | | |
| Govern | GV.OV | Oversight | | | | | |
| Govern | GV.SC | Cybersecurity Supply Chain Risk Management | | | | | |
| Identify | ID.AM | Asset Management | | | | | |
| Identify | ID.RA | Risk Assessment | | | | | |
| Identify | ID.IM | Improvement | | | | | |
| Protect | PR.AA | Identity Management, Authentication, and Access Control | | | | | |
| Protect | PR.AT | Awareness and Training | | | | | |
| Protect | PR.DS | Data Security | | | | | |
| Protect | PR.PS | Platform Security | | | | | |
| Protect | PR.IR | Technology Infrastructure Resilience | | | | | |
| Detect | DE.CM | Continuous Monitoring | | | | | |
| Detect | DE.AE | Adverse Event Analysis | | | | | |
| Respond | RS.MA | Incident Management | | | | | |
| Respond | RS.AN | Incident Analysis | | | | | |
| Respond | RS.CO | Incident Response Reporting and Communication | | | | | |
| Respond | RS.MI | Incident Mitigation | | | | | |
| Recover | RC.RP | Incident Recovery Plan Execution | | | | | |
| Recover | RC.CO | Incident Recovery Communication | | | | | |

## Coverage summary

<Paste the table from `kit-csf <this file>`. Coverage counts yes as 1 and partial as half, over the
categories that apply; "not applicable" rows are left out, and blank rows are listed, not counted.>

| Function | Yes | Partial | No | Not applicable | Blank | Coverage |
|---|---|---|---|---|---|---|
| Govern (GV) | | | | | | |
| Identify (ID) | | | | | | |
| Protect (PR) | | | | | | |
| Detect (DE) | | | | | | |
| Respond (RS) | | | | | | |
| Recover (RC) | | | | | | |
| Overall | | | | | | |

<The picture in two or three lines: the weakest Functions first, and whether the design reaches the
target, if one is set. A percentage is a reading aid, not a compliance score.>

## Gaps, most consequential first

<Each "no" and "partial" with the category ID, what the design would need to change, and the owner
by role. These go into the compliance map's control table and open questions.>

## Sources

<The design and its version, the compliance map it goes with, and NIST CSF 2.0 (NIST CSWP 29, Feb
2024).>

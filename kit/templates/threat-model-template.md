# Threat model: <design or system>

An example template for a STRIDE threat model of a design, one data flow at a time. The threat
modeler fills it in from the design specification (GDS) or impact assessment (IA) and any diagram
specs; the architect checks it. Copy it, change it to suit the team, and point
`memory/context/standards.md` at the copy. Delete the guidance lines in angle brackets when filling
it in.

| Field | Value |
|---|---|
| Design | <document title, number, and version> |
| Diagrams used | <diagram spec files and versions, or "none"> |
| Project | <project id or name> |
| Modeled by | <role, or "threat modeler, checked by (role)"> |
| Date | <DD-Mmm-YYYY> |
| Version | <v1, v2, ...; never overwrite an earlier one> |
| Scope | <the systems, environments, and flows the model covers, and what it leaves out> |
| Risk rating rule | <the scale from compliance.md, by name, or the default below> |
| Classification | <internal or confidential> |

## Summary

<Counts of threats by risk (high, medium, low) and of gaps, and the highest risks in two or three
lines.>

## Elements

| ID | Element | Type | Data class | Evidence |
|---|---|---|---|---|
| E-01 | <for example "Customer browser"> | external entity | <class> | <section or diagram> |
| P-01 | <for example "Order API"> | process | | |
| D-01 | <for example "Orders database"> | data store | | |

## Trust boundaries

| ID | Boundary | Between | Evidence |
|---|---|---|---|
| TB-01 | <for example "Internet to perimeter"> | <E-01 and P-01> | <section or diagram> |

## Data flows

| ID | From | To | Protocol | Data and class | Boundaries crossed | Authentication | Encryption | Evidence |
|---|---|---|---|---|---|---|---|---|
| F-01 | <E-01> | <P-01> | <for example HTTPS> | | <TB-01> | <as the design says, or "not stated"> | <as the design says, or "not stated"> | |

## Risk rating

<If compliance.md sets a scale, name it and use it here. Otherwise use this default and keep the
rule visible:>

- **Likelihood (L)** and **impact (I)**, each 1 (low), 2 (medium), or 3 (high).
- **Risk** = L x I: 1 to 2 is low, 3 to 4 is medium, 6 to 9 is high.
- Rate the residual risk, after the controls the design already names.

## Threats

STRIDE: Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of
privilege. Work through every category for each boundary-crossing flow and each element; skip one
only with a reason.

- **ATT&CK:** MITRE ATT&CK Enterprise technique IDs where one fits (for example T1078), from
  `kit-controls map <this file>`; mark a suggestion you haven't confirmed "(suggested)", and leave it
  blank when nothing fits.
- **800-53:** NIST SP 800-53 Rev 5 control IDs (for example AC-2, IA-2(1)) that would close the gap,
  by ID only; blank when there's no gap.

| ID | Flow or element | STRIDE | Threat | ATT&CK | Existing control (evidence) | Gap | 800-53 | L | I | Risk | Mitigation (owner if another team) | Test case ID |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T-01 | <F-01> | <category> | <the threat, concretely for this design> | <technique IDs, or blank> | <control and section, or "none stated"> | <what's missing, or "none"> | <control IDs for the gap> | | | <low, medium, or high> | <design-level mitigation> | <TC-01; the test itself is in the test-case table> |

## Categories skipped

| Flow or element | STRIDE | Reason |
|---|---|---|
| <D-01> | <Spoofing> | <for example "covered by the flows into it"> |

## Controls, for the risk and compliance mapper

| Control | Existing or missing | Threats it answers | 800-53 | Evidence |
|---|---|---|---|---|
| <for example "Mutual TLS between services"> | <existing, missing, or inherited, unverified> | <T-01, T-04> | <for example SC-8, IA-9; required for a missing control> | <section, or "proposed"> |

## Conflicts and defects

| Where | What the design says | What conflicts with it (IA, another section, a figure) | Why it matters |
|---|---|---|---|
| <section or figure> | <statement> | <the conflicting statement> | <threat or gap it affects> |

## Test cases, for the implementation planner

| ID | Threat | Test | Expected result |
|---|---|---|---|
| TC-01 | <T-01> | <what to try> | <what should happen, and what should be logged> |

## Not stated

<What the design doesn't say that the model needs, as questions for the writers or the architect,
by role.>

## Sources

<The design and its version, the IA, the diagram specs, and the setup files used. When the model
cites ATT&CK or 800-53, name the versions `kit-controls` reports and keep MITRE's notice:>

MITRE ATT&CK®: © 2026 The MITRE Corporation. This work is reproduced and distributed with the
permission of The MITRE Corporation. NIST SP 800-53 Rev 5: a US government work.

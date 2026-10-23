# Architecture requirements specification: <initiative name>

An example template for a TOGAF-style architecture requirements specification: the measurable
requirements, constraints, and success criteria the architecture must meet, each with an ID that
the design, tests, and change records can trace. Private to this Kit and used only on request; it
can extend IA section 3 instead of replacing it. Copy it, change it to suit the team, and point
`memory/context/writing.md` at the copy. Delete the guidance lines in angle brackets when filling
it in.

Based on the structure of TOGAF deliverables (The Open Group); headings paraphrased. TOGAF is a
trademark of The Open Group. This template uses section structure only, written in our own words.

| Field | Value |
|---|---|
| Initiative | <project name or slug> |
| Demand or ticket | <number> |
| Version | <0.1, 0.2, 1.0> |
| Prepared | <DD-Mmm-YYYY> |
| Prepared by | <role> |
| Requirements owner | <role, usually the sponsor or business owner> |
| Approved | <DD-Mmm-YYYY, or "not approved"> |
| Related documents | <architecture vision, architecture definition document, IA, GDS> |
| Classification | <internal or confidential> |

## 1. Purpose and scope

<Which architecture these requirements govern and which domains they cover.>

## 2. Success measures

| ID | Measure | Baseline | Target | How measured | Owner (role) |
|---|---|---|---|---|---|
| SM-01 | | | | | |

## 3. Requirements

<One row per requirement. Write each so a test can prove it. Priority: must, should, could.
Source: the document, meeting, or stakeholder role it came from.>

### 3.1 Business

| ID | Requirement | Priority | Source | Acceptance test |
|---|---|---|---|---|
| BR-01 | | | | |

### 3.2 Functional

| ID | Requirement | Priority | Source | Acceptance test |
|---|---|---|---|---|
| FR-01 | | | | |

### 3.3 Non-functional

<Cover at least performance, scalability, availability, recovery (RTO and RPO), resiliency,
management, monitoring, interoperability, retention, regulatory, and security. Delete categories
that don't apply and say so.>

| ID | Category | Requirement | Target value | Priority | Source | Acceptance test |
|---|---|---|---|---|---|---|
| NFR-01 | | | | | | |

### 3.4 Infrastructure and connectivity

| ID | Requirement | Priority | Source | Acceptance test |
|---|---|---|---|---|
| IR-01 | | | | |

### 3.5 Data

| ID | Requirement (classification, residency, retention, quality, ownership) | Priority | Source | Acceptance test |
|---|---|---|---|---|
| DR-01 | | | | |

### 3.6 Interoperability and integration

| ID | Requirement (interfaces, standards, protocols, partner systems) | Priority | Source | Acceptance test |
|---|---|---|---|---|
| INT-01 | | | | |

### 3.7 Service management and operations

| ID | Requirement (support model, monitoring, change, incident, capacity) | Priority | Source | Acceptance test |
|---|---|---|---|---|
| OPS-01 | | | | |

## 4. Constraints

| ID | Constraint | Imposed by (role, policy, or contract) |
|---|---|---|
| C-01 | | |

## 5. Assumptions

| ID | Assumption | Owner (role) | Confirm by |
|---|---|---|---|
| AS-01 | | | <DD-Mmm-YYYY> |

## 6. Requirements arising from gaps

<Requirements that come from the gap analysis in the architecture definition document, each linked
to its gap ID.>

## 7. Traceability

<Each requirement ID to the design section, test case, and change record that covers it. Use
`traceability-matrix-template.md` and `kit-trace`.>

## 8. Requirements change log

| Date | ID | Change | Reason | Approved by (role) |
|---|---|---|---|---|
| <DD-Mmm-YYYY> | | <added, changed, removed> | | |

## Maps to your IA and GDS

| Specification part | Usually supplied by |
|---|---|
| 3.1 Business | IA Business Requirements |
| 3.2 Functional | IA Functional Requirements |
| 3.3 Non-functional | IA Non-Functional Requirements (Performance, Scalability, Availability, Recovery, Resiliency, Management, Monitoring, Interoperability, Document Retention, Regulatory, Security Considerations); GDS RTO and RPO |
| 3.4 Infrastructure and connectivity | IA Infrastructure Requirements; IA Connectivity Requirements |
| 3.6 Interoperability | IA Interoperability Requirements; IA Integrations |
| 4 Constraints | IA Compliance Summary (data centre, network, infrastructure, security standards) |
| 5 Assumptions | IA Project Assumptions |
| 7 Traceability | `traceability-matrix-template.md` (IA to GDS, test plan, change request, POC) |

**New beyond IA and GDS:** requirement IDs, priority, source, and an acceptance test on every row;
success measures with a baseline and target; data and service-management requirements as their own
groups; requirements derived from gaps; and a change log for requirements after approval.

## Sources

<Every document cited, with its library accession number or location.>

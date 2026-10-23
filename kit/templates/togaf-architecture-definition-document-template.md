# Architecture definition document: <initiative name>

An example template for a TOGAF-style architecture definition document: the baseline and target
architecture in each domain (business, data, application, technology), the gaps between them, and
the reasoning behind the target. Private to this Kit and used only on request; for infrastructure
delivery the IA and GDS remain the documents of record, and this one can point to their sections
instead of repeating them. Copy it, change it to suit the team, and point
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
| Reviewed by | <role or forum> |
| Approved | <DD-Mmm-YYYY, or "not approved"> |
| Related documents | <architecture vision, requirements specification, IA, GDS, ADRs> |
| Classification | <internal or confidential> |

## 1. Purpose and scope

<What this document defines, the domains covered, the depth (conceptual, logical, physical), and
what is out of scope.>

## 2. Goals, drivers, and principles

<Short: link the architecture vision and list only the principles that shaped choices below.>

## 3. Business architecture

### 3.1 Baseline

<Business capabilities, processes, organisation units, and services affected today. Who uses the
system and for what.>

### 3.2 Target

<How those capabilities, processes, and services change. New or retired business services.>

### 3.3 Gaps

| # | Gap (baseline to target) | Type | Resolved by |
|---|---|---|---|
| B1 | | <new, changed, removed> | <work package or decision> |

## 4. Data architecture

### 4.1 Baseline

<Main data entities and stores, owners, classification, flows between systems, retention.>

### 4.2 Target

<Target stores and flows, master and reference data, classification and protection, retention and
deletion, data residency.>

### 4.3 Gaps

| # | Gap | Type | Resolved by |
|---|---|---|---|
| D1 | | | |

## 5. Application architecture

### 5.1 Baseline

<Applications and services in scope, their interfaces and integrations, and known pain points.>

### 5.2 Target

<Target applications and services, interfaces, integration patterns, and what is retired.>

### 5.3 Gaps

| # | Gap | Type | Resolved by |
|---|---|---|---|
| A1 | | | |

## 6. Technology architecture

### 6.1 Baseline

<Platforms, hosting (on-premises and cloud), network, storage, compute, identity, monitoring, and
management as they are today. Cite CMDB records or the dependency map.>

### 6.2 Target

<Target platforms and topology, resiliency (HA, backup, DR, isolated recovery), connectivity,
monitoring and management, and environments. Reference diagrams by file name.>

### 6.3 Gaps

| # | Gap | Type | Resolved by |
|---|---|---|---|
| T1 | | | |

## 7. Security architecture

<Cross-domain: trust boundaries, identity and access, encryption, logging, and how the target meets
the security baseline. Link the threat model if one exists.>

## 8. Consolidated gap analysis

| Gap | Domain | Depends on | Priority | Work package |
|---|---|---|---|---|
| | | | | |

<Group related gaps into candidate work packages; these feed the transition architecture and the
implementation and migration plan.>

## 9. Impact analysis

<What else the target touches: upstream and downstream systems, operations, support, licences,
skills, and regulatory obligations.>

## 10. Rationale and decisions

<Why the target looks as it does: options rejected and why. Link each ADR by number.>

## 11. Requirements traceability

<Each requirement ID from the architecture requirements specification against the section that
meets it. Use `traceability-matrix-template.md` for a full matrix.>

## 12. Open issues

| # | Issue | Owner (role) | Due |
|---|---|---|---|
| 1 | | | <DD-Mmm-YYYY> |

## Maps to your IA and GDS

| ADD part | Usually supplied by |
|---|---|
| 1-2 Purpose, goals, principles | IA Executive Summary, IA Solution Overview; GDS Introduction, 1.2 Guiding Principles |
| 3 Business architecture | IA Business Requirements (requirements only; neither template describes business architecture) |
| 4 Data architecture | IA Non-Functional (Document Retention, Regulatory); IA Security Architecture (Data Security, Confidential Data); GDS Data Protection Plan; GDS Database Services; GDS Data Retention |
| 5 Application architecture | IA Integrations; GDS Product Systems Architecture; GDS Product Service Flows |
| 6 Technology architecture (target) | IA 4.1-4.8 (Topology, Connectivity and Flows, Resiliency, On-Prem, Cloud, Monitoring / Management, Lab); IA 3.4-3.5 Infrastructure and Connectivity Requirements; GDS 3-4 Physical and Logical Network Topology, 6 External Connectivity, 7 Time Services, 8 Network Management, 9 Observability, 10 Disaster Recovery, 12 Failure/Recovery, 13 Non-Prod, 14 Systems Architecture, 15 Cloud Architecture |
| 7 Security architecture | IA Security Architecture; GDS Management Security Domains; GDS Security and Compliance; GDS Security Considerations |
| 9 Impact analysis | IA as a whole; dependency mapper output |
| 10 Rationale | GDS Guiding Principles (partly); ADRs |
| 12 Open issues | IA Risks / Issues List |

**New beyond IA and GDS:** an explicit baseline for each domain (both templates describe mainly the
target), per-domain gap tables and a consolidated gap analysis grouped into work packages, business
and data architecture as their own views rather than as requirements, and a rationale section tied
to ADRs.

## Sources

<Every document cited, with its library accession number or location.>

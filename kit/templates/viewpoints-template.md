# DoDAF-style viewpoints: <design or system>

Copy it, change it to suit the team, and point `memory/context/diagrams.md` at the copy. An example
template for four DoDAF-style viewpoint drafts made from a design specification (GDS). `kit-viewpoints`
fills in the element tables from the GDS and builds a draw.io file per view; the diagrammer checks
them against the standard, and the architect checks them against the design. Delete the guidance
lines in angle brackets when filling it in. The views are named by their DoDAF 2.02 IDs (a public
US Department of Defense framework); the descriptions here are a short paraphrase in Kit's own words,
so read the framework itself for the full definitions.

| Field | Value |
|---|---|
| Design | <GDS title, number, and version> |
| Based on | <the IA the GDS is based on, with its version, or "n/a"> |
| Project | <project id or name> |
| Views | <OV-1, SV-1, SV-4, DIV-2, or the ones asked for> |
| Prepared by | <role, or "kit-viewpoints and the diagrammer, checked by (role)"> |
| Date | <DD-Mmm-YYYY> |
| Version | <v1, v2, ...; never overwrite an earlier one> |
| Classification | <internal or confidential; the GDS's own classification> |

## The rules

- Every element cites the GDS section it came from, as [§6 Interfaces].
- An element found only by keyword, not by a heading, a table, or a labelled field, is marked
  "(inferred)". Check those first.
- Where the GDS says nothing, write "not stated". Never fill a gap from memory or from another
  system's design; ask the writers instead.
- People appear by role (for example "Operations analyst"), never by name.
- A viewpoint is a draft for the architect, not a certified architecture model.

## The views

| View | What it shows | Where it usually comes from in the GDS | Where it usually comes from in the IA |
|---|---|---|---|
| OV-1 High-level operational concept | Who uses the system, the system itself, the main external systems around it, and the main flows between them, drawn as one context picture | Overview or introduction, actors or user roles, external systems or dependencies, operational or process flow | Business driver, scope, stakeholders, impacted systems |
| SV-1 Systems interface description | The system's components and the interfaces between them, each with its protocol and port where stated | Components or solution architecture, interfaces, integration, connectivity or firewall flows | Impacted systems and integrations (often without protocols yet) |
| SV-4 Systems functionality | The functions the system performs, the component that performs each, and the data passed between functions | Functional design, functions or capabilities, processing, data flows | Functional requirements and in-scope capabilities |
| DIV-2 Logical data model | The main data entities, their attributes where stated, how they relate, and each entity's classification | Logical data model, data entities or data dictionary, relationships, data classification | Data impact, data classes touched, retention |

## OV-1 High-level operational concept

| Element | Kind (actor, system, external system) | Role or data | Source |
|---|---|---|---|
| <for example "Trader"> | actor | <what they do with the system> | <[§2 Actors]> |

Main flows, one line each, in order: <[§4 Operational flow]>

## SV-1 Systems interface description

| Component | Description | Technology | Hosting | Source |
|---|---|---|---|---|
| <for example "Routing engine"> | | | <zone or environment, or "not stated"> | |

| From | To | Protocol | Port | Data | Security | Source |
|---|---|---|---|---|---|---|
| <component> | <component or external system> | <as stated, or "not stated"> | <as stated, or "not stated"> | | <encryption and authentication as stated> | |

## SV-4 Systems functionality

| Function | Performed by (component) | Description | Source |
|---|---|---|---|
| <for example "Validate order"> | <component, or "not stated"> | | |

| From function | To function | Data | Source |
|---|---|---|---|
| | | | |

## DIV-2 Logical data model

| Entity | Attributes | Classification | Source |
|---|---|---|---|
| <for example "Order"> | <as stated, or "not stated"> | <the entity's class, else the document's, marked as such> | |

| From entity | To entity | Relationship (cardinality) | Source |
|---|---|---|---|
| | | <for example "one to many"> | |

## Diagrams

<The draw.io file for each view, built with `kit-drawio` from its JSON spec, so the team's font and
palette (`--styles` or KIT_DRAWIO_STYLES) apply. The kit-diaglint summary when lint rules are set,
and any departures from the diagramming standard with their reasons.>

## Not stated

<What each view needs that the GDS doesn't say, as questions for the GDS writer, by role.>

## Sources

<The GDS and its version, the IA, and the setup files used. DoDAF 2.02 is cited by name and
version only.>

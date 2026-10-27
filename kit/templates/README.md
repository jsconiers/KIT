# Templates

Example templates for each kind of work Kit's staff handles. They're starting points: copy one,
change it to suit your team, and point the agent's setup file in `memory/context/` at your copy.
Each template opens with a short note on how to use it, and its guidance sits in angle brackets to
delete when filling it in. If your team already has a template for something, point the setup file
at that one instead.

Delivery work (impact assessments and design specifications) uses your team's own templates, set
in `memory/context/writing.md`; none ship here.

| Work type | Template | Used by | Setup file |
|---|---|---|---|
| Decisions | `adr-template.md` | decision recorder | `decisions.md` |
| Decisions | `build-buy-partner-template.md` | Kit, cost estimator, decision recorder | `decisions.md` |
| Projects | `stakeholder-map-template.md` | status reporter, scheduler | `status.md` |
| Systems | `system-profile-template.md` | curator, Kit (`kit-sysprofile`) | `knowledge.md` |
| Standards | `zero-trust-rating-template.md` | standards checker (on request) | `standards.md` |
| Design review | `red-team-review-template.md` | red team | `standards.md` |
| Design review | `threat-model-template.md` | threat modeler (feeds risk and compliance mapper, implementation planner) | `standards.md` |
| Compliance | `csf-mapping-template.md` | risk and compliance mapper (when NIST CSF 2.0 applies; `kit-csf`) | `compliance.md` |
| Traceability | `traceability-matrix-template.md` | implementation planner, GDS writer, Kit (`kit-trace`) | `writing.md` |
| Projects | `executive-onepager-template.md` | deck builder, Kit (`kit-onepager`) | `writing.md` |
| Diagrams | `diagram-lint-rules.example.json` | diagrammer, reviewer (`kit-diaglint`) | `diagrams.md` (Lint rules) |
| TOGAF (on request) | `togaf-architecture-vision-template.md` | IA writer, GDS writer, implementation planner (on request) | `writing.md` |
| TOGAF (on request) | `togaf-statement-of-architecture-work-template.md` | IA writer, GDS writer, implementation planner (on request) | `writing.md` |
| TOGAF (on request) | `togaf-architecture-definition-document-template.md` | IA writer, GDS writer, implementation planner (on request) | `writing.md` |
| TOGAF (on request) | `togaf-architecture-requirements-specification-template.md` | IA writer, GDS writer, implementation planner (on request) | `writing.md` |
| TOGAF (on request) | `togaf-transition-architecture-template.md` | IA writer, GDS writer, implementation planner (on request) | `writing.md` |
| TOGAF (on request) | `togaf-implementation-migration-plan-template.md` | IA writer, GDS writer, implementation planner (on request) | `writing.md` |
| Diagrams | `viewpoints-template.md` | diagrammer (on request), Kit (`kit-viewpoints`) | `diagrams.md` |
| Questions | `question-tracker-template.md` | IA writer, GDS writer, intake triager, Kit (`kit-questions`) | `writing.md` |
| Compliance | `exception-register-template.md` | risk and compliance mapper, standards checker, Kit (`kit-exceptions`) | `compliance.md` |
| Compliance | `pbc-tracker-template.md` | Kit (`kit-pbc`) | `compliance.md` |
| Compliance | `control-map.example.json` | Kit (`kit-audit-export --controls`) | `compliance.md` |
| Costs | `sizing-template.md` | cost estimator, Kit (`kit-sizing`) | `costs.md` |
| POC | `poc-charter-template.md` | POC lead | `poc.md` |
| POC | `poc-test-plan-template.md` | POC lead | `poc.md` |
| POC | `poc-scorecard-template.md` | POC lead | `poc.md` |
| POC | `poc-findings-template.md` | POC lead | `poc.md` |
| Vendor meetings | `vendor-meeting-template.md` | meeting scribe | `meetings.md` |
| Labs | `lab-request-template.md` | lab planner (and the approver) | `labs.md` |
| Labs | `lab-runbook-template.md` | lab planner | `labs.md` |
| Training | `learning-plan-template.md` | training lead | `training.md` |
| Training | `learning-path-template.md` | training lead | `training.md` |
| Training | `training-kit-template.md` | training lead, deck builder | `training.md` |
| Training | `skills-matrix-template.md` | training lead | `training.md` |
| Research | `research-brief-template.md` | researcher, librarian (filing) | `writing.md` |
| Future tech | `radar-ballot-template.md` | future tech planner | `future-tech.md` |
| Future tech | `tech-lifecycle-review-template.md` | future tech planner | `future-tech.md` |
| Future tech | `strategy-brief-template.md` | future tech planner | `future-tech.md` |
| Future tech | `tech-roadmap-template.md` | future tech planner (`kit-roadmap` drafts) | `future-tech.md` |
| Future tech | `regulatory-watch-template.md` | weekly review, future tech planner, risk and compliance mapper | `future-tech.md` |
| Future tech | `tech-debt-register-template.md` | future tech planner | `future-tech.md` |
| Future tech | `vendor-landscape-template.md` | future tech planner | `future-tech.md` |
| Future tech | `radar-view-template.md` | future tech planner | `future-tech.md` |
| Future tech | `innovation-intake-template.md` | future tech planner | `future-tech.md` |

## How a piece of exploration work flows

1. **Research** answers the first questions (research brief), and a vendor evaluation can narrow
   the options.
2. **POC**: charter, then a lab request and runbook, then the test plan, evidence, scorecard, and
   findings. Vendor meetings along the way feed claims to verify.
3. **Decision**: the sponsor decides, and the decision recorder writes the ADR. For a sourcing
   choice, a build, buy, or partner analysis comes first.
4. **Afterwards**: on go, the findings' IA starter begins delivery work. After every verdict, the
   training lead outlines a knowledge-transfer session and turns what was learned into learning
   plans, and the future tech planner proposes a radar ballot.

## Rules for every template

- People appear by role, never by name.
- Dates are DD-Mmm-YYYY.
- Never write a credential, key, licence key, or NDA text into a filled-in template; name where it
  lives.
- Mark each filled-in copy's classification.

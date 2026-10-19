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

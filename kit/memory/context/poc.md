# POC setup

What the POC lead uses. It reads this before every job, so keep it current.

- **Folder:** `<library root>/artifacts/<project>/poc/<POC id>/` (see `library.md`), unless you set
  another place here. Inside it: `charter.md`, `test-plan.md`, `evidence/`, `evidence-log.md`,
  `scorecard.md`, and `findings.md`.
- **Numbering:** POC-0001 and up, never reused. `poc/INDEX.md` in the library root holds the
  register and the next free number.
- **Templates:** `~/Claude/Agents/kit/templates/poc-charter-template.md`,
  `poc-test-plan-template.md`, `poc-scorecard-template.md`, and `poc-findings-template.md`,
  examples to adapt. Point here to your team's own templates if it has them.
- **Scorecard weights and verdict bands:** optional. Until set, the lead uses the template's.
- **Who approves a charter and decides a verdict:** not set. Roles, not names, for example the
  sponsor and the build lead.
- **NDA owner:** not set. The team that confirms a vendor NDA is current (often Legal). The lead
  records only the confirmation, its date, and the expiry, never the NDA itself.
- **Data rule:** synthetic, masked, or public data only, unless the data owner approves otherwise
  in writing. Change this only to make it stricter.
- **Labs:** optional. Where lab environments are listed, so the lead can name the environment.
- **Security baseline:** optional. The standard the test plan's security checks follow (see
  `standards.md`).

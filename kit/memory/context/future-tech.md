# Future tech setup

What the future tech planner uses. It reads this before every job, so keep it current.

- **Folder:** `radar/` in the library root (see `library.md`), unless you set another place here.
  Inside it: `RADAR.md`, `ballots/`, `lifecycle/` (with `summary.md` from `kit-lifecycle`),
  `views/`, `strategy/`, `roadmap/`, `watch/`, `inventory.csv` or `inventory.json`, `eol.json`,
  `tech-debt.md`, `vendors.md`, and `LOG.md`.
- **Audiences:** not set. Who the radar serves, for its views, for example the architecture team,
  engineering and development, and company strategy.
- **Rings:** adopt, trial, assess, hold, unless you set others here.
- **Quadrants:** optional. For example platforms, tools, techniques, and languages and
  frameworks.
- **Voting rule:** not set. Who votes (roles or a forum), quorum, and how ties are settled. The
  planner never places a technology without a recorded vote.
- **Review cycle:** optional. How often radar entries and lifecycle reviews come up again, for
  example every six months.
- **Lifecycle data:** not set. Whether configuration-management data is good enough to drive
  lifecycle reviews, and which records to ask the gateway for. Kit saves them (or an export) as
  `inventory.csv` or `inventory.json` in the radar folder: product, version, system, owner role,
  environment.
- **End-of-support dates:** `eol.json` in the radar folder: product, cycle, eol, extended, source,
  checked. Dates come only from the researcher's cited briefs (public product names, never system
  names) or are entered by hand with a source; no tool calls an outside EOL service, so the
  inventory never leaves. `kit-lifecycle` flags past, urgent (12 months), warning (24 months), and
  unknown; entries checked more than 180 days ago are listed for a recheck.
- **Roadmap:** `kit-roadmap` drafts `roadmap/draft-<date>.md` from the radar, the lifecycle summary,
  tech debt, and POC go verdicts. Approvers: not set. The roles that approve the roadmap.
- **Watch list:** optional. Topics and public sources for the weekly regulatory and industry watch,
  for example: financial market regulators' rules and guidance on technology and operational
  resilience; NIST and ISO security and AI standards; cloud providers' security bulletins and
  deprecations; major vendors' end-of-support notices. Until set, the weekly review skips the
  watch.
- **Strategy brief:** optional. How often (default quarterly), the audience, and who reviews it
  before it goes out.
- **Templates:** `~/Claude/Agents/kit/templates/radar-ballot-template.md`,
  `tech-lifecycle-review-template.md`, `strategy-brief-template.md`,
  `tech-debt-register-template.md`, `vendor-landscape-template.md`, `radar-view-template.md`,
  `innovation-intake-template.md`, `tech-roadmap-template.md`, and `regulatory-watch-template.md`,
  examples to adapt.
- **Innovation gate approvers:** not set. The role that decides at each gate (assess, POC, pilot,
  adopt). Until set, the planner records gate recommendations only.
- **Renewal warning:** 90 days before a contract renewal, unless you set another number here.
- **Standards owner:** not set. The role that decides and makes changes to standards and reference
  architectures when the planner flags them.

# Standards setup

What the standards checker uses. It reads this before every job, so keep it current. If your
standards are internal, keep their details here: your copy of this file stays on your computer,
and the repo only has this blank template.

- **Engineering standards:** not set. Each standard's name, version, and where to read it.
- **Reference architectures:** not set. Each one, the kind of system it covers, and where it is.
- **Security baselines:** not set. For example encryption, authentication and MFA, logging and
  monitoring, patching, and network segmentation, with where each lives.
- **Hardening baselines:** not set. Which benchmark applies to which platform (for example a CIS
  Benchmark by name, version, and profile level), and where the team's exceptions are recorded.
  For a Zero Trust maturity rating, the checker uses `templates/zero-trust-rating-template.md`.
- **Availability and DR tiers:** not set. The tiers, what each requires, and how a system is
  assigned one.
- **Which apply when:** not set. Which standards apply to which kinds of change, environment, or
  classification.
- **Design review templates:** optional. The red team uses
  `templates/red-team-review-template.md` and the threat modeler `templates/threat-model-template.md`;
  name a team copy of either here to use it instead.
- **Waivers:** optional. How an exception is requested, who grants it by role, and where granted
  waivers are recorded.

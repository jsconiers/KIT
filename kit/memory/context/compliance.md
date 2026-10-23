# Compliance setup

What the risk and compliance mapper uses. It reads this before every job, so keep it current. If
your policies are internal, keep their details here: your copy of this file stays on your
computer, and the repo only has this blank template.

- **Control frameworks:** not set. Each framework or regulation that applies, such as
  financial-reporting controls or a security framework, its version, and where its control list is.
- **Policies:** not set. Information security, data classification and retention, privacy, and
  third-party risk policies, with where to read each.
- **Data classes:** not set. Your data classification levels and what each one requires.
- **Sign-off:** not set. Who owns sign-off for each framework or policy, by role, not by name.
- **Risk rating:** optional. The scale to rate risks on, if your team uses one.
- **Records:** optional. Where supporting records live, such as vendor risk assessments, and which
  connector reaches them through the gateway.
- **Regulatory watch:** not set. The public regimes and topics for the monthly regulatory watch,
  separated by commas or semicolons, for example "SEC Reg SCI, CFTC, DORA, NYDFS 500, NIST". Only
  public names: they go to the researcher's web searches, so never a system, project, or client.
  With REG_WATCH="on" in the run config, the first weekly review of each month asks the researcher
  for a cited brief on last month's public changes to these. Until set, it skips with a note.
- **Regulatory watch folder:** optional. Where the monthly watch is saved, as a full path (or
  starting with `~/`). Default: `regulatory-watch/` in the library root (see `library.md`), or
  Kit's `briefs/` folder if neither is set.
- **Exception register:** optional. The policy exception and waiver register `kit-exceptions` reads
  and adds to, as a full path or one relative to the library root. Default:
  `compliance/exception-register.md`. Start it from
  `~/Claude/Agents/kit/templates/exception-register-template.md`. EXCEPTIONS_WARN_DAYS in the run
  config (default 30) sets how early the morning alerts warn before an exception expires.
- **Control map:** optional. The JSON file (or Markdown table: Control, Name, Evidence) mapping each
  control ID to the evidence Kit has, for `kit-audit-export --controls`. Start from
  `~/Claude/Agents/kit/templates/control-map.example.json`.
- **PBC tracker:** optional. The register of auditors' "provided by client" requests that `kit-pbc`
  keeps, as a full path or one relative to the library root. Default:
  `compliance/audit-requests/pbc-tracker.md`. Start it from
  `~/Claude/Agents/kit/templates/pbc-tracker-template.md`.

## Framework profile

Which frameworks apply, to what, and who owns each. The mapper maps only against frameworks marked
**applies**, and says so in its report when this profile isn't set. Cite frameworks by name, ID,
and version; keep the control text itself where your team licenses or publishes it, not here.

| Framework | Version | Applies? | Systems or data classes in scope | Owner (role) | Where the control list is |
|---|---|---|---|---|---|
| NIST Cybersecurity Framework (CSF) | 2.0 | not set | not set | not set | not set |
| CRI Profile v2.x (Cyber Risk Institute, financial-sector profile of NIST CSF 2.0) | v2.x | not set | not set | not set | not set |
| NIST SP 800-53 | Rev 5 | not set | not set | not set | shipped with Kit: `kit-controls 800-53 <ID>` |
| PCI DSS | v4.0.1 | not set | not set | not set | not set |
| CIS Controls | v8.1 | not set | not set | not set | not set |
| CIS Benchmarks | per product and version | not set | not set | not set | not set |
| CISA Zero Trust Maturity Model | 2.0 | not set | not set | not set | not set |
| CISA Secure by Design | 2023/2024 | not set | not set | not set | not set |
| SOX IT general controls (ITGC) | your control set's version | not set | not set | not set | not set |
| Others | not set | not set | not set | not set | not set |

- **Applies?** is yes, no, or not set. Write "no" for a framework you've ruled out, so the mapper
  doesn't ask about it again.
- **Systems or data classes in scope:** the systems, environments, or data classes (from **Data
  classes** above) the framework covers, for example "cardholder data environment only".
- **Owner (role):** who answers questions on that framework and owns its sign-off, by role, not by
  name.
- **CRI Profile:** Kit doesn't ship its content, since its licence differs; cite it by name, version,
  and diagnostic statement ID, and point "Where the control list is" at your licensed copy. Its
  diagnostic statements extend the NIST CSF 2.0 categories, so a CSF mapping is the starting point.
- **NIST SP 800-53 Rev 5:** IDs, titles, one-line summaries, and baselines ship with Kit (public
  domain); `kit-controls` looks them up and cross-references MITRE ATT&CK. Read the catalog itself for
  the full control text.

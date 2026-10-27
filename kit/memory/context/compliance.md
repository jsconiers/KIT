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

## Framework profile

Which frameworks apply, to what, and who owns each. The mapper maps only against frameworks marked
**applies**, and says so in its report when this profile isn't set. Cite frameworks by name, ID,
and version; keep the control text itself where your team licenses or publishes it, not here.

| Framework | Version | Applies? | Systems or data classes in scope | Owner (role) | Where the control list is |
|---|---|---|---|---|---|
| NIST Cybersecurity Framework (CSF) | 2.0 | not set | not set | not set | not set |
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

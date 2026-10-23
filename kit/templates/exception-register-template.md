# Policy exception register

An example template for the team's register of policy exceptions and standards waivers. `kit-exceptions`
reads and adds to it, and the morning monitor warns before an exception expires or a review falls
due. Copy it, change it to suit the team, and point **Exception register** in
`memory/context/compliance.md` at the copy (default: `compliance/exception-register.md` in the
library root). Delete the guidance lines in angle brackets when filling it in. Keep the column
names: `kit-exceptions` finds the columns by name, so their order can change.

| Field | Value |
|---|---|
| Updated | <DD-Mmm-YYYY> |
| Kept by | <role> |
| Classification | <internal or confidential> |

## How to fill it in

- **ID:** EXC-0001 and up, never reused. `kit-exceptions add` takes the next free number.
- **Policy and section:** the policy or standard, its version, and the section the exception is
  from, for example "the organization's information security policy, v3, section 4.2". Cite it;
  never copy the policy's text here.
- **System or design:** the system, or the design document (IA or GDS) with its version.
- **Reason:** why the exception is needed, in one or two lines.
- **Compensating controls:** what reduces the risk while the exception stands. "None" if none.
- **Owner (role) and Approver (role):** who owns the exception and who granted it, by role only.
- **Granted, Expiry, Last reviewed:** dates as DD-Mmm-YYYY. Every granted exception has an expiry.
- **Review frequency:** monthly, quarterly, semi-annual, annual, or "every N months".
- **Status:** candidate (raised by a review, not yet requested), requested, granted, renewal
  requested, expired, revoked, or closed. Only the approver's recorded decision makes it granted;
  Kit's staff only ever add candidates.
- **Linked ticket and Evidence:** the change or risk ticket, and where the approval and
  supporting records are kept.
- Never delete a row. Close it with a status and a note in Evidence.

## Register

| ID | Policy and section | System or design | Reason | Compensating controls | Owner (role) | Approver (role) | Granted | Expiry | Review frequency | Last reviewed | Status | Linked ticket | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| <EXC-0001> | <policy, version, section> | <system or DOC-### v1.0> | <why> | <controls, or none> | <role> | <role> | <DD-Mmm-YYYY> | <DD-Mmm-YYYY> | <quarterly> | <DD-Mmm-YYYY> | <candidate> | <ticket> | <where the approval is> |

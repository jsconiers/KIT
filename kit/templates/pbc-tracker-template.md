# Audit request (PBC) tracker

An example template for tracking auditors' "provided by client" (PBC) requests. `kit-pbc` reads and
adds to it, gathers evidence for a request with `kit-audit-export --controls`, and drafts a response
for the owner to review. Copy it, change it to suit the team, and point **PBC tracker** in
`memory/context/compliance.md` at the copy (default: `compliance/audit-requests/pbc-tracker.md` in
the library root). Each request gets its own folder next to the tracker, named by its request ID.
Delete the guidance lines in angle brackets when filling it in. Keep the column names: `kit-pbc`
finds the columns by name.

| Field | Value |
|---|---|
| Updated | <DD-Mmm-YYYY> |
| Kept by | <role> |
| Classification | <internal or confidential> |

## How to fill it in

- **Request ID:** the auditor's own reference if they give one, otherwise PBC-0001 and up.
- **Audit:** the audit or review it belongs to, for example "annual IT general controls audit".
- **Requested item:** what the auditor asked for, in their words, in one line.
- **Control IDs:** the control or controls it supports, as named in the control map (for example
  CHG-01, ACC-02), separated by commas. `kit-pbc gather` uses them.
- **Requester (role) and Owner (role):** by role only, never by name.
- **Due date:** DD-Mmm-YYYY.
- **Status:** open, gathering, drafted, provided, or closed. Kit never marks a request provided;
  the owner does, once they've sent it.
- **Evidence links:** where the gathered pack and the response draft are.
- Never delete a row. Close it with a status and a note.

## Requests

| Request ID | Audit | Requested item | Control IDs | Requester (role) | Due date | Owner (role) | Status | Evidence links | Notes |
|---|---|---|---|---|---|---|---|---|---|
| <PBC-0001> | <audit> | <item> | <CHG-01> | <role> | <DD-Mmm-YYYY> | <role> | <open> | <path> | <notes> |

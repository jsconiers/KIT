# Lab setup

What the lab planner uses. It reads this before every job, so keep it current.

- **Folder:** `labs/` in the library root (see `library.md`), unless you set another place here.
  Inside it: one folder per lab, `REGISTER.md`, and `LOG.md`.
- **Numbering:** LAB-0001 and up, never reused. `REGISTER.md` holds the next free number.
- **Environments:** not set. The kinds of lab you run, for example on-premises hardware and cloud
  accounts, and where each is listed.
- **Who approves a lab:** not set. Roles, not names.
- **Data rule:** synthetic, masked, or public data only, unless the data owner approves otherwise
  in writing. Change this only to make it stricter.
- **Default timebox:** optional. The teardown date to propose when a brief doesn't give one.
- **Cost:** optional. Spend caps for cloud labs, and how on-premises capacity is booked.
- **Security baseline:** optional. The standard labs must meet (see `standards.md`).
- **Template:** `~/Claude/Agents/kit/templates/lab-runbook-template.md`, an example to adapt.
- **Request template:** `~/Claude/Agents/kit/templates/lab-request-template.md`, what a lab
  request covers before approval. Point here to your team's own form if it has one.

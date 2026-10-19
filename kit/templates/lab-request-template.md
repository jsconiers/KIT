# Lab request: <short purpose>

An example template for asking for a lab before anyone builds one. The approver signs it off, then
the lab planner writes the runbook from it. Copy it, change it to suit the team, and point
`memory/context/labs.md` at the copy. Delete the guidance lines in angle brackets when filling it
in. A request fits on one page.

| Field | Value |
|---|---|
| Lab id | <LAB-nnnn, from the lab register> |
| Requested by | <role> |
| Owner | <role responsible for the lab until teardown> |
| Purpose | <POC id, training plan, or the question the lab answers> |
| Placement | <on-premises (site, rack or host pool) or cloud (account or subscription, region)> |
| Network | <isolated, lab network, or connected to what, and why> |
| Data | <synthetic, masked, or public; anything else needs the data owner's written approval, cited> |
| Data class | <public, internal, confidential> |
| Start | <DD-Mmm-YYYY> |
| Teardown by | <DD-Mmm-YYYY; required> |
| Classification | <internal or confidential> |

## What's needed

<Hosts, instances, storage, software and licences or trials, accounts and access by role.
Hardware borrowed from the lab pool, with its return date.>

## Cost

<Cloud: the estimated monthly cost and the spend cap. On-premises: capacity booked and for how
long.>

## Security

<Baseline it must meet, exceptions asked for, how credentials are held (named, never written
here), and logging.>

## Risks

<What could leak, break, or linger, and the mitigation for each.>

## Checks before approval

- [ ] Data rule met, or the data owner's approval cited
- [ ] `kit-labcheck` run on this request, each finding fixed or explained
- [ ] Teardown date set, with an owner
- [ ] Security baseline checked (standards checker, if used)
- [ ] Cost within the cap, or the cap's owner agreed

## Approval

| Role | Decision | Date |
|---|---|---|
| Approver | <approved / changes needed / declined> | |

<The lab planner records the decision here, in the lab register, and in its log. No runbook is
final until a decision of "approved" is recorded.>

# Lab runbook: <lab id> <short title>

An example template for lab runbooks, for on-premises and cloud labs. The lab planner fills it in;
people run it. Copy it, change it to suit the team, and point `memory/context/labs.md` at the copy.
Delete the guidance lines in angle brackets when filling it in. A runbook without a teardown date
isn't finished.

| Field | Value |
|---|---|
| Lab id | <LAB-nnnn> |
| Version | <0.1, 0.2, ...> |
| Purpose | <one sentence> |
| POC | <POC id, or none> |
| Owner | <role> |
| Approver | <role, and approval date> |
| Environment | <on-premises (site, rack, network segment) or cloud (account, region)> |
| Start | <DD-Mmm-YYYY> |
| Teardown by | <DD-Mmm-YYYY> |
| Data | <synthetic, masked, or public; never production or confidential without written approval> |
| Budget or capacity | <cloud spend cap, or on-premises capacity booked> |
| Classification | <internal or confidential> |

## Prerequisites

<Approvals, accounts, network access and firewall requests, licences or trials, hardware, and
where each credential lives (never the credential itself).>

## Setup

<Numbered steps, each short enough to follow at a terminal, with a check at the end of each stage.>

1. <step>
   - Check: <what you should see>

## Tests

<The tests to run, from the POC test plan when there is one (test case ids), or listed here.>

## Monitoring and cost

<What to watch while the lab runs, alerts, and how spend or capacity is checked.>

## Security

<Network isolation, access, encryption, logging, and any exception that needs a waiver.>

## Teardown

<Numbered steps to remove everything, in order, with a check after each.>

## Delete-or-return checklist

<Every item the lab created or borrowed. Nothing is closed until every row is done.>

| Item | Type | Remove or return | Who (role) | Done |
|---|---|---|---|---|
| | compute / storage / network rule / DNS / account / credential / data set / licence / hardware | | | |

## Close-out

<Date torn down, who confirmed it, final cost or capacity used, and what was learned for next time.>

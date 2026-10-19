# Vendor landscape

An example template for the vendor landscape and relationship view. The future tech planner keeps
it at `radar/vendors.md`, so radar ballots, POCs, and lifecycle reviews can see each vendor's whole
picture. Copy it, change it to suit the team, and point `memory/context/future-tech.md` at the
copy. Delete the guidance lines in angle brackets when filling it in.

Contract details come only from what Kit passes on (a renewal date, a tier). Never copy contract
text, prices, or terms here; note where the contract lives instead.

| Field | Value |
|---|---|
| Updated | <DD-Mmm-YYYY> |
| Kept by | <role> |
| Classification | <internal or confidential> |

## How to fill it in

- **Strategic tier:** strategic (hard to replace, central to many services), core, tactical, or
  exit (being retired).
- **Contract renewal:** the date Kit passes on, and where the contract lives. A renewal within 90
  days is flagged in the planner's report and the weekly review.
- **POCs run:** POC ids and verdicts, from the POC register.
- **Radar entries:** the vendor's technologies on the radar, with their rings.
- **Relationship owner:** the role that manages the vendor, never a name.
- **Risks:** lock-in, financial health, support quality, roadmap fit, security record, data
  location, concentration (too many services on one vendor). Cite the source.

## Vendors

| Vendor | Products in use | Strategic tier | Contract renewal | POCs run | Radar entries | Relationship owner | Risks | Flags |
|---|---|---|---|---|---|---|---|---|
| <vendor> | <products and versions> | <tier> | <DD-Mmm-YYYY; contract held by role or system> | <POC-nnnn: verdict> | <technology: ring> | <role> | <risks, with sources> | <renewal in 90 days> |

## Concentration

<Services that depend on a single vendor, and what an exit would take, in one line each.>

## Changes

<A dated line for each vendor added, retired, re-tiered, or renewed.>

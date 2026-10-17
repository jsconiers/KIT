# POC scorecard: <POC id> <short title>

An example template for scoring a POC, or comparing several, the same way every time. Copy it,
change the criteria and weights to suit the team, and point `memory/context/poc.md` at the copy.
Delete the guidance lines in angle brackets when filling it in.

| Field | Value |
|---|---|
| POC id | <POC-nnnn> |
| Scored on | <DD-Mmm-YYYY> |
| Scored by | <role> |
| Classification | <internal or confidential> |

## How to score

- Score each criterion 0 to 5: 0 = not met or not tested, 1 = poor, 3 = acceptable, 5 = excellent.
- Weights add up to 100. Weighted score = score x weight / 5, so the total is out of 100.
- Every score cites evidence (a test case and its evidence reference) or says "assessed: <basis>"
  where no test applies. A score with no basis counts as 0.
- **Gates** are pass or fail and are not weighted. Any failed gate means no-go, whatever the total.

## Gates

| Gate | Pass / fail | Evidence |
|---|---|---|
| All must-have success criteria from the charter met | | |
| Meets the security baseline, or exceptions are waivable | | |
| Data handling acceptable for the data class | | |
| Vendor POCs: NDA confirmed current by Legal | | |

## Weighted criteria

| # | Criterion | Weight | Score (0-5) | Weighted | Evidence |
|---|---|---|---|---|---|
| 1 | Functional fit: meets the use case | 25 | | | |
| 2 | Performance and scale | 15 | | | |
| 3 | Security and compliance | 15 | | | |
| 4 | Operability: monitoring, support, upgrades | 10 | | | |
| 5 | Integration with current systems | 10 | | | |
| 6 | Total cost of ownership (3 years) | 10 | | | |
| 7 | Vendor or project viability and support | 10 | | | |
| 8 | Skills and ease of adoption | 5 | | | |
| | **Total** | **100** | | **/100** | |

## Comparison (several options)

| Criterion | Weight | Option A | Option B | Option C |
|---|---|---|---|---|
| | | | | |
| **Total** | **100** | | | |

## Verdict recommendation

<go, no-go, or pivot, with the main reasons in three bullets. Typical bands, to adjust: 75 or more
with all gates passed = go; 50 to 74 = pivot or extend; under 50 or a failed gate = no-go. This is
a recommendation; the sponsor decides.>

| Recommended | Decided by (role) | Decision | Date |
|---|---|---|---|
| | | | |

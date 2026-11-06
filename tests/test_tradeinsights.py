#!/usr/bin/env python3
"""Tests for kit-tradeinsights: trades read from the journals' tables of your own trades in the layouts the journal
run has used (Close, Closed, Open and Close, a numbered table, a Unicode minus), tables under the trail guard, the
paper scalper, and the agentic account skipped; the day's fee-inclusive net; the rules as written (bold before or
after the colon, "not assessed"), and the 13:00 rule worked out from close times when the journal is silent; no-trade
days and days the journal couldn't show; the groupings, the after-a-loss check, the leaks, "too few to judge", and
--write. Synthetic journals; nothing personal.

  python3 tests/test_tradeinsights.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "shared/bin/kit-tradeinsights"
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-tradeinsights-"))
KIT = TMP / "kit"
J = KIT / "journal"
J.mkdir(parents=True)


def day(date, text):
    (J / f"{date}.md").write_text(text, encoding="utf-8")


# Thu 01-Oct: Close (ET) table; rules bold after the colon; net in the numbers table.
day("2026-10-01", """# Journal · Thu 01-Oct-2026

## Numbers
| Metric | Value | Source |
|---|---|---|
| Fee-inclusive P&L | **-$60.00** | realized_pnl |

## Trades
| Close (ET) | Contract | P&L |
|---|---|---|
| 09:45:10 | SPXW 7700C | -$40.00 |
| 10:05:00 | SPXW 7700C | -$30.00 |
| 13:20:00 | SPXW 7690C | +$20.00 |

## Trail guard (shadow mode)
| Close | Contract | P&L |
|---|---|---|
| 11:00:00 | SPXW 9999P | +$999.00 |

## Discipline and tilt
- 13:00 ET hard stop: **broken.** One trade after 13:00.
- At most 9 round trips: **kept** (3).
- Stop at target: **not applicable.**
- tilt_detector: too few trips to assess.
""")
# Mon 05-Oct: Open and Close columns, a Unicode minus, bold before the colon; net in the headline only.
day("2026-10-05", """# Journal · Mon 05-Oct-2026

**Headline:** Fee-inclusive P&L was **+$140.00** against the target.

## Real trades
| Open | Close | Contract | Gross P&L |
|---|---|---|---|
| 09:35 | 09:41 | SPXW 7650P | +$100.00 |
| 10:00 | 10:50 | SPXW 7655P | −$20.00 |
| 11:00 | 11:04 | SPXW 7660P | +$70.00 |

## Paper bot (scalper, dry run)
| Closed | Contract | P&L |
|---|---|---|
| 10:00 | SPXW 1C | -$500.00 |

## Rules
- **13:00 ET hard stop: kept.**
- **At most 9 round trips: kept** (3).
- **Stop at target: not tested** (target not reached).
- **Tilt:** none detected.
""")
# Thu 08-Oct: a numbered table with "Closed" and a P&L-after-fees row; no rule lines at all.
day("2026-10-08", """# Journal · Thu 08-Oct-2026

| Metric | Value | Source |
|---|---|---|
| P&L after fees | -$85.00 | realized_pnl |

## Your trades
| # | Closed | Contract | Entry | Gross P&L | Cumulative |
|---|---|---|---|---|---|
| 1 | 12:10:00 | SPXW 7700P | $2.00 | -$50.00 | -$50.00 |
| 2 | 14:02:00 | SPXW 7710C | $1.50 | -$30.00 | -$80.00 |

## Agentic account (Robinhood MCP)
| Closed | Symbol | P&L |
|---|---|---|
| 09:31 | MU | -$43.78 |
""")
day("2026-10-06", "# Journal · Tue 06-Oct-2026\n\nNo SPX trades today. Fee-inclusive P&L was $0.00 and there were 0 round trips.\n")
day("2026-10-07", "# Journal · Wed 07-Oct-2026\n\n| Fee-inclusive P&L | not available | realized_pnl failed |\n")
day("2026-09-30", "# Journal · Wed 30-Sep-2026\n\n## Trades\n| Close | Contract | P&L |\n|---|---|---|\n| 10:00 | SPXW 1P | +$5.00 |\n")
(J / "scorecard-2026-10.md").write_text("# Scorecard\n| Close | Contract | P&L |\n|---|---|---|\n| 10:00 | X | +$1.00 |\n")
ENV = dict(os.environ, KIT_DIR=str(KIT), KIT_TODAY="2026-10-31", PYTHONDONTWRITEBYTECODE="1")


def run(*a):
    r = subprocess.run([sys.executable, str(TOOL), *a], capture_output=True, text=True, env=ENV, timeout=60)
    return r.returncode, r.stdout, r.stderr


rc, out, err = run("--month", "2026-10", "--json")
r = json.loads(out) if rc == 0 else {}
o = r.get("overall", {})
ok(rc == 0 and o.get("trades") == 8, "only your own trades are read: 8, not the trail guard's, the bot's, or the "
   "agentic account's", (o, err))
ok(o.get("pnl") == 20.0 and o.get("wins") == 3, "gross P&L and wins across the layouts (Unicode minus included)", o)
ok(r["trading_days"] == 3 and r["no_trade_days"] == 1 and [u["date"] for u in r["unreadable"]] == ["07-Oct-2026"]
   and "sources failed" in r["unreadable"][0]["why"], "trading days, no-trade days, and days it couldn't read", r)
ok(r["net_fee_inclusive"] == -5.0 and r["net_days_known"] == 3, "fee-inclusive nets from the table, the headline, and "
   "a P&L-after-fees row", (r["net_fee_inclusive"], r["net_days_known"]))
ok(r["journals"] == 5, "September's journal and the scorecard aren't counted", r["journals"])
rules = r["rules"]
ok(rules["13:00 ET hard stop"]["broken"] == ["01-Oct-2026", "08-Oct-2026"] and rules["13:00 ET hard stop"]["kept"] == ["05-Oct-2026"],
   "the 13:00 rule as written, and from close times when the journal is silent (08-Oct)", rules["13:00 ET hard stop"])
ok(rules["stop at target"]["n/a"] == ["01-Oct-2026", "05-Oct-2026"] and rules["stop at target"]["unknown"] == ["08-Oct-2026"],
   "not applicable and not tested, and a day with no rule lines is couldn't tell", rules["stop at target"])
ok(rules["tilt"]["n/a"] == ["01-Oct-2026"] and rules["tilt"]["kept"] == ["05-Oct-2026"], "tilt: too few to assess is "
   "not applicable; none detected is kept", rules["tilt"])
bt = r["by_time"]
ok(bt["09:30-10:30 (first hour)"]["trades"] == 3 and bt["after 13:00"]["trades"] == 2 and bt["after 13:00"]["pnl"] == -10.0,
   "by time of day, by close time", bt)
ok(r["by_weekday"]["Thursday"]["trades"] == 5 and r["by_weekday"]["Thursday"]["pnl"] == -130.0
   and r["by_weekday"]["Monday"]["pnl"] == 150.0, "by weekday", r["by_weekday"])
ok(r["by_side"]["call"]["trades"] == 4 and r["by_side"]["put"]["trades"] == 4, "calls and puts from the contract", r["by_side"])
ok(r["held_known"] == 3 and r["by_hold"]["under 5 min"]["trades"] == 1 and r["by_hold"]["5-15 min"]["trades"] == 1,
   "hold time where the journal has open times", r["by_hold"])
ok(r["first_trade"]["trades"] == 3 and r["after_loss"]["trades"] == 4 and r["after_win"]["trades"] == 1,
   "first trade of the day, after a loss, after a win (each day in close order)", (r["after_loss"], r["after_win"]))
ok(r["without_after_1300"] == 30.0, "what the period would have been without the trades after 13:00")
ok(all(not g["enough"] for g in r["by_side"].values()) and r["by_weekday"]["Thursday"]["enough"],
   "groups under 5 trades are too few to judge", r["by_side"])
ok(any("Thursday" in x for x in r["leaks"]) and not any(x.startswith("calls") for x in r["leaks"]),
   "leaks come only from groups with enough trades", r["leaks"])

rc, out, _ = run("--month", "2026-10")
ok("too few to judge" in out and "## Couldn't read" in out and "07-Oct-2026" in out and "[work]" not in out,
   "the report says what's thin and what it couldn't read, and nothing is tagged work", out[:600])
rc, out, _ = run("--from", "2026-10-05", "--to", "2026-10-06", "--json")
ok(json.loads(out)["overall"]["trades"] == 3, "--from and --to")
rc, out, _ = run("--json")
ok(json.loads(out)["from"] == "2026-10-02", "the default is the last 30 days")
rc, out, _ = run("--month", "2026-10", "--write")
ok(rc == 0 and (J / "insights-2026-10.md").is_file(), "--write saves journal/insights-<period>.md", out)
ok(run("--month", "2026-13")[0] != 0, "a bad month is refused")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nkit-tradeinsights tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)

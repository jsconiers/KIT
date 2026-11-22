#!/usr/bin/env python3
"""kit-dates gifts: ideas, budgets, delivery days, order-by dates in the brief and the to-do, bought (by idea
number or in words, tied to the coming occasion), the year's spending, and that the brief never lists the
ideas themselves. KIT_TODAY pins the day. Synthetic names only.

Run: python3 tests/test_gifts.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TOOL = HERE.parent / "shared" / "bin" / "kit-dates"
tmp = pathlib.Path(tempfile.mkdtemp())
(tmp / ".install/logs").mkdir(parents=True)
(tmp / "QUEUE.md").write_text("# Queue\n\n## Sprint\n\n## Owner\n\n## Kit\n\n## Waiting on others\n\n"
                              "## Someday\n\n## Done\n")
env = dict(os.environ, KIT_DIR=str(tmp), KIT_TODAY="2026-11-20", PYTHONUTF8="1")
fails = []


def check(cond, what, extra=""):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)
        if extra:
            print("     " + str(extra)[:1500].replace("\n", "\n     "))


def run(*args, **kw):
    r = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, env=dict(env, **kw),
                       timeout=60, stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout, r.stderr


def data():
    return json.loads((tmp / "dates.json").read_text())


# Dates: Robin's birthday in 12 days (gift), Kai's in 40 days (gift), a work farewell in 9 days (gift).
run("add", "Robin Lake", "1990-12-02", "--relation", "friend", "--action", "gift")
run("add", "Kai", "01-01", "--action", "gift")
run("add", "Ops team farewell", "2026-11-29", "--what", "event", "--work", "--once", "--action", "gift")

# ---------------------------------------------------------------- ideas and budgets
rc, o, e = run("gift", "Robin", "Lake", "Trail running vest", "--price", "$64.50", "--link", "https://example.com/vest")
check(rc == 0 and "Saved for Robin Lake: Trail running vest ($64.50). 1 idea(s)" in o, "gift: an idea, with the full name", o + e)
rc, o, e = run("gift", "robin lake", "Cookbook", "--price", "30", "--for", "birthday")
check(rc == 0 and "2 idea(s) for Robin Lake" in o, "names match whatever the case", o + e)
rc, o, e = run("gift", "Robin Lake", "cookbook")
check(rc == 1 and "already has that idea" in e, "the same idea twice is refused", e)
rc, o, e = run("gift", "Robin Lake", "Vest", "--link", "not-a-link")
check(rc == 1 and "web address" in e, "--link must be a web address", e)
rc, o, e = run("gift", "Robin Lake", "Vest", "--price", "lots")
check(rc == 1 and "not an amount" in e, "--price must be an amount", e)
rc, o, e = run("budget", "Robin Lake", "75", "--ship", "4")
check(rc == 0 and "Robin Lake: budget $75 per occasion; delivery 4 days." in o, "budget and delivery days", o + e)
rc, o, e = run("budget", "Kai", "--ship", "99")
check(rc == 1 and "0 to 60" in e, "--ship is checked", e)
run("gift", "Kai", "Board game")

# ---------------------------------------------------------------- the brief: order-by dates, counts only
rc, o, e = run("brief")
robin = next((ln for ln in o.splitlines() if "Robin Lake's birthday" in ln), "")
check("Wed 02-Dec (in 12 days): Robin Lake's birthday (turns 36) (friend). Action: gift; order by Thu 26-Nov. "
      "(2 ideas saved: kit-dates gifts Robin)" in robin, "the brief: order by the date less delivery and two days", o + e)
check("vest" not in o.lower() and "cookbook" not in o.lower() and "$" not in o, "the brief never lists ideas or prices", o)
check(not any("Kai" in ln for ln in o.splitlines()), "Kai's is 42 days away: not in the brief yet", o)
farewell = next((ln for ln in o.splitlines() if "farewell" in ln), "")
check(farewell.startswith("[work] ") and "the order-by date has passed (Tue 24-Nov)" not in farewell
      and "order by Sun 22-Nov" in farewell and "no ideas saved yet" in farewell, "a work gift date: [work], order-by", farewell)
rc, o, e = run("brief", KIT_TODAY="2026-11-25")
farewell = next((ln for ln in o.splitlines() if "farewell" in ln), "")
check("the order-by date has passed (Sun 22-Nov): buy locally, or send a card" in farewell, "order-by passed: says so", farewell)

# ---------------------------------------------------------------- the to-do: due on the order-by date
rc, o, e = run("brief", "--queue")
q = (tmp / "QUEUE.md").read_text()
check("Get a gift for Robin Lake: Robin Lake's birthday (turns 36), Wed 02-Dec" in q and "26-Nov-2026" in
      q.split("Get a gift for Robin Lake")[1].split("\n")[0], "--queue: the gift to-do is due on the order-by date", q)
check("[work]" in q.split("Get a gift for Ops team farewell")[1].split("\n")[0], "the work gift to-do is [work]", q)

# ---------------------------------------------------------------- bought
rc, o, e = run("bought", "Robin Lake", "1", "--date", "2026-11-19")
check(rc == 0 and "Bought for Robin Lake: Trail running vest, $64.50 (for birthday 2026)." in o,
      "bought by idea number: price carried, tied to the coming birthday", o + e)
check([i["idea"] for i in data()["gifts"]["Robin Lake"]["ideas"]] == ["Cookbook"], "the idea leaves the list")
rc, o, e = run("brief")
robin = next((ln for ln in o.splitlines() if "Robin Lake's birthday" in ln), "")
check("Gift bought (19-Nov-2026)." in robin and "order by" not in robin, "the brief says it's bought", robin)
# Bought (or recorded) just after the day: it's for that day, not next year's.
run("add", "Ash Green", "11-15", "--action", "gift")
rc, o, e = run("bought", "Ash Green", "A late scarf", "--date", "2026-11-17")
check(rc == 0 and "(for birthday 2026)" in o, "a gift recorded two days after the birthday is for that birthday", o + e)
rc, o, e = run("brief", KIT_TODAY="2027-11-01")
ash = next((ln for ln in o.splitlines() if "Ash Green" in ln), "")
check("Gift bought" not in ash, "so next year's brief still asks about a gift", o)
rc, o, e = run("bought", "Ash Green", "Gloves", "--date", "12-28", KIT_TODAY="2027-01-03")
check(rc == 0 and any(b["date"] == "2026-12-28" for b in data()["gifts"]["Ash Green"]["bought"]) if rc == 0 else False,
      "12-28 written on 03-Jan is last December", o + e)
rc, o, e = run("bought", "Robin Lake", "9")
check(rc == 1 and "1 idea(s)" in e, "an idea number that isn't there is refused", e)
rc, o, e = run("bought", "Kai", "Puzzle", "--price", "22", "--for", "birthday")
check(rc == 0 and "(for birthday 2027)" in o, "--for birthday: the next one, so next year's for a January date", o + e)
rc, o, e = run("bought", "Kai", "Puzzle", "--date", "2026-12-01")
check(rc == 1 and "hasn't happened" in e, "no future purchase dates", e)
rc, o, e = run("--days", "60")
check("Kai's birthday; gift (bought)" in o and "Robin Lake's birthday (turns 36), friend; gift (bought)" in o,
      "the upcoming list says bought", o)

# ---------------------------------------------------------------- gifts views
rc, o, e = run("gifts", "Robin")
check(rc == 0 and "Robin Lake: budget $75 per occasion; delivery 4 days" in o and "1. Cookbook ($30) [birthday]" in o
      and "19-Nov-2026: Trail running vest, $64.50 (for birthday 2026)" in o and "bought: Trail running vest" in o,
      "gifts NAME: budget, next date, ideas, bought", o + e)
rc, o, e = run("gifts")
check("Gift dates in the next 60 days:" in o and "Sun 29-Nov Ops team farewell [work]: order by Sun 22-Nov; 0 idea(s)" in o,
      "gifts: the coming gift dates with order-by", o)
check("Spent in 2026: $86.50 on 2 gift(s): Robin Lake $64.50 of $75; Kai $22" in o, "the year's spending against the budget", o)
rc, o, e = run("gifts", "--year", "2027")
check("Spent in" not in o, "--year: that year's spending only", o)
rc, o, e = run("gift-remove", "Robin Lake", "1")
check(rc == 0 and "Dropped for Robin Lake: Cookbook" in o and data()["gifts"]["Robin Lake"]["ideas"] == [], "gift-remove")
j = json.loads(run("--json", "--days", "60")[1])
r = next(x for x in j if x["name"] == "Robin Lake")
check(r["order_by"] == "2026-11-26" and r["gift_bought"] is True, "--json carries the order-by date and bought")

shutil.rmtree(tmp)
print(f"\n{'FAILED' if fails else 'passed'}: kit-dates gifts, {len(fails)} failure(s)")
sys.exit(1 if fails else 0)

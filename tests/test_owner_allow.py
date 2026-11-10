#!/usr/bin/env python3
"""The installer respects an ask rule the owner moved to their own allow list: it doesn't add Kit's ask rule
back (an ask rule beats an allow rule, so that would undo the owner's decision on every install), says so,
keeps every other ask rule, and a rule Kit added to the allow list itself doesn't count as the owner's.
Deactivating leaves the owner's allow rule alone. Synthetic home folder; nothing outside it is touched.

  python3 tests/test_owner_allow.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SETUP = REPO / "shared/kit_setup.py"
sys.path.insert(0, str(REPO / "shared"))
import kit_setup  # noqa: E402  (for its ASK and ALLOW lists only)

P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-owner-allow-"))
HOME = TMP / "home"
KIT = HOME / "Claude/Agents/kit"
KIT.mkdir(parents=True)
SET = HOME / ".claude/settings.json"
SET.parent.mkdir(parents=True)
ENV = dict(os.environ, KIT_DIR=str(KIT), HOME=str(HOME), USERPROFILE=str(HOME), PYTHONDONTWRITEBYTECODE="1")
RULE = "Bash(osascript *)"
ok(RULE in kit_setup.ASK, "osascript is one of Kit's ask rules (the case this test covers)")


def setup(cmd):
    r = subprocess.run([sys.executable, str(SETUP), cmd], capture_output=True, text=True, env=ENV, timeout=60)
    return r.returncode, r.stdout + r.stderr


def perms():
    return json.loads(SET.read_text())["permissions"]


# A first install adds every ask rule.
SET.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}}))
rc, out = setup("activate")
ok(rc == 0 and RULE in perms()["ask"], "a first install adds the osascript ask rule", out)

# The owner moves it: out of ask, into their own allow list. Reinstalling leaves it that way.
data = json.loads(SET.read_text())
data["permissions"]["ask"].remove(RULE)
data["permissions"]["allow"].append(RULE)
SET.write_text(json.dumps(data))
rc, out = setup("activate")
p = perms()
ok(rc == 0 and RULE not in p["ask"] and RULE in p["allow"], "a reinstall doesn't add it back to ask", p.get("ask"))
ok("Left out Kit's ask rule for " + RULE in out, "and says so, with how to undo it", out)
ok(all(r in p["ask"] for r in kit_setup.ASK if r != RULE), "every other ask rule is still there")
rc, out = setup("activate")
ok(RULE not in perms()["ask"], "a third install leaves it out too")

# A rule in both lists stays in both, and the installer doesn't claim it left it out.
data = json.loads(SET.read_text())
data["permissions"]["ask"].append(RULE)
SET.write_text(json.dumps(data))
rc, out = setup("activate")
ok(RULE in perms()["ask"] and "Left out" not in out, "a rule the owner keeps in both lists is left as it is", out)

# Deactivating takes out Kit's own entries and leaves the owner's allow rule.
rc, out = setup("deactivate")
p = json.loads(SET.read_text()).get("permissions", {})
ok(rc == 0 and RULE in p.get("allow", []) and "Bash(ls)" in p.get("allow", []), "deactivate keeps the owner's allow rules", p)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nowner allow tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)

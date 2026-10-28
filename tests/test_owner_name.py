#!/usr/bin/env python3
"""test_owner_name.py: the name Kit's templates call the owner, and what they call the computer.

  python3 tests/test_owner_name.py

Checks shared/kit_setup.py: first names from display names ("Rivera, Alex" style included),
KIT_OWNER winning, never the bare login with nobody at the keyboard, and "Mac"/"PC"/"computer".
Runs on macOS, Linux, and Windows; CI runs it on Linux and Windows.
"""
import importlib.util
import io
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kit_setup", ROOT / "shared" / "kit_setup.py")
ks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ks)

fails = 0


def check(cond, name, detail=""):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f" -- {detail}"))
    fails += 0 if cond else 1


for full, want in [("Alex Rivera", "Alex"), ("Rivera, Alex", "Alex"), ("Rivera, Alex M.", "Alex"),
                   ("Rivera, Alex (Contractor)", "Alex"), ("[EXT] Rivera, Alex", "Alex"),
                   ("Dr. Maria L. Chen Jr.", "Maria"), ("  ", ""), ("", ""), ("1234", ""), (None, "")]:
    got = ks._first_name(full)
    check(got == want, f"first name of {full!r} is {want!r}", f"got {got!r}")

os.environ["KIT_OWNER"] = "Testy"
check(ks._owner_name() == "Testy", "KIT_OWNER wins")

os.environ.pop("KIT_OWNER", None)
login = (os.environ.get("USER") or os.environ.get("USERNAME") or "").strip()


class Terminal(io.StringIO):
    """Output that claims to be a terminal, so only the input side decides."""
    def isatty(self):
        return True


# Input from the null device (which on Windows claims to be a terminal): nobody's at the keyboard,
# so there must be no question.
sys.stdin = open(os.devnull)
shown, real = Terminal(), sys.stdout
sys.stdout = shown
try:
    got = ks._owner_name()
finally:
    sys.stdout = real
check("What first name" not in shown.getvalue(), "no question when input comes from the null device",
      shown.getvalue().strip())
print(f"     (without KIT_OWNER on this machine: {got!r}; login {login!r})")
check(bool(got), "a name comes back without KIT_OWNER")
check(not login or got.lower() != login.lower() or got == "your owner",
      "the bare login is never used as the name", f"got {got!r}")

want = "Mac" if sys.platform == "darwin" else ("PC" if os.name == "nt" else "computer")
check(ks.COMPUTER == want, f"this computer is called {want!r}", f"got {ks.COMPUTER!r}")

for rel in ("kit/KIT.md", "kit/memory/context/kit-setup.md"):
    text = (ROOT / rel).read_text(encoding="utf-8")
    check("'s Mac" not in text, f"{rel} doesn't assume a Mac")

print(f"\n{'all passed' if not fails else f'{fails} failed'}")
sys.exit(1 if fails else 0)

#!/usr/bin/env python3
"""Kit's automated checks. GitHub Actions runs them on every push; they also run locally:

  python3 .github/scripts/checks.py

1. Shell: `zsh -n` or `bash -n` on every shell script (by shebang, or .sh).
2. Python: every .py file, and every script whose shebang is python, compiles.
3. PowerShell: every .ps1 and .psm1 parses (needs pwsh).
4. Job templates: every .plist and .plist.template parses, with its placeholders filled in.
5. JSON: every .json file parses.
6. Personal details: when SCAN_PATTERNS is set (a repository secret, one regular expression per
   line), no tracked file matches any of them. Matches are reported by file, line, and pattern
   number, never by the pattern itself. A match ending in ".md" is a Claude Code @-import of a
   file, not an address, and isn't counted. The copyright line in LICENSE names the copyright
   holder on purpose and isn't scanned; the rest of LICENSE is. The fourth Gospel's name in a Bible
   reference (a chapter and verse, a numbered letter, or the name alone in quotes, as in the library's
   table of books) isn't a person's name and isn't counted either, as in export_public.py.

Exits 1 if anything fails.
"""
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
listed = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout
FILES = [ROOT / f for f in listed.splitlines() if f and (ROOT / f).is_file()]
fails = []
counts = {}


def rel(p):
    return str(p.relative_to(ROOT))


def shebang(p):
    try:
        with open(p, "rb") as fh:
            first = fh.readline(200).decode(errors="ignore")
    except OSError:
        return ""
    return first if first.startswith("#!") else ""


shell, py, ps, plists, jsons = [], [], [], [], []
for p in FILES:
    sb, name = shebang(p), p.name
    if name.endswith((".ps1", ".psm1")):
        ps.append(p)
    elif name.endswith(".py") or "python" in sb:
        py.append(p)
    elif name.endswith(".sh") or re.search(r"\b(zsh|bash|sh)\b", sb):
        shell.append((p, "bash" if re.search(r"\b(bash|sh)\b", sb) and "zsh" not in sb else "zsh"))
    elif name.endswith((".plist", ".plist.template")):
        plists.append(p)
    elif name.endswith(".json"):
        jsons.append(p)

# 1. Shell
for p, sh in shell:
    if not shutil.which(sh):
        fails.append(f"{rel(p)}: {sh} isn't installed, so it wasn't checked")
        continue
    r = subprocess.run([sh, "-n", str(p)], capture_output=True, text=True)
    if r.returncode:
        fails.append(f"{rel(p)}: {r.stderr.strip()[:300]}")
counts["shell scripts"] = len(shell)

# 2. Python
for p in py:
    try:
        compile(p.read_text(encoding="utf-8"), str(p), "exec")
    except SyntaxError as e:
        fails.append(f"{rel(p)}:{e.lineno}: {e.msg}")
counts["Python files"] = len(py)

# 3. PowerShell
if ps:
    pwsh = shutil.which("pwsh")
    if not pwsh:
        fails.append("pwsh isn't installed, so the PowerShell files weren't checked")
    else:
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False) as tf:
            tf.write("$bad = 0\n"
                     "foreach ($f in $args) {\n"
                     "  $errs = $null\n"
                     "  [void][System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$null, [ref]$errs)\n"
                     "  foreach ($x in $errs) { Write-Output (\"{0}:{1}: {2}\" -f $f, $x.Extent.StartLineNumber, $x.Message); $bad = 1 }\n"
                     "}\n"
                     "exit $bad\n")
        r = subprocess.run([pwsh, "-NoProfile", "-File", tf.name, *map(str, ps)], capture_output=True, text=True)
        os.unlink(tf.name)
        for line in (r.stdout + r.stderr).splitlines():
            if line.strip():
                fails.append(line.replace(str(ROOT) + os.sep, "").strip()[:300])
counts["PowerShell files"] = len(ps)

# 4. Job templates
for p in plists:
    text = p.read_text(encoding="utf-8").replace("{{USER}}", "runner").replace("{{HOME}}", "/Users/runner")
    try:
        plistlib.loads(text.encode())
    except Exception as e:  # noqa: BLE001
        fails.append(f"{rel(p)}: doesn't parse ({e})")
counts["job templates"] = len(plists)

# 5. JSON
for p in jsons:
    try:
        json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        fails.append(f"{rel(p)}: {e}")
counts["JSON files"] = len(jsons)

# 6. Personal details
# The fourth Gospel and its letters in Bible references, not a person: a chapter and verse after the name,
# a numbered letter, or the name alone in quotes (the library's table of books). Spelled in two parts so
# this line doesn't match the scan itself.
GOSPEL = "Jo" + "hn"
BIBLE = re.compile(rf'\b[123]\s+{GOSPEL}\b|\b{GOSPEL}(?=\s+\d)|(?<="){GOSPEL}(?=")|(?<=\'){GOSPEL}(?=\')')
patterns = [line for line in os.environ.get("SCAN_PATTERNS", "").splitlines() if line.strip()]
if patterns:
    rxs = [re.compile(x) for x in patterns]
    scanned = 0
    for p in FILES:
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for n, line in enumerate([rel(p)] + lines):
            if rel(p) == "LICENSE" and line.startswith("Copyright "):
                continue   # names the copyright holder on purpose
            line = BIBLE.sub("BIBLE-BOOK", line)
            for i, rx in enumerate(rxs, 1):
                if any(not m.group(0).endswith(".md") for m in rx.finditer(line)):
                    fails.append(f"{rel(p)}:{n}: matches personal-details pattern #{i}")
    counts["files scanned for personal details"] = scanned
else:
    print("Personal-details scan skipped: SCAN_PATTERNS isn't set.")

for what, n in counts.items():
    print(f"checked {n} {what}")
if fails:
    print(f"\n{len(fails)} problem(s):")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("\nAll checks passed.")

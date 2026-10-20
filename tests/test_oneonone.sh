#!/bin/bash
# Tests kit-oneonone (1:1 prep) with a fixture Kit in a throwaway folder.
#   bash tests/test_oneonone.sh
cd "$(dirname "$0")/.." || exit 1
exec python3 - "$PWD" <<'PY'
import os, pathlib, subprocess, sys, tempfile, shutil
repo = pathlib.Path(sys.argv[1]); tool = repo / "shared/bin/kit-oneonone"
tmp = pathlib.Path(tempfile.mkdtemp()); kit = tmp / "kit"
P = F = 0
def ok(c, n):
    global P, F
    if c: P += 1; print("ok  ", n)
    else: F += 1; print("FAIL", n)
(kit / "memory/context").mkdir(parents=True); (kit / "briefs").mkdir(); (kit / ".install/shared/morning").mkdir(parents=True)
(kit / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\n')
shutil.copy(repo / "kit/memory/context/oneonone.md", kit / "memory/context/oneonone.md")
(kit / "memory/accomplishments.md").write_text("# Accomplishments\n\n- 01-Oct-2026 [Other] Old thing (queue)\n- 15-Oct-2026 [Decisions] ADR-0001 accepted: folder transport (ADR)\n")
(kit / "STATUS.md").write_text("# Status\n\n## Blocked, and on whom\n- Confluence token returns 401.\n\n## Next\n- later\n")
(kit / "QUEUE.md").write_text("""# Queue

## Alex
- [ ] **Decide the radar voters** [work]: due 22-Oct-2026 (added 10-Oct-2026)
- [ ] **Need budget for the lab** [work] (added 10-Oct-2026)
- [ ] **Read a book** (added 10-Oct-2026)

## Kit
- [ ] **Approve the SQL test plan**: due 01-Dec-2026 (added 10-Oct-2026)

## Waiting on others
- [ ] **Extra credits**: Prod Support, since 15-Oct-2026 (added 15-Oct-2026)

## Done
""")
env = dict(os.environ, KIT_DIR=str(kit), KIT_TODAY="2026-10-19")
run = lambda *a: subprocess.run([sys.executable, str(tool), *a], capture_output=True, text=True, env=env)
r = run("--print"); t = r.stdout
ok(r.returncode == 0 and "1:1 prep with the manager" in t, "default role is 'manager' when not set")
ok("ADR-0001" in t and "Old thing" not in t, "wins limited to the look-back window (14 days)")
ok("Confluence token returns 401" in t, "blockers from STATUS.md")
ok("Extra credits" in t, "waiting on others listed")
ok("22-Oct-2026: Decide the radar voters" in t and "01-Dec-2026" not in t, "deadlines within 14 days only")
ok("## Decisions I need" in t and "Decide the radar voters" in t.split("## Decisions I need")[1], "decision items")
ok("Need budget for the lab" in t.split("## Asks")[1], "asks listed")
ok("Read a book" not in t, "unrelated items left out")
s = (kit / "memory/context/oneonone.md").read_text().replace("- **Manager role:** not set.", "- **Manager role:** head of architecture.")
(kit / "memory/context/oneonone.md").write_text(s)
r = run(); out = kit / "briefs/oneonone-2026-10-19.md"
ok(out.exists() and "head of architecture" in out.read_text(), "writes the brief with the role")
r = run("--done")
ok("Last 1:1:** 19-Oct-2026" in (kit / "memory/context/oneonone.md").read_text(), "--done records the date")
env["KIT_TODAY"] = "2026-10-25"
r = run("--print")
ok("ADR-0001" not in r.stdout and "Covers 19-Oct-2026" in r.stdout, "next prep starts at the last 1:1")
ok("[address]" not in r.stdout and "@" not in r.stdout, "no addresses")
shutil.rmtree(tmp)
print(f"kit-oneonone tests: {P} passed, {F} failed"); sys.exit(1 if F else 0)
PY

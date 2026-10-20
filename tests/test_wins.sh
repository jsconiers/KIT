#!/bin/bash
# Tests kit-wins (accomplishments log) with a fixture Kit and library in a throwaway folder.
#   bash tests/test_wins.sh
cd "$(dirname "$0")/.." || exit 1
exec python3 - "$PWD" <<'PY'
import os, pathlib, subprocess, sys, tempfile, shutil
repo = pathlib.Path(sys.argv[1]); tool = repo / "shared/bin/kit-wins"
tmp = pathlib.Path(tempfile.mkdtemp()); kit = tmp / "kit"; lib = tmp / "lib"
P = F = 0
def ok(c, n):
    global P, F
    if c: P += 1; print("ok  ", n)
    else: F += 1; print("FAIL", n)
(kit / "memory/context").mkdir(parents=True); (kit / "briefs").mkdir(); (kit / ".install/shared/morning").mkdir(parents=True)
(kit / ".install/shared/morning/config").write_text('OWNER_NAME="Alex"\n')
(kit / "memory/context/library.md").write_text(f"- **Library root:** `{lib}`\n")
(kit / "QUEUE.md").write_text("""# Queue

## Sprint

Sprint s1: 19-Oct-2026 to 30-Oct-2026
- [x] **Org profile for sharing** (M) [done]
- [ ] **Trust rules** (L) [open]

## Alex
- [ ] **Open thing**

## Kit

## Done
- [x] **Built the connector harness**: Kit, done 18-Oct-2026 (added 16-Oct-2026)
- [x] **Draft GDS for payments** [work]: done 17-Oct-2026 (added 10-Oct-2026)
- [x] **Book the dentist**: done 17-Oct-2026 (added 10-Oct-2026)
""")
(lib / "decisions").mkdir(parents=True); (lib / "poc").mkdir()
(lib / "decisions/INDEX.md").write_text("| Number | Title | Status | Date |\n|---|---|---|---|\n| ADR-0001 | Use folder transport | accepted | 15-Oct-2026 |\n| ADR-0002 | Maybe SQL | proposed | |\n")
(lib / "poc/INDEX.md").write_text("| Id | Title | Verdict | Closed |\n|---|---|---|---|\n| POC-0001 | Vendor X logging | go | 14-Oct-2026 |\n| POC-0002 | Vendor Y | pending | |\n")
(lib / "LOG.md").write_text("# Library log\n\n- 16-Oct-2026: Added `artifacts/pay/ia-v1.docx` as LIB-0300.\n- 16-Oct-2026: Rebuilt the index.\n")
(kit / "briefs/kit-release-notes-2026-10-19.md").write_text("# What changed in Kit\n\nUpdated: 1.4.0 (aaaaaaa) to 1.4.0 (bbbbbbb).\n")
env = dict(os.environ, KIT_DIR=str(kit), KIT_TODAY="2026-10-19")
run = lambda *a: subprocess.run([sys.executable, str(tool), *a], capture_output=True, text=True, env=env)
r = run("collect", "--dry-run")
ok(r.returncode == 0 and "would add" in r.stdout, "collect --dry-run reports")
ok(not (kit / "memory/accomplishments.md").exists(), "dry run writes nothing")
r = run("collect"); log = (kit / "memory/accomplishments.md").read_text()
ok("Built the connector harness" in log, "Kit's done item collected")
ok("Draft GDS for payments" in log and "[work]" not in log, "owner's [work] item collected, tag stripped")
ok("dentist" not in log, "owner's untagged (possibly personal) item skipped")
ok("Org profile for sharing" in log and "Trust rules" not in log, "finished sprint item collected, open one not")
ok("ADR-0001 accepted" in log and "ADR-0002" not in log, "accepted ADR collected, proposed skipped")
ok("POC-0001" in log and "verdict go" in log and "POC-0002" not in log, "POC verdict collected, pending skipped")
ok("LIB-0300" in log and "Rebuilt the index" not in log, "library document added collected, index rebuild skipped")
ok("Kit updated to 1.4.0 (bbbbbbb)" in log, "release notes collected")
ok("[Decisions] ADR-0001" in log and "[POCs and labs] POC-0001" in log, "themes assigned")
n1 = len(log.splitlines()); r = run("collect")
ok(len((kit / "memory/accomplishments.md").read_text().splitlines()) == n1 and "added 0" in r.stdout, "second collect adds nothing (dedupe)")
r = run()
ok(r.returncode == 0 and "this month" in r.stdout, "show this month")
r = run("report", "--from", "01-Oct-2026", "--to", "2026-10-31")
ok("## Decisions" in r.stdout and "## POCs and labs" in r.stdout and "item(s)" in r.stdout, "report grouped by theme")
r = run("report", "--from", "nonsense")
ok(r.returncode != 0, "bad date refused")
shutil.rmtree(tmp)
print(f"kit-wins tests: {P} passed, {F} failed"); sys.exit(1 if F else 0)
PY

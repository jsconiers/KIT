#!/usr/bin/env python3
"""Tests for kit-release, which cuts a release in one step: the checks (a clean clone on a branch, a newer version,
no tag yet, something under Unreleased), the edits (VERSION, the dated CHANGELOG heading, the docs' "Describes" and
"Date" rows), the commit and its message, the annotated tag, and the release zip (one top-level folder, the commit
in the zip comment, the installers in it) with its SHA-256 written beside it, which kit-update --zip then accepts.
--dry-run changes nothing. Runs in a throwaway git repository; never pushes.

  python3 tests/test_release.py
"""
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO = pathlib.Path(__file__).resolve().parent.parent
P = F = 0


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:900])


TMP = pathlib.Path(tempfile.mkdtemp(prefix="kit-release-"))
R = TMP / "KIT"
ENV = dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="Test",
           GIT_COMMITTER_EMAIL="t@example.invalid", PYTHONDONTWRITEBYTECODE="1", GIT_CONFIG_NOSYSTEM="1",
           HOME=str(TMP))


def sh(*a, cwd=R):
    return subprocess.run(list(a), cwd=cwd, capture_output=True, text=True, env=ENV, timeout=120)


for d in ("kit/agents", "shared/bin", "platform/mac", "platform/windows", "docs"):
    (R / d).mkdir(parents=True)
shutil.copy2(REPO / "shared/bin/kit-release", R / "shared/bin/kit-release")
(R / "VERSION").write_text("1.6.3\n")
(R / "kit/KIT.md").write_text("# Kit\n")
(R / "platform/mac/install.sh").write_text("#!/bin/bash\n")
(R / "platform/windows/install.ps1").write_text("# install\n")
(R / ".gitignore").write_text("dist/\n")
CHANGELOG = """# Changelog

## [Unreleased]

### Added
- `kit-trace --xlsx`: the traceability matrix as a workbook for reviewers (shared/kit_xlsx.py).
- A health score badge on the dashboard. It combines four things.

### Fixed
- kit-wins month counts unpriced runs.

## [1.6.3] - 2026-11-03

### Fixed
- An older fix.
"""
(R / "CHANGELOG.md").write_text(CHANGELOG)
(R / "docs/GUIDE.md").write_text("# Guide\n\n| | |\n|---|---|\n| Describes | Kit 1.6.3 |\n| Date | 03-Nov-2026 |\n")
(R / "docs/GUIDE.docx").write_bytes(b"PK fake")
(R / "docs/NOTES.md").write_text("# Notes\n\nNo version row here.\n")
sh("git", "init", "-q", "-b", "main")
sh("git", "add", "-A")
sh("git", "commit", "-q", "-m", "start")
TOOL = R / "shared/bin/kit-release"


def rel(*a):
    r = sh(sys.executable, str(TOOL), *a)
    return r.returncode, r.stdout, r.stderr


def head():
    return sh("git", "rev-parse", "HEAD").stdout.strip()


start = head()
rc, out, err = rel("1.7.0", "--dry-run", "--date", "2026-11-14")
ok(rc == 0 and "1.6.3 -> 1.7.0" in out and "edit CHANGELOG.md" in out and "edit docs/GUIDE.md" in out
   and "docs/NOTES.md" not in out, "--dry-run lists the edits", out + err)
ok("Release 1.7.0" in out and "Added: `kit-trace --xlsx`: the traceability matrix as a workbook for reviewers" in out,
   "--dry-run shows the commit message, summarised from the changelog", out)
ok(head() == start and (R / "VERSION").read_text() == "1.6.3\n" and not (R / "dist").exists(), "--dry-run changes nothing")

for args, why in ((["1.6.3"], "isn't newer"), (["1.5.0"], "isn't newer"), (["1.7"], "isn't a version"),
                  (["1.7.0", "--date", "14-Nov"], "Invalid isoformat")):
    rc, out, err = rel(*args)
    ok(rc == 1 and why.lower() in err.lower(), f"refused: {' '.join(args)}", err)
(R / "VERSION").write_text("1.6.3\n\n")
rc, out, err = rel("1.7.0")
ok(rc == 1 and "uncommitted changes" in err, "refused: uncommitted changes", err)
(R / "VERSION").write_text("1.6.3\n")
sh("git", "tag", "v1.7.0")
rc, out, err = rel("1.7.0")
ok(rc == 1 and "already exists" in err, "refused: the tag exists", err)
sh("git", "tag", "-d", "v1.7.0")
inst = TMP / "installed/shared/bin"
inst.mkdir(parents=True)
shutil.copy2(TOOL, inst / "kit-release")
r = sh(sys.executable, str(inst / "kit-release"), "1.7.0", cwd=TMP)
ok(r.returncode == 1 and "isn't a git clone" in r.stderr, "refused: the installed copy isn't a clone", r.stderr)

# ---- the real thing ---------------------------------------------------------------------------------------------
rc, out, err = rel("1.7.0", "--date", "2026-11-14", "--trailer", "Co-Authored-By: Someone <x@example.invalid>")
ok(rc == 0, "it releases", out + err)
ok((R / "VERSION").read_text() == "1.7.0\n", "VERSION is bumped")
log = (R / "CHANGELOG.md").read_text()
ok("## [1.7.0] - 2026-11-14\n\n### Added" in log and "## [Unreleased]" not in log and "## [1.6.3] - 2026-11-03" in log,
   "the Unreleased heading becomes the dated release", log[:300])
g = (R / "docs/GUIDE.md").read_text()
ok("| Describes | Kit 1.7.0 |" in g and "| Date | 14-Nov-2026 |" in g, "the docs' version and date rows", g)
msg = sh("git", "log", "-1", "--format=%B").stdout
ok(msg.startswith("Release 1.7.0\n") and "VERSION 1.6.3 -> 1.7.0: 3 change(s)" in msg
   and "- Fixed: kit-wins month counts unpriced runs." in msg and msg.rstrip().endswith("<x@example.invalid>"),
   "the commit message, with the trailer last", msg)
ok(sh("git", "status", "--porcelain").stdout.strip() == "", "everything is committed (the zip goes in ignored dist/)")
tag = sh("git", "cat-file", "-t", "v1.7.0").stdout.strip()
ok(tag == "tag" and sh("git", "rev-parse", "v1.7.0^{commit}").stdout.strip() == head()
   and "Kit 1.7.0" in sh("git", "tag", "-n1", "v1.7.0").stdout, "an annotated tag v1.7.0 on the release commit")
short = head()[:7]
z = R / "dist" / f"KIT-1.7.0-{short}.zip"
ok(z.is_file(), "the zip is in dist/, named with the version and commit", list((R / "dist").glob("*")))
with zipfile.ZipFile(z) as zf:
    names = zf.namelist()
    ok({n.split("/")[0] for n in names} == {"KIT-1.7.0"} and "KIT-1.7.0/platform/mac/install.sh" in names,
       "one top-level folder, with the installers", names[:8])
    ok(zf.comment.decode() == head() and zf.read("KIT-1.7.0/VERSION").decode().strip() == "1.7.0",
       "the commit is in the zip comment; VERSION inside says 1.7.0")
digest = hashlib.sha256(z.read_bytes()).hexdigest()
ok(f"SHA-256: {digest}" in out and (R / "dist" / f"{z.name}.sha256").read_text() == f"{digest}  {z.name}\n",
   "the SHA-256 is printed and written beside the zip", out)
ok("rebuild the Word and PDF copies of GUIDE.md" in out and "nothing was pushed" in out,
   "it says which Word and PDF copies to rebuild, and that nothing was pushed", out)

# The zip goes through kit-update's own checks for an untrusted release zip.
upd = REPO / "shared/bin/kit-update"
if upd.exists():
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("kit_update_rel", str(upd))
    spec = importlib.util.spec_from_loader("kit_update_rel", loader)
    mod = importlib.util.module_from_spec(spec)
    try:
        loader.exec_module(mod)
        fn = getattr(mod, "inspect_zip", None) or getattr(mod, "check_zip", None)
        if fn:
            info = fn(z)
            info = info[0] if isinstance(info, tuple) else info
            ok(isinstance(info, dict) and info.get("version") == "1.7.0" and info.get("commit") == head().lower(),
               "kit-update reads the version and commit from it", info)
        else:
            print("skip kit-update has no zip inspector to call")
    except SystemExit:
        print("skip kit-update couldn't be loaded here")

rc, out, err = rel("1.7.1")
ok(rc == 1 and "nothing under ## [Unreleased]" in err, "refused: nothing under Unreleased", err)

# --build-docs: its changes in docs/ go in the release commit; a failing build puts everything back.
(R / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n\n### Fixed\n- A fix.\n\n" +
                                (R / "CHANGELOG.md").read_text().split("\n", 2)[2])
sh("git", "commit", "-qam", "next")
before = head()
build = f'"{sys.executable}" -c "import pathlib; pathlib.Path(\'docs/GUIDE.docx\').write_bytes(b\'PK rebuilt\')"'
rc, out, err = rel("1.7.1", "--no-zip", "--build-docs", f'{build} && exit 3')
ok(rc == 1 and "--build-docs failed (exit 3)" in err and head() == before
   and (R / "docs/GUIDE.docx").read_bytes() == b"PK fake" and (R / "VERSION").read_text() == "1.7.0\n"
   and sh("git", "status", "--porcelain").stdout.strip() == "", "a failing --build-docs puts everything back", out + err)
rc, out, err = rel("1.7.1", "--no-zip", "--build-docs", build)
files = sh("git", "show", "--name-only", "--format=", "HEAD").stdout.split()
ok(rc == 0 and "docs/GUIDE.docx" in files and "VERSION" in files and "rebuild the Word" not in out
   and (R / "docs/GUIDE.docx").read_bytes() == b"PK rebuilt", "--build-docs: the rebuilt copies are in the release commit",
   out + err + str(files))

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nkit-release tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)

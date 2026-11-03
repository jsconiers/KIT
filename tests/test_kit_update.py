#!/usr/bin/env python3
"""Tests for kit-update: rerunning the installer when the clone is current but the install isn't from its
commit (it skipped the install when the clone had moved without it), --reinstall, and a landed patch
that differs from GitHub's commit only in binary files GitHub rebuilt (the Word and PDF documents).

  python3 tests/test_kit_update.py

Each case builds a throwaway "GitHub" (a bare repo), a clone, and a home folder, with a stand-in
installer that records its run and writes VERSION.json the way the real one does. Runs on macOS, Linux,
and Windows (the stand-in for install.ps1 there).
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent.parent
TOOL = HERE / "shared/bin/kit-update"
P = F = 0

INSTALL_SH = """#!/bin/bash
here="$(cd "$(dirname "$0")/../.." && pwd)"
inst="$HOME/Claude/Agents/kit/.install"
mkdir -p "$inst"
printf '{"version": "%s", "commit": "%s", "previous": {"version": "before"}}' \\
  "$(tr -d '[:space:]' < "$here/VERSION")" "$(git -C "$here" rev-parse HEAD)" > "$inst/VERSION.json"
echo ran >> "$HOME/installer-runs.txt"
"""
INSTALL_PS1 = """$here = (Resolve-Path (Join-Path $PSScriptRoot '..\\..')).Path
$inst = Join-Path $env:USERPROFILE 'Claude\\Agents\\kit\\.install'
New-Item -ItemType Directory -Force -Path $inst | Out-Null
$c = (git -C $here rev-parse HEAD).Trim()
$v = (Get-Content (Join-Path $here 'VERSION') -Raw).Trim()
('{"version": "' + $v + '", "commit": "' + $c + '", "previous": {"version": "before"}}') |
  Set-Content -Path (Join-Path $inst 'VERSION.json') -Encoding ASCII
Add-Content -Path (Join-Path $env:USERPROFILE 'installer-runs.txt') -Value 'ran'
"""


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:1500])


def run(cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)


def git(repo, *args):
    r = run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false", *args])
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr}")
    return r.stdout.strip()


def write(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_bytes(data.encode("utf-8"))


class Case:
    """A fresh GitHub (bare repo), the clone (KIT_REPO), a second clone that plays GitHub's side, and a
    home folder (HOME and USERPROFILE) for the install."""

    def __init__(self, tmp, name):
        self.root = tmp / name
        self.home = self.root / "home"
        self.home.mkdir(parents=True)
        self.origin = self.root / "github.git"
        run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)])
        self.clone = self.root / "KIT"
        self.clone.mkdir()
        git(self.clone, "init", "-q", "-b", "main")
        git(self.clone, "config", "core.autocrlf", "false")    # LF on Windows too, as committed
        write(self.clone / "VERSION", "1.0.0\n")
        write(self.clone / "notes.txt", "first\n")
        write(self.clone / "docs/guide.pdf", b"%PDF-1.7\n\x00\x01\x02 first build\n")
        write(self.clone / "platform/mac/install.sh", INSTALL_SH)
        write(self.clone / "platform/windows/install.ps1", INSTALL_PS1)
        git(self.clone, "add", "-A")
        git(self.clone, "commit", "-qm", "Kit 1.0.0")
        git(self.clone, "remote", "add", "origin", str(self.origin))
        git(self.clone, "push", "-q", "origin", "main")
        git(self.clone, "branch", "-q", "--set-upstream-to=origin/main", "main")
        self.other = self.root / "github-side"
        run(["git", "clone", "-q", "--config", "core.autocrlf=false", str(self.origin), str(self.other)])
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home), KIT_REPO=str(self.clone))

    def kit_update(self, *args):
        return run([sys.executable, str(TOOL), *args], env=self.env)

    def install_record(self, commit, version="1.0.0"):
        inst = self.home / "Claude/Agents/kit/.install"
        inst.mkdir(parents=True, exist_ok=True)
        (inst / "VERSION.json").write_text(json.dumps({"version": version, "commit": commit}), encoding="utf-8")

    def record(self):
        try:
            return json.loads((self.home / "Claude/Agents/kit/.install/VERSION.json").read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return {}

    def runs(self):
        f = self.home / "installer-runs.txt"
        return len(f.read_text().split()) if f.exists() else 0

    def head(self):
        return git(self.clone, "rev-parse", "HEAD")

    def backups(self):
        return [b for b in git(self.clone, "branch", "--list", "backup/*", "--format=%(refname:short)").split() if b]

    def github_commit(self, files, message):
        """A commit on GitHub, made from the other clone."""
        git(self.other, "pull", "-q", "origin", "main")
        for path, data in files.items():
            write(self.other / path, data)
        git(self.other, "add", "-A")
        git(self.other, "commit", "-qm", message)
        git(self.other, "push", "-q", "origin", "main")
        return git(self.other, "rev-parse", "HEAD")

    def local_commit(self, files, message):
        for path, data in files.items():
            write(self.clone / path, data)
        git(self.clone, "add", "-A")
        git(self.clone, "commit", "-qm", message)
        return self.head()


tmp = pathlib.Path(tempfile.mkdtemp(prefix="kit-update-test-"))
try:
    # ------------------------------------------------------------------ up to date, install matches
    c = Case(tmp, "current")
    c.install_record(c.head())
    r = c.kit_update()
    ok(r.returncode == 0 and "already up to date with GitHub, and the install matches the clone" in r.stdout,
       "current clone and matching install: nothing to do", r.stdout + r.stderr)
    r = c.kit_update("--apply", "--yes")
    ok(r.returncode == 0 and c.runs() == 0, "--apply with nothing to do doesn't run the installer", r.stdout + r.stderr)
    r = c.kit_update("--reinstall", "--yes")
    ok(r.returncode == 0 and c.runs() == 1 and "the clone stays at" in r.stdout and not c.backups(),
       "--reinstall runs the installer anyway, without moving the clone or making a backup branch", r.stdout + r.stderr)

    # ------------------------------------------------------------------ up to date, install lags (the 02-Nov bug)
    c = Case(tmp, "lagging")
    old = c.head()
    c.install_record(old)
    git(c.other, "pull", "-q", "origin", "main")
    c.github_commit({"VERSION": "1.1.0\n", "notes.txt": "second\n"}, "Release 1.1.0")
    git(c.clone, "pull", "-q", "origin", "main")          # the clone moved without the installer
    new = c.head()
    r = c.kit_update()
    ok(r.returncode == 0 and f"the clone is up to date with GitHub, but the install is from {old[:7]}, not the "
       f"clone's {new[:7]}" in r.stdout, "plain kit-update says the install lags the clone", r.stdout + r.stderr)
    ok("Version: 1.0.0 (installed) -> 1.1.0 (the clone)" in r.stdout and "Release 1.1.0" in r.stdout
       and "To install the clone's version: kit-update --apply" in r.stdout and c.runs() == 0,
       "the preview shows the versions and the commits not yet installed, and changes nothing", r.stdout)
    r = c.kit_update("--apply")
    ok(r.returncode == 1 and "no one at the keyboard" in r.stdout and "Traceback" not in r.stderr and c.runs() == 0,
       "--apply without --yes and no one to ask: nothing runs (on Windows too, where NUL counts as a terminal)",
       r.stdout + r.stderr)
    r = c.kit_update("--apply", "--yes")
    ok(r.returncode == 0 and c.runs() == 1 and c.head() == new and not c.backups(),
       "--apply reruns the installer when the clone is current but the install isn't (the bug: it skipped it)",
       r.stdout + r.stderr)
    ok(c.record().get("commit") == new and "Kit before -> 1.1.0" in r.stdout and "kit-update: done." in r.stdout,
       "the install is then from the clone's commit", (c.record(), r.stdout))
    r = c.kit_update("--apply", "--yes")
    ok(r.returncode == 0 and c.runs() == 1 and "the install matches the clone" in r.stdout,
       "a second --apply has nothing to do", r.stdout + r.stderr)

    # ------------------------------------------------------------------ no version record, and an unrecorded commit
    c = Case(tmp, "unrecorded")
    r = c.kit_update()
    ok(r.returncode == 0 and "has no version record" in r.stdout and "kit-update --apply" in r.stdout,
       "no VERSION.json: the preview says so and offers --apply", r.stdout + r.stderr)
    c.install_record("unknown")
    r = c.kit_update("--apply", "--yes")
    ok(r.returncode == 0 and "doesn't record which commit" in r.stdout and c.runs() == 1
       and c.record().get("commit") == c.head(), "an install with no commit recorded is reinstalled", r.stdout + r.stderr)

    # ------------------------------------------------------------------ the install is newer than the clone
    c = Case(tmp, "newer")
    git(c.clone, "checkout", "-q", "-b", "ahead")
    later = c.local_commit({"notes.txt": "later\n"}, "Not on GitHub yet")
    git(c.clone, "checkout", "-q", "main")
    c.install_record(later)
    r = c.kit_update("--apply", "--yes")
    ok(r.returncode == 0 and "newer than the clone" in r.stdout and c.runs() == 0,
       "an install newer than the clone isn't replaced by --apply", r.stdout + r.stderr)
    r = c.kit_update("--reinstall", "--yes")
    ok(r.returncode == 0 and c.runs() == 1 and c.record().get("commit") == c.head(),
       "--reinstall installs the clone's version anyway", r.stdout + r.stderr)

    # ------------------------------------------------------------------ GitHub ahead: the usual update still works
    c = Case(tmp, "fast-forward")
    c.install_record(c.head())
    tip = c.github_commit({"VERSION": "1.2.0\n"}, "Release 1.2.0")
    r = c.kit_update("--apply", "--yes")
    ok(r.returncode == 0 and c.head() == tip and c.runs() == 1 and len(c.backups()) == 1
       and "Version: 1.0.0 -> 1.2.0" in r.stdout, "GitHub ahead: the clone moves, a backup branch, the installer runs",
       r.stdout + r.stderr)

    # ------------------------------------------------------------------ a landed patch, exactly
    c = Case(tmp, "landed-exact")
    c.install_record(c.head())
    change = {"notes.txt": "patched\n", "docs/guide.pdf": b"%PDF-1.7\n\x00\x01\x02 patched build\n"}
    mine = c.local_commit(change, "My patch")
    landed = c.github_commit(change, "My patch, as GitHub has it")
    tip = c.github_commit({"VERSION": "1.0.1\n"}, "Release 1.0.1")
    r = c.kit_update()
    ok(r.returncode == 0 and f"landed on GitHub as {landed[:7]}; 2 GitHub commit(s) to take" in r.stdout,
       "a patch GitHub applied with exactly the clone's files is recognized", r.stdout + r.stderr)
    r = c.kit_update("--apply", "--yes")
    ok(r.returncode == 0 and c.head() == tip and c.runs() == 1 and git(c.clone, "rev-parse", c.backups()[0]) == mine,
       "--apply moves onto GitHub's main, with the local commit on the backup branch", r.stdout + r.stderr)

    # ------------------------------------------------------------------ a landed patch, with rebuilt documents
    c = Case(tmp, "landed-binary")
    c.install_record(c.head())
    mine = c.local_commit({"notes.txt": "patched\n", "docs/guide.pdf": b"%PDF-1.7\n\x00\x01\x02 built here\n"},
                          "My patch")
    landed = c.github_commit({"notes.txt": "patched\n", "docs/guide.pdf": b"%PDF-1.7\n\x00\x01\x02 rebuilt there\n"},
                             "My patch, documents rebuilt")
    r = c.kit_update()
    ok(r.returncode == 0 and f"landed on GitHub as {landed[:7]}, apart from 1 binary file(s) rebuilt there "
       "(docs/guide.pdf)" in r.stdout and "your versions stay on the backup branch" in r.stdout,
       "a patch GitHub applied with rebuilt binary files is recognized, and the files are named (the 1.6.1 refusal)",
       r.stdout + r.stderr)
    r = c.kit_update("--apply", "--yes")
    ok(r.returncode == 0 and c.head() == landed and c.runs() == 1
       and git(c.clone, "show", f"{c.backups()[0]}:docs/guide.pdf").endswith("built here"),
       "--apply takes GitHub's documents; the clone's own build stays on the backup branch", r.stdout + r.stderr)

    # ------------------------------------------------------------------ not landed: a text difference, or a new file
    c = Case(tmp, "not-landed-text")
    c.local_commit({"notes.txt": "patched\n", "docs/guide.pdf": b"%PDF-1.7\n\x00 here\n"}, "My patch")
    c.github_commit({"notes.txt": "patched differently\n", "docs/guide.pdf": b"%PDF-1.7\n\x00 there\n"}, "Other")
    before = c.head()
    r = c.kit_update("--apply", "--yes")
    ok(r.returncode == 1 and "commit(s) GitHub doesn't" in r.stdout and c.head() == before and c.runs() == 0,
       "a text file that differs: still refused, nothing changes", r.stdout + r.stderr)

    c = Case(tmp, "not-landed-added")
    c.local_commit({"notes.txt": "patched\n"}, "My patch")
    c.github_commit({"notes.txt": "patched\n", "docs/extra.pdf": b"%PDF-1.7\n\x00 new\n"}, "Patch plus a new file")
    r = c.kit_update()
    ok(r.returncode == 1 and "commit(s) GitHub doesn't" in r.stdout,
       "a binary file only one side has isn't a rebuilt document: refused", r.stdout + r.stderr)

    c = Case(tmp, "not-landed-binary-removed")
    c.local_commit({"notes.txt": "patched\n"}, "My patch")
    git(c.other, "pull", "-q", "origin", "main")
    write(c.other / "notes.txt", "patched\n")
    git(c.other, "rm", "-q", "docs/guide.pdf")
    git(c.other, "commit", "-qam", "Patch, and the document removed")
    git(c.other, "push", "-q", "origin", "main")
    r = c.kit_update()
    ok(r.returncode == 1 and "commit(s) GitHub doesn't" in r.stdout,
       "a binary file removed on one side: refused", r.stdout + r.stderr)

    # ------------------------------------------------------------------ uncommitted changes still stop it
    c = Case(tmp, "dirty")
    c.install_record("0" * 40)
    write(c.clone / "notes.txt", "edited, not committed\n")
    r = c.kit_update("--reinstall", "--yes")
    ok(r.returncode == 1 and "uncommitted changes" in r.stdout and c.runs() == 0,
       "uncommitted changes stop even --reinstall", r.stdout + r.stderr)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\nkit-update tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)

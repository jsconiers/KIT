#!/usr/bin/env python3
"""Tests for kit-update --zip: checking, previewing, and installing a release zip (the kind
`git archive --format=zip --prefix=KIT-<version>/` makes), for installs with no git clone.

  python3 tests/test_kit_update_zip.py

Each case uses a throwaway home folder (HOME and USERPROFILE) and temp folder, synthetic zips, and a
stand-in installer that records its run and writes VERSION.json the way the real one does. Covers a
valid upgrade, read-only previews, unsafe zips (zip slip, absolute paths, drive letters, backslashes,
symlinks, devices, two top-level folders, too big, too many files), a missing layout file, SHA-256
checks, downgrades, the same version, the release kept and pruned to 3, VERSION.json, the owner's name
kept, and a git clone left untouched (with the git path then leaving the newer install alone). Runs on
macOS, Linux, and Windows (the stand-in for install.ps1 there).
"""
import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

HERE = pathlib.Path(__file__).resolve().parent.parent
TOOL = HERE / "shared/bin/kit-update"
IS_WIN = os.name == "nt"
P = F = 0

INSTALL_SH = """#!/bin/bash
here="$(cd "$(dirname "$0")/../.." && pwd)"
inst="$HOME/Claude/Agents/kit/.install"
mkdir -p "$inst"
v="$(tr -d '[:space:]' < "$here/VERSION")"
printf '{"version": "%s", "commit": "%s", "installed": "now"}' "$v" "${KIT_PACKAGE_COMMIT:-unknown}" > "$inst/VERSION.json"
echo "ran $v owner=${KIT_OWNER:-} from=$here" >> "$HOME/installer-runs.txt"
"""
INSTALL_PS1 = """$here = (Resolve-Path (Join-Path $PSScriptRoot '..\\..')).Path
$inst = Join-Path $env:USERPROFILE 'Claude\\Agents\\kit\\.install'
New-Item -ItemType Directory -Force -Path $inst | Out-Null
$v = (Get-Content (Join-Path $here 'VERSION') -Raw).Trim()
$c = $env:KIT_PACKAGE_COMMIT; if (-not $c) { $c = 'unknown' }
('{"version": "' + $v + '", "commit": "' + $c + '", "installed": "now"}') |
  Set-Content -Path (Join-Path $inst 'VERSION.json') -Encoding ASCII
Add-Content -Path (Join-Path $env:USERPROFILE 'installer-runs.txt') -Value ("ran " + $v + " owner=" + $env:KIT_OWNER + " from=" + $here)
"""
CHANGELOG = """# Changelog

## [Unreleased]
- not yet

## [1.4.0] - 2026-04-01
- four

## [1.3.0] - 2026-03-01
- three

## [1.2.0] - 2026-02-01
- two

## [1.1.0] - 2026-01-15
- one point one

## [1.0.0] - 2026-01-01
- first
"""


def ok(cond, name, detail=""):
    global P, F
    if cond:
        P += 1
        print("ok  ", name)
    else:
        F += 1
        print("FAIL", name, str(detail)[:2000])


def run(cmd, env=None):
    return subprocess.run(cmd, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)


def commit_for(version):
    return hashlib.sha1(version.encode()).hexdigest()


def package(version, extra=None, drop=(), top=None):
    """The files of a synthetic Kit release, as {relative path: bytes}."""
    files = {
        "VERSION": f"{version}\n",
        "CHANGELOG.md": CHANGELOG,
        "README.md": f"Kit {version}\n",
        "install.sh": "#!/bin/bash\nexec bash platform/mac/install.sh\n",
        "install.ps1": "& powershell -File platform\\windows\\install.ps1\n",
        "platform/mac/install.sh": INSTALL_SH,
        "platform/windows/install.ps1": INSTALL_PS1,
        "kit/KIT.md": "# Kit\n",
        "shared/kit_setup.py": f"# setup {version}\n",
        "shared/bin/kit-update": "#!/usr/bin/env python3\n",
        f"shared/bin/kit-new-in-{version}": "#!/usr/bin/env python3\n",
    }
    files.update(extra or {})
    for d in drop:
        files = {k: v for k, v in files.items() if not (k == d or k.startswith(d.rstrip("/") + "/"))}
    return files


def make_zip(path, version, commit="auto", extra=None, drop=(), top=None, raw=()):
    """Write a release zip: one folder KIT-<version>/ (or TOP), the commit in the comment (as git archive
    does) unless commit is None. RAW adds (ZipInfo, data) entries as given, for the unsafe cases."""
    top = top or f"KIT-{version}"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo(top + "/"), b"")
        for rel, data in sorted(package(version, extra, drop).items()):
            zi = zipfile.ZipInfo(f"{top}/{rel}")
            zi.create_system = 3
            zi.external_attr = (stat.S_IFREG | (0o755 if rel.endswith((".sh", "kit-update")) else 0o644)) << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, data.encode() if isinstance(data, str) else data)
        for zi, data in raw:
            zf.writestr(zi, data)
        if commit == "auto":
            commit = commit_for(version)
        if commit:
            zf.comment = commit.encode()
    return path


def raw_entry(name, mode=None):
    zi = zipfile.ZipInfo(name)
    if mode is not None:
        zi.create_system = 3
        zi.external_attr = mode << 16
    return zi


class Case:
    def __init__(self, tmp, name):
        self.root = tmp / name
        self.home = self.root / "home"
        self.temp = self.root / "temp"
        self.zips = self.root / "zips"
        for d in (self.home, self.temp, self.zips):
            d.mkdir(parents=True)
        self.inst = self.home / "Claude/Agents/kit/.install"
        self.releases = self.inst / "releases"
        env = {k: v for k, v in os.environ.items() if k not in ("KIT_OWNER", "KIT_PACKAGE_COMMIT")}
        # PYTHONDONTWRITEBYTECODE: macOS's own Python 3.9 caches bytecode under ~/Library/Caches, which is in
        # the throwaway home the read-only checks compare.
        self.env = dict(env, HOME=str(self.home), USERPROFILE=str(self.home), TMPDIR=str(self.temp),
                        TEMP=str(self.temp), TMP=str(self.temp), KIT_REPO=str(self.root / "no-clone"),
                        PYTHONDONTWRITEBYTECODE="1")

    def installed(self, version, commit=None, files=None):
        """An existing install: VERSION.json and, optionally, some installed files."""
        self.inst.mkdir(parents=True, exist_ok=True)
        (self.inst / "VERSION.json").write_text(json.dumps(
            {"version": version, "commit": commit or commit_for(version), "installed": "before"}), encoding="utf-8")
        for rel, data in (files or {}).items():
            p = self.inst / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(data, encoding="utf-8")

    def zip(self, version, name=None, **kw):
        return make_zip(self.zips / (name or f"KIT-{version}.zip"), version, **kw)

    def kit_update(self, *args):
        return run([sys.executable, str(TOOL), *args], env=self.env)

    def record(self):
        try:
            return json.loads((self.inst / "VERSION.json").read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return {}

    def runs(self):
        f = self.home / "installer-runs.txt"
        return f.read_text(encoding="utf-8", errors="replace").splitlines() if f.exists() else []

    def kept(self):
        return sorted(d.name for d in self.releases.iterdir()) if self.releases.is_dir() else []

    def snapshot(self):
        out = {}
        for p in sorted(self.home.rglob("*")):
            out[p.relative_to(self.home).as_posix()] = p.read_bytes() if p.is_file() else None
        return out

    def temp_left(self):
        return list(self.temp.iterdir())


def text(r):
    return r.stdout + r.stderr


tmp = pathlib.Path(tempfile.mkdtemp(prefix="kit-update-zip-test-"))
try:
    # ------------------------------------------------------------------ read-only preview of an upgrade
    c = Case(tmp, "preview")
    c.installed("1.0.0", files={"shared/kit_setup.py": "# setup 1.0.0\n", "shared/bin/kit-update": "#!/usr/bin/env python3\n",
                                "shared/bin/kit-gone": "old\n", "kit/KIT.md": "# Kit\n"})
    z = c.zip("1.2.0")
    before = c.snapshot()
    r = c.kit_update("--zip", str(z))
    out = text(r)
    ok(r.returncode == 0 and "Kit 1.2.0, folder KIT-1.2.0/" in out and commit_for("1.2.0") in out
       and "from the zip comment" in out, "preview: the zip's version and commit", out)
    ok("Installed: Kit 1.0.0" in out and "The zip is newer." in out, "preview: the installed version, and newer", out)
    ok("- two" in out and "- one point one" in out and "- first" not in out and "- three" not in out
       and "not yet" not in out, "preview: the CHANGELOG entries between the two versions only", out)
    ok("changed" in out and "~ shared/kit_setup.py" in out and "+ shared/bin/kit-new-in-1.2.0" in out
       and "1 only in the install" in out, "preview: added, changed, and install-only files against the installed copy", out)
    ok(f"SHA-256: {hashlib.sha256(z.read_bytes()).hexdigest()}" in out, "preview: the zip's SHA-256 is printed", out)
    ok(c.snapshot() == before and not c.releases.exists() and not c.runs() and not c.temp_left()
       and "Nothing changed. To install it" in out,
       "read-only: nothing in the home folder changes, no release kept, no installer, no temp files left", out)
    r = c.kit_update("--zip", str(z), "--apply")
    ok(r.returncode == 1 and "no one at the keyboard" in text(r) and not c.runs() and c.snapshot() == before,
       "--apply without --yes and no one to ask: nothing installed", text(r))

    # ------------------------------------------------------------------ a valid upgrade
    c = Case(tmp, "upgrade")
    c.installed("1.0.0")
    (c.inst / "shared/morning").mkdir(parents=True)
    (c.inst / "shared/morning/config").write_text('# settings\nOWNER_NAME="Testy"\n', encoding="utf-8")
    z = c.zip("1.1.0", name="KIT-1.1.0-abc1234.zip")
    digest = hashlib.sha256(z.read_bytes()).hexdigest()
    r = c.kit_update("--zip", str(z), "--apply", "--yes")
    out = text(r)
    rel = c.releases / f"1.1.0-{commit_for('1.1.0')[:7]}"
    ok(r.returncode == 0 and len(c.runs()) == 1 and c.runs()[0].startswith("ran 1.1.0"),
       "upgrade: the release's installer ran once", out)
    ok("owner=Testy" in c.runs()[0], "upgrade: the owner's name from the install's settings is passed (KIT_OWNER)", c.runs())
    ok(rel.is_dir() and (rel / "VERSION").read_text().strip() == "1.1.0" and (rel / ".kit-release.json").is_file()
       and rel.name in c.runs()[0],
       "upgrade: the release is kept in .install/releases/<version>-<shortsha>/ and its own installer ran", (out, c.runs()))
    v = c.record()
    ok(v.get("version") == "1.1.0" and v.get("commit") == commit_for("1.1.0")
       and v.get("source", {}).get("type") == "zip" and v["source"].get("file") == "KIT-1.1.0-abc1234.zip"
       and v["source"].get("sha256") == digest and v["source"].get("commit") == commit_for("1.1.0"),
       "upgrade: VERSION.json records the zip's name, SHA-256, and commit", v)
    ok("To roll back" in out and "Kit 1.0.0 -> 1.1.0" in out and not c.temp_left(),
       "upgrade: reports the change and how to roll back, and leaves no temp files", out)
    ok("git clone" not in out, "upgrade with no clone: no clone warning", out)

    # ------------------------------------------------------------------ the same version
    r = c.kit_update("--zip", str(z), "--apply", "--yes")
    ok(r.returncode == 0 and "nothing to do" in text(r) and len(c.runs()) == 1,
       "the same version: nothing to do, the installer doesn't run", text(r))
    r = c.kit_update("--zip", str(z), "--reinstall")
    ok(r.returncode == 0 and len(c.runs()) == 1 and "Nothing changed" in text(r),
       "the same version with --reinstall but no --apply: still only a preview", text(r))
    r = c.kit_update("--zip", str(z), "--reinstall", "--apply", "--yes")
    ok(r.returncode == 0 and len(c.runs()) == 2 and c.kept() == [rel.name],
       "the same version with --reinstall --apply: installed again, one release folder", (text(r), c.kept()))

    # ------------------------------------------------------------------ releases kept, pruned to 3
    (c.releases / "not-kits").mkdir()                           # no marker: not Kit's, never pruned
    for ver in ("1.2.0", "1.3.0", "1.4.0"):
        r = c.kit_update("--zip", str(c.zip(ver)), "--apply", "--yes")
        ok(r.returncode == 0, f"upgrade to {ver}", text(r))
    names = c.kept()
    ok(names == sorted(["not-kits"] + [f"{x}-{commit_for(x)[:7]}" for x in ("1.2.0", "1.3.0", "1.4.0")]),
       "the last 3 releases are kept; older ones go, and a folder Kit didn't make stays", names)
    ok("removed 1.1.0-" in text(r) and f"releases{os.sep}1.3.0-" in text(r).replace("/", os.sep),
       "the prune is reported, and the rollback points at the previous release's installer", text(r))

    # ------------------------------------------------------------------ downgrade
    (c.inst / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")   # the real installer copies it
    r = c.kit_update("--zip", str(c.zips / "KIT-1.3.0.zip"), "--apply", "--yes")
    ok(r.returncode == 1 and "OLDER" in text(r) and "--allow-downgrade" in text(r) and c.record()["version"] == "1.4.0",
       "an older zip is refused", text(r))
    ok("- four" in text(r), "a refused downgrade shows the entries it would undo", text(r))
    r = c.kit_update("--zip", str(c.zips / "KIT-1.3.0.zip"), "--apply", "--yes", "--allow-downgrade")
    ok(r.returncode == 0 and c.record()["version"] == "1.3.0" and c.runs()[-1].startswith("ran 1.3.0"),
       "--allow-downgrade installs the older zip", text(r))

    # ------------------------------------------------------------------ SHA-256
    c = Case(tmp, "sha")
    c.installed("1.0.0")
    z = c.zip("1.1.0")
    good = hashlib.sha256(z.read_bytes()).hexdigest()
    r = c.kit_update("--zip", str(z), "--sha256", good.upper())
    ok(r.returncode == 0 and "matches the published value" in text(r), "SHA-256 match", text(r))
    r = c.kit_update("--zip", str(z), "--sha256", "0" * 64, "--apply", "--yes")
    ok(r.returncode == 1 and "doesn't match" in text(r) and not c.runs() and not c.releases.exists(),
       "SHA-256 mismatch: refused, nothing installed", text(r))

    # ------------------------------------------------------------------ no commit in the comment
    z = c.zip("1.1.0", name="nocomment.zip", commit=None)
    r = c.kit_update("--zip", str(z), "--apply", "--yes")
    ok(r.returncode == 0 and "the zip has no comment" in text(r) and c.record().get("commit") == "unknown"
       and c.record()["source"]["commit"] is None and any(n.startswith("1.1.0-zip") for n in c.kept()),
       "no zip comment: said plainly, recorded as unknown, the release named from the zip's SHA-256", (text(r), c.kept()))

    # ------------------------------------------------------------------ unsafe or wrong zips: all refused, nothing changes
    c = Case(tmp, "unsafe")
    c.installed("1.0.0")
    top = "KIT-1.1.0"
    bad = {
        "zip slip (..)": dict(raw=[(raw_entry(f"{top}/../../evil.txt"), b"x")]),
        "zip slip (.. in the middle)": dict(raw=[(raw_entry(f"{top}/shared/../../../evil.txt"), b"x")]),
        "absolute path": dict(raw=[(raw_entry("/tmp/evil.txt"), b"x")]),
        "drive letter": dict(raw=[(raw_entry("C:/evil.txt"), b"x")]),
        "backslash": dict(raw=[(raw_entry(f"{top}\\..\\evil.txt"), b"x")]),
        "symlink": dict(raw=[(raw_entry(f"{top}/shared/link", stat.S_IFLNK | 0o777), b"/etc/passwd")]),
        "device file": dict(raw=[(raw_entry(f"{top}/shared/dev", stat.S_IFCHR | 0o644), b"")]),
        "two top-level folders": dict(raw=[(raw_entry("other/file.txt"), b"x")]),
        "a file at the top level": dict(raw=[(raw_entry("README.txt"), b"x")]),
        "duplicate in another case": dict(raw=[(raw_entry(f"{top}/Shared/kit_setup.py"), b"x")]),
        "missing kit/": dict(drop=("kit/",)),
        "missing VERSION": dict(drop=("VERSION",)),
        "missing the installers": dict(drop=("install.sh", "platform/mac/install.sh")),
    }
    for label, kw in bad.items():
        z = make_zip(c.zips / f"bad-{len(os.listdir(c.zips))}.zip", "1.1.0", **kw)
        before = c.snapshot()
        r = c.kit_update("--zip", str(z), "--apply", "--yes")
        ok(r.returncode == 1 and "refused" in text(r) and "Traceback" not in text(r) and not c.runs()
           and c.snapshot() == before and not c.temp_left() and not (tmp / "evil.txt").exists(),
           f"refused: {label}", text(r))
    r = c.kit_update("--zip", str(make_zip(c.zips / "nokit.zip", "1.1.0", drop=("kit/",))))
    ok("missing kit/" in text(r), "a missing layout file is named", text(r))

    z = c.zips / "huge.zip"
    make_zip(z, "1.1.0")
    with zipfile.ZipFile(z, "a", zipfile.ZIP_DEFLATED) as zf:
        with zf.open(f"{top}/shared/huge.bin", "w", force_zip64=True) as f:
            block = b"\0" * (1 << 20)
            for _ in range(201):
                f.write(block)
    r = c.kit_update("--zip", str(z), "--apply", "--yes")
    ok(r.returncode == 1 and "MB uncompressed" in text(r) and not c.runs() and not c.temp_left(),
       f"refused: over 200 MB uncompressed (a {z.stat().st_size // 1024} KB zip)", text(r))
    z = c.zips / "many.zip"
    make_zip(z, "1.1.0")
    with zipfile.ZipFile(z, "a", zipfile.ZIP_STORED) as zf:
        for i in range(20001):
            zf.writestr(f"{top}/shared/many/{i}", b"")
    r = c.kit_update("--zip", str(z))
    ok(r.returncode == 1 and "entries, more than" in text(r), "refused: too many files", text(r))
    (c.zips / "not.zip").write_text("not a zip\n")
    r = c.kit_update("--zip", str(c.zips / "not.zip"))
    ok(r.returncode == 1 and "isn't a zip" in text(r), "refused: not a zip file", text(r))

    # ------------------------------------------------------------------ a git clone is left untouched
    c = Case(tmp, "clone")
    clone = c.root / "KIT"
    origin = c.root / "github.git"
    g = lambda *a: run(["git", "-C", str(clone), "-c", "user.name=t", "-c", "user.email=t@t",
                        "-c", "core.autocrlf=false", *a])
    run(["git", "init", "-q", "--bare", "-b", "main", str(origin)])
    clone.mkdir()
    g("init", "-q", "-b", "main")
    g("config", "core.autocrlf", "false")
    for rel, data in package("1.0.0").items():
        p = clone / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data.encode())
    g("add", "-A")
    g("commit", "-qm", "Kit 1.0.0")
    g("remote", "add", "origin", str(origin))
    g("push", "-q", "origin", "main")
    g("branch", "-q", "--set-upstream-to=origin/main", "main")
    head = g("rev-parse", "HEAD").stdout.strip()
    c.env["KIT_REPO"] = str(clone)
    c.installed("1.0.0", commit=head)
    status = g("status", "--porcelain").stdout
    r = c.kit_update("--zip", str(c.zip("1.1.0")), "--apply", "--yes")
    ok(r.returncode == 0 and "Warning: the git clone" in text(r) and "now differs from the install" in text(r),
       "with a clone: the zip installs, with a warning that the clone now differs", text(r))
    ok(g("rev-parse", "HEAD").stdout.strip() == head and g("status", "--porcelain").stdout == status
       and not g("branch", "--list", "backup/*").stdout.strip(), "the clone is untouched (same commit, clean, no backup branch)", "")
    runs = len(c.runs())
    r = c.kit_update("--apply", "--yes")
    ok(r.returncode == 0 and "newer than the clone's 1.0.0" in text(r) and len(c.runs()) == runs
       and c.record()["version"] == "1.1.0", "the git path then leaves the newer zip install alone", text(r))
    r = c.kit_update("--reinstall", "--yes")
    ok(r.returncode == 0 and len(c.runs()) == runs + 1 and c.record().get("version") == "1.0.0",
       "--reinstall on the git path installs the clone's version over it", text(r))
    # the same version from a zip, a commit the clone doesn't have: 'different', left alone
    r = c.kit_update("--zip", str(c.zip("1.0.0", name="same.zip")), "--reinstall", "--apply", "--yes")
    runs = len(c.runs())
    r = c.kit_update("--apply", "--yes")
    ok(r.returncode == 0 and "the clone's version but not from the clone's commit" in text(r) and len(c.runs()) == runs,
       "a same-version zip from another commit: the git path reports it different and leaves it", text(r))
    # GitHub moves ahead to 1.0.5 while the install is a 1.1.0 zip: the clone may move, the installer doesn't run
    c.kit_update("--zip", str(c.zip("1.1.0", name="again.zip")), "--reinstall", "--apply", "--yes")
    other = c.root / "github-side"
    run(["git", "clone", "-q", "--config", "core.autocrlf=false", str(origin), str(other)])
    (other / "VERSION").write_text("1.0.5\n")
    run(["git", "-C", str(other), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "Release 1.0.5"])
    run(["git", "-C", str(other), "push", "-q", "origin", "main"])
    runs = len(c.runs())
    r = c.kit_update("--apply", "--yes")
    ok(r.returncode == 0 and "won't run over it" in text(r) and len(c.runs()) == runs and c.record()["version"] == "1.1.0"
       and (clone / "VERSION").read_text().strip() == "1.0.5",
       "GitHub ahead of the clone but behind the zip install: the clone moves, the installer doesn't run", text(r))

    # ------------------------------------------------------------------ kit_version reads a kept release's note
    sys.dont_write_bytecode = True                         # leave no __pycache__ in the repo
    sys.path.insert(0, str(HERE / "shared"))
    import kit_version  # noqa: E402
    pkg = tmp / "kept-release"
    pkg.mkdir()
    (pkg / "VERSION").write_text("1.2.0\n")
    (pkg / ".kit-release.json").write_text(json.dumps({"version": "1.2.0", "commit": commit_for("1.2.0"),
                                                       "file": "KIT-1.2.0.zip", "sha256": "ab" * 32}))
    inst = tmp / "kept-install"
    prev, cur = kit_version.record(pkg, inst)
    ok(cur["commit"] == commit_for("1.2.0") and cur.get("source", {}).get("file") == "KIT-1.2.0.zip",
       "rerunning a kept release's installer records its commit and zip (the rollback path)", cur)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\nkit-update zip tests: {P} passed, {F} failed")
sys.exit(1 if F else 0)

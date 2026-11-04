"""kit_version: Kit's version stamp, install history, and release notes after an update.

The package carries its version in VERSION at the repo root (semver). Each install records it in
~/Claude/Agents/kit/.install/VERSION.json with the package's git commit, the date, what was
installed before, and a short history. When the version or commit changes, the installer writes
briefs/kit-release-notes.md for the next morning brief to summarize once.
"""
import datetime
import json
import os
import re
import subprocess
from pathlib import Path

HISTORY_KEEP = 20


def package_version(repo):
    p = Path(repo) / "VERSION"
    try:
        v = p.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return v or "unknown"


def git(repo, *args):
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


COMMIT_RX = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def release_marker(repo):
    """The note kit-update leaves in a release it keeps (.install/releases/<version>-<commit>/), or {}."""
    try:
        m = json.loads((Path(repo) / ".kit-release.json").read_text(encoding="utf-8"))
        return m if isinstance(m, dict) else {}
    except (OSError, ValueError):
        return {}


def package_commit(repo):
    """The package's git commit. For a package that isn't a git clone (a release zip), the commit
    kit-update read from the zip's comment: passed in KIT_PACKAGE_COMMIT, or in the note it keeps with
    the release; else "unknown"."""
    if not (Path(repo) / ".git").exists():
        for given in (os.environ.get("KIT_PACKAGE_COMMIT", ""), release_marker(repo).get("commit") or ""):
            given = given.strip().lower()
            if COMMIT_RX.fullmatch(given):
                return given
        return "unknown"
    return git(repo, "rev-parse", "HEAD") or "unknown"


def load(install_dir):
    p = Path(install_dir) / "VERSION.json"
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def inventory(install_dir):
    """Agent and command names in an install (or package) tree, for the before/after diff."""
    base = Path(install_dir)
    agents = sorted(p.stem for p in (base / "kit/agents").glob("*.md")) if (base / "kit/agents").is_dir() else []
    tools = sorted(p.name for p in (base / "shared/bin").iterdir()
                   if p.is_file() and not p.name.startswith((".", "_"))) if (base / "shared/bin").is_dir() else []
    return {"agents": agents, "commands": tools}


def _entry(v):
    """An install's version, commit, and date for previous and history, with where it came from when
    kit-update recorded that (a zip)."""
    out = {k: v.get(k) for k in ("version", "commit", "installed")}
    if v.get("source"):
        out["source"] = v["source"]
    return out


def record(repo, install_dir, now=None):
    """Write VERSION.json. Returns (previous, current); previous is {} on a first install."""
    install_dir = Path(install_dir)
    prev = load(install_dir)
    now = now or datetime.datetime.now()
    version, commit = package_version(repo), package_commit(repo)
    marker = release_marker(repo) if not (Path(repo) / ".git").exists() else {}
    carried = (commit == "unknown" and prev.get("version") == version and not marker
               and not os.environ.get("KIT_PACKAGE_COMMIT"))
    if carried:
        commit = prev.get("commit") or "unknown"   # a rerun from the installed copy, which isn't a repo
    cur = {
        "version": version,
        "commit": commit,
        "installed": now.strftime("%Y-%m-%d %H:%M"),
        "previous": _entry(prev) if prev else None,
    }
    if marker:                                     # a release kit-update kept from a zip
        cur["source"] = {"type": "zip", "file": marker.get("file"), "sha256": marker.get("sha256"),
                         "commit": marker.get("commit"), "release": str(repo)}
    elif carried and prev.get("source"):
        cur["source"] = prev["source"]             # a rerun from the installed copy of a zip install
    history = list(prev.get("history", []))
    if prev:
        history.append(_entry(prev))
    cur["history"] = history[-HISTORY_KEEP:]
    install_dir.mkdir(parents=True, exist_ok=True)
    tmp = install_dir / "VERSION.json.tmp"
    tmp.write_text(json.dumps(cur, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, install_dir / "VERSION.json")
    return prev, cur


def changed(prev, cur):
    if not prev:
        return False
    return prev.get("version") != cur.get("version") or prev.get("commit") != cur.get("commit")


def _vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3]) or (0,)


def changelog_between(repo, old, new):
    """CHANGELOG.md sections for versions after `old` up to and including `new`."""
    p = Path(repo) / "CHANGELOG.md"
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return []
    out, keep = [], False
    for line in text.splitlines():
        m = re.match(r"^## \[?([^\]\s]+)\]?", line)
        if m:
            ver = m.group(1)
            keep = ver.lower() != "unreleased" and _vkey(old) < _vkey(ver) <= _vkey(new)
        if keep:
            out.append(line)
    return out


def release_notes(repo, prev, cur, before, after):
    """Markdown release notes for an update from `prev` to `cur`."""
    short = lambda c: (c or "unknown")[:7]
    lines = [f"# What changed in Kit",
             "",
             f"Updated {cur['installed']}: {prev.get('version')} ({short(prev.get('commit'))}) to "
             f"{cur['version']} ({short(cur['commit'])}).",
             ""]
    sections = changelog_between(repo, prev.get("version"), cur["version"]) \
        if prev.get("version") != cur["version"] else []
    if sections:
        lines += sections + [""]
    else:
        subjects = None
        if prev.get("commit") not in (None, "unknown") and cur["commit"] != "unknown":
            subjects = git(repo, "log", "--format=- %s", f"{prev['commit']}..{cur['commit']}")
        lines += ["## Changes", ""]
        lines += [subjects] if subjects else ["- No change list is available for this update."]
        lines.append("")
    for kind, label in (("agents", "agents"), ("commands", "commands")):
        added = sorted(set(after[kind]) - set(before[kind]))
        gone = sorted(set(before[kind]) - set(after[kind]))
        if added:
            lines.append(f"New {label}: " + ", ".join(f"`{a}`" for a in added))
        if gone:
            lines.append(f"Removed {label}: " + ", ".join(f"`{a}`" for a in gone))
    return "\n".join(lines).rstrip() + "\n"


def write_release_notes(kit_dir, repo, prev, cur, before, after):
    """Write briefs/kit-release-notes.md when the version or commit changed. Returns the path or None."""
    if not changed(prev, cur):
        return None
    briefs = Path(kit_dir) / "briefs"
    briefs.mkdir(parents=True, exist_ok=True)
    p = briefs / "kit-release-notes.md"
    p.write_text(release_notes(repo, prev, cur, before, after), encoding="utf-8")
    return p

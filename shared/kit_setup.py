#!/usr/bin/env python3
"""kit_setup.py: install Kit's files, and add Kit to (or remove it from) Claude Code.

  check        confirm ~/.claude/settings.json and ~/.claude/CLAUDE.md can be updated; changes nothing
  scaffold     copy Kit's starter files into ~/Claude/Agents/kit, never overwriting existing ones
  activate     add Kit's import line to ~/.claude/CLAUDE.md and Kit's rules to ~/.claude/settings.json
               (Claude Code's auto memory is left alone)
  deactivate   remove exactly what activate added, as recorded in .install/manifest.json

Both Claude Code files are backed up to ~/Claude/Agents/kit/.install/backups/ before any change.
Standard library only; Python 3.8 or newer.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path

HOME = Path.home()
KIT = HOME / "Claude" / "Agents" / "kit"
INSTALL_DIR = KIT / ".install"
MANIFEST = INSTALL_DIR / "manifest.json"
CLAUDE_DIR = HOME / ".claude"
CLAUDE_MD = CLAUDE_DIR / "CLAUDE.md"
SETTINGS = CLAUDE_DIR / "settings.json"
PACKAGE = Path(__file__).resolve().parent   # this file lives in shared/
REPO = PACKAGE.parent                        # repo root: holds kit/, shared/, platform/, README.md

IMPORT_LINE = "@~/Claude/Agents/kit/KIT.md"
COMMENT_START = "<!-- Kit, installed "
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

K = "~/Claude/Agents/kit"
# Kit keeps its own notes without prompting (the owner chose "save facts itself").
ALLOW = [f"Read({K}/**)", f"Edit({K}/memory/**)", f"Edit({K}/QUEUE.md)", f"Edit({K}/STATUS.md)"]
# Always prompt, even if a broader allow rule exists: Kit's rules, Claude Code's own settings,
# and commands that delete, push or post, install, or change system settings.
ASK = [
    f"Edit({K}/KIT.md)", f"Edit({K}/lessons/**)", f"Edit({K}/preferences/**)", f"Edit({K}/.install/**)",
    "Edit(~/.claude/CLAUDE.md)", "Edit(~/.claude/settings.json)",
    "Bash(rm *)", "Bash(rmdir *)", "Bash(sudo *)",
    "Bash(git push)", "Bash(git push *)", "Bash(git reset --hard)", "Bash(git reset --hard *)", "Bash(git clean *)",
    "Bash(gh pr create *)", "Bash(gh pr merge *)", "Bash(gh issue create *)", "Bash(gh release create *)",
    "Bash(brew install *)", "Bash(brew uninstall *)", "Bash(brew upgrade *)",
    "Bash(pip install *)", "Bash(pip3 install *)", "Bash(python3 -m pip install *)",
    "Bash(npm install -g *)", "Bash(npm i -g *)",
    "Bash(defaults write *)", "Bash(launchctl *)", "Bash(softwareupdate *)", "Bash(osascript *)",
]


class Fail(Exception):
    """A problem to report; the command exits with status 1 and nothing further is changed."""



def _owner_name():
    """First name for {{OWNER}} in templates: KIT_OWNER, else this machine's account name."""
    name = os.environ.get("KIT_OWNER", "").strip()
    if not name:
        try:
            import pwd  # POSIX only
            parts = pwd.getpwuid(os.getuid()).pw_gecos.split(",")[0].split()
            name = next((p for p in parts if not p.endswith(".")), "")
        except Exception:
            try:
                import getpass
                name = getpass.getuser()
            except Exception:
                name = ""
    return name or "your owner"


OWNER = _owner_name()

def today():
    d = dt.date.today()
    return f"{d.day:02d}-{MONTHS[d.month - 1]}-{d.year}"


def stamp():
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def real(path):
    """Write through symlinks (for dotfile setups) instead of replacing them."""
    return path.resolve() if path.is_symlink() else path


def write_text_atomic(path, text, new_mode=0o600):
    path = real(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = (path.stat().st_mode & 0o777) if path.exists() else new_mode
    tmp = path.with_name(f".{path.name}.kit-tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    if os.name != "nt":            # POSIX permission bits are meaningless on Windows
        os.chmod(tmp, mode)
    os.replace(tmp, path)


def backup(label):
    dest = INSTALL_DIR / "backups" / f"{stamp()}-{label}"
    saved = []
    for src in (CLAUDE_MD, SETTINGS):
        if src.exists():
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(real(src)), str(dest / src.name))
            saved.append(src.name)
    return dest if saved else None


def load_settings():
    """Return (settings dict, existed). Refuses anything it can't safely edit."""
    if not SETTINGS.exists():
        return {}, False
    try:
        data = json.loads(real(SETTINGS).read_text(encoding="utf-8"))
    except ValueError as exc:
        raise Fail(f"{SETTINGS} isn't valid JSON ({exc}). Nothing was changed; fix it and run this again.")
    if not isinstance(data, dict):
        raise Fail(f"{SETTINGS} doesn't hold a JSON object. Nothing was changed.")
    perms = data.get("permissions")
    if perms is not None and not isinstance(perms, dict):
        raise Fail(f'"permissions" in {SETTINGS} isn\'t an object. Nothing was changed.')
    for key in ("allow", "ask", "additionalDirectories"):
        if perms and key in perms and not isinstance(perms[key], list):
            raise Fail(f'"permissions.{key}" in {SETTINGS} isn\'t a list. Nothing was changed.')
    return data, True


def save_settings(data):
    write_text_atomic(SETTINGS, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def new_manifest():
    return {
        "kit_home": str(KIT),
        "installed": today(),
        "claude_md": {"created_file": False, "added_text": "", "added_newline": False},
        "settings": {
            "created_file": False,
            "created_permissions": False,
            "created_lists": [],
            "added": {"allow": [], "ask": [], "additionalDirectories": []},
            "auto_memory": {"changed": False, "previous": None},
        },
    }


def read_manifest():
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------- commands

def cmd_check(args):
    data, _ = load_settings()
    if CLAUDE_MD.exists():
        try:
            real(CLAUDE_MD).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise Fail(f"can't read {CLAUDE_MD} ({exc.__class__.__name__}). Nothing was changed.")
    if (data.get("permissions") or {}).get("defaultMode") == "bypassPermissions":
        print("note: your settings run Claude Code with permission prompts bypassed. Kit's approval "
              "rules only work with prompts on, so consider changing defaultMode.")
    return 0


def cmd_scaffold(args):
    src = REPO / "kit"
    if not src.is_dir():
        raise Fail(f"can't find the starter files in {src}; run this from the unzipped package")
    KIT.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(KIT, 0o700)
    for folder in ("memory/people", "memory/projects", "memory/context", "lessons", "preferences",
                   ".install/backups"):
        (KIT / folder).mkdir(parents=True, exist_ok=True)
    date = today()
    created, kept, newer = [], [], []
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = path.relative_to(src)
        dest = KIT / rel
        text = path.read_text(encoding="utf-8").replace("{{DATE}}", date).replace("{{OWNER}}", OWNER)
        if not dest.exists():
            write_text_atomic(dest, text)
            created.append(str(rel))
        elif dest.read_text(encoding="utf-8") != text:
            if rel.as_posix() == "KIT.md":
                write_text_atomic(dest.with_name("KIT.md.new"), text)
                newer.append(str(rel))
            else:
                kept.append(str(rel))   # Kit's notes and your edits always win over the starter files
    # Keep a complete copy of the whole package under .install, so nothing has to stay in
    # ~/Downloads and the scheduled runners/plists always find tools at a stable nested path.
    if REPO.resolve() != INSTALL_DIR.resolve():
        if (REPO / "README.md").exists():
            shutil.copy2(str(REPO / "README.md"), str(INSTALL_DIR / "README.md"))
        for sub in ("kit", "shared", "platform"):
            s = REPO / sub
            if s.is_dir():
                # Copy over the top rather than rmtree + copytree: a re-run refreshes the
                # packaged files and keeps what this install added (shared/morning/config,
                # the built KitCal and KitMail apps).
                shutil.copytree(str(s), str(INSTALL_DIR / sub), dirs_exist_ok=True)
    if os.name != "nt":
        for rel in ("shared/kit_setup.py", "platform/mac/install.sh", "platform/mac/uninstall.sh"):
            p = INSTALL_DIR / rel
            if p.exists():
                os.chmod(p, 0o700)
    print(f"Kit's files: {len(created)} created, {len(kept)} kept as they were.")
    if newer:
        print("Kept your KIT.md; the packaged version is KIT.md.new, so compare and merge if you like.")
    return 0


def cmd_activate(args):
    data, existed = load_settings()                 # validates before anything is written
    claude_md_text = real(CLAUDE_MD).read_text(encoding="utf-8") if CLAUDE_MD.exists() else None
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    saved = backup("before-install")
    man = read_manifest() or new_manifest()
    s, c = man["settings"], man["claude_md"]

    # settings.json
    if not existed:
        s["created_file"] = True
    perms = data.get("permissions")
    if perms is None:
        perms = data["permissions"] = {}
        s["created_permissions"] = True
    for key, wanted in (("allow", ALLOW), ("ask", ASK), ("additionalDirectories", [str(KIT)])):
        if key not in perms:
            perms[key] = []
            if key not in s["created_lists"]:
                s["created_lists"].append(key)
        for item in wanted:
            if item not in perms[key]:
                perms[key].append(item)
                if item not in s["added"][key]:
                    s["added"][key].append(item)
    auto = s["auto_memory"]
    if auto.get("changed"):   # an earlier version of this installer turned auto memory off: undo that
        if data.get("autoMemoryEnabled") is False:
            if auto["previous"] == "absent":
                data.pop("autoMemoryEnabled", None)
            else:
                data["autoMemoryEnabled"] = auto["previous"]
        auto["changed"] = False
        print("Turned Claude Code's auto memory back on, the way it was before Kit.")
    save_settings(data)

    # CLAUDE.md
    text = claude_md_text or ""
    if IMPORT_LINE not in (line.strip() for line in text.splitlines()):
        added_newline = bool(text) and not text.endswith("\n")
        if os.name == "nt":
            uninstall_hint = ("powershell -ExecutionPolicy Bypass -File "
                              "~/Claude/Agents/kit/.install/platform/windows/uninstall.ps1")
        else:
            uninstall_hint = "bash ~/Claude/Agents/kit/.install/platform/mac/uninstall.sh"
        block = ("\n" if text else "") + (
            f"{COMMENT_START}{today()}. To take Kit out, run "
            f"{uninstall_hint} -->\n{IMPORT_LINE}\n")
        write_text_atomic(CLAUDE_MD, text + ("\n" if added_newline else "") + block)
        c.update({"created_file": claude_md_text is None, "added_text": block, "added_newline": added_newline})

    write_text_atomic(MANIFEST, json.dumps(man, indent=2) + "\n")
    print("Kit is now loaded in every Claude Code session.")
    if saved:
        print(f"Backups of your Claude Code files: {saved}")
    return 0


def cmd_deactivate(args):
    man = read_manifest()
    data, existed = load_settings()
    saved = backup("before-uninstall")
    if man is None:
        print("note: no install record found, so only Kit-specific entries are removed; "
              "general command rules and auto memory are left alone.")
        man = new_manifest()
        man["settings"]["added"] = {
            "allow": ALLOW, "ask": [r for r in ASK if K in r], "additionalDirectories": [str(KIT)]}
    s, c = man["settings"], man["claude_md"]

    if existed:
        perms = data.get("permissions")
        if isinstance(perms, dict):
            for key, items in s["added"].items():
                if isinstance(perms.get(key), list):
                    perms[key] = [x for x in perms[key] if x not in items]
                    if not perms[key] and key in s["created_lists"]:
                        del perms[key]
            if not perms and s["created_permissions"]:
                del data["permissions"]
        auto = s["auto_memory"]
        if auto["changed"] and data.get("autoMemoryEnabled") is False:   # untouched since install
            if auto["previous"] == "absent":
                data.pop("autoMemoryEnabled", None)
            else:
                data["autoMemoryEnabled"] = auto["previous"]
        if not data and s["created_file"]:
            real(SETTINGS).unlink()
        else:
            save_settings(data)

    if CLAUDE_MD.exists():
        text = real(CLAUDE_MD).read_text(encoding="utf-8")
        block = c.get("added_text") or ""
        if block and text.endswith(block):
            text = text[: -len(block)]
            if c.get("added_newline") and text.endswith("\n"):
                text = text[:-1]
        else:   # edited since install: remove just Kit's two lines
            text = "".join(line for line in text.splitlines(keepends=True)
                           if line.strip() != IMPORT_LINE and not line.strip().startswith(COMMENT_START))
        if not text.strip() and c.get("created_file"):
            real(CLAUDE_MD).unlink()
        else:
            write_text_atomic(CLAUDE_MD, text)

    if MANIFEST.exists():
        MANIFEST.rename(MANIFEST.with_name(f"manifest.removed-{stamp()}.json"))
    print("Kit is out of Claude Code: the import line and Kit's settings are removed.")
    if saved:
        print(f"Backups taken first: {saved}")
    return 0


def main(argv=None):
    if os.name != "nt":
        os.umask(0o077)
    parser = argparse.ArgumentParser(prog="kit_setup", description="Install or remove Kit.")
    sub = parser.add_subparsers(dest="cmd")
    sub.required = True
    sub.add_parser("check")
    sub.add_parser("scaffold")
    sub.add_parser("activate")
    sub.add_parser("deactivate")
    args = parser.parse_args(argv)
    handlers = {"check": cmd_check, "scaffold": cmd_scaffold, "activate": cmd_activate,
                "deactivate": cmd_deactivate}
    try:
        return handlers[args.cmd](args) or 0
    except Fail as exc:
        print(f"kit: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""kit_setup.py: install Kit's files, and add Kit to (or remove it from) Claude Code.

  check        confirm ~/.claude/settings.json and ~/.claude/CLAUDE.md can be updated; changes nothing
  scaffold     copy Kit's starter files into ~/Claude/Agents/kit, never overwriting existing ones,
               then install Kit's skills (as "skills" does)
  skills       copy kit/skills/<name> into ~/.claude/skills/<name> when no skill of that name is
               there; a skill Kit installed earlier is refreshed only if it hasn't been edited since
  agents       copy Kit's staff (~/Claude/Agents/kit/agents) into ~/.claude/agents; scaffold does this too,
               after refreshing the agents in Kit's folder that you haven't edited
  activate     add Kit's import line to ~/.claude/CLAUDE.md and Kit's rules to ~/.claude/settings.json
               (Claude Code's auto memory is left alone)
  deactivate   remove exactly what activate added, as recorded in .install/manifest.json
  guardcheck   run the connector guard's hooks in ~/.claude/agents the way Claude Code does, and exit 1
               unless each guarded agent blocks a write and allows a read (the installers run it last)

Both Claude Code files are backed up to ~/Claude/Agents/kit/.install/backups/ before any change.
Standard library only; Python 3.8 or newer.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit_version  # noqa: E402

HOME = Path.home()
KIT = HOME / "Claude" / "Agents" / "kit"
INSTALL_DIR = KIT / ".install"
MANIFEST = INSTALL_DIR / "manifest.json"
CLAUDE_DIR = HOME / ".claude"
CLAUDE_MD = CLAUDE_DIR / "CLAUDE.md"
SETTINGS = CLAUDE_DIR / "settings.json"
SKILLS_HOME = Path(os.path.expanduser(os.environ.get("KIT_SKILLS_DIR", str(CLAUDE_DIR / "skills"))))
SKILL_MARK = ".kit-installed.json"           # written into each skill folder Kit installs
AGENT_MARK = INSTALL_DIR / "agents-installed.json"   # hash of each agent file as Kit last wrote it
AGENTS_HOME = CLAUDE_DIR / "agents"
PACKAGE = Path(__file__).resolve().parent   # this file lives in shared/
REPO = PACKAGE.parent                        # repo root: holds kit/, shared/, platform/, README.md

IMPORT_LINE = "@~/Claude/Agents/kit/KIT.md"
COMMENT_START = "<!-- Kit, installed "
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

K = "~/Claude/Agents/kit"
# Kit keeps its own notes without prompting (the owner chose "save facts itself").
ALLOW = [f"Read({K}/**)", f"Edit({K}/memory/**)", f"Edit({K}/QUEUE.md)", f"Edit({K}/STATUS.md)",
         "Bash(kit-letter build *)", "Bash(kit-dates *)", "Bash(kit-expiry *)",
         "Bash(kit-textback status *)", "Bash(kit-textback log *)",
         # The library: finding and reading cataloged documents, refreshing the catalog, and
         # delivering finished work to the output folder (which never overwrites without --replace).
         "Bash(kit-library search *)", "Bash(kit-library find *)", "Bash(kit-library show *)",
         "Bash(kit-library recent *)", "Bash(kit-library collections *)", "Bash(kit-library tags *)",
         "Bash(kit-library rules *)", "Bash(kit-library output *)", "Bash(kit-library status *)",
         "Bash(kit-library --check *)", "Bash(kit-library deliver *)", "Bash(kit-library index *)",
         "Bash(kit-library flush *)",
         # The same reading commands with nothing after them.
         "Bash(kit-library)", "Bash(kit-library search)", "Bash(kit-library find)", "Bash(kit-library recent)",
         "Bash(kit-library collections)", "Bash(kit-library tags)", "Bash(kit-library output)",
         "Bash(kit-library status)", "Bash(kit-library --check)",
         # Kit's own lists (keep in touch, the private feedback log) and the read-only meeting audit.
         "Bash(kit-touch *)", "Bash(kit-feedback *)", "Bash(kit-meetload *)",
         # PPM Express: the connection check, the tool list, and the setup steps, which change nothing; the
         # portfolio pulse and the proposals for meeting actions, which only read it.
         "Bash(kit-ppmx check)", "Bash(kit-ppmx check *)", "Bash(kit-ppmx tools)", "Bash(kit-ppmx tools *)",
         "Bash(kit-ppmx setup)", "Bash(kit-ppmx setup *)", "Bash(kit-ppmx pulse)", "Bash(kit-ppmx pulse *)",
         "Bash(kit-ppmx actions)", "Bash(kit-ppmx actions *)",
         # The end-of-day wrap: it reads Kit's files and writes only its own wrap file.
         "Bash(kit-wrap)", "Bash(kit-wrap *)",
         # The team coverage map and the monthly architecture digest: they read Kit's registers (and PPM Express,
         # read only) and write only Kit's own files (the coverage file, briefs/teammap-*, briefs/digest-*).
         "Bash(kit-teammap)", "Bash(kit-teammap *)", "Bash(kit-digest)", "Bash(kit-digest *)",
         # The technical debt register: only the reading commands. add, set, accept, and close change the team's
         # register in the library with --write, so they ask first, like kit-facts set.
         "Bash(kit-techdebt)", "Bash(kit-techdebt list)", "Bash(kit-techdebt list *)", "Bash(kit-techdebt show *)",
         "Bash(kit-techdebt due)", "Bash(kit-techdebt due *)", "Bash(kit-techdebt month)", "Bash(kit-techdebt month *)",
         "Bash(kit-techdebt brief)", "Bash(kit-techdebt brief *)",
         # The author's desk: books, launch checklists, series bibles, and royalty totals, all in Kit's own author/
         # folder (and Kit Output with --deliver); nothing at KDP or IngramSpark changes.
         "Bash(kit-author)", "Bash(kit-author *)",
         # The review loop's plan only reads (it prints the steps, the agent commands, and the cost), and so do its
         # readiness score and status.
         "Bash(kit-review-loop plan *)", "Bash(kit-review-loop score *)", "Bash(kit-review-loop status)",
         "Bash(kit-review-loop status *)",
         # The MCP watchdog's report and the ticket watcher's last check only read Kit's own logs.
         "Bash(kit-mcp-watch status)", "Bash(kit-mcp-watch status *)", "Bash(kit-tickets show)",
         "Bash(kit-tickets show *)",
         # The sign-off ledger's reading commands (add and require change it only with --write) and the trading
         # insights, which read the journals and write only with --write into journal/.
         "Bash(kit-signoff list *)", "Bash(kit-signoff status *)", "Bash(kit-signoff check *)",
         "Bash(kit-tradeinsights)", "Bash(kit-tradeinsights *)",
         # The vendor evaluation desk's reading commands. The rest change an evaluation in the library or write a
         # file you name, so they ask.
         "Bash(kit-vendors)", "Bash(kit-vendors list)", "Bash(kit-vendors list *)", "Bash(kit-vendors due)",
         "Bash(kit-vendors due *)", "Bash(kit-vendors show *)", "Bash(kit-vendors gaps *)",
         # The consistency checks and the copy drift watcher read documents and write, only with --write, a report
         # in the project's reviews/. The fact sheet's reading commands; set and remove change it, so they ask.
         "Bash(kit-diagtext *)", "Bash(kit-dedupe *)", "Bash(kit-facts show *)", "Bash(kit-facts check *)",
         "Bash(kit-facts check-all *)", "Bash(kit-drift)", "Bash(kit-drift *)",
         # The acronym and page-budget checks read documents and write, only with --write, a report in reviews/.
         "Bash(kit-acronyms *)", "Bash(kit-pages *)",
         # Setup questions and the docs builder's reading commands. Answering, building, and bumping ask.
         "Bash(kit-settings questions)", "Bash(kit-settings questions *)", "Bash(kit-docs plan)",
         "Bash(kit-docs plan *)", "Bash(kit-docs status)", "Bash(kit-docs status *)", "Bash(kit-docs --check)",
         # Review drafts read Kit's own logs and notes and write only Kit's own folders. kit-timeoff asks: --handoff
         # starts a Claude run.
         "Bash(kit-selfeval)", "Bash(kit-selfeval *)", "Bash(kit-360 *)"]
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
    # Signing a letter with the saved signature asks every time (kit-letter build is allowed).
    "Bash(kit-letter sign *)",
    # A test answer changes and sends nothing, but a question still asks Claude (a paid run), so it asks first.
    "Bash(kit-textback test *)",
    # Changing what the library catalogs (collections, tags, rules, exclusions) asks first.
    "Bash(kit-library add *)", "Bash(kit-library remove *)", "Bash(kit-library about *)",
    "Bash(kit-library tag *)", "Bash(kit-library untag *)", "Bash(kit-library rule *)",
    "Bash(kit-library unrule *)", "Bash(kit-library exclude *)", "Bash(kit-library include *)",
    "Bash(kit-library define *)",
    # Copying to the phone mirror (iCloud) and staging a file to text both send files off the Mac, so they ask.
    "Bash(kit-library mirror)", "Bash(kit-library mirror *)", "Bash(kit-library fetch *)",
    # A pre-read or a rehearsal runs Claude on a document (a paid run), so it asks first.
    "Bash(kit-preread *)", "Bash(kit-rehearse *)",
    # The review loop's run starts four paid agent runs on a draft, so it asks first (plan, merge, and feedback
    # make no model call).
    "Bash(kit-review-loop run *)",
    # The settings page opens a local server that can change the run config and the setup files, so it asks first.
    "Bash(kit-settings ui)", "Bash(kit-settings ui *)",
    # A PPM Express call from the command line can change PPM Express (a create_ or update_ tool), so it
    # asks first, and so does adding the server to Claude Desktop's config.
    "Bash(kit-ppmx call *)", "Bash(kit-ppmx desktop)", "Bash(kit-ppmx desktop *)",
    # Making a meeting action's proposal changes PPM Express: it asks every time, one proposal at a time.
    "Bash(kit-ppmx actions apply *)",
    # Every PPM Express change asks, even when the ppmx server is allowed as a whole. A scheduled run
    # can't answer, so it never makes one.
    "mcp__ppmx__create_project", "mcp__ppmx__update_project", "mcp__ppmx__create_task",
    "mcp__ppmx__update_task", "mcp__ppmx__create_key_date", "mcp__ppmx__update_key_date",
    "mcp__ppmx__create_idea", "mcp__ppmx__update_idea", "mcp__ppmx__set_idea_stage",
    "mcp__ppmx__create_record", "mcp__ppmx__update_record",
]

# Claude Code hooks Kit adds to settings.json: the long-session token watchdog (kit-mcp-watch) on every MCP call's
# result and failure. They only log and advise; they never block a call (kit-hook exits 1 at worst, which Claude
# Code treats as a non-blocking error). Removed again by deactivate, by their exact command.
WATCH = '/bin/sh "$HOME/Claude/Agents/kit/.install/shared/bin/kit-hook" kit-mcp-watch {event} || exit 1'
HOOKS = [("PostToolUse", "mcp__.*", WATCH.format(event="post")),
         ("PostToolUseFailure", "mcp__.*", WATCH.format(event="fail"))]


def add_hooks(data, s):
    """Add Kit's hooks to settings.json's "hooks", recording each in the manifest. A "hooks" value that isn't the
    shape Claude Code uses is left alone, with a note."""
    hooks = data.get("hooks")
    if hooks is None:
        hooks = data["hooks"] = {}
        s["created_hooks"] = True
    if not isinstance(hooks, dict):
        print('note: "hooks" in settings.json isn\'t an object, so the MCP watchdog hooks weren\'t added.')
        return
    added = s.setdefault("added_hooks", [])
    for event, matcher, cmd in HOOKS:
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            print(f'note: "hooks.{event}" in settings.json isn\'t a list, so the MCP watchdog hook wasn\'t added there.')
            continue
        have = any(isinstance(g, dict) and any(isinstance(h, dict) and h.get("command") == cmd
                                               for h in (g.get("hooks") or [])) for g in groups)
        if not have:
            groups.append({"matcher": matcher, "hooks": [{"type": "command", "command": cmd, "timeout": 10}]})
        if [event, cmd] not in added:
            added.append([event, cmd])


def remove_hooks(data, s):
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return
    for event, cmd in [tuple(x) for x in (s.get("added_hooks") or [])] or [(e, c) for e, _, c in HOOKS]:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        keep = []
        for g in groups:
            if isinstance(g, dict) and isinstance(g.get("hooks"), list):
                g["hooks"] = [h for h in g["hooks"] if not (isinstance(h, dict) and h.get("command") == cmd)]
                if not g["hooks"]:
                    continue
            keep.append(g)
        if keep:
            hooks[event] = keep
        else:
            hooks.pop(event, None)
    if not hooks and s.get("created_hooks"):
        data.pop("hooks", None)


# Allow rules earlier versions added that now ask instead. Activate takes them out again, but only
# where the install record shows Kit added them (an owner's own rule of the same text stays).
RETIRED_ALLOW = ["Bash(kit-library mirror *)", "Bash(kit-library fetch *)"]


class Fail(Exception):
    """A problem to report; the command exits with status 1 and nothing further is changed."""


def _first_name(full):
    """The first name in a display name: "Alex Rivera" and "Rivera, Alex" give "Alex", and
    "Dr. Maria L. Chen Jr." gives "Maria". Empty when nothing in it looks like a name."""
    full = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", full or "")   # "(Contractor)", "[EXT]"
    if "," in full:                                             # directory style: "Last, First"
        full = full.split(",", 1)[1]
    for part in full.split():
        if not part.endswith(".") and any(c.isalpha() for c in part):
            return part
    return ""


def _windows_full_name():
    """The Windows account's display name: the directory's for a domain or work account, else the
    local account's full name. Empty when neither is set or reachable."""
    try:
        import ctypes
        from ctypes import wintypes
        get = ctypes.windll.secur32.GetUserNameExW
        get.argtypes = [ctypes.c_int, ctypes.c_wchar_p, ctypes.POINTER(wintypes.ULONG)]
        get.restype = wintypes.BOOLEAN
        size = wintypes.ULONG(512)
        buf = ctypes.create_unicode_buffer(size.value)
        if get(3, buf, ctypes.byref(size)) and buf.value.strip():   # 3 = NameDisplay
            return buf.value.strip()
    except Exception:
        pass
    try:
        import ctypes
        from ctypes import wintypes

        class USER_INFO_10(ctypes.Structure):
            _fields_ = [("name", ctypes.c_wchar_p), ("comment", ctypes.c_wchar_p),
                        ("usr_comment", ctypes.c_wchar_p), ("full_name", ctypes.c_wchar_p)]
        netapi = ctypes.windll.netapi32
        netapi.NetUserGetInfo.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, wintypes.DWORD,
                                          ctypes.POINTER(ctypes.c_void_p)]
        netapi.NetUserGetInfo.restype = wintypes.DWORD
        ptr = ctypes.c_void_p()
        if netapi.NetUserGetInfo(None, os.environ.get("USERNAME", ""), 10, ctypes.byref(ptr)) == 0 and ptr.value:
            try:
                return (ctypes.cast(ptr, ctypes.POINTER(USER_INFO_10)).contents.full_name or "").strip()
            finally:
                netapi.NetApiBufferFree(ptr)
    except Exception:
        pass
    return ""


def _interactive():
    """Someone at the keyboard: input and output are both a terminal. On Windows the NUL device
    also claims to be one, so there it must be a real console as well."""
    try:
        if not (sys.stdin and sys.stdin.isatty() and sys.stdout and sys.stdout.isatty()):
            return False
        if os.name == "nt":
            import ctypes
            import msvcrt
            mode = ctypes.c_ulong()
            handle = msvcrt.get_osfhandle(sys.stdin.fileno())
            return bool(ctypes.windll.kernel32.GetConsoleMode(ctypes.c_void_p(handle), ctypes.byref(mode)))
        return True
    except Exception:
        return False


def _owner_name():
    """First name for {{OWNER}} in templates: KIT_OWNER; else the first name in the account's full
    name (the macOS or Linux account's real name; on Windows the directory's display name, or the
    local account's full name); else, with someone at the keyboard, ask. Never the bare login (a
    name like "arivera" or "jsmith"), which isn't what anyone wants to be called."""
    name = os.environ.get("KIT_OWNER", "").strip()
    if name:
        return name
    login = (os.environ.get("USER") or os.environ.get("USERNAME") or "").strip()
    full = ""
    if os.name == "nt":
        full = _windows_full_name()
    else:
        try:
            import pwd  # POSIX only
            full = pwd.getpwuid(os.getuid()).pw_gecos.split(",")[0]
        except Exception:
            full = ""
    if full.strip().lower() == login.lower():   # the "full name" is just the login again
        full = ""
    name = _first_name(full)
    if not name and _interactive():
        try:
            name = input("What first name should Kit call you? ").strip()
        except EOFError:
            name = ""
    return name or "your owner"


_OWNER = None


def owner():
    """The owner's name for the templates, worked out once, when a template first needs it."""
    global _OWNER
    if _OWNER is None:
        _OWNER = _owner_name()
    return _OWNER


# What the templates call this computer ("on Alex's PC").
COMPUTER = "Mac" if sys.platform == "darwin" else ("PC" if os.name == "nt" else "computer")


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
        data = json.loads(real(SETTINGS).read_text(encoding="utf-8-sig"))
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
        data = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
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
    for folder in ("memory/people", "memory/projects", "memory/context", "memory/personal",
                   "memory/personal/decisions", "lessons", "preferences", ".install/backups"):
        (KIT / folder).mkdir(parents=True, exist_ok=True)
    date = today()
    before = kit_version.inventory(INSTALL_DIR)     # what the last install had, for release notes
    created, kept, newer = [], [], []
    marks = _read_agent_marks()
    agents = {"created": [], "updated": [], "current": [], "kept": []}
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = path.relative_to(src)
        dest = KIT / rel
        text = _render(path.read_text(encoding="utf-8"), date)
        if rel.parts[0] == "agents" and rel.suffix == ".md" and len(rel.parts) == 2:
            agents[_scaffold_agent(rel, dest, text, date, marks)].append(rel.stem)
            continue
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
        for name in ("README.md", "INSTALL.md", "DESIGN.md", "VERSION", "CHANGELOG.md", "GOVERNANCE.md",
                     "ONBOARDING.md"):
            if (REPO / name).exists():
                shutil.copy2(str(REPO / name), str(INSTALL_DIR / name))
        if (REPO / "tests/evals").is_dir():   # kit-evals reads its cases from here in the live Kit
            shutil.copytree(str(REPO / "tests/evals"), str(INSTALL_DIR / "tests/evals"), dirs_exist_ok=True)
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
    if any(agents.values()):
        write_text_atomic(AGENT_MARK, json.dumps(marks, indent=2, sort_keys=True) + "\n")
    print(f"Kit's files: {len(created)} created, {len(kept)} kept as they were.")
    print(f"Kit's staff in {KIT / 'agents'}: {len(agents['created'])} added, {len(agents['updated'])} updated, "
          f"{len(agents['current'])} already current, {len(agents['kept'])} kept (edited by you).")
    for name in agents["kept"]:
        print(f"Kept agent {name}: you've edited {KIT / 'agents' / (name + '.md')}, so it was left as it is. "
              f"Kit's version is in {INSTALL_DIR / 'kit' / 'agents' / (name + '.md')}.")
    prev, cur = kit_version.record(REPO, INSTALL_DIR)
    notes = kit_version.write_release_notes(KIT, REPO, prev, cur, before, kit_version.inventory(INSTALL_DIR))
    if notes:
        print(f"Kit updated from {prev.get('version')} to {cur['version']} ({cur['commit'][:7]}); "
              f"release notes in {notes}.")
    elif not prev:
        print(f"Kit version {cur['version']} ({cur['commit'][:7]}).")
    if newer:
        print("Kept your KIT.md; the packaged version is KIT.md.new, so compare and merge if you like.")
    report_skills(install_skills())
    report_agents(install_agents())
    return 0


def _render(text, date):
    text = text.replace("{{DATE}}", date).replace("{{COMPUTER}}", COMPUTER)
    return text.replace("{{OWNER}}", owner()) if "{{OWNER}}" in text else text


def _agent_hash(text):
    """sha256 of an agent file without its `model:` line, which kit-models apply sets."""
    return hashlib.sha256(re.sub(r"(?m)^model:.*\n?", "", text, count=1).encode("utf-8")).hexdigest()


def _read_agent_marks():
    try:
        data = json.loads(AGENT_MARK.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _models_line(name, live_text):
    """The `model:` value the agent should carry: models.json's choice when there is one, else the
    line the live file already has (None to keep the packaged one)."""
    try:
        import kit_models as km
        cfg = km.load(KIT)
        if cfg.get("_path") or cfg.get("_per_agent"):
            return km.resolve_agent(cfg, name)["model"]
    except Exception:   # a broken models.json is kit-models check's to report, not the installer's
        pass
    m = re.search(r"(?m)^model:\s*(\S+)", live_text or "")
    return m.group(1) if m else None


def _with_model(text, model):
    if not model:
        return text
    try:
        import kit_models as km
        return km.set_model_line(text, model)
    except Exception:
        return text


def _scaffold_agent(rel, dest, text, date, marks):
    """Install or refresh one agent in Kit's folder. Returns created, updated, current, or kept.
    An agent is refreshed only when it is Kit's unedited copy: it matches the hash recorded when Kit
    last wrote it or, for installs from before that record, the previously installed package copy.
    The `model:` line is left out of the comparison and kept as models.json sets it."""
    name, want = rel.stem, _agent_hash(text)
    if not dest.exists():
        write_text_atomic(dest, _with_model(text, _models_line(name, None)))
        marks[name] = want
        return "created"
    live = dest.read_text(encoding="utf-8")
    have = _agent_hash(live)
    if have == want:
        marks[name] = want
        return "current"
    base = marks.get(name)
    if base is None:
        prev = INSTALL_DIR / "kit" / rel   # the last install's package copy, before it's replaced below
        if prev.is_file() and prev.resolve() != (REPO / "kit" / rel).resolve():
            base = _agent_hash(_render(prev.read_text(encoding="utf-8"), date))
    if have != base:
        return "kept"     # the owner's edits win over Kit's version
    write_text_atomic(dest, _with_model(text, _models_line(name, live)))
    marks[name] = want
    return "updated"


def install_agents(src=None, dest_root=None):
    """Copy Kit's agents into ~/.claude/agents, where Claude Code loads them (as doctor.py
    --fix-agents does). Returns (installed, updated, current) name lists."""
    src = src or KIT / "agents"
    dest_root = dest_root or AGENTS_HOME
    installed, updated, current = [], [], []
    if not src.is_dir():
        return installed, updated, current
    dest_root.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.glob("*.md")):
        dest, text = dest_root / f.name, f.read_text(encoding="utf-8")
        if dest.exists() and dest.read_text(encoding="utf-8") == text:
            current.append(f.stem)
            continue
        (updated if dest.exists() else installed).append(f.stem)
        write_text_atomic(dest, text)
    return installed, updated, current


def report_agents(result):
    installed, updated, current = result
    print(f"Kit's staff in {AGENTS_HOME}: {len(installed)} installed, {len(updated)} updated, "
          f"{len(current)} already current.")


def cmd_agents(args):
    report_agents(install_agents())
    return 0


def _skill_hash(folder):
    """sha256 over a skill folder's files (not Kit's marker), so edits since install show up."""
    h = hashlib.sha256()
    for f in sorted(p for p in folder.rglob("*") if p.is_file() and p.name != SKILL_MARK):
        h.update(f.relative_to(folder).as_posix().encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def install_skills(src=None, dest_root=None):
    """Copy each kit/skills/<name> into ~/.claude/skills/<name>. Never overwrites a skill the
    owner has: a folder of that name that Kit didn't install, or that changed since Kit installed
    it, is skipped and reported. Returns (installed, updated, current, skipped) name lists."""
    src = src or REPO / "kit" / "skills"
    dest_root = dest_root or SKILLS_HOME
    installed, updated, current, skipped = [], [], [], []
    if not src.is_dir():
        return installed, updated, current, skipped
    for folder in sorted(p for p in src.iterdir() if (p / "SKILL.md").is_file()):
        dest = dest_root / folder.name
        want = _skill_hash(folder)
        if dest.exists():
            try:
                mark = json.loads((dest / SKILL_MARK).read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                mark = None
            if not isinstance(mark, dict) or mark.get("sha256") != _skill_hash(dest):
                skipped.append(folder.name)          # the owner's own skill, or edited since
                continue
            if mark["sha256"] == want:
                current.append(folder.name)
                continue
            shutil.rmtree(str(dest))                 # Kit's own, unedited copy: refresh it
            updated.append(folder.name)
        else:
            installed.append(folder.name)
        shutil.copytree(str(folder), str(dest), ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        write_text_atomic(dest / SKILL_MARK, json.dumps(
            {"installed_by": "kit", "date": today(), "sha256": want}, indent=2) + "\n")
    return installed, updated, current, skipped


def report_skills(result):
    installed, updated, current, skipped = result
    parts = [f"{len(installed)} installed", f"{len(updated)} updated", f"{len(current)} already current"]
    print(f"Kit's skills in {SKILLS_HOME}: " + ", ".join(parts) + ".")
    for name in skipped:
        print(f"Skipped skill {name}: {SKILLS_HOME / name} is yours (or was edited), so it was left "
              f"as it is. Kit's version is in {REPO / 'kit' / 'skills' / name}.")


def cmd_skills(args):
    report_skills(install_skills())
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
    for item in RETIRED_ALLOW:
        if item in s["added"]["allow"] and item in (perms.get("allow") or []):
            perms["allow"].remove(item)
            s["added"]["allow"].remove(item)
    # An ask rule the owner has moved to their own allow list (one Kit didn't add) is the owner's decision: an ask
    # rule beats an allow rule, so adding it back would undo that decision on every install. Leave it out, say so.
    owner_allowed = [r for r in ASK if r in (perms.get("allow") or []) and r not in s["added"]["allow"]]
    for key, wanted in (("allow", ALLOW), ("ask", ASK), ("additionalDirectories", [str(KIT)])):
        if key not in perms:
            perms[key] = []
            if key not in s["created_lists"]:
                s["created_lists"].append(key)
        for item in wanted:
            if key == "ask" and item in owner_allowed:
                if item in s["added"]["ask"]:
                    s["added"]["ask"].remove(item)
                continue
            if item not in perms[key]:
                perms[key].append(item)
                if item not in s["added"][key]:
                    s["added"][key].append(item)
    left_out = [r for r in owner_allowed if r not in perms["ask"]]
    if left_out:
        print("Left out Kit's ask rule for " + ", ".join(left_out) + ": your allow list has it. Take it out "
              "of your allow list and rerun the installer to have Claude Code ask again.")
    add_hooks(data, s)
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
        remove_hooks(data, s)
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


def cmd_guardcheck(args):
    """Claude Code lets a connector call through when a guard hook can't start (no Python, or only the
    Microsoft Store's python3 stub), so the installers check the installed hooks really block."""
    import guard_check
    results, skipped = guard_check.check_all(AGENTS_HOME)
    if skipped:
        print(f"Connector guard: not checked: {skipped}.")
        return 0
    if not results:
        return 0
    bad, lines = guard_check.summary(results)
    if not bad:
        print(f"Connector guard: checked {len(results)} agents in {AGENTS_HOME}: each blocks a write and allows a read.")
        for line in guard_check.grouped(results, "notes"):
            print(f"  note: {line}")
        return 0
    print("kit: the connector guard doesn't work in these agents:", file=sys.stderr)
    for line in lines:
        print(f"  {line}", file=sys.stderr)
    print("kit: install Python 3.8 or newer so that python3, py -3, or python runs it (the Microsoft Store's\n"
          "     python3 stub doesn't count), or set KIT_PYTHON to one. An agent you edited needs the hooks of\n"
          "     Kit's own copy (.install/kit/agents). Then run the installer again; INSTALL.md, Troubleshooting,\n"
          "     has the details.", file=sys.stderr)
    return 1


def main(argv=None):
    if os.name != "nt":
        os.umask(0o077)
    parser = argparse.ArgumentParser(prog="kit_setup", description="Install or remove Kit.")
    sub = parser.add_subparsers(dest="cmd")
    sub.required = True
    sub.add_parser("check")
    sub.add_parser("scaffold")
    sub.add_parser("skills")
    sub.add_parser("agents")
    sub.add_parser("activate")
    sub.add_parser("deactivate")
    sub.add_parser("guardcheck")
    args = parser.parse_args(argv)
    handlers = {"check": cmd_check, "scaffold": cmd_scaffold, "skills": cmd_skills, "agents": cmd_agents, "activate": cmd_activate,
                "deactivate": cmd_deactivate, "guardcheck": cmd_guardcheck}
    try:
        return handlers[args.cmd](args) or 0
    except Fail as exc:
        print(f"kit: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

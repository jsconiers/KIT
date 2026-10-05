#!/usr/bin/env python3
"""Add Kit's work protection to a folder, check it, or take it off.

  python3 ~/Claude/Agents/kit/.install/protect_folder.py <folder>
  python3 ~/Claude/Agents/kit/.install/protect_folder.py --check <folder>
  python3 ~/Claude/Agents/kit/.install/protect_folder.py --remove <folder>

The rules go in <folder>/.claude/settings.local.json, which Claude Code applies when you start
it in that folder. The file is personal: in a git repo it's listed in the repo's
.git/info/exclude, which is never committed or shared, so nothing changes for anyone else.

In a protected folder, Claude Code blocks Kit from reading the owner's personal notes, from changing
Kit's own files, and from the owner's trading and market-data servers.
"""
import json
import pathlib
import subprocess
import sys

RULES = [
    "Read(~/Claude/Agents/kit/memory/personal/**)",
    "Edit(~/Claude/Agents/kit/memory/**)",
    "Edit(~/Claude/Agents/kit/QUEUE.md)",
    "Edit(~/Claude/Agents/kit/STATUS.md)",
    "Read(~/Claude/Agents/kit/QUEUE.md)",
    "Read(~/Claude/Agents/kit/briefs/**)",
    "mcp__traders-edge",
    "mcp__robinhood-local",
    "mcp__etrade",
    "mcp__tastytrade",
    "mcp__alpaca",
    "mcp__tradingview",
    "mcp__yahoo-finance",
    "mcp__quiver-quant",
    "mcp__capital-trades",
]
REL = ".claude/settings.local.json"


def git(folder, *args):
    r = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def keep_out_of_git(folder):
    code, top = git(folder, "rev-parse", "--show-toplevel")
    if code != 0:
        return "not a git repo, nothing to exclude"
    rel = (folder / REL).resolve().relative_to(pathlib.Path(top).resolve()).as_posix()
    if git(folder, "ls-files", "--error-unmatch", rel)[0] == 0:
        return f"WARNING: {rel} is tracked by git. Remove it from the repo before you commit."
    if git(folder, "check-ignore", "-q", rel)[0] == 0:
        return "already ignored by git"
    code, common = git(folder, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if code != 0:
        code, common = git(folder, "rev-parse", "--absolute-git-dir")
    exclude = pathlib.Path(common) / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a") as f:
        f.write(f"\n# Kit work protection (personal settings)\n/{rel}\n")
    return f"listed in {exclude}"


def main(argv):
    mode, args = "add", []
    for a in argv:
        if a in ("--check", "--remove"):
            mode = a[2:]
        else:
            args.append(a)
    if len(args) != 1:
        print(__doc__)
        return 2
    folder = pathlib.Path(args[0]).expanduser().resolve()
    if not folder.is_dir():
        print(f"Not a folder: {folder}")
        return 1
    path = folder / REL
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text() or "{}")
        except json.JSONDecodeError as e:
            print(f"{path} isn't valid JSON ({e}). Fix it first.")
            return 1
    deny = data.get("permissions", {}).get("deny", [])

    if mode == "check":
        have = sum(r in deny for r in RULES)
        print(f"{folder}: {have} of {len(RULES)} protection rules present")
        for r in RULES:
            print(("  ok       " if r in deny else "  MISSING  ") + r)
        return 0 if have == len(RULES) else 1

    if mode == "remove":
        if not path.exists():
            print("No protection here.")
            return 0
        perms = data.setdefault("permissions", {})
        perms["deny"] = [r for r in deny if r not in RULES]
        if not perms["deny"]:
            del perms["deny"]
        if not perms:
            del data["permissions"]
        if data:
            path.write_text(json.dumps(data, indent=2) + "\n")
        else:
            path.unlink()
        print(f"Removed Kit's work protection from {folder}")
        return 0

    perms = data.setdefault("permissions", {})
    deny = perms.setdefault("deny", [])
    added = [r for r in RULES if r not in deny]
    deny.extend(added)
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Protected {folder}: {len(added)} rules added, {len(RULES) - len(added)} already there")
    print("git:", keep_out_of_git(folder))
    print("It applies when you start Claude Code in this folder.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""monitor_library.py: library freshness, an alert kind for run_alerts.py (kind "library").

  python3 monitor_library.py [--kit DIR]

Reads the library setup (memory/context/library.md): the **Library root:** path, and under Published
libraries each library's index ("index" followed by a backticked path) and its synced folder (the first
`~/...` or `/...` path in the same bullet; the index's own "Local folder:" line is the fallback). A
library named GDS or IA with no index given uses published/gds-index.md or published/ia-index.md.

library:index  For each published library, the file names in its folder (by name, Unicode-normalised;
               hidden and Office lock files left out) against the File column of its index: files not
               in the index, and index rows whose file is gone. It alerts when the unindexed files are
               more than LIBRARY_UNINDEXED_MAX (default 0, so any), when an indexed file is gone, or when
               the index is older than LIBRARY_INDEX_MAX_DAYS (default 30) while files changed after it
               was built. The index date is the latest "Built/Updated/Refreshed/Reindexed DD-Mmm-YYYY" in
               the index, else its file date. One [work] queue item for the owner per outage asks the
               librarian to reindex; it clears when the indexes catch up.
library:sync   Inferred. When the library root is under a CloudStorage path (OneDrive and the like): the
               published folders, which only the sync changes, show no file changed in
               LIBRARY_SYNC_MAX_DAYS (default 14) while Kit wrote to the library root within that time. A
               rough "sync may be stalled" signal, so it's marked inferred and gets no queue item, only the
               brief line and the dashboard banner.

Read-only: it lists folders and reads file dates and the index files, never opens a published
document (so OneDrive's on-demand files aren't downloaded) and never edits an index. Time-limited by
MONITOR_TIMEOUT (seconds, default 20): a listing that runs out of time is reported as not checked and
leaves any open alert as it was.
"""
import argparse
import datetime as dt
import os
import pathlib
import re
import sys
import time
import unicodedata

DATE = r"\d{2}-[A-Z][a-z]{2}-\d{4}"
SKIP_NAMES = {"desktop.ini", "thumbs.db", "icon\r"}
FILE_LIKE = re.compile(r"\.[A-Za-z0-9]{2,5}$")


class OutOfTime(Exception):
    pass


def nfc(s):
    return unicodedata.normalize("NFC", s)


def expand(p, base=None):
    p = os.path.expanduser(p.strip())
    if base and not os.path.isabs(p):
        p = os.path.join(base, p)
    return os.path.normpath(p)


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def paths_in(text):
    return [m for m in re.findall(r"`([^`]+)`", text) if m.startswith(("~", "/"))]


def setup(kit):
    """{"root": path or None, "libraries": [{"name", "index", "folder"}]} from library.md."""
    text = read(os.path.join(kit, "memory/context/library.md")) or ""
    out = {"root": None, "libraries": []}
    m = re.search(r"\*\*Library root:\*\*([^\n]*(?:\n(?!\s*[-#])[^\n]*)*)", text)
    if m:
        p = paths_in(m.group(1))
        if p:
            out["root"] = expand(p[0])
    sec = re.search(r"(?:^##\s*Published librar[^\n]*|\*\*Published libraries:\*\*)(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    body = sec.group(1) if sec else ""
    bullets = re.split(r"\n(?=- )", "\n" + body)
    for b in bullets:
        bm = re.match(r"\s*- \*\*([^*]+?):?\*\*:?(.*)", b, re.S)
        if not bm:
            continue
        label, rest = bm.group(1).strip().rstrip(":"), bm.group(2)
        idx = re.search(r"index\s+`([^`]+)`", rest)
        folders = [p for p in paths_in(rest) if not (idx and p == idx.group(1))]
        short = re.split(r"[\s(]", label, 1)[0]
        index = idx.group(1) if idx else ({"gds": "published/gds-index.md", "ia": "published/ia-index.md"}
                                          .get(short.lower()))
        if not index:
            continue
        out["libraries"].append({"name": short, "label": label, "index": index,
                                 "folder": expand(folders[0]) if folders else None})
    return out


def index_info(path):
    """(file names, built date or None) from an index file; None when it can't be read."""
    text = read(path)
    if text is None:
        return None
    files, col = set(), None
    for ln in text.splitlines():
        if not ln.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if col is None and any(c.lower() == "file" for c in cells):
            col = [c.lower() for c in cells].index("file")
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        cands = [cells[col]] if col is not None and col < len(cells) else cells
        for c in cands:
            for name in re.findall(r"`([^`]+)`", c) or ([c] if col is not None else []):
                name = os.path.basename(name.strip())
                if FILE_LIKE.search(name):
                    files.add(nfc(name))
    dates = []
    for m in re.finditer(r"(?:Built|Updated|Refreshed|Reindexed|Rebuilt)\s+(?:on\s+)?(" + DATE + ")", text):
        try:
            dates.append(dt.datetime.strptime(m.group(1), "%d-%b-%Y").date())
        except ValueError:
            pass
    folder = None
    fm = re.search(r"Local folder:\s*`([^`]+)`", text)
    if fm:
        folder = expand(fm.group(1))
    return files, (max(dates) if dates else None), folder


def listing(folder, deadline, limit=20000):
    """{name: mtime} for the files under folder (hidden and lock files skipped). Raises OutOfTime."""
    out = {}
    stack = [folder]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if deadline and time.monotonic() > deadline:
                        raise OutOfTime(folder)
                    n = e.name
                    if n.startswith((".", "~$")) or n.lower() in SKIP_NAMES:
                        continue
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            out[nfc(n)] = max(out.get(nfc(n), 0), e.stat(follow_symlinks=False).st_mtime)
                    except OSError:
                        continue
                    if len(out) >= limit:
                        return out
        except OSError:
            continue
    return out


def newest(files):
    return max(files.values()) if files else None


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def check_index(kit, cfg, now, deadline):
    """(problem or None, notes, folder listings) for library:index."""
    st = setup(kit)
    root = st["root"]
    unindexed_max = int(cfg.number("LIBRARY_UNINDEXED_MAX", 0)) if cfg else 0
    max_days = cfg.number("LIBRARY_INDEX_MAX_DAYS", 30) if cfg else 30
    parts, details, listings, trigger = [], [], {}, False
    for lib in st["libraries"]:
        idx_path = expand(lib["index"], root) if root or os.path.isabs(os.path.expanduser(lib["index"])) else None
        info = index_info(idx_path) if idx_path else None
        folder = lib["folder"] or (info[2] if info else None)
        if not folder or not os.path.isdir(folder):
            continue
        files = listing(folder, deadline)
        listings[lib["name"]] = files
        idx_name = os.path.basename(lib["index"])
        if info is None:
            if files:
                trigger = True
                parts.append(f"{lib['name']}: no index ({idx_name}) for {plural(len(files), 'file')}")
            continue
        indexed, built, _ = info
        if built is None:
            try:
                built = dt.date.fromtimestamp(os.path.getmtime(idx_path))
            except OSError:
                built = None
        unindexed = sorted(n for n in files if n not in indexed)
        gone = sorted(n for n in indexed if n not in files)
        cutoff = (dt.datetime.combine(built + dt.timedelta(days=1), dt.time()).timestamp() if built else None)
        changed = [n for n, t in files.items() if cutoff and t >= cutoff]
        age = (now.date() - built).days if built else None
        bits = []
        if len(unindexed) > unindexed_max:
            trigger = True
            bits.append(f"{plural(len(unindexed), 'file')} not in {idx_name}")
        if gone:
            trigger = True
            bits.append(f"{plural(len(gone), 'indexed file')} no longer in the folder")
        if age is not None and age > max_days and changed:
            trigger = True
            bits.append(f"index {age} days old with {plural(len(changed), 'file')} changed since")
        if bits:
            parts.append(f"{lib['name']}: " + ", ".join(bits))
            if unindexed:
                details.append(f"{lib['name']} not indexed: " + "; ".join(unindexed[:5])
                               + (f" (+{len(unindexed) - 5} more)" if len(unindexed) > 5 else ""))
            if gone:
                details.append(f"{lib['name']} gone: " + "; ".join(gone[:5])
                               + (f" (+{len(gone) - 5} more)" if len(gone) > 5 else ""))
    if not trigger:
        return None, listings, root
    reason = "; ".join(parts)
    extra = (" " + " ".join(d + "." for d in details)) if details else ""
    return {"check": "index", "reason": reason + ": ask the librarian to reindex",
            "title": "Ask the librarian to reindex the published libraries, out of date since {since} "
                     "(kit-alerts library)",
            "detail": f"{{today}}: {reason}.{extra} If many indexed files are gone, check the sync before "
                      "marking anything withdrawn. Kit clears its alert when the indexes match the folders.",
            "recovered": "Recovered {today}: the published indexes match their folders again; check this off "
                         "when you're satisfied."}, listings, root


def check_sync(cfg, now, deadline, listings, root):
    if not root or "cloudstorage" not in root.replace("\\", "/").lower() or not os.path.isdir(root):
        return None
    if not listings or not any(listings.values()):
        return None
    days = cfg.number("LIBRARY_SYNC_MAX_DAYS", 14) if cfg else 14
    if days <= 0:
        return None
    cloud = max(t for t in (newest(f) for f in listings.values()) if t)
    kit_files = listing(root, deadline, limit=5000)
    kit_new = newest(kit_files)
    horizon = now.timestamp() - days * 86400
    if cloud >= horizon or not kit_new or kit_new < horizon:
        return None
    quiet = int((now.timestamp() - cloud) // 86400)
    wrote = max(int((now.timestamp() - kit_new) // 86400), 0)
    when = "today" if wrote == 0 else f"{wrote} day{'s' if wrote != 1 else ''} ago"
    return {"check": "sync", "inferred": True,
            "reason": f"no file in the published folders has changed in {quiet} days (limit {days:g}) while Kit "
                      f"wrote to the library {when}; the cloud sync may be stalled (inferred)"}


def problems(kit, cfg=None, now=None, deadline=None):
    """{key: problem} for run_alerts.track_monitor, or None when the check ran out of time (open alerts
    are then left as they are)."""
    now = now or dt.datetime.now()
    try:
        idx, listings, root = check_index(kit, cfg, now, deadline)
        out = {}
        if idx:
            out["library:index"] = idx
        sync = check_sync(cfg, now, deadline, listings, root)
        if sync:
            out["library:sync"] = sync
        return out
    except OutOfTime as ex:
        print(f"run_alerts: library check not finished in time (listing {ex}); open alerts left as they were",
              file=sys.stderr)
        return None


def main(argv):
    ap = argparse.ArgumentParser(prog="monitor_library.py")
    ap.add_argument("--kit", default=os.environ.get("KIT_DIR", os.path.expanduser("~/Claude/Agents/kit")))
    a = ap.parse_args(argv)
    res = problems(a.kit, None, deadline=time.monotonic() + 20)
    for key, p in sorted((res or {}).items()):
        print(f"{key}: {p['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

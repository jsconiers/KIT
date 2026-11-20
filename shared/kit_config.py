"""kit_config: snapshots of Kit's configuration, and restoring one (`kit-config`, and the settings page's Snapshots).

What a snapshot holds (Kit's configuration only, never your notes, the queue, or memory):
  - the run config, .install/shared/morning/config
  - the JSON configs in memory/context/ (connector-guard.json, retention.json, and the rest), models.json,
    docs-build.json, and the setup wizard's state (.install/setup-wizard.json)
  - the setup files in memory/context/ that Kit ships (the ones kit-settings and the wizard edit)
  - Kit's own permission rules in ~/.claude/settings.json (allow, ask, deny): the rules Kit's installer adds,
    never the owner's own; a restore puts them back only with --include-permissions

Never a credential. A run config line whose key names a credential (a token, secret, or password, not the name of
one) or whose value looks like one is left out, and so is a JSON key that does; a restore keeps the file's current
line or value for each one left out. A setup file with anything credential-shaped in it is skipped whole, and so is
any file whose name says it holds secrets (.env, *.pem, *.key, credentials). The manifest says what was left out.

Where: .install/snapshots/<id>/ (id is YYYYMMDD-HHMMSS), with manifest.json (a SHA-256 per file) and files/; the
folder is 0700 and each file 0600 (on Windows the folder's ACLs, which the installer sets, apply instead).

A snapshot whose files match the latest one isn't taken again (the latest id is returned). A restore always takes a
snapshot of the current state first, so it can itself be undone, and shows the change before it writes. Writes go
through a temporary file and a rename; each changed file is committed to Kit's private repo where it's tracked, as
the settings page does. Snapshots past the keep count (SNAPSHOT_KEEP in the run config, default 30) are pruned,
oldest first, after each new one. Standard library only.
"""
import datetime as dt
import difflib
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import kit_settings as ks  # noqa: E402

SNAP_REL = ".install/snapshots"
ID_RE = re.compile(r"^\d{8}-\d{6}(?:-\d{1,3})?$")
PERMS = "~/.claude/settings.json (Kit's rules)"
PERM_LISTS = ("allow", "ask", "deny")
DEFAULT_KEEP = 30
OMIT = "#kit-config-omitted "
# A free-text line (a comment, prose) that looks credential-shaped is left out on its own, not the whole file;
# a restore takes the current file's line at the same place back if it still looks that way, else drops it.
OMIT_LINE = "#kit-config-omitted-line"
SECRET_FILE = re.compile(r"(^\.env($|\.)|\.env$|\.pem$|\.key$|\.p12$|\.pfx$|credential|secret|id_rsa|id_ed25519)", re.I)


class Error(Exception):
    pass


# ---------------------------------------------------------------------------------------------------------------
# What's covered.

def kit_dir(kit=None):
    return ks.kit_dir(kit)


def snap_root(kit):
    return kit_dir(kit) / SNAP_REL


def claude_settings_path():
    p = os.environ.get("KIT_CLAUDE_SETTINGS")
    return pathlib.Path(p) if p else pathlib.Path(os.path.expanduser("~")) / ".claude" / "settings.json"


def covered(kit):
    """[(rel, kind)] for the files a snapshot covers that exist now; kind is shell, json, or text."""
    kit = kit_dir(kit)
    out = []
    if (kit / ks.CONFIG_REL).is_file():
        out.append((ks.CONFIG_REL, "shell"))
    ctx = kit / "memory/context"
    if ctx.is_dir():
        out += [(p.relative_to(kit).as_posix(), "json") for p in sorted(ctx.glob("*.json")) if p.is_file()]
        shipped = ks.shipped_context(kit)
        names = {p.name for p in shipped.glob("*.md")} if shipped else set()
        out += [(p.relative_to(kit).as_posix(), "text") for p in sorted(ctx.glob("*.md")) if p.name in names]
    for rel in ("models.json", "docs-build.json", ".install/setup-wizard.json"):
        if (kit / rel).is_file():
            out.append((rel, "json"))
    return out


def kit_rules(kit):
    """The permission rules Kit manages: the installer's lists, plus what its manifest says it added."""
    rules = set()
    try:
        import kit_setup
        for name in ("ALLOW", "ASK", "DENY"):
            rules |= {r for r in getattr(kit_setup, name, []) if isinstance(r, str)}
    except Exception:  # noqa: BLE001  (kit_setup ships next to this file; a broken import mustn't stop a snapshot)
        pass
    try:
        m = json.loads((kit_dir(kit) / ".install/manifest.json").read_text(encoding="utf-8-sig"))
        for lst in (m.get("settings", {}).get("added", {}) or {}).values():
            rules |= {r for r in lst if isinstance(r, str)}
    except (OSError, ValueError, AttributeError):
        pass
    return rules


def current_permissions(kit):
    """{list: [Kit's rules present in settings.json, in its order]}, or None when there's no settings file."""
    p = claude_settings_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    perms = data.get("permissions") if isinstance(data, dict) else None
    if not isinstance(perms, dict):
        return {k: [] for k in PERM_LISTS}
    mine = kit_rules(kit)
    return {k: [r for r in (perms.get(k) or []) if isinstance(r, str) and r in mine] for k in PERM_LISTS}


# ---------------------------------------------------------------------------------------------------------------
# Leaving credentials out.

def _secret_line(key, value):
    return bool(value) and (ks.secret_key(key) or ks.looks_secret(value))


def sanitize_shell(text):
    """(text, [keys left out])."""
    out, omitted = [], []
    for line in text.splitlines(keepends=True):
        m = ks.CONFIG_LINE.match(line.rstrip("\r\n"))
        if m and _secret_line(m.group(1), ks._unquote(m.group(2))):
            omitted.append(m.group(1))
            out.append(OMIT + m.group(1) + line[len(line.rstrip("\r\n")):])
        elif not m and ks.looks_secret(line):
            omitted.append(OMIT_LINE)
            out.append(OMIT_LINE + line[len(line.rstrip("\r\n")):])
        else:
            out.append(line)
    return "".join(out), omitted


def _walk_json(obj, path, omitted):
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            if isinstance(v, str) and v and ((isinstance(k, str) and ks.secret_key(k)) or ks.looks_secret(v)):
                omitted.append(path + [k])
                continue
            new[k] = _walk_json(v, path + [k], omitted)
        return new
    if isinstance(obj, list):
        for v in obj:
            if isinstance(v, str) and ks.looks_secret(v):
                raise Error("a list holds something credential-shaped")
        return [_walk_json(v, path + [i], omitted) for i, v in enumerate(obj)]
    return obj


def sanitize_json(text):
    """(text, [paths left out]). The file's own bytes when nothing is left out."""
    data = json.loads(text)
    omitted = []
    clean = _walk_json(data, [], omitted)
    if not omitted:
        return text, []
    return json.dumps(clean, indent=2, ensure_ascii=False) + "\n", omitted


def sanitized(kit, rel, kind):
    """(text or None, omitted, skip reason or "")."""
    name = pathlib.PurePosixPath(rel).name
    if SECRET_FILE.search(name):
        return None, [], "its name says it holds secrets"
    try:
        text = (kit_dir(kit) / rel).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as ex:
        return None, [], f"couldn't be read ({ex.__class__.__name__})"
    try:
        if kind == "shell":
            t, om = sanitize_shell(text)
            return t, om, ""
        if kind == "json":
            t, om = sanitize_json(text)
            return t, om, ""
    except ValueError:
        return None, [], "not valid JSON"
    except Error as ex:
        return None, [], str(ex)
    return sanitize_text(text)


def sanitize_text(text):
    """(text, [markers], ""): each credential-shaped line replaced by a marker, the rest kept."""
    out, omitted = [], []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if ks.looks_secret(body):
            omitted.append(OMIT_LINE)
            out.append(OMIT_LINE + line[len(body):])
        else:
            out.append(line)
    return "".join(out), omitted, ""


def _merge_lines(snap_text, cur_text):
    """Put back each left-out line from the current file's same line, when that one still looks credential-shaped."""
    if OMIT_LINE not in snap_text:
        return snap_text
    cur = cur_text.splitlines()
    out = []
    for i, line in enumerate(snap_text.splitlines(keepends=True)):
        body = line.rstrip("\r\n")
        if body == OMIT_LINE:
            if i < len(cur) and ks.looks_secret(cur[i]):
                out.append(cur[i] + line[len(body):])
            continue
        out.append(line)
    return "".join(out)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def current_state(kit, permissions=True):
    """{"files": {rel: {"text", "kind", "omitted"}}, "skipped": {rel: why}, "permissions": {...} or None}."""
    files, skipped = {}, {}
    for rel, kind in covered(kit):
        t, om, why = sanitized(kit, rel, kind)
        if why:
            skipped[rel] = why
        else:
            files[rel] = {"text": t, "kind": kind, "omitted": om}
    return {"files": files, "skipped": skipped, "permissions": current_permissions(kit) if permissions else None}


# ---------------------------------------------------------------------------------------------------------------
# Snapshots on disk.

def _private_dir(p):
    p.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(p, 0o700)


def _write_private(path, text):
    _private_dir(path.parent)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(text.encode("utf-8"))
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(str(tmp), str(path))


def ids(kit):
    root = snap_root(kit)
    if not root.is_dir():
        return []
    return sorted((p.name for p in root.iterdir() if p.is_dir() and ID_RE.match(p.name)
                   and (p / "manifest.json").is_file()), key=_id_key)


def _id_key(i):
    parts = i.split("-")
    return (parts[0], parts[1], int(parts[2]) if len(parts) > 2 else 0)


def check_id(kit, sid):
    if not isinstance(sid, str) or not ID_RE.match(sid) or sid not in ids(kit):
        raise Error(f"no snapshot {sid!r}; kit-config list shows them")
    return sid


def manifest(kit, sid):
    check_id(kit, sid)
    return json.loads((snap_root(kit) / sid / "manifest.json").read_text(encoding="utf-8"))


def snap_file(kit, sid, rel):
    return (snap_root(kit) / sid / "files" / pathlib.PurePosixPath(rel)).read_bytes().decode("utf-8")


def load(kit, sid):
    """A snapshot in current_state()'s shape."""
    m = manifest(kit, sid)
    files = {rel: {"text": snap_file(kit, sid, rel), "kind": f["kind"], "omitted": f.get("omitted", [])}
             for rel, f in m["files"].items()}
    return {"files": files, "skipped": m.get("skipped", {}), "permissions": m.get("permissions")}


def _fingerprint(state):
    return {"files": {r: sha(f["text"]) for r, f in state["files"].items()}, "permissions": state["permissions"]}


def keep_count(kit):
    for k, v, _ in ks.config_entries(kit_dir(kit)):
        if k == "SNAPSHOT_KEEP" and re.fullmatch(r"\d{1,4}", v or "") and int(v) >= 1:
            return int(v)
    return DEFAULT_KEEP


def version(kit):
    try:
        return json.loads((kit_dir(kit) / ".install/VERSION.json").read_text(encoding="utf-8")).get("version", "")
    except (OSError, ValueError, AttributeError):
        return ""


def snapshot(kit=None, note="", force=False, now=None, prune_after=True):
    """Take a snapshot. Returns {"id", "new": bool, "files", "skipped", "omitted", "pruned"}."""
    kit = kit_dir(kit)
    note = " ".join(str(note or "").split())[:200]
    if ks.looks_secret(note):
        raise Error("the note looks like a credential")
    state = current_state(kit)
    existing = ids(kit)
    if existing and not force:
        last = existing[-1]
        try:
            if _fingerprint(load(kit, last)) == _fingerprint(state):
                return {"id": last, "new": False, "files": len(state["files"]), "skipped": state["skipped"],
                        "omitted": {}, "pruned": []}
        except (OSError, ValueError, Error, KeyError):
            pass
    now = now or dt.datetime.now()
    sid = f"{now:%Y%m%d-%H%M%S}"
    n = 1
    while (snap_root(kit) / sid).exists():
        sid = f"{now:%Y%m%d-%H%M%S}-{n}"
        n += 1
    _private_dir(snap_root(kit))
    d = snap_root(kit) / sid
    _private_dir(d)
    man = {"id": sid, "created": now.isoformat(timespec="seconds"), "note": note, "kit_version": version(kit),
           "files": {}, "skipped": state["skipped"], "permissions": state["permissions"]}
    for rel, f in state["files"].items():
        _write_private(d / "files" / pathlib.PurePosixPath(rel), f["text"])
        man["files"][rel] = {"kind": f["kind"], "sha256": sha(f["text"]), "size": len(f["text"].encode("utf-8")),
                             "omitted": f["omitted"]}
    _write_private(d / "manifest.json", json.dumps(man, indent=2, ensure_ascii=False) + "\n")
    pruned = prune(kit, keep_count(kit)) if prune_after else []
    omitted = {r: f["omitted"] for r, f in state["files"].items() if f["omitted"]}
    return {"id": sid, "new": True, "files": len(state["files"]), "skipped": state["skipped"], "omitted": omitted,
            "pruned": pruned}


def prune(kit=None, keep=DEFAULT_KEEP):
    """Delete the oldest snapshots past `keep`; returns their ids. Only folders named like a snapshot, inside
    .install/snapshots, are ever removed."""
    kit = kit_dir(kit)
    keep = max(1, int(keep))
    root = snap_root(kit).resolve()
    gone = []
    for sid in ids(kit)[:-keep]:
        p = (root / sid).resolve()
        if p.parent != root or not ID_RE.match(p.name) or p.is_symlink():
            continue
        shutil.rmtree(str(p))
        gone.append(sid)
    return gone


def listing(kit=None):
    """[{id, created, note, files, skipped, kit_version}] newest first."""
    out = []
    for sid in reversed(ids(kit)):
        try:
            m = manifest(kit, sid)
        except (OSError, ValueError, Error):
            continue
        out.append({"id": sid, "created": m.get("created", ""), "note": m.get("note", ""),
                    "files": len(m.get("files", {})), "skipped": len(m.get("skipped", {})),
                    "kit_version": m.get("kit_version", ""), "permissions": m.get("permissions") is not None})
    return out


# ---------------------------------------------------------------------------------------------------------------
# Diffs, and restoring.

def _udiff(a, b, label_a, label_b):
    return ks.mask_text("".join(difflib.unified_diff(a.splitlines(keepends=True), b.splitlines(keepends=True),
                                                     label_a, label_b, n=1)))


def _perm_text(p):
    if p is None:
        return ""
    return "".join(f"{k}: {r}\n" for k in PERM_LISTS for r in (p.get(k) or []))


def diff(kit, a, b="current"):
    """Unified diffs from snapshot a to snapshot b (or the current state), file by file. Masked."""
    sa = load(kit, check_id(kit, a))
    sb = current_state(kit) if b in (None, "current") else load(kit, check_id(kit, b))
    lb = "current" if b in (None, "current") else b
    out = []
    for rel in sorted(set(sa["files"]) | set(sb["files"])):
        ta = sa["files"].get(rel, {}).get("text", "")
        tb = sb["files"].get(rel, {}).get("text", "")
        if ta != tb:
            out.append(_udiff(ta, tb, f"{a}/{rel}", f"{lb}/{rel}")
                       or f"--- {a}/{rel}\n+++ {lb}/{rel}\n(only line endings differ)\n")
    pa, pb = _perm_text(sa["permissions"]), _perm_text(sb["permissions"])
    if pa != pb and sa["permissions"] is not None and sb["permissions"] is not None:
        out.append(_udiff(pa, pb, f"{a}/{PERMS}", f"{lb}/{PERMS}"))
    return "".join(out)


def _merge_shell(snap_text, cur_text):
    """The snapshot's config with each left-out credential line taken from the current file."""
    cur = {}
    for line in cur_text.splitlines():
        m = ks.CONFIG_LINE.match(line)
        if m:
            cur[m.group(1)] = line
    out, seen = [], set()
    for line in snap_text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if body == OMIT_LINE:
            out.append(line)
            continue
        if body.startswith(OMIT):
            key = body[len(OMIT):].strip()
            seen.add(key)
            if key in cur:
                out.append(cur[key] + line[len(body):])
            continue
        m = ks.CONFIG_LINE.match(body)
        if m:
            seen.add(m.group(1))
        out.append(line)
    nl = "\r\n" if "\r\n" in snap_text else "\n"
    extra = [v for k, v in cur.items() if k not in seen and _secret_line(k, ks._unquote(ks.CONFIG_LINE.match(v).group(2)))]
    if extra:
        if out and not out[-1].endswith(("\n", "\r")):
            out[-1] += nl
        out += [x + nl for x in extra]
    return "".join(out)


def _get(obj, path):
    for k in path:
        obj = obj[k]
    return obj


def _merge_json(snap_text, omitted, cur_text):
    if not omitted:
        return snap_text
    data = json.loads(snap_text)
    try:
        cur = json.loads(cur_text)
    except ValueError:
        cur = None
    for path in omitted:
        try:
            v = _get(cur, path)
            parent = _get(data, path[:-1])
            if isinstance(parent, dict):
                parent[path[-1]] = v
        except (KeyError, IndexError, TypeError):
            pass
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _same_json(a, b):
    """True when two JSON texts hold the same data (a restore doesn't rewrite a file only to reformat it)."""
    try:
        return json.loads(a) == json.loads(b)
    except ValueError:
        return False


def _read(path):
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def plan_restore(kit, sid, include_permissions=False):
    """{"changes": [(rel, path, old or None, new)], "permissions": (old data, new data) or None, "diff",
    "unchanged": n, "left": [rels now covered but not in the snapshot]}."""
    kit = kit_dir(kit)
    snap = load(kit, check_id(kit, sid))
    changes, unchanged, parts = [], 0, []
    for rel, f in sorted(snap["files"].items()):
        path = kit / pathlib.PurePosixPath(rel)
        cur = _read(path)
        if f["kind"] == "shell":
            new = _merge_lines(_merge_shell(f["text"], cur or ""), cur or "")
        elif f["kind"] == "json":
            new = _merge_json(f["text"], f["omitted"], cur or "")
        else:
            new = _merge_lines(f["text"], cur or "")
        if cur == new or (f["kind"] == "json" and cur is not None and _same_json(cur, new)):
            unchanged += 1
            continue
        changes.append((rel, path, cur, new))
        parts.append(_udiff(cur or "", new, f"current/{rel}", f"{sid}/{rel}") or f"--- {rel}\n(line endings only)\n")
    left = sorted(r for r, _ in covered(kit) if r not in snap["files"])
    perm = None
    if include_permissions and snap["permissions"] is not None:
        p = claude_settings_path()
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            raise Error(f"{p} couldn't be read as JSON; nothing was changed")
        if not isinstance(data, dict):
            raise Error(f"{p} doesn't hold a JSON object; nothing was changed")
        mine = kit_rules(kit) | {r for lst in snap["permissions"].values() for r in lst}
        new = json.loads(json.dumps(data))
        perms = new.setdefault("permissions", {})
        for k in PERM_LISTS:
            want = list(snap["permissions"].get(k) or [])
            cur = [r for r in (perms.get(k) or []) if isinstance(r, str)]
            merged = [r for r in cur if r not in mine or r in want] + [r for r in want if r not in cur]
            if merged or k in perms:
                perms[k] = merged
        if new != data:
            perm = (data, new)
            parts.append(_udiff(_perm_text(current_permissions(kit)),
                                _perm_text({k: [r for r in perms.get(k, []) if r in mine] for k in PERM_LISTS}),
                                f"current/{PERMS}", f"{sid}/{PERMS}"))
    elif snap["permissions"] is not None and _perm_text(snap["permissions"]) != _perm_text(current_permissions(kit)):
        parts.append(f"(Kit's permission rules in ~/.claude/settings.json differ from {sid}; they are restored only "
                     "with --include-permissions)\n")
    return {"changes": changes, "permissions": perm, "diff": "".join(parts), "unchanged": unchanged, "left": left}


def _log(kit, line):
    p = kit_dir(kit) / ".install/logs/kit-config.log"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {line}\n")
    except OSError:
        pass


def restore(kit, sid, include_permissions=False, commit=True):
    """Restore snapshot sid. Takes a snapshot of the current state first. Returns a dict with ok, message, before,
    written, diff."""
    kit = kit_dir(kit)
    plan = plan_restore(kit, sid, include_permissions)
    if not plan["changes"] and not plan["permissions"]:
        return {"ok": True, "message": f"Nothing to restore: the configuration already matches {sid}.",
                "before": None, "written": [], "diff": plan["diff"]}
    before = snapshot(kit, note=f"before restoring {sid}", prune_after=False)
    written = []
    for rel, path, old, new in plan["changes"]:
        mode = (path.stat().st_mode & 0o777) if path.exists() else 0o600
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".kit-config.tmp")
        tmp.write_bytes(new.encode("utf-8"))
        if os.name != "nt":
            os.chmod(tmp, mode)
        os.replace(str(tmp), str(path))
        written.append(rel)
    if plan["permissions"]:
        p = claude_settings_path()
        tmp = p.with_name(p.name + ".kit-config.tmp")
        tmp.write_text(json.dumps(plan["permissions"][1], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if os.name != "nt":
            os.chmod(tmp, (p.stat().st_mode & 0o777) if p.exists() else 0o600)
        os.replace(str(tmp), str(p))
        written.append(PERMS)
    commits = 0
    if commit:
        for rel in written:
            if rel != PERMS and ks.git_commit(kit, kit / rel, f"Settings: restored {rel} from snapshot {sid}")[0]:
                commits += 1
    _log(kit, f"restored {sid}: {', '.join(written)} (undo: kit-config restore {before['id']})")
    return {"ok": True, "before": before["id"], "written": written, "diff": plan["diff"],
            "message": (f"Restored {len(written)} file(s) from {sid}. The state before is snapshot {before['id']}: "
                        f"kit-config restore {before['id']} undoes this."
                        + (f" {commits} committed to Kit's private repo." if commits else ""))}

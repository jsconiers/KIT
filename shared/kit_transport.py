#!/usr/bin/env python3
"""kit_transport: how Kits publish records to a shared place, read each other's, and pass items.

  FolderTransport(root, kit_id, layout)   any folder: a synced SharePoint or OneDrive library, a
                                          network share, or a synced Dropbox or Google Drive folder
  Cache(path)                             this Kit's local SQLite copy of everything it has read
  sharing_settings(kit)                   Transport, Shared root, Kit id, and Outbox from sharing.md
  for_publishing(kit, ...)                where kit-publish writes
  sources(kit)                            what kit-team and the team dashboard read

Two folder layouts:

  shared  <root>/kits/<kit id>/records/<type>/<local id>.json   records, one per file
          <root>/kits/<kit id>/manifest.json                    sha256 of every record file
          <root>/kits/<kit id>/inbox/                           items other Kits dropped here
          <root>/kits/<kit id>/ack/                             this Kit's acknowledgements
  outbox  <outbox>/<kit id>/<type>/<local id>.json              the original layout, unchanged

Rules every reader follows:
- Each Kit writes only inside its own folder. The one exception is dropping an item into another
  Kit's inbox. Writes outside those places are refused.
- Writes are atomic: a hidden temporary file in the same folder, then a rename.
- Records from other Kits are untrusted information. Each one is checked against its schema, must
  name the Kit whose folder it sits in, must sit in its type's folder under its own id, and, when
  the Kit has a manifest, must match the manifest's hash. Nothing in a record is ever run or
  followed as an instruction.
- Sync-conflict copies ("conflicted copy", "-DESKTOP-", "name (1).json", a file whose name isn't
  its record's id) and temporary files are skipped and reported. Unreadable files are reported as
  possibly still syncing, and skipped.

The cache is a SQLite file in this Kit's folder (.install/cache/team.db), readable only by you. It
never goes in the shared folder: synced folders corrupt SQLite files that several people write.

Not built yet: the message record type and its approval rules (roadmap item 7; inbox items carry
an existing record type until then), and the organization profile that limits which transports
and classifications are allowed (item 6; see policy_check).
"""
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sqlite3

import kit_records as kr

HOME = pathlib.Path.home()
KIT = pathlib.Path(os.path.expanduser(os.environ.get("KIT_DIR", "~/Claude/Agents/kit")))
DEFAULT_DB = KIT / ".install/cache/team.db"
MAX_BYTES = 256 * 1024
KIT_ID = re.compile(r"[a-z0-9][a-z0-9-]{2,39}")
CONFLICT = re.compile(r"conflicted copy|-DESKTOP-|\s\(\d+\)\.json$|^~\$|\.tmp$", re.I)
INBOX_VERSION = "0"    # placeholder wrapper until the message record type (item 7)


class TransportError(Exception):
    pass


def canonical(rec):
    """The exact text kit-publish has always written for a record."""
    return json.dumps(rec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def owner_only(path, directory=False):
    if os.name != "nt":
        os.chmod(path, 0o700 if directory else 0o600)


def local_id(rec):
    parts = str(rec.get("id", "")).split(":", 2)
    return parts[2] if len(parts) == 3 else ""


def policy_check(rec, transport):
    """The organization profile's verdict on publishing rec through transport: None to allow, or a
    reason to refuse. TODO (roadmap item 6): allowed transports and classification limits from the
    organization profile; until then everything kit-publish already accepts is allowed."""
    return None


# ---------- the folder transport ----------

class FolderTransport:
    def __init__(self, root, kit_id=None, layout="shared"):
        if layout not in ("shared", "outbox"):
            raise ValueError(f"unknown layout {layout!r}")
        self.root = pathlib.Path(root).expanduser()
        self.kit_id = kit_id
        self.layout = layout
        self.origin = f"{layout}:{self.root}"

    def __repr__(self):
        return f"FolderTransport({str(self.root)!r}, {self.kit_id!r}, {self.layout!r})"

    # where things live
    def kit_dir(self, kit):
        return self.root / "kits" / kit if self.layout == "shared" else self.root / kit

    def records_dir(self, kit):
        return self.kit_dir(kit) / "records" if self.layout == "shared" else self.kit_dir(kit)

    def manifest_path(self, kit):
        return self.kit_dir(kit) / "manifest.json" if self.layout == "shared" else None

    def inbox_dir(self, kit):
        self._need_shared("inboxes")
        return self.kit_dir(kit) / "inbox"

    def ack_dir(self, kit):
        self._need_shared("acknowledgements")
        return self.kit_dir(kit) / "ack"

    def record_path(self, typ, local):
        self._need_kit()
        return self.records_dir(self.kit_id) / typ / f"{local}.json"

    def _need_shared(self, what):
        if self.layout != "shared":
            raise TransportError(f"{what} need the shared folder layout (set Shared root in sharing.md)")

    def _need_kit(self):
        if not self.kit_id or not KIT_ID.fullmatch(self.kit_id):
            raise TransportError(f"Kit id {self.kit_id!r} isn't set or isn't 3-40 lowercase letters, "
                                 "digits, or hyphens")

    def _inside(self, path, folder):
        try:
            path.resolve().relative_to(folder.resolve())
            return True
        except ValueError:
            return False

    def _guard_own(self, path):
        self._need_kit()
        if not self._inside(path, self.kit_dir(self.kit_id)):
            raise TransportError(f"refusing to write outside this Kit's folder: {path}")

    # writing (this Kit only)
    def publish(self, rec):
        """Write one record into this Kit's folder. Returns (path, written); unchanged text isn't
        rewritten."""
        self._need_kit()
        if rec.get("kit_id") != self.kit_id:
            raise TransportError(f"record {rec.get('id')!r} belongs to {rec.get('kit_id')!r}, not this Kit")
        problems = kr.validate(rec, kr.load_schemas())
        if problems:
            raise TransportError(f"record {rec.get('id')!r} isn't valid: " + "; ".join(problems[:3]))
        why = policy_check(rec, self)
        if why:
            raise TransportError(f"organization profile refuses {rec.get('id')!r}: {why}")
        path = self.record_path(rec["schema"], local_id(rec))
        self._guard_own(path)
        text = canonical(rec)
        if path.exists() and path.read_text(encoding="utf-8", errors="ignore") == text:
            return path, False
        atomic_write(path, text)
        return path, True

    def read_path(self, path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def own_record_files(self):
        self._need_kit()
        d = self.records_dir(self.kit_id)
        return {p for p in d.rglob("*.json") if not p.name.startswith(".")} if d.is_dir() else set()

    def remove(self, path):
        self._guard_own(path)
        path.unlink()
        if not any(path.parent.iterdir()):
            path.parent.rmdir()

    def finish(self):
        """Rewrite this Kit's manifest when its records changed (shared layout only)."""
        if self.layout != "shared":
            return False
        self._need_kit()
        base = self.kit_dir(self.kit_id)
        files = {p.relative_to(base).as_posix(): sha256(p.read_bytes()) for p in sorted(self.own_record_files())}
        mpath = self.manifest_path(self.kit_id)
        old = self.read_path(mpath) if mpath.exists() else None
        if old and old.get("files") == files:
            return False
        self._guard_own(mpath)
        atomic_write(mpath, json.dumps({"kit_id": self.kit_id, "updated": kr.now_iso(), "files": files},
                                       indent=2, sort_keys=True) + "\n")
        return True

    # reading (every Kit)
    def kits(self):
        base = self.root / "kits" if self.layout == "shared" else self.root
        if not base.is_dir():
            return []
        return sorted(d.name for d in base.iterdir() if d.is_dir() and KIT_ID.fullmatch(d.name))

    def _manifest(self, kit, warnings):
        mpath = self.manifest_path(kit)
        if mpath is None:
            return None
        if not mpath.exists():
            warnings.append(("manifest", kit, "no manifest yet: its records are shown unverified"))
            return None
        m = self.read_path(mpath)
        if not isinstance(m, dict) or not isinstance(m.get("files"), dict) or m.get("kit_id") != kit:
            warnings.append(("manifest", kit, "manifest unreadable or not this Kit's (still syncing?): "
                                              "records shown unverified"))
            return None
        return m["files"]

    def scan(self, schemas, kit_id=None, type=None, since=None):
        """Every acceptable record, as (record, info) pairs, plus warnings as (kind, where, message).
        info holds ref (kit/relative path), sha256, and verified (matched a manifest)."""
        out, warnings = [], []
        since_dt = kr.parse_iso(since) if isinstance(since, str) else since
        for kit in self.kits():
            if kit_id and kit != kit_id:
                continue
            base, rdir = self.kit_dir(kit), self.records_dir(kit)
            manifest = self._manifest(kit, warnings)
            seen = set()
            for f in sorted(rdir.rglob("*.json")) if rdir.is_dir() else []:
                rel = f.relative_to(base).as_posix()
                where = f"{kit}/{rel}"
                if f.name.startswith("."):
                    continue                       # another Kit's write in progress
                if CONFLICT.search(f.name):
                    warnings.append(("conflict", where, "sync-conflict or temporary copy: skipped"))
                    continue
                seen.add(rel)
                try:
                    data = f.read_bytes()
                    if len(data) > MAX_BYTES:
                        raise ValueError("file too large")
                    rec = json.loads(data.decode("utf-8"))
                except (OSError, ValueError, UnicodeDecodeError) as ex:
                    warnings.append(("file", where, f"unreadable, maybe still syncing: {ex}"))
                    continue
                if not isinstance(rec, dict):
                    warnings.append(("rejected", where, "not a JSON object"))
                    continue
                ok, why = kr.accept(rec, schemas)
                if why:
                    warnings.append(("schema" if ok else "rejected", where, why))
                if not ok:
                    continue
                if rec.get("kit_id") != kit:
                    warnings.append(("rejected", where, f"names Kit {rec.get('kit_id')!r} but sits in {kit}'s folder"))
                    continue
                if f.parent.name != rec["schema"]:
                    warnings.append(("rejected", where, f"a {rec['schema']} record in the {f.parent.name} folder"))
                    continue
                if f.stem != local_id(rec):
                    warnings.append(("conflict", where, "file name isn't the record's id (a sync copy?): skipped"))
                    continue
                digest, verified = sha256(data), False
                if manifest is not None:
                    listed = manifest.get(rel)
                    if listed is None:
                        warnings.append(("unverified", where, "not in its Kit's manifest (still syncing, or "
                                                              "added outside that Kit): skipped"))
                        continue
                    if listed != digest:
                        warnings.append(("tampered", where, "doesn't match its Kit's manifest (changed outside "
                                                            "that Kit, or still syncing): skipped"))
                        continue
                    verified = True
                if type and rec["schema"] != type:
                    continue
                if since_dt and (kr.parse_iso(rec.get("updated", "")) or since_dt) < since_dt:
                    continue
                out.append((rec, {"ref": where, "sha256": digest, "verified": verified, "kit": kit}))
            for rel in sorted(set(manifest or {}) - seen):
                warnings.append(("syncing", f"{kit}/{rel}", "in the manifest but not here yet"))
        return out, warnings

    def list(self, schemas, kit_id=None, type=None, since=None):
        return [rec for rec, _ in self.scan(schemas, kit_id, type, since)[0]]

    def read(self, ref, schemas):
        """One record by ref (<kit>/<relative path>), checked like scan; (record or None, problem)."""
        kit, _, rel = ref.partition("/")
        for rec, info in self.scan(schemas, kit_id=kit)[0]:
            if info["ref"] == ref:
                return rec, ""
        return None, f"{ref}: not found, or not acceptable (see kit-team status)"

    # inboxes (shared layout only)
    def send(self, to_kit, rec, schemas):
        """Drop a copy of one of this Kit's records into another Kit's inbox. TODO (item 7): the
        message record type and the owner's approval to send replace this placeholder wrapper."""
        self._need_kit()
        if not KIT_ID.fullmatch(to_kit or ""):
            raise TransportError(f"no such Kit id {to_kit!r}")
        if rec.get("kit_id") != self.kit_id:
            raise TransportError("only this Kit's own records can be sent")
        problems = kr.validate(rec, schemas)
        if problems:
            raise TransportError("record isn't valid: " + "; ".join(problems[:3]))
        hits = kr.secret_hits(canonical(rec))
        if hits:
            raise TransportError(f"record looks like it holds a {', '.join(hits)}")
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = f"{self.kit_id}--{rec['schema']}--{local_id(rec)}--{stamp}.json"
        path = self.inbox_dir(to_kit) / name
        if not self._inside(path, self.inbox_dir(to_kit)):
            raise TransportError("refusing to write outside that Kit's inbox")
        atomic_write(path, json.dumps({"inbox_version": INBOX_VERSION, "from": self.kit_id, "to": to_kit,
                                       "sent": kr.now_iso(), "record": rec}, indent=2, sort_keys=True) + "\n")
        return path

    def inbox(self, schemas):
        """This Kit's inbox items, checked: (items, warnings). Items are information only."""
        self._need_kit()
        items, warnings = [], []
        d, acks = self.inbox_dir(self.kit_id), self.ack_dir(self.kit_id)
        for f in sorted(d.glob("*.json")) if d.is_dir() else []:
            if f.name.startswith("."):
                continue
            if CONFLICT.search(f.name):
                warnings.append(("conflict", f"inbox/{f.name}", "sync-conflict or temporary copy: skipped"))
                continue
            item = self.read_path(f) if f.stat().st_size <= MAX_BYTES else None
            sender = f.name.split("--", 1)[0]
            why = ""
            if not isinstance(item, dict) or item.get("inbox_version") != INBOX_VERSION:
                why = "unreadable or unknown format (still syncing?)"
            elif item.get("from") != sender or item.get("to") != self.kit_id:
                why = "sender or recipient doesn't match the file"
            elif not isinstance(item.get("record"), dict) or item["record"].get("kit_id") != sender:
                why = "carried record isn't the sender's"
            else:
                ok, msg = kr.accept(item["record"], schemas)
                why = "" if ok else msg
            if why:
                warnings.append(("rejected", f"inbox/{f.name}", why))
                continue
            ack = self.read_path(acks / f.name) if (acks / f.name).exists() else None
            items.append({"name": f.name, "from": sender, "sent": item.get("sent", ""), "record": item["record"],
                          "ack": (ack or {}).get("state", "")})
        return items, warnings

    def ack(self, name, state="seen"):
        """Acknowledge an inbox item. The acknowledgement goes in this Kit's own ack folder, where the
        sender can read it."""
        self._need_kit()
        if not (self.inbox_dir(self.kit_id) / name).exists():
            raise TransportError(f"no inbox item {name!r}")
        path = self.ack_dir(self.kit_id) / name
        self._guard_own(path)
        atomic_write(path, json.dumps({"ack_version": INBOX_VERSION, "by": self.kit_id, "item": name,
                                       "state": state, "at": kr.now_iso()}, indent=2, sort_keys=True) + "\n")
        return path

    def acks_from(self, to_kit):
        """Acknowledgements another Kit wrote for items this Kit sent it: {item name: state}."""
        self._need_kit()
        d = self.ack_dir(to_kit)
        out = {}
        for f in sorted(d.glob(f"{self.kit_id}--*.json")) if d.is_dir() else []:
            a = self.read_path(f)
            if isinstance(a, dict) and a.get("by") == to_kit and a.get("item") == f.name:
                out[f.name] = a.get("state", "")
        return out


# ---------- settings ----------

def _setting_lines(path):
    out = {}
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        return out
    for m in re.finditer(r"^- \*\*([^*]+?):\*\*\s*(.*)$", text, re.M):
        v = m.group(2).strip()
        b = re.match(r"`([^`]+)`", v)
        v = b.group(1) if b else re.split(r"\.(?:\s|$)", v, 1)[0].strip()
        out[m.group(1).strip().lower()] = v
    return out


def _unset(v):
    return not v or v.strip().lower() in ("not set", "none", "")


def sharing_settings(kit=KIT):
    """Transport settings: sharing.md first, then sharing.json next to it, then environment variables
    KIT_TRANSPORT and KIT_SHARED_ROOT, which win when set."""
    kit = pathlib.Path(kit)
    md = _setting_lines(kit / "memory/context/sharing.md")
    js = {}
    try:
        js = json.loads((kit / "memory/context/sharing.json").read_text())
    except (OSError, ValueError):
        pass
    pick = lambda key, jkey: md.get(key) if not _unset(md.get(key)) else (js.get(jkey) or "")  # noqa: E731
    transport = (os.environ.get("KIT_TRANSPORT") or pick("transport", "transport") or "folder").lower()
    root = os.environ.get("KIT_SHARED_ROOT") or pick("shared root", "shared_root")
    kid = (pick("kit id", "kit_id") or "").lower()
    outbox = pick("outbox", "outbox") or str(kit / "outbox")
    return {"transport": transport,
            "shared_root": pathlib.Path(os.path.expanduser(root)) if root else None,
            "kit_id": kid, "outbox": pathlib.Path(os.path.expanduser(outbox))}


def for_publishing(kit=KIT, kit_id=None, outbox=None, shared_root=None):
    """Where kit-publish writes: an explicit outbox, else the shared root when Transport is folder and
    Shared root is set, else the outbox from sharing.md (the original layout)."""
    s = sharing_settings(kit)
    kid = kit_id or s["kit_id"]
    if outbox:
        return FolderTransport(outbox, kid, "outbox")
    root = pathlib.Path(shared_root).expanduser() if shared_root else s["shared_root"]
    if root and s["transport"] == "folder":
        return FolderTransport(root, kid, "shared")
    if s["transport"] != "folder":
        raise TransportError(f"transport {s['transport']!r} isn't built yet; only folder is")
    return FolderTransport(s["outbox"], kid, "outbox")


def sources(kit=KIT):
    """What to read: the shared root when set, else this Kit's own outbox."""
    s = sharing_settings(kit)
    if s["shared_root"] and s["transport"] == "folder":
        return [FolderTransport(s["shared_root"], s["kit_id"], "shared")]
    return [FolderTransport(s["outbox"], s["kit_id"], "outbox")]


# ---------- the local cache ----------

class Cache:
    def __init__(self, path=DEFAULT_DB):
        self.path = pathlib.Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        owner_only(self.path.parent, directory=True)
        self.db = sqlite3.connect(str(self.path))
        owner_only(self.path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS records (
                id TEXT PRIMARY KEY, kit_id TEXT, type TEXT, project TEXT, classification TEXT,
                schema_version TEXT, created TEXT, updated TEXT, sha256 TEXT, origin TEXT, ref TEXT,
                verified INTEGER, fetched TEXT, json TEXT);
            CREATE INDEX IF NOT EXISTS records_type ON records(type);
            CREATE INDEX IF NOT EXISTS records_project ON records(project);
            CREATE TABLE IF NOT EXISTS warnings (kind TEXT, location TEXT, message TEXT, seen TEXT);
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        """)

    def close(self):
        self.db.close()

    def sync(self, transports, schemas):
        """Pull every acceptable record from the transports into the cache. Records that vanished from
        a Kit folder that was read are dropped; nothing else is. Returns counts."""
        counts = {"new": 0, "changed": 0, "unchanged": 0, "removed": 0, "warnings": 0}
        now, all_warnings = kr.now_iso(), []
        with self.db:
            for t in transports:
                got, warnings = t.scan(schemas)
                all_warnings += warnings
                seen = {}
                for rec, info in got:
                    prev = seen.get(rec["id"])
                    if prev and (kr.parse_iso(prev[0]["updated"]) or 0) >= (kr.parse_iso(rec["updated"]) or 0):
                        continue
                    seen[rec["id"]] = (rec, info)
                for rid, (rec, info) in seen.items():
                    row = self.db.execute("SELECT sha256 FROM records WHERE id = ?", (rid,)).fetchone()
                    state = "unchanged" if row and row[0] == info["sha256"] else "changed" if row else "new"
                    counts[state] += 1
                    self.db.execute(
                        "INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (rid, rec["kit_id"], rec["schema"], rec["project"], rec["classification"],
                         rec["schema_version"], rec["created"], rec["updated"], info["sha256"], t.origin,
                         info["ref"], int(info["verified"]), now, json.dumps(rec, sort_keys=True)))
                read_kits = t.kits()
                for (rid,) in self.db.execute(
                        f"SELECT id FROM records WHERE origin = ? AND kit_id IN ({','.join('?' * len(read_kits))})",
                        (t.origin, *read_kits)).fetchall() if read_kits else []:
                    if rid not in seen:
                        self.db.execute("DELETE FROM records WHERE id = ?", (rid,))
                        counts["removed"] += 1
            self.db.execute("DELETE FROM warnings")
            self.db.executemany("INSERT INTO warnings VALUES (?,?,?,?)", [(*w, now) for w in all_warnings])
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('last_sync', ?)", (now,))
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('sources', ?)",
                            (json.dumps([t.origin for t in transports]),))
        counts["warnings"] = len(all_warnings)
        return counts

    def records(self, type=None, project=None, kit=None, text=None):
        sql, args = "SELECT json FROM records WHERE 1=1", []
        for col, val in (("type", type), ("project", project), ("kit_id", kit)):
            if val:
                sql += f" AND {col} = ?"
                args.append(val)
        if text:
            sql += " AND json LIKE ?"
            args.append(f"%{text}%")
        return [json.loads(r[0]) for r in self.db.execute(sql + " ORDER BY updated DESC, id", args)]

    def warnings(self):
        return [tuple(r) for r in self.db.execute("SELECT kind, location, message FROM warnings")]

    def meta(self, key, default=""):
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def status(self):
        by = self.db.execute("SELECT kit_id, type, COUNT(*), SUM(verified) FROM records "
                             "GROUP BY kit_id, type ORDER BY kit_id, type").fetchall()
        return {"last_sync": self.meta("last_sync"), "sources": json.loads(self.meta("sources", "[]")),
                "counts": by, "warnings": len(self.warnings())}

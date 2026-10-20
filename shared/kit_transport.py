#!/usr/bin/env python3
"""kit_transport: how Kits publish records to a shared place, read each other's, and pass items.

  FolderTransport(root, kit_id, layout)   any folder: a synced SharePoint or OneDrive library, a
                                          network share, or a synced Dropbox or Google Drive folder
  Cache(path)                             this Kit's local SQLite copy of everything it has read
  sharing_settings(kit)                   Transport, Shared root, Kit id, and Outbox from sharing.md
  for_publishing(kit, ...)                where kit-publish writes
  sources(kit)                            what kit-team and the team dashboard read
  kit_sql_transport.SQLTransport          PostgreSQL, SQL Server, or MySQL (Transport: sql; MySQL tested)
  load_policy(kit), policy_check(rec, t)  the organization profile, and its verdict on a record

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

The organization profile (memory/context/sharing-policy.json; see policy_check) limits which
transports and shared roots records may leave by and how classified they may be; it applies to
publishing and to sending. Without the file, internal records may leave and confidential never do.

Messages (the message record type): kit-team send drafts one, the owner approves it, and the
sending Kit publishes it in its own records (so its manifest and hash chain cover it) and drops an
identical copy into each recipient's inbox. A recipient accepts an inbox message only when it
passes its schema, names the Kit whose name starts the file and is its sender, lists the recipient,
and matches the sender's manifest hash for that message, with the sender's hash chain intact.
Messages are information: nothing in one is ever run or followed. Expired messages move to an
archive in the local cache; the sender's files are never deleted. Older inbox items (the
inbox_version "0" wrapper) are still read.

Hash chain: each Kit's manifest records every add, change, and removal of a record file as a chained
entry (seq, op, path, sha256, prev, hash). A reader recomputes the chain and replays it; a removed,
reordered, or edited entry, or a file list that doesn't match the replay, breaks it, and that Kit's
records are skipped and reported. The cache remembers each Kit's last head, so a chain rewritten
from scratch (history replaced) is reported too.

Retention in the cache: kit-retention's legal holds and an optional "team_cache" rule in
retention.json (older_than_days) apply to cached team records. A purge moves records into a holding
table; it never deletes them, and records in a held project are never purged.
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
INBOX_VERSION = "0"    # the older inbox wrapper, still read
MESSAGE_FILE = re.compile(r"^([a-z0-9][a-z0-9-]{2,39})--message--([a-z0-9][a-z0-9._-]{0,95})\.json$")
GENESIS = "0" * 64


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


# ---------- the hash chain in each Kit's manifest ----------

def chain_hash(prev, seq, op, path, digest):
    return sha256(f"{prev}|{seq}|{op}|{path}|{digest}".encode("utf-8"))


def extend_chain(chain, old_files, new_files):
    """Append an entry for every record file added, changed, or removed since old_files."""
    chain = list(chain or [])
    prev = chain[-1]["hash"] if chain else GENESIS
    events = []
    for path in sorted(set(old_files) | set(new_files)):
        a, b = old_files.get(path), new_files.get(path)
        if a == b:
            continue
        events.append(("add" if a is None else "remove" if b is None else "change", path, b or ""))
    for op, path, digest in events:
        seq = len(chain) + 1
        h = chain_hash(prev, seq, op, path, digest)
        chain.append({"seq": seq, "op": op, "path": path, "sha256": digest, "prev": prev, "hash": h})
        prev = h
    return chain


def verify_chain(manifest):
    """Problems with a manifest's hash chain (empty when it's intact and matches the file list)."""
    chain = manifest.get("chain")
    if not isinstance(chain, list):
        return ["no chain"]
    prev, state = GENESIS, {}
    for i, e in enumerate(chain, 1):
        if not isinstance(e, dict):
            return [f"entry {i} isn't an object"]
        if e.get("seq") != i:
            return [f"entry {i} has seq {e.get('seq')!r} (entries removed or reordered)"]
        if e.get("prev") != prev:
            return [f"entry {i} doesn't follow entry {i - 1}"]
        if e.get("op") not in ("add", "change", "remove"):
            return [f"entry {i} has an unknown op"]
        if chain_hash(prev, i, e["op"], e.get("path", ""), e.get("sha256", "")) != e.get("hash"):
            return [f"entry {i} was edited (its hash doesn't match)"]
        if e["op"] == "remove":
            state.pop(e.get("path"), None)
        else:
            state[e.get("path")] = e.get("sha256")
        prev = e["hash"]
    if manifest.get("head", prev) != prev:
        return ["the head doesn't match the last entry"]
    if state != manifest.get("files"):
        return ["the file list doesn't match the chain (records changed outside the chain)"]
    return []


# ---------- the organization profile (sharing policy) ----------

LEVELS = {"public": 0, "internal": 1, "confidential": 2}
POLICY_FILE = "memory/context/sharing-policy.json"
DEFAULT_POLICY = {
    "allowed_transports": ["folder"],   # transports records may leave by
    "allowed_roots": [],                # shared roots must start with one of these (empty: any)
    "blocked_root_patterns": [],        # a shared root containing one of these is refused
    "max_classification": {"folder": "internal"},
    "allow_confidential": False,        # confidential records never leave unless this is true
    "outbox_counts_as_leaving": True,   # the outbox is copied to the team by hand, so it's checked too
}


def load_policy(kit=None):
    """The organization profile from memory/context/sharing-policy.json, merged over the defaults.
    A missing file means the defaults (confidential never leaves; internal may). A file that can't be
    read refuses everything, so a broken policy never opens the door."""
    kit = pathlib.Path(kit) if kit else KIT
    pol = dict(DEFAULT_POLICY)
    path = kit / POLICY_FILE
    if not path.exists():
        pol["_source"] = "defaults (no sharing-policy.json)"
        return pol
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as ex:
        return {"_broken": f"{path} can't be read ({ex}); nothing is shared until it's fixed",
                "_source": str(path)}
    pol.update({k: v for k, v in data.items() if not k.startswith("_")})
    pol["_source"] = str(path)
    return pol


def _norm(path):
    return os.path.normcase(str(pathlib.Path(os.path.expanduser(str(path))).resolve()))


def root_verdict(transport, policy=None):
    """Whether the organization profile allows this transport and shared root at all: None or a
    reason. Only the shared layout is a place records leave by."""
    pol = policy or load_policy()
    if pol.get("_broken"):
        return pol["_broken"]
    kind = getattr(transport, "kind", "folder")
    if kind not in [t.lower() for t in pol.get("allowed_transports") or []]:
        return f"transport {kind!r} isn't in allowed_transports ({pol['_source']})"
    if getattr(transport, "layout", "shared") != "shared" or kind != "folder":
        return None
    root = _norm(transport.root)
    for pat in pol.get("blocked_root_patterns") or []:
        if str(pat).lower() in str(transport.root).lower() or str(pat).lower() in root.lower():
            return f"shared root {transport.root} matches blocked pattern {pat!r} ({pol['_source']})"
    allowed = pol.get("allowed_roots") or []
    if allowed and not any(root == _norm(a) or root.startswith(_norm(a).rstrip(os.sep) + os.sep)
                           for a in allowed):
        return (f"shared root {transport.root} isn't under an allowed root "
                f"({', '.join(map(str, allowed))}; {pol['_source']})")
    return None


def policy_check(rec, transport, policy=None):
    """The organization profile's verdict on rec leaving through transport: None to allow, or a
    reason to refuse. Checks the transport and shared root, then the record's classification against
    the transport's ceiling; confidential records never leave unless allow_confidential is true."""
    pol = policy or load_policy()
    if pol.get("_broken"):
        return pol["_broken"]
    if getattr(transport, "layout", "shared") == "outbox" and not pol.get("outbox_counts_as_leaving", True):
        return None
    why = root_verdict(transport, pol)
    if why:
        return why
    cls = str(rec.get("classification") or "internal").lower()
    if cls not in LEVELS:
        return f"unknown classification {cls!r}"
    if cls == "confidential" and not pol.get("allow_confidential"):
        return "confidential records never leave this Kit (allow_confidential is false)"
    kind = getattr(transport, "kind", "folder")
    ceiling = str((pol.get("max_classification") or {}).get(kind, "internal")).lower()
    if LEVELS.get(cls, 9) > LEVELS.get(ceiling, 1):
        return f"classification {cls} is above this transport's limit ({ceiling})"
    return None


def describe_policy(policy=None):
    """One line for kit-team status and the health check."""
    pol = policy or load_policy()
    if pol.get("_broken"):
        return "BROKEN: " + pol["_broken"]
    bits = [f"transports {', '.join(pol.get('allowed_transports') or ['none'])}",
            f"up to {(pol.get('max_classification') or {}).get('folder', 'internal')}",
            "confidential allowed" if pol.get("allow_confidential") else "confidential never leaves"]
    if pol.get("allowed_roots"):
        bits.append(f"{len(pol['allowed_roots'])} allowed root(s)")
    if pol.get("blocked_root_patterns"):
        bits.append("blocked: " + ", ".join(map(str, pol["blocked_root_patterns"])))
    return "; ".join(bits) + f" ({pol['_source']})"


# ---------- the folder transport ----------

class FolderTransport:
    def __init__(self, root, kit_id=None, layout="shared"):
        if layout not in ("shared", "outbox"):
            raise ValueError(f"unknown layout {layout!r}")
        self.root = pathlib.Path(root).expanduser()
        self.kit_id = kit_id
        self.layout = layout
        self.kind = "folder"
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
        old = old if isinstance(old, dict) else None
        if old and old.get("files") == files and isinstance(old.get("chain"), list):
            return False
        if old and isinstance(old.get("chain"), list) and not verify_chain(old):
            chain = extend_chain(old["chain"], old.get("files") or {}, files)
        else:
            chain = extend_chain([], {}, files)   # first chain (or a manifest from before chains)
        self._guard_own(mpath)
        atomic_write(mpath, json.dumps({"kit_id": self.kit_id, "updated": kr.now_iso(), "files": files,
                                        "chain": chain, "head": chain[-1]["hash"] if chain else GENESIS},
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
        if "chain" not in m:
            warnings.append(("unchained", kit, "manifest has no hash chain yet (an older Kit): its history "
                                               "can't be checked"))
            return m
        problems = verify_chain(m)
        if problems:
            warnings.append(("chain", kit, f"hash chain broken: {problems[0]}; this Kit's records are skipped"))
            return False
        return m

    def scan(self, schemas, kit_id=None, type=None, since=None):
        """Every acceptable record, as (record, info) pairs, plus warnings as (kind, where, message).
        info holds ref (kit/relative path), sha256, and verified (matched a manifest)."""
        out, warnings = [], []
        since_dt = kr.parse_iso(since) if isinstance(since, str) else since
        for kit in self.kits():
            if kit_id and kit != kit_id:
                continue
            base, rdir = self.kit_dir(kit), self.records_dir(kit)
            m = self._manifest(kit, warnings)
            if m is False:
                continue
            manifest = m["files"] if m else None
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
        """Drop a copy of one of this Kit's records into another Kit's inbox, in the older wrapper.
        Messages go through send_message (kit-team send) instead, with the owner's approval."""
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
        why = policy_check(rec, self)
        if why:
            raise TransportError(f"organization profile refuses sending {rec.get('id')!r}: {why}")
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = f"{self.kit_id}--{rec['schema']}--{local_id(rec)}--{stamp}.json"
        path = self.inbox_dir(to_kit) / name
        if not self._inside(path, self.inbox_dir(to_kit)):
            raise TransportError("refusing to write outside that Kit's inbox")
        atomic_write(path, json.dumps({"inbox_version": INBOX_VERSION, "from": self.kit_id, "to": to_kit,
                                       "sent": kr.now_iso(), "record": rec}, indent=2, sort_keys=True) + "\n")
        return path

    def chain_heads(self):
        """{kit: (seq, head hash, [entry hashes])} for Kits whose chain is intact (shared layout)."""
        out = {}
        if self.layout != "shared":
            return out
        for kit in self.kits():
            m = self._manifest(kit, [])
            if m and isinstance(m.get("chain"), list):
                out[kit] = (len(m["chain"]), m.get("head", GENESIS), [e["hash"] for e in m["chain"]])
        return out

    def send_message(self, rec, schemas):
        """Publish an approved message in this Kit's records, then drop an identical copy into each
        recipient's inbox. The caller must have the owner's approval; this never asks. Returns the
        inbox paths written."""
        self._need_kit()
        self._need_shared("messages")
        body = rec.get("body") or {}
        if rec.get("schema") != "message":
            raise TransportError("only message records are sent")
        if rec.get("kit_id") != self.kit_id or body.get("from_kit") != self.kit_id:
            raise TransportError("a message must come from this Kit")
        to = body.get("to") or []
        if not to or any(not KIT_ID.fullmatch(k or "") for k in to) or self.kit_id in to:
            raise TransportError(f"bad recipients {to!r}")
        problems = kr.validate(rec, schemas)
        if problems:
            raise TransportError("message isn't valid: " + "; ".join(problems[:3]))
        hits = kr.secret_hits(canonical(rec))
        if hits:
            raise TransportError(f"message looks like it holds a {', '.join(hits)}")
        why = policy_check(rec, self)
        if why:
            raise TransportError(f"organization profile refuses this message: {why}")
        self.publish(rec)
        self.finish()
        text, paths = canonical(rec), []
        for kit in to:
            path = self.inbox_dir(kit) / f"{self.kit_id}--message--{local_id(rec)}.json"
            if not self._inside(path, self.inbox_dir(kit)):
                raise TransportError("refusing to write outside that Kit's inbox")
            if path.exists() and path.read_text(encoding="utf-8", errors="ignore") != text:
                raise TransportError(f"{kit}'s inbox already has a different message with this id")
            atomic_write(path, text)
            paths.append(path)
        return paths

    def _check_message(self, f, data, schemas):
        """(record, '') or (None, why) for one message file in this Kit's inbox."""
        m = MESSAGE_FILE.match(f.name)
        if not m:
            return None, "file name isn't <sender>--message--<id>.json"
        sender, local = m.groups()
        try:
            rec = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None, "unreadable (still syncing?)"
        if not isinstance(rec, dict) or rec.get("schema") != "message":
            return None, "not a message record"
        ok, why = kr.accept(rec, schemas)
        if not ok:
            return None, why
        body = rec.get("body") or {}
        if rec.get("kit_id") != sender or body.get("from_kit") != sender or local_id(rec) != local:
            return None, "sender doesn't match the file it came in (spoofed?)"
        if self.kit_id not in (body.get("to") or []):
            return None, "this Kit isn't a recipient"
        mw = []
        man = self._manifest(sender, mw)
        if man is False:
            return None, "the sender's hash chain is broken"
        if not man:
            return None, "the sender has no manifest, so the message can't be verified"
        if man["files"].get(f"records/message/{local}.json") != sha256(data):
            return None, "doesn't match the sender's manifest (changed, or not really sent by that Kit)"
        return rec, ""

    def inbox(self, schemas, now=None):
        """This Kit's inbox items, checked: (items, warnings). Items are information only. Message
        items carry expired=True once past their expiry."""
        self._need_kit()
        items, warnings = [], []
        now = now or dt.datetime.now(dt.timezone.utc)
        d, acks = self.inbox_dir(self.kit_id), self.ack_dir(self.kit_id)
        for f in sorted(d.glob("*.json")) if d.is_dir() else []:
            if f.name.startswith("."):
                continue
            if CONFLICT.search(f.name):
                warnings.append(("conflict", f"inbox/{f.name}", "sync-conflict or temporary copy: skipped"))
                continue
            if "--message--" in f.name:
                data = f.read_bytes() if f.stat().st_size <= MAX_BYTES else b""
                rec, why = self._check_message(f, data, schemas) if data else (None, "too large")
                if why:
                    warnings.append(("rejected", f"inbox/{f.name}", why))
                    continue
                ack = self.read_path(acks / f.name) if (acks / f.name).exists() else None
                exp = kr.parse_iso(rec["body"]["expires"])
                items.append({"name": f.name, "from": rec["kit_id"], "sent": rec["created"], "record": rec,
                              "ack": (ack or {}).get("state", ""), "kind": "message",
                              "expired": bool(exp and exp < now)})
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
                          "ack": (ack or {}).get("state", ""), "kind": "wrapped", "expired": False})
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
    if s["transport"] == "sql" and not shared_root:
        return _sql(kit, kid)
    root = pathlib.Path(shared_root).expanduser() if shared_root else s["shared_root"]
    if root and s["transport"] in ("folder", "sql"):
        return FolderTransport(root, kid, "shared")
    if s["transport"] != "folder":
        raise TransportError(f"unknown transport {s['transport']!r} (folder or sql)")
    return FolderTransport(s["outbox"], kid, "outbox")


def _sql(kit, kid):
    """The SQL server transport (MySQL tested; see kit_sql_transport)."""
    import kit_sql_transport
    return kit_sql_transport.SQLTransport.from_settings(kit, kid)


def sources(kit=KIT):
    """What to read: the shared root when set, else this Kit's own outbox."""
    s = sharing_settings(kit)
    if s["transport"] == "sql":
        return [_sql(kit, s["kit_id"])]
    if s["shared_root"] and s["transport"] == "folder":
        return [FolderTransport(s["shared_root"], s["kit_id"], "shared")]
    return [FolderTransport(s["outbox"], s["kit_id"], "outbox")]


def team_retention(kit=None):
    """(older_than_days or None, holds dict) for cached team records: the "team_cache" rule in
    retention.json and the legal holds kit-retention keeps. Unreadable files mean keep everything
    and, for holds, treat everything as held."""
    kit = pathlib.Path(kit) if kit else KIT
    days, holds = None, {}
    try:
        rules = json.loads((kit / "memory/context/retention.json").read_text())
        days = (rules.get("team_cache") or {}).get("older_than_days")
    except (OSError, ValueError, AttributeError):
        days = None
    hp = kit / "memory/context/legal-holds.json"
    if hp.exists():
        try:
            holds = json.loads(hp.read_text())
            if not isinstance(holds, dict):
                holds = {"all": {"reason": "holds file isn't an object"}}
        except (OSError, ValueError):
            holds = {"all": {"reason": "holds file can't be read"}}
    return days, holds


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
            CREATE TABLE IF NOT EXISTS chain_heads (origin TEXT, kit_id TEXT, seq INTEGER, head TEXT,
                PRIMARY KEY (origin, kit_id));
            CREATE TABLE IF NOT EXISTS inbox_archive (name TEXT PRIMARY KEY, from_kit TEXT, id TEXT,
                expires TEXT, archived TEXT, json TEXT);
            CREATE TABLE IF NOT EXISTS records_holding (id TEXT PRIMARY KEY, sha256 TEXT, project TEXT,
                updated TEXT, reason TEXT, moved TEXT, json TEXT);
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
                    held = self.db.execute("SELECT sha256 FROM records_holding WHERE id = ?", (rid,)).fetchone()
                    if held and held[0] == info["sha256"]:
                        continue                   # purged into holding; unchanged at the source
                    row = self.db.execute("SELECT sha256 FROM records WHERE id = ?", (rid,)).fetchone()
                    state = "unchanged" if row and row[0] == info["sha256"] else "changed" if row else "new"
                    counts[state] += 1
                    self.db.execute(
                        "INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (rid, rec["kit_id"], rec["schema"], rec["project"], rec["classification"],
                         rec["schema_version"], rec["created"], rec["updated"], info["sha256"], t.origin,
                         info["ref"], int(info["verified"]), now, json.dumps(rec, sort_keys=True)))
                for kit, (seq, head, hashes) in (t.chain_heads().items() if hasattr(t, "chain_heads") else []):
                    known = self.db.execute("SELECT seq, head FROM chain_heads WHERE origin = ? AND kit_id = ?",
                                            (t.origin, kit)).fetchone()
                    if known and (known[0] > seq or hashes[known[0] - 1] != known[1]):
                        all_warnings.append(("history", kit, f"hash chain was rewritten since the last sync "
                                             f"(had {known[0]} entries, head {known[1][:12]}; now {seq}): "
                                             "its history was replaced"))
                    self.db.execute("INSERT OR REPLACE INTO chain_heads VALUES (?,?,?,?)", (t.origin, kit, seq, head))
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

    # expired messages
    def archive_expired(self, items):
        """Move expired inbox messages into the archive table (the sender's file is never touched).
        Returns how many were newly archived."""
        n, now = 0, kr.now_iso()
        with self.db:
            for i in items:
                if not i.get("expired"):
                    continue
                if self.db.execute("SELECT 1 FROM inbox_archive WHERE name = ?", (i["name"],)).fetchone():
                    continue
                r = i["record"]
                self.db.execute("INSERT INTO inbox_archive VALUES (?,?,?,?,?,?)",
                                (i["name"], i["from"], r["id"], r["body"].get("expires", ""), now,
                                 json.dumps(r, sort_keys=True)))
                n += 1
        return n

    def archived_names(self):
        return {r[0] for r in self.db.execute("SELECT name FROM inbox_archive")}

    # retention and legal holds
    def purge_candidates(self, older_than_days, holds):
        """Cached records older than the rule, minus any in a held project: [(id, project, updated)]."""
        if not older_than_days:
            return []
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(older_than_days))
        out = []
        for rid, project, updated in self.db.execute("SELECT id, project, updated FROM records ORDER BY updated"):
            u = kr.parse_iso(updated or "")
            if not u or u >= cutoff:
                continue
            if holds and ("all" in holds or project in holds):
                continue
            out.append((rid, project, updated))
        return out

    def purge(self, ids, reason):
        """Move records into the holding table (never deleted). Returns how many moved."""
        n, now = 0, kr.now_iso()
        with self.db:
            for rid in ids:
                row = self.db.execute("SELECT sha256, project, updated, json FROM records WHERE id = ?",
                                      (rid,)).fetchone()
                if not row:
                    continue
                self.db.execute("INSERT OR REPLACE INTO records_holding VALUES (?,?,?,?,?,?,?)",
                                (rid, row[0], row[1], row[2], reason, now, row[3]))
                self.db.execute("DELETE FROM records WHERE id = ?", (rid,))
                n += 1
        return n

    def holding(self):
        return [tuple(r) for r in self.db.execute("SELECT id, project, moved, reason FROM records_holding")]

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

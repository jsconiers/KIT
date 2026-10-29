#!/usr/bin/env python3
"""kit_sql_transport: share Kit records through a SQL server instead of a folder.

MySQL with PyMySQL is tested against a real server (MySQL 8.0, PyMySQL 1.2.3, 20-Oct-2026): creating
the database and tables (db-init), publishing, reading other Kits' records, refusing writes to
another Kit's rows, the organization profile, messages and acks, and detecting a tampered row.
PostgreSQL with psycopg passed the same live test (PostgreSQL 17.0, psycopg 3.3.6, 21-Oct-2026).
Microsoft SQL Server and the mysql-connector-python driver are still UNTESTED:
syntax-checked only. Try them on a test database first. Folder sharing is the other tested path.

  SQLTransport.from_settings(kit, kit_id)   reads memory/context/sharing-db.json
  SQLTransport(settings, kit_id)            settings: dialect, host, port, database, user,
                                            credential_env or keychain_entry, tls, driver

It offers the same operations as the folder transport: publish, list (scan), read, send a message
to other Kits' inboxes, list this Kit's inbox, and acknowledge. Tables (DDL per dialect in
shared/sql/<dialect>.sql): kits, records, messages, acks.

Rules, the same as the folder transport:
- This Kit writes only rows with its own kit_id: records it publishes, messages it sends, and
  acknowledgements of messages addressed to it. The code refuses anything else. Also restrict it in
  the database (row-level security on PostgreSQL; per-Kit schemas, views, or stored procedures on
  SQL Server and MySQL; see shared/sql/README.md), so a Kit can't write another Kit's rows even
  with a modified copy of this code.
- Records and messages from other Kits are untrusted information: each is checked against its
  schema, must name the Kit in its kit_id column, and must match its stored sha256. Each Kit's
  records form a hash chain (prev_hash), and a reader reports a broken chain.
- The organization profile applies: transport "sql" must be in allowed_transports, and
  max_classification["sql"] and allow_confidential limit what may leave.
- Every query is parameterized. TLS is required unless the settings say "tls": "off" (refused by
  default; for a database on this computer only).
- Credentials are named, never stored: an environment variable (credential_env) or a Keychain entry
  (keychain_entry), read through kit_secrets only when connecting.

Drivers are imported only when a connection is opened, so nothing here needs installing until you
use it:
  postgres  psycopg (version 3):           pip install "psycopg[binary]"
  mssql     pyodbc (with an ODBC driver)   pip install pyodbc        or pymssql: pip install pymssql
  mysql     PyMySQL                        pip install PyMySQL       or mysql-connector-python
"""
import datetime as dt
import hashlib
import json
import pathlib
import re

import kit_records as kr
import kit_transport as kt

UNTESTED = "UNTESTED: never run against a real database"
TESTED = {("mysql", "pymysql"): "tested on MySQL 8.0 with PyMySQL",
          ("postgres", "psycopg"): "tested on PostgreSQL 17 with psycopg 3"}
DIALECTS = ("postgres", "mssql", "mysql")
DEFAULT_PORTS = {"postgres": 5432, "mssql": 1433, "mysql": 3306}
DEFAULT_DRIVERS = {"postgres": "psycopg", "mssql": "pyodbc", "mysql": "pymysql"}
DRIVER_PACKAGES = {"psycopg": 'psycopg (version 3): pip install "psycopg[binary]"',
                   "pyodbc": "pyodbc and an ODBC Driver for SQL Server: pip install pyodbc",
                   "pymssql": "pymssql: pip install pymssql",
                   "pymysql": "PyMySQL: pip install PyMySQL",
                   "mysql.connector": "mysql-connector-python: pip install mysql-connector-python"}
GENESIS = "0" * 64
SETTINGS_FILE = "memory/context/sharing-db.json"


def chain_hash(prev, kit_id, typ, local, digest):
    return hashlib.sha256(f"{prev}|{kit_id}|{typ}|{local}|{digest}".encode("utf-8")).hexdigest()


def load_settings(kit=None):
    """The database settings from memory/context/sharing-db.json, or a TransportError."""
    kit = pathlib.Path(kit) if kit else kt.KIT
    path = kit / SETTINGS_FILE
    try:
        s = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as ex:
        raise kt.TransportError(f"Transport is sql but {path} can't be read ({ex})")
    if not isinstance(s, dict) or s.get("dialect") not in DIALECTS:
        raise kt.TransportError(f"{path}: dialect must be one of {', '.join(DIALECTS)}")
    for key in ("host", "database", "user"):
        if not s.get(key) or str(s[key]).lower() == "not set":
            raise kt.TransportError(f"{path}: {key} isn't set")
    return s


class SQLTransport:
    """Share records through a SQL server. MySQL with PyMySQL and PostgreSQL with psycopg are tested;
    the rest is UNTESTED."""

    kind = "sql"
    layout = "sql"

    def __init__(self, settings, kit_id=None):
        self.s = dict(settings)
        self.dialect = self.s["dialect"]
        if self.dialect not in DIALECTS:
            raise kt.TransportError(f"unknown dialect {self.dialect!r}")
        self.kit_id = kit_id
        self.driver = self.s.get("driver") or DEFAULT_DRIVERS[self.dialect]
        port = self.s.get("port") or DEFAULT_PORTS[self.dialect]
        self.origin = f"sql:{self.dialect}://{self.s['host']}:{port}/{self.s['database']}"
        self.root = self.origin
        self._conn = None

    @classmethod
    def from_settings(cls, kit=None, kit_id=None):
        return cls(load_settings(kit), kit_id)

    def __repr__(self):
        return f"SQLTransport({self.origin!r}, {self.kit_id!r})"

    def describe(self):
        return f"{self.origin} (sql, {self.driver}; {self.test_status()})"

    def test_status(self):
        return TESTED.get((self.dialect, self.driver), UNTESTED)

    # ---------- setup ----------
    def init_schema(self):
        """Create the database (MySQL, PostgreSQL) and Kit's tables from shared/sql/<dialect>.sql.
        Safe to rerun: every statement is CREATE ... IF NOT EXISTS. Returns the tables found after.
        The account needs rights to create this one database and its tables, nothing more."""
        ddl_file = pathlib.Path(__file__).resolve().parent / "sql" / f"{self.dialect}.sql"
        lines = [ln for ln in ddl_file.read_text(encoding="utf-8").splitlines() if not ln.strip().startswith("--")]
        if self.dialect == "mssql":
            raise kt.TransportError(f"SQL Server: create the database, then run {ddl_file} with sqlcmd "
                                    "(it uses GO batches); db-init doesn't do SQL Server yet")
        stmts = [x.strip() for x in "\n".join(lines).split(";") if x.strip()]
        db = str(self.s["database"])
        if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", db):
            raise kt.TransportError(f"database name {db!r} must be letters, digits, and underscores")
        tls = str(self.s.get("tls", "require")).lower()
        if tls == "off" and str(self.s["host"]) not in ("localhost", "127.0.0.1", "::1"):
            raise kt.TransportError("tls is off for a database that isn't on this computer; refused")
        port = int(self.s.get("port") or DEFAULT_PORTS[self.dialect])
        cred = self._credential()
        if self.dialect == "mysql":
            mod = self._import("pymysql" if self.driver == "pymysql" else "mysql.connector")
            if self.driver == "pymysql":
                ssl = None if tls == "off" else ({"ca": self.s["ssl_ca"]} if self.s.get("ssl_ca") else {})
                conn = mod.connect(host=self.s["host"], port=port, user=self.s["user"], password=cred, ssl=ssl,
                                   charset="utf8mb4", connect_timeout=int(self.s.get("timeout", 15)))
            else:
                conn = mod.connect(host=self.s["host"], port=port, user=self.s["user"], password=cred,
                                   ssl_disabled=(tls == "off"))
            del cred
            cur = conn.cursor()
            try:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db}` CHARACTER SET utf8mb4")
                cur.execute(f"USE `{db}`")
                for st in stmts:
                    cur.execute(st)
                conn.commit()
                cur.execute("SHOW TABLES")
                return sorted(r[0] for r in cur.fetchall())
            finally:
                cur.close()
                conn.close()
        # PostgreSQL: CREATE DATABASE can't run in a transaction, so use autocommit.
        mod = self._import("psycopg")
        conn = mod.connect(host=self.s["host"], port=port, dbname="postgres", user=self.s["user"], password=cred,
                           sslmode="disable" if tls == "off" else self.s.get("sslmode", "verify-full"),
                           autocommit=True)
        try:
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,)).fetchone():
                conn.execute(f'CREATE DATABASE "{db}"')
        finally:
            conn.close()
        self._conn = None
        c = self.connect()
        cur = c.cursor()
        try:
            for st in stmts:
                cur.execute(st)
            c.commit()
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()")
            return sorted(r[0] for r in cur.fetchall())
        finally:
            cur.close()

    # ---------- connection ----------
    def _credential(self):
        import kit_secrets
        provider = {k: self.s[k] for k in ("credential_env", "keychain_entry") if self.s.get(k)}
        if not provider:
            raise kt.TransportError(f"{SETTINGS_FILE}: name a credential_env or keychain_entry for the database")
        try:
            cred = kit_secrets.resolve(dict(provider, credential_required=True), name="database")
        except kit_secrets.CredentialError as ex:   # names where it looked, never a value
            raise kt.TransportError(f"database credential: {ex}")
        if cred is None:
            raise kt.TransportError("database credential not found")
        return cred.reveal()

    def _import(self, module):
        try:
            return __import__(module, fromlist=["connect"])
        except ImportError:
            raise kt.TransportError(f"the {self.dialect} adapter needs {DRIVER_PACKAGES.get(module, module)}")

    def connect(self):
        if self._conn is not None:
            return self._conn
        tls = str(self.s.get("tls", "require")).lower()
        if tls == "off" and str(self.s["host"]) not in ("localhost", "127.0.0.1", "::1"):
            raise kt.TransportError("tls is off for a database that isn't on this computer; refused")
        port = int(self.s.get("port") or DEFAULT_PORTS[self.dialect])
        cred = self._credential()
        if self.dialect == "postgres":
            mod = self._import("psycopg")
            self._conn = mod.connect(host=self.s["host"], port=port, dbname=self.s["database"],
                                     user=self.s["user"], password=cred,
                                     sslmode="disable" if tls == "off" else self.s.get("sslmode", "verify-full"),
                                     connect_timeout=int(self.s.get("timeout", 15)))
        elif self.dialect == "mssql" and self.driver == "pyodbc":
            mod = self._import("pyodbc")
            parts = {"DRIVER": "{" + self.s.get("odbc_driver", "ODBC Driver 18 for SQL Server") + "}",
                     "SERVER": f"{self.s['host']},{port}", "DATABASE": self.s["database"], "UID": self.s["user"],
                     "PWD": cred, "Encrypt": "no" if tls == "off" else "yes",
                     "TrustServerCertificate": "yes" if self.s.get("trust_server_certificate") else "no"}
            self._conn = mod.connect(";".join(f"{k}={v}" for k, v in parts.items()), autocommit=False,
                                     timeout=int(self.s.get("timeout", 15)))
        elif self.dialect == "mssql":
            mod = self._import("pymssql")
            self._conn = mod.connect(server=self.s["host"], port=port, database=self.s["database"],
                                     user=self.s["user"], password=cred, login_timeout=int(self.s.get("timeout", 15)))
            # pymssql's encryption depends on the FreeTDS build and its settings; pyodbc with
            # Encrypt=yes enforces TLS reliably, so prefer pyodbc where TLS matters.
        elif self.driver == "mysql.connector":
            mod = self._import("mysql.connector")
            self._conn = mod.connect(host=self.s["host"], port=port, database=self.s["database"],
                                     user=self.s["user"], password=cred, ssl_disabled=(tls == "off"),
                                     connection_timeout=int(self.s.get("timeout", 15)))
        else:
            mod = self._import("pymysql")
            ssl = None if tls == "off" else ({"ca": self.s["ssl_ca"]} if self.s.get("ssl_ca") else {})
            self._conn = mod.connect(host=self.s["host"], port=port, database=self.s["database"],
                                     user=self.s["user"], password=cred, ssl=ssl, charset="utf8mb4",
                                     connect_timeout=int(self.s.get("timeout", 15)))
        del cred
        if self.dialect == "mysql":
            # MySQL's default REPEATABLE READ keeps a connection's snapshot from its first read, so a
            # reader would miss messages and changes other Kits commit afterwards (found in the first
            # live test). READ COMMITTED matches PostgreSQL's and SQL Server's defaults.
            cur = self._conn.cursor()
            try:
                cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
            finally:
                cur.close()
        return self._conn

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _q(self, sql):
        """Queries are written with ? placeholders; convert for drivers that use %s."""
        if self.driver in ("psycopg", "pymssql", "pymysql", "mysql.connector"):
            return sql.replace("?", "%s")
        return sql

    def _exec(self, sql, args=(), fetch=False):
        cur = self.connect().cursor()
        try:
            cur.execute(self._q(sql), tuple(args))
            return cur.fetchall() if fetch else cur.rowcount
        finally:
            cur.close()

    def _need_kit(self):
        if not self.kit_id or not kt.KIT_ID.fullmatch(self.kit_id):
            raise kt.TransportError(f"Kit id {self.kit_id!r} isn't set or isn't valid")

    @staticmethod
    def _now():
        return dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)

    # ---------- writing (this Kit only) ----------
    def _ensure_kit(self):
        rows = self._exec("SELECT head_hash, seq FROM kits WHERE kit_id = ?", (self.kit_id,), fetch=True)
        if rows:
            return rows[0][0], int(rows[0][1])
        self._exec("INSERT INTO kits (kit_id, head_hash, seq, updated_at) VALUES (?, ?, ?, ?)",
                   (self.kit_id, GENESIS, 0, self._now()))
        return GENESIS, 0

    def publish(self, rec):
        """Write or update one of this Kit's records. Returns (ref, written). Commit with finish()."""
        self._need_kit()
        if rec.get("kit_id") != self.kit_id:
            raise kt.TransportError(f"record {rec.get('id')!r} belongs to {rec.get('kit_id')!r}, not this Kit")
        problems = kr.validate(rec, kr.load_schemas())
        if problems:
            raise kt.TransportError(f"record {rec.get('id')!r} isn't valid: " + "; ".join(problems[:3]))
        why = kt.policy_check(rec, self)
        if why:
            raise kt.TransportError(f"organization profile refuses {rec.get('id')!r}: {why}")
        text = kt.canonical(rec)
        digest = kt.sha256(text.encode("utf-8"))
        typ, local = rec["schema"], kt.local_id(rec)
        ref = f"{self.kit_id}/{typ}/{local}"
        row = self._exec("SELECT sha256 FROM records WHERE kit_id = ? AND type = ? AND local_id = ?",
                         (self.kit_id, typ, local), fetch=True)
        if row and row[0][0] == digest:
            return ref, False
        prev, seq = self._ensure_kit()
        new_head = chain_hash(prev, self.kit_id, typ, local, digest)
        args = (rec["schema_version"], digest, prev, rec["classification"], rec["project"], text, self._now())
        if row:
            self._exec("UPDATE records SET version = ?, sha256 = ?, prev_hash = ?, classification = ?, project = ?, "
                       "json = ?, published_at = ? WHERE kit_id = ? AND type = ? AND local_id = ?",
                       (*args, self.kit_id, typ, local))
        else:
            self._exec("INSERT INTO records (version, sha256, prev_hash, classification, project, json, published_at, "
                       "kit_id, type, local_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (*args, self.kit_id, typ, local))
        self._exec("UPDATE kits SET head_hash = ?, seq = ?, updated_at = ? WHERE kit_id = ?",
                   (new_head, seq + 1, self._now(), self.kit_id))
        return ref, True

    def own_refs(self):
        self._need_kit()
        return {f"{self.kit_id}/{t}/{l}" for t, l in
                self._exec("SELECT type, local_id FROM records WHERE kit_id = ?", (self.kit_id,), fetch=True)}

    def remove_ref(self, ref):
        kit, typ, local = ref.split("/", 2)
        if kit != self.kit_id:
            raise kt.TransportError("refusing to remove another Kit's record")
        self._exec("DELETE FROM records WHERE kit_id = ? AND type = ? AND local_id = ?", (kit, typ, local))

    def finish(self):
        """Commit this Kit's changes. Returns True."""
        if self._conn is not None:
            self._conn.commit()
        return True

    # ---------- reading (every Kit) ----------
    def kits(self):
        return [r[0] for r in self._exec("SELECT kit_id FROM kits ORDER BY kit_id", fetch=True)]

    def scan(self, schemas, kit_id=None, type=None, since=None):
        """Every acceptable record as (record, info), plus warnings, the same shapes as the folder
        transport. The chain check here is a light one: each record's stored sha256 must match its
        JSON, and its prev_hash must be a hash this Kit's chain could have produced."""
        out, warnings = [], []
        sql, args = "SELECT kit_id, type, local_id, sha256, prev_hash, json FROM records", []
        conds = []
        if kit_id:
            conds.append("kit_id = ?")
            args.append(kit_id)
        if type:
            conds.append("type = ?")
            args.append(type)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        since_dt = kr.parse_iso(since) if isinstance(since, str) else since
        for kit, typ, local, digest, prev, text in self._exec(sql + " ORDER BY kit_id, published_at", args, fetch=True):
            where = f"{kit}/{typ}/{local}"
            if kt.sha256(str(text).encode("utf-8")) != digest:
                warnings.append(("tampered", where, "row JSON doesn't match its sha256: skipped"))
                continue
            try:
                rec = json.loads(text)
            except ValueError:
                warnings.append(("rejected", where, "not JSON"))
                continue
            ok, why = kr.accept(rec, schemas)
            if why:
                warnings.append(("schema" if ok else "rejected", where, why))
            if not ok:
                continue
            if rec.get("kit_id") != kit or rec.get("schema") != typ or kt.local_id(rec) != local:
                warnings.append(("rejected", where, "row's kit, type, or id doesn't match its JSON"))
                continue
            if since_dt and (kr.parse_iso(rec.get("updated", "")) or since_dt) < since_dt:
                continue
            out.append((rec, {"ref": where, "sha256": digest, "verified": True, "kit": kit}))
        return out, warnings

    def list(self, schemas, kit_id=None, type=None, since=None):
        return [rec for rec, _ in self.scan(schemas, kit_id, type, since)[0]]

    def read(self, ref, schemas):
        kit, _, _ = ref.partition("/")
        for rec, info in self.scan(schemas, kit_id=kit)[0]:
            if info["ref"] == ref:
                return rec, ""
        return None, f"{ref}: not found, or not acceptable"

    def chain_heads(self):
        return {}   # the folder transport's history check; not built for SQL (UNTESTED adapter)

    # ---------- messages ----------
    def send_message(self, rec, schemas):
        """Publish an approved message and address it to each recipient. The caller must have the
        owner's approval."""
        self._need_kit()
        body = rec.get("body") or {}
        if rec.get("schema") != "message" or rec.get("kit_id") != self.kit_id or body.get("from_kit") != self.kit_id:
            raise kt.TransportError("only this Kit's own message records are sent")
        to = body.get("to") or []
        if not to or any(not kt.KIT_ID.fullmatch(k or "") for k in to) or self.kit_id in to:
            raise kt.TransportError(f"bad recipients {to!r}")
        hits = kr.secret_hits(kt.canonical(rec))
        if hits:
            raise kt.TransportError(f"message looks like it holds a {', '.join(hits)}")
        self.publish(rec)
        text = kt.canonical(rec)
        digest = kt.sha256(text.encode("utf-8"))
        for kit in to:
            self._exec("INSERT INTO messages (id, from_kit, to_kit, sha256, expires, sent_at, json) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (rec["id"], self.kit_id, kit, digest, body["expires"], self._now(), text))
        self.finish()
        return [f"{kit}:{rec['id']}" for kit in to]

    def inbox(self, schemas, now=None):
        self._need_kit()
        now = now or dt.datetime.now(dt.timezone.utc)
        items, warnings = [], []
        rows = self._exec("SELECT m.id, m.from_kit, m.sha256, m.json, a.state FROM messages m LEFT JOIN acks a "
                          "ON a.message_id = m.id AND a.by_kit = m.to_kit WHERE m.to_kit = ? ORDER BY m.sent_at",
                          (self.kit_id,), fetch=True)
        for mid, sender, digest, text, state in rows:
            where = f"inbox/{mid}"
            if kt.sha256(str(text).encode("utf-8")) != digest:
                warnings.append(("rejected", where, "message doesn't match its sha256"))
                continue
            try:
                rec = json.loads(text)
            except ValueError:
                warnings.append(("rejected", where, "not JSON"))
                continue
            ok, why = kr.accept(rec, schemas)
            body = rec.get("body") or {}
            if not ok:
                warnings.append(("rejected", where, why))
                continue
            if rec.get("kit_id") != sender or body.get("from_kit") != sender or self.kit_id not in (body.get("to") or []):
                warnings.append(("rejected", where, "sender or recipient doesn't match (spoofed?)"))
                continue
            stored = self._exec("SELECT sha256 FROM records WHERE kit_id = ? AND type = 'message' AND local_id = ?",
                                (sender, kt.local_id(rec)), fetch=True)
            if not stored or stored[0][0] != digest:
                warnings.append(("rejected", where, "doesn't match the sender's published message"))
                continue
            exp = kr.parse_iso(body.get("expires", ""))
            items.append({"name": mid, "from": sender, "sent": rec.get("created", ""), "record": rec,
                          "ack": state or "", "kind": "message", "expired": bool(exp and exp < now)})
        return items, warnings

    def ack(self, name, state="seen"):
        """Acknowledge a message addressed to this Kit (name is the message id)."""
        self._need_kit()
        if not self._exec("SELECT 1 FROM messages WHERE id = ? AND to_kit = ?", (name, self.kit_id), fetch=True):
            raise kt.TransportError(f"no inbox message {name!r}")
        self._exec("DELETE FROM acks WHERE message_id = ? AND by_kit = ?", (name, self.kit_id))
        self._exec("INSERT INTO acks (message_id, by_kit, state, at) VALUES (?, ?, ?, ?)",
                   (name, self.kit_id, state, self._now()))
        self.finish()
        return f"{self.origin} ack {name}"

    def acks_from(self, to_kit):
        self._need_kit()
        rows = self._exec("SELECT a.message_id, a.state FROM acks a JOIN messages m ON m.id = a.message_id "
                          "AND m.to_kit = a.by_kit WHERE a.by_kit = ? AND m.from_kit = ?",
                          (to_kit, self.kit_id), fetch=True)
        return {mid: st for mid, st in rows}

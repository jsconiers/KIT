# Sharing through a SQL server

**MySQL and PostgreSQL are tested; SQL Server is not.** The MySQL adapter (with PyMySQL) and
`mysql.sql` were tested against a real MySQL 8.0 server with PyMySQL 1.2.3 on 20-Oct-2026: `kit-team
db-init` created the database and tables, and the live test (`tests/live/test_sql_live.py`) passed
publishing, reading other Kits' records, refusing writes to another Kit's rows, the organization
profile, messages and acks, and tamper detection. The first live run found and fixed a real bug:
MySQL's default isolation level hid other Kits' newer commits from a reader, so the adapter now sets
READ COMMITTED. The PostgreSQL adapter (psycopg 3.3.6) and `postgres.sql` passed the same live test
against PostgreSQL 17.0 (Postgres.app) on 21-Oct-2026, with `kit-team db-init` creating the tables.
The SQL Server adapter, its DDL, and the mysql-connector-python
driver are still **UNTESTED**: syntax-checked only. Try them on a test database first.

## Setup

1. Create the database and tables. For MySQL and PostgreSQL, `kit-team db-init` does it (it's safe
   to rerun) once the settings below are filled in: the account needs rights to create this one
   database and its tables, for example `GRANT ALL PRIVILEGES ON kit_sharing.* TO
   'kit_user'@'localhost'` in MySQL. For SQL Server, create the database and run `mssql.sql` with
   sqlcmd. (MAMP's MySQL listens on port 8889, not 3306.)
2. Create one login per Kit, and limit each to its own rows (below).
3. In each Kit, set **Transport** to `sql` in `memory/context/sharing.md`, and fill in
   `memory/context/sharing-db.json`:

   ```json
   {
     "dialect": "postgres",
     "host": "db.example.internal",
     "port": 5432,
     "database": "kit_sharing",
     "user": "kit_kit_7f3a",
     "credential_env": "KIT_DB_CREDENTIAL",
     "keychain_entry": "",
     "tls": "require",
     "driver": "psycopg"
   }
   ```

   The credential is named, never stored: an environment variable or a macOS Keychain entry.
   `tls` is `require` by default; `off` is refused unless the host is this computer. Optional keys:
   `sslmode` (PostgreSQL, default `verify-full`), `odbc_driver` and `trust_server_certificate` (SQL
   Server with pyodbc), `ssl_ca` (MySQL with PyMySQL), `timeout` (seconds).
4. Add `sql` to `allowed_transports` in `memory/context/sharing-policy.json`, and set
   `max_classification.sql` (default internal). Confidential records never leave unless
   `allow_confidential` is true.
5. Install the driver for your dialect (a project dependency): `psycopg[binary]` for PostgreSQL;
   `pyodbc` plus Microsoft's ODBC Driver 18, or `pymssql`, for SQL Server; `PyMySQL` or
   `mysql-connector-python` for MySQL. Nothing is imported until a connection is opened.
6. `kit-team status` shows the transport and whether that dialect and driver are tested.
7. To check a setup end to end: `python3 tests/live/test_sql_live.py` (from a repo clone; it uses two
   test Kit ids and removes its rows).

## Limiting each Kit to its own rows

The code refuses to write another Kit's rows, but enforce it in the database too, so a modified
copy of the code can't.

- **PostgreSQL:** `postgres.sql` turns on row-level security. Name each Kit's login
  `kit_<kit id with hyphens as underscores>` (for example `kit_kit_7f3a` for Kit id `kit-7f3a`);
  `kit_owner()` maps the login back to the Kit id. Grant `SELECT, INSERT, UPDATE, DELETE` on the
  four tables to each login; the policies limit writes to the login's own rows and messages to
  their sender and recipients.
- **SQL Server:** use row-level security: an inline table-valued predicate function returning rows
  where `kit_id` (or `from_kit`, `by_kit`) equals the Kit id mapped from `SUSER_SNAME()`, and a
  `CREATE SECURITY POLICY` with a FILTER predicate for reads you want limited and BLOCK predicates
  for inserts and updates.
- **MySQL:** there's no row-level security. Give each Kit a view per table with
  `WHERE kit_id = '<kit id>' WITH CHECK OPTION`, grant writes only on its views, and reads on the
  base tables; or route writes through stored procedures that set `kit_id` from `CURRENT_USER()`.

## What's untested

- SQL Server: every connection, query, and transaction, its DDL, and its grants.
- PostgreSQL's row-level security policies and per-Kit grants above (the live test used one role
  for both test Kits). Password login was tested: the server required SCRAM-SHA-256 for the Kit
  role (a `pg_hba.conf` line for that role only) and refused it without the password. MySQL's per-Kit views (above) are untested too.
- The mysql-connector-python driver (PyMySQL is the tested one).
- The light hash-chain check (the SQL adapter checks each row's sha256 and keeps a per-Kit head
  and prev_hash, but doesn't replay the chain or detect history rewrites the way the folder
  transport does).
- TLS settings for each driver, and pymssql's encryption, which depends on its FreeTDS build.

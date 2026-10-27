-- Kit sharing tables for PostgreSQL. UNTESTED: never run against a real database.
-- Run once as the schema owner, then grant as in README.md (row-level security per Kit).

CREATE TABLE IF NOT EXISTS kits (
    kit_id      VARCHAR(40)  PRIMARY KEY,
    head_hash   CHAR(64)     NOT NULL,
    seq         INTEGER      NOT NULL DEFAULT 0,
    updated_at  TIMESTAMP    NOT NULL
);

CREATE TABLE IF NOT EXISTS records (
    kit_id          VARCHAR(40)   NOT NULL REFERENCES kits(kit_id),
    type            VARCHAR(40)   NOT NULL,
    local_id        VARCHAR(96)   NOT NULL,
    version         VARCHAR(10)   NOT NULL,
    sha256          CHAR(64)      NOT NULL,
    prev_hash       CHAR(64)      NOT NULL,
    classification  VARCHAR(20)   NOT NULL,
    project         VARCHAR(64)   NOT NULL,
    json            TEXT          NOT NULL,
    published_at    TIMESTAMP     NOT NULL,
    PRIMARY KEY (kit_id, type, local_id)
);
CREATE INDEX IF NOT EXISTS records_type ON records(type);
CREATE INDEX IF NOT EXISTS records_project ON records(project);

CREATE TABLE IF NOT EXISTS messages (
    id        VARCHAR(200)  NOT NULL,
    from_kit  VARCHAR(40)   NOT NULL REFERENCES kits(kit_id),
    to_kit    VARCHAR(40)   NOT NULL,
    sha256    CHAR(64)      NOT NULL,
    expires   VARCHAR(30)   NOT NULL,
    sent_at   TIMESTAMP     NOT NULL,
    json      TEXT          NOT NULL,
    PRIMARY KEY (id, to_kit)
);
CREATE INDEX IF NOT EXISTS messages_to ON messages(to_kit);

CREATE TABLE IF NOT EXISTS acks (
    message_id  VARCHAR(200)  NOT NULL,
    by_kit      VARCHAR(40)   NOT NULL,
    state       VARCHAR(20)   NOT NULL,
    at          TIMESTAMP     NOT NULL,
    PRIMARY KEY (message_id, by_kit)
);

-- Row-level security: each Kit's database login (named kit_<kit id with hyphens as underscores>)
-- writes only its own rows. kit_owner() maps the login back to a Kit id.
CREATE OR REPLACE FUNCTION kit_owner() RETURNS TEXT LANGUAGE sql STABLE AS
  $$ SELECT replace(substring(current_user from 5), '_', '-') $$;

ALTER TABLE kits ENABLE ROW LEVEL SECURITY;
ALTER TABLE records ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE acks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS kits_read ON kits;
DROP POLICY IF EXISTS kits_write ON kits;
CREATE POLICY kits_read ON kits FOR SELECT USING (true);
CREATE POLICY kits_write ON kits FOR ALL USING (kit_id = kit_owner()) WITH CHECK (kit_id = kit_owner());

DROP POLICY IF EXISTS records_read ON records;
DROP POLICY IF EXISTS records_write ON records;
CREATE POLICY records_read ON records FOR SELECT USING (true);
CREATE POLICY records_write ON records FOR ALL USING (kit_id = kit_owner()) WITH CHECK (kit_id = kit_owner());

DROP POLICY IF EXISTS messages_read ON messages;
DROP POLICY IF EXISTS messages_write ON messages;
CREATE POLICY messages_read ON messages FOR SELECT USING (to_kit = kit_owner() OR from_kit = kit_owner());
CREATE POLICY messages_write ON messages FOR INSERT WITH CHECK (from_kit = kit_owner());

DROP POLICY IF EXISTS acks_read ON acks;
DROP POLICY IF EXISTS acks_write ON acks;
CREATE POLICY acks_read ON acks FOR SELECT USING (true);
CREATE POLICY acks_write ON acks FOR ALL USING (by_kit = kit_owner()) WITH CHECK (by_kit = kit_owner());

-- Kit sharing tables for Microsoft SQL Server. UNTESTED: never run against a real database.
-- Run once as the schema owner, then grant as in README.md.

IF OBJECT_ID('dbo.kits', 'U') IS NULL
CREATE TABLE dbo.kits (
    kit_id      VARCHAR(40)  NOT NULL PRIMARY KEY,
    head_hash   CHAR(64)     NOT NULL,
    seq         INT          NOT NULL DEFAULT 0,
    updated_at  DATETIME2    NOT NULL
);

IF OBJECT_ID('dbo.records', 'U') IS NULL
CREATE TABLE dbo.records (
    kit_id          VARCHAR(40)    NOT NULL REFERENCES dbo.kits(kit_id),
    type            VARCHAR(40)    NOT NULL,
    local_id        VARCHAR(96)    NOT NULL,
    version         VARCHAR(10)    NOT NULL,
    sha256          CHAR(64)       NOT NULL,
    prev_hash       CHAR(64)       NOT NULL,
    classification  VARCHAR(20)    NOT NULL,
    project         VARCHAR(64)    NOT NULL,
    json            NVARCHAR(MAX)  NOT NULL,
    published_at    DATETIME2      NOT NULL,
    CONSTRAINT pk_records PRIMARY KEY (kit_id, type, local_id)
);

IF OBJECT_ID('dbo.messages', 'U') IS NULL
CREATE TABLE dbo.messages (
    id        VARCHAR(200)   NOT NULL,
    from_kit  VARCHAR(40)    NOT NULL REFERENCES dbo.kits(kit_id),
    to_kit    VARCHAR(40)    NOT NULL,
    sha256    CHAR(64)       NOT NULL,
    expires   VARCHAR(30)    NOT NULL,
    sent_at   DATETIME2      NOT NULL,
    json      NVARCHAR(MAX)  NOT NULL,
    CONSTRAINT pk_messages PRIMARY KEY (id, to_kit)
);

IF OBJECT_ID('dbo.acks', 'U') IS NULL
CREATE TABLE dbo.acks (
    message_id  VARCHAR(200)  NOT NULL,
    by_kit      VARCHAR(40)   NOT NULL,
    state       VARCHAR(20)   NOT NULL,
    at          DATETIME2     NOT NULL,
    CONSTRAINT pk_acks PRIMARY KEY (message_id, by_kit)
);

-- Per-Kit write limits: SQL Server has row-level security (CREATE SECURITY POLICY with a FILTER
-- and BLOCK predicate on kit_id = the login's Kit id). See README.md for the predicate function.

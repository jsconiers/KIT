-- Kit sharing tables for MySQL 8. UNTESTED: never run against a real database.
-- Run once as the schema owner, then grant as in README.md. MySQL has no row-level security, so
-- per-Kit write limits come from views with WITH CHECK OPTION or stored procedures (README.md).

CREATE TABLE IF NOT EXISTS kits (
    kit_id      VARCHAR(40)  NOT NULL PRIMARY KEY,
    head_hash   CHAR(64)     NOT NULL,
    seq         INT          NOT NULL DEFAULT 0,
    updated_at  DATETIME     NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS records (
    kit_id          VARCHAR(40)  NOT NULL,
    type            VARCHAR(40)  NOT NULL,
    local_id        VARCHAR(96)  NOT NULL,
    version         VARCHAR(10)  NOT NULL,
    sha256          CHAR(64)     NOT NULL,
    prev_hash       CHAR(64)     NOT NULL,
    classification  VARCHAR(20)  NOT NULL,
    project         VARCHAR(64)  NOT NULL,
    json            MEDIUMTEXT   NOT NULL,
    published_at    DATETIME     NOT NULL,
    PRIMARY KEY (kit_id, type, local_id),
    KEY records_type (type),
    KEY records_project (project),
    CONSTRAINT records_kit FOREIGN KEY (kit_id) REFERENCES kits(kit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS messages (
    id        VARCHAR(200)  NOT NULL,
    from_kit  VARCHAR(40)   NOT NULL,
    to_kit    VARCHAR(40)   NOT NULL,
    sha256    CHAR(64)      NOT NULL,
    expires   VARCHAR(30)   NOT NULL,
    sent_at   DATETIME      NOT NULL,
    json      MEDIUMTEXT    NOT NULL,
    PRIMARY KEY (id, to_kit),
    KEY messages_to (to_kit),
    CONSTRAINT messages_kit FOREIGN KEY (from_kit) REFERENCES kits(kit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS acks (
    message_id  VARCHAR(200)  NOT NULL,
    by_kit      VARCHAR(40)   NOT NULL,
    state       VARCHAR(20)   NOT NULL,
    at          DATETIME      NOT NULL,
    PRIMARY KEY (message_id, by_kit)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

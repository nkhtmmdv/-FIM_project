-- =============================================
-- FIM Sentinel — Database Schema
-- =============================================

CREATE TABLE IF NOT EXISTS monitored_files (
    id              SERIAL PRIMARY KEY,
    file_path       TEXT UNIQUE NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    severity        VARCHAR(10) DEFAULT 'WARNING',
    added_at        TIMESTAMPTZ DEFAULT NOW(),
    added_by        TEXT DEFAULT 'system'
);

CREATE TABLE IF NOT EXISTS baseline_hashes (
    id              SERIAL PRIMARY KEY,
    file_path       TEXT NOT NULL,
    sha256_hash     TEXT NOT NULL,
    file_size       BIGINT,
    permissions     TEXT,
    owner_uid       INTEGER,
    owner_gid       INTEGER,
    owner_name      TEXT,
    inode           BIGINT,
    baseline_set_at TIMESTAMPTZ DEFAULT NOW(),
    baseline_scan_id INTEGER
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id              SERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    duration_ms     INTEGER,
    files_scanned   INTEGER DEFAULT 0,
    files_clean     INTEGER DEFAULT 0,
    files_modified  INTEGER DEFAULT 0,
    files_deleted   INTEGER DEFAULT 0,
    files_added     INTEGER DEFAULT 0,
    status          VARCHAR(20) DEFAULT 'RUNNING',
    triggered_by    TEXT DEFAULT 'scheduler'
);

CREATE TABLE IF NOT EXISTS file_events (
    id                  SERIAL PRIMARY KEY,
    scan_run_id         INTEGER REFERENCES scan_runs(id),
    file_path           TEXT NOT NULL,
    event_type          VARCHAR(30) NOT NULL,
    severity            VARCHAR(10),
    hash_before         TEXT,
    hash_after          TEXT,
    size_before         BIGINT,
    size_after          BIGINT,
    permissions_before  TEXT,
    permissions_after   TEXT,
    owner_before        TEXT,
    owner_after         TEXT,
    detected_at         TIMESTAMPTZ DEFAULT NOW(),
    acknowledged        BOOLEAN DEFAULT FALSE,
    acknowledged_by     TEXT,
    acknowledged_at     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS users (
    id                  SERIAL PRIMARY KEY,
    username            TEXT UNIQUE NOT NULL,
    password_hash       TEXT NOT NULL,
    role                VARCHAR(20) DEFAULT 'analyst',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    last_login          TIMESTAMPTZ,
    telegram_chat_id    TEXT DEFAULT '',
    telegram_bot_token  TEXT DEFAULT ''
);

-- Migration: add columns if upgrading from older schema
ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_chat_id   TEXT DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_bot_token TEXT DEFAULT '';

-- Migration: replace all individual file/dir entries with single root
DELETE FROM monitored_files;
ALTER TABLE file_events ADD COLUMN IF NOT EXISTS acknowledged_by  TEXT;
ALTER TABLE file_events ADD COLUMN IF NOT EXISTS acknowledged_at  TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS audit_log (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL,
    action          TEXT NOT NULL,
    target          TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    ip_address      INET
);

CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_file_events_detected_at ON file_events(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_file_events_file_path   ON file_events(file_path);
CREATE INDEX IF NOT EXISTS idx_file_events_event_type  ON file_events(event_type);
CREATE INDEX IF NOT EXISTS idx_scan_runs_started_at    ON scan_runs(started_at DESC);

-- Single root: scan everything under /monitored recursively
INSERT INTO monitored_files(file_path, severity) VALUES
    ('/monitored', 'WARNING')
ON CONFLICT DO NOTHING;


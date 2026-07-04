"""
Community Scanner — Schema DDL
==============================
Additive tables for the existing Vigil SQLite DB.
Applied on top of the core IntelDB schema.
"""

COMMUNITY_SCHEMA_SQL = """
-- ─────────────────────────────────────────────────────────────
-- Topic clusters. Seeded from taxonomy.yaml; slug is the join key
-- so the YAML can be re-synced without breaking FKs.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS signal_clusters (
    id          INTEGER PRIMARY KEY,
    slug        TEXT    NOT NULL UNIQUE,
    label       TEXT    NOT NULL,
    lane        TEXT    NOT NULL CHECK (lane IN ('grc', 'platform_utility', 'itsm', 'other')),
    lane_weight REAL    NOT NULL DEFAULT 1.0,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ─────────────────────────────────────────────────────────────
-- Raw ingested threads. One row per thread per source.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS community_signals (
    id                    INTEGER PRIMARY KEY,
    source                TEXT    NOT NULL CHECK (source IN ('sn_community', 'reddit', 'stackoverflow')),
    external_id           TEXT    NOT NULL,
    board                 TEXT,
    title                 TEXT    NOT NULL,
    body                  TEXT,
    url                   TEXT    NOT NULL,
    posted_at             TEXT    NOT NULL,
    reply_count           INTEGER NOT NULL DEFAULT 0,
    view_count            INTEGER,
    has_accepted_solution INTEGER NOT NULL DEFAULT 0,
    has_large_code_block  INTEGER NOT NULL DEFAULT 0,
    commercial_hits       INTEGER NOT NULL DEFAULT 0,
    cluster_id            INTEGER REFERENCES signal_clusters(id) ON DELETE SET NULL,
    ingested_at           TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at            TEXT,
    UNIQUE (source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_signals_cluster   ON community_signals(cluster_id);
CREATE INDEX IF NOT EXISTS idx_signals_posted_at ON community_signals(posted_at);
CREATE INDEX IF NOT EXISTS idx_signals_source    ON community_signals(source, board);

-- ─────────────────────────────────────────────────────────────
-- Monthly score snapshots per cluster (trailing 12-month window).
-- Append-only: keep history so week-over-week deltas are queryable.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cluster_scores (
    id               INTEGER PRIMARY KEY,
    cluster_id       INTEGER NOT NULL REFERENCES signal_clusters(id) ON DELETE CASCADE,
    scored_at        TEXT    NOT NULL,
    window_start     TEXT    NOT NULL,
    window_end       TEXT    NOT NULL,
    thread_count     INTEGER NOT NULL,
    unsolved_rate    REAL    NOT NULL,
    workaround_rate  REAL    NOT NULL,
    commercial_rate  REAL    NOT NULL,
    store_gap_score  REAL,
    composite_score  REAL    NOT NULL,
    UNIQUE (cluster_id, scored_at)
);

CREATE INDEX IF NOT EXISTS idx_scores_cluster ON cluster_scores(cluster_id, scored_at);

-- ─────────────────────────────────────────────────────────────
-- Digest routing: which clusters surfaced in which weekly digest,
-- and disposition. Feeds the Qualifier the same way procurement
-- signals do.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS digest_entries (
    id           INTEGER PRIMARY KEY,
    cluster_id   INTEGER NOT NULL REFERENCES signal_clusters(id) ON DELETE CASCADE,
    digest_date  TEXT    NOT NULL,
    rank         INTEGER NOT NULL,
    score_delta  REAL,
    disposition  TEXT    CHECK (disposition IN ('app_candidate', 'content_candidate', 'watch', 'dismissed'))
                 DEFAULT NULL,
    notes        TEXT,
    UNIQUE (cluster_id, digest_date)
);

-- ─────────────────────────────────────────────────────────────
-- Ingest state: watermarks per source for incremental pulls.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ingest_state (
    source      TEXT PRIMARY KEY,
    last_id     TEXT,
    last_posted TEXT,
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
"""


def apply_community_schema(conn) -> None:
    """Apply community scanner tables to an existing SQLite connection."""
    conn.executescript(COMMUNITY_SCHEMA_SQL)
    conn.commit()

"""
Vectis Market Intelligence — Database Layer
============================================
SQLite database connection and schema management.
"""

import sqlite3
from pathlib import Path


# ─── SCHEMA DDL ──────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- Sources: verifiable origins of information
CREATE TABLE IF NOT EXISTS sources (
    source_id         TEXT PRIMARY KEY,
    source_type       TEXT NOT NULL CHECK (source_type IN (
        'procurement_posting','contract_award','job_posting','press_release',
        'linkedin_activity','company_page','news_article','gov_report',
        'community_post','api_record'
    )),
    url               TEXT,
    url_status        TEXT NOT NULL DEFAULT 'unchecked' CHECK (url_status IN (
        'live','dead','paywall','auth_required','unchecked'
    )),
    url_last_verified TEXT,
    title             TEXT NOT NULL,
    publisher         TEXT,
    published_at      TEXT,
    captured_at       TEXT NOT NULL,
    content_hash      TEXT,
    snapshot_path     TEXT,
    collection_method TEXT NOT NULL CHECK (collection_method IN (
        'api_automated','manual_entry','rss_feed','scrape','tip'
    )),
    collector_agent   TEXT NOT NULL
);

-- Signals: atomic factual observations, never narratives
CREATE TABLE IF NOT EXISTS signals (
    signal_id            TEXT PRIMARY KEY,
    signal_type          TEXT NOT NULL CHECK (signal_type IN (
        'rfp_posted','contract_awarded','job_posted','leadership_change',
        'product_release','partnership_announced','hiring_velocity',
        'content_theme','tech_adoption','budget_signal','org_restructure'
    )),
    summary              TEXT NOT NULL,
    entity_refs          TEXT,  -- JSON array
    domain_tags          TEXT,  -- JSON array
    confidence           TEXT NOT NULL CHECK (confidence IN ('verified','inferred','speculative')),
    confidence_rationale TEXT NOT NULL,
    extracted_by         TEXT NOT NULL,
    extracted_at         TEXT NOT NULL,
    expires_at           TEXT,
    superseded_by        TEXT REFERENCES signals(signal_id)
);

-- Signal-Source junction: the provenance chain
CREATE TABLE IF NOT EXISTS signal_sources (
    signal_id       TEXT NOT NULL REFERENCES signals(signal_id) ON DELETE CASCADE,
    source_id       TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    relevance       TEXT NOT NULL CHECK (relevance IN ('primary','supporting','contradicting')),
    excerpt         TEXT CHECK (length(excerpt) <= 200),
    page_or_section TEXT,
    PRIMARY KEY (signal_id, source_id)
);

-- Correlations: hypotheses connecting multiple signals
CREATE TABLE IF NOT EXISTS correlations (
    correlation_id   TEXT PRIMARY KEY,
    signal_ids       TEXT NOT NULL,  -- JSON array (min 2)
    correlation_type TEXT NOT NULL CHECK (correlation_type IN (
        'temporal_cluster','entity_overlap','domain_convergence',
        'causal_hypothesis','contradictory'
    )),
    hypothesis       TEXT NOT NULL,
    strength         TEXT NOT NULL CHECK (strength IN ('strong','moderate','weak')),
    generated_by     TEXT NOT NULL,
    generated_at     TEXT NOT NULL,
    human_reviewed   INTEGER NOT NULL DEFAULT 0,
    human_verdict    TEXT CHECK (human_verdict IN ('confirmed','rejected','modified','pending')),
    review_notes     TEXT
);

-- Opportunities: human-created only, built from verified evidence
CREATE TABLE IF NOT EXISTS opportunities (
    opportunity_id         TEXT PRIMARY KEY,
    title                  TEXT NOT NULL,
    lane                   TEXT NOT NULL CHECK (lane IN (
        'core_servicenow','core_grc','innovation','nowforge_product'
    )),
    status                 TEXT NOT NULL CHECK (status IN (
        'watching','researching','pursuing','proposal_submitted',
        'won','lost','abandoned'
    )),
    source_correlation_ids TEXT NOT NULL,  -- JSON array
    verification_checklist TEXT NOT NULL,  -- JSON object
    verification_score     REAL NOT NULL CHECK (verification_score BETWEEN 0.0 AND 1.0),
    fit_score              REAL NOT NULL CHECK (fit_score BETWEEN 0.0 AND 1.0),
    estimated_value        INTEGER,
    estimated_effort       TEXT CHECK (estimated_effort IN (
        'trivial','small','medium','large','enterprise'
    )),
    next_action            TEXT,
    deadline               TEXT,
    created_by             TEXT NOT NULL DEFAULT 'human',
    created_at             TEXT NOT NULL
);

-- Verification log: audit trail for trust measurement
CREATE TABLE IF NOT EXISTS verifications (
    verification_id TEXT PRIMARY KEY,
    target_type     TEXT NOT NULL CHECK (target_type IN ('source','signal','correlation')),
    target_id       TEXT NOT NULL,
    verified_by     TEXT NOT NULL,
    verified_at     TEXT NOT NULL,
    result          TEXT NOT NULL CHECK (result IN ('confirmed','failed','partial','expired')),
    failure_reason  TEXT,
    notes           TEXT
);

-- ── INDEXES ──────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_sources_type ON sources(source_type);
CREATE INDEX IF NOT EXISTS idx_sources_captured ON sources(captured_at);
CREATE INDEX IF NOT EXISTS idx_sources_publisher ON sources(publisher);
CREATE INDEX IF NOT EXISTS idx_sources_url ON sources(url);

CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_signals_confidence ON signals(confidence);
CREATE INDEX IF NOT EXISTS idx_signals_extracted ON signals(extracted_at);
CREATE INDEX IF NOT EXISTS idx_signals_expires ON signals(expires_at);
CREATE INDEX IF NOT EXISTS idx_signals_agent ON signals(extracted_by);

CREATE INDEX IF NOT EXISTS idx_signal_sources_source ON signal_sources(source_id);

CREATE INDEX IF NOT EXISTS idx_correlations_strength ON correlations(strength);
CREATE INDEX IF NOT EXISTS idx_correlations_reviewed ON correlations(human_reviewed);
CREATE INDEX IF NOT EXISTS idx_correlations_verdict ON correlations(human_verdict);

CREATE INDEX IF NOT EXISTS idx_opportunities_lane ON opportunities(lane);
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);
CREATE INDEX IF NOT EXISTS idx_opportunities_score ON opportunities(fit_score);

CREATE INDEX IF NOT EXISTS idx_verifications_target ON verifications(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_verifications_result ON verifications(result);
CREATE INDEX IF NOT EXISTS idx_verifications_agent ON verifications(verified_by);

-- ── VIEWS ────────────────────────────────────────────────────────────────

-- Stale signals: past expiration date
CREATE VIEW IF NOT EXISTS v_stale_signals AS
SELECT s.*,
    julianday('now') - julianday(s.expires_at) AS days_stale
FROM signals s
WHERE s.expires_at IS NOT NULL
  AND s.expires_at < datetime('now')
  AND s.superseded_by IS NULL;

-- Orphan signals: missing source links (integrity violation)
CREATE VIEW IF NOT EXISTS v_orphan_signals AS
SELECT s.*
FROM signals s
LEFT JOIN signal_sources ss ON s.signal_id = ss.signal_id
WHERE ss.source_id IS NULL;

-- Agent trustworthiness: verification success rate per agent
CREATE VIEW IF NOT EXISTS v_agent_trust AS
SELECT
    s.extracted_by AS agent,
    COUNT(DISTINCT s.signal_id) AS total_signals,
    COUNT(DISTINCT CASE WHEN v.result = 'confirmed' THEN v.target_id END) AS verified_ok,
    COUNT(DISTINCT CASE WHEN v.result = 'failed' THEN v.target_id END) AS verified_fail,
    ROUND(
        CAST(COUNT(DISTINCT CASE WHEN v.result = 'confirmed' THEN v.target_id END) AS REAL) /
        NULLIF(COUNT(DISTINCT CASE WHEN v.result IN ('confirmed','failed') THEN v.target_id END), 0),
        3
    ) AS trust_score
FROM signals s
LEFT JOIN verifications v ON v.target_type = 'signal' AND v.target_id = s.signal_id
GROUP BY s.extracted_by;

-- Pipeline summary: opportunities by lane and status
CREATE VIEW IF NOT EXISTS v_pipeline_summary AS
SELECT
    lane,
    status,
    COUNT(*) AS count,
    SUM(estimated_value) AS total_value,
    ROUND(AVG(verification_score), 2) AS avg_verification,
    ROUND(AVG(fit_score), 2) AS avg_fit
FROM opportunities
GROUP BY lane, status;

-- Evidence depth: how many sources back each signal
CREATE VIEW IF NOT EXISTS v_signal_evidence_depth AS
SELECT
    s.signal_id,
    s.summary,
    s.confidence,
    COUNT(ss.source_id) AS source_count,
    SUM(CASE WHEN ss.relevance = 'primary' THEN 1 ELSE 0 END) AS primary_sources,
    SUM(CASE WHEN ss.relevance = 'contradicting' THEN 1 ELSE 0 END) AS contradicting_sources
FROM signals s
LEFT JOIN signal_sources ss ON s.signal_id = ss.signal_id
GROUP BY s.signal_id;
"""


# ─── DATABASE ────────────────────────────────────────────────────────────────

class IntelDB:
    """Core database connection and schema management."""

    def __init__(self, db_path: str = "vectis_intel.db"):
        self.db_path = db_path
        # Ensure parent directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

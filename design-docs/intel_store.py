"""
Vectis Market Intelligence — Storage Layer
==========================================
Provenance-first evidence chain database.
Every insight traces back to verifiable sources.

Storage: SQLite (portable, zero-config, embeddable)
Pattern: Repository per entity + integrity enforcement
"""

import sqlite3
import uuid
import json
import hashlib
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
from pathlib import Path


# ─── ENUMS ───────────────────────────────────────────────────────────────────

class SourceType(str, Enum):
    PROCUREMENT_POSTING = "procurement_posting"
    CONTRACT_AWARD = "contract_award"
    JOB_POSTING = "job_posting"
    PRESS_RELEASE = "press_release"
    LINKEDIN_ACTIVITY = "linkedin_activity"
    COMPANY_PAGE = "company_page"
    NEWS_ARTICLE = "news_article"
    GOV_REPORT = "gov_report"
    COMMUNITY_POST = "community_post"
    API_RECORD = "api_record"


class UrlStatus(str, Enum):
    LIVE = "live"
    DEAD = "dead"
    PAYWALL = "paywall"
    AUTH_REQUIRED = "auth_required"
    UNCHECKED = "unchecked"


class CollectionMethod(str, Enum):
    API_AUTOMATED = "api_automated"
    MANUAL_ENTRY = "manual_entry"
    RSS_FEED = "rss_feed"
    SCRAPE = "scrape"
    TIP = "tip"


class SignalType(str, Enum):
    RFP_POSTED = "rfp_posted"
    CONTRACT_AWARDED = "contract_awarded"
    JOB_POSTED = "job_posted"
    LEADERSHIP_CHANGE = "leadership_change"
    PRODUCT_RELEASE = "product_release"
    PARTNERSHIP_ANNOUNCED = "partnership_announced"
    HIRING_VELOCITY = "hiring_velocity"
    CONTENT_THEME = "content_theme"
    TECH_ADOPTION = "tech_adoption"
    BUDGET_SIGNAL = "budget_signal"
    ORG_RESTRUCTURE = "org_restructure"


class Confidence(str, Enum):
    VERIFIED = "verified"
    INFERRED = "inferred"
    SPECULATIVE = "speculative"


class CorrelationType(str, Enum):
    TEMPORAL_CLUSTER = "temporal_cluster"
    ENTITY_OVERLAP = "entity_overlap"
    DOMAIN_CONVERGENCE = "domain_convergence"
    CAUSAL_HYPOTHESIS = "causal_hypothesis"
    CONTRADICTORY = "contradictory"


class CorrelationStrength(str, Enum):
    STRONG = "strong"      # 3+ verified signals
    MODERATE = "moderate"  # 2 verified or 3+ inferred
    WEAK = "weak"          # inferred/speculative only


class HumanVerdict(str, Enum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    MODIFIED = "modified"
    PENDING = "pending"


class OpportunityLane(str, Enum):
    CORE_SERVICENOW = "core_servicenow"
    CORE_GRC = "core_grc"
    INNOVATION = "innovation"
    NOWFORGE_PRODUCT = "nowforge_product"


class OpportunityStatus(str, Enum):
    WATCHING = "watching"
    RESEARCHING = "researching"
    PURSUING = "pursuing"
    PROPOSAL_SUBMITTED = "proposal_submitted"
    WON = "won"
    LOST = "lost"
    ABANDONED = "abandoned"


class EffortSize(str, Enum):
    TRIVIAL = "trivial"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    ENTERPRISE = "enterprise"


class SourceRelevance(str, Enum):
    PRIMARY = "primary"
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"


class VerificationTarget(str, Enum):
    SOURCE = "source"
    SIGNAL = "signal"
    CORRELATION = "correlation"


class VerificationResult(str, Enum):
    CONFIRMED = "confirmed"
    FAILED = "failed"
    PARTIAL = "partial"
    EXPIRED = "expired"


# ─── DATACLASSES ─────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Source:
    source_type: str
    title: str
    collection_method: str
    collector_agent: str
    source_id: str = field(default_factory=_uuid)
    url: Optional[str] = None
    url_status: str = UrlStatus.UNCHECKED
    url_last_verified: Optional[str] = None
    publisher: Optional[str] = None
    published_at: Optional[str] = None
    captured_at: str = field(default_factory=_now)
    content_hash: Optional[str] = None
    snapshot_path: Optional[str] = None


@dataclass
class Signal:
    signal_type: str
    summary: str
    confidence: str
    confidence_rationale: str
    extracted_by: str
    signal_id: str = field(default_factory=_uuid)
    entity_refs: Optional[str] = None   # JSON array
    domain_tags: Optional[str] = None   # JSON array
    extracted_at: str = field(default_factory=_now)
    expires_at: Optional[str] = None
    superseded_by: Optional[str] = None


@dataclass
class SignalSource:
    signal_id: str
    source_id: str
    relevance: str
    excerpt: Optional[str] = None
    page_or_section: Optional[str] = None


@dataclass
class Correlation:
    signal_ids: str  # JSON array of UUIDs
    correlation_type: str
    hypothesis: str
    strength: str
    generated_by: str
    correlation_id: str = field(default_factory=_uuid)
    generated_at: str = field(default_factory=_now)
    human_reviewed: bool = False
    human_verdict: Optional[str] = None
    review_notes: Optional[str] = None


@dataclass
class Opportunity:
    title: str
    lane: str
    status: str
    source_correlation_ids: str  # JSON array
    verification_checklist: str  # JSON object
    verification_score: float
    fit_score: float
    created_by: str = "human"  # ALWAYS human
    opportunity_id: str = field(default_factory=_uuid)
    estimated_value: Optional[int] = None
    estimated_effort: Optional[str] = None
    next_action: Optional[str] = None
    deadline: Optional[str] = None
    created_at: str = field(default_factory=_now)


@dataclass
class Verification:
    target_type: str
    target_id: str
    verified_by: str
    result: str
    verification_id: str = field(default_factory=_uuid)
    verified_at: str = field(default_factory=_now)
    failure_reason: Optional[str] = None
    notes: Optional[str] = None


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


# ─── INTEGRITY ENGINE ────────────────────────────────────────────────────────

class IntegrityError(Exception):
    """Raised when a provenance integrity rule is violated."""
    pass


class IntegrityEngine:
    """
    Enforces the anti-hallucination guarantees:
    1. No orphan signals (signal must have ≥1 source)
    2. Opportunities are human-created only
    3. Confidence degrades upstream
    4. Correlation strength bounded by weakest signal
    5. Stale signals auto-flag
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def validate_signal_has_sources(self, signal_id: str) -> bool:
        """Rule 1: No orphan signals."""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM signal_sources WHERE signal_id = ?",
            (signal_id,)
        ).fetchone()
        return row["cnt"] > 0

    def validate_opportunity_creator(self, created_by: str) -> None:
        """Rule 2: Opportunities are human-created only."""
        if created_by != "human":
            raise IntegrityError(
                f"Opportunity created_by must be 'human', got '{created_by}'. "
                "AI agents can recommend but never create opportunities."
            )

    def compute_correlation_strength(self, signal_ids: list[str]) -> str:
        """
        Rule 3/4: Correlation strength bounded by signal confidence.
        - strong: 3+ verified signals
        - moderate: 2 verified OR 3+ inferred
        - weak: all other combinations
        """
        if len(signal_ids) < 2:
            raise IntegrityError("Correlation requires minimum 2 signals.")

        placeholders = ",".join("?" * len(signal_ids))
        rows = self.conn.execute(
            f"SELECT confidence FROM signals WHERE signal_id IN ({placeholders})",
            signal_ids
        ).fetchall()

        confidences = [r["confidence"] for r in rows]
        verified_count = confidences.count(Confidence.VERIFIED)
        inferred_count = confidences.count(Confidence.INFERRED)

        if verified_count >= 3:
            return CorrelationStrength.STRONG
        elif verified_count >= 2 or (inferred_count + verified_count) >= 3:
            return CorrelationStrength.MODERATE
        return CorrelationStrength.WEAK

    def check_stale_correlations(self) -> list[str]:
        """Rule 4 (staleness): Find correlations built on expired signals."""
        rows = self.conn.execute("""
            SELECT DISTINCT c.correlation_id
            FROM correlations c, json_each(c.signal_ids) AS j
            JOIN signals s ON s.signal_id = j.value
            WHERE s.expires_at IS NOT NULL
              AND s.expires_at < datetime('now')
              AND c.strength != 'weak'
        """).fetchall()
        return [r["correlation_id"] for r in rows]

    def downgrade_stale_correlations(self) -> int:
        """Auto-downgrade correlations built on stale signals to 'weak'."""
        stale_ids = self.check_stale_correlations()
        if not stale_ids:
            return 0
        placeholders = ",".join("?" * len(stale_ids))
        self.conn.execute(
            f"UPDATE correlations SET strength = 'weak' WHERE correlation_id IN ({placeholders})",
            stale_ids
        )
        self.conn.commit()
        return len(stale_ids)

    def compute_verification_score(self, checklist: dict) -> float:
        """Compute verification score from checklist items."""
        items = checklist.get("items", [])
        if not items:
            return 0.0
        verified = sum(1 for i in items if i.get("verified", False))
        return round(verified / len(items), 3)

    def run_integrity_audit(self) -> dict:
        """Full system integrity check. Returns report."""
        orphans = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM v_orphan_signals"
        ).fetchone()["cnt"]

        stale = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM v_stale_signals"
        ).fetchone()["cnt"]

        bad_opps = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM opportunities WHERE created_by != 'human'"
        ).fetchone()["cnt"]

        trust = self.conn.execute(
            "SELECT agent, trust_score FROM v_agent_trust"
        ).fetchall()

        low_trust_agents = [
            {"agent": r["agent"], "score": r["trust_score"]}
            for r in trust if r["trust_score"] is not None and r["trust_score"] < 0.8
        ]

        stale_downgraded = self.downgrade_stale_correlations()

        return {
            "orphan_signals": orphans,
            "stale_signals": stale,
            "non_human_opportunities": bad_opps,
            "low_trust_agents": low_trust_agents,
            "stale_correlations_downgraded": stale_downgraded,
            "integrity_ok": orphans == 0 and bad_opps == 0,
            "audited_at": _now(),
        }


# ─── REPOSITORIES ────────────────────────────────────────────────────────────

class SourceRepo:

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, source: Source) -> Source:
        data = asdict(source)
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        self.conn.execute(
            f"INSERT INTO sources ({cols}) VALUES ({placeholders})",
            list(data.values())
        )
        self.conn.commit()
        return source

    def get(self, source_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM sources WHERE source_id = ?", (source_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_url_status(self, source_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE sources SET url_status = ?, url_last_verified = ? WHERE source_id = ?",
            (status, _now(), source_id)
        )
        self.conn.commit()

    def list_by_type(self, source_type: str, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM sources WHERE source_type = ? ORDER BY captured_at DESC LIMIT ?",
            (source_type, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def list_unchecked(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM sources WHERE url_status = 'unchecked' AND url IS NOT NULL "
            "ORDER BY captured_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


class SignalRepo:

    def __init__(self, conn: sqlite3.Connection, integrity: IntegrityEngine):
        self.conn = conn
        self.integrity = integrity

    def create(self, signal: Signal, sources: list[SignalSource]) -> Signal:
        """Create signal with mandatory source links (no orphans)."""
        if not sources:
            raise IntegrityError(
                "Cannot create signal without at least one source link. "
                "Every signal must be traceable to a verifiable origin."
            )

        data = asdict(signal)
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        self.conn.execute(
            f"INSERT INTO signals ({cols}) VALUES ({placeholders})",
            list(data.values())
        )

        for ss in sources:
            ss.signal_id = signal.signal_id
            ss_data = asdict(ss)
            ss_cols = ", ".join(ss_data.keys())
            ss_ph = ", ".join("?" * len(ss_data))
            self.conn.execute(
                f"INSERT INTO signal_sources ({ss_cols}) VALUES ({ss_ph})",
                list(ss_data.values())
            )

        self.conn.commit()
        return signal

    def get(self, signal_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_with_sources(self, signal_id: str) -> Optional[dict]:
        """Get signal with full source provenance chain."""
        signal = self.get(signal_id)
        if not signal:
            return None

        sources = self.conn.execute("""
            SELECT ss.relevance, ss.excerpt, ss.page_or_section,
                   src.*
            FROM signal_sources ss
            JOIN sources src ON ss.source_id = src.source_id
            WHERE ss.signal_id = ?
        """, (signal_id,)).fetchall()

        signal["sources"] = [dict(s) for s in sources]
        return signal

    def list_by_confidence(self, confidence: str, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM signals WHERE confidence = ? ORDER BY extracted_at DESC LIMIT ?",
            (confidence, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def list_by_domain(self, tag: str, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM signals WHERE domain_tags LIKE ? ORDER BY extracted_at DESC LIMIT ?",
            (f'%"{tag}"%', limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def list_active(self, limit: int = 100) -> list[dict]:
        """Signals that aren't expired or superseded."""
        rows = self.conn.execute("""
            SELECT * FROM signals
            WHERE superseded_by IS NULL
              AND (expires_at IS NULL OR expires_at > datetime('now'))
            ORDER BY extracted_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def supersede(self, old_signal_id: str, new_signal: Signal, sources: list[SignalSource]) -> Signal:
        """Create new signal that supersedes an existing one."""
        new_signal = self.create(new_signal, sources)
        self.conn.execute(
            "UPDATE signals SET superseded_by = ? WHERE signal_id = ?",
            (new_signal.signal_id, old_signal_id)
        )
        self.conn.commit()
        return new_signal

    def add_source(self, link: SignalSource) -> None:
        """Add an additional source to an existing signal (corroboration)."""
        data = asdict(link)
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        self.conn.execute(
            f"INSERT OR IGNORE INTO signal_sources ({cols}) VALUES ({placeholders})",
            list(data.values())
        )
        self.conn.commit()


class CorrelationRepo:

    def __init__(self, conn: sqlite3.Connection, integrity: IntegrityEngine):
        self.conn = conn
        self.integrity = integrity

    def create(self, correlation: Correlation) -> Correlation:
        """Create correlation with auto-computed strength."""
        signal_ids = json.loads(correlation.signal_ids)

        # Enforce minimum 2 signals
        if len(signal_ids) < 2:
            raise IntegrityError("Correlation requires minimum 2 signals.")

        # Verify all referenced signals exist
        placeholders = ",".join("?" * len(signal_ids))
        found = self.conn.execute(
            f"SELECT COUNT(*) as cnt FROM signals WHERE signal_id IN ({placeholders})",
            signal_ids
        ).fetchone()["cnt"]
        if found != len(signal_ids):
            raise IntegrityError(
                f"Correlation references {len(signal_ids)} signals but only {found} exist."
            )

        # Auto-compute strength from signal confidence levels
        computed_strength = self.integrity.compute_correlation_strength(signal_ids)
        correlation.strength = computed_strength

        data = asdict(correlation)
        cols = ", ".join(data.keys())
        ph = ", ".join("?" * len(data))
        self.conn.execute(
            f"INSERT INTO correlations ({cols}) VALUES ({ph})",
            list(data.values())
        )
        self.conn.commit()
        return correlation

    def get_with_signals(self, correlation_id: str) -> Optional[dict]:
        """Get correlation with full signal chain."""
        row = self.conn.execute(
            "SELECT * FROM correlations WHERE correlation_id = ?",
            (correlation_id,)
        ).fetchone()
        if not row:
            return None

        corr = dict(row)
        signal_ids = json.loads(corr["signal_ids"])
        placeholders = ",".join("?" * len(signal_ids))
        signals = self.conn.execute(
            f"SELECT * FROM signals WHERE signal_id IN ({placeholders})",
            signal_ids
        ).fetchall()
        corr["signals"] = [dict(s) for s in signals]
        return corr

    def review(self, correlation_id: str, verdict: str, notes: str = None) -> None:
        """Record human review of a correlation."""
        self.conn.execute(
            "UPDATE correlations SET human_reviewed = 1, human_verdict = ?, review_notes = ? "
            "WHERE correlation_id = ?",
            (verdict, notes, correlation_id)
        )
        self.conn.commit()

    def list_pending_review(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM correlations WHERE human_reviewed = 0 "
            "ORDER BY generated_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


class OpportunityRepo:

    def __init__(self, conn: sqlite3.Connection, integrity: IntegrityEngine):
        self.conn = conn
        self.integrity = integrity

    def create(self, opportunity: Opportunity) -> Opportunity:
        """Create opportunity — enforces human-only creation."""
        self.integrity.validate_opportunity_creator(opportunity.created_by)

        # Verify all referenced correlations exist and are human-reviewed
        corr_ids = json.loads(opportunity.source_correlation_ids)
        for cid in corr_ids:
            row = self.conn.execute(
                "SELECT human_reviewed, human_verdict FROM correlations WHERE correlation_id = ?",
                (cid,)
            ).fetchone()
            if not row:
                raise IntegrityError(f"Correlation {cid} not found.")
            if not row["human_reviewed"]:
                raise IntegrityError(
                    f"Correlation {cid} has not been human-reviewed. "
                    "All supporting correlations must be reviewed before opportunity creation."
                )
            if row["human_verdict"] == HumanVerdict.REJECTED:
                raise IntegrityError(
                    f"Correlation {cid} was rejected. Cannot build opportunity on rejected evidence."
                )

        # Auto-compute verification score
        checklist = json.loads(opportunity.verification_checklist)
        opportunity.verification_score = self.integrity.compute_verification_score(checklist)

        data = asdict(opportunity)
        cols = ", ".join(data.keys())
        ph = ", ".join("?" * len(data))
        self.conn.execute(
            f"INSERT INTO opportunities ({cols}) VALUES ({ph})",
            list(data.values())
        )
        self.conn.commit()
        return opportunity

    def update_status(self, opportunity_id: str, status: str, next_action: str = None) -> None:
        self.conn.execute(
            "UPDATE opportunities SET status = ?, next_action = ? WHERE opportunity_id = ?",
            (status, next_action, opportunity_id)
        )
        self.conn.commit()

    def update_checklist(self, opportunity_id: str, checklist: dict) -> None:
        """Update checklist and recompute verification score."""
        score = self.integrity.compute_verification_score(checklist)
        self.conn.execute(
            "UPDATE opportunities SET verification_checklist = ?, verification_score = ? "
            "WHERE opportunity_id = ?",
            (json.dumps(checklist), score, opportunity_id)
        )
        self.conn.commit()

    def list_by_lane(self, lane: str, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM opportunities WHERE lane = ? AND status NOT IN ('won','lost','abandoned') "
            "ORDER BY fit_score DESC LIMIT ?",
            (lane, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def pipeline_summary(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM v_pipeline_summary").fetchall()
        return [dict(r) for r in rows]


class VerificationRepo:

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def log(self, verification: Verification) -> Verification:
        data = asdict(verification)
        cols = ", ".join(data.keys())
        ph = ", ".join("?" * len(data))
        self.conn.execute(
            f"INSERT INTO verifications ({cols}) VALUES ({ph})",
            list(data.values())
        )
        self.conn.commit()
        return verification

    def agent_trust_scores(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM v_agent_trust").fetchall()
        return [dict(r) for r in rows]

    def history_for(self, target_type: str, target_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM verifications WHERE target_type = ? AND target_id = ? "
            "ORDER BY verified_at DESC",
            (target_type, target_id)
        ).fetchall()
        return [dict(r) for r in rows]


# ─── EVIDENCE CHAIN TRAVERSAL ────────────────────────────────────────────────

class EvidenceChain:
    """
    Traverses the full evidence chain for any entity.
    Opportunity → Correlations → Signals → Sources
    This is how you answer: "Why are we pursuing this?"
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def trace_opportunity(self, opportunity_id: str) -> dict:
        """Full evidence chain from opportunity back to sources."""
        opp = self.conn.execute(
            "SELECT * FROM opportunities WHERE opportunity_id = ?",
            (opportunity_id,)
        ).fetchone()
        if not opp:
            return {"error": "Opportunity not found"}

        result = dict(opp)
        result["evidence_chain"] = []

        corr_ids = json.loads(opp["source_correlation_ids"])
        for cid in corr_ids:
            corr = self.conn.execute(
                "SELECT * FROM correlations WHERE correlation_id = ?", (cid,)
            ).fetchone()
            if not corr:
                continue

            corr_data = dict(corr)
            corr_data["signals"] = []

            signal_ids = json.loads(corr["signal_ids"])
            for sid in signal_ids:
                signal = self.conn.execute(
                    "SELECT * FROM signals WHERE signal_id = ?", (sid,)
                ).fetchone()
                if not signal:
                    continue

                signal_data = dict(signal)
                sources = self.conn.execute("""
                    SELECT ss.relevance, ss.excerpt, ss.page_or_section,
                           src.source_id, src.title, src.url, src.url_status,
                           src.publisher, src.source_type
                    FROM signal_sources ss
                    JOIN sources src ON ss.source_id = src.source_id
                    WHERE ss.signal_id = ?
                """, (sid,)).fetchall()

                signal_data["sources"] = [dict(s) for s in sources]
                corr_data["signals"].append(signal_data)

            result["evidence_chain"].append(corr_data)

        return result

    def trace_signal(self, signal_id: str) -> dict:
        """Trace a single signal back to its sources."""
        signal = self.conn.execute(
            "SELECT * FROM signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()
        if not signal:
            return {"error": "Signal not found"}

        result = dict(signal)
        sources = self.conn.execute("""
            SELECT ss.relevance, ss.excerpt, ss.page_or_section,
                   src.*
            FROM signal_sources ss
            JOIN sources src ON ss.source_id = src.source_id
            WHERE ss.signal_id = ?
        """, (signal_id,)).fetchall()

        result["sources"] = [dict(s) for s in sources]

        # Include verification history
        verifications = self.conn.execute(
            "SELECT * FROM verifications WHERE target_type = 'signal' AND target_id = ? "
            "ORDER BY verified_at DESC",
            (signal_id,)
        ).fetchall()
        result["verifications"] = [dict(v) for v in verifications]

        return result


# ─── CONVENIENCE FACADE ──────────────────────────────────────────────────────

class IntelStore:
    """
    High-level facade over the entire storage layer.
    
    Usage:
        with IntelStore("vectis_intel.db") as store:
            source = store.sources.create(Source(...))
            signal = store.signals.create(Signal(...), [SignalSource(...)])
            chain = store.evidence.trace_signal(signal.signal_id)
            audit = store.integrity.run_integrity_audit()
    """

    def __init__(self, db_path: str = "vectis_intel.db"):
        self.db = IntelDB(db_path)
        self.integrity = IntegrityEngine(self.db.conn)
        self.sources = SourceRepo(self.db.conn)
        self.signals = SignalRepo(self.db.conn, self.integrity)
        self.correlations = CorrelationRepo(self.db.conn, self.integrity)
        self.opportunities = OpportunityRepo(self.db.conn, self.integrity)
        self.verifications = VerificationRepo(self.db.conn)
        self.evidence = EvidenceChain(self.db.conn)

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ─── DEMO / SMOKE TEST ──────────────────────────────────────────────────────

def demo():
    """End-to-end smoke test demonstrating the evidence chain."""

    import os
    db_path = "demo_intel.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    with IntelStore(db_path) as store:
        print("=" * 60)
        print("VECTIS MARKET INTELLIGENCE — STORAGE LAYER DEMO")
        print("=" * 60)

        # 1. Create sources
        print("\n── Creating Sources ──")
        src_sam = store.sources.create(Source(
            source_type=SourceType.PROCUREMENT_POSTING,
            title="RFI: GRC Modernization Services - Dept of Treasury",
            url="https://sam.gov/opp/abc123/view",
            publisher="SAM.gov",
            published_at="2026-03-01T00:00:00Z",
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="procurement_scanner",
        ))
        print(f"  ✓ Source: {src_sam.title}")

        src_linkedin = store.sources.create(Source(
            source_type=SourceType.JOB_POSTING,
            title="Deloitte - Senior ServiceNow GRC Developer (6 postings)",
            url="https://linkedin.com/jobs/view/123456",
            publisher="LinkedIn",
            published_at="2026-02-15T00:00:00Z",
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="competitive_intel",
        ))
        print(f"  ✓ Source: {src_linkedin.title}")

        src_release = store.sources.create(Source(
            source_type=SourceType.PRESS_RELEASE,
            title="ServiceNow Xanadu Release Notes - IRM API Enhancements",
            url="https://docs.servicenow.com/xanadu/irm-api",
            publisher="ServiceNow",
            published_at="2026-02-20T00:00:00Z",
            collection_method=CollectionMethod.RSS_FEED,
            collector_agent="tech_radar",
        ))
        print(f"  ✓ Source: {src_release.title}")

        # 2. Create signals (with mandatory source links)
        print("\n── Creating Signals ──")
        sig_rfp = store.signals.create(
            Signal(
                signal_type=SignalType.RFP_POSTED,
                summary="Treasury posted RFI for GRC modernization services, specifically mentioning IRM and FISMA compliance automation.",
                entity_refs=json.dumps(["dept_treasury", "servicenow"]),
                domain_tags=json.dumps(["grc", "federal", "servicenow"]),
                confidence=Confidence.VERIFIED,
                confidence_rationale="Direct SAM.gov posting with solicitation number",
                extracted_by="procurement_scanner",
            ),
            sources=[SignalSource(
                signal_id="",
                source_id=src_sam.source_id,
                relevance=SourceRelevance.PRIMARY,
                excerpt="GRC modernization including FISMA compliance automation on ServiceNow",
            )]
        )
        print(f"  ✓ Signal [{sig_rfp.confidence}]: {sig_rfp.summary[:80]}...")

        sig_hiring = store.signals.create(
            Signal(
                signal_type=SignalType.HIRING_VELOCITY,
                summary="Deloitte posted 6 ServiceNow GRC-specific roles in a 3-week window (Feb 1-21).",
                entity_refs=json.dumps(["deloitte", "servicenow"]),
                domain_tags=json.dumps(["grc", "servicenow", "federal"]),
                confidence=Confidence.VERIFIED,
                confidence_rationale="Direct LinkedIn job posting URLs, counted manually",
                extracted_by="competitive_intel",
            ),
            sources=[SignalSource(
                signal_id="",
                source_id=src_linkedin.source_id,
                relevance=SourceRelevance.PRIMARY,
                excerpt="6 roles: 2 GRC Developer, 2 IRM Architect, 1 FISMA Analyst, 1 PM",
            )]
        )
        print(f"  ✓ Signal [{sig_hiring.confidence}]: {sig_hiring.summary[:80]}...")

        sig_api = store.signals.create(
            Signal(
                signal_type=SignalType.PRODUCT_RELEASE,
                summary="ServiceNow Xanadu release includes new IRM REST APIs for control test automation.",
                entity_refs=json.dumps(["servicenow"]),
                domain_tags=json.dumps(["servicenow", "grc", "api"]),
                confidence=Confidence.VERIFIED,
                confidence_rationale="Official ServiceNow release documentation",
                extracted_by="tech_radar",
            ),
            sources=[SignalSource(
                signal_id="",
                source_id=src_release.source_id,
                relevance=SourceRelevance.PRIMARY,
                excerpt="New REST endpoints for control_test and audit_engagement tables",
            )]
        )
        print(f"  ✓ Signal [{sig_api.confidence}]: {sig_api.summary[:80]}...")

        # 3. Orphan signal test
        print("\n── Integrity Test: Orphan Signal ──")
        try:
            store.signals.create(
                Signal(
                    signal_type=SignalType.BUDGET_SIGNAL,
                    summary="This signal has no sources and should be rejected.",
                    confidence=Confidence.SPECULATIVE,
                    confidence_rationale="No sources",
                    extracted_by="test",
                ),
                sources=[]  # NO SOURCES — should fail
            )
            print("  ✗ ERROR: Orphan signal was created!")
        except IntegrityError as e:
            print(f"  ✓ Blocked: {e}")

        # 4. Create correlation
        print("\n── Creating Correlation ──")
        corr = store.correlations.create(Correlation(
            signal_ids=json.dumps([sig_rfp.signal_id, sig_hiring.signal_id, sig_api.signal_id]),
            correlation_type=CorrelationType.DOMAIN_CONVERGENCE,
            hypothesis="Federal GRC modernization wave: Treasury is buying, Deloitte is staffing, and ServiceNow is enabling. Vectis has a positioning window.",
            strength="",  # auto-computed
            generated_by="qualifier_agent",
        ))
        print(f"  ✓ Correlation [{corr.strength}]: {corr.hypothesis[:80]}...")

        # 5. Human review
        print("\n── Human Review ──")
        store.correlations.review(corr.correlation_id, HumanVerdict.CONFIRMED,
            "Pattern checks out. SAM posting is real, Deloitte hiring matches known pipeline.")
        print(f"  ✓ Correlation reviewed: confirmed")

        # 6. Create opportunity (human only)
        print("\n── Creating Opportunity ──")
        opp = store.opportunities.create(Opportunity(
            title="Treasury GRC Modernization - NowForge + Vectis Consulting",
            lane=OpportunityLane.CORE_GRC,
            status=OpportunityStatus.RESEARCHING,
            source_correlation_ids=json.dumps([corr.correlation_id]),
            verification_checklist=json.dumps({
                "items": [
                    {"claim": "Treasury RFI exists on SAM.gov", "verified": True},
                    {"claim": "Deloitte is staffing for GRC work", "verified": True},
                    {"claim": "Xanadu IRM APIs support NowForge integration", "verified": False},
                    {"claim": "Treasury uses ServiceNow IRM", "verified": False},
                ]
            }),
            verification_score=0.0,  # auto-computed
            fit_score=0.85,
            estimated_value=150000,
            estimated_effort=EffortSize.LARGE,
            next_action="Pull full SAM.gov RFI document and verify ServiceNow requirement",
        ))
        print(f"  ✓ Opportunity: {opp.title}")
        print(f"    Verification score: {opp.verification_score} (2/4 items verified)")
        print(f"    Fit score: {opp.fit_score}")

        # 7. Non-human opportunity test
        print("\n── Integrity Test: AI-Created Opportunity ──")
        try:
            store.opportunities.create(Opportunity(
                title="This should be blocked",
                lane=OpportunityLane.INNOVATION,
                status=OpportunityStatus.WATCHING,
                source_correlation_ids=json.dumps([corr.correlation_id]),
                verification_checklist=json.dumps({"items": []}),
                verification_score=0.0,
                fit_score=0.5,
                created_by="qualifier_agent",  # NOT human — should fail
            ))
            print("  ✗ ERROR: Non-human opportunity was created!")
        except IntegrityError as e:
            print(f"  ✓ Blocked: {e}")

        # 8. Evidence chain traversal
        print("\n── Evidence Chain Traversal ──")
        chain = store.evidence.trace_opportunity(opp.opportunity_id)
        print(f"  Opportunity: {chain['title']}")
        for corr_data in chain["evidence_chain"]:
            print(f"    └─ Correlation [{corr_data['strength']}]: {corr_data['hypothesis'][:60]}...")
            for sig in corr_data["signals"]:
                print(f"       └─ Signal [{sig['confidence']}]: {sig['summary'][:55]}...")
                for src in sig["sources"]:
                    print(f"          └─ Source [{src['relevance']}]: {src['title'][:50]}...")
                    print(f"             URL: {src['url']}")

        # 9. Verification logging
        print("\n── Verification Log ──")
        store.verifications.log(Verification(
            target_type=VerificationTarget.SIGNAL,
            target_id=sig_rfp.signal_id,
            verified_by="human",
            result=VerificationResult.CONFIRMED,
            notes="Confirmed SAM.gov posting exists and matches signal description",
        ))
        store.verifications.log(Verification(
            target_type=VerificationTarget.SIGNAL,
            target_id=sig_hiring.signal_id,
            verified_by="human",
            result=VerificationResult.CONFIRMED,
            notes="Verified 6 LinkedIn postings directly",
        ))
        print("  ✓ Logged 2 verification records")

        # 10. Integrity audit
        print("\n── Integrity Audit ──")
        audit = store.integrity.run_integrity_audit()
        for k, v in audit.items():
            print(f"  {k}: {v}")

        # 11. Agent trust scores
        print("\n── Agent Trust Scores ──")
        trust = store.verifications.agent_trust_scores()
        for t in trust:
            score = t["trust_score"] if t["trust_score"] is not None else "N/A"
            print(f"  {t['agent']}: {score} ({t['total_signals']} signals, {t['verified_ok']} confirmed)")

        # Cleanup
        os.remove(db_path)
        print("\n" + "=" * 60)
        print("DEMO COMPLETE — All integrity rules enforced")
        print("=" * 60)


if __name__ == "__main__":
    demo()

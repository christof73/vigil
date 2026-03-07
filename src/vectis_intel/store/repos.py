"""
Vectis Market Intelligence — Repositories
==========================================
Data access layer for all entities.
"""

import json
import sqlite3
from dataclasses import asdict
from typing import Optional

from .models import (
    Source, Signal, SignalSource, Correlation, Opportunity, Verification,
    HumanVerdict, _now
)
from .integrity import IntegrityEngine, IntegrityError


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

    def get_by_url(self, url: str) -> Optional[dict]:
        """Find source by URL (for deduplication)."""
        row = self.conn.execute(
            "SELECT * FROM sources WHERE url = ?", (url,)
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

    def list_by_type(self, signal_type: str, limit: int = 50) -> list[dict]:
        """List signals filtered by signal_type."""
        rows = self.conn.execute(
            "SELECT * FROM signals WHERE signal_type = ? ORDER BY extracted_at DESC LIMIT ?",
            (signal_type, limit)
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

    def list_stale(self, limit: int = 50) -> list[dict]:
        """List signals past their expiration date."""
        rows = self.conn.execute(
            "SELECT * FROM v_stale_signals ORDER BY days_stale DESC LIMIT ?",
            (limit,)
        ).fetchall()
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

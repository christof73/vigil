"""
Vectis Market Intelligence — Integrity Engine
==============================================
Enforces provenance and anti-hallucination rules.
"""

import sqlite3
from .models import Confidence, CorrelationStrength, _now


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

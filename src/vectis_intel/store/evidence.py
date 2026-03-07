"""
Vectis Market Intelligence — Evidence Chain
============================================
Traverses the full evidence chain for any entity.
"""

import json
import sqlite3


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

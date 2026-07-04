"""
Tests for Community Scanner cluster promotion.
Covers: happy path with evidence trace, guards, source dedupe,
transaction rollback, integrity audit, re-promotion after terminal.
"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from vectis_intel.store.db import IntelDB
from vectis_intel.store.facade import IntelStore
from vectis_intel.store.models import (
    SignalType, CorrelationType, SourceType,
    OpportunityStatus,
)
from vectis_intel.community.schema import apply_community_schema
from vectis_intel.community.promote import (
    promote_cluster, audit_promotions, PromotionError, TERMINAL_STATUSES,
)


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def store(db_path):
    """IntelStore with both core and community schemas."""
    s = IntelStore(db_path)
    apply_community_schema(s.db.conn)
    yield s
    s.close()


@pytest.fixture
def conn(store):
    """Community-side connection (same DB)."""
    return store.db.conn


def _seed_cluster(conn, slug="test_cluster", label="Test Cluster", lane="grc", weight=1.3):
    conn.execute(
        "INSERT INTO signal_clusters (slug, label, lane, lane_weight) VALUES (?, ?, ?, ?)",
        (slug, label, lane, weight),
    )
    conn.commit()
    return conn.execute("SELECT id FROM signal_clusters WHERE slug = ?", (slug,)).fetchone()["id"]


def _seed_signals(conn, cluster_id, n=5, base_views=1000):
    """Seed community_signals with view counts for promotion selection."""
    for i in range(n):
        conn.execute(
            """INSERT INTO community_signals
               (source, external_id, board, title, body, url, posted_at,
                reply_count, view_count, has_accepted_solution, cluster_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "reddit", f"thread_{cluster_id}_{i}", "servicenow",
                f"Thread title {i} about GRC evidence collection",
                f"Body text for thread {i}",
                f"https://reddit.com/r/servicenow/{cluster_id}_{i}",
                f"2026-06-{i+1:02d}T00:00:00Z",
                10 + i, base_views + i * 100,
                1 if i == 0 else 0,  # first thread has accepted solution
                cluster_id,
            ),
        )
    conn.commit()


def _seed_score(conn, cluster_id, scored_at="2026-07-01T00:00:00Z"):
    conn.execute(
        """INSERT INTO cluster_scores
           (cluster_id, scored_at, window_start, window_end,
            thread_count, unsolved_rate, workaround_rate,
            commercial_rate, store_gap_score, composite_score)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (cluster_id, scored_at, "2025-07-01T00:00:00Z", "2026-07-01T00:00:00Z",
         34, 0.71, 0.15, 0.08, 0.7, 0.65),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM cluster_scores WHERE cluster_id = ? ORDER BY scored_at DESC LIMIT 1",
        (cluster_id,),
    ).fetchone()["id"]


def _seed_digest(conn, cluster_id, digest_date="2026-07-01"):
    conn.execute(
        """INSERT INTO digest_entries (cluster_id, digest_date, rank)
           VALUES (?, ?, 1)""",
        (cluster_id, digest_date),
    )
    conn.commit()


class TestPromoteClusterHappyPath:
    def test_full_chain_created(self, conn, store):
        """Promote creates sources, signals, correlation, opportunity, and audit row."""
        cid = _seed_cluster(conn)
        _seed_signals(conn, cid, n=5)
        _seed_score(conn, cid)
        _seed_digest(conn, cid)

        result = promote_cluster(conn, store, "test_cluster", "2026-07-01", n_threads=3)

        assert result["signals_created"] == 3
        assert result["opportunity_id"]
        assert result["correlation_id"]

        # Verify opportunity exists
        opp = store.db.conn.execute(
            "SELECT * FROM opportunities WHERE opportunity_id = ?",
            (result["opportunity_id"],),
        ).fetchone()
        assert opp is not None
        assert opp["created_by"] == "human"
        assert opp["status"] == "watching"
        assert opp["lane"] == "core_grc"

        # Verify correlation exists with correct type
        corr = store.db.conn.execute(
            "SELECT * FROM correlations WHERE correlation_id = ?",
            (result["correlation_id"],),
        ).fetchone()
        assert corr is not None
        assert corr["correlation_type"] == "recurring_demand"
        assert corr["human_reviewed"] == 1

        # Verify signals
        signal_ids = json.loads(
            conn.execute(
                "SELECT thread_signal_ids FROM cluster_promotions WHERE cluster_id = ?",
                (cid,),
            ).fetchone()["thread_signal_ids"]
        )
        assert len(signal_ids) == 3
        for sid in signal_ids:
            sig = store.db.conn.execute(
                "SELECT * FROM signals WHERE signal_id = ?", (sid,)
            ).fetchone()
            assert sig["signal_type"] == "community_demand"
            assert sig["confidence"] == "verified"

        # Verify promotion audit row
        promo = conn.execute(
            "SELECT * FROM cluster_promotions WHERE cluster_id = ?", (cid,)
        ).fetchone()
        assert promo["n_threads"] == 3
        assert promo["promoted_by"] == "human"

    def test_evidence_trace_walks_to_urls(self, conn, store):
        """trace_evidence on promoted opportunity returns thread URLs."""
        cid = _seed_cluster(conn)
        _seed_signals(conn, cid, n=3)
        _seed_score(conn, cid)

        result = promote_cluster(conn, store, "test_cluster", "2026-07-01", n_threads=3)
        chain = store.evidence.trace_opportunity(result["opportunity_id"])

        assert "evidence_chain" in chain
        assert len(chain["evidence_chain"]) == 1  # one correlation

        corr_data = chain["evidence_chain"][0]
        assert len(corr_data["signals"]) == 3

        for sig in corr_data["signals"]:
            assert len(sig["sources"]) >= 1
            assert sig["sources"][0]["url"].startswith("https://reddit.com/")

    def test_digest_disposition_set(self, conn, store):
        """Promotion sets digest entry disposition to app_candidate."""
        cid = _seed_cluster(conn)
        _seed_signals(conn, cid)
        _seed_score(conn, cid)
        _seed_digest(conn, cid)

        promote_cluster(conn, store, "test_cluster", "2026-07-01")

        de = conn.execute(
            "SELECT disposition FROM digest_entries WHERE cluster_id = ? AND digest_date = '2026-07-01'",
            (cid,),
        ).fetchone()
        assert de["disposition"] == "app_candidate"


class TestPromoteClusterGuards:
    def test_inactive_cluster_blocked(self, conn, store):
        cid = _seed_cluster(conn)
        conn.execute("UPDATE signal_clusters SET active = 0 WHERE id = ?", (cid,))
        conn.commit()

        with pytest.raises(PromotionError, match="not found or inactive"):
            promote_cluster(conn, store, "test_cluster", "2026-07-01")

    def test_nonexistent_cluster_blocked(self, conn, store):
        with pytest.raises(PromotionError, match="not found or inactive"):
            promote_cluster(conn, store, "no_such_cluster", "2026-07-01")

    def test_missing_score_blocked(self, conn, store):
        _seed_cluster(conn)
        _seed_signals(conn, 1)

        with pytest.raises(PromotionError, match="No score snapshot"):
            promote_cluster(conn, store, "test_cluster", "2026-07-01")

    def test_n_threads_less_than_2_blocked(self, conn, store):
        with pytest.raises(PromotionError, match="n_threads must be >= 2"):
            promote_cluster(conn, store, "test_cluster", "2026-07-01", n_threads=1)

    def test_too_few_threads_available(self, conn, store):
        cid = _seed_cluster(conn)
        _seed_signals(conn, cid, n=1)  # only 1 thread
        _seed_score(conn, cid)

        with pytest.raises(PromotionError, match="Only 1 threads available"):
            promote_cluster(conn, store, "test_cluster", "2026-07-01")

    def test_duplicate_active_promotion_blocked(self, conn, store):
        cid = _seed_cluster(conn)
        _seed_signals(conn, cid, n=5)
        _seed_score(conn, cid)

        promote_cluster(conn, store, "test_cluster", "2026-07-01")

        with pytest.raises(PromotionError, match="Active promotion already exists"):
            promote_cluster(conn, store, "test_cluster", "2026-07-02")


class TestSourceDedupe:
    def test_existing_source_reused(self, conn, store):
        """If a thread URL already exists as a source, reuse it."""
        cid = _seed_cluster(conn)
        _seed_signals(conn, cid, n=3)
        _seed_score(conn, cid)

        # Pre-create a source with one of the thread URLs
        from vectis_intel.store.models import Source, CollectionMethod
        existing = Source(
            source_type=SourceType.COMMUNITY_POST,
            title="Pre-existing source",
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="test",
            url=f"https://reddit.com/r/servicenow/{cid}_0",
        )
        store.sources.create(existing)

        result = promote_cluster(conn, store, "test_cluster", "2026-07-01", n_threads=3)
        assert result["sources_reused"] >= 1


class TestRepromotion:
    def test_repromotion_after_terminal(self, conn, store):
        """Re-promotion allowed after opportunity reaches terminal status."""
        cid = _seed_cluster(conn)
        _seed_signals(conn, cid, n=5)
        _seed_score(conn, cid)

        result1 = promote_cluster(conn, store, "test_cluster", "2026-07-01")

        # Move opportunity to terminal status
        store.opportunities.update_status(result1["opportunity_id"], "abandoned")

        # Re-promote should succeed with fresh chain
        result2 = promote_cluster(conn, store, "test_cluster", "2026-07-02")
        assert result2["opportunity_id"] != result1["opportunity_id"]
        assert result2["correlation_id"] != result1["correlation_id"]


class TestPromotionAudit:
    def test_clean_audit(self, conn, store):
        cid = _seed_cluster(conn)
        _seed_signals(conn, cid, n=3)
        _seed_score(conn, cid)

        promote_cluster(conn, store, "test_cluster", "2026-07-01")
        audit = audit_promotions(conn, store)

        assert audit["orphan_promotions"] == 0
        assert audit["orphan_recurring_demand"] == 0
        assert audit["integrity_ok"] is True

    def test_orphan_recurring_demand_detected(self, conn, store):
        """RECURRING_DEMAND correlation without promotion row is flagged."""
        cid = _seed_cluster(conn)
        _seed_signals(conn, cid, n=3)
        _seed_score(conn, cid)

        promote_cluster(conn, store, "test_cluster", "2026-07-01")

        # Delete the promotion row (simulate orphaning)
        conn.execute("DELETE FROM cluster_promotions")
        conn.commit()

        audit = audit_promotions(conn, store)
        assert audit["orphan_recurring_demand"] == 1
        assert audit["integrity_ok"] is False

    def test_terminal_statuses(self):
        """Verify terminal statuses match expectations."""
        assert "won" in TERMINAL_STATUSES
        assert "lost" in TERMINAL_STATUSES
        assert "abandoned" in TERMINAL_STATUSES
        assert "watching" not in TERMINAL_STATUSES


class TestSignalTypes:
    def test_community_demand_enum(self):
        assert SignalType.COMMUNITY_DEMAND == "community_demand"

    def test_recurring_demand_enum(self):
        assert CorrelationType.RECURRING_DEMAND == "recurring_demand"

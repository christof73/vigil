"""
Tests for Community Scanner scorer.
Covers: normalization, NULL store_gap handling, empty window,
composite calculation, lane weight application, outlier override.
"""

import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pytest

from vectis_intel.community.schema import apply_community_schema
from vectis_intel.community.config import TaxonomyManager
from vectis_intel.community.score import score_clusters, _compute_cluster_stats, get_outlier_slugs


@pytest.fixture
def db():
    """Temporary SQLite DB with community schema applied."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    apply_community_schema(conn)
    yield conn
    conn.close()
    os.unlink(path)


@pytest.fixture
def taxonomy(tmp_path):
    """Minimal taxonomy for testing."""
    yaml_content = """
config:
  min_keyword_hits: 2
  large_code_block_lines: 30
  window_months: 12
  commercial_keywords: [consultant]
  scoring_weights:
    thread_count_norm: 0.30
    unsolved_rate: 0.20
    workaround_rate: 0.20
    commercial_rate: 0.15
    store_gap_score: 0.15
  outlier_override:
    top_n: 2
  content_candidate:
    min_views: 500
    require_unsolved: true
lanes:
  grc: {weight: 1.3}
  platform_utility: {weight: 1.0}
  secops: {weight: 1.0}
  hrsd: {weight: 0.9}
  itsm: {weight: 0.7}
  other: {weight: 0.6}
clusters:
  - slug: test_cluster_a
    label: Test Cluster A
    lane: grc
    keywords: [test, alpha]
  - slug: test_cluster_b
    label: Test Cluster B
    lane: platform_utility
    keywords: [beta, bravo]
  - slug: test_cluster_c
    label: Test Cluster C
    lane: itsm
    keywords: [gamma, charlie]
"""
    p = tmp_path / "taxonomy.yaml"
    p.write_text(yaml_content)
    return TaxonomyManager(str(p))


def _seed_cluster(conn, slug, label, lane, lane_weight):
    conn.execute(
        "INSERT INTO signal_clusters (slug, label, lane, lane_weight) VALUES (?, ?, ?, ?)",
        (slug, label, lane, lane_weight),
    )
    conn.commit()
    return conn.execute("SELECT id FROM signal_clusters WHERE slug = ?", (slug,)).fetchone()["id"]


def _seed_signal(conn, cluster_id, posted_at, accepted=False, large_code=False, commercial=0):
    conn.execute(
        """INSERT INTO community_signals
           (source, external_id, title, url, posted_at, cluster_id,
            has_accepted_solution, has_large_code_block, commercial_hits)
           VALUES ('reddit', ?, 'test', 'http://test', ?, ?, ?, ?, ?)""",
        (f"id_{posted_at}_{cluster_id}", posted_at, cluster_id,
         int(accepted), int(large_code), commercial),
    )


class TestComputeClusterStats:
    def test_basic_stats(self, db):
        cid = _seed_cluster(db, "c1", "Cluster 1", "grc", 1.3)
        _seed_signal(db, cid, "2026-06-01T00:00:00Z", accepted=True)
        _seed_signal(db, cid, "2026-06-02T00:00:00Z", accepted=False, large_code=True)
        _seed_signal(db, cid, "2026-06-03T00:00:00Z", commercial=2)
        _seed_signal(db, cid, "2026-06-04T00:00:00Z")

        stats = _compute_cluster_stats(db, cid, "2026-01-01T00:00:00Z", "2026-12-31T00:00:00Z")
        assert stats is not None
        assert stats["thread_count"] == 4
        assert stats["unsolved_rate"] == 0.75  # 3/4 unsolved
        assert stats["workaround_rate"] == 0.25  # 1/4 has code
        assert stats["commercial_rate"] == 0.25  # 1/4 has commercial

    def test_empty_window(self, db):
        cid = _seed_cluster(db, "c1", "Cluster 1", "grc", 1.3)
        stats = _compute_cluster_stats(db, cid, "2026-01-01T00:00:00Z", "2026-12-31T00:00:00Z")
        assert stats is None

    def test_window_filtering(self, db):
        cid = _seed_cluster(db, "c1", "Cluster 1", "grc", 1.3)
        _seed_signal(db, cid, "2025-01-01T00:00:00Z")  # outside window
        _seed_signal(db, cid, "2026-06-01T00:00:00Z")  # inside window

        stats = _compute_cluster_stats(db, cid, "2026-01-01T00:00:00Z", "2026-12-31T00:00:00Z")
        assert stats["thread_count"] == 1


class TestScoreClusters:
    def test_scoring_with_lane_weight(self, db, taxonomy):
        cid = _seed_cluster(db, "test_cluster_a", "Test A", "grc", 1.3)
        for i in range(10):
            _seed_signal(db, cid, f"2026-06-{i+1:02d}T00:00:00Z")

        as_of = datetime(2026, 7, 1, tzinfo=timezone.utc)
        result = score_clusters(db, taxonomy, as_of=as_of)
        assert result["scored"] == 1

        score_row = db.execute(
            "SELECT * FROM cluster_scores WHERE cluster_id = ?", (cid,)
        ).fetchone()
        assert score_row is not None
        assert score_row["thread_count"] == 10
        # Composite should be > 0 due to lane_weight * factors
        assert score_row["composite_score"] > 0

    def test_null_store_gap_uses_half(self, db, taxonomy):
        """NULL store_gap_score should be treated as 0.5."""
        cid = _seed_cluster(db, "test_cluster_a", "Test A", "grc", 1.3)
        _seed_signal(db, cid, "2026-06-01T00:00:00Z")

        as_of = datetime(2026, 7, 1, tzinfo=timezone.utc)
        score_clusters(db, taxonomy, as_of=as_of)

        row = db.execute(
            "SELECT store_gap_score FROM cluster_scores WHERE cluster_id = ?", (cid,)
        ).fetchone()
        # NULL in DB because 0.5 is the unknown default, not a real score
        assert row["store_gap_score"] is None

    def test_no_active_clusters(self, db, taxonomy):
        as_of = datetime(2026, 7, 1, tzinfo=timezone.utc)
        result = score_clusters(db, taxonomy, as_of=as_of)
        assert result["scored"] == 0

    def test_empty_cluster_skipped(self, db, taxonomy):
        _seed_cluster(db, "test_cluster_a", "Test A", "grc", 1.3)
        # No signals for this cluster
        as_of = datetime(2026, 7, 1, tzinfo=timezone.utc)
        result = score_clusters(db, taxonomy, as_of=as_of)
        assert result["skipped_empty"] == 1
        assert result["scored"] == 0

    def test_append_only(self, db, taxonomy):
        """Running scoring twice should create two score rows."""
        cid = _seed_cluster(db, "test_cluster_a", "Test A", "grc", 1.3)
        _seed_signal(db, cid, "2026-06-01T00:00:00Z")

        t1 = datetime(2026, 7, 1, tzinfo=timezone.utc)
        t2 = datetime(2026, 7, 2, tzinfo=timezone.utc)
        score_clusters(db, taxonomy, as_of=t1)
        score_clusters(db, taxonomy, as_of=t2)

        count = db.execute(
            "SELECT COUNT(*) as cnt FROM cluster_scores WHERE cluster_id = ?", (cid,)
        ).fetchone()["cnt"]
        assert count == 2

    def test_normalization_across_clusters(self, db, taxonomy):
        """thread_count_norm should be relative to max cluster."""
        cid_a = _seed_cluster(db, "test_cluster_a", "Test A", "grc", 1.3)
        cid_b = _seed_cluster(db, "test_cluster_b", "Test B", "platform_utility", 1.0)

        # A gets 10 threads, B gets 5
        for i in range(10):
            _seed_signal(db, cid_a, f"2026-06-{i+1:02d}T00:00:00Z")
        for i in range(5):
            _seed_signal(db, cid_b, f"2026-06-{i+1:02d}T00:00:00Z")

        as_of = datetime(2026, 7, 1, tzinfo=timezone.utc)
        score_clusters(db, taxonomy, as_of=as_of)

        score_a = db.execute(
            "SELECT composite_score FROM cluster_scores WHERE cluster_id = ?", (cid_a,)
        ).fetchone()["composite_score"]
        score_b = db.execute(
            "SELECT composite_score FROM cluster_scores WHERE cluster_id = ?", (cid_b,)
        ).fetchone()["composite_score"]

        # A should score higher (more threads, higher lane weight)
        assert score_a > score_b

    def test_outlier_slugs_returned(self, db, taxonomy):
        """score_clusters should return outlier_slugs based on thread_count × unsolved_rate."""
        cid_a = _seed_cluster(db, "test_cluster_a", "Test A", "grc", 1.3)
        cid_b = _seed_cluster(db, "test_cluster_b", "Test B", "platform_utility", 1.0)
        cid_c = _seed_cluster(db, "test_cluster_c", "Test C", "itsm", 0.7)

        # A: 5 threads, all unsolved → raw metric = 5 * 1.0 = 5
        for i in range(5):
            _seed_signal(db, cid_a, f"2026-06-{i+1:02d}T00:00:00Z")
        # B: 10 threads, half solved → raw metric = 10 * 0.5 = 5
        for i in range(10):
            _seed_signal(db, cid_b, f"2026-06-{i+1:02d}T00:00:00Z", accepted=(i < 5))
        # C: 20 threads, all unsolved → raw metric = 20 * 1.0 = 20 (highest)
        for i in range(20):
            _seed_signal(db, cid_c, f"2026-06-{i+1:02d}T00:00:00Z")

        as_of = datetime(2026, 7, 1, tzinfo=timezone.utc)
        result = score_clusters(db, taxonomy, as_of=as_of)

        assert "outlier_slugs" in result
        # C should be first (highest raw metric), despite low ITSM lane weight
        assert result["outlier_slugs"][0] == "test_cluster_c"
        assert len(result["outlier_slugs"]) == 2  # top_n=2 in test taxonomy

    def test_new_lanes_accepted(self, db, taxonomy):
        """secops and hrsd lanes should be accepted by schema."""
        cid_s = _seed_cluster(db, "secops_test", "SecOps Test", "secops", 1.0)
        cid_h = _seed_cluster(db, "hrsd_test", "HRSD Test", "hrsd", 0.9)
        assert cid_s > 0
        assert cid_h > 0


class TestGetOutlierSlugs:
    def test_returns_top_n(self, db, taxonomy):
        cid_a = _seed_cluster(db, "test_cluster_a", "A", "grc", 1.3)
        cid_b = _seed_cluster(db, "test_cluster_b", "B", "platform_utility", 1.0)

        for i in range(10):
            _seed_signal(db, cid_a, f"2026-06-{i+1:02d}T00:00:00Z")
        for i in range(3):
            _seed_signal(db, cid_b, f"2026-06-{i+1:02d}T00:00:00Z")

        as_of = datetime(2026, 7, 1, tzinfo=timezone.utc)
        score_clusters(db, taxonomy, as_of=as_of)

        slugs = get_outlier_slugs(db, top_n=1)
        assert len(slugs) == 1
        assert slugs[0] == "test_cluster_a"  # higher thread_count * unsolved_rate

    def test_empty_scores(self, db):
        slugs = get_outlier_slugs(db, top_n=3)
        assert slugs == []

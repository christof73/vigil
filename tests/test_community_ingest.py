"""
Tests for Community Scanner ingest layer.
Fixture-based parsing tests — no live API calls.
"""

import os
import sqlite3
import tempfile
import xml.etree.ElementTree as ET

import pytest

from vectis_intel.community.schema import apply_community_schema
from vectis_intel.community.config import TaxonomyManager
from vectis_intel.community.ingest.base import upsert_signal, get_watermark, set_watermark
from vectis_intel.community.ingest.sn_community import _parse_rss_feed, _parse_rss_item


@pytest.fixture
def db():
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
    yaml_content = """
config:
  min_keyword_hits: 2
  large_code_block_lines: 30
  commercial_keywords: [consultant, paid solution]
  window_months: 12
  scoring_weights:
    thread_count_norm: 0.30
    unsolved_rate: 0.20
    workaround_rate: 0.20
    commercial_rate: 0.15
    store_gap_score: 0.15
lanes:
  grc: {weight: 1.5}
clusters:
  - slug: test_cluster
    label: Test
    lane: grc
    keywords: [evidence request, attestation]
"""
    p = tmp_path / "taxonomy.yaml"
    p.write_text(yaml_content)
    return TaxonomyManager(str(p))


# ── Watermark tracking ──────────────────────────────────────

class TestWatermark:
    def test_get_none_initially(self, db):
        assert get_watermark(db, "reddit") is None

    def test_set_and_get(self, db):
        set_watermark(db, "reddit", "2026-06-01T00:00:00Z", "abc123")
        assert get_watermark(db, "reddit") == "2026-06-01T00:00:00Z"

    def test_update_watermark(self, db):
        set_watermark(db, "reddit", "2026-06-01T00:00:00Z")
        set_watermark(db, "reddit", "2026-06-02T00:00:00Z")
        assert get_watermark(db, "reddit") == "2026-06-02T00:00:00Z"


# ── Upsert signal ───────────────────────────────────────────

class TestUpsertSignal:
    def test_insert(self, db, taxonomy):
        # Seed a cluster for classification
        db.execute(
            "INSERT INTO signal_clusters (slug, label, lane, lane_weight) VALUES ('test_cluster', 'Test', 'grc', 1.5)"
        )
        db.commit()

        action = upsert_signal(
            db, taxonomy,
            source="reddit",
            external_id="post_123",
            board="servicenow",
            title="evidence request attestation question",
            body="Need help with evidence request and attestation",
            url="https://reddit.com/r/servicenow/123",
            posted_at="2026-06-01T00:00:00Z",
            reply_count=5,
        )
        assert action == "inserted"

        row = db.execute("SELECT * FROM community_signals WHERE external_id = 'post_123'").fetchone()
        assert row is not None
        assert row["source"] == "reddit"
        assert row["reply_count"] == 5
        assert row["cluster_id"] is not None  # should be classified

    def test_update_on_conflict(self, db, taxonomy):
        upsert_signal(
            db, taxonomy,
            source="reddit", external_id="post_123",
            board="servicenow", title="test", body=None,
            url="https://test.com", posted_at="2026-06-01T00:00:00Z",
            reply_count=0,
        )
        db.commit()

        action = upsert_signal(
            db, taxonomy,
            source="reddit", external_id="post_123",
            board="servicenow", title="test", body=None,
            url="https://test.com", posted_at="2026-06-01T00:00:00Z",
            reply_count=10, view_count=500,
        )
        assert action == "updated"

        row = db.execute("SELECT * FROM community_signals WHERE external_id = 'post_123'").fetchone()
        assert row["reply_count"] == 10
        assert row["view_count"] == 500

    def test_dedupe_different_sources(self, db, taxonomy):
        """Same external_id from different sources = two rows."""
        upsert_signal(
            db, taxonomy,
            source="reddit", external_id="123",
            board="sn", title="t", body=None,
            url="https://r.com", posted_at="2026-06-01T00:00:00Z",
        )
        upsert_signal(
            db, taxonomy,
            source="stackoverflow", external_id="123",
            board="sn", title="t", body=None,
            url="https://so.com", posted_at="2026-06-01T00:00:00Z",
        )
        db.commit()

        count = db.execute("SELECT COUNT(*) as cnt FROM community_signals").fetchone()["cnt"]
        assert count == 2

    def test_commercial_hits_detected(self, db, taxonomy):
        upsert_signal(
            db, taxonomy,
            source="reddit", external_id="com1",
            board="sn", title="Need a consultant for paid solution",
            body=None, url="https://test.com",
            posted_at="2026-06-01T00:00:00Z",
        )
        db.commit()

        row = db.execute("SELECT commercial_hits FROM community_signals WHERE external_id = 'com1'").fetchone()
        assert row["commercial_hits"] == 2


# ── RSS parser ───────────────────────────────────────────────

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>ServiceNow Community</title>
    <item>
      <guid>thread-001</guid>
      <title>How to set up GRC evidence collection</title>
      <link>https://community.servicenow.com/thread/001</link>
      <pubDate>Mon, 01 Jun 2026 12:00:00 GMT</pubDate>
      <description>I need help setting up evidence collection...</description>
    </item>
    <item>
      <guid>thread-002</guid>
      <title>Update set collision during promotion</title>
      <link>https://community.servicenow.com/thread/002</link>
      <pubDate>Tue, 02 Jun 2026 14:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


class TestRSSParser:
    def test_parse_items(self):
        items = _parse_rss_feed(SAMPLE_RSS)
        assert len(items) == 2

    def test_item_fields(self):
        items = _parse_rss_feed(SAMPLE_RSS)
        first = items[0]
        assert first.external_id == "thread-001"
        assert first.title == "How to set up GRC evidence collection"
        assert first.url == "https://community.servicenow.com/thread/001"
        assert "2026-06-01" in first.posted_at
        assert first.body is not None

    def test_item_without_body(self):
        items = _parse_rss_feed(SAMPLE_RSS)
        second = items[1]
        assert second.body is None  # No description element

    def test_missing_required_fields(self):
        bad_rss = """<?xml version="1.0"?>
        <rss><channel><item><guid>x</guid></item></channel></rss>"""
        items = _parse_rss_feed(bad_rss)
        assert len(items) == 0  # Missing title and link

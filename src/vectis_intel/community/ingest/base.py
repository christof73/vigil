"""
Community Scanner — Ingestion Base
==================================
Shared utilities for all ingesters: normalized dict format, dedup upsert,
watermark tracking, and derived-field computation.
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from ..classify import classify, classify_signal, has_large_code_block, count_commercial_hits
from ..config import TaxonomyManager

logger = logging.getLogger("vectis_intel.community.ingest")


@dataclass
class IngestResult:
    """Summary of an ingestion run."""
    source: str
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_watermark(conn: sqlite3.Connection, source: str) -> Optional[str]:
    """Get the last-seen posted_at timestamp for a source."""
    row = conn.execute(
        "SELECT last_posted FROM ingest_state WHERE source = ?", (source,)
    ).fetchone()
    return row["last_posted"] if row else None


def set_watermark(conn: sqlite3.Connection, source: str, last_posted: str, last_id: Optional[str] = None) -> None:
    """Update watermark for a source."""
    conn.execute(
        """INSERT INTO ingest_state (source, last_posted, last_id, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(source) DO UPDATE SET
               last_posted = excluded.last_posted,
               last_id = COALESCE(excluded.last_id, last_id),
               updated_at = excluded.updated_at""",
        (source, last_posted, last_id, _now_iso()),
    )
    conn.commit()


def upsert_signal(
    conn: sqlite3.Connection,
    taxonomy: TaxonomyManager,
    *,
    source: str,
    external_id: str,
    board: Optional[str],
    title: str,
    body: Optional[str],
    url: str,
    posted_at: str,
    reply_count: int = 0,
    view_count: Optional[int] = None,
    has_accepted_solution: bool = False,
) -> str:
    """
    Insert or update a community_signals row.

    On conflict (source, external_id): update mutable fields only.
    Computes derived fields (code block detection, commercial hits, classification)
    at ingest time.

    Returns:
        'inserted' or 'updated'
    """
    large_code = has_large_code_block(body, taxonomy.large_code_block_lines)
    commercial = count_commercial_hits(title, body, taxonomy.commercial_keywords)

    # Classify
    slug = classify(title, body, taxonomy.clusters, taxonomy.min_keyword_hits)
    cluster_id = None
    if slug:
        row = conn.execute(
            "SELECT id FROM signal_clusters WHERE slug = ?", (slug,)
        ).fetchone()
        if row:
            cluster_id = row["id"]

    # Check for existing
    existing = conn.execute(
        "SELECT id FROM community_signals WHERE source = ? AND external_id = ?",
        (source, external_id),
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE community_signals SET
                reply_count = ?, view_count = ?, has_accepted_solution = ?,
                has_large_code_block = ?, commercial_hits = ?,
                cluster_id = ?, updated_at = ?
               WHERE id = ?""",
            (
                reply_count, view_count, int(has_accepted_solution),
                int(large_code), commercial,
                cluster_id, _now_iso(),
                existing["id"],
            ),
        )
        return "updated"
    else:
        conn.execute(
            """INSERT INTO community_signals
               (source, external_id, board, title, body, url, posted_at,
                reply_count, view_count, has_accepted_solution,
                has_large_code_block, commercial_hits, cluster_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source, external_id, board, title, body, url, posted_at,
                reply_count, view_count, int(has_accepted_solution),
                int(large_code), commercial, cluster_id,
            ),
        )
        return "inserted"

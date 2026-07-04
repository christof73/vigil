"""
Community Scanner — Weekly Digest Generator
============================================
Top 10 clusters by latest composite, with delta vs prior digest.
Per cluster: 3 highest-view raw thread links.
Separate section: content_candidate-eligible clusters.
Uncategorized count + 5 sample titles.
Output format: JSON dict (matches procurement scanner MCP tool output).
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("vectis_intel.community.digest")


def _get_prior_scores(conn: sqlite3.Connection, digest_date: str) -> dict[int, float]:
    """Get most recent composite scores from the prior digest."""
    rows = conn.execute(
        """SELECT de.cluster_id, cs.composite_score
           FROM digest_entries de
           JOIN cluster_scores cs ON cs.cluster_id = de.cluster_id
           WHERE de.digest_date < ?
           GROUP BY de.cluster_id
           HAVING de.digest_date = MAX(de.digest_date)
           ORDER BY cs.scored_at DESC""",
        (digest_date,),
    ).fetchall()

    # For each cluster, get the score from the scoring run closest to that digest
    prior = {}
    for row in rows:
        cid = row["cluster_id"]
        if cid not in prior:
            prior[cid] = row["composite_score"]
    return prior


def _get_top_threads(
    conn: sqlite3.Connection,
    cluster_id: int,
    limit: int = 3,
) -> list[dict]:
    """Get highest-view threads for a cluster."""
    rows = conn.execute(
        """SELECT title, url, view_count, posted_at, source
           FROM community_signals
           WHERE cluster_id = ?
           ORDER BY COALESCE(view_count, 0) DESC, posted_at DESC
           LIMIT ?""",
        (cluster_id, limit),
    ).fetchall()
    return [
        {
            "title": r["title"],
            "url": r["url"],
            "view_count": r["view_count"],
            "posted_at": r["posted_at"],
            "source": r["source"],
        }
        for r in rows
    ]


def _get_uncategorized_stats(conn: sqlite3.Connection) -> dict:
    """Count uncategorized threads and sample titles."""
    count_row = conn.execute(
        "SELECT COUNT(*) as cnt FROM community_signals WHERE cluster_id IS NULL"
    ).fetchone()
    total = conn.execute("SELECT COUNT(*) as cnt FROM community_signals").fetchone()

    samples = conn.execute(
        """SELECT title, url, source FROM community_signals
           WHERE cluster_id IS NULL
           ORDER BY posted_at DESC LIMIT 5"""
    ).fetchall()

    total_count = total["cnt"] if total else 0
    uncat_count = count_row["cnt"] if count_row else 0

    return {
        "count": uncat_count,
        "total_signals": total_count,
        "percentage": round(uncat_count / total_count * 100, 1) if total_count > 0 else 0,
        "sample_titles": [
            {"title": s["title"], "url": s["url"], "source": s["source"]}
            for s in samples
        ],
    }


def generate_digest(
    conn: sqlite3.Connection,
    digest_date: Optional[str] = None,
    top_n: int = 10,
) -> dict:
    """
    Generate weekly digest.

    Args:
        conn: SQLite connection with community schema.
        digest_date: ISO date string (default: today).
        top_n: Number of top clusters to include.

    Returns:
        Digest dict with top clusters, content candidates,
        uncategorized stats, and metadata.
    """
    if digest_date is None:
        digest_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Get latest scores for active clusters
    top_clusters = conn.execute(
        """SELECT cs.*, sc.slug, sc.label, sc.lane, sc.lane_weight
           FROM cluster_scores cs
           JOIN signal_clusters sc ON sc.id = cs.cluster_id
           WHERE sc.active = 1
             AND cs.scored_at = (
                 SELECT MAX(cs2.scored_at) FROM cluster_scores cs2
                 WHERE cs2.cluster_id = cs.cluster_id
             )
           ORDER BY cs.composite_score DESC
           LIMIT ?""",
        (top_n,),
    ).fetchall()

    # Prior scores for delta computation
    prior_scores = _get_prior_scores(conn, digest_date)

    # Build digest entries
    entries = []
    for rank, cluster in enumerate(top_clusters, 1):
        cid = cluster["cluster_id"]
        current_score = cluster["composite_score"]
        prior = prior_scores.get(cid)
        delta = round(current_score - prior, 4) if prior is not None else None

        top_threads = _get_top_threads(conn, cid)

        entry = {
            "rank": rank,
            "cluster_slug": cluster["slug"],
            "cluster_label": cluster["label"],
            "lane": cluster["lane"],
            "composite_score": current_score,
            "score_delta": delta,
            "thread_count": cluster["thread_count"],
            "unsolved_rate": cluster["unsolved_rate"],
            "workaround_rate": cluster["workaround_rate"],
            "commercial_rate": cluster["commercial_rate"],
            "store_gap_score": cluster["store_gap_score"],
            "top_threads": top_threads,
        }
        entries.append(entry)

        # Write digest_entries row
        conn.execute(
            """INSERT OR REPLACE INTO digest_entries
               (cluster_id, digest_date, rank, score_delta)
               VALUES (?, ?, ?, ?)""",
            (cid, digest_date, rank, delta),
        )

    # Content candidates: high views + unsolved, regardless of composite rank
    content_candidates = conn.execute(
        """SELECT sc.slug, sc.label, cs.unsolved_rate, cs.thread_count,
                  cs.composite_score
           FROM cluster_scores cs
           JOIN signal_clusters sc ON sc.id = cs.cluster_id
           WHERE sc.active = 1
             AND cs.unsolved_rate > 0.6
             AND cs.thread_count >= 5
             AND cs.scored_at = (
                 SELECT MAX(cs2.scored_at) FROM cluster_scores cs2
                 WHERE cs2.cluster_id = cs.cluster_id
             )
           ORDER BY cs.unsolved_rate DESC, cs.thread_count DESC"""
    ).fetchall()

    content_section = [
        {
            "cluster_slug": c["slug"],
            "cluster_label": c["label"],
            "unsolved_rate": c["unsolved_rate"],
            "thread_count": c["thread_count"],
            "composite_score": c["composite_score"],
        }
        for c in content_candidates
    ]

    uncategorized = _get_uncategorized_stats(conn)

    conn.commit()

    digest = {
        "digest_date": digest_date,
        "top_clusters": entries,
        "content_candidates": content_section,
        "uncategorized": uncategorized,
        "metadata": {
            "total_clusters_scored": len(top_clusters),
            "content_candidate_count": len(content_section),
            "uncategorized_pct": uncategorized["percentage"],
        },
    }

    logger.info(
        f"Digest generated for {digest_date}: "
        f"{len(entries)} top clusters, "
        f"{len(content_section)} content candidates, "
        f"{uncategorized['percentage']}% uncategorized"
    )

    return digest

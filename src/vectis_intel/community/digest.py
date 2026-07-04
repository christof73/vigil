"""
Community Scanner — Weekly Digest Generator
============================================
Top 10 clusters by latest composite, with delta vs prior digest.
Per cluster: 3 highest-view raw thread links.
Outlier overrides: top-N by raw thread_count × unsolved_rate always surface.
Content candidates: lane-agnostic (min_views + unsolved from config).
Uncategorized count + 5 sample titles.
Output format: JSON dict (matches procurement scanner MCP tool output).
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from .config import TaxonomyManager
from .score import get_outlier_slugs

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


def _build_cluster_entry(conn, cluster_row, rank, prior_scores):
    """Build a single digest entry dict from a scored cluster row."""
    cid = cluster_row["cluster_id"]
    current_score = cluster_row["composite_score"]
    prior = prior_scores.get(cid)
    delta = round(current_score - prior, 4) if prior is not None else None

    return {
        "rank": rank,
        "cluster_slug": cluster_row["slug"],
        "cluster_label": cluster_row["label"],
        "lane": cluster_row["lane"],
        "composite_score": current_score,
        "score_delta": delta,
        "thread_count": cluster_row["thread_count"],
        "unsolved_rate": cluster_row["unsolved_rate"],
        "workaround_rate": cluster_row["workaround_rate"],
        "commercial_rate": cluster_row["commercial_rate"],
        "store_gap_score": cluster_row["store_gap_score"],
        "top_threads": _get_top_threads(conn, cid),
    }


def generate_digest(
    conn: sqlite3.Connection,
    taxonomy: TaxonomyManager,
    digest_date: Optional[str] = None,
    top_n: int = 10,
) -> dict:
    """
    Generate weekly digest.

    Args:
        conn: SQLite connection with community schema.
        taxonomy: Loaded taxonomy config (for outlier_top_n, content_candidate).
        digest_date: ISO date string (default: today).
        top_n: Number of top clusters to include by composite score.

    Returns:
        Digest dict with top clusters, outlier overrides, content candidates,
        uncategorized stats, and metadata.
    """
    if digest_date is None:
        digest_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Get latest scores for all active clusters (need full set for outlier merging)
    all_scored = conn.execute(
        """SELECT cs.*, sc.slug, sc.label, sc.lane, sc.lane_weight
           FROM cluster_scores cs
           JOIN signal_clusters sc ON sc.id = cs.cluster_id
           WHERE sc.active = 1
             AND cs.scored_at = (
                 SELECT MAX(cs2.scored_at) FROM cluster_scores cs2
                 WHERE cs2.cluster_id = cs.cluster_id
             )
           ORDER BY cs.composite_score DESC"""
    ).fetchall()

    prior_scores = _get_prior_scores(conn, digest_date)

    # Top-N by composite score
    top_clusters = all_scored[:top_n]
    top_slugs = {c["slug"] for c in top_clusters}

    # Outlier overrides: top-N by raw thread_count × unsolved_rate
    outlier_slugs_list = get_outlier_slugs(conn, taxonomy.outlier_top_n)
    outlier_slugs = set(outlier_slugs_list)

    # Find outliers not already in the top-N composite list
    outlier_additions = []
    scored_by_slug = {c["slug"]: c for c in all_scored}
    for slug in outlier_slugs_list:
        if slug not in top_slugs and slug in scored_by_slug:
            outlier_additions.append(scored_by_slug[slug])

    # Build entries: top-N first, then outlier additions
    entries = []
    rank = 1
    for cluster in top_clusters:
        entry = _build_cluster_entry(conn, cluster, rank, prior_scores)
        entry["outlier_override"] = cluster["slug"] in outlier_slugs
        entries.append(entry)

        conn.execute(
            """INSERT OR REPLACE INTO digest_entries
               (cluster_id, digest_date, rank, score_delta)
               VALUES (?, ?, ?, ?)""",
            (cluster["cluster_id"], digest_date, rank, entry["score_delta"]),
        )
        rank += 1

    for cluster in outlier_additions:
        entry = _build_cluster_entry(conn, cluster, rank, prior_scores)
        entry["outlier_override"] = True
        entries.append(entry)

        conn.execute(
            """INSERT OR REPLACE INTO digest_entries
               (cluster_id, digest_date, rank, score_delta)
               VALUES (?, ?, ?, ?)""",
            (cluster["cluster_id"], digest_date, rank, entry["score_delta"]),
        )
        rank += 1

    # Content candidates: lane-agnostic, config-driven (min_views + unsolved)
    min_views = taxonomy.content_min_views
    require_unsolved = taxonomy.content_require_unsolved

    content_query = """
        SELECT sc.slug, sc.label, sc.lane, cs.unsolved_rate, cs.thread_count,
               cs.composite_score, cs.cluster_id
        FROM cluster_scores cs
        JOIN signal_clusters sc ON sc.id = cs.cluster_id
        WHERE sc.active = 1
          AND cs.scored_at = (
              SELECT MAX(cs2.scored_at) FROM cluster_scores cs2
              WHERE cs2.cluster_id = cs.cluster_id
          )
    """

    # Find clusters with high-view unsolved threads
    if require_unsolved:
        content_query += " AND cs.unsolved_rate > 0.5"

    content_query += " ORDER BY cs.unsolved_rate DESC, cs.thread_count DESC"

    content_rows = conn.execute(content_query).fetchall()

    # Filter by min_views: check if cluster has threads exceeding view threshold
    content_section = []
    for c in content_rows:
        high_view_count = conn.execute(
            """SELECT COUNT(*) as cnt FROM community_signals
               WHERE cluster_id = ? AND COALESCE(view_count, 0) >= ?""",
            (c["cluster_id"], min_views),
        ).fetchone()["cnt"]

        if high_view_count > 0:
            content_section.append({
                "cluster_slug": c["slug"],
                "cluster_label": c["label"],
                "lane": c["lane"],
                "unsolved_rate": c["unsolved_rate"],
                "thread_count": c["thread_count"],
                "composite_score": c["composite_score"],
                "high_view_threads": high_view_count,
            })

    uncategorized = _get_uncategorized_stats(conn)

    conn.commit()

    digest = {
        "digest_date": digest_date,
        "top_clusters": entries,
        "outlier_overrides": outlier_slugs_list,
        "content_candidates": content_section,
        "uncategorized": uncategorized,
        "metadata": {
            "total_clusters_scored": len(all_scored),
            "top_n_by_composite": len(top_clusters),
            "outlier_additions": len(outlier_additions),
            "content_candidate_count": len(content_section),
            "uncategorized_pct": uncategorized["percentage"],
        },
    }

    logger.info(
        f"Digest generated for {digest_date}: "
        f"{len(entries)} entries ({len(outlier_additions)} outlier additions), "
        f"{len(content_section)} content candidates, "
        f"{uncategorized['percentage']}% uncategorized"
    )

    return digest

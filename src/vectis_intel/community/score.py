"""
Community Scanner — Monthly Scorer
==================================
Per active cluster, trailing 12-month window:

composite = lane_weight × Σ (weight_i × factor_i)

Factors:
  thread_count_norm  = cluster thread_count / max(thread_count across clusters)
  unsolved_rate      = 1 - (accepted_solution threads / total)
  workaround_rate    = threads with has_large_code_block / total
  commercial_rate    = threads with commercial_hits > 0 / total
  store_gap_score    = from vigil-store-crossref (NULL → 0.5, never 1.0)

v1.1 scoring scope rules:
  - Lane weights apply to app_candidate ranking only
  - Outlier override: top-N by raw thread_count × unsolved_rate always
    surface in digest regardless of lane-weighted rank
  - Content-candidate flagging is lane-agnostic (min_views + unsolved)

Weights from taxonomy.yaml config. Appends to cluster_scores (never overwrites).
"""

import logging
import sqlite3
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from typing import Optional

from .config import TaxonomyManager

logger = logging.getLogger("vectis_intel.community.score")


def _compute_cluster_stats(
    conn: sqlite3.Connection,
    cluster_id: int,
    window_start: str,
    window_end: str,
) -> Optional[dict]:
    """Compute raw stats for a single cluster within the window."""
    row = conn.execute(
        """SELECT
            COUNT(*) as thread_count,
            SUM(CASE WHEN has_accepted_solution = 1 THEN 1 ELSE 0 END) as solved_count,
            SUM(CASE WHEN has_large_code_block = 1 THEN 1 ELSE 0 END) as workaround_count,
            SUM(CASE WHEN commercial_hits > 0 THEN 1 ELSE 0 END) as commercial_count
           FROM community_signals
           WHERE cluster_id = ?
             AND posted_at >= ? AND posted_at < ?""",
        (cluster_id, window_start, window_end),
    ).fetchone()

    if not row or row["thread_count"] == 0:
        return None

    tc = row["thread_count"]
    return {
        "thread_count": tc,
        "unsolved_rate": 1.0 - (row["solved_count"] / tc),
        "workaround_rate": row["workaround_count"] / tc,
        "commercial_rate": row["commercial_count"] / tc,
    }


def score_clusters(
    conn: sqlite3.Connection,
    taxonomy: TaxonomyManager,
    as_of: Optional[datetime] = None,
) -> dict:
    """
    Run monthly scoring for all active clusters.

    Args:
        conn: SQLite connection with community schema.
        taxonomy: Loaded taxonomy config.
        as_of: Score as of this datetime (default: now).

    Returns:
        {"scored": int, "skipped_empty": int, "window": (start, end)}
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    window_months = taxonomy.window_months
    window_end = as_of.strftime("%Y-%m-%dT%H:%M:%SZ")
    window_start = (as_of - relativedelta(months=window_months)).strftime("%Y-%m-%dT%H:%M:%SZ")
    scored_at = window_end

    weights = taxonomy.scoring_weights

    # Get all active clusters
    clusters = conn.execute(
        "SELECT id, slug, lane, lane_weight FROM signal_clusters WHERE active = 1"
    ).fetchall()

    if not clusters:
        logger.warning("No active clusters to score")
        return {"scored": 0, "skipped_empty": 0, "window": (window_start, window_end)}

    # First pass: compute raw stats and find max thread count for normalization
    cluster_stats = {}
    max_thread_count = 0

    for cluster in clusters:
        stats = _compute_cluster_stats(conn, cluster["id"], window_start, window_end)
        if stats:
            cluster_stats[cluster["id"]] = stats
            if stats["thread_count"] > max_thread_count:
                max_thread_count = stats["thread_count"]

    # Second pass: compute composite scores and insert
    scored = 0
    skipped_empty = 0

    for cluster in clusters:
        cid = cluster["id"]
        stats = cluster_stats.get(cid)

        if stats is None:
            skipped_empty += 1
            continue

        # Normalize thread count
        thread_count_norm = stats["thread_count"] / max_thread_count if max_thread_count > 0 else 0

        # Get store_gap_score from most recent scoring run (if exists)
        prev_score = conn.execute(
            """SELECT store_gap_score FROM cluster_scores
               WHERE cluster_id = ? ORDER BY scored_at DESC LIMIT 1""",
            (cid,),
        ).fetchone()
        store_gap = prev_score["store_gap_score"] if prev_score and prev_score["store_gap_score"] is not None else 0.5

        # Composite = Σ(weight × factor)
        raw_composite = (
            weights.get("thread_count_norm", 0.30) * thread_count_norm
            + weights.get("unsolved_rate", 0.20) * stats["unsolved_rate"]
            + weights.get("workaround_rate", 0.20) * stats["workaround_rate"]
            + weights.get("commercial_rate", 0.15) * stats["commercial_rate"]
            + weights.get("store_gap_score", 0.15) * store_gap
        )

        # Apply lane weight
        composite = cluster["lane_weight"] * raw_composite

        conn.execute(
            """INSERT INTO cluster_scores
               (cluster_id, scored_at, window_start, window_end,
                thread_count, unsolved_rate, workaround_rate,
                commercial_rate, store_gap_score, composite_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cid, scored_at, window_start, window_end,
                stats["thread_count"],
                round(stats["unsolved_rate"], 4),
                round(stats["workaround_rate"], 4),
                round(stats["commercial_rate"], 4),
                store_gap if store_gap != 0.5 else None,  # preserve NULL semantics
                round(composite, 4),
            ),
        )
        scored += 1

    conn.commit()

    # Compute outlier overrides: top-N by raw thread_count × unsolved_rate (no lane weight)
    outlier_top_n = taxonomy.outlier_top_n
    outlier_candidates = []
    for cluster in clusters:
        cid = cluster["id"]
        stats = cluster_stats.get(cid)
        if stats is None:
            continue
        raw_metric = stats["thread_count"] * stats["unsolved_rate"]
        outlier_candidates.append((cluster["slug"], raw_metric))

    outlier_candidates.sort(key=lambda x: x[1], reverse=True)
    outlier_slugs = [slug for slug, _ in outlier_candidates[:outlier_top_n]]

    result = {
        "scored": scored,
        "skipped_empty": skipped_empty,
        "window": (window_start, window_end),
        "outlier_slugs": outlier_slugs,
    }
    logger.info(f"Scoring complete: {result}")
    return result


def get_outlier_slugs(
    conn: sqlite3.Connection,
    top_n: int = 3,
) -> list[str]:
    """
    Get top-N clusters by raw thread_count × unsolved_rate from latest scores.
    These clusters surface in the digest regardless of lane-weighted rank.
    """
    rows = conn.execute(
        """SELECT sc.slug, cs.thread_count, cs.unsolved_rate
           FROM cluster_scores cs
           JOIN signal_clusters sc ON sc.id = cs.cluster_id
           WHERE sc.active = 1
             AND cs.scored_at = (
                 SELECT MAX(cs2.scored_at) FROM cluster_scores cs2
                 WHERE cs2.cluster_id = cs.cluster_id
             )
           ORDER BY (cs.thread_count * cs.unsolved_rate) DESC
           LIMIT ?""",
        (top_n,),
    ).fetchall()
    return [r["slug"] for r in rows]


def update_store_gap(
    conn: sqlite3.Connection,
    cluster_slug: str,
    gap_score: float,
) -> bool:
    """
    Update store_gap_score for the latest score entry of a cluster.
    Called via CLI subcommand after manual vigil-store-crossref runs.

    Args:
        gap_score: 0.0 (saturated) to 1.0 (empty). Never set to 1.0 for
                   unknown — that's what NULL/0.5 is for.
    """
    cluster = conn.execute(
        "SELECT id FROM signal_clusters WHERE slug = ?", (cluster_slug,)
    ).fetchone()
    if not cluster:
        logger.warning(f"Cluster '{cluster_slug}' not found")
        return False

    updated = conn.execute(
        """UPDATE cluster_scores SET store_gap_score = ?
           WHERE cluster_id = ?
             AND scored_at = (SELECT MAX(scored_at) FROM cluster_scores WHERE cluster_id = ?)""",
        (gap_score, cluster["id"], cluster["id"]),
    ).rowcount

    conn.commit()
    return updated > 0

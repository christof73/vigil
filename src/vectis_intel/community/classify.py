"""
Community Scanner — Classifier
==============================
Pure-function keyword matcher. No LLM, no embeddings.

Rules:
  - Case-insensitive substring match against title + body
  - Thread matches a cluster if >= min_keyword_hits keywords hit
  - Ties: highest hit count wins; still tied → first in taxonomy order, log tie
  - Zero matches → None (uncategorized)
"""

import logging
import re
import sqlite3
from typing import Optional

logger = logging.getLogger("vectis_intel.community.classify")


def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    """Count how many distinct keywords appear in text (case-insensitive substring)."""
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


def classify(
    title: str,
    body: Optional[str],
    clusters: list[dict],
    min_keyword_hits: int = 2,
) -> Optional[str]:
    """
    Classify a thread against taxonomy clusters.

    Args:
        title: Thread title.
        body: Thread body (first post only). May be None.
        clusters: List of cluster dicts from taxonomy.yaml.
        min_keyword_hits: Minimum keyword matches to qualify.

    Returns:
        cluster slug, or None if uncategorized.
    """
    text = title
    if body:
        text = f"{title} {body}"

    best_slug: Optional[str] = None
    best_hits = 0
    tied = False

    for cluster in clusters:
        hits = _count_keyword_hits(text, cluster["keywords"])
        if hits >= min_keyword_hits:
            if hits > best_hits:
                best_slug = cluster["slug"]
                best_hits = hits
                tied = False
            elif hits == best_hits and best_slug is not None:
                tied = True
                # First in taxonomy order wins — don't update best_slug

    if tied:
        logger.info(
            f"Classification tie at {best_hits} hits, resolved to '{best_slug}' (first in taxonomy order)",
            extra={"title": title[:80]},
        )

    return best_slug


def has_large_code_block(body: Optional[str], threshold_lines: int = 30) -> bool:
    """Detect code blocks exceeding threshold lines in body text."""
    if not body:
        return False

    # Match fenced code blocks (```...```) or <pre>...</pre>
    fenced = re.findall(r"```[\s\S]*?```", body)
    for block in fenced:
        lines = block.strip().split("\n")
        if len(lines) - 2 >= threshold_lines:  # subtract opening/closing fence
            return True

    pre_blocks = re.findall(r"<pre[^>]*>[\s\S]*?</pre>", body, re.IGNORECASE)
    for block in pre_blocks:
        lines = block.strip().split("\n")
        if len(lines) - 2 >= threshold_lines:
            return True

    # Indented code blocks: 4+ consecutive lines starting with 4 spaces or tab
    indent_run = 0
    for line in body.split("\n"):
        if line.startswith("    ") or line.startswith("\t"):
            indent_run += 1
            if indent_run >= threshold_lines:
                return True
        else:
            indent_run = 0

    return False


def count_commercial_hits(title: str, body: Optional[str], keywords: list[str]) -> int:
    """Count commercial keyword matches in title + body."""
    text = title
    if body:
        text = f"{title} {body}"
    return _count_keyword_hits(text, keywords)


def classify_signal(
    conn: sqlite3.Connection,
    signal_id: int,
    title: str,
    body: Optional[str],
    clusters: list[dict],
    min_keyword_hits: int = 2,
) -> Optional[int]:
    """
    Classify a community_signals row and update its cluster_id.

    Returns:
        cluster_id (int) or None if uncategorized.
    """
    slug = classify(title, body, clusters, min_keyword_hits)
    if slug is None:
        conn.execute(
            "UPDATE community_signals SET cluster_id = NULL WHERE id = ?",
            (signal_id,),
        )
        return None

    row = conn.execute(
        "SELECT id FROM signal_clusters WHERE slug = ?", (slug,)
    ).fetchone()
    if row is None:
        logger.warning(f"Cluster slug '{slug}' not found in signal_clusters table")
        return None

    cluster_id = row["id"]
    conn.execute(
        "UPDATE community_signals SET cluster_id = ? WHERE id = ?",
        (cluster_id, signal_id),
    )
    return cluster_id


def reclassify_all(
    conn: sqlite3.Connection,
    clusters: list[dict],
    min_keyword_hits: int = 2,
) -> dict:
    """
    Re-run classifier over all community_signals rows.
    Use after taxonomy edits.

    Returns:
        {"classified": int, "uncategorized": int, "total": int}
    """
    rows = conn.execute("SELECT id, title, body FROM community_signals").fetchall()
    classified = 0
    uncategorized = 0

    for row in rows:
        cluster_id = classify_signal(
            conn, row["id"], row["title"], row["body"],
            clusters, min_keyword_hits,
        )
        if cluster_id is not None:
            classified += 1
        else:
            uncategorized += 1

    conn.commit()
    result = {"classified": classified, "uncategorized": uncategorized, "total": len(rows)}
    logger.info(f"Reclassification complete: {result}")
    return result

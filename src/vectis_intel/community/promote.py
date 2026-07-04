"""
Community Scanner — Cluster Promotion
=====================================
Turns a human `app_candidate` disposition into an Opportunity with
full provenance, bridging the community pipeline to the procurement
pipeline under the integrity engine and evidence chain guarantees.

Core design: threads are signals; the aggregate is a correlation hypothesis.
An aggregate stat ("34 threads, 71% unsolved") is a computation with no URL —
it cannot be a Signal without violating anti-hallucination. Instead:

    top-N threads  →  N × (Source + Signal + SignalSource)  [each URL-verifiable]
    pattern claim  →  1 × Correlation (hypothesis = factual stats template)
    pursuit        →  1 × Opportunity (created_by='human')
    audit          →  1 × cluster_promotions row
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from typing import Optional

from ..store.models import (
    Source, Signal, SignalSource, Correlation, Opportunity,
    SourceType, CollectionMethod, SignalType, Confidence,
    CorrelationType, SourceRelevance, OpportunityStatus, HumanVerdict,
    _uuid, _now,
)
from ..store.integrity import IntegrityError

logger = logging.getLogger("vectis_intel.community.promote")

# Terminal opportunity statuses — re-promotion allowed after these
TERMINAL_STATUSES = {"won", "lost", "abandoned"}

# Map community lanes to opportunity lanes
LANE_MAP = {
    "grc": "core_grc",
    "secops": "core_servicenow",
    "platform_utility": "core_servicenow",
    "hrsd": "core_servicenow",
    "itsm": "core_servicenow",
    "other": "core_servicenow",
}

DEFAULT_EXPIRY_MONTHS = 12


class PromotionError(Exception):
    """Raised when a promotion guard fails."""
    pass


def promote_cluster(
    conn: sqlite3.Connection,
    store,
    cluster_slug: str,
    digest_date: str,
    n_threads: int = 5,
    expiry_months: int = DEFAULT_EXPIRY_MONTHS,
) -> dict:
    """
    Promote a community cluster to the procurement pipeline.

    Creates N Sources + Signals, 1 Correlation, 1 Opportunity,
    and 1 cluster_promotions audit row in a single transaction.

    Args:
        conn: SQLite connection (community schema applied).
        store: IntelStore instance (for procurement-side writes).
        cluster_slug: Cluster to promote.
        digest_date: Digest date that surfaced this cluster.
        n_threads: Number of top threads to promote (min 2).
        expiry_months: Months before promoted signals expire.

    Returns:
        {"opportunity_id": str, "correlation_id": str, "signals_created": int,
         "sources_reused": int, "promotion_id": int}

    Raises:
        PromotionError: Guard failure (inactive cluster, missing scores, etc.)
        IntegrityError: Provenance violation.
    """
    if n_threads < 2:
        raise PromotionError("n_threads must be >= 2 (correlation requires >= 2 signals)")

    # ── Guard 1: cluster exists and is active ─────────────────
    cluster = conn.execute(
        "SELECT * FROM signal_clusters WHERE slug = ? AND active = 1",
        (cluster_slug,),
    ).fetchone()
    if not cluster:
        raise PromotionError(f"Cluster '{cluster_slug}' not found or inactive")

    cluster_id = cluster["id"]

    # ── Guard 2: latest score snapshot exists ─────────────────
    score_snapshot = conn.execute(
        """SELECT * FROM cluster_scores
           WHERE cluster_id = ? ORDER BY scored_at DESC LIMIT 1""",
        (cluster_id,),
    ).fetchone()
    if not score_snapshot:
        raise PromotionError(f"No score snapshot for cluster '{cluster_slug}' — run scoring first")

    # ── Guard 3: no active promotion for this cluster ─────────
    existing_promotions = conn.execute(
        "SELECT opportunity_id FROM cluster_promotions WHERE cluster_id = ?",
        (cluster_id,),
    ).fetchall()

    for promo in existing_promotions:
        opp = store.db.conn.execute(
            "SELECT status FROM opportunities WHERE opportunity_id = ?",
            (promo["opportunity_id"],),
        ).fetchone()
        if opp and opp["status"] not in TERMINAL_STATUSES:
            raise PromotionError(
                f"Active promotion already exists for '{cluster_slug}' "
                f"(opportunity {promo['opportunity_id']}, status={opp['status']}). "
                f"Close the existing opportunity before re-promoting."
            )

    # ── Step 3: select top threads ────────────────────────────
    threads = conn.execute(
        """SELECT * FROM community_signals
           WHERE cluster_id = ?
             AND posted_at >= ? AND posted_at < ?
           ORDER BY COALESCE(view_count, 0) DESC, reply_count DESC
           LIMIT ?""",
        (cluster_id, score_snapshot["window_start"], score_snapshot["window_end"], n_threads),
    ).fetchall()

    if len(threads) < 2:
        raise PromotionError(
            f"Only {len(threads)} threads available in scoring window — need at least 2"
        )

    actual_n = len(threads)
    now = _now()
    expires_at = (
        datetime.now(timezone.utc) + relativedelta(months=expiry_months)
    ).isoformat()

    # ── Steps 4-5: create sources, signals, correlation ───────
    signal_ids = []
    sources_reused = 0

    try:
        for thread in threads:
            # Step 4a: Source — dedupe by URL
            existing_source = store.sources.get_by_url(thread["url"])
            if existing_source:
                source_id = existing_source["source_id"]
                sources_reused += 1
            else:
                source = Source(
                    source_type=SourceType.COMMUNITY_POST,
                    title=thread["title"],
                    collection_method=CollectionMethod.API_AUTOMATED,
                    collector_agent="community_scanner",
                    url=thread["url"],
                    url_status="unchecked",
                    publisher=thread["source"],
                    published_at=thread["posted_at"],
                )
                store.sources.create(source)
                source_id = source.source_id

            # Step 4b: Signal
            views_str = f"{thread['view_count']} views" if thread["view_count"] else "views N/A"
            accepted = "yes" if thread["has_accepted_solution"] else "no"
            summary = (
                f"Community thread '{thread['title']}' ({thread['source']}/{thread['board'] or 'unknown'}), "
                f"posted {thread['posted_at']}, {thread['reply_count']} replies, {views_str}, "
                f"accepted solution: {accepted}."
            )

            signal = Signal(
                signal_type=SignalType.COMMUNITY_DEMAND,
                summary=summary,
                confidence=Confidence.VERIFIED,
                confidence_rationale="Thread directly observable at source URL",
                extracted_by="community_scanner",
                domain_tags=json.dumps([cluster["lane"]]),
                entity_refs=json.dumps([cluster_slug]),
                expires_at=expires_at,
            )

            # Step 4c: SignalSource
            signal_source = SignalSource(
                signal_id=signal.signal_id,
                source_id=source_id,
                relevance=SourceRelevance.PRIMARY,
                excerpt=thread["title"][:200],
            )

            store.signals.create(signal, [signal_source])
            signal_ids.append(signal.signal_id)

        # Step 5: Correlation
        unsolved_pct = f"{score_snapshot['unsolved_rate']:.0%}"
        workaround_pct = f"{score_snapshot['workaround_rate']:.0%}"
        store_gap = score_snapshot["store_gap_score"]
        store_gap_str = f"{store_gap:.2f}" if store_gap is not None else "unknown"

        hypothesis = (
            f"Cluster '{cluster['label']}' ({cluster['lane']}): "
            f"{score_snapshot['thread_count']} threads in trailing 12mo, "
            f"{unsolved_pct} unsolved, workaround_rate {workaround_pct}, "
            f"store_gap {store_gap_str}, composite {score_snapshot['composite_score']:.4f} "
            f"as of {score_snapshot['scored_at']}."
        )

        correlation = Correlation(
            signal_ids=json.dumps(signal_ids),
            correlation_type=CorrelationType.RECURRING_DEMAND,
            hypothesis=hypothesis,
            strength="weak",  # auto-computed by CorrelationRepo.create()
            generated_by="community_scanner",
        )
        correlation = store.correlations.create(correlation)

        # Auto-review: the human IS the gate by invoking this function
        store.correlations.review(
            correlation.correlation_id,
            HumanVerdict.CONFIRMED,
            notes=f"Auto-confirmed via cluster promotion of '{cluster_slug}'",
        )

        # Step 6: Opportunity
        opp_lane = LANE_MAP.get(cluster["lane"], "core_servicenow")
        checklist = {
            "items": [
                {"label": "Community demand verified", "verified": True},
                {"label": "Store gap assessed", "verified": store_gap is not None},
                {"label": "Competitor analysis complete", "verified": False},
                {"label": "Technical feasibility confirmed", "verified": False},
            ]
        }

        opportunity = Opportunity(
            title=f"Community demand: {cluster['label']}",
            lane=opp_lane,
            status=OpportunityStatus.WATCHING,
            source_correlation_ids=json.dumps([correlation.correlation_id]),
            verification_checklist=json.dumps(checklist),
            verification_score=0.0,  # auto-computed by OpportunityRepo
            fit_score=0.0,  # unscored — Qualifier's job
            created_by="human",
        )
        opportunity = store.opportunities.create(opportunity)

        # Step 7: set digest disposition
        conn.execute(
            """UPDATE digest_entries SET disposition = 'app_candidate'
               WHERE cluster_id = ? AND digest_date = ? AND disposition IS NULL""",
            (cluster_id, digest_date),
        )

        # Step 8: cluster_promotions audit row
        conn.execute(
            """INSERT INTO cluster_promotions
               (cluster_id, digest_date, score_snapshot_id, correlation_id,
                opportunity_id, thread_signal_ids, n_threads)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                cluster_id, digest_date, score_snapshot["id"],
                correlation.correlation_id, opportunity.opportunity_id,
                json.dumps(signal_ids), actual_n,
            ),
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    result = {
        "opportunity_id": opportunity.opportunity_id,
        "correlation_id": correlation.correlation_id,
        "signals_created": actual_n,
        "sources_reused": sources_reused,
        "promotion_id": conn.execute(
            "SELECT last_insert_rowid() as id"
        ).fetchone()["id"],
    }
    logger.info(f"Promoted cluster '{cluster_slug}': {result}")
    return result


def audit_promotions(conn: sqlite3.Connection, store) -> dict:
    """
    Promotion-specific integrity checks.

    1. Every cluster_promotions row points to a live correlation and opportunity.
    2. Every RECURRING_DEMAND correlation has a promotion row (no orphan pattern-claims).

    Returns:
        {"orphan_promotions": int, "orphan_recurring_demand": int,
         "stale_demand_signals": int, "integrity_ok": bool}
    """
    # Check 1: promotion rows with missing correlation or opportunity
    orphan_promotions = 0
    promotions = conn.execute("SELECT * FROM cluster_promotions").fetchall()
    for p in promotions:
        corr = store.db.conn.execute(
            "SELECT correlation_id FROM correlations WHERE correlation_id = ?",
            (p["correlation_id"],),
        ).fetchone()
        opp = store.db.conn.execute(
            "SELECT opportunity_id FROM opportunities WHERE opportunity_id = ?",
            (p["opportunity_id"],),
        ).fetchone()
        if not corr or not opp:
            orphan_promotions += 1

    # Check 2: RECURRING_DEMAND correlations without a promotion row
    recurring = store.db.conn.execute(
        "SELECT correlation_id FROM correlations WHERE correlation_type = 'recurring_demand'"
    ).fetchall()
    promotion_corr_ids = {p["correlation_id"] for p in promotions}
    orphan_recurring = sum(
        1 for r in recurring if r["correlation_id"] not in promotion_corr_ids
    )

    # Check 3: count stale COMMUNITY_DEMAND signals (for info)
    stale_demand = store.db.conn.execute(
        """SELECT COUNT(*) as cnt FROM signals
           WHERE signal_type = 'community_demand'
             AND expires_at IS NOT NULL
             AND expires_at < datetime('now')
             AND superseded_by IS NULL"""
    ).fetchone()["cnt"]

    ok = orphan_promotions == 0 and orphan_recurring == 0

    result = {
        "orphan_promotions": orphan_promotions,
        "orphan_recurring_demand": orphan_recurring,
        "stale_demand_signals": stale_demand,
        "integrity_ok": ok,
    }
    logger.info(f"Promotion audit: {result}")
    return result

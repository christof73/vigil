"""
Community Scanner — Taxonomy Sync
=================================
Upserts taxonomy.yaml clusters into signal_clusters table.
Slug is the stable join key — labels, lanes, and weights can change
without breaking FKs.
"""

import logging
import sqlite3

from .config import TaxonomyManager

logger = logging.getLogger("vectis_intel.community.sync_taxonomy")


def sync_taxonomy(conn: sqlite3.Connection, taxonomy: TaxonomyManager) -> dict:
    """
    Upsert taxonomy clusters into signal_clusters.

    Returns:
        {"inserted": int, "updated": int, "deactivated": int}
    """
    data = taxonomy.get()
    clusters = data.get("clusters", [])
    lanes = data.get("lanes", {})

    inserted = 0
    updated = 0

    yaml_slugs = set()

    for cluster in clusters:
        slug = cluster["slug"]
        label = cluster["label"]
        lane = cluster["lane"]
        lane_weight = lanes.get(lane, {}).get("weight", 1.0)
        yaml_slugs.add(slug)

        existing = conn.execute(
            "SELECT id, label, lane, lane_weight FROM signal_clusters WHERE slug = ?",
            (slug,),
        ).fetchone()

        if existing is None:
            conn.execute(
                "INSERT INTO signal_clusters (slug, label, lane, lane_weight, active) VALUES (?, ?, ?, ?, 1)",
                (slug, label, lane, lane_weight),
            )
            inserted += 1
            logger.info(f"Inserted cluster: {slug}")
        else:
            if (existing["label"] != label or existing["lane"] != lane
                    or existing["lane_weight"] != lane_weight):
                conn.execute(
                    "UPDATE signal_clusters SET label = ?, lane = ?, lane_weight = ?, active = 1 WHERE slug = ?",
                    (label, lane, lane_weight, slug),
                )
                updated += 1
                logger.info(f"Updated cluster: {slug}")
            else:
                # Re-activate if it was soft-retired
                conn.execute(
                    "UPDATE signal_clusters SET active = 1 WHERE slug = ? AND active = 0",
                    (slug,),
                )

    # Soft-deactivate clusters no longer in taxonomy
    all_slugs = conn.execute(
        "SELECT slug FROM signal_clusters WHERE active = 1"
    ).fetchall()
    deactivated = 0
    for row in all_slugs:
        if row["slug"] not in yaml_slugs:
            conn.execute(
                "UPDATE signal_clusters SET active = 0 WHERE slug = ?",
                (row["slug"],),
            )
            deactivated += 1
            logger.info(f"Deactivated cluster: {row['slug']}")

    conn.commit()

    result = {"inserted": inserted, "updated": updated, "deactivated": deactivated}
    logger.info(f"Taxonomy sync complete: {result}")
    return result

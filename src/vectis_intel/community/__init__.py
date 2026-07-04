"""
Vectis Market Intelligence — Community Scanner
===============================================
Counts how often the same ServiceNow pain recurs across community
channels, measures whether it goes unsolved, and cross-references
Store coverage.

Modules:
  - ingest: Source-specific ingesters (SN Community, Reddit, Stack Overflow)
  - classify: Deterministic keyword-based topic classifier
  - score: Monthly composite scoring with configurable weights
  - digest: Weekly ranked digest generator
  - config: Taxonomy configuration loader
  - schema: Additive SQLite DDL
  - sync_taxonomy: YAML → signal_clusters upsert
"""

from .schema import apply_community_schema
from .config import TaxonomyManager
from .classify import classify, has_large_code_block, count_commercial_hits, reclassify_all
from .score import score_clusters, update_store_gap, get_outlier_slugs
from .digest import generate_digest
from .sync_taxonomy import sync_taxonomy

__all__ = [
    "apply_community_schema",
    "TaxonomyManager",
    "classify",
    "has_large_code_block",
    "count_commercial_hits",
    "reclassify_all",
    "score_clusters",
    "update_store_gap",
    "get_outlier_slugs",
    "generate_digest",
    "sync_taxonomy",
]

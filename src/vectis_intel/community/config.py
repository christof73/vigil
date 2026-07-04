"""
Community Scanner — Taxonomy Configuration
==========================================
Loads taxonomy.yaml, provides access to clusters, config, and lane weights.
"""

import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("vectis_intel.community.config")

_DEFAULT_TAXONOMY_PATH = Path(__file__).parent / "taxonomy.yaml"


class TaxonomyManager:
    """Loads and caches taxonomy.yaml with hot-reload on file change."""

    def __init__(self, path: Optional[str] = None):
        self.path = Path(path) if path else _DEFAULT_TAXONOMY_PATH
        self._data: Optional[dict] = None
        self._mtime: Optional[float] = None

    def _load(self) -> dict:
        if not self.path.exists():
            logger.warning(f"Taxonomy not found: {self.path}")
            return {"config": {}, "lanes": {}, "clusters": []}

        with open(self.path) as f:
            data = yaml.safe_load(f)

        self._mtime = self.path.stat().st_mtime
        logger.info(
            f"Loaded taxonomy from {self.path}",
            extra={"cluster_count": len(data.get("clusters", []))},
        )
        return data

    def _has_changed(self) -> bool:
        if not self.path.exists():
            return False
        current_mtime = self.path.stat().st_mtime
        return self._mtime is None or current_mtime > self._mtime

    def get(self, check_reload: bool = True) -> dict:
        if self._data is None:
            self._data = self._load()
        elif check_reload and self._has_changed():
            logger.info("Taxonomy file changed, reloading...")
            self._data = self._load()
        return self._data

    @property
    def config(self) -> dict:
        return self.get().get("config", {})

    @property
    def clusters(self) -> list[dict]:
        return self.get().get("clusters", [])

    @property
    def lanes(self) -> dict:
        return self.get().get("lanes", {})

    def lane_weight(self, lane: str) -> float:
        return self.lanes.get(lane, {}).get("weight", 1.0)

    @property
    def scoring_weights(self) -> dict:
        return self.config.get("scoring_weights", {})

    @property
    def commercial_keywords(self) -> list[str]:
        return self.config.get("commercial_keywords", [])

    @property
    def min_keyword_hits(self) -> int:
        return self.config.get("min_keyword_hits", 2)

    @property
    def large_code_block_lines(self) -> int:
        return self.config.get("large_code_block_lines", 30)

    @property
    def window_months(self) -> int:
        return self.config.get("window_months", 12)

    @property
    def outlier_override(self) -> dict:
        return self.config.get("outlier_override", {"top_n": 3})

    @property
    def outlier_top_n(self) -> int:
        return self.outlier_override.get("top_n", 3)

    @property
    def content_candidate_config(self) -> dict:
        return self.config.get("content_candidate", {"min_views": 1000, "require_unsolved": True})

    @property
    def content_min_views(self) -> int:
        return self.content_candidate_config.get("min_views", 1000)

    @property
    def content_require_unsolved(self) -> bool:
        return self.content_candidate_config.get("require_unsolved", True)

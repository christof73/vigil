"""
Tests for Community Scanner classifier.
Covers: keyword matching, tie-breaking, threshold edge cases,
code block detection, commercial hit counting.
"""

import pytest

from vectis_intel.community.classify import (
    classify,
    has_large_code_block,
    count_commercial_hits,
    _count_keyword_hits,
)


# ── Sample taxonomy clusters for testing ─────────────────────

CLUSTERS = [
    {
        "slug": "grc_evidence_collection",
        "label": "GRC Evidence Collection",
        "lane": "grc",
        "keywords": ["evidence request", "evidence collection", "attestation", "control attestation"],
    },
    {
        "slug": "update_set_lifecycle",
        "label": "Update Set Promotion",
        "lane": "platform_utility",
        "keywords": ["update set", "skipped updates", "missing dependency", "collision"],
    },
    {
        "slug": "acl_debugging",
        "label": "ACL Debugging",
        "lane": "platform_utility",
        "keywords": ["acl", "access denied", "security rule", "read access"],
    },
]


# ── classify() ───────────────────────────────────────────────

class TestClassify:
    def test_basic_match(self):
        result = classify(
            "How to handle evidence request for SOC2",
            "We need to collect evidence collection artifacts from teams",
            CLUSTERS,
            min_keyword_hits=2,
        )
        assert result == "grc_evidence_collection"

    def test_no_match_below_threshold(self):
        result = classify(
            "General ServiceNow question",
            "Nothing related to any cluster keywords here",
            CLUSTERS,
            min_keyword_hits=2,
        )
        assert result is None

    def test_single_hit_below_default_threshold(self):
        """One keyword hit should not match at threshold=2."""
        result = classify(
            "I have an update set problem",
            "No other keywords here",
            CLUSTERS,
            min_keyword_hits=2,
        )
        assert result is None

    def test_exact_threshold(self):
        """Exactly min_keyword_hits should match."""
        result = classify(
            "update set issue with collision",
            "",
            CLUSTERS,
            min_keyword_hits=2,
        )
        assert result == "update_set_lifecycle"

    def test_highest_hits_wins(self):
        """Cluster with more keyword hits should win."""
        result = classify(
            "update set collision with skipped updates and missing dependency",
            "",
            CLUSTERS,
            min_keyword_hits=2,
        )
        assert result == "update_set_lifecycle"

    def test_tie_first_in_order_wins(self):
        """When tied, first cluster in taxonomy order wins."""
        # Both clusters get exactly 2 hits
        result = classify(
            "evidence request attestation acl access denied",
            "",
            CLUSTERS,
            min_keyword_hits=2,
        )
        # grc_evidence_collection comes first in CLUSTERS
        assert result == "grc_evidence_collection"

    def test_case_insensitive(self):
        result = classify(
            "UPDATE SET issues",
            "There was a COLLISION during promotion",
            CLUSTERS,
            min_keyword_hits=2,
        )
        assert result == "update_set_lifecycle"

    def test_none_body(self):
        """Body can be None."""
        result = classify(
            "evidence request and attestation issues",
            None,
            CLUSTERS,
            min_keyword_hits=2,
        )
        assert result == "grc_evidence_collection"

    def test_empty_clusters(self):
        result = classify("any title", "any body", [], min_keyword_hits=2)
        assert result is None

    def test_threshold_one(self):
        """Single keyword hit should match at threshold=1."""
        result = classify(
            "Just acl stuff",
            None,
            CLUSTERS,
            min_keyword_hits=1,
        )
        assert result == "acl_debugging"


# ── has_large_code_block() ───────────────────────────────────

class TestHasLargeCodeBlock:
    def test_fenced_block_over_threshold(self):
        lines = "\n".join([f"line {i}" for i in range(35)])
        body = f"Some text\n```\n{lines}\n```\nMore text"
        assert has_large_code_block(body, threshold_lines=30) is True

    def test_fenced_block_under_threshold(self):
        lines = "\n".join([f"line {i}" for i in range(10)])
        body = f"```\n{lines}\n```"
        assert has_large_code_block(body, threshold_lines=30) is False

    def test_pre_block_over_threshold(self):
        lines = "\n".join([f"line {i}" for i in range(35)])
        body = f"<pre>\n{lines}\n</pre>"
        assert has_large_code_block(body, threshold_lines=30) is True

    def test_indented_block_over_threshold(self):
        lines = "\n".join([f"    code line {i}" for i in range(32)])
        body = f"Some text\n{lines}\nMore text"
        assert has_large_code_block(body, threshold_lines=30) is True

    def test_indented_block_under_threshold(self):
        lines = "\n".join([f"    code line {i}" for i in range(5)])
        body = f"Some text\n{lines}\nMore text"
        assert has_large_code_block(body, threshold_lines=30) is False

    def test_none_body(self):
        assert has_large_code_block(None) is False

    def test_empty_body(self):
        assert has_large_code_block("") is False

    def test_mixed_indent_resets(self):
        """Non-indented line breaks the run."""
        block1 = "\n".join([f"    line {i}" for i in range(15)])
        block2 = "\n".join([f"    line {i}" for i in range(15)])
        body = f"{block1}\nnot indented\n{block2}"
        assert has_large_code_block(body, threshold_lines=30) is False


# ── count_commercial_hits() ──────────────────────────────────

class TestCountCommercialHits:
    KEYWORDS = ["consultant", "quoted us", "licensing cost", "paid solution"]

    def test_basic_count(self):
        assert count_commercial_hits(
            "Need a consultant for this",
            "They quoted us $50k",
            self.KEYWORDS,
        ) == 2

    def test_no_hits(self):
        assert count_commercial_hits(
            "Simple question",
            "No commercial content",
            self.KEYWORDS,
        ) == 0

    def test_none_body(self):
        assert count_commercial_hits(
            "Looking for a consultant",
            None,
            self.KEYWORDS,
        ) == 1

    def test_case_insensitive(self):
        assert count_commercial_hits(
            "PAID SOLUTION needed",
            "Licensing Cost is high",
            self.KEYWORDS,
        ) == 2

    def test_all_keywords(self):
        assert count_commercial_hits(
            "consultant quoted us",
            "licensing cost paid solution",
            self.KEYWORDS,
        ) == 4


# ── _count_keyword_hits() ───────────────────────────────────

class TestCountKeywordHits:
    def test_substring_match(self):
        assert _count_keyword_hits("this contains acl rules", ["acl", "rules"]) == 2

    def test_no_partial_double_count(self):
        """Each keyword counted at most once even if it appears multiple times."""
        assert _count_keyword_hits("acl acl acl", ["acl"]) == 1

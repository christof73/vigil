"""
Tests for configuration management.
"""

import json
import os
import tempfile
import pytest

from vectis_intel.config import (
    WatchlistManager,
    setup_logging,
    get_env,
    get_env_bool,
    get_env_int,
)


class TestWatchlistManager:
    """Tests for WatchlistManager."""

    @pytest.fixture
    def sample_watchlist_file(self):
        """Create a temporary watchlist file."""
        watchlist = {
            "version": "1.0",
            "keywords": {
                "servicenow": ["ServiceNow", "SNOW"],
                "grc": ["GRC", "governance risk compliance"],
            },
            "naics_codes": {
                "primary": ["541512", "541511"],
                "secondary": ["541519"],
            },
            "competitors": {
                "large_primes": ["Deloitte", "Accenture"],
            },
            "agencies_of_interest": ["Treasury", "DHS"],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(watchlist, f)
            path = f.name

        yield path, watchlist

        os.unlink(path)

    def test_load_watchlist(self, sample_watchlist_file):
        """Test loading watchlist from file."""
        path, expected = sample_watchlist_file
        manager = WatchlistManager(path)

        watchlist = manager.get()

        assert watchlist["version"] == "1.0"
        assert "servicenow" in watchlist["keywords"]
        assert len(watchlist["keywords"]["servicenow"]) == 2

    def test_get_stats(self, sample_watchlist_file):
        """Test getting watchlist statistics."""
        path, _ = sample_watchlist_file
        manager = WatchlistManager(path)

        # Force load
        manager.get()
        stats = manager.get_stats()

        assert stats["exists"] is True
        assert stats["keyword_categories"] == 2
        assert stats["total_keywords"] == 4  # 2 + 2
        assert stats["naics_primary"] == 2
        assert stats["naics_secondary"] == 1
        assert stats["competitor_groups"] == 1
        assert stats["agencies_of_interest"] == 2

    def test_reload(self, sample_watchlist_file):
        """Test reloading watchlist."""
        path, original = sample_watchlist_file
        manager = WatchlistManager(path)

        # Initial load
        watchlist1 = manager.get()
        assert len(watchlist1["keywords"]["servicenow"]) == 2

        # Modify file
        updated = original.copy()
        updated["keywords"]["servicenow"].append("Service-Now")
        with open(path, "w") as f:
            json.dump(updated, f)

        # Force reload
        watchlist2 = manager.reload()
        assert len(watchlist2["keywords"]["servicenow"]) == 3

    def test_missing_file(self):
        """Test handling missing watchlist file."""
        manager = WatchlistManager("/nonexistent/path.json")
        watchlist = manager.get()

        # Should return empty defaults
        assert watchlist == {"keywords": {}, "naics_codes": {}}

    def test_invalid_json(self):
        """Test handling invalid JSON."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("not valid json {{{")
            path = f.name

        try:
            manager = WatchlistManager(path)
            watchlist = manager.get()

            # Should return empty defaults
            assert watchlist == {"keywords": {}, "naics_codes": {}}
        finally:
            os.unlink(path)


class TestEnvironmentHelpers:
    """Tests for environment variable helpers."""

    def test_get_env_default(self):
        """Test get_env with default."""
        # Clean up any existing value
        os.environ.pop("TEST_VAR_12345", None)

        result = get_env("TEST_VAR_12345", "default_value")
        assert result == "default_value"

    def test_get_env_set(self):
        """Test get_env with set value."""
        os.environ["TEST_VAR_12345"] = "actual_value"
        try:
            result = get_env("TEST_VAR_12345", "default")
            assert result == "actual_value"
        finally:
            os.environ.pop("TEST_VAR_12345", None)

    def test_get_env_bool_true(self):
        """Test get_env_bool with true values."""
        for value in ["true", "True", "TRUE", "1", "yes", "YES"]:
            os.environ["TEST_BOOL"] = value
            assert get_env_bool("TEST_BOOL", False) is True
        os.environ.pop("TEST_BOOL", None)

    def test_get_env_bool_false(self):
        """Test get_env_bool with false values."""
        for value in ["false", "False", "FALSE", "0", "no", "NO"]:
            os.environ["TEST_BOOL"] = value
            assert get_env_bool("TEST_BOOL", True) is False
        os.environ.pop("TEST_BOOL", None)

    def test_get_env_bool_default(self):
        """Test get_env_bool with missing value."""
        os.environ.pop("TEST_BOOL_MISSING", None)
        assert get_env_bool("TEST_BOOL_MISSING", True) is True
        assert get_env_bool("TEST_BOOL_MISSING", False) is False

    def test_get_env_int(self):
        """Test get_env_int."""
        os.environ["TEST_INT"] = "42"
        try:
            result = get_env_int("TEST_INT", 0)
            assert result == 42
        finally:
            os.environ.pop("TEST_INT", None)

    def test_get_env_int_invalid(self):
        """Test get_env_int with invalid value."""
        os.environ["TEST_INT_BAD"] = "not_a_number"
        try:
            result = get_env_int("TEST_INT_BAD", 100)
            assert result == 100  # Falls back to default
        finally:
            os.environ.pop("TEST_INT_BAD", None)


class TestLogging:
    """Tests for logging setup."""

    def test_setup_logging(self):
        """Test setting up logging."""
        logger = setup_logging(level="DEBUG", json_format=False)

        assert logger.name == "vectis_intel"
        assert logger.level == 10  # DEBUG

    def test_setup_logging_json(self):
        """Test setting up JSON logging."""
        logger = setup_logging(level="INFO", json_format=True)

        assert logger.name == "vectis_intel"
        # Check handler has JSON formatter
        assert len(logger.handlers) == 1

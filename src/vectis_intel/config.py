"""
Vectis Intel — Configuration Management
=======================================
Handles logging, watchlist loading, and hot-reload.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class StructuredFormatter(logging.Formatter):
    """
    JSON-structured log formatter for production use.

    Output format:
    {"timestamp": "...", "level": "INFO", "logger": "vectis_intel", "message": "...", "extra": {...}}
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "lineno", "funcName", "created",
                "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process", "message", "exc_info", "exc_text",
                "stack_info",
            ):
                extra_fields[key] = value

        if extra_fields:
            log_data["extra"] = extra_fields

        return json.dumps(log_data)


class HumanFormatter(logging.Formatter):
    """
    Human-readable log formatter for development.
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"{timestamp} | {record.levelname:8} | {record.name} | {record.getMessage()}"


def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
) -> logging.Logger:
    """
    Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_format: Use JSON structured logging (for production)

    Returns:
        Root logger for vectis_intel
    """
    # Get log level
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Create formatter
    if json_format:
        formatter = StructuredFormatter()
    else:
        formatter = HumanFormatter()

    # Configure handler
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger("vectis_intel")
    root_logger.setLevel(log_level)
    root_logger.handlers = [handler]

    # Prevent propagation to root logger
    root_logger.propagate = False

    return root_logger


class WatchlistManager:
    """
    Manages watchlist configuration with hot-reload support.

    Tracks file modification time and reloads on change.

    Usage:
        manager = WatchlistManager("/path/to/watchlists.json")
        watchlist = manager.get()  # Returns cached or reloaded
        manager.reload()  # Force reload
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self._watchlist: Optional[dict] = None
        self._mtime: Optional[float] = None
        self._logger = logging.getLogger("vectis_intel.config")

    def _load(self) -> dict:
        """Load watchlist from file."""
        if not self.path.exists():
            self._logger.warning(f"Watchlist not found: {self.path}")
            return {"keywords": {}, "naics_codes": {}}

        try:
            with open(self.path) as f:
                data = json.load(f)

            self._mtime = self.path.stat().st_mtime
            self._logger.info(
                f"Loaded watchlist from {self.path}",
                extra={
                    "keyword_categories": len(data.get("keywords", {})),
                    "naics_primary": len(data.get("naics_codes", {}).get("primary", [])),
                }
            )
            return data

        except json.JSONDecodeError as e:
            self._logger.error(f"Invalid JSON in watchlist: {e}")
            return {"keywords": {}, "naics_codes": {}}

        except Exception as e:
            self._logger.error(f"Failed to load watchlist: {e}")
            return {"keywords": {}, "naics_codes": {}}

    def _has_changed(self) -> bool:
        """Check if the watchlist file has been modified."""
        if not self.path.exists():
            return False

        try:
            current_mtime = self.path.stat().st_mtime
            return self._mtime is None or current_mtime > self._mtime
        except Exception:
            return False

    def get(self, check_reload: bool = True) -> dict:
        """
        Get the watchlist, reloading if file has changed.

        Args:
            check_reload: If True, check for file changes (default)

        Returns:
            Watchlist configuration dict
        """
        if self._watchlist is None:
            self._watchlist = self._load()
        elif check_reload and self._has_changed():
            self._logger.info("Watchlist file changed, reloading...")
            self._watchlist = self._load()

        return self._watchlist

    def reload(self) -> dict:
        """Force reload the watchlist."""
        self._watchlist = self._load()
        return self._watchlist

    def get_stats(self) -> dict:
        """Get statistics about the current watchlist."""
        watchlist = self.get(check_reload=False)

        keywords = watchlist.get("keywords", {})
        naics = watchlist.get("naics_codes", {})
        competitors = watchlist.get("competitors", {})
        agencies = watchlist.get("agencies_of_interest", [])

        total_keywords = sum(len(terms) for terms in keywords.values())

        return {
            "path": str(self.path),
            "exists": self.path.exists(),
            "last_modified": datetime.fromtimestamp(self._mtime).isoformat() if self._mtime else None,
            "keyword_categories": len(keywords),
            "total_keywords": total_keywords,
            "naics_primary": len(naics.get("primary", [])),
            "naics_secondary": len(naics.get("secondary", [])),
            "competitor_groups": len(competitors),
            "agencies_of_interest": len(agencies),
        }


# Environment variable helpers
def get_env(key: str, default: str = "") -> str:
    """Get environment variable with default."""
    return os.getenv(key, default)


def get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean environment variable."""
    value = os.getenv(key, "").lower()
    if value in ("true", "1", "yes"):
        return True
    if value in ("false", "0", "no"):
        return False
    return default


def get_env_int(key: str, default: int = 0) -> int:
    """Get integer environment variable."""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default

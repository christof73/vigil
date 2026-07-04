"""
Community Scanner — Ingestion Layer
===================================
Source-specific ingesters that emit normalized community_signals rows.
"""

from .base import IngestResult, upsert_signal, get_watermark, set_watermark
from .reddit import RedditIngester
from .stackoverflow import StackOverflowIngester
from .sn_community import SNCommunityIngester

__all__ = [
    "IngestResult",
    "upsert_signal",
    "get_watermark",
    "set_watermark",
    "RedditIngester",
    "StackOverflowIngester",
    "SNCommunityIngester",
]

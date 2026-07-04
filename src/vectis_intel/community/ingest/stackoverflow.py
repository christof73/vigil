"""
Community Scanner — Stack Overflow Ingester
==========================================
Stack Exchange API v2.3, `servicenow` tag.
Free quota is sufficient at daily cadence.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import httpx

from .base import IngestResult, upsert_signal, get_watermark, set_watermark
from ..config import TaxonomyManager

logger = logging.getLogger("vectis_intel.community.ingest.stackoverflow")

SE_API_BASE = "https://api.stackexchange.com/2.3"
TAG = "servicenow"


class StackOverflowIngester:
    """
    Ingests questions tagged `servicenow` from Stack Overflow.

    Uses the Stack Exchange API (no auth required for read-only).
    `has_accepted_solution` maps to `is_answered` + `accepted_answer_id`.
    """

    SOURCE = "stackoverflow"

    def __init__(self, taxonomy: TaxonomyManager):
        self.taxonomy = taxonomy

    async def ingest(
        self,
        conn: sqlite3.Connection,
        page_size: int = 100,
        max_pages: int = 5,
    ) -> IngestResult:
        """
        Pull new questions tagged 'servicenow', sorted by creation date.

        Args:
            conn: SQLite connection with community schema applied.
            page_size: Items per API page (max 100).
            max_pages: Safety limit on pagination.
        """
        result = IngestResult(source=self.SOURCE)
        watermark = get_watermark(conn, self.SOURCE)
        latest_posted = watermark

        # Convert watermark to epoch for fromdate parameter
        fromdate = None
        if watermark:
            try:
                dt = datetime.fromisoformat(watermark.replace("Z", "+00:00"))
                fromdate = int(dt.timestamp())
            except ValueError:
                pass

        async with httpx.AsyncClient(timeout=30.0) as client:
            page = 1
            has_more = True

            while has_more and page <= max_pages:
                params = {
                    "order": "desc",
                    "sort": "creation",
                    "tagged": TAG,
                    "site": "stackoverflow",
                    "pagesize": page_size,
                    "page": page,
                    "filter": "withbody",  # include body text
                }
                if fromdate:
                    params["fromdate"] = fromdate

                try:
                    resp = await client.get(f"{SE_API_BASE}/questions", params=params)
                    resp.raise_for_status()
                except Exception as e:
                    logger.error(f"Stack Exchange API error (page {page}): {e}")
                    result.errors += 1
                    break

                data = resp.json()
                items = data.get("items", [])
                has_more = data.get("has_more", False)

                if not items:
                    break

                for q in items:
                    question_id = str(q.get("question_id", ""))
                    if not question_id:
                        continue

                    created = q.get("creation_date", 0)
                    posted_at = datetime.fromtimestamp(
                        created, tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")

                    title = q.get("title", "")
                    body = q.get("body") or None
                    url = q.get("link", f"https://stackoverflow.com/q/{question_id}")
                    reply_count = q.get("answer_count", 0)
                    view_count = q.get("view_count")
                    has_accepted = bool(q.get("accepted_answer_id"))

                    action = upsert_signal(
                        conn, self.taxonomy,
                        source=self.SOURCE,
                        external_id=question_id,
                        board=TAG,
                        title=title,
                        body=body,
                        url=url,
                        posted_at=posted_at,
                        reply_count=reply_count,
                        view_count=view_count,
                        has_accepted_solution=has_accepted,
                    )
                    if action == "inserted":
                        result.inserted += 1
                    else:
                        result.updated += 1

                    if latest_posted is None or posted_at > latest_posted:
                        latest_posted = posted_at

                # Check API quota
                remaining = data.get("quota_remaining", 300)
                if remaining < 10:
                    logger.warning(f"Stack Exchange quota low: {remaining} remaining")
                    break

                page += 1

                # Be respectful of rate limits
                if has_more:
                    import asyncio
                    await asyncio.sleep(1.0)

        if latest_posted and latest_posted != watermark:
            set_watermark(conn, self.SOURCE, latest_posted)

        conn.commit()
        logger.info(f"Stack Overflow ingest: {result}")
        return result

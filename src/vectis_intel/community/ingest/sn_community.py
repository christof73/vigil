"""
Community Scanner — ServiceNow Community Ingester
=================================================
Khoros RSS feed per board. This is the GO/NO-GO gate:
if RSS is unavailable, STOP and surface the decision.

Target boards:
  - Developer
  - GRC/IRM
  - Platform Administration
"""

import logging
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional

import httpx

from .base import IngestResult, upsert_signal, get_watermark, set_watermark
from ..config import TaxonomyManager

logger = logging.getLogger("vectis_intel.community.ingest.sn_community")

# Khoros RSS feed URL pattern — board ID is the variable part
# These need verification before first run (GO/NO-GO gate)
BOARD_FEEDS = {
    "developer": "https://community.servicenow.com/community/feeds/board?board.id=developer-forum",
    "grc-irm": "https://community.servicenow.com/community/feeds/board?board.id=grc-irm",
    "platform-admin": "https://community.servicenow.com/community/feeds/board?board.id=platform-administration",
}


@dataclass
class RSSItem:
    """Parsed RSS feed item."""
    external_id: str
    title: str
    body: Optional[str]
    url: str
    posted_at: str
    reply_count: int = 0
    view_count: Optional[int] = None
    has_accepted_solution: bool = False


def _parse_rss_item(item: ET.Element) -> Optional[RSSItem]:
    """Parse a single RSS <item> into an RSSItem."""
    guid = item.findtext("guid")
    title = item.findtext("title")
    link = item.findtext("link")

    if not guid or not title or not link:
        return None

    # Parse pub date
    pub_date_str = item.findtext("pubDate")
    if pub_date_str:
        try:
            posted_at = parsedate_to_datetime(pub_date_str).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            posted_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        posted_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    body = item.findtext("description") or item.findtext("content:encoded")

    # Khoros sometimes includes reply count and accepted solution in custom namespaces
    # These vary by feed configuration — extract if available
    reply_count = 0
    has_accepted = False

    # Try Khoros-specific fields (namespace varies)
    for child in item:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "replies":
            try:
                reply_count = int(child.text or "0")
            except ValueError:
                pass
        elif tag == "accepted_solution" or tag == "kudos":
            if child.text and child.text.lower() in ("true", "1"):
                has_accepted = True

    return RSSItem(
        external_id=guid,
        title=title,
        body=body,
        url=link,
        posted_at=posted_at,
        reply_count=reply_count,
        has_accepted_solution=has_accepted,
    )


def _parse_rss_feed(xml_text: str) -> list[RSSItem]:
    """Parse RSS XML into list of RSSItems."""
    root = ET.fromstring(xml_text)
    items = []
    for item_elem in root.iter("item"):
        parsed = _parse_rss_item(item_elem)
        if parsed:
            items.append(parsed)
    return items


class SNCommunityIngester:
    """
    Ingests threads from ServiceNow Community Khoros RSS feeds.

    GO/NO-GO: Call verify_feeds() before first production run.
    If any feed returns non-200 or non-RSS content, stop and
    escalate — do not silently fall back to scraping.
    """

    SOURCE = "sn_community"

    def __init__(self, taxonomy: TaxonomyManager, boards: Optional[dict[str, str]] = None):
        self.taxonomy = taxonomy
        self.boards = boards or BOARD_FEEDS

    async def verify_feeds(self) -> dict[str, dict]:
        """
        Check RSS feed availability for all target boards.

        Returns:
            {board_id: {"status": int, "available": bool, "error": str|None}}
        """
        results = {}
        async with httpx.AsyncClient(timeout=15.0) as client:
            for board_id, url in self.boards.items():
                try:
                    resp = await client.get(url)
                    is_rss = (
                        resp.status_code == 200
                        and ("xml" in resp.headers.get("content-type", "")
                             or resp.text.strip().startswith("<?xml"))
                    )
                    results[board_id] = {
                        "status": resp.status_code,
                        "available": is_rss,
                        "error": None if is_rss else f"Non-RSS response (status={resp.status_code})",
                    }
                except Exception as e:
                    results[board_id] = {
                        "status": None,
                        "available": False,
                        "error": str(e),
                    }
                    logger.error(f"Feed verification failed for {board_id}: {e}")

        available = sum(1 for r in results.values() if r["available"])
        logger.info(f"Feed verification: {available}/{len(self.boards)} boards available")
        return results

    async def ingest(self, conn: sqlite3.Connection) -> IngestResult:
        """
        Pull all configured boards, upsert into community_signals.

        Failures on individual boards log and skip — one dead feed
        does not block the others.
        """
        result = IngestResult(source=self.SOURCE)
        watermark = get_watermark(conn, self.SOURCE)
        latest_posted = watermark

        async with httpx.AsyncClient(timeout=30.0) as client:
            for board_id, url in self.boards.items():
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                except Exception as e:
                    logger.error(f"Failed to fetch {board_id}: {e}")
                    result.errors += 1
                    continue

                try:
                    items = _parse_rss_feed(resp.text)
                except ET.ParseError as e:
                    logger.error(f"Failed to parse RSS for {board_id}: {e}")
                    result.errors += 1
                    continue

                for item in items:
                    # Skip items older than watermark
                    if watermark and item.posted_at <= watermark:
                        result.skipped += 1
                        continue

                    action = upsert_signal(
                        conn, self.taxonomy,
                        source=self.SOURCE,
                        external_id=item.external_id,
                        board=board_id,
                        title=item.title,
                        body=item.body,
                        url=item.url,
                        posted_at=item.posted_at,
                        reply_count=item.reply_count,
                        has_accepted_solution=item.has_accepted_solution,
                    )
                    if action == "inserted":
                        result.inserted += 1
                    else:
                        result.updated += 1

                    if latest_posted is None or item.posted_at > latest_posted:
                        latest_posted = item.posted_at

                logger.info(f"Board {board_id}: processed {len(items)} items")

        if latest_posted and latest_posted != watermark:
            set_watermark(conn, self.SOURCE, latest_posted)

        conn.commit()
        logger.info(f"SN Community ingest: {result}")
        return result

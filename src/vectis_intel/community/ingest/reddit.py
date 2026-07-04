"""
Community Scanner — Reddit Ingester
====================================
Official Reddit API via script-type app credentials.
Pulls `new` listing on r/servicenow, daily cadence.
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import httpx

from .base import IngestResult, upsert_signal, get_watermark, set_watermark
from ..config import TaxonomyManager

logger = logging.getLogger("vectis_intel.community.ingest.reddit")

SUBREDDIT = "servicenow"
REDDIT_OAUTH_URL = "https://oauth.reddit.com"
REDDIT_AUTH_URL = "https://www.reddit.com/api/v1/access_token"
USER_AGENT = "vigil-community-scanner/1.0 (by Vectis Labs)"


class RedditIngester:
    """
    Ingests threads from r/servicenow using the official Reddit API.

    Requires script-type app credentials via environment:
      REDDIT_CLIENT_ID
      REDDIT_CLIENT_SECRET
      REDDIT_USERNAME (for user-agent, not login)
    """

    SOURCE = "reddit"

    def __init__(self, taxonomy: TaxonomyManager):
        self.taxonomy = taxonomy
        self.client_id = os.getenv("REDDIT_CLIENT_ID", "")
        self.client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
        self._access_token: Optional[str] = None

    async def _authenticate(self, client: httpx.AsyncClient) -> str:
        """Obtain OAuth2 access token via client_credentials grant."""
        if not self.client_id or not self.client_secret:
            raise RuntimeError("REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set")

        resp = await client.post(
            REDDIT_AUTH_URL,
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        return self._access_token

    async def ingest(self, conn: sqlite3.Connection, limit: int = 100) -> IngestResult:
        """
        Pull new posts from r/servicenow, paginate to watermark.

        Args:
            conn: SQLite connection with community schema applied.
            limit: Max posts per API page (Reddit max = 100).
        """
        result = IngestResult(source=self.SOURCE)
        watermark = get_watermark(conn, self.SOURCE)
        latest_posted = watermark

        async with httpx.AsyncClient(timeout=30.0) as client:
            token = await self._authenticate(client)
            headers = {
                "Authorization": f"Bearer {token}",
                "User-Agent": USER_AGENT,
            }

            after = None
            done = False

            while not done:
                params = {"limit": limit, "sort": "new"}
                if after:
                    params["after"] = after

                resp = await client.get(
                    f"{REDDIT_OAUTH_URL}/r/{SUBREDDIT}/new",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

                children = data.get("data", {}).get("children", [])
                if not children:
                    break

                for child in children:
                    post = child.get("data", {})
                    post_id = post.get("id")
                    if not post_id:
                        continue

                    created_utc = post.get("created_utc", 0)
                    posted_at = datetime.fromtimestamp(
                        created_utc, tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")

                    # Stop if we've reached the watermark
                    if watermark and posted_at <= watermark:
                        done = True
                        break

                    title = post.get("title", "")
                    body = post.get("selftext") or None
                    url = f"https://www.reddit.com{post.get('permalink', '')}"
                    reply_count = post.get("num_comments", 0)
                    view_count = None  # Reddit doesn't expose view counts via API

                    action = upsert_signal(
                        conn, self.taxonomy,
                        source=self.SOURCE,
                        external_id=post_id,
                        board=SUBREDDIT,
                        title=title,
                        body=body,
                        url=url,
                        posted_at=posted_at,
                        reply_count=reply_count,
                        view_count=view_count,
                        has_accepted_solution=False,  # Reddit has no accepted answer concept
                    )
                    if action == "inserted":
                        result.inserted += 1
                    else:
                        result.updated += 1

                    if latest_posted is None or posted_at > latest_posted:
                        latest_posted = posted_at

                after = data.get("data", {}).get("after")
                if not after:
                    break

                # Rate limit: Reddit allows 60 req/min for OAuth
                # At daily cadence this is unlikely to matter, but be respectful
                import asyncio
                await asyncio.sleep(1.0)

        if latest_posted and latest_posted != watermark:
            set_watermark(conn, self.SOURCE, latest_posted)

        conn.commit()
        logger.info(f"Reddit ingest: {result}")
        return result

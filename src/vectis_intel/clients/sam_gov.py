"""
SAM.gov Opportunities API Client
================================
Async client for searching federal procurement opportunities.

API Docs: https://open.gsa.gov/api/sam-api/
Base URL: https://api.sam.gov/opportunities/v2/search
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import httpx

logger = logging.getLogger("vectis_intel.sam_gov")

# SAM.gov requires a SAM.gov-issued API key (NOT api.data.gov keys like DEMO_KEY)
# Register at sam.gov, go to Profile > Public API Key > Request API Key
# Keys expire every 90 days
# See: https://open.gsa.gov/api/get-opportunities-public-api/
DEFAULT_API_KEY = os.getenv("SAM_GOV_API_KEY", "")


@dataclass
class SamPointOfContact:
    """Point of contact for an opportunity."""
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    type: Optional[str] = None


@dataclass
class SamOpportunity:
    """
    Parsed SAM.gov opportunity from search results.

    Note: The `description` field in search results is a URL, not inline text.
    Use `get_opportunity_detail()` to fetch the full description.
    """
    notice_id: str
    title: str
    solicitation_number: Optional[str] = None
    department: Optional[str] = None  # fullParentPathName
    sub_tier: Optional[str] = None
    posted_date: Optional[str] = None
    response_deadline: Optional[str] = None
    archive_date: Optional[str] = None
    naics_code: Optional[str] = None
    classification_code: Optional[str] = None
    notice_type: Optional[str] = None  # e.g., "Combined Synopsis/Solicitation"
    base_type: Optional[str] = None
    set_aside: Optional[str] = None
    active: bool = True
    description_url: Optional[str] = None  # URL to fetch full description
    resource_links: list[str] = field(default_factory=list)
    point_of_contact: list[SamPointOfContact] = field(default_factory=list)

    @property
    def sam_url(self) -> Optional[str]:
        """Direct link to view on SAM.gov."""
        if self.resource_links:
            return self.resource_links[0]
        return f"https://sam.gov/opp/{self.notice_id}/view" if self.notice_id else None


@dataclass
class SamOpportunityDetail(SamOpportunity):
    """Full opportunity detail including description text."""
    description: Optional[str] = None
    award_info: Optional[dict] = None
    attachments: list[dict] = field(default_factory=list)


@dataclass
class SamSearchResult:
    """Search result with pagination info."""
    total_records: int
    opportunities: list[SamOpportunity]
    has_more: bool = False
    offset: int = 0
    limit: int = 10


class SamGovError(Exception):
    """Error from SAM.gov API."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class SamGovClient:
    """
    Async client for SAM.gov Opportunities API.

    Key behaviors:
    - Uses httpx.AsyncClient for async HTTP
    - Respects rate limits (1 req/sec by default)
    - Handles pagination automatically
    - Returns typed dataclasses, not raw dicts
    - All errors logged, never silently swallowed

    Usage:
        async with SamGovClient() as client:
            result = await client.search_opportunities(keywords=["ServiceNow"])
            for opp in result.opportunities:
                print(opp.title)
    """

    BASE_URL = "https://api.sam.gov/opportunities/v2/search"

    def __init__(
        self,
        api_key: str = DEFAULT_API_KEY,
        rate_limit_delay: float = 2.0,  # SAM.gov has strict limits (~10/min)
        timeout: float = 30.0,
        max_retries: int = 5,  # More retries for rate limit recovery
    ):
        self.api_key = api_key
        self.rate_limit_delay = rate_limit_delay
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None
        self._last_request_time: Optional[float] = None

    async def __aenter__(self) -> "SamGovClient":
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _rate_limit(self):
        """Enforce rate limiting between requests."""
        if self._last_request_time is not None:
            elapsed = asyncio.get_event_loop().time() - self._last_request_time
            if elapsed < self.rate_limit_delay:
                await asyncio.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def _request(self, params: dict) -> dict:
        """Make rate-limited request with retries."""
        if not self._client:
            raise SamGovError("Client not initialized. Use 'async with SamGovClient()' context.")

        if not self.api_key:
            raise SamGovError(
                "SAM.gov API key required. Set SAM_GOV_API_KEY environment variable. "
                "Get a key from: sam.gov > Profile > Public API Key > Request API Key"
            )

        params["api_key"] = self.api_key

        last_error = None
        for attempt in range(self.max_retries):
            await self._rate_limit()

            try:
                logger.debug(f"SAM.gov request attempt {attempt + 1}: {params}")
                response = await self._client.get(self.BASE_URL, params=params)

                if response.status_code == 429:
                    # Rate limited - back off exponentially
                    wait_time = (2 ** attempt) * self.rate_limit_delay
                    logger.warning(f"Rate limited by SAM.gov, waiting {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue

                if response.status_code >= 500:
                    # Server error - retry
                    wait_time = (2 ** attempt) * 0.5
                    logger.warning(f"SAM.gov server error {response.status_code}, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue

                if response.status_code != 200:
                    raise SamGovError(
                        f"SAM.gov API error: {response.status_code}",
                        status_code=response.status_code,
                        response_text=response.text[:500]
                    )

                return response.json()

            except httpx.TimeoutException as e:
                last_error = SamGovError(f"Request timeout: {e}")
                logger.warning(f"SAM.gov timeout, attempt {attempt + 1}/{self.max_retries}")
            except httpx.RequestError as e:
                last_error = SamGovError(f"Request error: {e}")
                logger.warning(f"SAM.gov request error: {e}, attempt {attempt + 1}/{self.max_retries}")

        raise last_error or SamGovError("Max retries exceeded")

    def _parse_opportunity(self, data: dict) -> SamOpportunity:
        """Parse raw API response into SamOpportunity dataclass."""
        contacts = []
        for poc in data.get("pointOfContact", []):
            contacts.append(SamPointOfContact(
                full_name=poc.get("fullName"),
                email=poc.get("email"),
                phone=poc.get("phone"),
                type=poc.get("type"),
            ))

        return SamOpportunity(
            notice_id=data.get("noticeId", ""),
            title=data.get("title", ""),
            solicitation_number=data.get("solicitationNumber"),
            department=data.get("fullParentPathName"),
            sub_tier=data.get("subTierAgency"),
            posted_date=data.get("postedDate"),
            response_deadline=data.get("responseDeadLine"),
            archive_date=data.get("archiveDate"),
            naics_code=data.get("naicsCode"),
            classification_code=data.get("classificationCode"),
            notice_type=data.get("type"),
            base_type=data.get("baseType"),
            set_aside=data.get("typeOfSetAsideDescription"),
            active=data.get("active", "Yes") == "Yes",
            description_url=data.get("description"),  # This is a URL, not text
            resource_links=data.get("resourceLinks", []),
            point_of_contact=contacts,
        )

    async def search_opportunities(
        self,
        keywords: Optional[list[str]] = None,
        naics_codes: Optional[list[str]] = None,
        posted_from: Optional[datetime] = None,
        posted_to: Optional[datetime] = None,
        ptype: Optional[str] = None,
        solicitation_number: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> SamSearchResult:
        """
        Search SAM.gov opportunities.

        Args:
            keywords: Search terms (searches title and description)
            naics_codes: NAICS code filter (e.g., ["541512", "541511"])
            posted_from: Start date filter
            posted_to: End date filter
            ptype: Procurement type:
                   o=solicitation, p=presolicitation, r=sources sought,
                   s=special notice, k=combined synopsis/solicitation
            solicitation_number: Specific solicitation number
            limit: Results per page (max 1000)
            offset: Pagination offset

        Returns:
            SamSearchResult with opportunities and pagination info
        """
        # Date range is required by SAM.gov API
        # Default to last 30 days if not specified
        if posted_from is None:
            posted_from = datetime.now() - timedelta(days=30)
        if posted_to is None:
            posted_to = datetime.now()

        params = {
            "limit": min(limit, 1000),
            "offset": offset,
            "postedFrom": posted_from.strftime("%m/%d/%Y"),
            "postedTo": posted_to.strftime("%m/%d/%Y"),
        }

        # SAM.gov uses 'title' parameter for title search (not 'keyword')
        if keywords:
            params["title"] = " ".join(keywords)

        if naics_codes:
            params["naics"] = ",".join(naics_codes)

        if ptype:
            params["ptype"] = ptype

        if solicitation_number:
            params["solnum"] = solicitation_number

        logger.info(f"Searching SAM.gov: keywords={keywords}, naics={naics_codes}, limit={limit}")

        data = await self._request(params)

        total = data.get("totalRecords", 0)
        opportunities = [
            self._parse_opportunity(opp)
            for opp in data.get("opportunitiesData", [])
        ]

        logger.info(f"SAM.gov returned {len(opportunities)} of {total} total opportunities")

        return SamSearchResult(
            total_records=total,
            opportunities=opportunities,
            has_more=(offset + len(opportunities)) < total,
            offset=offset,
            limit=limit,
        )

    async def search_all_opportunities(
        self,
        keywords: Optional[list[str]] = None,
        naics_codes: Optional[list[str]] = None,
        posted_from: Optional[datetime] = None,
        posted_to: Optional[datetime] = None,
        ptype: Optional[str] = None,
        max_results: int = 500,
    ) -> list[SamOpportunity]:
        """
        Search with automatic pagination up to max_results.

        Returns all matching opportunities up to the limit.
        """
        all_opportunities = []
        offset = 0
        page_size = 100

        while len(all_opportunities) < max_results:
            result = await self.search_opportunities(
                keywords=keywords,
                naics_codes=naics_codes,
                posted_from=posted_from,
                posted_to=posted_to,
                ptype=ptype,
                limit=page_size,
                offset=offset,
            )

            all_opportunities.extend(result.opportunities)

            if not result.has_more:
                break

            offset += page_size

        return all_opportunities[:max_results]

    async def get_opportunity_detail(
        self,
        notice_id: Optional[str] = None,
        solicitation_number: Optional[str] = None,
    ) -> Optional[SamOpportunityDetail]:
        """
        Fetch full details for a specific opportunity.

        Must provide either notice_id or solicitation_number.

        Note: This fetches from the search API with specific filters,
        then fetches the description URL if available.
        """
        if not notice_id and not solicitation_number:
            raise ValueError("Must provide notice_id or solicitation_number")

        # Search for the specific opportunity
        params = {"limit": 1}
        if solicitation_number:
            params["solnum"] = solicitation_number

        data = await self._request(params)

        opps = data.get("opportunitiesData", [])
        if not opps:
            return None

        # Find matching opportunity
        opp_data = None
        for opp in opps:
            if notice_id and opp.get("noticeId") == notice_id:
                opp_data = opp
                break
            elif solicitation_number and opp.get("solicitationNumber") == solicitation_number:
                opp_data = opp
                break

        if not opp_data:
            opp_data = opps[0]  # Take first if no exact match

        # Parse base opportunity
        base = self._parse_opportunity(opp_data)

        # Fetch full description if URL available
        description_text = None
        if base.description_url and self._client:
            try:
                await self._rate_limit()
                desc_response = await self._client.get(base.description_url)
                if desc_response.status_code == 200:
                    description_text = desc_response.text
            except Exception as e:
                logger.warning(f"Failed to fetch description: {e}")

        return SamOpportunityDetail(
            notice_id=base.notice_id,
            title=base.title,
            solicitation_number=base.solicitation_number,
            department=base.department,
            sub_tier=base.sub_tier,
            posted_date=base.posted_date,
            response_deadline=base.response_deadline,
            archive_date=base.archive_date,
            naics_code=base.naics_code,
            classification_code=base.classification_code,
            notice_type=base.notice_type,
            base_type=base.base_type,
            set_aside=base.set_aside,
            active=base.active,
            description_url=base.description_url,
            resource_links=base.resource_links,
            point_of_contact=base.point_of_contact,
            description=description_text,
        )

    async def search_by_watchlist(
        self,
        watchlist: dict,
        posted_within_days: int = 7,
        max_per_keyword: int = 50,
    ) -> list[SamOpportunity]:
        """
        Search using watchlist configuration.

        Args:
            watchlist: Dict with "keywords" and "naics_codes" from watchlists.json
            posted_within_days: Look back N days
            max_per_keyword: Max results per keyword category

        Returns:
            Deduplicated list of opportunities matching any watchlist criteria
        """
        posted_from = datetime.now() - timedelta(days=posted_within_days)
        posted_to = datetime.now()

        # Get NAICS codes
        naics = watchlist.get("naics_codes", {})
        all_naics = naics.get("primary", []) + naics.get("secondary", [])

        # Collect all opportunities, deduplicate by notice_id
        seen_ids: set[str] = set()
        all_opportunities: list[SamOpportunity] = []

        # Search by each keyword category
        keywords_config = watchlist.get("keywords", {})
        for category, terms in keywords_config.items():
            logger.info(f"Searching watchlist category: {category}")

            try:
                result = await self.search_opportunities(
                    keywords=terms,
                    naics_codes=all_naics if all_naics else None,
                    posted_from=posted_from,
                    posted_to=posted_to,
                    limit=max_per_keyword,
                )

                for opp in result.opportunities:
                    if opp.notice_id not in seen_ids:
                        seen_ids.add(opp.notice_id)
                        all_opportunities.append(opp)

            except SamGovError as e:
                logger.error(f"Error searching category {category}: {e}")
                continue

        logger.info(f"Watchlist search found {len(all_opportunities)} unique opportunities")
        return all_opportunities

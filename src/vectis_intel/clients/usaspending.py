"""
USAspending.gov API Client
==========================
Client for searching federal contract awards.

API Documentation: https://api.usaspending.gov/
No authentication required - fully public API.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import httpx

logger = logging.getLogger("vectis_intel.usaspending")


class USAspendingError(Exception):
    """Exception for USAspending API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class AwardSummary:
    """
    Summary of a contract award from USAspending search results.
    """
    award_id: str
    recipient_name: str
    award_amount: float
    awarding_agency: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    naics_code: Optional[str] = None
    description: Optional[str] = None
    award_type: Optional[str] = None

    # Internal tracking field for URL generation
    generated_internal_id: Optional[str] = None

    @property
    def usaspending_url(self) -> str:
        """Generate the USAspending.gov URL for this award."""
        if self.generated_internal_id:
            return f"https://www.usaspending.gov/award/{self.generated_internal_id}"
        # Fallback - search URL
        return f"https://www.usaspending.gov/search/?keyword={self.award_id}"

    @classmethod
    def from_api_response(cls, data: dict) -> "AwardSummary":
        """Parse an award from the spending_by_award API response."""
        return cls(
            award_id=data.get("Award ID") or data.get("award_id") or "",
            recipient_name=data.get("Recipient Name") or data.get("recipient_name") or "Unknown",
            award_amount=float(data.get("Award Amount") or data.get("total_obligation") or 0),
            awarding_agency=data.get("Awarding Agency") or data.get("awarding_agency_name") or "",
            start_date=data.get("Start Date") or data.get("period_of_performance_start_date"),
            end_date=data.get("End Date") or data.get("period_of_performance_current_end_date"),
            naics_code=data.get("NAICS Code") or data.get("naics_code"),
            description=data.get("Description") or data.get("description"),
            award_type=data.get("Award Type") or data.get("type_description"),
            generated_internal_id=data.get("generated_internal_id"),
        )


@dataclass
class AwardDetail:
    """
    Full details of a contract award.
    """
    award_id: str
    recipient_name: str
    recipient_duns: Optional[str]
    recipient_uei: Optional[str]
    award_amount: float
    total_obligation: float
    awarding_agency: str
    funding_agency: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    naics_code: Optional[str]
    naics_description: Optional[str]
    psc_code: Optional[str]  # Product/Service Code
    description: Optional[str]
    award_type: Optional[str]
    place_of_performance: Optional[str]
    usaspending_url: str

    @classmethod
    def from_api_response(cls, data: dict) -> "AwardDetail":
        """Parse from /awards/{id}/ response."""
        # Award detail response has nested structure
        recipient = data.get("recipient", {}) or {}
        latest_transaction = data.get("latest_transaction_contract_data", {}) or {}

        return cls(
            award_id=data.get("piid") or data.get("fain") or data.get("uri") or "",
            recipient_name=recipient.get("recipient_name") or "Unknown",
            recipient_duns=recipient.get("recipient_duns"),
            recipient_uei=recipient.get("recipient_uei"),
            award_amount=float(data.get("total_obligation") or 0),
            total_obligation=float(data.get("total_obligation") or 0),
            awarding_agency=data.get("awarding_agency", {}).get("toptier_agency", {}).get("name") or "",
            funding_agency=data.get("funding_agency", {}).get("toptier_agency", {}).get("name") if data.get("funding_agency") else None,
            start_date=data.get("period_of_performance_start_date"),
            end_date=data.get("period_of_performance_current_end_date"),
            naics_code=latest_transaction.get("naics"),
            naics_description=latest_transaction.get("naics_description"),
            psc_code=latest_transaction.get("product_or_service_code"),
            description=data.get("description"),
            award_type=data.get("type_description"),
            place_of_performance=_format_place_of_performance(data.get("place_of_performance", {})),
            usaspending_url=f"https://www.usaspending.gov/award/{data.get('generated_internal_id', '')}",
        )


@dataclass
class SearchResult:
    """Result of a USAspending search."""
    awards: list[AwardSummary]
    total_count: int
    page: int
    has_next: bool

    @classmethod
    def from_api_response(cls, data: dict) -> "SearchResult":
        """Parse search result from API response."""
        results = data.get("results", [])
        page_meta = data.get("page_metadata", {})

        awards = [AwardSummary.from_api_response(r) for r in results]

        return cls(
            awards=awards,
            total_count=page_meta.get("total", len(awards)),
            page=page_meta.get("page", 1),
            has_next=page_meta.get("hasNext", False),
        )


def _format_place_of_performance(pop: dict) -> Optional[str]:
    """Format place of performance as a string."""
    if not pop:
        return None
    parts = []
    if pop.get("city_name"):
        parts.append(pop["city_name"])
    if pop.get("state_name"):
        parts.append(pop["state_name"])
    if pop.get("country_name") and pop["country_name"] != "UNITED STATES":
        parts.append(pop["country_name"])
    return ", ".join(parts) if parts else None


class USAspendingClient:
    """
    Client for USAspending.gov Awards API.

    Key behaviors:
    - POST-based search endpoints (not GET)
    - Auto-pagination
    - Rate limiting (1 req/sec to be respectful)
    - Typed response models

    Usage:
        async with USAspendingClient() as client:
            results = await client.search_awards(keywords=["ServiceNow"])
            for award in results.awards:
                print(f"{award.recipient_name}: ${award.award_amount:,.2f}")
    """

    BASE_URL = "https://api.usaspending.gov/api/v2"

    # Award type codes
    # A = BPA Call, B = Purchase Order, C = Delivery Order, D = Definitive Contract
    DEFAULT_AWARD_TYPES = ["A", "B", "C", "D"]

    # Default fields to request
    DEFAULT_FIELDS = [
        "Award ID",
        "Recipient Name",
        "Award Amount",
        "Awarding Agency",
        "Start Date",
        "End Date",
        "NAICS Code",
        "Description",
        "Award Type",
        "generated_internal_id",
    ]

    def __init__(
        self,
        rate_limit_delay: float = 1.0,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize the USAspending client.

        Args:
            rate_limit_delay: Seconds to wait between requests
            timeout: Request timeout in seconds
            max_retries: Number of retries for failed requests
        """
        self.rate_limit_delay = rate_limit_delay
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None
        self._last_request_time: Optional[float] = None

    async def __aenter__(self) -> "USAspendingClient":
        """Enter async context."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "VectisIntel/0.1.0 (procurement-scanner)",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
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

    async def _post(self, endpoint: str, payload: dict) -> dict:
        """
        Make a POST request with retries.

        Args:
            endpoint: API endpoint (without base URL)
            payload: JSON payload

        Returns:
            Response JSON as dict
        """
        if not self._client:
            raise USAspendingError("Client not initialized. Use 'async with' context.")

        url = f"{self.BASE_URL}{endpoint}"

        for attempt in range(self.max_retries):
            await self._rate_limit()

            try:
                response = await self._client.post(url, json=payload)

                if response.status_code == 200:
                    return response.json()

                if response.status_code == 429:
                    # Rate limited - wait and retry
                    wait_time = (attempt + 1) * 5  # Exponential backoff
                    logger.warning(f"Rate limited. Waiting {wait_time}s before retry.")
                    await asyncio.sleep(wait_time)
                    continue

                if response.status_code >= 500:
                    # Server error - retry
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Server error {response.status_code}. Retrying in {wait_time}s.")
                    await asyncio.sleep(wait_time)
                    continue

                # Client error - don't retry
                raise USAspendingError(
                    f"API error: {response.status_code} - {response.text[:500]}",
                    status_code=response.status_code
                )

            except httpx.TimeoutException:
                if attempt < self.max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Request timed out. Retrying in {wait_time}s.")
                    await asyncio.sleep(wait_time)
                else:
                    raise USAspendingError("Request timed out after all retries")

            except httpx.RequestError as e:
                if attempt < self.max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Request error: {e}. Retrying in {wait_time}s.")
                    await asyncio.sleep(wait_time)
                else:
                    raise USAspendingError(f"Request failed after all retries: {e}")

        raise USAspendingError("Max retries exceeded")

    async def _get(self, endpoint: str) -> dict:
        """
        Make a GET request with retries.

        Args:
            endpoint: API endpoint (without base URL)

        Returns:
            Response JSON as dict
        """
        if not self._client:
            raise USAspendingError("Client not initialized. Use 'async with' context.")

        url = f"{self.BASE_URL}{endpoint}"

        for attempt in range(self.max_retries):
            await self._rate_limit()

            try:
                response = await self._client.get(url)

                if response.status_code == 200:
                    return response.json()

                if response.status_code == 404:
                    return {}  # Not found - return empty

                if response.status_code == 429 or response.status_code >= 500:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Error {response.status_code}. Retrying in {wait_time}s.")
                    await asyncio.sleep(wait_time)
                    continue

                raise USAspendingError(
                    f"API error: {response.status_code}",
                    status_code=response.status_code
                )

            except httpx.TimeoutException:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep((attempt + 1) * 2)
                else:
                    raise USAspendingError("Request timed out")

            except httpx.RequestError as e:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep((attempt + 1) * 2)
                else:
                    raise USAspendingError(f"Request failed: {e}")

        raise USAspendingError("Max retries exceeded")

    async def search_awards(
        self,
        keywords: Optional[list[str]] = None,
        naics_codes: Optional[list[str]] = None,
        recipient_name: Optional[str] = None,
        agency_name: Optional[str] = None,
        awarded_after: Optional[str] = None,  # YYYY-MM-DD
        awarded_before: Optional[str] = None,  # YYYY-MM-DD
        award_types: Optional[list[str]] = None,
        min_amount: Optional[float] = None,
        limit: int = 25,
        page: int = 1,
        sort_by: str = "Award Amount",
        sort_order: str = "desc",
    ) -> SearchResult:
        """
        Search for contract awards.

        Args:
            keywords: Search keywords (searches in description)
            naics_codes: Filter by NAICS codes
            recipient_name: Filter by contractor/recipient name
            agency_name: Filter by awarding agency
            awarded_after: Start date (YYYY-MM-DD)
            awarded_before: End date (YYYY-MM-DD)
            award_types: Award type codes (A, B, C, D)
            min_amount: Minimum award amount
            limit: Results per page (max 100)
            page: Page number
            sort_by: Sort field
            sort_order: "asc" or "desc"

        Returns:
            SearchResult with awards and pagination info
        """
        # Build filters
        filters: dict = {}

        if keywords:
            filters["keywords"] = keywords

        if naics_codes:
            filters["naics_codes"] = naics_codes

        if recipient_name:
            filters["recipient_search_text"] = [recipient_name]

        if agency_name:
            filters["agencies"] = [{
                "type": "awarding",
                "tier": "toptier",
                "name": agency_name,
            }]

        # Time period
        if awarded_after or awarded_before:
            start = awarded_after or "2000-01-01"
            end = awarded_before or datetime.now().strftime("%Y-%m-%d")
            filters["time_period"] = [{"start_date": start, "end_date": end}]

        # Award types (default to contracts)
        filters["award_type_codes"] = award_types or self.DEFAULT_AWARD_TYPES

        # Amount filter
        if min_amount is not None:
            filters["award_amounts"] = [{"lower_bound": min_amount}]

        # Build request payload
        payload = {
            "filters": filters,
            "fields": self.DEFAULT_FIELDS,
            "limit": min(limit, 100),
            "page": page,
            "sort": sort_by,
            "order": sort_order,
        }

        logger.debug(f"Search awards payload: {payload}")

        data = await self._post("/search/spending_by_award/", payload)
        return SearchResult.from_api_response(data)

    async def search_all_awards(
        self,
        max_results: int = 100,
        **search_kwargs,
    ) -> list[AwardSummary]:
        """
        Search awards with automatic pagination.

        Args:
            max_results: Maximum total results to fetch
            **search_kwargs: Arguments passed to search_awards()

        Returns:
            List of all matching awards (up to max_results)
        """
        all_awards = []
        page = 1
        per_page = min(100, max_results)

        while len(all_awards) < max_results:
            result = await self.search_awards(
                limit=per_page,
                page=page,
                **search_kwargs
            )

            all_awards.extend(result.awards)

            if not result.has_next or len(result.awards) == 0:
                break

            page += 1

            # Safety limit
            if page > 20:
                logger.warning("Hit pagination safety limit (20 pages)")
                break

        return all_awards[:max_results]

    async def get_award_detail(self, award_id: str) -> Optional[AwardDetail]:
        """
        Fetch full details for an award.

        Args:
            award_id: The award ID (generated_internal_id from search)

        Returns:
            AwardDetail or None if not found
        """
        data = await self._get(f"/awards/{award_id}/")

        if not data:
            return None

        return AwardDetail.from_api_response(data)

    async def search_by_recipient(
        self,
        recipient_name: str,
        naics_codes: Optional[list[str]] = None,
        awarded_within_days: int = 365,
        max_results: int = 50,
    ) -> list[AwardSummary]:
        """
        Search for awards to a specific recipient (contractor/competitor).

        Args:
            recipient_name: Recipient/contractor name to search
            naics_codes: Optional NAICS filter
            awarded_within_days: Look back N days
            max_results: Maximum results

        Returns:
            List of awards to this recipient
        """
        awarded_after = (datetime.now() - timedelta(days=awarded_within_days)).strftime("%Y-%m-%d")

        return await self.search_all_awards(
            recipient_name=recipient_name,
            naics_codes=naics_codes,
            awarded_after=awarded_after,
            max_results=max_results,
        )

    async def search_by_agency(
        self,
        agency_name: str,
        naics_codes: Optional[list[str]] = None,
        awarded_within_days: int = 365,
        max_results: int = 50,
    ) -> list[AwardSummary]:
        """
        Search for awards by a specific agency.

        Args:
            agency_name: Agency name (e.g., "Department of the Treasury")
            naics_codes: Optional NAICS filter
            awarded_within_days: Look back N days
            max_results: Maximum results

        Returns:
            List of awards from this agency
        """
        awarded_after = (datetime.now() - timedelta(days=awarded_within_days)).strftime("%Y-%m-%d")

        return await self.search_all_awards(
            agency_name=agency_name,
            naics_codes=naics_codes,
            awarded_after=awarded_after,
            max_results=max_results,
        )

    async def search_by_watchlist(
        self,
        watchlist: dict,
        awarded_within_days: int = 30,
        max_per_keyword: int = 25,
    ) -> list[AwardSummary]:
        """
        Search awards using watchlist configuration.

        Args:
            watchlist: Watchlist config with keywords and naics_codes
            awarded_within_days: Look back N days
            max_per_keyword: Max results per keyword category

        Returns:
            Deduplicated list of awards
        """
        awarded_after = (datetime.now() - timedelta(days=awarded_within_days)).strftime("%Y-%m-%d")

        # Get NAICS codes
        naics_config = watchlist.get("naics_codes", {})
        all_naics = naics_config.get("primary", []) + naics_config.get("secondary", [])

        # Get keywords
        keywords_config = watchlist.get("keywords", {})

        all_awards = []
        seen_ids = set()

        # Search by each keyword category
        for category, terms in keywords_config.items():
            logger.info(f"Searching USAspending for category: {category}")

            result = await self.search_awards(
                keywords=terms,
                naics_codes=all_naics if all_naics else None,
                awarded_after=awarded_after,
                limit=max_per_keyword,
            )

            for award in result.awards:
                if award.award_id not in seen_ids:
                    seen_ids.add(award.award_id)
                    all_awards.append(award)

        logger.info(f"USAspending watchlist search found {len(all_awards)} unique awards")
        return all_awards

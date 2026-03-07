"""
Tests for SAM.gov API client.

Integration tests hit the live API and are marked with @pytest.mark.integration.
Run unit tests only: pytest tests/test_sam_client.py -m "not integration"
Run all tests: pytest tests/test_sam_client.py -v

IMPORTANT: Integration tests require a valid SAM.gov API key.
Set SAM_GOV_API_KEY environment variable before running.
Get a key from: sam.gov > Profile > Public API Key > Request API Key
"""

import json
import os
import pytest
from datetime import datetime, timedelta
from pathlib import Path

from vectis_intel.clients import (
    SamGovClient,
    SamGovError,
    SamOpportunity,
    SamSearchResult,
)


# Check if SAM.gov API key is available for integration tests
SAM_API_KEY = os.getenv("SAM_GOV_API_KEY", "")
SKIP_INTEGRATION = not SAM_API_KEY
SKIP_REASON = (
    "SAM_GOV_API_KEY not set. Get a key from: sam.gov > Profile > Public API Key"
)


class TestSamOpportunityParsing:
    """Unit tests for response parsing (no network)."""

    def test_parse_opportunity(self):
        """Test parsing raw API response into dataclass."""
        raw = {
            "noticeId": "abc123",
            "title": "GRC Modernization Services",
            "solicitationNumber": "70B03C25R00000123",
            "fullParentPathName": "DEPARTMENT OF THE TREASURY",
            "postedDate": "2026-03-01",
            "responseDeadLine": "2026-03-31T17:00:00-04:00",
            "naicsCode": "541512",
            "classificationCode": "D399",
            "type": "Combined Synopsis/Solicitation",
            "active": "Yes",
            "description": "https://api.sam.gov/opportunities/v2/...",
            "resourceLinks": ["https://sam.gov/opp/abc123/view"],
            "pointOfContact": [
                {"fullName": "John Doe", "email": "john@example.gov"}
            ],
        }

        # Use the client's internal parser
        client = SamGovClient.__new__(SamGovClient)
        opp = client._parse_opportunity(raw)

        assert opp.notice_id == "abc123"
        assert opp.title == "GRC Modernization Services"
        assert opp.solicitation_number == "70B03C25R00000123"
        assert opp.department == "DEPARTMENT OF THE TREASURY"
        assert opp.naics_code == "541512"
        assert opp.active is True
        assert opp.sam_url == "https://sam.gov/opp/abc123/view"
        assert len(opp.point_of_contact) == 1
        assert opp.point_of_contact[0].email == "john@example.gov"

    def test_sam_url_fallback(self):
        """Test SAM URL generation when resourceLinks is empty."""
        client = SamGovClient.__new__(SamGovClient)
        opp = client._parse_opportunity({
            "noticeId": "xyz789",
            "title": "Test",
        })

        assert opp.sam_url == "https://sam.gov/opp/xyz789/view"

    def test_parse_empty_response(self):
        """Test parsing minimal/empty response."""
        client = SamGovClient.__new__(SamGovClient)
        opp = client._parse_opportunity({})

        assert opp.notice_id == ""
        assert opp.title == ""
        assert opp.active is True  # Default
        assert opp.point_of_contact == []


class TestSamSearchResult:
    """Unit tests for search result structure."""

    def test_search_result_has_more(self):
        result = SamSearchResult(
            total_records=150,
            opportunities=[],
            has_more=True,
            offset=0,
            limit=100,
        )
        assert result.has_more is True

    def test_search_result_no_more(self):
        result = SamSearchResult(
            total_records=50,
            opportunities=[],
            has_more=False,
            offset=0,
            limit=100,
        )
        assert result.has_more is False


@pytest.mark.integration
@pytest.mark.skipif(SKIP_INTEGRATION, reason=SKIP_REASON)
class TestSamGovClientIntegration:
    """
    Integration tests that hit the live SAM.gov API.

    These tests verify:
    1. API URL is correct
    2. Response parsing works with real data
    3. Rate limiting doesn't cause errors

    Run with: SAM_GOV_API_KEY=your_key pytest tests/test_sam_client.py -m integration -v
    """

    @pytest.mark.asyncio
    async def test_search_servicenow_keyword(self):
        """Search for ServiceNow opportunities - validates API connectivity."""
        async with SamGovClient() as client:
            result = await client.search_opportunities(
                keywords=["ServiceNow"],
                limit=5,
            )

        assert isinstance(result, SamSearchResult)
        assert result.total_records >= 0
        # May or may not have results depending on current postings
        print(f"Found {result.total_records} total, returned {len(result.opportunities)}")

        if result.opportunities:
            opp = result.opportunities[0]
            assert opp.notice_id, "Should have notice_id"
            assert opp.title, "Should have title"
            print(f"First result: {opp.title}")

    @pytest.mark.asyncio
    async def test_search_with_naics(self):
        """Search with NAICS code filter."""
        async with SamGovClient() as client:
            result = await client.search_opportunities(
                naics_codes=["541512"],  # Computer Systems Design
                limit=5,
            )

        assert isinstance(result, SamSearchResult)
        print(f"Found {result.total_records} opportunities with NAICS filter")
        # Note: SAM.gov API doesn't strictly filter by NAICS in all cases
        # It may return broader results. The filter is best-effort.

    @pytest.mark.asyncio
    async def test_search_with_date_range(self):
        """Search with date filter."""
        posted_from = datetime.now() - timedelta(days=30)
        posted_to = datetime.now()

        async with SamGovClient() as client:
            result = await client.search_opportunities(
                keywords=["IT services"],
                posted_from=posted_from,
                posted_to=posted_to,
                limit=5,
            )

        assert isinstance(result, SamSearchResult)
        print(f"Found {result.total_records} IT services opportunities in last 30 days")

    @pytest.mark.asyncio
    async def test_search_combined_synopsis(self):
        """Search for combined synopsis/solicitation type."""
        async with SamGovClient() as client:
            result = await client.search_opportunities(
                ptype="k",  # Combined synopsis/solicitation
                limit=5,
            )

        assert isinstance(result, SamSearchResult)
        print(f"Found {result.total_records} combined synopsis opportunities")

    @pytest.mark.asyncio
    async def test_pagination(self):
        """Test that pagination works."""
        async with SamGovClient() as client:
            # Get first page
            page1 = await client.search_opportunities(
                naics_codes=["541512"],
                limit=3,
                offset=0,
            )

            if page1.total_records > 3:
                # Get second page
                page2 = await client.search_opportunities(
                    naics_codes=["541512"],
                    limit=3,
                    offset=3,
                )

                # Should have different opportunities
                page1_ids = {o.notice_id for o in page1.opportunities}
                page2_ids = {o.notice_id for o in page2.opportunities}

                # No overlap between pages
                assert not (page1_ids & page2_ids), "Pages should have different opportunities"
                print(f"Pagination working: page1={len(page1.opportunities)}, page2={len(page2.opportunities)}")

    @pytest.mark.asyncio
    async def test_search_by_watchlist(self):
        """Test watchlist-based search."""
        # Load actual watchlist
        watchlist_path = Path(__file__).parent.parent / "config" / "watchlists.json"
        if watchlist_path.exists():
            watchlist = json.loads(watchlist_path.read_text())
        else:
            # Minimal watchlist for testing
            watchlist = {
                "keywords": {
                    "servicenow": ["ServiceNow"],
                    "grc": ["GRC", "governance risk compliance"],
                },
                "naics_codes": {
                    "primary": ["541512"],
                    "secondary": [],
                }
            }

        async with SamGovClient() as client:
            opportunities = await client.search_by_watchlist(
                watchlist=watchlist,
                posted_within_days=30,
                max_per_keyword=10,
            )

        print(f"Watchlist search found {len(opportunities)} unique opportunities")

        # Should have deduplicated
        notice_ids = [o.notice_id for o in opportunities]
        assert len(notice_ids) == len(set(notice_ids)), "Should be deduplicated"

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test that rate limiting doesn't cause errors on multiple requests."""
        # Use longer delay to avoid hitting SAM.gov's strict rate limits
        async with SamGovClient(rate_limit_delay=2.0) as client:
            # Make 2 requests (SAM.gov has strict per-minute limits)
            for i in range(2):
                result = await client.search_opportunities(
                    keywords=["technology"],
                    limit=1,
                )
                assert isinstance(result, SamSearchResult)
                print(f"Request {i+1}: {result.total_records} total records")

    @pytest.mark.asyncio
    async def test_search_all_with_pagination(self):
        """Test search_all_opportunities pagination."""
        # Use longer delay and smaller result set to avoid rate limits
        async with SamGovClient(rate_limit_delay=2.0) as client:
            opportunities = await client.search_all_opportunities(
                keywords=["ServiceNow"],  # More specific keyword
                posted_from=datetime.now() - timedelta(days=14),
                max_results=10,  # Smaller to minimize API calls
            )

        print(f"search_all_opportunities returned {len(opportunities)} results")
        assert len(opportunities) <= 10


class TestSamGovClientErrors:
    """Test error handling (no network required)."""

    @pytest.mark.asyncio
    async def test_missing_api_key_raises_error(self):
        """Missing API key should raise helpful error."""
        async with SamGovClient(api_key="") as client:
            with pytest.raises(SamGovError, match="SAM.gov API key required"):
                await client.search_opportunities(
                    keywords=["test"],
                    limit=1,
                )

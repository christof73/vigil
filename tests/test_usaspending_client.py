"""
Tests for USAspending.gov API client.

Unit tests use sample data - no network required.
Integration tests (marked with @pytest.mark.integration) hit the live API.
"""

import pytest
from datetime import datetime, timedelta

from vectis_intel.clients.usaspending import (
    USAspendingClient,
    USAspendingError,
    AwardSummary,
    AwardDetail,
    SearchResult,
)


# Sample API responses for unit tests
SAMPLE_SEARCH_RESPONSE = {
    "results": [
        {
            "Award ID": "70B03C22F00001234",
            "Recipient Name": "DELOITTE CONSULTING LLP",
            "Award Amount": 4500000.00,
            "Awarding Agency": "Department of the Treasury",
            "Start Date": "2025-06-01",
            "End Date": "2026-05-31",
            "NAICS Code": "541512",
            "Description": "ServiceNow GRC implementation and FISMA compliance services",
            "Award Type": "Definitive Contract",
            "generated_internal_id": "CONT_AWD_12345",
        },
        {
            "Award ID": "75N98020F00009876",
            "Recipient Name": "BOOZ ALLEN HAMILTON INC",
            "Award Amount": 2100000.00,
            "Awarding Agency": "Department of Homeland Security",
            "Start Date": "2025-08-01",
            "NAICS Code": "541512",
            "Description": "FISMA compliance monitoring platform",
            "Award Type": "Delivery Order",
            "generated_internal_id": "CONT_AWD_67890",
        },
    ],
    "page_metadata": {
        "page": 1,
        "hasNext": False,
        "total": 2,
    }
}

SAMPLE_AWARD_DETAIL = {
    "piid": "70B03C22F00001234",
    "description": "ServiceNow GRC implementation and FISMA compliance services",
    "type_description": "Definitive Contract",
    "total_obligation": 4500000.00,
    "period_of_performance_start_date": "2025-06-01",
    "period_of_performance_current_end_date": "2026-05-31",
    "generated_internal_id": "CONT_AWD_12345",
    "recipient": {
        "recipient_name": "DELOITTE CONSULTING LLP",
        "recipient_duns": "123456789",
        "recipient_uei": "ABC123DEF456",
    },
    "awarding_agency": {
        "toptier_agency": {
            "name": "Department of the Treasury"
        }
    },
    "funding_agency": {
        "toptier_agency": {
            "name": "Department of the Treasury"
        }
    },
    "latest_transaction_contract_data": {
        "naics": "541512",
        "naics_description": "Computer Systems Design Services",
        "product_or_service_code": "D399",
    },
    "place_of_performance": {
        "city_name": "Washington",
        "state_name": "District of Columbia",
        "country_name": "UNITED STATES",
    },
}


class TestAwardSummaryParsing:
    """Tests for AwardSummary parsing from API response."""

    def test_parse_award(self):
        """Test parsing an award from API response."""
        data = SAMPLE_SEARCH_RESPONSE["results"][0]
        award = AwardSummary.from_api_response(data)

        assert award.award_id == "70B03C22F00001234"
        assert award.recipient_name == "DELOITTE CONSULTING LLP"
        assert award.award_amount == 4500000.00
        assert award.awarding_agency == "Department of the Treasury"
        assert award.naics_code == "541512"
        assert "ServiceNow" in award.description

    def test_usaspending_url(self):
        """Test URL generation for award."""
        data = SAMPLE_SEARCH_RESPONSE["results"][0]
        award = AwardSummary.from_api_response(data)

        assert "usaspending.gov/award/CONT_AWD_12345" in award.usaspending_url

    def test_parse_minimal_award(self):
        """Test parsing award with minimal data."""
        data = {
            "Award ID": "TEST123",
            "Recipient Name": "TEST CORP",
            "Award Amount": 100000,
        }
        award = AwardSummary.from_api_response(data)

        assert award.award_id == "TEST123"
        assert award.recipient_name == "TEST CORP"
        assert award.award_amount == 100000


class TestAwardDetailParsing:
    """Tests for AwardDetail parsing."""

    def test_parse_detail(self):
        """Test parsing full award detail."""
        detail = AwardDetail.from_api_response(SAMPLE_AWARD_DETAIL)

        assert detail.award_id == "70B03C22F00001234"
        assert detail.recipient_name == "DELOITTE CONSULTING LLP"
        assert detail.recipient_uei == "ABC123DEF456"
        assert detail.award_amount == 4500000.00
        assert detail.awarding_agency == "Department of the Treasury"
        assert detail.naics_code == "541512"
        assert detail.naics_description == "Computer Systems Design Services"
        assert "Washington" in detail.place_of_performance


class TestSearchResult:
    """Tests for SearchResult parsing."""

    def test_search_result_parsing(self):
        """Test parsing search result."""
        result = SearchResult.from_api_response(SAMPLE_SEARCH_RESPONSE)

        assert len(result.awards) == 2
        assert result.total_count == 2
        assert result.page == 1
        assert result.has_next is False

    def test_search_result_with_pagination(self):
        """Test search result with pagination."""
        data = {
            "results": SAMPLE_SEARCH_RESPONSE["results"],
            "page_metadata": {
                "page": 1,
                "hasNext": True,
                "total": 100,
            }
        }
        result = SearchResult.from_api_response(data)

        assert result.has_next is True
        assert result.total_count == 100


class TestUSAspendingClientUnit:
    """Unit tests for USAspendingClient (no network)."""

    def test_client_init(self):
        """Test client initialization."""
        client = USAspendingClient(
            rate_limit_delay=1.0,
            timeout=30.0,
            max_retries=3,
        )
        assert client.rate_limit_delay == 1.0
        assert client.timeout == 30.0
        assert client.max_retries == 3

    def test_default_award_types(self):
        """Test default award type codes."""
        client = USAspendingClient()
        assert "A" in client.DEFAULT_AWARD_TYPES  # BPA Call
        assert "B" in client.DEFAULT_AWARD_TYPES  # Purchase Order
        assert "C" in client.DEFAULT_AWARD_TYPES  # Delivery Order
        assert "D" in client.DEFAULT_AWARD_TYPES  # Definitive Contract


# ─── INTEGRATION TESTS ────────────────────────────────────────────────────────
# These tests hit the live USAspending API.
# Run with: pytest tests/test_usaspending_client.py -v -m integration

@pytest.mark.integration
class TestUSAspendingClientIntegration:
    """Integration tests that hit the live USAspending API."""

    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return USAspendingClient(rate_limit_delay=1.0)

    @pytest.mark.asyncio
    async def test_search_servicenow_keyword(self, client):
        """Test searching for ServiceNow awards."""
        async with client:
            result = await client.search_awards(
                keywords=["ServiceNow"],
                awarded_after="2024-01-01",
                limit=5,
            )

        assert isinstance(result, SearchResult)
        # May or may not have results, but should not error
        assert result.awards is not None

    @pytest.mark.asyncio
    async def test_search_with_naics(self, client):
        """Test searching by NAICS code."""
        async with client:
            result = await client.search_awards(
                naics_codes=["541512"],
                awarded_after="2024-01-01",
                limit=5,
            )

        assert isinstance(result, SearchResult)
        for award in result.awards:
            # NAICS should be 541512 or related
            if award.naics_code:
                assert award.naics_code.startswith("541")

    @pytest.mark.asyncio
    async def test_search_by_recipient(self, client):
        """Test searching by recipient name."""
        async with client:
            awards = await client.search_by_recipient(
                recipient_name="Deloitte",
                naics_codes=["541512"],
                awarded_within_days=365,
                max_results=5,
            )

        assert isinstance(awards, list)
        # Deloitte should have awards in this NAICS
        if len(awards) > 0:
            assert "DELOITTE" in awards[0].recipient_name.upper()

    @pytest.mark.asyncio
    async def test_search_by_agency(self, client):
        """Test searching by agency name."""
        async with client:
            awards = await client.search_by_agency(
                agency_name="Department of the Treasury",
                naics_codes=["541512"],
                awarded_within_days=365,
                max_results=5,
            )

        assert isinstance(awards, list)

    @pytest.mark.asyncio
    async def test_pagination(self, client):
        """Test that pagination works."""
        async with client:
            # First page
            result1 = await client.search_awards(
                naics_codes=["541512"],
                awarded_after="2024-01-01",
                limit=2,
                page=1,
            )

            if result1.has_next:
                # Second page
                result2 = await client.search_awards(
                    naics_codes=["541512"],
                    awarded_after="2024-01-01",
                    limit=2,
                    page=2,
                )

                # Should have different results
                if len(result1.awards) > 0 and len(result2.awards) > 0:
                    assert result1.awards[0].award_id != result2.awards[0].award_id

    @pytest.mark.asyncio
    async def test_search_by_watchlist(self, client):
        """Test searching by watchlist configuration."""
        watchlist = {
            "keywords": {
                "servicenow": ["ServiceNow", "SNOW platform"],
                "grc": ["GRC", "governance risk compliance"],
            },
            "naics_codes": {
                "primary": ["541512"],
                "secondary": ["541511"],
            }
        }

        async with client:
            awards = await client.search_by_watchlist(
                watchlist=watchlist,
                awarded_within_days=365,
                max_per_keyword=5,
            )

        assert isinstance(awards, list)
        # Should have deduplicated results
        award_ids = [a.award_id for a in awards]
        assert len(award_ids) == len(set(award_ids))

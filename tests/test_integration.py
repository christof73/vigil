"""
Integration tests for the full pipeline.
Tests ProcurementAgent + IntelStore working together.
"""

import json
import os
import tempfile
import pytest

from vectis_intel.store import IntelStore
from vectis_intel.agents import ProcurementAgent, load_watchlist
from vectis_intel.clients.sam_gov import SamOpportunity


# Sample watchlist
SAMPLE_WATCHLIST = {
    "keywords": {
        "servicenow": ["ServiceNow"],
        "grc": ["GRC", "governance risk compliance"],
        "fisma": ["FISMA"],
    }
}

# Sample opportunities
SAMPLE_OPPORTUNITIES = [
    SamOpportunity(
        notice_id="opp001",
        title="ServiceNow GRC Implementation for FISMA Compliance",
        solicitation_number="TREAS-2026-001",
        department="DEPARTMENT OF THE TREASURY",
        posted_date="2026-03-01",
        response_deadline="2026-04-01T17:00:00-04:00",
        naics_code="541512",
        notice_type="Combined Synopsis/Solicitation",
        resource_links=["https://sam.gov/opp/opp001/view"],
    ),
    SamOpportunity(
        notice_id="opp002",
        title="Cloud Infrastructure Modernization",
        solicitation_number="DHS-2026-002",
        department="DEPARTMENT OF HOMELAND SECURITY",
        posted_date="2026-03-05",
        response_deadline="2026-04-15T17:00:00-04:00",
        naics_code="518210",
        notice_type="Sources Sought",
        resource_links=["https://sam.gov/opp/opp002/view"],
    ),
    SamOpportunity(
        notice_id="opp003",
        title="GRC Platform Support Services",
        solicitation_number="GSA-2026-003",
        department="GENERAL SERVICES ADMINISTRATION",
        posted_date="2026-03-06",
        naics_code="541512",
        notice_type="Award Notice",
        resource_links=["https://sam.gov/opp/opp003/view"],
    ),
]


@pytest.fixture
def store():
    """Create a temporary IntelStore for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    store = IntelStore(db_path)
    yield store
    store.close()
    os.unlink(db_path)


class TestFullPipeline:
    """Integration tests for full extraction → storage pipeline."""

    def test_extract_and_store(self, store):
        """Test extracting signals from opportunities and storing them."""
        agent = ProcurementAgent(SAMPLE_WATCHLIST)

        # Extract signals
        results, extracted, skipped = agent.extract_batch(
            SAMPLE_OPPORTUNITIES,
            existing_urls=set()
        )

        assert extracted == 3
        assert skipped == 0

        # Store each result
        for result in results:
            if not result.skipped:
                store.sources.create(result.source)
                store.signals.create(result.signal, [result.signal_source])

        # Verify signals were stored
        active_signals = store.signals.list_active(limit=10)
        assert len(active_signals) == 3

        # Verify domain tags were stored
        grc_signals = store.signals.list_by_domain("grc")
        assert len(grc_signals) == 2  # opp001 and opp003

        servicenow_signals = store.signals.list_by_domain("servicenow")
        assert len(servicenow_signals) == 1  # opp001

    def test_deduplication_across_runs(self, store):
        """Test that duplicate opportunities are skipped on re-extraction."""
        agent = ProcurementAgent(SAMPLE_WATCHLIST)

        # First run - extract and store
        results1, extracted1, skipped1 = agent.extract_batch(
            SAMPLE_OPPORTUNITIES,
            existing_urls=set()
        )

        for result in results1:
            if not result.skipped:
                store.sources.create(result.source)
                store.signals.create(result.signal, [result.signal_source])

        assert extracted1 == 3

        # Build set of existing URLs
        existing_urls = {r.source.url for r in results1 if not result.skipped}

        # Second run - same opportunities should be skipped
        results2, extracted2, skipped2 = agent.extract_batch(
            SAMPLE_OPPORTUNITIES,
            existing_urls=existing_urls
        )

        assert extracted2 == 0
        assert skipped2 == 3

        # Still only 3 signals in store
        active_signals = store.signals.list_active(limit=10)
        assert len(active_signals) == 3

    def test_evidence_chain_after_extraction(self, store):
        """Test that evidence chain traversal works after extraction."""
        agent = ProcurementAgent(SAMPLE_WATCHLIST)

        # Extract and store one opportunity
        result = agent.extract_from_sam_opportunity(SAMPLE_OPPORTUNITIES[0])
        store.sources.create(result.source)
        signal = store.signals.create(result.signal, [result.signal_source])

        # Trace the evidence chain
        chain = store.evidence.trace_signal(signal.signal_id)

        assert "error" not in chain
        assert chain["signal_type"] == "rfp_posted"
        assert len(chain["sources"]) == 1
        assert chain["sources"][0]["url"] == "https://sam.gov/opp/opp001/view"

    def test_integrity_after_extraction(self, store):
        """Test that integrity audit passes after extraction."""
        agent = ProcurementAgent(SAMPLE_WATCHLIST)

        # Extract and store
        results, _, _ = agent.extract_batch(SAMPLE_OPPORTUNITIES, existing_urls=set())
        for result in results:
            if not result.skipped:
                store.sources.create(result.source)
                store.signals.create(result.signal, [result.signal_source])

        # Run integrity audit
        audit = store.integrity.run_integrity_audit()

        assert audit["orphan_signals"] == 0
        assert audit["integrity_ok"] is True

    def test_query_by_signal_type(self, store):
        """Test querying signals by type after extraction."""
        agent = ProcurementAgent(SAMPLE_WATCHLIST)

        # Extract and store
        results, _, _ = agent.extract_batch(SAMPLE_OPPORTUNITIES, existing_urls=set())
        for result in results:
            if not result.skipped:
                store.sources.create(result.source)
                store.signals.create(result.signal, [result.signal_source])

        # Query by type
        rfp_signals = store.signals.list_by_type("rfp_posted")
        award_signals = store.signals.list_by_type("contract_awarded")

        assert len(rfp_signals) == 2  # opp001, opp002
        assert len(award_signals) == 1  # opp003

    def test_source_deduplication_by_url(self, store):
        """Test that sources can be looked up by URL for deduplication."""
        agent = ProcurementAgent()

        # Extract first opportunity
        result = agent.extract_from_sam_opportunity(SAMPLE_OPPORTUNITIES[0])
        store.sources.create(result.source)
        store.signals.create(result.signal, [result.signal_source])

        # Check if source URL exists
        existing = store.sources.get_by_url("https://sam.gov/opp/opp001/view")
        assert existing is not None
        assert existing["title"] == "ServiceNow GRC Implementation for FISMA Compliance"

        # Non-existent URL
        not_found = store.sources.get_by_url("https://sam.gov/opp/nonexistent/view")
        assert not_found is None

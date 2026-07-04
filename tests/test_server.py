"""
Tests for the MCP server functionality.
"""

import json
import os
import pytest
import tempfile
from unittest.mock import patch, AsyncMock

# Mock environment before importing server module
os.environ["INTEL_DB_PATH"] = ":memory:"
os.environ["SAM_GOV_API_KEY"] = "test-api-key"


class TestServerTools:
    """Tests for MCP server tool definitions."""

    def test_list_tools_returns_all_tools(self):
        """Verify all expected tools are defined."""
        import asyncio
        from vectis_intel.server import list_tools

        tools = asyncio.run(list_tools())
        tool_names = {t.name for t in tools}

        expected_tools = {
            "ping",
            "reload_watchlist",
            "scan_opportunities",
            "get_opportunity_detail",
            "scan_awards",
            "search_competitor_awards",
            "list_signals",
            "trace_evidence",
            "list_stale_signals",
            "integrity_audit",
            "agent_trust_report",
            "pipeline_summary",
            "community_ingest",
            "community_score",
            "community_digest",
            "community_promote",
            "community_status",
            "sync_taxonomy",
        }

        assert tool_names == expected_tools

    def test_tool_schemas_have_required_fields(self):
        """Verify tool schemas have proper structure."""
        import asyncio
        from vectis_intel.server import list_tools

        tools = asyncio.run(list_tools())

        for tool in tools:
            assert tool.name is not None
            assert tool.description is not None
            assert tool.inputSchema is not None
            assert tool.inputSchema.get("type") == "object"


class TestPingHandler:
    """Tests for ping tool handler."""

    def test_ping_returns_status(self):
        """Ping should return server status."""
        import asyncio
        from vectis_intel.server import handle_ping

        result = asyncio.run(handle_ping())
        assert len(result) == 1

        data = json.loads(result[0].text)
        assert data["status"] == "ok"
        assert data["server"] == "vectis-intel"
        assert data["version"] == "0.1.0"
        assert "database" in data
        assert "timestamp" in data


class TestListSignalsHandler:
    """Tests for list_signals tool handler."""

    @pytest.fixture
    def setup_store_with_signals(self):
        """Create a store with test signals."""
        from vectis_intel.store import (
            IntelStore, Source, Signal, SignalSource,
            SourceType, CollectionMethod, SignalType, Confidence, SourceRelevance
        )

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        store = IntelStore(db_path)

        # Create test data
        source = Source(
            source_type=SourceType.PROCUREMENT_POSTING,
            title="Test Opportunity",
            url="https://sam.gov/opp/test123/view",
            publisher="SAM.gov",
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="test",
        )
        store.sources.create(source)

        signal = Signal(
            signal_type=SignalType.RFP_POSTED,
            summary="Test RFP posted",
            confidence=Confidence.VERIFIED,
            confidence_rationale="Test signal",
            domain_tags='["servicenow", "grc"]',
            extracted_by="test",
        )
        signal_source = SignalSource(
            signal_id=signal.signal_id,
            source_id=source.source_id,
            relevance=SourceRelevance.PRIMARY,
        )
        store.signals.create(signal, [signal_source])

        yield store, db_path

        store.close()
        os.unlink(db_path)

    def test_list_signals_returns_signals(self, setup_store_with_signals):
        """list_signals should return stored signals."""
        import asyncio
        from vectis_intel import server

        store, db_path = setup_store_with_signals

        # Patch get_store to use our test store
        with patch.object(server, "_store", store):
            result = asyncio.run(server.handle_list_signals({"limit": 10}))

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert len(data["signals"]) == 1
        assert "Test RFP" in data["signals"][0]["summary"]

    def test_list_signals_by_domain(self, setup_store_with_signals):
        """list_signals should filter by domain tag."""
        import asyncio
        from vectis_intel import server

        store, db_path = setup_store_with_signals

        with patch.object(server, "_store", store):
            result = asyncio.run(server.handle_list_signals({"domain_tag": "servicenow"}))

        data = json.loads(result[0].text)
        assert data["count"] == 1

        # Test domain that doesn't exist
        with patch.object(server, "_store", store):
            result = asyncio.run(server.handle_list_signals({"domain_tag": "fedramp"}))

        data = json.loads(result[0].text)
        assert data["count"] == 0


class TestIntegrityAuditHandler:
    """Tests for integrity_audit handler."""

    def test_integrity_audit_returns_report(self):
        """integrity_audit should return audit report."""
        import asyncio
        from vectis_intel.store import IntelStore
        from vectis_intel import server

        # Use in-memory database
        store = IntelStore(":memory:")

        with patch.object(server, "_store", store):
            result = asyncio.run(server.handle_integrity_audit())

        data = json.loads(result[0].text)
        assert "integrity_ok" in data
        assert "orphan_signals" in data
        assert "stale_signals" in data


class TestTraceEvidenceHandler:
    """Tests for trace_evidence handler."""

    @pytest.fixture
    def setup_store_with_chain(self):
        """Create a store with evidence chain."""
        from vectis_intel.store import (
            IntelStore, Source, Signal, SignalSource,
            SourceType, CollectionMethod, SignalType, Confidence, SourceRelevance
        )

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        store = IntelStore(db_path)

        # Create test chain
        source = Source(
            source_type=SourceType.PROCUREMENT_POSTING,
            title="Chain Test",
            url="https://sam.gov/opp/chain123/view",
            publisher="SAM.gov",
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="test",
        )
        store.sources.create(source)

        signal = Signal(
            signal_type=SignalType.RFP_POSTED,
            summary="Chain test RFP",
            confidence=Confidence.VERIFIED,
            confidence_rationale="Test chain signal",
            extracted_by="test",
        )
        signal_source = SignalSource(
            signal_id=signal.signal_id,
            source_id=source.source_id,
            relevance=SourceRelevance.PRIMARY,
        )
        created_signal = store.signals.create(signal, [signal_source])

        yield store, db_path, created_signal.signal_id

        store.close()
        os.unlink(db_path)

    def test_trace_evidence_returns_chain(self, setup_store_with_chain):
        """trace_evidence should return evidence chain."""
        import asyncio
        from vectis_intel import server

        store, db_path, signal_id = setup_store_with_chain

        with patch.object(server, "_store", store):
            result = asyncio.run(server.handle_trace_evidence({"signal_id": signal_id}))

        data = json.loads(result[0].text)
        assert "signal_type" in data
        assert "sources" in data
        assert len(data["sources"]) == 1
        assert data["sources"][0]["url"] == "https://sam.gov/opp/chain123/view"

    def test_trace_evidence_missing_id(self):
        """trace_evidence should error without ID."""
        import asyncio
        from vectis_intel import server

        result = asyncio.run(server.handle_trace_evidence({}))
        assert "Must provide" in result[0].text


class TestScanOpportunitiesHandler:
    """Tests for scan_opportunities handler."""

    def test_scan_without_api_key(self):
        """scan_opportunities should error without API key."""
        import asyncio
        from vectis_intel import server

        # Save original value
        original_key = server.SAM_GOV_API_KEY

        try:
            # Clear API key
            server.SAM_GOV_API_KEY = ""

            result = asyncio.run(server.handle_scan_opportunities({}))
            data = json.loads(result[0].text)
            assert "error" in data
            assert "SAM_GOV_API_KEY" in data["error"]
        finally:
            # Restore original
            server.SAM_GOV_API_KEY = original_key


class TestGetOpportunityDetailHandler:
    """Tests for get_opportunity_detail handler."""

    def test_get_detail_without_api_key(self):
        """get_opportunity_detail should error without API key."""
        import asyncio
        from vectis_intel import server

        original_key = server.SAM_GOV_API_KEY

        try:
            server.SAM_GOV_API_KEY = ""

            result = asyncio.run(server.handle_get_opportunity_detail({"notice_id": "test"}))
            data = json.loads(result[0].text)
            assert "error" in data
        finally:
            server.SAM_GOV_API_KEY = original_key

    def test_get_detail_missing_params(self):
        """get_opportunity_detail should require notice_id or solicitation_number."""
        import asyncio
        from vectis_intel import server

        result = asyncio.run(server.handle_get_opportunity_detail({}))
        data = json.loads(result[0].text)
        assert "error" in data
        assert "notice_id" in data["error"] or "solicitation" in data["error"]

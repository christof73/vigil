"""
Smoke tests for the store package.
Verifies the refactor from intel_store.py didn't break anything.
"""

import json
import os
import tempfile
import pytest

from vectis_intel.store import (
    IntelStore,
    IntegrityError,
    Source, Signal, SignalSource, Correlation, Opportunity, Verification,
    SourceType, CollectionMethod, SignalType, Confidence, SourceRelevance,
    CorrelationType, OpportunityLane, OpportunityStatus,
    VerificationTarget, VerificationResult, HumanVerdict,
)


@pytest.fixture
def store():
    """Create a temporary IntelStore for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    store = IntelStore(db_path)
    yield store
    store.close()
    os.unlink(db_path)


class TestSourceRepo:
    """Tests for SourceRepo."""

    def test_create_and_get(self, store):
        source = store.sources.create(Source(
            source_type=SourceType.PROCUREMENT_POSTING,
            title="Test RFP",
            url="https://sam.gov/opp/test123/view",
            publisher="SAM.gov",
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="test_agent",
        ))

        retrieved = store.sources.get(source.source_id)
        assert retrieved is not None
        assert retrieved["title"] == "Test RFP"
        assert retrieved["url"] == "https://sam.gov/opp/test123/view"

    def test_get_by_url(self, store):
        url = "https://sam.gov/opp/unique123/view"
        store.sources.create(Source(
            source_type=SourceType.PROCUREMENT_POSTING,
            title="Unique Source",
            url=url,
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="test_agent",
        ))

        # Should find by URL
        found = store.sources.get_by_url(url)
        assert found is not None
        assert found["title"] == "Unique Source"

        # Should not find non-existent URL
        not_found = store.sources.get_by_url("https://example.com/not-exists")
        assert not_found is None

    def test_list_by_type(self, store):
        store.sources.create(Source(
            source_type=SourceType.PROCUREMENT_POSTING,
            title="Procurement 1",
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="test",
        ))
        store.sources.create(Source(
            source_type=SourceType.JOB_POSTING,
            title="Job 1",
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="test",
        ))

        procurements = store.sources.list_by_type(SourceType.PROCUREMENT_POSTING)
        assert len(procurements) == 1
        assert procurements[0]["title"] == "Procurement 1"


class TestSignalRepo:
    """Tests for SignalRepo."""

    def test_create_with_source(self, store):
        # First create a source
        source = store.sources.create(Source(
            source_type=SourceType.PROCUREMENT_POSTING,
            title="Test Source",
            url="https://sam.gov/test",
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="test",
        ))

        # Create signal with source link
        signal = store.signals.create(
            Signal(
                signal_type=SignalType.RFP_POSTED,
                summary="Test RFP posted",
                confidence=Confidence.VERIFIED,
                confidence_rationale="Direct posting",
                extracted_by="test_agent",
            ),
            sources=[SignalSource(
                signal_id="",  # Will be set by create()
                source_id=source.source_id,
                relevance=SourceRelevance.PRIMARY,
            )]
        )

        assert signal.signal_id is not None
        retrieved = store.signals.get_with_sources(signal.signal_id)
        assert len(retrieved["sources"]) == 1

    def test_orphan_signal_rejected(self, store):
        """Signals without sources must be rejected."""
        with pytest.raises(IntegrityError, match="at least one source"):
            store.signals.create(
                Signal(
                    signal_type=SignalType.RFP_POSTED,
                    summary="Orphan signal",
                    confidence=Confidence.SPECULATIVE,
                    confidence_rationale="No sources",
                    extracted_by="test",
                ),
                sources=[]  # No sources - should fail
            )

    def test_list_by_type(self, store):
        source = store.sources.create(Source(
            source_type=SourceType.PROCUREMENT_POSTING,
            title="Source",
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="test",
        ))

        store.signals.create(
            Signal(
                signal_type=SignalType.RFP_POSTED,
                summary="RFP signal",
                confidence=Confidence.VERIFIED,
                confidence_rationale="Test",
                extracted_by="test",
            ),
            sources=[SignalSource(signal_id="", source_id=source.source_id, relevance=SourceRelevance.PRIMARY)]
        )

        rfps = store.signals.list_by_type(SignalType.RFP_POSTED)
        assert len(rfps) == 1

    def test_list_by_domain(self, store):
        source = store.sources.create(Source(
            source_type=SourceType.PROCUREMENT_POSTING,
            title="Source",
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="test",
        ))

        store.signals.create(
            Signal(
                signal_type=SignalType.RFP_POSTED,
                summary="GRC signal",
                domain_tags=json.dumps(["grc", "servicenow"]),
                confidence=Confidence.VERIFIED,
                confidence_rationale="Test",
                extracted_by="test",
            ),
            sources=[SignalSource(signal_id="", source_id=source.source_id, relevance=SourceRelevance.PRIMARY)]
        )

        grc_signals = store.signals.list_by_domain("grc")
        assert len(grc_signals) == 1

        other_signals = store.signals.list_by_domain("fedramp")
        assert len(other_signals) == 0


class TestCorrelationRepo:
    """Tests for CorrelationRepo."""

    def test_auto_compute_strength(self, store):
        """Correlation strength should be auto-computed from signal confidence."""
        source = store.sources.create(Source(
            source_type=SourceType.PROCUREMENT_POSTING,
            title="Source",
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="test",
        ))

        # Create 3 verified signals
        signal_ids = []
        for i in range(3):
            sig = store.signals.create(
                Signal(
                    signal_type=SignalType.RFP_POSTED,
                    summary=f"Signal {i}",
                    confidence=Confidence.VERIFIED,
                    confidence_rationale="Test",
                    extracted_by="test",
                ),
                sources=[SignalSource(signal_id="", source_id=source.source_id, relevance=SourceRelevance.PRIMARY)]
            )
            signal_ids.append(sig.signal_id)

        # Create correlation - strength should be auto-computed as STRONG (3+ verified)
        corr = store.correlations.create(Correlation(
            signal_ids=json.dumps(signal_ids),
            correlation_type=CorrelationType.DOMAIN_CONVERGENCE,
            hypothesis="Test hypothesis",
            strength="",  # Should be auto-computed
            generated_by="test",
        ))

        assert corr.strength == "strong"

    def test_minimum_two_signals(self, store):
        """Correlations require at least 2 signals."""
        source = store.sources.create(Source(
            source_type=SourceType.PROCUREMENT_POSTING,
            title="Source",
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="test",
        ))
        sig = store.signals.create(
            Signal(
                signal_type=SignalType.RFP_POSTED,
                summary="Single signal",
                confidence=Confidence.VERIFIED,
                confidence_rationale="Test",
                extracted_by="test",
            ),
            sources=[SignalSource(signal_id="", source_id=source.source_id, relevance=SourceRelevance.PRIMARY)]
        )

        with pytest.raises(IntegrityError, match="minimum 2 signals"):
            store.correlations.create(Correlation(
                signal_ids=json.dumps([sig.signal_id]),  # Only 1 signal
                correlation_type=CorrelationType.DOMAIN_CONVERGENCE,
                hypothesis="Test",
                strength="",
                generated_by="test",
            ))


class TestOpportunityRepo:
    """Tests for OpportunityRepo."""

    def test_human_only_creation(self, store):
        """Opportunities must be created by humans only."""
        with pytest.raises(IntegrityError, match="must be 'human'"):
            store.opportunities.create(Opportunity(
                title="AI-created opportunity",
                lane=OpportunityLane.CORE_GRC,
                status=OpportunityStatus.WATCHING,
                source_correlation_ids=json.dumps([]),
                verification_checklist=json.dumps({"items": []}),
                verification_score=0.0,
                fit_score=0.5,
                created_by="ai_agent",  # Not human - should fail
            ))


class TestIntegrityEngine:
    """Tests for IntegrityEngine."""

    def test_verification_score_computation(self, store):
        checklist = {
            "items": [
                {"claim": "Test 1", "verified": True},
                {"claim": "Test 2", "verified": True},
                {"claim": "Test 3", "verified": False},
                {"claim": "Test 4", "verified": False},
            ]
        }
        score = store.integrity.compute_verification_score(checklist)
        assert score == 0.5  # 2/4 verified

    def test_integrity_audit(self, store):
        audit = store.integrity.run_integrity_audit()
        assert "orphan_signals" in audit
        assert "stale_signals" in audit
        assert "non_human_opportunities" in audit
        assert "integrity_ok" in audit
        assert audit["integrity_ok"] is True  # Empty DB should be OK


class TestEvidenceChain:
    """Tests for EvidenceChain."""

    def test_trace_signal(self, store):
        source = store.sources.create(Source(
            source_type=SourceType.PROCUREMENT_POSTING,
            title="Test Source",
            url="https://sam.gov/test",
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="test",
        ))

        signal = store.signals.create(
            Signal(
                signal_type=SignalType.RFP_POSTED,
                summary="Test signal",
                confidence=Confidence.VERIFIED,
                confidence_rationale="Direct posting",
                extracted_by="test",
            ),
            sources=[SignalSource(
                signal_id="",
                source_id=source.source_id,
                relevance=SourceRelevance.PRIMARY,
                excerpt="Test excerpt",
            )]
        )

        chain = store.evidence.trace_signal(signal.signal_id)
        assert "sources" in chain
        assert len(chain["sources"]) == 1
        assert chain["sources"][0]["url"] == "https://sam.gov/test"

    def test_trace_nonexistent(self, store):
        chain = store.evidence.trace_signal("nonexistent-id")
        assert "error" in chain


class TestFullWorkflow:
    """End-to-end workflow test matching the original demo."""

    def test_full_evidence_chain(self, store):
        """Test the complete Source → Signal → Correlation → Opportunity flow."""

        # 1. Create source
        src = store.sources.create(Source(
            source_type=SourceType.PROCUREMENT_POSTING,
            title="RFI: GRC Modernization - Treasury",
            url="https://sam.gov/opp/abc123/view",
            publisher="SAM.gov",
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="procurement_scanner",
        ))

        # 2. Create signal with source
        sig1 = store.signals.create(
            Signal(
                signal_type=SignalType.RFP_POSTED,
                summary="Treasury posted RFI for GRC modernization",
                entity_refs=json.dumps(["dept_treasury"]),
                domain_tags=json.dumps(["grc", "federal"]),
                confidence=Confidence.VERIFIED,
                confidence_rationale="Direct SAM.gov posting",
                extracted_by="procurement_scanner",
            ),
            sources=[SignalSource(
                signal_id="",
                source_id=src.source_id,
                relevance=SourceRelevance.PRIMARY,
            )]
        )

        # Create second signal for correlation
        src2 = store.sources.create(Source(
            source_type=SourceType.JOB_POSTING,
            title="Deloitte GRC hiring",
            url="https://linkedin.com/jobs/123",
            publisher="LinkedIn",
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="competitive_intel",
        ))

        sig2 = store.signals.create(
            Signal(
                signal_type=SignalType.HIRING_VELOCITY,
                summary="Deloitte hiring 6 GRC roles",
                confidence=Confidence.VERIFIED,
                confidence_rationale="LinkedIn posting",
                extracted_by="competitive_intel",
            ),
            sources=[SignalSource(
                signal_id="",
                source_id=src2.source_id,
                relevance=SourceRelevance.PRIMARY,
            )]
        )

        # 3. Create correlation
        corr = store.correlations.create(Correlation(
            signal_ids=json.dumps([sig1.signal_id, sig2.signal_id]),
            correlation_type=CorrelationType.DOMAIN_CONVERGENCE,
            hypothesis="GRC modernization wave",
            strength="",
            generated_by="qualifier_agent",
        ))

        # 4. Human review
        store.correlations.review(
            corr.correlation_id,
            HumanVerdict.CONFIRMED,
            "Pattern checks out"
        )

        # 5. Create opportunity (human only)
        opp = store.opportunities.create(Opportunity(
            title="Treasury GRC Opportunity",
            lane=OpportunityLane.CORE_GRC,
            status=OpportunityStatus.RESEARCHING,
            source_correlation_ids=json.dumps([corr.correlation_id]),
            verification_checklist=json.dumps({
                "items": [
                    {"claim": "RFI exists", "verified": True},
                    {"claim": "Deloitte staffing", "verified": True},
                ]
            }),
            verification_score=0.0,
            fit_score=0.85,
            created_by="human",
        ))

        # 6. Trace evidence chain
        chain = store.evidence.trace_opportunity(opp.opportunity_id)
        assert chain["title"] == "Treasury GRC Opportunity"
        assert len(chain["evidence_chain"]) == 1
        assert len(chain["evidence_chain"][0]["signals"]) == 2

        # 7. Run integrity audit
        audit = store.integrity.run_integrity_audit()
        assert audit["orphan_signals"] == 0
        assert audit["non_human_opportunities"] == 0
        assert audit["integrity_ok"] is True

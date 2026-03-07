"""
Procurement Agent
=================
Signal extraction from SAM.gov and USAspending data.

This is the critical layer where data quality is enforced.
Every signal MUST:
- Link to at least one source with a verifiable URL
- Have an appropriate confidence level
- Contain a factual summary (no interpretation)
- Include domain_tags and entity_refs for downstream correlation
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..clients.sam_gov import SamOpportunity, SamOpportunityDetail
from ..clients.usaspending import AwardSummary, AwardDetail
from ..store import (
    Source, Signal, SignalSource,
    SourceType, CollectionMethod, SignalType, Confidence, SourceRelevance,
)

logger = logging.getLogger("vectis_intel.procurement")


@dataclass
class ExtractionResult:
    """Result of extracting signals from an opportunity."""
    source: Source
    signal: Signal
    signal_source: SignalSource
    domain_tags: list[str]
    entity_refs: list[str]
    skipped: bool = False
    skip_reason: Optional[str] = None


class ProcurementAgent:
    """
    Transforms raw API responses into Source + Signal pairs
    for the IntelStore.

    Usage:
        agent = ProcurementAgent(watchlist)
        result = agent.extract_from_sam_opportunity(opportunity)
        if not result.skipped:
            store.sources.create(result.source)
            store.signals.create(result.signal, [result.signal_source])
    """

    # Agency name normalization patterns
    AGENCY_PATTERNS = [
        (r"DEPT\.?\s*OF\s*", "Department of "),
        (r"^DEPARTMENT OF THE\s+", ""),  # Remove "THE" for cleaner refs
        (r"\.+", "."),  # Collapse multiple dots
    ]

    # Notice type to signal type mapping
    NOTICE_TYPE_MAP = {
        "Solicitation": SignalType.RFP_POSTED,
        "Combined Synopsis/Solicitation": SignalType.RFP_POSTED,
        "Presolicitation": SignalType.RFP_POSTED,
        "Sources Sought": SignalType.RFP_POSTED,
        "Special Notice": SignalType.RFP_POSTED,
        "Award Notice": SignalType.CONTRACT_AWARDED,
        "Intent to Bundle": SignalType.RFP_POSTED,
        "Sale of Surplus Property": SignalType.RFP_POSTED,
    }

    def __init__(self, watchlist: Optional[dict] = None):
        """
        Initialize with optional watchlist for domain tag inference.

        Args:
            watchlist: Dict with "keywords" mapping category -> [terms]
        """
        self.watchlist = watchlist or {}
        self._build_keyword_patterns()

    def _build_keyword_patterns(self):
        """Pre-compile regex patterns for keyword matching."""
        self.keyword_patterns: dict[str, list[re.Pattern]] = {}

        keywords_config = self.watchlist.get("keywords", {})
        for category, terms in keywords_config.items():
            patterns = []
            for term in terms:
                # Case-insensitive word boundary match
                pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
                patterns.append(pattern)
            self.keyword_patterns[category] = patterns

    def _normalize_agency(self, agency_name: str) -> str:
        """Normalize agency name for entity_refs."""
        if not agency_name:
            return ""

        name = agency_name.strip()

        # Apply normalization patterns
        for pattern, replacement in self.AGENCY_PATTERNS:
            name = re.sub(pattern, replacement, name, flags=re.IGNORECASE)

        # Take first part (top-level agency) if hierarchical
        if "." in name:
            name = name.split(".")[0].strip()

        return name.strip()

    def _agency_to_ref(self, agency_name: str) -> str:
        """Convert agency name to snake_case entity reference."""
        normalized = self._normalize_agency(agency_name)
        if not normalized:
            return ""

        # Convert to snake_case
        ref = normalized.lower()
        ref = re.sub(r"[^a-z0-9]+", "_", ref)
        ref = re.sub(r"_+", "_", ref)
        ref = ref.strip("_")

        return ref

    def infer_domain_tags(self, title: str, description: Optional[str] = None) -> list[str]:
        """
        Infer domain tags from title and description using watchlist keywords.

        Returns list of matching category names (e.g., ["servicenow", "grc", "fisma"])
        """
        if not self.keyword_patterns:
            return []

        text = title or ""
        if description:
            text = f"{text} {description}"

        matched_tags = []
        for category, patterns in self.keyword_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    matched_tags.append(category)
                    break  # One match per category is enough

        return matched_tags

    def _build_summary(self, opp: SamOpportunity) -> str:
        """
        Build factual summary for signal.

        Template: "{agency} posted {type} for '{title}' (SOL# {solicitationNumber}),
                   NAICS {naicsCode}, response due {responseDeadLine}."
        """
        agency = self._normalize_agency(opp.department) or "Unknown agency"
        notice_type = opp.notice_type or opp.base_type or "opportunity"

        parts = [f"{agency} posted {notice_type}"]

        # Title (truncate if too long)
        title = opp.title or "Untitled"
        if len(title) > 100:
            title = title[:97] + "..."
        parts.append(f"for '{title}'")

        # Solicitation number
        if opp.solicitation_number:
            parts.append(f"(SOL# {opp.solicitation_number})")

        # NAICS
        if opp.naics_code:
            parts.append(f", NAICS {opp.naics_code}")

        # Response deadline
        if opp.response_deadline:
            # Parse and format deadline
            try:
                if "T" in opp.response_deadline:
                    dt = datetime.fromisoformat(opp.response_deadline.replace("Z", "+00:00"))
                    deadline_str = dt.strftime("%Y-%m-%d")
                else:
                    deadline_str = opp.response_deadline
                parts.append(f", response due {deadline_str}")
            except (ValueError, TypeError):
                parts.append(f", response due {opp.response_deadline}")

        return " ".join(parts) + "."

    def _get_signal_type(self, opp: SamOpportunity) -> str:
        """Determine signal type from notice type."""
        notice_type = opp.notice_type or opp.base_type or ""

        for key, signal_type in self.NOTICE_TYPE_MAP.items():
            if key.lower() in notice_type.lower():
                return signal_type

        # Default to RFP_POSTED for unknown types
        return SignalType.RFP_POSTED

    def extract_from_sam_opportunity(
        self,
        opp: SamOpportunity,
        existing_urls: Optional[set[str]] = None,
    ) -> ExtractionResult:
        """
        Transform a SAM.gov opportunity into Source + Signal + SignalSource.

        Args:
            opp: SamOpportunity from the SAM.gov client
            existing_urls: Set of URLs already in the database (for deduplication)

        Returns:
            ExtractionResult with source, signal, and signal_source objects.
            Check result.skipped to see if this was a duplicate.
        """
        # Get the source URL
        source_url = opp.sam_url
        if not source_url:
            return ExtractionResult(
                source=None,
                signal=None,
                signal_source=None,
                domain_tags=[],
                entity_refs=[],
                skipped=True,
                skip_reason="No source URL available",
            )

        # Deduplication check
        if existing_urls and source_url in existing_urls:
            return ExtractionResult(
                source=None,
                signal=None,
                signal_source=None,
                domain_tags=[],
                entity_refs=[],
                skipped=True,
                skip_reason=f"Source URL already exists: {source_url}",
            )

        # Infer domain tags
        description = None
        if isinstance(opp, SamOpportunityDetail):
            description = opp.description
        domain_tags = self.infer_domain_tags(opp.title, description)

        # Build entity references
        entity_refs = []
        if opp.department:
            agency_ref = self._agency_to_ref(opp.department)
            if agency_ref:
                entity_refs.append(agency_ref)

        # Add NAICS-based tags
        if opp.naics_code:
            entity_refs.append(f"naics_{opp.naics_code}")

        # Create Source
        source = Source(
            source_type=SourceType.PROCUREMENT_POSTING,
            title=opp.title or "Untitled Opportunity",
            url=source_url,
            publisher="SAM.gov",
            published_at=opp.posted_date,
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="procurement_scanner",
        )

        # Determine signal type and confidence
        signal_type = self._get_signal_type(opp)

        # All SAM.gov postings are verified (authoritative source)
        confidence = Confidence.VERIFIED
        confidence_rationale = f"Direct SAM.gov posting"
        if opp.solicitation_number:
            confidence_rationale += f": {opp.solicitation_number}"

        # Build summary
        summary = self._build_summary(opp)

        # Create Signal
        signal = Signal(
            signal_type=signal_type,
            summary=summary,
            entity_refs=json.dumps(entity_refs) if entity_refs else None,
            domain_tags=json.dumps(domain_tags) if domain_tags else None,
            confidence=confidence,
            confidence_rationale=confidence_rationale,
            extracted_by="procurement_scanner",
            expires_at=opp.response_deadline,  # Signal expires at response deadline
        )

        # Create SignalSource link
        signal_source = SignalSource(
            signal_id=signal.signal_id,
            source_id=source.source_id,
            relevance=SourceRelevance.PRIMARY,
            excerpt=opp.title[:200] if opp.title else None,
        )

        return ExtractionResult(
            source=source,
            signal=signal,
            signal_source=signal_source,
            domain_tags=domain_tags,
            entity_refs=entity_refs,
            skipped=False,
        )

    def extract_batch(
        self,
        opportunities: list[SamOpportunity],
        existing_urls: Optional[set[str]] = None,
    ) -> tuple[list[ExtractionResult], int, int]:
        """
        Extract signals from a batch of opportunities.

        Args:
            opportunities: List of SamOpportunity objects
            existing_urls: Set of URLs already in database

        Returns:
            Tuple of (results, extracted_count, skipped_count)
        """
        results = []
        extracted = 0
        skipped = 0

        for opp in opportunities:
            result = self.extract_from_sam_opportunity(opp, existing_urls)
            results.append(result)

            if result.skipped:
                skipped += 1
                logger.debug(f"Skipped: {result.skip_reason}")
            else:
                extracted += 1
                # Add to existing_urls to prevent duplicates within batch
                if existing_urls is not None and result.source:
                    existing_urls.add(result.source.url)

        logger.info(f"Extracted {extracted} signals, skipped {skipped}")
        return results, extracted, skipped

    # ─── USASPENDING AWARD EXTRACTION ─────────────────────────────────────────

    def _build_award_summary(self, award: AwardSummary) -> str:
        """
        Build factual summary for award signal.

        Template: "{recipient} awarded ${amount} contract by {agency}
                   for '{description}' (Award# {awardId}), NAICS {naics}."
        """
        recipient = award.recipient_name or "Unknown contractor"
        amount = award.award_amount or 0

        # Format amount
        if amount >= 1_000_000:
            amount_str = f"${amount / 1_000_000:.1f}M"
        elif amount >= 1_000:
            amount_str = f"${amount / 1_000:.0f}K"
        else:
            amount_str = f"${amount:,.2f}"

        agency = self._normalize_agency(award.awarding_agency) or "Unknown agency"

        parts = [f"{recipient} awarded {amount_str} contract by {agency}"]

        # Description (truncate if too long)
        if award.description:
            desc = award.description
            if len(desc) > 80:
                desc = desc[:77] + "..."
            parts.append(f"for '{desc}'")

        # Award ID
        if award.award_id:
            parts.append(f"(Award# {award.award_id})")

        # NAICS
        if award.naics_code:
            parts.append(f", NAICS {award.naics_code}")

        # Start date
        if award.start_date:
            parts.append(f", effective {award.start_date}")

        return " ".join(parts) + "."

    def extract_from_award(
        self,
        award: AwardSummary,
        existing_urls: Optional[set[str]] = None,
    ) -> ExtractionResult:
        """
        Transform a USAspending award into Source + Signal + SignalSource.

        Args:
            award: AwardSummary from the USAspending client
            existing_urls: Set of URLs already in the database (for deduplication)

        Returns:
            ExtractionResult with source, signal, and signal_source objects.
            Check result.skipped to see if this was a duplicate.
        """
        # Get the source URL
        source_url = award.usaspending_url
        if not source_url or "None" in source_url:
            return ExtractionResult(
                source=None,
                signal=None,
                signal_source=None,
                domain_tags=[],
                entity_refs=[],
                skipped=True,
                skip_reason="No source URL available",
            )

        # Deduplication check
        if existing_urls and source_url in existing_urls:
            return ExtractionResult(
                source=None,
                signal=None,
                signal_source=None,
                domain_tags=[],
                entity_refs=[],
                skipped=True,
                skip_reason=f"Source URL already exists: {source_url}",
            )

        # Infer domain tags from description
        domain_tags = self.infer_domain_tags(
            award.description or "",
            None
        )

        # Build entity references
        entity_refs = []
        if award.awarding_agency:
            agency_ref = self._agency_to_ref(award.awarding_agency)
            if agency_ref:
                entity_refs.append(agency_ref)

        # Add recipient as entity ref (normalized)
        if award.recipient_name:
            recipient_ref = re.sub(r"[^a-z0-9]+", "_", award.recipient_name.lower())
            recipient_ref = re.sub(r"_+", "_", recipient_ref).strip("_")
            if recipient_ref:
                entity_refs.append(f"contractor_{recipient_ref}")

        # Add NAICS-based tags
        if award.naics_code:
            entity_refs.append(f"naics_{award.naics_code}")

        # Create Source
        source = Source(
            source_type=SourceType.CONTRACT_AWARD,
            title=award.description[:200] if award.description else f"Award {award.award_id}",
            url=source_url,
            publisher="USAspending.gov",
            published_at=award.start_date,
            collection_method=CollectionMethod.API_AUTOMATED,
            collector_agent="procurement_scanner",
        )

        # All USAspending awards are verified (authoritative source)
        confidence = Confidence.VERIFIED
        confidence_rationale = f"Direct USAspending.gov record"
        if award.award_id:
            confidence_rationale += f": {award.award_id}"

        # Build summary
        summary = self._build_award_summary(award)

        # Create Signal (awards don't expire)
        signal = Signal(
            signal_type=SignalType.CONTRACT_AWARDED,
            summary=summary,
            entity_refs=json.dumps(entity_refs) if entity_refs else None,
            domain_tags=json.dumps(domain_tags) if domain_tags else None,
            confidence=confidence,
            confidence_rationale=confidence_rationale,
            extracted_by="procurement_scanner",
            expires_at=None,  # Awards don't expire
        )

        # Create SignalSource link
        signal_source = SignalSource(
            signal_id=signal.signal_id,
            source_id=source.source_id,
            relevance=SourceRelevance.PRIMARY,
            excerpt=award.description[:200] if award.description else None,
        )

        return ExtractionResult(
            source=source,
            signal=signal,
            signal_source=signal_source,
            domain_tags=domain_tags,
            entity_refs=entity_refs,
            skipped=False,
        )

    def extract_awards_batch(
        self,
        awards: list[AwardSummary],
        existing_urls: Optional[set[str]] = None,
    ) -> tuple[list[ExtractionResult], int, int]:
        """
        Extract signals from a batch of awards.

        Args:
            awards: List of AwardSummary objects
            existing_urls: Set of URLs already in database

        Returns:
            Tuple of (results, extracted_count, skipped_count)
        """
        results = []
        extracted = 0
        skipped = 0

        for award in awards:
            result = self.extract_from_award(award, existing_urls)
            results.append(result)

            if result.skipped:
                skipped += 1
                logger.debug(f"Skipped award: {result.skip_reason}")
            else:
                extracted += 1
                # Add to existing_urls to prevent duplicates within batch
                if existing_urls is not None and result.source:
                    existing_urls.add(result.source.url)

        logger.info(f"Extracted {extracted} award signals, skipped {skipped}")
        return results, extracted, skipped


def load_watchlist(path: str) -> dict:
    """Load watchlist configuration from JSON file."""
    import json
    from pathlib import Path

    watchlist_path = Path(path)
    if not watchlist_path.exists():
        logger.warning(f"Watchlist not found: {path}")
        return {}

    with open(watchlist_path) as f:
        return json.load(f)

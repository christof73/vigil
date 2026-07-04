"""
Vectis Market Intelligence — Data Models
=========================================
Enums and dataclasses for the evidence chain database.
"""

import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─── ENUMS ───────────────────────────────────────────────────────────────────

class SourceType(str, Enum):
    PROCUREMENT_POSTING = "procurement_posting"
    CONTRACT_AWARD = "contract_award"
    JOB_POSTING = "job_posting"
    PRESS_RELEASE = "press_release"
    LINKEDIN_ACTIVITY = "linkedin_activity"
    COMPANY_PAGE = "company_page"
    NEWS_ARTICLE = "news_article"
    GOV_REPORT = "gov_report"
    COMMUNITY_POST = "community_post"
    API_RECORD = "api_record"


class UrlStatus(str, Enum):
    LIVE = "live"
    DEAD = "dead"
    PAYWALL = "paywall"
    AUTH_REQUIRED = "auth_required"
    UNCHECKED = "unchecked"


class CollectionMethod(str, Enum):
    API_AUTOMATED = "api_automated"
    MANUAL_ENTRY = "manual_entry"
    RSS_FEED = "rss_feed"
    SCRAPE = "scrape"
    TIP = "tip"


class SignalType(str, Enum):
    RFP_POSTED = "rfp_posted"
    CONTRACT_AWARDED = "contract_awarded"
    JOB_POSTED = "job_posted"
    LEADERSHIP_CHANGE = "leadership_change"
    PRODUCT_RELEASE = "product_release"
    PARTNERSHIP_ANNOUNCED = "partnership_announced"
    HIRING_VELOCITY = "hiring_velocity"
    CONTENT_THEME = "content_theme"
    TECH_ADOPTION = "tech_adoption"
    BUDGET_SIGNAL = "budget_signal"
    ORG_RESTRUCTURE = "org_restructure"
    COMMUNITY_DEMAND = "community_demand"


class Confidence(str, Enum):
    VERIFIED = "verified"
    INFERRED = "inferred"
    SPECULATIVE = "speculative"


class CorrelationType(str, Enum):
    TEMPORAL_CLUSTER = "temporal_cluster"
    ENTITY_OVERLAP = "entity_overlap"
    DOMAIN_CONVERGENCE = "domain_convergence"
    CAUSAL_HYPOTHESIS = "causal_hypothesis"
    CONTRADICTORY = "contradictory"
    RECURRING_DEMAND = "recurring_demand"


class CorrelationStrength(str, Enum):
    STRONG = "strong"      # 3+ verified signals
    MODERATE = "moderate"  # 2 verified or 3+ inferred
    WEAK = "weak"          # inferred/speculative only


class HumanVerdict(str, Enum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    MODIFIED = "modified"
    PENDING = "pending"


class OpportunityLane(str, Enum):
    CORE_SERVICENOW = "core_servicenow"
    CORE_GRC = "core_grc"
    INNOVATION = "innovation"
    NOWFORGE_PRODUCT = "nowforge_product"


class OpportunityStatus(str, Enum):
    WATCHING = "watching"
    RESEARCHING = "researching"
    PURSUING = "pursuing"
    PROPOSAL_SUBMITTED = "proposal_submitted"
    WON = "won"
    LOST = "lost"
    ABANDONED = "abandoned"


class EffortSize(str, Enum):
    TRIVIAL = "trivial"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    ENTERPRISE = "enterprise"


class SourceRelevance(str, Enum):
    PRIMARY = "primary"
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"


class VerificationTarget(str, Enum):
    SOURCE = "source"
    SIGNAL = "signal"
    CORRELATION = "correlation"


class VerificationResult(str, Enum):
    CONFIRMED = "confirmed"
    FAILED = "failed"
    PARTIAL = "partial"
    EXPIRED = "expired"


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── DATACLASSES ─────────────────────────────────────────────────────────────

@dataclass
class Source:
    source_type: str
    title: str
    collection_method: str
    collector_agent: str
    source_id: str = field(default_factory=_uuid)
    url: Optional[str] = None
    url_status: str = UrlStatus.UNCHECKED
    url_last_verified: Optional[str] = None
    publisher: Optional[str] = None
    published_at: Optional[str] = None
    captured_at: str = field(default_factory=_now)
    content_hash: Optional[str] = None
    snapshot_path: Optional[str] = None


@dataclass
class Signal:
    signal_type: str
    summary: str
    confidence: str
    confidence_rationale: str
    extracted_by: str
    signal_id: str = field(default_factory=_uuid)
    entity_refs: Optional[str] = None   # JSON array
    domain_tags: Optional[str] = None   # JSON array
    extracted_at: str = field(default_factory=_now)
    expires_at: Optional[str] = None
    superseded_by: Optional[str] = None


@dataclass
class SignalSource:
    signal_id: str
    source_id: str
    relevance: str
    excerpt: Optional[str] = None
    page_or_section: Optional[str] = None


@dataclass
class Correlation:
    signal_ids: str  # JSON array of UUIDs
    correlation_type: str
    hypothesis: str
    strength: str
    generated_by: str
    correlation_id: str = field(default_factory=_uuid)
    generated_at: str = field(default_factory=_now)
    human_reviewed: bool = False
    human_verdict: Optional[str] = None
    review_notes: Optional[str] = None


@dataclass
class Opportunity:
    title: str
    lane: str
    status: str
    source_correlation_ids: str  # JSON array
    verification_checklist: str  # JSON object
    verification_score: float
    fit_score: float
    created_by: str = "human"  # ALWAYS human
    opportunity_id: str = field(default_factory=_uuid)
    estimated_value: Optional[int] = None
    estimated_effort: Optional[str] = None
    next_action: Optional[str] = None
    deadline: Optional[str] = None
    created_at: str = field(default_factory=_now)


@dataclass
class Verification:
    target_type: str
    target_id: str
    verified_by: str
    result: str
    verification_id: str = field(default_factory=_uuid)
    verified_at: str = field(default_factory=_now)
    failure_reason: Optional[str] = None
    notes: Optional[str] = None

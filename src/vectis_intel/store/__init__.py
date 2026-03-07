"""
Vectis Market Intelligence — Storage Layer
==========================================
Provenance-first evidence chain database.
"""

from .models import (
    # Enums
    SourceType, UrlStatus, CollectionMethod,
    SignalType, Confidence,
    CorrelationType, CorrelationStrength,
    HumanVerdict,
    OpportunityLane, OpportunityStatus, EffortSize,
    SourceRelevance,
    VerificationTarget, VerificationResult,
    # Dataclasses
    Source, Signal, SignalSource,
    Correlation, Opportunity, Verification,
)
from .db import IntelDB
from .integrity import IntegrityEngine, IntegrityError
from .repos import SourceRepo, SignalRepo, CorrelationRepo, OpportunityRepo, VerificationRepo
from .evidence import EvidenceChain
from .facade import IntelStore

__all__ = [
    # Enums
    "SourceType", "UrlStatus", "CollectionMethod",
    "SignalType", "Confidence",
    "CorrelationType", "CorrelationStrength",
    "HumanVerdict",
    "OpportunityLane", "OpportunityStatus", "EffortSize",
    "SourceRelevance",
    "VerificationTarget", "VerificationResult",
    # Dataclasses
    "Source", "Signal", "SignalSource",
    "Correlation", "Opportunity", "Verification",
    # Core classes
    "IntelDB",
    "IntegrityEngine", "IntegrityError",
    "SourceRepo", "SignalRepo", "CorrelationRepo", "OpportunityRepo", "VerificationRepo",
    "EvidenceChain",
    "IntelStore",
]

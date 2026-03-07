"""
Vectis Intel — API Clients
==========================
HTTP clients for external data sources.
"""

from .sam_gov import (
    SamGovClient,
    SamGovError,
    SamOpportunity,
    SamOpportunityDetail,
    SamSearchResult,
    SamPointOfContact,
)
from .usaspending import (
    USAspendingClient,
    USAspendingError,
    AwardSummary,
    AwardDetail,
    SearchResult as AwardSearchResult,
)

__all__ = [
    # SAM.gov
    "SamGovClient",
    "SamGovError",
    "SamOpportunity",
    "SamOpportunityDetail",
    "SamSearchResult",
    "SamPointOfContact",
    # USAspending
    "USAspendingClient",
    "USAspendingError",
    "AwardSummary",
    "AwardDetail",
    "AwardSearchResult",
]

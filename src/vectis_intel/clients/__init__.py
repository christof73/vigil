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

__all__ = [
    "SamGovClient",
    "SamGovError",
    "SamOpportunity",
    "SamOpportunityDetail",
    "SamSearchResult",
    "SamPointOfContact",
]

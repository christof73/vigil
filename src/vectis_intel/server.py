"""
Vectis Market Intelligence — MCP Server
=======================================
Main entrypoint for the MCP server.

Run with: python -m vectis_intel.server
"""

import os
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .store import IntelStore
from .clients.sam_gov import SamGovClient, SamGovError
from .clients.usaspending import USAspendingClient, USAspendingError
from .agents.procurement import ProcurementAgent
from .config import (
    setup_logging,
    WatchlistManager,
    get_env,
    get_env_bool,
)
from .community.schema import apply_community_schema
from .community.config import TaxonomyManager
from .community.sync_taxonomy import sync_taxonomy
from .community.score import score_clusters
from .community.digest import generate_digest
from .community.promote import promote_cluster, audit_promotions, PromotionError
from .community.ingest.sn_community import SNCommunityIngester
from .community.ingest.reddit import RedditIngester
from .community.ingest.stackoverflow import StackOverflowIngester

# Environment configuration
INTEL_DB_PATH = get_env("INTEL_DB_PATH", "./data/vectis_intel.db")
WATCHLIST_PATH = get_env("WATCHLIST_PATH", "./config/watchlists.json")
TAXONOMY_PATH = get_env("TAXONOMY_PATH", "")
SAM_GOV_API_KEY = get_env("SAM_GOV_API_KEY", "")
LOG_LEVEL = get_env("LOG_LEVEL", "INFO")
LOG_JSON = get_env_bool("LOG_JSON", False)

# Configure logging
logger = setup_logging(level=LOG_LEVEL, json_format=LOG_JSON)

# Initialize MCP server
server = Server("vectis-intel")

# Global instances (initialized on startup)
_store: IntelStore | None = None
_watchlist_manager: WatchlistManager | None = None
_taxonomy_manager: TaxonomyManager | None = None
_community_schema_applied: bool = False


def get_store() -> IntelStore:
    """Get or create the IntelStore instance."""
    global _store
    if _store is None:
        _store = IntelStore(INTEL_DB_PATH)
        logger.info(f"Initialized IntelStore at {INTEL_DB_PATH}")
    return _store


def get_watchlist_manager() -> WatchlistManager:
    """Get or create the WatchlistManager instance."""
    global _watchlist_manager
    if _watchlist_manager is None:
        _watchlist_manager = WatchlistManager(WATCHLIST_PATH)
    return _watchlist_manager


def get_watchlist() -> dict:
    """Get the current watchlist (with hot-reload check)."""
    return get_watchlist_manager().get()


def _resolve_taxonomy_path() -> str:
    """Find taxonomy.yaml — explicit env var, or default location."""
    if TAXONOMY_PATH:
        return TAXONOMY_PATH
    # Default: alongside the community package
    pkg_dir = Path(__file__).parent / "community" / "taxonomy.yaml"
    return str(pkg_dir)


def get_taxonomy_manager() -> TaxonomyManager:
    """Get or create the TaxonomyManager instance."""
    global _taxonomy_manager
    if _taxonomy_manager is None:
        _taxonomy_manager = TaxonomyManager(_resolve_taxonomy_path())
        logger.info(f"Initialized TaxonomyManager at {_resolve_taxonomy_path()}")
    return _taxonomy_manager


def get_community_conn():
    """Get a SQLite connection with community schema applied."""
    global _community_schema_applied
    store = get_store()
    if not _community_schema_applied:
        apply_community_schema(store.db.conn)
        _community_schema_applied = True
        logger.info("Community schema applied")
    return store.db.conn


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available MCP tools."""
    return [
        # ─── HEALTH & STATUS ─────────────────────────────────────────────
        Tool(
            name="ping",
            description="Health check - verify the MCP server is running and database is accessible.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="reload_watchlist",
            description="Force reload the watchlist configuration from disk. Use after editing watchlists.json.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),

        # ─── PROCUREMENT SCANNING ────────────────────────────────────────
        Tool(
            name="scan_opportunities",
            description="Search SAM.gov for procurement opportunities matching Vectis watchlist keywords and NAICS codes. Creates Source + Signal records in IntelStore for each new opportunity found.",
            inputSchema={
                "type": "object",
                "properties": {
                    "posted_within_days": {
                        "type": "integer",
                        "default": 7,
                        "description": "Look back N days from today"
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Override watchlist keywords (e.g., ['ServiceNow', 'GRC'])"
                    },
                    "naics_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Override watchlist NAICS codes (e.g., ['541512', '541511'])"
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 100,
                        "description": "Maximum opportunities to fetch per keyword category"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_opportunity_detail",
            description="Fetch full details for a specific SAM.gov opportunity by notice ID or solicitation number. Returns structured data without creating signals (for human review).",
            inputSchema={
                "type": "object",
                "properties": {
                    "notice_id": {
                        "type": "string",
                        "description": "SAM.gov notice ID"
                    },
                    "solicitation_number": {
                        "type": "string",
                        "description": "Solicitation number (e.g., 70B03C25R00000123)"
                    }
                },
                "required": []
            }
        ),

        # ─── AWARD SCANNING (USAspending) ─────────────────────────────────
        Tool(
            name="scan_awards",
            description="Search USAspending.gov for recent contract awards matching watchlist criteria. Creates Source + Signal records for each new award found.",
            inputSchema={
                "type": "object",
                "properties": {
                    "awarded_within_days": {
                        "type": "integer",
                        "default": 30,
                        "description": "Look back N days from today"
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Override watchlist keywords (e.g., ['ServiceNow', 'GRC'])"
                    },
                    "naics_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Override watchlist NAICS codes (e.g., ['541512'])"
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 50,
                        "description": "Maximum awards to fetch"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="search_competitor_awards",
            description="Search USAspending.gov for awards to a specific competitor/contractor. Creates Source + Signal records for each award found.",
            inputSchema={
                "type": "object",
                "properties": {
                    "competitor_name": {
                        "type": "string",
                        "description": "Contractor name to search (e.g., 'Deloitte Consulting')"
                    },
                    "naics_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by NAICS codes (e.g., ['541512'])"
                    },
                    "awarded_within_days": {
                        "type": "integer",
                        "default": 365,
                        "description": "Look back N days (default: 1 year)"
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 50,
                        "description": "Maximum awards to fetch"
                    }
                },
                "required": ["competitor_name"]
            }
        ),

        # ─── INTEL STORE QUERIES ─────────────────────────────────────────
        Tool(
            name="list_signals",
            description="Query signals from the IntelStore with optional filters.",
            inputSchema={
                "type": "object",
                "properties": {
                    "confidence": {
                        "type": "string",
                        "enum": ["verified", "inferred", "speculative"],
                        "description": "Filter by confidence level"
                    },
                    "signal_type": {
                        "type": "string",
                        "description": "Filter by signal type (e.g., rfp_posted, contract_awarded)"
                    },
                    "domain_tag": {
                        "type": "string",
                        "description": "Filter by domain tag (e.g., servicenow, grc, federal)"
                    },
                    "active_only": {
                        "type": "boolean",
                        "default": True,
                        "description": "Exclude expired/superseded signals"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Maximum number of signals to return"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="trace_evidence",
            description="Full evidence chain traversal for a signal or opportunity. Returns the complete chain: opportunity → correlations → signals → sources.",
            inputSchema={
                "type": "object",
                "properties": {
                    "signal_id": {
                        "type": "string",
                        "description": "UUID of the signal to trace"
                    },
                    "opportunity_id": {
                        "type": "string",
                        "description": "UUID of the opportunity to trace"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="list_stale_signals",
            description="List signals past their expiration date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Maximum number of signals to return"
                    }
                },
                "required": []
            }
        ),

        # ─── INTEGRITY & ANALYTICS ───────────────────────────────────────
        Tool(
            name="integrity_audit",
            description="Run full integrity audit on the IntelStore. Returns orphan signals, stale signals, agent trust scores, and overall integrity status.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="agent_trust_report",
            description="Verification success rate per collection agent.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="pipeline_summary",
            description="Opportunity pipeline by lane and status. Returns counts, total value, and average verification/fit scores.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),

        # ─── COMMUNITY SCANNER ─────────────────────────────────────────
        Tool(
            name="community_ingest",
            description="Run community thread ingestion from one or all sources (SN Community RSS, Reddit, Stack Overflow). Each source runs independently — one failure does not block others.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["all", "sn_community", "reddit", "stackoverflow"],
                        "default": "all",
                        "description": "Which source to ingest from"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="community_score",
            description="Run monthly composite scoring for all active clusters. Computes thread_count_norm, unsolved_rate, workaround_rate, commercial_rate, store_gap, and lane-weighted composite. Returns outlier slugs (top-N by raw thread_count × unsolved_rate).",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="community_digest",
            description="Generate weekly ranked digest. Returns top clusters by composite score with deltas, outlier overrides, lane-agnostic content candidates, and uncategorized stats. This is the primary community intelligence output.",
            inputSchema={
                "type": "object",
                "properties": {
                    "digest_date": {
                        "type": "string",
                        "description": "ISO date (YYYY-MM-DD). Defaults to today."
                    },
                    "top_n": {
                        "type": "integer",
                        "default": 10,
                        "description": "Number of top clusters to include"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="community_promote",
            description="Promote a community cluster to the procurement pipeline. Creates Sources, Signals (COMMUNITY_DEMAND), Correlation (RECURRING_DEMAND), and Opportunity with full provenance chain. Human gate: calling this tool IS the human decision.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cluster_slug": {
                        "type": "string",
                        "description": "Cluster slug to promote (e.g., 'grc_evidence_collection')"
                    },
                    "digest_date": {
                        "type": "string",
                        "description": "Digest date that surfaced this cluster (YYYY-MM-DD)"
                    },
                    "n_threads": {
                        "type": "integer",
                        "default": 5,
                        "description": "Number of top threads to promote (min 2)"
                    }
                },
                "required": ["cluster_slug", "digest_date"]
            }
        ),
        Tool(
            name="community_status",
            description="Community scanner status: cluster counts by lane, ingestion watermarks, uncategorized percentage, latest scoring date, and promotion audit.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="sync_taxonomy",
            description="Sync taxonomy.yaml clusters to the signal_clusters table. Inserts new clusters, updates changed labels/lanes/weights, soft-deactivates removed clusters.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool invocations."""
    logger.info(f"Tool called: {name} with args: {arguments}")

    try:
        # Health & Status
        if name == "ping":
            return await handle_ping()
        elif name == "reload_watchlist":
            return await handle_reload_watchlist()

        # Procurement Scanning
        elif name == "scan_opportunities":
            return await handle_scan_opportunities(arguments)
        elif name == "get_opportunity_detail":
            return await handle_get_opportunity_detail(arguments)

        # Award Scanning (USAspending)
        elif name == "scan_awards":
            return await handle_scan_awards(arguments)
        elif name == "search_competitor_awards":
            return await handle_search_competitor_awards(arguments)

        # Intel Store Queries
        elif name == "list_signals":
            return await handle_list_signals(arguments)
        elif name == "trace_evidence":
            return await handle_trace_evidence(arguments)
        elif name == "list_stale_signals":
            return await handle_list_stale_signals(arguments)

        # Integrity & Analytics
        elif name == "integrity_audit":
            return await handle_integrity_audit()
        elif name == "agent_trust_report":
            return await handle_agent_trust_report()
        elif name == "pipeline_summary":
            return await handle_pipeline_summary()

        # Community Scanner
        elif name == "community_ingest":
            return await handle_community_ingest(arguments)
        elif name == "community_score":
            return await handle_community_score()
        elif name == "community_digest":
            return await handle_community_digest(arguments)
        elif name == "community_promote":
            return await handle_community_promote(arguments)
        elif name == "community_status":
            return await handle_community_status()
        elif name == "sync_taxonomy":
            return await handle_sync_taxonomy()

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.exception(f"Error in tool {name}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# ─── HEALTH & STATUS HANDLERS ────────────────────────────────────────────────

async def handle_ping() -> list[TextContent]:
    """Health check - verify server and database."""
    store = get_store()
    watchlist_mgr = get_watchlist_manager()

    # Check database
    try:
        store.db.conn.execute("SELECT 1").fetchone()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"

    # Check API key
    api_key_status = "configured" if SAM_GOV_API_KEY else "missing"

    # Get watchlist stats
    watchlist_stats = watchlist_mgr.get_stats()

    result = {
        "status": "ok",
        "server": "vectis-intel",
        "version": "0.1.0",
        "database": db_status,
        "db_path": INTEL_DB_PATH,
        "sam_api_key": api_key_status,
        "watchlist": {
            "keyword_categories": watchlist_stats["keyword_categories"],
            "total_keywords": watchlist_stats["total_keywords"],
            "naics_codes": watchlist_stats["naics_primary"] + watchlist_stats["naics_secondary"],
            "last_modified": watchlist_stats["last_modified"],
        },
        "logging": {
            "level": LOG_LEVEL,
            "json_format": LOG_JSON,
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_reload_watchlist() -> list[TextContent]:
    """Force reload the watchlist configuration."""
    watchlist_mgr = get_watchlist_manager()

    # Get stats before reload
    old_stats = watchlist_mgr.get_stats()

    # Force reload
    watchlist_mgr.reload()

    # Get stats after reload
    new_stats = watchlist_mgr.get_stats()

    result = {
        "reloaded": True,
        "path": new_stats["path"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "keyword_categories": new_stats["keyword_categories"],
            "total_keywords": new_stats["total_keywords"],
            "naics_primary": new_stats["naics_primary"],
            "naics_secondary": new_stats["naics_secondary"],
        },
        "changes": {
            "keywords_changed": old_stats["total_keywords"] != new_stats["total_keywords"],
            "old_total_keywords": old_stats["total_keywords"],
            "new_total_keywords": new_stats["total_keywords"],
        }
    }

    logger.info(
        "Watchlist reloaded",
        extra={"old_keywords": old_stats["total_keywords"], "new_keywords": new_stats["total_keywords"]}
    )

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── PROCUREMENT SCANNING HANDLERS ───────────────────────────────────────────

async def handle_scan_opportunities(args: dict) -> list[TextContent]:
    """
    Scan SAM.gov for opportunities and create signals.

    Flow: SamGovClient → ProcurementAgent → IntelStore
    """
    if not SAM_GOV_API_KEY:
        return [TextContent(type="text", text=json.dumps({
            "error": "SAM_GOV_API_KEY not configured",
            "help": "Set SAM_GOV_API_KEY environment variable. Get a key from: sam.gov > Profile > Public API Key"
        }, indent=2))]

    store = get_store()
    watchlist = get_watchlist()

    # Parse arguments
    posted_within_days = args.get("posted_within_days", 7)
    max_results = args.get("max_results", 100)
    keywords = args.get("keywords")
    naics_codes = args.get("naics_codes")

    # Build search parameters
    if keywords or naics_codes:
        # Override watchlist with provided values
        search_watchlist = {
            "keywords": {"custom": keywords} if keywords else {},
            "naics_codes": {
                "primary": naics_codes or [],
                "secondary": []
            }
        }
    else:
        search_watchlist = watchlist

    # Get existing source URLs for deduplication
    existing_sources = store.sources.list_by_type("procurement_posting", limit=1000)
    existing_urls = {s["url"] for s in existing_sources if s.get("url")}
    logger.info(f"Found {len(existing_urls)} existing source URLs for deduplication")

    # Search SAM.gov
    try:
        async with SamGovClient(api_key=SAM_GOV_API_KEY) as client:
            opportunities = await client.search_by_watchlist(
                watchlist=search_watchlist,
                posted_within_days=posted_within_days,
                max_per_keyword=max_results,
            )
    except SamGovError as e:
        return [TextContent(type="text", text=json.dumps({
            "error": f"SAM.gov API error: {str(e)}",
            "status_code": getattr(e, "status_code", None)
        }, indent=2))]

    logger.info(f"SAM.gov returned {len(opportunities)} opportunities")

    # Extract signals
    agent = ProcurementAgent(watchlist)
    results, extracted, skipped = agent.extract_batch(
        opportunities,
        existing_urls=existing_urls
    )

    # Store new signals
    created_signals = []
    for result in results:
        if not result.skipped:
            try:
                store.sources.create(result.source)
                signal = store.signals.create(result.signal, [result.signal_source])
                created_signals.append({
                    "signal_id": signal.signal_id,
                    "summary": signal.summary[:100] + "..." if len(signal.summary) > 100 else signal.summary,
                    "domain_tags": result.domain_tags,
                    "expires_at": signal.expires_at,
                })
            except Exception as e:
                logger.error(f"Failed to store signal: {e}")
                skipped += 1
                extracted -= 1

    # Build response
    response = {
        "scan_completed": datetime.now(timezone.utc).isoformat(),
        "parameters": {
            "posted_within_days": posted_within_days,
            "keywords": keywords or "watchlist",
            "naics_codes": naics_codes or "watchlist",
        },
        "results": {
            "opportunities_found": len(opportunities),
            "signals_created": extracted,
            "duplicates_skipped": skipped,
        },
        "signals": created_signals
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_get_opportunity_detail(args: dict) -> list[TextContent]:
    """Fetch full details for a specific opportunity."""
    if not SAM_GOV_API_KEY:
        return [TextContent(type="text", text=json.dumps({
            "error": "SAM_GOV_API_KEY not configured"
        }, indent=2))]

    notice_id = args.get("notice_id")
    solicitation_number = args.get("solicitation_number")

    if not notice_id and not solicitation_number:
        return [TextContent(type="text", text=json.dumps({
            "error": "Must provide notice_id or solicitation_number"
        }, indent=2))]

    try:
        async with SamGovClient(api_key=SAM_GOV_API_KEY) as client:
            detail = await client.get_opportunity_detail(
                notice_id=notice_id,
                solicitation_number=solicitation_number
            )
    except SamGovError as e:
        return [TextContent(type="text", text=json.dumps({
            "error": f"SAM.gov API error: {str(e)}"
        }, indent=2))]

    if not detail:
        return [TextContent(type="text", text=json.dumps({
            "error": "Opportunity not found"
        }, indent=2))]

    # Convert to dict for JSON serialization
    result = {
        "notice_id": detail.notice_id,
        "title": detail.title,
        "solicitation_number": detail.solicitation_number,
        "department": detail.department,
        "posted_date": detail.posted_date,
        "response_deadline": detail.response_deadline,
        "naics_code": detail.naics_code,
        "notice_type": detail.notice_type,
        "set_aside": detail.set_aside,
        "sam_url": detail.sam_url,
        "description": detail.description[:2000] if detail.description else None,
        "point_of_contact": [
            {"name": poc.full_name, "email": poc.email}
            for poc in detail.point_of_contact
        ] if detail.point_of_contact else [],
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── AWARD SCANNING HANDLERS (USAspending) ───────────────────────────────────

async def handle_scan_awards(args: dict) -> list[TextContent]:
    """
    Scan USAspending.gov for contract awards and create signals.

    Flow: USAspendingClient → ProcurementAgent → IntelStore
    """
    store = get_store()
    watchlist = get_watchlist()

    # Parse arguments
    awarded_within_days = args.get("awarded_within_days", 30)
    max_results = args.get("max_results", 50)
    keywords = args.get("keywords")
    naics_codes = args.get("naics_codes")

    # Build search parameters
    if keywords or naics_codes:
        # Override watchlist with provided values
        search_watchlist = {
            "keywords": {"custom": keywords} if keywords else {},
            "naics_codes": {
                "primary": naics_codes or [],
                "secondary": []
            }
        }
    else:
        search_watchlist = watchlist

    # Get existing source URLs for deduplication
    existing_sources = store.sources.list_by_type("contract_award", limit=1000)
    existing_urls = {s["url"] for s in existing_sources if s.get("url")}
    logger.info(f"Found {len(existing_urls)} existing award URLs for deduplication")

    # Search USAspending
    try:
        async with USAspendingClient() as client:
            awards = await client.search_by_watchlist(
                watchlist=search_watchlist,
                awarded_within_days=awarded_within_days,
                max_per_keyword=max_results,
            )
    except USAspendingError as e:
        return [TextContent(type="text", text=json.dumps({
            "error": f"USAspending API error: {str(e)}",
            "status_code": getattr(e, "status_code", None)
        }, indent=2))]

    logger.info(f"USAspending returned {len(awards)} awards")

    # Extract signals
    agent = ProcurementAgent(watchlist)
    results, extracted, skipped = agent.extract_awards_batch(
        awards,
        existing_urls=existing_urls
    )

    # Store new signals
    created_signals = []
    for result in results:
        if not result.skipped:
            try:
                store.sources.create(result.source)
                signal = store.signals.create(result.signal, [result.signal_source])
                created_signals.append({
                    "signal_id": signal.signal_id,
                    "summary": signal.summary[:100] + "..." if len(signal.summary) > 100 else signal.summary,
                    "domain_tags": result.domain_tags,
                })
            except Exception as e:
                logger.error(f"Failed to store award signal: {e}")
                skipped += 1
                extracted -= 1

    # Build response
    response = {
        "scan_completed": datetime.now(timezone.utc).isoformat(),
        "parameters": {
            "awarded_within_days": awarded_within_days,
            "keywords": keywords or "watchlist",
            "naics_codes": naics_codes or "watchlist",
        },
        "results": {
            "awards_found": len(awards),
            "signals_created": extracted,
            "duplicates_skipped": skipped,
        },
        "signals": created_signals
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_search_competitor_awards(args: dict) -> list[TextContent]:
    """
    Search USAspending.gov for awards to a specific competitor.

    Creates Source + Signal records for each award found.
    """
    store = get_store()
    watchlist = get_watchlist()

    # Parse arguments
    competitor_name = args.get("competitor_name")
    if not competitor_name:
        return [TextContent(type="text", text=json.dumps({
            "error": "competitor_name is required"
        }, indent=2))]

    naics_codes = args.get("naics_codes")
    awarded_within_days = args.get("awarded_within_days", 365)
    max_results = args.get("max_results", 50)

    # Get existing source URLs for deduplication
    existing_sources = store.sources.list_by_type("contract_award", limit=1000)
    existing_urls = {s["url"] for s in existing_sources if s.get("url")}

    # Search USAspending for this competitor
    try:
        async with USAspendingClient() as client:
            awards = await client.search_by_recipient(
                recipient_name=competitor_name,
                naics_codes=naics_codes,
                awarded_within_days=awarded_within_days,
                max_results=max_results,
            )
    except USAspendingError as e:
        return [TextContent(type="text", text=json.dumps({
            "error": f"USAspending API error: {str(e)}",
            "status_code": getattr(e, "status_code", None)
        }, indent=2))]

    logger.info(f"Found {len(awards)} awards for competitor: {competitor_name}")

    # Extract signals
    agent = ProcurementAgent(watchlist)
    results, extracted, skipped = agent.extract_awards_batch(
        awards,
        existing_urls=existing_urls
    )

    # Store new signals
    created_signals = []
    total_value = 0

    for result in results:
        if not result.skipped:
            try:
                store.sources.create(result.source)
                signal = store.signals.create(result.signal, [result.signal_source])
                created_signals.append({
                    "signal_id": signal.signal_id,
                    "summary": signal.summary[:100] + "..." if len(signal.summary) > 100 else signal.summary,
                })
            except Exception as e:
                logger.error(f"Failed to store competitor award signal: {e}")
                skipped += 1
                extracted -= 1

    # Calculate total value from awards
    for award in awards:
        total_value += award.award_amount or 0

    # Build response
    response = {
        "scan_completed": datetime.now(timezone.utc).isoformat(),
        "competitor": competitor_name,
        "parameters": {
            "awarded_within_days": awarded_within_days,
            "naics_codes": naics_codes or "all",
        },
        "results": {
            "awards_found": len(awards),
            "signals_created": extracted,
            "duplicates_skipped": skipped,
            "total_award_value": total_value,
            "total_award_value_formatted": f"${total_value:,.2f}",
        },
        "signals": created_signals
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


# ─── INTEL STORE QUERY HANDLERS ──────────────────────────────────────────────

async def handle_list_signals(args: dict) -> list[TextContent]:
    """List signals with filters."""
    store = get_store()
    limit = args.get("limit", 20)

    # Apply filters in priority order
    if "confidence" in args:
        signals = store.signals.list_by_confidence(args["confidence"], limit)
    elif "signal_type" in args:
        signals = store.signals.list_by_type(args["signal_type"], limit)
    elif "domain_tag" in args:
        signals = store.signals.list_by_domain(args["domain_tag"], limit)
    elif args.get("active_only", True):
        signals = store.signals.list_active(limit)
    else:
        signals = store.signals.list_active(limit)

    result = {
        "count": len(signals),
        "signals": signals
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_trace_evidence(args: dict) -> list[TextContent]:
    """Trace evidence chain for signal or opportunity."""
    store = get_store()

    if "signal_id" in args:
        chain = store.evidence.trace_signal(args["signal_id"])
    elif "opportunity_id" in args:
        chain = store.evidence.trace_opportunity(args["opportunity_id"])
    else:
        return [TextContent(type="text", text="Error: Must provide signal_id or opportunity_id")]

    return [TextContent(type="text", text=json.dumps(chain, indent=2))]


async def handle_list_stale_signals(args: dict) -> list[TextContent]:
    """List stale signals."""
    store = get_store()
    limit = args.get("limit", 20)
    signals = store.signals.list_stale(limit)
    result = {
        "count": len(signals),
        "stale_signals": signals
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── INTEGRITY & ANALYTICS HANDLERS ──────────────────────────────────────────

async def handle_integrity_audit() -> list[TextContent]:
    """Run full integrity audit."""
    store = get_store()
    audit = store.integrity.run_integrity_audit()
    return [TextContent(type="text", text=json.dumps(audit, indent=2))]


async def handle_agent_trust_report() -> list[TextContent]:
    """Get agent trust scores."""
    store = get_store()
    scores = store.verifications.agent_trust_scores()
    return [TextContent(type="text", text=json.dumps(scores, indent=2))]


async def handle_pipeline_summary() -> list[TextContent]:
    """Get pipeline summary."""
    store = get_store()
    summary = store.opportunities.pipeline_summary()
    return [TextContent(type="text", text=json.dumps(summary, indent=2))]


# ─── COMMUNITY SCANNER HANDLERS ─────────────────────────────────────────────

async def handle_community_ingest(args: dict) -> list[TextContent]:
    """Run community thread ingestion."""
    conn = get_community_conn()
    taxonomy = get_taxonomy_manager()
    source = args.get("source", "all")

    results = {}

    if source in ("all", "sn_community"):
        try:
            ingester = SNCommunityIngester(taxonomy)
            r = await ingester.ingest(conn)
            results["sn_community"] = {
                "inserted": r.inserted, "updated": r.updated,
                "skipped": r.skipped, "errors": r.errors,
            }
        except Exception as e:
            logger.exception("SN Community ingestion failed")
            results["sn_community"] = {"error": str(e)}

    if source in ("all", "reddit"):
        try:
            ingester = RedditIngester(taxonomy)
            r = await ingester.ingest(conn)
            results["reddit"] = {
                "inserted": r.inserted, "updated": r.updated,
                "skipped": r.skipped, "errors": r.errors,
            }
        except Exception as e:
            logger.exception("Reddit ingestion failed")
            results["reddit"] = {"error": str(e)}

    if source in ("all", "stackoverflow"):
        try:
            ingester = StackOverflowIngester(taxonomy)
            r = await ingester.ingest(conn)
            results["stackoverflow"] = {
                "inserted": r.inserted, "updated": r.updated,
                "skipped": r.skipped, "errors": r.errors,
            }
        except Exception as e:
            logger.exception("Stack Overflow ingestion failed")
            results["stackoverflow"] = {"error": str(e)}

    response = {
        "ingestion_completed": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "results": results,
    }
    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_community_score() -> list[TextContent]:
    """Run monthly scoring for all active clusters."""
    conn = get_community_conn()
    taxonomy = get_taxonomy_manager()

    result = score_clusters(conn, taxonomy)
    response = {
        "scoring_completed": datetime.now(timezone.utc).isoformat(),
        "scored": result["scored"],
        "skipped_empty": result["skipped_empty"],
        "window": {"start": result["window"][0], "end": result["window"][1]},
        "outlier_slugs": result.get("outlier_slugs", []),
    }
    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_community_digest(args: dict) -> list[TextContent]:
    """Generate weekly community digest."""
    conn = get_community_conn()
    taxonomy = get_taxonomy_manager()

    digest_date = args.get("digest_date")
    top_n = args.get("top_n", 10)

    digest = generate_digest(conn, taxonomy, digest_date=digest_date, top_n=top_n)
    return [TextContent(type="text", text=json.dumps(digest, indent=2))]


async def handle_community_promote(args: dict) -> list[TextContent]:
    """Promote a cluster to the procurement pipeline."""
    conn = get_community_conn()
    store = get_store()

    cluster_slug = args.get("cluster_slug")
    digest_date = args.get("digest_date")
    n_threads = args.get("n_threads", 5)

    if not cluster_slug or not digest_date:
        return [TextContent(type="text", text=json.dumps({
            "error": "cluster_slug and digest_date are required"
        }, indent=2))]

    try:
        result = promote_cluster(conn, store, cluster_slug, digest_date, n_threads=n_threads)
        response = {
            "promoted": True,
            "cluster_slug": cluster_slug,
            "opportunity_id": result["opportunity_id"],
            "correlation_id": result["correlation_id"],
            "signals_created": result["signals_created"],
            "sources_reused": result["sources_reused"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except PromotionError as e:
        response = {"promoted": False, "error": str(e)}

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_community_status() -> list[TextContent]:
    """Community scanner status overview."""
    conn = get_community_conn()
    store = get_store()

    # Cluster counts by lane
    lane_counts = conn.execute(
        """SELECT lane, COUNT(*) as count, SUM(active) as active
           FROM signal_clusters GROUP BY lane"""
    ).fetchall()

    # Total community signals
    total_signals = conn.execute(
        "SELECT COUNT(*) as cnt FROM community_signals"
    ).fetchone()["cnt"]

    # Uncategorized count
    uncat = conn.execute(
        "SELECT COUNT(*) as cnt FROM community_signals WHERE cluster_id IS NULL"
    ).fetchone()["cnt"]

    # Ingestion watermarks
    watermarks = conn.execute(
        "SELECT source, last_id, last_posted, updated_at FROM ingest_state"
    ).fetchall()

    # Latest scoring date
    latest_score = conn.execute(
        "SELECT MAX(scored_at) as latest FROM cluster_scores"
    ).fetchone()

    # Promotion audit
    audit = audit_promotions(conn, store)

    response = {
        "clusters_by_lane": {
            r["lane"]: {"total": r["count"], "active": r["active"]}
            for r in lane_counts
        },
        "signals": {
            "total": total_signals,
            "uncategorized": uncat,
            "uncategorized_pct": round(uncat / total_signals * 100, 1) if total_signals > 0 else 0,
        },
        "ingestion_watermarks": {
            r["source"]: {
                "last_id": r["last_id"],
                "last_posted": r["last_posted"],
                "updated_at": r["updated_at"],
            }
            for r in watermarks
        },
        "latest_scoring": latest_score["latest"] if latest_score else None,
        "promotion_audit": audit,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_sync_taxonomy() -> list[TextContent]:
    """Sync taxonomy.yaml to signal_clusters table."""
    conn = get_community_conn()
    taxonomy = get_taxonomy_manager()

    result = sync_taxonomy(conn, taxonomy)
    response = {
        "synced": True,
        "inserted": result["inserted"],
        "updated": result["updated"],
        "deactivated": result["deactivated"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return [TextContent(type="text", text=json.dumps(response, indent=2))]


# ─── MAIN ────────────────────────────────────────────────────────────────────

async def main():
    """Main entry point - run the MCP server."""
    logger.info("Starting Vectis Intel MCP server...")

    # Initialize on startup
    get_store()
    get_watchlist()

    # Log configuration
    logger.info(f"Database: {INTEL_DB_PATH}")
    logger.info(f"Watchlist: {WATCHLIST_PATH}")
    logger.info(f"SAM.gov API key: {'configured' if SAM_GOV_API_KEY else 'NOT SET'}")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

"""
Vectis Market Intelligence — MCP Server
=======================================
Main entrypoint for the MCP server.

Run with: python -m vectis_intel.server
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .store import IntelStore
from .clients.sam_gov import SamGovClient, SamGovError
from .agents.procurement import ProcurementAgent, load_watchlist

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("vectis_intel")

# Environment configuration
INTEL_DB_PATH = os.getenv("INTEL_DB_PATH", "./data/vectis_intel.db")
WATCHLIST_PATH = os.getenv("WATCHLIST_PATH", "./config/watchlists.json")
SAM_GOV_API_KEY = os.getenv("SAM_GOV_API_KEY", "")

# Initialize MCP server
server = Server("vectis-intel")

# Global instances (initialized on startup)
_store: IntelStore | None = None
_watchlist: dict | None = None


def get_store() -> IntelStore:
    """Get or create the IntelStore instance."""
    global _store
    if _store is None:
        _store = IntelStore(INTEL_DB_PATH)
        logger.info(f"Initialized IntelStore at {INTEL_DB_PATH}")
    return _store


def get_watchlist() -> dict:
    """Get or load the watchlist configuration."""
    global _watchlist
    if _watchlist is None:
        _watchlist = load_watchlist(WATCHLIST_PATH)
        logger.info(f"Loaded watchlist from {WATCHLIST_PATH}")
    return _watchlist


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
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool invocations."""
    logger.info(f"Tool called: {name} with args: {arguments}")

    try:
        # Health & Status
        if name == "ping":
            return await handle_ping()

        # Procurement Scanning
        elif name == "scan_opportunities":
            return await handle_scan_opportunities(arguments)
        elif name == "get_opportunity_detail":
            return await handle_get_opportunity_detail(arguments)

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

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.exception(f"Error in tool {name}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# ─── HEALTH & STATUS HANDLERS ────────────────────────────────────────────────

async def handle_ping() -> list[TextContent]:
    """Health check - verify server and database."""
    store = get_store()

    # Check database
    try:
        store.db.conn.execute("SELECT 1").fetchone()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"

    # Check API key
    api_key_status = "configured" if SAM_GOV_API_KEY else "missing"

    # Check watchlist
    watchlist = get_watchlist()
    watchlist_status = f"{len(watchlist.get('keywords', {}))} keyword categories"

    result = {
        "status": "ok",
        "server": "vectis-intel",
        "version": "0.1.0",
        "database": db_status,
        "db_path": INTEL_DB_PATH,
        "sam_api_key": api_key_status,
        "watchlist": watchlist_status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
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

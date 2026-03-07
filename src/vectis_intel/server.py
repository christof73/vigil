"""
Vectis Market Intelligence — MCP Server
=======================================
Main entrypoint for the MCP server.

Run with: python -m vectis_intel.server
"""

import os
import json
import logging
from datetime import datetime, timezone

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .store import IntelStore

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("vectis_intel")

# Environment configuration
INTEL_DB_PATH = os.getenv("INTEL_DB_PATH", "./data/vectis_intel.db")
WATCHLIST_PATH = os.getenv("WATCHLIST_PATH", "./config/watchlists.json")

# Initialize MCP server
server = Server("vectis-intel")

# Global store instance (initialized on startup)
_store: IntelStore | None = None


def get_store() -> IntelStore:
    """Get or create the IntelStore instance."""
    global _store
    if _store is None:
        _store = IntelStore(INTEL_DB_PATH)
        logger.info(f"Initialized IntelStore at {INTEL_DB_PATH}")
    return _store


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available MCP tools."""
    return [
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
            name="integrity_audit",
            description="Run full integrity audit on the IntelStore. Returns orphan signals, stale signals, agent trust scores, and overall integrity status.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
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
        if name == "ping":
            return await handle_ping()
        elif name == "integrity_audit":
            return await handle_integrity_audit()
        elif name == "list_signals":
            return await handle_list_signals(arguments)
        elif name == "trace_evidence":
            return await handle_trace_evidence(arguments)
        elif name == "list_stale_signals":
            return await handle_list_stale_signals(arguments)
        elif name == "agent_trust_report":
            return await handle_agent_trust_report()
        elif name == "pipeline_summary":
            return await handle_pipeline_summary()
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as e:
        logger.exception(f"Error in tool {name}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def handle_ping() -> list[TextContent]:
    """Health check - verify server and database."""
    store = get_store()
    # Quick query to verify DB is accessible
    try:
        store.db.conn.execute("SELECT 1").fetchone()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"

    result = {
        "status": "ok",
        "server": "vectis-intel",
        "version": "0.1.0",
        "database": db_status,
        "db_path": INTEL_DB_PATH,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_integrity_audit() -> list[TextContent]:
    """Run full integrity audit."""
    store = get_store()
    audit = store.integrity.run_integrity_audit()
    return [TextContent(type="text", text=json.dumps(audit, indent=2))]


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


async def main():
    """Main entry point - run the MCP server."""
    logger.info("Starting Vectis Intel MCP server...")

    # Initialize store on startup
    get_store()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

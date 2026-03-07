# Vectis Intel — Procurement Scanner MCP Server

MCP server for monitoring federal procurement opportunities (SAM.gov) and contract awards (USAspending.gov). Extracts structured signals and persists them to an evidence chain database.

## Quick Start

```bash
# Install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run the MCP server (for Claude Code integration)
python -m vectis_intel
```

## Project Structure

```
vigil/
├── pyproject.toml              # Project metadata + dependencies
├── src/vectis_intel/
│   ├── server.py               # MCP server entrypoint
│   ├── store/                  # IntelStore database layer
│   │   ├── models.py           # Dataclasses + enums
│   │   ├── db.py               # SQLite connection + schema
│   │   ├── integrity.py        # Integrity rules engine
│   │   ├── repos.py            # Repository classes
│   │   ├── evidence.py         # Evidence chain traversal
│   │   └── facade.py           # IntelStore facade
│   ├── clients/                # API clients (Phase 2+)
│   ├── agents/                 # Signal extraction (Phase 3+)
│   └── tools/                  # MCP tool definitions (Phase 4+)
├── config/
│   └── watchlists.json         # Keywords, NAICS codes, competitors
├── data/
│   └── vectis_intel.db         # SQLite database (auto-created)
└── tests/
    └── test_store.py           # Store package tests
```

## MCP Tools (Phase 1)

| Tool | Description |
|------|-------------|
| `ping` | Health check - verify server and database |
| `integrity_audit` | Run full integrity audit |
| `list_signals` | Query signals with filters |
| `trace_evidence` | Full evidence chain traversal |
| `list_stale_signals` | List expired signals |
| `agent_trust_report` | Verification rates per agent |
| `pipeline_summary` | Opportunity pipeline by lane |

## Claude Code Integration

Add to your MCP config (`~/.claude/mcp.json` or project-level):

```json
{
  "mcpServers": {
    "vectis-intel": {
      "command": "python",
      "args": ["-m", "vectis_intel"],
      "cwd": "/path/to/vigil",
      "env": {
        "SAM_GOV_API_KEY": "DEMO_KEY",
        "INTEL_DB_PATH": "./data/vectis_intel.db"
      }
    }
  }
}
```

## Build Phases

- [x] **Phase 1: Foundation** — Project structure, store refactor, MCP server shell
- [ ] **Phase 2: SAM.gov Client** — API client for procurement opportunities
- [ ] **Phase 3: Signal Extraction** — Transform API data to Source + Signal pairs
- [ ] **Phase 4: MCP Tool Wiring** — Connect clients to MCP tools
- [ ] **Phase 5: USAspending** — Contract awards client
- [ ] **Phase 6: Operational Polish** — Logging, error handling, config reload

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SAM_GOV_API_KEY` | **Yes** | — | SAM.gov API key (see below) |
| `INTEL_DB_PATH` | No | `./data/vectis_intel.db` | SQLite database path |
| `WATCHLIST_PATH` | No | `./config/watchlists.json` | Watchlist config path |
| `LOG_LEVEL` | No | `INFO` | Logging level |

## Getting a SAM.gov API Key

**Important:** SAM.gov requires its own API key. The generic `DEMO_KEY` from api.data.gov does NOT work.

1. Go to [sam.gov](https://sam.gov) and create an account (or sign in)
2. Navigate to your Profile (user icon in header)
3. Go to "Public API Key" section
4. Click "Request API Key"
5. Copy the key and set it: `export SAM_GOV_API_KEY=your_key_here`

**Notes:**
- Keys expire every 90 days
- Rate limit: 1,000 requests/day
- Registration can take up to 10 business days

## License

Proprietary - Vectis Labs

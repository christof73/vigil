# Vectis Intel — Procurement Scanner MCP Server

An MCP (Model Context Protocol) server that monitors federal procurement opportunities and contract awards, extracts structured intelligence signals, and persists them to an evidence chain database.

## Features

- **SAM.gov Integration** — Search federal procurement opportunities by keyword, NAICS code, and date range
- **USAspending.gov Integration** — Track contract awards, competitor wins, and agency spending
- **Signal Extraction** — Transform raw API data into structured, traceable intelligence signals
- **Evidence Chain** — Full provenance tracking from signal → source → URL
- **Watchlist-Based Scanning** — Configure keywords, NAICS codes, and competitors to monitor
- **Hot-Reload Configuration** — Update watchlists without restarting the server

## Quick Start

### 1. Install

```bash
cd vigil
pip install -e ".[dev]"
```

### 2. Configure

Create a `.env` file (or set environment variables):

```bash
# Required for SAM.gov scanning
SAM_GOV_API_KEY=your-key-here  # Get from sam.gov > Profile > Public API Key

# Optional
INTEL_DB_PATH=./data/vectis_intel.db
WATCHLIST_PATH=./config/watchlists.json
LOG_LEVEL=INFO
LOG_JSON=false  # Set to true for structured JSON logs
```

### 3. Configure Claude Code MCP

Add to your Claude Code MCP config (`~/.claude/mcp.json` or project-level):

```json
{
  "mcpServers": {
    "vectis-intel": {
      "command": "python",
      "args": ["-m", "vectis_intel.server"],
      "cwd": "/path/to/vigil",
      "env": {
        "SAM_GOV_API_KEY": "your-key-here",
        "INTEL_DB_PATH": "./data/vectis_intel.db"
      }
    }
  }
}
```

### 4. Run

The server starts automatically when Claude Code loads it. You can also run directly:

```bash
python -m vectis_intel.server
```

## MCP Tools

### Health & Status

| Tool | Description |
|------|-------------|
| `ping` | Health check — verify server, database, and configuration |
| `reload_watchlist` | Force reload watchlist from disk after editing |

### Procurement Scanning (SAM.gov)

| Tool | Description |
|------|-------------|
| `scan_opportunities` | Search SAM.gov for opportunities matching watchlist, create signals |
| `get_opportunity_detail` | Fetch full details for a specific opportunity |

### Award Scanning (USAspending.gov)

| Tool | Description |
|------|-------------|
| `scan_awards` | Search USAspending for contract awards matching watchlist |
| `search_competitor_awards` | Track what specific competitors are winning |

### Intel Store Queries

| Tool | Description |
|------|-------------|
| `list_signals` | Query signals with filters (type, confidence, domain) |
| `trace_evidence` | Full evidence chain traversal for a signal |
| `list_stale_signals` | Find expired signals past their deadline |

### Integrity & Analytics

| Tool | Description |
|------|-------------|
| `integrity_audit` | Run full integrity check on the database |
| `agent_trust_report` | Verification success rates per collection agent |
| `pipeline_summary` | Opportunity pipeline by status and lane |

## Example Usage

```
You: Scan SAM.gov for ServiceNow and GRC opportunities posted in the last 14 days

Claude: [calls scan_opportunities]
Found 8 new opportunities. Created 8 signals:
1. [verified] Department of Treasury posted Sources Sought for 'GRC Platform Modernization'...
2. [verified] DHS/CISA posted Combined Synopsis for 'FISMA Continuous Monitoring Tools'...

You: Show me the evidence chain for that Treasury opportunity

Claude: [calls trace_evidence]
Signal: Treasury posted Sources Sought for 'GRC Platform Modernization'...
  └─ Source: https://sam.gov/opp/xyz789/view (SAM.gov, captured today)
  └─ Confidence: verified (Direct SAM.gov posting: SOL# 70B03C25R00000456)
  └─ Domain tags: servicenow, grc, federal, fisma
  └─ Expires: 2026-04-15

You: Search what Deloitte has won in this space recently

Claude: [calls search_competitor_awards]
Found 3 awards to Deloitte Consulting in NAICS 541512 in the last 12 months:
1. $4.5M — Department of Treasury — "ServiceNow GRC Implementation Phase 2"
2. $2.1M — DHS — "FISMA Compliance Platform Support"
```

## Watchlist Configuration

Edit `config/watchlists.json` to customize what the scanner monitors:

```json
{
  "version": "1.0",
  "keywords": {
    "servicenow": ["ServiceNow", "service-now", "SNOW platform"],
    "grc": ["GRC", "governance risk compliance", "risk management framework"],
    "fisma": ["FISMA", "NIST 800-53", "security controls"]
  },
  "naics_codes": {
    "primary": ["541512", "541511"],
    "secondary": ["541519", "518210"]
  },
  "competitors": {
    "large_primes": ["Deloitte Consulting", "Booz Allen Hamilton", "Accenture Federal"],
    "servicenow_partners": ["Thirdera", "Cask", "GlideFast Consulting"]
  },
  "agencies_of_interest": [
    "Department of the Treasury",
    "Department of Homeland Security",
    "General Services Administration"
  ]
}
```

After editing, use `reload_watchlist` to apply changes without restarting.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SAM_GOV_API_KEY` | Yes* | — | SAM.gov API key (get from sam.gov > Profile > Public API Key) |
| `INTEL_DB_PATH` | No | `./data/vectis_intel.db` | SQLite database path |
| `WATCHLIST_PATH` | No | `./config/watchlists.json` | Watchlist configuration path |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `LOG_JSON` | No | `false` | Use structured JSON logging |

*Required for SAM.gov scanning. USAspending.gov works without authentication.

## Getting a SAM.gov API Key

**Important:** SAM.gov requires its own API key. The generic `DEMO_KEY` from api.data.gov does NOT work.

1. Go to [sam.gov](https://sam.gov) and create an account (or sign in)
2. Navigate to your Profile (user icon in header)
3. Go to "Public API Key" section
4. Click "Request API Key"
5. Copy the key and set it: `export SAM_GOV_API_KEY=your_key_here`

**Notes:**
- Keys expire every 90 days
- Rate limit: ~1,000 requests/day
- Registration can take up to 10 business days

## Database

The IntelStore uses SQLite with a provenance-first schema:

- **Sources** — Original documents/URLs with collection metadata
- **Signals** — Extracted intelligence with confidence levels
- **SignalSources** — Many-to-many linking signals to their sources
- **Correlations** — Human-identified relationships between signals
- **Opportunities** — Business opportunities (human-created only)
- **Verifications** — Audit trail for human verification actions

### Integrity Rules

1. **No orphan signals** — Every signal must link to at least one source
2. **Human-only opportunities** — Opportunities can only be created by humans
3. **Confidence degradation** — Signal confidence degrades if sources become unavailable
4. **Evidence chain** — Every claim traceable to a verifiable URL

## Development

### Run Tests

```bash
# Unit tests (no network required)
pytest tests/ -v -k "not integration"

# Integration tests (hits live APIs)
pytest tests/ -v -m integration
```

### Project Structure

```
vigil/
├── src/vectis_intel/
│   ├── server.py          # MCP server entrypoint
│   ├── config.py          # Logging and configuration
│   ├── store/             # IntelStore database layer
│   │   ├── models.py      # Dataclasses and enums
│   │   ├── db.py          # Schema and connection management
│   │   ├── repos.py       # Repository classes
│   │   ├── integrity.py   # Integrity engine
│   │   ├── evidence.py    # Evidence chain traversal
│   │   └── facade.py      # IntelStore facade
│   ├── clients/
│   │   ├── sam_gov.py     # SAM.gov API client
│   │   └── usaspending.py # USAspending.gov API client
│   └── agents/
│       └── procurement.py # Signal extraction logic
├── config/
│   └── watchlists.json    # Monitoring configuration
├── data/
│   └── vectis_intel.db    # SQLite database (auto-created)
└── tests/
    ├── test_store.py
    ├── test_sam_client.py
    ├── test_usaspending_client.py
    ├── test_signal_extraction.py
    ├── test_integration.py
    └── test_server.py
```

## Build Phases

- [x] **Phase 1: Foundation** — Project structure, store refactor, MCP server shell
- [x] **Phase 2: SAM.gov Client** — API client for procurement opportunities
- [x] **Phase 3: Signal Extraction** — Transform API data to Source + Signal pairs
- [x] **Phase 4: MCP Tool Wiring** — Connect clients to MCP tools
- [x] **Phase 5: USAspending** — Contract awards client
- [x] **Phase 6: Operational Polish** — Logging, error handling, config reload

## License

Proprietary - Vectis Labs

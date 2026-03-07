# Procurement Scanner MCP Server — Implementation Plan
### Vectis Market Intelligence | Spec for Claude Code

---

## Overview

Build an MCP server that monitors federal procurement opportunities (SAM.gov) and contract awards (USAspending.gov), extracts structured signals, and persists them to the IntelStore evidence chain database. The server exposes tools callable by Claude Code for both automated collection runs and ad-hoc queries.

**Constraint:** Zero paid APIs. SAM.gov and USAspending.gov are both free public APIs.

---

## Project Structure

```
vectis-intel/
├── README.md
├── pyproject.toml                  # Project metadata + dependencies
├── src/
│   └── vectis_intel/
│       ├── __init__.py
│       ├── server.py               # MCP server entrypoint
│       ├── store/
│       │   ├── __init__.py
│       │   ├── db.py               # IntelDB, schema DDL, connection mgmt
│       │   ├── models.py           # Dataclasses + enums (Source, Signal, etc.)
│       │   ├── integrity.py        # IntegrityEngine
│       │   ├── repos.py            # All repository classes
│       │   ├── evidence.py         # EvidenceChain traversal
│       │   └── facade.py           # IntelStore facade
│       ├── clients/
│       │   ├── __init__.py
│       │   ├── sam_gov.py          # SAM.gov API client
│       │   └── usaspending.py      # USAspending.gov API client
│       ├── agents/
│       │   ├── __init__.py
│       │   └── procurement.py      # Signal extraction logic
│       └── tools/
│           ├── __init__.py
│           ├── procurement_tools.py # MCP tool definitions for procurement
│           └── intel_tools.py       # MCP tool definitions for IntelStore queries
├── config/
│   └── watchlists.json             # Keyword/NAICS watchlists (configurable)
├── data/
│   └── vectis_intel.db             # SQLite database (auto-created)
└── tests/
    ├── test_sam_client.py
    ├── test_usaspending_client.py
    ├── test_signal_extraction.py
    └── test_integrity.py
```

### Key Decision: Refactor intel_store.py

The existing `intel_store.py` monolith should be split into the `store/` package as part of this build. The logic is already well-separated by class — this is a file reorganization, not a rewrite.

---

## Dependencies

```toml
[project]
name = "vectis-intel"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",           # MCP SDK (Model Context Protocol)
    "httpx>=0.27.0",         # Async HTTP client for API calls
    "pydantic>=2.0",         # Optional: request/response validation
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]
```

Note: `mcp` is the official MCP Python SDK from Anthropic (pip install mcp). Use it for server definition, tool registration, and transport.

---

## API Clients

### SAM.gov Opportunities API

**Base URL:** `https://api.sam.gov/opportunities/v2/search`

**Authentication:** Free public access. An API key is optional but recommended for higher rate limits. Register at https://api.data.gov for a free key. If no key, requests are limited to ~1,000/day. With a free key, limit is higher. The key is passed as `?api_key=DEMO_KEY` query param.

**Key Endpoints:**

| Endpoint | Purpose |
|----------|---------|
| `GET /opportunities/v2/search` | Search posted opportunities by keyword, NAICS, dates, type |

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `api_key` | string | API key (use `DEMO_KEY` for testing or get a free key from api.data.gov) |
| `keyword` | string | Search in title and description |
| `naics` | string | NAICS code filter (comma-separated) |
| `postedFrom` | string | Start date (MM/DD/YYYY) |
| `postedTo` | string | End date (MM/DD/YYYY) |
| `ptype` | string | Procurement type: o=solicitation, p=presolicitation, r=sources sought, s=special notice, k=combined synopsis/solicitation |
| `solnum` | string | Solicitation number |
| `limit` | int | Results per page (default 10, max 1000) |
| `offset` | int | Pagination offset |

**Response shape** (relevant fields):

```json
{
  "totalRecords": 142,
  "opportunitiesData": [
    {
      "noticeId": "abc123",
      "title": "GRC Modernization Services",
      "solicitationNumber": "70B03C25R00000123",
      "fullParentPathName": "DEPARTMENT OF THE TREASURY",
      "fullParentPathCode": "020.0000",
      "postedDate": "2026-03-01",
      "type": "Combined Synopsis/Solicitation",
      "baseType": "Combined Synopsis/Solicitation",
      "archiveType": "autocustom",
      "archiveDate": "2026-04-01",
      "responseDeadLine": "2026-03-31T17:00:00-04:00",
      "naicsCode": "541512",
      "classificationCode": "D399",
      "active": "Yes",
      "description": "https://api.sam.gov/opportunities/v2/...",
      "organizationType": "OFFICE",
      "officeAddress": { ... },
      "pointOfContact": [ { "fullName": "...", "email": "..." } ],
      "links": [ { "rel": "self", "href": "..." } ],
      "resourceLinks": [ "https://sam.gov/opp/abc123/view" ]
    }
  ]
}
```

**Important:** The `description` field in search results is a URL, not inline text. To get the full description, make a separate GET to that URL.

**NAICS Codes relevant to Vectis:**

| NAICS | Description | Relevance |
|-------|-------------|-----------|
| 541512 | Computer Systems Design Services | Primary — ServiceNow implementation |
| 541511 | Custom Computer Programming Services | ServiceNow development |
| 541519 | Other Computer Related Services | Broad IT services |
| 518210 | Computing Infrastructure Providers | Cloud/SaaS infrastructure |
| 541611 | Administrative Management Consulting | GRC consulting |
| 541690 | Other Scientific and Technical Consulting | Technical advisory |

**Keywords to monitor:**

```json
{
  "primary": [
    "ServiceNow", "GRC", "governance risk compliance",
    "FISMA", "NIST 800-53", "risk management framework",
    "IRM", "integrated risk management"
  ],
  "secondary": [
    "IT service management", "ITSM modernization",
    "workflow automation", "low-code platform",
    "FedRAMP", "authority to operate", "ATO"
  ],
  "innovation": [
    "AI agent", "agentic AI", "MCP server",
    "model context protocol", "AI automation"
  ]
}
```

**Rate Limiting:** Be conservative. Run search queries no more than 1 per second. Batch results by date range (e.g., last 7 days) rather than running broad open-ended queries.

### SAM.gov Client Implementation Notes

```python
# src/vectis_intel/clients/sam_gov.py

class SamGovClient:
    """
    Client for SAM.gov Opportunities API.
    
    Key behaviors:
    - Uses httpx.AsyncClient for async HTTP
    - Respects rate limits (1 req/sec)
    - Handles pagination automatically
    - Returns typed dataclasses, not raw dicts
    - All errors logged, never silently swallowed
    """
    
    BASE_URL = "https://api.sam.gov/opportunities/v2/search"
    
    # Methods to implement:
    # - search_opportunities(keywords, naics_codes, posted_after, posted_before, ptype, limit)
    #   → list[SamOpportunity]
    # - get_opportunity_detail(notice_id)
    #   → SamOpportunityDetail (includes full description text)
    # - search_by_watchlist(watchlist: Watchlist)
    #   → list[SamOpportunity] (runs all keyword/NAICS combos from config)
```

### USAspending.gov API

**Base URL:** `https://api.usaspending.gov/api/v2/`

**Authentication:** None. Fully public, no API key needed.

**Key Endpoints:**

| Endpoint | Purpose |
|----------|---------|
| `POST /search/spending_by_award/` | Search contract awards by keyword, agency, NAICS |
| `POST /search/spending_by_category/` | Aggregate spending by category |
| `GET /awards/{award_id}/` | Award detail |
| `POST /recipient/` | Lookup recipient (contractor) details |

**Search Awards Request:**

```json
{
  "filters": {
    "keywords": ["ServiceNow", "GRC"],
    "time_period": [
      { "start_date": "2025-01-01", "end_date": "2026-03-07" }
    ],
    "naics_codes": [{ "require": ["541512"] }],
    "award_type_codes": ["A", "B", "C", "D"]
  },
  "fields": [
    "Award ID", "Recipient Name", "Award Amount",
    "Awarding Agency", "Start Date", "NAICS Code",
    "Description"
  ],
  "limit": 25,
  "page": 1,
  "sort": "Award Amount",
  "order": "desc"
}
```

**Response shape:**

```json
{
  "results": [
    {
      "Award ID": "70B03C22F00001234",
      "Recipient Name": "DELOITTE CONSULTING LLP",
      "Award Amount": 4500000.00,
      "Awarding Agency": "Department of the Treasury",
      "Start Date": "2025-06-01",
      "NAICS Code": "541512",
      "Description": "ServiceNow GRC implementation and FISMA compliance..."
    }
  ],
  "page_metadata": { "page": 1, "hasNext": true, "total": 87 }
}
```

**USAspending client notes:**
- POST-based search (not GET)
- Pagination via `page` parameter
- No rate limit published, but be respectful — 1 req/sec max
- Award type codes: A=BPA Call, B=Purchase Order, C=Delivery Order, D=Definitive Contract

### USAspending Client Implementation Notes

```python
# src/vectis_intel/clients/usaspending.py

class USAspendingClient:
    """
    Client for USAspending.gov Awards API.
    
    Key behaviors:
    - POST-based search endpoints
    - Auto-pagination
    - Typed response models
    """
    
    BASE_URL = "https://api.usaspending.gov/api/v2"
    
    # Methods to implement:
    # - search_awards(keywords, naics_codes, date_range, limit)
    #   → list[AwardSummary]
    # - get_award_detail(award_id)
    #   → AwardDetail
    # - search_by_recipient(recipient_name, date_range)
    #   → list[AwardSummary] (competitor research)
    # - search_by_agency(agency_name, naics_codes, date_range)
    #   → list[AwardSummary] (agency pipeline research)
```

---

## Signal Extraction Logic

### Procurement Agent

```python
# src/vectis_intel/agents/procurement.py

class ProcurementAgent:
    """
    Transforms raw API responses into Source + Signal pairs
    for the IntelStore.
    
    This is the critical layer where data quality is enforced.
    Every signal MUST:
    - Link to at least one source with a verifiable URL
    - Have an appropriate confidence level
    - Contain a factual summary (no interpretation)
    - Include domain_tags and entity_refs for downstream correlation
    """
```

**SAM.gov opportunity → Source + Signal mapping:**

| API Field | Maps To | Entity |
|-----------|---------|--------|
| `resourceLinks[0]` | `source.url` | Source |
| `title` | `source.title` | Source |
| `"SAM.gov"` | `source.publisher` | Source |
| `postedDate` | `source.published_at` | Source |
| `"procurement_posting"` | `source.source_type` | Source |
| `"api_automated"` | `source.collection_method` | Source |
| `"procurement_scanner"` | `source.collector_agent` | Source |
| — | — | — |
| `"rfp_posted"` | `signal.signal_type` | Signal |
| (generated summary) | `signal.summary` | Signal |
| `fullParentPathName` → normalized | `signal.entity_refs` | Signal |
| (from keyword match analysis) | `signal.domain_tags` | Signal |
| `"verified"` | `signal.confidence` | Signal |
| `"Direct SAM.gov posting: {solicitationNumber}"` | `signal.confidence_rationale` | Signal |
| `responseDeadLine` | `signal.expires_at` | Signal |

**Summary generation rule:** The signal summary must be a factual statement, not an interpretation. Template:

```
"{agency} posted {type} for '{title}' (SOL# {solicitationNumber}), 
NAICS {naicsCode}, response due {responseDeadLine}."
```

No: "Treasury is investing in GRC modernization."
Yes: "Department of the Treasury posted Combined Synopsis/Solicitation for 'GRC Modernization Services' (SOL# 70B03C25R00000123), NAICS 541512, response due 2026-03-31."

**Domain tag inference:** Match opportunity title + description against the keyword watchlist. Tag with all matching categories (primary → `servicenow`, `grc`, etc; secondary → `itsm`, `fedramp`; innovation → `ai_agents`, `mcp`).

**USAspending award → Source + Signal mapping follows the same pattern:**
- `signal_type` = `"contract_awarded"`
- Summary: "{recipient} awarded ${amount} contract by {agency} for '{description}' (Award# {awardId}), NAICS {naics}."
- `confidence` = `"verified"` (USAspending is authoritative)
- No `expires_at` (awards don't expire)

**Deduplication:** Before creating a signal, check if a signal with matching `signal_type` + matching source URL already exists in the database. If yes, skip (idempotent collection runs).

---

## MCP Tools

### Procurement Tools

```python
# src/vectis_intel/tools/procurement_tools.py

# Tool: scan_opportunities
# Description: Search SAM.gov for procurement opportunities matching 
#   Vectis watchlist keywords and NAICS codes. Creates Source + Signal 
#   records in IntelStore for each new opportunity found.
# Parameters:
#   - posted_within_days: int (default 7) — look back N days
#   - keywords: list[str] | None — override watchlist keywords
#   - naics_codes: list[str] | None — override watchlist NAICS
# Returns: Summary of new signals created (count, titles, deadlines)

# Tool: scan_awards
# Description: Search USAspending.gov for recent contract awards 
#   matching watchlist criteria. Creates Source + Signal records.
# Parameters:
#   - awarded_within_days: int (default 30) — look back N days
#   - keywords: list[str] | None
#   - naics_codes: list[str] | None
#   - recipient: str | None — filter by contractor name (competitor research)
# Returns: Summary of new signals created

# Tool: get_opportunity_detail
# Description: Fetch full details for a specific SAM.gov opportunity 
#   by notice ID or solicitation number. Returns structured data 
#   without creating signals (for human review).
# Parameters:
#   - notice_id: str | None
#   - solicitation_number: str | None
# Returns: Full opportunity data including description, contacts, dates

# Tool: search_competitor_awards
# Description: Search USAspending for awards to a specific competitor.
#   Creates Source + Signal records for each.
# Parameters:
#   - competitor_name: str (e.g., "Deloitte Consulting")
#   - naics_codes: list[str] | None
#   - awarded_within_days: int (default 365)
# Returns: Award history summary
```

### IntelStore Query Tools

```python
# src/vectis_intel/tools/intel_tools.py

# Tool: list_signals
# Description: Query signals from the IntelStore with filters.
# Parameters:
#   - confidence: str | None — filter by verified/inferred/speculative
#   - domain_tag: str | None — filter by domain tag
#   - signal_type: str | None — filter by type
#   - active_only: bool (default True) — exclude expired/superseded
#   - limit: int (default 20)
# Returns: List of signals with source counts

# Tool: trace_evidence
# Description: Full evidence chain traversal for a signal or opportunity.
# Parameters:
#   - signal_id: str | None
#   - opportunity_id: str | None
# Returns: Complete chain: opportunity → correlations → signals → sources

# Tool: integrity_audit
# Description: Run full integrity audit on the IntelStore.
# Returns: Orphan signals, stale signals, agent trust scores, integrity status

# Tool: list_stale_signals
# Description: List signals past their expiration date.
# Returns: Stale signals with days-stale count

# Tool: agent_trust_report
# Description: Verification success rate per collection agent.
# Returns: Per-agent trust scores and signal counts

# Tool: pipeline_summary
# Description: Opportunity pipeline by lane and status.
# Returns: Counts, total value, avg verification/fit scores by lane
```

---

## Watchlist Configuration

```json
// config/watchlists.json
{
  "version": "1.0",
  "updated_at": "2026-03-07",
  "naics_codes": {
    "primary": ["541512", "541511"],
    "secondary": ["541519", "518210", "541611", "541690"]
  },
  "keywords": {
    "servicenow": ["ServiceNow", "service-now", "SNOW platform"],
    "grc": ["GRC", "governance risk compliance", "risk management framework", "integrated risk management", "IRM"],
    "fisma": ["FISMA", "NIST 800-53", "NIST SP 800-53", "security controls", "control assessment"],
    "fedramp": ["FedRAMP", "cloud authorization", "authority to operate", "ATO"],
    "itsm": ["IT service management", "ITSM modernization", "incident management platform"],
    "automation": ["workflow automation", "process automation", "low-code platform"],
    "ai_innovation": ["AI agent", "agentic AI", "MCP server", "model context protocol", "AI-powered automation", "intelligent automation"]
  },
  "competitors": {
    "large_primes": ["Deloitte Consulting", "Booz Allen Hamilton", "Accenture Federal", "KPMG"],
    "servicenow_partners": ["Thirdera", "Cask", "Infocenter", "GlideFast Consulting", "Crossfuze"]
  },
  "agencies_of_interest": [
    "Department of the Treasury",
    "Department of Homeland Security",
    "Department of Defense",
    "General Services Administration",
    "Environmental Protection Agency",
    "Department of Energy"
  ]
}
```

---

## MCP Server Registration

The server registers with Claude Code via the standard MCP config:

```json
// Claude Code MCP config (~/.claude/mcp.json or project-level)
{
  "mcpServers": {
    "vectis-intel": {
      "command": "python",
      "args": ["-m", "vectis_intel.server"],
      "env": {
        "SAM_GOV_API_KEY": "DEMO_KEY",
        "INTEL_DB_PATH": "./data/vectis_intel.db"
      }
    }
  }
}
```

The server entrypoint (`server.py`) should:
1. Initialize the IntelStore (creates DB if not exists)
2. Load watchlist config from `config/watchlists.json`
3. Register all MCP tools (procurement + intel query tools)
4. Start the MCP server on stdio transport

---

## Build Order

**Phase 1: Foundation** (do first, validates everything)
1. Set up project structure with pyproject.toml
2. Refactor `intel_store.py` into `store/` package (split by file, same logic)
3. Write `store/` unit tests to verify refactor didn't break anything
4. Implement basic MCP server shell (`server.py`) with a single ping tool to verify Claude Code connectivity

**Phase 2: SAM.gov Client**
1. Implement `SamGovClient` with `search_opportunities` method
2. Write integration test that hits live SAM.gov API with a known keyword ("ServiceNow") and verifies response parsing
3. Implement `get_opportunity_detail` for full description fetch
4. Implement `search_by_watchlist` that runs all keyword/NAICS combos

**Phase 3: Signal Extraction**
1. Implement `ProcurementAgent.extract_from_sam_opportunity()` — transforms a SAM opportunity into Source + Signal + SignalSource objects
2. Implement deduplication check (skip if source URL already exists)
3. Implement domain tag inference from keyword matching
4. Write unit tests with sample SAM.gov response data

**Phase 4: MCP Tool Wiring**
1. Implement `scan_opportunities` tool — calls SamGovClient → ProcurementAgent → IntelStore
2. Implement `get_opportunity_detail` tool
3. Implement `list_signals` and `trace_evidence` query tools
4. Implement `integrity_audit` tool
5. Test full loop via Claude Code: "scan for ServiceNow opportunities posted this week"

**Phase 5: USAspending**
1. Implement `USAspendingClient` with `search_awards` method
2. Implement signal extraction for awards
3. Implement `scan_awards` and `search_competitor_awards` tools
4. Test: "show me what Deloitte has won in NAICS 541512 in the last year"

**Phase 6: Operational Polish**
1. Implement `watchlists.json` loader with hot-reload on config change
2. Add logging throughout (structured JSON logs)
3. Error handling: API timeouts, rate limits, malformed responses
4. Add `pipeline_summary` and `agent_trust_report` tools
5. README with setup instructions

---

## Testing Strategy

**Unit tests** (no network):
- Signal extraction from sample API responses
- Integrity engine rules (orphan signals, human-only opportunities, confidence degradation)
- Deduplication logic
- Domain tag inference

**Integration tests** (hits live APIs):
- SAM.gov search with known keyword returns parseable results
- USAspending search returns parseable results
- Full pipeline: search → extract → store → query → trace evidence

**Mark integration tests** with `@pytest.mark.integration` so they can be excluded from CI runs that shouldn't hit external APIs.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SAM_GOV_API_KEY` | No | `DEMO_KEY` | API key from api.data.gov (free registration for higher rate limits) |
| `INTEL_DB_PATH` | No | `./data/vectis_intel.db` | Path to SQLite database |
| `WATCHLIST_PATH` | No | `./config/watchlists.json` | Path to watchlist config |
| `LOG_LEVEL` | No | `INFO` | Logging level |

---

## Success Criteria

After Phase 4 is complete, you should be able to open Claude Code and have this conversation:

```
You: Scan SAM.gov for ServiceNow and GRC opportunities posted in the last 14 days

Claude: [calls scan_opportunities tool]
Found 8 new opportunities. Created 8 signals:
1. [verified] Department of Treasury posted Sources Sought for 'GRC Platform Modernization'...
2. [verified] DHS/CISA posted Combined Synopsis for 'FISMA Continuous Monitoring Tools'...
...

You: Show me the evidence chain for that Treasury opportunity

Claude: [calls trace_evidence tool]
Signal: Treasury posted Sources Sought for 'GRC Platform Modernization'...
  └─ Source: https://sam.gov/opp/xyz789/view (SAM.gov, captured today, URL live)
  └─ Confidence: verified (Direct SAM.gov posting: SOL# 70B03C25R00000456)
  └─ Domain tags: servicenow, grc, federal, fisma
  └─ Expires: 2026-04-15

You: Search what Deloitte has won in this space recently

Claude: [calls search_competitor_awards tool]
Found 3 awards to Deloitte Consulting in NAICS 541512 in the last 12 months:
1. $4.5M — Department of Treasury — "ServiceNow GRC Implementation Phase 2"
2. $2.1M — DHS — "FISMA Compliance Platform Support"
...

You: Run an integrity audit

Claude: [calls integrity_audit tool]
✓ 0 orphan signals
✓ 0 non-human opportunities  
✓ 2 stale signals (past response deadline)
✓ Agent trust: procurement_scanner 1.0 (14 signals, 14 verified)
✓ Integrity: OK
```

That's the target experience. The system finds real opportunities, links them to real sources, and you can trace every claim back to a URL.

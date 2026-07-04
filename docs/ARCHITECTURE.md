# Vigil — Architecture Document

> Vectis Labs Market Intelligence Platform
> Last updated: 2026-07-03

---

## System Overview

Vigil is an MCP (Model Context Protocol) server that monitors federal procurement opportunities, contract awards, and community pain signals across ServiceNow channels. It extracts structured intelligence with full provenance tracking and surfaces ranked digests for human review.

**Core guarantee:** every signal is traceable to a verifiable URL. The system counts and ranks — it does not decide.

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude Code (MCP Host)                   │
│                                                             │
│   Skills: opportunity-scorer, capability-statement,         │
│           intelligence-briefing, signal-dashboard,          │
│           competitive-tracker, store-crossref               │
└───────────────────────────┬─────────────────────────────────┘
                            │ MCP Protocol
┌───────────────────────────▼─────────────────────────────────┐
│                    MCP Server (server.py)                    │
│                                                             │
│   12 tools: scan, query, audit, trace                       │
│   Hot-reload config │ Structured logging                    │
└──────┬──────────┬──────────┬──────────┬─────────────────────┘
       │          │          │          │
  ┌────▼────┐ ┌──▼───┐ ┌───▼────┐ ┌───▼──────────┐
  │ Clients │ │Agent │ │ Store  │ │  Community   │
  │ sam_gov │ │procur│ │ facade │ │  Scanner     │
  │ usaspend│ │ement │ │ repos  │ │  ingest/     │
  └────┬────┘ └──┬───┘ │ integ. │ │  classify    │
       │         │     │ evid.  │ │  score/digest│
       │         │     └───┬────┘ └───┬──────────┘
       │         │         │          │
  ┌────▼─────────▼─────────▼──────────▼───────────┐
  │              SQLite (WAL mode)                  │
  │                                                │
  │  sources │ signals │ signal_sources             │
  │  correlations │ opportunities │ verifications   │
  │  community_signals │ signal_clusters            │
  │  cluster_scores │ digest_entries │ ingest_state │
  │  cluster_promotions                             │
  └────────────────────────────────────────────────┘
```

---

## Layer Architecture

### 1. MCP Server (`server.py`)

Entry point. Registers 12 tools across 5 categories:

| Category | Tools | Purpose |
|----------|-------|---------|
| Health | `ping`, `reload_watchlist` | Server status, config hot-reload |
| Procurement | `scan_opportunities`, `get_opportunity_detail` | SAM.gov opportunity ingestion |
| Awards | `scan_awards`, `search_competitor_awards` | USAspending contract monitoring |
| Queries | `list_signals`, `trace_evidence`, `list_stale_signals` | Evidence chain traversal |
| Analytics | `integrity_audit`, `agent_trust_report`, `pipeline_summary` | System health and pipeline views |

**Configuration** (environment variables):

| Variable | Default | Purpose |
|----------|---------|---------|
| `SAM_GOV_API_KEY` | `""` | SAM.gov API key |
| `INTEL_DB_PATH` | `./data/vectis_intel.db` | SQLite database path |
| `WATCHLIST_PATH` | `./config/watchlists.json` | Watchlist config |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `LOG_JSON` | `false` | Structured JSON logging |

All tool handlers return `list[TextContent]` with JSON payloads.

---

### 2. HTTP Clients (`clients/`)

Async httpx clients with rate limiting and retry logic.

#### SAM.gov Client (`sam_gov.py`)
- **API:** `https://api.sam.gov/opportunities/v2/search`
- **Auth:** API key (optional, higher rate limits)
- **Rate limit:** 2.0s between requests (configurable)
- **Retry:** Exponential backoff on 429/5xx, 5 max retries
- **Key methods:** `search_opportunities()`, `search_by_watchlist()`, `get_opportunity_detail()`
- **Note:** Description field is a URL requiring separate fetch

#### USAspending Client (`usaspending.py`)
- **API:** `https://api.usaspending.gov/api/v2` (POST-based search)
- **Auth:** None required (public API)
- **Rate limit:** 1.0s between requests
- **Key methods:** `search_awards()`, `search_by_recipient()`, `search_by_agency()`

Both clients return typed dataclasses, never raw dicts.

---

### 3. Signal Extraction (`agents/procurement.py`)

`ProcurementAgent` transforms raw API responses into Source + Signal + SignalSource triples.

**Extraction rules:**
- SAM.gov opportunities → `RFP_POSTED` signals (confidence: `VERIFIED`)
- USAspending awards → `CONTRACT_AWARDED` signals (confidence: `VERIFIED`)
- Summaries are factual templates, never interpretive
- Domain tags inferred from watchlist keyword matching
- Deduplication by source URL (both database-wide and intra-batch)

**Summary template (opportunities):**
```
"{agency} posted {type} for '{title}' (SOL# {solNum}), NAICS {code}, response due {deadline}."
```

**Summary template (awards):**
```
"{recipient} awarded ${amount} contract by {agency} for '{desc}' (Award# {id}), NAICS {code}."
```

---

### 4. Data Store (`store/`)

Six-module storage layer with provenance-first design.

#### Schema (`db.py`)

```
sources ──────── signal_sources ──────── signals
                 (provenance)            │
                                         │ signal_ids (JSON)
                                    correlations
                                         │ source_correlation_ids
                                    opportunities
                                         │
                                    verifications
```

**Connection setup:** SQLite with WAL mode, foreign keys enforced, `sqlite3.Row` factory.

**Timestamp convention:** ISO 8601 UTC as TEXT (`datetime.now(timezone.utc).isoformat()`).

**ID convention:** UUID4 strings for all entity IDs.

#### Models (`models.py`)

14 enums constraining all categorical fields. 6 dataclasses mapping to tables:

| Dataclass | Key Fields |
|-----------|------------|
| `Source` | `source_type`, `url`, `url_status`, `collection_method`, `collector_agent` |
| `Signal` | `signal_type`, `summary`, `confidence`, `confidence_rationale`, `expires_at` |
| `SignalSource` | `signal_id`, `source_id`, `relevance`, `excerpt` |
| `Correlation` | `signal_ids` (JSON), `correlation_type`, `hypothesis`, `strength` |
| `Opportunity` | `lane`, `status`, `verification_score`, `fit_score`, `created_by` (always "human") |
| `Verification` | `target_type`, `target_id`, `result`, `failure_reason` |

#### Repositories (`repos.py`)

CRUD operations per entity type. Key constraints enforced in code:

- **No orphan signals:** `SignalRepo.create()` requires ≥1 `SignalSource`
- **Human-only opportunities:** `OpportunityRepo.create()` enforces `created_by = 'human'`
- **Correlation minimum:** `CorrelationRepo.create()` requires ≥2 signal IDs

#### Integrity Engine (`integrity.py`)

Anti-hallucination enforcement:

| Rule | Enforcement |
|------|-------------|
| No orphan signals | Every signal must link to ≥1 source |
| Human-only opportunities | `created_by` must be "human" |
| Strength bounded by evidence | Correlation strength ≤ weakest underlying signal |
| Stale signal flagging | Past-deadline signals auto-detected |
| Confidence degradation | Stale signals cascade weakness to correlations |
| Trust scoring | Per-agent verification success rates |

`run_integrity_audit()` returns a full system health report.

#### Evidence Chain (`evidence.py`)

Traverses the provenance graph:
```
Opportunity → Correlations → Signals → Sources → URLs
```

Answers "why are we pursuing this?" with a linked chain back to verifiable documents.

#### Facade (`facade.py`)

`IntelStore` composes all repositories + integrity + evidence into a single entry point:
```python
with IntelStore(db_path) as store:
    store.sources.create(...)
    store.signals.create(...)
    store.integrity.run_integrity_audit()
    store.evidence.trace_signal(signal_id)
```

---

### 5. Community Scanner (`community/`)

Counts recurring ServiceNow pain across community channels, classifies by taxonomy, scores monthly, and generates weekly ranked digests.

#### Module Layout

```
community/
├── taxonomy.yaml        # 25 clusters, 6 lanes, scoring config
├── schema.py            # Additive SQLite DDL (6 tables)
├── config.py            # TaxonomyManager (YAML + hot-reload)
├── classify.py          # Pure-function keyword matcher
├── score.py             # Monthly composite scoring
├── digest.py            # Weekly ranked digest generator
├── promote.py           # Cluster → Opportunity promotion bridge
├── sync_taxonomy.py     # YAML → signal_clusters upsert
└── ingest/
    ├── base.py          # Shared: upsert, watermark, derived fields
    ├── sn_community.py  # Khoros RSS (7 boards)
    ├── reddit.py        # Official API, r/servicenow
    └── stackoverflow.py # Stack Exchange API
```

#### Classification (`classify.py`)

Pure function: `classify(title, body, taxonomy) → cluster_slug | None`

- Case-insensitive substring matching
- Threshold: `min_keyword_hits` (default 2)
- Ties: highest hit count wins; still tied → first in taxonomy order (logged)
- No match → `cluster_id = NULL` (uncategorized — this is data, not an error)

**Derived-at-ingest fields** (deterministic, no LLM):
- `has_large_code_block`: fenced/`<pre>`/indented blocks exceeding threshold lines
- `commercial_hits`: count of commercial keyword matches in title + body

#### Scoring (`score.py`)

Monthly, per active cluster, trailing 12-month window:

```
composite = lane_weight × Σ (weight_i × factor_i)
```

| Factor | Weight | Computation |
|--------|--------|-------------|
| `thread_count_norm` | 0.30 | cluster threads / max threads across clusters |
| `unsolved_rate` | 0.20 | 1 - (solved / total) |
| `workaround_rate` | 0.20 | threads with large code blocks / total |
| `commercial_rate` | 0.15 | threads with commercial hits / total |
| `store_gap_score` | 0.15 | from vigil-store-crossref (NULL → 0.5) |

**v1.1 scoring scope rules:**
- Lane weights apply to **app_candidate ranking only**
- **Outlier override:** top-N (default 3) by raw `thread_count × unsolved_rate` always surface in digest, regardless of lane-weighted rank
- **Content-candidate flagging is lane-agnostic:** `min_views` + unsolved, because SEO value doesn't care about portfolio fit

Scores are append-only (never overwritten). History enables week-over-week deltas.

#### Taxonomy (`taxonomy.yaml`)

v1.1: 25 clusters across 6 lanes.

| Lane | Weight | Rationale |
|------|--------|-----------|
| `grc` | 1.3 | $500-2000/mo apps, near-zero Store competition |
| `secops` | 1.0 | Planned knowledge pack, moderate competition |
| `platform_utility` | 1.0 | $200-1000/mo apps, contestable but broad demand |
| `hrsd` | 0.9 | Planned knowledge pack, less founder track record |
| `itsm` | 0.7 | Saturated Store category |
| `other` | 0.6 | Catch-all |

Weights encode pricing power + competition, not founder knowledge. Compressed range (1.3/0.7 vs old 1.5/0.3) because NowForge plugin-factory economics lower per-app build cost.

#### Digest (`digest.py`)

Weekly output:
1. **Top 10 clusters** by composite score, with delta vs. prior digest
2. **Per cluster:** 3 highest-view raw thread links (non-negotiable — scores get you to the neighborhood, reading the poster's actual words is where judgment happens)
3. **Outlier overrides:** clusters surfaced by raw frequency despite low lane weight
4. **Content candidates:** high-view + unsolved clusters (lane-agnostic)
5. **Uncategorized monitor:** count + 5 sample titles (taxonomy drift detection)

Two dispositions: `app_candidate` (Store pipeline) and `content_candidate` (Gotcha Journal / SEO). Both stay NULL until human review.

#### Ingestion

Three sources, daily cron cadence. Failures log and skip — one dead source must not block the others.

| Source | API | Cadence | Key Notes |
|--------|-----|---------|-----------|
| SN Community | Khoros RSS | Daily | **GO/NO-GO gate** — verify feeds first |
| Reddit | Official OAuth API | Daily | r/servicenow, paginate to watermark |
| Stack Overflow | Stack Exchange API | Daily | `servicenow` tag, free quota sufficient |

All ingesters emit normalized dicts → `community_signals` rows. Dedupe on `(source, external_id)`; on conflict, UPDATE mutable fields only.

---

### 6. Configuration (`config/`)

#### Watchlist (`watchlists.json`)

Drives all procurement scanning:
```
├── naics_codes (primary: 541512, 541511 + 4 secondary)
├── keywords (7 categories: servicenow, grc, fisma, fedramp, itsm, automation, ai_innovation)
├── competitors (large_primes + servicenow_partners)
└── agencies_of_interest
```

Hot-reloadable via `WatchlistManager` (file mtime tracking).

#### Taxonomy (`community/taxonomy.yaml`)

Drives community classification and scoring. Hot-reloadable via `TaxonomyManager`.

---

## Data Flow Patterns

### Procurement Scan

```
watchlist.json → SamGovClient.search_by_watchlist()
    → ProcurementAgent.extract_batch()
    → IntelStore: sources.create() + signals.create()
    → JSON response via MCP
```

### Community Scan

```
taxonomy.yaml → sync_taxonomy() → signal_clusters
    → Ingesters (RSS/API) → upsert_signal() → community_signals
    → classify() → cluster_id assignment
    → score_clusters() → cluster_scores (append-only)
    → generate_digest() → digest_entries + JSON output
```

### Cluster Promotion (community → procurement pipeline)

```
Human disposition: "promote test_cluster"
    → promote_cluster(slug, digest_date, n_threads=5)
    → Guard: cluster active, score exists, no active promotion
    → Select top-N threads by view_count in scoring window
    → Per thread:
        Source: dedupe by URL (reuse or create, type=COMMUNITY_POST)
        Signal: type=COMMUNITY_DEMAND, confidence=VERIFIED
        SignalSource: relevance=PRIMARY, excerpt=title
    → Correlation: type=RECURRING_DEMAND, hypothesis=factual stats
    → Auto-review correlation (human IS the gate)
    → Opportunity: lane mapped from cluster, status=WATCHING, fit_score=0.0
    → cluster_promotions audit row
    → trace_evidence() walks back to N thread URLs
```

Core design: threads are signals (each URL-verifiable); the aggregate stat is a correlation hypothesis. No anti-hallucination violation because every Signal links to a real URL.

### Evidence Trace

```
signal_id → EvidenceChain.trace_signal()
    → signal + signal_sources + sources + verifications
    → Full provenance chain to verifiable URLs
```

---

## Design Principles

1. **Anti-hallucination:** Every signal traceable to a URL. IntegrityEngine enforces this at write time.
2. **Human gate:** Opportunities are human-created only. AI systems count, rank, and surface — they do not decide.
3. **Append-only scoring:** Score history is never overwritten. Deltas require history.
4. **Fail-safe ingestion:** One dead source must not block others. Log and skip.
5. **Taxonomy-driven classification:** Hand-built keyword maps are debuggable and honest about what they know. The uncategorized pile is itself a signal.
6. **Config-driven weights:** No hardcoded scoring weights. All configurable in YAML/JSON.

---

## Explicitly NOT Built (v1)

- Embeddings/RAG clustering (trigger: uncategorized > ~20% sustained)
- Sentiment analysis, deal-size inference, engagement prediction
- Reply-thread ingestion (first post only)
- Auto-disposition or auto-routing past the human gate
- SN Community scraping fallback (human decision if RSS is dead)
- Automated correlation creation (human-only today)

---

## Dependencies

```toml
mcp>=1.0.0              # Model Context Protocol SDK
httpx>=0.27.0            # Async HTTP client
pydantic>=2.0            # Validation
pyyaml>=6.0              # Taxonomy config
python-dateutil>=2.9     # Date math for scoring windows
```

Python ≥3.11 required. Build system: hatchling.

---

## Test Coverage

65 community scanner tests + existing procurement tests. 148 total passing (non-integration).

| Test File | Covers |
|-----------|--------|
| `test_community_classify.py` | Keyword matching, ties, thresholds, code block detection, commercial hits |
| `test_community_ingest.py` | Watermark tracking, upsert/dedupe, RSS parsing |
| `test_community_score.py` | Normalization, NULL store_gap, empty windows, lane weights, outlier override |
| `test_community_promote.py` | Full promotion chain, evidence trace, guards, source dedupe, re-promotion, audit |
| `test_store.py` | SourceRepo, SignalRepo, integrity rules |
| `test_signal_extraction.py` | ProcurementAgent signal transformation |
| `test_sam_client.py` | SAM.gov client (integration) |
| `test_usaspending_client.py` | USAspending client (integration) |
| `test_server.py` | MCP tool definitions |
| `test_config.py` | Watchlist loading |
| `test_integration.py` | Full pipeline |

Run: `PYTHONPATH=src python3 -m pytest tests/ -v -m "not integration"`

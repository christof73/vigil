# Vigil — User Guide

> Vectis Labs Market Intelligence Platform
> MCP server + Claude Code skills for federal procurement and community signal monitoring

---

## Prerequisites

- Python 3.11+
- Claude Code CLI (or Claude Desktop)
- SAM.gov API key (free at sam.gov > Profile > Public API Key)
- Reddit API credentials (optional, for community ingestion)

### Installation

```bash
cd vigil
pip install -e ".[dev]"
```

### Environment Variables

Set these before starting the server:

| Variable | Required | Purpose |
|----------|----------|---------|
| `SAM_GOV_API_KEY` | Yes (for procurement) | SAM.gov API key |
| `INTEL_DB_PATH` | No | SQLite path (default: `./data/vectis_intel.db`) |
| `WATCHLIST_PATH` | No | Watchlist config (default: `./config/watchlists.json`) |
| `TAXONOMY_PATH` | No | Community taxonomy (default: auto-detected) |
| `REDDIT_CLIENT_ID` | For Reddit ingestion | Reddit script app client ID |
| `REDDIT_CLIENT_SECRET` | For Reddit ingestion | Reddit script app client secret |
| `LOG_LEVEL` | No | `DEBUG`, `INFO` (default), `WARNING`, `ERROR` |
| `LOG_JSON` | No | `true` for structured JSON logging |

---

## Quick Start

### 1. Verify the server is running

```
> Use the ping tool to check server status.
```

Response confirms database connection, API key status, and watchlist stats.

### 2. Run your first procurement scan

```
> Scan SAM.gov for opportunities posted in the last 7 days matching our watchlist.
```

This calls `scan_opportunities` with default parameters — searches all watchlist keywords and NAICS codes, creates Source + Signal records for each new opportunity found.

### 3. Check what was found

```
> List the latest signals.
```

Returns signals sorted by recency with confidence levels and domain tags.

### 4. Score an opportunity

```
> Score this opportunity: [paste SAM.gov solicitation details]
```

Triggers the `/vigil-opportunity-scorer` skill — produces a qualification card with go/no-go recommendation.

---

## Tool Reference

Vigil exposes 18 MCP tools across 6 categories. You don't call tools directly — describe what you want and Claude selects the right tool.

### Health & Config

| What to say | Tool called | What happens |
|-------------|-------------|--------------|
| "Check if Vigil is running" | `ping` | Returns server status, DB connection, API key status |
| "Reload the watchlist" | `reload_watchlist` | Hot-reloads `watchlists.json` from disk |

### Procurement Scanning

| What to say | Tool called | What happens |
|-------------|-------------|--------------|
| "Scan SAM.gov for new opportunities" | `scan_opportunities` | Searches SAM.gov by watchlist keywords/NAICS, creates signals |
| "Scan for opportunities posted in the last 30 days" | `scan_opportunities` | Same, with custom lookback window |
| "Search SAM.gov for GRC opportunities" | `scan_opportunities` | Override keywords with specific terms |
| "Get details on solicitation 70B03C25R00000123" | `get_opportunity_detail` | Fetches full opportunity without creating signals |

### Award Monitoring

| What to say | Tool called | What happens |
|-------------|-------------|--------------|
| "Scan USAspending for recent contract awards" | `scan_awards` | Searches by watchlist, creates award signals |
| "What contracts has Deloitte won recently?" | `search_competitor_awards` | Searches awards by recipient name |
| "Show Booz Allen's ServiceNow awards from the past year" | `search_competitor_awards` | Competitor-specific with NAICS filter |

### Intelligence Queries

| What to say | Tool called | What happens |
|-------------|-------------|--------------|
| "List active signals" | `list_signals` | Returns signals filtered by confidence, type, or domain |
| "Show me all GRC signals" | `list_signals` | Filtered by domain tag |
| "Trace the evidence chain for opportunity X" | `trace_evidence` | Walks Opportunity → Correlations → Signals → Sources → URLs |
| "What signals have expired?" | `list_stale_signals` | Lists past-deadline signals |

### System Health

| What to say | Tool called | What happens |
|-------------|-------------|--------------|
| "Run an integrity audit" | `integrity_audit` | Checks for orphan signals, stale cascades, trust scores |
| "Show agent trust scores" | `agent_trust_report` | Verification success rate per collection agent |
| "Show the pipeline summary" | `pipeline_summary` | Opportunities grouped by lane and status |

### Community Scanner

| What to say | Tool called | What happens |
|-------------|-------------|--------------|
| "Ingest community threads" | `community_ingest` | Pulls from SN Community, Reddit, Stack Overflow |
| "Ingest from Reddit only" | `community_ingest` | Single-source ingestion |
| "Score the community clusters" | `community_score` | Monthly composite scoring, returns outlier slugs |
| "Generate the community digest" | `community_digest` | Weekly ranked digest with top clusters, deltas, content candidates |
| "Show community scanner status" | `community_status` | Cluster counts, watermarks, uncategorized %, promotion audit |
| "Sync the taxonomy" | `sync_taxonomy` | Upserts taxonomy.yaml → signal_clusters table |
| "Promote cluster grc_evidence_collection from digest 2026-07-01" | `community_promote` | Creates full provenance chain: Signals → Correlation → Opportunity |

---

## Daily Workflow

### Morning Scan (5 minutes)

```
1. "Scan SAM.gov for opportunities posted in the last 2 days"
2. "Scan USAspending for awards from the last week"
3. "List new signals — anything interesting?"
```

Claude scans both APIs, creates signals, and summarizes what's new. If anything looks promising:

```
4. "Score this opportunity" (paste or reference by signal ID)
5. "Write me a briefing on the Treasury GRC signals"
```

### Weekly Community Review (10 minutes)

```
1. "Ingest community threads"
2. "Score the community clusters"
3. "Generate the community digest"
```

Review the digest output:
- **Top 10 clusters** — highest composite scores with week-over-week deltas
- **Outlier overrides** — clusters surfacing by raw frequency despite low lane weight
- **Content candidates** — high-view unsolved clusters for Gotcha Journal / SEO
- **Uncategorized %** — if this exceeds 20%, taxonomy needs expansion

If a cluster warrants pursuit:

```
4. "Promote cluster grc_evidence_collection from digest 2026-07-01"
```

This creates an Opportunity in the procurement pipeline with full evidence chain back to individual community thread URLs.

### Weekly Intelligence Briefing

```
> /vigil-intelligence-briefing
```

Paste raw signals, SAM.gov results, news articles, or meeting notes. Claude produces a structured .docx briefing with signal inventory, confidence scoring, analysis, and recommended actions.

### Monthly Competitive Check

```
> "What contracts has Thirdera won in the last 90 days?"
> "Search for Accenture Federal ServiceNow awards"
> /vigil-competitive-tracker [paste competitor news]
```

---

## Skills Reference

Skills are invoked with slash commands. They produce structured output following Vectis Labs conventions.

| Skill | Trigger | Output |
|-------|---------|--------|
| `/vigil-opportunity-scorer` | "Score this opportunity" | Qualification card with dimension scores, go/no-go, next steps |
| `/vigil-intelligence-briefing` | "Write a briefing on these signals" | .docx intelligence briefing with provenance |
| `/vigil-capability-statement` | "Write a cap statement for this RFI" | .docx capability statement tailored to opportunity |
| `/vigil-competitive-tracker` | "Analyze this competitor" | Competitor profile, gap analysis, positioning |
| `/vigil-store-crossref` | "Does this signal support any planned apps?" | Store app roadmap cross-reference and priority ranking |
| `/vigil-signal-dashboard` | "Build a dashboard for these signals" | React artifact dashboard with Vectis design system |

---

## Community Scanner Deep Dive

### How Scoring Works

Each cluster gets a monthly composite score:

```
composite = lane_weight × Σ(weight × factor)
```

| Factor | Weight | What it measures |
|--------|--------|------------------|
| Thread count (normalized) | 30% | Cluster volume vs. busiest cluster |
| Unsolved rate | 20% | 1 - (accepted solutions / total) |
| Workaround rate | 20% | Threads with large code blocks (DIY fixes) |
| Commercial rate | 15% | Threads mentioning consultants, licensing costs |
| Store gap score | 15% | How under-served this area is on the Store (NULL → 0.5) |

Lane weights amplify scoring for strategic lanes:

| Lane | Weight | Rationale |
|------|--------|-----------|
| GRC | 1.3 | $500-2000/mo apps, near-zero Store competition |
| SecOps | 1.0 | Planned knowledge pack, moderate competition |
| Platform Utility | 1.0 | $200-1000/mo apps, broad demand |
| HRSD | 0.9 | Less founder track record |
| ITSM | 0.7 | Saturated Store category |
| Other | 0.6 | Catch-all |

### Outlier Override

The top 3 clusters by raw `thread_count × unsolved_rate` always surface in the digest, even if lane weighting pushes them down. This prevents the lane weight system from suppressing high-frequency pain that happens to fall in a low-weight lane.

### Cluster Promotion

When you promote a cluster, Vigil creates:

```
N community threads  →  N × Source + Signal (COMMUNITY_DEMAND)
Pattern claim        →  1 × Correlation (RECURRING_DEMAND)
Pursuit decision     →  1 × Opportunity (created_by='human')
Audit trail          →  1 × cluster_promotions row
```

Every Signal links to a verifiable thread URL. The Correlation holds the aggregate stats as a hypothesis (e.g., "34 threads, 71% unsolved"). Running `trace_evidence` on the resulting Opportunity walks the full chain back to individual thread URLs.

### Content Candidates

Clusters flagged for Gotcha Journal / SEO content are lane-agnostic — SEO value doesn't care about portfolio fit. The criteria:

- Thread view count ≥ 1,000 (configurable in taxonomy.yaml)
- Unsolved rate > 50%

---

## Watchlist Configuration

Edit `config/watchlists.json` to control what procurement scans look for:

```json
{
  "naics_codes": {
    "primary": ["541512", "541511"],
    "secondary": ["541519", "518210"]
  },
  "keywords": {
    "servicenow": ["ServiceNow", "SNOW platform"],
    "grc": ["GRC", "governance risk compliance"]
  },
  "competitors": {
    "large_primes": ["Deloitte Consulting", "Booz Allen Hamilton"],
    "servicenow_partners": ["Thirdera", "Cask"]
  },
  "agencies_of_interest": [
    "Department of the Treasury",
    "Department of Homeland Security"
  ]
}
```

After editing, run `reload_watchlist` or restart the server.

---

## Taxonomy Configuration

Edit `src/vectis_intel/community/taxonomy.yaml` to control community classification:

- **Add a cluster:** Add an entry under `clusters:` with `slug`, `label`, `lane`, and `keywords`
- **Adjust lane weights:** Edit values under `lanes:`
- **Change scoring:** Edit `config.scoring_weights`
- **Tune outlier detection:** Edit `config.outlier_override.top_n`
- **Tune content candidates:** Edit `config.content_candidate.min_views`

After editing, run `sync_taxonomy` to push changes to the database, then `community_score` to recalculate.

---

## Evidence Chain

Vigil's core guarantee: every signal is traceable to a verifiable URL. The provenance chain:

```
Opportunity
  └─ Correlation(s)  ← hypothesis, bounded by weakest signal
       └─ Signal(s)  ← atomic fact with confidence level
            └─ Source(s)  ← URL to original document
```

To trace any signal or opportunity:

```
> Trace the evidence for opportunity [ID]
```

Returns the full chain. If any URL in the chain is dead, the integrity audit flags it.

---

## Integrity Rules

The integrity engine enforces these automatically:

| Rule | What happens |
|------|--------------|
| No orphan signals | Every signal must link to ≥1 source. Creation blocked otherwise. |
| Human-only opportunities | `created_by` must be `"human"`. AI cannot create opportunities. |
| Strength bounded by evidence | Correlation strength ≤ weakest underlying signal confidence |
| Stale signal cascade | Past-deadline signals automatically weaken their correlations |
| Trust scoring | Per-agent verification success rate tracked over time |

Run `integrity_audit` periodically to check system health.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `SAM_GOV_API_KEY not configured` | Set the environment variable before starting the server |
| `No module named 'mcp'` | Run `pip install -e ".[dev]"` to install dependencies |
| Scan returns 0 results | Check keyword spelling in watchlist, try wider date range |
| Community ingest returns all errors | Check API credentials (Reddit), verify RSS feeds (SN Community) |
| Uncategorized % above 20% | Taxonomy needs new clusters — review uncategorized sample titles in digest |
| Integrity audit shows orphan signals | Database may have partial writes — investigate the flagged signal IDs |
| Promotion blocked: "Active promotion already exists" | The cluster's opportunity must reach terminal status (won/lost/abandoned) before re-promoting |

---

## Architecture Reference

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system architecture, schema diagrams, data flow patterns, and design principles.

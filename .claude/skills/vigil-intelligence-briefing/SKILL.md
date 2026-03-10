---
name: vigil-intelligence-briefing
description: >
  Generate structured intelligence briefings from raw market signals, procurement data, contract awards,
  news, or strategic observations. Use this skill whenever the user provides raw intelligence data and
  wants it synthesized into a Vectis Labs briefing document — including when they paste SAM.gov results,
  USAspending data, news articles, meeting notes, or any collection of market signals. Also trigger when
  the user asks to "write a briefing," "analyze this intel," "what does this mean for Vectis," or
  "summarize these signals." The output is a .docx intelligence briefing following Vectis Labs' established
  format with provenance tracking, confidence scoring, and strategic implications.
---

# Vigil Intelligence Briefing Generator

Produces structured intelligence briefings from raw signals — procurement data, contract awards, market
shifts, competitive observations, or any combination. Every claim traces to a source signal. No narrative
without underlying evidence.

## When to Use

- User pastes raw procurement data (SAM.gov, USAspending.gov, GovWin, etc.)
- User shares news articles, meeting notes, or observations about the federal/ServiceNow market
- User asks to analyze market signals or "write a briefing"
- User references Vigil data or asks "what does this mean for Vectis/NowForge"
- User wants to document strategic observations for future reference

## Briefing Structure

ALWAYS use this exact structure. Sections may be omitted if not applicable to the signal set,
but the ordering and formatting must be preserved.

```
BRIEFING HEADER
  - Title (descriptive, not generic)
  - Date
  - Source(s) with specificity (API endpoint, meeting recording timestamp, article URL, etc.)
  - Classification: Internal Briefing — Not for external distribution
  - Prepared By: Vectis Labs Intelligence
  - Audience: Vectis Leadership & [relevant practice area]

EXECUTIVE SUMMARY
  2-3 paragraphs. Lead with the single most important finding.
  State the bottom line up front — what this means for Vectis in one sentence.

SIGNAL INVENTORY
  Numbered list of discrete signals extracted from the raw data.
  Each signal is an atomic factual statement — not a narrative.
  Format per signal:
    [S-001] {factual statement} — Source: {specific source} | Confidence: {high|medium|low}

ANALYSIS
  Organized by theme, not by signal order.
  Every analytical claim must reference one or more signal IDs in brackets.
  Use subsections with descriptive headings.
  Include a "What We Don't Know" subsection for gaps and unknowns.

STRATEGIC IMPLICATIONS FOR VECTIS
  Explicit connections to:
    - NowForge product roadmap (if relevant)
    - Store app portfolio (if relevant)
    - Consulting pipeline (if relevant)
    - Platform Decoupling hedge (if relevant)
    - Vigil monitoring priorities (what to watch next)

RECOMMENDED ACTIONS
  Numbered, concrete, time-bound where possible.
  Each action tagged with priority: [IMMEDIATE] [NEAR-TERM] [MONITOR]

KEY TAKEAWAYS
  Numbered summary table (same format as Treasury OCIO briefing).
  5-8 items maximum. Each is a standalone assertion.
```

## Provenance Rules

These are non-negotiable. They reflect Vectis Labs' anti-hallucination architecture:

1. **No orphan claims.** Every analytical statement must reference at least one signal ID.
   If you cannot trace a claim to a signal, do not include it.

2. **Atomic signals only.** Each signal in the inventory is a single factual observation,
   not a conclusion or narrative. "Treasury awarded a $420M Salesforce BPA to Lancer
   Information Solutions in March 2025" is a signal. "Treasury is moving away from
   ServiceNow" is an analytical claim that must reference signals.

3. **Confidence is explicit.** Every signal gets a confidence tag:
   - **high** — directly observed or from authoritative primary source (API data, official
     announcements, direct observation)
   - **medium** — from credible secondary source or reasonable inference from primary data
   - **low** — single-source unverified, rumor, or inference chain with 2+ steps

4. **Source specificity.** "SAM.gov" is not specific enough. Use "SAM.gov opportunity
   W52P1J-26-R-0042, posted 2026-03-01" or "USAspending.gov award PIID GS-35F-0119Y,
   obligated 2026-02-15."

5. **Correlation strength bounded by weakest signal.** If an analytical claim connects
   two signals, the confidence of the claim cannot exceed the lower of the two signal
   confidence levels.

## Confidence Taxonomy

When scoring signals and claims, apply these definitions consistently:

| Level | Definition | Example |
|-------|-----------|---------|
| **High** | Primary source, directly verifiable, authoritative | Contract award in USAspending, official press release, direct observation |
| **Medium** | Credible secondary source, single-step inference from high-confidence data | Industry publication report, LinkedIn announcement by named individual, pattern from 2+ high signals |
| **Low** | Unverified single source, multi-step inference, or temporal extrapolation | Forum post, rumor, "if X continues then Y" projections |

## Output Format

Generate the briefing as a .docx file using the docx skill. Read `/mnt/skills/public/docx/SKILL.md`
before generating the document.

Apply these formatting conventions:
- Header table with metadata (Date, Source, Classification, Prepared By, Audience)
- Section headings as Heading 1
- Signal inventory as a numbered list with bold signal IDs
- Key takeaways as a numbered table (number | takeaway text)
- Professional tone — measured, precise, no hype
- Use the Vectis Labs logo at `/mnt/user-data/uploads/vectis-logo.png` if available

## Handling Incomplete Data

Raw signals are often messy or incomplete. Handle gracefully:

- If the user provides unstructured text (meeting notes, article paste), extract discrete
  signals first, present them for confirmation, then build the briefing.
- If signal count is low (< 3), note in the executive summary that the briefing is based
  on limited signals and analytical confidence is constrained accordingly.
- If signals conflict, present both and note the conflict explicitly in the Analysis section.
  Do not silently resolve contradictions.

## Cross-Reference Awareness

When analyzing signals, check for relevance to these Vectis strategic contexts:

- **Activation triggers for Platform Decoupling (Service Line #5):**
  Federal AI workforce replacement programs, ServiceNow license cancellations,
  platform migration RFIs, commercial ServiceNow consolidation signals

- **Store app portfolio opportunities:**
  GRC pain points, audit management gaps, compliance tooling needs that map to
  the target app list (Audit Readiness Dashboard, Evidence Collection Tracker,
  Control Inheritance Manager, etc.)

- **Competitive positioning:**
  Now Assist announcements, Build Agent updates, competing MCP server activity,
  partner ecosystem shifts

- **Federal market timing:**
  Agency AI adoption pace, contractor reduction announcements, DOGE-related
  directives, procurement vehicle changes

## Example Signal Extraction

**Raw input (user pastes):**
"Just saw on SAM.gov — Treasury posted an RFI for ServiceNow GRC module assessment
services, response due April 15. Looks like they want someone to evaluate their
current GRC implementation. Also noticed that the existing ServiceNow BPA with
Accenture Federal wasn't renewed last month according to USAspending."

**Extracted signals:**
```
[S-001] Treasury posted RFI on SAM.gov for ServiceNow GRC module assessment services,
        response deadline April 15, 2026.
        Source: SAM.gov (solicitation number pending) | Confidence: high

[S-002] Treasury's existing ServiceNow BPA with Accenture Federal was not renewed.
        Source: USAspending.gov (contract ID pending verification) | Confidence: medium
        Note: "last month" is imprecise — verify exact expiration date.
```

**Why S-002 is medium, not high:** The user said "according to USAspending" but the
specific contract ID and date haven't been verified. Once the PIID and period of
performance are confirmed, this upgrades to high.

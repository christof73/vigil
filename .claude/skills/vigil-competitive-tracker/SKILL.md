---
name: vigil-competitive-tracker
description: >
  Track, analyze, and document competitive intelligence for the ServiceNow ecosystem and federal
  consulting market. Use this skill when the user asks about competitors, wants to analyze a competitor's
  positioning, needs to update competitive intelligence, asks "what is [company] doing," wants to compare
  Vectis against competitors, or provides competitive signals (job postings, contract wins, product
  announcements, partner updates). Also trigger for ServiceNow ecosystem changes like Now Assist updates,
  Build Agent announcements, partner program changes, or platform roadmap shifts.
---

# Vigil Competitive Tracker

Maintains structured competitive intelligence on the ServiceNow ecosystem and federal GRC market.
Produces competitor profiles, capability gap analyses, and positioning recommendations.

## When to Use

- User shares information about a competitor (win, hire, announcement, product launch)
- User asks to analyze a specific company's positioning
- User asks "who competes with us" or "what's the competitive landscape"
- User provides ServiceNow ecosystem news (Now Assist, Build Agent, partner program)
- User wants to update or review the competitive intelligence baseline

## Competitor Categories

### Category 1: Direct Tool Competitors (NowForge space)
Companies building AI-powered ServiceNow development tools.

| Competitor | Type | Threat Level |
|-----------|------|-------------|
| ServiceNow Now Assist for Code | In-platform AI copilot | Medium — script-only, tied to premium licensing |
| ServiceNow Build Agent | AI app builder | Medium — targets beginners, not professional consultancies |
| echelon-ai-labs MCP | Open-source MCP server | Low — data operations only, no app dev |
| michaelbuckner MCP | Open-source MCP server | Low — search/update only, no schema tools |
| CData MCP Server | Commercial data connector | Low — analytics only, no dev operations |

### Category 2: Federal ServiceNow Consultancies (Consulting market)
Firms competing for the same federal ServiceNow engagements.

Track: contract wins, hiring patterns, capability statements, partner tier status,
set-aside certifications, key personnel moves.

### Category 3: ServiceNow Store Publishers (Store app market)
Companies publishing competing or adjacent apps on the ServiceNow Store.

Track: new app listings, pricing changes, review/rating trends, GRC-specific apps.

### Category 4: Platform Alternatives (Long-term hedge)
Technologies that could displace ServiceNow in federal mid-complexity use cases.

Track: AI-generated bespoke apps (Treasury model), low-code platforms, alternative
GRC solutions.

## Competitor Profile Structure

When creating or updating a competitor profile, use this format:

```
COMPETITOR PROFILE: {Company Name}
Updated: {date}
Source signals: {list signal IDs from briefings}

OVERVIEW
  Type:           {consultancy | tool vendor | store publisher | platform}
  Size:           {employee count / revenue estimate}
  SN Partnership: {tier — Registered/Specialist/Premier/Elite}
  Set-Asides:     {SDVOSB, 8(a), HUBZone, etc.}
  Key Verticals:  {federal agencies / commercial sectors}

CAPABILITIES
  ServiceNow Modules: {ITSM, GRC, HRSD, CSM, etc.}
  Certifications:     {CSA, CAD, CIS, etc. — team aggregate}
  AI/Automation:      {any AI-augmented delivery capabilities}
  Differentiators:    {what they claim sets them apart}

RECENT ACTIVITY
  {Chronological list of observed signals — contract wins, hires, announcements}
  Each entry: date | signal | source | confidence

STRENGTHS (vs. Vectis)
  {What they do better or have that Vectis doesn't}

WEAKNESSES (vs. Vectis)
  {Where Vectis has structural advantages}

POSITIONING IMPLICATIONS
  {How this competitor's existence/activity should influence Vectis strategy}
```

## Analysis Frameworks

### Capability Gap Matrix
When comparing Vectis against multiple competitors, produce a matrix:

```
Capability              Vectis    Comp A    Comp B    Comp C
─────────────────────── ───────── ───────── ───────── ─────────
GRC depth               ●●●●●     ●●●○○     ●●○○○     ●●●●○
AI-augmented delivery   ●●●●●     ●○○○○     ○○○○○     ●●○○○
Store app portfolio     ●○○○○     ○○○○○     ●●●○○     ○○○○○
Federal past perf.      ●○○○○     ●●●●○     ●●●●●     ●●●○○
Set-aside certs         ○○○○○     ●●●○○     ●●●●●     ●●○○○
Dev tool productivity   ●●●●●     ●●○○○     ○○○○○     ●○○○○
```

Use ● for capability present, ○ for absent. 5-point scale.

### Win/Loss Analysis
When a signal indicates a competitor won a contract Vectis could have pursued:

1. What was the opportunity? (solicitation, agency, scope)
2. Why did they likely win? (vehicle access, past performance, pricing, set-aside)
3. What would Vectis have needed to be competitive?
4. Is this a pattern or a one-off?
5. Does this change Vectis strategy or priorities?

## ServiceNow Ecosystem Monitoring

For platform-level changes, analyze through three lenses:

1. **Does this help or hurt NowForge's positioning?**
   Example: Build Agent expansion into enterprise features = increased threat level.
   Example: Now Assist requiring Enterprise Plus = reduced threat (pricing barrier).

2. **Does this create a Store app opportunity?**
   Example: New platform feature with poor OOB reporting = dashboard app opportunity.

3. **Does this shift the federal market dynamics?**
   Example: ServiceNow AI features requiring internet egress = federal adoption friction.

## Signal Integration

Competitive signals should be tagged for cross-reference with other Vigil skills:
- Tag with `[COMP-{competitor_id}]` for competitor-specific signals
- Tag with `[ECOSYSTEM]` for platform-level changes
- Tag with `[STORE-OPP]` if the signal implies a Store app opportunity
- Tag with `[DECOUPLE-TRIGGER]` if the signal is a Platform Decoupling activation indicator

## Output Formats

- **Single competitor analysis:** Full profile document (use docx skill for formal output)
- **Competitive landscape update:** Summary table with recent changes highlighted
- **Ecosystem alert:** Short-form briefing on a specific platform change and implications
- **Quarterly competitive review:** Comprehensive landscape document with trend analysis

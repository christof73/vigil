---
name: vigil-store-crossref
description: >
  Cross-reference market signals, procurement data, and competitive intelligence against the Vectis Labs
  ServiceNow Store app roadmap. Use this skill whenever the user wants to check if market signals
  validate planned Store apps, identify new app opportunities from procurement data, prioritize the
  Store app backlog based on market evidence, or asks "does this signal support any of our planned
  apps," "what app should we build next," "is there market demand for [app concept]," or "cross-reference
  this against our roadmap." Also trigger when analyzing federal pain points that could map to a Store
  app opportunity.
---

# Vigil Store App Roadmap Cross-Reference

Maps market signals to the Vectis Labs Store app portfolio, validates planned apps against
real demand signals, identifies new opportunities, and prioritizes the build backlog.

## When to Use

- User provides procurement signals and wants to check roadmap alignment
- User asks which Store app to build next
- User wants to validate market demand for a planned app
- User identifies a federal pain point and wonders if it's a Store app opportunity
- User wants to reprioritize the Store app backlog based on recent intelligence

## Current Store App Roadmap

Read `references/store-app-roadmap.md` for the full roadmap with descriptions,
revenue projections, and build status.

## Cross-Reference Process

### Step 1: Signal Classification

For each signal, determine its Store app relevance:

| Signal Type | What to Look For |
|-------------|-----------------|
| Procurement (RFI/RFP) | Requirements that describe problems a Store app solves |
| Contract awards | Spending on services a Store app could replace or complement |
| Competitor activity | Competing apps or capabilities that validate the market |
| Platform changes | New ServiceNow features that enable or obsolete planned apps |
| User complaints | Community posts, forum threads, support cases describing pain points |
| Agency directives | Policy changes that create new compliance or operational needs |

### Step 2: Mapping

Map each relevant signal to one or more planned apps:

```
SIGNAL → APP MAPPING

[S-001] Treasury RFI for GRC assessment services
  → Audit Readiness Dashboard (validates demand for GRC reporting)
  → GRC Migration Utility (if RFI mentions cross-instance migration)

[S-002] DHS posts requirement for clone management automation
  → Clone Data Protector (direct hit — exact use case)

[S-003] ServiceNow Community thread: 47 upvotes on "ACL audit tool needed"
  → Deployment Validation Suite (ACL validation is a feature)
  → NEW OPPORTUNITY: Standalone ACL Audit App?
```

### Step 3: Demand Scoring

For each planned app, maintain a cumulative demand score:

| Evidence Type | Points |
|--------------|--------|
| Direct procurement requirement (RFI/RFP mentioning the capability) | +5 |
| Contract award for services the app would replace | +4 |
| Competitor publishing a similar app on the Store | +3 |
| Community thread with 20+ upvotes on the pain point | +3 |
| Agency directive creating new need | +4 |
| Customer interview / direct feedback mentioning the need | +5 |
| Indirect inference from related procurement | +1 |
| ServiceNow OOB improvement reducing the need | -3 |

### Step 4: Priority Recommendation

Output a ranked recommendation:

```
STORE APP PRIORITY RANKING (Updated: {date})
Based on {N} market signals from {date range}

RANK  APP                           DEMAND   BUILD     REVENUE    PRIORITY
                                    SCORE    EFFORT    EST.       SCORE
─────────────────────────────────────────────────────────────────────────
  1   Audit Readiness Dashboard      23      Medium    $1,500/mo   A
  2   Clone Data Protector           18      Low       $1,000/mo   A
  3   Deployment Validation Suite    15      Medium    $1,500/mo   B+
  4   GRC Migration Utility          12      High      $2,000/mo   B
  ...

PRIORITY SCORE KEY:
  A  = Build now — strong demand evidence, favorable effort/revenue ratio
  B+ = Build next — good evidence, queue after current build
  B  = Planned — evidence supports the concept, build when capacity allows
  C  = Defer — limited demand evidence, revisit in 90 days
  X  = Reconsider — evidence suggests reduced demand or OOB competition
```

## New Opportunity Detection

When signals describe pain points that don't map to any planned app, flag as a potential
new opportunity:

```
NEW OPPORTUNITY DETECTED

Signal(s): [S-003], [S-007]
Pain Point: Federal agencies need automated ACL auditing across scoped apps
Existing Planned App: None (Deployment Validation Suite covers ACLs partially)
Market Evidence: 47 upvotes on SN Community, 2 RFIs mentioning access control audits
Estimated Revenue: $300-$800/mo
Build Effort: Low (NowForge ACL tools + record_query already exist)
Recommendation: Add to roadmap as candidate, validate with 1-2 more signals
```

## Output Formats

### Quick Cross-Reference (conversational)
When the user provides 1-3 signals and wants a quick check — respond inline with
the mapping and any priority changes.

### Full Roadmap Review (document)
When the user asks for a comprehensive priority update — produce a formatted report
with the full ranked table, signal mappings, and new opportunity flags. Use docx skill
for formal output.

### Dashboard Data (for vigil-signal-dashboard)
When the user wants to visualize the cross-reference — output structured JSON that
the signal dashboard skill can consume for the Store App Opportunity Map view.

## Integration with Other Vigil Skills

- **Intelligence Briefing:** When a briefing identifies Store-relevant signals, tag them
  with `[STORE:{app-id}]` for automated cross-reference.
- **Opportunity Scorer:** When scoring an opportunity, check if the requirement maps to a
  planned Store app — this increases Strategic Value score.
- **Competitive Tracker:** When a competitor publishes a Store app, update the demand score
  for the equivalent planned Vectis app (+3 validation points, but note competitive urgency).

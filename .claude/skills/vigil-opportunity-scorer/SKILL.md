---
name: vigil-opportunity-scorer
description: >
  Score and qualify procurement opportunities, contract awards, or market signals against Vectis Labs
  fit criteria. Use this skill whenever the user shares a SAM.gov opportunity, RFI/RFP, contract award,
  or any procurement signal and wants to know if Vectis should pursue it. Also trigger when the user asks
  "should we bid on this," "is this a fit," "score this opportunity," "qualify this lead," or provides
  a NAICS code, solicitation number, or federal procurement data. Outputs a structured qualification
  card with go/no-go recommendation and reasoning.
---

# Vigil Opportunity Scorer

Scores procurement opportunities against Vectis Labs' strategic fit criteria. This skill encodes the
Qualifier agent's logic for manual use during Vigil's operational shakedown period.

## When to Use

- User pastes a SAM.gov opportunity or RFI/RFP text
- User shares USAspending contract award data
- User asks whether Vectis should pursue a specific opportunity
- User wants to compare multiple opportunities by fit
- User provides procurement signals and wants qualification analysis

## Scoring Dimensions

Score each dimension 0–10. The composite score is a weighted average.

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| **ServiceNow Alignment** | 25% | Does this involve ServiceNow platform work? GRC/ITSM/HRSD? |
| **GRC/Compliance Adjacency** | 20% | Does it touch audit, risk, compliance, FISMA, NIST, FedRAMP? |
| **Delivery Model Fit** | 15% | Can Vectis deliver this as outcome-based (not staff aug)? Solo or sub? |
| **Contract Vehicle Access** | 15% | Is the vehicle accessible? Set-aside status? Sub-contracting path? |
| **NowForge Leverage** | 10% | Can NowForge accelerate delivery for a structural cost advantage? |
| **Revenue Potential** | 10% | What's the realistic revenue to Vectis? Duration? |
| **Strategic Value** | 5% | Past performance, portfolio building, reference account potential? |

## Scoring Rubric Detail

Read `references/scoring-rubric.md` for the full rubric with per-dimension scoring criteria
and examples at each level (0-3 low, 4-6 medium, 7-10 high).

## Qualification Thresholds

| Composite Score | Recommendation | Action |
|----------------|----------------|--------|
| **8.0 – 10.0** | **PURSUE** — Strong fit, allocate preparation time | Draft capability statement, identify teaming partners |
| **6.0 – 7.9** | **EVALUATE** — Good fit with caveats, needs deeper look | Identify blockers, assess teaming options, set decision deadline |
| **4.0 – 5.9** | **MONITOR** — Marginal fit, track for changes | Add to Vigil watchlist, revisit if scope or vehicle changes |
| **0.0 – 3.9** | **PASS** — Not a fit for current Vectis capabilities | Log reason, check for adjacent signals |

## Output Format: Qualification Card

Generate this structure for every scored opportunity:

```
═══════════════════════════════════════════════════
  OPPORTUNITY QUALIFICATION CARD
  Vectis Labs · Vigil Intelligence
═══════════════════════════════════════════════════

  SOLICITATION:    {number or "N/A — signal only"}
  TITLE:           {opportunity title}
  AGENCY:          {agency / bureau}
  POSTED:          {date}
  RESPONSE DUE:    {date or "N/A"}
  NAICS:           {code(s)}
  SET-ASIDE:       {type or "Full & Open"}
  EST. VALUE:      {dollar range}

  ─────────────────────────────────────────────────
  COMPOSITE SCORE:  {X.X} / 10.0  →  {PURSUE|EVALUATE|MONITOR|PASS}
  ─────────────────────────────────────────────────

  DIMENSION SCORES:
    ServiceNow Alignment ........... {X}/10  ({rationale})
    GRC/Compliance Adjacency ....... {X}/10  ({rationale})
    Delivery Model Fit ............. {X}/10  ({rationale})
    Contract Vehicle Access ........ {X}/10  ({rationale})
    NowForge Leverage .............. {X}/10  ({rationale})
    Revenue Potential .............. {X}/10  ({rationale})
    Strategic Value ................ {X}/10  ({rationale})

  ─────────────────────────────────────────────────
  KEY FACTORS:
    (+) {top positive factor}
    (+) {second positive factor}
    (−) {top risk/blocker}
    (−) {second risk/blocker}

  ─────────────────────────────────────────────────
  RECOMMENDED NEXT STEPS:
    1. {specific action}
    2. {specific action}
    3. {specific action}

  ─────────────────────────────────────────────────
  STORE APP RELEVANCE:
    {If the opportunity reveals a ServiceNow gap that maps to a
     target Store app, note it here. Otherwise "None identified."}

  VIGIL MONITORING:
    {What related signals should Vigil track going forward?}
```

## Handling Partial Information

Federal procurement data is often incomplete. Score what you can and flag gaps:

- Missing NAICS → note it, estimate based on description
- No dollar value → score Revenue Potential as "insufficient data" (score 3, flag for research)
- Ambiguous scope → score ServiceNow Alignment conservatively, note the ambiguity
- Unknown vehicle → score Contract Vehicle Access at 2 unless user provides vehicle info

Always state what information would change the score if obtained.

## Batch Scoring

When the user provides multiple opportunities, score each independently, then present a
ranked summary table:

```
RANK  SCORE  RECOMMENDATION  SOLICITATION         TITLE
  1    8.2   PURSUE          W52P1J-26-R-0042     Treasury GRC Assessment
  2    6.5   EVALUATE        75FCMC-26-R-0108     DHS ServiceNow Migration
  3    4.1   MONITOR         GS-35F-26-R-0331     GSA ITSM Support
```

## Set-Aside Awareness

Vectis Labs is a small business LLC. Score set-aside compatibility:

| Set-Aside Type | Vectis Eligibility | Score Modifier |
|---------------|-------------------|----------------|
| Small Business | Eligible | +1 to Vehicle Access |
| SDVOSB | Not eligible (currently) | -2 to Vehicle Access |
| 8(a) | Not eligible | -3 to Vehicle Access |
| HUBZone | Not eligible (currently) | -2 to Vehicle Access |
| WOSB | Not eligible | -3 to Vehicle Access |
| Full & Open | Eligible (likely as sub) | 0 |

When a set-aside doesn't match, always check: "Is there a teaming/subcontracting path?"
If yes, reduce the penalty by 1.

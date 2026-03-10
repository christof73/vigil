---
name: vigil-signal-dashboard
description: >
  Build React artifact visualizations of Vigil market intelligence data. Use this skill whenever the
  user wants to visualize procurement signals, opportunity pipelines, scoring distributions, competitive
  landscapes, signal timelines, or any Vigil data as an interactive dashboard. Also trigger when the
  user says "visualize these signals," "show me a dashboard," "chart this data," "build a pipeline view,"
  or wants any visual representation of market intelligence data. Outputs follow Vectis Labs' dark
  monospace design language.
---

# Vigil Signal Dashboard Builder

Creates interactive React artifact dashboards for Vigil market intelligence data. All dashboards follow
the established Vectis/Vigil design system — dark background, monospace typography, teal/violet/amber
accent palette.

## When to Use

- User wants to visualize Vigil signal data (procurement, competitive, tech radar)
- User asks for a pipeline view of scored opportunities
- User wants timeline visualization of signals or market events
- User wants competitive landscape or positioning charts
- User requests any dashboard or chart from market intelligence data

## Design System

Read `/mnt/skills/public/frontend-design/SKILL.md` before building any dashboard.

Then apply these Vigil-specific design constraints:

### Color Palette

```
Background:     #0a0a0f (primary), #0c0c14 (cards), #0c0c18 (panels)
Border:         #1e293b (default), #27273a (subtle)
Text:           #e2e8f0 (primary), #94a3b8 (secondary), #64748b (muted), #475569 (dim)

Accent Colors (functional):
  Blue:         #3b82f6  — Collection layer, procurement signals
  Violet:       #8b5cf6  — Technology signals, orchestration
  Cyan:         #06b6d4  — Competitive intelligence
  Amber:        #f59e0b  — Qualification, warnings, human gates
  Emerald:      #10b981  — Activation, success, positive signals
  Pink:         #ec4899  — Content, marketing, strategic
  Indigo:       #818cf8  — Shared state, infrastructure

Score Colors:
  PURSUE:       #10b981 (emerald)
  EVALUATE:     #f59e0b (amber)
  MONITOR:      #06b6d4 (cyan)
  PASS:         #64748b (muted)

Confidence Colors:
  High:         #10b981
  Medium:       #f59e0b
  Low:          #ef4444
```

### Typography

```
Font family:    'JetBrains Mono', 'SF Mono', 'Fira Code', monospace
Section labels: 9px, uppercase, letter-spacing: 1px, color: #475569
Card titles:    12-13px, font-weight: 600, color: #e2e8f0
Body text:      11px, color: #94a3b8
Badges/tags:    9-10px, uppercase, letter-spacing: 0.3-0.5px
```

### Component Patterns

```
Cards:          background: #0c0c14, border: 1px solid #1e293b, border-radius: 10px
Active cards:   border color matches accent, background adds accent at 12% opacity
Accent bars:    2px top border on selected/active cards
Status badges:  Pill shape, accent color at 18% opacity background, accent border at 28%
Grid pattern:   Fixed background, opacity 0.03, 32px grid, accent color lines
Hover states:   Border color transition, no background change
```

### Layout Principles

- Always responsive (use the useIsMobile hook pattern)
- Mobile breakpoint at 640px
- Desktop: side-by-side panels with sticky detail sidebars
- Mobile: stacked with collapsible sections and bottom-sheet detail panels
- Minimum touch target: 44px on mobile

## Dashboard Types

### 1. Pipeline View
Shows scored opportunities in a kanban-style layout grouped by recommendation (PURSUE → EVALUATE → MONITOR → PASS). Each card shows solicitation, agency, score, and key factors.

### 2. Signal Timeline
Chronological view of signals with confidence color-coding. Filterable by source (SAM.gov, USAspending, manual observation). Supports date range selection.

### 3. Scoring Distribution
Histogram or dot plot of opportunity scores across dimensions. Helps identify which dimensions are consistently low (capability gaps) or high (sweet spots).

### 4. Competitive Landscape
Positioning map or comparison matrix showing Vectis vs. competitors across capability dimensions. Uses the competitive intel agent's data.

### 5. Activation Monitor
Tracks Platform Decoupling activation triggers. Progress bars or threshold indicators for each trigger type with current signal count vs. activation threshold.

### 6. Store App Opportunity Map
Cross-references procurement signals against the target Store app portfolio. Shows which signals map to which app concepts and where new app opportunities emerge.

## Data Input Handling

Dashboards accept data in these formats:
- Raw JSON (from Vigil SQLite exports)
- Structured signal lists (from intelligence briefings)
- Qualification cards (from opportunity scorer)
- User-provided tables or lists

When the user provides raw data, parse it into the dashboard's expected structure. When data
is ambiguous, embed sensible defaults and note assumptions in the dashboard's info panel.

## Interactivity Requirements

Every dashboard must include:
- Click-to-inspect on data points (detail panel or tooltip)
- At least one filter dimension
- Responsive layout (desktop sidebar + mobile bottom sheet pattern)
- Loading states for any async data
- Empty states with helpful messaging

## React Technical Constraints

- Single-file .jsx artifact (no separate CSS/JS)
- Tailwind utility classes only (no compiler — use pre-defined classes)
- Available libraries: React, recharts, d3, lodash, lucide-react
- No localStorage/sessionStorage — use React state only
- Default export required, no required props

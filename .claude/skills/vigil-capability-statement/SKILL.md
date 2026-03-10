---
name: vigil-capability-statement
description: >
  Generate targeted capability statements for Vectis Labs tailored to specific opportunities, agencies,
  or market segments. Use this skill when the user asks to "create a capability statement," "write a
  cap statement," "prepare a response to this RFI," or needs a one-pager for a specific prospect or
  opportunity. Also trigger when the user provides an opportunity (from the scorer or SAM.gov) and
  wants to prepare pursuit materials. Outputs a professional .docx or .pdf capability statement
  following federal contractor conventions.
---

# Vigil Capability Statement Generator

Produces targeted capability statements for Vectis Labs, customized to specific opportunities,
agencies, or verticals. Federal capability statements follow conventions that procurement officers
expect — deviation signals inexperience.

## When to Use

- User wants a capability statement for a specific opportunity
- User is preparing to respond to an RFI or Sources Sought notice
- User wants a general-purpose Vectis Labs capability statement
- User wants to customize the capability statement for a specific agency or vertical
- User provides an opportunity score card and wants pursuit materials

## Capability Statement Structure

Federal capability statements are typically one page (two pages maximum). They follow an
established format that GSA, DoD, and civilian agencies expect to see.

### Required Elements

```
HEADER
  - Vectis Labs logo (use /mnt/user-data/uploads/vectis-logo.png if available)
  - Company name: Vectis Labs LLC
  - Tagline: {customized to opportunity — see Tagline Guidance}
  - Contact: vectislabs.co | {email when established}

CORE COMPETENCIES (3-5 bullets)
  Tailored to the opportunity. Draw from the competency library below.
  Each bullet: bold capability name + 1-sentence description of what Vectis delivers.

DIFFERENTIATORS (3-4 bullets)
  What sets Vectis apart for THIS specific opportunity.
  Always include at least one quantified differentiator.

PAST PERFORMANCE / RELEVANT EXPERIENCE
  Project summaries relevant to the opportunity.
  Format: Client (anonymized if needed) | Scope | Outcome | Period
  If past performance is limited, use "Relevant Experience" header and
  describe the founder's 10+ years of directly applicable work.

COMPANY DATA
  - DUNS / UEI: {when obtained}
  - CAGE Code: {when obtained}
  - NAICS Codes: 541512 (Computer Systems Design), 541519 (Other Computer Related),
    541611 (Administrative Management Consulting), 541690 (Other Scientific/Technical Consulting)
  - Business Size: Small Business
  - Set-Asides: {applicable certifications}
  - State of Incorporation: Texas
  - Facility Clearance: {status}

CONTACT
  - Name, title, email, phone, website
```

## Tagline Guidance

The tagline sits directly under "Vectis Labs LLC" and should be customized:

| Context | Tagline |
|---------|---------|
| General purpose | ServiceNow Solutions & Compliance Architecture |
| GRC-focused opportunity | Federal GRC Implementation & Compliance Automation |
| ServiceNow migration | ServiceNow Platform Rationalization & Migration |
| AI/modernization RFI | AI-Augmented ServiceNow Delivery & Platform Intelligence |
| Data migration | Intelligent Data Migration & Schema Normalization for ServiceNow |

## Competency Library

Draw from these when building the Core Competencies section. Select 3-5 that best
match the target opportunity:

**ServiceNow Platform:**
- **ServiceNow GRC Implementation** — Policy & Compliance, Audit Management, Integrated Risk Management module deployment aligned with NIST 800-53 and FISMA frameworks
- **ServiceNow Custom Application Development** — Full-stack scoped application design and deployment including schema architecture, business logic, access controls, and Service Catalog integration
- **ServiceNow Platform Administration** — Instance configuration, upgrade planning, performance optimization, and cross-module integration
- **Next Experience Workspace Design** — Modern UI Builder workspace development with configurable layouts, data-driven components, and role-based experiences

**Compliance & GRC:**
- **Federal Compliance Architecture** — NIST 800-53, FISMA, FedRAMP, OMB A-50 compliance framework alignment for IT systems and workflow platforms
- **Audit Management & POA&M** — End-to-end audit lifecycle management from engagement tracking through finding remediation and corrective action plan execution
- **Continuous Monitoring** — Automated compliance monitoring, control testing, and evidence collection workflows

**Technical:**
- **AI-Augmented Platform Delivery** — Accelerated implementation timelines through proprietary automation tooling (3-5x development velocity on scaffold and configuration work)
- **Data Migration & Schema Normalization** — Intelligent migration from legacy systems and flat data sources into normalized ServiceNow schemas with automated transform map generation
- **Platform Rationalization** — Configuration intelligence assessments mapping existing ServiceNow implementations against framework-aligned best practices

## Differentiator Library

Select and customize 3-4:

- **GRC Domain Depth:** 10+ years of hands-on GRC implementation across federal agencies, not general ServiceNow consulting with GRC added as an afterthought
- **Delivery Speed:** Proprietary tooling enables 3-5x faster ServiceNow application delivery without sacrificing enterprise-grade quality or compliance alignment
- **Framework Alignment Focus:** Every implementation decision evaluated against the applicable compliance framework — NIST 800-53, FISMA, FedRAMP — not just "what the customer asked for"
- **Certified Expertise:** CSA and CAD certified with deep platform architecture knowledge, not staff augmentation
- **Outcome-Based Engagement:** Fixed-price deliverables, not hourly billing — aligned incentives for speed and quality
- **Small Business Agility:** Direct access to senior technical leadership on every engagement — no layers of project management between the decision-maker and the person doing the work

## Customization from Opportunity Data

When the user provides a scored opportunity (from vigil-opportunity-scorer), automatically:

1. Select competencies that match the high-scoring dimensions
2. Tailor differentiators to address the opportunity's specific requirements
3. Select the most relevant past performance examples
4. Choose NAICS codes that match the solicitation
5. Adjust the tagline to the opportunity's domain

## Output Format

Generate as a .docx file using the docx skill. Read `/mnt/skills/public/docx/SKILL.md`
before generating.

Design requirements:
- One page strongly preferred, two pages maximum
- Professional layout with clear visual hierarchy
- Vectis Labs logo top-left
- Teal (#00a896) and navy (#1e3a5f) accent colors matching brand
- Clean sans-serif typography
- Clearly separated sections with subtle rules or spacing
- Print-friendly (no dark backgrounds)

## Important Constraints

- **Never reveal NowForge by name** in capability statements. Reference "proprietary automation tooling"
  or "AI-augmented delivery capabilities" — the tool stays invisible.
- **Never overstate past performance.** If Vectis has limited direct federal contracting history,
  frame the founder's 10+ years of federal consulting experience accurately.
- **Always include NAICS codes.** Procurement officers filter by NAICS — missing codes means
  missing opportunities.
- **Match the opportunity's language.** If the solicitation says "ITSM modernization," the
  capability statement should use that exact phrase, not "service management transformation."

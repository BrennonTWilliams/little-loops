---
discovered_commit: b20aa691700cd09e7071bc829c943e3a83876abf
discovered_branch: main
discovered_date: 2026-01-06T20:47:28Z
deferred_date: 2026-01-06
deferred_reason: Simplifying initial product dimension scope
---

# FEAT-005: Product Issue Category (DEFERRED)

## Status

**Deferred** | Created: 2026-01-06 | Deferred: 2026-01-06

## Deferral Rationale

This feature has been deferred from the initial Product dimension implementation for the following reasons:

1. **Separation of Concerns**: Product analysis enriches existing issue types (BUG, FEAT, ENH) with business context rather than creating a parallel categorization system. This avoids confusion about when to use PROD vs FEAT with product context.

2. **Simpler Initial Scope**: The MVP product dimension focuses on:
   - Optional product impact fields in existing issue templates (ENH-005)
   - A dedicated `/ll:scan_product` command separate from technical scanning
   - Goal-aligned prioritization without a new issue category

3. **Workflow Clarity**: Users work with either technical workflows (`scan_codebase`, `manage_issue`) or product workflows (`scan_product`). Adding a PROD category would blur these boundaries.

4. **Future Consideration**: If usage patterns reveal a strong need for dedicated product issues that don't fit BUG/FEAT/ENH, this feature can be reconsidered.

## Original Summary

Add a new `PROD` (Product) issue category alongside the existing `BUG`, `FEAT`, and `ENH` categories. Product issues represent work driven primarily by business goals, user needs, or strategic priorities rather than technical considerations.

## Original Motivation

Current issue categories are technically-oriented:
- **BUG**: Something is broken
- **FEAT**: New technical capability
- **ENH**: Improve existing technical implementation

These don't capture issues that are:
- Driven by user research findings
- Required to meet a business objective
- Strategic priorities without technical origin
- Product-market fit improvements

## Alternative Approach (Implemented Instead)

Rather than a separate PROD category, the Product dimension:

1. **Enriches existing issues** with optional product impact fields (goal alignment, persona impact, business value) via ENH-005

2. **Creates FEAT/ENH issues** from `/ll:scan_product` with product context included, keeping them in standard directories

3. **Maintains separation** between technical workflows (`/ll:scan_codebase`) and product workflows (`/ll:scan_product`)

## Labels

`feature`, `product-dimension`, `deferred`

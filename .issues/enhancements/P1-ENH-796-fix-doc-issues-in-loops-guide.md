---
discovered_date: 2026-03-17T00:00:00Z
discovered_by: capture-issue
testable: false
---

# ENH-796: Fix documentation issues in LOOPS_GUIDE.md

## Summary

Several omissions, inconsistencies, and navigation issues in `docs/guides/LOOPS_GUIDE.md` (927 lines) including a critical missing evaluator entry in the reference table.

## Current Behavior

`docs/guides/LOOPS_GUIDE.md` (927 lines) has 11 documented issues: the `mcp_result` evaluator is absent from the main Evaluators reference table despite appearing in the harness evaluation pipeline, the `backoff:` field is mentioned in Tips without prior introduction, `max_retries` and `on_retry_exhausted` are only documented in the harness section (not the core state reference), there is no table of contents, 21 built-in loops are listed ungrouped, arrow styles are inconsistent (`──▶` vs `──→` vs `▶`), and `ll-loop test`/`ll-loop simulate` are never demonstrated in the walkthrough.

## Expected Behavior

All 11 documented issues are resolved: `mcp_result` appears in the Evaluators reference table with a description, `backoff:`, `max_retries`, and `on_retry_exhausted` are introduced in the core state reference section, a TOC is present at the top, built-in loops are grouped by category, arrow styles are standardized across all diagrams, `---` separator usage is consistent in APO loop sections, and the walkthrough demonstrates `ll-loop test` and `ll-loop simulate`.

## Motivation

The `mcp_result` evaluator appears in the harness evaluation pipeline table but is absent from the main Evaluators reference table — a critical omission that will cause users to miss this evaluator entirely when browsing the reference. The guide is 927 lines with no TOC, and 21 built-in loops are listed ungrouped, making it difficult to navigate and discover functionality.

## Issues to Fix

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | **High** | Evaluators table | `mcp_result` evaluator is **missing from the main Evaluators reference table** — add it |
| 2 | Medium | `apo-beam` loop definition | `eval_criteria` default is `""` while all other APO loops default to `"clarity, specificity, and effectiveness"` — verify and fix |
| 3 | Medium | Tips section | `backoff:` field mentioned without prior introduction — add introduction in core state reference |
| 4 | Medium | Core state documentation | `max_retries`/`on_retry_exhausted` only introduced in harness section, not in core state reference |
| 5 | Low | "Beyond the Basics" section | Vague heading with no introductory sentence listing topics covered |
| 6 | Low | Diagrams | Mixed arrow styles: `──▶` vs `──→` vs `▶` — standardize |
| 7 | Low | Built-in loops table | 21 loops listed with no grouping by category — group them |
| 8 | Low | APO loop sections | Inconsistent use of `---` horizontal rule separators |
| 9 | Low | `diff_stall` evaluator | Described ~500 lines after first mention — add forward reference or inline description |
| 10 | Low | Walkthrough section | `ll-loop test` and `ll-loop simulate` never demonstrated in walkthrough despite appearing in CLI reference |
| 11 | Low | Document | No table of contents for a 927-line document — add TOC |

## Implementation Steps

1. Add a table of contents at the top of the document
2. Add `mcp_result` to the main Evaluators reference table with description
3. Introduce `backoff:`, `max_retries`, and `on_retry_exhausted` in the core state reference section
4. Investigate and fix `apo-beam` `eval_criteria` default inconsistency
5. Add an introductory sentence to "Beyond the Basics" section
6. Standardize arrow styles across all diagrams
7. Group the 21 built-in loops by category (e.g., APO, harness, utility)
8. Standardize `---` separator usage in APO loop sections
9. Add a forward reference near `diff_stall`'s first mention in the evaluators table
10. Add `ll-loop test` and `ll-loop simulate` demonstrations to the walkthrough

## Scope Boundaries

- Only `docs/guides/LOOPS_GUIDE.md` is in scope — not restructuring other documentation files
- Not adding new loop features or changing any runtime behavior
- Not splitting the guide into multiple files; only improving navigation within the existing document
- Not updating `ll-loop` CLI code — documentation fixes only

## Impact

- **Priority**: P1 — The missing `mcp_result` evaluator entry is a critical omission; users browsing the reference table will not know this evaluator exists
- **Effort**: Small — All changes are documentation edits; no code changes required
- **Risk**: Low — Documentation-only change with no runtime impact
- **Breaking Change**: No

## Labels

`documentation`, `loops`, `captured`

## Resolution

All 10 documentation issues resolved in `docs/guides/LOOPS_GUIDE.md`:

1. Added table of contents at the top of the document
2. Added `mcp_result` to the main Evaluators reference table with verdict details and link to MCP Tool Actions
3. Added forward reference in `diff_stall` table entry linking to [Stall Detection](#stall-detection)
4. Added new **"Retry and Timing Fields"** subsection in Beyond the Basics introducing `backoff:`, `max_retries`, and `on_retry_exhausted` with example
5. Added introductory sentence to "Beyond the Basics" listing all covered topics
6. Fixed `apo-beam` `eval_criteria` default from `""` to `"clarity, specificity, and effectiveness"` — consistent with all other APO loops
7. Standardized arrow styles in all 5 APO FSM flow diagrams from `→` to `──→` (matching harness diagrams)
8. Removed `---` horizontal rule separators between APO subsections — rely on `###` headings consistently
9. Grouped built-in loops table into 4 categories: Issue Management, Code Quality, Reinforcement Learning, Automatic Prompt Optimization
10. Added steps 3 (Test) and 4 (Simulate) to the walkthrough with `ll-loop test` and `ll-loop simulate` examples; renumbered subsequent steps

## Status

**Completed** | Created: 2026-03-17 | Resolved: 2026-03-18 | Priority: P1

## Session Log
- `/ll:manage-issue` - 2026-03-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a39b5c75-560c-4c69-82fb-496433339a86.jsonl`
- `/ll:ready-issue` - 2026-03-18T15:56:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a39b5c75-560c-4c69-82fb-496433339a86.jsonl`
- `/ll:format-issue` - 2026-03-18T01:51:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a6fe969a-a054-43aa-be89-f0f4d50aacab.jsonl`
- `/ll:capture-issue` - 2026-03-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ca8a2338-e3dd-4309-8117-478c418261ea.jsonl`

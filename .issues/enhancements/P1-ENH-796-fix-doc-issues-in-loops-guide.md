---
discovered_date: 2026-03-17T00:00:00Z
discovered_by: capture-issue
---

# ENH-796: Fix documentation issues in LOOPS_GUIDE.md

## Summary

Several omissions, inconsistencies, and navigation issues in `docs/guides/LOOPS_GUIDE.md` (927 lines) including a critical missing evaluator entry in the reference table.

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

## Session Log
- `/ll:capture-issue` - 2026-03-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ca8a2338-e3dd-4309-8117-478c418261ea.jsonl`

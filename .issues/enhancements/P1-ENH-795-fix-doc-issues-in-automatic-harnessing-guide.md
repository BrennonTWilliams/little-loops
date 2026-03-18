---
discovered_date: 2026-03-17T00:00:00Z
discovered_by: capture-issue
---

# ENH-795: Fix documentation issues in AUTOMATIC_HARNESSING_GUIDE.md

## Summary

Several factual errors, broken links, and inconsistencies in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` degrade accuracy and usability.

## Motivation

Two P1 errors (a false heading claim and a broken anchor) will actively mislead readers. The remaining items reduce trust in the document and create confusion when readers try to follow examples. The guide is 603 lines with no TOC, making navigation difficult without fixes.

## Issues to Fix

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | **High** | "Full 6-phase ordering" heading (~line 196) | Heading claims 6 phases but lists only 5 — fix count in heading |
| 2 | **High** | Broken anchor link | Note references `#check_mcp` but anchor is `#mcp-tool-gates-check_mcp` — fix the link |
| 3 | Medium | Conceptual cycle diagram (~lines 27–55) | Diagram omits `check_mcp` and `check_skill` — update to show all phases |
| 4 | Medium | Stall detection example (~line 469) | Uses `${current_item}` but established syntax is `${captured.current_item.output}` — fix interpolation |
| 5 | Medium | `check_semantic` action field | Uses `echo 'Evaluating...'` with no explanation of why a placeholder echo is needed for LLM judge step |
| 6 | Low | Discovery command table | "Active issues list" command string is very long in a narrow table cell — reformat |
| 7 | Low | `action_type` usage | Variant A uses `action_type: prompt` while `check_skill` uses `action_type: slash_command` — add explanation |
| 8 | Low | `timeout` field | `timeout: 14400` has inline comment "4-hour limit" but unit (seconds) never stated — add unit |
| 9 | Low | Worked example | Omits `check_mcp`/`check_skill` phases without explanation — add a note clarifying the omission |
| 10 | Low | Document | No table of contents for a 603-line document — add TOC |

## Implementation Steps

1. Add a table of contents at the top of the document
2. Fix the "6-phase" heading to say "5-phase" (or count and add missing phase if one was accidentally dropped)
3. Fix the broken anchor: change `#check_mcp` reference to `#mcp-tool-gates-check_mcp`
4. Update the conceptual cycle diagram to include all phases
5. Fix variable interpolation in stall detection example
6. Add prose explaining the `echo` placeholder in `check_semantic`
7. Reformat the long command in the discovery table
8. Explain `action_type` difference between Variant A and `check_skill`
9. State the unit for `timeout` field
10. Add a note in the worked example explaining the simplified scope

## Session Log
- `/ll:capture-issue` - 2026-03-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ca8a2338-e3dd-4309-8117-478c418261ea.jsonl`

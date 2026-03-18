---
discovered_date: 2026-03-17T00:00:00Z
discovered_by: capture-issue
testable: false
---

# ENH-795: Fix documentation issues in AUTOMATIC_HARNESSING_GUIDE.md

## Summary

Several factual errors, broken links, and inconsistencies in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` degrade accuracy and usability.

## Current Behavior

`docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` contains factual errors, broken anchor links, and inconsistencies: the "Full 6-phase ordering" heading lists only 5 phases, a `#check_mcp` anchor reference is broken, the conceptual cycle diagram omits phases, a variable interpolation example uses incorrect syntax, and the 603-line document lacks a table of contents.

## Expected Behavior

All 10 documented issues are resolved: the heading accurately reflects the phase count, all anchor links navigate correctly, the cycle diagram shows all phases, variable interpolation examples use the correct `${captured.current_item.output}` syntax, and a table of contents aids navigation.

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

## Success Metrics

- All 10 documented issues resolved (2 High, 3 Medium, 5 Low severity)
- Broken anchor (`#check_mcp`) corrected and navigable
- Factual heading error ("6 phases" vs actual count) corrected
- Table of contents present for the 603-line document
- Variable interpolation example uses correct `${captured.current_item.output}` syntax

## Scope Boundaries

- **In scope**: The 10 specific issues enumerated in the Issues to Fix table
- **Out of scope**: Restructuring document sections, adding new content beyond the TOC, rewriting existing correct prose, changing any YAML examples beyond the listed fixes

## API/Interface

N/A - No public API changes (documentation-only fix)

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

## Integration Map

### Files to Modify
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`

### Dependent Files (Callers/Importers)
- TBD - use grep to find references: `grep -r "AUTOMATIC_HARNESSING_GUIDE" docs/`

### Similar Patterns
- N/A

### Tests
- N/A - documentation-only change

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (the file being fixed)

### Configuration
- N/A

## Impact

- **Priority**: P1 - Two High-severity items actively mislead readers (false heading, broken anchor)
- **Effort**: Small - Targeted edits to a single markdown file, no code changes
- **Risk**: Low - Documentation-only change with no functional impact
- **Breaking Change**: No

## Labels

`documentation`, `enhancement`, `low-risk`

## Resolution

All 10 documented issues resolved:
1. Added table of contents at the top of the document
2. Fixed "Full 6-phase ordering" heading → "Full 5-phase ordering"
3. Fixed broken anchor `#check_mcp` → `#mcp-tool-gates-check_mcp`
4. Updated conceptual cycle diagram to include `check_mcp` and `check_skill` phases
5. Fixed stall detection variable syntax `${current_item}` → `${captured.current_item.output}`
6. Added explanation for `echo` placeholder action in `check_semantic` section
7. Reformatted long "Active issues list" discovery command in the table
8. Added `action_type` comparison table (`slash_command` vs `prompt`) in `check_skill` section
9. Added "seconds" unit to `timeout: 14400` comment
10. Added note in worked example explaining omission of `check_mcp`/`check_skill` phases

## Status

**Completed** | Created: 2026-03-17 | Resolved: 2026-03-18 | Priority: P1

## Session Log
- `/ll:manage-issue` - 2026-03-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:ready-issue` - 2026-03-18T15:47:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/25dfcda4-185b-4a88-90c8-6899e0f2e16f.jsonl`
- `/ll:format-issue` - 2026-03-18T01:50:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b830ec36-9580-485f-8f7c-92ded037ca03.jsonl`
- `/ll:capture-issue` - 2026-03-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ca8a2338-e3dd-4309-8117-478c418261ea.jsonl`

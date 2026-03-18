---
discovered_date: 2026-03-17T00:00:00Z
discovered_by: capture-issue
---

# ENH-798: Fix documentation issues in WORKFLOW_ANALYSIS_GUIDE.md

## Summary

Several misleading recipes, undefined variables, and minor inconsistencies in `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` (282 lines).

## Motivation

The "Quick pattern check" recipe promises users they can stop after Step 1 of the pipeline, but the command runs all steps with no mid-pipeline stop. This overpromise will confuse users who try to follow the recipe. Additionally, the priority formula uses input variables with undefined ranges, making the thresholds uninterpretable.

## Issues to Fix

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | **High** | "Quick pattern check" recipe | Claims users can "stop after Step 1" — the command runs all steps with no mid-pipeline stop; fix or remove |
| 2 | Medium | `cohesion_score` explanation | Appears after Step 3 section despite being a Step 2 concept — move to correct location |
| 3 | Medium | Priority formula (HIGH ≥8, MEDIUM ≥4, LOW <4) | `frequency`, `workflow_count`, and `friction_score` never defined with ranges — define them |
| 4 | Medium | `type` field in proposals | Not explained at first mention; the 9-type table (~line 189) explains it but isn't cross-referenced |
| 5 | Medium | "Quick pattern check" recipe | `ll-messages --stdout \| head -20` previews raw messages but performs no pattern analysis — fix recipe |
| 6 | Low | CLI reference table | `--skip-cli` and `--commands-only` flags listed but never demonstrated in any recipe |
| 7 | Low | Frequency threshold | "Frequency ≥ 5" automation threshold conflicts with LOW priority bucket (1–2 occurrences) — clarify |
| 8 | Low | ASCII pipeline diagram | Bottom row shows 3 output arrows while top row has 5 columns — fix visual mismatch |
| 9 | Low | Document | No table of contents — add TOC |

## Implementation Steps

1. Add a table of contents at the top of the document
2. Fix the "Quick pattern check" recipe — either remove the false "stop after Step 1" claim or implement a stop mechanism
3. Fix the second misleading recipe (`ll-messages | head -20`) to actually perform analysis or change the stated purpose
4. Define `frequency`, `workflow_count`, and `friction_score` with their valid ranges near the priority formula
5. Add a cross-reference from the first mention of `type` field to the 9-type table
6. Move `cohesion_score` explanation to the Step 2 section
7. Clarify the frequency threshold vs. LOW priority bucket conflict
8. Fix the ASCII pipeline diagram bottom row arrow count
9. Add recipe demonstrations for `--skip-cli` and `--commands-only` or remove them from the reference table

## Session Log
- `/ll:capture-issue` - 2026-03-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ca8a2338-e3dd-4309-8117-478c418261ea.jsonl`

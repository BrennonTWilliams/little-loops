---
id: ENH-1368
type: ENH
priority: P2
status: completed
discovered_date: 2026-05-05
discovered_by: manual
testable: true
confidence_score: 100
outcome_confidence: 100
---

# ENH-1368: Audit and Fix 11 Issue-Refinement Built-in Loops

## Summary

Audited the 11 built-in loops in the `issue-management` category to identify stale content, duplication, and broken behavior. Found 4 actionable problems: a stale loop description, a missing rate-limit guard, a superseded loop with a weak decomposition path, and copy-paste duplication between two sibling loops. Resolved all four.

## Problems Found and Fixed

### P1 — Stale description in `issue-refinement` (fixed)

**File:** `scripts/little_loops/loops/issue-refinement.yaml`

The description said "format → score → refine pipeline" but the loop was refactored (ENH-901) to delegate entirely to `refine-to-ready-issue`. The "format" and "score" steps live inside the sub-loop. The outer loop simply picks the next issue via `ll-issues next-action` and delegates. Updated description to accurately reflect this.

### P2 — `sprint-refine-and-implement` missing rate-limit guard (fixed)

**File:** `scripts/little_loops/loops/sprint-refine-and-implement.yaml:101`

`auto-refine-and-implement` had `fragment: with_rate_limit_handling` on its `implement_issue` state. The `sprint-refine-and-implement` equivalent was missing it — a rate limit during a long sprint run would hard-error instead of backing off gracefully. Added the fragment and `on_rate_limit_exhausted: done` transition.

### P3 — `issue-size-split` superseded and weak (removed)

**File:** `scripts/little_loops/loops/issue-size-split.yaml` (deleted)

The loop's `split_issue` state used a free-form LLM prompt to decompose issues manually rather than calling `/ll:issue-size-review --auto`, which already handles automated decomposition. Its overall purpose (find large → split → normalize → repeat) was fully covered by `backlog-flow-optimizer`'s BOTTLENECK_SIZE path and by invoking `/ll:issue-size-review --auto` directly. Removed the loop file and cleaned up all references in docs, README, and tests.

### P4 — Copy-paste duplication between sibling loops (documented)

**Files:** `auto-refine-and-implement.yaml`, `sprint-refine-and-implement.yaml`

The `get_passed_issues`, `implement_next`, `implement_issue`, and `skip_and_continue` states are ~identical between both files (differing only in `.tmp` file prefixes). This is what caused P2 to exist — when `auto-refine-and-implement` got rate-limit handling, `sprint-refine-and-implement` silently fell behind. The FSM fragment system (lib/common.yaml) only supports single-state blueprints, not multi-state groupings, so full DRY extraction isn't possible without a new FSM feature. Added cross-reference comments in both files pointing to each other so future edits stay in sync.

## Loops Audited — Final Status

| Loop | Verdict |
|------|---------|
| `refine-to-ready-issue` | Healthy — no action |
| `recursive-refine` | Healthy — no action |
| `autodev` | Healthy — no action |
| `backlog-flow-optimizer` | Healthy — no action |
| `issue-discovery-triage` | Healthy — no action |
| `issue-staleness-review` | Healthy — no action |
| `prompt-across-issues` | Healthy — no action |
| `issue-refinement` | Fixed description (P1) |
| `sprint-refine-and-implement` | Added rate-limit guard (P2) |
| `issue-size-split` | **Removed** (P3) |
| `auto-refine-and-implement` | Added cross-reference comment (P4) |

## Changes Made

- `scripts/little_loops/loops/issue-refinement.yaml` — updated description
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — added `fragment: with_rate_limit_handling` + `on_rate_limit_exhausted: done` to `implement_issue`; added cross-reference comment
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — added cross-reference comment
- `scripts/little_loops/loops/issue-size-split.yaml` — **deleted**
- `scripts/little_loops/loops/README.md` — removed `issue-size-split` row, updated `issue-refinement` description
- `docs/guides/LOOPS_GUIDE.md` — removed `issue-size-split` row
- `scripts/tests/test_builtin_loops.py` — removed `issue-size-split` from expected-loops set and from `REQUIRED_ON_BLOCKED` list

## Verification

All 293 tests in `test_builtin_loops.py` pass after changes.

## Status

**Completed** | 2026-05-05 | Priority: P2

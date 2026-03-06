---
discovered_date: 2026-03-05
discovered_by: capture-issue
---

# BUG-599: issue-refinement loop stuck in infinite cycle due to fmt/priority bugs

## Summary

Five bugs in `loops/issue-refinement.yaml` and `ll-loop run -v` cause the issue-refinement loop to run indefinitely and process issues in the wrong order. The critical bug is a mismatch between what the evaluate state considers a failure (`fmt=✗`) and what the fix state will act on (only `fmt=—`), creating an unbreakable cycle. Observed by running `ll-loop run issue-refinement -v` in an external project and confirmed via `ll-loop history`.

## Current Behavior

1. **`fmt=✗` vs `fmt=—` mismatch — infinite loop (critical)**: The evaluate prompt fails any issue where `fmt` shows `✗`. But the fix prompt's Step A only triggers `/ll:format-issue` if the column shows `—` (em-dash). When format-issue was previously attempted and produced `✗` (run but failed/incomplete), the fix never re-runs it. Evaluate perpetually fails and routes back to fix, which does nothing to resolve `fmt`, which causes evaluate to fail again — forever.

2. **No escape path for issues that hit an inherent confidence ceiling (high)**: The fix prompt stops after 5 refinements regardless of score. But evaluate still fails if `confidence < 70`. FEAT-2078 hit 63/100 with an "inherent ceiling" (file renames touching 11+ importers), was accepted by the fix step as done, but evaluate continues to fail it. Loop cycles on that issue indefinitely with no exit.

3. **Issue selection by "highest ID" skips high-priority bugs (medium)**: The fix prompt selects "the highest Issue ID that still needs refinement work." A P4 FEAT (FEAT-2078, ID 2078) was worked on for 14 minutes while a P0 BUG (BUG-2169, ID 2169 — a higher numeric ID) went untouched. ID-based selection is the wrong ordering heuristic.

4. **Evaluate `on_error: fix` on LLM timeout wastes a fix slot (medium)**: In the observed run, iteration 1's LLM evaluation timed out (`LLM evaluation timeout`), causing `on_error: fix` to fire and spawn a 14-minute Claude session unnecessarily. History shows each LLM evaluate step takes ~24 seconds and is vulnerable to inference latency spikes. A timeout should retry evaluation, not trigger a full fix.

5. **`ll-loop run -v` duplicates shell action output (low)**: In verbose run mode, shell command output is printed twice per iteration. Confirmed by comparing `run -v` output (table appears twice) with `history` output (table appears once). The shell command runs correctly once; the duplication is in the verbose display layer.

## Expected Behavior

1. Fix prompt handles `fmt=✗` identically to `fmt=—`: re-runs `/ll:format-issue` to clear either state.
2. Fix has a ceiling-acceptance path: after 5 refinements with `readiness>=85`, the issue is treated as done for loop purposes even if `confidence < 70`, and the loop moves on.
3. Issue selection processes by priority (P0 → P5), using ID as tiebreaker — not by highest ID alone.
4. `on_error: evaluate` (retry) instead of `on_error: fix` in the evaluate state.
5. Verbose mode prints each shell action's output exactly once.

## Steps to Reproduce

1. Have a project with active issues where some have `fmt=✗` in `ll-issues refine-status` (format previously attempted but incomplete).
2. Run `ll-loop run issue-refinement`.
3. Observe: evaluate fails on `fmt=✗`; fix never re-runs format-issue (Step A only checks for `—`); loop cycles evaluate → fix → evaluate → fix indefinitely without progress.

## Root Cause

- **Bug 1**: `loops/issue-refinement.yaml` fix prompt Step A: condition `"column shows — or absent"` does not cover the `✗` state for `fmt` or `verify`.
- **Bug 2**: `loops/issue-refinement.yaml` fix prompt Step C: no logic to flag an issue as "ceiling reached" and exempt it from future evaluate failures.
- **Bug 3**: `loops/issue-refinement.yaml` fix prompt: `"Find the highest Issue ID"` uses numeric ID as a proxy for priority — wrong heuristic.
- **Bug 4**: `loops/issue-refinement.yaml` evaluate state: `on_error: fix` should be `on_error: evaluate` to retry on timeout rather than spawning a fix session.
- **Bug 5**: `scripts/little_loops/cli/loop/info.py` (verbose run display) — shell output rendered twice per iteration in verbose mode.

## Motivation

The `issue-refinement` loop is a key component of automated issue prep workflows used by `ll-auto`, `ll-parallel`, and `ll-sprint`. When the loop infinite-cycles due to the `fmt=✗` mismatch, those automation pipelines stall entirely — no issues get refined, and the loop must be killed manually. Projects relying on automated refinement before a sprint lose the ability to prepare issues hands-free, negating the primary value of the loop system.

## Proposed Solution

**Bug 1** — Update Step A in the fix prompt to cover both `—` and `✗`:
```
- format incomplete (column shows — or ✗): /ll:format-issue [ISSUE_ID] --auto
- verify incomplete (column shows — or ✗): /ll:verify-issues [ISSUE_ID] --auto
```

**Bug 2** — Add a ceiling-acceptance rule to Step C: after 5 refinements, if `readiness >= 85`, treat the issue as refined-to-ceiling and move on. The evaluate prompt should also be updated to accept `readiness >= 85` as passing when `refine >= 5` (inherent ceiling case).

**Bug 3** — Change fix prompt selection criterion from "highest Issue ID" to "highest-priority issue needing work (lowest P number first, then highest ID as tiebreaker)."

**Bug 4** — Change `on_error: fix` → `on_error: evaluate` in the evaluate state.

**Bug 5** — Investigate `scripts/little_loops/cli/loop/info.py` for double-render of action output in verbose run mode and add a regression test.

## Integration Map

### Files to Modify
- `loops/issue-refinement.yaml` — Bugs 1, 2, 3, 4 (fix prompt and evaluate routing)
- `scripts/little_loops/cli/loop/info.py` — Bug 5 (verbose output duplication)

### Dependent Files (Callers/Importers)
- `scripts/tests/test_ll_loop_display.py` — Tests for display behavior; add regression test for Bug 5

### Similar Patterns
- Other loop YAML files in `loops/` that use fix prompts with column-check logic should be audited for the same `✗` vs `—` mismatch pattern

### Tests
- `scripts/tests/test_ll_loop_display.py` — Add test asserting verbose mode emits each shell action output exactly once

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Fix `loops/issue-refinement.yaml` evaluate state: change `on_error: fix` → `on_error: evaluate`
2. Fix `loops/issue-refinement.yaml` fix prompt Step A: add `✗` to column-check conditions for `fmt` and `verify`
3. Fix `loops/issue-refinement.yaml` fix prompt: change issue selection from "highest ID" to "highest priority then highest ID"
4. Fix `loops/issue-refinement.yaml` fix prompt Step C: add ceiling-acceptance logic (after 5 refinements with readiness>=85, skip to next issue)
5. Investigate and fix double-output in `scripts/little_loops/cli/loop/info.py` verbose mode
6. Add regression test to `scripts/tests/test_ll_loop_display.py`

## Impact

- **Priority**: P2 — The loop is non-functional due to infinite cycling on the `fmt=✗` mismatch; blocks automated issue refinement workflows entirely
- **Effort**: Small — Bugs 1–4 are YAML config text changes; Bug 5 requires code investigation in one file
- **Risk**: Low — YAML changes are isolated to the loop config; display fix is additive
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | FSM loop architecture and state routing |
| `.claude/CLAUDE.md` | CLI tools reference (`ll-loop`, `ll-issues`) |

## Labels

`bug`, `loops`, `fsm`, `issue-refinement`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-03-05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e5ab8beb-daac-4b0a-bbba-56295f1d683b.jsonl`
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/605b9148-691d-487e-9661-b1d6c6c35f7b.jsonl`

---

## Status

**Open** | Created: 2026-03-05 | Priority: P2

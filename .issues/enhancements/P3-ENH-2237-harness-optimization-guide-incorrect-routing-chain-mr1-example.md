---
id: ENH-2237
type: ENH
status: done
priority: P3
discovered_date: 2026-06-19
discovered_by: audit-docs
testable: false
completed_at: 2026-06-20 04:06:26+00:00
labels:
- docs
- loops
- meta-loop
- harness
relates_to:
- ENH-2236
---

# ENH-2237: Fix incorrect routing chain in HARNESS_OPTIMIZATION_GUIDE MR-1 canonical example

## Summary

The MR-1 canonical example in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (lines 104–108) describes the routing chain for `loop-composer-adaptive.yaml` incorrectly — it reverses `check_replan_budget` and `increment_replan_count`, omits intermediate states, and mischaracterizes when the budget gate fires. The example needs to be rewritten to reflect the actual YAML routing.

## Current Behavior

`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` lines 107–108 describe the MR-1 canonical example routing chain for `loop-composer-adaptive.yaml`:

> "Full routing chain: `increment_replan_count → check_replan_budget (output_numeric) → read_completed_summaries → read_last_verdict → reassess (llm_structured)`"

This chain is factually incorrect in two ways:

1. **`increment_replan_count` and `check_replan_budget` are reversed.** In the actual YAML (`scripts/little_loops/loops/loop-composer-adaptive.yaml:442–453`), `check_replan_budget` routes `on_yes` to `increment_replan_count`, not the other way around.

2. **`check_replan_budget` does not precede `read_completed_summaries`.** The actual path between `increment_replan_count` and `read_completed_summaries` runs through `apply_replan` and a full sub-loop execution. The guide implies they are adjacent.

The actual routing to re-enter `reassess` after a first replan:

```
reassess (1st run)
  → parse_reassess_decision
  → route_reassess_replan (on_yes)
  → check_replan_budget (output_numeric gate — blocks if budget exhausted)
  → increment_replan_count
  → apply_replan
  → (sub-loop re-executes)
  → write_step_failed
  → read_completed_summaries
  → read_last_verdict
  → reassess (2nd run, now budget-gated)
```

The guide's description is also misleading about what the gate does: it says `check_replan_budget` "gates access to the reassess prompt," implying it blocks the *first* call. In reality, `reassess` is always reached on the first sub-loop failure; `check_replan_budget` gates *re-entry* after a replan attempt.

## Expected Behavior

Lines 104–108 are rewritten to describe the correct routing, distinguishing first-entry (ungated) from re-entry (budget-gated), and giving the accurate state ordering:

Suggested replacement for the MR-1 canonical example block:

```
**Canonical MR-1 example — `loop-composer-adaptive`'s `reassess` gate**: When a
sub-loop fails, `reassess` (`llm_structured`) is reached unconditionally via
`write_step_failed → read_completed_summaries → read_last_verdict → reassess`.
If `reassess` decides to replan, `check_replan_budget` (`output_numeric`, operator: `lt`)
gates *re-entry*: `reassess → parse_reassess_decision → route_reassess_replan (on_yes)
→ check_replan_budget → increment_replan_count → apply_replan → (sub-loop re-runs)
→ … → reassess`. The budget counter is a non-LLM signal the LLM cannot self-inflate,
so it enforces a hard ceiling on how many times the LLM judge can decide to replan —
satisfying MR-1's requirement that every `llm_structured` state be paired with a
non-LLM evaluator in its routing chain.
```

## Scope Boundaries

- Only update lines 104–108 of `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (the MR-1 canonical example block)
- Do not change any other sections of the guide
- Do not modify `loop-composer-adaptive.yaml` or any loop YAML files
- Cross-check of the `harness-single-shot.yaml:check_semantic → check_invariants` pattern on the same lines is read-only; do not alter it

## Implementation Steps

1. Read `loop-composer-adaptive.yaml` states `check_replan_budget`, `increment_replan_count`, `write_step_failed`, `read_completed_summaries`, `reassess` to confirm actual routing order
2. Replace lines 104–108 in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` with the corrected example text from `## Expected Behavior`
3. Verify the `harness-single-shot.yaml:check_semantic → check_invariants` claim on the same lines is unchanged

## Impact

- **Priority**: P3 — Low; incorrect example causes confusion when authors model new loops on it, but does not break any runtime behavior
- **Effort**: Small — single prose block replacement in one doc file; no code changes
- **Risk**: Low — documentation-only change; no functional or behavioral impact
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-19 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-06-20T04:05:28 - `f8d4add9-958f-4e0b-9238-74f3df289581.jsonl`
- `/ll:format-issue` - 2026-06-20T03:51:02 - `d0cf3b86-358f-4c2f-ba19-f4565d61ace4.jsonl`

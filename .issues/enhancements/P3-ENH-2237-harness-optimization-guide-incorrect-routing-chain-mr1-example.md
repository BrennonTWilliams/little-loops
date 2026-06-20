---
id: ENH-2237
type: ENH
status: open
priority: P3
discovered_date: 2026-06-19
discovered_by: audit-docs
labels:
- docs
- loops
- meta-loop
- harness
relates_to:
- ENH-2236
---

# ENH-2237: Fix incorrect routing chain in HARNESS_OPTIMIZATION_GUIDE MR-1 canonical example

## Problem

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

## Implementation Notes

- Verify routing by reading `scripts/little_loops/loops/loop-composer-adaptive.yaml` states: `check_replan_budget` (line 442), `increment_replan_count` (line 431), `write_step_failed` (line 368), `read_completed_summaries` (line 457), `reassess` (line 496)
- The replacement text should keep the example concise — the key point is that the non-LLM gate enforces a ceiling on LLM-decided replans, not that it blocks first entry
- Cross-check with the `harness-single-shot.yaml:check_semantic → check_invariants` pattern claim on the same lines (verified accurate; don't change that)

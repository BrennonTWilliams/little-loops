---
id: FEAT-1809
title: Adaptive `loop-composer` — Re-plan-on-Failure Variant
type: FEAT
priority: P3
status: open
parent: EPIC-1811
captured_at: "2026-05-30T06:48:30Z"
discovered_date: 2026-05-30
discovered_by: capture-issue
relates_to: [FEAT-1808, FEAT-1810]
---

# FEAT-1809: Adaptive `loop-composer` — Re-plan-on-Failure Variant

## Summary

Extend `loop-composer` (FEAT-1808) with adaptive execution: when a mid-plan sub-loop fails, returns low confidence, or terminates with an unexpected result, the composer re-plans the *tail* of the DAG using the new world state instead of aborting. The plan becomes mutable; the executor becomes a planner-executor pair that re-enters the decompose state under defined conditions.

## Motivation

Pure upfront-planning (FEAT-1808) is cheap, inspectable, and easy to debug — but brittle. Real multi-loop chains routinely hit branches the planner couldn't predict: an `ll:scan-codebase` step turns up no issues, an `ll:refine-issue` returns low confidence, a sub-loop terminates in `failed` instead of `done`. Without re-planning, the composer either stops cold or carries broken assumptions forward into downstream steps.

**Why:** The most common reason multi-step orchestrators degrade in practice is plan-mutation gaps — the plan was right when written, wrong by step 4. Letting the planner re-enter at known checkpoints recovers most of those cases without falling back to a fully reactive (and unauditable) agent loop.
**How to apply:** This is *not* a replacement for FEAT-1808; it sits on top of the static planner. Keep the upfront plan as the dominant control flow; re-planning is the exception path.

## Proposed Solution

Layer the following onto `loop-composer.yaml` (or fork to `loop-composer-adaptive.yaml` if the divergence is large enough):

1. **Per-step verdict gate.** After each sub-loop completes, evaluate `{success, confidence, terminal_state}`. If verdict is `partial` / `blocked` / low-confidence, route to `reassess` instead of the next step.
2. **`reassess` state.** Tier 2 LLM prompt that takes the *original goal*, the *current plan*, the *completed steps* (with outputs), and the *failing step's verdict*. Output is one of:
   - `CONTINUE` — verdict was a false alarm; proceed with the original plan.
   - `REPLAN_TAIL` — discard steps after the failing one; re-emit a new tail plan.
   - `ABORT` — goal is unreachable; emit failure summary and exit.
3. **Bounded re-plan budget.** Hard limit on re-plan invocations per run (e.g. `${context.max_replans}` default 2). Each re-plan increments a counter; on exhaustion → `ABORT`.
4. **Step-output checkpointing.** Each completed sub-loop's output is persisted to `.loops/tmp/composer-checkpoints/step-<N>.json` so re-plans have full context without re-running upstream steps. Tail re-plans MUST consume these checkpoints in their prompt.
5. **Plan-version log.** Every plan version (v1 from initial decompose, v2 from first re-plan, …) is written to `.loops/tmp/composer-plans/v<N>.json` for post-mortem auditing.

**Non-obvious design constraints:**
- **Upstream steps are immutable.** Re-planning ONLY mutates the unexecuted tail. A re-plan that wants to undo a completed step must explicitly emit a compensating step (e.g. a revert/cleanup loop) rather than rewriting history. This keeps the audit trail straight.
- **`reassess` must be cheap.** It runs after every step, so the prompt and context size matter. Pass only the failing step's verdict + plan summary, not the full output blobs (those live in checkpoints).
- **Re-plan does not re-decompose from scratch.** The prompt is "given completed steps S1..Sk and failed step Sk+1, propose a new Sk+2..Sn". Full re-decomposition is reserved for an `ABORT` + retry at the user level.

## Meta-Loop Considerations

Per `.claude/CLAUDE.md` § Loop Authoring, any loop that mutates other harness artifacts is a meta-loop and needs non-LLM evaluator pairing. `loop-composer-adaptive` orchestrates other loops but doesn't *write* harness artifacts itself, so it's a regular orchestration loop — **but** the `reassess` LLM judge is exactly the kind of self-evaluation surface that mis-grades reliably. Pair `reassess` with an exit-code / `output_numeric` evaluator (e.g. step exit-code, files-produced count) as ground truth before trusting the LLM's `CONTINUE` verdict.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/loop-composer.yaml` OR `loop-composer-adaptive.yaml` (decide during design — depends on whether the static and adaptive variants share enough states to compose from a shared fragment in `loops/lib/`)
- `scripts/little_loops/loops/lib/composer.yaml` (new likely) — extract `reassess` and verdict-gate fragments for reuse between static + adaptive
- `scripts/tests/test_loop_composer_adaptive.py` (new)
- `docs/guides/LOOPS_GUIDE.md` — note adaptive variant and when to prefer it

### Similar Patterns
- `scripts/little_loops/loops/recursive-refine.yaml` — re-entrant decomposition with budget caps (closest existing analog)
- `scripts/little_loops/loops/harness-single-shot.yaml` — `on_partial` routing precedent for verdict gates
- FEAT-1808 (predecessor — must land first)

### Configuration
- `orchestration.composer.adaptive.enabled` (default false until proven)
- `orchestration.composer.adaptive.max_replans` (default 2)
- `orchestration.composer.adaptive.reassess_min_confidence` (default 0.6 — below this, automatically `REPLAN_TAIL`)

## Open Questions

1. **Fork vs. flag.** Is adaptive a separate loop file or a `context.adaptive=true` switch on FEAT-1808? Fork is cleaner for users; flag avoids duplication. Pattern-finder pass during design should compare both shapes.
2. **Re-plan loop budget interaction with `max_iterations`.** The composer's `max_iterations` and `max_replans` need a sane combined cap so re-plans can't multiply iteration count uncontrolled.
3. **Compensating steps.** Should the adaptive composer have a vocabulary of "undo" loops (e.g. revert-last-commit) it can emit during re-plan? Probably out of scope for the MVP — flag for post-mortem after first real run.

## Prerequisite

FEAT-1808 must ship before this. Implementing adaptive without the static planner under it is a leaky abstraction.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-31T21:34:34 - `922ffae8-14ce-45e5-a71a-02187250e8c9.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:08 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:14 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-30T06:48:30Z - `6be17ec6-da10-4c91-9b41-f2c0b3be4efb.jsonl`

---

## Status

- **State**: open
- **Created**: 2026-05-30

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and FEAT-1808 both spec intermediate artifacts using bare `.loops/tmp/` paths (`composer-checkpoints/step-<N>.json`, `composer-plans/v<N>.json`). Per MR-3 (`ll-loop validate` WARNING), all intermediate artifacts MUST be written under `${context.run_dir}/` to prevent state corruption on concurrent runs. Update all artifact paths in the Implementation Steps to use `${context.run_dir}/` (e.g. `${context.run_dir}/checkpoints/step-<N>.json`, `${context.run_dir}/plans/v<N>.json`). The path convention should be established in FEAT-1808 first; this issue must inherit the same convention.

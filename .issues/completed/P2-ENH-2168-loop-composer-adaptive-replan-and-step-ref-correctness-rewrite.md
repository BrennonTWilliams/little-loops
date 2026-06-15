---
id: ENH-2168
title: Correctness rewrite of loop-composer-adaptive (step-ref resolution, replan
  budget/retry semantics, JSONL interpolation) + shared fixes in loop-composer
type: ENH
priority: P2
status: done
captured_at: '2026-06-15T15:43:43Z'
completed_at: '2026-06-15T15:43:43Z'
discovered_date: '2026-06-15'
relates_to:
- FEAT-1809
- ENH-2135
size: Medium
---

# ENH-2168: Correctness rewrite of loop-composer-adaptive

## Summary

An audit of `scripts/little_loops/loops/loop-composer-adaptive.yaml` surfaced
8 design-level defects that the mechanical `ll-loop validate` gate does not
catch — two of them High-severity bugs that broke the loop's documented core
promises. All 8 were independently confirmed by a read-only `loop-specialist`
static verification pass plus two `Explore` agents that established the FSM
engine mechanics and the (tightly-coupled) existing test coverage. This issue
fixes all 8, adds a new `validate_replan` state, and propagates the two shared
bugs' fixes to the sibling static `loop-composer.yaml`. Extends the composer
hardening begun in [[ENH-2135]] (which fixed `check_auto_plan` error-routing in
the static loop but explicitly left the adaptive variant).

## Root Cause

- **Files**: `scripts/little_loops/loops/loop-composer-adaptive.yaml`,
  `scripts/little_loops/loops/lib/composer.yaml`,
  `scripts/little_loops/loops/loop-composer.yaml`
- **Cause** (per finding):

| # | Sev | Defect |
|---|-----|--------|
| 1 | High | **Step-output references never resolved.** The decompose prompt instructed the LLM to chain steps with `{{step_id_output}}`, but `replace_step_ref` in `execute_plan` looked up `checkpoints/step-{ref_id}.json` using the full brace contents — `step-step_1_output.json`, which never exists (the file is `step-step_1.json`). The literal `{{step_1_output}}` was passed through unsubstituted, silently breaking step-to-step data flow (the whole point of the DAG). Identical in `loop-composer.yaml`. |
| 2 | High | **Replan budget consumed by every failure.** `write_step_failed` routed unconditionally to `increment_replan_count → check_replan_budget` *before* `reassess` decided anything, so a CONTINUE decision still burned budget; and increment-then-check with `max_replans=2` permitted only **one** reassessment (`count=1<2` ok, `count=2` not `<2` abort). |
| 3 | Med | **`apply_replan` wrote an unvalidated tail.** The LLM's `new_tail_plan` was written straight to `composer-plan.json`/`topo-order.json` with no catalog-membership / node-cap / cycle / duplicate-`step_id` checks — bypassing the `validate_plan` fragment the initial plan passes. |
| 4 | Med | **Replanned tail ignored its own `depends_on`.** `apply_replan` wrote `topo-order` in raw array order rather than the Kahn topological sort used for the initial plan. |
| 5 | Med | **Sub-loop JSONL interpolated into Python `"""..."""` literals.** `write_step_success`/`write_step_failed`/`parse_plan`/`parse_reassess_decision`/`apply_replan` did `x = """${captured.X.output}"""`. The captured value (a JSONL event stream / LLM output) is substituted into a Python triple-quoted literal, so embedded `"""`/`\n`/`\"`/`\\` corrupt the parse — the same bug class the catalog read-from-disk fix (`lib/composer.yaml`) already solved, never propagated to these states. |
| 6 | Low | **Dead `llm_structured` evaluators.** `decompose_goal` and `review_chain` routed `on_yes`/`on_no`/`on_partial` all to the same next state, so the LLM grading call cost a round-trip and changed nothing (routing was decided by the downstream deterministic parser). |
| 7 | Low | **`check_auto_plan` `on_error: execute_plan`** silently skipped the HITL approval gate on a genuine error — the fail-open path [[ENH-2135]] fixed in the static loop but left in the adaptive variant. |
| 8 | High | **Failed step locked as immutable.** `write_step_failed` appended the failing step to `completed-steps.txt`, which `apply_replan` treated as the immutable boundary — so REPLAN_TAIL could never retry the step that triggered the reassess, directly contradicting the loop's "replace only the unexecuted tail" promise. (Found by `loop-specialist` during verification.) |

## Resolution

- **Status**: Done
- **Closed**: 2026-06-15

### #1 — align placeholder + tolerant lookup (both loops)
Prompt now says `{{step_id}}` (e.g. `{{step_1}}`); `replace_step_ref` also strips
a trailing `_output` defensively so legacy phrasing still resolves.

### #2 — replan budget only consumed by REPLAN_TAIL (new graph)
```
write_step_failed → read_completed_summaries → read_last_verdict → reassess
  reassess → parse_reassess_decision → route_reassess_continue
    route_reassess_continue  on_yes(CONTINUE)   → execute_plan          # no budget consumed
                             on_no               → route_reassess_replan
    route_reassess_replan    on_yes(REPLAN_TAIL) → check_replan_budget
                             on_no(ABORT)        → abort_composer
  check_replan_budget        on_yes(count<max)   → increment_replan_count
                             on_no/on_error      → abort_composer
  increment_replan_count     →                     apply_replan
  apply_replan               →                     validate_replan
  validate_replan            on_yes              → execute_plan
                             on_no/on_error      → abort_composer
```
The `output_numeric` budget gate now reads the count *before* increment on the
REPLAN branch, so `max_replans=2` permits exactly 2 replans; CONTINUE/ABORT
never reach it. MR-1 intent is preserved (the non-LLM gate remains in
`reassess`'s downstream chain, and the deterministic `parse_reassess_decision`
+ `route_*` states drive routing, not the LLM verdict).

### #3 + #4 — validate every replan
New `validate_replan` state reuses the `validate_plan` fragment over the merged
(succeeded + new tail) plan: rejects unknown loop names, node-cap violations,
cycles, and duplicate `step_id`s, and writes the Kahn-sorted `topo-order.json`.
`apply_replan` now drops any stale `topo-order.json` and lets the fragment own it.

### #5 — quoted-heredoc-to-file instead of Python-literal interpolation
Captures are in-memory only (`fsm/executor.py:1161-1167`), so each consuming
shell action now writes `${captured.X.output}` to a run-dir file via a quoted
heredoc (`<< 'DELIM'`, written literally — no escape/`"""` interpretation) and
Python reads it from disk. Proven to round-trip adversarial JSONL (embedded
`"""`, backslashes, quotes, `$var`, backticks) intact.

### #6 — drop dead evaluators
`decompose_goal` and `review_chain` use a plain `next:` (no `evaluate` block →
no LLM grading call fires, `executor.py:891-928`). `reassess`'s evaluator is
**kept** (intentional MR-1 coverage with a dedicated test).

### #7 — HITL fail-safe
`check_auto_plan` `on_error: execute_plan` → `on_error: present_plan`, matching
the static loop's [[ENH-2135]] fix.

### #8 — separate success from execution
`write_step_success` appends to **both** `completed-steps.txt` (cursor) and
`succeeded-steps.txt` (immutable boundary); `write_step_failed` appends to the
cursor only. `apply_replan` builds the immutable prefix from `succeeded-steps.txt`
and rewrites `completed-steps.txt` to the succeeded set, so a failed step is no
longer skipped and the new tail may retry it.

## Files Modified

- `scripts/little_loops/loops/loop-composer-adaptive.yaml` — #1, #2, #3/#4 (new
  `validate_replan`), #5 (5 shell states), #6, #7, #8.
- `scripts/little_loops/loops/lib/composer.yaml` — `{{step_id}}` wording +
  accurate immutability note in the `reassess` prompt; updated the fragment
  description to reflect the repositioned MR-1 gate.
- `scripts/little_loops/loops/loop-composer.yaml` — shared #1 and #5 fixes.
- `scripts/tests/test_loop_composer_adaptive.py` — rewired replan-flow
  assertions to the new graph; added `validate_replan` to `REQUIRED_STATES`;
  added tests for #8 (succeeded-tracking) and a #5 interpolation guard.
- `scripts/tests/test_loop_composer.py` — added the #5 interpolation guard.

## Verification

- `ll-loop validate loop-composer-adaptive` and `ll-loop validate loop-composer`
  — both valid, exit 0, no MR-1/MR-4 warnings; `validate_replan` present in the
  state graph.
- `python -m pytest scripts/tests/test_loop_composer_adaptive.py
  scripts/tests/test_loop_composer.py scripts/tests/test_builtin_loops.py` —
  **927 passed**.
- `ruff check` on the touched test files — clean.
- Isolated mechanics test confirming the #5 heredoc round-trips adversarial
  JSONL intact (the old `"""..."""` form corrupted it).
- `mypy` skipped intentionally: only YAML + test files changed (no
  `scripts/little_loops/` source), so it carries no signal.
- **Not run** (recommended live follow-up, billed LLM run): end-to-end
  `ll-loop run loop-composer-adaptive` on a 2-step goal with a deliberately
  failing step, confirming (a) `{{step_1}}` resolves in the dispatched input,
  (b) CONTINUE does not decrement the replan budget, (c) REPLAN_TAIL can
  re-include the failed step.

## Impact

Restores two broken core promises of the adaptive composer — cross-step data
flow (#1) and "retry the failed step via REPLAN_TAIL" (#8) — fixes a budget
accounting bug that halved the effective replan allowance and let CONTINUE
silently consume it (#2), hardens replans against malformed LLM tails (#3/#4),
eliminates a JSONL-corruption failure class (#5), removes a fail-open HITL
bypass (#7), and trims two wasted LLM grading calls per run (#6). Shared bugs
#1 and #5 are fixed in the static `loop-composer.yaml` as well.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-15T15:44:35 - `faceb11e-e2d7-4c0d-a89f-0bc95671d1c2.jsonl`

---
id: BUG-3220
type: BUG
title: Funnel judged gates route abstention into finalize_failed in composer and router
  loops
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:28:07Z'
parent: EPIC-3217
---

# BUG-3220: Funnel judged gates route abstention into finalize_failed in composer and router loops

## Summary

Ten LLM-judged gates in the built-in loops are *funnels*: `on_yes`, `on_no`, and `on_partial` all point at the same next state, because the LLM call produces an artifact (a plan, a classification, a score sheet) rather than judging a condition. The verdict is structurally irrelevant — every branch proceeds.

Since ENH-3185, abstention is the one verdict that does not follow the funnel. It escalates to `on_error` instead. For three of these gates, `on_error` is `finalize_failed`, so a state that structurally cannot fail today becomes a run-killer the first time a judge returns `cannot_judge`.

## Current Behavior

Funnel gates whose abstention path diverges from the funnel (`scripts/little_loops/loops/`):

| loop :: state | funnel target | abstention target |
|---|---|---|
| `goal-cluster` :: `dedup_and_batch` | `parse_batch_plan` | `finalize_failed` |
| `loop-composer` :: `decompose_goal` | `parse_plan` | `finalize_failed` |
| `loop-router` :: `classify_goal` | `route_branch_project` | `finalize_failed` |
| `goal-cluster` :: `propagate_context` | `save_hints` | `execute_cluster` |

The remaining six funnel gates — `goal-cluster::synthesize_cluster_result`, `loop-composer::review_chain`, `loop-router::score_project_loops`, `loop-router::score_builtin_loops`, `loop-router::review`, `migrate-sdk-version::classify_outcome` — happen to have an `on_error` that equals the funnel target, so they behave correctly today by coincidence rather than by declaration, and only after paying two holds first.

## Expected Behavior

A funnel gate funnels every verdict, abstention included. The downstream parse/consume state is already the component that handles a malformed or empty artifact; abstention should reach it the same way a `no` does, so the existing artifact-validation path gets to run instead of the loop failing upstream of it.

Where the parse state genuinely cannot tolerate an unproduced artifact, that is worth stating explicitly rather than inheriting a failure route written for infrastructure errors.

## Motivation

These four gates convert a working loop into a failing one on a verdict that carries no information about the artifact. The six coincidentally-correct gates additionally waste two re-runs of an LLM call per abstention. Both are cheap to fix and the fix is mechanical: one line per gate.

## Root Cause

- **File**: `scripts/little_loops/fsm/executor.py` (mechanism); the 9 in-scope gate declarations across `goal-cluster.yaml`, `loop-composer.yaml`, `loop-router.yaml` (site — see scope correction below)
- **Anchor**: `FSMExecutor._abstention_declared()` (2656-2667) treats `cannot_judge` as undeclared whenever a gate has no `on_cannot_judge`/`route.routes["cannot_judge"]`, regardless of whether the gate's other verdicts all funnel to the same target; `_abstention_fallback()` (2669-2681) then resolves via `state.on_error`/`route.error`, which was written for genuine infrastructure errors and, for the 4 diverging gates, happens to differ from the funnel target.
- **Cause**: These gates are funnels by design — `on_yes`/`on_no`/`on_partial` all point at one downstream parse/consume state because the LLM call produces an artifact (a plan, a classification) rather than judging a pass/fail condition. `cannot_judge` is structurally just another "the call happened, here's what came back" outcome for a funnel gate, but ENH-3185's abstention machinery does not know a state is a funnel — it always escalates an undeclared abstention to `on_error`, which for `dedup_and_batch`/`decompose_goal`/`classify_goal` is `finalize_failed` (not the funnel target) and for `propagate_context` is `execute_cluster` (not `save_hints`). A gate that structurally cannot fail today becomes a run-killer on its first `cannot_judge` verdict.
- **Scope correction**: the issue's table lists 10 gates, including `migrate-sdk-version.yaml::classify_outcome`. Verified this state's `evaluate:` block overrides the `llm_gate` fragment's default `type: llm_structured` to `type: output_contains` (`migrate-sdk-version.yaml:157-159`), and `evaluate_output_contains` (`scripts/little_loops/fsm/evaluators.py:436-490`) can only return `yes`/`no`/`error` — it cannot produce `cannot_judge`. This state does not participate in the abstention mechanism at all and is out of scope; the actual gate count for this fix is **9**, not 10.

## Proposed Solution

Declare `on_cannot_judge: <funnel target>` on all ten gates. A declared route fires immediately with no hold (ENH-3185 precedence), which removes both the spurious failures and the wasted retries.

Doing this on the six coincidentally-correct gates as well is deliberate: it converts an accident of the error route into a stated intent, so a later change to `on_error` cannot silently reintroduce the divergence.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Files to Modify
Verified against the issue's table (one correction below):

- `scripts/little_loops/loops/goal-cluster.yaml` — `dedup_and_batch` (192-195, funnel `parse_batch_plan`, `on_error: finalize_failed`), `propagate_context` (623-626, funnel `save_hints`, `on_error: execute_cluster`), `synthesize_cluster_result` (685-688, all four → `finalize_present_result`, coincidentally correct)
- `scripts/little_loops/loops/loop-composer.yaml` — `decompose_goal` (79-82, funnel `parse_plan`, `on_error: finalize_failed`), `review_chain` (464-467, all four → `finalize_present_result`, coincidentally correct)
- `scripts/little_loops/loops/loop-router.yaml` — `classify_goal` (115-118, funnel `route_branch_project`, `on_error: finalize_failed`), `score_project_loops` (171-174, all four → `parse_project_score`), `score_builtin_loops` (229-232, all four → `parse_builtin_score`), `review` (395-398, all four → `finalize_present_result`)
- `scripts/little_loops/loops/migrate-sdk-version.yaml` — `classify_outcome` (133-163) — **correction**: this state uses the `llm_gate` fragment (`scripts/little_loops/loops/lib/common.yaml:47-72`, which defaults `evaluate.type: llm_structured`), but its own `evaluate:` block overrides `type` to `output_contains, pattern: "CLASSIFY_JSON:"` (lines 157-159). Fragment merging (`_deep_merge`, `scripts/little_loops/fsm/fragments.py:43-63`) lets state-level keys win, so the merged type is `output_contains`. `evaluate_output_contains` (`scripts/little_loops/fsm/evaluators.py:436-490`) can only return `yes`/`no`/`error` — it structurally cannot produce `cannot_judge`, so this state does not actually participate in the abstention-hold/escalation behavior despite its four routes (`on_yes`/`on_no`/`on_blocked`/`on_error`, all → `apply_update`) otherwise looking like a funnel. **This state is out of scope for this issue's fix.**

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `_ABSTENTION_HOLD_CAP = 2` (2654), `_abstention_declared` (2656-2667), `_abstention_fallback` (2669-2681), `_route_abstention_hold` (2683-2697), and the abstention dispatch branch (2075-2085). No code changes needed — declaring `on_cannot_judge` per gate routes through the existing `extra_routes` mechanism with no hold.
- Downstream parse/consume states already validate malformed/empty artifacts independently of this fix and do not need to change:
  - `parse_batch_plan` (`goal-cluster.yaml:197-254`) — on unparseable JSON, prints an error and `sys.exit(1)`, routing via `on_error: finalize_failed` (no retry).
  - `parse_plan` (`loop-composer.yaml:86-145`) — same parse-failure shape, but routes via `on_error: re_decompose`, a bounded retry (`output_numeric lt 3`) back into `decompose_goal` before finally reaching `finalize_failed`.
  - `route_branch_project` (`loop-router.yaml:120-132`) — plain substring match (`'BRANCH:project' in output`); an empty/malformed classification falls through to `on_no: route_branch_builtin`, then to `propose_new_loop` — no explicit malformed-input branch needed since absence already reads as "no".
  - `save_hints` (`goal-cluster.yaml:628-661`) — on regex/parse failure, `new_hints` simply stays `[]`; always proceeds via unconditional `next: execute_cluster`.

### Conventions in Force
- No loop YAML in the repo declares `on_cannot_judge` today (grep-confirmed across all 91 files under `scripts/little_loops/loops/`).
- The schema mechanism that would accept it is a catch-all: `fsm-loop-schema.json`'s `stateConfig.patternProperties: {"^on_": {"type": "string", ...}}` (lines 686-692) already permits any `on_<verdict>` key; `StateConfig.extra_routes` (`fsm/schema.py:687,866`) is the dataclass-side counterpart.
- Inline `#` comments next to `on_*` routes in this codebase state the semantic reason for the branch, frequently citing the originating issue ID (e.g. `rn-decompose.yaml:82-83` `# partial = review ran with a caveat; proceed and log it (BUG-1975)`; `scan-and-implement.yaml:75-76` `# ENH-2825: a broken diff is not "nothing new"`). None of the four diverging funnel gates in this issue currently carry any inline comment on their `on_*` lines — a gap the fix should close, not just the missing route.
- The closest existing repo-wide, exemption-table-driven route-shape assertion is `test_loop_composer.py`/`test_builtin_loops.py`'s `test_no_failure_edge_routes_to_a_success_terminal`, which walks every built-in loop asserting `on_error`/`on_failure`/`on_retry_exhausted` never lands on a success terminal (with a hardcoded exemption dict citing `ENH-2365`/`ENH-2575`). No equivalent funnel-consistency assertion exists yet.

### Tests
- `scripts/tests/test_loop_composer.py:126-130` (`test_dispatch_step_routes_success_and_failure`) and `scripts/tests/test_loop_router.py:131-146` (`test_classify_goal_routes_to_branch_project`, `test_three_branch_targets_reachable_from_classify_goal`) hardcode literal route-target assertions for some of these states; `test_classify_goal_routes_to_branch_project` currently checks only `on_yes`/`on_no`, not `on_partial` or (yet) `on_cannot_judge`.
- `scripts/tests/test_builtin_loops.py:49-57` (`test_all_validate_as_valid_fsm`) is the generic "all loops validate" gate every changed file passes through; it is not funnel-aware.
- `scripts/little_loops/fsm/validation/*.py` contains no rule referencing `cannot_judge`/`abstention`/`funnel` (grep-confirmed) — `ENH-3222` (sibling issue) is the proposed validator rule; it does not exist yet, so no test currently enforces this issue's invariant.

### Documentation
N/A — no user-facing docs describe these four loops' abstention routing specifically; `docs/generalized-fsm-loop.md:547` documents the general `on_cannot_judge` mechanism only.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Decision Rules
- New routing decision this fix introduces, per gate: `on_cannot_judge: <target>` where `<target>` equals the gate's existing funnel target (the state its `on_yes`/`on_no`/`on_partial` already all share). Exact inputs: the 9 in-scope gates are `goal-cluster.yaml::dedup_and_batch` (target `parse_batch_plan`), `goal-cluster.yaml::propagate_context` (target `save_hints`), `goal-cluster.yaml::synthesize_cluster_result` (target `finalize_present_result`), `loop-composer.yaml::decompose_goal` (target `parse_plan`), `loop-composer.yaml::review_chain` (target `finalize_present_result`), `loop-router.yaml::classify_goal` (target `route_branch_project`), `loop-router.yaml::score_project_loops` (target `parse_project_score`), `loop-router.yaml::score_builtin_loops` (target `parse_builtin_score`), `loop-router.yaml::review` (target `finalize_present_result`).
- Escape hatch / exception: where the downstream parse state genuinely cannot tolerate an unproduced artifact, that is a case for a distinct `on_cannot_judge` target rather than the funnel — but this issue's own research (Integration Map above) found all four downstream consumers already validate malformed/empty artifacts independently (fail cleanly, bounded-retry, or degrade gracefully), so no gate in this set currently needs the exception.
- `migrate-sdk-version.yaml::classify_outcome` is excluded from this decision rule entirely per the Root Cause scope correction — its evaluator cannot produce `cannot_judge`, so no `on_cannot_judge` route is meaningful there.

### Types
N/A — no data shape introduced or modified; all 9 fixes are YAML routing-key additions.

### Signatures
- `FSMExecutor._abstention_declared(state: StateConfig, verdict: str) -> bool` — unaffected; a declared `on_cannot_judge` makes this return `True` for the `cannot_judge` verdict via the existing `extra_routes` check, which is what skips the hold.

### Call Path
`dedup_and_batch`/`decompose_goal`/`classify_goal`/`propagate_context` (llm_structured evaluate, funnel target ≠ on_error target) -> `FSMExecutor` abstention dispatch -> hold twice -> `finalize_failed`/`execute_cluster` is the current diverging path this issue closes. `FSMExecutor` (`scripts/little_loops/fsm/executor.py`) owns the dispatch, hold, and fallback logic uniformly; declaring `on_cannot_judge` per gate makes the abstention path match the funnel path exactly, with no hold.

## Implementation Steps

1. The 4 diverging gates (`goal-cluster::dedup_and_batch`, `loop-composer::decompose_goal`, `loop-router::classify_goal`, `goal-cluster::propagate_context`) each gain `on_cannot_judge: <their funnel target>`, closing the spurious-failure path first since these are the gates that convert a working loop into a failing one today.
2. The 5 coincidentally-correct in-scope gates (`goal-cluster::synthesize_cluster_result`, `loop-composer::review_chain`, `loop-router::score_project_loops`, `loop-router::score_builtin_loops`, `loop-router::review`) each gain `on_cannot_judge: <their funnel target>` too, per the Program Design decision rule — converting an accident of the error route into a stated intent and removing the two wasted holds per abstention.
3. `migrate-sdk-version.yaml::classify_outcome` is left unchanged — the Root Cause scope correction found its evaluator cannot produce `cannot_judge`, so no route is meaningful there.
4. Each changed route carries an inline `#` comment stating why abstention funnels the same way the other verdicts do, following this codebase's existing rationale-comment convention (Integration Map → Conventions in Force).
5. `python -m pytest scripts/tests/test_loop_composer.py scripts/tests/test_loop_router.py scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_executor.py -v` passes, and `ll-loop validate` runs clean against `goal-cluster.yaml`, `loop-composer.yaml`, and `loop-router.yaml`.

## Impact

Removes three spurious run failures, one spurious re-execution branch, and up to two wasted LLM calls per abstention on six further gates. No behavior change on the non-abstention paths.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.executor` section — abstention-hold
  and escalation-to-`on_error` mechanics that route funnel gates into `finalize_failed`
- `docs/ARCHITECTURE.md` `## Extension Architecture & Event Flow` — FSM executor
  state-transition and event-emission model

## Status

**Open** | Created: 2026-08-16 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-08-16T23:58:31 - `40668286-18e1-4fb3-b8c2-566405cf8bec.jsonl`
- `/ll:capture-issue` - 2026-08-16T23:29:37 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`

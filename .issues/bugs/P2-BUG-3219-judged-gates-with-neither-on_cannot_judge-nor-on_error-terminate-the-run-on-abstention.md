---
id: BUG-3219
type: BUG
title: Judged gates with neither on_cannot_judge nor on_error terminate the run on
  abstention
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:27:46Z'
parent: EPIC-3217
---

# BUG-3219: Judged gates with neither on_cannot_judge nor on_error terminate the run on abstention

## Summary

Thirteen LLM-judged gates in the built-in loops declare neither `on_cannot_judge` nor `on_error`. When such a gate abstains, `FSMExecutor` holds the state twice and then calls `_abstention_fallback()`, which returns `None` because there is no error route to resolve — and `_route()` returning `None` terminates the run via `_finish("error", "No valid transition")`.

ENH-3185 accepted this outcome as "loud rather than silent", and as a default that is correct. But three of the thirteen are the `harness-*` templates that `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` tells users to copy, so the shape propagates into every user-authored harness.

## Current Behavior

Gates with neither route (`scripts/little_loops/loops/`):

| loop | state |
|---|---|
| `harness-single-shot.yaml` | `check_semantic` |
| `harness-multi-item.yaml` | `check_semantic`, `check_skill` |
| `harness-plan-research-implement-report.yaml` | `check_semantic` |
| `rn-build.yaml` | `check_substrate` |
| `rn-plan.yaml` | `check_substrate` |
| `integrate-sdk.yaml` | `enumerate_from_code`, `enumerate_from_docs` |
| `adopt-third-party-api.yaml` | `enumerate` |
| `assumption-firewall.yaml` | `extract_assumptions` |
| `dataset-curation.yaml` | `validate_schema` |
| `incremental-refactor.yaml` | `check_complete` |
| `loop-specialist-eval.yaml` | `check_skill` |

A run reaching any of these and abstaining dies after three attempts with "No valid transition".

There is a cost dimension as well. `_route_abstention_hold()` re-enters the *state*, not just the evaluator, so the state's action re-runs on each hold. For `check_skill` — an agentic user-simulation gate documented at 30–300s — an undeclared abstention buys two full re-simulations before the run terminates anyway.

## Expected Behavior

Each of these gates routes abstention somewhere deliberate. The right destination is per-gate and is not uniformly "retry the work":

- `check_semantic` in the harness templates: abstention means the judge could not see the evidence. The productive route is a state that *produces* the missing evidence (re-run with artifact capture, widen the diff scope), not `execute`, which redoes work the judge already could not observe.
- `rn-build` / `rn-plan` `check_substrate`: "does the substrate exist" is deterministically probe-able. Abstention should run a probe rather than guess `design_artifacts`.
- `loop-specialist-eval` / `harness-multi-item` `check_skill`: declare an explicit route so the expensive hold is skipped entirely.
- The extraction-shaped gates (`enumerate*`, `extract_assumptions`, `validate_schema`, `check_complete`) may legitimately funnel abstention to the same target as their other verdicts — see the sibling funnel-gate issue for that pattern.

## Motivation

The templates are the propagation vector. Fixing the three `harness-*` files stops the defect from being copied forward; fixing the remaining ten removes latent run-terminations from loops that are shipped as working.

## Root Cause

- **File**: `scripts/little_loops/fsm/executor.py` (mechanism); 13 gate declarations across the 11 loop files listed in Current Behavior (site)
- **Anchor**: `FSMExecutor._route()` (2699-2752) has no dedicated shorthand branch for `cannot_judge` — it only resolves via `extra_routes`/`route.routes`, both of which require the loop author to have declared the key; `FSMExecutor._abstention_fallback()` (2669-2681) returns `None` when neither `route.error` nor `on_error` is set; the main execution loop's `next_state is None` branch (758-774) calls `self._finish("error", error="No valid transition")`.
- **Cause**: Each of the 13 named gates was authored before ENH-3185 introduced the `cannot_judge` verdict (or was authored after without the new key in mind) and declares only `on_yes`/`on_no`(/`on_partial`) — the pre-ENH-3185 verdict set. None declares `on_error` either, so an abstaining judge has no declared exit: it holds twice via `_route_abstention_hold()` (2683-2697, `_ABSTENTION_HOLD_CAP = 2`), re-running the state's action each hold, then `_abstention_fallback()` finds no route and the run terminates loudly. This is "correct" per ENH-3185's design (loud beats silent), but three of the 13 sites are the `harness-*` templates `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` tells users to copy, so the gap propagates into user-authored harnesses.

## Proposed Solution

Work gate by gate rather than applying one blanket route. For each, decide what unobservability means at that point in the loop, declare `on_cannot_judge` accordingly, and where the answer is genuinely "we cannot proceed", route to a failure-shaped terminal so the run reports `failed` rather than dying on an unroutable verdict.

Update the harness templates' inline comments to show the `on_cannot_judge` line alongside the existing `on_partial` self-hold, since those comments are the de facto documentation for the pattern.

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
All 13 gates confirmed present exactly as the issue's table states, each `evaluate.type: llm_structured` with `on_yes`/`on_no`(`/on_partial`) but no `on_cannot_judge` and no `on_error`:

- `scripts/little_loops/loops/harness-single-shot.yaml` — `check_semantic` (lines 136-154)
- `scripts/little_loops/loops/harness-multi-item.yaml` — `check_skill` (122-139), `check_semantic` (141-159)
- `scripts/little_loops/loops/harness-plan-research-implement-report.yaml` — `check_semantic` (135-151)
- `scripts/little_loops/loops/rn-build.yaml` — `check_substrate` (382-396)
- `scripts/little_loops/loops/rn-plan.yaml` — `check_substrate` (152-168)
- `scripts/little_loops/loops/integrate-sdk.yaml` — `enumerate_from_code` (48-82), `enumerate_from_docs` (86-122) — both funnel `on_yes`/`on_no`/`on_partial` to `prove`
- `scripts/little_loops/loops/adopt-third-party-api.yaml` — `enumerate` (25-61) — funnels to `prove`
- `scripts/little_loops/loops/assumption-firewall.yaml` — `extract_assumptions` (25-56) — funnels to `parse_assumptions`
- `scripts/little_loops/loops/dataset-curation.yaml` — `validate_schema` (169-186)
- `scripts/little_loops/loops/incremental-refactor.yaml` — `check_complete` (44-52)
- `scripts/little_loops/loops/loop-specialist-eval.yaml` — `check_skill` (42-64)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `_route()` (2699-2752, no dedicated `cannot_judge` shorthand branch — only resolves via `extra_routes`/route-table), `_abstention_fallback()` (2669-2681, returns `None` when neither `route.error` nor `on_error` is set), `_route_abstention_hold()`/`_ABSTENTION_HOLD_CAP=2` (2683-2697), and the main execution loop (758-774) that calls `self._finish("error", error="No valid transition")` when `next_state is None`. None require code changes — the fix is per-loop YAML routes.
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — the documented source that users copy the three `harness-*.yaml` templates from; the propagation vector named in this issue's Motivation.
- Evidence sources each gate judges (for the "what does abstention mean here" design call): `check_semantic` states judge `${captured.execute_result.output}` (the prior action's stdout); `check_substrate` states judge `${captured.design_artifacts.output}`/`${captured.plan_for_substrate.output}` (a plan/design doc); `check_skill` states judge either a skill invocation's raw output or (loop-specialist-eval) `${captured.agent_run.output}` (an agent transcript); the `enumerate*`/`extract_assumptions`/`validate_schema`/`check_complete` gates judge their own immediately-preceding action's freeform output for a tagged-JSON sentinel or pass/fail report.

### Conventions in Force
- `on_partial` is the last routing line in every existing gate that has it (evidence: `harness-single-shot.yaml:136-154`'s `check_semantic` itself — the exact defect state — ends its route block at `on_partial` with no `on_error` line at all; contrast `fix-quality-and-tests.yaml:25-28` and `openscad-model-generator.yaml:131-134`, which both add an explicit `on_error` after `on_partial`). A new `on_cannot_judge` line belongs in that same run, per `docs/generalized-fsm-loop.md:547`'s documented convention ("same as `on_blocked`").
- Failure-shaped terminals in this codebase pair `terminal: true` with `failure: true`, name varies by loop (`failed`, `build_failed`, `<phase>_failed`, `blocked`, `abort_<phase>`); the pairing is enforced by convention, not schema (`rn-build.yaml:1255-1258` documents that `FAILURE_TERMINAL_NAMES` only *defaults* the flag for legacy names — new names must set `failure: true` explicitly).
- No existing loop state is a named "capture evidence and re-run the judge" phase — the nearest structural precedents for the `check_semantic` fix direction are `rn-build.yaml:308-336`'s `check_research_written` (probes whether an upstream prompt's expected artifact exists, writes a placeholder stub if not) and `rn-build.yaml:1231-1250`'s `finalize_build_failed` (reads run-dir state before declaring failure) — both "read what evidence actually exists" rather than blindly re-running.
- Deterministic existence/capability probes in this codebase are plain `action_type: shell` states using `command -v`/file-existence tests, evaluated with `type: exit_code` or `type: output_contains` — never `llm_structured` (evidence: `cua-agent-desktop.yaml:101-118` `check_install`, `cua-agent-desktop.yaml:125-152` `check_permissions`, `rn-build.yaml:108-128` `check_structure`, `rn-build.yaml:155-171` `verify_structure`). `rn-build.yaml`'s own `check_substrate` (382-396, the exact state this issue names) is *not* built this way — it is an `llm_structured` judge, the target of the fix rather than an example of the deterministic pattern.
- `on_cannot_judge` appears in zero loop YAML files today (grep-confirmed across `scripts/little_loops/loops/**`); the only concrete YAML shape in the repo is the test fixture in `scripts/tests/test_fsm_executor.py:1895-1921` (`extra_routes={"cannot_judge": "abstained"}`).

### Tests
- `scripts/tests/test_fsm_executor.py` — `TestAbstentionRouting` (from 1882), specifically `test_undeclared_cannot_judge_shorthand_no_on_error_terminates_loud` (1953) exercises exactly the neither-declared shape this issue describes, but at the `FSMExecutor`/`StateConfig` unit level, not against any of the 11 named loop files.
- `scripts/tests/test_fsm_schema.py:1091` `test_on_partial_only_shorthand_is_valid` confirms today's static validator does **not** flag "judged gate with no `on_cannot_judge`/`on_error`" as an error or warning — no existing test would catch a regression here; `ENH-3222` (sibling issue) is the proposed validator rule for this gap.
- `scripts/tests/test_builtin_loops.py` — `TestBuiltinLoopFiles` walks every loop under `scripts/little_loops/loops/`; this is the file-level harness that would enumerate all 13 gates for a corpus-wide route-completeness check, distinct from the hand-built fixtures in `test_fsm_executor.py`.

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` and the inline `#` comments in the three `harness-*.yaml` templates are the de facto documentation for this pattern per the issue's own Proposed Solution — both need the `on_cannot_judge` line added alongside the existing `on_partial` comment once the fix lands.
- `docs/generalized-fsm-loop.md:547` already documents the general `on_cannot_judge` mechanism; no change needed there.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Decision Rules
Per-gate abstention destinations this issue's Expected Behavior section calls for (exact inputs: the gate's verdict enum `{yes, no, partial, cannot_judge, cannot_judge_uncertain}`, decided per gate rather than one blanket rule):
- `check_semantic` in the three `harness-*` templates: route to a state that *produces* the missing evidence (re-run with artifact capture, widen the diff scope) — not `execute`, which redoes work the judge already could not observe. No such evidence-producing state exists in the codebase today (see Conventions in Force); the implementer names a new one.
- `rn-build.yaml`/`rn-plan.yaml` `check_substrate`: route to a deterministic probe state (shell/`exit_code`, following the `check_install`/`check_structure` shape in Conventions in Force) rather than guessing `design_artifacts`. No such probe state exists yet for substrate checks; the implementer creates one.
- `loop-specialist-eval.yaml`/`harness-multi-item.yaml` `check_skill`: declare an explicit `on_cannot_judge` route so the expensive hold (agentic re-simulation, documented 30-300s) is skipped entirely — the target state is the implementer's call, but skipping the hold is the fixed requirement.
- The extraction-shaped gates (`enumerate_from_code`, `enumerate_from_docs`, `enumerate`, `extract_assumptions`, `validate_schema`, `check_complete`) may fold `on_cannot_judge` into the same funnel target their other verdicts already share — see the sibling funnel-gate issue (BUG-3220) for that pattern; this is a legitimate exception to "decide per gate," not a contradiction of it.
Escape hatch: where a gate's decided answer is genuinely "we cannot proceed," `on_cannot_judge` targets a failure-shaped terminal (`terminal: true`, `failure: true`) rather than leaving the gate to terminate the whole run via "No valid transition."

### Types
N/A — no data shape introduced or modified; all 13 fixes are YAML routing-key additions.

### Signatures
- `FSMExecutor._route(state: StateConfig, verdict: str, ctx: InterpolationContext) -> str | None` — unaffected; a declared `on_cannot_judge` resolves through this function's existing `extra_routes` fallback, same mechanism `on_blocked` uses today.

### Call Path
`check_semantic`/`check_substrate`/`check_skill`/`enumerate*` (llm_structured evaluate, no route declared) -> `FSMExecutor` abstention dispatch -> hold twice -> "No valid transition" termination is the current path this issue closes per gate. `FSMExecutor` (`scripts/little_loops/fsm/executor.py`) owns the dispatch, hold, and fallback logic uniformly across all 13 sites; only the loop YAML routing keys differ per gate.

## Implementation Steps

1. The three `harness-*` template `check_semantic` states gain `on_cannot_judge` routes to an evidence-producing state (per the Decision Rules in Program Design), and their inline `#` comments document the new route the same way the existing `on_partial` self-hold is commented — this closes the propagation vector first.
2. `rn-build.yaml`/`rn-plan.yaml`'s `check_substrate` states gain `on_cannot_judge` routes to a deterministic probe state, modeled on the existing `check_install`/`check_structure` shell+`exit_code` shape rather than another `llm_structured` guess.
3. `loop-specialist-eval.yaml`/`harness-multi-item.yaml`'s `check_skill` states gain an explicit `on_cannot_judge` route so the two-hold agentic re-simulation cost is skipped.
4. The six extraction-shaped gates (`enumerate_from_code`, `enumerate_from_docs`, `enumerate`, `extract_assumptions`, `validate_schema`, `check_complete`) gain `on_cannot_judge` routes, each to its own gate's existing funnel target (consistent with BUG-3220's pattern for gates where the verdict is structurally irrelevant).
5. Every changed state where the answer is "we cannot proceed" routes to a `terminal: true` / `failure: true` state, not left to die on "No valid transition".
6. `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_executor.py -v` passes, and `ll-loop validate` runs clean against each of the 11 changed loop files.

## Impact

Removes 13 latent run-terminations and stops the no-route shape from propagating into user harnesses via the documented templates.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.executor` / `little_loops.fsm.validation`
  sections — `_abstention_fallback()` semantics and the MR rule set
- `.claude/CLAUDE.md` `## Loop Authoring` — meta-loop shape rules referenced by
  `ll-loop validate`, and the harness-template guide these gates propagate into

## Status

**Open** | Created: 2026-08-16 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-08-16T23:56:52 - `40668286-18e1-4fb3-b8c2-566405cf8bec.jsonl`
- `/ll:capture-issue` - 2026-08-16T23:29:36 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`

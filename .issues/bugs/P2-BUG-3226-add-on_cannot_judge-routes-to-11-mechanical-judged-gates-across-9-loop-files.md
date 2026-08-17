---
id: BUG-3226
type: BUG
title: Add on_cannot_judge routes to 11 mechanical judged gates across 9 loop files
priority: P2
testable: true
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
parent: EPIC-3217
supersedes: [BUG-3219]
---

# BUG-3226: Add on_cannot_judge routes to 11 mechanical judged gates across 9 loop files

## Summary

Eleven of the thirteen judged gates named in BUG-3219 declare neither `on_cannot_judge`
nor `on_error`. When such a gate abstains, `FSMExecutor` holds the state twice and then
terminates the run via `_finish("error", "No valid transition")`. For these eleven gates
the fix is a route addition rather than new machinery — as distinct from `check_substrate`
(`rn-build.yaml`/`rn-plan.yaml`), which needs a brand-new deterministic probe state and is
tracked separately in BUG-3227.

"Route addition" is not the same as "purely mechanical" for all eleven. Nine route to a
target that already exists. **Three files have no failure terminal at all and need one
added** (`harness-plan-research-implement-report.yaml`, `loop-specialist-eval.yaml`,
`dataset-curation.yaml`), and **two gates require a per-gate judgement call because they are
not funnel-shaped** (`validate_schema`, `check_complete` — see Expected Behavior). Treating
those two as funnels routes an abstention into a repair loop that re-enters the same
abstaining judge; that is the specific mistake this issue exists to avoid.

## Parent Issue

Supersedes BUG-3219 (decomposed): Judged gates with neither on_cannot_judge nor on_error
terminate the run on abstention. BUG-3227 is the sibling successor.

Relationship to BUG-3228 (`_uncertain` suffix fallback): independent, per EPIC-3217
Sequencing. This issue declares `on_cannot_judge` only, exactly as written, and needs no
revision when BUG-3228 lands — at which point `cannot_judge_uncertain` inherits these same
routes automatically.

## Current Behavior

Gates with neither route, in scope for this issue:

| loop | state |
|---|---|
| `harness-single-shot.yaml` | `check_semantic` |
| `harness-multi-item.yaml` | `check_semantic`, `check_skill` |
| `harness-plan-research-implement-report.yaml` | `check_semantic` |
| `integrate-sdk.yaml` | `enumerate_from_code`, `enumerate_from_docs` |
| `adopt-third-party-api.yaml` | `enumerate` |
| `assumption-firewall.yaml` | `extract_assumptions` |
| `dataset-curation.yaml` | `validate_schema` |
| `incremental-refactor.yaml` | `check_complete` |
| `loop-specialist-eval.yaml` | `check_skill` |

Out of scope: `rn-build.yaml`/`rn-plan.yaml` `check_substrate` (BUG-3227).

## Steps to Reproduce

1. Pick any gate from the table above, e.g. `integrate-sdk.yaml`'s `enumerate_from_code`.
2. Drive its `llm_structured` judge to return `{"verdict": "cannot_judge", ...}` — either by
   running the loop against input the criterion cannot be evaluated from, or by unit-driving
   `FSMExecutor` with a stubbed evaluator (the shape `TestAbstentionRouting`,
   `scripts/tests/test_fsm_executor.py:1882`, already uses).
3. Observe the state re-enter itself twice (`_ABSTENTION_HOLD_CAP`), then the run terminate
   with `status="error"`, `error="No valid transition"` — rather than routing anywhere.

## Impact

Eleven gates across nine built-in loops kill their run on any abstention. Because
`harness-single-shot.yaml`, `harness-multi-item.yaml`, and
`harness-plan-research-implement-report.yaml` are the templates users copy per
`docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`, the defect propagates into every
harness a user scaffolds. The failure surfaces as a generic "No valid transition" with no
indication that a judge abstained, so it reads as an FSM authoring bug rather than an
unevaluable criterion. Until ENH-3185's abstention grammar has routes to land on, the
feature's benefit remains theoretical for these gates.

## Expected Behavior

- `check_semantic` in the three `harness-*` templates: route `on_cannot_judge` to the
  loop's failure terminal (`failed` in `harness-single-shot.yaml` and
  `harness-multi-item.yaml`; a new failure terminal must be added to
  `harness-plan-research-implement-report.yaml`, which today has only `done`), following
  the `check_invariants`/ENH-2825 precedent at `harness-single-shot.yaml:170`
  (`on_error: failed  # ENH-2825: an uncheckable invariant is not a pass`). Do not route
  back into `check_semantic` itself or into `execute` — see BUG-3219's Expected Behavior
  for the reasoning against both.
- `loop-specialist-eval.yaml`/`harness-multi-item.yaml` `check_skill`: declare an explicit
  `on_cannot_judge` route so the expensive two-hold agentic re-simulation (documented
  30-300s) is skipped entirely. `loop-specialist-eval.yaml` has no failure terminal today
  and needs one added if that is the chosen destination.
- The **four** genuinely funnel-shaped extraction gates fold `on_cannot_judge` into the
  single target their other verdicts already share. Verified as true funnels (all of
  `on_yes`/`on_no`/`on_partial` pointing at one state):

  | gate | funnel target |
  |---|---|
  | `integrate-sdk.yaml` `enumerate_from_code` (80-82) | `prove` |
  | `integrate-sdk.yaml` `enumerate_from_docs` (120-122) | `prove` |
  | `adopt-third-party-api.yaml` `enumerate` (59-61) | `prove` |
  | `assumption-firewall.yaml` `extract_assumptions` (54-56) | `parse_assumptions` |

  See the sibling funnel-gate issue BUG-3220 for this pattern.

- `validate_schema` and `check_complete` are **not** funnels and must not be folded. Their
  verdicts diverge, so "the target their other verdicts already share" is undefined, and the
  target they *partially* share is the repair branch:

  | gate | routing today |
  |---|---|
  | `dataset-curation.yaml` `validate_schema` (186-188) | `on_yes: publish`, `on_no`/`on_partial`: `fix_item` |
  | `incremental-refactor.yaml` `check_complete` (51-53) | `on_yes: done`, `on_no`/`on_partial`: `execute_step` |

  Routing `cannot_judge` to `fix_item`/`execute_step` sends an abstention into a repair loop
  that re-enters the same abstaining judge on the next pass — an unbounded cycle capped only
  by the loop's `max_iterations`, which reports as a limit failure rather than the real
  cause. Both must instead be fail-closed to a failure terminal, consistent with EPIC-3217
  decision (b) ("`failure: true` remains the FSM's only non-success terminal shape —
  fail-closed, which is the right default for gates"):
  - `check_complete` → `failed` (`incremental-refactor.yaml:69`, already `terminal: true` +
    `failure: true`).
  - `validate_schema` → a **new** failure terminal; `dataset-curation.yaml` has only `done`
    (205-206) today.
- Every changed state where the answer is "we cannot proceed" routes to a `terminal:
  true` / `failure: true` state, not left to die on "No valid transition". This requires
  adding a failure terminal to three files that have none:
  `harness-plan-research-implement-report.yaml` (only `done`, 176),
  `loop-specialist-eval.yaml` (only `done`, 66-67), and `dataset-curation.yaml` (only
  `done`, 205-206).
- `adopt-third-party-api.yaml`'s existing `failed` terminal (140-141) declares only
  `terminal: true` and is missing `failure: true`, unlike every other failure terminal in
  the corpus. Fix it as part of this change rather than propagating the outlier.
- Update the harness templates' inline `#` comments to show the `on_cannot_judge` line
  alongside the existing `on_partial` self-hold, since those comments are the de facto
  documentation for the pattern (`docs/generalized-fsm-loop.md:547`).

## Root Cause

Each named gate was authored before ENH-3185 introduced the `cannot_judge` verdict (or
authored after without the new key in mind) and declares only `on_yes`/`on_no`(`/on_partial`).
None declares `on_error` either, so `FSMExecutor._abstention_fallback()`
(`scripts/little_loops/fsm/executor.py:2669-2681`) returns `None`, and the main execution
loop's `next_state is None` branch (758-774) calls `self._finish("error", error="No valid
transition")`. No executor code changes are required — the fix is per-loop YAML routes.

## Proposed Solution

Work gate by gate, in three groups:

1. **`check_semantic` × 3 (harness templates)** — `on_cannot_judge: failed`, adding a
   `failed` terminal to `harness-plan-research-implement-report.yaml`.
2. **`check_skill` × 2** — explicit `on_cannot_judge` route bypassing the expensive
   two-hold agentic re-simulation; `loop-specialist-eval.yaml` needs a failure terminal
   added.
3. **Extraction-shaped gates × 6** — the *four* true funnels fold into their existing funnel
   target; `validate_schema` and `check_complete` route fail-closed to a failure terminal
   (new one for `dataset-curation.yaml`; existing `failed` for `incremental-refactor.yaml`).

Plus the `adopt-third-party-api.yaml` `failed`-terminal `failure: true` correction.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/loops/harness-single-shot.yaml` — `check_semantic` (136-154) declares `on_yes`/`on_no`/`on_partial` only; a `failed` terminal already exists (174-177, `terminal: true`/`failure: true`, ENH-2825 comment) and is already the `on_error` target of sibling gates `check_stall` (54) and `check_invariants` (169) in this same file.
- `scripts/little_loops/loops/harness-multi-item.yaml` — `check_skill` (122-139) and `check_semantic` (141-159) both lack `on_error`/`on_cannot_judge`; `failed` terminal exists (189-191) and is already `discover`'s `on_error` target (57).
- `scripts/little_loops/loops/harness-plan-research-implement-report.yaml` — `check_semantic` (135-151) lacks both routes. No `failed`/`blocked` terminal exists anywhere in this file — only `done` (175, `terminal: true`). Every other gate's `on_error` in this file (`check_stall`, `check_concrete`, `check_invariants`) routes to `report` (116, 164), not to a dedicated failure terminal.
- `scripts/little_loops/loops/loop-specialist-eval.yaml` — `check_skill` (42-64) lacks both routes. Only one terminal exists in the whole file, `done` (66-67) — no failure terminal, and no funnel alternative besides `execute` (the existing `on_no`/`on_partial` target).
- `scripts/little_loops/loops/integrate-sdk.yaml` — `enumerate_from_code` (48-82) and `enumerate_from_docs` (86-122) already funnel `on_yes`/`on_no`/`on_partial` to `prove`. A `blocked` terminal exists (235-237, `terminal: true`/`failure: true`), reached today via `diagnose_and_block` (133).
- `scripts/little_loops/loops/adopt-third-party-api.yaml` — `enumerate` (25-61) already funnels all three verdicts to `prove`. `failed` terminal exists (140-141) but declares only `terminal: true` — it omits `failure: true`, unlike every other failure terminal cited above; `scrape`'s `on_error: failed` (22) already targets it.
- `scripts/little_loops/loops/assumption-firewall.yaml` — `extract_assumptions` (25-56) already funnels all three verdicts to `parse_assumptions`. `blocked` terminal exists (186-188, `terminal: true`/`failure: true`), already targeted by `read_issue`'s `on_error: blocked` (22) and others.
- `scripts/little_loops/loops/dataset-curation.yaml` — `validate_schema` (169-186) lacks both routes; `on_no`/`on_partial` both go to `fix_item`. Only one terminal in the file, `done` (205-206) — no failure/blocked terminal exists at all, and no test class (`TestDatasetCurationLoop`) exists today.
- `scripts/little_loops/loops/incremental-refactor.yaml` — `check_complete` (44-52) lacks both routes. `failed` terminal exists (69), already targeted by `replan`'s `on_retry_exhausted: failed` (63).
- `skills/create-loop/loop-types.md` — `check_semantic`/`check_skill` scaffolding templates (Variant A, Variant B, `harness-refine-issue` example) omit `on_cannot_judge` from the routing keys shown.
- `skills/create-loop/reference.md` — routing-key field reference omits `on_cannot_judge`.

### Dependent Files (Callers/Importers)
- No Python callers of these loop YAML files beyond the FSM loader — `FSMExecutor._abstention_fallback()` (`scripts/little_loops/fsm/executor.py:2669-2681`) is the sole consumer of the routing gap; it requires no code changes (confirmed: `state.on_error` shorthand already resolves via `_resolve_route`, and `StateConfig._from_dict()` already collects unrecognized `on_*` keys — including `on_cannot_judge` — into `extra_routes`, and `fsm-loop-schema.json`'s `stateConfig.patternProperties: "^on_"` already accepts it; BUG-3221, which would have added explicit schema support, is cancelled as unnecessary).

### Conventions in Force
- An abstention/error path meaning "we cannot proceed" routes to a state literally named `failed` (or, in `integrate-sdk.yaml`/`assumption-firewall.yaml`, `blocked`) declared with `terminal: true` and `failure: true` together — evidence: `harness-single-shot.yaml:174-177`, `harness-multi-item.yaml:189-191`, `incremental-refactor.yaml:69`, `integrate-sdk.yaml:235-237`, `assumption-firewall.yaml:186-188`. This is not applied uniformly even within one file — `harness-multi-item.yaml`'s own `check_invariants` routes `on_error: advance` (173), not to `failed`.
- Routing lines conventionally carry an inline `#` comment naming the semantic reason and originating issue ID — evidence: `harness-single-shot.yaml:41,54,169` (`# ENH-2825: ...`), `rn-decompose.yaml:82-83` (`# partial = ... (BUG-1975)`, `# no = ... (ENH-1977)`).
- Funnel-shaped gates (all verdicts routing to one shared parse/consume target) are the existing shape for the six extraction-type gates in this issue's scope — evidence: `integrate-sdk.yaml:80-82,120-122`, `adopt-third-party-api.yaml:59-61`, `assumption-firewall.yaml:54-56`, each showing `on_yes`/`on_no`/`on_partial` all pointing at the same target.
- No built-in loop declares `on_cannot_judge` today — grep-confirmed zero matches across all 91 files under `scripts/little_loops/loops/`, so there is no existing route line to copy verbatim; the nearest structural analogs are the `on_error`-shorthand and funnel-routing conventions above.
- `adopt-third-party-api.yaml`'s `failed` terminal (140-141) is the one outlier that omits `failure: true` — a disagreement with the `terminal: true` + `failure: true` pairing used everywhere else, worth resolving consistently rather than copying the outlier.

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestAssumptionFirewallLoop` (10239), `TestAdoptThirdPartyApiLoop` (10748), `TestIntegrateSdkLoop` (10815), `TestIncrementalRefactorLoop` (11166), `TestHarnessCapture` (2902, currently parametrized only over `harness-single-shot.yaml`/`harness-multi-item.yaml` via its `HARNESS_FILES` list). No test in this file currently asserts an `on_cannot_judge` value anywhere (grep-confirmed) — the nearest precedent shape is the flat `state.get("on_error") == "target"` / `state.get("terminal") is True` assertions used throughout (e.g. `:1394`, `:1787`, `:2897`).
- `scripts/tests/test_feat1544_loop_specialist_eval.py` — `TestLoopSpecialistEvalStates` (68).
- No dedicated test class exists yet for `dataset-curation.yaml` — `TestIncrementalRefactorLoop`'s `data["states"]["<name>"].get(...)` shape is the closest model to build a new `TestDatasetCurationLoop` class from.
- `TestValidatorWarningBudget` (13779-13907) is the corpus-wide lint ratchet gating `ll-loop validate` warnings; its `ALLOWLIST` keys on `(loop stem, category)` and requires a comment citing the owning issue if a new warning must be suppressed rather than fixed.

### Documentation
- `docs/generalized-fsm-loop.md:547` — documents the `cannot_judge`/`on_cannot_judge` mechanism in prose; is the "de facto documentation for the pattern" the issue's Expected Behavior refers to for inline-comment updates.
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — documented source users copy the three `harness-*.yaml` templates from.

## Program Design

### Signatures
- `FSMExecutor._abstention_declared(state: StateConfig, verdict: str) -> bool` — the dispatch gate; becomes `True` once a state declares `on_cannot_judge`, which is exactly what this issue's routes add, sending the abstention through the normal `_route()` path instead of the hold-then-fallback path; see `scripts/little_loops/fsm/executor.py:2656-2667`.
- `FSMExecutor._route_abstention_hold(state: StateConfig, state_name: str, ctx: InterpolationContext) -> str | None` — re-enters the same state up to `_ABSTENTION_HOLD_CAP` (2) times before calling `_abstention_fallback`; see `scripts/little_loops/fsm/executor.py:2683-2697`.
- `FSMExecutor._abstention_fallback(state: StateConfig, ctx: InterpolationContext) -> str | None` — the on_error-equivalent fallback checked once the hold cap is exhausted; returns `route.error`, else `on_error`, else `None`, and never `route.default` or an implicit `on_no`; see `scripts/little_loops/fsm/executor.py:2669-2681`.

### Types
N/A — no new data shape; this issue adds routing keys (`on_cannot_judge: <state_name>`) to existing `StateConfig` YAML dicts. `StateConfig._from_dict()` (`scripts/little_loops/fsm/schema.py`) already collects unrecognized `on_*` keys into `extra_routes`, and `fsm-loop-schema.json`'s `stateConfig.patternProperties: "^on_"` already accepts the key — no schema change needed (BUG-3221, which would have added explicit support, is cancelled as unnecessary).

### Call Path
`FSMExecutor` main loop → judge evaluates `evaluate.type: llm_structured` state, returns `cannot_judge` verdict → `_abstention_declared(state, "cannot_judge")` checks for `on_cannot_judge`/`route.routes["cannot_judge"]` on the 11 named states (currently absent in all 11) → `_route_abstention_hold()` holds up to 2× → `_abstention_fallback()` checks `state.on_error` (absent in all 11) → returns `None` → main loop's `next_state is None` branch (`:758-774`, no summary/iteration-cap state active) → `self._finish("error", error="No valid transition")`, terminating the run. Adding `on_cannot_judge: <target>` to each of the 11 states makes `_abstention_declared()` return `True` for that state, routing the abstention through the normal `_route()` path to `<target>` instead — no executor code changes required, only per-loop YAML additions.

### Decision Rules
N/A — no new decision logic. This issue applies an existing, already-implemented verdict/routing mechanism (`cannot_judge`, ENH-3185) to gates that omitted a route for it; it does not introduce a new gap kind, gate, threshold, or classification rule.

## Implementation Steps

1. The three `harness-*` template `check_semantic` states gain `on_cannot_judge` routes to
   the loop's failure terminal (adding one to
   `harness-plan-research-implement-report.yaml`), with inline comments documenting the
   route per the ENH-2825 rationale.
2. `loop-specialist-eval.yaml`/`harness-multi-item.yaml`'s `check_skill` states gain an
   explicit `on_cannot_judge` route (`loop-specialist-eval.yaml` needs a failure terminal
   added if routing there).
3. The four true funnel gates (`enumerate_from_code`, `enumerate_from_docs`, `enumerate`,
   `extract_assumptions`) gain `on_cannot_judge` routes to their existing funnel targets
   (`prove`, `prove`, `prove`, `parse_assumptions`).
4. `check_complete` (`incremental-refactor.yaml`) gains `on_cannot_judge: failed`, and
   `validate_schema` (`dataset-curation.yaml`) gains `on_cannot_judge` to a newly added
   `failure: true` terminal — neither routes into its repair branch (`execute_step` /
   `fix_item`), per Expected Behavior.
5. Every changed state where the answer is "we cannot proceed" routes to a `terminal:
   true` / `failure: true` state, and `adopt-third-party-api.yaml`'s `failed` terminal
   (140-141) gains the missing `failure: true`.
6. Update `skills/create-loop/loop-types.md`'s `check_semantic`/`check_skill` scaffolding
   templates (Variant A, Variant B, the `harness-refine-issue` example) and
   `skills/create-loop/reference.md`'s routing-key field reference to document
   `on_cannot_judge` alongside `on_yes`/`on_no`, so loops scaffolded via `/ll:create-loop`
   don't inherit the same defect.
7. Add `on_cannot_judge` structural assertions to the existing per-loop test classes in
   `scripts/tests/test_builtin_loops.py`: `TestAssumptionFirewallLoop` (10239),
   `TestAdoptThirdPartyApiLoop` (10748), `TestIntegrateSdkLoop` (10815),
   `TestIncrementalRefactorLoop` (11166); to `scripts/tests/test_feat1544_loop_specialist_eval.py`'s
   `TestLoopSpecialistEvalStates` (68); add a new `TestDatasetCurationLoop` class (no
   dedicated coverage exists today — model on `TestIncrementalRefactorLoop`'s
   `data["states"]["<name>"].get(...)` shape); and extend `TestHarnessCapture`'s
   `HARNESS_FILES` list (`test_builtin_loops.py:2905-2908`, currently only
   `harness-single-shot.yaml`/`harness-multi-item.yaml`) or add a parallel class to cover
   `harness-plan-research-implement-report.yaml`.
   The new failure terminals in `harness-plan-research-implement-report.yaml`,
   `loop-specialist-eval.yaml`, and `dataset-curation.yaml` each get a `terminal: true` +
   `failure: true` assertion.
8. `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_executor.py
   scripts/tests/test_feat1544_loop_specialist_eval.py -v` passes, and `ll-loop validate`
   runs clean against each of the 9 changed loop files, including against
   `TestValidatorWarningBudget`'s corpus-wide lint ratchet
   (`test_builtin_loops.py:13779-13907`) without needing a new `ALLOWLIST` entry.

## Sequencing Notes

- Independent of BUG-3228; see Parent Issue. Nothing here needs revision when the
  `_uncertain` fallback lands.
- **Do not run in parallel with BUG-3227.** Both issues edit
  `skills/create-loop/loop-types.md` (this issue: the Variant A/B and `harness-refine-issue`
  `check_semantic`/`check_skill` scaffolds; BUG-3227: the Specialist Pipeline template and
  the `# OPTIONAL: check_substrate` block) and `skills/create-loop/reference.md`'s
  routing-key field reference. Under `parallel.epic_branches` these land as conflicting
  edits to the same two files. Sequence them, or land the shared `reference.md` routing-key
  update in whichever issue goes first and have the other rebase.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.executor` — `_abstention_fallback()` semantics
- `.claude/CLAUDE.md` `## Loop Authoring` — meta-loop shape rules referenced by `ll-loop
  validate`, and the harness-template guide these gates propagate into
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — the documented source users copy the three
  `harness-*.yaml` templates from

## Status

**Open** | Created: 2026-08-16 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-08-17T01:20:21 - `f9d03c8c-c328-4dfd-93cf-1b2bf5193b15.jsonl`
- `/ll:issue-size-review` - 2026-08-17T01:13:51 - `aac72723-ff3b-4a56-8e20-e1cf00b2242c.jsonl`

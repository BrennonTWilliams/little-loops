---
id: BUG-3227
type: BUG
title: check_substrate abstention needs a deterministic probe state in rn-build/rn-plan
priority: P2
testable: true
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
parent: EPIC-3217
supersedes: [BUG-3219]
---

# BUG-3227: check_substrate abstention needs a deterministic probe state in rn-build/rn-plan

## Summary

`rn-build.yaml`/`rn-plan.yaml`'s `check_substrate` gates are two of the thirteen judged
gates named in BUG-3219 that declare neither `on_cannot_judge` nor `on_error`, so an
abstaining judge holds twice and then terminates the run via "No valid transition". Unlike
the other eleven gates (BUG-3226), this pair can't be fixed by routing to an
already-existing target: "does the substrate exist" is deterministically probe-able, and no
such probe state exists anywhere in the repo today. This issue is the one sub-task
BUG-3219 itself flags as needing more design than a route addition, and lands
independently of BUG-3226.

## Parent Issue

Supersedes BUG-3219 (decomposed): Judged gates with neither on_cannot_judge nor on_error
terminate the run on abstention. BUG-3226 is the sibling successor covering the other
eleven gates.

Relationship to BUG-3228 (`_uncertain` suffix fallback): independent, per EPIC-3217
Sequencing. This issue declares `on_cannot_judge` only; `cannot_judge_uncertain` inherits
the same route once BUG-3228 lands.

## Current Behavior

| loop | state |
|---|---|
| `rn-build.yaml` | `check_substrate` (382-396) |
| `rn-plan.yaml` | `check_substrate` (152-168) |

Both are `evaluate.type: llm_structured`, judging `${captured.design_artifacts.output}`/
`${captured.plan_for_substrate.output}` (a plan/design doc), with `on_yes`/`on_no`(`/on_partial`)
but no `on_cannot_judge` and no `on_error`. A run reaching either and abstaining holds
twice (re-running the state's action each hold via `_route_abstention_hold()`,
`scripts/little_loops/fsm/executor.py:2683-2697`) then dies after three attempts with
"No valid transition".

## Steps to Reproduce

1. Run `rn-build.yaml` (or `rn-plan.yaml`) far enough to reach `check_substrate` — in
   `rn-build.yaml` via `commit_design` (364-377), which routes there unconditionally; in
   `rn-plan.yaml` via `generate_rubric` (77-147).
2. Have the judge abstain on the captured plan/design doc — i.e. the document does not
   contain enough to decide whether the substrate exists, which is exactly the case that
   motivates a deterministic probe.
3. Observe `check_substrate` re-enter itself twice (re-running its `echo`/`cat` action and
   re-judging each hold), then the run terminate with `error="No valid transition"`.

## Impact

Two gates in the two `rn-*` planning loops kill their run on abstention, and unlike the
BUG-3226 gates the correct destination is not a route that already exists — "does the
substrate exist" is a deterministic question the judge should never have been asked. Left
unfixed, the run dies with a generic transition error at the exact point where a one-line
shell test would have answered definitively.

## Expected Behavior

Abstention on `check_substrate` should run a deterministic probe rather than guess
`design_artifacts`. Deterministic existence/capability probes in this codebase are plain
`action_type: shell` states using `command -v`/file-existence tests, evaluated with `type:
exit_code` or `type: output_contains` — never `llm_structured` (evidence:
`cua-agent-desktop.yaml:101-118` `check_install`, `cua-agent-desktop.yaml:125-152`
`check_permissions`, `rn-build.yaml:108-128` `check_structure`, `rn-build.yaml:155-171`
`verify_structure`). `check_substrate` itself is the target of this fix, not an existing
example of the pattern — no "capture evidence and re-run the judge" state exists yet
anywhere in the repo; the nearest structural precedents are `rn-build.yaml:308-336`'s
`check_research_written` (probes whether an upstream prompt's expected artifact exists,
writes a placeholder stub if not) and `rn-build.yaml:1231-1250`'s `finalize_build_failed`
(reads run-dir state before declaring failure).

Where the probe determines the substrate genuinely doesn't exist, route to a
failure-shaped terminal (`terminal: true`, `failure: true`) rather than leaving the gate to
die on "No valid transition".

### RESOLVED: a positive probe bypasses the judge, it does not re-enter `check_substrate`

The Proposed Solution's "route back into the normal flow" means **`check_substrate`'s own
`on_yes` target** (`scope_project` in `rn-build.yaml`, `research_iteration` in
`rn-plan.yaml`), not a re-judge.

Rationale: re-entering `check_substrate` re-runs the identical `llm_structured` judge over
the identical captured input (`${captured.design_artifacts.output}` /
`${captured.plan_for_substrate.output}` — the probe does not modify either). The judge that
just abstained will very likely abstain again, producing a `check_substrate → probe →
check_substrate` cycle bounded only by the loop's `max_iterations`, which surfaces as a
limit failure rather than the real cause. The deterministic probe exists precisely to be
*more authoritative* than the judge on this question; deferring back to the judge discards
that. This also matches the established shape — `check_install` → `check_permissions`,
`check_structure` `on_yes` → `tech_research`, `verify_structure` `on_yes` →
`load_normalized` all move forward, none route back to a judge.

### The probe command must be pinned per loop before implementation

"Substrate" is not the same object in the two loops, so a single probe command does not
transfer:

- `rn-build.yaml` — `check_substrate` judges `${captured.design_artifacts.output}`, captured
  by `design_artifacts` (340-360) and committed by `commit_design` (364-377).
- `rn-plan.yaml` — `check_substrate` judges `${captured.plan_for_substrate.output}`, which
  is a `cat "${captured.run_dir.output}/plan.md"` of the file written by `generate_rubric`
  (77-147).

The issue is not implementable until the concrete shell test for each loop is written down
here — otherwise the implementer invents the substrate semantics at the keyboard, which is
exactly the ambiguity the LLM judge is already failing on. Both commands should follow
`finalize_build_failed`'s (`rn-build.yaml:1225-1251`) tolerant read shape
(`2>/dev/null || echo ""`) so a missing path yields a definite "not found" rather than a
shell error routed as `on_error`.

## Root Cause

Same executor mechanism as BUG-3219/BUG-3226 —
`FSMExecutor._abstention_fallback()` (`scripts/little_loops/fsm/executor.py:2669-2681`)
returns `None` when neither `route.error` nor `on_error` is set, and the main execution
loop's `next_state is None` branch (758-774) calls `self._finish("error", error="No valid
transition")`. `check_substrate` was authored before ENH-3185 introduced the `cannot_judge`
verdict and declares only `on_yes`/`on_no`.

## Proposed Solution

Add a new deterministic probe state (shell + `exit_code`/`output_contains`, modeled on
`check_install`/`check_structure`) that `check_substrate`'s `on_cannot_judge` routes to.
The probe checks for the substrate's existence directly rather than relying on the LLM
judge's read of `design_artifacts`/`plan_for_substrate`. If the probe finds substrate, route
forward to `check_substrate`'s existing `on_yes` target — not back into `check_substrate`
(see Expected Behavior § RESOLVED); if not, route to a failure-shaped terminal.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/loops/rn-build.yaml` — `check_substrate` (382-396, `evaluate.type: llm_structured`, judging `${captured.design_artifacts.output}`) lacks `on_cannot_judge`/`on_error`. `design_artifacts` (340-360) captures the judged content; `commit_design` (364-377) routes unconditionally to `check_substrate`.
- `scripts/little_loops/loops/rn-plan.yaml` — `check_substrate` (152-168, judging `${captured.plan_for_substrate.output}`, itself captured by a `cat "${captured.run_dir.output}/plan.md"` shell action in the same state) lacks `on_cannot_judge`/`on_error`. `plan.md` is written by `generate_rubric` (77-147), which routes to `check_substrate`.

### Dependent Files (Callers/Importers)
- No Python callers beyond the FSM loader — `FSMExecutor._abstention_fallback()` (`scripts/little_loops/fsm/executor.py:2669-2681`) is the sole consumer of the routing gap and needs no code changes; the new probe state is expressed purely as loop YAML.

### Conventions in Force
- Deterministic existence/capability probes in this codebase are `action_type: shell` states whose `evaluate.type` is `output_contains` or `exit_code` — never `llm_structured` — evidence: `cua-agent-desktop.yaml:101-118` (`check_install`), `cua-agent-desktop.yaml:125-152` (`check_permissions`), `rn-build.yaml:108-128` (`check_structure`), `rn-build.yaml:155-171` (`verify_structure`). All four declare `on_yes`/`on_no`/`on_error` explicitly rather than leaving any unhandled.
- The probe's "not found" branch conventionally routes to a `terminal: true`/`failure: true` state with a short, condition-describing name (`not_installed`, `perm_denied`, `failed`, `build_failed`) — evidence: `cua-agent-desktop.yaml:120-123,154-159`, `harness-single-shot.yaml:174-177`, `rn-build.yaml:1252-1254`.
- The probe's "found, continue" branch routes forward into the normal pipeline, not back to a judge — evidence: `check_install` → `check_permissions`, `check_structure` on_yes → `tech_research`, `verify_structure` on_yes → `load_normalized`.
- `on_error` handling for these deterministic probes is not uniform: `check_install`/`check_permissions`/`verify_structure` route `on_error` to the same failure state as `on_no`; `check_structure` instead routes `on_error` forward to `tech_research`, treating a shell-mechanics error as non-fatal — a disagreement to resolve deliberately, not by copying either example blindly.
- `rn-build.yaml:308-336`'s `check_research_written` is the closest existing precedent for "probe an upstream artifact directly, self-heal (write a stub) if missing, then continue" — it always `exit 0`s and funnels `on_yes`/`on_no`/`on_error` all to the same next state (`design_artifacts`), rather than branching to a failure terminal on a missing artifact.
- No "judge abstains → deterministic probe → route based on probe result" chain exists anywhere in the repo today (grep-confirmed zero `on_cannot_judge` matches across all `loops/` files) — `check_substrate` is the first instance of this exact shape, not a case of copying an existing example.
- `rn-build.yaml:1225-1251`'s `finalize_build_failed` is the precedent for reading run-dir state tolerantly (`2>/dev/null || echo ""`) before declaring a failure terminal.

### Tests
- `scripts/tests/test_builtin_loops.py::TestCheckSubstrateOptionalState` (13635; line refs in this section are advisory and have already drifted once) already covers both loops' `check_substrate` states via string-slice assertions (locate state start/next-state boundary in `.read_text()`, assert route keys present in the slice) — e.g. `test_rn_build_check_substrate_has_full_routing` (13709-13720), `test_rn_plan_check_substrate_has_full_routing` (13670-13681), plus positional-ordering assertions (13722-13736, 13683-13697). A structurally analogous precedent for asserting a specific route *target* (not just key presence) after a gate was repointed to a new state exists at `test_rn_build_check_harness_name_no_longer_routes_to_synthesize` (13763-13776) and `test_rn_build_has_harness_missing_states`/`test_rn_build_harness_missing_has_full_routing` (13740-13761, added for ENH-2415's `harness_missing` state) — the closest model for asserting a newly-added probe state's own routing.
- `scripts/tests/test_rn_build.py`, `scripts/tests/test_rn_plan.py` — loop-specific test files; unclear whether either currently has assertions touching `check_substrate` beyond `test_builtin_loops.py`'s coverage — needs a dedicated check during implementation.
- `TestValidatorWarningBudget` (`test_builtin_loops.py:13779-13907`) — corpus-wide lint ratchet; a new probe state that is unreachable or mis-referenced trips its `"unreachable"` (`not reachable from initial state`, message source `fsm/validation/structural_rules.py:1052`) or `"loop-reference"` (`does not resolve to any file`, message source `fsm/validation/reachability.py:93`) categories. `ALLOWLIST` entries require a comment citing the owning issue; ENH-2748's in-YAML `capture_reachability_ok: true` flag is a documented alternative for at least the `capture-ordering` category, but no equivalent flag exists for `unreachable`/`loop-reference`.

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — canonical `check_substrate` "State Shape" YAML block (449-464) needs updating to show the new `on_cannot_judge` → probe route.
- `docs/guides/LOOPS_REFERENCE.md` — `check_substrate` prose (286, 297, 714) needs updating for the new route.
- `skills/create-loop/loop-types.md` — Specialist Pipeline template `check_semantic` (1354-1394) and the commented `# OPTIONAL: check_substrate` block (1327-1346) need updating; cross-check `skills/create-loop/reference.md`'s routing-key field reference stays consistent.

## Program Design

### Signatures
- `FSMExecutor._abstention_declared(state: StateConfig, verdict: str) -> bool` — becomes `True` for `check_substrate` once `on_cannot_judge: <probe_state_name>` is declared, routing the abstention to the new probe state instead of holding; see `scripts/little_loops/fsm/executor.py:2656-2667`.
- `FSMExecutor._route_abstention_hold(state: StateConfig, state_name: str, ctx: InterpolationContext) -> str | None` — holds `check_substrate` up to `_ABSTENTION_HOLD_CAP` (2) times, re-running the state's action (the `echo`/`cat` in `rn-build.yaml`/`rn-plan.yaml`) and re-judging each hold, before falling through to `_abstention_fallback()`; see `scripts/little_loops/fsm/executor.py:2683-2697`.
- `FSMExecutor._abstention_fallback(state: StateConfig, ctx: InterpolationContext) -> str | None` — same fallback mechanism as BUG-3226; returns `None` today for both `check_substrate` states since neither declares `route.error` nor `on_error`; see `scripts/little_loops/fsm/executor.py:2669-2681`.

### Types
N/A — no new data shape. The new probe state is a standard `StateConfig` YAML dict (`action_type: shell`, `evaluate.type: exit_code`/`output_contains`); no schema change is required.

### Call Path
`FSMExecutor._abstention_declared` -> `FSMExecutor._route_abstention_hold` -> `FSMExecutor._abstention_fallback` -> `FSMExecutor._finish`.

Today, for both loops: `check_substrate` (`evaluate.type: llm_structured`) abstains → `FSMExecutor._abstention_declared` returns `False` (no route declared) → `FSMExecutor._route_abstention_hold` holds 2× → `FSMExecutor._abstention_fallback` returns `None` → main loop `next_state is None` (`scripts/little_loops/fsm/executor.py:758-774`) → `FSMExecutor._finish("error", "No valid transition")`. Target call path after the fix: `check_substrate` abstains → `on_cannot_judge: <new probe state>` → probe state runs a deterministic shell existence check on the substrate (modeled on `check_install`/`check_structure`'s `action_type: shell` + `exit_code`/`output_contains` shape) → probe's `on_yes` routes back into the loop's normal flow (the state `check_substrate`'s own `on_yes` would have targeted — `scope_project` in `rn-build.yaml`, `research_iteration` in `rn-plan.yaml`) or, on `on_no`, to a `terminal: true`/`failure: true` state (new or existing, per-loop).

### Decision Rules
- New gap kind introduced by this issue: an `on_cannot_judge` route from an `llm_structured` gate to a freshly-added deterministic probe state, rather than to an existing target (contrast with BUG-3226's gates, which route to something that already exists).
- Exact inputs: the probe's shell command must test substrate existence directly — analogous to `check_install`'s `command -v agent-desktop` or `check_structure`'s `grep -c` header count — the concrete command is an implementation decision, not yet pinned by research (no existing "substrate" probe exists to model verbatim).
- Threshold/exit condition: probe result surfaces via `evaluate.type: exit_code` (shell exit 0/1) or `output_contains` (echoed sentinel string), following the two evaluator types already in use for this shape in this codebase — not a numeric threshold.
- Escape hatch / dismissal: on a definitive "substrate does not exist" result, route to a `terminal: true`/`failure: true` state (per Expected Behavior) rather than re-attempting the LLM judge or silently proceeding — mirrors `not_installed`/`perm_denied`/`failed` conventions in Integration Map.
- **Resolved** (was the issue's one open question): a positive probe result bypasses the judge and proceeds to `check_substrate`'s existing `on_yes` target (`scope_project` / `research_iteration`); it does not route back into `check_substrate` for re-judging. See Expected Behavior § RESOLVED for the reasoning — a re-judge re-runs the same judge over the same unmodified captured input and cycles until `max_iterations`.
- **Still to pin before implementation**: the concrete probe shell command for each loop. `rn-build.yaml`'s and `rn-plan.yaml`'s substrates are different objects (design artifacts vs `plan.md`), so one command does not transfer; see Expected Behavior § The probe command must be pinned per loop.

## Implementation Steps

0. Pin the concrete probe shell command for each loop (Expected Behavior § The probe command
   must be pinned per loop) before writing YAML — this issue is not implementable without it.
1. Design and add the deterministic probe state to `rn-build.yaml` and `rn-plan.yaml`
   (shell command + `exit_code`/`output_contains` evaluation, per the `check_install`/
   `check_structure` shape), with `check_substrate`'s `on_cannot_judge` routing to it.
2. Route the probe's own failure branch to a `terminal: true` / `failure: true` state in
   each loop, and its success branch forward to `check_substrate`'s existing `on_yes`
   target (`scope_project` in `rn-build.yaml`, `research_iteration` in `rn-plan.yaml`) —
   never back into `check_substrate`. Decide the probe's `on_error` deliberately: the
   existing probes disagree (`check_install`/`check_permissions`/`verify_structure` send
   `on_error` to the failure state; `check_structure` sends it forward), so pick one and
   comment the reason rather than copying either blindly.
3. Update `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`'s canonical `check_substrate` "State
   Shape" YAML block (lines 449-464) and `docs/guides/LOOPS_REFERENCE.md`'s
   `check_substrate` prose (lines 286, 297, 714 — "infeasible plans route back to...") to
   describe the new `on_cannot_judge` → probe route.
4. Update `skills/create-loop/loop-types.md`'s Specialist Pipeline template `check_semantic`
   (lines 1354-1394) and the commented `# OPTIONAL: check_substrate` block (lines
   1327-1346) to show the new route, and cross-check
   `skills/create-loop/reference.md`'s routing-key field reference is consistent.
5. Add/extend test coverage: `TestCheckSubstrateOptionalState`
   (`scripts/tests/test_builtin_loops.py:13635`) already covers both loops' `check_substrate`
   states — extend it for the new route; check whether `scripts/tests/test_rn_build.py`
   and `scripts/tests/test_rn_plan.py` need a dedicated assertion for the new probe state
   too.
6. `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_rn_build.py
   scripts/tests/test_rn_plan.py scripts/tests/test_fsm_executor.py -v` passes, and
   `ll-loop validate` runs clean against `rn-build.yaml`/`rn-plan.yaml`, including against
   `TestValidatorWarningBudget`'s corpus-wide lint ratchet
   (`test_builtin_loops.py:13779-13907`) — an unreachable or mis-referenced new probe state
   trips `"unreachable"`/`"loop-reference"` and needs either a fix or a new owned-by-issue
   `ALLOWLIST` entry.

## Sequencing Notes

- Independent of BUG-3228; see Parent Issue.
- **Do not run in parallel with BUG-3226.** Both edit `skills/create-loop/loop-types.md`
  (this issue: the Specialist Pipeline `check_semantic` template and the
  `# OPTIONAL: check_substrate` block; BUG-3226: the Variant A/B and `harness-refine-issue`
  scaffolds) and `skills/create-loop/reference.md`'s routing-key field reference. Under
  `parallel.epic_branches` these land as conflicting edits to the same two files.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.executor` — `_abstention_fallback()` semantics
- `.claude/CLAUDE.md` `## Loop Authoring` — meta-loop shape rules referenced by `ll-loop
  validate`
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md` — canonical
  `check_substrate` documentation that needs updating alongside the fix

## Status

**Open** | Created: 2026-08-16 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-08-17T01:20:21 - `f9d03c8c-c328-4dfd-93cf-1b2bf5193b15.jsonl`
- `/ll:issue-size-review` - 2026-08-17T01:13:51 - `aac72723-ff3b-4a56-8e20-e1cf00b2242c.jsonl`

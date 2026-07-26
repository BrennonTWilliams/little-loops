---
id: BUG-2822
type: BUG
priority: P2
status: done
captured_at: '2026-07-26T01:54:53Z'
completed_at: '2026-07-26T04:41:40Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
labels:
- fsm
- loops
- max-steps
- flux
- generator-evaluator
relates_to:
- BUG-2815
- FEAT-2817
- ENH-2814
confidence_score: 98
outcome_confidence: 85
score_complexity: 19
score_test_coverage: 23
score_ambiguity: 20
score_change_surface: 23
---

# BUG-2822: `generator-evaluator-flux` starves at 2.5 cycles and discards a generated image on budget exhaustion

## Summary

`oracles/generator-evaluator-flux.yaml` inherits `max_steps: 20` from
`generator-evaluator` but adds a `synthesize` state, making its cycle **8 states
long** — 20 ÷ 8 = 2.5 cycles. The oracle is architecturally incapable of
completing a third *scored* iteration regardless of image quality. It also has no
`on_max_steps` handler, so an exhausted child is indistinguishable from a crash:
the parent's `run_gen_eval` routes `on_no → diagnose → failed` and throws away a
completed, on-disk FLUX image.

Evidence: `thoughts/audit-loop-run-flux-image-generator-2026-07-26T011622.md`
(`/ll:audit-loop-run` on run `2026-07-26T011622`, verdict `partial`).

Same defect class as [[BUG-2815]] (`evaluation-quality`), different loop. The
family-wide version of the budget half is tracked separately in BUG-2824.

## Current Behavior

Verified by loading the resolved FSMs (`ll-loop` loader, `from:` inheritance
expanded):

```
oracles/generator-evaluator-flux   max_steps=20  on_max_steps=None  nstates=10
oracles/generator-evaluator        max_steps=20  on_max_steps=None  nstates=9
flux-image-generator               max_steps=20  on_max_steps=None  nstates=8
```

The child's cycle:

```
generate → synthesize → evaluate → snapshot → score → record_score → check_stall → check_diff_stall
```

Observed run trace (from the audited `events.jsonl`, 181 lines):

```
cycle 1: generate → synthesize → evaluate → snapshot → score → record_score → check_stall → check_diff_stall
cycle 2: generate → synthesize → evaluate → snapshot → score → record_score → check_stall → check_diff_stall
cycle 3: generate → synthesize → evaluate → snapshot   ← BUDGET EXHAUSTED at step 20
```

```json
{"event":"loop_complete","final_state":"score","iterations":20,"terminated_by":"max_steps","depth":1}
{"event":"loop_complete","final_state":"failed","iterations":5,"terminated_by":"terminal"}
```

Consequences observed on disk in the run dir:

- `image-iter-3.png` (607,499 bytes, `seed=1023760`) was generated but **never
  scored** — no `critique.md` entry, no `.score_history` line.
- `.score_history` holds only `5.8` and `5.4` against `pass_threshold: 6`.
- `grep -c max_steps_summary events.jsonl` → `0`.
- `vision_gate` — the only external, non-self-certifying evaluator — **never
  ran**, despite `VISION_*` being configured. `.vision_rounds` does not exist.
- Parent utilization was 5/20 (0.25); the child's was 20/20 (1.00). Every one of
  the 24 `action_complete` events carried `exit_code: 0` — nothing actually
  failed.

**Critical detail for whoever fixes this**: the audit document's own diff targets
`flux-image-generator.yaml`'s `max_steps`. That is the **wrong file**. Each loop
resolves its own `max_steps`; a sub-loop does not inherit the parent's. Raising
the parent's budget alone would not have changed this run at all.

## Steps to Reproduce

Structural (no FLUX endpoint required):

```bash
python3 -c "
import logging, pathlib, little_loops.loops as L
from little_loops.cli.loop._helpers import load_loop
d = pathlib.Path(L.__file__).parent
f = load_loop('oracles/generator-evaluator-flux', d, logging.getLogger('x'))
print('max_steps=', f.max_steps, 'on_max_steps=', f.on_max_steps)
"
# → max_steps= 20 on_max_steps= None
```

The cycle is 8 states (`generate → synthesize → evaluate → snapshot → score →
record_score → check_stall → check_diff_stall`), so 20 ÷ 8 = 2.5 cycles. No run
is needed to observe the ceiling.

Behavioural (requires `IMAGE_BASE_URL`): run
`ll-loop run flux-image-generator` on any brief that will not pass the rubric in
two rounds, then inspect the run dir — `.gen_counter` will exceed the line count
of `.score_history`, and `grep -c max_steps_summary events.jsonl` returns `0`.

## Expected Behavior

1. The child oracle's budget accommodates its intended iteration count — at 8
   states per cycle, `max_steps: 60` buys ~7 full scored cycles, which is the
   headroom `check_stall` (`score_stall`, `max_stall: 2`) and `check_diff_stall`
   (`max_stall: 3`) were calibrated to consume.
2. Budget exhaustion is a distinct, reported outcome, not a silent crash. An
   exhausted child writes a best-so-far verdict via an `on_max_steps` summary
   state so the parent can report partial success and surface the images that
   were produced.
3. A generated-but-unscored image is never orphaned by a budget cut.
4. `synthesize` fails loudly when `image-prompt.txt` is **stale** (unchanged
   since the previous iteration), not just when it is missing or empty.

## Motivation

Every wasted cycle here is real GPU spend on a self-hosted diffusion endpoint,
plus an LLM rubric call. This run burned three FLUX generations and delivered a
`failed` verdict while holding a usable image on disk. The loop shipped in
FEAT-2817 (commit `c52d0988`) can, as configured, never converge on any image
requiring more than two refinement rounds — which is most non-trivial briefs.

## Proposed Solution

### 1. Raise the child oracle's budget (`oracles/generator-evaluator-flux.yaml`)

Add a top-level override — the file currently inherits 20 silently via `from:`:

```yaml
 name: generator-evaluator-flux
 from: generator-evaluator
 visibility: internal
+# 8-state cycle (the base 7 + synthesize); 60 ≈ 7 full scored iterations.
+# Overrides the inherited max_steps: 20, which capped this oracle at 2.5 cycles.
+max_steps: 60
```

Also raise `flux-image-generator.yaml`'s own `max_steps: 20`. Its
`vision_gate → run_gen_eval` back-edge costs 2 states per vision round against a
`ROUND_CAP` of 3, and the linear prefix is 4 — the parent cannot currently
complete the vision rounds its own code budgets for.

### 2. Add an `on_max_steps` summary state

Give the flux oracle a summary state that reads `.score_history`, `seeds.txt` and
`.gen_counter`, names the best-scoring iteration, and emits a verdict token the
parent's `run_gen_eval` evaluator can consume as partial success. Per BUG-158
semantics (`executor.py:590-601`), a terminal doubling as the `on_max_steps`
handler *does* execute its action — one of only two live terminal actions in the
corpus — so this is the sanctioned shape and does not fall foul of [[BUG-2813]].

The parent then needs a route that distinguishes "child exhausted with usable
output" from "child errored", instead of collapsing both into
`on_no → diagnose → failed`. Note this interacts with ENH-2814: today a `failed`
terminal exits 0 anyway, so the distinction is currently unobservable downstream.

### 3. Detect a stale prompt file in `synthesize`

`synthesize` already hard-fails on a missing/empty prompt
(`[ ! -s "$PROMPT_FILE" ]`), but not on an unchanged one. Iteration 3's evaluator
returned `partial` with this verdict, verbatim:

> "the file-writing action itself is only supported by a self-report (\"The
> image-prompt.txt has been written (118 words)\") rather than a visible Write
> tool result... the actual file creation cannot be verified from the output
> alone."

Hash `image-prompt.txt` into `.prompt_hash` alongside the existing `.gen_counter`
idiom and emit `IMAGE_FAIL` when the hash is unchanged on iteration ≥ 2 — a
regenerate on an unrewritten prompt burns a full FLUX generation to re-render a
near-identical latent.

**Explicitly rejected** (the audit's recommendation #4): splitting `generate`'s
`on_yes`/`on_no`/`on_partial: synthesize` collapse. That collapse is a
deliberate, documented decision (ENH-1907, commented in both
`generator-evaluator.yaml` and `generator-evaluator-flux.yaml`): routing on the
default judge's read of the agent's *narration* dead-ends the sub-loop
nondeterministically, because a pass that describes its fixes rather than
asserting them earns `partial`. The hash check above is the correct, deterministic
answer to the same concern.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Confirmed executor mechanics** (`scripts/little_loops/fsm/executor.py:461-499` step-cap check, `:590-601` fallthrough): `on_max_steps` is `None` for both `generator-evaluator-flux.yaml` and its base `generator-evaluator.yaml` (neither declares the key), so the step-cap branch at `executor.py:462-463` is skipped entirely — the sub-loop exits via plain `_finish("interrupted")`/step-cap exhaustion without ever entering a handler state. The BUG-158 fallthrough semantics cited in the issue (`:590-601`, `if self.current_state != self.fsm.on_max_steps: return self._finish("max_steps")`) are confirmed accurate at that line range, but only engage once `on_max_steps` is actually configured.
- **Two ready-to-copy templates for the terminal-doubling `on_max_steps` state** (exactly the shape #2 in Proposed Solution asks for — `terminal: true` with a live `action:`):
  - `scripts/little_loops/loops/vega-viz.yaml:553-577`, state `max_steps_summary` (wired via `on_max_steps: max_steps_summary` at `:37`) — reads `best.html`/`best.critique.md`/`best_score.txt` from `${captured.run_dir.output}`, emits a summary via `action_type: prompt`, evaluates with `output_contains: "SUMMARY_EMITTED"`, `terminal: true`.
  - `scripts/little_loops/loops/cua-agent-desktop.yaml:1213-1264`, state `max_steps_summary` (wired via `on_max_steps: max_steps_summary` at `:17`) — same shape, writes `summary.md` from `.action_log.md`, `output_contains: "SUMMARY_WRITTEN"`.
  - Contrast: `canvas-sketch-generator.yaml`'s `on_max_steps: finalize` (`:32`) and `general-task.yaml`'s `on_max_steps: summarize_partial` (`:9`) are *not* terminal-doubling — both `next:` to a downstream terminal instead, so they don't exercise the BUG-158 special case. The flux oracle's new state should follow the vega-viz/cua-agent-desktop shape, not the canvas-sketch-generator shape, since it needs the action to run in the same state that satisfies `on_max_steps`.
- **No existing content-hash staleness idiom exists in the loop corpus** (searched `hashlib`/`md5sum`/`sha1sum`/`shasum`/`cksum` across `scripts/little_loops/loops/`; the only hit, `cli-anything-bootstrap.yaml:78`, is an unrelated cache-key derivation). The closest prior art for a small per-run-dir marker file with a comparison gate is `scripts/little_loops/loops/lib/common.yaml:148-181` (`diff_stall_gate`/`score_stall_gate` fragments) and the `.gen_counter` idiom already in `synthesize` (`generator-evaluator-flux.yaml:100-110`, read-with-except-default-0, increment, rewrite). The proposed `.prompt_hash` gate should follow that same read/compare/rewrite shape — there's no closer template to copy, so this is new-idiom territory, not a refactor of an existing gate.
- **No existing 3-way `loop:`-delegation route exists** for "child exhausted with usable output" vs. "child errored" (`flux-image-generator.yaml:86-169`'s `run_gen_eval` currently only has `on_yes`/`on_no`/`on_error`, all three of which a step-cap-exhausted child falls into via `on_no`/`on_error` today). This is new plumbing on the parent side, not an established pattern elsewhere in the corpus.
- **The base oracle (`generator-evaluator.yaml`) has no `on_max_steps` either** (confirmed by direct read of `:11-15`/`:148-187`) — every other wrapper inheriting from it (svg/html/p5js/hitl-md variants plus `generator-evaluator-cli`) shares the same silent-fallthrough behavior unless it independently overrides `on_max_steps`. Consistent with the issue's note that the family-wide fix is tracked separately in BUG-2824.
- **Test-file convention already established** in `scripts/tests/test_flux_image_generator.py`: existing structural assertions use `load_and_validate` (not the issue's own `load_loop` repro snippet), e.g. `test_oracle_inherits_generator_evaluator` (`:58-64`), `test_oracle_inherits_stall_machinery` (`:73-77`). A new structural test should follow that convention: `fsm, _ = load_and_validate(ORACLE); assert fsm.max_steps >= 8 * INTENDED_CYCLES; assert fsm.on_max_steps in fsm.states`. For the stale-prompt behavioral case, `TestSynthesizeBehaviour.test_second_iteration_does_not_overwrite_and_uses_a_new_seed` (`:253-267`) is the closest existing precedent for a "call `synthesize` twice against the same run dir, assert on the second call" shape — extend it to write the same `image-prompt.txt` content twice and assert the second call emits `IMAGE_FAIL` instead of `IMAGE_OK`. For engine-level `on_max_steps` coverage (not this file, but relevant if the fix touches shared executor behavior), see `scripts/tests/test_fsm_executor.py` class `TestMaxStepsSummaryHook` and `scripts/tests/test_ll_loop_execution.py:159-198` (`test_runs_summary_state_on_max_steps`).

### 4. Score before snapshot (deferred)

The audit also recommends reordering the cycle so `score`/`record_score` follow
`evaluate` directly, so a budget cut can never orphan a generated image. That
ordering lives in the **base** `generator-evaluator`, shared by 6+ wrappers —
it belongs to BUG-2824, not here.

## Integration Map

| File | Change |
|---|---|
| `scripts/little_loops/loops/oracles/generator-evaluator-flux.yaml` | `max_steps: 60` override; `on_max_steps` summary state; stale-prompt hash gate in `synthesize` |
| `scripts/little_loops/loops/flux-image-generator.yaml` | raise `max_steps`; route exhausted-with-output distinctly from `run_gen_eval` |
| `scripts/tests/test_flux_image_generator.py` | assert resolved `max_steps` ≥ 8 × intended cycles and `on_max_steps` is set; behavioural test for the stale-prompt failure mode against the existing stub FLUX server |

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — the `flux-image-generator` flow diagram (~L1760-1788) and its trailing bullets (~L1785, ~L1788) show only the current two-way `run_gen_eval` routing and say nothing about `max_steps`/`on_max_steps`; both need updating once the 3-way route and summary state land, following the `svg-image-generator` entry's (L1727) pattern of stating `max_steps:` explicitly. [Agent 2 finding]
- `scripts/little_loops/loops/README.md` (optional, not test-enforced) — the one-line catalog summaries for `flux-image-generator` (L154) and `oracles/generator-evaluator-flux` (L185) describe iteration/routing behavior in prose without citing `max_steps`/`on_max_steps`; not stale, but incomplete relative to the new summary-state and hash-gate behavior. [Agent 1/2 finding]

### Verified No Further Wiring Needed

_Wiring pass added by `/ll:wire-issue`:_
- `fsm/validation.py`'s `terminal_action_ok` gate (`_validate_terminal_action_ok`, ~L1148-1191) already builds an exemption set from `{fsm.on_max_steps, fsm.on_max_iterations}` — the new terminal-doubling summary state needs no `terminal_action_ok: true` suppression flag, matching the `vega-viz.yaml`/`cua-agent-desktop.yaml` precedent. [Agent 2 finding]
- MR-1 (`meta_self_eval_ok`) does not apply if the summary state's evaluator is `output_contains` (non-LLM), and MR-5 (`artifact_versioning_ok`) does not apply since the summary state only reads existing `.score_history`/`seeds.txt`/`.gen_counter`, it writes no new per-iteration artifacts. [Agent 2 finding]
- `scripts/tests/test_builtin_loops.py` has structural tests touching `flux-image-generator` (loop-set membership, L166) and `oracles/generator-evaluator.yaml` (MR-4 regression, L2001-2014, L498-510) — none hardcode a `max_steps` value or assert `on_max_steps is None` for either loop, so raising the budget and adding the handler will not break them. No file change needed, verified rather than assumed. [Agent 1/3 finding]
- No `commands/`, `skills/`, `.ll/ll-config.json`, or `.ll/decisions.d/*` coupling exists for these two loops — confirmed via direct search, nothing there references `flux-image-generator`/`generator-evaluator-flux` by name or numeric `max_steps`. [Agent 2 finding]
- Sibling wrappers inheriting the same base (`svg-image-generator.yaml`, `html-website-generator.yaml`, `html-anything.yaml`, `hitl-md.yaml`, `hitl-compare.yaml`, `interactive-component-generator.yaml`, `oracles/generator-evaluator-cli.yaml`) all delegate to `oracles/generator-evaluator` directly, not the flux variant — confirmed unaffected, consistent with the issue's stated contained blast radius. [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- No test currently asserts `fsm.max_steps` or `on_max_steps` for either `flux-image-generator.yaml` or `oracles/generator-evaluator-flux.yaml` — the planned `test_flux_image_generator.py` additions are genuinely new coverage, not updates to an existing pinned assertion. Model the `max_steps` assertion on `TestLoopStructure.test_validates_without_errors` (`load_and_validate(path)` pattern, ~L50-56) and the state-presence check on `test_oracle_inherits_stall_machinery` (~L73-77). [Agent 3 finding]
- Reference pattern for the new `on_max_steps` terminal-doubling structural/behavioral test: `scripts/tests/test_fsm_executor.py::TestMaxStepsSummaryHook` (~L8857, `_make_fsm()` helper ~L8860-8871, `test_summary_state_runs_on_cap` ~L8873, `test_max_steps_summary_event_emitted` ~L8885) and `scripts/tests/test_ll_loop_execution.py::test_runs_summary_state_on_max_steps` (~L159, real temp-YAML + mocked `subprocess.Popen` + `main_loop()` shape). [Agent 3 finding]
- No existing content-hash/staleness test helper exists anywhere in `scripts/tests/` (checked `hashlib`/`sha256`/`prompt_hash` hits in `test_codequery_codegraph.py`, `test_fsm_evaluators.py`, `test_fragment_store.py` — all unrelated domains) — the `.prompt_hash` staleness test is net-new with no local precedent beyond generic `hashlib.sha256(path.read_bytes()).hexdigest()` usage. [Agent 3 finding]

## Implementation Steps

1. Add the `max_steps` override and `on_max_steps` summary state to the flux
   oracle; confirm with the resolved-FSM load that both take effect through
   `from:` inheritance.
2. Add the stale-prompt hash gate to `synthesize`, reusing the `.gen_counter`
   file-counter idiom already in that Python heredoc.
3. Raise the parent's `max_steps` and add the partial-success route.
4. Extend `test_flux_image_generator.py` with the structural assertions and a
   stale-prompt behavioural case (the stub server harness already exists).
5. Run `ll-loop validate flux-image-generator` and
   `ll-loop validate oracles/generator-evaluator-flux`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/guides/LOOPS_REFERENCE.md` — refresh the `flux-image-generator` flow diagram and its two trailing bullets to show the new 3-way `run_gen_eval` route, the `on_max_steps` summary state, and the stale-prompt hash gate.
7. (Optional) Refresh the one-line catalog summaries in `scripts/little_loops/loops/README.md` for `flux-image-generator` and `oracles/generator-evaluator-flux` to mention the new budget/summary-state behavior.

## Impact

- **Severity**: P2. The loop produces output but cannot converge; the failure is
  silent and costs real GPU spend per wasted cycle.
- **Blast radius**: contained to the two flux YAMLs and their test file. The base
  oracle is untouched, so no sibling wrapper regresses.
- **Risk**: low. Budget increases cannot break a passing run; the `on_max_steps`
  state is additive; the hash gate is a new failure mode on a path that currently
  silently wastes a generation.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `thoughts/audit-loop-run-flux-image-generator-2026-07-26T011622.md` | Source audit; verbatim run evidence |
| `.claude/CLAUDE.md` § Loop Authoring | MR-1 / MR-5 rules and validator gates |
| `docs/guides/LOOPS_REFERENCE.md` | Loop catalog entry for `flux-image-generator` |

## Session Log
- `/ll:manage-issue` - 2026-07-26T04:41:07Z - `90bcac60-952b-45ec-82a0-b5049b072dd8.jsonl`
- `/ll:ready-issue` - 2026-07-26T04:23:31 - `27e7551c-ee1d-4f72-b7c0-274e002cea02.jsonl`
- `/ll:confidence-check` - 2026-07-25T00:00:00 - `34bd459d-4bea-4d40-ae6e-26594fcbbb59.jsonl`
- `/ll:wire-issue` - 2026-07-26T04:21:23 - `2ce90762-9692-4702-8b31-caf74a7e207b.jsonl`
- `/ll:refine-issue` - 2026-07-26T04:14:43 - `51375cc3-34a6-4a02-b462-e8b812da1ff0.jsonl`
- `/ll:capture-issue` - 2026-07-26T01:54:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3bbb9637-e022-4716-b2c1-d8b3f35b1152.jsonl`

## Resolution

Fixed by raising the child oracle's (`oracles/generator-evaluator-flux.yaml`)
`max_steps` from an inherited 20 to an explicit 60 (~7 scored 8-state cycles),
raising the wrapper's (`flux-image-generator.yaml`) `max_steps` from 20 to 24 to
accommodate the vision-gate back-edge, and adding an `on_max_steps:
max_steps_summary` terminal-doubling state to the oracle that names the
best-scoring iteration and emits `SUMMARY_EMITTED` instead of silently
discarding a generated-but-unscored image. The wrapper's `run_gen_eval` now
captures the child's event stream and a new `check_gen_eval_exhausted` state
distinguishes "child exhausted with usable output" (routes to
`finalize_partial` → `partial_done`, a distinct terminal) from "child errored"
(unchanged `diagnose → failed` path) — `loop:` sub-loop delegation only
natively supports `on_yes`/`on_no`/`on_error`, so this 3-way distinction is
implemented one state downstream of `run_gen_eval` rather than as a native
route. Also added a `.prompt_hash` staleness gate to `synthesize`, emitting
`IMAGE_FAIL` when `image-prompt.txt` is unchanged since the previous iteration
(iteration ≥ 2), reusing the existing `.gen_counter` read/compare/rewrite idiom.

Added structural tests (`fsm.max_steps`, `on_max_steps` presence) and a
behavioral test for the stale-prompt failure mode to
`test_flux_image_generator.py`. Updated `docs/guides/LOOPS_REFERENCE.md`'s flow
diagram and notes, and `scripts/little_loops/loops/README.md`'s catalog
summaries for both loops.

Deferred to BUG-2824: reordering the base `generator-evaluator` cycle so
`score`/`record_score` follow `evaluate` directly (shared by 6+ wrappers, out of
scope here).

---

## Status

- [x] Done

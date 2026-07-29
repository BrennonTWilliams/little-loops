---
id: BUG-2904
type: BUG
priority: P2
status: done
captured_at: '2026-07-28T00:00:00Z'
discovered_date: 2026-07-28
discovered_by: svg-image-generator-screenshot-hang-diagnosis
completed_at: '2026-07-29T02:58:06Z'
depends_on:
- BUG-2901
relates_to:
- BUG-2901
- ENH-2903
confidence_score: 100
outcome_confidence: 88
score_complexity: 23
score_test_coverage: 23
score_ambiguity: 20
score_change_surface: 22
---

# BUG-2904: generator-evaluator screenshot state has no timeout bound (1h per hang)

## Summary

The `evaluate` state in `scripts/little_loops/loops/oracles/generator-evaluator.yaml:74-84`
runs `playwright screenshot` with **no per-state `timeout:`**, so a hung Chromium
render blocks for a full hour per iteration.

This is distinct from and complementary to BUG-2901. That bug meant the timeout
path, when it fired, killed the wrong process group; this bug means for this
state the timeout effectively never fires at all. BUG-2901 had to land first —
without it, adding a timeout here would only convert a hang into a runner
suicide.

## Status

Open and **unblocked**. BUG-2901 is `done` — fixed by commit `e2cb3d8e`
(*fix(fsm): start shell actions in own process group to prevent runner self-kill
on timeout*), which added `start_new_session=True` to `DefaultActionRunner.run()`'s
shell path. The hard prerequisite is satisfied; this is ready to implement.

## Current Behavior

No `timeout:` is set on the state, and the loop sets no `default_timeout`. The
executor therefore falls back to `state.timeout or self.fsm.default_timeout or
3600` (`scripts/little_loops/fsm/executor.py:1706`) — a 3600s ceiling per
invocation.

`evaluate.type: output_contains` with `pattern: "CAPTURED"` cannot rescue this.
Playwright only emits `CAPTURED` on clean exit, so a process that never exits
never produces an evaluable verdict; the block is inside the action, upstream of
any routing.

`max_steps: 40` is not a practical bound either — it counts state transitions,
and the 7-state cycle fits roughly 5 `evaluate` invocations, each capable of
running the full 3600s fallback.

## Expected Behavior

A screenshot that has not completed within a small, explicit bound is terminated,
its process group reaped, and the action reports `exit_code: 124`.

**Caveat on "route on a real signal"** (added 2026-07-29): `exit_code: 124` will
be recorded in the event stream, but it is **not routable at this state**. The
state inherits `evaluate.type: output_contains` / `pattern: "CAPTURED"` from the
fragment, and `output_contains` never consults the exit code — only the
no-`evaluate:` default path calls `evaluate_exit_code`
(`scripts/little_loops/fsm/executor.py:1994`). A timeout therefore yields verdict
**`no`**, not `error`. Since `on_yes`/`on_no`/`on_error` all converge on
`snapshot`, this changes nothing for *this* issue — but it is the premise
[ENH-2903] was built on, and that issue has been corrected accordingly.

## Steps to Reproduce

Observed twice on consecutive runs (`svg-image-generator-20260728T171659` and
`...T175147`), identical symptom each time:

1. Run `ll-loop run svg-image-generator` against an SVG that stalls Chromium.
2. Observe the process tree: Playwright subprocess alive at 0% CPU, Chromium
   tree alive at 1.5–2.8% CPU.
3. Observe `screenshot.png` is never written.
4. Observe the event stream ends at:

```json
{"event": "action_output", "ts": "2026-07-28T23:04:03.756726+00:00",
 "line": "Capturing screenshot into /Users/.../screenshot.png", "depth": 1}
```

with no subsequent `action_output`, no `action_complete`, and no failure event.
`state.json` freezes at `status: running`, `state: run_gen_eval`, `iteration: 3`.

## Impact

Unattended runs stall for up to an hour per iteration and roughly five hours per
run, holding a live Chromium tree the whole time. Because no terminal event is
written, the failure presents as a silent hang, defeating post-hoc diagnosis via
`/ll:audit-loop-run` and `ll-history`.

## Proposed Solution

Add a per-state bound to the `evaluate` state:

```yaml
evaluate:
  timeout: 120
  fragment: playwright_screenshot
  ...
```

Deliberately **not** wrapping the action in coreutils `timeout(1)` (as the
original diagnosis suggested): it is redundant once BUG-2901 lands, `timeout` is
not present on stock macOS, and the FSM already owns timeout enforcement. Put
the bound in the layer that owns it.

Also deliberately **not** modifying the shared `playwright_screenshot` fragment
in `lib/harness.yaml:2-14`. That fragment has 5+ consumers
(`pixi-generative-art`, `generative-art`, `svg-textgrad`,
`generator-evaluator-cli`, `generator-evaluator-flux`) and is documented as
shared; a per-state `timeout:` is inheritance-free and each consumer can set its
own value.

This is additionally safe because **the `evaluate` state already overrides the
fragment's `action:` inline** (`generator-evaluator.yaml:75-81`, the Variant A
`$(pwd)/` path-expansion override the fragment's own description anticipates).
Only `evaluate.type: output_contains` / `pattern: "CAPTURED"` are actually
inherited. Adding `timeout:` alongside the existing override touches nothing any
other consumer reads.

## Open Questions

Resolved:

- **Per-state `timeout:` vs. loop-level `default_timeout:`.** Per-state, on
  `evaluate` only — a per-state bound touches only that state, while
  `default_timeout` would re-bound every state in the loop (including
  `generate`, which legitimately runs long).
- **Ceiling value: 120s.** Committing to this rather than the draft 90s to
  leave headroom over `--full-page` on heavy generated pages, while still
  bounding a hang to a couple minutes instead of an hour.
- **Sibling oracles: now in scope** (revised 2026-07-29). The original text
  deferred `generator-evaluator-cli.yaml` and `generator-evaluator-flux.yaml`
  to "a separate issue," which was never filed. Both are the identical one-line
  `timeout: 120` addition with identical rationale, so folding them in here is
  cheaper than tracking a third issue — and leaving them out means the same
  hour-long hang survives in two of the five wrappers' paths.

New:

- **Does `killpg` actually reap the Chromium tree?** `_kill_process_group`
  (`scripts/little_loops/fsm/runners.py:288-304`) SIGKILLs the action's process
  group, which BUG-2901 made distinct via `start_new_session=True`. That reaps
  Chromium only if neither Playwright's node wrapper nor Chromium itself calls
  `setsid`. Verify during implementation; if a detached tree survives, the
  host-level descendant counter deferred by [ENH-2903] becomes live again.

## Acceptance Criteria

- [x] BUG-2901 is merged (hard prerequisite) — commit `e2cb3d8e`.
- [x] The `evaluate` state in `generator-evaluator.yaml` carries an explicit
      `timeout: 120`.
- [x] The same bound is applied to the screenshot states in
      `generator-evaluator-cli.yaml` and `generator-evaluator-flux.yaml`.
      (`generator-evaluator-cli.yaml`'s local override already carried an
      explicit `timeout: 360`, which already satisfies "bounded" — left
      unchanged; `generator-evaluator-flux.yaml` gained a new `timeout: 120`.)
- [x] A hung screenshot terminates within that bound, and the `playwright`
      process plus its same-session descendants are reaped. (Stated in terms of
      the process group rather than "the Chromium tree" — `killpg` cannot
      guarantee reaping a descendant that has called `setsid`; see Open
      Questions.)
- [x] `lib/harness.yaml`'s shared fragment is unchanged.
- [x] `ll-loop validate` passes for all three oracles.
- [x] `python -m pytest scripts/tests/` exits 0.
- [x] New regression tests assert the screenshot state's `timeout` is a
      positive int in all three oracle test classes (see Tests below).

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — add
  `timeout: 120` to the `evaluate` state (lines ~74-84).
- `scripts/little_loops/loops/oracles/generator-evaluator-cli.yaml` — verify
  whether its screenshot-taking state overrides `evaluate` locally (in which
  case it needs its own explicit `timeout: 120`) or inherits it unmodified
  from `generator-evaluator.yaml` via `from:` (in which case the base-file
  edit propagates automatically through `resolve_inheritance` and no separate
  edit is needed here — confirm which applies before editing).
- `scripts/little_loops/loops/oracles/generator-evaluator-flux.yaml` — its
  `evaluate` state (line ~188-206) fully overrides the base with its own
  `cp`-based shell action and does **not** inherit from
  `generator-evaluator.yaml`'s `evaluate`, so it needs its own explicit
  `timeout: 120` added directly.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `TestGeneratorEvaluatorOracle`
  class (~line 9772-9876), alongside `test_evaluate_uses_playwright_screenshot_fragment`
  (line 9800). No existing test asserts anything about `evaluate`'s timeout —
  this is a pure gap, not a breaking change. Add a new test modeled on the
  precedent at `test_research_states_have_timeout_and_error_route`
  (line 10837, rn-refine tests):
  ```python
  def test_evaluate_has_bounded_timeout(self, data: dict) -> None:
      """BUG-2904: evaluate (Playwright screenshot) must not hang for the
      loop's full 7200s timeout on a headless-browser stall."""
      state = data["states"].get("evaluate", {})
      assert isinstance(state.get("timeout"), int) and state["timeout"] > 0, (
          "evaluate state must declare a positive per-state timeout (BUG-2904)"
      )
  ```
- Same assertion pattern needed in `TestGeneratorEvaluatorCliOracle`
  (`test_builtin_loops.py:9878+`, using its `resolved_data` fixture so
  inheritance is accounted for) and in whatever test class covers
  `generator-evaluator-flux.yaml` (see `scripts/tests/test_flux_image_generator.py:59`,
  `test_oracle_inherits_generator_evaluator` — flux's own `evaluate` override
  needs a direct, non-inherited assertion since it does not pick up the base
  fix).
- Confirmed no existing test breaks: `test_max_steps_covers_intended_cycle_count`,
  `test_has_on_max_steps_summary_handler`, and the fragment tests in
  `test_fsm_fragments.py` don't assert on `evaluate`'s timeout in either
  direction.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md` § "Timeouts" (~lines 1452-1480) — the
  canonical doc for the state-level-`timeout:`-overrides-`default_timeout`
  pattern this fix uses; already documents an MCP/Playwright-heavy-state
  callout at line 1473 that this fix is a concrete instance of. Optional
  cross-reference only — not required for correctness, no mechanical update
  needed.

### Verified: No Further Wiring Needed

_Wiring pass added by `/ll:wire-issue`:_ confirmed via codebase trace, no
changes needed in — `scripts/little_loops/fsm/schema.py` (`State.timeout`
already a modeled optional field), `scripts/little_loops/fsm/fsm-loop-schema.json`
(per-state `timeout` already declared), `scripts/little_loops/fsm/executor.py`
(`exit_code: 124` timeout convention already implemented end-to-end at
lines 1706, 1941-1942, 2526-2527), `scripts/little_loops/loops/lib/harness.yaml`
(the `playwright_screenshot` fragment sets no `timeout`, so no merge-precedence
conflict with any of the three state-level values), any `config-schema.json`/
`.ll/ll-config.json` surface, or `ll-loop` CLI code.


## Resolution

Added `timeout: 120` to the `evaluate` state in `generator-evaluator.yaml` and
`generator-evaluator-flux.yaml`. `generator-evaluator-cli.yaml`'s local
`evaluate` override already declared an explicit `timeout: 360`, so it was
left unchanged — already bounded. Added a `test_evaluate_has_bounded_timeout`
(or `_resolved_` variant) regression test to each of the three oracle test
classes asserting the state's `timeout` is a positive int.

## Session Log
- `/ll:manage-issue` - 2026-07-29T02:57:19Z - `1173d515-97b6-4d43-b274-2ea63aa3d3b0.jsonl`
- `/ll:ready-issue` - 2026-07-29T02:52:15 - `fc90cfce-6c97-4a48-9216-146d69f72171.jsonl`
- `/ll:confidence-check` - 2026-07-28T00:00:00Z - `5b9bd873-3256-4558-a40e-856d19ae9809.jsonl`
- `/ll:wire-issue` - 2026-07-29T02:49:13 - `7dcb9bbe-3a66-4dc1-b297-26ed0f30489c.jsonl`
- `/ll:refine-issue` - 2026-07-29T02:43:04 - `2c8cc461-78dd-4c0e-a077-682624fe62ad.jsonl`

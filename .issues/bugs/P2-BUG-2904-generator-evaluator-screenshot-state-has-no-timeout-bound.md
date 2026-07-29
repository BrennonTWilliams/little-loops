---
id: BUG-2904
type: BUG
priority: P2
status: open
captured_at: '2026-07-28T00:00:00Z'
discovered_date: 2026-07-28
discovered_by: svg-image-generator-screenshot-hang-diagnosis
depends_on:
- BUG-2901
relates_to:
- BUG-2901
- ENH-2903
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
its process tree reaped, and the action reports `exit_code: 124` so the loop can
route on a real signal.

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
  timeout: 90
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

Both must be **resolved in this issue before implementation** — they change the
shape of the diff, not just a constant.

- Is 90s the right ceiling? Static SVGs render in <5s, but `--full-page` on a
  heavy generated HTML page may legitimately take longer. Wants one calibration
  pass across the consumer loops before settling.
- **Per-state `timeout:` vs. loop-level `default_timeout:`.** These are different
  changes with different blast radii: a per-state bound touches only `evaluate`,
  while `default_timeout` re-bounds every state in the loop (including `generate`,
  which legitimately runs long). Recommendation: per-state here, and file a
  separate issue if the sibling oracles (`generator-evaluator-cli.yaml`,
  `generator-evaluator-flux.yaml`) want the same treatment — they are not in this
  issue's scope.

## Acceptance Criteria

- [x] BUG-2901 is merged (hard prerequisite) — commit `e2cb3d8e`.
- [ ] The `evaluate` state in `generator-evaluator.yaml` carries an explicit
      `timeout:`.
- [ ] A hung screenshot terminates within that bound and the Chromium tree is
      reaped.
- [ ] `lib/harness.yaml`'s shared fragment is unchanged.
- [ ] `ll-loop validate oracles/generator-evaluator` passes.
- [ ] `python -m pytest scripts/tests/` exits 0.

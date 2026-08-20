---
id: BUG-3262
type: BUG
title: html-website-generator smoke_test prepends cwd to an already-absolute run_dir,
  spinning until timeout
priority: P2
status: done
testable: true
program_design_not_applicable: true
discovered_by: manual-run
discovered_date: '2026-08-20'
captured_at: '2026-08-20T19:14:49Z'
completed_at: '2026-08-20T19:14:49Z'
---

# BUG-3262: html-website-generator smoke_test prepends cwd to an already-absolute run_dir, spinning until timeout

## Summary

`smoke_test` in `scripts/little_loops/loops/html-website-generator.yaml` built its
Playwright target URL as `'file://' + process.cwd() + '/${context.run_dir}/index.html'`.
But `run_dir` is *already* absolute — `cli/loop/run.py:198` and `cli/loop/lifecycle.py:666`
both set it to `str(loops_dir / "runs" / instance_id) + "/"`. The concatenation produced a
doubled path, `page.goto` raised `ERR_FILE_NOT_FOUND`, and the state's `on_error` route sent
the loop back to regenerate. Since the path never changes within a run, this never
recovered: the loop regenerated a passing artifact until the 3600s timeout and terminated
`failed`.

Observed on a real run (`html-website-generator-20260820T112153`, 2026-08-20): 70m40s,
10 iterations, 335K output / 14.9M cache tokens, terminal state `failed` — for an artifact
that had already passed at the 14-minute mark.

## Current Behavior

```js
await page.goto('file://' + process.cwd() + '/${context.run_dir}/index.html');
```

resolved to a URL with the repo root appearing twice — the cwd, then the absolute
`run_dir` concatenated onto it:

```
file://<repo-root>/<repo-root>/.loops/runs/<instance-id>//index.html
                   ^^ absolute run_dir appended to cwd
```

The generator-evaluator sub-loop *succeeded on every pass* — four `loop_complete` events
with `final_state: done`, `failure_terminal: false`, and `.screenshot_misses` at `0`. Each
time it returned, `smoke_test` crashed on the malformed path and routed back:

| time (UTC) | event |
|---|---|
| 16:38:01 | sub-loop `done` -> smoke_test -> `ERR_FILE_NOT_FOUND` -> `run_gen_eval` |
| 16:51:41 | same |
| 16:59:06 | same |
| 17:17:52 | same |
| 17:32:33 | outer `timeout` (3600s) -> `failed` |

The final `critique.md` scored the artifact 9/9/8/8 against a threshold of 6, and the
107KB `index.html` was functionally sound — a manual Playwright run against the correct
path returned `textLen 25097, errors []`. The artifact was fine the whole time; only the
gate was broken.

A second defect surfaced while fixing the first: **`on_no` was unreachable.** Every failure
branch in the script called `process.exit(1)`, so `FAIL:minimal_content` and
`FAIL:js_errors` — genuine artifact problems — registered as evaluator verdict `error`, not
`no`. The two routes were therefore indistinguishable in practice.

## Root Cause

Two independent gaps, both in the `smoke_test` state:

1. **No path normalization.** `oracles/generator-evaluator.yaml:78-80` and this same file's
   `vision_gate` state both already normalize defensively
   (`case "$RUN_DIR" in /*) ABS_DIR="$RUN_DIR" ;; *) ABS_DIR="$(pwd)/$RUN_DIR" ;; esac`).
   `smoke_test` was the only state in the loop that assumed a relative `run_dir`, and the
   only `process.cwd()` in the entire `loops/` tree.

2. **`on_error` treated a harness fault as an artifact fault.** Routing a failed *test* to
   "generate it again" is only correct when the artifact is what failed. A missing browser,
   an unreadable path, or a node fault means the artifact was never tested at all —
   regeneration cannot fix it, and each retry costs a full generate+evaluate cycle. This is
   the same reasoning ENH-2825 already applied to `vision_gate`.

## Expected Behavior

`smoke_test` resolves `run_dir` in whichever form it arrives, and distinguishes "the
artifact failed the test" (regenerate) from "the test could not run" (fail loudly).

## Steps to Reproduce

1. `ll-loop run html-website-generator "<any description>"` from a repo root.
2. Watch `.loops/.running/<instance>.events.jsonl` for the first `state_enter` of
   `smoke_test`.
3. Observe `action_complete` with `exit_code: 1` and a `stderr_preview` of
   `SMOKE_FAIL: page.goto: net::ERR_FILE_NOT_FOUND`, followed by
   `route: smoke_test -> run_gen_eval`.
4. The cycle repeats until `max_steps` or `timeout`; the loop never reaches `vision_gate`
   or `done`.

Deterministic — `run_dir` is absolute on every code path that sets it.

## Resolution

- **Action**: fix
- **Completed**: 2026-08-20
- **Status**: Completed

### Changes Made

- `scripts/little_loops/loops/html-website-generator.yaml`, `smoke_test` state:
  - Normalizes `run_dir` with the same `case` idiom already used by `vision_gate` and
    `oracles/generator-evaluator.yaml:78-80`, exports it as `ABS_DIR`, and navigates via
    `process.env.ABS_DIR` instead of prepending `process.cwd()`.
  - The content and JS-error checks now `exit(0)` so they register as verdict `no`
    (regenerate); only the `catch` block exits non-zero, registering as `error`. Without
    this, flipping `on_error` alone would have routed genuine artifact failures straight to
    `failed`.
  - `browser.close()` moved above the checks so the early exits do not leak a browser.
  - `on_error: run_gen_eval` -> `on_error: failed`, with a comment recording why the two
    routes differ.

### Verification Results

The action was rendered out of the YAML and executed from a repo root with `run_dir`
substituted, covering all three branches:

| scenario | output | exit | route |
|---|---|---|---|
| the real 107KB artifact from the failed run | `SMOKE_PASS` | 0 | `vision_gate` |
| `index.html` absent | `SMOKE_FAIL: ERR_FILE_NOT_FOUND` | 1 | `failed` |
| 28-byte stub page | `FAIL:minimal_content` | 0 | `run_gen_eval` |

- Tests: PASS — 1710 passed (`scripts/tests/test_builtin_loops.py`,
  `scripts/tests/test_fsm_fragments.py`). Scoped to the loop-schema suites; the full suite
  was not run for this YAML-only change.
- `ll-loop validate` schema check: PASS (via `test_builtin_loops.py`).

## Notes

**Sibling loops are clean.** `process.cwd()` appears nowhere else under
`scripts/little_loops/loops/`, and of the five sibling generator loops
(`svg-image-generator`, `html-anything`, `generative-art`, `p5js-sketch-generator`,
`interactive-component-generator`) only `interactive-component-generator` has a smoke state
at all — `smoke_component`, which sets no `on_error` and so is not exposed to this shape.

**One judgment call worth revisiting.** A missing `index.html` now routes to `failed` rather
than regenerating. That reads correct — the sub-loop screenshots `index.html` in order to
score it, so arriving at `smoke_test` without one means something structural is wrong,
and the sub-loop has its own screenshot-miss handling — but a case could be made for
treating it as a `no`.

**No cycling detection.** Four identical `run_gen_eval -> smoke_test -> run_gen_eval`
transitions with an unchanged verdict is a stalled-not-converging signal that nothing in
the FSM runner currently detects. Independent of this fix, and not addressed here.

## Program Design

N/A — `program_design_not_applicable: true`. The change is confined to one state's shell
action and its route table in a loop YAML: no types, no signatures, no Python call path.
The one design decision — which failures count as `no` versus `error` — is recorded under
Root Cause and Resolution.

## Impact

- **Priority**: P2 - the loop could not reach a terminal `done` state at all. Every run
  burned its full timeout and reported `failed` while sitting on a passing artifact, so the
  cost was both a broken feature and ~an hour of wasted model spend per invocation
- **Effort**: Small - one state in one loop YAML
- **Risk**: Low - the normalization is the idiom two neighbouring states already use, and
  the exit-code split makes a previously-dead route reachable rather than changing a live
  one
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `loops`, `fsm`, `harness`, `correctness`

## Status

**Done** | Created: 2026-08-20 | Completed: 2026-08-20 | Priority: P2


## Session Log
- `hook:posttooluse-status-done` - 2026-08-20T19:16:25 - `ac384ad1-3b5f-46bd-b8ff-0dd622dad506.jsonl`

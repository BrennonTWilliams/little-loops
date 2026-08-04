---
id: FEAT-3033
title: Plumb idle-timeout detection into the FSM action runner
type: FEAT
priority: P2
status: open
discovered_date: 2026-08-03
captured_at: "2026-08-04T04:17:13Z"
discovered_by: capture-issue
relates_to:
- BUG-3032
- BUG-2718
- BUG-2928
- BUG-1640
- BUG-1815
- ENH-2977
- FEAT-488
labels:
- fsm
- timeout
- runners
verify_verdict: VALID
---

# FEAT-3033: Plumb idle-timeout detection into the FSM action runner

## Summary

The FSM executor has exactly one liveness sensor: a wall-clock deadline. There
is no idle detection anywhere in `scripts/little_loops/fsm/` — `grep -rn
"idle" little_loops/fsm/runners.py little_loops/fsm/executor.py` returns
**zero** matches.

This matters because wall-clock duration carries no information about whether
an agent state is healthy. A long-running agent and a wedged one look identical
to a stopwatch. Idle time does carry that information: a process still emitting
output is demonstrably making progress.

The primitive already exists elsewhere in the tree. `idle_timeout` is
implemented and plumbed for `ll-auto` and `ll-parallel` (`subprocess_utils.py`,
`worker_pool.py:931`, surfaced as `--idle-timeout` by FEAT-488). It was never
extended to the FSM path.

**Two kinds of work, not one.** The FSM has four execution paths, and they need
different things:

| Path | Mechanism | Work required |
|---|---|---|
| **prompt** (`runners.py:131-186`, `is_slash_command`) | delegates to `run_claude_command()` | **pass-through only** — idle is already implemented at `subprocess_utils.py:476` |
| **baseline** (`executor.py:~2670`, `_run_baseline`) | calls `run_claude_command()` directly | **pass-through only** |
| **shell** (`runners.py:241-306`) | own selector loop | new tracking code |
| **mcp** (`executor.py:_run_subprocess`) | own selector loop | new tracking code |
| **sdk/batch** (`executor.py:_dispatch_live`) | no subprocess | out of scope — see below |

The prompt path is the one BUG-3032 is about, and it needs **no new idle
logic** — `run_claude_command` already accepts `idle_timeout: int = 0`
(`subprocess_utils.py:327`) and enforces it against stream-json event cadence.
Sequence the work accordingly: pass-through first (unblocks BUG-3032), selector
loops second (covers shell/mcp states).

## Motivation

This is the load-bearing prerequisite for BUG-3032. That issue proposes
removing the hard-coded 3600s wall-clock cap on FSM prompt states, which
silently overrides the multi-hour budgets 19 loops explicitly declare. But
removing a wall-clock cap without adding a replacement sensor would leave a
genuinely hung state bounded only by the loop-level budget — up to four days
for `goal-cluster.yaml`, `loop-router.yaml`, and the `loop-composer*` loops
(`timeout: 345600`).

Idle detection is what makes relaxing the wall-clock cap safe rather than
reckless. Order matters: this lands first, BUG-3032 second.

**Constraint this places on BUG-3032.** A default-off idle sensor plus a
removed wall-clock cap yields *no* sensor by default — `goal-cluster.yaml`-class
loops would fall straight back to the four-day budget, which is the outcome
this section calls unacceptable. Defaulting idle to `0` (recommended below, for
BUG-2718 reasons) is therefore only coherent if BUG-3032 takes one of:

- relax the cap **only** for states/loops that explicitly declare
  `idle_timeout` / `default_idle_timeout`, leaving 3600s in force otherwise; or
- ship a non-zero `default_idle_timeout` as part of BUG-3032, chosen from
  measured cadence rather than guessed.

The first is the safer default. Whichever is chosen, it belongs in BUG-3032's
acceptance criteria, not left implicit here.

Secondary value independent of BUG-3032: idle detection catches a class of
failure the wall clock misses entirely — a state that wedges at minute 2 of a
60-minute budget currently burns the remaining 58 minutes before anything
notices.

## Current Behavior

`FSMExecutor` and the `ActionRunner` implementations enforce a wall-clock
deadline only:

- `fsm/runners.py:241-306` — the shell path builds `deadline = time.time() +
  timeout`, then runs a selector loop with bounded polling
  (`sel.select(timeout=min(1.0, remaining))`), checking the wall-clock deadline
  before each read. It reads output but never timestamps it.
- `fsm/executor.py:2040-2125` — `_run_subprocess` (the MCP path) uses the same
  deadline-plus-selector shape, with the same omission.

On breach, `_kill_process_group` reaps the tree and the result is stamped
`exit_code=124`.

The prompt path is different, and is the reason this issue is smaller than it
looks. `runners.py:131-186` calls `run_claude_command(command=..., timeout=...,
...)` — and simply **never passes `idle_timeout`**, so it takes the parameter's
`0` default (disabled). The capability is present and unused.

The same call site then discards the one signal that already distinguishes the
two kill causes. `run_claude_command` raises
`subprocess.TimeoutExpired(cmd_args, idle_timeout, output="idle_timeout")` on an
idle kill versus a bare `TimeoutExpired(cmd_args, timeout)` on wall-clock
(`subprocess_utils.py:474-485`); `runners.py:186-194` catches `TimeoutExpired`
and flattens both to `exit_code=124`. Three call sites elsewhere already
discriminate correctly on this sentinel — `issue_manager.py:1899`,
`cli/sprint/run.py:110`, `cli/sprint/run.py:860`, all with the identical
`kind = "idle timeout" if exc.output == "idle_timeout" else "timeout"`.

There is no configuration surface for idle at any level: not on `stateConfig`,
not at the loop level in `fsm-loop-schema.json`, and not on `ActionRunner.run`.

## Expected Behavior

The FSM gains an idle sensor alongside the existing wall-clock one, following
the shape FEAT-488 established for `ll-auto`/`ll-parallel`.

- A new optional `idle_timeout` on `stateConfig`, and a loop-level
  `default_idle_timeout`, resolved with the same precedence chain the wall-clock
  timeout already uses (`state.idle_timeout or fsm.default_idle_timeout or
  <default>`).
- `0` disables idle detection, consistent with `idle_timeout_seconds` in
  `AutomationConfig` and with `ParallelConfig.idle_timeout_per_issue`.
- The resolved value reaches all four subprocess-backed paths: passed to
  `run_claude_command` on the prompt and baseline paths, and enforced by the
  new tracking in the shell and mcp selector loops.
- The selector loops in `runners.py` and `executor.py` track a
  `last_output_at` timestamp updated on every read, and terminate the process
  group when `time.time() - last_output_at > idle_timeout`, matching the
  semantics `subprocess_utils.py:476` already implements.
- An idle kill is **distinguishable from a wall-clock kill** — and the
  distinction must reach *loop authors*, not just logs.

  This requires an `ActionResult` field, **not** a new exit code. A new code
  does not work: `evaluators.py:1836` (BUG-1815) already short-circuits *any*
  non-zero exit to verdict `error` for every evaluator outside
  `_EXIT_CODE_AWARE_EVALUATORS`, so a hypothetical `exit_code=125` would land on
  `on_error:` alongside a wall-clock kill and be indistinguishable there —
  delivering none of the differentiated-recovery value that motivates this
  bullet. (Reusing `124` is separately ruled out: BUG-1640 wired it to
  short-circuit to `error` at `evaluators.py:1810-1817`.)

  Concretely: add a field such as `timeout_kind: "wall" | "idle" | None` to
  `ActionResult`, populated on the prompt/baseline paths from the existing
  `exc.output == "idle_timeout"` sentinel and on the selector paths from the
  new branch, then surface it into the interpolation context so transitions and
  guards can read it. Exit code stays `124` for both, preserving BUG-1640
  routing unchanged.

  **The author-facing path is `${prev.timeout_kind}`.** The seam is
  `self.prev_result` (`executor.py:1509` and `:1579`), which flows into
  `ctx.prev` at `executor.py:2773`. Two consequences that must be handled
  rather than discovered:

  - `prev_result` is serialized into checkpoints (`persistence.py:345`,
    restored at `:410`). A run resumed from a pre-change checkpoint has no
    `timeout_kind` key, so authored guards must be written
    `${prev.timeout_kind:default=}` — a bare reference raises
    `InterpolationError`. Document this in the guide, and make the round-trip
    tolerate the missing key rather than defaulting it at restore time.
  - Decide whether the `captured` namespace carries it too. `captured` entries
    are documented as `{output, stderr, exit_code, duration_ms}`
    (`interpolation.py:48`); omitting `timeout_kind` there leaves
    `capture:`-based guards unable to express what `prev`-based guards can.
    Recommendation: add it to both, so the two namespaces stay symmetric.

- **Timeout results report the elapsed duration, not the budget.** Every
  timeout path currently stamps `duration_ms = timeout * 1000`:
  `runners.py:191` (prompt), `runners.py:299` (shell), and
  `executor.py:2732` (`_run_baseline_arm`). An idle kill at minute 2 of a
  3600s budget therefore reports 3 600 000 ms. That corrupts telemetry, cost
  attribution, and any elapsed-based guard — and idle detection makes it far
  more common, since dying early is the entire point. All three become
  `_now_ms() - start`, which is already what the baseline arm's *success*
  path does two lines above the bug (`executor.py:2723`). This is in scope
  here rather than a follow-up: the feature actively worsens the defect.

## Proposed Solution

### Part 1 — pass-through (unblocks BUG-3032)

No new liveness logic. Resolve the value, hand it to the implementation that
already exists, and stop discarding the sentinel it already raises:

```python
# runners.py:131-186 (prompt path), currently:
completed = run_claude_command(command=action, timeout=timeout, ...)
except subprocess.TimeoutExpired:
    return ActionResult(output="", stderr="Action timed out", exit_code=124, ...)

# becomes:
completed = run_claude_command(
    command=action, timeout=timeout, idle_timeout=idle_timeout, ...
)
except subprocess.TimeoutExpired as exc:
    idled = exc.output == "idle_timeout"       # sentinel already set upstream
    return ActionResult(
        output="",
        stderr="Action idle-timed out" if idled else "Action timed out",
        exit_code=124,                          # unchanged — preserves BUG-1640
        timeout_kind="idle" if idled else "wall",
        ...
    )
```

The same two-line change applies to **`_run_baseline_arm`**
(`executor.py:2680`, invoked at `:2615`), which calls `run_claude_command`
directly rather than through an `ActionRunner`. Note it runs *concurrently*
with the harness arm in a `ThreadPoolExecutor` — both arms need the resolved
value, not just the harness one, or an A/B comparison would run the two arms
under different liveness rules.

### Part 2 — selector loops (shell and mcp states)

The two selector loops are near-identical in shape and should grow the same
three lines rather than diverging further:

```python
# runners.py:241 and executor.py:2057, currently:
deadline = time.time() + timeout
...
    ready = sel.select(timeout=poll_timeout)

# becomes:
deadline = time.time() + timeout if timeout else None
last_output_at = time.time()
...
    ready = sel.select(timeout=poll_timeout)
    if ready:
        last_output_at = time.time()      # any read counts as liveness
    if idle_timeout and (time.time() - last_output_at) > idle_timeout:
        idled_out = True
        break
```

Note the `if timeout else None` on the deadline — that is the seam BUG-3032
needs in order to express "no wall-clock cap," and it belongs in this change so
the two issues don't both edit the same expression.

Given how similar the two loops are, extracting the shared read-and-deadline
logic into one helper is worth considering, but is not required by this issue
and shouldn't gate it.

#### Blocking `readline()` defeats both sensors — resolve before implementing

The three-line patch above is *not sufficient on its own*. At
`runners.py:270`, `sel.select()` reports a pipe ready as soon as any bytes are
available, and the loop then calls `key.fileobj.readline()`, which blocks until
a newline arrives or the pipe reaches EOF. A child that writes a partial line
and then wedges blocks the loop indefinitely — past the wall-clock deadline and
past the new `last_output_at` check, because neither is reached again.
`executor.py:_run_subprocess` has the identical shape.

This is exactly the wedged-process case the feature exists to catch, so it
cannot be left implicit. Pick one and record it in the implementation:

- **Fix it** — read with `os.read(fd, N)` on the raw descriptor and buffer
  lines manually, so no read blocks past the poll window. This makes both
  sensors actually enforceable and is the recommended option; it is the larger
  share of step 5's cost.
- **Accept it** — keep `readline()` and document the limitation explicitly
  (idle detection covers silent children, not children stuck mid-line), so the
  gap is a known boundary rather than a surprise during a real incident.

Note this defect predates the issue — the wall-clock deadline is already
unenforceable in the same circumstance. This feature does not introduce it, but
it does make the gap load-bearing.

#### MCP path: the exit-code short-circuit does not apply

The "a new exit code cannot deliver differentiated recovery" argument in
*Expected Behavior* has one exception, and it lands on a path this issue
touches. `evaluators.py:1814` exempts `mcp_result` from the `exit_code == 124`
short-circuit because `evaluate_mcp_result` has its own `timeout` verdict. So
for mcp states the new selector-loop code must decide: keep emitting the
existing `timeout` verdict for both kill causes (simplest, and `timeout_kind`
remains the only discriminator, consistently with every other path), or add a
distinct verdict. **Recommendation: keep `timeout`** — a second verdict would
fork mcp-state authoring away from the uniform `${prev.timeout_kind}` idiom for
no added expressive power. Either way, state it; today it is unspecified.

### Out of scope

`_dispatch_live` (`executor.py`, the `sdk`/`batch` request paths) runs no
subprocess, so neither mechanism applies to it. It keeps wall-clock-only
behavior. State this explicitly rather than leaving it as an apparent
oversight; a follow-up can add SDK-level idle if it proves needed.

**No `ll-loop run --idle-timeout` flag.** The configuration surface this issue
adds is YAML-only: `idle_timeout` on `stateConfig` and `default_idle_timeout`
at the loop level. `add_idle_timeout_arg` (`cli_args.py:125`) exists and is
wired into `ll-auto`/`ll-parallel`, so adding it here is cheap — but a
run-level override interacts with per-state resolution in ways that belong with
ENH-2977's broader timeout-surface work, not bolted on mid-feature. Closing
this as a non-goal rather than leaving it open, so it isn't re-litigated during
implementation.

### Choosing a default

Prefer a conservative one (or `0`/disabled) initially. The agent-output cadence
in this codebase is not currently measured. Streaming agents can be quiet for
long stretches during synthesis; `lib/common.yaml:52-56` already notes
MCP-heavy prompts doing ~10 tool calls before producing output.

BUG-2718 is the usual precedent cited here — a fixed 30s kill that destroyed
legitimate parallel subagent work — and it is a fair general caution against
guessing tight. But weigh it accurately: **BUG-2718 was a *post-stream-close*
grace kill**, firing after the child's stdout/stderr had already closed while
blocking subagent work was still in flight. Stream-idle is structurally
different — it measures gaps *between* events on a live stream, and a
synthesizing agent still emits tool-use events. BUG-2718 argues for not
guessing tight; it does not by itself argue for disabled-by-default.

The stronger argument for starting at `0` is simply that cadence is unmeasured.
Measuring it (max inter-event gap across a sample of real prompt-state runs)
would be a cheap way to retire that uncertainty and is a reasonable precursor
to BUG-3032's default choice.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/runners.py` — `ActionRunner.run` (the `Protocol` at
  line 36) gains `idle_timeout`. Two distinct edits inside the runner: the
  prompt branch (131-186) forwards it to `run_claude_command` and reads
  `exc.output` in the `TimeoutExpired` handler; the shell selector loop
  (241-306) tracks `last_output_at`. `SimulationActionRunner` (line 338-368,
  which currently does `del timeout, ...`) also needs the parameter — it has no
  `**kwargs`, so an unrecognised kwarg is a `TypeError`.
- `scripts/little_loops/fsm/executor.py` — `_run_subprocess` (line 2040) gains
  the tracking. Four call sites resolve and pass the value, and they are **not**
  all the same shape:
  - `~1825` — mcp path into `_run_subprocess`. Note its wall-clock fallback is
    `state.timeout or self.fsm.default_timeout or 30` (30, not 3600); the idle
    precedence chain should mirror whatever this does rather than assume 3600.
  - `~1835` — contributed-action runner (`self._contributed_actions[...]`), a
    separate third-party runner surface that needs the same kwarg-gating.
  - `~1866` — the main `self.action_runner.run(...)` call (prompt + shell).
  - `2680` — **`_run_baseline_arm`, which calls `run_claude_command` directly**,
    not `_run_subprocess` (invoked from the `ThreadPoolExecutor` at `:2615`).
    Pass-through edit, per Part 1.
- `scripts/little_loops/fsm/types.py` — `ActionResult` (line 89) gains
  `timeout_kind: str | None = None`, defaulted so every existing construction
  site keeps working.
- `scripts/little_loops/fsm/persistence.py:345, 410` — `prev_result` is
  checkpointed and restored; the restore path must tolerate a `timeout_kind`
  key absent from pre-change checkpoints.
- `scripts/little_loops/fsm/schema.py` — `StateConfig` (line 658 area) gains
  `idle_timeout: int | None`; `FSMConfig` (line 1281 area) gains
  `default_idle_timeout`; both need `from_dict`/`to_dict` round-tripping
  (lines 875, 1544, 1378).
- `scripts/little_loops/fsm/fsm-loop-schema.json` — new properties on
  `stateConfig` and at the root. Use `minimum: 0` (not `minimum: 1`, which the
  existing timeout properties use) so `0` can express "disabled."

### Dependent Files

- `scripts/little_loops/fsm/validation/_base.py:95` — the known-keys list that
  includes `default_timeout`; the new loop-level key must be added or
  validation will reject it.
- Third-party / extension `ActionRunner` implementations — the new parameter
  must be **kwarg-gated**, following the `working_dir` and
  `automation_profile` precedent at `executor.py:1841-1862`, so runners
  predating this change keep working.

### Similar Patterns

- `scripts/little_loops/subprocess_utils.py:327, 460-490` — not merely a
  "similar pattern" but the **actual implementation the prompt and baseline
  paths reuse**. The reference for semantics (`0` = disabled), for the kill
  sequence, and for the `output="idle_timeout"` sentinel.
- `scripts/little_loops/issue_manager.py:1899`, `cli/sprint/run.py:110`,
  `cli/sprint/run.py:860` — the three existing consumers of that sentinel,
  all spelling it `exc.output == "idle_timeout"`. Match this rather than
  inventing a fourth convention.
- `scripts/little_loops/parallel/worker_pool.py:926-931` — shows wall-clock and
  idle passed side by side into `_run_claude_base`, which is the end state for
  the FSM call sites.
- `scripts/little_loops/cli_args.py:125` — `add_idle_timeout_arg`, already
  wired into `ll-auto` and `ll-parallel`. Whether `ll-loop run` should get the
  same flag is an open scope question; it overlaps ENH-2977.

### Tests

- `idle_timeout=0` disables idle detection entirely (process producing no
  output runs to the wall-clock deadline). Assert for both the shell path and
  the prompt path.
- A process that emits output steadily past `idle_timeout` is **not** killed —
  the regression guard for the whole feature.
- A process silent longer than `idle_timeout` is killed, and its result carries
  `timeout_kind == "idle"` while a wall-clock kill carries `"wall"` — both
  still `exit_code=124`.
- Prompt path specifically: a `TimeoutExpired` raised with
  `output="idle_timeout"` maps to `timeout_kind="idle"`, and a bare one maps to
  `"wall"`. This is the unit test that guards `runners.py:186-194` against
  re-flattening the distinction.
- `exit_code=124` still routes to verdict `error` via BUG-1640 regardless of
  `timeout_kind` — guards against the new field perturbing existing routing.
- `timeout_kind` is readable from a transition guard as
  `${prev.timeout_kind}` (the acceptance test for the differentiated-recovery
  use case; without it the field is write-only and the feature's stated benefit
  is undelivered). Include the `captured` namespace if that decision lands
  symmetric.
- A checkpoint written before this change restores without error, and
  `${prev.timeout_kind:default=}` resolves empty rather than raising
  (`persistence.py:410` round-trip guard).
- **`duration_ms` on a timeout reflects elapsed time, not the budget.** A state
  with `timeout: 3600` killed after ~2s reports a `duration_ms` in the seconds
  range, not 3600000. Assert on all three paths: prompt (`runners.py:191`),
  shell (`runners.py:299`), and `_run_baseline_arm` (`executor.py:2732`).
- Selector-loop liveness under the chosen read strategy: a child that writes a
  partial line (no trailing newline) and then goes silent is still killed at
  `idle_timeout` — the regression guard for the blocking-`readline()` decision.
  If the "accept it" option is taken instead, this test asserts and documents
  the *current* behavior so the boundary is pinned rather than accidental.
- mcp path: an idle kill still produces the `mcp_result` `timeout` verdict
  (unchanged routing), with the distinction carried only by `timeout_kind`.
- Precedence: `state.idle_timeout` overrides `fsm.default_idle_timeout`.
- An `ActionRunner` implementation not accepting the new kwarg still runs
  (kwarg-gating regression guard), including `SimulationActionRunner`.

### Documentation

- `docs/guides/` FSM/loop-authoring guide — document the new fields and, in
  particular, when idle is the right sensor and wall-clock is not.
- `scripts/little_loops/loops/lib/common.yaml:47-56` — the `llm_gate` fragment's
  timeout-budget prose predates this and should mention idle.
- `CHANGELOG.md` — new entry, in a concrete version section (not
  `[Unreleased]`).

## Implementation Steps

Ordered so that BUG-3032 is unblocked at step 4, before the selector-loop work
begins.

1. Add `idle_timeout` / `default_idle_timeout` to `schema.py` and
   `fsm-loop-schema.json`, with `minimum: 0` and round-trip coverage; add the
   loop-level key to `validation/_base.py`.
2. Add `timeout_kind` to `ActionResult` (`types.py:89`) and surface it via
   `prev_result` → `${prev.timeout_kind}`, including the `persistence.py`
   round-trip tolerance for checkpoints lacking the key. Confirm
   `exit_code=124` routing through `evaluators.py` is unchanged (BUG-1640
   short-circuit intact).
3. Prompt path: forward `idle_timeout` to `run_claude_command` and stop
   flattening the sentinel in the `TimeoutExpired` handler
   (`runners.py:131-194`). Same for `_run_baseline_arm`. Fix `duration_ms` to
   elapsed rather than budget on all three timeout paths while in these
   handlers.
4. Resolve and pass the value at the executor call sites, kwarg-gated on
   `ActionRunner.run` per the `working_dir` / `automation_profile` precedent;
   add the parameter to `SimulationActionRunner` and the contributed-action
   runner surface. **BUG-3032 is unblocked here.**
5. **Decide the blocking-`readline()` question first** (fix via `os.read` vs.
   document the limitation) — it sizes the rest of this step. Then add
   `last_output_at` tracking to the `runners.py` shell selector loop and mirror
   it in `executor.py:_run_subprocess`, including the
   `deadline = ... if timeout else None` seam BUG-3032 needs, and settle the
   mcp `timeout`-verdict question.
6. Tests per above.
7. Docs, including the explicit `_dispatch_live` out-of-scope note.

## Impact

- **Priority**: P2 — blocks BUG-3032, which is affecting live multi-hour loops.
  Not P1 on its own, since nothing is broken today by its absence; the harm is
  that the only available sensor is the wrong one.
- **Effort**: Small-Medium, and front-loaded in the cheap half. The BUG-3032
  unblock (steps 1-4) is schema plumbing plus a parameter pass-through to an
  implementation that already exists and is already tested — no new liveness
  logic. The selector-loop work (step 5) is the genuinely new code, and it
  serves shell/mcp states rather than the motivating case. The
  schema/round-trip/validation surface and kwarg-gating across three runner
  surfaces (`ActionRunner`, `SimulationActionRunner`, contributed actions) are
  the real cost — plus, if the blocking-`readline()` fix is taken, replacing
  `readline()` with buffered `os.read` in two selector loops. That decision is
  the single largest swing in this issue's size; steps 1-4 are unaffected
  either way.
- **Risk**: Low-Medium. Additive and default-off. Two genuine risks:
  choosing a default idle value too aggressive for streaming agent cadence
  (mitigated by defaulting to disabled and letting loop authors opt in), and
  perturbing the BUG-1640 / BUG-1815 exit-code routing — mitigated by keeping
  `exit_code=124` for both kill causes and carrying the distinction in a new
  field instead.
- **Breaking Change**: No, provided the new runner parameter is kwarg-gated.

## Related Key Documentation

- `docs/reference/API.md` — documents the `fsm` module surface, including
  `ActionRunner`, whose signature this changes.
- `.claude/CLAUDE.md` § Loop Authoring — the FSM design rules (MR-1..MR-14) and
  the harness-optimization guide this feature's new fields become part of.

## Status

**Open** | Created: 2026-08-03 | Priority: P2

Captured from a review of ENH-2977, during a broader discussion of whether
FSM loops have too many timeouts. Established as the prerequisite for
BUG-3032 after confirming the FSM path has no idle sensor at all.

Revised 2026-08-03 after a pre-implementation code review, which found that the
original framing pointed the work at the wrong paths. Corrections applied: the
prompt path (the one BUG-3032 is about) already reaches an idle implementation
via `run_claude_command` and needs pass-through only; the idle-vs-wall-clock
signal already exists as the `output="idle_timeout"` sentinel and is discarded
at `runners.py:186`; a new exit code cannot deliver differentiated recovery
because of the BUG-1815 short-circuit, so the distinction moves to an
`ActionResult` field; `executor.py:~2670` is `_run_baseline`, not a
`_run_subprocess` call site; `_dispatch_live` is now explicitly out of scope;
and the default-off recommendation is reconciled with BUG-3032's sequencing.

Revised 2026-08-04 after a second pre-implementation review that re-verified
every code reference against the tree (all confirmed accurate). Six additions:
blocking `readline()` in both selector loops defeats the new idle sensor *and*
the existing wall-clock one, so the three-line patch is insufficient and the
fix-vs-document decision is now called out as step 5's sizing question;
`duration_ms = timeout * 1000` on all three timeout paths reports the budget
rather than elapsed time, a defect this feature actively worsens and therefore
fixes; the interpolation seam is named concretely as `${prev.timeout_kind}`
with its `persistence.py` checkpoint round-trip and `:default=` requirement;
the `mcp_result` evaluator is identified as the one exception to the
exit-code short-circuit argument, with `timeout` recommended as the unchanged
verdict; `_run_baseline` corrected to `_run_baseline_arm` (`executor.py:2680`),
noting both A/B arms need the value; and the `ll-loop run --idle-timeout` open
scope question is closed as a non-goal, deferred to ENH-2977.

## Session Log
- `/ll:verify-issues` - 2026-08-04T04:54:17 - `0645ab21-f89c-4db8-a208-435d990eba38.jsonl`
- `/ll:capture-issue` - 2026-08-04T04:20:07 - `62eddd57-7e6c-4ca5-b631-081e050a3dc6.jsonl`

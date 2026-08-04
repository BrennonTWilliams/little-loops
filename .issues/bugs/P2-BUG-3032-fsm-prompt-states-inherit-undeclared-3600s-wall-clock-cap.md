---
id: BUG-3032
title: FSM prompt states inherit an undeclared 3600s cap that overrides loop-level budgets
type: BUG
priority: P2
status: open
discovered_date: 2026-08-03
captured_at: "2026-08-04T04:17:13Z"
discovered_by: capture-issue
depends_on:
- FEAT-3033
relates_to:
- FEAT-3033
- BUG-2718
- BUG-2928
- BUG-2904
- BUG-773
labels:
- fsm
- timeout
- executor
verify_verdict: NON_VALID
---

# BUG-3032: FSM prompt states inherit an undeclared 3600s cap that overrides loop-level budgets

## Summary

Every `action_type: prompt` state in every FSM loop is silently capped at one
hour of wall-clock time by a hard-coded literal in the executor, regardless of
the budget the loop declares. Agent states that exceed it are SIGKILLed and
their output discarded unexamined.

`scripts/little_loops/fsm/executor.py:1862` and `:1893`:

```python
timeout=state.timeout or self.fsm.default_timeout or 3600
```

Across `scripts/little_loops/loops/` there are **91 loops, and exactly one**
(`general-task.yaml:6`, `default_timeout: 14400`) sets `default_timeout`. The
other 90 inherit the literal for every state that doesn't set its own
`timeout:`.

## Current Behavior

The trailing `or 3600` acts as an invisible ceiling that contradicts explicit
author intent. Nineteen loops declare multi-hour to multi-day budgets while
each of their individual states is capped at 60 minutes:

| Loop | Declared `timeout:` | Effective per-state cap |
|---|---|---|
| `goal-cluster.yaml` | 345600 (4 days) | 3600 |
| `loop-router.yaml` | 345600 (4 days) | 3600 |
| `loop-composer.yaml`, `loop-composer-adaptive.yaml` | 345600 (4 days) | 3600 |
| `rn-build.yaml` | 86400 (24h) | 3600 |
| `issue-refinement.yaml` | 86400 (24h) | 3600 |
| `worktree-health.yaml` | 86400 (24h) | 3600 |
| `scan-and-implement.yaml` | 36000 (10h) | 3600 |
| `autodev.yaml` | 28800 (8h) | 3600 |
| `recursive-refine.yaml` | 28800 (8h) | 3600 |
| `auto-refine-and-implement.yaml` | 28800 (8h) | 3600 |
| `prompt-across-issues.yaml` | 28800 (8h) | 3600 |
| `rn-implement.yaml` | 28800 (8h) | 3600 |
| `sprint-build-and-validate.yaml` | 25200 (7h) | 3600 |
| `eval-driven-development.yaml`, `harness-multi-item.yaml`, `outer-loop-eval.yaml`, `rn-remediate.yaml`, `interactive-component-generator.yaml` | 14400 (4h) | 3600 |

None of these loops sets `default_timeout`, so a loop declaring a four-day
budget still kills any single agent state at the one-hour mark.

**The kill is maximally destructive.** On breach the process group is SIGKILLed
(`_kill_process_group`) and the result stamped `exit_code=124`. Then
`fsm/evaluators.py:1814-1818` (BUG-1640) short-circuits:

```python
if exit_code == 124 and eval_type != "mcp_result":
    return EvaluationResult(verdict="error", ...)
```

The evaluator never runs, so whatever the agent produced in those 60 minutes is
discarded without being examined. There is no handoff and no partial credit. A
state 55 minutes into productive work that needed 70 is indistinguishable from
one that wedged at minute one.

## Expected Behavior

A wall-clock cap on an agent state should be something a loop author opts into,
not something inherited invisibly — and it should never be tighter than the
budget the loop explicitly declares.

- Prompt-mode states default to **no wall-clock cap** (`None`), relying on
  FEAT-3033's idle detection to catch genuine hangs. Duration is not evidence of
  ill health for an agent; silence is.
- Author-declared `state.timeout` and loop-level `default_timeout` remain
  authoritative and unchanged.
- Loop-level `timeout:` remains the real backstop — it is author-declared, it is
  what these 19 loops already use correctly, and it is enforced independently at
  `executor.py:546-567`.
- **Shell and MCP states keep their bounded defaults.** The `or 30` at
  `executor.py:1825` (MCP) is correct and should not change: those states run
  `git`, validators, and `ll-issues` queries, where overrun genuinely does mean
  hung.

## Root Cause

`scripts/little_loops/fsm/executor.py`, in the action-dispatch block — the
`or 3600` terminal fallback on the `contributed` (line 1862) and default
`action_runner.run` (line 1893) paths, plus the same expression at line 2697.

The literal is not a considered default for agent work; it is a backstop that
was never revisited as loops grew to multi-day budgets. `scripts/little_loops/
loops/lib/common.yaml:52-56` documents it, but frames it as a safe ceiling and
warns only against setting `default_timeout` too **low**:

> The 3600s executor fallback only applies when neither state-level `timeout:`
> nor loop-level `default_timeout:` is set — a low `default_timeout:` bypasses
> the fallback and will kill MCP-heavy prompts mid-synthesis.

That prose does not recognize that 3600 is itself the ceiling being hit.

## Frequency

Affects 90 of 91 loops on every prompt state that doesn't set `timeout:`.
Manifests whenever a single agent state legitimately exceeds one hour — which
the declared budgets above show is expected behavior for the long-running
loops, not an edge case.

## Proposed Fix

Change the prompt-mode fallback to `None` (no wall-clock cap), leaving
`state.timeout` and `fsm.default_timeout` authoritative and leaving the MCP/shell
`or 30` untouched:

```python
# executor.py:1866 — prompt / contributed paths
timeout=state.timeout or self.fsm.default_timeout,   # None => no wall-clock cap
```

This requires the downstream runner to accept `None` as "no deadline" — the
seam FEAT-3033 introduces when it makes `deadline` conditional. **That is why
this issue depends on FEAT-3033**: shipping this alone would leave a genuinely
hung state bounded only by the loop-level budget, which for `goal-cluster` and
the `loop-composer*` loops is four days.

Two adjacent cleanups worth folding in:

1. `loops/lib/common.yaml:47-56` — the `llm_gate` fragment's timeout-budget
   prose describes the old behavior and must be rewritten.
2. `issue-refinement.yaml` no longer contains the `default_timeout: 3600` that
   BUG-773 recorded as present (it now has only `timeout: 86400`). Worth a
   glance during implementation to confirm that removal was deliberate rather
   than an unnoticed regression.

**Out of scope**: changing loop-level `timeout:` values in any YAML; the
`minimum: 1` constraint in `fsm-loop-schema.json` that prevents expressing
`default_timeout: 0` as an explicit opt-out (a separate, smaller gap).

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/executor.py` — lines 1862, 1893, 2697: drop the
  `or 3600` terminal fallback on prompt/contributed paths. Line 1852 (`or 30`,
  MCP) unchanged.
- `scripts/little_loops/loops/lib/common.yaml` — lines 47-56, the `llm_gate`
  timeout-budget prose.

### Dependent Files

- `scripts/little_loops/fsm/runners.py` — must handle `timeout=None`; delivered
  by FEAT-3033.
- `scripts/little_loops/fsm/evaluators.py:1810` — the 124 short-circuit is not
  changed by this issue, but becomes rarer on the prompt path. Its behavior for
  author-declared timeouts is unchanged and correct.
- `scripts/little_loops/fsm/stall_detector.py` — already treats
  `(state, 124, error)` as a stall signal. Unchanged, but note that with fewer
  spurious 124s, this detector gets a cleaner signal rather than a worse one.

### Similar Patterns

Four completed P2 bugs in this same class — a fixed timeout killing legitimate
long-running work — establish both the pattern and the appetite for fixing it:

- **BUG-2718** — fixed 30s post-stream-close kill killed parallel subagents.
- **BUG-2928** — 120s subprocess default killed every queued FSM loop run.
- **BUG-2904** — a state with no per-state `timeout:` "blocks for a full hour
  per iteration": direct observation of this exact fallback, fixed there by
  bounding a *shell* state (consistent with keeping shell defaults bounded).
- **BUG-773** — added `default_timeout: 3600` to `issue-refinement.yaml`.

### Tests

- A prompt state with neither `state.timeout` nor `fsm.default_timeout` set
  receives no wall-clock deadline (the core regression guard — assert the value
  passed to the runner is `None`, not `3600`).
- An MCP/shell state with neither set still receives `30` — pins that this
  change did not leak into the bounded paths.
- `state.timeout` and `fsm.default_timeout` still take precedence, in that
  order.
- Loop-level `timeout:` still terminates a run (`executor.py:546-567`) when no
  per-state cap exists — proves the backstop survives.
- A long-running prompt state that would previously have been killed at 3600s
  now runs to completion and its output reaches the evaluator rather than being
  short-circuited to `error`.

### Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — if it documents timeout
  defaults, update.
- `CHANGELOG.md` — new entry in a concrete version section, not `[Unreleased]`.

## Implementation Steps

1. Land FEAT-3033 first (`timeout=None` support and idle detection).
2. Drop the `or 3600` at `executor.py:1835`, `:1866`, `:2670`.
3. Rewrite the `lib/common.yaml` `llm_gate` timeout prose.
4. Add the tests above, especially the MCP `or 30` non-leak guard.
5. Spot-check `issue-refinement.yaml`'s missing `default_timeout`.

## Impact

- **Priority**: P2 — actively destroying agent work in live multi-hour loops,
  silently and with no partial credit. Not P1 only because loop authors can work
  around it today by setting `default_timeout` explicitly.
- **Effort**: Small once FEAT-3033 lands — three expressions and a docs block.
  The tests matter more than the change.
- **Risk**: Medium, and concentrated in ordering. Removing a wall-clock cap
  before idle detection exists would convert "work killed at 1h" into "hung
  state occupies a worker for up to 4 days," which is worse. The `depends_on`
  is load-bearing, not decorative.
- **Breaking Change**: Behavioral, but strictly in the direction of honoring
  declared intent. Any loop relying on the 3600 cap was relying on undeclared
  behavior that contradicts its own `timeout:` field; such a loop can set
  `default_timeout: 3600` to restore the old ceiling explicitly.

## Related Key Documentation

- `.claude/CLAUDE.md` § Loop Authoring — the FSM design rules and the
  harness-optimization guide governing loop shape.
- `docs/reference/API.md` — documents the `fsm` module surface, including the
  executor dispatch path this changes.

## Status

**Open** | Created: 2026-08-03 | Priority: P2

Captured while reviewing ENH-2977, after the observation that FSM timeouts have
historically done more harm than good. Investigation found the harm is not the
number of timeouts but this one undeclared default, and that four prior P2 bugs
share its shape.

## Verification Notes

Verified 2026-08-03 via `/ll:verify-issues`. Core diagnosis, root cause, and
proposed fix are all still accurate. Line-number citations had drifted since
capture (likely from FEAT-2675's compression block and ENH-2714's
pruning-profile block landing in `executor.py` in between) and were corrected
in place:

- `or 30` (MCP path): `:1825` → `:1852`
- `or 3600` (contributed-action path): `:1835` → `:1862`
- `or 3600` (main `action_runner.run`): `:1866` → `:1893`
- `or 3600` (`_run_baseline`): `:2670` → `:2697`
- `evaluators.py` BUG-1640 short-circuit: `:1810-1817` → `:1814-1818`

`loops/lib/common.yaml:47-56`, `general-task.yaml:6`
(`default_timeout: 14400`), and `issue-refinement.yaml`'s `timeout: 86400`
with no `default_timeout` all confirmed exact, as-is.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-04T04:56:49 - `d6fd3e14-c984-4d6e-aad4-732de84b59ce.jsonl`
- `/ll:verify-issues` - 2026-08-04T04:54:17 - `0645ab21-f89c-4db8-a208-435d990eba38.jsonl`
- `/ll:capture-issue` - 2026-08-04T04:20:07 - `62eddd57-7e6c-4ca5-b631-081e050a3dc6.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): FEAT-3033 states that unconditionally
removing the wall-clock cap is only safe if idle detection actually ships enabled for
the affected states — its recommended default is `idle_timeout=0` (disabled), and it
requires BUG-3032 to take one of two options to stay coherent: (a) relax the cap
**only** for states/loops that explicitly declare `idle_timeout` /
`default_idle_timeout`, leaving 3600s in force otherwise; or (b) ship a non-zero
`default_idle_timeout` chosen from measured cadence. This issue's current Expected
Behavior/Tests remove the cap unconditionally regardless of whether idle detection is
configured, which would reproduce the "hung state occupies a worker for up to 4 days"
outcome flagged in this issue's own Risk section. Implementation must pick (a) or (b)
above — (a) is the safer default per FEAT-3033 — before landing the `or 3600` removal.

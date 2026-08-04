---
id: BUG-3032
title: FSM prompt states inherit an undeclared 3600s cap that overrides loop-level
  budgets
type: BUG
priority: P2
status: open
discovered_date: 2026-08-03
captured_at: '2026-08-04T04:17:13Z'
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
confidence_score: 80
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
decision_needed: false
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

## Steps to Reproduce

1. Take any loop declaring a multi-hour budget and no `default_timeout` — e.g.
   `scripts/little_loops/loops/autodev.yaml` (`timeout: 28800`, 8h).
2. Pick any `action_type: prompt` state in it that sets no per-state `timeout:`.
3. Run the loop with `ll-loop run autodev` and let that state do work that
   legitimately exceeds 60 minutes (a large implement-and-test state on a
   substantial issue reaches this routinely).
4. At the 3600s mark the state's process group is SIGKILLed
   (`_kill_process_group`) and the result stamped `exit_code=124`, despite the
   loop declaring an 8-hour budget.
5. `fsm/evaluators.py:1814-1818` short-circuits on `exit_code == 124`, so the
   evaluator never runs and the 60 minutes of output is discarded unexamined.

Minimal equivalent without a live run: assert the `timeout` value reaching
`ActionRunner.run` for a prompt state whose loop sets neither `state.timeout`
nor `default_timeout`. It is `3600` regardless of the loop-level `timeout:`.

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

Per the Option A decision recorded below, the relaxation is **gated on an
explicit idle opt-in**, not unconditional:

- A **prompt-mode** state that resolves a non-zero idle timeout
  (`state.idle_timeout or fsm.default_idle_timeout`) gets **no wall-clock cap**,
  relying on FEAT-3033's idle detection to catch genuine hangs. Duration is not
  evidence of ill health for an agent; silence is.
- A prompt-mode state with **no** idle opt-in keeps the `3600` fallback. The
  other 90 loops are unchanged until they declare idle.
- Author-declared `state.timeout` and loop-level `default_timeout` remain
  authoritative and unchanged, and continue to win over both of the above.
- Loop-level `timeout:` remains the real backstop — it is author-declared, it is
  what these 19 loops already use correctly, and it is enforced independently at
  `executor.py:546-567`.
- **Shell and MCP states keep their bounded defaults**, *including* when the
  loop declares `default_idle_timeout`. The `or 30` at `executor.py:1852` (MCP)
  is correct and should not change: those states run `git`, validators, and
  `ll-issues` queries, where overrun genuinely does mean hung. See the
  `action_mode` gating note under Files to Modify — the shell path shares
  line 1893 with prompt, so this is not automatic.

**The "no cap" sentinel is `0`, not `None`.** `run_claude_command` already
documents `timeout: Timeout in seconds (0 for no timeout)`
(`subprocess_utils.py:346`) and guards with `if timeout and (now - start_time) >
timeout` (`:465`), so the prompt path needs no new downstream seam at all.
`None` is additionally unsafe: `runners.py:191` and `:299` stamp
`duration_ms=timeout * 1000`, which is a `TypeError` on `None` (and a misleading
`0` until FEAT-3033 converts those to elapsed time — see Risk).

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

Make the `3600` fallback conditional on the idle chain resolving to zero, at the
one dispatch branch that serves prompt mode (`executor.py:1893`), leaving
`state.timeout` and `fsm.default_timeout` authoritative and leaving the MCP
`or 30` and the shell path untouched:

```python
# executor.py:1893 — the shared prompt/shell `else:` branch
_idle = state.idle_timeout or self.fsm.default_idle_timeout or 0   # FEAT-3033
_wall_fallback = 0 if (action_mode == "prompt" and _idle) else 3600
...
    timeout=state.timeout or self.fsm.default_timeout or _wall_fallback,
```

Two gates are load-bearing here and neither is optional:

- `action_mode == "prompt"` — line 1893 dispatches **shell states too**
  (`is_slash_command=action_mode == "prompt"`, `:1895`). Without this gate a
  loop-level `default_idle_timeout` silently un-caps every shell state in the
  loop.
- `_idle` truthiness — the Option A opt-in. With no idle sensor declared, the
  `3600` fallback stays exactly as it is today.

**This is why the issue depends on FEAT-3033**: shipping the relaxation without
an idle sensor in place would leave a genuinely hung state bounded only by the
loop-level budget, which for `goal-cluster` and the `loop-composer*` loops is
four days.

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

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-04 — based on codebase analysis:_

**Option A**: Relax the wall-clock cap only for states/loops that explicitly declare `idle_timeout` / `default_idle_timeout` — reusing the existing `state.X or fsm.default_X or <fallback>` precedence-chain shape already in force for `timeout`/`default_timeout` (`fsm/executor.py:1852,1862,1893`). The `or 3600` fallback stays in effect for any state/loop that has not opted in.

> **Selected:** Option A — matches the codebase's established "explicit non-zero opt-in, 0/disabled default" convention and confines any miscalibration risk to loops that opt in, rather than guessing a global default with no measurement backing it.

**Option B**: Ship a non-zero `default_idle_timeout` chosen from measured agent-output cadence, applied as the new global default so the `or 3600` removal in BUG-3032's Proposed Fix snippet is unconditional for every prompt state.

**Recommended**: Option A — every existing idle/disable-style knob in this codebase defaults to `0` (disabled) and requires explicit non-zero opt-in: `subprocess_utils.py:327` (`idle_timeout: int = 0`), `config/automation.py:18` (`idle_timeout_seconds: int = 0`), `parallel/types.py:393` / `config/core.py:552` (`idle_timeout_per_issue: int = 0`). Option A is the only one consistent with that convention. Option B has no precedent and no data source: a repo-wide search for measured-cadence telemetry (`history_reader.py`, `issue_manager.py`, `stall_detector.py`, and general "cadence"/"inter-event gap" grep) found nothing; FEAT-3033 itself states cadence "is not currently measured" and names option (a) "the safer default" in its own Scope Boundary framing. FEAT-3033's schema for the new field already declares `minimum: 0` (vs. `minimum: 1` on the existing `timeout`/`default_timeout` properties) specifically so `0` can express "disabled," and its Dependent Files section directs the new `idle_timeout` runner parameter to be kwarg-gated following the `working_dir`/`automation_profile` precedent at `executor.py:1870-1889` — both are Option A's implementation shape, not Option B's.

### Decision Rationale

_Added by `/ll:decide-issue` — 2026-08-04:_

**Selected: Option A** — gate the wall-clock-cap relaxation on an explicit `idle_timeout`/`default_idle_timeout` opt-in, leaving `or 3600` in force otherwise.

**Reasoning**: Every existing idle/disable-style knob in this codebase (`subprocess_utils.py:327`, `config/automation.py:18`, `parallel/types.py:393`, `config/core.py:526,552`, `config-schema.json:255-260`) defaults to `0`/disabled and requires explicit non-zero opt-in — Option A is the only one of the two that matches this established, four-surface convention. Option B requires a non-zero global default derived from measured agent-output cadence, but no such measurement exists anywhere in the codebase today (confirmed by an independent search of `stall_detector.py`, `history_reader.py`, `issue_manager.py`, and a repo-wide grep for "cadence"), and FEAT-3033 — the dependency this fix rides on — explicitly designed its own schema (`minimum: 0`, not `minimum: 1`) and default (start-at-zero) around the opposite shape, naming Option A "the safer default" in its own text. Option B's unconditional-for-every-loop shape would also reproduce, at global scope, the exact "hung state occupies a worker for up to 4 days" risk this issue's own Risk section warns against, whereas Option A confines any miscalibration to only the loops/states that opt in.

**Scoring Summary**:

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — opt-in gate | 2 | 1 | 2 | 3 | **8/12** |
| B — measured global default | 0 | 1 | 1 | 0 | **2/12** |

**Key evidence**:
- Option A evidence for: reuses the identical `state.X or fsm.default_X or <fallback>` precedence chain already at `fsm/executor.py:1852,1862,1893`, and the disabled-by-default idiom at `subprocess_utils.py:327`, `config/automation.py:18`, `parallel/types.py:393`.
- Option A evidence against: introduces a novel coupling — `idle_timeout`'s presence gating a *different* field's fallback value — with no existing precedent among the four cited `idle_timeout*` surfaces, all of which gate only themselves; and it only relaxes the cap for loops that separately opt in via YAML, leaving the other 90 loops' fallback unchanged until they do.
- Option B evidence against: contradicts the codebase's own idle/disable-knob convention outright (reuse_score 0/3 from independent evaluation); no measured-cadence data source exists to derive its required non-zero value; FEAT-3033's schema and stated preference were both built around the opposite (start-at-zero) shape.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/executor.py` — **line 1893 only**, plus its
  `_run_baseline_arm` counterpart at line 2697: make the `or 3600` terminal
  fallback conditional per the Proposed Fix. Two sibling call sites are
  deliberately **not** changed:
  - `:1852` (`or 30`, MCP) — unchanged, per Expected Behavior.
  - `:1862` (`contributed`) — **unchanged.** This branch is not a prompt path:
    contributed actions are third-party runner surfaces invoked with
    `is_slash_command=False`, i.e. arbitrary author-registered action types, not
    agent prompts. FEAT-3033 kwarg-gates `idle_timeout` precisely because those
    runners may predate it, so relaxing the cap here would leave a contributed
    action with *neither* sensor. If a contributed runner wants the relaxation
    it can declare `state.timeout` explicitly.
  - `:1893` is shared by prompt **and shell** — the `action_mode == "prompt"`
    gate in the Proposed Fix is what keeps shell states bounded. A test pins it.
- `scripts/little_loops/loops/lib/common.yaml` — lines 47-56, the `llm_gate`
  timeout-budget prose.

### Dependent Files

- `scripts/little_loops/fsm/runners.py` — must handle `timeout=0` on the prompt
  path. `run_claude_command` already does (`subprocess_utils.py:346,465`), so
  the only required change is FEAT-3033's `duration_ms` fix at `runners.py:191`
  (`timeout * 1000` → elapsed), which otherwise reports `0` for every idle kill
  on an uncapped state. That fix is a **hard prerequisite** of this issue, not
  the telemetry cleanup FEAT-3033 currently frames it as.
- `scripts/little_loops/fsm/schema.py` / `fsm-loop-schema.json` — the
  `idle_timeout` / `default_idle_timeout` fields this issue's gate reads;
  delivered by FEAT-3033 step 1.
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

- **Opt-in ON**: a prompt state with a non-zero `idle_timeout` (or a loop-level
  `default_idle_timeout`) and neither `state.timeout` nor `fsm.default_timeout`
  receives no wall-clock deadline — assert the value passed to the runner is
  `0`, not `3600` and not `None`. The core regression guard.
- **Opt-in OFF**: the same state *without* any idle declaration still receives
  `3600`. This is the Option A gate; without this test the decision is
  unenforced.
- **Shell non-leak**: a shell state in a loop declaring `default_idle_timeout`
  still receives `3600`. Pins the `action_mode == "prompt"` gate — line 1893
  serves both modes, so this is the test most likely to catch a naive fix.
- **MCP non-leak**: an MCP state with neither set still receives `30`.
- **Contributed non-leak**: a `contributed` state in a loop declaring
  `default_idle_timeout` still receives `3600` (`:1862` untouched).
- `state.timeout` and `fsm.default_timeout` still take precedence over the
  relaxation, in that order, even with idle declared.
- Loop-level `timeout:` still terminates a run (`executor.py:546-567`) when no
  per-state cap exists — proves the backstop survives.
- A long-running prompt state that would previously have been killed at 3600s
  now runs to completion and its output reaches the evaluator rather than being
  short-circuited to `error`.
- An idle kill on an uncapped state reports elapsed `duration_ms`, not `0`
  (guards the `timeout * 1000` interaction; overlaps FEAT-3033's own test but
  is load-bearing for this issue specifically).

### Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — if it documents timeout
  defaults, update.
- `CHANGELOG.md` — new entry in a concrete version section, not `[Unreleased]`.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-04 — based on codebase analysis:_

### Types
- No new data shape introduced by this bug fix; `StateConfig.timeout: int | None` (`fsm/schema.py:658`) and `FSMConfig.default_timeout: int | None` (`fsm/schema.py:1281-1282`) are the existing fields whose precedence-chain resolution changes.

### Signatures
- Fallback resolution (current, to be changed): `timeout = state.timeout or self.fsm.default_timeout or 3600` at `fsm/executor.py:1862` (contributed) and `:1893` (default/prompt dispatch); same shape at `_run_baseline_arm`, `fsm/executor.py:2697`. The MCP-path sibling, `... or 30` at `fsm/executor.py:1852`, is explicitly unchanged.
- `ActionRunner.run(self, action: str, timeout: int, is_slash_command: bool, on_output_line, agent, tools, on_usage, on_usage_detailed, model, working_dir=None, automation_profile=None) -> ActionResult` — Protocol, `fsm/runners.py:39-52`; `DefaultActionRunner.run` (`fsm/runners.py:95`) is the concrete implementation that calls `run_claude_command`.
- `run_claude_command(command: str, timeout: int = 3600, idle_timeout: int = 0, ...)` — `subprocess_utils.py:322,327`. `idle_timeout` is already wired through to raise `subprocess.TimeoutExpired(cmd_args, idle_timeout, output="idle_timeout")` on an idle-specific kill (`subprocess_utils.py:485`), but `runners.py:173-188` never passes it, and `runners.py:189-197` collapses both timeout kinds to the same `exit_code=124` — no `timeout_kind` distinction survives to `evaluators.py`.

### Call Path
`FSMExecutor._run_action_or_route` (`executor.py:1852`/`:1862`/`:1893`) -> `DefaultActionRunner.run` (`runners.py:95`) -> `run_claude_command` (`subprocess_utils.py:322`); on breach -> `_kill_process_group` -> `ActionResult(exit_code=124)` -> `evaluators.py:1814-1818` short-circuit (evaluator never runs). `_run_baseline_arm` (`executor.py:2680-2734`) follows the same shape but calls `run_claude_command` directly, bypassing `ActionRunner`.

Two properties of this path constrain the fix and are easy to miss:

- The `:1893` branch is the `else:` of the dispatch chain and therefore serves
  **both** prompt and shell actions — the mode is distinguished only by
  `is_slash_command=action_mode == "prompt"` at `:1895`. Any change to its
  fallback must re-derive `action_mode` rather than assuming prompt.
- `:1862` (`contributed`) passes `is_slash_command=False` into a third-party
  runner; it is not a prompt path and is out of scope for the relaxation.

Under Option A (see Proposed Solution), this path gains a second, parallel precedence chain — `state.idle_timeout or self.fsm.default_idle_timeout` — resolved alongside the existing `state.timeout or self.fsm.default_timeout` chain and kwarg-gated into `ActionRunner.run` following the `working_dir`/`automation_profile` precedent already in force at `executor.py:1870-1889`, terminating in `run_claude_command`'s existing (but currently unused) `idle_timeout` parameter. None of `StateConfig`, `FSMConfig`, `fsm-loop-schema.json`, or the `ActionRunner` Protocol currently declare `idle_timeout`/`default_idle_timeout` — that plumbing is FEAT-3033's scope, not this issue's; BUG-3032 only changes the `or 3600` terminal fallback once FEAT-3033's fields exist.

## Implementation Steps

1. Land FEAT-3033 steps 1-4 first — the `idle_timeout` /
   `default_idle_timeout` schema fields this gate reads, the prompt-path
   pass-through, and the `duration_ms`-to-elapsed fix at `runners.py:191`.
   FEAT-3033's step 5 (selector loops) and its unresolved blocking-`readline()`
   fork are **not** prerequisites — they serve shell/mcp states, which this
   issue deliberately leaves capped.
2. Make the `or 3600` conditional at `executor.py:1893` and `:2697` per the
   Proposed Fix, gated on both `action_mode == "prompt"` and a non-zero
   resolved idle timeout. Leave `:1852` (MCP) and `:1862` (contributed) alone.
3. Rewrite the `lib/common.yaml` `llm_gate` timeout prose.
4. Add the tests above — the opt-in-OFF and shell non-leak guards are the two
   that enforce the Option A decision.
5. Spot-check `issue-refinement.yaml`'s missing `default_timeout`.

## Impact

- **Priority**: P2 — actively destroying agent work in live multi-hour loops,
  silently and with no partial credit. Not P1 only because loop authors can work
  around it today by setting `default_timeout` explicitly.
- **Effort**: Small once FEAT-3033 lands — three expressions and a docs block.
  The tests matter more than the change.
- **Risk**: Medium, and concentrated in ordering and in the two gates.
  Relaxing the cap before idle detection exists would convert "work killed at
  1h" into "hung state occupies a worker for up to 4 days," which is worse —
  the `depends_on` is load-bearing, not decorative. Option A's opt-in gate
  narrows the blast radius to loops that declare idle; the second gate
  (`action_mode == "prompt"`) is what keeps a loop-level `default_idle_timeout`
  from un-capping that loop's shell states as a side effect. Both need tests,
  not just care.
- **Breaking Change**: No, under Option A. A loop's prompt states behave
  identically until it declares `idle_timeout` / `default_idle_timeout`; the
  relaxation and the sensor arrive together, by the author's own choice. The
  cost of that safety is that the 90 affected loops stay capped until each opts
  in — accepted deliberately, since the alternative (Option B) required a
  global default value no measurement currently supports.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-04_

> ⚠ **Stale as of the 2026-08-04 pre-implementation review.** Three of the four
> gaps below are now closed: `## Program Design` exists, the Scope Boundary fork
> was resolved to Option A by `/ll:decide-issue`, and `## Steps to Reproduce`
> was added. The Option A decision has since been propagated into Expected
> Behavior, Proposed Fix, Integration Map, Tests, and Implementation Steps
> (it had been recorded but not applied to the body, which was the last real
> blocker). The one remaining gap is unchanged and genuine: **FEAT-3033 steps
> 1-4 must land first.** Re-run `/ll:confidence-check` to refresh the scores.

**Readiness Score**: 70/100 → STOP — ADDRESS GAPS (hard override)
**Outcome Confidence**: 78/100 → MODERATE

### Concerns
- Dependency (`FEAT-3033`) is still `status: open` — the issue's own Risk
  section calls this ordering "load-bearing, not decorative"; landing before
  idle detection ships would convert a 1h kill into a multi-day hang.
- `Scope Boundary` note (added by `/ll:audit-issue-conflicts`) leaves an
  unresolved fork: implementation must pick option (a) or (b) before the
  `or 3600` removal lands.

### Gaps to Address
- `## Program Design` section is missing entirely (`ll-issues format-check`
  → `missing: ["Program Design", "Steps to Reproduce"]`; `ll-issues
  check-design BUG-3032` exits 1). The gate is armed
  (`.ll/program-design-cutover.json` present) and the issue carries no
  `program_design_not_applicable` flag. Populate concrete types/signatures/call
  path via `/ll:refine-issue` or `/ll:reconcile-issue`, or set
  `program_design_not_applicable: true` if the 3-line literal removal is judged
  trivial enough to skip the gate.
- `FEAT-3033` (blocking dependency) has not landed — cannot safely start
  implementation until it ships `timeout=None` support in `runners.py`.
- Resolve the `Scope Boundary` fork (option (a): gate the cap removal on
  explicit `idle_timeout`/`default_idle_timeout` opt-in, vs option (b): ship a
  non-zero `default_idle_timeout`) before implementation begins.
- Add the missing `## Steps to Reproduce` section flagged by `format-check`.

### Escalation (readiness < 70 after 2+ prior refinement passes)
- **Unresolved options (score_ambiguity = 10 ≤ 10)**: Run
  `/ll:decide-issue BUG-3032` — the Scope Boundary (a)/(b) fork is blocking
  readiness; selecting one clears the ambiguity.

## Session Log
- `/ll:decide-issue` - 2026-08-04T06:33:17 - `d9b95d0a-bc35-44a3-9a60-f978eece0013.jsonl`
- `/ll:refine-issue` - 2026-08-04T06:30:09 - `58473744-ba97-43e3-9145-5be88f2da018.jsonl`
- `/ll:confidence-check` - 2026-08-04T06:24:18 - `3cb0a0fa-c62e-4f00-bb85-ee1d66537a41.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T04:56:49 - `d6fd3e14-c984-4d6e-aad4-732de84b59ce.jsonl`
- `/ll:verify-issues` - 2026-08-04T04:54:17 - `0645ab21-f89c-4db8-a208-435d990eba38.jsonl`
- `/ll:capture-issue` - 2026-08-04T04:20:07 - `62eddd57-7e6c-4ca5-b631-081e050a3dc6.jsonl`

---

## Scope Boundary

> ✅ **Resolved 2026-08-04** — option (a) selected (see Decision Rationale) and
> now propagated throughout the body. Retained below for provenance.

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

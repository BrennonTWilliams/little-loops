---
id: BUG-2730
title: headless automation prompt path carries no "stay in turn" contract, and parallel-agent
  skills invite the end-turn-and-wait pattern that triggers exit 143
type: BUG
status: done
priority: P1
captured_at: '2026-07-21T22:40:00Z'
completed_at: '2026-07-22T01:06:32Z'
discovered_date: '2026-07-21'
discovered_by: issue-size-review
parent: BUG-2729
labels:
- subprocess
- automation
- headless
- prompt-contract
relates_to:
- BUG-2729
- ENH-2714
decision_needed: false
confidence_score: 100
outcome_confidence: 83
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# BUG-2730: headless automation prompt path carries no "stay in turn" contract, and parallel-agent skills invite the end-turn-and-wait pattern

## Summary

FSM `slash_command` actions run skills via headless `claude -p` (stream-json). In
interactive Claude Code, a model may spawn subagents, end its turn, and be
re-invoked by a `<task-notification>` when they finish. In headless mode that
contract does not exist: ending the turn ends the *session*, and `claude -p`
tears down and reaps still-running subagent children (SIGTERM to the process
group, exit 143) — silently discarding in-flight subagent work.

This is the **Primary fix** half of [[BUG-2729]] (decomposed 2026-07-21): prevent
the model from choosing the end-turn-and-wait pattern in headless runs at all,
by (a) injecting a "stay in turn" instruction into the automation prompt path
and (b) removing the wait-for-notification phrasing that currently invites the
unsafe pattern from the parallel-agent skills.

## Current Behavior

`hooks/session_start.py`'s `LL_AUTOMATION` gate suppresses the config-JSON /
`project_context` digest under automation but injects no replacement
instruction — the headless prompt path carries no "stay in turn" contract.
Separately, seven skills/commands (`refine-issue`, `wire-issue`,
`decide-issue`, `manage-issue`, `audit-issue-conflicts`,
`tradeoff-review-issues`, `analyze-workflows`) instruct the model to "spawn
agents and wait for them to complete," phrasing that reads as license to end
the turn and resume on a `<task-notification>` — the pattern that self-
terminates headless `claude -p` sessions with exit 143 (per [[BUG-2729]]).

## Expected Behavior

Headless automation runs carry an explicit "stay in turn" instruction (model
must wait for spawned agents/tasks synchronously within the same turn, never
end the turn while they're in flight). All seven affected skills/commands
are reworded so their spawn→wait instructions read as an in-turn synchronous
wait rather than end-turn-and-resume-on-notification phrasing.

## Impact

- **Priority**: P1 - In-flight subagent work is silently discarded on
  headless exit 143 self-termination ([[BUG-2729]]); this issue is the
  primary prevention half of that fix.
- **Effort**: Medium - one new injection branch in `session_start.py` plus
  seven one-line reword edits across skills/commands.
- **Risk**: Low - additive prompt text and wording changes only; no control-
  flow or FSM behavior changes.
- **Breaking Change**: No

## Steps to Reproduce

1. Run any of the seven affected skills/commands (e.g. `/ll:refine-issue`)
   under headless automation (`LL_AUTOMATION=1`, e.g. via `ll-auto` or an FSM
   `slash_command` action).
2. Reach the parallel-agent spawn step; the model spawns agents per the
   "Spawn all N agents..." instruction.
3. Observe: the skill's own wording ("Wait for ALL agents to complete before
   proceeding") carries no in-turn-synchronous framing and no headless
   "stay in turn" contract precedes it — the model may end its turn instead
   of waiting synchronously, and headless `claude -p` then tears down the
   session, SIGTERM-ing still-running subagent children (exit 143, per
   [[BUG-2729]]).

## Parent Issue

Decomposed from [[BUG-2729]]: headless session end-turn-while-awaiting-subagents
self-terminates with exit 143, discarding in-flight work. The parent's Secondary
fix (FSM-side retry classification of exit-143-after-result) is tracked
separately as a sibling BUG created in the same decomposition — see
`## Session Log` cross-reference in BUG-2729 for the sibling ID.

## Codebase Research Findings

_Carried over from [[BUG-2729]]'s `/ll:refine-issue` pass:_

- No automation prompt-prefix builder exists to inject a "stay in turn"
  instruction into. `scripts/little_loops/skill_expander.py` has no
  automation-prefix-building logic at all (only `$ARGUMENTS`/config
  substitution in `expand_skill()`, line ~99) — this is net-new code, not an
  edit to an existing builder.
- `scripts/little_loops/hooks/session_start.py:91-112` is the only existing
  consumer of `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` ([[ENH-2714]]'s carrier).
  It currently only **suppresses** the config-JSON/`project_context` digest
  under automation (`return LLHookResult(exit_code=0, ...)` at line ~112) — a
  subtraction mechanism, not an injection one. This is the nearest existing
  hook point to branch a new "stay in turn" instruction from, but there is no
  precedent in this codebase for *adding* prompt text via this path.
- Treat the `automation_profile` / `LL_AUTOMATION_PROFILE` env-var signal
  (already reaching the child process via `host_runner.py`) as the input
  signal to branch injection on.

### Wait-for-Notification Phrasing to Audit

All four parallel-agent skills contain the same recurring phrase immediately
after their spawn instruction — this is the exact wording that invites the
unsafe end-turn-and-wait pattern:

- `commands/refine-issue.md:123-190` — "Spawn all 3 agents in a SINGLE
  message..." / "**Wait for ALL agents to complete before proceeding.**"
- `skills/wire-issue/SKILL.md:136-241` — same "Spawn all 3 agents..." /
  "**Wait for ALL 3 agents to complete before proceeding.**"
- `skills/decide-issue/SKILL.md:315-322` — "Spawn one
  `ll:codebase-pattern-finder` Agent per option... Use `run_in_background:
  false` and wait for all to complete before proceeding." / "**Wait for ALL
  agents to complete before proceeding to Phase 5.**"
- `skills/manage-issue/SKILL.md:110` — "**CRITICAL**: Wait for ALL sub-agent
  tasks to complete before proceeding to planning."

### Codebase Research Findings — `/ll:refine-issue` pass

_Added by `/ll:refine-issue` — based on codebase analysis (2026-07-21):_

**Injection mechanism — exact code path and precedent**

- The `LL_AUTOMATION` gate at `scripts/little_loops/hooks/session_start.py`
  `handle()` lines 91-112 is confirmed as the branch point, but today it is a
  **hard early-return** (`return LLHookResult(exit_code=0, feedback=None,
  stdout=None)` at line 112) that fires when
  `history.automation_pruning.enabled` is true — it skips the rest of
  `handle()` entirely (no config load, no digest, no local-override merge).
  A "stay in turn" instruction cannot simply be appended to the normal-path
  `stdout_payload` because that whole code path is bypassed on this branch.
- The channel Claude Code actually ingests as session context is
  `LLHookResult.stdout` (not `feedback`, which for `session_start.py` only
  reaches stderr — see `types.py:84-133` docstring and
  `hooks/__init__.py::main_hooks`, `if result.stdout is not None:
  sys.stdout.write(result.stdout)`). The existing string-append idiom to
  model the new text after is lines 226-243: `stdout_payload = stdout_payload
  + "\n\n" + _project_context_block`.
- **Concrete fix shape**: replace the line-112 early return with a branch
  that composes `LLHookResult(exit_code=0, feedback=None, stdout=<stay-in-turn
  text>)` instead of `stdout=None` — i.e. still skip the config-JSON/digest
  work (pruning gate's purpose), but no longer send an empty `stdout`.
- The one existing precedent in this codebase for "prepend labeled text to a
  prompt string before invocation" is `host_runner.py::CodexRunner.
  _inject_agent_persona()` (lines 503-518), called from `CodexRunner.
  build_streaming()` (lines 533-536): `f"[Persona: {agent}]\n{instructions}\n
  \n---\n\n{prompt}"`. It is gated on `agent`, not `automation_profile`, and
  lives in `CodexRunner` only — `ClaudeCodeRunner.build_streaming()` (lines
  262-312) does no prompt-string mutation today (`args += ["-p", prompt]`,
  line 281). This is a second candidate injection point (host-runner-level
  prompt prefixing) as an alternative to the session_start.py hook-stdout
  approach above — session_start.py is preferred because it already owns the
  `LL_AUTOMATION` signal end-to-end and requires no new parameter threading
  through `build_streaming()`'s Protocol (implemented identically across 4
  host runners).
- `skill_expander.py::expand_skill()` (lines 99-136) confirmed to have no
  `automation_profile`/env-var-aware branch at all — it does not need one
  under the session_start.py-hook approach, since that channel is
  session-level, not skill-text-level.

**Exit-143 FSM classification — confirmed out of scope for this issue**

- `fsm/executor.py::_route_next_state()` (lines 1403-1484) → `issue_lifecycle.
  py::classify_failure()` (lines 93-238) currently ignores its `returncode`
  parameter entirely (docstring: "Process exit code (available for future
  use)", line 101) and falls through to `FailureType.REAL` for exit 143 with
  no text-pattern match — i.e. exit 143 is retried/routed exactly like an
  ordinary implementation failure today. This confirms the parent issue's
  description of the still-open gap, but it is the **Secondary fix** tracked
  as sibling `BUG-2731-fsm-classify-exit-143-as-retryable-infra-teardown`
  (found via `ll-issues path` search) — no action needed in BUG-2730.

**Wait-for-notification phrasing audit — 3 additional files not in the original 4-file list**

A grep for the same recurring phrase surfaces 3 more files with the identical
end-turn-and-wait pattern, not included in this issue's current scope:

- `skills/audit-issue-conflicts/SKILL.md:178` — "Wait for **all batch
  agents** to complete before proceeding." (spawn instruction at line 165)
- `commands/tradeoff-review-issues.md:161` — "Wait for all subagents in a
  wave to complete before launching the next wave."
- `commands/analyze-workflows.md:119` — "**Wait for agent to complete.**"
  (single-agent spawn, same phrasing shape)

`.issues/enhancements/P3-ENH-1801-audit-issue-conflicts-cross-theme-detection.md:67,82`
already cross-references the exact `audit-issue-conflicts/SKILL.md` sentence
as a future insertion anchor, confirming this phrasing predates the
BUG-2729/2730 audit and was simply missed by its 4-file list (the same way
`manage-issue/SKILL.md` itself was "missed by the original three-skill list"
per `BUG-2729.md:157-159` before a later wiring pass caught it).

**Option A**: Keep this issue scoped to the 4 files already named
(`refine-issue`, `wire-issue`, `decide-issue`, `manage-issue`) and leave the
3 newly-found files (`audit-issue-conflicts`, `tradeoff-review-issues`,
`analyze-workflows`) for a follow-up issue, since they weren't part of the
original BUG-2729 decomposition scope.

**Option B**: Expand this issue's Acceptance Criteria to cover all 7 files
found to carry the same end-turn-and-wait phrasing, since the fix (reword to
in-turn synchronous wait) is mechanically identical across all of them and
splitting them into a second issue would just be process overhead for a
one-line wording change per file.

> **Selected:** Option B — mechanically identical one-line reword across all
> 7 files; narrower scoping already dropped `manage-issue/SKILL.md` once in
> this same audit lineage.

**Recommended**: Option B — the reword is the same one-line change in every
case, and BUG-2730's own history shows this audit list has already missed
files once (`manage-issue/SKILL.md`); closing the issue without covering the
3 newly-found files risks a third miss.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-21.

**Selected**: Option B — expand Acceptance Criteria to cover all 7 files

**Reasoning**: Two independent codebase-pattern-finder passes confirmed the
3 newly-found files (`audit-issue-conflicts/SKILL.md:178`,
`tradeoff-review-issues.md:161`, `analyze-workflows.md:119`) carry the exact
same spawn→wait-for-notification phrasing shape as the original 4, with no
structural differences that would make the reword non-trivial. BUG-2730's own
history already shows narrow scoping dropped one file
(`manage-issue/SKILL.md`) in this same audit lineage before a later
`/ll:wire-issue` pass caught it — closing this issue without the 3 additional
files risks repeating that gap for a fix that costs nothing extra to include.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (scope to 4) | 1/3 | 3/3 | 2/3 | 1/3 | 7/12 |
| Option B (scope to 7) | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |

**Key evidence**:
- Option A: `Scope Boundaries` follow-up-issue convention exists in this repo
  (ENH-1801, ENH-2621), but that precedent covers genuinely separate
  design-triage work, not finishing an already-scoped mechanical sweep; this
  same audit lineage already lost a file once via this exact "defer to
  follow-up" move.
- Option B: Direct reads confirm all 3 additional files carry identical
  spawn→wait phrasing with no structural adaptation needed; ENH-1801:67,82
  already cross-references the exact `audit-issue-conflicts/SKILL.md`
  sentence, showing ecosystem pressure already points at that file.

## Proposed Fix

Inject an instruction into the automation prompt path (the natural carrier is
[[ENH-2714]]'s `automation_profile`, branched via
`hooks/session_start.py`'s existing `LL_AUTOMATION` gate — the injection side
of that gate is new code) stating: *"You are running headlessly. Ending your
turn ends the session. Never end your turn while spawned agents/tasks are
still running — wait for them synchronously within the turn."*

Reword all seven wait-for-notification phrasings (the original four plus the
three surfaced by the `/ll:refine-issue` audit pass) so they read as an
in-turn synchronous wait (e.g. "Spawn all N agents and wait for their results
in this same turn before proceeding") rather than language that reads as
"end your turn and resume on notification."

## Acceptance Criteria

- [x] Headless automation prompt prefix carries the stay-in-turn contract
- [x] Parallel-agent skills/commands (`refine-issue`, `wire-issue`,
      `decide-issue`, `manage-issue`, `audit-issue-conflicts`,
      `tradeoff-review-issues`, `analyze-workflows`) contain no
      end-turn-and-wait phrasing for automation mode

## Resolution

- `scripts/little_loops/hooks/session_start.py`: replaced the `LL_AUTOMATION`
  pruning gate's `return LLHookResult(exit_code=0, feedback=None,
  stdout=None)` (line ~112) with a new module-level constant
  `_STAY_IN_TURN_INSTRUCTION` composed into `stdout=` on that same return —
  the config-JSON/`project_context` digest stays pruned, but the returned
  `stdout` is no longer empty; it now carries: *"You are running headlessly.
  Ending your turn ends the session. Never end your turn while spawned
  agents/tasks are still running — wait for them synchronously within the
  turn."*
- Reworded the wait-for-notification phrasing in all seven files identified
  by the decision rationale (Option B), replacing "wait for X to complete"
  with "wait for X's results synchronously in this same turn" —
  `commands/refine-issue.md` (2 sites), `skills/wire-issue/SKILL.md` (2
  sites), `skills/decide-issue/SKILL.md` (2 sites),
  `skills/manage-issue/SKILL.md` (1 site),
  `skills/audit-issue-conflicts/SKILL.md` (1 site),
  `commands/tradeoff-review-issues.md` (2 sites),
  `commands/analyze-workflows.md` (1 site).
- Added `TestAutomationPruningStayInTurn` (3 tests) to
  `scripts/tests/test_hook_session_start.py`, covering: the instruction fires
  under `LL_AUTOMATION=1` + pruning enabled and still suppresses
  `<project_context>`; the instruction is absent when pruning is disabled;
  the instruction is absent with no `LL_AUTOMATION` env var. Full suite
  (`python -m pytest scripts/tests/`) passes at 15754 passed, 38 skipped;
  `ruff check scripts/` and `python -m mypy
  scripts/little_loops/hooks/session_start.py` both clean.
- Sibling `BUG-2731` (FSM-side exit-143 retry classification) is out of
  scope, as noted in the Codebase Research Findings.

## Status

**Done** | Created: 2026-07-21 | Priority: P1

## Session Log
- `/ll:manage-issue` - 2026-07-22T01:05:51 - `5a92dd83-64f6-4d40-aeb3-c1c83fa9f733.jsonl`
- `/ll:ready-issue` - 2026-07-22T00:58:39 - `c5a04b7c-d82b-4e30-959e-f53eac8f0581.jsonl`
- `/ll:decide-issue` - 2026-07-22T00:54:27 - `3055bcbb-ced6-4172-973d-7e48d2920e69.jsonl`
- `/ll:refine-issue` - 2026-07-22T00:50:28 - `9084231e-e205-4043-a800-034094756484.jsonl`
- `/ll:verify-issues` - 2026-07-21T23:08:29 - `9fc8185c-278a-4573-8071-af3d44765f41.jsonl`
- `/ll:issue-size-review` - 2026-07-21T23:15:00Z - `5d306492-7288-421c-83db-83a5420b5516.jsonl`

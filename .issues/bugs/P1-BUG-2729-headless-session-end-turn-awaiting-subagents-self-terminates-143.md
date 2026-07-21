---
id: BUG-2729
title: headless automation sessions that end their turn while awaiting subagents are
  torn down by claude -p shutdown (SIGTERM/exit 143), discarding in-flight work
type: BUG
status: done
priority: P1
captured_at: '2026-07-21T22:40:00Z'
discovered_date: '2026-07-21'
discovered_by: audit-loop-run
size: Very Large
labels:
- subprocess
- automation
- headless
- prompt-contract
relates_to:
- BUG-2718
- ENH-2717
- BUG-2726
- ENH-2727
- ENH-2714
confidence_score: 95
outcome_confidence: 62
score_complexity: 12
score_test_coverage: 20
score_ambiguity: 14
score_change_surface: 16
---

# BUG-2729: headless sessions that end their turn while awaiting subagents self-terminate with exit 143, discarding in-flight work

## Summary

FSM `slash_command` actions run skills via headless `claude -p` (stream-json).
In interactive Claude Code, a model may spawn subagents, **end its turn**, and be
re-invoked by a `<task-notification>` when they finish. In headless mode that
contract does not exist: the end-of-turn `result` event ends the *session*. The
CLI then shuts down, reaps its still-running subagent children (SIGTERM to the
process group), and exits **143** — silently discarding all in-flight subagent
work. From the FSM's perspective the action just "failed with exit 143".

This is the behavioral successor of [[BUG-2718]]: that fix stopped *little-loops*
from SIGKILLing sessions whose streams closed early (grace 30s → 300s +
result-event break), but it cannot stop *claude itself* from tearing down when
the model voluntarily ends its turn to wait. Whether a given run survives
depends on whether the model chooses to block in-turn on its agents (survives)
or end-turn-and-wait (dies) — which is why this recurs intermittently across
automation runs.

## Evidence (run `2026-07-21T214941-autodev`, refine of ENH-2722)

Inner session transcript
`~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d7556fa3-cf0f-4f60-bc7c-7b6b7c3355dd.jsonl`:

1. The session spawned three subagents in one message (`ll:codebase-locator`,
   `ll:codebase-analyzer`, `ll:codebase-pattern-finder`; `run_in_background`
   unset).
2. Last assistant text: *"I'll pause here and wait for the three background
   research agents (locator, analyzer, pattern-finder) to complete before
   enriching the issue file."* — the turn genuinely ended: the **Stop hook
   fired**, `stop_hook_summary` was written.
3. `{"type": "queue-operation", "operation": "dequeue", "timestamp":
   "2026-07-21T21:52:21.056Z"}` — a `<task-notification>` user message was being
   dequeued to re-invoke the model.
4. The process exited **143** at `21:52:21.997` (< 1s later). The FSM run log
   shows only `(2m 36s)  exit: 143` — none of little-loops' kill-path log lines
   ("Action timed out" / "did not exit within Ns after streams closed, killing"),
   and those paths SIGKILL (returncode -15/-9), not 143.
5. Downstream: `refine-to-ready-issue` routed `on_error → diagnose → failed`;
   autodev ledgered `ENH-2722  refine_failed` ([[ENH-2727]] misattribution) and
   the diagnose session confabulated ([[BUG-2726]]). Both are mitigations of
   consequences; this issue is the root cause.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase research (three-agent research pass)._

### Files to Modify

- `scripts/little_loops/fsm/executor.py` — the retry classification chain lives
  in `_route_next_state` (the `elif action_result.exit_code != 0 and
  _failure_type == ...` block at lines ~1412–1449). It already special-cases
  429/rate-limit (`_handle_rate_limit`, line ~2325) and `"api server error"`
  text (`_handle_api_error`, line ~2576, `_DEFAULT_API_ERROR_RETRIES` /
  `_DEFAULT_API_ERROR_BACKOFF` constants at lines 114–117). A new
  `exit_code == 143` branch is a further `elif` in this same chain, modeled
  structurally on `_handle_api_error` (flat per-state retry counter dict,
  same shape as `self._api_error_retries`).
- `scripts/little_loops/issue_lifecycle.py` — `classify_failure()` (line ~93)
  is **purely text-pattern-based**; it accepts a `returncode` parameter but
  its docstring says "available for future use" (line ~101) and the body
  never branches on it. A 143 classification must be keyed off `returncode`
  directly (SIGTERM leaves no stdout/stderr text signature to grep for),
  which is new territory for this function. `FailureType` enum (lines
  79–90) is the model for the value shape.
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()` (line
  ~286) tracks `result_seen` as a **local variable** (set `True` at line
  ~496 when a `type: "result"` stream-json event is parsed) but never
  returns it — the final `CompletedProcess(...)` (lines 543–548) carries
  only `args`/`returncode`/`stdout`/`stderr`. This must be surfaced to
  callers for the "143-after-result" gate to be derivable at all.
- `scripts/little_loops/fsm/runners.py` / `scripts/little_loops/fsm/types.py`
  — `DefaultActionRunner.run()` (line ~95, `is_slash_command=True` branch at
  line ~132) builds `ActionResult` (line ~192–199); `ActionResult` (defined
  `fsm/types.py:69`) has no `result_seen` or `session_id` field today. The
  only indirect proxy currently available is `ActionResult.usage_events`
  being non-empty (usage callbacks only fire from inside the `result`-event
  branch), but nothing downstream inspects it for retry classification.
- `scripts/little_loops/host_runner.py` — `build_streaming(resume: bool =
  False)` is boolean-only across all host implementations (Claude maps
  `resume=True` → `--continue`, line ~280; Gemini maps to `--resume latest`,
  line ~936). **No host implementation supports resuming a specific
  session ID.** Implementing "retry via `--resume <session_id>`" (the
  Secondary fix) requires: (a) reading `session_id` from the `system`/`init`
  stream-json event in `run_claude_command()` (currently unread — only
  `event.get("model")` is extracted at line ~445), (b) storing it per
  in-flight action (no such store exists), and (c) a session-ID-aware resume
  path added to `HostRunner.build_streaming`.
- `scripts/little_loops/skill_expander.py` — confirmed via research to
  contain **no automation-prefix-building logic at all** (only
  `$ARGUMENTS`/config substitution in `expand_skill()`, line ~99). The
  issue's Primary fix language ("the static prefix `run_claude_command` /
  `skill_expander.py` builds") assumes a prefix builder that does not
  currently exist — this is net-new code, not an edit to an existing
  builder.
- `scripts/little_loops/hooks/session_start.py:91-112` — the only existing
  consumer of `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` (ENH-2714's carrier).
  It currently only **suppresses** the config-JSON/`project_context` digest
  under automation (`return LLHookResult(exit_code=0, ...)` at line ~112) —
  a subtraction mechanism, not an injection one. This is the nearest
  existing hook point to branch a new "stay in turn" instruction from, but
  there is no precedent in this codebase for *adding* prompt text via this
  path.
- `scripts/little_loops/loops/autodev.yaml` — `skip_inflight` state (lines
  151–165) hardcodes the literal string `refine_failed` on both
  `on_failure` and `on_error` (`echo "${captured.input.output}
  refine_failed" >> ...`). This is the exact site that needs to branch (or
  interpolate) a distinct reason when the new 143 classification fires —
  coordinates with [[ENH-2727]], which already proposes extending this same
  site.

### Wait-for-Notification Phrasing to Audit (AC 2)

All four parallel-agent skills contain the **same recurring phrase**
immediately after their spawn instruction — this is what AC 2 ("Parallel-agent
skills contain no end-turn-and-wait phrasing") targets:

- `commands/refine-issue.md:123-190` — "Spawn all 3 agents in a SINGLE
  message..." / "**Wait for ALL agents to complete before proceeding.**"
- `skills/wire-issue/SKILL.md:136-241` — same "Spawn all 3 agents..." /
  "**Wait for ALL 3 agents to complete before proceeding.**"
- `skills/decide-issue/SKILL.md:315-322` — "Spawn one
  `ll:codebase-pattern-finder` Agent per option... Use `run_in_background:
  false` and wait for all to complete before proceeding." / "**Wait for ALL
  agents to complete before proceeding to Phase 5.**"
- `skills/manage-issue/SKILL.md:110` — "**CRITICAL**: Wait for ALL sub-agent
  tasks to complete before proceeding to planning." — same pattern, missed by
  the original three-skill list. _Wiring pass added by `/ll:wire-issue`._

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/issue_manager.py:958` (`process_issue_inplace`) — a
  **second consumer** of `classify_failure(error_output, result.returncode)`,
  parallel to `fsm/executor.py:947`'s `_execute_state`. It treats
  `(FailureType.TRANSIENT, FailureType.NON_RECOVERABLE)` as "log, don't file a
  bug issue" — if the fix adds a new `FailureType` member for the 143 case, this
  tuple check must include it too, or a 143 kill on this (non-FSM) path still
  falls through to `create_issue_from_failure()` and files a phantom bug.
  `issue_manager.py` also calls `run_claude_command()` directly at lines
  277, 455, 627, 683, 844 (`run_with_continuation` and related retry loops) —
  a parallel non-FSM headless-session path with the same exit-143 exposure as
  the FSM path; worth an explicit scope note on whether this path is covered
  or intentionally out of scope for this issue.
- `scripts/little_loops/cli/logs.py:1032,1126-1131` — a **third consumer** of
  `classify_failure()`, used by `ll-logs scan-failures` to skip clustering
  errors already classified as `TRANSIENT`/`NON_RECOVERABLE`. Same tuple-update
  requirement as `issue_manager.py` above — otherwise `scan-failures --capture`
  will file spurious bug issues for 143-kill signatures it clusters.

### Similar Patterns (retry-classification precedent)

- `_handle_api_error()` (`executor.py:2576`) — flat per-state counter
  (`self._api_error_retries: dict[str, dict]`), flat backoff, emits
  `api_error_retry`/`api_error_exhausted` events, falls through to normal
  routing on exhaustion. This is the closest structural analog for a new
  143-classification handler (vs. `_handle_rate_limit`'s heavier
  short-burst + long-wait ladder).
- `StateConfig.retryable_exit_codes` (`executor.py:1457-1471`) — an existing
  **opt-in per-state** exit-code allowlist primitive. Per
  `feedback_check_existing_flags_before_proposing` (repo convention: check
  existing flags before adding new ones), worth an explicit note that this
  primitive is opt-in/per-loop-author, not automatically populated with
  infra-signal codes — it does not by itself solve AC 3's "classifies... as
  retryable infra teardown" requirement, which needs global default
  behavior, not per-loop opt-in.
- `self._last_action_exit_code` (`executor.py:247-251`, ENH-2522) — the
  established idiom in this file for "remember the last exit code to make a
  downstream classification decision"; a `result_seen`-equivalent tracking
  field would follow the same shape.

### Tests

- `scripts/tests/test_fsm_executor.py` — `TestRateLimitCircuit`/API-error
  test group (~lines 6360–7446), e.g. `test_api_error_counter_reset_on_success`
  and `test_api_error_does_not_trigger_rate_limit_handler` (~7398–7429) use
  `MockActionRunner` with `.results` list + `runner.use_indexed_order = True`
  — the standard fixture idiom to model new 143-classification regression
  tests after (AC 4). Also `test_action_timeout_exit_code_124_routes_to_error`
  (~2763) and `test_shell_exit_code_1_routes_to_on_error_without_on_no`
  (~5093) as existing exit-code-specific test precedents. `TestRetryableExitCodes`
  (~4968) is the existing test group for `state.retryable_exit_codes` — the
  generic opt-in primitive noted above.
- `scripts/tests/test_subprocess_utils.py` — would need a new test asserting
  `result_seen` (once surfaced) is correctly propagated from
  `run_claude_command()`'s `CompletedProcess` return.
  `TestRunClaudeCommandResultBreak::test_breaks_on_result_event_without_pipe_eof`
  (~2356) already exercises the exact stream-json `"result"`-event → break
  code path this would extend; `TestRunClaudeCommandModelDetection`'s
  `test_on_usage_callback_called_with_result_event` (~1596) and
  `test_result_event_is_error_appends_to_stderr` (~1691) show the
  `mock_process.stdout = io.StringIO(...)` fixture scaffolding to reuse.

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_issue_lifecycle.py::TestClassifyFailure` (~676-820) —
  a single parametrized test method covering `classify_failure()`. **No
  existing row varies `returncode`** (confirmed: the function only branches
  on `error_output` text today) — needs a new `returncode=143` case once the
  function gains returncode-driven branching. `FailureType` enum
  (`issue_lifecycle.py:79-90`) currently has exactly 3 members
  (`TRANSIENT`/`NON_RECOVERABLE`/`REAL`); no `INFRA_RETRY`-equivalent exists
  yet anywhere in the codebase (AC 3/4 greenfield, not a modification).
- `scripts/tests/test_issue_manager.py` — needs a new/updated test covering
  `issue_manager.py:958`'s `classify_failure()` call once the new
  `FailureType` member is added to its transient/non-recoverable tuple check
  (see Dependent Files above).
- `scripts/tests/test_builtin_loops.py` — literal `"refine_failed"` string
  assertions that may need updating if `skip_inflight` branches to a distinct
  reason code for the 143 case specifically: `test_skipped_breakdown_...`
  (~2893-2904, breakdown dict counts), a ledger-line format assertion at
  ~4752 (`"ENH-0001  refine_failed" in skipped`, note two-space separator
  matching the `echo` action's literal format). `test_refine_failed_is_terminal`
  and the `on_failure`/`on_error` routing tests (~5440-5475) assert on
  `refine_issues`' routing (a different state), not `skip_inflight`'s ledger
  write — likely unaffected unless the fix also touches that routing.
- No test currently asserts `exit_code==143` anywhere in
  `scripts/tests/` — this confirms AC 4 is greenfield, not a
  breaking-change area.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/EVENT-SCHEMA.md` (~line 363, `rate_limit_exhausted` section)
  — if the Secondary fix emits a new DES event for the 143-retry path (e.g.
  `infra_retry`), it needs a matching `###` section here, following the
  `rate_limit_exhausted`/`api_error_retry` pattern.
- `scripts/little_loops/observability/schema.py` (~lines 333-357,
  `RateLimitExhaustedVariant`/`ApiErrorRetryVariant` classes) — a new emitted
  event type needs a matching `@dataclass(frozen=True)` DES variant subclass
  here; this is what `ll-verify-des-audit` checks source emit-sites against
  (see CLAUDE.md § CLI Tools).
- `docs/observability/des-audit.md` (~lines 54-57, variant→event-type table)
  — needs a new row for the new variant class if one is added.
- `docs/guides/LOOPS_REFERENCE.md` (~line 835 state-diagram edge, ~861-862
  state table) — documents `refine_failed` as `skip_inflight`'s only
  outcome; needs updating if `skip_inflight` branches to a distinct reason
  code for the 143 case.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/fsm/fsm-loop-schema.json` (~line 483,
  `retryable_exit_codes`) — the JSON-Schema definition backing
  `StateConfig.retryable_exit_codes`, the existing opt-in per-state primitive
  already discussed above (`executor.py:1457-1471`). No schema change needed
  if the fix follows this existing mechanism rather than adding new
  classify_failure/FSM-executor logic — flagged here only so the schema is
  confirmed unaffected either way.

## Expected Behavior

Automation-invoked sessions never lose work to their own end-of-turn: either the
session stays in-turn until all spawned agents return, or the FSM recognizes the
teardown signature and retries/resumes instead of recording a hard failure.

## Proposed Fix

Primary — **prompt contract for headless runs**: inject an instruction into the
automation prompt path (the static prefix `run_claude_command` /
`skill_expander.py` builds; [[ENH-2714]]'s `automation_profile` is a natural
carrier) stating: *"You are running headlessly. Ending your turn ends the
session. Never end your turn while spawned agents/tasks are still running — wait
for them synchronously within the turn."* Audit the parallel-agent skills
(`refine-issue`, `decide-issue`, `wire-issue`, …) for wording that invites the
wait-for-notification pattern.

Secondary — **retryable teardown signature in the FSM**: treat
`exit_code == 143` + `result_seen` (usage captured) as `infra_retry` rather than
a terminal action failure: retry once via `--resume <session_id>` (the
transcript survives) or re-run the action, and ledger a distinct reason code
(coordinates with [[ENH-2727]]).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- No `--resume <session_id>` mechanism exists anywhere in this codebase today
  — `resume` is boolean-only everywhere it's threaded (`run_claude_command()`,
  `HostRunner.build_streaming()`), mapping to `--continue` (Claude) or
  `--resume latest` (Gemini). Resuming a *specific* prior session after a
  143 teardown requires new session-ID capture + storage + host-runner
  plumbing, not just flipping an existing flag — this is a real cost driver
  for the Secondary fix, not a one-line change.
- No automation prompt-prefix builder exists to inject the "stay in turn"
  instruction into (`skill_expander.py` has none; `session_start.py`'s
  `LL_AUTOMATION` gate only suppresses, never adds text). The Primary fix's
  "natural carrier" language in the original proposal assumes plumbing that
  isn't there yet — treat this as new code, and the `automation_profile` /
  `LL_AUTOMATION_PROFILE` env-var signal (already reaching the child process
  via `host_runner.py`) as the input signal to branch on, not an existing
  text-injection point to extend.
- `classify_failure()` (`issue_lifecycle.py:93`) is purely regex/text-based
  and explicitly does not branch on `returncode` despite accepting it —
  confirms the issue's framing that 143 falls through all existing
  TRANSIENT/NON_RECOVERABLE branches today with no matching text pattern.

## Acceptance Criteria

- [ ] Headless automation prompt prefix carries the stay-in-turn contract
- [ ] Parallel-agent skills contain no end-turn-and-wait phrasing for
      automation mode
- [ ] FSM classifies exit-143-after-result as retryable infra teardown with a
      distinct ledger reason (not `refine_failed`), with at least one retry
- [ ] Regression coverage: a simulated 143-after-result action routes to retry,
      not `on_error` terminal failure

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-21_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 62/100 → MODERATE

### Outcome Risk Factors
- Deep per-site complexity on the prompt-injection carrier: no automation
  prefix-builder exists today (`skill_expander.py` has none; `session_start.py`'s
  `LL_AUTOMATION` gate only suppresses text, never adds it) — this site is
  genuinely new code, not an edit to an existing builder.
- Unresolved retry-mechanism choice: the Secondary fix proposes "retry via
  `--resume <session_id>` **or** re-run the action" as if interchangeable, but
  session-ID-aware resume requires new plumbing across every `HostRunner`
  implementation (none support it today — `resume` is boolean-only,
  mapping to `--continue`/`--resume latest`), while a plain re-run does not.
  Recommend scoping the initial implementation to re-run only and deferring
  session-ID resume as a follow-on enhancement.

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-21
- **Reason**: Issue too large for single session

### Decomposed Into
- BUG-2730: headless automation prompt path carries no "stay in turn" contract, and parallel-agent skills invite the end-turn-and-wait pattern that triggers exit 143
- BUG-2731: FSM treats exit-143-after-result as a terminal action failure instead of retryable infra teardown, discarding in-flight subagent work

## Session Log
- `/ll:issue-size-review` - 2026-07-21T23:15:00Z - `5d306492-7288-421c-83db-83a5420b5516.jsonl`
- `/ll:confidence-check` - 2026-07-21T23:00:00 - `5d306492-7288-421c-83db-83a5420b5516.jsonl`
- `/ll:wire-issue` - 2026-07-21T22:22:57 - `4a6f89d5-eed4-45a6-a195-909777f64fc7.jsonl`
- `/ll:refine-issue` - 2026-07-21T22:15:01 - `b46323b4-c19c-47ae-a82b-ea821cc9e3ee.jsonl`

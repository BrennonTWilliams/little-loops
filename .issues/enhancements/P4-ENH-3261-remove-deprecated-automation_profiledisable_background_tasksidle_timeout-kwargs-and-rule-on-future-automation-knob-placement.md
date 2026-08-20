---
id: ENH-3261
type: ENH
title: Remove deprecated automation_profile/disable_background_tasks/idle_timeout
  kwargs and rule on future automation-knob placement
priority: P4
status: open
blocked_by:
- ENH-3097
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T16:33:59Z'
labels:
- automation
- refactor
- tech-debt
---

# ENH-3261: Remove deprecated automation_profile/disable_background_tasks/idle_timeout kwargs and rule on future automation-knob placement

## Summary

ENH-3097 threaded `AutomationContext` through `run_claude_command()` (both
`subprocess_utils.py` and the `issue_manager.py` wrapper),
`run_with_continuation()`, and every forwarding call site, migrating every
in-tree caller off the legacy `automation_profile`/`disable_background_tasks`/
`idle_timeout` kwargs. Those three kwargs remain on all three declaring
signatures as a deprecated compatibility shim (resolved internally via
`resolve_automation()`), per ENH-3094/ENH-3095/ENH-3096/ENH-3097's shared
Decision Rules ("explicit `automation=` wins, legacy kwargs still work").

Now that ENH-3097 has landed, every in-tree caller uses `automation=` —
the precondition ENH-3097's own Program Design § Signatures named for
removing the shim ("removing them is a follow-up once no in-tree caller uses
them — a precondition this issue itself satisfies"). This issue is that
follow-up.

## Current Behavior

`subprocess_utils.run_claude_command()`, the `issue_manager.py` wrapper of the
same name, and `issue_manager.run_with_continuation()` all still declare the
three legacy kwargs (`automation_profile: str | None = None`,
`disable_background_tasks: bool = False`, `idle_timeout: int = 0`) alongside
`automation: AutomationContext | None = None`, resolving the pair internally
via `resolve_automation()`. Every in-tree caller has migrated to
`automation=` (ENH-3097), so the legacy kwargs are now dead weight kept alive
only for backward compatibility that no in-tree code exercises.

## Expected Behavior

The three legacy kwargs are removed from all three declaring signatures, the
internal `resolve_automation()` folding at those sites is deleted (each
function reads `automation` directly), and the now-unreachable
`Test*AutomationShim` legacy-kwarg test cases for those three sites are
removed. `runner_spec._run_skill()`'s `spec.args` legacy dict keys are
addressed separately per a written ruling (they have out-of-tree consumers,
unlike the three signatures above — see Program Design § Decision Rules item 1). A written ruling also
exists for where future automation knobs (`timeout_kill_grace_seconds`,
`sandbox_mode`) belong.

## Motivation

ENH-3094's stated payoff for this whole four-issue chain was "the next
automation knob is a field on one frozen dataclass instead of a new
parameter threaded through six functions." Leaving the legacy shim in place
indefinitely — with no follow-up filed — means that payoff never actually
materializes: new contributors keep seeing three deprecated-but-present
kwargs on every signature and reasonably conclude the pattern is still "add
a kwarg," which is exactly what happened with `timeout_kill_grace_seconds`
(ENH-3130), landed after `AutomationContext` existed but shaped like the
pre-collapse world anyway.

## Proposed Solution

1. Delete `automation_profile`, `disable_background_tasks`, and
   `idle_timeout` from the three declaring signatures listed in Current
   Behavior, and their `resolve_automation()` folding.
2. Delete the legacy-kwarg-focused test cases in each site's
   `Test*AutomationShim` class (`test_legacy_kwargs_construct_context_internally`,
   `test_legacy_kwarg_alone_is_silent`, the conflict/warn tests, and
   `test_empty_context_equivalent_to_none`'s legacy-kwarg comparisons) —
   keep only the tests that exercise `automation=` directly.
3. Write the two rulings in Program Design § Decision Rules, either inline in
   this issue or as `.ll/decisions.yaml` entries via `ll-issues decisions`.
4. If the `timeout_kill_grace_seconds` ruling says "retrofit," add the field
   to `AutomationContext` and migrate its three call-chain sites the same
   way ENH-3097 did for the original three knobs.

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()` def
- `scripts/little_loops/issue_manager.py` — `run_claude_command()` wrapper
  def and `run_with_continuation()` def
- `docs/reference/API.md` — the two `run_claude_command()` mirrors (drop the
  deprecated-knob `Args:` entries added by ENH-3097)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/runner_spec.py` — no signature change, but its
  ruling (Program Design § Decision Rules item 1) determines whether its `spec.args` legacy keys stay
- `scripts/little_loops/fsm/executor.py`, `scripts/little_loops/fsm/runners.py`,
  `scripts/little_loops/parallel/worker_pool.py` — already forward
  `automation=` only (ENH-3097); unaffected by this removal

### Tests
- `scripts/tests/test_subprocess_utils.py::TestRunClaudeCommandAutomationShim`
- `scripts/tests/test_issue_manager.py` — the `run_with_continuation`
  legacy-kwarg forwarding tests added/retargeted by ENH-3097
- `scripts/tests/test_enh3097_no_mixed_automation_kwargs.py` — the AST guard
  can likely be deleted or narrowed once the legacy kwargs it guards against
  no longer exist on the three declaring signatures

### Documentation
- `docs/reference/API.md` mirrors (see Files to Modify)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- Confirmed anchors for the three declaring functions and their `resolve_automation()` folding: `subprocess_utils.py:348` (`run_claude_command()` def) with the fold at `subprocess_utils.py:458-464`; `issue_manager.py:140` (`run_claude_command()` wrapper def) with the fold at `issue_manager.py:227-233`; `issue_manager.py:280` (`run_with_continuation()` def) with the fold at `issue_manager.py:375-381`.
- `resolve_automation()` itself is defined at `host_runner.py:1886` and is **not** deleted by this issue — it stays shared, still called by `runner_spec.py:146` (`_run_skill()`) and by the 6 `HostRunner` implementations' own `build_streaming()` legacy shim (ENH-3095, out of scope here). Only the three declaring functions' call sites of it are removed.
- `runner_spec.py:128-132` already carries an in-code comment (tagged ENH-3097) stating the exact rationale for Decision Rules item 1 ("no in-tree producer sets either key; consumers are out-of-tree ll-harness/ll-action/extension runners") — this is effectively a pre-existing draft of the AC2 ruling, not a fresh decision to derive from scratch.
- Test correction: `test_issue_manager.py` has no `Test*AutomationShim` class. The actual legacy-kwarg-forwarding tests there are two standalone functions: `test_forwards_automation_profile_to_subprocess` (`test_issue_manager.py:1390`) and `test_automation_profile_defaults_to_none` (`test_issue_manager.py:1468`).
- `test_fsm_runners.py::TestActionRunnerAutomationShim` (line 650) is an automation-shim test class but targets `DefaultActionRunner.run()` (`fsm/runners.py:117`), not one of the three declaring functions in scope — it is unaffected by this issue's kwarg removal and should not be touched.
- `test_subprocess_utils.py::TestRunClaudeCommandAutomationShim` (line 2461) confirmed in scope; its legacy-kwarg tests (`test_legacy_kwargs_construct_context_internally`, `test_legacy_kwarg_alone_is_silent`, `test_explicit_context_wins_and_warns_on_conflict`, `test_explicit_context_wins_and_warns_on_disable_background_tasks_conflict`, `test_idle_timeout_zero_and_unset_both_resolve_automation_to_none`, `test_explicit_automation_discards_legacy_idle_timeout`, plus the legacy-kwarg comparisons inside `test_empty_context_equivalent_to_none`) all call `run_claude_command()` directly with the legacy kwargs and become call-site `TypeError`s once those kwargs are removed.

## Implementation Steps

1. Remove the three legacy kwargs and their `resolve_automation()` folding
   from the three declaring sites.
2. Remove the now-unreachable legacy-kwarg test cases; update `API.md`.
3. Write the two rulings (Program Design § Decision Rules) and act on the
   `timeout_kill_grace_seconds` one if it says "retrofit."
4. Run the full verification gate (AC 4).

## Impact

- **Priority**: P4 - cleanup with no user-visible effect; safe to defer
  behind higher-priority work, but should not be dropped or it becomes
  permanent scope creep on every future automation-knob addition.
- **Effort**: Small - mechanical kwarg removal plus two written decisions;
  no new runtime logic.
- **Risk**: Low - every in-tree caller already migrated off the legacy
  kwargs (ENH-3097 AC 10/AC 3), so removing them cannot silently change
  in-tree behavior. The only risk is breaking an out-of-tree caller that
  still passes the legacy kwargs directly to one of the three declaring
  functions (not the `runner_spec` dict keys, which stay either way).
- **Breaking Change**: Yes - for any caller (in-tree or out-of-tree) still
  passing `automation_profile=`/`disable_background_tasks=`/`idle_timeout=`
  directly to `run_claude_command()` or `run_with_continuation()`.

## Scope Boundaries

**In scope:** the three declaring signatures' legacy kwargs and their
internal folding; the two written rulings (Program Design § Decision Rules);
retrofitting `timeout_kill_grace_seconds` onto `AutomationContext` if the
ruling says to.

**Out of scope:** `runner_spec._run_skill()`'s `spec.args` legacy dict keys
(addressed by a ruling, not necessarily removed — they have out-of-tree
consumers this repo doesn't control); `HostRunner.build_streaming()`'s own
legacy `automation_profile`/`disable_background_tasks` kwargs (ENH-3095, a
separate boundary); actually retrofitting `sandbox_mode` (the ruling may
conclude host-specific knobs stay bare parameters).

## Program Design

No new runtime behavior — this is parameter/test deletion plus two written
decisions.

### Signatures

Delta, not replacement — remove three parameters (`automation_profile: str |
None = None`, `disable_background_tasks: bool = False`, `idle_timeout: int =
0`) from each signature below, keeping `automation` and every other
parameter untouched:

`def run_claude_command(automation: AutomationContext | None = None) -> subprocess.CompletedProcess[str]`

`def run_with_continuation(automation: AutomationContext | None = None) -> subprocess.CompletedProcess[str]`

### Call Path

Each of the three declaring functions currently calls
`resolve_automation(automation, automation_profile, disable_background_tasks,
idle_timeout, caller=...)` internally to fold the legacy trio; after removal
each reads `automation` directly with no fold step, and forwards it unchanged
to its own callee (`build_streaming()` / `_run_claude_base` / the wrapper)
exactly as it does today when `automation=` is already the incoming value.

### Decision Rules

1. **`runner_spec` legacy dict keys**: likely kept, because their consumers
   are out-of-tree (`ll-harness`/`ll-action`/extension runners) and this
   repo cannot coordinate a breaking change with them the way it could with
   an in-tree caller. Confirm this by re-checking for in-tree producers at
   implementation time (a repo-wide grep for `"automation_profile"` in
   `scripts/little_loops/` should still hit only the read in
   `runner_spec.py`, per ENH-3097's Codebase Research Findings).
2. **Future-knob placement** (`timeout_kill_grace_seconds`, `sandbox_mode`):
   decide field-vs-parameter for each, with `sandbox_mode`'s host-specificity
   as the deciding factor for whether host-specific knobs are categorically
   exempt from `AutomationContext` collapse.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- `resolve_automation()` (`host_runner.py:1886-1934`) confirmed semantics: when `automation` is given together with any legacy value, it emits a `DeprecationWarning` and returns `automation` unchanged — the legacy values (including `idle_timeout`) are **discarded, not merged**. When only legacy values are given, it constructs a fresh `AutomationContext(profile=automation_profile, disable_background_tasks=disable_background_tasks, idle_timeout=idle_timeout)`. When neither is given, it returns `None`. This confirms the issue's "explicit `automation=` wins, legacy kwargs still work" framing exactly.
- Evidence for Decision Rules item 2 (`timeout_kill_grace_seconds` / `sandbox_mode` placement): `timeout_kill_grace_seconds` is a bare `float` parameter at every layer today (`subprocess_utils.py:367`, `issue_manager.py:155`, `issue_manager.py:299`, `fsm/runners.py:133`, `runner_spec.py:156` via `spec.args`, `parallel/worker_pool.py:963`) — it has **no** `AutomationContext` field, and `subprocess_utils.run_claude_command()` never forwards it past its own local `_kill_process_group(process, grace_seconds=timeout_kill_grace_seconds)` call (`subprocess_utils.py:538,549`); it never reaches the host-runner/`build_streaming()` layer where `AutomationContext` actually flows. This is evidence toward "keep as bare parameter," not retrofit.
- `sandbox_mode` exists concretely only as a `CodexRunner`-private bare parameter (`host_runner.py:664`, `sandbox_mode: str | None = None`) — it is not on the shared `HostRunner` Protocol (`host_runner.py:242-255`), not on any of the other 7 `build_streaming()` implementations, and not an `AutomationContext` field. Its host-specificity (a `CodexRunner._VALID_SANDBOX_MODES` mapping to Codex-only CLI flags, `host_runner.py:600-614`) is direct evidence for the issue's proposed "host-specific knobs are categorically exempt from `AutomationContext` collapse" framing.

## Out of Scope

- Actually retrofitting `timeout_kill_grace_seconds`/`sandbox_mode` onto
  `AutomationContext` — this issue only has to rule on *whether* to, not
  do it, unless the ruling is trivial enough to land in the same change.
- Any change to `HostRunner.build_streaming()`'s own legacy
  `automation_profile`/`disable_background_tasks` kwargs (ENH-3095) — those
  are a separate boundary with the same shim shape but are not this issue's
  concern unless the knob-placement ruling above says otherwise.

## Acceptance Criteria

1. The three legacy kwargs are removed from `subprocess_utils.run_claude_command()`,
   `issue_manager.run_claude_command()`, and `issue_manager.run_with_continuation()`,
   along with their `resolve_automation()` folding and dead shim-kwarg tests.
2. A written ruling exists (in this issue or a linked decision entry) on
   whether `runner_spec._run_skill()`'s legacy `spec.args` keys are removed
   or kept indefinitely, with rationale.
3. A written ruling exists on where `timeout_kill_grace_seconds` and
   `sandbox_mode` — and, by extension, future per-call automation knobs —
   belong: `AutomationContext` fields, or parameters. `timeout_kill_grace_seconds`
   is retrofitted if the ruling says so.
4. `python -m pytest scripts/tests/`, `python -m mypy scripts/little_loops/`,
   and `ruff check scripts/` all pass/are clean.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.issues/enhancements/P3-ENH-3094-collapse-per-call-automation-kwargs-into-automationcontext.md` | Parent issue (status: done) |
| `.issues/enhancements/P3-ENH-3095-add-automationcontext-dataclass-and-thread-through-hostrunner-build-streaming.md` | Defines `AutomationContext` (status: done) |
| `.issues/enhancements/P3-ENH-3096-thread-automationcontext-through-actionrunner-run.md` | Threads through `ActionRunner.run()` (status: done) |
| `.issues/enhancements/P3-ENH-3097-thread-automationcontext-through-run-claude-command-and-callers.md` | Direct predecessor; migrated every in-tree caller off the legacy kwargs, the precondition this issue's removal depends on |

## Status

**Open** | Created: 2026-08-20 | Priority: P4


## Session Log
- `/ll:refine-issue` - 2026-08-20T18:02:20 - `c26819fc-4c17-46b0-bed5-ff46e41ae3e1.jsonl`
- `/ll:format-issue` - 2026-08-20T16:39:21 - `131da9b9-fc52-4bdb-a155-4ddc01aec740.jsonl`

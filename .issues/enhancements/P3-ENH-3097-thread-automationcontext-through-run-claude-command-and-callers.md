---
id: ENH-3097
type: ENH
title: Thread AutomationContext through run_claude_command() and its callers
priority: P3
status: open
parent: ENH-3094
blocked_by:
- ENH-3095
- BUG-3112
discovered_date: 2026-08-07
discovered_by: /ll:issue-size-review
labels:
- automation
- refactor
- tech-debt
testable: true
decision_needed: false
reconcile_attempted: true
relates_to:
- FEAT-3078
- FEAT-3033
- ENH-2714
- BUG-3093
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# ENH-3097: Thread AutomationContext through run_claude_command() and its callers

## Summary

Third of three children decomposed from ENH-3094. This child threads the
`AutomationContext` dataclass (introduced in ENH-3095) through
`run_claude_command()` in both `subprocess_utils.py` and the
`issue_manager.py` wrapper, `issue_manager.run_with_continuation()`,
`runner_spec.py`'s forwarding sites, `fsm/runners.py`'s decompose-then-forward
seam, and the remaining direct-call sites (`fsm/executor.py`'s baseline arm,
<!-- ll-prose-ok: _run_claude_base is a local import alias (`run_claude_command as _run_claude_base`), not a def-site symbol -->
`worker_pool.py:_run_claude_base`, and the five in-`issue_manager.py` call
sites).

**Dependency status**: ENH-3095 (`status: done`) defined `AutomationContext`
in `host_runner.py`, which this child imports. ENH-3096 (`status: done`) has
also since landed, threading `AutomationContext` through `ActionRunner.run()`
— its completed work is what surfaces the sixth call site this pass found at
`fsm/runners.py:177-191` (see Proposed Solution → Codebase Research
Findings). The dependency chain is fully satisfied; nothing external still
gates this issue.

## Parent Issue

Decomposed from ENH-3094: Collapse the per-call automation kwargs into a
single AutomationContext dataclass. See that issue for full motivation,
sequencing decision, and Program Design section — this child implements the
`run_claude_command()` / caller slice of that design.

## Current Behavior

Every function on the `run_claude_command()` call chain declares the automation
knobs as three independent parameters and forwards them positionally down the
next layer:

- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()` declares
  `idle_timeout: int = 0` (`:350`), `automation_profile: str | None = None`
  (`:358`), and `disable_background_tasks: bool = False` (`:359`) among its 22
  parameters. It forwards `automation_profile=`/`disable_background_tasks=` into
  `resolve_host().build_streaming()` (`:437-447`) — which since ENH-3095 also
  accepts a collapsed `automation=` it never receives — and consumes
  `idle_timeout` locally in the selector loop (`:513`, `:522`).
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()` already
  resolves the trio into one `AutomationContext` via `resolve_automation(...,
  caller="ActionRunner.run()")` (`:177-183`), then immediately **decomposes it
  back** into `resolved_automation_profile`/`resolved_disable_background_tasks`/
  `resolved_idle_timeout` (`:187-191`) to call `run_claude_command()`
  (`:234-252`). A comment at `:184-186` states why: "`run_claude_command()` has
  no `automation=` parameter until ENH-3097."
- `scripts/little_loops/issue_manager.py`, `runner_spec.py`,
  `fsm/executor.py`, `parallel/worker_pool.py` — same three-kwarg shape at
  every declaring and forwarding site (see Files to Modify for each).

The result is a collapse that stops halfway: `AutomationContext` exists and is
the currency at the `build_streaming()` and `ActionRunner.run()` boundaries, but
the `run_claude_command()` layer between them still speaks the old dialect, so
one boundary pays to decompose into it and the other never gets it at all.

## Expected Behavior

`run_claude_command()` accepts `automation: AutomationContext | None = None`, so
the context flows end to end without a decompose/recompose round trip:

- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()` gains
  `automation:`, resolves it against the retained legacy kwargs via
  `resolve_automation()`, forwards `automation=` alone into `build_streaming()`,
  and reads the selector-loop idle threshold off `automation.idle_timeout`.
  Loop logic unchanged.
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()` forwards
  `automation=automation` straight through (`:234-252`); the `:187-191`
  decomposition shrinks to only what the shell branch still reads, and the
  `:184-186` comment plus the `:81`/`:158` docstrings are rewritten.
- All other sites construct or forward a single `automation=` argument.
- The three legacy kwargs remain accepted everywhere and behave identically,
  so no caller outside this issue's scope breaks.

## Behavior Parity

This issue replaces code paths in `scripts/little_loops/subprocess_utils.py` and
`scripts/little_loops/fsm/runners.py`. Both replacements are pure refactors —
these are the behaviors that must survive them unchanged:

| Replaced path | Behavior that must be preserved | Verified by |
|---|---|---|
| `subprocess_utils.py` — the `automation_profile=`/`disable_background_tasks=` forward into `build_streaming()` | The invocation argv `build_streaming()` returns is byte-identical for the same effective profile and background-task setting. The collapsed `automation=` carries the same two values it did as separate kwargs. | `test_host_runner.py::test_claude_runner_matches_legacy_args` (existing argv snapshot); new `Test*AutomationShim` in `test_subprocess_utils.py` |
| `subprocess_utils.py` — the selector loop's `idle_timeout` read (`:513`, `:522`) | Idle detection fires at the same threshold, `0` still disables it, and the kill still raises `TimeoutExpired(..., output="idle_timeout")` (the sentinel `fsm/runners.py:254` and `ActionResult.timeout_kind` depend on). Only the *source* of the value changes. | `TestRunClaudeCommandIdleTimeout` / `TestRunClaudeCommandWaitTimeout` (existing, expected to pass unchanged); `test_feat3033_idle_timeout.py` |
| `fsm/runners.py:187-191` — the decompose-then-forward of the resolved context | The three values `run_claude_command()` receives are the same ones `resolve_automation()` resolved, so precedence (explicit `automation=` wins over legacy kwargs, warning names `ActionRunner.run()`) is unchanged. The `int(automation.idle_timeout or 0)` conversion disappears — harmless because `0` and `None` are equivalent at the consumer (Decision Rules). | `test_fsm_runners.py::TestActionRunnerAutomationShim` (assertions retargeted from decomposed kwargs to the captured `automation` object) |
| `fsm/runners.py` — the shell-branch reads below `:191` | **Partially replaced.** Only `resolved_idle_timeout` survives (read at `:346-347` and `:374`); `resolved_automation_profile` and `resolved_disable_background_tasks` were read *only* by the `run_claude_command()` call at `:246-247` and become dead code — see AC 7. | existing shell-branch tests; `ruff check scripts/` (F841) |
| `subprocess_utils.py` — idle detection when a caller passes `automation=` **and** a legacy `idle_timeout=` | **Deliberately not preserved — this is the one real behavior change.** See § Decision Rules → "Explicit `automation=` discards a legacy `idle_timeout`". | new `test_explicit_automation_discards_legacy_idle_timeout` in `test_subprocess_utils.py` (AC 12) |

No user-visible behavior, CLI surface, config key, or log line changes, with the
single exception of the `automation=` + legacy-`idle_timeout=` combination noted
in the last table row (no in-tree caller produces it after this issue). The one
new observable is a `DeprecationWarning` when a caller supplies both
`automation=` and a legacy kwarg — intended, and AC 9 asserts it does *not* fire
for in-tree forwarding.

## Impact

Contained cleanup, no runtime behavior change intended — every consumer reads
the same values by a different route, and the legacy kwargs stay live as a
compatibility shim. The payoff is that ENH-3094's collapse actually completes:
the next automation knob is a field on one frozen dataclass instead of a new
parameter threaded through six functions and asserted in a dozen tests. The
risk concentrated in this change is the three nested `resolve_automation()`
points it creates — a layer that forwards both `automation=` and a legacy kwarg
emits a `DeprecationWarning` on every `ll-auto` round (see Decision Rules and
AC 9, which exists to catch exactly that).

## Status

`open` — unblocked. `blocked_by: [ENH-3095, BUG-3112]` are both `status: done`,
and ENH-3096 has landed since filing. Ready to implement — the fifth-round
corrections in Verification Notes (2026-08-20) are applied and reviewed.

## Scope Boundaries

**In scope:** `run_claude_command()` in `subprocess_utils.py` and
`issue_manager.py`; `issue_manager.run_with_continuation()` (not
`worker_pool.WorkerPool._run_with_continuation()` — a distinct method at
`worker_pool.py:990` that carries no automation kwargs and needs no change);
`runner_spec.py`'s forwarding sites; `fsm/executor.py`'s baseline-arm direct
call; the bare `idle_timeout=` forward in `worker_pool.py`; the five
in-`issue_manager.py` call sites of the two changed functions
(`:853,:927,:1128,:1462` on the wrapper, `:1259` on `run_with_continuation()`);
the `docs/reference/API.md` mirrors. Current line numbers for each are in
§ Program Design → Codebase Research Findings (2026-08-20), which is the single
authoritative set — do not trust line numbers quoted elsewhere in this file.

**Out of scope:** `HostRunner.build_streaming()` (ENH-3095, a dependency);
`ActionRunner.run()`'s `resolve_automation()` call and `fsm/executor.py`'s
`extra_kwargs` assembly (ENH-3096). **In scope despite living inside
`ActionRunner.run()`:** `fsm/runners.py:187-252` — the decomposition of the
already-resolved `AutomationContext` back into legacy kwargs before calling
`run_claude_command()`, which exists only because `run_claude_command()` had
no `automation=` parameter until this issue closes that seam (see Codebase
Research Findings).

**Superseded carve-out (BUG-3093):** earlier revisions of this issue excluded
"fixing the BUG-3093 `idle_timeout`-only asymmetry at
`issue_manager.py:826,893,1089`". That carve-out is now moot — BUG-3093 is
`status: done` and all four of those sites (now `:853,:927,:1128,:1462`) pass
`automation_profile="ll-auto"` and `disable_background_tasks=` alongside
`idle_timeout=`. There is no remaining asymmetry to either fix or preserve
there; those sites are ordinary in-scope call sites that migrate to
`automation=` like every other. The one genuine remaining asymmetry is at
`worker_pool.py`'s `_run_claude_base` forward, which passes
`disable_background_tasks=` and `idle_timeout=` but has no `automation_profile=`
kwarg at all — preserve that (`AutomationContext(profile=None, ...)`), do not
fix it here.

## Proposed Solution

Replace `automation_profile` / `idle_timeout` keyword arguments with
`automation: AutomationContext | None = None` across
`run_claude_command()` (both the `subprocess_utils.py` implementation and the
`issue_manager.py` wrapper), `run_with_continuation()`, and every forwarding
site. Keep the legacy kwargs as deprecated pass-throughs per the parent's
Decision Rules (explicit `automation` context wins; deprecation warning
logged).

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` — replace per-knob kwargs with
  `automation` in `run_claude_command()` def (`:343-366`); call `resolve_host().build_streaming()`
  at `:436-447`; `idle_timeout` is consumed locally by the selector loop at
  `:513` and the `TimeoutExpired` it raises at `:522`, unaffected by this
  shape change beyond reading it off `automation.idle_timeout`.
  **Typing**: `AutomationContext.idle_timeout` is `float | None` while the
  retained legacy parameter is `int = 0`, so do **not** rebind the parameter —
  mypy rejects assigning `float | None` into it. Bind a new local, e.g.
  `effective_idle_timeout: float = (automation.idle_timeout or 0) if automation
  else 0`, and point `:513`/`:522` at that.
  (`subprocess.TimeoutExpired`'s `timeout` field accepts a float, so the
  `:522` raise needs no other change.)
- `scripts/little_loops/issue_manager.py` — wrapper `run_claude_command()`
  (def `:139-154`, forwards to `_run_claude_base` at `:213-226`) and
  `run_with_continuation()` (def `:260-279`, calls the wrapper at `:355-367`
  and `:537-550`)
- `scripts/little_loops/issue_manager.py` — the five in-file **call sites** of
  those two functions, each passing the full legacy trio
  (`automation_profile=`/`disable_background_tasks=`/`idle_timeout=`) today and
  each migrating to a single `automation=AutomationContext(...)`:
  `:853` (`_run_ready` Phase 1), `:927` (`_retry_cmd` Phase 1 retry),
  `:1128` (`decide-issue`), `:1462` (`FINALIZE_RETRY_PROMPT`) on the wrapper,
  and `:1259` on `run_with_continuation()` (the `ll-auto` implement phase).
  These keep working untouched via the legacy shim, but they are the largest
  cluster of callers in the tree — leaving them on the deprecated path defeats
  the collapse. Migrate them.
- `scripts/little_loops/runner_spec.py` — update `automation_profile` read
  (`:127`), `disable_background_tasks` read (`:131`), and the three forwarding
  sites (trace mode `:153-154`; stream_callback mode `:186-187`;
  blocking/default mode `:194-198`, which calls `resolve_host().build_streaming()`
  directly, bypassing `run_claude_command()`).
  **This site's compatibility surface is a dict, not a signature, and it is the
  only externally-facing one in this issue.** The values arrive via
  `spec.args.get("automation_profile")` / `.get("disable_background_tasks")` out
  of an untyped `spec.args: dict[str, Any]`, and **no in-tree producer sets
  either key** — a repo-wide grep for `"automation_profile"` across
  `scripts/little_loops/` hits only the read at `:127` itself. The keys exist for
  out-of-tree callers (`ll-harness`/`ll-action`/extension runners), which is
  precisely where a silent key rename breaks people with no test to catch it.
  So the contract must be stated, not left to the implementer: read a new
  `spec.args.get("automation")` (an `AutomationContext`) **and** keep honoring
  both legacy keys, folding them via `resolve_automation(..., caller="run_skill()")`.
  Do not rename or drop the legacy keys here. AC 2 and AC 13 cover this.
- `scripts/little_loops/fsm/executor.py` `_run_baseline_arm()` (`:3178-3243`) —
  the `run_claude_command()` call at `:3218-3225`; becomes a forward of
  `resolve_automation(None, None, False, float(idle_timeout) if idle_timeout
  else None, caller="_run_baseline_arm()")`. `idle_timeout` here resolves as
  `state.idle_timeout or self.fsm.default_idle_timeout or 0` (`:3199`) and is
  `0` on the common path, so unconditionally *constructing* an
  `AutomationContext` would turn today's `automation=None` into an all-default
  context on most runs. The shim already returns `None` in exactly that case,
  so it supplies the conditional without a hand-written `if` (see Decision
  Rules). This matches ENH-3096's landed precedent for `fsm/executor.py`'s
  `extra_kwargs` assembly — documented at `docs/reference/API.md:6098` as
  passing `automation=` only "when any of the three knobs resolves non-default".
- `scripts/little_loops/parallel/worker_pool.py` `_run_claude_base` forward
  (method `:895-952`, call at `:940-952`) — replace the bare `idle_timeout=` /
  `disable_background_tasks=` forwards with a single `automation=`, built by
  `resolve_automation(None, None, disable_background_tasks,
  float(idle) if idle else None, caller="WorkerPool._run_claude_command()")`
  where `idle = self.parallel_config.idle_timeout_per_issue`. Preserve the
  existing asymmetry that this site has no `automation_profile=` kwarg today
  (the shim leaves `profile=None`).
  **This site carries the same all-default hazard as the baseline arm above** —
  `idle_timeout_per_issue` may be `0` and `disable_background_tasks` `False`,
  so unconditional construction would replace today's `automation=None` with an
  all-default context. An earlier revision of this issue told the baseline arm
  to construct conditionally and this site to construct unconditionally, which
  were two contradictory rules for one hazard; routing both through the shim
  resolves it (see Decision Rules).
- `scripts/little_loops/fsm/runners.py:187-252` — `DefaultActionRunner.run()`
  already resolves an `AutomationContext` via `resolve_automation()` at
  `:177-183` (`caller="ActionRunner.run()"`, out of scope — ENH-3096); it then
  decomposes that context back into legacy kwargs at `:187-191` purely
  because `run_claude_command()` had no `automation=` parameter. Replace the
  decomposition with a direct `automation=automation` forward at the
  `run_claude_command()` call spanning `:234-252`. The decomposition shrinks
  rather than disappearing — but **only one of the three locals survives**, and
  the split is exact (verified by full-file usage grep):
  - `resolved_idle_timeout` (`:191`) — also read by the shell branch at
    `:346-347` and `:374`. **Keep.**
  - `resolved_automation_profile` (`:187`) and
    `resolved_disable_background_tasks` (`:188-190`) — read *only* at
    `:246-247`, the `run_claude_command()` call this issue collapses. **Delete
    both**; leaving them is dead code and `ruff check scripts/` flags it (F841).
- `scripts/little_loops/fsm/runners.py` prose — three comment/docstring sites
  describe the behavior being removed and must be rewritten alongside it: the
  ENH-3097 comment at `:184-186` ("`run_claude_command()` has no `automation=`
  parameter until ENH-3097, so decompose the resolved context back into legacy
  kwargs for that forwarding call") and the two parameter docstrings at `:81`
  and `:158` ("Forwarded to `run_claude_command()` when ...").
- Every call site above also folds `disable_background_tasks: bool = False`
  (an `AutomationContext` field alongside `profile`/`idle_timeout`,
  `host_runner.py:172-190`) into `automation=`, not just the
  `automation_profile`/`idle_timeout` pair.
- Each new call site should invoke the existing `resolve_automation()` shim
  (`host_runner.py:1886-1934`) rather than reimplementing the legacy-kwarg
  fold inline, passing its own identifying `caller=` string (asserted
  verbatim in tests, e.g. `pytest.warns(DeprecationWarning, match=<caller>)`).
  Having resolved, **forward only `automation=` onward — never `automation=`
  plus a legacy kwarg** (see Decision Rules).
- `docs/reference/API.md` — `issue_manager.run_claude_command()` mirror
  (`:2853-2894`) and `subprocess_utils.run_claude_command()` mirror
  (`:11653-11680`); both confirmed byte-for-byte in sync with current code as
  of 2026-08-20 — update alongside the signature change.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:6072-6104` — the `#### ActionRunner Protocol` section
  is a third, previously-unlisted mirror location: its prose at `:6098`
  reads "`DefaultActionRunner` decomposes the resolved context back into
  `automation_profile=`/`disable_background_tasks=`/`idle_timeout=` when
  forwarding to `run_claude_command()`, which has no `automation` parameter
  until ENH-3097." — this sentence describes exactly the pre-ENH-3097
  decomposition behavior this issue removes (`fsm/runners.py:187-191`) and
  must be rewritten once that decomposition is replaced with a direct
  `automation=automation` forward [Agent 2 finding, confirmed by direct read]
- `scripts/little_loops/workflow_sequence/__init__.py:285` — calls
  `run_claude_command(command=skill_cmd, timeout=300)` with no
  `automation_profile`/`idle_timeout` kwargs; unaffected by the signature
  change (legacy-kwarg shim is additive), no code change needed, listed for
  completeness [Agent 1 finding, confirmed by direct read]
- `scripts/little_loops/cli/generate_skill_descriptions.py:119` — calls
  `run_claude_command(command=prompt, timeout=60)` with no
  `automation_profile`/`idle_timeout` kwargs; same as above, no code change
  needed [Agent 1 finding, confirmed by direct read]

### Tests
- `scripts/tests/test_issue_manager.py:1402-1483` — patches
  `little_loops.issue_manager.run_claude_command` and asserts
  `kwargs.get("automation_profile")` / `kwargs.get("disable_background_tasks")`
  on the forwarded call; update these assertions (or add a parallel shim-test
  class) once `run_with_continuation()` forwards `automation=` instead of the
  bare trio
- `scripts/tests/test_worker_pool.py:2902-2914` — `mock_run_claude` has an
  explicit signature (`idle_timeout: int = 0`, `disable_background_tasks: bool
  = False`, no `**kwargs`), so it raises `TypeError` the moment the production
  forward starts passing `automation=`; gains `automation`
- `scripts/tests/test_runner_spec.py:33-38` — `FakeRunner.build_streaming(**_: object)`;
  verify this stays resilient with no signature change needed
- Each of this issue's call sites gains a parallel `Test*AutomationShim`
  class with the five-test shape used by the ENH-3095/ENH-3096 precedent:
  `test_legacy_kwargs_construct_context_internally`,
  `test_legacy_kwarg_alone_is_silent` (`warnings.simplefilter("error")` +
  bare legacy kwarg must not raise),
  `test_explicit_context_wins_and_warns_on_conflict`
  (`pytest.warns(DeprecationWarning, match=<caller>)`),
  `test_explicit_context_wins_and_warns_on_disable_background_tasks_conflict`,
  `test_empty_context_equivalent_to_none` — see `test_host_runner.py:1587-1660+`
  (`TestAutomationContext`, ENH-3095) and `test_fsm_runners.py:648-727`
  (`TestActionRunnerAutomationShim`, ENH-3096) as the shape to mirror.

### Tests (wiring gaps)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_runners.py::TestActionRunnerAutomationShim` — six
  assertions inspect the mock-captured *decomposed* legacy kwargs, the exact
  behavior `runners.py:187-191` loses when it starts forwarding
  `automation=automation` directly; each must switch to inspecting a
  captured `"automation"` key (an `AutomationContext`) instead:
  `test_legacy_kwargs_construct_context_internally` (`:671-672`,
  `captured.get("automation_profile")` / `.get("disable_background_tasks")`),
  `test_explicit_context_wins_and_warns_on_conflict` (`:691`,
  `captured.get("automation_profile")`),
  `test_explicit_context_wins_and_warns_on_disable_background_tasks_conflict`
  (`:701`, `captured.get("disable_background_tasks")`),
  `test_empty_context_equivalent_to_none` (`:707-711`, compares
  `.get("automation_profile")`/`.get("disable_background_tasks")`/
  `.get("idle_timeout")` between two calls),
  `test_explicit_automation_discards_legacy_idle_timeout` (`:725-726`,
  `captured.get("idle_timeout")` / `.get("automation_profile")`)
  [Agent 3 finding, confirmed by direct read of `runners.py:187-191`'s role]
- `scripts/tests/test_feat3033_idle_timeout.py` — two assertions on the same
  decomposed-kwarg pattern, same failure mode:
  `test_idle_timeout_forwarded_to_run_claude_command` (`:90-105`, patches
  `little_loops.fsm.runners.run_claude_command`, asserts
  `received["idle_timeout"] == 42`) and
  `test_baseline_arm_forwards_idle_timeout` (`:350-372`, patches
  `little_loops.fsm.executor.run_claude_command`, asserts
  `received["idle_timeout"] == 7`) — the second exercises
  `fsm/executor.py`'s `_run_baseline_arm()`, one of this issue's own primary
  call sites, so this assertion breaks directly from this issue's own change
  to that site, not just the `runners.py` decomposition removal
  [Agent 3 finding]
- `scripts/tests/test_subprocess_utils.py` — has zero `AutomationContext`
  coverage today; its existing `idle_timeout=` calls (`TestRunClaudeCommandIdleTimeout`/
  `TestRunClaudeCommandWaitTimeout`, e.g. `:1085,1104,1136,1172,1212-1213,2694`)
  exercise the real function via the legacy-kwarg shim path and are expected
  to keep passing unchanged (backward-compat is additive, not a
  breaking case) — but this file is where the new `Test*AutomationShim`
  class for `run_claude_command()` itself belongs, since it's the only
  primary call site with no existing shim-test class of any kind
  [Agent 3 finding]

_Added by `/ll:verify-issues` — 2026-08-19 — four further invalidation sites,
each confirmed by direct read. Three of them break from **this issue's own
AC 10**, not from a sibling's change:_

- `scripts/tests/test_issue_manager.py:2271` — `assert
  mock_run.call_args.kwargs["automation_profile"] == "ll-auto"`, the BUG-3093
  guard on the Phase 1 ready-issue site (`issue_manager.py:853`). AC 10 migrates
  that site to `automation=AutomationContext(...)`, so the key disappears and
  the subscript raises `KeyError` — a hard failure, not a changed value.
- `scripts/tests/test_issue_manager.py:2304` —
  `captured_profiles.append(kwargs.get("automation_profile"))` on the
  ready-issue fallback path; same migration, collects `None` instead of
  `"ll-auto"` and the downstream assertion fails.
- `scripts/tests/test_issue_manager.py:4901` — `assert all(call.kwargs.get(
  "automation_profile") == "ll-auto" for call in mock_cmd.call_args_list)`,
  covering both the ready-issue and decide-issue (`issue_manager.py:1128`)
  calls; fails for the same reason.
- `scripts/tests/test_fsm_runners.py:629`
  (`test_disable_background_tasks_kwarg_forwarded`, FEAT-3078) — asserts
  `captured_kwargs.get("disable_background_tasks") is True` on the
  mock-captured `run_claude_command` kwargs. It sits **outside**
  `TestActionRunnerAutomationShim` (which begins at `:648`), so the
  per-assertion enumeration above — scoped to `:671-726` — misses it, yet
  AC 7's removal of the `runners.py:187-191` decomposition breaks it
  identically. Retarget to the captured `automation` object's
  `.disable_background_tasks`.

  These four are guards, not incidental assertions: the three BUG-3093 ones
  exist to prove the `ll-auto` profile is still declared on those subprocesses,
  and the FEAT-3078 one that background-task disabling still reaches the child.
  Retarget them to `kwargs["automation"].profile` /
  `.disable_background_tasks` — do not delete them with the kwarg shape.

### Tests (new, from the 2026-08-19 review pass)

- **No-spurious-warning test for the three-layer chain** (AC 9, and the
  highest-value new test here). Call
  `issue_manager.run_claude_command(..., automation_profile="ll-auto",
  disable_background_tasks=True, idle_timeout=30)` under
  `warnings.simplefilter("error")` with the real `subprocess_utils` and
  `host_runner` layers in play (mock only at the `subprocess.Popen` boundary),
  and assert it does not raise. This fails loudly if any layer forwards
  `automation=` *and* a legacy kwarg onward, which is the failure mode
  Decision Rules calls out — `resolve_automation()` warns on that combination
  (`host_runner.py:1918-1927`), and nothing else in the suite would catch it.
- **`0`-vs-`None` idle regression guard**: assert that
  `run_claude_command(..., idle_timeout=0)` and `run_claude_command(...)` with
  no idle kwarg produce identical behavior (both resolve to
  `automation is None`, both leave the selector loop's idle branch dead) — pins
  the Decision Rules ruling so a later reader doesn't "fix" the shim's falsy
  check.
- **Conditional baseline-arm construction** (AC 11): assert
  `_run_baseline_arm()` forwards `automation=None` (or omits it) when
  `state.idle_timeout` and `fsm.default_idle_timeout` are both unset, and an
  `AutomationContext(idle_timeout=N)` when either is set. Extend
  `test_feat3033_idle_timeout.py::test_baseline_arm_forwards_idle_timeout`,
  which already patches `little_loops.fsm.executor.run_claude_command` and is
  the natural home.
- **The five `issue_manager.py` call sites** (AC 10): the existing
  `test_issue_manager.py` assertions that capture `kwargs.get("automation_profile")`
  switch to capturing `kwargs["automation"].profile`.

### Tests (new, from the 2026-08-20 pre-implementation review)

- **Idle-discard contract test** (AC 12, the highest-value new test in this
  round): assert that `run_claude_command(automation=AutomationContext(
  profile="ll-auto"), idle_timeout=1800)` leaves the selector loop's idle
  branch dead — idle detection is **off**, not armed at 1800 — because
  `resolve_automation()` drops the legacy value rather than merging it. Pair it
  with the AC 12 assertion that no in-tree site passes the combination. Home:
  the new `Test*AutomationShim` class in `test_subprocess_utils.py`.
- **`runner_spec` legacy-dict-key test** (AC 13): drive `_run_skill` with
  `spec.args = {"automation_profile": "ll-auto", "disable_background_tasks":
  True}` (no `"automation"` key) and assert the resolved context reaching
  `build_streaming()` carries both values — the out-of-tree compatibility
  guarantee, currently untested because no in-tree producer sets those keys.
  Add the mirror case for a `spec.args["automation"]` context, and the conflict
  case (both present → explicit context wins, `DeprecationWarning` matching
  `run_skill()`).
- **`worker_pool` all-default omission** (AC 3/AC 11): assert
  `_run_claude_command()` forwards `automation=None` when
  `idle_timeout_per_issue` is `0` and `disable_background_tasks` is `False`,
  and a populated context otherwise — the same shape AC 11 already requires of
  the baseline arm. `test_worker_pool.py:2902-2914`'s `mock_run_claude` is the
  natural capture point (it gains `automation` per § Tests above).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **Sixth call site not in original scope — `fsm/runners.py`'s `DefaultActionRunner.run()`** (ENH-3096's completed work): at `runners.py:177-183` it already calls the shared `resolve_automation()` helper (see below), then explicitly **decomposes the resolved context back into legacy kwargs** at `runners.py:187-191` before calling `run_claude_command()` at `runners.py:234-252`. A comment at `runners.py:184-186` reads: "`run_claude_command()` has no `automation=` parameter until ENH-3097, so decompose the resolved context back into legacy kwargs for that forwarding call ... below." This decomposition is the exact seam this issue closes — once `run_claude_command()` accepts `automation:`, this call site should pass `automation=automation` directly instead of decomposing. Add `fsm/runners.py:187-252` to Files to Modify.
- **A reusable shim helper already exists and should be called, not reimplemented**: `resolve_automation(automation, automation_profile, disable_background_tasks, idle_timeout, *, caller="build_streaming()")` at `host_runner.py:1886-1934`. It implements exactly the Decision Rules behavior this issue specifies (explicit `automation=` wins and warns via `DeprecationWarning` naming `caller` when legacy kwargs are also present; legacy-alone builds `AutomationContext(...)` silently — no warning; neither given returns `None`). It is already consumed by `fsm/runners.py:177-183` (`caller="ActionRunner.run()"`) and should be the shim this issue's five/six call sites call, rather than each site reimplementing the fold inline.
- **Third field also collapses into `automation=`**: `disable_background_tasks: bool = False` is a field on `AutomationContext` (`host_runner.py:172-190`) alongside `profile`/`idle_timeout`, and is present as a legacy kwarg at every in-scope call site — not just the `automation_profile`/`idle_timeout` pair this issue's Proposed Solution text names. Note: `worker_pool.py`'s `_run_claude_base` forward (`worker_pool.py:940-952`) already passes `disable_background_tasks=` but has no `automation_profile=` kwarg at all — a pre-existing asymmetry to preserve (not fix) when threading `automation=` through that site.

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **Test convention to follow** (from ENH-3095/ENH-3096 precedent): both landed siblings added a parallel `Test*AutomationShim`/`TestAutomationContext` class with an identical five-test shape — `test_legacy_kwargs_construct_context_internally`, `test_legacy_kwarg_alone_is_silent` (`warnings.simplefilter("error")` + bare legacy kwarg must not raise), `test_explicit_context_wins_and_warns_on_conflict` (`pytest.warns(DeprecationWarning, match=<caller>)`), `test_explicit_context_wins_and_warns_on_disable_background_tasks_conflict`, `test_empty_context_equivalent_to_none`. See `test_host_runner.py:1587-1660+` (`TestAutomationContext`, ENH-3095) and `test_fsm_runners.py:648-727` (`TestActionRunnerAutomationShim`, ENH-3096, whose docstring says it mirrors the former). This issue's five/six call sites are expected to gain the same test shape.
- **Existing tests assert on legacy kwarg names directly, not an `automation=` object**: `test_issue_manager.py:1402-1483` patches `little_loops.issue_manager.run_claude_command` and asserts `kwargs.get("automation_profile")` / `kwargs.get("disable_background_tasks")` on the forwarded call — these assertions will need updating (or a new parallel shim-test class added alongside them) once `run_with_continuation()` forwards `automation=` instead of the bare trio.

## Acceptance Criteria

1. `run_claude_command()` in both `subprocess_utils.py` and
   `issue_manager.py`, plus `run_with_continuation()`, accept
   `automation: AutomationContext | None = None` in place of
   `automation_profile`/`idle_timeout`.
2. `runner_spec.py`'s `automation_profile` read (`:127`), its
   `disable_background_tasks` read (`:131`), and its three forwarding sites
   (`:153-154,186-187,194-198`) updated to the collapsed parameter. `_run_skill`
   reads a new `spec.args.get("automation")` key and folds it with the two
   legacy `spec.args` keys via `resolve_automation(..., caller="run_skill()")`.
3. `fsm/executor.py:3218-3225` and `worker_pool.py:940-952` forward a single
   `automation=` instead of bare `idle_timeout=`/`disable_background_tasks=`
   kwargs, obtaining it from `resolve_automation()` (not a hand-rolled
   conditional) so both sites still pass `None` when every knob is default.
4. The `automation_profile`/`idle_timeout` keywords still work, constructing
   an `AutomationContext` internally, per the ENH-3095 shim pattern.
5. `docs/reference/API.md` `issue_manager.run_claude_command()` mirror
   updated.
6. `python -m pytest scripts/tests/` passes, **and** `python -m mypy
   scripts/little_loops/` and `ruff check scripts/` are clean. The two static
   gates are load-bearing here, not boilerplate: mypy is what catches the
   `float | None` → `int` rebind at `subprocess_utils.py` (see Files to Modify),
   and ruff F841 is what catches the two `fsm/runners.py` locals that go dead
   under AC 7. Both are project gates per `.claude/CLAUDE.md` § Development.
7. `fsm/runners.py`'s `DefaultActionRunner.run()` forwards `automation=automation`
   directly to `run_claude_command()` (`:234-252`) instead of decomposing it
   back into legacy kwargs, and the now-unused `resolved_automation_profile` /
   `resolved_disable_background_tasks` locals (`:187-190`) are deleted.
   `resolved_idle_timeout` (`:191`) stays — the shell branch reads it at
   `:346-347` and `:374`.
8. `docs/reference/API.md:6072-6104`'s `#### ActionRunner Protocol` section
   prose no longer says `run_claude_command()` "has no `automation` parameter
   until ENH-3097" (`/ll:wire-issue` finding — a third mirror location beyond
   criterion 5's), and `fsm/runners.py`'s matching in-code prose (the ENH-3097
   comment at `:184-186` and the two parameter docstrings at `:81`/`:158`) is
   rewritten to match the new forwarding behavior.
9. `runner_spec.py`'s blocking/default arm forwards `automation=` **only** to
   its direct `resolve_host().build_streaming()` call, with no legacy kwarg
   alongside it — so `build_streaming()`'s own `resolve_automation()` never
   sees a spurious conflict. Same requirement for
   `subprocess_utils.run_claude_command()`'s `build_streaming()` forward and
   the `issue_manager.py` wrapper's `_run_claude_base` forward: a test asserts
   that a legacy-kwarg call through the full chain emits **no**
   `DeprecationWarning` (`warnings.simplefilter("error")`).
10. The five in-`issue_manager.py` call sites (`:853,:927,:1128,:1462,:1259`)
    pass `automation=AutomationContext(...)` rather than the legacy trio. The
    three existing BUG-3093 profile guards over those sites —
    `test_issue_manager.py:2271`, `:2304`, `:4901` — are **retargeted** to
    `kwargs["automation"].profile == "ll-auto"`, not deleted: the guarantee
    they enforce (these subprocesses declare themselves under automation)
    must survive the parameter-shape change. Likewise
    `test_fsm_runners.py:629` (FEAT-3078) retargets to
    `kwargs["automation"].disable_background_tasks` under AC 7.
11. `fsm/executor.py`'s baseline arm passes a non-`None` `automation=` only when
    `idle_timeout` resolves truthy, preserving today's `automation=None` on the
    common path (matching ENH-3096's `extra_kwargs` precedent). The same holds
    at `worker_pool.py:940-952`, which carries the identical hazard. Both get
    this from `resolve_automation()` returning `None` for an all-default input
    rather than from a hand-written `if` (AC 3, Decision Rules).
12. A test pins that an explicit `automation=` **discards** a legacy
    `idle_timeout=` at `subprocess_utils.run_claude_command()` — i.e. that
    `automation=AutomationContext(profile="ll-auto"), idle_timeout=N` runs with
    idle detection **off**, not at threshold `N`. This is the one intended
    behavior change in the issue (Behavior Parity, last row) and the one place
    where the shim's uniform "explicit wins" rule has a live consequence
    instead of an inert one. Mirror
    `test_fsm_runners.py::test_explicit_automation_discards_legacy_idle_timeout`.
    No in-tree call site may produce this combination.
13. `runner_spec._run_skill`'s legacy `spec.args` keys (`"automation_profile"`,
    `"disable_background_tasks"`) still work unchanged, with a test asserting
    it. This is the only compatibility surface in the issue that is a **dict
    rather than a function signature**, and it has no in-tree producer — every
    consumer is out-of-tree (`ll-harness`/`ll-action`/extension runners), so
    nothing else in the suite would catch a key rename.
14. A follow-up issue is filed for removing the legacy
    `automation_profile`/`disable_background_tasks`/`idle_timeout` kwargs from
    all three declaring sites, and `ENH-3094` (parent) is closed. After this
    issue every in-tree caller is migrated, which is the precondition
    § Program Design → Signatures names for that removal — so the successor is
    actionable the moment this lands. Without it the compatibility shim becomes
    permanent by default, which inverts the parent's whole purpose.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **Current confirmed line numbers (2026-08-20)**, superseding the 2026-08-19 verify-pass estimates in Verification Notes:
  - `subprocess_utils.run_claude_command()` def: `:343-366` (18 params, no `automation:`); forwards `automation_profile`/`disable_background_tasks` into `resolve_host().build_streaming()` at `:436-447`; `idle_timeout` consumed directly by the selector loop at `:513` (`if idle_timeout and (now - last_output_time) > idle_timeout:`) and the resulting `TimeoutExpired(..., output="idle_timeout")` raised at `:522`.
  - `issue_manager.py` wrapper `run_claude_command()`: def `:139-154`; forwards to `_run_claude_base` (imported alias for `subprocess_utils.run_claude_command`, `issue_manager.py:66`) at `:213-226`.
  - `issue_manager.run_with_continuation()`: def `:260-279`; calls the wrapper at two sites — `:355-367` (main loop) and `:537-550` (Option E `--continue` handoff branch).
  - `runner_spec.py`: `automation_profile` read `:127`; `disable_background_tasks` read `:131`; `timeout_kill_grace_seconds` read `:136`; three forwarding sites — trace mode `:153-154`, stream_callback mode `:186-187`, blocking/default mode `:194-198` (calls `resolve_host().build_streaming()` directly, bypassing `run_claude_command()`).
  - `fsm/executor.py` `_run_baseline_arm()`: def `:3178-3243`; `run_claude_command()` call `:3218-3225` — passes only `idle_timeout=idle_timeout` (resolved at `:3199`), no `automation_profile=`/`disable_background_tasks=` at all (a documented existing gap, comment at `:3204-3206`).
  - `worker_pool.py` `_run_claude_base` forward: method spans `:895-952`, call at `:940-952`; import alias at `:39`.
  - `docs/reference/API.md`: both mirrors confirmed byte-for-byte in sync with current code (no drift) — `issue_manager.run_claude_command()` mirror `:2853-2894`, `subprocess_utils.run_claude_command()` mirror `:11653-11680`.
- **`resolve_automation()` full signature** (the shim to call, not reimplement): `resolve_automation(automation: AutomationContext | None, automation_profile: str | None, disable_background_tasks: bool, idle_timeout: float | None = None, *, caller: str = "build_streaming()") -> AutomationContext | None` — `host_runner.py:1886-1934`. `caller=` is asserted verbatim in tests (e.g. `pytest.warns(DeprecationWarning, match="ActionRunner.run()")`); each new call site in this issue's scope should pass its own identifying `caller=` string.
_Added by review pass — 2026-08-19 — re-verified against `main`:_

- **All 2026-08-20 line numbers above re-confirmed accurate** (`subprocess_utils.py:343-366`/`:437-447`/`:513`/`:522`; `issue_manager.py:139-154`/`:213-226`/`:260-279`/`:355-367`/`:537-550`; `runner_spec.py:127`/`:131`/`:148`/`:182`/`:194`; `fsm/executor.py:3178`/`:3199`/`:3218`; `worker_pool.py:940`; `fsm/runners.py:177-191`/`:234-252`; `docs/reference/API.md:2853`/`:6072`/`:6098`/`:11653`). One correction applied: `test_worker_pool.py`'s `mock_run_claude` is at `:2902-2914`, not `:2833`.
- **`HostRunner.build_streaming()` already accepts `automation=`** (`host_runner.py:242-255` Protocol, `:348-362` `ClaudeCodeRunner`, which calls `resolve_automation()` at `:362`). ENH-3095 is fully landed at that boundary, so the `automation=` forwards this issue adds have a live parameter to land in — no coordination needed, and no reason for any site to keep forwarding legacy kwargs downward.
- **`resolve_automation()` treats a bare `idle_timeout=0` as "not supplied"** — `legacy_used = automation_profile is not None or disable_background_tasks or bool(idle_timeout)` (`host_runner.py:1917`), so it returns `None` rather than `AutomationContext(idle_timeout=0)`. This is intentional and matches every consumer (`subprocess_utils.py:513`'s `if idle_timeout and ...`; `fsm/runners.py:191`'s `int(automation.idle_timeout or 0)`). See Decision Rules — do not fork the shim over it.
- **BUG-3093's asymmetry no longer exists.** All four former sites now pass `automation_profile="ll-auto"` and `disable_background_tasks=config.orchestration.disable_background_tasks` alongside `idle_timeout=` (`issue_manager.py:853`, `:927`, `:1128`, `:1462`), each with a `# BUG-3093:` comment explaining the profile. A fifth site, `:1259` (`run_with_continuation()`, the ll-auto implement phase), does the same with a `# BUG-3058:` comment. All five are in scope for the parameter-shape change.
- **`worker_pool.py` has its own `_run_with_continuation()`** at `:990`, distinct from `issue_manager.run_with_continuation()`; it funnels through `self._run_claude_command()` (`:896-952`) and carries no automation kwargs of its own, so it needs no change. The four in-file callers of `_run_claude_command()` (`:449`, `:586`, `:1034`, `:1184`) likewise pass none.
- **`AutomationContext` has no alternate constructor** — plain `@dataclass(frozen=True)` at `host_runner.py:172-190` with `profile: str | None = None`, `idle_timeout: float | None = None`, `disable_background_tasks: bool = False`. No `from_legacy()` classmethod exists; construction is always `AutomationContext(profile=..., idle_timeout=..., disable_background_tasks=...)` or via `resolve_automation()`.
- **`fsm/runners.py:177-191` (`DefaultActionRunner.run()`) is the seam this issue closes**: already calls `resolve_automation(automation, automation_profile, disable_background_tasks, float(idle_timeout) if idle_timeout else None, caller="ActionRunner.run()")` at `:177-183`, then decomposes the result back to `resolved_automation_profile`/`resolved_disable_background_tasks`/`resolved_idle_timeout` at `:187-191` (using `int(automation.idle_timeout or 0)` for the timeout — another `0`/`None` collapse point matching the pattern this issue's existing Decision Rules bullet already warns against at its own five sites) purely because `run_claude_command()` doesn't accept `automation=` yet. Once it does, this decomposition should be replaced with a direct `automation=automation` forward at the `run_claude_command()` call spanning `runners.py:234-252`.

### Types
- Imports `AutomationContext` from `host_runner.py` (defined by ENH-3095, not yet landed — this issue is `blocked_by: [ENH-3095]`).

### Signatures

**Expressed as a delta, not a replacement signature.** The three functions are
not reduced to a four-parameter shape — `subprocess_utils.run_claude_command()`
alone declares 22 parameters (`:343-366`), most of them callbacks unrelated to
automation. The change to each is exactly:

- **Add** `automation: AutomationContext | None = None`.
- **Retain** `automation_profile: str | None = None`,
  `disable_background_tasks: bool = False`, and `idle_timeout: int = 0` as
  deprecated pass-throughs, resolved internally via `resolve_automation()` per
  AC 4 and the Decision Rules. They are **not** removed by this issue; removing
  them is a follow-up once no in-tree caller uses them — a precondition this
  issue itself satisfies, since AC 10 and AC 3 migrate every in-tree caller.
  **File that successor issue as part of closing this one (AC 14)**; there is no
  fourth child under ENH-3094 today, so an unfiled follow-up means the shim ships
  as the permanent shape.
- **Leave every other parameter untouched** (`timeout`, `working_dir`,
  `stream_callback`, the `on_*` callbacks, `agent`, `tools`, `model`,
  `resume_session`, `post_stream_close_grace_seconds`,
  `timeout_kill_grace_seconds`, `workspace_root`, and — on the
  `issue_manager.py` wrapper — `logger`, `stream_output`, `preview_full`).

Applies identically to all three declaring sites:
`subprocess_utils.run_claude_command()`, the `issue_manager.run_claude_command()`
wrapper, and `issue_manager.run_with_continuation()`. This mirrors the shape
`HostRunner.build_streaming()` already has post-ENH-3095 (`host_runner.py:242-255`),
where `automation` sits alongside the retained
`automation_profile`/`disable_background_tasks` pair.
- `runner_spec.py`'s `_run_skill` reads `automation_profile` out of the untyped `spec.args: dict[str, Any]` (`:124-128`, `spec.args.get("automation_profile")`) — the only one of these sites where the value arrives via dict lookup rather than a named parameter; becomes reading/constructing an `AutomationContext` the same way. `idle_timeout` is not threaded through `runner_spec.py` today (no `spec.args.get("idle_timeout")` anywhere in `_run_skill`) and this issue does not add it.

### Call Path

_Deliberately prose-only. This section previously carried its own line numbers
from the original filing (`subprocess_utils.py:402-411`/`:478-487`,
`issue_manager.py:207-218`/`:340-350`, `runner_spec.py:140-149`/`:172-177`/`:182`,
`fsm/executor.py:2771-2778`, `worker_pool.py:924-934`) that had drifted by
hundreds of lines and contradicted the correct set in Files to Modify. Numbers
live in **one** place now: § Program Design → Codebase Research Findings
(2026-08-20). Do not re-add them here._

- `subprocess_utils.run_claude_command()` — the `resolve_host().build_streaming()` call forwards `automation_profile=`/`disable_background_tasks=` today; becomes a single `automation=automation` forward, consuming ENH-3095's boundary. Do not forward the legacy kwargs alongside it (Decision Rules).
- `subprocess_utils.run_claude_command()` selector loop — `idle_timeout` is consumed locally (`if idle_timeout and (now - last_output_time) > idle_timeout: raise TimeoutExpired(..., output="idle_timeout")`) and never reaches `build_streaming()`; the read becomes `automation.idle_timeout if automation else 0`, loop logic unchanged.
<!-- ll-prose-ok: _run_claude_base is a local import alias (`run_claude_command as _run_claude_base`), not a def-site symbol -->
- `issue_manager.py` wrapper forwards 1:1 to `issue_manager.py:_run_claude_base` (`subprocess_utils.run_claude_command`, imported alias) — becomes a 1:1 forward of `automation=automation`.
- `issue_manager.run_with_continuation()` forwards to the wrapper on every continuation round (main loop and the Option E `--continue` handoff branch) — same collapse, same forwarding shape.
- The five in-`issue_manager.py` call sites of those two functions each build one `AutomationContext(profile="ll-auto", disable_background_tasks=config.orchestration.disable_background_tasks, idle_timeout=config.automation.idle_timeout_seconds)` in place of the legacy trio.
- `runner_spec.py` three forwarding sites: trace mode and stream_callback mode (both call `run_claude_command`), and blocking/default mode (calls `resolve_host().build_streaming()` directly, bypassing `run_claude_command()` entirely) — each currently passes bare `automation_profile=`/`disable_background_tasks=`; each becomes `automation=automation`. The `automation_profile`/`disable_background_tasks` values still originate from `spec.args` dict lookups, which do not change shape.
- `fsm/executor.py` baseline arm — currently passes only `idle_timeout=idle_timeout` (no `automation_profile` at all today) — becomes a conditional `automation=AutomationContext(idle_timeout=idle_timeout)` (see Files to Modify for why conditional).
- `worker_pool.py` `_run_claude_base` forward — currently passes `idle_timeout=self.parallel_config.idle_timeout_per_issue` and `disable_background_tasks=` but no `automation_profile` — becomes `automation=AutomationContext(idle_timeout=..., disable_background_tasks=...)` with `profile` left `None`.
- `fsm/runners.py` `DefaultActionRunner.run()` — the already-resolved context forwards directly as `automation=automation` instead of being decomposed back into the legacy trio.

### Decision Rules
- Same shim pattern as ENH-3095/ENH-3096: legacy `automation_profile`/`disable_background_tasks`/`idle_timeout` keywords still work, constructing an `AutomationContext` internally; explicit `automation` wins when both given; deprecation warning logged.
- **Each layer forwards only `automation=`, never `automation=` plus a legacy kwarg.** This is the likeliest implementation bug in the issue, because the call chain now has *three* nested `resolve_automation()` points: `issue_manager.run_claude_command()` (new) → `subprocess_utils.run_claude_command()` (new) → `HostRunner.build_streaming()` (`host_runner.py:362`, landed in ENH-3095). `resolve_automation()` treats "explicit context **and** any legacy kwarg" as a *conflict*, not merely deprecated use, and emits a `DeprecationWarning` (`host_runner.py:1918-1927`). So a wrapper that resolves its own inputs into a context and then forwards `automation=ctx, automation_profile="ll-auto"` down one level makes the inner layer warn on **every** `ll-auto` round — a log flood with no real conflict behind it. Resolve once per layer, drop the legacy kwargs at the forward.
- **Explicit `automation=` discards a legacy `idle_timeout` — and at this layer
  that silently disables idle detection.** `resolve_automation()` folds a legacy
  `idle_timeout` into its `legacy_used` conflict check and then *drops* it when an
  explicit context wins; it is never merged field-wise into the returned context
  (`host_runner.py:1917-1930`, and the shim's own docstring says so). At the
  `build_streaming()` boundary that discard is inert, because `idle_timeout` is
  never read there (`AutomationContext` docstring, `host_runner.py:182-185`). At
  **`run_claude_command()` it is not inert**: `idle_timeout` gates the selector
  loop's idle kill at `subprocess_utils.py:513`. So after this issue,
  `run_claude_command(automation=AutomationContext(profile="ll-auto"), idle_timeout=1800)`
  runs with **idle detection off**, emitting only a `DeprecationWarning`. That is
  exactly the shape of a half-migrated caller — context built for the profile,
  idle left behind as a kwarg.
  **Rule: a caller that passes `automation=` must carry `idle_timeout` inside the
  context. It is not merged from the legacy kwarg, and no site may pass both.**
  Do not add a field-wise merge to the shim to paper over this — that would fork
  the "explicit wins" rule ENH-3096 deliberately made uniform across both
  boundaries. Pin the discard with a test instead (AC 12) so it is a documented
  contract rather than a latent hang-detector outage.
- **Use `resolve_automation()` to get the "omit when all-default" conditional —
  do not hand-roll an `if`.** Two sites (`fsm/executor.py`'s baseline arm,
  `worker_pool.py`'s `_run_claude_base` forward) construct a context from values
  that are commonly all-default, where unconditional construction would turn
  today's `automation=None` into an all-default `AutomationContext`. Calling
  `resolve_automation(None, None, disable_background_tasks, idle_timeout,
  caller=...)` returns `None` in exactly that case, so the conditional falls out
  for free and both sites obey the "call the shim, don't reimplement the fold"
  rule below. A hand-written `if idle_timeout:` quietly violates it and produces
  two different rules for one hazard (see AC 3 and AC 11).
  For the record the all-default context is *behaviorally* benign —
  `_apply_automation_env()` and the FEAT-3078 background-task gate
  (`host_runner.py:412-419`) both key off `profile is not None` — so this is a
  uniformity rule, not a correctness one. It is still the rule.
- `AutomationContext.idle_timeout` is `float | None` (ENH-3095) versus the `int = 0` parameters across this issue's call sites, so the `0`-vs-`None` distinction needs a decision. **Do not fork or reimplement `resolve_automation()` to preserve it.** The shim's `legacy_used = automation_profile is not None or disable_background_tasks or bool(idle_timeout)` (`host_runner.py:1917`) deliberately treats a bare `idle_timeout=0` as "not supplied" and returns `None` rather than `AutomationContext(idle_timeout=0)`. That is already correct for every consumer in scope, because none of them distinguishes the two: `subprocess_utils.py:513` reads `if idle_timeout and (now - last_output_time) > idle_timeout`, and `fsm/runners.py:191` reads `int(automation.idle_timeout or 0)` — `0` and `None` are both falsy and both mean "idle detection disabled". Call the shim as-is. (An earlier revision of this issue carried a rule requiring `0` be preserved as distinct from `None`; following it literally would mean forking the shared shim to no behavioral end. It is superseded by this bullet.)

- **Nit, non-blocking:** `resolve_automation()` warns with `stacklevel=3`
  (`host_runner.py:1918-1927`), tuned when there were at most two resolve points.
  With three nested points the reported source line lands on an intermediate
  little-loops frame rather than the originating caller. Nothing breaks — the
  tests match on the `caller=` string, not the location — so do not adjust it
  here; noted only so a future reader doesn't mistake it for a regression.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.issues/enhancements/P3-ENH-3094-collapse-per-call-automation-kwargs-into-automationcontext.md` | Parent issue — full motivation, Program Design, decision rationale |
| `.issues/enhancements/P3-ENH-3095-add-automationcontext-dataclass-and-thread-through-hostrunner-build-streaming.md` | Dependency — defines `AutomationContext` |
| `.issues/bugs/P3-BUG-3093-three-ll-auto-subprocesses-declare-themselves-non-automation.md` | `status: done` — its asymmetry is **closed**; the former carve-out in Scope Boundaries is superseded, see the note there |

## Verification Notes

**2026-08-10** (`/ll:verify-issues`): Verified 2026-08-10: AutomationContext
still absent (ENH-3095 not landed) — dependency correct. Call-site line
numbers drifted ~20-60 lines (e.g. fsm/executor.py call now ~2801 not
2771-2774; worker_pool.py forward now ~929-936 not 924-934;
subprocess_utils.run_claude_command now at :343 not :320-341).
Structure/shape of the refactor is unchanged.

**2026-08-19** (`/ll:verify-issues`): Still `OUTDATED` — drift has grown
further at the two fastest-moving sites, structure otherwise unchanged:

- `subprocess_utils.run_claude_command()` def now `:343-362+` (was
  `:320-341`).
- `issue_manager.py` wrapper `run_claude_command()` still accurate at
  `:139-152` — unchanged since original filing.
- `issue_manager.run_with_continuation()` now `:260-...` (was `:252-269`).
- `runner_spec.py` `automation_profile` read now `:127` (was `:128`,
  negligible); forwarding sites now `:153,186,196` (was `:145,176,182`).
- `fsm/executor.py` baseline arm: def `_run_baseline_arm` now at `:3175`,
  the `run_claude_command()` call now at `:3215-3221` — was `:2771-2774`
  at filing, `~2801` at the last verify pass; drift has grown by ~400 more
  lines since then and is trending upward each pass, not stabilizing.
- `worker_pool.py` `_run_claude_base` forward now `:940-949` — was
  `:924-934` at filing, `~929-936` at the last verify pass; same
  still-growing pattern.
- `docs/reference/API.md` `issue_manager.run_claude_command()` mirror now
  at `:2856-2890` (was `:2626-2655`).
- `BUG-3112` (`blocked_by`) is now `status: done` — satisfied, informational
  only, does not change the remaining `blocked_by: ENH-3095` (still open).
- Same missing-param gap as ENH-3096: neither issue mentions
  `disable_background_tasks`, corroborated by ENH-3095's own Codebase
  Research Findings flagging this exact sibling gap. Does not conflict with
  the proposed collapse — the param carries through unchanged.

**Verdict persisted 2026-08-19:** the pass above ran without `--check`, which
is the mode that writes `verify_verdict:` to frontmatter, so the field was
left at its stale `VALID`. Applied the documented `OUTDATED → NON_VALID`
mapping (`commands/verify-issues.md:265-289`) by hand — the verification did
run and did return `OUTDATED`; only the persist step was skipped by mode.
Re-verify with `--check` after ENH-3095 lands.

**2026-08-19** (pre-implementation review): re-verified every claim against
`main` and applied seven corrections — see § Program Design → Codebase Research
Findings (2026-08-19) for the evidence. Summary of what changed in this file:

1. `Signatures` rewritten as a delta; the previous "New" signature deleted the
   legacy kwargs, directly contradicting AC 4 and the Decision Rules.
2. The `0`-vs-`None` Decision Rule was unsatisfiable via the shim this issue
   also mandates calling; replaced with an explicit "call the shim as-is, and
   here is why that's correct" ruling.
3. Added the forward-only-`automation=` Decision Rule (three nested
   `resolve_automation()` points now exist; forwarding both triggers a
   spurious `DeprecationWarning` per `ll-auto` round).
4. BUG-3093 carve-out marked superseded — that bug is `done` and the
   asymmetry it described is closed.
5. Five previously-unlisted in-`issue_manager.py` call sites added to scope.
6. Stale line numbers removed from `Program Design → Call Path` (they
   contradicted Files to Modify); `test_worker_pool.py:2833` corrected to
   `:2902-2914`.
7. Deleted the dead "Missing criterion for the sixth call site" block under
   Acceptance Criteria — AC 7 already was that criterion.

New ACs 9–11 and a new `Tests (new, from the 2026-08-19 review pass)` section
were added. Frontmatter `verify_verdict` left at `NON_VALID` — re-run
`/ll:verify-issues --check` to repersist now that ENH-3095/ENH-3096 have landed
and the drift is corrected.

**2026-08-19** (`/ll:verify-issues --check`): every claim about current state
re-verified against `main` by direct read and **all hold** — the full line-number
set in § Program Design → Codebase Research Findings (2026-08-20) is accurate
(`subprocess_utils.py:343-366`/`:350`/`:358`/`:359`/`:437-447`/`:513`/`:522`;
`issue_manager.py:139-154`/`:213-226`/`:260-279`/`:355`/`:537` and all five call
sites `:853,:927,:1128,:1259,:1462`, each confirmed passing
`automation_profile="ll-auto"`; `runner_spec.py:127`/`:131`/`:153-154`/
`:186-187`/`:194-198`; `fsm/executor.py:3178-3243`/`:3199`/`:3218-3225`;
`worker_pool.py:940-952`; `fsm/runners.py:81`/`:158`/`:177-183`/`:184-186`/
`:187-191`/`:234-252`; `host_runner.py:172-190`/`:1886-1934`/`:1917`/`:1918-1927`;
`docs/reference/API.md:2853`/`:6072`/`:6098`/`:11653`;
`test_worker_pool.py:2902-2914`). No required decision rules are active.

Verdict was `PROPOSAL_UNSOUND` on a single finding — the proposal's test-impact
accounting was incomplete — and the corrections were applied in the same pass:

1. Four previously-unlisted test assertions that the Proposed Solution breaks as
   written, added to § Tests (wiring gaps) with the 2026-08-19 heading. Three
   (`test_issue_manager.py:2271,:2304,:4901`) break from this issue's **own**
   AC 10, and `:2271` is a `KeyError`, not a value mismatch; the fourth
   (`test_fsm_runners.py:629`) sits outside `TestActionRunnerAutomationShim` and
   so escaped the wiring pass's `:671-726` enumeration.
2. AC 10 extended to require those guards be *retargeted* rather than deleted —
   they encode the BUG-3093/FEAT-3078 guarantees, which must survive a pure
   parameter-shape refactor.
3. `subprocess_utils.run_claude_command()`'s parameter count corrected from 18
   to 22 in Current Behavior and § Program Design → Signatures (incidental; the
   signature delta never depended on the count).

`verify_verdict` set to `VALID` — it reflects the file **after** these
corrections, since the sole defect the pass found is the one it repaired. A
future pass that changes nothing should reproduce `VALID`.

**2026-08-20** (pre-implementation review, fifth round): all line numbers in
§ Program Design → Codebase Research Findings re-verified against `main` by
direct read and **all still hold**. Six corrections applied — none invalidate
the approach, all sharpen under-specified instructions or close a gap:

1. **New behavior hazard documented** (Behavior Parity last row, new Decision
   Rule, AC 12): `resolve_automation()` discards a legacy `idle_timeout` when an
   explicit `automation=` also arrives. Inert at `build_streaming()` (idle is
   never read there), but **not** inert at `run_claude_command()`, where it gates
   the selector-loop idle kill at `subprocess_utils.py:513` — the combination
   silently disables idle detection. Pinned by test rather than "fixed" by
   forking the shim, which would break ENH-3096's uniform explicit-wins rule.
2. **`fsm/runners.py` dead-local split corrected** (Behavior Parity row 4, AC 7):
   the file said all three decomposed locals survive for the shell branch. Usage
   grep shows only `resolved_idle_timeout` does (`:346-347`, `:374`);
   `resolved_automation_profile` and `resolved_disable_background_tasks` are read
   only at `:246-247` and must be deleted.
3. **Contradictory conditional-construction rules reconciled** (AC 3, AC 11, new
   Decision Rule): AC 11 required a conditional at `fsm/executor.py`'s baseline
   arm while Files to Modify told `worker_pool.py` to construct unconditionally —
   two rules for one hazard. Both now route through `resolve_automation()`, which
   returns `None` for all-default input, supplying the conditional for free.
4. **`runner_spec` dict-key contract specified** (AC 2, AC 13): the automation
   values arrive via untyped `spec.args` lookups with **no in-tree producer** (a
   repo-wide grep for `"automation_profile"` in `scripts/little_loops/` hits only
   the read at `:127`), making it the issue's only externally-facing compat
   surface and the only one no existing test covers. Now specified: add an
   `"automation"` key, keep both legacy keys, fold via
   `resolve_automation(caller="run_skill()")`.
5. **Static gates added to AC 6**: mypy is what catches the `float | None` → `int`
   rebind at `subprocess_utils.py` (correction 1's territory) and ruff F841 is
   what catches correction 2's dead locals — both load-bearing for this change,
   not boilerplate.
6. **Shim-removal follow-up made an AC** (AC 14): § Signatures deferred removal
   to "a follow-up once no in-tree caller uses them", a precondition this issue
   itself satisfies, but no such issue exists and ENH-3094 has only three
   children — so the shim would ship as the permanent shape by default.

`verify_verdict` left at `VALID`; the corrections above are refinements to an
approach that re-verified clean, not defects in it.

## Session Log
- `/ll:confidence-check` - 2026-08-20T15:10:46 - `d1a0a529-4a4a-4956-8bd6-268fc1152f27.jsonl`
- `/ll:confidence-check` - 2026-08-20T14:31:22 - `8f4849c7-f264-45db-90d2-abcbcb8ba804.jsonl`
- `/ll:reconcile-issue` - 2026-08-20T05:03:08 - `1087295a-4b0c-427d-ae4c-467e8ea34d7c.jsonl`
- `/ll:verify-issues` - 2026-08-20T04:57:41 - `1087295a-4b0c-427d-ae4c-467e8ea34d7c.jsonl`
- `/ll:wire-issue` - 2026-08-20T04:38:44 - `4ee98805-cd89-4657-9e66-10a84d755f40.jsonl`
- `/ll:reconcile-issue` - 2026-08-20T04:31:02 - `c922381f-76e0-40bc-8b49-424300556cf1.jsonl`
- `/ll:refine-issue` - 2026-08-20T04:26:31 - `bc783ddd-7686-4216-8c7b-f8960149f7f4.jsonl`
- `/ll:verify-issues` - 2026-08-20T00:59:29 - `e89696fe-140c-45df-a34b-1cf937e9f43c.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:10 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:26:27 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-09T03:26:27 - `39a3fd52-4ea1-4f7e-83e9-1871820dfe65.jsonl`
- `/ll:refine-issue` - 2026-08-07T22:51:22 - `596f76ed-c393-479b-9539-adbce5a6a72b.jsonl`
- `/ll:issue-size-review` - 2026-08-07T22:09:44 - `dec986a1-15de-4376-b5dd-5868a8d3e188.jsonl`

---
id: ENH-3096
type: ENH
title: Thread AutomationContext through ActionRunner.run() and fsm/executor.py
priority: P3
status: open
parent: ENH-3094
blocked_by: []
discovered_date: 2026-08-07
discovered_by: /ll:issue-size-review
labels:
- automation
- fsm
- refactor
- tech-debt
testable: true
decision_needed: false
relates_to:
- FEAT-3078
- FEAT-3033
- ENH-2714
- ENH-3095
verify_verdict: NON_VALID
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3096: Thread AutomationContext through ActionRunner.run() and fsm/executor.py

## Summary

Second of three children decomposed from ENH-3094. This child threads the
`AutomationContext` dataclass (introduced in ENH-3095) through the
`ActionRunner` Protocol boundary in `fsm/runners.py` — `DefaultActionRunner`,
`SimulationActionRunner` — and the `extra_kwargs` assembly in `fsm/executor.py` — and collapses the
largest cluster of hand-written test mocks that currently raise `TypeError`
on any new kwarg.

**ENH-3095 has landed** (commit `c7804788`) — `AutomationContext` is defined in
`host_runner.py` and can be imported; frontmatter `blocked_by` is already
cleared. Can proceed in parallel with ENH-3097
— they touch disjoint files except for a shared edit to `fsm/executor.py`
(different line ranges: this child touches the `extra_kwargs` assembly, now
at `:2229-2267`; ENH-3097 touches the baseline arm's direct call, line range
to be reconfirmed against current `main` when that issue is worked).

## Parent Issue

Decomposed from ENH-3094: Collapse the per-call automation kwargs into a
single AutomationContext dataclass. See that issue for full motivation,
sequencing decision, and Program Design section — this child implements the
`ActionRunner` slice of that design.

## Scope Boundaries

**In scope:** `ActionRunner.run()` Protocol and its `DefaultActionRunner` /
`SimulationActionRunner` implementations; the `extra_kwargs` assembly in
`fsm/executor.py:2229-2267`; the `SimulationActionRunner` `del` no-op list
(`:432-444`); the `docs/reference/API.md` ActionRunner mirror (`:6075-6091`)
and its surrounding kwarg-gating prose (`:6096-6098`); the associated
test-mock signatures.

**Out of scope:** `HostRunner.build_streaming()` (ENH-3095, a dependency);
`run_claude_command()` and its callers, including `fsm/executor.py`'s
baseline-arm direct call at `:2771-2774` (ENH-3097). Because
`run_claude_command()` is out of scope and has **no `automation` parameter
today**, `DefaultActionRunner` must decompose its resolved context back into
legacy kwargs when forwarding — see Call Path.

**This issue grows the `run()` signature; it does not shrink it.** Per AC #4
and the parent's Decision Rules, the legacy kwargs stay as deprecated
pass-throughs, so `automation` is *added* alongside them. The actual
parameter-count reduction is a later cleanup, after ENH-3097 migrates the
remaining callers. Any "New signature" below that appears to drop the legacy
kwargs is wrong — see Signatures.

## Proposed Solution

Add `automation: AutomationContext | None = None` to the `ActionRunner`
Protocol and its two implementations, resolving it against the existing
`automation_profile` / `disable_background_tasks` / `idle_timeout` kwargs
through a shim mirroring ENH-3095's `_resolve_automation()`. Collapse the
`extra_kwargs` dict assembly in `fsm/executor.py:2229-2267` into constructing
one `AutomationContext` and passing it as `automation=`. Keep the legacy
kwargs as deprecated pass-throughs per the parent's Decision Rules (explicit
`automation` context wins over legacy kwargs; deprecation warning logged).

### Codebase Research Findings (from parent)

- **`SimulationActionRunner` `del (...)` list** (`fsm/runners.py:432-444`):
  now covers all three of `idle_timeout`, `automation_profile`, and
  `disable_background_tasks`. The historical asymmetry described in earlier
  drafts of this issue (`idle_timeout` deleted, `automation_profile` omitted)
  **no longer exists** — nothing is left to fix there; the change is purely
  additive (`automation` joins the list).
- **`idle_timeout` never reaches `build_streaming()`**: it is consumed
  entirely in `subprocess_utils.py:478` and the shell/mcp selector loops in
  `fsm/runners.py:311,337` / `fsm/executor.py:2150,2169` — those selector-loop
  consumption sites read the value but are unaffected by this parameter-shape
  change (they read the resolved context instead of the bare kwarg).

### Files to Modify
- `scripts/little_loops/fsm/runners.py` — add `automation: AutomationContext | None
  = None` alongside the existing legacy kwargs in the `ActionRunner` Protocol
  (`:39-56`) and 2 implementations (`DefaultActionRunner.run():109-125`,
  `SimulationActionRunner.run():394-411`); add `automation` to the
  `SimulationActionRunner` `del` no-op list (`:432-444`) **and** to its
  docstring `Args:` list (`:412-426`, which also still omits `idle_timeout`)
- `scripts/little_loops/host_runner.py:1886-1920` — extend `_resolve_automation()`
  with the fourth `idle_timeout` input and a `caller` parameter for the warning
  message; promote the name to `resolve_automation` if making it a cross-module
  helper. **This file was previously missing from this list** even though the
  recommended shim approach edits it — see Program Design § The Shim.
- `scripts/little_loops/fsm/executor.py` — collapse `extra_kwargs` assembly
  (`:2229-2267`) into constructing one `AutomationContext`
- `docs/reference/API.md:6075-6091` — `ActionRunner` Protocol mirror (code
  block), **plus** the kwarg-gating prose at `:6096-6098`, which describes
  per-knob gating that this change replaces with a single `automation` gate.
  While editing the mirror, also add the missing `timeout_kill_grace_seconds`
  parameter (pre-existing drift, cheap to fix in the same edit).
- `docs/development/TESTING.md:635-643` — `MockActionRunner` example, already
  drifted (predates `automation_profile`/`disable_background_tasks`/
  `idle_timeout`). Fold it in here rather than let it drift further, since
  this issue changes the mock contract.

### Tests
- `scripts/tests/test_fsm_executor.py:35-118` — `MockActionRunner` (primary
  mock, explicit `run()` signature)
- `scripts/tests/test_fsm_executor.py:10946-10985` — `_ContinuityRunner`
  (inline fake, includes `automation_profile`, no `idle_timeout`)
- `scripts/tests/test_fsm_executor.py:11184-11228` — `_TamperingActionRunner`
  (inline fake, includes `automation_profile`)
- `scripts/tests/test_fsm_executor.py` — ~11 more inline fakes with explicit
  `run()` signatures and no `**kwargs`: `FailingRunner:2518`,
  `ShutdownAfterFirstActionRunner:3351`, `TimeoutCapturingRunner:5261`,
  `CapturingRunner:6373`, and others. **These are safe only when *nothing*
  resolves.** The collapse replaces three independent per-knob gates with one
  combined gate (see Decision Rules), so any fake driven through the executor
  with a pruning profile, `disable_background_tasks`, or a non-zero
  `idle_timeout` in play now receives `automation=` where it previously
  received the individual legacy kwarg.

  **Fix these mechanically, do not audit them individually.** The obvious
  approach — check each fake against the states its test configures and add
  `automation` only where needed — is expensive and silently wrong the next
  time a knob is added. There are 112 `def run(` definitions across 19 test
  files; `test_fsm_executor.py` alone already carries ~17 that accept
  `**kwargs`. **Give every `ActionRunner` fake `**kwargs: Any`.** It is
  mechanical, permanently retires this class of churn, and makes both ENH-3097
  and the eventual legacy-kwarg removal nearly free. This is safe precisely
  because the compat surface is in-tree (see Decision Rules § blast radius).

  **One deliberate exception:** the old-runner double in
  `test_feat3033_idle_timeout.py:390-467` must keep its explicit, `**kwargs`-free
  signature — proving that the kwarg gate *omits* the parameter is that test's
  entire purpose, and `**kwargs` would make it vacuously pass.
- `scripts/tests/test_fsm_persistence.py:766-792` — `MockActionRunner` (stops
  at `model`; no `working_dir`/`automation_profile`/`idle_timeout` today)
- `scripts/tests/test_usage_journal.py:17-52` — `MockActionRunner` (stops at
  `model`; no automation kwargs today)
- `scripts/tests/test_fsm_runners.py:435-600` — patches `run_claude_command`,
  captures kwargs at `:485`
- `scripts/tests/test_feat3033_idle_timeout.py:390-467` — kwarg-gating
  compatibility template; imports `MockActionRunner` from `test_fsm_executor.py:28`;
  `test_idle_disabled_omits_kwarg_for_old_runners` proves the backward-compat
  contract for `automation=`
- `scripts/tests/test_bug3032_wall_clock_cap.py:24,39` — imports
  `MockActionRunner` from `test_fsm_executor`, drives it with `idle_timeout=60`;
  update in lockstep with the shared mock
- `scripts/tests/test_learning_state.py:46` — `_MockRunner.run()` explicit, no
  `**kwargs`; safe only if `automation=` stays kwarg-gated

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_runners.py:606-626` — `test_disable_background_tasks_kwarg_forwarded`,
  calls `runner.run(..., automation_profile="ll-auto", disable_background_tasks=True)` directly on
  `DefaultActionRunner` with both legacy kwargs together, past the issue's already-cited `435-600`
  range; existing test to update or confirm passes unchanged through the new shim [Agent 1/3 finding]
- `scripts/tests/test_feat3033_idle_timeout.py:73,103,135,167,211,262` — bare `idle_timeout=N`
  calls directly on the real `DefaultActionRunner` (legacy-kwarg-alone shape), outside the issue's
  cited `390-467` template range; verify unaffected under kwarg gating [Agent 3 finding]
- `scripts/tests/test_host_guard.py:582-590` — instantiates `DefaultActionRunner` and calls
  `.run("sleep 0.05; echo hi", timeout=10, is_slash_command=False)` / `.run("echo hi", ...)` with no
  automation kwargs; real caller not previously in this list, verify unaffected [Agent 1/3 finding]
- `scripts/tests/test_cli_loop_testing.py` — exercises `cli/loop/testing.py`'s `cmd_test()`
  (see Dependent Files below), which calls `SimulationActionRunner.run()`/`DefaultActionRunner.run()`
  with no automation kwargs; verify unaffected [Agent 3 finding]
- New test class mirroring `TestAutomationContext` (`test_host_runner.py:1587-1662`) for the
  `ActionRunner`-side shim — frozen-ness of `AutomationContext` is already covered by ENH-3095 and
  needn't be re-tested; focus on legacy-alone-silent, explicit-wins-and-warns (both `profile` and
  `disable_background_tasks` fields), and empty-context-equivalent-to-`None`, applied against
  `DefaultActionRunner.run()`/`SimulationActionRunner.run()` instead of `HostRunner.build_streaming()`
  [Agent 3 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/extension.py:28,87-88` — imports `ActionRunner` only as a `TYPE_CHECKING`
  return-type annotation on `ActionProviderExtension.provided_actions() -> dict[str, ActionRunner]`;
  no direct `run()` call site, informational only [Agent 1 finding]
- `scripts/little_loops/fsm/__init__.py:108,173` — re-exports `ActionRunner`; the name is unaffected
  by the parameter collapse, no edit needed but confirm the re-export still resolves [Agent 1 finding]
- `scripts/little_loops/cli/loop/testing.py:72-87` (`cmd_test()`) — instantiates
  `SimulationActionRunner()`/`DefaultActionRunner()` and calls
  `.run(action, timeout=..., is_slash_command=...)` with no automation kwargs; must keep working
  unmodified under kwarg-gating [Agent 1 finding]
- `scripts/little_loops/runner_spec.py:127-136` — extracts `automation_profile`,
  `disable_background_tasks`, `timeout_kill_grace_seconds` from an args dict for its own
  `run_claude_command()` call path, parallel to (not through) `ActionRunner.run()`; out of this
  issue's scope but shares the same legacy-kwarg names — confirm no accidental coupling
  [Agent 1 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **Line numbers corrected against current `main`** (ENH-3095 has landed —
  commit `c7804788`): `ActionRunner` Protocol `run()` now
  `fsm/runners.py:38-56` (signature `:38-53`, full incl. docstring `:38-83`);
  `DefaultActionRunner.run()` now `fsm/runners.py:109-...` (`run_claude_command()`
  forwarding call at `:200-218`; direct `idle_timeout` selector-loop reads now
  at `:311` and `:337`, not `:287,313`); `SimulationActionRunner.run()` now
  `fsm/runners.py:394-410` (signature) with its `del` no-op list now at
  `:432-444`; `extra_kwargs` assembly in `fsm/executor.py` now `:2229-2267`
  (call-site `**extra_kwargs` spread at `:2278-2288`); `docs/reference/API.md`
  ActionRunner Protocol mirror now `:6072-6100` (code block `:6075-6091`).
- **The shim pattern to mirror now exists and is concrete**: ENH-3095 landed
  `AutomationContext` (`host_runner.py:171-190`, `frozen=True`, fields
  `profile: str | None`, `idle_timeout: float | None`, `disable_background_tasks:
  bool = False`) plus a module-level `_resolve_automation(automation,
  automation_profile, disable_background_tasks) -> AutomationContext | None`
  shim (`host_runner.py:1886-1920`), called identically at 6 of the 8 concrete
  `build_streaming()` implementations (e.g. `host_runner.py:362`) — the
  remaining two, `OpenCodeRunner` and `PiRunner`, are unwired stubs that
  unconditionally raise `HostNotConfigured` and never reach the shim. Its
  contract: explicit `automation=` always wins; a `DeprecationWarning`
  (`stacklevel=3`) fires only when `automation=` AND a legacy kwarg are both
  supplied; bare legacy-kwarg-only use is silent by design (every in-tree
  caller still uses legacy kwargs until ENH-3097 migrates them — warning
  there would flood every `ll-auto` run); `automation=None` with no legacy
  kwargs returns `None`, preserving today's opt-out path. This is the shape
  this issue's `ActionRunner`-side shim should mirror — same helper-function
  structure, same precedence rule, same silent-legacy
  behavior — not just "a shim pattern" in the abstract. **But the signatures
  are not identical**: `_resolve_automation()` takes three inputs and has no
  `idle_timeout` parameter, because `build_streaming()` never receives one.
  The `ActionRunner` boundary needs a fourth input — see Program Design §
  The Shim for the resolution (recommendation: extend the shared helper with a
  defaulted `idle_timeout` rather than write a near-copy in `fsm/runners.py`).
- **`AutomationContext.idle_timeout` is `float | None`**, already reserved
  for this issue's use (its own docstring at `host_runner.py:183-186` names
  ENH-3096 as the second consumer) — but `ActionRunner.run()`'s current
  `idle_timeout: int = 0` is a different shape (non-Optional int, `0` means
  disabled). The shim must decide how `0` (today's default/"disabled") maps
  onto `float | None` (`None` means unset) without conflating the two — see
  Program Design § The Shim for the chosen mapping.
- **Two new parameters have joined the signature since this issue was
  written**: `disable_background_tasks: bool = False` (FEAT-3078) and
  `timeout_kill_grace_seconds: float = 0.0` (ENH-3130) now sit in all three
  `run()` signatures, between `automation_profile` and `idle_timeout`.
  `disable_background_tasks` is also a field on `AutomationContext` already
  (see above) and should fold into the same collapsed `automation=`
  parameter alongside `profile`/`idle_timeout`; `timeout_kill_grace_seconds`
  has no `AutomationContext` field and stays a separate parameter — out of
  this issue's collapse.
- **A second, out-of-scope kwarg-gated dict exists at `executor.py:2203-2222`**
  (the `contributed`-action branch's `_contrib_extra` dict, `idle_timeout`-only,
  independently maintained from the `extra_kwargs` block this issue targets)
  — confirms the issue's existing "do not fold it into this change" scope note
  against current line numbers.

_Wiring pass added by `/ll:wire-issue`:_
- **`fsm/executor.py:2211-2222`'s `_contrib_extra` block is confirmed unaffected**:
  it is only exercised by `scripts/tests/test_fsm_executor.py` and, being
  structurally independent from `extra_kwargs`, needs no edit for this issue
  [Agent 2 finding].
- **`docs/development/TESTING.md`'s `MockActionRunner` example (`:635-643`)
  already predates `automation_profile`/`disable_background_tasks`/
  `idle_timeout` entirely** — pre-existing drift, not caused by this issue; no
  forced edit, flagged for awareness only [Agent 2 finding].
- **No JSON schema, `--format json` output, or logging inspects `extra_kwargs`
  directly** — it is an internal local dict, never serialized; no gate-consumer
  coupling found [Agent 2 finding].
- **No integration/e2e test currently exercises the full `extra_kwargs` →
  `ActionRunner.run()` path** (`test_ll_loop_execution.py`,
  `test_builtin_loops.py`, `integration/test_loop_run_e2e.py` all have zero
  matches for `automation_profile`/`idle_timeout`/`AutomationContext`) — an
  optional coverage gap, not a required addition, since unit-level coverage
  via `MockActionRunner` and `test_feat3033_idle_timeout.py` already exercises
  the contract [Agent 3 finding].

## Acceptance Criteria

1. `ActionRunner.run()` Protocol, `DefaultActionRunner`, and
   `SimulationActionRunner` accept `automation: AutomationContext | None = None`
   **alongside** the existing `automation_profile` / `disable_background_tasks`
   / `idle_timeout` kwargs (which remain, deprecated — see AC #4).
   `timeout_kill_grace_seconds` is untouched.
2. The `extra_kwargs` assembly in `fsm/executor.py:2229-2267` builds one
   `AutomationContext` instead of a per-knob dict, and the BUG-3032
   `_wall_fallback` computation still derives from the resolved idle value.
3. `SimulationActionRunner`'s `del` no-op list (`fsm/runners.py:432-444`) gains
   `automation` and retains the legacy names it still declares for Protocol
   conformance. (No asymmetry fix is involved — the list already covers all
   three legacy names.)
4. The `automation_profile` / `disable_background_tasks` / `idle_timeout`
   keywords still work standalone and silently, constructing an
   `AutomationContext` internally per the ENH-3095 shim pattern; supplying one
   alongside an explicit `automation=` emits a `DeprecationWarning` and the
   explicit context wins.
5. `DefaultActionRunner` still calls `run_claude_command()` successfully:
   because that function has no `automation` parameter until ENH-3097, the
   resolved context is decomposed back into
   `automation_profile=` / `disable_background_tasks=` / `idle_timeout=` at the
   forwarding call (`fsm/runners.py:200-218`).
6. A new test class for the `ActionRunner`-side shim exists, mirroring
   `TestAutomationContext` (`test_host_runner.py:1587-1662`): legacy-alone is
   silent, explicit-wins-and-warns for each legacy field, and an empty context
   is equivalent to `None`. Frozen-ness is already covered by ENH-3095 and is
   not re-tested. It additionally asserts (a) the `DeprecationWarning` names
   `ActionRunner.run()`, not `build_streaming()`, and (b) that
   `run(..., automation=AutomationContext(profile="x"), idle_timeout=60)` emits
   the `DeprecationWarning` and resolves to a context whose `idle_timeout` is
   `None` — the legacy value is discarded, per the decision in Program Design
   § The Shim.
7. The shared shim carries a `caller` parameter so its `DeprecationWarning`
   names the invoking function; the 7 existing `build_streaming()` call sites
   keep their current message via the default.
8. `docs/reference/API.md` ActionRunner Protocol mirror (`:6075-6091`) and its
   kwarg-gating prose (`:6096-6098`) updated; the mirror also gains the
   missing `timeout_kill_grace_seconds`. `SimulationActionRunner.run()`'s own
   docstring `Args:` list (`fsm/runners.py:412-426`) gains `automation` — and
   `idle_timeout`, which it already omits today.
9. `python -m pytest scripts/tests/` passes, as do `python -m mypy
   scripts/little_loops/` and `ruff check scripts/`. The type gate is not
   optional here: this change adds a `Protocol` parameter, two implementations,
   and a cross-module import — exactly the shape mypy catches and pytest does
   not.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **Current full `run()` signature** (`fsm/runners.py:38-53`, identical shape
  in `ActionRunner` Protocol, `DefaultActionRunner`, and
  `SimulationActionRunner`) now includes two params added since this issue
  was drafted:
  `run(self, action: str, timeout: int, is_slash_command: bool, on_output_line: Callable[[str], None] | None = None, agent: str | None = None, tools: list[str] | None = None, on_usage: UsageCallback | None = None, on_usage_detailed: DetailedUsageCallback | None = None, model: str | None = None, working_dir: Path | None = None, automation_profile: str | None = None, disable_background_tasks: bool = False, idle_timeout: int = 0, timeout_kill_grace_seconds: float = 0.0) -> ActionResult`
  `automation_profile`, `disable_background_tasks`, and `idle_timeout` are the
  three knobs that fold into `automation: AutomationContext | None = None`;
  `timeout_kill_grace_seconds` has no `AutomationContext` field and is
  unaffected. **Note:** folding here means "carried by the context", not
  "removed from the signature" — the three legacy kwargs remain as deprecated
  pass-throughs (AC #4), matching what ENH-3095 landed at
  `build_streaming()`. The authoritative Old/New signatures are in Program
  Design § Signatures; any earlier draft signature omitting the legacy kwargs
  is superseded by it.
- **The `_resolve_automation()` shim (`host_runner.py:1886-1920`) is the
  reference implementation for this issue's own shim**, though not a
  drop-in one: same precedence
  (explicit `automation=` wins), same `DeprecationWarning` conditions (fires
  only on simultaneous `automation=` + legacy kwarg; `stacklevel=3` since the
  shim is one frame below the public `run()` call), same silent-legacy-alone
  behavior, same `None`-when-nothing-supplied return — but a different
  parameter list (three inputs there, four needed here; see § The Shim).
  `TestAutomationContext`
  in `scripts/tests/test_host_runner.py:1587-1661` is the corresponding test
  template (frozen-ness, defaults, legacy-alone-silent, explicit-wins-and-warns,
  empty-context-equivalent-to-None) this issue's own new test class for the
  `ActionRunner` shim should follow.
- **`SimulationActionRunner`'s current `del` no-op list** (`fsm/runners.py:432-444`)
  already includes `idle_timeout`, `automation_profile`, and
  `disable_background_tasks` as three separate names — confirms the earlier
  Verification Notes finding that the historical asymmetry (AC #3) no longer
  exists. Since the legacy kwargs remain declared, the three `del` entries
  stay; the only change is adding `automation` to the list.

### Types
- Imports `AutomationContext` from `host_runner.py` (defined by ENH-3095,
  landed in commit `c7804788` — this issue's `blocked_by: [ENH-3095]` is now
  resolved).

### Signatures

**Old** — `ActionRunner.run()` Protocol (`fsm/runners.py:39-56`),
`DefaultActionRunner.run()` (`:109-125`), `SimulationActionRunner.run()`
(`:394-411`), all three identical as verified against current `main`:

`run(self, action: str, timeout: int, is_slash_command: bool, on_output_line: Callable[[str], None] | None = None, agent: str | None = None, tools: list[str] | None = None, on_usage: UsageCallback | None = None, on_usage_detailed: DetailedUsageCallback | None = None, model: str | None = None, working_dir: Path | None = None, automation_profile: str | None = None, disable_background_tasks: bool = False, idle_timeout: int = 0, timeout_kill_grace_seconds: float = 0.0) -> ActionResult`

**New** — additive. The three legacy automation kwargs **remain** (deprecated
pass-throughs, AC #4), `automation` is inserted before them, and
`timeout_kill_grace_seconds` is untouched:

`run(self, action: str, timeout: int, is_slash_command: bool, on_output_line: Callable[[str], None] | None = None, agent: str | None = None, tools: list[str] | None = None, on_usage: UsageCallback | None = None, on_usage_detailed: DetailedUsageCallback | None = None, model: str | None = None, working_dir: Path | None = None, automation: AutomationContext | None = None, automation_profile: str | None = None, disable_background_tasks: bool = False, idle_timeout: int = 0, timeout_kill_grace_seconds: float = 0.0) -> ActionResult`

This is the same shape ENH-3095 landed at `HostRunner.build_streaming()` —
which likewise kept `automation_profile`/`disable_background_tasks` next to
the new `automation`. Removing the legacy kwargs is a separate later cleanup,
not this issue.

### The Shim

`host_runner._resolve_automation()` takes **three** inputs (`automation`,
`automation_profile`, `disable_background_tasks`) — it has no `idle_timeout`
parameter, because `build_streaming()` never sees one. The `ActionRunner`
boundary needs a **fourth**. So this is *not* a literal reuse of that helper;
earlier drafts of this issue calling the shapes "identical" were wrong.

**Recommended:** extend the shared `_resolve_automation()` with
`idle_timeout: float | None = None` (keyword-only, defaulted) so there is one
contract and one `DeprecationWarning` site, rather than a second near-copy in
`fsm/runners.py`. Verify the existing 7 `build_streaming()` call sites are
unaffected by the added default.

Three mechanics of that reuse, verified against current `main`:

- **The warning message is hardcoded to the wrong function.**
  `host_runner.py:1908-1911` reads *"`build_streaming()` received both
  `automation=` and a legacy …"*. Called from `ActionRunner.run()`, that names
  a function the caller never invoked. Add a `caller: str = "build_streaming()"`
  parameter and interpolate it, so the `ActionRunner` site passes
  `caller="ActionRunner.run()"`. Note that
  `test_host_runner.py:1616,1628` match on the loose pattern `"automation"`, so
  existing tests won't catch the regression — the new test class must assert the
  caller name.
- **`stacklevel=3` stays correct at the new site.** The depth is identical
  (`_resolve_automation` → `run()` → caller vs.
  `_resolve_automation` → `build_streaming()` → caller), so the warning still
  points at user code. Do not adjust it.
- **No circular-import risk.** `fsm/runners.py:22` already imports from
  `little_loops.host_runner` (`project_child_env`), so importing
  `AutomationContext` and the shim adds no new edge. `_resolve_automation` is
  module-private, though: rename it to `resolve_automation` when promoting it to
  a cross-module helper (preferred), or leave the private name and record the
  deliberate cross-module private import in a comment.

**Hazard: "explicit wins" silently discards a legacy `idle_timeout`.** Under
the ENH-3095 contract, `automation=AutomationContext(profile="x")` supplied
alongside legacy `idle_timeout=60` warns, and the context wins — so the 60s
idle value is dropped. For `profile`/`disable_background_tasks` that is
harmless (both are prompt-mode-only knobs). `idle_timeout` is different: it is
the only one of the three that drives the **shell** branch's selector loops
(`runners.py:311,337`), so dropping it silently disables hang detection on a
live shell state. The executor never triggers this (it builds a single
context), but any direct `run()` caller can.

**Decided (2026-08-19): keep the uniform rule — explicit context wins wholesale,
the legacy `idle_timeout` is discarded, and the `DeprecationWarning` is the
caller's signal.** No special-casing. Rationale: one precedence rule across both
boundaries is worth more than rescuing a caller who supplied contradictory
inputs, and a per-field fallback would mean `automation=` no longer fully
determines the resolved context — a subtler trap than the drop it avoids, and a
divergence from what ENH-3095 already landed at `build_streaming()`.

Implementation consequences:

- The shim's `idle_timeout` input participates in `legacy_used` detection (so
  the conflict warning fires) but is **not** merged into an explicit context.
- Document the drop in the shim docstring and in the `API.md` kwarg-gating prose
  (AC #8) — this is intended behavior, not an oversight, and must read that way
  to the next person.
- Pin it with a test asserting that
  `run(..., automation=AutomationContext(profile="x"), idle_timeout=60)` warns
  **and** resolves to `idle_timeout is None` (AC #6).

**Type mapping.** `AutomationContext.idle_timeout` is `float | None`
(`host_runner.py:189`) whereas `ActionRunner.run()`'s `idle_timeout: int = 0`
uses `0` as "disabled". The shim must not conflate `0` with `None`:

- For `legacy_used` detection, treat `idle_timeout=0` as **not supplied** (it
  is the existing default; treating it as supplied would make every call
  legacy-using and defeat the `None` opt-out path).
- When constructing from legacy kwargs, map a non-zero `int` to `float`;
  leave `None` for the unset case.
- Consumers that need the old `int`-ish semantics read
  `automation.idle_timeout or 0` — see Call Path.

### Call Path
- `fsm/executor.py:2229-2267` `extra_kwargs` assembly (today builds a kwarg-gated dict: `working_dir` if `self.working_dir is not None`; `automation_profile` if `action_mode == "prompt"` and a resolved, enabled pruning-profile config exists; `disable_background_tasks` if prompt-mode and `orchestration.disable_background_tasks`; `idle_timeout` if the resolved value is truthy) collapses into constructing one `AutomationContext(profile=..., disable_background_tasks=..., idle_timeout=...)` and passing it as `automation=` — kept kwarg-gated (only added to `extra_kwargs` when the context is non-empty) so implementations without an `automation` parameter still work, per the existing pattern's own inline comments at `:2226-2228`, `:2233-2240`, `:2246-2254`, `:2261-2264`.
- **Keep the `_idle_timeout` local alive.** `fsm/executor.py:2276` derives BUG-3032's `_wall_fallback` (`0 if (action_mode == "prompt" and _idle_timeout) else 3600`) from that local. Folding the value into the context object must not delete the computation — read it back off the context if the local is removed.
- Inside `DefaultActionRunner.run()`: resolve `automation` via the shim first, then **decompose it back into legacy kwargs** at the `run_claude_command(...)` forwarding call (`runners.py:200-218`, currently passing `automation_profile=`/`disable_background_tasks=`/`idle_timeout=`). `run_claude_command()`'s signature (`subprocess_utils.py:343-366`, verified against current `main`) has **no `automation` parameter** — that is ENH-3097's change, not yet landed, so forwarding `automation=automation` would raise `TypeError` on every prompt action. Pass `automation_profile=ctx.profile if ctx else None`, `disable_background_tasks=ctx.disable_background_tasks if ctx else False`, `idle_timeout=int(ctx.idle_timeout or 0) if ctx else 0`. ENH-3097 later replaces this decomposition with a direct `automation=` hand-off.
- `idle_timeout` is additionally read directly by this method's own shell-command selector loops (`runners.py:311` and `:337` — not `:287,313`, which are stale) — those reads become `automation.idle_timeout if automation else 0` (or read a resolved local), since `automation_profile` has no effect on that branch today and none is being added.
- Inside `SimulationActionRunner.run()`: add `automation` to the `del` no-op list at `:432-444`, keeping the legacy names it still declares. This is purely additive — the list already covers `idle_timeout`, `automation_profile`, and `disable_background_tasks`.

### Decision Rules
- Same shim contract as ENH-3095 (see The Shim above for where the shapes differ): the legacy `automation_profile`/`disable_background_tasks`/`idle_timeout` keywords stay as deprecated pass-throughs on `ActionRunner.run()` and both implementations; explicit `automation` wins when both are given; a `DeprecationWarning` fires **only** on the simultaneous-supply conflict, never on bare legacy use.
- **The gate widens — this is the main compatibility risk.** Today there are three independent per-knob gates; collapsed, there is one: `automation` is added to `extra_kwargs` when *any* of profile / `disable_background_tasks` / idle resolves non-default. So a state that configures only `idle_timeout` now sends `automation=` where it previously sent `idle_timeout=`. Old runners are still safe when nothing resolves — that is the contract `test_feat3033_idle_timeout.py:390-467`'s `test_idle_disabled_omits_kwarg_for_old_runners` proves, and it must stay green — but every in-tree fake reached with automation active needs an `automation` parameter or `**kwargs` (see Tests).
- **But the blast radius is narrower than it looks — verified.** Third-party / extension `ActionRunner`s do **not** flow through `extra_kwargs`: `extension.py`'s `ActionProviderExtension.provided_actions() -> dict[str, ActionRunner]` feeds `self._contributed_actions`, which is dispatched by the **contributed** branch and its separate `_contrib_extra` dict (`executor.py:2211-2222`) — explicitly out of scope here. The main `action_runner` has exactly one injection point, `FSMExecutor(action_runner=...)` (`executor.py:187`, whose own docstring says *"for testing"*), used in-tree only by `cli/loop/testing.py:263`. So the widened gate reaches in-tree fakes and direct-API users, **not the plugin ecosystem**. Size the compatibility work accordingly — this is what makes the mechanical `**kwargs` fix in Tests safe rather than reckless.
- The `contributed`-action branch's separate, adjacent kwarg-gating in `fsm/executor.py:2210-2222` (its own `_contrib_extra` dict, `idle_timeout`-only, no `automation_profile` today) is out of this issue's stated scope (`ActionRunner.run()` and `:2229-2267` only) — do not fold it into this change.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.issues/enhancements/P3-ENH-3094-collapse-per-call-automation-kwargs-into-automationcontext.md` | Parent issue — full motivation, Program Design, decision rationale |
| `.issues/enhancements/P3-ENH-3095-add-automationcontext-dataclass-and-thread-through-hostrunner-build-streaming.md` | Dependency — defines `AutomationContext` |
| `scripts/tests/test_feat3033_idle_timeout.py:390-467` | Kwarg-gating compatibility template |
| `scripts/little_loops/host_runner.py:1886-1920` | `_resolve_automation()` — reference shim (three inputs; this issue needs four) |
| `scripts/little_loops/subprocess_utils.py:343-366` | `run_claude_command()` — no `automation` param until ENH-3097; forces the decomposition in Call Path |
| `docs/development/TESTING.md:635-643` | `MockActionRunner` doc example, already drifted; updated by this issue |

## Verification Notes

**2026-08-19** (`/ll:verify-issues`): Structure of the proposed refactor is
still sound; verdict `OUTDATED` on line numbers and one stale claim:

- Corrected line numbers: `ActionRunner.run()` Protocol now `:40-56` (was
  `:39-53`); `DefaultActionRunner.run()` now `:109-125` (was `:98-112`);
  `SimulationActionRunner.run()` now `:394-410` (was `:370-384`);
  `extra_kwargs` assembly in `fsm/executor.py` now `:2229-2267` (was
  `:1886-1910`); `docs/reference/API.md` ActionRunner Protocol mirror now
  `:6072-6091` (was `:5769-5785` — that mirror is also already missing
  `timeout_kill_grace_seconds`, a pre-existing gap unrelated to this issue).
- **The `del` no-op asymmetry claim is stale.** `SimulationActionRunner.run`'s
  `del` list (now `:432-444`) already includes both `idle_timeout` and
  `automation_profile` — the described omission no longer exists. AC #3's
  "fixes the pre-existing `automation_profile` omission as a side effect"
  should be dropped or reworded; there is nothing left to fix there, only the
  mechanical `automation_profile`/`idle_timeout` → `automation` collapse.
- Two new params, `disable_background_tasks: bool = False` and
  `timeout_kill_grace_seconds: float = 0.0`, now sit between
  `automation_profile` and `idle_timeout` in all three `run()` signatures
  (added since this issue was written). They don't conflict with the
  proposed collapse — they carry through unchanged — but the "Old"/"New"
  signatures documented in Program Design should show them so an implementer
  isn't misled into dropping them. Corroborated independently by ENH-3095's
  own Codebase Research Findings, which flag this exact gap.

**Verdict persisted 2026-08-19:** the pass above ran without `--check`, which
is the mode that writes `verify_verdict:` to frontmatter, so the field was
left at its stale `VALID`. Applied the documented `OUTDATED → NON_VALID`
mapping (`commands/verify-issues.md:265-289`) by hand — the verification did
run and did return `OUTDATED`; only the persist step was skipped by mode.
Re-verify with `--check` after ENH-3095 lands, which is also when the two
missing params above and the stale `del`-asymmetry claim should be folded in.

**2026-08-19** (pre-implementation review, manual): every claim below was
checked directly against current `main` (ENH-3095 landed, `c7804788`). Two
blocking defects found and corrected in-place; the structure of the refactor
remains sound.

1. **Blocking — the issue contradicted itself on whether the legacy kwargs
   survive.** AC #4 and Decision Rules said they stay as deprecated
   pass-throughs; Program Design's "New" signature deleted them. ENH-3095's
   landed code keeps them (`host_runner.py` `build_streaming()` still declares
   `automation_profile`/`disable_background_tasks` next to `automation`), so
   "stay" is correct. Signatures section rewritten as additive; Scope
   Boundaries now states plainly that this issue grows the signature and the
   real collapse is a later cleanup.
2. **Blocking — `DefaultActionRunner` could not forward `automation=`
   downstream.** `run_claude_command()` (`subprocess_utils.py:343-366`) has no
   `automation` parameter; that is ENH-3097, not yet landed. The old Call Path
   instruction ("becomes forwarding `automation=automation`") would raise
   `TypeError` on every prompt action. Call Path now specifies decomposing the
   resolved context back into legacy kwargs at `fsm/runners.py:200-218`, and
   AC #5 covers it.
3. **The shim is not a drop-in reuse of `_resolve_automation()`.** That helper
   takes three inputs and has no `idle_timeout`; this boundary needs a fourth,
   plus an explicit `int 0` → `float | None` mapping. Added Program Design §
   The Shim with a recommendation (extend the shared helper) and the mapping
   rules. Earlier text calling the shapes "identical" corrected.
4. **The kwarg gate widens.** Three independent per-knob gates become one
   combined gate, so a state configuring only `idle_timeout` now receives
   `automation=`. The Tests section previously annotated the ~11 inline fakes
   as "safe under the kwarg-gating contract" — true only when nothing
   resolves. Annotation corrected; fakes reached with automation active need
   `automation` or `**kwargs`.
5. **`_wall_fallback` hazard.** `fsm/executor.py:2276` derives BUG-3032's
   wall-clock fallback from the `_idle_timeout` local being folded into the
   context; noted in Call Path and AC #2 so it isn't dropped.
6. **Stale line numbers propagated into the normative sections.** The prior
   passes corrected them only in the appendices while Scope Boundaries, Files
   to Modify, ACs, Call Path, and Decision Rules still carried
   `executor.py:1886-1910`, `runners.py:39-53/:98-112/:370-384`,
   `API.md:5769-5785`, `del` at `:404`, `_contrib_extra` at `:1860-1879`, and
   idle reads at `:287,313`. All updated to verified current values.
7. **AC #3 rewritten** — the `del` asymmetry it promised to fix does not
   exist (`fsm/runners.py:432-444` already covers all three legacy names);
   the change there is purely additive.
8. **Added missing ACs/scope**: a required test class for the
   `ActionRunner`-side shim (previously only mentioned in the wiring notes),
   the `API.md:6096-6098` kwarg-gating prose (which this change invalidates),
   the missing `timeout_kill_grace_seconds` in the `API.md` mirror, and
   `docs/development/TESTING.md:635-643`'s already-drifted `MockActionRunner`
   example — folded in here rather than left to drift, since this issue
   changes the mock contract.

**2026-08-19** (second pre-implementation review, manual): re-checked every
load-bearing claim against current `main`. The line numbers, the
`_resolve_automation()` contract, the `del` list contents, the two added
params, and the `run_claude_command()` decomposition hazard **all verify
correctly** — no structural change needed. Seven additions applied:

1. **The shared-helper reuse would ship a wrong warning.** `_resolve_automation()`'s
   message hardcodes `"build_streaming() received both …"`; called from
   `ActionRunner.run()` it names a function the caller never invoked. Added a
   required `caller` parameter (AC #7) plus the note that the existing tests
   match on the loose pattern `"automation"` and would not catch it. Also
   recorded two verified non-issues so they aren't re-litigated: `stacklevel=3`
   is still correct at the new site (identical frame depth), and there is no
   circular-import risk (`fsm/runners.py:22` already imports from
   `host_runner`).
2. **"Explicit wins" silently drops a legacy `idle_timeout`.** Unlike the other
   two knobs, `idle_timeout` drives the *shell* branch's selector loops
   (`runners.py:311,337`), so the drop disables hang detection on a live shell
   state. Unreachable from the executor, reachable by any direct `run()` caller.
   **Resolved same day:** option (a) chosen — the uniform "explicit wins, warn"
   rule stands and the legacy value is discarded by design. Recorded in § The
   Shim with its rationale and pinned by AC #6; no open decision remains.
3. **Right-sized the gate-widening risk.** Extension runners reach the executor
   via `_contributed_actions` → the contributed branch's `_contrib_extra`, not
   `extra_kwargs`; the main `action_runner`'s only injection point is
   `FSMExecutor(action_runner=...)` ("for testing"). The widened gate therefore
   cannot break the plugin ecosystem. Added to Decision Rules.
4. **Replaced the per-fake audit with a mechanical fix.** "Audit each fake
   against the states its test configures" is expensive and goes stale on the
   next knob. There are 112 `def run(` definitions across 19 test files. Tests
   now mandates `**kwargs: Any` on every `ActionRunner` fake, with one
   deliberate exception (the old-runner double in
   `test_feat3033_idle_timeout.py:390-467`, which `**kwargs` would make
   vacuously pass). Safe because of finding 3.
5. **Added the type gate to the ACs.** AC #9 now requires `mypy` and `ruff`
   alongside pytest — this change is a Protocol signature edit, which pytest
   does not police.
6. **Added two missing edit targets**: `host_runner.py:1886-1920` was absent
   from Files to Modify despite being edited under the recommended shim
   approach, and `SimulationActionRunner.run()`'s docstring `Args:` list
   (`fsm/runners.py:412-426`) already omits `idle_timeout` and would omit
   `automation`.
7. **Housekeeping**: dropped the stale "`blocked_by: [ENH-3095]` is resolved"
   narrative from the Summary (frontmatter is already `[]`). `verify_verdict`
   remains `NON_VALID` from the mode-skipped persist above, but every item that
   verdict flagged has since been corrected — re-run `/ll:verify-issues --check`
   before implementation or a go/no-go gate will block on a stale field.

**2026-08-19** (`/ll:verify-issues --check`): re-verified every load-bearing
line number, signature, and count against current `main`. All confirmed
exact — `ActionRunner.run()` Protocol (`:40-56`), `DefaultActionRunner.run()`
(`:109-125`, forwarding call `:200-218`, selector-loop reads `:311`/`:337`),
`SimulationActionRunner.run()` (`:394-410`, `del` list `:432-444`, docstring
still omitting `idle_timeout`), `AutomationContext` (`host_runner.py:172-190`),
`_resolve_automation()` (`:1886-1920`), `run_claude_command()` signature
(`subprocess_utils.py:343-366`, no `automation` param), `extra_kwargs`/`_contrib_extra`
assemblies and `_wall_fallback` derivation in `executor.py`, the `API.md`
mirror (`:6072-6100`, code block `:6075-6091`, prose `:6096-6098`, still
missing `timeout_kill_grace_seconds`), and the "112 `def run(` across 19 test
files" count (`grep -rn "def run(" scripts/tests/*.py | wc -l` → 112;
`grep -rln` → 19).

**One inaccuracy found and corrected below.** The Codebase Research Findings
section (under Program Design) claims `_resolve_automation()` is "called
identically at all 7 `build_streaming()` implementations (e.g.
`host_runner.py:362`)". Verified count is **6**, not 7: call sites are at
`:362, 671, 1069, 1267, 1456, 1663`. Of the 8 concrete `build_streaming()`
implementations (`ClaudeCodeRunner`, `CodexRunner`, `OpenCodeRunner`,
`PiRunner`, `GeminiRunner`, `OmpRunner`, `KimiRunner`, `QwenRunner`), two —
`OpenCodeRunner:866` and `PiRunner:942` — are unwired stubs that
unconditionally `raise HostNotConfigured(...)` and never reach the shim call.
This claim originates in ENH-3095's own research (inherited here) and is
background context for "the shim pattern to mirror," not part of this
issue's own scope or Program Design decisions — it does not change what
`ActionRunner.run()`'s shim must do. Verdict `NEEDS_UPDATE`: correct "7" to
"6" (or "6 of 8 concrete implementations, excluding the two unwired stubs")
wherever this count is cited.

**2026-08-19** (`/ll:verify-issues --check`, graph: provider=`codegraph`
freshness=`fresh`): re-verified every load-bearing line number, signature,
and count against current `main` for a second time. All confirmed accurate
except two off-by-one/two line-number drifts, both corrected in-place:

- `DefaultActionRunner.run()`'s `run_claude_command()` forwarding call is
  `:200-218` (was cited as `:198-217` in the Signatures summary line).
- The `_contrib_extra` dict itself starts at `:2211`, not `:2210` (three
  citations corrected: Wiring pass note, Decision Rules ×2). The Codebase
  Research Findings citation `:2203-2222` (branch start, not dict start) was
  already exact and is unchanged.

Everything else re-confirmed exact: `ActionRunner.run()` Protocol (`:40-56`),
`SimulationActionRunner.run()` (`:394-410`, `del` list `:432-444`, docstring
still omitting `idle_timeout`), `extra_kwargs` assembly (`:2229-2267`),
`_wall_fallback` (`:2276`), `AutomationContext` (`host_runner.py:171-190`),
`_resolve_automation()` (`:1886-1920`, 6 call sites at `:362,671,1069,1267,
1456,1663`), `run_claude_command()` (`subprocess_utils.py:343-366`, still no
`automation` param), `API.md` mirror (`:6072-6100`, code `:6075-6091`, prose
`:6096-6098`, still missing `timeout_kill_grace_seconds`), and the
112-def/19-file grep counts. ENH-3097 confirmed still `open` — the
issue's "not yet landed" assumption for `run_claude_command()` holds.
Decisions log checked: the one active rule bearing on this issue (sequence
after FEAT-3078) is satisfied — `disable_background_tasks` is already in all
three `run()` signatures. No `DECISIONS_VIOLATION`.

**Verdict: NEEDS_UPDATE** (two minor line-number drifts, now corrected).
Structure, signatures, and Program Design remain sound.

## Session Log
- `/ll:confidence-check` - 2026-08-20T03:49:46 - `519404c3-823a-450e-a451-9ef539f0b512.jsonl`
- `/ll:verify-issues` - 2026-08-20T03:47:11 - `74be4b45-e2a8-44ac-9a2a-7d8bd9d187b2.jsonl`
- `/ll:verify-issues` - 2026-08-20T03:41:18 - `231c8ac3-c9af-42c5-a42e-ca8e5ae3effb.jsonl`
- `/ll:confidence-check` - 2026-08-20T03:20:16 - `2aa6a55a-aa17-4bc9-8502-2bb12cc16aa2.jsonl`
- `/ll:confidence-check` - 2026-08-20T02:04:14 - `833d1ad6-7285-4af9-88d5-083c9b946f51.jsonl`
- `/ll:wire-issue` - 2026-08-20T01:45:51 - `af1a453c-65d0-4b3c-bc6b-b8e4bf055010.jsonl`
- `/ll:refine-issue` - 2026-08-20T01:35:05 - `f61456ba-aec2-43f2-8c6e-c3a8655726d7.jsonl`
- `/ll:verify-issues` - 2026-08-20T00:59:29 - `e89696fe-140c-45df-a34b-1cf937e9f43c.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:10 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:refine-issue` - 2026-08-07T22:51:22 - `596f76ed-c393-479b-9539-adbce5a6a72b.jsonl`
- `/ll:issue-size-review` - 2026-08-07T22:09:43 - `dec986a1-15de-4376-b5dd-5868a8d3e188.jsonl`

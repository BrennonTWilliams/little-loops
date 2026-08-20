---
id: ENH-3261
type: ENH
title: Remove deprecated automation_profile/disable_background_tasks/idle_timeout
  kwargs and rule on future automation-knob placement
priority: P4
status: done
blocked_by:
- ENH-3097
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T16:33:59Z'
completed_at: '2026-08-20T19:58:33Z'
labels:
- automation
- refactor
- tech-debt
confidence_score: 100
outcome_confidence: 85
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 22
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

The three legacy kwargs are removed from all three declaring signatures, a
`*` keyword-only marker is inserted at each removal point (so a stale
positional caller fails loudly instead of silently re-binding — see Impact),
the internal `resolve_automation()` folding at those sites is deleted (each
function reads `automation` directly), and the now-unreachable
`Test*AutomationShim` legacy-kwarg test cases for those three sites are
removed. `test_enh3097_no_mixed_automation_kwargs.py` is **repurposed, not
deleted**, into a signature guard that fails if any of the three names
reappears on any of the three functions. `runner_spec._run_skill()`'s
`spec.args` legacy dict keys are addressed separately per a written ruling
(they have out-of-tree consumers, unlike the three signatures above — see
Program Design § Decision Rules item 1). Written rulings also exist for where
future automation knobs (`timeout_kill_grace_seconds`, `sandbox_mode`)
belong, and for the two sibling shims (ENH-3095/ENH-3096), which are ruled
permanently kept because they sit on Protocol boundaries — making these three
concrete functions the only shim surface this chain removes.

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
   Behavior, and their `resolve_automation()` folding. Insert a `*`
   keyword-only marker at each removal point.
2. Delete the legacy-kwarg-focused test cases in each site's
   `Test*AutomationShim` class (`test_legacy_kwargs_construct_context_internally`,
   `test_legacy_kwarg_alone_is_silent`, the conflict/warn tests, and
   `test_empty_context_equivalent_to_none`'s legacy-kwarg comparisons) —
   keep only the tests that exercise `automation=` directly.
3. Repurpose `test_enh3097_no_mixed_automation_kwargs.py` from a call-site
   AST guard into an `inspect.signature` guard over the three functions
   (see Program Design § Regression Guard).
4. Update `resolve_automation()`'s docstring (`host_runner.py:1902-1906`),
   whose "every in-tree caller does exactly that until ENH-3097 migrates
   them" rationale for silent bare-legacy use is already false.
5. Add a CHANGELOG entry under a **Breaking change** callout naming the three
   removed kwargs and the `automation=AutomationContext(...)` migration.
6. All three rulings are already written below (Decision Rules items 1-3) and
   require no code work. Carry them into `.ll/decisions.yaml` via
   `ll-issues decisions` if a machine-readable record is wanted — item 3's
   Protocol-vs-concrete rule is the one worth recording, since it governs
   every future shim-removal question in this area.

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()` def
- `scripts/little_loops/issue_manager.py` — `run_claude_command()` wrapper
  def and `run_with_continuation()` def
- `scripts/little_loops/host_runner.py` — `resolve_automation()`'s docstring
  only (lines 1902-1906): the "every in-tree caller does exactly that until
  ENH-3097 migrates them, and warning there would flood every `ll-auto` run"
  rationale for silent bare-legacy-kwarg use is falsified by this issue's own
  premise. The function body is untouched (it stays shared — see Codebase
  Research Findings).
- `docs/reference/API.md` — the two `run_claude_command()` mirrors (drop the
  deprecated-knob `Args:` entries added by ENH-3097)
- `CHANGELOG.md` — a **Breaking change** entry (repo precedent:
  `CHANGELOG.md:2482`), naming the three removed kwargs and the
  `automation=AutomationContext(profile=..., disable_background_tasks=...,
  idle_timeout=...)` migration for out-of-tree callers. Per project
  convention, promote into a concrete `## [X.Y.Z] - DATE` section rather than
  filing under `[Unreleased]`.

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_manager.py::TestRunWithContinuation::test_forwards_disable_background_tasks_to_subprocess`
  (line 1415, call at 1435-1440) — a third legacy-kwarg test the prior
  `/ll:refine-issue` passes missed; passes `automation_profile="ll-auto",
  disable_background_tasks=True` directly to `run_with_continuation()` and
  becomes a call-site `TypeError` post-removal, same as the two already-named
  tests. `test_automation_profile_defaults_to_none` (1468) and
  `test_disable_background_tasks_defaults_to_false` (1444) pass no legacy
  kwargs and won't break, but their docstrings/rationale become stale.
- `scripts/tests/test_enh3097_no_mixed_automation_kwargs.py` — **repurposed,
  not deleted** (see Program Design § Regression Guard). Its call-site AST
  check goes trivially-green after removal (nothing left to mix), but
  deleting it outright leaves nothing preventing the kwargs from being
  re-added — which is exactly the failure ENH-3130 already demonstrated once.

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

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- Test line corrections (from `codebase-analyzer`, `/ll:refine-issue` re-run): `test_subprocess_utils.py::TestRunClaudeCommandAutomationShim` spans lines 2461-2594 (all calls keyword-style, e.g. `automation_profile="autodev", disable_background_tasks=True` at 2495-2497 — each becomes a clean `TypeError` after removal, not a silent behavior change).
- `test_issue_manager.py`'s two legacy-kwarg-forwarding tests resolve to `test_forwards_automation_profile_to_subprocess` and `test_automation_profile_defaults_to_none`, with keyword-style calls in the 1395-1442 range — re-verify exact line numbers at implementation time, as this file shifts frequently.
- `runner_spec.py`'s legacy `spec.args` dict-key surface (Decision Rules item 1) has direct test coverage at `scripts/tests/test_runner_spec.py:228-296` (`TestRunSkillAutomationCompat`), whose class docstring independently states "the only externally-facing compat surface" — corroborating evidence for keeping the dict keys, unaffected by this issue's function-kwarg removal.
- `scripts/tests/test_host_runner.py:150-240,1600-1640` (`TestAutomationContext`) covers `HostRunner.build_streaming()`'s own legacy kwarg pair — a related but out-of-scope declaring site (ENH-3095), not one of this issue's three functions; do not touch it under this issue.

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
- **Risk**: Low in-tree, moderate out-of-tree. Every in-tree caller already
  migrated off the legacy kwargs (ENH-3097 AC 10/AC 3), so removal cannot
  silently change in-tree behavior. Two out-of-tree risks, of different
  severity:
  - *Keyword callers* — fail loudly with `TypeError`. Benign.
  - *Positional callers* — **fail silently.** `idle_timeout` sits
    mid-signature at all three sites (position 7 / 5 / 7, see Program Design
    § Signatures), so removing it re-binds every positional argument after it
    to the wrong parameter: a caller passing `run_claude_command(cmd, 3600,
    wd, cb, on_start, on_end, 300)` lands `300` on `on_model_detected`
    instead of `idle_timeout`. This is the sharpest risk in the change and is
    the reason for the `*` keyword-only marker at each removal point, which
    converts it back into a loud `TypeError`. All in-tree calls are
    keyword-style (verified by the `/ll:wire-issue` grep below), so the
    marker costs nothing in-tree.
- **Breaking Change**: Yes - for any caller (in-tree or out-of-tree) still
  passing `automation_profile=`/`disable_background_tasks=`/`idle_timeout=`
  directly to `run_claude_command()` or `run_with_continuation()`. The
  package ships to PyPI, so this needs a CHANGELOG **Breaking change** entry
  (see Integration Map § Files to Modify), not just an in-repo removal.
  Note that `idle_timeout` is the sharper break of the three: unlike the two
  deprecated-from-birth kwargs, it is a long-standing first-class parameter
  (FEAT-3033) reachable from CLI flags (`cli_args.add_idle_timeout_arg`,
  `cli_args.py:125`) and only labelled deprecated by ENH-3097 itself.

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
0`) from each of the **three** declaring sites below, keeping `automation`
and every other parameter untouched. The first two collide by bare name and
must be disambiguated by module:

1. `subprocess_utils.run_claude_command(...)` — `subprocess_utils.py:348`;
   drops all three (`idle_timeout` at param position 7 of 22)
2. `issue_manager.run_claude_command(...)` — `issue_manager.py:140`, the
   wrapper; drops all three (`idle_timeout` at position 5)
3. `issue_manager.run_with_continuation(...)` — `issue_manager.py:280`;
   drops all three (`idle_timeout` at position 7)

Post-removal shape at each site (delta shown against `automation`, which is
the one automation parameter that survives):

`def run_claude_command(command: str, *, automation: AutomationContext | None = None) -> subprocess.CompletedProcess[str]` — the `subprocess_utils` site, sites 1 and 2 above sharing this shape

`def run_with_continuation(initial_command: str, logger: Logger, *, automation: AutomationContext | None = None) -> subprocess.CompletedProcess[str]` — the `issue_manager` site

Each removal point gets a `*` keyword-only marker so the parameters that
followed the removed ones cannot be reached positionally. Without it, an
out-of-tree caller passing arguments positionally past a removed parameter
binds its values to the *wrong parameters* silently — see Impact § Risk.
This applies to all three removed names, not just `idle_timeout`: in
`subprocess_utils.run_claude_command()`, `automation_profile` and
`disable_background_tasks` sit at positions 16/17 with **six** parameters
after them (`post_stream_close_grace_seconds`, `timeout_kill_grace_seconds`,
`on_result_seen`, `on_session_id_detected`, `on_tool_call`,
`workspace_root`), so removing even those two shifts positions.

### Call Path

Each of the three declaring functions currently calls
`resolve_automation(automation, automation_profile, disable_background_tasks,
idle_timeout, caller=...)` internally to fold the legacy trio; after removal
each reads `automation` directly with no fold step, and forwards it unchanged
to its own callee (`build_streaming()` / `_run_claude_base` / the wrapper)
exactly as it does today when `automation=` is already the incoming value.

In `subprocess_utils.run_claude_command()` only, the second read at
`subprocess_utils.py:468-470` collapses to
`effective_idle_timeout: float = (automation.idle_timeout or 0) if automation else 0`
— the `if ... else` guard **stays** (`automation` is still `None` on the
common path); only the `else idle_timeout` fallback branch changes to `else
0`. An earlier research bullet below describes this as reading
`resolved_automation.idle_timeout or 0` "directly"; that phrasing drops a
guard that is still required.

### Regression Guard

`test_enh3097_no_mixed_automation_kwargs.py` is rewritten from a call-site
AST walk into an `inspect.signature` assertion: for each of the three
functions above, none of `automation_profile` / `disable_background_tasks` /
`idle_timeout` appears in `.parameters`. This is the mechanism that makes
Decision Rules item 2 enforceable rather than advisory — the ENH-3130
precedent (a new knob landed as a bare kwarg after `AutomationContext`
already existed) is evidence that a written rule alone does not hold. Keep
the existing file's `_TARGET_NAMES` breadth in mind: it also covers the
`_run_claude_base` import aliases at `issue_manager.py:66` and
`worker_pool.py:39`, which are the same two symbols under a different name.

### Decision Rules

Both rulings below are **written, not open** — the Codebase Research Findings
in this issue already supply the evidence each needs, so neither is
implementation-time work. Re-verify the two named greps at implementation
time; do not re-derive the conclusions.

1. **`runner_spec` legacy dict keys — RULING: kept indefinitely.**
   `spec.args["automation_profile"]` and
   `spec.args["disable_background_tasks"]` (`runner_spec.py:139-144`) stay.
   Rationale: unlike a function kwarg, a dict key is an
   externally-originated wire format — every producer is out-of-tree
   (`ll-harness` / `ll-action` / extension runners), so this repo cannot
   coordinate the break the way it can with an in-tree caller. The
   preconditon that licensed removing the three function kwargs ("no
   in-tree caller uses them") is therefore *not* the same precondition here:
   in-tree absence is exactly what makes these keys purely external.
   `runner_spec.py:128-132` already carries this rationale in-code (tagged
   ENH-3097), and `test_runner_spec.py:228-296`
   (`TestRunSkillAutomationCompat`) independently documents the surface as
   "the only externally-facing compat surface." Re-verify at implementation
   time that a repo-wide grep for `"automation_profile"` under
   `scripts/little_loops/` still hits only the `runner_spec.py` read; if an
   in-tree producer has appeared, this ruling reopens.

2. **Future-knob placement — RULING: `AutomationContext` carries knobs that
   cross the host-runner boundary and apply to every host; knobs consumed
   locally, or specific to one host, stay bare parameters.**
   Under that criterion both named knobs stay parameters:
   - `timeout_kill_grace_seconds` — **stays a parameter, not retrofitted.**
     It never reaches the layer `AutomationContext` flows through: it is
     consumed locally by `_kill_process_group(process,
     grace_seconds=...)` (`subprocess_utils.py:538,549`) and is never
     forwarded to `build_streaming()`. Putting it on the context would ship
     a field through the host-runner boundary that no host reads. This also
     retroactively ratifies ENH-3130's shape rather than treating it as the
     mistake the Motivation section frames it as — the Motivation's real
     complaint (contributors read three deprecated-but-present kwargs as
     license to add a fourth) is addressed by the removal plus the § Regression
     Guard, not by relocating this knob.
   - `sandbox_mode` — **stays a parameter.** It exists only as a
     `CodexRunner`-private argument (`host_runner.py:664`), is absent from
     the shared `HostRunner` Protocol (`host_runner.py:242-255`) and from
     the other seven `build_streaming()` implementations, and maps to
     Codex-only CLI flags via `CodexRunner._VALID_SANDBOX_MODES`
     (`host_runner.py:600-614`). Host-specific knobs are categorically
     exempt from `AutomationContext` collapse: the dataclass's whole purpose
     is to spare all 8 implementations a parameter each, which a knob only
     one of them understands does not do.

   Consequence: Proposed Solution's former "retrofit if the ruling says so"
   step is resolved as *no retrofit*, and `AutomationContext` keeps its three
   fields (`profile`, `idle_timeout`, `disable_background_tasks`,
   `host_runner.py:172-190`).

3. **Sibling shims (ENH-3095 / ENH-3096) — RULING: both kept indefinitely;
   no follow-up removal issues.** The governing distinction is *what kind of
   surface carries the shim*, not which kwarg it is:

   > **Concrete in-tree functions shed compatibility shims. Protocol methods
   > and dict wire formats keep them.**

   A concrete function has only *callers*, and this repo can see all the
   in-tree ones (ENH-3097 migrated them; the `/ll:wire-issue` grep below
   confirms zero remain). A `Protocol` method has out-of-tree
   *implementers* who must structurally match the signature — dropping a
   parameter breaks anyone who declares it, and neither the implementer set
   nor a migration window is under this repo's control. A dict wire format
   (item 1) has out-of-tree *producers*, same constraint.

   Both sibling shims sit on Protocols: `HostRunner.build_streaming()`
   (`host_runner.py:242`, 8 implementations) and `ActionRunner.run()`
   (`fsm/runners.py:35`, with `DefaultActionRunner` at :117 and
   `SimulationActionRunner` at :~428 plus out-of-tree extension runners).
   They are therefore **kept**, under the same rule as item 1 — this is a
   decision, not a default. This issue's three functions are the only
   non-Protocol surface among the four shims, which is precisely why it is
   the only one whose kwargs are removed.

   This also disposes of the "shim with no follow-up filed never gets
   removed" worry raised by the Motivation: these two are not awaiting a
   follow-up, they are ruled permanent. `resolve_automation()` stays live to
   serve them (see Codebase Research Findings).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- `resolve_automation()` (`host_runner.py:1886-1934`) confirmed semantics: when `automation` is given together with any legacy value, it emits a `DeprecationWarning` and returns `automation` unchanged — the legacy values (including `idle_timeout`) are **discarded, not merged**. When only legacy values are given, it constructs a fresh `AutomationContext(profile=automation_profile, disable_background_tasks=disable_background_tasks, idle_timeout=idle_timeout)`. When neither is given, it returns `None`. This confirms the issue's "explicit `automation=` wins, legacy kwargs still work" framing exactly.
- Evidence for Decision Rules item 2 (`timeout_kill_grace_seconds` / `sandbox_mode` placement): `timeout_kill_grace_seconds` is a bare `float` parameter at every layer today (`subprocess_utils.py:367`, `issue_manager.py:155`, `issue_manager.py:299`, `fsm/runners.py:133`, `runner_spec.py:156` via `spec.args`, `parallel/worker_pool.py:963`) — it has **no** `AutomationContext` field, and `subprocess_utils.run_claude_command()` never forwards it past its own local `_kill_process_group(process, grace_seconds=timeout_kill_grace_seconds)` call (`subprocess_utils.py:538,549`); it never reaches the host-runner/`build_streaming()` layer where `AutomationContext` actually flows. This is evidence toward "keep as bare parameter," not retrofit.
- `sandbox_mode` exists concretely only as a `CodexRunner`-private bare parameter (`host_runner.py:664`, `sandbox_mode: str | None = None`) — it is not on the shared `HostRunner` Protocol (`host_runner.py:242-255`), not on any of the other 7 `build_streaming()` implementations, and not an `AutomationContext` field. Its host-specificity (a `CodexRunner._VALID_SANDBOX_MODES` mapping to Codex-only CLI flags, `host_runner.py:600-614`) is direct evidence for the issue's proposed "host-specific knobs are categorically exempt from `AutomationContext` collapse" framing.

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- `subprocess_utils.run_claude_command`'s `idle_timeout` removal is not a clean single deletion like the other two kwargs: beyond the `resolve_automation()` fold, `idle_timeout` is read a second time at `subprocess_utils.py:468-470` to compute `effective_idle_timeout = (resolved_automation.idle_timeout or 0) if resolved_automation else idle_timeout`, used by the local idle-kill check (`subprocess_utils.py:548,558`). Removing the bare `idle_timeout` parameter requires collapsing this fallback expression to read `resolved_automation.idle_timeout or 0` directly, not just deleting the parameter and the `resolve_automation()` call argument. `automation_profile`/`disable_background_tasks` in this same function, and all three legacy names in both `issue_manager.py` functions, appear only in their docstring and the fold call — a clean deletion for those.
- False-positive caution for the removal pass: `issue_manager.py` lines ~903-904, 977-980, 1182-1183, 1326-1327, 1519-1520 also contain the tokens `disable_background_tasks=` / `idle_timeout=`, but these are `AutomationContext(...)` constructor calls populating the dataclass's own fields at `process_issue_inplace`'s call sites — not the deprecated kwargs of `run_claude_command`/`run_with_continuation`. Do not mistake these for legacy-kwarg call sites during removal.
- `resolve_automation()` (`host_runner.py:1886-1934`) confirmed: the `DeprecationWarning` fires only when `automation` and any legacy value are both given (the legacy value is then discarded, not merged); a bare legacy-kwarg-only call remains silent by design, per an existing docstring rationale ("warning there would flood every ll-auto run", lines 1904-1906) that this issue's own premise — every in-tree caller has migrated — now falsifies.
- Precedent evidence for Decision Rules item 2: `timeout_kill_grace_seconds` (ENH-3130) was already added to all three shim signatures as a bare parameter (`subprocess_utils.py:367`; `issue_manager.py:155,299`; `runner_spec.py:156`), not as an `AutomationContext` field — `AutomationContext` (`host_runner.py:172-190`) has exactly three fields today (`profile`, `idle_timeout`, `disable_background_tasks`); no `sandbox_mode` or `timeout_kill_grace_seconds` field exists anywhere in the codebase. The ruling must reconcile with or explicitly override this existing precedent rather than treat the question as open.
- `test_enh3097_no_mixed_automation_kwargs.py`'s AST guard (`TestNoMixedAutomationKwargs`, class at line 66) inspects call-site keyword names only, not function signatures — it will keep passing trivially after removal (nothing left to mix) but becomes vestigial/dead documentation of a completed migration. Its two synthetic self-tests hardcode legacy kwarg names in string snippets and don't need touching for mechanical removal to succeed.

_Added by `/ll:wire-issue` — 2026-08-20 — based on codebase analysis:_

- Repo-wide grep for `automation_profile=`/`disable_background_tasks=`/`idle_timeout=` (excluding tests) across `scripts/` found **no** in-tree caller passing these as legacy kwargs to `run_claude_command()`/`run_with_continuation()` — every hit resolved to either an `AutomationContext(...)` constructor call, an unrelated same-named field on a different class/dataclass (`OrchestrationConfig`, `StateConfig`, `WorkerPool._run_claude_command`'s own parameter), or `resolve_automation()`'s own definition. This corroborates the issue's "every in-tree caller already migrated" claim (AC 1 risk assessment).
- Doc/manifest/schema/gate coupling confirmed clean: `CLAUDE.md`, `CONTRIBUTING.md`, `commands/*.md`, `skills/*/SKILL.md`, `config-schema.json`, `.ll/ll-config.json`, loop YAML, and `hooks/` all have zero references to the three kwarg names as call-site kwargs to the two target functions. `docs/reference/API.md` has additional automation-kwarg blocks beyond the two known `run_claude_command()` mirrors, but they document `HostRunner.build_streaming()` (API.md:9565-9582) and `ActionRunner` (API.md:6077-6106) — separate, out-of-scope Protocols; no third doc block exists for `run_with_continuation()` beyond a passing mention (API.md:11606).
- `resolve_automation()` (`host_runner.py:1886-1934`) is called from six other live sites beyond the three being removed here — `build_streaming()` (6 `HostRunner` implementations), `DefaultActionRunner.run()` (`fsm/runners.py:179-185`, `caller="ActionRunner.run()"`), and `runner_spec.py`'s `_run_skill()` (`caller="_run_skill()"`) — confirming the issue's existing statement that `resolve_automation()` itself is not deleted. Their `pytest.warns(DeprecationWarning, ...)` assertions (`test_fsm_runners.py:696,708,732`; `test_host_runner.py:1622,1632`; `test_runner_spec.py:289`) all match different `caller=` string labels than the two target functions', so none break when this issue's folding is removed.

## Out of Scope

- Retrofitting `timeout_kill_grace_seconds`/`sandbox_mode` onto
  `AutomationContext` — **resolved as "no retrofit"** by Decision Rules
  item 2, so no code work falls out of it. `AutomationContext` keeps its
  three current fields.
- Any change to `HostRunner.build_streaming()`'s own legacy
  `automation_profile`/`disable_background_tasks` kwargs (ENH-3095) or to
  `ActionRunner.run()`'s (ENH-3096). Both are Protocol boundaries and are
  ruled **kept indefinitely** (Decision Rules item 3) — permanently out of
  scope, not deferred.

## Resolved Questions

1. **Does `idle_timeout` belong in this issue?** — **RESOLVED: yes; all
   three kwargs are removed together.**

   The question was whether to defer `idle_timeout` to a batch with the
   ENH-3095/ENH-3096 shim removals, on the grounds that it is a first-class
   FEAT-3033 parameter with a CLI surface (`cli_args.add_idle_timeout_arg`,
   `cli_args.py:125`) rather than a born-deprecated shim, and that removing
   it here leaves `ActionRunner.run()` / `DefaultActionRunner.run()` /
   `SimulationActionRunner.run()` still declaring `idle_timeout: int = 0`
   (`fsm/runners.py:55,132,443`). Resolved against deferral, on three
   grounds:

   - **The asymmetry is the rule working, not a wart.** Decision Rules item 3
     draws the line at Protocol-vs-concrete. `ActionRunner` is a `Protocol`
     (`fsm/runners.py:35`) whose out-of-tree implementers must structurally
     match; `run_claude_command()` is a concrete function with only callers.
     `idle_timeout` surviving one layer up and dying one layer down is
     exactly what that rule prescribes, and deferral would postpone this
     removal to align with a layer that is now ruled never to align.
   - **Deferral does not avoid the positional-shift risk**, which was its
     main practical draw. `automation_profile`/`disable_background_tasks`
     sit at positions 16/17 of `subprocess_utils.run_claude_command()` with
     six parameters after them, so removing only those two shifts positions
     too. The `*` keyword-only marker is required either way, and once
     present the risk is zero for all three names.
   - **Deferral costs two breaking releases on the same three functions** —
     duplicate CHANGELOG entry, test churn, and signature-guard revision —
     against thin evidence of exposure: the `/ll:wire-issue` grep found no
     caller of any kind passing these as function kwargs, and the concrete
     external surface is the `runner_spec` `spec.args` dict, which item 1
     keeps regardless.

   Accepted cost: a caller wanting only an idle-kill must construct
   `AutomationContext(idle_timeout=N)` — a type named for automation used
   for a plain timeout. This is a naming smell, not a behavior change (an
   `AutomationContext` with `profile=None` yields the same `LL_AUTOMATION=""`
   as `automation=None`, via `_apply_automation_env()`,
   `host_runner.py:1866-1882`), and ENH-3095 put `idle_timeout` on the
   dataclass deliberately ("carried here for signature uniformity with the
   `ActionRunner` boundary", `host_runner.py:183-185`). Reopening it here
   would relitigate the settled ENH-3094→3097 chain rather than fix
   anything.

## Acceptance Criteria

1. All three legacy kwargs (`automation_profile`, `disable_background_tasks`,
   `idle_timeout` — per Resolved Questions item 1) are removed from
   `subprocess_utils.run_claude_command()`, `issue_manager.run_claude_command()`,
   and `issue_manager.run_with_continuation()`, along with their
   `resolve_automation()` folding and dead shim-kwarg tests. A `*`
   keyword-only marker sits at each removal point, so a stale positional
   call raises `TypeError` rather than silently binding to the wrong
   parameter.
2. ~~A written ruling exists on `runner_spec._run_skill()`'s legacy
   `spec.args` keys~~ — **satisfied in-issue**: Decision Rules item 1 rules
   *kept indefinitely*. Verification reduces to re-running its named grep and
   confirming no in-tree producer has appeared.
3. ~~A written ruling exists on `timeout_kill_grace_seconds` /
   `sandbox_mode` placement~~ — **satisfied in-issue**: Decision Rules item 2
   rules *both stay bare parameters*, under the boundary-crossing criterion
   stated there. No retrofit; `AutomationContext` is unmodified.
4. `test_enh3097_no_mixed_automation_kwargs.py` is repurposed into an
   `inspect.signature` guard that fails if any removed name reappears on any
   of the three functions — verified by temporarily re-adding one kwarg and
   confirming the guard goes red.
5. `CHANGELOG.md` carries a **Breaking change** entry naming the removed
   kwargs and the `automation=AutomationContext(...)` migration, and
   `resolve_automation()`'s now-false docstring rationale
   (`host_runner.py:1902-1906`) is corrected.
6. ~~The two sibling shims each have a filed removal issue or a recorded
   ruling~~ — **satisfied in-issue**: Decision Rules item 3 rules both
   *kept indefinitely* under the Protocol-vs-concrete rule. No follow-up
   issues are filed. Verification reduces to confirming this issue changes
   neither `HostRunner.build_streaming()` nor `ActionRunner.run()`.
7. `python -m pytest scripts/tests/`, `python -m mypy scripts/little_loops/`,
   and `ruff check scripts/` all pass/are clean. Scope `ruff format` to the
   files actually changed — a bare `ruff format scripts/` reformats ~30
   unrelated files.

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
- `/ll:manage-issue` - 2026-08-20T19:58:03 - `ec728862-173d-4fdf-85c5-0f68ffbf8e20.jsonl`
- `/ll:ready-issue` - 2026-08-20T19:39:02 - `1b7f174f-b8b2-4a50-a0a1-d3642c95ce7a.jsonl`
- `/ll:confidence-check` - 2026-08-20T19:34:58 - `2c4b1f13-5fb0-471a-b37b-bbb8b476e566.jsonl`
- `/ll:confidence-check` - 2026-08-20T19:14:26 - `ef903645-d040-4ca1-8c8f-c324b6f98449.jsonl`
- `/ll:wire-issue` - 2026-08-20T19:10:35 - `9cb5f76e-23d6-4a1b-9819-6a1e9a11c010.jsonl`
- `/ll:refine-issue` - 2026-08-20T18:59:58 - `4917cb13-c907-4c13-94be-7c5d9e9796a9.jsonl`
- `/ll:refine-issue` - 2026-08-20T18:02:20 - `c26819fc-4c17-46b0-bed5-ff46e41ae3e1.jsonl`
- `/ll:format-issue` - 2026-08-20T16:39:21 - `131da9b9-fc52-4bdb-a155-4ddc01aec740.jsonl`

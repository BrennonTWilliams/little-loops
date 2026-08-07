---
id: ENH-3094
type: ENH
title: Collapse the per-call automation kwargs into a single AutomationContext dataclass
priority: P3
status: open
discovered_date: 2026-08-07
discovered_by: pre-implementation-review
captured_at: '2026-08-07T00:00:00Z'
labels:
- automation
- host-runner
- refactor
- tech-debt
testable: true
decision_needed: false
relates_to:
- FEAT-3078
- FEAT-3033
- ENH-2714
verify_verdict: VALID
confidence_score: 80
outcome_confidence: 69
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# ENH-3094: Collapse the per-call automation kwargs into a single AutomationContext dataclass

## Summary

Every per-invocation automation knob is threaded as its own keyword argument
through the same call chain. There are two today — `automation_profile`
(ENH-2714) and `idle_timeout` (FEAT-3033) — and FEAT-3078 adds a third,
`disable_background_tasks`. Each one costs the same fixed toll:

- 7 `build_streaming()` signatures (`ClaudeCodeRunner`, `CodexRunner`,
  `OpenCodeRunner`, `PiRunner`, `GeminiRunner`, `OmpRunner`, `KimiRunner`) plus
  the `HostRunner` Protocol (`host_runner.py:196,216`)
- the `ActionRunner` Protocol and its three implementations
  (`fsm/runners.py:39-53`, `DefaultActionRunner:98-135`,
  `SimulationActionRunner:352-409`)
- `subprocess_utils.run_claude_command()` (`:320`) and the local
  `issue_manager.run_claude_command()` wrapper (`:139-218`) plus
  `run_with_continuation` (`:268`)
- `runner_spec.py:128,145,176,182` and `fsm/executor.py:1886-1910`
- roughly eight test files of hand-written, explicit-signature `run()` mocks
  that raise `TypeError` on any new kwarg:
  `test_fsm_executor.py:36-70` (`MockActionRunner`, also imported by
  `test_feat3033_idle_timeout.py:28`), the inline fakes around
  `test_fsm_executor.py:10963` and `:11201`, `test_fsm_persistence.py:774`,
  `test_usage_journal.py:25`
- two hand-maintained Protocol mirrors in `docs/reference/API.md`
  (~5769-5789, ~9173-9198)

That is the majority of FEAT-3078's change surface, and it is not FEAT-3078's
own complexity — it is the cost of the threading pattern, paid a third time.

## Status

open — filed 2026-08-07 from FEAT-3078's Open Question 2 during
pre-implementation review. Deliberately sequenced after FEAT-3078.

## Current Behavior

Each per-invocation automation knob is its own keyword argument, repeated
verbatim down the whole chain:

```python
def build_streaming(self, *, prompt: str, ..., automation_profile: str | None = None) -> HostInvocation
def run(self, ..., automation_profile: str | None = None, idle_timeout: float | None = None) -> ActionResult
```

Adding one more knob means editing all ~20 declaration sites enumerated above,
including test mocks that raise `TypeError` on an unrecognized kwarg.

## Expected Behavior

Adding a fourth per-invocation automation knob touches the `AutomationContext`
dataclass and the code that reads the field — not 7 `build_streaming()`
signatures, 4 `ActionRunner` declarations, 8 test-mock signatures, and 2
hand-maintained doc mirrors.

## Impact

Pure tech-debt paydown; no user-visible behavior change. The payoff is on the
*next* automation flag, and the cost of not doing it is that every future flag
re-pays a fixed ~20-file toll that has nothing to do with the flag itself.

## Scope Boundaries

**In scope:** the `AutomationContext` dataclass, threading it through
`build_streaming()` / `run_claude_command()` / `ActionRunner.run()`, the
deprecated keyword pass-throughs, and the doc mirrors.

**Out of scope:** changing what any of the three knobs *does*; the
`HostRunner` Protocol's non-automation parameters (`working_dir`, `resume`,
`agent`, `tools`, `model`, `workspace_root`) — those are host-invocation
concerns, not automation context, and collapsing them would be a different and
larger refactor; and `_apply_automation_env()`'s env semantics, which ENH-3081
settled.

## Proposed Solution

Introduce a frozen `AutomationContext` dataclass carrying the per-invocation
automation knobs, and thread **one** parameter through the chain in place of
the current N:

```python
@dataclass(frozen=True)
class AutomationContext:
    profile: str | None = None
    idle_timeout: float | None = None
    disable_background_tasks: bool = False
```

`_apply_automation_env()` (`host_runner.py:1547`) already consolidates the env
side across all five real runners — this is the caller-side counterpart, and
the helper is the natural place for the context to land.

### Sequencing

Deliberately **not** a blocker for FEAT-3078. Two viable orders:

- **After FEAT-3078** — safest. FEAT-3078 pays the toll once more, then this
  collapses all three at once with three known consumers to validate against.
- **Before FEAT-3078** — cheaper in total, but does a wide mechanical refactor
  with only two consumers to prove the shape, and FEAT-3078 becomes the first
  test of an unproven abstraction.

Recommend **after**, unless FEAT-3078's implementation actually stalls on the
mock-signature churn — in which case flip the order rather than adding
`**kwargs` escape hatches to the mocks.

See Option A/B decision block under Proposed Solution → Codebase Research Findings.

### Backward compatibility

Keep the existing keyword arguments as deprecated pass-throughs that construct
an `AutomationContext` internally, so third-party `ActionRunner` implementations
and the `test_feat3033_idle_timeout.py:390-467` kwarg-gating tests
(`test_idle_disabled_omits_kwarg_for_old_runners`) keep working. That test class
is also the template for proving the compatibility shim.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- **Deprecated pass-through shim is net-new in this codebase**: no production `DeprecationWarning` shim exists to copy. The actual warning convention in `scripts/little_loops/` is `warnings.warn(msg, Category, stacklevel=N)` (CapabilityNotSupported style, `host_runner.py:108-116`). The `host_runner.py:114-115` docstring references a `config.core` `DeprecationWarning` precedent, but no `warnings.warn` or `DeprecationWarning` exists anywhere in `scripts/little_loops/config/core.py` — that reference is stale and should not be followed for the compatibility shim's warning calls.
- **`idle_timeout` never reaches `build_streaming()` or `_apply_automation_env()`**: it is consumed entirely in `subprocess_utils.py:478` (selector loop, kills with `output="idle_timeout"`) and the shell/mcp selector loops in `fsm/runners.py:287,313` / `fsm/executor.py:2150,2169`. The `AutomationContext` carrying `.idle_timeout` through `build_streaming()` is therefore for signature uniformity only — none of the 5 real `build_streaming()` implementations will read that field. This is fine (the context is a carrier, not a consumer), but worth noting in case an implementer expects `_apply_automation_env()` to consume it.
- **`SimulationActionRunner.run` `del (...)` asymmetry at `fsm/runners.py:404`**: the `del` no-op list includes `idle_timeout` but omits `automation_profile`, so `automation_profile` is an unreferenced declared parameter. ENH-3094 would collapse both into one `automation` parameter, fixing the asymmetry.
- **BUG-3093 interaction**: three `run_claude_command()` call sites in `issue_manager.py` pass `idle_timeout` but omit `automation_profile` entirely (`:826,893,1089`), causing children to receive `LL_AUTOMATION=""` (non-automation assertion). ENH-3094's refactor doesn't fix this — it only changes the parameter shape — but the collapsed signature makes the omission more visible since the call site would pass `automation=None` explicitly rather than omitting a kwarg.

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

**Option A**: Sequence after FEAT-3078 — safest. FEAT-3078 pays the threading toll once more, then ENH-3094 collapses all three knobs at once with three known consumers to validate against. The deprecated pass-through shim is proven against the real third-knob consumer rather than a hypothetical one.

> **Selected:** Option A — sequence after FEAT-3078; the collapse and deprecated shim are validated against three known consumers, per the recommendation below.

**Option B**: Sequence before FEAT-3078 — cheaper in total diffs, but does a wide mechanical refactor with only two consumers (`automation_profile`, `idle_timeout`) to prove the shape. FEAT-3078 becomes the first test of an unproven abstraction.

**Recommended**: Option A — after FEAT-3078. Unless FEAT-3078's implementation actually stalls on the mock-signature churn, in which case flip the order rather than adding `**kwargs` escape hatches to the mocks.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-07.

**Selected**: Option A — sequence after FEAT-3078

**Reasoning**: Sequencing the collapse after FEAT-3078 matches the recommendation already recorded in this issue's decision block and in FEAT-3078's Open Question 2. Codebase evidence confirms the deprecated pass-through shim is net-new — no production `DeprecationWarning` precedent exists (`host_runner.py:114-115`'s `config.core` reference is stale) — so the shim is best validated against the real third-knob consumer FEAT-3078 introduces rather than a hypothetical one, reusing the established kwarg-gating template (`test_feat3033_idle_timeout.py:390-467`). Option B's main strength, removing the ~8-file overlap with FEAT-3078, does not outweigh making FEAT-3078 the first test of an unproven abstraction and the BUG-3093 timing trap at `issue_manager.py:826,893,1089`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — after FEAT-3078 | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |
| Option B — before FEAT-3078 | 2/3 | 2/3 | 2/3 | 2/3 | 8/12 |

**Key evidence**:
- Option A: Reuses the kwarg-gating backward-compat pattern (`fsm/executor.py:1883-1910`) and its regression template (`test_feat3033_idle_timeout.py:425-466`); FEAT-3078 provides the real third-knob consumer to validate the net-new deprecated pass-through shim. Cost: doc mirrors touched twice (minor).
- Option B: Removes the near-total file overlap with FEAT-3078 (~8 shared files) and shrinks FEAT-3078's diff, but mock churn is comparable (14 explicit `run()` signatures in `test_fsm_executor.py`), the shim stays net-new, and landing before BUG-3093 hard-codes the `idle_timeout`-only asymmetry at `issue_manager.py:826,893,1089`.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/host_runner.py` — add `AutomationContext` dataclass alongside `HostInvocation`; replace `automation_profile` kwarg with `automation: AutomationContext | None` in `HostRunner` Protocol (`:216-248`) and 7 concrete `build_streaming()` signatures; update `_apply_automation_env()` signature (`:1547`)
- `scripts/little_loops/fsm/runners.py` — replace `automation_profile`/`idle_timeout` kwargs with `automation: AutomationContext | None` in `ActionRunner` Protocol (`:39-53`) and 2 implementations (`DefaultActionRunner:98-112`, `SimulationActionRunner:370-384`)
- `scripts/little_loops/subprocess_utils.py` — replace per-knob kwargs with `automation` in `run_claude_command()` (`:320-341`); `idle_timeout` is consumed locally at `:478`, never reaches `build_streaming()`
- `scripts/little_loops/issue_manager.py` — same in wrapper `run_claude_command()` (`:139-152`) and `run_with_continuation()` (`:252-269`)
- `scripts/little_loops/runner_spec.py` — update `automation_profile` read (`:128`) and forwarding sites (`:145,176,182`)
- `scripts/little_loops/fsm/executor.py` — collapse `extra_kwargs` assembly (`:1886-1910`) into constructing one `AutomationContext`
- `docs/reference/API.md` — update two hand-maintained Protocol mirrors (`:5769-5785`, `:9173-9188`)
- `scripts/little_loops/__init__.py` — export `AutomationContext` in `__all__` (`:71-90`) alongside `HostInvocation`; `host_runner.py`'s own `__all__` (`:44-67`) gains the name too [Agent 2 finding]

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/schema.py:449-450` — `PruningProfileConfig` docstring mirrors `host_runner.py build_streaming(..., automation_profile=...)` and must cite the collapsed `automation=` parameter [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py:924-934` — threads `idle_timeout` into `_run_claude_base` but **not** `automation_profile` (asymmetry carried forward from today's state)
- `scripts/little_loops/cli/loop/testing.py:73,87` — direct `ActionRunner.run()` calls, no automation kwargs passed
- `scripts/little_loops/workflow_sequence/__init__.py:285` — calls `run_claude_command()`, no automation kwargs
- `scripts/little_loops/cli/generate_skill_descriptions.py:119` — calls `run_claude_command()`, no automation kwargs

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py:2771-2774` — baseline arm calls `run_claude_command(..., idle_timeout=idle_timeout)` directly — a second forwarding site inside an already-modified file, distinct from the `extra_kwargs` assembly at `:1886-1910` [Agent 1 finding]
- `scripts/little_loops/parallel/worker_pool.py:924-934` — the `_run_claude_base(...)` forward currently passes the bare `idle_timeout=` kwarg; becomes `automation=AutomationContext(idle_timeout=...)`, which in turn forces `test_worker_pool.py:2833`'s explicit `mock_run_claude` signature to gain `automation` [Agent 1/3 finding]

### Conventions in Force
- **Frozen dataclass convention**: `HostInvocation` (`host_runner.py:146-164`) docstring explicitly establishes `frozen=True` for value objects crossing runner/caller boundaries; `AutomationContext` follows this rule. (Mutable defaults use `field(default_factory=...)` — not needed here since all three fields are scalar.)
- **Kwarg-gating backward compatibility**: `working_dir`, `automation_profile`, `idle_timeout` are all omitted from `ActionRunner.run()` when unset, so implementations predating each knob keep working — evidence at `fsm/executor.py:1883-1910` and the `test_feat3033_idle_timeout.py:425-466` legacy-runner template. The deprecated pass-through shim builds on this precedent.
- **Protocol explicit signatures**: both `HostRunner` and `ActionRunner` Protocols declare full explicit signatures (no `**kwargs`) — `host_runner.py:216-248`, `fsm/runners.py:39-53`. Every implementation copies the signature verbatim, including stub runners that raise `HostNotConfigured`.
- **Deprecated pass-through shim is net-new**: no production `DeprecationWarning` shim exists in this codebase to copy. The actual warning convention is `warnings.warn(msg, Category, stacklevel=N)` (`CapabilityNotSupported` style, `host_runner.py:108-116`). The `host_runner.py:114-115` docstring claims a `config.core` `DeprecationWarning` precedent, but no `warnings.warn` or `DeprecationWarning` exists anywhere in `config/core.py` — that reference is stale and should not be followed.

### Tests
- `scripts/tests/test_fsm_executor.py:35-118` — `MockActionRunner` (primary mock, explicit `run()` signature), imported by `test_feat3033_idle_timeout.py:28`
- `scripts/tests/test_fsm_executor.py:10946-10985` — `_ContinuityRunner` (inline fake, includes `automation_profile`, no `idle_timeout`)
- `scripts/tests/test_fsm_executor.py:11184-11228` — `_TamperingActionRunner` (inline fake, includes `automation_profile`)
- `scripts/tests/test_fsm_persistence.py:766-792` — `MockActionRunner` (stops at `model`; no `working_dir`/`automation_profile`/`idle_timeout`)
- `scripts/tests/test_usage_journal.py:17-52` — `MockActionRunner` (stops at `model`; no automation kwargs)
- `scripts/tests/test_feat3033_idle_timeout.py:390-467` — kwarg-gating compatibility template; `test_idle_disabled_omits_kwarg_for_old_runners` proves the backward-compat contract
- `scripts/tests/test_subprocess_utils.py:2321-2368` — `test_delegates_to_resolve_host` asserts exact `build_streaming` kwarg set; breaks on any new kwarg
- `scripts/tests/test_host_runner.py:61-82` — `TestAutomationProfileEnvAcrossRunners`, table-driven across 5 real runners; asserts `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` env values
- `scripts/tests/test_issue_manager.py:1390-1435` — `automation_profile` forwarding tests
- `scripts/tests/test_fsm_runners.py:435-600` — patches `run_claude_command`; captures kwargs at `:485`
- `scripts/tests/conftest.py:725-742` — `_CMD_RUN_ENV_VARS` scrub list; must gain any new automation env var (FEAT-3078's `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` is subject to this)
- `scripts/tests/test_runner_spec.py:33-38` — `FakeRunner.build_streaming(**_: object)` — already resilient via `**_`
- `scripts/tests/test_action.py:25-50` — `FakeRunner.build_streaming(**_ : object)` — already resilient via `**_`
- `scripts/tests/test_cli_harness.py:29-38` — `FakeRunner.build_streaming(**_ : object)` — already resilient via `**_`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_worker_pool.py:2833` — `mock_run_claude` has an explicit signature (`idle_timeout: int = 0`, no `**kwargs`); must gain `automation` once `worker_pool.py:924-934` forwards the context [Agent 3 finding]
- `scripts/tests/test_bug3032_wall_clock_cap.py:24,39` — imports `MockActionRunner` from `test_fsm_executor` and drives it with `idle_timeout=60`; updated in lockstep with the shared mock [Agent 3 finding]
- `scripts/tests/test_learning_state.py:46` — `_MockRunner.run()` explicit, no `**kwargs`; safe only if `automation=` stays kwarg-gated (AC-2/LegacyRunner template) [Agent 3 finding]
- `scripts/tests/test_host_runner.py:996-1000` — `TestKimiRunner::test_automation_profile_env` calls `build_streaming(automation_profile=...)` directly; re-pointed at `automation=` (same family as `:61-82`) [Agent 3 finding]
- `scripts/tests/test_host_runner.py` — new `TestAutomationContext` frozen-dataclass check mirroring `TestHostInvocation` (`:1160-1183`); new deprecated-shim test (context-wins + `DeprecationWarning`) following the `pytest.warns` pattern at `:1186-1199` [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` — beyond the three named mocks, ~11 more inline fakes (`FailingRunner:2518`, `ShutdownAfterFirstActionRunner:3351`, `TimeoutCapturingRunner:5261`, `CapturingRunner:6373`, …) declare explicit `run()` signatures with no `**kwargs`; safe only under the AC-2 kwarg-gating contract [Agent 3 finding]

### Documentation
- `docs/reference/API.md:5769-5785` — ActionRunner Protocol mirror (lists `automation_profile`/`idle_timeout` explicitly)
- `docs/reference/API.md:9173-9188` — HostRunner Protocol mirror (lists `automation_profile` only; `idle_timeout` never reaches this layer)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:2626-2655` — a third hand-maintained mirror: `issue_manager.run_claude_command()` wrapper. Already stale today (lists `idle_timeout`, omits the `automation_profile` param that exists at `issue_manager.py:151`); gains `automation` [Agent 2 finding]
- `docs/ARCHITECTURE.md:777` — PruningProfileConfig row explicitly cites `host_runner.py build_streaming(..., automation_profile=...)`; update to the collapsed `automation=` parameter [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:632` — describes the `automation_profile=None` env-signal clearing (ENH-3081); behavior unchanged but references the legacy kwarg — advisory, light-touch [Agent 2 finding]

### Configuration
- `scripts/little_loops/config-schema.json` — `orchestration` object; FEAT-3078 adds `disable_background_tasks` here
- `scripts/little_loops/config/orchestration.py:62-103` — `OrchestrationConfig` dataclass; currently only `host_cli`, `request_path`, `composer`, `cluster` — no `disable_background_tasks` field yet

## Program Design

### Types
`AutomationContext` — a frozen dataclass in `scripts/little_loops/host_runner.py`
(alongside `HostInvocation`), carrying `profile: str | None`,
`idle_timeout: float | None`, `disable_background_tasks: bool`. Frozen so it can
be shared across a call chain without aliasing hazards.

### Signatures

```python
def build_streaming(self, *, prompt: str, working_dir: Path | None = None, resume: bool = False, agent: str | None = None, tools: list[str] | None = None, model: str | None = None, workspace_root: Path | None = None, automation: AutomationContext | None = None) -> HostInvocation
def run(self, action: str, ..., automation: AutomationContext | None = None) -> ActionResult
def _apply_automation_env(env: dict[str, str], automation: AutomationContext | None) -> None
```

- `HostRunner.build_streaming(..., automation: AutomationContext | None = None)`
  replacing the three individual kwargs, with the old names retained as
  deprecated pass-throughs that construct a context.
- `ActionRunner.run(..., automation: AutomationContext | None = None)` —
  same treatment across `DefaultActionRunner` and `SimulationActionRunner`.
- `run_claude_command(..., automation: AutomationContext | None = None)` in both
  `subprocess_utils.py:320` and the `issue_manager.py:139` wrapper.

### Call Path
Unchanged in shape — the refactor narrows what flows through it:
`issue_manager` / `fsm.executor` / `runner_spec` → `run_claude_command` →
`resolve_host().build_streaming()` → `_apply_automation_env()`
(`host_runner.py:1547`), which becomes the context's primary consumer.

### Decision Rules
- Old kwargs are deprecated, not removed — third-party `ActionRunner`
  implementations and the `test_feat3033_idle_timeout.py:390-467` kwarg-gating
  tests must keep passing unmodified.
- When both an `automation` context and a legacy kwarg are supplied, the
  explicit context wins; log a deprecation warning rather than merging.

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/fsm/executor.py:2771-2774` — baseline arm's direct `run_claude_command(idle_timeout=...)` call, a second forwarding site beyond the `extra_kwargs` collapse at `:1886-1910`
- Update `scripts/little_loops/parallel/worker_pool.py:924-934` — replace the bare `idle_timeout=` forward with `automation=AutomationContext(idle_timeout=...)`
- Register `AutomationContext` in `host_runner.py.__all__` (`:44-67`) and re-export from `scripts/little_loops/__init__.py` (`:71-90`)
- Update `scripts/little_loops/fsm/schema.py:449-450` — `PruningProfileConfig` docstring mirror of `build_streaming(..., automation_profile=...)`
- Update `docs/ARCHITECTURE.md:777` and `docs/reference/API.md:2626-2655` (third mirror) alongside the two known API.md Protocol mirrors
- Update `scripts/tests/test_worker_pool.py:2833` and `scripts/tests/test_bug3032_wall_clock_cap.py` for the shared `MockActionRunner` signature change; re-point `test_host_runner.py:996-1000` at `automation=`
- Add `TestAutomationContext` frozen-dataclass test (mirror `TestHostInvocation:1160-1183`) and a deprecated-shim test (context-wins + `DeprecationWarning`, `pytest.warns` pattern at `test_host_runner.py:1186-1199`)

## Acceptance Criteria

1. `AutomationContext` exists and is threaded as a single parameter through
   `build_streaming()`, `run_claude_command()`, and `ActionRunner.run()`.
2. The existing `automation_profile` / `idle_timeout` /
   `disable_background_tasks` keyword arguments still work, constructing a
   context internally.
3. Adding a fourth automation knob requires touching the dataclass and its
   consumers, not 7 runner signatures — demonstrated by a test that passes an
   unknown-to-the-runner context field without a `TypeError`.
4. `docs/reference/API.md` Protocol mirrors updated.
5. `python -m pytest scripts/tests/` passes.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/host_runner.py:1547-1564` | `_apply_automation_env()`, the existing env-side consolidation |
| `.issues/features/P3-FEAT-3078-thread-disable-background-tasks-config-flag-through-host-runner.md` | The third instance that motivated this |
| `scripts/tests/test_feat3033_idle_timeout.py:390-467` | Kwarg-gating compatibility template |


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-07_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 69/100 → MODERATE

### Concerns
- FEAT-3078, the issue this ENH is deliberately sequenced after (Option A, decided by `/ll:decide-issue`), is still `status: Open` — implementing now, before FEAT-3078 lands, effectively reverts to the rejected Option B (validating the deprecated shim against two known consumers instead of three) and hard-codes the BUG-3093 `idle_timeout`-only asymmetry the decision rationale explicitly wanted FEAT-3078 to settle first.
- Criterion 4 (Issue Well-Specified) is capped at 10/20 by the ENH-3047 parity gate: `missing_behavior_parity` is non-empty for `scripts/little_loops/fsm/runners.py`, `scripts/little_loops/host_runner.py`, and `scripts/little_loops/subprocess_utils.py` — none of these three files has a `### Behavior Parity` subsection describing what the collapsed `automation=` parameter replaces.

### Outcome Risk Factors
- Complexity — Breadth scores 0/12: the full site count (7 `build_streaming()` signatures, 4 `ActionRunner` declarations, ~15 test-mock signatures, 2+ doc mirrors) is 16+, so per-site risk is diluted across a wide sweep even though each site's substitution is largely mechanical.
- Change Surface / Fanout Verifiability scores 10/25 (Pattern A, 6-10 callers): `worker_pool.py`, `testing.py`, `workflow_sequence/__init__.py`, `generate_skill_descriptions.py`, and the second `fsm/executor.py:2771-2774` forwarding site each need individual judgment about whether/how the `automation=` context applies — not a uniform regex-style substitution, so a site could be missed silently.

## Session Log
- `/ll:confidence-check` - 2026-08-07T21:55:33 - `e94f284e-432d-4bf1-8e65-a9ce191c682e.jsonl`
- `/ll:verify-issues` - 2026-08-07T21:53:01 - `42a03bea-7711-429c-a09f-f876f3f7e3d8.jsonl`
- `/ll:wire-issue` - 2026-08-07T21:49:12 - `35e6ddfc-4405-4f10-9efb-d6c8092f14b6.jsonl`
- `/ll:decide-issue` - 2026-08-07T21:34:20 - `fd2e53e4-0579-41c7-9ef2-f0d78a3f6c18.jsonl`
- `/ll:refine-issue` - 2026-08-07T21:26:55 - `63949a70-00b3-47fb-a31f-16a9f83204ff.jsonl`

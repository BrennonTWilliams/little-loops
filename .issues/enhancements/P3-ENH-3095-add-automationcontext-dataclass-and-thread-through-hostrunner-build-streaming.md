---
id: ENH-3095
type: ENH
title: Add AutomationContext dataclass and thread it through HostRunner.build_streaming()
priority: P3
status: open
parent: ENH-3094
blocked_by:
- FEAT-3078
- BUG-3112
discovered_date: 2026-08-07
discovered_by: /ll:issue-size-review
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
confidence_score: 98
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
verify_verdict: VALID
reconcile_attempted: true
---

# ENH-3095: Add AutomationContext dataclass and thread it through HostRunner.build_streaming()

## Summary

First of three children decomposed from ENH-3094 (collapse per-call automation
kwargs into a single `AutomationContext`). This child introduces the
`AutomationContext` dataclass itself and threads it through the
`HostRunner.build_streaming()` boundary — the 8 concrete runners
(`ClaudeCodeRunner`, `CodexRunner`, `OpenCodeRunner`, `PiRunner`,
`GeminiRunner`, `OmpRunner`, `KimiRunner`, `QwenRunner`) plus the `HostRunner`
Protocol and `_apply_automation_env()`.

**Two kwargs collapse at this boundary, not one:** `automation_profile`
(ENH-2714) *and* `disable_background_tasks` (FEAT-3078, which landed after this
issue was written and added a second standalone automation kwarg to the
Protocol and all 8 runners). Both become fields of the single `automation`
context. `idle_timeout` — the third `AutomationContext` field — never reaches
this boundary and is carried for signature uniformity only (see Decision
Rules).

This child must land before ENH-3096 (ActionRunner boundary) and ENH-3097
(run_claude_command / caller boundary) — both need to import the
`AutomationContext` type this child defines.

## Current Behavior

`HostRunner.build_streaming()`'s Protocol and all 8 concrete implementations
(`ClaudeCodeRunner`, `CodexRunner`, `OpenCodeRunner`, `PiRunner`,
`GeminiRunner`, `OmpRunner`, `KimiRunner`, `QwenRunner`) accept two bare
automation keywords — `automation_profile: str | None = None` and
`disable_background_tasks: bool = False` — and `_apply_automation_env()` reads
the bare profile string directly to set
`LL_AUTOMATION`/`LL_AUTOMATION_PROFILE`. `ClaudeCodeRunner.build_streaming()`
(`host_runner.py:376`) reads both, gating
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` on
`disable_background_tasks and automation_profile is not None`.

## Expected Behavior

`HostRunner.build_streaming()`'s Protocol and all 8 concrete implementations
accept `automation: AutomationContext | None = None` in place of both
`automation_profile` and `disable_background_tasks`; `_apply_automation_env()`
reads `AutomationContext` fields, and `ClaudeCodeRunner`'s
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` gate reads
`automation.disable_background_tasks` / `automation.profile`. Both
`automation_profile` and `disable_background_tasks` remain deprecated keywords
that construct an `AutomationContext` internally, with a `DeprecationWarning`
emitted when a legacy kwarg is supplied alongside an explicit `automation`
context — in which case the context wins.

## Impact

Without this change, each new per-call automation knob (two at this boundary
today — `automation_profile` from ENH-2714 and `disable_background_tasks`,
which FEAT-3078 has since landed — plus `idle_timeout` one layer up) keeps
paying the fixed toll of touching all 8 `build_streaming()` signatures plus the
Protocol individually. This child
unblocks ENH-3096 (`ActionRunner` boundary) and ENH-3097
(`run_claude_command()` / caller boundary), which both need to import the
`AutomationContext` type defined here.


## Blocks

- ENH-3096
- ENH-3097

## Status

Open — unblocked. FEAT-3078 and BUG-3112 have both landed (`status: done`),
satisfying this issue's `blocked_by`. Per the parent ENH-3094's recorded
decision (Option A, `/ll:decide-issue`, `.ll/decisions.d/cd87607d-e3b2-4588-a697-466559bab1d3.json`),
this collapse was deliberately sequenced after FEAT-3078 so the deprecated
`automation_profile` pass-through shim would be validated against the real
third-knob consumer (`disable_background_tasks`) rather than a hypothetical
one. Ready to implement.

## Parent Issue

Decomposed from ENH-3094: Collapse the per-call automation kwargs into a
single AutomationContext dataclass. See that issue for the full motivation,
sequencing-after-FEAT-3078 decision, and Program Design section (types,
signatures, decision rules) — this child implements the `HostRunner` slice of
that design.

## Scope Boundaries

**In scope:** the `AutomationContext` dataclass; `HostRunner.build_streaming()`
Protocol and all 8 concrete implementations (including `QwenRunner`, added
after this issue was written by EPIC-3154); `_apply_automation_env()`;
`ClaudeCodeRunner`'s `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` gate
(`host_runner.py:376`); the shared `_resolve_automation()` shim helper; the
deprecated `automation_profile` **and `disable_background_tasks`**
pass-throughs at this boundary; doc mirrors that describe `build_streaming()`'s
signature.

**Out of scope:** `ActionRunner.run()` (ENH-3096), `run_claude_command()` and
its callers (ENH-3097), and anything ENH-3094 itself scoped out (the three
knobs' actual behavior, `HostRunner`'s non-automation parameters,
`_apply_automation_env()`'s env semantics).

**Sibling-issue gap (recorded, not fixed here):** neither ENH-3096 nor
ENH-3097 mentions `disable_background_tasks` anywhere — both predate
FEAT-3078's landing. They forward the kwarg today
(`fsm/runners.py:53,122,213,407`, `subprocess_utils.py:359,445`,
`runner_spec.py:131,154,187,197`, `issue_manager.py:152,224,277`) and will need
the same fold-in. Flag on those issues before implementing them; not this
child's job.

## Proposed Solution

```python
@dataclass(frozen=True)
class AutomationContext:
    profile: str | None = None
    idle_timeout: float | None = None
    disable_background_tasks: bool = False
```

Replace **both** the `automation_profile: str | None = None` and
`disable_background_tasks: bool = False` parameters with a single
`automation: AutomationContext | None = None` across the `HostRunner` Protocol
and its 8 implementations, keeping both legacy names as deprecated keywords
that construct an `AutomationContext` internally. When an explicit
`automation` is supplied alongside either legacy kwarg, the context wins and a
deprecation warning is emitted (no existing `DeprecationWarning` shim exists
in this codebase — see parent's Codebase Research Findings; the
`config.core` precedent referenced in `host_runner.py:114-115` is stale).

The shim logic is identical in all 8 runners, so it lives in **one shared
module-level helper** next to `_apply_automation_env()` rather than being
copy-pasted 8 times:

```python
def _resolve_automation(
    automation: AutomationContext | None,
    automation_profile: str | None,
    disable_background_tasks: bool,
) -> AutomationContext | None:
    ...
```

Each `build_streaming()` opens with a single call to it and thereafter reads
only the resolved context.

### Files to Modify
- `scripts/little_loops/host_runner.py` — add `AutomationContext` dataclass
  alongside `HostInvocation`; replace `automation_profile` **and
  `disable_background_tasks`** with `automation: AutomationContext | None` in
  `HostRunner` Protocol `build_streaming` (`:218`, params at `:227-228`) and
  the 8 concrete `build_streaming()` signatures: `ClaudeCodeRunner` (`:314`,
  params `:323-324`), `CodexRunner` (`:616`), `OpenCodeRunner` (`:825`),
  `PiRunner` (`:900`), `GeminiRunner` (`:1012`), `OmpRunner` (`:1209`),
  `KimiRunner` (`:1397`), `QwenRunner` (`:1603`, class at `:1555`, added after
  this issue was written by EPIC-3154); add the shared `_resolve_automation()`
  helper and update `_apply_automation_env()` (`:1819`); update
  `ClaudeCodeRunner`'s `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` gate (`:376-379`)
  to read context fields; register `AutomationContext` in
  `host_runner.py.__all__` (`:44-67`)
- `scripts/little_loops/host_runner.py:44-67` (drive-by) — `__all__` is also
  missing `QwenRunner` today, a pre-existing EPIC-3154 gap in the same list
  this issue already edits. Add it.
- `scripts/little_loops/__init__.py:26,86` — export `AutomationContext`
  alongside `HostInvocation` (both the import block and `__all__`)
- `scripts/little_loops/fsm/schema.py:463-481` — `PruningProfileConfig`
  docstring mirrors `build_streaming(..., automation_profile=...)` at `:463`
  and the shared-gate prose at `:481`; update both to cite `automation=`
- `docs/reference/API.md:9563` — `HostRunner` Protocol mirror (lists both
  `automation_profile` and `disable_background_tasks` explicitly)
- `docs/reference/API.md:9575` — prose under that mirror describing the
  coupled `disable_background_tasks` + `automation_profile is not None` gate;
  rewrite in context terms
- `docs/ARCHITECTURE.md:737-738` — `PruningProfileConfig`/
  `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` rows citing
  `build_streaming(..., automation_profile=...)`
- `docs/guides/LOOPS_GUIDE.md:636-638` — **not light-touch.** `:636` describes
  `automation_profile=None` env-signal clearing (ENH-3081); `:638` explicitly
  documents that `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` "shares the same
  `automation_profile is not None` gate" — that sentence needs a real rewrite
  once both knobs live on one context

**Advisory (semantics prose, verify wording still reads true):**
- `docs/reference/HOST_COMPATIBILITY.md:250` — `[^bgtasks]` footnote, phrased
  as "when `orchestration.disable_background_tasks` is true and
  `automation_profile` is set"
- `docs/reference/CONFIGURATION.md:1236` — `disable_background_tasks` config
  row, same phrasing

Both describe config-level behavior (unchanged by this refactor), so they may
need no edit — but they name the kwarg, so confirm rather than assume.

### Tests
- `scripts/tests/test_host_runner.py:65` — `TestAutomationProfileEnvAcrossRunners`,
  table-driven across the 6 real runners (`:137` list already includes
  `QwenRunner`); re-point at `automation=`
- `scripts/tests/test_host_runner.py:1159` — `TestKimiRunner::test_automation_profile_env`
  (class at `:999`); re-point at `automation=`
- `scripts/tests/test_host_runner.py` — new `TestAutomationContext`
  frozen-dataclass test (mirror `TestHostInvocation` at `:1554`) and
  deprecated-shim tests (context-wins + `DeprecationWarning` for each legacy
  kwarg; `pytest.warns` pattern at `:1266`)
- `scripts/tests/test_host_runner.py` — new empty-context equivalence test:
  `automation=AutomationContext()` must produce byte-identical env to
  `automation=None` for **both** `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` and
  `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` (all `""`), per AC7
- `scripts/tests/conformance/test_host_conformance.py` — exercises
  `resolve_host()` + `build_streaming()` producing a valid `HostInvocation`
  across runners; confirm it passes under the new parameter shape
- `scripts/tests/test_subprocess_utils.py:2322` — `test_delegates_to_resolve_host`
  asserts the exact `build_streaming` kwarg set; update for `automation=`
- `scripts/tests/conftest.py:725-742` — `_CMD_RUN_ENV_VARS` scrub list; confirm
  no new env var is introduced by this child (env semantics are unchanged,
  only the parameter shape)
- `scripts/tests/test_runner_spec.py:33-38`, `scripts/tests/test_action.py:25-50`,
  `scripts/tests/test_cli_harness.py:29-38` — `FakeRunner.build_streaming(**_: object)`;
  verify these stay resilient with no signature change needed

## Acceptance Criteria

1. `AutomationContext` exists as a frozen dataclass (`profile`, `idle_timeout`,
   `disable_background_tasks`) in `scripts/little_loops/host_runner.py` and is
   exported from `host_runner.__all__` and `scripts/little_loops/__init__.py`.
2. `HostRunner.build_streaming()` Protocol and all 8 concrete runners
   (including `QwenRunner`) accept `automation: AutomationContext | None = None`
   in place of **both** `automation_profile` and `disable_background_tasks`.
3. The `automation_profile` and `disable_background_tasks` keywords still work,
   constructing an `AutomationContext` internally via the shared
   `_resolve_automation()` helper; when a legacy kwarg is supplied alongside an
   explicit `automation`, the context wins and a `DeprecationWarning` is
   emitted. Supplying a legacy kwarg *alone* is silent by design — every
   in-tree caller does exactly that until ENH-3097 lands, and warning there
   would flood every `ll-auto` run (see Decision Rules).
4. `_apply_automation_env()` reads `AutomationContext` fields, and
   `ClaudeCodeRunner`'s `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` gate
   (`host_runner.py:376`) reads `automation.disable_background_tasks` /
   `automation.profile` in place of the two bare parameters.
5. `docs/reference/API.md:9563` HostRunner Protocol mirror and its `:9575`
   prose, `docs/ARCHITECTURE.md:737-738`, `docs/guides/LOOPS_GUIDE.md:636-638`,
   and `scripts/little_loops/fsm/schema.py:463-481` updated.
6. `python -m pytest scripts/tests/` passes.
7. `automation=AutomationContext()` (non-`None`, all fields defaulted) produces
   byte-identical child env to `automation=None`: `LL_AUTOMATION=""`,
   `LL_AUTOMATION_PROFILE=""`, and `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=""`.
   The ENH-3081 neutralize-with-`""` contract (never omit the key) holds for
   all three vars.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

### Additional Research Findings
- `scripts/little_loops/config/automation.py` already defines an unrelated `AutomationConfig` (and `ParallelAutomationConfig`) dataclass family for project-level automation settings. The new `AutomationContext` in `host_runner.py` is a distinct, per-call runtime value with no relation to those — worth a docstring note on `AutomationContext` to prevent readers conflating the two similarly-named types.
- `scripts/tests/conformance/test_host_conformance.py` exercises `resolve_host()` + `build_streaming()` producing a valid `HostInvocation` across runners — check this still passes under the new `automation=` parameter shape even though it isn't in the issue's enumerated Tests list.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/runner_spec.py:194-197` — `resolve_host().build_streaming(prompt=prompt, automation_profile=automation_profile, disable_background_tasks=disable_background_tasks)`. A second direct caller of `build_streaming()`'s legacy kwargs, distinct from the out-of-scope `run_claude_command()` path (ENH-3097) — this one calls the Protocol method directly, and passes **both** legacy kwargs (not automation_profile alone). Never paired with `automation=`, so it resolves through the deprecated shim without triggering the new `DeprecationWarning`; no signature break. No dedicated test exercises this line against a real runner — `scripts/tests/test_runner_spec.py` (already in Tests below) always patches `resolve_host` to return `FakeRunner.build_streaming(**_: object)`, a catch-all that stays resilient. No code or test change required here; recorded for wiring completeness only.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

### Types
`AutomationContext(profile: str | None = None, idle_timeout: float | None = None, disable_background_tasks: bool = False)`
- `AutomationContext` (frozen dataclass, `host_runner.py`, alongside `HostInvocation`): `profile: str | None = None`, `idle_timeout: float | None = None`, `disable_background_tasks: bool = False`

### Signatures
Old — `HostRunner.build_streaming()` Protocol and all 8 concrete runners
(**note both automation kwargs**; `disable_background_tasks` was added by
FEAT-3078 after this issue was first written):
`build_streaming(self, *, prompt: str, working_dir: Path | None = None, resume: bool = False, agent: str | None = None, tools: list[str] | None = None, model: str | None = None, automation_profile: str | None = None, disable_background_tasks: bool = False, workspace_root: Path | None = None) -> HostInvocation`

New (legacy kwargs retained as deprecated pass-throughs):
`build_streaming(self, *, prompt: str, working_dir: Path | None = None, resume: bool = False, agent: str | None = None, tools: list[str] | None = None, model: str | None = None, automation: AutomationContext | None = None, automation_profile: str | None = None, disable_background_tasks: bool = False, workspace_root: Path | None = None) -> HostInvocation`

`_apply_automation_env(env: dict[str, str], automation: AutomationContext | None) -> None`

`_resolve_automation(automation: AutomationContext | None, automation_profile: str | None, disable_background_tasks: bool) -> AutomationContext | None`

- Current — `HostRunner.build_streaming()` Protocol (`host_runner.py:218`, automation params at `:227-228`) and all 8 concrete runners share the same two trailing automation parameters at: `ClaudeCodeRunner:314` (params `:323-324`), `CodexRunner:616` (this one also inserts its own `sandbox_mode: str | None = None` between `tools` and `model` — unaffected by this change), `OpenCodeRunner:825`, `PiRunner:900`, `GeminiRunner:1012`, `OmpRunner:1209`, `KimiRunner:1397`, `QwenRunner:1603`.
- New — replace both with `automation: AutomationContext | None = None` in the Protocol and all 8 implementations, keeping the legacy names as deprecated pass-throughs resolved by `_resolve_automation()`.
- `_apply_automation_env(env: dict[str, str], automation_profile: str | None) -> None` (`host_runner.py:1819`) becomes `_apply_automation_env(env: dict[str, str], automation: AutomationContext | None) -> None`, reading `automation.profile` in place of the bare string — `automation is None` and `automation.profile is None` both take the existing "write `""`, not absent" opt-out branch.
- `_resolve_automation()` is new, module-level, and lives beside `_apply_automation_env()`. It exists so the deprecation shim is written once rather than duplicated verbatim across 8 runners. Returns `None` when neither an explicit context nor any legacy kwarg is supplied (preserving today's `automation=None` opt-out path); otherwise returns the explicit context if given, else `AutomationContext(profile=automation_profile, disable_background_tasks=disable_background_tasks)`.
- `ClaudeCodeRunner`'s `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` gate (`host_runner.py:376-379`) currently reads `if disable_background_tasks and automation_profile is not None:` and becomes `if automation is not None and automation.disable_background_tasks and automation.profile is not None:`; the `else:` branch still writes `""`. This is the only runner that reads `disable_background_tasks` — the other 7 accept and ignore it, so their change is compile-only for that field.

### Call Path
`subprocess_utils.run_claude_command()` (`:444-445`) -> `runner.build_streaming(..., automation=...)` -> the 6 real runners each call `_apply_automation_env(env, automation)` (`:369` Claude, `:672` Codex, `:1066` Gemini, `:1253` Omp, `:1448` Kimi, `:1647` Qwen) -> sets `env["LL_AUTOMATION"]`/`env["LL_AUTOMATION_PROFILE"]` from `automation.profile`. `ClaudeCodeRunner` additionally reads `automation.disable_background_tasks` at `:376` for `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`. `OpenCodeRunner`/`PiRunner` never reach `_apply_automation_env()` — both raise `HostNotConfigured` before touching any parameter, so their signature change is compile-only.

### Decision Rules
- Deprecated-kwarg shim: `automation_profile: str | None = None` **and `disable_background_tasks: bool = False`** stay as parameters on the Protocol and all 8 implementations. If `automation` is `None` and either legacy kwarg is non-default, construct `AutomationContext(profile=automation_profile, disable_background_tasks=disable_background_tasks)` internally. If an explicit `automation` is supplied alongside either legacy kwarg, the context wins and a `DeprecationWarning` is emitted via `warnings.warn(..., DeprecationWarning, stacklevel=2)`. No existing `DeprecationWarning` shim exists anywhere in `scripts/little_loops/` to copy — confirmed by direct search; `host_runner.py:114-115`'s docstring reference to a `config.core` precedent is stale (zero `warnings.warn`/`DeprecationWarning` occurrences in `config/core.py`). Do not reuse `CapabilityNotSupported(UserWarning)` (`host_runner.py:108-116`) for this — that class is reserved for host-capability mismatches (unsupported `agent`/`tools`/`workspace_root`), a semantically distinct case the parent's findings explicitly flag as not to be confused with this shim.
- **Why the warning is conflict-only, not use-of-legacy-kwarg:** every in-tree caller of `build_streaming()` passes only the legacy kwargs today — `runner_spec.py:186-187` and `subprocess_utils.py:444-445` — and keeps doing so until ENH-3097 migrates them. Warning on plain legacy use would therefore fire on every `ll-auto` / FSM-loop invocation for the life of two follow-up issues while signalling nothing actionable at the call site. `scripts/pyproject.toml` sets no `filterwarnings = error`, so an always-warn variant would not fail the suite — the objection is log noise, not test breakage. Consequence to accept: this `DeprecationWarning` will not fire from any production path until ENH-3097 lands, so it is exercised only by the dedicated unit test. Note also that what it actually signals is *parameter conflict*, not deprecation; the warning message should say so explicitly.
- **Removal milestone:** the shim has no removal trigger as written, which makes it permanent by default. Drop both legacy kwargs from the Protocol and all 8 runners once ENH-3097 lands and no in-tree caller passes them — file that as a follow-up cleanup issue when this child is implemented, or state here that the shim is intentionally permanent for third-party `HostRunner` implementations.
- `automation_profile=None` / `automation=None` remains an active opt-out (writes `LL_AUTOMATION=""`, not an absent key) — this ENH-3081 semantic is unchanged; only the parameter shape changes. The same neutralize-with-`""` contract applies to `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` (`host_runner.py:379`) and must survive the fold-in — see AC7.
- **`idle_timeout` is carried, never consumed, at this boundary.** It is `AutomationContext`'s third field but never reaches `build_streaming()` or `_apply_automation_env()`: it is consumed entirely in `subprocess_utils.py:513` (selector loop, kills with `output="idle_timeout"`) and the shell/mcp selector loops in `fsm/runners.py` / `fsm/executor.py`. Do not wire it into `_apply_automation_env()` or any runner — the context is a carrier for this field, and it becomes live only at the ENH-3096 boundary.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.issues/enhancements/P3-ENH-3094-collapse-per-call-automation-kwargs-into-automationcontext.md` | Parent issue — full motivation, Program Design, decision rationale |
| `scripts/little_loops/host_runner.py:1547-1564` | `_apply_automation_env()`, the existing env-side consolidation |
| `scripts/tests/test_feat3033_idle_timeout.py:390-467` | Kwarg-gating compatibility template |

## Verification Notes

**2026-08-19** (`/ll:verify-issues`): `AutomationContext` still doesn't exist
in `host_runner.py`; core claim holds. `blocked_by` (FEAT-3078, BUG-3112) and
parent ENH-3094 all confirmed `status: done` — issue is genuinely unblocked.

**2026-08-19** (pre-implementation review): resolved the blocking scope gap
below and refreshed anchors. Findings folded into the body:
- **Blocker (now fixed in-body):** `disable_background_tasks` (FEAT-3078) is a
  standalone `build_streaming()` kwarg on the Protocol and all 8 runners
  (`host_runner.py:228`, `:324`, …), but the issue's Program Design listed it
  in *neither* the Old nor the New signature — implementing literally would
  have deleted a shipped parameter. It is also `AutomationContext` field #3.
  Now folded into `automation` throughout, per parent ENH-3094's intent.
- **Sibling gap (not fixed):** ENH-3096 and ENH-3097 have zero mentions of
  `disable_background_tasks`. Recorded under Scope Boundaries; flag on those
  issues before implementing them.
- Added the shared `_resolve_automation()` helper so the shim isn't duplicated
  8×; added AC7 (empty-context ≡ `None` for all three env vars); documented
  why the `DeprecationWarning` is conflict-only and that it has no removal
  milestone.
- Fixed AC5, which cited `ARCHITECTURE.md:777` / `LOOPS_GUIDE.md:632` while
  Files to Modify (already refreshed) cited `:737-738` / `:636-638`.
- Refreshed test anchors: `TestKimiRunner::test_automation_profile_env` is at
  `:1159` (was cited `:996-1000`, which is the class decl); `TestHostInvocation`
  at `:1554` (was `:1160-1183`); `pytest.warns` template near `:1266`.
  Production anchors in Files to Modify were all verified correct.
- Added `docs/reference/API.md:9575`, `HOST_COMPATIBILITY.md:250`,
  `CONFIGURATION.md:1236`, and the conformance test to the affected lists;
  noted `LOOPS_GUIDE.md:638` is a real rewrite, not a light touch.
- Drive-by: `host_runner.__all__` (`:44-67`) is missing `QwenRunner` — a
  pre-existing EPIC-3154 gap in the same list AC1 already edits.

**Scope gap (RESOLVED 2026-08-19 — kept for history):** EPIC-3154 (commit `2ac04c4a`, "feat(host): add Qwen
Code host adapter") landed an **8th concrete `HostRunner` implementation**,
`QwenRunner` (`host_runner.py:1555`), after this issue was written. It has
the same `automation_profile: str | None = None` trailing parameter and the
same `_apply_automation_env(env, automation_profile)` call
(`host_runner.py:1647`) as the other 7 runners. `scripts/tests/test_host_runner.py`'s
`TestAutomationProfileEnvAcrossRunners` table already includes `QwenRunner`
alongside the other 5 real (non-`HostNotConfigured`) runners. This issue's
Scope Boundaries, Files to Modify, Acceptance Criteria (1-2), Program Design
Signatures, and Call Path sections all still enumerate only 7 runners and
would need `QwenRunner` added throughout before implementation — a real
content gap, not merely a citation drift.

**Line-number drift (also needs refresh, secondary to the scope gap above):**
every cited anchor in Files to Modify / Program Design has moved further
since the 2026-08-10 pass (drift now up to ~270 lines, not ~15-35):
- `host_runner.py` Protocol `build_streaming` now at `:218` (was cited
  `:216-227`, consistent)
- `ClaudeCodeRunner.build_streaming` now at `:314` (cited `:299-310`)
- `CodexRunner.build_streaming` now at `:616` (cited `:590-602`)
- `OpenCodeRunner.build_streaming` now at `:825` (cited `:797-808`)
- `PiRunner.build_streaming` now at `:900` (cited `:871-882`)
- `GeminiRunner.build_streaming` now at `:1012` (cited `:982-993`)
- `OmpRunner.build_streaming` now at `:1209` (cited `:1177-1188`)
- `KimiRunner.build_streaming` now at `:1397` (cited `:1363-1374`)
- `_apply_automation_env` now at `:1819` (cited `:1547-1564`/`:1547`)
- `docs/reference/API.md` HostRunner Protocol mirror now at `:9563` (cited
  `:9173-9188`)
- `docs/ARCHITECTURE.md` `PruningProfileConfig`/`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`
  rows now at `:737-738` (cited `:777`)
- `docs/guides/LOOPS_GUIDE.md` automation-profile prose now at `:636-638`
  (cited `:632`)
- `scripts/little_loops/fsm/schema.py` `PruningProfileConfig` docstring
  mirror now at `:463-481` (cited `:449-450`)

Also note: parent ENH-3094's frontmatter says `status: done` but its own body
'## Status' section still says open — a stale self-contradiction on the
parent, doesn't affect this issue's validity.

Remedy: **done** — `QwenRunner` and the refreshed anchors were applied in the
2026-08-19 review pass above. No further refine/reconcile needed before
implementation.

**2026-08-19** (`/ll:verify-issues --check`): Re-checked every anchor. All
`host_runner.py` production citations (Protocol `:218`/params `:227-228`, all
8 `build_streaming()` defs, `_apply_automation_env` `:1819`, the
`ClaudeCodeRunner` gate `:376`, `__all__` `:44-67` missing `QwenRunner`) and
all doc citations (`API.md:9563/9575`, `ARCHITECTURE.md:737-738`,
`LOOPS_GUIDE.md:636-638`, `schema.py:463-481`) confirmed accurate.
`blocked_by`/parent all confirmed `status: done`; backlinks on ENH-3096/
ENH-3097 confirmed present. One drift found and fixed: Dependent Files cited
`runner_spec.py:182` for the `build_streaming()` call, which is actually at
`:194-197` and passes **both** `automation_profile` and
`disable_background_tasks` (the prior note said "only `automation_profile`").
Corrected in place. Verdict: `NEEDS_UPDATE` (now resolved).

## Session Log
- `/ll:verify-issues` - 2026-08-20T00:50:31 - `0c36abcb-97ca-4d1b-a837-bc5e77cc1b2c.jsonl`
- `/ll:confidence-check` - 2026-08-20T00:35:51 - `319ac0b1-cd90-4d0c-9495-41a3d1945bec.jsonl`
- `/ll:reconcile-issue` - 2026-08-20T00:29:25 - `202a6ed4-bed9-4c2b-b275-e850f1beb7fe.jsonl`
- `/ll:verify-issues` - 2026-08-20T00:22:49 - `edca6765-bded-4cd4-bbe9-b026c21cad5e.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:10 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:26:27 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-09T03:26:27 - `39a3fd52-4ea1-4f7e-83e9-1871820dfe65.jsonl`
- `/ll:ready-issue` - 2026-08-09T02:52:47 - `6431dd81-8b40-4678-a555-981e5457f142.jsonl`
- `/ll:confidence-check` - 2026-08-09T01:59:07 - `9b3b8077-be68-4765-a354-0d51ab3b4859.jsonl`
- `/ll:wire-issue` - 2026-08-09T01:55:13 - `963d0bbe-3f49-4745-8100-971274145bbd.jsonl`
- `/ll:refine-issue` - 2026-08-07T22:51:21 - `596f76ed-c393-479b-9539-adbce5a6a72b.jsonl`
- `/ll:issue-size-review` - 2026-08-07T22:09:43 - `dec986a1-15de-4376-b5dd-5868a8d3e188.jsonl`

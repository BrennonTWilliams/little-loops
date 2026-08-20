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
relates_to:
- FEAT-3078
- FEAT-3033
- ENH-2714
- BUG-3093
verify_verdict: NON_VALID
---

# ENH-3097: Thread AutomationContext through run_claude_command() and its callers

## Summary

Third of three children decomposed from ENH-3094. This child threads the
`AutomationContext` dataclass (introduced in ENH-3095) through
`run_claude_command()` in both `subprocess_utils.py` and the
`issue_manager.py` wrapper, `run_with_continuation()`, `runner_spec.py`'s
forwarding sites, and the two remaining direct-call sites
(`fsm/executor.py`'s baseline arm,
<!-- ll-prose-ok: _run_claude_base is a local import alias (`run_claude_command as _run_claude_base`), not a def-site symbol -->
`worker_pool.py:_run_claude_base`).

**Blocked by ENH-3095**: this child imports `AutomationContext` from
`host_runner.py`, which ENH-3095 defines. Can proceed in parallel with
ENH-3096 once ENH-3095 lands — they touch disjoint files except for a shared
edit to `fsm/executor.py` (different line ranges: this child touches the
baseline arm's direct call at `:2771-2774`; ENH-3096 touches the
`extra_kwargs` assembly at `:1886-1910`).

## Parent Issue

Decomposed from ENH-3094: Collapse the per-call automation kwargs into a
single AutomationContext dataclass. See that issue for full motivation,
sequencing decision, and Program Design section — this child implements the
`run_claude_command()` / caller slice of that design.

## Scope Boundaries

**In scope:** `run_claude_command()` in `subprocess_utils.py` and
`issue_manager.py`; `run_with_continuation()`; `runner_spec.py`'s forwarding
sites; `fsm/executor.py:2771-2774` (baseline arm direct call); the bare
`idle_timeout=` forward in `worker_pool.py:924-934`; the
`docs/reference/API.md` `issue_manager.run_claude_command()` mirror.

**Out of scope:** `HostRunner.build_streaming()` (ENH-3095, a dependency);
`ActionRunner.run()` and `fsm/executor.py`'s `extra_kwargs` assembly
(ENH-3096). Fixing the BUG-3093 `idle_timeout`-only asymmetry at
`issue_manager.py:826,893,1089` is explicitly **not** this issue's job (per
parent's Codebase Research Findings) — this child only changes the parameter
shape those call sites use, it does not add the missing `automation_profile`
argument.

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
  `automation` in `run_claude_command()` (`:320-341`); `idle_timeout` is
  consumed locally at `:478` (selector loop), unaffected by this shape change
- `scripts/little_loops/issue_manager.py` — same in wrapper
  `run_claude_command()` (`:139-152`) and `run_with_continuation()` (`:252-269`)
- `scripts/little_loops/runner_spec.py` — update `automation_profile` read
  (`:128`) and forwarding sites (`:145,176,182`)
- `scripts/little_loops/fsm/executor.py:2771-2774` — baseline arm's direct
  `run_claude_command(idle_timeout=...)` call; becomes
  `automation=AutomationContext(idle_timeout=...)`
- `scripts/little_loops/parallel/worker_pool.py:924-934` — replace the bare
  `idle_timeout=` forward with `automation=AutomationContext(idle_timeout=...)`
- `docs/reference/API.md:2626-2655` — `issue_manager.run_claude_command()`
  wrapper mirror (already stale today — lists `idle_timeout`, omits the
  `automation_profile` param that exists at `issue_manager.py:151`; gains
  `automation`)

### Tests
- `scripts/tests/test_issue_manager.py:1390-1435` — `automation_profile`
  forwarding tests
- `scripts/tests/test_worker_pool.py:2833` — `mock_run_claude` has an explicit
  signature (`idle_timeout: int = 0`, no `**kwargs`); gains `automation`
- `scripts/tests/test_runner_spec.py:33-38` — `FakeRunner.build_streaming(**_: object)`;
  verify this stays resilient with no signature change needed

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **Sixth call site not in original scope — `fsm/runners.py`'s `DefaultActionRunner.run()`** (ENH-3096's completed work): at `runners.py:177-183` it already calls the shared `resolve_automation()` helper (see below), then explicitly **decomposes the resolved context back into legacy kwargs** at `runners.py:187-191` before calling `run_claude_command()` at `runners.py:234-252`. A comment at `runners.py:184-186` reads: "`run_claude_command()` has no `automation=` parameter until ENH-3097, so decompose the resolved context back into legacy kwargs for that forwarding call ... below." This decomposition is the exact seam this issue closes — once `run_claude_command()` accepts `automation:`, this call site should pass `automation=automation` directly instead of decomposing. Add `fsm/runners.py:187-252` to Files to Modify.
- **A reusable shim helper already exists and should be called, not reimplemented**: `resolve_automation(automation, automation_profile, disable_background_tasks, idle_timeout, *, caller="build_streaming()")` at `host_runner.py:1886-1934`. It implements exactly the Decision Rules behavior this issue specifies (explicit `automation=` wins and warns via `DeprecationWarning` naming `caller` when legacy kwargs are also present; legacy-alone builds `AutomationContext(...)` silently — no warning; neither given returns `None`). It is already consumed by `fsm/runners.py:177-183` (`caller="ActionRunner.run()"`) and should be the shim this issue's five/six call sites call, rather than each site reimplementing the fold inline.
- **Third field also collapses into `automation=`**: `disable_background_tasks: bool = False` is a field on `AutomationContext` (`host_runner.py:172-190`) alongside `profile`/`idle_timeout`, and is present as a legacy kwarg at every in-scope call site — not just the `automation_profile`/`idle_timeout` pair this issue's Proposed Solution text names. Note: `worker_pool.py`'s `_run_claude_base` forward (`worker_pool.py:940-952`) already passes `disable_background_tasks=` but has no `automation_profile=` kwarg at all — a pre-existing asymmetry to preserve (not fix) when threading `automation=` through that site.

## Acceptance Criteria

1. `run_claude_command()` in both `subprocess_utils.py` and
   `issue_manager.py`, plus `run_with_continuation()`, accept
   `automation: AutomationContext | None = None` in place of
   `automation_profile`/`idle_timeout`.
2. `runner_spec.py`'s read (`:128`) and forwarding sites (`:145,176,182`)
   updated to the collapsed parameter.
3. `fsm/executor.py:2771-2774` and `worker_pool.py:924-934` construct and
   forward an `AutomationContext` instead of a bare `idle_timeout=` kwarg.
4. The `automation_profile`/`idle_timeout` keywords still work, constructing
   an `AutomationContext` internally, per the ENH-3095 shim pattern.
5. `docs/reference/API.md` `issue_manager.run_claude_command()` mirror
   updated.
6. `python -m pytest scripts/tests/` passes.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

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
- **`AutomationContext` has no alternate constructor** — plain `@dataclass(frozen=True)` at `host_runner.py:172-190` with `profile: str | None = None`, `idle_timeout: float | None = None`, `disable_background_tasks: bool = False`. No `from_legacy()` classmethod exists; construction is always `AutomationContext(profile=..., idle_timeout=..., disable_background_tasks=...)` or via `resolve_automation()`.
- **`fsm/runners.py:177-191` (`DefaultActionRunner.run()`) is the seam this issue closes**: already calls `resolve_automation(automation, automation_profile, disable_background_tasks, float(idle_timeout) if idle_timeout else None, caller="ActionRunner.run()")` at `:177-183`, then decomposes the result back to `resolved_automation_profile`/`resolved_disable_background_tasks`/`resolved_idle_timeout` at `:187-191` (using `int(automation.idle_timeout or 0)` for the timeout — another `0`/`None` collapse point matching the pattern this issue's existing Decision Rules bullet already warns against at its own five sites) purely because `run_claude_command()` doesn't accept `automation=` yet. Once it does, this decomposition should be replaced with a direct `automation=automation` forward at the `run_claude_command()` call spanning `runners.py:234-252`.

### Types
- Imports `AutomationContext` from `host_runner.py` (defined by ENH-3095, not yet landed — this issue is `blocked_by: [ENH-3095]`).

### Signatures
Old — `run_claude_command()` (`subprocess_utils.py` and the `issue_manager.py` wrapper share this shape):
`run_claude_command(command: str, timeout: int = 3600, working_dir: Path | None = None, idle_timeout: int = 0, automation_profile: str | None = None) -> subprocess.CompletedProcess[str]`

New:
`run_claude_command(command: str, timeout: int = 3600, working_dir: Path | None = None, automation: AutomationContext | None = None) -> subprocess.CompletedProcess[str]`

- Current, each declaring an independent `automation_profile: str | None = None` / `idle_timeout: int = 0` (or `int` positional-equivalent) pair: `subprocess_utils.run_claude_command()` (`:320-341`); `issue_manager.run_claude_command()` wrapper (`:139-152`); `issue_manager.run_with_continuation()` (`:252-269`).
- New — each becomes `automation: AutomationContext | None = None` in place of the pair.
- `runner_spec.py`'s `_run_skill` reads `automation_profile` out of the untyped `spec.args: dict[str, Any]` (`:124-128`, `spec.args.get("automation_profile")`) — the only one of these sites where the value arrives via dict lookup rather than a named parameter; becomes reading/constructing an `AutomationContext` the same way. `idle_timeout` is not threaded through `runner_spec.py` today (no `spec.args.get("idle_timeout")` anywhere in `_run_skill`) and this issue does not add it.

### Call Path
- `subprocess_utils.py:402-411` — `automation_profile` forwarded to `runner.build_streaming(automation_profile=...)` becomes `build_streaming(automation=automation)`, consuming ENH-3095's boundary.
- `subprocess_utils.py:478-487` — `idle_timeout` consumed locally by the selector loop (`if idle_timeout and (now - last_output_time) > idle_timeout: raise TimeoutExpired(..., output="idle_timeout")`), never reaches `build_streaming()`; the read becomes `automation.idle_timeout if automation else 0` at this same site, loop logic unchanged.
<!-- ll-prose-ok: _run_claude_base is a local import alias (`run_claude_command as _run_claude_base`), not a def-site symbol -->
- `issue_manager.py` wrapper (`:207-218`) forwards 1:1 to `issue_manager.py:_run_claude_base` (`subprocess_utils.run_claude_command`, imported alias) — becomes a 1:1 forward of `automation=automation`.
- `issue_manager.run_with_continuation()` (`:340-350`) forwards to the wrapper on every continuation round — same collapse, same forwarding shape.
- `runner_spec.py` three forwarding sites: trace mode (`:140-149`, calls `run_claude_command`), stream_callback mode (`:172-177`, calls `run_claude_command`), and blocking/default mode (`:182`, calls `resolve_host().build_streaming()` directly, bypassing `run_claude_command()` entirely) — each currently passes bare `automation_profile=automation_profile`; each becomes `automation=automation`.
- `fsm/executor.py:2771-2778` baseline arm — currently passes only `idle_timeout=idle_timeout` (no `automation_profile` at all today) — becomes `automation=AutomationContext(idle_timeout=idle_timeout)`.
- `worker_pool.py:924-934` `_run_claude_base` forward — currently passes only `idle_timeout=self.parallel_config.idle_timeout_per_issue` (no `automation_profile` today) — becomes `automation=AutomationContext(idle_timeout=self.parallel_config.idle_timeout_per_issue)`.

### Decision Rules
- Same shim pattern as ENH-3095/ENH-3096: legacy `automation_profile`/`idle_timeout` keywords still work, constructing an `AutomationContext` internally; explicit `automation` wins when both given; deprecation warning logged.
- Explicitly out of scope, restated here so the shim isn't conflated with a fix: BUG-3093's `idle_timeout`-only asymmetry at `issue_manager.py:826,893,1089` (call sites passing `idle_timeout` but never `automation_profile`) — this issue changes only the *parameter shape* those sites use (`idle_timeout=` kwarg -> `automation=AutomationContext(idle_timeout=...)`); it does not add a missing `profile=` argument to close that asymmetry.
- `AutomationContext.idle_timeout` is `float | None` (ENH-3095) versus the `int = 0` parameters across this issue's five call sites — the internal shim construction (`AutomationContext(idle_timeout=idle_timeout)`) must preserve `0` (explicitly disabled) as distinct from `None` (unset), not collapse `0` to `None` via a falsy check.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.issues/enhancements/P3-ENH-3094-collapse-per-call-automation-kwargs-into-automationcontext.md` | Parent issue — full motivation, Program Design, decision rationale |
| `.issues/enhancements/P3-ENH-3095-add-automationcontext-dataclass-and-thread-through-hostrunner-build-streaming.md` | Dependency — defines `AutomationContext` |
| `.issues/bugs/*BUG-3093*` (if present) | Related asymmetry at `issue_manager.py:826,893,1089` — explicitly out of scope here |

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

## Session Log
- `/ll:verify-issues` - 2026-08-20T00:59:29 - `e89696fe-140c-45df-a34b-1cf937e9f43c.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:10 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:26:27 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-09T03:26:27 - `39a3fd52-4ea1-4f7e-83e9-1871820dfe65.jsonl`
- `/ll:refine-issue` - 2026-08-07T22:51:22 - `596f76ed-c393-479b-9539-adbce5a6a72b.jsonl`
- `/ll:issue-size-review` - 2026-08-07T22:09:44 - `dec986a1-15de-4376-b5dd-5868a8d3e188.jsonl`

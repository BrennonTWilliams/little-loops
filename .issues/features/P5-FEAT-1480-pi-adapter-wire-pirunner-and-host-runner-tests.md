---
id: FEAT-1480
title: Pi Adapter — Wire PiRunner and Host Runner Tests
type: FEAT
priority: P5
status: open
parent: EPIC-1622
relates_to: FEAT-1476
depends_on: [FEAT-1714]
---

# FEAT-1480: Pi Adapter — Wire PiRunner and Host Runner Tests

## Summary

Implement `PiRunner.build_*` methods in `host_runner.py` (replacing the `HostNotConfigured` stubs), update `HostCapabilities` to reflect Pi's actual capability set, and write the associated host runner and hook-intents tests.

## Parent Issue

Decomposed from FEAT-1477: Pi Adapter — Python Backend: Config, Host Runner, Schema, and Tests

## Acceptance Criteria

- `scripts/little_loops/host_runner.py` `PiRunner.build_streaming()`, `build_blocking_json()`, `build_detached()`, and `build_version_check()` are wired (no longer raise `HostNotConfigured`); `HostCapabilities` updated as appropriate
- All host runner Pi tests pass: `python -m pytest scripts/tests/test_host_runner.py -k pi`
- Hook-intents Pi propagation test passes: `python -m pytest scripts/tests/test_hook_intents.py -k pi`
- No regressions in existing Claude Code, OpenCode, or Codex test suites

## Proposed Solution

### Step 1: Confirm CodexRunner Template

Review `CodexRunner` at `host_runner.py` lines 270–418 as the direct template. Note:
- `CodexRunner.capabilities` at lines 300–305: `HostCapabilities(streaming=True, permission_skip=True, agent_select=False, tool_allowlist=False)` — evaluate against Pi's CLI flags before copying
- Run `pi --help` first to verify Pi CLI supports streaming JSON output and a bypass-approvals flag before setting `HostCapabilities` identically to Codex

### Step 2: Wire PiRunner

In `scripts/little_loops/host_runner.py` at `PiRunner` class (lines ~478–532):
- Replace all four `build_*` methods that raise `HostNotConfigured("Pi orchestration not yet wired — see FEAT-992...")` with actual command construction, following `CodexRunner` as the template
- Update `HostCapabilities()` flags to reflect Pi's actual capability set
- `detect()` already returns `shutil.which("pi") is not None` — verify it's correct (no change expected)

**Important**: `("pi", "pi")` is already in `_PROBE_ORDER` (unlike CodexRunner which is gated). Wiring `build_*` immediately activates Pi for any environment with `pi` on PATH. Run the full test suite with `pi` absent from PATH to confirm no inadvertent routing regressions.

### Step 3: Write Host Runner and Hook-Intents Tests

- `scripts/tests/test_host_runner.py:TestPiRunner` (~lines 337–392) — replace 4 `pytest.raises(HostNotConfigured, match="FEAT-992")` assertions with argv-snapshot tests following `TestCodexRunner` as template; update `test_pirunner_probe_returns_stub_not_raise` (~line 357) — remove the `HostNotConfigured` assertion and replace with an argv snapshot (e.g. `assert invocation.binary == "pi"`) following `test_codex_runner_flag_translation` at line 194
- `scripts/tests/test_hook_intents.py:TestHooksMainModule` (~line 359) — add `test_ll_hook_host_env_var_propagates_pi` after the codex variant

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — `PiRunner` class at lines 478–532; `CodexRunner` at lines 270–418 is the direct template

### Test Files
- `scripts/tests/test_host_runner.py:337` — `TestPiRunner` (lines 337–393); four `match="FEAT-992"` raises to replace
- `scripts/tests/test_hook_intents.py:359` — `TestHooksMainModule`; `test_ll_hook_host_env_var_propagates_codex` is the template

### Test Templates
- `scripts/tests/test_host_runner.py:165` — `TestCodexRunner`; `test_codex_runner_flag_translation` at line 194 is the canonical argv-snapshot form
- `scripts/tests/test_hook_intents.py:359` — `test_ll_hook_host_env_var_propagates_codex` in `TestHooksMainModule`

### Dependent Files (Transparent Beneficiaries)
- `scripts/little_loops/subprocess_utils.py` — calls `resolve_host().build_streaming()` at line 263; works automatically
- `scripts/little_loops/cli/action.py` — calls `resolve_host().build_version_check()` at line 149
- `scripts/little_loops/parallel/worker_pool.py` — calls `resolve_host().build_blocking_json()` at line 576
- `scripts/little_loops/fsm/evaluators.py` — calls `resolve_host().build_blocking_json()` at line 609
- `scripts/little_loops/fsm/handoff_handler.py` — calls `resolve_host().build_detached()` at line 116

## Codebase Research Notes

- `PiRunner.detect()` at `host_runner.py:493` already correctly returns `shutil.which("pi") is not None` — no change needed
- `PiRunner` is already registered and in `_PROBE_ORDER` — auto-detects immediately once `build_*` is wired
- `test_opencode_runner_gated_from_auto_probe` is NOT needed for Pi since Pi is intentionally in `_PROBE_ORDER`

## Impact

- **Priority**: P5
- **Effort**: Small–Medium
- **Risk**: Low — additive; no changes to existing host logic. Pi auto-activates on PATH detection once wired.

## Status

**Open** | Created: 2026-05-15 | Priority: P5

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-18): This issue modifies `host_runner.py` to wire `PiRunner` (lines 478–532). ENH-1529 also modifies `host_runner.py` to add `_sandbox_args()` and thread `sandbox_mode` through `CodexRunner` (lines 270–418). The two changes target different class regions and are non-overlapping, but landing both PRs simultaneously on the same file can produce near-miss merge conflicts during rebase. Sequence or merge these PRs deliberately; review both diff hunks together before landing.

## Session Log
- `/ll:verify-issues` - 2026-05-31T02:30:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:verify-issues` - 2026-05-23T00:35:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2955f8fa-d24c-40f9-9d2d-3d46811662f9.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-18T05:05:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/16717e5e-bfe4-4e7f-8d36-177b4b791f2d.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-17T18:46:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ebf7abce-1ef1-46c8-8cbc-56d9f857d730.jsonl`
- `/ll:issue-size-review` - 2026-05-15T20:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e9b11ad-de12-4f82-9761-25c38e59c783.jsonl`

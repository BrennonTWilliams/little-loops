---
id: FEAT-1477
type: FEAT
priority: P5
status: done
parent: FEAT-1474
confidence_score: 100
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
size: Very Large
completed_at: 2026-05-15T00:00:00Z
---

# FEAT-1477: Pi Adapter — Python Backend: Config, Host Runner, Schema, and Tests

## Summary

Wire the Python backend for Pi Coding Agent support: add `PI_CONFIG_DIR` constant and `_config_candidates()` branch in `config/core.py`, implement `PiRunner.build_*` methods in `host_runner.py`, add `"pi"` to `config-schema.json`'s `hooks.properties.host.enum`, and write all associated Python tests.

## Parent Issue

Decomposed from FEAT-1474: Pi Adapter Core — TypeScript Adapter, Config Candidate, Schema, and Tests

## Acceptance Criteria

- `scripts/little_loops/config/core.py` has `PI_CONFIG_DIR = ".pi"` constant (after `CODEX_CONFIG_DIR`) and an `elif host == "pi" or state_dir == PI_CONFIG_DIR:` branch in `_config_candidates()`
- `scripts/little_loops/host_runner.py` `PiRunner.build_streaming()`, `build_blocking_json()`, `build_detached()`, and `build_version_check()` are wired (no longer raise `HostNotConfigured`); `HostCapabilities` updated as appropriate
- `config-schema.json` includes `"pi"` in `hooks.properties.host.enum` (note: `orchestration.host_cli` already has `"pi"` — this resolves the inconsistency)
- All Python tests pass: `python -m pytest scripts/tests/ -k pi`
- No regressions in existing Claude Code, OpenCode, or Codex test suites

## Proposed Solution

### Step 1: Confirm FEAT-957 Template

Verify `hooks/adapters/codex/` exists and `_config_candidates()` in `config/core.py` has the `codex` branch — use as template.

### Step 2: Add Pi Config Candidate

In `scripts/little_loops/config/core.py` (~line 36), add after `CODEX_CONFIG_DIR = ".codex"`:
```python
PI_CONFIG_DIR = ".pi"
```

In `_config_candidates()` (~lines 84-88), add branch mirroring the codex branch:
```python
elif host == "pi" or state_dir == PI_CONFIG_DIR:
    candidates.append(project_root / PI_CONFIG_DIR / CONFIG_FILENAME)
```

Also update `OrchestrationConfig` docstring: remove `"pi" (reserved for FEAT-992)` annotation.

### Step 3: Wire PiRunner

In `scripts/little_loops/host_runner.py` at `PiRunner` class (lines ~478–532):
- Replace all four `build_*` methods that raise `HostNotConfigured("Pi orchestration not yet wired — see FEAT-992...")` with actual command construction, following `CodexRunner` as the template.
- Update `HostCapabilities()` flags to reflect Pi's actual capability set.
- `detect()` already returns `shutil.which("pi") is not None` — verify it's correct.

### Step 4: Update Config Schema

In `config-schema.json`, add `"pi"` to `hooks.properties.host.enum` (around line 1102–1104).

### Step 5: Write Python Tests

- `scripts/tests/test_config.py:TestResolveConfigPath` — add Pi probe-order tests after `test_codex_path_takes_precedence_when_host_codex` (~line 1040), mirroring the codex variant with `LL_HOOK_HOST=pi` and `.pi/ll-config.json`
- `scripts/tests/test_config_schema.py:test_hooks_in_schema` (~line 155) — update exact-equality assertion to include `"pi"` in `hooks.host.enum`: `["claude-code", "opencode", "codex", "pi"]`
- `scripts/tests/test_hook_intents.py:TestHooksMainModule` (~line 359) — add `test_ll_hook_host_env_var_propagates_pi` after the codex variant
- `scripts/tests/test_host_runner.py:TestPiRunner` (~lines 337–392) — replace 4 `pytest.raises(HostNotConfigured, match="FEAT-992")` assertions with argv-snapshot tests following `TestCodexRunner` as template; update `test_pirunner_probe_returns_stub_not_raise` (~line 357) once `build_*` is wired
- `scripts/tests/test_hook_session_start.py` (~line 64) — add Pi parallel of `test_falls_back_to_codex_dir_config`: set `LL_HOOK_HOST=pi`, create `.pi/ll-config.json`, assert it is loaded through the session-start handler

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — `PiRunner` class at lines 478–532; `CodexRunner` at lines 270–418 is the direct template
- `scripts/little_loops/config/core.py` — `CODEX_CONFIG_DIR = ".codex"` at line 36; `_config_candidates()` codex branch at lines 85–86; `OrchestrationConfig` docstring (~line 58)
- `config-schema.json` — `hooks.properties.host.enum` (currently `["claude-code", "opencode", "codex"]`; add `"pi"`); `orchestration.host_cli` already includes `"pi"` — **no change needed there**

### Registry / Probe Order (context for blast radius)
- `host_runner.py:542` — `_HOST_RUNNER_REGISTRY["pi"] = PiRunner` already live
- `host_runner.py:554` — `("pi", "pi")` in `_PROBE_ORDER` already active (unlike Codex which is gated by a commented-out entry); wiring `build_*` immediately activates Pi for any env with `pi` on PATH

### Test Files
- `scripts/tests/test_host_runner.py:337` — `TestPiRunner` (lines 337–393); four `match="FEAT-992"` raises to replace
- `scripts/tests/test_config.py:1040` — `TestResolveConfigPath`; codex probe-order tests at lines 1040–1085 are the template
- `scripts/tests/test_config_schema.py:136` — `test_hooks_in_schema`; exact assertion at line 155: `assert host["enum"] == ["claude-code", "opencode", "codex"]`
- `scripts/tests/test_hook_intents.py:359` — `TestHooksMainModule`; `test_ll_hook_host_env_var_propagates_codex` is the template
- `scripts/tests/test_hook_session_start.py:64` — `TestSessionStartConfigLoad`; `test_falls_back_to_codex_dir_config` is the template

### Documentation (may need updates)
- `docs/reference/HOST_COMPATIBILITY.md` — host compatibility matrix; may need Pi row updated from "stub" to "supported"
- `docs/reference/API.md` — `little_loops.host_runner` section; `PiRunner` runner-table row (currently says "stub"); remove `PiRunner` from `HostNotConfigured` stub-runner sentence

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — `PiRunner` row at line 570: `"Stub for the Raspberry Pi host (FEAT-992 research deferred)"` becomes stale; `hooks/adapters/` directory tree (lines 85–98) lists `claude-code/`, `opencode/`, `codex/` but has no `pi/` entry (FEAT-1476 primary scope)
- `docs/development/TROUBLESHOOTING.md` — line 294 and line 308 list `PiRunner` as a stub runner and reference FEAT-992; become stale once `build_*` is wired (FEAT-1476 primary scope)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_ (transparent beneficiaries — no code changes required; listed for blast-radius awareness)
- `scripts/little_loops/subprocess_utils.py` — calls `resolve_host().build_streaming()` at line 263; works automatically once `PiRunner.build_streaming()` is wired
- `scripts/little_loops/cli/action.py` — calls `resolve_host().build_version_check()` at line 149
- `scripts/little_loops/parallel/worker_pool.py` — calls `resolve_host().build_blocking_json()` at line 576
- `scripts/little_loops/fsm/evaluators.py` — calls `resolve_host().build_blocking_json()` at line 609
- `scripts/little_loops/fsm/handoff_handler.py` — calls `resolve_host().build_detached()` at line 116
- `scripts/little_loops/hooks/session_start.py` — calls `resolve_config_path()` which internally calls `_config_candidates()`; will automatically probe `.pi/ll-config.json` once the branch is added — no code change needed
- `scripts/little_loops/__init__.py` — exports `HostNotConfigured`, `HostInvocation`, `HostRunner`, `CapabilityNotSupported`; concrete runners (`PiRunner`) and `PI_CONFIG_DIR` are intentionally NOT exported at package level (matching `CodexRunner` convention) — no change needed

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `PiRunner.detect()` at `host_runner.py:493` already correctly returns `shutil.which("pi") is not None` — no change needed
- `PiRunner` is already registered and in `_PROBE_ORDER` — unlike `CodexRunner` (which is commented out of `_PROBE_ORDER` and gated), Pi auto-detects immediately once `build_*` is wired
- `CodexRunner.capabilities` at `host_runner.py:300–305` = `HostCapabilities(streaming=True, permission_skip=True, agent_select=False, tool_allowlist=False)` — this is the specific capability set to evaluate against Pi's CLI docs; if Pi CLI supports streaming JSON output and a bypass-approvals flag, set identically
- `test_pirunner_probe_returns_stub_not_raise` at `test_host_runner.py:357–369` currently patches `shutil.which`, calls `resolve_host(env={})`, asserts `PiRunner` returned, **then asserts `HostNotConfigured` on `build_streaming`** — after wiring, remove the `HostNotConfigured` assertion and replace it with an argv snapshot (e.g. `assert invocation.binary == "pi"`) following `test_codex_runner_flag_translation` at `test_host_runner.py:194`
- `test_opencode_runner_gated_from_auto_probe` at `test_host_runner.py:301–306` checks `runner.name not in {name for name, _ in hr._PROBE_ORDER}` — Pi does NOT need this test since Pi is intentionally in `_PROBE_ORDER`

## Files to Modify

- `scripts/little_loops/config/core.py` — `PI_CONFIG_DIR` constant + `_config_candidates()` branch + `OrchestrationConfig` docstring cleanup
- `scripts/little_loops/host_runner.py` — wire `PiRunner.build_*` methods; update `HostCapabilities`
- `config-schema.json` — add `"pi"` to `hooks.properties.host.enum`
- `scripts/tests/test_config.py` — Pi probe-order test cases
- `scripts/tests/test_config_schema.py` — update exact-equality assertion
- `scripts/tests/test_hook_intents.py` — `LL_HOOK_HOST=pi` propagation test
- `scripts/tests/test_host_runner.py` — replace stub raises with argv-snapshot tests
- `scripts/tests/test_hook_session_start.py` — Pi session-start config-load test

## Test Templates

- `scripts/tests/test_config.py:1040` — `test_codex_path_takes_precedence_when_host_codex` in `TestResolveConfigPath`
- `scripts/tests/test_config_schema.py:155` — exact assertion line to update
- `scripts/tests/test_hook_intents.py:359` — `test_ll_hook_host_env_var_propagates_codex` in `TestHooksMainModule`
- `scripts/tests/test_host_runner.py:165` — `TestCodexRunner`; `test_codex_runner_flag_translation` at line 194 is the canonical argv-snapshot form
- `scripts/tests/test_hook_session_start.py:64` — `test_falls_back_to_codex_dir_config` in `TestSessionStartConfigLoad`

## Impact

- **Priority**: P5
- **Effort**: Medium
- **Risk**: Low — additive; no changes to existing host logic

## Status

**Open** | Created: 2026-05-15 | Priority: P5

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-15_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 67/100 → MODERATE

### Outcome Risk Factors
- **8 change sites spanning source + test files**: Integration overhead above a typical single-file feature; each template copy is mechanical but five test files must stay in sync.
- **Pi CLI flag surface unverified**: `PiRunner.build_*` must translate to Pi's actual flags for streaming and permission-skip. The issue says "if Pi CLI supports streaming JSON output and a bypass-approvals flag, set identically to CodexRunner" — run `pi --help` first to confirm before setting `HostCapabilities`.
- **Auto-activation via `_PROBE_ORDER`**: Unlike `CodexRunner` (which is gated), `("pi", "pi")` is already active. Wiring `build_*` turns on Pi routing for any machine with `pi` on PATH. Run the full test suite with `pi` absent from PATH to confirm no inadvertent routing regressions.

## Session Log
- `/ll:wire-issue` - 2026-05-15T19:58:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c5cd5504-1a49-4471-b701-2ccee2cd4de1.jsonl`
- `/ll:refine-issue` - 2026-05-15T19:53:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/153f9861-caa4-4423-b4ac-99f08867d6bc.jsonl`
- `/ll:issue-size-review` - 2026-05-15T20:10:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f91d7b90-f81d-4224-83bd-e6b959badcd1.jsonl`
- `/ll:confidence-check` - 2026-05-15T20:25:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c5cd5504-1a49-4471-b701-2ccee2cd4de1.jsonl`
- `/ll:issue-size-review` - 2026-05-15T20:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e9b11ad-de12-4f82-9761-25c38e59c783.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-15
- **Reason**: Issue too large for single session (score: 11/11, Very Large)

### Decomposed Into
- FEAT-1479: Pi Adapter — Config Candidate, Schema, and Config Tests
- FEAT-1480: Pi Adapter — Wire PiRunner and Host Runner Tests

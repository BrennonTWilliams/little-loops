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

Implement `PiRunner.build_*` methods in `host_runner.py` (replacing the `HostNotConfigured` stubs), apply `HostCapabilities` as determined by FEAT-1714's Pi CLI flag audit (do not independently evaluate), and write the associated host runner and hook-intents tests.

## Parent Issue

Decomposed from FEAT-1477: Pi Adapter — Python Backend: Config, Host Runner, Schema, and Tests

## Acceptance Criteria

- `scripts/little_loops/host_runner.py` `PiRunner.build_streaming()`, `build_blocking_json()`, `build_detached()`, and `build_version_check()` are wired (no longer raise `HostNotConfigured`); `HostCapabilities` updated as appropriate
- All host runner Pi tests pass: `python -m pytest scripts/tests/test_host_runner.py -k pi`
- Hook-intents Pi propagation test passes: `python -m pytest scripts/tests/test_hook_intents.py -k pi`
- No regressions in existing Claude Code, OpenCode, or Codex test suites

## Proposed Solution

### Step 1: Consume FEAT-1714 Audit

FEAT-1714's research note provides the definitive mapping from Pi CLI flags to `HostCapabilities` fields. Import this mapping verbatim — do not independently re-audit Pi's CLI flags. The audit output (research note) is the single source of truth for Pi's capability surface.

- `CodexRunner.capabilities` at lines 300–305 provides the `HostCapabilities` shape template; FEAT-1714's audit determines which flags to set for Pi
- If FEAT-1714's audit is incomplete or the research note is not yet written, block this step until FEAT-1714 is done

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

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-01_

**Verdict: OUTDATED** — Implementation not started:
- All 4 `PiRunner.build_*` methods still raise `HostNotConfigured` at `host_runner.py:671–707`
- `HostCapabilities` for Pi not defined
- Depends on FEAT-1714 (also unstarted)

## Status

**Open** | Created: 2026-05-15 | Priority: P5

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-18): This issue modifies `host_runner.py` to wire `PiRunner` (lines 478–532). ENH-1529 also modifies `host_runner.py` to add `_sandbox_args()` and thread `sandbox_mode` through `CodexRunner` (lines 270–418). The two changes target different class regions and are non-overlapping, but landing both PRs simultaneously on the same file can produce near-miss merge conflicts during rebase. Sequence or merge these PRs deliberately; review both diff hunks together before landing.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's `test_ll_hook_host_env_var_propagates_pi` test in `test_hook_intents.py` tests the **Python-side host routing** — that the intent dispatcher reads `LL_HOOK_HOST=pi` and routes correctly. FEAT-1478's sentinel-file test in `test_pi_adapter.py` verifies the **TypeScript adapter** sets `LL_HOOK_HOST=pi` before spawning Python. Both tests are needed, but their assertions must be non-overlapping to avoid redundancy: this issue asserts Python routing behavior; FEAT-1478 asserts env-var propagation from the TypeScript layer.

## Session Log
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T20:02:29 - `0860b18c-08b7-4093-862a-cc8046f35aaa.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:55 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-06-01T14:29:19 - `f3a091ba-2869-499e-9de4-7f5c8ca96083.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:58 - `5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:10 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:13 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:verify-issues` - 2026-05-23T00:35:44 - `2955f8fa-d24c-40f9-9d2d-3d46811662f9.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-18T05:05:17 - `16717e5e-bfe4-4e7f-8d36-177b4b791f2d.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-17T18:46:35 - `ebf7abce-1ef1-46c8-8cbc-56d9f857d730.jsonl`
- `/ll:issue-size-review` - 2026-05-15T20:30:00 - `3e9b11ad-de12-4f82-9761-25c38e59c783.jsonl`

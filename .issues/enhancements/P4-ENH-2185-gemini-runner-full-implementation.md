---
id: ENH-2185
title: GeminiRunner full implementation — build_streaming, build_blocking_json, build_detached, build_version_check
type: enhancement
status: open
priority: P4
parent: EPIC-2178
depends_on: [FEAT-2179, ENH-2184]
captured_at: "2026-06-15T00:00:00Z"
discovered_date: 2026-06-15
discovered_by: capture-issue
labels: [gemini, host-compat, host-runner]
---

# ENH-2185: GeminiRunner full implementation

## Summary

Replace the `HostNotConfigured` stubs in `GeminiRunner` (ENH-2184) with real
`build_streaming`, `build_blocking_json`, `build_detached`, and
`build_version_check` implementations. Flag translation is fully established by
FEAT-2179.

## Current Behavior

`GeminiRunner.build_streaming`, `build_blocking_json`, `build_detached`, and
`build_version_check` all raise `HostNotConfigured` — the class exists as a
stub (ENH-2184) with no functional implementations.

## Expected Behavior

Each method returns a valid `HostInvocation` with the correct Gemini CLI
arguments:
- `build_streaming` → `gemini -p <prompt> -o stream-json [--model <m>] [--approval-mode=yolo]`
- `build_blocking_json` → `gemini -p <prompt> -o json`
- `build_detached` → `gemini -p <prompt>` (fire-and-forget, no output capture)
- `build_version_check` → `["gemini", "--version"]`

## Use Case

`ll-auto`, `ll-sprint`, and `ll-loop` call `resolve_host().build_streaming(...)`.
With the stub only, these raise `HostNotConfigured`. This issue makes them
functional with Gemini.

## Implementation Steps

1. Implement `build_streaming`:
   - `gemini -p <prompt> -o stream-json [--model <m>] [--approval-mode=yolo]`
   - Mirror `ClaudeRunner.build_streaming` flag mapping
2. Implement `build_blocking_json`:
   - `gemini -p <prompt> -o json`
   - Response blob shape: `{response, stats, error?}` (from FEAT-2179)
3. Implement `build_detached`:
   - `gemini -p <prompt>` with no output capture (fire-and-forget)
4. Implement `build_version_check`:
   - `["gemini", "--version"]`
5. Update `scripts/tests/test_host_runner.py` — replace stub tests with
   functional coverage (mocking subprocess).
6. Update `scripts/tests/test_gemini_adapter.py` (if exists) with
   `build_streaming` invocation tests.

## Acceptance Criteria

- `resolve_host().build_streaming(prompt="hello")` returns a valid
  `HostInvocation` for `gemini -p hello -o stream-json`.
- `resolve_host().build_blocking_json(prompt="hello")` returns a valid
  `HostInvocation` for `gemini -p hello -o json`.
- `build_version_check()` returns `["gemini", "--version"]`.
- `ll-auto --host gemini` can process at least one issue end-to-end (requires
  `gemini` on PATH).
- Tests pass.

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py` — `GeminiRunner` methods

### Dependent Files (Callers/Importers)

- `scripts/little_loops/subprocess_utils.py:329` — central orchestration dispatch that calls `resolve_host().build_streaming(...)` (used by ll-auto/ll-parallel; ll-sprint/ll-loop reach `build_streaming` through this module, not via direct runner modules)
- `scripts/little_loops/cli/harness.py:283` — calls `resolve_host().build_streaming(...)`

### Similar Patterns

- `scripts/little_loops/host_runner.py` — `ClaudeRunner` methods (mirror flag mapping)

### Tests

- `scripts/tests/test_host_runner.py` — replace stub tests with functional coverage (mocking subprocess)
- `scripts/tests/test_gemini_adapter.py` — `build_streaming` invocation tests (if exists)

### Documentation

- `docs/reference/HOST_COMPATIBILITY.md` — verify Gemini method coverage table
- `docs/reference/API.md` — update `GeminiRunner` entries

### Configuration

- N/A

## Research Notes (FEAT-2179)

| Method | Command |
|--------|---------|
| `build_streaming` | `gemini -p <prompt> -o stream-json [-m <model>] [--approval-mode=yolo]` |
| `build_blocking_json` | `gemini -p <prompt> -o json` |
| `build_detached` | `gemini -p <prompt>` (background) |
| `build_version_check` | `gemini --version` |

Session resume: `-r latest` / `-r <index>` / `-r <session-id>` — wire if `HostInvocation` supports resume.

## Impact

- **Priority**: P4 — net-new host support gated behind ENH-2184 (stub) and FEAT-2179; does not block the established Claude/Codex/OpenCode workflows, so it only earns value once Gemini is a desired target.
- **Effort**: S (2–4 hours) — four method bodies mirroring the existing `ClaudeRunner` flag mapping; mostly mechanical, with the bulk of the work in replacing stub tests with functional subprocess-mocked coverage.
- **Risk**: Low — isolated to `GeminiRunner`; existing runners untouched
- **Breaking Change**: No

---

## Verification Notes

2026-06-18 (BLOCKED): ENH-2184 (stub) is not yet implemented — no `GeminiRunner` in `host_runner.py`. Full implementation cannot start until the stub lands.

- **2026-06-26** (/ll:verify-issues): Corrected Dependent Files — replaced three nonexistent modules (`auto_runner.py`, `sprint_runner.py`, `loop_runner.py`) with the actual `build_streaming` consumers `subprocess_utils.py:329` and `cli/harness.py:283`.

**Open** | Created: 2026-06-15 | Priority: P4


## Session Log
- `/ll:format-issue` - 2026-06-26T23:18:13 - `4d6a8ad8-6bd0-49d7-b654-aa79c9184ffd.jsonl`
- `/ll:format-issue` - 2026-06-26T23:17:01 - `4d6a8ad8-6bd0-49d7-b654-aa79c9184ffd.jsonl`

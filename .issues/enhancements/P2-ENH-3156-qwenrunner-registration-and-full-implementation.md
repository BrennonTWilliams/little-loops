---
id: ENH-3156
title: QwenRunner registration + full build_* implementation
type: ENH
status: done
priority: P2
parent: EPIC-3154
depends_on:
- FEAT-3155
captured_at: '2026-08-13T01:28:37Z'
discovered_date: 2026-08-12
discovered_by: capture-issue
labels:
- qwen
- host-compat
completed_at: '2026-08-13T02:45:00Z'
---

# ENH-3156: QwenRunner registration + full build_* implementation

## Summary

Add `QwenRunner` to `scripts/little_loops/host_runner.py` satisfying the
`HostRunner` Protocol, registered in `_HOST_RUNNER_REGISTRY["qwen"]` with
`_PROBE_ORDER += [("qwen", "qwen")]` appended at the END and a
`_remediation_hint()` entry. Kimi landed without a stub stage (ENH-2912 +
FEAT-2914 collapsed); expect the same here — full implementation directly.
`KimiRunner` / `ClaudeCodeRunner` are the templates.

## Motivation

The runner is the critical path to `LL_HOST_CLI=qwen` actually running
`ll-auto`/`ll-loop`/FSM loops. The headline capability:
`structured_output=True` via the inline `--json-schema` flag — Qwen becomes
only the second host after Claude Code to re-enable the FSM evaluators'
schema-constrained verdict path (gated off for every other host per
`HostCapabilities.structured_output`, ENH-2627).

## Implementation Steps

1. `build_streaming` = `["--yolo", "--output-format", "stream-json"]`
   (+ `["--continue"]` if resume) + `["-p", prompt]` (+ `["--model", m]`);
   env `LL_NON_INTERACTIVE=1` + `DANGEROUSLY_SKIP_PERMISSIONS=1` +
   `LL_AUTOMATION*` passthrough; worktree `GIT_DIR`/`GIT_WORK_TREE` handling
   via the shared helper.
2. `build_blocking_json` = `["--yolo", "--output-format", "json", "-p", prompt]`;
   consume the final `result` element of the buffered message array; honor
   `json_schema` by appending `["--json-schema", schema]` — the strict path
   no other non-Claude host has.
3. `build_detached` = `["--yolo", "-p", prompt]`.
4. `build_version_check` = `["--version"]`.
5. `describe_capabilities()`: `streaming`/`permission_skip`/`structured_output`
   True; `agent_select`/`tool_allowlist` False (no `--agent` flag —
   documented as planned upstream; `--exclude-tools` is denylist-only).
   `agent=` passed with `agent_select=False` → `CapabilityNotSupported`
   warn-and-drop (Gemini posture, R5).
6. Full unit tests in `scripts/tests/test_host_runner.py` (expand a
   `TestQwenRunner` class); verify with
   `python -m pytest scripts/tests/test_host_runner.py -k qwen`.

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py` — `QwenRunner`, registry, probe order, remediation hint
- `scripts/tests/test_host_runner.py` — full `QwenRunner` coverage

### New Files

- None.

### Dependent Files

- `scripts/little_loops/cli/doctor.py` — capability report accuracy
- `scripts/tests/conformance/test_host_conformance.py` — golden paths run for qwen once `_HOST_BINARY` lands (ENH-3161)
- `docs/reference/HOST_COMPATIBILITY.md` — runner capability cells, filled by ENH-3162

## Impact

- **Priority**: P2 — critical path; the epic's success metrics depend on it.
- **Effort**: M — four `build_*` methods plus full tests; flag surface desk-verified by the report, live-verified by FEAT-3155.
- **Risk**: Medium-Low — additive; main risk is stream-json event-shape drift (R4), pinned by runner tests.
- **Breaking Change**: No.

## Verification Notes

2026-08-12 (DONE): `QwenRunner` landed full (no stub stage, Kimi precedent).
Registered in `_HOST_RUNNER_REGISTRY["qwen"]`, `_PROBE_ORDER` appended
`("qwen","qwen")` last, `_remediation_hint()` + `resolve_host()` docstring
updated. `structured_output=True` — required a host-aware fix in
`fsm/evaluators.py::_structured_output_args`: qwen rejects claude's
`--no-session-persistence` (live-verified argv parse error), so the
persistence opt-out is now keyed on `invocation.binary` (claude →
`--no-session-persistence`, qwen → `--chat-recording false`).
`build_blocking_json` uses `stream-json` (qwen's `--output-format json`
buffers an array that breaks single-envelope consumers). Env carries
`QWEN_CODE_SUPPRESS_YOLO_WARNING=1` to keep stderr clean. `TestQwenRunner`
(21 tests) + `TestQwenStructuredOutputArgs` (3 tests) added; full
`test_host_runner.py` green: 206 passed, 1 skipped.

## Session Log
- `/ll:capture-issue` - 2026-08-13T01:28:37Z - qwen-code host integration report capture

---

**Done** | Created: 2026-08-12 | Completed: 2026-08-12 | Priority: P2

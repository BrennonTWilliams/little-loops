---
id: ENH-1529
title: "Expose sandbox_mode parameter on CodexRunner build methods"
priority: P4
type: ENH
status: open
captured_at: "2026-05-16T21:26:07Z"
discovered_date: "2026-05-16"
discovered_by: capture-issue
relates_to:
  - FEAT-1465
  - FEAT-1462
---

# ENH-1529: Expose sandbox_mode parameter on CodexRunner build methods

## Summary

`CodexRunner` currently hardcodes `--dangerously-bypass-approvals-and-sandbox` in every
`build_*` method, giving callers no way to request a more constrained Codex execution.
Expose a `sandbox_mode` parameter so automation code can choose between `off` (current
default), `read-only`, `write-to-cwd`, and `network` without reaching around the runner
abstraction.

## Current Behavior

All four `CodexRunner` build methods (`build_streaming`, `build_blocking_json`,
`build_detached`, `build_version_check`) unconditionally append
`--dangerously-bypass-approvals-and-sandbox` to the `codex exec` invocation.

When callers pass `tools=["Read", "Grep"]` hoping to constrain execution, the runner
emits a `CapabilityNotSupported` warning and drops the parameter — but still runs with
zero sandboxing.

## Expected Behavior

`build_streaming` (and the other relevant build methods) accept an optional
`sandbox_mode: str | None = None` parameter:

- `None` (default) → `--dangerously-bypass-approvals-and-sandbox` (current behavior, no regression)
- `"off"` → same as `None` (explicit alias)
- `"read-only"` → omit `--dangerously-bypass-approvals-and-sandbox`; append `--sandbox read-only`
- `"write-to-cwd"` → omit `--dangerously-bypass-approvals-and-sandbox`; append `--sandbox write-to-cwd`
- `"network"` → omit `--dangerously-bypass-approvals-and-sandbox`; append `--sandbox network`

Invalid values raise `ValueError`. The existing `tools` warning message is updated to
suggest `sandbox_mode` as the Codex-native alternative.

## Motivation

The `--tools` allowlist gap is well-documented (`host_runner.py:364-370`), but the
current workaround is all-or-nothing: either full unrestricted access or don't use Codex.
Surfacing Codex's own sandbox modes through the standard runner API lets callers express
the intent ("restrict file writes") in the abstraction layer rather than bypassing it.

## Proposed Solution

1. Add `sandbox_mode: str | None = None` to `build_streaming`, `build_blocking_json`,
   and `build_detached` signatures in `CodexRunner`.
2. Replace the hardcoded `--dangerously-bypass-approvals-and-sandbox` with a helper
   `_sandbox_args(sandbox_mode)` that returns the appropriate flag(s).
3. Update the `tools` warning to include: `"Use sandbox_mode='read-only' or 'write-to-cwd' for constrained Codex execution."`
4. Update `HostCapabilities` / `describe_capabilities` to note partial tool-constraint
   support via sandbox modes.
5. Add `sandbox_mode` tests to `test_host_runner.py`.

## Integration Map

- **`scripts/little_loops/host_runner.py`** — `CodexRunner.build_streaming`,
  `build_blocking_json`, `build_detached`; new `_sandbox_args` helper; updated
  `tools` warning text
- **`scripts/tests/test_host_runner.py`** — new parametrized tests for each
  `sandbox_mode` value and the invalid-value path

## Implementation Steps

1. Add `_sandbox_args(sandbox_mode: str | None) -> list[str]` as a static method or
   module-level helper in `host_runner.py`
2. Thread `sandbox_mode` through the three build methods, replacing the hardcoded flag
3. Update the `CapabilityNotSupported` warning message for `tools`
4. Update `describe_capabilities` note for `tool_allowlist`
5. Write tests; run `python -m pytest scripts/tests/test_host_runner.py`

## Impact

- **Scope**: `host_runner.py` only; no callers currently pass `tools` to `CodexRunner`
- **Risk**: Low — default (`None`) preserves existing behavior exactly
- **Callers**: `ll-auto`, `ll-parallel`, `ll-sprint` all use the default path; no
  changes needed unless a caller wants constrained execution

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/reference/HOST_COMPATIBILITY.md` | Codex capability table; update `tool_allowlist` row |
| `thoughts/research/codex-headless-invocation.md` | Flag translation source of truth |
| `scripts/tests/test_host_runner.py` | Existing test surface to extend |

## Labels

`codex`, `host-runner`, `sandbox`

## Status

- [ ] Implementation
- [ ] Tests pass
- [ ] `describe_capabilities` updated
- [ ] `HOST_COMPATIBILITY.md` updated

---

## Session Log
- `/ll:capture-issue` - 2026-05-16T21:26:07Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c91b1bb-8b36-420d-bb06-e3e6a03f08a4.jsonl`

---
id: FEAT-2914
title: KimiRunner full implementation (build_streaming, build_blocking_json, build_detached, build_version_check)
type: FEAT
status: open
priority: P2
parent: EPIC-2910
depends_on:
- ENH-2912
captured_at: "2026-07-29T15:55:00Z"
discovered_date: 2026-07-29
discovered_by: capture-issue
labels:
- kimi
- host-compat
---

# FEAT-2914: KimiRunner full implementation (build_streaming, build_blocking_json, build_detached, build_version_check)

## Summary

Replace the ENH-2912 stub with the real `KimiRunner` implementation per the
FEAT-2911 spike: `build_streaming`, `build_blocking_json`, `build_detached`,
and `build_version_check`. `GeminiRunner`
(`scripts/little_loops/host_runner.py:928-1138`) is the closest template.
Blocked on ENH-2912.

## Motivation

The runner is the critical path to `LL_HOST_CLI=kimi-code` actually running
`ll-auto`/`ll-loop`/FSM loops. The spike already verified the full flag
surface against kimi 0.30.0, so the translation is mechanical — the main
subtleties are kimi's lack of a single-blob JSON mode and the
`--agent`/`--continue` conflict.

## Implementation Steps

1. `build_streaming` = `kimi -p <prompt> --output-format stream-json`; add
   `--continue` for resume; `--agent` (warn + drop with
   `CapabilityNotSupported` when `resume=True` — kimi rejects the combo);
   `-m` model; `--add-dir` for `workspace_root`
   (`workspace_sandboxed=False`); env `LL_NON_INTERACTIVE=1` /
   `LL_AUTOMATION*`; worktree `GIT_DIR`/`GIT_WORK_TREE` handling.
2. `build_blocking_json` = `CodexRunner` pattern — stream and consume the
   final assistant content (kimi has no single-blob JSON mode);
   `json_schema` dropped with `CapabilityNotSupported` →
   `structured_output=False`.
3. `build_detached` = `kimi -p` text mode; note
   `print_background_mode=steer` keeps the process alive while background
   tasks are pending.
4. `build_version_check` = `kimi --version`.
5. `describe_capabilities()`: `streaming`/`permission_skip`/`agent_select`
   True; `tool_allowlist`/`structured_output`/`workspace_sandboxed` False.
6. Full unit tests in `scripts/tests/test_host_runner.py` (expand
   `TestKimiRunner`); verify with
   `python -m pytest scripts/tests/test_host_runner.py -k kimi`.

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py` — real `build_*` implementations replace the stub raises
- `scripts/tests/test_host_runner.py` — full `KimiRunner` coverage

### New Files

- None.

### Dependent Files

- `scripts/little_loops/cli/doctor.py` — capability report accuracy
- `scripts/tests/conformance/test_host_conformance.py` — golden paths run for kimi once `_HOST_BINARY` lands (ENH-2918)
- `docs/reference/HOST_COMPATIBILITY.md` — runner capability cells, flipped by ENH-2919

## Impact

- **Priority**: P2 — critical path; the epic's success metrics depend on it.
- **Effort**: M — four `build_*` methods plus full tests; flag surface already verified by the spike.
- **Risk**: Medium-Low — additive; spike de-risked the CLI surface, main risk is stream-event drift across kimi versions.
- **Breaking Change**: No.

## Session Log
- `/ll:capture-issue` - 2026-07-29T15:55:00Z - kimi-code host adapter planning session

---

**Open** | Created: 2026-07-29 | Priority: P2

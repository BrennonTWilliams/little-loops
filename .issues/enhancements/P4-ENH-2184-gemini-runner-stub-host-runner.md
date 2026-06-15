---
id: ENH-2184
title: GeminiRunner stub in host_runner.py
type: enhancement
status: open
priority: P4
parent: EPIC-2178
depends_on: [FEAT-2179]
captured_at: "2026-06-15T00:00:00Z"
discovered_date: 2026-06-15
discovered_by: capture-issue
labels: [gemini, host-compat, host-runner]
---

# ENH-2184: GeminiRunner stub in host_runner.py

## Summary

Add a `GeminiRunner` class to `scripts/little_loops/host_runner.py` that raises
`HostNotConfigured` on all `build_*` calls. Wire it into `_HOST_RUNNER_REGISTRY`
and `_PROBE_ORDER` so `resolve_host()` can select Gemini when `LL_HOST_CLI=gemini`
or `gemini` is on PATH. Analogous to `PiRunner`.

This is the stub step. Full implementation lands in ENH-2185.

## Use Case

A developer sets `LL_HOST_CLI=gemini`. Without this stub, `resolve_host()` raises
an unknown-host error. With the stub, the host resolves correctly and
`HostNotConfigured` is raised with a helpful remediation hint, analogous to Pi's
behavior before Pi support was complete.

## Implementation Steps

1. Add `GeminiRunner` class to `host_runner.py`:
   - Inherits `HostRunner` protocol
   - `binary = "gemini"`
   - All `build_streaming`, `build_blocking_json`, `build_detached`,
     `build_version_check` raise `HostNotConfigured("gemini", "ENH-2185")`
   - `probe()` → `shutil.which("gemini") is not None`
2. Add `("gemini", GeminiRunner)` to `_HOST_RUNNER_REGISTRY`.
3. Add `("gemini", "gemini")` to `_PROBE_ORDER` after Pi.
4. Add a Gemini case to `_remediation_hint()` pointing to EPIC-2178.
5. Add test coverage to `scripts/tests/test_host_runner.py`:
   - `test_gemini_runner_stub_raises_host_not_configured`
   - `test_resolve_host_selects_gemini_when_ll_host_cli_set`

## Acceptance Criteria

- `resolve_host()` returns a `GeminiRunner` when `LL_HOST_CLI=gemini`.
- All `build_*` calls on the stub raise `HostNotConfigured`.
- `ll-doctor` lists `gemini` as a recognized host with stub status.
- Tests pass: `python -m pytest scripts/tests/test_host_runner.py -k gemini`.

## API/Interface

### Files to Modify

- `scripts/little_loops/host_runner.py` — `GeminiRunner` class, registry, probe order, remediation hint
- `scripts/tests/test_host_runner.py` — stub coverage

## Research Notes

From FEAT-2179 findings:
- Binary: `gemini` (npm `@google/gemini-cli`), v0.46.0
- `probe()`: `shutil.which("gemini")`
- `build_version_check`: `gemini --version`

Pattern: follow `PiRunner` in `host_runner.py` — it's the simplest existing stub.

## Impact

- **Effort**: XS (< 1 hour)
- **Risk**: Very low — additive only, no existing behavior changes
- **Breaking Change**: No

---

**Open** | Created: 2026-06-15 | Priority: P4

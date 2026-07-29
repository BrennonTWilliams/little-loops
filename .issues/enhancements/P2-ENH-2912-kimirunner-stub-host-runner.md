---
id: ENH-2912
title: KimiRunner stub in host_runner.py
type: ENH
status: done
priority: P2
parent: EPIC-2910
captured_at: '2026-07-29T15:55:00Z'
discovered_date: 2026-07-29
discovered_by: capture-issue
labels:
- kimi
- host-compat
completed_at: '2026-07-29T20:54:05Z'
---

# ENH-2912: KimiRunner stub in host_runner.py

## Summary

Add a `KimiRunner` class to `scripts/little_loops/host_runner.py` copying the
`OpenCodeRunner`/`PiRunner` stub shape (`host_runner.py:780-925`):
`name = "kimi-code"`, `detect()` = `shutil.which("kimi")`, all `build_*`
raise `HostNotConfigured`, and a `describe_capabilities()` stub. Wire it into
`_HOST_RUNNER_REGISTRY` (:1325), `_PROBE_ORDER` (:1336), `_remediation_hint()`
(:1345), and `__all__` (:44-66).

## Motivation

This is the critical-path entry point for EPIC-2910 — every downstream child
(full runner, conformance, `ll-doctor` visibility) assumes the `kimi-code`
host key resolves. The stub makes `LL_HOST_CLI=kimi-code` resolve with a
helpful `HostNotConfigured` remediation hint instead of an unknown-host
error, exactly as `PiRunner` did before Pi support was complete.

## Implementation Steps

1. Add the `KimiRunner` class copying the `OpenCodeRunner`/`PiRunner` stub
   shape (`scripts/little_loops/host_runner.py:780-925`): `name = "kimi-code"`,
   `detect()` returns `shutil.which("kimi") is not None`, all
   `build_streaming`/`build_blocking_json`/`build_detached`/`build_version_check`
   raise `HostNotConfigured` pointing to FEAT-2914 / EPIC-2910, and a
   `describe_capabilities()` stub reporting the host as unsupported.
2. Add `"kimi-code": KimiRunner` to `_HOST_RUNNER_REGISTRY` (:1325).
3. Append `("kimi-code", "kimi")` LAST in `_PROBE_ORDER` (:1336) — append-only,
   so auto-detection precedence is unchanged for existing users with `kimi`
   installed.
4. Extend `_remediation_hint()` (:1345) — add kimi to both inline host lists.
5. Export `"KimiRunner"` in `__all__` (:44-66).
6. Add `TestKimiRunner` coverage to `scripts/tests/test_host_runner.py`
   (mirror `TestPiRunner`); verify with
   `python -m pytest scripts/tests/test_host_runner.py -k kimi`.

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py` — class, registry, probe order, remediation hint, `__all__`
- `scripts/tests/test_host_runner.py` — stub coverage

### New Files

- None.

### Dependent Files

- `scripts/tests/conformance/test_host_conformance.py` — golden paths auto-parametrize over the registry; the `_HOST_BINARY` entry lands in ENH-2918
- `scripts/little_loops/cli/doctor.py` — stub status surfaces automatically via `describe_capabilities()`

## Impact

- **Priority**: P2 — critical-path entry point; unblocks FEAT-2914.
- **Effort**: XS (< 1 hour).
- **Risk**: Very low — additive only, no existing behavior changes.
- **Breaking Change**: No.

## Session Log
- `/ll:verify-issues` - 2026-07-29T20:54:13 - `7dce485a-c75c-400c-ac56-53fcf2521623.jsonl`
- `/ll:capture-issue` - 2026-07-29T15:55:00Z - kimi-code host adapter planning session

---

**Open** | Created: 2026-07-29 | Priority: P2

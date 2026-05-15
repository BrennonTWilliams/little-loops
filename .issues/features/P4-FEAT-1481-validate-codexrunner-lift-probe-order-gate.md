---
id: FEAT-1481
type: FEAT
priority: P4
status: open
captured_at: "2026-05-15T20:37:29Z"
discovered_date: 2026-05-15
discovered_by: capture-issue
depends_on: FEAT-1465
---

# FEAT-1481: Validate CodexRunner and Lift `_PROBE_ORDER` Gate

## Summary

`CodexRunner` is registered in `_HOST_RUNNER_REGISTRY` but commented out of `_PROBE_ORDER` (gated behind `LL_HOST_CLI=codex`). Once manually smoke-tested against a real `codex` binary, the gate should be lifted so Codex auto-detects when on PATH and `claude` is absent.

## Current Behavior

`CodexRunner` only activates via explicit `LL_HOST_CLI=codex`. Even if `codex` is installed and `claude` is not, `resolve_host()` will raise `HostNotConfigured` instead of picking up Codex automatically. The commented-out probe entry in `host_runner.py` reads:

```python
# ("codex", "codex"),  # FEAT-1465: gated behind LL_HOST_CLI until validated
```

## Expected Behavior

After validation:
1. `resolve_host()` auto-detects `codex` binary when on PATH and no override env var is set (probe order: `claude → codex → pi`).
2. `("codex", "codex")` is uncommented in `_PROBE_ORDER`.
3. `test_host_runner.py::test_detect_binary_probe_order` passes with codex in the sequence.

## Motivation

The gate was a deliberate safety measure in FEAT-1465 — "gated until validated in production usage." That validation is the remaining work. Without it, Codex-only environments require manual env var configuration that the probe order is designed to avoid.

## Proposed Solution

1. **Smoke test** — with `codex` installed, set `LL_HOST_CLI=codex` and run:
   ```bash
   python -m little_loops.cli.action capabilities
   ll-auto --dry-run   # or ll-sprint --dry-run on a real sprint
   ```
   Verify `build_streaming`, `build_blocking_json`, `build_version_check`, and `build_detached` produce working argv.
2. **Ungate** — uncomment `("codex", "codex")` in `_PROBE_ORDER` in `scripts/little_loops/host_runner.py`.
3. **Remove gating comment** — delete or update the inline comment on the probe entry.
4. **Verify test** — confirm `test_detect_binary_probe_order` in `scripts/tests/test_host_runner.py` passes with codex in the sequence (the test already uses `shutil.which` mocking, so no codex binary needed for CI).

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py` — uncomment `("codex", "codex")` in `_PROBE_ORDER` (~line 553)
- `scripts/tests/test_host_runner.py` — ensure `test_detect_binary_probe_order` covers the updated probe order

### Files to Reference (not modify)

- `thoughts/research/codex-headless-invocation.md` — flag translation research (FEAT-1465)
- `hooks/adapters/codex/README.md` — adapter smoke-test reference

## Implementation Steps

1. Install `codex` binary locally (or use a CI environment that has it)
2. Run smoke tests with `LL_HOST_CLI=codex` as documented above
3. If all commands produce correct argv and no runtime errors, uncomment the probe entry
4. Run `python -m pytest scripts/tests/test_host_runner.py -v` to verify
5. Run `python -m mypy scripts/little_loops/host_runner.py` and `ruff check scripts/little_loops/host_runner.py`

## Impact

- **Scope**: Single-line code change after validation
- **Risk**: Low — CodexRunner is already fully implemented and tested; this only affects auto-detection fallback
- **Unblocks**: Codex-only environments that can't or don't want to set `LL_HOST_CLI`

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/host_runner.py` | `_PROBE_ORDER` and `CodexRunner` implementation |
| `thoughts/research/codex-headless-invocation.md` | Flag translation research from FEAT-1465 |
| `hooks/adapters/codex/README.md` | Codex adapter contract and smoke-test steps |

## Labels

host-runner, codex, validation

---

## Session Log
- `/ll:capture-issue` - 2026-05-15T20:37:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ac48eaf-913e-40cd-8b15-98d99f2901cc.jsonl`

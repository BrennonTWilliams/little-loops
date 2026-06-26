# Host Conformance Harness

The conformance harness validates that every registered host runner can
construct valid invocations for the four little-loops orchestration golden
paths: `ll-auto`, `ll-sprint`, `ll-loop`, `ll-action`.

It is implemented as a single pytest-parametrized test suite in
`scripts/tests/conformance/test_host_conformance.py`.  Parametrization is
over every host registered in `_HOST_RUNNER_REGISTRY`
(`scripts/little_loops/host_runner.py`), so adding a new host requires only
a registry entry — no new test code.

## Running the Harness

```bash
# All conformance tests (all hosts × all golden paths)
pytest -m conformance scripts/tests/

# Single host only
pytest -m conformance --conformance-host codex scripts/tests/

# Deselect conformance from a full suite run
pytest -m "not conformance" scripts/tests/
```

## Reading the Results

Each test is identified as `test_golden_path_invocation[<golden-path>-<host>]`.

| Result | Meaning |
|--------|---------|
| `PASSED` | Host runner is wired; `build_streaming()` returns a valid `HostInvocation`. |
| `SKIPPED` (binary absent) | Host CLI binary not found on PATH — install or set `LL_HOST_CLI`. |
| `SKIPPED` (stub runner) | Host runner is registered but not yet implemented (`HostNotConfigured`). |
| `FAILED` | Runner is wired but produces an invalid `HostInvocation` (empty binary or args). |

PASS/SKIP maps to the "Orchestration CLI" table in
`docs/reference/HOST_COMPATIBILITY.md`: PASS → ✓, SKIP(stub) → `stub[^orch]`.

## Baseline Pass/Fail Board

Snapshot as of 2026-06-26 on a machine with `claude` and `codex` on PATH:

| Golden Path | claude-code | codex | opencode | pi |
|-------------|:-----------:|:-----:|:--------:|:--:|
| `ll-auto`   | PASS        | PASS  | SKIP     | SKIP |
| `ll-sprint` | PASS        | PASS  | SKIP     | SKIP |
| `ll-loop`   | PASS        | PASS  | SKIP     | SKIP |
| `ll-action` | PASS        | PASS  | SKIP     | SKIP |

SKIP = stub runner (`HostNotConfigured`) — see
`docs/reference/HOST_COMPATIBILITY.md` footnote `[^orch]`.

## Adding a New Host

1. Implement `HostRunner` for the new host in `host_runner.py` and add it to
   `_HOST_RUNNER_REGISTRY`.
2. The conformance harness automatically picks it up on the next run.
3. Update the baseline board above once the host passes.

## Closing Superseded Issues

Per FEAT-2259, once this harness lands:

- Run `pytest -m conformance --conformance-host codex` and verify all four
  paths pass, then close **FEAT-1721** (Codex conformance) as superseded.
- Run `pytest -m conformance --conformance-host gemini` once a `GeminiRunner`
  lands, then close **FEAT-2192** (Gemini conformance) as superseded.

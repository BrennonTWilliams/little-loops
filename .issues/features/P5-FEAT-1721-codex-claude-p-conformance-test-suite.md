---
id: FEAT-1721
title: Codex `claude -p` conformance test suite
type: FEAT
priority: P5
status: open
captured_at: "2026-05-26T02:23:05Z"
discovered_date: 2026-05-26
discovered_by: capture-issue
parent: EPIC-1463
depends_on: [FEAT-1481, ENH-1718]
relates_to: [FEAT-1716]
labels: [codex, testing, host-compat, conformance]
---

# FEAT-1721: Codex `claude -p` conformance test suite

## Summary

No test exercises `ll-auto`, `ll-sprint`, `ll-loop`, or `ll-action` end-to-end against a real `codex` binary. The "first-class `claude -p` replacement" claim for Codex is unverified at the orchestration level. This is the Codex parallel to FEAT-1716 (Pi conformance suite).

## Motivation

`CodexRunner` is fully wired and `_PROBE_ORDER` auto-detects Codex (FEAT-1481 done). But unit tests only cover argv snapshots and shell script execution — nothing proves `ll-auto`, `ll-sprint`, `ll-loop`, or FSM evaluator paths produce correct output against a real `codex` binary. Regressions in `CodexRunner.build_*` won't be caught until a user hits them in production.

## Acceptance Criteria

- A test module `scripts/tests/conformance/test_codex_claude_p_parity.py` with golden-path suite covering:
  - `ll-action` invoking a trivial skill against Codex
  - `ll-loop run <no-op-loop>` completing successfully against Codex
  - At least one FSM evaluator path (`fsm/evaluators.py` `build_blocking_json`) producing a structured response
  - At least one `fsm/handoff_handler.py` `build_detached` path spawning correctly
- Tests skip (not fail) when `codex` is not on PATH
- `pytest -m conformance_codex` entrypoint
- `docs/development/CONFORMANCE.md` documents how to run; initial baseline pass/fail board captured after first run
- `pyproject.toml` registers `conformance_codex` pytest marker

## Implementation Steps

1. Inventory `resolve_host().build_*` callers (same set as FEAT-1716: `subprocess_utils.py:263`, `cli/action.py:149`, `parallel/worker_pool.py:576`, `fsm/evaluators.py:609`, `fsm/handoff_handler.py:116`)
2. Design minimal golden paths — keep total wall-clock under ~2 minutes
3. Create `scripts/tests/conformance/__init__.py` if subdir doesn't exist
4. Implement `test_codex_claude_p_parity.py`:
   - `@pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI not installed")`
   - Force host: `monkeypatch.setenv("LL_HOST_CLI", "codex")`
   - Assert observable outcomes (exit code, output file existence, stdout fragment)
5. Register `conformance_codex` marker in `pyproject.toml`
6. Run suite on a machine with Codex installed; record baseline in `docs/development/CONFORMANCE.md`; file follow-up issues for any ✗ entries

## Notes

- Mirrors FEAT-1716 (Pi conformance suite) exactly — the two can share the `conformance/` subdir and pytest marker convention.
- Do not duplicate `test_host_runner.py` argv-snapshot tests — conformance tests assert on observable outcomes, not internal argv shape.
- `CodexRunner.build_blocking_json` uses `--output-schema <tempfile>` for structured output (ENH-1530) — conformance test must call `p.unlink(missing_ok=True)` on `HostInvocation.cleanup_paths` after subprocess completes.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/HOST_COMPATIBILITY.MD` | Matrix this suite validates |
| `scripts/tests/conformance/test_pi_claude_p_parity.py` | Parallel suite to model after (FEAT-1716) |
| `scripts/little_loops/host_runner.py` | Call surface to exercise |

## Status

**Open** | Created: 2026-05-26 | Priority: P5

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:40:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-29T20:48:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`
- `/ll:capture-issue` - 2026-05-26T02:23:05Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e210ff4-bcab-4372-9c8c-a0ba98da62d5.jsonl`

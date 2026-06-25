---
id: FEAT-2192
title: "Conformance test suite \u2014 ll-auto/ll-sprint/ll-loop golden paths against\
  \ gemini -p"
type: feature
status: cancelled
priority: P4
parent: EPIC-2178
depends_on:
- ENH-2184
- ENH-2185
- FEAT-2186
- ENH-2187
captured_at: '2026-06-15T00:00:00Z'
discovered_date: 2026-06-15
discovered_by: capture-issue
labels:
- gemini
- host-compat
- tests
- conformance
---

# FEAT-2192: Conformance test suite — ll-auto/ll-sprint/ll-loop golden paths

## Resolution

**Cancelled 2026-06-25 — superseded by FEAT-2259.** The generic host-parameterized conformance harness covers the Gemini `gemini -p` golden paths (`--host gemini`). Per EPIC-2257 (ARCHITECTURE-049), per-host conformance / skill / command children are folded into the generic host-parameterized components rather than built bespoke. Run the equivalent capability via the generic tool with the appropriate `--host` argument.

## Summary

Create a conformance test suite that validates `ll-auto`, `ll-sprint`, and
`ll-loop` golden paths against `gemini -p`. Analogous to FEAT-1721 (Codex
conformance suite).

This is the final gate for EPIC-2178: proves that little-loops orchestration
works end-to-end with the Gemini runner, not just that the components exist.

## Use Case

A CI job or developer verification confirms that `LL_HOST_CLI=gemini ll-auto`
can process at least one issue end-to-end, that `ll-loop` FSM execution fires
hook events, and that streaming JSON output is parsed correctly.

## Implementation Steps

1. Create `scripts/tests/test_gemini_conformance.py` with:
   - `test_gemini_runner_build_streaming_invocation` — verify generated command
     args match expected Gemini flags (no subprocess needed; mock `shutil.which`)
   - `test_gemini_runner_build_blocking_json_invocation` — same
   - `test_gemini_runner_probe_returns_true_when_binary_on_path` — mock PATH
   - `test_gemini_hook_adapter_session_start_fires` — feed a `SessionStart`
     event payload through the adapter script and verify `LLHookEvent` is emitted
   - `test_gemini_hook_adapter_pre_tool_use_fires` — same for `BeforeTool`
2. Mark tests that require `gemini` binary with `@pytest.mark.requires_gemini`
   skip guard (so CI without Gemini installed still passes).
3. Update `scripts/tests/test_host_runner.py` to include Gemini in the
   "all registered hosts" coverage sweep.
4. Document manual golden-path verification steps in
   `docs/reference/HOST_COMPATIBILITY.md` Gemini column or a new
   `docs/guides/GEMINI_SETUP.md`.

## Acceptance Criteria

- `python -m pytest scripts/tests/test_gemini_conformance.py` passes without
  `gemini` on PATH (requires-gemini tests skipped).
- With `gemini` on PATH, `test_gemini_hook_adapter_session_start_fires` passes.
- `ll-auto --host gemini` can process one issue end-to-end (manual verification
  documented).
- `ll-loop run <any-loop> --host gemini` completes at least one iteration.

## API/Interface

### New Files

- `scripts/tests/test_gemini_conformance.py`

### Files to Modify

- `scripts/tests/test_host_runner.py` — Gemini in all-hosts sweep

## Research Notes (FEAT-2179)

- `gemini -p <prompt> -o stream-json` — streaming invocation
- `gemini -p <prompt> -o json` — blocking JSON invocation
- Hook protocol: stdin/stdout JSON, identical to Claude Code

Codex analog: `scripts/tests/test_codex_conformance.py` (FEAT-1721).

## Impact

- **Effort**: S–M (4–8 hours)
- **Risk**: Low — test-only; requires `gemini` binary for integration tests
- **Breaking Change**: No

---

## Verification Notes

2026-06-18 (BLOCKED): `scripts/tests/test_gemini_conformance.py` does not exist. `scripts/tests/conformance/` directory does not exist. All four dependencies (ENH-2184, ENH-2185, FEAT-2186, ENH-2187) remain unimplemented. Correctly blocked in practice.

**Open** | Created: 2026-06-15 | Priority: P4

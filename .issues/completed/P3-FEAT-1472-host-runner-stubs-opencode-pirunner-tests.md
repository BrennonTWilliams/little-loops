---
id: FEAT-1472
type: FEAT
priority: P3
status: done
parent: FEAT-1466
depends_on: FEAT-1464
discovered_date: 2026-05-15
completed_at: 2026-05-15T15:55:33Z
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1472: Host Runner Stubs — OpenCodeRunner + PiRunner + Tests

## Summary

Add `OpenCodeRunner` stub and `PiRunner` stub to `host_runner.py`, register both in the runner registry, add tests, run the grep sweep, and resolve the `evaluators.py` error message generalization. Option B (stub) is already decided for OpenCodeRunner — both runners raise `HostNotConfigured` from all four `build_*` methods.

## Parent Issue

Decomposed from FEAT-1466: OpenCodeRunner, PiRunner Stub, Docs Sweep, HOST_COMPATIBILITY.md Orchestration Row

## Scope

Covers Implementation Steps 3, 4, 5, 6, 7, and 16 from FEAT-1466. The grep sweep (Step 7) is scoped to exclude `subprocess_utils.py` pending FEAT-1469.

**Explicitly out of scope**: All documentation updates (FEAT-1473), Option A (full OpenCodeRunner with external CLI research).

## Acceptance Criteria

- [ ] `OpenCodeRunner` stub added to `scripts/little_loops/host_runner.py` after `CodexRunner` (~line 416); raises `HostNotConfigured("OpenCode orchestration not yet wired — research OpenCode headless CLI. Set LL_HOST_CLI=claude-code to use Claude Code instead.")` from all four `build_*` methods
- [ ] `PiRunner` stub added after `OpenCodeRunner`; raises `HostNotConfigured("Pi orchestration not yet wired — see FEAT-992. Set LL_HOST_CLI=claude-code to use Claude Code instead.")` from all four `build_*` methods
- [ ] Both runners registered in `_HOST_RUNNER_REGISTRY` (host_runner.py:422–425); `__all__` updated to export `OpenCodeRunner` and `PiRunner`
- [ ] `grep -rn '"claude"' scripts/little_loops/` (excluding `subprocess_utils.py`) returns no hard-coded binary literals beyond: `ClaudeCodeRunner.name`, `binary="claude"` inside `ClaudeCodeRunner.build_*`, comments/docstrings, `_PROBE_ORDER` tuple `("claude-code", "claude")`
- [ ] `evaluators.py:632,641,647` error strings generalized from hardcoded `"claude CLI not found"` / `"Claude CLI error"` / `"Claude CLI returned empty output"` to use `invocation.binary` (or explicitly documented as follow-up with a `# TODO(FEAT-XXXX):` comment). All three sites share the same try block; `invocation` (built at line 609) is in scope at every raise site.
- [ ] `TestOpenCodeRunner` added to `scripts/tests/test_host_runner.py`: registry presence, env-var resolve, all four build methods raise `HostNotConfigured`, protocol satisfaction (`isinstance(OpenCodeRunner(), HostRunner)`)
- [ ] `TestPiRunner` added to `scripts/tests/test_host_runner.py`: registry presence, env-var resolve (`resolve_host(env={"LL_HOST_CLI": "pi"})`), all four build methods raise `HostNotConfigured` with `"FEAT-992"` substring, protocol satisfaction
- [ ] `python -m pytest scripts/tests/test_host_runner.py -v` passes; no call-site regressions in full suite

## Proposed Solution

### OpenCodeRunner stub (Option B — decided)

```python
class OpenCodeRunner:
    name = "opencode"
    capabilities = HostCapabilities()  # all False — no orchestration yet

    def detect(self) -> bool:
        return shutil.which("opencode") is not None

    def build_streaming(self, *, **kwargs) -> HostInvocation:
        raise HostNotConfigured(
            "OpenCode orchestration not yet wired — research OpenCode headless CLI. "
            "Set LL_HOST_CLI=claude-code to use Claude Code instead."
        )

    # same body for build_blocking_json, build_version_check, build_detached
```

### PiRunner stub

```python
class PiRunner:
    name = "pi"
    capabilities = HostCapabilities()  # all False — no orchestration yet

    def detect(self) -> bool:
        return shutil.which("pi") is not None

    def build_streaming(self, *, **kwargs) -> HostInvocation:
        raise HostNotConfigured(
            "Pi orchestration not yet wired — see FEAT-992. "
            "Set LL_HOST_CLI=claude-code to use Claude Code instead."
        )

    # same body for build_blocking_json, build_version_check, build_detached
```

Note: `_PROBE_ORDER` already has `("pi", "pi")` but `_HOST_RUNNER_REGISTRY` has no `"pi"` key. Adding the registry entry causes probing on a `pi`-on-PATH host to return `PiRunner` and immediately raise `HostNotConfigured` on first `build_*` call. Do NOT add `("opencode", "opencode")` to `_PROBE_ORDER` (Option B per decision — no external CLI research done; no auto-probe risk).

### evaluators.py error message generalization (Step 16)

`scripts/little_loops/fsm/evaluators.py` has two hardcoded strings inside `evaluate_llm_structured()`:
- Line 632 (`except FileNotFoundError` block): `"claude CLI not found. Install from https://docs.anthropic.com/en/docs/claude-code"`
- Line 641 (non-zero returncode handler): `"Claude CLI error: {proc.stderr.strip()}"`

Generalize to use `invocation.binary` (already in scope of the function from the `resolve_host()` call). If `invocation` is not in scope at both sites, extract the binary name from the `HostInvocation` object before the try/except.

### Registry update

```python
_HOST_RUNNER_REGISTRY: dict[str, type] = {
    "claude-code": ClaudeCodeRunner,
    "codex": CodexRunner,
    "opencode": OpenCodeRunner,  # stub — FEAT-1472
    "pi": PiRunner,               # stub — FEAT-1472
}
```

`__all__` (host_runner.py module level): add `"OpenCodeRunner"` and `"PiRunner"`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Third hardcoded "Claude CLI" string discovered** at `evaluators.py:647` inside the empty-stdout guard: `error_msg = "Claude CLI returned empty output"`. Same `invocation` variable is in scope. Generalizing all three sites to `invocation.binary` is cleanest done as one pass.
- **`invocation.binary` scope confirmed**: `invocation` is built at `evaluators.py:609` and used at line 621 inside a single `try` block. The `except FileNotFoundError` (line 628), `if proc.returncode != 0` (line 638), and the empty-stdout guard (line 644–653) all execute in scope where `invocation` is bound. No extra extraction needed.
- **`_remediation_hint()` already advertises `opencode` and `pi`** at `host_runner.py:440–445` as valid `LL_HOST_CLI` values. Adding the registry entries makes the hint accurate (currently it points users at runners that fail at registry lookup with a generic "unknown host" error instead of a useful `HostNotConfigured` message).
- **Probe-order design pattern**: `_PROBE_ORDER` currently lists `("claude-code", "claude")` and `("pi", "pi")`; the codex row is commented out at `host_runner.py:435` (`# ("codex", "codex"),  # FEAT-1465: gated behind LL_HOST_CLI until validated`). For OpenCode, follow the same gated pattern — do NOT add `("opencode", "opencode")` to `_PROBE_ORDER` per Option B.
- **Protocol satisfaction is structural**: `HostRunner` (host_runner.py:100–154) is `@runtime_checkable` and requires `name: str`, `detect()`, `build_streaming()`, `build_blocking_json()`, `build_version_check()`, `build_detached()`. The Protocol does NOT include `capabilities` — it's a class-level attribute that exists on `ClaudeCodeRunner` and `CodexRunner` by convention. Adding `capabilities = HostCapabilities()` to the stubs preserves that convention.
- **Stub method signatures**: For protocol matching, `@runtime_checkable` only checks attribute presence (not signature), so `def build_streaming(self, *, **kwargs) -> HostInvocation:` works for `isinstance(OpenCodeRunner(), HostRunner)`. However, matching the full Protocol signature (e.g., `def build_streaming(self, *, prompt: str, working_dir: Path | None = None, resume: bool = False, agent: str | None = None, tools: list[str] | None = None) -> HostInvocation:`) is more consistent with `CodexRunner` (host_runner.py:268–416) and aids type-checking. Pick one style for both stubs.
- **Test import block update**: `scripts/tests/test_host_runner.py:13–30` imports `CapabilityNotSupported, ClaudeCodeRunner, CodexRunner, HostCapabilities, HostInvocation, HostNotConfigured, HostRunner, resolve_host` from `little_loops.host_runner`. Add `OpenCodeRunner, PiRunner` to that block.
- **Test pattern reference**: `TestCodexRunner` in `scripts/tests/test_host_runner.py:163–282` is the canonical model — particularly `test_codex_runner_registered` (registry presence check via `hr._HOST_RUNNER_REGISTRY`), `test_codex_runner_gated_from_auto_probe` (probe-order absence check via set comprehension), `test_resolve_host_picks_codex_via_env` (`isolated_env` fixture + `resolve_host(env={"LL_HOST_CLI": "codex"})`), and `test_satisfies_host_runner_protocol` (`isinstance` check).
- **Existing fixture**: `isolated_env` at `test_host_runner.py:33–38` already deletes both `LL_HOST_CLI` and `LL_HOOK_HOST` via `monkeypatch.delenv(..., raising=False)`. Reuse for any test that calls `resolve_host()`.
- **Probe-side-effect on `pi`-equipped hosts**: `_PROBE_ORDER` already contains `("pi", "pi")` (host_runner.py:436). Registering `PiRunner` in `_HOST_RUNNER_REGISTRY` activates the existing probe edge: on any host where `shutil.which("pi") is not None` (e.g., Python's `pi` package isn't on PATH by default, but some scientific Linux distros ship a `pi` binary), `resolve_host()` will succeed at probe time and immediately raise `HostNotConfigured` on the first `build_*` call. Worth a test: `test_pirunner_probe_returns_stub_not_raise` — `resolve_host(env={"LL_HOST_CLI": "pi"})` returns `PiRunner`, then the first `build_*` raises.

## Files to Modify

- `scripts/little_loops/host_runner.py` — add `OpenCodeRunner`, `PiRunner`, update registry and `__all__`
- `scripts/tests/test_host_runner.py` — add `TestOpenCodeRunner` and `TestPiRunner` classes
- `scripts/little_loops/fsm/evaluators.py` — generalize two hardcoded "claude CLI" error strings

## Similar Patterns to Follow

- `CodexRunner` at `scripts/little_loops/host_runner.py:268–416` (full runner reference)
- `TestCodexRunner` in `scripts/tests/test_host_runner.py:160–282` (test class reference)
- `isolated_env` fixture (deletes `LL_HOST_CLI` and `LL_HOOK_HOST` from env) in `test_host_runner.py`
- `pytest.raises(HostNotConfigured)` pattern for stub method tests

## Dependent Call Sites (must not regress)

- `scripts/little_loops/fsm/evaluators.py:609` — `build_blocking_json`
- `scripts/little_loops/fsm/handoff_handler.py:116` — `build_detached`
- `scripts/little_loops/parallel/worker_pool.py:576` — `build_blocking_json`
- `scripts/little_loops/cli/action.py:143` — `resolve_host()` + `build_version_check()`

## Integration Map

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_fsm_evaluators.py` — **update (will break)**: `TestLLMStructuredEvaluator.test_cli_not_found` (line 578) asserts `"claude CLI not found" in result.details["error"]` as a substring match. When `evaluators.py` generalizes to `invocation.binary`, the produced string changes. Update the assertion to match the new format (e.g., assert `"CLI not found"` or patch `resolve_host` to return a deterministic runner). [Agent 2 + Agent 3 finding]
- `scripts/tests/test_fsm_evaluators.py` — **low-risk, verify**: `TestLLMStructuredEvaluator.test_empty_stdout` (line 714) asserts `"empty output" in result.details["error"]`. The generalized form `f"{invocation.binary} CLI returned empty output"` still contains `"empty output"`, so this should survive — but verify after the change. [Agent 3 finding]

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. After generalizing `evaluators.py` error strings, update `scripts/tests/test_fsm_evaluators.py::TestLLMStructuredEvaluator.test_cli_not_found` — change the assertion from `"claude CLI not found"` to match the generalized format (e.g., `"CLI not found"` or the `invocation.binary`-prefixed form). This test patches `subprocess.run` to raise `FileNotFoundError` and asserts on the detail string — it will fail if the literal is not updated.
2. After the update, verify `TestLLMStructuredEvaluator.test_empty_stdout` still passes — the `"empty output"` substring should survive the rename but confirm.

## Dependencies

- **FEAT-1464** must land first (provides `host_runner.py` scaffold)
- Can run in parallel with **FEAT-1473**

## Resolution

Implemented stub `OpenCodeRunner` and `PiRunner` in `scripts/little_loops/host_runner.py`, both raising `HostNotConfigured` from all four `build_*` methods with explicit remediation hints (OpenCode → "research OpenCode headless CLI"; Pi → "see FEAT-992"). Registered both in `_HOST_RUNNER_REGISTRY` and exported via `__all__`. Per Option B, neither runner is added to `_PROBE_ORDER` for OpenCode; `("pi", "pi")` was already present, so the existing probe edge now resolves to `PiRunner` and raises on first `build_*`.

Generalized three hardcoded "claude CLI" / "Claude CLI" strings in `scripts/little_loops/fsm/evaluators.py` (lines 632, 641, 647) to interpolate `invocation.binary`, removing host-specific language from generic LLM evaluator errors. Updated `test_fsm_evaluators.py::test_cli_not_found` substring assertion to match the new format.

Added `TestOpenCodeRunner` (8 tests) and `TestPiRunner` (8 tests including a probe-edge regression test) to `scripts/tests/test_host_runner.py`. Final grep sweep `grep -rn '"claude"' scripts/little_loops/` returns only the AC-allowlisted hits (ClaudeCodeRunner internals + `_PROBE_ORDER`).

Verification: 180/180 host_runner + fsm_evaluators tests pass; ruff check clean; full suite shows 4 pre-existing unrelated failures (README pillar structure, marketplace version sync) confirmed via baseline stash check.

## Session Log
- `/ll:manage-issue` - 2026-05-15T15:55:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:ready-issue` - 2026-05-15T15:50:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8deac8af-c5de-4807-817f-1b9912d1023b.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/375f80ed-3900-4806-8b03-4306d0c74628.jsonl`
- `/ll:wire-issue` - 2026-05-15T15:47:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1cd4a684-4816-432f-9db3-7807637be7d8.jsonl`
- `/ll:refine-issue` - 2026-05-15T15:43:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/493efa0f-c223-4f2e-a5b0-f39c3316eb4e.jsonl`
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3404bce4-b1e1-4c4a-bdaf-327d629a43da.jsonl`

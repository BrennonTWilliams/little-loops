---
discovered_date: 2026-03-31
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 86
---

# BUG-903: `llm_structured` evaluator 1800s timeout causes 30-min hang when API is unavailable

## Summary

The `evaluate_with_llm()` function in `evaluators.py` uses a default `timeout=1800` (30 minutes) for the Claude CLI subprocess. When the claude CLI stalls on network I/O (API rate limiting or transient auth failure), the loop silently blocks for the full 1800 seconds before failing. This manifests in the `refine-to-ready-issue` built-in loop's `confidence_check` state, where a trivial threshold-comparison evaluation (two numbers vs. two thresholds) idles at 0.4% CPU for 30 minutes waiting for an unresponsive API.

## Current Behavior

When the `confidence_check` state in `refine-to-ready-issue` triggers an `llm_structured` evaluation:

1. `evaluate_with_llm()` spawns a `claude -p <prompt> --output-format json ...` subprocess with the default `timeout=1800`
2. If the Claude API is unavailable (rate limit, transient auth failure), the `claude` CLI stalls at 0.4% CPU, sleeping on network I/O
3. The loop blocks for the full 30 minutes before `subprocess.TimeoutExpired` is raised
4. Total loop runtime becomes ~40 minutes even though all productive work (format + refine + confidence action) completes in ~10 minutes

Timeline observed in testing:
- `confidence_check` action: ~2 min (OK)
- `confidence_check` evaluate (llm_structured): 30 min (TIMEOUT)

## Expected Behavior

The `llm_structured` evaluator should fail fast on API unavailability. For trivial evaluation prompts (checking if two scores meet two thresholds), a 60–120s timeout is sufficient for even slow API responses. The loop should surface an error within minutes, not 30 minutes, allowing for retry or manual intervention.

## Motivation

Automated loops like `refine-to-ready-issue` run unattended overnight or in CI. A 30-minute silent hang is invisible until the full timeout expires. The 1800s default was introduced in ENH-763 to prevent spurious failures from slow API responses, but it now masks real infrastructure failures (rate limits, auth issues) for an unreasonably long time. For trivial prompts — the `confidence_check` evaluate prompt is literally "is score A > 90 and score B > 75?" — even 60s is generous.

## Steps to Reproduce

1. Run `ll-loop run refine-to-ready-issue` on a project with pending issues
2. After the `confidence_check` action completes (at ~12 minutes), watch the evaluate step stall
3. Observe: the evaluate subprocess (pid visible via `ps`) shows 0.4% CPU for 30 minutes before failing with `"LLM evaluation timeout"`

Alternatively, reproduce by directly calling `evaluate_with_llm()` while the Anthropic API is rate-limited or unreachable.

## Root Cause

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Anchor**: `in function evaluate_with_llm()`
- **Cause**: `timeout: int = 1800` default at line 536 is applied uniformly to all `llm_structured` evaluation prompts regardless of complexity. The subprocess runs `claude -p <prompt> --output-format json --json-schema ... --dangerously-skip-permissions --no-session-persistence` (lines 565–577) and calls `subprocess.run(..., timeout=timeout)` at line 581. When the claude CLI idles on API I/O, no intermediate heartbeat or retry is possible — the caller simply waits for `subprocess.TimeoutExpired`.

There is no mechanism in the loop YAML `evaluate:` config to override the timeout per state, so all `llm_structured` evaluators inherit the 1800s default.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Function name correction**: The actual function name is `evaluate_llm_structured()` (not `evaluate_with_llm()`). Signature at `evaluators.py:528–537`; timeout default at `evaluators.py:536`; subprocess call at `evaluators.py:581`.

**Two dispatch paths — only Path B is affected**:
- **Path A** (implicit, no `evaluate:` block in YAML): `executor.py:839–858` calls `evaluate_llm_structured(..., timeout=self.fsm.llm.timeout)`. Already controllable via the top-level `llm: timeout:` block in loop YAML. Default comes from `LLMConfig.timeout` at `schema.py:361`.
- **Path B** (explicit `evaluate: type: llm_structured` block): `evaluators.py:817–830` calls `evaluate_llm_structured(output, prompt, schema, min_confidence, uncertain_suffix)` with **no `timeout` argument**, unconditionally falling back to the 1800s default. The `confidence_check` state in `refine-to-ready-issue.yaml:31–43` uses this path.

**Schema gap**: `EvaluateConfig` dataclass (`schema.py:24–80`) has no `timeout` field. Until one is added, Path B cannot be overridden per-state regardless of YAML content.

## Proposed Solution

**Option A (recommended)**: Lower the default timeout in `evaluate_with_llm()` from 1800s to 120s. Two minutes is generous for trivial prompts and still handles slow API responses.

```python
# scripts/little_loops/fsm/evaluators.py
def evaluate_with_llm(
    output: str,
    ...
    timeout: int = 120,  # was 1800 (ENH-763); 120s is sufficient for trivial prompts
) -> EvaluationResult:
```

**Option B**: Expose `timeout` as an optional field in FSM state `evaluate:` config blocks. Pass it through from the loop YAML to `evaluate_with_llm()`. This gives per-state control for loops with more complex evaluation prompts.

**Recommended**: Implement both — lower the default to 120s AND add optional `timeout:` override in `evaluate:` config.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_with_llm()` default timeout parameter

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — dispatches to `evaluate_with_llm()` for `llm_structured` type
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `confidence_check` state uses `llm_structured` evaluate

### Similar Patterns
- `scripts/little_loops/fsm/evaluators.py:405` — tool evaluator uses its own 30s timeout (separate code path, unaffected)

### Tests
- `scripts/tests/fsm/test_evaluators.py` — add test verifying new default and `TimeoutExpired` path

### Documentation
- `docs/reference/API.md` — update `evaluate_with_llm()` signature docs if timeout default is documented

### Configuration
- `config-schema.json` — add `timeout` field to state `evaluate:` block schema if Option B is implemented

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Additional Files to Modify (Option A + B)
- `scripts/little_loops/fsm/evaluators.py:536` — change `timeout: int = 1800` → `timeout: int = 120` (Option A)
- `scripts/little_loops/fsm/evaluators.py:817–830` — add `timeout=config.timeout` to `evaluate_llm_structured()` call in the explicit `llm_structured` dispatcher branch (Option B)
- `scripts/little_loops/fsm/schema.py:74–140` — add `timeout: int | None = None` field to `EvaluateConfig`; update `to_dict` (following `min_confidence` skip-if-default pattern at `schema.py:103–104`) and `from_dict` (following `schema.py:133`)
- `scripts/little_loops/fsm/schema.py:361` — also change `LLMConfig.timeout` default from `1800` → `120` to fix Path A implicit evaluations
- `scripts/little_loops/fsm/validation.py:155–173` — add `timeout > 0` validation for `llm_structured` following `min_confidence` block pattern
- `scripts/little_loops/fsm/fsm-loop-schema.json:300` — add `timeout` integer field to `evaluateConfig` JSON schema definition (**not** `config-schema.json`; the FSM loop schema lives here); follow `min_confidence` pattern at lines 300–305 and the existing `llmConfig.timeout` definition at lines 383–389

#### Dependent Files (callers / test assertions requiring updates)
- `scripts/little_loops/fsm/executor.py:853–858` — Path A explicit call site; once `LLMConfig.timeout` default changes, no code change needed here, but verify fallback behavior is correct
- `scripts/tests/test_fsm_schema.py:489` — asserts `config.timeout == 1800` for `LLMConfig` default; **must update** to `120` after the default change
- `scripts/tests/test_fsm_evaluators.py:692–701` — `test_cli_timeout_handling` already mocks `TimeoutExpired`; extend to assert new default value is `120` and add a dispatcher-passthrough test following `test_dispatch_diff_stall_with_options` at `test_fsm_evaluators.py:1102–1112`

#### Confirmed Similar Patterns
- `schema.py:80, 103–104, 115–116, 133, 139` — `max_stall` field: complete end-to-end template for optional integer in `EvaluateConfig` (field declaration, `to_dict`, `from_dict`)
- `evaluators.py:811–815` — `diff_stall` dispatcher passing `max_stall=config.max_stall` — structural template for wiring new field through `evaluate()` dispatcher
- `fsm-loop-schema.json:363–391` — `llmConfig.timeout` JSON schema entry — direct template for the new `evaluateConfig.timeout` field definition
- `test_fsm_evaluators.py:569–576` — `mock_cli` fixture pattern; use `mock_run.call_args.kwargs["timeout"]` to assert the timeout value passed to `subprocess.run()`

## Implementation Steps

1. In `evaluate_with_llm()` (`evaluators.py`), change `timeout: int = 1800` to `timeout: int = 120`
2. In the FSM executor (`executor.py`), add support for optional `timeout` field in state `evaluate:` config, passing it to `evaluate_with_llm()`
3. Update `config-schema.json` to allow `timeout` in `evaluate:` blocks (if Option B)
4. Add test coverage in `test_evaluators.py` for the new default and timeout error path
5. Verify `refine-to-ready-issue` runs cleanly end-to-end with the reduced default

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Concrete file:line references and order correction:

1. `evaluators.py:536` — change `timeout: int = 1800` → `timeout: int = 120`
2. `schema.py:361` — change `LLMConfig.timeout` default `1800` → `120` (fixes Path A implicit evaluations)
3. `schema.py:74–140` — add `timeout: int | None = None` to `EvaluateConfig` following `min_confidence` pattern; update `to_dict` skip-if-None (line ~116), update `from_dict` with `data.get("timeout")` (line ~139)
4. `evaluators.py:817–830` — add `timeout=config.timeout` to the `evaluate_llm_structured()` call in the `llm_structured` dispatcher branch (this is the actual fix for Path B, not `executor.py`)
5. `validation.py:155–173` — add `if evaluate.type == "llm_structured" and evaluate.timeout is not None and evaluate.timeout < 1: errors.append(ValidationError(...))` following `min_confidence` block
6. `fsm-loop-schema.json:300` — add `"timeout"` integer property to `evaluateConfig` definition (**not** `config-schema.json`); follow the `min_confidence` entry at lines 300–305 and `llmConfig.timeout` at lines 383–389 for format
7. `test_fsm_evaluators.py:692–701` — update `test_cli_timeout_handling` to assert new default; add a passthrough test modeled on `test_dispatch_diff_stall_with_options:1102–1112`
8. `test_fsm_schema.py:489` — update `assert config.timeout == 1800` → `assert config.timeout == 120`

## Impact

- **Priority**: P2 — Causes 30-minute unattended hangs in production; directly observed in testing another project
- **Effort**: Small — single default parameter change; Option B adds minor config plumbing
- **Risk**: Low — 120s is still generous for API latency; users needing longer timeouts can override per-state via Option B
- **Breaking Change**: No — existing callers that pass an explicit `timeout` argument are unaffected

## Related Key Documentation

- `.issues/completed/P3-ENH-763-raise-llm-evaluation-timeout-default-to-1800s.md` — completed enhancement that originally set the 1800s default; provides prior decision context
- `docs/guides/LOOPS_GUIDE.md:321, 396–404` — `llm_structured` evaluator user-facing documentation (may need timeout guidance added)
- `docs/reference/API.md:3545, 3697–3707` — `evaluate_llm_structured` Python API reference; documents `timeout` parameter location in `LLMConfig` and `EvaluateConfig` dataclass fields

## Labels

`bug`, `fsm`, `loops`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-03-31T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6df5ee0a-f20f-4ab8-a215-3c707d7115cd.jsonl`
- `/ll:refine-issue` - 2026-04-01T03:03:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6df5ee0a-f20f-4ab8-a215-3c707d7115cd.jsonl`
- `/ll:format-issue` - 2026-04-01T02:47:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/df3e7853-3ef3-4208-af09-bf629e0fa561.jsonl`
- `/ll:capture-issue` - 2026-03-31T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/afd36911-09cb-4a84-a407-9174c8f43270.jsonl`

---

## Status

**Won't Do** | Created: 2026-03-31 | Closed: 2026-03-31 | Priority: P2

The 1800s timeout is intentional and necessary for complex evaluation tasks. Reducing the default would cause spurious failures for loops with expensive LLM evaluations. Closing as won't do.

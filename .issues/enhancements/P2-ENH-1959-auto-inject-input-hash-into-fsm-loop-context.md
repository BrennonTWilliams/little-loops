---
id: ENH-1959
type: ENH
priority: P2
status: open
captured_at: '2026-06-05T18:05:10Z'
discovered_date: 2026-06-05
discovered_by: capture-issue
parent: EPIC-1962
confidence_score: 100
decision_needed: false
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1959: Auto-Inject input_hash into FSM Loop Context for Checkpoint Fingerprinting

## Summary

The FSM runner injects `${context.run_dir}` (a timestamped per-run directory) into every loop's context, but does NOT inject `${context.input_hash}` or any task-identity token. Loops that implement checkpoint/resume (like `general-task.yaml`) must compute their own task hash using platform-specific shell commands (`md5 -q` on macOS, `md5sum` on Linux) to verify that a checkpoint belongs to the same task. This is fragile, platform-dependent, and easy to omit — leading to cross-task checkpoint contamination.

The runner already has all necessary information: it receives `input` as a positional argument and populates `fsm.context["input"]`. Adding `input_hash` is a trivial one-line change at the injection site in `scripts/little_loops/cli/loop/run.py`.

## Current Behavior

Loops that need to fingerprint checkpoint state to the current task must compute a hash inline in shell actions:

```bash
TASK_HASH=$(echo "${context.input}" | md5 -q 2>/dev/null || echo "${context.input}" | md5sum 2>/dev/null | cut -d' ' -f1)
```

Problems:
1. **Platform-dependent**: `md5 -q` (macOS) vs `md5sum` (Linux) requires a fallback chain
2. **Error-prone**: If both commands fail silently, `TASK_HASH` is empty and fingerprinting is skipped
3. **Boilerplate**: Every loop that wants checkpoint safety must copy this incantation
4. **Missing entirely**: The current `general-task.yaml` has NO task fingerprinting, which directly caused the 2026-06-05 failure (stale checkpoint from unrelated task triggered false `RESUME_SKIP`)

## Expected Behavior

The runner should auto-inject `${context.input_hash}` alongside the existing `${context.run_dir}`. Loops can then use it directly:

```bash
STORED_HASH=$(grep -o '"task_hash":"[^"]*"' "$CHECKPOINT" | ...)
if [ "$STORED_HASH" != "${context.input_hash}" ]; then
  rm -f "$CHECKPOINT"
  echo "RESUME_CLEAN"
  exit 0
fi
```

`input_hash` should be:
- A hex digest (e.g., SHA-256 truncated to 12 hex chars) of `${context.input}`
- Always present when `${context.input}` is non-empty
- Stable for the same input string (deterministic)
- Available in both shell and prompt action types

## Motivation

- **Prevents cross-task contamination**: The 2026-06-05 `general-task` failure was caused by a stale checkpoint from a prior unrelated task. Fingerprinting would have prevented it
- **Trivial to implement**: ~5 lines in `run.py`, no new dependencies
- **Broadly useful**: Any loop with checkpoint/resume logic benefits, not just `general-task`
- **Eliminates platform-specific code**: Loop authors write `${context.input_hash}` instead of the `md5`/`md5sum` dance

## Proposed Solution

In `scripts/little_loops/cli/loop/run.py`, after the context injection block (where `run_dir` is injected at line 161), add:

```python
# Inject input hash for checkpoint fingerprinting
if "input_hash" not in fsm.context and fsm.context.get("input"):
    fsm.context["input_hash"] = hashlib.sha256(
        fsm.context["input"].encode()
    ).hexdigest()[:12]
```

In `scripts/little_loops/cli/loop/lifecycle.py`, after the `run_dir` re-injection block (lines 461-464), add the same injection so `input_hash` is available during resumed runs:

```python
# Re-inject input_hash for resume (input already restored from persisted state)
if "input_hash" not in fsm.context and fsm.context.get("input"):
    fsm.context["input_hash"] = hashlib.sha256(
        fsm.context["input"].encode()
    ).hexdigest()[:12]
```

In `scripts/little_loops/fsm/validation.py`, add `input_hash` to the `RUNNER_INJECTED` set (line 422) so the validator knows it's runner-provided and doesn't flag it as a missing fragment parameter binding:

```python
RUNNER_INJECTED = {"run_dir", "loop_name", "started_at", "input_hash"}
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`RUNNER_INJECTED` location correction**: The set is at `validation.py:422` inside `_validate_fragment_bindings()`, not in `schema.py` as originally stated. It currently contains `{"run_dir", "loop_name", "started_at"}`. Corrected in Integration Map and Proposed Solution above.
- **Resume path (`lifecycle.py`)**: `cmd_resume()` re-injects `run_dir` at lines 461-464 and `design_tokens_context` at lines 496-498. Both `cmd_run()` and `cmd_resume()` must inject `input_hash` for it to be available in all execution paths. Added to Files to Modify and Implementation Steps.
- **`hashlib` not yet imported in `run.py`**: No existing `import hashlib` in `run.py`. Must be added (already imported in `session_store.py`, `evaluators.py`, and `history_context.py` — established pattern).
- **No existing platform-specific hashing in loops**: A grep for `md5sum`, `sha256sum`, `input_hash`, `task_hash`, and `fingerprint` across all loop YAMLs returned zero matches. The platform-specific hashing pattern described in "Current Behavior" is aspirational — no loop currently attempts task fingerprinting, which is exactly why `general-task.yaml` had no protection against the BUG-1960 cross-task contamination scenario.
- **Existing SHA-256 truncation precedent**: `_content_hash()` at `history_context.py:47-48` uses `hashlib.sha256(content.encode()).hexdigest()[:16]` — same pattern, different truncation length. The proposed 12-char truncation matches the existing MD5 cache-key convention at `evaluators.py:464`.
- **Fragment parameter validation**: `RUNNER_INJECTED` only affects `_validate_fragment_bindings()` — if a fragment declares `input_hash` as a required parameter, the validator skips it as a static error. This is consistent with how `run_dir`, `loop_name`, and `started_at` are handled today.

## API/Interface

N/A — No new public API or CLI surface. `${context.input_hash}` is a runner-injected context variable exposed to loop actions (shell and prompt), following the existing `${context.run_dir}` injection pattern:

- **Key**: `fsm.context["input_hash"]`
- **Type**: `str | None` — hex digest string when `input` is non-empty, absent otherwise
- **Stability**: Deterministic for identical input strings (SHA-256 truncated to 12 hex chars)
- **Backwards compatible**: Additive only — no existing context keys or interfaces are modified

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py:161` — inject `input_hash` after existing `run_dir` injection (`cmd_run()`, line 161-162)
- `scripts/little_loops/cli/loop/lifecycle.py:461` — inject `input_hash` during resume (follows `run_dir` re-injection at lines 461-464 and `design_tokens_context` re-injection at lines 496-498)
- `scripts/little_loops/fsm/validation.py:422` — add `input_hash` to `RUNNER_INJECTED` set inside `_validate_fragment_bindings()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py:461` — `cmd_resume()` must also inject `input_hash` (follows `run_dir` re-injection pattern); without this, resumed runs would lack `input_hash`
- `scripts/little_loops/loops/general-task.yaml` — consumer (after BUG-1960 migration to `run_dir`); can use `${context.input_hash}` in `select_step` checkpoint and `resume_check` validation
- `scripts/little_loops/loops/rn-implement.yaml:239` — already writes checkpoint to `${context.run_dir}/checkpoint.json`; can add `task_hash` field for fingerprinting
- Any loop implementing checkpoint/resume — can adopt `${context.input_hash}` for fingerprinting

### Similar Patterns
- `${context.run_dir}` — already injected by runner at `run.py:161`; `input_hash` follows the same pattern (guard: `if "input_hash" not in fsm.context`)
- `RUNNER_INJECTED` in `validation.py:422` — existing set `{"run_dir", "loop_name", "started_at"}` for runner-provided context keys; `input_hash` joins them
- `design_tokens_context` injection at `run.py:181-183` and `lifecycle.py:496-498` — most recent runner-injected context variable, pattern for both `cmd_run()` and `cmd_resume()` paths
- `hashlib.sha256(content.encode()).hexdigest()[:16]` — existing SHA-256 truncation pattern at `history_context.py:47-48` (`_content_hash()`) and `session_store.py:791`
- `hashlib.md5(scope_str.encode()).hexdigest()[:12]` — existing 12-char truncation convention at `evaluators.py:464` (matches the proposed 12-char truncation for `input_hash`)

### Tests
- `scripts/tests/test_ll_loop_program_md.py:282` — add test modeled on `test_design_tokens_context_injected_into_context()`: verify `input_hash` is injected into `fsm.context` by `cmd_run()`
- `scripts/tests/test_fsm_validation.py:1980` — add test modeled on `test_runner_injected_vars_not_flagged()`: verify fragment states declaring `input_hash` as a required parameter don't trigger false-positive validation errors
- `scripts/tests/test_cli_loop_lifecycle.py:637` — add test modeled on `test_design_tokens_context_injected_via_cmd_resume()`: verify `input_hash` is re-injected by `cmd_resume()`
- `scripts/tests/test_ll_loop_execution.py` — integration test: after `ll-loop run <loop> "some task input"`, `fsm.context["input_hash"]` is present and deterministic
- `scripts/tests/test_ll_loop_commands.py:2624` — add adjacent test modeled on `test_positional_input_injected_into_context()`: verify `input_hash` is stable for same input, different for different inputs

### Documentation
- `docs/generalized-fsm-loop.md` — document `${context.input_hash}` alongside `${context.run_dir}`
- `docs/guides/LOOPS_GUIDE.md` — add example of using `input_hash` for checkpoint fingerprinting

## Implementation Steps

1. **Import `hashlib`** — add `import hashlib` to `run.py` (not currently imported) and `lifecycle.py`
2. **Inject `input_hash` in `cmd_run()`** — in `run.py:161-162`, after the `run_dir` injection block, compute SHA-256 hash of `fsm.context.get("input")` truncated to 12 hex chars; inject as `fsm.context["input_hash"]` (guarded: `if "input_hash" not in fsm.context and fsm.context.get("input")`)
3. **Inject `input_hash` in `cmd_resume()`** — in `lifecycle.py:461-464`, after the `run_dir` re-injection block, add the same hash computation so `input_hash` is available during resumed runs
4. **Update `RUNNER_INJECTED`** — add `"input_hash"` to the set at `validation.py:422` inside `_validate_fragment_bindings()`
5. **Add tests** — unit test for deterministic hashing (model after `test_design_tokens_context_injected_into_context()` in `test_ll_loop_program_md.py:282`), fragment validation test (model after `test_runner_injected_vars_not_flagged()` in `test_fsm_validation.py:1980`)
6. **Update docs** — two doc files as listed above
7. **Adopt in general-task.yaml** — after BUG-1960 migration, use `${context.input_hash}` in checkpoint write/validate

## Success Metrics

- **Correctness**: `fsm.context["input_hash"]` is present in every loop run with non-empty input (verified by integration test)
- **Determinism**: Same input string produces identical `input_hash` across runs (verified by unit test)
- **Uniqueness**: Different input strings produce different hashes (verified by unit test)
- **Adoption**: `general-task.yaml` uses `${context.input_hash}` for checkpoint fingerprinting (post-BUG-1960 migration)
- **Elimination**: Zero platform-specific `md5`/`md5sum` shell commands remain in loop YAMLs for task hashing

## Scope Boundaries

- **In scope**:
  - Injecting `input_hash` into FSM context at runner level (`run.py`)
  - Adding `input_hash` to `RUNNER_INJECTED` set for validator awareness (`schema.py`)
  - Tests verifying presence, determinism, and uniqueness
  - Documentation updates (two files listed in Integration Map)

- **Out of scope**:
  - Changing the hash algorithm (SHA-256 with 12-char truncation is fixed)
  - Modifying how individual loops consume the hash beyond adopting it in `general-task.yaml`
  - Broader context injection refactoring beyond `input_hash`
  - Backfilling `input_hash` into historical loop runs or session logs

## Impact

- **Priority**: P2 — Directly prevents the cross-task contamination class of bugs; trivial to implement
- **Effort**: Trivial — ~5 lines of Python + tests + docs
- **Risk**: Very Low — additive change; no existing behavior modified
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `fsm`, `context`, `checkpoint`, `loops`

## Session Log
- `/ll:refine-issue` - 2026-06-05T18:28:22 - `af4bc73a-d7d6-4402-89e0-fccdfe0db04b.jsonl`
- `/ll:format-issue` - 2026-06-05T18:13:35 - `b727da36-5701-4920-98db-1291d7539e68.jsonl`
- `/ll:capture-issue` - 2026-06-05T18:05:10Z - `6111e846-8894-477b-81b3-17824f89e659.jsonl`
- `/ll:confidence-check` - 2026-06-05T19:45:00Z - `e5bf076d-b9d5-49f4-95a7-3015337eb380.jsonl`

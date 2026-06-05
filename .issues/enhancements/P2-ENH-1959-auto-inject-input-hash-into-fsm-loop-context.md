---
id: ENH-1959
type: ENH
priority: P2
status: open
captured_at: "2026-06-05T18:05:10Z"
discovered_date: 2026-06-05
discovered_by: capture-issue
parent: EPIC-1962
confidence_score: 95
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

In `scripts/little_loops/cli/loop/run.py`, after the context injection block (where `run_dir` is injected), add:

```python
# Inject input hash for checkpoint fingerprinting
if fsm.context.get("input"):
    fsm.context["input_hash"] = hashlib.sha256(
        fsm.context["input"].encode()
    ).hexdigest()[:12]
```

In `scripts/little_loops/fsm/schema.py`, add `input_hash` to the `RUNNER_INJECTED` set (line ~420) so the validator knows it's runner-provided and doesn't flag it as missing.

## API/Interface

N/A — No new public API or CLI surface. `${context.input_hash}` is a runner-injected context variable exposed to loop actions (shell and prompt), following the existing `${context.run_dir}` injection pattern:

- **Key**: `fsm.context["input_hash"]`
- **Type**: `str | None` — hex digest string when `input` is non-empty, absent otherwise
- **Stability**: Deterministic for identical input strings (SHA-256 truncated to 12 hex chars)
- **Backwards compatible**: Additive only — no existing context keys or interfaces are modified

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py` — inject `input_hash` after existing `run_dir` injection (~line 162)
- `scripts/little_loops/fsm/schema.py` — add `input_hash` to `RUNNER_INJECTED` set

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/general-task.yaml` — consumer (after BUG-1960 migration to `run_dir`); can use `${context.input_hash}` in `select_step` checkpoint and `resume_check` validation
- Any loop implementing checkpoint/resume — can adopt `${context.input_hash}` for fingerprinting

### Similar Patterns
- `${context.run_dir}` — already injected by runner; `input_hash` follows the same pattern
- `RUNNER_INJECTED` in `validation.py` — existing set for runner-provided context keys; `input_hash` joins `run_dir`, `loop_name`, `started_at`

### Tests
- `scripts/tests/test_ll_loop_execution.py` — add test: after `ll-loop run <loop> "some task input"`, `fsm.context["input_hash"]` is present and deterministic
- `scripts/tests/test_fsm_executor.py` — add test: `input_hash` is stable for same input, different for different inputs

### Documentation
- `docs/generalized-fsm-loop.md` — document `${context.input_hash}` alongside `${context.run_dir}`
- `docs/guides/LOOPS_GUIDE.md` — add example of using `input_hash` for checkpoint fingerprinting

## Implementation Steps

1. **Inject `input_hash`** — in `run.py`, compute SHA-256 hash of `fsm.context.get("input", "")` truncated to 12 hex chars; inject as `fsm.context["input_hash"]`
2. **Update `RUNNER_INJECTED`** — add `"input_hash"` to the set in `schema.py` or `validation.py`
3. **Add tests** — unit test for deterministic hashing, integration test for presence in context
4. **Update docs** — two doc files as listed above
5. **Adopt in general-task.yaml** — after BUG-1960 migration, use `${context.input_hash}` in checkpoint write/validate

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
- `/ll:format-issue` - 2026-06-05T18:13:35 - `b727da36-5701-4920-98db-1291d7539e68.jsonl`
- `/ll:capture-issue` - 2026-06-05T18:05:10Z - `6111e846-8894-477b-81b3-17824f89e659.jsonl`

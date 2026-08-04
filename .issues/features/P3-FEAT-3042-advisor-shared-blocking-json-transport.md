---
id: FEAT-3042
title: Advisor transport - shared run_blocking_json helper
type: FEAT
parent: FEAT-3037
priority: P3
status: open
testable: true
discovered_date: 2026-08-04
labels:
- planning-hub
---

# FEAT-3042: Advisor transport - shared run_blocking_json helper

## Summary

Extract the per-call host resolution and structured-output run-and-parse loop
out of `evaluate_llm_structured` into reusable `host_runner.py` helpers
(`resolve_host_named`, `run_blocking_json`), and migrate
`evaluate_llm_structured` onto the extracted helper. This is the shared
transport the advisor (FEAT-3044) consumes later — it ships and is tested
independently of the advisor surface.

## Parent Issue

Decomposed from FEAT-3037: Host-agnostic advisor. FEAT-3037 scored Very Large
(11/11) on `ll-issues size` and covers three architecturally separable
concerns (shared transport, config plumbing, advisor core + CLI). This child
covers the transport concern.

## Current Behavior

- `resolve_host()` (`host_runner.py:1564`) resolves **one** host per process,
  from `LL_HOST_CLI` / `LL_HOOK_HOST` / a PATH probe. Every existing call site
  calls it bare — there is no per-call host selection anywhere in the
  codebase.
- Structured-output handling is inlined in `evaluate_llm_structured`
  (`fsm/evaluators.py:1083-1268`): builders drop the `json_schema` argument,
  `_structured_output_args` re-appends `--json-schema`/`--no-session-persistence`
  only for hosts advertising `HostCapabilities.structured_output`, and the
  run-subprocess-and-parse loop (timeout, empty-stdout-with-exit-0 guard, JSON
  envelope extraction with JSONL/tag fallbacks, `cleanup_paths` unlinking)
  exists only inline in that one function.

## Expected Behavior

- `resolve_host_named(name: str) -> HostRunner` resolves a specific registered
  host, ignoring ambient `LL_HOST_CLI`, without mutating process-global state.
- `run_blocking_json(invocation, *, schema=None, timeout=180) -> dict | None`
  executes a blocking invocation and returns parsed JSON, handling: host-gated
  schema flags, the timeout, the empty-stdout-with-exit-0 guard, the JSON
  envelope extraction (whole-string parse → last-non-blank-line JSONL fallback
  → tag fallback), and `HostInvocation.cleanup_paths` unlinking (including on
  failure/timeout).
- `evaluate_llm_structured` is refactored onto `run_blocking_json` with
  **unchanged external behavior** — same error-handling order, same error
  messages, same schema-conditional evidence coercion left in the caller (not
  pushed into the shared helper).
- Existing FSM evaluator tests pass without edits (AC #13 from the parent).

## Proposed Solution

### Per-call host resolution

```python
def resolve_host_named(name: str) -> HostRunner:
    """Resolve a specific registered host, ignoring ambient LL_HOST_CLI."""
    return resolve_host({"LL_HOST_CLI": name})
```

`resolve_host()` already accepts an optional `env: dict[str, str] | None`
param (defaults to `dict(os.environ)`) — this is a one-line wrapper, no
signature change to `resolve_host` itself.

### Structured verdict across hosts (three paths)

`HostCapabilities.structured_output` is `True` **only** for `ClaudeCodeRunner`.
`run_blocking_json()` must branch on host capability:

| Host | Mechanism |
|------|-----------|
| `claude-code` | inline `--json-schema` + `--no-session-persistence` (via `_structured_output_args`) |
| `codex` | `--output-schema <tmpfile>`, built by `CodexRunner.build_blocking_json`; caller **must** unlink `HostInvocation.cleanup_paths` |
| `gemini`, `omp`, `kimi-code` | prompt-and-parse, with the `_extract_tagged_structured_output` tag fallback |
| `opencode`, `pi` | stubs — `build_*` raises `HostNotConfigured`; fail soft |

### Check-order preservation (must match exactly)

`evaluate_llm_structured`'s error-handling order (`fsm/evaluators.py:1083-1268`)
is check-order-dependent and must be preserved exactly:
`subprocess.TimeoutExpired` → `FileNotFoundError` → `proc.returncode != 0`
(reports stderr) → **then** the empty-stdout-with-exit-0 guard (only reached
when `returncode == 0`) → JSON envelope parse. Collapsing or reordering these
changes which error message a caller sees for the same failure.

The JSON envelope extraction fallback priority: whole-string `json.loads`,
then last-non-blank-line JSONL fallback on `JSONDecodeError`; `subtype ==
"error_max_structured_output_retries"` and legacy `is_error` are checked
before result extraction; result extraction tries `structured_output` dict
field first, then `result` field (dict as-is, or string re-parsed via
`json.loads`, falling back to `_extract_tagged_structured_output()` only on
that inner `JSONDecodeError`, re-raising only if the tag fallback also returns
`None`), then a bare `"verdict" in envelope` fallback, else an error with a
300-char `raw_preview`.

**Decide explicitly during implementation**: `evaluate_llm_structured` does a
module-level `import subprocess` in `fsm/evaluators.py:32` and calls
`subprocess.run(...)` directly; `test_fsm_evaluators.py` patches this at ~15
call sites via `patch("little_loops.fsm.evaluators.subprocess.run")`.
`host_runner.py` currently has zero `subprocess.run`/`Popen` calls. For AC
#13's "existing tests pass without edits" to hold, either `run_blocking_json()`
must still bottom out at a patchable `evaluators.subprocess.run` call (i.e.
`evaluators.py` keeps doing the actual `subprocess.run` and
`run_blocking_json` takes the already-completed result), or the tests need
updating to patch `host_runner.subprocess.run` instead.

**Schema-conditional behavior stays in the caller.** Evidence-coercion
(`evaluate_llm_structured` lines ~1246-1248) forces `verdict = "no"`
specifically when `schema is None` (the *default* schema) and evidence is
blank — this is `evaluate_llm_structured`-specific and must not be pushed into
`run_blocking_json()`, since other future callers (the advisor) always supply
their own schema.

## API/Interface

```python
# scripts/little_loops/host_runner.py
def resolve_host_named(name: str) -> HostRunner: ...

def run_blocking_json(
    invocation: HostInvocation,
    *,
    schema: dict[str, Any] | None = None,
    timeout: int = 180,
) -> dict[str, Any] | None:
    """Execute a blocking invocation and return parsed JSON.

    Handles host-gated schema flags, the empty-stdout-with-exit-0 guard, the
    tagged-output fallback, and `invocation.cleanup_paths` unlinking.
    """
```

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py` — add `resolve_host_named`,
  `run_blocking_json`; export both in `__all__`.
- `scripts/little_loops/fsm/evaluators.py` — refactor `evaluate_llm_structured`
  onto `run_blocking_json`; `_structured_output_args` and
  `_extract_tagged_structured_output` (`evaluators.py:159`, `:111`) move or
  are imported by the helper — both are currently module-private and unused
  elsewhere, so relocating is a clean move with no other dependents.

### Dependent Files (Callers/Importers, unaffected)

- All other 8 existing `build_blocking_json` call sites (`runner_spec.py:290`,
  `parallel/worker_pool.py:805`, `cli/issues/decisions.py:797`,
  `fsm/evaluators.py:1314,1566`, `learning_tests/extractor.py:132`,
  `session_store/lifecycle.py:154`) keep working unchanged — this refactor is
  additive. Only `evaluate_llm_structured` migrates onto the shared helper.
  `evaluate_blind_comparator` (~line 1314) and a third judge call (~line 1566)
  duplicate the subprocess-and-parse loop but lack the tag-fallback safety
  net — leaving them un-migrated is an intentional scope boundary for this
  issue, not an oversight.

### Similar Patterns

- `dispatch_anthropic_request` (`host_runner.py:1879-1936`) is SDK-based (no
  subprocess) and returns `ActionResult` — not a refactor target for
  `run_blocking_json()`, just a neighboring function in the same module.

### Tests

- `scripts/tests/test_host_runner.py` — `resolve_host_named` for every
  registry key; `HostNotConfigured` for `opencode`/`pi`; `run_blocking_json`
  schema-flag branching per capability; `cleanup_paths` unlinked on the codex
  path on success, failure, and timeout. `CodexRunner`'s
  `--output-schema`/`cleanup_paths` branch already has real-tempfile test
  coverage (`test_build_blocking_json_json_schema_writes_temp_file` ~line
  348, `test_build_blocking_json_json_schema_returns_cleanup_paths` ~line
  361, `test_build_blocking_json_no_schema_cleanup_paths_empty` ~line 383,
  from ENH-1530) — extend that block, don't duplicate it.
- `scripts/tests/test_fsm_evaluators.py` — `evaluate_llm_structured` behavior
  unchanged after the refactor (regression guard); existing ~15
  `patch("little_loops.fsm.evaluators.subprocess.run")` call sites must
  either keep working unmodified or be deliberately updated per the decision
  above.

### Documentation

- `docs/reference/API.md` — `little_loops.host_runner` new exports
  (`resolve_host_named`, `run_blocking_json`).

## Acceptance Criteria

1. `resolve_host_named("codex")` resolves the codex host regardless of ambient
   `LL_HOST_CLI`, and does not mutate `os.environ` or any process-global host
   state.
2. A verdict is parsed correctly on all three structured-output paths:
   claude-code inline `--json-schema`, codex `--output-schema` temp file, and
   prompt-and-parse tag fallback (mocked host runners).
3. The codex path unlinks every `HostInvocation.cleanup_paths` entry,
   including when the subprocess fails or times out.
4. A call exceeding the passed `timeout` terminates and raises/returns a
   timeout indication rather than hanging.
5. `evaluate_llm_structured` behavior is unchanged after migrating onto
   `run_blocking_json` — existing FSM evaluator tests pass (with or without
   edits, per the explicit subprocess-patching decision made during
   implementation — either way, the same behavioral contract holds).
6. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` all pass.

## Out of Scope

- The `advisor` config block, `ll-advise` CLI, capability floor, and
  `ll-doctor` check (FEAT-3044) — this issue ships the transport only, with no
  advisor-facing caller yet.
- Backfilling `run_blocking_json()` onto `evaluate_blind_comparator` or the
  third judge call site in `evaluators.py` — noted as a pre-existing asymmetry,
  deliberately left for a future issue.

## Impact

- **Priority**: P3 — foundational plumbing for the advisor slice; no
  user-facing behavior change on its own beyond an internal refactor.
- **Effort**: Small-Medium — mostly extraction of existing logic with strict
  behavior-preservation constraints; the risk is in getting the check order
  and test-patching decision exactly right.
- **Risk**: Medium — touches every `check_semantic`/`llm_structured` FSM
  state via `evaluate_llm_structured`. Mitigated by keeping the refactor
  behavior-preserving and gated on existing evaluator tests.
- **Breaking Change**: No — purely additive + an internal refactor with an
  explicit regression-test gate.

## Related Key Documentation

- `docs/reference/API.md#little_loopshost_runner`
- `docs/reference/HOST_COMPATIBILITY.md#orchestration-cli`

## Status

**Open** | Created: 2026-08-04 | Priority: P3


## Session Log
- `/ll:issue-size-review` - 2026-08-04T20:47:20 - `b57cebec-46d2-436b-b650-9a1afa94ec18.jsonl`

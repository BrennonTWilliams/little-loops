---
id: FEAT-3042
title: Advisor transport - shared run_blocking_json helper
type: FEAT
parent: FEAT-3037
priority: P3
status: done
testable: true
decision_needed: false
discovered_date: 2026-08-04
completed_at: '2026-08-23T15:31:54Z'
labels:
- planning-hub
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
verify_verdict: VALID
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

- `resolve_host()` (`host_runner.py:1955`) resolves **one** host per process,
  from `LL_HOST_CLI` / `LL_HOOK_HOST` / a PATH probe. Every existing call site
  calls it bare — there is no per-call host selection anywhere in the
  codebase.
- Structured-output handling is inlined in `evaluate_llm_structured`
  (`fsm/evaluators.py:1109-1321`): builders drop the `json_schema` argument,
  `_structured_output_args` re-appends `--json-schema`/`--no-session-persistence`
  only for hosts advertising `HostCapabilities.structured_output`, and the
  run-subprocess-and-parse loop (timeout, empty-stdout-with-exit-0 guard, JSON
  envelope extraction with JSONL/tag fallbacks, `cleanup_paths` unlinking)
  exists only inline in that one function.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- `resolve_host()` is at `host_runner.py:1955` (re-anchored 2026-08-23; earlier passes cited :1564/:1811) — and it is not memoized: `resolve_host(env)` re-resolves a fresh runner instance on every call (the `env is None` default copies `os.environ`, `:1981`), so "resolves one host per process" overstates the caching. Per-call host selection (`resolve_host_named`) is therefore a genuinely new capability; every production call site today calls `resolve_host()` bare.

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

`HostCapabilities.structured_output` is `True` for `ClaudeCodeRunner`
(`host_runner.py:338`) **and** `QwenRunner` (`:1643`, added by
EPIC-3154/FEAT-3155 after this issue was first refined — the "only
ClaudeCodeRunner" claim from earlier passes is stale).
`run_blocking_json()` must branch on host capability:

| Host | Mechanism |
|------|-----------|
| `claude-code`, `qwen` | inline `--json-schema` + `--no-session-persistence` (via `_structured_output_args`) |
| `codex` | `--output-schema <tmpfile>`, built by `CodexRunner.build_blocking_json`; caller **must** unlink `HostInvocation.cleanup_paths` |
| `gemini`, `omp`, `kimi-code` | prompt-and-parse, with the `_extract_tagged_structured_output` tag fallback |
| `opencode`, `pi` | stubs — `build_*` raises `HostNotConfigured`; fail soft |

### Check-order preservation (must match exactly)

`evaluate_llm_structured`'s error-handling order (`fsm/evaluators.py:1109-1321`)
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

**Child-env chokepoint must be preserved (ENH-3184, landed after the last
refine pass)**: `evaluate_llm_structured`'s `subprocess.run` call now passes
`env=project_child_env(invocation)` (`fsm/evaluators.py:~1154-1160`;
`project_child_env` at `host_runner.py:1833`). Every task-path subprocess
spawn routes through this single chokepoint. Whichever side of the Option A
split ends up owning the `subprocess.run` call, the extraction must keep the
`env=project_child_env(invocation)` argument — silently dropping it would
bypass ENH-3184's env-projection contract.

**Decide explicitly during implementation**: `evaluate_llm_structured` does a
module-level `import subprocess` in `fsm/evaluators.py:32` and calls
`subprocess.run(...)` directly; `test_fsm_evaluators.py` patches this at 17
call sites via `patch("little_loops.fsm.evaluators.subprocess.run")`.
`host_runner.py` currently has zero `subprocess.run`/`Popen` calls.
`run_blocking_json()` bottoms out at a patchable `evaluators.subprocess.run`
call — `evaluators.py` keeps doing the actual `subprocess.run` and
`run_blocking_json` takes the already-completed result — so all 16 existing
patch sites keep working unmodified, satisfying AC #13's "existing tests pass
without edits."

**Schema-conditional behavior stays in the caller.** Evidence-coercion
(`evaluate_llm_structured` lines ~1288-1301, ENH-2342; `cannot_judge` exempt
per ENH-3185) forces `verdict = "no"` specifically when `schema is None` (the
*default* schema) and evidence is blank — this is
`evaluate_llm_structured`-specific and must not be pushed into
`run_blocking_json()`, since other future callers (the advisor) always supply
their own schema.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

> **Selected:** Option A — matches the codebase's only existing execution convention (host_runner.py builds `HostInvocation`, callers execute) and leaves all 16 test patch sites untouched.

**Option A**: `run_blocking_json()` bottoms out at a patchable `evaluators.subprocess.run` call — `fsm/evaluators.py` keeps the actual `subprocess.run` (module-level `import subprocess` at `fsm/evaluators.py:32`) and `run_blocking_json` receives the already-completed subprocess result. `test_fsm_evaluators.py` patches `little_loops.fsm.evaluators.subprocess.run` at 17 sites (lines 892, 970, 1309, 1440, 1536, 1701, 2209, 2287, 2396, 2412, 2445, 2456, 2483, 2516, 2593, 2616, 2642 — re-grepped 2026-08-23); `host_runner.py` has zero `subprocess.run`/`Popen` calls today.

**Option B**: `host_runner.py` owns the subprocess call and the evaluator tests are updated to patch `host_runner.subprocess.run` instead — requires `host_runner.py` to add `import subprocess` and re-target the 17 existing `patch("little_loops.fsm.evaluators.subprocess.run")` sites.

**Recommended**: Option A — smallest test churn (the 17 existing patch sites stay untouched) and keeps the refactor behavior-preserving, consistent with AC #5's "existing FSM evaluator tests pass" branch and the issue's Impact mitigation ("gated on existing evaluator tests").

### Decision Rationale

**Selected: Option A** — `evaluate_llm_structured` keeps the actual `subprocess.run` call in `fsm/evaluators.py` (module already does `import subprocess`), and `run_blocking_json` in `host_runner.py` receives the already-completed subprocess result rather than executing it internally.

Two parallel codebase-pattern-finder passes confirmed `host_runner.py` has zero `subprocess.run`/`Popen` calls anywhere today — every `build_*` method across all nine host runners only constructs and returns a `HostInvocation` value object (per the explicit contract in its docstring: "Call sites pass `binary` + `args` to `subprocess`..."). All five other `build_blocking_json` callers (`runner_spec.py:324`, `parallel/worker_pool.py:815`, `cli/issues/decisions.py:797`, `learning_tests/extractor.py:131`, `session_store/lifecycle.py:154`) execute the subprocess themselves in their own module immediately after calling the builder — with no exception found anywhere in the codebase. Option B would introduce the first subprocess execution point ever placed inside `host_runner.py`, requiring it to newly import `subprocess` and duplicate/relocate the timeout, exit-code, empty-stdout-guard, and JSON-envelope-parsing logic currently inlined in `evaluate_llm_structured` (`fsm/evaluators.py:1109-1321`) with no existing single execution point to extend from.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 3 — matches the sole existing build/execute split, no exceptions anywhere | 0 — breaks the only convention in the codebase |
| Simplicity | 3 — no new `subprocess` import or duplicated parsing logic in `host_runner.py` | 1 — requires relocating/duplicating substantial execution+parsing logic |
| Testability | 3 — all 17 existing `patch("little_loops.fsm.evaluators.subprocess.run")` sites stay untouched | 1 — all 17 sites need retargeting to `host_runner.subprocess.run` |
| Risk | 3 — behavior-preserving, contained scope | 1 — new execution point, higher regression risk against the check-order requirement |
| **Total** | **12/12** | **3/12** |

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-23.

**Selected**: Option A — `run_blocking_json()` bottoms out at a patchable `evaluators.subprocess.run` call

**Reasoning**: Codebase evidence shows the "caller owns `subprocess.run`, shared logic processes the completed result" shape is the established convention across every `build_blocking_json` consumer in the tree (`runner_spec.py:290`, `session_store/lifecycle.py:154`, `worker_pool.py:805`, `cli/issues/decisions.py:797`, `learning_tests/extractor.py:132`, and all 3 call sites in `fsm/evaluators.py` itself) — `host_runner.py` has zero `subprocess`/`Popen` calls today and has never executed a subprocess directly. Option B would make `host_runner.py` the first exception to that convention and requires mechanically re-targeting all 16 existing `test_fsm_evaluators.py` patch sites for no behavioral benefit.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |
| Option B | 0/3 | 1/3 | 1/3 | 1/3 | 3/12 |

**Key evidence**:
- Selected (Option A): extends a pattern already duplicated 3x in `fsm/evaluators.py` (`:1128`, `:1321`, `:1573`); reuses `_structured_output_args`, `_extract_tagged_structured_output`, and Codex's already-tested tempfile/`cleanup_paths` handling directly; all 16 existing `evaluators.subprocess.run` patch sites stay untouched.
- Rejected (Option B): no codebase precedent for `host_runner.py` executing a subprocess itself — every one of its 6+ `build_blocking_json` consumers keeps execution local; would require re-targeting 16+ test patch sites and make `host_runner.py` an architectural outlier.

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
  `_extract_tagged_structured_output` (`evaluators.py:166`, `:118`) move or
  are imported by the helper — both are currently module-private and unused
  elsewhere, so relocating is a clean move with no other dependents.
   > ⚠ Superseded — `_structured_output_args` has 2 other call sites, not 0

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/evaluators.py` — `_structured_output_args`
  (`evaluators.py:166`) is called at three sites, not one:
  `evaluate_llm_structured` (`:1150`, in scope), `evaluate_blind_comparator`
  (`:1369`, explicitly out of scope), and `evaluate_contract` (`:1624`,
  explicitly out of scope). If it relocates into `host_runner.py`, those two
  out-of-scope call sites need `from little_loops.host_runner import
  _structured_output_args` — a cross-module import of a `_`-prefixed name
  (unconventional but not circular: `evaluators.py` already imports from
  `host_runner.py`; the reverse import does not exist and must not be added).
  Confirm during implementation whether `_structured_output_args`/
  `_extract_tagged_structured_output` actually need to relocate at all under
  Option A (evaluators.py keeps the real `subprocess.run` call) — if
  `run_blocking_json` only receives an already-completed subprocess result,
  these two helpers may be able to stay in `evaluators.py` unmoved, which
  sidesteps the cross-module-import question entirely.

### Dependent Files (Callers/Importers, unaffected)

- All other 8 existing `build_blocking_json` call sites (`runner_spec.py:324`,
  `parallel/worker_pool.py:815`, `cli/issues/decisions.py:797`,
  `fsm/evaluators.py:1365,1621`, `learning_tests/extractor.py:131`,
  `session_store/lifecycle.py:154`) keep working unchanged — this refactor is
  additive. Only `evaluate_llm_structured` migrates onto the shared helper.
  `evaluate_blind_comparator` (`:1322`) and `evaluate_contract`'s judge call
  (`:1621`) duplicate the subprocess-and-parse loop but lack the tag-fallback
  safety net — leaving them un-migrated is an intentional scope boundary for
  this issue, not an oversight.

### Similar Patterns

- `dispatch_anthropic_request` (`host_runner.py:2270`) is SDK-based (no
  subprocess) and returns `ActionResult` — not a refactor target for
  `run_blocking_json()`, just a neighboring function in the same module.

### Tests

- `scripts/tests/test_host_runner.py` — `resolve_host_named` for every
  registry key; `HostNotConfigured` for `opencode`/`pi`; `run_blocking_json`
  schema-flag branching per capability; `cleanup_paths` unlinked on the codex
  path on success, failure, and timeout. `CodexRunner`'s
  `--output-schema`/`cleanup_paths` branch already has real-tempfile test
  coverage (`test_build_blocking_json_json_schema_writes_temp_file` line
  542, `test_build_blocking_json_json_schema_returns_cleanup_paths` line
  555, `test_build_blocking_json_no_schema_cleanup_paths_empty` line 577,
  from ENH-1530) — extend that block, don't duplicate it.
- `scripts/tests/test_fsm_evaluators.py` — `evaluate_llm_structured` behavior
  unchanged after the refactor (regression guard); existing 17
  `patch("little_loops.fsm.evaluators.subprocess.run")` call sites must
  either keep working unmodified or be deliberately updated per the decision
  above.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_evaluators.py` — `TestBlindComparator` (class at
  line 2178) and `TestContractEvaluator` (class at line 2495) cover
  `evaluate_blind_comparator` and `evaluate_contract` independently of
  `evaluate_llm_structured` — these serve as the regression backstop
  confirming `_structured_output_args` still works for the two out-of-scope
  callers if it relocates. [Agent 3 finding]

### Documentation

- `docs/reference/API.md` — `little_loops.host_runner` new exports
  (`resolve_host_named`, `run_blocking_json`).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:6013` — prose documents
  `evaluate_llm_structured`'s dispatch path as
  `host_runner.resolve_host().build_blocking_json()`; update to describe the
  `run_blocking_json` handoff. [Agent 2 finding]
- `docs/reference/API.md:9562` — line listing `host_runner.py`'s
  `__all__` verbatim; regenerate once `resolve_host_named`/`run_blocking_json`
  are added (note: it is already stale independently — missing
  `KimiRunner`/`QwenRunner`). [Agent 2 finding]
- `docs/reference/API.md:9647` — documents `build_blocking_json()`'s purpose
  ("Used by FSM structured evaluators"); update to reference the new helper
  as the actual consumer. [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- `dispatch_anthropic_request` is defined at `host_runner.py:2270` (re-anchored 2026-08-23) — still SDK-based (no subprocess) and returns `ActionResult`, so it stays outside `run_blocking_json`'s refactor scope.
- ENH-1530's Codex `--output-schema`/`cleanup_paths` tests live at `test_host_runner.py:542`, `:555`, `:577` (re-anchored 2026-08-23): `test_build_blocking_json_json_schema_writes_temp_file`, `..._returns_cleanup_paths`, `..._no_schema_cleanup_paths_empty`. Extend that block rather than duplicating.
- `test_fsm_evaluators.py` patches `little_loops.fsm.evaluators.subprocess.run` at 17 sites (lines 892, 970, 1309, 1440, 1536, 1701, 2209, 2287, 2396, 2412, 2445, 2456, 2483, 2516, 2593, 2616, 2642 — re-grepped 2026-08-23).
- `CodexRunner.build_blocking_json` also accepts a `sandbox_mode: str | None = None` keyword beyond the `HostRunner` Protocol surface (`host_runner.py:731-738`) — `run_blocking_json` need not expose it, but the build call must tolerate the widened signature.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Resolve the `_structured_output_args`/`_extract_tagged_structured_output`
  relocation question explicitly before touching `evaluators.py`: either (a)
  they stay in `evaluators.py` unmoved and `run_blocking_json` never calls
  them directly (consistent with Option A, where `evaluators.py` still owns
  the actual `subprocess.run`), or (b) they relocate to `host_runner.py` and
  `evaluate_blind_comparator`/`evaluate_contract` (evaluators.py:1369,1624)
  gain a `from little_loops.host_runner import _structured_output_args,
  _extract_tagged_structured_output` line. Do not silently drop either
  out-of-scope call site.
- Update `docs/reference/API.md` at the three anchors above (6013, 9562,
  9647) alongside the code change, not as a follow-up.
- Add `TestBlindComparator`/`TestContractEvaluator` (test_fsm_evaluators.py
  2178/2495) to the regression run explicitly called out in AC #5's
  verification, since they're the only coverage for the two out-of-scope
  callers of `_structured_output_args`.

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

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

Findings verified line-by-line against `host_runner.py`/`fsm/evaluators.py`,
organized below by category.

### Types
- `HostInvocation` — frozen dataclass at `host_runner.py:151`; carries `binary`, `args`, `env`, `capabilities`, and `cleanup_paths: tuple[Path, ...]` (default at `host_runner.py:168`). `run_blocking_json` receives one and must unlink every `cleanup_paths` entry after the run.
- `HostCapabilities` — frozen dataclass at `host_runner.py:123`; `structured_output: bool = False` at `host_runner.py:141`; True on `ClaudeCodeRunner` (`host_runner.py:338`) and `QwenRunner` (`:1643`, FEAT-3155).
- `HostRunner` — `@runtime_checkable` Protocol at `host_runner.py:222`; requires `name`, `detect()`, `build_streaming()`, `build_blocking_json()`, `build_version_check()`, `build_detached()`, `describe_capabilities()`.

### Signatures
- `def resolve_host(env: dict[str, str] | None = None) -> HostRunner` — defined at `host_runner.py:1955`; reads `LL_HOST_CLI` then `LL_HOOK_HOST` from the passed env (`:1983`), then `_PROBE_ORDER` via `shutil.which`; raises `HostNotConfigured`; never mutates process-global state (the `env is None` default copies `os.environ`, `:1981`).
- `def resolve_host_named(name: str) -> HostRunner` — new helper; body is `return resolve_host({"LL_HOST_CLI": name})`; the env dict short-circuits before any probe.
- `def run_blocking_json(invocation: HostInvocation, *, schema: dict[str, Any] | None = None, timeout: int = 180) -> dict[str, Any] | None` — new helper; extraction target, signature matches the issue's API/Interface block.
- `def evaluate_llm_structured(output: str, prompt: str | None = None, schema: dict[str, Any] | None = None, min_confidence: float = 0.5, uncertain_suffix: bool = False, model: str = DEFAULT_LLM_MODEL, max_tokens: int = 256, timeout: int = 1800) -> EvaluationResult` — `fsm/evaluators.py:1109`; migrates onto `run_blocking_json` with unchanged external behavior.
- `def build_blocking_json(*, prompt: str, model: str | None = None, json_schema: dict | None = None, sandbox_mode: str | None = None) -> HostInvocation` — `CodexRunner` method at `host_runner.py:731-738`; the only builder writing a tempfile (`--output-schema`, `:755`) and returning non-empty `cleanup_paths` (`:764`).
- `def _extract_tagged_structured_output(text: str) -> dict[str, Any] | None` — `fsm/evaluators.py:118`; module-private today, unused outside `evaluators.py`.
- `def _structured_output_args(invocation, schema: dict[str, Any]) -> list[str]` — `fsm/evaluators.py:166`; appends `--json-schema`/`--no-session-persistence` only when `getattr(invocation.capabilities, "structured_output", False)`.

### Call Path
`evaluate_llm_structured` -> `resolve_host` -> `build_blocking_json` -> `subprocess.run(..., env=project_child_env(invocation))` -> JSON envelope parse; evidence coercion stays in the caller (`evaluate_llm_structured`, `fsm/evaluators.py:~1288-1301`).

### Decision Rules
- N/A — no new runtime decision logic; the capability-gated schema branching and the envelope-fallback chain already exist in `evaluate_llm_structured` and are being extracted, not invented.

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


## Verification Notes

### 2026-08-12 (`/ll:verify-issues`)

Line citations had drifted: `resolve_host()` moved from `host_runner.py:1576` to `:1811` (env-default-copy guard now at `:1836-1837`, the `LL_HOST_CLI`/`LL_HOOK_HOST` read at `:1839`), and `evaluate_llm_structured` moved from `fsm/evaluators.py:1083-1268` to `:1094-1281`. All anchors in this file were re-grepped and updated to match. The underlying design (extract `resolve_host_named`/`run_blocking_json`, preserve `evaluate_llm_structured`'s check order, Option A subprocess-ownership decision) is unaffected by the drift and remains sound.

### 2026-08-23 (manual staleness pass)

All anchors re-grepped and updated again (`resolve_host` → `host_runner.py:1955`, `evaluate_llm_structured` → `fsm/evaluators.py:1109-1321`, helpers → `:118`/`:166`, test patch sites → 17, ENH-1530 tests → `test_host_runner.py:542/555/577`, API.md anchors → 6013/9562/9647). Two **material** updates beyond drift: (1) `QwenRunner` now also advertises `structured_output=True` (FEAT-3155) — the inline `--json-schema` path covers `claude-code` and `qwen`, not claude-code alone; (2) ENH-3184 landed `project_child_env()` and `evaluate_llm_structured`'s `subprocess.run` now passes `env=project_child_env(invocation)` — the extraction must preserve this (new requirement added under Check-order preservation). Design otherwise unchanged; leftover `verify_verdict: NON_VALID` frontmatter (stale since the 2026-08-12 anchor fix) reset to `VALID`.

## Session Log
- `/ll:verify-issues` - 2026-08-13T03:08:31 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:confidence-check` - 2026-08-10T19:50:59 - `20931a62-9bcb-46af-ab62-ab96842c221d.jsonl`
- `/ll:wire-issue` - 2026-08-10T18:45:17 - `ffa08fd4-dce7-4108-91f7-6bb57e5df4c8.jsonl`
- `/ll:decide-issue` - 2026-08-10T18:35:39 - `03ae87f5-7478-45c5-b006-43cc9c6c1023.jsonl`
- `/ll:refine-issue` - 2026-08-07T01:13:05 - `dbaeb448-e0d3-4927-896a-a00b59910595.jsonl`
- `/ll:issue-size-review` - 2026-08-04T20:47:20 - `b57cebec-46d2-436b-b650-9a1afa94ec18.jsonl`

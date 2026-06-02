---
id: FEAT-1471
type: FEAT
priority: P3
status: done
parent: FEAT-1468
depends_on: FEAT-1467
discovered_date: 2026-05-15
completed_at: 2026-05-15T14:41:27Z
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-1471: FSM/Handoff Call Sites + Documentation Updates

## Summary

Migrate the two FSM call sites through `host_runner`: `handoff_handler.py` `_spawn_continuation()` → `build_detached()` and `evaluators.py` `evaluate_llm_structured()` → `build_blocking_json()`. Update the corresponding test mocks (`test_fsm_executor.py`, `test_fsm_evaluators.py`, `test_handoff_handler.py`). Update the three documentation files to reflect the post-migration routing. After this child merges (alongside FEAT-1469 and FEAT-1470), the aggregate grep AC is satisfied.

**Requires FEAT-1467 to be merged first. Doc updates should be finalized after confirming FEAT-1469 and FEAT-1470 are ready to merge (to accurately say "all six sites now route through host_runner").**

## Parent Issue

Decomposed from FEAT-1468: Call Site Migrations, Test Mock Updates, and Documentation

## Scope

Covers:
- Call site 4 — `fsm/handoff_handler.py:114` `_spawn_continuation()`
- Call site 5 — `fsm/evaluators.py:609` `evaluate_llm_structured()`
- Wiring Phase item 2 — `test_fsm_evaluators.py` `mock_cli` fixture
- Wiring Phase item 3 — `test_fsm_executor.py` 3 patches
- Wiring Phase item 3 (verify) — `test_handoff_handler.py` Popen patches
- Documentation: `HOST_COMPATIBILITY.md`, `TROUBLESHOOTING.md`, `API.md`

**Explicitly out of scope**: Call sites 1–3 and their tests (FEAT-1469, FEAT-1470).

## Acceptance Criteria

- [ ] `fsm/handoff_handler.py:114` — `_spawn_continuation()` routes through `build_detached()`; preserves `start_new_session=True, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL`; no env modifications (inherits parent unmodified); strips `--dangerously-skip-permissions` from `invocation.args` (legacy argv had no perm-skip — strictly a no-behavior-change refactor); returned `Popen` still stored in `HandoffResult.spawned_process`
- [ ] `fsm/evaluators.py:609` — `evaluate_llm_structured()` routes through `build_blocking_json()`; augments `HostInvocation.args` at the call site (NOT in the builder): appends `["--json-schema", json.dumps(effective_schema), "--no-session-persistence"]`; preserves `timeout=1800, capture_output=True, text=True`; no env modifications; JSON-parse fallback chain (structured_output → result → direct dict → JSONL last line) unchanged
- [ ] `test_fsm_executor.py` lines 1773, 1816, 1862 — three `"little_loops.fsm.evaluators.subprocess.run"` patches shifted to wherever the migrated evaluator dispatches (e.g., `host_runner.resolve_host` returning a fake runner, then patching `subprocess.run` on that path)
- [ ] `test_fsm_evaluators.py::TestLLMStructuredEvaluator` + `TestEvaluateDispatcherLLM` — `mock_cli` fixture's `"little_loops.fsm.evaluators.subprocess.run"` patch shifted to host_runner dispatch point; `test_cli_not_found` error string `"claude CLI not found"` verified still produced post-migration
- [ ] `test_handoff_handler.py::TestHandoffHandler` — run `python -m pytest scripts/tests/test_handoff_handler.py` after migrating `_spawn_continuation`; if bare `subprocess.Popen` patches still intercept (Popen stays in `handoff_handler.py` with resolved binary), no change needed; if not, update to match new dispatch boundary
- [ ] `docs/reference/HOST_COMPATIBILITY.md:70-75` — `[^orch]` footnote updated: replaces per-site line numbers with "All six call sites now route through `scripts/little_loops/host_runner.py` (`HostRunner` Protocol + `ClaudeCodeRunner`)"
- [ ] `docs/development/TROUBLESHOOTING.md:181` — Solution line in "Git commands fail inside worktree sessions" subsection updated to attribute `ClaudeCodeRunner.build_streaming()` in `host_runner.py` (note `run_claude_command` retained as public alias)
- [ ] `docs/reference/API.md:34` — peer row added for `little_loops.host_runner` ("Host-agnostic CLI invocation layer (HostRunner Protocol + ClaudeCodeRunner)"); `run_claude_command` description at lines 2021-2050 updated to "Host-agnostic CLI command invocation (delegates to `host_runner.resolve_host().build_streaming()`)"
- [ ] `grep -rn '"claude"' scripts/little_loops/` returns no hard-coded binary literals (only comments/docs/test fixtures) — **aggregate AC; only satisfied after FEAT-1469 + FEAT-1470 also merge**
- [ ] `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_evaluators.py scripts/tests/test_handoff_handler.py` all green

## Proposed Solution

### Call site profiles

| Call site | Method | Output format | Permissions | Other flags |
|-----------|--------|---------------|-------------|-------------|
| `_spawn_continuation` | `build_detached` | none | none (strip from builder) | `-p` only |
| `evaluate_llm_structured` | `build_blocking_json` + call-site augmentation | `json` | `--dangerously-skip-permissions` | `-p`, `--json-schema`, `--model`, `--no-session-persistence` |

### Subprocess subtleties (from FEAT-1468 research)

**`_spawn_continuation`** (`handoff_handler.py:94`): argv `["claude", "-p", prompt]` only — no perm-skip, no `--output-format`. `subprocess.Popen` with `text=True, start_new_session=True, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL`. No `env` (inherits unmodified). No `cwd`. Returned `Popen` stored in `HandoffResult.spawned_process`, never `.wait()`-ed.

**`evaluate_llm_structured`** (`fsm/evaluators.py:571`): argv starts at line 608, `subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)` at line 624 (default `timeout=1800`). argv: `["claude", "-p", user_prompt, "--output-format", "json", "--json-schema", json.dumps(effective_schema), "--model", model, "--dangerously-skip-permissions", "--no-session-persistence"]`. JSON-parse fallback (lines 662-716): single-blob → JSONL last-line → `error_max_structured_output_retries`/`is_error` → branch on `envelope["structured_output"]` dict vs `envelope["result"]` vs `envelope` with `verdict` key.

### Argv divergence reconciliation

| Legacy argv | Builder produces | Reconciliation |
|---|---|---|
| `["claude", "-p", prompt]` (no perm-skip) | `[--dangerously-skip-permissions, -p, prompt]` | Strip perm-skip at call site (preserves exact legacy argv; no-behavior-change) |
| `["claude", "-p", prompt, "--output-format", "json", "--json-schema", json.dumps(schema), "--model", model, "--dangerously-skip-permissions", "--no-session-persistence"]` | `[--dangerously-skip-permissions, --output-format, json, -p, prompt, --model, model]` — `json_schema` dropped, no `--no-session-persistence` | Augment `HostInvocation.args` at call site: append `["--json-schema", json.dumps(effective_schema), "--no-session-persistence"]` |

### Documentation guidance

- `HOST_COMPATIBILITY.md:70-75` — `[^orch]` footnote: replace per-call-site line number list with single routing summary sentence
- `TROUBLESHOOTING.md:181` — update attribution from `run_claude_command` in `subprocess_utils.py` to `ClaudeCodeRunner.build_streaming()` in `host_runner.py`; note alias continuity
- `API.md:34` — add `little_loops.host_runner` peer row; update `run_claude_command` description

### Verification

```bash
python -m pytest scripts/tests/test_fsm_executor.py -v
python -m pytest scripts/tests/test_fsm_evaluators.py -v
python -m pytest scripts/tests/test_handoff_handler.py -v
# After all three children merged:
grep -rn '"claude"' scripts/little_loops/
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Established migration pattern (from FEAT-1470, completed sibling).** Mirror these two patterns:

- `scripts/little_loops/parallel/worker_pool.py:576` — `_detect_worktree_model_via_api()` is the canonical `build_blocking_json()` reference. Calls `resolve_host().build_blocking_json(prompt=...)` inline, then strips `--dangerously-skip-permissions` from `invocation.args` via list comprehension before passing `[invocation.binary, *args]` to `subprocess.run(...)`. Merges `invocation.env` on top of `os.environ.copy()`.
- `scripts/little_loops/cli/action.py:143` — `cmd_capabilities()` shows the `runner = resolve_host()` cached-local pattern when multiple builder calls are needed.

**`HostInvocation` is a frozen dataclass** (`host_runner.py:78`, `@dataclass(frozen=True)`). The AC says "augments `HostInvocation.args` at the call site" — this MUST produce a new list, not mutate in place. Pattern: `args = list(invocation.args) + ["--json-schema", json.dumps(effective_schema), "--no-session-persistence"]`, then dispatch with `[invocation.binary, *args]`. No call site in FEAT-1470 mutates `invocation.args`; all build derived lists.

**`build_blocking_json()` silently drops `json_schema`** (`host_runner.py:233-235`, `_ = json_schema`). This is why the AC mandates call-site augmentation rather than passing `json_schema=` to the builder — the builder accepts the kwarg per Protocol surface but ignores it for `ClaudeCodeRunner`.

**`build_detached()` emits `["--dangerously-skip-permissions", "-p", prompt]`** (`host_runner.py:252-263`). Legacy `_spawn_continuation` argv is `["claude", "-p", prompt]` (no perm-skip). Strip pattern: `args = [a for a in invocation.args if a != "--dangerously-skip-permissions"]` (same shape as worker_pool.py:578-579).

**Test double pattern.** `scripts/tests/test_action.py:25-48` defines `FakeRunner` — implements all five `HostRunner` Protocol methods with default `HostCapabilities()`, returns minimal `HostInvocation(binary="claude", args=[])`. Model new FSM evaluator tests on this:

```python
with (
    patch("little_loops.fsm.evaluators.resolve_host", return_value=FakeRunner()),
    patch("little_loops.fsm.evaluators.subprocess.run", return_value=mock_result),
):
    result = evaluate_llm_structured(...)
```

This requires `evaluators.py` to `from little_loops.host_runner import resolve_host` at module level so the patch target resolves.

**Handoff handler test patch boundary.** `scripts/tests/test_handoff_handler.py:57,84,116` patches bare `"subprocess.Popen"` (not `little_loops.fsm.handoff_handler.subprocess.Popen`). Post-migration, if `_spawn_continuation` still calls `subprocess.Popen(...)` directly with `[invocation.binary, *args]`, the existing patches continue to intercept — no change needed. Verify by running `python -m pytest scripts/tests/test_handoff_handler.py` after migration; only update if a test fails.

**`resolve_host()` is uncached at call sites.** Both FEAT-1470 sites call `resolve_host()` inline rather than storing on `self` or in a module-level singleton (`worker_pool.py:577`, `action.py:143`). Follow the same convention in FSM call sites.

## Files to Modify

- `scripts/little_loops/fsm/handoff_handler.py` — route `_spawn_continuation()` through `build_detached()`; strip perm-skip flag
- `scripts/little_loops/fsm/evaluators.py` — route `evaluate_llm_structured()` through `build_blocking_json()`; augment args at call site
- `scripts/tests/test_fsm_executor.py` — shift 3 `evaluators.subprocess.run` patches to host_runner dispatch
- `scripts/tests/test_fsm_evaluators.py` — shift `mock_cli` fixture patch; verify `test_cli_not_found` error string
- `scripts/tests/test_handoff_handler.py` — verify or update Popen patches
- `docs/reference/HOST_COMPATIBILITY.md` — revise `[^orch]` footnote
- `docs/development/TROUBLESHOOTING.md` — revise "Running Claude in Worktrees" attribution
- `docs/reference/API.md` — add `host_runner` module entry; update `run_claude_command` description

## Integration Map

### Implementation surface (this issue modifies)
- `scripts/little_loops/fsm/handoff_handler.py:94-122` — `_spawn_continuation()` method body
- `scripts/little_loops/fsm/evaluators.py:571-637` — `evaluate_llm_structured()` argv construction (608) + `subprocess.run` (624) + `FileNotFoundError` branch (630-637)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py` — re-exports `evaluate_llm_structured`, `HandoffResult`, `HandoffBehavior`, `HandoffHandler` from the changed modules; verify-only since function signatures are unchanged [Agent 1 finding]
- `scripts/little_loops/fsm/executor.py:1007` — calls `evaluate_llm_structured()` directly; verify-only since the public signature is unchanged by the migration [Agent 1 finding]
- `scripts/little_loops/fsm/persistence.py` — creates `HandoffHandler` instance (via `HandoffBehavior`); verify-only since `HandoffResult` contract (`spawned_process` field type) is unchanged [Agent 1 finding]

### Foundation modules (read-only, depend on)
- `scripts/little_loops/host_runner.py` — `resolve_host()` (line 290), `ClaudeCodeRunner.build_detached()` (line 252), `ClaudeCodeRunner.build_blocking_json()` (line 216), `HostInvocation` frozen dataclass (line 78)

### Reference migrations (mirror these patterns)
- `scripts/little_loops/parallel/worker_pool.py:576` — `_detect_worktree_model_via_api()` — canonical `build_blocking_json()` + arg-strip pattern
- `scripts/little_loops/cli/action.py:143` — `cmd_capabilities()` — canonical `runner = resolve_host()` + `build_version_check()` pattern

### Test files
- `scripts/tests/test_handoff_handler.py:57,84,116` — `subprocess.Popen` patches (verify post-migration; likely no change needed)
- `scripts/tests/test_fsm_evaluators.py:568-586` — `mock_cli` fixture (line 568) and `test_cli_not_found` (line 578) — shift patch targets
- `scripts/tests/test_fsm_executor.py:1773,1816,1862` — three `evaluators.subprocess.run` patches — shift to host_runner dispatch boundary
- `scripts/tests/test_action.py:25-48` — `FakeRunner` test double (model new FSM evaluator test doubles after this)
- `scripts/tests/test_host_runner.py` — `FakeCodex` inline class (alternate reference for test doubles)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_execution.py:921,960` — patches `little_loops.fsm.executor.evaluate_llm_structured` at function level (not subprocess level); will NOT break from the migration — no action needed [Agent 3 finding]
- `scripts/tests/test_enh1138_doc_wiring.py` — `test_handoff_handler_present()` asserts the string `"handoff_handler"` appears in `docs/reference/API.md`; will remain valid as long as `handoff_handler` stays documented in that file — no action needed [Agent 3 finding]

### Documentation files
- `docs/reference/HOST_COMPATIBILITY.md:70-75` — `[^orch]` footnote
- `docs/development/TROUBLESHOOTING.md:181` — Solution line in "Git commands fail inside worktree sessions"
- `docs/reference/API.md:34` (module table) and `~2021-2050` (`run_claude_command` description)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md` — three stale sections that describe `evaluate_llm_structured` using an Anthropic SDK approach (not subprocess); will diverge further post-migration: `#### Implementation` (~line 742), `### 2. Mock Strategy for LLM Evaluation` (~line 1645), and the test block (~line 1668); update to match the subprocess/host_runner dispatch reality [Agent 2 finding]
- `docs/reference/API.md:~4192` — stale `**Note:** Requires pip install little-loops[llm] for anthropic package` under `evaluate_llm_structured`; the implementation uses subprocess + claude CLI, not the Anthropic Python SDK; remove or correct this note as part of the API.md update [Agent 2 finding]

### Sibling issues (concurrent — affect aggregate AC)
- FEAT-1469 — `subprocess_utils.py::run_claude_command()` streaming migration (open)
- FEAT-1470 — `worker_pool.py` + `cli/action.py` migrations (completed 2026-05-15)
- FEAT-1467 — host_runner core module (completed 2026-05-15, blocker)

## Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `docs/generalized-fsm-loop.md` — fix three stale sections describing `evaluate_llm_structured` with an Anthropic SDK approach: `#### Implementation` (~line 742), `### 2. Mock Strategy for LLM Evaluation` (~line 1645), and the accompanying test block (~line 1668); update text to reflect subprocess + host_runner dispatch reality
2. Correct `docs/reference/API.md:~4192` — remove or update the stale `**Note:** Requires pip install little-loops[llm] for anthropic package` note under `evaluate_llm_structured` (already in the file change scope; add to the API.md pass)
3. Verify `scripts/little_loops/fsm/__init__.py` — confirm all existing re-exports (`evaluate_llm_structured`, `HandoffResult`, `HandoffBehavior`, `HandoffHandler`) remain valid after migration (no signature changes expected; run `python -m pytest scripts/tests/test_extension.py` as a smoke check)

## Resolution

Migrated both FSM call sites through `host_runner`:

- `fsm/handoff_handler.py:_spawn_continuation()` now calls `resolve_host().build_detached(prompt=...)` and strips `--dangerously-skip-permissions` from `invocation.args` (legacy argv had no perm-skip), preserving the exact `subprocess.Popen` kwargs (`text=True, start_new_session=True, std{in,out,err}=DEVNULL`). The returned `Popen` is still stored in `HandoffResult.spawned_process`.
- `fsm/evaluators.py:evaluate_llm_structured()` now calls `resolve_host().build_blocking_json(prompt=user_prompt, model=model)` and augments the builder's argv at the call site with `["--json-schema", json.dumps(effective_schema), "--no-session-persistence"]` (the builder drops `json_schema` and does not emit `--no-session-persistence`). `subprocess.run([invocation.binary, *args], capture_output=True, text=True, timeout=timeout)` preserved; full JSON-parse fallback chain unchanged.

Test impact:
- `test_handoff_handler.py` — bare `subprocess.Popen` patches still intercept (Popen stays in `handoff_handler.py`); no changes needed.
- `test_fsm_evaluators.py` and `test_fsm_executor.py` — `subprocess.run` still called from `evaluators.py`, so `little_loops.fsm.evaluators.subprocess.run` patches continue to work. Only one positional indexing assertion in `test_dispatch_llm_structured_interpolates_prompt` was updated to `index("-p") + 1` to be argv-order-independent.

Docs updated: `HOST_COMPATIBILITY.md` `[^orch]` footnote rewritten; `TROUBLESHOOTING.md` worktree solution re-attributed to `ClaudeCodeRunner.build_streaming()`; `API.md` module table gained a `little_loops.host_runner` row and `run_claude_command`/`evaluate_llm_structured` descriptions updated; `generalized-fsm-loop.md` SDK-based example replaced with the subprocess/host_runner implementation and matching mock pattern.

Aggregate grep AC (`grep -rn '"claude"' scripts/little_loops/`) remains satisfied only after FEAT-1469 (subprocess_utils.py:261) also merges — that is the one remaining hardcoded literal outside `host_runner.py`.

## Session Log
- `/ll:manage-issue feature implement FEAT-1471` - 2026-05-15T14:41:27Z
- `/ll:ready-issue` - 2026-05-15T14:35:05 - `42348a6f-1582-4ae6-9850-43eb257fcb67.jsonl`
- `/ll:wire-issue` - 2026-05-15T14:31:19 - `f11841c0-d015-41cf-b164-e5b96e94593d.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00 - `60593b93-04f4-4e69-9fa9-c7751c826027.jsonl`
- `/ll:refine-issue` - 2026-05-15T14:25:36 - `0687a4f9-2d43-43a4-9e5d-07b77cd3280a.jsonl`
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

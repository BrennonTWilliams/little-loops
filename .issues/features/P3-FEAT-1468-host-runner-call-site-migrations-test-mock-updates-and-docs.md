---
id: FEAT-1468
type: FEAT
priority: P3
status: done
parent: FEAT-1464
depends_on: FEAT-1467
discovered_date: 2026-05-15
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 70
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
size: Very Large
completed_at: 2026-05-15T00:00:00Z
---

# FEAT-1468: Call Site Migrations, Test Mock Updates, and Documentation

## Summary

Migrate all six hard-coded `"claude"` call sites through `host_runner` (introduced in FEAT-1467). Update all affected test mock targets. Update documentation that references the pre-refactor call-site line numbers or attribution. After this PR merges, the grep AC is satisfied: `grep -rn '"claude"' scripts/little_loops/` returns no hard-coded binary literals (only comments/docs/test fixtures).

**Requires FEAT-1467 to be merged first.**

## Parent Issue

Decomposed from FEAT-1464: Scaffold host_runner.py + ClaudeCodeRunner + Call Site Migrations + Config Wiring

## Scope

Covers:
- `### Call site profiles (per-site flag variance)` — all 6 production call site migrations
- Wiring Phase items 1 (test_issue_manager.py), 2 (test_generate_skill_descriptions.py), 3 (test_fsm_executor.py)
- Wiring Phase items 7 (HOST_COMPATIBILITY.md), 8 (TROUBLESHOOTING.md), 10 (API.md)

**Explicitly out of scope**: `host_runner.py` module creation, config layer, schema, `__init__.py` exports, `test_host_runner.py`, `test_extension.py`, `test_config.py`, `test_orchestrator.py`, ARCHITECTURE.md, CONTRIBUTING.md (all in FEAT-1467).

## Acceptance Criteria

- [ ] `subprocess_utils.py:219` — `run_claude_command()` routes through `HostInvocation`; kept as alias of new `run_host_command`; preserves `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` and worktree env vars; uses `subprocess.Popen` with `text=True, bufsize=1, stdout=PIPE, stderr=PIPE`; `--agent` and `--tools` come after `-p <command>` in argv
- [ ] `parallel/worker_pool.py:584` — `_detect_worktree_model_via_api()` routes through `build_blocking_json()`; preserves `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1`, `cwd=worktree_path, capture_output=True, text=True, timeout=30`. Note: `build_blocking_json` returns `env={}` and adds `--dangerously-skip-permissions` (not present in legacy argv) — migration must merge `HostInvocation.env` into `os.environ.copy()` and decide whether to strip the perm-skip flag for this call site (see Argv Divergence Reconciliation)
- [ ] `cli/action.py:142,149` — `cmd_capabilities()` uses `resolve_host().detect()` instead of `shutil.which("claude")` and `build_version_check()` for the `--version` subprocess
- [ ] `fsm/handoff_handler.py:114` — `_spawn_continuation()` (method name confirmed by codebase research; FEAT-1464 referenced this as `_spawn_new_claude_session`) routes through `build_detached()`; preserves `start_new_session=True, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL`; no env modifications; reconciles `--dangerously-skip-permissions` divergence (see Argv Divergence Reconciliation below)
- [ ] `fsm/evaluators.py:609` — LLM-graded evaluator routes through `build_blocking_json()`; preserves `--output-format json`, `--json-schema <serialized>`, `--model`, `--no-session-persistence`; `timeout=1800`; no env modifications. Note: `ClaudeCodeRunner.build_blocking_json` currently drops `json_schema` (`host_runner.py:236`) and has no `--no-session-persistence` flag — migration must either extend the builder signature or augment `HostInvocation.args` at the call site (see Argv Divergence Reconciliation below)
- [ ] `grep -rn '"claude"' scripts/little_loops/` returns no hard-coded binary literals (only comments/docs/test fixtures)
- [ ] `test_subprocess_mocks.py::TestRunClaudeCommand::test_command_includes_correct_arguments` patches `host_runner.resolve_host` instead of `subprocess`/`shutil.which`
- [ ] `test_worker_pool.py` mock target shifted from `subprocess.run` to `host_runner` dispatch point; all `CompletedProcess(args=["claude", ...])` fixtures audited
- [ ] `test_issue_manager.py::TestStreamingCallback` `_run_claude_base` patch (lines 986, 1019) shifted to `host_runner.resolve_host`
- [ ] `test_generate_skill_descriptions.py::TestProcessSkills` `little_loops.subprocess_utils.run_claude_command` patch shifted to `host_runner` dispatch point
- [ ] `test_fsm_executor.py` — 3 `little_loops.fsm.evaluators.subprocess.run` patches (lines 1773, 1816, 1862) shifted to `host_runner` dispatch path
- [ ] `docs/reference/HOST_COMPATIBILITY.md` — `[^orch]` footnote revised: specific call-site line numbers replaced with post-refactor routing summary ("all six sites now route through `host_runner`")
- [ ] `docs/development/TROUBLESHOOTING.md` — `## Git Worktree Problems` → "Git commands fail inside worktree sessions" subsection (lines 175–186); the Solution line at line 181 attributes `run_claude_command` in `subprocess_utils.py` as the `GIT_DIR`/`GIT_WORK_TREE` setter — update to attribute `ClaudeCodeRunner.build_streaming()` in `host_runner.py` (with `run_claude_command` retained as the public alias)
- [ ] `docs/reference/API.md` — `little_loops.host_runner` module entry added (line 34 peer); `run_claude_command` description updated to "Host-agnostic CLI command invocation"
- [ ] `test_action.py::TestCmdCapabilities` (4 methods) + `TestMainAction.test_capabilities_subcommand_dispatch` — `little_loops.cli.action.shutil.which` and `little_loops.cli.action.subprocess.run` patches shifted to mock `resolve_host()` (availability via `detect()`) and the resolved binary's version subprocess call
- [ ] `test_fsm_evaluators.py::TestLLMStructuredEvaluator` + `TestEvaluateDispatcherLLM` — `mock_cli` fixture's `"little_loops.fsm.evaluators.subprocess.run"` patch shifted to host_runner dispatch point; `test_cli_not_found` error string `"claude CLI not found"` verified still produced post-migration
- [ ] `test_handoff_handler.py::TestHandoffHandler` — verify bare `subprocess.Popen` patches survive: if `handoff_handler.py` still calls `Popen([invocation.binary, *invocation.args], ...)` directly, patches pass as-is; update if Popen moves inside the runner
- [ ] Full test suite green: `python -m pytest scripts/tests/`

## Proposed Solution

### Call site migration approach

Work through call sites one at a time, running `python -m pytest scripts/tests/` after each migration to catch regressions immediately. Implement `test_claude_runner_matches_legacy_args` snapshot test (from FEAT-1467) before starting migrations to lock in correct argv.

### Call site profiles (per-site flag variance)

| Call site | Method | Output format | Permissions | Other flags |
|-----------|--------|---------------|-------------|-------------|
| `run_claude_command` | `build_streaming` | `stream-json` | `--dangerously-skip-permissions` | `-p`, `--verbose`, optional `--continue`, `--agent`, `--tools` |
| `_detect_worktree_model_via_api` | `build_blocking_json` | `json` | none | `-p` only |
| `cmd_capabilities` | `build_version_check` | none | none | `--version` |
| `_spawn_new_claude_session` | `build_detached` | none | none | `-p` only |
| LLM-graded evaluator | `build_blocking_json` | `json` | `--dangerously-skip-permissions` | `-p`, `--json-schema`, `--model`, `--no-session-persistence` |

### Subprocess subtleties

From FEAT-1464 codebase research (preserve these exactly):

- **`run_claude_command`** — `subprocess.Popen` (not `subprocess.run`), `text=True, bufsize=1, stdout=PIPE, stderr=PIPE`, no explicit `stdin`, `cwd=working_dir`. Returns manually-constructed `CompletedProcess[str]` with `stdout = "\n".join(...)` and `returncode` fallback `-9`.
- **`_detect_worktree_model_via_api`** — sets `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` (same as `run_claude_command`). `subprocess.run` with `cwd=worktree_path, capture_output=True, text=True, timeout=30`. Returns `str | None` from `data["modelUsage"]` first key.
- **`cmd_capabilities`** — line 142 is `shutil.which("claude")` (pure Python, NOT a subprocess); line 149 is the subprocess for `--version`. `resolve_host().detect()` replaces the `shutil.which` call.
- **`_spawn_continuation`** (the actual method name; FEAT-1464 referred to this as `_spawn_new_claude_session`) — no env modifications (inherits parent entirely). `subprocess.Popen` with `text=True, start_new_session=True, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL`. Returned `Popen` is stored in `HandoffResult.spawned_process` but never `.wait()`-ed. Legacy argv is bare `["claude", "-p", prompt]` — no `--dangerously-skip-permissions`.
- **`evaluate_llm_structured`** — argv construction starts at line 608, `subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)` at line 624 (default `timeout=1800`). No env modifications. `--output-format json` is explicit in argv (line 612-613). `--json-schema` value is `json.dumps(effective_schema)` (serialized string, not a file path). JSON-parse fallback: tries `result["structured_output"]`, then `result["result"]`, then direct dict; JSONL fallback (last non-empty line).

### Argv Divergence Reconciliation

_Added by `/ll:refine-issue` (codebase research, 2026-05-15)._ The builders in `ClaudeCodeRunner` (FEAT-1467) were modeled on `run_claude_command` and do not exactly match the inline argv at every legacy call site. Each divergence must be reconciled explicitly before merging — silently adopting the builder argv would be a behavior change. Recommendation: when the divergence is a missing flag (json-schema, no-session-persistence) or a flag the builder adds unconditionally (perm-skip on worktree probe), augment `HostInvocation.args` post-build at the call site rather than threading new kwargs through the builder. Leave the builder API stable so other hosts can implement against a small surface; treat the call-site adjustments as host-specific Claude Code argv quirks.

| Call site → builder | Legacy argv has | Builder produces | Reconciliation |
|---|---|---|---|
| `run_claude_command` → `build_streaming` | `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` + optional `GIT_DIR`/`GIT_WORK_TREE` in `os.environ.copy()` | `HostInvocation.env` returns partial dict only (those keys) | Caller merges `HostInvocation.env` into `os.environ.copy()` before `Popen`. Pop responsibility for `bufsize=1, text=True, stdout=PIPE, stderr=PIPE, cwd=working_dir` stays at the call site. |
| `_detect_worktree_model_via_api` → `build_blocking_json` | argv: `[-p, prompt, --output-format, json]` (no perm-skip) + env `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` | argv: `[--dangerously-skip-permissions, --output-format, json, -p, prompt]` + env `{}` | Strip `--dangerously-skip-permissions` from `invocation.args` (or accept it — model probe is read-only, so adding it is plausibly safe; document the decision in the PR). Caller still merges env. |
| `cmd_capabilities` → `build_version_check` + `resolve_host().detect()` | line 142 = `shutil.which("claude")`, line 149 = `subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=10)` | `detect()` returns bool; `build_version_check` returns `["--version"]` | Use `resolve_host().detect()` for availability; if true, fetch resolved binary (via runner's reported binary or a new accessor) and run `[binary, *invocation.args]`. No divergence in argv. |
| `_spawn_continuation` → `build_detached` | argv: `["claude", "-p", prompt]` (no perm-skip) | argv: `[--dangerously-skip-permissions, -p, prompt]` | Either strip the flag at call site to preserve exact legacy argv, or accept the behavior change (handoff continuations historically work without it). Recommend stripping to keep this PR strictly a no-behavior-change refactor. |
| `evaluate_llm_structured` → `build_blocking_json` | argv: `[-p, prompt, --output-format, json, --json-schema, json.dumps(schema), --model, model, --dangerously-skip-permissions, --no-session-persistence]` + `timeout=1800` | argv: `[--dangerously-skip-permissions, --output-format, json, -p, prompt, --model, model]` — `json_schema` silently dropped (host_runner.py:236), no `--no-session-persistence` | Augment `HostInvocation.args` at the call site: append `["--json-schema", json.dumps(effective_schema), "--no-session-persistence"]`. Do NOT modify `build_blocking_json` to accept `--no-session-persistence` (CapabilityNotSupported is the right primitive for other hosts that lack it). |

### Dependent callers to verify (alias continuity)

After migrating `run_claude_command`, verify these still work via the alias:
- `scripts/little_loops/fsm/runners.py:20` — imports `run_claude_command`
- `scripts/little_loops/issue_manager.py:38,45` — imports `run_claude_command`
- `scripts/little_loops/cli/generate_skill_descriptions.py:91` — imports `run_claude_command` dynamically

### Wiring Phase (added by `/ll:wire-issue`)

_Three test files identified by wiring analysis are missing from the migration:_

1. Migrate `test_action.py::TestCmdCapabilities` mock targets — `patch("little_loops.cli.action.shutil.which", ...)` (5 occurrences) shifts to `patch("little_loops.cli.action.resolve_host", ...)` returning a fake runner whose `detect()` returns the mocked bool; `patch("little_loops.cli.action.subprocess.run", ...)` stays valid only if `cmd_capabilities` still calls `subprocess.run` directly with the resolved binary (confirm during migration). Same update for `TestMainAction.test_capabilities_subcommand_dispatch` at line 416.
2. Migrate `test_fsm_evaluators.py` `mock_cli` fixture — used by all tests in `TestLLMStructuredEvaluator` and `TestEvaluateDispatcherLLM`; shifts from `patch("little_loops.fsm.evaluators.subprocess.run")` to wherever the migrated evaluator dispatches (same migration required as the three patches in `test_fsm_executor.py` lines 1773, 1816, 1862). Verify `test_cli_not_found` error string `"claude CLI not found"` is still produced.
3. Verify `test_handoff_handler.py::TestHandoffHandler` — run `python -m pytest scripts/tests/test_handoff_handler.py` after migrating `_spawn_continuation`; if bare `subprocess.Popen` patches still intercept (Popen stays in `handoff_handler.py`), no change needed; if not, update to match new dispatch boundary.

## Files to Modify

- `scripts/little_loops/subprocess_utils.py` — route `run_claude_command()` through `HostInvocation`; preserve alias
- `scripts/little_loops/parallel/worker_pool.py` — route `_detect_worktree_model_via_api()` through `host_runner`
- `scripts/little_loops/cli/action.py` — `cmd_capabilities()`: `shutil.which("claude")` → `resolve_host().detect()` + version via resolved binary
- `scripts/little_loops/fsm/handoff_handler.py` — route `_spawn_continuation()` (lines 94–122; argv at line 114) through `build_detached()`
- `scripts/little_loops/fsm/evaluators.py` — route LLM-graded evaluator through `build_blocking_json()`
- `scripts/tests/test_subprocess_mocks.py` — update mock target to `host_runner.resolve_host`
- `scripts/tests/test_worker_pool.py` — update mock targets; audit `CompletedProcess(args=["claude", ...])` fixtures
- `scripts/tests/test_issue_manager.py` — shift `_run_claude_base` patch (lines 986, 1019) to `host_runner.resolve_host`
- `scripts/tests/test_generate_skill_descriptions.py` — shift `run_claude_command` patch to `host_runner` dispatch
- `scripts/tests/test_fsm_executor.py` — shift 3 `evaluators.subprocess.run` patches (lines 1773, 1816, 1862) to `host_runner` dispatch
- `docs/reference/HOST_COMPATIBILITY.md` — revise `[^orch]` footnote
- `docs/development/TROUBLESHOOTING.md` — revise "Running Claude in Worktrees" section attribution
- `docs/reference/API.md` — add `host_runner` module entry; update `run_claude_command` description
- `scripts/tests/test_action.py` — update `TestCmdCapabilities` mock targets: shift `shutil.which` + `subprocess.run` patches at the `action` module level to `resolve_host` mock [Wiring pass]
- `scripts/tests/test_fsm_evaluators.py` — update `TestLLMStructuredEvaluator` + `TestEvaluateDispatcherLLM` `mock_cli` fixture: shift `little_loops.fsm.evaluators.subprocess.run` patch to host_runner dispatch [Wiring pass]
- `scripts/tests/test_handoff_handler.py` — verify or update `TestHandoffHandler` bare `subprocess.Popen` patches after `_spawn_continuation` routes through `build_detached()` [Wiring pass]

## Codebase Research Findings

_Added by `/ll:refine-issue` (2026-05-15). Verifies the post-FEAT-1467 codebase state for the call sites this issue migrates._

### Call-site anchors (verified line numbers)

| Site | File:anchor | Subprocess pattern | Notes |
|------|-------------|-------------------|-------|
| 1 | `subprocess_utils.py:219` def, `:260-273` argv, `:292` Popen | `subprocess.Popen` | argv begins `["claude", "--dangerously-skip-permissions", "--verbose", "--output-format", "stream-json"]`; conditional `--continue`, then `-p`, then optional `--agent`, `--tools`. Env: `os.environ.copy()` + `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1`; if `working_dir/.git` is a file, reads `gitdir:` ref and sets `GIT_DIR`/`GIT_WORK_TREE`. Returns hand-built `CompletedProcess(cmd_args, returncode or -9, "\n".join(stdout_lines), "\n".join(stderr_lines))` at line 422 — alias must preserve this exact return shape. |
| 2 | `worker_pool.py:562` def, `:582-595` `subprocess.run`, `:584` argv start | `subprocess.run` | argv: `["claude", "-p", "reply with just 'ok'", "--output-format", "json"]` — no perm-skip. kwargs: `cwd=worktree_path, capture_output=True, text=True, timeout=30, env=env`. Env: `os.environ.copy()` + `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` (no `GIT_DIR`/`GIT_WORK_TREE` even though running in a worktree). Parses `data["modelUsage"]` first key. Swallows `TimeoutExpired`/`FileNotFoundError`/`JSONDecodeError` → `None`. |
| 3 | `cli/action.py:139` def `cmd_capabilities`, `:142` `shutil.which`, `:148-153` subprocess | `subprocess.run` | Line 142 `shutil.which("claude")` is NOT a subprocess — it's a PATH probe; `resolve_host().detect()` replaces it. Line 148-153 runs `["claude", "--version"]` with `capture_output=True, text=True, timeout=10`. On `TimeoutExpired`/`FileNotFoundError`/`OSError` → `available=False`. |
| 4 | `handoff_handler.py:94` def `_spawn_continuation`, `:114` argv, `:115-122` Popen | `subprocess.Popen` | argv: `["claude", "-p", prompt]` only — no perm-skip, no `--output-format`. kwargs: `text=True, start_new_session=True, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL`. No `env` (inherits unmodified). No `cwd`. Returned `Popen` stored in `HandoffResult.spawned_process`, never `.wait()`-ed. |
| 5 | `fsm/evaluators.py:571` def `evaluate_llm_structured`, `:608-620` argv, `:624` `subprocess.run` | `subprocess.run` | argv: `["claude", "-p", user_prompt, "--output-format", "json", "--json-schema", json.dumps(effective_schema), "--model", model, "--dangerously-skip-permissions", "--no-session-persistence"]`. `effective_schema` defaults to `DEFAULT_LLM_SCHEMA`; `model` to `DEFAULT_LLM_MODEL`. kwargs: `capture_output=True, text=True, timeout=timeout` (default 1800). JSON-parse fallback (lines 662-716): single-blob → JSONL last-line → `error_max_structured_output_retries`/`is_error` short-circuit → branch on `envelope["structured_output"]` dict vs `envelope["result"]` (dict/str/JSON-decode) vs `envelope` itself with `verdict` key. |

### Test mock-target conventions (post-FEAT-1467)

- **Argv capture (preserve)**: `test_subprocess_mocks.py::TestRunClaudeCommand::test_command_includes_correct_arguments` (lines 63–103) patches **bare `"subprocess.Popen"`** with a `side_effect` that captures `args[0]`. After migration this patch target is still correct (`subprocess_utils.py` still calls `subprocess.Popen` directly). The AC "patches `host_runner.resolve_host`" applies to tests that exercise host *selection*, not to tests that snapshot argv at the Popen boundary — keep the Popen patch for the argv snapshot.
- **Host-runner injection**: `test_host_runner.py` establishes two patterns:
  1. `monkeypatch.setattr("little_loops.host_runner.shutil.which", fake_which)` for probe-order tests
  2. Direct `_HOST_RUNNER_REGISTRY` mutation with `try/finally` restore for injecting fake `HostRunner`s
- **Module-qualified patch strings (preserve where appropriate)**:
  - `test_issue_manager.py:986,1019` patches `"little_loops.issue_manager._run_claude_base"` — module-qualified at the *use* site. After migration this can shift to patch `host_runner.resolve_host` returning a fake runner, OR retain the `_run_claude_base` patch (whichever stays simpler).
  - `test_generate_skill_descriptions.py::TestProcessSkills` (multiple methods at lines 139, 156, 173, 186, 203, 231, 249) patches `"little_loops.subprocess_utils.run_claude_command"` — module-qualified at the *definition* site. After migration, the same patch target still works as long as `run_claude_command` remains an alias re-exported from `subprocess_utils` (which is required by AC line 35).
  - `test_fsm_executor.py:1772-1774, 1816, 1862` patches `"little_loops.fsm.evaluators.subprocess.run"`. Post-migration, the call site no longer uses `subprocess.run` directly — patch must shift to whatever entry point the migrated evaluator uses (e.g., `host_runner.resolve_host` returning a fake runner whose `build_blocking_json` produces predictable argv, then patching `subprocess.run` on that path; OR patching a new helper that wraps `subprocess.run` for blocking-JSON invocations).
- **`CompletedProcess(args=["claude", ...])` fixtures in `test_worker_pool.py`** (lines ~2267-2314) are NOT subprocess mocks — they're return values passed to `patch.object(worker_pool, "_run_claude_command", return_value=handoff_result)`. These remain valid post-migration as long as `_run_claude_command` still returns a `CompletedProcess` whose `args` is the full argv (which it should, since the migrated `run_claude_command` builds `cmd_args = [invocation.binary, *invocation.args]`). Audit means: confirm the simulated argv shape still matches what callers inspect, not necessarily change the fixtures.

### Docs anchors (verified)

- `docs/reference/HOST_COMPATIBILITY.md:70-75` — `[^orch]` footnote currently lists all six call sites with line numbers. Replace with post-refactor routing summary: e.g., "All six call sites now route through `scripts/little_loops/host_runner.py` (`HostRunner` Protocol + `ClaudeCodeRunner`)."
- `docs/development/TROUBLESHOOTING.md:175-186` — `## Git Worktree Problems` → "Git commands fail inside worktree sessions" subsection. The Solution line at ~181 names `run_claude_command` in `subprocess_utils.py`. Update to attribute `ClaudeCodeRunner.build_streaming()` in `host_runner.py` (note `run_claude_command` is retained as the public alias).
- `docs/reference/API.md:34` — module overview table currently has `| little_loops.subprocess_utils | Subprocess handling |`. Add a peer row for `little_loops.host_runner` ("Host-agnostic CLI invocation layer (HostRunner Protocol + ClaudeCodeRunner)"). The `run_claude_command` entry at lines 2021–2050 needs description updated to "Host-agnostic CLI command invocation (delegates to `host_runner.resolve_host().build_streaming()`)."

### CompletedProcess return-shape contract

`subprocess_utils.py:422-427` constructs:
```python
return subprocess.CompletedProcess(
    cmd_args,
    process.returncode if process.returncode is not None else -9,
    stdout="\n".join(stdout_lines),
    stderr="\n".join(stderr_lines),
)
```
Callers (`worker_pool._run_claude_command`, `issue_manager.run_claude_command` wrapper, `cli/generate_skill_descriptions.py:91`) access `.returncode`, `.stdout`, `.stderr` directly. The migrated implementation must preserve all four fields and the `-9` fallback exactly.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-15_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Outcome Risk Factors
- Wide file surface (16 change sites — 0/12 Breadth score) is the dominant driver of the Moderate confidence rating. Per-site depth is genuinely low (local function body substitutions), but coordinating 5 production modules + 8 test mock updates + 3 doc edits in a single PR raises integration risk. Mitigation: work through call sites in table order and run `python -m pytest scripts/tests/` after each site.
- `test_subprocess_utils.py` is not in the Integration Map (intentionally — Popen stays in `subprocess_utils.py` post-migration), but its 20+ tests exercise `run_claude_command` through the full Popen path. Run `python -m pytest scripts/tests/test_subprocess_utils.py` explicitly after migrating site 1 to confirm the untouched test file still passes.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-15
- **Reason**: Issue too large for single session (score 11/11, 16 change sites across 5 production modules + 8 test files + 3 doc files)

### Decomposed Into
- FEAT-1469: Streaming call site migration — `run_claude_command` + alias tests
- FEAT-1470: Detection & blocking call sites — `worker_pool.py` + `cli/action.py` + tests
- FEAT-1471: FSM/handoff call sites + documentation updates

**Note**: The aggregate grep AC (`grep -rn '"claude"' scripts/little_loops/` returns no hard-coded binary literals) is only satisfied after all three children merge.

## Session Log
- `/ll:confidence-check` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ad225cd-959b-4311-ba00-306f545ffa94.jsonl`
- `/ll:wire-issue` - 2026-05-15T13:40:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/22ed95d3-9f16-4fce-967a-36500c0ab8a2.jsonl`
- `/ll:refine-issue` - 2026-05-15T13:33:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5dc5ec06-7910-40b9-98d5-2ffad9f17471.jsonl`
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6024d56a-9aff-4760-9ebc-3ce5b51bb09f.jsonl`
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

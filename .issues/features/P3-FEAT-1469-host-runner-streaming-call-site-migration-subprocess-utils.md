---
id: FEAT-1469
type: FEAT
priority: P3
status: done
parent: FEAT-1468
depends_on: FEAT-1467
discovered_date: 2026-05-15
discovered_by: issue-size-review
completed_at: 2026-05-15T18:36:36Z
confidence_score: 100
outcome_confidence: 74
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 10
size: Very Large
---

# FEAT-1469: Streaming Call Site Migration — `run_claude_command` + Alias Tests

## Summary

Migrate the `run_claude_command()` streaming call site in `subprocess_utils.py` through `host_runner` (`HostInvocation` / `ClaudeCodeRunner.build_streaming()`). Update the three test files that mock `run_claude_command` or its subprocess internals at the alias boundary. After this child merges, `"claude"` is removed from `subprocess_utils.py` and all alias callers continue working unchanged.

**Requires FEAT-1467 to be merged first.**

## Current Behavior

`run_claude_command()` in `scripts/little_loops/subprocess_utils.py` hardcodes the `"claude"` binary directly in its `subprocess.Popen` invocation, bypassing the `host_runner` abstraction layer introduced in FEAT-1467. Any host override via `LL_HOST_CLI` or `orchestration.host_cli` is silently ignored for this call site.

## Expected Behavior

`run_claude_command()` routes through `resolve_host().build_streaming(...)`, producing a `HostInvocation` whose `binary` and `args` are passed to `subprocess.Popen`. All alias callers (`fsm/runners.py`, `issue_manager.py`, `cli/generate_skill_descriptions.py`) continue to work without changes.

## Use Case

A developer running `ll-auto` or `ll-parallel` on an OpenCode or PiCode host sets `LL_HOST_CLI=opencode` in their environment. `run_claude_command()` must invoke the configured host binary — not a hardcoded `"claude"` — so that all streaming call sites respect the host abstraction uniformly.

## Parent Issue

Decomposed from FEAT-1468: Call Site Migrations, Test Mock Updates, and Documentation

## Scope

Covers:
- Call site 1 — `subprocess_utils.py:219` `run_claude_command()`
- Dependent callers to verify (alias continuity): `fsm/runners.py:20` (import) + `fsm/runners.py:102` (call), `issue_manager.py:45-47` (`from little_loops.subprocess_utils import run_claude_command as _run_claude_base`), `cli/generate_skill_descriptions.py:91` (import) + `cli/generate_skill_descriptions.py:116` (call)
- Test mock updates: `test_subprocess_mocks.py`, `test_issue_manager.py`, `test_generate_skill_descriptions.py`

**Explicitly out of scope**: Call sites 2–5 (`worker_pool.py`, `action.py`, `handoff_handler.py`, `evaluators.py`) and their tests — those are in FEAT-1470 and FEAT-1471. Documentation updates — in FEAT-1471.

## Acceptance Criteria

- [ ] `subprocess_utils.py:219` — `run_claude_command()` builds a `HostInvocation` via `ClaudeCodeRunner.build_streaming()` and calls `subprocess.Popen([invocation.binary, *invocation.args], ...)` with the resolved binary; preserves `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` and optional `GIT_DIR`/`GIT_WORK_TREE` in the env by merging `HostInvocation.env` into `os.environ.copy()`; preserves `text=True, bufsize=1, stdout=PIPE, stderr=PIPE, cwd=working_dir`; `--agent` and `--tools` still come after `-p <command>` in argv; returns hand-built `CompletedProcess(cmd_args, returncode or -9, "\n".join(stdout_lines), "\n".join(stderr_lines))` unchanged
- [ ] Alias callers unaffected: `fsm/runners.py:20` + `:102`, `issue_manager.py:45-47` (import-as-alias `_run_claude_base`), `cli/generate_skill_descriptions.py:91` + `:116` continue to import and call `run_claude_command` with no changes
- [ ] `test_subprocess_mocks.py::TestRunClaudeCommand::test_command_includes_correct_arguments` — the bare `"subprocess.Popen"` patch is KEPT (not shifted to `host_runner.resolve_host`); argv snapshot at the Popen boundary stays valid post-migration. Note: the AC in FEAT-1468 ("patches `host_runner.resolve_host`") was superseded by codebase research finding that `subprocess_utils.py` continues calling `subprocess.Popen` directly.
- [ ] `test_issue_manager.py` lines 986, 1019 — `_run_claude_base` patch (`"little_loops.issue_manager._run_claude_base"`) continues to work as-is OR is shifted to `host_runner.resolve_host`; whichever is simpler given the migration boundary
- [ ] `test_generate_skill_descriptions.py` — `TestProcessSkills` patches (lines 139, 156, 173, 186, 203) and `TestMainGenerateSkillDescriptions` patches (lines 231, 249) all use `"little_loops.subprocess_utils.run_claude_command"` and continue to work as-is (alias re-export from `subprocess_utils` preserved)
- [ ] `python -m pytest scripts/tests/test_subprocess_utils.py scripts/tests/test_subprocess_mocks.py scripts/tests/test_issue_manager.py scripts/tests/test_generate_skill_descriptions.py` all green

## Proposed Solution

### Call site profile

| Call site | Method | Output format | Permissions | Other flags |
|-----------|--------|---------------|-------------|-------------|
| `run_claude_command` | `build_streaming` | `stream-json` | `--dangerously-skip-permissions` | `-p`, `--verbose`, optional `--continue`, `--agent`, `--tools` |

### Subprocess subtleties (from FEAT-1468 research)

`subprocess_utils.py:219` — `subprocess.Popen` (not `subprocess.run`), `text=True, bufsize=1, stdout=PIPE, stderr=PIPE`, no explicit `stdin`, `cwd=working_dir`. Returns manually-constructed `CompletedProcess[str]` with `stdout = "\n".join(...)` and `returncode` fallback `-9`. Callers access `.returncode`, `.stdout`, `.stderr` directly — preserve all four fields and the `-9` fallback exactly.

Env construction: `os.environ.copy()` + `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1`; if `working_dir/.git` is a file, reads `gitdir:` ref and sets `GIT_DIR`/`GIT_WORK_TREE`. After migration: merge `HostInvocation.env` into `os.environ.copy()` before `Popen` (the runner returns partial dict; caller merges).

### Resolution strategy

_Added by `/ll:refine-issue` — based on codebase analysis:_

Use `resolve_host()`, not direct `ClaudeCodeRunner()` instantiation, so the call site is host-agnostic and `LL_HOST_CLI` / `LL_HOOK_HOST` overrides take effect:

```python
from little_loops.host_runner import resolve_host

runner = resolve_host()
invocation = runner.build_streaming(
    prompt=command,
    working_dir=Path(working_dir) if working_dir else None,
    resume=resume_session,
    agent=agent,
    tools=tools,
)
```

This matches the convention established by sibling migrations in FEAT-1468 (e.g. `cli/action.py:cmd_capabilities` uses `resolve_host().detect()`). Top-level `from little_loops.host_runner import resolve_host` is safe in `subprocess_utils.py` — `host_runner.py` only imports stdlib + `Path`, so there is no circular import risk.

### `cmd_args` local variable — all three uses must update

`subprocess_utils.py` uses one local `cmd_args` list in three places:

| Line | Current use | Post-migration |
|---|---|---|
| `292-300` | `subprocess.Popen(cmd_args, ...)` | `subprocess.Popen([invocation.binary, *invocation.args], ...)` |
| `330` | `raise subprocess.TimeoutExpired(cmd_args, timeout)` | use the same `[invocation.binary, *invocation.args]` list |
| `341` | `raise subprocess.TimeoutExpired(cmd_args, idle_timeout, output="idle_timeout")` | use the same `[invocation.binary, *invocation.args]` list |
| `422-427` | `subprocess.CompletedProcess(cmd_args, returncode, stdout=..., stderr=...)` | use the same `[invocation.binary, *invocation.args]` list |

Recommended: bind once at the top of the function — `cmd_args = [invocation.binary, *invocation.args]` — and reuse, so the three `TimeoutExpired`/`CompletedProcess` constructors stay consistent with the Popen call.

### Env merge order — `HostInvocation.env` must win on conflict

The current code seeds `env = os.environ.copy()` then writes `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` and worktree `GIT_DIR`/`GIT_WORK_TREE` directly onto that dict, so the runner's values always take effect. Post-migration the merge must preserve that semantic:

```python
env = {**os.environ.copy(), **invocation.env}
```

(NOT `os.environ.copy() | invocation.env` only — that works in 3.9+; either is fine. The key constraint is that `invocation.env` wins on conflict.) `HostInvocation.env` for `build_streaming` returns `{"CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "1", "GIT_DIR": ..., "GIT_WORK_TREE": ...}` — these must override any inherited values.

### Argv divergence reconciliation

| Legacy argv | Builder produces | Reconciliation |
|---|---|---|
| `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` + optional `GIT_DIR`/`GIT_WORK_TREE` | `HostInvocation.env` returns partial dict only | Caller merges `HostInvocation.env` into `os.environ.copy()` before Popen |
| `bufsize=1, text=True, stdout=PIPE, stderr=PIPE, cwd=working_dir` | builder does not set Popen kwargs | Stay at call site |

### Verification

After migrating `subprocess_utils.py`, run:
```bash
python -m pytest scripts/tests/test_subprocess_utils.py -v
python -m pytest scripts/tests/test_subprocess_mocks.py -v
python -m pytest scripts/tests/test_issue_manager.py -v
python -m pytest scripts/tests/test_generate_skill_descriptions.py -v
```

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Add `from little_loops.host_runner import resolve_host` import to `subprocess_utils.py`
2. Migrate `run_claude_command()` body: call `resolve_host().build_streaming(...)`, bind `cmd_args = [invocation.binary, *invocation.args]`, merge env as `{**os.environ.copy(), **invocation.env}`
3. Add new tests in `test_subprocess_utils.py`:
   - `patch("little_loops.subprocess_utils.resolve_host", ...)` — verify `resolve_host()` is called and its `HostInvocation` is used
   - Assert `HostInvocation.env` keys override matching `os.environ` keys (env merge order)
   - Optionally: test that `HostNotConfigured` raised by `resolve_host()` propagates out of `run_claude_command()`
4. Run full test suite: `python -m pytest scripts/tests/test_subprocess_utils.py scripts/tests/test_subprocess_mocks.py scripts/tests/test_issue_manager.py scripts/tests/test_generate_skill_descriptions.py`
5. Patch `little_loops.subprocess_utils.resolve_host` in the **existing** test classes — after migration, `run_claude_command()` calls `resolve_host()` first, which internally calls `subprocess.run(["claude", "--version"])` for host detection; `subprocess.run()` uses `subprocess.Popen` internally, so the existing `patch("subprocess.Popen", side_effect=capture_popen)` WILL intercept the detect call, injecting an extra `captured_args` entry that shifts index-based argv assertions (e.g., `captured_args[0]` becomes the detect call, not the command call). Fix: add `patch("little_loops.subprocess_utils.resolve_host", return_value=FakeRunner())` as a module-level autouse fixture in `test_subprocess_utils.py` (preferred) or as a per-test context manager in each `TestRunClaudeCommand*` test; same addition needed in `test_subprocess_mocks.py::TestRunClaudeCommand`. Use the `FakeRunner` pattern from `test_action.py:25-47` — its `build_streaming` returns `HostInvocation(binary="claude", args=[])` which preserves argv snapshot compatibility.

## Files to Modify

- `scripts/little_loops/subprocess_utils.py` — add `from little_loops.host_runner import resolve_host` at module top; route `run_claude_command()` through `HostInvocation`; preserve `run_claude_command` symbol so existing `from little_loops.subprocess_utils import run_claude_command` imports keep working
- `scripts/tests/test_subprocess_mocks.py` — keep bare `subprocess.Popen` patch; verify argv snapshot at lines 95-103 still produces `["claude", "--dangerously-skip-permissions", "--verbose", "--output-format", "stream-json", "-p", "/ll:ready-issue BUG-001"]`
- `scripts/tests/test_issue_manager.py` — `_run_claude_base` patch at lines 986, 1019 continues to work as-is because `_run_claude_base = subprocess_utils.run_claude_command` (the alias at `issue_manager.py:45-47`) is preserved; no patch shift needed
- `scripts/tests/test_generate_skill_descriptions.py` — 7 patches of `little_loops.subprocess_utils.run_claude_command` (lines 139, 156, 173, 186, 203, 231, 249) continue to work as-is — the symbol is unchanged at the module path
- `scripts/tests/test_subprocess_utils.py` — existing coverage across 8 test classes remains valid post-migration (bare `subprocess.Popen` patch is module-global); **add new tests** for: (a) `resolve_host()` delegation via `patch("little_loops.subprocess_utils.resolve_host", ...)`, (b) `HostInvocation.env` entries override `os.environ` keys on conflict, (c) optionally `HostNotConfigured` propagation through `run_claude_command()`

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/subprocess_utils.py:219` — `run_claude_command()`: build via `resolve_host().build_streaming(...)`, merge `invocation.env` over `os.environ.copy()`, use `[invocation.binary, *invocation.args]` in all four call points (Popen, two `TimeoutExpired`, `CompletedProcess`)
- `scripts/tests/test_subprocess_utils.py` — add `resolve_host()` delegation test and env merge-order test; this file appears in the AC pytest command but was omitted from Files to Modify [wiring pass]

### Dependent Files (Callers/Importers — verify alias continuity, no edits expected)
- `scripts/little_loops/issue_manager.py:45-47` — `from little_loops.subprocess_utils import run_claude_command as _run_claude_base`; downstream call sites at `issue_manager.py:97` (enriched wrapper), `:151` (calls `_run_claude_base`), `:236, :337, :511, :567, :727` (calls the enriched `run_claude_command`)
- `scripts/little_loops/fsm/runners.py:20, :102` — direct import and call
- `scripts/little_loops/cli/generate_skill_descriptions.py:91, :116` — direct import and call

### Similar Patterns
- `scripts/little_loops/host_runner.py:179-218` — `ClaudeCodeRunner.build_streaming` is the canonical argv-mirror of pre-refactor `subprocess_utils.run_claude_command` (lines 260-273). Locked in by `tests/test_host_runner.py::test_claude_runner_matches_legacy_args` (FEAT-1467)
- Sibling migration pattern (FEAT-1468, `cli/action.py:cmd_capabilities`): `resolve_host()` → `runner.build_version_check()` → spawn subprocess

_Second-pass refinement (2026-05-15) — additional patterns discovered:_

- **Canonical env-merge sibling**: `scripts/little_loops/parallel/worker_pool.py:576-594` (`_detect_active_model`) is the only existing production call site that merges `invocation.env`. The established pattern is two-statement:
  ```python
  env = os.environ.copy()
  env.update(invocation.env)
  ```
  not the dict-unpack form `{**os.environ.copy(), **invocation.env}` prescribed in the Proposed Solution above. Both produce identical results when `invocation.env` keys win on conflict; **prefer `.update()` for consistency with the existing sibling**. The Proposed Solution's "either is fine" caveat is correct — this is a style alignment, not a correctness issue.
- **`HostNotConfigured` propagation convention**: Audited all four existing `resolve_host()` call sites (`worker_pool.py`, `fsm/evaluators.py`, `fsm/handoff_handler.py`, `cli/action.py`). **None** catch `HostNotConfigured` — the established convention is to let it propagate to the caller. The optional AC ("test that `HostNotConfigured` raised by `resolve_host()` propagates out of `run_claude_command()`") aligns with this convention; the test should assert propagation, not handling.
- **Reusable test double**: `scripts/tests/test_action.py:25-47` defines a `FakeRunner` class (modeled on `FakeCodex` from `test_host_runner.py`) with `build_streaming`/`build_blocking_json`/`build_version_check`/`build_detached` stubs. The new tests in `test_subprocess_utils.py` should reuse this pattern — either import `FakeRunner` from `test_action.py` or define a local equivalent. Patch target: `"little_loops.subprocess_utils.resolve_host"` (after the import is added).

_Third-pass refinement (2026-05-15) — additional findings:_

- **Closest structural Popen template**: `scripts/little_loops/fsm/handoff_handler.py:116-126` is the closest existing sibling for the migration shape — `Popen([invocation.binary, *args], ...)` after `resolve_host().build_detached(...)`. The Resolution strategy currently cites `cli/action.py:cmd_capabilities`, but that path uses `subprocess.run` for `build_version_check`, not `Popen`. `handoff_handler.py` strips `--dangerously-skip-permissions` from `args` before unpacking (an arg-filtering technique) — `run_claude_command` does NOT need that filter; it keeps the flag. Use `handoff_handler.py` as the Popen-shape template, `action.py:cmd_capabilities` as the `resolve_host()` discovery template.

- **Silent debug-log loss** (behavioral delta): `subprocess_utils.py:290` currently emits `logger.debug("Worktree detected: GIT_DIR=%s", env["GIT_DIR"])` when a `.git` file is found. `ClaudeCodeRunner.build_streaming()` (`host_runner.py:204-211`) sets the same env keys but does NOT log. Post-migration this debug line silently disappears because worktree detection moves into the runner. Mitigation if observability matters: after the env merge, check `"GIT_DIR" in invocation.env` and re-emit the same debug log at the call site. **Recommendation**: re-emit to preserve diagnostic continuity — costs one line, eliminates a silent behavioral change.

- **Combined-flag argv coverage gap** (test-pattern-finder finding): `test_host_runner.py:116-152` covers `--continue`, `--agent`, and `--tools` for `ClaudeCodeRunner.build_streaming` in **separate** tests; no existing test exercises a combined `resume=True + agent="x" + tools=[...]` argv. FEAT-1469's argv equivalence relies on `test_claude_runner_matches_legacy_args` (no-flags only). If the implementer wants tighter parity coverage they can add one combined-flag golden test, but this is **optional** — the issue's AC does not require it and the three individual tests + the no-flags golden test are sufficient to prove argv stability under any single-flag permutation.

_Fourth-pass refinement (2026-05-15) — verified pattern absences (test-pattern-finder + codebase-analyzer):_

- **No existing env merge-order test exists.** The only `invocation.env` assertion in the suite is `test_host_runner.py:412` (`assert invocation.env == {}`, a default-value check). No test verifies that `invocation.env` values override `os.environ` on key collision — so the new env merge-order test in `test_subprocess_utils.py` (Implementation Steps step 3) is genuinely novel coverage, not duplication.
- **No conflict risk on the `resolve_host` patch target.** No test in the suite currently patches `little_loops.subprocess_utils.resolve_host`; the only existing patches against `subprocess_utils` are `run_claude_command` (in `test_action.py:175, :265, :282` — out of scope for FEAT-1469) and `subprocess_utils.logger` (in `test_subprocess_utils.py:1286, :1314`). The new autouse fixture patching `little_loops.subprocess_utils.resolve_host` is safe to add.
- **`HostNotConfigured` propagation through callers is untested.** The only `HostNotConfigured` tests are inside `test_host_runner.py:95-388` (validating `resolve_host()` itself) and `test_feat1462_doc_wiring.py:45-94` (doc-wiring check). No test asserts that a caller of `run_claude_command()` or any subprocess utility lets `HostNotConfigured` propagate — the optional AC test would be the first such coverage.
- **Function-body inspection clean.** The second `try/except subprocess.TimeoutExpired` block at `subprocess_utils.py:403-417` (the 30-second drain wait after streams close) does NOT use `cmd_args` and does NOT raise `TimeoutExpired` — so the migration correctly focuses only on the three `cmd_args` usages already documented (Popen + two `TimeoutExpired` raises + `CompletedProcess`).

### Tests
- `scripts/tests/test_subprocess_mocks.py:22-103` — `TestRunClaudeCommand::test_command_includes_correct_arguments` is the argv snapshot at the Popen boundary. Imports `little_loops.issue_manager.run_claude_command` (the wrapper) at line 85, which transitively calls `subprocess_utils.run_claude_command`. The patch at line 77 (`patch("subprocess.Popen", side_effect=capture_popen)`) is module-global so it intercepts regardless of which alias produced the call
- `scripts/tests/test_issue_manager.py:986, :1019` — `TestRunClaudeCommand::test_streams_output_when_enabled` / `test_skips_streaming_when_disabled` — patches `little_loops.issue_manager._run_claude_base` (the imported alias)
- `scripts/tests/test_generate_skill_descriptions.py:139, :156, :173, :186, :203` — `TestProcessSkills` patches at `little_loops.subprocess_utils.run_claude_command`; `:231, :249` — `TestMainGenerateSkillDescriptions` patches at the same path (module-attr symbol path)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_subprocess_utils.py` — **existing coverage** across 8 test classes (`TestRunClaudeCommand`, `TestRunClaudeCommandOutputCapture`, `TestRunClaudeCommandStreaming`, `TestRunClaudeCommandTimeout`, `TestRunClaudeCommandProcessCallbacks`, `TestRunClaudeCommandSelectorCleanup`, `TestRunClaudeCommandIntegration`, `TestRunClaudeCommandIdleTimeout`): argv snapshots, env-var merging, timeout/kill, streaming, idle-timeout, process callbacks; all stable post-migration since `subprocess.Popen` is still called directly. `TestRunClaudeCommandIntegration::test_command_in_result` (line 965) asserts `result.args` against the full argv list — stays valid because `ClaudeCodeRunner.build_streaming` argv is locked by `test_host_runner.py::test_claude_runner_matches_legacy_args`. **Gap**: no test currently patches `little_loops.subprocess_utils.resolve_host` to verify delegation, and no test verifies `HostInvocation.env` merge-order priority
- `scripts/tests/test_fsm_executor.py` — 4 patches of `"little_loops.fsm.runners.run_claude_command"` (lines 3403, 3420, 4569, 4602) in `TestDefaultActionRunner`; patches the name as bound in the `fsm.runners` module namespace — stable through migration; **no changes needed**
- `scripts/tests/test_action.py` — 13 patches of `"little_loops.subprocess_utils.run_claude_command"` (lines 126, 148, 163, 176, 187, 198, 212, 238, 255, 266, 409, 458, 469) in `TestCmdInvoke`; symbol path is preserved; out-of-scope (FEAT-1470); **no changes needed**

_Wiring pass (2nd) added by `/ll:wire-issue`:_
- `scripts/tests/test_worker_pool.py` — `TestWorkerPoolRunClaudeCommand::test_run_claude_command_tracks_process` (line 2175) patches `"little_loops.parallel.worker_pool._run_claude_base"`; this is `worker_pool.py`'s own import alias, not `subprocess_utils` directly; FEAT-1469 does not touch `worker_pool.py` (deferred to FEAT-1470); **no changes needed**

_Wiring pass (3rd) added by `/ll:wire-issue`:_
- `scripts/tests/test_host_runner.py` — `TestClaudeCodeRunner::test_claude_runner_matches_legacy_args` (line 116): the argv equivalence contract test between the legacy hardcoded argv list and `ClaudeCodeRunner.build_streaming()`; **do not modify** — this is the cross-reference proof that delegation produces identical argv; must stay green after FEAT-1469 [Agent 3 finding]
- **Existing test stability gap** — the 8 `TestRunClaudeCommand*` classes in `test_subprocess_utils.py` and `TestRunClaudeCommand` in `test_subprocess_mocks.py` all call `run_claude_command()` directly with a `patch("subprocess.Popen", side_effect=capture_popen)`. After migration, `resolve_host()` is called inside `run_claude_command()` and triggers `subprocess.run(["claude", "--version"])` for host detection; `subprocess.run()` internally calls `subprocess.Popen`, which IS intercepted by the capture side_effect — injecting an extra `captured_args` entry that shifts index-based argv snapshot assertions. Add `patch("little_loops.subprocess_utils.resolve_host", return_value=FakeRunner())` as a module-level autouse fixture (or per-test context) to short-circuit `detect()` entirely. The AC's "bare Popen patch is KEPT" remains true — the Popen patch stays; the `resolve_host` patch is an addition, not a replacement [Agent 3 finding]

### Documentation
- Deferred to FEAT-1471 per scope split; this child does NOT touch `docs/`

### Configuration
- None — no new config keys; `orchestration.host_cli` (added in FEAT-1467) governs resolution via `resolve_host()`

## Impact

- **Priority**: P3 — Completes host-runner abstraction for the most frequently called streaming entry point; blocked by FEAT-1467 (done)
- **Effort**: Large — Single function migration but requires coordinated test updates across 4 test files and a new autouse `resolve_host` fixture pattern
- **Risk**: Low — Alias callers are unmodified; `subprocess.Popen` is still called directly at the same site; argv shape locked by `test_claude_runner_matches_legacy_args`
- **Breaking Change**: No — `run_claude_command` symbol preserved at existing import path

## Labels

`host-runner`, `migration`, `subprocess`, `testing`, `call-site`

## Status

**Open** | Created: 2026-05-15 | Priority: P3

## Confidence Check Notes

_Last updated by `/ll:confidence-check` on 2026-05-15 (re-run; scores unchanged)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- **Wide change surface across 6-10 dependent files** — issue_manager.py, fsm/runners.py, generate_skill_descriptions.py + 4 test files all require verification runs even though none are expected to need edits; a regression in the preserved function contract would surface as test failures rather than a compile error, so the full pytest suite in the AC is load-bearing
- **New delegation tests not yet written** — the two new tests in test_subprocess_utils.py (resolve_host patch + env merge-order priority) are required by AC but must be authored during implementation; they're the only coverage that verifies the migration correctness at the abstraction boundary rather than the Popen boundary

## Session Log
- `/ll:ready-issue` - 2026-05-15T18:28:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a7266ec-c5b5-4c2f-9e4f-98b8b1efda13.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/631f963e-730d-4448-9a7b-24ec9120e739.jsonl`
- `/ll:wire-issue` - 2026-05-15T18:21:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6471c46-d789-49cb-9936-de27174a97ea.jsonl`
- `/ll:refine-issue` - 2026-05-15T18:11:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5c69cf60-78ec-4a83-8028-3eaf2ef8da8d.jsonl`
- `/ll:confidence-check` - 2026-05-15T18:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82d0a12c-f330-4f71-af02-2884a8a07caf.jsonl`
- `/ll:wire-issue` - 2026-05-15T18:02:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eb7a1539-5968-4349-b66e-7412f36b200f.jsonl`
- `/ll:refine-issue` - 2026-05-15T17:54:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f2f575f6-1d58-472f-a602-97e2d7519327.jsonl`
- `/ll:wire-issue` - 2026-05-15T17:20:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/db3329e1-8acc-403a-b640-5d9e35fae4f5.jsonl`
- `/ll:refine-issue` - 2026-05-15T17:16:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc5bf9df-9dcb-4cbd-9f50-94231bf44e37.jsonl`
- `/ll:wire-issue` - 2026-05-15T13:56:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/978001d2-a715-45c7-b4c6-b5b80a6d8699.jsonl`
- `/ll:refine-issue` - 2026-05-15T13:51:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bdf2e3ae-16d6-4e72-9afd-6caa398f2bf0.jsonl`
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4e969bf3-ae63-4f97-be5f-6be542d3997d.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/982aae20-b43e-46c0-8930-9d3848a09bdc.jsonl`

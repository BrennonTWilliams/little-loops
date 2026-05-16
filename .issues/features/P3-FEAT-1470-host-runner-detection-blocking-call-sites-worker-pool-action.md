---
id: FEAT-1470
type: FEAT
priority: P3
status: done
parent: FEAT-1468
depends_on: FEAT-1467
discovered_date: 2026-05-15
completed_at: 2026-05-15T14:18:48Z
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1470: Detection & Blocking Call Sites — `worker_pool.py` + `cli/action.py` + Tests

## Summary

Migrate two call sites through `host_runner`: the model-detection probe in `parallel/worker_pool.py` (`_detect_worktree_model_via_api()` → `build_blocking_json()`) and the capabilities check in `cli/action.py` (`cmd_capabilities()` → `resolve_host().detect()` + `build_version_check()`). Update the corresponding test mocks in `test_worker_pool.py` and `test_action.py`.

**Requires FEAT-1467 to be merged first.**

## Parent Issue

Decomposed from FEAT-1468: Call Site Migrations, Test Mock Updates, and Documentation

## Scope

Covers:
- Call site 2 — `parallel/worker_pool.py:562` `_detect_worktree_model_via_api()` (subprocess.run at lines 582-595)
- Call site 3 — `cli/action.py:139` `cmd_capabilities()` (shutil.which at line 142; subprocess.run at lines 148-153)
- Wiring Phase item 1 — `test_action.py::TestCmdCapabilities` mock target shift
- Test mock updates: `test_worker_pool.py::TestWorkerPoolModelDetection` (lines 1660-1744), `test_action.py::TestCmdCapabilities` + `TestMainAction.test_capabilities_subcommand_dispatch`

**Explicitly out of scope**: Call sites 1, 4, 5 and their tests (FEAT-1469, FEAT-1471). Documentation updates (FEAT-1471).

## Acceptance Criteria

- [x] `parallel/worker_pool.py:562` — `_detect_worktree_model_via_api()` routes through `resolve_host().build_blocking_json(prompt="reply with just 'ok'")`; preserves `cwd=worktree_path, capture_output=True, text=True, timeout=30`; constructs env as `os.environ.copy()` + `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` + merged `invocation.env` (empty for `ClaudeCodeRunner`, but keeps cross-host parity); strips `--dangerously-skip-permissions` from `invocation.args` (legacy argv had none); decision documented in PR comment (strip chosen to preserve no-behavior-change intent)
- [x] `cli/action.py:142` — `shutil.which("claude")` replaced with `resolve_host().detect()` returning bool availability
- [x] `cli/action.py:148` — version subprocess uses resolved binary: `subprocess.run([invocation.binary, *invocation.args], capture_output=True, text=True, timeout=10)` where `invocation = resolve_host().build_version_check()`; preserves `TimeoutExpired`/`FileNotFoundError`/`OSError` → `available=False` fallback (note: `detect()` does not catch `OSError`, so the version-call try/except must remain)
- [x] `test_worker_pool.py::TestWorkerPoolModelDetection` (lines 1660-1744, 5 methods) — existing `patch("subprocess.run")` patches remain valid since the migrated function still terminates in `subprocess.run`; verify `CompletedProcess([], 0, json_response, "")` fixtures still match (they do — callers only inspect `.returncode` and `.stdout`); confirm no `_detect_worktree_model_via_api` test inspects argv shape (current tests don't, so argv divergence is invisible). The `CompletedProcess(args=["claude", ...])` references at lines 2269-2314 are in `TestRunWithContinuation` — unrelated to detection; verify they remain untouched.
- [x] `test_action.py::TestCmdCapabilities` (4 methods at lines 281-368) + `TestMainAction.test_capabilities_subcommand_dispatch` (lines 416-430) — replace 5 occurrences of `patch("little_loops.cli.action.shutil.which", ...)` with `patch("little_loops.cli.action.resolve_host", return_value=FakeRunner(detect_returns=...))`; keep `patch("little_loops.cli.action.subprocess.run", ...)` (still valid since `cmd_capabilities` calls `subprocess.run` directly with the resolved binary). FakeRunner can be a module-level test helper modeled on `FakeCodex` in `test_host_runner.py:test_explicit_override_beats_hook_host`.
- [x] `python -m pytest scripts/tests/test_worker_pool.py scripts/tests/test_action.py` all green

## Resolution

Implemented per the refined plan. `worker_pool.py:_detect_worktree_model_via_api` now uses `resolve_host().build_blocking_json(...)`, stripping `--dangerously-skip-permissions` to preserve the detection-probe semantics, and merging `invocation.env` after the `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` set so explicit overrides take priority. `cli/action.cmd_capabilities` uses `resolve_host().detect()` for availability and `runner.build_version_check()` for the version subprocess; the `OSError`/`TimeoutExpired`/`FileNotFoundError` fallback is retained. `shutil` import was removed from `cli/action.py`. Added a module-level `FakeRunner` test helper in `test_action.py` (modeled on `FakeCodex`) and shifted all 5 `shutil.which` patches to `resolve_host` patches. `test_worker_pool.py` required no edits — the bare `patch("subprocess.run")` boundary still terminates the migrated function. Verification: 142 tests pass across `test_action.py`, `test_worker_pool.py`, `test_host_runner.py`; `ruff check` and `mypy` clean.

## Proposed Solution

### Call site profiles

| Call site | Method | Output format | Permissions | Other flags |
|-----------|--------|---------------|-------------|-------------|
| `_detect_worktree_model_via_api` | `build_blocking_json` | `json` | none | `-p` only |
| `cmd_capabilities` | `build_version_check` + `resolve_host().detect()` | none | none | `--version` |

### Subprocess subtleties (from FEAT-1468 research)

**`_detect_worktree_model_via_api`** (`worker_pool.py:562`): argv `["claude", "-p", "reply with just 'ok'", "--output-format", "json"]` — no perm-skip. `subprocess.run` with `cwd=worktree_path, capture_output=True, text=True, timeout=30, env=env`. Env: `os.environ.copy()` + `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1`. Parses `data["modelUsage"]` first key. Swallows `TimeoutExpired`/`FileNotFoundError`/`JSONDecodeError` → `None`.

**`cmd_capabilities`** (`action.py:139`): Line 142 `shutil.which("claude")` is NOT a subprocess — pure PATH probe; `resolve_host().detect()` replaces it. Lines 148-153: `subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=10)`. On `TimeoutExpired`/`FileNotFoundError`/`OSError` → `available=False`.

### Argv divergence reconciliation

| Legacy argv | Builder produces | Reconciliation |
|---|---|---|
| `["claude", "-p", prompt, "--output-format", "json"]` (no perm-skip) | `[--dangerously-skip-permissions, --output-format, json, -p, prompt]` | Strip `--dangerously-skip-permissions` from `invocation.args` at call site; document in PR comment |
| `shutil.which("claude")` (PATH probe) | `detect()` returns bool | Use `resolve_host().detect()` for availability; fetch resolved binary for version subprocess |

### Verification

After migrating both call sites:
```bash
python -m pytest scripts/tests/test_worker_pool.py -v
python -m pytest scripts/tests/test_action.py -v
```

## Files to Modify

- `scripts/little_loops/parallel/worker_pool.py` — route `_detect_worktree_model_via_api()` through `build_blocking_json()`; strip perm-skip flag
- `scripts/little_loops/cli/action.py` — `shutil.which("claude")` → `resolve_host().detect()`; version subprocess uses resolved binary
- `scripts/tests/test_worker_pool.py` — update mock targets; audit `CompletedProcess(args=["claude", ...])` fixtures
- `scripts/tests/test_action.py` — shift `shutil.which` patches to `resolve_host` mock; verify `subprocess.run` patches

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify (with anchors)
- `scripts/little_loops/parallel/worker_pool.py` — `WorkerPool._detect_worktree_model_via_api()` at line 562; subprocess.run call at lines 582-595
- `scripts/little_loops/cli/action.py` — `cmd_capabilities()` at line 139; `shutil.which("claude")` at line 142; `subprocess.run(["claude", "--version"], ...)` at lines 148-153
- `scripts/tests/test_worker_pool.py` — `TestWorkerPoolModelDetection` class at lines 1660-1744 (5 test methods, all use bare `patch("subprocess.run")`)
- `scripts/tests/test_action.py` — `TestCmdCapabilities` class at lines 281-368 (4 methods, patches at lines 293, 312, 335, 350); `TestMainAction.test_capabilities_subcommand_dispatch` at lines 416-430 (patch at line 424)

### Module Imports to Add
- `cli/action.py` — add `from little_loops.host_runner import resolve_host` (currently only imports `shutil` and `subprocess`)
- `parallel/worker_pool.py` — add `from little_loops.host_runner import resolve_host` (verify; current import may be needed at module top or function-scoped)

### Production Callers
- `_detect_worktree_model_via_api` has exactly one production caller: `WorkerPool._setup_worktree` (line 536), gated by `self.parallel_config.show_model`
- `cmd_capabilities` is dispatched from `main_action()` via the `capabilities` subcommand

### Reference Patterns (for implementation)
- **FakeRunner for tests** — model on `FakeCodex` in `scripts/tests/test_host_runner.py::TestResolveHost.test_explicit_override_beats_hook_host`. Required methods: `detect() -> bool`, `build_blocking_json(**_) -> HostInvocation`, `build_version_check() -> HostInvocation`, plus `name`, `capabilities` attributes (registry-style usage not required here; tests use `patch("...resolve_host", return_value=fake_runner_instance)`)
- **Argv strip pattern** — `[a for a in invocation.args if a != "--dangerously-skip-permissions"]` keeps the no-perm-skip semantics intact for the detection probe
- **Env merge pattern** — `env = os.environ.copy(); env["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"] = "1"; env.update(invocation.env)` (order matters: explicit override after merge to keep call-site invariants; `invocation.env` is `{}` for `ClaudeCodeRunner` so this is a no-op today but keeps cross-host parity)
- **Existing argv snapshot test** — `test_host_runner.py::TestClaudeCodeRunner::test_claude_runner_matches_legacy_args` provides the canonical baseline for `build_streaming` argv. No similar lock exists for `build_blocking_json` argv; one is not required by this issue since the strip pattern intentionally diverges.

### Test Mock Patch Paths (post-migration)
| Test target | Patch path |
|---|---|
| `_detect_worktree_model_via_api` subprocess | bare `"subprocess.run"` (unchanged — keeps existing 5 patches working) |
| `cmd_capabilities` host probe | `"little_loops.cli.action.resolve_host"` (NEW — replaces `shutil.which` patches) |
| `cmd_capabilities` version subprocess | `"little_loops.cli.action.subprocess.run"` (unchanged) |

### Behavioral Asymmetry Notes
- `ClaudeCodeRunner.detect()` returns `shutil.which("claude") is not None` — identical semantics to the current `cmd_capabilities` line 142 probe.
- `cmd_capabilities`'s `OSError`-on-version-call → `available=False` branch must remain, because `detect()` only checks PATH; it does not run the version subprocess. The version-call try/except continues to guard against `TimeoutExpired`, `FileNotFoundError`, and `OSError`.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/HOST_COMPATIBILITY.md` — `[^orch]` footnote lists `cli/action.py:142,149` and `parallel/worker_pool.py:584` as raw call sites by line number; these become stale after migration. Update deferred to FEAT-1471 per decomposition plan.

## Implementation Steps

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **worker_pool.py migration** — In `_detect_worktree_model_via_api` (line 562): replace literal argv with `invocation = resolve_host().build_blocking_json(prompt="reply with just 'ok'")`; build env via `os.environ.copy()` + `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` + `invocation.env.items()`; strip `--dangerously-skip-permissions` from `invocation.args`; pass `[invocation.binary, *stripped_args]` to `subprocess.run`. Keep all existing kwargs (`cwd`, `capture_output`, `text`, `timeout=30`) and the exception tuple.
2. **action.py migration (line 142)** — Replace `claude_path = shutil.which("claude")` and `available = claude_path is not None` with `runner = resolve_host(); available = runner.detect()`. Keep `runner` in scope for step 3.
3. **action.py migration (lines 148-153)** — Inside `if available:` block, replace literal `["claude", "--version"]` with `invocation = runner.build_version_check(); subprocess.run([invocation.binary, *invocation.args], capture_output=True, text=True, timeout=10)`. Keep the existing `except (TimeoutExpired, FileNotFoundError, OSError): available = False` handler.
4. **test_worker_pool.py audit** — Confirm `TestWorkerPoolModelDetection` (5 tests at lines 1659-1742) still pass without changes; the bare `patch("subprocess.run")` boundary is preserved by the migration. The `TestRunWithContinuation` fixtures at lines 2267-2314 exercise a different code path and should not be touched.
5. **test_action.py test helper** — Add a module-level `FakeRunner` class modeled on `FakeCodex` (test_host_runner.py:test_explicit_override_beats_hook_host) with `detect`, `build_version_check`, and stub `build_streaming`/`build_blocking_json`/`build_detached` to satisfy the Protocol. Accept `detect_returns: bool` in `__init__` for parameterization.
6. **test_action.py patch shift** — In the 5 spots currently patching `"little_loops.cli.action.shutil.which"`: replace each with `patch("little_loops.cli.action.resolve_host", return_value=FakeRunner(detect_returns=...))`. The companion `subprocess.run` patches (mock_version, TimeoutExpired side_effect) remain unchanged.
7. **Verification**:
   ```bash
   python -m pytest scripts/tests/test_worker_pool.py::TestWorkerPoolModelDetection -v
   python -m pytest scripts/tests/test_action.py::TestCmdCapabilities scripts/tests/test_action.py::TestMainAction -v
   python -m pytest scripts/tests/test_worker_pool.py scripts/tests/test_action.py
   ```

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Remove `import shutil` from `cli/action.py` — `shutil` has no remaining uses after `shutil.which("claude")` is replaced in Step 2; `ruff check` (CI) will flag it as an unused import if left in.

## Session Log
- `/ll:manage-issue` - 2026-05-15T14:18:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/280f9133-381f-4455-93b8-227118f1c415.jsonl`
- `/ll:ready-issue` - 2026-05-15T14:15:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2e0f7b6b-b579-42ce-903d-740d3dee3298.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ca04b8f0-231f-48d8-aced-f992137c9225.jsonl`
- `/ll:wire-issue` - 2026-05-15T14:11:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8bdc9bf1-f1d5-4040-81f0-8b364a120d6f.jsonl`
- `/ll:refine-issue` - 2026-05-15T14:06:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/43dbf466-d4c4-4415-9506-a054212d031b.jsonl`
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

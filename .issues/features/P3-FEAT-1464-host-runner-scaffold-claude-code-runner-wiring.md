---
id: FEAT-1464
type: FEAT
priority: P3
status: done
parent: FEAT-1462
discovered_date: 2026-05-15
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 66
score_complexity: 13
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
size: Very Large
---

# FEAT-1464: Scaffold host_runner.py + ClaudeCodeRunner + Call Site Migrations + Config Wiring

## Summary

Introduce `scripts/little_loops/host_runner.py` with the `HostRunner` Protocol, `HostInvocation` dataclass, `ClaudeCodeRunner` implementation, and capability-warning surface (`CapabilityNotSupported`, `HostNotConfigured`). Migrate all six hard-coded `"claude"` call sites through the new module. Wire `OrchestrationConfig` into the config layer. Update test mock targets accordingly. This is the safe-refactor PR: behavior-identical for Claude Code users, full test suite stays green, and the grep AC is satisfied before any new host code lands.

## Parent Issue

Decomposed from FEAT-1462: Abstract Host CLI Invocation in Orchestration Layer

## Scope

Covers Implementation Steps 2, 4, 9, 10, 11, 12, 13, 14 from the parent issue.

**Explicitly out of scope**: Codex research, CodexRunner, OpenCodeRunner, PiRunner, HOST_COMPATIBILITY.md orchestration row, and the full doc-wiring test file (those land in FEAT-1465 and FEAT-1466).

## Acceptance Criteria

- [ ] New module `scripts/little_loops/host_runner.py` exposes `resolve_host()`, `HostInvocation`, `HostRunner` protocol, `HostNotConfigured`, and `CapabilityNotSupported`
- [ ] Host detection resolves in documented order: `LL_HOST_CLI` env → `LL_HOOK_HOST` env → binary probe (`claude` → `codex` → `pi`) → `HostNotConfigured` with remediation hint
- [ ] `ClaudeCodeRunner` produces argv byte-identical to pre-refactor calls (verified by snapshot test `test_host_runner.py::test_claude_runner_matches_legacy_args`)
- [ ] `CapabilityNotSupported` subclasses `UserWarning` so callers can upgrade to abort via `warnings.filterwarnings("error", ...)`
- [ ] All six call sites route through `host_runner`:
  - `subprocess_utils.py:219` — `run_claude_command()` (keep as alias of new `run_host_command`)
  - `parallel/worker_pool.py:584` — `_detect_worktree_model_via_api()`
  - `cli/action.py:142,149` — `cmd_capabilities()` (preflight + version check)
  - `fsm/handoff_handler.py:114` — `_spawn_new_claude_session()`
  - `fsm/evaluators.py:609` — LLM-graded evaluator
- [ ] `grep -rn '"claude"' scripts/little_loops/` returns no hard-coded binary literals (only comments/docs/test fixtures)
- [ ] `OrchestrationConfig` dataclass added to `config/core.py` with parse in `BRConfig._parse_config()` (line 185) and serialization in `BRConfig.to_dict()` (line 464)
- [ ] `OrchestrationConfig` re-exported from `config/__init__.py` following existing `__all__` pattern
- [ ] `HostRunner`, `HostInvocation`, `HostNotConfigured`, `CapabilityNotSupported` added to `scripts/little_loops/__init__.py` `__all__` (consistent with all other Protocols in the package)
- [ ] `config-schema.json` includes `orchestration.host_cli` enum `["auto", "claude-code", "codex", "opencode", "pi"]` with default `"auto"`; host-name spellings match existing `hooks.host` enum at line 1103
- [ ] `test_subprocess_mocks.py::TestRunClaudeCommand::test_command_includes_correct_arguments` updated to patch `host_runner.resolve_host` instead of `subprocess`/`shutil.which`
- [ ] `test_worker_pool.py` mock target shifted from `subprocess.run` to `host_runner` dispatch point; all `CompletedProcess(args=["claude", ...])` fixtures audited
- [ ] `test_config_schema.py::test_orchestration_in_schema()` added following `test_hooks_in_schema()` pattern
- [ ] Full test suite green: `python -m pytest scripts/tests/`

## Proposed Solution

### host_runner.py design

```python
@dataclass(frozen=True)
class HostInvocation:
    binary: str
    args: list[str]
    env: dict[str, str]
    capabilities: HostCapabilities  # streaming, permission_skip, agent_select, tool_allowlist

class HostRunner(Protocol):
    name: str
    def detect(self) -> bool: ...
    def build_streaming(self, *, prompt: str, working_dir: Path,
                        resume: bool, agent: str | None,
                        tools: list[str] | None) -> HostInvocation: ...
    def build_blocking_json(self, *, prompt: str, model: str | None,
                             json_schema: dict | None) -> HostInvocation: ...
    def build_version_check(self) -> HostInvocation: ...
    def build_detached(self, *, prompt: str) -> HostInvocation: ...

def resolve_host() -> HostRunner:
    """Resolution order: LL_HOST_CLI → LL_HOOK_HOST → binary probe → HostNotConfigured"""
```

Split `build_invocation()` into purpose-specific factory methods (streaming, blocking_json, version_check, detached) to handle per-call-site flag variance documented in the parent issue's Integration Map table.

### Patterns to follow

- **Protocol pattern**: Model on `extension.py` `@runtime_checkable` Protocols (`LLExtension`, `LLHookIntentExtension`)
- **Lazy dispatch registry**: Model `_HOST_RUNNER_REGISTRY` on `hooks/__init__.py:44-70` `_HOOK_INTENT_REGISTRY` + `_dispatch_table()` pattern
- **Warning vs. exception**: `CapabilityNotSupported(UserWarning)` following `config/core.py` `warnings.warn()` pattern for opt-in capture

### Call site profiles (per-site flag variance)

| Call site | Method | Output format | Permissions | Other flags |
|-----------|--------|---------------|-------------|-------------|
| `run_claude_command` | `build_streaming` | `stream-json` | `--dangerously-skip-permissions` | `-p`, `--verbose`, optional `--continue`, `--agent`, `--tools` |
| `_detect_worktree_model_via_api` | `build_blocking_json` | `json` | none | `-p` only |
| `cmd_capabilities` | `build_version_check` | none | none | `--version` |
| `_spawn_new_claude_session` | `build_detached` | none | none | `-p` only |
| LLM-graded evaluator | `build_blocking_json` | `json` | `--dangerously-skip-permissions` | `-p`, `--json-schema`, `--model`, `--no-session-persistence` |

### Config wiring

Add `OrchestrationConfig` to `config/core.py` following the same closure-of-extension-point convention documented in `_config_candidates()` docstring (line 82).

## Files to Modify

- `scripts/little_loops/host_runner.py` — NEW: Protocol + ClaudeCodeRunner + registry + capability surface
- `scripts/little_loops/subprocess_utils.py` — route `run_claude_command()` through `HostInvocation`; preserve `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` and worktree env vars
- `scripts/little_loops/parallel/worker_pool.py` — route `_detect_worktree_model_via_api()` through `host_runner`
- `scripts/little_loops/cli/action.py` — `cmd_capabilities()`: `shutil.which("claude")` → `resolve_host().detect()` + version via resolved binary
- `scripts/little_loops/fsm/handoff_handler.py` — route `_spawn_new_claude_session()` through `build_detached()`; preserve `start_new_session=True, stdin/stdout/stderr=DEVNULL`
- `scripts/little_loops/fsm/evaluators.py` — route LLM-graded evaluator through `build_blocking_json()`
- `scripts/little_loops/config/core.py` — add `OrchestrationConfig`, parse in `_parse_config()`, serialize in `to_dict()`
- `scripts/little_loops/config/__init__.py` — re-export `OrchestrationConfig`
- `scripts/little_loops/__init__.py` — add host_runner types to `__all__`
- `config-schema.json` — add `orchestration.host_cli` enum
- `scripts/tests/test_host_runner.py` — NEW: detection precedence, capability gating, ClaudeCodeRunner snapshot
- `scripts/tests/test_subprocess_mocks.py` — update mock target
- `scripts/tests/test_worker_pool.py` — update mock targets, audit argv fixtures
- `scripts/tests/test_config_schema.py` — add `test_orchestration_in_schema()`

## Dependent Callers to Verify (alias continuity)

- `scripts/little_loops/fsm/runners.py:20` — imports `run_claude_command`; alias keeps it working, verify against new host-runner path
- `scripts/little_loops/issue_manager.py:38,45` — imports `run_claude_command`; same alias path
- `scripts/little_loops/cli/generate_skill_descriptions.py:91` — imports `run_claude_command` dynamically; same alias path

## Tests

- `test_host_runner.py::test_detect_explicit_override` — `LL_HOST_CLI=codex` wins
- `test_host_runner.py::test_detect_falls_back_to_hook_host` — uses `LL_HOOK_HOST`
- `test_host_runner.py::test_detect_binary_probe_order` — claude → codex → pi
- `test_host_runner.py::test_raises_when_no_host` — clear error with remediation
- `test_host_runner.py::test_claude_runner_matches_legacy_args` — snapshot of pre-refactor argv (inline-list pattern from `test_subprocess_mocks.py::TestRunClaudeCommand::test_command_includes_correct_arguments`)
- `test_host_runner.py::test_capability_warning` — requesting unsupported capability emits `CapabilityNotSupported`
- `test_config_schema.py::test_orchestration_in_schema` — assert schema structure follows `test_hooks_in_schema()` pattern

### Additional Tests (Wiring Pass — added by `/ll:wire-issue`)

_Tests not in the AC that will break or need mock-target updates:_

- `scripts/tests/test_issue_manager.py` — patches `little_loops.issue_manager._run_claude_base` at lines 986 and 1019 in `TestStreamingCallback`; mock target shifts if `issue_manager` routes through `host_runner` — update to patch `host_runner.resolve_host` [Agent 2 + Agent 3 finding]
- `scripts/tests/test_generate_skill_descriptions.py` — patches `little_loops.subprocess_utils.run_claude_command` directly in `TestProcessSkills` (line 138); mock target shifts when `generate_skill_descriptions` routes through `host_runner` — NOT in known list [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` — patches `little_loops.fsm.evaluators.subprocess.run` at three integration-test locations (lines 1773, 1816, 1862); breaks when `evaluators.py` routes through `host_runner` — NOT in known list [Agent 3 finding]
- `scripts/tests/test_extension.py` — `TestNewProtocols` class: each new `__all__` export must get a corresponding `test_smoke_import_*` test; add entries for `HostRunner`, `HostInvocation`, `HostNotConfigured`, `CapabilityNotSupported` following existing `test_smoke_import_ll_hook_event` pattern [Agent 2 finding]
- `scripts/tests/test_config.py` — add `OrchestrationConfig` to the import block (lines 11–45); `TestResolveConfigPath` uses `monkeypatch.delenv("LL_HOOK_HOST")` throughout — ensure new `LL_HOST_CLI` env var reads in `config/core.py` don't bleed across tests [Agent 3 finding]
- `scripts/tests/test_orchestrator.py` — integration fixture constructs `BRConfig` from a minimal dict lacking `orchestration.host_cli`; verify `OrchestrationConfig` has a sensible default so this fixture doesn't break when `_parse_config()` is updated [Agent 3 finding]

## Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/HOST_COMPATIBILITY.md` — `[^orch]` footnote (lines ~70–75) explicitly lists the six pre-refactor call-site line numbers; becomes stale once FEAT-1464 migrates them — update footnote to note that all six sites now route through `host_runner` [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` — "Running Claude in Worktrees" section attributes `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` to `run_claude_command` in `subprocess_utils.py`; this env-construction logic moves into `ClaudeCodeRunner.build_streaming()` after refactor — update section attribution [Agent 2 finding]
- `docs/ARCHITECTURE.md` — directory tree entry `subprocess_utils.py  # Subprocess handling` (line 253) is partially superseded; add `host_runner.py  # Host CLI abstraction (HostRunner Protocol + ClaudeCodeRunner)` as a peer entry [Agent 2 finding]
- `docs/reference/API.md` — `#### run_claude_command` function docs remain accurate (signature unchanged, function still exists as alias) but description "Invoke Claude CLI command" should be updated to reflect host-agnostic routing; `little_loops.subprocess_utils` module-index entry (line 34) should gain a peer `little_loops.host_runner` entry [Agent 2 finding]
- `CONTRIBUTING.md` — package structure directory tree (line 222) does not list `host_runner.py`; add entry alongside `subprocess_utils.py` [Agent 2 finding]

## Impact

- No behavioral change for Claude Code users
- Safe-refactor baseline that FEAT-1465 and FEAT-1466 build on
- Grep AC (`no hard-coded "claude" literals`) becomes verifiable CI gate after this PR

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Call-site argv & subprocess subtleties (not captured in the Call site profiles table)

- **`run_claude_command` (`subprocess_utils.py:260-300`)** — uses `subprocess.Popen` (not `subprocess.run`), with `text=True, bufsize=1, stdout=PIPE, stderr=PIPE`, no explicit `stdin` (inherits from parent — NOT `DEVNULL` or `PIPE`), `cwd=working_dir`. Return value is a **manually-constructed** `CompletedProcess[str]` at line ~422 where `stdout` is `"\n".join(...)` of assistant-event text and `returncode` falls back to `-9` on `None`. Argv order subtlety for the snapshot test: `--agent` and `--tools` come **after** `-p <command>`, not before.
- **`_detect_worktree_model_via_api` (`worker_pool.py:578-595`)** — also sets `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` (same env treatment as `run_claude_command`); issue table omits this. Uses `subprocess.run` with `cwd=worktree_path, capture_output=True, text=True, timeout=30`. Hardcoded prompt literal `"reply with just 'ok'"`. Returns `str | None` (extracted from `data["modelUsage"]` first key).
- **`cmd_capabilities` (`action.py:142, 149`)** — line 142 is `shutil.which("claude")` (pure Python, **not** a subprocess); line 149 is the only subprocess (`subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=10)`). Resolver implementation must expose both a `detect()` (replaces `shutil.which`) and `build_version_check()` (replaces the `--version` argv).
- **`_spawn_new_claude_session` (`handoff_handler.py:109-122`)** — **no env modifications** (inherits parent entirely; no `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR`). `subprocess.Popen` with `text=True, start_new_session=True, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL`. Returned `Popen` is stored in `HandoffResult.spawned_process` but never `.wait()`-ed.
- **`evaluate_llm_structured` (`evaluators.py:608-624`)** — argv construction starts at line 608, actual `subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)` is at line 624 (default `timeout=1800`). **No env modifications**. `--output-format json` is **explicit** in argv (line 612-613), not implicit. The `--json-schema` value is `json.dumps(effective_schema)` — a serialized string, not a file path. JSON-parse fallback: tries `result["structured_output"]`, then `result["result"]`, then direct dict; with JSONL fallback (last non-empty line).

### Convention novelty (FEAT-1464 introduces two new conventions)

- **No `@dataclass(frozen=True)` exists anywhere in `scripts/little_loops/`** — `HostInvocation(frozen=True)` would establish a new convention. Closest existing analog: `hooks/types.py:LLHookEvent` (mutable but immutable-by-convention, with `to_dict()`/`from_dict()` classmethods). Implementer should either (a) commit to `frozen=True` as a new convention or (b) match the existing `LLHookEvent` mutable-with-discipline pattern. Recommend (a) since `HostInvocation` is a value object passed across boundaries.
- **No `class FooWarning(UserWarning):` subclass exists** in the package — `CapabilityNotSupported(UserWarning)` would also be new. Existing `warnings.warn()` usages (`config/core.py:310-324` deprecation warnings; `issues/anchor_sweep.py:77`) use built-in categories only.

### Concrete pattern anchors to model on

| Aspect | File:anchor | Notes |
|--------|-------------|-------|
| `@runtime_checkable` Protocol | `extension.py:LLExtension`, `extension.py:LLHookIntentExtension` | Apply `@runtime_checkable` only if `isinstance(obj, HostRunner)` is needed at runtime |
| Registry + dispatch | `hooks/__init__.py:44-70` (`_HOOK_INTENT_REGISTRY`, `_register_hook_intents`, `_dispatch_table`) | Duplicate-name handling raises `ValueError`; built-ins shadow extension-provided entries |
| Nested sub-config `from_dict` | `config/features.py:EventsConfig.from_dict` (lines 474-482) | Each sub-config calls `data.get("key", {})` so an empty dict is always passed down |
| Nested sub-config with own `from_dict` | `config/features.py:LoopsConfig` + `LoopsGlyphsConfig` (lines 338-353) | Closest match if `OrchestrationConfig` grows nested sub-blocks |
| Property exposure on `BRConfig` | `config/core.py:211-284` | Each sub-config has a `@property` returning the typed dataclass |
| Inline-argv snapshot test (Popen) | `tests/test_subprocess_mocks.py:63-103` (`TestRunClaudeCommand::test_command_includes_correct_arguments`) | Uses `captured_args` + `capture_popen` side_effect, direct `== [...]` list assertion |
| Inline-argv snapshot test (run) | `tests/test_subprocess_mocks.py:404-418` (`TestCheckGitStatus::test_correct_git_commands`) | Simpler variant for `subprocess.run` sites; uses `mock_run.call_args_list[0][0][0]` |
| Schema test pattern | `tests/test_config_schema.py:136-155` (`test_hooks_in_schema`) | Asserts key present, `type == "object"`, `additionalProperties is False`, then each sub-key + enum |
| JSON schema entry shape | `config-schema.json:1097-1108` (existing `hooks` block) | Add `orchestration` as a peer block with `additionalProperties: false` and `host_cli` enum |

### Additional test files requiring mock-target updates (not enumerated in Acceptance Criteria)

- `scripts/tests/test_subprocess_utils.py` — additional coverage for `run_claude_command`; mock targets shift to `host_runner.resolve_host`
- `scripts/tests/test_action.py` — `cmd_capabilities()` tests; replace `shutil.which` mock with `host_runner.resolve_host().detect()` mock
- `scripts/tests/test_handoff_handler.py` — `_spawn_new_claude_session()` tests; mock `host_runner.build_detached()` instead of `subprocess.Popen`
- `scripts/tests/test_fsm_evaluators.py` — LLM-graded evaluator tests; mock `host_runner.build_blocking_json()` instead of `subprocess.run`

### `__all__` export discipline

`scripts/little_loops/__init__.py` currently groups exports by category with section comments (`# extensions`, `# hook types`, etc.). Add a new `# host runner` section block following the same convention; add `HostRunner`, `HostInvocation`, `HostNotConfigured`, `CapabilityNotSupported` (and `HostCapabilities` if introduced as a public type).

## Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `scripts/tests/test_issue_manager.py` — shift `_run_claude_base` patch in `TestStreamingCallback` (lines 986, 1019) to the new `host_runner` dispatch path
2. Update `scripts/tests/test_generate_skill_descriptions.py` — shift `little_loops.subprocess_utils.run_claude_command` patch in `TestProcessSkills` to `host_runner` dispatch point
3. Update `scripts/tests/test_fsm_executor.py` — shift 3 `little_loops.fsm.evaluators.subprocess.run` patches (lines 1773, 1816, 1862) to `host_runner` dispatch path
4. Update `scripts/tests/test_extension.py` — add `test_smoke_import_host_runner`, `test_smoke_import_host_invocation`, `test_smoke_import_host_not_configured`, `test_smoke_import_capability_not_supported` to `TestNewProtocols` following existing pattern
5. Update `scripts/tests/test_config.py` — add `OrchestrationConfig` to the import block; audit `TestResolveConfigPath` `monkeypatch.delenv("LL_HOOK_HOST")` calls for `LL_HOST_CLI` isolation
6. Verify `scripts/tests/test_orchestrator.py` — confirm `BRConfig` with no `orchestration` key still loads cleanly after `_parse_config()` update (i.e., `OrchestrationConfig` has defaults for all fields)
7. Update `docs/reference/HOST_COMPATIBILITY.md` — revise `[^orch]` footnote from specific call-site line numbers to post-refactor routing summary
8. Update `docs/development/TROUBLESHOOTING.md` — revise "Running Claude in Worktrees" section to attribute env-var construction to `ClaudeCodeRunner.build_streaming()` instead of `subprocess_utils.run_claude_command`
9. Update `docs/ARCHITECTURE.md` — add `host_runner.py` entry to the Python package directory tree
10. Update `docs/reference/API.md` — add `little_loops.host_runner` module entry; update `run_claude_command` description to "Host-agnostic CLI command invocation"
11. Update `CONTRIBUTING.md` — add `host_runner.py` to the package structure directory tree

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-15_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 66/100 → MODERATE

### Outcome Risk Factors
- Wide change surface across 25 sites (6 source call sites + 8 test mock-target updates + 5 doc edits) — a missed mock target will fail silently; running the full test suite immediately after each call-site migration is the mitigation
- Per-site flag variance: each of the 6 call sites maps to a different factory method (build_streaming / build_blocking_json / build_version_check / build_detached) with distinct argv, env, and subprocess modes — implement `test_claude_runner_matches_legacy_args` snapshot test first to lock in correct argv before migrating sites
- `host_runner.py` is a net-new module introducing two conventions new to this codebase (`frozen=True` dataclass, `CapabilityNotSupported(UserWarning)`) — minor friction in code review, both well-justified in codebase research findings

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-15
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-1467: host_runner.py Core Module, Config Wiring, and Foundation Tests
- FEAT-1468: Call Site Migrations, Test Mock Updates, and Documentation

**Note**: Children are strictly sequential (FEAT-1468 requires FEAT-1467). If parallelism isn't available, consider implementing as a single PR.

## Session Log
- `/ll:refine-issue` - 2026-05-15T12:46:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82fbcae4-2906-4b5e-9aa8-40a0851611c6.jsonl`
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d0a84cca-2574-4c32-8edd-684205b8feb0.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/edba2017-dcd5-412e-a69d-62b9a5dd8541.jsonl`
- `/ll:wire-issue` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6024d56a-9aff-4760-9ebc-3ce5b51bb09f.jsonl`

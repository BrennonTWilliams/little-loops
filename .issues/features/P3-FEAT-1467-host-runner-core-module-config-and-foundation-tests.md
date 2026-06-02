---
id: FEAT-1467
type: FEAT
priority: P3
status: done
completed_at: 2026-05-15T13:27:20Z
parent: FEAT-1464
discovered_date: 2026-05-15
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1467: host_runner.py Core Module, Config Wiring, and Foundation Tests

## Summary

Introduce `scripts/little_loops/host_runner.py` with the `HostRunner` Protocol, `HostInvocation` dataclass, `ClaudeCodeRunner` implementation, `CapabilityNotSupported`, and `HostNotConfigured`. Wire `OrchestrationConfig` into the config layer and JSON schema. Export all new public types from `scripts/little_loops/__init__.py`. Deliver isolation-tested foundation (`test_host_runner.py`) and config/extension smoke tests. No production call sites are migrated here — that lands in FEAT-1468.

## Parent Issue

Decomposed from FEAT-1464: Scaffold host_runner.py + ClaudeCodeRunner + Call Site Migrations + Config Wiring

## Scope

Covers:
- `### host_runner.py design` (Protocol, dataclass, ClaudeCodeRunner, resolve_host, capability surface)
- `### Patterns to follow` (Protocol pattern, registry, warning convention)
- `### Config wiring` (OrchestrationConfig, schema update)
- Wiring Phase items 4 (test_extension.py), 5 (test_config.py), 6 (test_orchestrator.py)
- Wiring Phase items 9 (ARCHITECTURE.md), 11 (CONTRIBUTING.md)

**Explicitly out of scope**: All 6 production call site migrations, test mock-target updates for call sites, HOST_COMPATIBILITY.md footnote, TROUBLESHOOTING.md, API.md description updates (all in FEAT-1468).

## Acceptance Criteria

- [ ] `scripts/little_loops/host_runner.py` exposes: `resolve_host()`, `HostInvocation`, `HostRunner`, `HostNotConfigured`, `CapabilityNotSupported`, `HostCapabilities`
- [ ] `resolve_host()` detection order: `LL_HOST_CLI` env → `LL_HOOK_HOST` env → binary probe (`claude` → `codex` → `pi`) → `HostNotConfigured` with remediation hint
- [ ] `ClaudeCodeRunner` implements all four factory methods: `build_streaming`, `build_blocking_json`, `build_version_check`, `build_detached`
- [ ] `CapabilityNotSupported` subclasses `UserWarning`
- [ ] `HostInvocation` is a `@dataclass(frozen=True)` (new convention for value objects passed across boundaries)
- [ ] `OrchestrationConfig` added to `config/core.py` with parse in `BRConfig._parse_config()` and serialization in `BRConfig.to_dict()`
- [ ] `OrchestrationConfig` re-exported from `config/__init__.py` following existing `__all__` pattern
- [ ] `HostRunner`, `HostInvocation`, `HostNotConfigured`, `CapabilityNotSupported` added to `scripts/little_loops/__init__.py` `__all__` in a new `# host runner` section
- [ ] `config-schema.json` includes `orchestration.host_cli` enum `["auto", "claude-code", "codex", "opencode", "pi"]` with default `"auto"`; host-name spellings match existing `hooks.host` enum at line 1103
- [ ] `test_host_runner.py::test_detect_explicit_override` — `LL_HOST_CLI=codex` wins
- [ ] `test_host_runner.py::test_detect_falls_back_to_hook_host` — uses `LL_HOOK_HOST`
- [ ] `test_host_runner.py::test_detect_binary_probe_order` — claude → codex → pi
- [ ] `test_host_runner.py::test_raises_when_no_host` — clear error with remediation
- [ ] `test_host_runner.py::test_claude_runner_matches_legacy_args` — snapshot of pre-refactor argv (inline-list pattern from `test_subprocess_mocks.py::TestRunClaudeCommand::test_command_includes_correct_arguments`)
- [ ] `test_host_runner.py::test_capability_warning` — requesting unsupported capability emits `CapabilityNotSupported`
- [ ] `test_config_schema.py::test_orchestration_in_schema` added following `test_hooks_in_schema()` pattern
- [ ] `test_extension.py::TestNewProtocols` gains `test_smoke_import_host_runner`, `test_smoke_import_host_invocation`, `test_smoke_import_host_not_configured`, `test_smoke_import_capability_not_supported`
- [ ] `test_config.py` has `OrchestrationConfig` in the import block; `TestResolveConfigPath` calls that use `monkeypatch.delenv("LL_HOOK_HOST")` audited for `LL_HOST_CLI` isolation
- [ ] `test_orchestrator.py` integration fixture with no `orchestration` key in config dict still loads cleanly after `_parse_config()` update
- [ ] `docs/ARCHITECTURE.md` gains `host_runner.py  # Host CLI abstraction (HostRunner Protocol + ClaudeCodeRunner)` as peer entry to `subprocess_utils.py`
- [ ] `CONTRIBUTING.md` package structure directory tree gains `host_runner.py` entry alongside `subprocess_utils.py`
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

### Patterns to follow

- **Protocol pattern**: Model on `extension.py` `@runtime_checkable` Protocols (`LLExtension`, `LLHookIntentExtension`)
- **Lazy dispatch registry**: Model `_HOST_RUNNER_REGISTRY` on `hooks/__init__.py:44-70` `_HOOK_INTENT_REGISTRY` + `_dispatch_table()` pattern
- **Warning vs. exception**: `CapabilityNotSupported(UserWarning)` following `config/core.py` `warnings.warn()` pattern for opt-in capture

### Config wiring

Add `OrchestrationConfig` to `config/core.py` following the nested sub-config `from_dict` pattern in `config/features.py:EventsConfig.from_dict` (lines 474-482). Each sub-config calls `data.get("key", {})` so an empty dict is always passed down — ensures `OrchestrationConfig` has sensible defaults when the key is absent.

## Files to Modify

- `scripts/little_loops/host_runner.py` — NEW: Protocol + ClaudeCodeRunner + registry + capability surface
- `scripts/little_loops/config/core.py` — add `OrchestrationConfig`, parse in `_parse_config()` (line 185), serialize in `to_dict()` (line 464)
- `scripts/little_loops/config/__init__.py` — re-export `OrchestrationConfig`
- `scripts/little_loops/__init__.py` — add host_runner types to `__all__` in new `# host runner` section
- `config-schema.json` — add `orchestration.host_cli` enum (peer block to existing `hooks` at line 1097)
- `scripts/tests/test_host_runner.py` — NEW: detection precedence, capability gating, ClaudeCodeRunner snapshot
- `scripts/tests/test_config_schema.py` — add `test_orchestration_in_schema()`
- `scripts/tests/test_extension.py` — add smoke import tests for new types
- `scripts/tests/test_config.py` — add `OrchestrationConfig` import; audit `LL_HOST_CLI` env isolation
- `scripts/tests/test_orchestrator.py` — verify BRConfig with no `orchestration` key loads cleanly
- `docs/ARCHITECTURE.md` — add `host_runner.py` directory tree entry
- `CONTRIBUTING.md` — add `host_runner.py` to package structure tree
- `docs/reference/CONFIGURATION.md` — add `### orchestration` section documenting `orchestration.host_cli`

## Integration Map

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — add `### orchestration` subsection documenting `orchestration.host_cli` enum `["auto", "claude-code", "codex", "opencode", "pi"]` with `default: "auto"`; placed as a peer to existing `hooks`, `parallel`, `events` sub-sections in "Manual Configuration"; this is the only user-facing config key introduced by FEAT-1467 with no existing doc coverage [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_host_runner.py` — add `test_host_invocation_is_frozen`: instantiate `HostInvocation` and assert `dataclasses.FrozenInstanceError` is raised on attribute mutation; no existing frozen-dataclass test in the suite — this establishes the new-convention verification pattern [Agent 3 finding]

## Codebase Research Findings

Inherited from FEAT-1464 and verified by `/ll:refine-issue` (2026-05-15). Key anchors:

| Aspect | File:anchor | Notes |
|--------|-------------|-------|
| `@runtime_checkable` Protocol | `extension.py:38` (`LLExtension`), `extension.py:103` (`LLHookIntentExtension`) | Apply `@runtime_checkable` only if `isinstance(obj, HostRunner)` is needed at runtime |
| Registry + dispatch | `hooks/__init__.py:44-70` (`_HOOK_INTENT_REGISTRY`, `_register_hook_intents`, `_dispatch_table`) | Extension-vs-extension duplicate raises `ValueError` (line 47-57); extension-vs-built-in **silently shadows** via `{**_HOOK_INTENT_REGISTRY, **built_ins}` (line 60-70) — built-ins always win. Mirror this for `ClaudeCodeRunner`: register as a built-in, allow extensions to register additional hosts without conflict. |
| Nested sub-config `from_dict` | `config/features.py:474-482` (`EventsConfig.from_dict`) | Use `data.get("key", {})` pattern |
| `BRConfig._parse_config` insertion | `config/core.py:185` (start of method); last sub-config line is `self._events = EventsConfig.from_dict(...)` at line 209 | Insert `self._orchestration = OrchestrationConfig.from_dict(self._raw_config.get("orchestration", {}))` after line 209 |
| `BRConfig.to_dict` serialization | `config/core.py:464` | Manually constructed dict of dicts; add `"orchestration"` peer block |
| Property exposure on `BRConfig` | `config/core.py:205-209` (init) + `211-284` (`@property` blocks) | Each sub-config has private `_field` in `__init__` and a public `@property` returning the typed dataclass |
| `warnings.warn()` pattern | `config/core.py:310-314` | Existing precedent uses `DeprecationWarning` with `stacklevel=2`; `CapabilityNotSupported(UserWarning)` follows the same 3-arg call shape |
| Schema test pattern | `tests/test_config_schema.py:136-155` (`test_hooks_in_schema`) | Assert key, `type == "object"`, `additionalProperties is False`, sub-key + enum |
| JSON schema entry shape | `config-schema.json:1097-1108` | `hooks.host` enum at line 1103 is exactly `["claude-code", "opencode", "codex"]`. Add `orchestration` as a peer block; `host_cli` enum extends this with `"auto"` (default) and `"pi"` |
| Smoke import pattern | `tests/test_extension.py:616-632` (`TestNewProtocols.test_smoke_import_ll_hook_event`, `test_smoke_import_ll_hook_intent_extension`) | One-liner pattern: `from little_loops import X  # noqa: F401` + `assert X is not None` |
| Legacy-argv snapshot baseline | `subprocess_utils.py:219` (`run_claude_command` def); `cmd_args` list built at lines 260-273 | This is the argv `test_claude_runner_matches_legacy_args` must match. Existing inline-list assertion lives at `tests/test_subprocess_mocks.py:63-103` |

**Convention novelty** (FEAT-1467 establishes these for the first time, both confirmed by full-tree grep):
- No `@dataclass(frozen=True)` exists in `scripts/little_loops/` — `HostInvocation(frozen=True)` is a new convention for value objects
- No `class FooWarning(UserWarning):` subclass exists — `CapabilityNotSupported(UserWarning)` is also new
- No `LL_HOST_CLI` references exist anywhere in the codebase — `resolve_host()` introduces this env var. `LL_HOOK_HOST` is already established (29 files); the resolution order in AC must consult both.

**FEAT-1468 deferred surface (do NOT touch in FEAT-1467)**: The call sites of `run_claude_command` that FEAT-1468 will migrate are concentrated in:
- `fsm/runners.py:20, 102` (direct import + call)
- `issue_manager.py:46, 97, 236, 337, 511, 567, 727` (wrapped as `_run_claude_base`, re-exported as enriched `run_claude_command`)
- `parallel/worker_pool.py:33, 277, 379, 643, 738, 828` (wrapped as `_run_claude_base`, method `_run_claude_command`)
- `cli/action.py:61, 84, 118` (direct import + call)
- `cli/generate_skill_descriptions.py:91, 116` (direct import + call)

Listed here only to confirm FEAT-1467 stays strictly within its own scope.

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

13. Update `docs/reference/CONFIGURATION.md` — add `### orchestration` subsection documenting `orchestration.host_cli` with enum values and default `"auto"` (peer to existing `hooks`, `parallel`, `events` subsections)
14. Update `scripts/tests/test_host_runner.py` — add `test_host_invocation_is_frozen` asserting `dataclasses.FrozenInstanceError` on mutation (establishes frozen-dataclass test convention for the codebase)

## Resolution

Implemented FEAT-1467 (2026-05-15):

- **NEW** `scripts/little_loops/host_runner.py`: `HostRunner` Protocol, `HostInvocation` (`@dataclass(frozen=True)`), `HostCapabilities`, `ClaudeCodeRunner`, `resolve_host()`, `HostNotConfigured`, `CapabilityNotSupported(UserWarning)`, `_HOST_RUNNER_REGISTRY`
- **Config wiring**: `OrchestrationConfig` added to `config/core.py`, parsed in `_parse_config()`, serialized in `to_dict()`, exposed via `BRConfig.orchestration` property; re-exported from `config/__init__.py`
- **Schema**: `orchestration.host_cli` enum `["auto","claude-code","codex","opencode","pi"]` added to `config-schema.json` as peer to `hooks`
- **Public API**: `HostRunner`, `HostInvocation`, `HostNotConfigured`, `CapabilityNotSupported` added to `little_loops.__all__` under new `# host runner` section
- **Tests** (15 new): `test_host_runner.py` covers detection precedence (explicit/hook-host/probe/raise), `ClaudeCodeRunner` legacy-argv snapshot, frozen-dataclass guard, `CapabilityNotSupported` warning, `HostRunner` Protocol satisfaction; plus `test_orchestration_in_schema` in `test_config_schema.py`, 5 smoke-import tests in `test_extension.py`, `TestOrchestrationConfig` (5 tests) in `test_config.py`, and `TestBRConfigWithoutOrchestration` in `test_orchestrator.py`
- **Docs**: `host_runner.py` peer entry added to `docs/ARCHITECTURE.md` and `CONTRIBUTING.md` package trees; `### orchestration` subsection added to `docs/reference/CONFIGURATION.md`

Verification: `python -m pytest scripts/tests/` → 6537 passed (2 pre-existing failures in `test_update_skill.py::TestMarketplaceVersionSync` unrelated — version drift between `marketplace.json`/`plugin.json`); `ruff check scripts/` clean; `python -m mypy scripts/little_loops/host_runner.py scripts/little_loops/config/core.py scripts/little_loops/__init__.py` clean.

Strictly within scope: no production call sites of `run_claude_command` migrated (deferred to FEAT-1468).

## Session Log
- `/ll:manage-issue` - 2026-05-15T13:27:20Z
- `/ll:ready-issue` - 2026-05-15T13:18:22 - `3668e713-a602-4cbb-81d7-b3d14d634f08.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00 - `cd508d33-6a51-49ce-9e65-117a04eea2f9.jsonl`
- `/ll:wire-issue` - 2026-05-15T13:15:04 - `92ff58dc-1aac-46be-a467-8ab3f7cfb61c.jsonl`
- `/ll:refine-issue` - 2026-05-15T13:07:18 - `6763033d-632a-41bd-ade1-cf6f9e9e8e50.jsonl`
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `6024d56a-9aff-4760-9ebc-3ce5b51bb09f.jsonl`

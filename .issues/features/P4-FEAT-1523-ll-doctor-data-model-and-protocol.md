---
id: FEAT-1523
type: FEAT
priority: P4
status: done
captured_at: '2026-05-16T15:07:07Z'
completed_at: '2026-05-16T17:08:28Z'
discovered_date: 2026-05-16
discovered_by: issue-size-review
parent: FEAT-1496
labels:
- host-compat
- preflight
size: Medium
decision_needed: false
confidence_score: 98
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1523: ll-doctor — core data model, Protocol, and host-selection helper

## Summary

Establish the foundational data model and `describe_capabilities()` Protocol method needed by `ll-doctor`. All downstream children (CLI tool, docs) depend on this landing first.

## Motivation

`ll-doctor` (FEAT-1496) needs a structured, programmatic way to report each host CLI's capability matrix. Today, capability information is scattered across `HostCapabilities` flags, `CapabilityNotSupported` warnings emitted at call sites, and `HostNotConfigured` exceptions raised from `resolve_host()`. There is no single surface a CLI can query to produce a tabular report.

This child lands first because the CLI tool and documentation siblings of FEAT-1496 both depend on these types and the Protocol method. Without the data model in place, the rest of the preflight effort cannot proceed.

## Parent Issue

Decomposed from FEAT-1496: Host-capability preflight check (`ll-doctor`)

## Scope

Covers implementation steps 1, 2, 3, 10, and 14 from the parent issue.

## Use Case

A maintainer adding a new host CLI runner (alongside `ClaudeCodeRunner`, `CodexRunner`, `OpenCodeRunner`, `PiRunner`) needs to declare what their host supports — which capabilities are full vs. partial vs. unsupported, and which hooks install vs. defer. They implement `describe_capabilities()` on their runner once, and that single method feeds both `ll-doctor`'s preflight report and any future tooling (docs generators, config validators) that needs to introspect host compatibility.

## Current Behavior

- No `CapabilityEntry`, `HookEntry`, or `CapabilityReport` dataclass exists in `scripts/little_loops/host_runner.py`.
- The `HostRunner` Protocol (lines 102-155) has no `describe_capabilities()` method.
- `CodexRunner` carries a `capabilities` dict (lines 300-305) and emits `CapabilityNotSupported` warnings at call sites (319-325 agent, 326-333 tools, 372-380 json_schema), but this state is not exposed through a queryable interface.
- `OpenCodeRunner` and `PiRunner` raise `HostNotConfigured` rather than declaring themselves absent in a structured way.
- `resolve_host()` (lines 562-606) reads `LL_HOST_CLI` from the environment but does not consult `orchestration.host_cli` in `.ll/ll-config.json`.
- `config-schema.json` has no `orchestration` top-level key, so `host_cli` is undocumented in the schema.

## Expected Behavior

- Three frozen dataclasses (`CapabilityEntry`, `HookEntry`, `CapabilityReport`) live in `host_runner.py` alongside `HostInvocation`.
- `HostRunner.describe_capabilities() -> CapabilityReport` is part of the Protocol; all four concrete runners implement it.
- A host-selection helper bridges `orchestration.host_cli` in `BRConfig` to `LL_HOST_CLI` before `resolve_host()` runs, satisfying AC#1 of the parent (resolution via both env var and config key).
- `CapabilityReport`, `CapabilityEntry`, `HookEntry` are re-exported from `scripts/little_loops/__init__.py` so downstream consumers (CLI, tests, docs) can import from the package root.
- `config-schema.json` either documents the `orchestration.host_cli` key or explicitly notes that `ll-doctor` reads it via raw `BRConfig` ahead of schema validation.

## Acceptance Criteria

- [ ] `CapabilityEntry(name, status: Literal["full","partial","unsupported"], note)` dataclass added to `scripts/little_loops/host_runner.py` alongside `HostInvocation` (lines 82-99), using `@dataclass(frozen=True)`
- [ ] `HookEntry(name, status: Literal["installed","registered","deferred","absent"], note)` dataclass added
- [ ] `CapabilityReport(host, binary, version, capabilities: list[CapabilityEntry], hooks: list[HookEntry])` dataclass added
- [ ] `describe_capabilities() -> CapabilityReport` added to `HostRunner` Protocol (lines 102-155)
- [ ] All four concrete runners implement `describe_capabilities()`:
  - `ClaudeCodeRunner` → all capabilities `full`
  - `CodexRunner` → `agent_select=False, tool_allowlist=False` sourced from existing `capabilities` at lines 300-305; `json_schema` partial
  - `OpenCodeRunner` → `HostNotConfigured` represented as absent-host state
  - `PiRunner` → `HostNotConfigured` represented as absent-host state
- [ ] A host-selection helper reads `orchestration.host_cli` from `.ll/ll-config.json` and sets `LL_HOST_CLI` before calling `resolve_host()` (satisfies AC#1 of parent: resolution via both env var and config key)
- [ ] `CapabilityReport`, `CapabilityEntry`, `HookEntry` added to `scripts/little_loops/__init__.py` imports and `__all__` (mirror existing `CapabilityNotSupported` pattern at lines 22-27 and 68-71)
- [ ] `config-schema.json` gap resolved: `orchestration` top-level key with `host_cli` string property added (or document explicitly that `ll-doctor` reads it via raw `BRConfig` before schema validation)
- [ ] Consistency test: invoke `CodexRunner.build_streaming(agent=..., tools=...)` under `warnings.catch_warnings(record=True)` and assert every emitted `CapabilityNotSupported` maps to an `unsupported` entry in `describe_capabilities()` output

## API/Interface

```python
# scripts/little_loops/host_runner.py — added alongside HostInvocation

@dataclass(frozen=True)
class CapabilityEntry:
    name: str
    status: Literal["full", "partial", "unsupported"]
    note: str = ""

@dataclass(frozen=True)
class HookEntry:
    name: str
    status: Literal["installed", "registered", "deferred", "absent"]
    note: str = ""

@dataclass(frozen=True)
class CapabilityReport:
    host: str
    binary: str
    version: str
    capabilities: list[CapabilityEntry] = field(default_factory=list)
    hooks: list[HookEntry] = field(default_factory=list)


class HostRunner(Protocol):
    # ... existing methods ...
    def describe_capabilities(self) -> CapabilityReport: ...


# Host-selection helper (location: doctor.py or shared utility)
def apply_host_cli_from_config(config: BRConfig) -> None:
    """Read orchestration.host_cli from config and export as LL_HOST_CLI.

    Must run before resolve_host() so env-var lookup picks up the config value.
    Env var takes precedence if already set (caller override).
    """
```

Re-exports added to `scripts/little_loops/__init__.py`:

```python
from .host_runner import (
    CapabilityEntry,
    CapabilityReport,
    HookEntry,
    # ... existing exports ...
)

__all__ = [
    "CapabilityEntry",
    "CapabilityReport",
    "HookEntry",
    # ... existing entries ...
]
```

## Implementation Steps

1. In `scripts/little_loops/host_runner.py`, add after `HostInvocation` (lines 82-99):
   ```python
   @dataclass(frozen=True)
   class CapabilityEntry:
       name: str
       status: Literal["full", "partial", "unsupported"]
       note: str

   @dataclass(frozen=True)
   class HookEntry:
       name: str
       status: Literal["installed", "registered", "deferred", "absent"]
       note: str = ""

   @dataclass(frozen=True)
   class CapabilityReport:
       host: str
       binary: str
       version: str
       capabilities: list[CapabilityEntry] = field(default_factory=list)
       hooks: list[HookEntry] = field(default_factory=list)
   ```
2. Add `describe_capabilities(self) -> CapabilityReport` to `HostRunner` Protocol (lines 102-155).
3. Implement on each runner:
   - `ClaudeCodeRunner`: all capabilities `"full"`; hooks from `hooks/hooks.json`
   - `CodexRunner`: source from `self.capabilities` (lines 300-305); warning sites at 319-325 (agent), 326-333 (tools), 372-380 (json_schema) become the `"unsupported"`/`"partial"` entries
   - `OpenCodeRunner`, `PiRunner`: emit a single `CapabilityEntry` with `status="unsupported"` and note `"binary not configured (HostNotConfigured)"`
4. Add `apply_host_cli_from_config()` helper to `scripts/little_loops/host_runner.py` (alongside `resolve_host()`) — `doctor.py` does not exist yet (created by sibling FEAT-1524), so placing it here avoids a missing-module import. The sibling CLI child can import it from `host_runner`.
5. Update `scripts/little_loops/host_runner.py:32-43` (`__all__`) and `scripts/little_loops/__init__.py:22-27` (import) and `68-71` (`__all__`): add `CapabilityReport`, `CapabilityEntry`, `HookEntry` to all three locations.
6. Resolve `config-schema.json` gap for `orchestration.host_cli` — five sub-steps required:
   a. Create `OrchestrationConfig` dataclass in `scripts/little_loops/config/` following the `AutomationConfig` pattern in `config/automation.py`
   b. Wire `BRConfig._parse_config()` in `scripts/little_loops/config/core.py`: `self._orchestration = OrchestrationConfig.from_dict(self._raw_config.get("orchestration", {}))`
   c. Add `@property orchestration(self) -> OrchestrationConfig` on `BRConfig`
   d. Export `OrchestrationConfig` from `scripts/little_loops/config/__init__.py`
   e. Add `orchestration` object with `host_cli` string property to `config-schema.json`
7. Tests at `scripts/tests/test_host_runner.py` (or a new `test_cli_doctor_model.py`):
   - `TestCapabilityReport` — round-trip dataclass construction; include frozen-instance mutation test mirroring `TestHostInvocation.test_host_invocation_is_frozen` pattern
   - `TestDescribeCapabilities` — one test per runner; assert each runner returns a `CapabilityReport`
   - Consistency test: use `pytest.warns(CapabilityNotSupported)` (not `warnings.catch_warnings(record=True)`) — the established pattern in `test_host_runner.py` uses `pytest.warns()`
8. Run: `python -m pytest scripts/tests/test_host_runner.py -v && python -m mypy scripts/little_loops/ && ruff check scripts/`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `scripts/tests/test_action.py` — add `describe_capabilities(self) -> CapabilityReport` stub to `FakeRunner` (line 25) returning a minimal `CapabilityReport(host="fake", binary="fake", version="0.0")` to prevent `AttributeError` in any test path that calls the new Protocol method on an injected runner
10. Extend `scripts/tests/test_config.py` — add `TestOrchestrationConfig` class with `test_from_dict_with_defaults` and `test_from_dict_with_host_cli`; extend `TestBRConfig` with `test_orchestration_property_from_file` using `sample_config` fixture
11. Extend `scripts/tests/test_config_schema.py` — add `test_orchestration_host_cli_in_schema()` to `TestConfigSchema` following the `test_hooks_in_schema` pattern; assert `orchestration.host_cli` is a string `enum` containing `"claude-code"`, `"codex"`, etc.
12. Extend `scripts/tests/conftest.py` — add `"orchestration": {}` key to the `sample_config` fixture so `TestBRConfig` exercises the default `OrchestrationConfig` construction path
13. Update `docs/ARCHITECTURE.md` — add `describe_capabilities()` to the `HostRunner (Protocol)` row in the `## Host Runner Layer` method table (line ~565)

## Files to Modify

- `scripts/little_loops/host_runner.py` — dataclasses, Protocol method, runner implementations
- `scripts/little_loops/__init__.py` — re-exports
- `config-schema.json` — `orchestration` key gap
- `scripts/little_loops/config/core.py` — wire `BRConfig._parse_config()` (step 6b) and add `@property orchestration(self) -> OrchestrationConfig` (step 6c) [wiring pass]
- `scripts/little_loops/config/__init__.py` — export `OrchestrationConfig` in import block and `__all__` (step 6d) [wiring pass]

## Files to Create

- Tests (extend `scripts/tests/test_host_runner.py` or create `scripts/tests/test_capability_report.py`)

## Integration Map

Anchor references from parent issue:
- `HostCapabilities` at `scripts/little_loops/host_runner.py:66-80` — extend, do not duplicate
- `HostInvocation` at `:82-99` — style template
- `HostRunner` Protocol at `:102-155` — add method here
- `CodexRunner.capabilities` at `:300-305` — source of ✗ rows
- Warning sites: `:319-325` (agent), `:326-333` (tools), `:372-380` (json_schema)
- `_HOST_RUNNER_REGISTRY` at `:538-543`
- `resolve_host()` at `:562-606` — does NOT read `orchestration.host_cli`

### Dependent Files (Callers/Importers)

- `scripts/little_loops/__init__.py` — re-exports `CapabilityNotSupported`; mirror that pattern for the new types
- Future `scripts/little_loops/doctor.py` (FEAT-1496 sibling) — primary consumer of `describe_capabilities()` and `apply_host_cli_from_config()`
- `scripts/little_loops/fsm/evaluators.py` — calls `resolve_host()`; `apply_host_cli_from_config()` must run before this
- `scripts/little_loops/fsm/handoff_handler.py` — calls `resolve_host()`
- `scripts/little_loops/cli/action.py` — calls `resolve_host()`; `cmd_capabilities()` function will consume the new dataclasses
- `scripts/little_loops/subprocess_utils.py` — calls `resolve_host()`
- `scripts/little_loops/parallel/worker_pool.py` — calls `resolve_host()`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_action.py` — `FakeRunner` Protocol double (line 25) implements all five current Protocol methods but is missing `describe_capabilities()`; any code path in `cli/action.py` that calls `runner.describe_capabilities()` will raise `AttributeError` — must add stub before merging [Agent 3 / Agent 2 finding]
- `scripts/tests/test_extension.py` — imports `HostRunner` and `CapabilityNotSupported` from package root; after FEAT-1523, `CapabilityEntry`, `HookEntry`, `CapabilityReport` become available from root — smoke-import assertions may need to cover the new symbols [Agent 1 finding]

### Similar Patterns

- `CapabilityNotSupported` import + `__all__` entry at `scripts/little_loops/__init__.py:22-27, 68-71` — exact pattern to mirror for the new dataclasses
- Existing `@dataclass(frozen=True)` usage on `HostInvocation` (lines 82-99) and `HostCapabilities` (lines 66-80) — style template
- `AutomationConfig.from_dict()` in `scripts/little_loops/config/automation.py` + `BRConfig._parse_config()` in `scripts/little_loops/config/core.py` — exact wiring pattern to follow for the new `OrchestrationConfig` section

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `host_runner.__all__` at `scripts/little_loops/host_runner.py:32-43` — the three new types (`CapabilityEntry`, `HookEntry`, `CapabilityReport`) must also be added here, not just to `__init__.py`. Step 5 in Implementation Steps currently only mentions `__init__.py`.
- `orchestration` config key is **absent from both `BRConfig` and `config-schema.json`** — adding it requires: (a) new `OrchestrationConfig` dataclass (follow `AutomationConfig` pattern in `config/automation.py`), (b) wiring in `BRConfig._parse_config()`, (c) `@property` on `BRConfig`, (d) export from `config/__init__.py`, (e) schema entry. Step 6 should cover all five sub-steps.
- `apply_host_cli_from_config()` **cannot live in `doctor.py`** — that file does not exist yet (it is created by sibling FEAT-1524). Recommend placing it in `host_runner.py` (alongside `resolve_host()`) so the sibling CLI child can import it without circular dependency.
- Test convention: the existing `test_host_runner.py` uses `pytest.warns(CapabilityNotSupported, match=...)`, **not** `warnings.catch_warnings(record=True)` as mentioned in AC#7. The AC's consistency test should use `pytest.warns()` to match the established pattern. `warnings.catch_warnings` is used only in production code (`cli/migrate.py:120`).
- `ClaudeCodeRunner.build_blocking_json()` silently drops `json_schema` via `_ = json_schema` (no warning emitted). When implementing `ClaudeCodeRunner.describe_capabilities()`, this may warrant a `json_schema` entry with `status="unsupported"` or `status="partial"` rather than treating all capabilities as `"full"`.

### Tests

- `scripts/tests/test_host_runner.py` — extend, or create `scripts/tests/test_capability_report.py`
- Consistency test using `warnings.catch_warnings(record=True)` around `CodexRunner.build_streaming(...)`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py` — add `TestOrchestrationConfig` class (follow `TestAutomationConfig` at line 280/304 pattern: `test_from_dict_with_defaults`, `test_from_dict_with_host_cli`) + extend `TestBRConfig` with `test_orchestration_property_from_file` [Agent 3 finding]
- `scripts/tests/test_config_schema.py` — add `test_orchestration_host_cli_in_schema()` in `TestConfigSchema`, following the `test_hooks_in_schema` pattern; assert `orchestration.host_cli` is a string with `enum` containing `"claude-code"` [Agent 2 / Agent 3 finding]
- `scripts/tests/conftest.py` — extend `sample_config` fixture (line 66) with an `"orchestration"` key so `TestBRConfig` tests cover the default `OrchestrationConfig` construction path [Agent 3 finding]
- `scripts/tests/test_action.py` — update: add `describe_capabilities()` stub to `FakeRunner` (line 25) returning a minimal `CapabilityReport` to prevent `AttributeError` on any code path that calls the new method [Agent 2 / Agent 3 finding — **may break without this**]
- `scripts/tests/test_feat1462_doc_wiring.py` — consider extending `TestApiMdWiring` to assert `CapabilityReport`, `CapabilityEntry`, `HookEntry`, and `describe_capabilities` are documented in `API.md` (currently no guard — new public surface goes unguarded without this) [Agent 2 finding]

### Documentation

- `docs/reference/HOST_COMPATIBILITY.md` — may reference the new types; sibling docs child of FEAT-1496 will update
- `docs/reference/API.md` — `little_loops.host_runner` section will pick up new symbols automatically if generated

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — `## Host Runner Layer` table row for `HostRunner (Protocol)` (line 565) currently lists only `detect()` + `build_*` methods; needs `describe_capabilities()` added [Agent 2 finding]

### Configuration

- `config-schema.json` — add `orchestration.host_cli` property (or document the gap explicitly)

## Impact

- **Priority**: P4 - Foundation work for a P4 parent (FEAT-1496); landing this first unblocks two sibling children but is not itself user-visible.
- **Effort**: Medium - Three new dataclasses, one Protocol method, four runner implementations, one helper, one schema change, tests across all of the above.
- **Risk**: Low - Additive only. New dataclasses, new Protocol method, new helper. No existing behavior changes; existing `HostCapabilities` flags and warning sites remain untouched and continue to be the source of truth that `describe_capabilities()` reads from.
- **Breaking Change**: No

## Related Key Documentation

- `docs/reference/HOST_COMPATIBILITY.md` — host capability matrix this work formalizes
- `docs/reference/API.md#little_loopshost_runner` — module reference that will gain the new symbols
- `.claude/CLAUDE.md` — "Host CLI Abstraction" section describing `resolve_host()` and `LL_HOST_CLI` resolution

## Session Log
- `/ll:ready-issue` - 2026-05-16T16:58:02 - `9ff9319a-c7c4-4bf0-98ef-c2eac9f0b3e9.jsonl`
- `/ll:confidence-check` - 2026-05-16T17:00:00Z - `8cad7c10-6e4d-4a47-b9d1-399aa50d373a.jsonl`
- `/ll:wire-issue` - 2026-05-16T16:51:40 - `6902f110-9a95-46f3-8783-05f9ce88a53a.jsonl`
- `/ll:refine-issue` - 2026-05-16T16:45:48 - `7c9ec8f0-9a81-4c17-b634-1ee2b2905955.jsonl`
- `/ll:format-issue` - 2026-05-16T15:15:04 - `51c3d43d-d40e-431c-b47f-33a47f801e9e.jsonl`
- `/ll:issue-size-review` - 2026-05-16T15:07:07Z - `b57cdb22-126d-4dc6-b12f-a5213e07e705.jsonl`

## Status

**Open** | Created: 2026-05-16 | Priority: P4

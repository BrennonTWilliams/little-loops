---
id: FEAT-1523
type: FEAT
priority: P4
status: open
captured_at: '2026-05-16T15:07:07Z'
discovered_date: 2026-05-16
discovered_by: issue-size-review
parent: FEAT-1496
labels:
- host-compat
- preflight
size: Medium
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
4. Add host-selection helper (a small function or method) that reads `orchestration.host_cli` from `BRConfig` and exports it as `LL_HOST_CLI` before `resolve_host()` is called. This can live in `doctor.py` or as a shared utility — but the logic belongs in this child so the CLI child can import it.
5. Update `scripts/little_loops/__init__.py`: add `CapabilityReport`, `CapabilityEntry`, `HookEntry` to imports and `__all__`.
6. Resolve `config-schema.json` gap for `orchestration.host_cli`.
7. Tests at `scripts/tests/test_host_runner.py` (or a new `test_cli_doctor_model.py`):
   - `TestCapabilityReport` — round-trip dataclass construction
   - `TestDescribeCapabilities` — one test per runner; assert each runner returns a `CapabilityReport`
   - Consistency test per AC#7 of parent
8. Run: `python -m pytest scripts/tests/test_host_runner.py -v && python -m mypy scripts/little_loops/ && ruff check scripts/`

## Files to Modify

- `scripts/little_loops/host_runner.py` — dataclasses, Protocol method, runner implementations
- `scripts/little_loops/__init__.py` — re-exports
- `config-schema.json` — `orchestration` key gap

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
- Anywhere `resolve_host()` is called — host-selection helper needs to run before these call sites (grep for `resolve_host(` to enumerate)

### Similar Patterns

- `CapabilityNotSupported` import + `__all__` entry at `scripts/little_loops/__init__.py:22-27, 68-71` — exact pattern to mirror for the new dataclasses
- Existing `@dataclass(frozen=True)` usage on `HostInvocation` (lines 82-99) and `HostCapabilities` (lines 66-80) — style template

### Tests

- `scripts/tests/test_host_runner.py` — extend, or create `scripts/tests/test_capability_report.py`
- Consistency test using `warnings.catch_warnings(record=True)` around `CodexRunner.build_streaming(...)`

### Documentation

- `docs/reference/HOST_COMPATIBILITY.md` — may reference the new types; sibling docs child of FEAT-1496 will update
- `docs/reference/API.md` — `little_loops.host_runner` section will pick up new symbols automatically if generated

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
- `/ll:format-issue` - 2026-05-16T15:15:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/51c3d43d-d40e-431c-b47f-33a47f801e9e.jsonl`
- `/ll:issue-size-review` - 2026-05-16T15:07:07Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b57cdb22-126d-4dc6-b12f-a5213e07e705.jsonl`

## Status

**Open** | Created: 2026-05-16 | Priority: P4

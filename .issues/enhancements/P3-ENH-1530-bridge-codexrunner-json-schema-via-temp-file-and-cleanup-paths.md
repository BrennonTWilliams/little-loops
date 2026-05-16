---
id: ENH-1530
title: "Bridge CodexRunner json_schema via temp-file and cleanup_paths"
type: ENH
priority: P3
status: open
captured_at: "2026-05-16T21:30:27Z"
discovered_date: "2026-05-16"
discovered_by: capture-issue
---

# ENH-1530: Bridge CodexRunner json_schema via temp-file and cleanup_paths

## Summary

`CodexRunner.build_blocking_json` currently warns and drops the `json_schema` parameter because Codex's `--output-schema` flag takes a file path rather than an inline dict. The `describe_capabilities` report marks this as `"partial"` but that label is misleading — the feature is effectively unsupported today. Wire the bridge: serialize the schema dict to a temp file, pass `--output-schema <path>`, and expose a `cleanup_paths` field on `HostInvocation` so callers can unlink the file after the subprocess completes.

## Current Behavior

When `json_schema` is passed to `CodexRunner.build_blocking_json`:
1. A `CapabilityNotSupported` warning is emitted
2. The schema is silently dropped
3. Codex runs without any output schema enforcement
4. `describe_capabilities` reports `json_schema` as `"partial"` — which is inaccurate since nothing is wired

## Expected Behavior

When `json_schema` is passed to `CodexRunner.build_blocking_json`:
1. The schema dict is serialized to a temp file (e.g. via `tempfile.mktemp(suffix=".json", prefix="ll-schema-")`)
2. `--output-schema <path>` is appended to the Codex args
3. The temp file path is returned in `HostInvocation.cleanup_paths` for caller-managed cleanup
4. No `CapabilityNotSupported` warning is emitted (the capability works)
5. `describe_capabilities` reports `json_schema` as `"partial"` with note `"file-mediated: schema written to temp file, caller must unlink cleanup_paths"`

## Motivation

The current state has two problems: schema enforcement is silently lost on Codex (correctness risk for callers that depend on structured output), and `describe_capabilities` misrepresents the status as `"partial"` when the feature does nothing. Implementing the bridge makes `"partial"` honest and enables schema enforcement on Codex at the cost of a small lifecycle contract. Callers already handle subprocess results — adding `for p in invocation.cleanup_paths: p.unlink(missing_ok=True)` is low friction.

## Proposed Solution

### 1. Add `cleanup_paths` to `HostInvocation`

```python
@dataclass(frozen=True)
class HostInvocation:
    binary: str
    args: list[str]
    env: dict[str, str] = field(default_factory=dict)
    capabilities: HostCapabilities = field(default_factory=HostCapabilities)
    cleanup_paths: tuple[Path, ...] = field(default_factory=tuple)
```

### 2. Wire temp-file bridge in `CodexRunner.build_blocking_json`

```python
import json, tempfile

if json_schema is not None:
    schema_file = Path(tempfile.mktemp(suffix=".json", prefix="ll-schema-"))
    schema_file.write_text(json.dumps(json_schema))
    args += ["--output-schema", str(schema_file)]
    cleanup = (schema_file,)
else:
    cleanup = ()

return HostInvocation(
    binary="codex",
    args=args,
    env={},
    capabilities=self.capabilities,
    cleanup_paths=cleanup,
)
```

### 3. Update `describe_capabilities`

Change the `json_schema` entry note to reflect the file-mediated partial support:

```python
CapabilityEntry(
    "json_schema",
    "partial",
    "codex --output-schema requires a file path; schema is written to a "
    "temp file and path returned in HostInvocation.cleanup_paths for caller cleanup",
),
```

### 4. `ClaudeCodeRunner` — no change needed

`ClaudeCodeRunner.build_blocking_json` already silently drops `json_schema` (the claude CLI has no schema flag). `cleanup_paths` defaults to `()` via the new field default. Mark it `"unsupported"` in `describe_capabilities` (it already is).

## API/Interface

```python
# New field on HostInvocation (backwards-compatible; defaults to empty tuple)
cleanup_paths: tuple[Path, ...] = field(default_factory=tuple)

# Caller contract (any subprocess site that may receive a schema-bearing invocation)
inv = runner.build_blocking_json(prompt=..., json_schema=my_schema)
result = subprocess.run([inv.binary, *inv.args], ...)
for p in inv.cleanup_paths:
    p.unlink(missing_ok=True)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — `HostInvocation` dataclass, `CodexRunner.build_blocking_json`, `CodexRunner.describe_capabilities`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py` — `ll-action` uses `build_blocking_json`; add cleanup after subprocess
- Any other callers of `build_blocking_json` — grep for `build_blocking_json` to find all sites

### Similar Patterns
- `ClaudeCodeRunner.build_blocking_json` — silently drops `json_schema`; add `cleanup_paths=()` implicitly via default

### Tests
- `scripts/tests/test_host_runner.py` — add test: `CodexRunner.build_blocking_json(json_schema={...})` writes temp file, includes `--output-schema`, returns non-empty `cleanup_paths`
- Add test: `cleanup_paths` file exists before subprocess, `unlink` removes it
- Add test: no `json_schema` → `cleanup_paths` is empty tuple

### Documentation
- `docs/reference/API.md` — document `cleanup_paths` field on `HostInvocation`
- `docs/reference/HOST_COMPATIBILITY.md` — update Codex `json_schema` row to `partial (file-mediated)`

### Configuration
- N/A

## Implementation Steps

1. Add `cleanup_paths: tuple[Path, ...] = field(default_factory=tuple)` to `HostInvocation`
2. Wire temp-file bridge in `CodexRunner.build_blocking_json` (write + `--output-schema`)
3. Update `CodexRunner.describe_capabilities` note for `json_schema`
4. Find all `build_blocking_json` call sites; add `cleanup_paths` unlink after subprocess
5. Add/update tests in `test_host_runner.py`
6. Update API and HOST_COMPATIBILITY docs

## Scope Boundaries

- **In scope**: `CodexRunner.build_blocking_json` temp-file bridge, `HostInvocation.cleanup_paths` field, `describe_capabilities` note update for `json_schema`
- **Out of scope**: `ClaudeCodeRunner` changes — it already silently drops `json_schema`; `cleanup_paths` defaults to `()` via the new field default
- **Out of scope**: Automatic temp-file cleanup — callers own the lifecycle via `cleanup_paths` (by design, consistent with how subprocess results are managed)
- **Out of scope**: Other build methods (`build_streaming`, `build_detached`) — `json_schema` is only meaningful for blocking JSON calls

## Impact

- **Priority**: P3 - Makes `"partial"` label honest and enables real schema enforcement on Codex
- **Effort**: Small - ~50 lines of code across 2 files + tests
- **Risk**: Low - additive change; `cleanup_paths` defaults to `()` so existing callers are unaffected
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `codex`, `host-runner`, `captured`

## Status

**Open** | Created: 2026-05-16 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-05-16T21:32:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2328f3b-20de-411f-87c0-2b4355026da6.jsonl`
- `/ll:capture-issue` - 2026-05-16T21:30:27Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d524271d-ad54-4d19-976b-1c1d9e8d5463.jsonl`

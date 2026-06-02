---
id: ENH-1530
title: Bridge CodexRunner json_schema via temp-file and cleanup_paths
type: ENH
priority: P3
status: done
captured_at: '2026-05-16T21:30:27Z'
completed_at: '2026-05-16T22:40:49Z'
discovered_date: '2026-05-16'
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

_Actual production call sites of `build_blocking_json` (neither passes `json_schema`, so no cleanup integration is needed at these sites):_

- `scripts/little_loops/fsm/evaluators.py:609` — `evaluate_with_llm()` calls `resolve_host().build_blocking_json(prompt=..., model=...)` without `json_schema`; it already appends `--json-schema` and `--no-session-persistence` to `invocation.args` post-construction as a Claude-specific workaround — unaffected by ENH-1530
- `scripts/little_loops/parallel/worker_pool.py:576` — `_detect_active_model()` calls with prompt-only probe, no `json_schema` — unaffected

_Note: `scripts/little_loops/cli/action.py` uses `build_version_check`, not `build_blocking_json`. The ll-action JSON invocation (`cmd_capabilities`) goes through `run_claude_command` / `subprocess_utils`, not directly via `build_blocking_json`._

### Similar Patterns
- `ClaudeCodeRunner.build_blocking_json` — silently drops `json_schema`; add `cleanup_paths=()` implicitly via default

### Tests
- `scripts/tests/test_host_runner.py:251` — **Replace** `test_build_blocking_json_emits_warning_for_json_schema` (currently asserts the `CapabilityNotSupported` warning is emitted — this test must be deleted, not supplemented, since the warning is being removed)
- Add test: `CodexRunner.build_blocking_json(json_schema={...})` writes temp file, includes `--output-schema <path>`, returns `cleanup_paths` with that path
- Add test: `cleanup_paths` file exists before subprocess, `Path.unlink(missing_ok=True)` removes it
- Add test: no `json_schema` → `cleanup_paths` is empty tuple
- `scripts/tests/test_action.py:25` — `FakeRunner.build_blocking_json` returns `HostInvocation(binary="claude", args=[])` with no `cleanup_paths`; this still works since `cleanup_paths` defaults to `()`

_Wiring pass added by `/ll:wire-issue`:_
- Add test: `TestHostInvocation.test_cleanup_paths_defaults_to_empty_tuple` — explicit assertion `HostInvocation(binary="x", args=[]).cleanup_paths == ()` to pin the default [Agent 3 finding]
- `scripts/tests/test_host_runner.py:415` — `TestHostInvocation.test_default_env_and_capabilities` — update to also assert `invocation.cleanup_paths == ()` alongside the existing `env` and `capabilities` assertions [Agent 3 finding]
- `scripts/tests/test_host_runner.py:493` — `TestDescribeCapabilities.test_codex_runner_agent_select_unsupported` — asserts `by_name["json_schema"].status == "partial"`; the status stays `"partial"` after ENH-1530 so the assertion should still pass, but verify the note-string is not also asserted (if it is, update to the new file-mediated note) [Agent 3 finding]
- `scripts/tests/test_subprocess_utils.py:1898,1945` — `TestRunClaudeCommandHostRunner.test_delegates_to_resolve_host` and `.test_invocation_env_overrides_os_environ` — construct `HostInvocation(binary=..., args=..., env=...)` without `cleanup_paths`; **safe** because `default_factory=tuple` provides the default; no changes needed but confirms the default is load-bearing for the entire test suite [Agent 1 + 3 finding]

### Documentation
- `docs/reference/API.md` — document `cleanup_paths` field on `HostInvocation`
- `docs/reference/HOST_COMPATIBILITY.md` — update Codex `json_schema` row to `partial (file-mediated)`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — line 566 describes `HostInvocation` as "Value object holding `binary`, `args`, `env`, and `capabilities`"; add `cleanup_paths` to the field enumeration [Agent 2 finding]
- `docs/codex/usage.md` — `### json_schema inline dict (tool schemas)` section (lines 91–93) states schema values "are not supported and will cause the tool invocation to be skipped"; update to describe file-mediated partial support — but preserve the `CapabilityNotSupported` string in the file because `test_enh1495_doc_wiring.py::TestCodexUsageDocWiring.test_mentions_capability_not_supported` asserts it appears (the `--agent` and `tools` paragraphs keep the reference, so leave them intact) [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `HostInvocation` is declared `@dataclass(frozen=True)` at `host_runner.py:87` with 4 fields: `binary`, `args` (`list[str]`), `env` (`dict`, `default_factory=dict`), `capabilities` (`default_factory=HostCapabilities`). No `cleanup_paths` field yet.
- The proposed `default_factory=tuple` is intentionally different from the codebase's universal `default_factory=list` pattern — `tuple` is appropriate here because `HostInvocation` is `frozen=True` and tuple communicates immutability. Call sites that need to modify args already do `list(invocation.args) + [...]` (see `evaluators.py:609`).
- Caller contract confirmed: all `HostInvocation` consumers access `.binary` and `.args` directly before passing to `subprocess.run` or `subprocess.Popen` — no framework intermediary. Callers adding `cleanup_paths.unlink()` is consistent with the existing manual lifecycle pattern.
- `Path.unlink(missing_ok=True)` is the established cleanup idiom throughout the codebase (e.g., `subprocess_utils.py:read_sentinel()`, `transport.py`).

## Implementation Steps

1. Add `cleanup_paths: tuple[Path, ...] = field(default_factory=tuple)` to `HostInvocation` in `host_runner.py:87`
2. Wire temp-file bridge in `CodexRunner.build_blocking_json` (`host_runner.py`): write schema to `tempfile.mktemp(suffix=".json", prefix="ll-schema-")`, append `["--output-schema", str(schema_file)]` to `args`, return `cleanup_paths=(schema_file,)`
3. Remove the `warnings.warn(CapabilityNotSupported, ...)` call from `CodexRunner.build_blocking_json`
4. Update `CodexRunner.describe_capabilities` note for `json_schema` to reflect file-mediated partial support
5. **No call-site cleanup needed**: neither production `build_blocking_json` caller (`evaluators.py:609`, `worker_pool.py:576`) passes `json_schema`, so `cleanup_paths` will always be `()` at these sites
6. **Replace** (not supplement) `test_build_blocking_json_emits_warning_for_json_schema` at `test_host_runner.py:251` with new tests: temp file creation, `--output-schema` flag, `cleanup_paths` populated, no warning emitted, empty tuple when no schema
7. Update `docs/reference/API.md` to document `cleanup_paths` field on `HostInvocation`
8. Update `docs/reference/HOST_COMPATIBILITY.md` Codex `json_schema` row to `partial (file-mediated)`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `docs/ARCHITECTURE.md` line 566 — add `cleanup_paths` to the `HostInvocation` field enumeration ("binary, args, env, capabilities, **cleanup_paths**")
10. Update `docs/codex/usage.md` `### json_schema inline dict (tool schemas)` section — replace "not supported and will cause the tool invocation to be skipped" with description of file-mediated partial support; **keep** `CapabilityNotSupported` string present elsewhere in the file (the `--agent` / `tools` paragraphs) so `test_enh1495_doc_wiring.py` does not break
11. Add `TestHostInvocation.test_cleanup_paths_defaults_to_empty_tuple` in `test_host_runner.py` — assert `HostInvocation(binary="x", args=[]).cleanup_paths == ()`
12. Update `TestHostInvocation.test_default_env_and_capabilities` (line 415) — add `assert invocation.cleanup_paths == ()` assertion alongside existing `env` and `capabilities` checks

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
- `/ll:manage-issue` - 2026-05-16T22:40:49Z - `fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-05-16T22:37:11 - `8f7c32cd-a1de-4bf0-9e18-d5dccb439fe6.jsonl`
- `/ll:confidence-check` - 2026-05-16T22:45:00Z - `3de3022c-b670-4415-8576-75b1c573b639.jsonl`
- `/ll:wire-issue` - 2026-05-16T22:33:12 - `91e24fe2-0232-45d3-9311-02722818c1a7.jsonl`
- `/ll:refine-issue` - 2026-05-16T22:27:12 - `8aefa41b-9dfe-4400-b466-d830ce9ac219.jsonl`
- `/ll:format-issue` - 2026-05-16T21:32:49 - `b2328f3b-20de-411f-87c0-2b4355026da6.jsonl`
- `/ll:capture-issue` - 2026-05-16T21:30:27Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d524271d-ad54-4d19-976b-1c1d9e8d5463.jsonl`

---
id: FEAT-1496
type: FEAT
priority: P4
status: done
captured_at: '2026-05-16T13:04:12Z'
discovered_date: 2026-05-16
discovered_by: capture-issue
parent: EPIC-1463
blocked_by:
- FEAT-1493
labels:
- captured
- codex
- host-compat
- preflight
- ux
confidence_score: 90
outcome_confidence: 63
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
implementation_order_risk: true
size: Very Large
---

# FEAT-1496: Host-capability preflight check (`ll-doctor`)

## Summary

Add a preflight/diagnostic command — tentatively `ll-doctor` — that probes the currently selected host CLI (`LL_HOST_CLI` or `orchestration.host_cli`) and reports which ll capabilities will work, which will degrade silently, and which will outright fail. Today, `CapabilityNotSupported` warnings only fire mid-orchestration when a feature is invoked (`scripts/little_loops/host_runner.py:319,326`), surfacing too late.

## Current Behavior

`CodexRunner.build_streaming` emits `CapabilityNotSupported` to stderr when callers pass `agent=` or `tools=`, but only at the moment the invocation runs. A user kicking off a long `ll-parallel` run discovers degraded behavior 20 minutes in. There is no upfront `ll <something> --check` that says "here's what your host can and cannot do."

## Expected Behavior

Running `ll-doctor` (or `ll <subcommand> --preflight`) prints a table per active host:

```
Host: codex (resolved from LL_HOST_CLI)
Binary: /opt/homebrew/bin/codex  (version 0.5.x)

✓ build_streaming                        full
✓ build_blocking_json                    NDJSON only — `json_schema` unsupported
✓ build_detached                         full
✓ build_version_check                    full
✗ --agent (persona selection)            CapabilityNotSupported — silently dropped
✗ --tools (tool allowlist)               CapabilityNotSupported — sandbox modes only
✓ Hook: session_start                    installed
✓ Hook: pre_compact                      installed
✓ Hook: user_prompt_submit               installed
✓ Hook: post_tool_use                    installed (fire-and-forget, 5s)
○ Hook: pre_tool_use                     handler registered, NOT wired (opt-in)
○ Hook: stop                             deferred (no consumer)
```

Plus exit code 0 if everything required for the configured workflows is present; 1 if a critical capability is missing.

## Use Case

**Who**: A developer using little-loops with a non-default host CLI (e.g., Codex, OpenCode)

**Context**: Before starting a long `ll-parallel` or `ll-sprint` run, they want upfront confirmation that the configured host supports all features those workflows depend on.

**Goal**: Run `ll-doctor` to get an immediate, accurate report of which capabilities are supported, degraded, or unavailable — without waiting for a mid-run failure.

**Outcome**: Either proceed with confidence (all required capabilities present, exit 0), or learn which specific gaps exist before committing time to a long run.

## Acceptance Criteria

- [ ] `ll-doctor` resolves the active host via `LL_HOST_CLI` env var or `orchestration.host_cli` in `ll-config.json`
- [ ] Output includes host binary name and resolved version
- [ ] Each invocation-mode capability (`build_streaming`, `build_blocking_json`, `build_detached`, `build_version_check`, agent selection, tool allowlist) is reported with status (✓ full / partial / ✗ unsupported) and a short description
- [ ] Hook installation status is reported per hook intent (installed / registered-not-wired / deferred)
- [ ] Exit code 0 when all capabilities required for configured workflows are present
- [ ] Exit code 1 when any critical capability is missing
- [ ] `describe_capabilities()` output is consistent with `CapabilityNotSupported` warnings emitted by each runner

## Motivation

The Codex audit identified that several capability gaps degrade silently. Surfacing them upfront via a single command:

1. Saves users from discovering gaps mid-run (long `ll-parallel` or `ll-sprint` invocations)
2. Provides a single command for issue reports ("what does `ll-doctor` say?")
3. Documents host parity in a runnable form — the table stays in sync with the actual `HostRunner` implementations, unlike `HOST_COMPATIBILITY.md` which can drift

## Proposed Solution

1. Add a `CapabilityReport` dataclass alongside `HostInvocation` in `scripts/little_loops/host_runner.py`
2. Each `HostRunner` (`ClaudeCodeRunner`, `CodexRunner`, `OpenCodeRunner`, `PiRunner`) implements `describe_capabilities() -> CapabilityReport` enumerating supported features
3. New CLI tool `ll-doctor` (`scripts/little_loops/cli/doctor.py`) prints the report for the resolved host, plus hook-installation status (read from the host adapter's expected install path)
4. Hook discovery: walk the resolved host's adapter dir (`hooks/adapters/<host>/`) and check whether each shim is referenced in the host's installed `hooks.json`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`HostCapabilities` already exists** at `scripts/little_loops/host_runner.py:66-80` (frozen dataclass with `streaming`, `permission_skip`, `agent_select`, `tool_allowlist` bools). Each runner sets a class-level `capabilities: HostCapabilities` instance — `CodexRunner.capabilities` at lines 300-305 already encodes `agent_select=False, tool_allowlist=False`. The new `CapabilityReport` should **build on** this (wrap it with human-readable notes + version + binary), not duplicate it.
- **`HostRunner` is a `typing.Protocol`** (lines 102-155), not an ABC. Adding `describe_capabilities()` means: declare in the Protocol, implement on all four concrete classes (`ClaudeCodeRunner`, `CodexRunner`, `OpenCodeRunner`, `PiRunner`).
- **Existing precedent: `ll-action capabilities`** subcommand at `scripts/little_loops/cli/action.py:140` (`cmd_capabilities()`) already resolves the host via `resolve_host()`, calls `build_version_check()`, runs the binary, and emits JSON. `ll-doctor` should extend this pattern (human-readable table + exit code) — and the `ll-action capabilities` JSON shape should be updated in lockstep to surface the new `CapabilityReport` so both tools share one source of truth.
- **`resolve_host()` currently only reads env vars** (`LL_HOST_CLI`, `LL_HOOK_HOST`) at lines 562-606. It does **not** read `orchestration.host_cli` from `.ll/ll-config.json` directly; that lookup is upstream. Acceptance criterion #1 ("resolves the active host via `LL_HOST_CLI` env var or `orchestration.host_cli` in `ll-config.json`") implies `ll-doctor` must perform the config-key lookup itself before calling `resolve_host()` (or factor that lookup into a shared helper).
- **Hook wiring asymmetry**: `hooks/hooks.json` is Claude Code-specific. Codex has its own `hooks/adapters/codex/hooks.json`. OpenCode uses a TypeScript plugin (`hooks/adapters/opencode/index.ts`) with no JSON manifest. The "Hook: ✓/✗" rows in the Expected Behavior table need per-host detection logic — there is no single `installed-hooks.json` to read.
- **`OpenCodeRunner` / `PiRunner` raise `HostNotConfigured`** (not `CapabilityNotSupported`). `ll-doctor` should treat "host binary absent" as a separate report state from "host present but lacks capability X."

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — add `CapabilityReport` + `describe_capabilities()` on each runner
- `scripts/pyproject.toml` — register `ll-doctor` entry point

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` — increment CLI tool count strings: `"23 typed CLI tools"` (line 46) and `"24 CLI tools"` (line 164) [Agent 2 finding]
- `commands/help.md` — `CLI TOOLS` block lists every `ll-` tool; add `ll-doctor` entry [Agent 2 finding]
- `skills/configure/areas.md` — `"Authorize all 21"` enumeration string must become `"Authorize all 22"` with `ll-doctor` added to the list [Agent 2 finding]
- `skills/init/SKILL.md` — bash permissions block and CLAUDE.md boilerplate blocks enumerate CLI tools; add `"Bash(ll-doctor:*)"` [Agent 2 finding]
- `docs/reference/CLI.md` — add `### ll-doctor` section (follow the `### ll-action` model) [Agent 2 finding]
- `docs/reference/API.md` — `## little_loops.host_runner` section documents Protocol method table and `__all__` list; add `describe_capabilities()`, `CapabilityReport`, `CapabilityEntry`, `HookEntry` [Agent 2 finding]
- `docs/ARCHITECTURE.md` — `## Host CLI Abstraction` symbol table lists `HostCapabilities`, `resolve_host()`, `CapabilityNotSupported`; add new dataclasses [Agent 2 finding]

### Files to Create
- `scripts/little_loops/cli/doctor.py` — the CLI tool

### Dependent Files (Callers/Importers)
- `.claude/CLAUDE.md` — document `ll-doctor` in CLI Tools section
- `docs/reference/HOST_COMPATIBILITY.md` — cross-link

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/__init__.py` — re-exports `HostRunner`, `CapabilityNotSupported`, `HostInvocation`, `HostNotConfigured` from `host_runner.py`; new dataclasses `CapabilityReport`, `CapabilityEntry`, `HookEntry` must be added to `__all__` here (and imported) or they won't be accessible from the package root [Agent 1 finding]

### Tests
- `scripts/tests/test_cli_doctor.py` — verify report shape for each host (naming follows `test_cli_<name>.py` convention seen in `scripts/tests/test_cli_docs.py`)
- Verify report matches the actual `CapabilityNotSupported` warnings emitted by runner methods

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_action.py` — **will break** when `cmd_capabilities()` is updated to emit full `CapabilityReport`: (a) `FakeRunner` (lines 25–48) lacks `describe_capabilities()` and will raise `AttributeError`; (b) `TestCmdCapabilities` (lines 308–398) asserts on the current `{available, version, supported_skills}` flat shape which will change; (c) `TestMainAction.test_capabilities_subcommand_dispatch` (line ~452) also uses `FakeRunner` — update all three in the same pass as `action.py` changes [Agent 3 finding]
- `scripts/tests/test_create_extension_wiring.py` — `TestFeat1229LlActionWiring.test_configure_areas_count_is_17` asserts `"Authorize all 21"` and a separate assertion checks `"23 typed CLI tools"` — both strings must be updated when `ll-doctor` is added to the count-tracked files [Agent 2 finding]
- `scripts/tests/test_feat1462_doc_wiring.py` — `TestApiMdWiring` asserts presence of existing symbols in `API.md`, `ARCHITECTURE.md`, `HOST_COMPATIBILITY.md`; verify new symbols (`CapabilityReport`, `describe_capabilities`) are covered or add assertions [Agent 2 finding]

### Similar Patterns
- Other CLI entry points in `scripts/little_loops/cli/` — follow the same module/entry-point pattern (e.g., `ll-logs`, `ll-issues`)

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — **gap**: the `orchestration` top-level key is absent (schema uses `additionalProperties: false`). Acceptance Criterion #1 requires `ll-doctor` to resolve `orchestration.host_cli` from `ll-config.json`, but writing that key currently fails schema validation. Either add the `orchestration` object to the schema, or document that `ll-doctor` reads it via `BRConfig` before schema validation (and add `hooks.host` enum cross-reference as the closest existing analog) [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Concrete file:line anchors for the work:**

| Surface | Location | Notes |
|---------|----------|-------|
| `HostCapabilities` dataclass | `scripts/little_loops/host_runner.py:66-80` | Extend, do not duplicate |
| `HostInvocation` dataclass | `scripts/little_loops/host_runner.py:82-99` | Style template (`frozen=True`) for `CapabilityReport` |
| `HostRunner` Protocol | `scripts/little_loops/host_runner.py:102-155` | Add `describe_capabilities()` here |
| `ClaudeCodeRunner` | `scripts/little_loops/host_runner.py` (after line 155) | Reports all-✓ |
| `CodexRunner.capabilities` | `scripts/little_loops/host_runner.py:300-305` | Source of truth for ✗ rows |
| Warning sites (Codex) | `host_runner.py:319-325` (agent), `326-333` (tools), `372-380` (json_schema) | Test that report matches these warnings |
| `OpenCodeRunner`, `PiRunner` | `scripts/little_loops/host_runner.py` | Raise `HostNotConfigured` — separate report state |
| `_HOST_RUNNER_REGISTRY` | `scripts/little_loops/host_runner.py:538-543` | Iterate for `--all-hosts` flag if added |
| `_PROBE_ORDER` | `scripts/little_loops/host_runner.py:547-551` | Note: `opencode` absent — only env-selectable |
| `resolve_host()` | `scripts/little_loops/host_runner.py:562-606` | Does NOT read `orchestration.host_cli` — see Proposed Solution finding #4 |

**Entry-point registration (two-file pattern):**
1. `scripts/pyproject.toml:48-74` — add `ll-doctor = "little_loops.cli:main_doctor"` to `[project.scripts]`
2. `scripts/little_loops/cli/__init__.py:29-84` — `from little_loops.cli.doctor import main_doctor` plus add to `__all__` and the module-level docstring tool listing

**Pre-existing tool to extend in lockstep:**
- `scripts/little_loops/cli/action.py:140` — `cmd_capabilities()` already JSON-emits a minimal `{available, version, supported_skills}` shape. After `CapabilityReport` lands, update this to surface the full report so `ll-action capabilities --json` and `ll-doctor` share the same data source.

**Hook wiring inputs (no single manifest exists):**
- Claude Code: `hooks/hooks.json` (root)
- Codex: `hooks/adapters/codex/hooks.json`
- OpenCode: `hooks/adapters/opencode/index.ts` (TypeScript plugin — no JSON to parse; check for the file's existence + listed hook intents)

**Test pattern to follow** (`scripts/tests/test_cli_docs.py`):
- `class TestMainDoctor:` with one method per behavior
- `with patch("sys.argv", ["ll-doctor"]), patch("little_loops.host_runner.resolve_host", ...), patch("builtins.print"):` then `assert main_doctor() == 0`
- Argparse failure tests: `pytest.raises(SystemExit)` asserting `exc_info.value.code == 2`

## API/Interface

```python
@dataclass
class CapabilityEntry:
    name: str
    status: Literal["full", "partial", "unsupported"]
    note: str

@dataclass
class CapabilityReport:
    host: str
    binary: str
    version: str
    capabilities: list[CapabilityEntry]
    hooks: list[HookEntry]

class HostRunner:
    def describe_capabilities(self) -> CapabilityReport: ...
```

```bash
# CLI
ll-doctor [--host <host>]
# Exit 0: all critical capabilities present
# Exit 1: critical capability missing
```

## Implementation Steps

1. **Define dataclasses** in `scripts/little_loops/host_runner.py` (alongside `HostInvocation` at lines 82-99, using `@dataclass(frozen=True)` and `field(default_factory=...)` per house convention):
   - `CapabilityEntry(name, status: Literal["full","partial","unsupported"], note)`
   - `HookEntry(name, status: Literal["installed","registered","deferred","absent"], note)`
   - `CapabilityReport(host, binary, version, capabilities: list[CapabilityEntry], hooks: list[HookEntry])`
2. **Add `describe_capabilities()` to the `HostRunner` Protocol** at `host_runner.py:102-155`, then implement on all four concrete runners. Source the ✓/✗ values from each runner's existing class-level `capabilities: HostCapabilities` (no new state needed — `CodexRunner.capabilities` already encodes the right values at lines 300-305).
3. **Add a host-selection helper** that reads `orchestration.host_cli` from `.ll/ll-config.json` and sets `LL_HOST_CLI` before calling `resolve_host()` (Acceptance Criterion #1 requires this, but `resolve_host()` at lines 562-606 currently only consults env vars).
4. **Author `scripts/little_loops/cli/doctor.py`** following the `cli/docs.py:main_verify_docs()` template:
   - `from __future__ import annotations`
   - `argparse.ArgumentParser` with `RawDescriptionHelpFormatter` and an epilog containing `Examples:` + `Exit codes:` blocks
   - `configure_output()` + `Logger(use_color=use_color_enabled())` right after `parse_args()`
   - Print the ✓/✗ table inline with `print()` using the literal characters (mirror `doc_counts.py:format_result_text()` at line 172)
   - Return `0` if no critical gaps; `1` otherwise
5. **Register the entry point in both places**:
   - `scripts/pyproject.toml` `[project.scripts]` (lines 48-74): `ll-doctor = "little_loops.cli:main_doctor"`
   - `scripts/little_loops/cli/__init__.py` (lines 29-84): import + `__all__` + module-docstring tool listing
6. **Tests at `scripts/tests/test_cli_doctor.py`** following `test_cli_docs.py` pattern:
   - One `TestMainDoctor` class
   - `patch("sys.argv", ...)` + `patch("little_loops.host_runner.resolve_host", ...)` + `patch("builtins.print")`
   - Assert exit code 0 when host has all capabilities; exit code 1 when `CodexRunner` is the selected host (it's missing `agent_select` / `tool_allowlist`)
   - Add a consistency test: invoke `CodexRunner.build_streaming(agent=..., tools=...)` under `warnings.catch_warnings(record=True)` and assert every emitted `CapabilityNotSupported` corresponds to an `unsupported` entry in its `describe_capabilities()` output (Acceptance Criterion #7)
7. **Update `ll-action capabilities`** (`scripts/little_loops/cli/action.py:140`) to emit the full `CapabilityReport` shape in JSON form, so `ll-doctor` (table view) and `ll-action capabilities` (machine view) share one source of truth.
8. **Documentation**:
   - Append `ll-doctor` row to `.claude/CLAUDE.md` CLI Tools section
   - Cross-link in `docs/reference/HOST_COMPATIBILITY.md` (the doc this command keeps honest)
9. **Run checks**: `python -m pytest scripts/tests/test_cli_doctor.py scripts/tests/test_host_runner.py -v && ruff check scripts/ && python -m mypy scripts/little_loops/`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `scripts/little_loops/__init__.py` — add `CapabilityReport`, `CapabilityEntry`, `HookEntry` to the import block and `__all__` list (mirror the existing `CapabilityNotSupported` entry at lines 22–27 and 68–71)
11. Update `scripts/tests/test_action.py` — (a) add `describe_capabilities()` stub to `FakeRunner` (lines 25–48), (b) update `TestCmdCapabilities` assertions to match the new `CapabilityReport` JSON shape emitted by `cmd_capabilities()`, (c) update `TestMainAction.test_capabilities_subcommand_dispatch` accordingly — do this in the same commit as step 7 (action.py update) to avoid a broken-tests window
12. Update `scripts/tests/test_create_extension_wiring.py` — increment the `"Authorize all 21"` → `"Authorize all 22"` assertion and the `"23 typed CLI tools"` assertion after step 8 registration files are updated
13. Verify or extend `scripts/tests/test_feat1462_doc_wiring.py` — check that `TestApiMdWiring` covers `CapabilityReport` and `describe_capabilities` once `API.md` and `ARCHITECTURE.md` are updated in step 8
14. Resolve `config-schema.json` gap — add an `orchestration` object definition with `host_cli` string property before implementing AC#1 in `doctor.py`; or explicitly document in implementation that config-key lookup bypasses schema validation via raw `BRConfig` read

## Impact

- **Priority**: P4 — UX improvement, not blocking
- **Effort**: Medium — touches all four host runners and adds a new CLI
- **Risk**: Low — Read-only diagnostic
- **Breaking Change**: No

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/HOST_COMPATIBILITY.md` | Current source of capability info; `ll-doctor` complements it |
| `.claude/CLAUDE.md` | Documents host CLI abstraction and `resolve_host()` |


## Blocks

- ENH-1495

## Labels

`feat`, `captured`, `codex`, `host-compat`, `preflight`, `ux`

## Status

**Open** | Created: 2026-05-16 | Priority: P4

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-16_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- Broad file surface with 20+ distinct change sites (Breadth 0/12) — most are mechanical doc/wiring edits; use the Integration Map steps 1–14 as a literal checklist to avoid missing a site.
- Tests are co-deliverables: `test_cli_doctor.py` doesn't exist yet; implement tests in the same pass as `doctor.py` to avoid a broken-tests window.
- `config-schema.json` strategy (step 14) is an open "either/or" — resolve before starting so AC#1 implementation in `doctor.py` is unambiguous.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-16
- **Reason**: Issue too large for single session (score 11/11 — Very Large; 14 implementation steps across 5 subsystems)

### Decomposed Into
- FEAT-1523: ll-doctor — core data model, Protocol, and host-selection helper
- FEAT-1503: ll-doctor — CLI tool and ll-action capabilities update (depends on FEAT-1523)
- FEAT-1504: ll-doctor — documentation and wiring touchpoints (depends on FEAT-1523; can run parallel with FEAT-1503)

## Session Log
- `/ll:issue-size-review` - 2026-05-16T15:07:07Z - `b57cdb22-126d-4dc6-b12f-a5213e07e705.jsonl`
- `/ll:confidence-check` - 2026-05-16T15:30:00Z - `d35fc42a-49a3-4b52-b62c-3cacbc47d225.jsonl`
- `/ll:wire-issue` - 2026-05-16T14:57:12 - `d35fc42a-49a3-4b52-b62c-3cacbc47d225.jsonl`
- `/ll:refine-issue` - 2026-05-16T14:51:31 - `50ccb0d9-66bf-480e-b5b2-089e3624949a.jsonl`
- `/ll:format-issue` - 2026-05-16T13:24:02 - `d64e8a75-a28c-4d9e-b390-8a3589494173.jsonl`
- `/ll:capture-issue` - 2026-05-16T13:04:12Z - `0f112cdc-ed18-410c-85e1-0d7cc45aa863.jsonl`

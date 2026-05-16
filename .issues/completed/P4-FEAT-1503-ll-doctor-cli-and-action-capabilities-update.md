---
id: FEAT-1503
type: FEAT
priority: P4
status: done
captured_at: '2026-05-16T15:07:07Z'
discovered_date: 2026-05-16
discovered_by: issue-size-review
parent: FEAT-1496
blocked_by:
- FEAT-1523
labels:
- host-compat
- preflight
size: Very Large
confidence_score: 80
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1503: ll-doctor — CLI tool and ll-action capabilities update

## Summary

Author the `ll-doctor` CLI entry point and update `ll-action capabilities` to emit the full `CapabilityReport` shape, so both the human-readable table and the machine-readable JSON share one source of truth.

## Parent Issue

Decomposed from FEAT-1496: Host-capability preflight check (`ll-doctor`)

## Scope

Covers implementation steps 4, 5, 6, 7, 11 from the parent issue.

**Depends on**: FEAT-1523 (data model and Protocol must land first)

## Current Behavior

- No `ll-doctor` CLI tool exists; users have no unified way to check which host capabilities are available before running automation.
- `ll-action capabilities` (`scripts/little_loops/cli/action.py:140` — `cmd_capabilities()`) emits only a minimal JSON shape: `{available, version, supported_skills}`. It does not surface invocation-mode capabilities, hook installation status, or per-feature gaps.
- Capability detection logic is fragmented across host runners and is not reflected in a single report consumable by both humans and tooling.

## Expected Behavior

- `ll-doctor` resolves the active host (via `LL_HOST_CLI` / `orchestration.host_cli`) and prints a ✓/✗/○ status table covering host binary, version, invocation modes, and per-hook installation status.
- Exit code is `0` when all required capabilities are present; `1` when any critical capability is missing.
- `ll-action capabilities --json` emits the full `CapabilityReport` dataclass serialized to JSON, identical in structure to what `ll-doctor` consumes — one data source, two presentations.

## Motivation

Multi-host support (Claude Code, Codex, OpenCode) means feature availability is no longer uniform. Without a preflight check, users discover capability gaps only when automation fails partway through. `ll-doctor` makes those gaps visible up front; sharing the report shape with `ll-action capabilities` lets downstream tooling (CI, FSM loops, dashboards) consume the same authoritative data without scraping human-readable output. This is a required deliverable of the parent FEAT-1496 host-compat preflight effort.

## Use Case

A developer working on a project configured for Codex runs `ll-doctor` before kicking off `ll-auto`. The table shows `agent_select: ✗ (not supported by Codex)` and `tool_allowlist: ✗`, with hook installation status `installed` for `session_start` but `deferred` for `pre_compact`. They learn — in one command — which automation features will silently degrade, and can either reconfigure or switch hosts before burning a long run.

## Proposed Solution

Add `scripts/little_loops/cli/doctor.py` implementing `main_doctor()`, modeled on `cli/docs.py:main_verify_docs()`. The function:

1. Parses args (no positional args; `--json` flag optional for machine output).
2. Calls the host-resolution helper from FEAT-1523 to get the active runner.
3. Calls `runner.describe_capabilities()` → `CapabilityReport`.
4. Prints a ✓/✗/○ table using literal Unicode (mirror `cli/doc_counts.py:format_result_text()`).
5. Returns `0` if no critical gaps, `1` otherwise.

In parallel, update `action.py:cmd_capabilities()` to serialize the full `CapabilityReport` dataclass (via `dataclasses.asdict()`) so `ll-action capabilities --json` and `ll-doctor` share the data source. Test updates land in the same pass to avoid a broken-tests window.

```python
# scripts/little_loops/cli/doctor.py (sketch)
def main_doctor(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    configure_output()
    log = Logger(use_color=use_color_enabled())
    runner = resolve_host_runner()
    report = runner.describe_capabilities()
    _print_report(report, json_mode=args.json)
    return 0 if not report.has_critical_gap() else 1
```

## Acceptance Criteria

- [ ] `scripts/little_loops/cli/doctor.py` exists and implements `main_doctor()`
- [ ] `ll-doctor` resolves the active host via `LL_HOST_CLI` / `orchestration.host_cli` using the helper from FEAT-1523
- [ ] Output includes host binary name and resolved version
- [ ] Each invocation-mode capability is printed with ✓/✗/○ status and a short description
- [ ] Hook installation status is reported per hook intent (installed / registered-not-wired / deferred)
- [ ] Exit code 0 when all required capabilities are present; 1 when any critical capability is missing
- [ ] `ll-doctor` registered as an entry point in `scripts/pyproject.toml` and `scripts/little_loops/cli/__init__.py`
- [ ] `ll-action capabilities` (action.py:140) emits the full `CapabilityReport` shape in JSON so both tools share one data source
- [ ] `scripts/tests/test_cli_doctor.py` exists with full coverage of doctor.py behaviors
- [ ] `scripts/tests/test_action.py` updated: `FakeRunner` gets `describe_capabilities()` stub; `TestCmdCapabilities` assertions updated for the new JSON shape; `TestMainAction.test_capabilities_subcommand_dispatch` updated accordingly

## API/Interface

```python
# New CLI entry point
def main_doctor(argv: list[str] | None = None) -> int: ...

# Updated JSON shape from `ll-action capabilities --json`
# Before: {"available": bool, "version": str, "supported_skills": [str, ...]}
# After:  full CapabilityReport (see FEAT-1523 dataclass), e.g.:
# {
#   "host": "claude-code",
#   "binary": "claude",
#   "version": "...",
#   "invocation_modes": [{"name": "agent_select", "supported": true, "description": "..."}, ...],
#   "hooks": [{"intent": "session_start", "status": "installed"}, ...],
#   "critical_gaps": []
# }
```

## Implementation Steps

1. **Author `scripts/little_loops/cli/doctor.py`** following `cli/docs.py:main_verify_docs()` template:
   - `from __future__ import annotations`
   - `argparse.ArgumentParser` with `RawDescriptionHelpFormatter`, epilog with `Examples:` and `Exit codes:` blocks
   - `configure_output()` + `Logger(use_color=use_color_enabled())` after `parse_args()`
   - Call the host-selection helper from FEAT-1523 to resolve the active host
   - Call `runner.describe_capabilities()` to get the `CapabilityReport`
   - Print the ✓/✗/○ table with `print()` using literal Unicode characters (mirror `doc_counts.py:format_result_text()` at line 172)
   - Return `0` if no critical gaps; `1` otherwise

2. **Register entry point in two places**:
   - `scripts/pyproject.toml` `[project.scripts]` (lines 48-74): add `ll-doctor = "little_loops.cli:main_doctor"`
   - `scripts/little_loops/cli/__init__.py` (lines 29-84): `from little_loops.cli.doctor import main_doctor` + add to `__all__` and module-docstring tool listing

3. **Update `scripts/little_loops/cli/action.py:140`** — `cmd_capabilities()` currently emits minimal `{available, version, supported_skills}` JSON; update to emit the full `CapabilityReport` dataclass serialized to JSON so `ll-action capabilities --json` and `ll-doctor` share one source of truth.

4. **Update `scripts/tests/test_action.py`** in the same pass as step 3 to avoid a broken-tests window:
   - Add `describe_capabilities()` stub to `FakeRunner` (lines 25-48)
   - Update `TestCmdCapabilities` assertions to match the new `CapabilityReport` JSON shape
   - Update `TestMainAction.test_capabilities_subcommand_dispatch` accordingly

5. **Write `scripts/tests/test_cli_doctor.py`** following `test_cli_docs.py` pattern:
   ```python
   class TestMainDoctor:
       def test_exit_zero_when_all_capabilities_present(self):
           with patch("sys.argv", ["ll-doctor"]), \
                patch("little_loops.host_runner.resolve_host", return_value=mock_claude_runner), \
                patch("builtins.print"):
               assert main_doctor() == 0

       def test_exit_one_when_critical_capability_missing(self):
           # Use CodexRunner (agent_select=False, tool_allowlist=False)
           ...

       def test_consistency_capability_not_supported_matches_report(self):
           # warnings.catch_warnings(record=True) → assert each CapabilityNotSupported
           # corresponds to unsupported entry in describe_capabilities()
           ...
   ```

6. **Update `docs/reference/CLI.md` `#### capabilities` JSON block** — reflect the new `CapabilityReport` shape (this is a FEAT-1503 change, not deferred to FEAT-1496, since it documents the `cmd_capabilities()` output changed in step 3).

7. Run: `python -m pytest scripts/tests/test_cli_doctor.py scripts/tests/test_action.py -v && ruff check scripts/ && python -m mypy scripts/little_loops/`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- In step 3, after updating `cmd_capabilities()`, immediately update `docs/reference/CLI.md` `#### capabilities` (lines 63–68) — do not leave the old JSON shape in the doc.
- Note: `test_create_extension_wiring.py` and `test_ll_logs_wiring.py` count assertions (`"23 typed CLI tools"`, `"Authorize all 21"`) will break during the FEAT-1496 doc pass — not a FEAT-1503 concern but flag for the implementer of FEAT-1496.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/action.py` — update `cmd_capabilities()` (line 140) to serialize full `CapabilityReport`
- `scripts/pyproject.toml` — add `ll-doctor` entry point in `[project.scripts]` (lines 48-74)
- `scripts/little_loops/cli/__init__.py` — import `main_doctor`, add to `__all__`, update module docstring tool listing (lines 29-84)
- `scripts/tests/test_action.py` — add `describe_capabilities()` stub to `FakeRunner` (lines 25-48); update `TestCmdCapabilities` (lines 308-398) and `TestMainAction.test_capabilities_subcommand_dispatch` (~line 452)

### Files to Create

- `scripts/little_loops/cli/doctor.py`
- `scripts/tests/test_cli_doctor.py`

### Dependent Files (Callers/Importers)

- Any consumer of `ll-action capabilities --json` output (CI/FSM loops) — grep for `ll-action capabilities` and `cmd_capabilities` references before changing the JSON shape

_Wiring pass added by `/ll:wire-issue`:_
- **Confirmed: zero runtime consumers** — full codebase grep found no callers of `ll-action capabilities` in `.loops/` FSM YAML files, `hooks/`, `skills/`, or `commands/`. The JSON shape change in `cmd_capabilities()` carries no downstream breakage risk beyond `test_action.py` assertions.

### Similar Patterns

- `scripts/little_loops/cli/docs.py:main_verify_docs()` — template for `main_doctor()` structure
- `scripts/little_loops/cli/doc_counts.py:format_result_text()` (line 172) — pattern for ✓/✗/○ Unicode table output

### Tests

- `scripts/tests/test_cli_doctor.py` — new, full coverage of `main_doctor()` (mirrors `test_cli_docs.py`)
- `scripts/tests/test_action.py` — updates for new `CapabilityReport` JSON shape

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension_wiring.py` — `TestFeat1229LlActionWiring.test_readme_tool_count_is_20` asserts `"23 typed CLI tools"` in README; `test_configure_areas_count_is_17` asserts `"Authorize all 21"` in `skills/configure/areas.md`. These will break when FEAT-1496 doc updates add `ll-doctor` to count surfaces — no action needed in FEAT-1503, but note the dependency.
- `scripts/tests/test_ll_logs_wiring.py` — `TestConfigureAreasWiring.test_authorize_all_count_is_17` asserts `"Authorize all 21"` in `skills/configure/areas.md`. Same dependency: breaks during FEAT-1496 doc pass, not FEAT-1503.

### Documentation

- N/A in this issue; documentation updates for the new CLI tool tracked separately in FEAT-1496 follow-up

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `#### capabilities` section (lines 63–68) contains a verbatim JSON code block showing the old `{available, version, supported_skills}` shape. This is a FEAT-1503 concern (not FEAT-1496) because it documents the `cmd_capabilities()` output being changed in this issue. Update the code block to reflect the new `CapabilityReport` shape in the same pass as step 3.

### Configuration

- N/A — uses existing `LL_HOST_CLI` env var and `orchestration.host_cli` config key

### Anchor References (from parent issue)

- `cmd_capabilities()` at `scripts/little_loops/cli/action.py:140` — existing JSON emitter to extend
- `pyproject.toml` entry points at lines 48-74
- `cli/__init__.py` imports/exports at lines 29-84
- `FakeRunner` at `scripts/tests/test_action.py:25-48`
- `TestCmdCapabilities` at test_action.py lines 308-398
- `TestMainAction.test_capabilities_subcommand_dispatch` at ~line 452 (confirmed lines 452-468)
- Hook wiring inputs: `hooks/hooks.json` (Claude Code), `hooks/adapters/codex/hooks.json` (Codex), `hooks/adapters/opencode/index.ts` (OpenCode — no JSON, check file existence)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`○` symbol is NOT in `doc_counts.py:format_result_text()`**: The referenced function (`doc_counts.py:163`) only uses `✓` and `✗`. The three-symbol mapping (`full → ✓`, `partial → ○`, `unsupported → ✗`) required by `CapabilityEntry.status` must be implemented directly in `doctor.py` — not mirrored from `doc_counts.py`.
- **Exact imports for `doctor.py`** (from `docs.py:8-9`): `from little_loops.cli.output import configure_output, use_color_enabled` and `from little_loops.logger import Logger`.
- **`FakeRunner` confirmed** (`test_action.py:25-48`): Does not yet have `describe_capabilities()`. Add a stub returning a minimal `CapabilityReport` matching FEAT-1523's shape. Existing stub pattern: each `build_*` method returns `HostInvocation(binary="claude", args=[...])`.
- **`CapabilityNotSupported`** is an importable `UserWarning` subclass in `host_runner.py` — use in `test_consistency_capability_not_supported_matches_report` via `warnings.catch_warnings(record=True)`.
- **No runtime consumers of `ll-action capabilities`** confirmed: Full codebase grep found zero callers outside of docs and issue files. The JSON shape change carries no downstream breakage risk beyond `test_action.py` updates.
- **`CapabilityReport`, `describe_capabilities`, `has_critical_gap` do not exist yet**: None of these symbols are present anywhere in the codebase — all must land from FEAT-1523 before this issue can be implemented.
- **`main_gitignore` exclusion precedent** (`cli/__init__.py`): `main_gitignore` is imported but absent from `__all__`. Ensure `main_doctor` is added to both the import block AND `__all__` to be fully exported.
- **`TestCmdCapabilities` assertion pattern**: `capsys.readouterr().out` → `json.loads(...)`. Each test patches three things: `little_loops.cli.action.resolve_host`, `little_loops.cli.action.subprocess.run`, and `little_loops.cli.action._find_plugin_root`.
- **Stale `TestCmdCapabilities` line range**: The Integration Map and Anchor References say "lines 308-398" — confirmed actual span is **308-404** (`TestCmdList` class starts at line 405, `TestMainAction` at line 438).
- **Stale `doc_counts.py` path and line in Implementation Steps and Similar Patterns**: Both reference `cli/doc_counts.py:format_result_text()` at "line 172" — the correct path is `scripts/little_loops/doc_counts.py` (NOT under the `cli/` subdirectory) and the function is at line **163**. The file under `cli/` does not exist.
- **`cli/__init__.py` is exactly 84 lines total**: imports block starts at line 29, `__all__` block at line 56, file ends at line 84 — the "lines 29-84" range in the issue is accurate.
- **`FakeRunner` has no `describe_capabilities()` stub** (confirmed as of 2026-05-16): `test_action.py:24-47` shows `FakeRunner` with `detect`, `build_streaming`, `build_blocking_json`, `build_version_check`, `build_detached` — step 4 must add `describe_capabilities()` returning a minimal `CapabilityReport`.

## Impact

- **Priority**: P4 — Quality-of-life preflight tool; not blocking automation, but materially improves multi-host UX
- **Effort**: Medium — New CLI module (~150 LOC), entry point wiring, test file, and `cmd_capabilities()` refactor with test updates; pattern is established by `cli/docs.py`
- **Risk**: Low — Net-new tool; only behavioral risk is the JSON shape change for `ll-action capabilities`, confirmed safe (no runtime consumers outside test suite)
- **Breaking Change**: Yes (minor) — `ll-action capabilities --json` output shape changes; only `test_action.py` requires updates

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-16_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 89/100 → HIGH CONFIDENCE

### Concerns
- FEAT-1523 (data model and Protocol) is still open; `CapabilityReport`, `describe_capabilities`, and `has_critical_gap` don't exist in the codebase yet — implementation cannot begin until FEAT-1523 is merged.

## Session Log
- `/ll:issue-size-review` - 2026-05-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e46d252d-d6ba-4cf5-9954-c3c6cea402e5.jsonl`
- `/ll:confidence-check` - 2026-05-16T15:07:07Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2eba7181-f872-447b-b971-2d9898d5f7d0.jsonl`
- `/ll:refine-issue` - 2026-05-16T16:17:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed312de9-319e-4f20-b181-75cd7e59a6f3.jsonl`
- `/ll:confidence-check` - 2026-05-16T16:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da25f3c9-59e2-4a23-b616-e70edb45a186.jsonl`
- `/ll:wire-issue` - 2026-05-16T16:11:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a248831a-2f44-4396-89d5-fdd0a4c30cbc.jsonl`
- `/ll:refine-issue` - 2026-05-16T16:07:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01ffccbc-3218-47c8-80de-81cb04de7885.jsonl`
- `/ll:format-issue` - 2026-05-16T15:15:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d20d20f9-58ee-4faf-9f54-894f4110d03f.jsonl`
- `/ll:issue-size-review` - 2026-05-16T15:07:07Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b57cdb22-126d-4dc6-b12f-a5213e07e705.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-16
- **Reason**: Issue too large for single session

### Decomposed Into
- FEAT-1524: ll-doctor — CLI module, entry point registration, and tests
- FEAT-1525: ll-action capabilities — emit full CapabilityReport + doc update

---

**Done** | Created: 2026-05-16 | Priority: P4

---
id: FEAT-1239
priority: P3
size: Medium
parent: FEAT-1236
decision_needed: false
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
completed_at: 2026-04-21T22:22:45Z
status: done
---

# FEAT-1239: Wire decide-issue into Python pipeline and manage-issue gate

## Summary

Wire the `decide-issue` skill into the ll-auto, ll-parallel, and ll-sprint pipelines by adding `decision_needed` support to `IssueInfo`, adding `decide_command` to `ParallelConfig`, inserting conditional `decide-issue` invocations in `issue_manager.py` and `worker_pool.py`, updating `config-schema.json`, and adding a `decision_needed` gate to `skills/manage-issue/SKILL.md`.

## Current Behavior

When `decision_needed: true` is set in an issue's frontmatter, the automation pipelines (ll-auto, ll-parallel, ll-sprint) and the `manage-issue` skill do not check this field — they proceed directly to implementation regardless. Issues with multiple competing implementation options are implemented without a decision-making step, risking the wrong approach being chosen silently.

## Expected Behavior

- `IssueInfo` parses `decision_needed` from frontmatter and exposes it to pipeline consumers
- `ll-auto` and `ll-parallel` invoke `/ll:decide-issue` between Phase 1 (ready check) and Phase 2 (implementation) when `decision_needed: true`
- `manage-issue` halts at Phase 2 with a clear message directing the user to run `/ll:decide-issue [ID]` when `decision_needed: true`; `--force-implement` bypasses the halt with a warning
- `config-schema.json` and the config layer chain (`automation.py`, `core.py`, `ParallelConfig`) expose `decide_command` so users can customize the invocation

## Use Case

A developer refines an issue and `/ll:refine-issue` deposits two competing implementation options, setting `decision_needed: true`. When `ll-auto` or `ll-parallel` picks up the issue next, instead of silently picking one approach, the pipeline pauses and invokes `/ll:decide-issue` — prompting a decision before implementation proceeds. Similarly, if the developer runs `/ll:manage-issue` directly, they see a clear HALT message directing them to resolve the decision first.

## Parent Issue

Decomposed from FEAT-1236: Add /ll:decide-issue skill to resolve multiple implementation options

## Depends On

FEAT-1238 (decide-issue skill must exist before pipeline wires to it)

## Acceptance Criteria

- `IssueInfo.decision_needed: bool | None = None` field parsed from frontmatter in `issue_parser.py`
- `ParallelConfig.decide_command` field + `get_decide_command()` method in `parallel/types.py`
- `issue_manager.py` invokes `decide-issue` between Phase 1 end and Phase 2 begin when `info.decision_needed is True`
- `worker_pool.py` invokes `decide-issue` between `set_worker_stage(IMPLEMENTING)` and `get_manage_command()` when `decision_needed=True`
- `config-schema.json` has `decide_command` property in `parallel` section (required because `additionalProperties: false`)
- `skills/manage-issue/SKILL.md` halts at Phase 2 with a clear message when `decision_needed: true`; `--force-implement` bypasses the halt with a warning

## Proposed Solution

### 1. IssueInfo — `scripts/little_loops/issue_parser.py`

- At line 247 (after `testable`), add: `decision_needed: bool | None = None`
- In `to_dict()` at line 281 (alongside `testable`): add `decision_needed` entry
- In `from_dict()` at line 311 (alongside `testable=data.get("testable")`): add `decision_needed=data.get("decision_needed")`
- In `parse_file():338-444`, extract `decision_needed` from frontmatter dict using the same pattern as `testable:401-409`

### 2. ParallelConfig — `scripts/little_loops/parallel/types.py`

- At line 329-330 (alongside `ready_command`/`manage_command`): add `decide_command: str = "decide-issue {{issue_id}}"`
- Add `get_decide_command(issue_id: str) -> str` method following `get_ready_command` pattern
- Add `decide_command` to `to_dict()` (alongside `manage_command:405-406`) and `from_dict()` (alongside `manage_command:443-446`)

### 3. issue_manager.py — `scripts/little_loops/issue_manager.py:560-563`

Insert conditional `decide-issue` step between Phase 1 end (line 560) and Phase 2 begin (line 562):
```python
if info.decision_needed is True:
    run_claude_command(f"decide-issue {issue_id} --auto")
```

### 4. worker_pool.py — `scripts/little_loops/parallel/worker_pool.py:370-376`

Insert conditional step between `set_worker_stage(IMPLEMENTING)` at line 370 and `get_manage_command` at line 376:
```python
if issue.decision_needed is True:
    _run_claude_command(self.parallel_config.get_decide_command(issue.issue_id))
```

### 5. config-schema.json

At line 297, add `decide_command` property to `parallel` section between `manage_command:297` and `worktree_copy_files:302`:
```json
"decide_command": {
  "type": "string",
  "default": "decide-issue {{issue_id}}",
  "description": "Command template for the decide-issue step. {{issue_id}} is substituted at runtime."
}
```

### 6. manage-issue gate — `skills/manage-issue/SKILL.md`

Add `decision_needed` gate at Phase 2 start (after optional confidence-check at lines 118-129, before plan creation). Follow the exact HALT/WARN/PROCEED pattern from Phase 2.5 (`SKILL.md:157-191`):
- If `decision_needed: true` and no `--force-implement`: HALT with message directing user to run `/ll:decide-issue [ISSUE_ID]` first
- If `decision_needed: true` and `--force-implement`: WARN and proceed

### 7. commands/refine-issue.md

Update the pipeline position section to reference `/ll:decide-issue` as the next step after `decision_needed: true` is set.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`issue_manager.py` calling convention**: All pipeline commands follow the `expand_skill() or slash_fallback` pattern before passing to `run_claude_command`. The decide-issue call should mirror the ready-issue call at `:354-363`:
```python
_decide_slash = f"/ll:decide-issue {info.issue_id} --auto"
_decide_cmd = expand_skill("decide-issue", [info.issue_id, "--auto"], config) or _decide_slash
result = run_claude_command(_decide_cmd, logger, timeout=config.automation.timeout_seconds, ...)
```

**`worker_pool.py` calling convention**: `_run_claude_command()` signature at `:626` is `(command, working_dir, issue_id=)` — `worktree_path` is required as the second positional argument. Follow the ready-issue call at `:272-278`:
```python
decide_cmd = self.parallel_config.get_decide_command(issue.issue_id)
decide_result = self._run_claude_command(decide_cmd, worktree_path, issue_id=issue.issue_id)
```

**`manage-issue` gate placement**: Insert new `## Phase 2.3: Decision Gate` section **before** Phase 2.5 (confidence gate at `:157`), not inside it. The gate pseudocode is identical in structure to Phase 2.5's HALT/WARN/PROCEED pattern.

## Files to Modify

- `scripts/little_loops/issue_parser.py` — `IssueInfo.decision_needed` field + parse/serialize
- `scripts/little_loops/parallel/types.py` — `ParallelConfig.decide_command` + `get_decide_command()`
- `scripts/little_loops/issue_manager.py` — conditional decide-issue invocation
- `scripts/little_loops/parallel/worker_pool.py` — conditional decide-issue invocation
- `config-schema.json` — `decide_command` JSON Schema property
- `skills/manage-issue/SKILL.md` — `decision_needed` gate
- `commands/refine-issue.md` — pipeline position update

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py:247` — add `decision_needed: bool | None = None` field; serialize at `:282` (`to_dict`), deserialize at `:310` (`from_dict`), parse at `:401-441` (`parse_file`) following `testable_raw`/`testable_value` pattern
- `scripts/little_loops/parallel/types.py:329` — add `decide_command` field alongside `ready_command`/`manage_command`; add `get_decide_command()` following `get_ready_command()` at `:357-367`; update `to_dict()`:404 and `from_dict()`:443
- `scripts/little_loops/issue_manager.py:560` — insert conditional decide-issue step after `issue_timing["ready"]` assignment and before Phase 2 comment
- `scripts/little_loops/parallel/worker_pool.py:370` — insert conditional step after `set_worker_stage(IMPLEMENTING)` and before `get_manage_command()` at `:376`
- `config-schema.json:297` — add `decide_command` property to `parallel` section (schema uses `additionalProperties: false` at `:326`, so omitting this causes validation failure)
- `skills/manage-issue/SKILL.md:157` — insert new `## Phase 2.3: Decision Gate` before Phase 2.5 confidence gate
- `commands/refine-issue.md` — update pipeline position section
- `scripts/little_loops/config/automation.py:51-90` — add `decide_command: str` field to `ParallelAutomationConfig` and its `from_dict()` method; this is the middle layer of the 3-layer config chain — without it, `ll-config.json`'s `parallel.decide_command` is silently ignored even if the schema and `ParallelConfig` accept it [Wiring pass added by `/ll:wire-issue`]
- `scripts/little_loops/config/core.py:302-335,385-400` — add `decide_command=self._parallel.decide_command` in `BRConfig.create_parallel_config()` (alongside `ready_command`/`manage_command` at lines ~319-321) and in `to_dict()` parallel section (alongside `ready_command`/`manage_command` at lines ~394-395); this is the final forwarding layer from config loading to ParallelConfig instantiation [Wiring pass added by `/ll:wire-issue`]

### Tests

- `scripts/tests/test_issue_parser.py:1346` — add `TestIssueInfoDecisionNeeded` class following `TestIssueInfoTestable` pattern (7-8 cases: default None, False, True, to_dict, from_dict missing, from_dict false, parse_file with/without field)
- `scripts/tests/test_parallel_types.py:724` — add `decide_command` assertion to `test_default_values`; add `test_get_decide_command` tests following `test_get_ready_command*` at `:776-826`; add field to `test_roundtrip_serialization`:968
- `scripts/tests/test_parallel_types.py:953` — add `decide_command` default assertion to `test_from_dict_defaults_for_missing_fields` (currently asserts `command_prefix` and `base_branch` but not `decide_command`) [Wiring pass added by `/ll:wire-issue`]
- `scripts/tests/test_issue_manager.py` — add tests for conditional decide-issue invocation (triggered when `decision_needed=True`, skipped when `None`/`False`); use `process_issue_inplace` with `patch("little_loops.issue_manager.run_claude_command")` following `TestReadyIssueErrorHandling` pattern at `:1173`
- `scripts/tests/test_worker_pool.py` — add tests for conditional decide-issue invocation in parallel path; use call_count pattern in `TestWorkerPoolProcessIssue._process_issue()` flow tests at `:1743`; set `mock_issue.decision_needed = True/None` on the `MagicMock` fixture

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:298-306` — parallel config table lists `ready_command` and `manage_command` with defaults and descriptions; add a `decide_command` row between them following the same format (default: `"decide-issue {{issue_id}}"`)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/automation.py:51-90` — defines `ParallelAutomationConfig` which is the data class that reads `parallel.*` from `ll-config.json`; imports `ParallelConfig` indirectly via `core.py`. Adding `decide_command` to the schema without this class means user config for `decide_command` is silently dropped.
- `scripts/little_loops/config/core.py:302-335` — `BRConfig.create_parallel_config()` maps `self._parallel.*` fields to `ParallelConfig(...)` constructor args; imports `ParallelAutomationConfig`. Adding `decide_command` to `ParallelConfig` without threading it through here means the field always uses its default regardless of user config.

### Similar Patterns
- `scripts/little_loops/issue_parser.py:247` — `testable: bool | None = None` exact field shape to copy for `decision_needed`
- `scripts/little_loops/parallel/types.py:357-367` — `get_ready_command()` exact method shape for `get_decide_command()`
- `skills/manage-issue/SKILL.md:157-191` — Phase 2.5 confidence gate is the exact HALT/WARN/PROCEED pseudocode structure to follow

## Implementation Steps

1. **`issue_parser.py`**: Add `decision_needed: bool | None = None` at `:247`. Copy `testable_raw`/`testable_value` two-branch string-coercion block at `:401-409` (rename variables). Add to `to_dict()`:282 and `from_dict()`:310 with `data.get("decision_needed")` (no default).
2. **`parallel/types.py`**: Add `decide_command: str = "decide-issue {{issue_id}}"` at `:330`. Add `get_decide_command(issue_id: str) -> str` after `get_ready_command()`:357. Add to `to_dict()`:404 and `from_dict()`:443 with default matching the field default.
3. **`config-schema.json`**: Insert `"decide_command"` property between `manage_command` and `worktree_copy_files` in the `parallel` section. Use `{"type": "string", "description": "Command template for decide-issue step. {{issue_id}} substituted at runtime.", "default": "decide-issue {{issue_id}}"}`.
4. **`config/automation.py`**: Add `decide_command: str = "decide-issue {{issue_id}}"` to `ParallelAutomationConfig` alongside `ready_command`/`manage_command`. Update `from_dict()` to read `data.get("decide_command", ...)` with the same default. [Wiring pass added by `/ll:wire-issue`]
5. **`config/core.py`**: In `create_parallel_config()`, add `decide_command=self._parallel.decide_command` to the `ParallelConfig(...)` constructor call. In `to_dict()`, add `"decide_command": self._parallel.decide_command` to the parallel section dict alongside `ready_command`/`manage_command`. [Wiring pass added by `/ll:wire-issue`]
6. **`issue_manager.py`**: After `issue_timing["ready"] = ...` at `:560`, add `if info.decision_needed is True:` block. Use `expand_skill("decide-issue", [info.issue_id, "--auto"], config) or _decide_slash` pattern (not bare `run_claude_command(f"decide-issue ...")`) to match existing pipeline conventions.
7. **`worker_pool.py`**: After `set_worker_stage(IMPLEMENTING)` at `:370`, add `if issue.decision_needed is True:` block calling `self._run_claude_command(decide_cmd, worktree_path, issue_id=issue.issue_id)`.
8. **`skills/manage-issue/SKILL.md`**: Insert `## Phase 2.3: Decision Gate` before Phase 2.5. READ `decision_needed` from YAML frontmatter. If `true` and no `--force-implement`: HALT directing user to run `/ll:decide-issue [ID]`. If `true` and `--force-implement`: WARN and PROCEED. If absent/false: PROCEED silently.
9. **`commands/refine-issue.md`**: In Pipeline Position section, add `/ll:decide-issue` to the flow between `/ll:refine-issue` and `/ll:wire-issue`.
10. **Tests**: Add `TestIssueInfoDecisionNeeded` to `test_issue_parser.py` (7-8 cases mirroring `TestIssueInfoTestable`). Add `test_get_decide_command*` (3 methods mirroring `:776-826`), `decide_command` default assertion to `test_default_values`, assertion to `test_from_dict_defaults_for_missing_fields`, and field to `test_roundtrip_serialization` in `test_parallel_types.py`. Add conditional invocation tests to `test_issue_manager.py` (using `process_issue_inplace` + `TestReadyIssueErrorHandling` pattern) and `test_worker_pool.py` (using call_count pattern in `TestWorkerPoolProcessIssue`).
11. **`docs/reference/CONFIGURATION.md`**: Add `decide_command` row to the parallel config table at `:298-306`. [Wiring pass added by `/ll:wire-issue`]

## Impact

- **Priority**: P3
- **Effort**: Medium — touches multiple Python files but each change is small and well-scoped
- **Risk**: Low — purely additive; existing behavior unchanged when `decision_needed` is absent/false
- **Breaking Change**: No (additive to schema)

## Labels

`feature`, `pipeline`, `automation`

---

**Completed** | Created: 2026-04-21 | Priority: P3

## Resolution

Implemented all acceptance criteria:

- `IssueInfo.decision_needed: bool | None = None` added to `issue_parser.py` with full parse/serialize/deserialize support following the `testable` pattern
- `ParallelConfig.decide_command` field + `get_decide_command()` method added to `parallel/types.py`
- `issue_manager.py` invokes `decide-issue` (via `expand_skill` pattern) between Phase 1 and Phase 2 when `info.decision_needed is True`
- `worker_pool.py` invokes `decide-issue` between `set_worker_stage(IMPLEMENTING)` and `get_manage_command()` when `issue.decision_needed is True`
- `config-schema.json` has `decide_command` property in `parallel` section
- `config/automation.py` `ParallelAutomationConfig` has `decide_command` field (middle config layer)
- `config/core.py` threads `decide_command` through `create_parallel_config()` and `to_dict()`
- `skills/manage-issue/SKILL.md` has Phase 2.3 Decision Gate with HALT/WARN/PROCEED pattern; `--force-implement` bypasses with warning
- `docs/reference/CONFIGURATION.md` has `decide_command` row in parallel config table
- 18 new tests added across `test_issue_parser.py`, `test_parallel_types.py`, `test_issue_manager.py`, `test_worker_pool.py`; full suite: 5087 passed

## Session Log
- `/ll:ready-issue` - 2026-04-21T22:12:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/02ab6d71-d9eb-4e8f-9d67-3dbb5174a9f5.jsonl`
- `/ll:wire-issue` - 2026-04-21T22:08:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a7b6286-0e67-451f-8360-2e4e3d0cc0b4.jsonl`
- `/ll:refine-issue` - 2026-04-21T22:02:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/68101119-8e6e-4ea9-89c9-399845bad1cf.jsonl`
- `/ll:confidence-check` - 2026-04-21T22:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f6228541-5875-4fde-b8dd-a8e77e8985fd.jsonl`
- `/ll:manage-issue` - 2026-04-21T22:22:45Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

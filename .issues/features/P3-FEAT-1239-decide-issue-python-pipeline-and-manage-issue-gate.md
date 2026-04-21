---
id: FEAT-1239
priority: P3
size: Medium
parent: FEAT-1236
---

# FEAT-1239: Wire decide-issue into Python pipeline and manage-issue gate

## Summary

Wire the `decide-issue` skill into the ll-auto, ll-parallel, and ll-sprint pipelines by adding `decision_needed` support to `IssueInfo`, adding `decide_command` to `ParallelConfig`, inserting conditional `decide-issue` invocations in `issue_manager.py` and `worker_pool.py`, updating `config-schema.json`, and adding a `decision_needed` gate to `skills/manage-issue/SKILL.md`.

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

## Files to Modify

- `scripts/little_loops/issue_parser.py` — `IssueInfo.decision_needed` field + parse/serialize
- `scripts/little_loops/parallel/types.py` — `ParallelConfig.decide_command` + `get_decide_command()`
- `scripts/little_loops/issue_manager.py` — conditional decide-issue invocation
- `scripts/little_loops/parallel/worker_pool.py` — conditional decide-issue invocation
- `config-schema.json` — `decide_command` JSON Schema property
- `skills/manage-issue/SKILL.md` — `decision_needed` gate
- `commands/refine-issue.md` — pipeline position update

## Impact

- **Priority**: P3
- **Effort**: Medium — touches multiple Python files but each change is small and well-scoped
- **Risk**: Low — purely additive; existing behavior unchanged when `decision_needed` is absent/false
- **Breaking Change**: No (additive to schema)

## Labels

`feature`, `pipeline`, `automation`

---

**Open** | Created: 2026-04-21 | Priority: P3

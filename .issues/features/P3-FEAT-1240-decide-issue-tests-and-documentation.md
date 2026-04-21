---
id: FEAT-1240
priority: P3
size: Medium
parent: FEAT-1236
---

# FEAT-1240: Tests and documentation for decide-issue

## Summary

Add tests for the decide-issue skill and all Python pipeline changes introduced by FEAT-1238 and FEAT-1239, and update documentation to include decide-issue in the refinement pipeline.

## Parent Issue

Decomposed from FEAT-1236: Add /ll:decide-issue skill to resolve multiple implementation options

## Depends On

FEAT-1238 (skill must exist for doc-wiring tests), FEAT-1239 (Python changes must exist for integration tests)

## Acceptance Criteria

- `scripts/tests/test_decide_issue_skill.py` exists with doc-wiring assertions following `test_refine_issue_command.py` pattern
- `TestIssueInfoDecisionNeeded` class added to `test_issue_parser.py` (5 unit tests + 1 `parse_file` integration test)
- `TestUpdateFrontmatter` addition in `test_frontmatter.py` verifying `decision_needed: False` write
- `test_parallel_types.py` updated: `decide_command` assertions in 3 existing tests + new `test_get_decide_command_*`
- `test_worker_pool.py` updated: 4 two-call mocks updated to three-call; 2 new tests added
- `test_issue_manager.py` updated: case where `decision_needed: true` triggers the decide-issue step
- `test_orchestrator.py` updated: conditional decide-issue invocation case
- Documentation updated in 5 files

## Proposed Solution

### New Test File: `scripts/tests/test_decide_issue_skill.py`

Doc-wiring tests asserting `skills/decide-issue/SKILL.md` contains:
- Flag parsing section (`--auto`, `--dry-run`)
- Three option extraction patterns
- `codebase-pattern-finder` subagent spawn reference
- Scoring criteria (consistency, simplicity, testability, risk)
- `> **Selected:**` annotation format
- `decision_needed: false` frontmatter update
- `ll-issues append-log` session log call

Follow `test_refine_issue_command.py` pattern: `Path.read_text()` + `str.index()` assertions.

### test_issue_parser.py — Add `TestIssueInfoDecisionNeeded`

Follow `TestIssueInfoTestable:1346` and `TestIssueInfoSize:1477` as the exact template:
1. `test_decision_needed_defaults_to_none`
2. `test_decision_needed_set_value`
3. `test_decision_needed_in_to_dict`
4. `test_decision_needed_from_dict_restore`
5. `test_decision_needed_from_dict_missing`
6. Integration: `IssueParser.parse_file` with `decision_needed: true` frontmatter

### test_frontmatter.py — Add to `TestUpdateFrontmatter`

Add test verifying that passing `{"decision_needed": False}` via `update_frontmatter()` produces correct serialized output. Confirm whether `bool` is accepted by the function's type signature `dict[str, str | int]` — if not, document the type gap.

### test_parallel_types.py — Update Existing + Add New

**Update** (add `decide_command` assertions):
- `test_default_values:724`
- `test_roundtrip_serialization:968`
- `test_from_dict_defaults_for_missing_fields:953`

**Add new**:
- `test_get_decide_command_builds_correct_string` — follow `test_get_ready_command:776` pattern

If a `DECIDING` `WorkerStage` enum value is added in FEAT-1239, update `test_enum_member_count:402` from `== 8` to `== 9`.

### test_worker_pool.py — Update 4 Mocks + Add 2 Tests

**Update** (two-call `_run_claude_command` mocks → three-call when `decision_needed=True`):
- `test_process_issue_success_flow:1814`
- `test_process_issue_cleans_leaked_files:1872`
- `test_process_issue_captures_corrections:1926`
- `test_process_issue_recovers_committed_leaks:1978`

**Add new**:
- `test_process_issue_skips_decide_when_decision_not_needed` — confirms two calls when `decision_needed=None`
- `test_process_issue_runs_decide_when_decision_needed` — confirms three calls; second call contains `decide-issue`

### test_issue_manager.py

Add test case: `decision_needed: true` in `IssueInfo` triggers `decide-issue` step between Phase 1 and Phase 2.

### test_orchestrator.py

Add test case: conditional decide-issue invocation when `decision_needed=True`.

### Documentation Updates

- `docs/ARCHITECTURE.md` — update pipeline diagram to show decide-issue between refine-issue and wire-issue
- `docs/reference/COMMANDS.md` — add `/ll:decide-issue` entry in skill reference
- `docs/reference/CONFIGURATION.md:301-302` — add `decide_command` row to parallel command templates table; add `decision_needed` gate description near line 342 mirroring `confidence_gate.enabled`
- `docs/reference/API.md:570` — add `decision_needed: bool | None = None` to `IssueInfo` code block after `testable`
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:182-190` — add `decide-issue` step between `refine-issue` and `wire-issue` in refinement pipeline numbered list

## Files to Create/Modify

- `scripts/tests/test_decide_issue_skill.py` — **new file**
- `scripts/tests/test_issue_parser.py` — add `TestIssueInfoDecisionNeeded`
- `scripts/tests/test_frontmatter.py` — add `TestUpdateFrontmatter` case
- `scripts/tests/test_parallel_types.py` — update 3 tests + add new
- `scripts/tests/test_worker_pool.py` — update 4 mocks + add 2 tests
- `scripts/tests/test_issue_manager.py` — add conditional decide-issue case
- `scripts/tests/test_orchestrator.py` — add conditional decide-issue case
- `docs/ARCHITECTURE.md` — pipeline diagram
- `docs/reference/COMMANDS.md` — new entry
- `docs/reference/CONFIGURATION.md` — new row + description
- `docs/reference/API.md` — new field
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — new pipeline step

## Impact

- **Priority**: P3
- **Effort**: Medium — many files but changes are mechanical (template-following)
- **Risk**: Low — test additions only; 4 existing worker_pool tests need mock count updates
- **Breaking Change**: No

## Labels

`feature`, `pipeline`, `automation`, `testing`, `documentation`

---

**Open** | Created: 2026-04-21 | Priority: P3

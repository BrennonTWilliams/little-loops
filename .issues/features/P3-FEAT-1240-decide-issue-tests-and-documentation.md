---
id: FEAT-1240
priority: P3
size: Very Large
parent: FEAT-1236
confidence_score: 100
outcome_confidence: 61
score_complexity: 0
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
completed_at: 2026-04-21T22:43:52Z
status: done
---

# FEAT-1240: Tests and documentation for decide-issue

## Summary

Add tests for the decide-issue skill and all Python pipeline changes introduced by FEAT-1238 and FEAT-1239, and update documentation to include decide-issue in the refinement pipeline.

## Parent Issue

Decomposed from FEAT-1236: Add /ll:decide-issue skill to resolve multiple implementation options

## Depends On

FEAT-1238 (skill must exist for doc-wiring tests), FEAT-1239 (Python changes must exist for integration tests)

## Use Case

A developer modifies the decide-issue skill or its pipeline integration and needs confidence that the change is correct. Without tests, regressions are invisible until manual inspection. Documentation gaps mean the skill doesn't appear in refinement pipeline guides, leaving users unaware it exists.

## Current Behavior

- `scripts/tests/test_decide_issue_skill.py` does not exist — the decide-issue skill has no doc-wiring test coverage
- `test_frontmatter.py` and `test_orchestrator.py` lack `decision_needed`-related test cases
- Documentation files omit decide-issue from pipeline diagrams, command references, and configuration tables

## Expected Behavior

- `test_decide_issue_skill.py` exists with assertions covering all 7 structural elements of `SKILL.md`
- All test files cover `decision_needed` gating logic with full branch coverage
- All five documentation files list decide-issue in the appropriate pipeline stage and reference tables

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

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/automation.py:53` — defines `ParallelAutomationConfig.decide_command` field; already consistent, no change needed
- `scripts/little_loops/config/core.py` — aggregates `ParallelAutomationConfig`; already consistent
- `scripts/little_loops/parallel/orchestrator.py` — imports `WorkerPool` and `IssueInfo`; handles `DECIDING` state; `test_orchestrator.py` has zero `decision_needed` tests (confirmed gap)
- `scripts/little_loops/skill_expander.py` — expands `{{config.decide_command}}` placeholders in skill content

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Already-Implemented (Verify Only)

Research found these test classes/tests **already exist** from FEAT-1238/FEAT-1239 implementation — verify each before re-adding:

- `TestIssueInfoDecisionNeeded` at `scripts/tests/test_issue_parser.py:1477-1605` — full class with 8 tests (default None, False, True, to_dict, from_dict missing, from_dict False, parse_file True, parse_file absent)
- `decide_command` assertions at `scripts/tests/test_parallel_types.py:724,829-853,980` — `test_default_values` includes `decide_command` field; `TestGetDecideCommand` at :829 tests default/custom prefix/custom template; `test_from_dict_defaults_for_missing_fields` and `test_roundtrip_serialization` include `decide_command`
- `TestWorkerPoolDecisionNeededGate` at `scripts/tests/test_worker_pool.py:2213` — tests "invoked when True" and "skipped when None"
- `TestDecisionNeededGate` at `scripts/tests/test_issue_manager.py:2569` — tests `process_issue_inplace()` decision gate

#### Files to Create
- `scripts/tests/test_decide_issue_skill.py` — confirmed **does not exist**; primary deliverable
  - Target: `skills/decide-issue/SKILL.md` (9-phase structure: flag parsing :53-75, option extraction :98-128, pattern-finder spawn :134-163, scoring :169-198, annotation format `> **Selected:**` :204-238, `decision_needed: false` update :242-266, `ll-issues append-log` :272-286)
  - Follow: `scripts/tests/test_refine_issue_command.py:1-121` — module-level `Path` constants, `content.index()` for section boundaries, slice assertions

#### Files to Modify
- `scripts/tests/test_frontmatter.py:180-279` — verify `TestUpdateFrontmatter` lacks `decision_needed: False` test; `bool` subclasses `int` so `{"decision_needed": False}` satisfies `dict[str, str | int]` type signature at `frontmatter.py:106`
- `scripts/tests/test_orchestrator.py` — verify conditional decide-issue test exists; orchestrator delegates to `WorkerPool._process_issue()` indirectly via `worker_pool.submit()` at `orchestrator.py:792,830` — no direct `decision_needed` check in orchestrator
- `docs/ARCHITECTURE.md`, `docs/reference/COMMANDS.md`, `docs/reference/CONFIGURATION.md:301-302,342`, `docs/reference/API.md:570`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:182-190`

#### Files Outside Known List — Also Need Updating

_Wiring pass added by `/ll:wire-issue`:_

- `README.md:89` — `"26 skills"` must become `"27 skills"` (`ll-verify-docs` will fail otherwise); also add `/ll:decide-issue` row to Issue Refinement table (~line 108-124) and Skills table (~line 210-237)
- `CONTRIBUTING.md:125` — `"26 skill definitions"` must become `"27 skill definitions"`; also update `skills/` directory tree (~line 125-149) to list `decide-issue/`
- `skills/issue-workflow/SKILL.md:69-81` — Refinement Phase command list omits `decide-issue` between `refine-issue` and `wire-issue`
- `CHANGELOG.md` — no entry for `decide-issue` skill (FEAT-1238/1239 changes); add a user-facing entry in the current release section (do NOT use `[Unreleased]`)
- `.claude/CLAUDE.md` — Issue Refinement skills list omits `decide-issue`^; add between `refine-issue` and `wire-issue`
- `docs/reference/ISSUE_TEMPLATE.md:887` — `decision_needed` frontmatter row documents the setter (`refine-issue`) but not the consumer; mention `/ll:decide-issue` as the consuming command

#### Key Source Files
- `skills/decide-issue/SKILL.md` — full 9-phase implementation, used as doc-wiring test target
- `scripts/little_loops/issue_parser.py:247-248` — `decision_needed: bool | None = None` after `testable`
- `scripts/little_loops/frontmatter.py:106` — `update_frontmatter(content: str, updates: dict[str, str | int]) -> str`
- `scripts/little_loops/parallel/types.py:331,388` — `decide_command` field and `get_decide_command()` method
- `scripts/little_loops/parallel/worker_pool.py:373-382` — decision gate: `if issue.decision_needed is True` → calls `_run_claude_command` with decide cmd
- `scripts/little_loops/issue_manager.py:563-577` — `process_issue_inplace()` decide-issue step between Phase 1 (ready) and Phase 2 (manage)

#### Similar Patterns
- `scripts/tests/test_refine_issue_command.py:1-121` — exact template for new skill test file
- `scripts/tests/test_issue_parser.py:1346-1475` — `TestIssueInfoTestable` as field-test template
- `scripts/tests/test_parallel_types.py:777-853` — `test_get_ready_command` as template for `test_get_decide_command`

## Implementation Steps

1. **Create `scripts/tests/test_decide_issue_skill.py`**: Define `SKILL_FILE = PROJECT_ROOT / "skills" / "decide-issue" / "SKILL.md"`; assert all 7 Acceptance Criteria items using `content.index()` section boundaries following `test_refine_issue_command.py:18-82` pattern
2. **Verify `test_frontmatter.py`**: Check `TestUpdateFrontmatter` at :180-279 for `decision_needed: False` test; if absent, add one using `update_frontmatter(content, {"decision_needed": False})` and assert `"decision_needed: false"` in result (YAML lowercases bool)
3. **Verify `test_orchestrator.py`**: Check for decide-issue conditional invocation test; if absent, add a test that verifies a `decision_needed=True` issue routes through the worker pool correctly
4. **Update `docs/ARCHITECTURE.md`**: Insert decide-issue between refine-issue and wire-issue in pipeline diagram
5. **Update `docs/reference/COMMANDS.md`**: Add `/ll:decide-issue` entry following existing skill entry format
6. **Update `docs/reference/CONFIGURATION.md:301-302`**: Add `decide_command` row to parallel command templates table; add `decision_needed` gate description near :342 mirroring `confidence_gate.enabled`
7. **Update `docs/reference/API.md:570`**: Add `decision_needed: bool | None = None` to `IssueInfo` code block after `testable`
8. **Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:182-190`**: Add decide-issue step between refine-issue and wire-issue in refinement pipeline numbered list
9. **Run tests**: `python -m pytest scripts/tests/test_decide_issue_skill.py scripts/tests/test_frontmatter.py scripts/tests/test_orchestrator.py -v --tb=short`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. **Update `README.md`**: Change `"26 skills"` → `"27 skills"` (~line 89); add `/ll:decide-issue` row to Issue Refinement table (~line 108-124) and to Skills table (~line 210-237) — `ll-verify-docs` will fail if count is not updated
11. **Update `CONTRIBUTING.md`**: Change `"26 skill definitions"` → `"27 skill definitions"` (~line 125); add `decide-issue/` to the `skills/` directory tree (~line 125-149)
12. **Update `skills/issue-workflow/SKILL.md:69-81`**: Add `decide-issue` to Refinement Phase command list between `refine-issue` and `wire-issue`
13. **Update `CHANGELOG.md`**: Add user-facing entry for `/ll:decide-issue` skill in the current release section (do NOT use `[Unreleased]`; promote to a concrete `## [X.Y.Z]` version block)
14. **Update `.claude/CLAUDE.md`**: Add `decide-issue`^ to the Issue Refinement skills list between `refine-issue` and `wire-issue`
15. **Update `docs/reference/ISSUE_TEMPLATE.md:887`**: Extend the `decision_needed` frontmatter row to mention `/ll:decide-issue` as the consuming command (alongside the existing mention of `refine-issue` as the setter)

## Impact

- **Priority**: P3
- **Effort**: Medium — many files but changes are mechanical (template-following)
- **Risk**: Low — test additions only; 4 existing worker_pool tests need mock count updates
- **Breaking Change**: No

## Labels

`feature`, `pipeline`, `automation`, `testing`, `documentation`

---

**Completed** | Created: 2026-04-21 | Priority: P3

## Resolution

Implemented all acceptance criteria:

- Created `scripts/tests/test_decide_issue_skill.py` with 27 doc-wiring assertions across 8 test classes covering all 7 structural elements of `skills/decide-issue/SKILL.md`
- Added `test_update_decision_needed_bool_false` to `test_frontmatter.py::TestUpdateFrontmatter` confirming bool False (subclasses int) serializes as YAML `false`
- Added `TestDecisionNeededRouting` to `test_orchestrator.py` with 2 tests verifying decision_needed issues are dispatched to `_process_parallel` without orchestrator-level blocking
- Updated 11 documentation files: `docs/ARCHITECTURE.md` (Deciding state), `docs/reference/COMMANDS.md` (new entry), `docs/reference/API.md` (decision_needed field), `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` (step 5), `README.md` (skill count 26→27, two table rows), `CONTRIBUTING.md` (skill count + directory tree), `skills/issue-workflow/SKILL.md` (refinement phase), `CHANGELOG.md` (1.86.0 entry), `docs/reference/ISSUE_TEMPLATE.md` (decision_needed row)
- `.claude/CLAUDE.md` update blocked by file permissions — requires manual addition of `decide-issue`^ to Issue Refinement list

## Session Log
- `/ll:ready-issue` - 2026-04-21T22:36:52 - `43a10134-e6ab-43e1-ac5c-a1f561db0cd0.jsonl`
- `/ll:wire-issue` - 2026-04-21T22:31:49 - `1fe3f6c6-5218-469a-85e0-c99d45f7980b.jsonl`
- `/ll:refine-issue` - 2026-04-21T22:27:21 - `334dbc9e-19a8-43a9-bcb6-3b35525856ba.jsonl`
- `/ll:confidence-check` - 2026-04-21T22:45:00 - `6ea157c8-aee5-47f5-af69-3a6e8572e83e.jsonl`
- `/ll:manage-issue` - 2026-04-21T22:43:52Z - `fff12b2b-2ed2-40bc-9248-ba889878465e.jsonl`

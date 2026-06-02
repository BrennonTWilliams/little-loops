---
captured_at: "2026-04-21T20:38:05Z"
discovered_date: "2026-04-21"
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 60
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
size: Very Large
status: done
completed_at: 2026-04-21T00:00:00Z
---

# FEAT-1236: Add /ll:decide-issue skill to resolve multiple implementation options

## Summary

A new `/ll:decide-issue` skill that, when an issue has a `decision_needed: true` frontmatter flag, compares listed implementation options using codebase evidence, evaluates their tradeoffs, selects the best-fit option, updates the issue with the decision and reasoning, and clears the flag. Enables the refinement pipeline to fully resolve issues before implementation without requiring human intervention for every option-bearing issue.

## Current Behavior

When `/ll:refine-issue --auto` finds multiple valid implementation approaches from codebase research, it deposits all options without choosing one. There is no mechanism to automatically evaluate and select among them. The choice is left to the implementer at implementation time — when switching is most expensive and context is most stale.

## Expected Behavior

A `/ll:decide-issue` skill can be run after `/ll:refine-issue` to evaluate listed options using codebase evidence (similar patterns, call sites, consistency, complexity), select one, annotate the reasoning inline, and update the issue with a final decision. A `decision_needed: true` frontmatter flag (set by `refine-issue --auto` per ENH-1237) signals to automation that this step should run before the issue proceeds to `/ll:wire-issue`.

## Motivation

Unresolved implementation options left in issues create ambiguity for automated pipelines — `ll-auto` cannot choose among them, and implementers must make the decision at implementation time when switching cost is highest. Resolving options early, with codebase evidence, produces cleaner, more actionable issues and makes automated pipelines fully unattended through the refinement phase.

## Use Case

A developer runs `ll-auto` on a backlog of issues. `/ll:refine-issue --auto` enriches an ENH issue and finds 3 viable implementation approaches from pattern research. It sets `decision_needed: true` in frontmatter. `ll-auto` detects the flag and invokes `/ll:decide-issue`, which evaluates the 3 options, finds that Option 2 matches an established pattern in the codebase, selects it, and annotates the reasoning. The issue proceeds to `/ll:wire-issue` with a clear, decided approach — no human decision required.

## Acceptance Criteria

- Given an issue with `decision_needed: true` and 2+ options in Proposed Solution, `/ll:decide-issue` selects one and updates the issue with the choice highlighted and reasoning annotated
- `decision_needed` is cleared (false or removed) from frontmatter after a decision is made
- If only one option is present, the skill exits cleanly without modifying the issue
- Can be run manually on any issue even without the `decision_needed` flag
- `--dry-run` flag previews the decision without modifying the issue
- Output report includes the chosen option, scoring summary, and options considered
- `/ll:manage-issue` halts at Phase 2 with a clear message when `decision_needed: true` is present, directing the user to run `/ll:decide-issue` first; `--force-implement` bypasses the halt with a warning

## Proposed Solution

New skill at `skills/decide-issue/SKILL.md`:

1. Read the issue and extract all implementation options from `Proposed Solution` (numbered list items, option headers, or "Option A / Option B" patterns)
2. For each option, spawn a `codebase-pattern-finder` subagent to gather evidence: does this pattern exist elsewhere? how many call sites? any existing utilities that support it?
3. Score each option against: consistency with existing patterns, implementation simplicity, testability, and risk
4. Select the top-scoring option; annotate it inline in `Proposed Solution` with a `> **Selected:** ...` callout and a `### Decision Rationale` subsection explaining the scoring
5. Clear `decision_needed: true` from frontmatter (set to `false` or remove key)

Triggered by `decision_needed: true` in frontmatter when invoked by `ll-auto`/`ll-parallel`. Can also be invoked manually on any issue with multiple options.

## API/Interface

```
/ll:decide-issue [ISSUE_ID] [--auto] [--dry-run]
```

Frontmatter field:
```yaml
decision_needed: true   # set by refine-issue --auto; cleared by decide-issue
```

## Integration Map

### Files to Modify
- `skills/decide-issue/SKILL.md` — new skill (create)
- `commands/` — register skill if needed
- `scripts/little_loops/auto.py` — add conditional `decide-issue` invocation when `decision_needed: true`
- `scripts/little_loops/parallel_runner.py` — same conditional invocation
- `skills/manage-issue/SKILL.md` — add `decision_needed` gate at Phase 2 (after reading issue, before plan creation): halt with message if `true`, respect `--force-implement` to bypass with warning

### Dependent Files (Callers/Importers)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/issue_manager.py:560-563` — `decide-issue` step must be inserted between Phase 1 end (line 560) and Phase 2 begin (line 562); `run_claude_command()` is the invocation mechanism
- `scripts/little_loops/parallel/worker_pool.py:370-376` — `decide-issue` step must be inserted between Step 4 end (`set_worker_stage` at line 370) and Step 5 begin (`get_manage_command` at line 376); uses `_run_claude_command()`
- `scripts/little_loops/parallel/types.py:329-330` — `ParallelConfig` stores `ready_command` and `manage_command` templates; a `decide_command: str = "decide-issue {{issue_id}}"` field should be added alongside them with a corresponding `get_decide_command()` method
- `scripts/little_loops/issue_parser.py:247` — `IssueInfo` dataclass has `testable: bool | None = None`; add `decision_needed: bool | None = None` with the same pattern so Python pipeline can read the flag
- `scripts/little_loops/frontmatter.py:106-129` — `update_frontmatter()` is used to write frontmatter fields from Python; used by `orchestrator.py` for `completed_at`; `decide-issue` can use Edit tool (skill-side) or this function (Python-side) to clear the flag

### Similar Patterns

_Corrected and enriched by `/ll:refine-issue`:_

- `skills/wire-issue/SKILL.md:123-202` — primary structural model for the new SKILL.md; parallel Agent spawn pattern, flag parsing, issue location, and `ll-issues append-log` session log at line 367
- `skills/manage-issue/SKILL.md:157-191` — `--force-implement` gate pattern to follow exactly for the `decision_needed` gate; `confidence_score` gate uses the same HALT/WARN/PROCEED structure
- `skills/confidence-check/SKILL.md:398-446` — canonical inline `---` block frontmatter replacement pattern for clearing `decision_needed` via Edit tool
- `skills/format-issue/SKILL.md:163-175` — idempotency rule: skip the write if field already has the same value
- `.issues/completed/P2-BUG-903-*.md:65-76` — real `**Option A** / **Option B**` example for option extraction testing
- Note: `refine-issue` is a **command** (`commands/refine-issue.md`), not a skill; `decide-issue` is a **skill** (`skills/decide-issue/SKILL.md`)

### Tests

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_issue_manager.py` — pipeline integration tests to update; add a case where `decision_needed: true` triggers the decide-issue step between Phase 1 and Phase 2
- `scripts/tests/test_orchestrator.py` — parallel orchestrator tests to update; add conditional decide-issue invocation case
- `scripts/tests/test_refine_issue_command.py` — structural doc-wiring test file to model new tests after (uses `Path.read_text()` + `str.index()` assertions against markdown)
- `scripts/tests/test_decide_issue_skill.py` — **new file**; doc-wiring tests for `skills/decide-issue/SKILL.md` assertions; follow `test_refine_issue_command.py` pattern

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py` — add `TestIssueInfoDecisionNeeded` class (5-test pattern: default-None, set-value, in-to_dict, from_dict-restore, from_dict-missing); follow `TestIssueInfoSize` at line 1477 and `TestIssueInfoTestable` at line 1346 as the exact template; add integration test via `IssueParser.parse_file` with `decision_needed: true` frontmatter
- `scripts/tests/test_frontmatter.py` — add test to `TestUpdateFrontmatter` class verifying that passing `{"decision_needed": False}` via `update_frontmatter()` produces the correct serialized output (the function's type signature is `dict[str, str | int]`; confirm whether `bool` or `None` is accepted)
- `scripts/tests/test_parallel_types.py` — **will break**: `test_default_values:724`, `test_roundtrip_serialization:968`, `test_from_dict_defaults_for_missing_fields:953` do not assert `decide_command`; update all three; also add `test_get_decide_command_builds_correct_string` following `test_get_ready_command:776` pattern; if a `DECIDING` `WorkerStage` enum value is added, `test_enum_member_count:402` must change from `== 8` to `== 9`
- `scripts/tests/test_worker_pool.py` — **will break**: `test_process_issue_success_flow:1814`, `test_process_issue_cleans_leaked_files:1872`, `test_process_issue_captures_corrections:1926`, `test_process_issue_recovers_committed_leaks:1978` all use a two-call mock for `_run_claude_command`; inserting the decide-issue step makes it three calls when `decision_needed=True`; update to three-call dispatch and add: `test_process_issue_skips_decide_when_decision_not_needed` (confirms two calls when `decision_needed=None`) and `test_process_issue_runs_decide_when_decision_needed` (confirms three calls, second contains `decide-issue`)

### Documentation
- `docs/ARCHITECTURE.md` — pipeline diagram may need updating to show decide-issue between refine-issue and wire-issue
- `commands/refine-issue.md` — pipeline position section should reference `/ll:decide-issue` as next step after `decision_needed: true`
- `docs/reference/ISSUE_TEMPLATE.md:887` — `decision_needed` field already documented (added by ENH-1237)
- `docs/reference/COMMANDS.md` — add `/ll:decide-issue` entry in skill reference
- `.claude-plugin/plugin.json` — register `decide-issue` skill (verify auto-discovery or add explicit entry; plugin.json:20 uses `"skills": ["./skills"]` directory reference, so auto-discovery likely applies — no explicit entry needed)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:301-302` — add `decide_command` row to the parallel command templates table alongside `ready_command` and `manage_command`; also add `decision_needed` gate description near line 342 mirroring the `confidence_gate.enabled` description already there
- `docs/reference/API.md:551-573` — add `decision_needed: bool | None = None` to the `IssueInfo` field listing code block (after `testable` at line 570)
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:182-190` — add `decide-issue` as a step between `refine-issue` and `wire-issue` in the refinement pipeline numbered list

### Configuration
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json:287-326` — **must add** `decide_command` property to the `parallel` section between `manage_command:297` and `worktree_copy_files:302`; the section has `"additionalProperties": false` at line 326, so any user placing `decide_command` in their `ll-config.json` will get a schema validation failure until this is updated; default value: `"decide-issue {{issue_id}}"`

## Implementation Steps

1. Add `decision_needed: bool | None = None` field to `IssueInfo` dataclass (`scripts/little_loops/issue_parser.py:247`, after `testable`) and ensure `parse_frontmatter()` (`frontmatter.py:18-80`) surfaces it
2. Add `decide_command: str = "decide-issue {{issue_id}}"` and `get_decide_command()` to `ParallelConfig` (`scripts/little_loops/parallel/types.py:329-330`) alongside the existing `ready_command`/`manage_command` pattern
3. Create `skills/decide-issue/SKILL.md` using `skills/wire-issue/SKILL.md:1-50` as the structural template: frontmatter with `allowed-tools`, flag parsing (`--auto`, `--dry-run`), issue location via `ll-issues path`; parallel Agent spawns using `codebase-pattern-finder` subagent per option
4. Implement option extraction within the skill (three patterns from `commands/refine-issue.md:265-274`: numbered `1.`/`2.`, `### Option A/B`, `**Option A**/**Option B**`)
5. Implement scoring and selection: each option gets a `codebase-pattern-finder` Agent; score on consistency, simplicity, testability, risk; annotate selected option with `> **Selected:** ...` callout and `### Decision Rationale` subsection
6. Implement frontmatter update: follow `skills/confidence-check/SKILL.md:398-446` for inline `---` block replacement; set `decision_needed: false`; idempotency per `skills/format-issue/SKILL.md:163-175`
7. Add conditional `decide-issue` step to `scripts/little_loops/issue_manager.py:560-563` (between Phase 1 end and Phase 2 begin) gated on `info.decision_needed is True`
8. Add conditional `decide-issue` step to `scripts/little_loops/parallel/worker_pool.py:370-376` (between `set_worker_stage(IMPLEMENTING)` and `get_manage_command`) using `_run_claude_command()` with `self.parallel_config.get_decide_command(issue.issue_id)`
9. Add `decision_needed` gate to `skills/manage-issue/SKILL.md` at Phase 2 start (before plan creation, after the optional confidence-check at lines 118-129): HALT if `true`, bypass with `--force-implement` warning — follow the exact pattern of Phase 2.5 (`SKILL.md:157-191`)
10. Update `commands/refine-issue.md` pipeline position section to reference decide-issue after refine-issue
11. Write `scripts/tests/test_decide_issue_skill.py` with doc-wiring assertions following `test_refine_issue_command.py` pattern; update `test_issue_manager.py` and `test_orchestrator.py` for the new conditional step

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

12. Update `scripts/little_loops/issue_parser.py:261-314` — add `decision_needed` to `IssueInfo.to_dict()` return dict (alongside `testable:281`) and `from_dict()` constructor call (alongside `testable=data.get("testable"):311`); also update `parse_file():338-444` to extract `decision_needed` from frontmatter dict using the same pattern as `testable:401-409`
13. Update `scripts/little_loops/parallel/types.py:387-459` — add `decide_command` to `ParallelConfig.to_dict()` (alongside `manage_command:405-406`) and `from_dict()` (alongside `manage_command:443-446`); this ensures config roundtrips survive serialization
14. Update `config-schema.json:297` — add `decide_command` JSON Schema property to the `parallel` section alongside `ready_command`/`manage_command`; required because `additionalProperties: false` at line 326 will reject any user config that sets this field before the schema update
15. Update `docs/reference/CONFIGURATION.md:301-302` — add `decide_command` row to the parallel command templates table
16. Update `docs/reference/API.md:570` — add `decision_needed: bool | None = None` to the `IssueInfo` code block after `testable`
17. Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:182-190` — add `decide-issue` step between `refine-issue` and `wire-issue` in the refinement pipeline list
18. Update `scripts/tests/test_issue_parser.py` — add `TestIssueInfoDecisionNeeded` class following `TestIssueInfoTestable:1346` template (5 unit tests + 1 `parse_file` integration test)
19. Update `scripts/tests/test_frontmatter.py` — add test to `TestUpdateFrontmatter` for clearing `decision_needed` via `update_frontmatter()`
20. Update `scripts/tests/test_parallel_types.py` — add `decide_command` assertions to `test_default_values:724`, `test_roundtrip_serialization:968`, `test_from_dict_defaults_for_missing_fields:953`; add `test_get_decide_command_*` tests following `test_get_ready_command:776` pattern
21. Update `scripts/tests/test_worker_pool.py` — update four two-call mocks (`test_process_issue_success_flow:1814`, `test_process_issue_cleans_leaked_files:1872`, `test_process_issue_captures_corrections:1926`, `test_process_issue_recovers_committed_leaks:1978`) to three-call dispatch; add `test_process_issue_skips_decide_when_decision_not_needed` and `test_process_issue_runs_decide_when_decision_needed`

## Impact

- **Priority**: P3 - improves automated pipeline quality; not blocking but meaningfully increases unattended throughput
- **Effort**: Medium - new skill with multi-step logic; option parsing and scoring are novel
- **Risk**: Low - reads and writes to issue files only; no system-wide state changes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `pipeline`, `automation`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-04-21T22:00:00Z - `7bd492a7-b7a8-4c17-ae89-d8d259f2fbbc.jsonl`
- `/ll:wire-issue` - 2026-04-21T21:34:22 - `850e678a-e77e-4d8b-a5c7-8cdbdc0ea507.jsonl`
- `/ll:refine-issue` - 2026-04-21T21:29:27 - `a5bee7df-fa35-4a40-857e-d8f91d13f83a.jsonl`
- `/ll:capture-issue` - 2026-04-21T20:38:05Z - `6c8873df-f234-41f4-a242-d1cae3dc0002.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00Z - `237a06a8-dd6b-467a-b0ce-032255c420b6.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-21
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into

- FEAT-1238: Create /ll:decide-issue skill — core implementation
- FEAT-1239: Wire decide-issue into Python pipeline and manage-issue gate
- FEAT-1240: Tests and documentation for decide-issue

---

**Decomposed** | Created: 2026-04-21 | Priority: P3

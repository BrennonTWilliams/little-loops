---
discovered_date: 2026-04-07
discovered_by: issue-size-review
confidence_score: 95
outcome_confidence: 78
parent_issue: FEAT-988
testable: false
---

# FEAT-991: FSMExecutor Hook Dispatch — Skill and Docs Update

## Summary

Update the `review-loop` skill (reference.md and SKILL.md) to warn (not error) on unknown `action_type` values, and update the API reference and architecture documentation to reflect the extension system registries added by FEAT-987.

## Parent Issue

Decomposed from FEAT-988: FSMExecutor Hook Dispatch — Tests and Wiring Pass

## Use Case

A developer has authored a loop YAML that registers a contributed `action_type` of `webhook` via the FEAT-990 extended schema. When they run `/ll:review-loop` on this YAML, QC-3 previously emitted an error ("unknown action_type") that blocked the entire review. After this update, QC-3 emits a warning and lets the review complete. Separately, a developer implementing a contributed action plugin reads `docs/reference/API.md` and finds `ActionRunner` described as the extension dispatch interface — enabling them to write a working integration without needing to read executor source code.

## Current Behavior

- `review-loop/reference.md` QC-3 check treats unknown `action_type` values as errors — after the schema widening in FEAT-990, contributed types like `webhook` are valid and should only warn
- `review-loop/SKILL.md` QC-3 block mirrors the same hardcoded list (`prompt`, `shell`, `slash_command`, `mcp_tool`) and also errors on unknown values
- `docs/reference/API.md` ActionRunner Protocol section describes `ActionRunner` only as a testing/customization interface, missing its role as the contributed-actions runtime dispatch interface
- `docs/ARCHITECTURE.md` extension component table does not list the three new registries: `_contributed_actions`, `_contributed_evaluators`, `_interceptors`

## Expected Behavior

- QC-3 in `review-loop/reference.md` warns (not errors) on unknown `action_type` values (any value not in the built-in list)
- QC-3 block in `review-loop/SKILL.md:128–137` matches the updated `reference.md` behavior
- `docs/reference/API.md:4040–4053` ActionRunner Protocol section notes it serves as the contributed-actions runtime dispatch interface
- `docs/ARCHITECTURE.md:454–459` extension component table includes the three new extension sub-protocols

## Proposed Solution

### 1. review-loop Reference Update

**`skills/review-loop/reference.md:103–132`** — QC-3 `action_type` mismatch check:

Change behavior so that values not in `["prompt", "slash_command", "shell", "mcp_tool"]` produce a **warning** (not an error). These are potential contributed types after FEAT-990 widens the schema.

Example updated language:
> QC-3: If `action_type` is set to a value not in `["prompt", "slash_command", "shell", "mcp_tool"]`, treat it as a potential contributed type and warn rather than fail. Contributed action types are dispatched via the extension registry.

### 2. review-loop SKILL.md Update

**`skills/review-loop/SKILL.md:128–137`** — QC-3 block:

Apply the same warn-not-error change as `reference.md`. Both files document the same QC-3 check and must stay in sync. Note: QC-3 in SKILL.md is compact (lines 128–137 only) — the 128–198 range in the parent issue was the full QC section; QC-3 itself ends at line 137 where QC-4 begins.

### 3. API.md Update

**`docs/reference/API.md:4040–4053`** — `ActionRunner Protocol` section:

Add a note that `ActionRunner` also serves as the contributed-actions runtime dispatch interface used by the extension system (not just for testing/customization). Extension plugins register runners against custom `action_type` strings.

### 4. ARCHITECTURE.md Update

**`docs/ARCHITECTURE.md:454–459`** — extension component table:

The existing table uses three columns: `Component | File | Purpose`. Add the three extension sub-protocols introduced by FEAT-987 (defined in `extension.py:58–97`), which are the proper table entries since the table lists extension.py components:

| Component | File | Purpose |
|-----------|------|---------|
| `ActionProviderExtension` | `extension.py` | Protocol for plugins providing custom `ActionRunner` instances; populated into `FSMExecutor._contributed_actions` |
| `EvaluatorProviderExtension` | `extension.py` | Protocol for plugins providing custom evaluator callables; populated into `FSMExecutor._contributed_evaluators` |
| `InterceptorExtension` | `extension.py` | Protocol for plugins providing `before_route`/`after_route` hooks; stored in `FSMExecutor._interceptors` |

Note: `_contributed_actions`, `_contributed_evaluators`, and `_interceptors` are private instance attributes of `FSMExecutor` (`fsm/executor.py:154–157`) populated at wiring time — the extension sub-protocols above are their public-facing extension contracts.

## Implementation Steps

1. Update `skills/review-loop/reference.md:103–135` QC-3 to add a third sub-case: "Unknown `action_type` value (not in built-in list and not registered as contributed type)" → emit Warning
2. Update `skills/review-loop/SKILL.md:128–137` QC-3 block to add matching branch (lines 128–137 only; QC-4 starts at line 138)
3. Update `docs/reference/API.md:4040–4053` ActionRunner Protocol section to note contributed-actions dispatch role (`ActionRunner` is defined in `scripts/little_loops/fsm/runners.py`, re-exported via `fsm/__init__.py`)
4. Update `docs/ARCHITECTURE.md:454–459` extension component table — append 3 rows for `ActionProviderExtension`, `EvaluatorProviderExtension`, `InterceptorExtension` using the 3-column format (`Component | File | Purpose`)

## Integration Map

### Files to Modify

- `skills/review-loop/reference.md:103–132` — QC-3 update (warn not error on unknown action_type)
- `skills/review-loop/SKILL.md:128–198` — QC-3 block update (must match reference.md)
- `docs/reference/API.md:4040–4053` — ActionRunner Protocol section description update
- `docs/ARCHITECTURE.md:454–458` — extension component table; add three new registries

### Context Files (Read Before Editing)

- `scripts/little_loops/fsm/executor.py:154–157` — `_contributed_actions`, `_contributed_evaluators`, `_interceptors` registry declarations
- `scripts/little_loops/fsm/executor.py:446–456` — interceptor loop (`before_route`/`after_route`)
- `scripts/little_loops/fsm/executor.py:492–499` — contributed action dispatch
- `scripts/little_loops/fsm/executor.py:668–674` — contributed evaluator dispatch
- `scripts/little_loops/fsm/executor.py:760–773` — `_action_mode()` dispatch logic; built-in types: `mcp_tool`, `prompt`, `slash_command`, `shell`; contributed dispatch at line 768
- `scripts/little_loops/extension.py:58–97` — `InterceptorExtension` (lines 58–76), `ActionProviderExtension` (lines 78–86), `EvaluatorProviderExtension` (lines 89–97)
- `scripts/little_loops/fsm/runners.py` — `ActionRunner` Protocol definition (source of truth; re-exported via `fsm/__init__.py`)

### Dependent Files (Callers/Importers)

- N/A — documentation-only changes; no code modules import or call these files

### Similar Patterns

- `skills/review-loop/reference.md:418–427` — FA-6 is the only Error-severity check in the skill; all other checks use Warning or Suggestion — confirms that adding a Warning (not Error) for unknown `action_type` is consistent with the existing severity model
- Warning finding string convention: `"Warning: states.<name>: <message>."` — the severity prefix in the finding string must match the `**Severity**:` header declaration (see QC-2 at line 77, QC-4 at line 146)
- `scripts/little_loops/fsm/validation.py:469–503` — Python precedent for warn-not-raise on unknown values (unknown top-level YAML keys collected as `ValidationSeverity.WARNING`, not raised)

### Tests

- `scripts/tests/test_review_loop.py:278–311` — `TestReviewLoopQualityChecks` class has existing QC-3 test cases; consider adding a test for unknown `action_type` (e.g., `action_type: webhook`) asserting Warning severity (not Error) — though this is a documentation-only skill update, not Python code

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_review_loop.py` — new test `test_qc3_unknown_action_type_warns_not_errors` needed inside `TestReviewLoopQualityChecks`; follow the QC-4 Warning pattern at lines 315–328: assert `action_type not in {"prompt", "slash_command", "shell", "mcp_tool"}`, then note the skill should emit Warning (not Error); no existing QC-3 tests break — they assert on input discriminators only, not severity enum values

### Documentation

- Covered by Files to Modify above (all changes are in documentation and skill files)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:495–502` — line 495 states "Each state's action is executed in **one of four modes**" and the table at 497–502 enumerates only `shell`, `slash_command`, `prompt`, `mcp_tool` as a closed set; since the extension system (FEAT-987/990) allows contributed action types as a fifth dispatch category, this section needs a note that contributed types (dispatched via `_contributed_actions` registry) are a valid additional mode — avoids contradicting the QC-3 warn change

### Configuration

- N/A — no configuration files affected

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/guides/LOOPS_GUIDE.md:495–502` — amend the "one of four modes" statement and four-row table to note contributed action types as an additional dispatch mode (dispatched via the extension registry when `_contributed_actions` has a matching key)
6. Add `test_qc3_unknown_action_type_warns_not_errors` to `TestReviewLoopQualityChecks` in `scripts/tests/test_review_loop.py` — follow the QC-4 Warning pattern at lines 315–328; assert the state has an unrecognized `action_type` (not in the built-in set) and note the skill emits Warning

## Acceptance Criteria

- [ ] QC-3 in `review-loop/reference.md:103–135` adds a third sub-case: unknown `action_type` values (not in built-in set) emit Warning, not Error
- [ ] QC-3 block in `review-loop/SKILL.md:128–137` matches updated `reference.md` behavior (both files always kept in sync)
- [ ] `docs/reference/API.md:4040–4053` ActionRunner Protocol section notes it is the contributed-actions runtime dispatch interface, not just a testing hook
- [ ] `docs/ARCHITECTURE.md:454–459` extension component table includes rows for `ActionProviderExtension`, `EvaluatorProviderExtension`, `InterceptorExtension` using the 3-column format

## Impact

- **Priority**: P4 - Strategic
- **Effort**: Small — documentation-only edits in 4 files
- **Risk**: Very Low — docs and skill updates; no code changes
- **Breaking Change**: No
- **Depends On**: FEAT-990 (schema widening makes the warn-not-error change accurate)

## Labels

`feature`, `fsm`, `extension-hooks`, `documentation`, `decomposed`

## Status

**Completed** | Created: 2026-04-07 | Completed: 2026-04-07 | Priority: P4

## Resolution

All 6 implementation steps completed:

1. `skills/review-loop/reference.md` QC-3: Added third sub-case — unknown `action_type` (not in built-in list) emits Warning with note about contributed types and extension registry dispatch
2. `skills/review-loop/SKILL.md` QC-3 block: Added matching Warning branch for unknown/contributed `action_type` values; do NOT emit Error
3. `docs/reference/API.md` ActionRunner Protocol section: Added note that `ActionRunner` is the contributed-actions runtime dispatch interface, used by `ActionProviderExtension.provided_actions()` and `FSMExecutor._contributed_actions`
4. `docs/ARCHITECTURE.md` extension component table: Added 3 new rows for `InterceptorExtension`, `ActionProviderExtension`, and `EvaluatorProviderExtension` with file and purpose columns
5. `docs/guides/LOOPS_GUIDE.md` action types section: Changed "one of four modes" to "one of four built-in modes" and added a fifth row for contributed types dispatched via extension registry
6. `scripts/tests/test_review_loop.py`: Added `test_qc3_unknown_action_type_warns_not_errors` to `TestReviewLoopQualityChecks` — asserts `webhook` is not in the built-in set and documents expected Warning severity

## Session Log
- `/ll:ready-issue` - 2026-04-08T04:15:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/89440067-8c9e-4bf6-8a22-c4a45deb96db.jsonl`
- `/ll:confidence-check` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8ec0a998-d31f-417c-bb86-14e5d81ef7e4.jsonl`
- `/ll:wire-issue` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/memory/MEMORY.md`
- `/ll:refine-issue` - 2026-04-08T04:02:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2f57d33-23e4-4e0b-82c9-e4dc648d0215.jsonl`
- `/ll:format-issue` - 2026-04-08T03:57:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b491a50e-c2ec-405d-8a6a-8a0de63369ff.jsonl`
- `/ll:issue-size-review` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0b5b8fb2-d663-482d-be59-6aa37de8e735.jsonl`

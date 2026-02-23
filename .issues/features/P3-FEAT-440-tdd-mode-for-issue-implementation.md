---
discovered_date: "2026-02-18"
discovered_by: capture-issue
confidence_score: 92
---

# FEAT-440: TDD Mode for Issue Implementation

## Summary

Add a feature toggle in `ll-config.json` to enable TDD (Test-Driven Development) mode for issue implementation. When enabled, the implementation flow changes from the current Research > Plan > Implement > Verify > Complete to a test-first approach: Research > Plan > Write Tests (expect failures) > Implement (make tests pass) > Verify > Complete. This affects all automated processing tools: `ll-auto`, `ll-parallel`, and `ll-sprint`.

## Current Behavior

The `manage-issue` skill follows a fixed implementation flow:
1. Phase 1: Find Issue
2. Phase 1.5: Deep Research
3. Phase 2: Create Implementation Plan
4. Phase 3: Implement (code first)
5. Phase 4: Verify (tests run after implementation)
6. Phase 4.5: Integration Review
7. Phase 5: Complete

Tests are always written alongside or after implementation code. There is no option to enforce a test-first workflow.

## Expected Behavior

A `tdd_mode` toggle in `ll-config.json` enables TDD workflow:
1. Phase 1: Find Issue
2. Phase 1.5: Deep Research
3. Phase 2: Create Implementation Plan (includes test plan)
4. **Phase 3a: Write Tests** (Red - tests must fail against current code)
5. **Phase 3b: Implement** (Green - make failing tests pass)
6. Phase 4: Verify (all tests pass, lint, types)
7. Phase 4.5: Integration Review
8. Phase 5: Complete

When disabled (default), the current flow is unchanged.

## Motivation

TDD produces better-tested code with higher confidence in correctness. For automated issue processing (`ll-auto`, `ll-parallel`, `ll-sprint`), TDD mode ensures that acceptance criteria are codified as tests before implementation begins, preventing issues where implementation passes verification but doesn't fully address the issue requirements. This is particularly valuable for bug fixes (test reproduces the bug first) and features with clear acceptance criteria.

## Use Case

A developer configures `"tdd_mode": true` in their `ll-config.json`. When `ll-parallel` processes a batch of issues, each Claude session invokes `manage-issue` which detects the TDD toggle. Instead of jumping straight to implementation, the session first writes failing tests based on the plan's success criteria and the issue's acceptance criteria. It verifies the tests fail (Red phase). Then it implements the solution, verifying that the previously-failing tests now pass (Green phase). The standard verification phase then runs as usual.

## Acceptance Criteria

- [ ] New `tdd_mode` boolean toggle in `ll-config.json` (default: `false`)
- [ ] When enabled, `manage-issue` inserts a "Write Tests" phase before implementation
- [ ] The test-writing phase produces tests that fail against the current codebase (Red)
- [ ] The implementation phase makes those tests pass (Green)
- [ ] Standard verification (Phase 4) still runs as a final check
- [ ] `ll-auto`, `ll-parallel`, and `ll-sprint` all respect the toggle (they invoke `manage-issue` which reads config)
- [ ] When disabled, behavior is identical to current flow (no regression)
- [x] Design decision resolved: conditional logic in `manage-issue` (Approach A), `tdd_mode` under `commands` config section

## API/Interface

### Config Schema Addition

`tdd_mode` is added to the existing `commands` section alongside `pre_implement` and `post_implement`:

```json
{
  "commands": {
    "tdd_mode": false
  }
}
```

## Proposed Solution

**Decision**: Conditional logic in `manage-issue` (Approach A).

When `commands.tdd_mode` is `true`, Phase 3 splits into two sub-phases within the existing skill:

- **Phase 3a: Write Tests (Red)** — Write tests derived from the plan's success criteria. Run the test command and assert failure against the current codebase before any implementation code is written.
- **Phase 3b: Implement (Green)** — Write implementation code until the Phase 3a tests pass. Standard implementation guidelines apply.

All existing flags (`--resume`, `--gates`, `--quick`, `--plan-only`, context handoff) apply to both sub-phases without modification. The plan template gains a "Test Plan" subsection specifying which tests to write in Phase 3a.

The CLI tools (`ll-auto`, `ll-parallel`, `ll-sprint`) require no changes — they invoke `manage-issue` which reads `commands.tdd_mode` from config directly.

## Integration Map

### Files to Modify
- `skills/manage-issue/SKILL.md` - Add Phase 3a/3b conditional logic under `commands.tdd_mode`
- `skills/manage-issue/templates.md` - Add "Test Plan" subsection to the plan template
- `scripts/little_loops/config.py` - Add `tdd_mode: bool = False` to `CommandsConfig`
- `config-schema.json` - Add `tdd_mode` boolean property to `commands` schema section

### Dependent Files (No Changes Required)
- `scripts/little_loops/subprocess_utils.py` - No changes; CLI tools invoke `manage-issue` unchanged
- `scripts/little_loops/cli/auto.py` - No changes
- `scripts/little_loops/cli/parallel.py` - No changes
- `scripts/little_loops/cli/sprint.py` - No changes

### Similar Patterns
- `--gates` flag in `manage-issue` - conditional phase behavior based on config/flags
- `commands.pre_implement` / `commands.post_implement` - existing hook points around implementation

### Tests
- `scripts/tests/test_config.py` - Add tests for `tdd_mode` field parsing and default value

### Documentation
- `README.md` - Document `tdd_mode` config option
- `docs/API.md` - Update config reference

### Configuration
- `.claude/ll-config.json` - New toggle location
- `config-schema.json` - Schema validation for new field

## Implementation Steps

1. Add `tdd_mode: bool = False` to `CommandsConfig` in `config.py` and `config-schema.json`
2. Add Phase 3a (Write Tests / Red) and Phase 3b (Implement / Green) conditional blocks to `skills/manage-issue/SKILL.md`, gated on `{{config.commands.tdd_mode}}`
3. Add "Test Plan" subsection to the plan template in `skills/manage-issue/templates.md`
4. Add Red-phase verification step: run `{{config.project.test_cmd}}` after writing tests and assert non-zero exit before proceeding to Phase 3b
5. Add tests for `tdd_mode` config field parsing to `scripts/tests/test_config.py`
6. Update `README.md` and `docs/API.md` to document the new config option

## Impact

- **Priority**: P3 - Valuable workflow improvement but not blocking any current work
- **Effort**: Medium - Requires modifying core skill logic and config schema
- **Risk**: Low - Feature toggle defaults to off, no change to existing behavior when disabled
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `captured`, `workflow`, `tdd`, `manage-issue`

## Session Log
- `/ll:capture-issue` - 2026-02-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dde3da3f-b9fb-4092-9940-a33135c3b17f.jsonl`
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6952751c-b227-418e-a8d3-d419ea5b0bf6.jsonl`

---

## Status

**Open** | Created: 2026-02-18 | Priority: P3

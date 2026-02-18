---
discovered_date: "2026-02-18"
discovered_by: capture-issue
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
- [ ] Design decision resolved: either conditional logic in `manage-issue` or a separate TDD skill

## API/Interface

### Config Schema Addition

```json
{
  "commands": {
    "tdd_mode": false
  }
}
```

Or as a new top-level workflow section:

```json
{
  "workflow": {
    "tdd_mode": false
  }
}
```

### Skill Interface (if separate skill approach)

```
/ll:manage-issue-tdd [type] [action] [issue-id] [flags]
```

Or the existing `manage-issue` conditionally switches behavior based on config.

## Proposed Solution

Two approaches to evaluate:

### Approach A: Conditional Logic in manage-issue

Add TDD-aware phase logic to the existing `manage-issue` skill. When `tdd_mode` is enabled in config, Phase 3 splits into Phase 3a (Write Tests) and Phase 3b (Implement). The plan template gains a "Test Plan" section that specifies which tests to write first.

- **Pros**: Single skill to maintain, leverages all existing infrastructure (flags, gates, resume, handoff)
- **Cons**: Adds complexity to an already large skill

### Approach B: Separate TDD Skill

Create a `manage-issue-tdd` skill that implements the TDD flow. The CLI tools (`ll-auto`, `ll-parallel`, `ll-sprint`) check the config toggle and invoke the appropriate skill via `manage_command` config.

- **Pros**: Clean separation, TDD skill can evolve independently
- **Cons**: Code duplication across skills, two skills to maintain in sync

**Recommendation**: Evaluate both approaches during implementation planning. Approach A is likely simpler if the phase insertion is clean; Approach B is better if TDD requires fundamentally different plan templates and verification logic.

## Integration Map

### Files to Modify
- `skills/manage-issue/SKILL.md` - Add TDD phase logic or branch to TDD skill
- `skills/manage-issue/templates.md` - Add TDD plan template with test plan section
- `scripts/little_loops/config.py` - Add `tdd_mode` to `CommandsConfig` or new `WorkflowConfig`
- `config-schema.json` - Add `tdd_mode` property to schema

### Dependent Files (Callers/Importers)
- `scripts/little_loops/subprocess_utils.py` - Constructs Claude CLI commands (may need to pass different skill)
- `scripts/little_loops/cli.py` - CLI entry points for `ll-auto`, `ll-parallel`, `ll-sprint`

### Similar Patterns
- `--gates` flag in `manage-issue` - conditional phase behavior based on config/flags
- `commands.pre_implement` / `commands.post_implement` - existing hook points around implementation

### Tests
- `scripts/tests/test_config.py` - Add tests for new config field parsing
- New test for TDD phase ordering if Approach B (new skill file)

### Documentation
- `README.md` - Document `tdd_mode` config option
- `docs/API.md` - Update config reference

### Configuration
- `.claude/ll-config.json` - New toggle location
- `config-schema.json` - Schema validation for new field

## Implementation Steps

1. Add `tdd_mode` field to config dataclass and schema
2. Design and implement TDD phase logic (Approach A or B)
3. Create TDD-specific plan template with test plan section
4. Add Red/Green verification steps to the TDD phases
5. Ensure CLI tools (`ll-auto`, `ll-parallel`, `ll-sprint`) respect the toggle
6. Add tests for config parsing and phase ordering
7. Update documentation

## Impact

- **Priority**: P3 - Valuable workflow improvement but not blocking any current work
- **Effort**: Medium - Requires modifying core skill logic and config schema, plus design decision on approach
- **Risk**: Low - Feature toggle defaults to off, no change to existing behavior when disabled
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `captured`, `workflow`, `tdd`, `manage-issue`

## Session Log
- `/ll:capture-issue` - 2026-02-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dde3da3f-b9fb-4092-9940-a33135c3b17f.jsonl`

---

## Status

**Open** | Created: 2026-02-18 | Priority: P3

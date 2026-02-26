---
discovered_date: "2026-02-18"
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 63
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

- [x] New `tdd_mode` boolean toggle in `ll-config.json` (default: `false`)
- [x] When enabled, `manage-issue` inserts a "Write Tests" phase before implementation
- [x] The test-writing phase produces tests that fail against the current codebase (Red)
- [x] Red-phase validation uses exit-code + output scan: assert non-zero exit AND scan output for `FAILED` markers (not `ERROR`/`ImportError`/`SyntaxError`)
- [x] The implementation phase makes those tests pass (Green)
- [x] Standard verification (Phase 4) still runs as a final check
- [x] `ll-auto`, `ll-parallel`, and `ll-sprint` all respect the toggle (they invoke `manage-issue` which reads config)
- [x] When disabled, behavior is identical to current flow (no regression)
- [x] Design decision resolved: conditional logic in `manage-issue` (Approach A), `tdd_mode` under `commands` config section
- [x] Design decision resolved: Red-phase validation via exit-code + output scan (not exit-code only or two-stage)

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

All existing flags (`--resume`, `--gates`, `--quick`, `--plan-only`, context handoff) apply to both sub-phases without modification. The plan template gains a "Phase 0: Write Tests (Red)" sub-phase inside the Implementation Phases section, specifying which tests to write in Phase 3a.

The CLI tools (`ll-auto`, `ll-parallel`, `ll-sprint`) require no changes — they invoke `manage-issue` which reads `commands.tdd_mode` from config directly.

### Red-Phase Verification Design

The Red phase must distinguish valid test failures (assertions fail because code isn't implemented yet) from invalid failures (import errors, syntax errors, wrong test targets). The validation uses **exit-code + output scan**:

1. Run `{{config.project.test_cmd}}` on the newly written test files
2. Assert **non-zero exit code** (tests must fail)
3. Scan test output for failure markers:
   - **Valid Red**: Output contains `FAILED` (pytest assertion failures) — proceed to Phase 3b
   - **Invalid Red**: Output contains `ERROR`, `ImportError`, `SyntaxError`, `ModuleNotFoundError`, or collection errors — halt and fix test code before proceeding
4. If tests **pass** (zero exit code): halt — tests should not pass against unimplemented code

This follows the same pass/fail interpretation pattern used in Phase 4 (`SKILL.md:289-313`) but inverts the success condition and adds output classification.

## Integration Map

### Files to Modify
- `skills/manage-issue/SKILL.md:189-285` — Add Phase 3a/3b conditional logic gated on `config.commands.tdd_mode`, following the Phase 2.5 confidence gate skip-condition pattern at lines 154-186
- `skills/manage-issue/templates.md:128-168` — Add "Phase 0: Write Tests (Red)" sub-phase inside `## Implementation Phases` section, following the existing phase/success-criteria structure
- `scripts/little_loops/config.py:270-287` — Add `tdd_mode: bool = False` field to `CommandsConfig` dataclass and `from_dict()` method
- `scripts/little_loops/config.py:689-697` — Add `"tdd_mode": self._commands.tdd_mode` to `to_dict()` commands dict (required for `{{config.commands.tdd_mode}}` template interpolation via `resolve_variable()` at line 724)
- `config-schema.json:228-266` — Add `tdd_mode` boolean property to `commands` section (note: `additionalProperties: false` at line 266 blocks unknown keys until explicitly added)
- `skills/configure/areas.md:311-358` — Add `tdd_mode` to the commands config area display so `/ll:configure` shows it
- `skills/init/interactive.md:852-857` — Add TDD mode option to init wizard impl-hooks mapping

### Dependent Files (No Changes Required)
- `scripts/little_loops/subprocess_utils.py` — CLI tools construct `"/ll:manage-issue {type} {action} {issue_id}"` and pass to Claude subprocess; no config forwarding needed
- `scripts/little_loops/issue_manager.py:512` — Builds command string `f"/ll:manage-issue {type_name} {action} {issue_arg}"`; no flags appended
- `scripts/little_loops/parallel/types.py:359-375` — Template substitution on `manage_command`; no tdd_mode injection
- `scripts/little_loops/cli/auto.py` — Delegates to `process_issue_inplace()` unchanged
- `scripts/little_loops/cli/parallel.py` — Delegates to `ParallelOrchestrator` unchanged
- `scripts/little_loops/cli/sprint/run.py` — Uses same two paths (inplace / parallel) unchanged

### Similar Patterns
- **Phase 2.5 Confidence Gate** (`SKILL.md:154-186`) — Closest pattern: config boolean (`confidence_gate.enabled`) gates entire phase execution with skip-condition header. Model Phase 3a skip-condition after this.
- **`--gates` flag** (`SKILL.md:255-271`) — Conditional phase gate pauses; same prose-level conditional instruction style
- **`ConfidenceGateConfig`** (`config.py:252-267`) — Closest dataclass pattern: `enabled: bool = False` with `from_dict()` using `data.get("enabled", False)`
- **`p0_sequential`** (`config.py:210-211`) — Flat boolean field pattern on a config dataclass
- `commands.pre_implement` / `commands.post_implement` (`config.py:272-273`) — **Note: these are dead code** — defined in config but no skill currently invokes them. Do not model after these.

### Tests
- `scripts/tests/test_config.py:241-258` — Add `tdd_mode` assertions to existing `TestCommandsConfig.test_from_dict_with_all_fields()` and `test_from_dict_with_defaults()`, following the same pattern used for `pre_implement`, `confidence_gate`, etc.

### Documentation
- `docs/reference/CONFIGURATION.md` — Document `tdd_mode` config option in commands section
- `docs/reference/API.md` — Update `CommandsConfig` reference
- `README.md` — Document `tdd_mode` config option

### Configuration
- `.claude/ll-config.json` — New toggle location under `commands`
- `config-schema.json:223-262` — Schema validation for new field

## Implementation Steps

### Phase 1: Config Infrastructure
1. Add `tdd_mode: bool = False` field to `CommandsConfig` dataclass at `config.py:270` (after `confidence_gate`)
2. Add `tdd_mode=data.get("tdd_mode", False)` to `CommandsConfig.from_dict()` at `config.py:282`
3. Add `"tdd_mode": self._commands.tdd_mode` to `BRConfig.to_dict()` commands dict at `config.py:689`
4. Add `"tdd_mode": { "type": "boolean", "description": "Enable TDD mode (test-first) for manage-issue", "default": false }` to `config-schema.json` commands properties (before the closing `additionalProperties: false` at line 266)
5. Add `tdd_mode` assertions to `TestCommandsConfig` tests at `test_config.py:231-258`: assert default is `False` and explicit `True` is parsed

### Phase 2: Plan Template
6. Add "Phase 0: Write Tests (Red)" sub-phase to `## Implementation Phases` in `templates.md:128`, following the existing `#### Changes Required` / `#### Success Criteria` structure. Include test file paths, test function names, and what each test asserts.

### Phase 3: Skill Logic
7. Add Phase 3a conditional block to `SKILL.md` after Phase 2.5 (line ~186), gated with: `**Skip this phase if**: config.commands.tdd_mode is false (default).` — following the confidence gate skip-condition pattern
8. Phase 3a body: write tests from the plan's "Phase 0: Write Tests (Red)" subsection, then run `{{config.project.test_cmd}}` on the new test files
9. Add Red-phase validation: assert non-zero exit AND scan output — `FAILED` markers = valid Red (proceed), `ERROR`/`ImportError`/`SyntaxError` = invalid Red (halt and fix)
10. Add Phase 3b: standard implementation phase (existing Phase 3 content) that runs when `tdd_mode` is true, with the additional instruction to make Phase 3a tests pass

### Phase 4: Surface in Configure/Init
11. Add `tdd_mode` to `skills/configure/areas.md:311-358` commands config area:
    - Add `tdd_mode: {{config.commands.tdd_mode}}` to the Current Values display block (after `post_implement`)
    - Add question following the confidence gate boolean pattern:
      ```yaml
      - header: "TDD"
        question: "Enable TDD mode (test-first) for manage-issue?"
        options:
          - label: "{{current tdd_mode}} (keep)"
            description: "Keep current setting"
          - label: "true"
            description: "Yes, write tests before implementation (Red/Green)"
          - label: "false"
            description: "No, standard implementation flow (default)"
        multiSelect: false
      ```
12. Add TDD mode option to `skills/init/interactive.md:852-857` after the Impl Hooks question:
    - Add question following the impl-hooks mapping pattern:
      ```yaml
      - header: "TDD Mode"
        question: "Enable test-first (TDD) mode for issue implementation?"
        options:
          - label: "Skip (Recommended)"
            description: "Standard implementation flow — tests alongside code"
          - label: "Enable TDD"
            description: "Write failing tests first, then implement to pass them"
        multiSelect: false
      ```
    - Mapping: "Skip" → omit `commands.tdd_mode` (defaults to `false`); "Enable TDD" → `{ "commands": { "tdd_mode": true } }`

### Phase 5: Documentation & Verification
13. Update `docs/reference/CONFIGURATION.md`, `docs/reference/API.md`, and `README.md` to document the new config option
14. Run `python -m pytest scripts/tests/test_config.py -v` to verify config tests pass

## Impact

- **Priority**: P4 - Valuable workflow improvement but not blocking any current work
- **Effort**: Medium - 7 files to modify across config, skill, template, configure, and init
- **Risk**: Low - Feature toggle defaults to off, no change to existing behavior when disabled
- **Breaking Change**: No

## Related Key Documentation

- `docs/reference/CONFIGURATION.md` — Config reference (documents `pre_implement`, `post_implement`, `confidence_gate`)
- `docs/reference/API.md` — API reference covering `CommandsConfig`, `ConfidenceGateConfig`
- `.issues/completed/P3-ENH-447-confidence-score-blocking-gate-for-manage-issue.md` — Added confidence gate (closest prior art for config-gated phase logic)

## Labels

`feature`, `captured`, `workflow`, `tdd`, `manage-issue`

## Resolution

**Action**: Implemented
**Date**: 2026-02-25

### Changes Made
- `scripts/little_loops/config.py` — Added `tdd_mode: bool = False` to `CommandsConfig`, `from_dict()`, and `to_dict()`
- `config-schema.json` — Added `tdd_mode` boolean property to `commands` schema
- `scripts/tests/test_config.py` — Added `tdd_mode` assertions to both `TestCommandsConfig` test methods
- `skills/manage-issue/SKILL.md` — Added Phase 3a (Write Tests — Red) with skip-condition and Red-phase validation, updated Phase 3 heading for TDD mode
- `skills/manage-issue/templates.md` — Added Phase 0: Write Tests (Red) to plan template with TDD mode guidance
- `skills/configure/areas.md` — Added `tdd_mode` to commands area display and configuration questions
- `skills/init/interactive.md` — Added TDD Mode question and mapping to init wizard
- `docs/reference/CONFIGURATION.md` — Documented `tdd_mode` config option with description
- `docs/reference/API.md` — Updated `CommandsConfig` description to include `tdd_mode`

### Verification
- 2954 tests passed (0 failures)
- Type check clean on `config.py`
- No new lint issues introduced

## Session Log
- `/ll:capture-issue` - 2026-02-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dde3da3f-b9fb-4092-9940-a33135c3b17f.jsonl`
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6952751c-b227-418e-a8d3-d419ea5b0bf6.jsonl`
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Issue is well-specified with concrete config schema and skill integration points; remaining gap (red-phase verification design) is a design decision per tradeoff review, not a codebase research gap
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/706d5ec0-3b91-4a6f-9224-c258b13baf39.jsonl` - Resolved Red-phase verification design (exit-code + output scan), added 3 missing Integration Map files (to_dict, configure, init), enriched all sections with file:line references
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/268e71aa-e103-4890-965e-ad86820481b2.jsonl` - Verified all 9 line references still accurate; added concrete question YAML for configure/areas.md and init/interactive.md TDD entries

---

## Status

**Completed** | Created: 2026-02-18 | Completed: 2026-02-25 | Priority: P4

---

## Tradeoff Review Note

**Reviewed**: 2026-02-24 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | MEDIUM |
| Complexity added | MEDIUM |
| Technical debt risk | MEDIUM |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first - The red-phase verification mechanism is underspecified. The issue needs to define how to distinguish valid test failures (tests for unimplemented code) from invalid failures (import errors, syntax errors, wrong test targets). Additionally, the value proposition depends on LLM agents reliably executing a test-first discipline, which is unproven in this system. Consider adding concrete success/failure criteria for red-phase assertion and a small proof-of-concept before full implementation.

## Blocks

- ENH-459

## Blocked By

- FEAT-441

- ENH-498
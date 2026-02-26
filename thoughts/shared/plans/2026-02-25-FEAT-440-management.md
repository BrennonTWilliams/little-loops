# Implementation Plan: FEAT-440 — TDD Mode for Issue Implementation

## Issue Summary

Add `commands.tdd_mode` boolean toggle (default: `false`) to `ll-config.json`. When enabled, `manage-issue` splits Phase 3 into Phase 3a (Write Tests — Red) and Phase 3b (Implement — Green), enforcing a test-first workflow.

## Approach

Conditional logic in `manage-issue` SKILL.md gated on `config.commands.tdd_mode`, following the Phase 2.5 confidence gate skip-condition pattern. The config infrastructure follows the existing `CommandsConfig` flat boolean pattern (like `p0_sequential` in `ParallelAutomationConfig`).

## Code Reuse & Integration

- **Reusable existing code**: `CommandsConfig` dataclass pattern (`config.py:270-287`), Phase 2.5 skip-condition pattern (`SKILL.md:154-186`)
- **Patterns to follow**: `p0_sequential` flat boolean field, `confidence_gate.enabled` boolean question in configure/areas.md, Round 3a multiSelect feature selection in init/interactive.md
- **New code justification**: Phase 3a/3b conditional prose and Red-phase validation logic are genuinely new (no existing TDD workflow exists)

## Implementation Phases

### Phase 1: Config Infrastructure

#### Overview
Add `tdd_mode: bool = False` to `CommandsConfig`, its `from_dict()`, `to_dict()`, the JSON schema, and tests.

#### Changes Required

**File**: `scripts/little_loops/config.py:277`
**Changes**: Add `tdd_mode` field after `confidence_gate`, add to `from_dict()` and `to_dict()`

```python
# After line 277 (confidence_gate field):
    tdd_mode: bool = False

# In from_dict() after line 286:
            tdd_mode=data.get("tdd_mode", False),

# In to_dict() after line 696 (confidence_gate closing brace):
                "tdd_mode": self._commands.tdd_mode,
```

**File**: `config-schema.json:264`
**Changes**: Add `tdd_mode` property to `commands.properties` before `additionalProperties: false`

```json
        "tdd_mode": {
          "type": "boolean",
          "description": "Enable TDD mode: write failing tests before implementation in manage-issue",
          "default": false
        }
```

**File**: `scripts/tests/test_config.py:241-268`
**Changes**: Add `tdd_mode` to both test methods

```python
# In test_from_dict_with_all_fields, add to data dict:
            "tdd_mode": True,
# Add assertion:
        assert config.tdd_mode is True

# In test_from_dict_with_defaults, add assertion:
        assert config.tdd_mode is False
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_config.py::TestCommandsConfig -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/config.py`

---

### Phase 2: Plan Template Update

#### Overview
Add "Phase 0: Write Tests (Red)" sub-phase to the Enhanced Plan Template so generated plans include a test-writing section when TDD mode is active.

#### Changes Required

**File**: `skills/manage-issue/templates.md:128`
**Changes**: Add TDD phase guidance inside `## Implementation Phases` section, after the section header and before `### Phase 1:`. This is a conditional sub-phase that only appears in generated plans when `config.commands.tdd_mode` is `true`.

```markdown
> **TDD Mode** (when `config.commands.tdd_mode` is `true`): Include "Phase 0: Write Tests (Red)" as the first implementation phase. This phase writes failing tests derived from the issue's acceptance criteria and the plan's success criteria. The tests must fail against the current codebase (Red). Subsequent phases then implement code to make these tests pass (Green).

### Phase 0: Write Tests (Red) *(TDD mode only)*

#### Overview
Write tests that encode the issue's acceptance criteria. These tests must FAIL against the current codebase.

#### Test Files
- [List specific test files to create/modify]
- [List test function names and what each asserts]

#### Red Validation
After writing tests, run: `{{config.project.test_cmd}} [test_files] -v`
- **Expected**: Non-zero exit code with `FAILED` markers (assertion failures)
- **Invalid**: `ERROR`, `ImportError`, `SyntaxError`, `ModuleNotFoundError` — fix test code before proceeding

#### Success Criteria

**Automated Verification**:
- [ ] Tests fail with assertion errors (not import/syntax errors): `{{config.project.test_cmd}} [test_files] -v` returns non-zero exit
- [ ] Test output contains `FAILED` (not `ERROR`/`ImportError`/`SyntaxError`)
```

---

### Phase 3: Skill Logic — Phase 3a/3b in SKILL.md

#### Overview
Add conditional TDD phases to `manage-issue` SKILL.md between Phase 2.5 and the existing Phase 3 content. When `config.commands.tdd_mode` is `true`, Phase 3 splits into 3a (Write Tests) and 3b (Implement).

#### Changes Required

**File**: `skills/manage-issue/SKILL.md`
**Location**: After Phase 2.5 section ending at line 187, before `## Phase 3: Implement` at line 190

**Changes**: Insert a new `## Phase 3a: Write Tests — Red (TDD Mode)` section following the Phase 2.5 skip-condition pattern, then modify Phase 3 heading to clarify it becomes Phase 3b when TDD mode is active.

New section to insert after the `---` separator at line 188:

```markdown
## Phase 3a: Write Tests — Red (TDD Mode)

**Skip this phase if**: `config.commands.tdd_mode` is `false` (default), or action is `verify` or `plan`.

When `config.commands.tdd_mode` is `true`, write tests BEFORE implementation:

1. **Read the plan's "Phase 0: Write Tests (Red)" section** for test specifications
2. **Write test files** based on the issue's acceptance criteria and the plan's test specifications
3. **Run tests** against the current (unmodified) codebase:

```bash
{{config.project.test_cmd}} [newly_written_test_files] -v
```

4. **Validate Red phase** — check test output:

```
RUN {{config.project.test_cmd}} on new test files

IF exit code is 0 (tests pass):
  HALT: "✗ Red phase failed: tests pass against current code.
         Tests should fail before implementation. Review test logic."
  Fix tests to properly assert expected behavior, then re-run.

IF exit code is non-zero:
  SCAN test output:
    IF output contains "FAILED" (pytest assertion failures):
      LOG: "✓ Red phase passed: tests fail with assertion errors as expected."
      PROCEED to Phase 3b (Implementation)

    IF output contains "ERROR", "ImportError", "SyntaxError", or "ModuleNotFoundError":
      HALT: "✗ Red phase invalid: tests have structural errors, not assertion failures.
             Fix import paths, syntax, or test setup before proceeding."
      Fix test code and re-run validation.
```

5. **Commit test files** (optional, if `--gates` flag is set and user approves)

> **Phase Gate** (requires `--gates` flag): After Red validation passes, pause to show test files written and validation results before proceeding to implementation.

---
```

Then update the Phase 3 heading and add a note:

```markdown
## Phase 3 (3b in TDD Mode): Implement
```

Add after the Phase 3 heading (line 190), before "### Resuming Work":

```markdown
> **TDD Mode note**: When `config.commands.tdd_mode` is `true`, this phase is Phase 3b. The goal is to make the Phase 3a tests pass (Green). After implementation, verify that all Phase 3a tests now pass before proceeding to Phase 4.
```

#### Success Criteria

**Manual Verification**:
- [ ] Phase 3a section follows the Phase 2.5 skip-condition pattern
- [ ] Red-phase validation pseudocode covers all three outcomes (pass, valid fail, invalid fail)
- [ ] Phase 3 heading updated to note TDD mode relationship

---

### Phase 4: Configure & Init Integration

#### Overview
Surface the `tdd_mode` toggle in `/ll:configure` and `/ll:init` so users can discover and set it.

#### Changes Required

**File**: `skills/configure/areas.md:319-320`
**Changes**: Add `tdd_mode` to Current Values display and add a question to Round 1

In Current Values block, after `threshold` line:
```
  tdd_mode:         {{config.commands.tdd_mode}}
```

Change `### Round 1 (3 questions)` to `### Round 1 (4 questions)` and add question after the Threshold question:

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

**File**: `skills/init/interactive.md:857`
**Changes**: Add TDD mode question after the Impl Hooks mapping block

```markdown
  - header: "TDD Mode"
    question: "Enable test-first (TDD) mode for issue implementation?"
    options:
      - label: "Skip (Recommended)"
        description: "Standard implementation flow — tests alongside code"
      - label: "Enable TDD"
        description: "Write failing tests first, then implement to pass them"
    multiSelect: false

**TDD Mode mapping:**
- "Skip" → omit `commands.tdd_mode` (defaults to `false`)
- "Enable TDD" → `{ "commands": { "tdd_mode": true } }`
```

#### Success Criteria

**Manual Verification**:
- [ ] `tdd_mode` appears in configure commands area display
- [ ] TDD question follows existing boolean question pattern
- [ ] Init wizard TDD option follows Impl Hooks mapping pattern

---

### Phase 5: Documentation

#### Overview
Update configuration reference, API reference, and README to document the new toggle.

#### Changes Required

**File**: `docs/reference/CONFIGURATION.md`
**Changes**: Add `tdd_mode` row to commands table and example JSON, add description paragraph

**File**: `docs/reference/API.md:88`
**Changes**: Update `CommandsConfig` description to mention `tdd_mode`

**File**: `README.md` — No changes needed (README doesn't list individual config options)

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- `test_from_dict_with_all_fields`: verify `tdd_mode=True` parsed correctly
- `test_from_dict_with_defaults`: verify `tdd_mode` defaults to `False`

### Integration Tests
- No additional integration tests needed — the feature is config + prompt logic. The skill files (SKILL.md, templates.md) are prompt instructions, not executable code.

## References

- Original issue: `.issues/features/P4-FEAT-440-tdd-mode-for-issue-implementation.md`
- Phase 2.5 confidence gate pattern: `skills/manage-issue/SKILL.md:154-186`
- CommandsConfig dataclass: `scripts/little_loops/config.py:270-287`
- Config schema commands section: `config-schema.json:228-266`

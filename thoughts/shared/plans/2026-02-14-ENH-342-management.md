# ENH-342: Command examples hardcode tool names instead of config values

## Summary

Replace hardcoded tool names (`pytest`, `ruff`, `mypy`) in example/template sections of 3 files with `{{config.project.*}}` template references, following the pattern already established in `commands/check-code.md`.

## Research Findings

- **Pattern to follow**: `commands/check-code.md` uses `{{config.project.test_cmd}}`, `{{config.project.lint_cmd}}`, `{{config.project.type_cmd}}`, `{{config.project.format_cmd}}`, and `{{config.project.src_dir}}` throughout
- **Scope**: Issue specifies exactly 3 files; additional files exist with hardcoded names but are out of scope per the issue's boundaries
- **Config keys used**: `test_cmd`, `lint_cmd`, `type_cmd`, `src_dir`

## Implementation Plan

### Phase 1: Update `skills/create-loop/SKILL.md` (line 218)

**Current** (line 218):
```
Action: mypy src/
```

**Replace with**:
```
Action: {{config.project.type_cmd}} {{config.project.src_dir}}
```

This is an example output block showing what a test iteration looks like. Replacing `mypy src/` with config references makes it consistent with the config-driven approach.

### Phase 2: Update `commands/iterate-plan.md` (lines 125-127)

**Current** (lines 125-127):
```markdown
- [ ] `pytest tests/` passes
- [ ] `ruff check .` passes
- [ ] `mypy src/` passes
```

**Replace with**:
```markdown
- [ ] `{{config.project.test_cmd}}` passes
- [ ] `{{config.project.lint_cmd}} {{config.project.src_dir}}` passes
- [ ] `{{config.project.type_cmd}} {{config.project.src_dir}}` passes
```

### Phase 3: Update `commands/loop-suggester.md` (line 60)

**Current** (line 60):
```
- Common checks: `pytest`, `mypy`, `ruff`, `eslint`, `tsc`
```

**Replace with** a note referencing configured commands while keeping the concrete examples for clarity:
```
- Common checks: tools configured via `{{config.project.*}}` (e.g., `pytest`, `mypy`, `ruff`, `eslint`, `tsc`)
```

This preserves the illustrative examples while noting the config-driven approach, since `loop-suggester` is detecting patterns in user history (not executing commands) and needs concrete tool names for pattern matching.

### Phase 4: Verification

- Run `python -m pytest scripts/tests/` — no code changes, but ensure no regressions
- Run `ruff check scripts/` — lint check
- Run `python -m mypy scripts/little_loops/` — type check

### Success Criteria

- [ ] `skills/create-loop/SKILL.md` line 218 uses config references
- [ ] `commands/iterate-plan.md` lines 125-127 use config references
- [ ] `commands/loop-suggester.md` line 60 references configured commands
- [ ] All verification passes
- [ ] No other files modified (scope boundaries respected)

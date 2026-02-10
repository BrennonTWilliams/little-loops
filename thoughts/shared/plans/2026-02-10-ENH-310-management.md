# ENH-310: Wire build_cmd into check_code verification - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-310-wire-build-cmd-into-check-code.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

`commands/check_code.md` runs three check types: lint, format, and types. Each follows the same structural pattern:
1. A mode-conditional bash block with banner output
2. The config command reference `{{config.project.*_cmd}}`
3. Exit code checking with `[PASS]`/`[FAIL]` messages
4. A line in the summary report

`build_cmd` is fully defined in `config-schema.json:50-54` (nullable string, default null), the `ProjectConfig` dataclass at `config.py:75`, and is populated by 6 of 9 templates (TypeScript, Go, Rust, Java Maven, Java Gradle, .NET). However, it is never referenced in `check_code.md`.

### Key Discoveries
- `commands/check_code.md` has zero references to `build_cmd`
- The pattern for each check mode is consistent: conditional block + banner + command + exit check
- `build_cmd` is nullable (same as `type_cmd`), and `check_code.md` handles nullable commands implicitly via Claude's contextual understanding of the config
- `allowed-tools` in frontmatter currently restricts to `Bash(ruff:*, mypy:*, python:*)` — build commands (npm, cargo, go, etc.) are not included
- The `manage_issue.md` command uses `(if configured)` comments for optional commands

## Desired End State

`/ll:check_code` has a new `build` mode and includes build verification in `all` mode when `build_cmd` is configured. The summary report includes a Build line. Projects without `build_cmd` see no change.

### How to Verify
- For this project (no `build_cmd`): `/ll:check_code all` works identically to before, summary may show `Build: [SKIP]`
- For a project with `build_cmd`: the build command runs as part of `all` mode and can be run standalone with `build` mode

## What We're NOT Doing

- Not changing `manage_issue` verification — that's ENH-311
- Not changing the config schema or templates
- Not adding `build_cmd` to any other workflow
- Not adding auto-fix for build errors (builds don't have auto-fix)

## Solution Approach

Single-file edit to `commands/check_code.md` following the exact existing patterns for lint/format/types checks. Add `build` as a new mode that runs after types in `all` mode.

## Code Reuse & Integration

- **Patterns to follow**: The exact check block pattern from `check_code.md:90-104` (types mode) — build follows the same pattern since neither has auto-fix
- **No new code/files needed**: This is purely additive within the existing command file

## Implementation Phases

### Phase 1: Edit commands/check_code.md

#### Overview
Add `build_cmd` support throughout the command file.

#### Changes Required

**1. Frontmatter — update description and allowed-tools** (lines 1-9)

Update description to mention build:
```yaml
description: Run code quality checks (lint, format, types, build)
```

Add common build tool patterns to allowed-tools:
```yaml
allowed-tools:
  - Bash(ruff:*, mypy:*, python:*, npm:*, cargo:*, go:*, dotnet:*, mvn:*, ./gradlew:*, make:*)
```

**2. Configuration section — add build_cmd** (after line 21)

Add:
```markdown
- **Build command**: `{{config.project.build_cmd}}`
```

**3. Check Modes section — add build mode** (line 28, before "all")

Update list to:
```markdown
- **lint**: Run linter to find code issues
- **format**: Check code formatting
- **types**: Run type checking
- **build**: Run build verification (if configured)
- **all**: Run all checks (default)
- **fix**: Auto-fix issues where possible
```

**4. Add build check block** (after types block, before fix block — after line 105)

```markdown
#### Mode: build

Run build verification if `build_cmd` is configured (non-null). Skip silently if not configured.

```bash
if [ "$MODE" = "build" ] || [ "$MODE" = "all" ]; then
    echo ""
    echo "========================================"
    echo "BUILD"
    echo "========================================"

    # Only run if build_cmd is configured (non-null)
    {{config.project.build_cmd}}

    if [ $? -eq 0 ]; then
        echo "[PASS] Build succeeded"
    else
        echo "[FAIL] Build failed"
    fi
fi
```
```

**5. Summary report — add Build line** (after line 147)

```
Results:
  Linting:    [PASS/FIXED/FAIL]
  Formatting: [PASS/FIXED/FAIL]
  Types:      [PASS/FAIL]
  Build:      [PASS/FAIL/SKIP]
```

Add SKIP to the status legend:
```
- SKIP: Check not configured (e.g., no build_cmd set)
```

**6. Arguments section — add build mode** (after line 167)

Add `build` to the mode list:
```markdown
  - `build` - Run build verification only (if configured)
```

**7. Examples section — add build example** (after line 185)

```bash
# Just build verification
/ll:check_code build
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Format passes: `ruff format --check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] The check_code.md file has correct markdown structure
- [ ] The new build block follows the exact same pattern as the types block
- [ ] Running `/ll:check_code all` on this project (no build_cmd) doesn't break anything

## Testing Strategy

This is a prompt-only change (markdown command file), so there are no unit tests to write. Verification is:
1. Structural: the markdown is well-formed and follows existing patterns
2. Functional: lint/format/types still pass on the modified file (no syntax issues)
3. Integration: the command still works when invoked (manual)

## References

- Original issue: `.issues/enhancements/P3-ENH-310-wire-build-cmd-into-check-code.md`
- Related patterns: `commands/check_code.md:90-104` (types mode block)
- Config schema: `config-schema.json:50-54`
- Dataclass: `scripts/little_loops/config.py:75`

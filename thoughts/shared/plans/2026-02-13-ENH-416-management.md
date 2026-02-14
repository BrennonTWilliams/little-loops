# ENH-416: --all flag should implicitly enable --auto behavior - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P4-ENH-416-all-flag-should-imply-auto-behavior.md
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

Two skill files (`confidence-check/SKILL.md` and `format-issue/SKILL.md`) validate that `--all` requires `--auto` and throw an error if `--all` is used alone. The codebase already has a precedent for flag implication: `--dangerously-skip-permissions` implies `--auto` in both files.

### Key Discoveries
- `skills/confidence-check/SKILL.md:63-68` — Error block that rejects `--all` without `--auto`
- `skills/format-issue/SKILL.md:70-75` — Identical error block
- `skills/confidence-check/SKILL.md:42` — Existing "implies" pattern (`--dangerously-skip-permissions` → `AUTO_MODE=true`)
- `skills/format-issue/SKILL.md:52-57` — Same "implies" pattern
- `skills/confidence-check/SKILL.md:78` — Docs say "Requires `--auto`."
- `skills/confidence-check/SKILL.md:412-413` — Example shows `--all` alone as error case
- No other files in the repo use this `--all requires --auto` pattern

## Desired End State

- `--all` auto-enables `--auto` in both skills
- `--all --auto` still works (backwards compatible)
- `--auto` alone still works for single-issue non-interactive mode
- Documentation updated to reflect new behavior

## What We're NOT Doing

- Not adding `--all`/`--auto` flags to commands that don't have them
- Not changing any other flag behavior
- Not modifying plan/thought files that contain historical copies of the pattern

## Solution Approach

Replace the error validation block with an auto-enable block (matching the existing `--dangerously-skip-permissions` implies `--auto` pattern). Update documentation references.

## Implementation Phases

### Phase 1: Update confidence-check/SKILL.md

#### Changes Required

**File**: `skills/confidence-check/SKILL.md`

1. **Lines 63-68**: Replace error block with auto-enable:
   ```bash
   # --all implies --auto (batch processing is inherently non-interactive)
   if [[ "$ALL_MODE" == true ]]; then
       AUTO_MODE=true
   fi
   ```

2. **Line 78**: Change `Requires \`--auto\`.` to `Implies \`--auto\`.`

3. **Lines 412-413**: Replace error example with working example:
   ```bash
   # All active issues (--auto is implied)
   /ll:confidence-check --all
   ```

#### Success Criteria
- [ ] File edits applied cleanly
- [ ] No broken markdown structure

### Phase 2: Update format-issue/SKILL.md

#### Changes Required

**File**: `skills/format-issue/SKILL.md`

1. **Lines 70-75**: Replace error block with auto-enable:
   ```bash
   # --all implies --auto (batch processing is inherently non-interactive)
   if [[ "$ALL_MODE" == true ]]; then
       AUTO_MODE=true
   fi
   ```

#### Success Criteria
- [ ] File edits applied cleanly
- [ ] No broken markdown structure

### Phase 3: Verify

- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Grep confirms no remaining "all flag requires --auto" error patterns

## References

- Original issue: `.issues/enhancements/P4-ENH-416-all-flag-should-imply-auto-behavior.md`
- Existing "implies" pattern: `skills/confidence-check/SKILL.md:42`
- Existing "implies" pattern: `skills/format-issue/SKILL.md:52-57`

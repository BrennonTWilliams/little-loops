# ENH-276: Add Flag Conventions to Commands

## Summary

Standardize `--flag` style modifier conventions across commands and skills, adding flag support to `scan-codebase`, `manage-issue`, and `audit-architecture`, then documenting the convention in `help.md`, `docs/COMMANDS.md`, and `CONTRIBUTING.md`.

## Research Findings

### Existing Flag Patterns
- **19 distinct flags** already in use across 11+ commands/skills
- **Established pattern**: Bash substring matching `[[ "$FLAGS" == *"--flag"* ]]` (used in align-issues, refine-issue, format-issue, etc.)
- **Skill pattern**: YAML frontmatter `flags` argument with natural language conditional sections (manage-issue)
- **Common flags already standardized**: `--auto`, `--dry-run`, `--all`, `--deep`, `--quick`, `--verbose`

### Target Files
1. `commands/scan-codebase.md` — No flags currently, no arguments section
2. `skills/manage-issue/SKILL.md` — Has `--plan-only`, `--resume`, `--gates`; needs `--dry-run`, `--quick`
3. `commands/audit-architecture.md` — Has `focus` positional arg only; needs `--deep`, `--focus` as flags
4. `commands/help.md` — Lists commands but no flag convention section
5. `docs/COMMANDS.md` — Has per-command flag docs but no convention reference
6. `CONTRIBUTING.md` — Has "Adding Commands" section but no flag guidelines

### Design Decisions (autonomous, no --gates)
- **`--focus` for audit-architecture**: The command already has a positional `focus` argument. Adding `--focus` as a flag would conflict. Instead, add `--deep` flag only — the positional arg already handles focus areas.
- **`--quick` for scan-codebase**: Reduce to 1 sub-agent scan (combined) instead of 3 parallel scans, skip cross-referencing step.
- **`--deep` for scan-codebase**: Increase analysis depth in sub-agent prompts, add extra verification passes.
- **`--focus` for scan-codebase**: Narrow scan to a specific focus area (e.g., `--focus security`, `--focus performance`).
- **`--dry-run` for manage-issue**: Show the plan without implementing. This is essentially what `--plan-only` does — mark `--dry-run` as an alias.
- **`--quick` for manage-issue**: Skip Phase 1.5 deep research, skip confidence check, go straight to planning.
- **`--deep` for audit-architecture**: Spawn sub-agents for deeper analysis (pattern-finder, analyzer) instead of direct sequential analysis.

## Implementation Plan

### Phase 1: Add flags to scan-codebase.md

**File**: `commands/scan-codebase.md`

Changes:
1. Add `argument-hint` and `arguments` section to YAML frontmatter (flags: `--quick`, `--deep`, `--focus [area]`)
2. Add flag parsing section after Process step 0 (Initialize)
3. Add conditional behavior for `--quick` (single combined agent, skip cross-referencing)
4. Add conditional behavior for `--deep` (enhanced prompts, extra verification)
5. Add conditional behavior for `--focus [area]` (narrow agent prompts to specific concern)
6. Add Arguments documentation section before Examples
7. Update Examples section with flag usage

### Phase 2: Add flags to manage-issue SKILL.md

**File**: `skills/manage-issue/SKILL.md`

Changes:
1. Update `flags` argument description to include `--dry-run` and `--quick`
2. Add `--dry-run` as alias for `--plan-only` in Phase 2 section
3. Add `--quick` behavior: skip Phase 1.5 deep research and confidence check
4. Update Arguments section with new flags
5. Update Examples section

### Phase 3: Add flags to audit-architecture.md

**File**: `commands/audit-architecture.md`

Changes:
1. Add `arguments` array to YAML frontmatter with `flags` entry for `--deep`
2. Add flag parsing section
3. Add `--deep` conditional behavior: spawn sub-agents for deeper analysis
4. Update Arguments section
5. Update Examples section

### Phase 4: Add Flag Convention section to help.md

**File**: `commands/help.md`

Changes:
1. Add "Standard Flags" reference section after the command listing
2. Document the standard flag convention with table of common flags
3. Update scan-codebase entry to show flags
4. Update manage-issue entry to show new flags
5. Update audit-architecture entry to show flags

### Phase 5: Update docs/COMMANDS.md

**File**: `docs/COMMANDS.md`

Changes:
1. Add "Flag Conventions" section near top (after intro, before Setup)
2. Update `/ll:scan-codebase` entry with flags
3. Update `/ll:manage-issue` entry with new flags
4. Update `/ll:audit-architecture` entry with flags

### Phase 6: Update CONTRIBUTING.md

**File**: `CONTRIBUTING.md`

Changes:
1. Add "Flag Conventions" subsection in "Adding Commands" section
2. Document the standard flag pattern with code example
3. List standard flags and when to use them

### Phase 7: Verify

- [ ] `python -m pytest scripts/tests/ -v` (no Python changes, but verify nothing broken)
- [ ] `ruff check scripts/` (no Python changes expected)
- [ ] `python -m mypy scripts/little_loops/` (no Python changes expected)

## Success Criteria

- [ ] `scan-codebase.md` supports `--quick`, `--deep`, `--focus [area]` flags
- [ ] `manage-issue/SKILL.md` supports `--dry-run` (alias for --plan-only) and `--quick` flags
- [ ] `audit-architecture.md` supports `--deep` flag
- [ ] `help.md` includes flag convention reference section
- [ ] `docs/COMMANDS.md` documents flags for updated commands
- [ ] `CONTRIBUTING.md` has flag convention guidelines for command authors
- [ ] All existing tests still pass

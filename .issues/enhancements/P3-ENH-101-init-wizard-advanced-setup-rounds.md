---
discovered_date: 2026-01-21
discovered_by: capture_issue
---

# ENH-101: Add Advanced Setup Rounds to Init Wizard

## Summary

Add optional "advanced setup" rounds to `/ll:init --interactive` wizard to expose additional configuration options that currently require manual editing of `ll-config.json`.

## Context

An audit of the init wizard revealed that only **26% of configurable features** are exposed through the interactive setup. Users must manually edit `ll-config.json` to access the remaining 74% of configuration options.

This enhancement adds optional advanced rounds to the wizard for commonly-needed settings that are currently missing.

## Current Behavior

The init wizard covers 5 rounds:
1. Core project settings (name, src_dir, test_cmd, lint_cmd)
2. Additional config (format_cmd, issues dir, scan dirs, exclude patterns)
3. Features selection (parallel processing, context monitoring)
4. Advanced settings (limited to issues path, worktree files, context threshold)
5. Document tracking

Missing from wizard but frequently needed:
- Continuation behavior settings
- Project test_dir and build_cmd
- Prompt optimization settings

## Expected Behavior

Add an optional "Advanced Setup" section after Round 5 that covers:

### Round 6: Project Advanced (2 questions)

```yaml
questions:
  - question: "Do you have a separate test directory?"
    header: "Test dir"
    options:
      - label: "tests/"
        description: "Standard tests/ directory"
      - label: "test/"
        description: "Alternative test/ directory"
      - label: "Same as src"
        description: "Tests are alongside source files"
    multiSelect: false

  - question: "Do you have a build command?"
    header: "Build cmd"
    options:
      - label: "npm run build"
        description: "Node.js build"
      - label: "python -m build"
        description: "Python build"
      - label: "make build"
        description: "Makefile build"
      - label: "Skip"
        description: "No build step needed"
    multiSelect: false
```

### Round 7: Continuation Behavior (3 questions)

```yaml
questions:
  - question: "Enable automatic session continuation detection?"
    header: "Continuation"
    options:
      - label: "Yes (Recommended)"
        description: "Auto-detect continuation prompts on session start"
      - label: "No"
        description: "Manual /ll:resume required"
    multiSelect: false

  - question: "What should continuation prompts include?"
    header: "Include"
    options:
      - label: "Todos"
        description: "Include pending todo list items"
      - label: "Git status"
        description: "Include current git status"
      - label: "Recent files"
        description: "Include recently modified files"
    multiSelect: true

  - question: "How long should continuation prompts remain valid?"
    header: "Expiry"
    options:
      - label: "24 hours (Recommended)"
        description: "Prompts expire after one day"
      - label: "48 hours"
        description: "Prompts expire after two days"
      - label: "No expiry"
        description: "Prompts never expire"
    multiSelect: false
```

### Round 8: Prompt Optimization (3 questions)

```yaml
questions:
  - question: "Enable automatic prompt optimization?"
    header: "Optimize"
    options:
      - label: "Yes (Recommended)"
        description: "Enhance prompts with codebase context"
      - label: "No"
        description: "Use prompts as-is"
    multiSelect: false

  - question: "Optimization mode?"
    header: "Mode"
    options:
      - label: "Quick"
        description: "Fast optimization, less thorough"
      - label: "Thorough (Recommended)"
        description: "Full codebase analysis"
    multiSelect: false

  - question: "Require confirmation before optimization?"
    header: "Confirm"
    options:
      - label: "Yes"
        description: "Show optimized prompt for approval"
      - label: "No (Recommended)"
        description: "Apply optimization automatically"
    multiSelect: false
```

### Entry Point

Add a question after Round 5:

```yaml
questions:
  - question: "Would you like to configure advanced settings?"
    header: "Advanced"
    options:
      - label: "Skip (Recommended)"
        description: "Use sensible defaults for advanced settings"
      - label: "Configure"
        description: "Set up continuation, prompt optimization, and more"
    multiSelect: false
```

If "Configure" is selected, proceed to Rounds 6-8. Otherwise, skip to final output.

## Impact

- **Priority**: P3 (nice to have, improves UX)
- **Effort**: Low - extend existing wizard structure
- **Risk**: Low - additive feature, doesn't change existing behavior

## Proposed Solution

1. Add `--advanced` flag to `/ll:init` to skip directly to advanced rounds
2. Add optional "Configure advanced settings?" prompt after Round 5
3. Implement Rounds 6-8 with questions for:
   - `project.test_dir`, `project.build_cmd`
   - `continuation.*` settings
   - `prompt_optimization.*` settings
4. Update config generation to include new fields

## Files to Modify

| File | Changes |
|------|---------|
| `commands/init.md` | Add advanced setup rounds and `--advanced` flag |

## Related Issues

- FEAT-020: Product Analysis Opt-In Configuration (also extends init)
- FEAT-021: Goals/Vision Ingestion Mechanism (also extends init)

## Labels

`enhancement`, `init`, `wizard`, `configuration`, `ux`

---

## Status

**Completed** | Created: 2026-01-21 | Priority: P3

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-21
- **Status**: Completed

### Changes Made
- `commands/init.md`: Added advanced setup rounds (6-8) with entry gate question
  - Step 5f: Advanced Settings Gate - asks if user wants to configure advanced settings
  - Step 5g: Project Advanced (Round 6) - test_dir, build_cmd
  - Step 5h: Continuation Behavior (Round 7) - auto_detect, include options, expiry
  - Step 5i: Prompt Optimization (Round 8) - enabled, mode, confirm
- Updated Interactive Mode Summary table to reflect new rounds (4-9 total)
- Updated Display Summary to show continuation and prompt_optimization sections
- Updated config template to include new sections

### Verification Results
- Tests: PASS
- Lint: PASS
- Types: PASS

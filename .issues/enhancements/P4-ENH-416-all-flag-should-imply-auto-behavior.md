---
discovered_date: 2026-02-13
discovered_by: capture_issue
confidence_score: 97
---

# ENH-416: --all flag should implicitly enable --auto behavior

## Summary

When `--all` is passed to skills/commands that support batch processing, it should automatically imply `--auto` behavior instead of throwing an error requiring both flags. This reduces friction for users who want to batch-process all active issues — typing `--all` alone should be sufficient.

## Current Behavior

In `skills/confidence-check/SKILL.md` and `skills/format-issue/SKILL.md`, passing `--all` without `--auto` produces an error:

```
Error: --all flag requires --auto mode for non-interactive batch processing
Usage: /ll:confidence-check --all --auto
```

Users must explicitly pass both `--all --auto` to run batch processing.

## Expected Behavior

- `--all` automatically enables `--auto` behavior (non-interactive mode)
- `--all --auto` still works (no breaking change)
- `--auto` alone still works for single-issue non-interactive mode
- No error when `--all` is passed without `--auto`

The flag parsing logic should change from:

```bash
# Current: error if --all without --auto
if [[ "$ALL_MODE" == true ]] && [[ "$AUTO_MODE" == false ]]; then
    echo "Error: --all flag requires --auto mode..."
    exit 1
fi
```

To:

```bash
# New: --all implies --auto
if [[ "$ALL_MODE" == true ]]; then
    AUTO_MODE=true
fi
```

## Motivation

Requiring both flags is redundant — batch processing all issues inherently requires non-interactive mode. Forcing users to type `--all --auto` is unnecessary friction. This should be a consistent pattern across all skills/commands that support these flags.

## Proposed Solution

Update the flag parsing in every skill/command that has the `--all requires --auto` validation to instead auto-enable `--auto` when `--all` is passed.

### Affected Files

1. `skills/confidence-check/SKILL.md` — Replace error block with auto-enable
2. `skills/format-issue/SKILL.md` — Replace error block with auto-enable

### Pattern to Apply

In each file, replace the validation block:

```bash
# Validate: --all requires --auto
if [[ "$ALL_MODE" == true ]] && [[ "$AUTO_MODE" == false ]]; then
    echo "Error: --all flag requires --auto mode for non-interactive batch processing"
    echo "Usage: /ll:<skill> --all --auto"
    exit 1
fi
```

With:

```bash
# --all implies --auto (batch processing is inherently non-interactive)
if [[ "$ALL_MODE" == true ]]; then
    AUTO_MODE=true
fi
```

Also update documentation/usage sections that mention `--all` requiring `--auto`.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — flag parsing, docs, usage examples
- `skills/format-issue/SKILL.md` — flag parsing, docs

### Dependent Files (Callers/Importers)
- `skills/manage-issue/SKILL.md` — references confidence-check (no changes needed)

### Similar Patterns
- `commands/ready_issue.md` — currently has no `--all`/`--auto` flags (separate issue if needed)

### Tests
- N/A (prompt-based skill definitions, no Python tests)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Update `skills/confidence-check/SKILL.md` — replace error block with auto-enable, update docs
2. Update `skills/format-issue/SKILL.md` — replace error block with auto-enable, update docs
3. Grep for any other `--all requires --auto` patterns and apply consistently

## Impact

- **Priority**: P4 - Quality-of-life improvement, not blocking workflows
- **Effort**: Small - Simple find-and-replace in 2 files
- **Risk**: Low - Additive change, `--all --auto` still works
- **Breaking Change**: No

## Scope Boundaries

- NOT adding `--all`/`--auto` flags to commands that don't have them yet (e.g., `ready_issue`)
- NOT changing any other flag behavior beyond the `--all` implies `--auto` pattern

## Success Metrics

- `/ll:confidence-check --all` runs without error (auto-enables non-interactive mode)
- `/ll:format-issue --all` runs without error (auto-enables non-interactive mode)
- `/ll:confidence-check --all --auto` still works (backwards compatible)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Skill development preferences |
| architecture | docs/ARCHITECTURE.md | Skill definition conventions |

## Labels

`enhancement`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-02-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/029370ae-e505-4752-bc55-4fd2b8896741.jsonl`
- `/ll:manage-issue` - 2026-02-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/caefd7bf-6a76-4821-9e00-efef2915b5c2.jsonl`

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `skills/confidence-check/SKILL.md`: Replaced `--all requires --auto` error block with `--all implies --auto` auto-enable; updated docs and examples
- `skills/format-issue/SKILL.md`: Replaced `--all requires --auto` error block with `--all implies --auto` auto-enable; updated usage hint in `--all` + issue ID validation

### Verification Results
- Tests: PASS (2734 passed)
- Lint: PASS
- Types: PASS
- Integration: PASS

---

## Status

**Completed** | Created: 2026-02-13 | Completed: 2026-02-13 | Priority: P4

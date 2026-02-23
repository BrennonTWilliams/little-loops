---
type: ENH
id: ENH-453
title: Offer to create issue directories during init instead of as next step
priority: P3
status: open
created: 2026-02-22
---

# Offer to create issue directories during init instead of as next step

## Summary

Step 10 (completion message) tells users to manually run `mkdir -p .issues/{bugs,features,enhancements}`. Since issue management is a core feature and the directory structure is deterministic from the config, init should create these directories automatically.

## Current Behavior

After completing the init wizard, Step 10 (completion message) instructs users to manually run `mkdir -p .issues/{bugs,features,enhancements}` as a next step. The issue directories are not created automatically during init.

## Expected Behavior

During Step 8 (Write Configuration), init also creates the issue directories automatically using the configured `issues.base_dir`. The completion message confirms "Created: .issues/{bugs,features,enhancements,completed}" rather than listing directory creation as a manual next step.

## Motivation

Issue directory creation is a deterministic, always-needed step that requires no user decision. Requiring users to manually run `mkdir` after init is unnecessary friction — especially since the directory structure is fully known from the config. Automating it removes one more manual step from onboarding.

## Proposed Solution

In Step 8 (Write Configuration), after writing `ll-config.json`, also create the issue directories:

```bash
mkdir -p .issues/bugs .issues/features .issues/enhancements .issues/completed
```

Use the configured `issues.base_dir` and `issues.categories` values. Update the completion message to say "Created: .issues/{bugs,features,enhancements,completed}" instead of listing it as a manual next step.

## Scope Boundaries

- **In scope**: Automatic creation of issue directories during Step 8 using configured `issues.base_dir`; updating completion message
- **Out of scope**: Creating other directories (sprints, loops), populating directories with example files, handling custom category configurations

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — Step 8 (lines ~158-182): add directory creation after writing ll-config.json; Step 10 (lines ~207-227): update completion message

### Similar Patterns
- N/A

### Tests
- N/A

### Documentation
- N/A

### Configuration
- Uses `issues.base_dir` from ll-config.json (default: `.issues`)

## Implementation Steps

1. In Step 8 of `SKILL.md`, after writing `ll-config.json`, add Bash tool call: `mkdir -p .issues/bugs .issues/features .issues/enhancements .issues/completed`
2. Use the configured `issues.base_dir` value (not hardcoded `.issues`) for path construction
3. Update Step 10 completion message to list directory creation as completed rather than as a next step
4. Handle edge case: directories already exist (`mkdir -p` is idempotent)

## Impact

- **Priority**: P3 — Reduces manual setup steps; improves onboarding smoothness
- **Effort**: Small — Two-line change to Step 8 + completion message update
- **Risk**: Low — `mkdir -p` is idempotent; no risk of data loss or overwriting
- **Breaking Change**: No

## Labels

`enhancement`, `init`, `onboarding`, `issue-directories`

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`

## Blocked By

- BUG-450
- ENH-451
- ENH-456
- ENH-457

## Blocks

- ENH-458
- ENH-459

---

## Status

**Open** | Created: 2026-02-22 | Priority: P3

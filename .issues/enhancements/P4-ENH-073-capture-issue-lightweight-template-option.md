---
discovered_date: 2025-01-15
discovered_by: manual_review
---

# ENH-073: capture_issue should offer lightweight template option

## Summary

The `/ll:capture_issue` command creates issues with a comprehensive template including many sections (Current Behavior, Expected Behavior, Proposed Solution, Impact, Labels, Status). For quick issue capture, a lighter template option would improve usability.

## Current Behavior

Every captured issue gets the full template (lines 306-356 in `commands/capture_issue.md`):
- Summary
- Context
- Current Behavior
- Expected Behavior
- Proposed Solution
- Impact (Priority, Effort, Risk)
- Labels
- Status

This is heavyweight for quick captures like "The login button is broken" or "Add dark mode".

## Expected Behavior

Offer template options, either via:

1. **Argument flag**: `/ll:capture_issue --quick "description"`
2. **Config option**: `config.issues.capture_template: "full" | "minimal"`
3. **AskUserQuestion**: Let user choose after extraction

**Minimal template example:**
```markdown
---
discovered_date: [YYYY-MM-DD]
discovered_by: capture_issue
---

# [TYPE]-[NNN]: [Title]

## Summary

[Description]

## Context

[Source context]

---

**Priority**: [P0-P5] | **Created**: [YYYY-MM-DD]
```

The minimal template can always be expanded later via `/ll:ready_issue`.

## Proposed Implementation

1. Add `capture_template` option to `config-schema.json` under `issues` section (after `templates_dir` around line 109):
   ```json
   "capture_template": {
     "type": "string",
     "enum": ["full", "minimal"],
     "default": "full",
     "description": "Default template style for captured issues"
   }
   ```

2. Update `commands/capture_issue.md` to check config and use appropriate template in the "Create issue file" section (lines 306-356)

3. Optionally add `--quick` flag to force minimal template regardless of config

## Impact

- **Priority**: P4
- **Effort**: Low
- **Risk**: Low

## Labels

`enhancement`, `commands`, `usability`

---

## Status

**Open** | Created: 2025-01-15 | Priority: P4

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-18
- **Status**: Completed

### Changes Made
- `config-schema.json`: Added `capture_template` option with enum ["full", "minimal"] and default "full"
- `commands/capture_issue.md`: Added `--quick` flag argument, config documentation, flag parsing, and conditional template logic

### Verification Results
- Tests: PASS (1345 tests)
- Lint: PASS (markdown files not linted by ruff)
- JSON Schema: PASS

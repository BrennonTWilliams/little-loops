---
discovered_date: 2025-01-15
discovered_by: manual_review
---

# ENH-073: capture_issue should offer lightweight template option

## Summary

The `/ll:capture_issue` command creates issues with a comprehensive template including many sections (Current Behavior, Expected Behavior, Proposed Solution, Impact, Labels, Status). For quick issue capture, a lighter template option would improve usability.

## Current Behavior

Every captured issue gets the full template (lines 269-316):
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

1. Add `capture_template` option to `config-schema.json` under `issues`:
   ```json
   "capture_template": {
     "type": "string",
     "enum": ["full", "minimal"],
     "default": "full"
   }
   ```

2. Update `capture_issue.md` to check config and use appropriate template

3. Optionally add `--quick` flag to force minimal template

## Impact

- **Priority**: P4
- **Effort**: Low
- **Risk**: Low

## Labels

`enhancement`, `commands`, `usability`

---

## Status

**Open** | Created: 2025-01-15 | Priority: P4

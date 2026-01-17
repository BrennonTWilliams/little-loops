# ENH-089: Add Version Fields to Skill SKILL.md Frontmatter

## Status

**Closed - Invalid** (2026-01-17)

**Reason**: The official skill development specification (plugin-dev:skill-development SKILL.md) explicitly lists only `name` and `description` as required frontmatter fields. The `version` field appears in some examples but is not required or explicitly recommended as a best practice. Per lines 32-35 of the specification:

```
├── YAML frontmatter metadata (required)
│   ├── name: (required)
│   └── description: (required)
```

The validation checklist (lines 419-421) also confirms only `name` and `description` are required.

---

## Summary

Skill `SKILL.md` files are missing the recommended `version` field in their YAML frontmatter.

## Current State

Example from `skills/issue-workflow/SKILL.md`:
```yaml
---
name: issue-workflow
description: |
  Quick reference for the little-loops issue management workflow...
---
```

## Recommended State

Per plugin structure best practices:
```yaml
---
name: issue-workflow
description: |
  Quick reference for the little-loops issue management workflow...
version: 1.0.0
---
```

## Affected Files

- `skills/issue-workflow/SKILL.md`
- `skills/create-loop/SKILL.md`
- `skills/capture-issue/SKILL.md`

## Implementation

Add `version: 1.0.0` to each skill's frontmatter:

```bash
# For each SKILL.md file, add version field after description
```

## Benefits

- Follows plugin structure best practices
- Enables version tracking for skills
- Useful for changelog generation and compatibility checking

## Priority

Low priority - skills function correctly without this field. This is a best-practice improvement rather than a bug fix.

## References

- Plugin structure specification example:
  ```yaml
  ---
  name: Skill Name
  description: When to use this skill
  version: 1.0.0
  ---
  ```

## Discovered By

Plugin structure audit using `plugin-dev:plugin-structure` skill

---
type: ENH
id: ENH-459
title: Mention ll.local.md during init completion message
priority: P4
status: open
created: 2026-02-22
---

# Mention ll.local.md during init completion message

## Summary

The local override file `.claude/ll.local.md` is a useful feature for per-developer settings (different test commands, scan directories, etc.), but init never mentions it. Users would need to discover it through CLAUDE.md or README.md.

## Proposed Change

Add a line to the Step 10 completion message:

```
Next steps:
  ...
  N. For personal overrides: create .claude/ll.local.md (gitignored)
```

Also consider adding `.claude/ll.local.md` to the `.gitignore` entries in Step 9 if not already present (it should be gitignored by default since it's for personal settings).

## Files

- `skills/init/SKILL.md` (Step 9 .gitignore, lines ~184-203; Step 10 completion, lines ~207-227)

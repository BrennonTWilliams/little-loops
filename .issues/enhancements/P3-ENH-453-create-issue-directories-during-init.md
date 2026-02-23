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

## Proposed Change

In Step 8 (Write Configuration), after writing `ll-config.json`, also create the issue directories:

```bash
mkdir -p .issues/bugs .issues/features .issues/enhancements .issues/completed
```

Use the configured `issues.base_dir` and `issues.categories` values. Update the completion message to say "Created: .issues/{bugs,features,enhancements,completed}" instead of listing it as a manual next step.

## Files

- `skills/init/SKILL.md` (Step 8, lines ~158-182; Step 10, lines ~207-227)

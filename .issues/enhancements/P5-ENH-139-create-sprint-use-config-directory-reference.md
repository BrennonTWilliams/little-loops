---
discovered_date: 2026-01-24
discovered_by: audit
---

# ENH-139: Use config reference for directory in create_sprint command

## Summary

The `/ll:create-sprint` command hardcodes `.sprints` in the directory creation step instead of using the configured `sprints_dir` value.

## Context

Line 91 shows:
```bash
mkdir -p .sprints
```

And line 95 references:
```
.sprints/${SPRINT_NAME}.yaml
```

While the default value in `config-schema.json` is `.sprints`, the command should use the configured value for consistency and to support custom configurations.

## Current Behavior

The command always creates/uses the `.sprints` directory regardless of what `sprints.sprints_dir` is configured to.

## Expected Behavior

Use the configured directory from `ll-config.json`:
- Read `sprints.sprints_dir` from config (default: `.sprints`)
- Use that value in directory creation and file path

## Proposed Solution

Update Step 4 to reference the config value:

```markdown
### 4. Create Sprint Directory (if needed)

Ensure the sprints directory exists (using the configured `sprints_dir`):

```bash
mkdir -p ${SPRINTS_DIR}
```

Where `${SPRINTS_DIR}` is the value read from `sprints.sprints_dir` in the configuration.
```

Similarly update Step 5 file path:
```markdown
Create the sprint definition at `${SPRINTS_DIR}/${SPRINT_NAME}.yaml`
```

## Impact

- **Priority**: P5 (very low - consistency improvement)
- **Effort**: Very low (text changes only)
- **Risk**: None

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| config | config-schema.json | sprints.sprints_dir definition (line 531-534) |

## Labels

`enhancement`, `create_sprint`, `consistency`

---

## Status

**Open** | Created: 2026-01-24 | Priority: P5


---

## Resolution

- **Status**: Closed - Already Fixed
- **Closed**: 2026-01-24
- **Reason**: already_fixed
- **Closure**: Automated (ready_issue validation)

### Closure Notes
Issue was automatically closed during validation.
The issue was determined to be invalid, already resolved, or not actionable.

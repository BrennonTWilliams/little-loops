---
discovered_date: 2026-01-29
discovered_by: capture_issue
source: docs/CLI-TOOLS-AUDIT.md
---

# ENH-188: Add quiet mode to ll-auto and ll-sprint

## Summary

ll-parallel supports `--quiet/-q` for suppressing non-essential output, but ll-auto and ll-sprint lack this option. Adding quiet mode improves consistency and is useful for CI/scripted environments.

## Context

Identified from CLI Tools Audit (docs/CLI-TOOLS-AUDIT.md):
- Listed as "Low Priority" standardization opportunity
- Consistency Matrix shows only ll-parallel has quiet mode

## Current Behavior

| Tool | Quiet Mode |
|------|------------|
| ll-auto | ❌ Always verbose |
| ll-parallel | ✅ `--quiet/-q` |
| ll-sprint | ❌ Always verbose |

## Expected Behavior

All three tools support `--quiet/-q` flag that:
- Suppresses progress messages
- Suppresses informational logging
- Still shows errors and warnings
- Still shows final summary

## Proposed Solution

1. Add `--quiet/-q` argument to ll-auto and ll-sprint:

```python
parser.add_argument(
    "-q", "--quiet",
    action="store_true",
    help="Suppress non-essential output"
)
```

2. Integrate with existing Logger class:
   - The Logger class already supports log levels
   - Quiet mode sets level to WARNING or higher
   - Normal mode uses INFO level

3. Example integration:

```python
if args.quiet:
    logger.set_level(logging.WARNING)
else:
    logger.set_level(logging.INFO)
```

## Files to Modify

- `scripts/little_loops/cli.py:25-112` - Add --quiet to ll-auto
- `scripts/little_loops/cli.py:1284-1336` - Add --quiet to ll-sprint
- May need to update Logger class if quiet mode behavior differs

## Impact

- **Priority**: P4 (Low - nice to have feature)
- **Effort**: Low (simple argument and logging level change)
- **Risk**: Very Low (additive feature)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| audit | docs/CLI-TOOLS-AUDIT.md | Consistency Matrix |

## Labels

`enhancement`, `ll-auto`, `ll-sprint`, `consistency`, `cli`, `captured`

---

## Status

**Open** | Created: 2026-01-29 | Priority: P4

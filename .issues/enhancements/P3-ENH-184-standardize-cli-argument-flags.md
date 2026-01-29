---
discovered_date: 2026-01-29
discovered_by: capture_issue
source: docs/CLI-TOOLS-AUDIT.md
---

# ENH-184: Standardize CLI argument flags across tools

## Summary

CLI argument flags are inconsistent across ll-auto, ll-parallel, and ll-sprint. Standardizing these improves user experience and reduces cognitive load when switching between tools.

## Context

Identified from CLI Tools Audit (docs/CLI-TOOLS-AUDIT.md):
- Argument Parsing Comparison table shows inconsistencies
- Listed as "Medium Priority" standardization opportunity

## Current Behavior

| Argument | ll-auto | ll-parallel | ll-sprint |
|----------|---------|-------------|-----------|
| `--timeout` | ❌ | ✅ `-t` | ✅ (no short) |
| `--workers` | ❌ | ✅ `-w` | `--max-workers` |
| `--skip` | ✅ | ✅ | ❌ |
| `--only` | ✅ | ✅ | Uses `--issues` |
| `--resume` | ✅ `-r` | ✅ `-r` | ❌ |
| `--quiet` | ❌ | ✅ `-q` | ❌ |

## Expected Behavior

Consistent flags across all three tools:
- `--timeout/-t` - Available in all tools that support timeouts
- `--max-workers/-w` - Consistent naming (prefer `--max-workers` for clarity)
- `--skip` - Available in all tools for excluding issues
- `--only` - Consistent naming across tools (not `--issues`)
- `--resume/-r` - Available in all tools (requires ENH-182 for sprint)
- `--quiet/-q` - Available in all tools (see ENH-189)

## Proposed Solution

### For ll-sprint (cli.py:1284-1336):

1. Add `-t` short flag for `--timeout`
2. Add `-w` short flag for `--max-workers`
3. Add `--skip` argument for excluding issues
4. Consider renaming `--issues` to `--only` for consistency (or add alias)

### Example changes:

```python
# Before
parser.add_argument("--timeout", type=int, default=3600)
parser.add_argument("--max-workers", type=int, default=2)

# After
parser.add_argument("-t", "--timeout", type=int, default=3600)
parser.add_argument("-w", "--max-workers", type=int, default=2)
parser.add_argument("--skip", nargs="*", help="Issues to skip")
```

## Files to Modify

- `scripts/little_loops/cli.py:1284-1336` - Sprint argument definitions

## Impact

- **Priority**: P3 (Medium - UX improvement)
- **Effort**: Low (simple argument additions)
- **Risk**: Low (additive changes, no breaking changes)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| audit | docs/CLI-TOOLS-AUDIT.md | Argument Parsing Comparison table |

## Labels

`enhancement`, `ll-sprint`, `consistency`, `cli`, `captured`

---

## Status

**Open** | Created: 2026-01-29 | Priority: P3

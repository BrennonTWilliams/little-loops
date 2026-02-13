---
discovered_commit: 925b8ce
discovered_branch: main
discovered_date: 2026-02-13T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# ENH-405: Document `ll-next-id` CLI tool in README

## Summary

The `ll-next-id` CLI tool is defined in `scripts/pyproject.toml` (entry point `little_loops.cli:main_next_id`) but is not documented in the README CLI Tools section or CONTRIBUTING.md.

## Location

- **File**: `README.md`
- **Section**: CLI Tools

## Current Behavior

The README CLI Tools section documents 11 tools but omits `ll-next-id`. The tool is registered in `pyproject.toml` and functions correctly — it prints the next globally unique issue number.

## Expected Behavior

Add a brief `ll-next-id` subsection to the README CLI Tools section showing usage:

```bash
ll-next-id                       # Print next issue number (e.g., 042)
```

## Impact

- **Severity**: Low (internal utility, but still undocumented)
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-02-13 | Priority: P4

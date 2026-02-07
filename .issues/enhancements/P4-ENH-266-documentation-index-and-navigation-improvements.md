---
discovered_commit: c5005eb
discovered_branch: main
discovered_date: 2026-02-06T22:30:00Z
discovered_by: audit_docs
doc_file: docs/
---

# ENH-266: Documentation Index and Navigation Improvements

## Summary

Documentation issue found by `/ll:audit_docs`. The project lacks a central documentation index, making it harder for users to discover and navigate all available documentation.

## Location

- **Missing file**: `docs/INDEX.md`
- **Affected**: New users, documentation discoverability

## Current Content

Users must rely on:
1. README.md Documentation section (lists some docs)
2. ARCHITECTURE.md Related Documentation section
3. Direct file navigation

No central index exists.

## Problem

- No single place to see all available documentation
- Difficult to discover all docs, especially research/ subdirectory
- Inconsistent linking styles (absolute vs relative paths)
- No descriptions of what each doc contains

## Expected Content

Create `docs/INDEX.md` with:

```markdown
# Documentation Index

Complete reference for all little-loops documentation.

## User Documentation

- [README](../README.md) - Installation, quick start, configuration
- [CONTRIBUTING](../CONTRIBUTING.md) - Development setup and guidelines
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues and solutions
- [Command Reference](COMMANDS.md) - All slash commands with usage
- [Session Handoff](SESSION_HANDOFF.md) - Context management guide

## Developer Documentation

- [Architecture Overview](ARCHITECTURE.md) - System design and diagrams
- [API Reference](API.md) - Python module documentation
- [Testing Guide](TESTING.md) - Testing patterns and conventions
- [E2E Testing](E2E_TESTING.md) - End-to-end testing guide

## Advanced Topics

- [FSM Loop Guide](generalized-fsm-loop.md) - Automation loop system
- [CLI Tools Audit](CLI-TOOLS-AUDIT.md) - CLI tools review
- [Claude CLI Integration](claude-cli-integration-mechanics.md) - Integration details

## Research

- [research/](research/) - Research notes and explorations
```

## Additional Improvements

1. **Standardize link styles** - Decide on absolute vs relative
2. **Add link checker to CI** - Prevent broken links
3. **Add breadcrumb navigation** - For large docs

## Impact

- **Severity**: Low (quality of life)
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `user-experience`

---

## Status

**Open** | Created: 2026-02-06 | Priority: P4

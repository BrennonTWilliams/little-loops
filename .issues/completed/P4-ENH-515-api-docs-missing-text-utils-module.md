---
type: ENH
priority: P4
effort: low
risk: low
---

# Add text_utils module to API Reference

## Summary

The `little_loops.text_utils` module exists but is not documented in `docs/reference/API.md`'s Module Overview table.

## Motivation

The API Reference should document all public modules for completeness and discoverability.

## Current Behavior

The Module Overview table in `docs/reference/API.md` lists 25 modules but omits `text_utils`.

## Expected Behavior

The `text_utils` module should appear in the Module Overview table and have a dedicated documentation section in `docs/reference/API.md`, consistent with all other public modules.

## Proposed Solution

Add `text_utils` to the Module Overview table with a description and add a section documenting its public API.

## Integration Map

- `docs/reference/API.md` — Add module entry and documentation section

## Implementation Steps

1. Review `scripts/little_loops/text_utils.py` for public API surface
2. Add row to Module Overview table in `docs/reference/API.md`
3. Add detailed documentation section for the module

## Scope Boundaries

- Only add `text_utils` to the existing API Reference; do not restructure other module documentation
- Do not modify the `text_utils` module code itself

## Impact

- **Priority**: P4 - Documentation completeness, not blocking any functionality
- **Effort**: Low - Single file edit with straightforward content
- **Risk**: Low - Documentation only, no code changes
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`

## Source

Identified by `/ll:audit-docs` on 2026-02-27.

## Resolution

**Fixed** on 2026-02-27.

- Added `text_utils` row to Module Overview table in `docs/reference/API.md`
- Added `## little_loops.text_utils` documentation section with `SOURCE_EXTENSIONS` constant and `extract_file_paths` function

## Status

**Completed** | Created: 2026-02-27 | Resolved: 2026-02-27 | Priority: P4

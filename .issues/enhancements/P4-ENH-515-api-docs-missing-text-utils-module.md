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

## Proposed Solution

Add `text_utils` to the Module Overview table with a description and add a section documenting its public API.

## Integration Map

- `docs/reference/API.md` — Add module entry and documentation section

## Implementation Steps

1. Review `scripts/little_loops/text_utils.py` for public API surface
2. Add row to Module Overview table in `docs/reference/API.md`
3. Add detailed documentation section for the module

## Source

Identified by `/ll:audit-docs` on 2026-02-27.

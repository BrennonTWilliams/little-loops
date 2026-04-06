---
discovered_date: 2026-04-06
discovered_by: capture-issue
---

# ENH-969: ll-auto --verbose Should Show Full Content Without Truncation

## Summary

When `ll-auto` is run with the `--verbose` flag, output for prompts, responses, and other content is currently truncated (e.g., `"... (406 more lines)"`). The verbose mode should display full, untruncated content as intended.

## Current Behavior

Running `ll-auto --verbose` produces truncated output such as:
```
... (406 more lines)
```
Long prompt or response content is cut off, defeating the purpose of the verbose flag.

## Expected Behavior

With `--verbose`, all content (prompts, responses, tool outputs, etc.) should be displayed in full without any truncation. The verbose flag signals the user wants complete output for debugging or inspection purposes.

## Motivation

The `--verbose` flag is a debugging/inspection tool. Truncation undermines its value — if a user is investigating a prompt or response, they need the full text. Truncation may hide the exact content relevant to the issue being debugged.

## Proposed Solution

TBD - requires investigation

Likely involves finding where truncation logic is applied in `ll-auto`'s output/display code and either: (a) bypassing truncation when `--verbose` is set, or (b) removing it entirely from the verbose code path.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis (likely in `scripts/little_loops/` — search for truncation logic, `...`, or `more lines`)

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD

## Implementation Steps

1. Locate truncation logic in `ll-auto` output code (grep for `more lines`, truncate, max length)
2. Add a check: if `--verbose` is active, skip truncation
3. Verify full content is displayed for prompts, responses, and tool outputs under `--verbose`

## Impact

- **Priority**: P3 - Verbose mode is only used by power users/debuggers, but when used, truncation is a hard blocker for its purpose
- **Effort**: Small - Likely a single conditional check around existing truncation logic
- **Risk**: Low - Only affects verbose output path; no production behavior change
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ll-auto`, `verbose`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-04-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

---

## Status

**Open** | Created: 2026-04-06 | Priority: P3

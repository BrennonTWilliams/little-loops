---
id: ENH-2020
title: CLI.md introduction claims to cover 'all ll- tools' but mcp-call lacks the
  ll- prefix
status: done
priority: P5
type: ENH
created: 2026-06-08
completed_at: 2026-06-08 16:34:02+00:00
testable: false
---

## Summary

`docs/reference/CLI.md` opens with "Complete reference for all `ll-` command-line tools," but `mcp-call` is documented in the Utilities section without the `ll-` prefix. The tool name is accurate, but the page framing is slightly misleading.

## Current Behavior

Line 3 of `docs/reference/CLI.md` reads:

> Complete reference for all `ll-` command-line tools.

The `mcp-call` tool is then documented under `### mcp-call` (Utilities section) without the `ll-` prefix, making it technically inconsistent with the introductory framing.

## Expected Behavior

The introduction accurately describes the page's scope — either by noting that `mcp-call` is an additional utility not following the `ll-` prefix convention, or by grouping it under a clearly separated "Other Tools" / "Utilities" section heading so readers understand the scope of coverage.

## Proposed Solution

Update line 3 of `docs/reference/CLI.md` from:

```
Complete reference for all `ll-` command-line tools.
```

To something like:

```
Complete reference for `ll-` command-line tools and related utilities (including `mcp-call`).
```

Alternatively, add a brief note in the `### mcp-call` section header clarifying the naming convention difference.

## Impact

- **Priority**: P5 - Minor documentation inconsistency; no functional impact
- **Effort**: Small - Single line edit in one doc file
- **Risk**: Low - Documentation only, no code changes
- **Breaking Change**: No

## Scope Boundaries

- Only update the introduction text in `docs/reference/CLI.md`
- Do not rename `mcp-call` or add an `ll-` prefix alias
- Do not restructure the CLI.md page layout

## Labels

`documentation`, `dx`

## Status

**Open** | Created: 2026-06-08 | Priority: P5

## Source

Discovered during `/ll:audit-docs docs/reference` on 2026-06-08.


## Session Log
- `/ll:ready-issue` - 2026-06-08T16:33:09 - `963db350-29d5-4612-97ae-aec54c3b07c1.jsonl`

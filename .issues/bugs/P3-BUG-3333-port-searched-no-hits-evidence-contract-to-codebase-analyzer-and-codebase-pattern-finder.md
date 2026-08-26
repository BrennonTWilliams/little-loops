---
id: BUG-3333
type: BUG
title: Port Searched-No-Hits evidence contract to codebase-analyzer and codebase-pattern-finder
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-26'
captured_at: '2026-08-26T20:52:00Z'
---

# BUG-3333: Port Searched-No-Hits evidence contract to codebase-analyzer and codebase-pattern-finder

## Summary

BUG-3330 gave `agents/codebase-locator.md` a `### Searched, No Hits` output
group and matching evidence rules so negative claims ("symbol not found")
carry the same citation discipline as positive ones. The fix was
deliberately scoped to `codebase-locator.md` only — the agent where the
reproduction occurred — but the underlying failure mechanism (a filtered
Grep miss generalized into a tree-wide negative claim) is not unique to it.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

`agents/codebase-analyzer.md` and `agents/codebase-pattern-finder.md` share
the same section skeleton (`## Output Format` -> `## Important Guidelines`
-> `## What NOT to Do`) and the same no-Bash, Grep-only tool restriction as
`codebase-locator.md`. Either can assert an equally damaging false negative
off the same mechanism — e.g. "nothing calls this function" or "this branch
is unreachable" — from a filtered search that only covers a language/path
slice of the tree.

## Proposed Solution

Port the `### Searched, No Hits` contract from BUG-3330's fix to
`agents/codebase-analyzer.md` and `agents/codebase-pattern-finder.md`,
adapted to each agent's negative-claim vocabulary (e.g. "no caller found",
"pattern not present"):

- A mandatory output row for every explicitly named target not confirmed by
  a citation elsewhere in the output.
- Each row states the scope actually searched; a `type:`/`glob:`/`path:`
  filtered miss is evidence about that slice only.
- Re-run unfiltered before asserting absence, except when the caller scoped
  the question to a path or file type.
- Named exclusions carry the hit count inside the excluded path.
- One row per distinct target — no aggregate negatives.
- A matching prohibition bullet in `## What NOT to Do`.

See BUG-3330 for the root cause (filtered-Grep generalized into an
unfiltered negative) and the proven row wording/shape to reuse.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Issues

- BUG-3330 — origin of the `### Searched, No Hits` contract, fixed for
  `codebase-locator.md` only

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-26 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-08-26T20:52:06 - `0bf7be52-4470-4341-8647-365e248c9992.jsonl`

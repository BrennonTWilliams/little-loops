---
id: BUG-3150
type: BUG
title: issue-file mutators write unlocked and non-atomically (set-status, link, append-log)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-11'
captured_at: '2026-08-11T18:29:27Z'
---

# BUG-3150: issue-file mutators write unlocked and non-atomically (set-status, link, append-log)

## Summary

`ll-issues set-status` and `ll-issues link` perform read-modify-write on issue
files with **neither a lock nor an atomic write**, despite `file_utils` providing
both (`acquire_lock`, `atomic_write`) and despite `create`/`scaffold-epic`
already using them correctly.

`path.write_text(...)` truncates the target before writing, so the failure mode
is not merely a lost update — an interleaved or interrupted write can leave a
**torn or empty issue file**.

## Current Behavior

| Command | Lock | Atomic write | Worst case |
| --- | --- | --- | --- |
| `create` (`cli/issues/create.py:202`) | yes (`.issues/.id-alloc.lock`) | exclusive-create `open(path,"x")` | safe |
| `scaffold-epic` (`cli/issues/scaffold_epic.py:83`) | yes | — | safe |
| `set-status` (`cli/issues/set_status.py:127`, `:209`) | **no** | **no** (`write_text`) | torn / empty file |
| `link` (`cli/issues/link.py:149`, `:170`, `:202`) | **no** | **no** (`write_text`) | torn / empty file; half-linked graph |
| `append-log` (via `session_log.py:245`) | **no** | yes (`atomic_write`) | lost update only |

Two distinct defects:

1. **Non-atomic writes** (`set-status`, `link`) — a crash or concurrent write
   mid-`write_text` corrupts the issue file. This is data loss, not a race
   policy.
2. **Unlocked read-modify-write** (all three) — two writers interleave and one
   update is silently lost.

`link` additionally writes source and target as two independent unprotected
writes (`:149`/`:170` then `:202`), so an interruption between them leaves the
source claiming a link the target has no backlink for.

## Why it surfaces now

Tier 1 of EPIC-3127 was read-only, so this never came up. The CLI's implicit
safety property was "one human runs one command at a time." FEAT-3149 exposes
these same three mutations as MCP tools, which removes that assumption: multiple
hosts can call concurrently, and any of them can race a local `ll-auto` /
`ll-parallel` run. An MCP-layer lock cannot fix this — it would not serialize
against a direct CLI invocation — so the fix belongs here, at the CLI layer.

This is a pre-existing defect independent of MCP; FEAT-3149 only makes it
reachable in normal use.

## Expected Behavior

- `set-status`, `link`, and `append-log` each perform their read-modify-write
  under `acquire_lock`, and write via `atomic_write` rather than `write_text`.
- `link`'s source and target updates happen under a single lock hold so the
  backlink invariant cannot be broken by an interruption between them.

## Acceptance Criteria

1. `set-status` and `link` write via `atomic_write`; no `write_text` call remains
   on an issue-file mutation path.
2. All three mutators hold `acquire_lock` across read-modify-write.
3. `link` updates source and target under one lock hold.
4. A concurrency test asserts that N concurrent `set-status` invocations against
   one issue leave a valid, parseable file with exactly one winning status (no
   torn or empty file).
5. A test asserts `link` cannot leave a source-without-target backlink state when
   interrupted between its two writes.
6. `python -m pytest scripts/tests/` exits 0.

## Notes

Blast radius is wide: every project on this machine is `local-editable` against
this checkout, so these mutators are live everywhere with no reinstall step.
Prefer reusing `acquire_lock`/`atomic_write` exactly as `create.py` does over
introducing a new locking primitive.

Lock granularity is a design choice worth settling during implementation: a
single `.issues/` -wide lock is simplest and matches `.id-alloc.lock`, while a
per-file lock permits more concurrency. Given these are sub-millisecond writes,
the simpler whole-directory lock is likely correct.


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

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

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Steps to Reproduce

1. [Step 1]
2. [Step 2]
3. [Observe: description of the bug]

## Root Cause

- **File**: `path/to/file.py`
- **Anchor**: `in function buggy_func()`
- **Cause**: [Explanation of why bug happens]

## Error Messages

## Environment

## Frequency

## Location

- **File**: `path/to/file`
- **Line(s)**: [lines] (at scan commit: [COMMIT_HASH_SHORT])
- **Anchor**: `in function name()`
- **Code**:
```
# Relevant code snippet
```

## Reproduction Steps

## Proposed Fix

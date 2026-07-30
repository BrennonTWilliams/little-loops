---
id: ENH-2923
type: ENH
priority: P3
status: open
captured_at: "2026-07-30T02:14:15Z"
discovered_date: 2026-07-29
discovered_by: capture-issue
relates_to: []
---

# ENH-2923: Scope `ll-logs scan-failures` to a specific skill

## Summary

`ll-logs scan-failures --project <path>` reports failure clusters keyed by
tool+error signature across the entire project, with no way to filter to a
single skill (e.g. `review-epic`). Getting skill-specific analytics currently
requires running the full scan and manually grepping the output for the
skill name.

## Current Behavior

`ll-logs scan-failures --project <path>` accepts only `--project`/`--all`,
`--window-days`, `--capture`, `--capture-foreign`, and `-j/--json`. There is
no `--skill NAME` filter, so a user asking "what's failing for skill X"
must run the unfiltered scan and grep the (potentially large) output
themselves.

## Expected Behavior

`scan-failures` should accept an optional `--skill NAME` flag that limits
reported failure clusters to those attributable to the named skill,
mirroring how `ll-history-context --for-skill NAME` already gates on a
skill name for a related CLI.

## Motivation

Skill-scoped failure analytics let a maintainer check the health of one
skill (e.g. after a change to `review-epic`) without wading through
unrelated `ll-issues`/other-tool noise in the full project scan.

## Proposed Solution

Add `--skill NAME` to `scan-failures`. Failure clusters are currently keyed
by tool+error signature, not skill name, so this likely needs a lookup from
session events (tool invocation -> enclosing skill/command context) to
attribute a cluster to a skill correctly, rather than a simple string match
on the cluster's tool name.

## Impact

- **Priority**: P3 - convenience/analytics improvement, not blocking any workflow
- **Effort**: Medium - requires wiring skill attribution into cluster data, not just an argparse flag
- **Risk**: Low - additive, optional flag
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-07-30T02:14:15Z - `b1cb0370-8b55-4a10-a364-649e81045dd0.jsonl`

---

## Status

**Open** | Created: 2026-07-29 | Priority: P3

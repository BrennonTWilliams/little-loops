---
id: ENH-3423
type: ENH
title: verify-issues auto-mode notes read as unresolved after fixes
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T19:06:51Z'
---

# ENH-3423: verify-issues auto-mode notes read as unresolved after fixes

## Summary

`/ll:verify-issues` (`commands/verify-issues.md`) has no guidance for how the persisted
`## Verification Notes` section should be worded when `--auto` mode both diagnoses a defect
and applies the fix in the same pass.

Observed running `/ll:verify-issues ENH-3421 --auto`: the command found drifted `file:line`
anchors and one self-contradictory claim in the issue, applied the corrections per section 4's
auto-mode instructions, then wrote a Verification Notes section that opened with
`Verdict: NEEDS_UPDATE` — using the raw verdict-table label as the section lead. Read after the
fact, that reads as an outstanding action item even though the same edit had already resolved
everything it describes. The user had to ask "does it still need update after your changes?
shouldn't the verdict reflect this?" before it was reworded to "Verdict at time of check:
NEEDS_UPDATE (corrections below applied in the same pass...)".

Root cause: section 2.5 ("Check Mode Behavior") defines exactly how the verdict is persisted,
but only for `--check` mode, which never applies fixes — so its `verify_verdict: NON_VALID` /
`VALID` labels always describe the file's true current state. Section 4 ("Update Issue Files")
says to "document what changed or needs correction" but gives no comparable framing rule for
plain `--auto` mode, where verification and remediation happen in the same pass and a bare
verdict label goes stale the instant it's written.

Proposed fix: section 4 (or a new subsection) should instruct that when auto-mode applies
corrections in the same pass as detection, the Verification Notes text must distinguish
"verdict at detection" from "state after auto-fix" — e.g. requiring phrasing like "Verdict at
time of check: X (corrections below applied in this pass; issue is now accurate)" rather than a
bare verdict label, whenever non-destructive fixes were actually applied to the same sections
the note describes.


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

## Current Pain Point

## Success Metrics

## Scope Boundaries

## Backwards Compatibility

## API/Interface

```python
# Example interface/signature
```


## Session Log
- `/ll:capture-issue` - 2026-09-09T19:06:59 - `095aaa45-5f8e-445a-8993-2ec43b515f28.jsonl`

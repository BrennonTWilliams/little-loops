---
id: ENH-3576
type: ENH
title: Format-check repair coverage for missing and boilerplate sections with format-issue
  fallback
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:14Z'
parent: EPIC-3565
blocks:
- ENH-3577
---

# ENH-3576: Format-check repair coverage for missing and boilerplate sections with format-issue fallback

## Summary

`refine-to-ready-issue`'s normalization step runs `ll-issues format-check <ID> --fix --apply`
and tolerates failure with `|| true`. `format_check._REPAIR_DISPATCH` repairs exactly six gap
classes: `prose_dep_drift`, `duplicate_findings_block`, `duplicate_heading`,
`empty_provenance_stub`, `template_placeholders` (derivable tokens only) and
`duplicate_session_log`. Missing or renamed sections, empty sections and boilerplate have no
deterministic repair, and the closure never invokes `/ll:format-issue`. Refinement and
ready-issue may incidentally repair some gaps, but there is no guaranteed
check → apply → recheck cycle.

## Current Behavior

A structurally malformed issue can reach expensive research and scoring with gaps that no
step is responsible for repairing.

## Expected Behavior

1. Deterministic check
2. Apply supported repairs
3. Recheck
4. Invoke `/ll:format-issue` only for remaining template gaps
5. Author missing substantive content via the appropriate skill
6. Recheck

Run this before expensive research when structure is malformed, and again after
content-changing repairs. Advisory template preferences stay distinct from implementation
blockers.

## Motivation

Malformed structure is cheap to detect and fix deterministically. Leaving it to incidental repair during expensive research wastes budget and lowers score quality.

## Proposed Solution

- Add a `recheck_format` state after `normalize_structure` (`format-check --fix --apply`) that reads the remaining
  gap classes from `format-check --format json` (the CLI has no `--json` flag).
- On remaining `missing`/`boilerplate` in directive sections (at least `Summary` and
  `Acceptance Criteria`, matching Phase 1.8's allowlist), conditionally run
  `/ll:format-issue <ID> --auto`, bounded once per issue per run.
- Consider adding a deterministic `missing` fixer that inserts empty template headings for
  ceremonial sections.

## Program Design

### Types

- `_REPAIR_DISPATCH: dict[str, Callable[..., None]]` — gap-class → fixer table in `format_check.py`
- `FormatGaps.missing: list[str]` — remaining missing template sections, read via `format-check --format json`

### Signatures

- `_fix_missing_sections(config: BRConfig, source_id: str, path: Path, targets: list[str], *, apply: bool) -> None` — optional ceremonial-heading inserter (same shape as the other `_fix_*` fixers)
- `recheck_format` — new FSM shell state in `refine-to-ready-issue.yaml`; routes to `format_issue_fallback` when directive `missing`/`boilerplate` gaps remain

### Call Path

`cmd_format_check` -> `_apply_fix_dispatch` -> `_REPAIR_DISPATCH` fixer; loop: `normalize_structure` -> `recheck_format` -> `format_issue_fallback` (`/ll:format-issue <ID> --auto`, once per run) -> `clear_verify_verdict`

## Scope Boundaries

- Out of scope: changing `check_format_gaps` gap detection or its exit-code semantics
- Out of scope: authoring substantive content for empty directive sections beyond what `/ll:format-issue --auto` infers
- Out of scope: sweep mode (`--all --fix --apply`) repairs; new fixers stay single-issue only (see `_SWEEP_SAFE_REPAIRS`)
- Out of scope: consolidating the preparation pipeline into one controller (ENH-3577)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — normalization step
- `scripts/little_loops/cli/issues/format_check.py` — `_REPAIR_DISPATCH` (optional new fixer)

### Dependent Files (Callers/Importers)
- `skills/confidence-check/SKILL.md` Phase 1.8 (`STRUCT_GAP`), corrected in BUG-3570

### Similar Patterns
- Existing `_fix_*` fixers in `format_check.py`

### Tests
- `scripts/tests/test_ll_issues_format_check.py`, `scripts/tests/test_builtin_loops.py`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `recheck_format` after `format-check --fix --apply` in refine-to-ready-issue
2. Conditionally run `/ll:format-issue --auto` once for remaining directive gaps
3. Optionally add a ceremonial-`missing` heading inserter to `_REPAIR_DISPATCH`
4. Tests for the conditional format-issue route

## Impact

- **Priority**: P3
- **Effort**: Medium
- **Risk**: Low

## Acceptance Criteria

- [ ] A remaining directive-section `missing` gap after `--fix` triggers one `/ll:format-issue` pass
- [ ] Normalization no longer silently swallows an unrepaired directive gap

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- `format-check --json` does not exist; the flag is `--format json` — corrected.
- The normalization state is `normalize_structure` in `refine-to-ready-issue.yaml`; it runs after `refine_issue`/`refine_followup`/`wire_issue`, not before research. The "run before expensive research" expectation therefore needs a second placement, not just a `recheck_format` after the existing state — noted for implementation.
- All six `_REPAIR_DISPATCH` classes, the `|| true` tolerance and the Phase 1.8 `STRUCT_GAP` allowlist verified accurate.

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-25T17:14:23 - `6249b55a-80e7-48d1-ad8e-6ad301b4a4d0.jsonl`
- `/ll:verify-issues` - 2026-09-25T15:27:34 - `bc279096-6a89-4a82-b7c2-8e6f11cc30f5.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:32 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`

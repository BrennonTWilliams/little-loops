---
id: BUG-2009
title: "autodev/recursive-refine: find glob fails on issue ID type-prefix mismatch and missing priority prefix"
type: BUG
priority: P3
status: open
captured_at: '2026-06-07T21:35:32Z'
discovered_date: '2026-06-07'
discovered_by: capture-issue
relates_to:
- BUG-2003
labels:
- autodev
- recursive-refine
- loop-defect
---

# BUG-2009: autodev/recursive-refine find glob fails on ID type-prefix mismatch

## Summary

The same defective issue-file resolution that BUG-2003 fixed in the `rn-*` loop family
still exists in `loops/autodev.yaml` and `loops/recursive-refine.yaml`. Both use a raw
`find .issues -name "*-$ID-*"` glob to locate an issue/child/parent file. That glob fails
in two ways:

1. **Type-prefix mismatch** — `*-$ID-*` embeds the full `TYPE-NNN`, so a stale or mismatched
   prefix (e.g. `FEAT-1903` for a file named `P4-ENH-1903-*.md`) never matches, even though
   issue numbers are globally unique and the file plainly exists.
2. **Missing priority prefix** — the leading literal `-` in `*-$ID-*` requires a character
   before the type token, so a file with no `P#-` prefix (e.g. `FEAT-1725-foo.md`) is missed.

BUG-2003 fixed the `rn-*` sites by (a) making `_resolve_issue_id` in
`scripts/little_loops/cli/issues/show.py` treat the type prefix as advisory and (b) routing
the shell sites through `ll-issues path`. That Layer-0 resolver fix does **not** reach these
loops because they call `find` directly rather than `ll-issues path`.

## Affected Sites

| Site (var) | File:Line | Resolves |
|---|---|---|
| `INFLIGHT_FILE` | `autodev.yaml:307` | in-flight issue |
| `child_file` | `autodev.yaml:344` | decomposed child |
| `PARENT_FILE` | `autodev.yaml:376` | parent issue |
| `child_file` | `autodev.yaml:512` | decomposed child |
| `PARENT_FILE` | `autodev.yaml:527` | parent issue |
| `child_file` | `recursive-refine.yaml:243` | decomposed child |
| `PARENT_FILE` | `recursive-refine.yaml:302` | parent issue |
| `ISSUE_FILE` | `recursive-refine.yaml:449` | target issue |
| `child_file` | `recursive-refine.yaml:542` | decomposed child |
| `PARENT_FILE` | `recursive-refine.yaml:590` | parent issue |

(10 sites: 5 in `autodev.yaml`, 5 in `recursive-refine.yaml`.)

## Root Cause

Identical to BUG-2003: `find .issues -name "*-$ID-*"` requires the exact type token *and*
a character before it. Issue numbers are globally unique across types
(`get_next_issue_number`), so the type prefix is redundant strictness and the leading hyphen
is an incorrect anchor.

## Expected Behavior

- Each site locates the issue/child/parent file regardless of a stale/mismatched type prefix
  (e.g. `FEAT-1903` resolves `ENH-1903`).
- A file with no priority prefix (e.g. `FEAT-1725-foo.md`) is located at every site.
- Behavior matches the now-tolerant `rn-*` loops.

## Proposed Solution

Mirror the BUG-2003 Layer-2 fix: replace each `find .issues -name "*-$ID-*" ! -path
"*/completed/*" | head -1` with `ll-issues path "$ID" 2>/dev/null`, which inherits the
type-prefix-tolerant shared resolver (`_resolve_issue_id`) fixed in BUG-2003. The `child_file`
sites that span multiple lines (continuation `\`) should be collapsed to the single-call form.

Note the `${captured.input.output}` interpolation at several sites — substitute the resolved
context value into the `ll-issues path` argument the same way the existing `find` arg does.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — lines 307, 344, 376, 512, 527
- `scripts/little_loops/loops/recursive-refine.yaml` — lines 243, 302, 449, 542, 590

### Similar Patterns
- BUG-2003 (the `rn-*` fix) is the exact template; reuse `ll-issues path` rather than
  re-implementing the glob.

### Tests
- N/A at the YAML level — validated via `ll-loop validate` + `ll-loop run` integration. The
  underlying resolver tolerance is already covered by `TestPathPrefixTolerant` in
  `scripts/tests/test_issues_path.py` (added in BUG-2003).

## Acceptance Criteria

- All 10 sites use `ll-issues path` (or an equivalent tolerant resolution); no
  `find .issues -name "*-$..."` glob remains in either loop file.
- An issue/child/parent with a mismatched type prefix resolves at every site.
- A file with no priority prefix resolves at every site.
- `ll-loop validate autodev` and `ll-loop validate recursive-refine` both pass.

## Impact

- **Priority**: P3 — latent; same defect class as the P2 BUG-2003 but not yet observed
  causing a run failure in these loops. Will surface the same way (consumed slot / mis-routed
  child / unresolved parent) once a mismatched or un-prefixed ID flows through.
- **Effort**: Small — mechanical 10-site swap mirroring BUG-2003; no new resolver logic needed.
- **Risk**: Low — additive tolerance; correctly-prefixed IDs unaffected.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-07 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-06-07T21:35:32 - `da163c1d-378a-4a58-b8d2-88910a03d4ca.jsonl`

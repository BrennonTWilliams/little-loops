---
id: BUG-2009
title: 'autodev/recursive-refine: find glob fails on issue ID type-prefix mismatch
  and missing priority prefix'
type: BUG
priority: P3
status: done
captured_at: '2026-06-07T21:35:32Z'
completed_at: '2026-06-07T22:31:53Z'
discovered_date: '2026-06-07'
discovered_by: capture-issue
relates_to:
- BUG-2003
labels:
- autodev
- recursive-refine
- loop-defect
confidence_score: 100
outcome_confidence: 85
score_complexity: 25
score_test_coverage: 15
score_ambiguity: 25
score_change_surface: 20
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

## Current Behavior

`autodev.yaml` and `recursive-refine.yaml` resolve issue files via a raw shell glob at 10
sites:

```bash
find .issues -name "*-$ID-*" ! -path "*/completed/*" | head -1
```

This returns an empty string in two scenarios, causing the loop to operate on a missing file
path:
1. **Type-prefix mismatch** — `$ID` contains a type token (e.g. `FEAT-1903`) that differs
   from the file's actual prefix (`ENH-1903`), so no filename matches.
2. **Missing priority prefix** — a file like `FEAT-1725-foo.md` (no `P#-`) is missed because
   the leading `-` before `$ID` requires at least one character before the token.

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

## Steps to Reproduce

1. Create a `.issues/` file whose on-disk type prefix differs from the ID used by the loop
   (e.g. file is `P4-ENH-1903-*.md` but loop state references `FEAT-1903`), or create a
   file without a `P#-` priority prefix (e.g. `FEAT-1725-foo.md`).
2. Trigger `autodev.yaml` or `recursive-refine.yaml` with that issue ID (via `ll-loop run`
   or an in-progress session that reaches one of the 10 resolution sites).
3. Observe: the `INFLIGHT_FILE`, `child_file`, or `PARENT_FILE` variable resolves to an
   empty string — the loop either mis-routes, drops the slot, or exits with an empty file path.

## Expected Behavior

- Each site locates the issue/child/parent file regardless of a stale/mismatched type prefix
  (e.g. `FEAT-1903` resolves `ENH-1903`).
- A file with no priority prefix (e.g. `FEAT-1725-foo.md`) is located at every site.
- Behavior matches the now-tolerant `rn-*` loops.

## Motivation

BUG-2003 confirmed this defect class causes real loop failures: consumed slots, mis-routed
children, unresolved parents. The 10 unpatched sites in `autodev.yaml` and
`recursive-refine.yaml` present identical risk — it is only a matter of when a
type-prefix mismatch or un-prefixed ID flows through. The fix is a mechanical 10-site swap
that mirrors an already-proven patch, carries negligible risk, and requires no new resolver
logic.

## Proposed Solution

Mirror the BUG-2003 Layer-2 fix: replace each `find .issues -name "*-$ID-*" ! -path
"*/completed/*" | head -1` with `ll-issues path "$ID" 2>/dev/null`, which inherits the
type-prefix-tolerant shared resolver (`_resolve_issue_id`) fixed in BUG-2003. The `child_file`
sites that span multiple lines (continuation `\`) should be collapsed to the single-call form.

Note the `${captured.input.output}` interpolation at several sites — substitute the resolved
context value into the `ll-issues path` argument the same way the existing `find` arg does.

## Implementation Steps

1. Replace all 5 `find .issues -name "*-$ID-*"` resolution sites in `autodev.yaml`
   (at `INFLIGHT_FILE`, `child_file` ×2, `PARENT_FILE` ×2) with `ll-issues path "$ID" 2>/dev/null`.
2. Replace all 5 corresponding sites in `recursive-refine.yaml` with `ll-issues path "$ID" 2>/dev/null`.
3. Collapse any multi-line continuation (`\`) forms to the single-call pattern used by `rn-*` post BUG-2003.
4. Run `ll-loop validate autodev` and `ll-loop validate recursive-refine` — both must pass.
5. Smoke-test by running either loop with a mismatched-prefix ID and confirming the file is located.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — lines 307, 344, 376, 512, 527
- `scripts/little_loops/loops/recursive-refine.yaml` — lines 243, 302, 449, 542, 590

### Similar Patterns
- BUG-2003 (the `rn-*` fix) is the exact template; reuse `ll-issues path` rather than
  re-implementing the glob.
- Concrete reference implementations to mirror: `rn-decompose.yaml:109`
  (`CHILD_FILE=$(ll-issues path "$child_id" 2>/dev/null)`), `rn-implement.yaml:77`
  (`resolved=$(ll-issues path "$raw_id" 2>/dev/null)`), `rn-remediate.yaml:84,123,312`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against the current codebase (2026-06-07):_

- **All 10 sites confirmed verbatim** at the claimed line numbers (autodev: 307, 344, 376,
  512, 527; recursive-refine: 243, 302, 449, 542, 590), each using
  `find .issues -name "*-$ID-*" ! -path "*/completed/*"`. The three multi-line continuation
  forms are autodev:344, recursive-refine:243, and recursive-refine:449 — collapse these to
  the single-call form (the trailing `grep -q "Decomposed from $PARENT_ID"`/`decision_needed`
  guards stay unchanged; only the assignment line changes).
- **The swap preserves the `! -path "*/completed/*"` exclusion implicitly.**
  `_resolve_issue_id` (`scripts/little_loops/cli/issues/show.py:91-103`) searches **only**
  `config.issue_categories` dirs (`bugs/`, `features/`, `enhancements/`, `epics/`). `completed/`
  exists on disk but is **not** a category, so `ll-issues path` never returns a completed file.
  No separate exclusion flag is needed in the replacement — dropping `! -path "*/completed/*"`
  is safe and behavior-preserving.
- **Tolerance verified empirically**: `ll-issues path FEAT-2009` resolves the on-disk
  `BUG-2009` file. The resolver prefers an exact-type match but falls back to the unambiguous
  numeric match when the type prefix is stale (`show.py:108-116`), and globs `*-{numeric_id}-*.md`
  with no leading-character requirement (`show.py:103`) — covering both failure modes in the bug.
- **Out-of-scope inconsistency (note for the implementer, do not fix here)**: the
  `child_file` guards in `autodev.yaml`/`recursive-refine.yaml` test only
  `grep -q "Decomposed from $PARENT_ID"`, whereas the post-BUG-2003 `rn-decompose.yaml:111-113`
  guard also accepts `parent:.*$PARENT_ID` frontmatter. Aligning that guard is a separate
  enhancement; this bug is scoped to the resolution swap only.

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

## Resolution

**Status**: done | Resolved: 2026-06-07

Replaced all 10 `find .issues -name "*-$ID-*" ! -path "*/completed/*" | head -1` resolution
sites with `ll-issues path "$ID" 2>/dev/null`, inheriting the type-prefix-tolerant shared
resolver fixed in BUG-2003. The three multi-line continuation forms (autodev `child_file`,
recursive-refine `child_file`, recursive-refine `ISSUE_FILE`) were collapsed to the single-call
pattern; the trailing `grep -q "Decomposed from ..."` / `decision_needed` guards are unchanged.

**Files modified**:
- `scripts/little_loops/loops/autodev.yaml` — 5 sites (`INFLIGHT_FILE`, `child_file` ×2, `PARENT_FILE` ×2)
- `scripts/little_loops/loops/recursive-refine.yaml` — 5 sites (`child_file` ×2, `PARENT_FILE` ×2, `ISSUE_FILE`)

**Verification**:
- No `find .issues -name "*-$..."` glob remains in either loop (grep: NONE).
- `ll-loop validate autodev` → valid; `ll-loop validate recursive-refine` → valid (pre-existing
  MR-3 shared-state warnings are unrelated and out of scope).
- Smoke test: `ll-issues path FEAT-2009` resolves the on-disk `BUG-2009` file (mismatched-prefix
  tolerance confirmed); correct-prefix lookup unchanged.
- Resolver tolerance regression-covered by `TestPathPrefixTolerant` — 17 tests pass.

## Status

**Done** | Created: 2026-06-07 | Resolved: 2026-06-07 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-06-07T22:31:53 - `94001b17-192e-4675-8b12-449cc4ed8e69.jsonl`
- `/ll:refine-issue` - 2026-06-07T22:19:00 - `ec3552fa-7077-4532-8b37-a0d09aeb3ffd.jsonl`
- `/ll:format-issue` - 2026-06-07T21:41:33 - `0d7c59d4-7959-43a0-a3fb-6500f7a0b2b8.jsonl`
- `/ll:capture-issue` - 2026-06-07T21:35:32 - `da163c1d-378a-4a58-b8d2-88910a03d4ca.jsonl`

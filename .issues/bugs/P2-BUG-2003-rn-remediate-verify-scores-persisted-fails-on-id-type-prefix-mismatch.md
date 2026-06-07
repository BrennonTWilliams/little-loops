---
id: BUG-2003
title: 'rn-remediate: verify_scores_persisted fails when issue ID type prefix mismatches
  filename'
type: BUG
priority: P2
status: done
captured_at: '2026-06-07T00:00:00Z'
completed_at: '2026-06-07T21:33:43Z'
discovered_date: '2026-06-07'
discovered_by: audit-loop-run
relates_to:
- BUG-1973
- ENH-1977
labels:
- rn-implement
- rn-remediate
- loop-defect
---

# BUG-2003: rn-remediate verify_scores_persisted fails on ID type-prefix mismatch

## Summary

`verify_scores_persisted` in `rn-remediate` uses `find .issues -name "*-$ID-*"` to confirm
that `/ll:confidence-check` wrote scores back to the issue file. When the caller passes a
mismatched type prefix (e.g., `FEAT-1903` for an issue whose filename is `P4-ENH-1903-*.md`),
the `find` returns empty, the state exits 1, and the sub-loop routes to `emit_scores_missing →
failed`. The issue is recorded as an implementation failure even though confidence-check
succeeded and wrote valid scores.

## Current Behavior

Run `rn-implement-20260607T122052`:

1. Queue contained `FEAT-1903`; actual file is `P4-ENH-1903-document-ll-parallel-...md`
2. `/ll:confidence-check FEAT-1903 --auto` → exit 0, readiness 70/100, outcome 86/100,
   scores written to ENH-1903 frontmatter
3. `verify_scores_persisted` runs `find .issues -name "*-FEAT-1903-*"` → returns empty
4. State exits 1 → `emit_scores_missing` → `failed` (sub-loop terminal)
5. `FEAT-1903` written to `failures.txt`; remediation slot consumed with no output

`ll-issues show FEAT-1903` also returns "Error: Issue 'FEAT-1903' not found." — confirming
that `ll-issues` resolution also requires the exact type prefix.

## Expected Behavior

- `verify_scores_persisted` locates the issue file regardless of whether the queued ID uses
  the correct type prefix (e.g., `FEAT-1903` finds `ENH-1903`)
- When `confidence-check` exits 0 and writes scores, `verify_scores_persisted` exits 0
- No `SCORES_MISSING` failure when confidence-check succeeded
- `ll-loop run rn-implement "FEAT-1903"` proceeds through `verify_scores_persisted` without error

## Steps to Reproduce

1. Add an issue to the rn-implement queue using a mismatched type prefix (e.g., `FEAT-1903`
   where the actual file is `P4-ENH-1903-*.md`)
2. Run `ll-loop run rn-remediate` targeting that issue
3. Observe `/ll:confidence-check FEAT-1903 --auto` exits 0 and writes scores to ENH-1903 frontmatter
4. Observe `verify_scores_persisted` runs `find .issues -name "*-FEAT-1903-*"` → returns empty
5. State exits 1 → routes to `emit_scores_missing` → `failed` (sub-loop terminal)
6. Issue appears in `failures.txt` despite successful confidence-check run

## Root Cause

`verify_scores_persisted` uses a `find` glob that requires the exact type token in the filename
(`*-FEAT-1903-*`). The confidence-check skill resolves IDs via a different mechanism (number-only
scan) and can find `ENH-1903` when given `FEAT-1903`. The two lookup strategies are misaligned.

**This is not a single-state bug.** The same defective `find .issues -name "*-$ID-*"` glob — and
the same `ll-issues show`-based ID resolution that requires an exact type prefix — appear in **five
sites** across the two sub-loops. The leading literal `-` in `*-$ID-*` *also* fails on files with
**no priority prefix** (e.g. `FEAT-1725-foo.md`, where there is no character before `FEAT` to
satisfy the hyphen), so the fix must address both the type-prefix mismatch and the missing-prefix
case (the latter was the actual failure observed in run `rn-implement-20260607T203138`):

| Site | File | Mechanism | Failure mode |
|---|---|---|---|
| `verify_scores_persisted` (~L75) | `rn-remediate.yaml` | `find "*-$ID-*"` | type mismatch + no-prefix |
| `check_outcome` (~L112) | `rn-remediate.yaml` | `find "*-$ID-*"` | type mismatch + no-prefix |
| `verify_re_assess_scores` (~L286) | `rn-remediate.yaml` | `find "*-$ID-*"` | type mismatch + no-prefix |
| `diagnose` (~L148) | `rn-remediate.yaml` | `ll-issues show "$ID" --json` | type mismatch → empty → silently echoes `DECOMPOSE` |
| `detect_children` (~L108) | `rn-decompose.yaml` | `find "*-$child_id-*"` | type mismatch + no-prefix |

The re-scoring loop central to the design (`re_assess → verify_re_assess_scores →
check_convergence → diagnose`) passes through three of these sites on **every** remediation pass.
Fixing only `verify_scores_persisted` means a type-mismatched or un-prefixed issue passes the
first score gate and then fails on the **second** pass at `verify_re_assess_scores` — so the narrow
fix does not actually unblock the refine/wire/decide path.

## Proposed Solution

Two layers, both required:

**Layer 1 — normalize IDs to canonical filename form at the entry point.** Resolve each input ID
against actual filenames before it propagates downstream. The cleanest place is `init` in
`rn-implement` (seed the queue with canonical IDs) plus the parameter hand-off into `rn-remediate`
/ `rn-decompose`. This fixes the *type-prefix mismatch* class at the source.

**Layer 2 — harden the glob at every site so it tolerates a missing priority prefix.** Normalization
alone does NOT fix un-prefixed files (`*-FEAT-1725-*` still misses `FEAT-1725-foo.md`). Replace the
leading-hyphen glob with a substring match plus a numeric fallback at **all five sites**:

```bash
# Applies to verify_scores_persisted, check_outcome, verify_re_assess_scores
# (rn-remediate.yaml) and detect_children (rn-decompose.yaml).
ISSUE_FILE=$(find .issues -name "*$ID*" ! -path "*/completed/*" 2>/dev/null | head -1)
if [ -z "$ISSUE_FILE" ]; then
  ID_NUM=$(echo "$ID" | grep -oE '[0-9]+$')
  ISSUE_FILE=$(find .issues -name "*-${ID_NUM}-*" ! -path "*/completed/*" 2>/dev/null | head -1)
fi
if [ -z "$ISSUE_FILE" ]; then
  echo "ERROR: Issue file not found for $ID"
  exit 1
fi
```

For `diagnose`, which resolves via `ll-issues show "$ID" --json`: Layer 1 normalization makes the
canonical ID resolve, but also add a guard so an empty `--json` result no longer silently falls
through to `echo "DECOMPOSE"` (that masks a resolution failure as a real routing decision) — emit
an explicit error/token instead.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` — `verify_scores_persisted`, `check_outcome`,
  `verify_re_assess_scores`, and `diagnose` (resolution guard)
- `scripts/little_loops/loops/rn-decompose.yaml` — `detect_children`
- `scripts/little_loops/loops/rn-implement.yaml` — `init` (Layer 1 ID normalization before seeding
  `queue.txt`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/rn-implement.yaml` — populates the queue consumed by rn-remediate and rn-decompose

### Similar Patterns
- `ll-issues path` / `ll-issues show` use number-only scan; reuse that resolution (or call it)
  rather than re-implementing the glob per state
- Audit Proposal 1 (`rn-implement-audit-2026-06-07.md`) lists the same four affected states

### Tests
- N/A — loop YAML behavior is validated via `ll-loop run` integration

### Documentation
- N/A

### Configuration
- N/A

## Acceptance Criteria

- Running `ll-loop run rn-implement "ENH-1903"` or `ll-loop run rn-implement "FEAT-1903"` (with
  the mismatched type prefix) both correctly locate the file and proceed past every score gate
- An issue file with **no priority prefix** (e.g. `FEAT-1725-foo.md`) is located at all five sites
- An issue that takes the refine/wire/decide path completes a **second** remediation pass without a
  SCORES_MISSING failure at `verify_re_assess_scores`
- `detect_children` in `rn-decompose` locates child files when their type prefix differs from the
  queued ID
- `diagnose` no longer emits a `DECOMPOSE` token purely because `ll-issues show --json` returned
  empty — an unresolved ID surfaces as an explicit failure
- No SCORES_MISSING failure when confidence-check successfully writes scores to the issue file

## Impact

- **Priority**: P2 — Blocks the remediation slot for affected issues *on every pass*; the un-prefixed-file variant caused a 0% implementation rate (0/1) in run `rn-implement-20260607T203138`
- **Effort**: Small-to-Medium — repeats the same fallback pattern across five sites in three loop files plus a one-time ID-normalization step in `init`
- **Risk**: Low — additive fallback; the exact-match path is preserved, so correctly-prefixed IDs are unaffected. Substring glob `*$ID*` is marginally broader; the numeric fallback and `! -path "*/completed/*"` filter keep matches scoped
- **Breaking Change**: No

## Resolution

Fixed at the **root cause** plus the requested defense-in-depth layers:

- **Layer 0 (root cause)** — `_resolve_issue_id` in `scripts/little_loops/cli/issues/show.py`
  now treats the type prefix and priority as *advisory*. Because issue numbers are globally
  unique across types (`get_next_issue_number`), a numeric match is unambiguous: the resolver
  prefers an exact-type (then exact-priority) match but falls back to the numeric match when the
  caller's prefix is stale (`FEAT-1903` → `ENH-1903`). The resolver's existing `*-{num}-*.md`
  glob already tolerated a missing priority prefix. This single fix aligns every `ll-issues`
  subcommand (`path`, `show`, `check-flag`, `check-readiness`, `set-scores`, `set-status`) — all
  of which share this resolver — with confidence-check's tolerant resolution.
- **Layer 1 (normalize at entry)** — `rn-implement.yaml` `init` normalizes each seeded queue ID
  to canonical `TYPE-NNN` via `ll-issues path`, so a stale prefix and cross-type duplicate refs
  collapse to one identity before the visited-set / cycle detection keys on them.
- **Layer 2 (dedupe resolution at the 5 sites)** — replaced `find .issues -name "*-$ID-*"` (which
  fails on both type-mismatch and missing priority prefix) with `ll-issues path "$ID"` at
  `verify_scores_persisted`, `check_outcome`, `verify_re_assess_scores` (rn-remediate.yaml) and
  `detect_children` (rn-decompose.yaml). `diagnose`'s empty-`--json` guard now `exit 1`s (routing
  to `emit_implement_failed`) instead of silently echoing `DECOMPOSE` (AC5).

**Tests**: added `TestPathPrefixTolerant` (6 cases) to `scripts/tests/test_issues_path.py`
covering mismatched type prefix, missing priority prefix, both-at-once, numeric-only on an
un-prefixed file, exact-type preference, and a preserved not-found path. TDD red→green confirmed.

**Verification**: `ll-issues show FEAT-1903 --json` now resolves to `ENH-1903` (previously
"not found"). Full suite compared against a pristine-tree baseline: identical 315 pre-existing
environmental failures / 78 errors on both, with **+6 new passing tests** from this change — zero
regressions. ruff + mypy clean on the changed Python. All three loops pass `ll-loop validate`.

**Follow-up (out of scope)**: the same defective `find .issues -name "*-$ID-*"` glob remains in
`loops/autodev.yaml` and `loops/recursive-refine.yaml` (which use raw `find`, not `ll-issues path`,
so the Layer 0 fix does not reach them). Worth a separate issue.

## Status

**Done** | Created: 2026-06-07 | Completed: 2026-06-07 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-06-07T21:09:39 - `43eafcad-fab4-4d06-bb01-972d6fe15051.jsonl`
- `/ll:format-issue` - 2026-06-07T20:47:02 - `57f27ab7-f753-43a9-be87-54b2970f859d.jsonl`
- `/ll:manage-issue` - 2026-06-07T21:33:43 - `da163c1d-378a-4a58-b8d2-88910a03d4ca.jsonl`

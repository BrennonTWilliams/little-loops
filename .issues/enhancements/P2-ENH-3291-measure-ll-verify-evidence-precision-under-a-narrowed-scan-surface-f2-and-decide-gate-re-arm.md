---
id: ENH-3291
type: ENH
title: Measure ll-verify-evidence precision under a narrowed scan surface (F2) and
  decide gate re-arm
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-22'
captured_at: '2026-08-22T14:19:01Z'
labels:
- verify-issues
- evidence
- precision
- gate
- measurement
relates_to:
- BUG-3282
---

# ENH-3291: Measure ll-verify-evidence precision under a narrowed scan surface (F2) and decide gate re-arm

## Summary

`ll-verify-evidence` (BUG-3282) ships and is wired, but its `EVIDENCE_UNVERIFIED` verdict is
**advisory only** — `check_evidence_unverified` in
`scripts/little_loops/loops/refine-to-ready-issue.yaml` falls through to
`check_proposal_unsound` on every edge (`on_yes`/`on_no`/`on_error`). It was demoted because a
hand-labelled 30-finding sample measured **~0.13–0.20 precision** against the **0.30** blocking
bar. This issue owns the work that decides whether the gate can re-arm: narrow the scan surface
(fallback F2), expand the labelled sample, re-measure, and either restore routing or record
plainly that the detector stays advisory.

## Current Behavior

The detector is fully wired — the verdict is detected, persisted to frontmatter, and visible in
run logs — but it never routes. Consequences:

- A real fabrication produces `EVIDENCE_UNVERIFIED` and the loop proceeds anyway. The detector
  cannot prevent the class of defect BUG-3282 was opened for.
- The repo-wide `--all` gate is green only because **278 findings are grandfathered** into
  `.ll/evidence-baseline.json`. That baseline is suppression, not correctness.
- `test_check_evidence_unverified_is_advisory_not_routing` in
  `scripts/tests/test_builtin_loops.py` asserts every edge avoids `check_reconcile_limit` and
  carries the re-arm condition in its docstring, so re-arming cannot happen silently.

Below 0.30 precision, routing is net-negative **even when the gate is right**: a false
`EVIDENCE_UNVERIFIED` sends a *correct* issue into `reconcile_issue`, which rewrites directive
sections it had no reason to touch.

## Expected Behavior

The re-arm decision is made from measured numbers against pre-committed bars, and the numbers are
reproducible from artifacts in the repo rather than remembered from a session. Either the gate
routes again because it earned it, or the advisory posture is recorded as the deliberate,
measured outcome.

## Scope Boundaries

**In scope**: narrowing the scan surface (F2), expanding and recording the labelled sample,
measuring the four metrics, and the routing decision that follows.

**Out of scope**: fallback F1 (turning `TestRepoGate` from "zero beyond baseline" into a rate
gate). F1 addresses gate *brittleness* under normal churn, which is a different problem from the
imprecision that caused the demotion — it does not license re-arming and must not be bundled in
as if it did. Also out of scope: further attribution or span-kind tuning, since the residual class
is paraphrase and provably out of reach of both.

## Motivation

BUG-3282 shipped a working detector that currently cannot prevent the defect it was built for.
The fabricated-evidence class it targets is exactly the failure that survives ordinary review —
an issue whose code references all check out but whose motivating quote was invented — so leaving
the gate advisory leaves that hole open.

The cost of guessing instead of measuring runs both ways. Re-arming at ~0.15 precision means
roughly five correct issues are pushed into `reconcile_issue` for every real fabrication caught,
and `reconcile_issue` rewrites directive sections — so the fix would damage more issues than the
bug does. Staying advisory forever without ever measuring means carrying a detector, a 278-entry
grandfather baseline, and a loop state that pay no rent. Only a measurement settles it, and the
measurement is cheap relative to either mistake.

## Proposed Solution

**F2 — narrow the scan surface to `.md`/issue artifacts only** (~316 → ~160 spans).

*Hypothesis* (specific and falsifiable): paraphrase false positives concentrate in quoted
**code**, so dropping code artifacts lifts precision without costing recall. This is defensible
on BUG-3282's own framing rather than as a precision dodge: quoted code vs. source is already
the `verify-issues.md` §B.0 check's job, so the two checks stop overlapping.

**Then re-measure and decide from the numbers, not from intent.**

### Measurement protocol

Blocking requires **all four**:

| Metric | Bar |
|---|---|
| Recall on labelled true-fabrications | **1.00** (non-negotiable) |
| Precision | **≥ 0.30** |
| Corpus rate | **≤ 0.15** findings/file |
| Net-new findings per 100 commits of normal churn | **≤ 5** (`--all` at `HEAD` vs `HEAD~100`, same baseline, diffed) |

**Sample-size caveat.** The existing ~0.13–0.20 figure comes from a hand-labelled sample of
**30**. At that size the error bars are wide enough that "did F2 clear 0.30?" may simply not be
answerable. Expanding the labelled set is a **prerequisite for a trustworthy verdict, not an
optional extra** — a re-measurement landing at 0.28 vs 0.32 on n=30 is decisive in neither
direction.

### If it clears

Restore `on_yes: check_reconcile_limit` in
`scripts/little_loops/loops/refine-to-ready-issue.yaml`. Deliberately a one-line edit, but
**guarded** — update `test_check_evidence_unverified_is_advisory_not_routing` in the same commit.

### If it does not clear

The honest outcome is that this detector stays advisory indefinitely. **Record that rather than
reaching for a weaker bar.** The remaining fallback F1 (rate gate — change `TestRepoGate` from
"zero beyond baseline" to "≤ N beyond baseline and ≤ M per file") addresses gate *brittleness*,
not the imprecision-rewrites-correct-issues problem, so it is not a substitute for F2 and does
not license re-arming.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/verify_evidence.py` — F2's surface narrowing. The natural seam is
  artifact resolution (`resolve_artifact`), which already knows the cited artifact's path, so a
  non-`.md` target can be dropped there without touching span extraction.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — the `check_evidence_unverified` state
  (`:355`) and its `on_yes` edge; the ASCII flow comment at `:16-17` names the F3 posture and must
  move with it. **Only if the measurement clears.**

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py` — `main_verify_evidence` re-export; unchanged unless the
  CLI surface gains a flag.
- `.ll/evidence-baseline.json` — 278 grandfathered findings. F2 changes which spans are scanned,
  so the baseline needs regenerating; see the `--update-baseline` gotcha in Notes.

### Similar Patterns
- `scripts/little_loops/cli/verify_private_refs.py` — the three-mode enforcement shape
  (changed-files / `--added-only` / `--all` + baseline) that `verify_evidence` mirrors.

### Tests
- `scripts/tests/test_verify_evidence.py` — F2's surface-narrowing behavior and its fixtures.
- `scripts/tests/test_builtin_loops.py` —
  `test_check_evidence_unverified_is_advisory_not_routing` is the re-arm guard; it must be updated
  in the same commit as any `on_yes` change, never separately.
- `scripts/tests/test_issue_parser.py` — `_ALLOWLIST` pins `cli/verify_evidence.py` by **line
  number**; any edit that shifts the `_ISSUE_ID_RE` definition requires re-deriving it.

### Documentation
- `docs/reference/CLI.md` — the `ll-verify-evidence` section, if the scan surface or flags change.
- `scripts/little_loops/cli/verify_evidence.py` module docstring — the **Scope** paragraph states
  which artifacts are in scope and is the first thing a reader trusts.

### Configuration
- `.ll/evidence-baseline.json` (tracked baseline), `.ll/evidence-verdict-cache.json` (untracked
  memoization — safe to delete at any time).

## Implementation Steps

1. **Expand the labelled set first.** Label enough findings that the precision estimate can
   distinguish 0.28 from 0.32; record the labels in-repo so the number is reproducible. Doing this
   before F2 also gives a like-for-like before/after on the same labelled corpus.
2. **Implement F2** — restrict the scan to `.md`/issue artifacts at the artifact-resolution seam.
3. **Re-measure all four metrics** — precision, recall on labelled true-fabrications, corpus rate,
   and the 100-commit net-new delta (`--all` at `HEAD` vs `HEAD~100`, same baseline, diffed).
4. **Regenerate the baseline** against the narrowed surface, scanning with an *empty* baseline.
5. **Decide from the numbers.** If all four bars clear: restore `on_yes: check_reconcile_limit`
   and update the guard test in the same commit. If not: record the advisory posture as the
   measured outcome, with the numbers, and close.
6. **Verify** — `python -m pytest scripts/tests/` exits 0; `ll-loop validate
   refine-to-ready-issue.yaml` stays valid.

## Impact

- **Priority**: P2 - The detector already exists and is wired; this decides whether it does its
  job. Not P1 because the advisory posture is stable and safe — nothing is actively breaking.
- **Effort**: Medium - F2 itself is small; the labelling work that makes the measurement
  trustworthy is the bulk of it and is not compressible.
- **Risk**: Medium - The risk is concentrated in the decision, not the code. Re-arming on an
  under-powered sample sends correct issues into `reconcile_issue`, which rewrites directive
  sections — a worse outcome than leaving the gate advisory.
- **Breaking Change**: No - unless the gate re-arms, in which case `refine-to-ready-issue` routing
  changes for issues carrying an `EVIDENCE_UNVERIFIED` verdict.

## Root Cause

The residual false positives are the **paraphrase** class — spans quoting real code inexactly.
No attribution rule or span-kind filter reaches them, because the span genuinely does not appear
verbatim in any revision of the cited artifact; it is a human rewording of something real. This
is not closable by tuning the matcher, which is why F2 narrows the *input* instead.

## Acceptance Criteria

- [ ] The scan surface is narrowed to `.md`/issue artifacts (F2), with the exclusion implemented
      where span extraction or artifact resolution can enforce it deterministically.
- [ ] The labelled sample is expanded beyond n=30 and the labels are recorded in-repo so the
      measurement is reproducible rather than a remembered figure.
- [ ] Precision, recall, corpus rate, and the 100-commit net-new delta are all measured and
      reported against the table above.
- [ ] Either: `on_yes: check_reconcile_limit` is restored **and**
      `test_check_evidence_unverified_is_advisory_not_routing` is updated in the same commit;
      or: the advisory posture is recorded as the outcome, with the measured numbers.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Carried from BUG-3282's Decision Rules entry *"Gate posture — advisory, not routing (fallback
F3, decided 2026-08-21)"*, which holds the full rationale.

Gotchas that cost time on BUG-3282 and apply directly here:

- **`--update-baseline` must scan with an *empty* baseline.** Baselined spans are dropped before
  matching, so scanning with the existing baseline and replacing the file silently
  un-grandfathers everything already recorded.
- **The verdict cache at `.ll/evidence-verdict-cache.json` is memoization, never policy.** If a
  finding set ever looks wrong, delete it — that must change timing only.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-22 | Priority: P2

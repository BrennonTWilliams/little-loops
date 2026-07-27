---
id: ENH-2870
title: Route program-design gate failures through autodev reconcile-before-defer and
  arm the cutover stamp
type: ENH
priority: P2
status: open
discovered_by: split-from-ENH-2852
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
blocked_by:
- ENH-2852
relates_to:
- ENH-2871
- FEAT-2855
- FEAT-2867
labels:
- rework
- verification
- automation
---

# ENH-2870: Route program-design gate failures through autodev reconcile-before-defer and arm the cutover stamp

Split from ENH-2852 (2026-07-27): the core gate ships fail-open (no cutover stamp
written), so nothing can mass-defer before this routing exists. This issue adds the
autodev deferral routing for the new gate and — as its final AC — arms the gate in this
repo by writing the stamp. The sequencing is self-enforcing: the stamp is only safe to
write once the reconcile-before-defer routing exists, and that routing is this issue.

## Summary

ENH-2852 adds a deterministic `## Program Design` specificity gate inside
`check_format_gaps()` / `ll-issues format-check`, consumed by `/ll:confidence-check` as a
hard override. A new hard failure mode in the confidence gate surfaces in `autodev.yaml`'s
`check_reconcile_needed` / `recheck_after_size_review` as readiness stagnation — a
refined-but-design-less issue could burn a generic reconcile/spike remedy cycle before
deferring under generic `low_readiness`. Give the design-gate failure its own routing:
reconcile-before-defer, and a distinct machine reason code when the remedy fails.

## Current Behavior

After ENH-2852 core ships (unstamped), the gate is off everywhere. Once armed, a
design-gate-caused confidence failure would be indistinguishable from generic low
readiness in autodev: it would flow through the existing stagnation/pre-deferral-remedy
machinery and defer as `low_readiness`, invisible to `ll-issues deferred-triage` as a
design-specific failure.

## Expected Behavior

A confidence-check failure caused solely by the `## Program Design` gate routes once
through the `/ll:reconcile-issue` remedy (it is exactly the kind of directive-section gap
reconcile exists to fix) before any deferral; a post-remedy deferral uses the distinct
machine reason code `design_gate_failed`, not generic `low_readiness`, so
`ll-issues deferred-triage` can distinguish it. With routing in place, the cutover stamp
is written for this repo, arming the gate.

## Proposed Change

1. **`DeferReason` enum** (`scripts/little_loops/issue_lifecycle.py`, lines 58–79 — the
   established single place new deferral reason codes are added):
   `DESIGN_GATE_FAILED = "design_gate_failed"  # ENH-2852/ENH-2870: program-design stage failed verification`,
   following the existing inline-comment convention.
2. **`autodev.yaml` routing**: `recheck_after_size_review` (~line 1435) already implements
   the exact shape needed — it computes `GATE=PASS/FAIL`, checks a stagnation backstop,
   and (per BUG-2803's pre-deferral remedy guarantee) arms a one-shot `reconcile`/`spike`
   remedy via run-dir handshake files (`autodev-pre-deferral-remedy-fired`) before any
   deferral write. Add a design-gate-caused-FAIL discriminator to this same chain —
   checked before the generic `low_readiness` write, routed once through
   `reconcile_current` (near `check_reconcile_needed`, ~line 1165), and only deferred
   with `--reason design_gate_failed` if the post-remedy pass still fails. No new remedy
   infrastructure — this reuses BUG-2803/FEAT-2751's existing machinery.
3. **Consumers of the new reason code**:
   - `scripts/little_loops/cli/issues/set_status.py` — `--reason` flag plumbing.
   - `scripts/little_loops/cli/issues/deferred_triage.py` — insert `design_gate_failed`
     into `_REASON_RANK` at an explicit rank with a dated `# ENH-2870:` rationale comment
     following the existing `# FEAT-2751:`/`# BUG-2734:` convention.
   - `scripts/little_loops/issue_manager.py` — reads `deferred_reason` off issues.
4. **Arm the gate in this repo**: write `.ll/program-design-cutover.json`
   (`{"sha": "<full 40-char SHA>", "date": "YYYY-MM-DD"}` — exactly these two keys, the
   schema pinned in ENH-2852). Per the pinned boundary rule, the `date` is the day
   *after* this issue's gate-arming merge, so every pre-gate issue is strictly earlier
   and exempt. FEAT-2855 and FEAT-2867 parse this same file at this same path.
5. **Docs**: `docs/reference/API.md` `#### deferred-triage` enumerates every `DeferReason`
   code by name in ranked prose — slot `design_gate_failed` in to match `_REASON_RANK`.

## Acceptance Criteria

- [ ] `DeferReason.DESIGN_GATE_FAILED = "design_gate_failed"` exists with the
      convention-following inline comment; `set_status.py --reason`, `deferred_triage.py`
      (`_REASON_RANK` with dated comment), and `issue_manager.py` all recognize it.
- [ ] A confidence-check failure caused solely by the `## Program Design` gate routes to
      the reconcile remedy before any deferral; only a post-remedy failure defers, and
      with `--reason design_gate_failed`, never generic `low_readiness`.
- [ ] The design-gate discriminator in `recheck_after_size_review` short-circuits ahead of
      the generic `low_readiness` write and reuses the existing BUG-2803 one-shot remedy
      handshake (no new remedy infrastructure).
- [ ] `.ll/program-design-cutover.json` is written for this repo with the pinned
      two-key schema, dated the day after the gate-arming merge (strictly-earlier
      exemption comparison per ENH-2852).
- [ ] `docs/reference/API.md`'s deferred-triage reason-code list includes
      `design_gate_failed` at its `_REASON_RANK` position.
- [ ] Tests: `scripts/tests/test_autodev_loop.py` gains a sibling class to
      `TestRecheckAfterSizeReviewStagnationBackstop` following the `readiness_stagnated`
      pattern — string-assertions that the action references `design_gate_failed` and any
      new marker files, plus an ordering test that the branch short-circuits
      `low_readiness`; `test_autodev_decision_gate.py` extended for the routing;
      `test_issue_lifecycle.py` covers enum membership if exhaustive coverage is wanted.

## Scope Boundaries

- **In scope**: `DeferReason.DESIGN_GATE_FAILED` + its three consumers, the
  `recheck_after_size_review` design-gate discriminator, docs for the reason-code list,
  and writing `.ll/program-design-cutover.json` for this repo (arming the gate).
- **Out of scope**: the gate itself, specificity grading, grandfathering/stamp-*reading*
  (ENH-2852, which blocks this); the `manage-issue` Deviations writer (ENH-2871);
  wiring stamp-arming into `ll-init`/`/ll:configure` (optional follow-up, unowned);
  FEAT-2855/FEAT-2867's window computations (they only consume the stamp this issue
  writes).

## Impact

- **Priority**: P2 - the gate ENH-2852 ships stays disarmed everywhere until this lands;
  arming without it would defer design-gap issues under an indistinct reason code with no
  reconcile-first remedy.
- **Effort**: Medium - one enum member, one autodev discriminator reusing existing remedy
  machinery, three small consumer updates, one stamp file, docs.
- **Risk**: Low-Medium - the routing reuses proven BUG-2803/FEAT-2751 machinery; the main
  risk is stamp timing/schema drift against FEAT-2855/FEAT-2867, mitigated by the pinned
  single-file contract.
- **Breaking Change**: No - additive reason code; the stamp arms the gate only in this
  repo.

## Status

**Open** | Created: 2026-07-27 | Priority: P2

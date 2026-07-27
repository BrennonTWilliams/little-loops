---
id: 2854
title: Guard against agent edits to test files during verification
type: ENH
priority: P2
status: open
discovered_by: ll-product-promotion
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
---

# ENH-2854: Guard against agent edits to test files during verification

Origin: ll-product #ENH-052

## Summary

Any loop that uses a green test suite as a transition predicate can be satisfied by editing or commenting out the tests instead of fixing the code. Detect agent modifications to test files across a verification step and either revert them before scoring or fail the transition.

The natural host is the embedded-verification-in-FSM-transitions mechanism (ll-product #ENH-025 — not this repo's local ENH-025, which is unrelated), which currently does not address tamper detection.

## Motivation

"Make the tests pass" is a reward an agent can collect by weakening the tests. Deleting an assertion, commenting out a case, loosening a comparison, or adding a skip marker all turn a suite green without touching the defect. Where a loop treats suite status as a transition predicate, this converts a verification gate into a no-op — and it is invisible in the loop's own telemetry, because from the harness's point of view the tests passed.

Detecting it is mechanical: diff the test files across the step and compare against what the agent was authorized to change.

## Proposed Change

1. **Snapshot** test-file state at the start of a verification step (content hashes over the paths matching the project's test patterns).
2. **Compare** at the end of the step. Any modified, deleted, or newly-skipped test file is a tamper candidate.
3. **Policy** — configurable per loop, with a safe default:
   - `revert` — restore test files to their pre-step state, then score. Scoring then reflects the code change alone.
   - `fail` — fail the transition and report which files were touched.
   - `allow` — permit the edits but record them prominently in the run's evidence (for steps whose *purpose* is editing tests).
4. **Report** — the set of touched test files, and the nature of each change, lands in the verification evidence for the run regardless of policy.

## Design Notes

- Test-file identification should reuse the project's existing test discovery configuration rather than hardcoding a pattern; a false negative here (a test file the guard doesn't know about) is the failure mode that matters.
- Detect weakening that is not a file modification too, where cheap: newly added skip/xfail markers and removed assertions are the common shapes. Content hashing catches all of these as "modified"; the report should say *which* if it can, but the guard's correctness does not depend on classifying them.
- Some legitimate steps modify tests — an issue whose whole point is fixing a broken test. That is what `allow` is for; it must be an explicit per-loop opt-in, never the default and never inferred.
- Deterministic only. No LLM judgment about whether an edit was "reasonable".
- **Scope the guard to the verification step, not the whole issue run.** With `commands.tdd_mode: true`, the implement phase legitimately writes tests before code. The snapshot is taken at *verify-step start*, never at issue start — otherwise every TDD run trips the guard. Make this boundary explicit in the implementation and tests.
- **Ordering with ENH-2853.** `revert` must not destroy ENH-2853's evidence: the pre-patch check runs on the step's diff *before* any revert is applied. `revert` applies only to modifications/deletions of tests that existed at verify-step start; a test file newly added during the verification step is never "reverted" (deleted) by this guard — it is instead handed to ENH-2853's pre-patch check, which is the correct arbiter for new tests.
- **Test-file identification needs a config key that does not exist yet.** Config currently has `project.test_cmd`, not file patterns. Introduce `project.test_patterns` (glob list, with a sensible per-project-type default from the templates), and implement identification as one shared module consumed by both this guard and ENH-2853.

## Acceptance Criteria

- [ ] Test files are snapshotted at verification-step start (not issue start) and compared after it; a TDD-mode run whose implement phase added tests does not trip the guard.
- [ ] Test discovery reuses a `project.test_patterns` config key (new; template-defaulted) via a module shared with ENH-2853, rather than a hardcoded list.
- [ ] Modified, deleted, and newly-added test files are all detected.
- [ ] `revert` policy restores pre-existing test files to their pre-step state before scoring; it never deletes a test file newly added during the step, and ENH-2853's pre-patch check (when present) runs on the diff before any revert.
- [ ] `fail` policy fails the transition and names the touched files.
- [ ] `allow` policy is opt-in per loop and still records the edits in the run evidence.
- [ ] The default policy is not `allow`.
- [ ] Touched-file details appear in the run's verification evidence under every policy.
- [ ] The guard makes no LLM calls.
- [ ] Tests cover: commented-out assertion, added skip marker, deleted test file, untouched tests, and each of the three policies.

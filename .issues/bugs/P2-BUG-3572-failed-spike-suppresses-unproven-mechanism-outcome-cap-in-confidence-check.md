---
id: BUG-3572
type: BUG
title: Failed spike suppresses unproven-mechanism outcome cap in confidence-check
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:13Z'
parent: EPIC-3565
blocks:
- ENH-3577
- BUG-3574
blocked_by:
- BUG-3571
- BUG-3588
---

# BUG-3572: Failed spike suppresses unproven-mechanism outcome cap in confidence-check

## Summary

On failure, `/ll:spike` sets only `spike_attempted: true` (not `spike_completed`) and says a
failed spike means the approach is wrong. But confidence-check Phase 1.9 (ENH-3350) sets
`SPIKE_SUPPRESSED` when **either** `spike_attempted` or `spike_completed` is set. `rubric.md`
then applies no unproven-mechanism cap, and `outcome_confidence` becomes the raw Criteria A–D
sum. A spike that *disproved* the mechanism therefore removes the very cap that demanded
proof. Whether the issue stays blocked depends on the scorer noticing `## Spike Findings`,
which is discretionary, not an FSM guarantee.

A second defect sits under the first: the spike skill treats **any** non-zero Verification
exit as "approach disproven" (`skills/spike/SKILL.md` Phase 5, "If any command exits
non-zero, the spike **failed**"). Import errors, no tests collected, environment failures
and an unrelated regression-suite failure are all reported as a refutation.

## Current Behavior

A failed spike → `spike_attempted: true` → cap suppressed → the issue can pass the outcome
threshold on an approach its own spike refuted.

## Expected Behavior

Only a proven spike retires the proof requirement. A refuted spike routes to a decision,
design change or decomposition. An inconclusive or errored spike keeps the cap. Changing the
approach after a refutation lets a new spike run on the new approach.

## Steps to Reproduce

1. Take an issue with `unproven_mechanism: true` whose mechanism is wrong
2. Run `/ll:spike --auto`; verification fails, and only `spike_attempted: true` is written
3. Run `/ll:confidence-check`: Phase 1.9 sets `SPIKE_SUPPRESSED`, and the outcome is scored with no unproven-mechanism cap

## Motivation

Spikes exist to prove a mechanism before implementation. Treating a disproof as permission to proceed defeats the purpose.

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **File**: `skills/confidence-check/SKILL.md`, Phase 1.9 (ENH-3350) — `SPIKE_SUPPRESSED="yes"` is set when `spike_attempted || spike_completed` succeeds (one `{ …||… }` group). `skills/confidence-check/rubric.md` § "Outcome Confidence Cap (ENH-3350)" applies `min(raw_sum, outcome_threshold − 1)` only when `UNPROVEN_MECHANISM == "true"` and `SPIKE_SUPPRESSED` is empty.
- **Write side**: `skills/spike/SKILL.md` Phase 6 "On failure" sets only `spike_attempted: true` and appends `## Spike Findings`; on success it sets both `spike_completed` and `spike_attempted`. Phase 5 routes every non-zero Verification exit to the failure branch with no refuted/inconclusive distinction. No `spike_refuted` / `spike_verdict` exists anywhere, and nothing in the cap path reads `## Spike Findings`. The spike skill never clears `unproven_mechanism`; suppression is purely the Phase 1.9 read (`docs/reference/API.md`'s "cleared by /ll:spike (spike_completed)" comment overstates this).
- **No reset path**: nothing clears `spike_attempted` or `unproven_mechanism` (writers/readers: `skills/spike`, `skills/confidence-check`, `commands/refine-issue.md`, `commands/reconcile-issue.md`, `cli/issues/set_flags.py`, `cli/issues/show.py`, the three loops). Once suppression keys on `spike_completed` only, a refuted issue whose approach is later changed stays capped forever unless the fix adds a re-arm rule.
- **Loop consequence**: `refine-to-ready-issue.yaml` `run_spike` returns `next`/`on_error: confidence_check` with no verdict routing, and autodev `run_spike` → `count_repair_cycle_spike` → `rerun_confidence_after_spike` → `enqueue_or_skip`, so a refuted spike is rescored uncapped in both.

## Proposed Solution

Separate evidence truth from attempt bounding:

1. **Encoding — boolean `spike_refuted: true`** (not a `spike_verdict` enum). It matches the
   lowercase-bool spike flag convention, works with `ll-issues check-flag` and the existing
   `show --json` emission pattern with no new flag-reading CLI, and yields three states:
   - **proven**: `spike_completed: true`
   - **refuted**: `spike_attempted: true` + `spike_refuted: true`
   - **inconclusive**: `spike_attempted: true` with neither of the others — which is also how
     every legacy attempted-only issue reads, so legacy issues fail safe (cap stays).
2. **Deterministic refuted-vs-inconclusive rule** in spike Phase 5/6. The pytest exit code
   alone cannot carry it: the plan's regression-guard test lives in `$SPIKE_DIR` next to the
   AC tests (`skills/spike/SKILL.md` Phase 3 "at least one regression-guard test", Phase 4
   "Include the regression-guard test"), and both run in the single
   `pytest "$SPIKE_DIR/"` command — so exit 1 does not say *which* test failed. Exit 1 also
   covers test-time errors (fixture/setup errors, an `ImportError` inside a test body),
   which are not refutations. Classify per test from JUnit XML instead:
   - Phase 5 runs each Verification command with `--junitxml=<run file>`.
   - **Refuted** only when ≥1 AC test reports `<failure>` (an assertion failure, not
     `<error>`), **and** every regression-guard test in `$SPIKE_DIR` passed, **and** every
     named existing regression suite passed.
   - **Inconclusive** otherwise: any `<error>`, collection/import errors, no tests collected
     (exit 5), usage/internal errors (exit 2–4), timeouts, a failing guard test, or a failing
     regression suite.
   - Guard tests must be identifiable: the plan template names them (e.g. a
     `test_guard_*` prefix or a `@pytest.mark.spike_guard` marker) so the classifier does
     not rely on the model's reading.
   - Put the classification in a small CLI (e.g. `ll-issues spike-verdict --junit <xml>...
     --guard-pattern <p>` → prints `PROVEN|REFUTED|INCONCLUSIVE`, exits 0/1/3) so it is
     unit-testable; written as prose in the skill it remains the model's judgment, and the
     skill tests are literal-string assertions that cannot check it.
   - Residual, accepted: an AC `<failure>` caused by a bug in the spike's own implementation
     reads as refuted. The Findings entry must quote the failing assertion so a human can
     tell the two apart.
   - Inconclusive writes `spike_attempted: true` only and a `## Spike Findings` entry naming
     the non-verdict cause; it does not claim the approach is wrong.
3. **Cap**: Phase 1.9 sets `SPIKE_SUPPRESSED` on `spike_completed` only. `spike_attempted`
   stays purely an attempt bound (autodev's remedy dispatcher and `check_spike_needed` rely
   on it).
4. **Routing via `decision_needed` and the existing decision gates** (one new autodev check
   state, below; no new remedy states). On refuted, the spike skill also
   arms `decision_needed: true` and adds an Open Questions item naming the refuted approach
   and the alternatives from `## Spike Findings`, so `/ll:decide-issue` has a decidable
   group. The existing decision gates then route it; because the cap stays on, outcome stays
   below threshold and the loops' fail paths reach those gates:
   - refine-to-ready: `confidence_check` → `check_outcome` (fail) → `check_decision_needed`
     → `check_decide_attempts` → `resolve_decision_pre_breakdown`
   - autodev: **not reached today — must be added.** The post-spike path is
     `rerun_confidence_after_spike` → `enqueue_or_skip` → (no children)
     `recheck_after_size_review`, and that state re-reads `decision_needed` only to *defer*
     it as `decision_unresolved` (ENH-2936 branch, ~`autodev.yaml:2318-2337`); it never
     calls `resolve_decision`. `check_decision_before_size_review` → `resolve_decision` is
     reachable only from `recheck_scores`. Fix: retarget `rerun_confidence_after_spike`'s
     `next`/`on_error` to a new `check_decision_after_spike` (`ll-issues check-flag <ID>
     decision_needed`, `fragment: shell_exit`) with `on_yes: resolve_decision`,
     `on_no`/`on_error: enqueue_or_skip`. Existing decide bounds (the ENH-1415 decide-ran
     flag, `check_decide_rate_limited`) apply unchanged
   - not decidable (no alternative exists) → the existing size-review/deferral path, which is
     the correct stop for a refuted approach with no replacement
5. **Re-arm rule**: when `/ll:decide-issue` resolves a decision on an issue carrying
   `spike_refuted: true`, it removes `spike_attempted` and `spike_refuted` so a spike can run
   on the chosen approach (`unproven_mechanism` stays true, so the cap and `spike_needed`
   re-apply). Cycles are bounded by the existing once-per-run markers
   (`refine-to-ready-spike-ran`, `check_decide_attempts`, autodev's
   `autodev-pre-deferral-remedy-fired`) and the FEAT-2751 stagnation counter.
   When the new spike runs differs by loop, and the AC states both:
   - **refine-to-ready**: the run-dir marker `refine-to-ready-spike-ran` blocks a second
     spike in the same run, so the chosen approach stays capped and the run ends not-ready;
     the new spike runs on the **next** run (fresh run dir).
   - **autodev**: `check_spike_needed` is predicate-only (`spike_needed == 'true' and
     spike_attempted != 'true'`), so the re-arm allows the new spike in the **same** run.
     Bound: at most one re-armed spike per issue per run — add a run-dir marker if the
     existing counters do not already guarantee it.
   - Set-only flag writes are safe here: a later `/ll:confidence-check` cannot clear the
     spike's `decision_needed`, because `ll-issues set-flags` only sets flags
     (`set_flags.py:apply_flags_from_notes`, "clearing a flag stays owned by
     `/ll:decide-issue`").
6. **Inconclusive is not retried automatically.** It consumes the attempt and keeps the cap;
   the loops stop (deferral), and recovery is `/ll:spike <ID> --force` after fixing the
   cause. The deferral reason must say so, so the stop is actionable rather than a silent
   dead end.

Termination does not depend on attempted-only cap suppression (see research below), so no
loop regresses into spike → score → spike cycling.

## Program Design

### Types

- `spike_refuted: bool` — new frontmatter flag written by `/ll:spike` on a refuted result and removed by `/ll:decide-issue` on re-arm; emitted by `show --json` as `'true'`/`None` like the other `spike_*` flags.

### Signatures

- `cmd_show(config: BRConfig, args: argparse.Namespace) -> int` — existing `ll-issues show`; its `--json` spike-flag block gains `spike_refuted`.
- `cmd_check_flag(config: BRConfig, args: argparse.Namespace) -> int` — existing `ll-issues check-flag`; used unchanged by confidence-check Phase 1.9 (`spike_completed`) and loop predicates (`spike_refuted`).
- `classify_spike_junit(junit_paths: list[Path], guard_pattern: str) -> str` — new pure function; returns `PROVEN`, `REFUTED` or `INCONCLUSIVE` from JUnit XML per the rule in Proposed Solution 2.
- `cmd_spike_verdict(config: BRConfig, args: argparse.Namespace) -> int` — new `ll-issues spike-verdict --junit <xml>`; prints the verdict, exits 0 proven / 1 refuted / 3 inconclusive.

### Call Path

`cmd_check_flag` -> `parse_frontmatter`; `cmd_show` -> `_parse_card_fields` -> `parse_frontmatter`; `cmd_spike_verdict` -> `classify_spike_junit`

## Integration Map

### Files to Modify
- `skills/spike/SKILL.md` — Phase 5 runs Verification with `--junitxml` and calls the classifier; Phase 6 failure branch split (refuted: `spike_refuted`, `decision_needed`, alternatives entry; inconclusive: `spike_attempted` only); Phase 7 messages
- `skills/spike/plan-template.md` — regression-guard tests must follow a fixed naming/marker convention the classifier can select
- `scripts/little_loops/cli/issues/` — new `spike_verdict.py` (JUnit XML → `PROVEN|REFUTED|INCONCLUSIVE`); register in `cli/issues/__init__.py` dispatch and `_USAGE` epilog
- `skills/confidence-check/SKILL.md` Phase 1.9 — suppress on `spike_completed` only; `skills/confidence-check/rubric.md` cap row wording
- `skills/decide-issue/SKILL.md` — re-arm: remove `spike_attempted`/`spike_refuted` after resolving a decision on a refuted issue
- `scripts/little_loops/cli/issues/show.py` — emit `spike_refuted` as a lowercased string alongside the other `spike_*` flags
- `scripts/little_loops/loops/autodev.yaml` — new `check_decision_after_spike` between `rerun_confidence_after_spike` and `enqueue_or_skip` (see Proposed Solution 4); `recheck_after_size_review` remedy selector (`spike_attempted == 'true'` → no remedy) must not treat a refuted issue as remedy-exhausted
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — no routing change expected (decision gate already downstream of `confidence_check`); add a comment at `run_spike` recording the refuted → `decision_needed` contract
- `scripts/little_loops/loops/README.md` (~L85) — `spike-gate` row describes spike flags

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/spike-gate.yaml` — `check_spike_completed` → `recheck` → `blocked`; only completion-keyed consumer, already treats a failed spike as blocking; confirm refuted stays blocked
- `scripts/little_loops/cli/issues/set_flags.py` — `_spike_not_already_flagged()` suppresses `spike_needed` re-flagging on attempted-or-completed; must stay attempt-bound (re-arm removes `spike_attempted`, which re-enables it as intended)
- `commands/refine-issue.md` (~L1083) — earlier spike-detection point reads `spike_attempted`/`spike_completed`; confirm unchanged semantics
- `commands/reconcile-issue.md` (~L144) — mirrors `/ll:spike`'s `spike_attempted` convention; update if the failure contract gains a marker

### Similar Patterns
- `spike-gate.yaml` is completion-keyed already — the intended semantics
- `commands/reconcile-issue.md` § 5 clears stale evidence (`set-scores --clear`) after a content rewrite — same shape as the decide-issue re-arm

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/ISSUE_TEMPLATE.md` — `spike_attempted` row ("whether or not it proved the mechanism"); add `spike_refuted` (pinned by `test_wiring_reference_docs.py` entry `("docs/reference/ISSUE_TEMPLATE.md", "spike_attempted", "ENH-2640")`)
- `docs/reference/COMMANDS.md`, `docs/reference/CLI.md` (~2273), `docs/reference/API.md`, `docs/guides/LOOPS_REFERENCE.md` — describe spike flags; correct API.md's "cleared by /ll:spike (spike_completed)" overstatement
- `scripts/little_loops/loops/README.md` — `spike-gate` row

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_confidence_check_skill.py` — update Phase 1.9 / `test_spike_attempted_guard_enforced`; add a test that attempted-only keeps the cap
- `scripts/tests/test_spike_skill.py` — literal-string assertions for the refuted/inconclusive split and the `spike_refuted` / `decision_needed` write-back (pattern at `:100-107`)
- `scripts/tests/test_show.py` — `show --json` surfacing test for `spike_refuted` (pattern at `test_show.py:373-438`)
- `scripts/tests/test_builtin_loops.py`, `test_autodev_loop.py`, `test_autodev_decision_gate.py` — refuted → decision routing via stub `ll-issues` on `PATH` executing the real state `action`; remedy selector with `spike_refuted`
- `scripts/tests/test_set_flags_cli.py` — confirm `_spike_not_already_flagged` behavior unchanged
- decide-issue skill contract test for the re-arm step
- `scripts/tests/test_wiring_skills_and_commands.py` — `test_host_artifacts_are_not_stale` mirror gate (all five `GATED_HOSTS`, incl. `rubric.md` companion drift)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Every reader of the spike flags**: `cli/issues/set_flags.py` (`_spike_not_already_flagged()` returns `not (spike_attempted or spike_completed)` and gates `spike_needed` re-flagging via `_spike_precondition_factory()`; `_unproven_mechanism_trigger()`); `cli/issues/show.py` (`show --json` surfaces `spike_needed`/`spike_attempted`/`spike_completed`/`unproven_mechanism` as lowercased strings — a new field must be surfaced here for FSM predicates to read it); `issue_parser.py` `IssueInfo` (carries `unproven_mechanism` only); `loops/autodev.yaml`; `loops/refine-to-ready-issue.yaml`; `loops/spike-gate.yaml`.
- **autodev spike-related states**: `check_spike_needed` and `check_spike_needed_before_skip` (predicate `spike_needed == 'true' and spike_attempted != 'true'`, string compare over `ll-issues show --json`); `recheck_after_size_review` (remedy selector: `spike_attempted == 'true'` yields no remedy; writes the once-per-run `autodev-pre-deferral-remedy-fired` marker); `dispatch_pre_deferral_remedy`; `run_spike`; `count_repair_cycle_spike` (FEAT-2751 backstop counter); `rerun_confidence_after_spike`. No autodev state reads `spike_completed` (comments only).
- **refine-to-ready spike states**: `check_spike_needed` (same predicate plus the run-dir marker `refine-to-ready-spike-ran`, BUG-3553) and `run_spike`; no `rerun_confidence_after_spike` — the return goes straight to `confidence_check`, and `check_decision_needed` (reached from `check_outcome`'s fail path) sits upstream of `check_spike_needed`.
- **Termination does not depend on attempted-only cap suppression.** Loop bounds are the `spike_attempted != 'true'` predicates, the pre-deferral once-per-run marker, the `refine-to-ready-spike-ran` marker, and the FEAT-2751 stagnation counter; all are independent of the confidence-check cap. Not verifiable by static reading: absence of oscillation between `enqueue_or_skip` and the size-review/reconcile paths once the cap stays on — that rests on the stagnation backstop.
- **Decision state names**: autodev has `resolve_decision` (`:683`, reached from `check_decision_before_size_review`), `resolve_decision_direct` (`:704`) and `resolve_decision_at_dequeue`; refine-to-ready uses `resolve_decision_pre_breakdown` (sub-loop `oracles/resolve-decision`); size review is `snap_and_size_review` / `run_size_review`.
- **Tests that pin current behavior**: `test_confidence_check_skill.py` (asserts Phase 1.9 names `SPIKE_SUPPRESSED`, `spike_attempted`, `spike_completed`; `test_spike_attempted_guard_enforced`), `test_spike_skill.py`, `test_set_flags_cli.py`, `test_builtin_loops.py` (many `check_spike_needed` / `spike-gate` assertions), `test_autodev_decision_gate.py`, `test_autodev_loop.py` (`_run_pre_deferral_remedy_selector`), `test_show.py`. None asserts that attempted-only suppresses the cap, so no existing test locks in the bug.

## Conventions in Force

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Routing rule**: a skill writes the outcome into issue frontmatter and the FSM gates on a deterministic shell probe over that file (`fragment: shell_exit`) — never on a slash command's exit code or on prose (`cli/issues/check_verify_verdict.py:1-10`; `refine-to-ready-issue.yaml:397-401` "write-verdict/read-verdict shape"). Two probe shapes exist: a dedicated `ll-issues check-*` command and inline python over `ll-issues show --json` when two fields are needed (`autodev.yaml:1416-1446`, `refine-to-ready-issue.yaml:722-748`).
- **A new field must be surfaced in `show --json` to be routable**: `show.py:134-148` emits lowercased strings (`'true'` or `None`) for `spike_*`, `reconcile_attempted`, `outcome_gate_waived`; BUG-3390 records that a flag not emitted there was "dead end-to-end". Predicates compare strings, not bools.
- **No key allowlist exists** for issue frontmatter — `spike_*`, `verify_verdict`, `reconcile_attempted` are written and read by name; the only registry is `DEPRECATED_FRONTMATTER_KEYS` (`frontmatter.py:54`), and only `decision_needed` / `unproven_mechanism` / `missing_artifacts` are typed `IssueInfo` fields (`issue_parser.py:4031-4033`, `_coerce_tristate_bool`).
- **Writers**: `spike_*` and `verify_verdict` are written by the model via Edit — "there is no `set-flag` CLI verb", `skills/spike/SKILL.md:248-251` — while `spike_needed`/`decision_needed` go through `set-flags`.
- **Mirror gate**: `test_wiring_skills_and_commands.py:463` `GATED_HOSTS = ["gemini","kimi-code","qwen","codex","omp"]`; `test_host_artifacts_are_not_stale` fails on any un-regenerated mirror (`ll-adapt --host <h> --apply`, per host), with a separate companion-file drift check (`:602-638`) covering `rubric.md`.

## Implementation Steps

0. New `spike-verdict` ll-issues subcommand (JUnit XML in, `PROVEN|REFUTED|INCONCLUSIVE` out) with unit tests covering `<failure>` vs `<error>`, failing guard test, failing regression suite, no tests collected; guard-test naming convention in `plan-template.md`
1. Spike skill: Phase 5 runs Verification with `--junitxml` and routes on the classifier; Phase 6 failure branch split (refuted writes `spike_refuted: true`, `decision_needed: true`, an Open Questions item and `## Spike Findings`; inconclusive writes `spike_attempted: true` and a findings entry naming the cause)
2. `show.py`: emit `spike_refuted`
3. Confidence-check Phase 1.9: suppress on `spike_completed` only; update `rubric.md` cap row
4. Decide-issue: re-arm (remove `spike_attempted` / `spike_refuted`) when resolving a decision on a refuted issue
5. autodev: add `check_decision_after_spike` → `resolve_decision` on the post-spike path; fix the `recheck_after_size_review` remedy selector for refuted issues; make inconclusive deferrals name `/ll:spike --force` as the recovery
6. Regression tests: attempted-only keeps the cap; refuted routes to decision (both loops) and never reaches implementation; inconclusive keeps the cap and is not re-spiked automatically; decide re-arm allows one new spike; attempt limits still bound re-runs
7. Docs and mirrors: ISSUE_TEMPLATE, COMMANDS, CLI, API, LOOPS_REFERENCE, loops README; `ll-adapt --host <gemini|kimi-code|qwen|codex|omp> --apply`

## Impact

- **Priority**: P2. A refuted approach can reach implementation.
- **Effort**: Medium
- **Risk**: Medium. Changes the spike/scoring contract used by several loops.
- **Migration**: issues that currently pass the outcome gate on attempted-only suppression
  (legacy failed spikes) become capped at their next rescoring and read as inconclusive.
  Expect a one-time rise in deferrals among `unproven_mechanism: true` issues; list them
  (`spike_attempted: true`, no `spike_completed`) before landing.
- **Sequencing**: `blocked_by: BUG-3571` — shares `skills/confidence-check/SKILL.md` (and
  mirrors) and refine-to-ready's `run_spike` → `confidence_check` path. `blocked_by: BUG-3588`
  — autodev's `rerun_confidence_after_spike` successor (BUG-3588 adds a score clear before it
  and a presence gate after it; this issue retargets its `next`, which then means the presence
  gate's success edge). BUG-3574 is `blocked_by` this issue: it reuses the
  refuted → `decision_needed` contract defined here.

## Acceptance Criteria

- [ ] A failed spike does not suppress the unproven-mechanism cap
- [ ] A Verification failure caused by collection/import/env errors, a test-time `<error>`, a failing regression-guard test or a failing regression suite is recorded as inconclusive, not refuted
- [ ] Refuted/inconclusive classification is made by a CLI from JUnit XML, not by the model reading exit codes
- [ ] A refuted spike routes to decision/design/decomposition, not straight to rescoring, in both autodev and refine-to-ready; in autodev it reaches `resolve_decision` rather than a `decision_unresolved` deferral
- [ ] An inconclusive spike keeps the cap, is not re-spiked automatically, and its deferral names `/ll:spike --force` as the recovery
- [ ] Resolving a decision on a refuted issue re-arms exactly one new spike on the chosen approach — in the same run under autodev, on the next run under refine-to-ready
- [ ] Attempt limits still bound spike re-runs

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-09-25T01:11:18 - `283a56a1-35bd-43bb-b2f7-64d9f104c2c4.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:06:50 - `42a934e3-5df9-4ac6-9296-d0ced0bc2261.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:19 - `4b76ee9e-e590-41ab-940d-a6df6f1554bd.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:31 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`

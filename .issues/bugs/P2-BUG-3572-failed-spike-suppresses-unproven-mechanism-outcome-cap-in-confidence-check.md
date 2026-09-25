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
confidence_score: 95
outcome_confidence: 58
score_complexity: 5
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
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
- **Loop consequence**: `refine-to-ready-issue.yaml` `run_spike` returns `next`/`on_error: confidence_check` with no verdict routing, and autodev `run_spike` → `count_repair_cycle_spike` → `clear_scores_before_spike` → `rerun_confidence_after_spike` → `check_scores_present_spike` → `enqueue_or_skip` (BUG-3588 chain), so a refuted spike is rescored uncapped in both.

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
   which are not refutations. **JUnit's `<failure>` tag is not enough either**: pytest
   emits `<failure>` for *any* exception raised in the test call phase — verified
   2026-09-24: `ModuleNotFoundError` and `FileNotFoundError` raised in a test body both
   produce `<failure>`, identical to a real `assert`; only fixture/setup errors produce
   `<error>`. `<failure>` carries only a `message` attribute (no exception type), and a bare
   `assert` has message `"assert 1 == 2"` with no `AssertionError` prefix, so parsing the
   message is fragile. Classify per test from JUnit XML **plus structured exception
   metadata**:
   - **Exception-type plugin**: ship a pytest plugin in the package
     (`little_loops.spike_junit_plugin`), loaded with `-p little_loops.spike_junit_plugin`.
     Its `pytest_runtest_makereport` hookwrapper appends
     `("ll_exc_type", call.excinfo.type.__name__)` to **`item.user_properties`** on a failed
     `call` phase. It must be `item.user_properties`, not `rep.user_properties`: junitxml
     reads properties from the teardown report, which copies the item's list (verified —
     `rep.user_properties` emits nothing). Result:
     `<property name="ll_exc_type" value="AssertionError"/>` inside the `<testcase>`.
   - **Evidence contract**: Phase 5 runs **every** planned Verification command with
     `--junitxml=<run_dir>/<role>-<n>.xml` and the plugin, and passes each report to the
     classifier **tagged with its role**: `spike` (the `$SPIKE_DIR` suite, containing AC and
     guard tests) or `regression` (a named existing suite). Each report must be fresh from
     this run (stale files are deleted before the run), and the command's exit status is
     passed alongside it.
   - **Guard tests are identified by name prefix `test_guard_`** (set by the plan template).
     Markers cannot be used: `@pytest.mark.*` does not appear in the JUnit output (verified —
     a marked test produces a bare `<testcase>`). Every non-guard test in a `spike` report
     is an AC test.
   - **Proven** only when every report is present and well-formed, every command exited 0,
     and ≥1 AC test and ≥1 guard test **passed** (not skipped).
   - **Refuted** only when ≥1 AC test is `<failure>` with `ll_exc_type == AssertionError`,
     **and** every guard test passed, **and** every `regression` report is fully passing.
   - **Inconclusive** in every other case, including: a missing or malformed report, a
     planned command with no report; any `<error>`; any AC `<failure>` whose `ll_exc_type` is
     absent or not `AssertionError` (e.g. an `ImportError`/`OSError` in a test body);
     collection errors; no tests collected (exit 5); usage/internal errors (exit 2–4);
     timeouts; **zero matching AC tests or zero guard tests**; AC or guard tests that are all
     skipped; a failing guard test; a failing regression report.
   - Put the classification in a small CLI (`ll-issues spike-verdict --report
     <role>:<xml>:<exit> ...` → prints `PROVEN|REFUTED|INCONCLUSIVE` plus a one-line cause,
     exits 0/1/3) so it is unit-testable; written as prose in the skill it remains the
     model's judgment, and the skill tests are literal-string assertions that cannot check
     it.
   - Residual, accepted: an AC `AssertionError` caused by a bug in the spike's own
     implementation reads as refuted. The Findings entry must quote the failing assertion so
     a human can tell the two apart.
   - Inconclusive writes a `## Spike Findings` entry naming the classifier's cause; it does
     not claim the approach is wrong.
3. **Flag transitions — every verdict writes the full flag set.** Phase 6 currently only
   adds flags ("skip the write if already `true`"), so a `--force` rerun inherits stale
   flags: a failed rerun after a proven spike keeps `spike_completed` (cap stays suppressed
   on a now-failing mechanism), and a proven rerun after a refutation keeps `spike_refuted`.
   Each verdict sets its flags **and removes the others**:

   | Verdict | `spike_attempted` | `spike_completed` | `spike_refuted` | `decision_needed` |
   |---|---|---|---|---|
   | proven | set | set | **remove** | unchanged |
   | refuted | set | **remove** | set | set (see 5) |
   | inconclusive | set | **remove** | **remove** | unchanged |

   This covers proven → failed, refuted → proven, refuted → inconclusive, and
   inconclusive → proven (the `--force` recovery path). Removal uses the same
   Edit-the-frontmatter convention as the writes (there is no `set-flag` verb and
   `set-flags` is set-only). Removing `spike_refuted` on a later verdict does not clear a
   `decision_needed` the refutation armed; that stays owned by `/ll:decide-issue`.
4. **Cap**: Phase 1.9 sets `SPIKE_SUPPRESSED` on `spike_completed` only. `spike_attempted`
   stays purely an attempt bound (autodev's remedy dispatcher and `check_spike_needed` rely
   on it).
5. **Post-spike routing — branch on the verdict immediately after `run_spike`, before any
   rescoring, in both loops.** The previous draft sent the spike through rescoring first
   and relied on the capped outcome to reach the decision gates. That contradicts the
   "not straight to rescoring" AC, and in refine-to-ready it is unsafe: `confidence_check`
   → `check_readiness` runs **before** `check_outcome`, and a readiness drop after the
   rescoring routes `check_readiness.on_no` → `check_refine_limit` → `refine_followup` /
   `breakdown_issue`, never reaching `check_decision_needed`. Rescoring before a decision is
   also wasted work, since the decision rewrites the issue and forces another rescoring.
   On refuted, the spike skill arms `decision_needed: true` and adds an Open Questions item
   naming the refuted approach and the alternatives from `## Spike Findings`, so
   `/ll:decide-issue` has a decidable group. A new three-way post-spike state reads the flags
   (inline python over `ll-issues show --json`, per Conventions in Force):
   - **refine-to-ready**: `run_spike.next`/`on_error` → new `route_spike_verdict`:
     `spike_refuted == 'true'` → `check_decide_attempts` (→
     `resolve_decision_pre_breakdown`, whose `on_success` already returns to
     `confidence_check`); inconclusive (attempted, neither completed nor refuted) →
     `record_spike_inconclusive` (item 7); proven → `confidence_check` (unchanged).
   - **autodev**: BUG-3588 has landed (`795f40a06`); the post-spike chain is now
     `run_spike` → `count_repair_cycle_spike` → `clear_scores_before_spike` →
     `rerun_confidence_after_spike` → `check_scores_present_spike` →
     (`on_yes`) `enqueue_or_skip`. Insert `route_spike_verdict` **between
     `count_repair_cycle_spike` and `clear_scores_before_spike`**: refuted →
     `check_spike_budget` (item 6) → `resolve_decision`; inconclusive →
     `record_spike_inconclusive`; proven → `clear_scores_before_spike` (BUG-3588's
     clear → rescore → presence-gate chain is unchanged, and `check_scores_present_spike`'s
     `on_yes: enqueue_or_skip` stays). BUG-3588's score-presence gate must not be bypassed
     on any path that proceeds to scoring.
   - Today autodev never reaches a decision after a spike:
     `recheck_after_size_review` re-reads `decision_needed` only to *defer* it as
     `decision_unresolved` (ENH-2936 branch), and `check_decision_before_size_review` →
     `resolve_decision` is reachable only from `recheck_scores`.
   - **Scores on the refuted path**: autodev's refuted branch skips BUG-3588's clear, so the
     issue keeps its pre-spike scores until `resolve_decision` → `mark_decide_ran` →
     `rerun_confidence_after_decide` rescores. On resolve failure it goes to
     `check_decide_rate_limited` → `record_decision_unresolved` (deferred), which reads no
     scores. Verify no path from the refuted branch reaches `enqueue_or_skip` without a
     fresh rescoring.
   - not decidable (no alternative exists) → the resolve-decision oracle fails →
     `record_decision_unresolved` in both loops. That is the correct stop for a refuted
     approach with no replacement.
6. **Mandatory spike budget.** The previous draft said existing decide bounds "apply
   unchanged". They do not: the ENH-1415 `autodev-decide-ran` marker is read **only** in
   `decide_current` (`resolve_decision` is also entered from `check_decision_at_dequeue`,
   `check_decision_after_refine` and `check_decision_before_size_review`, and the sibling
   `resolve_decision_direct` / `resolve_decision_at_dequeue` states exist too; none of these
   check the marker), and `check_decide_rate_limited` is a 429-exhaustion check, not an attempt
   count. So refute → decide → re-arm → spike → refute can cycle within one autodev run,
   bounded only by the FEAT-2751 stagnation backstop. Add an explicit **per-issue, per-run
   spike budget**: a run-dir marker `spike-runs-<ID>` (a count) incremented by every entry
   into `run_spike` in both loops, and checked before `run_spike` by every entry path
   (autodev `check_spike_needed`, `check_spike_needed_before_skip`,
   `dispatch_pre_deferral_remedy`; refine-to-ready `check_spike_needed`, which subsumes
   BUG-3553's `refine-to-ready-spike-ran`). Budget: **2 per issue per run in autodev**
   (original + one re-armed spike), **1 in refine-to-ready**. A refuted verdict with the
   budget spent routes to `record_decision_unresolved`, not `resolve_decision`.
7. **Re-arm rule**: `/ll:decide-issue` removes `spike_attempted` and `spike_refuted` only
   when **both** (a) the issue carries `spike_refuted: true` and (b) `decision_needed` was
   actually cleared in this invocation, meaning the refuted approach was replaced by a
   chosen one. The re-arm lives in the decide-issue skill itself, so it covers both callers
   (autodev's `resolve_decision`/`resolve_decision_direct`/`resolve_decision_at_dequeue`
   and refine-to-ready's `resolve_decision_pre_breakdown`, all via
   `oracles/resolve-decision`). It must **not** fire when the oracle finishes `done` with a
   residual decision group still armed (`resolve-decision.yaml` `check_residual_decision`),
   because the approach has not changed. `unproven_mechanism` stays true, so the cap and
   `spike_needed` re-apply. When the new spike runs differs by loop, and the AC states both:
   - **refine-to-ready**: the spike budget (1) blocks a second spike in the same run, so the
     chosen approach stays capped and the run ends not-ready; the new spike runs on the
     **next** run (fresh run dir).
   - **autodev**: `check_spike_needed` is predicate-only (`spike_needed == 'true' and
     spike_attempted != 'true'`), so the re-arm allows the new spike in the **same** run,
     within the budget of 2.
   - Set-only flag writes are safe here: a later `/ll:confidence-check` cannot clear the
     spike's `decision_needed`, because `ll-issues set-flags` only sets flags
     (`set_flags.py:apply_flags_from_notes`, "clearing a flag stays owned by
     `/ll:decide-issue`").
8. **Inconclusive is not retried automatically, and stops at a named site in each loop.** It
   consumes the attempt and keeps the cap. Without a dedicated branch, the capped outcome
   in refine-to-ready falls through `check_outcome` → `check_decision_needed` (no) →
   `check_spike_needed` (no, attempted) → `check_missing_artifacts` toward
   `breakdown_issue`, which would decompose an issue because of an environment failure.
   New deferral code **`spike_inconclusive`**, emitted by a new `record_spike_inconclusive`
   state in each loop, modeled on `record_decision_unresolved` (skip if already
   done/cancelled; `ll-issues set-status <ID> deferred --by automation --reason
   spike_inconclusive`):
   - **autodev**: also appends `<ID>  spike_inconclusive` to `autodev-skipped.txt`, removes
     `autodev-inflight`, then `dequeue_next`.
   - **refine-to-ready**: also writes `spike_inconclusive` to `refine-terminal-class`
     (BUG-3390 pattern), then `failed`.
   - Both echo the classifier's cause, followed by
     `[SPIKE_INCONCLUSIVE] <ID> — spike could not reach a verdict (<cause>); fix the cause,
     then run /ll:spike <ID> --force and re-run to resurface`.
   - `auto-refine-and-implement` and any other caller reading `refine-terminal-class` must
     treat `spike_inconclusive` as a non-quality, human-needed stop (like
     `decision_unresolved`).

Termination does not depend on attempted-only cap suppression (see research below), so no
loop regresses into spike → score → spike cycling.

## Program Design

### Types

- `spike_refuted: bool` — new frontmatter flag written by `/ll:spike` on a refuted result, removed by `/ll:spike` on a later proven/inconclusive verdict and by `/ll:decide-issue` on re-arm; emitted by `show --json` as `'true'`/`None` like the other `spike_*` flags.
- `SpikeReport` — dataclass `(role: str, junit_path: Path, exit_code: int)`; `role` is `spike` or `regression`.
- `SpikeVerdict` — dataclass `(verdict: str, cause: str)`; `verdict` is `PROVEN`, `REFUTED` or `INCONCLUSIVE`, and `cause` is a one-line reason quoted into `## Spike Findings` and the `spike_inconclusive` deferral message.

### Signatures

- `cmd_show(config: BRConfig, args: argparse.Namespace) -> int` — existing `ll-issues show`; its `--json` spike-flag block gains `spike_refuted`.
- `cmd_check_flag(config: BRConfig, args: argparse.Namespace) -> int` — existing `ll-issues check-flag`; used unchanged by confidence-check Phase 1.9 (`spike_completed`) and loop predicates (`spike_refuted`).
- `classify_spike_junit(reports: list[SpikeReport], guard_prefix: str = "test_guard_") -> SpikeVerdict` — new pure function; applies the Proposed Solution 2 rule, reading `<property name="ll_exc_type">` for `<failure>` classification and treating missing/malformed reports as inconclusive.
- `cmd_spike_verdict(config: BRConfig, args: argparse.Namespace) -> int` — new `ll-issues spike-verdict --report <role>:<xml>:<exit> ...`; prints the verdict and cause, exits 0 proven / 1 refuted / 3 inconclusive.
- `pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Generator` — hookwrapper in `little_loops/spike_junit_plugin.py` (new); on a failed `call` phase appends `("ll_exc_type", call.excinfo.type.__name__)` to `item.user_properties`.

### Call Path

`cmd_check_flag` -> `parse_frontmatter`; `cmd_show` -> `_parse_card_fields` -> `parse_frontmatter`; `cmd_spike_verdict` -> `classify_spike_junit`; pytest (`-p little_loops.spike_junit_plugin`) -> `pytest_runtest_makereport`

## Integration Map

### Files to Modify
- `skills/spike/SKILL.md` — Phase 5 deletes stale reports, runs every Verification command with `--junitxml=<run_dir>/<role>-<n>.xml -p little_loops.spike_junit_plugin`, and calls the new `spike-verdict` classifier; Phase 6 writes the full flag set per verdict (Proposed Solution 3 table; refuted also arms `decision_needed` + Open Questions item); Phase 7 messages
- `skills/spike/plan-template.md` — regression-guard tests are named `test_guard_*` (not a marker: markers are absent from JUnit output); Verification section tags each command `spike` or `regression`
- `scripts/little_loops/spike_junit_plugin.py` (new) — pytest plugin recording `ll_exc_type` via `item.user_properties`
- `scripts/little_loops/cli/issues/` — new `spike_verdict.py` (`SpikeReport` list → `SpikeVerdict`); register in `cli/issues/__init__.py` dispatch and `_USAGE` epilog
- `skills/confidence-check/SKILL.md` Phase 1.9 — suppress on `spike_completed` only; `skills/confidence-check/rubric.md` cap row wording
- `skills/decide-issue/SKILL.md` — re-arm: remove `spike_attempted`/`spike_refuted` only when the issue is refuted **and** `decision_needed` was cleared in this invocation (not on a residual-group `done`)
- `scripts/little_loops/cli/issues/show.py` — emit `spike_refuted` as a lowercased string alongside the other `spike_*` flags
- `scripts/little_loops/loops/autodev.yaml` — new `route_spike_verdict` between `count_repair_cycle_spike` and `clear_scores_before_spike` (Proposed Solution 5; BUG-3588's clear → rescore → `check_scores_present_spike` chain stays on the proven branch); new `check_spike_budget` and `record_spike_inconclusive`; the `spike-runs-<ID>` budget check at every `run_spike` entry (`check_spike_needed`, `check_spike_needed_before_skip`, `dispatch_pre_deferral_remedy`); `recheck_after_size_review` remedy selector (`spike_attempted == 'true'` → no remedy) must not treat a refuted issue as remedy-exhausted
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — **routing change**: `run_spike.next`/`on_error` → new `route_spike_verdict` (refuted → `check_decide_attempts`; inconclusive → new `record_spike_inconclusive` → `failed`; proven → `confidence_check`); `check_spike_needed` switches from `refine-to-ready-spike-ran` to the shared `spike-runs-<ID>` budget
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` (and any other `refine-terminal-class` reader) — treat `spike_inconclusive` as a non-quality, human-needed stop
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
- `docs/reference/COMMANDS.md`, `docs/reference/CLI.md` (~2273), `docs/reference/API.md`, `docs/guides/LOOPS_REFERENCE.md` — describe spike flags; correct API.md's "cleared by /ll:spike (spike_completed)" overstatement; CLI.md documents the new `spike-verdict` subcommand
- `docs/reference/DEFERRAL_CODES.md` — add the `spike_inconclusive` row (emitted by `record_spike_inconclusive` in autodev and refine-to-ready)
- `scripts/little_loops/loops/README.md` — `spike-gate` row

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_confidence_check_skill.py` — update Phase 1.9 / `test_spike_attempted_guard_enforced`; add a test that attempted-only keeps the cap
- `scripts/tests/test_spike_skill.py` — literal-string assertions for the refuted/inconclusive split and the `spike_refuted` / `decision_needed` write-back (pattern at `:100-107`)
- `scripts/tests/test_show.py` — `show --json` surfacing test for `spike_refuted` (pattern at `test_show.py:373-438`)
- `scripts/tests/test_builtin_loops.py`, `test_autodev_loop.py`, `test_autodev_decision_gate.py` — refuted → decision routing via stub `ll-issues` on `PATH` executing the real state `action`; remedy selector with `spike_refuted`
- `scripts/tests/test_set_flags_cli.py` — confirm `_spike_not_already_flagged` behavior unchanged
- decide-issue skill contract test for the re-arm step (incl. no re-arm on residual-group `done`)
- `scripts/tests/test_spike_verdict.py` (new) — classifier + plugin over real pytest-generated JUnit (Implementation Step 0 matrix)
- `scripts/tests/test_refine_to_ready_*` / `test_builtin_loops.py` — `route_spike_verdict` three-way routing; refuted reaches the decision with readiness passing and failing; inconclusive → `record_spike_inconclusive` → `failed`, never `breakdown_issue`
- deferral-code coverage for `spike_inconclusive` (wherever `DEFERRAL_CODES.md` rows are pinned)
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

0. `spike_junit_plugin.py` plus the `spike-verdict` ll-issues subcommand, with unit tests over real pytest-generated JUnit (run pytest in `tmp_path` with the plugin) covering: an assert failure → refuted; `ImportError` / `OSError` in a test body (`<failure>`, non-`AssertionError` `ll_exc_type`) → inconclusive; `<error>` (fixture setup) → inconclusive; a failing guard test; a failing `regression` report; a missing report; malformed XML; no tests collected; all AC tests skipped; zero AC or zero guard tests; a nonzero exit with an all-pass report. Guard-test `test_guard_*` convention and per-command role tags in `plan-template.md`
1. Spike skill: Phase 5 deletes stale reports, runs every Verification command with `--junitxml` + the plugin, and routes on the classifier; Phase 6 writes the full flag set per verdict (Proposed Solution 3 table: refuted also writes `decision_needed: true`, an Open Questions item and `## Spike Findings`; inconclusive writes a findings entry naming the cause)
2. `show.py`: emit `spike_refuted`
3. Confidence-check Phase 1.9: suppress on `spike_completed` only; update `rubric.md` cap row
4. Decide-issue: re-arm (remove `spike_attempted` / `spike_refuted`) only when refuted **and** `decision_needed` cleared in this invocation
5. Both loops: `route_spike_verdict` immediately after the spike (autodev: after `count_repair_cycle_spike`, before `clear_scores_before_spike`; refine-to-ready: `run_spike.next`); `record_spike_inconclusive` (`spike_inconclusive` deferral, recovery message naming `/ll:spike <ID> --force`); the shared `spike-runs-<ID>` budget (autodev 2, refine-to-ready 1) checked at every `run_spike` entry; autodev `recheck_after_size_review` remedy selector fixed for refuted issues
6. Regression tests: attempted-only keeps the cap; each flag transition in the Proposed Solution 3 table, incl. `--force` proven → failed and refuted → proven; refuted routes to decision **before any rescoring** in both loops and never reaches implementation; refine-to-ready refuted still reaches the decision with readiness **both passing and failing**; inconclusive stops at `record_spike_inconclusive` in both loops (not `breakdown_issue`), is not re-spiked automatically, and its message names `/ll:spike --force`; decide re-arm allows one new spike and does not fire on a residual-group `done`; **repeated refutation** (refute → decide → re-arm → refute) stops at the budget with `decision_unresolved`, not another `resolve_decision`; autodev's proven branch still passes through BUG-3588's `check_scores_present_spike`
7. Docs and mirrors: ISSUE_TEMPLATE, COMMANDS, CLI, API, LOOPS_REFERENCE, DEFERRAL_CODES, loops README; `ll-adapt --host <gemini|kimi-code|qwen|codex|omp> --apply`

## Impact

- **Priority**: P2. A refuted approach can reach implementation.
- **Effort**: Medium
- **Risk**: Medium. Changes the spike/scoring contract used by several loops.
- **Migration**: issues that currently pass the outcome gate on attempted-only suppression
  (legacy failed spikes) become capped at their next rescoring and read as inconclusive.
  Expect a one-time rise in deferrals among `unproven_mechanism: true` issues; list them
  (`spike_attempted: true`, no `spike_completed`) before landing.
- **Sequencing**: `blocked_by: BUG-3571` (done) — shares `skills/confidence-check/SKILL.md`
  (and mirrors) and refine-to-ready's `run_spike` → `confidence_check` path.
  `blocked_by: BUG-3588` (done, `795f40a06`) — added `clear_scores_before_spike` before and
  `check_scores_present_spike` after `rerun_confidence_after_spike`. This issue inserts its
  verdict branch **upstream** of that chain (after `count_repair_cycle_spike`) and leaves
  the chain and its `on_yes: enqueue_or_skip` edge untouched. BUG-3574 is `blocked_by` this
  issue: it reuses the refuted → `decision_needed` contract defined here.

## Acceptance Criteria

- [ ] A failed spike does not suppress the unproven-mechanism cap
- [ ] A Verification failure caused by collection/import/env errors, a non-`AssertionError` exception in a test body (JUnit `<failure>`), a test-time `<error>`, a failing regression-guard test, a failing regression suite, a missing/malformed report, or zero matching AC/guard tests is recorded as inconclusive, not refuted
- [ ] Refuted/inconclusive classification is made by a CLI from role-tagged JUnit XML with recorded exception types, not by the model reading exit codes
- [ ] Every spike verdict writes the full flag set: a failed `--force` rerun clears a stale `spike_completed`, and a proven rerun clears a stale `spike_refuted`
- [ ] A refuted spike routes to a decision **before any rescoring** in both autodev and refine-to-ready, whatever its readiness score; in autodev it reaches `resolve_decision` rather than a `decision_unresolved` deferral, while budget remains
- [ ] An inconclusive spike keeps the cap, is not re-spiked automatically, and stops at `record_spike_inconclusive` in both loops (deferral code `spike_inconclusive`, not decomposition), with a message naming `/ll:spike <ID> --force` as the recovery
- [ ] Resolving a decision on a refuted issue re-arms exactly one new spike on the chosen approach — in the same run under autodev, on the next run under refine-to-ready; a residual-group `done` with `decision_needed` still armed does not re-arm
- [ ] A per-issue, per-run spike budget, shared by every `run_spike` entry path, bounds re-runs; a repeated refutation within one run stops with `decision_unresolved`
- [ ] autodev's proven path still passes BUG-3588's score-presence gate (`check_scores_present_spike`)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-24_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 58/100 → LOW

### Concerns
- New pytest plugin (`spike_junit_plugin`) is loaded via `-p` inside the spike skill, which runs in consuming projects; confirm the module resolves there (editable/pypi install) before relying on it.

### Outcome Risk Factors
- Broad enumeration across 16+ sites (skill, plan template, plugin, CLI, two loops, decide-issue, show.py, docs, mirrors for five hosts) with deep per-site complexity: a new verdict contract plus loop routing changes in `autodev.yaml` and `refine-to-ready-issue.yaml`.
- Wide blast radius on spike flags: `set_flags.py`, `show.py`, three loops, `refine-issue`, `reconcile-issue`, `decide-issue`, `spike-gate.yaml`.
- Repeated-refutation cycling (refute → decide → re-arm → refute) rests on the new `spike-runs-<ID>` budget plus the FEAT-2751 backstop; oscillation is not statically verifiable. Consider splitting: (1) classifier CLI + plugin, (2) cap/flag contract, (3) loop routing + budget.

## Session Log
- `/ll:confidence-check` - 2026-09-25T03:34:09 - `1d2aa8fb-1dc2-4396-a044-d0a19e8f17b9.jsonl`
- `/ll:wire-issue` - 2026-09-25T01:11:18 - `283a56a1-35bd-43bb-b2f7-64d9f104c2c4.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:06:50 - `42a934e3-5df9-4ac6-9296-d0ced0bc2261.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:19 - `4b76ee9e-e590-41ab-940d-a6df6f1554bd.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:31 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`

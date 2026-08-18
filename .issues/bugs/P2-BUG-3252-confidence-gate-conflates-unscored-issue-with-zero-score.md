---
id: BUG-3252
type: BUG
title: ll-auto confidence gate conflates an unscored issue with a zero-scored one,
  emits no remediation, and records the skip as a failure
priority: P2
status: open
testable: true
discovered_by: analyze_log
discovered_date: '2026-08-17'
discovered_commit: 6ba249d0
discovered_source: ll-auto run 2026-08-17T17:51-18:20 (--only ENH-3237,ENH-3240)
relates_to:
- FEAT-3117
supersedes:
- BUG-3253
reconcile_attempted: true
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-3252: ll-auto confidence gate conflates an unscored issue with a zero-scored one, emits no remediation, and records the skip as a failure

## Summary

`readiness_status()` coerces a missing `confidence_score` frontmatter key to the
integer `0`. The `ll-auto` pre-Phase-1 confidence gate then reports that `0` as
though it were a measured score, halts, and files the issue under
`failed_issues` — so an issue that has simply never been through
`/ll:confidence-check` is indistinguishable in the log, the summary, and the
state file from one that was assessed and found genuinely unready.

The gate itself is correct to halt. Three things around it are wrong: the
message misrepresents absence as a score, the remediation the skill spec
mandates is never emitted, and the outcome is classified as a failure rather
than a skip.

## Steps to Reproduce

1. Take an issue with no `confidence_score` in frontmatter — e.g. one freshly
   produced by `/ll:capture-issue` + `/ll:format-issue` + `/ll:wire-issue`, none
   of which write a score.
2. Ensure `commands.confidence_gate.enabled` is `true` in `.ll/ll-config.json`
   (it is, with `readiness_threshold: 85`).
3. Run `ll-auto --only <ID>`.

Observed, from the 2026-08-17 run against ENH-3240:

```
[18:20:58] ENH-3240: below readiness threshold (confidence 0 < 85)
CONFIDENCE_GATE_BLOCKED ENH-3240
PHASE1_NOT_STARTED ENH-3240 confidence_gate
...
[18:20:58] Failed issues: 1
[18:20:58]   - ENH-3240: below_readiness_threshold (0 < 85)...
```

ENH-3240's frontmatter at that moment contained no `confidence_score` key at
all — the `0` is entirely synthesized by the reader.

## Current Behavior

`scripts/little_loops/cli/issues/check_readiness.py:87`:

```python
confidence = int(fm.get("confidence_score") or 0)
```

`ReadinessStatus` therefore has no way to express "unscored". Its
`meets_readiness` property (`check_readiness.py:33-35`) compares the synthesized
`0` against the threshold, which is the right *decision* but for a reason the
type can no longer carry.

`scripts/little_loops/issue_manager.py:813-833` consumes it:

```python
logger.warning(
    f"{info.issue_id}: below readiness threshold "
    f"(confidence {status.confidence} < {status.readiness_threshold})"
)
print(f"CONFIDENCE_GATE_BLOCKED {info.issue_id}", flush=True)
print(f"PHASE1_NOT_STARTED {info.issue_id} confidence_gate", flush=True)
return _stamped_result(
    success=False,
    ...
    failure_reason=(
        f"below_readiness_threshold "
        f"({status.confidence} < {status.readiness_threshold})"
    ),
)
```

`success=False` routes the issue into `state.failed_issues`, which the run
summary renders under the "Failed issues:" heading
(`issue_manager.py:1965-1968`).

## Expected Behavior

1. **Absence is representable.** `ReadinessStatus` distinguishes "no
   `confidence_score` key" from "`confidence_score: 0`". The gate decision is
   unchanged — both halt — but the reported reason differs.
2. **The message states which case it is.** Unscored issues get "has no
   confidence score (never assessed)", not "confidence 0 < 85".
3. **The remediation is emitted.** `skills/manage-issue/SKILL.md:183` specifies
   the gate should "HALT and direct the user to run `/ll:confidence-check
   [ID]`". `ll-auto` mirrors the gate's decision but not its remediation, so the
   operator gets a number with no next command. Emit the suggested command.
4. **A gate skip is not a failure.** The issue was never attempted; counting it
   as failed misrepresents the run's outcome and pollutes downstream metrics.
5. **The auto-correction rate stops counting never-attempted issues, and says
   so.** The concrete downstream instance of (4): a gated issue enters the
   `len(completed) + len(failed)` denominator without ever having been able to
   contribute to the numerator, biasing the rate downward by exactly the number
   of gated issues. Part 3 fixes the denominator; Part 4 discloses the
   exclusion. (Absorbed from BUG-3253, superseded by this issue.)

The `CONFIDENCE_GATE_BLOCKED` / `PHASE1_NOT_STARTED` stdout markers must keep
their exact current spelling — `autodev.yaml`'s `check_impl_reached`
discriminator greps for them (per the comments at `issue_manager.py:819-826`).

## Impact

- **Severity**: P2 — no data loss, but the run summary actively misinforms.
  "Failed issues: 1 — below_readiness_threshold (0 < 85)" reads as "this issue
  was evaluated and scored badly", prompting an operator to go re-refine an
  issue whose only real problem is that nobody has run `/ll:confidence-check`
  on it yet.
- **Frequency**: every unscored issue passed to `ll-auto` while the gate is
  enabled. In the observed run that was 1 of 2 issues (50%).
- **Data Risk**: None.

## Root Cause

`or 0` in `check_readiness.py:87` is a lossy coercion at the type boundary. The
`ReadinessStatus` dataclass docstring is explicit that it deliberately avoids a
combined `passed` verdict so that two callers with different needs each get a
correct answer — the same reasoning applies here: collapsing absent and zero
serves the comparison but destroys the diagnostic.

The classification half is separate: `_stamped_result(success=False, ...)` is
the only outcome shape the gate branch has available, and `IssueProcessingResult`
has no "skipped" state distinct from "failed".

## Proposed Solution

**Part 1 — represent absence.**

Add a nullable raw field to `ReadinessStatus` alongside the coerced one, so no
existing consumer changes behavior:

- `raw_confidence: int | None` — the frontmatter value before coercion, `None`
  when the key is absent, null, or non-numeric. Uses the same coercion
  semantics as `IssueParser._coerce_optional_int` (`issue_parser.py:2908-2919`),
  matching the established absence-preserving pattern. **That method is not
  directly callable from here** — see the Coercion Helper decision rule below.
- `confidence` keeps its current `int` semantics and `meets_readiness` keeps its
  current comparison, so `cmd_check_readiness` and the `autodev.yaml`
  `--readiness`/`--outcome` CLI fallbacks are untouched.

**Not a `confidence_present: bool` sibling field.** Beyond the convention
argument in the research findings below, the bool is *incorrect* for the case
this bug exists to fix: `confidence_present = "confidence_score" in fm` reports
`True` for `confidence_score: null` or `confidence_score: ""` while `confidence`
is still the synthesized `0` — so a null score would render "below readiness
threshold (0 < 85)", reproducing exactly the misreporting under repair. The
`_coerce_optional_int` semantics collapse absent / null / non-numeric to a
single `None`, which is the distinction the message needs.

**`outcome_confidence` is in scope.** `check_readiness.py:88` carries the
identical `int(fm.get("outcome_confidence") or 0)` coercion. Add
`raw_outcome: int | None` in the same edit — `cmd_check_readiness` compares both
thresholds, so leaving one half absence-blind guarantees the same defect
resurfaces the first time a caller reports on `meets_outcome`.

**Part 2 — message and remediation.**

In `issue_manager.py`'s gate branch, branch the log line on
`raw_confidence is None` and append the remediation command in both cases:

```
ENH-3240: no confidence score recorded (never assessed) — run
  /ll:confidence-check ENH-3240
ENH-3240: below readiness threshold (confidence 40 < 85) — run
  /ll:confidence-check ENH-3240
```

Leave the two `print(...)` marker lines byte-identical.

**Part 3 — classification.**

Distinguish gate skips from failures in the run state. Keep `success=False` (so
`--only` callers still see a non-success), add `was_gated: bool = False` to
`IssueProcessingResult` alongside the existing `was_blocked`/`plan_created`
flags, set it on the confidence-gate return, and add a matching
`elif result.was_gated:` arm to the state-mapping switch
(`issue_manager.py:2105-2123`) routing to the already-tested
`state_manager.mark_skipped(...)`. `ProcessingState.skipped_issues`
(`state.py:53`) exists for exactly this and needs no shape change.

**Scope: the confidence gate only.** Do not extend `was_gated` to the learning
gate. The learning gate runs *after* `issue_timing["ready"]` is recorded
(`issue_manager.py:1109`) — i.e. after Phase 1 completed — and its returns pass
`corrections=corrections`. Marking it skipped would remove a corrected issue
from the denominator while its corrections stay in the numerator, which is the
same defect BUG-3253 is fixing, inverted. The confidence gate is safe precisely
because its `_stamped_result(...)` omits `corrections=` entirely
(`issue_manager.py:826-834`), so it can never contribute to the numerator.

**`ll-sprint` is in scope — it is a third dispatch site, not a near-duplicate.**
`cli/sprint/run.py` calls `process_issue_inplace()` directly at two sites
(`run.py:75` via the SIGALRM timeout wrapper, and `run.py:839` on the retry
path) and maps the result with its own dispatch chain rather than reusing
`AutoManager._process_issue`'s:

```
run.py:711   elif issue_result.was_blocked:
run.py:715       state.skipped_blocked_issues[issue.issue_id] = issue_result.failure_reason
run.py:724   state.failed_issues[issue.issue_id] = orchestration_reason
run.py:878   elif retry_result.was_blocked:      # retry path, same shape
run.py:882       state.skipped_blocked_issues[...] = ...
```

`docs/reference/CLI.md:406` already records that the confidence gate "inherits
into `ll-sprint`'s two `process_issue_inplace()` call sites," so a gated issue
lands in `SprintState.failed_issues` (`sprint.py:102`) today. Wiring `was_gated`
only into `issue_manager.py:2105-2123` leaves that misclassification standing.

Unlike the parallel path — correctly excluded below, since it has no confidence
gate and no reason mapping to route — the sprint path has both the gate and an
existing skip bucket (`SprintState.skipped_blocked_issues`, `sprint.py:103`).
Mirroring costs two `elif result.was_gated:` arms (one per dispatch site,
`run.py:711-724` and `run.py:878-895`), writing to `skipped_blocked_issues` with
the gate's `failure_reason`. No new state shape.

Safe for the sprint FSM consumer: `sprint-build-and-validate.yaml:168` merges
both buckets —
`jq '[(.failed_issues // {} | keys), (.skipped_blocked_issues // {} | keys)] | flatten | unique'`
— so a failed→skipped move is invisible to `extract_unresolved`.

**Known adjacent defect — do not widen scope to fix it here.** `_process_issue`
records corrections unconditionally, *after* the dispatch switch
(`issue_manager.py:2124-2125`), including for issues routed to `mark_skipped`.
This is already live on `main`: the BLOCKED verdict returns `was_blocked=True`
**with** `corrections=corrections` (`issue_manager.py:1068-1075`), so a
corrected-then-blocked issue lands in the numerator and not the denominator —
`Auto-corrections: 1/0` is reachable today, independent of this bug. Confining
Part 3 to the confidence gate avoids adding to it. If the numerator is ever
filtered, it must be filtered on the same predicate as the denominator.

The summary renderer does not print `skipped_issues` at all today
(`issue_manager.py:1949-1991`) — a pre-existing gap that already hides
`was_blocked`/`plan_created` skips. Adding a "Skipped issues:" block is
discretionary here; see Open Questions.

**Part 4 — the correction-rate annotation (absorbed from BUG-3253).**

Part 3 fixes the auto-correction rate's denominator as a side effect: with the
confidence gate routed to `skipped_issues`, `total_issues =
len(state.completed_issues) + len(state.failed_issues)`
(`issue_manager.py:1973`) stops counting issues that never ran `/ll:ready-issue`
and so never had the opportunity to contribute to the numerator. No change to
that line is required.

What Part 3 does *not* do is disclose the exclusion. A bare `1/1 (100.0%)` is
indistinguishable from a run where nothing was gated, so annotate the line at
`issue_manager.py:1971-1977`, sourcing the count from `state.skipped_issues`
filtered to gated entries:

```
Auto-corrections: 1/1 (100.0%) (1 gated before Phase 1)
```

Round parentheses, matching the codebase's inline-annotation convention —
`_sample()` (`work_verification.py:48-58`), `worker_pool.py:1365`,
`issue_history/formatting.py:216,735`, all `"(...)"`. No square-bracket
annotation precedent exists.

Observed impact this corrects, from the same 2026-08-17 run: one issue ran
Phase 1 and was corrected, giving a true rate of 1/1 = 100%, but the summary
reported `Auto-corrections: 1/2 (50.0%)` — the second denominator slot belonging
to ENH-3240, whose log reads `PHASE1_NOT_STARTED ENH-3240 confidence_gate`. The
metric is mechanically biased downward by exactly the number of
confidence-gate-blocked issues, which makes it unusable for the quality tracking
`state.py:32-34` says it exists for.

Constraints on Part 4:

- **Keep the zero-denominator guard.** The existing `if total_issues > 0 else 0`
  must survive — a run where every issue was gated now has a denominator of zero
  where it previously had a nonzero one. This guard is a uniform codebase
  convention (`orchestrator.py:1650`, `issue_progress.py:161-162`,
  `hotspots.py:70,96`, `dependency_mapper/analysis.py:227,317,389`).
- **Numerator and denominator must be filtered on the same predicate.**
  `_process_issue` records corrections unconditionally after the dispatch switch
  (`issue_manager.py:2124-2125`), so an excluded-but-corrected issue would yield
  a rate above 100%, or `1/0`. Excluding the confidence gate is safe for free —
  its `_stamped_result(...)` omits `corrections=` entirely. See the known
  adjacent defect above for the BLOCKED-verdict case that already violates this
  on `main`.
- **`ll-auto` only.** `ll-sprint` computes no correction rate at all (no
  `corrections` handling anywhere in `cli/sprint/run.py`), so Part 4 does not
  reach it even though Part 3 does. `ll-parallel` has the rate
  (`orchestrator.py:1649-1653`) but no confidence gate, so it has no exposure to
  this bias; its denominator is integer counters on `IssuePriorityQueue`
  (`parallel/priority_queue.py:110-194`), not a reason mapping, and there is
  nothing to annotate.
- **New test, not an extension.** No existing test exercises
  `_log_timing_summary`'s or the orchestrator's `Auto-corrections:` output —
  confirmed by grep for `_log_timing_summary`, `Auto-corrections`, and
  `PROCESSING SUMMARY` across `scripts/tests/`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

- **Precedent favors `raw_confidence: int | None` over a `confidence_present: bool` sibling field.** No dataclass in this codebase adds a `_present: bool` companion to a coerced field; every absence-preserving field found instead widens its own type to `T | None` — e.g. `IssueInfo.confidence_score: int | None` (`issue_parser.py:2154`), populated via `self._coerce_optional_int(...)` (`issue_parser.py:2480`, method defined at `2908-2919`). Part 1 names both options; only the `int | None` form matches an existing codebase pattern.
- **Part 3's sequential-path blast radius is narrower than described.** `was_blocked`/`plan_created` → `mark_skipped()` → `ProcessingState.skipped_issues` is live, tested (`test_issue_manager.py:3862-3899`), and already excluded from the correction-rate denominator at `issue_manager.py:1973`. The confidence gate simply never sets either flag on its `_stamped_result(...)` call. The **parallel path is a separate story**: it has no skip bucket at all, and its BLOCKED-verdict handling already diverges from the sequential path (see Program Design findings). Scoping Part 3 to the sequential path only leaves the parallel path both without a confidence gate today (`worker_pool.py` has no `readiness_status()` call) and with its own pre-existing BLOCKED-classification gap.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

Findings grouped by category:

### Files to Modify
- `scripts/little_loops/cli/issues/check_readiness.py` — `ReadinessStatus` dataclass (line 16) and the `readiness_status()` coercion (line 42, `or 0` at line 87)
- `scripts/little_loops/issue_manager.py` — pre-Phase-1 gate branch (806-835), `IssueProcessingResult` (639-655), the result-to-state routing switch (2105-2123), and `_log_timing_summary`'s `Auto-corrections:` line (1971-1977; Part 4)
- `scripts/little_loops/cli/sprint/run.py` — the two result-dispatch sites (711-724, 878-895); Part 3 only
- `docs/reference/CLI.md:406` — states verbatim that a sub-threshold issue "is skipped and reported via the `failed` channel with reason `below_readiness_threshold (N < M)`". Part 3 falsifies the channel and Part 2 changes the message. Both halves of that sentence need rewriting; `docs/reference/API.md` needs no change (`IssueProcessingResult` is not documented there, and `ProcessingState`'s shape is unchanged).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/check_readiness.py:115` (`cmd_check_readiness`) and `scripts/little_loops/issue_manager.py:811` (pre-Phase-1 gate) both call `readiness_status()` — confirmed via code graph (`callers-of`)
- `scripts/little_loops/issue_manager.py:2105-2123` is the sole consumer of `IssueProcessingResult.was_blocked`/`plan_created` for skip routing

### Conventions in Force
- Absence-preserving fields in this codebase widen the type to `T | None` rather than adding a `_present: bool` sibling — evidence: `IssueInfo.confidence_score: int | None` (`issue_parser.py:2154`) populated via `_coerce_optional_int()` (`issue_parser.py:2738-2749`, "returns None if raw is None or not a digit string"), and a parallel `_coerce_tristate_bool()` (`issue_parser.py:2751-2765`) for tri-state booleans. No `_present: bool` sibling-field precedent exists anywhere in the codebase.
- A "not a failure" outcome is expressed by setting an existing boolean flag on `IssueProcessingResult` (`was_blocked`, `plan_created`) while still returning `success=False`; the flag is interpreted only at the state-mapping switch in `_process_issue()` (`issue_manager.py:2105-2123`), which routes it to `state_manager.mark_skipped(...)` instead of `mark_failed(...)`. `ProcessingState.skipped_issues` (`state.py:53`) and `StateManager.mark_skipped()` (`state.py:221-232`) already exist for this purpose — evidence: `was_blocked=True` on the BLOCKED verdict (`issue_manager.py:1068-1075`) and `plan_created=True` on the plan-awaiting-approval branch (`issue_manager.py:1409-1417`) both route there today.
- Every pre-Phase-1/pre-Phase-2 gate halt in `process_issue_inplace` follows a fixed shape: logger message → stable stdout marker(s) → early `return _stamped_result(success=False, ...)` → a comment citing the earlier gate it mirrors. Evidence: confidence gate (`issue_manager.py:800-835`), learning-gate blocked/impl_failed/infra_failed (`1151-1207`).

### Tests
- `test_issue_manager.py:5457` (`TestConfidenceGatePreCheck`) — existing coverage of the confidence-gate branch, split across a marker-only test (`test_sub_threshold_prints_confidence_gate_blocked_marker`, `5544-5570`) and a result-field test (`test_sub_threshold_score_skips_before_phase_1`, `5525-5542`)
- `test_issue_manager.py:3862-3899` (`test_unreachable_reason_was_blocked_and_plan_created_wording`) — direct precedent for testing skip-vs-failure classification via `mark_skipped`
- `scripts/tests/` sprint-run coverage — Part 3's sprint arms need a case at each of the two dispatch sites (`run.py:711-724`, `878-895`) asserting a gated result lands in `SprintState.skipped_blocked_issues`, not `failed_issues`; mirror whatever existing `was_blocked` sprint coverage exists.
- Part 4's test is entirely new: no test anywhere in `scripts/tests/` exercises `_log_timing_summary`'s or the orchestrator's `Auto-corrections:`/`PROCESSING SUMMARY` output (confirmed by grep for all three strings).
- `test_check_readiness.py` — scoped to `readiness_status()`/`cmd_check_readiness()` in isolation; its `_make_issue()` helper (`22-35`) already supports omitting `confidence_score` entirely to model the absent case, distinct from an explicit `0`

## Program Design

### Types
- `ReadinessStatus` (`scripts/little_loops/cli/issues/check_readiness.py:16`) gains two
  fields: `raw_confidence: int | None` and `raw_outcome: int | None`. Each carries the
  frontmatter value before coercion, `None` when the key is absent, null, or
  non-numeric — see the Coercion Helper decision rule for how. The existing `confidence: int` / `outcome: int` fields and the
  `meets_readiness`/`meets_outcome` properties keep their current semantics unchanged,
  so every existing consumer is unaffected. Both new fields default to `None`; declare
  them last so any positional construction in tests stays valid.
- `IssueProcessingResult` (`scripts/little_loops/issue_manager.py:639-655`) gains
  `was_gated: bool = False`, alongside the existing `was_blocked`/`plan_created`
  flags it mirrors. Part 3 only.

### Signatures
- `readiness_status(config: BRConfig, issue_id: str, *, default_readiness: int = 85, default_outcome: int = 65) -> ReadinessStatus | None` — `scripts/little_loops/cli/issues/check_readiness.py:41` — resolves the issue, reads frontmatter, and builds the status. This is where `fm.get("confidence_score") or 0` (line 87) and `fm.get("outcome_confidence") or 0` (line 88) live, and where `raw_confidence`/`raw_outcome` must be populated before the coercion discards the distinction.
- `IssueParser._coerce_optional_int(self, raw: Any) -> int | None` — `scripts/little_loops/issue_parser.py:2908` — `return int(raw) if raw is not None and str(raw).isdigit() else None`. **An instance method on `IssueParser` (class at `issue_parser.py:2431`), not a module-level function** — `check_readiness.py` cannot import and call it as written. See the Coercion Helper decision rule.
- `cmd_check_readiness(config: BRConfig, args: argparse.Namespace) -> int` — `scripts/little_loops/cli/issues/check_readiness.py:95` — the `ll-issues check-readiness` entry point. Requires both thresholds and ignores `enabled`. Must not change: `autodev.yaml` invokes it at three sites with `--readiness`/`--outcome`.
- `AutoManager._log_timing_summary(self, run_start_time: float) -> None` — `scripts/little_loops/issue_manager.py:1949` — owns the `Auto-corrections:` line at `1971-1977`. Part 4 only: the denominator at `1973` needs no edit once Part 3 lands; the `(N gated before Phase 1)` suffix and the preserved `if total_issues > 0 else 0` guard go here.
- `_stamped_result(**kwargs: Any) -> IssueProcessingResult` — `scripts/little_loops/issue_manager.py:768` — the local closure stamping base-state onto every outcome. The gate branch's `success=False` return flows through here, which is where a distinct skip classification would have to be expressed.

### Call Path
The gate path this bug reports:
`ll-auto --only <ID>` -> `AutoManager._process_issue()` -> the pre-Phase-1 gate at `scripts/little_loops/issue_manager.py:806-833` -> `readiness_status()` (`check_readiness.py:41`) -> `parse_frontmatter()` -> `int(fm.get("confidence_score") or 0)` at `check_readiness.py:87` -> `ReadinessStatus.meets_readiness` -> `logger.warning(...)` + two `print(...)` markers -> `_stamped_result(success=False, failure_reason="below_readiness_threshold ...")` -> `state.failed_issues` -> `_log_timing_summary()` at `issue_manager.py:1949`.

The spec this path is meant to mirror:
`skills/manage-issue/SKILL.md:183` — "If absent or below `readiness_threshold` and `--force-implement` is not set, HALT and direct the user to run `/ll:confidence-check [ID]`."

### Decision Rules
- **Add a field, do not change `confidence`'s type.** Making `confidence` an `int | None` would force every consumer to handle the None case. The `ReadinessStatus` docstring already establishes the pattern of carrying multiple narrow signals rather than one collapsed verdict, precisely so different callers stay correct; `raw_confidence` follows it.
- **`raw_confidence: int | None`, not `confidence_present: bool`.** Settles the two options Part 1 originally named. The bool matches no codebase precedent *and* is wrong for `confidence_score: null` — see Part 1 for the full argument.
- **Coercion Helper: inline a local helper, do not import.** `_coerce_optional_int`
  is an instance method on `IssueParser` (`issue_parser.py:2908`), so
  `check_readiness.py` cannot call it — and importing `IssueParser` there purely
  to reach a private method would invert the dependency (`check_readiness` is a
  thin CLI leaf). Inline the one-line body as a module-private helper in
  `check_readiness.py`, matching `IssueParser._coerce_optional_int`'s semantics
  exactly. Lifting the method to module scope with `IssueParser` delegating is
  the acceptable alternative if a third caller ever appears; it is not worth the
  churn for one. Either way the semantics must stay `str(raw).isdigit()`-based:
  `readiness_status` reads frontmatter with `coerce_types=True`, so the value
  arriving is already an `int` for well-formed scores, and `str(85).isdigit()`
  is `True` — the helper is correct on both `int` and `str` input, and correctly
  returns `None` for negatives and floats.
- **The gate decision does not change.** Absent and zero both halt today and must both halt after this fix. Only the reported reason and the classification differ. This keeps the fix free of any behavior change for the pass/fail path.
- **Marker strings are frozen.** `CONFIDENCE_GATE_BLOCKED <ID>` and `PHASE1_NOT_STARTED <ID> confidence_gate` are consumed by `autodev.yaml`'s `check_impl_reached` discriminator (see the comments at `issue_manager.py:819-826`). Remediation text goes on the `logger.warning` line, never into the marker lines.
- **Threshold resolution stays the raw-JSON read.** `readiness_status`'s docstring is explicit that it must remain absence-sensitive rather than sourcing from `ConfidenceGateConfig`, because the config dataclass cannot express "key absent" and would break `autodev.yaml`'s `--readiness`/`--outcome` fallback. Do not refactor it while in this file.
- **Part 3 covers the confidence gate only.** Not the learning gate (post-Phase-1, carries `corrections`), not the decision gate (never produces a failure result at all — `issue_manager.py:1135-1136` logs a warning and falls through to Phase 2).
- **Part 3 covers both `process_issue_inplace()` consumers: `ll-auto` and `ll-sprint`.** The gate lives inside `process_issue_inplace`, so every caller inherits it; `cli/sprint/run.py` is a caller with its own dispatch chain (`run.py:711-724`, `878-895`) and its own skip bucket (`SprintState.skipped_blocked_issues`, `sprint.py:103`). Fixing only `issue_manager.py` leaves `ll-sprint` misclassifying. See Part 3 above for the two-arm change.
- **Part 3 excludes the parallel path.** `parallel/worker_pool.py` has no confidence gate — no `readiness_status()` call exists in it — and `parallel/orchestrator.py`'s denominator reads integer counters (`queue.completed_count + queue.failed_count`, `orchestrator.py:1649`), not a reason mapping. There is nothing for this fix to route there. The parallel path's own BLOCKED-classification gap is pre-existing and out of scope.
- **Part 4 annotates; it does not filter.** The denominator change is entirely a
  consequence of Part 3's routing. Do not add a `failure_reason` string
  predicate to `_log_timing_summary` — that route was evaluated under BUG-3253
  and withdrawn: it cannot distinguish pre- from post-Phase-1 gates without
  excluding the learning gate, which is the very defect it would be fixing,
  inverted. No `failure_reason`-string classifier exists anywhere in the
  codebase (grep for `_is_.*failure`/`_is_.*_reason` returns zero hits); gate
  classification is done via stdout markers today.
- **Parts 1-2, Part 3, and Part 4 are separable, but Part 4 depends on Part 3.**
  Part 4's denominator correctness comes from Part 3's routing; shipping the
  annotation alone would label a still-miscounted rate.
- **Parts 1-2 and Part 3 are separable.** Parts 1-2 touch two files and carry no state-shape change. Part 3 adds one dataclass field and one dispatch arm; both reuse existing tested infrastructure.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

- **Existing skip-routing infrastructure narrows Part 3's blast radius for the sequential (`ll-auto`) path.** `IssueProcessingResult` already carries `was_blocked: bool` and `plan_created: bool` (`issue_manager.py:639-655`); both route through the state-mapping switch in `_process_issue()` (`issue_manager.py:2105-2123`) to `state_manager.mark_skipped()` (`state.py:221-232`) rather than `mark_failed()`. `ProcessingState.skipped_issues: dict[str, str]` (`state.py:53`) already exists with a docstring naming exactly this distinction ("a non-failure skip reason (e.g. blocked-by-dependency, plan-awaiting-approval)"). For the sequential path, Part 3 reduces to: give the confidence-gate branch a way to signal "skip, not fail" on its `_stamped_result(...)` call, plus one new arm in the routing switch — not a new state shape.
- **`_log_timing_summary` does not render `skipped_issues` at all today** (`issue_manager.py:1949-1991`) — only a "Failed issues:" block exists (`1965-1968`). This is a pre-existing gap independent of this bug: `was_blocked`/`plan_created` skips are already silently absent from the run summary. Whether Part 3 also needs a "Skipped issues:" block, or leaves that gap standing, is open.
- **The parallel path (`parallel/orchestrator.py`) has no `skipped_issues`/`mark_skipped` concept at all.** `IssuePriorityQueue` only tracks `completed_count`/`failed_count` (`priority_queue.py:110-194`). `ParallelOrchestrator._on_worker_complete`'s dispatch (`orchestrator.py:1071-1232`) has no `elif result.was_blocked` arm before its generic `else: mark_failed(...)` — so a BLOCKED-verdict `WorkerResult` (which does set `was_blocked=True`, `worker_pool.py:508-520`) counts toward `queue.failed_count` there, unlike the sequential path where the equivalent case is excluded. A Part-3 fix confined to `issue_manager.py` does not close this parallel-path gap; the two paths are already materially divergent here, not just near-duplicates.

## Open Questions

- Should Part 3 also add a "Skipped issues:" block to `_log_timing_summary`?
  Skips are invisible in the summary today (`was_blocked`/`plan_created`
  included), so shipping Part 3 without it means a gate-blocked issue disappears
  from the summary entirely rather than appearing under the wrong heading —
  arguably worse for the operator than the status quo. Leaning yes.

_Resolved by review, 2026-08-18:_

- ~~Does any FSM loop currently key off `failed_issues` containing gate-blocked
  IDs?~~ **No loop is at risk; no compatibility window needed.** A repo-wide
  grep over `loops/` finds exactly one state-file consumer of a `failed_issues`
  bucket: `sprint-build-and-validate.yaml:168`'s `extract_unresolved`, and it
  merges both buckets —
  `jq '[(.failed_issues // {} | keys), (.skipped_blocked_issues // {} | keys)] | flatten | unique'`
  — so a failed→skipped move is invisible to it. Nothing reads `ll-auto`'s
  `ProcessingState.failed_issues` from a loop at all. The stdout markers are
  unaffected either way, so loops routing on `CONFIDENCE_GATE_BLOCKED` /
  `PHASE1_NOT_STARTED` were never at risk.
- ~~Should Part 3 land here or split into its own issue?~~ Land here. Its blast
  radius is one dataclass field plus one dispatch arm over already-tested
  infrastructure (`mark_skipped`, `skipped_issues`), and it is what makes
  BUG-3253's confidence-gate case correct without string matching.

## Related Issues

- FEAT-3117 — wires an Advisor `confidence_gate` consult trigger into this exact
  call site (`issue_manager.py`'s pre-Phase-1 gate). Adjacent, not overlapping:
  it adds an escalation path, this fixes what the gate reports. FEAT-3117 is
  blocked on FEAT-3116/FEAT-3120; this issue is not.
- BUG-3253 — **superseded by this issue and cancelled, 2026-08-18.** It reported
  the auto-correction rate metric distorted by this issue's
  failure-classification half. Once the route was settled on Option C′, its
  entire fix mechanism *was* Part 3, leaving only the disclosure annotation and
  a new test — both now absorbed here as Part 4. Closing it avoids a
  single-line issue permanently blocked on this one. Its analysis of the
  denominator, the numerator/denominator symmetry invariant, and the parallel
  path's separate divergences is carried into Part 4 and the Decision Rules
  rather than lost.

## Related Key Documentation

- `skills/manage-issue/SKILL.md:179-183` — Phase 2.5 confidence gate spec, the
  behavior `ll-auto`'s gate is meant to mirror.
- `scripts/little_loops/state.py:32-34` — states that failed issues and
  auto-corrections are tracked for quality purposes; the rationale for Part 4.

## Status

**Open** | Created: 2026-08-17 | Priority: P2

## Session Log
- supersession - 2026-08-18 - absorbed BUG-3253 as Part 4 (correction-rate annotation, zero-denominator guard, numerator/denominator symmetry invariant, new `Auto-corrections:` test); declared `supersedes: [BUG-3253]`
- pre-implementation review (round 2) - 2026-08-18 - corrected the `_coerce_optional_int` citation (instance method on `IssueParser` at `issue_parser.py:2908`, not a module function at 2738) and added the Coercion Helper decision rule; pulled `ll-sprint`'s two dispatch sites into Part 3 scope; added `docs/reference/CLI.md:406` to Files to Modify; resolved the `failed_issues` FSM-consumer open question
- `/ll:confidence-check` - 2026-08-18T03:03:04 - `1941922d-3eb4-4f32-8b99-167f8846ca3b.jsonl`
- pre-implementation review - 2026-08-18 - settled Part 1 on `raw_confidence: int | None`, pulled `outcome_confidence` into scope, specified Part 3 as `was_gated` + `mark_skipped` scoped to the confidence gate only, recorded the numerator asymmetry and the sequencing ahead of BUG-3253
- `/ll:confidence-check` - 2026-08-18T01:57:00 - `22c6cfbd-e81b-49b4-b781-b4588a9711ab.jsonl`
- `/ll:reconcile-issue` - 2026-08-18T01:53:03 - `06441b6f-0a06-4067-9c07-e33e815934ec.jsonl`
- `/ll:refine-issue` - 2026-08-18T01:45:34 - `45517e10-4dcf-4cdb-ac90-c8175e3464a2.jsonl`
- `/ll:format-issue` - 2026-08-18T01:35:12 - `f0f6a7d7-4813-4604-95ee-0469a847224f.jsonl`
- `/analyze_log` - 2026-08-17 - ll-auto run audit (ENH-3237, ENH-3240)

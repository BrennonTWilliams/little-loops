---
id: FEAT-3405
title: Quality-regression detection, attribution, and report/CLI wiring
type: FEAT
priority: P0
status: open
discovered_date: '2026-09-07'
parent: FEAT-3398
blocked_by: FEAT-3404
labels:
- path-a
- observability
- regression-detection
learning_tests_required:
- yaml
verify_verdict: NON_VALID
size: Large
confidence_score: 80
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-3405: Quality-regression detection, attribution, and report/CLI wiring

## Summary

Detect quality regressions in the agent-quality metric series produced by the
local quality report over `history.db` — a prior-K-window baseline comparison —
and attribute each detected shift to the model, host, or little-loops version
whose share of the window's runs moved most, wired all the way through
`analyze_agent_quality()`, all four output formatters, and a new `--sensitivity`
CLI flag on `ll-history quality`.

## Parent Issue

Decomposed from FEAT-3398: Quality-regression detection with model/host/version
attribution. This is the second of two children. **Depends on FEAT-3404**
(`ll_version` column + typed reader path) — `load_window_compositions()` below
reads `orchestration_runs.ll_version`, which does not exist until FEAT-3404
lands.

## Current Behavior

`analyze_agent_quality()` (`little_loops/issue_history/agent_quality.py`)
already turns `history.db` into a `QualityAnalysis` — a time series of
`QualityWindow`s (fix rate, correction rate, cost per issue, tokens per issue,
retry inflation) bucketed by `(period, orchestrator)`. Nothing reads that series
for a shift: an operator has to eyeball the report output by hand to notice a
regression, and there is no attribution of a drop to a candidate cause.

## Expected Behavior

A new detection pass over `QualityAnalysis.windows` (and `retry_windows`) flags
the most recent window of each series when it drops against a baseline of prior
windows and, for each flagged window, names the model/host/version whose share
of the window's issues (or loop runs) shifted most versus the baseline (or
reports "no attributable change" when no dimension's mix moved). Detection is
deterministic and LLM-free. A fixture corpus with an injected drop is flagged; a
fixture corpus with none is not; a corpus whose early months predate usage
capture is not flagged at the capture boundary.

## Use Case

**Who**: A maintainer running `ll-*` quality reports across their own
agent-heavy projects.

**Context**: After bumping the model or host version, or after a little-loops
upgrade, the maintainer wants to know within one report run whether agent
quality moved — not weeks later after noticing a vague sense that "things feel
worse".

**Goal**: See "fix-rate dropped 30% since the 2026-09-01 model update" surfaced
automatically in the report, with a named cause to investigate.

**Outcome**: The report attaches a regression alert to the affected window, with
the coinciding change boundary named, instead of a silent line the maintainer
must interpret unaided.

## Motivation

The local agent-quality report already turns `history.db` into a longitudinal
metric series, but a series is only actionable if something reads it. Silent
quality regression — agents that got quietly worse after a model, host, or
toolkit change, with nobody noticing for weeks — is the failure mode the series
exists to catch. Attribution is what makes an alert actionable: a detected drop
with no candidate cause is noise.

## Design notes

Detection must be statistical over recorded values only — no LLM in the
detection path. The evidence chain this feeds is meant to be checkable by
someone who does not trust the agent.

**What the series actually is** (corrected 2026-09-08 against the live report,
`ll-history quality --format json`; point-in-time counts): `QualityWindow`s are
bucketed by the **`issue_events` done-transition timestamp** (`_load_closed_issues`
→ `month_key(done_ts)`, `agent_quality.py:225,510`) × the orchestrator label
from `orchestration_runs.driver` (default `unattributed`). They are **not**
bucketed by `orchestration_runs.started_at` — an earlier draft measured that
column and drew its sparsity conclusion from the wrong table. Live shape: 14
windows spanning 2026-01..2026-09 — `unattributed` 10 points, `ll-auto` 3
(Jul/Aug/Sep), `ll-sprint` 1 (Aug) — plus one window with `period ==
"unknown"` (13 closed issues whose `issue_events.ts` is empty; `month_key`
returns the literal sentinel `"unknown"`, `_utils.py:43-45`). Because
`"unknown"` sorts lexicographically **after** `"2026-09"`, a naive
sort-by-period would treat it as the newest window; it must be excluded by
name.

**Data density still rules out change-point detection** — attributed
orchestrators have 1–3 points each. The detection statistic is therefore a
**prior-K-window baseline comparison**, not a change-point algorithm: for each
`(metric, orchestrator)` series sorted by period, baseline = mean of the
previous `K` windows (default `K=3`, using however many exist, minimum 1) that
are eligible (see Decision Rules → Baseline eligibility); the current window is
flagged when its relative move in the worse direction exceeds `sensitivity` and
it is itself eligible. Windows whose period is the `"unknown"` sentinel are
excluded from every series and counted in a `skipped_unknown_period` field.

**The live DB has zero-valued early baselines.** Jan–Apr 2026 report
`correction_rate`/`cost_per_issue`/`tokens_per_issue` = 0.0 because
`usage_events`/`user_corrections` capture did not exist yet, not because work was
free; May then reads cost 0 → 16.49. A relative-move statistic divides by the
baseline, so without a rule this is both a `ZeroDivisionError` and a guaranteed
false alarm on first run. See Decision Rules → Baseline eligibility and Latest
window only.

**Retry inflation is a separate series.** It is not in `QualityWindow.metrics`;
it lives in `QualityAnalysis.retry_windows`, bucketed by `(period, loop_name)`
from `loop_runs` (42 live points, the densest series in the report) and has no
`issue_sessions` join, so model/host are unavailable there. It is detected over
as a second series keyed by `loop_name`, with attribution restricted to the
`ll_version` dimension read from `loop_runs.ll_version` — which is the sole
consumer of FEAT-3404's `loop_runs` half.

**There is no single "model in effect" per window.** The DB runs multiple models
concurrently per orchestration-run month. A boundary join has nothing to join
to. Attribution is instead a **composition shift**: for each flagged window,
compute the share of runs per model, per host, and per `ll_version` in the
window and in its baseline; report the `(dimension, value)` whose share
increased most, provided the increase exceeds `ATTRIBUTION_MIN_SHIFT` (default
0.25 absolute share). Below that, "no attributable change".

**Stamp gap**: per-issue model is derivable via `issue_sessions ->
usage_events.model` (the join the cost metric already uses; reaches 623 of 641
`issue_sessions` issues on this repo as measured 2026-09-08). Host is on
`raw_events.host` via the same session join. `ll_version` is read from
`orchestration_runs.ll_version` / `loop_runs.ll_version`, added by FEAT-3404.

## Dependencies

**FEAT-3404** (blocking): supplies the `orchestration_runs.ll_version` /
`loop_runs.ll_version` column this issue's `load_window_compositions()` reads.

Depends on the local agent-quality report over `history.db` for metric
definitions and windowing (`analyze_agent_quality()`, already shipped).

**Sequencing (re-checked 2026-09-08)**: the parent's sequencing note is stale.
ENH-3397 (retry reclassification) and FEAT-3399 (cross-repo aggregation) are
both `done`, so the retry-inflation fixtures here are simply written against
the current, already-reclassified `loop_runs.iterations` semantics — no
follow-up re-run is owed. FEAT-3399 never referenced this issue's type names
(grep confirmed). The live sibling to coordinate with is **FEAT-3410** (open,
`blocked_by: FEAT-3409`), which cites the same `analyze_agent_quality()` /
`format_agent_quality_*` signatures this issue extends; whichever lands second
re-verifies its citations.

## Proposed Solution

### Decision: `--sensitivity` convention

**Selected**: Module-level constant + CLI flag (Option A) — mirrors
`MIN_SAMPLE_SIZE` (`rework.py:35`) and `--min-sample`
(`cli/history.py:227-274,470-487`), reused a *third* time on this exact
`quality` subcommand (`agent_quality.py:48`, `cli/history.py:263-269,484-487`),
with its footgun (`or MIN_SAMPLE_SIZE` silently discarding an explicit `0`)
already fixed via the `is not None` guard. `DEFAULT_SENSITIVITY` lives as a
module constant in the detection module, threaded through
`detect_quality_regressions(..., sensitivity: float = DEFAULT_SENSITIVITY)`,
with a `--sensitivity` flag on `ll-history quality` using the same `is not
None` explicit-override check. Option B (`.ll/ll-config.json` schema entry) was
considered and rejected: its closest analog, `EvolutionConfig`, is never
actually read from project config on its one live `issue_history/` call path
(`analysis.py:143: EvolutionConfig()`), and it would provide no per-invocation
override for a threshold a maintainer will want to tune ad hoc for a single
report run.

## Program Design

### Types

- `RunAttribution`: `dimension: Literal["model", "host", "ll_version"]`,
  `value: str`, `window_share: float`, `baseline_share: float`, `shift: float`
  (= `window_share - baseline_share`).
- `RegressionEvent`: `metric: str`, `series: str` (the orchestrator label for
  `QualityWindow` metrics, the `loop_name` for `retry_inflation`), `period:
  str`, `value: float`, `baseline_periods: list[str]`, `baseline_value: float`,
  `magnitude: float` (relative move in the worse direction), `attribution:
  RunAttribution | None`; `to_dict()`. Carries scalars rather than the whole
  `QualityWindow` so the same type serves both series.
- `QualityRegressionAnalysis`: `events: list[RegressionEvent]`, `sensitivity:
  float`, `baseline_windows: int`, `latest_only: bool`, `skipped_unknown_period:
  int`, `skipped_zero_baseline: int`, `notes: tuple[str, ...]`; `to_dict()`.
  Follows the `detect_* -> *Analysis` convention. **Not** `RegressionAnalysis`
  — that name is taken by the unrelated bug-fix clustering type in
  `issue_history/models.py`.
- `WindowComposition`: `period: str`, `series: str`, `counts: dict[str,
  dict[str, float]]` (dimension -> value -> weighted count) plus a derived
  `shares()` helper. Storing counts (not shares) is what lets the baseline
  composition be **pooled** across K windows rather than a mean-of-shares.
  **Unit of "share"**: for `QualityWindow` series, the unit is a *closed issue
  in the window*; each issue contributes to every distinct `usage_events.model`
  (and `raw_events.host`) seen across its sessions, weighted by the same
  `1/len(issues)` multi-issue-session split `_usage_totals()` already uses
  (`agent_quality.py:295-334`), and to exactly one `ll_version` from its
  `orchestration_runs` row (issues in `unattributed` windows have no such row,
  so that dimension is simply empty there). For the `retry_inflation` series
  the unit is a `loop_runs` row and the only dimension is `ll_version`.

### Signatures

- `DEFAULT_SENSITIVITY = 0.30`, `DEFAULT_BASELINE_WINDOWS = 3`, `ATTRIBUTION_MIN_SHIFT = 0.25`, `HIGHER_IS_BETTER: frozenset[str] = frozenset({"fix_rate"})` (module constants; `classify_verdict` has no direction flag — fix-rate's verdict is derived upstream from `rework_share`, so the direction set must be explicit here)
- `detect_quality_regressions(analysis: QualityAnalysis, compositions: list[WindowComposition], *, sensitivity: float = DEFAULT_SENSITIVITY, baseline_windows: int = DEFAULT_BASELINE_WINDOWS, latest_only: bool = True) -> QualityRegressionAnalysis` — no `min_sample` parameter: eligibility is read from `QualityMetric.insufficient_history` / `RetryWindow.insufficient_history`, which `analyze_agent_quality()` already computed from `analysis.min_sample_size`.
- `attribute_change(window: WindowComposition, baseline: list[WindowComposition], *, min_shift: float = ATTRIBUTION_MIN_SHIFT) -> RunAttribution | None` — pools `baseline` counts before computing shares.
- `load_window_compositions(conn, issue_window: dict[int, tuple[str, str]], issue_ids: dict[int, str], session_issues: dict[str, set[int]]) -> list[WindowComposition]` — `issue_ids` maps `issue_num -> issue_id` text (needed to join `orchestration_runs.issue_id`, which is TEXT); `session_issues` is the `_session_issue_map()` result `analyze_agent_quality()` already holds. All three inputs are locals of `analyze_agent_quality()` at `agent_quality.py:504-514`; extend the `closed` loop there to also build `issue_ids`.
- `analyze_agent_quality(issues, *, db=DEFAULT_DB_PATH, min_sample=MIN_SAMPLE_SIZE, sensitivity: float = DEFAULT_SENSITIVITY, baseline_windows: int = DEFAULT_BASELINE_WINDOWS, latest_only: bool = True) -> QualityAnalysis` — the existing producer gains the three pass-through kwargs so the CLI → analyze → detect path is one call chain.

### Call Path

`analyze_agent_quality()` (`little_loops/issue_history/agent_quality.py`) ->
`QualityAnalysis` (gains an optional `regressions: QualityRegressionAnalysis |
None` field) -> `detect_quality_regressions()` -> all four formatters:
`format_agent_quality_markdown()`/`_text()` gain an additive `if
analysis.regressions is not None:` block (rendered even when `events` is empty,
so the skipped counts and the correlational note are always visible);
`_json()`/`_yaml()` pick it up through `QualityAnalysis.to_dict()`.

### Decision Rules

- **Detection statistic**: prior-K-window baseline comparison (not
  change-point). Per `(metric, series)` — series = orchestrator for the four
  `QualityWindow` metrics, `loop_name` for `retry_inflation` — sorted by
  period: baseline = mean of the up-to-`baseline_windows` preceding *eligible*
  windows; flag when the current window is eligible and its relative move in
  the worse direction exceeds `sensitivity`. Direction comes from
  `HIGHER_IS_BETTER` (only `fix_rate`); everything else, including
  `retry_inflation`, is lower-is-better. Magnitude = `(baseline - value) /
  baseline` for higher-is-better, `(value - baseline) / baseline` otherwise.
- **Unknown-period exclusion**: windows whose `period == "unknown"` (the
  `month_key` sentinel, `_utils.py:43-45`) are dropped from every series before
  sorting and counted in `skipped_unknown_period`. They are never the "latest"
  window even though the string sorts last.
- **Baseline eligibility**: a window is eligible for either side of the
  comparison only if `insufficient_history` is False **and**
  `metric.verdict is not None` (the cost coverage gate; a pricing-table gap must
  not read as a regression). Additionally, for `cost_per_issue` and
  `tokens_per_issue` a window with `value == 0.0` is ineligible as a baseline —
  on the live DB Jan–Apr 2026 are zero only because usage capture didn't exist.
  If, after these filters, `baseline_value == 0` (legitimately possible for
  `correction_rate`), the comparison is skipped and counted in
  `skipped_zero_baseline`; a relative move against zero is undefined, and
  `classify_verdict`'s "0 → anything = degrading" shortcut is too blunt for an
  alert that is supposed to be rarer and louder than a verdict.
- **Latest window only (default)**: only the most recent eligible window of
  each series is tested; `latest_only=False` (`--all-windows`) tests every
  window against its own trailing baseline. Rationale: the use case is "did
  quality move in *this* report run"; on the live DB the all-windows mode
  emits historical Aug-vs-Jul and May-vs-Apr alerts on every invocation.
- **Sensitivity default**: `DEFAULT_SENSITIVITY = 0.30`, deliberately wider than
  `classify_verdict`'s ±20% band so an alert is rarer and louder than a
  `degrading` verdict. Document the tradeoff: at `min_sample=5` a fix-rate
  window of 5 issues moves in 20% steps, so one extra reopen can trip 0.30 —
  `min_sample` gates both sides of the comparison; lower `sensitivity` = more
  alerts = more false positives on small windows.
- **Return type**: `QualityRegressionAnalysis` wrapper, per the `detect_* ->
  *Analysis` convention (five existing `detect_*` functions in
  `issue_history/` all follow this — `detect_manual_patterns`,
  `detect_config_gaps`, `detect_cross_cutting_smells`,
  `detect_recurring_feedback`, `detect_skill_bypass`); empty `events` is the
  not-found sentinel.
- **Baseline composition is pooled**: `attribute_change()` sums the
  `WindowComposition.counts` of all baseline windows per `(dimension, value)`
  and derives shares from the pooled totals, so a large baseline month is not
  outweighed by a tiny one. Only *increases* in share are candidates (the
  thing that showed up more is the named suspect); a dimension with no data on
  either side (e.g. `ll_version` for `unattributed`, or every dimension for a
  pre-v48 baseline) is skipped, not treated as a 0 → X shift.
- **Attribution dismissal escape hatch**: when no dimension's share shift in
  the flagged window exceeds `ATTRIBUTION_MIN_SHIFT` versus the baseline
  windows, `attribute_change()` returns `None` and the report renders "no
  attributable change" rather than omitting the `RegressionEvent` — a detected
  drop is always surfaced even without a named cause. Attribution is
  correlational (a mix shift coinciding with a drop), and the rendered note
  says so, matching `_STANDARD_NOTES`.

### False friend

`scripts/little_loops/issue_history/regressions.py`
(`analyze_regression_clustering()`) and `models.py:242,265`
(`RegressionCluster`/`RegressionAnalysis`) are an unrelated, pre-existing
bug-fix **regression-clustering** system (temporal + file-overlap heuristics
linking a bug fix to a later bug in the same file) — shares the word
"regression" with this issue's statistical quality-metric regression detection
but is a different system entirely; do not conflate when searching or naming.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- `scripts/little_loops/issue_history/quality.py` is a third same-word-adjacent
  module distinct from both `agent_quality.py` (this issue's producer) and the
  new `quality_regressions.py` (this issue's target module) — its docstring is
  "Issue history quality analysis: test gaps, rejections, manual patterns,
  config gaps" (`quality.py:1`), unrelated to the agent-quality metric series.
  A third false friend alongside `regressions.py`/`models.py`'s
  `RegressionCluster`/`RegressionAnalysis` already listed above — do not
  conflate any of the three when searching or naming.

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_history/agent_quality.py` —
  `analyze_agent_quality()` (line 462) and `format_agent_quality_markdown()`
  (line 619) are the existing producer/renderer this issue's
  `detect_quality_regressions()`/`attribute_change()` consume and extend.
- `scripts/little_loops/cli/history.py` — `ll-history quality` subcommand
  (parser line 251, handler line 470) calls `analyze_agent_quality` then
  `format_agent_quality_{json,yaml,markdown,text}` (487-496); this is where
  `--sensitivity`/`--baseline-windows`/`--all-windows` are added.
- `scripts/little_loops/issue_history/quality_regressions.py` (new module) —
  types, `load_window_compositions`, `detect_quality_regressions`,
  `attribute_change`.
- `scripts/little_loops/issue_history/__init__.py` — every existing
  `detect_*`/`analyze_*` function and its dataclasses is re-exported at the
  package level (e.g. `analyze_agent_quality`/`QualityAnalysis`/`QualityWindow`
  at lines 75-85, listed in `__all__` ~215-218, and in the module docstring's
  export list ~line 50); add `detect_quality_regressions`, `attribute_change`,
  `load_window_compositions`, `RunAttribution`, `RegressionEvent`,
  `QualityRegressionAnalysis`, `WindowComposition` the same way.

### Dependent Files (Callers/Importers)

- Importers of `agent_quality.py`:
  `scripts/tests/test_issue_history_agent_quality.py:15`,
  `scripts/little_loops/issue_history/__init__.py:75`.
- Callers of `format_agent_quality_markdown`:
  `scripts/little_loops/cli/history.py:494` (`main_history`),
  `scripts/tests/test_issue_history_agent_quality.py:371`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_history/agent_quality.py:482,495,552` — existing
  `QualityAnalysis(...)` constructor calls that do not pass `regressions`; the
  new field needs a `= None` default so these keep working unchanged. Same for
  `scripts/tests/test_issue_history_agent_quality.py:369`
  (`QualityAnalysis()` default-construction). [Agent 2 finding]
- `scripts/little_loops/issue_history/agent_quality.py:145-152`
  (`QualityAnalysis.to_dict()`) — this hand-written dict (not
  `dataclasses.asdict()`) is the actual JSON/YAML wire point per the Call Path
  section; it must add a `"regressions": self.regressions.to_dict() if
  self.regressions else None` key or `format_agent_quality_json`/`_yaml` won't
  emit the new data despite the formatter functions themselves being edited.
  [Agent 2 finding]
- `scripts/little_loops/issue_history/__init__.py` re-export surface has three
  distinct edit sites (all need the new
  `quality_regressions`/`RunAttribution`/`RegressionEvent`/
  `QualityRegressionAnalysis`/`WindowComposition`/`load_window_compositions`/
  `detect_quality_regressions`/`attribute_change` names): docstring export list
  lines 50, 63-66; `from little_loops.issue_history.agent_quality import (...)`
  block lines 75-84 (needs a new sibling `from
  little_loops.issue_history.quality_regressions import (...)` block);
  `__all__` at line 218 (`QualityAnalysis` neighbor) and lines 248-263
  (`analyze_agent_quality`/`format_agent_quality_*` neighbors). [Agent 2
  finding, refines existing bullet's "imports, `__all__`, docstring export
  list" with precise anchors]

### Conventions in Force

- Every `detect_*` function elsewhere in `issue_history/` returns a wrapping
  `*Analysis` dataclass, never a bare `list[...]` — followed here via
  `QualityRegressionAnalysis`.
- `format_agent_quality_markdown()` (line 619) already uses the
  additive-rendering shape: one `if analysis.<field>: lines.append("## <Heading>")
  ...` block per optional sub-report, appended without touching prior blocks.

## Implementation Steps

1. `load_window_compositions()` in a new sibling module
   `scripts/little_loops/issue_history/quality_regressions.py` builds per-
   `(period, series)` weighted counts: model/host from `issue_sessions ->
   usage_events.model` / `raw_events.host` (1/n multi-issue split), `ll_version`
   from `orchestration_runs.ll_version` joined on `issue_id` text, plus a
   per-`(period, loop_name)` `ll_version` composition from `loop_runs` for the
   retry series. Inputs are the `issue_window`/`session_issues` locals
   `analyze_agent_quality()` already builds (`agent_quality.py:504-514`) plus a
   new `issue_ids: dict[int, str]` built in the same `closed` loop.
2. `detect_quality_regressions()` and `attribute_change()` in the same module,
   per Program Design (two series families, unknown-period exclusion, baseline
   eligibility, zero-baseline skip, latest-only default, pooled attribution);
   `analyze_agent_quality()` gains `sensitivity`/`baseline_windows`/
   `latest_only` kwargs, calls them, and stores the result on the new
   `QualityAnalysis.regressions` field.
3. All four formatters render the result: additive blocks in
   `format_agent_quality_markdown()`/`_text()`, `to_dict()` for json/yaml. The
   block shows `skipped_unknown_period`/`skipped_zero_baseline` counts and the
   correlational-attribution note even when `events` is empty.
4. `--sensitivity`, `--baseline-windows`, and `--all-windows` flags on
   `ll-history quality` with the `is not None` guard (`cli/history.py:484-487`)
   for the two numeric flags.
5. Add `detect_quality_regressions`, `attribute_change`,
   `load_window_compositions`, `RunAttribution`, `RegressionEvent`,
   `QualityRegressionAnalysis`, `WindowComposition` to
   `issue_history/__init__.py`'s imports, `__all__`, and docstring export list.
6. Tests: injected-drop / no-drop fixture pair per `TestFixRate`; a
   mixed-model fixture where a drop coincides with a model-share shift asserts
   the attribution, and one where the mix is unchanged asserts `None`; an
   `issue_events` row with empty `ts` lands in `skipped_unknown_period` and is
   never the latest window; a zero-baseline `correction_rate` series is skipped
   and counted, not raised or flagged; a cost series whose first months are 0.0
   with no `usage_events` does **not** flag the first priced month; a
   coverage-suppressed cost window (`verdict is None`) is ineligible; a
   `retry_inflation` series over `loop_runs` flags and attributes to
   `ll_version`; `latest_only` default emits only the newest window per series
   while `--all-windows` emits historical ones; `--sensitivity`,
   `--baseline-windows`, `--all-windows` flag tests.
   Verified by `python -m pytest scripts/tests/test_issue_history_agent_quality.py
   scripts/tests/test_cli_history.py -v`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Give `QualityAnalysis.regressions` a `= None` default — the three existing
  `QualityAnalysis(...)` constructor call sites
  (`agent_quality.py:482,495,552`) and the test default-construction
  (`test_issue_history_agent_quality.py:369`) don't pass it and must keep
  working unmodified.
- Add a `"regressions"` key to `QualityAnalysis.to_dict()`
  (`agent_quality.py:145-152`) — the hand-written dict is the actual
  JSON/YAML emission point; editing `format_agent_quality_json`/`_yaml` alone
  is not sufficient.
- Update all three `issue_history/__init__.py` edit sites for the new names
  (`RunAttribution`, `RegressionEvent`, `QualityRegressionAnalysis`,
  `WindowComposition`, `load_window_compositions`,
  `detect_quality_regressions`, `attribute_change`): docstring lines 50, 63-66;
  new `from little_loops.issue_history.quality_regressions import (...)` block
  near lines 75-84; `__all__` entries near line 218 and lines 248-263.
- Add a `raw_events`-insertion test helper to
  `test_issue_history_agent_quality.py` before writing the host-attribution
  fixture — no existing helper covers the `host` dimension.

## Tests

- `scripts/tests/test_issue_history_agent_quality.py` — `TestFixRate`
  (137-164) already pairs a "flat, no drop" fixture
  (`test_flat_history_yields_full_fix_rate`, asserts `verdict == "stable"`)
  with a "drop injected" fixture
  (`test_reopened_issues_degrade_fix_rate_vs_baseline`, asserts `verdict ==
  "degrading"`) in the same class, built via `_close`/`_reopen` helpers against
  a real `tmp_path` sqlite db — the direct template for the AC's "fixture
  corpus with an injected drop is flagged; a corpus with none is not."
- `scripts/little_loops/stats.py::wilson_ci`/`paired_direction`, tested in
  `scripts/tests/test_stats.py::TestWilsonCI` — closest general-purpose
  statistical-test template (boundary cases, symmetry check, clamping,
  ordering invariant, hand-computed known values) for testing
  `detect_quality_regressions()`'s formula.
- `TestHistoryQualitySubcommand` (`scripts/tests/test_cli_history.py:220-271`)
  — 4 existing tests; add a 5th mirroring
  `test_quality_min_sample_flag_accepted` for `--sensitivity`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- `scripts/tests/test_issue_history_quality.py` exists but is a false friend by
  name only: it covers `TestUpdateRejectionMetrics`,
  `TestAnalyzeTestGapsGapScoreBranches`, `TestAnalyzeTestGapsPriorityThresholds`,
  `TestDetectConfigGapsFilesystem` (lines 30, 76, 113, 156) — rejection/test-gap/
  config-gap analysis, unrelated to `agent_quality`/quality-regression
  detection. New tests for this issue belong in
  `test_issue_history_agent_quality.py` / `test_cli_history.py` as already
  specified above, not this file.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_history_agent_quality.py` — the existing
  `_usage_event()` helper (lines 70-90) already parameterizes `model` per call
  and covers the model dimension for a mixed-model composition fixture with no
  changes needed. However **no helper inserts into `raw_events`** (which
  carries `host`, `session_store/schema.py:471-485`) tied to a
  session/issue — a new test helper is needed before the `host`-attribution
  fixture (Program Design's `WindowComposition.shares["host"]`) can be built.
  [Agent 3 finding]
- `scripts/little_loops/issue_history/__init__.py` — no existing test asserts
  `__all__`/re-export completeness for this package (repo-wide search found
  only the unrelated `TestPackageReexportSurface` in
  `scripts/tests/test_session_store_schema.py:2825-2844`, which covers
  `session_store`, not `issue_history`). Not a hard blocker, but the new
  `quality_regressions` names added to `__init__.py`'s three edit sites (see
  Dependent Files above) have no automated guard against a missed export;
  consider a matching `TestPackageReexportSurface`-style test for
  `issue_history` while touching this file. [Agent 3 finding]

## Documentation

- `docs/reference/API.md:2380,2393` — `analyze_agent_quality`/
  `format_agent_quality_*` entries need `detect_quality_regressions`/
  `attribute_change`/`RunAttribution`/`RegressionEvent` added.
- `docs/reference/CLI.md:3162` (`#### ll-history quality`) — document the new
  regression-alert output and `--sensitivity`/`--baseline-windows`/
  `--all-windows` flags, including the latest-only default and the
  zero-baseline / unknown-period skip counts.
- `docs/guides/HISTORY_SESSION_GUIDE.md:485` — reconcile the existing
  forward-reference to "a downstream regression-detection consumer" once this
  lands.

## Impact

- **Priority**: P0 — silent quality regressions are the failure mode the
  metric series exists to catch; without detection the series is observed by
  nobody.
- **Effort**: Medium — new detection module, genuinely new statistical code
  (no existing change-point/z-score/rolling-baseline utility exists anywhere in
  the codebase to adapt), plus 4-format wiring and a CLI flag.
- **Risk**: Medium — the detection pass is read-only and additive, but the
  statistic itself is novel with no prior value to anchor `DEFAULT_SENSITIVITY`
  to; the main risk is a poorly-calibrated default producing false positives on
  small windows (mitigated by `min_sample` gating both sides of the
  comparison).
- **Breaking Change**: No.

## Acceptance Criteria

- Detection is deterministic and LLM-free — statistical over recorded values
  only.
- A fixture corpus with an injected quality drop is detected; a corpus with no
  drop produces no alert (false-positive check is part of the test, not an
  afterthought).
- Each detection names the model/host/version whose share of the window's runs
  shifted most versus the baseline (with both shares shown), or explicitly
  reports "no attributable change" when no shift exceeds `ATTRIBUTION_MIN_SHIFT`.
- A fixture where a drop coincides with a model-mix shift attributes to that
  model; a fixture with the same drop and an unchanged mix attributes `None`.
- Windows whose period is the `month_key` sentinel `"unknown"` are excluded
  from every series and reported as a count; they are never selected as the
  latest window.
- A zero baseline is skipped and counted (`skipped_zero_baseline`), never
  raised or flagged; zero-valued `cost_per_issue`/`tokens_per_issue` windows and
  coverage-suppressed (`verdict is None`) windows are ineligible as baselines.
  Running against a DB whose early months predate usage capture does not flag
  the first priced month.
- By default only the most recent eligible window per series is tested;
  `--all-windows` tests every window.
- `retry_inflation` (`QualityAnalysis.retry_windows`, keyed by `loop_name`) is
  detected over as its own series, attributed on `ll_version` only.
- Sensitivity is configurable via `--sensitivity`, with a documented default
  and its false-positive tradeoff.
- All four output formats (`text`, `markdown`, `json`, `yaml`) carry the
  regression block.

## Status

**Open** | Created: 2026-09-07 | Priority: P0

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (Dependencies Hard Override, BUG-3051)
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Gaps to Address
- `blocked_by: FEAT-3404` is unresolved (status: open) — `load_window_compositions()` reads `orchestration_runs.ll_version`, which does not exist until FEAT-3404 lands. Wait for or prioritize FEAT-3404 before starting implementation here.

## Session Log
- `/ll:confidence-check` - 2026-09-08T14:57:01 - `ca488d79-9d00-4093-b23a-fe056ec17be3.jsonl`
- `/ll:verify-issues` - 2026-09-08T04:54:45 - `3160105b-dd7c-40a3-aa61-9ec1da8184c9.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-08T04:49:39 - `e0531aaa-d1f3-482e-9dd7-3feb0e19d4f4.jsonl`
- `/ll:verify-issues` - 2026-09-08T04:41:05 - `c5dd39be-b3d6-4711-bede-d6709e2c60d0.jsonl`
- `/ll:wire-issue` - 2026-09-08T04:36:04 - `cffe6054-9afb-4402-b700-c03555de36ac.jsonl`
- `/ll:refine-issue` - 2026-09-08T04:29:17 - `6c3d6722-d2d6-49ca-aa14-3fd65e063ef7.jsonl`
- `/ll:format-issue` - 2026-09-08T03:48:53 - `2c3dcc18-94f9-46a0-aa50-9e1b85813520.jsonl`
- `/ll:issue-size-review` - 2026-09-08T03:38:19 - `2c3dcc18-94f9-46a0-aa50-9e1b85813520.jsonl`

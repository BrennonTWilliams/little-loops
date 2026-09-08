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

A new detection pass over `QualityAnalysis.windows` flags drops against a
baseline of prior windows and, for each flagged window, names the
model/host/version whose share of the window's runs shifted most versus the
baseline (or reports "no attributable change" when no dimension's mix moved).
Detection is deterministic and LLM-free. A fixture corpus with an injected drop
is flagged; a fixture corpus with none is not.

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

**Data density rules out change-point detection** (measured against the live
`.ll/history.db` on 2026-09-08, point-in-time counts that will grow as the DB
accumulates more runs): windows are calendar months; `orchestration_runs` spans
2026-08-02..2026-09-08 (two calendar months, zero rows in July); per-orchestrator
monthly points are sparse (`ll-auto` 2 points, `ll-sprint` 1 point). 210 of 554
rows have `started_at IS NULL` and land in an empty-period bucket (exact count
confirmed). The detection statistic is therefore a **prior-K-window baseline
comparison**, not a change-point algorithm: for each `(metric, orchestrator)`
series sorted by period, baseline = mean of the previous `K` windows (default
`K=3`, using however many exist, minimum 1) that clear `min_sample`; the current
window is flagged when its relative move in the worse direction exceeds
`sensitivity` and it also clears `min_sample`. Windows with an empty/NULL period
are excluded from the series and counted in a `skipped_null_period` field.

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

**Sequencing note carried from parent**: ENH-3397 (`blocked_by: FEAT-3398`)
reclassifies retries and will change the `retry_inflation` metric this pass
detects over — it must re-run the injected-drop/no-drop fixtures for
`retry_inflation` after its change once this issue lands. FEAT-3399
forward-references this issue's type names — keep
`QualityRegressionAnalysis`/`RegressionEvent`/`RunAttribution` stable once
landed.

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
- `RegressionEvent`: `metric: str`, `window: QualityWindow`, `baseline_periods:
  list[str]`, `baseline_value: float`, `magnitude: float` (relative move in the
  worse direction), `attribution: RunAttribution | None`; `to_dict()`.
- `QualityRegressionAnalysis`: `events: list[RegressionEvent]`, `sensitivity:
  float`, `baseline_windows: int`, `skipped_null_period: int`, `notes:
  tuple[str, ...]`; `to_dict()`. Follows the `detect_* -> *Analysis` convention.
  **Not** `RegressionAnalysis` — that name is taken by the unrelated bug-fix
  clustering type in `issue_history/models.py`.
- `WindowComposition`: `period: str`, `orchestrator: str`, `shares:
  dict[str, dict[str, float]]` (dimension -> value -> share of runs). Built
  from `issue_sessions -> usage_events.model` / `raw_events.host` and
  `orchestration_runs.ll_version`.

### Signatures

- `DEFAULT_SENSITIVITY = 0.30`, `DEFAULT_BASELINE_WINDOWS = 3`, `ATTRIBUTION_MIN_SHIFT = 0.25` (module constants)
- `detect_quality_regressions(analysis: QualityAnalysis, compositions: list[WindowComposition], *, sensitivity: float = DEFAULT_SENSITIVITY, baseline_windows: int = DEFAULT_BASELINE_WINDOWS, min_sample: int = MIN_SAMPLE_SIZE) -> QualityRegressionAnalysis`
- `attribute_change(window: WindowComposition, baseline: list[WindowComposition], *, min_shift: float = ATTRIBUTION_MIN_SHIFT) -> RunAttribution | None`
- `load_window_compositions(conn, issue_window: dict[int, tuple[str, str]]) -> list[WindowComposition]`

  Reuses the per-issue `(period, orchestrator)` map `analyze_agent_quality()` already builds at `agent_quality.py:510`.

### Call Path

`analyze_agent_quality()` (`little_loops/issue_history/agent_quality.py`) ->
`QualityAnalysis` (gains an optional `regressions: QualityRegressionAnalysis |
None` field) -> `detect_quality_regressions()` -> all four formatters:
`format_agent_quality_markdown()`/`_text()` gain an additive `if
analysis.regressions and analysis.regressions.events:` block; `_json()`/`_yaml()`
pick it up through `QualityAnalysis.to_dict()`.

### Decision Rules

- **Detection statistic**: prior-K-window baseline comparison (not
  change-point). Per `(metric, orchestrator)` series: baseline = mean of the
  up-to-`baseline_windows` preceding windows that clear `min_sample`; flag when
  the current window clears `min_sample` and its relative move in the worse
  direction (per each metric's existing `higher_is_better`/lower-is-better
  convention in `classify_verdict`, `issue_history/_utils.py:57-71`) exceeds
  `sensitivity`. NULL/empty-period windows are excluded and counted.
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
  `--sensitivity`/`--baseline-windows` are added.
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
   `(period, orchestrator)` model/host/`ll_version` shares from `issue_sessions
   -> usage_events.model`, `issue_sessions -> raw_events.host`, and
   `orchestration_runs.ll_version`, reusing the `issue_window` map
   `analyze_agent_quality()` already builds (`agent_quality.py:510`).
2. `detect_quality_regressions()` and `attribute_change()` in the same module,
   per Program Design; `analyze_agent_quality()` calls them and stores the
   result on the new `QualityAnalysis.regressions` field.
3. All four formatters render the result: additive blocks in
   `format_agent_quality_markdown()`/`_text()`, `to_dict()` for json/yaml.
4. `--sensitivity` (and `--baseline-windows`) flags on `ll-history quality`
   with the `is not None` guard (`cli/history.py:484-487`).
5. Add `detect_quality_regressions`, `attribute_change`,
   `load_window_compositions`, `RunAttribution`, `RegressionEvent`,
   `QualityRegressionAnalysis`, `WindowComposition` to
   `issue_history/__init__.py`'s imports, `__all__`, and docstring export list.
6. Tests: injected-drop / no-drop fixture pair per `TestFixRate`; a
   mixed-model fixture where a drop coincides with a model-share shift asserts
   the attribution, and one where the mix is unchanged asserts `None`;
   NULL-`started_at` rows are excluded not bucketed; `--sensitivity` flag test.
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
  regression-alert output and `--sensitivity`/`--baseline-windows` flags.
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
- Rows with NULL `started_at` are excluded from the series and reported as a
  count, never bucketed into an empty period.
- Sensitivity is configurable via `--sensitivity`, with a documented default
  and its false-positive tradeoff.
- All four output formats (`text`, `markdown`, `json`, `yaml`) carry the
  regression block.

## Status

**Open** | Created: 2026-09-07 | Priority: P0

## Session Log
- `/ll:verify-issues` - 2026-09-08T04:54:45 - `3160105b-dd7c-40a3-aa61-9ec1da8184c9.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-08T04:49:39 - `e0531aaa-d1f3-482e-9dd7-3feb0e19d4f4.jsonl`
- `/ll:verify-issues` - 2026-09-08T04:41:05 - `c5dd39be-b3d6-4711-bede-d6709e2c60d0.jsonl`
- `/ll:wire-issue` - 2026-09-08T04:36:04 - `cffe6054-9afb-4402-b700-c03555de36ac.jsonl`
- `/ll:refine-issue` - 2026-09-08T04:29:17 - `6c3d6722-d2d6-49ca-aa14-3fd65e063ef7.jsonl`
- `/ll:format-issue` - 2026-09-08T03:48:53 - `2c3dcc18-94f9-46a0-aa50-9e1b85813520.jsonl`
- `/ll:issue-size-review` - 2026-09-08T03:38:19 - `2c3dcc18-94f9-46a0-aa50-9e1b85813520.jsonl`

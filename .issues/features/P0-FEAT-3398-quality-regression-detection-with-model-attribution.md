---
id: FEAT-3398
title: Quality-regression detection with model/host/version attribution
type: FEAT
priority: P0
status: open
discovered_date: '2026-09-07'
labels:
- path-a
- observability
- regression-detection
---

## Summary

Detect quality regressions in the agent-quality metric series produced by the local quality report over `history.db` — baseline windows plus change-point detection — and attribute each detected shift to the model, host, and little-loops version in effect, so the report can say *"fix-rate dropped 30% since the model update"* rather than just plotting a line.

## Current Behavior

`analyze_agent_quality()` (`little_loops/issue_history/agent_quality.py`) already turns `history.db` into a `QualityAnalysis` — a time series of `QualityWindow`s (fix rate, correction rate, cost per issue, tokens per issue, retry inflation) bucketed by `(period, orchestrator)`. Nothing reads that series for a shift: an operator has to eyeball the report output by hand to notice a regression, and nothing on a `QualityWindow` names the model, host, or little-loops version in effect for that window, so even a spotted drop has no candidate cause to attribute it to.

## Expected Behavior

A new detection pass over `QualityAnalysis.windows` flags statistically significant drops against a rolling baseline and, for each flagged window, names the model/host/version boundary its start coincides with (or reports "no attributable change" when none exists). Detection is deterministic and LLM-free. A fixture corpus with an injected drop is flagged; a fixture corpus with none is not.

## Use Case

**Who**: A maintainer running `ll-*` quality reports across their own agent-heavy projects.

**Context**: After bumping the model or host version, or after a little-loops upgrade, the maintainer wants to know within one report run whether agent quality moved — not weeks later after noticing a vague sense that "things feel worse".

**Goal**: See "fix-rate dropped 30% since the 2026-09-01 model update" surfaced automatically in the report, with a named cause to investigate (roll back the model, pin the host, or look at the harness itself).

**Outcome**: The report attaches a regression alert to the affected window, with the coinciding change boundary named, instead of a silent line the maintainer must interpret unaided.

## Motivation

The local agent-quality report already turns `history.db` into a longitudinal metric series, but a series is only actionable if something reads it. Silent quality regression — agents that got quietly worse after a model, host, or toolkit change, with nobody noticing for weeks — is the failure mode the series exists to catch, and detecting it by eye does not scale past one project.

Attribution is what makes an alert actionable. A detected drop with no candidate cause is noise: the operator cannot tell whether to roll back a model, pin a host, or investigate their own harness. Naming the change boundary the shift coincides with turns a plotted line into a decision.

## Design notes

Detection must be statistical over recorded values only — no LLM in the detection path. The evidence chain this feeds is meant to be checkable by someone who does not trust the agent, and an LLM grading its own quality series is exactly the bias the deterministic verification-evidence work already rejects.

Baseline windows and change-point detection over the existing metric series are the mechanism; the attribution join is against the model/host/version stamps carried on runs.

## Dependencies

Depends on the local agent-quality report over `history.db` for metric definitions and windowing.

Requires that runs carry model/host/version stamps. If `history.db` does not already record them, adding that capture is in scope for this issue.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

Codebase-locator confirmed none of `RunAttribution`/`RegressionEvent`/`detect_quality_regressions`/`attribute_change` exist yet, and pinned down exactly where the new detection pass would plug into the existing agent-quality pipeline:

### Files to Modify
- `scripts/little_loops/issue_history/agent_quality.py` — `analyze_agent_quality()` (line 462) and `format_agent_quality_markdown()` (line 619) are the existing producer/renderer this issue's `detect_quality_regressions()`/`attribute_change()` consume and extend, per the issue's own Call Path.
- `scripts/little_loops/cli/history.py` — `ll-history quality` subcommand (parser line 251, handler line 470) calls `analyze_agent_quality` then `format_agent_quality_{json,yaml,markdown,text}` (487-496); this is the CLI entry point the Call Path terminates at.
- `scripts/little_loops/session_store/schema.py` / `writers.py` — capturing model/host/version stamps (the issue's Dependencies clause: "if `history.db` does not already record them, adding that capture is in scope") requires changes here; see gap below.

### Dependent Files (Callers/Importers)
- Importers of `agent_quality.py`: `scripts/tests/test_issue_history_agent_quality.py:15`, `scripts/little_loops/issue_history/__init__.py:75`.
- Callers of `format_agent_quality_markdown`: `scripts/little_loops/cli/history.py:494` (`main_history`), `scripts/tests/test_issue_history_agent_quality.py:371`.

### Model/host/version stamp gap (Dependencies clause)
- `usage_events` already carries a `model TEXT` column (`schema.py:514`, indexed `:523`); `raw_events` already carries `host TEXT NOT NULL` (`schema.py:475`, indexed `:490`). `orchestration_runs` (`schema.py:540`) carries `driver`/`head_sha`/`branch` but no model/host/version columns. No persisted little-loops-version stamp exists anywhere — `__version__` (`scripts/little_loops/__init__.py:83`) lives only in the installed package, never written to `history.db`. Confirms the issue's own contingency is real: `RunAttribution`'s model/host/version-boundary join has no existing per-run join point to read from today and this capture must be added, not merely surfaced.
- `record_orchestration_run()` and `record_loop_run_summary()` (`session_store/writers.py:1287,1428`) are the two per-run writers; neither signature currently accepts a model, host, or version parameter.

### Conventions in Force
- Every `detect_*` function elsewhere in `issue_history/` (`quality.py:272,410`, `debt.py:46`, `evolution.py:92,202`) returns a wrapping `*Analysis` dataclass (e.g. `ManualPatternAnalysis`, `RecurringFeedbackAnalysis`), never a bare `list[...]`. This issue's own signature, `detect_quality_regressions(...) -> list[RegressionEvent]`, departs from that convention — worth a deliberate call, not an accidental one.
- Two disagreeing conventions exist for exposing a detection threshold/sensitivity: (A) a module-level constant used as a function kwarg default plus a CLI flag with an explicit `is not None` check to allow an explicit falsy override (`rework.py:35`, `MIN_SAMPLE_SIZE`; `cli/history.py:486`), vs (B) a `.ll/ll-config.json` schema entry consumed via a dataclass (`config/features.py:1406-1419` `EvolutionConfig`, `config-schema.json:2176-2192`). No `DEFAULT_SENSITIVITY` or equivalent exists anywhere today under either convention — this issue introduces the first instance either way.
- `format_agent_quality_markdown()` (line 619) already uses the additive-rendering shape the issue's own Call Path describes reusing: one `if analysis.<field>: lines.append("## <Heading>") ...` block per optional sub-report, appended in sequence without touching prior blocks (mirrored at larger scale in `issue_history/formatting.py::format_analysis_markdown()`).
- **False friend**: `scripts/little_loops/issue_history/regressions.py` (`analyze_regression_clustering()`) and `models.py:242,265` (`RegressionCluster`/`RegressionAnalysis`) are an unrelated, pre-existing bug-fix **regression-clustering** system (temporal + file-overlap heuristics linking a bug fix to a later bug in the same file) — shares the word "regression" with this issue's statistical quality-metric regression detection but is a different system entirely; do not conflate when searching or naming.

### Tests
- `scripts/tests/test_issue_history_agent_quality.py` — `TestFixRate` (137-164) already pairs a "flat, no drop" fixture (`test_flat_history_yields_full_fix_rate`, asserts `verdict == "stable"`) with a "drop injected" fixture (`test_reopened_issues_degrade_fix_rate_vs_baseline`, asserts `verdict == "degrading"`) in the same class, built via `_close`/`_reopen` helpers against a real `tmp_path` sqlite db — this is the direct template for the AC's "fixture corpus with an injected drop is flagged; a corpus with none is not."

### Documentation
- `docs/reference/API.md:2380,2393` — `analyze_agent_quality`/`format_agent_quality_*` entries will need `detect_quality_regressions`/`attribute_change`/`RunAttribution`/`RegressionEvent` added.
- `docs/reference/CLI.md:3162` (`#### ll-history quality`) — will need the new regression-alert output and any new `--sensitivity`-style flag documented.

## Program Design

### Types

- `RunAttribution`: `model: str`, `host: str`, `ll_version: str`, `effective_from: str` (period key)
- `RegressionEvent`: `metric: str`, `window: QualityWindow`, `baseline_period: str`, `magnitude: float`, `attribution: RunAttribution | None`

### Signatures

- `detect_quality_regressions(analysis: QualityAnalysis, *, sensitivity: float = DEFAULT_SENSITIVITY) -> list[RegressionEvent]`
- `attribute_change(window: QualityWindow, attributions: list[RunAttribution]) -> RunAttribution | None`

### Call Path

`analyze_agent_quality()` (`little_loops/issue_history/agent_quality.py`) -> `QualityAnalysis` -> `detect_quality_regressions()` -> `format_agent_quality_markdown()` (extended to render `RegressionEvent`s alongside the existing window table)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

Analyzer and pattern-finder agents confirmed no existing statistical detection utility exists in this codebase to adapt, so the following are new decisions rather than reuse of an established gate:

### Decision Rules

- **Detection statistic**: deterministic, LLM-free, computed over `QualityAnalysis.windows` only. No existing change-point/z-score/rolling-baseline statistical utility exists in this codebase (searched repo-wide, no hits) — the fixed ±20%-band `classify_verdict()` baseline convention (`issue_history/_utils.py:57`, shared by `agent_quality.py`/`rework.py`) is the only existing "baseline" mechanism, and it is not itself a change-point detector; this issue's detection logic is new statistical code, not an adaptation of an existing one.
- **Sensitivity default**: `DEFAULT_SENSITIVITY` has no existing value or precedent anywhere in the codebase — must be chosen and documented fresh, with its false-positive tradeoff, per the Acceptance Criteria.
- **Attribution dismissal escape hatch**: when no model/host/version boundary's `effective_from` coincides with a flagged window's start, `attribute_change()` returns `None` and the report renders "no attributable change" rather than omitting the `RegressionEvent` — a detected drop is always surfaced even without a named cause.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

1. Model/host/little-loops-version stamps become readable per run: extend `record_orchestration_run()`/`record_loop_run_summary()` (`scripts/little_loops/session_store/writers.py:1287,1428`) and the `orchestration_runs` schema (`schema.py:540`) to carry them, since no per-run join point for this exists today (see Integration Map → Model/host/version stamp gap); verified by `python -m pytest scripts/tests/test_session_store_writers.py -v`.
2. `detect_quality_regressions()` and `attribute_change()` are added to `scripts/little_loops/issue_history/agent_quality.py` (or a sibling module, per the existing `agent_quality.py`/`rework.py` sibling-module shape), consuming `QualityAnalysis.windows` and the new per-run attribution stamps; the detection statistic is new deterministic code — no existing change-point/z-score utility exists to adapt (see Program Design → Decision Rules).
3. `format_agent_quality_markdown()` (`agent_quality.py:619`) is extended with an additive `if regressions:` block rendering `RegressionEvent`s, following the same per-field truthy-check shape already used for `analysis.retry_windows`.
4. A fixture corpus with an injected quality drop is flagged and a corpus with none is not, following the paired-test template already established in `scripts/tests/test_issue_history_agent_quality.py::TestFixRate`; verified by `python -m pytest scripts/tests/test_issue_history_agent_quality.py -v`.

## Impact

- **Priority**: P0 - Silent quality regressions are the failure mode the whole metric series exists to catch; without detection the series is observed by nobody.
- **Effort**: Large - requires both a new statistical detection module and, per Dependencies, adding model/host/version stamp capture to `history.db` if not already present.
- **Risk**: Low - read-only analysis over existing `history.db` data; no changes to the write path or existing report output beyond additive alerts.
- **Breaking Change**: No

## Acceptance Criteria

- Detection is deterministic and LLM-free — statistical over recorded values only.
- A fixture corpus with an injected quality drop is detected; a corpus with no drop produces no alert (false-positive check is part of the test, not an afterthought).
- Each detection names the candidate change (model/host/version boundary) it coincides with, or explicitly reports "no attributable change".
- Sensitivity is configurable, with a documented default and its false-positive tradeoff.

## Status

**Open** | Created: 2026-09-07 | Priority: P0


## Session Log
- `/ll:refine-issue` - 2026-09-08T00:56:22 - `c12a8469-1c0e-4551-abdc-a66d5e5d6bda.jsonl`
- `/ll:format-issue` - 2026-09-08T00:08:41 - `fd8050c6-8bbf-4735-ba8f-b83f5f588867.jsonl`

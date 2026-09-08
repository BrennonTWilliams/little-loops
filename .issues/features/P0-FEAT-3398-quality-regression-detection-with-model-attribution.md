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
learning_tests_required:
- yaml
confidence_score: 90
outcome_confidence: 40
score_complexity: 5
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 0
decision_needed: false
---

## Summary

Detect quality regressions in the agent-quality metric series produced by the local quality report over `history.db` — baseline windows plus change-point detection — and attribute each detected shift to the model, host, and little-loops version in effect, so the report can say *"fix-rate dropped 30% since the model update"* rather than just plotting a line.

## Current Behavior

`analyze_agent_quality()` (`little_loops/issue_history/agent_quality.py`) already turns `history.db` into a `QualityAnalysis` — a time series of `QualityWindow`s (fix rate, correction rate, cost per issue, tokens per issue, retry inflation) bucketed by `(period, orchestrator)`. Nothing reads that series for a shift: an operator has to eyeball the report output by hand to notice a regression, and nothing on a `QualityWindow` names the model, host, or little-loops version in effect for that window, so even a spotted drop has no candidate cause to attribute it to.

## Expected Behavior

A new detection pass over `QualityAnalysis.windows` flags drops against a baseline of prior windows and, for each flagged window, names the model/host/version whose share of the window's runs shifted most versus the baseline (or reports "no attributable change" when no dimension's mix moved). Detection is deterministic and LLM-free. A fixture corpus with an injected drop is flagged; a fixture corpus with none is not.

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

Baseline windows over the existing metric series are the mechanism; attribution compares each window's model/host/version composition against the baseline's.

### Design review corrections (2026-09-07)

_Added after review against the live `.ll/history.db`; these supersede the "change-point" and "boundary join" framing elsewhere in this issue._

- **Data density rules out change-point detection.** Windows are calendar months and `orchestration_runs` on this repo spans three months (2026-07..2026-09), so each orchestrator has 3-4 points. 210 of 554 rows have `started_at IS NULL` and would land in an empty-period bucket. The detection statistic is therefore a **prior-K-window baseline comparison**, not a change-point algorithm: for each `(metric, orchestrator)` series sorted by period, baseline = mean of the previous `K` windows (default `K=3`, using however many exist, minimum 1) that clear `min_sample`; the current window is flagged when its relative move in the worse direction exceeds `sensitivity` and it also clears `min_sample`. Windows with an empty/NULL period are excluded from the series and counted in a `skipped_null_period` field on the analysis. Window granularity stays monthly in this issue; a finer `--window` is a follow-up.
- **There is no single "model in effect" per window.** Every month in the DB runs 5-8 models concurrently (`usage_events.model` grouped by month). A boundary join keyed on `effective_from` has nothing to join to. Attribution is instead a **composition shift**: for each flagged window, compute the share of runs per model, per host, and per `ll_version` in the window and in its baseline; report the `(dimension, value)` whose share increased most, provided the increase exceeds `ATTRIBUTION_MIN_SHIFT` (default 0.25 absolute share). Below that, "no attributable change".
- **Most of the stamp gap is already closed.** Per-issue model is derivable today via `issue_sessions -> usage_events.model` (the join the cost metric already uses; reaches 623/639 issues on this repo). Host is on `raw_events.host` via the same session join. Only the little-loops **version** is unrecorded anywhere. Scope the schema migration to a single `ll_version TEXT` column on `orchestration_runs` (and `loop_runs`), read model/host through the existing joins, and drop the plan to thread `model`/`host` through every `record_orchestration_run` call site. Write-timing: `__version__` is known at dequeue, so `ll_version` follows the `base_sha` COALESCE pattern (`writers.py:1357-1360`).

## Dependencies

Depends on the local agent-quality report over `history.db` for metric definitions and windowing.

Requires that runs carry a little-loops version stamp; model and host are already recoverable from `usage_events`/`raw_events` via `issue_sessions`. Adding the `ll_version` capture is in scope for this issue.

**Sequencing**: ENH-3397 (`blocked_by: FEAT-3398`) reclassifies retries and will change the `retry_inflation` metric this pass detects over. This issue lands first; ENH-3397 must re-run the injected-drop/no-drop fixtures for `retry_inflation` after its change. FEAT-3399 forward-references this issue's type names — keep `QualityRegressionAnalysis`/`RegressionEvent`/`RunAttribution` stable once landed.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

The Wiring Phase's "Decide the `--sensitivity` config convention" item names two disagreeing, both-established codebase conventions for exposing a new tunable value, with no existing precedent tying report-time detection sensitivity to either one:

**Option A**: Module-level constant + CLI flag — mirrors `MIN_SAMPLE_SIZE` (`rework.py:35`) and `--min-sample` (`cli/history.py:227-274,470-487`). `DEFAULT_SENSITIVITY` lives as a module constant in the detection module, threaded through `detect_quality_regressions(..., sensitivity: float = DEFAULT_SENSITIVITY)`, with a `--sensitivity` flag on `ll-history quality` using the `is not None` explicit-override check (the `quality` subcommand's deliberate fix over `rework`'s `args.min_sample or MIN_SAMPLE_SIZE` footgun with an explicit `0`). No `.ll/ll-config.json` presence.

> **Selected:** Option A — module-level constant + CLI flag, matching the precedent already reused on this exact `quality` subcommand with a ready test template and no per-run override gap.

**Option B**: `.ll/ll-config.json` schema entry consumed via a dataclass — mirrors `EvolutionConfig` (`config/features.py:1407-1419`) and its `config-schema.json:2176-2192` mirror. A new small dataclass (e.g. `RegressionDetectionConfig`) nested under `HistoryConfig` via `field(default_factory=...)`, with a lenient `from_dict(cls, data)` classmethod and a matching schema-json object (`"additionalProperties": false`, per-field `"default"`/`"description"`). No CLI flag for any value in this family exists today.

No recommendation is implied by the research: both conventions are established and disagree on where a tunable belongs, and nothing in the codebase ties the quality/rework report-time sensitivity family specifically to one or the other.

### Decision Rationale

**Selected**: Option A — module-level constant + CLI flag.

**Reasoning**: Option A directly reuses a pattern already established twice in `rework.py`/`cli/history.py` (`MIN_SAMPLE_SIZE`, `FOLLOW_UP_WINDOW_DAYS`) and, critically, already reused a *third* time on this exact `quality` subcommand (`agent_quality.py:48`, `cli/history.py:263-269,484-487`) — with its footgun (`or MIN_SAMPLE_SIZE` silently discarding an explicit `0`) already identified and fixed via the `is not None` guard, and an exact test template ready to copy (`test_quality_min_sample_flag_accepted`, `test_cli_history.py:256-265`). Option B's closest analog, `EvolutionConfig`, is the only `HistoryConfig`-nested config actually consumed inside `issue_history/` — and even that consumer instantiates it with bare defaults (`analysis.py:143: EvolutionConfig()`) rather than reading `.ll/ll-config.json`, meaning the "established" config-schema convention has no example of an `issue_history/` detection function actually reading a project-config value on a live path. Option B also requires ~55-60 LOC of new scaffolding (dataclass, schema mirror, `_DATACLASS_SECTION_MAP` entry, `to_dict()` entry, dedicated test class) and provides no per-invocation override — a real gap for a detection threshold a maintainer will want to tune ad hoc for a single report run, something Option A's CLI flag already supports today.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A: constant + CLI flag | 3 | 3 | 3 | 3 | 12/12 |
| B: config-schema dataclass | 1 | 1 | 1 | 1 | 4/12 |

**Key evidence**:
- `agent_quality.py:48` already imports and reuses `MIN_SAMPLE_SIZE` on the very subcommand this issue extends.
- `cli/history.py:484-487`'s `is not None` guard is the exact footgun fix a `--sensitivity` flag would inherit for free.
- `analysis.py:143` shows `EvolutionConfig()` — Option B's own precedent — is never actually read from `.ll/ll-config.json` on its one live `issue_history/` call path.
- No `--config-override`-style flag exists anywhere in `cli/history.py`, so Option B would have no per-invocation override.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

Codebase-locator confirmed none of `RunAttribution`/`RegressionEvent`/`detect_quality_regressions`/`attribute_change` exist yet, and pinned down exactly where the new detection pass would plug into the existing agent-quality pipeline:

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- Locator confirmation: all `path:line` citations in this issue's own Files to Modify / Dependent Files / Root Cause sections remain accurate as of this pass — `docs/guides/HISTORY_SESSION_GUIDE.md`'s schema-version-history table still ends at `v47 | ENH-3204 | credential_scope_events table` (line 107) and its `orchestration_runs` column-enumeration row is still at line 132; `docs/ARCHITECTURE.md`'s matching table still ends at line 680. The file changed since the last refine pass but not in a way that invalidates any citation here.
- Sibling issue **FEAT-3399** (cross-repo history.db aggregation) already forward-references this issue's `RunAttribution`/`RegressionEvent`/`detect_quality_regressions`/`attribute_change` names in its own text — coordinate the concrete shape of these types with FEAT-3399 if the two land close together, since FEAT-3399 is not this issue's dependency but assumes this issue's naming.
- Naming precedent for host+model attribution already exists elsewhere: `advisor_host`/`advisor_model`/`main_model` is a three-column host+model set on `advisor_consults` (`schema.py:1255-1257`, added v45/FEAT-3300) — precedent for the column-naming shape, though not on `orchestration_runs` itself.
- New-column write-timing convention: the prior `orchestration_runs` column addition (`base_sha`/`base_dirty`, v38/ENH-2866) uses `SET x=COALESCE(excluded.x, x)` in `record_orchestration_run()`'s UPSERT (`writers.py:1358-1360`) specifically because those values are known at dequeue time and "the terminal call passes none of these" (comment, `writers.py:1357`); other columns use last-write-wins (`SET x=excluded.x`). Whether `model`/`host`/`ll_version` need COALESCE or last-write-wins depends on which call site(s) first know these values — this determines the UPSERT clause shape for the new columns.
- Schema migration test template concretized: `TestSchemaV38BaseShaColumns` (`test_session_store_schema.py:1902-1967`) is a 5-test class — column-presence via `PRAGMA table_info`, a negative check that a sibling table (`loop_runs`) did *not* gain the columns, an upgrade-from-old-version test (`_bootstrap_schema_at(db, 37)` then `ensure_db()` then assert old rows survive with NULL new columns), plus `test_excluded_from_rebuild`/`test_not_kindless` — this is the exact 5-assertion shape the new migration's test class should mirror.

### Files to Modify
- `scripts/little_loops/issue_history/agent_quality.py` — `analyze_agent_quality()` (line 462) and `format_agent_quality_markdown()` (line 619) are the existing producer/renderer this issue's `detect_quality_regressions()`/`attribute_change()` consume and extend, per the issue's own Call Path.
- `scripts/little_loops/cli/history.py` — `ll-history quality` subcommand (parser line 251, handler line 470) calls `analyze_agent_quality` then `format_agent_quality_{json,yaml,markdown,text}` (487-496); this is the CLI entry point the Call Path terminates at.
- `scripts/little_loops/session_store/schema.py` / `writers.py` — capturing model/host/version stamps (the issue's Dependencies clause: "if `history.db` does not already record them, adding that capture is in scope") requires changes here; see gap below.

### Dependent Files (Callers/Importers)
- Importers of `agent_quality.py`: `scripts/tests/test_issue_history_agent_quality.py:15`, `scripts/little_loops/issue_history/__init__.py:75`.
- Callers of `format_agent_quality_markdown`: `scripts/little_loops/cli/history.py:494` (`main_history`), `scripts/tests/test_issue_history_agent_quality.py:371`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py:71` and `scripts/pyproject.toml:87` — `main_history` import/registration and the `ll-history` CLI entry point; unaffected by the detection logic itself but confirms the one production entry point.
- `record_orchestration_run` production call sites that must thread through new `model`/`host`/`ll_version` params for `RunAttribution` to have anything to join against (per the issue's own Dependencies clause): `scripts/little_loops/issue_manager.py:767,2309`, `scripts/little_loops/parallel/orchestrator.py:1223` (`_record_orchestration_result()`), `scripts/little_loops/parallel/worker_pool.py:1703` (`_record_dequeue_stamp()`), `scripts/little_loops/cli/sprint/run.py:736,928`.
- `record_loop_run_summary`'s sole production caller: `scripts/little_loops/fsm/executor.py:4293` inside `FSMExecutor._finish()` (best-effort, wrapped in `except Exception: pass`).
- `scripts/little_loops/session_store/__init__.py:48-49,152-153,204,206` — re-exports both writers; its docstring's one-line signature summary for each would go stale once new params are added.
- `scripts/little_loops/history_reader/runs.py:79,100-103` — `recent_orchestration_runs()`/`aggregate_orchestration_runs()` hardcode their `SELECT` column lists and `_ORCHESTRATION_GROUP_COLUMNS` map; new columns are invisible through this typed reader path unless added here.
- `scripts/little_loops/history_reader/models.py:151` — `OrchestrationRun` dataclass is positionally/name-matched against the `SELECT` list via `_row_to_dataclass`; needs new fields for `model`/`host`/`ll_version` or they stay unreadable.
- `scripts/little_loops/session_store/schema_manifest.json:265,273,281,1605` — checked-in `orchestration_runs` table/index snapshot; **must be regenerated** after the schema migration (`test_schema_manifest_matches_checked_in_file`, `test_session_store_schema.py:2870`) and the version bump re-asserted (`test_manifest_schema_version_matches_live_schema_version`, line 2887).
- `scripts/little_loops/cli/doctor.py:502` and `scripts/little_loops/cli/artifact/dashboard.py:42` — both import `SCHEMA_VERSION` from `session_store.schema`; unaffected by the value change itself but confirms no hardcoded `47` elsewhere in these files (only the constant is imported).

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

_Wiring pass added by `/ll:wire-issue`:_
- `record_orchestration_run` test call sites that construct the current signature and will need new-param test cases: `scripts/tests/test_fsm_executor.py:13317-13325`, `scripts/tests/test_history_reader_runs.py:23` (`_stamp` helper wrapping the call, reused by two test classes), `scripts/tests/test_issue_history_rework.py:264-271`, `scripts/tests/test_issue_manager.py:5071,5736` (patches the callable), `scripts/tests/test_cli_sprint.py:875` (patches the callable), `scripts/tests/test_sprint_integration.py:1152-1157`, `scripts/tests/test_worker_pool.py:4470,4536`, `scripts/tests/test_orchestrator.py:322-404`. `scripts/tests/test_sprint.py:3159-3176` runs an **AST-based** check asserting every `record_orchestration_run(driver="ll-sprint")` call carries a required stamp — review if new required kwargs are introduced (existing calls use keyword-only optional args, so purely additive params are non-breaking).
- `record_loop_run_summary` test call sites: `scripts/tests/test_history_reader_usage.py:79-85`, `scripts/tests/test_cli_ctx_stats.py:584-590`, `scripts/tests/test_history_reader_events.py:255-256,453-601`, `scripts/tests/test_session_store_queries.py:519-532`, `scripts/tests/test_session_store_lifecycle.py:698-718`, `scripts/tests/test_issue_history_cli.py:1705-1813`, `scripts/tests/test_issue_history_parsing.py:148-155,694-712`, `scripts/tests/test_feat3182_evidence_bundle.py:374-382`. `scripts/tests/test_feat3182_executor_git_facts.py:142-149` patches the callable rather than constructing a real call — only breaks if `FSMExecutor._finish()` stops passing an argument this test asserts on via `mock_record.call_args`.
- Schema migration test template: `TestSchemaV38BaseShaColumns` (`scripts/tests/test_session_store_schema.py:1902-1955`) is the exact prior `orchestration_runs` column-addition precedent (ENH-2866, `base_sha`/`base_dirty`) to model the new migration's test after, including its not-on-unrelated-table check and upgrade-preserves-old-rows check. `SCHEMA_VERSION = 47` is asserted at multiple points in this file (e.g. lines 1884, 1929) — every one needs updating to the new version.
- `classify_verdict()` (`issue_history/_utils.py:57-71`) is the only existing "baseline" mechanism in `issue_history/`, tested only indirectly via `TestFixRate` above — not itself a change-point detector, confirming the issue's own claim that no adaptable statistical utility exists.
- `scripts/little_loops/stats.py::wilson_ci`/`paired_direction`, tested in `scripts/tests/test_stats.py::TestWilsonCI` — the closest general-purpose statistical-test template in the codebase (boundary cases, symmetry check, clamping, ordering invariant, hand-computed known values) for testing `detect_quality_regressions()`'s formula, though it's a confidence-interval utility, not a change-point detector.
- Five existing `detect_*` functions in `issue_history/` (`detect_manual_patterns`, `detect_config_gaps`, `detect_cross_cutting_smells`, `detect_recurring_feedback`, `detect_skill_bypass`) all return a wrapping `*Analysis` dataclass and each has a dedicated test class (see agent findings for exact locations) — `detect_quality_regressions() -> list[RegressionEvent]` departs from this convention; no existing test establishes an assertion-shape precedent for a bare-list-returning `detect_*` (e.g., no convention for what an empty list vs. an empty analysis object should look like as the not-found sentinel).
- `TestHistoryQualitySubcommand` (`scripts/tests/test_cli_history.py:220-271`) — 4 existing tests (`test_quality_text_default_empty_history`, `test_quality_json_format_routes_to_json_formatter`, `test_quality_min_sample_flag_accepted`, `test_quality_help_exits_zero`); a new `--sensitivity` flag follows `--min-sample`'s `add_argument` shape and needs a 5th test mirroring `test_quality_min_sample_flag_accepted`.

### Documentation
- `docs/reference/API.md:2380,2393` — `analyze_agent_quality`/`format_agent_quality_*` entries will need `detect_quality_regressions`/`attribute_change`/`RunAttribution`/`RegressionEvent` added.
- `docs/reference/CLI.md:3162` (`#### ll-history quality`) — will need the new regression-alert output and any new `--sensitivity`-style flag documented.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/HISTORY_SESSION_GUIDE.md` — the schema-version-history table (currently ending `v47 | ENH-3204 | credential_scope_events table`) needs a new row for the `orchestration_runs` migration this issue adds; the `orchestration_runs` table-description row (line 132) needs `model`/`host`/`ll_version` added to its column enumeration; line 485's existing forward-reference to "a downstream regression-detection consumer" should be reconciled once this feature lands.
- `docs/ARCHITECTURE.md` — same schema-version-history table (rows ~659-680) needs the matching new-version row.

## Program Design

### Types

_Revised 2026-09-07 per Design notes → Design review corrections._

- `RunAttribution`: `dimension: Literal["model", "host", "ll_version"]`, `value: str`, `window_share: float`, `baseline_share: float`, `shift: float` (= `window_share - baseline_share`). Named after the composition dimension whose share rose most in the flagged window.
- `RegressionEvent`: `metric: str`, `window: QualityWindow`, `baseline_periods: list[str]`, `baseline_value: float`, `magnitude: float` (relative move in the worse direction), `attribution: RunAttribution | None`; `to_dict()`.
- `QualityRegressionAnalysis`: `events: list[RegressionEvent]`, `sensitivity: float`, `baseline_windows: int`, `skipped_null_period: int`, `notes: tuple[str, ...]`; `to_dict()`. Follows the `detect_* -> *Analysis` convention. **Not** `RegressionAnalysis` — that name is taken by the unrelated bug-fix clustering type in `issue_history/models.py`.
- `WindowComposition`: `period: str`, `orchestrator: str`, `shares: dict[str, dict[str, float]]` (dimension -> value -> share of runs). Built from `issue_sessions -> usage_events.model` / `raw_events.host` and `orchestration_runs.ll_version`.

### Signatures

- `DEFAULT_SENSITIVITY = 0.30`, `DEFAULT_BASELINE_WINDOWS = 3`, `ATTRIBUTION_MIN_SHIFT = 0.25` (module constants, Option A)
- `detect_quality_regressions(analysis: QualityAnalysis, compositions: list[WindowComposition], *, sensitivity: float = DEFAULT_SENSITIVITY, baseline_windows: int = DEFAULT_BASELINE_WINDOWS, min_sample: int = MIN_SAMPLE_SIZE) -> QualityRegressionAnalysis`
- `attribute_change(window: WindowComposition, baseline: list[WindowComposition], *, min_shift: float = ATTRIBUTION_MIN_SHIFT) -> RunAttribution | None`
- `load_window_compositions(conn, issue_window: dict[int, tuple[str, str]]) -> list[WindowComposition]` (reuses the per-issue `(period, orchestrator)` map `analyze_agent_quality()` already builds at `agent_quality.py:510`)

### Call Path

`analyze_agent_quality()` (`little_loops/issue_history/agent_quality.py`) -> `QualityAnalysis` (gains an optional `regressions: QualityRegressionAnalysis | None` field) -> `detect_quality_regressions()` -> all four formatters: `format_agent_quality_markdown()`/`_text()` gain an additive `if analysis.regressions and analysis.regressions.events:` block; `_json()`/`_yaml()` pick it up through `QualityAnalysis.to_dict()`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

Analyzer and pattern-finder agents confirmed no existing statistical detection utility exists in this codebase to adapt, so the following are new decisions rather than reuse of an established gate:

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- Two disagreeing statistical-baseline conventions exist in this codebase, neither of which this issue's detection statistic is obligated to reuse (no existing change-point/z-score utility was found, confirming the issue's own Decision Rules claim), but both are candidate shapes for `DEFAULT_SENSITIVITY`'s meaning:
  - `classify_verdict()` (`issue_history/_utils.py:57-71`, shared by `agent_quality.py`/`rework.py`): a fixed ±20%-relative-to-baseline band, hardcoded as literals, baseline always "the earliest same-orchestrator window" (never a rolling mean). Three-way verdict (`improving`/`stable`/`degrading`) as a bare `str`.
  - `wilson_ci()`/`paired_direction()` (`little_loops/stats.py:14,43`): a Wilson 95% binomial-CI sign test, "inconclusive" whenever the interval straddles 0.5, `Literal[...]` return types. Scoped today to loop-evaluation/harness-rubric reporting (`specs/harness-optimize-rubric-check.py`), never imported by `issue_history/`.
- `model`/`host` columns already exist elsewhere as a co-located attribution pair (`advisor_host`/`advisor_model`/`main_model` on `advisor_consults`, `schema.py:1255-1257`, v45/FEAT-3300) — no existing precedent found for a persisted little-loops-*version* column anywhere; `__version__` (`little_loops/__init__.py:83`) has never been written to `history.db`.

### Decision Rules

- **Detection statistic**: deterministic, LLM-free, computed over `QualityAnalysis.windows` only. No existing change-point/z-score/rolling-baseline statistical utility exists in this codebase (searched repo-wide, no hits) — the fixed ±20%-band `classify_verdict()` baseline convention (`issue_history/_utils.py:57`, shared by `agent_quality.py`/`rework.py`) is the only existing "baseline" mechanism, and it is not itself a change-point detector; this issue's detection logic is new statistical code, not an adaptation of an existing one.
- **Detection statistic (resolved 2026-09-07)**: prior-K-window baseline comparison, not change-point detection — see Design notes → Design review corrections. Per `(metric, orchestrator)` series: baseline = mean of the up-to-`baseline_windows` preceding windows that clear `min_sample`; flag when the current window clears `min_sample` and its relative move in the worse direction (per each metric's existing `higher_is_better`/lower-is-better convention in `classify_verdict`) exceeds `sensitivity`. NULL/empty-period windows are excluded and counted.
- **Sensitivity default (resolved)**: `DEFAULT_SENSITIVITY = 0.30`, deliberately wider than `classify_verdict`'s ±20% band so an alert is rarer and louder than a `degrading` verdict. Tradeoff to document: at `min_sample=5` a fix-rate window of 5 issues moves in 20% steps, so one extra reopen can trip 0.30 — that is why `min_sample` gates both sides of the comparison, and the doc must say lower `sensitivity` = more alerts = more false positives on small windows.
- **Return type (resolved)**: `QualityRegressionAnalysis` wrapper, per the `detect_* -> *Analysis` convention; empty `events` is the not-found sentinel.
- **Attribution dismissal escape hatch**: when no dimension's share shift in the flagged window exceeds `ATTRIBUTION_MIN_SHIFT` versus the baseline windows, `attribute_change()` returns `None` and the report renders "no attributable change" rather than omitting the `RegressionEvent` — a detected drop is always surfaced even without a named cause. Attribution is correlational (a mix shift coinciding with a drop), and the rendered note says so, matching `_STANDARD_NOTES`.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

_Revised 2026-09-07: scope of step 1 narrowed to `ll_version` only; model/host are read through existing joins (see Design notes → Design review corrections)._

1. Schema v48: add `ll_version TEXT` to `orchestration_runs` (`schema.py:540`) and `loop_runs`; `record_orchestration_run()`/`record_loop_run_summary()` (`writers.py:1287,1428`) gain a keyword-only `ll_version: str | None = None` param, defaulting to `little_loops.__version__` inside the writer so call sites need no change; UPSERT uses `COALESCE(excluded.ll_version, ll_version)` per the `base_sha` pattern (`writers.py:1357-1360`). Verified by `python -m pytest scripts/tests/test_session_store_writers.py scripts/tests/test_session_store_schema.py -v`.
2. `load_window_compositions()` in a new sibling module `scripts/little_loops/issue_history/quality_regressions.py` builds per-`(period, orchestrator)` model/host/`ll_version` shares from `issue_sessions -> usage_events.model`, `issue_sessions -> raw_events.host`, and `orchestration_runs.ll_version`, reusing the `issue_window` map `analyze_agent_quality()` already builds (`agent_quality.py:510`).
3. `detect_quality_regressions()` and `attribute_change()` in the same module, per Program Design; `analyze_agent_quality()` calls them and stores the result on the new `QualityAnalysis.regressions` field.
4. All four formatters render the result: additive blocks in `format_agent_quality_markdown()`/`_text()`, `to_dict()` for json/yaml.
5. `--sensitivity` (and `--baseline-windows`) flags on `ll-history quality` with the `is not None` guard (`cli/history.py:484-487`).
6. Tests: injected-drop / no-drop fixture pair per `TestFixRate`; a mixed-model fixture where a drop coincides with a model-share shift asserts the attribution, and one where the mix is unchanged asserts `None`; NULL-`started_at` rows are excluded not bucketed. Verified by `python -m pytest scripts/tests/test_issue_history_agent_quality.py scripts/tests/test_cli_history.py -v`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- ~~Thread the new `model`/`host`/`ll_version` params through every `record_orchestration_run` production call site~~ **Superseded 2026-09-07**: only `ll_version` is added, and the writer defaults it from `little_loops.__version__`, so the call sites at `issue_manager.py:767,2309`, `parallel/orchestrator.py:1223`, `parallel/worker_pool.py:1703`, `cli/sprint/run.py:736,928`, `fsm/executor.py:4293` are unchanged. Keep the `test_sprint.py:3159-3176` AST check in mind: the new kwarg is optional, so it stays non-breaking.
- Extend `history_reader/runs.py`'s `recent_orchestration_runs()`/`aggregate_orchestration_runs()` SELECT column lists (79,100-103) and `history_reader/models.py`'s `OrchestrationRun` dataclass (151) with `ll_version` so it is visible through the typed reader path.
- Regenerate `scripts/little_loops/session_store/schema_manifest.json` after the `orchestration_runs` migration (recipe in `test_session_store_schema.py:2852-2865`); update every `SCHEMA_VERSION == 47` assertion in `test_session_store_schema.py` (e.g. lines 1884, 1929) to the new version.
- `--sensitivity` config convention: **decided** — module-level constant + CLI flag (mirroring `MIN_SAMPLE_SIZE`/`--min-sample`, `cli/history.py:263-270,486`); see Proposed Solution → Decision Rationale. `DEFAULT_SENSITIVITY` lives as a module constant in the detection module, threaded as `detect_quality_regressions(..., sensitivity: float = DEFAULT_SENSITIVITY)`, with a `--sensitivity` CLI flag on `ll-history quality` using the same `is not None` explicit-override guard as `--min-sample` (`cli/history.py:486`).
- Add a `--sensitivity` flag test to `TestHistoryQualitySubcommand` (`test_cli_history.py:220-271`), mirroring `test_quality_min_sample_flag_accepted`.
- Add a v48-equivalent row to `docs/guides/HISTORY_SESSION_GUIDE.md`'s and `docs/ARCHITECTURE.md`'s schema-version-history tables, and update `HISTORY_SESSION_GUIDE.md` line 132's `orchestration_runs` column enumeration.

## Impact

- **Priority**: P0 - Silent quality regressions are the failure mode the whole metric series exists to catch; without detection the series is observed by nobody.
- **Effort**: Medium - a new detection module plus a one-column schema migration (`ll_version`); model/host attribution reads through existing joins (revised 2026-09-07 from Large).
- **Risk**: Low-Medium - the detection pass is read-only and additive, but the `ll_version` column is a schema bump (v48) touching `record_orchestration_run`/`record_loop_run_summary`, the typed reader path, and `schema_manifest.json`; a missed reader-path update leaves the column unreadable, not corrupted.
- **Breaking Change**: No

## Acceptance Criteria

- Detection is deterministic and LLM-free — statistical over recorded values only.
- A fixture corpus with an injected quality drop is detected; a corpus with no drop produces no alert (false-positive check is part of the test, not an afterthought).
- Each detection names the model/host/version whose share of the window's runs shifted most versus the baseline (with both shares shown), or explicitly reports "no attributable change" when no shift exceeds `ATTRIBUTION_MIN_SHIFT`.
- A fixture where a drop coincides with a model-mix shift attributes to that model; a fixture with the same drop and an unchanged mix attributes `None`.
- Rows with NULL `started_at` are excluded from the series and reported as a count, never bucketed into an empty period.
- `ll_version` is recorded on new `orchestration_runs`/`loop_runs` rows without any orchestrator call-site change; existing rows read back with NULL.
- Sensitivity is configurable via `--sensitivity`, with a documented default and its false-positive tradeoff.
- All four output formats (`text`, `markdown`, `json`, `yaml`) carry the regression block.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-07_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 40/100 → LOW

### Outcome Risk Factors
- Broad enumeration across 16+ sites: `orchestration_runs` schema migration, ~7 `record_orchestration_run`/`record_loop_run_summary` call sites needing new-param threading (`issue_manager.py`, `parallel/orchestrator.py`, `parallel/worker_pool.py`, `cli/sprint/run.py`, `fsm/executor.py`), the typed reader path (`history_reader/runs.py`, `models.py`), `schema_manifest.json` regeneration, plus 15+ test files and 4 docs files — the fanout raises the odds of a missed call site or reader-path gap even though each individual site change is small.
- _(Resolved 2026-09-07: both decisions below are now recorded in Program Design → Decision Rules and Proposed Solution → Decision Rationale; the call-site fanout above is also reduced to a single optional writer kwarg.)_ Two architecture-convention decisions are left open at spec time rather than resolved: (1) `detect_quality_regressions() -> list[RegressionEvent]` deliberately departs from the codebase's `detect_*` → `*Analysis`-wrapper convention with no decision recorded; (2) the `--sensitivity` config convention (module-constant + CLI flag vs. `.ll/ll-config.json` schema entry) is explicitly left for the implementer to decide. Resolving both before coding starts would reduce mid-implementation rework and keep the change consistent with the rest of `issue_history/`.
- The core `detect_quality_regressions()`/`attribute_change()` logic is genuinely new statistical code — no existing change-point/z-score/rolling-baseline utility exists anywhere in the codebase to adapt, and `DEFAULT_SENSITIVITY` has no prior value to anchor to.

## Status

**Open** | Created: 2026-09-07 | Priority: P0


## Session Log
- `/ll:refine-issue` - 2026-09-08T02:52:50 - `db8f4456-9d33-4a56-83a5-6fd56728c61f.jsonl`
- `/ll:decide-issue` - 2026-09-08T02:38:37 - `dbbb8e28-65c6-4fbb-8510-be5c16cd4905.jsonl`
- `/ll:refine-issue` - 2026-09-08T02:31:36 - `6cc496d2-f0d1-4efd-a1af-1d7a8f2e9860.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-08T02:29:08 - `68b61242-b6be-4235-b2f6-614f534d7caf.jsonl`
- `/ll:confidence-check` - 2026-09-08T02:15:46 - `79da3fca-fbcb-4530-ac1f-339229369837.jsonl`
- `/ll:confidence-check` - 2026-09-08T02:10:48 - `8a6cd350-cac1-4f1e-a42b-0221ef8ee56a.jsonl`
- `/ll:wire-issue` - 2026-09-08T02:00:49 - `2d920f5a-2d4d-4a14-9303-a5bfb4bae86a.jsonl`
- `/ll:refine-issue` - 2026-09-08T00:56:22 - `c12a8469-1c0e-4551-abdc-a66d5e5d6bda.jsonl`
- `/ll:format-issue` - 2026-09-08T00:08:41 - `fd8050c6-8bbf-4735-ba8f-b83f5f588867.jsonl`

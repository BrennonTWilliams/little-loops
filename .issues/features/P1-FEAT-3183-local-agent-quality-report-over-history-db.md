---
id: 3183
title: Local agent-quality report over history.db
type: FEAT
priority: P0
status: open
testable: true
discovered_date: '2026-08-15'
labels:
- path-a
- observability
- history-db
relates_to:
- FEAT-2867
- FEAT-3182
- FEAT-2315
---

## Summary

Ship a local, screenshot-worthy agent-quality report built from `.ll/history.db`: fix-rate, correction rate, retry inflation, and cost per issue, each **trended over time** rather than reported as a point-in-time total.

## Current Behavior

`.ll/history.db` (`SCHEMA_VERSION = 40`) records issue transitions, loop runs, user corrections,
token/cost usage, and test runs per project. Two commands read parts of it analytically:
`ll-history analyze` (issue-file trends, `--period`/`--compare`) and `ll-history rework`
(reopen/follow-up/touch-back/revert rates). Neither answers whether the *agents* are getting
better: there is no correction-rate trend, no retry-inflation signal, and no cost-per-issue
figure anywhere in the CLI. `usage_events` — real input/output/cache token counts and `cost_usd`,
populated since v20 (ENH-2461) — currently has **no reader at all**.

## Expected Behavior

`ll-history quality` prints a windowed quality report over `.ll/history.db`, sharing
`ll-history rework`'s `(calendar month, orchestrator)` windows so the two read side by side:

```
agent quality — little-loops (by month x orchestrator)

2026-07 / ll-auto        closed 24
  fix-rate           0.79  (stable)
  correction rate    0.31 /session  (degrading vs 2026-05)
  retry inflation    2.4  iterations/run  (stable)
  cost per issue     $1.82  (degrading vs 2026-05)

2026-08 / ll-auto        closed 3
  insufficient history (min sample 5)

> Orchestrator attribution is correlational, not causal.
> Cost is attributed via issue_sessions; multi-issue sessions are split evenly.
```

`--format json|yaml|markdown` emit the same data, each payload carrying the metric-definition
block. `--min-sample N` controls the insufficient-data threshold.

## Motivation

`history.db` already stores tool calls, tokens, corrections, and lifecycle transitions per project. Nothing turns that into an answer to the only question a user actually asks: *are my agents any good, and is that changing?*

A point-in-time total cannot answer it. "You spent 40k tokens on this issue" is trivia; "your fix-rate has dropped 30% since the last model update" is actionable, and it is the shape of analysis that people currently hand-build one session-corpus at a time because no tool produces it.

## Boundary (non-duplication)

_Rewritten after codebase research — the original draft fenced against the wrong issue._

### The real overlap is `ll-history`, not `ll-logs`

**`ll-history rework`** (FEAT-2867, **shipped** — `scripts/little_loops/issue_history/rework.py`) is
already this issue's shape, and is the surface to extend:

- Reads `.ll/history.db` read-only via `_connect_readonly`, no network, no LLM calls
  (`rework.py:1–8` docstring states this explicitly) — AC #1, already satisfied by the pattern.
- Emits a **time series** of `(calendar month, orchestrator)` windows (`ReworkWindow`,
  `rework.py:79`), not a point-in-time total.
- `MIN_SAMPLE_SIZE = 5` (`rework.py:32`) gates each window to `insufficient_history: true`
  instead of a misleading ratio — AC #3, already solved, following the
  `issue_history/debt.py` convention.
- Metric definitions are pinned in code: `quality_adjusted_throughput()` (`rework.py:53`) is a
  named formula and `_STANDARD_NOTES` (`rework.py:42–50`) carries the caveats — the partial
  precedent for AC #4.
- Four renderers (`format_rework_{text,json,markdown,yaml}`, `rework.py:448–540`) — AC #5.

**`ll-history analyze`** already ships trend infrastructure this issue would otherwise rebuild:
`--period weekly|monthly|quarterly` and `--compare N` (last N days vs. previous N days)
(`cli/history.py:82–134`).

**Consequence**: ship as **`ll-history quality`**, a new
`scripts/little_loops/issue_history/agent_quality.py` modeled on `rework.py` — *not* a new
top-level command and *not* a second windowing convention.

### Why not FEAT-2315

FEAT-2315 (`ll-logs summary`, under EPIC-2369) was named as the extension point in the original
draft. It is the wrong foundation on four counts:

1. **Blocked behind a deferred chain.** FEAT-2315 is `status: deferred`, `depends_on: ENH-2317`
   (also deferred), under EPIC-2369 (deferred), alongside FEAT-2316 and ENH-2318 (both deferred).
   This issue is P0; starting there means unblocking four P3 issues first.
2. **No trend machinery to inherit.** FEAT-2315 is explicitly point-in-time — one
   `--window-days N` lookback rendered as a table. This issue's central requirement (a time series
   per metric) is precisely the part FEAT-2315 does not have.
3. **Its refinement is stale.** FEAT-2315's Codebase Research Findings pin `SCHEMA_VERSION = 14`
   and flag an **UNKNOWN — no test-results table**, proposing `cli_events.exit_code` parsing as a
   workaround. The schema is now **40** (`session_store/schema.py:21`) with both `test_run_events`
   and `usage_events` (v20 / ENH-2461: real input/output/cache token counts + `cost_usd`). The
   open decision it asks the implementer to resolve is resolved by the schema.
4. **Wrong home.** `ll-logs` is framed around host session-JSONL and maintainer-catalog telemetry;
   FEAT-2315 itself notes `summary` would be the *first* `ll-logs` subcommand reading
   `history.db`, requiring a doc carve-out in `HISTORY_SESSION_GUIDE.md` (~line 291).

FEAT-2315 remains a genuinely orthogonal *work digest* ("what did I do this week") and is not
superseded by this issue. The two do not compete once this issue lands under `ll-history`.

### Not to be confused with

`issue_history/regressions.py` is **issue-text clustering** (`analyze_regression_clustering`), not
metric-regression detection. AC #4's "downstream regression detection" consumer does not exist
yet — this issue must therefore *establish* the shared definition surface, not import one.

## Metric Data Sources

_Added by wiring pass — all tables verified against `scripts/little_loops/session_store/schema.py`
at `SCHEMA_VERSION = 40`._

| Metric | Source | Notes |
|---|---|---|
| **Fix-rate** | `issue_events` (`issue_id`, `transition`, `ts`) + the reopen/revert signals in `rework.py` | Largely derivable from `analyze_rework()`. Reuse its signals rather than recomputing — and inherit its documented caveat that `issue_events` dedups per `(issue_num, transition)`, so a second done→open→done cycle collapses into the first. |
| **Correction rate** | `user_corrections` (`ts`, `session_id`, `content`, `source`), net of `correction_retirements` (`topic_fingerprint`, `addressed_at`) | `issue_history/evolution.py` (`detect_recurring_feedback`) already queries this pair — reuse, don't re-query. Denominator must be an explicit per-window unit (sessions or closed issues), stated in the metric definition. |
| **Retry inflation** | `loop_runs` (`iterations`, `final_state`, `terminated_by`, `started_at`) | Net-new. `iterations` is the direct retry count; `terminated_by`/`final_state` separate genuine convergence from exhaustion. `subagent_runs` (`status`, `started_at`/`ended_at`) is a secondary signal. |
| **Cost per issue** | `usage_events` (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `cost_usd`, `session_id`) | Net-new. **`usage_events` has no `issue_id`** — join `usage_events.session_id` → the `issue_sessions` view (`schema.py:889`) → `issue_id`. Sessions touching multiple issues need a stated attribution rule (split vs. duplicate vs. drop); pick one and document it. Prefer `cost_usd` when present, fall back to token counts when null. |

**Windowing**: reuse `rework.py`'s `(calendar month, orchestrator)` bucketing via `_month_key()`
(`rework.py:130`) and `_orchestrator_labels()` (`rework.py:186`, reads `orchestration_runs.driver`,
with issues lacking a row falling into the `unattributed` bucket) so the two reports' windows line
up and can be read side by side.

## Integration Map

_Added by wiring pass — based on codebase analysis._

### Files to Create
- `scripts/little_loops/issue_history/agent_quality.py` — modeled structurally on `rework.py`:
  module docstring stating the read-only/no-LLM contract, `MIN_SAMPLE_SIZE`-gated windows,
  `@dataclass` models with `to_dict()`, an `analyze_agent_quality()` entry point, and
  `format_agent_quality_{text,json,markdown,yaml}()`.

### Files to Modify
- `scripts/little_loops/issue_history/_utils.py` (currently 25 lines, only
  `get_issue_content()`) — **extract the shared windowing + min-sample primitives here**
  (`_month_key`, `_add_days`, `_classify_verdict`, `_assign_verdicts`, the
  `insufficient_history` gate) so `rework.py` and `agent_quality.py` consume one definition.
  This is the concrete mechanism for AC #4; without it the two modules fork the convention.
  Refactor `rework.py` to import from `_utils` — behavior-preserving, covered by the existing
  `scripts/tests/test_issue_history_rework.py`.
- `scripts/little_loops/cli/history.py` — add a `quality` subparser (copy the `rework_parser`
  block, lines 198–224: `--format` with `text|json|markdown|yaml`, `--min-sample`) and the
  `if args.command == "quality":` dispatch branch (mirror the `rework` branch, lines 339–372,
  including its `resolve_history_db(project_root / DEFAULT_DB_PATH)` + `find_issues(config,
  status_filter=all_statuses)` preamble). Add usage examples to the epilog beside the existing
  `rework` examples (lines 57–58).
- `scripts/little_loops/issue_history/__init__.py` — export the new models, `analyze_agent_quality`,
  and the four formatters; add them to `__all__` and to the module docstring's `Public exports`
  block (the docstring is the package's documented surface — it lists every existing analyzer).

### Reused (read-only — no changes needed)
- `scripts/little_loops/history_reader.py:_connect_readonly()` — the read-only connect helper
  `rework.py` and `collisions.py` both use; returns `None` on a missing DB, which is the
  empty-database path for AC #3.
- `scripts/little_loops/session_store/` — `DEFAULT_DB_PATH`; the `issue_sessions` view
  (`schema.py:889`) for the session→issue join.
- `scripts/little_loops/issue_history/evolution.py` — `detect_recurring_feedback()` for the
  correction-rate numerator.
- `scripts/little_loops/issue_history/rework.py` — `analyze_rework()` for the fix-rate signals.
- `scripts/little_loops/cli/output.py` — `print_json()`.

### Scope guards
- **Do not add a `quality` state to `.loops/ll-logs-telemetry-digest.yaml`.** That loop is the
  EPIC-1918 *maintainer* dogfooding set over `ll-logs`; this is an interactive `ll-history`
  surface for target-project users.
- **Do not touch `issue_history/regressions.py`** — despite the name, it clusters issue text and
  is unrelated to metric-regression detection.
- **Do not change `analyze_rework()`'s signature or output.** The `_utils` extraction is an
  internal move only; `ll-history rework`'s JSON payload is a consumed contract.

### Tests
- `scripts/tests/test_issue_history_agent_quality.py` (new) — model on
  `scripts/tests/test_issue_history_rework.py`, whose class structure maps directly onto this
  issue's ACs: `TestEmptyAndMissingDb` (line 75) → AC #3's empty case,
  `TestBelowMinimumSample` (line 91) → AC #3's sparse case, `TestFlatHistory` (line 106),
  `TestInjectedRework` (line 124) / `TestInjectedImprovement` (line 216) → trend direction,
  `TestFormatting` (line 286) → AC #5. Reuse its seeding helpers `_close()` (line 40),
  `_stamp_ts()` (line 48), `_reopen()` (line 62); add equivalents that insert `usage_events`,
  `loop_runs`, and `user_corrections` rows.
- `scripts/tests/test_issue_history_rework.py` — must pass **unchanged** after the `_utils`
  extraction; that is the regression gate on the refactor.
- `scripts/tests/test_cli_history.py` / `test_issue_history_cli.py` — add a `ll-history quality`
  dispatch smoke test, and a sibling-subcommand no-regression check (`ll-history rework --help`
  under `pytest.raises(SystemExit)`, asserting exit 0) confirming the new subparser doesn't break
  existing ones.

### Documentation
- `docs/reference/CLI.md` — add a `#### ll-history quality` section immediately after
  `#### ll-history rework` (line 2730), matching its format: flag table, then a prose paragraph
  defining each metric, its window, its insufficient-data threshold, and its caveats. Add
  examples to the `ll-history` example block (~line 2791).
- `docs/reference/API.md` — `## little_loops.issue_history` (line 2240) and the import example
  (line 2413); the `main_history` entry (line 4537) describing the subcommand set.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — **the single documented home required by AC #4.**
  Add a "Quality metric definitions" section covering both `rework` and `quality` metrics, with
  each definition stated once and cited from the CLI.md prose rather than restated.
- `.claude/CLAUDE.md` / `commands/help.md` — neither currently mentions `ll-history` subcommands
  individually (verified), so no change is required; do not add a one-off entry.

## Program Design

Types and signatures, mirroring `rework.py`'s `Signal`/`Window`/`Analysis` triple so both modules
render through the same shape.

**New in `scripts/little_loops/issue_history/_utils.py`** (extracted from `rework.py`):

- `MetricDefinition` — frozen dataclass holding `name`, `unit`, `window`, `denominator`, `threshold`, and `caveats`; the single documented definition emitted into every JSON payload.
- `month_key(ts: str | None) -> str` — calendar-month bucket key; the public rename of `_month_key`.
- `add_days(ts: str, days: int) -> str` — ISO timestamp offset; the public rename of `_add_days`.
- `classify_verdict(rate: float, baseline: float) -> str` — returns `improving`/`stable`/`degrading`; the public rename of `_classify_verdict`.
- `orchestrator_labels(conn: sqlite3.Connection, issue_ids: set[str]) -> dict[str, str]` — maps issue to `orchestration_runs.driver`, defaulting to `unattributed`.

**New in `scripts/little_loops/issue_history/agent_quality.py`:**

- `QualityMetric` — dataclass carrying `name`, `value: float | None`, `sample_size`, `verdict`, `baseline_period`, `insufficient_history: bool`, and `to_dict()`.
- `QualityWindow` — dataclass carrying `period`, `orchestrator`, `closed_count`, `metrics: dict[str, QualityMetric]`, and `to_dict()`.
- `QualityAnalysis` — dataclass carrying `windows: list[QualityWindow]`, `definitions: list[MetricDefinition]`, `min_sample_size`, `notes: tuple[str, ...]`, and `to_dict()`.
- `analyze_agent_quality(issues: list[IssueInfo], *, db: Path | str = DEFAULT_DB_PATH, min_sample: int = MIN_SAMPLE_SIZE) -> QualityAnalysis` — the entry point; returns an empty `QualityAnalysis` when `_connect_readonly()` returns `None`.
- `format_agent_quality_text(analysis: QualityAnalysis) -> str` — human renderer; the other three formatters take and return the same types.

### Call Path

1. `main_history()` — `scripts/little_loops/cli/history.py:16` entry point; parses argv and dispatches on `args.command`.
2. `quality` dispatch branch — `scripts/little_loops/cli/history.py:339` is the `rework` branch to copy, including its `resolve_history_db(project_root / DEFAULT_DB_PATH)` call.
3. `find_issues()` — `scripts/little_loops/issue_parser.py` supplies the `list[IssueInfo]` with `status_filter=all_statuses`, needed for supersession edges.
4. `analyze_agent_quality()` — `scripts/little_loops/issue_history/agent_quality.py` fans out to the four metric collectors.
5. `_connect_readonly()` — `scripts/little_loops/history_reader.py` opens `.ll/history.db`; returns `None` on a missing DB, which short-circuits to the empty analysis.
6. `analyze_rework()` — `scripts/little_loops/issue_history/rework.py:310` supplies the fix-rate signals.
7. `detect_recurring_feedback()` — `scripts/little_loops/issue_history/evolution.py` supplies the correction-rate numerator.
8. `classify_verdict()` — `scripts/little_loops/issue_history/_utils.py` assigns each metric its `improving`/`stable`/`degrading` verdict against the earliest same-orchestrator window.
9. `print()` via the chosen `format_agent_quality_*` renderer, matching the `rework` branch at `scripts/little_loops/cli/history.py:362`.

## Implementation Steps

1. Extract the windowing/min-sample primitives from `rework.py` into `_utils.py`; refactor
   `rework.py` to import them. Confirm `test_issue_history_rework.py` passes unchanged.
2. Define the metric-definition structure (name, window, denominator, threshold, caveats) in
   `_utils.py` so both modules emit it into their JSON payloads — AC #4's "one place."
3. Resolve the two stated attribution decisions and record them in the module docstring:
   the multi-issue session cost split, and the correction-rate denominator.
4. Implement `agent_quality.py`: the four metrics, windowed, each with an
   `insufficient_history` gate.
5. Implement the four renderers; wire the `quality` subparser + dispatch in `cli/history.py`.
6. Tests per the Tests section.
7. Docs per the Documentation section.

## Acceptance Criteria

- One command emits the report from any project's `history.db` with no network access and no LLM call.
  → **`ll-history quality`**, not a new top-level command.
- At least four metrics, each with a time series and an explicit window definition.
  → fix-rate, correction rate, retry inflation, cost per issue; windows shared with
  `ll-history rework` via `_utils`.
- Empty or sparse databases degrade to a clear "insufficient data" state, not a crash and not a
  misleading zero. → missing DB via `_connect_readonly() is None`; sparse via the
  `MIN_SAMPLE_SIZE` gate emitting `insufficient_history: true`.
- Metric definitions are documented in one place and reusable by downstream regression detection.
  → the shared definition structure in `_utils.py`, emitted into every JSON payload and
  documented in `docs/guides/HISTORY_SESSION_GUIDE.md`.
- The output is legible to someone who did not run the loops it describes.
  → four renderers; caveats carried in-band as `rework.py`'s `_STANDARD_NOTES` does.
- `ll-history rework`'s existing output is unchanged by the `_utils` refactor.

## Use Case

A developer returns to a project after a model upgrade and runs `ll-history quality`. The report
shows correction rate up 40% and retry inflation up from 1.6 to 2.4 iterations/run over the last
two months, while raw closed-issue throughput held flat — the regression the throughput number
alone concealed. They pin the prior model without having to hand-assemble a session corpus.

## Impact

- **Priority**: P1 — the first reader of `usage_events`, and the load-bearing input to any future
  quality-regression detection. Not blocking, but nothing else surfaces this data.
- **Effort**: Medium — the windowing/min-sample/rendering scaffolding is inherited from
  `rework.py`; the real work is the `_utils` extraction, the two net-new metrics
  (retry inflation, cost per issue), and the attribution decisions in step 3.
- **Risk**: Low-Medium — the new command is read-only and additive, but the `_utils` extraction
  touches shipped `ll-history rework` behavior. `test_issue_history_rework.py` passing unchanged
  is the gate.
- **Breaking Change**: No.

## Open Decisions

Both must be resolved during implementation (step 3) and recorded in the module docstring:

1. **Multi-issue session cost attribution** — a session touching N issues can split `cost_usd`
   evenly, duplicate the full cost to each, or be dropped from the metric. Even-split is the
   suggested default; whichever is chosen must be stated in-band with the output.
2. **Correction-rate denominator** — per session or per closed issue. Per-session is more stable
   at low issue volume; per-closed-issue is comparable against the other three metrics' windows.

## Status

- [ ] open

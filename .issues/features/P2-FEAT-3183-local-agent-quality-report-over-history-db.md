---
id: 3183
title: Local agent-quality report over history.db
type: FEAT
priority: P2
status: open
parent: EPIC-3214
epic: EPIC-3214
testable: true
discovered_date: '2026-08-15'
labels:
- path-a
- observability
- history-db
depends_on:
- BUG-3236
- ENH-2775
relates_to:
- FEAT-2867
- FEAT-3182
- FEAT-2315
confidence_score: 98
outcome_confidence: 92
score_complexity: 20
score_test_coverage: 24
score_ambiguity: 24
score_change_surface: 24
---

## Summary

Ship a local, screenshot-worthy agent-quality report built from `.ll/history.db`: fix-rate, correction rate, retry inflation, cost per issue, and tokens per issue, each **trended over time** rather than reported as a point-in-time total — and each carrying the coverage of the data behind it, so a trend driven by incomplete instrumentation is distinguishable from a real one.

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

2026-07 / unattributed   closed 41
  fix-rate           0.74  (stable)
  correction rate    0.22 /closed issue  (degrading vs 2026-05)
  cost per issue     $1.44  (no verdict — priced coverage 0.44)
  tokens per issue   612k  (degrading vs 2026-05)

2026-07 / ll-auto        closed 24
  fix-rate           0.79  (stable)
  correction rate    0.31 /closed issue  (degrading vs 2026-05)
  cost per issue     $1.82  (degrading vs 2026-05)
  tokens per issue   748k  (degrading vs 2026-05)

2026-08 / ll-auto        closed 3
  insufficient history (min sample 5)

retry inflation (by month x loop)
  2026-07 / rn-refine        2.4 iterations/run  (stable)
  2026-07 / code-run-gate    1.6 iterations/run  (improving vs 2026-05)

> Orchestrator attribution is correlational, not causal.
> Most issues have no orchestration_runs row and fall into `unattributed`.
> Cost is attributed via issue_sessions; multi-issue sessions are split evenly.
> Cost verdicts are suppressed below 50% priced coverage; tokens per issue is
> unaffected by pricing-table gaps.
> Retry inflation buckets by loop, not orchestrator — loop_runs has no issue_id.
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
   This issue is P1; starting there means unblocking four P3 issues first.
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
at `SCHEMA_VERSION = 41`._

| Metric | Source | Notes |
|---|---|---|
| **Fix-rate** | `issue_events` (`issue_id`, `transition`, `ts`) + the reopen/revert signals in `rework.py` | Formula pinned below (see **Fix-rate definition**). Reuse `analyze_rework()`'s signals rather than recomputing — and inherit its documented caveat that `issue_events` dedups per `(issue_num, transition)`, so a second done→open→done cycle collapses into the first. |
| **Correction rate** | `user_corrections` (`ts`, `session_id`, `content`, `source`), net of `correction_retirements` (`topic_fingerprint`, `addressed_at`) | `issue_history/evolution.py` (`detect_recurring_feedback`) already queries this pair — but see the research finding below: it is not directly reusable. **`user_corrections` has no `issue_id`** — bucketing by orchestrator requires `user_corrections.session_id` → `issue_sessions` → issue → `orchestration_runs.driver`. Denominator is **per closed issue** (decided, see Open Decisions). |
| **Retry inflation** | `loop_runs` (`iterations`, `final_state`, `terminated_by`, `started_at`) | Net-new. `iterations` is the direct retry count; `terminated_by`/`final_state` separate genuine convergence from exhaustion. `subagent_runs` (`status`, `started_at`/`ended_at`) is a secondary signal. **Attribution axis is contested — see Retry-inflation attribution below.** |
| **Cost per issue** | `usage_events` (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `cost_usd`, `session_id`) | Net-new. **`usage_events` has no `issue_id`** — join `usage_events.session_id` → the `issue_sessions` view (`schema.py:889`) → issue. Sessions touching multiple issues split `cost_usd` evenly (decided, see Open Decisions). **`cost_usd` is null for unpriced models and the nulls are not random — see Cost coverage bias below.** |
| **Tokens per issue** | same as cost per issue, summing the four token columns | Companion to cost per issue, added because it is the only always-computable spend signal (no pricing-table dependency). Reported alongside cost, not instead of it. |

### Fix-rate definition (pinned)

`fix_rate = 1 - rework_share`, reusing the term already computed for
`quality_adjusted_throughput()` (`rework.py:53`) so the two reports cannot disagree. This is
deliberately *not* "share of closed issues that never reopened" — that variant counts issues,
this one carries the same weighting `rework` already publishes. The distinction is material and
was previously unstated; it is now the definition emitted in the `MetricDefinition` payload.

Inherited caveat (must appear in-band): `issue_events` dedups per `(issue_num, transition)`, so
repeat done→open→done cycles collapse into one and fix-rate is biased optimistic.

### Cost coverage bias (must be gated, not assumed away)

`usage_events.cost_usd` is written at ingest by `pricing.estimate_cost_usd()`, which returns
`None` for any model absent from `MODEL_PRICING` (`pricing.py:120-122`). Measured on this repo's
`.ll/history.db`: **68,092 of 301,563 rows (22.6%) have a null `cost_usd`**, and the nulls are
concentrated entirely in models missing from the table:

| model | rows | null `cost_usd` |
|---|---|---|
| claude-sonnet-5 | 129,969 | 0 |
| claude-sonnet-4-6 | 65,547 | 0 |
| **MiniMax-M3** | 41,061 | **41,061** |
| claude-opus-4-8 | 31,709 | 0 |
| **claude-opus-5** | 23,084 | **23,084** |
| **deepseek-v4-flash** | 3,663 | **3,663** |
| claude-fable-5 | 4,559 | 0 |
| claude-haiku-4-5-20251001 | 1,687 | 0 |

The current-generation model is the unpriced one. Older windows are fully costed, recent windows
are partially costed, so **cost per issue drifts downward over time from pricing-table coverage
alone** — precisely the artifact this issue's Use Case asks the report to distinguish from a real
regression. The Metric Data Sources draft previously said "fall back to token counts when null";
that does not work, because converting tokens to dollars needs the same missing pricing.

Required handling:

1. Each cost window carries `priced_share` (rows with non-null `cost_usd` ÷ total rows), gated the
   way `rework.py:396` already gates on `LOW_COVERAGE_THRESHOLD = 0.5`. Below threshold, the
   window reports `insufficient_history`-style suppression of the *verdict*, not a silent number.
2. **Tokens per issue** ships as the always-computable companion (no pricing dependency), so a
   spend trend is still readable when pricing coverage is poor.
3. In-band caveat: `cost_usd` is frozen at write time from the then-current pricing table
   (including Sonnet 5's introductory rate, which expires 2026-08-31 — `pricing.py:5-7`), so a
   pricing-table change alone moves the trend.

Adding `claude-opus-5` and a documented unpriced/non-Anthropic path to `MODEL_PRICING` is a
worthwhile prerequisite but is **not** a substitute for the coverage gate — historical rows are
already written with null and are not recomputed.

### Retry-inflation attribution

The Expected Behavior sample (`retry inflation 2.4 iterations/run`) is a per-**run** mean and needs
no join at all. Only the orchestrator axis forces one, and that join is lossy: **280 of 1,038
distinct `loop_runs` are reachable** via `loop_runs.run_id → usage_events.run_id →
issue_sessions.session_id` (27%), because only 40,891 of 301,563 `usage_events` rows carry a
`run_id` (13.5%).

Decision: report retry inflation bucketed by `(calendar month, loop_name)` — outside the
orchestrator axis — so no runs are dropped, and carry the note that this metric's second axis
differs from the other four. The two-hop per-issue attribution is explicitly out of scope; if a
future consumer needs it, it needs the coverage fraction reported alongside.

### Orchestrator bucket skew

`orchestration_runs` holds 363 rows on this repo's DB (`ll-auto` 343, `ll-sprint` 20) against
2,237 distinct issues in `issue_events` — **roughly 84% of issues fall into the `unattributed`
bucket**. The Expected Behavior sample shows only `ll-auto` windows and is therefore not
representative of real output. The text renderer must be designed and tested with `unattributed`
as the dominant bucket, not as an edge case.

**Windowing**: reuse `rework.py`'s `(calendar month, orchestrator)` bucketing via `_month_key()`
(`rework.py:130`) and `_orchestrator_labels()` (`rework.py:186`, reads `orchestration_runs.driver`,
with issues lacking a row falling into the `unattributed` bucket) so the two reports' windows line
up and can be read side by side.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

- **BLOCKER — `issue_sessions.issue_num` does not exist on already-migrated databases. Filed as [[BUG-3236]]; this issue now `depends_on` it.** `schema.py:889-908` (migration index 35 → v36, ENH-2771) redefines the view with an `issue_num` column, and the finding below correctly reports that as the source-of-truth definition. It is not what a live database has. This repo's `.ll/history.db` reports `schema_version = 41` in its `meta` table, yet `sqlite_master` holds the **v16** view — five columns (`issue_id, session_id, jsonl_path, first_message_ts, last_message_ts`), no `issue_num`. `SELECT issue_num FROM issue_sessions` raises `sqlite3.OperationalError: no such column` on it today (verified), and the drift is already breaking shipped readers — `ll-history sessions <ID>`, `issue_effort()`, and `recent_issue_velocity()` all silently return empty against it. Fresh databases and the current upgrade path are both correct, so a fresh-install test will not reproduce it. Every metric in this issue except retry inflation depends on this join, so BUG-3236 gates the feature; until it lands, any code written against `issue_num` must also carry an `issue_id` fallback path.
- **`SCHEMA_VERSION` is 41** (`session_store/schema.py:21`); the tables cited (`usage_events`, `loop_runs`, `user_corrections`, `correction_retirements`, `issue_sessions` view) are unaffected by v41 (ENH-3185, unrelated). The Metric Data Sources header has been corrected to match.
- **`loop_runs` has no `issue_id` column.** Confirmed schema (`session_store/schema.py:557-571`, v23/ENH-2814): `id, run_id (UNIQUE), loop_name, started_at, ended_at, final_state, iterations, terminated_by, error, evaluator_score, diagnostics_path, head_sha, branch, failure_terminal`. Retry inflation per-issue requires a two-hop join not exercised anywhere in the codebase today: `loop_runs.run_id → usage_events.run_id → usage_events.session_id → issue_sessions.session_id → issue_num`. The one existing precedent, `history_reader.waste_attribution()` (`history_reader.py:1010-1049`), only goes one hop (`usage_events JOIN loop_runs ON run_id`, grouped by `loop_name`, never by issue) and its own comment (`history_reader.py:1017-1021`) notes rows with no matching `loop_runs` are dropped by the inner join, not misattributed — the same drop-not-misattribute behavior would need to hold for the two-hop chain.
- **`issue_sessions` view does support the claimed `usage_events.session_id → issue_id` join**, but the correct group key is `issue_num` (stable numeric), not `issue_id` (mutable TEXT on retype — rationale at `schema.py:827-833`, ENH-2771). Current live view definition is v36/ENH-2771 (`schema.py:889-908`; it has been redefined three times — v5, v16, v36 — each `DROP VIEW IF EXISTS` + `CREATE VIEW` supersedes the prior, so v36 is authoritative), exposing `issue_id, issue_num, session_id, jsonl_path, first_message_ts, last_message_ts`.
- **`detect_recurring_feedback()` reuse for the correction-rate numerator is not straightforward** (`issue_history/evolution.py:92-183`): it opens the DB via a separate `_open_db()` helper (`evolution.py:30-47`) that deliberately skips `ensure_db()`'s migration path (docstring at lines 31-36), distinct from `rework.py`'s `_connect_readonly()` (which does call `ensure_db()`, `history_reader.py:422-436`) — combining both in one report means picking one DB-open semantics, not both. Its core query groups by exact `content` string equality over a flat 90-day lookback (`_STALE_DAYS = 90`) with **no calendar-month or orchestrator bucketing at all** — adapting it for a windowed rate means writing new SQL, not calling the existing function. `user_corrections` also has no `issue_id` column (only `session_id`), so it needs the same `user_corrections.session_id → issue_sessions.session_id → issue_id` hop as `loop_runs`. Retirement filtering (`correction_retirements` join) happens as an in-memory Python filter after the SQL query returns (fingerprint computed via `sha256(content[:512])`, `evolution.py:53-55`), not in SQL — would need to run per-window if adapted.
- **`_assign_verdicts()` is hardcoded to the four rework-specific signal names** (`("reopen", "follow_up", "touch_back", "revert")`, `rework.py:298`, via `getattr(w, name)`) — it is not a generic drop-in for a differently-named signal set (fix-rate, correction-rate, retry-inflation, cost-per-issue) without generalizing the signal-name list or duck-typing over a shared signal shape. `_month_key()` (`rework.py:130-131`) and `_classify_verdict()` (`rework.py:276-283`) are pure and cleanly extractable as-is; `_add_days()` (`rework.py:134-139`) depends on the module constant `_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"` (`rework.py:40`), which must move with it.
- `analyze_rework()` requires `issues: list[IssueInfo]` from `find_issues(config, status_filter=all_statuses)` purely to resolve `supersedes:` edges for the reopen signal (`superseded_by()` call, `rework.py:341`) — a second data source (on-disk `.issues/*.md`) beyond `history.db` that any code reusing this pattern inherits, not just a DB connection.
- CLI dispatch resolves the DB path via `resolve_history_db(project_root / DEFAULT_DB_PATH)` (`cli/history.py:339-372`), not the raw `DEFAULT_DB_PATH` constant directly — `analyze_rework`'s own `db: Path | str = DEFAULT_DB_PATH` default is only reached if the CLI didn't override it, which it always does.
- Formatters (`format_rework_text`/`_markdown`, `rework.py:463-540`) use `assert signal.rate is not None` / `assert w.quality_adjusted is not None` (lines 476, 487, 520) as hard invariants gated on `insufficient_history` being checked first — a new formatter modeled on these must replicate the same insufficient-history-branch-before-assert structure or risk `AssertionError` instead of a graceful message.
- `--min-sample`/`--follow-up-days` CLI args default to `None` and fall back to the module constant only at the call site (`args.min_sample or MIN_SAMPLE_SIZE`, `cli/history.py:359`) — an explicit `--min-sample 0` is falsy and silently replaced by `MIN_SAMPLE_SIZE` rather than honored; a `quality` subcommand modeled on this dispatch inherits the same footgun unless it special-cases `0`.

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
- `scripts/little_loops/issue_history/evolution.py` — **reference only, not a call site.** Per the
  research findings, `detect_recurring_feedback()` uses a different DB-open helper, a flat 90-day
  lookback with no month/orchestrator bucketing, and in-memory retirement filtering; the
  correction-rate numerator needs new windowed SQL modeled on it, not a call to it. Reuse its
  `sha256(content[:512])` retirement-fingerprint convention so the two agree on what "retired"
  means.
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
  `loop_runs`, and `user_corrections` rows. Additionally required:
  - `TestCostCoverageGate` — seed a window whose `usage_events` are majority null-`cost_usd`
    (mimicking the `claude-opus-5` rows) and assert the cost metric reports `coverage < 0.5` and
    `verdict is None`, while `tokens per issue` still emits a verdict. This is the regression test
    for the bias described in **Cost coverage bias**; without it the defect is invisible because
    the number still renders.
  - `TestUnattributedDominant` — seed a window where most closed issues have no
    `orchestration_runs` row and assert the text renderer emits a readable `unattributed` block.
  - `TestMinSampleZero` — assert `--min-sample 0` is honored rather than replaced by
    `MIN_SAMPLE_SIZE`.
  - A test that runs against a database seeded at `schema_version >= 36` with the **pre-v36**
    `issue_sessions` view (no `issue_num`) and asserts the report degrades rather than raising
    `sqlite3.OperationalError` — the step-0 hazard. Drop this only if the view repair lands first.
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
  each definition stated once and cited from the CLI.md prose rather than restated. Must also
  document the coverage semantics: what `priced_share` means, why cost verdicts are suppressed
  below `LOW_COVERAGE_THRESHOLD`, and that unpriced models (any model absent from
  `pricing.MODEL_PRICING`) contribute tokens but not dollars.
- `.claude/CLAUDE.md` / `commands/help.md` — neither currently mentions `ll-history` subcommands
  individually (verified), so no change is required; do not add a one-off entry.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

- **Naming collision risk (not a code collision)**: `scripts/little_loops/issue_history/quality.py` already exists — an unrelated analyzer ("test gaps, rejections, manual patterns, config gaps", `quality.py:1`) with no CLI subcommand currently wired to it (`grep add_parser` in `cli/history.py` shows no `"quality"` subparser today). This issue's proposed `agent_quality.py` module name and `ll-history quality` subcommand do not collide with it in code, but the near-identical naming (`quality.py` vs. `agent_quality.py`, both under `issue_history/`) is worth a one-line disambiguation note in the new module's docstring so a future reader doesn't conflate the two.
- **No `issue_history/*.py` module other than `rework.py` defines its dataclasses locally.** Every sibling (`debt.py`, `regressions.py`, `quality.py`, `evolution.py`) imports its `@dataclass` types from the shared `little_loops/issue_history/models.py` instead. `rework.py`'s locally-defined `ReworkSignal`/`ReworkWindow`/`ReworkAnalysis` (with their own `to_dict()` methods, `rework.py:58-127`) are the only ones observed with `to_dict()` at all — `models.py` dataclasses in the excerpts read are plain, without `to_dict()`. `agent_quality.py` following `rework.py`'s pattern (local dataclasses + `to_dict()`) diverges from the majority convention; that divergence is consistent with modeling on `rework.py` specifically (the issue's stated approach) but is not "the" codebase norm.
- **The four `format_*_{text,json,markdown,yaml}` renderers are independently hand-built per module with no shared base.** `rework.py:448-540` and `issue_history/formatting.py:18-576` (the `analyze`/`summary` renderers) each hand-assemble `lines: list[str]` + `"\n".join(lines)` and hand-build markdown pipe tables as string literals. A shared table helper exists — `cli/output.py:299`, `table(headers, rows, max_col_width=40) -> str` — but no `issue_history/*.py` module imports or calls it (confirmed via grep, no matches). Not every subcommand even uses the four-format convention: `collisions.py` has only one text renderer, with its JSON path built ad hoc via `dataclasses.asdict()` + `print_json()` in `cli/history.py:384-396` rather than a dedicated `format_collision_audit_json()`. Two competing CLI flag conventions coexist in `cli/history.py`: `-f/--format {text,json,markdown,yaml}` (used by `analyze`, `rework`) vs. a single `--json`/`-j` boolean via the shared `add_json_arg()` helper (used by `sessions`, `root`, `audit-issue-collisions`, `summary`) — the issue's plan to copy `rework_parser`'s `-f/--format` block is consistent with the `analyze`/`rework` sub-family, not the whole file.
- **`_utils.py` extraction precedent exists and is a clean-cut, no-shim pattern.** `_utils.py` currently holds exactly one helper, `get_issue_content()` (`_utils.py:10-25`), consumed by `debt.py`, `quality.py`, and `regressions.py` via plain top-level import — none of those modules keep a local re-export or compatibility shim. This is the established precedent this issue's planned `rework.py` → `_utils.py` windowing-helper extraction should follow: a clean import cut, verified by the consuming module's existing test suite passing unchanged, not a re-export left behind in `rework.py`.
- **`MIN_SAMPLE_SIZE`'s precedent citation is inaccurate.** `rework.py:32`'s own comment attributes the `MIN_SAMPLE_SIZE`/insufficient-history convention to `issue_history/debt.py`, but `debt.py` has no such named constant — it gates on inline magic numbers instead (`debt.py:209` — `total_count >= 3`; `debt.py:217` — `total_count >= 5`), with no `insufficient_*` boolean field on its output dataclasses. `rework.py` is actually the only existing module with a named `MIN_SAMPLE_SIZE` constant and a boolean `insufficient_history` field pattern — the issue's citation of `debt.py` as convention precedent (in its own Metric Data Sources section) should be read as "the first instance of this shape," not "an established multi-module convention."
- CLI subcommand registration in `cli/history.py` uses **function-local imports** inside `main_history()` (both a broad import at the top listing all format functions, and a second narrower import inside the dispatch branch for constants) — per `scripts/tests/test_cli_history.py:9-11`'s file-level docstring note, this means test mocks must target the source module (`little_loops.issue_history.agent_quality.*`), not `little_loops.cli.history.*`.

## Program Design

Types and signatures, mirroring `rework.py`'s `Signal`/`Window`/`Analysis` triple so both modules
render through the same shape.

**New in `scripts/little_loops/issue_history/_utils.py`** (extracted from `rework.py`):

- `MetricDefinition` — frozen dataclass holding `name`, `unit`, `window`, `denominator`, `formula`, `min_sample`, `verdict_band`, and `caveats`; the single documented definition emitted into every JSON payload. (The draft's single `threshold` field was ambiguous between the min-sample gate and the improving/degrading band — it is split into `min_sample` and `verdict_band`, and `formula` is added so fix-rate's pinned definition travels with the payload.)
- `month_key(ts: str | None) -> str` — calendar-month bucket key; the public rename of `_month_key`.
- `add_days(ts: str, days: int) -> str` — ISO timestamp offset; the public rename of `_add_days`.
- `classify_verdict(rate: float, baseline: float) -> str` — returns `improving`/`stable`/`degrading`; the public rename of `_classify_verdict`.
- `orchestrator_labels(conn: sqlite3.Connection, issue_ids: set[str]) -> dict[str, str]` — maps issue to `orchestration_runs.driver`, defaulting to `unattributed`.

**New in `scripts/little_loops/issue_history/agent_quality.py`:**

- `QualityMetric` — dataclass carrying `name`, `value: float | None`, `sample_size`, `verdict`, `baseline_period`, `insufficient_history: bool`, `coverage: float | None` (the priced/joinable share backing this value; `None` when the metric has no coverage concept), and `to_dict()`. A metric below `LOW_COVERAGE_THRESHOLD` reports its `value` with `verdict = None` rather than suppressing the number.
- `QualityWindow` — dataclass carrying `period`, `orchestrator`, `closed_count`, `metrics: dict[str, QualityMetric]`, and `to_dict()`.
- `RetryWindow` — dataclass carrying `period`, `loop_name`, `run_count`, `mean_iterations`, `verdict`, `insufficient_history: bool`, and `to_dict()`. Separate from `QualityWindow` because retry inflation buckets by loop, not orchestrator (see Retry-inflation attribution).
- `QualityAnalysis` — dataclass carrying `windows: list[QualityWindow]`, `retry_windows: list[RetryWindow]`, `definitions: list[MetricDefinition]`, `min_sample_size`, `notes: tuple[str, ...]`, and `to_dict()`.
- `analyze_agent_quality(issues: list[IssueInfo], *, db: Path | str = DEFAULT_DB_PATH, min_sample: int = MIN_SAMPLE_SIZE) -> QualityAnalysis` — the entry point; returns an empty `QualityAnalysis` when `_connect_readonly()` returns `None`.
- `format_agent_quality_text(analysis: QualityAnalysis) -> str` — human renderer; the other three formatters take and return the same types.

### Call Path

1. `main_history()` — `scripts/little_loops/cli/history.py:16` entry point; parses argv and dispatches on `args.command`.
2. `quality` dispatch branch — `scripts/little_loops/cli/history.py:339` is the `rework` branch to copy, including its `resolve_history_db(project_root / DEFAULT_DB_PATH)` call.
3. `find_issues()` — `scripts/little_loops/issue_parser.py` supplies the `list[IssueInfo]` with `status_filter=all_statuses`, needed for supersession edges.
4. `analyze_agent_quality()` — `scripts/little_loops/issue_history/agent_quality.py` fans out to the five metric collectors (four on the orchestrator axis, retry inflation on the loop axis).
5. `_connect_readonly()` — `scripts/little_loops/history_reader.py` opens `.ll/history.db`; returns `None` on a missing DB, which short-circuits to the empty analysis.
6. `analyze_rework()` — `scripts/little_loops/issue_history/rework.py:310` supplies the fix-rate signals.
7. New windowed correction SQL in `agent_quality.py` — `user_corrections` → `issue_sessions` → issue → `orchestration_runs.driver`, retirement-filtered on the `correction_retirements` fingerprint convention borrowed from `evolution.py` (not a call into it).
8. `classify_verdict()` — `scripts/little_loops/issue_history/_utils.py` assigns each metric its `improving`/`stable`/`degrading` verdict against the earliest same-orchestrator window.
9. `print()` via the chosen `format_agent_quality_*` renderer, matching the `rework` branch at `scripts/little_loops/cli/history.py:362`.

## Implementation Steps

0. **Prerequisite — BUG-3236** (`depends_on`): land the `issue_sessions` view repair, or implement
   every session→issue join with an `issue_id` fallback. Verify against a database already at
   `schema_version >= 36`, not a freshly created one — a fresh DB masks the defect entirely.
1. Extract the windowing/min-sample primitives from `rework.py` into `_utils.py`; refactor
   `rework.py` to import them. Confirm `test_issue_history_rework.py` passes unchanged.
2. Define the metric-definition structure (name, unit, window, denominator, formula, min_sample,
   verdict_band, caveats) in `_utils.py` so both modules emit it into their JSON payloads —
   AC #4's "one place." Fix-rate's pinned formula goes here.
3. Record the resolved attribution decisions in the module docstring: even-split multi-issue cost,
   per-closed-issue correction denominator, loop-bucketed retry inflation.
4. Implement `agent_quality.py`: the five metrics, windowed, each with an `insufficient_history`
   gate, plus the `coverage` field and `LOW_COVERAGE_THRESHOLD` verdict suppression on cost.
5. Implement the four renderers; wire the `quality` subparser + dispatch in `cli/history.py`.
   Use `if args.min_sample is None` rather than `args.min_sample or MIN_SAMPLE_SIZE` — a deliberate
   divergence from the `rework` branch, which silently discards an explicit `--min-sample 0`.
6. Tests per the Tests section.
7. Docs per the Documentation section.

## Acceptance Criteria

- One command emits the report from any project's `history.db` with no network access and no LLM call.
  → **`ll-history quality`**, not a new top-level command.
- At least four metrics, each with a time series and an explicit window definition.
  → fix-rate, correction rate, cost per issue, tokens per issue (shared `(month, orchestrator)`
  windows via `_utils`), plus retry inflation on its own `(month, loop_name)` axis. Each metric's
  formula and denominator are stated in its `MetricDefinition`, not left implicit.
- A metric whose backing data is incomplete reports its coverage and withholds its trend verdict
  rather than publishing a verdict derived from a shifting denominator.
  → `QualityMetric.coverage` + `LOW_COVERAGE_THRESHOLD`; specifically, cost per issue must not
  emit an improving/degrading verdict on a window whose priced share is below 0.5.
- The report is legible when most issues are `unattributed` (~84% on the source repo's DB).
  → the text renderer is tested with `unattributed` as the dominant bucket.
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
  `rework.py`; the real work is the `_utils` extraction, the three net-new metrics
  (retry inflation, cost per issue, tokens per issue), and the coverage-gating machinery.
  Add the `issue_sessions` view repair (step 0) if it is not landed separately first.
- **Risk**: Medium — the new command is read-only and additive, but (a) the `_utils` extraction
  touches shipped `ll-history rework` behavior, gated by `test_issue_history_rework.py` passing
  unchanged, and (b) the session→issue join it depends on is broken on already-migrated databases
  (step 0). The dominant *product* risk is publishing a cost trend that reflects pricing-table
  coverage rather than agent behavior — the coverage gate exists to prevent exactly that.
- **Breaking Change**: No.

## Open Decisions

_Both previously-open decisions are now **resolved**; they remain recorded here and must be
restated in the module docstring._

1. **Multi-issue session cost attribution** — **RESOLVED: split `cost_usd` evenly** across the N
   issues a session touches. Duplicating inflates the project total; dropping silently loses the
   multi-issue sessions, which are the expensive ones. Stated in-band with the output.
2. **Correction-rate denominator** — **RESOLVED: per closed issue.** Per-session was the more
   stable choice at low volume, but `user_corrections` carries only `session_id` while the
   orchestrator label is derived per-issue from `orchestration_runs.issue_id` — a per-session
   denominator would count sessions while its numerator buckets by issue, in the same ratio.
   Per-closed-issue keeps one bucketing key and makes the metric comparable against the others.
   Viability confirmed: 193 of 195 `user_corrections` rows map to an `issue_sessions` row on this
   repo's DB.

Remaining unresolved:

3. **Whether to land the `MODEL_PRICING` gap first.** Adding `claude-opus-5` (and a documented
   unpriced path for non-Anthropic models) improves coverage going forward but does not recompute
   already-written null rows, so the coverage gate is required either way. Sequencing is the only
   question, not necessity.


## Blocks

- ENH-3211

## Status

- [ ] open


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:58 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
- `/ll:confidence-check` - 2026-08-16T06:14:00 - `626afca1-c50f-4d88-96c2-8085727c7eca.jsonl`
- `/ll:refine-issue` - 2026-08-16T06:04:27 - `7c646ce3-f44e-4eef-97cb-1c8c88c8d9d9.jsonl`

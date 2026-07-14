---
id: ENH-2578
title: wire-issue graph-first discovery phase with before/after token measurement
type: ENH
priority: P3
status: blocked
labels: [skills, code-intelligence, token-cost, measurement, captured]
captured_at: "2026-07-10T05:34:41Z"
discovered_date: "2026-07-10"
discovered_by: capture-issue
parent: EPIC-2575
status_note: "Blocked by BUG-2633 — parse_frontmatter drops PyYAML-serialized lists, surfaced while attempting this wiring (run auto-refine-and-implement-20260713T190717)."
depends_on:
- BUG-2633
blocked_by:
- BUG-2633
---

# ENH-2578: wire-issue graph-first discovery phase with before/after token measurement

## Summary

Wire the first skill consumer onto the `ll-code` query surface: `/ll:wire-issue` gains a graph-first discovery step that seeds its Integration Map candidates (callers, importers, impacted tests/config/docs) from one or two `ll-code --json` calls, then spends its remaining budget **confirming** those candidates with targeted Grep instead of discovering them from scratch. Ship with a before/after token/turn measurement on benchmark issues; the measured delta — not assumption — decides whether `/ll:find-dead-code`, `/ll:audit-architecture`, and `/ll:refine-issue --gap-analysis` get the same treatment.

## Current Behavior

`skills/wire-issue/SKILL.md` traces "every file that must change, every caller that may break, every config key, doc section, or test that needs touching" through open-ended Read/Glob/Grep/find exploration (allowed-tools: Read, Glob, Grep, Edit, Bash find/ls/wc/git/ll-issues, Agent). Caller and importer discovery is typically 4–8 grep rounds per planned change, interpreted by the agent, repeated for every issue — including in autodev loops where the codebase facts barely changed between runs. `ll-code` (FEAT-2576/ENH-2577) exists but nothing calls it.

## Expected Behavior

Within wire-issue's tracing phase:

```
# New sub-phase: Graph-accelerated discovery (before manual tracing)
STATUS = Bash: ll-code --json status
if provider unavailable → skip silently; proceed with current flow (zero regression)
else:
    for each planned change target (symbol or file) from the issue's Implementation Steps:
        CANDIDATES += ll-code --json callers-of / importers-of / impact-of
    # Hints, not verdicts:
    confirm each candidate with ONE targeted Grep at its path:line before it enters the Integration Map
    if STATUS.freshness == "stale": treat all candidates as leads only; widen confirmation to current flow for anything wiring-critical
    negative results ("no callers") are NEVER trusted alone → run the current exploratory pass for that target
```

The skill's written output (Integration Map) is format-identical to today — only how candidates are found changes. `--dry-run`/`--auto` behavior unchanged.

## Use Case

`/ll:wire-issue FEAT-XXXX --auto` inside an autodev triage loop: the issue re-signatures `IssueManager.load`. One `ll-code --json callers-of` returns 11 exact call sites; the agent confirms each with a single targeted Grep and finds one new site added since indexing (flagged stale). Integration Map complete in ~3 tool rounds instead of ~10, with the stale drift caught by the confirmation step rather than shipped as a gap.

## Proposed Solution

1. **SKILL.md change** — add the graph-accelerated discovery sub-phase (pseudocode above) to `skills/wire-issue/SKILL.md`'s tracing phase, and `Bash(ll-code:*)` to `allowed-tools`. Encode the three safety rules verbatim: silent fallback when unavailable; confirm-before-map for every positive hit; never trust negative results without an exploratory pass.
2. **Measurement** — define a benchmark set of 3–5 representative closed issues with known-good Integration Maps (e.g., re-run against their pre-implementation commits). Run wire-issue N times per issue across **three** conditions: graph phase disabled (baseline), graph phase enabled with `code_query.provider` forced to `fallback` (grep/AST, no index — the default most projects will actually run), and graph phase enabled with `provider` forced to `codegraph` (SQLite index built ahead of the run). Pull per-run token/turn/tool-call counts from the session history db (`ll-history` / `ll-logs`, EPIC-1918-style telemetry) and report them per-provider, not pooled. Record results in the issue's Session Log and epic.
3. **Decision gate** — write the go/no-go into EPIC-2575, evaluated **separately for each provider** (a codegraph win does not imply a fallback win, since fallback is itself grep-based and may show a smaller or negative delta): material win (target: ≥30% discovery-phase token reduction with zero Integration Map regressions) → file the mechanical follow-ups for find-dead-code / audit-architecture / refine-issue --gap-analysis, scoped to the provider(s) that won; a wash on both providers → close the epic at protocol+provider with no further skill changes; a split result (codegraph wins, fallback doesn't) → ship the phase but document that it only pays off with a codegraph index present.

## Scope Boundaries

- **Not** changes to any other skill — follow-ups are filed only after the measured win.
- **Not** Integration Map format changes — output contract untouched.
- **Not** find-dead-code integration — explicitly deferred: its delete-recommendation semantics make stale negatives dangerous; it goes second only after the confirm-step pattern is proven here.
- **Not** new measurement infrastructure — reuse existing history/logs telemetry; if a counter is missing, capture a separate issue.

## API/Interface

- `skills/wire-issue/SKILL.md`: new sub-phase + `Bash(ll-code:*)` in allowed-tools frontmatter.
- No Python/CLI changes.

## Integration Map

### Files to Create
- Benchmark notes/fixture list (issue IDs + commits) — location per existing eval conventions (e.g., alongside skill or in `specs/`)

### Files to Modify
- `skills/wire-issue/SKILL.md` — allowed-tools + tracing-phase sub-section
- Docs page for wire-issue if phases are documented there
- `EPIC-2575` — record measurement results and go/no-go

### Dependent Files
- Potential follow-up issues for `skills/ll-find-dead-code/`, `skills/ll-audit-architecture/`, `skills/ll-refine-issue/` (filed only on measured win)

### Similar Patterns
- `skills/wire-issue/SKILL.md` existing phase structure and `--auto`/`--dry-run` conventions
- ENH-2569's measurement-first discipline ("land alone, record fire rate") — same land-then-measure-then-route philosophy
- EPIC-1918 (ll-logs as development telemetry) — where the run metrics come from

### Tests
- Skill-lint/doc checks (`ll-verify-skills`, `ll-verify-docs`) stay green
- Manual/benchmark: Integration Map parity check between disabled/fallback/codegraph runs on the benchmark set (no missing entries), token/turn deltas reported per provider

### Documentation
- CHANGELOG; wire-issue docs note the optional acceleration + fallback behavior

### Configuration
- None beyond ENH-2577's `code_query` block (skill respects whatever provider/staleness policy resolves).

## Implementation Steps

1. Add the sub-phase + allowed-tools to wire-issue SKILL.md with the three safety rules.
2. Assemble the benchmark issue set; capture baseline runs (graph phase off).
3. Capture enabled runs; compare tokens/turns/tool-calls and Integration Map parity.
4. Write results + go/no-go into EPIC-2575; file follow-up issues if the gate passes.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-07-12):_

### ll-code CLI contract (verified anchors)

- **CLI**: `scripts/little_loops/cli/code.py::main_code()`. Subcommands: `status`, `callers-of`, `callees-of`, `importers-of`, `defines`, `references`, `impact-of` (`--depth`, default 2).
- **Provider lever for the 3 benchmark arms**: `--provider {auto,codegraph,fallback}`. `_default_provider()` reads `BRConfig(cwd).code_query.provider`. Forcing `--provider fallback` / `--provider codegraph` per-invocation is exactly how the three measurement conditions are pinned — no config edit needed between arms.
- **`--json` envelope**: `{"provider", "freshness", "query", "results": [CodeRef…]}`. `CodeRef` (`codequery/core.py`) fields: `path, line, symbol, kind, confidence ("exact"|"heuristic"), provider`. `ProviderStatus` fields: `available, freshness ("fresh"|"stale"|"unknown"), indexed_at, detail`.
- **Exit-code contract implements the three safety rules directly** (`main_code()` docstring): `0` = hits, `1` = no hits, `2` = provider error / `Unsupported` query kind. So the skill can branch purely on exit code:
  - exit `2` → provider unavailable/unsupported → **silent skip** (safety rule 1)
  - exit `1` → "no callers/importers" negative → **never trust alone; run the exploratory pass** (safety rule 3)
  - exit `0` → hits → **confirm each with one targeted Grep** before it enters the Integration Map (safety rule 2)

### Implementation-critical gap: codegraph does not support `impact-of`

`CodegraphProvider.capabilities()` (`codequery/codegraph.py`) is `{callers_of, callees_of, importers_of, defines, references}` — **no `impact_of`**. `ll-code impact-of … --provider codegraph` raises `Unsupported` → exit 2. Only `FallbackProvider` implements `impact_of` (ast import-graph reverse-BFS). **Consequence for the pseudocode**: the `impact-of` candidate lever must be treated as "provider doesn't support it → skip this lever" (not an error) in the codegraph arm; `callers-of` / `importers-of` / `references` work on both providers and carry the graph-first discovery there.

### Staleness → availability folding (freshness is pre-interpreted)

`CodegraphProvider.status()` folds `code_query.staleness` into the reported `available`/`freshness`: `off` → always `fresh`/available (trusts index); `strict` + drift → `available=False`, `freshness="stale"`; `warn` (default) + drift → `available=True` but `freshness="stale"`. So the issue's "if STATUS.freshness == stale → treat candidates as leads only" reads straight off the JSON `freshness` field, and under `strict` a stale index takes the exit-2 silent-skip path automatically.

### Measurement blocker — per-run TOKEN counts are not queryable today (capture a separate issue)

> ⚠ **SUPERSEDED 2026-07-12** — this blocker is now RESOLVED. ENH-2461 landed
> (commit `02814aa6`, "usage_events consumer + read API for real LLM token
> usage"), shipping the `usage_events` table and a session-filterable read API.
> See "Measurement blocker RESOLVED" below. The historical analysis is kept for
> provenance; the go/no-go dependency chain no longer includes a token-counter
> issue.

The Step-2 plan assumes per-run token/turn/tool-call counts are pullable from `.ll/history.db` via `ll-history`/`ll-logs`. Research finding (2026-07-12, pre-ENH-2461) — **only tool-call/turn counts existed; per-run token counts did not**:

- `.ll/history.db` `tool_events` carries `bytes_in`/`bytes_out`/`cache_hit` (byte-level, not tokens), aggregated DB-wide, not per-run (`session_store.py`).
- The **only** code path reading real per-message token usage is `ctx_stats.py::_compute_cache_rate_from_jsonl()` — hardcoded to the single most-recently-modified JSONL, **not parameterized by `session_id`**.
- The intended per-state `usage_event` table (input/output tokens) is stubbed in `ctx_stats.py::_aggregate_usage_events()` and **blocked on ENH-2461** (not yet merged).
- What *is* available today: `ll-logs diff <a> <b>` → per-tool count deltas; `history_reader.lookup_session_metadata()` → `tool_count`; `ll-history sessions <ID>` → issue→session JSONL mapping.

**Implication** (per this issue's own Scope Boundary "if a counter is missing, capture a separate issue"): the token-delta half of the measurement needs either ENH-2461 to land first, or a small reader that sums `message.usage` tokens for a *named session's* JSONL (generalize `_compute_cache_rate_from_jsonl` to accept a `session_id`). **Recommend**: file that as a blocking dependency issue; meanwhile measure **tool-call and turn deltas** (available today) as the primary signal and report token deltas once the counter lands. ~~This makes ENH-2578 effectively blocked on a token-counter dependency, not just on FEAT-2576/ENH-2577.~~ **← no longer true; ENH-2461 landed 2026-07-12 (see below).**

### Measurement blocker RESOLVED — per-session token counts are queryable now (ENH-2461, 2026-07-12)

_Added by `/ll:refine-issue` — the Step-2 measurement is unblocked. The go/no-go
no longer waits on a token-counter issue._

ENH-2461 (commit `02814aa6`) added a real `usage_events` table (session-store
schema **v20**) plus a public read API. The exact surface an implementer/harness
calls for Step-2 per-provider token deltas:

- **Table** — `usage_events` (`session_store.py`, `_MIGRATIONS` v20; populated by
  `_backfill_usage_events()`). Columns: `ts, session_id, model, state,
  input_tokens, output_tokens, cache_read_input_tokens,
  cache_creation_input_tokens, cost_usd`. Indexed on `session_id` and `model`.
  Derived from each `type=="assistant"` line's `message["usage"]` during
  `ll-session backfill`/`rebuild` (raw_events → cache-table materialization, per
  ENH-2581). Note: `state` is always `NULL` on parser-written rows — the on-disk
  transcript has no FSM-state boundary, so token deltas are **per-session**, not
  per-FSM-state.
- **Public read API** (`history_reader.py`, verified anchors):
  - `aggregate_usage(group_by="session", *, since=None, db=DEFAULT_DB_PATH) -> list[dict]`
    — **this is the direct per-run total**: one row per `session_id` with
    summed `input_tokens`/`output_tokens`/`cache_*`/`cost_usd` and an `events`
    (assistant-turn) count. This is the primary lever for the before/after
    token delta per benchmark arm.
  - `recent_usage_events(session_id=None, model=None, *, since=None, limit=20, db=…) -> list[UsageEvent]`
    — per-call rows filterable by exact `session_id` (the "sum `message.usage`
    for a named session" capability the stale finding said was missing). Returns
    `[]` on any read failure (graceful degradation).
- **CLI surface** — no dedicated `usage`/`tokens` subcommand yet, but `usage` is
  a first-class kind: `ll-session recent --kind usage [--issue <ID>] [--limit N] [--json]`
  (dispatches through `main_session()` in `cli/session.py`; `--issue` filters to
  sessions co-occurring with the issue via `sessions_for_issue()`), and
  `ll-session export --tables usage_event --since <DATE> -o file` dumps the raw
  rows (note the export key is `usage_event`, singular-suffixed, vs. the
  `--kind usage` value — two names, same table). Map issue→session JSONL with
  `ll-history sessions <ID>` to pick the arm's session IDs, then aggregate.
- **`ctx_stats.py::_aggregate_usage_events()` is now a full implementation** (not
  the stub the prior finding cited), but it rolls up **per-model, project-wide**
  — it does *not* group by session. For per-run/per-arm deltas call
  `history_reader.aggregate_usage(group_by="session")` directly, not ctx-stats.

**Net effect on this issue**: the token-delta half of Step-2 is now doable with
existing telemetry. Recommended Step-2 wiring: for each benchmark arm, capture
the wire-issue run's `session_id` (via `ll-history sessions <benchmark-ID>` or the
Session Log line), then
`history_reader.aggregate_usage(group_by="session")` (or `ll-session recent
--kind usage --issue <ID> --json`) for that session's input/output token totals;
report per-provider median deltas in the `ll-loop run --baseline` A/B format (see
Patterns to model → A/B measurement). Tool-call/turn deltas remain available as a
corroborating signal.

### A/B reporting has a reusable writer (not just the --baseline guide)

Beyond the `ll-loop run --baseline` median-delta report format, the actual
serializer is reusable: `ab_writer.py::calculate_ab_summary()` produces an
`ABResults` dataclass (`harness_pass_rate`, `baseline_pass_rate`, `delta`,
`median_tokens_harness/baseline`, `median_duration_harness/baseline`, `per_item`)
and `write_ab_json()`/`ab_results_to_dict()` emit `ab.json` against a draft-07
schema (`_AB_SCHEMA`). Model the per-provider benchmark report on this field set
so the three arms (disabled / fallback / codegraph) report identically. FSM
threads baseline context via `cli/loop/run.py` `fsm.context["_baseline"]`,
consumed in `fsm/executor.py` when a `--baseline` run finishes.

### Patterns to model

- **Silent-fallback shellout**: `skills/wire-issue/static-coupling-layer.md` (loaded as Phase 3.5) is the closest in-repo "hints, not verdicts, skip silently" precedent — `2>/dev/null`, empty-result and absent-tool treated identically, results injected as downstream agent hints. The new graph-discovery sub-phase belongs adjacent to it (a Phase 3.5/3.6 slot **before** Phase 4's parallel wiring agents in `skills/wire-issue/SKILL.md`), and `allowed-tools` gains `Bash(ll-code:*)` following the existing `Bash(ll-<tool>:*)` wildcard convention.
- **A/B measurement reporting**: `ll-loop run <loop> --baseline` (`docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`) is the repo's median-delta format (median tokens/duration/pass-rate + explicit % delta per arm) — report per-provider the same way.
- **Recording the go/no-go**: use the epic-body `## Implementation Status` / `## Success Metrics` strikethrough pattern (EPIC-1918 precedent), not just a Session Log line.

### Config already landed (no config work in this issue)

The `code_query` block is fully wired: `CodeQueryConfig` / `CodeQueryCodegraphConfig` (`config/features.py`), schema in `config-schema.json`, consumed by `_default_provider()` and `CodegraphProvider` (ENH-2612 / ENH-2613 done). The skill respects whatever provider/staleness resolves; no schema or dataclass change is required.

## Impact

- **Priority**: P3 — the payoff step; converts EPIC-2575 from plumbing into measured token savings (EPIC-2456).
- **Effort**: Small-Medium — prompt-only skill change + benchmark runs; no engine code.
- **Risk**: Low — silent fallback preserves today's flow exactly; confirm-before-map bounds stale-index damage.
- **Breaking Change**: No.

## Related Issues

- **EPIC-2575** — parent. **Blocked by FEAT-2576 and ENH-2577** (needs the CLI and a real provider for a meaningful measurement).
- **EPIC-2456** — token cost reduction; report the measured delta there.
- **EPIC-1918** — telemetry source for the measurement.
- **ENH-2461** — ✅ **done** (commit `02814aa6`). Landed the `usage_events` table +
  `history_reader.aggregate_usage(group_by="session")` read API; this **unblocks the
  token-delta half of Step-2**. Previously flagged (in prior refine) as a blocking
  token-counter dependency — no longer outstanding. Depends on ENH-2581 (raw_events
  source-of-truth / `ll-session rebuild`), which also landed.

## Status

**Open** | Created: 2026-07-10 | Priority: P3

## Session Log
- `/ll:refine-issue` - 2026-07-13T04:36:50 - `c34d2f4c-d3a4-4025-bc6a-2b899a5909ba.jsonl`
- `/ll:refine-issue` - 2026-07-12T23:55:22 - `c0410b59-a59a-410c-8b5c-9ba8ced794b2.jsonl`

- `/ll:capture-issue` - 2026-07-10T05:34:41Z - `manual capture via Claude Cowork session (EPIC-2575 design discussion)`

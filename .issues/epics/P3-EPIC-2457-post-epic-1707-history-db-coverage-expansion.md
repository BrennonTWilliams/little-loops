---
id: EPIC-2457
title: Post-EPIC-1707 history.db coverage expansion
type: EPIC
priority: P3
status: open
discovered_date: 2026-07-02
captured_at: "2026-07-02T00:00:00Z"
discovered_by: capture-issue
relates_to: [ENH-2458, ENH-2459, ENH-2460, ENH-2461, ENH-2462, ENH-2463, ENH-2464, ENH-2465, ENH-2466, ENH-2492, ENH-2493, ENH-2494, ENH-2495, ENH-2496, ENH-2497, ENH-2498, ENH-2504, ENH-2505, ENH-2506, ENH-2507, ENH-2508, ENH-2509, ENH-2510, ENH-2511, ENH-2512]
labels:
  - epic
  - history-db
  - captured
---

# EPIC-2457: Post-EPIC-1707 history.db coverage expansion

## Summary

After EPIC-1707 (history.db as Agent Context Layer — done 2026-06-12) closed, the 6 event tables (`tool_events`, `file_events`, `issue_events`, `loop_events`, `message_events`, `user_corrections`) plus FTS5 `search_index`, plus the producer/consumer wiring cover the *runtime* signal surface. Nine additional coverage gaps remained, surfaced by the findings report at `thoughts/history-db-expand-wiring.md`: commit metadata, test run results, skill success signals, real LLM token counts, explicit `session_id` on `issue_events`, per-loop-run summary rows, decisions backlinks, epic progress snapshots, and learning test rows in the DB. Each is independently scoped (per the source doc's own framing: *"no single mechanism unifies them"*), but they share a single underlying substrate (`.ll/history.db`) and a common consumer story (extend what agents can query). This epic tracks the rollup; each child owns its own scope.

## Goal

When this epic is done, `.ll/history.db` persists the nine additional signal classes listed in `thoughts/history-db-expand-wiring.md` §3 (commit linkage, test results, skill success signal, real token counts, explicit `session_id`, per-loop-run summary rows, decisions backlinks, epic progress snapshots, learning test rows), each discoverable via `ll-session search --fts` and queryable via `ll-session recent --kind <new_kind>`.

## Motivation

The findings report (see `## Sources`) inventories what history.db captures today versus what it doesn't. The nine gaps are not coordination-coupled — they don't share state and don't depend on each other — but they share enough surface that capturing them under one EPIC makes their progression visible (velocity, blocking patterns, scope drift) without forcing artificial implementation coupling.

### Why this is a post-1707 epic and not standalone enhancements

- **Provenance**: All nine items were identified as residual gaps immediately after the EPIC-1707 closure review. Capturing them now preserves the lineage from "what 1707 covered" to "what still needed covering."
- **Discoverability**: A future contributor looking at history.db coverage will land on this EPIC via `relates_to:` and read the children's scope in one place.
- **Acceptance of partial scope creep**: Children may complete in any order, may be cancelled without blocking the others, and may gain additional siblings over time. The epic's closure criterion is "all children done OR explicitly deferred" rather than a coordinated release (originally 9 children; 16 as of the 2026-07-05 expansions).

### Out-of-scope (will not be added under this EPIC)

- Schema rewrites or breakable changes to existing tables.
- Cross-project / global history aggregation.
- Real-time sync to external systems (GitHub, Linear) — separate EPIC territory.
- Dashboard / UI surface — separate effort.
- Anything that violates the EPIC-1707 graceful-degradation contract (writes must not block their caller; reads must not raise on missing/empty DB).

## Scope

### In scope

- Nine children, each a discrete enhancement to `.ll/history.db` write or read surface.
- Each child owns its own schema migration, producer wiring, read API addition, CLI flag (where applicable), tests, docs.
- All children follow the EPIC-1707 producer/consumer contracts: writes are best-effort and `contextlib.suppress(Exception)`-guarded; reads degrade gracefully when DB is absent/empty.

### Out of scope

- Coordinated cross-child work — no shared helper module is required.
- EPIC's own implementation status file — each child owns its own.
- Schema bump coordination — each child may add a migration; `SCHEMA_VERSION` bumps per child as needed.
- Test framework changes — each child uses the existing test patterns from its nearest neighbor.

## Children

- **ENH-2458** — Capture git commit metadata (hash, message, author, branch, touched-files list) into a new `commit_events` table at commit time; link to issue_id via message/branch parsing. *(P2 — doc ranked #1 by value)*
- **ENH-2459** — Capture pytest run results (pass/fail counts, duration, failing test names) into a new `test_run_events` table by wrapping test invocations. *(P2 — doc ranked #2; only CI gate, currently unrecorded)*
- **ENH-2460** — Add `exit_code`, `success`, and `duration_ms` columns to `skill_events` so skills carry the same success signal that `cli_events` already carries via ENH-1834. *(P3 — doc ranked #3; cheap, hook-side addition)*
- **ENH-2461** — Persist actual LLM API token usage (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`) into `tool_events` (or a new `usage_events` table) so cost analysis doesn't require re-parsing JSONL every time. *(P3 — doc ranked #4)*
- **ENH-2462** — Add explicit `session_id` column to `issue_events` and replace the inferred `issue_sessions` view with an authoritative column captured at transition time. *(P3 — doc ranked #5; removes false-positive/negative joins)*
- **ENH-2463** — Add a per-loop-run summary row (final state, iteration count, evaluator score, diagnosis artifact path) to a new `loop_runs` table so loop health is queryable without replaying the event stream. *(P3 — doc ranked #6)*
- **ENH-2464** — Add `source_session_id` / `source_issue_id` backlinks to `.ll/decisions.yaml` entries so every `decision` can be traced to the session and issue that produced it. *(P3 — doc ranked #7)*
- **ENH-2465** — Periodic epic-progress snapshots into `.ll/history.db` so EPIC velocity is reconstructable historically instead of being a fresh point-in-time computation. *(P3 — doc ranked #8)*
- **ENH-2466** — Mirror Learning Test Registry records into `.ll/history.db` (or at least index them into `search_index`) so `ll-session search` discovers them alongside everything else. *(P3 — doc ranked #9)*

### Post-closure-review expansion (added 2026-07-05)

A review of history.db coverage on 2026-07-05 (after ENH-2458/2459/2460/2462
landed) surfaced six additional uncaptured signal classes. Per this EPIC's own
"may gain additional siblings over time" clause, they are added as children
rather than a new EPIC. Each is independently scoped and follows the same
graceful-degradation contract:

- **ENH-2492** — Capture per-issue orchestration run outcomes (`ll-auto` /
  `ll-parallel` / `ll-sprint`) into an `orchestration_runs` table; today each
  batch lands as one coarse `cli_event`. *(P2 — highest-value new sibling;
  Python-orchestration analog of ENH-2458/2459, distinct from ENH-2463's FSM
  `loop_runs`.)*
- **ENH-2493** — Persist `ll-harness` / DSL-eval structured outcomes (runner,
  target, semantic verdict, pass/fail, timeout) into a `harness_events` table;
  today only the exit code survives. *(P3)*
- **ENH-2494** — Capture the non-pytest CI gates (`ruff`, `mypy`,
  `ruff format --check`) into a `check_events` table, generalizing ENH-2459's
  pytest-only `test_run_events`. *(P3)*
- **ENH-2495** — Record session-lifecycle / handoff events (`handoff_needed`,
  `compaction`, `stale_ref_sweep`, `session_end`) into a
  `session_lifecycle_events` table; today only `post-tool-use` writes to the DB
  and these hooks emit sentinel/advisory only. *(P3)*
- **ENH-2496** — Config-change audit trail: hash-gated `config_snapshots` of the
  merged `.ll/ll-config.json` at `session_start` so runs are attributable to a
  known configuration. *(P3)*
- **ENH-2497** — Discriminate sub-agent / `Task` spawns via an `agent_type`
  column on `tool_events` so subagent usage is queryable (agent analog of
  ENH-2460's skill success signal). *(P3)*

Item #5 from the review (PR / release / GitHub-sync events) was considered and
**not** captured under this EPIC — it overlaps the "real-time sync to external
systems" out-of-scope line and is better tracked separately if pursued.

### Second-pass expansion (added 2026-07-05)

A follow-up producer-surface sweep on 2026-07-05 (after the first six siblings
landed as issues) checked every hook and CLI that emits a signal against the
15 existing children. All confirmed §2 gaps and the six expansion items were
already covered; one genuinely-uncaptured producer remained, added here. A
second finding — the `ll-verify-*` / `ll-check-links` / `ll-deps validate` gate
family — was folded into **ENH-2494** as a scope widening (same `check_events`
table, no new child) rather than a new sibling.

- **ENH-2498** — Capture prompt-optimization outcomes (offer mode, bypass
  reason, raw/optimized length, accepted heuristic) from the `UserPromptSubmit`
  optimize hook into a `prompt_opt_events` table; live offer-row + JSONL
  backfill for the outcome. Today the one hook that mutates user intent leaves
  no trace, so the feature is unmeasured. *(P3)*

### Third-pass expansion (added 2026-07-06)

A second-pass producer-surface sweep on 2026-07-06, prompted by the
`autodev-bug2501-kill-analysis` (2026-07-07) — which found that the
post-tool-use / context-monitor / session-store-trace mechanics had
several uncaptured producer sites that materially hampered debugging —
surfaced nine additional gaps. Per this EPIC's "may gain additional
siblings over time" clause, they are added as children rather than a
new EPIC:

- **ENH-2504** — Persist verification / readiness-review verdicts
  (`ll-ready-issue`, `ll-confidence-check`, `ll-tradeoff-review`,
  `ll-go-no-go`, `ll-refine-issue`, `ll-format-issue`,
  `ll-verify-issues`, `ll-prioritize-issues`, `ll-align-issues`,
  `/ll:verify-issue-loop`) into a `verdict_events` table. Adjacent to
  ENH-2493 but for the *read-side verifiers* rather than executors.
  *(P3 — paired with ENH-2493 as the third leg of the read-side
  stool.)*
- **ENH-2505** — Link subagent session-tree (parent→child) into a
  `subagent_runs` table (`parent_session_id`, `child_session_id`,
  `agent_type`, `started_at`, `ended_at`). ENH-2497 captures
  `agent_type` on `tool_events` but doesn't link the spawned session
  back to its parent — this issue closes the join. *(P3 — enables
  "which parent sessions burn budget on subagent retries".)*
- **ENH-2506** — Capture hook execution telemetry (event_name,
  matcher, script, exit_code, duration_ms, stderr_preview) into a
  `hook_events` table. The hook dispatcher wraps every handler in a
  `try/except Exception: return LLHookResult(exit_code=0)`; this
  issue persists the fires that the wrapper currently swallows.
  *(P3 — most "the hook didn't fire" debug threads start with no
  data.)*
- **ENH-2507** — Persist context-window pressure measurements (50 / 75
  / 90 / 100% crossings from `context-monitor.sh`) into a
  `context_pressure_events` table. Pairs with `tool_events.bytes_in/
  out/cache_hit` as the missing end-of-pipeline signal. *(P3 — cheap,
  ~one row per PostToolUse fire.)*
- **ENH-2508** — Link commits to git tags and release versions: two
  nullable columns (`tag TEXT`, `release_version TEXT`) on
  `commit_events`, backfilled from `git tag --points-at <sha>`. Widens
  ENH-2458. Lets `ll-session search` find "everything touched by
  v0.4.2." *(P3 — trivial additive column.)*
- **ENH-2509** — Capture worktree lifecycle events
  (`worktree_create` / `worktree_merge` / `worktree_delete`) into
  `session_lifecycle_events`. Widens ENH-2495 with three new event
  discriminators rather than a new child. *(P3 — very low effort as
  a fold into ENH-2495.)*
- **ENH-2510** — Persist `ll-history-context` query telemetry
  (queried_kind, queried_id, result_tokens, hit_rate) into a
  `context_query_events` table. Pairs naturally with `ll-ctx-stats`
  for cost analysis — together they answer "is the history-context
  fetcher a meaningful slice of session spend." *(P3 — enables
  data-driven tuning of `history.compaction.budget_tokens`.)*
- **ENH-2511** — Capture MCP tool-call telemetry
  (`mcp_server`, `mcp_tool`, `mcp_outcome`, `latency_ms`) on
  `tool_events`. Widens ENH-2497's v19 migration with four additive
  columns instead of a separate table. *(P3 — same migration target
  as ENH-2497; coordinate as a single batch.)*
- **ENH-2512** — Persist read-side audit / review outcomes
  (`/ll:review-epic`, `/ll:review-sprint`, `/ll:review-loop`,
  `/ll:audit-architecture`, `/ll:audit-claude-config`,
  `/ll:audit-docs`, `/ll:audit-loop-run`) into a `review_events`
  table with `severity_counts` + `findings_json_summary`. Adjacent to
  ENH-2493 but for opinion-bearing audits rather than harness
  evaluators. *(P3 — backs velocity-tracking questions like "how
  many P0 review findings closed this week?".)*

## Children (filled post-write by `/ll:capture-issue`)

_See `## Children` section above. File system source: this EPIC and 25 child ENH
files (9 original + 6 from the 2026-07-05 first-pass expansion + ENH-2498 from
the 2026-07-05 second-pass expansion + 9 from the 2026-07-06 third-pass
expansion)._

## Integration Map

### No files to modify at the EPIC level

This EPIC owns no shared infrastructure. Each child issue is a self-contained enhancement with its own schema migration and producer/consumer wiring, following the EPIC-1707 precedents (each with a graceful-degradation guarantee and `contextlib.suppress(Exception)` write-guard).

### Sequencing

There are **no hard dependencies** between children. Recommended implementation order, mirroring the doc's rank ordering (highest-value first):

1. ENH-2458 (commit linkage) — P2, biggest blind spot — **done 2026-07-03 (schema v17)**
2. ENH-2459 (test results) — P2, only CI gate without history — **done 2026-07-03 (schema v18)**
3. ENH-2460 (skill success signal) — P3, cheap — **done 2026-07-03 (schema v15)**
4. ENH-2461 (real token counts) — P3
5. ENH-2462 (session_id on issue_events) — P3 — **done 2026-07-03 (schema v16)**
6. ENH-2463 (per-loop-run summary) — P3
7. ENH-2464 (decisions backlinks) — P3
8. ENH-2465 (epic progress snapshots) — P3
9. ENH-2466 (learning test rows) — P3

Children may be implemented in any order; the P2 pair landed first as recommended. Among the 2026-07-05 siblings (ENH-2492…2498), land ENH-2492 (P2, orchestration run outcomes) before the P3s.

## Impact

- **Priority**: P3 — Rollup epic for twenty-five independent enhancements (9 original + 7 added 2026-07-05 + 9 added 2026-07-06); no coordinated release pressure.
- **Effort**: Variable, per child. Sum across children: estimated Medium-Large (six small per-child slices + three medium ones based on doc's own complexity signal).
- **Risk**: Low per child; cumulative risk is "schema sprawl" if children land uncoordinated — mitigated by each child adding at most one migration per the EPIC-1707 graceful-degradation contract.
- **Breaking Change**: No — every child is additive; no existing tables modified beyond optional additive columns and indexes.

## Success Metrics

- All 25 children reach `status: done` (or are explicitly cancelled/deferred with rationale). _Progress as of 2026-07-06: 4 done (ENH-2458, ENH-2459, ENH-2460, ENH-2462), 21 open._
- `ll-session search --fts` returns results across the new kinds (`commit`, `test_run`, `loop_run`, `learning_test`).
- A new contributor can ask `ll-session recent --kind commit` and see a real row, proving schema migration landed.
- The findings report's "Source" section becomes a historical record of *what was missing* — re-running the report's inventory should show zero items in §2.

## Dependencies / Sequencing

- **Soft prerequisite**: EPIC-1707 must be `done` — confirmed in the in-scope check above (EPIC-1707 closed 2026-06-12).
- **No inter-child hard dependencies.** ENH-2462 (explicit session_id on issue_events) may benefit from ENH-1752 (history_reader read API), but neither blocks the other.
- **Soft blocker for ENH-2459**: A `pytest` subprocess wrapper or shell wrapper at the right point in the run flow. The project uses `python -m pytest scripts/tests/` as its sole CI gate per `.claude/CLAUDE.md` § Testing & CI Policy.
- **Soft blocker for ENH-2458**: A `git commit` wrapper or `post-commit` hook registration point — see `ll-commit` skill (`skills/commit/`).

## Verification Notes

_Added 2026-07-02 at capture time:_ EPIC is open with all 9 children listed in `## Children` and `relates_to` frontmatter. No verification pass has been run yet; verification will land alongside each child's implementation.

_Audit 2026-07-06:_ 16 children in `relates_to` match the 16 child files on disk (all carry `parent: EPIC-2457`). 4 done / 12 open. Done children verified against code: `commit_events` (v17), `test_run_events` (v18), `skill_events` completion columns (v15), `issue_events.session_id` (v16) all present in `session_store.py`; `SCHEMA_VERSION` is 18 and `_VALID_KINDS` includes `commit` and `test_run`. Success-metric kinds `loop_run` and `learning_test` remain pending (ENH-2463, ENH-2466).

## Sources

- `thoughts/history-db-expand-wiring.md` — the source findings report this epic is derived from
- `scripts/little_loops/session_store.py` — schema v14 at capture time (v18 as of 2026-07-06), write paths, FTS5 index
- `scripts/little_loops/history_reader.py` — read API from ENH-1752
- EPIC-1707 — closed parent epic; 34 children all done; this epic captures the post-closure gaps

## Status

**Open** | Created: 2026-07-02 | Priority: P3

## Session Log
- audit - 2026-07-06 - Reconciled child counts (9 → 25) in closure criterion, Children note, Success Metrics, and Impact; marked done children in Sequencing; added 2026-07-06 verification-notes entry (4 done / 21 open, schema v18 verified in code).
- third-pass expansion - 2026-07-06 - Added 9 children (ENH-2504..ENH-2512) following the autodev-bug2501-kill-analysis prompt: `verdict_events` (read-side verifier signals), `subagent_runs` (parent→child session linkage), `hook_events` (per-fire telemetry), `context_pressure_events` (PostToolUse pressure curve), `commit→tag` linkage on `commit_events`, worktree lifecycle widening of `session_lifecycle_events`, `context_query_events` (history-context fetcher cost), MCP tool-call telemetry on `tool_events`, and `review_events` (audit/review verdicts). Item sources: the user-reported gap list (2026-07-06); several fold into existing children (ENH-2495, ENH-2497, ENH-2458) as scope-widening.
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`

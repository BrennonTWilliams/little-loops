---
id: ENH-3528
title: Read the host's authoritative token counts where exposed; estimate only where they are not
type: ENH
priority: P0
status: open
discovered_date: '2026-09-23'
labels:
- observability
- multi-host
---

# Read the host's authoritative token counts where exposed; estimate only where they are not

## Summary

An estimated token count presented in the same column, same units, and same formatting as a measured one is an accuracy claim the project does not actually hold — and token-cost is the metric this project leads with. Model measured-vs-estimated as a per-host capability rather than an implementation detail, and surface it. Where a host exposes its own authoritative token counts, read them and delete the estimator on that path. Where it does not, keep estimating and label the number as an estimate wherever it is rendered or exported. Two hosts with two strategies and no forced uniformity is the correct outcome; a single blended number that is sometimes measured and sometimes guessed is not.

## Current Behavior

`ll-ctx-stats` (`little_loops.cli.ctx_stats`) renders token figures without distinguishing measured from estimated. The `.ll/ll-context-state.json` fallback path (`_render_fallback`) prints "Estimated tokens in context" from `estimated_tokens`, and the context-pressure render is documented as "rough by design", yet both share units and formatting with figures read from host logs. `HostCapabilities` (`little_loops.host_runner`) and `HostCapabilityEntry` (`little_loops.adapters.capabilities`) carry no field describing how a host's token counts are obtained, so any measured-vs-estimated decision would have to be branched at call sites.

## Expected Behavior

Each host declares its token-count strategy (`measured` or `estimated`) in the host capability map. `ll-ctx-stats` text and JSON output label every estimated figure as an estimate and carry a per-figure `source`. Hosts that publish authoritative counts have those counts read on the log-ingestion path, with the estimator removed from that path; hosts without them keep estimating, labeled.

## Scope Boundaries

- **In scope**: capability-map field for token-count source; estimate labeling in `ll-ctx-stats` render and JSON export; reading authoritative counts for one host that exposes them; recording `source` alongside stored figures.
- **Out of scope**: improving estimator accuracy; forcing a uniform strategy across hosts; adding token counting for hosts with no log-ingestion seam; changing non-token metrics.

## Design

The capability belongs in the host capability map, not in an ad-hoc branch at each call site. It splits into two independently shippable halves, and the cheap one should not wait on the expensive one:

- **Labeling** (self-contained, no new ingestion required): mark estimated figures as estimates in `ll-ctx-stats` output and in anything that exports them. This removes the false precision immediately.
- **Reading authoritative counts** (lands on the host log-ingestion seam): parse a host that publishes its own token counts, prefer those over the estimator on that path, and record the measured/estimated source alongside the figure.

Where a host exposes authoritative counts, the estimator on that path is deleted rather than bypassed, so the two strategies stay visibly distinct.

## Acceptance Criteria

- [ ] `ll-ctx-stats` output labels estimated token figures as estimates, in every render and export path.
- [ ] The measured-vs-estimated strategy is modelled as a per-host capability in the host capability map, not branched per call site.
- [ ] For a host that exposes authoritative token counts, its counts are read and the estimator on that path is deleted.
- [ ] For a host that exposes no counts, estimation is kept and the figures remain labeled as estimates.
- [ ] Every rendered or exported token figure carries (or is traceable to) its source: measured or estimated.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-23 — based on codebase analysis:_

**Files to Modify (ground truth, not a prescription)**
- `scripts/little_loops/cli/ctx_stats.py` — `main_ctx_stats` (:790) orchestrates `_aggregate_tool_events`, `_aggregate_skill_stats`, `_compute_cache_rate_from_jsonl`, `_aggregate_usage_events` (:211, signature takes only `db_path`), `_aggregate_mcp_health`, `_aggregate_waste`, `_aggregate_context_pressure`, and `_render_fallback` (:592) only when there is no SQLite summary (or its token total is 0).
- `scripts/little_loops/adapters/capabilities.py` — `HostCapabilityEntry` (:58, frozen, defaulted trailing fields, 6 hosts, no opencode/pi) and `host_runner.RUNTIME_HOST_CAPABILITIES` (:523, 8 hosts) are two disjoint maps. Which one owns `token_source` is undecided by any existing convention; the issue's Program Design names `HOST_CAPABILITIES`, which cannot describe opencode/pi.
- `scripts/little_loops/session_store/schema.py` / `writers.py` — `usage_events` (v20; v21 adds `invocation_id`, `provider_vendor`; v29 adds `run_id`; `SCHEMA_VERSION` = 52) has no `source`/provenance column and no host column. Writers: `record_usage_event` (live, from `FSMExecutor._finish`, gated on `analytics_capture.usage_events`) and `_backfill_usage_events` (transcript-derived; only `type == assistant` records with `message.usage`).

**Current behavior (corrects/refines the issue's Current Behavior)**
- The fallback text path already labels its headline figure as estimated, and its JSON key is `estimated_tokens`; the unlabeled cases are elsewhere: `usage_by_model` (JSON only, measured), waste `tokens_wasted/tokens_total` (measured, from `usage_events JOIN loop_runs`), the context-pressure curve (percentages derived from the estimator; the stored column is `used_tokens_est` but `ctx_stats` reads `used_pct`), and the time-gained line (`saved / 100.0`, an in-code heuristic). The cache-rate line is measured host-log data and already appends a `[host]` suffix for non-claude-code hosts.
- `_print_json` already emits a top-level `source` key with values `sqlite | fallback | none` meaning data store, not measured-vs-estimated. The issue's "JSON gains a `source` key" collides with it at the top level; the ENH-3429 precedent avoided the same collision by naming the field `cache_rate_host` rather than `host`.
- The estimator is `hooks/scripts/context-monitor.sh` (registered in `hooks/hooks.json`, Claude Code PostToolUse only; no adapter wires it). `estimated_tokens` is already a blend: measured `result_token_count` (written by `issue_manager._on_usage_writer` from the stream `result` event) wins, else the transcript baseline (`message.usage` of the last assistant record) plus per-tool heuristic, else running heuristic. The state file does not record which branch produced the value. Deleting "the estimator on that path" is therefore not a clean removal on claude-code: the heuristic is also the only source between transcript refreshes.
- Authoritative counts per host today: claude-code (`message.usage`, read), codex (`event_msg`/`token_count` with `last_token_usage`/`total_token_usage` in the rollout — read only by `_codex_cache_usage` for cache rate and by `usage_from_event` on live `turn.completed`; **never reaches `usage_events`**, because `_backfill_usage_events` requires assistant records with `message.usage`), qwen (`HOST_COMPATIBILITY.md` says usage is present, but `normalize_qwen_record` rebuilds `message` without `usage`), gemini/omp (normalizers have no token handling), kimi-code (`HOST_COMPATIBILITY.md` records no usage events in stream-json), opencode (deferred; `step_finish.part.tokens`). Codex or qwen are the hosts whose ingestion gap is smallest; no code today reads either into `usage_events`.
- `token_reporting` already exists as an advisory, unstructured runtime `report_rows` entry (status + note) in `RUNTIME_HOST_CAPABILITIES` (codex row confirmed "full"; other hosts' rows not inspected) and in `cli/doctor.py` `_ADVISORY_CAPABILITIES`. A typed `token_source` overlaps with it; `verify_host_map._check_runtime_contradiction` only cross-checks report rows whose name equals a `HostCapabilities` field.

**Dependent Files (Callers/Importers)**
- `cli/ctx_stats.py` importers: `cli/__init__.py:58`, `tests/test_cli_ctx_stats.py:13`. `main_ctx_stats` is the only caller of `_aggregate_usage_events` (:813) and `_render_fallback` (:848). `capabilities.py` importers: `adapters/{qwen,omp,kimi,gemini,codex,core}.py`, `cli/adapt.py:12`, `cli/verify_host_map.py:48`, `tests/test_verify_host_map.py:6`.
- Other readers of `usage_events` token columns (must tolerate any schema change): `history_reader/usage.py` (`cost_attribution`, `waste_attribution`, `recent_usage_events`), `cli/artifact/dashboard.py` and its `dashboard.llat` template, `issue_history/agent_quality.py`, `fsm/cost_graph.py`, `observability/tracing.py`.

**Constraints if a stored `source` is added (schema change)**
- Migrations are append-only `ALTER TABLE ... ADD COLUMN`, nullable, fix-forward, one string appended to `_MIGRATIONS` with an issue-tagged comment; `SCHEMA_VERSION` must equal `len(_MIGRATIONS)` (`test_schema_version_matches_migrations_length`); `session_store/schema_manifest.json` must be regenerated; about 25 tests in `test_session_store_schema.py` hardcode the current version.
- `session_store/queries.py` `_SHAREABLE_COLUMNS["usage_events"]` is a hashed allowlist: a column change requires bumping `_SHAREABLE_ALLOWLIST_VERSION`, and `test_feat3304_artifact_dashboard.py` pins both.
- `usage_events` column naming differs from `harness_events` (`cache_read_input_tokens` vs `cache_read_tokens`), and closed vocabularies on new columns elsewhere use SQL `CHECK (... IN (...))` (`research_triage_events`, `harness_events`) while `usage_events` columns carry none.

**Conventions in Force**
- A new `HostCapabilityEntry` field is defaulted and set explicitly on every entry with an issue-tagged rationale comment (`subagents: SubagentSupport = "none"`, ENH-2874); closed vocabularies are module-level `Literal` aliases above the dataclass. Parity gate: `ll-verify-host-map` (doc-key parity, runtime-vs-registry, emitter agreement) — none inspects token fields, so a new field is unguarded unless a check is added. The HOST_COMPATIBILITY.md adapter table is hand-authored and compared by host key only.
- Additive JSON key convention in `_print_json`: added inside the `sqlite` branch, `None` when unbacked, text output byte-identical in the default case (tests: `TestCacheHitRateInOutput` in `test_cli_ctx_stats.py`, including a byte-identical-for-claude-code case).
- Estimate labeling elsewhere is by name (`used_tokens_est`, `estimated_tokens`), not by a provenance column. Closest labeled-provenance vocabulary: `Confidence = Literal["exact","heuristic"]` in `codequery/core.py`.
- Host log parsers: one module per non-Claude host under `session_store/` normalizing to Claude-shaped records, dispatched by `_PARSERS` in `session_store/sessions.py`; the qwen/gemini/omp normalizers strip `message.usage` and `_compute_cache_rate_from_jsonl` documents a native usage reader for them as a follow-up.

**Tests**
- `scripts/tests/test_cli_ctx_stats.py` (`TestAggregateUsageEvents` ~:234–270, fallback `estimated_tokens` fixture ~:380), `test_verify_host_map.py`, `test_adapters.py`, `test_session_store_schema.py`/`writers.py`/`lifecycle.py`, `test_history_reader_usage.py`, `test_hooks_integration.py` (context-monitor `estimated_tokens` behavior), `test_enh_3166_qwen_normalizer.py`, codex fixtures under `scripts/tests/fixtures/codex/`.

**Documentation**
- `docs/reference/CLI.md` (`ll-ctx-stats` ~:568, JSON key list ~:578), `docs/reference/HOST_COMPATIBILITY.md` (token-reporting row ~:264, codex usage ~:316–327), `docs/reference/API.md` (`main_ctx_stats`), `docs/guides/SESSION_HANDOFF.md` (state file example), `docs/development/TROUBLESHOOTING.md` (~:1167).

## Program Design

### Types

- `TokenSource = Literal["measured", "estimated"]`
- `HostCapabilityEntry.token_source: TokenSource = "estimated"`

### Signatures

- `token_source_for(host: str) -> TokenSource` — looks up `HOST_CAPABILITIES[host].token_source`
- `_render_fallback(state: dict[str, Any], logger: Logger) -> None` — labels figures as estimates
- `_aggregate_usage_events(db_path: Path) -> dict[str, Any] | None` — includes `source` per figure

### Call Path

`main_ctx_stats` -> `_aggregate_usage_events` -> `token_source_for` -> `HOST_CAPABILITIES`

## Impact

- **Priority**: P0 - token cost is the project's lead metric; unlabeled estimates are a false accuracy claim
- **Effort**: Medium - labeling half is small; the authoritative-read half depends on the log-ingestion seam
- **Risk**: Low - additive capability field and output labels
- **Breaking Change**: No (JSON output gains a `source` key)

## Status

**Open** | Created: 2026-09-23 | Priority: P0


## Session Log
- `/ll:refine-issue` - 2026-09-23T23:20:19 - `1dd8afb6-deef-4834-bd0a-401f1160db13.jsonl`
- `/ll:format-issue` - 2026-09-23T22:59:16 - `f909c28b-1081-4c2f-b215-fc2794a9d5b6.jsonl`

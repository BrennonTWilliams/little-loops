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

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/host_runner.py` — `RUNTIME_HOST_CAPABILITIES` carries the codex `token_reporting: "full"` report row (~:647–648); `token_source` on `HostCapabilityEntry` is a second, separate surface — keep the two consistent [Agent 1/2 finding]
- `scripts/little_loops/cli/doctor.py` — `_ADVISORY_CAPABILITIES = frozenset({"claude_md_suppression", "token_reporting"})` (~:102) [Agent 1/2 finding]
- `scripts/little_loops/adapters/core.py` — `HOST_CAPABILITIES.get(getattr(emitter, "name", ""))` (~:573); `scripts/little_loops/text_utils.py` (~:291–293) also imports `HOST_CAPABILITIES` [Agent 1 finding]
- `scripts/little_loops/cli/ctx_stats.py` — `_codex_cache_usage` (def ~:356, called ~:424) is the existing codex authoritative-count reader; `estimated_tokens` read in `_render_fallback` (~:594) and `_print_json` (~:669); `_print_json` emits `usage_by_model` (~:661, undocumented in CLI.md) and top-level `source` at ~:646/:668/:676 [Agent 1/2 finding]
- `scripts/little_loops/subprocess_utils.py` — `usage_from_event` (def ~:81; calls ~:143, :169, :706, :730) parses claude `result` and codex `turn.completed` usage [Agent 1 finding]
- `scripts/little_loops/fsm/executor.py` — live `record_usage_event` call (~:4393–4399); this is the writer that would stamp `source` [Agent 1 finding]
- `scripts/little_loops/session_store/lifecycle.py` — `_backfill_usage_events` call (~:1004) and table-count list (~:949, :982) [Agent 1/2 finding]
- `scripts/little_loops/session_store/{qwen,sessions,codex}.py` — `normalize_qwen_record` (qwen.py ~:59; sessions.py ~:1126/:1143), `codex.py` docstring on `_codex_cache_usage`/`event_msg`/`token_count`; the seams where native usage would be read [Agent 1 finding]
- `scripts/little_loops/session_store/queries.py` — `_SHAREABLE_COLUMNS` (~:149) and `_SHAREABLE_ALLOWLIST_VERSION = 1` (~:179); `cli/artifact/dashboard.py` imports both (~:37–38, :98, :317) [Agent 1/2 finding]
- `scripts/little_loops/history_reader/usage.py` — `cost_attribution` allows a raw `usage_events` column as `group_by`, so `source` would become groupable; also `waste_attribution`, `recent_usage_events`; `history_reader/models.py` `UsageEvent` (~:244) [Agent 2 finding]
- `scripts/little_loops/history_reader/context.py` / `models.py` — `used_tokens_est` SELECTs (~:145, :174, :209) and dataclass field (~:276) [Agent 1 finding]
- `scripts/little_loops/issue_history/{agent_quality,quality_regressions,workspace_quality}.py`, `init/core.py` — read `usage_events`; must tolerate a new nullable column [Agent 2 finding]
- `scripts/little_loops/hooks/session_start.py` (~:174–196, ENH-2581) — a `SCHEMA_VERSION` advance triggers `--rebuild` on next SessionStart in every local-editable project [Agent 2 finding]
- `scripts/little_loops/loops/context-health-monitor.yaml` (~:26–27) — echoes `jq -r '.estimated_tokens // "n/a"' .ll/ll-context-state.json` unlabeled [Agent 1 finding]
- `hooks/scripts/context-monitor.sh` (`estimated_tokens` written ~:256/:404, read ~:300/:330; `used_tokens_est` to `context_events` ~:87) and `hooks/scripts/context-handoff-sentinel.sh` (~:40, :51) already distinguish `result_token_count` (measured) from `estimated_tokens` [Agent 1/2 finding]
- `scripts/little_loops/cli/harness.py` — 26 hits on `input_tokens|total_tokens|cache_read` (ENH-3464 efficiency vector); candidate token-figure renderer to check for labeling [Agent 1 finding]

### Files to Modify (wiring additions)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/verify_host_map.py` — add a `token_source` consistency rule in `_check_emitter_agreement` or `_check_runtime_contradiction` (cross-check against the `token_reporting` report row); no check inspects token fields today [Agent 2 finding]
- `scripts/little_loops/session_store/schema_manifest.json` — regenerate if a `usage_events.source` column is added; `package_data.py` ships it [Agent 1/2 finding]
- `scripts/little_loops/session_store/queries.py` — `_SHAREABLE_COLUMNS["usage_events"]` (12 columns) and `_SHAREABLE_ALLOWLIST_VERSION` only if `source` joins the shareable export [Agent 2 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` § `ll-ctx-stats` — `--json` key list (`cache_rate_host` etc.), intro "token estimates" wording; add per-figure source and document `usage_by_model`; ~:5178 dashboard allowlist prose [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md` — "Token reporting" row (~:264) with `[^tok]`/`[^tok-codex]`/`[^qwen]`/`[^kimi]`/`[^gemini]`/`[^omp]` footnotes, codex reader (~:316–333, :566); hand-authored per-host measured/estimated narrative [Agent 2 finding]
- `docs/reference/API.md` — `main_ctx_stats` (~:5146), `_aggregate_context_pressure` (~:9452), `used_tokens_est` (~:9421, :10163), `cost_attribution`/`waste_attribution`/`recent_usage_events` (~:8801/:8821/:8431) [Agent 1/2 finding]
- `docs/reference/CONFIGURATION.md` (~:567 `analytics.capture.usage_events`; ~:532 token-priority tiers; ~:968 `_SHAREABLE_COLUMNS`) [Agent 1/2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md` — schema-history table (last row `v52`; add v53) [Agent 2 finding]
- `docs/ARCHITECTURE.md` — migration table (~:659–685, add v53) and `result_token_count` tiers (~:1414–1418) [Agent 1/2 finding]
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` (~:309), `docs/guides/SESSION_HANDOFF.md` (~:288, :366), `docs/development/TROUBLESHOOTING.md` (~:1167), `docs/observability/otel-mapping.md`, `docs/observability/realized-savings-verification.md`, `docs/codex/usage.md` (~:125) — mention estimated/measured tokens or `usage_events` columns [Agent 1/2 finding]

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_ctx_stats.py` — add estimate-label and per-figure `source` cases in `TestMainCtxStats`/`TestAggregateUsageEvents`; follow `TestCacheHitRateInOutput.test_json_includes_cache_rate_host` (:1177) and `test_json_cache_rate_host_null_when_no_jsonl` (:1192). Existing substring asserts in the fallback test (~:374–396: `"12,345"`/`"12345"`, `"read"`) and `data["source"] == "sqlite"` (~:422) must keep passing [Agent 2/3 finding]
- `scripts/tests/test_verify_host_map.py` (`subagents` per-host assertions :35–50; explicit `HostCapabilityEntry(...)` constructions ~:159, :192–237) and `test_adapters.py` `TestFixtureHostRegistration` (~:1271–1293) — survive only if `token_source` has a default; extend bad-map fixtures for a new check [Agent 2/3 finding]
- `scripts/tests/test_session_store_schema.py` — new v53 column migration class following the v29 `run_id` tests (~:1518–1549); `test_manifest_schema_version_matches_live_schema_version` (~:3169) and `test_schema_manifest_matches_checked_in_file`; verify `test_usage_events_columns` (~:1030, v20) does not use exact `==` [Agent 2/3 finding]
- `scripts/tests/test_session_store_writers.py` — hard-coded `SCHEMA_VERSION == 52` pins (~:521–522, :1386, :1516, :1855, :2097); `test_assistant_messages.py` (~:88) also pins 52; update all in the same commit [Agent 2/3 finding]
- `scripts/tests/test_feat3304_artifact_dashboard.py` — `PINNED_VERSION`/`PINNED_HASH` in `test_allowlist_and_version_change_together` (~:659), hand-built fixture DDL (~:87–93) and `== _SHAREABLE_COLUMNS["usage_events"]` (~:237); touched only if `source` joins the allowlist [Agent 2/3 finding]
- `scripts/tests/test_enh_3166_qwen_normalizer.py` — `test_ui_telemetry_has_no_normalized_equivalent` asserts the opposite of qwen token extraction; update if qwen is the chosen host [Agent 3 finding]
- `scripts/tests/test_subprocess_utils.py` (`usage_from_event` ~:3280–3342), `test_session_store_lifecycle.py`, `test_history_reader_usage.py` (uses named-column INSERTs, safe), `test_hooks_integration.py` (`estimated_tokens` ~:105–1090, `used_tokens_est` ~:410), `test_cli_doctor.py` (~:149–182, `token_reporting` advisory), `test_host_runner.py` (~:2233–2238, codex `token_reporting == "full"`), `test_history_store_chokepoint_gate.py` (~:20, names `cli/ctx_stats.py` as a diagnostic aggregator — new raw-SQL reads fall under it) [Agent 1/2 finding]
- `scripts/tests/fixtures/codex/rollout-interactive.jsonl` — fixture for a codex `token_count` → `usage_events` ingestion test [Agent 3 finding]

### Configuration
_Wiring pass added by `/ll:wire-issue`:_
- `.ll/evidence-precision-labels.json` — precision-label registry that mentions `usage_events`; check whether it carries a rule tied to estimate labeling [Agent 1/2 finding — unverified]
- `docs/reference/json-output-contracts.md` is not affected; no loop, hook, skill or command parses `ll-ctx-stats --json` [Agent 2 finding]

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Keep the per-figure `source` off the top level of `_print_json` (already `sqlite|fallback|none`); nest it under the figures or use a distinct key
- Add `token_source` with a default to `HostCapabilityEntry` and set it explicitly on all 6 entries; add a `verify_host_map` rule tying it to the runtime `token_reporting` row
- If `usage_events.source` is added: append one migration, bump `SCHEMA_VERSION` to 53, regenerate `schema_manifest.json`, update the `== 52` pins in `test_session_store_writers.py` and `test_assistant_messages.py`, add v53 rows to `HISTORY_SESSION_GUIDE.md` and `ARCHITECTURE.md`; expect a SessionStart `--rebuild` in every local-editable project
- Decide allowlist membership up front: adding `source` to `_SHAREABLE_COLUMNS` requires the `_SHAREABLE_ALLOWLIST_VERSION` bump, the pinned hash, and the dashboard fixture DDL
- For the codex or qwen ingestion half, extend `_backfill_usage_events` and the live `record_usage_event` path, add fixture-backed tests, and update `test_ui_telemetry_has_no_normalized_equivalent` if qwen is chosen
- Label `context-health-monitor.yaml` and the `SESSION_HANDOFF.md`/`TROUBLESHOOTING.md` `estimated_tokens` examples
- Update `CLI.md` (including the undocumented `usage_by_model` key) and `HOST_COMPATIBILITY.md`

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
- `/ll:wire-issue` - 2026-09-23T23:43:26 - `96fe3651-90ba-4862-a958-697a2df577cc.jsonl`
- `/ll:refine-issue` - 2026-09-23T23:20:19 - `1dd8afb6-deef-4834-bd0a-401f1160db13.jsonl`
- `/ll:format-issue` - 2026-09-23T22:59:16 - `f909c28b-1081-4c2f-b215-fc2794a9d5b6.jsonl`

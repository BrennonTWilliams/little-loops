---
id: BUG-3531
type: BUG
title: Codex live usage stores cache-inclusive input_tokens in the uncached-input
  column
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T00:20:32Z'
blocks:
- ENH-3528
- ENH-3532
labels:
- observability
- multi-host
---

# BUG-3531: Codex live usage stores cache-inclusive input_tokens in the uncached-input column

## Summary

Codex's `turn.completed` usage reports `input_tokens` **inclusive** of cached and cache-write tokens, but `usage_from_event` (`scripts/little_loops/subprocess_utils.py`) stores it unchanged in the `input_tokens` field, whose meaning everywhere else (Claude's disjoint three-way split, `estimate_cost_usd`, `usage_events`) is **uncached** input. Cached Codex tokens are therefore counted twice in any input + cache total, and mixed-host aggregates add two different quantities in one column.

## Steps to Reproduce

1. `python -c "from little_loops.subprocess_utils import usage_from_event as u; print(u({'type':'turn.completed','usage':{'input_tokens':1000,'cached_input_tokens':600,'output_tokens':10}}, default_model='x'))"`
2. Observe `input_tokens=1000, cache_read_tokens=600`; any input + cache total counts the 600 cached tokens twice. Expected uncached input is `400` when cache-write is explicitly zero (as `codex-cli 0.152.1` always emits it); an omitted cache-write leaves the disjoint uncached component unavailable (`None`).
3. Real capture: `scripts/tests/fixtures/codex/exec-json-turn.jsonl` reports `"input_tokens":38945,"cached_input_tokens":26752,"cache_write_input_tokens":0`; today it is stored as-is, so 26,752 cached tokens are counted in both columns. Correct uncached input is `12193`.

## Current Behavior

- `usage_from_event` for `turn.completed` (post-ENH-3538): `input_tokens=usage.get("input_tokens")`, `cache_read_tokens=usage.get("cached_input_tokens")`, `cache_creation_tokens=usage.get("cache_write_input_tokens")` — no subtraction, no validation of component types; `provenance` stays `'unknown'`.
- `ctx_stats._codex_cache_usage` already treats Codex input as inclusive and derives `uncached = max(0, input_tokens - cached_input_tokens - cache_write_input_tokens)` (`ctx_stats.py`), so the two Codex paths disagree.
- `_codex_cache_usage` sums `input_tokens`, `cached_input_tokens` and `cache_write_input_tokens` across all turns first and only then clamps with `max(0, …)` (`ctx_stats.py:388`). One inconsistent turn is therefore hidden by another turn's positive uncached balance, and `test_codex_clamps_negative_uncached_to_zero` (`test_cli_ctx_stats.py:1043`) enshrines the silent clamp.
- `ctx_stats._aggregate_usage_events` sums `input_tokens` and the cache columns across all rows regardless of host. **Out of scope here**: mixed-host/legacy aggregate composition belongs to ENH-3528.
- The Claude cache-rate reader in `_compute_cache_rate_from_jsonl` (`ctx_stats.py:451-453`) has the same `int(usage.get(..., 0))` coercion. **Out of scope here**: this bug changes only the Codex reader.
- `FSMExecutor` sums `TokenUsage` fields across a state's usage events into the `action_complete` payload (`executor.py:2697`). Any status carried outside `TokenUsage` is lost there.
- Pre-foundation live Codex rows are not identifiable by host: `turn.completed` has no `model` field (rows store `"unknown"`), and the old writer stored no host. ENH-3538's writer (landed, schema v54) stamps host via `_stamp_usage` but deliberately leaves provenance unknown; that does not certify foundation-era rows' input semantics.
- Container validation is also missing: a nonempty list or string in live `usage` raises `AttributeError`, while an empty object is silently discarded by the `if not usage:` truthiness check (`subprocess_utils.py` `usage_from_event`). Component validation alone does not close this gap. The check (`subprocess_utils.py:153-154`) is shared with the Claude `result` branch, so a non-dict Claude `usage` raises too.
- `fake_host`'s `turn_completed` directive omits `cache_write_input_tokens` by default (`fake_host.py:283-291`, commented "the real shape"), and `test_enh3538_token_observations.py:117` (`test_turn_completed_omits_cache_write_by_default`) asserts that. Decision 6 showed 0.152.1 always emits the field. Left as is, every fake-host Codex run would normalize to `input_tokens=None`/`unknown`, and no end-to-end test could reach `measured`.
- `_compute_cache_rate_from_jsonl` returns `None` for three different cases: no session, a Claude session with zero total, and a Codex session with no usable `token_count` event. `_print_json` then emits null for every cache-rate key, so it cannot tell a Codex no-observation result from a missing or non-Codex session.
- The producer can emit fabricated zeros: when no `ThreadTokenUsageUpdated` notification arrives before the turn completes, `codex exec` emits `Usage::default()` (all components `0`). Today that is stored as a real zero observation.
- USD cost is not currently affected: `MODEL_PRICING` has no OpenAI models, so Codex rows get `cost_usd = NULL`. It becomes a cost bug the moment Codex pricing is added.

## Expected Behavior

Live Codex usage is normalized to the canonical disjoint contract before it leaves `usage_from_event`: `input_tokens` = uncached input, with cache-read/cache-write as separate components. Inconsistent, missing, or malformed components must not be silently clamped or coerced into a plausible measured split. Cache-rate text and JSON output expose excluded observations, including when no valid observation remains.

## Integration Map

- `scripts/little_loops/subprocess_utils.py` `usage_from_event`, `TokenUsage`; `scripts/little_loops/cli/ctx_stats.py` `_codex_cache_usage`, `_render`, `_print_json` — propagate excluded-event counts and unavailable rates into public text/JSON output, not only the helper's dict.
- `scripts/little_loops/fsm/executor.py` — `action_complete` usage aggregation; relies on ENH-3538's completeness-aware sums (no new flag).
- `scripts/little_loops/session_store/writers.py` `record_usage_event` — persist inconsistent observations as `provenance='unknown'` using ENH-3538's columns.
- `scripts/little_loops/fake_host.py` — the `turn_completed` directive defaults `cache_write_input_tokens` to `0` (0.152.1 shape); `omit=cache_write` keeps the older-CLI shape available. Update the stale "Codex omits cache_write_input_tokens by default" comment. With all defaults, a bare `turn_completed` now emits all-zero usage and triggers Decision 1's live all-zero rule. Tests that need a measured row must pass nonzero values.
- `scripts/little_loops/runner_spec.py` (`_run_skill` / `_run_prompt`, lines ~276, ~459) — `RunnerResult` efficiency fields (ENH-3464) come from `usage_from_stream_lines` → `usage_from_event`, so Codex `input_tokens` there also becomes uncached input (or `None` when inconsistent). Codex efficiency figures captured before this fix aren't comparable; note this in the CHANGELOG entry.
- Stale docstrings/notes to update: `TokenUsage.provenance` ("No acquisition path is `measured` yet", `subprocess_utils.py:87`); the `usage_from_event` docstring ("until BUG-3531 Decision 6 establishes otherwise", `subprocess_utils.py:149-150`, and it should state that `input_tokens` is uncached input for every host); `record_usage_event` ("nothing here certifies `measured`", `session_store/writers.py:1955`); the Codex `token_reporting` capability note (`host_runner.py:643-652`), which should say that Codex input is normalized to uncached.
- Existing tests that change: `test_codex_turn_completed_event_with_usage` (`test_subprocess_utils.py:3338`) asserts `input_tokens == 1000` (becomes `425` = 1000 − 500 − 75, measured); `test_turn_completed_omits_cache_write_by_default` (`test_enh3538_token_observations.py:117`) flips to assert a default `0`, with a separate `omit=cache_write` case; `test_codex_clamps_negative_uncached_to_zero` (`test_cli_ctx_stats.py:1043`) is replaced (see AC).
- Tests: `test_subprocess_utils.py`, `test_cli_ctx_stats.py` (replace `test_codex_clamps_negative_uncached_to_zero`; test public JSON/text output), `test_fsm_runners.py`, `test_fsm_executor.py`, `runner_spec` usage tests; fixtures `scripts/tests/fixtures/codex/` (`rollout-interactive.jsonl` for reasoning; matched stdout/rollout captures for the live path). Add null/negative/boolean/nonnumeric component cases, empty/wrong-type `usage`/`info`/`last_token_usage` containers, and mixed, all-excluded, valid-zero, and no-observation cache-rate cases.
- Fixtures (captured 2026-09-24, committed with this review): `exec-json-turn.jsonl` (fresh `codex exec --json`, 2 model requests), `exec-json-resume.jsonl` (`codex exec resume --last --json`, 1 request), `rollout-exec-resume.jsonl` (matching rollout, trimmed to token-accounting records).
- Documentation: fixture README (§ Live `codex exec --json` usage contract) records CLI version, capture procedure, observation scope, and cache-write evidence; CHANGELOG documents new Codex input semantics and public cache-rate exclusion fields. `docs/reference/CLI.md:578` (`ll-ctx-stats --json`) documents `cache_rate_consistent_events`/`cache_rate_inconsistent_events`, their `null`-for-non-Codex rule, and nullable cache-rate token fields. `ll-ctx-stats` has no JSON schema under `docs/reference/schemas/`. `docs/reference/API.md` documents `normalize_codex_input`/`CodexInputSplit` and that `TokenUsage.input_tokens` is uncached input for every host.

## Design Decisions

_Revised 2026-09-24. All decisions are resolved; Decision 6's producer contract is established from the version-matched source and a matched live/rollout capture._

1. **Representation.** `normalize_codex_input(usage) -> CodexInputSplit`, a frozen dataclass `(uncached_input: int | None, cache_read: int | None, cache_write: int | None, consistent: bool)`. A consistent observation gives `uncached_input = input - cache_read - cache_write` only when all three inputs are known nonnegative integers. When valid cache components exceed inclusive input, the result is `consistent=False`, with `uncached_input=None` (unavailable, per ENH-3538's null-not-zero rule) and the valid cache components kept exactly as reported. `consistent` is local to the split; it is not added to `TokenUsage`.
   - **Missing keys.** Missing `input_tokens` or `cached_input_tokens` makes the split unavailable/inconsistent (`cache_read=None` for the latter). Omitted `cache_write_input_tokens` is always unknown: `cache_write=None`, `uncached_input=None`, `consistent=False`. Decision 6 established that 0.152.1 always emits the field on both paths, so an omission indicates an older CLI that predates it; there is no zero-on-omission option.
   - **Malformed components.** Explicit `null`, negative integers, booleans, floats, strings (including numeric strings), and other noninteger values are unavailable (`None`), never coerced via `int(...)` or `or 0`. Validate input, cache-read, cache-write, and output independently. Preserve other valid reported components; an invalid/missing input-split component makes `uncached_input=None` and `consistent=False`. Invalid/missing output becomes `output_tokens=None` and prevents measured row provenance, but does not invalidate an otherwise valid input split used solely for cache-rate calculation. Explicit cache-write `null` never uses the omitted-key zero rule.
   - **Containers and empty objects.** Validate mapping types before `.get` calls; do not use truthiness to decide whether an observation is present. For live `turn.completed`, absent or explicit-null `usage` means no observation; a present empty object is an all-missing observation, and a present non-object (`[]`, `[1]`, strings, booleans, numbers) is malformed. Empty/malformed live observations reach the detailed callback/persistence with all components `None` and unknown provenance; they never fire the legacy callback or become zero usage. An entirely empty or non-object block cannot fabricate a zero component.
   - **Live all-zero usage.** A live `turn.completed` whose input, cache-read, cache-write, and output components are all valid `0` is the producer's `Usage::default()` fallback (Decision 6), not a measurement: all components become `None` with unknown provenance, it reaches the detailed callback/persistence like an empty observation, and never fires the legacy callback. This rule is live-path only; a rollout `last_token_usage` of all zeros remains a valid zero observation (Decision 4).
   - **Claude `result` branch.** Restructuring the shared presence check must not change Claude semantics: absent, null, or empty `usage` still returns `None`. It does get the mapping-type guard, so a non-object `usage` returns `None` instead of raising. The live all-zero rule, `normalize_codex_input`, and measured provenance do not apply. Claude rows stay `unknown` (ENH-3528 owns any Claude promotion).
   - **Rollout containers.** Missing or null `info` is no usage (including rate-limit-only events). A mapping `info` without `last_token_usage`, including `info={}`, has no per-request observation; never substitute `total_token_usage` automatically. A present `last_token_usage` that is empty, null, or non-object counts as one excluded observation with unavailable components. Non-null, non-object `info` in a `token_count` record also counts once as malformed/excluded. No shape raises; public accepted/excluded counts distinguish these cases from absent usage. ENH-3532 reuses these rules when it adds persistence; this bug fix adds no historical ingestion.
2. **Survives aggregation.** No new `TokenUsage` flag. `usage_from_event` maps a consistent input split onto ENH-3538's fields; `provenance='measured'` requires a consistent split, a valid known output count, and a non-all-zero observation. `usage_from_event` does **not** set `host`: `_stamp_usage` in `run_claude_command` already stamps the resolved runner host (and warns on a parser/runner mismatch, which `fake_host`'s `turn.completed` under a non-codex runner would trigger). The `runner_spec` path (`usage_from_stream_lines`) is unstamped; `RunnerResult` carries no host, so nothing is lost there. Otherwise provenance is `unknown`; an inconsistent input split specifically gives `input_tokens=None`, retaining other valid components. ENH-3538's completeness-aware executor sums carry missing-component counts into the `action_complete` payload, and each `TokenUsage` is still collected individually for per-row persistence. A valid input split can remain numeric when only output is missing, without certifying the row as measured.
3. **Survives persistence.** Rows are written through ENH-3538's writer with the provenance above and `channel='live'`. This relies on ENH-3538's migration and nullable components (landed; schema v54), not on all of ENH-3528. Landing the normalization first would mix corrected and uncorrected rows with nothing to tell them apart.
4. **Per-observation, before summing.** `_codex_cache_usage` normalizes each usage observation and then sums only consistent input splits. Missing/malformed input splits and cache components exceeding inclusive input are excluded from the hit-rate numerator and denominator, and counted as `inconsistent_events`; valid splits count as `consistent_events`. `info: null` rate-limit-only records are not usage observations and affect neither count. A present but incomplete usage observation counts as excluded. It never clamps an aggregate.
   - **Public result.** The helper returns both counts plus its existing fields. `_print_json` exposes `cache_rate_inconsistent_events` and `cache_rate_consistent_events` beside the existing `cache_hit_rate_pct`/token/host fields. Text reports exclusions whenever nonzero and identifies mixed results as based only on accepted observations; the extra fields must not disappear at the renderer boundary.
   - **All excluded.** Return a result with `hit_rate_pct=None`, token totals `None`, `consistent_events=0`, and the retained exclusion count. JSON emits nulls and the counts; text reports an unavailable rate and the exclusions, never `None%`, `0%`, or zero token totals.
   - **Valid zero usage.** A consistent all-zero observation remains accepted: token totals are zero and `hit_rate_pct=None` because the denominator is zero. Text identifies zero usage; both counts distinguish this case from all-excluded.
   - **No observation vs. no Codex source.** When a Codex session exists but contains no usage observation, `_codex_cache_usage` returns a result dict (not `None`) with both counts `0`, null rate/token totals, and `host='codex'`. JSON emits those zero counts; text prints nothing or a "no usage observed" line, never `0%`. `_compute_cache_rate_from_jsonl` still returns `None` when no session exists. The Claude reader's dict carries no counts. In both cases JSON emits `cache_rate_consistent_events`/`cache_rate_inconsistent_events` as `null`: the counts exist only for a Codex rollout source, so `0/0` never appears for a Claude or missing session.
5. **Legacy rows.** No correction. Pre-foundation live Codex rows can't be told apart from other hosts' rows (model `"unknown"`, no host), so they are not selected by model name and cached tokens are not subtracted wholesale. Foundation-era rows may have a Codex host but still unnormalized input: neither host nor release timing certifies them. Both classes keep `provenance='unknown'`; no retroactive subtraction or promotion. ENH-3528's aggregation reports that composition rather than presenting a clean total.
6. **Producer contract (resolved 2026-09-24, `codex-cli 0.152.1`).** Evidence: version-matched source (openai/codex tag `rust-v0.152.1`, external repo: exec crate `event_processor_with_jsonl_output.rs::usage_from_last_total`, `exec_events.rs::Usage`, app-server-protocol v2 `thread.rs::ThreadTokenUsage`) plus a matched stdout/rollout capture (`exec-json-turn.jsonl`, `exec-json-resume.jsonl`, `rollout-exec-resume.jsonl`; details in the fixture README).
   - **Scope: per invocation.** `turn.completed.usage` is `ThreadTokenUsage.total` at turn completion, which sums every model request in the invocation (capture: `19404+19541=38945` input, `112+5=117` output). `codex exec resume` does **not** restore the prior total (resumed invocation: `total == last == 19559`). `codex exec` shuts down after its single `turn.completed`, so the live value is exactly one invocation's usage: no baseline/differencing, `usage_from_event`'s signature is unchanged, and `_stamp_usage`'s `scope_kind='invocation'` is correct for both fresh and resumed runs (`host_runner.py` builds `exec resume --last`).
   - **Inclusive input** confirmed on both paths (`cached + cache_write <= input` on every observation).
   - **Cache-write is always emitted** (`#[serde(default)]` is deserialize-only; no `skip_serializing_if`); both captures carry explicit `0`. Omission = pre-field CLI → unknown (Decision 1).
   - **All-zero fallback.** With no usage notification the producer emits `Usage::default()`; handled by Decision 1's live all-zero rule.
   - **Residual, out of scope:** a mid-invocation auto-compaction may reset `total_token_usage` (per the `_codex_cache_usage` docstring), making a compacted invocation's live total an undercount. It can never double-count, so it does not affect this fix's correctness; not captured. Re-verify this contract when `codex --version` changes (fixture README re-capture rule).

## Implementation Steps

1. ~~Complete Decision 6's producer-contract investigation~~ — done 2026-09-24; fixtures and README committed.
2. Add shared normalization, container guards (including the Claude `result` mapping guard), per-component validation, and the live all-zero rule with focused absent/empty/malformed/partial/zero tests; wire the live parser (measured provenance) and per-observation rollout cache-rate reader. Flip `fake_host`'s `turn_completed` cache-write default to `0` and update the tests that pin it. Drive the live-path tests from `exec-json-turn.jsonl`/`exec-json-resume.jsonl`. Share the container contract with ENH-3532.
3. Carry accepted/excluded counts and unavailable rates through both public renderers; test mixed, all-excluded, valid-zero, no-observation, and non-Codex/no-session (`null` counts) outputs.
4. Verify executor missing counts, per-row persistence, legacy-row preservation, and runner efficiency pass-through against ENH-3538. Update the stale docstrings/capability note, `docs/reference/CLI.md`, `docs/reference/API.md`, and CHANGELOG; run focused tests and required project checks.

## Impact

- **Priority**: P2 — overstated token totals for Codex runs; latent cost bug.
- **Effort**: Medium — Decision 6 ruled out stateful differencing, so the parser change is small; the breadth is in validation, cache-rate public output, and test coverage.
- **Risk**: Low to medium — changes stored values for new Codex rows.
- **Related**: ENH-3532 (historical rollout ingestion) must use the same normalizer.

## Acceptance Criteria

- [ ] A complete Codex `turn.completed` with `input_tokens=1000, cached_input_tokens=600, cache_write_input_tokens=0, output_tokens=10` yields `input_tokens=400, cache_read_tokens=600, cache_creation_tokens=0, provenance='measured'`; through `run_claude_command` under the codex runner the row also has `host='codex'`, `scope_kind='invocation'`. Fixture-backed: `exec-json-turn.jsonl` yields `input_tokens=12193, cache_read_tokens=26752, cache_creation_tokens=0, output_tokens=117` and `exec-json-resume.jsonl` yields `input_tokens=231, cache_read_tokens=19328, output_tokens=5`, both measured. The same usage with `cache_write_input_tokens` omitted yields `input_tokens=None`, unknown provenance.
- [x] Matched stdout/rollout captures and the version-matched producer source establish the omitted-cache-write semantics (always emitted by 0.152.1; omission = older CLI = unknown). The fixture README records the evidence and CLI version (2026-09-24).
- [ ] A live `turn.completed` with all four components `0` yields all-`None` components, unknown provenance, reaches the detailed callback/persistence, and does not fire the legacy callback. A rollout all-zero `last_token_usage` still counts as an accepted zero observation.
- [ ] Inconsistent components (`cache_read + cache_write > input`) yield `input_tokens=None`, keep the reported cache components, and persist as `provenance='unknown'`. Covered at the `usage_from_event`, executor-payload (missing-input count) and `usage_events` row levels.
- [ ] `_codex_cache_usage` and `usage_from_event` share `normalize_codex_input`. `_codex_cache_usage` normalizes per turn before summing: a test with one inconsistent turn and one consistent turn shows the inconsistent turn excluded and counted, not absorbed.
- [ ] Public text and JSON tests verify accepted/excluded counts for mixed observations and all-excluded observations. All-excluded results retain the count with null rate/token totals and an unavailable text message. Consistent zero usage preserves zero token totals and a null rate with an accepted count; no-observation results have zero counts and null totals. Rate-limit-only events do not inflate either count.
- [ ] `test_codex_clamps_negative_uncached_to_zero` is replaced by a test asserting the inconsistent-turn outcome. No test requires a silent clamp.
- [ ] Output/reasoning inclusion is verified against `rollout-interactive.jsonl`, whose turns have nonzero `reasoning_output_tokens` (9, 158) and `total_tokens == input_tokens + output_tokens` (so reasoning is included in output and must not be added again). `rollout-exec.jsonl` can't establish this because its reasoning count is 0.
- [ ] The captured `codex exec --json` fixtures (`exec-json-turn.jsonl`, `exec-json-resume.jsonl`, committed 2026-09-24) drive the live-path tests via `usage_from_stream_lines` (the rollout fixtures come from a different event stream).
- [ ] Missing `input_tokens` or `cached_input_tokens` yields `uncached_input=None`, `consistent=False` (and `cache_read=None` for the latter); omitted cache-write yields `cache_write=None`, `uncached_input=None`, `consistent=False`.
- [ ] Parameterized boundary tests cover explicit `null`, negative counts, booleans, floats, numeric strings, and nonnumeric values in input/cache/output components. No case raises or fabricates zero; valid sibling components survive, missing counts reach executor/persistence, and malformed observations never receive measured provenance. A valid input split with missing/invalid output remains usable for cache rate but has `output_tokens=None` and unknown row provenance.
- [ ] Container tests cover absent/null/empty-object/list/string/boolean/numeric live `usage`, rollout `info`, and `last_token_usage`. Presence semantics follow Decision 1; no `.get` failure occurs. Empty/malformed live observations persist as all-null/unknown, while absent/null live usage creates no observation. Rollout no-observation cases do not affect counts; present malformed/empty usage counts exactly once as excluded and survives all-excluded public rendering. No omitted-key rule fabricates zero for an invalid or empty block.
- [x] The captured fixture set includes a multi-request invocation and a `codex exec resume` run and records the usage scope: per invocation (sum of the invocation's requests; the total is not restored on resume), so no differencing is needed (Decision 6).
- [ ] `_codex_cache_usage` over `rollout-exec-resume.jsonl` sums the three `last_token_usage` observations (input `58504`, cached `46080`, cache-write `0`) with `consistent_events=3`, not the cumulative `total_token_usage` values.
- [ ] Legacy rows follow Design Decision 5: no correction. A test shows existing pre-fix `usage_events` rows are unchanged by the migration and the new code, and still read as `provenance='unknown'`. (The mixed legacy + new **aggregate** composition report belongs to ENH-3528.)
- [ ] `fake_host`'s `turn_completed` emits `cache_write_input_tokens: 0` by default, and `omit=cache_write` still omits it. An end-to-end `run_claude_command` run under the codex runner, driven by a fake-host script with nonzero consistent values, persists a `usage_events` row with `provenance='measured'`, `host='codex'`, and normalized `input_tokens`. A bare `turn_completed` (all zeros) yields the all-`None`/unknown observation.
- [ ] The Claude `result` branch is unchanged for valid, absent, null, and empty `usage`. It stays `provenance='unknown'`, and a non-object `usage` (list/string/number) returns `None` without raising.
- [ ] `ll-ctx-stats --json` emits `cache_rate_consistent_events`/`cache_rate_inconsistent_events` as `null` when the cache rate comes from a Claude session or no session exists, and as integers (possibly `0`/`0`) only for a Codex rollout source.
- [ ] Stale "no path is `measured`" docstrings (`TokenUsage.provenance`, `record_usage_event`) and the `usage_from_event` Decision-6 reference are updated. `docs/reference/CLI.md` lists the new JSON keys.
- [ ] Foundation-era rows with `host='codex'` and unknown provenance remain unchanged too; host presence does not trigger retrospective normalization or certification. ENH-3532 owns additional live correlation identities, not this normalization fix.

## Program Design

### Types

- `TokenUsage` — no new fields (uses ENH-3538's nullable components and `provenance`/`host`); its `input_tokens` field is documented as uncached input for every host.
- `CodexInputSplit` — new frozen dataclass `(uncached_input: int | None, cache_read: int | None, cache_write: int | None, consistent: bool)`; nullable cache-write supports explicit null/malformed values and omissions (older CLIs).
- Cache-rate result — existing token/rate fields become nullable for unavailable data; adds integer `consistent_events` and `inconsistent_events`. Public JSON uses the `cache_rate_` prefix for both counts.

### Signatures

- `usage_from_event(event: dict[str, Any], *, default_model: str) -> TokenUsage | None` — signature unchanged (Decision 6: no stateful handling); the `turn.completed` branch validates container presence/type, applies the live all-zero rule, normalizes, and sets `provenance` (not `host`; `_stamp_usage` owns it).
- `normalize_codex_input(usage: Mapping[str, Any]) -> CodexInputSplit` — new shared helper for one observation; also used per observation by `_codex_cache_usage`. Never converts omitted, null, or malformed values to zero.

### Call Path

- `usage_from_event` → `FSMExecutor` (payload aggregation, per-event collection) → `record_usage_event` (live FSM path)
- `_codex_cache_usage` → `normalize_codex_input` → accepted/excluded cache-rate result → `_render` / `_print_json`

## Verification Notes

Historical verdict: **VALID** (2026-09-23, before the reviews below). `usage_from_event` `turn.completed` branch stores `input_tokens` unchanged (`subprocess_utils.py:105-110`); `_codex_cache_usage` documents inclusive input and subtracts. Inclusive-input evidence came from `scripts/tests/fixtures/codex/rollout-exec.jsonl` (`input_tokens` 13001, `cache_write_input_tokens` 12998). That rollout evidence does not by itself establish the omitted-field or cumulative-count contract of the separate live stream. `ll-verify-evidence` was clean.

**Correction (2026-09-23)**: the exec fixture's `reasoning_output_tokens` is 0, so `total_tokens = input + output` there cannot show whether reasoning is included in output. `rollout-interactive.jsonl` can: for example `output_tokens=237, reasoning_output_tokens=158, total_tokens=26316 = 26079 + 237`, so reasoning is a subset of output.

### Pre-implementation review 2026-09-23

Retargeted `blocked_by` from BUG-3530 (done) + ENH-3528 to ENH-3538 (extracted foundation). Replaced the `input_consistent` flag with `input_tokens=None` + `provenance='unknown'` so inconsistent input is unavailable rather than a fabricated 0 and survives payload summing.

### Pre-implementation review 2026-09-23 (2)

`cache_read` became `int | None` with explicit missing-key rules. This review still assumed omitted cache-write meant zero; review (3) below supersedes that assumption. Added `runner_spec` `RunnerResult` as an affected consumer, a cumulative-vs-per-turn capture check, and a row-level legacy criterion; the aggregate composition report belongs to ENH-3528.

### Pre-implementation review 2026-09-23 (3)

Applied public text/JSON exclusion reporting and all-excluded/valid-zero behavior; added strict component validation and nullable cache-write; strengthened the producer-contract prerequisite to require evidence for zero-on-omission as well as usage scope. Removed stale frontmatter confidence scores rather than presenting the earlier 95/100 as current readiness. The double-counting bug still reproduces; the producer-contract investigation remains outstanding. Re-run `/ll:confidence-check` after that evidence resolves the contract.

### Applied pre-implementation review 2026-09-24

Added explicit container validation/presence rules and tests for live `usage` and rollout `info`/`last_token_usage`; probes showed nonempty lists/strings currently raise while an empty usage object disappears. Kept the producer-contract investigation as a readiness gate and made effort provisional until cumulative/resume semantics resolve. Clarified preservation of foundation-era unnormalized rows and assigned additional live identity plumbing to ENH-3532. Specification changes only; the earlier confidence assessment is historical and must be rerun after Decision 6 and the foundation are complete.

### Producer-contract resolution 2026-09-24

Resolved Decision 6 from the `rust-v0.152.1` source and a live capture (`codex exec --json` with 2 model requests, then `codex exec resume --last --json`, model pinned to `gpt-5.6-sol`). Live usage is per invocation (not restored on resume), so no differencing is needed and the signature stays unchanged. Cache-write is always emitted, so the `omitted_cache_write_is_zero` option was dropped. Added the live all-zero (`Usage::default()`) rule. Removed `host` stamping from the parser (`_stamp_usage` owns it). Mid-invocation compaction remains an uncaptured undercount risk, recorded as out of scope. ENH-3538 is done, so the `blocked_by` edge is resolved. Re-run `/ll:confidence-check`.

### Pre-implementation review 2026-09-24 (2)

Checked the design against post-ENH-3538 code. Fixture figures (12193, 231, 58504/46080 over 3 observations) reproduce. Added: the `fake_host` `turn_completed` cache-write default flip (it omitted the field and would have made every simulated Codex run unknown), and the Claude `result` branch's shared container check (mapping guard, semantics otherwise unchanged). Also added the no-observation vs. no-session vs. non-Codex distinction for the public counts (`null` outside a Codex rollout source), the existing tests that change, stale docstrings/capability note, and concrete doc targets (`CLI.md:578`, `API.md`). Marked `_aggregate_usage_events` and the Claude cache-rate reader coercion as out of scope. Dropped the resolved `blocked_by: ENH-3538` edge (done) and the stale frontmatter scores. Re-run `/ll:confidence-check`.

## Status

**Open** | Created: 2026-09-24 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-24 (supersedes the earlier 95/71 scores). **Historical**: frontmatter scores removed in review 2026-09-24 (2); re-run before implementing._

**Readiness Score**: 65/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 63/100 → MODERATE

### Gaps to Address
_Both gaps resolved 2026-09-24: ENH-3538 is done; Decision 6 evidence and live fixtures are committed. Scores below are stale until the next confidence check._
- **Unresolved dependency (hard override)**: `blocked_by` ENH-3538 is `open` — land the foundation first (nullable components, `provenance`/`host` columns, completeness-aware executor sums).
- **Producer-contract evidence outstanding (Decision 6)**: matched `codex exec --json` stdout/rollout captures, per-turn vs thread-cumulative usage, and omitted `cache_write_input_tokens` semantics are unresolved; no live `turn.completed` fixture exists under `scripts/tests/fixtures/codex/` (only `rollout-exec.jsonl`, `rollout-interactive.jsonl`). This is Implementation Step 1 and gates `measured` provenance.

### Outcome Risk Factors
- Several design decisions left open pending the evidence: omission rule and cumulative-count/baseline-difference handling (may change the `usage_from_event` call path/signature).
- Shared normalizer spans `subprocess_utils`, `ctx_stats`, `runner_spec` and executor/persistence, plus ENH-3532 coupling.

## Session Log
- `/ll:confidence-check` - 2026-09-24T03:50:15 - `a1bbb8d4-d93b-4517-a766-21a26af03296.jsonl`
- `/ll:verify-issues` - 2026-09-24T03:44:03 - `747bdb3d-c82b-437c-9f00-ae0dbc6a8638.jsonl`
- `/ll:confidence-check` - 2026-09-24T00:45:01 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:37:52 - `97f40d76-766f-412a-a4ef-794728276e4c.jsonl`

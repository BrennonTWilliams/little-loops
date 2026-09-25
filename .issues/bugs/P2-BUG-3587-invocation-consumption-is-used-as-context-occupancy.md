---
id: BUG-3587
type: BUG
title: Invocation consumption is used as context occupancy
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T01:46:08Z'
parent: EPIC-3562
relates_to:
- ENH-3545
- ENH-3538
- ENH-1376
labels:
- observability
- context-monitor
---

# BUG-3587: Invocation consumption is used as context occupancy

## Summary

Invocation token consumption is written to `result_token_count` and treated as current context occupancy by the context monitor and handoff sentinel. Repeated model requests can consume more tokens than remain in the context window, so this can cause premature pressure warnings or handoffs. The value is also written after the session it describes has ended, into a repo-shared file, so it can only ever be read by a *different* session. Fix: retire the key — stop writing it and remove its priority tier from both hooks. This is independent of ENH-3545's additive provenance/staleness labels.

## Current Behavior

`scripts/little_loops/issue_manager.py` writes the sum of the legacy usage callback's input and output to the result_token_count state field. `hooks/scripts/context-monitor.sh` prioritizes that value over its transcript baseline and estimator, and `hooks/scripts/context-handoff-sentinel.sh` prioritizes it over `estimated_tokens`. The field has no metric/scope/freshness qualification and can survive context changes and compaction. ENH-3538's known-component lower bounds preserve consumption reporting; they do not establish current occupancy.

Lifecycle makes the value unusable as occupancy for any session:

- `_on_usage_writer` runs in the parent `ll-auto` process on the child's terminal `result` event — i.e. after the child's last turn.
- `session-cleanup.sh:38` (a **Stop** hook, fires at every turn end) runs `rm -f .ll/ll-context-state.json`, and `session_start.handle` / `session-start.sh:13` delete the file again at the next session start.
- So the writer typically recreates the file containing only `{"result_token_count": N}`, and the only possible readers are *other* sessions sharing the repo root (an interactive session, a concurrent run) before the next SessionStart deletes it. The observable failure is cross-session contamination: a finished child invocation's cumulative consumption drives another session's monitor tier 1 and Stop sentinel.
- The state file carries no session id, so no qualification written by this producer can make the value "a measurement for the same session/context interval".

## Expected Behavior

Consumption remains reported through its existing channels (`TokenUsage` via `on_usage` / `on_usage_detailed`, `ctx_stats`), but is never written into the context-occupancy state file. The monitor and sentinel select occupancy from the transcript baseline or the existing estimator only. A `result_token_count` key left in an old state file is ignored. Configured threshold values remain unchanged; corrected inputs may intentionally change when a warning or handoff fires.

## Motivation

Premature context-pressure handoffs interrupt useful work even when the active context fits. Correcting the metric lets occupancy protection remain useful without discarding valid consumption accounting.

## Proposed Solution

Retire `result_token_count` at both ends:

1. **Producer** — delete `_on_usage_writer` in `process_issue_inplace` (`issue_manager.py:811-825`) and pass the caller's `on_usage` straight through at its call site (~1347). Consumption reporting is unchanged because the closure only added the state-file write.
2. **Monitor** — remove tier 1 from `context-monitor.sh` `main()`: drop the field from the jq `@tsv` list and the `read -r` list together (position-coupled), remove the tier-1 branch and its "do NOT add TOKENS" comment. Occupancy order becomes transcript baseline + per-tool tokens > stored estimate + tokens.
3. **Sentinel** — remove the `TOKEN_COUNT` override in `context-handoff-sentinel.sh` (jq read ~38-44, its four-field default string, override ~51-55, the "accurate" comment); it uses `estimated_tokens` only.
4. **Compatibility** — no migration: both hooks simply stop reading the key, so a leftover value in an old state file is inert.

Already audited (no change): the Python context guards in `issue_manager.py` / `parallel/worker_pool.py` do not read the key or the state file — the cumulative `usage_ratio` arm was removed under BUG-2280. No consumption-budget consumer of the key exists. No new state keys, no ENH-3545 metadata dependency, and no compaction/session invalidation contract are needed, because nothing reads the key after this change. Do not replace the existing estimator.

## Integration Map

- Files: `scripts/little_loops/issue_manager.py`, `scripts/little_loops/parallel/worker_pool.py`, `hooks/scripts/context-monitor.sh`, `hooks/scripts/context-handoff-sentinel.sh`; context state readers as needed.
- Tests: `scripts/tests/test_hooks_integration.py`, issue-manager and worker-pool usage/guard tests, `scripts/tests/test_enh3538_token_observations.py` where prior lower-bound expectations encode occupancy behavior.
- Docs: `docs/guides/BUILTIN_HOOKS_GUIDE.md`, `docs/guides/SESSION_HANDOFF.md`, `docs/development/TROUBLESHOOTING.md`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Scope correction: the Python context guards are not occupancy consumers of this key. `run_with_continuation` (`issue_manager.py`) and `WorkerPool._run_with_continuation` (`parallel/worker_pool.py`) keep `_last_input`/`_last_output` only for guillotine resume text and `token_stats`. The cumulative-token `usage_ratio` arm was removed under BUG-2280, and neither file reads `result_token_count` or the state file. The only Python occupancy-affecting path is the writer itself, plus the sentinel, which `read_sentinel` turns into the Option E handoff turn in both files.
- No consumer classifies as a consumption budget: nothing compares `result_token_count` against a budget. Consumption stays reported through `TokenUsage` (cost/provenance, `ctx_stats`), not through this key. The acceptance criteria that name "consumption budget consumers" and "Python occupancy guards" have no current referent.
- Occupancy consumers of the key: `hooks/scripts/context-monitor.sh` `main()` (tier 1 of `NEW_TOKENS`, feeds `USAGE_PERCENT`, pressure levels, the handoff threshold, exit 2, and `ll-context-crossings.log`) and `hooks/scripts/context-handoff-sentinel.sh` (`TOKEN_COUNT` override, writes `.ll/ll-context-handoff-needed`).
- `pre_compact.py` and `precompact-state.sh` snapshot the whole state file, including the key, into `context_state_at_compact`. They do not modify the state file.
- Tests that encode the defect and must change with the behavior, all in `scripts/tests/test_hooks_integration.py`: `test_result_token_count_used_when_present`, `test_result_token_count_zero_falls_back_to_heuristics`, `test_impossible_baseline_clamped`, and `TestContextHandoffSentinel.test_result_token_count_preferred_over_estimated`. The monitor tests use `tmp_path/"ll-context-state.json"`, while the sentinel tests use `tmp_path/".ll"/"ll-context-state.json"`.
- Test gaps: no test calls `_on_usage_writer`, no test seeds `result_token_count` together with `last_compaction` or a precompact file, and `check_compaction` has no behavioral test (`test_pre_compact.py::test_check_compaction_reads_compacted_at` only greps script text).
- Docs repeating the tier order that must stay consistent: `docs/guides/SESSION_HANDOFF.md` (~359-397), `docs/ARCHITECTURE.md` (~1412-1420, "authoritative"), `docs/reference/CONFIGURATION.md` (~532), `docs/development/TROUBLESHOOTING.md` (~1165-1170). `docs/guides/BUILTIN_HOOKS_GUIDE.md` has no `result_token_count` mention. The comment at `context-handoff-sentinel.sh:51` ("accurate") also encodes the assumption.
- `scripts/little_loops/loops/context-health-monitor.yaml` reads only `.estimated_tokens` and is unaffected.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/scripts/context-monitor.sh` `main()` (jq `@tsv` read ~299-313) — `RESULT_TOKEN_COUNT` is a position-coupled `read -r` field; edit the jq list and `read` list together when removing/renaming it
- `hooks/scripts/context-monitor.sh` `main()` (~324-337, post-`check_compaction()` re-extract) — re-extracts `CURRENT_TOKENS`, `HANDOFF_COMPLETE`, etc. but not `RESULT_TOKEN_COUNT`; any invalidation must blank/refresh the shell variable here, not only rewrite state JSON in `check_compaction` [Agent 2 finding]
- `hooks/scripts/context-monitor.sh` `main()` (~361-380) — tier-1 branch skips `+ TOKENS` while tiers 2/3 add it; `overhead`/`SYSTEM_PROMPT_BASELINE` additions follow the tier choice, so falling through to tier 2/3 changes both additions [Agent 2 finding]
- `hooks/scripts/context-monitor.sh` `main()` (~385-387) — 3x-`CONTEXT_LIMIT` clamp was the only bound on an inflated tier-1 value [Agent 2 finding]
- `hooks/scripts/context-handoff-sentinel.sh` (jq `@tsv` read ~38-44, default string `"0	0	false	0"`, four fields in order) — separate copy of the field list; sentinel has no transcript-baseline tier or compaction check, so once the key is dropped it depends wholly on the monitor keeping `estimated_tokens` current [Agent 2 finding]
- `scripts/little_loops/subprocess_utils.py` `write_sentinel()` (~396-429) — second producer of the sentinel JSON schema (`written_at, token_count, context_limit, usage_percent`); consider if any qualification field is added. Readers `read_sentinel()` (`subprocess_utils.py:~371`), `issue_manager.py:540`, `parallel/worker_pool.py:1237` read only `usage_percent`, so added fields are compatible [Agent 2 finding]
- `scripts/little_loops/cli/ctx_stats.py` (`DEFAULT_STATE_RELPATH` ~61, loader ~331, ~594-604, ~815-827) — reads only `estimated_tokens`, labelled `estimated_entry(..., scope_kind="context")`; already consistent, no change unless new metadata keys should be surfaced [Agent 1/2 finding]
- `scripts/little_loops/hooks/pre_compact_handoff.py:176` — reads `ll-precompact-state.json`; touch only if the compaction-invalidation contract changes that file's shape [Agent 1 finding]
- Path-only state-file references, no change expected: `scripts/little_loops/parallel/merge_coordinator.py:188`, `scripts/little_loops/text_utils.py:211,215`, `scripts/little_loops/init/writers.py:103`, `scripts/little_loops/config-schema.json:256,260`
- Note: `_on_usage_writer` hardcodes `.ll/ll-context-state.json` (`issue_manager.py:813`) and ignores `context_monitor.state_file` (schema ~972-976); pre-existing coupling the change inherits

### Files to Modify (additions)

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/scripts/context-monitor.sh` `main()` comment at ~362 ("result_token_count already reflects full turn usage — do NOT add TOKENS on top") and `hooks/scripts/context-handoff-sentinel.sh:51` ("result_token_count (accurate)") — encode the defective assumption; rewrite with the code change [Agent 1/2 finding]
- `scripts/little_loops/issue_manager.py:811-819` `_on_usage_writer` — header comment "writes result_token_count to the context state file" and the `state["result_token_count"] = input_tokens + output_tokens` write [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TROUBLESHOOTING.md` — must keep the `hooks/scripts/context-monitor.sh` reference asserted by `test_wiring_guides_and_meta.py:165` (row `FEAT-1459`) when editing ~1165-1170 [Agent 3 finding]
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:309` — describes monitor as "refined against authoritative token counts from the transcript"; consistent with fix, review wording only [Agent 2 finding]
- `site/guides/SESSION_HANDOFF`, `site/development/TROUBLESHOOTING`, `site/ARCHITECTURE`, `site/reference/CONFIGURATION` (generated, incl. `search_index.json`) — mirror the tier text; regenerate rather than hand-edit if the site is tracked [Agent 2 finding]
- `CHANGELOG.md:3271` (ENH-1376 introduced tier 1) — historical, do not edit; add a new entry at release prep only
- Cache-read note: `SESSION_HANDOFF.md` says cache-read is excluded, but `_fire_legacy_usage` includes it — fix while editing the tier-order docs
- No `ll-adapt` mirror change needed (`skills/configure/show-output.md` and its `.gemini`/`.kimi-code`/`.qwen` mirrors do not mention the key); `hooks/adapters/**` has no copy of the priority order

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hooks_integration.py` `TestContextHandoffSentinel.test_sentinel_written_above_threshold` (~3041) — seeds `result_token_count: 0` with `estimated_tokens: 150000`; stays valid if zero/absent means unknown. Also check `test_sentinel_not_written_below_threshold` (~3078) and `test_sentinel_not_written_when_handoff_complete` (~3108), whose fixtures seed the key [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py` `test_impossible_baseline_clamped` (~1262-1278) — seeds `result_token_count=1517046`, exercising the 3x clamp through tier 1; rework to reach the clamp via the transcript-baseline tier [Agent 2 finding]
- `scripts/tests/test_pre_compact.py:277` `test_check_compaction_reads_compacted_at` — script-text grep of `context-monitor.sh`; breaks if `check_compaction` is restructured. `test_pre_compact.py:107` (`context_state_at_compact` snapshot) stays valid [Agent 3 finding]
- `scripts/tests/test_subprocess_utils.py:1735,1760,2689` (`on_usage` sum semantics) — regression anchors for `_fire_legacy_usage`; no change unless it changes. Add a partial-usage case (a `None` field) beside 1760 [Agent 3 finding]
- `scripts/tests/test_issue_manager.py:1910` `test_high_cumulative_usage_does_not_write_sentinel` and the BUG-2280 test (~2150), `scripts/tests/test_worker_pool.py:3405` — regression anchors; they patch `run_with_continuation` and never reach `_on_usage_writer` [Agent 3 finding]
- New: `_on_usage_writer` test driven through `process_issue_inplace` — pattern: `TestReadyIssueErrorHandling.test_forwards_on_usage_detailed_to_ready_issue_call` (`test_issue_manager.py:2252`), `mock_config` fixture (~2196), fake `mock_run(command, *a, **kw)` calling `kw.get("on_usage")`, then read `temp_project_dir/.ll/ll-context-state.json` (path hardcoded, so control `repo_path`) [Agent 3 finding]
- New (monitor): shell-hook tests in `TestContextMonitor` (`test_hooks_integration.py:38`, `test_config` fixture ~47, `tmp_path/"ll-context-state.json"`; multi-step template `test_transcript_baseline_refreshed_on_new_turn` ~1305) for high `result_token_count` + low `estimated_tokens` → no handoff; compaction invalidation (seed `last_compaction` / `.compacted_at`); legacy unqualified key [Agent 3 finding]
- New (sentinel): `TestContextHandoffSentinel` pattern (`monkeypatch.chdir(tmp_path)`, `.ll/ll-config.json` with `context_monitor.sentinel_threshold`, assert `.ll/ll-context-handoff-needed`) for old-format state; plus a monitor/sentinel agreement test with identical seeded state [Agent 3 finding]
- `scripts/tests/test_hook_session_start.py:83` — only session-invalidation coverage (file deletion); extend only if a session/interval tag is introduced
- `scripts/tests/conformance/test_host_conformance.py` (3 hits, self-hosted only, not read) — check what it asserts before finalizing
- No test asserts the `ll-context-crossings.log` line format or the stderr "Context ~N% used ... estimated" text, so a provenance suffix would not break tests (message says "estimated" even for tier 1; revisit wording)

## Program Design

### Types

No new types or state keys. `result_token_count` is retired from `.ll/ll-context-state.json`: no producer writes it and no consumer reads it. Existing keys (`estimated_tokens`, `transcript_baseline_tokens`, etc.) are unchanged. No replacement estimator is required.

### Signatures

- `process_issue_inplace(..., on_usage: Callable[[int, int], None] | None = None, ...)` (`issue_manager.py`) — signature unchanged; the nested `_on_usage_writer` closure is deleted and `on_usage` is forwarded as-is at the ~1347 call site.
- Shell monitor/sentinel entry points remain unchanged; their metric selection changes, not their configured thresholds.

### Call Path

Today (defective):

- `subprocess_utils._fire_legacy_usage` → `issue_manager.process_issue_inplace` nested `_on_usage_writer` → `.ll/ll-context-state.json` key `result_token_count` (written after the child session's Stop cleanup; no budget consumer exists).
- `context-monitor.sh` `main()` and `context-handoff-sentinel.sh` (script body) read the key as tier 1; `check_compaction()` resets other fields but not this one.

After the fix:

- `subprocess_utils._fire_legacy_usage` → caller's `on_usage` (via `process_issue_inplace`) → consumption reporting only; nothing touches the state file.
- `context-monitor.sh` `main()`: transcript baseline + per-tool tokens, else stored `estimated_tokens` + tokens → `USAGE_PERCENT` → pressure levels / handoff threshold.
- `context-handoff-sentinel.sh`: `estimated_tokens` → sentinel threshold → `.ll/ll-context-handoff-needed` → `subprocess_utils.read_sentinel` in `issue_manager` / `parallel/worker_pool.py`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Conventions in force: additive state keys carry no schema or version and are read with jq `// default` (`context-monitor.sh` `main()`, `context-handoff-sentinel.sh`), so absent keys must remain valid. A zero or unlabelled value means unknown, never measured (`subprocess_utils.TokenProvenance` defaults to `"unknown"`). `ctx_stats._fallback_provenance` labels state figures as `estimated_entry(..., scope_kind="context")`.
- Metadata vocabularies that already exist and disagree on time naming: ENH-3538 `TokenUsage` uses `provenance`, `scope_kind`, `observed_at`, `observed_at_basis` (`"event"|"received"`). The ENH-3528 `token_provenance._META_KEYS` uses `observation_time_basis`, `observed_from`, `observed_to`, `stale`. ENH-3545's proposal uses `baseline_observed_at`, `estimate_updated_at`, `stale_reason`, none of which exist in `scripts/` yet. BUG-3587 must record its additive key names against these before implementing.
- Producer identity: `result_token_count` carries no `scope_kind` in the state file, though `_stamp_usage` sets `scope_kind="invocation"` on the in-memory `TokenUsage`. Any qualification must be written by `_on_usage_writer`, since the monitor never writes or clears the key.
- Both hooks must apply the same selection rule. Today the monitor and sentinel each embed their own copy of the priority order, which is how they agree by accident.
- Compaction invalidation is a timestamp handshake (`.compacted_at` in `ll-precompact-state.json` vs state `.last_compaction`, `check_compaction()`). Session invalidation is file deletion only. Any invalidation contract for the key must work inside these two mechanisms, or introduce a session/interval tag on the state file.

### Decision Rules
- N/A — no new decision logic beyond the metric-selection order already described under Call Path.

## Implementation Steps

1. Write failing tests first (TDD): high `result_token_count` + low `estimated_tokens` in the state file → monitor does not hand off and sentinel does not write `.ll/ll-context-handoff-needed`; `process_issue_inplace` with a fake `on_usage` firing does not create or modify `.ll/ll-context-state.json`.
2. Delete `_on_usage_writer` and forward `on_usage` directly in `issue_manager.py`.
3. Remove tier 1 from `context-monitor.sh` and the override from `context-handoff-sentinel.sh`.
4. Rewrite the four defect-encoding tests and `test_impossible_baseline_clamped`; update docs; run project checks.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `hooks/scripts/context-monitor.sh` `main()` — remove tier 1 from the jq/`read` list together and delete the tier-1 branch; re-verify `+ TOKENS` / `overhead` / `SYSTEM_PROMPT_BASELINE` additions now that tier 2/3 is always taken; delete the ~362 comment. Check whether the 3x-`CONTEXT_LIMIT` clamp (~385-387) is still needed — its main target was inflated tier-1 values — and keep it only if the transcript baseline can still exceed it
- Update `hooks/scripts/context-handoff-sentinel.sh` — drop the field from the jq read (~38-44) and shorten the default string to three fields; remove the override (~51-55) and the "accurate" comment
- Update `scripts/little_loops/issue_manager.py` — delete `_on_usage_writer` and its header comment (811-825); pass `on_usage` directly at ~1347
- Update `scripts/tests/test_hooks_integration.py` — invert/replace `test_result_token_count_used_when_present`, `test_result_token_count_zero_falls_back_to_heuristics`, `TestContextHandoffSentinel.test_result_token_count_preferred_over_estimated` so they assert the key is ignored; re-seed `test_impossible_baseline_clamped` through the transcript-baseline tier; drop the key from sentinel fixtures at ~3052/3089/3118 (or keep it as legacy noise to prove it's ignored)
- Add tests: `process_issue_inplace` leaves the state file untouched when `on_usage` fires (pattern: `test_issue_manager.py:2252`); monitor and sentinel ignore a legacy key when seeded with the same state; a stream-json `result` fixture whose `usage` sums several requests' `cache_read_input_tokens` above the context limit, confirming `result.usage` is cumulative across a `-p` run (the premise of the repro)
- Update docs: remove tier 1 from `SESSION_HANDOFF.md` (~359-397), `ARCHITECTURE.md` (~1412-1420), `CONFIGURATION.md` (~532), `TROUBLESHOOTING.md` (~1165-1170; keep the `context-monitor.sh` reference for `test_wiring_guides_and_meta.py:165`). The cache-read inconsistency in `SESSION_HANDOFF.md` disappears with the tier-1 text. Regenerate `site/` copies if tracked

## Impact

- Priority: P2 — incorrect metric selection can prematurely interrupt automated work.
- Risk: Medium — guard behavior intentionally changes, while accounting and threshold configuration must remain stable.

## Steps to Reproduce

1. Feed `process_issue_inplace` a stream-json `result` event whose `usage` block sums several requests (e.g. `input_tokens: 2000`, `cache_read_input_tokens: 600000`, `output_tokens: 8000` against a 200K context limit), as a multi-request `-p` run produces.
2. Observe `_on_usage_writer` writing `result_token_count: 610000` into `.ll/ll-context-state.json` after the child session's Stop cleanup has already deleted the file.
3. In another session sharing the repo root (or by invoking the hooks directly against that state with `estimated_tokens` well below threshold), run `context-monitor.sh` and `context-handoff-sentinel.sh`: the monitor reports ~305% usage (clamped at 3x) and exits 2, and the sentinel writes `.ll/ll-context-handoff-needed`.

## Root Cause

- `scripts/little_loops/issue_manager.py` — `_on_usage_writer`: invocation consumption is stored in the context-state file without metric/scope qualification.
- `hooks/scripts/context-monitor.sh` — `main`: the result-count branch assumes that consumption is an occupancy baseline.
- `hooks/scripts/context-handoff-sentinel.sh` — result-count preference repeats that assumption.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- `result_token_count` has exactly one producer: `_on_usage_writer` (nested in `process_issue_inplace`, `issue_manager.py`). It read-modify-writes `.ll/ll-context-state.json` on every stream-json result event, with no lock and a non-atomic `write_text`. Its path is hardcoded and ignores `context_monitor.state_file`.
- The stored value is `(input_tokens + cache_read_tokens) + output_tokens` for the latest invocation only (`subprocess_utils._fire_legacy_usage`). Cache-creation tokens are excluded. `docs/guides/SESSION_HANDOFF.md` says cache-read is excluded, which does not match this code. The callback does not fire when input, output or cache_read is `None`, so the key is then left unchanged, stale but non-zero.
- The state file has no session-id key. Session scoping comes only from file deletion in `session-start.sh` / `hooks/session_start.py` and `session-cleanup.sh`.
- `context-monitor.sh` `main()` reads `RESULT_TOKEN_COUNT` before `check_compaction()`. Its compaction reset rewrites `estimated_tokens`, `breakdown`, `handoff_complete` and `threshold_crossed_at`, but never touches `result_token_count` or `transcript_baseline_tokens`. A non-zero value keeps tier-1 priority, so the post-compaction estimate is unreachable while it is set.
- Occupancy priority in `main()` is `result_token_count` > transcript baseline + per-tool tokens > stored estimate + tokens. The 3x-`CONTEXT_LIMIT` sanity clamp is the only bound on an inflated value. `context-handoff-sentinel.sh` overrides `estimated_tokens` with `result_token_count` whenever it is > 0.

## Acceptance Criteria

- [ ] `process_issue_inplace` no longer writes `result_token_count` (or any key) to `.ll/ll-context-state.json` when `on_usage` fires; the caller's `on_usage` / `on_usage_detailed` still receive the same values.
- [ ] Given a state file with a high `result_token_count` and low `estimated_tokens`, `context-monitor.sh` does not exit 2 or log a threshold crossing, and `context-handoff-sentinel.sh` does not write `.ll/ll-context-handoff-needed`.
- [ ] Genuine high occupancy (high `estimated_tokens` or transcript baseline) still triggers the monitor handoff and the sentinel at the configured thresholds.
- [ ] `git grep result_token_count -- hooks scripts/little_loops docs` returns no hits (CHANGELOG and `site/` history excepted).
- [ ] Threshold configuration is unchanged; the removed tier and resulting trigger change are documented in the four tier-order docs.
- [ ] No dependency on ENH-3545: this issue adds no state keys, and ENH-3545's AC ("Metadata does not relabel `result_token_count` as measured occupancy") is satisfied trivially.

## Scope Boundaries

- In scope: correcting consumption-as-occupancy decisions and their producers, compatibility, and regression coverage.
- Out of scope: estimator accuracy improvements, threshold tuning, usage ingestion/coverage reconciliation, and ENH-3545's UI metadata implementation.
- Out of scope, capture separately: `session-cleanup.sh` deletes `.ll/ll-context-state.json` on **Stop** (every turn end), which resets the monitor's running estimate each turn and runs in parallel with the Stop sentinel reading the same file. Likewise `check_compaction()` leaves `transcript_baseline_tokens` untouched; confirm it refreshes on the next turn now that tier 2 is the primary path.
- ENH-3545 can land independently; this issue owns behavior changes to occupancy decisions.

## Related Key Documentation

- `docs/guides/SESSION_HANDOFF.md` — context state and handoff behavior.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — monitor and sentinel behavior.

## Status

**Open** | Created: 2026-09-25 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-09-25T02:10:49 - `dd11e427-8257-4f96-897e-d90f77550ff1.jsonl`
- `/ll:refine-issue` - 2026-09-25T02:06:17 - `19d71a6c-75f4-47f1-9198-08c2f11c9949.jsonl`
- `/ll:capture-issue` - 2026-09-25T01:52:41 - `344bbaba-06f1-4c37-b3c7-3b36aa7bfabc.jsonl`

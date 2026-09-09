---
id: ENH-3429
type: ENH
title: Rewire ll-ctx-stats onto the session-discovery seam (Codex cache-rate reader)
priority: P2
status: open
discovered_by: issue-size-review
discovered_date: '2026-09-09'
captured_at: '2026-09-09T21:54:30Z'
labels:
- multi-host
- observability
parent: ENH-3419
blocked_by:
- ENH-3427
blocks: []
relates_to:
- ENH-3420
- FEAT-3417
- ENH-3428
- ENH-3430
---

# ENH-3429: Rewire ll-ctx-stats onto the session-discovery seam (Codex cache-rate reader)

## Summary

Decomposed from ENH-3419 (score 8/11, Very Large). Rewires `cli/ctx_stats.py`'s
`_compute_cache_rate_from_jsonl` to pick its file via `detect_sessions` instead of
`get_sessions_folder` + newest-file glob, and adds a Codex-native cache-rate reader with the
correct cumulative/inclusive-token semantics. Depends on ENH-3427 for `_resolve_host` and the
`--host` flag already registered on `ll-ctx-stats`.

## Parent Issue

Decomposed from ENH-3419: Adopt the session-discovery seam in ll-logs, ll-messages, and
ll-ctx-stats (Codex observability).

## Current Behavior

`_compute_cache_rate_from_jsonl(cwd) -> dict[str, Any] | None` (`cli/ctx_stats.py:342`, called
from `main_ctx_stats` at ~753) calls `get_sessions_folder(cwd)` (355), picks the newest non-
`agent-*` file, sums Claude-shaped `message.usage` keys (`cache_read_input_tokens`,
`cache_creation_input_tokens`, `input_tokens`), and returns `{cache_read, cache_write, uncached,
hit_rate_pct}`, consumed by the text renderer (~473-477) and JSON renderer (~598-601).

## Proposed Solution

1. **File selection only through the seam**: pick the newest non-agent handle for the resolved
   host (or across hosts when `None`) via `detect_sessions(cwd, host, include_agents=False,
   limit=1)`. For every **non-codex** host, keep today's raw per-line reader
   (`ctx_stats.py:381-403`) on `handle.path` — do **not** route usage through `iter_events`. The
   qwen/gemini normalizers strip `message.usage` entirely (`normalize_qwen_record` drops any
   record lacking `parts`; `normalize_gemini_session` yields only `user`/`gemini` types), so the
   existing qwen/gemini tests (`test_cli_ctx_stats.py:909,941`) would break if routed through
   `iter_events`. Record this consequence in the reader's docstring: real qwen/gemini/omp cache
   rates are unreachable through the normalizers today; a native usage reader is a follow-up.
   `iter_events` is used for the **codex branch only**.
2. **Codex reader** (`_codex_cache_usage`): `event_msg.payload.type == "token_count"` records carry
   `payload.info.total_token_usage`/`last_token_usage`. `total_token_usage` is **cumulative** —
   sum `last_token_usage` across every `token_count` event (never sum `total_token_usage`, which
   would misbehave across a mid-session compaction reset). Codex `input_tokens` is **inclusive** of
   cached and cache-write tokens, so `uncached = input_tokens - cached_input_tokens -
   cache_write_input_tokens`, `cache_read = cached_input_tokens`, `cache_write =
   cache_write_input_tokens` (applying the Claude formula verbatim double-counts cached tokens).
3. **Fail-soft rules**: return `None` when no `token_count` event is seen at all (0.130.0 rollouts
   carry none — 399/400 of the newest local corpus), exactly as the Claude reader returns `None` on
   `total == 0`. Skip any `token_count` event whose `payload.info` is `null` (rate-limit-only
   events); add a synthetic fixture case for it.
4. **Return shape**: keep the same four keys (renderers untouched); add one additive key, `host`
   (the `handle.host` the rate was read from) — under the union default, `limit=1` picks the
   newest session across hosts, so the JSON renderer should surface which host it came from.
5. **Docs**: record the Codex cache-rate key semantics in the reader's docstring and in
   `docs/reference/HOST_COMPATIBILITY.md` next to `[^tok-codex]` (the complementary `codex exec
   --json` `turn.completed` source), including that the cache line appears only for sessions from a
   CLI version that emits `token_count` (0.152.1 confirmed; 0.130.0 does not).

## Files to Modify

- `scripts/little_loops/cli/ctx_stats.py` (`_compute_cache_rate_from_jsonl` 342-355,
  `main_ctx_stats` ~753)
- `docs/reference/HOST_COMPATIBILITY.md` (Codex cache-rate key semantics next to `[^tok-codex]`)

### Tests

- `scripts/tests/test_cli_ctx_stats.py::TestComputeCacheRateFromJsonl` (676-974) — add
  `test_resolves_codex_rollout_cache_rate` beside the qwen (909)/gemini (941) pairs, asserting
  against the fixture's last (4th) `token_count` event: `input_tokens=84003,
  cached_input_tokens=57915, cache_write_input_tokens=26076` → `uncached=12`, `hit_rate_pct == 69`
  (the reader `round()`s to an int at `ctx_stats.py:415` — assert `== 69`, not `≈ 68.9`); the sum of
  `last_token_usage.input_tokens` across all four events (`14002+21854+22068+26079=84003`)
  independently confirms the cumulative semantics.
- Add a no-`token_count` → `None` case and an `info: null`-skipped case.
- The qwen/gemini pair (`test_cli_ctx_stats.py:909,941`) must pass unmodified — they depend on the
  non-codex branch keeping the raw per-line reader.

## Acceptance Criteria

- `ll-ctx-stats` obtains its file via `detect_sessions` (limit=1) and uses `iter_events` for the
  codex branch only; every other host keeps the raw per-line reader on `handle.path`.
- `ll-ctx-stats` under Codex reports `hit_rate_pct` computed by summing `last_token_usage` across
  every `token_count` event, with `uncached = input_tokens - cached_input_tokens -
  cache_write_input_tokens`; the fixture-derived test value matches (`hit_rate_pct == 69`).
- A rollout with no `token_count` event yields `None` (cache line absent, JSON `cache_hit_rate`
  null); `token_count` events with `info: null` are skipped — both test-asserted.
- The four existing return keys and both renderers (text ~473-477, JSON ~598-601) are unchanged;
  the JSON output carries the additive `host` key naming the session's source host.
- Claude Code output for every existing test in `test_cli_ctx_stats.py` (including the qwen/gemini
  cache-rate pair) is unchanged.
- `docs/reference/HOST_COMPATIBILITY.md` documents the Codex cache-rate key semantics next to
  `[^tok-codex]`.

## Dependencies

Blocked by ENH-3427 (host-resolution seam). Independent of ENH-3428/ENH-3430 (disjoint files —
touches `cli/ctx_stats.py` only).

## Status

**Open** | Created: 2026-09-09 | Priority: P2


## Session Log
- `/ll:issue-size-review` - 2026-09-09T21:57:08 - `0ecdfd2a-1186-4e76-ae8e-586f75aad086.jsonl`

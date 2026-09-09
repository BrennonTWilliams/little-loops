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
learning_tests_required:
- codex
---

# ENH-3429: Rewire ll-ctx-stats onto the session-discovery seam (Codex cache-rate reader)

## Summary

Decomposed from ENH-3419 (score 8/11, Very Large). Rewires `cli/ctx_stats.py`'s
`_compute_cache_rate_from_jsonl` to pick its file via `session_store/sessions.py`'s
`detect_sessions` instead of `little_loops/user_messages.py`'s `get_sessions_folder` + newest-file glob, and
adds a Codex-native cache-rate reader with the correct cumulative/inclusive-token semantics.
Depends on ENH-3427 for `_resolve_host` and the `--host` flag already registered on
`ll-ctx-stats`.

## Parent Issue

Decomposed from ENH-3419: Adopt the session-discovery seam in ll-logs, ll-messages, and
ll-ctx-stats (Codex observability).

## Current Behavior

`_compute_cache_rate_from_jsonl(cwd) -> dict[str, Any] | None` (`cli/ctx_stats.py:342`, called
from `main_ctx_stats` at ~753) calls `get_sessions_folder(cwd)` (355), picks the newest non-
`agent-*` file, sums Claude-shaped `message.usage` keys (`cache_read_input_tokens`,
`cache_creation_input_tokens`, `input_tokens`), and returns `{cache_read, cache_write, uncached,
hit_rate_pct}`, consumed by the text renderer (~473-477) and JSON renderer (~598-601).

## Expected Behavior

`_compute_cache_rate_from_jsonl` picks its file via `detect_sessions(cwd, host,
include_agents=False, limit=1)` instead of `get_sessions_folder` + newest-file glob, so
`ll-ctx-stats` gets its cache-rate handle from the same session-discovery seam as `ll-logs` and
`ll-messages`. For non-Codex hosts the raw per-line reader keeps computing `cache_read`,
`cache_write`, `uncached`, and `hit_rate_pct` exactly as today. For Codex, a new
`_codex_cache_usage` reader derives the same four keys from `token_count` events read via
`iter_events`, correctly treating `total_token_usage` as cumulative (summing `last_token_usage`
instead) and `input_tokens` as inclusive of cached/cache-write tokens. The JSON renderer gains one
additive `host` key naming which host the rate was read from; both renderers and all four existing
return keys are otherwise unchanged.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Confirmed via code-graph query (`ll-code callers-of _compute_cache_rate_from_jsonl`): its only caller is `main_ctx_stats` (`cli/ctx_stats.py:753`); the only importers of `cli/ctx_stats.py` are `cli/__init__.py:58` and `scripts/tests/test_cli_ctx_stats.py:13`. No other call site depends on the current single-arg signature.
- Confirmed the existing fixture `scripts/tests/fixtures/codex/rollout-interactive.jsonl` already contains 4 `token_count` events; its 4th (last) event matches the values cited in this issue's Tests section exactly (`total_token_usage.input_tokens=84003, cached_input_tokens=57915, cache_write_input_tokens=26076`), and the sum of `last_token_usage.input_tokens` across all four events is `14002+21854+22068+26079=84003`. `test_resolves_codex_rollout_cache_rate` can point at this existing fixture — no new fixture file needs to be authored.
- Confirmed the current `_compute_cache_rate_from_jsonl(cwd: Path) -> dict[str, Any] | None` (`cli/ctx_stats.py:340-410`) matches this issue's Current Behavior description exactly: calls `get_sessions_folder(cwd)`, globs non-`agent-*` `*.jsonl` files, takes the newest by `st_mtime`, sums `cache_read_input_tokens`/`cache_creation_input_tokens`/`input_tokens` from `message.usage` on `type == "assistant"` records deduplicated by `uuid`, and returns `round(cache_read / total * 100)` as `hit_rate_pct`.
- Confirmed `ENH-3427` (this issue's `blocked_by`) is still `open`, and `cli/ctx_stats.py` has no `--host` flag or `_resolve_host` call yet (`grep -n "_resolve_host\|--host" cli/ctx_stats.py` — no hits) — the `blocked_by: [ENH-3427]` edge is accurate and current.

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

## Program Design

### Types

- No new types — reuses `SessionHandle` (`session_store/sessions.py`) and the existing
  `dict[str, Any] | None` cache-rate return shape (`cache_read`, `cache_write`, `uncached`,
  `hit_rate_pct`, plus additive `host`).

### Signatures

- `_compute_cache_rate_from_jsonl(cwd: Path, host: str | None) -> dict[str, Any] | None`
  (`cli/ctx_stats.py:342`, signature gains `host` to thread through `_resolve_host` from ENH-3427)
- `_codex_cache_usage(handle: SessionHandle) -> dict[str, Any] | None` (new, `cli/ctx_stats.py`)
- `detect_sessions(cwd: Path, host: str | None = None, *, include_agents: bool = False, limit:
  int | None = None, home: Path | None = None) -> list[SessionHandle]`
  (`session_store/sessions.py:291`)
- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` (`session_store/sessions.py:824`)

### Call Path

`main_ctx_stats` -> `_compute_cache_rate_from_jsonl` -> `detect_sessions` -> (codex branch)
`_codex_cache_usage` -> `iter_events`; (non-codex branch) existing raw per-line reader on
`handle.path`.

## Scope Boundaries

- **In scope**: routing file selection through `detect_sessions`; adding the Codex `token_count`
  cache-rate reader; the additive `host` JSON key; docs for the Codex key semantics.
- **Out of scope**: qwen/gemini/omp native usage readers — their normalizers strip `message.usage`
  entirely, so real cache rates for those hosts stay unreachable through `iter_events` until a
  follow-up adds native usage readers for them (tracked as a documented limitation, not a new
  issue here). Also out of scope: any change to the text/JSON renderer layout beyond the additive
  `host` key, and any change to `main_ctx_stats`'s `--host` flag itself (delivered by ENH-3427).

## Impact

- **Priority**: P2 - decomposed from ENH-3419 (score 8/11, Very Large); observability parity for
  Codex is valuable but not blocking any other in-flight work once ENH-3427 lands.
- **Effort**: Small - single-file change (`cli/ctx_stats.py`) reusing the seam ENH-3427 already
  wires up; the Codex reader is a self-contained function with fixture-derived test values already
  specified.
- **Risk**: Low - non-codex hosts keep their existing raw per-line reader untouched (explicitly
  not routed through `iter_events`), so the qwen/gemini/omp test suite is unaffected; the codex
  branch is new code, not a rewrite of a working path.
- **Breaking Change**: No - all four existing return keys and both renderers are unchanged; `host`
  is purely additive.

## Dependencies

Blocked by ENH-3427 (host-resolution seam). Independent of ENH-3428/ENH-3430 (disjoint files —
touches `cli/ctx_stats.py` only).

## Status

**Open** | Created: 2026-09-09 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-09-09T22:40:45 - `a5a46f1d-6d28-431d-9f96-7d68b9b6445d.jsonl`
- `/ll:format-issue` - 2026-09-09T22:05:58 - `1744c85d-b425-4d1c-b20e-c1e871e66aec.jsonl`
- `/ll:issue-size-review` - 2026-09-09T21:57:08 - `0ecdfd2a-1186-4e76-ae8e-586f75aad086.jsonl`

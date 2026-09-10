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
blocked_by: []
blocks: []
relates_to:
- ENH-3420
- FEAT-3417
- ENH-3428
- ENH-3430
learning_tests_required:
- codex-rollout
confidence_score: 100
outcome_confidence: 95
score_complexity: 23
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 22
---

# ENH-3429: Rewire ll-ctx-stats onto the session-discovery seam (Codex cache-rate reader)

## Summary

Decomposed from ENH-3419 (score 8/11, Very Large). Rewires `cli/ctx_stats.py`'s
`_compute_cache_rate_from_jsonl` to pick its file via `session_store/sessions.py`'s
`detect_sessions` instead of `little_loops/user_messages.py`'s `get_sessions_folder` + newest-file glob, and
adds a Codex-native cache-rate reader with the correct cumulative/inclusive-token semantics.
ENH-3427 (now done) already registered `_resolve_host` and the `--host` flag on
`ll-ctx-stats`; this issue is the follow-on that consumes it.

## Parent Issue

Decomposed from ENH-3419: Adopt the session-discovery seam in ll-logs, ll-messages, and
ll-ctx-stats (Codex observability).

## Current Behavior

`_compute_cache_rate_from_jsonl(cwd) -> dict[str, Any] | None` (`cli/ctx_stats.py:344`, called
from `main_ctx_stats` at ~753) calls `get_sessions_folder(cwd)` (355), picks the newest non-
`agent-*` file, sums Claude-shaped `message.usage` keys (`cache_read_input_tokens`,
`cache_creation_input_tokens`, `input_tokens`), and returns `{cache_read, cache_write, uncached,
hit_rate_pct}`, consumed by the text renderer (~473-477) and JSON renderer (~598-601).

## Expected Behavior

`_compute_cache_rate_from_jsonl` picks its file via `detect_sessions(cwd, host,
include_agents=False, limit=1)` instead of `get_sessions_folder` + newest-file glob, so
`ll-ctx-stats` gets its cache-rate handle from the same session-discovery seam as `ll-logs` and
`ll-messages`. `main_ctx_stats` resolves `host` as `_resolve_host(args.host, default=None)`
(flag > `LL_HOOK_HOST` > union), the same call shape `cli/messages.py` uses. For non-Codex hosts
the raw per-line reader keeps computing `cache_read`, `cache_write`, `uncached`, and
`hit_rate_pct` exactly as today. For Codex, a new `_codex_cache_usage` reader derives the same
four keys from `token_count` events read via `iter_events`, correctly treating
`total_token_usage` as cumulative (summing `last_token_usage` instead) and `input_tokens` as
inclusive of cached/cache-write tokens.

Because the union default picks the newest session *across hosts*, both renderers must say where
the rate came from: the return dict gains an additive `host` key (the `handle.host`), the JSON
payload surfaces it as `cache_rate_host` (not bare `host`, which would read as "the host that ran
`ll-ctx-stats`" next to the flat `cache_*_tokens` keys), and the text line gains a ` [<host>]`
suffix whenever `host != "claude-code"`. All four existing return keys and the existing text/JSON
key names are unchanged.

Adopting the seam must not reintroduce the BUG-2489 TOCTOU race the current inline reader guards
against: `detect_sessions`'s three discovery paths call `.stat().st_mtime` unguarded, so this issue
adds the `OSError` guard there (skip the file) as the seam's first consumer that cares.

## Proposed Solution

1. **File selection only through the seam**: in `main_ctx_stats`, resolve
   `host = _resolve_host(args.host, default=None)` (import from `little_loops.user_messages`,
   as `cli/messages.py` and `cli/session.py:633` do) and pass it to
   `_compute_cache_rate_from_jsonl(cwd, host)`. There, pick the newest non-agent handle for the
   resolved host (or across hosts when `None`) via `detect_sessions(cwd, host,
   include_agents=False, limit=1)`; drop the `get_sessions_folder` import from `ctx_stats.py`
   (`session_log.py` still uses it — leave that alone). For every **non-codex** host, keep today's
   raw per-line reader
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
   cached and cache-write tokens, so `uncached = max(0, input_tokens - cached_input_tokens -
   cache_write_input_tokens)`, `cache_read = cached_input_tokens`, `cache_write =
   cache_write_input_tokens` (applying the Claude formula verbatim double-counts cached tokens).
   The `max(0, ...)` clamp guards against a future CLI version switching `input_tokens` to
   exclusive, which would otherwise print a hit rate above 100%. Event shape as seen through
   `iter_events`: `SessionEvent.type == "event_msg"` and `SessionEvent.payload` is the record's
   `payload` dict, so the filter is `ev.type == "event_msg" and ev.payload.get("type") ==
   "token_count"` and the usage lives at `ev.payload["info"]`.
3. **Fail-soft rules**: return `None` when no `token_count` event is seen at all (0.130.0 rollouts
   carry none — 399/400 of the newest local corpus), exactly as the Claude reader returns `None` on
   `total == 0`. Skip any `token_count` event whose `payload.info` is `null` (rate-limit-only
   events); add a synthetic fixture case for it.
4. **Return shape and renderers**: keep the same four keys; add one additive key, `host` (the
   `handle.host` the rate was read from). Under the union default, `limit=1` picks the newest
   session across hosts, so both renderers surface it:
   - JSON (`_print_json`, sqlite branch only — the fallback branch has never carried cache-rate
     keys): add `"cache_rate_host": cache_rate["host"] if cache_rate else None` beside the
     existing `cache_*_tokens` keys. Do **not** name it bare `host`.
   - Text (`_render`, ~473-477): append ` [<host>]` to the `Cache hit rate:` line when
     `cache_rate["host"] != "claude-code"`; the Claude Code line is byte-identical to today.
5. **BUG-2489 guard in the seam**: wrap the `path.stat().st_mtime` calls in
   `_detect_codex_sessions`' rollout scan (`sessions.py:200`), `_detect_claude_sessions`
   (`:266`), and `_detect_layout_sessions` (`:457`) in `try/except OSError: continue`. The current
   inline reader in `ctx_stats.py:365-373` carries this guard; routing through the seam would
   silently drop it otherwise. Add one test per path that deletes a file between glob and stat
   (monkeypatch `Path.stat` to raise `OSError` for one name) and asserts the remaining handles
   are returned.
6. **Learning test**: the existing `codex-rollout` record only proves `token_count` events *exist*
   on 0.152.1. Extend it (via `/ll:explore-api` against a local 0.152.1 rollout) with three
   assertions this issue's math depends on: `total_token_usage` is cumulative (each event's value
   equals the running sum of `last_token_usage`), `last_token_usage.input_tokens >=
   cached_input_tokens + cache_write_input_tokens` (inclusive), and `info: null` occurs on
   rate-limit-only `token_count` events. Frontmatter `learning_tests_required` now names
   `codex-rollout`, not `codex` (the MCP-config target), so `/ll:confidence-check` gates on the
   right record.
7. **Docs**: record the Codex cache-rate key semantics in the reader's docstring and in
   `docs/reference/HOST_COMPATIBILITY.md` next to `[^tok-codex]` (the complementary `codex exec
   --json` `turn.completed` source), including that the cache line appears only for sessions from a
   CLI version that emits `token_count` (0.152.1 confirmed; 0.130.0 does not). In
   `docs/reference/CLI.md` § `ll-ctx-stats`: update the `--host` bullet's "not yet consumed by
   session enumeration (ENH-3427)" clause to describe what it now selects, and add
   `cache_rate_host` to the `--json` bullet's key list.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- **Correction — ENH-3427 landed since the prior refine pass**: `ll-issues show ENH-3427` now reports `status: done` (`completed_at: '2026-09-10T01:17:37Z'`), which postdates this issue's own prior `/ll:refine-issue` pass (Session Log `2026-09-09T22:40:45`) — the finding above claiming ENH-3427 "is still `open`" was accurate when written but is now stale. `ll-ctx-stats` already has `--host` registered via `add_host_arg(parser)` (`cli/ctx_stats.py:76`), also contradicting that finding's "no `--host` flag" claim. The flag is parsed but never consumed: no `args.host` reference exists anywhere in `main_ctx_stats()` or `_compute_cache_rate_from_jsonl` (confirmed by grep of `cli/ctx_stats.py`, matches beyond line 76 are only docstring/comment mentions at 348-349, 365).
- **Convention already in force**: `cli/session.py:633-635` already consumes the seam ENH-3427 landed — `_backfill_host: str = _resolve_host(args.host, default="claude-code")` after `add_host_arg(parser)` registration — the pattern `main_ctx_stats` will follow to read `args.host` and thread it into `_compute_cache_rate_from_jsonl`.
- **Remaining work is unchanged**: threading `args.host` into `_compute_cache_rate_from_jsonl` and routing file selection through `detect_sessions` are still undone (`ctx_stats.py` has zero references to either `detect_sessions` or `iter_events`). Only the *blocking* status changes — see Dependencies section.

## Files to Modify

- `scripts/little_loops/cli/ctx_stats.py` (`_compute_cache_rate_from_jsonl` 344-418,
  `main_ctx_stats` ~755, `_render` ~473-477, `_print_json` ~598-601)
- `scripts/little_loops/session_store/sessions.py` (BUG-2489 `OSError` guard around the three
  `.stat().st_mtime` calls at 200/266/457)
- `scripts/tests/test_cli_ctx_stats.py` (migrate 8 `get_sessions_folder` patches; new codex cases)
- `scripts/tests/test_session_discovery.py` (three stat-race cases for `detect_sessions`)
- `docs/reference/HOST_COMPATIBILITY.md` (Codex cache-rate key semantics next to `[^tok-codex]`)
- `docs/reference/CLI.md` § `ll-ctx-stats` (`--host` bullet at ~478 no longer "not yet consumed";
  `cache_rate_host` in the `--json` key list)
- `.ll/learning-tests/` `codex-rollout` record (three new assertions, see Proposed Solution §6)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:3523` — the `get_sessions_folder` doc entry states this function is used
  "whenever you glob `*.jsonl` non-recursively... the `get_current_session_jsonl`,
  `fsm.continuity`, and `ll-ctx-stats` cache-rate call sites all resolve through it." Once
  `ctx_stats.py` drops the `get_sessions_folder` import (Proposed Solution §1), the `ll-ctx-stats`
  clause becomes false — remove it from this sentence. [Agent 2 finding]

### Tests

- **Existing `TestComputeCacheRateFromJsonl` tests need a mechanical migration, not a rewrite.**
  10 of its 12 tests (`test_cli_ctx_stats.py:687,693,730,746,769,808,845,871,893,916`) patch
  `little_loops.cli.ctx_stats.get_sessions_folder`. Once the reader routes through
  `detect_sessions`, that patch is dead: the call falls through to the real `Path.home()`, finds
  no project folder, and returns `None`. Replace each with
  `patch("little_loops.cli.ctx_stats.detect_sessions", return_value=[SessionHandle(host="claude-code",
  session_id=..., path=project_folder / "session.jsonl", cwd=tmp_path, updated_at=...)])` (or
  `[]` for the `None`-folder case at 687), and pass `host=None` (or `"claude-code"`) as the new
  second argument. **Every assertion in those tests stays byte-identical** — that is the
  regression guarantee, not "tests unmodified". The newest-file-wins test (~730) should assert
  that only the first handle is read, since `limit=1` now does the ordering.
- The qwen (921)/gemini (953) pair genuinely pass unmodified apart from the added argument: they
  monkeypatch `Path.home` and set `LL_HOOK_HOST`, so `_resolve_host` → `detect_sessions` →
  `_detect_layout_sessions` resolves the same `chats/` dir through the real chain. They depend on
  the non-codex branch keeping the raw per-line reader.
- Add `test_resolves_codex_rollout_cache_rate` beside the qwen/gemini pair, pointing
  `detect_sessions` (patched, or via `Path.home` monkeypatch + a copied fixture) at
  `scripts/tests/fixtures/codex/rollout-interactive.jsonl` and asserting against the fixture's
  last (4th) `token_count` event: `input_tokens=84003, cached_input_tokens=57915,
  cache_write_input_tokens=26076` → `uncached=12`, `hit_rate_pct == 69`, `host == "codex"` (the
  reader `round()`s to an int at `ctx_stats.py:417` — assert `== 69`, not `≈ 68.9`); the sum of
  `last_token_usage.input_tokens` across all four events (`14002+21854+22068+26079=84003`)
  independently confirms the cumulative semantics.
- Add a no-`token_count` → `None` case, an `info: null`-skipped case, and a negative-`uncached`
  clamp case (synthetic event with `input_tokens < cached + cache_write` → `uncached == 0`).
- Renderer cases: JSON payload carries `cache_rate_host` (`"codex"` for the fixture, `None` when
  `cache_rate` is `None`); text line ends in ` [codex]` for a codex handle and is byte-identical
  to today for a claude-code handle.
- `sessions.py` stat-race cases: one per discovery path (codex rollout scan, claude, layout);
  monkeypatch `Path.stat` to raise `OSError` for one filename and assert the other handles are
  still returned.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Confirmed via code-graph query (`ll-code callers-of _compute_cache_rate_from_jsonl`): its only caller is `main_ctx_stats` (`cli/ctx_stats.py:753`); the only importers of `cli/ctx_stats.py` are `cli/__init__.py:58` and `scripts/tests/test_cli_ctx_stats.py:13`. No other call site depends on the current single-arg signature.
- Confirmed the existing fixture `scripts/tests/fixtures/codex/rollout-interactive.jsonl` already contains 4 `token_count` events; its 4th (last) event matches the values cited in this issue's Tests section exactly (`total_token_usage.input_tokens=84003, cached_input_tokens=57915, cache_write_input_tokens=26076`), and the sum of `last_token_usage.input_tokens` across all four events is `14002+21854+22068+26079=84003`. `test_resolves_codex_rollout_cache_rate` can point at this existing fixture — no new fixture file needs to be authored.
- Confirmed the current `_compute_cache_rate_from_jsonl(cwd: Path) -> dict[str, Any] | None` (`cli/ctx_stats.py:344-418`) matches this issue's Current Behavior description exactly: calls `get_sessions_folder(cwd)`, globs non-`agent-*` `*.jsonl` files, takes the newest by `st_mtime`, sums `cache_read_input_tokens`/`cache_creation_input_tokens`/`input_tokens` from `message.usage` on `type == "assistant"` records deduplicated by `uuid`, and returns `round(cache_read / total * 100)` as `hit_rate_pct`.

_Added by review — 2026-09-09:_

- `parse_codex_rollout` (`sessions.py:641-684`) yields `SessionEvent(type=<top-level type>, payload=<record["payload"]>)`, so `token_count` events arrive as `type == "event_msg"` with `payload["type"] == "token_count"` and `payload["info"]` holding the usage — the filter in Proposed Solution §2 matches this.
- `detect_sessions` calls `.stat().st_mtime` unguarded at `sessions.py:200,266,457`; only `ctx_stats.py:365-373` and `session_log.py:291` carry the BUG-2489 guard. Adopting the seam without §5 would regress BUG-2489.
- `_print_json` (`ctx_stats.py:560-620`) is flat: `cache_hit_rate_pct`, `cache_read_tokens`, `cache_write_tokens`, `uncached_tokens` sit beside `source`, `bytes_*`, `skill_health`. Only the `source == "sqlite"` branch carries cache-rate keys; the fallback branch never has.
- `ll-learning-tests list` shows `codex-rollout`'s only `token_count` assertion is existence on 0.152.1; the `codex` target this issue previously named covers MCP TOML config, not rollouts.
- `docs/reference/CLI.md:476` still documents `--host` as "Additive and not yet consumed by session enumeration (ENH-3427)" — stale once this lands.

## Acceptance Criteria

- `main_ctx_stats` resolves `host` via `_resolve_host(args.host, default=None)` and
  `_compute_cache_rate_from_jsonl(cwd, host)` obtains its file via `detect_sessions` (limit=1),
  using `iter_events` for the codex branch only; every other host keeps the raw per-line reader on
  `handle.path`. `ctx_stats.py` no longer imports `get_sessions_folder`.
- `ll-ctx-stats` under Codex reports `hit_rate_pct` computed by summing `last_token_usage` across
  every `token_count` event, with `uncached = max(0, input_tokens - cached_input_tokens -
  cache_write_input_tokens)`; the fixture-derived test value matches (`hit_rate_pct == 69`).
- A rollout with no `token_count` event yields `None` (cache line absent, JSON
  `cache_hit_rate_pct` null); `token_count` events with `info: null` are skipped; a synthetic
  event with `input_tokens < cached + cache_write` clamps `uncached` to 0 — all test-asserted.
- The four existing return keys and the existing text/JSON key names are unchanged. The return
  dict carries an additive `host` key; the JSON payload surfaces it as `cache_rate_host` (never
  bare `host`); the text line gains a ` [<host>]` suffix only when `host != "claude-code"`.
- Every pre-existing assertion in `test_cli_ctx_stats.py::TestComputeCacheRateFromJsonl` passes
  with only the patch target (`get_sessions_folder` → `detect_sessions`) and the added `host`
  argument changed; the qwen/gemini pair passes with only the added argument.
- `detect_sessions` skips (rather than raises on) a file that disappears between glob and stat in
  all three discovery paths — test-asserted per path (BUG-2489 parity).
- The `codex-rollout` learning test record carries passing assertions for cumulative
  `total_token_usage`, inclusive `input_tokens`, and `info: null` occurrence.
- `docs/reference/HOST_COMPATIBILITY.md` documents the Codex cache-rate key semantics next to
  `[^tok-codex]`; `docs/reference/CLI.md` § `ll-ctx-stats` no longer says `--host` is unconsumed
  and lists `cache_rate_host` under `--json`.

## Program Design

### Types

- No new types — reuses `SessionHandle` (`session_store/sessions.py`) and the existing
  `dict[str, Any] | None` cache-rate return shape (`cache_read`, `cache_write`, `uncached`,
  `hit_rate_pct`, plus additive `host`).

### Signatures

- `_compute_cache_rate_from_jsonl(cwd: Path, host: str | None) -> dict[str, Any] | None`
  (`cli/ctx_stats.py:344`, signature gains `host` to thread through `_resolve_host` from ENH-3427)
- `_codex_cache_usage(handle: SessionHandle) -> dict[str, Any] | None` (new, `cli/ctx_stats.py`)
- `_resolve_host(flag: str | None, *, default: None = None) -> str | None`
  (`user_messages.py:383`, existing)
- `detect_sessions(cwd: Path, host: str | None = None, *, include_agents: bool = False, limit:
  int | None = None, home: Path | None = None) -> list[SessionHandle]`
  (`session_store/sessions.py:297`, unchanged signature; gains `OSError` guard on stat)
- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` (`session_store/sessions.py:834`)

### Call Path

`main_ctx_stats` -> `_resolve_host(args.host, default=None)` -> `_compute_cache_rate_from_jsonl(cwd,
host)` -> `detect_sessions(cwd, host, include_agents=False, limit=1)` -> (codex branch)
`_codex_cache_usage` -> `iter_events`; (non-codex branch) existing raw per-line reader on
`handle.path`. Result dict (four keys + `host`) -> `_render` (text suffix) / `_print_json`
(`cache_rate_host`).

## Scope Boundaries

- **In scope**: consuming `--host` in `main_ctx_stats`; routing file selection through
  `detect_sessions`; adding the Codex `token_count` cache-rate reader; the additive `host` return
  key surfaced as `cache_rate_host` (JSON) and a ` [<host>]` suffix (text, non-claude-code only);
  the BUG-2489 `OSError` guard inside `detect_sessions`; the three `codex-rollout` learning-test
  assertions; docs for the Codex key semantics and the `--host`/`--json` bullets in CLI.md.
- **Out of scope**: qwen/gemini/omp native usage readers — their normalizers strip `message.usage`
  entirely, so real cache rates for those hosts stay unreachable through `iter_events` until a
  follow-up adds native usage readers for them (tracked as a documented limitation, not a new
  issue here). Also out of scope: any other change to the text/JSON renderer layout, any change to
  the `--host` flag's registration or choices (delivered by ENH-3427), and `session_log.py`'s own
  `get_sessions_folder` use (it keeps its inline BUG-2489 guard; migrating it to the seam is a
  separate issue).

## Impact

- **Priority**: P2 - decomposed from ENH-3419 (score 8/11, Very Large); observability parity for
  Codex is valuable but not blocking any other in-flight work once ENH-3427 lands.
- **Effort**: Small-to-Medium - the `ctx_stats.py` change reuses the seam ENH-3427 already
  wires up and the Codex reader is a self-contained function with fixture-derived test values;
  the extra cost is the mechanical migration of 8 test patches, a three-line guard in
  `sessions.py` with three tests, and one learning-test extension.
- **Risk**: Low - non-codex hosts keep their existing raw per-line reader untouched (explicitly
  not routed through `iter_events`), so the qwen/gemini/omp assertions are unaffected; the codex
  branch is new code, not a rewrite of a working path. The one real regression hazard (BUG-2489
  stat race) is addressed in-issue rather than inherited.
- **Breaking Change**: No - all four existing return keys and the existing text/JSON key names are
  unchanged; `host` / `cache_rate_host` and the non-claude-code text suffix are purely additive.

## Dependencies

No open blocker — ENH-3427 (host-resolution seam) is `done`. Independent of ENH-3428/ENH-3430
at the file level (`cli/ctx_stats.py`, `sessions.py`'s stat guard, and the ctx-stats tests are
untouched by either). One soft coupling: ENH-3428's in-flight working-tree edits to
`user_messages.py` keep `_resolve_host` and `get_sessions_folder` intact, so this issue can land
before or after it; do not remove `get_sessions_folder` here (`session_log.py` still imports it).
Parent ENH-3419 is already `done` (closed as decomposed); `parent:` on a non-EPIC does not roll
up, so this issue's completion is tracked on its own.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- **Blocker resolved**: ENH-3427 is `done` (`completed_at: 2026-09-10T01:17:37Z`) — `blocked_by` edge cleared accordingly (this refine pass). `--host` is already registered on `ll-ctx-stats` (`ctx_stats.py:76`) but unconsumed downstream; wiring it up is exactly what this issue's Proposed Solution completes. No remaining hard dependency.

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the
issue as it now reads is up to date — this section is a record of what was wrong and fixed, not
an outstanding action item).

- **Graph**: provider=`codegraph` freshness=`stale` — no graph-assisted checks were used to
  originate a verdict; all findings below were confirmed directly against the working tree.
- All signatures, call paths, line ranges for the seam functions (`detect_sessions`,
  `_detect_codex_sessions`/`_detect_claude_sessions`/`_detect_layout_sessions`, `iter_events`,
  `parse_codex_rollout`, `_resolve_host`), the BUG-2489 `.stat()` call sites (`sessions.py:200,
  266, 457`), the qwen/gemini normalizer behavior, the fixture-derived cumulative-sum math
  (`hit_rate_pct == 69`, `uncached == 12`), the codex-rollout learning-test record's existing
  assertions, dependency graph (ENH-3427 done, no open blocker), decisions log (no active
  required rules), and evidence quotes (`ll-verify-evidence` clean) all check out against current
  code.
- Fixed four stale citations: `_compute_cache_rate_from_jsonl`'s Current Behavior line cite
  (342 → 344); the test-migration count and line list ("8 of its 10 tests" → "10 of its 12
  tests" — the class has 12 tests total, 10 patching `get_sessions_folder` plus the qwen/gemini
  pair that don't); the qwen/gemini test line numbers (909/941 → actual 921/953); and the
  `docs/reference/CLI.md` `--host` bullet line cite (478 → 476).

## Status

**Open** | Created: 2026-09-09 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-10T02:52:23 - `756850bc-9733-44c4-8072-7050bfbe2c2c.jsonl`
- `/ll:verify-issues` - 2026-09-10T02:48:32 - `ccf4b116-f388-4b46-b017-1735a236d98c.jsonl`
- `/ll:wire-issue` - 2026-09-10T02:41:27 - `7404ab20-8130-4df4-a992-c730bf1293b4.jsonl`
- `/ll:refine-issue` - 2026-09-10T02:25:21 - `39c793f2-5060-4772-946d-1b90fa8dc829.jsonl`
- `/ll:refine-issue` - 2026-09-09T22:40:45 - `a5a46f1d-6d28-431d-9f96-7d68b9b6445d.jsonl`
- `/ll:format-issue` - 2026-09-09T22:05:58 - `1744c85d-b425-4d1c-b20e-c1e871e66aec.jsonl`
- `/ll:issue-size-review` - 2026-09-09T21:57:08 - `0ecdfd2a-1186-4e76-ae8e-586f75aad086.jsonl`

---
id: FEAT-1623
type: FEAT
priority: P4
status: done
completed_at: 2026-05-23T01:47:53Z
parent: EPIC-1626
depends_on:
- FEAT-1112
relates_to:
- FEAT-1160
- FEAT-1624
labels:
- captured
- data-layer
- analytics
- hooks
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-1623: ctx-stats Data Layer — Schema Extension and PostToolUse Hook

## Summary

Extend FEAT-1112's `tool_events` SQLite table with per-tool byte-tracking columns and implement the `post_tool_use.py::handle()` extension that writes byte metrics on every tool call. Update all breaking tests triggered by the hook becoming non-no-op, and update adapter documentation that currently describes the handler as a no-op.

## Parent Issue
Decomposed from FEAT-1160: Context Window Analytics Command

## Scope
Covers Implementation Steps 1, 2, 6, 7, 13 from FEAT-1160.

## Use Case

A developer running an interactive Claude Code session triggers many tool calls (Read, Bash, Edit) whose payload sizes vary widely. Downstream, they invoke `/ll:ctx-stats` (FEAT-1624) to inspect which tools consumed the most context-window bytes during the session. This issue makes `post_tool_use.py::handle()` the producer of the byte-metric data that the future CLI consumes — without it, ctx-stats has no source rows to query.

## Current Behavior

- `scripts/little_loops/hooks/post_tool_use.py::handle()` is a no-op that returns `LLHookResult(exit_code=0)` without persisting any data.
- The `tool_events` table introduced in FEAT-1112 does not yet expose `bytes_in`, `bytes_out`, or `cache_hit` columns to consumers (columns may already exist in the migration but are unwritten).
- Adapter files (`hooks/adapters/codex/`, `hooks/adapters/opencode/`) and `docs/reference/HOST_COMPATIBILITY.md` describe the handler as a no-op with fire-and-forget semantics.
- Tests in `test_hook_post_tool_use.py` and `test_hook_intents.py` assert the no-op contract (`result.stdout is None`, empty stdout assertions).

## Expected Behavior

- `post_tool_use.py::handle()` writes a row to `tool_events` per tool call containing `bytes_in`, `bytes_out`, and `cache_hit` derived from the `LLHookEvent` payload.
- Writes are guarded by an `analytics.enabled` config flag — when false, the handler returns immediately without touching SQLite.
- Failures (locked store, missing store) degrade gracefully without raising into the hook dispatcher.
- Adapter comments and host-compatibility docs reflect data-producing semantics.
- Existing tests are updated to reflect the new contract; new tests cover the SQLite write path.

## Motivation

Context-window analytics (FEAT-1160) require persistent per-tool byte metrics to detect context pressure and surface high-cost tool calls. Without this data layer, the `/ll:ctx-stats` CLI (FEAT-1624) and docs wiring (FEAT-1625) have no source data to query. This issue unblocks the entire FEAT-1160 decomposition chain.

## Proposed Solution

### Step 1: Schema extension
Verify and confirm the `bytes_in INTEGER`, `bytes_out INTEGER`, `cache_hit INTEGER` columns in `session_store.py` migration. **Status: already present.** Columns are defined in `_MIGRATIONS[0]` (the v1 CREATE TABLE for `tool_events` at `scripts/little_loops/session_store.py` lines 76–88) and are referenced — currently as `None` — by the inline INSERT in `_backfill_tool_events()` at lines 512–518. No schema migration work is needed; Step 1 reduces to confirming presence before Step 2 begins.

Note: the column type for `cache_hit` is **`INTEGER`** (SQLite has no native BOOLEAN — store as 0/1), not `BOOLEAN` as written in the Current Behavior section above.

### Step 2: Extend `post_tool_use.py::handle()`
Extend `scripts/little_loops/hooks/post_tool_use.py::handle()` to write byte metrics per tool call:
- Compute `bytes_in = len(json.dumps(payload.get("tool_input", {})))`
- Compute `bytes_out = len(json.dumps(payload.get("tool_response", {})))`
- Compute `cache_hit = bool(payload.get("cache_hit", False))` (stored as 0/1 in SQLite)
- Guard on `analytics.enabled` config flag (follow `context_monitor.enabled` guard pattern in `hooks/scripts/context-monitor.sh` line 21)
- Model on `session_start.py::handle()` (data-producing handler returning `LLHookResult(exit_code=0, stdout=...)`)
- Input schema from `scripts/little_loops/hooks/types.py::LLHookEvent`

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete patterns and anchors verified against the codebase:_

- **Python feature-flag helper already exists**: `feature_enabled(config_data, "analytics.enabled")` at `scripts/little_loops/config/features.py:13`. This is the Python port of the shell `ll_feature_enabled` — use it directly rather than re-implementing dot-path traversal. Import via `from little_loops.config.features import feature_enabled` (not re-exported from `config/__init__.py`).
- **Established config-loading pattern in a hook**: model on `scripts/little_loops/hooks/user_prompt_submit.py::_load_config()` (line 38) — calls `resolve_config_path(cwd)` from `config.core`, then `json.loads(config_path.read_text(...))`, returns `None` on missing config / parse error. The handler then checks `feature_enabled(config, "analytics.enabled")` before any DB work.
- **No dispatcher-level exception catch**: `main_hooks()` at `scripts/little_loops/hooks/__init__.py:126` invokes `handler(event)` with **no try/except**. Any uncaught exception propagates to the subprocess caller and may surface as a hook failure to the host. All graceful degradation must therefore live inside `handle()` itself.
- **Graceful-degradation pattern to use**: wrap the SQLite write block in `with contextlib.suppress(Exception):` (matches `session_start.py:111–114` precedent). Use the broad `Exception` form, not just `sqlite3.Error`, because `ensure_db`/path-resolution can also raise `OSError` and `RuntimeError`. The narrower `sqlite3.Error + logger.warning` pattern (`SQLiteTransport.send`, line 312) is reserved for the long-lived transport sink, not single-shot hook writes.
- **No existing `insert_tool_event()` helper**: the only writer to `tool_events` is the inline INSERT in `_backfill_tool_events()` at `scripts/little_loops/session_store.py:512–518`. Recommendation: **inline the 8-column INSERT directly in the handler** (mirrors the backfill SQL exactly) rather than extracting a helper now. Extracting a helper can be deferred to FEAT-1624 if the CLI needs symmetric reads/writes.
- **Connection pattern for one-shot writes**: use `connect(db_path)` from `session_store` followed by `conn.close()` in a `try/finally`. This matches `_backfill_tool_events()` (lines 487–527). Do **not** use `SQLiteTransport` — that class is the long-lived loop-event sink, not a per-call writer.
- **`ts` timestamp**: use `_now()` from `scripts/little_loops/session_store.py:146` for ISO-formatted timestamps consistent with backfill rows.
- **`args_hash`**: use the existing `_hash_args(args)` helper (referenced by `_backfill_tool_events()` line 519) on `payload.get("tool_input", {})` so backfill and live writes produce comparable hashes.
- **`result_size`**: backfill writes `None`; for live writes, set to `bytes_out` (the new column is the more accurate analogue and avoids ambiguity vs. row count).
- **`cache_hit` payload key is not yet emitted by hosts**: research confirmed no existing test fixture or adapter writes a `cache_hit` field on PostToolUse events. `payload.get("cache_hit", False)` will default to `False` until hosts begin populating it — acceptable for the data layer; FEAT-1624 surfaces are tolerant of all-False columns.
- **opencode line number correction**: the "no-op baseline" comment in `hooks/adapters/opencode/index.ts` is at **line 76**, not line 75 as written in Step 13.

### Step 6: Fix breaking hook tests
Update `scripts/tests/test_hook_post_tool_use.py`:
- Adapt `TestPostToolUseBaseline.test_empty_payload_returns_pass` and `test_arbitrary_payload_returns_pass` to reflect non-no-op handler (drop `result.stdout is None` / `not result.data` assertions)
- Add `TestPostToolUseWithSessionStore` class covering:
  - Successful SQLite write with valid payload
  - Graceful fallback when store is absent/locked
  - Byte field extraction from `event.payload`

### Step 7: Fix breaking intent dispatch test
Update `scripts/tests/test_hook_intents.py`:
- Revise `TestHooksMainModule.test_dispatch_post_tool_use_happy_path` (line 319) to assert the new stdout content instead of `result.stdout == ""`

### Step 13: Update adapter no-op language
In the same commit as Step 2:
- `hooks/adapters/codex/post-tool-use.sh` (lines 7, 12) — remove "no-op" comments
- `hooks/adapters/opencode/index.ts` (line 76) — update "no-op baseline" comment
- `hooks/adapters/codex/README.md` (line 84) — update latency characterization
- `hooks/adapters/opencode/README.md` (lines 46–49, 111) — update "observational-only semantics" description
- `docs/reference/HOST_COMPATIBILITY.md` footnote `[^hot]` (lines 32–40) — update "fire-and-forget" latency claim

## Implementation Steps

1. Verify `bytes_in`/`bytes_out`/`cache_hit` columns present in `session_store.py` migration
2. Add `analytics` property (with `enabled: boolean, default: false`) to `config-schema.json` root `properties` — required before any user can set `analytics.enabled: true` in `ll-config.json` without schema validation failures
3. Extend `post_tool_use.py::handle()` to compute and persist byte metrics under `analytics.enabled` guard
4. Update breaking tests in `test_hook_post_tool_use.py` — adapt assertions **and** update module-level docstring (lines 1–8) that asserts "no-op baseline"; add `TestPostToolUseWithSessionStore` coverage
5. Update `test_hook_intents.py::test_dispatch_post_tool_use_happy_path` — adapt assertions at lines 340–343 **and** update docstring at lines 321–324 that asserts "no-op baseline... no stdout or stderr"
6. Refresh adapter no-op language across codex/opencode adapter files and `HOST_COMPATIBILITY.md` footnote; verify `test_codex_adapter.py::test_post_tool_use_sets_ll_hook_host_codex` still passes
7. Add `analytics.enabled` entry to `docs/reference/CONFIGURATION.md` (alongside schema update from Step 2)
8. Run `python -m pytest scripts/tests/test_hook_post_tool_use.py scripts/tests/test_hook_intents.py` to verify

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

2. Register `analytics` section in `config-schema.json` — add `"analytics": {"type": "object", "properties": {"enabled": {"type": "boolean", "default": false}}}` under root `properties`; without this, `"additionalProperties": false` rejects any config that enables the feature flag
7. Add `analytics.enabled` to `docs/reference/CONFIGURATION.md` — update the per-config-key tables section to document the new flag alongside existing `context_monitor.enabled` and similar flags

## API/Interface

```python
# scripts/little_loops/hooks/post_tool_use.py
def handle(event: LLHookEvent) -> LLHookResult:
    """Persist per-tool byte metrics to tool_events table.

    Guarded by analytics.enabled config flag. Failures degrade silently.
    """
    # No public interface change — same LLHookEvent → LLHookResult contract.
    # Side effect: row inserted into session_store.tool_events.
```

No external CLI or public Python API changes. Schema columns (`bytes_in INTEGER`, `bytes_out INTEGER`, `cache_hit BOOLEAN`) on `tool_events` are internal to `session_store.py`.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — verify `bytes_in`/`bytes_out`/`cache_hit` columns (lines 513–514)
- `scripts/little_loops/hooks/post_tool_use.py` — extend `handle()` from no-op to byte-tracking writer
- `hooks/adapters/codex/post-tool-use.sh` — remove "no-op" comments
- `hooks/adapters/opencode/index.ts` — update "no-op baseline" comment
- `hooks/adapters/codex/README.md` — update latency claim
- `hooks/adapters/opencode/README.md` — update semantics description
- `docs/reference/HOST_COMPATIBILITY.md` — update `[^hot]` footnote
- `config-schema.json` — add `analytics` property with `enabled` boolean (critical: root-level `"additionalProperties": false` will reject any `ll-config.json` with `analytics.enabled: true` until this is added) [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/__init__.py::_dispatch_table()` — wires `post_tool_use.handle` into the hook dispatcher
- `scripts/little_loops/hooks/types.py` — `LLHookEvent` / `LLHookResult` dataclass contracts (reference only, no changes)

### Similar Patterns
- `scripts/little_loops/hooks/session_start.py::handle()` — data-producing hook handler model; `contextlib.suppress(Exception)` write-guard at lines 111–114
- `scripts/little_loops/hooks/user_prompt_submit.py::_load_config()` (line 38) — established Python pattern for loading `.ll/ll-config.json` from inside a hook
- `scripts/little_loops/config/features.py::feature_enabled()` (line 13) — Python helper that mirrors shell `ll_feature_enabled` for dot-path flag checks
- `scripts/little_loops/session_store.py::_backfill_tool_events()` (lines 487–527) — inline `INSERT INTO tool_events(...)` SQL and connection lifecycle to mirror
- `scripts/little_loops/session_store.py::_now()` (line 146), `_hash_args()` — helpers to reuse for `ts` and `args_hash` columns
- `hooks/scripts/context-monitor.sh` — `ll_feature_enabled "context_monitor.enabled"` shell guard pattern (line 21)
- `scripts/little_loops/hooks/__init__.py` — `_dispatch_table()` registration (line 83); **no try/except** around handler call at line 126

### Tests
- `scripts/tests/test_hook_post_tool_use.py` — update baseline assertions, add `TestPostToolUseWithSessionStore`; also update module-level docstring (lines 1–8) which states "no-op baseline returning `LLHookResult(exit_code=0)`"
- `scripts/tests/test_hook_intents.py` — update `test_dispatch_post_tool_use_happy_path` assertion (line 319; assertions at lines 340–343) **and** its docstring (lines 321–324) which reads "no-op baseline... no stdout or stderr" — both the assertion and docstring assert the no-op contract
- `scripts/tests/test_hook_session_start.py` (lines 19–27) — `in_tmp` fixture pattern for cwd-dependent handlers; reuse if the handler reads `Path.cwd()`
- `scripts/tests/test_session_store.py::TestSQLiteTransport` (line 70) — model for write-then-`recent(db, kind="tool")` read-back assertions in the new `TestPostToolUseWithSessionStore` class

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_codex_adapter.py` — exercises `hooks/adapters/codex/post-tool-use.sh` end-to-end via `test_post_tool_use_sets_ll_hook_host_codex()`; uses a fake-package stub so the real handler is bypassed and the test won't break, but verify after adapter comment changes [Agent 1 finding]

### Documentation

- `hooks/adapters/codex/README.md`
- `hooks/adapters/opencode/README.md`
- `docs/reference/HOST_COMPATIBILITY.md`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — no `analytics.enabled` entry exists; add alongside schema update since the section listing per-config-key tables currently omits `analytics` entirely [Agent 2 finding]

### Configuration
- `analytics.enabled` flag in `.ll/ll-config.json` (new gate; default off until FEAT-1624 ships)

## Acceptance Criteria
- [ ] `session_store.py` `tool_events` table has `bytes_in`, `bytes_out`, `cache_hit` columns
- [ ] `post_tool_use.py::handle()` writes byte metrics per tool call to SQLite
- [ ] `analytics.enabled: false` skips SQLite writes (guard in place)
- [ ] Locked/missing store fails silently without raising into dispatcher
- [ ] `test_hook_post_tool_use.py` tests pass with updated assertions
- [ ] `test_hook_post_tool_use.py` includes `TestPostToolUseWithSessionStore` covering write, fallback, and field extraction
- [ ] `test_hook_intents.py::test_dispatch_post_tool_use_happy_path` passes
- [ ] Adapter files no longer describe handler as a "no-op"
- [ ] `docs/reference/HOST_COMPATIBILITY.md` `[^hot]` footnote reflects data-producing semantics

## Impact
- **Priority**: P4 - Foundational data layer for FEAT-1160 ctx-stats; FEAT-1624/1625 depend on it but no user-facing pressure until that chain ships
- **Effort**: Small - Schema columns already inserted (FEAT-1112); handler change is ~30 LOC; test adaptations are mechanical; doc edits are localized
- **Risk**: Low - Behind `analytics.enabled` config guard; failure mode is silent skip; comprehensive test coverage planned
- **Breaking Change**: No - Config-gated; default behavior unchanged when `analytics.enabled` is false

## Related Key Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — host hook semantics (updated by this issue)
- `docs/ARCHITECTURE.md` — session store and hook dispatcher overview
- FEAT-1160 parent PRD

## Session Log
- `/ll:manage-issue` - 2026-05-23T01:47:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1bbe0f9c-730d-428b-b6c7-f9f337347998.jsonl`
- `/ll:ready-issue` - 2026-05-23T01:37:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ea74cc3d-653e-4942-b13e-d6e30bbd9568.jsonl`
- `/ll:confidence-check` - 2026-05-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/46973b91-6719-4152-a643-065f9dac6728.jsonl`
- `/ll:wire-issue` - 2026-05-23T01:33:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5c6575ad-08c8-4239-bb34-3c01d8c91783.jsonl`
- `/ll:refine-issue` - 2026-05-23T01:27:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6ca96194-8e2a-43cf-a4d7-65ffa2188f54.jsonl`
- `/ll:format-issue` - 2026-05-23T01:16:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8da292ce-0772-4768-ab92-9c4bc7efe216.jsonl`
- `/ll:issue-size-review` - 2026-05-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

---

## Status
**Done** | Created: 2026-05-22 | Completed: 2026-05-23 | Priority: P4

## Resolution

Implemented per the plan:

- `scripts/little_loops/hooks/post_tool_use.py::handle()` now persists per-tool byte metrics (`bytes_in`, `bytes_out`, `cache_hit`) into `.ll/session.db::tool_events` on every tool call, gated by `analytics.enabled` and wrapped in `contextlib.suppress(Exception)` so SQLite failures degrade silently.
- `config-schema.json` gains an `analytics` section with the `enabled` boolean (default `false`) so opting in does not trip `additionalProperties: false`.
- `scripts/tests/test_hook_post_tool_use.py` baseline tests adapted; new `TestPostToolUseWithSessionStore` class covers the enabled write path, the disabled/no-config skip paths, `cache_hit` extraction, byte-field defaults, and graceful fallback when SQLite raises.
- `scripts/tests/test_hook_intents.py::test_dispatch_post_tool_use_happy_path` docstring/assertions updated to match the new data-producing contract (tmp_path with no config → no SQLite write).
- Adapter files (`hooks/adapters/codex/post-tool-use.sh`, `hooks/adapters/codex/README.md`, `hooks/adapters/opencode/index.ts`, `hooks/adapters/opencode/README.md`) and `docs/reference/HOST_COMPATIBILITY.md` `[^hot]` footnote reflect data-producing semantics under the `analytics.enabled` guard.
- `docs/reference/CONFIGURATION.md` documents the new `analytics.enabled` flag.

Verification: targeted hooks tests (45 + 32 passed), full suite (7334 passed; one pre-existing CLAUDE.md skill-count failure unrelated to this issue), `ruff check scripts/` passes, `mypy` on the handler passes.

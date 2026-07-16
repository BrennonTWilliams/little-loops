---
id: ENH-2582
title: analytics.auto_collect opt-in background summarization
type: ENH
priority: P3
status: open
discovered_date: 2026-07-08
captured_at: "2026-07-08T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - session-end
  - captured
---

# ENH-2582: analytics.auto_collect opt-in background summarization

## Summary

Add a new `analytics.auto_collect` config namespace (default
**off**) that, when enabled, causes a new `SessionEnd` hook to
invoke `ll-session compact --and-prune` (the subcommand
introduced by ENH-2581). The runner is best-effort per the
EPIC-1707 graceful-degradation contract
(`contextlib.suppress(Exception)` around the subprocess
spawn). **No auto-injection** of observations into prompt
context; consumption stays pull-based via `ll-history-context`.

## Motivation

The project already does ClaudeMem-style "auto-collect to DB
during the session" via `analytics.capture.*` (per
`config-schema.json:1561-1629` and
`config/features.py:528-556`). What's missing is *background
summarization of older sessions* — `summary_nodes` are
regenerated only on explicit `compact_session` calls, not
automatically as data ages out. The new `compact` subcommand
from ENH-2581 is the primitive; this child wires it to a
config gate and a `SessionEnd` trigger.

The user's intent: a ClaudeMem-like auto-collect experience,
but **without** the auto-injection that has caused other
"context engineering" tools to confuse models with stale or
off-topic observations. The project is intentionally
pull-based on the read side (skills query `history.db` on
demand via `ll-history-context`); the auto-collect runner
preserves that posture.

## Current Behavior

- `_compact_sessions()` at `session_store.py:2189-2341`
  exists and is gated on `history.compaction.enabled`
  (default `false`), but only fires from explicit
  `backfill()` calls. There is no `SessionEnd` hook.
- `scripts/little_loops/hooks/` has no `session_end.py` (per
  `ls` of the directory; the existing hooks are
  `session_start`, `post_tool_use`, `pre_tool_use`,
  `post_commit`, `sweep_stale_refs`, `pre_compact_handoff`,
  `install_learning_gate`, `edit_batch_nudge`).
- `config-schema.json` has zero matches for `auto_collect`,
  `autocollect`, or `auto-collect`. The `enabled` boolean
  at `analytics.enabled` (default `false`) is the closest
  analog — it gates the `post_tool_use` hook persisting
  metrics per the schema description at line 1567.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- ENH-2581 is now `done`. The relevant primitive is
  `session_store.py:compact()` (`scripts/little_loops/session_store.py:3034`),
  which deterministically creates `kind='retention'` summary nodes and then
  optionally calls `prune()`. It is distinct from the LLM-backed
  `_compact_sessions()` path gated by `history.compaction.enabled`; this issue
  must not describe or test the two paths as if they were the same.
- The current schema anchor is `config-schema.json:1608-1681`. Its
  `analytics` object contains `enabled` (default `true`), `capture`, and
  `retention`, with `additionalProperties: false`; `auto_collect` must be added
  as a sibling property. The earlier claim that `analytics.enabled` defaults
  to `false` is stale; the new `auto_collect.enabled` gate remains independently
  default-off.
- There is no parent analytics dataclass. `BRConfig._parse_config()` directly
  constructs `AnalyticsCaptureConfig` at
  `scripts/little_loops/config/core.py:241-243`, and exposes it through
  `BRConfig.analytics_capture`. A new auto-collect config should follow that
  standalone-dataclass/accessor pattern rather than adding a field to a
  nonexistent wrapper.
- `session_end` already names a host-agnostic intent in
  `scripts/little_loops/hooks/__init__.py:_dispatch_table()`, where it maps to
  `sweep_stale_refs.handle`. That intent is currently invoked from a
  `SessionStart` hook as the FEAT-1680 stale-reference sweep. Native
  `SessionEnd` currently runs only `hooks/scripts/scratch-cleanup.sh` via
  `hooks/hooks.json:198-209`.
- Claude Code applies a short SessionEnd execution window (documented in
  `sweep_stale_refs.py`); therefore the new path must only validate the gate,
  detach a child with `subprocess.Popen(..., start_new_session=True)`, and
  return without waiting.

## Expected Behavior

`analytics.auto_collect.enabled: false` (default) by default.
When `true`:

- `SessionEnd` hook spawns a detached subprocess
  (`ll-session compact --and-prune --config <config_path>`).
- The subprocess wraps its work in
  `contextlib.suppress(Exception)` per EPIC-1707. Failures
  during compaction do not block the session from ending.
- The schema adds the new key under
  `analytics.auto_collect`; the dataclass gains the field.
- `SessionStart` orchestration (per ENH-2581) is unchanged
  — `analytics.auto_collect` does **not** gate the
  `rebuild` decision (that decision is based on
  `SCHEMA_VERSION`, per ENH-2581's open question §c).
- **No auto-injection of observations into prompt context.**
  This is explicitly out of scope. The user must opt in
  per-skill (via `analytics.capture.skills` and the
  `ll-history-context` consumer) for any read-side use.

## Scope Boundaries

### In Scope

- A default-off `analytics.auto_collect.enabled` schema and typed runtime config.
- A host-agnostic hook intent plus Claude Code native `SessionEnd` registration.
- Best-effort detached execution of the existing deterministic
  `ll-session --db <path> compact --and-prune --config <path>` primitive.
- Preservation of existing SessionEnd scratch cleanup and FEAT-1680 stale-ref
  sweep behavior.
- Config, handler, dispatch, registration, and documentation coverage.

### Out of Scope

- The LLM-backed `history.compaction` / `_compact_sessions()` path or any change
  to retention thresholds and `compact()` / `prune()` semantics.
- Automatic prompt injection, changes to `ll-history-context`, or changes to the
  separate `history.session_digest` feature.
- SessionStart rebuild/backfill orchestration introduced by ENH-2581.
- Blocking on the child process or surfacing compaction failures to the host.
- Native SessionEnd registration for hosts that do not expose an equivalent
  lifecycle event; the handler remains reusable when an adapter becomes
  available.

## Proposed Solution

### 1. Schema addition (`config-schema.json`)

Add to the `analytics` object (around line 1561):

```json
"auto_collect": {
  "type": "object",
  "description": "Background summarization runner. When enabled, the SessionEnd hook invokes ll-session compact --and-prune. Default off; no auto-injection (ENH-2582).",
  "properties": {
    "enabled": {
      "type": "boolean",
      "default": false,
      "description": "Run ll-session compact --and-prune on SessionEnd (default false)."
    }
  },
  "additionalProperties": false
}
```

The parent `analytics` object's `additionalProperties: false`
allows this addition (the new key is a property of
`analytics`, not a new top-level key).

### 2. Dataclass addition (`config/features.py`)

Add new dataclass after `AnalyticsCaptureConfig`
(line 528-556):

```python
@dataclass
class AutoCollectConfig:
    """Background summarization runner (ENH-2582).
    When enabled, SessionEnd invokes ll-session compact --and-prune.
    Default off; no auto-injection.
    """
    enabled: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutoCollectConfig":
        return cls(enabled=bool(data.get("enabled", False)))
```

Add field to the parent analytics config dataclass (find
the class containing `capture: AnalyticsCaptureConfig`):

```python
auto_collect: AutoCollectConfig = field(default_factory=AutoCollectConfig)
```

### 3. New `SessionEnd` hook (`scripts/little_loops/hooks/session_end.py`)

Mirror `session_start.py`'s `handle()` pattern (line 75+):

```python
def handle(event: dict) -> int:
    """SessionEnd hook (ENH-2582). Fires ll-session compact --and-prune
    in a detached subprocess if analytics.auto_collect.enabled is true.
    Best-effort per EPIC-1707 graceful-degradation contract.
    """
    payload = event.get("payload", {})
    cwd = Path(payload.get("cwd") or os.getcwd())
    config_path = resolve_config_path(cwd)
    if config_path is None:
        return 0

    config = load_config(config_path)
    if not (config.get("analytics", {}).get("auto_collect", {}).get("enabled")):
        return 0  # default off; no-op

    db_path = resolve_history_db(cwd / ".ll" / "history.db")
    with contextlib.suppress(Exception):
        subprocess.Popen(
            [sys.executable, "-m", "little_loops.cli.session", "compact",
             "--and-prune", "--config", str(config_path),
             "--db", str(db_path)],
            start_new_session=True,
            stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL,
            cwd=str(cwd),
        )
    return 0
```

The hook returns 0 in all paths. Failures during config
load or subprocess spawn are swallowed by
`contextlib.suppress(Exception)`.

### 4. Hook registration (`hooks/hooks.json`)

Add:

```json
{
  "event": "SessionEnd",
  "matcher": "*",
  "hooks": [{
    "type": "command",
    "command": "python -m little_loops.hooks.session_end"
  }]
}
```

(Exact schema: see `hooks/hooks.json` for the existing
`SessionStart` registration; mirror it.)

### 5. Tests

`scripts/tests/test_hook_session_end.py` mirroring
`TestSessionStartBackfillThread` at
`scripts/tests/test_hook_session_start.py:236-303`. The
pattern: mock `subprocess.Popen`, capture arg lists, call
`handle(_event())`, assert on the captured calls.

Test cases:

- `test_noop_when_auto_collect_disabled` — default config;
  assert no Popen call.
- `test_noop_when_config_absent` — no `.ll/ll-config.json`;
  assert no Popen call.
- `test_spawns_subprocess_when_enabled` — config has
  `analytics.auto_collect.enabled: true`; assert one
  Popen call with `compact --and-prune` in args.
- `test_swallows_popen_exception` — patch `subprocess.Popen`
  to raise; assert `handle()` returns 0 (does not raise).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Implement a distinct host-agnostic intent such as
  `analytics_auto_collect`, backed by a module such as
  `scripts/little_loops/hooks/analytics_auto_collect.py`. Do **not** replace or
  compose through the existing `session_end` intent: it currently owns the
  FEAT-1680 stale-reference sweep and is invoked during `SessionStart`.
- Add `hooks/adapters/claude-code/analytics-auto-collect.sh` following the
  existing adapter pattern, then register that adapter as a sibling entry in
  the existing native `SessionEnd` array in `hooks/hooks.json`. Add the new
  intent to `_dispatch_table()`, the module intent list, and `_USAGE` in
  `scripts/little_loops/hooks/__init__.py`.
- Define `AnalyticsAutoCollectConfig(enabled: bool = False)` as a standalone
  dataclass in `config/features.py`; construct and expose it from `BRConfig`
  beside `analytics_capture`. The handler may parse this typed config from the
  resolved file, but should not invent a parent `AnalyticsConfig` solely for
  this flag.
- Return `LLHookResult(exit_code=0)`, not the integer `0`, because
  `main_hooks()` dereferences `result.stdout`, `result.feedback`, and
  `result.exit_code`.
- Put config/path resolution, gate evaluation, DB resolution, and `Popen`
  inside one best-effort exception envelope. The sample above only suppresses
  `Popen`, so it does not satisfy its own claim that config-load failures are
  swallowed. `sweep_stale_refs.handle()` provides the full-handler
  `try/except Exception` precedent.
- Resolve the DB through
  `session_store.resolve_history_db(cwd / ".ll" / "history.db")` so
  `LL_HISTORY_DB` and `history.db_path` precedence from ENH-2623 is preserved.
  The child argv must place the parent-parser `--db` option **before** the
  subcommand:

  ```python
  [
      sys.executable,
      "-m",
      "little_loops.cli.session",
      "--db",
      str(db_path),
      "compact",
      "--and-prune",
      "--config",
      str(config_path),
  ]
  ```

  The previously proposed `compact ... --db <path>` order is rejected by
  `_build_parser()` as an unrecognized argument.
- Mirror `session_start.handle()`'s detached `Popen` kwargs and explicitly skip
  when `LL_NON_INTERACTIVE` is set, preventing every nested automation session
  from launching a redundant compaction process.
- Keep all prompt-producing modules unchanged. `compact()` writes retention
  summary rows only; `ll-history-context` remains the explicit pull-side
  consumer, and the pre-existing `history.session_digest` SessionStart context
  is a separate feature.

## Integration Map

### Files to Modify

- `config-schema.json:1608-1681` — add default-off
  `analytics.auto_collect.enabled` beside `capture` and `retention`.
- `scripts/little_loops/config/features.py:AnalyticsCaptureConfig` — add the
  adjacent standalone `AnalyticsAutoCollectConfig` dataclass.
- `scripts/little_loops/config/core.py:BRConfig._parse_config()` and
  `BRConfig.analytics_capture` — construct and expose the new typed config.
- `scripts/little_loops/hooks/analytics_auto_collect.py` — add the gate and
  best-effort detached internal-Python subprocess handler.
- `scripts/little_loops/hooks/__init__.py:_dispatch_table()` and `_USAGE` —
  register a new intent without changing the existing `session_end` mapping.
- `hooks/adapters/claude-code/analytics-auto-collect.sh` — translate the native
  hook payload into the new host-agnostic intent.
- `hooks/hooks.json:198-209` — append the adapter under the existing
  `SessionEnd` registration; preserve `scratch-cleanup.sh`.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/session.py:_build_parser()` — defines `--db` on the
  parent parser and `compact --and-prune --config` on the subparser.
- `scripts/little_loops/cli/session.py:main_session()` — loads the config and
  calls `session_store.compact(..., and_prune=True)`.
- `scripts/little_loops/session_store.py:compact()` — deterministic retention
  summarization; reads `analytics.retention.raw_event_max_age_days`.
- `scripts/little_loops/session_store.py:resolve_history_db()` — owns
  environment/config/default DB-path precedence.
- `scripts/little_loops/hooks/sweep_stale_refs.py:handle()` — current owner of
  the `session_end` intent and the full best-effort handler precedent; must
  remain wired unchanged.

### Similar Patterns

- `scripts/little_loops/hooks/session_start.py:handle()` — detached
  `sys.executable -m ...` worker with `start_new_session=True` and all stdio
  redirected to `DEVNULL`.
- `scripts/little_loops/hooks/sweep_stale_refs.py:handle()` — returns
  `LLHookResult` and catches all exceptions so lifecycle work cannot block the
  host.
- `hooks/adapters/claude-code/session-end.sh` — minimal adapter that pipes the
  native JSON payload into `python -m little_loops.hooks <intent>`.

### Tests

- `scripts/tests/test_hook_analytics_auto_collect.py` — new handler tests for
  absent/disabled/enabled config, `LL_NON_INTERACTIVE`, exact parser-valid argv
  and detach kwargs, config/path/DB-resolution failures, and `Popen` failures.
- `scripts/tests/test_hook_intents.py` — prove the new intent dispatches while
  `session_end` still maps to `sweep_stale_refs.handle`.
- `scripts/tests/test_config.py` — typed config default and explicit-enable
  parsing through `BRConfig`.
- `scripts/tests/test_config_schema.py` — schema acceptance and rejection of
  unknown `auto_collect` properties.
- `scripts/tests/test_hooks_integration.py` — native `SessionEnd` registration
  keeps scratch cleanup and invokes the new adapter.

### Documentation

- `docs/reference/CONFIGURATION.md` — document the default-off namespace beside
  the existing `analytics.capture` and `analytics.retention` sections.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — document the detached SessionEnd path
  and its short execution window.
- `docs/reference/API.md` — add `AnalyticsAutoCollectConfig` and its `BRConfig`
  accessor.
- `docs/reference/CLI.md` — cross-reference the opt-in trigger from the existing
  `ll-session compact --and-prune` section.
- `docs/reference/HOST_COMPATIBILITY.md` — record the new lifecycle intent and
  supported native host registration.

### Configuration

- `.ll/ll-config.json` and generated configs may omit `auto_collect`; the typed
  and schema defaults keep it off. Existing `analytics.enabled`, `capture`, and
  `retention` values must continue to parse unchanged.

## Acceptance Criteria

- `analytics.auto_collect.enabled` defaults to `false`.
- When `false`, `SessionEnd` is a no-op (no subprocess
  spawn, no DB read).
- When `true`, the subprocess fires on `SessionEnd` with
  args `compact --and-prune --config <path> --db <path>`.
- The subprocess is best-effort: any exception during
  spawn is swallowed; the hook returns 0.
- **No auto-injection of observations into prompt context.**
  This is enforced by the absence of any code path that
  injects `summary_nodes` into a `UserPromptSubmit` or
  `SessionStart` payload. Documented in
  `docs/ARCHITECTURE.md`.
- Schema validates with the new key; pre-existing
  `analytics.*` keys continue to work.
- Tests cover: default-off, enabled-on, config-absent,
  exception-swallowed.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The new native `SessionEnd` registration preserves the existing scratch
  cleanup hook, and the existing host-agnostic `session_end` intent remains
  mapped to `sweep_stale_refs.handle`.
- Missing config, `analytics.auto_collect`, or `enabled` all produce a no-op;
  disabled paths do not resolve/open the DB or spawn a process.
- Enabled mode launches exactly one detached child with parser-valid argument
  order: `--db <path> compact --and-prune --config <path>`.
- `LL_HISTORY_DB` and `history.db_path` overrides are honored through
  `resolve_history_db()`.
- Config discovery, JSON parsing, typed gate parsing, DB-path resolution, and
  process creation are all best-effort; any exception returns
  `LLHookResult(exit_code=0)`.
- `LL_NON_INTERACTIVE` suppresses the child launch to avoid redundant work in
  nested automation sessions.
- Schema/config tests prove `enabled` defaults to `false`, explicit `true` is
  accepted, unknown nested keys are rejected, and existing `analytics.*`
  configurations remain valid.
- No new call from `session_start`, `user_prompt_submit`, or any prompt renderer
  reads or injects retention `summary_nodes`.

## Implementation Steps

1. Add `auto_collect` property to `analytics` block in
   `config-schema.json` (around line 1561-1629).
2. Add `AutoCollectConfig` dataclass to
   `config/features.py` after `AnalyticsCaptureConfig`.
   Add `auto_collect: AutoCollectConfig` field to the
   parent analytics class.
3. Create `scripts/little_loops/hooks/session_end.py`
   mirroring `session_start.py` `handle()` pattern.
4. Register `SessionEnd` event in `hooks/hooks.json`.
5. Update `scripts/little_loops/hooks/__init__.py` to
   export `session_end.handle` (per
   `hooks/__init__.py:91` pattern).
6. Tests in
   `scripts/tests/test_hook_session_end.py`:
   - `test_noop_when_auto_collect_disabled`
   - `test_noop_when_config_absent`
   - `test_spawns_subprocess_when_enabled`
   - `test_swallows_popen_exception`
7. Docs:
   - `docs/ARCHITECTURE.md` — add row to the
     "Session lifecycle hooks" table; note
     "no auto-injection" defense.
   - `docs/reference/API.md` — `AutoCollectConfig`
     reference.
   - `docs/reference/CLI.md` — note that
     `analytics.auto_collect.enabled` toggles
     `SessionEnd` background summarization.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete sequence against the current codebase:_

1. Add `analytics.auto_collect.enabled` to the root `config-schema.json`, then
   add `AnalyticsAutoCollectConfig` plus a `BRConfig.analytics_auto_collect`
   accessor in `config/features.py` and `config/core.py`.
2. Create `scripts/little_loops/hooks/analytics_auto_collect.py` with a single
   best-effort `handle(LLHookEvent) -> LLHookResult` envelope. Resolve the
   project/config/gate first; when enabled and interactive, resolve the DB and
   launch the internal CLI as a detached child without waiting.
3. Register a new `analytics_auto_collect` intent in
   `scripts/little_loops/hooks/__init__.py`; leave the existing `session_end`
   mapping unchanged.
4. Add the Claude Code adapter and append it to the existing native
   `SessionEnd` hook list, preserving scratch cleanup.
5. Add typed-config/schema tests, direct handler tests, dispatcher tests, and a
   hook-registration integration assertion. Model `Popen` capture after
   `TestSessionStartBackfillThread`, but also assert kwargs and the global
   `--db` option's position before `compact`.
6. Update `docs/reference/CONFIGURATION.md`,
   `docs/guides/BUILTIN_HOOKS_GUIDE.md`, `docs/reference/API.md`,
   `docs/reference/CLI.md`, and `docs/reference/HOST_COMPATIBILITY.md`. The
   previously named lifecycle table does not currently exist in
   `docs/ARCHITECTURE.md`; update that document only if adding a new lifecycle
   overview is intentionally part of scope.
7. Run focused tests for the files above, then the project gate:
   `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P3.
- **Effort**: Small. New hook file, new config key, one
  new subprocess call, four test functions. The
  `compact`/`prune` work itself is owned by ENH-2581.
- **Risk**: Low. Default off. When on, the subprocess
  is best-effort; failures are swallowed. The
  `SessionEnd` hook is fire-and-forget; it never
  blocks session termination.
- **Breaking Change**: No. New hook is additive; new
  config key is additive. No existing `ll-session
  compact` callsite changes.

## Sources

- `thoughts/history-db-raw-events-architecture.md` §
  "The `compact`/`prune` split" — the broader
  architecture this child participates in.
- `scripts/little_loops/hooks/session_start.py:75-221`
  — the `handle()` pattern to mirror.
- `scripts/little_loops/hooks/__init__.py:91` — the
  hook registration pattern.
- `scripts/little_loops/config/features.py:528-556` —
  `AnalyticsCaptureConfig` to extend.
- `config-schema.json:1561-1629` — `analytics` block
  to extend.
- `scripts/tests/test_hook_session_start.py:236-303` —
  `TestSessionStartBackfillThread` test pattern to
  mirror.

### Codebase Research Findings

_Added by `/ll:refine-issue` — current-source corrections:_

- `scripts/little_loops/session_store.py:compact()` is at approximately
  `3034-3121`; `_compact_sessions()` is a separate LLM-backed path at
  approximately `2452-2604`.
- The analytics schema is at `config-schema.json:1608-1681` and
  `AnalyticsCaptureConfig` spans
  `scripts/little_loops/config/features.py:528-558`.
- `scripts/little_loops/hooks/__init__.py:_dispatch_table()` is the stable
  registration anchor; numeric line 91 currently maps `session_end` to
  `sweep_stale_refs.handle`.
- `thoughts/history-db-raw-events-architecture.md` is not present in the current
  tree. Treat it as a stale source reference; ENH-2581 plus
  `session_store.compact()`/`prune()` are the current sources of truth.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Session lifecycle hooks table; "no auto-injection" defense. |
| `docs/reference/API.md` | `AutoCollectConfig` reference. |
| `docs/reference/CLI.md` | `analytics.auto_collect.enabled` toggle. |
| `thoughts/history-db-raw-events-architecture.md` | The parent design doc. |

## Status

**Open** | Created: 2026-07-08 | Priority: P3

Depends on **ENH-2581** (raw_events source of truth +
`compact` subcommand). The `SessionEnd` hook calls
`ll-session compact --and-prune`; that subcommand is
introduced by ENH-2581.

## Session Log
- `/ll:refine-issue` - 2026-07-16T17:45:43 - `47549753-d403-42e4-a8c1-dc90cd53d5e7.jsonl`
- `/ll:capture-issue` - 2026-07-08T00:00:00Z - fourth-pass expansion of EPIC-2457

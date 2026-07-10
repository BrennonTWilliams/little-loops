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
- `/ll:capture-issue` - 2026-07-08T00:00:00Z - fourth-pass expansion of EPIC-2457

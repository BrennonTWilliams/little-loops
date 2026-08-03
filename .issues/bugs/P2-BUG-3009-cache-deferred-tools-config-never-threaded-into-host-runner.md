---
id: BUG-3009
title: cache/deferred_tools config parsed but never threaded into host_runner dispatch
type: BUG
status: open
priority: P2
discovered_date: 2026-08-02
discovered_by: multi-agent-audit
parent: EPIC-3008
testable: true
labels:
- config
- host-runner
- fsm
---

# BUG-3009: `cache`/`deferred_tools` config parsed but never threaded into `host_runner` dispatch

## Summary

`cache.require_repeat` and `deferred_tools.{threshold,search_tool_variant}`
(`config-schema.json:643-672`) are fully parsed into typed `BRConfig`
dataclasses and documented in `docs/reference/CONFIGURATION.md`, but the one
live runtime call site that could act on them never passes them through — the
config is functionally inert regardless of what a user sets in
`ll-config.json`.

## Current Behavior

- `BRConfig.cache` / `BRConfig.deferred_tools` are parsed at
  `scripts/little_loops/config/core.py:260-263` and exposed as properties at
  `core.py:349-356`, and exposed in `to_dict()` at `core.py:769-771`.
- `host_runner.build_anthropic_request()`'s docstring
  (`scripts/little_loops/host_runner.py:1700-1702`) states `require_repeat`
  "mirrors `config.cache.require_repeat` — callers wire the config value
  through explicitly."
- The only real call site, `scripts/little_loops/fsm/executor.py`'s
  `_dispatch_live` (around `executor.py:2452-2510`), calls
  `host_runner.dispatch_anthropic_request(...)` / `dispatch_batch_request(...)`
  **without ever passing `require_repeat`, `defer_loading_threshold`, or
  `search_tool_variant`**, so all three silently fall back to hardcoded
  defaults (`require_repeat=True`, `defer_loading_threshold=None`,
  `search_tool_variant="bm25"`) no matter what's configured.
- Confirmed via grep: zero references to `.cache` or `.deferred_tools` (or
  `require_repeat`/`defer_loading_threshold`/`search_tool_variant`) anywhere in
  `fsm/executor.py`.

## Steps to Reproduce

1. Set `cache.require_repeat: false` (or a non-default `deferred_tools.threshold`)
   in a project's `.ll/ll-config.json`.
2. Run an FSM loop state that reaches `_dispatch_live` in
   `scripts/little_loops/fsm/executor.py` (any live-dispatch loop run).
3. Inspect the kwargs passed to `host_runner.dispatch_anthropic_request`/
   `dispatch_batch_request` (e.g. via a spy/mock in a test, or by tracing the
   call) — `require_repeat` is still `True` and `defer_loading_threshold`/
   `search_tool_variant` are still `None`/`"bm25"`, ignoring the configured
   values.

## Expected Behavior

`_dispatch_live` should read `cache.require_repeat` and
`deferred_tools.{threshold,search_tool_variant}` from a `BRConfig` instance and
pass them through to `dispatch_anthropic_request`/`dispatch_batch_request`, so
a user's `ll-config.json` overrides actually take effect on live FSM runs.

## Blocker: the executor has no `self.config`

`FSMExecutor` does **not** hold a `BRConfig` instance. It constructs one ad hoc
at five sites, from four different roots:

| Site | Root used |
|------|-----------|
| `executor.py:927` | `repo_path` |
| `executor.py:1104` | `Path.cwd()` |
| `executor.py:1366` | `repo_root` |
| `executor.py:2010` | `self.working_dir or Path.cwd()` |
| `executor.py:3137` | `Path.cwd()` |

So the fix cannot just write `self.config.cache.require_repeat` — the implementer
must first decide *which root* and *how often* config is resolved.

**Decision (made here so implementation doesn't have to guess):** resolve from
`self.working_dir or Path.cwd()`, matching the existing precedent at
`executor.py:2010` (the nearest sibling read, and the only one that honors an
explicit working dir). Resolve it **once** and memoize on the executor — do not
construct a `BRConfig` per dispatch, which would re-read and re-parse
`ll-config.json` on every action in the loop.

## Suggested Fix Direction

1. Add a memoized accessor on `FSMExecutor` (e.g. `_get_config()` caching a
   `BRConfig(self.working_dir or Path.cwd())` on first use).
2. In `_dispatch_live`, thread the values into **both** dispatch call sites —
   the SDK path (`executor.py:2475`) and the batch path (`executor.py:2499`) —
   as `require_repeat=`, `defer_loading_threshold=`, `search_tool_variant=`.
3. Add tests asserting a non-default `ll-config.json` value changes the kwargs
   actually passed, via a spy/mock on `dispatch_anthropic_request` *and* on
   `dispatch_batch_request` (the batch path is easy to forget — it currently has
   the same gap).

## Program Design

### Signatures

Both are **keyword-only** and return `ActionResult`/`str`, not `dict`:

```python
def dispatch_anthropic_request(
    *,
    action: str,
    system_prompt: str | None = None,
    tools: list[ToolDefinition] | None = None,
    model: str,
    fragment_store: FragmentStore,
    require_repeat: bool = True,
    defer_loading_threshold: int | None = None,
    search_tool_variant: str = "bm25",
) -> ActionResult: ...          # existing, host_runner.py:1879

def dispatch_batch_request(
    *,
    custom_id: str,
    action: str,
    system_prompt: str | None = None,
    tools: list[ToolDefinition] | None = None,
    model: str,
    fragment_store: FragmentStore,
    require_repeat: bool = True,
    defer_loading_threshold: int | None = None,
    search_tool_variant: str = "bm25",
) -> str: ...                   # existing, host_runner.py:1939
```

Config dataclass field names (confirmed, `config/features.py:562-606`):
`CacheConfig.require_repeat: bool = True`;
`DeferredToolsConfig.threshold: int | None = None`,
`DeferredToolsConfig.search_tool_variant: str = "bm25"`.

### Call Path

`fsm/executor.py::_dispatch_live` -> memoized
`BRConfig(self.working_dir or Path.cwd())` -> reads `.cache.require_repeat` and
`.deferred_tools.{threshold,search_tool_variant}` -> passes them as explicit
keyword args into `host_runner.dispatch_anthropic_request(...)`
(`executor.py:2475`) **and** `host_runner.dispatch_batch_request(...)`
(`executor.py:2499`).

## Acceptance Criteria

- [ ] `_dispatch_live`'s SDK path passes all three values from config.
- [ ] `_dispatch_live`'s batch path passes all three values from config.
- [ ] `BRConfig` is constructed at most once per executor instance, not once per
      dispatch (assert via a spy on `BRConfig.__init__` across a multi-iteration run).
- [ ] Config root is `self.working_dir or Path.cwd()`, verified by a test that
      sets `working_dir` to a temp project with a non-default `ll-config.json`
      while cwd is elsewhere.
- [ ] With no `cache`/`deferred_tools` config present, the kwargs passed equal
      the current hardcoded defaults (no behavior change).
- [ ] `python -m pytest scripts/tests/` exits 0.

## Status

**Open** | Created: 2026-08-02 | Priority: P2

## Impact

- **Priority**: P2 — silent config no-op; a user who explicitly sets these
  values gets no effect and no warning.
- **Effort**: Small — one call site, additive kwargs.
- **Risk**: Low — passing explicit values that already match current defaults
  when unset is a no-op; only changes behavior when non-default config is set.
- **Breaking Change**: No.

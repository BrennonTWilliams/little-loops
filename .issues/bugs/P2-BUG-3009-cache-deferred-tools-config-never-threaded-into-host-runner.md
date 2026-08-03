---
id: BUG-3009
title: cache/deferred_tools config parsed but never threaded into host_runner dispatch
type: BUG
status: done
priority: P2
discovered_date: 2026-08-02
discovered_by: multi-agent-audit
completed_at: '2026-08-03T05:58:33Z'
parent: EPIC-3008
testable: true
labels:
- config
- host-runner
- fsm
confidence_score: 95
outcome_confidence: 83
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 25
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

- Exact current SDK-path call (`executor.py:2474-2481`):
  ```python
  if request_path == "sdk":
      return host_runner.dispatch_anthropic_request(
          action=action,
          system_prompt=None,
          tools=None,
          model=model,
          fragment_store=fragment_store,
      )
  ```
- Exact current batch-path call (`executor.py:2498-2506`):
  ```python
  batch_id = host_runner.dispatch_batch_request(
      custom_id=custom_id,
      action=action,
      system_prompt=None,
      tools=None,
      model=model,
      fragment_store=fragment_store,
  )
  ```
- `dispatch_anthropic_request`/`dispatch_batch_request` forward `require_repeat`, `defer_loading_threshold`, `search_tool_variant` unchanged into `build_anthropic_request`/`build_batch_request` (`host_runner.py:1904-1914`, `:1961-1972`) — the omission at the call site is the entire defect; no downstream code needs to change.

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
3. **Fold `executor.py:2010` onto the same accessor.** That site already
   constructs `BRConfig(self.working_dir or Path.cwd())` — the identical root
   expression the new accessor uses — and only reads `._raw_config` off it. Left
   alone, it becomes a second full parse of the same file in the same executor,
   which defeats the point of memoizing and makes the "constructed once" AC
   below unverifiable. Reading `._raw_config` from the memoized instance is
   behavior-identical.
4. Add tests asserting a non-default `ll-config.json` value changes the kwargs
   actually passed, via a spy/mock on `dispatch_anthropic_request` *and* on
   `dispatch_batch_request` (the batch path is easy to forget — it currently has
   the same gap).

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_dispatch_live` (line 2453 opens the method); SDK-path call at lines 2474-2481 currently passes only `action`, `system_prompt`, `tools`, `model`, `fragment_store`; batch-path call at lines 2498-2506 passes the identical subset. Neither passes `require_repeat`, `defer_loading_threshold`, or `search_tool_variant`.

### Conventions in Force
- `FSMExecutor` threads config objects derived from `BRConfig` into dispatch **only** via constructor-injected attributes set once at construction, not via a lazily-memoized in-method accessor — the two existing precedents are `self.compression_config` (set at `executor.py:247`) and `self.orchestration_config` (set at `executor.py:242`), both read directly at call sites (e.g. `self.orchestration_config.request_path` at `executor.py:2353`) and both re-propagated verbatim into sub-loop `FSMExecutor(...)` construction. Production wiring for these two happens at the CLI layer (`scripts/little_loops/cli/loop/run.py:571-581`), which resolves one `BRConfig` and passes its typed sub-configs down as constructor kwargs — not inside `executor.py` itself.
- No `functools.cached_property` or `if self._x is None: self._x = ...` lazy-init pattern exists anywhere for a config object in `FSMExecutor`; the one example of that shape in the codebase (`scripts/little_loops/state.py:114-119`, `StateManager.state`) is unrelated to config threading. `FSMExecutor` does have two eager-conditional-at-`__init__` attributes with the `X | None = None` shape (`self._host_guard`, `executor.py:375-377`; `self._stall_detector`, `executor.py:391-393`), constructed once at `__init__` time rather than lazily.
- A prior bug of this exact shape — parsed config never reaching its runtime consumer — is `BUG-2767` (`.issues/bugs/`, status `done`): "loop confidence thresholds ignore ll-config". Its fix added a dedicated seeding helper (`seed_confidence_thresholds`, `scripts/little_loops/cli/loop/_helpers.py`) called from three separate sites (`cli/loop/run.py`, `cli/loop/lifecycle.py`, and `fsm/executor.py::_execute_sub_loop`) rather than a single in-executor accessor, and explicitly declined to wire through an existing-but-inert override dataclass (`LoopConfigOverrides`, `fsm/schema.py:911-973`) to avoid "two competing config-read paths."

### Tests
- `scripts/tests/test_fsm_executor.py` — exercises `_dispatch_live` end-to-end via `FSMExecutor.run()`, patching `little_loops.host_runner.dispatch_anthropic_request` (conventionally bound as `mock_dispatch`) and `dispatch_batch_request` (conventionally bound as `mock_submit`); no existing case asserts `require_repeat`/`defer_loading_threshold`/`search_tool_variant`. Established kwargs-assertion idiom: `mock_dispatch.call_args.kwargs["model"] == "haiku"` (line 7565; same shape at 9988-9989, 10035, 10099 for the batch path via `mock_submit`).
- `scripts/tests/test_host_runner_dispatch.py` — exercises `dispatch_anthropic_request`/`dispatch_batch_request` in isolation (patches `anthropic.Anthropic`); does not touch `_dispatch_live` or `FSMExecutor`.
- No existing test in the repo patches `BRConfig.__init__` or asserts a call-count delta on it. The closest composable precedents: `patch.object(<module>, "<method>", wraps=<real_callable>)` for a count-preserving spy (e.g. `scripts/tests/test_ll_loop_display.py:1977-1992`, `mock_render.assert_called_once_with(...)`), and `patch.object(<Class>, "__init__", <capture_fn>)` for kwargs-on-construction capture (`scripts/tests/test_ll_loop_execution.py:710` et al., `capture_fsm_executor_init`) — no existing test composes these into a "run N dispatches, assert construction count unchanged" delta assertion.
- `scripts/tests/test_fsm_executor.py::TestExecutorWorkingDir` (~line 5490) is the existing "temp project, cwd elsewhere" shape (`FSMExecutor(fsm, working_dir=tmp_path)` constructed directly, real cwd left as pytest's cwd) — though its assertions cover shell-action cwd, not a `BRConfig` read from that root.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- No external callers/importers require changes — `ll-code --json importers-of scripts/little_loops/fsm/executor.py` returned zero hits (index freshness was `stale` at query time, so this negative was widened with an exploratory pass rather than trusted alone) and confirmed via agent trace: `_dispatch_live`'s only caller is `FSMExecutor._run_action` at `executor.py:1835`, internal to the same file. `executor.py:2010` (`_compact_continuity_summary`) is the one other in-file `BRConfig(self.working_dir or Path.cwd())` construction and is already covered by Suggested Fix Direction step 3.
- Constructor-injection call sites (`cli/loop/run.py:571-581`, `cli/loop/lifecycle.py:581-587`, `_execute_sub_loop`'s child-`FSMExecutor` propagation at `executor.py:1002-1005`) do **not** need changes under the memoized-accessor fix direction already decided in this issue (Suggested Fix Direction step 1) — they only apply if a constructor-injection pattern were chosen instead, which this issue explicitly rejected in favor of a lazily-memoized in-method accessor.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- Concrete existing patterns to model new SDK/batch kwargs-assertion tests after (same file, `scripts/tests/test_fsm_executor.py`, class `TestRequestPathDispatchWiring`): `test_request_path_sdk_calls_dispatch_not_cli` (~line 9954) patches `little_loops.host_runner.dispatch_anthropic_request` as `mock_dispatch` and co-patches `little_loops.fsm.executor.evaluate_llm_structured`; `test_request_path_batch_submits_polls_and_clears_tracker` (~line 10058) patches `little_loops.host_runner.dispatch_batch_request` as `mock_submit` plus `poll_batch_result`. New tests for AC 1/2 (kwargs reflect config) should extend these two, not invent new fixtures.
- `scripts/tests/test_config.py::TestBRConfigDeferredToolsIntegration` (~line 3056) is the fixture pattern for writing a non-default `{"deferred_tools": {...}}` into `temp_project_dir / ".ll" / "ll-config.json"` then asserting on a fresh `BRConfig(temp_project_dir)` — no parallel `TestBRConfigCacheIntegration` exists yet; the `cache` key follows the identical shape (`{"cache": {"require_repeat": False}}`).
- **Gap confirmed, not just unlisted**: no test anywhere in the repo does a call-count *delta* assertion on a constructor (grep for `BRConfig.*call_count` returns nothing). AC 2/3's "spy on `BRConfig.__init__`, assert delta unchanged across N dispatches" must be composed fresh from two existing-but-separate patterns: `patch.object(<module>, "<name>", wraps=<real_callable>)` (`scripts/tests/test_ll_loop_display.py:1977-1992`, single-call form only) and `patch.object(<Class>, "__init__", <capture_fn calling original_init>)` (`scripts/tests/test_ll_loop_execution.py:695-717`). Neither is a literal template — budget implementation time for this composition, it is not a copy-paste.
- `TestExecutorWorkingDir` (~line 5491, full class read) does **not** combine `working_dir=` with `monkeypatch.chdir()` to a different cwd — no existing test proves "config root resolves from `working_dir`, not real cwd." AC 4's test needs a new composition: `temp_project_dir`-style `.ll/ll-config.json` write + `FSMExecutor(fsm, working_dir=<project with non-default config>)` + `monkeypatch.chdir(<other tmp dir>)` before `executor.run()`.
- Confirmed via grep (`require_repeat|defer_loading_threshold|search_tool_variant` in `test_fsm_executor.py`): zero existing matches. No test currently asserts the buggy default kwargs, so nothing breaks/needs updating — every AC-listed test is net-new, not a modification.

### Documentation
- `CacheConfig`/`DeferredToolsConfig` docstrings (`scripts/little_loops/config/features.py:563-573`, `586-595`) both state these configs are "consulted only when `orchestration.request_path == 'sdk'`" — worth reconciling against this issue's direction to thread the same three kwargs into **both** the SDK path and the batch path.

## Program Design

### Signatures

- `dispatch_anthropic_request(*, action: str, model: str, fragment_store: FragmentStore, require_repeat: bool = True, defer_loading_threshold: int | None = None, search_tool_variant: str = "bm25") -> ActionResult`
- `dispatch_batch_request(*, custom_id: str, action: str, model: str, fragment_store: FragmentStore, require_repeat: bool = True, defer_loading_threshold: int | None = None, search_tool_variant: str = "bm25") -> str`

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

- [x] `_dispatch_live`'s SDK path passes all three values from config.
- [x] `_dispatch_live`'s batch path passes all three values from config.
- [x] The dispatch path adds **zero** additional `BRConfig` constructions per
      dispatch. Assert as a *delta*, not an absolute count: spy on
      `BRConfig.__init__`, record the count after the first dispatch, run N more
      dispatches, assert the count is unchanged.
      **Do not assert `call_count == 1`** — `FSMExecutor` legitimately constructs
      `BRConfig` at `executor.py:927`, `:1104`, `:1366`, and `:3137` for
      unrelated reads, so an absolute-count assertion is ambiguous at best and
      falsely red at worst.
- [x] `executor.py:2010` reads `_raw_config` off the memoized instance rather
      than constructing its own (per Suggested Fix Direction step 3), verified by
      the same spy: a run that exercises both that site and a dispatch adds one
      construction total, not two.
- [x] Config root is `self.working_dir or Path.cwd()`, verified by a test that
      sets `working_dir` to a temp project with a non-default `ll-config.json`
      while cwd is elsewhere.
- [x] With no `cache`/`deferred_tools` config present, the kwargs passed equal
      the current hardcoded defaults (no behavior change).
- [x] `python -m pytest scripts/tests/` exits 0 (4 pre-existing, unrelated
      failures from an uncommitted `ll-cli-logo.txt` change; the 5 new tests and
      the rest of the suite pass).

## Resolution

- **Action**: fix
- **Completed**: 2026-08-03
- **Status**: Completed

### Changes Made
- `scripts/little_loops/fsm/executor.py`: added memoized `_get_br_config()` accessor
  (backed by a new `self._br_config: BRConfig | None` set in `__init__`), resolved from
  `self.working_dir or Path.cwd()`; threaded `require_repeat`, `defer_loading_threshold`,
  `search_tool_variant` into both the SDK-path and batch-path `_dispatch_live` calls;
  `_compact_continuity_summary` now reads `._raw_config` off the same memoized instance
  instead of constructing its own `BRConfig`.
- `scripts/tests/test_fsm_executor.py`: added `TestCacheDeferredToolsDispatchWiring` with
  5 tests covering SDK-path/batch-path kwargs, default-unchanged behavior, working-dir-based
  config root, and a zero-extra-construction delta assertion via a `BRConfig.__init__` spy.

### Verification Results
- Tests: `python -m pytest scripts/tests/` — 18082 passed, 42 skipped, 4 failed (all 4
  failures are pre-existing/unrelated: an uncommitted `scripts/little_loops/assets/ll-cli-logo.txt`
  change present in the working tree before this fix, confirmed via `git diff --stat` on that
  file). All 5 new tests pass.
- Lint: `ruff check` on both changed files — PASS.
- Types: `mypy scripts/little_loops/fsm/executor.py` — PASS.

## Status

**Open** | Created: 2026-08-02 | Priority: P2

## Impact

- **Priority**: P2 — silent config no-op; a user who explicitly sets these
  values gets no effect and no warning.
- **Effort**: Small — one call site, additive kwargs.
- **Risk**: Low — passing explicit values that already match current defaults
  when unset is a no-op; only changes behavior when non-default config is set.
- **Breaking Change**: No.


## Session Log
- `/ll:manage-issue` - 2026-08-03T05:57:56 - `0694e364-9e14-488d-910b-9431457d2ad2.jsonl`
- `/ll:ready-issue` - 2026-08-03T05:49:08 - `e0ccf49b-9853-443a-af8d-8235729b1cff.jsonl`
- `/ll:confidence-check` - 2026-08-03T05:47:27 - `a33ef94d-4571-4021-85c6-af34ee40628f.jsonl`
- `/ll:wire-issue` - 2026-08-03T05:44:59 - `b7155231-1455-41f0-a8f9-2f05ecfdc485.jsonl`
- `/ll:refine-issue` - 2026-08-03T05:37:55 - `68d1f67f-baa2-4849-8579-5fd7868b229f.jsonl`

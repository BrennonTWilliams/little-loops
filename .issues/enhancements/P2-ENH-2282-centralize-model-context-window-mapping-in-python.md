---
id: ENH-2282
title: "Centralize model\u2192context-window mapping in Python and add 1M-context\
  \ support"
type: ENH
status: open
priority: P2
decision_needed: false
captured_at: '2026-06-25T00:18:53Z'
discovered_date: '2026-06-25'
discovered_by: capture-issue
labels:
- context-monitor
- context-window
- continuation
- guillotine
- refactor
relates_to:
- BUG-2280
- BUG-2054
- FEAT-812
confidence_score: 95
outcome_confidence: 74
score_complexity: 13
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-2282: Centralize model→context-window mapping in Python and add 1M-context support

## Summary

The context-window size used to drive handoff/guillotine decisions is resolved by
**two independent systems that share no code**, and neither correctly handles
1M-context models by the model identifier:

1. **Bash hook layer** (`hooks/scripts/context-monitor.sh`) — has a `get_context_limit()`
   model→window mapper (added by FEAT-812), but its lookup table predates 1M models:
   every `claude-*-4*` prefix maps to `200000` (`context-monitor.sh:135-136`), so the
   `case` is effectively a no-op. The only thing that ever yields `1000000` is a
   downstream **empirical heuristic** (`context-monitor.sh:296-300`) that bumps the
   limit when the measured transcript baseline exceeds 200k — reactive and guard-railed
   against corrupt reads (`<= 1100000`).

2. **Python automation layer** (`issue_manager.py`, `subprocess_utils.py`,
   `parallel/worker_pool.py`) — has **no** model→window mapping at all. `context_limit`
   is a hardcoded `200_000` default in ~4 signatures. The model *is* detected at
   runtime (`on_model_detected` → `_detected_model`, `issue_manager.py:1354-1357`) but
   the value is only logged and **thrown away** — it never sets `context_limit`.

This is the upstream cause behind the [[BUG-2280]] / [[BUG-2054]] cluster: both issues'
proposed fixes say "reuse the model→window mapping," but that mapping does not exist in
Python, and the bash one has no 1M entry to reuse.

The signal is already present in the model id — e.g. this session runs
`claude-opus-4-8[1m]`, where the `[1m]` suffix *is* the 1M marker.

## Motivation

- The default 200k window is wrong for any 1M-context session, throwing off every
  `usage / context_limit` percentage that drives sentinel writes and the Option J
  guillotine.
- Autonomous paths (`ll-auto`, `ll-parallel`, `ll-sprint`) never set the `--context-limit`
  override, so they silently run on the wrong denominator — exactly where BUG-2280 fired.
- Two divergent resolution systems mean a fix in one layer (FEAT-812, bash) doesn't
  reach the other (Python continuation path).

## Current Behavior

- Python `run_claude_with_continuation()` / `write_sentinel()` / worker pool all assume
  `context_limit = 200_000` regardless of the detected model.
- Bash `get_context_limit()` returns `200000` for all known models; 1M is only ever
  reached via the transcript-baseline auto-upgrade heuristic.
- No shared, model-keyed source of truth; `[1m]`-suffixed model ids are not recognized
  as 1M anywhere by identifier.

## Expected Behavior

- A single source of truth maps a detected model id → context-window size, recognizing
  the `[1m]` suffix (and any explicit 1M variants) as `1_000_000` and known Claude-4
  base ids as `200_000`, with a conservative fallback for unknown models.
- The Python continuation/sentinel path sets `context_limit` from the **detected** model
  (via the existing `on_model_detected` callback) instead of the hardcoded default.
- The bash hook and Python path agree on the same mapping (shared, or one delegates).
- Explicit override (`--context-limit` / `LL_CONTEXT_LIMIT` /
  `context_monitor.context_limit_estimate`) retains top precedence.

## API/Interface

Add a Python helper (single source of truth), e.g.:

```python
def context_window_for(model: str | None, override: int | None = None) -> int:
    """Resolve context-window size for a model id. Precedence:
    explicit override → model-id lookup ([1m] suffix → 1M, known base → 200k)
    → conservative 200k floor."""
```

Wire it into the `on_model_detected` callback in `issue_manager.py` so `context_limit`
is derived from the detected model. Keep the empirical auto-upgrade as a fallback when
the id is stripped/unknown.

## Proposed Solution

Implement option **A** (static model→window lookup in Python), structured to allow the
full hybrid later:

1. Add `context_window_for()` as the single source of truth (precedence: override →
   `[1m]` suffix / known-id lookup → 200k floor).
2. Feed it from the already-detected model in `issue_manager.py` so the continuation
   path, `write_sentinel()`, and `worker_pool.py` use the model-correct limit instead
   of `200_000`.
3. Replace the dead bash `case` in `context-monitor.sh:get_context_limit()` with the
   same table (add the `[1m]`/1M entry), or have the hook delegate to the Python helper,
   so the two layers can't diverge again.
4. Keep the empirical transcript auto-upgrade heuristic as a fallback under the lookup.

## Implementation Steps

1. **New file: `scripts/little_loops/context_window.py`** — add `context_window_for(model, override=None)` with precedence: `override` arg → `LL_CONTEXT_LIMIT` env var → `[1m]`-suffix / known-id lookup → 200k floor. Add unit tests in `scripts/tests/test_context_window.py` covering `[1m]` → 1M, known base → 200k, `None` → 200k, override-arg wins, env-var override wins.

2. **`scripts/little_loops/issue_manager.py`: add `context_limit` to `process_issue_inplace()`**
   - Add `context_limit: int = 200_000` parameter to `process_issue_inplace()`.
   - Pass it through to the `run_with_continuation()` call inside Phase 2.
   - In `AutoManager._process_issue()`, after the model is stored in `self._detected_model`, derive `resolved_limit = context_window_for(self._detected_model[0] if self._detected_model else None)` and pass it as `context_limit=resolved_limit` to `process_issue_inplace()`.

3. **`scripts/little_loops/subprocess_utils.py:write_sentinel()`** — change parameter default from `200_000` to `context_window_for()` call, or keep the default and rely on callers always passing the resolved value. The `assemble_guillotine_prompt()` fallback `200_000` at line 190 also needs updating to `context_window_for()`.

4. **`scripts/little_loops/parallel/worker_pool.py:WorkerPool._run_with_continuation()`** — read `LL_CONTEXT_LIMIT` via `context_window_for(None)` (which checks the env var as override) rather than threading `on_model_detected` through the worker infrastructure. Change the default `200_000` at line 831 to `context_window_for(None)`.

5. **`hooks/scripts/context-monitor.sh:get_context_limit()`** — add a `[1m]`-suffix branch: `claude-*\[1m\]) echo 1000000 ;;` before the existing `claude-*-4*` branches, so the identifier-based path reaches 1M without relying solely on the transcript auto-upgrade heuristic.

6. **Re-check threshold economics at 1M**: sentinel fires at `0.60 * 1_000_000 = 600k` tokens; guillotine at `0.90 * 1_000_000 = 900k`. Confirm in tests that these thresholds compose correctly with the BUG-2280 fix (which stops conflating cumulative tokens with window occupancy); the denominators are independent so composition should be clean.

7. Run `python -m pytest scripts/tests/` + `ruff check scripts/` + `python -m mypy scripts/little_loops/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. **Update `hooks/scripts/context-handoff-sentinel.sh`** — replace hardcoded `200000` fallback (lines 65/67) with a `get_context_limit "$MODEL"` call (or the same `LL_CONTEXT_LIMIT`-first guard used in `context-monitor.sh:266`) so the sentinel correctly handles 1M-context sessions even when the state file is absent
9. **Update `scripts/tests/test_hooks_integration.py`** — add a test that invokes the bash `get_context_limit()` (or the hook) with a `claude-opus-4-8[1m]` model and asserts the output is `1000000`; existing non-1M assertions (line 361-362) are safe and require no changes
10. **Update description text in 4 locations** (minor prose only):
    - `docs/reference/CONFIGURATION.md:445` — add "`[1m]`-suffixed models resolve to 1M by identifier"
    - `docs/guides/SESSION_HANDOFF.md:307` — same clause
    - `docs/guides/BUILTIN_HOOKS_GUIDE.md:242` — same clause
    - `config-schema.json:706` — update `context_limit_estimate` description to mention `[1m]` suffix

## Success Metrics

- `context_window_for("claude-opus-4-8[1m]")` → `1_000_000` (unit test passes)
- `context_window_for("claude-opus-4-8")` → `200_000` (unit test passes)
- `context_window_for(None)` → `200_000` conservative fallback (unit test passes)
- Explicit override argument wins over model-id lookup (unit test passes)
- Bash `get_context_limit()` and Python `context_window_for()` return the same value for all tested model IDs
- All existing `python -m pytest scripts/tests/` pass; `ruff check` and `mypy` clean

## Scope Boundaries

- **In scope**: Adding `context_window_for()` as the single Python source of truth; wiring it into `on_model_detected` → `context_limit` in `issue_manager.py`; updating `subprocess_utils.py` and `parallel/worker_pool.py` hardcoded `200_000` references; updating `hooks/scripts/context-monitor.sh:get_context_limit()` to recognize `[1m]` and explicit 1M model variants.
- **Out of scope**: Changing sentinel (0.60) or guillotine (0.90) threshold *percentages* — only the denominator changes; rearchitecting the empirical transcript auto-upgrade heuristic (kept as fallback); fixing cumulative-token conflation in BUG-2280 (separate fix, must compose cleanly); host CLI invocation changes.

## Integration Map

### Files to Modify
- `scripts/little_loops/context_window.py` (new) — `context_window_for()` helper and model lookup table
- `scripts/little_loops/issue_manager.py` — wire `context_window_for()` into `on_model_detected`; update `run_claude_with_continuation` and `process_issue_inplace` to use model-resolved `context_limit`
- `scripts/little_loops/subprocess_utils.py` — replace hardcoded `200_000` default with `context_window_for()` call
- `scripts/little_loops/parallel/worker_pool.py` — replace hardcoded `200_000` default with `context_window_for()` call
- `hooks/scripts/context-monitor.sh` — update `get_context_limit()` to add `[1m]` → `1000000` entry (or delegate to Python helper)

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/scripts/context-handoff-sentinel.sh` — hardcoded `200000` fallback at lines 65/67; used when state file is absent or `context_limit` key is missing; once `context-monitor.sh` correctly writes `1000000` for `[1m]` models to the state file, the sentinel reads it correctly — but the fallback itself should also be updated to call `get_context_limit()` so out-of-order invocations don't regress [Agent 1 finding]

### Dependent Files (Callers/Importers)

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Hardcoded `200_000` parameter defaults (need updating):**
- `scripts/little_loops/issue_manager.py:210` — `run_with_continuation()` parameter `context_limit: int = 200_000`
- `scripts/little_loops/subprocess_utils.py:126` — `write_sentinel()` parameter `context_limit: int = 200_000`
- `scripts/little_loops/subprocess_utils.py:190` — `assemble_guillotine_prompt()` dict fallback `token_stats.get("context_limit", 200_000)`
- `scripts/little_loops/parallel/worker_pool.py:831` — `WorkerPool._run_with_continuation()` parameter `context_limit: int = 200_000`

**Functions that call `run_with_continuation()` / `_run_with_continuation()` without passing `context_limit` (critical wiring gap):**
- `scripts/little_loops/issue_manager.py:process_issue_inplace()` — calls `run_with_continuation()` with no `context_limit` arg and has no `context_limit` parameter itself; the entire Phase 2 continuation path uses the 200k default
- `scripts/little_loops/parallel/worker_pool.py:WorkerPool._process_issue()` — calls `_run_with_continuation()` with no `context_limit` arg; `WorkerPool` has no `on_model_detected` plumbing at all

**CLI files that set `LL_CONTEXT_LIMIT` env var (already exist, no changes needed):**
- `scripts/little_loops/cli/auto.py:86` — sets `os.environ["LL_CONTEXT_LIMIT"]` from `--context-limit` arg
- `scripts/little_loops/cli/parallel.py:203` — same
- `scripts/little_loops/cli/sprint/run.py:263` — same
- `scripts/little_loops/cli/loop/run.py:192` — same

**Note**: `LL_CONTEXT_LIMIT` is set by all CLIs but is **never consumed** by `issue_manager.py` or `worker_pool.py` — those files use function-parameter defaults only. `context_window_for()` should read `LL_CONTEXT_LIMIT` as its override source so the env-var path finally connects to the Python continuation logic.

### Similar Patterns
- `hooks/scripts/context-monitor.sh:get_context_limit()` — existing bash mapper (lines 129-136); align table entries; the `LL_CONTEXT_LIMIT` env var check precedes `get_context_limit()` at line 266
- `scripts/little_loops/issue_manager.py:AutoManager._process_issue()` — `on_model_detected` closure at line 1354; model is stored in `self._detected_model` list but only logged (line 1357) and never used to derive `context_limit`
- `scripts/little_loops/subprocess_utils.py:run_claude_command()` — fires `on_model_detected(event["model"])` when the `system/init` event is parsed (line 421); this is the model-detection source
- **`scripts/little_loops/pricing.py:MODEL_PRICING` + `estimate_cost_usd()`** — closest structural match to `context_window_for()`: module-level `dict[str, ...]` keyed on exact model-id strings, single public lookup function, returns `None` for unknown models; model new `context_window.py` after this module
- **`scripts/tests/test_pricing.py:TestModelPricing` + `TestEstimateCostUsd`** — direct test template: `test_known_models_present`, `test_unknown_model_returns_none`, `test_zero_tokens_returns_zero` — model `test_context_window.py` classes after this
- **`scripts/tests/conftest.py:_restore_cmd_run_env_vars`** — already cleans up `LL_CONTEXT_LIMIT` in an autouse fixture (line 484); tests for `context_window_for()` that set `LL_CONTEXT_LIMIT` should use `monkeypatch.setenv("LL_CONTEXT_LIMIT", "1000000")` and this fixture auto-restores

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical wiring gap: `process_issue_inplace()` has no `context_limit` parameter**

`process_issue_inplace()` in `issue_manager.py` does not accept `context_limit`. Its `run_with_continuation()` call omits the argument, so Phase 2 (the main manage-issue implementation run) always uses the 200k default regardless of any upstream resolution. Implementation Step 2 must add `context_limit` to `process_issue_inplace()` before the wiring to `on_model_detected` can flow through.

**`AutoManager._detected_model` is captured but never read back**

In `AutoManager._process_issue()`, the `on_model` closure appends to `self._detected_model` for the first issue only; subsequent issues pass `on_model=None`. The stored model name is never subsequently read — no code reads `self._detected_model[0]` to inform `context_limit`. The fix: read `self._detected_model[0]` after the first invocation and pass `context_window_for(self._detected_model[0])` as `context_limit` to `process_issue_inplace()`.

**`WorkerPool` has no model detection at all**

`WorkerPool._run_with_continuation()` has no `on_model_detected` parameter and `_process_issue()` never detects the model. The simplest fix for `worker_pool.py` is to read `int(os.environ.get("LL_CONTEXT_LIMIT", 0)) or context_window_for(None)` — callers already set `LL_CONTEXT_LIMIT` via CLI, and `context_window_for()` can read it as its override source, avoiding the need to plumb `on_model_detected` through the worker infrastructure.

**`assemble_guillotine_prompt()` also has a hardcoded 200k fallback**

`subprocess_utils.assemble_guillotine_prompt()` reads `context_limit = token_stats.get("context_limit", 200_000)`. This fallback will be correct once callers pass the model-resolved value through `token_stats`, but the dict key `"context_limit"` must be populated upstream — which it is, via `run_with_continuation()` at line 397.

**Bash auto-upgrade heuristic at lines 295-299 in `context-monitor.sh`**

The heuristic bumps `CONTEXT_LIMIT` to `1000000` when the measured transcript baseline exceeds the current `CONTEXT_LIMIT` but is `<= 1100000`. Once the static `get_context_limit()` table is corrected (to return `1000000` for `[1m]` models by identifier), the heuristic becomes a fallback for model IDs with stripped suffixes rather than the primary detection path.

### Tests
- `scripts/tests/test_context_window.py` (new) — cover `[1m]` suffix → 1M, known base → 200k, unknown → 200k floor, override-arg precedence, `LL_CONTEXT_LIMIT` env-var precedence
- `scripts/tests/test_subprocess_utils.py` — existing; has tests for `write_sentinel()` and `on_model_detected` callback; add assertions for model-resolved `context_limit` in sentinel output
- `scripts/tests/test_issue_manager.py` — existing; covers `run_with_continuation()` with `context_limit` and `_detected_model` caching; add tests that `context_limit` is derived from `_detected_model` once detected
- `scripts/tests/test_worker_pool.py` — existing; covers `_run_with_continuation()` with `context_limit` defaults; add test that `LL_CONTEXT_LIMIT` env var reaches the worker path via `context_window_for()`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hooks_integration.py` — existing; tests `context-monitor.sh` hook with `claude-sonnet-4-6` and asserts `200000` output (line 361-362); no `[1m]` model test exists — add a test that `get_context_limit("claude-opus-4-8[1m]")` returns `1000000` via the bash hook path [Agent 1/3 finding]

### Documentation
- `docs/reference/API.md` — add `context_window_for()` to Python API reference

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:445` — describes "known Claude 4 models → 200000; auto-upgrades to 1M when transcript baseline indicates it"; after this ENH, `[1m]`-suffixed models resolve to 1M by identifier — add a clause about `[1m]` suffix recognition [Agent 2 finding]
- `docs/guides/SESSION_HANDOFF.md:307` — same description gap: "auto-detection (known Claude 4 models → 200000; baseline exceeding that auto-upgrades to 1000000)"; needs `[1m]` suffix clause [Agent 2 finding]
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:242` — `context_monitor.context_limit_estimate` description: "upgrades to 1M when the transcript baseline indicates it" now incomplete; add "or when the model id carries a `[1m]` suffix" [Agent 2 finding]

### Configuration
- N/A — override via `LL_CONTEXT_LIMIT` / `context_monitor.context_limit_estimate` already documented

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json:706` — `context_limit_estimate` description says "known claude-*-4* variants → 200000; if transcript baseline exceeds that, auto-upgrades to 1000000"; needs clause about `[1m]`-suffix → 1M by identifier, not only by transcript heuristic [Agent 2 finding]

## Impact

- **Severity**: Medium-high. Root cause feeding a P1 (BUG-2280) and a P2 (BUG-2054);
  affects every autonomous path's handoff math on 1M-context sessions.
- **Effort**: Small–medium. The detection plumbing already exists; this wires it through
  and centralizes the table.
- **Risk**: Low. Override precedence and the empirical fallback preserve current behavior
  for unknown models.
- **Breaking change**: No.

## Related

- [[BUG-2280]] — Option J guillotine conflates cumulative tokens with window occupancy;
  its fix references reusing the model→window mapping this ENH creates.
- [[BUG-2054]] — context-monitor hook 200k-denominator misreport (sibling metric bug).
- [[FEAT-812]] — auto-detect model from JSONL to select context limit (**done**; built
  the bash `get_context_limit()` but predates 1M models and never touched the Python
  layer — this ENH extends both).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-24_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- Wide change surface (16 files across 4 subsystems) — implement using the enumerated Integration Map checklist; the 5 doc-clause additions (CONFIGURATION.md, SESSION_HANDOFF.md, BUILTIN_HOOKS_GUIDE.md, API.md, config-schema.json) are easy to miss.
- Two implementation steps have alternative paths without selection — step 3 (subprocess_utils.py default-change vs. rely-on-callers-always-passing) and step 5 (static bash table entry vs. Python delegation) should each be resolved at implementation start.

## Session Log
- `/ll:confidence-check` - 2026-06-24T00:00:00Z - `5c0be5b3-5eab-46ac-aee6-ef4d793bf8fc.jsonl`
- `/ll:wire-issue` - 2026-06-25T02:48:07 - `a3a3017d-2eaa-4766-b353-55d8b52bace7.jsonl`
- `/ll:refine-issue` - 2026-06-25T02:31:07 - `34b26a5a-d832-46f8-b8fa-760681ae32d9.jsonl`
- `/ll:format-issue` - 2026-06-25T00:26:13 - `39a6da98-eb0c-4e9f-8e70-0cee870a1dfe.jsonl`
- `/ll:capture-issue` - 2026-06-25T00:18:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42cd21cf-d24a-49c4-84ab-8bc13878f6f0.jsonl`

---

## Status

open

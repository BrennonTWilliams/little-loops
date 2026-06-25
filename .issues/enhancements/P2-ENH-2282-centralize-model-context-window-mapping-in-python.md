---
id: ENH-2282
title: Centralize model→context-window mapping in Python and add 1M-context support
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
relates_to: [BUG-2280, BUG-2054, FEAT-812]
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

1. Add `context_window_for()` (with tests for `[1m]` → 1M, known base → 200k, unknown →
   200k, override wins).
2. Thread the detected model into `context_limit` resolution in `issue_manager.py`
   (`run_claude_with_continuation` and the `process_issue_inplace` path) and
   `parallel/worker_pool.py`.
3. Update `context-monitor.sh:get_context_limit()` to add the 1M/`[1m]` entry (or
   delegate), so the bash layer matches.
4. **Re-check threshold economics at 1M**: the guillotine/sentinel fire at
   `0.90 * limit`, so the absolute trigger moves from 180k to 900k tokens — confirm the
   sentinel (`sentinel_threshold`, default 0.60) and guillotine (0.90) thresholds still
   behave sensibly, and that this composes with the BUG-2280 fix (which separately stops
   conflating cumulative tokens with window occupancy).
5. Run `python -m pytest scripts/tests/` + `ruff check scripts/` + mypy.

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

### Dependent Files (Callers/Importers)
- TBD — `grep -r "context_limit" scripts/little_loops/` to find all callers
- TBD — `grep -r "200_000\|200000" scripts/little_loops/` to find hardcoded fallbacks

### Similar Patterns
- `hooks/scripts/context-monitor.sh:get_context_limit()` — existing bash mapper; align table entries
- `issue_manager.py:on_model_detected` — existing callback; threading pattern to reuse

### Tests
- `scripts/tests/test_context_window.py` (new) — cover `[1m]` suffix → 1M, known base → 200k, unknown → 200k floor, override precedence

### Documentation
- `docs/reference/API.md` — add `context_window_for()` to Python API reference

### Configuration
- N/A — override via `LL_CONTEXT_LIMIT` / `context_monitor.context_limit_estimate` already documented

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

## Session Log
- `/ll:format-issue` - 2026-06-25T00:26:13 - `39a6da98-eb0c-4e9f-8e70-0cee870a1dfe.jsonl`
- `/ll:capture-issue` - 2026-06-25T00:18:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42cd21cf-d24a-49c4-84ab-8bc13878f6f0.jsonl`

---

## Status

open

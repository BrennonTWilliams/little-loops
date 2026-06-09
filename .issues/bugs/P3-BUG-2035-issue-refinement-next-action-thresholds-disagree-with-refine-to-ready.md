---
id: BUG-2035
type: BUG
priority: P3
status: open
captured_at: '2026-06-08T00:00:00Z'
discovered_date: 2026-06-08
discovered_by: audit-loop-run
relates_to:
  - BUG-2034
---

# BUG-2035: issue-refinement and refine-to-ready-issue use disagreeing readiness thresholds

## Summary

The two halves of the refinement loop resolve readiness/outcome thresholds from
different sources with different fallbacks, so neither reliably honors
`commands.confidence_gate` in `.ll/ll-config.json`:

- The selector — `issue-refinement.yaml` calling `ll-issues next-action` — **ignores
  config entirely** and uses the CLI argparse defaults `ready_threshold=85` /
  `outcome_threshold=70` (`next_action.py:32-34`, `cli/issues/__init__.py:477-490`).
- The sub-loop — `refine-to-ready-issue.yaml` — **reads config** via
  `check_readiness`/`check_outcome` but falls back to `readiness_threshold=90` /
  `outcome_threshold=75` (`refine-to-ready-issue.yaml:17-18`) when a key is absent.

Both should source thresholds from `commands.confidence_gate`, and when a key is
absent both should fall back to the **same** pair. The agreed fallback pair is
**85 / 70**. A working precedent for this resolution already exists in the
codebase: `ll-issues check-readiness` (`cli/issues/check_readiness.py:33-41`)
reads `commands.confidence_gate` first and falls back to its CLI args — that is
the pattern to copy.

This mismatch is part of why borderline issues churn (see BUG-2034): the selector
and the sub-loop never agree on what "ready" means, so an issue can sit in a band
where one half keeps working it while the other considers it done.

## Current Behavior

Live config today sets only `commands.confidence_gate.readiness_threshold: 85` —
there is **no** `outcome_threshold` key. Under that config:

| Threshold | Selector (`next-action`) | Sub-loop (`refine-to-ready`) | Agree? |
|-----------|--------------------------|------------------------------|--------|
| readiness | 85 (argparse default; config ignored) | 85 (read from config) | ✅ by coincidence |
| outcome   | 70 (argparse default; config ignored) | 75 (config key absent → fallback) | ❌ 70 vs 75 |

- Readiness agrees only by accident: the selector's hardcoded default (85) happens
  to equal the config value the sub-loop reads. Change `readiness_threshold` in
  config and the selector won't follow — they immediately diverge.
- Outcome already diverges today (70 vs 75) because the config has no
  `outcome_threshold`, and the two fallbacks differ.

## Expected Behavior

Both the selector and the sub-loop resolve readiness/outcome thresholds from
`commands.confidence_gate` in `.ll/ll-config.json`. When a key is absent, **both**
fall back to the same hardcoded pair — **readiness 85 / outcome 70**. For any given
config, "`next-action` says this issue still needs work" and
"`refine-to-ready-issue` considers this issue done" resolve against identical
numbers.

## Steps to Reproduce

1. Use the current `.ll/ll-config.json` (sets `confidence_gate.readiness_threshold:
   85`, no `outcome_threshold`).
2. Start `issue-refinement` against a backlog containing an issue whose
   `outcome_confidence` is in the 70–74 range (and readiness ≥ 85).
3. Observe: `ll-issues next-action` treats the issue as done (its outcome bar is 70).
4. Observe: `refine-to-ready-issue` treats the same issue as **not** done (its
   outcome bar falls back to 75) and keeps iterating.
5. Config-override divergence: set `commands.confidence_gate.readiness_threshold:
   90`. The sub-loop picks up 90; `next-action` stays at its hardcoded 85. Selector
   and sub-loop now disagree even when config is explicit.

## Root Cause

- **Selector**: `ll-issues next-action` never reads `commands.confidence_gate`. Its
  thresholds come only from argparse (`cli/issues/__init__.py:477-490`, defaults
  85/70) consumed in `get_next_action_data()` (`next_action.py:32-34`). The
  `issue-refinement.yaml` `evaluate` state calls it with no threshold flags, so the
  hardcoded defaults always win.
- **Sub-loop**: `refine-to-ready-issue.yaml` reads `commands.confidence_gate` in its
  `check_readiness`/`check_outcome` Python blocks, but its context fallbacks are
  90/75 (`refine-to-ready-issue.yaml:17-18`) — different from the selector's 85/70.
- **Net**: two independent resolution paths, two different fallback pairs, and one
  of them (the selector) doesn't consult config at all. A working single-source
  pattern already exists in `check_readiness.py` but `next-action` doesn't use it.

## Motivation

Without a shared, config-first resolution the selector and sub-loop disagree on the
finish line, producing the churn described in BUG-2034: the sub-loop pushes an
issue past a bar the selector doesn't share (or vice versa), and the loop wastes
iterations re-selecting "done" issues. Making `commands.confidence_gate` the single
source of truth for both halves — with matching 85/70 fallbacks — eliminates the
disagreement band and makes loop termination coherent.

## Proposed Solution

Make both halves resolve thresholds config-first with matching 85/70 fallbacks,
reusing the established `check_readiness.py` pattern.

1. **Selector (`next_action.py`)** — read `commands.confidence_gate` from config,
   falling back to the argparse `ready_threshold`/`outcome_threshold` (which stay
   85/70). Mirror `cli/issues/check_readiness.py:33-41` exactly:

   ```python
   default_ready = getattr(args, "ready_threshold", 85)
   default_outcome = getattr(args, "outcome_threshold", 70)
   config_path = config.project_root / ".ll" / "ll-config.json"
   try:
       cg = json.loads(config_path.read_text()).get("commands", {}).get("confidence_gate", {})
       ready_threshold = cg.get("readiness_threshold", default_ready)
       outcome_threshold = cg.get("outcome_threshold", default_outcome)
   except Exception:
       ready_threshold, outcome_threshold = default_ready, default_outcome
   ```

   No change to `issue-refinement.yaml` is required — its existing no-flag
   `next-action` call now honors config automatically, like every other
   `next-action` caller.

2. **Sub-loop (`refine-to-ready-issue.yaml`)** — change the context fallbacks from
   90/75 to **85/70** so the absent-config fallback matches the selector:

   ```yaml
   context:
     readiness_threshold: 85   # canonical: commands.confidence_gate.readiness_threshold in ll-config.json
     outcome_threshold: 70     # canonical: commands.confidence_gate.outcome_threshold in ll-config.json
   ```

   (Update the four read-sites that reference `${context.readiness_threshold}` /
   `${context.outcome_threshold}` only if they restate the numbers in comments.)

After this, with the live config (readiness 85, no outcome) both halves resolve to
**85 / 70**; adding `outcome_threshold` to config moves both in lockstep.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/next_action.py` — `get_next_action_data()`: read
  `commands.confidence_gate.{readiness,outcome}_threshold` from config, falling back
  to the argparse defaults (85/70). This is a defaults change for *all* `next-action`
  callers, intentionally making config the single source of truth.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `context`: change
  `readiness_threshold` 90→85 and `outcome_threshold` 75→70 so the absent-config
  fallback matches the selector.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/issue-refinement.yaml` — `evaluate` state: no change
  needed; its no-flag `next-action` call inherits the new config-first behavior.
- `scripts/little_loops/cli/issues/__init__.py:477-490` — `next-action` argparse:
  the `--ready-threshold`/`--outcome-threshold` defaults (85/70) become the
  *fallback* layer; leave them as-is.

### Similar Patterns
- `scripts/little_loops/cli/issues/check_readiness.py:33-41` — canonical config-first
  resolution to copy verbatim.

### Tests
- `scripts/tests/` (next-action coverage) — add a test asserting `get_next_action_data()`
  reads `commands.confidence_gate` and falls back to 85/70 when keys are absent.
- `scripts/tests/test_builtin_loops.py` — assert `refine-to-ready-issue.yaml` context
  fallbacks are 85/70.

### Documentation
- N/A

### Configuration
- `.ll/ll-config.json` — `commands.confidence_gate.readiness_threshold` /
  `commands.confidence_gate.outcome_threshold` (single source of truth after fix;
  `outcome_threshold` currently absent → falls back to 70 for both halves).

## Implementation Steps

1. In `next_action.py`, resolve `ready_threshold`/`outcome_threshold` config-first
   (mirror `check_readiness.py:33-41`), falling back to the argparse defaults 85/70.
2. In `refine-to-ready-issue.yaml`, change the context fallbacks to 85 / 70.
3. Confirm both halves now resolve to identical numbers under (a) current config
   (85 / 70) and (b) config with explicit `readiness_threshold`/`outcome_threshold`.
4. Run `ll-loop validate issue-refinement` and `ll-loop validate refine-to-ready-issue`
   to confirm no new FSM violations.
5. Add the unit tests above.

## Acceptance Criteria

- [ ] `next-action` and `refine-to-ready-issue` resolve to identical
      readiness/outcome thresholds for the same config (config value when present;
      85/70 fallback when absent).
- [ ] With default config, an issue the sub-loop considers "done" is not
      immediately re-selected by `next-action` (and vice versa).
- [ ] `next-action` reads `commands.confidence_gate` from `.ll/ll-config.json`
      (previously ignored it).
- [ ] The selector and sub-loop fallbacks match (85 / 70); the divergent 90/75
      sub-loop fallback is gone.

## Scope Boundaries

- Makes `commands.confidence_gate` the single source of truth for both the selector
  and the sub-loop, with matching 85/70 fallbacks. The `next-action` CLI argparse
  default values stay 85/70 — but they move from "the only source" to "the fallback
  layer," which changes resolved behavior for any caller that relied on config being
  ignored. This is intentional and the point of the fix.
- Does not change the sub-loop's routing or `max_refine_count`.

## Files

- `scripts/little_loops/cli/issues/next_action.py:32-34` — selector thresholds
  (make config-first)
- `scripts/little_loops/cli/issues/check_readiness.py:33-41` — canonical config-first
  pattern to copy
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:17-18` — sub-loop fallbacks
  (90/75 → 85/70)
- `scripts/little_loops/loops/issue-refinement.yaml:17-18` — `evaluate` state
  (no change; inherits config-first behavior)

## Impact

- **Priority**: P3 — coherence/correctness defect that compounds the BUG-2034
  churn; not independently fatal.
- **Effort**: Small — one CLI function + one loop-context edit.
- **Risk**: Low. `next-action` callers that omitted config now honor it; fallback
  stays 85/70 so behavior is unchanged when config is absent.
- **Breaking Change**: No (resolved thresholds shift only when config is set).

## Labels

`loops`, `issue-refinement`, `bug`, `captured`, `from-audit`

## Status

**Open** | Created: 2026-06-08 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-09T02:41:48 - `2e851901-2808-4980-9585-6d4994df06a4.jsonl`
</content>
</invoke>

---
id: ENH-1445
priority: P2
type: ENH
parent: ENH-1442
decision_needed: false
confidence_score: 100
outcome_confidence: 94
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 25
status: done
completed_at: 2026-05-11T20:01:30Z
---

# ENH-1445: Goals Discovery — Hook Warning Fix + Test Update

## Summary

Downgrade or remove the false-alarm warning in `hooks/scripts/session-start.sh` that fires when `ll-goals.md` is absent and `product.enabled: true`. After the discovery fallback introduced in ENH-1444, a missing `ll-goals.md` is valid — the hook should no longer treat it as a warning condition.

## Current Behavior

`hooks/scripts/session-start.sh` `validate_enabled_features()` (lines 134–143) emits `[little-loops] Warning: product.enabled is true but goals file not found: $goals_file` to stderr when `product.enabled: true` and `ll-goals.md` is absent. Since ENH-1444 introduced a discovery fallback that synthesizes goals from existing project docs, this warning fires on every session for any project with `product.enabled: true` but no hand-authored goals file — a false alarm by design.

## Expected Behavior

No warning or error when `product.enabled: true` and `ll-goals.md` is absent. The absence of the file is a valid, expected state; goals are auto-discovered from project documentation.

## Parent Issue

Decomposed from ENH-1442: Goals Discovery — Core Implementation (scan-product, product-analyzer, hooks, tests)

## Files to Modify

- `hooks/scripts/session-start.sh:134–143` — `validate_enabled_features()` product block; downgrade `"Warning: product.enabled is true but goals file not found"` to an informational `Note:` or remove the block entirely
- `scripts/tests/test_hooks_integration.py:1649` — `test_warns_product_without_goals`; update to assert new informational message or remove if warning block is dropped

## Implementation Steps

1. **Update `hooks/scripts/session-start.sh`** — In `validate_enabled_features()` lines 134–143: the block reads `product.enabled` + `product.goals_file`, then runs `[ ! -f "$goals_file" ]` and echoes `"[little-loops] Warning: product.enabled is true but goals file not found: $goals_file"` to stderr. Change to:
   - Option A (preferred): emit `[little-loops] Note: ll-goals.md not found — goals will be synthesized from discovered docs`
   - Option B: remove the block entirely

> **Selected:** Option B — remove the block entirely; a missing `ll-goals.md` is now a valid, expected state post-ENH-1444, making the warning a false alarm with no informational value.

2. **Update `scripts/tests/test_hooks_integration.py:1649`** — `test_warns_product_without_goals` (lines 1649–1669): update assertion to match new informational message if kept, or remove the test if the warning block is dropped

3. **Verify `scripts/tests/test_hooks_integration.py:1671`** — `test_no_warnings_when_properly_configured`: stays green post-change; if Option A (Note message retained), consider whether a new assertion for the `Note:` message is needed or whether the test remains a meaningful smoke test

4. **Run tests**: `python -m pytest scripts/tests/test_hooks_integration.py -v -k "product"`

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-11.

**Selected**: Option B — Remove the warning block entirely

**Reasoning**: ENH-1444 made a missing `ll-goals.md` a valid, expected state — goals are now synthesized from discovered docs when the file is absent. Continuing to warn about this condition generates false alarms by design. Option B is a clean deletion with no new infrastructure: all remaining tests pass unchanged, and the `Note:` severity level introduced by Option A has no existing precedent in hook-emitted output (informational messages use plain `[little-loops] <statement>` without a severity token).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (Note message) | 1/3 | 2/3 | 3/3 | 2/3 | 8/12 |
| Option B (remove block) | 2/3 | 3/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- Option A: `Note:` severity token is novel — zero `echo "[little-loops] Note: ..."` occurrences in any hook script; informational messages use plain format without severity labels
- Option B: Pure deletion of 10 shell lines + 21 test lines; all 4 remaining product tests pass unchanged; `product` block is the only filesystem-state check in `validate_enabled_features()` — its premise changed with ENH-1444

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/reference/CONFIGURATION.md` — revise `### product` section line 327 to note that `ll-goals.md` is optional when `product.enabled: true`; goals are auto-discovered from project documentation if absent

## Acceptance Criteria

- Hook no longer emits a false-alarm `Warning:` when `ll-goals.md` is absent and `product.enabled: true`
- `test_hooks_integration.py` product tests pass with updated or removed assertions

## Scope Boundaries

- Only the `product.enabled` warning block (lines 134–143) is removed; the `sync.enabled` (lines 112–121) and `documents.enabled` (lines 123–132) warning blocks are intentionally unchanged — those checks test configuration keys, not filesystem state
- No changes to the goals discovery logic introduced by ENH-1444
- No changes to `docs/reference/CONFIGURATION.md` beyond updating the `### product` prose to note that `ll-goals.md` is optional

## Codebase Reference

- `hooks/scripts/session-start.sh:134–143` — current warning block
- `scripts/tests/test_hooks_integration.py:1649–1669` — `test_warns_product_without_goals`
- `scripts/tests/test_hooks_integration.py:1671` — `test_no_warnings_when_properly_configured`

## Integration Map

### Files to Modify
- `hooks/scripts/session-start.sh:134–143` — the `product.enabled` block inside `validate_enabled_features()`; lines 134–143 are the exact change target (confirmed)
- `scripts/tests/test_hooks_integration.py:1649–1669` — `test_warns_product_without_goals` in `TestSessionStartValidation`; assert at line 1667: `"product.enabled is true but goals file not found" in result.stderr`

### Dependent Files (Callers/Importers)
- `hooks/scripts/session-start.sh:156` — `validate_enabled_features "$CONFIG_FILE"` call site; no other callers

### Similar Patterns (Warning Blocks to Remain Unchanged)
- `hooks/scripts/session-start.sh:112–121` — `sync.enabled` warning block; same `echo "[little-loops] Warning: ..." >&2` pattern, checks config keys not filesystem
- `hooks/scripts/session-start.sh:123–132` — `documents.enabled` warning block; same pattern

### Tests
- `scripts/tests/test_hooks_integration.py:1649` — `test_warns_product_without_goals` — **must be updated or removed** (currently asserts the warning string that will be removed)
- `scripts/tests/test_hooks_integration.py:1671` — `test_no_warnings_when_properly_configured` — asserts `"Warning:" not in result.stderr`; **stays green under both options** (Option A emits `Note:` not `Warning:`, Option B emits nothing); the goals file it creates at line 1682 becomes dead setup under Option B but causes no failure
- `scripts/tests/test_hooks_integration.py:1714` — `test_no_warnings_when_features_disabled` — asserts `"Warning:" not in result.stderr`; unaffected by either option

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — `### product` section, line 327: prose reads "For existing projects, set `product.enabled: true` in `.ll/ll-config.json` and create a goals file with your product vision..." — this implies the file must exist; update to note that goals are auto-discovered if `ll-goals.md` is absent (same language used in scan-product fallback) [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`Note:` format is novel in session-start.sh** — no existing `echo "[little-loops] Note: ..."` pattern is used in session-start.sh or other hook scripts. The only `Note:` occurrences are shell comments in `hooks/scripts/context-monitor.sh` (lines 46, 138). Option A introduces a new message severity level; Option B avoids this by simply removing the block.
- **Option B implication for `test_no_warnings_when_properly_configured`**: the goals-file creation at line 1682 (`(config_dir / "ll-goals.md").write_text(...)`) is there solely to suppress the product warning. Under Option B the creation becomes dead setup, but the test still passes cleanly since the negative assertion `"Warning:" not in result.stderr` is unaffected.
- **Option A implication for `test_warns_product_without_goals`**: the test currently asserts `"product.enabled is true but goals file not found" in result.stderr`. If the warning is replaced by a `Note:`, the test must be updated to assert the new `Note:` substring (or renamed to `test_notes_product_without_goals`). Option B: simply remove the test.
- **All three product tests use `result.stderr`** — the hook emits all `[little-loops]` messages with `>&2`, so stderr is the correct assertion target.

## Impact

- **Priority**: P2 — Eliminates false-alarm warnings for all users with `product.enabled: true` who rely on the goals discovery fallback (ENH-1444); repeated noise degrades trust in hook output
- **Effort**: Small — Pure deletion: ~10 shell lines + ~21 test lines; no new logic or infrastructure
- **Risk**: Low — Deletion only; surrounding warning blocks and all remaining product tests are unaffected; no callers outside the function itself
- **Breaking Change**: No

## Labels

`enhancement`, `hooks`, `testing`, `product`

## Status

**Open** | Created: 2026-05-11 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-05-11T20:00:19 - `49becedd-fa32-468d-92aa-cde351ac73f0.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `ff0145d5-b7f9-4caa-94df-36d9126dc2fd.jsonl`
- `/ll:decide-issue` - 2026-05-11T19:56:19 - `2cf9c552-8f63-44f7-971b-98d9da90104c.jsonl`
- `/ll:wire-issue` - 2026-05-11T19:50:32 - `d95423f9-658c-4e96-8246-610cc4efd463.jsonl`
- `/ll:refine-issue` - 2026-05-11T19:47:27 - `3f6570c7-cc28-4156-88a6-a61486c174bb.jsonl`
- `/ll:issue-size-review` - 2026-05-11T19:30:00 - `0abadba2-fa26-422a-8f2e-9ed2d2744c98.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `33a403c7-158c-474f-923d-29419c3cafc5.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The `docs/reference/CONFIGURATION.md` line 327 (`### product` prose) update is owned by ENH-1443. Do not re-apply that change here — ENH-1443 is the designated documentation issue for all goals-discovery prose softening. This issue covers only `hooks/scripts/session-start.sh` warning removal and `scripts/tests/test_hooks_integration.py`.

---
id: ENH-2748
title: Suppress flag for capture-reachability validator warning
type: ENH
priority: P3
status: done
captured_at: '2026-07-22T00:00:00Z'
completed_at: '2026-07-23T03:23:54Z'
discovered_date: '2026-07-22'
discovered_by: capture-issue
relates_to:
- ENH-1961
- BUG-1997
- ENH-2128
- BUG-2744
labels:
- fsm
- validation
- dx
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 23
score_test_coverage: 23
score_ambiguity: 25
score_change_surface: 22
---

# ENH-2748: Suppress flag for capture-reachability validator warning

## Summary

`_validate_capture_reachability()` (`scripts/little_loops/fsm/validation.py`,
ENH-1961) does pure state-graph dominance analysis on `${captured.*}`
references and has no way for a loop author to mark a flagged reference as
intentionally safe. When a loop closes a stale-capture gap with a *runtime*
guard the validator can't model (e.g. a marker file written/checked by shell
actions), the WARNING keeps firing on every `ll-loop run`/`ll-loop validate`
forever, even though the case is understood and already fixed.

This is unlike the MR-1 through MR-11 meta-loop rules (`fsm/validation.py`),
each of which supports a top-level per-rule suppress flag (`meta_self_eval_ok`,
`shared_state_ok`, `bash_default_ok`, etc.) so an author can silence a
specific, reviewed false positive without losing the check for everything
else. The capture-reachability check has no equivalent.

## Current Behavior

The only existing mitigation is `TestValidatorWarningBudget.ALLOWLIST` in
`scripts/tests/test_builtin_loops.py` (~line 11068) — a test-code map of
`(loop stem, category) -> allowed warning paths` that keeps CI from failing on
known false positives and ratchets bidirectionally (fails if a "fixed" entry
stops producing its warning). This works for CI but does nothing for the
interactive/automation path: every `ll-loop run` still prints the WARNING to
stderr.

Concretely, `autodev.yaml`'s `check_guard2_verdict` state references
`${captured.size_review_output.output}`. `check_broke_down`'s `on_no`
shortcut can statically reach it without `run_size_review` (the capturing
state) ever running. BUG-2744 closed the actual correctness gap by adding
`check_size_review_ran_this_pass`, a runtime marker-file gate
(`autodev-size-review-skipped-this-pass`) that reroutes that path away from
`check_guard2_verdict` before it ever reads a stale capture. The validator
can't see the marker file's runtime semantics, so it still flags the state as
statically reachable via the bypass path — correctly, from a pure graph
standpoint, but the case is already handled. The warning is allowlisted in
`TestValidatorWarningBudget.ALLOWLIST` (`("autodev", "capture-ordering")` ->
`"states.check_guard2_verdict.action"`) but still prints on every real run.

## Expected Behavior

A loop author who has reviewed a capture-reachability warning and confirmed
the bypass path is runtime-guarded can suppress it explicitly in the loop
YAML — mirroring the MR-* pattern (e.g. a top-level
`capture_reachability_ok: true`, or a narrower per-state/per-var suppress list
if blanket-loop suppression is judged too coarse). Suppressed warnings should
still be validated for staleness (analogous to
`test_allowlist_entries_are_not_stale`) so a suppress flag doesn't silently
outlive the condition that justified it.

## Motivation

Loop authors currently have no way to acknowledge-and-silence a reviewed
capture-reachability false positive at the source; the only lever is a
test-file allowlist that a runtime `ll-loop run` never consults. This is
recurring noise (`autodev`, `adopt-third-party-api`, `examples-miner`,
`goal-cluster`, `integrate-sdk` all currently carry allowlisted
`capture-ordering` warnings) that trains users to ignore validator output —
undermining the check's value for genuinely new bypass bugs.

## Proposed Solution

- Add a suppress mechanism to `_validate_capture_reachability()` analogous to
  the MR-* `top-level flag` convention already documented in
  `.claude/CLAUDE.md` § Loop Authoring (e.g. `capture_reachability_ok: true`
  at loop top level, or scoped to specific `state.path` entries if that's
  too coarse for multi-warning loops).
- When set, downgrade or drop the corresponding WARNING(s) at both
  `ll-loop validate` and `ll-loop run` time.
- Once implemented, migrate the existing `TestValidatorWarningBudget.ALLOWLIST`
  `capture-ordering` entries (Bucket A: sub-loop-injected captures, plus the
  `autodev`/`check_guard2_verdict` runtime-guard case) to the new in-YAML
  flag, and consider whether the test-level ratchet can be simplified once
  the suppress reason lives next to the state it protects.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `_validate_capture_reachability()` (`scripts/little_loops/fsm/validation.py:2765-2877`)
  currently has no suppress guard. Every one of the 12 existing MR-* suppress
  flags follows an identical shape: `if fsm.<flag>_ok: return []` as the
  first statement (e.g. `_validate_artifact_isolation()` at
  `fsm/validation.py:1586-1587`), a docstring line naming the flag, and a
  message-text mirror telling the user the exact flag name to set.
- No `category` field exists on `ValidationError` (fields are only
  `message`, `path`, `severity` — `fsm/validation.py:47-66`). The
  `"capture-ordering"` label is a test-file-only classifier
  (`CATEGORY_PATTERNS["capture-ordering"] = "References ${captured."`,
  `test_builtin_loops.py:11055`) matched by substring against
  `ValidationError.message`. A top-level suppress flag can reuse the
  existing early-return pattern with no schema-level "category" plumbing.
- No per-state/per-var suppress precedent exists anywhere in `validation.py`
  today — all 12 existing flags are blanket loop-wide booleans, even for
  rules like MR-12 (`_validate_pruning_profile()`) that internally iterate
  per-state. The only state-scoped suppress *artifact* in the codebase is
  the test-level `ALLOWLIST` dict (`(loop, category) -> {state.path, ...}`),
  which lives in test code, not the loop schema.

**Option A**: Top-level boolean flag `capture_reachability_ok: bool = False`
on `FSMLoop`, mirroring all 12 existing MR-* flags exactly (single
early-return guard in `_validate_capture_reachability()`, entry in
`KNOWN_TOP_LEVEL_KEYS`, `to_dict`/`from_dict` round-trip). Suppresses all
capture-reachability warnings for the whole loop.

> **Selected:** Option A — mechanical extension of the existing 13-deep
> MR-* suppress-flag convention with zero new infrastructure; Option B has
> no schema-level precedent and would require new matching logic.

**Option B**: Narrower per-state/per-var suppress list (e.g. a
`capture_reachability_ok: [state.path, ...]` list, or a nested
`capture_reachability_ok: {state_name: [var, ...]}` map) that suppresses
only the named reference(s), leaving the rule active for any other
unreviewed reference in the same loop. No existing precedent in
`validation.py`; would be the first of its kind in the schema.

**Recommended**: Option A — every one of the 5 currently-known
false-positive loops (`autodev`, `adopt-third-party-api`, `examples-miner`,
`goal-cluster`, `integrate-sdk`) has exactly one or a small handful of
allowlisted `capture-ordering` paths per loop, and research found zero
precedent for scoped suppression anywhere in the 12 existing MR-* rules —
consistency with the established convention outweighs the marginal
precision loss of blanket-loop suppression. Option B can be revisited later
as a follow-on if a loop author hits a case where one reviewed bypass and
one genuine new bug coexist in the same loop.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-22.

**Selected**: Option A — Top-level boolean flag `capture_reachability_ok`

**Reasoning**: All 13 existing MR-* suppress flags in `fsm/schema.py`/`fsm/validation.py`
are uniform blanket-loop booleans with an identical field/guard/docstring/`to_dict`/
`from_dict`/`KNOWN_TOP_LEVEL_KEYS` shape, and a ready-made 4-test template
(`TestArtifactIsolation`) exists to mirror. Option B's only analog
(`TestValidatorWarningBudget.ALLOWLIST`) lives entirely in test code and was never
promoted into the schema — it would require a new field shape, new state/var matching
logic (no `category` field exists on `ValidationError`), and no existing test template,
for marginal precision gain over the 5 currently-known false-positive loops.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| Option A (top-level boolean) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B (per-state/var scoped) | 1/3 | 1/3 | 2/3 | 2/3 | 6/12 |

**Key evidence**:
- Option A: 13 existing call sites in `fsm/validation.py` (lines 1360–2272) follow the exact
  `if fsm.<flag>_ok: return []` guard; `fsm/schema.py:1207-1223` has 13 contiguous plain
  `bool = False` fields to extend in place; `TestArtifactIsolation` (`test_fsm_validation.py:1509`)
  and `TestCaptureReachabilityValidation` (`test_fsm_validation.py:2689`) are ready templates.
- Option B: the only scoped-suppress shape in the repo (`(loop, category) -> {state.path}`)
  is test-file-only (`test_builtin_loops.py:11068`), never wired into `FSMLoop`,
  `to_dict()`/`from_dict()`, or `KNOWN_TOP_LEVEL_KEYS`; zero schema-level precedent for any
  per-state/per-var suppress field among all 13 existing flags.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — add the
  `if fsm.capture_reachability_ok: return []` early-return guard to
  `_validate_capture_reachability()` (function starts at line 2765; the
  `validate_fsm()` call site at line 1318 already wires it in, no change
  needed there); add `capture_reachability_ok` to `KNOWN_TOP_LEVEL_KEYS`
  (lines 200-251)
- `scripts/little_loops/fsm/schema.py` — add
  `capture_reachability_ok: bool = False` field to the `FSMLoop` dataclass
  (alongside the existing suppress flags, lines 1207-1223), emit in
  `to_dict()` (~1306-1333) and parse in `from_dict()` (~1419-1432)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/config_cmds.py:12` (`cmd_validate()`) —
  calls `load_and_validate()`, prints warnings via `print(f"  ⚠ {w}")`;
  benefits automatically once the flag suppresses the warning upstream
- `scripts/little_loops/cli/loop/run.py:92,116` (`cmd_run()`) — calls
  `load_and_validate()` (default `raise_on_error=True`); the
  `logger.warning()` stderr emission inside `load_and_validate()`
  (`fsm/validation.py:3053-3054`) stops firing once suppressed
- `scripts/little_loops/loops/autodev.yaml`, `adopt-third-party-api.yaml`,
  `examples-miner.yaml`, `goal-cluster.yaml`, `integrate-sdk.yaml` — the 5
  built-in loops currently carrying allowlisted `capture-ordering`
  warnings; migration targets for the new flag

### Similar Patterns
- `_validate_artifact_isolation()` (MR-3, `fsm/validation.py:1574-1604`) —
  cleanest example of the full end-to-end suppress-flag convention (guard,
  docstring, message-text mirror)
- `_validate_bash_default_interpolation()` (MR-7,
  `fsm/validation.py:1846-1878`) and `_validate_overescaped_shell()` (MR-9,
  `fsm/validation.py:1901-1902`) — same pattern

### Tests
- `scripts/tests/test_fsm_validation.py:2689` — `TestCaptureReachabilityValidation`
  class already exists with a `_fsm_with_capture_and_ref()` fixture helper
  to extend; `TestArtifactIsolation` (line 1509) is the cleanest 4-test
  template to mirror (fires-without-flag, suppressed-with-flag,
  wired-via-`validate_fsm()`, recognized-as-known-top-level-key)
- `scripts/tests/test_builtin_loops.py:11038` —
  `TestValidatorWarningBudget.ALLOWLIST`; the `("autodev", "capture-ordering")`
  entry (~line 11086) plus 4 others are the concrete migration targets once
  the YAML flag exists

### Documentation
- `.claude/CLAUDE.md` § Loop Authoring (MR-* table, lines ~147-162) — add a
  new row once implemented
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (lines 85-106) —
  source-of-truth rationale doc for the MR-* pattern

## Implementation Steps

1. Add `capture_reachability_ok: bool = False` field to the `FSMLoop`
   dataclass in `scripts/little_loops/fsm/schema.py` (alongside the existing
   suppress flags, ~line 1207-1223), with `to_dict()`/`from_dict()`
   round-trip support (~lines 1306-1333, 1419-1432).
2. Add `capture_reachability_ok` to `KNOWN_TOP_LEVEL_KEYS` in
   `scripts/little_loops/fsm/validation.py` (lines 200-251) to avoid a
   spurious "Unknown top-level key" warning.
3. Add the early-return guard `if fsm.capture_reachability_ok: return []` as
   the first statement in `_validate_capture_reachability()`
   (`fsm/validation.py:2765`), plus a docstring line and message-text mirror
   following the `_validate_artifact_isolation()` pattern
   (`fsm/validation.py:1574-1604`).
4. Add tests in `scripts/tests/test_fsm_validation.py`, extending
   `TestCaptureReachabilityValidation` (line 2689) with the 4-test shape
   from `TestArtifactIsolation` (line 1509): fires-without-flag,
   suppressed-with-flag, wired-through-`validate_fsm()`, and
   recognized-as-known-top-level-key via real YAML text.
5. Migrate the 5 existing `(<loop>, "capture-ordering")` entries in
   `TestValidatorWarningBudget.ALLOWLIST`
   (`scripts/tests/test_builtin_loops.py:11068`) to
   `capture_reachability_ok: true` in the corresponding loop YAML files
   (`autodev.yaml`, `adopt-third-party-api.yaml`, `examples-miner.yaml`,
   `goal-cluster.yaml`, `integrate-sdk.yaml`), removing the allowlist
   entries once each loop carries the flag.
6. Add a new row to the MR-* table in `.claude/CLAUDE.md` § Loop Authoring
   documenting the flag.
7. Verify:
   `python -m pytest scripts/tests/test_fsm_validation.py scripts/tests/test_builtin_loops.py -v`

## Resolution

Implemented Option A exactly as decided: added `capture_reachability_ok: bool = False`
to `FSMLoop` (`fsm/schema.py`), with `to_dict()`/`from_dict()` round-trip support and
a `KNOWN_TOP_LEVEL_KEYS` entry (`fsm/validation.py`). `_validate_capture_reachability()`
now starts with the standard `if fsm.capture_reachability_ok: return []` early-return
guard matching all 13 other MR-* suppress flags. Migrated all 5 currently-known
false-positive loops (`autodev`, `adopt-third-party-api`, `examples-miner`,
`goal-cluster`, `integrate-sdk`) to the new flag with an inline comment explaining
each bypass, and removed the now-empty `TestValidatorWarningBudget.ALLOWLIST`
`capture-ordering` entries. Added a `TestArtifactIsolation`-shaped 4-test block to
`TestCaptureReachabilityValidation` and a new row to the `.claude/CLAUDE.md` MR-*
table. Full suite (`python -m pytest scripts/tests/`, 15911 passed), `ruff check`,
and `mypy` all pass; `ll-loop validate` confirms all 5 migrated loops are clean.

## Impact

- **Priority**: P3 - Cosmetic/DX noise, not a correctness bug; all currently
  known cases are already tracked via the test allowlist.
- **Effort**: Small - one new validator suppress-flag check plus config
  plumbing, following the existing MR-* flag pattern closely.
- **Risk**: Low - purely additive; existing unsuppressed loops are unaffected.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:manage-issue` - 2026-07-23T03:23:10Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e2ecd55e-87e5-42e3-9828-de7e2501926c.jsonl`
- `/ll:ready-issue` - 2026-07-23T03:15:19 - `ea424d23-6c78-4a3d-b2c8-e31081d57e0f.jsonl`
- `/ll:confidence-check` - 2026-07-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6805341a-46cd-43ef-9500-3112dc89893f.jsonl`
- `/ll:decide-issue` - 2026-07-23T03:12:01 - `e08fb834-17a4-4f72-8cd3-1b37c7b8309f.jsonl`
- `/ll:refine-issue` - 2026-07-23T03:08:35 - `0f8f6584-bed0-4f9a-9672-c672ac6b0b86.jsonl`
- `/ll:capture-issue` - 2026-07-23T02:34:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2d2bccef-f831-463f-83a5-6b0e317afe52.jsonl`

---

**Open** | Created: 2026-07-22 | Priority: P3

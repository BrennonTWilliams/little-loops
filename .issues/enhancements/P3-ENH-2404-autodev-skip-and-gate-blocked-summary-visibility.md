---
id: ENH-2404
title: autodev/auto-refine summary loses skip reasons and drops gate-blocked issues
  entirely; make per-issue outcomes legible in summary.json
type: ENH
status: open
priority: P3
captured_at: '2026-06-30T00:00:00Z'
discovered_date: '2026-06-30'
discovered_by: audit-loop-run
labels:
- loops
- fsm
- verdict
- observability
relates_to:
- BUG-2403
- ENH-2385
- ENH-2402
- ENH-2397
confidence_score: 95
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-2404: legible per-issue outcomes in auto-refine summary.json

## Summary

`auto-refine-and-implement.finalize` collapses every parked issue into a single
`skipped` integer, and **omits gate-blocked issues entirely**. Two concrete
defects:

1. **Gate-blocked issues vanish from the summary.** `autodev` records
   learning-gate blocks to `autodev-gate-blocked.txt` (`autodev.yaml`
   `mark_gate_blocked`, init line 49) — distinct from skips by design (ENH-2319 /
   ENH-2402). But `finalize` only reads `autodev-skipped.txt` and
   `auto-refine-and-implement-errored.txt`. A gate-blocked issue is counted in
   neither `skipped` nor `errored` — it disappears from `summary.json` with no
   trace. (The cards audit didn't surface this because that run had zero
   gate-blocks.)

2. **Skip reasons are erased.** `autodev-skipped.txt` receives bare IDs from four
   semantically distinct states: `skip_inflight` (refinement failed),
   `enqueue_children` / `enqueue_or_skip` (decomposed — a *success*, not a
   failure), and `recheck_after_size_review` on_no (score below threshold). A
   reviewer reading `summary.json` cannot tell "5 decomposed into children" from
   "5 failed refinement" — they read identically as `skipped: 5`.

This is the layer above BUG-2403: once `closed` is correct, the remaining
question for any run is *why* the parked issues parked. Today that is unanswerable
without re-reading `events.jsonl`.

## Current Behavior

`auto-refine-and-implement`'s `finalize` state reads only two ledgers when
building `summary.json`: `autodev-skipped.txt` and
`auto-refine-and-implement-errored.txt` (see `docs/guides/LOOPS_REFERENCE.md`
§ Closure accounting). Two outcomes are misrepresented as a result:

1. Gate-blocked issues are invisible. `autodev` writes learning-gate blocks to
   `autodev-gate-blocked.txt` (`autodev.yaml` `mark_gate_blocked`, `init` line
   49) as a ledger distinct from skips (ENH-2319 / ENH-2402). `finalize` never
   reads this file, so a gate-blocked issue is counted in neither `skipped`
   nor `errored` — it disappears from `summary.json` with no trace.
2. Skip reasons are flattened to bare IDs. `autodev-skipped.txt` receives
   unlabeled IDs from four semantically distinct states (`skip_inflight`,
   `enqueue_children`, `enqueue_or_skip`, `recheck_after_size_review` on_no),
   so `summary.json`'s `skipped: N` cannot distinguish "N decomposed into
   children" (a success) from "N failed refinement" (a failure) without
   re-reading `events.jsonl`.

## Expected Behavior

- **Gate-blocked surfaced**: `finalize` reads `autodev-gate-blocked.txt` and emits
  a `gate_blocked` count in `summary.json`; gate-blocked issues are never silently
  dropped.
- **Skip reasons preserved**: replace the bare-ID `autodev-skipped.txt` with a
  two-space-delimited `ID  REASON` ledger (matching the established
  `rn-implement.yaml` `mark_deferred`/`re_enqueue_unblocked` convention),
  where reason ∈ `{decomposed, refine_failed, low_readiness, ...}`.
  `finalize` aggregates these into a `skipped_breakdown` object.
- **Layered summary.json** (subsumes audit P5):

  ```json
  {
    "verdict": "...",
    "closed": 0,
    "not_closed": 0,
    "skipped": 5,
    "skipped_breakdown": { "decomposed": 1, "refine_failed": 0, "low_readiness": 4 },
    "gate_blocked": 0,
    "errored": 0
  }
  ```

- **Skip-rate signal, not a hard gate** (reframes audit P6): emit a derived
  `parked_rate = (skipped + not_closed + gate_blocked) / input_size` field so a
  run sweeping the ready-flag is *visible*. Do NOT add a blocking `RAMPANT_SKIP`
  gate — with `skipped_breakdown` present, a high parked rate interprets itself
  (e.g. "4 low_readiness" is actionable; "4 decomposed" is healthy). A blanket
  floor would fire on legitimate decomposition-heavy runs.

## Motivation

This is the layer above BUG-2403: once `closed` correctly reflects real
completions, the next question any run report must answer is *why* the
parked issues parked. Today that question is unanswerable from
`summary.json` alone — a reviewer (or an automated triage step) has to grep
`events.jsonl` per issue to tell decomposition from failure, or to learn a
gate block happened at all. Surfacing `gate_blocked` and `skipped_breakdown`
turns the summary into a self-sufficient run report, instead of one that
`audit-loop-run` and human reviewers currently have to reconstruct by hand
from raw event logs.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — at each skip site write
  `ID  REASON` (two-space-delimited, matching `rn-implement.yaml`
  `mark_deferred`) rather than a bare ID (`skip_inflight`, `enqueue_children`,
  `enqueue_or_skip`, `recheck_after_size_review`).
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `finalize` reads
  the keyed skip ledger + `autodev-gate-blocked.txt`; emits `skipped_breakdown`,
  `gate_blocked`, `parked_rate`.
- `audit-loop-run` skill — recognize the new `summary.json` keys (additive; older
  runs without them must still parse).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — `read_outcome`
  state (lines 34-44) `cat`s `summary.json` verbatim into its own stdout and does
  not parse individual keys; confirmed the new `skipped_breakdown`/`gate_blocked`/
  `parked_rate` keys propagate automatically with **no code change required**
  here. Listed for completeness, not as an action item. [wiring agent finding]

### Tests
- `scripts/tests/test_builtin_loops.py` — gate-blocked count surfaces in
  `summary.json`; `skipped_breakdown` reflects mixed skip reasons; `parked_rate`
  computed; back-compat parse of a legacy summary without the new keys.

_Wiring pass added by `/ll:wire-issue`:_
- `TestAutoRefineAndImplementLoop._run_finalize` (`test_builtin_loops.py:1799-1831`)
  — its `skipped` fixture param currently writes bare `ID-{i}` lines with no
  REASON suffix, and the helper never writes `autodev-gate-blocked.txt` at all.
  Both need updating (REASON-suffixed lines + a new gate-blocked fixture param)
  or the new `skipped_breakdown`/`gate_blocked` parsing logic under test will see
  empty/zero values for every synthetic row regardless of whether the
  implementation is correct. [wiring agent finding]
- `TestValidatorWarningBudget.test_deterministic_warning_categories_do_not_regrow`
  / `test_allowlist_entries_are_not_stale` (`test_builtin_loops.py:7710-7811`) —
  ratchets WARNING-severity categories per `(loop_stem, category)`; neither
  `autodev` nor `auto-refine-and-implement` currently has an `ALLOWLIST` entry.
  If the new shell logic added to `finalize`/skip-sites trips a category (e.g.
  MR-3 shared-tmp, MR-5 artifact-versioning), add an allowlist entry referencing
  ENH-2404 rather than silently suppressing. [wiring agent finding]
- `test_builtin_loop_has_no_bare_variable_references`
  (`test_builtin_loop_interpolation.py`) — runs every loop action through the
  real `interpolate()` engine; any unescaped `${...}`-shaped text introduced in
  new REASON strings or finalize parsing code will crash this test (same class
  of bug as MR-7 in `.claude/CLAUDE.md`). [wiring agent finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` § `/ll:audit-loop-run` "Verdict values" table
  (~lines 845-852) — describes the same `summary.json`-based phantom/
  honest-failure disambiguation mechanism whose Step 6a prose is being updated
  in `skills/audit-loop-run/SKILL.md`. Doesn't enumerate the specific key set
  today, so not strictly forced by the additive keys, but worth a cross-check
  pass to avoid the two descriptions drifting. [wiring agent finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Skip-site write locations** (all currently write a bare ID via
`echo "$ID" >> autodev-skipped.txt`, no delimiter):
- `scripts/little_loops/loops/autodev.yaml:126` — `skip_inflight` (refinement failure)
- `scripts/little_loops/loops/autodev.yaml:432` — `enqueue_children` (decomposed — success)
- `scripts/little_loops/loops/autodev.yaml:582` — `enqueue_or_skip` (size-review decomposed — success)
- `scripts/little_loops/loops/autodev.yaml:614` — `recheck_after_size_review` on_no (low readiness — failure)
- `scripts/little_loops/loops/autodev.yaml:360` — `mark_gate_blocked` writes to
  `autodev-gate-blocked.txt` (separate ledger, initialized empty at `init:49`)
- `scripts/little_loops/loops/autodev.yaml:623-658` — `done` already reads and
  surfaces `autodev-gate-blocked.txt` in its own human-readable stdout summary;
  the data already exists, only `finalize`'s `summary.json` never reads it.

**`finalize` state** — `scripts/little_loops/loops/auto-refine-and-implement.yaml:129-191`:
- `count()` helper (line 139): `awk 'NF{c++} END{print c+0}'`, fails open to 0.
- `SKIP=$(count autodev-skipped.txt)` (line 163), `ERR=$(count $P-errored.txt)`
  (line 164) — `autodev-gate-blocked.txt` is never referenced (zero `grep`
  matches for `gate` in this state).
- Current `summary.json` schema emitted verbatim (lines 182-183):
  `{"verdict":"%s","closed":%s,"not_closed":%s,"skipped":%s,"errored":%s}` —
  exactly the 5 keys asserted by `test_finalize_summary_has_closure_keys`.
- A `subloop_outcome_auto-refine-and-implement.txt` sidecar (line 187,
  ENH-2005 pattern) is written alongside `summary.json` — unaffected by this
  issue.

**No `ID|reason` pipe-delimited ledger precedent exists in this codebase**
(`grep -rn "cut -d'|'" / "awk -F'|'"` across `scripts/little_loops` returns
nothing applicable). Two existing conventions were found instead, both in
`scripts/little_loops/loops/rn-implement.yaml`:
1. Two-space-delimited `ID  REASON` — `mark_deferred` write (~lines 905-939)
   / `re_enqueue_unblocked` read (~lines 558-590), parsed via
   `awk '{print $1}'` (ID) and `cut -d' ' -f2-` (reason). The format is
   documented as an inline comment at both the writer and reader.
2. Tag-suffixed line + `grep -c TAG` aggregation —
   `record_failure`/`record_sub_loop_crash`/`record_scores_missing`/
   `record_size_review_failed`/`record_learning_gate_blocked` (~lines
   846-901) all append to one shared `failures.txt` with an uppercase tag
   word; `report` (~lines 961-1016) aggregates via
   `grep -c "<TAG>" failures.txt`, derives a residual count by subtraction,
   and emits one `summary.json` key per tag via `printf`. This is the
   closest existing precedent for "one ledger, N semantically distinct
   reasons, each its own `summary.json` key" — directly analogous to the
   `skipped_breakdown` this issue proposes.

**Decision (2026-06-30): adopted convention 1.** This issue's design now uses
`ID  REASON` (two-space-delimited) instead of `ID|reason`, matching
`mark_deferred`/`re_enqueue_unblocked` exactly — see API/Interface below.
Rationale: it's already proven in this codebase for the same job (issue ID +
free-text reason in a shared ledger), parses with plain
`awk '{print $1}'` / `cut -d' ' -f2-`, and avoids introducing a new delimiter
style. Convention 2 (tag-suffixed + `grep -c`) fits fixed enum-like tags
better than this issue's free-form reason field, so it was not chosen.

**`audit-loop-run` skill** — `skills/audit-loop-run/SKILL.md` Step 6a
"Summary Cross-Check" (lines 257-269) is the only place that names specific
`summary.json` keys (`closed`, `implemented`, `failed`, `decomposed`); it
does not mention `skipped`, `errored`, `not_closed`, or `gate_blocked`
today. Step 6b "Verdict Table" (lines 270-296) already treats `summary.json`
absence and cross-loop key variance as expected/tolerable — this is
prose-only (no JSON-schema code path), verified by string-presence
assertions in `scripts/tests/test_audit_loop_run_skill.py` (e.g. line 132
`assert "summary.json" in step6_section`).

**Back-compat precedent already in place downstream**:
`sprint-refine-and-implement.yaml`'s `record_crash` state (lines 46-57)
already writes a divergent minimal `summary.json` shape
(`{"verdict":"crashed","reason":"..."}`, lacking
`closed`/`not_closed`/`skipped`/`errored` entirely), and `read_outcome`
(lines 34-44) just `cat`s the file verbatim without parsing specific keys —
confirming `summary.json` consumers in this codebase already tolerate
key-set variation, the same posture this issue's back-compat requirement
needs.

No `jq` usage exists in any loop YAML's JSON construction — `summary.json`
is always built via `printf '{"key":%s,...}\n'`; when aggregation logic
needs more than `wc -l`/`grep -c`, the established fallback is an inline
`python3 -c "..."` heredoc with `try/except Exception: print(0)` (see
`general-task.yaml:508-533`, `summarize_success`).

## Implementation Steps

1. In `autodev.yaml`, change each skip site (`skip_inflight`,
   `enqueue_children`, `enqueue_or_skip`, `recheck_after_size_review` on_no)
   to append `ID  REASON` (two-space-delimited, matching `rn-implement.yaml`
   `mark_deferred`) instead of a bare ID.
2. In `auto-refine-and-implement.yaml` `finalize`, parse the `ID  REASON`
   ledger (via `awk '{print $1}'` / `cut -d' ' -f2-`, same as
   `re_enqueue_unblocked`) into `skipped_breakdown` and read
   `autodev-gate-blocked.txt` into `gate_blocked`.
3. Compute and emit `parked_rate = (skipped + not_closed + gate_blocked) /
   input_size` alongside the existing `summary.json` fields.
4. Update the `audit-loop-run` skill to read the new keys, falling back
   gracefully when they're absent (legacy summaries).
5. Add/extend tests in `test_builtin_loops.py` for gate-blocked surfacing,
   skip-reason breakdown, parked-rate computation, and legacy back-compat
   parsing.
6. Run `ll-loop validate` on both loops and confirm `test_builtin_loops.py`
   is green.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

7. Update `_run_finalize`'s test fixture (`test_builtin_loops.py:1799-1831`)
   to write REASON-suffixed `autodev-skipped.txt` lines and add a new
   `autodev-gate-blocked.txt` fixture param — otherwise the new parsing logic
   under test sees empty/zero values regardless of correctness.
8. After implementing, run
   `TestValidatorWarningBudget.test_deterministic_warning_categories_do_not_regrow`
   / `test_allowlist_entries_are_not_stale` specifically; if the new shell
   logic trips a WARNING category, add an `ALLOWLIST` entry referencing
   ENH-2404 rather than silently suppressing it.
9. Cross-check `docs/reference/COMMANDS.md` § `/ll:audit-loop-run` "Verdict
   values" table against the `skills/audit-loop-run/SKILL.md` Step 6a edit
   (Step 4) so the two descriptions don't drift.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Existing test scaffolding to extend rather than reinvent (all in
`scripts/tests/test_builtin_loops.py`):
- `TestAutoRefineAndImplementLoop._run_finalize` (lines 1799-1831) —
  executes the real `finalize` shell action via
  `subprocess.run(["bash","-c", script], ...)` against a `tmp_path` run dir;
  its keyword-arg signature (`closed=`, `passed=`, `skipped=`, `errored=`)
  is the natural place to add `gate_blocked=` and a per-reason
  `skipped_breakdown=` for the new tests this issue requires.
- `test_finalize_summary_has_closure_keys` (lines 1890-1896) — template for
  a new test asserting `gate_blocked`, `skipped_breakdown`, `parked_rate`
  keys are present.
- `test_finalize_sources_autodev_ledgers` (lines 1793-1797) — currently
  asserts only `autodev-passed.txt`/`autodev-skipped.txt` appear in the
  action; template for a new `test_finalize_sources_gate_blocked_ledger`
  asserting `"autodev-gate-blocked.txt" in action`.
- `test_mark_gate_blocked_advances_queue_without_failing` (lines 2212-2223)
  — existing structural test for the `mark_gate_blocked` write; unaffected
  by this issue (no format change needed there).
- `test_skip_inflight_shell_action_writes_skipped_and_clears_inflight`
  (lines 2851-2874) — execution test that asserts `"ENH-0001" in skipped`;
  will need updating to `"ENH-0001  refine_failed" in skipped` (two-space
  delimiter) once the skip-site format changes.
- `skills/audit-loop-run/SKILL.md` Step 6a (lines 257-269) is the prose to
  edit for Implementation Step 4; `scripts/tests/test_audit_loop_run_skill.py`
  (string-presence assertions, e.g. line 132) is the test pattern to
  extend.

## Scope Boundaries

- **In scope**: `autodev.yaml` skip-site ledger format (`ID  REASON`,
  two-space-delimited), `auto-refine-and-implement.yaml` `finalize` reading
  the keyed ledger +
  `autodev-gate-blocked.txt`, new `summary.json` keys (`skipped_breakdown`,
  `gate_blocked`, `parked_rate`), `audit-loop-run` recognizing the new keys.
- **Out of scope**: a blocking `RAMPANT_SKIP` / parked-rate gate —
  `parked_rate` is a visibility signal only; a blanket floor would fire on
  legitimate decomposition-heavy runs (explicit non-goal, see Expected
  Behavior).
- **Out of scope**: fixing the `closed` ground-truth count itself — that is
  BUG-2403, a prerequisite this issue depends on but does not re-implement.
- **Out of scope**: backfilling `skipped_breakdown` / `gate_blocked` into
  archived `summary.json` files from past runs.

## API/Interface

New `summary.json` keys (additive — existing keys unchanged):

```json
{
  "skipped_breakdown": { "decomposed": 0, "refine_failed": 0, "low_readiness": 0 },
  "gate_blocked": 0,
  "parked_rate": 0.0
}
```

New `autodev-skipped.txt` line format: `ID  REASON` (two-space-delimited,
was bare `ID`), matching the existing `rn-implement.yaml`
`mark_deferred`/`re_enqueue_unblocked` convention — parse with
`awk '{print $1}'` (ID) and `cut -d' ' -f2-` (reason). `reason` ∈
`{decomposed, refine_failed, low_readiness, ...}`. `audit-loop-run` must
parse both the new `ID  REASON` format and legacy bare-ID lines for
back-compat.

## Acceptance Criteria

- [ ] A run with a learning-gate block reports `gate_blocked >= 1` in
      `summary.json` (no silent drop).
- [ ] `skipped_breakdown` distinguishes `decomposed` from refinement/score
      failures.
- [ ] `parked_rate` is emitted; no blocking skip-rate gate is added.
- [ ] `audit-loop-run` reads the new keys without breaking on legacy summaries.
- [ ] `ll-loop validate` passes for both loops; `test_builtin_loops.py` green.

## Impact

- **Priority**: P3 — observability/correctness of the run report; depends on
  BUG-2403 landing first (fix `closed`, then explain the remainder).
- **Effort**: Medium — touches both loop YAMLs + the audit skill + tests.
- **Risk**: Low — additive `summary.json` keys; existing keys unchanged.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/guides/LOOPS_REFERENCE.md` § Closure accounting | Documents the current `summary.json` / `autodev-skipped.txt` / `autodev-passed.txt` schema this issue extends |
| BUG-2403 | Prerequisite — fixes the `closed` ground-truth count this issue's `parked_rate` denominator depends on |
| ENH-2402 | Established `autodev-gate-blocked.txt` as a ledger distinct from skips |
| ENH-2397 | Regression test for the `subloop_outcome_auto-refine-and-implement.txt` sidecar contract — same artifact family `finalize` writes alongside `summary.json`; wiring agent finding |

## Session Log
- `/ll:confidence-check` - 2026-06-30T21:30:00Z - `9c51cc81-2d8a-46ee-95b4-5c41273e7bfb.jsonl`
- `/ll:wire-issue` - 2026-06-30T21:04:31 - `ec0f9327-2f06-44a8-abd0-51d0ad3feb50.jsonl`
- `/ll:refine-issue (ledger-format decision)` - 2026-06-30T20:54:12 - `46dd6a40-bb04-4d8a-9558-e932826588aa.jsonl`
- `/ll:refine-issue` - 2026-06-30T20:48:53 - `46dd6a40-bb04-4d8a-9558-e932826588aa.jsonl`
- `/ll:format-issue` - 2026-06-30T20:39:22 - `4bf4d1ed-eaa9-464a-9d2e-9abf985fe2f8.jsonl`
- `audit-loop-run` - 2026-06-30 - derived from
  `audit-loop-sprint-refine-and-implement-2026-06-30.md` (cards repo) proposals
  P4/P5/P6, re-scoped against the actual autodev skip/gate-blocked ledgers.

---

## Status

**Open** | Created: 2026-06-30 | Priority: P3

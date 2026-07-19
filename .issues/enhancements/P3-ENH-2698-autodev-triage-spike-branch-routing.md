---
id: ENH-2698
title: autodev triage_outcome_failure spike branch routing
type: ENH
priority: P3
status: done
labels:
- fsm
- loops
- autodev
- confidence
- risk-reduction
parent: EPIC-2570
relates_to:
- ENH-2568
completed_at: '2026-07-15T18:06:29Z'
confidence_score: 98
outcome_confidence: 82
score_complexity: 20
score_test_coverage: 23
score_ambiguity: 18
score_change_surface: 21
---

# ENH-2698: autodev triage_outcome_failure spike branch routing

## Summary

Add a spike remediation branch to `autodev.yaml`'s `triage_outcome_failure` state
so an outcome-confidence failure caused by an unproven internal mechanism
(`spike_needed: true`, set by `/ll:confidence-check` Phase 4.10) routes through
`/ll:spike --auto` and a confidence re-check, instead of falling into
decompose/size-review where it doesn't fit.

## Parent Issue

Decomposed from ENH-2568: autodev spike triage routing + spike-gate wrapper loop.
This child covers **Part 1** of the parent's Proposed Solution (autodev.yaml
triage routing) plus the wiring-phase test/doc items that attach to it.

## Current Behavior

`triage_outcome_failure` (`scripts/little_loops/loops/autodev.yaml:665-679` —
re-verify anchors at implementation time, see parent issue's corrected
line-number map) maps an outcome-confidence failure to exactly three remedies:
`decision_needed`/low ambiguity → `run_decide`; `missing_artifacts` → `run_wire`
→ `run_refine` → `rerun_confidence_after_wire`; otherwise → decompose via
`run_size_review`. An issue whose low outcome confidence stems from a
zero-precedent mechanism with no test coverage of the risky core (ENH-2565)
fits none of these and thrashes into `autodev-skipped.txt`.

## Expected Behavior

`triage_outcome_failure.on_no` routes a `spike_needed: true` issue to
`run_spike` (`/ll:spike <ID> --auto`), then `rerun_confidence_after_spike`
re-scores and routes to `enqueue_or_skip`. A completed-or-attempted spike never
runs twice (`spike_attempted` guard).

## Proposed Solution

- `triage_outcome_failure` on_no path: insert `check_spike_needed` between
  `run_decide` routing and `check_missing_artifacts`. Ordering: an unresolved
  design decision must be settled before spiking an approach (decide first);
  spike check sits after decide, before missing_artifacts.
- `check_spike_needed`: single inline-python `shell_exit` state reading both
  `spike_needed` and `spike_attempted` from `ll-issues show --json` (predicate
  is `spike_needed AND NOT spike_attempted`, a two-field condition
  `ll-issues check-flag` can't express in one call) — mirrors
  `triage_outcome_failure`'s own inline-python idiom
  (autodev.yaml:671-675). On match → `run_spike`; else fall through to
  `check_missing_artifacts` (preserve the existing chain — retarget
  `triage_outcome_failure.on_no` from `check_missing_artifacts` to
  `check_spike_needed`).
- `run_spike`: `fragment: with_rate_limit_handling`,
  `action: "/ll:spike ${captured.input.output} --auto"`,
  `action_type: slash_command`, `next: rerun_confidence_after_spike`,
  `on_error: rerun_confidence_after_spike`, `on_rate_limit_exhausted: done`.
  Consider a dedicated `timeout` given the rn-refine 4h-cap history
  (ENH-2565).
- `rerun_confidence_after_spike`: re-run `/ll:confidence-check`, copy of
  `rerun_confidence_after_wire` (a spike is a repair action like wiring, not a
  decision resolution — do not mirror `rerun_confidence_after_decide`, which
  has a dedicated `recheck_after_decide` state), `next: enqueue_or_skip`.
- Optional `commands.spike_gate.enabled` kill-switch in
  `scripts/little_loops/config-schema.json` under `commands`
  (`"additionalProperties": false` gate — must be declared as a sibling
  property following the `commands.confidence_gate` nested-object template,
  ~lines 465-490, if implemented).

## API/Interface

- Consumes frontmatter flag `spike_needed` (ENH-2569, already landed) and
  writes/reads `spike_attempted`.
- New autodev states: `check_spike_needed`, `run_spike`,
  `rerun_confidence_after_spike`.

## Files to Modify

_Wiring pass added by `/ll:wire-issue`:_
- **`scripts/little_loops/cli/issues/show.py`** — **BLOCKING dependency.**
  `_parse_card_fields()` builds its `--json` payload from a **hardcoded
  allowlist** (`score_ambiguity` line 180, `decision_needed_raw` line 186,
  `missing_artifacts_raw` line 187; emitted in the `return {...}` dict at
  lines 343/359/362-364), **not** a passthrough of arbitrary frontmatter. There
  is currently **no** `spike_needed`/`spike_attempted` extraction or dict key.
  The proposed `check_spike_needed` design ("reading both `spike_needed` and
  `spike_attempted` from `ll-issues show --json`", Proposed Solution) will read
  `None` for both fields regardless of frontmatter state unless `show.py` is
  changed. **Add two `frontmatter.get(...)` extractions and two dict keys**
  (mirror the `decision_needed`/`missing_artifacts` boolean-string pattern) so
  `show --json` surfaces the flags. Alternative (avoids touching `show.py`):
  have `check_spike_needed`'s inline-python open + YAML-parse the frontmatter
  directly rather than shelling `show --json` — decide at implementation time,
  but the CLI gap is real either way. [Agent 2 finding, confirmed]

- `scripts/little_loops/loops/autodev.yaml` — `triage_outcome_failure` routing
  + 3 new states.
- `scripts/tests/test_builtin_loops.py:3882-3889` — retarget
  `test_triage_outcome_failure_on_no_routes_to_check_missing_artifacts` to
  assert `on_no == "check_spike_needed"`; add a test that
  `check_spike_needed`'s fall-through still reaches `check_missing_artifacts`.
  Clone the `run_wire`/`rerun_confidence_after_wire` structural/routing test
  clusters (~4207-4259) for `run_spike`/`rerun_confidence_after_spike`. Add the
  3 new state names to `test_required_states_exist`'s `required` set
  (~3247-3280).
- `scripts/tests/test_autodev_decision_gate.py` —
  `TestAutodevValidatesAfterFix.test_autodev_yaml_loads_and_validates`
  (~line 271) must still pass zero-`ValidationSeverity.ERROR` after the 3 new
  states are added (MR-1..MR-11 lint, especially MR-7 `${ns.path:default=...}`
  escaping in the inline-python `check_spike_needed` shell body). Add a sibling
  `TestXStructural`/`TestXRouting` class pair for the spike triad, following
  the `check_decision_at_dequeue`/`check_decision_before_size_review`
  precedent.
- `docs/reference/ISSUE_TEMPLATE.md` — the frontmatter-flag reference table has
  a `spike_needed` row (~line 889) but no rows for `spike_attempted`/
  `spike_completed`, the flags these new states read/write; add both per the
  one-row-per-flag convention.
- `scripts/tests/test_wiring_reference_docs.py:25` — add a symmetrical
  `("docs/reference/ISSUE_TEMPLATE.md", "spike_attempted", "ENH-2568")`
  `DOC_STRINGS_PRESENT` presence row.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- **`docs/guides/LOOPS_REFERENCE.md`** — narrates the exact triage shape this
  issue changes and will go stale. Three touchpoints: (1) the autodev
  FSM-flow **ASCII diagram** — line 979 (`triage_outcome_failure → [score_ambiguity ≤ 10?]`)
  and line 982 (`check_missing_artifacts → [missing_artifacts=true?]`) — insert
  the new `check_spike_needed → [spike_needed AND NOT spike_attempted?] →
  run_spike → rerun_confidence_after_spike → enqueue_or_skip` branch between
  them; (2) the **"Outcome failure triage" prose** at line 1009 calls this a
  **"three-branch triage"** and describes the `check_missing_artifacts`
  fall-through — update to reflect the new fourth branch and the retargeted
  `on_no` edge; (3) the narrative sentence at **line 144** describing the
  `triage_outcome_failure → check_missing_artifacts → run_wire` path. The
  second diagram (~line 1106, `scan-and-implement`'s `check_decision_needed →
  check_missing_artifacts` lattice) is a **separate loop — unaffected**.
  [Agent 2 finding, confirmed]
- `CHANGELOG.md` — add an entry for the 3 new autodev states on delivery
  (process convention, mirrors ENH-1291/ENH-2569 entries). [Agent 1 finding]

## Tests

- `test_builtin_loops.py`: triage routes `spike_needed`→`run_spike`,
  `spike_attempted` suppression, rerun-confidence wiring, retargeted `on_no`
  edge + fall-through chain preserved.
- Regression: existing triage paths (decide/wire/size-review) unchanged.
- `test_autodev_decision_gate.py`: whole-file `load_and_validate` remains
  zero-ERROR; new structural/routing class pair for the spike triad.
- `test_wiring_reference_docs.py`: new `DOC_STRINGS_PRESENT` row passes.
- Full regression: `python -m pytest scripts/tests/test_builtin_loops.py
  scripts/tests/test_autodev_decision_gate.py scripts/tests/test_wiring_reference_docs.py -v`.

_Wiring pass added by `/ll:wire-issue`:_
- **New coverage for the `show --json` spike-flag emission** (if the `show.py`
  path is taken): no existing test exercises `ll-issues show --json` output
  parsing for `spike_needed`/`spike_attempted` — `test_show.py` covers only
  card-rendering, and `test_issues_cli.py`'s `--json` coverage is `list`/
  `sequence`/`impact-effort` only (not `show`). Add a `test_show.py`/
  `test_issues_cli.py` case asserting `show --json` on a fixture issue with
  `spike_needed: true` / `spike_attempted: true` set surfaces both keys. This
  is a **new, unproven dependency** — the FSM routing tests already planned do
  **not** cover the inline-python JSON-parse of these fields. Include the
  `spike_attempted`-suppression case (both flags true → `check_spike_needed`
  falls through, not `run_spike`). [Agent 3 finding, confirmed]
- **Anchor correction (test_autodev_decision_gate.py):** the decide-path
  structural/routing precedent to clone is `TestCheckDecisionBeforeSizeReviewStructural`
  at lines **290-370** (sibling to `TestCheckDecisionAtDequeueStructural`
  ~101-184), **not** lines 3829-3863 as the Codebase Research Findings state —
  that file is ~620 lines total. Use the 290-370 anchor at implementation time.
  [Agent 3 finding, confirmed]
- `test_spike_skill.py` already asserts the producer side (`spike_completed:
  true` at ~line 97, `spike_attempted: true` at ~line 101 in `/ll:spike`
  SKILL.md) — no change needed, but it is the authoritative flag contract
  `check_spike_needed`'s predicate must match. [Agent 3 finding]

## Codebase Research Findings

_Added by `/ll:refine-issue` — anchor re-verification against current worktree (all
cited anchors resolved; no drift found):_

### autodev.yaml anchors — confirmed, zero drift

- `triage_outcome_failure` — lines **665-679** exactly as cited. Inline-python body
  spans 672-675 (`action: |` opener at 671). `on_yes: run_decide`,
  `on_no: check_missing_artifacts` (678), `on_error: detect_children`.
- `check_missing_artifacts` — lines **681-689**. `on_yes: run_wire`,
  `on_no: detect_children`. **Correction to Current Behavior prose**: the
  size-review path is `check_missing_artifacts.on_no → detect_children` (the
  size-review lattice), *not* a direct `run_size_review` edge. `triage_outcome_failure`
  is the only state referencing `check_missing_artifacts`, so retargeting its `on_no`
  to `check_spike_needed` is a clean single-edge move.
- Clone template `run_wire` — lines **406-415**: `fragment: with_rate_limit_handling`,
  `action: "/ll:wire-issue ${captured.input.output} --auto"`,
  `action_type: slash_command`, `next: run_refine`, `on_error: run_refine`,
  `on_rate_limit_exhausted: done`. Note `run_wire.next` targets **`run_refine`**
  (lines 417-430, interposed), which then routes to `rerun_confidence_after_wire`
  (lines **432-442**). `run_spike` should route directly to
  `rerun_confidence_after_spike` (no refine interposition — a spike proves a
  mechanism, it does not edit integration points).
- Clone template `rerun_confidence_after_wire` — lines **432-442**:
  `action: "/ll:confidence-check ${captured.input.output}"`, `next: enqueue_or_skip`,
  `on_error: enqueue_or_skip`, `on_rate_limit_exhausted: done`. This is the correct
  model for `rerun_confidence_after_spike` (repair-action rerun, no dedicated
  recheck state — unlike the decide path).
- Decide-path contrast (confirms "do not mirror `rerun_confidence_after_decide`"):
  `rerun_confidence_after_decide` (325-338) → `recheck_after_decide` (340-356) →
  `assert_decision_cleared` (358-370). The decide path has a dedicated readiness
  recheck + decision-flag re-verification gate; the wire path does not. Follow the
  wire path.
- `with_rate_limit_handling` fragment is defined in
  `scripts/little_loops/loops/lib/common.yaml:61-74` (not in autodev.yaml). It
  requires the composing state to supply `on_rate_limit_exhausted:`. Defaults:
  `max_rate_limit_retries: 3`, `rate_limit_max_wait_seconds: 21600` (~6h wall-clock
  budget) — the "consider a dedicated timeout" note is satisfiable by overriding
  `rate_limit_max_wait_seconds` at the `run_spike` state level.

### Test/doc anchors — confirmed

- `test_builtin_loops.py`:
  `test_triage_outcome_failure_on_no_routes_to_check_missing_artifacts` at **3882-3889**
  (retarget assertion to `check_spike_needed`). Wire test cluster spans
  **4193-4260** (`test_rerun_confidence_after_wire_*`, ~11 methods to clone).
  `test_required_states_exist` `required` set at **3250-3277** (already lists
  `run_wire`, `run_refine`, `rerun_confidence_after_wire` — add the 3 spike states).
- `test_autodev_decision_gate.py`:
  `TestAutodevValidatesAfterFix.test_autodev_yaml_loads_and_validates` at **271**.
  Precedent class pair to follow: the `check_decision_before_size_review`
  structural/routing methods at **3829-3863**.
- `ISSUE_TEMPLATE.md`: `spike_needed` row at **889**; its description already
  *mentions* `spike_attempted`/`spike_completed` ("never re-flagged once
  `spike_attempted`/`spike_completed` is set") but **no separate rows exist** for
  them — confirms the doc gap.
- `test_wiring_reference_docs.py`: `DOC_STRINGS_PRESENT` declared at **20**; the
  existing `spike_needed` entry is at **line 25** and is tagged **`ENH-2569`** (not
  ENH-2568). **Provenance note**: the issue proposes tagging the new
  `spike_attempted` row `ENH-2568`, but since this child (ENH-2640) is the state
  that reads/writes `spike_attempted`, tagging the new row **`ENH-2640`** is more
  accurate provenance. Confirm the desired convention at implementation time.

## Scope Boundaries

- No rn-* loop edits (documented as future work in the parent).
- No changes to `/ll:explore-api`, Learning-Test Registry, or
  `proof-first-task.yaml`.
- `spike-gate.yaml` (the standalone wrapper loop) is out of scope — see
  ENH-2641.

## Impact

- **Priority**: P3
- **Effort**: Medium — 3 FSM states, routing edge retarget, tests + docs.
- **Risk**: Medium — touches autodev's triage lattice; mitigated by copying
  the wire/decide routing shape verbatim and the `spike_attempted` one-shot
  guard.
- **Breaking Change**: No — additive states; existing paths unchanged.

## Related Issues

- **ENH-2568** — parent issue this was decomposed from.
- **ENH-2641** — sibling child covering the `spike-gate.yaml` wrapper loop.
- **FEAT-2567** — `/ll:spike` skill (done, provides `--auto`/`--check`
  contracts).
- **ENH-2569** — `spike_needed` flag detection (done).
- **ENH-2565** — motivating instance.
- **BUG-1491** — rerun-confidence-after-remediation precedent.

## Resolution

Implemented the spike-remediation branch in `autodev.yaml`:

- **`triage_outcome_failure.on_no`** retargeted from `check_missing_artifacts` to
  the new `check_spike_needed` gate (decide-first ordering preserved).
- **`check_spike_needed`** — inline-python `shell_exit` state reading `spike_needed`
  and `spike_attempted` from `ll-issues show --json`; predicate is `spike_needed AND
  NOT spike_attempted` (one-shot guard). On match → `run_spike`; else falls through
  to `check_missing_artifacts`, preserving the wire/size-review chain.
- **`run_spike`** — `/ll:spike --auto` (`with_rate_limit_handling`,
  `rate_limit_max_wait_seconds: 14400`) → `rerun_confidence_after_spike`.
- **`rerun_confidence_after_spike`** — copy of `rerun_confidence_after_wire`
  (`/ll:confidence-check` → `enqueue_or_skip`).
- **`show.py`** (blocking dep) — `_parse_card_fields` now extracts and emits
  `spike_needed`/`spike_attempted`/`spike_completed` as lowercased boolean strings.
- Tests: `test_builtin_loops.py` (retargeted `on_no` + 6 new spike-triad methods,
  3 new required states), `test_autodev_decision_gate.py` (`TestSpikeTriageStructural`),
  `test_wiring_reference_docs.py` (new `spike_attempted` row), `test_show.py`
  (2 spike-flag emission cases).
- Docs: `ISSUE_TEMPLATE.md` (`spike_attempted`/`spike_completed` rows),
  `LOOPS_REFERENCE.md` (ASCII diagram + four-branch triage prose + line-144
  narrative), `CHANGELOG.md` (1.145.0 Added entry).

Optional `commands.spike_gate.enabled` kill-switch not implemented (marked optional).
Full suite green under hermetic `PYTHONPATH=scripts` (14981 passed); the two
default-runner false negatives are the documented editable-install-pins-main-tree
and PYTHONPATH-self-contamination environmental artifacts, not real failures.

## Status

**Done** | Created: 2026-07-15 | Completed: 2026-07-15 | Priority: P3

## Session Log
- `/ll:issue-size-review` - 2026-07-15T12:06:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-20260715-120653-subloop-epic-epic-2570-spike-workflow-skill-confidence-flag-autodev-routing/0840f459-5e13-45ee-bcca-0c5d1a7e8a86.jsonl`
- `/ll:refine-issue` - 2026-07-15T12:51:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-20260715-120653-subloop-epic-epic-2570-spike-workflow-skill-confidence-flag-autodev-routing/a670c73c-78ce-4263-b75d-bb80f9666e44.jsonl`
- `/ll:wire-issue` - 2026-07-15T13:00:00 - session JSONL unresolved
- `/ll:confidence-check` - 2026-07-15T13:10:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-20260715-120653-subloop-epic-epic-2570-spike-workflow-skill-confidence-flag-autodev-routing/3cba9787-2a0f-4f53-ab2b-e0bee93e52b3.jsonl`
- `/ll:manage-issue` - 2026-07-15T18:05:55Z - implementation session

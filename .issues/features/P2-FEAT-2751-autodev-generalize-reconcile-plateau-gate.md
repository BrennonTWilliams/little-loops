---
id: FEAT-2751
title: 'autodev: generalize reconcile plateau gate beyond the spike path (stagnation
  backstop)'
type: FEAT
priority: P2
status: done
captured_at: '2026-07-23T21:42:00Z'
completed_at: '2026-07-23T23:17:39Z'
discovered_date: '2026-07-23'
discovered_by: capture-issue
decision_needed: false
size: Medium
confidence_score: 98
outcome_confidence: 68
score_complexity: 15
score_test_coverage: 20
score_ambiguity: 13
score_change_surface: 20
---

# FEAT-2751: autodev: generalize reconcile plateau gate beyond the spike path (stagnation backstop)

## Summary

Finding from the `2026-07-23T16:08 autodev FEAT-021` run on `sketch-storyboards`
(run_dir `.loops/runs/autodev-20260723T160811/`, 28m 3s, 25 iterations, single-issue
input). (The companion guard-2 regex finding from the same run was split out to
BUG-2752 — a standalone, low-risk fix that doesn't need to wait on this design.)

Root cause of the 28-minute grind: autodev already has the correct remedy for a
pinned readiness score — `check_reconcile_needed` (ENH-2689) routes plateaued
issues to `/ll:reconcile-issue`, the in-place rewrite of stale directive
sections that `/ll:refine-issue` (append-only) can never fix. But its plateau
predicate compares current confidence against
`autodev-pre-spike-readiness.txt`, and that snapshot is written **only on the
spike-armed branches** (`check_spike_needed` ~line 870 and
`check_spike_needed_before_skip` ~line 1044, both on `on_yes`). For any issue
without `spike_needed: true` — the common case, including FEAT-021 — the
snapshot never exists, `pre == ''`, the plateau test is structurally false, and
the reconcile pass is bypassed. FEAT-021 (confidence 85 / outcome 86,
`Very Large`) was ground through `/ll:refine-issue` (140,990 in),
`/ll:wire-issue` (82,770 in), `/ll:confidence-check` (305,478 in), and
`/ll:issue-size-review` (73,983 in) with readiness pinned at 85, then deferred
`low_readiness` — without the one state designed for exactly this condition
ever firing.

**Primary fix**: snapshot pre-refine confidence per-issue at `dequeue_next`
(`autodev-pre-readiness.txt`) and gate `check_reconcile_needed` on it, so any
issue whose confidence is unchanged after the repair chain gets its one
reconcile pass before deferral — spike or no spike.

**Secondary (backstop)**: when reconcile has already fired and the score is
still pinned on a subsequent deferral-eligible check, defer with a distinct
`readiness_stagnated` reason instead of `low_readiness`, honouring the user's
`prefer-abort-over-long-runs` preference with an informative triage code.

## Status

Open — rescoped 2026-07-23 (see Session Log); not started.

## Impact

Every non-spike issue that plateaus in autodev currently burns a full repair
chain (~600k input tokens, ~28 min in the FEAT-021 run) and defers
`low_readiness` without ever receiving the designed reconcile remedy. The fix
converts those runs into either a successful implement (score moves after the
rewrite) or a fast, honestly-labelled `readiness_stagnated` deferral.

## Motivation

`autodev` is the project's primary "refine + implement a specific set of
issues" orchestrator and is exercised frequently. The refine → wire →
confidence-check chain appends findings but never rewrites directive sections;
`/ll:reconcile-issue` exists precisely to break that plateau, and ENH-2689
wired it in — but only for the spike sub-case. Generalizing the gate fixes the
grinding behaviour at its root: stuck issues get the designed rewrite remedy
instead of cycling score checks for 28 minutes and deferring with a reason
(`low_readiness`) that hides the fact that no rewrite was ever attempted. The
stagnation backstop then distinguishes "reconcile tried and failed" from
"never got the remedy" in `ll-issues deferred-triage`.

## Current Behavior

Run trace (`.loops/runs/autodev-20260723T160811/`):

- `autodev-input.txt` = `FEAT-021` (9 bytes, single issue)
- `refine_current` (iter 4) ran `/ll:refine-issue` → `/ll:wire-issue` →
  `/ll:confidence-check`. Confidence stayed at 85 (was 85 before refinement).
- `check_passed` (85 < readiness_threshold 90) → `triage_outcome_failure` →
  `check_spike_needed` (no — so no pre-spike snapshot written) →
  `check_missing_artifacts` (no) → `detect_children` → `size_review_snap` →
  `check_broke_down` → `check_parent_resolved` → `recheck_scores` (still 85) →
  `check_decision_before_size_review` → `run_size_review` (iter 17)
- `/ll:issue-size-review --auto` ran but produced no children.
  `check_guard2_verdict` fell through (see BUG-2752 — orthogonal).
- `check_reconcile_needed` was on the chain but its predicate read a
  nonexistent `autodev-pre-spike-readiness.txt` → plateau false →
  `reconcile_current` never ran.
- `recheck_after_size_review` found 85 < 90, wrote
  `FEAT-021  low_readiness` to `autodev-skipped.txt`, called
  `ll-issues set-status deferred --by automation --reason low_readiness`,
  and exited.
- `dequeue_next` saw empty queue → `done`. Total: 28m 3s, 25 iterations.

## Expected Behavior

1. `dequeue_next` snapshots the issue's current `confidence` to
   `autodev-pre-readiness.txt` when the issue is dequeued (mirroring the
   `autodev-pre-spike-readiness.txt` write shape from ENH-2689) and clears the
   per-issue repair-cycle counter.
2. `check_reconcile_needed`'s plateau predicate reads
   `autodev-pre-readiness.txt` (preferring the spike snapshot when present,
   since it is the fresher pre-repair baseline): plateau =
   `pre != '' AND pre == current AND NOT reconcile_attempted`. A plateaued
   FEAT-021-profile issue now routes to `reconcile_current` →
   `/ll:reconcile-issue` → `rerun_confidence_after_reconcile` before any
   deferral. The `reconcile_attempted` one-shot guard is unchanged.
3. Backstop: `recheck_after_size_review` (and
   `regate_after_atomic_remediation`) write `readiness_stagnated` instead of
   `low_readiness` when the issue has been through ≥ 2 repair cycles this run
   (`autodev-repair-cycle-count.txt`, incremented by each repair-class state's
   success branch) AND `current_confidence <= pre_readiness`. Below that
   threshold the existing `low_readiness` write is untouched.

## Use Case

Run `ll-loop run autodev FEAT-XXX` against a Very Large, already-refined issue
whose confidence score is stuck at 85 (the canonical FEAT-021 profile, no
`spike_needed`). Expected:

- The loop runs `/ll:refine-issue` → `/ll:wire-issue` → `/ll:confidence-check`
  once. If confidence crosses 90 → `implement_current` (unchanged).
- If confidence stays at 85: `check_reconcile_needed` now detects the plateau
  from the dequeue-time snapshot and runs `/ll:reconcile-issue`, then one more
  `/ll:confidence-check`.
- If the reconciled score crosses 90 → implement (the root-cause win).
- If it stays pinned: the next deferral-eligible check fires the stagnation
  backstop and defers with `readiness_stagnated` — a triage reason that now
  truthfully means "all remedies including reconcile were attempted."

## Proposed Solution

### Codebase Research Findings (`/ll:refine-issue` pass, 2026-07-23)

- **Line numbers have drifted ~19 lines** since this issue was authored (verified
  directly against `scripts/little_loops/loops/autodev.yaml`, 2026-07-23):
  `dequeue_next` (78–116), `check_reconcile_needed` (1053–1084), and the
  `check_spike_needed*` snapshot writers are still exact, but
  `regate_after_atomic_remediation` is actually at **1202–1243** (issue says
  1183–1224) and `recheck_after_size_review` is actually at **1272–1323** (issue
  says 1253–1305). `reconcile_current` is at 1245–1257. Re-grep line anchors
  before editing rather than trusting the numbers above.
- **Missing piece: `readiness_stagnated` is not a registered deferral reason
  code.** `ll-issues set-status ... --reason readiness_stagnated` will fail
  argparse validation (`choices=[...]`) before the shell state's `|| true` can
  mask it, silently no-opping the stagnation write. Three sites need the new
  code added in lockstep:
  - `scripts/little_loops/cli/issues/__init__.py` — `choices=[...]` list on the
    `set-status --reason` argument (~line 773–791, alongside `low_readiness`,
    `gate_blocked`, `decision_unresolved`, `oversized_atomic`).
  - `scripts/little_loops/cli/issues/set_status.py` — `_DEFERRAL_REASON_CODES`
    frozenset (lines 12–21).
  - `scripts/little_loops/issue_lifecycle.py` — `DeferReason` enum (lines
    58–74) has `LOW_READINESS`, `GATE_BLOCKED`, `DECISION_UNRESOLVED`,
    `OVERSIZED_ATOMIC` members; add `READINESS_STAGNATED = "readiness_stagnated"`
    to keep the Python-side enum and CLI enum in sync.
  - `.claude/CLAUDE.md` § Issue File Format's "Unified not-ready policy" list of
    automation reason codes should also gain `readiness_stagnated` once this
    ships, per that section's existing convention of enumerating every
    autodev-authored code.
- **Repair-class success branches use `next:`/`on_success:`, not `on_yes:`.**
  All five repair-class states use `fragment: with_rate_limit_handling` (except
  `refine_current`, which is a `loop:` delegate), so their success-path key is
  uniformly `next:` (or `on_success:` for the delegate case) — never `on_yes:`.
  Confirmed routing for the counter-increment insertion points:
  - `refine_current` (line 132, `loop: refine-to-ready-issue`) →
    `on_success: copy_broke_down` (line 152)
  - `run_wire` (line 483) → `next: run_refine` (line 490)
  - `run_size_review` (line 918) → `next: enqueue_or_skip` (line 933)
  - `reconcile_current` (line 1245) → `next: rerun_confidence_after_reconcile`
    (line 1255)
  - `run_spike` (line 879) → `next: rerun_confidence_after_spike` (line 891)

  A counter-increment shell action must be spliced in as a new intermediate
  state on each of these five `next:`/`on_success:` edges, or folded into the
  action block of the state each currently routes to.
- **`autodev-pre-spike-readiness.txt` is currently never reset at
  `dequeue_next`** — confirmed by direct read of `dequeue_next`'s action block
  (lines 84–111); it resets `autodev-inflight`, `refine-broke-down`,
  `autodev-broke-down`, `autodev-decide-ran`,
  `autodev-decide-options-deposited`, `autodev-size-review-skipped-this-pass`,
  and repopulates `autodev-pre-ids.txt`, but never touches the spike snapshot.
  This confirms the staleness risk this issue's item (1) is designed to close
  in a multi-issue run.
- **`reconcile_attempted` is issue-frontmatter-scoped, not a run-dir marker
  file** — written by `/ll:reconcile-issue` itself (per the comment at
  `reconcile_current`, autodev.yaml:1250) and read via `ll-issues show --json`
  inside `check_reconcile_needed`'s inline Python (line 1073). It does not need
  an `rm -f` reset at `dequeue_next` the way the `.loops/tmp`-style flags do —
  it is already per-issue by construction.
- **Established snapshot read/write idiom to reuse** (both already present in
  `check_spike_needed` / `check_spike_needed_before_skip` and
  `check_reconcile_needed`): `ll-issues show ${captured.input.output} --json |
  python3 -c "..."` piping into a script that writes/reads a raw (non-JSON)
  string value to `${context.run_dir}/<name>.txt`, guarded by
  `os.path.exists()` on read with a safe `pre = ''` default. The new
  `autodev-pre-readiness.txt` writer/reader should follow this exact shape.
- **Established counter-file idiom** (from `recursive-refine.yaml`'s
  `recursive-refine-dequeued-count.txt` / `recursive-refine-commit-count.txt`,
  and `rn-remediate.yaml`'s per-issue `remediation_count_$${ID}.txt`):
  `N=$(cat "$FILE" 2>/dev/null || echo 0); N=$((N + 1)); printf '%s' "$N" >
  "$FILE"`. Use this shape for `autodev-repair-cycle-count.txt` increments.
- **Deferral write pattern to mirror** for the `readiness_stagnated` branch
  (from `recheck_after_size_review`'s existing `low_readiness` write, lines
  1300–1319, and `mark_gate_blocked`'s `gate_blocked` write): append `"$ID
  <reason>"` (two-space delimiter) to `autodev-skipped.txt`, `rm -f
  ${context.run_dir}/autodev-inflight`, check current status via `ll-issues
  show --json` and skip the `set-status` call if already
  `done`/`completed`/`cancelled` (the BUG-2729 postmortem guard, present
  verbatim at every existing deferral site), otherwise call `ll-issues
  set-status "$ID" deferred --by automation --reason readiness_stagnated
  2>/dev/null || true`.

### Original Codebase Research Findings

- `check_reconcile_needed` (autodev.yaml:1053–1084) is the single plateau
  gate; its inline Python reads only
  `${context.run_dir}/autodev-pre-spike-readiness.txt`. Change: read
  `autodev-pre-spike-readiness.txt` if it exists, else
  `autodev-pre-readiness.txt`; rest of predicate (`pre == cur AND NOT
  reconcile_attempted`) unchanged. Routing (`on_yes: reconcile_current`,
  `on_no: check_size_review_ran_this_pass`) unchanged.
- `dequeue_next` (lines 78–116) gains: snapshot `autodev-pre-readiness.txt`
  per-issue on dequeue; reset `autodev-repair-cycle-count.txt` and remove any
  stale `autodev-pre-spike-readiness.txt` alongside the existing per-issue
  flag resets (`autodev-decide-ran`, etc.) — the spike snapshot is
  run-dir-scoped and would otherwise leak across issues in a multi-issue run.
- `recheck_after_size_review` (lines 1253–1305) is the `low_readiness` write
  site. Before the `echo "$ID  low_readiness"` line, read
  `autodev-pre-readiness.txt` and `autodev-repair-cycle-count.txt`; when
  `cycle_count >= 2 AND current_confidence <= pre_readiness`, write/defer with
  `readiness_stagnated` instead. Mirror in `regate_after_atomic_remediation`
  (lines 1183–1224) for the guard-2 remediation path (its `oversized_atomic`
  reason takes precedence — only the `low_readiness`-equivalent branch is
  affected there, i.e. none; mirroring is limited to counter increments).
- Counter increments (`autodev-repair-cycle-count.txt`): on the success
  branches of `refine_current`, `run_wire`, `run_size_review`,
  `reconcile_current`, `run_spike` — every repair-class state that returns to
  the score-checking chain.

### Files to Modify

- `scripts/little_loops/loops/autodev.yaml` — three edits: (1) `dequeue_next`
  snapshot + counter/spike-snapshot reset; (2) `check_reconcile_needed`
  snapshot fallback; (3) stagnation backstop in `recheck_after_size_review` +
  counter increments in the five repair-class states.
- `scripts/little_loops/cli/issues/__init__.py` — add `readiness_stagnated` to
  the `set-status --reason` `choices=[...]` list (~line 773–791).
- `scripts/little_loops/cli/issues/set_status.py` — add `readiness_stagnated`
  to `_DEFERRAL_REASON_CODES` (lines 12–21).
- `scripts/little_loops/issue_lifecycle.py` — add
  `READINESS_STAGNATED = "readiness_stagnated"` to the `DeferReason` enum
  (lines 58–74).
- `scripts/tests/test_autodev_loop.py` (create, shared with BUG-2752) — see
  Tests.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/deferred_triage.py` — `_REASON_RANK` dict
  (lines 15–26) enumerates every deferral reason code for `ll-issues
  deferred-triage`'s sort order (`remediation_stalled`=0 ... `low_readiness`=5,
  `_DEFAULT_REASON_RANK=6`). Not adding `readiness_stagnated` here is not a
  crash risk (`.get()` falls back to rank 6, tie-broken by age), but leaves the
  new code silently unranked relative to the codes this issue's own summary
  says it should be distinguishable from in triage. Add a rank entry (after
  `low_readiness`, before the default) for consistency with the module's
  documented ranking convention.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — three sites enumerate the fixed set of deferral
  reason codes and must gain `readiness_stagnated`: the closure-context
  `deferred_reason` prose (~line 1180, "`low_readiness`, `gate_blocked`,
  `decision_unresolved`, `oversized_atomic`"), the `set-status --reason <code>`
  flag table row (~line 1664, same list), and the `deferred-triage` rank-order
  prose (~line 1727, "Rank order (highest first): ... `oversized_atomic`,
  `low_readiness`, then any other (unranked) code").
- `docs/reference/API.md` — the `deferred-triage` subcommand section
  (~lines 3745–3751) restates the same rank-order prose in the `next-issue`
  area and must be updated in lockstep with CLI.md.
- `.claude/CLAUDE.md` § Issue File Format's "Unified not-ready policy" bullet
  (~line 184) — already identified by this issue's own refine-issue research
  (see Codebase Research Findings) but was not carried into this Files to
  Modify list; confirmed via wiring pass as a required edit, not optional.
- Ruled out (verified, no change needed): `docs/reference/COMMANDS.md` (grepped
  for all six existing reason codes — no matches, doesn't enumerate them);
  `commands/reconcile-issue.md` (no reason-code references);
  `scripts/little_loops/cli/issues/show.py` (closure-context rendering is
  fully generic — `deferred_reason` is emitted verbatim with no per-value
  branching, confirmed at the `closure_text` fallback chain and JSON emit
  site — needs no change for a new reason-code string).

### Tests

- `test_check_reconcile_needed_fires_from_dequeue_snapshot_without_spike` —
  no `autodev-pre-spike-readiness.txt`; `autodev-pre-readiness.txt` = 85,
  frontmatter confidence 85, no `reconcile_attempted`; assert the predicate
  exits 0 (plateau detected).
- `test_check_reconcile_needed_prefers_spike_snapshot_when_present` — both
  snapshots exist with different values; assert the spike snapshot governs.
- `test_check_reconcile_needed_no_fire_on_confidence_improvement` — pre 85,
  current 88; assert exit 1.
- `test_recheck_after_size_review_defers_with_stagnation_reason_after_two_cycles`
  — `autodev-pre-readiness.txt` 85, `autodev-repair-cycle-count.txt` 2,
  confidence 85; assert `readiness_stagnated` write.
- `test_recheck_after_size_review_still_writes_low_readiness_below_cycle_threshold`
  — same but counter 1; assert unchanged `low_readiness` write (regression
  guard).
- `test_set_status_accepts_readiness_stagnated_reason` (add to
  `scripts/tests/test_set_status_cli.py`, extending the existing
  `test_set_status_deferred_stamps_autodev_reason_codes` parametrization) —
  assert `ll-issues set-status <ID> deferred --by automation --reason
  readiness_stagnated` succeeds and stamps `deferred_reason:
  readiness_stagnated` (regression guard for the CLI `choices=[...]` /
  `_DEFERRAL_REASON_CODES` extension — without it the shell state's `|| true`
  silently swallows the argparse failure). Confirmed pattern: extend the
  existing `@pytest.mark.parametrize("reason_code", [...])` tuple at
  `test_set_status_cli.py:302` — no fixture changes needed, the assertion body
  checks `deferred_by`/`deferred_reason`/`deferred_date` generically.

### Existing Tests That Will Break (regression, not additive)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_autodev_decision_gate.py::test_reconcile_predicate_reads_snapshot_and_guard`
  (lines 509–518) — asserts `"autodev-pre-spike-readiness.txt" in action` on
  `check_reconcile_needed`'s predicate. Must be updated once the predicate also
  handles the `autodev-pre-readiness.txt` fallback, or it will pass vacuously
  while missing coverage of the new branch.
- `scripts/tests/test_autodev_decision_gate.py::test_reconcile_current_invokes_skill`
  (lines 546–552) — asserts `reconcile_current.get("next") ==
  "rerun_confidence_after_reconcile"` literally. **Will fail** if the
  repair-cycle counter increment is spliced in as a new intermediate state on
  this edge (one of the two implementation options this issue's research
  already flags); safe only if the increment is folded into `reconcile_current`'s
  own action block instead. Same risk applies to the mirrored
  `rerun_confidence_after_reconcile`-edge assertion — confirm which
  implementation option is chosen before running this test.
- `scripts/tests/test_builtin_loops.py::test_run_spike_action_and_routing`
  (lines 4952–4961) — asserts `run_spike.get("next") ==
  "rerun_confidence_after_spike"` literally. Same splice-vs-fold risk as above
  for `run_spike`'s counter-increment edge.
- Confirmed **not** at risk (checked directly, only assert `fragment`/
  `action_type`/`action` content, not literal `next`/`on_success` targets):
  `refine_current` (`test_refine_current_has_success_and_failure_routes`,
  test_builtin_loops.py:4021–4030 — only checks `on_success != on_failure`),
  `run_wire` (test_builtin_loops.py:5122–5134), `run_size_review`
  (test_builtin_loops.py:4454–4463, 5787–5793). The five repair-class success
  edges named in this issue's routing table therefore have exactly two
  literal-target regression risks, not five.
- Counter-file idiom confirmed for the new `autodev-repair-cycle-count.txt`
  tests: follow `test_loops_recursive_refine.py`'s
  `test_dequeued_counter_increments_across_calls` (lines 1379–1388) shape —
  call the increment action N times in a loop, read
  `.loops/tmp/recursive-refine-dequeued-count.txt` as `int(...)` after each
  call, assert monotonic `[1, 2, 3]`.

## Acceptance Criteria

- [x] `dequeue_next` writes `autodev-pre-readiness.txt`, resets
      `autodev-repair-cycle-count.txt`, and removes stale
      `autodev-pre-spike-readiness.txt` per issue
- [x] `check_reconcile_needed` detects a plateau from
      `autodev-pre-readiness.txt` when the spike snapshot is absent
      (FEAT-021 profile now reaches `reconcile_current`)
- [x] `check_reconcile_needed` still prefers `autodev-pre-spike-readiness.txt`
      when present; `reconcile_attempted` one-shot guard unchanged
- [x] `recheck_after_size_review` writes `readiness_stagnated` (not
      `low_readiness`) when `cycle_count >= 2` AND `current_confidence <=
      pre_readiness`
- [x] `recheck_after_size_review` still writes `low_readiness` unchanged when
      `cycle_count < 2` (regression guard)
- [x] `readiness_stagnated` is registered as a valid deferral reason code in
      `set-status --reason` choices, `_DEFERRAL_REASON_CODES`, and the
      `DeferReason` enum — `ll-issues set-status <ID> deferred --by automation
      --reason readiness_stagnated` succeeds instead of failing argparse
      validation
- [x] `ll-loop validate autodev` passes with no MR-1 / MR-3 violations after
      changes
- [x] `pytest scripts/tests/test_autodev_loop.py -q` passes
- [x] `pytest scripts/tests/ -q` (full suite) passes

## Resolution

Implemented as scoped:

- `dequeue_next` now writes `autodev-pre-readiness.txt` (pre-refine confidence
  snapshot) per issue, resets `autodev-repair-cycle-count.txt` to `0`, and
  clears any stale `autodev-pre-spike-readiness.txt` from a prior issue.
- `check_reconcile_needed`'s plateau predicate prefers
  `autodev-pre-spike-readiness.txt` when present, else falls back to
  `autodev-pre-readiness.txt` — generalizing the reconcile remedy beyond the
  spike-armed path (rest of the predicate, including the `reconcile_attempted`
  one-shot guard, is unchanged).
- Five new `count_repair_cycle_*` shell states (after `refine_current`,
  `run_wire`, `run_size_review`, `run_spike`, `reconcile_current`) increment
  `autodev-repair-cycle-count.txt`, then forward to each state's original
  target — this required updating two existing tests that asserted the old
  literal `next`/`on_error` targets.
- `recheck_after_size_review` defers with the new `readiness_stagnated` reason
  instead of `low_readiness` when `cycle_count >= 2` AND current confidence is
  no better than the dequeue-time snapshot; the `low_readiness` branch is
  unchanged below that threshold.
- `readiness_stagnated` registered as a valid deferral reason code in
  `set-status --reason` choices, `_DEFERRAL_REASON_CODES`, the `DeferReason`
  enum, and ranked in `deferred_triage._REASON_RANK` (above `low_readiness`,
  below `oversized_atomic`).
- Docs updated: `.claude/CLAUDE.md`, `docs/reference/CLI.md` (3 sites),
  `docs/reference/API.md`.
- New tests added to `scripts/tests/test_autodev_loop.py` (dequeue snapshot,
  fallback-predicate behavior via a subprocess-isolated run of the real inline
  Python, counter-state routing/increment, stagnation-backstop structure) and
  `scripts/tests/test_set_status_cli.py` (readiness_stagnated regression
  guard). Full suite: 16081 passed, 38 skipped, 0 failed.

## Related

- `FEAT-021` (deferred instance this finding comes from)
- BUG-2752 (guard-2 regex loosening — split from this issue, same run/finding)
- ENH-2689 (`check_reconcile_needed` / `autodev-pre-spike-readiness.txt` — the
  spike-coupled plateau gate this issue generalizes)

## Session Log
- `/ll:manage-issue` (implement) - 2026-07-23T23:17:07 - `f83a91ec-6813-4707-9d76-6d8ec10d10ee.jsonl`
- `/ll:confidence-check` - 2026-07-23T23:15:00 - `bf8a3c3f-3ab8-4b30-b7a5-00ff436aeb7b.jsonl`
- `/ll:wire-issue` - 2026-07-23T22:55:10 - `b2f74506-9571-426e-b32d-198d614f619c.jsonl`
- `/ll:refine-issue` - 2026-07-23T22:48:04 - `7c8b59da-d701-4df4-a3e4-fd1f94aa5294.jsonl`

- captured by manual review of `.loops/runs/autodev-20260723T160811/` on
  2026-07-23 at 21:42 — findings synthesized from `usage.jsonl` (4 LLM
  invocations across 25 iterations), `autodev-skipped.txt` (`FEAT-021
  low_readiness`), `autodev-pre-ids.txt` ≡ `autodev-post-ids.txt` (no children
  created), and `FEAT-021` frontmatter (`confidence_score: 85`,
  `outcome_confidence: 86`, `size: Very Large`, `deferred_reason:
  low_readiness`).
- 2026-07-23: split into two issues — guard-2 regex fix moved to BUG-2752
  (low-risk, ships independently); per-issue wall-clock timeout dropped from
  scope.
- 2026-07-23: rescoped after review — root cause identified as
  `check_reconcile_needed`'s spike-coupled snapshot making the reconcile
  remedy unreachable for non-spike issues. Primary deliverable is now the
  generalized plateau gate (dequeue-time `autodev-pre-readiness.txt`
  fallback); the stagnation detector is demoted to a deferral-reason backstop
  that fires only after reconcile has had its shot.

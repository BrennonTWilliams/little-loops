---
id: ENH-2909
type: ENH
priority: P3
status: done
captured_at: '2026-07-29T02:59:11Z'
completed_at: '2026-07-29T05:22:43Z'
discovered_date: 2026-07-29
discovered_by: capture-issue
labels:
- loops
- fsm
- autodev
- efficiency
relates_to:
- BUG-2907
- BUG-2908
confidence_score: 98
outcome_confidence: 82
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 20
---

# ENH-2909: `autodev` dequeue pre-flight — park issues with unmet blockers before refining

## Summary

`autodev`'s `dequeue_next` hands any queued issue straight to the full
refine → wire → confidence-check → size-review chain without first checking
whether the issue is implementable. In the audited run, FEAT-108 spent ~34
minutes and 12 parent iterations completing that chain, only for
`implement_current` to discover it was blocked by an unresolved dependency ring
(`FEAT-108 → FEAT-123 → FEAT-122 → FEAT-108`) and do nothing. A pre-flight
blocker check at dequeue time would have parked it in seconds.

## Current Behavior

`dequeue_next` already performs pre-flight work — it snapshots the backlog to
`autodev-pre-ids.txt` for child detection and (per FEAT-2751) snapshots
pre-refine confidence to `autodev-pre-readiness.txt`. Downstream,
`check_status_at_dequeue` filters issues already `done`/`cancelled`/`deferred`
(ENH-2868), and `check_decision_at_dequeue` filters `decision_needed`.

There is no equivalent check for unmet `blocked_by` / `depends_on` edges, even
though `ll-issues show <ID> --json` exposes `blocked_by` directly and
`ll-deps` provides full cross-issue dependency analysis. The blocked issue
proceeds through the entire refine chain.

## Expected Behavior

At dequeue, an issue whose `blocked_by` / `depends_on` edges are not all
resolved (blocker status `done` or `cancelled` — per BUG-2897, `deferred` is
**non-terminal** and does *not* resolve an edge) is recorded in
`autodev-skipped.txt` with a reason stem (`blocked_by_unmet`, or
`blocked_by_cycle` when the issue participates in a dependency cycle) and the
queue advances without refining it. `finalize_done` surfaces the bucket
separately from generic skips, the way it already does for `already_*`,
`refine_failed_infra`, and gate-blocked issues.

## Motivation

A doomed issue consumes a full refine cycle — sub-loop `refine-to-ready-issue`
(12 iterations at depth 1) plus a nested `verify-confidence-scores` run — before
the loop learns it cannot be implemented. On a multi-issue queue this compounds:
each blocked entry costs a full cycle's wall-clock and tokens while producing no
closure.

## Motivation

Efficiency, not correctness — BUG-2907 and BUG-2908 make the *outcome* honest;
this makes the loop stop paying for a known-unwinnable attempt.

Worth noting explicitly so the implementer does not over-fit: **the refine pass
was not worthless.** It is what discovered and recorded the `blocked_by` edges in
the first place (`+blocked_by: [FEAT-122, FEAT-123, FEAT-124]`, confidence
80→87). An issue with *no* declared blockers that turns out to be blocked cannot
be caught by this pre-flight, and that is acceptable — the check is a cheap
filter on already-declared edges, not a dependency discovery mechanism.

## Proposed Solution

Add a dedicated state between `check_decision_at_dequeue` and `refine_current`
rather than growing `dequeue_next`'s action (which is already long, and whose
`on_yes`/`on_no` routing carries queue-empty semantics that a second predicate
would muddy). This mirrors the existing `check_status_at_dequeue` /
`check_decision_at_dequeue` chain shape:

```yaml
  check_blockers_at_dequeue:
    action: |
      ID="${captured.input.output}"
      ll-issues show "$ID" --json 2>/dev/null | python3 -c "
      import json, sys
      d = json.load(sys.stdin)
      blockers = d.get('blocked_by') or []
      print(','.join(blockers) if blockers else '')
      " > ${context.run_dir}/autodev-blockers.txt
      # unmet := any blocker whose status is not done/cancelled
      # (BUG-2897: deferred does NOT resolve an edge)
    action_type: shell
    on_yes: skip_blocked
    on_no: refine_current
    on_error: refine_current
```

Prefer `ll-deps` over hand-rolled graph walking if it already exposes an
"unmet blockers for ID" query — check its subcommand surface first; the
dependency-graph semantics (including BUG-2897's non-terminal `deferred` rule)
live in `issue_parser.find_issues_for_graph()` and should not be reimplemented in
bash.

`skip_blocked` records the reason and clears `autodev-inflight` (mirroring
`skip_inflight` / `mark_gate_blocked`), then routes `next: dequeue_next`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`ll-deps` has no reusable per-ID query.** `main_deps()`
  (`scripts/little_loops/cli/deps.py`) exposes only `analyze`, `validate`,
  `fix`, `apply`, `tree` — all repo-wide (`broken_refs`, `cycles`,
  `stale_completed_refs`, ...), none answers "is ID X's `blocked_by` unmet."
  The closest primitive is `issue_parser.find_issues(..., skip_blocked=True)`
  (lines 1449–1522), a whole-population readiness filter via
  `DependencyGraph.from_issues(...).get_ready_issues()`, not a single-ID
  lookup. **Do not spend implementation time re-checking this** — the
  hand-rolled shell-in-YAML approach the draft state already sketches is the
  only option; the "check `ll-deps` first" caveat above can be dropped.
- **A near-identical gate already exists and should be ported, not
  reinvented.** `scripts/little_loops/loops/rn-implement.yaml` has
  `check_blocked_by` (lines 407–510) → `route_blocked_by` (512–522) →
  `mark_deferred` (~1332–1368), added for ENH-2008. It parses the issue
  file's frontmatter directly (not `ll-issues show --json`, for shell-escape
  safety), diffs `blocked_by` against `ll-issues list --json --status done`,
  writes unmet deps to `$RUN_DIR/blocked_by_unmet_$${ID}.txt`, and on
  `BLOCKED` calls `ll-issues set-status "$ID" deferred --by automation
  --reason blocked_by_unmet`. `on_error` fails open to the next gate. This is
  a working reference implementation of exactly the state this issue
  proposes — port its shape into `autodev.yaml` rather than authoring the
  pseudo-code above from scratch.
- **`DeferReason.BLOCKED_BY_UNMET` already exists** —
  `scripts/little_loops/issue_lifecycle.py:66`, `class DeferReason(Enum)`.
  Reuse this enum member; no new reason code needs to be added.
- **BUG-2908 has already landed on `main`** — `finalize_done` in
  `autodev.yaml` (lines 1796–1932) already reflects the BUG-2908 rewrite
  (comments throughout cite it explicitly, e.g. "BUG-2908 Step 4"). The
  Impact section's prior sequencing note (which named BUG-2908 as a
  landing-order prerequisite) is now moot — no sequencing risk remains.
- **Exact current state locations in `autodev.yaml`** (for the diff):
  `dequeue_next` (82–148), `check_status_at_dequeue` (150–194) — note its
  inline comment at 166–170 already flags this exact gap ("`blocked` status
  is distinct from unmet `blocked_by` deps, which rn-implement's
  `check_blocked_by` already gates" — i.e. autodev's own code already names
  the missing piece), `skip_already_resolved` (196–213),
  `check_decision_at_dequeue` (215–227), `refine_current` (229–263, has a
  BUG-2611 comment warning never to add an explicit `on_no:` — it would
  shadow `on_failure`), `skip_inflight` (265–298), `mark_gate_blocked`
  (726–748, the dedicated-ledger-file pattern — `autodev-gate-blocked.txt`ing
  its own `.txt` rather than tagging `autodev-skipped.txt`).
- **`finalize_done` bucket-wiring convention** (1825–1897): ledger a
  two-space-delimited `"ID  reason_stem"` line → exclude that stem from the
  generic `Skipped` bucket via `grep -v` → dedicated `COUNT`/`LIST` pair →
  `printf` block gated on `count > 0` → fold into `summary.json` only if it
  should affect verdict (comment at 1902–1904: "decomposed/gate-blocked/
  decision-unresolved/low-readiness parking is not a failure signal" — a new
  `blocked_by_unmet` bucket should follow the same non-failure precedent).
- **Test templates already exist for every piece**
  (`scripts/tests/test_builtin_loops.py`, `class TestAutodevLoop`, 4127+):
  `test_check_status_at_dequeue_routing` (4536) for static route assertions,
  `test_check_status_at_dequeue_classifies` (4574,
  subprocess-with-stubbed-`ll-issues` pattern) for the shell-body unit test,
  `test_check_status_at_dequeue_fails_open_when_cli_missing` (4596) for the
  fail-open case, `test_skip_already_resolved_ledgers_stem_and_clears_inflight`
  (4617) for the skip-state ledger/inflight-clear test, and
  `test_finalize_done_buckets_already_resolved_separately` (4666) for the
  bucket-exclusion test.

Cycle detection is a refinement, not a prerequisite: `ll-auto` already logs
`Dependency cycle detected` and the loop can report `blocked_by_unmet` without
distinguishing a cycle. Add `blocked_by_cycle` as a distinct reason only if
`ll-deps` surfaces cycle membership cheaply.

## API/Interface

No public API change. New run-dir artifacts: `autodev-blockers.txt` (transient),
new reason stems in `autodev-skipped.txt`.

## Scope Boundaries

**In scope**: pre-flight check on declared `blocked_by` / `depends_on` edges at
dequeue; a `skip_blocked` state; `finalize_done` bucket surfacing.

**Out of scope**: discovering undeclared dependencies; auto-resolving or
reordering the queue to implement blockers first (a queue-scheduling change,
materially larger); changing `ll-auto`'s own blocked-issue handling (BUG-2907).

## Integration Map

- `scripts/little_loops/loops/autodev.yaml` — new `check_blockers_at_dequeue` +
  `skip_blocked` states between `check_decision_at_dequeue` (215–227) and
  `refine_current` (229–263); `finalize_done` (1796–1932) bucket rendering.
  BUG-2908 has already landed on `main` (confirmed by inline comments in
  `finalize_done`), so the prior sequencing risk no longer applies.
- `scripts/little_loops/loops/rn-implement.yaml` — `check_blocked_by`
  (407–510) / `route_blocked_by` (512–522) / `mark_deferred` (~1332–1368) is
  a working reference implementation of this exact gate (ENH-2008); port its
  shape rather than writing from scratch.
- `scripts/little_loops/issue_parser.py` — `find_issues_for_graph()`
  (1550–1569), `find_issues(..., skip_blocked=True)` (1449–1522),
  `DependencyGraph`; BUG-2897's non-terminal-`deferred` rule
- `scripts/little_loops/issue_lifecycle.py:66` — `DeferReason.BLOCKED_BY_UNMET`
  already exists; reuse it
- `scripts/little_loops/cli/deps.py` — confirmed no per-ID unmet-blockers
  query exists (`analyze`/`validate`/`fix`/`apply`/`tree` are all repo-wide)
- `scripts/tests/test_builtin_loops.py` — `TestAutodevLoop` (4127+); see
  `test_check_status_at_dequeue_routing` (4536),
  `test_check_status_at_dequeue_classifies` (4574),
  `test_check_status_at_dequeue_fails_open_when_cli_missing` (4596),
  `test_skip_already_resolved_ledgers_stem_and_clears_inflight` (4617),
  `test_finalize_done_buckets_already_resolved_separately` (4666) as test
  templates

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:4536-4551` —
  `test_check_status_at_dequeue_routing` hardcodes
  `state.get("on_no") == "check_decision_at_dequeue"` for the
  `check_status_at_dequeue` state. Inserting `check_blockers_at_dequeue`
  between `check_status_at_dequeue` and `check_decision_at_dequeue` **will
  break this assertion** — it must be updated to point at the new state.
  [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:4236-4263` —
  `test_dequeue_next_routes_to_check_decision_at_dequeue` is a tolerant
  chain-walk (updated for ENH-2868's insertion of `check_status_at_dequeue`);
  it will **not** break from this insertion provided the new state's
  `on_error` routes to its own `on_no`/`next` or on to
  `check_decision_at_dequeue` (fail-open invariant it asserts at 4256-4258).
  Confirms the insertion point is safe. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:6226-6267` —
  `TestAutodevRnImplementDeferralParity` parametrizes over
  `AUTODEV_NOT_READY_STATES = ("mark_gate_blocked",
  "record_decision_unresolved", "recheck_after_size_review")` plus
  rn-implement's `mark_deferred`, asserting each calls `ll-issues set-status
  ... deferred --by automation --reason ...`. As drafted, `skip_blocked` only
  appends to `autodev-skipped.txt` and clears `autodev-inflight` (mirroring
  `skip_inflight`) — it does **not** set `status: deferred`, so it does not
  join this tuple. If a future revision instead defers the issue (as
  rn-implement's own `check_blocked_by`/`mark_deferred` does), this test's
  tuple would need `skip_blocked` added. [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — the autodev FSM-flow diagram (~1000-1052)
  currently shows `dequeue_next → refine_current` with no blocker pre-gate;
  needs the new `check_blockers_at_dequeue → skip_blocked → dequeue_next`
  branch added. Its Output Artifacts table (~476, where rn-implement's own
  `blocked_by` deferral reason is already documented) would need a
  `Blocked-by-unmet` row added alongside autodev's existing
  `Gate-blocked (%d)` / `Decision-unresolved (%d)` bucket lines. [Agent 2
  finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `test_check_blockers_at_dequeue_classifies` (new, model after
  `test_check_status_at_dequeue_classifies`,
  `test_builtin_loops.py:4552-4595`) — **cannot be a straight port**: if the
  state is ported from rn-implement's `check_blocked_by` shape (per the
  issue's own recommendation), that state execs `ll-issues list --json
  --status done` and parses `.issues/*/*.md` frontmatter directly rather than
  calling `ll-issues show <ID> --json` per the draft pseudo-code above. The
  stub setup must therefore create a real issue `.md` file with `blocked_by:`
  frontmatter under a temp `.issues/<category>/` for the glob-scan to find,
  not just stub CLI output. [Agent 3 finding]
- rn-implement's `check_blocked_by`/`route_blocked_by` (rn-implement.yaml
  407-522) have **no existing dedicated unit test** in
  `test_builtin_loops.py` — only `mark_deferred`'s action-text is compared
  for shape parity (e.g. `test_autodev_not_ready_exit_matches_mark_deferred_shape`,
  ~6254). There is no test to "port" for the shell-body logic itself; new
  coverage must be written from scratch using
  `test_check_status_at_dequeue_classifies`'s subprocess-stub mechanics as
  the template. [Agent 3 finding]
- `test_finalize_done_buckets_blocked_by_unmet_separately` (new, model after
  `test_finalize_done_buckets_already_resolved_separately`,
  `test_builtin_loops.py:4666-4699`) — seed a `blocked_by_unmet_<ID>` (or
  chosen stem) ledger line in `autodev-skipped.txt` and assert it lands in
  its own bucket, excluded from `Already-resolved` and generic `Skipped`.
  [Agent 3 finding]

## Implementation Steps

1. Check `ll-deps`' subcommand surface for an existing "unmet blockers for ID"
   query before writing any graph logic in the loop.
2. Add `check_blockers_at_dequeue` + `skip_blocked`; wire the routing.
3. Surface the new reason stem in `finalize_done`'s summary buckets.
4. Tests: an issue with a `done` blocker refines normally; one with an `open`
   blocker is skipped with reason; one with a `deferred` blocker is **also**
   skipped (BUG-2897 regression guard).
5. `ll-loop validate autodev` clean.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `test_check_status_at_dequeue_routing`
   (`test_builtin_loops.py:4536-4551`) — its hardcoded
   `on_no == "check_decision_at_dequeue"` assertion breaks once
   `check_blockers_at_dequeue` is inserted; point it at the new state.
7. Write `test_check_blockers_at_dequeue_classifies` from scratch (no
   existing rn-implement `check_blocked_by` test to port) — stub via a real
   temp `.issues/` frontmatter file plus `ll-issues list --json --status
   done`, not a bare `ll-issues show` stub, if the state is ported from
   rn-implement's shape.
8. Write `test_finalize_done_buckets_blocked_by_unmet_separately`
   (`test_builtin_loops.py:4666-4699` pattern).
9. Update `docs/guides/LOOPS_REFERENCE.md`'s autodev flow diagram and Output
   Artifacts bucket table to include the new state and bucket.

## Success Metrics

A queued issue with an unmet blocker is parked in one dequeue cycle instead of
consuming a full refine chain (~12 iterations / ~30 min in the observed case).

## Impact

- **Efficiency**: removes the dominant wasted-cycle case from `autodev` runs on
  dependency-heavy backlogs.
- **Ordering**: BUG-2908 (previously a `depends_on` blocker) has already
  landed on `main` — confirmed by its comments already present in
  `finalize_done`. The dependency edge has been downgraded to `relates_to`
  since it no longer blocks this issue.
- **Risk**: a too-aggressive predicate would skip implementable issues. Confining
  the check to declared edges with terminal-status resolution keeps it
  conservative; the `on_error: refine_current` fallback fails open.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.claude/CLAUDE.md` § Issue File Format | `deferred` is non-terminal for dependency purposes (BUG-2897) |
| `docs/ARCHITECTURE.md` | dependency graph and orchestration layers |
| `audit-loop-run-autodev-2026-07-29T013824.md` | audit report with verbatim run evidence |

## Resolution

Added a `check_blockers_at_dequeue` / `skip_blocked` pre-flight gate to
`autodev.yaml` between `check_decision_at_dequeue` and `refine_current`,
ported from `rn-implement.yaml`'s `check_blocked_by` shape (ENH-2008). The
gate parses the dequeued issue's own frontmatter directly, diffs `blocked_by`
against `ll-issues list --json --status done`, and treats `deferred` blockers
as unmet per BUG-2897. `skip_blocked` ledgers `"$ID  blocked_by_unmet"` to
`autodev-skipped.txt`, clears `autodev-inflight`, and routes back to
`dequeue_next` — it does not change issue status (out of scope). `on_error:
refine_current` fails open. `finalize_done` now surfaces a dedicated
`Blocked-by-unmet` bucket, excluded from the generic `Skipped` count and not
folded into `summary.json`'s verdict, matching the gate-blocked/decision-
unresolved precedent.

Added six new tests in `test_builtin_loops.py` (routing, classification,
BUG-2897 deferred-blocker regression guard, ledger/inflight-clear, bucket
separation) and updated two pre-existing routing tests in
`test_autodev_decision_gate.py` that hardcoded the old
`check_decision_at_dequeue` → `refine_current` edge. Updated
`docs/guides/LOOPS_REFERENCE.md`'s autodev FSM-flow diagram and Output
Artifacts table. `ll-loop validate autodev` clean; full suite (17004 passed,
42 skipped) green.

## Session Log
- `/ll:confidence-check` - 2026-07-29T00:00:00Z - `fb4dce37-4b3a-4631-844c-3890a7bdbe69.jsonl`
- `/ll:wire-issue` - 2026-07-29T05:05:29 - `5c485344-103b-412a-880e-2a03a0d38468.jsonl`
- `/ll:refine-issue` - 2026-07-29T04:58:39 - `59c4fbe3-eba4-4104-a2a8-9b53c7863a18.jsonl`
- `/ll:capture-issue` - 2026-07-29T02:59:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a15bf47-b270-4d12-a74c-47b9c005a000.jsonl`
- `/ll:manage-issue` - 2026-07-29T05:22:11Z - `2ed5591f-4c09-4b99-ae99-5842ed744ac2.jsonl`

---

## Status

`open`

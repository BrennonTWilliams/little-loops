---
id: ENH-3606
type: ENH
title: Move autodev second-pass preparation states into prepare-issue
priority: P3
status: open
discovered_by: issue-size-review
discovered_date: '2026-09-26'
decision_needed: false
blocked_by:
- ENH-3605
- ENH-3611
blocks:
- ENH-3600
relates_to:
- ENH-3590
- ENH-3577
- ENH-3609
- ENH-3610
parent: ENH-3601
---

# ENH-3606: Move autodev second-pass preparation states into prepare-issue

## Summary

Second half of ENH-3601 (Option B), re-cut on 2026-09-26. With the `prepare-issue`
pass-through wrapper and its ledger-ownership rule in place (ENH-3605), move the whole
second-pass cluster out of `autodev.yaml` in one change:

- wire/refine;
- reconcile and design remedy;
- size-review and atomic remediation;
- go/no-go;
- pre-deferral remedy;
- the obligation selectors ENH-3610/3611 add.

Afterwards autodev owns only the queue, the ledger bookkeeping, and the fail-closed proof
gate in front of `implement_current`. The go/no-go trigger stays the existing deterministic
`deferred_reason: oversized_atomic` predicate, unchanged.

## Why one change

The states form one strongly connected cluster: reconcile → size-review →
`recheck_after_size_review` → pre-deferral remedy → reconcile, with the selectors
re-entering the refine child from several points. A `loop:` child cannot route into its
parent's states. Any cut through the cluster leaves edges with no destination, or forces an
interim "continue in autodev" outcome that `PreparationOutcome` does not have. That is why
the original ENH-3605/3606 split was replaced with plumbing (ENH-3605) followed by this
single move.

## Parent Issue

Decomposed from ENH-3601: Move autodev second-pass preparation routing into a preparation
controller. See the parent for the decision rationale.

## Current Behavior

After ENH-3605 and ENH-3609–3611, autodev still owns the second-pass ladder behind its
`check_passed` gate. That ladder is `select_obligation_post_refine` →
`check_missing_artifacts` → wire/refine → reconcile/design remedy → size-review/atomic →
`select_obligation_post_size_review` → go/no-go and pre-deferral remedy →
`select_obligation_pre_implement`. It also owns the `wire`, `reconcile` and `atomic`
rescoring triplets. Each ladder exit re-enters `refine_current` or reaches the proof gate
inside autodev.

## Expected Behavior

`prepare-issue` runs its inner `refine-to-ready-issue` and then its own pass gate and
second-pass ladder. It re-enters its inner loop when a selector returns `DECISION*` or
`PROOF*`, and emits one terminal record: `READY`, a ledgered `BLOCKED:*` / `DEFERRED:*`
stop, `DECOMPOSED`, `CANCELLED` or `RETRYABLE_ERROR:*`. Autodev has no second-pass state.

## Scope Boundaries

- **In scope**: every state listed in Scope, the shared rescoring path, the wrapper
  terminals, the autodev fail-safes for tokens that become impossible, the tests/docs that
  pin these states, and the queue-only absence test.
- **Out of scope**:
  - widening the go/no-go trigger with a risk signal (separate follow-up);
  - removing legacy sentinels and ledger files (ENH-3600);
  - new `PreparationOutcome` values or run-record tokens;
  - changes to `refine-to-ready-issue.yaml`;
  - `recursive-refine.yaml`'s same-named states (`size_review_snap`, `check_broke_down`,
    `recheck_scores`, `enqueue_or_skip`, `detect_children`).

## Scope

### Anchor refresh (first step)

Every state name, edge and line anchor in this issue was researched against pre-ENH-3609–3611
`autodev.yaml`, and ENH-3610/3611 rename, add and drop states (for example,
`snap_and_size_review` is dropped by ENH-3611). Before editing, regenerate the boundary edge
table against post-ENH-3611 `autodev.yaml`:

- every edge from a moving state to a staying state;
- every edge from a staying state to a moving state.

Record it in this issue. Each entry must end up either internal to the wrapper, as a
wrapper terminal, or retargeted in autodev per the rules below.

### States that move into `prepare-issue.yaml`

- **Pass gate and selectors**: a wrapper-local `check_passed` (run after the inner loop's
  done path), `select_obligation_post_refine`, `select_obligation_post_size_review`, and
  `select_obligation_pre_implement` (ENH-3610/3611).
  - A selector's `refine_current` re-entry target becomes a loop back to the wrapper's
    `run_refine_to_ready`.
  - Its proof-gate target (`check_proof_defer_or_implement`) becomes the wrapper's `ready`
    terminal.
- **Wire/refine**: `check_missing_artifacts`, `run_wire`, `run_refine`,
  `count_repair_cycle_wire`.
- **Reconcile/design remedy**: `check_reconcile_needed`, `reconcile_current`,
  `refine_for_design`, `check_atomic_design_remedy`, `dispatch_design_remedy`,
  `count_repair_cycle_reconcile`, `count_repair_cycle_refine_for_design`.
- **Size-review/atomic**: `run_size_review`, `count_repair_cycle_size_review`,
  `check_size_review_ran_this_pass`, `check_guard2_verdict`, `check_guard2_score_fallback`,
  `check_readiness_for_atomic_remediation`, `remediate_oversized_atomic`,
  `regate_after_atomic_remediation`, `recheck_after_size_review`, `recheck_scores`,
  `check_parent_resolved_post_size_review`, plus the child-detection half of
  `enqueue_or_skip` (see Queue ownership).
- **Go/no-go**: `check_go_no_go_eligible`, `run_go_no_go`, `check_go_no_go_waiver`,
  `reopen_waived` (only for `deferred_reason: oversized_atomic`).
- **Pre-deferral remedy**: `check_pre_deferral_remedy`, `dispatch_pre_deferral_remedy`.
- **Repair-cycle counter**: `count_repair_cycle_refine` moves to become the wrapper's
  pre-state of `run_refine_to_ready`. After the move, re-entries happen inside the wrapper
  and no longer pass autodev's `refine_current → count_repair_cycle_refine`. Left in
  autodev, the counter would undercount, and `recheck_after_size_review`'s stagnation
  backstop (count ≥ 2) would stop firing. Moving it keeps "every inner entry increments"
  for the first entry and every re-entry.

### States that stay in autodev (queue-only)

- `init`, `dequeue_next` and the dequeue checks (`check_status_at_dequeue`,
  `check_blockers_at_dequeue`, `check_gate_at_dequeue` and their skip/defer states).
- `refine_current`, `copy_broke_down`, the ENH-3607/3609 routers and `ledger_child_stop`.
- `check_passed`, kept as a fail-closed double check on `READY`; its `on_no` and
  `on_cannot_judge` become `skip_inflight`.
- `check_proof_defer_or_implement`, `implement_current` and the post-implementation states.
- Queue and ledger states: `skip_inflight*`, `mark_*_infra`, `detect_children`,
  `enqueue_children`, `check_parent_resolved`, `recover_subloop_children`,
  `finalize_rate_limited`, `finalize_done` and the terminals.
- `size_review_snap` and `check_broke_down` are only on `detect_children`'s no-children
  fallback. Delete them if the DECOMPOSED guarantee below makes them unreachable, or keep
  them as the fail-safe path; pin whichever you choose.

### Shared rescoring path

Replace the `wire`, `reconcile` and `atomic` triplets with one path. Each entry point
writes `rescore-origin-<ID>` (`wire` | `reconcile` | `atomic`) → `clear_scores` →
`rerun_confidence` → `check_scores_present` → `route_after_rescore`. `route_after_rescore`
reads the marker and dispatches to that origin's post-ENH-3611 successor. Today those
successors are `enqueue_or_skip`, `recheck_after_size_review` and
`regate_after_atomic_remediation`.

- Keep the per-origin retry marker names (`autodev-rescore-retry-<origin>-<ID>`) so
  `dequeue_next`'s clear is unchanged.
- An unknown or missing origin routes to the scores-absent terminal (fail closed).
- Keep the BUG-3588 freshness rules.
- Re-declare the `confidence-check-recheck` `pruning_profile:` once.

### Queue ownership and the DECOMPOSED guarantee

- The wrapper never writes `autodev-queue.txt` and never runs `finalize-decomposition`.
- Size-review decomposition keeps the child detection from `enqueue_or_skip`: diff the IDs
  and match `parent:`/"Decomposed from" provenance (BUG-2729) into
  `autodev-new-children.txt`. It then writes `1` to `refine-broke-down` and ends in a
  `decomposed` record with `--child-ids`.
- Autodev's existing `DECOMPOSED` → `detect_children` → `enqueue_children` path does the
  enqueue. `enqueue_children` already writes the `decomposed` row and runs
  `finalize-decomposition`, exactly as `enqueue_or_skip`'s queue branch does today.
- Confirm that `detect_children`'s `autodev-pre-ids.txt` baseline predates the wrapper, so
  size-review children fall inside its diff. Pin this with a test.
- **Guarantee**: the wrapper emits `decomposed` only when `child_ids` is non-empty or the
  parent is resolved. `check_parent_resolved_post_size_review.on_yes` emits `decomposed`, so
  autodev reaches `recover_subloop_children` through `detect_children` (no children) →
  `check_parent_resolved`. A parent that is not resolved and has no children continues the
  wrapper's ladder and never returns to autodev.
- `dequeue_next` stays the only cleaner of the per-pass markers
  (`autodev-size-review-ran-this-pass`, `autodev-pre-deferral-remedy.txt` / `-fired`, rescore
  retry markers, the repair-cycle counter reset). The wrapper must not clear them on entry,
  because re-entries within one pass must still see them.

### Terminal table

Every row writes a `writer: prepare-issue` record. Per ENH-3605's rule, the wrapper writes
the ledger row with the same reason string as today, and autodev routes every
`BLOCKED:*` / `DEFERRED:*` to `ledger_child_stop` (no row).

| Wrapper stop (today's row) | Outcome / `--legacy-class` | Autodev route |
|---|---|---|
| `oversized_atomic` (incl. go/no-go escalation, waiver declined) | `deferred` / `gate_unmet` | `ledger_child_stop` |
| `design_gate_failed` | `deferred` / `gate_unmet` | `ledger_child_stop` |
| `readiness_stagnated`, `low_readiness` | `deferred` / `gate_unmet` | `ledger_child_stop` |
| `decision_unresolved` (from `recheck_after_size_review`) | `blocked` / `decision_unresolved` | `ledger_child_stop` |
| atomic-remediation failure | `blocked` / `quality` | `ledger_child_stop` |
| `resolved_by_subloop` / parent resolved | `decomposed` (see guarantee) | `detect_children` |
| size-review decomposition | `decomposed` + `--child-ids` | `detect_children` → `enqueue_children` |
| rate-limit exhaustion | `retryable_error` / `infra` + `--evidence-refs rate_limit_exhausted` | `finalize_rate_limited` |
| scores absent after repair | `retryable_error` / `infra` | `skip_inflight_infra` |
| state `on_error` exits that today go to `dequeue_next` | `retryable_error` / `infra` | `skip_inflight_infra` |
| ladder complete, gates pass | `ready` | `check_passed` → `check_proof_defer_or_implement` |

- Keep the `deferred_reason` frontmatter writes (`ll-issues set-status --reason ...`)
  exactly as today; `deferred_triage`, `show` and `check_readiness --honor-waiver` read them.
- `reopen_waived` runs inside the same wrapper run that wrote the `oversized_atomic` row, so
  its `grep -vxF "$ID  oversized_atomic"` removal and `autodev-inflight` re-arm keep
  working. Pin this with a test.

### Rate limits

- Every moved slash state (`run_wire`, `run_refine`, `reconcile_current`, `refine_for_design`,
  `rerun_confidence`, `remediate_oversized_atomic`, `run_go_no_go`) keeps
  `with_rate_limit_handling`. Its `on_rate_limit_exhausted` goes to a wrapper-local
  `mark_rate_limited` terminal that writes `--legacy-class infra --evidence-refs
  rate_limit_exhausted`. That preserves today's halt through `finalize_rate_limited`.
- `run_size_review` is the odd one out today: `on_rate_limit_exhausted: dequeue_next` drops
  the issue silently, with no row. **Decided (2026-09-26)**: halt like every other site.
  `run_size_review`'s `on_rate_limit_exhausted` goes to `mark_rate_limited`, which ends in
  `finalize_rate_limited` in autodev. A dedicated test pins it.

### Accepted behavior changes

Document these in `docs/guides/LOOPS_REFERENCE.md`:

- Scores-absent stops and `on_error → dequeue_next` drops now produce one
  `refine_failed_infra` row. Today they are invisible in `finalize_done`, and
  `autodev-scores-absent.txt` is never read.
- `run_size_review` rate-limit exhaustion now halts the queue through `finalize_rate_limited`
  instead of silently dropping the issue and moving to the next one.

### Mechanics

- Rewrite every `${captured.input.output}` in the moved states to `${context.input}`
  (passthrough flattens `captured` into the child context). Update or remove the
  `# ll-lint: mr11-ok(captured.input.output)` markers (`TestMr11MarkerSet`).
- Moved states must take their captures from wrapper states. For example,
  `captured.size_review_output` feeds `check_guard2_verdict` / `check_guard2_score_fallback`
  through `evaluate.source`.
- Re-declare `pruning_profile:` blocks: `run_wire` `wire-issue-auto`, `run_refine` /
  `refine_for_design` `refine-issue-repair`, `rerun_confidence` `confidence-check-recheck`,
  `reconcile_current` `reconcile-issue-auto`, and `run_size_review` `issue-size-review-auto`.
  Otherwise MR-12 warns.
- Shared per-issue files must keep their names, because both loops read them through the
  shared `run_dir`:
  - `autodev-repair-cycle-count.txt`, `autodev-pre-readiness.txt`,
    `autodev-design-gate-failed-<ID>`, `autodev-design-remedy-attempted-<ID>`,
    `autodev-atomic-design-remedy-pending`;
  - `autodev-contradiction-reconcile-*`, `autodev-go-no-go-attempted-<ID>`,
    `autodev-pre-deferral-remedy*`, `autodev-size-review-ran-this-pass`, `spike-runs-<ID>`.

## Tests

- **Queue-only absence**: a `REMOVED_INLINE_STATES`-shaped parametrized test covering every
  moved state (pattern: `TestIssueRefinementSubLoop` ~`test_builtin_loops.py:1323`/`:1413`).
  Also assert that `enqueue_children`, `dequeue_next` and `recover_subloop_children` are the
  only writers of `autodev-queue.txt` across both loops.
- **Wrapper structure** (`test_prepare_issue.py`): the moved states exist; the selector
  re-entry targets `run_refine_to_ready` and the proof target is the `ready` terminal; every
  terminal writes `--writer prepare-issue`; every moved slash state's
  `on_rate_limit_exhausted` targets `mark_rate_limited`; there is exactly one
  `clear_scores` / `rerun_confidence` / `check_scores_present` / `route_after_rescore`
  chain.
- **Wrapper execution** (real FSM, stub skills):
  - one case per terminal-table row, asserting the record token and the exact ledger rows
    (no double count);
  - the rescoring dispatch for each origin, plus unknown origin → scores-absent;
  - the repair-cycle counter increments on the first entry and on each re-entry, and the
    stagnation backstop still fires at count ≥ 2;
  - the DECOMPOSED guarantee (no `decomposed` record with empty `child_ids` and an
    unresolved parent);
  - `reopen_waived` removes the row and re-enters;
  - the go/no-go trigger predicate is unchanged.
- **Autodev**:
  - `check_passed.on_no` / `on_cannot_judge` → `skip_inflight`;
  - `TestProofGateFailClosed` still passes (only `check_proof_defer_or_implement` precedes
    `implement_current`);
  - `test_fsm_topology.py::test_autodev_topology` count updated, with a delta comment;
  - real-FSM: a size-review decomposition enqueues children through `enqueue_children`
    with one `decomposed` row.
- **Relocate or rewrite** (don't delete; ENH-3075 AC 8) against a `prepare-issue.yaml`
  loader. The inventories below list the suites.
- **Record mapping**: extend `test_run_record.py` `TestOutcomeMapping.CASES` (:235-250) and
  `test_legacy_class_mapping_via_cli` (:340-348) with the terminal table's classes, and add
  a `prepare-issue` mirror of `TestLoopCallSites` (:494-550).
- **Baselines and gates**: update `loop_interpolation_baseline.json` (move the autodev
  `check_reconcile_needed` entry to `prepare-issue.yaml`, and add entries for unbaselined
  wrapper sites; `recursive-refine.yaml`'s `enqueue_or_skip` / `recheck_scores` entries do
  not move). Re-check `TestMr11MarkerSet` and `TestSubLoopStateTimeoutAudit`.

## Docs

- `docs/guides/LOOPS_REFERENCE.md`:
  - autodev ASCII tree (~:1038-1072, :1184-1186) and the notes/dispatch paragraphs
    (~:1081-1087);
  - the pre-dequeue flow (~:1035-1037);
  - the BUG-2734/BUG-3390 go/no-go, pre-deferral and `recheck_after_size_review`
    paragraphs, and `:579` (`run_size_review`);
  - move the wire/reconcile/score-freshness paragraphs to `### prepare-issue`, and add the
    accepted behavior changes.
- `docs/reference/DEFERRAL_CODES.md` `:24-30`: Source citations name `prepare-issue` states.
- `docs/reference/CLI.md`: `:2272`, `:2318`, `:2334-2335`, `:2687`, `:2884`,
  `:3090-3095`, and the run-record section (`:2403-2438`).
- `docs/reference/API.md`: `:983`, `:4662-4681`.
- `docs/reference/COMMANDS.md`: `:307`, `:311`, `:366`.
- `docs/reference/ISSUE_TEMPLATE.md`: `:916`, `:919`.
- `docs/ARCHITECTURE.md`: `:463`, `:672`, `:676`, `:821`.
- `commands/reconcile-issue.md` (`:83`, `:145`, `:197`, `:368`) and
  `commands/refine-issue.md:1073`.
- `skills/go-no-go/SKILL.md:402` and `skills/audit-loop-run/SKILL.md:271`, re-anchored to
  `prepare-issue`. Then run `ll-adapt --host <gemini|kimi-code|qwen> --apply` and re-check
  the `test_wiring_skills_and_commands.py` line pins (~:750-751, which pin
  `skills/go-no-go/SKILL.md` lines 176 and 276).
- Comments only:
  - `little_loops.cli.issues.show` (:148), `little_loops.cli.issues.check_gate` (module
    docstring), `little_loops.cli.issues.deferred_triage` (:12, :25) and
    `little_loops.issue_manager` (:1230);
  - `loops/rn-refine.yaml` (:419, :500);
  - the `refine-to-ready-issue.yaml` header comments that cite autodev states.

## Acceptance Criteria

- [ ] `autodev.yaml` has no wire, reconcile, design-remedy, pre-deferral, size-review, go/no-go, selector or rescoring states (explicit absence test)
- [ ] Autodev is the only writer of `autodev-queue.txt` (`enqueue_children`, `dequeue_next`, `recover_subloop_children`); the wrapper writes none
- [ ] `prepare-issue` has exactly one rescoring path with per-origin dispatch and the BUG-3588 freshness rules; the retry marker names are unchanged
- [ ] Every `prepare-issue` terminal writes a `writer: prepare-issue` record matching the terminal table, the ledger rows keep today's reason strings, and no stop is ledgered twice
- [ ] Rate-limit exhaustion in any moved slash state halts autodev through `finalize_rate_limited`, including `run_size_review` (no more silent `dequeue_next` drop)
- [ ] The repair-cycle counter increments on every inner entry, including wrapper re-entries; the stagnation backstop test passes
- [ ] A `decomposed` record always has non-empty `child_ids` or a resolved parent; size-review children are enqueued through autodev's `enqueue_children`
- [ ] The go/no-go trigger is the unchanged, deterministic `oversized_atomic` predicate
- [ ] `implement_current`'s only predecessor is `check_proof_defer_or_implement`, and `READY` comes only from the wrapper's pass gate plus `select_obligation_pre_implement`
- [ ] The relocated behavioral suites pass; `auto-refine-and-implement` summary counts are unchanged in a real-FSM run

## Impact

- **Priority**: P3 - completes the ENH-3601 decomposition and unblocks ENH-3600
- **Effort**: Very Large - ~40 states plus the selectors, a rescoring consolidation and a large test/doc migration; not splittable further because the cluster is strongly connected
- **Risk**: High - rewrites the second-pass routing of the most-used loop; mitigated by ENH-3605's plumbing and ledger rule landing first, per-row terminal tests, and an unchanged go/no-go predicate
- **Breaking Change**: No (the accepted behavior changes above are ledger-visibility only)

## Integration Map

_Line anchors and edge names below predate ENH-3609–3611 (and partly ENH-3607). Refresh
them in the first implementation step. Research from the original ENH-3605 (wire/refine,
reconcile/design) was merged here on 2026-09-26._

### Codebase Research Findings

- **Files to modify**:
  - `scripts/little_loops/loops/autodev.yaml`. Wire/reconcile/design: `refine_current`
    ~:511, `run_wire` ~:1033, `check_missing_artifacts` ~:1871, `check_reconcile_needed`
    ~:2051, `check_atomic_design_remedy` ~:2411, `refine_for_design` ~:2523,
    `reconcile_current` ~:2565, `dispatch_design_remedy` ~:2951.
  - The same file, size-review/go-no-go/pre-deferral: `detect_children` ~:1413,
    `size_review_snap` ~:1490, `check_broke_down` ~:1503, `run_size_review` ~:1882,
    `count_repair_cycle_size_review` ~:1905, `enqueue_or_skip` ~:1924, guard2 / readiness /
    `remediate_oversized_atomic` ~:2152-2242, `regate_after_atomic_remediation` ~:2317,
    go/no-go ~:2436-2497, `recheck_after_size_review` ~:2682, pre-deferral ~:2930/2975.
  - `scripts/little_loops/loops/prepare-issue.yaml` (new) — created by ENH-3605.
- **Rescoring triplets**: five existed (`decide`, `wire`, `spike`, `atomic`, `reconcile`);
  ENH-3610/3611 remove `decide` and `spike`. The remaining three differ only in entry point,
  successor and retry-marker name, and are cleared by `dequeue_next`. `refine_for_design`
  and `count_repair_cycle_reconcile` both feed `clear_scores_before_reconcile`. All three
  `check_scores_present_*` / `clear_scores_before_*` route failures to
  `mark_scores_absent_infra`, which stays in autodev and writes only
  `autodev-scores-absent.txt` (no skipped row).
- **Repair-cycle counter**: `count_repair_cycle_{refine,wire,size_review,refine_for_design,reconcile}`
  all write `autodev-repair-cycle-count.txt`. `recheck_after_size_review` reads it for the
  stagnation backstop (count ≥ 2 with confidence not above `autodev-pre-readiness.txt`).
  `dequeue_next` resets it.
- **Size-review sentinels**: `autodev-pre-ids.txt` / `-post-ids.txt` / `-diff-ids.txt` /
  `-new-children.txt` are written by `size_review_snap`, `detect_children`, `enqueue_or_skip`
  and `recover_subloop_children`. `autodev-size-review-ran-this-pass` is set by
  `count_repair_cycle_size_review`, read by `check_size_review_ran_this_pass`, and cleared by
  `dequeue_next`.
- **Design-remedy state**:
  - `autodev-atomic-design-remedy-pending` is written by `regate_after_atomic_remediation`
    and consumed by `check_atomic_design_remedy`;
  - `autodev-design-remedy-attempted-<ID>` has no further notes;
  - `autodev-pre-deferral-remedy.txt` / `-fired` are written by `recheck_after_size_review`
    and cleared by `dequeue_next`;
  - `autodev-go-no-go-attempted-<ID>` is per-issue and never cleared (one-shot).
  - `reopen_waived` re-arms `autodev-inflight`.
- **Coupling to the queue file**:
  - `enqueue_or_skip`'s queue branch duplicates `enqueue_children`: both merge
    `autodev-new-children.txt` into `autodev-queue.txt`, append `ID  decomposed` to
    `autodev-skipped.txt`, run `ll-issues finalize-decomposition --children-file`, and clear
    `autodev-inflight`.
  - `enqueue_or_skip.on_no` → `check_parent_resolved_post_size_review`, and
    `check_broke_down.on_yes` → `check_parent_resolved`.
- **Ledger writes in moved states**:
  - `recheck_after_size_review` writes `resolved_by_subloop`, `design_gate_failed`,
    `decision_unresolved`, `readiness_stagnated` and `low_readiness`;
  - `regate_after_atomic_remediation` writes `resolved_by_subloop`, `design_gate_failed`
    and `oversized_atomic`;
  - `reopen_waived` removes `oversized_atomic` with `grep -vxF`;
  - `enqueue_or_skip` writes `decomposed`.
  - `finalize_done` (~:3066-3129) parses `autodev-skipped.txt` by reason substring;
    `auto-refine-and-implement` builds `SKILL_BREAKDOWN` from the reason column
    (~:1118-1133).
- **Terminal mapping constraint**: `outcome_from_legacy_class` is first-match-wins
  (`cancelled` → `broke_down` → `infra` → `decision_unresolved`/`proposal_unsound`/`quality`
  → `spike_inconclusive`/`gate_unmet` → thresholds). The run-record CLI accepts only the six
  `LEGACY_CLASSES`, so `gate_unmet` loses the specific reason in `legacy_class`. The ledger
  row and the `deferred_reason` frontmatter carry it.
- **Rate-limit**: `run_size_review` uses `on_rate_limit_exhausted: dequeue_next` (to become a
  halt; see Rate limits); the other
  moved slash states go to `finalize_rate_limited` (`run_go_no_go` is pinned at
  `test_builtin_loops.py:8254-8258`). The `subloop_rate_limit_diagnostic` fragment
  (`lib/common.yaml:446`) needs `operation` through `with:` and `${context.issue_id}`.
  `rn-decompose.yaml`'s `run_size_review` → `rate_limit_diagnostic` is the existing
  sub-loop-side shape.
- **Inbound cross-boundary edges (pre-ENH-3611 names)**:
  - `check_spike_needed` → `check_missing_artifacts` becomes ENH-3610's
    `select_obligation_post_refine` `_` → `check_missing_artifacts`;
  - `check_spike_needed_before_skip` → `check_reconcile_needed` becomes ENH-3611's
    `select_obligation_post_size_review`;
  - `check_passed.on_no` → selector;
  - `check_parent_resolved.on_no` → `recheck_scores`;
  - `check_broke_down.on_no` → `enqueue_or_skip`.

### Conventions in Force

- State-move tests: extracted-loop suites live in their own file and assert states through
  `data["states"][name]` (`test_rn_decompose.py`). Source loops assert absence with a
  `REMOVED_INLINE_STATES` parametrized test (`TestIssueRefinementSubLoop`,
  ~`test_builtin_loops.py:1323`).
- Baseline JSON entries are keyed `(file, state, var, class)` and must move in the same
  commit as the state (`TestInterpSweepBaseline::test_completeness_guard`).
- `test_fsm_topology.py::TestAutodevSmoke::test_autodev_topology` (~:233-261) pins
  autodev's state count, with a commented delta per issue.
- Mirror gates after skills/README edits: `test_adapters.py` (~:1176-1203) and
  `test_packaging_duplicate_files.py` (~:22). The docs-audience gate forbids
  `scripts/tests/` and `scripts/little_loops/` citations in `docs/guides`,
  `docs/reference`, `skills/` and `commands/`.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/auto-refine-and-implement.yaml`: reads `autodev-queue.txt`
  (~:477/:1077), `autodev-inflight` (~:1058) and the ledgers (~:1088-1144, `SKILL_BREAKDOWN`
  ~:1118-1133). Its counts must not change. `scan-and-implement.yaml:79` also calls
  `loop: autodev`.
- `scripts/little_loops/loops/recursive-refine.yaml`: has its own `check_missing_artifacts`
  (~:594-602), `size_review_snap`, `check_broke_down`, `recheck_scores`, `enqueue_or_skip`
  and `detect_children`. The names collide only; do not touch them. `rn-decompose.yaml` has
  its own `run_size_review`.
- `little_loops.cli.issues.run_record` / `little_loops.run_record`: no change beyond
  ENH-3605's `forward`. `_read_broke_down` reads the shared `refine-broke-down`.
- `little_loops.cli.issues.check_readiness` (`--honor-waiver`, `outcome_gate_waived`),
  `show` (:147-158, :296), `deferred_triage` (`_REASON_RANK`), `set_status` (`DeferReason`)
  and `issue_lifecycle` (`OVERSIZED_ATOMIC`) consume `deferred_reason`; no code change.

### Tests

- `scripts/tests/test_builtin_loops.py::TestAutodevLoop`:
  - `test_required_states_exist` (~:6659), `test_old_states_removed` (~:6705) and
    `test_context_passthrough_on_refine_current` (~:8588);
  - the second-pass cluster (~:8095-8920): `test_recheck_after_size_review_*`,
    `test_check_guard2_*`, `test_go_no_go_escalation_chain_shape`,
    `test_check_go_no_go_eligible_one_shot_and_reason_scoped`,
    `test_reopen_waived_reopens_stages_and_rearms_inflight`, `test_enqueue_or_skip_*`,
    `test_pre_deferral_remedy_*`, `test_recheck_scores_on_*` (~:8890-8920);
  - wire/reconcile/design pins: `check_missing_artifacts` (~:9183-9209), `run_wire` /
    `run_refine` (~:9214-9238, :9519-9531), `rerun_confidence_after_wire` (~:9534-9590),
    `check_reconcile_needed` (~:8328, :8636-8660, :8839-8872, :9121-9165),
    `reconcile_current` / `count_repair_cycle_reconcile` (~:9145-9166),
    `dispatch_design_remedy` (~:8771-8793), `check_atomic_design_remedy` (~:8229);
  - `test_snap_and_size_review_*` (~:9437-9473; dropped by ENH-3611);
  - queue-adjacent: `test_enqueue_children_*` (~:8443-8716),
    `test_check_broke_down_on_no_routes_to_enqueue_or_skip` (:8510),
    `test_dequeue_next_clears_pre_deferral_remedy_files` (:8832),
    `test_dequeue_next_resets_contradiction_budget` (:8878);
  - `TestAutodevRnImplementDeferralParity` (~:9736; `AUTODEV_NOT_READY_STATES`).
- `scripts/tests/test_autodev_decision_gate.py`:
  - `TestReconcilePlateauStructural` / `Routing` (~:532-695),
    `TestDesignGateRefineRemedy` (~:698-770), `TestAtomicDesignRemedyRouting` (~:772-818),
    `TestGuard2VerdictBypass` (~:820);
  - `TestCheckDecisionBeforeSizeReviewStructural` (~:334) / `Routing` (:903), as they
    survive ENH-3610.
  - `_load_autodev_yaml` needs a `prepare-issue.yaml` twin.
- `scripts/tests/test_autodev_loop.py`: `TestCheckGuard2VerdictPattern` (:106),
  `TestCheckGuard2ScoreFallback` (:150), the `check_reconcile_needed` tests (~:190-300,
  :923-961), `TestRepairCycleCounterStates` (~:450-486), `TestRecheckAfterSizeReview*`
  (:497/:571/:715/:807), `TestPreDeferralRemedyContradictionExemption` (:850),
  `TestRegateAfterAtomicRemediationDesignGateBranch` (:917),
  `TestRecheckScoresDesignGateEndToEnd` (:1056), `TestDesignGateStep0Detection`,
  `TestDequeueNextPreReadinessSnapshot`, `TestCheckGateAtDequeueMarkerLiterals`.
- `scripts/tests/test_autodev_scores_freshness.py`:
  - `_PAIRS` (:28-31), with the `wire`/`reconcile`/`atomic` cases rewritten to the shared
    path;
  - `test_repair_predecessors_target_clear_states`, `test_readiness_readers_route_exit_3`,
    `test_check_passed_still_reaches_detect_children_on_error`;
  - `TestInlineGateAbsence` (:218-219), `test_dequeue_next_clears_retry_markers`;
  - the topology pins at :95-96.
- `scripts/tests/test_spike_verdict_routing.py`: `test_autodev_routing_table` (~:89-106),
  `test_dispatch_pre_deferral_remedy_*` (~:147) and the loop over
  `("autodev.yaml", "refine-to-ready-issue.yaml")` (~:136).
- `scripts/tests/test_ll_issues_check_gate.py` (~:268 docstring, ~:376),
  `test_go_no_go_skill.py:42` docstring, `test_recursive_finalize.py:133-140`,
  `test_auto_refine_closure_accounting.py`, and `TestAutoRefineAndImplementLoop` (~:4761,
  :4998-5620). These pin the queue/ledger files that stay autodev-owned.
- **Unaffected (name collision)**: `test_loops_recursive_refine.py`,
  `TestRecursiveRefineLoop` (~:9780-10170), `test_issue_refinement_broke_down.py`,
  `test_rn_refine.py`, `test_rn_implement.py`.

### Configuration

- No schema, config or manifest change. `run_record.py` already accepts the `prepare-issue`
  writer and the six `LEGACY_CLASSES`, and the `pyproject.toml` glob covers the YAML.

## Implementation Steps

1. Regenerate the boundary edge table against post-ENH-3611 `autodev.yaml` and record it
   here.
2. Pin the terminal table (the `TestOutcomeMapping` and CLI rows) and the `run_size_review`
   halt (`on_rate_limit_exhausted: mark_rate_limited`).
3. Build the wrapper ladder: the pass gate, the moved states with `${context.input}`
   rewrites, the shared rescoring path, the wrapper terminals, and `count_repair_cycle_refine`
   as the pre-state of the inner loop.
4. In the same commit: delete the moved states from autodev, set `check_passed.on_no` /
   `on_cannot_judge` → `skip_inflight`, and resolve `size_review_snap` / `check_broke_down`.
5. Relocate and rewrite the suites; add the absence, queue-writer, terminal-table, rescoring
   dispatch, counter and DECOMPOSED-guarantee tests; update the topology count and the
   baseline JSON.
6. Update the docs and comments; re-anchor the skills; run `ll-adapt` and re-check the line
   pins.

## Program Design

### Types

- `PreparationOutcome`: six-value Literal in `little_loops.run_record` (reused; the moved
  terminals use `ready`, `deferred`, `blocked`, `decomposed` and `retryable_error`)

### Signatures

- `write_run_record(run_dir: Path, record: RunRecord) -> Path` — reached through `ll-issues run-record write ... --writer prepare-issue` at each wrapper terminal
- `select_next_obligation(config: BRConfig, issue_id: str, *, skip: Iterable[Obligation] = (), ...) -> ObligationResult | None` — reached through the moved selector states (`ll-issues next-obligation`)

### Call Path

`autodev.yaml:refine_current` -> `prepare-issue.yaml:run_refine_to_ready` -> `prepare-issue.yaml:check_passed` -> `prepare-issue.yaml:select_obligation_post_refine` -> `prepare-issue.yaml:check_missing_artifacts`

`prepare-issue.yaml:run_size_review` -> `prepare-issue.yaml:recheck_after_size_review` -> `write_run_record` -> `autodev.yaml:route_refine_outcome` -> `autodev.yaml:ledger_child_stop`

## Status

**Open** | Created: 2026-09-26 | Priority: P3

## Session Log
- `/ll:wire-issue` - 2026-09-26T03:36:28 - `e6ad8ea2-14d6-441f-a607-435314c2d056.jsonl`
- `/ll:refine-issue` - 2026-09-26T03:22:25 - `7612ef86-47f8-4d5d-aa01-e50211538dc3.jsonl`
- `/ll:format-issue` - 2026-09-26T03:07:12 - `34887897-5e19-4ee2-b656-5f0a00c15f02.jsonl`

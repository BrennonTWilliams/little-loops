# Spike: preparation routing policy in Python (ENH-3621)

Branch `spike/preparation-policy` (not for `main`). Question: can autodev's second-pass
preparation ladder (39 states in `autodev.yaml`, plus `size_review_snap`,
`check_broke_down` and `mark_scores_absent_infra`) be a pure Python policy over the
issue file, config and an append-only per-issue fact log, driven by a ≤ 15-state
dispatch loop, with behavior parity against today and a correct resume?

## Verdict: PASS (all four criteria)

| Criterion | Result | Evidence |
|---|---|---|
| 1. Parity on every characterization scenario | **PASS** | 19/19 pinned scenarios match on skipped rows (order), queue, staged/passed/unverified, dequeue order, record tokens, status/`deferred_reason`, `summary.json`, slash sequence, repair-cycle counter, `ll-auto` calls and ledgers. 5 scenarios differ, every difference is enumerated and justified (below); 0 unexplained. 9 extra *differential* scenarios (today and policy run on the same input) match, 2 with justified record diffs. |
| 2. No autodev event enters a moved state | **PASS** | Every parity run asserts `path ∩ (39 moved + 3 deleted) = ∅`; the transform asserts no autodev edge targets a removed state. |
| 3. Crash + resume is exact | **PASS** | 232/232 crash points (6 scenarios × every runner call of every wrapper and inner action state × before/after) resume through `PersistentExecutor.resume()` to identical parity artifacts and identical counters, with exactly 0 replayed commands at 180 points and exactly 1 at the 52 points where a command ran but its done fact was not yet written. |
| 4. `decide()` table-tested; wrapper ≤ 15 states; no `rm -f` | **PASS** | 44 table tests over `decide()`; `prepare-issue-policy.yaml` has 15 states (13 non-terminal + `done`/`failed`) and no `rm` at all; `ll-loop validate` clean. |

FAIL conditions: no rule needed an implicit program counter beyond the last done fact
(the de-risk table below held without change); 0 unexplained diffs; no resumed run
diverged; the four hardest shapes (H1–H4) are at parity.

## What was built

- `scripts/little_loops/preparation_policy.py`
  - `StepKind` {RUN_CHILD, WIRE, REFINE_GAP, RESCORE, RECONCILE, SIZE_REVIEW, GO_NO_GO,
    FINISH, STOP}; frozen `Step(kind, seq, payload, reason, evidence, observations)`.
  - `decide(IssueSnapshot, Facts) -> Step` is pure. `next_preparation_step(config,
    issue_id, run_dir, *, readiness_threshold, outcome_threshold)` =
    `decide(snapshot_issue(...), load_facts(...))`. The snapshot reuses
    `select_next_obligation` (tier-1 skipped), `resolve_gate_verdict`,
    `check_format_gaps`/`design_gate_failed`, `readiness_status` semantics,
    `superseded_marker_count`, and `IssueParser.session_command_counts`.
  - Fact log `run_dir/prep-facts/<ID>.jsonl`, lines `{pass, seq, kind: intent|done|obs,
    step, payload}`, append-only, idempotent by `(pass, seq, kind)` (obs also by
    content). Pass id from `run_dir/prep-pass-<ID>`.
  - Writers, separate from decisions (`ll-issues prep …`, registered in
    `cli/issues/__init__.py`, so the harness fork server serves them):
    `prep step` (applied terminal → replay it; open intent → re-run its idempotent
    preconditions and replay; else decide → append obs → append intent → run
    preconditions → print the kind), `prep record [--guard2]` (done fact + the
    repair-cycle projection), `prep apply` (sole terminal writer: ledger row →
    set-status → run record → inflight clear, idempotent through its own done fact and
    `apply_progress` obs). `prep explain` prints a decision without writing.
- `scripts/little_loops/loops/prepare-issue-policy.yaml` — 15 states:
  `select_step` → {`run_child` (loop: refine-to-ready-issue), `run_wire`,
  `run_refine_gap`, `run_rescore`, `run_reconcile`, `run_size_review` →
  `classify_guard2` → `record_guard2`, `run_go_no_go`} → `record_step` → `select_step`;
  FINISH/STOP → `apply_outcome` → `done`/`failed`; `mark_rate_limited`;
  `max_steps: 80`, `on_max_steps: apply_outcome`; policy infra STOP at > 15 done facts
  per pass.
- Harness hookup (`scripts/tests/preparation_policy_harness.py`): the prototype is passed
  as `prepare_issue_yaml`; `policy_transform` applies ENH-3606's boundary retargets
  (`refine_current.on_success` → `copy_broke_down`; `check_passed` yes → proof gate,
  no/cannot_judge → `skip_inflight`, error → `skip_inflight_infra`;
  `detect_children` no/error → `check_parent_resolved`; `check_parent_resolved` no →
  `skip_inflight`, error → `skip_inflight_infra`), deletes the 39 + 3 states, drops
  `capture_reachability_ok`, and adds the `prep-pass-$CURRENT` increment to
  `dequeue_next`. `copy_broke_down` was left unshrunk (harmless; ENH-3606 shrinks it).
- Harness extensions (`scripts/tests/autodev_harness.py`): `faults` accept
  `"state#N"` (fault the N-th runner call in a state — needed because today's fault
  points no longer exist); `Crash.replay_same` (roll back the killed command's scripted
  response so the resumed replay gets the same result — models a deterministic
  replay); `AutodevResult.inner_calls` (executed inner runs, for replay counting).
- Tests: `test_preparation_policy.py` (44 `decide()` table tests),
  `test_preparation_policy_parity.py` (19 pinned + 9 differential + allowance sanity),
  `test_preparation_policy_resume.py` (6 count pins + 232 crash/resume points).

## Checkpoint → rule-order table (written before coding; unchanged by the build)

Model: the ladder is a pure function `decide(snapshot, facts) -> Step`. A *checkpoint*
is the last `done` fact of the current pass (kind + its `role` / `origin` / `attempt`
payload). Between two commands (inner run, slash command) the ladder runs only reads
and ledger/status writes, so every chain of today's shell/classify states between two
commands collapses into one `decide()` call. Rules below are evaluated top to bottom;
the first match wins. Aggregates are counted over the fact log, never over run_dir
handshake files.

| Checkpoint (last done fact) | Continuation |
|---|---|
| none in pass | `RUN_CHILD{role: first}` (precondition: clear both records) |
| `RUN_CHILD` | inner `failed` → STOP(child_stop); `error` → STOP(inner_error); token `CANCELLED` → FINISH(cancelled); `DECOMPOSED` → DETECT; else → GATE(check_passed, **no design**) |
| `WIRE{artifacts}` | `REFINE_GAP{post_wire}` |
| `REFINE_GAP{post_wire}` | `RESCORE{wire, 1}` (precondition: clear scores) |
| `RESCORE{o, n}` | scores absent: n=1 → `RESCORE{o, 2}`, n=2 → STOP(scores_absent); present: o=wire → POST_SIZE_REVIEW, o=reconcile → RASR, o=atomic → RAAR |
| `SIZE_REVIEW` | POST_SIZE_REVIEW |
| `RECONCILE` | `RESCORE{reconcile, 1}` |
| `WIRE{atomic}` | `RESCORE{atomic, 1}` |
| `REFINE_GAP{design}` | `RESCORE{reconcile, 1}` |
| `GO_NO_GO` | waiver stamped → PRE_IMPLEMENT (precondition: reopen); else STOP(oversized_atomic) |
| FINISH / STOP (applied) | the same terminal (idempotent re-apply after a restart) |

Chains inside one `decide()` (today's state names): GATE = `check_passed`; SPR =
`select_obligation_post_refine` → `check_missing_artifacts`; DETECT = `detect_children`
→ `check_parent_resolved` → `recheck_scores`; POST_SIZE_REVIEW = `enqueue_or_skip` →
`check_parent_resolved_post_size_review` → `select_obligation_post_size_review` →
`check_reconcile_needed` → `check_size_review_ran_this_pass` → `check_guard2_*` →
`check_readiness_for_atomic_remediation`; RASR = `recheck_after_size_review` →
`check_pre_deferral_remedy` → `dispatch_design_remedy` → `dispatch_pre_deferral_remedy`;
RAAR = `regate_after_atomic_remediation` → `check_atomic_design_remedy` →
`check_go_no_go_eligible`; PRE_IMPLEMENT = `select_obligation_pre_implement`.

Aggregates (replacing run_dir handshakes):

| Today (file) | Fact-log aggregate | Scope |
|---|---|---|
| `autodev-repair-cycle-count.txt` | done facts for RUN_CHILD(terminal done), WIRE{artifacts}, SIZE_REVIEW, RECONCILE, REFINE_GAP{design} (file kept as a projection) | pass |
| `autodev-rescore-origin-<ID>` | `origin` on the RESCORE step (carried from the done fact before it) | step |
| `autodev-rescore-retry-<o>-<ID>` | `attempt` on the RESCORE step | step |
| `autodev-reentry-{DECISION,PROOF}-<ID>` | a RUN_CHILD **intent** with role decision / proof exists | pass |
| `autodev-pre-deferral-remedy{.txt,-fired}` | an intent with `pre_deferral: true` exists (the armed token is consumed in the same `decide()`) | pass |
| `autodev-atomic-design-remedy-pending` | none (consumed in the same `decide()`) | — |
| `autodev-contradiction-reconcile-{armed,count}` | RECONCILE intents with `contradiction_only: true` | pass |
| `autodev-contradiction-reconcile-<ID>` | any such intent | run |
| `autodev-design-remedy-attempted-<ID>` | any REFINE_GAP{design} intent | run |
| `autodev-go-no-go-attempted-<ID>` | any GO_NO_GO intent | run |
| `autodev-design-gate-failed-<ID>` | `obs design_gate_failed` (sticky, BUG-3620 parity) | run |
| `autodev-size-review-ran-this-pass` + `captured.size_review_output` | the last SIZE_REVIEW done fact in the pass, with `guard2` on it | pass |
| `autodev-pre-readiness.txt` (+ backfills) | `obs pass_start.pre_readiness`, then the latest `obs pre_readiness` | pass |
| `autodev-pre-ids.txt` (+ `size_review_snap` refresh) | `obs pass_start.pre_ids`; no refresh needed (provenance-filtered diff, see below) | pass |

The `size_review_snap` baseline refresh is redundant under provenance filtering: a
child with `parent: <ID>` created before the refresh is found by `detect_children`
itself, so the size-review diff against the dequeue baseline returns the same set.

### The four hardest scenarios

**H1 — guard-2 across epochs.** Epoch 1: `RUN_CHILD` → GATE fail → SPR → DETECT → RS
fail → `SIZE_REVIEW` (guard2=true) → … → RASR arms the spike remedy →
`RUN_CHILD{spike_remedy}` (epoch 2) → GATE fail → SPR → ARTIFACTS →
`WIRE{artifacts}` → `REFINE_GAP` → `RESCORE{wire}` → POST_SIZE_REVIEW → CRN no → GUARD2.

| Rule order at GUARD2 | Fact read |
|---|---|
| 1. a SIZE_REVIEW done fact exists in this pass (today: ran-this-pass marker) | pass aggregate |
| 2. its **last** occurrence has guard2 (today: latest capture, run-scoped) | last SIZE_REVIEW done |
| 3. readiness ≥ threshold (CRAR) → `WIRE{atomic}`; else RASR | snapshot |

A later size review in the pass (guard2=false) replaces it, as today's capture
overwrite does. Verified by `h1_guard2_across_epochs{,_go}` (differential) and
`test_h1_guard2_reads_the_last_size_review_of_the_pass`.

**H2 — first gate skips check-design; later gates run it.**

| Checkpoint | Gate rule | Design obs recorded? |
|---|---|---|
| `RUN_CHILD` (GATE = check_passed) | readiness+outcome (waiver) | no |
| DETECT → RS (same `decide()` call) | readiness+outcome (waiver) AND design | yes, on fail |
| RASR / RAAR | inline gate AND design; then the sticky-marker branches | yes, on fail |

Verified by `h2_first_gate_skips_design` (differential), `design_gate_failed` (pinned),
`test_h2_first_gate_ignores_design_and_files_no_marker`.

**H3 — DECISION / PROOF re-entry returns to post-refine.** Any `RUN_CHILD` done fact,
whatever its role, continues at GATE. Budgets are intent aggregates per pass, plus the
lifetime `refine_count < max_refine_count` term. Verified by
`decision_reentry_exhausted` (pinned), `h3_proof_reentry_then_ready`,
`h3_decision_reentry_resolves` (differential), and the budget table tests.

**H4 — go/no-go requires the prior oversized_atomic deferral, then reopen.**

| Step | Rule / writer |
|---|---|
| RAAR (after `RESCORE{atomic}`) | gate pass → PRE_IMPLEMENT; resolved → FINISH(decomposed); absent → STOP(scores_absent); design marker → `REFINE_GAP{design}` if no design intent in the run, else STOP(design_gate_failed); else oversized_atomic: GO_NO_GO intent in the run → STOP(oversized_atomic), else `GO_NO_GO` |
| `GO_NO_GO` intent | **precondition** written by `prep step` (idempotent): `set-status deferred --reason oversized_atomic`, because the skill keys its waiver on that frontmatter |
| after `GO_NO_GO` | waived → PRE_IMPLEMENT with precondition `reopen`; readiness below threshold → STOP(low_readiness) (ENH-3606 accepted change 4); not waived → STOP(oversized_atomic) |

Today the `oversized_atomic` row is written before go/no-go and removed by
`reopen_waived`; the policy writes rows only in `apply`, so the GO path never writes
it: same net ledger. Verified by `oversized_atomic_no_go` / `_go_reopen_implement`
(pinned) and `h1_guard2_across_epochs_go` (differential).

**Conclusion of the de-risk step (held through the build):** no rule needs an implicit
program counter. The last done fact carries a small explicit return address
(`role` / `origin` / `attempt`) — exactly the data the handshake files carried. Four
side effects must happen *before* a command, so they are step preconditions rather
than apply writes: clear records (RUN_CHILD), clear scores (first RESCORE), defer
oversized_atomic (GO_NO_GO) and reopen (the step after a GO).

## Per-scenario parity (criterion 1)

`test_preparation_policy_parity.py::test_policy_parity` compares 15 parity fields
against the ENH-3618 pins. Autodev's *path* necessarily changes (ladder states are
gone) and is checked only for moved-state absence.

| Scenario (pinned) | Result | Diffs vs today's pin (all justified) |
|---|---|---|
| ready_implement_closed | parity | — |
| design_gate_failed | parity | — |
| oversized_atomic_no_go | parity | — |
| oversized_atomic_go_reopen_implement | parity + 1 | record `MISSING` → `READY`: BUG-LIKE pin fixed per ENH-3606 terminal table (`mark_ready`) |
| readiness_stagnated | parity | — |
| low_readiness | parity | — |
| decision_unresolved_at_recheck | parity | — (the pinned `summary` bucket quirk is autodev_summary's, unchanged) |
| decision_reentry_exhausted | parity | — |
| size_review_decomposition | parity + 1 | parent record `BLOCKED` → `DECOMPOSED`: BUG-LIKE pin fixed per the terminal table (size-review decomposition → decomposed + child_ids). Queue, `decomposed` row, `finalize-decomposition` and new-children ledger are identical — autodev's `enqueue_children` now does the enqueue |
| resolved_parent_at_recheck | parity + 1 | record `BLOCKED` → `DECOMPOSED`: ENH-3606 `route_ladder_stop` (resolved → mark_decomposed); `recover_subloop_children` writes the same `resolved_by_subloop` row |
| inner_decomposed_parent_resolved | parity | — |
| scores_absent_after_repair | parity + 3 | `refine_failed_infra` row, record `RETRYABLE_ERROR:infra`, no `autodev-scores-absent.txt`: ENH-3606 accepted change 1 and the decided deletion of `mark_scores_absent_infra` (the known allowed diff). `summary.json` unchanged (the infra bucket is not a `skipped` count) |
| on_error_drop | parity + 5 | fault remapped (`enqueue_or_skip` no longer exists → 3rd `select_step` exits 2, the same decision point). `refine_failed_infra` row, record infra, no `inflight_at_finalize`, verdict `no-op` not `phantom`, final `done` not `failed`: ENH-3606 accepted change 1 (`on_error` drops become one `refine_failed_infra` row), which also fixes the pinned BUG-LIKE phantom |
| ladder_rate_limit_is_inert | parity | — (the rate-limit smoke: slash states stay `next:`-shaped, BUG-3622 parity) |
| inner_decomposed | parity | — |
| inner_cancelled | parity | — |
| inner_stop_gate_unmet | parity | — |
| inner_error | parity | — |
| inner_rate_limited | parity | — |

`test_allowed_diffs_are_real_diffs` fails if any allowance equals the pin (no vacuous
allowances).

Differential scenarios (`test_policy_matches_today_differential`: today and the policy
run on the same scenario; each also asserts the slash/inner-run shape it names, so a
scenario cannot pass vacuously):

| Scenario | Shape exercised | Result |
|---|---|---|
| h1_guard2_across_epochs | H1: epoch-1 guard-2 read in epoch 2 after spike re-entry + wire rescore → NO-GO | parity |
| h1_guard2_across_epochs_go | H1 + H4 GO → reopen → implement | parity + record `READY` (as above) |
| h2_first_gate_skips_design | H2: scores pass, design gate armed and failing → implemented | parity |
| h3_proof_reentry_then_ready | H3 PROOF re-entry at SPR | parity |
| h3_decision_reentry_resolves | H3 DECISION re-entry at SPR | parity |
| pre_deferral_reconcile_remedy | fresh_below reconcile + pre-readiness backfill, armed reconcile remedy, low_readiness | parity |
| rescore_retry_recovers | scores-presence retry, then RASR pass → implemented | parity + record `READY` (today keeps the forwarded inner `BLOCKED` on an implemented issue — BUG-LIKE) |
| contradiction_reconcile | contradiction-only reconcile, then readiness_stagnated | parity |
| contradiction_masked_by_format_gaps | quirk Q1 (below): same marker, blocking format gaps → no reconcile | parity |

## Resume matrix (criterion 3)

`test_preparation_policy_resume.py`. Each point kills the process (`HarnessCrash`, a
`BaseException`) at the N-th runner call of a state, *before* the action runs or
*after* it ran but before its result returned, then resumes with a fresh
`PersistentExecutor(...).resume()`. Autodev has `refine_current` persisted while the
wrapper runs, so every resume restarts the wrapper at `select_step` — the case that
breaks ENH-3606's graph move. Each point is compared with an uncrashed run of the same
scenario on all 15 parity fields plus the fact-derived repair-cycle count. Crash points
are pinned by `test_matrix_counts_match_clean_run` (6 more tests). Result: **238
passed** (19 min at `-n 4`).

| Scenario | Points | 0 replays expected & observed | exactly 1 replay expected & observed | Artifacts / counters |
|---|---|---|---|---|
| readiness_stagnated | 30 | 22 | 8 | identical |
| oversized_atomic_go_reopen_implement | 36 | 26 | 10 | identical |
| design_gate_failed | 42 | 30 | 12 | identical |
| decision_reentry_exhausted | 20 | 16 | 4 | identical |
| size_review_decomposition (3 issues) | 42 | 34 | 8 | identical |
| h1_guard2_across_epochs_go (H1+H4) | 62 | 44 | 18 | identical |
| **Total** | **232** | **180** | **52** | **232/232** |

By crash point (all scenarios):

| Crash point | Replayed commands | Why |
|---|---|---|
| `select_step` before / after | 0 | after: intent + preconditions written; resume replays the intent (preconditions are idempotent) |
| `resolve_issue` (inner) before / after | 0 | the inner run restarts; its command had not run |
| command state (`scripted_run`, `run_*`) before | 0 | command never ran |
| command state after | 1 | command ran, no done fact → the open intent replays it once |
| `record_step` / `record_guard2` before | 1 | same: the command's done fact is not yet written |
| `record_step` / `record_guard2` after | 0 | done fact written; resume decides the next step |
| `apply_outcome` before / after | 0 | after: the applied terminal is in the log; `prep step` returns it and `apply` is idempotent |

Comparison with today (the ENH-3618 resume characterization): a kill after
`count_repair_cycle_reconcile` double-counts the repair-cycle counter (4 instead of 3),
and a kill inside the inner loop re-runs the whole wrapper. Under the policy the counter
is derived from done facts (never double-counted) and a restart replays at most the one
unrecorded command.

Harness note: a replayed command gets the *same* scripted response
(`Crash.replay_same`), i.e. the matrix assumes a replayed command has the same effect
as the killed one. Real LLM replays are not deterministic; the guarantee proven here is
"≤ 1 replay and no double-applied bookkeeping", not "the replay decides the same way".

## Quirks and bugs found

- **Q1 (new, bug candidate): the ENH-2992 contradiction trigger is dead on any issue with
  a blocking format gap.** `check_reconcile_needed` runs
  `FMT_JSON=$(ll-issues format-check "$ID" --format json 2>/dev/null || echo '{}')`.
  `format-check --format json` prints the JSON *and* exits 1 when
  `gaps.has_blocking_gaps`, so `FMT_JSON` becomes `"<json>\n{}"`, `json.loads` raises,
  and `markers = 0`. Reproduced by `contradiction_masked_by_format_gaps` (today's
  ladder never reconciles an issue missing `## Impact`/`## Status` even with a
  `⚠ Superseded` marker). The policy keeps parity (`markers = 0 if has_blocking_gaps`)
  and flags it in `snapshot_issue`. Capture as its own BUG.
- **BUG-3620 confirmed and kept.** The design-gate-failed marker is run-scoped and never
  cleared; RASR/RAAR branch on it after the current check-design passes, including in a
  later pass of the same issue (`test_design_marker_is_sticky_across_passes_bug3620_parity`).
  In the policy the fix is one line (`_Decider.design_marker()` returns the current
  verdict).
- **Q3: first-gate asymmetry.** `check_passed` does not consult check-design; RS, RASR
  and RAAR hard-AND it. An issue whose scores pass after the inner loop is implemented
  even when the Program Design gate fails (`h2_first_gate_skips_design`). Probably
  intended (the inner loop owns the tier-1 DESIGN gate), but it should be a stated rule.
- **Today's resume** re-runs the whole wrapper and double-counts the repair-cycle
  counter (pinned `after_counter_increment_double_counts`). The fact log fixes both.
- **`record_reentry_exhausted` writes its `decision_unresolved` row before the status
  check** (known in ENH-3606). The policy follows ENH-3606: a resolved issue at any
  deferral stop ends DECOMPOSED and autodev's `recover_subloop_children` owns the row
  (edge case; no characterization scenario reaches it).
- **Sub-loop terminal type has no stable capture.** `record_step` learns
  done/failed/error from `${captured.run_child.terminated_by}` /
  `${captured.run_child.failure_terminal}`. The executor merges child captures into
  `captured.run_child` only when the child captured something, so a child with no
  captures would leave a stale `failure_terminal` from an earlier child run in the same
  wrapper execution. Real `refine-to-ready-issue` always captures; production should
  get a stable executor-provided capture (or use three record states, which costs 2
  states of the 15).
- **Re-deferral re-stamps `deferred_date`**: the GO_NO_GO precondition defers the issue
  before the skill runs (as today); a NO-GO then `apply`s `set-status deferred` again.
  Cosmetic.
- Rate limits: BUG-3622 still makes every `next:`-shaped slash state inert to 429s;
  `mark_rate_limited` is wired but unreachable, exactly like today
  (`ladder_rate_limit_is_inert` at parity).

## LOC

| Artifact | Lines (total / non-comment, non-blank) |
|---|---|
| Today: the 39 moved states in `autodev.yaml` | 1,461 / 879 |
| Today: `size_review_snap` + `check_broke_down` + `mark_scores_absent_infra` | 59 / 34 |
| Today: routing state in ~15 run_dir handshake files | (implicit) |
| ENH-3606 plan: `prepare-issue.yaml` after the move | ~55 states (7 + 39 + 9) |
| Policy module `preparation_policy.py` | 1,280 total: types + `Facts`/`IssueSnapshot` ~257, `decide()` ~383, `snapshot_issue` ~131, fact I/O + writers ~414, CLI ~95 |
| Dispatch loop `prepare-issue-policy.yaml` | 182 / 150, **15 states** |
| Spike tests | table 467, parity 372, resume 214, harness glue 130; harness extensions +29 |

The policy is not smaller in raw lines than the YAML it replaces; the win is that the
routing is ordinary, table-testable Python (44 table tests run in 0.1 s) and the loop
has 15 states with no handshake files.

## Open risks

- **Coverage-bounded parity.** The policy re-implements ~25 inline shell/Python
  predicates (string compare of pre/cur readiness, `int(x or 0)` coercions, the remedy
  heuristic, the BUG-3614 cap). 28 end-to-end scenarios + 44 table tests cover the
  terminal table and H1–H4, but not every branch combination (contradiction-sourced
  spike exemption, spike-budget-exhausted reconcile fallback, refine-cap on DPDR,
  `_error` routes of the selectors). A production issue should port the relevant
  existing shell-level tests to table tests before deleting the YAML.
- **Per-pass cap is below the legal worst case.** `MAX_DONE_PER_PASS = 15` (the plan's
  number) held for every scenario (max observed ≈ 10), but the ladder's own budgets
  allow more (≤ 4 inner epochs, each with wire/rescore/size-review/reconcile legs, plus
  atomic and design remedies). Derive the bound like ENH-3606's step arithmetic and set
  `max_steps ≈ 3 × cap + 3`.
- **Snapshot cost.** Each `select_step` scans every active issue for child provenance and
  runs `next-obligation`, format-gap and gate probes. Make the snapshot lazy (children
  only in DETECT / POST_SIZE_REVIEW).
- **Record writing is duplicated.** `apply` writes the `prepare-issue` record in-process
  with the same `outcome_from_legacy_class` + `readiness_status` logic as
  `ll-issues run-record write`; share one helper.
- **Crash granularity.** The harness kills only at runner-call boundaries. A kill inside
  `prep apply` between the row append and its `apply_progress` obs could still
  double-append the row; make the row append + progress one atomic write (or key rows
  by `(pass, seq)` in a side file) in production.
- **Handoff** (`on_handoff: spawn`) restarts from the same persisted state as resume, so
  it inherits the resume result, but no handoff-specific test was run.
- Standalone use of the wrapper outside autodev has no `dequeue_next`, so the pass id
  stays `"0"` for the whole run_dir; fine while run_dirs are per run instance.

## Recommendation vs ENH-3606

Replace ENH-3606 with a new ENH, "prepare-issue as a policy dispatch loop", that
`supersedes: [ENH-3606]` and carries over its still-valid decisions (terminal table,
ledger ownership, DECOMPOSED guarantee, queue ownership, accepted behavior changes,
boundary retargets, the three deletions). Drop the graph-relocation mechanics
(the 55-state wrapper, `route_inner_success`, `detect_ladder_children`,
`route_ladder_stop`, `mark_*` terminals, the 250-step arithmetic, the
`count_repair_cycle_refine` → `clear_record` entry chain): each becomes a rule, a
precondition, or an `apply` outcome.

The production issue needs to add:

1. `little_loops.preparation_policy` split into policy (pure), facts, and writers;
   shared record-writing helper with `run-record write`; lazy snapshot; derived per-pass
   cap and `max_steps`.
2. `ll-issues prep {step,record,apply,explain}` with `docs/reference/CLI.md` and
   `docs/reference/API.md` entries; `docs/guides/LOOPS_REFERENCE.md` (autodev tree,
   prepare-issue section, accepted behavior changes); `docs/ARCHITECTURE.md` (fact log).
3. `prepare-issue.yaml` replaced in place by the 15-state dispatch loop; autodev edits
   = ENH-3606's boundary retargets + 42 deletions + the `dequeue_next` pass-id write
   (+ shrink `copy_broke_down`).
4. Test migration: ENH-3606's "Relocate or rewrite" inventory (TestAutodevLoop
   second-pass cluster, `test_autodev_decision_gate.py`, `test_autodev_loop.py`,
   `test_autodev_scores_freshness.py`, `test_spike_verdict_routing.py`, baselines and
   topology pins) becomes `decide()` table tests plus wrapper-structure tests; promote
   the spike's parity and differential tests and a representative subset of the resume
   matrix (the full matrix is ~240 runs, ~35 min at `-n 4`; keep it opt-in/slow).
5. Decisions to take with it: Q1 (fix the format-check masking or keep parity),
   BUG-3620 (one-line fix in the policy), Q3 (first-gate design rule), the
   run-terminal capture for `record_step`.
6. **BUG-3622 dependency**: the rate-limit rows stay unreachable until BUG-3622 lands;
   with the dispatch loop the fix touches 6 slash states (or the executor), and
   `mark_rate_limited` is already wired.
7. Re-point ENH-3600 and ENH-3590 `blocked_by` to the new issue; ENH-3600's
   `refine-terminal-class` MISSING-fallback removal is simpler because every wrapper
   exit now goes through `apply`.

## Post-spike notes (main)

Added when the report was copied to `main` (2026-09-26). The spike code is **not merged**;
it lives on branch `spike/preparation-policy` (head `a51621302`). Two findings above no
longer describe `main`:

- **BUG-3622 is fixed** (commit `ce86ce662`). The executor now applies 429 handling to
  states routed by `next:`, and rate-limit retries no longer count toward the throttle.
  The "rate-limit rows unreachable / BUG-3622 parity" notes (parity row
  `ladder_rate_limit_is_inert`, Quirks "Rate limits", recommendation item 6) are stale:
  the production policy's `mark_rate_limited` path is reachable and must be live and
  tested, and rate-limit exhaustion must halt autodev through `finalize_rate_limited`.
- **BUG-3620 is fixed.** The sticky `autodev-design-gate-failed-<ID>` marker is retired;
  the design branches of `recheck_after_size_review` and `regate_after_atomic_remediation`
  read the current check-design verdict. The "BUG-3620 sticky-marker parity" rule
  (aggregates table row `obs design_gate_failed`, Quirks "BUG-3620 confirmed and kept",
  `test_design_marker_is_sticky_across_passes_bug3620_parity`) is stale: the production
  policy must implement the current-verdict design rule (the "one-line fix" in
  `_Decider.design_marker()`), and the parity tests must pin the fixed behavior.

Follow-ups captured from this report: ENH-3623 "prepare-issue as a policy dispatch loop"
(supersedes ENH-3606), BUG-3624 for Q1 (format-check exit code masks the contradiction
trigger), and ENH-3625 for Q3 (state the first-gate Program Design rule).

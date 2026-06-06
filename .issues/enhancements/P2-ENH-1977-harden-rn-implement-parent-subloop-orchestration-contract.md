---
id: ENH-1977
title: "Harden rn-implement parent↔sub-loop orchestration contract (rate-limit laundering, terminal vocabulary, threshold consistency, resume, decomposed-parent lifecycle + EPIC re-linking)"
type: ENH
priority: P2
status: open
captured_at: '2026-06-06T00:00:00Z'
discovered_date: '2026-06-06'
discovered_by: audit-loop-run
relates_to:
- BUG-1972
- BUG-1973
- BUG-1974
- BUG-1975
- BUG-1976
- BUG-1096
- ENH-1340
- ENH-1936
labels:
- rn-implement
- rn-remediate
- rn-decompose
- loop-defect
- orchestration
- epics
---

# ENH-1977: Harden the rn-implement parent↔sub-loop orchestration contract

## Summary

A structural review of the `rn-implement` orchestrator (parent) against its delegated sub-loops
(`rn-remediate`, `rn-decompose`) and the FSM runner's loop-delegation semantics revealed seven gaps
(A–G) in the **parent↔sub-loop verdict contract**. These are distinct from the within-state defects
already filed (BUG-1973…1976); they concern how outcomes flow *across* the loop boundary.

The root cause for several gaps is the runner's loop-delegation mapping. In
`scripts/little_loops/fsm/executor.py:598-612`, a `loop:` state resolves a child to **exactly three
verdicts**:

- child `final_state == "done"` → parent `on_yes`
- child reaches any *other* terminal (e.g. `failed`) → parent `on_no`
- child `terminated_by == "error"` → parent `on_error`

There is no mechanism to propagate a child's rate-limit (or any richer) terminal to the parent. Every
sub-loop outcome is therefore squeezed into yes/no/error, which silently breaks rate-limit handling,
conflates decomposition-vs-failure, and routes implement crashes into decomposition.

This issue captures a **single coordinated fix** for all seven gaps. They are bundled because A, B,
and C share one structural remedy (a sub-loop outcome-classification channel) and the others touch the
same three loop files; splitting them would cause repeated churn over `rn-implement.yaml`,
`rn-remediate.yaml`, and `rn-decompose.yaml`.

## Coordination with BUG-1974 / BUG-1975 / BUG-1976

These three within-state bugs came from the same audit (run `2026-06-06T015949`). Their relationship
to this ENH is **not uniform** — two are absorbed here, one ships standalone:

- **BUG-1975 (missing `on_partial` on `run_size_review`) — folded into this issue.** Fix 1 requires
  `run_size_review`'s partial/error paths to emit a `SIZE_REVIEW_FAILED` token, but a `partial` verdict
  currently falls through to `_finish("error")` *before any token-write state can run*. So Fix 1 is not
  implementable without first adding BUG-1975's `on_partial` route — it is a prerequisite sub-task, not
  a parallel fix. **Decision on semantics:** adopt BUG-1975's routing (`on_partial → detect_children`,
  "review ran with a caveat, proceed and log it"), **not** a blanket `SIZE_REVIEW_FAILED`. In the
  observed run the `partial` was caused by staged unrelated changes (BUG-1976's root cause), i.e. the
  review *succeeded* with a hygiene caveat — not a review failure. `SIZE_REVIEW_FAILED` is reserved for
  genuine review errors (`on_error`).

- **BUG-1974 (`detect_children` no-children → `failed` terminal) — partially absorbed.** Fix 1's token
  channel makes the *parent-level* consequence moot (the parent classifies on the `NO_CHILDREN` token,
  not on the child's done/failed terminal). But BUG-1974's literal complaint is the *sub-loop's own*
  `final_state: failed` polluting event-history/telemetry — so the no-children terminal **must still be
  flipped `on_no: failed → done`** (writing the `NO_CHILDREN` token, then terminating in a success
  state) as part of Fix 1/Fix 4's `detect_children` rewrite. Carry this telemetry flip explicitly so it
  is not dropped.

- **BUG-1976 (`issue-size-review` over-broad `git add .issues/`) — NOT superseded; ship standalone.**
  Fix 4 edits `issue-size-review/SKILL.md` only to emit the `Decomposed from <parent>` marker; it never
  touches the blanket-stage line. The staging bug is orthogonal (same file, different line, different
  behavior) and should be fixed independently of this ENH.

`detect_children` is the shared conflict zone (BUG-1974's terminal flip + Fix 4's body-marker match
rewrite both land there). Do **not** implement this ENH in parallel (`ll-parallel`) with BUG-1974;
serialize them or fold 1974 in here.

## Gaps

### GAP A — [HIGH] Rate-limit exhaustion is laundered into success
Both sub-loops route their `rate_limit_diagnostic` state to `done` (`rn-remediate.yaml:418`,
`rn-decompose.yaml:220`). Because `done` → `on_yes`, the parent's `run_remediation` /
`run_decomposition` treat a rate-limited issue **identically to a fully implemented/decomposed one**
and advance via `dequeue_next`. Consequences:
- The parent's `on_rate_limit_exhausted:` routes (`rn-implement.yaml:153`, `:166`) are **unreachable
  dead code** — a `loop:` child can never yield a rate-limit verdict.
- Rate-limited issues are silently dropped: counted as processed-success, absent from `summary.json`
  (which has no rate-limit field), only buried in `rate_limits.txt`. Under a sustained 429 storm the
  loop reports success while implementing nothing.

### GAP B — [MEDIUM] Sub-loop terminal vocabulary is too coarse
`rn-remediate` funnels ~6 distinct outcomes into one `failed` terminal: scores-missing, refine error,
implement crash, remediation-budget exhausted, convergence STALLED, and the legitimate "needs
DECOMPOSE" signal. The parent maps *every* `failed` → `run_decomposition`, so it cannot distinguish
"this issue is too big, split it" from "the run crashed" from "frontmatter was malformed."

### GAP C — [MEDIUM] Implement-failure routes to decomposition (instance of B)
`rn-remediate.yaml:242-243`: `implement` `on_no`/`on_error` → `failed` → parent → `run_decomposition`.
An issue that *passed readiness* but failed `ll-auto` (tests broke, runtime error) is sent to a
size-review/decomposition that cannot fix it; if no children are found it is downgraded to
`skip_issue`. Genuine implementation failures never reach the summary's `failed` count.

### GAP D — [LOW/MED] check_readiness ignores the loop's thresholds
`rn-remediate.yaml:101-104` calls `ll-issues check-readiness "$ID"` with no `--readiness` /
`--outcome` flags (both flags exist), so it uses **ll-config defaults**, while `diagnose` and
`check_convergence` use the loop-context thresholds (85/75). Overriding thresholds via loop params
makes the readiness gate silently disagree with the dimensional router.

### GAP E — [MEDIUM] Checkpoint is written but can never be resumed
`failed` writes `checkpoint.json` with queue/visited/depth_map paths (`rn-implement.yaml:239-240`),
but `init` (`rn-implement.yaml:50`) always re-seeds `queue.txt` from `input` and wipes it. There is no
resume entry point, so an 8h / 500-iteration recursive run that dies must restart from scratch — the
checkpoint is misleading dead weight.

### GAP F — [MEDIUM] Decomposed-parent lifecycle is never closed, and EPIC membership is lost
When `rn-decompose` splits a parent, it appends the parent to `skipped.txt` and increments
`decomposed_count` (`rn-decompose.yaml:197-202`) but **never updates the parent issue's status** and
never moves it out of the active backlog (the same defect class as BUG-1096 / ENH-1340 in
`recursive-refine`). Worse: if the decomposed parent was a member of an EPIC (i.e. it carries
`parent: EPIC-NNN`), the newly created children inherit no EPIC association, so they silently fall out
of the EPIC's scope, `relates_to:` list, `## Children` section, and `ll-issues epic-progress` rollup.

### GAP G — [LOW] missing_artifacts is parsed but never routed
`diagnose` extracts `missing_artifacts` (`rn-remediate.yaml:163`) but the routing matrix
(`rn-remediate.yaml:171-183`) never uses it. Dimensional reactivity is incomplete — an issue missing
integration artifacts is not steered to `wire`.

## Proposed Solution

### Fix 1 — Sub-loop outcome-classification channel (resolves A, B, C)

Avoid an FSM-engine change. Use the existing shared `run_dir` coupling: each sub-loop writes a single
outcome token to `${run_dir}/subloop_outcome_<id>.txt` on every terminal path, and the parent adds a
classifier state after each `loop:` delegation that reads the token and routes deterministically.

**rn-remediate** writes one of: `IMPLEMENTED`, `NEEDS_DECOMPOSE`, `IMPLEMENT_FAILED`,
`SCORES_MISSING`, `RATE_LIMITED`.
- `implement` success → `IMPLEMENTED`
- `route_d_refine` no-match / `route_conv_improved` no-match (STALLED) / `check_remediation_budget`
  exhausted → `NEEDS_DECOMPOSE`
- `implement` failure/error → `IMPLEMENT_FAILED`
- `verify_scores_persisted` / `verify_re_assess_scores` failure → `SCORES_MISSING`
- `rate_limit_diagnostic` → `RATE_LIMITED` (and **route to `failed`, not `done`** — see below)

**rn-decompose** writes one of: `DECOMPOSED`, `NO_CHILDREN`, `SIZE_REVIEW_FAILED`, `RATE_LIMITED`.

Both sub-loops keep `done`/`failed` terminals, but `rate_limit_diagnostic` must route to a non-`done`
terminal so the parent does not read success. The parent then classifies on the token rather than on
the bare done/failed verdict:

```yaml
  run_remediation:
    loop: rn-remediate
    with: { issue_id: "${captured.input.output}", run_dir: "${captured.run_dir.output}", ... }
    on_yes: classify_remediation      # IMPLEMENTED path still reaches here
    on_no: classify_remediation       # failed/non-done also classified, not blindly decomposed
    on_error: classify_remediation

  classify_remediation:
    action_type: shell
    action: |
      cat "${captured.run_dir.output}/subloop_outcome_${captured.input.output}.txt" 2>/dev/null \
        || echo "IMPLEMENT_FAILED"
    capture: rem_outcome
    next: route_rem_implemented
  # chained output_contains routers:
  #   IMPLEMENTED      -> dequeue_next
  #   NEEDS_DECOMPOSE  -> run_decomposition
  #   RATE_LIMITED     -> rate_limit_diagnostic
  #   IMPLEMENT_FAILED -> record_failure   (new state: append to failures.txt, then dequeue_next)
  #   SCORES_MISSING   -> record_failure
```

`record_failure` appends to `failures.txt` and dequeues — implement crashes and malformed-score
issues are now counted as failures (fixes C and the summary undercount), and only genuine
`NEEDS_DECOMPOSE` outcomes reach decomposition (fixes B). `RATE_LIMITED` reaches the parent's
real rate-limit diagnostic (fixes A); the previously-dead `on_rate_limit_exhausted` routes can be
removed.

Add the same classifier (`classify_decomposition`) after `run_decomposition`:
`DECOMPOSED`/`NO_CHILDREN` → `dequeue_next` (NO_CHILDREN via `skip_issue`), `RATE_LIMITED` →
`rate_limit_diagnostic`, `SIZE_REVIEW_FAILED` → `record_failure`.

Extend `report`/`summary.json` with `rate_limited` and `failed` counts derived from
`rate_limits.txt` and `failures.txt`.

### Fix 2 — Threshold consistency (resolves D)

Pass the loop-context thresholds to `check-readiness`:

```yaml
  check_readiness:
    action: |
      ID="${context.issue_id}"
      ll-issues check-readiness "$ID" \
        --readiness "${context.readiness_threshold}" \
        --outcome "${context.outcome_threshold}"
```

### Fix 3 — Resume support (resolves E)

Add a resume entry. `init` accepts an optional `resume: true` context flag (or detects an existing
non-empty `${run_dir}/queue.txt`): when resuming, skip the queue re-seed and the tracking-file
truncation, preserving `queue.txt`, `visited.txt`, `depth_map.txt`, and counters. Document
`ll-loop run rn-implement --resume <run_dir>` (or equivalent). If resume is out of scope, instead
**remove** the misleading `checkpoint.json` write so it does not imply a capability that does not
exist.

### Fix 4 — Decomposed-parent lifecycle + EPIC re-linking (resolves F)

After `enqueue_children` succeeds, run a new `finalize_parent` state in `rn-decompose` that:

1. **Closes the parent.** Set the decomposed parent's status to `done` (work is now carried by the
   children) via `ll-issues set-status <parent> done`, append a body note
   "Decomposed into <child-ids>", and move it to the type-based completed directory (mirroring the
   BUG-1096 fix for `recursive-refine`).

2. **Re-links children to the parent's EPIC, if any.** Read the decomposed parent's `parent:` field.
   If it matches `EPIC-NNN`:
   - Resolve the field collision: `parent:` is canonically used for **both** decomposition lineage
     and EPIC membership (`link-epics/SKILL.md`, `list_cmd.py:146`). A child cannot carry two
     `parent:` values. **Decision:** make children first-class EPIC members — set each child's
     `parent: EPIC-NNN`, and record decomposition lineage in `relates_to: [<parent-id>]` plus a
     `Decomposed from <parent-id>` body marker. This keeps `ll-issues list --group-by epic`,
     `epic-progress`, and `link-epics` working unchanged.
   - Because detection currently keys on `parent:.*<parent-id>` (`rn-decompose.yaml:110-111`),
     **switch `detect_children` to match on the `Decomposed from <parent-id>` body marker** (already
     a fallback at `:111`) or on the size-review child manifest, so detection survives the `parent:`
     repoint to the EPIC. Have `issue-size-review` emit the marker reliably when it creates children.
   - Update the EPIC: append each child to the EPIC's `relates_to:` list and `## Children` section,
     and remove/mark the decomposed parent there.

   If the decomposed parent has no EPIC (`parent:` empty or non-EPIC), only step 1 applies and
   children keep `parent: <parent-id>` as today.

### Fix 5 — Route missing_artifacts (resolves G)

Add a branch to the `diagnose` routing matrix (before the ambiguity→WIRE rule):

```bash
elif [ "$MISSING_ARTIFACTS" = "true" ]; then
  echo "WIRE"
```

## Acceptance Criteria

- [ ] A rate-limited sub-loop run reaches the parent's `rate_limit_diagnostic` and is reported in
      `summary.json.rate_limited`; the issue is **not** counted as implemented. (A)
- [ ] `on_rate_limit_exhausted` dead routes on the parent's `loop:` states are removed or made
      reachable. (A)
- [ ] An implement crash is recorded in `failures.txt` and `summary.json.failed`, and does **not**
      trigger a decomposition attempt. (B, C)
- [ ] Only `NEEDS_DECOMPOSE` outcomes route to `run_decomposition`. (B)
- [ ] `check_readiness` uses the loop-context thresholds; readiness and `diagnose` agree under
      overridden thresholds. (D)
- [ ] A killed run can be resumed without re-seeding the queue (or the dead checkpoint is removed). (E)
- [ ] A decomposed parent's status is set to `done` and it is moved to the completed directory. (F)
- [ ] When the decomposed parent had `parent: EPIC-NNN`, each child carries `parent: EPIC-NNN`,
      records lineage via `relates_to`/body marker, and appears in the EPIC's `relates_to:`,
      `## Children`, and `ll-issues epic-progress`. (F)
- [ ] `detect_children` still finds children after the `parent:` repoint (matches on body marker /
      manifest). (F)
- [ ] `run_size_review` has an `on_partial: detect_children` route; a `partial` verdict proceeds
      instead of `terminated_by: error`. (folds BUG-1975)
- [ ] A no-children `detect_children` outcome terminates the sub-loop in `done` (writing the
      `NO_CHILDREN` token), not `failed`; sub-loop telemetry no longer records `final_state: failed`
      for expected no-decomposition runs. (folds BUG-1974)
- [ ] An issue with `missing_artifacts: true` routes to `wire`. (G)
- [ ] `ll-loop validate` passes for all three loops; MR-1/MR-3/MR-4 remain satisfied.
- [ ] Tests cover: rate-limit classification, implement-failure classification, decompose
      classification, threshold pass-through, resume, parent-close, and EPIC re-linking (incl. the
      no-EPIC path).

## Impact

- **Priority**: P2 — GAP A causes silent success-reporting under rate limits (correctness/trust);
  B/C/F corrupt accounting and EPIC rollups.
- **Effort**: Large — touches all three loop YAMLs, `summary.json`, `issue-size-review` (child
  marker), and adds parent classifier/record-failure/finalize states + tests.
- **Risk**: Medium — changes routing semantics and issue-file mutation (status + EPIC frontmatter);
  the EPIC re-link must be idempotent and guard the no-EPIC path.
- **Breaking Change**: No (additive routing + lifecycle; `summary.json` gains fields).
- **Blast radius**: All `rn-implement` runs, especially under rate limits, on implement failures, and
  whenever a decomposed parent belongs to an EPIC.

## Status

**Open** | Created: 2026-06-06 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-06-06 - from rn-implement orchestration-contract review (executor.py:598-612 verdict mapping; run 2026-06-06T015949 audit)

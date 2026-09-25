---
id: BUG-3571
type: BUG
title: Refine-to-ready accepts stale or absent verify verdict and confidence scores
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:13Z'
parent: EPIC-3565
decision_needed: false
blocks:
- ENH-3577
---

# BUG-3571: Refine-to-ready accepts stale or absent verify verdict and confidence scores

## Summary

Readiness evidence is checked for presence, not currency:

- `ll-issues check-verify-verdict` (`cli/issues/check_verify_verdict.py`) returns 0 when
  the verdict frontmatter field is absent. This fail-open is deliberate (ENH-3031). But nothing in
  `refine-to-ready-issue` clears a prior verdict before `verify_issue` runs, and
  `verify_issue.on_error` routes into the check. A `VALID` from an earlier run, against
  earlier content, satisfies the gate even when the current verification errored. The check
  state's own `on_error` also routes to `check_hedges`, so an erroring probe passes too.
- `oracles/verify-confidence-scores.yaml` `verify_scores_persisted` only asserts that
  `confidence` and `outcome` exist in frontmatter. Pre-existing scores pass even when the
  current `/ll:confidence-check` call wrote nothing, and the oracle's retry path is then
  unreachable.
- Autodev's `rerun_confidence_after_decide|wire|spike|atomic_remediation` states route both
  `next` and `on_error` to a successor that reads scores through `ll-issues check-readiness`.
  None of them clears scores first (only the reconcile path does, via `/ll:reconcile-issue`'s
  `set-scores --clear`). A failed rescoring after a repair therefore falls through to the
  pre-repair scores.

## Current Behavior

A failed verify or scoring call can be followed by a pass based on evidence from a previous
revision of the issue.

## Expected Behavior

A gate passes only on evidence produced by the current invocation. A missing result from a
current call is a retryable infrastructure failure, not a pass and not a quality failure.

## Steps to Reproduce

1. Run refine-to-ready-issue on an issue carrying `verify_verdict: VALID` and scores from an earlier run
2. Make `/ll:verify-issues --check` error (e.g. host failure) and have confidence-check write nothing
3. Observe `check_verify_verdict` exit 0 and `verify_scores_persisted` exit 0 on the stale values

## Motivation

Autodev's repair loop edits issue content (reconcile, wire, refine) and then rescores. Without freshness, the implementation gate can be satisfied by evidence about content that no longer exists.

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **File**: `scripts/little_loops/cli/issues/check_verify_verdict.py`, `cmd_check_verify_verdict` — default mode passes on `verdict is None or str(verdict).upper() == "VALID"`; it reads only frontmatter (`parse_frontmatter(path.read_text(), coerce_types=True)`), with no timestamp, hash or nonce input, so it cannot distinguish a current verdict from one about earlier content.
- **Routing that feeds it stale state** (`scripts/little_loops/loops/refine-to-ready-issue.yaml`): `verify_issue` has `next: check_verify_verdict` and `on_error: check_verify_verdict` (comment: "verification failure is non-fatal, like wire_issue"); `check_verify_verdict` itself has `on_error: check_hedges`, i.e. an erroring probe also proceeds.
- **Scores** (`scripts/little_loops/loops/oracles/verify-confidence-scores.yaml`): `verify_scores_persisted` and `verify_scores_persisted_final` run identical Python and fail only if `d.get('confidence') is None or d.get('outcome') is None`. Because presence passes, `retry_confidence_check` is reachable only when scores are absent — with stale scores present the retry path is never taken.
- **Absent scores read as low quality**: `check_readiness.py:readiness_status` coerces an absent `confidence_score`/`outcome_confidence` to 0 (`int(fm.get(...) or 0)`), so clearing scores alone would turn a failed rescoring into a readiness deferral — an infra failure misclassified as a quality verdict. `ReadinessStatus.raw_confidence`/`raw_outcome` already carry `None` for absence.
- **Writers carry no binding**: `verify_verdict` is written only by the model via Edit in `commands/verify-issues.md` § "2.5. Check Mode Behavior (--check)" (values `VALID`, `EVIDENCE_UNVERIFIED`, `PROPOSAL_UNSOUND`, `NON_VALID`); there is no Python writer and no CLI that removes it. Scores are written by `ll-issues set-scores` (`cli/issues/set_scores.py:cmd_set_scores`, via `update_frontmatter`) from `skills/confidence-check/SKILL.md` Phase 4, and removed by `set-scores --clear` (`remove_frontmatter_keys(content, SCORE_KEYS)`).

## Proposed Solution

Clearing the verdict at refine start is a no-op while an absent verdict passes, so the
freshness mechanism and the absent-field semantics must change together. Options:

1. **Invocation stamp**: record a run-scoped nonce or timestamp before each verify/score
   call. The check requires the persisted field's stamp to be at least that recent.
2. **Content fingerprint**: persist verdict/scores with a hash of the issue body that
   excludes the Session Log and score fields themselves. The check recomputes and compares.
3. **Clear-then-require**: clear `verify_verdict`/scores immediately before each verify/score
   call, and report absence after the call as a distinct `ABSENT` result (exit 3) that the
   loops route to retry-once-then-infra — never to pass, and never to a quality verdict.

> **Selected:** 3. Clear-then-require — every consumer re-runs verify/scoring immediately before reading, so no cross-revision cache exists for a fingerprint to protect.

### Decision Rationale

- **No cache to bind.** Every reader of `verify_verdict` and the scores (refine-to-ready's
  `check_verify_verdict` and scores oracle, autodev's post-`rerun_confidence_after_*`
  rechecks) runs directly after the call that should have produced the evidence. Freshness
  here means "this invocation", which clearing gives exactly.
- **Option 2 costs more for no coverage gain.** It needs the verdict writer moved from a
  model Edit to a CLI, a new body-normalizing hash that excludes the Session Log and score
  fields, and `set-scores` changes — and still only protects a cache nobody reuses. Its
  claimed advantage (post-repair rescoring in autodev) is covered by clearing before each
  `rerun_confidence_after_*` call.
- **Option 1** adds a stamp to every writer (including the model-Edit verdict writer) and a
  run-scoped nonce plumbed into both loops; same writer cost as 2 with weaker binding.
- **Exit 3, not exit 1.** Folding absence into NON_VALID (or into readiness 0) would send an
  outage into `refine_followup`/deferral — the misclassification `refine-to-ready-issue.yaml`
  already names at `:955-960`. `fragment: harness_exit` (`lib/common.yaml`) sets
  `evaluate.abstain_on_exit_3: true`, which maps exit 3 to `on_cannot_judge`
  (`fsm/evaluators.py:evaluate_exit_code`); reuse that routing rather than a new convention.
- **Session Log invariant holds trivially**: nothing is cached across the call, so
  `ll-issues append-log` between the call and the check cannot invalidate anything.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

**Recommended**: Option 3 (clear-then-require), selected above. Note the absent-field defaults
differ across gates today — `check-verify-verdict` default mode fails open, its query flags
and `check-flag` fail closed, `check_readiness.py` coerces absent to 0 — and this fix aligns
the two evidence gates on an explicit `ABSENT` outcome.

## Program Design

### Types

- `ABSENT` exit code `3` — new outcome for `check-verify-verdict` default mode and `check-readiness` when the evidence field is missing; 0 pass / 1 fail / 2 issue not found are unchanged.

### Signatures

- `cmd_check_verify_verdict(config: BRConfig, args: argparse.Namespace) -> int` — existing; default mode returns 3 with a `VERIFY_VERDICT_ABSENT` stderr token instead of 0 when `verify_verdict` is absent.
- `cmd_check_readiness(config: BRConfig, args: argparse.Namespace) -> int` — existing; returns 3 with a `SCORES_ABSENT` token when `raw_confidence` or `raw_outcome` is `None`, before threshold comparison.
- `cmd_clear_verify_verdict(config: BRConfig, args: argparse.Namespace) -> int` — new `ll-issues clear-verify-verdict <ID>` verb; removes `verify_verdict` via `remove_frontmatter_keys`, mirroring `set-scores --clear`.

### Call Path

`cmd_clear_verify_verdict` -> `remove_frontmatter_keys`; `cmd_check_verify_verdict` -> `parse_frontmatter`; `cmd_check_readiness` -> `readiness_status`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `cmd_check_verify_verdict` default mode: absent → exit 3; `--proposal-unsound` / `--evidence-unverified` query modes unchanged
- `scripts/little_loops/cli/issues/check_readiness.py` — `cmd_check_readiness`: absent score → exit 3
- `scripts/little_loops/cli/issues/` — new `clear_verify_verdict.py` (register in `cli/issues/__init__.py` dispatch and `_USAGE` epilog)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`:
  - new `clear_verify_verdict` state ahead of `verify_issue` (every entry into `verify_issue` must pass through it)
  - `check_verify_verdict`: switch to `fragment: harness_exit`; `on_cannot_judge` → retry `verify_issue` once, then an infra terminal (mirror `check_decide_rate_limited` → `mark_rate_limit_infra`); `on_error` → the same infra path, not `check_hedges`
  - `confidence_check` entry, including the `run_spike` return (`next`/`on_error: confidence_check`) — scores cleared by the oracle's first state, see below
- `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml` — new initial state running `ll-issues set-scores <ID> --clear` before `confidence_check`; `verify_scores_persisted`/`_final` logic unchanged (presence is now sufficient because scores were cleared)
- `scripts/little_loops/loops/autodev.yaml`:
  - `set-scores --clear` before each of `rerun_confidence_after_decide|wire|spike|atomic_remediation` (reconcile's path already clears)
  - the successors' `check-readiness` calls (`recheck_after_decide`, `enqueue_or_skip`, `regate_after_atomic_remediation`, `recheck_after_size_review`): route exit 3 to an infra classification (model on `mark_gate_infra`, `:1097`) instead of deferral. Several call `check-readiness` inside compound shell (`:656`, `:791`, `:1370`); audit each so exit 3 is not swallowed by a pipe or `||`

### Dependent Files (Callers/Importers)
- `commands/verify-issues.md` (`--check` verdict persistence) — writer unchanged; § "Frontmatter sync" (~L389) still correct
- `skills/confidence-check/SKILL.md` (score persistence via `ll-issues set-scores`) — writer unchanged
- Every other `ll-issues check-readiness` caller (sprints, `ll-auto`, manage-issue gates) now sees exit 3 for unscored issues — grep all callers and confirm each treats non-zero-non-1 correctly

### Similar Patterns
- ENH-2630 verdict freshness in `auto-refine-and-implement.yaml` `merge_epic_branch`: a persisted verdict (`verify-verdict.txt`) is reused only when its recorded SHA (`verify-sha.txt`) matches the current tip; absent → re-run
- `fragment: harness_exit` exit-3 abstain routing (ENH-3224)
- `oracles/verify-confidence-scores.yaml` retry-once shape (`retry_confidence_check` → `verify_scores_persisted_final` → `failed`)

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `#### ll-issues check-verify-verdict` (line ~2345) states "Exit 0 if `VALID` **or absent** (fail-open)"; rewrite for exit 3, and the shared exit-code note (~line 2235); document `check-readiness` exit 3 and the new `clear-verify-verdict` verb [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — `oracles/verify-confidence-scores` row (~line 83) and the "Claim-verification gate chain (ENH-3031)" paragraph (~line 144) describe the gate semantics being changed [Agent 2 finding]
- `scripts/little_loops/cli/issues/__init__.py` — `check-verify-verdict` help line in `_USAGE`-style epilog (~line 160, "Exit 0 unless … NON_VALID") restates the fail-open contract; also the `add_check_verify_verdict_parser` help string [Agent 2 finding]
- `.qwen/commands/ll/verify-issues.md`, `.gemini/commands/verify-issues.toml`, `.kimi-code/skills/ll-verify-issues/SKILL.md` — generated mirrors; regenerate with `ll-adapt --host <gemini|kimi-code|qwen> --apply` only if `commands/verify-issues.md` or `skills/confidence-check/SKILL.md` change [Agent 2 finding]

### Configuration
- N/A

### Tests
- `scripts/tests/test_ll_issues_check_verify_verdict.py` — `test_absent_field_exits_zero_fail_open` (line 86) pins the fail-open contract; replace with an absent → exit 3 test [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — routing assertions that change: `verify_issue.next`/`on_error` (~1574-1578), `test_check_verify_verdict_state_routing` (~1582-1596), oracle routing (~1489-1507), `test_check_verify_verdict_on_no_reaches_check_proposal_unsound` (~3083) [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — ENH-2630 freshness tests (`test_merge_epic_branch_reuses_fresh_verify_verdict` ~4879; `test_reuses_fresh_verify_verdict_and_skips_rerun` / `test_reruns_when_verify_verdict_missing` ~6478-6522) are the model for the new stateful regression cases [Agent 3 finding]
- `scripts/tests/test_autodev_loop.py` — clear-before-rerun and exit-3 routing for the four `rerun_confidence_after_*` successors
- `scripts/tests/test_set_scores_cli.py` — unchanged unless `--clear` behavior changes [Agent 3 finding]
- New `check-readiness` exit-3 CLI test and `clear-verify-verdict` CLI test (temp `.issues/` pattern from `test_ll_issues_check_verify_verdict.py`)
- Test techniques (no successive-call stateful stub exists yet): run the real state `action` under `bash -c` against a stub `ll-issues` on `PATH` (`test_builtin_loops.py:1989-2008`, `:7753-7770`; `test_autodev_loop.py:644-688`); persist state across invocations through run-dir files (`_run_counter_state`, `test_builtin_loops.py:1894-1901`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Autodev does not use the scores oracle.** `oracles/verify-confidence-scores` is referenced only by `refine-to-ready-issue.yaml` (`confidence_check` state). Autodev's five rerun states (`rerun_confidence_after_decide|wire|spike|atomic_remediation|reconcile`) set `next` and `on_error` to the same successor — `recheck_after_decide`, `enqueue_or_skip` (wire and spike), `regate_after_atomic_remediation`, `recheck_after_size_review` — which read scores through `ll-issues check-readiness`. They already use `with_rate_limit_handling` / `on_rate_limit_exhausted: finalize_rate_limited`.
- **Scores are already cleared on one path.** `ll-issues set-scores --clear` removes the six `SCORE_KEYS`; `commands/reconcile-issue.md` § 5 step 2 calls it after a rewrite (commit `b2f7e09a9`). No loop YAML calls `--clear`, and nothing clears `verify_verdict` anywhere.
- **Invariant for any freshness design**: verdict/score persistence must not be invalidated by Session Log appends (the `ll-issues append-log` step runs inside the same passes) — and Step 6.5-style log appends occur *between* verify and check. Clear-then-require satisfies this by construction.
- **Freshness conventions already in the codebase** (none applied to `verify_verdict` or scores): (1) per-run scoping via `${context.run_dir}` marker/counter files reset in `resolve_issue` (`refine-to-ready-issue.yaml:146-158`); (2) content/fingerprint binding recomputed at read time (`general-task.yaml` `input_hash`/`task_hash`, `git hash-object` working-tree fingerprint at `:434-485`; `cli/artifact/status.py` `_sha256_file`; `cli/verify_evidence.py` `_span_hash`/`_worktree_fingerprint`); (3) timestamp comparison (`issues/research_triage.py:_triage_axis`); (4) rescore-and-compare against a dequeue snapshot (`autodev-pre-readiness.txt`, ~2224-2307).
- **`ll-issues check-*` exit-code contract**: 0 pass / 1 fail / 2 issue not found, wired through `fragment: shell_exit`. `set_scores.py:51` is the outlier (returns 1 for not-found).
- **`on_error` routing is split**: verify/score gates fail open to the same target as `on_yes`, whereas rate-limit and learning-gate paths classify infra failures explicitly (`check_decide_rate_limited` → `mark_rate_limit_infra` → `refine-terminal-class = infra`; `mark_gate_infra`/`GATE_INFRA_FAILED` in autodev and rn-remediate).

## Implementation Steps

1. `check-verify-verdict` default mode: absent → exit 3 (`VERIFY_VERDICT_ABSENT`); update parser help, `_USAGE`, and the CLI test that pins fail-open
2. `check-readiness`: absent score → exit 3 (`SCORES_ABSENT`) before threshold comparison; grep every caller and confirm exit 3 is handled
3. Add `ll-issues clear-verify-verdict <ID>` (via `remove_frontmatter_keys`) with a CLI test
4. refine-to-ready: `clear_verify_verdict` state before every entry to `verify_issue`; `check_verify_verdict` on `harness_exit` with `on_cannot_judge` → one retry of `verify_issue`, then infra terminal; `on_error` → infra path
5. Scores oracle: initial `set-scores --clear` state before `confidence_check` (covers every refine-to-ready entry, including the `run_spike` return)
6. autodev: `set-scores --clear` before each `rerun_confidence_after_{decide,wire,spike,atomic_remediation}`; route `check-readiness` exit 3 in each successor to an infra classification instead of deferral
7. Regression tests (stateful stubs): failed verify with a prior `VALID` does not pass; no-op confidence-check with prior scores does not pass; failed autodev rescoring after wire does not pass on pre-repair scores; each absent case lands on the infra path, not NON_VALID/deferral
8. Update `docs/reference/CLI.md` and `docs/guides/LOOPS_REFERENCE.md` gate contracts

## Impact

- **Priority**: P2. Old scores come from real earlier runs, so this is not fabrication, but
  post-repair content goes unverified.
- **Effort**: Medium
- **Risk**: Medium. A stricter gate raises infra-classified stops; routing absence to infra
  (not quality) keeps it from inflating deferral rates. Shares `refine-to-ready-issue.yaml`'s
  `run_spike` → `confidence_check` path and the confidence-check skill with BUG-3572 — land
  the two sequentially.

## Acceptance Criteria

- [ ] A verify call that errors cannot pass on a verdict from a prior run
- [ ] An erroring `check_verify_verdict` probe does not route to `check_hedges`
- [ ] A confidence-check that writes nothing cannot pass on pre-existing scores (refine-to-ready, including after `run_spike`)
- [ ] An autodev rescoring that fails after decide/wire/spike/atomic remediation cannot pass on pre-repair scores
- [ ] Absent evidence after a completed call is classified as infra (retry once, then infra stop) — not `NON_VALID` and not a low-readiness deferral
- [ ] `ll-issues check-verify-verdict` and `check-readiness` exit 3 on absent evidence; 0/1/2 semantics otherwise unchanged
- [ ] Session Log appends between a call and its check do not affect the gate

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-09-25T01:11:23 - `283a56a1-35bd-43bb-b2f7-64d9f104c2c4.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:06:50 - `42a934e3-5df9-4ac6-9296-d0ced0bc2261.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:19 - `4b76ee9e-e590-41ab-940d-a6df6f1554bd.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:31 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`

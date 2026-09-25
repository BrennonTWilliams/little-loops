---
id: BUG-3571
type: BUG
title: Refine-to-ready accepts stale or absent verify verdict and confidence scores
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:13Z'
completed_at: '2026-09-25T02:14:48Z'
parent: EPIC-3565
decision_needed: false
blocks:
- ENH-3577
- BUG-3572
- BUG-3574
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# BUG-3571: Refine-to-ready accepts stale or absent verify verdict and confidence scores

## Summary

Readiness evidence in `refine-to-ready-issue` is checked for presence, not currency:

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

**Scope split (2026-09-25):** autodev's post-repair rescoring
(`rerun_confidence_after_*`) and `ll-issues check-readiness` exit 3 moved to **BUG-3588**. This
issue covers `check-verify-verdict`, the new `clear-verify-verdict` verb, the scores oracle and
`refine-to-ready-issue.yaml`.

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

refine-to-ready re-enters its gate band after every repair (`refine_followup`,
`reconcile_issue`, `run_spike` → `confidence_check`) and gates again. Without freshness, the
readiness verdict it hands to callers (autodev, recursive-refine) can rest on evidence about
content that no longer exists.

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **File**: `scripts/little_loops/cli/issues/check_verify_verdict.py`, `cmd_check_verify_verdict` — default mode passes on `verdict is None or str(verdict).upper() == "VALID"`; it reads only frontmatter (`parse_frontmatter(path.read_text(), coerce_types=True)`), with no timestamp, hash or nonce input, so it cannot distinguish a current verdict from one about earlier content.
- **Routing that feeds it stale state** (`scripts/little_loops/loops/refine-to-ready-issue.yaml`): `verify_issue` has `next: check_verify_verdict` and `on_error: check_verify_verdict` (comment: "verification failure is non-fatal, like wire_issue"); `check_verify_verdict` itself has `on_error: check_hedges`, i.e. an erroring probe also proceeds.
- **Scores** (`scripts/little_loops/loops/oracles/verify-confidence-scores.yaml`): `verify_scores_persisted` and `verify_scores_persisted_final` run identical Python and fail only if `d.get('confidence') is None or d.get('outcome') is None`. Because presence passes, `retry_confidence_check` is reachable only when scores are absent — with stale scores present the retry path is never taken. `confidence_check.on_error: failed` also skips the retry entirely.
- **Writers carry no binding**: `verify_verdict` is written only by the model via Edit in `commands/verify-issues.md` § "2.5. Check Mode Behavior (--check)" (values `VALID`, `EVIDENCE_UNVERIFIED`, `PROPOSAL_UNSOUND`, `NON_VALID`) — for every verdict, so absence after a completed `--check` call means the call failed. There is no Python writer and no CLI that removes it. Scores are written by `ll-issues set-scores` (`cli/issues/set_scores.py:cmd_set_scores`, via `update_frontmatter`) from `skills/confidence-check/SKILL.md` Phase 4, and removed by `set-scores --clear` (`remove_frontmatter_keys(content, SCORE_KEYS)`).

## Proposed Solution

Clearing the verdict at refine start is a no-op while an absent verdict passes, so the
freshness mechanism and the absent-field semantics must change together. Options:

1. **Invocation stamp**: record a run-scoped nonce or timestamp before each verify/score
   call. The check requires the persisted field's stamp to be at least that recent.
2. **Content fingerprint**: persist verdict/scores with a hash of the issue body that
   excludes the Session Log and score fields themselves. The check recomputes and compares.
3. **Clear-then-require**: clear `verify_verdict`/scores immediately before each verify/score
   call, and report absence after the call as a distinct `ABSENT` result (exit 3) that the
   loop routes to retry-once-then-infra — never to pass, and never to a quality verdict.

> **Selected:** 3. Clear-then-require — every consumer re-runs verify/scoring immediately before reading, so no cross-revision cache exists for a fingerprint to protect.

### Decision Rationale

- **No cache to bind.** Every reader of `verify_verdict` and the scores in this loop
  (`check_verify_verdict` and the scores oracle) runs directly after the call that should have
  produced the evidence. Freshness here means "this invocation", which clearing gives exactly.
  Autodev's post-repair rechecks follow the same shape (BUG-3588).
- **Option 2 costs more for no coverage gain.** It needs the verdict writer moved from a
  model Edit to a CLI, a new body-normalizing hash that excludes the Session Log and score
  fields, and `set-scores` changes — and still only protects a cache nobody reuses.
- **Option 1** adds a stamp to every writer (including the model-Edit verdict writer) and a
  run-scoped nonce plumbed into the loop; same writer cost as 2 with weaker binding.
- **Exit 3, not exit 1.** Folding absence into NON_VALID would send an outage into
  `refine_followup` — the misclassification `refine-to-ready-issue.yaml` already names at
  `:955-960`. `fragment: harness_exit` (`lib/common.yaml`) sets
  `evaluate.abstain_on_exit_3: true`, which maps exit 3 to `on_cannot_judge`
  (`fsm/evaluators.py:evaluate_exit_code`); reuse that routing rather than a new convention.
- **Session Log invariant holds trivially**: nothing is cached across the call, so
  `ll-issues append-log` between the call and the check cannot invalidate anything.

## Program Design

### Types

- `ABSENT` exit code `3` — new outcome for `check-verify-verdict` default mode when `verify_verdict` is missing; 0 pass / 1 fail / 2 issue not found are unchanged.

### Signatures

- `cmd_check_verify_verdict(config: BRConfig, args: argparse.Namespace) -> int` — existing; default mode returns 3 with a `VERIFY_VERDICT_ABSENT` stderr token instead of 0 when `verify_verdict` is absent.
- `cmd_clear_verify_verdict(config: BRConfig, args: argparse.Namespace) -> int` — new `ll-issues clear-verify-verdict <ID>` verb; removes `verify_verdict` via `remove_frontmatter_keys`, mirroring `set-scores --clear`.

### Call Path

`cmd_clear_verify_verdict` -> `remove_frontmatter_keys`; `cmd_check_verify_verdict` -> `parse_frontmatter`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `cmd_check_verify_verdict` default mode: absent → exit 3; `--proposal-unsound` / `--evidence-unverified` query modes unchanged (they fail closed on absence and are only reached after a present verdict)
- `scripts/little_loops/cli/issues/` — new `clear_verify_verdict.py` (register in `cli/issues/__init__.py` dispatch and `_USAGE` epilog)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`:
  - new `clear_verify_verdict` state ahead of `verify_issue`. `verify_issue` has a single predecessor today (`normalize_structure`, `next` and `on_error`), so retargeting that one state covers every entry
  - `check_verify_verdict`: switch to `fragment: harness_exit`; `on_cannot_judge` → a retry-counter state → one retry via `clear_verify_verdict` (not `verify_issue` directly, so the retry also starts from a cleared field), then `mark_evidence_absent_infra`; `on_error` → `mark_evidence_absent_infra`, not `check_hedges`
  - **retry counter** `${context.run_dir}/refine-to-ready-verify-retries`: seed it to `0` in `resolve_issue` alongside the other counters (`:150-156`). autodev reuses one run_dir across issues (see the comment at `:172-175`), so an unreset counter would carry a spent retry into the next issue. The cap is per run, not per gate-band pass
  - new `mark_evidence_absent_infra` terminal-class state: `printf 'infra' > ${context.run_dir}/refine-terminal-class`, echo a `[VERIFY_VERDICT_ABSENT]` / `[SCORES_ABSENT]` token naming the source, `next: failed`. Do not reuse `mark_rate_limit_infra` — its name and comment are rate-limit-specific, and postmortems need to tell an evidence outage from a 429
  - `confidence_check` entry, including the `run_spike` return (`next`/`on_error: confidence_check`) — scores cleared by the oracle's first state, see below
  - `confidence_check.on_failure`/`on_error` (currently `diagnose`): an oracle `failed` after a cleared start means absent evidence — route both to `mark_evidence_absent_infra`, not through `diagnose`; today nothing classifies it
- `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml` — new initial state running `ll-issues set-scores <ID> --clear` before `confidence_check`; `verify_scores_persisted`/`_final` logic unchanged (presence is now sufficient because scores were cleared). Also `confidence_check.on_error: failed` skips the retry entirely — route it to `retry_confidence_check` so an erroring first call gets the same one retry as a no-op call

### Dependent Files (Callers/Importers)
- `commands/verify-issues.md` (`--check` verdict persistence) — writer unchanged; § "Frontmatter sync" (~L389) still correct
- `skills/confidence-check/SKILL.md` (score persistence via `ll-issues set-scores`) — writer unchanged
- `ll-issues check-verify-verdict` callers: `refine-to-ready-issue.yaml` only (`check_verify_verdict`, `check_evidence_unverified`, `check_proposal_unsound`) — grep of `scripts/little_loops`, `skills`, `commands`, `hooks`
- `oracles/verify-confidence-scores` callers: `refine-to-ready-issue.yaml` `confidence_check` only
- refine-to-ready's own `check_readiness` / `check_outcome` / `check_scores_from_file` coerce absence to 0, but are reached only on the oracle's `done` terminal (scores present) — unchanged

### Similar Patterns
- ENH-2630 verdict freshness in `auto-refine-and-implement.yaml` `merge_epic_branch`: a persisted verdict (`verify-verdict.txt`) is reused only when its recorded SHA (`verify-sha.txt`) matches the current tip; absent → re-run
- `fragment: harness_exit` exit-3 abstain routing (ENH-3224)
- `oracles/verify-confidence-scores.yaml` retry-once shape (`retry_confidence_check` → `verify_scores_persisted_final` → `failed`)
- `check_decide_attempts` run-dir counter seeded in `resolve_issue` (BUG-3553)

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `#### ll-issues check-verify-verdict` (line ~2345) states "Exit 0 if `VALID` **or absent** (fail-open)"; rewrite for exit 3, and the shared exit-code note (~line 2235); document the new `clear-verify-verdict` verb [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — `oracles/verify-confidence-scores` row (~line 83) and the "Claim-verification gate chain (ENH-3031)" paragraph (~line 144) describe the gate semantics being changed [Agent 2 finding]
- `scripts/little_loops/cli/issues/__init__.py` — `check-verify-verdict` help line in `_USAGE`-style epilog (~line 160, "Exit 0 unless … NON_VALID") restates the fail-open contract; also the `add_check_verify_verdict_parser` help string [Agent 2 finding]
- `.qwen/commands/ll/verify-issues.md`, `.gemini/commands/verify-issues.toml`, `.kimi-code/skills/ll-verify-issues/SKILL.md` — generated mirrors; regenerate with `ll-adapt --host <gemini|kimi-code|qwen> --apply` only if `commands/verify-issues.md` or `skills/confidence-check/SKILL.md` change [Agent 2 finding]

### Configuration
- N/A

### Tests
- `scripts/tests/test_ll_issues_check_verify_verdict.py` — `test_absent_field_exits_zero_fail_open` (line 86) pins the fail-open contract; replace with an absent → exit 3 test [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — routing assertions that change: `verify_issue.next`/`on_error` (~1574-1578), `test_check_verify_verdict_state_routing` (~1582-1596), oracle routing (~1489-1507), `test_check_verify_verdict_on_no_reaches_check_proposal_unsound` (~3083) [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — add a `resolve_issue` seeds-`refine-to-ready-verify-retries` assertion next to `test_resolve_issue_seeds_hedge_attempts_counter` (~1663) / `test_resolve_issue_resets_decide_and_spike_state` (~1984)
- `scripts/tests/test_builtin_loops.py` — ENH-2630 freshness tests (`test_merge_epic_branch_reuses_fresh_verify_verdict` ~4879; `test_reuses_fresh_verify_verdict_and_skips_rerun` / `test_reruns_when_verify_verdict_missing` ~6478-6522) are the model for the new stateful regression cases [Agent 3 finding]
- New `clear-verify-verdict` CLI test (temp `.issues/` pattern from `test_ll_issues_check_verify_verdict.py`)
- Test techniques (no successive-call stateful stub exists yet): run the real state `action` under `bash -c` against a stub `ll-issues` on `PATH` (`test_builtin_loops.py:1989-2008`, `:7753-7770`); persist state across invocations through run-dir files (`_run_counter_state`, `test_builtin_loops.py:1894-1901`)

## Implementation Steps

1. `check-verify-verdict` default mode: absent → exit 3 (`VERIFY_VERDICT_ABSENT`); update parser help, `_USAGE`, and the CLI test that pins fail-open
2. Add `ll-issues clear-verify-verdict <ID>` (via `remove_frontmatter_keys`) with a CLI test
3. refine-to-ready: `mark_evidence_absent_infra` state; `refine-to-ready-verify-retries` seeded in `resolve_issue`
4. refine-to-ready: `clear_verify_verdict` state between `normalize_structure` and `verify_issue`; `check_verify_verdict` on `harness_exit` with `on_cannot_judge` → one retry via `clear_verify_verdict`, then `mark_evidence_absent_infra`; `on_error` → `mark_evidence_absent_infra`
5. Scores oracle: initial `set-scores --clear` state before `confidence_check` (covers every refine-to-ready entry, including the `run_spike` return); `confidence_check.on_error` → `retry_confidence_check`. refine-to-ready: route `confidence_check.on_failure`/`on_error` to `mark_evidence_absent_infra`
6. Regression tests (stateful stubs): failed verify with a prior `VALID` does not pass; no-op confidence-check with prior scores does not pass; each absent case lands on `mark_evidence_absent_infra` (terminal class `infra`), not NON_VALID/`refine_followup`; a spent verify retry in one issue does not carry into the next issue in a shared run_dir
7. Update `docs/reference/CLI.md` and `docs/guides/LOOPS_REFERENCE.md` gate contracts

## Impact

- **Priority**: P2. Old verdicts and scores come from real earlier runs, so this is not
  fabrication, but post-repair content goes unverified.
- **Effort**: Small–Medium (after the BUG-3588 split)
- **Risk**: Medium. A stricter gate raises infra-classified stops; routing absence to infra
  (not quality) keeps it from inflating deferral rates. A run that clears scores and then
  stops leaves the issue unscored; `ll-auto`'s gate then reports it as "no confidence score
  (never assessed)" — accurate, but a visible change.
- **Sequencing**: lands first. BUG-3572 (shares refine-to-ready's `run_spike` →
  `confidence_check` path and the confidence-check skill) and BUG-3574 (shares
  `check_verify_verdict.py` and the verify gate band) are `blocked_by` this issue. BUG-3588
  (autodev half) touches disjoint files and can land in parallel.

## Acceptance Criteria

- [x] A verify call that errors cannot pass on a verdict from a prior run
- [x] An erroring `check_verify_verdict` probe does not route to `check_hedges`
- [x] A confidence-check that writes nothing cannot pass on pre-existing scores (including after `run_spike`)
- [x] Absent evidence after a completed call is retried once, then classified as infra via `mark_evidence_absent_infra` — not `NON_VALID`, not `refine_followup`, not an unclassified `diagnose`
- [x] The verify retry counter is reset per issue in `resolve_issue`
- [x] `ll-issues check-verify-verdict` exits 3 on an absent verdict; 0/1/2 semantics otherwise unchanged
- [x] Session Log appends between a call and its check do not affect the gate

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Resolution

Implemented Option 3 (clear-then-require). `check-verify-verdict` exits 3 (`VERIFY_VERDICT_ABSENT`) on an absent verdict; new `ll-issues clear-verify-verdict`; refine-to-ready clears before `verify_issue`, retries once via `check_verify_retries` (counter seeded per issue in `resolve_issue`), and routes absence/probe errors/oracle failure to `mark_evidence_absent_infra` (class `infra`). The scores oracle clears scores first and retries on `confidence_check` error. Tests and CLI/loop docs updated. Two unrelated failures pre-exist on main (`test_no_new_unverifiable_evidence`, `test_autodev_topology`).

## Status

**Open** | Created: 2026-09-24 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-24; scores cleared 2026-09-25 after the BUG-3588 split changed scope — re-run `/ll:confidence-check`._

### Concerns
- _Resolved:_ the Integration Map's `:656`/`:791`/`:1370` `check-readiness` citations moved to BUG-3588 with the autodev half.

### Outcome Risk Factors
- _Mitigated by split:_ was ~12 change sites across 3 CLI files, 2 loop YAMLs + oracle and 5 autodev states (outcome 64); the autodev half and `check-readiness` are now BUG-3588.
- No successive-call stateful stub exists yet; the regression tests need new test infrastructure.
- _Resolved:_ `confidence_check.on_failure`/`on_error` route to `mark_evidence_absent_infra`.

## Session Log
- `/ll:manage-issue` - 2026-09-25T02:14:47 - `c7e90b5f-625f-45b3-83aa-bfd944e4d83f.jsonl`
- `/ll:ready-issue` - 2026-09-25T02:04:21 - `5af81d8a-1dd8-4009-bfe9-b6aa8410d743.jsonl`
- `/ll:confidence-check` - 2026-09-25T02:02:24 - `5a030a02-b57b-4f48-9915-c2922670f102.jsonl`
- `/ll:confidence-check` - 2026-09-25T01:45:32 - `ce904479-7e73-4d58-aa48-892e2cdb88b3.jsonl`
- `/ll:wire-issue` - 2026-09-25T01:11:23 - `283a56a1-35bd-43bb-b2f7-64d9f104c2c4.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:06:50 - `42a934e3-5df9-4ac6-9296-d0ced0bc2261.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:19 - `4b76ee9e-e590-41ab-940d-a6df6f1554bd.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:31 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`

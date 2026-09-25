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
decision_needed: true
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
  earlier content, satisfies the gate even when the current verification errored.
- `oracles/verify-confidence-scores.yaml` `verify_scores_persisted` only asserts that
  `confidence` and `outcome` exist in frontmatter. Pre-existing scores pass even when the
  current `/ll:confidence-check` call wrote nothing.
- Autodev's outer `rerun_confidence_after_*` states route `on_error` into score checks, so a
  failed rescoring falls through to the old scores.

## Current Behavior

A failed verify or scoring call can be followed by a pass based on evidence from a previous
revision of the issue.

## Expected Behavior

A gate passes only on evidence produced by the current invocation, or on cached evidence
provably bound to the current issue content. A missing result from a current call is a
retryable infrastructure failure, not a pass.

## Steps to Reproduce

1. Run refine-to-ready-issue on an issue carrying `verify_verdict: VALID` and scores from an earlier run
2. Make `/ll:verify-issues --check` error (e.g. host failure) and have confidence-check write nothing
3. Observe `check_verify_verdict` exit 0 and `verify_scores_persisted` exit 0 on the stale values

## Motivation

Autodev's repair loop edits issue content (reconcile, wire, refine) and then rescores. Without freshness, the implementation gate can be satisfied by evidence about content that no longer exists.

## Proposed Solution

Design decision needed first: clearing the verdict at refine start is a no-op while an absent
verdict passes. Options:

1. **Invocation stamp**: record a run-scoped nonce or timestamp before each verify/score
   call. The check requires the persisted field's stamp to be at least that recent.
2. **Content fingerprint**: persist verdict/scores with a hash of the issue body that
   excludes the Session Log and score fields themselves. The check recomputes and compares.
3. **Clear-then-require**: clear `verify_verdict`/scores before the call, and make absence
   after a completed call fail (keeping fail-open only for the pre-ENH-3031 legacy case).

Option 3 is the cheapest. Option 2 also covers the outer loop's post-repair rescoring.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

**Option A**: Invocation stamp — record a run-scoped nonce or timestamp before each verify/score call; the check requires the persisted field's stamp to be at least that recent.

**Option B**: Content fingerprint — persist verdict/scores with a hash of the issue body that excludes the Session Log and score fields themselves; the check recomputes and compares. Also covers the outer loop's post-repair rescoring.

**Option C**: Clear-then-require — clear `verify_verdict`/scores before the call and make absence after a completed call fail (keeping fail-open only for the pre-ENH-3031 legacy case). Cheapest.

**Recommended**: not selected — decision deferred to `/ll:decide-issue`; note the fail-open default and the `check_readiness.py` absent-score-as-0 behavior differ across gates (see Integration Map findings).

## Program Design

Provisional on the freshness-mechanism decision above; signatures assume Option 2 (content fingerprint).

### Types

- `verdict_fingerprint: str` — frontmatter field persisted beside the verdict and scores.

### Signatures

- `cmd_check_verify_verdict(config: BRConfig, args: argparse.Namespace) -> int` — existing; compares the stored fingerprint to the recomputed one.
- `content_fingerprint(body: str) -> str` — new; hashes the body excluding the Session Log and score fields.

### Call Path

`parse_frontmatter` -> `cmd_check_verify_verdict` -> `content_fingerprint`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `cmd_check_verify_verdict`
- `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml` — `verify_scores_persisted`, `verify_scores_persisted_final`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `verify_issue`, `check_verify_verdict`
- `scripts/little_loops/loops/autodev.yaml` — `rerun_confidence_after_*` `on_error` routes

### Dependent Files (Callers/Importers)
- `commands/verify-issues.md` (`--check` verdict persistence)
- `skills/confidence-check/SKILL.md` (score persistence via `ll-issues set-scores`)

### Similar Patterns
- The resolve-decision oracle's `done` terminal: its description should also be corrected, since it can return `done` with the flag armed (see BUG-3568)

### Tests
- `scripts/tests/test_builtin_loops.py`, `scripts/tests/test_autodev_loop.py`; new stateful-stub regression cases

### Documentation
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `#### ll-issues check-verify-verdict` (line ~2345) states "Exit 0 if `VALID` **or absent** (fail-open)"; rewrite if absence stops passing, and the shared exit-code note (~line 2235) [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — `oracles/verify-confidence-scores` row (~line 83) and the "Claim-verification gate chain (ENH-3031)" paragraph (~line 144) describe the gate semantics being changed [Agent 2 finding]
- `scripts/little_loops/cli/issues/__init__.py` — `check-verify-verdict` help line in `_USAGE`-style epilog (~line 160, "Exit 0 unless … NON_VALID") restates the fail-open contract [Agent 2 finding]
- `.qwen/commands/ll/verify-issues.md`, `.gemini/commands/verify-issues.toml`, `.kimi-code/skills/ll-verify-issues/SKILL.md` — generated mirrors of `commands/verify-issues.md`; regenerate with `ll-adapt --host <gemini|kimi-code|qwen> --apply` after editing the verdict writer or `skills/confidence-check/SKILL.md` [Agent 2 finding]

### Configuration
- N/A

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_check_verify_verdict.py` — `test_absent_field_exits_zero_fail_open` (line 86) pins the fail-open contract and will break if absence stops passing [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — routing assertions will break if routes change: `verify_issue.next`/`on_error` (lines ~1574-1578), `test_check_verify_verdict_state_routing` (~1582-1596), oracle routing (~1489-1507); also `test_check_verify_verdict_on_no_reaches_check_proposal_unsound` (~3083) [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — `test_merge_epic_branch_reuses_fresh_verify_verdict` (~4879) and `test_reuses_fresh_verify_verdict_and_skips_rerun` / `test_reruns_when_verify_verdict_missing` (~6478-6511): existing verdict-freshness precedent in `auto-refine-and-implement` (`epic_cfg.refresh_on_reuse`); model new regression cases on them [Agent 3 finding]
- `scripts/tests/test_set_scores_cli.py` — `test_set_scores_writes_all_fields`, `test_set_scores_updates_existing_fields_without_disturbing_others`; update if `set-scores` also persists a stamp/fingerprint [Agent 3 finding]
- `scripts/tests/test_confidence_check_skill.py` — asserts on `skills/confidence-check/SKILL.md` Phase 4; update if score persistence changes [Agent 3 finding]
- `scripts/tests/test_enh3250_verify_issues_graph_seeding.py`-family (`test_enh3126_verify_issues_graph_seeding.py`, `test_enh3250_verify_issues_proposal_vs_code.py`) — assert on `commands/verify-issues.md` text; update if the `--check` verdict-persistence step changes [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Correction — autodev does not use the scores oracle.** The issue says autodev's `rerun_confidence_after_*` `on_error` routes "into score checks" and that the oracle's `verify_scores_persisted` is involved. `oracles/verify-confidence-scores` is referenced only by `refine-to-ready-issue.yaml` (`confidence_check` state, `loop: oracles/verify-confidence-scores`). Autodev's five rerun states (`rerun_confidence_after_decide|wire|spike|atomic_remediation|reconcile`) all set `next` and `on_error` to the same successor — `recheck_after_decide`, `enqueue_or_skip` (wire and spike), `regate_after_atomic_remediation`, `recheck_after_size_review` — which read scores through `ll-issues check-readiness`. They already use `with_rate_limit_handling` / `on_rate_limit_exhausted: finalize_rate_limited`. Unread by this pass: the `check-readiness` implementation and the `enqueue_or_skip` body.
- **Correction — scores are already cleared on one path.** `ll-issues set-scores --clear` removes the six `SCORE_KEYS`; `commands/reconcile-issue.md` § 5 step 2 calls it after a rewrite (commit `b2f7e09a9`). So after reconcile in either loop, rescoring starts from cleared scores and the "falls through to old scores" claim does not hold on that path. No loop YAML calls `--clear`, and nothing clears `verify_verdict` anywhere.
- **Program Design ordering**: the Call Path `parse_frontmatter -> cmd_check_verify_verdict -> content_fingerprint` is reversed for the first hop — `cmd_check_verify_verdict` already imports and calls `parse_frontmatter` (`scripts/little_loops/frontmatter.py`, siblings `strip_frontmatter`, `update_frontmatter`, `remove_frontmatter_keys`).
- **No fingerprint precedent for issue content**: `content_fingerprint`, `verdict_fingerprint`, `body_hash`, `issue_hash` exist nowhere in code. Existing hashing is unrelated (`fsm/context_seed.py:derive_input_hash` sha256 of `context["input"]`; `session_store/schema.py` `target_content_hash`/`input_hash` columns; `issue_history/agent_quality.py`; `pii.py`). `scripts/little_loops/session_log.py:session_log_body()` reads a Session Log section's body (fence-aware) but no helper returns the body with the Session Log removed.
- **Writers that would have to persist any stamp/fingerprint** (currently listed only as dependents): `commands/verify-issues.md` (verdict writer, model-driven Edit, so a binding value must be computed by a CLI it calls, not by the model) and `skills/confidence-check/SKILL.md` Phase 4 (`set-scores`). Skill edits trip the mirror gates (`ll-adapt --apply`).
- **Invariant for any freshness design**: verdict/score persistence must not be invalidated by Session Log appends (the `ll-issues append-log` step runs inside the same passes) — and Step 6.5-style log appends occur *between* verify and check.

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Freshness conventions already in the codebase** (none applied to `verify_verdict` or scores): (1) per-run scoping via `${context.run_dir}` marker/counter files reset in `resolve_issue` (`refine-to-ready-issue.yaml:146-158`, `refine-to-ready-spike-ran` at `check_spike_needed`) — freshness means "this run", not "this content"; (2) content/fingerprint binding recomputed at read time (`general-task.yaml` `input_hash`/`task_hash` at `:223-229`, `:370-371` and the `git hash-object` working-tree fingerprint at `:434-485` that excludes `.loops/` so the gate's own artifacts do not perturb it; `cli/artifact/status.py:41-72` `_sha256_file`; `cli/verify_evidence.py:1106-1270` `_span_hash`/`_worktree_fingerprint`); (3) timestamp comparison (`issues/research_triage.py:_triage_axis` at `:464-479` — `changed > refined_at` marks an axis stale; skipped when `refined_at is None`); (4) rescore-and-compare against a dequeue snapshot (`autodev-pre-readiness.txt`, lines ~2224-2307), which detects "no better", not "not rewritten".
- **`ll-issues check-*` exit-code contract**: 0 pass / 1 fail / 2 issue not found (`check_flag.py`, `check_readiness.py`, `check_verify_verdict.py`, `check_open_questions.py`, `check_decidable.py`, `check_acceptance_criteria.py`, `check_design.py`, `check_unresolved_decisions.py`), wired through `fragment: shell_exit`. `set_scores.py:51` is the outlier (returns 1 for not-found). Absent-field defaults disagree: `check-verify-verdict` default mode fails open, its `--proposal-unsound`/`--evidence-unverified` flags and `check-flag` fail closed, and `check_readiness.py:128-133` coerces an absent score to 0 (fails the threshold).
- **`on_error` routing is split**: verify/score gates fail open to the same target as `on_yes` (`verify_issue`, `check_verify_verdict`, `run_spike`, autodev `rerun_confidence_after_*`), whereas rate-limit and learning-gate paths classify infra failures explicitly (`check_decide_rate_limited` → `mark_rate_limit_infra` → `refine-terminal-class = infra`; `mark_gate_infra`/`GATE_INFRA_FAILED` in autodev and rn-remediate; `refine-to-ready-issue.yaml:955-960` names routing an outage into a quality verdict a "misclassification"). The oracle's `retry_confidence_check` → `verify_scores_persisted_final` → `failed` is the only retry-once shape (rationale at `verify-confidence-scores.yaml:61-64`).
- **Test techniques available** (no successive-call stateful stub exists in `test_builtin_loops.py` or `test_autodev_loop.py`): extract the real state `action` from the loaded YAML and run it under `bash -c` against a static stub `ll-issues` on `PATH` (`test_builtin_loops.py:1989-2008`, `:7753-7770`; `test_autodev_loop.py:644-688`); persist state across repeated invocations through run-dir files (`_run_counter_state` at `test_builtin_loops.py:1894-1901`); CLI contract tests in a temp `.issues/` (`test_ll_issues_check_verify_verdict.py`, which pins fail-open at `test_absent_field_exits_zero_fail_open`, line 86, and will need updating if absence stops passing); structural routing assertions (`test_builtin_loops.py:1489-1507` cover the oracle's routing but not pre-existing scores).

## Implementation Steps

1. Choose the freshness mechanism
2. Apply it to `check_verify_verdict` (default mode) and `verify-confidence-scores`
3. Route `rerun_confidence_*` `on_error` to a retry/infra path, not score checks
   > ⚠ Superseded — autodev never uses the scores oracle; see § Codebase Research Findings under Integration Map
4. Regression tests: failed verify with an old `VALID`; no-op confidence-check with old scores

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_ll_issues_check_verify_verdict.py` — flip/replace `test_absent_field_exits_zero_fail_open` if absence stops passing
- Update `scripts/tests/test_builtin_loops.py` — routing assertions at `verify_issue`/`check_verify_verdict`/oracle if `on_error` routes change; add stateful regression cases modeled on the `reuses_fresh_verify_verdict` tests
- Update `docs/reference/CLI.md` and `docs/guides/LOOPS_REFERENCE.md` — restate the gate contract (fail-open wording)
- Update the `check-verify-verdict` help line in `scripts/little_loops/cli/issues/__init__.py`
- If `commands/verify-issues.md` or `skills/confidence-check/SKILL.md` change, run `ll-adapt --host <gemini|kimi-code|qwen> --apply` to refresh the mirrors

## Impact

- **Priority**: P2. Old scores come from real earlier runs, so this is not fabrication, but
  post-repair content goes unverified.
- **Effort**: Medium
- **Risk**: Medium. A stricter gate raises deferral rates.

## Acceptance Criteria

- [ ] A verify call that errors cannot pass on a verdict from a prior run
- [ ] A confidence-check that writes nothing cannot pass on pre-existing scores
- [ ] Session Log appends do not invalidate cached evidence

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-09-25T01:11:23 - `283a56a1-35bd-43bb-b2f7-64d9f104c2c4.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:06:50 - `42a934e3-5df9-4ac6-9296-d0ced0bc2261.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:19 - `4b76ee9e-e590-41ab-940d-a6df6f1554bd.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:31 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **File**: `scripts/little_loops/cli/issues/check_verify_verdict.py`, `cmd_check_verify_verdict` — default mode passes on `verdict is None or str(verdict).upper() == "VALID"`; it reads only frontmatter (`parse_frontmatter(path.read_text(), coerce_types=True)`), with no timestamp, hash or nonce input, so it cannot distinguish a current verdict from one about earlier content.
- **Routing that feeds it stale state** (`scripts/little_loops/loops/refine-to-ready-issue.yaml`): `verify_issue` has `next: check_verify_verdict` and `on_error: check_verify_verdict` (comment: "verification failure is non-fatal, like wire_issue"); `check_verify_verdict` itself has `on_error: check_hedges`, i.e. an erroring probe also proceeds.
- **Scores** (`scripts/little_loops/loops/oracles/verify-confidence-scores.yaml`): `verify_scores_persisted` and `verify_scores_persisted_final` run identical Python and fail only if `d.get('confidence') is None or d.get('outcome') is None`. Because presence passes, `retry_confidence_check` is reachable only when scores are absent — with stale scores present the retry path is never taken.
- **Writers carry no binding**: `verify_verdict` is written only by the model via Edit in `commands/verify-issues.md` § "2.5. Check Mode Behavior (--check)" (values `VALID`, `EVIDENCE_UNVERIFIED`, `PROPOSAL_UNSOUND`, `NON_VALID`); there is no Python writer. Scores are written by `ll-issues set-scores` (`cli/issues/set_scores.py:cmd_set_scores`, via `update_frontmatter`) from `skills/confidence-check/SKILL.md` Phase 4.

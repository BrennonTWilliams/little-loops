---
id: ENH-3604
type: ENH
title: Adopt ll-issues next-obligation inside refine-to-ready-issue and settle next-action
  delegation
priority: P3
status: open
verify_verdict: VALID
discovered_by: ll-issues-create
discovered_date: '2026-09-26'
captured_at: '2026-09-26T01:51:59Z'
parent: EPIC-3565
blocked_by: []
relates_to:
- ENH-3577
- ENH-3599
- ENH-3608
- ENH-3610
- ENH-3601
confidence_score: 95
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3604: Adopt ll-issues next-obligation inside refine-to-ready-issue and settle next-action delegation

## Summary

Adopt `ll-issues next-obligation` (FEAT-3598) inside `refine-to-ready-issue.yaml`,
replacing the child's bespoke inline predicates with one `route:` dispatch where
the mapping is 1:1, and decide how `ll-issues next-action` relates to the selector.
Split out of FEAT-3598 during its 2026-09-25 review; FEAT-3598 ships the selector only.

## Current Behavior

`refine-to-ready-issue.yaml` evaluates each preparation gate in its own state, several
with bespoke inline Python: `check_placeholders` re-derives `placeholder_count` shell-side
from `format-check --format json`; `check_readiness` / `check_outcome` /
`check_scores_from_file` run heredoc `ll-issues show --json` comparisons against the
seeded `${context.readiness_threshold}` / `${context.outcome_threshold}` (BUG-3552).
`ll-issues next-action` keeps its own per-issue checks (`is_formatted`, session-log
`/ll:verify-issues` presence, threshold read of `commands.confidence_gate`), which differ
from the selector's on every token.

## Expected Behavior

The child's pre-score chain and score predicates route on
`ll-issues next-obligation ID --format token` output, with behaviour identical to today
on every existing routing test, except the three deliberate divergences recorded under
Proposed Solution > Codebase Research Findings > Accepted behavior changes.
The selector's HEDGES probe first gains the unresolved-options check that
`check-open-questions` already applies, so the dispatch does not drop it (see the HEDGES
parity decision). `next-action`'s output tokens and exit codes are unchanged.

## Motivation

Removes the copied readiness predicates FEAT-3598 was created to consolidate (Step B of
ENH-3577), so the child, ENH-3599 and ENH-3601 share one ordering instead of drifting.

## Proposed Solution

Constraints found in the FEAT-3598 review (verified against the child YAML 2026-09-25):

- **FORMAT is not adoptable.** `precheck_format` and `normalize_structure` run
  `format-check --fix --apply` (writes) and bump the one-shot
  `refine-to-ready-format-fallback` counter; the selector is read-only.
  `test_format_probe_routing.py` parametrizes over both states and executes their
  actions. Keep both states.
- **DECISION gains nothing.** `check_decision_needed` / `check_decision_mid_refine` /
  `check_decision_mid_wire` are already one-line `ll-issues check-flag ... decision_needed`.
- **Adoption targets:** the pre-score chain `check_verify_verdict` →
  `check_evidence_unverified` / `check_proposal_unsound` / `check_directive_drift` →
  `check_hedges` → `check_placeholders` → `check_ac_automatable` → `check_design`, and the
  inline heredoc predicates in `check_readiness` / `check_outcome` / `check_scores_from_file`.
- **Done-path states.** The run record is written by `write_done_record` (reached via
  `check_decision_before_done`, ENH-3610), not by the gate states. `check_missing_artifacts`
  is kept and stays in `DONE_PATH_GATES`; `check_outcome` and `check_scores_from_file` are
  removed with the score dispatch and leave that tuple. `test_ready_iff_check_passed_would_pass`
  drives the run-record writer and is unaffected by the dispatch flags (dispatches omit
  `--honor-waiver`; see the recorded decision).
- **Dispatch mechanics:** one `route:` state over
  `ll-issues next-obligation ID --format token --readiness-threshold ... --outcome-threshold ... --skip ...`,
  modelled on `route_spike_verdict`. It routes to the existing budget states
  (`check_hedge_attempts`, `check_gate_refine_limit`, `check_reconcile_limit`,
  `check_verify_retries`, `check_proposal_revision_budget`, `check_refine_limit`,
  `check_decide_attempts`), never directly to repair states. Budget states that tolerate a
  soft gate record it in a per-run skip file under `${context.run_dir}` that the dispatch
  state turns into `--skip` flags.
- **Error stance:** fail-closed selector errors (exit 2) must route where today's
  fail-closed gates do (`check_verify_verdict.on_error → mark_evidence_absent_infra`;
  outcome → `diagnose`); fail-open gates keep continuing.
- **PROOF:** the selector's PROOF (`assess_proof`) departs from `check_spike_needed`
  (`spike_attempted=true` without `spike_completed` → `absent`; structured `proof` gate
  folded in). Either keep `check_spike_needed` (it also spends the `spike-runs-<ID>`
  budget) or pass `--skip PROOF` when the child's rule says don't respawn. (ENH-3599, which
  moved spike/decision repair routing into this child, is done; resolved by the tier-3
  decision below.)
- **`next-action`:** decided: no delegation (token semantics differ: format session-log
  shortcut vs `check_format_gaps`; verify session-log presence vs persisted verdict). Its
  raw-JSON threshold read is unified with `readiness_status`'s copy of the same block; see
  the recorded decision below.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

**Design decisions recorded (resolving the either/or items above; supersedes the "either ... or" wording in the Proposed Solution bullets):**

- **Decision: `next-action` takes the shared-helper route, not delegation; the helper is raw-JSON and absence-aware, and the seeder is excluded.** `readiness_status` (`cli/issues/check_readiness.py:113-127`) already holds a raw `.ll/ll-config.json` `commands.confidence_gate` read that is the same block `cmd_next_action` (`next_action.py:33-44`) copies: each key is read per-key, the caller-supplied default applies only when the key is absent, and any read/parse failure falls back to both defaults; explicit overrides are layered on afterwards by `readiness_status` only. `readiness_status` also reads `enabled` (default `False`) inside the same `try` block, with the same all-or-nothing fallback. `seed_confidence_thresholds` (`context_seed.py:46-72`) resolves through `BRConfig.commands.confidence_gate`, whose `ConfidenceGateConfig` always populates non-`None` 85/65 (so a partial or absent block resolves to 85/65 and `ll.local.md` overrides merge in), and only fills context keys that are absent. Those semantics differ and are not unified. Named surface: `resolve_confidence_thresholds(config_path: Path, defaults: tuple[int, int]) -> tuple[int, int, bool]` in `little_loops/cli/issues/check_readiness.py` (returning `(readiness, outcome, enabled)`), called by `readiness_status` (defaults = its `default_readiness`/`default_outcome` params, overrides layered after the call, `enabled` consumed) and by `cmd_next_action` (defaults = its argparse values, `enabled` ignored), which imports it from `check_readiness`. It does **not** live in `fsm/context_seed.py`: importing `little_loops.fsm.context_seed` executes `little_loops/fsm/__init__.py` (executor, evaluators, validation), a heavy import and cycle risk on a path the selector's SCORES probe hits every call. The seeder keeps its `BRConfig` path (Scope Boundaries). The delegation branch is dropped.
  - Constraint: the helper's per-key result must equal today's for each caller across {absent file, malformed JSON, partial block, full block, explicit argparse/default values}: partial block keeps the argparse/default value for the missing key (not 85/65 unless that is the default), and `enabled` falls back to `False` exactly when both thresholds fall back. A parametrized test over `cmd_next_action` and `readiness_status` pins this. The `malformed JSON` and `absent file` rows exercise the helper directly with a temp `config_path` (a `BRConfig` is never re-parsed).
  - Constraint: `next-action` output tokens and exit codes stay identical; `test_next_action.py` is the golden-output guard and must pass unmodified. `seed_confidence_thresholds` behavior is untouched and its existing tests must keep passing.
- **Decision: two dispatch states, not one.** `select_next_obligation` runs pre-score tier 1, scores (tier 2) and low-outcome tier 3 in a single call, and `confidence_check` (which clears scores first) sits between the pre-score chain and the score predicates. A single dispatch on either side of it would read stale/cleared scores or re-run every pre-score gate.
  - **State names (pinned so tables, tests and the interpolation baseline can reference them):** `route_pre_score_obligation` (pre-score dispatch), `route_score_obligation` (score dispatch) and `record_hedge_skip` (skip-file writer). Both dispatches are `evaluate: {type: classify}` states with a `route:` table modelled on `route_spike_verdict`, and each carries a `capture:` named after its state (`capture: route_pre_score_obligation` / `capture: route_score_obligation`).
  - **Terminal-path capture retargeting:** three states read the removed captures and must move to `captured.route_score_obligation` in lockstep: `diagnose`'s prompt evidence list (the `check_outcome:` / `check_scores_from_file:` stderr lines, yaml ~1464/1469), `write_failure_evidence` (the exit-code and `failure_type` printf lines, ~1528-1568) and `classify_terminal`'s exit-code and `failure_type` loops (~1634-1653). In each, the two old references collapse to one `route_score_obligation` reference, and its `# ll-lint: mr11-ok(...)` markers replace the two old ones (the `MR11_MARKER_ALLOWLIST` tuples in `test_builtin_loops.py` move with them). Failure mode if missed: a selector killed during the score dispatch (exit 143/137/124, or `failure_type` transient) routes `_` -> `diagnose` -> `classify_terminal`, which then finds no populated capture and ledgers the run `quality` instead of `infra`. The pre-score dispatch needs no terminal-path entry: its `_`/`_error` route goes straight to `mark_evidence_absent_infra`, which writes its own class.
  - **Pre-score dispatch** `route_pre_score_obligation` (replaces `check_verify_verdict` through `check_design`; entered from `verify_issue`'s `next`/`on_error`): always passes `--skip FORMAT` (the kept `normalize_structure`/`precheck_format` states own FORMAT and their one-shot `refine-to-ready-format-fallback` counter; residual directive gaps must not produce an unrouted `FORMAT` token) and `--skip SCORES` (returns `NONE` at tier 2 and never reaches tier 3), plus any obligation recorded in the per-run skip file.
  - **Score dispatch** `route_score_obligation` (replaces `check_readiness` + `check_outcome` + `check_scores_from_file`; entered from `confidence_check.on_success`): passes explicit `--readiness-threshold`/`--outcome-threshold` from the seeded `${context.readiness_threshold}` / `${context.outcome_threshold}` and skips every tier-1 obligation plus `DECISION`, `PROOF` and `ARTIFACTS`, so its only possible tokens are `NONE`, `SCORES:absent`, `SCORES:readiness_below`, `SCORES:outcome_below`.
- **Token-to-state routing table (pre-score dispatch):**

  | Token | Routes to | Replaces today's path |
  |---|---|---|
  | `NONE` | `confidence_check` | `check_design.on_yes` |
  | `VERIFY:absent` | `check_verify_retries` | `check_verify_verdict.on_cannot_judge` (exit 3) |
  | `VERIFY:PROPOSAL_UNSOUND` | `check_proposal_revision_budget` | `check_proposal_unsound.on_yes` |
  | `VERIFY:DIRECTIVE_DRIFT` | `check_reconcile_limit` | `check_directive_drift.on_yes` |
  | `VERIFY:EVIDENCE_UNVERIFIED`, `VERIFY:other` | `check_gate_refine_limit` | advisory fall-through `check_evidence_unverified` -> `check_proposal_unsound` -> `check_directive_drift` -> `check_gate_refine_limit` |
  | `HEDGES` | `check_hedge_attempts` | `check_hedges.on_no` |
  | `PLACEHOLDERS` | `check_gate_refine_limit` | `check_placeholders.on_no` |
  | `ACCEPTANCE_CRITERIA` | `check_reconcile_limit` | `check_ac_automatable.on_no` |
  | `DESIGN` | `check_gate_refine_limit` | `check_design.on_no` |
  | `_` (empty stdout, the selector's exit-2 path) and `_error` (executor-level failure) | `mark_evidence_absent_infra` | `check_verify_verdict.on_error` (with SCORES/tier 3 skipped, exit 2 can only be VERIFY or an unresolvable ID) |

  `VERIFY:EVIDENCE_UNVERIFIED` and `VERIFY:other` reach `check_gate_refine_limit` because `check_evidence_unverified` is advisory (all three of its edges lead to `check_proposal_unsound`) and the `check_proposal_unsound` / `check_directive_drift` `on_no`/`on_error` edges lead on to `check_gate_refine_limit`; `VERIFY:absent` reaches `check_verify_retries` (exit 3 today). A test over the classification tokens `classify_verify_verdict()` can return pins this fall-through order.

- **Token-to-state routing table (score dispatch):**

  | Token | Routes to | Replaces today's path |
  |---|---|---|
  | `NONE` | `check_decision_before_done` | `check_outcome.on_yes` (ENH-3610 decision gate on the done path is kept) |
  | `SCORES:readiness_below`, `SCORES:absent` | `check_refine_limit` | `check_readiness.on_no` (absent confidence reads as 0 today); `SCORES:absent` with outcome-only absence is a recorded divergence, see Accepted behavior changes |
  | `SCORES:outcome_below` | `check_decision_needed` | `check_outcome.on_no` |
  | `_` (empty stdout, the selector's exit-2 path) and `_error` | `diagnose` | `check_readiness.on_error` -> `check_scores_from_file` -> `diagnose` (the fallback's re-read is dropped, see Accepted behavior changes) |

  `check_scores_from_file` is removed with `check_readiness` / `check_outcome`. Its `on_yes`/`on_no` pins in `test_builtin_loops.py` and its `DONE_PATH_GATES` entry move in lockstep.
- **Dispatch exit-code mechanics:** `evaluate_classify` (`fsm/evaluators.py`) reads only stdout; `cmd_next_obligation` writes its exit-2 error to stderr and leaves stdout empty, so the verdict is `""`, which resolves to the `_` route default, not `_error`. Both tables therefore map `_` and `_error` identically; the routing test asserts both keys exist and asserts the empty-output case reaches the infra/diagnose target. A second test enumerates every `Obligation` member that the dispatch's skip set does not exclude and asserts each token is a table key, so a token leaking despite the skips (drift between the selector and the loop) fails a test instead of silently routing to the infra state.
- **Accepted behavior changes (deliberate; the only divergences from today's routing):**
  1. Outcome-only-absent scores (confidence >= readiness, `outcome_confidence` unset) route via `SCORES:absent` to `check_refine_limit` instead of reading outcome as 0 and reaching `check_decision_needed`. After `confidence_check` clears and rewrites scores, an unset outcome is a scoring fault, not a low outcome, and the selector's `SCORES:absent` does not distinguish confidence from outcome absence.
  2. A failed `ll-issues show` read routes straight to `diagnose` instead of first retrying through `check_scores_from_file`; the fallback's `on_no -> breakdown_issue` edge (outcome-only failure triggers scope reduction) is dropped, because a failed read is now an infra fault and low scores route through `SCORES:*` tokens.
  3. `NONE` on the score dispatch requires both scores at threshold, where the fallback passed a combined check only on the failed-read path; the main chain already required both, so this matches the primary path.
  Routing tests that pinned the removed edges (`test_check_readiness_on_*`, `test_check_scores_from_file_state_exists`) are rewritten against the dispatch, not merely renamed.
- **Decision: tier-3 stays in the child (`--skip DECISION --skip PROOF --skip ARTIFACTS` on the score dispatch).** `check_decision_needed` -> `check_spike_needed` -> `check_missing_artifacts` keep their current order and states. `check_spike_needed` owns the per-issue `spike-runs-<ID>` counter shared with autodev and the rule `spike_needed AND NOT spike_attempted`; the selector's `assess_proof` ignores `spike_needed` entirely, so neither delegating to it nor mixing it in preserves the routing pinned by `test_spike_verdict_routing.py`. ENH-3599 (spike/decision repair routing into this child) is done; moving tier-3 into the selector is out of scope here and would need its own issue.
- **Decision: omit `--honor-waiver` on both dispatches.** The child's `check_outcome` / `check_scores_from_file` never consult `outcome_gate_waived`; only the run-record `ready` computation and `check-readiness --honor-waiver` do. Passing the flag would route a waived outcome shortfall to `NONE` -> `done` where the child today routes it to `check_decision_needed`. `test_ready_iff_check_passed_would_pass` drives the run-record writer directly and does not depend on the dispatch flags.
- **Decision: the skip file exists only for HEDGES.** Only the hedge gate is a genuine skip-and-proceed. The YAML has four exhaustion/fail-open edges from the hedge sub-chain into `check_placeholders`: `check_hedge_attempts.on_no` (2nd red reading), `check_hedge_attempts.on_error` (fail-open counter), `check_hedge_refine_limit.on_no` (refine budget spent) and `check_hedge_refine_limit.on_error` (fail-open). All four are hedge-skip edges and retarget to `record_hedge_skip`. `check_hedges.on_error` is a probe failure, not an exhaustion: the selector swallows fail-open HEDGES probe errors internally, so that edge disappears with `check_hedges`. Exhausted VERIFY / PLACEHOLDERS / DESIGN / ACCEPTANCE_CRITERIA budgets terminate through `record_gate_unmet` / `mark_evidence_absent_infra` and are not skips. Protocol: file `${context.run_dir}/refine-to-ready-skip-obligations`, one obligation name per line, appended by `record_hedge_skip`, which then re-enters `route_pre_score_obligation`, and re-expanded into `--skip` flags on every entry to that dispatch. The per-issue reset is load-bearing, not optional: autodev reuses one `run_dir` across issues (yaml:548), so a skip file left by one issue would silently skip HEDGES for the next. It is reset by a new `rm -f ${context.run_dir}/refine-to-ready-skip-obligations` line in `resolve_issue`'s `action`, placed beside the existing `rm -f ... refine-to-ready-proposal-revision` line (that state resets counters one line at a time, so the reset is its own `&&` clause). Ordering consequence: after a hedge skip, the re-entered dispatch re-runs tier 1 from VERIFY onward (today the chain continues at `check_placeholders`); the re-read is read-only (the persisted verdict is not regenerated) and the earlier gates were already green, so the result matches; fail-closed VERIFY probing is repeated once per skip. Bash `${...}` in the flag-building shell must be escaped `$${...}` (interpolation runs over the whole action string before bash).
- **Decision: fix the selector's HEDGES probe in this issue (scope exception to "no change to FEAT-3598's selector semantics").** `check_hedges` runs `ll-issues check-open-questions`, which exits 1 when `locate_unresolved_options(content)` **or** `count_open_questions_in_sections(content)` is non-zero (`cli/issues/check_open_questions.py:59-64`). The selector's HEDGES branch in `_tier1_probe` (`cli/issues/next_obligation.py:244-248`) counts only open questions. Adopting it unchanged would stop forcing a refine for an issue that still carries an unresolved option set (e.g. Option A / Option B with no selection), and no existing routing test would notice. Fix: the HEDGES probe also calls `locate_unresolved_options(content)` and reports unmet when either count is non-zero, with evidence `open_questions=N` and `unresolved_options=M` (in '<heading>'). This makes the selector match the gate it claims to mirror, so other next-obligation consumers move toward child parity too. The other tier-1 probes were checked and already share their gate CLI's predicate: ACCEPTANCE_CRITERIA (`_find_manual_criteria`), DESIGN (`check_format_gaps` + `design_gate_failed`), PLACEHOLDERS (`placeholder_count`, the accessor behind `FormatGaps.template_placeholders`).
  - Guard: a parity test in `scripts/tests/test_ll_issues_next_obligation.py` runs each tier-1 gate CLI (`check-open-questions`, `check-acceptance-criteria`, `check-design`, and the `format-check --format json` placeholder count) and `select_next_obligation` over the same fixtures and asserts unmet-vs-met agrees. Fixtures include: unresolved options with zero open questions (HEDGES unmet), open questions with zero options, a manual AC, a missing Program Design section, a leftover template placeholder, and a clean issue.
- **Error stance detail:** fail-open tier-1 probes (HEDGES, PLACEHOLDERS, ACCEPTANCE_CRITERIA, DESIGN) are swallowed inside the selector and appear only in `probe_errors` on the text/json formats, never in `--format token`; the child's fail-open gates likewise continue silently, so behaviour is preserved and no observability is lost that exists today.

### Behavior Parity

Eleven gate states in `refine-to-ready-issue.yaml` are replaced by two dispatch states. Parity contract:

- **Preserved:** every routing edge in the two token-to-state tables, the fail-closed/fail-open error stance per gate, each budget state's counter and target, the HEDGES skip-and-proceed after the second red reading, the ENH-3610 decision gate on the done path, and the run-record write in `write_done_record`. The terminal classification of a killed or transient-failed score read stays `infra` via the retargeted `route_score_obligation` capture.
- **Preserved by a selector fix:** HEDGES covers unresolved options, as `check-open-questions` does (HEDGES parity decision).
- **Deliberately changed:** the three items under Accepted behavior changes, plus one ordering change: after a hedge skip, tier 1 is re-read from VERIFY instead of continuing at PLACEHOLDERS (read-only re-read, same result).
- **Guarded by:** the two routing-table test classes and the token-completeness test, the skip-file test, the tier-1 parity test, `test_format_probe_routing.py`, `test_spike_verdict_routing.py`, `test_run_record.py`, and the `classify_terminal` capture test.

## Integration Map

Carried over from FEAT-3598's wiring passes (see that issue for per-line citations).

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`: dispatch states, skip file, terminal-path capture retargeting, and the file-header routing summary and step-budget comments (lines ~4-120), which narrate the removed states. `max_steps: 90` is kept: the chain gets shorter, and a hedge skip adds only `record_hedge_skip` plus one re-dispatch.
- `scripts/little_loops/cli/issues/check_readiness.py` (adds `resolve_confidence_thresholds`; `readiness_status` calls it)
- `scripts/little_loops/cli/issues/next_action.py` (calls `resolve_confidence_thresholds`, imported from `check_readiness`)
- `scripts/little_loops/cli/issues/next_obligation.py`: HEDGES probe gains `locate_unresolved_options` (see the HEDGES parity decision). Module docstring lines 4 and 11 drop the stale `check_outcome.on_yes = done` wording (ENH-3610 moved that edge to `check_decision_before_done`) and name the dispatch states instead.
- `scripts/little_loops/fsm/context_seed.py` is **not** modified.
- Out of scope: `.claude/workflows/refine-to-ready.js` (gitignored, machine-local, untested mirror; see Integration Map findings)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml` — embeds the child (`refine_current`)
- `scripts/little_loops/loops/issue-refinement.yaml`, `scripts/little_loops/loops/recursive-refine.yaml` — delegate into the child and consume `next-action` tokens
- `scripts/little_loops/loops/lib/cli.yaml` — `ll_issues_next` / `ll_issues_next_issue` fragments (unchanged token contract)
- `scripts/little_loops/cli/issues/refine_status.py` — mirrors next-action's predicate inputs
- `scripts/little_loops/fsm/context_seed.py` — `seed_confidence_thresholds` (unchanged; called from `cli/loop/run.py`, `cli/loop/lifecycle.py`, `cli/loop/info.py`, `fsm/executor.py`)
- `ll-issues next-obligation` consumers outside this child pick up the stricter HEDGES probe; re-run their tests (`test_ll_issues_next_obligation.py` plus any loop that shells out to `next-obligation`, found with `grep -rn "next-obligation" scripts/little_loops/loops/`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/auto-refine-and-implement.yaml`, `scripts/little_loops/loops/rn-remediate.yaml` — reference `refine-to-ready-issue` / its gate states; confirm state-name and route contracts survive the rewiring [Agent 1 finding]
- `scripts/little_loops/loops/oracles/resolve-decision.yaml`, `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml` — reference the child's gate states/scores predicates; check for renamed-state coupling [Agent 1 finding]
- `scripts/little_loops/fsm/validation/reachability.py` — reachability checks over the child's states; new dispatch state must keep every budget state reachable [Agent 1 finding]
- `scripts/little_loops/run_record.py`, `scripts/little_loops/cli/issues/run_record.py` — run-record writers invoked by done-path gate states that must be kept [Agent 2 finding]
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — persisted-verdict probe shared with the selector's VERIFY obligation (exit-2 fail-closed contract) [Agent 2 finding]

### Tests
- `scripts/tests/test_builtin_loops.py` — TestRefineToReadyIssueSubLoop routing tests for every replaced state; `check_readiness.on_error == check_scores_from_file` pins; `MR11_MARKER_ALLOWLIST` refine tuples (move in lockstep with `# ll-lint: mr11-ok(...)` markers); `test_context_fallbacks_match_selector_defaults`; `TestInterpSweepBaseline::test_completeness_guard`
- `scripts/tests/data/loop_interpolation_baseline.json` — three refine entries (`check_outcome`, `check_readiness`, `check_scores_from_file`); baseline any new dispatch state
- `scripts/tests/test_run_record.py` — `DONE_PATH_GATES`, RC-guard ordering, `TestTerminalExecution`, `test_ready_iff_check_passed_would_pass`
- `scripts/tests/test_format_probe_routing.py` — executes `normalize_structure` / `precheck_format` actions (keep both states)
- `scripts/tests/test_spike_verdict_routing.py` — child spike/decision route table
- `scripts/tests/test_next_action.py` (golden output), `scripts/tests/test_fsm_fragments.py`, `scripts/tests/test_issue_refinement_broke_down.py`, `scripts/tests/test_issue_parser.py` (`next_action:30` anchor)
- _Wiring pass added by `/ll:wire-issue`:_ `scripts/tests/test_autodev_decision_gate.py`, `scripts/tests/test_fsm_executor.py`, `scripts/tests/test_learning_tests_gate.py`, `scripts/tests/test_ll_issues_next_obligation.py`, `scripts/tests/test_ll_issues_check_verify_verdict.py` — reference the child's gate states or selector tokens; re-run after rewiring [Agent 3 finding]
- _Coupling triage (name collisions vs real coupling):_ **Coupled** — `test_builtin_loops.py`, `test_run_record.py`, `test_autodev_decision_gate.py`, `test_ll_issues_check_verify_verdict.py` (child-scoped removed-state assertions), and `test_enh3250_verify_issues_proposal_vs_code.py` (its assertion message names `check_proposal_unsound`; re-read it and update the message/target if it greps the child's YAML for that state). **Name collisions, out of scope:** `test_autodev_loop.py` (`check_readiness_for_atomic_remediation`, `check_design` via `recheck_scores`), `test_rn_remediate.py` (`rn-remediate.yaml` has its own `check_readiness`/`check_outcome` states), `test_rn_implement.py` (`check_readiness` in its own state list), `scripts/little_loops/cli/issues/__init__.py` (`check_design`/`check_readiness` CLI subcommands), `issue_parser.py`, `issue_manager.py` and `test_issue_parser_unresolved.py` (comments/prose or the `readiness_status` function, not child state names). A removed-state grep must be scoped to `refine-to-ready-issue.yaml` and the child-scoped tests, never repo-wide.
- Corpus gates: `scripts/tests/test_builtin_loop_interpolation.py` (escape bash `${...}` as `$${...}`), `test_fsm_fragments.py::test_builtin_loops_load_after_migration`, MR-14 sweep in `scripts/tests/test_fsm_schema.py`

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — refine-to-ready gate-chain narrative, ASCII diagrams, fragment table rows
- `docs/reference/CLI.md` — state-name prose (check-flag consumers, run-record callers, `--proposal-unsound` / `--directive-drift`, check-readiness FSM-loop-use note)
- `docs/reference/DEFERRAL_CODES.md` — `spike_inconclusive` / `proposal_unsound` source states
- `commands/verify-issues.md` — persisted-verdict contract names `check_verify_verdict` / `check_proposal_unsound` (host mirrors via `ll-adapt`)
- `scripts/little_loops/loops/README.md` — child catalog rows
- _Wiring pass added by `/ll:wire-issue`:_ `docs/reference/API.md` (`next-action` row ~line 4639, `resolve_confidence_thresholds` under `little_loops.cli.issues.check_readiness`), `docs/reference/CONFIGURATION.md` and `skills/configure/areas.md` (`commands.confidence_gate` threshold resolution) [Agent 2 finding]
- `docs/reference/CLI.md` `next-obligation` entry: HEDGES now also covers unresolved options

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- **Correction, `.claude/workflows/refine-to-ready.js`:** gitignored (`.gitignore:185`, `.claude/workflows/`), never tracked, and not tied to the YAML by any gate. Its only test coupling is `test_run_record.py` (`MIRROR`), whose test is `skipif(not MIRROR.exists())` and concerns only the Finalize-phase run-record mirror, which this issue does not change. Treat it as out of scope and unverified; it is not an acceptance target.
- **Correction, done-path gates:** `check_outcome`, `check_scores_from_file` and `check_missing_artifacts` no longer write the run record (ENH-3610). `write_done_record` does, reached via `check_decision_before_done`; `test_run_record.py::test_done_path_gate_writes_no_record` pins `DONE_PATH_GATES = ("check_outcome", "check_scores_from_file", "check_missing_artifacts")` to `on_yes == "check_decision_before_done"` and no `run-record write` in the action. Removing `check_outcome` / `check_scores_from_file` requires that tuple to change in lockstep; `check_missing_artifacts` is kept.
- **Correction, `check_verify_verdict.py` exit codes:** the child gate handles 0 (VALID), 1 (NON_VALID) and 3 (ABSENT), with `on_error: mark_evidence_absent_infra`; the module returns 2 only for an unresolvable ID. The selector's exit-2 contract belongs to `cmd_next_obligation` / `ObligationProbeError` (`cli/issues/next_obligation.py`), not to `check_verify_verdict.py`. `classify_verify_verdict()` is the shared pure helper both use, returning `absent`, `VALID`, `EVIDENCE_UNVERIFIED`, `PROPOSAL_UNSOUND`, `DIRECTIVE_DRIFT` or `other`.
- **Correction, score-pass edge:** `check_outcome.on_yes` is `check_decision_before_done` (ENH-3610), not `done`; a passing-scores `NONE` from the selector must therefore still route through that decision gate (see the routing tables under Proposed Solution).
- **States removed by the adoption** (routing tests asserting them by name and edge move or are deleted in lockstep): `check_verify_verdict`, `check_evidence_unverified`, `check_proposal_unsound`, `check_directive_drift`, `check_hedges`, `check_placeholders`, `check_ac_automatable`, `check_design`, `check_readiness`, `check_outcome`, `check_scores_from_file`. **States kept:** `clear_verify_verdict`, `verify_issue`, `check_verify_retries`, `check_proposal_revision_budget` and the proposal-revision chain, `check_hedge_attempts`, `check_hedge_refine_limit`, `check_reconcile_limit`, `check_gate_refine_limit`, `check_refine_limit`, `check_decision_before_done`, `write_done_record`, `check_decision_needed`, `check_decide_attempts`, `check_spike_needed`, `run_spike`, `route_spike_verdict`, `check_missing_artifacts`, `normalize_structure`, `precheck_format`. Existing tests naming removed states (`test_builtin_loops.py` `TestRefineToReadyIssueSubLoop` `test_check_readiness_on_*` / `test_check_scores_from_file_state_exists`, `test_ll_issues_check_verify_verdict.py` `--proposal-unsound` / `--directive-drift` consumers, `test_autodev_decision_gate.py`, reachability tests) are rewritten against the dispatch states, not merely renamed. `check-verify-verdict --proposal-unsound` / `--directive-drift` / `--evidence-unverified` remain CLI features consumed elsewhere; only their use in this child ends.
- **Mirror/doc gates that fire on this change:** `ll-adapt --host <gemini|kimi-code|qwen> --apply` after editing `commands/verify-issues.md`; `command cp -f README.md scripts/README.md` if `README.md` is touched; `scripts/tests/test_docs_audience_gate.py` for edits under `docs/guides/`, `docs/reference/`, `skills/`, `commands/`; `scripts/little_loops/loops/README.md` child-catalog rows. New states must be added to `scripts/tests/data/loop_interpolation_baseline.json` when they interpolate.

## Program Design

### Types

- No new Python types. Consumes `Obligation` / `ObligationResult` from FEAT-3598.

### Signatures

- `seed_confidence_thresholds(context: dict[str, Any], config: Any = None) -> None` — existing seeder in `fsm/context_seed.py`; unchanged (BRConfig-based)
- `resolve_confidence_thresholds(config_path: Path, defaults: tuple[int, int]) -> tuple[int, int, bool]` — new, in `cli/issues/check_readiness.py`; raw-JSON, per-key absence-aware read of readiness, outcome and `enabled`, shared by `cmd_next_action` and `readiness_status`
- `select_next_obligation(config: BRConfig, issue_id: str, *, skip: Iterable[Obligation] = (), readiness_override: int | None = None, outcome_override: int | None = None, honor_waiver: bool = False) -> ObligationResult | None` — existing; signature unchanged, its HEDGES probe also counts unresolved options
- `cmd_next_action(config: BRConfig, args: argparse.Namespace) -> int` — existing; output tokens and exit codes unchanged

### Call Path

- Loop: `refine-to-ready-issue` dispatch state -> `cmd_next_obligation` -> `select_next_obligation` (FEAT-3598 deliverables)
- HEDGES: `select_next_obligation` -> `count_open_questions_in_sections` and `locate_unresolved_options` (the same pair `cmd_check_open_questions` calls)
- Thresholds: `cmd_next_action` and `readiness_status` -> `resolve_confidence_thresholds`, replacing their duplicated direct `commands.confidence_gate` reads; `seed_confidence_thresholds` is not on this path

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- FEAT-3598 is `done`: `ll-issues next-obligation` exists (`cli/issues/next_obligation.py`). Its shipped surface is `ISSUE_ID`, `--format {text,json,token}`, repeatable `--skip OBLIGATION` (choices are every `Obligation` member except `NONE`), `--readiness-threshold N`, `--outcome-threshold N`, `--honor-waiver`, `--config`. Step 1's "confirm the CLI shape" is therefore already answerable. There is no remaining blocker edge (`blocked_by: []`).
- Exit contract: `cmd_next_obligation` returns 0 for any assessment (including `NONE`), and 2 for an unresolvable ID or an `ObligationProbeError` from a fail-closed probe (VERIFY, SCORES). A route table must therefore treat exit 2 as `on_error`, and every token as `on_yes`-style output matching; there is no non-zero exit for "obligation unmet".
- Token vocabulary a `route:` table must cover: `FORMAT`, `VERIFY`, `HEDGES`, `PLACEHOLDERS`, `ACCEPTANCE_CRITERIA`, `DESIGN`, `SCORES:readiness_below`, `SCORES:outcome_below`, `DECISION`, `PROOF`, `ARTIFACTS`, `NONE` (sub_reasons appear as `OBLIGATION:sub_reason` via `ObligationResult.token()`). The selector's tiers are pre-score, scores, then low-outcome diagnosis only when readiness passes and outcome is below threshold; passing scores return `NONE` even with `decision_needed`/spike flags set; the child routes that `NONE` to `check_decision_before_done` (the former `check_outcome.on_yes`, ENH-3610).
- Threshold resolution today exists in two independent forms: `cmd_next_action` (`cli/issues/next_action.py:34-44`) reads raw `.ll/ll-config.json` `commands.confidence_gate` with argparse defaults 85/65 as fallback, while `seed_confidence_thresholds` (`fsm/context_seed.py:46-72`) resolves through `BRConfig.commands.confidence_gate` and only fills keys absent from context. The selector takes explicit overrides. A third copy lives in `readiness_status` (`check_readiness.py:113-127`), identical in shape to next-action's. The shared helper covers those two raw-JSON readers and preserves their fallback-to-default behavior when the file is unreadable, which the seeder does not have.
- Constraint: dispatches omit `--honor-waiver` (see the recorded decision); a waived outcome shortfall therefore routes as `SCORES:outcome_below` to `check_decision_needed`, as the child does today.
- Constraint: `--skip` is a caller-owned stateless override, so the per-run skip file must be rebuilt into flags on every dispatch entry; a soft gate that stopped being recorded silently re-arms.

## Implementation Steps

1. FEAT-3598's CLI shape (`--format token`, `--skip`, threshold flags, exit codes) is confirmed and recorded in the Program Design findings; no action remains.
2. `route_pre_score_obligation` and the HEDGES skip file exist, and the pre-score chain routes through them to the existing budget states.
3. `route_score_obligation` replaces `check_readiness` / `check_outcome` / `check_scores_from_file`; the RC-guard and run-record behavior of the kept done-path states is unchanged.
4. `resolve_confidence_thresholds` exists and is shared by `cmd_next_action` and `readiness_status`.
5. Update routing/baseline/MR11 tests in lockstep; update the gate-chain docs.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Check `auto-refine-and-implement.yaml`, `rn-remediate.yaml` and `oracles/*.yaml` for references to renamed/removed child states
- Verify `fsm/validation/reachability.py` passes with the new dispatch state (all budget states reachable)
- Update `docs/reference/API.md`, `docs/reference/CONFIGURATION.md`, `skills/configure/areas.md` if the threshold helper is extracted
- Re-run `test_autodev_decision_gate.py`, `test_fsm_executor.py`, `test_learning_tests_gate.py`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

Outcome-phrased replacements for the superseded steps (order is forced only where stated):

0. The selector's HEDGES probe counts unresolved options as well as open questions, and the tier-1 parity test passes. Must land before step 1: step 1 removes `check_hedges`, the only gate that checks unresolved options today.
1. Pre-score dispatch exists and routes per the first token table; `verify_issue` still precedes it and `clear_verify_verdict` still precedes `verify_issue`. Verified by the new routing test class plus reachability (every kept budget state reachable).
2. HEDGES skip protocol is in place (the four hedge-skip edges retarget to `record_hedge_skip`, `resolve_issue` resets the file, dispatch rebuilds flags each entry). Must land with or before step 1's removal of `check_hedges`. Verified by the skip-file test.
3. Score dispatch exists (after `confidence_check.on_success`), `check_readiness` / `check_outcome` / `check_scores_from_file` are gone, and `NONE` still reaches `check_decision_before_done` -> `write_done_record`. `diagnose`, `write_failure_evidence` and `classify_terminal` read `captured.route_score_obligation` in place of the two removed captures. Verified by `test_run_record.py` with `DONE_PATH_GATES` reduced to the surviving `check_missing_artifacts` (the tuple at `test_run_record.py:41` changes in lockstep), plus a test that `classify_terminal`'s action references `captured.route_score_obligation.exit_code` and `.failure_type`, and no longer references `check_outcome` / `check_scores_from_file`.
4. `resolve_confidence_thresholds` exists in `cli/issues/check_readiness.py`; `cmd_next_action` and `readiness_status` both call it with unchanged per-key precedence (and `readiness_status`'s `enabled` fallback is unchanged); `seed_confidence_thresholds` and `fsm/context_seed.py` are untouched. Verified by the parametrized threshold test and an unmodified `test_next_action.py`.
5. Tests, baselines and docs move with the state changes: `loop_interpolation_baseline.json`, `MR11_MARKER_ALLOWLIST` tuples, the YAML's own header routing summary and step-budget comments, the `next_obligation.py` module docstring, docs listed under Integration Map, plus `ll-adapt --apply` for `commands/verify-issues.md`. Verified by `python -m pytest scripts/tests/` exiting 0 and `ll-loop validate` on the four loops named in Acceptance Criteria.

## Impact

- **Priority**: P3 — follow-up to FEAT-3598 under EPIC-3565
- **Effort**: Medium — loop rewiring plus a broad test/doc lockstep
- **Risk**: Medium — changes routing in a child embedded by autodev, issue-refinement and recursive-refine
- **Breaking Change**: No

## Scope Boundaries

- No change to FEAT-3598's selector semantics, with one recorded exception: the HEDGES probe gains the unresolved-options check so it matches `check-open-questions` (see the HEDGES parity decision). Any other needed change goes to FEAT-3598's surface first, in a separate issue.
- No change to `autodev.yaml`. ENH-3599, ENH-3601 and ENH-3608 are done; further selector adoption in autodev needs its own issue.
- `next-action` output tokens and exit codes stay unchanged.

## Acceptance Criteria

- [ ] The child's pre-score chain and score predicates route through `ll-issues next-obligation`; FORMAT states and the decision `check-flag` states are kept
- [ ] Every existing child routing test passes with only the documented lockstep updates (state renames, baseline entries, MR11 tuples)
- [ ] `test_run_record.py` done-path gate and ready-iff-check-readiness tests pass
- [ ] The hedge budget still lets the run proceed via `--skip HEDGES` (per-run skip file); the format fallback stays a counter in the kept `normalize_structure`/`precheck_format` states and is not `--skip`-governed
- [ ] `next-action` output unchanged; `cmd_next_action` and `readiness_status` both call `resolve_confidence_thresholds` from `check_readiness.py` (`seed_confidence_thresholds` and `fsm/context_seed.py` are not touched)
- [ ] The selector's HEDGES probe reports unmet for unresolved options with zero open questions, and a tier-1 parity test shows each gate CLI and the selector agree on shared fixtures
- [ ] `diagnose`, `write_failure_evidence` and `classify_terminal` read `captured.route_score_obligation`; no reference to `captured.check_outcome` or `captured.check_scores_from_file` remains in the child YAML
- [ ] Gate-chain docs updated, including the child YAML's own header comments and the `next_obligation.py` module docstring

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

Machine-checkable restatement of the criteria above (the list above is preserved; these name the concrete checks):

- A new routing test class in `scripts/tests/test_builtin_loops.py` asserts, for each row of the two token-to-state tables under Proposed Solution, the dispatch state's `route:` target, plus both `_` and `_error` -> `mark_evidence_absent_infra` (pre-score, dispatch `route_pre_score_obligation`) and -> `diagnose` (score, dispatch `route_score_obligation`), and a completeness test that every `Obligation` token not excluded by a dispatch's skip set is a table key.
- A test executes the dispatch actions' skip-flag construction against a temp `run_dir`: an empty skip file yields exactly `--skip FORMAT --skip SCORES`; a file containing `HEDGES` adds `--skip HEDGES`; a second entry rebuilds the flags from the file (no stale in-memory state). It also asserts the four hedge-skip edges (`check_hedge_attempts` and `check_hedge_refine_limit`, each `on_no` and `on_error`) target `record_hedge_skip`, which writes `HEDGES`, and that `resolve_issue` resets the file.
- `test_format_probe_routing.py`, `test_spike_verdict_routing.py`, `test_next_action.py` (golden output) and `test_run_record.py` (with `DONE_PATH_GATES` updated only for the removed states) pass; `python -m pytest scripts/tests/` exits 0.
- A parametrized threshold-resolution test (absent file, malformed JSON, partial block, full block, explicit argparse/default values) gives identical per-key numbers for `cmd_next_action` and `readiness_status` before and after the helper extraction; `seed_confidence_thresholds` tests are unchanged.
- Reachability (`fsm/validation/reachability.py` checks in the corpus tests), `TestInterpSweepBaseline::test_completeness_guard`, `test_context_fallbacks_match_selector_defaults`, MR11 marker-allowlist tests and `ll-loop validate` on `refine-to-ready-issue`, `autodev`, `issue-refinement` and `recursive-refine` all pass.
- Doc assertions: `docs/guides/LOOPS_REFERENCE.md` gate-chain narrative and diagrams name `route_pre_score_obligation` / `route_score_obligation` / `record_hedge_skip` rather than removed states. Machine check: a grep of the eleven removed state names (`check_verify_verdict`, `check_evidence_unverified`, `check_proposal_unsound`, `check_directive_drift`, `check_hedges`, `check_placeholders`, `check_ac_automatable`, `check_design`, `check_readiness`, `check_outcome`, `check_scores_from_file`) over `scripts/little_loops/loops/README.md` and `docs/guides/LOOPS_REFERENCE.md` returns no hit describing the refine-to-ready-issue chain. Named allowlist (legitimate hits): `docs/reference/CLI.md` `check-verify-verdict --proposal-unsound` / `--directive-drift` / `--evidence-unverified` flag documentation, the `check-readiness` / `check-design` CLI subcommand names, `rn-remediate.yaml`'s and autodev's own same-named states, and `commands/verify-issues.md`'s persisted-verdict contract (rewritten to name the dispatch state). `docs/reference/API.md` documents `resolve_confidence_thresholds`.
- Soft-gate criterion (same as the rewritten top-level criterion): only the HEDGES budget is skipped via `--skip`; the format fallback is a counter in the kept `normalize_structure`/`precheck_format` states and is not governed by `--skip`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-26 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-26_

**Readiness Score**: 95/100 -> PROCEED
**Outcome Confidence**: 71/100 -> MODERATE

### Concerns
- `.claude/workflows/refine-to-ready.js` is a gitignored machine-local file (stale_file_ref); marked out of scope, non-blocking
- Tier-3 PROOF stays in the child per decision; coordinate later moves with ENH-3599

### Outcome Risk Factors
- Moderate per-site complexity: rewiring a routing chain with shared state (skip file, budget states, RC guards) in a child embedded by autodev, issue-refinement and recursive-refine
- Broad lockstep across routing, baseline, MR11 and run-record tests; wide caller surface (5+ loops)

## Session Log
- `/ll:confidence-check` - 2026-09-26T08:23:54 - `a7e1c77c-7aac-49e2-8bc2-8597a74e3698.jsonl`
- `/ll:verify-issues` - 2026-09-26T08:20:13 - `a7e1c77c-7aac-49e2-8bc2-8597a74e3698.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-26T08:19:24 - `a7e1c77c-7aac-49e2-8bc2-8597a74e3698.jsonl`
- `/ll:confidence-check` - 2026-09-26T08:15:55 - `a7e1c77c-7aac-49e2-8bc2-8597a74e3698.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-26T08:11:48 - `a7e1c77c-7aac-49e2-8bc2-8597a74e3698.jsonl`
- `/ll:confidence-check` - 2026-09-26T08:08:05 - `a7e1c77c-7aac-49e2-8bc2-8597a74e3698.jsonl`
- `/ll:verify-issues` - 2026-09-26T08:05:37 - `a7e1c77c-7aac-49e2-8bc2-8597a74e3698.jsonl`
- `/ll:wire-issue` - 2026-09-26T08:04:33 - `a7e1c77c-7aac-49e2-8bc2-8597a74e3698.jsonl`
- `/ll:refine-issue` - 2026-09-26T08:03:33 - `a7e1c77c-7aac-49e2-8bc2-8597a74e3698.jsonl`
- `/ll:capture-issue` - 2026-09-26T01:52:07 - `f544b4eb-e137-4689-a451-49e3380df0f3.jsonl`

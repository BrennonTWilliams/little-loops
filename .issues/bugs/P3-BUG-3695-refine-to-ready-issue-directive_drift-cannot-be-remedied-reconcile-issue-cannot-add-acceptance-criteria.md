---
id: BUG-3695
type: BUG
title: 'refine-to-ready-issue DIRECTIVE_DRIFT cannot be remedied: reconcile-issue
  cannot add Acceptance Criteria'
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T17:46:29Z'
parent: EPIC-3694
blocked_by: []
relates_to:
- BUG-3708
- BUG-3691
- ENH-3690
- ENH-3718
decision_needed: false
confidence_score: 92
outcome_confidence: 69
score_complexity: 13
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 18
completed_at: '2026-10-04T01:07:53Z'
---

# BUG-3695: refine-to-ready-issue DIRECTIVE_DRIFT cannot be remedied: reconcile-issue cannot add Acceptance Criteria

> **Implementation review 2026-10-03:** the code fix already landed in `8dbd00703`, including the caller flag, B6 enumeration/persistence, real-child scripted FSM harness, non-convergence signal and docs/mirrors. Do not implement it again. This review reran the relevant repair, command, loop, dispatch and cost suites: **2120 passed, 1 skipped**. The full-suite closure gate was not rerun in this review; retain `open` for that final validation/closure, rather than claiming a fresh full-suite pass from the checked historical ACs. Live model compliance belongs to the already-captured **ENH-3718**, including its new ineligible stale-evidence case; it is not a prerequisite for this code issue's closure. The earlier review and confidence assessment below are historical.

> **Review 2026-10-03 (EPIC-3694 children review, Opus second opinion, confidence 0.7).**
>
> - **Unblocked:** BUG-3708 landed (`45481a2ba`); the "Gaps to Address" blocker in § Confidence Check Notes is resolved. Rerun `/ll:confidence-check` before implementing.
> - **Anchors are stale** (BUG-3708 added ~50 lines to `commands/verify-issues.md`; `refine-to-ready-issue.yaml` has also shifted — `check_reconcile_limit` now starts near line 797, `VERIFY:DIRECTIVE_DRIFT` route at 589). Locate by phrase: the `DIRECTIVE_DRIFT` row of the §2C verdict table, §2.5 "`DIRECTIVE_DRIFT` verdict (BUG-3574, check B6)" bullet, and the state names in the loop YAML.
> - **Split the live evaluation.** The three-run live-evaluation AC and Implementation Step 6 become a separate follow-up (capture it when the code lands) so the code ACs are not gated on three LLM runs. Scripted FSM tests still prove routing only.
> - **Distinct non-convergence signal, no budget fallback.** Keep `check_reconcile_limit` at `target: 2`, but when `DIRECTIVE_DRIFT` recurs after the flagged reconcile and the budget is exhausted, make that visible (e.g. a distinct `echo` line / run-record evidence note from `record_gate_unmet`) so incomplete B6 enumeration is distinguishable from other gate failures. Do **not** add a new `--legacy-class`: `LEGACY_CLASSES` in `run_record.py` is a closed tuple with consumers in `autodev_summary.py`, `preparation_policy.py` and `deferred_triage.py`.
> - **Stale-verdict window:** `clear_verify_verdict` runs only on the post-repair path before `verify_issue`. Reconcile reached via a non-VERIFY route (shared `ACCEPTANCE_CRITERIA`) can see an old `DIRECTIVE_DRIFT` verdict + evidence; the flag's eligibility check already requires the verdict, but add a test where a stale verdict/evidence pair is present on the `ACCEPTANCE_CRITERIA` route and the flag is absent/ignored.
> - **Evidence lifecycle with ENH-3690:** both issues write the evidence frontmatter field from different verdict branches. Per §2.5 precedence (`NON_VALID` > `EVIDENCE_UNVERIFIED` > `CLAIMS_OUTDATED` > `PROPOSAL_UNSOUND` > `DIRECTIVE_DRIFT`), a pass that returns `CLAIMS_OUTDATED` replaces the evidence with claim items and drops the drift list until the next pass; pin that `--from-evidence` (correct_claims) and `arm_proposal_revision` can never consume drift evidence (they route only on their own verdicts).

## Summary

`refine-to-ready-issue` routes a `DIRECTIVE_DRIFT` verify verdict to `reconcile_issue`, but `/ll:reconcile-issue` is forbidden from adding Acceptance Criteria, so the one remedy the verdict promises cannot clear the finding. The loop then exhausts its budgets and ends `GATE_UNMET`, even though the fix is small and fully specified by the verify finding.

## Current Behavior

Observed in run `refine-to-ready-issue-20261002T111524` on ENH-3678 (history run `2026-10-02T171524-refine-to-ready-issue`, 33 iterations, 24m39s, `failed`):

1. `verify_issue` returned `DIRECTIVE_DRIFT` on iterations 14, 20 and 29. Every claim about current code held; the only finding was a check B6 AC-coverage gap — the Integration Map lists a `ll-doctor` "rebuild pending" surface (`cli/doctor.py`) with no Acceptance Criterion. Later passes added further uncovered points: notice suppression on the automation-pruning path, the replay-duration measurement, and the `session_store/__init__.py` re-export.
2. the `DIRECTIVE_DRIFT` row of `commands/verify-issues.md`'s §2C verdict table (was `:263`) defines `DIRECTIVE_DRIFT` as "remedied by `reconcile-issue`", and the loop routes `VERIFY:DIRECTIVE_DRIFT` -> `check_reconcile_limit` -> `reconcile_issue` (`refine-to-ready-issue.yaml`, `"VERIFY:DIRECTIVE_DRIFT"` route entry).
3. `reconcile_issue` ran once (iteration 17) and reported `RECONCILED` with "Acceptance Criteria: unchanged". Its CONCERNS said adding the AC "would be a new requirement rather than a correction". That follows `commands/reconcile-issue.md:120`: "do not invent new requirements" — it only rewrites directive text contradicted by the issue's own findings.
4. `check_reconcile_limit` (counter increments on every entry, `target: 2`) allows one reconcile per run. The second `DIRECTIVE_DRIFT` fell to `check_gate_refine_limit` -> `refine_followup`, which is research-only and additive (`commands/refine-issue.md` §5c) and cannot add ACs; it appended more findings instead.
5. The third `DIRECTIVE_DRIFT` found both budgets exhausted -> `record_gate_unmet` -> `failed`.

This is a contract mismatch: a coverage gap (missing AC) is not a contradiction, so neither remedy state can fix it. Sibling of BUG-3574 (`PROPOSAL_UNSOUND` routed to reconcile, which cannot edit Proposed Solution) and ENH-3690 (`NON_VALID` citation-only findings have no repair route).

## Steps to Reproduce

1. Take an issue whose Integration Map lists a surface (e.g. `cli/doctor.py`) that no Acceptance Criterion covers, and whose code claims are otherwise accurate (ENH-3678 at the time of the observed run).
2. Run `ll-loop run refine-to-ready-issue ENH-3678`.
3. Observe `verify_issue` return `DIRECTIVE_DRIFT` (check B6 AC-coverage gap) and route to `check_reconcile_limit` -> `reconcile_issue`.
4. Observe `reconcile_issue` report `RECONCILED` with "Acceptance Criteria: unchanged", then `refine_followup` append findings without adding ACs.
5. Observe the loop exhaust both budgets and end `GATE_UNMET` via `record_gate_unmet` (`failed`).

## Expected Behavior

A `DIRECTIVE_DRIFT` finding about required observable behavior missing an AC is repaired by adding the entailed criterion; a fixture-invalidation finding is repaired with an Implementation Step. After repair, a fresh `verify_issue` can return `VALID` within the existing budget. Context-only inventories do not create new requirements merely by appearing in Integration Map.

## Motivation

Any automated refinement run on an issue whose Integration Map has uncovered points burns ~25 minutes and 30+ iterations, then fails `GATE_UNMET`, although the fix (add the AC the verify finding names) is small and fully specified. The only workaround is a manual AC edit, which defeats the unattended `refine-to-ready-issue` path. It is the third instance of a verdict routed to a remedy that cannot clear it (see BUG-3574, ENH-3690), so fixing the contract also removes a recurring class of false `GATE_UNMET` exits.

## Proposed Solution

**Keep selected Option A:** a narrow caller-flag-gated carve-out in `commands/reconcile-issue.md`, using existing sections, routes and the one-reconcile budget. The pre-implementation review on 2026-10-03 settles the choices below; do not add a route-token flag or an automatic counter increase.

### Evidence producer and repair eligibility

- `verify-issues` must persist **both** `verify_verdict: DIRECTIVE_DRIFT` and the complete current `verify_evidence` in **one frontmatter update**. Replace prior evidence, do not append it. Reuse the existing escaped, single-line **double-quoted YAML scalar**, with `; `-separated findings shaped `<section>: '<specific drift>' -> <entailed correction>`. Include every applicable uncovered point and every fixture/compatibility drift found in the pass; do not truncate the list or silently drop findings. This is frontmatter-only in `--check`.
- Add `--from-verify-evidence` to reconcile-issue's flag documentation, parsing, read/findings stage and repair contract. Eligibility is **flag + `verify_verdict == DIRECTIVE_DRIFT` + nonempty `verify_evidence`**. Missing flag, another verdict or absent/empty evidence leaves the existing contract in force. `--check` remains read-only even when eligible.
- Only `refine-to-ready-issue.yaml`'s `reconcile_issue` action passes the flag. Its shared `ACCEPTANCE_CRITERIA` route still uses the same action, but a `VALID`/non-drift verdict must not authorize additions from `verify_evidence`. `reconcile_revision`, `prepare-issue.yaml`'s `run_reconcile` and normal/manual calls do not acquire the flag automatically from frontmatter.
- Treat each verify finding as an additional recorded source, with every added or rewritten item traceable to a concrete finding and **entailed by the selected mechanism**. A finding that demands a new behavior/option must be `PROPOSAL_UNSOUND`, not a license to invent requirements under `DIRECTIVE_DRIFT`.
- May add/rewrite Acceptance Criteria and Implementation Steps, and correct existing Integration Map entries. **Never add Integration Map entries in this carve-out**: that creates a new coverage obligation. Preserve all other sections and existing provenance protections. The ordinary "do not invent new requirements" rule continues outside this narrow source extension.
- Report `Acceptance Criteria: [rewritten | added | unchanged]` and make Implementation Steps reporting equally able to describe additions.

### B6 applicability and complete enumeration

Classify **every actual Integration Map entry** once in the verify report, recording `covered`, `uncovered` or `not applicable` plus the applicable directive/one-line reason. Multiple entries may share one criterion or step; coverage is not one AC per filename. Distinguish:

| Entry's role in the selected mechanism | Required coverage |
|---|---|
| Observable behavior, public API or compatibility contract change | An AC stating the expected outcome and how it is verified |
| Required test/mock/fixture update or fixture invalidation | A concrete Implementation Step; do not invent an AC for the fixture itself |
| Context-only existing caller, unchanged helper, Similar Pattern, or Tests/Documentation inventory | `not applicable` with a reason; listing a file alone creates no requirement |

An entry describing an actual behavior/contract consequence remains applicable even if filed under Tests or Documentation; decide by role, not subsection name. An AC that merely says a surface "is covered" is not coverage. An applicable gap that would change the chosen mechanism is `PROPOSAL_UNSOUND`; otherwise put **all** uncovered applicable points into this pass's `verify_evidence` and assign `DIRECTIVE_DRIFT` under existing precedence. Do not narrow scope only after a failed replay: apply this classification from the first implementation.

### Caller freshness and budget limits

Keep `check_reconcile_limit` at `target: 2` (one reconcile/run), including its sharing with `ACCEPTANCE_CRITERIA`. Do not raise it to 3 when a replay fails; investigate incomplete enumeration, applicability churn or an ineffective repair and fix this contract or file a focused follow-up.

Keep the normal freshness chain: `normalize_structure` -> `clear_verify_verdict` -> `verify_issue` -> dispatch. Structural tests pin its topology, VERIFY-before-AC ordering and the HEDGES-only skip writer. **These are not an absolute freshness guarantee:** clear uses `|| true` and proceeds on error; if it fails and verify writes nothing, stale drift/evidence can survive. Passing the captured route token would not fix that window because the token is derived from the same persisted verdict. Accept/document the existing infrastructure limitation here; a fail-closed clear/write protocol is separate work.

The downstream AC probe is `check-acceptance-criteria` / `_find_manual_criteria`: it only scans checkbox criteria for manual-verification phrases. A green probe is necessary compatibility with the next obligation, **not proof of observable quality, coverage or convergence**. B6 and repeated live evaluation establish those properties separately.

### Decision Rationale

`/ll:decide-issue` selected Option A on 2026-10-02. It reuses the explicit caller flag pattern of `verify-issues --from-evidence` (BUG-3637) and the ENH-2937 narrow carve-out precedent without a new state/counter or `max_steps` bump. Option B (dedicated repair state/budget) stays rejected; it still needs the same editing capability and adds routing complexity.

The Program Design precedent in `.ll/decisions.d/b5a1b051-4f32-42a8-b4ef-148a54801c52.json` remains intact: this issue extends the source for already eligible ACs/Steps, rather than adding a fourth rewrite section.

**Opus critique, 2026-10-03:** supports this minimum caller gate and the B6 role distinction (confidence 0.77), rejects the route-token flag as non-independent evidence and rejects the automatic budget fallback as hiding non-convergence. Residual risks are model compliance, applicability churn and the existing failed-clear/no-write window.

## Integration Map

### Files to Modify

- `commands/reconcile-issue.md` — flag argument/Parse Flags, Contract eligibility and allowed additions, findings extraction, repair workflow and Output Format; keep provenance and preserved-section rules
- `commands/verify-issues.md` — B6 role/coverage enumeration, `DIRECTIVE_DRIFT` remedy row/cross-references, and scoped persistence bullet writing current evidence with verdict
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `reconcile_issue` action gains only `--from-verify-evidence`; existing routes/counters/step cap stay unchanged
- `scripts/tests/test_reconcile_issue_command.py`, `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py`, `scripts/tests/test_builtin_loops.py`, `scripts/tests/test_ll_issues_next_obligation.py` — contract and route/negative-case tests
- `scripts/tests/test_bug3695_directive_drift_repair.py` — landed real built-in FSM with scripted slash-command effects; AC/fixture drift and budget regression

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/prepare-issue.yaml` — `run_reconcile` must not gain the flag, including with leftover drift/evidence
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `reconcile_revision` must not gain it; `ACCEPTANCE_CRITERIA` shares `reconcile_issue`, so verdict/evidence eligibility still matters
- `scripts/little_loops/cli/issues/next_obligation.py` — pin VERIFY-before-AC order; no new token/classifier
- `scripts/little_loops/cli/issues/check_acceptance_criteria.py` — reuse the actual manual-phrase probe; no stronger guarantee or new evaluator in this issue
- `scripts/little_loops/cli/issues/clear_verify_verdict.py` — removes both evidence fields in the normal path; no fail-closed infrastructure change here
- `scripts/little_loops/preparation_policy.py`, `scripts/little_loops/cli/issues/check_verify_verdict.py` — existing caller/classifier contracts; no mechanism change
- `skills/ll-reconcile-issue/SKILL.md` and generated command mirrors — regenerate via adapters where command metadata/body is copied
- BUG-3708 / ENH-3690 — overlapping command edits; follow the implementation order and preserve B8's mechanical advisory boundary

### Similar Patterns

- BUG-3637 `--from-evidence`: explicit targeted consumer mode, not inferred from field presence
- ENH-2937 `TestReconcileScopeBoundariesEligibility`: narrow source/section contract tests
- `scripts/tests/test_autodev_characterization.py` / `scripts/tests/autodev_harness.py`: real FSM plus scripted slash-command responses; existing harness stubs the child, so adapt the pattern to execute the actual `refine-to-ready-issue` child rather than accidentally testing the stub

### Tests

- Scoped DIRECTIVE_DRIFT persistence slice must write **both** fields and explain escaping/replacement; the existing test's generic `verify_evidence:` substring can pass from another verdict branch and is insufficient
- Flag, verdict and evidence eligibility: missing flag, `VALID`, other verdict, empty evidence, stale evidence cleared normally and check-mode no-write; normal/other caller actions cannot activate additions
- B6 behavior entry vs fixture entry vs context inventory; one AC can cover multiple behavior entries; a surface-name-only AC does not cover behavior; all uncovered applicable points enter one evidence set
- Exact `reconcile_issue` action pin gains the flag; reconcile_revision/prepare caller pins exclude it; existing PRE_TABLE, counter and max_steps pins remain green
- Real child FSM with stubbed model effects: first verify writes AC-only drift, reconcile adds an entailed checkbox AC, normalizer/clear run, next verify writes VALID; assert actual state order, evidence removal, one attempt and no `record_gate_unmet`
- Sibling fixture-only drift case adds a Step without an invented AC or map entry; ineffective repair still follows existing exhaustion behavior rather than receiving extra budget
- Run `_find_manual_criteria` / the real AC checker on the fixture repair output and test compatibility with `ACCEPTANCE_CRITERIA`; do not claim this scripted effect proves actual model quality
- Existing prose-baseline, audience and host-artifact staleness tests stay green

### Documentation and Mirrors

- `docs/guides/LOOPS_REFERENCE.md` — role-based drift repair and unchanged shared budget
- `docs/reference/COMMANDS.md` — explicit evidence flag and narrow addition scope
- `docs/reference/CLI.md`, `docs/reference/API.md` — update existing remedy descriptions only where they imply reconciliation cannot add entailed directives; no new CLI flag or Python reconcile function
- Regenerate gemini, kimi-code, qwen and codex with `ll-adapt --host <host> --apply`; include omp if `.omp` exists, matching its staleness gate. Never hand-edit mirrors.

## Program Design

### Types

Reuse existing frontmatter fields:

- `verify_verdict: str` — persisted verdict class
- `verify_evidence: str` — escaped one-line findings scalar

No new frontmatter schema, route token or budget artifact.

### Signatures

Command boundary: `/ll:reconcile-issue ISSUE_ID --from-verify-evidence`. This is command/loop prose, **not an existing Python `reconcile_issue(...)` function**. The eligible field/flag conditions and allowed sections are defined above.

### Call Path

`verify_issue` writes drift and all current evidence -> `route_pre_score_obligation` -> existing `check_reconcile_limit` -> flagged `reconcile_issue` -> `normalize_structure` -> `clear_verify_verdict` -> new `verify_issue` -> existing dispatch. The normal clear removes evidence only after repair.

## Implementation Steps

_Historical implementation plan — completed by `8dbd00703`. Remaining work is the normal full-suite closure gate and status update; ENH-3718 owns live evaluation._

1. BUG-3708 has landed (`45481a2ba`). Keep its occurrence/property and advisory contracts intact while editing B6/persistence; serialize overlapping ENH-3690 edits too.
2. Update B6 with the applicability table and complete per-entry walk. Persist DIRECTIVE_DRIFT verdict/evidence together using the existing escaped single-line format; update remedy row/cross-references without losing asserted anchors.
3. Add the caller flag and narrow source extension throughout reconcile's arguments, parsing, findings read, contract, edit workflow and output. Preserve ordinary no-new-requirements, provenance and check-mode rules. Only the shared `reconcile_issue` action receives the flag.
4. Add scoped prose tests and positive/negative scripted real-FSM cases above; pin unchanged dispatch, counter and max_steps. Test actual AC-checker compatibility separately from semantic coverage expectations. Add the distinct non-convergence line/evidence note to `record_gate_unmet` (no new `legacy_class`) with a test, plus the stale-verdict-on-`ACCEPTANCE_CRITERIA` inert case.
5. Update relevant docs, regenerate present host mirrors and run `python -m pytest scripts/tests/`.
6. **(Split to a follow-up issue — see Review 2026-10-03 callout.)** Evaluate three independent runs from an identical fresh fixture reproducing the AC-only drift (ENH-3678 has since changed), each with fresh run_dir, unchanged code and the current one-reconcile budget. Record findings, AC/Step edits, checker output, verdicts and counts reaching VALID/ready. Also evaluate fixture-only drift and irrelevant Tests/Docs inventories. Live evaluation assesses model compliance; scripted tests prove routing, not convergence. Investigate failures or capture a focused follow-up, never automatically raise the counter.

## Impact

- **Priority**: P3 — an applicable drift finding currently has no effective in-loop repair
- **Effort**: Medium — command contract, one action flag, focused routing fixtures, docs/mirrors and live evaluation
- **Risk**: Medium — model-generated additions can invent requirements or churn applicability; explicit source/role boundaries and repeated evaluation constrain this

## Acceptance Criteria

- [x] `reconcile_issue` alone gains `--from-verify-evidence`; `reconcile_revision` and prepare's `run_reconcile` do not. Eligibility additionally requires DIRECTIVE_DRIFT and nonempty evidence; absent/other/empty conditions leave ordinary behavior intact, including read-only `--check`.
- [x] DIRECTIVE_DRIFT persistence writes verdict and the complete current evidence together, replacing old evidence, with the existing escaped double-quoted single-line scalar format; tests slice this specific branch.
- [x] B6 classifies every map entry as covered/uncovered/not applicable, distinguishes behavior ACs from fixture Steps, records all applicable uncovered points in one pass and does not demand one AC per file/inventory entry.
- [x] Added ACs/Steps trace to verify findings and the selected mechanism; every AC states an observable outcome and how to verify it. No map entries or new mechanism requirements are added; output reports additions.
- [x] Scripted real-child FSM tests exercise AC-only and fixture-only drift through repair/normalize/clear/fresh verify, assert evidence lifecycle and one attempt, and preserve the negative exhaustion path.
- [x] VERIFY-before-AC ordering, normal clear topology, HEDGES-only skip and non-drift shared-state eligibility are tested; the existing failed-clear/no-write limitation is documented, not described as impossible.
- [x] Repaired fixture checkbox ACs pass the actual manual-phrase probe; coverage/quality is tested separately rather than inferred from that probe's exit 0.
- [x] On budget exhaustion after a flagged reconcile, `record_gate_unmet` output/evidence distinguishes DIRECTIVE_DRIFT non-convergence from other gate failures without adding a `legacy_class`; tests pin unflagged callers and the eligibility contract, and show a VALID verdict with stale evidence can reach the flagged shared `ACCEPTANCE_CRITERIA` action. Actual refusal to add directives in that ineligible case is live-evaluated under ENH-3718, not proved by scripted effects.
- [x] Route table, target 2/shared budget and max_steps stay unchanged; mirrors and relevant documentation match; `python -m pytest scripts/tests/` exits 0.
- [x] Live-evaluation work transferred to **ENH-3718**, which has already been captured. This checks the handoff only: the live runs remain pending there and are not claimed as satisfied here. Original scope: three independent AC-only runs plus fixture-only/context-inventory evaluation; investigate failures without automatically increasing the budget.

## Secondary Observations

- _(Moved out)_ `refine_followup`'s vanished scratch snapshot is now tracked as BUG-3702.
- `verify_issue` on iteration 29 spent turns on a failed glob for the issue file before recovering. Out of scope here (not part of the DIRECTIVE_DRIFT contract); not filed separately — it is a one-off efficiency note.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-02 | Priority: P3

Code implemented in `8dbd00703`; awaiting the normal full-suite closure gate. No further implementation of this issue's selected mechanism is needed. ENH-3718 separately owns live evaluation and records the existing failed-clear/no-write limitation.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-03 (re-scored after BUG-3708 landed and `blocked_by` was cleared)_

_Historical pre-implementation assessment. Correction from this review: the flag and adapted real-child harness now exist in `8dbd00703`; the live follow-up is ENH-3718. Preserve the original assessment below as history, not as current implementation work._

**Readiness Score**: 92/100 → PROCEED
**Outcome Confidence**: 69/100 → MODERATE

### Concerns

- Anchors resolve by phrase, not line: `VERIFY:DIRECTIVE_DRIFT` route (`refine-to-ready-issue.yaml:589`), `check_reconcile_limit` (`:797`), `reconcile_issue` (`:822`), `reconcile_revision` (`:712`), `record_gate_unmet` (`:1252`), "do not invent new requirements" (`commands/reconcile-issue.md:120`). `--from-verify-evidence` exists nowhere yet, so no duplicate. `format-check` is clean and `check-design` passes. `.omp` is absent, so no omp mirror.
- The new-signal AC (distinct non-convergence output from `record_gate_unmet`) had no Implementation Step; step 4 now covers it.
- The carve-out is command prose, not an enforced edit filter; model compliance is evaluated in the split-out live-evaluation follow-up.

### Outcome Risk Factors

- Cross-cutting contract change (verify B6 + persistence, reconcile flag/eligibility, one loop action, four docs, host mirrors) with moderate per-site depth.
- One shared reconcile attempt remains; incomplete first-pass enumeration or applicability churn can still exhaust it. No automatic budget fallback masks that defect.
- The new real-child FSM test must adapt `autodev_harness.py`, which currently stubs the child.
- Failed clear plus a verify call that writes nothing can retain stale evidence (documented limitation).
- Shared `commands/verify-issues.md` / mirror surface with other EPIC-3694 children requires serialized edits.

## Session Log
- Implementation review - 2026-10-03 - `/ll:advise` with Opus (confidence 0.80): confirmed `8dbd00703` already delivers the code fix; reran 2120 relevant tests (1 skipped); corrected the live-evaluation handoff and negative-test evidence claim. ENH-3718 gains a live non-drift/stale-evidence eligibility check. Full suite not rerun, so closure remains pending rather than attributing live compliance or a fresh full-suite pass to scripted tests.
- `/ll:confidence-check` - 2026-10-03T22:46:43 - `c4c6a704-e666-48df-b6fe-37ff869c1bae.jsonl`
- `/ll:confidence-check` - 2026-10-03T17:52:31 - `7b5fbb18-2486-460d-9469-16b4a7432e0e.jsonl`
- `/ll:confidence-check` - 2026-10-03T17:18:06 - `e655cd0c-0c5d-446b-bee6-c9fe4cf5573e.jsonl`
- `/ll:decide-issue` - 2026-10-02T20:01:51 - `c7a25ce4-f603-4faf-97bd-88495061e012.jsonl`
- `/ll:confidence-check` - 2026-10-02T19:45:19 - `9a15ba2c-4c77-475b-8d6d-2e5aa8b1186f.jsonl`
- `/ll:wire-issue` - 2026-10-02T19:42:57 - `4830feb2-90ba-4747-9939-6d60a5df22df.jsonl`
- `/ll:refine-issue` - 2026-10-02T17:56:39 - `211b3968-8e30-4656-bda0-11230a163531.jsonl`
- `/ll:format-issue` - 2026-10-02T17:52:15 - `dc7de560-ace3-44cc-8c42-afca4eb429ff.jsonl`
- `/ll:capture-issue` - 2026-10-02T17:46:36 - `f95760a1-28e5-4de5-bec7-aaf05cf7e5d8.jsonl`

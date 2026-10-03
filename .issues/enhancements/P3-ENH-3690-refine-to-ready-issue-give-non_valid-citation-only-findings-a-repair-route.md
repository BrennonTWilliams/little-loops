---
id: ENH-3690
type: ENH
title: 'refine-to-ready-issue: give NON_VALID citation-only findings a repair route'
priority: P3
status: open
decision_needed: false
discovered_by: ll-issues-create
discovered_date: '2026-10-01'
captured_at: '2026-10-01T22:03:25Z'
relates_to:
- BUG-3691
- BUG-3708
- BUG-3695
blocked_by:
- BUG-3691
parent: EPIC-3694
epic: EPIC-3694
---

# ENH-3690: refine-to-ready-issue: give NON_VALID citation-only findings a repair route

## Summary

In `refine-to-ready-issue`, a `/ll:verify-issues --check` verdict of `NON_VALID` caused only by wrong file-path or symbol-location citations has no repair route, so the run ends `GATE_UNMET` (observed on BUG-3689, run `refine-to-ready-issue-20261001T151155`, 33 iterations / 19m38s).

Chain: the third verify pass flagged two mis-citations (a bare `runner_spec.py:335` in Current Behavior, whose real path is `scripts/little_loops/runner_spec.py`; and `cli/loop/feed.py:terminal_size()` in Tests/Wiring Phase, which is defined in `cli/output.py`). Because one finding sat in Current Behavior, `commands/verify-issues.md` §2C keeps the verdict `NON_VALID` (never `CLAIMS_OUTDATED`), and `NON_VALID` outranks the Tests-section finding that alone would have been correctable. `route_pre_score_obligation` maps it to `VERIFY:other` -> `check_gate_refine_limit`. That budget (one loopback per run) had already been spent by an earlier `refine_followup`, which is additive-only and cannot fix a stale fact. Route continues to `record_gate_unmet` -> `failed`.

Neither `reconcile_issue` (directive sections only) nor `correct_claims` (`CLAIMS_OUTDATED` only) is reachable.

## Current Behavior

A `NON_VALID` verdict whose only findings are wrong file-path or symbol-location citations routes `VERIFY:other` -> `check_gate_refine_limit` in `refine-to-ready-issue.yaml`. That state holds a shared one-loopback-per-run budget that an earlier `refine_followup` has usually already spent. When it is spent the run goes to `record_gate_unmet` and ends `GATE_UNMET`. Neither `correct_claims` (reachable only via `VERIFY:CLAIMS_OUTDATED` -> `check_claim_correction_budget`) nor `reconcile_issue` (directive sections only) can run.

## Expected Behavior

A run whose only verify findings are citation-shaped (wrong path or symbol location, no change to the issue's premise) is repaired in-loop by a claims-correction attempt, or ends with a distinct non-quality outcome. It does not end `GATE_UNMET`. Findings that change the issue's premise still persist as `NON_VALID` and keep the current route.

## Motivation

This enhancement would:
- Remove a false quality failure: BUG-3689's run (`refine-to-ready-issue-20261001T151155`) burned 33 iterations / 19m38s and ended `GATE_UNMET` over two cosmetic mis-citations.
- Make `GATE_UNMET` mean what it says: a quality gate the issue could not meet, not a citation typo that no state is able to fix.
- Stop spending the single gate-refine budget on `refine_followup`, which is additive-only (`commands/refine-issue.md` §5c) and cannot fix a stale fact.

## Proposed Solution

Options (pick one):
1. Give `VERIFY:other`/`NON_VALID` one `correct_claims`-style attempt before `record_gate_unmet` when `verify_evidence` lists only citation-shaped findings.
2. Relax §2C so a pure path/symbol-location fix in Current Behavior is `CLAIMS_OUTDATED` (premise unchanged), keeping premise changes `NON_VALID`.
3. Have `VERIFY:other` skip `refine_followup` (cannot help) and go straight to a claims-correction state, so the single gate-refine budget isn't wasted.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-01 — based on codebase analysis:_

**Option A**: Give `VERIFY:other` / `NON_VALID` one `correct_claims`-style attempt before `record_gate_unmet` when `verify_evidence` lists only citation-shaped findings (Option 1 above).

**Option B**: Relax `commands/verify-issues.md` §2C so a pure path / symbol-location fix in a premise section is `CLAIMS_OUTDATED`, keeping premise-changing findings `NON_VALID` (Option 2 above).
> **Selected:** Option B — smallest change; reuses the existing `VERIFY:CLAIMS_OUTDATED` route, counter, and `correct_claims` cycle with no YAML/Python edits.

**Option C**: Have `VERIFY:other` skip `refine_followup` and go straight to a claims-correction state (Option 3 above).

**Recommended**: Option B — Options A and C both depend on two facts the research below shows are currently false (a `NON_VALID` verdict persists no `verify_evidence`, and `correct_claims` is barred from editing premise sections), so each still needs a `verify-issues.md` change; Option B makes that change once and reuses the existing `VERIFY:CLAIMS_OUTDATED` route, counter, and tests unchanged.

- Constraint shared by all options: `correct_claims` runs `/ll:verify-issues <ID> --auto --from-evidence`, which is a no-op when `verify_evidence` is absent or empty (`commands/verify-issues.md` §4 "In-place claim correction"). §2.5 persists `verify_evidence` only for `PROPOSAL_UNSOUND`, `DIRECTIVE_DRIFT`, and `CLAIMS_OUTDATED`; nothing persists it for `NON_VALID`. Routing a `NON_VALID` run into `check_claim_correction_budget` as-is would therefore consume the one correction pass and edit nothing.
- Constraint shared by all options: the same §4 rule bounds in-place correction by §2C's correctable scope and excludes Summary, Current Behavior, Expected Behavior, Root Cause, Motivation, Steps to Reproduce, and Proposed Solution. The BUG-3689 trigger was a bare path in Current Behavior, so even with `verify_evidence` populated, `correct_claims` would refuse that finding unless the scope rule changes for path / symbol-location fixes.
- Constraint for Option A / C: the discriminator would parse `verify_evidence`, which is a single double-quoted YAML scalar with `; `-separated items shaped `<section>: '<stale text>' -> <current truth>` (§2.5), not a list. No code splits or classifies it today; `arm_proposal_revision.py` only collapses its whitespace and `clear_verify_verdict.py` only deletes the key.
- Constraint for Option B: the correctable-scope sentence in §2C and the matching sentence in §4 must stay consistent, and `TestClaimsOutdatedVerdict` in `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` asserts both the `Correctable scope for` heading text and the seven premise section names, so it must be updated in the same change. The never-auto-correct set (`INVALID`, `RESOLVED`, `DECISIONS_VIOLATION`, `REGRESSION_LIKELY`, `POSSIBLE_REGRESSION`, `DEP_ISSUES`) and the "both scopes present means `NON_VALID` wins" precedence must remain intact so premise-changing findings still persist as `NON_VALID`.
- Constraint for Option C: `check_gate_refine_limit` is shared by `VERIFY:EVIDENCE_UNVERIFIED`, `PLACEHOLDERS`, `DESIGN`, and `check_reconcile_limit` exhaustion, so changing only the `VERIFY:other` route entry leaves those callers on `refine_followup`; the `PRE_TABLE` assertion in `TestRefineToReadyDispatch.test_pre_score_routing_table` compares the whole route map and must be updated for any route change.
- Counter convention (any option adding a new budget state): per-run integer file under `${context.run_dir}`, seeded to `0` in `resolve_issue`, incremented in a shell state with `output_numeric lt 2`, exhaustion routed to a terminal-recording state; each new cycle also needs the `max_steps` comment-block entry (currently 113, the BUG-3637 cycle is 6 steps). Evidence: `check_claim_correction_budget`, `check_proposal_revision_budget` in `scripts/little_loops/loops/refine-to-ready-issue.yaml`.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-10-01.

**Selected**: Option B — relax `commands/verify-issues.md` §2C / §4 so a pure path / symbol-location fix in a premise section is `CLAIMS_OUTDATED`.

**Reasoning**: Option B changes only prose in `verify-issues.md` (§2C, §2.5, §4) plus `TestClaimsOutdatedVerdict`, and reuses the whole `VERIFY:CLAIMS_OUTDATED` pipeline (`check_claim_correction_budget` -> `correct_claims` -> `normalize_structure` -> `clear_verify_verdict` -> `verify_issue`). Options A and C each need the same `verify-issues.md` scope/persistence change *plus* a new `verify_evidence` splitter/classifier or a coarser-than-needed `VERIFY:other` reroute (which would wrongly skip `refine_followup` for `RESOLVED`/`INVALID`/`DEP_ISSUES` findings).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |
| Option B | 3/3 | 3/3 | 2/3 | 1/3 | 9/12 |
| Option C | 2/3 | 2/3 | 2/3 | 0/3 | 6/12 |

**Key evidence**:
- Against A: reuses the budget-state template (`refine-to-ready-issue.yaml:623-682`) but needs a new `NON_VALID` evidence write, a `verify_evidence` splitter (none exists), and the same §2C relaxation as B.
- For B: no YAML/Python/route changes; the `TestClaimsOutdatedVerdict` assertions (heading text + seven section names, `test_enh3250_verify_issues_proposal_vs_code.py:166-180`) stay green if those phrases are kept.
- Against C: single route-key edit (`:594`) but `VERIFY:other` collapses `NON_VALID`, `RESOLVED`, `INVALID`, `DEP_ISSUES`, and premise findings; `verify_evidence` is unpersisted for them so the repair state would no-op.
- **Risk to watch (B)**: relaxes the BUG-3637 premise-edit guard with a model-judged path-vs-premise split, and BUG-3691 shows citation judgment is unstable; keep the "both scopes present means `NON_VALID` wins" precedence and never-auto-correct set intact, and note `correct_claims` still has a single per-run budget.

### Revision (2026-10-02, EPIC-3694 pre-implementation review)

Revises the `/ll:decide-issue` choice above; Option B's *mechanism* (reuse the `VERIFY:CLAIMS_OUTDATED` route, no YAML/Python route change) stands, but its **discriminator changes**:

- Option B as decided loosens the BUG-3637 premise-edit guard using a *model-judged* path-vs-premise split — the same unstable judgment BUG-3691 documents. That is a masking hazard: a premise-changing finding mislabeled "citation-only" would be auto-corrected.
- **Revised rule (B′):** a finding qualifies for `CLAIMS_OUTDATED` only when it **maps to a deterministic `ll-issues format-check` key** (`stale_file_ref`, `ambiguous_file_ref`, `mislocated_symbol_ref`, the new `stale_line_ref`; the BUG-3691 rescope adds the defined-in/imported-in and bare-filename rules). Anything the model raises that format-check does not back up stays `NON_VALID`. "Both scopes present means `NON_VALID` wins", the never-auto-correct set, and the `verify_evidence` write requirement are unchanged.
- Hence `blocked_by: BUG-3691`. Dissent considered: ship Option B now as a stopgap gated on the format-check keys that already exist (stale/ambiguous/mislocated); BUG-3691's new rules would then widen coverage. Reasonable if the 33-iteration `GATE_UNMET` burn recurs before BUG-3691 lands — drop `blocked_by` in that case, but keep the key-gating.
- Follow-up option (not in scope): for `mislocated_symbol_ref` and uniquely-resolved `ambiguous_file_ref`, rewrite the citation mechanically in code (`symbol_resolves_elsewhere` gives the target) instead of via the model's `correct_claims`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` - `route_pre_score_obligation` (`VERIFY:other` route), `check_claim_correction_budget`, `correct_claims` (Option B selected: no YAML change expected — existing `VERIFY:CLAIMS_OUTDATED` route is reused)
- `commands/verify-issues.md` - §2C correctable-scope rule and §2.5 verdict precedence (Option B — selected)
  > ⚠ Superseded — needed by every option; see § Codebase Research Findings under Proposed Solution
- `scripts/little_loops/cli/issues/check_verify_verdict.py` - only if a new verdict value or evidence discriminator is added

_Wiring pass added by `/ll:wire-issue`:_
- `commands/verify-issues.md:265` — verdict-table row in `§2C` calls `CLAIMS_OUTDATED` "a **factual metadata correction** only"; reword so a path / symbol-location fix in a premise section qualifies [Agent 2 finding]
- `commands/verify-issues.md:279` — "stays `NON_VALID`" sentence naming the seven premise sections in `Correctable scope for CLAIMS_OUTDATED`; carve out the path / symbol-location case [Agent 2 finding]
- `commands/verify-issues.md:277` — rationale that auto-rewriting a premise is unsafe because an independent `--check` re-pass cannot catch it, in `Correctable scope for CLAIMS_OUTDATED`; the relaxation must reconcile with this [Agent 2 finding]
- `commands/verify-issues.md:400-423` — `§2.5` "CLAIMS_OUTDATED verdict" and "Any other verdict" bullets state "every finding is in the correctable scope defined in §2C" and the never-auto-correct list; keep consistent with the relaxed §2C [Agent 2 finding]
- `commands/verify-issues.md:464-471` — second copy of the seven-section premise list in `In-place claim correction (BUG-3637)` (§4); must change in the same edit as §2C [Agent 2 finding]
- `commands/verify-issues.md:511-515` — `§4.1 Frontmatter sync` says `CLAIMS_OUTDATED` holds "when the residual findings are still all in the correctable scope"; depends on the §2C definition [Agent 2 finding]
- `commands/verify-issues.md:612-614` — `--from-evidence` flag description in `Arguments`; "correct only the claims it lists" wording named in this issue's scope [Agent 2 finding]
- `.gemini/commands/verify-issues.toml:249` — git-tracked full-body host mirror of `Correctable scope for CLAIMS_OUTDATED`; regenerate with `ll-adapt --host gemini --apply` after the command edit [Agent 1 + Agent 2 finding]
- `.qwen/commands/ll/verify-issues.md:250` — git-tracked full-body host mirror; regenerate with `ll-adapt --host qwen --apply` [Agent 1 + Agent 2 finding]
- `.kimi-code/skills/ll-verify-issues/SKILL.md` — git-tracked full-body host mirror (one `Correctable scope` hit); regenerate with `ll-adapt --host kimi-code --apply` [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/next_obligation.py` - emits the `VERIFY:*` tokens `route_pre_score_obligation` classifies
- `scripts/little_loops/loops/autodev.yaml` and other loops that wrap `refine-to-ready-issue` consume its terminal outcomes (`GATE_UNMET`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `classify_verify_verdict` collapses `NON_VALID` to `other` and passes `CLAIMS_OUTDATED` through; unchanged under Option B, the relaxation lands upstream in the verdict the command writes [Agent 1 finding]
- `scripts/little_loops/cli/issues/clear_verify_verdict.py` — `cmd_clear_verify_verdict` deletes `verify_verdict` and `verify_evidence` after `correct_claims`; no change [Agent 1 finding]
- `scripts/little_loops/cli/issues/arm_proposal_revision.py` — `cmd_arm_proposal_revision` reads `verify_evidence` as a whitespace-collapsed string (`PROPOSAL_UNSOUND` only); no change [Agent 1 finding]
- `scripts/little_loops/preparation_policy.py` — calls `select_next_obligation` in the `prepare-issue` policy probe; consumes `VERIFY:*` tokens, no change [Agent 1 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — header routing comments (`VERIFY:CLAIMS_OUTDATED` entry) and the `correct_claims` / `check_claim_correction_budget` state comments describe "factual metadata" only; reword only if the §2C wording changes materially [Agent 2 finding]
- No other loop YAML or hook routes on `VERIFY:CLAIMS_OUTDATED` or calls `/ll:verify-issues`; no skill or other command restates the premise-section list (searched `CLAIMS_OUTDATED`, `Correctable scope`, `premise` across `commands/`, `skills/`, `hooks/`, `scripts/little_loops/loops/`) [Agent 1 + Agent 2 finding]

### Similar Patterns
- BUG-3637 `CLAIMS_OUTDATED` route: `check_claim_correction_budget` -> `correct_claims` -> `normalize_structure` -> `clear_verify_verdict` -> `verify_issue`
- BUG-3574 `check_proposal_revision_budget` (own per-run counter, exhaustion bypasses `check_gate_refine_limit`)

### Tests
- `scripts/tests/test_builtin_loops.py` - route table assertions for `route_pre_score_obligation` (near the `"VERIFY:*"` map) plus a new test for the citation-only route
- `scripts/tests/test_ll_issues_next_obligation.py` - if the selector's tokens change

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — add new pins in `TestClaimsOutdatedVerdict`: §2C carve-out wording; "both scopes present means `NON_VALID` wins" still stated; six never-auto-correct names still listed; §4 `In-place claim correction` carries the same carve-out. Follow the `" ".join(text.split())` flatten plus `body.index(...)` slice style [Agent 3 finding]
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — `test_correctable_scope_rule_excludes_premise_sections` in `TestClaimsOutdatedVerdict` checks the seven section names only as substrings anywhere in the body, so it stays green after the relaxation and would not catch a wrongly kept exclusion; tighten it rather than rely on it [Agent 3 finding]
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — `test_persistence_carves_out_claims_outdated_with_evidence` and `test_persistence_states_full_precedence_order` in `TestClaimsOutdatedVerdict` pin the six never-auto-correct names, the `<section>: '<stale text>' -> <current truth>` shape and the backtick-delimited precedence strings; may break if §2.5 is reworded [Agent 3 finding]
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — `test_section_4_has_in_place_correction_rule` in `TestClaimsOutdatedVerdict` pins `In-place claim correction`, `does not count as a correction` and `--from-evidence` between `### 4.` and `### 4.1`; may break if §4 is reworded [Agent 3 finding]
- `scripts/tests/test_wiring_skills_and_commands.py` — `test_host_artifacts_are_not_stale` (`commands` kind, hosts gemini / qwen / kimi-code) fails with `adapted != 0` until the mirrors are regenerated with `ll-adapt --host <host> --apply` [Agent 2 + Agent 3 finding]
- `scripts/tests/test_docs_audience_gate.py` — scans `commands/*.md`; new §2C / §4 prose must not cite `scripts/tests/` or `scripts/little_loops/` paths (use `little_loops.<module>`) [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — `TestRefineToReadyDispatch.test_pre_score_routing_table` (`PRE_TABLE`, `"VERIFY:CLAIMS_OUTDATED"` / `"VERIFY:other"`) and `test_dispatch_tokens_are_complete` stay green under Option B; no route edit [Agent 2 + Agent 3 finding]
- No fixture or end-to-end test runs `/ll:verify-issues` against a bare-path citation in Current Behavior (it is an LLM-judged command), so acceptance for that case can only be pinned as prose; `check_claim_correction_budget` and `correct_claims` also have no per-state shape test or `resolve_issue` seeding assertion today (searched `claim-corrections`, `correct_claims`, `check_claim_correction_budget` across `scripts/tests`) [Agent 3 finding]

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` - `refine-to-ready-issue` routing description
- `docs/reference/CLI.md` - only if `next-obligation` tokens change

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:154` — `VERIFY:CLAIMS_OUTDATED` row in `Claim-verification gate chain`; describes route and budget only, update the "stale claim" description if the verdict now also covers path / symbol-location fixes in premise sections [Agent 1 + Agent 2 finding]
- `docs/reference/CLI.md:2435` — `ll-issues next-obligation` `VERIFY` sub_reason list describes `CLAIMS_OUTDATED` as "a claim-correctable `OUTDATED`/`NEEDS_UPDATE` finding" in `next-obligation`; confirm wording still holds [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-01 — based on codebase analysis:_

- `scripts/little_loops/loops/refine-to-ready-issue.yaml`: `route_pre_score_obligation` (classify route table; `VERIFY:other` and `VERIFY:CLAIMS_OUTDATED` entries), `check_gate_refine_limit` (shared `refine-to-ready-refine-count` file, `lt 2`, exhaustion -> `record_gate_unmet`), `check_claim_correction_budget` (own `refine-to-ready-claim-corrections` counter, exhaustion -> `record_gate_unmet` directly), `correct_claims`, `resolve_issue` (seeds every counter), and the `max_steps` comment block.
- `scripts/little_loops/cli/issues/check_verify_verdict.py:classify_verify_verdict` collapses `NON_VALID` (and any unrecognized value) to `other`; `next_obligation.py:select_next_obligation` reads only `verify_verdict`, never `verify_evidence`. A new verdict value needs an entry in both, in the hand-listed `sub` dict in `TestRefineToReadyDispatch._tokens`, and in `TestVerify` in `test_ll_issues_next_obligation.py`.
- `commands/verify-issues.md` is needed for every option, not Option B only: §2.5 verdict persistence (no `verify_evidence` write for `NON_VALID`), §2C correctable scope, §4 in-place correction bound, and the `--from-evidence` flag description.
- Terminal-outcome consumers: `autodev.yaml` failure router maps `DEFERRED:gate_unmet` to `ledger_child_stop` and `route_refine_success` to `skip_inflight`; `prepare-issue.yaml:run_child` and `recursive-refine.yaml:run_refine` run the loop as a child. A route that ends `done` takes the success path in those consumers; a route that still ends `record_gate_unmet` leaves them unchanged. `LEGACY_CLASSES` in `scripts/little_loops/run_record.py` is a closed tuple, so a "distinct non-quality outcome" needs a new class there plus its consumers (`autodev_summary.py`, `preparation_policy.py`, `deferred_triage.py`).
- Tests: `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py:TestClaimsOutdatedVerdict` pins the §2C wording; `check_claim_correction_budget` and `correct_claims` currently have no per-state shape test and no `resolve_issue` seeding assertion (only the `PRE_TABLE` entry), unlike the hedge, verify-retries, and proposal-revision counters.
- Docs: `docs/guides/LOOPS_REFERENCE.md` "Claim-verification gate chain" token table lists `VERIFY:other` under `check_gate_refine_limit` and `VERIFY:CLAIMS_OUTDATED` under `check_claim_correction_budget`; the routing header comment at the top of `refine-to-ready-issue.yaml` mirrors it.

_Added by `/ll:refine-issue` — 2026-10-01 — based on codebase analysis:_

- Post-correction routing (existing behavior, unchanged by Option B): `check_claim_correction_budget` allows one pass per run (own counter, exhaustion goes straight to `record_gate_unmet`). After `correct_claims` -> `normalize_structure` -> `clear_verify_verdict`, `verify_issue` re-runs a full `--check`: a repeat `CLAIMS_OUTDATED` ends `GATE_UNMET` (budget spent); a `NON_VALID` goes to `check_gate_refine_limit`. So a mis-correction surfaces as a second finding, not silently.
- Empty-evidence hazard: `--from-evidence` makes no edits when `verify_evidence` is absent or empty, yet the one correction pass is still consumed. Under Option B every path/symbol finding relabeled `CLAIMS_OUTDATED` must still be written into `verify_evidence` as `<section>: '<stale text>' -> <current truth>` items, since §2.5's `CLAIMS_OUTDATED` bullet is the only persistence point.
- Mixed-case invariant: an issue with one citation-only finding plus one premise-changing finding must remain `NON_VALID` (the "both scopes present means `NON_VALID` wins" rule); BUG-3689's trigger had two citation-only findings, so the relaxation is only sufficient when all findings qualify.

## Implementation Steps

1. Option B′ (see Decision Rationale § Revision): change §2C / §2.5 / §4 of `commands/verify-issues.md` so a finding qualifies for `CLAIMS_OUTDATED` only when backed by a deterministic `format-check` ref key; the verdict contract gains no new value.
   > ⚠ Superseded — Options 1/3 also need verify_evidence persistence and §2C scope change
2. Implement the route in `refine-to-ready-issue.yaml` (or the §2C rule) so citation-only findings reach a claims-correction attempt with its own counter, never `check_gate_refine_limit`.
   > ⚠ Superseded — Option B selected; no YAML route or counter change
3. Add a `test_builtin_loops.py` test for the new route and a regression test that premise-changing `NON_VALID` still reaches `record_gate_unmet`.
   > ⚠ Superseded — Option B adds no route; pin in test_enh3250 instead
4. Update `docs/guides/LOOPS_REFERENCE.md`; run `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` (the route table is unchanged; no YAML edit, so no `ll-loop validate` step).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `commands/verify-issues.md` §2C (verdict-table row at `:265`, `Correctable scope for CLAIMS_OUTDATED` at `:267-285`) and §4 `In-place claim correction` (`:464-471`) in one edit so both copies of the premise-section list agree; keep the literal phrases `Correctable scope for \`CLAIMS_OUTDATED\``, `In-place claim correction`, `does not count as a correction`, `--from-evidence` and the seven section names
- Update `commands/verify-issues.md` §2.5 (`:400-432`), §4.1 (`:511-515`) and the `--from-evidence` flag description (`:612-614`) to match; keep the six never-auto-correct names, the `<section>: '<stale text>' -> <current truth>` item shape and the `NON_VALID` > `EVIDENCE_UNVERIFIED` > `CLAIMS_OUTDATED` > `PROPOSAL_UNSOUND` precedence verbatim
- Update `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — add `TestClaimsOutdatedVerdict` pins for the path / symbol-location carve-out, "both scopes present means `NON_VALID` wins", and the §4 carve-out; tighten `test_correctable_scope_rule_excludes_premise_sections`
- Regenerate host mirrors after the command edit: `ll-adapt --host gemini --apply`, `ll-adapt --host qwen --apply`, `ll-adapt --host kimi-code --apply`, then re-run `test_host_artifacts_are_not_stale` in `scripts/tests/test_wiring_skills_and_commands.py`; stage the three mirrors (`.gemini/commands/verify-issues.toml`, `.qwen/commands/ll/verify-issues.md`, `.kimi-code/skills/ll-verify-issues/SKILL.md`)
- Update `docs/guides/LOOPS_REFERENCE.md` (`VERIFY:CLAIMS_OUTDATED` row, `Claim-verification gate chain`) and check `docs/reference/CLI.md` (`next-obligation` `CLAIMS_OUTDATED` description); keep new `commands/` prose free of `scripts/tests/` and `scripts/little_loops/` paths (`test_docs_audience_gate.py`)
- Leave `refine-to-ready-issue.yaml`, `check_verify_verdict.py`, `next_obligation.py` unchanged; confirm with `python -m pytest scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py scripts/tests/test_wiring_skills_and_commands.py scripts/tests/test_docs_audience_gate.py scripts/tests/test_builtin_loops.py`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-01 — based on codebase analysis:_

- Whichever option is chosen, a citation-only finding in a premise section must end in a state where `verify_evidence` is populated and the correctable-scope rule permits the edit; verify with a fixture issue carrying a bare-path citation in Current Behavior that reaches `VALID` without `record_gate_unmet`.
- Premise-changing `NON_VALID` findings (and the never-auto-correct set) must still persist as `NON_VALID` and reach `record_gate_unmet`; add a regression assertion alongside the `TestRefineToReadyDispatch` route tests.
- If a new route or budget state is added, it needs its own counter seeded in `resolve_issue`, a shape test in the style of the hedge/proposal-revision counter tests, a `max_steps` bookkeeping update, and the `LOOPS_REFERENCE.md` table row.
- `ll-loop validate refine-to-ready-issue`, `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py scripts/tests/test_ll_issues_next_obligation.py` pass.

## Impact

- **Priority**: P3 - Observed once; wastes a ~20 minute run, but the issue still surfaces as `GATE_UNMET` rather than corrupting state.
- **Effort**: Small - one new route plus a counter state, or a single rule edit in `commands/verify-issues.md`.
- **Risk**: Medium - loosens the BUG-3637 premise-edit guard; mitigated by gating on deterministic `format-check` keys (B′) rather than model judgment, and keeping `NON_VALID`-wins precedence.
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: a repair route (or verdict reclassification) for `NON_VALID` findings that are purely wrong path/symbol-location citations; the test for that route.
- **Out of scope**: changing how `refine_followup` works; raising the shared gate-refine budget; the verify citation-checking instability itself (tracked in BUG-3691); premise-changing `NON_VALID` findings.

## Program Design

### Types

- `citation_only: bool` — derived from the `verify_evidence` frontmatter findings (all citation-shaped), not stored

### Signatures

- N/A under selected Option B′ — no `is_citation_only` code discriminator; the §2C prose rule classifies a finding as `CLAIMS_OUTDATED` only when a `format-check` ref key backs it (revised from model-judged). (Rejected Option A would have needed `is_citation_only(evidence: str) -> bool`.)

### Call Path

`route_pre_score_obligation` -> `check_claim_correction_budget` -> `correct_claims` -> `normalize_structure` -> `clear_verify_verdict` -> `verify_issue` -> `route_pre_score_obligation`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-01 — based on codebase analysis:_

- `verify_evidence` is a single double-quoted YAML scalar (one line, `; `-separated items), so the Signatures entry `is_citation_only(evidence: list[str])` needs either a split step or a `str` parameter; no splitter exists today (`arm_proposal_revision.py` treats it as one whitespace-collapsed string). `NON_VALID` currently writes no `verify_evidence`, so the discriminator has no input unless §2.5 persistence changes.
- Call Path above is the existing `VERIFY:CLAIMS_OUTDATED` cycle (6 steps, `max_steps` 113); the `VERIFY:other` route does not currently reach it. `classify_verify_verdict` -> `ObligationResult.token()` -> `route_pre_score_obligation` is where a `VERIFY:other` split would have to originate.
- Decision Rules: N/A — no new decision logic beyond the citation-only discriminator, whose exact inputs (finding items from `verify_evidence`) and scope (path, line, count, or symbol-location changes only) are fixed by §2C's existing correctable-change list.

_Added by `/ll:refine-issue` — 2026-10-01 — based on codebase analysis:_

- Public identifiers on the Option B path: `classify_verify_verdict(verdict: object) -> str` (`cli/issues/check_verify_verdict.py`; `NON_VALID` and any unrecognized value return `"other"`, `CLAIMS_OUTDATED` passes through uppercased), `select_next_obligation(config, issue_id, ...) -> ObligationResult | None` and `ObligationResult.token() -> str` (`cli/issues/next_obligation.py`; yields `VERIFY:<sub_reason>`), `cmd_clear_verify_verdict(config, args) -> int` (`cli/issues/clear_verify_verdict.py`; deletes `verify_verdict` and `verify_evidence`, returns 0 when keys are absent). The Call Path states above are FSM state names, not Python symbols; the only underscore-private hop is `_verify_class` inside `select_next_obligation`. No signature changes under Option B.
- Decision Rules correction: the `N/A — no new decision logic` entry below does not hold under Option B. The relaxed §2C classification is new model-judged decision logic with these properties: **input** = each `OUTDATED`/`NEEDS_UPDATE` finding from checks 1-4 whose fix lies in a premise section (Summary, Current Behavior, Expected Behavior, Root Cause, Motivation, Steps to Reproduce, Proposed Solution); **qualifying change** = only a file path, line number/range, or citation anchor/symbol location, with the claim's meaning unchanged; **everything else** (a count that alters the claim, a changed behavior, status or premise) stays `NON_VALID`; **precedence** = any non-qualifying finding or any never-auto-correct verdict (`INVALID`, `RESOLVED`, `DECISIONS_VIOLATION`, `REGRESSION_LIKELY`, `POSSIBLE_REGRESSION`, `DEP_ISSUES`) makes the whole issue `NON_VALID`; **escape hatch** = when classification is uncertain, `NON_VALID`.
- Verification-asymmetry constraint: the §2C rationale for barring premise edits is that the post-correction `--check` re-pass checks claims against the codebase and cannot detect a rewritten premise. That reasoning does not apply to path and symbol-location fixes, because checks 1-2 and the B.0 anchor relocation re-test exactly those against the code. The relaxed wording should be bounded by this property (re-checkable against code), so the carve-out cannot widen to edits the re-pass cannot catch.

## Acceptance Criteria

- A run whose only verify findings are wrong path/symbol citations — each backed by a deterministic `ll-issues format-check` ref key — is repaired in-loop via the existing `VERIFY:CLAIMS_OUTDATED` route (with `verify_evidence` written) instead of ending `GATE_UNMET`.
- Premise-changing findings, findings not backed by a `format-check` key, and any mix of the two still persist as `NON_VALID`; the never-auto-correct set is unchanged.
- **Promotion of the BUG-3691 keys to blocking (added 2026-10-03):** BUG-3691 ships its new-rule and widened-scope format-check findings (defined-in vs imported-in, bare-filename resolution, widened scope, `stale_line_ref`) **advisory**. This issue's repair route must work from advisory keys (it reads them directly from `ll-issues format-check --format json`); promoting any of them to blocking (`has_blocking_gaps` / exit code) is allowed only once (a) this route exists and (b) a before/after run of `ll-issues format-check --all` over `.issues/` records the false-positive rate and the set of newly failing issues, with no unexplained rise in `rn-remediate` format-issue routing. Record the decision per key.
- **Only `examined_refs`-backed findings qualify:** a finding is "backed by a format-check key" only for citations present in BUG-3691's `examined_refs`; a model finding about an unexamined citation stays `NON_VALID`.
- Covered by prose pins in `test_enh3250_verify_issues_proposal_vs_code.py::TestClaimsOutdatedVerdict` (relaxed §2C wording, key-gating, `NON_VALID`-wins, §4 carve-out); the `test_builtin_loops.py` route table (`PRE_TABLE`) is unchanged and stays green — Option B′ adds no route, so no new route test is required.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-01 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Scope vs BUG-3691: "stays `NON_VALID`" applies only to premise-changing (non-citation) findings. An unbacked path/line/symbol-location finding is advisory and does not affect the verdict (BUG-3691 B8); format-check-backed citation findings take this issue's repair route. Revision/Acceptance wording saying "anything format-check does not back up stays `NON_VALID`" is superseded by this boundary.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:00 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-01T23:00:29 - `e877bc1c-48ea-4feb-ab39-87fd9cec4ed8.jsonl`
- `/ll:wire-issue` - 2026-10-01T22:55:34 - `d1b3dc57-235c-4dfc-938b-d540a6f69069.jsonl`
- `/ll:decide-issue` - 2026-10-01T22:49:22 - `268cb02f-8b6d-4e6b-b489-4d89e8acbc2e.jsonl`
- `/ll:refine-issue` - 2026-10-01T22:45:55 - `e0011095-7378-4cf4-9638-3e64fca04ccb.jsonl`
- `/ll:format-issue` - 2026-10-01T22:40:34 - `2692fd97-451f-440d-af08-de192622a289.jsonl`
- `/ll:capture-issue` - 2026-10-01T22:03:38 - `8a253271-7b3f-4496-adff-dcad85be0bc1.jsonl`

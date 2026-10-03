---
id: BUG-3708
type: BUG
title: 'verify-issues check B8: defer to format-check examined_refs for citation findings'
priority: P3
status: open
discovered_by: advise-review
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:05:31Z'
parent: EPIC-3694
blocked_by:
- BUG-3691
relates_to:
- ENH-3690
- BUG-3695
confidence_score: 77
outcome_confidence: 72
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3708: verify-issues check B8: defer to format-check examined_refs for citation findings

## Summary

`verify-issues` still resolves citations through the model's ad-hoc reads and greps, so a model-raised path/line/symbol-location finding can differ between passes of an unchanged issue (BUG-3689 run `refine-to-ready-issue-20261001T151155`: passes 1-2 saw every citation hold, pass 3 flagged two and misread bare `runner_spec.py` under a nonexistent `fsm/` directory). This is the prose half of the BUG-3691 split: add check **B8** to `commands/verify-issues.md` so the model defers to `ll-issues format-check` for the properties it actually examined. The detector half (new rules + `examined_refs`) is BUG-3691.

## Current Behavior

`commands/verify-issues.md` §2A/§2B does citation work with model reads/greps. Its only deterministic CLI calls are `ll-verify-evidence` (check B7) and `ll-issues format-check` for prose-dependency keys (§C step 3). The ref keys format-check already emits (`stale_file_ref`, `ambiguous_file_ref`, `stale_symbol_ref`, `mislocated_symbol_ref`) are ignored by `verify-issues`.

## Expected Behavior

Check **B8**, after check 7, consumes `ll-issues format-check <ID> --format json` for the same issue/code snapshot the model judged. Mechanical findings use the exact occurrence/property contract implemented in BUG-3691. Semantic content and premise judgments still require code evidence and remain model-decidable; full LLM verdicts are not promised to be deterministic.

| Coverage for the exact citation occurrence/property | Treatment in verify |
|---|---|
| `ok` | Demote a conflicting mechanical model finding to an advisory note; no verdict effect from that finding |
| Existing blocking gap key | Surface the deterministic finding even if the model missed it; deduplicate, then apply existing §2C/§2.5 verdict rules |
| New advisory gap key | Report it and any equivalent mechanical model finding as advisory; neither independently changes the verdict |
| Absent, unsupported, malformed or contradictory coverage | Fall back to current model judgment for that occurrence/property |
| Claimed content or premise consequence | Still verdict-bearing when supported by independent semantic evidence; a range/location check cannot decide it |

An entry proving tracked-index path resolution does not prove disk existence/readability, line range, symbol presence or definition. A `path_resolves: ok` cannot demote a finding that the tracked file is physically missing or unreadable in the working tree. An import-inclusive presence pass does not prove definition. A citation pass in one section does not override another occurrence. Missing findings do not mean passed checks.

## Motivation

Without B8, BUG-3691's deterministic checks do not stabilize the mechanical component of the verdict. Demotion based on missing gap lists can hide unexamined refs; promoting advisory results through verify would bypass the detector's measured advisory rollout. Both boundaries need an explicit contract before implementing the consumer.

## Proposed Solution

1. Add B8 after check 7, invoking format-check by `<ID>`; do not use `$ISSUE_FILE`, which the current §0/§1 examples never assign. In batch verify, use the **current per-issue ID**, not an empty command-level ID.
2. Match BUG-3691's `{ref, issue_line, issue_column, property, result}` records to the original full issue text. Properties are `path_resolves`, `line_in_range`, `symbol_resolves_in`, `symbol_defined_in`; raw ref keeps complete line/range/symbol forms. Match the exact occurrence and property, never a canonical file path alone. If the model finding cannot be located unambiguously, retain model judgment.
3. Apply the table above. Existing blocking citation keys are `stale_file_ref`, `ambiguous_file_ref`, `stale_symbol_ref`, `mislocated_symbol_ref`. New advisory keys are `advisory_stale_file_ref`, `advisory_ambiguous_file_ref`, `advisory_stale_symbol_ref`, `advisory_mislocated_symbol_ref`, `stale_line_ref`. An advisory deterministic failure must not regain verdict effect merely because the model reports the same mechanical defect. A content/premise exception must identify independent semantic evidence, not relabel that advisory defect.
4. **Findings exit status is not invocation failure:** valid single-ID JSON from exits **0 or 1** is consumable. Exit 1 often means unrelated structural gaps or blocking findings, not CLI failure. Unavailable command, no target, malformed JSON, missing/wrong-shaped `examined_refs` or unsupported entries yield silent fallback for unavailable coverage, matching B7's convention. Do not demote from unknown property/result values or conflicting entries for an occurrence/property.
5. Obtain results after the model's reads and re-run after any issue or cited-code edits before using them. Do not reuse stale metadata from a prior loop pass or from before a rewrite. Preserve `--check` as frontmatter-only persistence; B8 never repairs citations.
6. Name format-check as the resolution owner; do not restate its algorithms in command prose (EPIC-2938). Keep the existing §2B/§C/persistence/§3 anchors and prose baseline. Do not widen §2C's correction scope; ENH-3690 owns repair eligibility/promotion after this advisory boundary is in place.
7. Regenerate host mirrors with `ll-adapt --host <host> --apply` for gemini, kimi-code, qwen and codex; also regenerate omp **if its `.omp` mirror root is present**, matching the staleness gate's presence guard. Never hand-edit generated mirrors.

## Integration Map

### Files to Modify

- `commands/verify-issues.md` — B8 and any cross-reference needed to prevent earlier ad-hoc checks from overriding its mechanical results
- Host mirrors of `commands/verify-issues.md` — regenerate via `ll-adapt`
- `scripts/tests/test_bug3708_verify_issues_b8.py` (new) — scoped producer/consumer prose-contract tests

### Dependent Files (Callers/Importers)

- `scripts/little_loops/issue_parser.py`, `scripts/little_loops/issues/citations.py` (new) — producer-owned in BUG-3691, `scripts/little_loops/cli/issues/format_check.py` — producer of the locked occurrence/property/result contract; no duplicate resolver here
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — existing `verify_issue` and verdict dispatch; no new token/route in this issue
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — existing verdict classification/precedence unchanged
- ENH-3690 — may later authorize a narrowly scoped repair from advisory findings; this issue alone does not promote them
- BUG-3695 — serializes its B6/persistence edits after this command change

### Tests

- New B8 tests slice between check 7 and `#### C. Determine Verdict`, assert the invocation, complete identity/property contract, all table rows, advisory handling, exits 0/1 and fallback, batch-ID selection, freshness, tracked-but-missing file availability and content/premise exceptions
- Cross-check producer property/result names against BUG-3691's implemented schema, rather than asserting unrelated string presence anywhere in the command
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — existing verdict/table/persistence anchors remain valid
- `scripts/tests/test_verify_skill_prose.py::TestBaselineNeverIncreases`, `scripts/tests/test_docs_audience_gate.py`, `scripts/tests/test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` — retain prose/audience/mirror contracts
- These are command-contract tests. They do not prove the LLM obeys B8; repeated live evaluation is recorded separately below.

## Steps to Reproduce

1. Use the BUG-3689 trigger from `refine-to-ready-issue-20261001T151155`, with an imported-only definition attribution and a bare line-suffixed filename.
2. Compare verify passes over an unchanged fixture and code snapshot: ad-hoc mechanical citation findings can vary.

## Program Design

### Types

No new Python types. Consumer metadata contract:

- `examined_refs: list[CitationCheck]` — BUG-3691's occurrence/property records, serialized outside `FormatGaps`

### Signatures

`ll-issues format-check <ID> --format json` is the consumer boundary. Single-ID JSON has an `examined_refs` sibling list; `--all` deliberately remains a sparse gap report and is not a coverage source. The `check_format_gaps` coverage collector is producer-owned in BUG-3691; no Python signature change belongs here.

### Call Path

`verify_issue` -> per-issue B8 -> single-ID format-check / `check_format_gaps` -> exact occurrence/property lookup -> existing persistence -> `route_pre_score_obligation` / `classify_verify_verdict`. No repair, loop token or exit-code contract change.

## Implementation Steps

1. Land BUG-3691 and confirm its exact schema, advisory keys and compatibility tests.
2. Write B8 and reconcile earlier mechanical-check wording with its authority table. Preserve anchors and keep resolution algorithms in the CLI.
3. Add scoped contract tests, including valid exit-1 findings and same-file/different-range or different-scope occurrences. Regenerate mirrors using the hosts/presence guard above.
4. Correct the replay expectations: unsuffixed `runner_spec.py` has no new path coverage and stays model-decidable; a passing `runner_spec.py:N` range demotes only a mechanical path/range objection; definition-shaped `cli/loop/feed.py:terminal_size()` is an **advisory mislocation**, not a passing definition check. A missing/different claimed line content still requires a semantic finding.
5. Evaluate the same fresh citation fixture in three independent verify runs against a frozen code snapshot; record mechanical findings, whole verdicts and whether advisory results improperly changed them. Include a real existing blocking citation defect that the model initially overlooks. Treat this as live evaluation, not a deterministic pytest proof or a guarantee about all semantic verdicts.
6. Run `python -m pytest scripts/tests/`. Land before BUG-3695. ENH-3690 should use this exact coverage/severity policy when adding repair eligibility; serialize its overlapping command edits too.

## Impact

- **Priority**: P3 — detectors do not stabilize the mechanical component of verify without a consumer
- **Effort**: Small–Medium — command prose, focused contract tests, mirrors and repeated evaluation
- **Risk**: Medium — incorrect coverage can mask a defect; injecting existing blocking findings can change verify verdicts that previously missed them
- **Breaking Change**: No new verdict or CLI contract

## Acceptance Criteria

- [ ] B8 sits between check 7 and `#### C. Determine Verdict`, invokes single-ID format-check for the current issue and names the CLI as resolution owner.
- [ ] Exact occurrence/property passes demote only matching mechanical findings; missing coverage or another occurrence/property cannot demote them.
- [ ] Existing blocking deterministic failures are included even when the model misses them; new advisory findings and equivalent model findings have no independent verdict effect until ENH-3690 supplies an explicit policy.
- [ ] Path resolution, line bounds, import-inclusive presence and definition are distinct; claimed content/premise effects remain supported by independent semantic evidence.
- [ ] Valid JSON at exits 0/1 is consumed; failed/unavailable/malformed/unsupported coverage falls back; no stale pre-edit result is used.
- [ ] Scoped producer/consumer tests, existing anchors, prose baseline, audience gate and regenerated mirror checks pass; `python -m pytest scripts/tests/` exits 0.
- [ ] Three-run live evaluation records the mechanical findings and verdicts, including imported-only advisory mislocation, passing ranges, unexamined bare names and an existing blocking defect; limitations or failures are documented rather than hidden by contract-only tests.

## Related Key Documentation

- `docs/reference/CLI.md` — existing format-check contract (updated by BUG-3691)

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-03 (re-scored after the contract corrections)_

**Readiness Score**: 77/100 → STOP — ADDRESS GAPS (Dependencies hard override; the criteria sum alone would be PROCEED WITH CAUTION)
**Outcome Confidence**: 72/100 → MODERATE

### Gaps to Address

- `blocked_by: BUG-3691` is `open`. B8 consumes the `examined_refs` payload that BUG-3691 defines and has not yet built (`examined_refs` and `advisory_*` keys appear nowhere in `scripts/little_loops`). Land BUG-3691 first, then rerun confidence-check. This is the only blocker; `format-check` is clean and `check-design` passes.

### Concerns

- No B8 exists in `commands/verify-issues.md`, so there is no duplicate. The insertion point (after check 7, before `#### C. Determine Verdict` at line 249) is correct.
- Prose tests cannot prove the model obeys B8. Mechanical determinism and whole-verdict repeatability must not be conflated.

### Outcome Risk Factors

- Broad contract reuse: the consumer table must match BUG-3691's final schema exactly, and any producer drift forces a rewrite.
- The coverage-table semantics (demote / surface / advisory / fallback) are subtle prose. They are guarded by command-contract tests only, plus the three-run live evaluation.
- The change surface also includes four host mirrors regenerated via `ll-adapt`; there is no `.omp` root in this checkout.

The occurrence schema, property mapping, advisory policy, exit-1 handling and replay contradiction are now specified rather than left for the implementer. Remaining risk: prose tests cannot prove model compliance; mechanical determinism and whole semantic-verdict repeatability must not be conflated.

## Status

**Open** | Created: 2026-10-03 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-10-03T17:56:21 - `b5e6edc5-35e7-47c8-bd8f-3ec9a6ef2ef2.jsonl`
- `/ll:confidence-check` - 2026-10-03T17:52:30 - `7b5fbb18-2486-460d-9469-16b4a7432e0e.jsonl`
- `/ll:confidence-check` - 2026-10-03T17:18:05 - `e655cd0c-0c5d-446b-bee6-c9fe4cf5573e.jsonl`

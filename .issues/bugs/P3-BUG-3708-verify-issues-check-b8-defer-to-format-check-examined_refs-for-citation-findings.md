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
relates_to:
- ENH-3690
- BUG-3695
- BUG-3691
confidence_score: 95
outcome_confidence: 68
score_complexity: 14
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
| `ok` | Demote a conflicting mechanical model finding **of the same property** to an advisory note (see "Property-exact demotion" below); no verdict effect from that finding |
| Existing blocking gap key | Surface the deterministic finding even if the model missed it; deduplicate, then classify as below (check-1/check-4 `NEEDS_UPDATE` finding under §2C's correctable-scope rule) |
| New advisory gap key | Report it and any equivalent mechanical model finding as advisory; neither independently changes the verdict |
| Absent, unsupported, malformed or contradictory coverage | Fall back to current model judgment for that occurrence/property |
| Claimed content or premise consequence | Still verdict-bearing when supported by independent semantic evidence; a range/location check cannot decide it |

**Verdict mapping for a surfaced blocking key.** A deterministic `stale_file_ref` / `ambiguous_file_ref` / `stale_symbol_ref` / `mislocated_symbol_ref` is a check-1/check-4 `NEEDS_UPDATE` finding, classified by §2C's existing correctable-scope rule — no new verdict. Blocking keys only arise in Summary / Current Behavior / Root Cause / Context, so in practice the result is `NON_VALID` and routes through `refine_followup` unless §2C's scope already covers it. `## Context` is in neither §2C list today; B8 must rule on it explicitly (implementation step 2). `stale_file_ref` means "not git-tracked", so report it as **untracked**, not "missing" — a new, unstaged file would otherwise read as a stale reference.

**Property-exact demotion.** A pass is evidence only for its own property:

- `path_resolves: ok` is tracked-index resolution only. It demotes a "file doesn't exist" objection only if the file also exists on disk; a tracked-but-missing/unreadable file is never demoted.
- `line_in_range: ok` demotes only a "line is past end of file" objection, never a claim about what the line contains.
- `symbol_resolves_in: ok` is import-inclusive; it never demotes a "not defined here" finding (that needs `symbol_defined_in: ok`).
- A pass in one section/occurrence never overrides another occurrence. A missing entry means "not examined", not "passed".

## Motivation

Without B8, BUG-3691's deterministic checks do not stabilize the mechanical component of the verdict. Demotion based on missing gap lists can hide unexamined refs; promoting advisory results through verify would bypass the detector's measured advisory rollout. Both boundaries need an explicit contract before implementing the consumer.

## Proposed Solution

1. Add B8 after check 7, invoking format-check by `<ID>`; do not use `$ISSUE_FILE`, which the current §0/§1 examples never assign. In batch verify, use the **current per-issue ID**, not an empty command-level ID.
2. Match BUG-3691's `{ref, issue_line, issue_column, property, result}` records to the original full issue text. Match the exact occurrence and property (names in the CLI contract), never a canonical file path alone. If the model finding cannot be located unambiguously, retain model judgment. **Two sources, two jobs** (the producer-guard probe showed `examined_refs` alone drops blocking findings): *blocking* findings come from the top-level `stale_file_ref` / `ambiguous_file_ref` / `stale_symbol_ref` / `mislocated_symbol_ref` gap lists (they have no occurrence key — a plain stale-path mention with no `:N` or `:symbol` suffix gets a blocking `stale_file_ref` but **no** `examined_refs` entry, so match a model finding to it by ref string only); `examined_refs` is used for **demotion and advisory coverage**, deduplicated on `(issue_line, issue_column, ref, property)`. A blocking symbol result appears in both (same ref/claim) — count it once.
3. Apply the table above (blocking vs advisory key lists live in `docs/reference/CLI.md`; B8 names them by reference, not a restated list). An advisory deterministic failure must not regain verdict effect merely because the model reports the same mechanical defect. A content/premise exception must identify independent semantic evidence, not relabel that advisory defect. Apply the verdict mapping and property-exact demotion rules from Expected Behavior.
4. **Consumable = parses, not exit code.** Treat the output as usable only if stdout parses to a JSON object whose `examined_refs` is a list. Exit 0 and 1 are both fine (1 = blocking gaps), but exit 1 also covers not-found / errors with **non-JSON** output (verified: `format-check BUG-99999 --format json` prints `Error: Issue ... not found.` and exits 1), so never decide by exit code. An empty `examined_refs` list means no coverage → model judgment. Unavailable command, no target, non-JSON, malformed JSON, wrong-shaped `examined_refs` or unsupported entries → silent fallback, matching B7. Do not demote from unknown property/result values or conflicting entries for an occurrence/property.
5. **Freshness / single call.** Run format-check once, **after** the model's reads, and share that one result with §E step 3 (prose-dep keys) instead of calling it twice. Re-run only after a §4 issue edit. Do not reuse metadata from a prior loop pass (`normalize_structure` runs before the issue is edited and verified). Preserve `--check` as frontmatter-only persistence; B8 never repairs citations.
6. Name format-check as the resolution owner; do not restate its algorithms or producer semantics in command prose (EPIC-2938) — keep B8 to roughly **25 lines** and move any producer detail to `docs/reference/CLI.md`. Keep the existing §2B/§C/persistence/§3 anchors and prose baseline. Do not widen §2C's correction scope; ENH-3690 owns repair eligibility/promotion after this advisory boundary is in place.
7. **Reconcile checks 1 and 2.** Add a one-line "B8 governs examined occurrences" clause to check 1 ("Check files exist") and check 2 ("Verify line numbers"): where `examined_refs` has an entry for the occurrence/property, B8 decides the mechanical question; the model's ad-hoc read stands only for unexamined occurrences and for content/premise judgments.
8. **Modes and reporting.** B8 runs under `--check` (read-only, frontmatter persistence unchanged) and under batch (per-issue ID). B8 is **skipped** under `--from-evidence`, which re-checks only listed claims. Add a one-line citation summary to the §5 report (examined / demoted / surfaced / advisory counts). Name verify-issues B8 as a consumer in `docs/reference/CLI.md`'s format-check entry.
9. Regenerate host mirrors with `ll-adapt --host <host> --apply` for gemini, kimi-code, qwen and codex; also regenerate omp **if its `.omp` mirror root is present** (absent in this checkout), matching the staleness gate's presence guard. Never hand-edit generated mirrors.

## Integration Map

### Files to Modify

- `commands/verify-issues.md` — B8, the "B8 governs examined occurrences" clause in checks 1 and 2, an explicit `## Context` ruling in §2C, the §5 citation summary line, and `--from-evidence` skip wording
- `docs/reference/CLI.md` — name verify-issues B8 as an `examined_refs` consumer; keep producer detail here, not in the command
- Host mirrors of `commands/verify-issues.md` — regenerate via `ll-adapt`
- `scripts/tests/test_bug3708_verify_issues_b8.py` (new) — scoped producer/consumer prose-contract tests

### Dependent Files (Callers/Importers)

- `scripts/little_loops/issue_parser.py`, `scripts/little_loops/issues/citations.py` (new) — producer-owned in BUG-3691, `scripts/little_loops/cli/issues/format_check.py` — producer of the locked occurrence/property/result contract; no duplicate resolver here
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — existing `verify_issue` and verdict dispatch; no new token/route in this issue
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — existing verdict classification/precedence unchanged
- ENH-3690 — may later authorize a narrowly scoped repair from advisory findings; this issue alone does not promote them
- BUG-3695 — serializes its B6/persistence edits after this command change

### Tests

- New B8 tests slice between check 7 and `#### C. Determine Verdict` and assert structure, not wording: the invocation, the occurrence/property identity contract, all table rows, advisory handling, parse-based consumability (not exit code) and fallback, batch-ID selection, single shared call/freshness, `--check`/`--from-evidence` behavior and the checks 1/2 clause. Do not add caveat-string tests that pin prose phrasing.
- Import the property/result/gap-key constants from `little_loops.issues.citations` and `little_loops.issue_parser` instead of hard-coding strings, so producer drift fails the test.
- **Producer coverage contract (probed 2026-10-03, scratch fixture):** the guard "every blocking citation gap entry has an `examined_refs` entry" is **false** for plain path mentions. In `## Summary`/`## Context`, a backticked or bare stale path with no suffix raises blocking `stale_file_ref` with an empty `examined_refs` (only `path:N` / `path:symbol()` forms record `path_resolves`). Blocking `stale_symbol_ref` is covered. Pin this in a test (blocking plain-path ⇒ gap list only; blocking symbol ⇒ both) so B8's two-source rule can't silently regress; do not widen the producer here.
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

1. BUG-3691 has landed (`done`, commit `0c9c83ef5`); its schema matches this issue. The producer guard was probed and does **not** hold (plain-path blocking `stale_file_ref` has no `examined_refs` entry), so B8 uses the top-level blocking gap lists for surfacing and `examined_refs` for demotion/advisory only. Optionally file a follow-up to have the producer record `path_resolves` for plain path mentions (candidate under EPIC-3694).
2. Write B8 (≤ ~25 lines), the checks 1/2 clause, and an explicit §2C ruling for `## Context` (a blocking citation key found there is a check-1/check-4 `NEEDS_UPDATE` finding under the existing correctable-scope rule). Preserve anchors and keep resolution algorithms in the CLI.
3. Add scoped contract tests, including valid exit-1 JSON, exit-1 non-JSON (not-found) fallback, and same-file/different-range or different-scope occurrences. Update `CLI.md`. Regenerate mirrors using the hosts/presence guard above.
4. Correct the replay expectations: unsuffixed `runner_spec.py` has no new path coverage and stays model-decidable; a passing `runner_spec.py:N` range demotes only a mechanical path/range objection; definition-shaped `cli/loop/feed.py:terminal_size()` is an **advisory mislocation**, not a passing definition check. A missing/different claimed line content still requires a semantic finding.
5. **Non-blocking** live evaluation (does not gate closure; file a follow-up if it exposes drift): run a seeded citation fixture through three independent verify runs against a frozen code snapshot; record mechanical findings, whole verdicts and whether advisory results improperly changed them. Include a real existing blocking defect the model initially overlooks. This is evidence, not a pytest proof or a guarantee about semantic verdicts.
6. Run `python -m pytest scripts/tests/`. Land before BUG-3695. ENH-3690 should use this exact coverage/severity policy when adding repair eligibility; serialize its overlapping command edits too.

**Known limit:** `examined_refs` coverage is narrow (explicit `path:N` / `path:symbol` citations in a few sections; BUG-3708 itself yields 0 entries), so B8 will often not engage and does not eliminate BUG-3689-style variance for bare names or Proposed Solution citations. Widening producer coverage is a separate decision (candidate follow-up under EPIC-3694).

## Impact

- **Priority**: P3 — detectors do not stabilize the mechanical component of verify without a consumer
- **Effort**: Small–Medium — command prose, focused contract tests, mirrors and repeated evaluation
- **Risk**: Medium — incorrect coverage can mask a defect; injecting existing blocking findings can change verify verdicts that previously missed them (they land in premise sections, so they become `NON_VALID` and can add `refine_followup` cycles in `refine-to-ready-issue`)
- **Breaking Change**: No new verdict or CLI contract

## Acceptance Criteria

- [ ] B8 (≈25 lines) sits between check 7 and `#### C. Determine Verdict`, invokes single-ID format-check for the current issue, names the CLI as resolution owner, and checks 1/2 carry the "B8 governs examined occurrences" clause.
- [ ] Demotion is property-exact (path ok needs disk existence; line ok demotes only past-EOF; symbol-resolves never demotes "not defined"); missing coverage or another occurrence/property cannot demote.
- [ ] A surfaced blocking key is a check-1/check-4 `NEEDS_UPDATE` finding under §2C's correctable-scope rule, with an explicit `## Context` ruling and `stale_file_ref` reported as "untracked"; advisory findings and equivalent model findings have no independent verdict effect until ENH-3690.
- [ ] Consumability is decided by parseable JSON with a list-typed `examined_refs`, not exit code; non-JSON exit 1 (not-found), empty list, malformed or unsupported coverage falls back; one post-reads call is shared with §E step 3 and re-run only after §4 edits.
- [ ] `--check` runs B8 read-only, `--from-evidence` skips it, §5 report has a citation summary line, and `CLI.md` names verify-issues B8 as a consumer.
- [ ] Producer coverage-contract test passes (plain-path blocking ⇒ gap list only; blocking symbol ⇒ gap list and `examined_refs`); scoped tests import schema constants; existing anchors, prose baseline, audience gate and regenerated mirror checks pass; `python -m pytest scripts/tests/` exits 0.
- [ ] (Non-blocking) Live seeded-fixture evaluation recorded, or a follow-up filed; limitations are documented rather than hidden by contract-only tests.

## Related Key Documentation

- `docs/reference/CLI.md` — existing format-check contract (updated by BUG-3691)

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-03 (re-scored after BUG-3691 landed)_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Concerns

- The earlier `blocked_by: BUG-3691` gap is resolved: BUG-3691 is `done` (commit `0c9c83ef5`), `examined_refs` and the `advisory_*` keys exist in `scripts/little_loops`, and `ll-issues format-check BUG-3708` / `check-design` report no gaps.
- No B8 exists in `commands/verify-issues.md`; the insertion point (after check 7, before `#### C. Determine Verdict` at line 249) is correct. `scripts/tests/test_bug3708_verify_issues_b8.py` does not exist yet (expected).
- The ~25-line budget is tight for the two-source rule, the table and the mode/freshness clauses; the `## Context` ruling in §2C must be authored without widening the correctable scope.
- Prose tests cannot prove the model obeys B8. Mechanical determinism and whole-verdict repeatability must not be conflated.

### Outcome Risk Factors

- Moderate breadth: command prose, `CLI.md`, four regenerated host mirrors (no `.omp` root in this checkout) and a new test file — about 7 change sites, each subtle prose rather than mechanical.
- The coverage-table semantics (demote / surface / advisory / fallback) are guarded by command-contract tests only, plus the non-blocking three-run live evaluation.
- Broad contract reuse: the consumer table must match BUG-3691's schema exactly (import constants from `little_loops.issues.citations`), and any producer drift forces a rewrite.

## Status

**Open** | Created: 2026-10-03 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-10-03T18:39:57 - `026897e5-79d3-46c5-82b4-0205c55bab40.jsonl`
- `/ll:verify-issues` - 2026-10-03T17:56:21 - `b5e6edc5-35e7-47c8-bd8f-3ec9a6ef2ef2.jsonl`
- `/ll:confidence-check` - 2026-10-03T17:52:30 - `7b5fbb18-2486-460d-9469-16b4a7432e0e.jsonl`
- `/ll:confidence-check` - 2026-10-03T17:18:05 - `e655cd0c-0c5d-446b-bee6-c9fe4cf5573e.jsonl`

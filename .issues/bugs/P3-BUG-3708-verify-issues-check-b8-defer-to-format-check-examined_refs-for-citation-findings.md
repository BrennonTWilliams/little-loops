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
confidence_score: 65
outcome_confidence: 82
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# BUG-3708: verify-issues check B8: defer to format-check examined_refs for citation findings

## Summary

`verify-issues` still resolves citations through the model's ad-hoc reads and greps, so a model-raised path/line/symbol-location finding can differ between passes of an unchanged issue (BUG-3689 run `refine-to-ready-issue-20261001T151155`: passes 1-2 saw every citation hold, pass 3 flagged two and misread bare `runner_spec.py` under a nonexistent `fsm/` directory). This is the prose half of the BUG-3691 split: add check **B8** to `commands/verify-issues.md` so the model defers to `ll-issues format-check` for the properties it actually examined. The detector half (new rules + `examined_refs`) is BUG-3691.

## Current Behavior

`commands/verify-issues.md` §2A/§2B does citation work with model reads/greps. Its only deterministic CLI calls are `ll-verify-evidence` (check B7) and `ll-issues format-check` for prose-dependency keys (§C step 3). The ref keys format-check already emits (`stale_file_ref`, `ambiguous_file_ref`, `stale_symbol_ref`, `mislocated_symbol_ref`) are ignored by `verify-issues`.

## Expected Behavior

New check **B8** (after check 7) reads `ll-issues format-check <ID> --format json` and treats it as authoritative **only for citations listed in its `examined_refs` payload** (BUG-3691) and only for the properties recorded there: path existence/ambiguity, line-in-range, symbol definition location.

- A model finding of one of those kinds about an examined citation that format-check examined and passed is demoted to an advisory note that does not affect the verdict.
- A finding about a citation format-check did **not** examine (unsuffixed bare names, sections outside its scope, unrecognized forms) stays model-decidable and verdict-bearing.
- A cited line whose claimed *content* is absent or different, and any premise-changing citation finding, stays verdict-bearing: format-check cannot express it.
- Fail-open: invocation failure or a payload without `examined_refs` falls back silently to today's behavior (same wording as B7).

## Motivation

Without B8 the deterministic detectors from BUG-3691 do not change the verdict, because the model remains free to raise (or misread) citation findings on its own. Demotion must be keyed on what format-check examined; otherwise B8 would hide exactly the refs format-check leaves to the model (e.g. the 222 unsuffixed bare names measured in the 2026-10-02 review).

## Proposed Solution

1. Add **B8** to `commands/verify-issues.md` after §2B check 7, invoking `ll-issues format-check <ID> --format json` by `<ID>` (no `$ISSUE_FILE`: the §0/§1 shell blocks never assign it).
2. Name format-check as the owner of the resolution algorithm; do not describe the resolution steps (EPIC-2938 invariant, `test_verify_skill_prose.py::TestBaselineNeverIncreases`, `BASELINE_COUNT = 17`; no `python3 -c` / union-find wording).
3. Keep the `test_enh3250` anchors present and in order: `#### B. Verify Against Codebase`, `#### C. Determine Verdict`, `Persist the verdict to frontmatter`, `### 3. Request User Approval`.
4. Do not widen §2C's `CLAIMS_OUTDATED` correctable scope (BUG-3637 limited auto-rewrite deliberately); repair of pass-1 Wiring Phase / Root Cause citation defects is ENH-3690's route.
5. Regenerate host mirrors with `ll-adapt --host <gemini|qwen|kimi-code|codex> --apply` (never hand-edit).

## Integration Map

### Files to Modify
- `commands/verify-issues.md` — new check B8 after check 7
- Host mirrors of `commands/verify-issues.md` — regenerate via `ll-adapt`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `verify_issue` runs `/ll:verify-issues ... --check --auto`; no edit while no new verdict value is added
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `classify_verify_verdict`; unchanged (§2.5 precedence reuses existing verdicts)

### Tests
- `scripts/tests/test_bug3708_verify_issues_b8.py` (new) — B8 present between check 7 and `#### C. Determine Verdict`; consumes `ll-issues format-check`; names `examined_refs`; states the fail-open and content/premise-stay-verdict-bearing rules; modelled on `test_enh3126_verify_issues_graph_seeding.py`
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — slices on the §2B/§C/§3 anchors; must stay green
- `scripts/tests/test_verify_skill_prose.py::TestBaselineNeverIncreases` — B8 prose must not add prose markers
- `scripts/tests/test_docs_audience_gate.py` — no `scripts/` paths (use `little_loops.<module>`)
- `scripts/tests/test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` — fails until mirrors are regenerated

## Steps to Reproduce

1. Run `ll-loop run refine-to-ready-issue BUG-3689` (or any issue whose Tests/Wiring Phase cites a symbol via its importing module and a bare `name.py:N` file).
2. Compare per-pass verify summaries in `.loops/.running/<run>.log`: citation findings differ between passes of an unchanged issue.

## Program Design

### Types

- No new types. Consumes the `examined_refs` payload added to `ll-issues format-check --format json` by BUG-3691.

### Signatures

- `check_format_gaps(issue_path: Path, templates_dir: Path | None = None, ref_index: RefIndex | None = None, symbol_index: SymbolIndex | None = None) -> FormatGaps` — existing in `little_loops.issue_parser`; BUG-3691 makes it emit `examined_refs` (citation, property, result), which B8 reads via `ll-issues format-check <ID> --format json`. B8 itself is prose in `commands/verify-issues.md`.

### Call Path

`verify-issues` check B8 -> `ll-issues format-check <ID> --format json` -> `check_format_gaps` (BUG-3691) -> `examined_refs`

## Implementation Steps

1. Confirm BUG-3691 has landed `examined_refs` in `ll-issues format-check --format json`.
2. Write B8 per Proposed Solution; keep anchors and prose-baseline constraints.
3. Add the tests above; regenerate mirrors.
4. Replay the BUG-3689 case: a bare unsuffixed `runner_spec.py` finding stays verdict-bearing (not examined); an examined, passing `cli/loop/feed.py:terminal_size()` model finding is demoted.
5. Run `python -m pytest scripts/tests/`.
6. **Sequencing:** land before BUG-3695 (both edit `commands/verify-issues.md`, host mirrors and the prose baseline; serialize them).

## Impact

- **Priority**: P3 - without B8 the detectors do not stabilize the verdict
- **Effort**: Small - one prose check, tests, mirrors
- **Risk**: Medium - demoting model findings can hide real defects if the "examined" boundary is wrong; mitigated by keying on `examined_refs` and fail-open
- **Breaking Change**: No

## Acceptance Criteria

- B8 sits between check 7 and `#### C. Determine Verdict`, consumes `ll-issues format-check <ID> --format json`, and names format-check as the owner of resolution (asserted by test).
- B8 demotes a model finding only when its citation and property appear in `examined_refs` as passed; a finding about an unexamined citation stays verdict-bearing (asserted by prose test).
- A citation finding about claimed line *content* or a premise stays verdict-bearing.
- B8 is fail-open: invocation failure or missing `examined_refs` falls back to current behavior.
- `test_enh3250` anchors, the prose baseline and the docs-audience gate stay green; host mirrors regenerated; `python -m pytest scripts/tests/` exits 0.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-03_

**Readiness Score**: 65/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Concerns
- The `examined_refs` entry schema (`{ref, property, result}`, `property` ∈ `path_exists` | `line_in_range` | `symbol_defined_in`) exists only in BUG-3691's prose. B8 wording and the "model finding kind → property" mapping cannot be finalized until it lands.

### Gaps to Address
- **Unresolved `blocked_by`: BUG-3691 (open).** Remedy: land BUG-3691 (the `examined_refs` payload) first, or remove the dependency if B8 is reworked not to need it. Re-run `/ll:confidence-check BUG-3708` afterwards; with the dependency cleared, readiness would be ~85.

### Outcome Risk Factors
- B8 demotes model findings, so a wrong "examined" boundary can hide real defects; tests are string-presence only and cannot exercise the model's behavior. Mitigated by keying on `examined_refs` and fail-open.

## Status

**Open** | Created: 2026-10-03 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-10-03T17:18:05 - `e655cd0c-0c5d-446b-bee6-c9fe4cf5573e.jsonl`

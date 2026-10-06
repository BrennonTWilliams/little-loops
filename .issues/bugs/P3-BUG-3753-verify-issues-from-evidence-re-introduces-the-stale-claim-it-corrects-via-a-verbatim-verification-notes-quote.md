---
id: BUG-3753
type: BUG
title: Historical verification notes re-trigger blocking stale-file findings
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-06'
captured_at: '2026-10-06T01:01:37Z'
---

# BUG-3753: Historical verification notes re-trigger blocking stale-file findings

## Summary

A `verify-issues --from-evidence` correction can remove a stale current claim and quote it in `## Verification Notes`. The whole-file blocking file-reference scan then flags that historical token again, spending the loop's one correction attempt. A paraphrase/post-write-check instruction already landed; the remaining work is a narrow deterministic scan boundary plus regression coverage.

## Current Behavior

The ENH-3742 run `refine-to-ready-issue-20261005T180418` failed after correcting a slash-joined file shorthand and quoting it in Verification Notes. The subsequent check found the quote, exhausted the claim-correction budget and recorded `gate_unmet`.

`commands/verify-issues.md` already contains the paraphrase and post-write `format-check` rule from `310db44bb`; tracked host mirrors carry it. The affected issue was manually corrected. However, `scripts/little_loops/issue_parser.py`, `check_format_gaps`, still calls `classify_issue_refs(content, ref_index)` on the entire file. `normalize_structure` consumes directive gaps, so it does not repair this stale-file finding.

## Expected Behavior

Only references in exact historical `## Verification Notes` sections are omitted from the legacy blocking `stale_file_ref` scan. The same stale path anywhere outside those sections still blocks. The command keeps its paraphrase/post-write verification rule. No new loop state, correction attempt, advisory class or output schema is added.

## Steps to Reproduce

1. Freeze the original ENH-3742 correction-note case from git history, excluding unrelated transient verdict evidence.
2. Run `check_format_gaps`/`format-check` against it and observe a blocking stale path appearing only in Verification Notes.
3. Move or duplicate the same path into Current Behavior: it must remain blocking after this fix.

## Root Cause

The legacy reference aggregation has no historical-section boundary. A note quoting a repaired token therefore behaves as a current claim. The scan also prefers planned-new mentions anywhere in the document, so historical declarations can affect current classification.

## Proposed Solution

Inside `check_format_gaps`, compute fence-aware spans for every exact ATX H2 `Verification Notes` section. Use a copy with those spans masked by equal-length whitespace/newlines for the legacy stale-reference classification; do not change shared `classify_issue_refs` or `extract_file_paths`.

Apply these decided rules:

- Accept the exact heading with trailing whitespace; H3, suffixed/variant titles, and fenced heading text do not start an exemption.
- A section ends at the next real H1 or H2, or EOF. H3/H4 subsections stay inside the historical section. Cover every occurrence, not only the latest one.
- Preserve source offsets and line breaks. Quoted headings in a closed fence neither start nor end a span. If an unterminated fence makes a candidate exemption's boundary uncertain, retain that candidate's original text for the blocking scan; do not swallow the remaining document.
- Remove historical mentions before aggregating/classifying references. A stale path also mentioned elsewhere still blocks. A planned-new declaration appearing only in the historical span cannot exempt an unmarked active mention.
- Omit historical-only stale references rather than invent an advisory report. Keep the existing whole-file `ambiguous_file_ref` scan and the other structural/citation/symbol/line/CLI checks intact. This issue fixes the demonstrated stale-file feedback loop, not every possible historical claim type.

Keep the existing loop path `correct_claims` → `normalize_structure` → `clear_verify_verdict` → `verify_issue`. Clearing transient `verify_evidence` before the independent re-check is necessary: a token in canonical frontmatter remains outside the exemption. Pin this topology and the one-attempt budget; do not imply a direct `check_format_gaps` → budget call path.

## Program Design

### Types

A private list of historical `(start, end)` spans; existing `FormatGaps` fields and JSON output remain unchanged.

### Signatures

`check_format_gaps(issue_path, templates_dir=None, issue_statuses=None, ref_index=None, symbol_index=None, cli_index=None, *, examined_refs=None, project_root=None) -> FormatGaps`

The existing signature (annotations abbreviated above) stays intact; only the legacy blocking stale-file classification input is narrowed. Any new span/masking helper is private. Shared extraction APIs retain whole-file behavior.

### Call Path

Correction command writes the note → loop normalizes and clears transient verdict evidence → independent verification invokes `cmd_format_check` → `check_format_gaps` → scoped legacy `classify_issue_refs` returns no self-created stale-file blocker.

## Implementation Steps

1. Write behavioral tests for historical-only stale paths and the active/same-path control; implement the narrow fence-aware input mask.
2. Test repeated sections, H3 content, H1/H2 termination, variant/fenced headings, unterminated fences and historical planned-new declarations. Keep ambiguity and shared extraction behavior characterized.
3. Pin the landed command instruction and the real loop re-entry topology/budget. Use a frozen minimal reproduction derived from the historical issue; do not require that an entire unrelated issue has zero format gaps.
4. Review citation corpus expectations and explain the narrow omission in CLI/API documentation. Run focused format/citation/command/topology suites, then the full local suite.

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — private historical masking inside `check_format_gaps`.
- `scripts/tests/test_ll_issues_format_check.py` — narrow scan and boundary regressions.
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` or a new sibling test module — command instruction pin.
- `scripts/tests/test_builtin_loops.py` — existing-loop topology and correction-budget pin only.
- A minimal fixture under `scripts/tests/fixtures/issues/` (new file) — frozen stale-quote reproduction.
- `docs/reference/CLI.md`, `docs/reference/API.md` — exact blocking-scan exemption.

### Dependent Files

- `scripts/little_loops/text_utils.py` — reuse fence helpers; shared reference classification/extraction must retain their contracts.
- `scripts/little_loops/issues/citations.py` — existing section-aware/advisory checks remain unchanged.
- `scripts/little_loops/cli/issues/format_check.py` — current output fields/exit logic remain intact.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` and `scripts/little_loops/loops/rn-remediate.yaml` — consumers benefit from the same scoped blocker; no YAML edit/budget increase.
- `commands/verify-issues.md` and host mirrors — rule already landed. Regenerate mirrors only if further source prose changes are necessary.

## Acceptance Criteria

- [ ] A stale path only in exact historical H2 sections creates no blocking `stale_file_ref`; the same path outside them still blocks, even when also present or marked planned-new inside them.
- [ ] All section/fence/repetition boundaries above are covered; uncertain unterminated-fence spans retain blocking behavior.
- [ ] Existing ambiguity, structural, symbol, line and CLI checks remain intact, and shared reference extraction is unchanged.
- [ ] The minimal frozen reproduction verifies the stale-file behavior; existing corpus changes are reviewed explicitly rather than broad expectations weakened.
- [ ] Tests pin the command's paraphrase/post-write rule and the loop's normalize → clear transient verdict → independent re-check ordering with the existing one-attempt correction budget.
- [ ] Focused and full local suites pass. Documentation describes omission from this blocking scan without promising all historical findings are exempt.

## Impact

- **Priority**: P3 — a terminal correction feedback loop with an existing prose mitigation.
- **Effort**: Small/Medium — narrow parser behavior, regressions and documentation.
- **Risk**: Medium — all format-check consumers inherit the exemption; active-reference controls constrain it.
- **Breaking Change**: No output/schema/loop change.

## Review Notes

Reviewed on 2026-10-06. Settled omission versus advisory output, all-occurrence/fence boundaries, active duplicate mentions and historical planned-new declarations. Removed rejected loop-state wiring from the active plan and corrected the call path. Opus supported the narrow exemption (confidence 0.72), with dissent favoring advisory visibility. Cached scores/verdict were cleared because this specification changed; historical assessments are not current readiness evidence. No implementation changes were made.

## Related

BUG-3637, ENH-3690 and BUG-3695 are background for the existing correction flow.

## Status

**Open** | Reviewed: 2026-10-06 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-10-06T02:18:10 - `e2600ce5-ae49-45dd-9f4d-c7454cd772ad.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-06T02:14:49 - `dd470030-53a4-4ea7-a28e-a42612652be7.jsonl`
- `/ll:wire-issue` - 2026-10-06T02:10:41 - `f07bd331-c0c6-4aed-ba28-ade85ff49455.jsonl`
- `/ll:refine-issue` - 2026-10-06T02:02:43 - `a1b406f4-aba7-4d6b-9fb6-614b0249f344.jsonl`
- `/ll:format-issue` - 2026-10-06T02:01:35 - `7fee41a9-247a-46a6-853e-97ee7190a531.jsonl`
- `/ll:capture-issue` - 2026-10-06T01:01:57 - `89b97fde-6836-4bf2-b412-cd83564e6b38.jsonl`

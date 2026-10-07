---
id: ENH-3765
type: ENH
title: refine_followup gap-analysis adds contradictory Option B restatement beside
  rejected Option A
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-07'
captured_at: '2026-10-07T00:49:19Z'
relates_to:
- BUG-3763
- BUG-3764
- BUG-3767
---

# ENH-3765: refine_followup gap-analysis adds contradictory Option B restatement beside rejected Option A

## Summary

Additive gap-analysis can append a selected-option restatement beside rejected-option directives it is forbidden to remove. Protect candidate-bearing sections before the first additive write, including later Program Design repair gates, while allowing independent enrichment elsewhere. Report the residual for the operator; loop repair routing belongs to BUG-3763.

Observed on BUG-3761 in `.loops/.history/2026-10-07T000313-refine-to-ready-issue`: `refine_followup` took 359421 ms (about six minutes), added Option B restatements to Program Design/Impact, and left `unapplied_decision` unresolved.

## Current Behavior

The pass also added useful AC/research findings, so it was not a literal no-op. It nevertheless could not discharge the rewrite obligation. `refine_followup` has an unconditional next state; a line in model output does not control its shell routing.

The shared loop retry counter is incremented before gap-analysis starts. Its one retry is separate from the lifetime `max_refine_count` exemption supplied by the discriminated Session Log command. A marker emitted afterward cannot preserve or refund the loop attempt.

A guard inserted only in Step 5c is too late: Step 5a can already write findings. Covered-triage paths still reach Step 5c and later gates, and Step 6.7 can revise nonspecific Program Design. Protection must span the full additive-write path.

## Expected Behavior

Gap-analysis leaves sections named by rejected-option candidates unchanged, protects decision-derived Impact Effort/Risk conservatively, and continues independent additive work elsewhere. It reports which sections were withheld and the need for semantic review; eligible reconciliation requires confirmed verifier evidence. It does not present an appended competing design as a completed repair.

## Motivation

Keep an implementer's directives coherent while retaining useful refinement. BUG-3763's exhaustion guard avoids the observed post-reconcile retry; this command defense also protects manual invocation, misclassified `VERIFY:other` and other gate paths into gap-analysis.

## Proposed Solution

**A command-level, per-section write guard; no output-driven loop route, new flag, Python helper or counter change.**

### Early preflight

When `--gap-analysis` is active, resolve/read the issue and run `ll-issues format-check <ID> --format json` before any body write or scheduled findings application. Derive the canonical ID from the resolved issue when invoked with an explicit file path: refine accepts paths, while format-check requires an ID. Explicitly cover ordinary research, covered-triage, dry-run and late-gate paths. Read the structured `unapplied_decision_detail` candidates; do not parse human reason strings.

Consumable preflight data is a JSON object containing `unapplied_decision_detail` as a list, with every entry containing nonempty string `section` and `identifier` values. An explicitly empty list means no candidates; missing/non-list fields or malformed entries are indeterminate. Exit 1 may carry valid findings and remains consumable; a failed command/non-JSON error or unreadable issue is indeterminate. On an indeterminate preflight, make no body edits, report that the protection could not be assessed, and retain the ordinary non-dry-run Session Log convention when the target is safely readable; otherwise report that logging could not be completed. Do not silently treat failure as an empty candidate set.

### Section protection

When candidates exist:

- Resolve candidate identifiers and section headings against the full issue text and protect their actual containing H2s from every additive body-writing stage. Candidate pairs have no occurrence offsets; protect all matching parents when repeated headings or identifiers make attribution ambiguous. A nested `Files to Modify` normally protects Integration Map, but do not assume that parent when the issue places it elsewhere. If protection cannot be mapped safely, treat preflight as indeterminate. Do not append findings, selected-option restatements, warnings or replacement directives inside a protected section.
- Protect Impact Effort/Risk even though Impact is absent from the detector's section list. Preserve existing estimates and forbid appending an alternative decision-derived Effort/Risk restatement, including relocating it elsewhere to bypass the embargo. Original-byte preservation alone does not prevent the observed contradictory addition.
- A protected Program Design section cannot be revised by Step 6.7's specificity repair. Keep its unresolved gate visible. Recheck candidates before a later body-writing stage if an intervening edit can change the option/section structure; extend protection rather than bypassing it.
- The guard also bounds late stale-prose-dependency edits and duplicate-findings repairs: when a repair would touch a protected H2, withhold it and report the residual rather than letting a structural gate override the embargo.
- Continue additive changes in unrelated sections and the normal evidence-delta checks for owned additions. If the candidate names Proposed Solution, do not mutate its selection/rationale indirectly through later steps.
- Treat candidates as a conservative write embargo, not proof of incorrect prose or authorization to erase it. Historical research and shared vocabulary may be false positives; do not require every candidate to disappear, insert supersession markers to silence the detector, or launch an automatic full rewrite.

When preflight finds no candidates, retain ordinary gap-analysis behavior. This is not an Impact-only semantic detector: Impact drift without any scanner candidate remains the verifier's responsibility under BUG-3764.

### Reporting and lifecycle

Report `GAP_ANALYSIS:REVIEW_REQUIRED unapplied_decision` as an informational line with protected sections and candidate identifiers, changes applied elsewhere, and residual obligations. Raw candidates establish potential drift, not a proven rewrite requirement; the marker is not an exit status or a loop route. The eligible remedy is `/ll:reconcile-issue <ID> --from-verify-evidence` only after verifier evidence and a recorded selection establish eligibility; otherwise request semantic review rather than inventing a rewrite.

Non-dry-run invocations still append exactly one `/ll:refine-issue:gap-analysis` Session Log entry, including when every candidate-bearing section was skipped. Preserve the lifetime refinement-count exemption. `--dry-run` writes neither body nor Session Log and reports proposed protections; guard failures must not claim a completed clean pass.

When an embargo prevents the only required gate repair, record the locked sections and unmet obligation in command output, which loop callers already capture in the `refine_followup` output/event stream. The existing shared retry then ends at bounded `gate_unmet`; do not describe that expected refusal as convergence. Persist evaluation diagnostics under the harness's known run directory; the production command must not guess a run directory or require new caller wiring. False positives can therefore withhold useful work and require human review, even when no directive is semantically wrong.

### Decision Rationale

Review on 2026-10-06, including `/ll:advise` with `claude-opus-5-5` (confidence 0.75), chose conservative per-section protection. Refusing all enrichment on every raw candidate would discard useful independent work and amplify false positives. A model-output marker cannot route the existing slash-command state or undo its pre-spent counter. BUG-3763 therefore owns routing and budget behavior; this issue owns the command defense only.

Opus cautioned that false positives may withhold useful additions to a protected section. That is preferable to declaring its directives repaired by adding a competing design; semantic evaluation must record this limitation.

## Review Findings

- `commands/refine-issue.md` — the first possible writes precede Step 5c; Step 3.9's snapshot, Step 5a findings, Step 6 updates and Step 6.7 gates must all respect the protection. Step 6.8 still verifies actual unprotected additions.
- `scripts/little_loops/issue_parser.py` — `unapplied_decision_detail: list[dict[str, str]]` supplies section/identifier pairs. The existing detector excludes Impact and can flag historical/shared vocabulary.
- A disposable parser probe showed that appending the selected option beside rejected directives leaves the same candidate. Adding a restatement is not an in-place correction.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `refine_followup.next` is unconditional and shared retry counters advance before invocation. No loop change is assigned to this enhancement.
- BUG-3762's scanner candidates include intentional pieces of the A+C selection, so a candidate embargo must not imply that those identifiers are semantically rejected or require removal.

## Integration Map

### Files to Modify

- `commands/refine-issue.md` — early gap-analysis preflight, protected-section rules across every writing stage, late-gate handling, output and dry-run/no-op lifecycle.
- `scripts/tests/test_refine_issue_command.py` — section-scoped contract pins ensuring the guard is before first writes and covers covered triage and Step 6.7.
- `scripts/tests/test_ll_issues_format_check.py` — disposable executable candidate fixtures, including Program Design, nested Files to Modify, contradictory restatements and Impact's current exclusion.
- `docs/reference/COMMANDS.md` — gap-analysis's selective withholding behavior and unchanged refinement accounting.
- `.gemini/commands/refine-issue.toml`, `.qwen/commands/ll/refine-issue.md`, `.kimi-code/skills/ll-refine-issue/SKILL.md` — generated command mirrors; regenerate via `ll-adapt`.
- `scripts/tests/test_wiring_skills_and_commands.py` — registered-host mirror gate. Body-only source edits ordinarily leave the minimal Codex bridge unchanged.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/format_check.py` — existing `--format json` producer; no new field required.
- `scripts/little_loops/issue_parser.py` — unchanged candidate detector and projection.
- `scripts/little_loops/session_log.py`, `scripts/little_loops/cli/issues/refine_status.py` — existing gap-analysis discriminator and lifetime count exemption.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — caller and budget behavior owned by BUG-3763; no marker parsing added here.

### Similar Patterns

Covered-triage no-research reporting with Session Log append; Step 3.9 evidence snapshots before actual edits; Step 6.8's preservation of pre-existing material while checking owned additions.

### Tests

- Real candidate extraction: Program Design and nested Files to Modify are reported; Impact alone is not; appending a winner restatement leaves the rejected-directive candidate. Use synthetic disposable fixtures, not current BUG-3761.
- Contract pins name the H3-to-H2 containment rule, complete write-stage protection, preflight error versus findings exit status, dry-run and logging behavior. No fictional emission function or model-output parser is tested.
- Opt-in model evaluation compares protected H2s and existing Impact Effort/Risk byte-for-byte, allowing only the appended Session Log and independently justified unprotected additions. Include covered triage, late specificity repair, mixed gaps, a historical/shared-vocabulary candidate, all-sections-withheld and Impact-only/no-candidate cases.
- Check evidence deltas on actual unprotected additions and verify the single discriminated log entry/lifetime count. Model editing behavior is not proved by string-presence tests.
- Explicit-path/canonical-ID, missing/malformed detail fields, repeated headings with ambiguous parents, late dependency/findings repairs and absence of relocated competing Impact estimates are evaluated. A real-child scripted all-writes-withheld fixture exhausts the existing shared retry into `gate_unmet` with locked-section diagnostics; evaluate model withholding separately.

### Documentation

Command contract and reference; no CLI schema or loop configuration change.

### Configuration

No new setting.

## Program Design

### Types

Existing `FormatGaps.unapplied_decision_detail: list[dict[str, str]]` is the candidate input. A command-local set of containing H2 names controls protection; it is not a new persisted field or Python public type. Impact Effort/Risk protection is an additional conservative rule when any candidate exists.

### Signatures

No new Python signature:

- `check_format_gaps(issue_path: Path, templates_dir: Path | None = None, issue_statuses: dict[str, str] | None = None, ref_index: RefIndex | None = None, symbol_index: SymbolIndex | None = None, cli_index: CliSurfaceIndex | None = None, *, examined_refs: list[CitationCheck] | None = None, project_root: Path | None = None) -> FormatGaps` — existing parser interface, unchanged.
- `ll-issues format-check <ID> --format json` — existing command used by the preflight.

The review-required line is a documented report shape, not a callable function or an FSM verdict.

### Call Path

`refine_followup` or manual invocation -> `/ll:refine-issue --gap-analysis` -> early candidate preflight -> permitted unprotected additions -> discriminated Session Log (unless dry-run) -> guarded late checks/evidence delta -> residual report. Existing loop continuation is unchanged by this enhancement.

## Implementation Steps

1. Add the preflight before first possible body writes, including covered-triage paths. Distinguish valid findings JSON from an indeterminate probe.
2. Apply containing-H2 protection and Impact estimate protection to every body-writing stage, especially Step 5a, Step 5c, Step 6 and Step 6.7; retain independent additions and evidence checks.
3. Document the informational residual report and exact no-op/dry-run Session Log behavior. Do not add a loop route or alter either retry counter.
4. Add parser fixtures and contract pins; run the disposable model evaluation for protected bytes, independent enrichment and false positives.
5. Update command documentation and regenerate affected mirrors through `ll-adapt --host <host> --apply`; check codex, gemini, kimi-code, qwen and omp where tracked artifacts exist. Run the named focused tests and `scripts/tests/test_wiring_skills_and_commands.py`, then `python -m pytest scripts/tests/`.

## Scope Boundaries

This issue owns additive command protection and reporting. BUG-3763 owns the actual repair and exhaustion routing; BUG-3764 owns semantic classification, including Impact-only drift. No automatic full rewrite, raw-candidate loop route, refinement-count change or production-issue repair is included. This defense can land independently of the two bug fixes.

## Impact

- **Severity**: Contradictory directives and wasted work on a rewrite obligation; independent enrichment can still be useful.
- **Affected**: Gap-analysis command paths, including manual callers and retries reached for other gate failures.

## Acceptance Criteria

- Protection is established before any gap-analysis body edit and covers every later write stage. Candidate-containing H2s and existing Impact Effort/Risk remain byte-identical in disposable model evaluation while independent unprotected additions remain available.
- No alternative decision-derived Effort/Risk restatement is appended beside or outside the protected estimates. Late dependency/findings repairs respect the same embargo.
- The report identifies withheld sections/candidates and the need for semantic review without claiming confirmed drift, forcing candidate clearance or controlling loop routing.
- Explicitly empty candidates preserve normal behavior; missing/malformed candidate data and indeterminate preflight prevent body edits and report failure. Canonical-ID resolution for explicit paths, repeated/nested headings, ambiguous containment, historical/shared vocabulary, covered triage and all late repair stages are covered.
- Non-dry-run skipped passes append exactly one discriminated gap-analysis log entry; dry-run is read-only. Lifetime and loop counter rules are unchanged.
- Executable candidate fixtures, contract pins and disposable edit-quality evaluation cover the matrix above; focused and full local tests pass.

## Related Key Documentation

- `docs/reference/COMMANDS.md` — refine flags and gap-analysis behavior.
- `docs/guides/LOOPS_REFERENCE.md` — callers and shared retry budget.

## Status

**Open** | Created: 2026-10-07 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-10-07T01:51:25 - `a47df9fa-6eb0-42c9-bccf-a5644c5b0d50.jsonl`
- `/ll:format-issue` - 2026-10-07T00:51:36 - `9aaef30f-0230-47c7-ac7f-df1e0deadca8.jsonl`
- `/ll:capture-issue` - 2026-10-07T00:49:26 - `a47df9fa-6eb0-42c9-bccf-a5644c5b0d50.jsonl`

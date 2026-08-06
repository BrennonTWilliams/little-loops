---
id: BUG-3071
priority: P3
type: BUG
status: open
discovered_commit: 5d0a711f
discovered_branch: main
discovered_date: 2026-08-05
discovered_by: manual-investigation
labels:
- issues
- linter
- program-design
- diagnostics
testable: true
size: Small
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 89
score_complexity: 23
score_test_coverage: 23
score_ambiguity: 20
score_change_surface: 23
---

# BUG-3071: `program_design_nonspecific` names `Types/Signatures`, a heading its own parser rejects

## Summary

The Program Design gate's failure message reads:

> `no signature-shaped line found in Types/Signatures`

`Types/Signatures` is not a heading the parser accepts. `DESIGN_SUBSECTIONS`
(`scripts/little_loops/issues/program_design.py:64`) is
`("types", "signatures", "call path")` — three separate members, no combined entry.
`_evidence_body` (`:196`) keeps a line only when its enclosing subsection title is an
exact member, so a subsection literally titled `### Types/Signatures` is discarded
*before* signature parsing, and a perfectly well-formed signature inside it is invisible.

An author who follows the message literally writes the one heading guaranteed to fail.

## Current Behavior

Observed directly while writing BUG-3070: a correctly-shaped line

```
def run_release_gate(cwd: Path, *, base_dir: Path | None = None) -> int:
```

under `### Types/Signatures` failed the gate with `program_design_nonspecific`. Renaming
the heading to `### Signatures` — no change to the signature line — passed immediately.

The message is misleading in a second way: `_evidence_body` also keeps the **preamble**
(everything before the first subsection, `current is None` at `:212`), so a signature
needs no subsection at all. The message names one place, and it is not even a real one.

Three issues in the corpus have already transcribed the misleading string into their own
remediation notes, propagating it:

- `.issues/enhancements/P3-ENH-2978-pre-deferral-remedy-heuristic-ignores-measurement-gates.md:375`
- `.issues/enhancements/P2-ENH-2924-find-project-root-prefer-git-ancestor-over-nearest-ll.md:195`
- `.issues/enhancements/P2-ENH-2934-tamper-guard-fsm-adapter.md:334`

## Steps to Reproduce

1. In any issue's `## Program Design`, put a valid signature line under `### Types/Signatures`.
2. `ll-issues format-check <ID> --format json` → `program_design_nonspecific`.
3. Rename the heading to `### Signatures`, unchanged content → passes.

## Expected Behavior

The failure message names headings the parser actually accepts, so following it resolves
the failure rather than reproducing it.

## Root Cause

The message string is a human shorthand ("the types/signatures area") that reads as a
literal heading name. It was written to describe a *concept*; the parser matches *exact
titles*. The two drifted with nothing tying them together — the message at `:329` is a
hardcoded literal with no reference to `DESIGN_SUBSECTIONS`.

**The membership set is not the defect.** Corpus evidence is decisive: across `.issues/`
there are **0** occurrences of a combined `Types/Signatures` heading, against `### Signatures`
(119 files), `### Call Path` (123), `### Types` (71). The literal string `Types/Signatures`
appears in the repo *only* as this message (`program_design.py:329` and its spike copy
`scripts/tests/spike/program_design_specificity/program_design.py:197`). Nothing in the
corpus is silently failing because of the membership set; the message is the sole source
of the combined form.

## Proposed Solution

**Primary (required)** — reword `:329` to name the accepted locations:

```python
reasons.append(
    "no signature-shaped line found in Types, Signatures, or the section preamble"
)
```

Derive the list from `DESIGN_SUBSECTIONS` rather than restating it, so the two cannot
drift again.

**Secondary (defensive, optional)** — since the old message actively taught the combined
form, normalize a slash-joined title in `_subsection_title` by admitting any component:
treat `types/signatures` as matching if any `/`-split part is in `DESIGN_SUBSECTIONS`.
This makes already-written issues carrying the combined heading grade correctly instead
of silently dropping their evidence.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- **Convention evidence for the primary fix**: "must be one of" / "here are the valid values" diagnostics elsewhere in this codebase are built by joining the canonical collection at message-construction time, never restated as a separate literal — `fsm/validation/structural_rules.py:93-94,116-117,233,1613`, `pii.py:75`, `queue_store.py:230`, `session_store/queries.py:75`, `history_reader.py:944,1776,1948`, `fsm/validation/_base.py:161`, `compaction/instant.py:136,144` (derives prompt/fallback header text from the same `SECTION_HEADERS` tuple it displays). `program_design.py:329` is presently the outlier in this codebase — a hand-typed literal with zero structural connection to `DESIGN_SUBSECTIONS`.
- **Test precedent for the sync-assertion AC**: `scripts/tests/test_hook_intents.py:827-855` (`test_dispatch_table_intent_event_name_usage_stay_consistent`) splits a usage string into tokens and asserts set equality against a canonical enumeration (`_dispatch_table()`), failing with the symmetric difference on mismatch. This is the closest existing shape to follow for the new "every heading named in the message is a member of `DESIGN_SUBSECTIONS`" test.
- **Secondary fix has no existing precedent**: checked `_subsection_title`, `_subsection_body`, and every `.split("/")` usage across `scripts/little_loops/` (`parallel/file_hints.py`, `init/introspect.py`, `git_operations.py`, `issue_history/debt.py`, `issue_history/hotspots.py`, `hooks/learning_tests_gate.py`, `cli/loop/layout.py`) — none split a heading/title and check membership of the parts against a canonical set. The slash-normalization in the Secondary proposal would be genuinely new logic, not an extension of anything already in the codebase.

## Program Design

**Invariant.** Every heading named by a `program_design_nonspecific` reason is a heading
`_evidence_body` retains.

### Signatures

```python
def grade_program_design(body: str, resolver: Resolver) -> DesignVerdict:
def _evidence_body(body: str) -> str:
def _subsection_title(line: str) -> str | None:
```

`DESIGN_SUBSECTIONS: tuple[str, ...]` is the single source the message must be built from.

### Call Path

- `little_loops.issue_parser._gate_program_design` (`issue_parser.py:131`) →
  `grade_program_design` (`program_design.py:303`) → `_evidence_body` (`:196`) →
  `parse_signature_lines` (`:217`)
- `issue_parser.py:617` appends `program_design_nonspecific` with the reason text.

## Acceptance Criteria

- [ ] The string `Types/Signatures` no longer appears in
      `scripts/little_loops/issues/program_design.py`.
- [ ] The reason text is derived from `DESIGN_SUBSECTIONS`, not a duplicated literal.
- [ ] A test asserts every heading name in the message is a member of `DESIGN_SUBSECTIONS`
      (or the documented preamble), so future edits cannot reintroduce the drift.
- [ ] `python -m pytest scripts/tests/` exits 0.
- [ ] If the secondary fix is taken: a `### Types/Signatures` subsection with a valid
      signature line grades specific.

## Impact

Low severity, real friction. The gate is correct; only its diagnostic is wrong. The cost
is that the message routes authors *away* from the fix, and it has already been copied
verbatim into three issue files as remediation guidance.

## Integration Map

- `scripts/little_loops/issues/program_design.py` — message and (optionally) title matching.
- `scripts/little_loops/issue_parser.py:131`, `:617` — gate wiring; consumes the reason
  text only, no change expected.
- `scripts/tests/spike/program_design_specificity/program_design.py:197` — spike copy,
  out of scope (frozen spike artifact).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issues/research_triage.py:349` (`_program_design_unmet`) — calls
  `grade_issue_section` and joins `verdict.reasons` verbatim into its own evidence string
  at `:372`, the same pass-through pattern as `issue_parser.py:617`. A second, previously
  unlisted consumer of the reason text; no change expected, but must not break. [Agent 1 finding]
- `scripts/little_loops/cli/issues/format_check.py:149-150` — prints `program_design_nonspecific`
  reason text verbatim via `ll-issues format-check`; no change expected. [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_program_design_gate.py` — add the sync-assertion test here (new
  method in `TestGrading` or a new class), following `test_hook_intents.py:827-855`'s
  `TestDispatchTable.test_dispatch_table_intent_event_name_usage_stay_consistent` shape:
  split the new message into heading tokens and assert set equality against
  `DESIGN_SUBSECTIONS` (plus the documented preamble exception). No existing test in this
  file asserts the literal old string, so nothing breaks — this is purely additive. [Agent 3 finding]
- `scripts/tests/test_research_triage.py` — `TestProgramDesignGateOverride` (line 384) has
  no case that reaches `verdict.reasons` via `_program_design_unmet` for a
  signature-less-but-nonempty-nonboilerplate body; its three existing cases short-circuit
  at `"section missing"`/`"section empty"`/`"section boilerplate"` before reaching
  `grade_issue_section`. Optional new test to cover the second reason-text consumer
  end-to-end. [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- `scripts/tests/test_program_design_gate.py` — existing test file for this gate (module docstring cites originating issue; tests grouped into `Test*` classes, e.g. `TestGrading`, with declarative method names like `test_reproduction_lines_from_bug_2960`). The new sync-assertion test belongs here, following this file's convention rather than a new file.
- `program_design.py:333` — the sibling `no call-path anchor resolves against the repo: {', '.join(anchors)}` reason already interpolates a runtime-derived value via f-string join; the fix at `:329` brings that line in line with a pattern already present two lines away in the same function.
- `issue_parser.py:617` — confirmed pass-through: `verdict.reasons` is joined with `"; "` and prefixed with the section name (`"Program Design: "`) with no rewriting, so whatever string `grade_program_design` returns reaches `program_design_nonspecific` verbatim.

## Related Key Documentation

- `scripts/little_loops/issues/program_design.py` module docstring (resolution-indifference contract)

## Status

Open. Root cause confirmed by corpus evidence; message-fix vs. membership-fix decided in
favor of the message.


## Session Log
- `/ll:confidence-check` - 2026-08-06T02:28:10 - `9a303797-dd2e-465b-82b0-9952a9e6503a.jsonl`
- `/ll:verify-issues` - 2026-08-06T02:26:52 - `d10f284f-800d-4288-9288-7d13118a8c95.jsonl`
- `/ll:wire-issue` - 2026-08-06T02:25:18 - `76885966-401d-4c5e-9b76-1f9b9dd3bccf.jsonl`
- `/ll:refine-issue` - 2026-08-06T02:18:59 - `5fee6689-6af2-4cd7-be3d-79729fbae839.jsonl`

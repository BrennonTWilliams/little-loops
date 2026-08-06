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

## Related Key Documentation

- `scripts/little_loops/issues/program_design.py` module docstring (resolution-indifference contract)

## Status

Open. Root cause confirmed by corpus evidence; message-fix vs. membership-fix decided in
favor of the message.

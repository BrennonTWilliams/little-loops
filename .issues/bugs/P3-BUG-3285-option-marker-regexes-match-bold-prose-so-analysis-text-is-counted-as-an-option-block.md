---
id: BUG-3285
type: BUG
title: Option-marker regexes match bold prose, so analysis text is counted as an option
  block
priority: P3
status: open
discovered_by: manual-review
discovered_date: '2026-08-21'
captured_at: '2026-08-21T18:55:00Z'
labels:
- issue-parser
- locate-options
- decide-issue
- false-positive
relates_to:
- BUG-3279
- BUG-3278
size: Medium
---

# BUG-3285: Option-marker regexes match bold prose, so analysis text is counted as an option block

## Summary

The `bold_label` option marker is matched by prefix only: any line beginning `**Option <X>` is
treated as the start of an enumerable option block, regardless of what follows on that line.
Refinement prose routinely opens lines with `**Option A evidence**:`, `**Option B was already
applied**:`, `**Option A implementation spec**` — commentary *about* an option, not an option — and
every one of those is counted and spanned as if it were a fifth, sixth, seventh option.

## Current Behavior

Two regexes carry the defect independently:

- `_OPTION_PATTERNS[1]` (`scripts/little_loops/issue_parser.py:1893`) —
  `r"^\*\*Option\s+[A-Za-z0-9]+.*?\*\*"`, the `bold_label` tier, backing
  `locate_enumerable_options` → `ll-issues locate-options` / `ll-issues check-decidable`.
- `_OPTION_HEADING_RE` (`:2210`) — `r"^(?:###\s+Option\s+[A-Za-z0-9]|\*\*Option\s+[A-Za-z0-9]+)"`,
  backing `_option_block_spans` → `_unapplied_decision`, and `_iter_option_blocks` →
  `locate_unresolved_options` / `count_unresolved_options` / `ll-issues check-open-questions`.

Neither requires the bold run to *end* after the option identifier, so `**Option A evidence**` is
indistinguishable from `**Option A**` to both.

Live, via the public API (2026-08-21):

```
$ python -c "from little_loops.issue_parser import locate_enumerable_options; ..."
ENH-2967  count=4  pattern=bold_label
  Option A (preferred): a dedicated exit-code check     ← real
  Option B: a derived field on the JSON payload         ← real
  Option A evidence                                     ← prose
  Option B evidence against                             ← prose

BUG-1484  count=4  pattern=bold_label
  Option A                                              ← real
  Option B                                              ← real
  Option A implementation spec                          ← prose
  Option B was already applied                          ← prose
```

Corpus scale: of **362** issues under `.issues/` with ≥2 located options, **31** have a repeated
option letter — the signature of a phantom block, since a genuine option list does not reuse a
letter. (A handful of those 31 are legitimate two-decision issues — FEAT-3078, FEAT-2878 — so 31 is
an upper bound on affected issues, not a count of confirmed phantoms.)

## Steps to Reproduce

1. `python -c "import sys; sys.path.insert(0,'scripts'); from little_loops.issue_parser import
   locate_enumerable_options; import pathlib;
   r=locate_enumerable_options(pathlib.Path('.issues/enhancements/P3-ENH-2967-autodev-redderives-design-fail-predicate-in-three-blocks.md').read_text());
   print(r.count, [o.label for o in r.options])"`
2. Observe `count=4` with two of the four labels being `Option A evidence` / `Option B evidence
   against`.
3. Confirm ENH-2967's `## Proposed Solution` presents exactly **two** options; the other two lines
   are the refinement pass's evidence commentary.

## Expected Behavior

An option marker is a line whose bold run *is* the option — `**Option A**`, `**Option A: <title>**`,
`**Option A (preferred): <title>**`. A line whose bold run continues into commentary about an
option (`**Option A evidence**`, `**Option B was already applied**`) is prose and starts no block.

## Motivation

Three consumers degrade, in increasing order of consequence:

1. **`ll-issues check-decidable` over-counts.** An over-count skips a `/ll:refine-issue` detour that
   would otherwise run — the docstring at `:1885-1890` explicitly accepts approximate matching here,
   so this is the mildest effect and arguably within the stated tolerance.
2. **`/ll:decide-issue` Phase 4 scores phantom options.** Extraction hands the scoring agent a
   block whose "option" is an evidence note, so the agent scores commentary as a candidate.
3. **`ll-issues check-open-questions` reports phantom unresolved options.** A phantom block carries
   no `> **Selected:**` callout, so it counts as unresolved forever. This flips the exit code of the
   first probe in `resolve-decision.yaml`'s gate (`:63`), which can re-enter `decide` on an issue
   that is fully decided.

There is also a measurement interaction with **BUG-3279**: that issue's 151-issue corpus flip is
computed over a block set that includes these phantoms, so its blast-radius numbers partly reflect
this defect rather than the boundary change alone. BUG-3279's Rule 3 (section-scope
`### Decision Rationale`) incidentally neutralizes consequence 3 for decided issues, but does
nothing for consequences 1 and 2 or for undecided issues.

## Proposed Solution

Require the bold run to terminate at the end of the option identifier. Sketch — tighten both
regexes so the closing `**` may be preceded only by an optional title separated by `:` or a
parenthetical qualifier, e.g.

```
\*\*Option\s+[A-Za-z0-9]+(?:\s*\([^)]*\))?(?:\s*[:—-][^*]*)?\*\*
```

The load-bearing change is that `evidence`, `implementation spec`, `was already applied` — bare
words following the identifier with no `:` / `—` separator — no longer match.

**Validate the tightening against the corpus before committing to a pattern.** The two regexes are
matched by a wide range of real formatting in `.issues/`; the acceptance bar is that the 31
repeated-letter issues above lose their phantom blocks while no issue loses a real option. That is
directly measurable — run `locate_enumerable_options` over all of `.issues/` before and after and
diff the label lists.

### Open question — should the two regexes converge?

`_OPTION_PATTERNS[1]` and `_OPTION_HEADING_RE` encode the same intent with different text and are
fixed independently today. BUG-3279 already argues that parallel implementations of one rule are
why its defect recurred after ENH-3256. Worth deciding here whether the bold-marker sub-pattern
becomes a shared module-level constant, following the existing hoisting convention
(`_H3_HEADING_RE` `:1196`, `_OPTION_HEADING_RE` `:2210`, `_DECISION_RATIONALE_HEADING_RE` `:1316`).

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — `_OPTION_PATTERNS[1]` (`:1893`) and `_OPTION_HEADING_RE`
  (`:2210`)

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/locate_options.py`, `check_decidable.py`,
  `check_open_questions.py` — consume the fixed functions' output; no code change expected
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` (`:63`) — reads only exit codes; no
  code change, but its gate behavior changes on issues that currently carry phantom blocks

### Tests

- A fixture whose Proposed Solution has two real `**Option A/B: …**` markers plus
  `**Option A evidence**:` and `**Option B was already applied**:` prose lines — assert `count == 2`
  and that neither prose line appears as a label
- Preserve the accepted real shapes: `**Option A**`, `**Option A: title**`,
  `**Option A (preferred): title**` — assert each still matches
- A corpus-level guard mirroring the acceptance bar: assert no issue in `.issues/` reports a
  repeated option letter from a single option group

## Program Design

### Types

No new or changed types. `LocatedOption` / `LocatedOptions`
(`scripts/little_loops/issue_parser.py:1907`, `:1925`) keep their current fields; only how many
`LocatedOption`s a document yields changes.

### Signatures

No signature changes. The edit is confined to two module-level regex constants:

- `_OPTION_PATTERNS: tuple[re.Pattern[str], ...]` — the four precedence tiers; element `[1]` is the
  `bold_label` tier and is the one tightened (`scripts/little_loops/issue_parser.py:1891-1898`).
- `_OPTION_HEADING_RE: re.Pattern[str]` — the shared `### Option X` / `**Option X` marker used by
  the two span-iterating siblings, whose bold alternative is tightened identically
  (`scripts/little_loops/issue_parser.py:2210`).

Consumers whose behavior shifts without changing shape:

- `locate_enumerable_options(content: str) -> LocatedOptions` — returns a lower `count` on affected
  issues (`scripts/little_loops/issue_parser.py:2134`).
- `locate_unresolved_options(content: str) -> tuple[int, str | None]` — stops counting phantom
  blocks as permanently unresolved (`scripts/little_loops/issue_parser.py:2249`).
- `_unapplied_decision(content: str) -> list[str]` — stops treating evidence prose as a rejected
  option block (`scripts/little_loops/issue_parser.py:1392`).

### Call Path

`_OPTION_PATTERNS[1]` → `_locate_options_in_text` → `locate_enumerable_options` →
`ll-issues locate-options` / `ll-issues check-decidable` / `/ll:decide-issue` Phase 3.

`_OPTION_HEADING_RE` → `_option_block_spans` → `_unapplied_decision` → `ll-issues format-check`;
and `_OPTION_HEADING_RE` → `_iter_option_blocks` → `locate_unresolved_options` →
`count_unresolved_options` → `ll-issues check-open-questions` → `resolve-decision.yaml` gate
(`:63`).

### Decision Rules

One rule, applied identically in both regexes: a bold option marker matches only when the bold run
closes at the end of the option identifier, optionally preceded by a parenthetical qualifier and/or
a separator-introduced title (`:` / `—` / `-`). A bold run continuing into bare words after the
identifier is prose and starts no block. No new gate, threshold, or keyword list.

## Sequencing

Independent of **BUG-3279** — different regexes, different failure mode — but landing this **first**
makes BUG-3279's corpus regression check readable, since its before/after counts stop moving for
phantom-block reasons. Not a hard dependency in either direction.

## Impact

- **Priority**: P3 — real false positives with a live path to re-deciding decided issues, but the
  most consequential effect (consequence 3) is partially masked today by BUG-3279's absorption bug
  and would be further masked by that issue's Rule 3
- **Effort**: Medium — two regexes and a corpus validation pass; the work is in proving the
  tightening doesn't drop real options, not in writing it
- **Risk**: Medium — over-tightening silently drops genuine options, which is worse than the current
  over-count. The corpus before/after diff is the control
- **Breaking Change**: No — `count` falls on affected issues; no output shape changes

## Root Cause

Both option-marker regexes anchor on a prefix (`**Option <X>`) and never constrain what follows
before the closing `**`, so bold *commentary about* an option is structurally identical to an option
marker.

## Status

**Open** | Created: 2026-08-21 | Priority: P3


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-21T19:06:56 - `8c9f6596-f570-42d1-a2a2-c4e750b706f8.jsonl`

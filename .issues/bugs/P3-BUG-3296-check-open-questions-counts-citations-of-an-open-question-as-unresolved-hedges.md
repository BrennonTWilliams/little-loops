---
id: BUG-3296
type: BUG
title: check-open-questions counts citations of an open question as unresolved hedges
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-22'
captured_at: '2026-08-22T23:58:01Z'
parent: EPIC-3290
labels:
- issue-parser
- check-open-questions
- false-positive
- refine-to-ready-issue
- open-questions
---

# BUG-3296: check-open-questions counts citations of an open question as unresolved hedges

## Summary

`_OPEN_QUESTION_SIGNAL_RE` (`issue_parser.py:2604`) treats a *citation of* an open question as a
*declaration of* one. A line that points at a question — `§ *Open question*`, `(see Open
Question)`, `(per this issue's Open Question)` — or that merely quotes the vocabulary inside a
code span — `` `"open question"` ``, `` `## Open Questions` ``, `` `_OPEN_QUESTION_SECTIONS` `` —
is counted as an unresolved hedge, forever, because nothing ever "answers" a cross-reference.

This is the **unnumbered sibling of BUG-3169** (done), titled *"check-open-questions counts
cross-references to numbered open questions as unresolved hedges"*. That fix added a negative
lookahead for *numbered* citations:

```python
r"|\bopen questions?\b(?!\s*[#:]?\s*\d)"   # BUG-3169: prose hedge anywhere, but never a numbered citation
```

`open question #3` is now correctly ignored. `see Open Question` and `` `"open question"` `` are
not — the same defect class BUG-3169 named ("POSITION plus a declaration boundary, not the mere
presence of" the token), on the two shapes it did not reach.

## Current Behavior

Measured across `.issues/` (3199 files, tree `64c4159e7`): **14 issues** carry at least one
counted item that is purely a citation, and on **11 of them** those citations are the *only*
thing holding `ll-issues check-open-questions` at exit 1.

Live on this epic's own BUG-3285, whose two counted items are both in `## Integration Map` and
both point at a question decided six lines below the pointer:

```
$ ll-issues check-open-questions 3285
OPEN_QUESTIONS_REMAIN: 3285 — 2 open question(s) and 0 unresolved option(s)
```

1. ``- `scripts/little_loops/issue_parser.py` — … (convergence decision, § *Open question*; …)``
2. ``- `docs/guides/DECISIONS_LOG_GUIDE.md` (`:198`) — … (per this issue's Open Question)``

Both cite `### Open question — should the two regexes converge?`, which carries a
`> **Decided 2026-08-21 (epic review): yes …**` callout. There is no open question on that issue.

## Expected Behavior

An item declares an open question when it *asks* one. An item that names, quotes, or points at a
question — in a code span, or after a citation lead-in (`§`, `see`, `under`, `per`, `On the`) — is
a reference and counts as nothing.

## Motivation

`cmd_check_open_questions` exits 0 only when **both** halves are zero:

```python
if unresolved_options == 0 and open_questions == 0:   # locate_unresolved_options AND count_open_questions_in_sections
```

so a phantom hedge holds that exit code at 1 no matter how clean the option half is. Consumers:
`resolve-decision.yaml:63`, `refine-to-ready-issue.yaml:404` (`check_hedges`), and `autodev.yaml`.

**This is not a loop defect and does not livelock.** `refine-to-ready-issue.yaml`'s
`check_hedge_attempts` (`:411`, BUG-3170) already bounds it — `output_numeric lt 2`, so one
hedge-forced refine per run, then fall through to `check_placeholders`. Its comment states the
premise outright: *"the scan is an absolute-zero probe over vocabulary with no answer/hedge
distinction, so a residual count is the steady state for a well-refined issue."* The loop is
correct; the probe is what is wrong.

The cost is therefore bounded but real, and slightly self-defeating: the forced pass is
`/ll:refine-issue --auto`, which is **additive** — ENH-3031's own comment notes hedge vocabulary
"accumulates via `--gap-analysis` (additive, never removes content) and is never subsequently
closed." So a phantom hedge spends a refine cycle on an already-refined issue and can deposit more
of the vocabulary that caused it.

## Proposed Solution

Mask citations out of the item text *before* signal matching, inside
`_count_unresolved_items_in_text` — after the wrapped-continuation join, so item segmentation is
untouched (see § *Root Cause* for why the segmentation ordering is load-bearing):

```python
_CODE_SPAN_RE = re.compile(r"`[^`\n]*`")
_OQ_CITATION_RE = re.compile(
    r"(?:§|see|under|per|On the|referenced in|cited in)\s+[*_\"'“]{0,2}(?:this issue's\s+)?open questions?\b"
    r"|[\"“]\s*Open Questions?\b",
    re.IGNORECASE,
)
```

applied to `joined` (equal-length filler, so offsets and any future span reporting stay valid)
before `_OPEN_QUESTION_SIGNAL_RE.search(...)`. The `_RESOLVED_QUESTION_MARKER_RE` check runs
against the **unmasked** text, unchanged.

Note the code-span mask necessarily applies to *all* `_OPEN_QUESTION_SIGNAL_RE` alternatives, not
just the `open questions?` one — a quoted `` `"decision point"` `` in a vocabulary list is the same
false positive. That is intended and is the source of two of the measured deltas (`ENH-2446` 2→1,
`BUG-2820` 2→1).

### Corpus differential — measured 2026-08-22 at `64c4159e7`

Harness note: `count_open_questions_in_sections` scans via `_section_body` (**H2-only, first
occurrence**), *not* `_heading_bodies`. A differential built on the latter over-scans by ~4x and
reports spurious count *rises*; any re-measurement must use `_section_body`.

**14 issues change. Zero counts rise** — a suppression must be a pure subtraction, and this one
is. **11 gate exit codes flip 1→0**:

| Issue | hedges b→a | opts | exit b→a |
| --- | --- | --- | --- |
| `BUG-3285` | 2→0 | 0 | 1→**0** |
| `ENH-2821` | 2→0 | 0 | 1→**0** |
| `BUG-2985`, `ENH-2589`, `ENH-2738`, `ENH-2936`, `ENH-2970`, `ENH-3244`, `FEAT-1544`, `FEAT-2618`, `FEAT-2619` | 1→0 | 0 | 1→**0** |
| `BUG-2820`, `ENH-2446`, `ENH-1667` | 2→1 | 0 | 1→1 |

**All 16 suppressed items were hand-checked; every one is a citation.** Representative:
`` - Fixture issue with decision prose under `## Open Questions`, run the placement rule `` /
`- \`severity: str\` — \`"error"\` / \`"warn"\` (see Open Question)` /
`- \`scripts/little_loops/fsm/schema.py:891\` … per open question resolution: writ…`.
No item that asks an unanswered question is suppressed.

### This issue fires the defect on itself

`ll-issues check-open-questions 3296` reports **3 open question(s)** on this file at creation.
All three are the vocabulary appearing in *this issue's own prose about the vocabulary* — the
fixture list under *Tests*, the survivor list beside it, and the `_OQ_CITATION_RE` type
description under *Program Design*. Under the proposed mask the count is **0**. Any issue
describing this defect is unable to avoid triggering it, which is the cleanest available
statement of the root cause; pin `BUG-3296` itself as a corpus fixture (`3 → 0`).

### Scope boundaries

- **Only the citation shapes above.** The adjacent *resolved-in-prose* class — "the open question
  above is now resolved", "The open question is RESOLVED", "open question is closed by …" — is
  **out of scope**. Those are declarations that were answered without the
  `_RESOLVED_QUESTION_MARKER_RE` vocabulary (`✅ RESOLVED` / `**RESOLVED**`). Widening the
  *resolved* marker is a different, riskier change (it suppresses on an assertion the item makes
  about itself); this issue suppresses on structural position only.
- **Not** a change to `_RESOLVED_QUESTION_MARKER_RE`, the section list, or the BUG-3170 cap.
- **Observed, not fixed:** a question declared as a *heading* (`### Open Question for
  Implementer`, `ENH-2589`; `### Open Questions for Implementer`, `ENH-2505`) is already invisible
  to `_count_unresolved_items_in_text`, which counts only bullet/numbered items — headings hit the
  `else: _flush()` branch. So `ENH-2589`'s real open question is uncounted today and stays
  uncounted; only its citation was inflating the count. That under-count is a separate pre-existing
  gap and is deliberately not addressed here.

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — `_count_unresolved_items_in_text`, plus two new
  module-level constants next to `_RESOLVED_QUESTION_MARKER_RE` (`:2597`) and
  `_OPEN_QUESTION_SIGNAL_RE` (`:2604`), following this file's `# BUG-NNNN:` narrowing-comment
  convention.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/check_open_questions.py` — `cmd_check_open_questions` ANDs this
  counter with `locate_unresolved_options`; no code change.
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` (`:63`),
  `scripts/little_loops/loops/refine-to-ready-issue.yaml` (`check_hedges`, `:404`),
  `scripts/little_loops/loops/autodev.yaml` — exit-code gates; no code change, but 11 issues stop
  forcing a refine pass.

### Tests

- Fixtures pinning each suppressed shape as **not counted**: `§ *Open question*`,
  `(see Open Question)`, `(per this issue's Open Question)`, `` `"open question"` `` in a code
  span, `` `## Open Questions` `` in a code span.
- Paired **still-counted** survivors in the same class, per this file's regression-test convention
  (`TestNumberedOpenQuestionCitations`, `test_issue_parser_unresolved.py:485-583`, is the model —
  extend it rather than open a new class): `- Open question: does X need Y?`,
  `- **Open question: DSL task file format** — the issue does not specify the schema`,
  `- Minor open question on hook warning treatment — …`.
- **Corpus differential (required):** assert the count is a **pure subtraction** — no issue's
  `count_open_questions_in_sections` rises — with the 14 changed issues pinned by ID. Build it on
  `_section_body`, not `_heading_bodies`. Same skip-if-corpus-absent scaffolding as
  `TestUnappliedDecisionLiveCorpusSweep` (`test_issue_parser.py:5063`).
- Re-run against the tree the fix lands on; the corpus grows daily.

## Program Design

### Types

No new or changed types. Two new module-level regex constants only:

- `_CODE_SPAN_RE: re.Pattern[str]` — inline code spans, masked out before signal matching.
- `_OQ_CITATION_RE: re.Pattern[str]` — citation lead-ins immediately preceding the
  `open question(s)` phrase, plus the quoted section title.

### Signatures

No signature changes. The edit is confined to one private helper's matching input:

- `_count_unresolved_items_in_text(text: str) -> int` (`scripts/little_loops/issue_parser.py`) —
  masks `joined` before `_OPEN_QUESTION_SIGNAL_RE.search(...)`; return contract unchanged.
- `count_open_questions_in_sections(content: str) -> int` — returns a lower count on affected
  issues; contract unchanged.
- `cmd_check_open_questions(config: BRConfig, args: argparse.Namespace) -> int`
  (`scripts/little_loops/cli/issues/check_open_questions.py`) — unchanged code, exit code flips
  1 → 0 on 11 issues.

### Call Path

`_OPEN_QUESTION_SIGNAL_RE` → `_count_unresolved_items_in_text` →
`count_open_questions_in_sections` → `cmd_check_open_questions`
(`cli/issues/check_open_questions.py`) → `ll-issues check-open-questions` → the exit-code gates in
`loops/oracles/resolve-decision.yaml` (`:63`), `loops/refine-to-ready-issue.yaml`
(`check_hedges`, `:404` → `check_hedge_attempts`, `:411`), and `loops/autodev.yaml`.

### Decision Rules

One rule: an open-question signal counts only when it is **not** inside an inline code span and
**not** immediately preceded by a citation lead-in. Masking happens on the joined item text, after
segmentation, so the mask cannot change how items are grouped. No new gate, threshold, or section.

## Implementation Steps

1. **Add the two constants and the mask.** Define `_CODE_SPAN_RE` and `_OQ_CITATION_RE` beside
   `_RESOLVED_QUESTION_MARKER_RE` (`issue_parser.py:2597`), with a `# BUG-3296:` comment naming
   the discriminator added (this file's narrowing-fix convention — cf. `# BUG-3169:` at `:2433`).
   Apply both to `joined` inside `_count_unresolved_items_in_text`'s `_flush()`, using
   equal-length filler, *after* the wrapped-continuation join and *before*
   `_OPEN_QUESTION_SIGNAL_RE.search(...)`. Leave the `_RESOLVED_QUESTION_MARKER_RE` check on the
   unmasked text.
2. **Pin the shapes.** Extend `TestNumberedOpenQuestionCitations`
   (`test_issue_parser_unresolved.py:485-583`) with the five suppressed shapes and the three
   still-counted survivors listed under *Integration Map → Tests*, paired in one class so the
   narrowing cannot be shown to over-suppress.
3. **Land the corpus differential.** Assert `count_open_questions_in_sections` is a pure
   subtraction across `.issues/` — no issue's count rises — with the 14 changed issues pinned by
   ID. Build it on `_section_body`, not `_heading_bodies`; skip if `.issues/` is absent.
4. **Verify externally.** `ll-issues check-open-questions 3285` exits 0 (it exits 1 today on two
   citations), `python -m pytest scripts/tests/` exits 0, and the 11 flipped gates are re-measured
   against the landing tree.

## Impact

- **Priority**: P3 — bounded, non-livelocking waste (one refine pass per run per affected issue),
  but it fires on 14 issues today and holds 11 gates red on issues that have nothing to decide.
- **Effort**: Small — two constants, a mask call, and a corpus differential that is already
  measured and only needs to be written down as a test.
- **Risk**: Low — measured as a pure subtraction (zero count rises corpus-wide), and every one of
  the 16 suppressed items was hand-verified as a citation. The residual risk is a future
  declaration shape that happens to open with `see`/`per`, which the paired survivor fixtures
  guard.
- **Breaking Change**: No. No signature or output shape changes. 11 issues flip
  `check-open-questions` from exit 1 to exit 0, which is the intended correction.

## Steps to Reproduce

1. `ll-issues check-open-questions 3285` → exit 1, `OPEN_QUESTIONS_REMAIN … 2 open question(s)`.
2. Read `### Open question` in that file — it carries a `> **Decided …**` callout.
3. Confirm the two counted items are cross-references, not questions.

## Relationship to EPIC-3290

- **BUG-3285 — co-owned exit code.** BUG-3285 moves `locate_unresolved_options`; this issue moves
  `count_open_questions_in_sections`. Both flip the *same* `check-open-questions` exit code into
  the same three gates. BUG-3285's consequence 3 asserts the gate flips when phantom option blocks
  are removed; measured, that holds on all four affected files only because their hedge counts
  happen to be 0. `FEAT-2339` is the live counterexample — option half already clean, hedge count
  2, exit stays 1 regardless of anything BUG-3285 does. Independent fixes, one shared gate; either
  order.
- **BUG-3278 — prior diagnosis, complementary fix.** `:346-349` already names this hazard
  (*"that command also counts free-form open questions … gating the flag on it would pin
  `decision_needed: true` on any issue with an open question and stall every loop that branches on
  the flag"*) and routes around it by adding `check-unresolved-decisions` (Part 4). It explicitly
  leaves the contaminated command alone: `locate_unresolved_options` keeps its contract
  *"**unchanged** for `check_open_questions.py:59` and `resolve-decision.yaml:125-133`"* (`:209-212`).
  So BUG-3278 builds beside the defect; this issue removes it. No overlap in files touched.
- **BUG-3287, BUG-3289** — no open-question surface; no interaction.

## Root Cause

`_OPEN_QUESTION_SIGNAL_RE` matches vocabulary, not syntactic role. BUG-3169 added the first
role discriminator (a numbered citation is not a declaration) but scoped it to the numeric shape,
leaving section-name and code-span citations indistinguishable from questions.

The ordering constraint is load-bearing and is why the mask belongs after the join: masking raw
lines before segmentation blanks out lines that `_count_unresolved_items_in_text` uses as item
boundaries, splitting one item into several and making counts *rise*. A differential built that
way reports 53 spurious rises across the corpus.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-22 | Priority: P3

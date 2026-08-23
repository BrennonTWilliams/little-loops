---
id: BUG-3296
type: BUG
title: check-open-questions counts citations of an open question as unresolved hedges
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-22'
captured_at: '2026-08-22T23:58:01Z'
completed_at: '2026-08-23T05:19:38Z'
parent: EPIC-3290
labels:
- issue-parser
- check-open-questions
- false-positive
- refine-to-ready-issue
- open-questions
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3296: check-open-questions counts citations of an open question as unresolved hedges

## Summary

`_OPEN_QUESTION_SIGNAL_RE` (`issue_parser.py:2699`) treats a *citation of* an open question as a
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

Measured across `.issues/` (3200 files, re-measured 2026-08-22): **14 issues** carry at least one
counted item that is purely a citation, and on **11 of them** those citations are the *only*
thing holding `ll-issues check-open-questions` at exit 1. A fifteenth — this issue itself — makes
12 flipped gates in total (see § *This issue fires the defect on itself*).

**Live-impact caveat, and why the corpus figure overstates it.** Of those 12 flipped gates,
**11 sit on `status: done` issues and one on `deferred`**. Filtering the corpus to the 72
non-terminal issues: only **5** carry a nonzero hedge count at all, and the fix changes exactly
**one** of them — `BUG-3296`. The other four (`ENH-3000`, `EPIC-1867`, `FEAT-3120`, `FEAT-3039`,
1 each) carry genuine hedges and are correctly left alone. So the corpus table below is
*regression evidence that the narrowing is a pure subtraction*, *not* a measure of waste being
paid today; no loop will re-gate a terminal issue. See § *Motivation* for what the fix is
actually worth.

Live on this epic's own BUG-3285, whose two counted items are both in `## Integration Map` and
both point at a question decided six lines below the pointer:

<!-- ll-evidence-ok: live CLI output from running the command against BUG-3285, not a quote from BUG-3285's issue body -->
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

1. `refine-to-ready-issue.yaml:404` (`check_hedges`) — exit-code gate; a red reading forces a
   refine pass.
2. `oracles/resolve-decision.yaml:62` (`check_decidable`) — exit-code gate, but reached as
   `ll-issues check-open-questions ID || ll-issues check-decidable ID`. A 1→0 flip
   **short-circuits the `||`**, so `check-decidable` stops being consulted on those issues and
   the state routes `on_yes: run_decide` instead of reaching `deposit_options`.
3. `oracles/resolve-decision.yaml:118-141` (`deposit_options`) — **not an exit code**. It inlines
   `count_unresolved_options(c) + count_open_questions_in_sections(c)` and appends the sum to
   `.open_questions_<ID>.history`, which feeds the `open_question_stall` evaluator
   (`loops/lib/common.yaml:211-231`, `max_stall: 2`). A lower count reaches the plateau sooner,
   so the state routes `on_no: run_decide` earlier.

`autodev.yaml` is **not** a direct consumer — it carries no `check-open-questions` reference; that
cluster was extracted into `oracles/resolve-decision.yaml`, which autodev reaches via
`loop: oracles/resolve-decision` (`autodev.yaml:641`, `:657`).

Consumers 2 and 3 have **nil impact today**: none of the 12 affected issues carries
`decision_needed: true`, so none can enter `resolve-decision`. They are recorded because the
narrowing changes their inputs and both routings move in the *opposite* direction from
consumer 1's benefit — toward `run_decide` sooner, not toward less work.

**This is not a loop defect and does not livelock.** `refine-to-ready-issue.yaml`'s
`check_hedge_attempts` (`:411`, BUG-3170) already bounds it — `output_numeric lt 2`, so one
hedge-forced refine per run, then fall through to `check_placeholders`. Its comment states the
premise outright: *"the scan is an absolute-zero probe over vocabulary with no answer/hedge
distinction, so a residual count is the steady state for a well-refined issue."* The loop is
correct; the probe is what is wrong.

The cost per occurrence is therefore bounded but real, and slightly self-defeating: the forced pass
is `/ll:refine-issue --auto`, which is **additive** — ENH-3031's own comment notes hedge vocabulary
"accumulates via `--gap-analysis` (additive, never removes content) and is never subsequently
closed." So a phantom hedge spends a refine cycle on an already-refined issue and can deposit more
of the vocabulary that caused it.

**What the fix is worth, stated honestly.** Per § *Current Behavior*'s live-impact caveat, that
cost is not currently being paid: the 11 red gates are all on terminal issues. The justification is
therefore *prospective and self-demonstrating*, not a backlog of waste to reclaim:

- The citation shapes are **unavoidable in the issues most likely to hit the gate.** Any issue that
  discusses questions, decisions, or this probe itself deposits them; § *This issue fires the defect
  on itself* is the proof, and it is the one live issue the fix changes today.
- The vocabulary is **deposited by the very loop the gate forces.** `--gap-analysis` writes
  citations (`see Open Question`, `per this issue's Open Question`) when it *answers* a question —
  the same mechanism BUG-3169 fixed for the numbered shape, where the tally rose with every refine
  pass. The terminal-issue population is the accumulated record of that, which is exactly why the
  live population is small: those issues went `done` before anything cleared the residue.
- The residue is **permanent by construction.** Nothing ever answers a cross-reference, so an
  affected issue's gate is red for as long as it stays open.

The corpus differential's real job is to prove the narrowing does not over-suppress — 0 rises
across 3200 files — not to size a recovery.

## Proposed Solution

Mask citations out of the item text *before* signal matching, inside
`_count_unresolved_items_in_text` — after the wrapped-continuation join, so item segmentation is
untouched (see § *Root Cause* for why the segmentation ordering is load-bearing):

```python
# Backtick-pair span, joining the `_PLACEHOLDER_BACKTICK_SPAN_RE` (:1791) family and its
# cross-referenced siblings in `symbol_claims` / `cli_claims` / `prose_deps` — kept as its
# own copy per that file's existing convention rather than a new shared import.
# Deliberate divergence: `*`, not the siblings' `+` — see below.
_OQ_BACKTICK_SPAN_RE = re.compile(r"`[^`\n]*`")
_OQ_CITATION_RE = re.compile(
    r"(?:§|\b(?:see|under|per|on the|referenced in|cited in))\s+"
    r"[*_\"'“]{0,2}(?:this\s+issue['’]s\s+)?open questions?\b"
    r"|[\"“]\s*Open Questions?\b",
    re.IGNORECASE,
)
```

applied to `joined` (equal-length filler, so offsets and any future span reporting stay valid)
before `_OPEN_QUESTION_SIGNAL_RE.search(...)`. The `_RESOLVED_QUESTION_MARKER_RE` check runs
against the **unmasked** text, unchanged.

Three details in those patterns are load-bearing:

- **The lead-in alternation must be `\b`-anchored.** Unanchored, `per` matches inside *Proper*,
  *wrapper*, *deeper*, *paper*; `see` inside *foresee*/*oversee*; `under` inside *thunder*. Measured
  against the unanchored draft, `- The wrapper open question: does X need Y?` and
  `- Proper open questions handling is missing` are both masked — genuine declarations that do not
  *open* with the phrase and so depend on the prose-hedge alternative the mask would kill. The `\b`
  goes inside the group (not before `§`, which is a non-word character). Verified: the anchored and
  unanchored forms produce **identical results corpus-wide**, so the tightening costs nothing and
  removes a whole false-negative class.
- **`this\s+issue['’]s`** — the corpus already carries `“` and `…`, so a typographic apostrophe is a
  live shape; a straight-quote-only pattern silently misses it.
- **`_OQ_BACKTICK_SPAN_RE` joins the file's existing backtick-span family**
  (`issue_parser.py:1787-1791` establishes the convention explicitly: an independent copy per site,
  carrying a comment that names its siblings). A differently-named `_CODE_SPAN_RE` with no such
  comment forks that convention silently. **But this copy must use `*`, not the siblings' `+`,** and
  the comment must say why: `+` cannot match an empty span, so it mis-pairs across a
  **double-backtick** span (`` `` `x` `` ``) — the exact construct issue prose uses to show
  backticked content. Measured on this very file: with `+`, the *Tests* fixture bullet leaves
  `` `## Open Questions` `` unmasked and BUG-3296 counts **1** instead of **0**. The `*` form is
  what the corpus differential below was measured with.

Note the code-span mask necessarily applies to *all* `_OPEN_QUESTION_SIGNAL_RE` alternatives, not
just the `open questions?` one — a quoted `` `"decision point"` `` in a vocabulary list is the same
false positive, and a trailing `` `is this open?` `` no longer satisfies `\?\s*$`. That is intended
and is the source of two of the measured deltas (`ENH-2446` 2→1, `BUG-2820` 2→1).

**Inline masking only; fences deliberately not masked.** The rest of this file composes inline
backtick masking *with* `fence_spans`/`in_fence` (`_template_placeholders`, `:1884-1885`). This
change does not, for two reasons. (1) Measured: **zero** currently-counted items sit inside a fenced
block in any of the seven `_OPEN_QUESTION_SECTIONS`, corpus-wide — there is nothing to suppress.
(2) `_count_unresolved_items_in_text` is line-oriented and carries no offsets, so fence masking
there could only be done by blanking lines — which destroys the item boundaries the counter uses and
makes counts *rise*, the same hazard § *Root Cause* documents for pre-segmentation masking.
Span-containment masking would require threading offsets through the counter, which is out of scope
for a narrowing fix.

### Corpus differential — re-measured 2026-08-22 (3200 files)

Harness note: `count_open_questions_in_sections` scans via `_section_body` (**H2-only, first
occurrence**), *not* `_heading_bodies`. A differential built on the latter over-scans by ~4x and
reports spurious count *rises*; any re-measurement must use `_section_body`.

**14 issues change (15 with this one). Zero counts rise** — a suppression must be a pure
subtraction, and this one is. **11 gate exit codes flip 1→0 (12 with this one)**. Per § *Current
Behavior*, 11 of those 12 are `done` and one is `deferred`; this table is the over-suppression
regression evidence, not a measure of live waste:

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

`ll-issues check-open-questions 3296` reports **5 open question(s)** on this file. Every one is the
vocabulary appearing in *this issue's own prose about the vocabulary* — the fixture and survivor
lists under *Tests*, the `_OQ_CITATION_RE` type description under *Program Design*, the consumer
enumeration under *Integration Map*. Under the proposed mask the count is **0**. Any issue
describing this defect is unable to avoid triggering it, which is the cleanest available statement
of the root cause — and, per § *Current Behavior*, it is the **only non-terminal issue the fix
changes today**.

The count is a property of *this file's current wording*, so do not freeze it in a test: it was 3
at creation and reached 5 through review edits alone, and the `+`-vs-`*` measurement above shows how
sensitive it is to the mask's exact shape. Reproduce it by hand — `ll-issues check-open-questions
3296` before and after — and freeze the *shapes* as synthetic fixtures instead (see § *Tests*).

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

- `scripts/little_loops/issue_parser.py` — `_count_unresolved_items_in_text` (`:2747`), plus two new
  module-level constants next to `_RESOLVED_QUESTION_MARKER_RE` (`:2662`) and
  `_OPEN_QUESTION_SIGNAL_RE` (`:2699`), following this file's `# BUG-NNNN:` narrowing-comment
  convention.

> **Line refs are anchored to `HEAD` as of 2026-08-22.** BUG-3278's work has since landed on `main`
> (verified 2026-08-23: `status: done`, tree clean) and shifted every constant in this file by
> exactly +317 lines, confirming the predicted drift. Re-anchor all `:NNNN` refs against whatever
> tree the fix actually lands on; resolve by symbol name, not by line.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/check_open_questions.py` — `cmd_check_open_questions` ANDs this
  counter with `locate_unresolved_options`; no code change.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (`check_hedges`, `:404` →
  `check_hedge_attempts`, `:411`) — exit-code gate; no code change. This is the consumer the fix is
  *for*.
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — **two** distinct consumers, no code
  change to either:
  - `check_decidable` (`:62`) — exit-code gate, invoked as
    `ll-issues check-open-questions ID || ll-issues check-decidable ID`. A 1→0 flip short-circuits
    the `||`, so `check-decidable` is no longer consulted and the state routes `on_yes: run_decide`
    rather than `on_no: deposit_options`.
  - `deposit_options` (`:118-141`) — **numeric**, not an exit code: inlines
    `count_unresolved_options(c) + count_open_questions_in_sections(c)` into
    `.open_questions_<ID>.history`, consumed by the `open_question_stall` evaluator
    (`loops/lib/common.yaml:211-231`, `max_stall: 2`). A lower count plateaus sooner and routes to
    `run_decide` earlier.
  - Both are inert today: no affected issue carries `decision_needed: true`, so none can enter this
    loop. Listed because both move *opposite* to the `check_hedges` benefit.
- `scripts/little_loops/loops/autodev.yaml` — **indirect only.** It contains no
  `check-open-questions` reference; the cluster was extracted into `oracles/resolve-decision.yaml`,
  which autodev invokes via `loop: oracles/resolve-decision` (`:641`, `:657`).

### Tests

- Fixtures pinning each suppressed shape as **not counted**: `§ *Open question*`,
  `(see Open Question)`, `(per this issue's Open Question)`, `` `"open question"` `` in a code
  span, `` `## Open Questions` `` in a code span.
- Paired **still-counted** survivors in the same class, per this file's regression-test convention
  (`TestNumberedOpenQuestionCitations`, `test_issue_parser_unresolved.py:586`, is the model —
  extend it rather than open a new class): `- Open question: does X need Y?`,
  `- **Open question: DSL task file format** — the issue does not specify the schema`,
  `- Minor open question on hook warning treatment — …`.
- **Word-boundary survivors (required).** None of the three survivors above starts with a word
  *ending* in a lead-in, so they cannot catch the unanchored-alternation defect. Add at least:
  `- The wrapper open question: does X need Y?`, `- Proper open questions handling is missing`,
  `- A deeper open question remains`. All three are masked by an unanchored `per`/`see`/`under` and
  must stay **counted**.
- **Double-backtick survivor (required).** A `` `` `## Open Questions` `` ``-style span must mask
  *fully*; a `+`-quantified span regex mis-pairs and leaves the tail exposed. Pin one item whose
  suppressed shape is written with double backticks.
- **Corpus sweep (required), without pinned IDs.** Assert the narrowing is a pure subtraction:
  for every file in `.issues/`, the masked count must be `<=` the unmasked count, computed in the
  test by running the same segmentation against `_OPEN_QUESTION_SIGNAL_RE` with and without the
  mask. Build it on `_section_body`, not `_heading_bodies`; skip if `.issues/` is absent
  (`TestUnappliedDecisionLiveCorpusSweep`, `test_issue_parser.py:5604`, is the scaffolding model).
  Two constraints this replaces the original "pin the 14 changed issues by ID" plan for:
  - Once the fix lands there is **no before-state to compare against** — the old behavior is gone.
    The sweep must recompute the unmasked count inline from the module constants, or it cannot
    assert "subtraction" at all.
  - The cited precedent explicitly refuses to pin corpus results — *"not asserted here since the
    corpus changes daily"* — and freezes shapes as synthetic fixtures instead. Several of the 14
    are actively edited (`BUG-3285` is in this same epic and its own fix rewrites that file), so
    pinned counts would rot within days.
- Re-run against the tree the fix lands on; the corpus grows daily.

## Program Design

### Types

No new or changed types. Two new module-level regex constants only:

- `_OQ_BACKTICK_SPAN_RE: re.Pattern[str]` — inline backtick spans, masked out before signal
  matching. Joins the `_PLACEHOLDER_BACKTICK_SPAN_RE` (`:1791`) family with the sibling
  cross-reference comment that convention requires, but quantified `*` rather than `+` so
  double-backtick spans pair correctly.
- `_OQ_CITATION_RE: re.Pattern[str]` — `\b`-anchored citation lead-ins immediately preceding the
  `open question(s)` phrase, plus the quoted section title.

### Signatures

No signature changes. The edit is confined to one private helper's matching input:

- `_count_unresolved_items_in_text(text: str) -> int` (`scripts/little_loops/issue_parser.py`) —
  masks `joined` before `_OPEN_QUESTION_SIGNAL_RE.search(...)`; return contract unchanged.
- `count_open_questions_in_sections(content: str) -> int` — returns a lower count on affected
  issues; contract unchanged.
- `cmd_check_open_questions(config: BRConfig, args: argparse.Namespace) -> int`
  (`scripts/little_loops/cli/issues/check_open_questions.py`) — unchanged code, exit code flips
  1 → 0 on 12 issues (11 `done`, 1 `deferred`) plus this one.

### Call Path

`_OPEN_QUESTION_SIGNAL_RE` → `_count_unresolved_items_in_text` →
`count_open_questions_in_sections`, which forks into two consumer shapes:

1. **Exit code.** → `cmd_check_open_questions` (`cli/issues/check_open_questions.py`) →
   `ll-issues check-open-questions` → `loops/refine-to-ready-issue.yaml` (`check_hedges`, `:404` →
   `check_hedge_attempts`, `:411`) and `loops/oracles/resolve-decision.yaml` (`check_decidable`,
   `:62`, behind a `||` with `ll-issues check-decidable`).
2. **Numeric.** → imported directly by `loops/oracles/resolve-decision.yaml`'s `deposit_options`
   (`:118-141`), summed with `count_unresolved_options` into `.open_questions_<ID>.history` →
   `open_question_stall` evaluator (`loops/lib/common.yaml:211-231`).

`loops/autodev.yaml` reaches both only through `loop: oracles/resolve-decision` (`:641`, `:657`);
it holds no direct reference.

### Decision Rules

One rule: an open-question signal counts only when it is **not** inside an inline backtick span and
**not** immediately preceded by a `\b`-anchored citation lead-in. Masking happens on the joined item
text, after segmentation, so the mask cannot change how items are grouped. Fenced blocks are *not*
masked (measured: zero counted items live inside one). No new gate, threshold, or section.

## Implementation Steps

0. **Re-anchor the line refs.** Every `:NNNN` in this issue is anchored to `HEAD` at 2026-08-22;
   BUG-3278's work has since landed on `main` and shifted those constants by +317 lines. Resolve
   each constant by symbol name against the landing tree before editing.
1. **Add the two constants and the mask.** Define `_OQ_BACKTICK_SPAN_RE` (quantified `*`, with the
   sibling cross-reference comment and the `*`-not-`+` rationale) and `_OQ_CITATION_RE`
   (`\b`-anchored lead-ins, `['’]` apostrophe class) beside `_RESOLVED_QUESTION_MARKER_RE`
   (`issue_parser.py:2662`), with a `# BUG-3296:` comment naming the discriminator added (this
   file's narrowing-fix convention — cf. `# BUG-3169:` at `:2675`). Apply both to `joined` inside
   `_count_unresolved_items_in_text`'s `_flush()` (`:2747`), using equal-length filler, *after* the
   wrapped-continuation join and *before* `_OPEN_QUESTION_SIGNAL_RE.search(...)`. Leave the
   `_RESOLVED_QUESTION_MARKER_RE` check on the unmasked text.
2. **Pin the shapes.** Extend `TestNumberedOpenQuestionCitations`
   (`test_issue_parser_unresolved.py:586`) with the five suppressed shapes, the three still-counted
   survivors, the three **word-boundary** survivors, and the **double-backtick** case listed under
   *Integration Map → Tests* — paired in one class so the narrowing cannot be shown to
   over-suppress. Confirm by construction that the word-boundary trio fails against an unanchored
   `per`/`see`/`under` alternation and the double-backtick case fails against a `+`-quantified span.
3. **Land the corpus sweep.** Assert `masked <= unmasked` for every file in `.issues/`, recomputing
   the unmasked count inline from the module constants (there is no before-state once the fix
   lands). **No pinned issue IDs** — the cited precedent refuses them because the corpus changes
   daily. Build it on `_section_body`, not `_heading_bodies`; skip if `.issues/` is absent.
4. **Verify externally.** `python -m pytest scripts/tests/` exits 0; `ll-issues
   check-open-questions 3296` goes from a nonzero count to **0** (the one live issue the fix
   changes); `ll-issues check-open-questions 3285` exits 0 as the frozen `done`-issue spot check.
   Re-measure the full differential against the landing tree and update § *Corpus differential* —
   including the non-terminal split, which is the number that justifies the change.

## Impact

- **Priority**: P3 — and P3 is right for the reason § *Motivation* now states plainly: the defect
  is real, permanent, and self-inflicted by the loop that trips over it, but the backlog it has
  already produced sits on terminal issues. **One non-terminal issue changes today** (this one). The
  value is prospective — every future issue that discusses questions or decisions deposits these
  shapes, and nothing ever clears them.
- **Effort**: Small — two constants, a mask call, and a corpus sweep that is already measured and
  only needs to be written down as a test.
- **Risk**: Low — measured as a pure subtraction (zero count rises across 3200 files), and every
  one of the 16 suppressed items was hand-verified as a citation. Two over-suppression traps found
  in review are closed by construction and pinned by fixtures: an unanchored lead-in alternation
  masking *Proper* / *wrapper* / *deeper*, and a `+`-quantified span regex mis-pairing across
  double backticks. The residual risk is a future declaration shape opening with `see`/`per`, which
  the paired survivor fixtures guard.
- **Breaking Change**: No. No signature or output shape changes. 12 issues flip
  `check-open-questions` from exit 1 to exit 0, which is the intended correction. Two
  `resolve-decision.yaml` consumers (`check_decidable`'s `||` short-circuit and `deposit_options`'
  stall history) shift toward `run_decide` sooner; both are inert today because no affected issue
  carries `decision_needed: true`.

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


## Session Log
- `/ll:manage-issue` - 2026-08-23T05:19:31 - `17a55b50-a36b-49c5-816c-0c3adbd93077.jsonl`
- `/ll:ready-issue` - 2026-08-23T05:00:56 - `cc09229a-0981-4b55-8574-725807144227.jsonl`
- `/ll:confidence-check` - 2026-08-23T04:14:03 - `b2caa0cf-f05f-4cb4-8da9-96b9101c7e5c.jsonl`
- `/ll:confidence-check` - 2026-08-23T03:35:28 - `f76f3255-c5a1-47a5-a256-fbcdf24c224e.jsonl`

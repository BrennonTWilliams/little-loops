---
id: BUG-3169
type: BUG
title: check-open-questions counts cross-references to numbered Open Questions as
  unresolved hedges
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-14'
captured_at: '2026-08-14T23:27:36Z'
---

# BUG-3169: check-open-questions counts cross-references to numbered Open Questions as unresolved hedges

## Summary

`_OPEN_QUESTION_SIGNAL_RE` (`scripts/little_loops/issue_parser.py:1444`) matches the bare phrase `\bopen question\b` case-insensitively. That fires on *cross-references to* a numbered question ("On Open Question 1: option (c) is confirmed not free…", "relevant to Open Question 1's option (a)") exactly as readily as on an actual unanswered question. Since those cross-references are precisely the prose `/ll:refine-issue --auto --gap-analysis` deposits when it *answers* a question, `ll-issues check-open-questions` gets redder the more thoroughly refine does its job.

This makes `refine-to-ready-issue`'s `check_hedges` gate unclearable, and because that gate sits upstream of `confidence_check` in the chain (`check_verify_verdict → check_hedges → check_ac_automatable → confidence_check`), the loop burns its entire refine budget and falls through to `breakdown_issue` without ever scoring the issue.


## Reproduction

Observed on FEAT-3168 during `ll-loop run refine-to-ready-issue FEAT-3168`
(run `.loops/runs/refine-to-ready-issue-20260814T180315/`):

```
$ ll-issues check-open-questions FEAT-3168
OPEN_QUESTIONS_REMAIN: FEAT-3168 — 3 open question(s) and 0 unresolved option(s)
$ echo $?
1
```

All three counted items are *answers to*, or *citations of*, Question 1 — none
is an open question:

| Section | Item (truncated) | Matched signal |
|---|---|---|
| `## Open Questions` | "On **Open Question** 1: option (c) is confirmed not free. A grep/import sweep found no `ContextVar` usage…" | `\bopen question\b` |
| `## Open Questions` | "On **Open Question** 1, option (a): the two existing pins on `build_server()`'s signature…" | `\bopen question\b` |
| `## Program Design` | "…(relevant to **Open Question** 1's option (a)): `resource_index = build_resource_index(config)`…" | `\bopen question\b` |

None carries a `✅ RESOLVED` / `**RESOLVED**` marker, because they are prose
research findings rather than question bullets — so
`_RESOLVED_QUESTION_MARKER_RE` does not exclude them.

The `## Program Design` hit exists only because ENH-3031 widened
`_OPEN_QUESTION_SECTIONS` to include the sections refine/wire deposit findings
into. That widening is correct in intent; it just multiplied the blast radius
of this false positive.

## Current Behavior

`_OPEN_QUESTION_SIGNAL_RE` treats any occurrence of the literal phrase
`open question` (case-insensitive, `\b`-bounded) as an open-question signal,
with no distinction between a hedge and a back-reference to a numbered question.

The failure is self-reinforcing: each `/ll:refine-issue --auto --gap-analysis`
pass researches the question and writes *more* prose referencing "Open Question
1", so the count rises rather than falls. In the FEAT-3168 run this produced:

```
11 check_verify_verdict   yes (VALID) → check_hedges
12 check_hedges           NO  → check_refine_limit      ← 1st false positive
13 check_refine_limit     1 < 2 → refine_followup
14 refine_followup        (--gap-analysis)
...
19 check_hedges           NO  → check_refine_limit      ← 2nd false positive
20 check_refine_limit     2 not< 2 → breakdown_issue
```

Two refine passes and two verify passes burned (~$2.36, 19m46s), the refine
budget exhausted, `confidence_check` never reached, and the loop began
decomposing a correctly-sized issue.

## Expected Behavior

A numbered back-reference ("Open Question 1", "Open Questions 2 and 3", "Open
Question 1's option (a)") is a citation, not a hedge, and must not count toward
`count_open_questions_in_sections`.

A genuine open question must still count. The existing safety nets cover the
realistic authoring shapes for a numbered question:

- `- **Open Question 1:** Should the policy be enforced at build time?` — caught
  by the `\?\s*$` alternative.
- `- Open Question 2: needs decision on transport.` — caught by
  `\bneeds decision\b`.
- `- Backoff strategy. Open question.` — unnumbered, still caught by the
  `open question` alternative.

## Proposed Solution

Split the `open question` alternative in `_OPEN_QUESTION_SIGNAL_RE` into a
**declaration** alternative and a **citation-suppressing prose** alternative.
The discriminator is position plus a declaration boundary, not the presence of
a digit:

```python
# item-leading declaration, numbered or not
r"|^\s*(?:[-*]|\d+[.)])\s*[*_]{0,2}open question\b(?:\s*#?\s*\d+)?\s*(?:[:.*_—]|$)"
# prose hedge anywhere, but never a numbered citation
r"|\bopen questions?\b(?!\s*[#:]?\s*\d)"
```

The other 14 alternatives are hedge vocabulary with no citation form and are
left alone.

> **Selected:** the two-alternative declaration/citation split above.
>
> ### Decision Rationale
>
> The digit lookahead alone is not sufficient. `_count_unresolved_items_in_text`
> joins wrapped continuation lines before matching (ENH-3031), so the `\?\s*$`
> alternative — the safety net the lookahead-only fix leans on for numbered
> questions — anchors to the end of the *joined* item and stops firing as soon
> as a question carries any context line under it. Lookahead-only therefore
> silently drops two ordinary authoring shapes to 0:
> `- **Open Question 2:** Should X? / Context: …` (wrapped) and
> `- **Open Question 3:** Decide the default transport.` (imperative, no `?`,
> no hedge vocabulary). Both are exactly what this gate exists to catch.
>
> Item-leading position is likewise not sufficient on its own — `- Open
> Questions 2 and 3 were folded into the plan.` opens the item and is still a
> citation. Requiring a declaration boundary (`:` / `.` / `—` / `**` / end) and
> singular `question` in the leading alternative separates the two: a
> declaration introduces a question, a citation continues into a verb phrase or
> a possessive.
>
> Rejected alternative — dropping the `open question` alternative entirely in
> favour of the `\?$` / `**Q1.**` / `Q:` shape patterns: it would also stop
> catching genuine unnumbered prose hedges ("this remains an open question"),
> which is the case ENH-2446 added the phrase for; that case is why the second
> alternative is retained unanchored.

## Impact

- **Priority**: P2 — silently defeats the `check_hedges` gate and wastes a full
  refine budget per affected issue, but has a known manual workaround (reword
  the citation, or mark the item `✅ RESOLVED`).
- **Effort**: Small — one regex alternative plus regression tests.
- **Risk**: Low — narrowing a single alternative; the `\?$` and hedge-vocabulary
  alternatives remain as safety nets for genuine numbered questions.
- **Breaking Change**: No.

## Acceptance Criteria

- [x] `count_open_questions_in_sections` returns 0 for an item whose only
      open-question signal is a numbered back-reference ("On Open Question 1:
      option (c) is confirmed not free.").
- [x] `count_open_questions_in_sections` still returns 1 for an unnumbered prose
      hedge ("Backoff strategy. Open question.").
- [x] `count_open_questions_in_sections` still counts a numbered question that
      ends in `?` or carries hedge vocabulary.
- [x] `count_open_questions_in_sections` still counts an item-leading numbered
      declaration that carries a wrapped continuation line, or that is phrased
      as an imperative with no `?` and no hedge vocabulary — the two shapes a
      lookahead-only narrowing regresses to 0.
- [x] An item-leading *citation* ("Open Questions 2 and 3 were folded into the
      plan.", "Open Question 2 was answered by the sweep.") still returns 0 —
      leading position alone does not qualify as a declaration.
- [x] `python -m pytest scripts/tests/` exits 0 (existing
      `TestCountOpenQuestionsInSections` /
      `TestCountOpenQuestionsWidenedSections` cases still pass).

## Out of Scope

**The unnumbered section pointer.** A shape of the form:

> `## Integration Map` — "…`test_build_server_signature_unchanged` pins the
> zero-parameter signature — **see Open Questions**."

still counts. Deliberately not covered here, because the shape is genuinely
ambiguous rather than plainly wrong: "see Open Questions" can mean "context
lives over there" (benign) *or* "this item is blocked on an unresolved
question" (a real hedge). Suppressing it would require either a pointer-verb
lookbehind (`see` / `per` / `cf.` / `refer to`), which guesses at authorial
intent, or cross-section logic — `count_open_questions_in_sections` is
currently a per-section, additive scan with no such awareness.

FEAT-3168 carried one instance of this shape; it was reworded in the working
tree independently of this fix, so that issue now reports 0 against both the
old and new regex. Worth a separate issue if the pointer shape recurs.

**The gate ratchet.** `open question` was 1 of 15 alternatives, and the
remaining hedge vocabulary (`worth confirming`, `worth checking`, `TBD`,
`needs confirmation`, …) fires just as readily on the *answering* prose refine
deposits into `## Program Design` / `## Codebase Research Findings`. This fix
removes one instance of the self-reinforcing count; the class of failure
survives, and is tracked separately in [BUG-3170](BUG-3170) — make
`check_hedges` compare against a pre-refine baseline rather than requiring an
absolute zero.

## Integration Map

- `scripts/little_loops/issue_parser.py:1444` — `_OPEN_QUESTION_SIGNAL_RE`
  (the fix site).
- `scripts/little_loops/cli/issues/check_open_questions.py:60` — sole consumer
  via `count_open_questions_in_sections`.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:298` — `check_hedges`
  gate, the state that stalls.
- `scripts/tests/test_issue_parser_unresolved.py:259` —
  `TestCountOpenQuestionsInSections` (add regression cases here).
- `scripts/tests/test_ll_issues_check_open_questions.py` — subprocess-level
  exit-code contract.
- `scripts/tests/test_fsm_open_question_stall.py` — existing stall coverage.

## Status

**Open** | Created: 2026-08-14 | Priority: P2

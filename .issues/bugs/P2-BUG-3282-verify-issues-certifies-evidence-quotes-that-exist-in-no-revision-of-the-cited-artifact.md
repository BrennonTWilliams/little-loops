---
id: BUG-3282
type: BUG
title: verify-issues certifies evidence quotes that exist in no revision of the cited
  artifact
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T17:29:50Z'
labels:
- verify-issues
- skills
- evidence
- hallucination
- pipeline
relates_to:
- ENH-3283
- ENH-3284
- BUG-3278
---

# BUG-3282: verify-issues certifies evidence quotes that exist in no revision of the cited artifact

## Summary

`/ll:verify-issues` validates an issue's *code* claims but never checks that quoted **evidence** —
a snippet attributed to another file, usually another `.issues/` file — actually appears in the
artifact it is attributed to. An issue whose code references are all accurate but whose motivating
evidence is fabricated passes verification and receives `verify_verdict: VALID`.

## Current Behavior

`commands/verify-issues.md:71` ("Identify code snippets quoted") and `:129` ("**Validate code
snippets**: Does quoted code match current code?") scope quote-checking to source code. Nothing
in the pass:

- extracts quoted spans attributed to a named `.issues/` file or issue ID
- greps the cited artifact — at HEAD, across history, or in the working tree — for those spans
- checks that a `## Steps to Reproduce` naming a live artifact still reproduces against it

Observed on BUG-3278 (2026-08-21). Its `## Current Behavior` quoted two strings attributed to
ENH-3277:

```
- **(a) Make the documented override real.**
**DECISION — pick one before step 4 touches this file:**
```

Neither string exists in **any** committed revision of ENH-3277 (verified by grepping every
revision returned by `git log --all --format=%h -- .issues/enhancements/P2-ENH-3277*.md`).
ENH-3277's second decision point is prose, not bullets. Two `verify_issue` invocations during a
`refine-to-ready-issue` loop run stamped `verify_verdict: VALID` / `confidence_score: 98` anyway,
because every *code* assertion in the issue (`issue_parser.py:2134`, `:1967`, `:1891`, the
`section_header > bold_label > numbered > bullet` precedence order, the winner-take-all return)
was accurate.

## Expected Behavior

Verification extracts quoted spans that are attributed to a named artifact (file path or issue
ID) and confirms each one exists in that artifact. A span found nowhere in the cited artifact —
at HEAD, in the working tree, or in any revision — fails the pass and is named in the verdict,
regardless of how accurate the issue's code claims are.

## Motivation

An unverified evidence quote is worse than a missing one: it reads as the strongest part of the
issue. Downstream passes treat it as settled ground and build on it. On BUG-3278, `refine_issue`
and `wire_issue` produced roughly 150 lines of Integration Map, dependent-file inventory, docs
list, and test wiring — including a fixture spec and a proposed `--all-tiers` CLI flag — all
derived from a mechanism ("a `bullet`-tier block lost precedence to `bold_label`") that the
fabricated quote invented. The whole 26-minute loop run hardened a fiction.

The failure is silent by construction. Verification currently reports strongest confidence
exactly where its coverage is weakest: an issue with dense, accurate code citations and one
fabricated evidence quote scores higher than a vague but honest one.

## Proposed Solution

Add an evidence-existence check to the verification pass. It is deterministic and cheap enough to
run as a Python gate rather than an LLM judgement:

1. **Extract candidate spans.** Fenced blocks and inline-backtick runs that appear within N lines
   of a file path or issue ID reference, or inside a section that names one.
2. **Resolve the cited artifact.** Issue ID -> path via the existing resolver; file paths as
   given.
3. **`grep -F` each span** against the artifact at working tree, at HEAD, and across
   `git log --all` revisions of that path. Normalize whitespace before matching; skip spans below
   a minimum length (a 3-token quote is not evidence).
4. **Fail on zero hits**, naming the span and the artifact.

Open sub-question for implementation: whether this lands as a new `ll-verify-*` CLI invoked from
the skill (deterministic, testable by subprocess, reusable by `capture-issue`) or as prose added
to `commands/verify-issues.md`. The CLI shape is preferred — it is the only form the capture-side
guard can also call.

## Integration Map

### Files to Modify

- `commands/verify-issues.md` — extend the validation phase beyond `:129`'s code-snippet scope to
  cover artifact-attributed evidence quotes
- A new deterministic checker under `scripts/little_loops/` (module + `ll-*` entry point in
  `scripts/pyproject.toml`) if the CLI shape is taken

### Tests

- Fixture issue quoting a string present in the cited artifact -> passes
- Fixture issue quoting a string absent from the cited artifact -> fails, names span + artifact
- Fixture quoting a string absent at HEAD but present in an earlier revision -> passes (history is
  in scope; a repro can legitimately cite a since-edited file)
- Whitespace/line-wrap normalization: a quote reflowed across lines still matches

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P2 — silent, and it corrupts every downstream pass in a refine loop rather than
  failing one step
- **Effort**: Small-Medium — span extraction is the only non-trivial part
- **Risk**: Low-Medium — over-eager span extraction produces false failures on illustrative
  snippets that were never claimed to be verbatim quotes. Mitigate with a minimum span length and
  by requiring an explicit artifact attribution nearby.
- **Breaking Change**: No

## Steps to Reproduce

1. Author an issue whose code references are all correct but which quotes, in a fenced block or
   inline backticks, a line attributed to another issue file that does not contain it.
2. Run `/ll:verify-issues` on it.
3. Observe `verify_verdict: VALID` — the fabricated quote is never tested.

Historical instance: `git show baa553d9:.issues/bugs/P2-BUG-3278-*.md` is the capture that
contains the fabricated quotes; the loop's two verify passes are recorded in that file's
`## Session Log`.

## Root Cause

`commands/verify-issues.md` frames verification as "does the issue's description of the code match
the code" (`:129`). Evidence attributed to a non-source artifact — another issue file, a log, a
run directory — falls outside that frame entirely, so the pass has no step that could fail on it.

## Related Key Documentation

- `commands/verify-issues.md:71,129` — the code-scoped quote check this issue widens
- BUG-3278 — the issue whose fabricated evidence passed two verification rounds
- ENH-3277 — the artifact the fabricated quotes were attributed to

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-21T17:30:50 - `fa57a84b-34e0-4018-9e9e-dd57ed7ef3f3.jsonl`

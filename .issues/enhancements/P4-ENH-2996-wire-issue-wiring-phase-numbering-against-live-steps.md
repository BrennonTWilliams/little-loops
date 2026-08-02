---
id: ENH-2996
status: open
priority: P4
captured_at: '2026-08-02T13:43:01Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to:
- ENH-2995
decision_needed: false
testable: true
confidence_score: 99
outcome_confidence: 87
score_complexity: 23
score_test_coverage: 14
score_ambiguity: 25
score_change_surface: 25
---

# wire-issue's Wiring Phase numbers against live steps only

## Summary

`/ll:wire-issue` Phase 8b appends a `### Wiring Phase` whose entries continue
the numbering of the existing `## Implementation Steps` list. When some of
those earlier steps have been refuted by a prior `/ll:refine-issue` pass, the
continued numbering asserts a sequence that includes dead steps.

## Current Behavior

`skills/wire-issue/SKILL.md:383-396` (Phase 8b) instructs:

```markdown
### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

N. Update `path/to/caller.py` — adjust calls to `changed_function()` with new signature
N+1. Update `tests/test_affected.py` — adapt existing tests to new behavior
```

`N` continues from the existing list's last number, with no check on whether
those steps are still live.

Observed in `ENH-2500`
(`.issues/enhancements/P3-ENH-2500-per-run-dir-pending-file-and-scope-for-prompt-across-issues.md:287-298`):
the Wiring Phase is numbered 10-17, continuing a 1-9 list in which steps 1, 3,
6 and 7 are each explicitly refuted by an intervening
`### Codebase Research Findings` block ("Revised step 1: **omit entirely**",
"Step 6 target file is wrong"). The numbering presents a 17-step plan of which
four steps are dead.

## Expected Behavior

The Wiring Phase either:
- numbers against live steps only (skipping refuted ones), or
- uses an independent, unnumbered or letter-keyed list that makes no claim
  about position in the parent sequence.

The second is simpler and does not require wire-issue to re-derive which steps
are live.

## Motivation

Low severity on its own — the numbering is cosmetic and the wiring entries
themselves are sound (a corpus check found only 2% of 9,377 wiring bullets are
explicitly no-op, so wire-issue is not padding). The value is in not
compounding ENH-2995's contradiction problem with a numbering scheme that
implies the dead steps are part of the sequence.

## Proposed Solution

Two options, only one of which needs ENH-2995's superseded markers:

**Option A**: Wiring Phase entries become an unnumbered bulleted list, or
letter-keyed (`W1`, `W2`, …), making no positional claim. Zero dependency on
detecting live steps; shippable independently of ENH-2995.

> **Selected:** Option A — matches the unnumbered `-` bullet convention already
> used by 3 of 4 sibling Phase-8a subsections in `skills/wire-issue/SKILL.md`,
> has zero downstream code/test/doc coupling to the current `N.` numbering,
> and ships independently of the blocked ENH-2995 dependency.

**Option B**: wire-issue skips superseded-marked steps when computing `N`.
Needed ENH-2995's marker to exist and be parseable — now true (`ENH-2995` is
`status: done` as of this pass), though Option A remains selected regardless.

Option A is recommended — it removes the false claim rather than computing a
truer one, and the Wiring Phase is a distinct set of touchpoints that does not
genuinely need to interleave with the parent sequence.

### Decision Rationale

**Selected: Option A** (unnumbered/letter-keyed Wiring Phase entries).

Two `ll:codebase-pattern-finder` agents independently evaluated each option
against the codebase. Option A matches an existing, dominant convention with
zero downstream coupling; Option B is currently blocked and would introduce
new parsing logic that has no precedent.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 3 | 0 |
| Simplicity | 3 | 0 |
| Testability | 3 | 1 |
| Risk | 3 | 0 |
| **Total** | **12/12** | **1/12** |

Key evidence:
- 3 of 4 sibling Phase-8a subsections in `skills/wire-issue/SKILL.md`
  (`### Dependent Files`, `### Documentation`, `### Tests`, `### Configuration`)
  already use unnumbered `-` bullets with an italic attribution line — Phase
  8b's numbered `N.`/`N+1.` format is the sole outlier.
- No code, test, or doc anywhere in the repo parses or depends on the
  Wiring Phase's `N.`-style numbering (`output-report.md`'s `[N]` is a
  step-count placeholder, not a parsed sequence number).
- Option B hard-depended on `ENH-2995` for a superseded-step marker; that
  issue has since landed (`status: done` as of this pass — was open at
  decision time). This does not change the selection: Option B would still
  additionally require new step-filtering logic in wire-issue's Phase 3 that
  has no precedent today, and Option A remains the higher-scoring choice on
  its own merits.

## Program Design

### Signatures
- `emit_skill(self, skill_meta: dict) -> str` — `GeminiEmitter.emit_skill()`
  (`scripts/little_loops/adapters/gemini.py:80`). This is the only Python
  code this issue's change transitively touches: it copies
  `skills/wire-issue/SKILL.md`'s body verbatim into
  `.gemini/skills/wire-issue/SKILL.md`, so it must be re-run
  (`ll-adapt --host gemini --apply`) after Phase 8b's template text changes,
  or the Gemini mirror keeps the old `N.`/`N+1.` numbering. The Kimi adapter
  has the equivalent role via its own emitter, invoked as
  `ll-adapt --host kimi --apply`.
- No other Python function signature is touched — Phase 8b itself is
  instructional markdown prose in `skills/wire-issue/SKILL.md` that a Claude
  agent reads and follows verbatim when executing `/ll:wire-issue`; there is
  no deterministic parser for that template's numbering anywhere in
  `scripts/little_loops/`.

### Before / After (template text diff)

Before (`skills/wire-issue/SKILL.md:392-395`):
```
N. Update `path/to/caller.py` — adjust calls to `changed_function()` with new signature
N+1. Update `tests/test_affected.py` — adapt existing tests to new behavior
N+2. Register in `plugin.json` — add entry for new skill/command
N+3. Update `docs/relevant.md` — reflect changed behavior in documentation
```

After (Option A — matches the `### Dependent Files (Callers/Importers)`
convention at `skills/wire-issue/SKILL.md:338-343`):
```
- Update `path/to/caller.py` — adjust calls to `changed_function()` with new signature
- Update `tests/test_affected.py` — adapt existing tests to new behavior
- Register in `plugin.json` — add entry for new skill/command
- Update `docs/relevant.md` — reflect changed behavior in documentation
```

The `### Wiring Phase (added by \`/ll:wire-issue\`)` heading (line 388) and
its italic attribution line (line 390) are unchanged — only the four list
items (lines 392-395) change from `N.`/`N+1.`/`N+2.`/`N+3.` numbering to
plain `-` bullets.

### Instruction Text, Not Only the Example

Changing the fenced example alone is **not sufficient**. Phase 8b's only
prose instruction (`skills/wire-issue/SKILL.md:385`) reads "append a
wiring-specific phase to the existing `## Implementation Steps` section" and
says nothing about markers; an agent handed an issue whose parent list is
numbered `1.`–`9.` can still reasonably continue that numbering, because
nothing forbids it. An example is weak instruction. Line 385 must therefore
gain an explicit directive, e.g.:

```
Use plain `-` bullets for these entries. Do **not** continue the parent
list's numbering — the Wiring Phase is a distinct set of touchpoints and
makes no claim about position in the parent sequence.
```

Without this sentence the change may not actually take effect at runtime,
which is the difference between a cosmetic edit and the fix this issue asks
for.

### Vestigial `implementation_steps_count`

Phase 8b's numbering is the sole consumer of
`implementation_steps_count: N` (`skills/wire-issue/SKILL.md:120`, emitted in
Phase 3's `EXISTING_WIRING` block) — established under Call Path below and
re-confirmed this pass: no other phase, no `skills/wire-issue/output-report.md`
field, and no code in `scripts/little_loops/` reads it.

**Decision: remove the `implementation_steps_count: N` line from the
`EXISTING_WIRING` template.** A dead count left in the structured summary is
a standing invitation to re-derive numbering in a future edit. Phase 3's
prose item 6 ("**Implementation Steps** — what phases are already described",
line 109) stays: knowing which phases exist is still needed to avoid
duplicating an existing step in `new_impl_steps`; only the numeric count goes.

### Decision: Regression Lock Shape (Needle Tuples vs. Mirror-Equality Test)

The wiring pass proposed six `DOC_STRINGS_ABSENT`/`DOC_STRINGS_PRESENT` tuples
— the `N. Update` absence and the `-` bullet presence, each repeated across
`skills/wire-issue/SKILL.md` and both host mirrors. **Decision: do not do
that.** Two tuples on the source file, plus one mirror-equality test.

Rationale:
- The tuples only ever guard *two specific strings*. The failure mode this
  issue actually cares about — a skipped `ll-adapt --host … --apply` leaving
  the mirrors stale — is general, and recurs on every future edit to any
  mirrored skill.
- The mirrors are verbatim body copies. `GeminiEmitter.emit_skill()`
  (`scripts/little_loops/adapters/gemini.py:78-105`) delegates to
  `_prepare_skill_content()`, which rewrites frontmatter only; the emitter
  writes that result unchanged. Verified empirically on the current tree: the
  source and both mirrors are identical below the closing `---`, and differ
  only by the source's `metadata.short-description:` line (source line 17),
  which the emitter drops.

> **Comparison must strip the whole frontmatter block, not one line.** A test
> written as `tail -n +2` (i.e. dropping only the opening `---`) fails
> immediately on the current tree, because `metadata.short-description:` still
> falls inside the compared region. The test must split each file on its
> **closing** `---` delimiter and compare only what follows. This is the one
> detail most likely to be mis-implemented from the evidence above.
- **No mirror-drift test exists anywhere today.** `scripts/tests/test_adapters.py`
  exercises the emitters' behavior, not the freshness of the committed
  `.gemini/` and `.kimi-code/` trees. This is the gap that makes a skipped
  re-run silent, and needle tuples do not close it.

Implementation shape:
1. `ENH-2996`-tagged tuples on the source file only, in
   `scripts/tests/test_wiring_skills_and_commands.py`. These are the
   issue-specific lock. The exact needles are pinned below — do not
   improvise them.
2. One test asserting the post-frontmatter body of
   `skills/wire-issue/SKILL.md` equals that of both mirrors. This subsumes
   the four mirror tuples and guards every future edit. Its assertion message
   must name the remedy verbatim: `ll-adapt --host gemini --apply && ll-adapt
   --host kimi --apply`. This test will fire on *every* future edit to
   `skills/wire-issue/SKILL.md`, usually for someone who has never read this
   issue; a bare `AssertionError` on a body mismatch is not actionable.

#### Pinned needles

The `DOC_STRINGS_*` tables do **plain substring matching**, which drives the
needle choice:

- `DOC_STRINGS_ABSENT` needle: **`"N+1. Update"`** — *not* `"N. Update"`.
  `"N. Update"` is not a substring of `"N+1. Update"`/`"N+2. Update"`/
  `"N+3. Update"`, so it would guard only the first of the four markers.
  `"N+1. Update"` is unique repo-wide today (3 hits: the source skill and the
  two mirrors, all of which this issue changes).
- `DOC_STRINGS_PRESENT` needle: **``"- Update `path/to/caller.py`"``** —
  verified unique across `skills/`, `commands/`, and `agents/` on the current
  tree.

A second `DOC_STRINGS_ABSENT` tuple for `"N. Update"` is welcome but not
required; the `N+1` needle is the load-bearing one. Do not add mirror-path
tuples — mirror coverage is the body-equality test's job (see above).

If step 2 is scoped up during implementation into a general all-skills drift
gate (compare every `skills/*/SKILL.md` against its emitted mirrors), split
that into its own ENH rather than growing this one — a wire-issue-scoped
equality assertion is sufficient here.

**Drive-by fix (in scope):** `scripts/tests/test_wiring_skills_and_commands.py:275`
— the `DOC_STRINGS_ABSENT` assertion message is missing its `f` prefix, so
every absence failure prints literal `{issue_id}`/`{doc_rel}`/`{needle!r}`
braces instead of values. This issue adds entries to that exact table; fix
the one-character defect while there.

**Optional drive-by (cosmetic, take it or leave it):** the
`# -- 17 string-absence assertions --` header comment above
`DOC_STRINGS_ABSENT` is already stale (the table holds 25 entries before this
issue adds any). Either correct the count or drop the number from the comment.
Not an acceptance criterion.

### Call Path
`skills/wire-issue/SKILL.md` (Phase 8b template text, edited by hand for
this issue) -> `emit_skill` -> `.gemini/skills/wire-issue/SKILL.md` (mirror
regenerated by re-running `ll-adapt --host gemini --apply` after the
template edit). The equivalent Kimi mirror path is
`skills/wire-issue/SKILL.md` -> `ll-adapt --host kimi --apply` ->
`.kimi-code/skills/wire-issue/SKILL.md`.

Separately, within `skills/wire-issue/SKILL.md` itself: Phase 3
(`SKILL.md:100-121`, computes `implementation_steps_count: N` inside
`EXISTING_WIRING`) -> Phase 8b (`SKILL.md:383-396`, template-substitutes
`N`/`N+1`/... into the Wiring Phase list) -> issue file's
`## Implementation Steps` section (rendered output). `implementation_steps_count`
is local scratch state consumed only by Phase 8b's own numbering —
confirmed not re-emitted or read by `skills/wire-issue/output-report.md`
(its `[N]` at line 45 is a count of `new_impl_steps`, a distinct
Phase-4-derived list, not this field) or by any code in
`scripts/little_loops/`.

## Integration Map

### Files to Modify
- `skills/wire-issue/SKILL.md` — Phase 8b (lines 383-396)

_Wiring pass added by `/ll:wire-issue`:_
- `.gemini/skills/wire-issue/SKILL.md` — byte-identical mirror of Phase 8b
  (its own lines 387-395), produced by `GeminiEmitter.emit_skill()`
  (`scripts/little_loops/adapters/gemini.py`), which only rewrites
  frontmatter and copies the body verbatim. Will silently keep the old
  `N.`/`N+1.` numbering after this edit unless `ll-adapt --host gemini
  --apply` is re-run.
- `.kimi-code/skills/wire-issue/SKILL.md` — same situation (its own lines
  391-394), regenerated via `ll-adapt --host kimi --apply`.

### Dependent Files (Callers/Importers)
- `skills/wire-issue/output-report.md:45` — `## IMPLEMENTATION STEPS CHANGES`
  reports `[N] new steps added to Wiring Phase` as a *count* (from
  `new_impl_steps`'s length), not a positional sequence number. No change is
  required for correctness under either option. **Optional wording cleanup
  (in scope):** after this change the entries are bullets, not numbered
  steps, so "new steps added" keeps describing the section in the vocabulary
  this issue removes — reword to `[N] wiring touchpoints added`.
- No Python code parses `## Implementation Steps` numbering. The only
  `\d+\.`-matching regex in the codebase
  (`scripts/little_loops/issue_parser.py:39`,
  `_CRITERION_BULLET_PATTERN`) is scoped to `extract_criteria()`
  (line 1758) and only scans the Acceptance Criteria / Expected Behavior
  sections, never Implementation Steps.
  `scripts/little_loops/cli/issues/size.py:41` references the
  `Implementation Steps` heading only to detect presence for size scoring,
  not to parse numbering.

_Wiring pass added by `/ll:wire-issue`:_
- `commands/reconcile-issue.md:60-61,66-67,111,126` — describes reading
  "every bullet under `### Wiring Phase`" as a source-of-truth section.
  Format-agnostic prose (reads "bullets," not "numbered items") — no
  functional change needed, but it is a genuine consumer of the section's
  rendered shape.

### Similar Patterns
- `commands/refine-issue.md:26-59` (`## Register: Constraints, Not Recipes`) —
  guidance on when imperative sequencing is legitimate at all; lines 50-53
  carry the Implementation Steps-specific rule ("prefer phrasing each entry as
  an outcome plus its verification, not an edit instruction")

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Where `N` currently comes from: `skills/wire-issue/SKILL.md` Phase 3
  (lines 100-121) reads the issue's `## Implementation Steps` section and
  records only a raw count as `implementation_steps_count: N` inside the
  `EXISTING_WIRING` structured summary (line 120) — a prose-level scan by
  the executing agent, not a deterministic parser. Phase 8b (lines 383-396)
  then continues straight off that count with no live/dead filtering
  applied at any stage.
- `ENH-2995` (`status: done` as of this pass — was open when the above
  paragraph was researched) introduced the in-place `> ⚠ Superseded — see
  § ...` marker convention referenced there. This closes Option B's
  dependency, but does not change this issue's selection: Option A was
  chosen for zero coupling to that mechanism, not merely because it was
  unavailable at decision time.
- Marker-convention precedent: every other additive block in this
  template system — `skills/wire-issue/SKILL.md`'s own sibling Phase-8a
  subsections (`### Dependent Files (Callers/Importers)` at lines 338-343,
  `### Documentation` at 354-360, `### Tests` at 364-371, `### Configuration`
  at 375-381) plus `commands/refine-issue.md`'s `### Codebase Research
  Findings` (lines 454-460, and reused at line 604 for gap-analysis mode) —
  uses a `###` heading with an italicized attribution line
  (`_Wiring pass added by `/ll:wire-issue`:_` / `_Added by
  `/ll:refine-issue` — based on codebase analysis:_`) and **plain
  unnumbered `-` bullets**. The current Wiring Phase (`N.`/`N+1.`
  numbering) is the only one of wire-issue's own Phase-8 sub-blocks that
  departs from this convention.
- No existing `W1`/`W2`-style lettered list convention exists in this
  codebase's issue-template system to align Option A with; the only
  `W1`/`W2` hits found are Mermaid diagram participant labels in
  `docs/ARCHITECTURE.md` (unrelated). The nearest actual lettering
  precedent (`8a`/`8b`/`8c` in `skills/wire-issue/SKILL.md`, `5a`/`5b` in
  `commands/refine-issue.md`) letters phase headings in the skill's own
  procedural instructions, not list items written into generated issue
  content — a different surface.
- The mirrors under `.gemini/` and `.kimi-code/` are **git-tracked**, not
  gitignored (`git ls-files` confirms both), so the `ll-adapt` re-run produces
  two committed diffs. No test detects mirror drift against
  `skills/wire-issue/SKILL.md`, so skipping the re-run fails silently — which
  is why the regression-lock tuples below cover all three paths, not just the
  source skill.

### Tests
- No dedicated test file covers Phase 8b's numbering behavior specifically
  (it is markdown-template prose interpreted by the executing agent, not
  code); no test needs updating for either option.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` — no existing entry
  locks in Phase 8b's marker style either way (confirmed: no `Wiring
  Phase`/`N.`/`N+1`/`8b` hits in this file today). The file's established
  `DOC_STRINGS_PRESENT`/`DOC_STRINGS_ABSENT` parametrized-tuple pattern
  (`(doc_path, string, issue_id)`, e.g. line 228's
  `("agents/codebase-analyzer.md", "file:line", "ENH-1299")`) is the
  natural, already-precedented home for a regression guard: add
  `("skills/wire-issue/SKILL.md", "N. Update", "ENH-2996")` to
  `DOC_STRINGS_ABSENT` and/or a `DOC_STRINGS_PRESENT` tuple for the new
  `-` bullet form, so a future edit can't silently reintroduce numbered
  markers. Optional — not required for correctness, since nothing parses
  the old format — but closes the one gap where the new convention isn't
  locked in anywhere outside this issue's own prose.
  > ⚠ Superseded in part — see § Program Design → Decision: Regression Lock
  > Shape. The `DOC_STRINGS_*` tuples are kept but scoped to
  > `skills/wire-issue/SKILL.md` only; mirror coverage moves to a
  > body-equality test. The tuples are no longer optional.

### Documentation
- None found referencing Phase 8b's numbering scheme outside
  `skills/wire-issue/SKILL.md` itself and `skills/wire-issue/output-report.md`
  (confirmed not to need changes, see Dependent Files above).

### Configuration
- N/A

## Implementation Steps

1. Phase 8b's example list in `skills/wire-issue/SKILL.md` (lines 392-395)
   carries plain `-` bullets instead of `N.`/`N+1.`/`N+2.`/`N+3.`, leaving the
   `### Wiring Phase` heading (388) and italic attribution line (390)
   untouched — verified by reading the fenced block.
2. Phase 8b's instruction prose (line 385) explicitly forbids continuing the
   parent list's numbering, so the behavior does not rest on the example alone
   (see Program Design → Instruction Text, Not Only the Example) — verified by
   reading the sentence added after line 385.
3. `implementation_steps_count: N` is gone from the `EXISTING_WIRING` template
   (line 120) while Phase 3's prose item 6 (line 109) is retained — verified by
   `grep -n implementation_steps_count skills/wire-issue/SKILL.md` returning
   nothing.
4. Both host mirrors carry the identical body, regenerated (not hand-edited)
   via `ll-adapt --host gemini --apply` and `ll-adapt --host kimi --apply`, and
   their diffs are committed alongside the source edit — verified by
   `grep -n "N. Update" .gemini/skills/wire-issue/SKILL.md
   .kimi-code/skills/wire-issue/SKILL.md` returning nothing.
5. The new convention is locked against silent regression by `ENH-2996`-tagged
   tuples on `skills/wire-issue/SKILL.md` in
   `scripts/tests/test_wiring_skills_and_commands.py` — at minimum one
   `DOC_STRINGS_ABSENT` (`N+1. Update`) and one `DOC_STRINGS_PRESENT`
   (``- Update `path/to/caller.py` ``), using the pinned needles from Program
   Design → Pinned needles — verified by the absent-tuple failing if the
   `N+1.` marker is reintroduced.
6. Mirror staleness is caught by a body-equality test rather than duplicated
   needles (see Program Design → Decision: Regression Lock Shape), comparing
   each file's content *after its closing `---` frontmatter delimiter* (not
   `tail -n +2`, which still includes the diverging
   `metadata.short-description:` line and fails on the current tree) — verified
   by the test failing when `skills/wire-issue/SKILL.md` is edited without a
   corresponding `ll-adapt` re-run, and by its failure message naming the
   `ll-adapt --host gemini --apply && ll-adapt --host kimi --apply` remedy.
7. `scripts/tests/test_wiring_skills_and_commands.py:275`'s absence-assertion
   message interpolates its values — verified by the missing `f` prefix being
   restored and a deliberately-failing absence case printing real path and
   needle text.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Edit `skills/wire-issue/SKILL.md` Phase 8b per the selected option (Option A).
- Re-run `ll-adapt --host gemini --apply` and `ll-adapt --host kimi --apply`
  so `.gemini/skills/wire-issue/SKILL.md` and
  `.kimi-code/skills/wire-issue/SKILL.md` pick up the same template change
  (both are byte-for-byte mirrors, regenerated from source, not
  hand-edited).
- No *existing* test asserts on Phase 8b's numbering or bullet format
  (`test_wiring_skills_and_commands.py`, `test_enh494_skill_companions.py`,
  and others checked; none couple to this section's list-marker style), so
  nothing breaks — but nothing guards the change either.
- Add regression-lock tuples to
  `scripts/tests/test_wiring_skills_and_commands.py`'s
  `DOC_STRINGS_ABSENT`/`DOC_STRINGS_PRESENT` tables (existing
  `(doc_path, string, issue_id)` pattern) asserting the old `N. Update`
  marker is gone and the new `-` bullet form is present. Cover all three
  paths — `skills/wire-issue/SKILL.md` plus both host mirrors — since the
  mirrors are git-tracked and no test detects drift, so a skipped `ll-adapt`
  re-run would otherwise pass silently. [Wiring pass, `/ll:wire-issue`]
  > ⚠ Superseded — see § Program Design → Decision: Regression Lock Shape.
  > The three-path tuple duplication is replaced by two source-scoped tuples
  > plus one mirror body-equality test; the underlying drift concern stands.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Whichever option is chosen, the change is confined to
  `skills/wire-issue/SKILL.md` Phase 8b (lines 383-396) — no other file
  needs to change for the numbering scheme itself (see Integration Map →
  Dependent Files).
- The Wiring Phase's sibling Phase-8a subsections already use a `###`
  heading + italic attribution + plain unnumbered `-` bullets
  (`skills/wire-issue/SKILL.md:338-381`); Option A brings Phase 8b in line
  with that existing pattern rather than introducing a new one.
- Nothing downstream parses `## Implementation Steps` numbering (no `\d+.`
  regex scoped to that section anywhere in `scripts/little_loops/`), so
  either option is safe to make without a companion code change.
- `ENH-2995` has since landed (`status: done`), so Option B is no longer
  blocked — but Option A is what this issue selects, and remains
  independent of ENH-2995 regardless. `check_reconcile_needed`-style
  staleness detection still has no equivalent for Implementation Steps.
- Verification: after editing Phase 8b's template text, exercise
  `/ll:wire-issue` against an issue whose `## Implementation Steps` has 9
  entries (e.g. re-run against `ENH-2500`'s issue file, cited in this
  issue's Current Behavior, or a synthetic fixture) and confirm the emitted
  Wiring Phase entries carry no numeric claim about position in the parent
  sequence.

## Acceptance Criteria

- [ ] The four Wiring Phase template entries in `skills/wire-issue/SKILL.md`
      Phase 8b use plain `-` bullets; `grep -n "^N\. \|^N+[0-9]\." skills/wire-issue/SKILL.md`
      returns nothing.
- [ ] Phase 8b's instruction prose explicitly directs plain `-` bullets and
      forbids continuing the parent list's numbering.
- [ ] `grep -rn implementation_steps_count skills/ scripts/ .gemini/ .kimi-code/`
      returns nothing; Phase 3's prose item 6 is unchanged. The mirror paths are
      part of this grep deliberately: both carry the line today (each at their
      own line 119), and scoping the check to `skills/ scripts/` would let a
      skipped `ll-adapt` re-run pass this criterion while the mirrors stay stale.
- [ ] `.gemini/skills/wire-issue/SKILL.md` and
      `.kimi-code/skills/wire-issue/SKILL.md` bodies match the updated source
      (regenerated via `ll-adapt`, committed) and contain no `N.`/`N+1.` markers.
- [ ] `scripts/tests/test_wiring_skills_and_commands.py` gains at least two
      `ENH-2996`-tagged tuples, all scoped to `skills/wire-issue/SKILL.md` and
      none to a mirror path — including one `DOC_STRINGS_ABSENT` with needle
      `N+1. Update` and one `DOC_STRINGS_PRESENT` with needle
      ``- Update `path/to/caller.py` ``. (An extra `N. Update` absence tuple is
      permitted; the tables match by plain substring, so `N. Update` alone does
      **not** cover `N+1./N+2./N+3.` — see Program Design → Pinned needles.)
- [ ] A body-equality test asserts that the content of
      `skills/wire-issue/SKILL.md` following its **closing `---` frontmatter
      delimiter** is identical to that of both host mirrors, and fails when the
      source is edited without an `ll-adapt` re-run. Its failure message names
      the remedy: `ll-adapt --host gemini --apply && ll-adapt --host kimi
      --apply`.
- [ ] `scripts/tests/test_wiring_skills_and_commands.py:275`'s absence assertion
      uses an f-string, so failures print real values rather than literal braces.
- [ ] `python -m pytest scripts/tests/` exits 0.

**Manual (post-merge, not suite-verifiable):**

- [ ] A `/ll:wire-issue` pass against an issue with a 9-entry numbered
      `## Implementation Steps` emits a Wiring Phase with no positional numeric
      claim (see Codebase Research Findings → Verification). This exercises live
      agent behavior and cannot be asserted from `python -m pytest
      scripts/tests/`; it must be run by hand and is **not** a merge gate. The
      suite-side proxy is the instruction-prose criterion above — do not mark
      this box from a static grep.

## Impact

- Cosmetic correctness in issues that have been through both refine and wire.
- Small: affects the 1,140 issues carrying a wiring marker, only where refine
  also deposited a contradiction.

## Success Metrics

- A wire pass over an issue with refuted steps produces a Wiring Phase that
  makes no false positional claim.

## Scope Boundaries

- Does **not** change what wire-issue discovers or how it writes Integration
  Map entries — the coupling findings are sound and stay as-is.
- Does **not** address wiring-block accumulation (that is ENH-2993's optional
  second half).
- Does **not** backfill existing issue files. The ~1,140 issues that already
  carry a numbered `### Wiring Phase` keep it. This change affects the template
  only, so the new convention applies to *future* wire passes; migrating
  historical issues is explicitly out of scope and should not be attempted as
  part of this work.
- Mirror scope is exactly `.gemini/` and `.kimi-code/`. `.codex/` has no
  `wire-issue` skill on the current tree (confirmed), so it needs no
  regeneration and no equality coverage here.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/wire-issue/SKILL.md` | Contains Phase 8b, the section being changed |
| `commands/refine-issue.md` | Source of the refuted-step condition |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-02_

**Readiness Score**: 94/100 → PROCEED
**Outcome Confidence**: 87/100 → High

Both gaps from the prior pass are resolved: the `## Program Design` section
now exists (signature, before/after diff, `Call Path`) and `ll-issues
format-check` confirms the Program Design gate passes cleanly; `blocked_by:
[ENH-2995]` is satisfied (`ENH-2995` is `status: done`). No open gaps or
outcome risk factors remain.

## Session Log
- `/ll:confidence-check` - 2026-08-02T20:41:25 - `3a335d2c-6a4c-4144-a579-513545967cf2.jsonl`
- `/ll:confidence-check` - 2026-08-02T20:06:13 - `1da01c9f-8556-4c0a-a1e0-8d7eb0047f46.jsonl`
- `/ll:confidence-check` - 2026-08-02T19:42:09 - `1911b6e3-deb9-402f-a2b8-ed88f18f9129.jsonl`
- `/ll:wire-issue` - 2026-08-02T19:27:31 - `b162a59f-7793-4e9a-90ed-5e38fef057fa.jsonl`
- `/ll:refine-issue` - 2026-08-02T19:14:06 - `c2ddc2b8-a949-46f6-8466-7e925f3a2db0.jsonl`
- `/ll:confidence-check` - 2026-08-02T15:45:51 - `20ea844a-65cc-4307-b288-00dcc23e4621.jsonl`
- `/ll:wire-issue` - 2026-08-02T15:40:19 - `54b8b61c-90df-41f1-af64-799342e6500a.jsonl`
- `/ll:decide-issue` - 2026-08-02T15:26:29 - `0a208318-6b67-47ba-88f1-23b17a2f5884.jsonl`
- `/ll:refine-issue` - 2026-08-02T15:21:01 - `1a6be5be-a3c2-4f65-a811-ac343eeaa258.jsonl`
- `/ll:capture-issue` - 2026-08-02T13:45:57 - `fac7dff4-61c1-4496-95b8-7bd1993d2971.jsonl`

## Status

- **Status**: open

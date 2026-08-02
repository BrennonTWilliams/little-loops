---
id: ENH-2995
status: open
priority: P2
captured_at: '2026-08-02T13:43:01Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to:
- ENH-2992
- ENH-2993
- ENH-2996
testable: true
confidence_score: 92
outcome_confidence: 78
score_complexity: 20
score_test_coverage: 15
score_ambiguity: 20
score_change_surface: 20
---

# refine-issue marks superseded directive lines in place

## Summary

`/ll:refine-issue`'s Preservation Rule forbids overwriting any section with >2
lines of meaningful content. When codebase research discovers that the issue's
own `## Implementation Steps` (or `### Files to Modify`, or `## Acceptance
Criteria`) are *wrong*, refine's only available move is to append a rebuttal
underneath them. The refuted directive text stays in place, unmarked, and an
implementer reading top-down executes a plan the same file already disproved.

Add a narrow carve-out: refine may annotate a refuted directive line in place
with a superseded marker pointing at the finding that refutes it. Nothing is
removed or rewritten — only marked.

## Current Behavior

The Preservation Rule (`commands/refine-issue.md:444-460`) states:

> **Do NOT overwrite non-empty sections** with >2 lines of meaningful text
> - **Append** research findings as a subsection or additional bullets
> - **Do NOT replace** existing human-written or previously-refined content

This is correct as a default — it protects human prose from being bulldozed.
But it applies uniformly, including to the case where refine's own research
establishes that a directive line is factually false. The result is a file
that argues with itself.

**Measured across `.issues/` (2026-08-02):** of 1,295 issues containing a
`### Codebase Research Findings` block, **316 (24%)** contain correction
language inside that block — `is wrong`, `does not exist`, `will not work`,
`must be dropped`, `target file is wrong`, `is stale`, `omit entirely`.

Worst case is `ENH-2500`
(`.issues/enhancements/P3-ENH-2500-per-run-dir-pending-file-and-scope-for-prompt-across-issues.md`),
with 13 correction phrases. Its `## Implementation Steps` (line 264) opens:

> 1. Add `pending_file: "${context.run_dir}/pending.txt"` to the loop's `context:` block

and the `### Codebase Research Findings` subsection 16 lines below (line 280)
says:

> **Steps 1 + 3 are mutually incompatible with how context template resolution
> works** … Revised step 1: **omit entirely**.

Steps 6 and 7 are likewise refuted ("Step 6 target file is wrong … does not
exist"). Four of nine steps are dead, and nothing at the point of reading says
so.

## Expected Behavior

When a research finding directly refutes a specific directive line, refine
annotates that line in place:

```markdown
## Implementation Steps

1. Add `pending_file: "${context.run_dir}/pending.txt"` to the loop's `context:` block
   > ⚠ Superseded — omit entirely; see § Codebase Research Findings under Implementation Steps

2. Add `scope: ["${context.run_dir}"]` to the loop's top-level keys
```

Reading top-down, the refutation is visible at the point of the claim, **and
carries the reason** — a bare pointer back to the findings block would leave the
reader doing the same findings-to-step mapping by hand that this issue exists to
eliminate. The original text survives verbatim; the finding remains the
authority; no content is deleted.

## Motivation

The primary consumer of a refined issue is a headless automation session with
no human present (`commands/refine-issue.md:28-31` says so explicitly). That
session reads the issue's directive sections as instructions. A refuted step
that carries no marker at the point of reading is a defect injected into the
issue by the very pass meant to improve it — refine is the only actor that
knows the step is dead, and the Preservation Rule is what stops it from saying
so where it counts.

24% of refined issues carry at least one such contradiction. Only 19 issues in
the entire corpus have ever been through `/ll:reconcile-issue`, the skill built
to resolve them (see ENH-2992) — so for practical purposes the contradiction is
permanent once written.

## Proposed Solution

Add a bounded exception to the Preservation Rule in
`commands/refine-issue.md` § Preservation Rule, permitting **annotation** (not
replacement) of a directive line when a finding in the same pass refutes it.

The mechanism already exists in the same file. Gap-analysis mode
(`commands/refine-issue.md:605-608`) writes exactly this shape for stale
anchors:

```
> ⚠ Anchor `old_function:N` no longer resolves — verify against current codebase.
```

The carve-out generalizes that one case. Constraints that keep it narrow:

- **Annotate only, never edit** the refuted line's own text.
- Applies only to directive sections: `## Implementation Steps`,
  `### Files to Modify`, `## Acceptance Criteria`. Never to `## Summary`,
  `## Motivation`, `## Proposed Solution`, or any `### Option …` /
  `### Decision Rationale` prose — the same preserve-list
  `commands/reconcile-issue.md` already enforces.
- Fires only when the refutation comes from **this pass's own research
  findings**, not from re-reading prior appended blocks.
- The marker is a blockquote line immediately following the refuted line,
  **indented to that line's own content column** (3 spaces under a `1. ` step,
  2 under a `- ` bullet), so list numbering and any downstream parser that keys
  on `^\d+\.`/`^[-*]` are unaffected. At column 0 the blockquote would both
  terminate the list in CommonMark and forfeit that parser-safety property.
- Idempotent: skip if a marker is already present under that line, detected by
  substring-containment of the stable prefix `⚠ Superseded` (not exact-line
  equality — the reason clause is expected to vary between passes).
- **Removable by a later pass**: a marker is the one exception to
  "never remove existing content" — see the removal rule below.

**Marker removal (un-marking)**: the Preservation Rule's "Do NOT remove any
existing content under any circumstance" would otherwise make every marker
permanent — a step that becomes valid again (the codebase moved, or the original
finding was itself wrong) would keep a false ⚠ forever, with no actor able to
clear it. The carve-out therefore grants exactly one deletion right: **a refine
pass may delete a line matching the `⚠ Superseded` marker convention when this
pass's own findings no longer refute the line above it.** Only lines matching
that convention are ever deletable; the refuted line and all other content stay
untouchable. Removal is silent (no tombstone) — the marker is derived state, not
a record.

**Interaction with `/ll:reconcile-issue`**: this is complementary, not
competing. Reconcile *rewrites* directive sections wholesale on a plateau;
this marks them at write time so the contradiction is legible in the interim —
which, given 19 reconciles against 1,703 refines, is nearly always.

## Program Design

Two halves, and they are different kinds of change:

1. **The carve-out itself** is a prose-instruction change
   (`commands/refine-issue.md`, executed by the LLM via `Edit`), not Python.
   The "signature" below is not code to be written — it is the decision
   procedure the amended Preservation Rule text must encode precisely enough
   for a headless implementer to follow without guessing.
2. **The `unmarked_superseded_directive` gap class** (Implementation Step 5)
   *is* ordinary Python, in `issue_parser.py` + `cli/issues/format_check.py`,
   following the `stale_file_ref` class's existing shape. It is what makes
   half 1 falsifiable.

### Signatures

- `annotate_superseded_directive(section: str, line: str, next_line: str, findings: list[str]) -> str | None | REMOVE`
  — returns the marker text to insert below `line`, `None` for a no-op, or the
  sentinel `REMOVE` meaning "delete the existing marker on `next_line`".

Behavior:
1. `section` must be one of `## Implementation Steps`, `### Files to Modify`,
   `## Acceptance Criteria` — never `## Summary`, `## Motivation`,
   `## Proposed Solution`, `### Option …`, `### Decision Rationale`.
2. `findings` must be this pass's OWN `### Codebase Research Findings`
   entries — never findings re-read from a prior pass's appended block.
3. **Refutation test.** An entry in `findings` refutes `line` when it
   names or quotes `line` *and* asserts it is wrong. The correction phrases
   below are the detection list — the same list that produced this issue's
   316/1,295 corpus measurement, and the list the format-check gap class
   (Implementation Step 5) must reuse verbatim:

   `is wrong` · `does not exist` · `will not work` · `must be dropped` ·
   `target file is wrong` · `is stale` · `omit entirely`

   The list is **non-exhaustive guidance for LLM judgment**, not a closed
   grammar: a finding that plainly refutes the line in other words still
   qualifies. It is closed only for the deterministic format-check class,
   which must not invent phrases beyond it.
   If no entry refutes `line`, go to step 7.
4. Else `marker_text = "> ⚠ Superseded — {reason}; see § Codebase Research
   Findings under {section}"`, where `{reason}` is a ≤10-word clause lifted
   from the refuting finding (e.g. `omit entirely`, `target file does not
   exist`). The reason is required: without it, N refuted lines in one section
   all receive byte-identical markers and the reader must re-derive the
   findings-to-line mapping by hand.
5. Idempotency: if `next_line` contains the substring `⚠ Superseded`, return
   `None` — containment on that stable prefix, **not** equality against
   `marker_text`, since `{reason}` varies between passes. This follows the
   convention in Call Path (`if "Decomposed into" in content`,
   `any(marker in content ...)`); an exact-equality check would silently
   double-mark whenever the reason clause was worded differently.
6. Else: return `marker_text`, to be inserted as a new line immediately below
   `line`, **indented to `line`'s own content column** — 3 spaces under a
   `1. ` step, 2 under a `- ` bullet — and never prefixed with a digit-dot or
   `-`/`*` (must not match the bullet/option anchors below). Column-0
   placement is wrong twice over: it terminates the enclosing list in
   CommonMark, and it voids the `^`-anchored parser-collision argument in
   § Tests.
7. Un-marking: if `line` is not refuted by this pass's `findings` **and**
   `next_line` contains `⚠ Superseded`, return `REMOVE`. This is the sole
   deletion right the carve-out grants, and it applies only to lines matching
   the marker convention.

Invariant: `line` itself is never edited, reordered, or deleted. No section
outside the three listed is ever touched. The only deletable line in the file
is a `⚠ Superseded` marker under a no-longer-refuted directive line.

### Call Path

- `commands/refine-issue.md` § Preservation Rule (lines 444-460) — the carve-out
  is stated here as a bounded exception to "Do NOT overwrite non-empty
  sections".
- `commands/refine-issue.md:605-608` — the existing gap-analysis stale-anchor
  blockquote (`> ⚠ Anchor ... no longer resolves ...`) whose shape this
  carve-out reuses rather than inventing new marker syntax.
- `_append_decomposition_note` (`scripts/little_loops/recursive_finalize.py:91`)
  and `check_content_markers` (`scripts/little_loops/issue_manager.py:537`) —
  the idempotency convention step 5 above follows (plain substring-containment
  check, not a regex or structural parse).
- `_CRITERION_BULLET_PATTERN` and `_OPTION_PATTERNS`
  (`scripts/little_loops/issue_parser.py`) — the anchors the inserted marker
  line must not collide with (step 6).
- `scripts/little_loops/issue_parser.py:255` (gaps dataclass field), `:528`
  (detection branch) and `scripts/little_loops/cli/issues/format_check.py:154`
  (print branch) — the `stale_file_ref` gap class, the shape the new
  `unmarked_superseded_directive` class copies. Its detection input is
  § Program Design step 3's correction-phrase list, used as a closed set here
  even though it is open-ended guidance for the LLM.

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — § Preservation Rule (lines 444-460): add the
  annotation carve-out with its scope constraints, the marker-removal right,
  and the indentation/idempotency rules; § 5a enrichment rules
  (lines 323-443) reference it where Implementation Steps are discussed
  (lines 425-442)
- `scripts/little_loops/issue_parser.py` — the `unmarked_superseded_directive`
  gap class (Implementation Step 5): a field on the gaps dataclass alongside
  `stale_file_ref` (line 255), its `__bool__`/`to_dict` entries (lines 272,
  289), its docstring entry (line 365), and the detection branch modelled on
  line 528
- `scripts/little_loops/cli/issues/format_check.py` — print branch (cf.
  `stale_file_ref` at lines 154-155) plus the gap-class list in the `--help`
  text (lines 62-64) and module docstring (line 161)
- `scripts/little_loops/cli/issues/__init__.py:124` — the same gap-class list
  in the subcommand summary line
- `.claude/CLAUDE.md` — § Issue File Format / CLI Tools `ll-issues` bullet
  enumerates the format-check gap classes; add the new one

### Dependent Files (Callers/Importers)
- **Before this issue**: none. The Preservation Rule and the stale-anchor
  marker it reuses are pure prose instructions inside
  `commands/refine-issue.md`, executed by the LLM via the `Edit` tool — no
  Python code in `scripts/little_loops/` emits, parses, or depends on the
  `> ⚠ ...` marker string (grep for `⚠` and `"> ⚠"` across
  `scripts/little_loops/` returns only unrelated CLI output formatting).
- **After this issue**: the `unmarked_superseded_directive` gap class becomes
  the first and only Python consumer of the marker string, making
  `issue_parser.py`'s detection branch a dependent of the exact marker text.
  Keep the two in sync: the stable prefix the gap class greps for is
  `⚠ Superseded`, matching § Program Design step 5's idempotency check, so a
  reworded reason clause never breaks either one.
- `_sweep_file()`
  (`scripts/little_loops/issues/anchor_sweep.py`) only rewrites resolved
  anchors in place and tracks a `skipped_refs` count — it has no code path
  that emits the blockquote warning text; that text is written by the LLM
  following the command's prose instruction.

### Similar Patterns
- `commands/refine-issue.md:605-608` — gap-analysis mode's stale-anchor
  warning block; the single blockquote line itself is `refine-issue.md:607`
  (605 is the numbered-list wrapper, 608 the closing fence) — the marker text
  is the exact shape and blockquote convention to reuse
- `commands/reconcile-issue.md:42-63` § Contract — the authoritative
  rewrite-eligible vs preserve-untouched section split. Rewrite-eligible:
  `## Implementation Steps`, `## Acceptance Criteria`, `### Files to Modify`
  (unconditional), plus `## Scope Boundaries` (conditional, gated on a
  recorded-finding contradiction). Preserve-untouched: `## Summary`,
  `## Motivation`, `## Current Behavior`, `## Expected Behavior`,
  `## Proposed Solution` and any `### Option …` / `### Decision Rationale`,
  `### Codebase Research Findings`, `### Wiring Phase`, `### Similar
  Patterns`, `### Constraints`, `## Confidence Check Notes`, `## Session
  Log`, `## Status`. ENH-2995's proposed carve-out scope (`## Implementation
  Steps`, `### Files to Modify`, `## Acceptance Criteria`) is a strict subset
  of reconcile's unconditional three-item rewrite list — it deliberately
  omits reconcile's conditional fourth item, `## Scope Boundaries`.
- Idempotency convention used elsewhere for "don't re-add a marker that's
  already present": a plain substring-containment check against file content,
  not a regex or structural parse — e.g.
  `scripts/little_loops/recursive_finalize.py:91-97`
  `_append_decomposition_note()` (`if "Decomposed into" in content: return
  content`, docstring: "Idempotent: a second call is a no-op once the marker
  line exists"), `scripts/little_loops/issue_manager.py:537-560`
  `check_content_markers()` (`return any(marker in content for marker in
  markers)`), and the same shape at `session_log.py:230`,
  `issue_lifecycle.py:410`, `parallel/orchestrator.py:1770-1771`,
  `issue_discovery/search.py:472`. This is the convention to follow for the
  Proposed Solution's own "Idempotent: skip if an identical marker is already
  present under that line" constraint.

### Tests
- No existing test file asserts against `commands/refine-issue.md` prose
  directly (it is a markdown instruction file executed by the LLM, not
  Python).
- **The live parser risk is in `## Acceptance Criteria`, not Implementation
  Steps.** `_CRITERION_BULLET_PATTERN` (`issue_parser.py:39`,
  `^(?:-\s*\[[xX ]\]\s+|[-*]\s+|\d+\.\s+)(.+)$`) is reached only from
  `IssueParser.extract_criteria()` at `issue_parser.py:1782`, which walks
  `_CRITERIA_SECTION_NAMES` (`## Acceptance Criteria` / `## Expected
  Behavior`). That is the one section in the carve-out's scope with a live
  consumer, so it is the regression-test target: assert that a marker inserted
  under a criterion bullet is not returned as an extra criterion. It is not —
  the pattern is `^`-anchored under `re.MULTILINE` and an indented `> ⚠ …`
  line matches none of its three alternatives — but that is the assertion to
  write down.
- `## Implementation Steps` has **no parser at all** in
  `scripts/little_loops/` (`_OPTION_PATTERNS`, `issue_parser.py:579-586`,
  scans decision-option prose, not this section). The `^`-anchoring argument
  holds there for the same structural reason, but there is no live code path
  to regression-test; do not cite `extract_criteria()` as covering it.
- `cli/issues/size.py` *does* read the section — `_SOLUTION_HEADINGS`
  (line 41) includes `Implementation Steps` — but by word count, not
  structure. See § Impact.
- The `unmarked_superseded_directive` gap class (Implementation Step 5) needs
  ordinary unit coverage next to the other gap classes' tests: a fixture with
  correction language and no marker → flagged; the same fixture with a marker
  → clean; correction language in a *preserved* section (`## Summary`) → not
  flagged. This is the only genuinely behavioural test in the issue — the
  `TestSupersededDirectiveMarker` prose assertions cannot fail if refine never
  emits a marker.

_Wiring pass added by `/ll:wire-issue`:_
- Correction to the claim above: `_CRITERION_BULLET_PATTERN` is only ever
  applied by `IssueParser.extract_criteria()` against
  `_CRITERIA_SECTION_NAMES` (`## Acceptance Criteria` / `## Expected
  Behavior`) — it never scans `## Implementation Steps` today. The
  "won't be misparsed" claim still holds structurally (the regex is
  `^`-anchored either way, independent of which section calls it), but
  `extract_criteria()` is not currently a live code path over Implementation
  Steps specifically — don't cite it as the regression-test target for
  Implementation Steps coverage without first confirming which parser
  function (if any) walks that section. [Agent 3 finding]
- No existing test constructs an issue fixture with a blockquote line
  directly under a numbered `## Implementation Steps` item — this is
  genuinely new test surface, not an update to existing coverage. The
  closest structural-assertion template to copy is
  `scripts/tests/test_refine_issue_command.py::TestGapAnalysisMode`
  (lines 157-219), which slices a named section out of
  `commands/refine-issue.md` via `content.index(...)`/`content.find(...)`
  and asserts on substrings — no markdown AST, no regex compatibility
  check. Add a new `TestSupersededDirectiveMarker` class there asserting
  the Preservation Rule section documents the `> ⚠ Superseded — ...` marker
  and its scope constraints (annotate-only, three directive sections,
  same-pass-only, idempotent). [Agent 3 finding]
- `test_refine_issue_command.py::TestGapAnalysisMode::test_additive_only_contract_documented`
  and `::test_max_refine_count_exemption_documented` slice
  `#### 5. Apply Additive Changes Only` (`commands/refine-issue.md:600-612`),
  the same numbered-list region containing the existing stale-anchor
  `> ⚠ ...` precedent (line 605-608) this issue's carve-out reuses. Not
  expected to break, but re-verify their `content.index(...)`/`.find(...)`
  slice boundaries still capture the intended text if the new carve-out
  text is added inside or adjacent to that same section. [Agent 3 finding]

### Documentation
- None identified beyond `commands/refine-issue.md` itself; no other doc
  under `docs/` references the Preservation Rule or the stale-anchor marker
  convention.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:280` — § `/ll:reconcile-issue` characterizes
  `/ll:refine-issue` as strictly append-only for directive sections ("only
  **append** new 'Codebase Research Findings' bullets — they never rewrite
  the issue's own directive sections"). Once the annotation carve-out ships,
  refine also writes an inline `> ⚠ Superseded — ...` marker directly beneath
  a directive line itself, not just an appended bullet elsewhere — this line
  should note the distinction (annotate-in-place vs. append-elsewhere)
  without overstating it as a "rewrite" (it still isn't one). [Agent 2 finding]
- `docs/reference/COMMANDS.md:290` — same file, the `**Distinct from**` line
  parenthetically summarizes refine-issue as "(appends new research)"; same
  staleness risk, smaller surface. [Agent 2 finding]

### Registration / Manifest Files

_Wiring pass added by `/ll:wire-issue`:_
- `.gemini/commands/refine-issue.toml` (§ `Preservation Rule`, line 428) —
  a `ll-adapt`-generated verbatim mirror of `commands/refine-issue.md`'s body
  (via `scripts/little_loops/adapters/gemini.py`); goes stale once the
  Preservation Rule is amended until `ll-adapt --host gemini` is re-run. Not
  hand-edited; no code change needed, but the regen step must not be skipped.
  [Agent 2 finding]
- `.kimi-code/skills/ll-refine-issue/SKILL.md` (§ `Preservation Rule`) — same
  mirror relationship via `scripts/little_loops/adapters/kimi.py`; goes stale
  until `ll-adapt --host kimi` is re-run. [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. `commands/refine-issue.md` § Preservation Rule (lines 444-460) states the
   carve-out's scope constraint and the exact marker text/placement, matching
   the register `commands/reconcile-issue.md:42-63` § Contract already uses
   for its own rewrite-eligible/preserve-untouched split.
2. The marker reuses the blockquote shape already at
   `commands/refine-issue.md:607` (`> ⚠ Anchor ... no longer resolves ...`)
   rather than inventing new syntax, and the idempotency check follows the
   substring-containment convention already used at
   `scripts/little_loops/recursive_finalize.py:91-97` and
   `scripts/little_loops/issue_manager.py:537-560` (skip the append if the
   exact marker text is already present under the target line).
3. The marker placement does not collide with
   `scripts/little_loops/issue_parser.py`'s `_CRITERION_BULLET_PATTERN`
   (line 39) or `_OPTION_PATTERNS` (lines 579-586) — both anchor on
   `^\d+\.`/`^[-*]`, which an indented, non-digit-prefixed blockquote line
   does not match.
4. Re-running `/ll:refine-issue` against `ENH-2500`
   (`.issues/enhancements/P3-ENH-2500-per-run-dir-pending-file-and-scope-for-prompt-across-issues.md`)
   places superseded markers on its refuted Implementation Steps (1, 3, 6, 7
   per this issue's own measurement) and leaves every other section
   byte-identical.
5. **Deterministic enforcement gate.** Add an
   `unmarked_superseded_directive` gap class to `ll-issues format-check`
   (`scripts/little_loops/cli/issues/format_check.py`, joining the existing
   `missing`/`renamed`/`empty`/`boilerplate`/`testable`/`stale_file_ref`
   classes): flag an issue whose `### Codebase Research Findings` block
   contains a correction phrase from § Program Design step 3's closed list
   while no `⚠ Superseded` marker appears in `## Implementation Steps`,
   `### Files to Modify`, or `## Acceptance Criteria`. This is the same corpus
   scan that produced the 316/1,295 measurement in § Current Behavior, run as
   a check instead of a one-off. Without it the enhancement is unfalsifiable:
   step 6's test asserts only that the prose documents the marker and cannot
   fail if the behavior never fires. Precedent for a keyword-inference class
   is `testable` (doc-only). Report-only like the other classes — do not wire
   it into a blocking gate in this issue.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Add a `TestSupersededDirectiveMarker` test class to
   `scripts/tests/test_refine_issue_command.py`, following the
   `TestGapAnalysisMode` slice-and-assert idiom, asserting the amended
   Preservation Rule section documents the `> ⚠ Superseded — ...` marker and
   its scope constraints.
7. Update `docs/reference/COMMANDS.md:280` and `:290` (§ `/ll:reconcile-issue`)
   to acknowledge that `/ll:refine-issue` can now annotate a directive line
   in place with a superseded marker, not only append research bullets
   elsewhere — without overstating it as a rewrite (reconcile still owns that).
8. After merging, run `ll-adapt --host gemini` and `ll-adapt --host kimi` to
   regenerate `.gemini/commands/refine-issue.toml` and
   `.kimi-code/skills/ll-refine-issue/SKILL.md` so the mirrored Preservation
   Rule text stays in sync.

## Impact

- Refined issues stop shipping self-contradicting instructions to headless
  implementers.
- Zero content loss — the rule stays annotate-only, with the single scoped
  exception of deleting a `⚠ Superseded` marker this convention itself wrote.
- Reduces the blast radius of reconcile-issue's starvation (ENH-2992) without
  depending on it.
- **Minor size-score inflation.** Markers add words to `## Implementation
  Steps`, which `cli/issues/size.py` reads via `_SOLUTION_HEADINGS` (line 41)
  for `_section_complexity_signal` (`_SECTION_WORD_THRESHOLD = 300`) and for
  the whole-body `_WORD_COUNT_THRESHOLD = 800` signal. Four markers is roughly
  50 words, so the direction is wrong (annotating *dead* steps nudges an issue
  toward Very Large, feeding autodev's `issue-size-review --auto`
  decomposition gate) while the magnitude is negligible. Accepted, not
  mitigated — flagged so it is not rediscovered as a defect.

## Success Metrics

- A refine pass that emits correction language against a directive line also
  emits a superseded marker on that line (verifiable by re-running refine
  against `ENH-2500` and checking steps 1/3/6/7).
- No marker appears on any preserved section (`## Summary`, `## Motivation`,
  `## Proposed Solution`, `### Option …`).
- **Machine-checkable**: `ll-issues format-check --all --format json` reports
  a non-empty `unmarked_superseded_directive` list for the corpus today
  (expected on the order of the 316 issues measured in § Current Behavior),
  and reports an empty list for any issue refined after this change ships.
  This is the metric that can actually fail; the two above rely on LLM
  judgment.
- Re-running refine against an already-marked issue is a no-op on markers
  whose refutation still holds (idempotency, § Program Design step 5), and
  clears markers whose refutation no longer holds (step 7).

## Scope Boundaries

- Does **not** rewrite, reorder, or delete any directive text — that remains
  `/ll:reconcile-issue`'s job. The one deletion in scope is a `⚠ Superseded`
  marker this convention itself wrote (§ Proposed Solution, marker removal).
- Does **not** change when reconcile is invoked (ENH-2992). Reconcile
  overwrites the marked sections wholesale, so markers simply vanish on a
  reconcile pass; treating a marker as an input signal to reconcile's rewrite
  is a separate follow-up, not this issue.
- Does **not** touch `/ll:wire-issue`'s append behavior (ENH-2996).
- The `unmarked_superseded_directive` gap class is **report-only**. Wiring it
  into a blocking gate (pre-commit, `ll-doctor --full`, or autodev's readiness
  path) is deliberately out of scope until the class has corpus telemetry —
  the same WARN-now/ERROR-later stance MR-14 takes.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `commands/refine-issue.md` | Contains the Preservation Rule being amended |
| `commands/reconcile-issue.md` | Defines the rewrite-eligible / preserve-untouched split this carve-out must respect |

## Confidence Check Notes

**Readiness**: 88/100 — **Outcome Confidence**: 75/100

**Recommendation**: PROCEED

### Resolved
- The initial `/ll:confidence-check` pass hit a Program Design hard override
  (`## Program Design` was missing; the project's gate is armed via
  `.ll/program-design-cutover.json`, stamped 2026-07-30). A `## Program
  Design` section was added with a `### Signatures` entry (the
  `annotate_superseded_directive` decision procedure) and a `### Call Path`
  naming repo-resolvable anchors (`_append_decomposition_note`,
  `check_content_markers`). `ll-issues format-check` now reports
  `program_design_nonspecific: []` — the gate passes.

## Session Log
- `/ll:confidence-check` - 2026-08-02T15:55:04 - `de072167-1f81-49e9-8805-57d11b7bea51.jsonl`
- `/ll:confidence-check` - 2026-08-02T15:35:10 - `54b8b61c-90df-41f1-af64-799342e6500a.jsonl`
- `/ll:wire-issue` - 2026-08-02T15:30:11 - `d27699ab-a72d-4e7f-93a0-ed047b357fc4.jsonl`
- `/ll:refine-issue` - 2026-08-02T15:19:00 - `2be150f8-0636-40af-ae61-86aa9b31676d.jsonl`
- `/ll:capture-issue` - 2026-08-02T13:45:56 - `fac7dff4-61c1-4496-95b8-7bd1993d2971.jsonl`

## Status

- **Status**: open

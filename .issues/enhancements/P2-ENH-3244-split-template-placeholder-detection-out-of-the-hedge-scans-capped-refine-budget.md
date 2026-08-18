---
id: ENH-3244
type: ENH
title: Split template-placeholder detection out of the hedge scan's capped refine
  budget
priority: P2
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T19:14:03Z'
relates_to:
- BUG-3245
- ENH-3238
- ENH-3247
- ENH-3248
blocked_by:
- BUG-3245
- ENH-3247
decision_needed: false
confidence_score: 92
outcome_confidence: 82
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 21
score_change_surface: 18
---

# ENH-3244: Split template-placeholder detection out of the hedge scan's capped refine budget

## Summary

`ll-issues check-open-questions` treats literal template placeholders (`TBD`, `[Major phase 1]`) as
hedge vocabulary, so they share `check_hedge_attempts`' one-refine-per-run cap in
`refine-to-ready-issue.yaml` and get waived on the second red reading. Placeholders have a true-zero
target and are deterministically detectable; prose hedges have a genuine noise floor. They should
not share a budget.

## Current Behavior

The detection works. The waiver is what fails.

`\bTBD\b` is a term in `_OPEN_QUESTION_SIGNAL_RE` (`scripts/little_loops/issue_parser.py:1733`) and
`Integration Map` is in `_OPEN_QUESTION_SECTIONS` (`:1746`), so `ll-issues check-open-questions`
correctly returns exit 1 on an issue still carrying template debris.

Observed on the `refine-to-ready-issue` run over ENH-3238
(`.loops/.history/2026-08-17T183652-refine-to-ready-issue/events.jsonl`, 27 routes):

```
refine_issue → wire_issue → verify_issue → VALID → check_hedges NO → hedge_attempts=1 → refine_followup
             → check_wire_done(=1) → verify_issue → VALID → check_hedges NO → hedge_attempts=2 → PROCEED
             → check_ac_automatable → confidence_check → done
```

`check_hedges` (`refine-to-ready-issue.yaml:301-310`) returned NO on **both** passes. The second red
reading hit `check_hedge_attempts`' cap (`:312-333`, `target: 2`, BUG-3170 — one hedge-forced refine
per run) and routed `on_no` to `check_ac_automatable`, i.e. proceed anyway.

The issue reached the `done` terminal carrying five literal `TBD - requires codebase analysis`
bullets and `1. [Major phase 1] / 2. [Major phase 2] / 3. [Verification approach]`. Downstream
`confidence_check` then scored it 96 readiness / 90 outcome, 25/25 on the ambiguity axis.

### Why the existing `boilerplate` gap class does not catch this

`format-check` already has a `boilerplate` gap class, but it fires only when a **required section's
body equals its `creation_template` in full** (`scripts/little_loops/issue_parser.py:853-856`):

```python
template = section_defs.get(name, {}).get("creation_template", "")
if template and _normalize_whitespace(stripped) == _normalize_whitespace(template):
    gaps.boilerplate.append(name)
```

Any partial fill defeats that whole-body equality test. ENH-3238's `## Integration Map` had
`### Codebase Research Findings` populated with real research while its five sibling subsections
still held `TBD` bullets — so the section body no longer equalled the template, `boilerplate` stayed
silent, and the debris passed. The new check must be **per-placeholder containment**, not
whole-section equality.

## Expected Behavior

An issue cannot reach `done` while its file still contains unfilled template placeholders. That
condition is checked deterministically, outside the hedge scan's capped budget, and reported as a
structural gap rather than as hedge vocabulary.

Prose hedges keep the BUG-3170 cap unchanged.

## Motivation

BUG-3170's cap is justified in-line at `refine-to-ready-issue.yaml:312-317`:

> The scan is an absolute-zero probe over vocabulary with no answer/hedge distinction, so a residual
> count is the steady state for a well-refined issue. One forced refine is worth its cost; a second
> red reading must not spend the shared budget and decompose the issue.

That reasoning is **correct for prose hedges** — "worth confirming", "needs decision", "should be
considered" are ordinary technical English with a genuine noise floor, and demanding zero would
thrash. It is **wrong for literal template placeholders**, which have a true-zero target, no
legitimate residual, and a deterministic fix.

Conflating the two means the noisy signal's justified cap silently waives the clean signal. Every
placeholder in the observed run originated from the shipped template itself (see Current Behavior),
so this is not a rare shape — it is the default state of every freshly created issue, and the gate
that should guarantee it gets filled in is the one being waived.

## Proposed Solution

Split the signal by kind.

1. **Template placeholders become a `format-check` structural gap**, not a hedge term. `ll-issues
   format-check` already exposes deterministic public JSON keys for exactly this style of non-LLM
   routing — `superseded_marker_count` (`issue_parser.superseded_marker_count`) is read by
   `autodev.yaml:1590-1596` to route a gate with no LLM in the chain (MR-1). Add a
   `placeholder_count` (or a `template_placeholders` structural gap) alongside it.

2. **Patterns to detect** — anchored to the literal strings the shipped template emits, so this
   stays a true-zero probe and does not drift into prose matching:
   - `TBD - requires codebase analysis`, `TBD - use grep to find references`,
     `TBD - search for consistency`, `TBD - identify test files to update`,
     `TBD - docs that need updates`, `TBD - requires investigation`
   - `[Major phase 1]`, `[Major phase 2]`, `[Verification approach]`
   - `[P0-P5]`, `[Small/Medium/Large]`, `[Low/Medium/High]`, `[Yes/No]`, `[YYYY-MM-DD]`
   - `[If applicable - describe what currently happens]`, `[What should happen instead]`,
     `[Why this issue matters - ...]`

   **Empty provenance stubs are explicitly NOT on this list.** The
   `_Added by \`/ll:refine-issue\` — <date> — based on codebase analysis:_` stub with no bullet
   following it is **ENH-3247's `empty_provenance_stub` gap class**, not a template placeholder. It
   was on this list in an earlier revision; that was a duplicate detector for the same shape, in the
   same dataclass, in the same file. Ownership is now strict: ENH-3247 owns stub emptiness (a
   line-adjacency check), this issue owns literal template strings (a containment check). See
   Decision Rules › Boundary with ENH-3247.

3. **Remove `\bTBD\b` from `_OPEN_QUESTION_SIGNAL_RE`** (`issue_parser.py:1717`, the `\bTBD\b` term
   itself at `:1733`) once the structural check covers it, so the hedge scan stops double-reporting
   it and its capped budget is spent only on genuine prose hedges. `\bto be determined\b` is prose
   and stays.

4. **No FSM wiring here.** Routing the new signal into `refine-to-ready-issue.yaml` is
   **ENH-3248's** job, not this issue's — see Scope Boundaries. This issue ends at detection plus
   JSON exposure.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

Codebase research surfaced a real ambiguity the issue's own text does not resolve: Implementation
Steps §3 points at the five-touchpoint `FormatGaps` checklist ENH-3247 used, while Program Design §
Signatures points at `superseded_marker_count`'s scalar shape — and those two existing precedents
disagree with each other, not just with the reader.

> **Selected:** Option A — matches the 24-field `FormatGaps` pattern exactly and avoids Option B's semantic mismatch with `superseded_marker_count` (presence-is-neutral vs. this issue's presence-is-always-a-defect model).

**Option A**: Add the new count as a `FormatGaps` dataclass field (`list[str]`), following the
five-touchpoint pattern ENH-3247 used for `empty_provenance_stub`/`duplicate_heading` — field
(`issue_parser.py:513`-style), `has_gaps` OR-clause (`:541`-style), `to_dict()` key (`:569`-style),
`_print_gaps()` loop (`format_check.py:379-380`-style), and a CLI.md enumeration/paragraph. A
residual placeholder then participates in `has_gaps`/exit-code and the normal `--fix` dispatch
surface.

**Option B**: Add it as a scalar out-of-band `--format json` key (`placeholder_count: int`),
mirroring `superseded_marker_count`'s exact shape (`issue_parser.py:1326-1352`, wired at
`format_check.py:566-573`) — deliberately excluded from `FormatGaps`/`has_gaps`, documented as its
own `--format json`-only paragraph.

**Recommended**: Option A. `superseded_marker_count`'s exclusion from `FormatGaps` is justified in
its own code comment by marker *presence* being a neutral/positive signal, not a defect — the
opposite of this issue's own claim that placeholder residue is "always a defect... there is no
legitimate residual" (Decision Rules § Budget). Implementation Steps §3 already names the five
`FormatGaps` touchpoints, and Option A is the only one of the two that lets a placeholder gap block
"Formatted" status and surface through the existing `--fix`/`--apply` machinery the way `boilerplate`
and `empty_provenance_stub` do today.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-17.

**Selected**: Option A — `FormatGaps` dataclass field

**Reasoning**: Two independent codebase-evidence agents confirmed Option A matches the dominant,
actively-used `FormatGaps` shape (24 existing fields, with `duplicate_heading`/`empty_provenance_stub`
as direct structural precedents added by ENH-3247) and its fence-masking dependency
(`text_utils.fence_spans`/`in_fence`) is already a shared, importable utility. Option B is a
mechanically cheaper mirror of `superseded_marker_count`, but that precedent's own exclusion from
`FormatGaps` is justified by marker *presence* being a neutral/positive signal — the opposite of this
issue's stated defect model that placeholder residue is "always a defect... there is no legitimate
residual." Option A is also the only shape that lets a placeholder gap block "Formatted" status and
surface through the existing `--fix`/`--apply` machinery, matching Implementation Steps §3.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| Option B | 1/3 | 3/3 | 3/3 | 2/3 | 9/12 |

**Key evidence**:
- Option A: `duplicate_heading`/`empty_provenance_stub` (`issue_parser.py:512-513`) are structurally
  identical recent precedents; `_print_gaps()`'s docstring (`format_check.py:393-395`) documents a
  completeness contract tying every `FormatGaps` field to a matching print loop.
- Option B: `superseded_marker_count` (`issue_parser.py:1326-1352`) is a clean 2-line-wiring mirror,
  but its sole justification for excluding `FormatGaps` (presence is neutral/positive) directly
  contradicts this issue's own defect model, and it would ship with zero consumers until ENH-3248
  lands.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `_OPEN_QUESTION_SIGNAL_RE` (`:1717`; the `\bTBD\b` term at
  `:1733`) drops `\bTBD\b`; add the placeholder pattern set and a `placeholder_count`-style public
  accessor next to `superseded_marker_count`. **Lands on top of ENH-3247's `FormatGaps` widening** —
  see Decision Rules › Boundary with ENH-3247.
- `scripts/little_loops/cli/issues/format_check.py` — surface the new count as a structural gap and
  in `--format json`. ENH-3247 lands the `--fix` dispatch table here first; this issue adds a
  detection-only class and registers no repair.
- `scripts/little_loops/templates/` — the issue templates that emit these placeholders are the
  authoritative source for the literal pattern list; keep the two in sync.
- **Not** `scripts/little_loops/loops/refine-to-ready-issue.yaml` — no FSM edit in this issue. The
  gate belongs to ENH-3248.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/format_check.py:63-69` — the `argparse` subparser `help=` string
  enumerates gap classes by name (currently ending
  `.../duplicate_heading/empty_provenance_stub)`); append the new field's name. Separate from the
  `_print_gaps()` loop already listed above. [Agent 2 finding]
- `scripts/little_loops/cli/issues/format_check.py:386-391` — `cmd_format_check()`'s own docstring
  carries a second, independent gap-class enumeration ("Gap classes: missing/renamed/.../
  duplicate_heading/empty_provenance_stub."); append the new field's name here too. [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:301-333` — `check_hedges` /
  `check_hedge_attempts`. Removing `TBD` from the hedge vocabulary changes what this pair fires on;
  the BUG-3170 cap on the remaining prose vocabulary is deliberately left intact. **Read-only for
  this issue** — the behavior change here is what the existing gate no longer fires on, not a new
  state.
- `scripts/little_loops/loops/autodev.yaml:1590-1596` — the `superseded_marker_count` precedent this
  change mirrors. Any new key must follow the same "public JSON key read by a shell gate" shape.
- Every consumer of `ll-issues check-open-questions` — the exit-code contract changes meaning
  slightly (fewer true positives, all of them prose).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-remediate.yaml:100-122` — `ensure_formatted` gate calls
  `ll-issues format-check` and routes on its overall exit code. Once the new placeholder gap class
  participates in `has_gaps` (Option A, per Decision Rationale), issues that previously passed this
  gate with residual template debris will now fail it and route to `format_issue` instead — a
  behavior change for this consumer, not an edit target. [Agent 1 finding]

### Similar Patterns
- `superseded_marker_count` — deterministic count on `format-check --format json`, consumed by a
  non-LLM gate. The model for this change.

### Tests
- `scripts/tests/` — a test asserting a freshly created issue (`ll-issues create --variant full`)
  reports a non-zero placeholder count, and that a filled-in issue reports zero. The fresh-template
  case is the strongest fixture because the template ships the placeholders.
- Existing `check-open-questions` tests that assert on `TBD` will need updating when it moves.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser_unresolved.py:334-338` —
  `TestCountOpenQuestionsWidenedSections.test_codebase_research_findings_section_counted` asserts
  `count_open_questions_in_sections(...) == 1` on a fixture ("- TBD whether this path is actually
  hit.") that matches `_OPEN_QUESTION_SIGNAL_RE` **only** via the `\bTBD\b` alternative — no other
  vocabulary in that fixture matches. This is the concrete test that breaks when `\bTBD\b` is
  removed; update its fixture text or expected count. [Agent 3 finding, confirms Proposed
  Solution §3's "update affected tests"]
- `scripts/tests/test_ll_issues_format_check.py:1779-1874` —
  `TestFormatCheckEmptyProvenanceStubFix` is the CLI-level (not just `issue_parser.py` unit-level)
  test-class shape to mirror for the new gap class: detection message assertion, `--fix`
  preview-without-`--apply` behavior, and idempotent-apply behavior if a fixer is ever added.
  [Agent 3 finding]
- `scripts/tests/test_ll_issues_format_check.py:~300-393` (`test_gapped_issue_json_output`) — the
  `to_dict()` JSON-output assertion dict already has `"empty_provenance_stub": []`; add the new
  field's key alongside it. [Agent 3 finding]
- `scripts/tests/test_ll_issues_create.py:93,102` (`variant="full"` issue creation) and `:209-214`
  (`test_unsupplied_variant_sections_keep_placeholder`, asserting placeholder-string presence) —
  the existing fixture patterns to combine for the "fresh issue reports non-zero placeholder count /
  filled-in issue reports zero" test this issue's Tests section calls for. [Agent 3 finding]
- `scripts/tests/test_ll_issues_format_check.py:2275-2297` —
  `test_every_format_gaps_field_is_rendered` is a self-updating completeness-contract test (via
  `dataclasses.fields(FormatGaps)`): no edit needed, but it will fail if the new field is added to
  the dataclass without a matching `_print_gaps()` loop branch — this is the same enforcement the
  `_print_gaps()` docstring at `format_check.py:393-395` describes. [Agent 2/3 finding, FYI only]

### Documentation
- `docs/reference/CLI.md` — `ll-issues format-check` output keys, if enumerated there.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:2051` — the gap-class enumeration prose (currently ending "... and
  `empty_provenance_stub`" with a written count of "twenty-three classes... re-derive this count
  from `dataclasses.fields(FormatGaps)` rather than trusting the number written here"); insert the
  new field name and bump the written count. [Agent 2 finding]
- `docs/reference/CLI.md:2213` — the literal `--format json` example payload (a comma-joined
  dict-literal-shaped string ending `..., "empty_provenance_stub": [...], "superseded_marker_count":
  0`); insert the new key in field order. [Agent 2 finding]
- `docs/reference/API.md:895-916` — carries the same kind of gap-class enumeration, but confirmed
  already stale (lists only 21 names and never picked up ENH-3247's `duplicate_heading` /
  `empty_provenance_stub`); optional/best-effort touch, not a hard requirement enforced by any test.
  [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- **Stale anchors corrected**: `_OPEN_QUESTION_SIGNAL_RE` is now at `issue_parser.py:1870-1892` (the `\bTBD\b` term at `:1886`), not `:1717`/`:1733` as currently cited in Current Behavior/Program Design. `_OPEN_QUESTION_SECTIONS` is now at `:1898-1906`. `superseded_marker_count()` is now at `:1326-1352`, not `:1173` as cited in Program Design § Signatures.
- **Template strings are literal JSON, not procedural**: the placeholder text lives as `creation_template` values in `scripts/little_loops/templates/{enh,bug,feat,epic}-sections.json` — the `TBD -` bullets at `enh-sections.json:80` (mirrored in `bug-sections.json:80`, `feat-sections.json:80`, a shorter variant in `epic-sections.json:39`) and the `[Major phase N]` steps at `enh-sections.json:106` (mirrored in `bug-sections.json:106`, `feat-sections.json:106`). The existing `boilerplate` gap class already reads these same `creation_template` values at runtime (`issue_parser.py:853-856`) — a new detector could derive its literal-string list from `creation_template` instead of a hand-copied list, which would satisfy Proposed Solution §2's "keep the two in sync" by construction rather than by discipline.
- **Inline single-backtick masking already exists as a precedent** — independently defined (not shared) in three files: `scripts/little_loops/issues/symbol_claims.py:98`, `scripts/little_loops/issues/cli_claims.py:19`, and `scripts/little_loops/issues/prose_deps.py:42` (`_BACKTICK_SPAN_RE = re.compile(r"`([^`\n]+)`")`, cross-referenced across all three by comment). `prose_deps.py:110` shows the masking-mode usage relevant here: its match spans are appended into the same `fence_spans` list built from triple-backtick fences, then `_in_fence()` is reused unmodified. No shared `text_utils.py` helper exists for this yet — each site defines its own copy.
- **Test pattern to mirror**: `TestSupersededMarkerCount` (`scripts/tests/test_issue_parser.py:4571-4655`) — 6-case shape: zero-when-absent, single positive, multi-section coverage, out-of-scope negative, multiple-hits-in-one-section, missing-file fail-open. `TestDuplicateHeadingDetection`/`TestEmptyProvenanceStubDetection` (`:4711-4767`, `:4770-4805`) add a `test_*_inside_fence_is_invisible` case that neither `TestSupersededMarkerCount` nor either of those two test for inline-backtick exclusion — a new placeholder-detector test class needs that case added, since it would be novel to this detector.
- **Documentation touchpoints depend on the FormatGaps-field-vs-scalar-key choice** (see Proposed Solution § Codebase Research Findings): a `FormatGaps` field gets an inline enumeration mention (`docs/reference/CLI.md:2051`) or a dedicated "Also reports X" paragraph (`:2144-2161`, `:2173-2182`); an out-of-band `--format json`-only key gets its own "additionally carries X" paragraph (`:2163-2171`, the `superseded_marker_count` precedent).

## Implementation Steps

1. Confirm ENH-3247 has landed (`FormatGaps` widening + `--fix` dispatch table); this issue's gap
   class is added alongside its two, not in a competing edit.
2. Add the placeholder pattern set and public count accessor in `issue_parser.py`, next to
   `superseded_marker_count`.
3. Surface it from `ll-issues format-check` as a structural gap and in `--format json` (field,
   `has_gaps` clause, `to_dict` key, docstring table, `_print_gaps` loop — the five touchpoints
   ENH-3247 enumerates).
4. Remove `\bTBD\b` from `_OPEN_QUESTION_SIGNAL_RE`; update affected tests.
5. Add tests per the Tests section, including the fresh-template fixture.
6. `python -m pytest scripts/tests/` exits 0.

No FSM edit. The gate that consumes this signal is ENH-3248's.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/issues/format_check.py:63-69` — append the new field's name to
  the `argparse` subparser `help=` gap-class enumeration.
- Update `scripts/little_loops/cli/issues/format_check.py:386-391` — append the new field's name to
  `cmd_format_check()`'s own docstring enumeration (separate from the `_print_gaps()` loop).
- Update `docs/reference/CLI.md:2051` — insert the new field name into the enumeration prose and
  bump the written class count.
- Update `docs/reference/CLI.md:2213` — insert the new key into the `--format json` example payload.
- Update `scripts/tests/test_issue_parser_unresolved.py:334-338` — fix or retarget the fixture that
  relies solely on the `\bTBD\b` alternative, which will break once it's removed.
- Update `scripts/tests/test_ll_issues_format_check.py:~300-393` — add the new key to the
  `to_dict()` JSON-output assertion dict.
- Add a CLI-level test class mirroring `TestFormatCheckEmptyProvenanceStubFix`
  (`scripts/tests/test_ll_issues_format_check.py:1779-1874`) for the new gap class.
- Build the fresh-issue placeholder-count fixture from `scripts/tests/test_ll_issues_create.py:93,
  102,209-214`'s existing `variant="full"` creation + placeholder-presence-assertion patterns.
- Be aware (no required edit): `scripts/little_loops/loops/rn-remediate.yaml:100-122`'s
  `ensure_formatted` gate will start failing on issues with residual placeholder debris that
  previously passed, once the new gap class participates in `has_gaps`.

## Program Design

### Call Path

`check_open_questions` -> `superseded_marker_count` -> `cmd_format_check`

- `_OPEN_QUESTION_SIGNAL_RE` (`scripts/little_loops/issue_parser.py:1733`) currently carries
  `\bTBD\b`; `_OPEN_QUESTION_SECTIONS` (`:1746`) scopes the scan to seven sections including
  `Integration Map`. Together these make `ll-issues check-open-questions` exit 1 on template debris.
- `superseded_marker_count` (`scripts/little_loops/issue_parser.py`) is the shape to copy: a
  deterministic public count exposed on `ll-issues format-check --format json`.
- `cmd_format_check` (`scripts/little_loops/cli/issues/format_check.py`) surfaces structural gaps and
  the JSON payload the new count joins.
- `autodev.yaml:1590-1596` consumes `superseded_marker_count` from a shell gate with no LLM in the
  routing chain (MR-1) — the precedent for how the new count gets wired.

### Decision Rules

- **Signal kind**: literal-string containment, not vocabulary matching. The pattern set is anchored
  to the exact strings `scripts/little_loops/templates/` emits, so the probe stays true-zero.
- **Budget**: uncapped. A placeholder is always a defect; there is no legitimate residual, so the
  BUG-3170 cap reasoning does not apply.
- **Boundary with the hedge scan**: prose hedges (`worth confirming`, `needs decision`,
  `to be determined`) stay in `_OPEN_QUESTION_SIGNAL_RE` under the existing cap. Only `\bTBD\b`
  moves.
- **Boundary with ENH-3247 (ownership, not sequencing)**: ENH-3247 owns `empty_provenance_stub` — a
  line-adjacency check ("is there a bullet between this stub and the next heading?") built on
  `_paragraph_spans`. This issue owns `template_placeholders` — a literal-string containment check
  against the strings `scripts/little_loops/templates/` emits. An earlier revision of this issue
  claimed the stub shape too; that was a second detector for one defect in one dataclass in one
  file. Neither issue re-implements the other's detector, and neither reports the other's shape.
- **Boundary with ENH-3248 (detection vs. routing)**: this issue produces a signal; ENH-3248 consumes
  it. Both would otherwise edit `refine-to-ready-issue.yaml` in the same sprint wave — ENH-3248
  restructures that file's routing, adds two states, and recomputes `max_steps`, so a second
  concurrent gate insertion is a merge collision with no upside. Detection without routing is
  independently useful: `format-check` reports it and `--format json` exposes it.
- **Masking must cover inline code, not just fences.** Reuse ENH-3247's
  `fence_spans()`/`in_fence()` masking, but it is **not sufficient on its own** for this detector.
  **This issue's own file is the counter-example**: Proposed Solution § 2 enumerates every literal
  pattern as `` `TBD - requires codebase analysis` ``-style *inline* code spans, not inside a
  ```` ``` ```` fence — so a fence-only mask leaves ~15 false positives on this very file, and
  ENH-3247's `boilerplate`/`empty_provenance_stub` precedent does not solve it (neither of those
  shapes occurs in inline code). Options, to decide during implementation:
  1. Add inline-code-span masking alongside fence masking (a backtick-pair scan). Preferred —
     smallest rule, symmetric with the fence decision, and inline code means "this is a literal I am
     naming" everywhere in the corpus.
  2. Scope the detector to the sections the template actually emits placeholders into
     (`Integration Map`, `Implementation Steps`, `Impact`, `Motivation`), which excludes a
     `Proposed Solution` enumeration but not a `## Impact` discussion of one.
  Whichever is chosen, **this file must be a fixture asserting zero placeholders** — it is the
  natural adversarial case and it exists already.

### Signatures
- `superseded_marker_count(issue_path: Path) -> int` — the existing deterministic public accessor at
  `scripts/little_loops/issue_parser.py:1173` whose shape and JSON exposure the new count mirrors.
- `placeholder_count(issue_path: Path) -> int` — proposed new sibling accessor returning the number
  of unfilled template placeholders found in the issue file.

## Impact

- **Priority**: P2 - Silently lets template debris reach `done` and be scored 96/90. Not P1: the
  damage is a degraded issue file, not broken released behavior, and a human reviewing the issue
  catches it.
- **Effort**: Small - a pattern set, a public accessor, one gate, tests. Mirrors an existing
  precedent end to end.
- **Risk**: Low - the patterns are literal strings from the shipped template, so false positives are
  near-impossible. The one real risk is an uncapped gate looping when the repair pass cannot fix the
  placeholder; see Scope Boundaries.
- **Breaking Change**: No

## Scope Boundaries

**Detection only — no FSM routing.** The observed run's cap spent its one retry on `refine_followup`,
which runs `/ll:refine-issue --auto --gap-analysis` — additive-only by contract
(`refine-to-ready-issue.yaml:177-181`, "Gap-analysis is additive-only (never removes content)"). A
placeholder needs *deleting*, so the only repair mode that loop can invoke today is structurally
incapable of clearing what triggered it. Trigger and remedy are mismatched.

Choosing the remedy — deterministic normalize, `/ll:reconcile-issue`, or refine — is exactly
**ENH-3248's** subject, and ENH-3248 answers it: normalize → reconcile → refine, cheapest-first,
each rung bounded by a per-run counter. This issue therefore ships **no gate at all**. Wiring one
here would (a) duplicate ENH-3248's routing decision, and (b) collide with ENH-3248's edits to the
same YAML in the same sprint wave.

**Empty provenance stubs belong to ENH-3247.** See Decision Rules › Boundary with ENH-3247. This
issue detects literal template strings only.

**Not widening prose-hedge detection.** BUG-3170's cap on genuine prose hedges is correct and stays.

## Related Issues

- ENH-3247 — **hard prerequisite.** Lands the `FormatGaps` widening and `--fix` dispatch table this
  issue's gap class is added alongside, and **owns `empty_provenance_stub`** (previously claimed by
  this issue's pattern list — now ceded).
- ENH-3248 — **owns the FSM gate that consumes this signal.** This issue is detection-only precisely
  so the two do not both edit `refine-to-ready-issue.yaml`.
- BUG-3245 — produces the empty `_Added by_` provenance stubs; detection of those is ENH-3247's, and
  stopping their creation is BUG-3245's. This issue touches neither.
- ENH-3238 — the issue whose refine run surfaced this; the same run also passed two substantive
  errors that no gate in the loop could see.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-17 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-17_

**Readiness Score**: 75/100 → STOP — ADDRESS GAPS (hard override)
**Outcome Confidence**: 79/100 → MODERATE

### Concerns
- ~~Both `blocked_by` dependencies (BUG-3245, ENH-3247) are still `open`, not `done`/`cancelled`.~~
  **Resolved as of this pass (2026-08-17)**: both are now `done`, and code inspection confirms
  `empty_provenance_stub` exists in `issue_parser.py`'s `FormatGaps` (`:513`), so ENH-3247's widening
  Implementation Steps §1 waits on has landed.

### Gaps to Address
- ~~Resolve or land BUG-3245 and ENH-3247 before implementing this issue.~~ Resolved — both are
  `done`.
- Decision Rules § "Masking must cover inline code, not just fences" leaves the inline-vs-section-scope
  masking approach explicitly undecided ("Options, to decide during implementation") — pick one before
  or during implementation to avoid false positives on the issue's own fixture file.

### Outcome Risk Factors
- None beyond the open masking-strategy decision noted above; the pattern otherwise mirrors the
  existing `superseded_marker_count` precedent closely (mechanical, well-scoped, test plan specified).

## Session Log
- `/ll:confidence-check` - 2026-08-18T01:40:06 - `b1fcbc27-6cc0-4f61-afba-f89fc37a602f.jsonl`
- `/ll:wire-issue` - 2026-08-18T01:33:31 - `707dea9b-b70a-4464-bf06-ca7b4497f26c.jsonl`
- `/ll:decide-issue` - 2026-08-17T23:24:03 - `33a38c46-fd9e-408d-980c-20585c294776.jsonl`
- `/ll:refine-issue` - 2026-08-17T23:15:34 - `bbbe7744-e9dc-4cca-8051-3fce993a1ce7.jsonl`
- `/ll:confidence-check` - 2026-08-17T21:33:51 - `878d0e98-a6e4-41e7-80a9-53a56e3db6f7.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-17T20:25:54 - `fe71c380-6bd8-44e2-9c73-d0617456c6e4.jsonl`
- `/ll:capture-issue` - 2026-08-17T19:29:37 - `3ce34465-00fd-4ba7-a470-b61774849ebd.jsonl`
- `/ll:capture-issue` - 2026-08-17T19:16:20 - `33a98a0f-5403-4525-92db-f7737c5401c4.jsonl`

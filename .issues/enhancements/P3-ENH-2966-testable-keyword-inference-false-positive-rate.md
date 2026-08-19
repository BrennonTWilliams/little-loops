---
id: ENH-2966
title: '`testable` keyword inference fires on 62% of active issues'
type: ENH
priority: P3
status: open
captured_at: '2026-08-01T16:02:14Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- ENH-2946
testable: true
decision_needed: false
labels:
- issues
- cli
verify_verdict: VALID
confidence_score: 98
outcome_confidence: 80
score_complexity: 21
score_test_coverage: 23
score_ambiguity: 20
score_change_surface: 21
---

# ENH-2966: `testable` keyword inference fires on 62% of active issues

## Summary

`check_format_gaps`'s `testable` advisory flags an issue as
documentation-only when 2+ distinct signal keywords appear anywhere in its
title or body. In this repo — whose subject matter *is* documentation, skills,
and doc tooling — that fires on **80 of 125 active issues (64%)**. An advisory
that fires on the majority of the corpus carries no information.

## Current Behavior

`issue_parser.py`:

- `_TESTABLE_SIGNAL_KEYWORDS` (`L1828-1840`): `doc`, `docs`, `documentation`,
  `broken link`, `broken anchor`, `readme`, `changelog`, `spelling`, `typo`,
  `guide`, `fix link`.
- `_TESTABLE_KEYWORD_THRESHOLD = 2` (`L1841`) — 2+ *distinct* matches.
- `_count_testable_keyword_matches` (`L1844-1847`) — plain **substring**
  containment (`kw in text.lower()`), not word-boundary matching.
- `check_format_gaps` (`L992-1001`) scans `title + strip_frontmatter(content)`
  — the **entire issue body** — and appends a `testable` gap when no explicit
  `testable:` key is present.
- `infer_testable` (`L1850-1862`) applies the same rule over the same surface
  as a separate entry point.

Measured on the current backlog (2026-08-19): **80 of 125 active issues** trip
it. 33 active issues carry an explicit `testable:` key and are exempt by
construction.

The rule is behaving exactly as specified. The specification is the problem,
and the failure is **structural, not prose drift**. Because matching is bare
substring containment and `doc` is a substring of several ordinary words:

- The single word **`documentation` scores 2 on its own** (`doc` +
  `documentation`) — one occurrence of one word reaches the threshold.
- Any reference to a file under the repo's `docs/guides` directory scores 3
  (`doc` + `docs` + `guide`) from the path fragment alone.
- **`## Related Key Documentation` — a heading in the standard issue template —
  scores 2 by itself.** Every template-conformant issue without an explicit
  `testable:` key therefore fires *by construction*: **48 of the 125 active
  issues are guaranteed fires from that heading alone**, independent of
  anything the issue is actually about.

Secondary contributors:

- The scan covers the whole body, so any issue that *discusses* documentation
  in its Integration Map, Scope Boundaries, or Documentation section matches —
  regardless of whether the work itself is doc-only.
- Bare `doc`/`guide` are extremely common in a repo with `docs/guides/`,
  `LOOPS_GUIDE.md`, and `HARNESS_OPTIMIZATION_GUIDE.md`.

Concrete false positive: ENH-2946 (a pure CLI-implementation issue) began
tripping the advisory only after prose about *documentation drift* was added
to its body. The issue's testability did not change.

The advisory also **fails the gate**: `testable` is included in
`FormatGaps.has_gaps` (`L518-531`), so an advisory-only signal produces the
same non-zero `format-check` exit as a real structural gap.

## Expected Behavior

The advisory fires rarely enough that it is worth reading — it should identify
issues that are genuinely documentation-only, not issues that mention
documentation.

## Motivation

A gap class that fires on 62% of the corpus is indistinguishable from noise,
and the cost is not neutral:

- It trains readers to ignore `format-check` output, which also carries the
  ten real structural gap classes.
- The remedy the message suggests (`set an explicit testable:` key) makes the
  advisory disappear without anyone verifying the issue is actually testable —
  so the rule pushes toward reflexive frontmatter stamping rather than
  judgment.
- Every false positive is a non-zero exit from `format-check`, which is a
  gate other tooling consumes.

## Proposed Solution

### Measured fire counts (2026-08-19, 125 active issues)

Each option simulated against the live backlog before choosing:

| Option | Rule | Fires |
|---|---|---|
| *(current)* | whole body, 11 keywords, ≥2 | **80** |
| **A** | title + `## Summary`, 11 keywords, ≥2 | **9** |
| **B** | whole body, 8 keywords, ≥2 | **14** |
| **A + B** | title + `## Summary`, 8 keywords, ≥2 | **0** |
| **C** | whole body, 11 keywords, ≥3 | **70** |

The target is a single-digit fire count. **A alone hits it exactly (9).
A + B overshoots to zero** — a rule that never fires on a 125-issue corpus is
indistinguishable from a deleted rule, and leaves no live example to
hand-check. C barely moves (80 → 70), confirming that a fixed threshold cannot
survive a self-inflicted structural hit from the template's own heading.

The measurement is cheap to reproduce: `ll-issues format-check --all --format
json`, count non-empty `testable` arrays.

### Options

**A. Narrow the scan surface.** Match against the title and `## Summary` only,
not the whole body. Most genuine doc-only issues announce themselves in the
title ("fix broken link in X", "update CHANGELOG"). This removes the
`## Related Key Documentation` heading and the Integration Map/Scope Boundaries
prose from the scan, which is where the structural false positives originate.

**B. Tighten the keyword list.** Drop bare `doc`/`guide`/`docs` (substrings of
ordinary prose and of each other), keep the high-signal phrases (`broken link`,
`broken anchor`, `fix link`, `typo`, `spelling`, `changelog`, `readme`,
`documentation`). This makes the distinct-match count meaningful, since the
surviving keywords are no longer near-synonyms.

**C. Raise the threshold** from 2 to 3+ distinct matches. Cheapest change, but
measurement shows it only shifts the curve (80 → 70) rather than fixing the
surface problem.

**D. Negative signals.** Suppress when the issue names code artifacts
(`.py` paths, `def `/`class `, a `## Program Design` section with real
signatures). A doc-only issue rarely has a populated Program Design.

**E. Demote `testable` to a non-gating advisory.** Remove it from
`FormatGaps.has_gaps` so it still renders in the report but no longer forces a
non-zero `format-check` exit. This is **orthogonal to precision** and directly
addresses the harm named in Motivation — that every false positive fails a gate
other tooling consumes. It can be adopted alongside any of A–D, or on its own.

**Recommended**: **Option A alone**, plus **Option E**. A hits the single-digit
target on its own; B is held as a follow-up *only if* hand-checking A's 9
survivors shows they are still false positives. E is cheap and fixes the
gate-failure complaint independently of how precise the keyword rule becomes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis. The alternatives
above are restated here in the `**Option X**` heading form the
`check-decidable` probe (`locate_enumerable_options`,
`scripts/little_loops/issue_parser.py`) scans for — the `**A.**`-prefix form
above does not match its heading regex, so it was invisible to the decision
gate despite being a genuine 4-option decision point._

**Option A**: Narrow the scan surface to title + `## Summary` only. Measured:
**9 fires** (from 80). Hits the single-digit target on its own.

> **Selected:** Option A (paired with Option E) — reuses `_section_body`, the
> exact helper `check_format_gaps` already calls for its other gap classes, and
> two other gap classes already implement the identical
> allowlist-of-sections-via-`_section_body` pattern; it is the only option
> measured to hit the single-digit target on its own.

**Option B**: Tighten the keyword list — drop bare `doc`/`docs`/`guide`, keep
`broken link`, `broken anchor`, `fix link`, `typo`, `spelling`, `changelog`,
`readme`, `documentation`. Measured: **14 fires**. Combined with A: **0 fires**
(over-corrects).

**Option C**: Raise the threshold from 2 to 3+ distinct matches. Measured:
**70 fires** — barely moves, because the template's own `## Related Key
Documentation` heading plus one `docs/` path already clears any small fixed
count.

**Option D**: Negative signals. Suppress when the issue names code artifacts
(`.py` paths, `def `/`class `, a `## Program Design` section with real
signatures). A doc-only issue rarely has a populated Program Design. Not
measured — highest effort of the five, and A already meets the target.

**Option E**: Demote `testable` to a non-gating advisory by removing it from
`FormatGaps.has_gaps` (`issue_parser.py:518-531`). Report it, but stop failing
`format-check` on it. Orthogonal to A–D; composable with any of them.

**Recommended**: **Option A + Option E**. A is the minimum change that reaches
the single-digit target; E fixes the gate-failure harm independently. Hold B as
a follow-up contingent on hand-checking A's 9 survivors. Re-measure with
`ll-issues format-check --all --format json` after each step.

### Additional decisions required

**Decision 1 — Option A's fallback when `## Summary` is absent.** 5 active
issues have no `## Summary` section or an empty one (`ENH-3035`, `EPIC-2149`,
`EPIC-2087`, `FEAT-2379`, `FEAT-3036`). Under A the scan silently degrades to
title-only for these. Decide explicitly between:
- **A1** — title-only is fine (a doc-only issue announces itself in the title);
  simplest, and EPICs are never doc-only in practice. *Suggested default.*
- **A2** — fall back to the whole body when `## Summary` is missing, preserving
  today's behavior for those issues.

Whichever is chosen must be pinned by a test; today nothing covers it.

**Decision 2 — delete `infer_testable` rather than keep it in lockstep.**
`infer_testable` (`issue_parser.py:1850-1862`) has **zero production callers** —
a repo-wide search finds only its own tests (`test_issue_parser.py:4098-4136`),
`skills/format-issue/SKILL.md:176` naming it in prose, and
`docs/reference/CLI.md:2069` naming it in prose. The Call Path section below
frets that its two entry points are "kept in sync only by convention"; deleting
the unused one collapses that risk to nothing and removes a second surface to
update. Decide between:
- **D1** — delete `infer_testable` and its tests; `check_format_gaps` becomes
  the single call site. *Suggested default.*
- **D2** — keep it, and change both entry points in lockstep.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — the scan-surface construction in
  `check_format_gaps` (`L992-1001`); `_TESTABLE_SIGNAL_KEYWORDS`
  (`L1828-1840`) and `_TESTABLE_KEYWORD_THRESHOLD` (`L1841`) only if B/C are
  adopted; `_count_testable_keyword_matches` (`L1844-1847`);
  `FormatGaps.has_gaps` (`L518-531`) for Option E; `infer_testable`
  (`L1850-1862`) — deleted under Decision D1.
- `skills/format-issue/SKILL.md:174-188` — the "Testable Inference" section.
  Its prose says the match runs "against title + body" (`L186-187`), which
  Option A makes wrong. It also names `infer_testable` (`L176`), which
  Decision D1 removes.
- `skills/capture-issue/SKILL.md:233-237` — Phase 4 step 2 lists all 11
  keywords and the 2+ threshold and instructs the model to **re-scan** them at
  capture time. Note this already **contradicts** `format-issue/SKILL.md:177`
  ("do not re-scan for keywords here") — a pre-existing inconsistency to
  resolve while here, not just a mechanical keyword-list update.
- `docs/reference/CLI.md:2069-2072` — **third copy of the rule**, documenting
  `infer_testable`'s "signal-keyword tuple, 2+ distinct matches" and the
  advisory's semantics. Was missing from this list. Under Option E its
  "advisory only" wording must also state that it no longer affects exit code.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/format_check.py` — **missing from this
  list entirely**, despite being the CLI implementation that actually reads
  `FormatGaps.has_gaps` to decide the process exit code (`cmd_format_check`,
  calls to `check_format_gaps` at `:566,582,612,626`; `has_gaps` checks at
  `:590,660,662`). Tracing its gating logic surfaces a **contradiction with
  this issue's own Program Design claim** (below, `L360-362`) that "the class
  is still reported, just non-gating" under Option E: that claim is only true
  for single-ID `--format json` (`:647-660`, unconditional `payload =
  dict(gaps.to_dict())`). In **single-ID text mode** (`:662-668`), `if not
  gaps.has_gaps: print("...compliant"); return 0` — `_print_gaps` is only
  called in the `else` branch, so a testable-only issue prints "structurally
  compliant" and the testable line never appears. In **`--all` sweep, both
  formats** (`:590-607`), `if gaps.has_gaps: results[info.issue_id] = gaps`
  drops testable-only issues from `results` before either the text loop or
  the `--all --format json` payload — they vanish from the sweep report and
  sweep JSON, not just the exit code. If the intended UX is "always visible,
  just non-blocking" (as Program Design states), this file's gating logic
  needs a change beyond `has_gaps`, not just the `has_gaps` computation
  itself — otherwise "non-gating" silently becomes "invisible" in two of
  three surfaces.
- `docs/reference/API.md:906` — a **fourth prose copy** of the rule (missed
  by the "three prose copies" count in Scope Boundaries), in the
  `check_format_gaps()` docstring's gap-class table: *"the body trips 2+
  doc-only keyword signals... while frontmatter has no explicit `testable:`
  key."* Says "the body" (whole-body scan) — wrong under Option A, needs the
  same title + `## Summary` correction as the other three copies.

### Dependent Files
- `scripts/tests/test_issue_parser.py:4098-4136` — `TestInferTestable`'s
  true/false unit tests. Under Decision D1 these are deleted with the function;
  under D2 both fixtures need revisiting.
- `scripts/tests/test_ll_issues_format_check.py:2590-2650`
  (`_DOC_ONLY_BODY` / `TestFormatCheckTestableRendering`) — the regression
  anchor. **Verified to survive every option**, including A+B: its title
  ("Fix broken link in the docs guide") and Summary ("The documentation guide
  has a broken link and a typo in the readme") score 4 under the tightened
  keyword list restricted to title + Summary. It must not be weakened.
  Note that under Option E its `assert result == 1` will need to change, since
  `testable` would no longer drive a non-zero exit.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-remediate.yaml:100-121` — the
  `ensure_formatted` state runs `ll-issues format-check "$ID"` with
  `evaluate: type: exit_code`, routing `on_yes: assess` / `on_no:
  format_issue`. Under Option E a testable-only issue currently routes to
  `format_issue` (`/ll:format-issue --auto`) and will instead flow straight to
  `assess` — a real routing-behavior change to this loop, not just a metric
  shift. The state's own comment block already omits `testable` from the gap
  classes it names as gated, so no comment text becomes wrong, but the
  behavior does change silently unless this is verified as intended.
- `skills/confidence-check/SKILL.md:138` — calls `ll-issues format-check
  --format json` and consumes the JSON payload; confirm it does not read
  `has_gaps` directly in a way Option E's change would silently affect.
- `scripts/little_loops/cli/issues/format_check.py:63-70,472-482` — CLI
  `--help` text and `cmd_format_check`'s own docstring both enumerate
  `testable` among the gap classes with no gating/non-gating distinction;
  low risk, but check for staleness after Option E lands.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Correction to the section-extractor lead below**: `ll-issues sections`
  (`cmd_sections` in `scripts/little_loops/cli/issues/sections.py:16-48`) is
  **not** an issue-body section extractor — it prints/resolves the path of a
  static per-type template JSON (`{type}-sections.json`) used when
  *scaffolding a new issue*. It never reads an existing issue's markdown body.
  Following this reference would cost the implementer a dead-end.
- **The actual reusable helper** is `_section_body_with_offset(content,
  heading)` / `_section_body(content, heading)`
  (`scripts/little_loops/issue_parser.py:199-223`) — locates a `^## {heading}$`
  line and returns text up to the next `^## ` line. `check_format_gaps`
  already calls this (`body = _section_body(content, name)`) for its
  `empty`/`boilerplate`/`program_design_nonspecific` gap checks, so
  `_section_body(content, "Summary")` is the same-pattern call to reuse for
  Option A — no new regex, no new module. **Confirmed 2026-08-19**: the
  Option A / A+B fire counts in Proposed Solution were measured using exactly
  this helper, so the numbers reflect the real implementation, not an
  approximation. It returns `""` for a missing heading — hence Decision 1.
- Two other section-splitting implementations exist elsewhere in the codebase
  (`issue_history/doc_synthesis.py:104-127`'s `_extract_section`, and
  `issue_parser.py:662-677`'s `_iter_h2_sections` for multi-section
  enumeration) but neither is what `check_format_gaps` itself already uses —
  `_section_body` is the one already in the same call path.
- **Pre-existing scope discrepancy** (independent of this issue, but relevant
  context): both `skills/format-issue/SKILL.md:174-176` and
  `skills/capture-issue/SKILL.md:261-263` already describe the scan surface
  as "title + description text," not "title + entire body" — the Python
  implementation (`scan_text = f"{title}\n{_strip_fm(content)}"`,
  `issue_parser.py:496`) already scans more than either skill's prose
  documents. The skills and the code disagree *today*, before any fix here.
- **Test coverage gap**: neither `test_issue_parser.py:3950-3989`
  (`TestInferTestable`) nor `test_ll_issues_format_check.py`'s `_DOC_ONLY_BODY`
  fixture (lines 960-991) places any keyword hits outside the title/`##
  Summary` — every existing assertion passes unchanged whether the scan
  surface is the whole body or just title+Summary. Applying Option A alone
  would not fail any current test, but no current test would catch a
  regression in the narrowing either; a new case (keyword hits only in a
  later section like Impact/Steps to Reproduce, with title+Summary
  keyword-free) is needed to actually pin the Option A behavior change.
- For Option D (negative signals), no `_has_code_signals`-shaped helper
  exists anywhere in the codebase today. The closest prior art `check_format_gaps`
  already imports from a sibling module for a similar purpose is
  `program_design.py`'s `grade_issue_section`/`DesignVerdict` (wired in at
  `issue_parser.py:446-451` for the `program_design_nonspecific` gap) and
  `text_utils.py:14-90`'s `extract_file_paths` (path detection, not `def
  `/`class ` keyword detection) — Option D would compose from these, not
  start from scratch.

_Wiring pass added by `/ll:wire-issue`:_
- **A test not previously flagged will break silently under Option E**:
  `scripts/tests/test_issue_parser.py:4139-4196`
  (`TestCheckFormatGapsTestablePopulation`, distinct from `TestInferTestable`)
  — `test_doc_only_issue_reports_testable_gap` (`:4148-4163`) asserts
  `gaps.has_gaps is True` for a fixture whose only gap is `testable`. That
  assertion fails once `testable` is dropped from `has_gaps`; the sibling
  `issue_file.name in gaps.testable` assertion still passes unchanged.
- `scripts/tests/test_issue_parser_properties.py` and
  `scripts/tests/test_issue_parser_unresolved.py` — flagged as possibly
  exercising testable inference or the whole-body scan surface; check for
  assertions that assume today's behavior before/after Option A.
- `scripts/tests/test_builtin_loops.py:1835-1858,7178-7187` — validate loop
  states (`normalize_structure`, `check_reconcile_needed`) that consume
  `format-check`'s exit code / JSON output; confirm neither depends on
  `testable`'s current contribution to `has_gaps`.
- **Concrete pattern precedent for Implementation Steps 6-7's new regression
  tests** (not previously cited): two established section-scoping test
  shapes already exist and should be followed rather than inventing a new
  one — `TestStaleSymbolRefScoping`
  (`scripts/tests/test_feat3048_symbol_cli_claim_gaps.py:229-284`, uses a
  `_write_scoped_issue`/`_SCOPE_TEMPLATE` helper, one test method per
  section, including a negative control in an arbitrary unlisted heading to
  prove allowlist-not-denylist semantics) and
  `TestMissingBehaviorParity.test_no_gap_outside_scope_sections`
  (`scripts/tests/test_ll_issues_format_check.py:1018-1038`, string-replace
  on a `_CLEAN_BUG_BODY` constant, CLI-integration level). Both already use
  `_section_body` as the shared primitive — the same helper this issue plans
  to reuse for `testable`.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-19.

**Selected**: Option A — Narrow the scan surface to title + `## Summary` only (paired with the orthogonal Option E — demote `testable` from `has_gaps`).

**Reasoning**: Option A is the only option that meets the issue's own stated single-digit fire-count target on its own (80 → 9 of 125), and it does so by reusing `_section_body` (`issue_parser.py:199-223`) — the exact helper `check_format_gaps` already calls for its other gap classes, and the identical pattern two other gap classes (`missing_behavior_parity`, `stale_symbol_ref`) already implement as a section-name allowlist. Option B (14 fires alone, 0 combined with A) and Option C (70 fires) both leave the structural false-positive source — the template's own `## Related Key Documentation` heading — largely intact, since neither narrows the scan surface that heading lives in. Option D has no existing lightweight helper matching its required flat-text signature and is unmeasured against the backlog. Option E is orthogonal and composable with A; codebase evidence shows it is a small, self-contained `has_gaps` change with no conflicting precedent, so it is adopted alongside A per the issue's own recommendation rather than scored as a competing alternative.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — Narrow scan surface | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |
| B — Tighten keyword list | 3/3 | 3/3 | 3/3 | 0/3 | 9/12 |
| C — Raise threshold | 2/3 | 3/3 | 2/3 | 0/3 | 7/12 |
| D — Negative signals | 1/3 | 0/3 | 1/3 | 0/3 | 2/12 |
| E — Demote to non-gating | 2/3 | 3/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- A: `_section_body` reuse score 3/3 — two existing gap classes (`_behavior_parity_scope_text`, `_symbol_claim_scope_text`) already implement the identical section-allowlist pattern; measured 9/125 fires, hitting the target.
- B: pure data-tuple edit (reuse score 3/3), but alone undershoots the target (14/125) and combined with A over-corrects to 0/125 — held as a contingent follow-up, not primary.
- C: cheapest mechanical edit but the issue's own simulation shows it barely moves the fire rate (80→70/125) because the false positives are structural to the scan surface, not the threshold.
- D: no existing `_has_code_signals`-shaped helper; the closest prior art (`grade_program_design`) requires a git-grep resolver a flat-text signature can't supply — highest effort, unmeasured.
- E: no existing gating/non-gating split inside `FormatGaps` to copy, but the change is a single self-contained `has_gaps` edit with a clear existing test to update (`TestFormatCheckTestableRendering`).

## Program Design

### Types

**No new types.** This is a tuning change to two module-level constants and
one scan-surface expression; introducing a dataclass for it would be
over-structure.

### Signatures

`_count_testable_keyword_matches(text: str) -> int` (`issue_parser.py:1844`)
keeps its shape. What changes is what it is fed:

- The scan-surface expression in `check_format_gaps` (`L992-1001`) — currently
  `f"{title}\n{_strip_fm(content)}"`. Under Option A this becomes title +
  `## Summary` body only, reusing `_section_body` (see Research Findings). The
  no-`## Summary` fallback is Decision 1 above.
- `_TESTABLE_SIGNAL_KEYWORDS: tuple[str, ...]` — unchanged under the
  recommendation; under Option B drop bare `doc`, `docs`, `guide`.
- `FormatGaps.has_gaps` (`L518-531`) — under Option E, drop the `or
  self.testable` term. `to_dict` (`L561`) and the `_print_gaps` rendering loop
  stay as-is, so the class is still reported, just non-gating.

`infer_testable(issue: IssueInfo) -> bool` is **deleted** under Decision D1.

If Option D (negative signals) is adopted, add
`_has_code_signals(text: str) -> bool` alongside the existing counter and
require `count >= threshold and not _has_code_signals(...)`.

### Call Path

Under Decision D1 there is a **single** call path:
`check_format_gaps` → `_count_testable_keyword_matches` → `gaps.testable`,
and (Option E) `gaps.testable` no longer feeds `has_gaps` → exit code.

Under D2 the second entry point `infer_testable` → same counter survives, and
both call sites must see the same rule — they are kept in sync only by
convention, which is the reason D1 is the suggested default.

## Implementation Steps

1. Baseline: record the current fire count
   (`ll-issues format-check --all --format json`, count non-empty `testable`).
   Expected: 80 of 125 active issues.
2. Resolve Decision 1 (no-`## Summary` fallback) and Decision 2
   (`infer_testable` deletion) before writing code.
3. Apply Option A — narrow the scan surface to title + `## Summary`, reusing
   `_section_body`. Re-measure; expect **9**.
4. Hand-check those 9 survivors — every remaining hit should be an issue a
   human agrees is doc-only. **Only if they are still false positives**, apply
   Option B and re-measure (expect 14 → but note A+B measures 0, so B must be
   applied *instead of* A, not on top of it, if the goal is a non-empty
   result).
5. Apply Option E — remove `testable` from `has_gaps`; update the
   `TestFormatCheckTestableRendering` exit-code assertion accordingly.
6. Add the missing regression test: keyword hits placed **only** in a later
   section (e.g. Impact or Steps to Reproduce) with a keyword-free title and
   `## Summary` must **not** fire. Without this, Option A's narrowing is
   untested (see Research Findings).
7. Add a test pinning the Decision 1 fallback (issue with no `## Summary`).
8. Update `format-issue/SKILL.md`, `capture-issue/SKILL.md`, and
   `docs/reference/CLI.md` in lockstep — including resolving the pre-existing
   re-scan contradiction between the two skills.
9. Confirm `_DOC_ONLY_BODY` still trips.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Decide and implement how `scripts/little_loops/cli/issues/format_check.py`
  should surface a testable-only issue under Option E: today, dropping
  `testable` from `has_gaps` makes it vanish entirely from single-ID text
  mode and from `--all` sweep (both formats) — not just the exit code — which
  contradicts this issue's own "still reported, just non-gating" Program
  Design claim. Only single-ID `--format json` currently keeps it visible.
- Update `docs/reference/API.md:906` — a fourth prose copy of the rule,
  saying "the body" where Option A requires title + `## Summary`.
- Verify `scripts/little_loops/loops/rn-remediate.yaml`'s `ensure_formatted`
  gate (`:100-121`) — confirm that a testable-only issue no longer routing to
  `format_issue` (routing straight to `assess` instead) is the intended
  outcome of Option E, or adjust the gate.
- Update `scripts/tests/test_issue_parser.py:4148-4163`
  (`test_doc_only_issue_reports_testable_gap`) — its `has_gaps is True`
  assertion breaks under Option E; update while keeping the `testable`
  list-membership assertion.
- Check `skills/confidence-check/SKILL.md`,
  `scripts/tests/test_issue_parser_properties.py`, and
  `scripts/tests/test_issue_parser_unresolved.py` for assumptions tied to
  today's testable behavior.
- Follow `TestStaleSymbolRefScoping`
  (`scripts/tests/test_feat3048_symbol_cli_claim_gaps.py:229-284`) or
  `TestMissingBehaviorParity.test_no_gap_outside_scope_sections`
  (`scripts/tests/test_ll_issues_format_check.py:1018-1038`) as the pattern
  for the new section-scoping regression tests in steps 6-7, rather than a
  novel shape.

## Scope Boundaries

**In scope:**
- The keyword list, threshold, and scan surface for the `testable` inference.
- Whether `testable` contributes to `format-check`'s exit code (Option E).
- Deleting the unused `infer_testable` entry point (Decision 2).
- Keeping `check_format_gaps` consistent with the **three** prose copies of the
  rule (`format-issue/SKILL.md`, `capture-issue/SKILL.md`,
  `docs/reference/CLI.md`), including the pre-existing re-scan contradiction
  between the two skills.

**Out of scope:**
- The `testable` frontmatter field's *semantics* (`False` skips TDD, `None`
  treated as testable) — unchanged.
- Whether `testable` should be a `format-check` gap class at all — it should;
  this is about precision and gating, not existence. Option E demotes it to
  non-gating; it does not remove it.
- Introducing word-boundary/regex matching in place of substring containment.
  Narrowing the surface (A) is sufficient to hit the target; a matcher rewrite
  is a larger change with its own regression surface.
- Other `format-check` gap classes.
- ENH-2946's outstanding work (`set-flags`, `format-check --next`, skill
  slimming).

## Impact

- **Priority**: P3 — noise, not breakage. The advisory is correct-by-spec and
  nothing downstream misbehaves; it just wastes attention and erodes trust in
  `format-check`'s output.
- **Effort**: Small — a keyword list, a threshold, and a scan-surface change,
  with a cheap measurable target.
- **Risk**: Low — but note the rule is duplicated in two SKILL.md files, so a
  change that misses those leaves the CLI and the skills disagreeing. That
  duplication is itself the kind of prose-reimplementation
  `ll-verify-skill-prose` (ENH-2951) exists to catch.
- **Breaking Change**: No — advisory only.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

_Added by `/ll:verify-issues`:_ Core behavior and premise still accurate —
`_TESTABLE_SIGNAL_KEYWORDS`, `_TESTABLE_KEYWORD_THRESHOLD = 2`,
`_count_testable_keyword_matches`, and the whole-body scan surface
(`scan_text = f"{title}\n{_strip_fm(content)}"`) all still match verbatim.
Line-number citations are stale: the constants and functions now live around
`issue_parser.py:550-716`, not the originally cited `L489-528`.

**2026-08-19** (pre-implementation review): Premise re-verified against live
code and re-measured against the backlog. Changes made:

- Fire count restated 36/58 (62%) → **80/125 (64%)**; all line citations
  refreshed (constants `1828-1847`, scan surface `992-1001`, `infer_testable`
  `1850-1862`, `has_gaps` `518-531`, tests `4098-4136` and `2590-2650`).
- Root cause restated as **structural, not prose drift**: substring matching
  makes the single word `documentation` score 2, and the standard template's
  own `## Related Key Documentation` heading score 2 — **48 of 125 active
  issues fire from that heading alone**.
- All four options simulated. **The previously recommended A+B yields 0 fires**
  — over-corrects into a dead rule. Recommendation changed to **A alone (9
  fires)**, with B held as a contingent follow-up.
- Added **Option E** (demote `testable` out of `has_gaps` so it stops failing
  the gate) — Motivation named this harm but no option addressed it.
- Added **Decision 1** (Option A's fallback for the 5 active issues with no
  `## Summary`) and **Decision 2** (`infer_testable` has **zero production
  callers**; delete rather than maintain in lockstep).
- Added `docs/reference/CLI.md:2069-2072` as a third prose copy of the rule,
  missing from Files to Modify; flagged the pre-existing contradiction where
  `capture-issue/SKILL.md` tells the model to re-scan keywords while
  `format-issue/SKILL.md` says not to.
- Confirmed `_DOC_ONLY_BODY` survives every option (scores 4 under A+B), so the
  regression anchor holds regardless of choice.

**2026-08-10** (`/ll:verify-issues`): Verified 2026-08-10: logic unchanged
(`_TESTABLE_SIGNAL_KEYWORDS`, `_TESTABLE_KEYWORD_THRESHOLD = 2` confirmed
verbatim in issue_parser.py), but cited line numbers have drifted again — code
is now around lines 976-1010, not the ~550-716 previously noted. Cosmetic
only; core claim and fix options remain accurate.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and ENH-3000 both modify `check_format_gaps` in `scripts/little_loops/issue_parser.py` for unrelated gap classes (testable-keyword scan surface vs. a new `stale_file_ref` verdict branch). Coordinate implementation order to avoid a merge collision in the same function.

**Resolved 2026-08-19**: the ENH-3247 collision note previously here is stale —
ENH-3247 is `done`, so there is no longer an ordering constraint against it.
The ENH-3000 note above still stands (ENH-3000 is `open`).

## Session Log
- `/ll:confidence-check` - 2026-08-19T19:57:26 - `bd3f0a41-ce07-4c04-acd5-8a401b968303.jsonl`
- `/ll:wire-issue` - 2026-08-19T19:54:38 - `bd3f0a41-ce07-4c04-acd5-8a401b968303.jsonl`
- `/ll:decide-issue` - 2026-08-19T18:53:08 - `e7d6e805-7841-446d-b324-acab354e3e8f.jsonl`
- `/ll:confidence-check` - 2026-08-19T18:46:55 - `16de750d-d4f0-4fa9-ba37-ac3244bf63ce.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-17T20:25:55 - `fe71c380-6bd8-44e2-9c73-d0617456c6e4.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:26:27 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:45 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`
- `/ll:verify-issues` - 2026-08-03T04:54:47 - `d03f8e53-9873-4f8d-8cfd-bbc50704a66b.jsonl`
- `/ll:refine-issue` - 2026-08-01T19:58:05 - `f7d70fe6-d3b1-4443-814c-32eee6e8b043.jsonl`
- `/ll:capture-issue` - 2026-08-01T16:04:25 - `f9ef973a-acd3-40a7-a313-5e7a001f9a16.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P3

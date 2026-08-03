---
id: ENH-2999
status: open
priority: P3
captured_at: '2026-08-02T14:05:00Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to:
- ENH-2983
- ENH-2971
- ENH-2946
- ENH-3000
testable: true
confidence_score: 100
outcome_confidence: 77
score_complexity: 14
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 18
---

# `stale_file_ref` reports ambiguous multi-match references as drift

## Summary

`classify_file_ref()` returns `stale` for a reference that suffix-matches more
than one tracked file. Declining to resolve is correct — a silent pick would be
worse — but `stale` tells the reader the file moved or vanished, when the truth
is "this path matches two real files; disambiguate the reference." Wrong verdict
class for a correct decision. **44 instances** across `.issues/`.

> **Count corrected 2026-08-02** (pre-implementation review). The original
> capture said 86; that was measured *before* the mirror tie-break landed. Fresh
> measurement against the current tree: **44 ambiguous, 3,294 true stale** (3,338
> `stale_file_ref` findings total). Reproduce with the snippet under
> Implementation Steps § 3.

## Current Behavior

`scripts/little_loops/text_utils.py` — `resolve_ref_path()` returns `None` for
both "no match" and "more than one match", and `classify_file_ref()` collapses
both into `stale`:

```python
matches = [p for p in candidates if p.endswith(suffix)]
if len(matches) == 1:
    return matches[0]
non_mirror = [p for p in matches if not p.startswith(_mirror_prefixes())]
return non_mirror[0] if len(non_mirror) == 1 else None   # 0 matches and 3 matches
                                                          # are indistinguishable here
```

Worked examples from the corpus:

| Reference | Matches | Reported |
|---|---|---|
| `issues/anchor_sweep.py` | `scripts/little_loops/cli/issues/anchor_sweep.py`, `scripts/little_loops/issues/anchor_sweep.py` | `stale` |
| `agents/openai.yaml` | 66 tracked `skills/*/agents/openai.yaml` files | `stale` |

The docstring already documents the *decision* ("ambiguous matches must not
silently resolve") — this issue is about the *label*, not the resolution policy.

Note the mirror tie-break added alongside this issue's capture handles the
specific case where the ambiguity is a generated host-adapter copy
(`.codex/`, `.gemini/`, `.kimi-code/`) shadowing its source. The 44 above are
the residue: genuine same-name ambiguity between two real source paths.

## Expected Behavior

An ambiguous reference is reported as its own thing, with the candidate paths
named so the reader can disambiguate:

```
  ambiguous_file_ref: issues/anchor_sweep.py (matches 2: scripts/little_loops/cli/issues/…, scripts/little_loops/issues/…)
```

`stale_file_ref` then means what it says: a `/`-qualified path matching nothing.

## Motivation

The two conditions call for opposite fixes. `stale` says "find where this moved
or delete the reference"; ambiguous says "add the missing path prefix." Reporting
both under one label sends the reader after the wrong fix.

The volume argument is weak and should not be leaned on: 44 of 3,338 findings is
1.3% of the pile. The case for this change is correctness of the verdict, not
noise reduction — a reader who acts on an `ambiguous` finding as if it were
`stale` will go looking for a file that never moved.

## Proposed Solution

Add `ambiguous` to `RefStatus` (`text_utils.py:111`) and return it when the
suffix-match set has more than one member after the mirror tie-break.

Three consumers must be updated in the same change — this is why it is not a
narrow fix:

1. **`issue_parser.check_format_gaps()`** (`issue_parser.py:547`) — decide
   whether `ambiguous` gets its own `FormatGaps` field (recommended: it is
   separately actionable) or folds into `stale_file_ref`'s list with a
   distinguishing suffix.
2. **`cli/issues/format_check.py:154`** — print the candidate paths, not just
   the ref. The count is the actionable part.
3. **`issues/research_triage.py:193` and `:388-391`** — both hardcode
   `in ("resolved", "stale")`. **Decided (pre-implementation review): `ambiguous`
   joins the tuple in both places.** Rationale: today an ambiguous ref classifies
   `stale` and therefore *is* denominator-eligible. Leaving the tuples untouched
   would silently shift ENH-2971's ≥80% axis-coverage fractions as a side effect
   of a labelling change. Including it is the behavior-preserving choice, and it
   is also the substantively right one — the author cited a real file. Do not
   re-litigate this during implementation; update both tuples.

## Program Design

The resolution *policy* is unchanged. The classifier needs to distinguish "no
match" from "many matches", and the CLI needs the candidate paths to print — but
neither requires widening `resolve_ref_path`'s return type.

> **Design revised 2026-08-02 (pre-implementation review).** The original
> proposal added a frozen `RefResolution` dataclass plus a new `resolve_ref()`,
> keeping `resolve_ref_path` as a thin wrapper. The Codebase Research Findings
> below establish that shape has **no precedent here**, and that the nearest
> analogue (`subprocess_utils.py:43-54`) deliberately *avoided* widening a
> return type for this exact reason. The shape below gets the same result with
> one shared helper and no signature change — dropping the "novel shape" risk
> and the churn on dependent tests that assert `resolve_ref_path(...) is None`.

### Signatures

```python
RefStatus = Literal["resolved", "stale", "unresolvable_form", "planned_new", "ambiguous"]

def suffix_match_candidates(ref: str, index: RefIndex) -> list[str]:
    """Candidates for *ref* after the existing tie-break order.

    0 = absent, 1 = resolves, >1 = ambiguous.
    """

def resolve_ref_path(ref: str, index: RefIndex) -> str | None: ...   # signature UNCHANGED
```

`suffix_match_candidates` holds the shared body (exact-match short-circuit,
suffix match, mirror tie-break). Both existing functions call it:

> **Contract correction (pre-implementation review, 2026-08-02).** The helper is
> **not** "the non-mirror suffix matches" — describing it that way silently
> regresses mirror-only refs. Today's `resolve_ref_path` returns a lone match
> *before* consulting `_mirror_prefixes()`, so a ref whose only match is a
> generated mirror resolves to that mirror:
>
> ```
> agents/codebase-analyzer.toml → .codex/agents/codebase-analyzer.toml   # resolves today
> ```
>
> There are six such refs under `.codex/agents/` alone. The helper must
> reproduce today's order exactly, in this sequence:
>
> 1. `ref in candidates` → return `[ref]` (exact match wins even when other
>    suffix matches exist, so an exactly-cited path never reports `ambiguous`)
> 2. `matches = [p for p in candidates if p.endswith("/" + ref)]`
> 3. `len(matches) == 1` → return `matches` — **before** any mirror filtering
> 4. otherwise return `[p for p in matches if not p.startswith(_mirror_prefixes())]`
>
> Only step 4 filters. Any implementation that filters earlier changes
> resolution policy, which this issue explicitly does not do.
>
> **Edge case decided here so implementation does not have to:** when
> `len(matches) > 1` and *every* match is a mirror, step 4 yields an empty list
> → `stale`, matching today's `None` → `stale` exactly. It is not reported as
> `ambiguous`. Pin this with a test; nothing else distinguishes it from the
> zero-match path.

- `resolve_ref_path` returns the single element when there is exactly one, else
  `None` — **identical behavior and signature to today**, so ENH-2971's call
  sites and the existing `is None` assertions are untouched.
- `classify_file_ref` branches on the length: `1` → `resolved`, `>1` →
  `ambiguous`, `0` → `stale`.

The candidate list reaches the CLI through the `FormatGaps` entry string rather
than a new rendering concept — every `FormatGaps` field is already `list[str]`
and `_print_gaps` already renders one line per entry:

```
  ambiguous_file_ref: issues/anchor_sweep.py (2: scripts/little_loops/cli/issues/anchor_sweep.py, scripts/little_loops/issues/anchor_sweep.py)
```

**Truncation is required, not optional** _(pre-implementation review)_. The
worst real case in the corpus is `agents/openai.yaml` with **66** candidates;
rendering all of them puts a multi-kilobyte line in `format-check` output. The
entry string is capped at the count plus the first three paths:

```
  ambiguous_file_ref: agents/openai.yaml (66: skills/align-issues/agents/openai.yaml, skills/audit-docs/agents/openai.yaml, skills/capture-issue/agents/openai.yaml, …)
```

The count is the actionable part and is always shown in full; the elision marker
appears only when candidates exceed three. Candidates are sorted for
determinism. Because `FormatGaps` fields are `list[str]` of prose entries, the
`--format json` payload carries this same truncated string — the full candidate
list is not exposed as structured data, and no consumer needs it.

`check_format_gaps` calls `suffix_match_candidates()` only for the refs that came
back `ambiguous` — a handful per issue, against an already-built index, so no
measurable cost.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Exact current anchors confirmed: `RefStatus` Literal at `text_utils.py:111`
  (currently `Literal["resolved", "stale", "unresolvable_form", "planned_new"]`,
  no `ambiguous` member yet); `_mirror_prefixes()` at `text_utils.py:130-146`;
  `resolve_ref_path()` at `text_utils.py:255-283`; `classify_file_ref()` at
  `text_utils.py:201-252`, with the collapsing line at `text_utils.py:252`:
  `return "resolved" if resolve_ref_path(ref, index) is not None else "stale"`.
- No `assert_never`/exhaustiveness-check convention exists anywhere near
  `RefStatus` — every consumer tests membership in a subset it cares about
  (`== "stale"`, `in ("resolved", "stale")`) rather than matching all members.
  Adding `ambiguous` will not trip a compiler/lint completeness check; each of
  the three consumers must be updated by hand, and nothing else will catch a
  missed one besides the tests already named in Integration Map.
- No prior instance in this codebase widens a plain `str | None` return into a
  frozen dataclass while keeping the old function as a thin wrapper (the exact
  shape proposed here). The nearest analogues disagree with each other:
  `cli/adapt_skills_for_codex.py:47-56`'s "thin wrapper" delegates
  *implementation* without changing the return type, while
  `subprocess_utils.py:43-54` explicitly avoids widening a return type at all
  (uses a mutable-closure callback instead, citing avoiding-widening as the
  reason in-code). Neither is a precedent to copy; this is a novel shape in
  this codebase, not an established pattern being followed.

### Call Path

`classify_issue_refs` → `classify_file_ref` → `suffix_match_candidates` (new;
holds the existing suffix-match + mirror tie-break body), then out to the
consumers:

- `check_format_gaps` → `_print_gaps` — gains an `ambiguous_file_ref` bucket in
  `FormatGaps` and prints the candidates
- `qualified_ref_count` **and** `_triage_axis` — both gain `"ambiguous"` in the
  eligibility tuple (decided above)
- `resolve_ref_path` — reimplemented on top of the helper, signature and
  behavior unchanged

## Integration Map

### Sequencing: ENH-2993 has landed — no longer a blocker

_Added by pre-implementation review 2026-08-02; **updated 2026-08-02 (second
review): ENH-2993 is committed and `status: done`.** The earlier note said it was
uncommitted in the working tree; that is no longer true and the rebase-first
instruction is dropped._

ENH-2993 (`duplicate_findings_block` / `ll-issues fold-findings`) touched every
consumer site this issue touches. It is now on `main`, so implement directly.
What it leaves behind for this issue:

- `FormatGaps` has **14** fields on `main` (verified via
  `dataclasses.fields(FormatGaps)`), not the 13 recorded in the Codebase
  Research Findings below. After this change it is 15.
- All three gap-class CSVs already carry `duplicate_findings_block`; append the
  new class after it in each, keeping the existing order.
- Re-derive any doc that states a class count from
  `dataclasses.fields(FormatGaps)`; do not trust counts written in this file.

### Files to Modify

- `scripts/little_loops/text_utils.py` — `RefStatus` (:111), new
  `suffix_match_candidates`, `resolve_ref_path` (:255) reimplemented on it,
  `classify_file_ref` (:252) branch, and the numbered resolution-order docstring
- `scripts/little_loops/issue_parser.py` — `FormatGaps` field (:255 area),
  `has_gaps` (:274), `to_dict()` (:293), docstring paragraph (:371), population
  (:547)
- `scripts/little_loops/cli/issues/format_check.py` — **three** sites, not one:
  the `_print_gaps` loop (:154), the subparser `help=` gap-class CSV (:59-64),
  and `cmd_format_check`'s docstring gap-class list (:163-166)
  _(the latter two found by pre-implementation review)_
- `scripts/little_loops/issues/research_triage.py` — **both** hardcoded
  eligibility tuples: `qualified_ref_count` (:193) and `_triage_axis` (:388-391)
- ~~`.claude/CLAUDE.md` § CLI Tools~~ — **not a real edit site (second review,
  2026-08-02).** `.claude/CLAUDE.md` has no `## CLI Tools` section and no
  `format-check` gap-class list anywhere in it; `grep -n 'format-check\|gap
  class\|CLI Tools' .claude/CLAUDE.md` returns nothing. Do not go looking for it.
  The gap-class enumerations live only in `docs/reference/CLI.md:1853`,
  `docs/reference/API.md:862`, and the three code CSVs below
- `scripts/little_loops/cli/issues/__init__.py:124` — the top-level `format-check`
  subcommand's one-line `argparse` help string hardcodes the full gap-class list
  as a parenthesized CSV (`missing/renamed/.../stale_file_ref/...`); needs the
  new class name appended _(found by `/ll:wire-issue`)_

### Dependent Files

- `scripts/tests/test_text_utils.py` — `test_ambiguous_suffix_match_does_not_resolve`
  deliberately asserts the loose `!= "resolved"`, so it stays green; tighten it
  to assert `== "ambiguous"` as part of this change
- `scripts/tests/test_ll_issues_format_check.py`
  - `TestFormatCheckJsonOutput::test_clean_issue_json_output` (line 302, dict
    literal lines 326-343) pins the exact JSON key set and needs the new
    field's key added if `FormatGaps` gains one _(found by `/ll:wire-issue`)_
  - `qualified_ref_count()` has no fast unit test today — its only exerciser is
    the corpus-gated, skip-under-100 `test_locator_coverage_is_length_neutral`
    in `test_research_triage.py` (line 522); add a small hand-built-`RefIndex`
    unit test isolating the denominator-membership decision so it doesn't
    depend on corpus size _(found by `/ll:wire-issue`)_

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `RefStatus`/`classify_file_ref`/`classify_issue_refs`
  are documented at length beyond `.claude/CLAUDE.md`: the `Literal[...]`
  reproduction (~line 7073-7076), `classify_file_ref`'s `**Returns:**` bullet
  enumerating the four (soon five) values (~line 7098-7111),
  `classify_issue_refs`'s return-type reference (~line 7113-7125), a
  return-value table row (~line 7027), and `check_format_gaps`'s "twelve gap
  classes" prose plus its `stale_file_ref` bullet (~line 862, 874) — the count
  is already stale pre-existing this issue and both need updating in the same
  pass. _(Review 2026-08-02: it is not only the count. The `API.md:862`
  enumeration and the `CLI.md:1853` enumeration both **omit**
  `unmarked_superseded_directive` and — once ENH-2993 lands —
  `duplicate_findings_block`. Re-derive both lists from
  `dataclasses.fields(FormatGaps)` rather than incrementing "twelve".)_ Add a short entry for the new
  `suffix_match_candidates` to the `text_utils` function table (~line 7026-7028).
- `docs/reference/CLI.md` — the `#### ll-issues format-check` section: the same
  "twelve classes" prose (~line 1811), a `stale_file_ref`-specific paragraph
  describing "no exact or unique suffix match" that conflates the two failure
  modes this issue splits apart (~line 1862), and a worked `--format json`
  example payload that lists every `FormatGaps` key in order (**line 1914**, not
  1864 — corrected second review) — a new key must be inserted into that example
  if `ambiguous` becomes its own field.
- `docs/reference/CLI.md:1660` _(found by pre-implementation review)_ — the
  **research-triage** section's prose on which classes are "excluded from both
  sides of the fraction". _Second review 2026-08-02: this edit is
  **clarifying, not required**. The sentence is phrased by exclusion ("globs,
  `<placeholder>` paths and bare basenames come back `unresolvable_form` and are
  excluded") and stays literally true once `ambiguous` joins the eligibility
  tuples. Add "and `ambiguous`" to the inclusion side only if it reads clearer;
  do not treat a miss here as a defect._

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- A second test in the same file was missing from the Dependent Files list
  above: `test_text_utils.py::TestMirrorTieBreak::test_genuine_non_mirror_ambiguity_still_declines`
  (line 300) asserts `resolve_ref_path(...) is None` and
  `classify_file_ref(...) != "resolved"` (lines 310-311) for the exact
  `anchor_sweep.py` two-file collision this issue cites — same loose-assertion
  style as the other test, same tightening needed, and its `is None` check
  will also need updating to whatever sentinel `resolve_ref_path` returns once
  the return type widens.

  _Superseded by the revised Program Design (2026-08-02): `resolve_ref_path`
  keeps its `str | None` signature, so both `is None` assertions stay valid
  as-is. Only the loose `!= "resolved"` assertions need tightening to
  `== "ambiguous"`._
- `scripts/tests/test_research_triage.py` was entirely absent from Dependent
  Files but is corpus-gated (skips under 100 issues) and sensitive to the
  research-triage denominator decision above:
  `TestLengthNeutrality.test_locator_coverage_is_length_neutral` (line 522,
  the only production-adjacent exerciser of `qualified_ref_count()`) and
  `test_full_predicate_is_not_inert` (line 496, exercises
  `triage_research_axes()` → `_triage_axis()` end-to-end against the real
  `.issues/` corpus).
- `qualified_ref_count()` (`research_triage.py:171-195`) is **not** the only
  place the `("resolved", "stale")` tuple is hardcoded — `_triage_axis()`
  (`research_triage.py:388-391`, the function that actually computes the
  coverage fraction gating ENH-2971's ≥80% axis-coverage threshold)
  independently duplicates the identical two-member tuple rather than calling
  `qualified_ref_count()`. Both must be updated in the same change or the
  denominator decision silently only takes effect in one of the two places.
  Neither tuple is a named constant; there is no test asserting the two stay
  in sync with each other.
- `FormatGaps` (`issue_parser.py:236-293`) has 13 fields today; each existing
  field follows one repeated shape enforced by a structural test:
  `has_gaps` OR-clause (line 258-275), `to_dict()` entry (line 277-293), a
  docstring paragraph naming the originating issue (e.g. `stale_file_ref`
  at line 368-376, added ENH-2983), and a matching print loop in
  `cli/issues/format_check.py::_print_gaps` (line 132-157). A new field
  without a matching print loop fails
  `test_ll_issues_format_check.py::test_every_format_gaps_field_is_rendered`
  (line 1416) — the guard this codebase already relies on instead of an
  exhaustiveness check on the `Literal` itself. `test_clean_issue_json_output`
  (line 302, dict literal lines 326-343) separately pins the exact JSON key
  set and will need a new key if a field is added.

### Conventions in Force

- `resolve_ref_path()` is the single resolution path shared by `format-check`
  and `research-triage` — evidence: its docstring states the two must not drift.
  Any new status must be introduced there, not branched per consumer.
- No `RefStatus` member is handled via exhaustive matching anywhere in this
  codebase — every consumer (`classify_file_ref`, `check_format_gaps`,
  `qualified_ref_count`, `_triage_axis`) tests membership in a hand-picked
  subset (`==`/`in` against string literals), with no lint/test enforcing that
  all `Literal` members are covered somewhere. The only completeness guard in
  this area protects `FormatGaps` fields specifically
  (`test_every_format_gaps_field_is_rendered`), not the `RefStatus` type.

## Implementation Steps

1. Extract `suffix_match_candidates(ref, index) -> list[str]` from
   `resolve_ref_path`'s body; reimplement `resolve_ref_path` on it with an
   unchanged signature. `RefStatus` gains `ambiguous`; `classify_file_ref`
   branches on the candidate-list length.
2. Each consumer handles the new member explicitly — no silent fall-through to
   an `else` branch. That means all five sites: `FormatGaps` +
   `check_format_gaps`, the three `format_check.py` sites, and **both**
   `research_triage.py` eligibility tuples.
3. Corpus re-measurement shows **44** findings moving `stale` → `ambiguous`,
   3,294 remaining `stale`, and no ref changing `resolved` → anything else.
   Baseline measured 2026-08-02 with:

   ```python
   from pathlib import Path
   from little_loops.text_utils import build_ref_index, classify_issue_refs
   idx = build_ref_index(Path("."))
   amb = stale = 0
   for p in Path(".issues").rglob("*.md"):
       for ref, st in classify_issue_refs(p.read_text(errors="replace"), idx).items():
           if st != "stale":
               continue
           base = ref.rsplit("/", 1)[-1]
           n = len([x for x in idx.by_basename.get(base, []) if x.endswith("/" + ref)])
           amb, stale = (amb + 1, stale) if n > 1 else (amb, stale + 1)
   print(amb, stale)   # 44 3294 at capture time
   ```

   The corpus grows, so treat the exact numbers as a same-day baseline: the
   invariant that must hold is `ambiguous + stale == the pre-change
   stale_file_ref total`, measured immediately before and after.
4. `python -m pytest scripts/tests/` passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update **all three** hardcoded gap-class CSVs — `cli/issues/__init__.py:124`
  (top-level subcommand help), `cli/issues/format_check.py:59-64` (the
  subparser's own `help=`), and `cli/issues/format_check.py:163-166`
  (`cmd_format_check`'s docstring). The latter two were missed by the original
  wiring pass and found by pre-implementation review; nothing tests any of them,
  so a miss is silent.
- Update `docs/reference/API.md` — fix the stale "twelve gap classes" count,
  update `RefStatus`/`classify_file_ref`/`classify_issue_refs` return-value
  documentation, add a table entry for `suffix_match_candidates`
- Update `docs/reference/CLI.md` — fix the stale "twelve classes" count, split
  the `stale_file_ref` paragraph, update the worked `--format json` example
  payload to include the new key, **and** update the research-triage
  denominator prose at line 1660
- Add a unit test for `qualified_ref_count()`'s `"ambiguous"` handling that
  doesn't depend on the corpus-gated (skip-under-100) test, plus one asserting
  `_triage_axis()` counts `ambiguous` the same way — the two tuples are
  duplicated with nothing keeping them in sync
- Add the new field's key to `test_clean_issue_json_output`'s pinned dict
  literal in `test_ll_issues_format_check.py`
- Ruled out (checked, no change needed): `autodev.yaml` and `rn-remediate.yaml`
  call `ll-issues format-check --format json` but only parse
  `program_design_nonspecific`/`missing`/`empty`/`superseded_marker_count` —
  not `stale_file_ref` — so they are unaffected by this change

## Acceptance Criteria

_Added by pre-implementation review 2026-08-02._

- [ ] `classify_file_ref("issues/anchor_sweep.py", index) == "ambiguous"` — the
      two-real-source-path collision, currently `stale`
- [ ] `resolve_ref_path("issues/anchor_sweep.py", index) is None` still holds —
      the resolution policy is unchanged and the signature did not widen
- [ ] `classify_file_ref("scripts/little_loops/session_store.py", index) ==
      "stale"` — a genuinely absent path is unaffected
- [ ] `classify_file_ref("confidence-check/SKILL.md", index) == "resolved"` —
      the mirror tie-break still wins before ambiguity is declared
- [ ] **No mirror-only regression.**
      `resolve_ref_path("agents/codebase-analyzer.toml", index) ==
      ".codex/agents/codebase-analyzer.toml"` and `classify_file_ref(...) ==
      "resolved"` — a ref whose single match is a generated mirror resolves to
      it, exactly as today. This is the failure mode a naively "non-mirror"
      helper introduces; see the Contract correction in Program Design
- [ ] A ref whose matches are >1 and *all* mirrors classifies `stale`, not
      `ambiguous` — behavior-identical to today's `None`
- [ ] The `ambiguous_file_ref` entry for `agents/openai.yaml` renders a count
      **equal to `len(suffix_match_candidates(...))` measured against the live
      index** (66 on 2026-08-02) followed by at most three candidate paths and a
      `…`; the two-candidate `issues/anchor_sweep.py` entry renders both paths
      with no elision marker. _Second review: do not hardcode 66 in a test — a
      skill added or removed under `skills/*/agents/` changes it. Assert the
      rendered count against a freshly computed `len()`, and assert the
      `>3 → elide`, `≤3 → no marker` rule directly on a hand-built `RefIndex`._
- [ ] **`_triage_axis` is behavior-preserving.** For every issue in the corpus,
      `triage_research_axes()`'s `covered` verdict and coverage fraction are
      identical before and after the change — `ambiguous` moves from the `stale`
      bucket to its own name but stays denominator-eligible and stays out of the
      numerator (`research_triage.py:389-393` only appends to `resolved` when
      `status == "resolved"`). Verify by diffing triage output across the whole
      `.issues/` tree pre/post, not just by reading the tuple change
- [ ] **This issue file is its own fixture.** `ll-issues format-check ENH-2999`
      today reports exactly two gaps, both mislabelled:
      ```
      stale_file_ref: agents/openai.yaml
      stale_file_ref: issues/anchor_sweep.py
      ```
      After the change it must report zero `stale_file_ref` and two
      `ambiguous_file_ref`, with candidate counts **66** and **2** rendered in
      the output.
- [ ] `test_every_format_gaps_field_is_rendered` passes with the new field —
      i.e. `_print_gaps` gained its loop
- [ ] Corpus invariant: `ambiguous + stale` after the change equals the
      `stale_file_ref` total measured immediately before it (44 / 3,294 / 3,338
      on 2026-08-02)
- [ ] `python -m pytest scripts/tests/` exits 0

## Impact

- **Effort**: Small-Medium — the classifier change is a few lines; the cost is
  five consumer sites (`FormatGaps`, three `format_check.py` CSVs/loops, and
  both `research_triage.py` tuples) plus the doc sweep. The research-triage
  denominator question is now decided, not open.
- **Risk**: Low — additive status; the resolution policy does not change.
- **Breaking Change**: `RefStatus` is a public `Literal`. Any external consumer
  exhaustively matching it would need the new member, though there are none in
  this repo outside the three listed. _Consumer inventory confirmed exhaustive
  (second review, 2026-08-02): grepping `classify_file_ref|classify_issue_refs|
  resolve_ref_path|RefStatus` across `scripts/little_loops/`, `hooks/`, `loops/`,
  `commands/`, `skills/`, and `.claude/` returns exactly `issue_parser.py:545`,
  `research_triage.py:193`, and `research_triage.py:387-392` outside
  `text_utils.py` itself. There is no fourth site. `stale_file_ref` likewise
  appears in no loop YAML, skill, or hook._

## Scope Boundaries

- **In scope**: the verdict label and its propagation to every consumer site.
- **Out of scope**: changing *whether* ambiguous refs resolve. Declining is
  correct and stays.
- **Out of scope**: untracked-by-design directories reporting `stale` — that is
  a separate root cause tracked as ENH-3000 (open).

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/text_utils.py` | The classifier and its resolution-order contract |
| `docs/reference/CLI.md` | `#### ll-issues format-check` (:1853) enumerates every gap class; `--format json` example at :1914 |
| `docs/reference/API.md` | `check_format_gaps` gap-class prose (:862) and the `RefStatus` / `classify_file_ref` contract (:7073-7125) |

## Session Log
- `/ll:ready-issue` - 2026-08-03T02:55:30 - `98d80e04-349e-4ecb-960b-c2ce2d90ca46.jsonl`
- `/ll:confidence-check` - 2026-08-03T00:59:15 - `e098c4d0-bc23-4ca4-9927-7ae454650ec7.jsonl`
- `/ll:confidence-check` - 2026-08-03T00:44:15 - `8195d557-878b-450d-98ab-271852b83e7a.jsonl`
- `/ll:wire-issue` - 2026-08-03T00:37:25 - `ee2cf08a-9d4e-4629-b2ec-7211d56b5a4e.jsonl`
- `/ll:refine-issue` - 2026-08-03T00:26:30 - `879a3201-ecea-4313-99de-95ce49087308.jsonl`
- `/ll:capture-issue` - 2026-08-02

## Status

- **Status**: open

---
id: ENH-2999
status: open
priority: P3
captured_at: "2026-08-02T14:05:00Z"
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to: [ENH-2983, ENH-2971, ENH-2946]
testable: true
---

# `stale_file_ref` reports ambiguous multi-match references as drift

## Summary

`classify_file_ref()` returns `stale` for a reference that suffix-matches more
than one tracked file. Declining to resolve is correct — a silent pick would be
worse — but `stale` tells the reader the file moved or vanished, when the truth
is "this path matches two real files; disambiguate the reference." Wrong verdict
class for a correct decision. **86 instances** across `.issues/`.

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
(`.codex/`, `.gemini/`, `.kimi-code/`) shadowing its source. The 86 above are
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
both under one label sends the reader after the wrong fix, and — because 86 of
them sit inside a 3,331-finding pile — makes the pile marginally less trustworthy
in a way that discourages acting on any of it.

## Proposed Solution

Add `ambiguous` to `RefStatus` (`text_utils.py:111`) and return it when the
suffix-match set has more than one member after the mirror tie-break.

Three consumers must be updated in the same change — this is why it is not a
narrow fix:

1. **`issue_parser.check_format_gaps()`** (`issue_parser.py:528`) — decide
   whether `ambiguous` gets its own `FormatGaps` field (recommended: it is
   separately actionable) or folds into `stale_file_ref`'s list with a
   distinguishing suffix.
2. **`cli/issues/format_check.py:154`** — print the candidate paths, not just
   the ref. The count is the actionable part.
3. **`issues/research_triage.py:186`** — `qualified_ref_count()` gates on
   `in ("resolved", "stale")`. Decide deliberately whether an ambiguous ref
   counts toward ENH-2971's ≥80% axis-coverage denominator. It probably should
   (the author did cite a real file), but leaving the tuple untouched silently
   drops it.

## Program Design

The resolution *policy* is unchanged; only the return channel widens so callers
can tell the two failure modes apart. `resolve_ref_path` currently returns
`str | None`, collapsing "no match" and "many matches" into `None`.

### Signatures

```python
RefStatus = Literal["resolved", "stale", "unresolvable_form", "planned_new", "ambiguous"]

@dataclass(frozen=True)
class RefResolution:
    path: str | None = None            # the single resolved path, else None
    candidates: tuple[str, ...] = ()   # >1 when ambiguous, empty when absent

def resolve_ref(ref: str, index: RefIndex) -> RefResolution: ...
def resolve_ref_path(ref: str, index: RefIndex) -> str | None: ...  # kept as a wrapper
```

`classify_file_ref` maps the resolution: `path` set → `resolved`; `candidates`
non-empty → `ambiguous`; both empty → `stale`. The candidate list is what makes
the report actionable, so it must survive to the CLI rather than being reduced
to a boolean at the classifier boundary.

`resolve_ref_path` stays as a thin wrapper returning `resolution.path` — ENH-2971's
call sites want the target path, not the ambiguity detail, and keeping it spares
them a change.

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

`classify_issue_refs` → `classify_file_ref` → `resolve_ref` (new; wraps the
existing suffix-match body), then out to the two consumers:

- `check_format_gaps` → `main_format_check` — gains an `ambiguous` bucket in
  `FormatGaps` and prints the candidates
- `qualified_ref_count` — decide explicitly whether `ambiguous` joins
  `resolved`/`stale` in the coverage denominator

## Integration Map

### Files to Modify

- `scripts/little_loops/text_utils.py` — `RefStatus`, `resolve_ref_path`,
  `classify_file_ref`, and the numbered resolution-order docstring
- `scripts/little_loops/issue_parser.py` — `FormatGaps` field + population
- `scripts/little_loops/cli/issues/format_check.py` — reporting
- `scripts/little_loops/issues/research_triage.py` — denominator membership
- `.claude/CLAUDE.md` § CLI Tools — the `format-check` gap-class list enumerates
  every class by name and would go stale
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
  is already stale pre-existing this issue (13 fields today) and both need
  updating in the same pass. No dedicated section exists yet for the new
  `resolve_ref`/`RefResolution` — one should be added, not just edited.
- `docs/reference/CLI.md` — the `#### ll-issues format-check` section: the same
  "twelve classes" prose (~line 1811), a `stale_file_ref`-specific paragraph
  describing "no exact or unique suffix match" that conflates the two failure
  modes this issue splits apart (~line 1820-1828), and a worked `--format json`
  example payload that lists every `FormatGaps` key in order (~line 1864) — a
  new key must be inserted into that example if `ambiguous` becomes its own
  field.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- A second test in the same file was missing from the Dependent Files list
  above: `test_text_utils.py::TestMirrorTieBreak::test_genuine_non_mirror_ambiguity_still_declines`
  (line 300) asserts `resolve_ref_path(...) is None` and
  `classify_file_ref(...) != "resolved"` (lines 310-311) for the exact
  `anchor_sweep.py` two-file collision this issue cites — same loose-assertion
  style as the other test, same tightening needed, and its `is None` check
  will also need updating to whatever sentinel `resolve_ref_path` (or its
  `RefResolution` wrapper) returns once the return type widens.
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

1. `RefStatus` gains `ambiguous`; `resolve_ref_path` distinguishes the zero-match
   and many-match cases (returning the candidates, or a sentinel, rather than a
   bare `None`).
2. Each of the three consumers handles the new member explicitly — no silent
   fall-through to an `else` branch.
3. Corpus re-measurement shows ~86 findings moving `stale` → `ambiguous` and no
   ref changing `resolved` → anything else.
4. `python -m pytest scripts/tests/` passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `cli/issues/__init__.py:124` — append the new gap-class name to the
  `format-check` subcommand's hardcoded help-string CSV
- Update `docs/reference/API.md` — fix the stale "twelve gap classes" count,
  update `RefStatus`/`classify_file_ref`/`classify_issue_refs` return-value
  documentation, add a section for `resolve_ref`/`RefResolution`
- Update `docs/reference/CLI.md` — fix the stale "twelve classes" count, split
  the `stale_file_ref` paragraph, update the worked `--format json` example
  payload to include the new key
- Add a unit test for `qualified_ref_count()`'s `"ambiguous"` handling that
  doesn't depend on the corpus-gated (skip-under-100) test
- Add the new field's key to `test_clean_issue_json_output`'s pinned dict
  literal in `test_ll_issues_format_check.py`
- Ruled out (checked, no change needed): `autodev.yaml` and `rn-remediate.yaml`
  call `ll-issues format-check --format json` but only parse
  `program_design_nonspecific`/`missing`/`empty`/`superseded_marker_count` —
  not `stale_file_ref` — so they are unaffected by this change

## Impact

- **Effort**: Small-Medium — the classifier change is a few lines; the cost is
  the three consumers and deciding the research-triage denominator question.
- **Risk**: Low — additive status; the resolution policy does not change.
- **Breaking Change**: `RefStatus` is a public `Literal`. Any external consumer
  exhaustively matching it would need the new member, though there are none in
  this repo outside the three listed.

## Scope Boundaries

- **In scope**: the verdict label and its propagation to the three consumers.
- **Out of scope**: changing *whether* ambiguous refs resolve. Declining is
  correct and stays.
- **Out of scope**: untracked-by-design directories reporting `stale` — that is
  a separate root cause with its own issue.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/text_utils.py` | The classifier and its resolution-order contract |
| `.claude/CLAUDE.md` | § CLI Tools enumerates `format-check`'s gap classes |

## Session Log
- `/ll:wire-issue` - 2026-08-03T00:37:25 - `ee2cf08a-9d4e-4629-b2ec-7211d56b5a4e.jsonl`
- `/ll:refine-issue` - 2026-08-03T00:26:30 - `879a3201-ecea-4313-99de-95ce49087308.jsonl`
- `/ll:capture-issue` - 2026-08-02

## Status

- **Status**: open

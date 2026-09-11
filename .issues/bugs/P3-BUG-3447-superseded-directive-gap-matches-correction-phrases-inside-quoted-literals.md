---
id: BUG-3447
type: BUG
title: superseded-directive gap matches correction phrases inside quoted literals
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-11'
captured_at: '2026-09-11T03:57:18Z'
---

# BUG-3447: superseded-directive gap matches correction phrases inside quoted literals

## Summary

`check_format_gaps`'s `unmarked_superseded_directive` detector matches its closed correction-phrase list as raw case-insensitive substrings over the whole `### Codebase Research Findings` body, so a phrase appearing inside a **quoted string literal or a backtick code span** is treated as an author-asserted correction. Quoting a warning message, error string, or exception text — exactly what a research-findings block should do — trips the gap and fails `ll-issues format-check`, even when the author superseded nothing.

Both available escapes are bad. Adding a `⚠ Superseded` marker to satisfy the gate is not inert: `superseded_marker_count` is consumed by `loops/autodev.yaml` as the ENH-2992 `contradiction` predicate term that routes an issue to `/ll:reconcile-issue`, so the easy fix injects a fabricated contradiction signal into autodev's routing. The alternative is contorting accurate prose to dodge a 7-phrase list.

## Current Behavior

`issue_parser.py:1189-1195`:

```python
findings_bodies = _heading_bodies(content, "Codebase Research Findings")
has_correction = any(
    phrase in body.lower()
    for body in findings_bodies
    for phrase in _SUPERSEDED_CORRECTION_PHRASES
)
```

`phrase in body.lower()` is an unguarded substring test. `_SUPERSEDED_CORRECTION_PHRASES` (`:1462-1470`) is `"is wrong"`, `"does not exist"`, `"will not work"`, `"must be dropped"`, `"target file is wrong"`, `"is stale"`, `"omit entirely"` — all ordinary phrasings that occur naturally inside quoted identifiers, warning names, and error messages.

When `has_correction` is true and none of `## Implementation Steps` / `### Files to Modify` / `## Acceptance Criteria` carries a `⚠ Superseded` marker (`_SUPERSEDED_MARKER_PREFIX`, `:1472`), the gap is appended (`:1201-1202`) and `ll-issues format-check` exits 1.

Verified reproduction — three bodies differing only in whether the phrase is prose, a quoted literal, or a code span, run through `check_format_gaps` on an otherwise-clean BUG file:

```
genuine correction in prose                -> unmarked_superseded_directive = True
phrase inside a quoted literal             -> unmarked_superseded_directive = True
phrase inside a backtick code span         -> unmarked_superseded_directive = True
```

The two false positives are indistinguishable from the true positive. Concretely, the quoted-literal case was a findings bullet reading: `` `test_hook_session_start.py:675` pins that DESIGN.md-sourced projects don't trip the "path does not exist" warning `` — the substring `does not exist` matched inside the quoted warning name.

## Expected Behavior

A correction phrase occurring inside a fenced code block, an inline backtick code span, or a quoted string literal must **not** set `has_correction`. The same phrase in the author's own prose must flag exactly as today. `ll-issues format-check` must exit 0 for an issue whose findings block only quotes artifacts.

The existing four behaviours pinned by `TestUnmarkedSupersededDirective` (`:1355-1468`) — correction without marker flags, marked line does not flag, correction phrasing outside a findings block does not flag, JSON reporting — must all continue to pass unchanged.

## Motivation

A structural linter that fails accurately-written issues teaches authors to distrust it, and this one fails them in the exact place they are being most rigorous. `### Codebase Research Findings` blocks exist to record verified facts about the codebase, and verified facts are quoted: warning strings, exception messages, test names, log lines. Six of the seven phrases in `_SUPERSEDED_CORRECTION_PHRASES` are ordinary English that occurs routinely inside such quotations, so the more precisely an author documents evidence, the more likely the gap fires.

The cost is not just a red lint. The cheapest way to clear it is to add a `⚠ Superseded` marker, and that marker is load-bearing elsewhere: `superseded_marker_count` (`issue_parser.py:2000-2024`) is read by `loops/autodev.yaml:1707` as the ENH-2992 `contradiction` predicate term that routes an issue to `/ll:reconcile-issue`. An author silencing a false positive therefore fabricates a contradiction signal, spending a reconcile dispatch (capped at 2 per issue) on an issue that has nothing to reconcile. The alternative — rewording accurate prose to dodge a closed phrase list — degrades the evidence record the block exists to hold. Both outcomes were observed on 2026-09-11 while editing ENH-3441, where the phrase had to be reworded from a quoted warning name to "the missing-token-path warning" purely to clear the gate.

## Proposed Solution

Strip non-prose spans from each findings body before phrase matching. A minimal approach: remove fenced blocks (``` … ```), inline code spans (`` ` … ` ``), and double/single-quoted runs from a copy of the body, then run the existing substring scan over the residue. This is a preprocessing step local to the `has_correction` comprehension; `_SUPERSEDED_CORRECTION_PHRASES`, `_SUPERSEDED_MARKER_PREFIX`, `_heading_bodies`, and `superseded_marker_count` are all unchanged.

Precedent for the shape of the fix: ENH-2999 narrowed `stale_file_ref` after it conflated absent with ambiguous references, and BUG-3147 corrected a matcher whose phrasing assumptions were too narrow. Both are completed; neither touches this gap class.

Care needed: stripping quoted runs must not blind the detector to a genuine correction the author placed in quotes for emphasis. If that trade-off is judged too coarse, an alternative is to require the phrase to appear outside any code/quote span **and** to co-occur with a directive-section identifier — but that is a larger change to ENH-2995's semantics and should be a separate decision.

### Tests

`scripts/tests/test_ll_issues_format_check.py::TestUnmarkedSupersededDirective` (`:1355-1468`) currently covers: correction without marker flags, marked line does not flag, correction outside a findings block does not flag, and single-ID JSON reporting. `TestSupersededMarkerCountKey` (`:1471`) covers the count key.

**Coverage gap**: no test places a listed phrase inside a quoted literal or a code span. Net-new cases: (a) phrase in a double-quoted literal → no flag; (b) phrase in an inline backtick span → no flag; (c) phrase in a fenced block → no flag; (d) phrase in prose in the same file as (a)-(c) → still flags, proving the strip is scoped and not a blanket disable.

### Documentation

`docs/reference/CLI.md` describes `format-check`'s gap classes; the `unmarked_superseded_directive` entry should note that quoted and code spans are excluded from phrase matching.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — the `has_correction` comprehension inside `check_format_gaps()` (`:1190-1194`), plus one new module-private stripping helper alongside it. No change to `_SUPERSEDED_CORRECTION_PHRASES` (`:1462-1470`), `_SUPERSEDED_MARKER_PREFIX` (`:1472`), `_SUPERSEDED_DIRECTIVE_SECTIONS` (`:1471`), `_heading_bodies` (`:2220`), `superseded_marker_count` (`:2000`), or the `FormatGaps` dataclass (`:540`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/format_check.py:623,639` — invokes `check_format_gaps` twice per issue (pre-fix and post-`--fix` state); the gap list surfaces verbatim in both text and `--format json` output, so the fix changes what those reports contain without changing their shape
- `scripts/little_loops/cli/issues/check_design.py:39-40` — calls `check_format_gaps(path)` then `design_gate_failed(gaps)`; unaffected, since `design_gate_failed` (`:644`) reads only the Program Design gaps, not `unmarked_superseded_directive`
- `scripts/little_loops/loops/autodev.yaml:1707` — consumes `superseded_marker_count` from the `format-check --format json` payload for the ENH-2992 `contradiction` predicate. Reads the *marker count*, not this gap list, so it is untouched by the fix — but it is the reason the false positive is costly rather than merely annoying, and it must stay unchanged
- `scripts/little_loops/cli/issues/deferred_triage.py:33` — weights `design_gate_failed`; unaffected

### Similar Patterns
- `issue_parser.py:2270-2273` `_TESTABLE_PATTERNS` — precompiled word-boundary guards `(?<![a-z0-9_])...(?![a-z])` added for the ENH-2966 F1b/F1c false-positive class ("doesn't match inside an identifier or underscore-separated filename"). Same *class* of defect, different remedy: boundary guards would not fix this one, because `does not exist` matches with clean word boundaries inside a quoted literal
- `issue_parser.py:2283` `_BOLD_OPTION_MARKER` and `_OPTION_PATTERNS` — the BUG-3285 precedent for converging a matching rule so it is "encoded exactly once"; if a span-stripping helper is added, other substring scanners in this module are candidate follow-up consumers, but converting them is out of scope here
- `issue_parser.py:1903` `_unapplied_decision_pairs` — the ENH-3256 sibling detector, which already exempts paragraphs containing `_SUPERSEDED_MARKER_PREFIX`. It is the nearest example in this module of a matcher that carries an explicit contextual exemption, and is the shape to follow

### Behavior Parity

Replaces nothing. This narrows one existing gap class's trigger condition; no code path is removed and no public contract changes. `FormatGaps.unmarked_superseded_directive` keeps its type (`list[str]`), its payload shape (issue filenames), and its four currently-pinned behaviors. `loops/autodev.yaml`'s `contradiction` predicate keeps reading `superseded_marker_count`, which counts `⚠ Superseded` markers in directive sections and is computed independently of this detector — so no autodev routing behavior changes. The only observable difference is that issues whose findings block merely *quotes* a listed phrase stop being reported.

### Tests
- `scripts/tests/test_ll_issues_format_check.py:1355-1468` `TestUnmarkedSupersededDirective` — four existing cases (flag without marker, no flag when marked, no flag for correction phrasing outside a findings block, single-ID JSON reporting) must all keep passing unchanged
- `scripts/tests/test_ll_issues_format_check.py:1471` `TestSupersededMarkerCountKey` — subclasses the above and pins the `superseded_marker_count` JSON key that `autodev.yaml` consumes; must stay green
- `scripts/tests/test_issue_parser.py:5146` — covers `superseded_marker_count`'s directive-section scoping
- `scripts/tests/test_autodev_loop.py:88,310` — drives the loop's `contradiction` branch from an injected `LL_FORMAT_CHECK_JSON` payload including `superseded_marker_count`; unaffected but worth running as the downstream consumer
- Net-new: four cases per Proposed Solution § Tests — phrase in a quoted literal, in an inline code span, and in a fenced block each report no gap, while a prose phrase in the same file still reports one

### Documentation
- `docs/reference/API.md:912` — the `unmarked_superseded_directive` gap-class entry; add that quoted literals and code spans are excluded from phrase matching
- `docs/reference/CLI.md:2439` — the same gap class described under `ll-issues format-check`; mirror the note
- `docs/reference/API.md:898` and `docs/reference/CLI.md:2338` both state a twenty-eight-class count and instruct re-deriving it from `dataclasses.fields(FormatGaps)`; no class is added or removed, so neither count changes

### Configuration
- None — the detector has no config surface, and `.ll/program-design-cutover.json` arms only the Program Design gate, not this one

## Program Design

### Types

None new. `FormatGaps` (`issue_parser.py:540`) is unchanged — `unmarked_superseded_directive: list[str]` keeps its type and payload shape, and the twenty-eight-class count documented at `docs/reference/API.md:898` does not move.

### Signatures

- `check_format_gaps(issue_path: Path, templates_dir: Path | None = None, issue_statuses: dict[str, str] | None = None, ref_index: RefIndex | None = None, symbol_index: SymbolIndex | None = None, cli_index: CliSurfaceIndex | None = None) -> FormatGaps` — existing (`:684`); signature unchanged, the `has_correction` comprehension at `:1190-1194` gains a stripping call
- `_strip_quoted_spans(text: str) -> str` (new, module-private, `issue_parser.py` beside `_SUPERSEDED_CORRECTION_PHRASES`) — returns *text* with fenced code blocks, inline backtick spans, and quoted runs removed. Pure string transform, no I/O, no new parameters on any public function. Precompile its patterns at module load, matching `_TESTABLE_PATTERNS`' stated reason (`:2269`: "Precompiled once at module load so an `--all` sweep doesn't recompile … per issue")

### Call Path

`ll-issues format-check` -> `format_check.py:623` / `:639` -> `check_format_gaps()` -> `_heading_bodies(content, "Codebase Research Findings")` (`:1189`, unchanged) -> `_strip_quoted_spans(body)` (new) -> existing substring scan over `_SUPERSEDED_CORRECTION_PHRASES` -> `gaps.unmarked_superseded_directive.append(issue_path.name)` (`:1202`, unchanged).

Independent path, deliberately untouched: `ll-issues check-design` -> `check_design.py:39` -> `check_format_gaps()` -> `design_gate_failed(gaps)` (`:644`), and `autodev.yaml:1707` -> `superseded_marker_count` (`:2000`).

Constraint: fail-open behavior is preserved. `check_format_gaps` already reports no gaps on an unresolved template or unreadable file rather than blocking; `_strip_quoted_spans` must not raise on malformed markup (unbalanced backticks or an unterminated fence) — strip what it can recognize and return the residue.

## Implementation Steps

1. Outcome — quoted and code spans stop triggering the gap: `_strip_quoted_spans` removes fenced blocks, inline backtick spans, and quoted runs from each findings body before the `has_correction` scan (`issue_parser.py:1190-1194`), so a bullet that only quotes a warning name, exception message, or test identifier reports no gap
2. Constraint — genuine prose corrections still flag: the four cases in `TestUnmarkedSupersededDirective` (`test_ll_issues_format_check.py:1355-1468`) and the `superseded_marker_count` key in `TestSupersededMarkerCountKey` (`:1471`) pass **unchanged**. This is a narrowing, not a disable — if the new tests pass by making the detector never fire, the change is wrong
3. Outcome — new coverage for the false-positive class: four cases added to `TestUnmarkedSupersededDirective` — listed phrase in a double-quoted literal, in an inline backtick span, and in a fenced block each report no gap; and a fourth file carrying the same phrase in prose *alongside* those three forms still reports one, proving the strip is scoped
4. Constraint — downstream consumers untouched: `superseded_marker_count` (`:2000-2024`) and `design_gate_failed` (`:644`) are not modified, so `loops/autodev.yaml:1707`'s ENH-2992 `contradiction` predicate and `cli/issues/check_design.py:39-40` behave identically. Run `scripts/tests/test_autodev_loop.py` to confirm the `contradiction` branch still routes from an injected marker count
5. Outcome — fail-open preserved: `_strip_quoted_spans` returns the residue rather than raising on unbalanced backticks or an unterminated fence, keeping `check_format_gaps`'s documented fail-open contract
6. Outcome — docs match behavior: `docs/reference/API.md:912` and `docs/reference/CLI.md:2439` note that quoted literals and code spans are excluded from phrase matching. Neither the twenty-eight-class count nor `dataclasses.fields(FormatGaps)` changes
7. Verification: `python -m pytest scripts/tests/test_ll_issues_format_check.py scripts/tests/test_issue_parser.py scripts/tests/test_autodev_loop.py -v` exits 0, and `ll-issues format-check --all` reports no new `unmarked_superseded_directive` entries against `main` while still reporting the ones `main` legitimately has
8. Verification — the original repro clears: re-running the three-body reproduction (prose / quoted literal / backtick span through `check_format_gaps` on an otherwise-clean BUG file) yields `True / False / False` instead of today's `True / True / True`

## Impact

- **Priority**: P3 - A false-positive advisory gate. It blocks nothing silently, but it fails `format-check` on accurately-written issues, erodes trust in the linter, and its cheapest workaround (adding a `⚠ Superseded` marker) feeds a fabricated contradiction signal into `autodev.yaml`'s reconcile routing.
- **Effort**: Small - One preprocessing helper plus four test cases; no changes to the phrase list, marker constant, or public gap keys.
- **Risk**: Low - Narrowing a detector risks false negatives, so case (d) above is required to prove genuine prose corrections still flag. No product-code behavior change.
- **Breaking Change**: No

## Steps to Reproduce

1. Take any issue that passes `ll-issues format-check`.
2. Add to a `### Codebase Research Findings` block a bullet that quotes an artifact containing a listed phrase — e.g. `` - The loader warns `"path does not exist"` and returns `None`. ``
3. Run `ll-issues format-check <ID>`.
4. Observe: exit 1 with `unmarked_superseded_directive: <file>.md`, though no directive was superseded and no correction was asserted.
5. Control: the same bullet with the phrase in plain prose (`- Step 1 does not exist in the current code`) flags identically — the matcher cannot tell the two apart.

## Root Cause

- **File**: `scripts/little_loops/issue_parser.py`
- **Anchor**: `in function check_format_gaps()` — the `has_correction` comprehension at `:1190-1194`
- **Cause**: The phrase list is matched as bare substrings against undifferentiated body text. Nothing strips fenced code blocks, inline code spans, or quoted string literals before matching, so text the author is *quoting* is scored as text the author is *asserting*. The gap class was added by ENH-2995 to detect a findings block that contradicts a directive section; a quotation is not a contradiction.

`_heading_bodies` (`:2220`) matching every `##`/`###` occurrence of the heading regardless of parent is **intentional and not the defect** — it is pinned by `test_ll_issues_format_check.py::TestUnmarkedSupersededDirective::test_all_reports_correction_without_marker`, which places the findings block under `## Implementation Steps` and expects a flag. `/ll:refine-issue` emits one findings block per parent H2 (ENH-2993), so scanning all of them is correct.

Note that the obvious fix does not apply: the neighbouring `_TESTABLE_PATTERNS` (`:2270-2273`) uses word-boundary guards `(?<![a-z0-9_])...(?![a-z])` for a similar false-positive class, but in the reproduction above `does not exist` matches with clean word boundaries inside the quoted literal. Boundary guards would not have prevented it. The needed guard is contextual (strip quoted/code spans), not lexical.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-11 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-11T04:00:50 - `515fc7bd-e601-4deb-8bd5-084871c22c6f.jsonl`

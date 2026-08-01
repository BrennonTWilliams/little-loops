---
id: ENH-2950
title: 'll-issues locate-options --json: expose option spans so decide-issue stops
  re-implementing Patterns 1-5'
type: ENH
priority: P1
status: done
discovered_by: skill-audit
discovered_date: 2026-07-31
completed_at: '2026-08-01T03:06:43Z'
parent: EPIC-2938
epic: EPIC-2938
relates_to:
- ENH-2939
- ENH-2936
- ENH-2443
labels:
- cli
- issues
- determinism
- drift
confidence_score: 98
outcome_confidence: 83
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 22
---

# ENH-2950: `ll-issues locate-options --json` — option spans for decide-issue

## Summary

`skills/decide-issue/SKILL.md` Phase 3 (Patterns 1–4, L150–196) and Phase 3b (Provisional
Patterns A–E, L197–336) specify option detection in prose, while
`issue_parser.locate_enumerable_options` (L527–565) implements the same precedence chain
in Python. ENH-2936 proved the divergence risk is live: it had to land Pattern E in
**both** places in one commit (`5e29c4d4`). Expose the Python locator's full result as
JSON so the skill reads spans instead of re-scanning.

## Current Behavior

- `ll-issues check-decidable <ID>` is exit-code only (`cli/issues/check_decidable.py`);
  its `--help` exposes no output flag.
- `locate_enumerable_options(content) -> tuple[int, str | None]` returns only
  `(count, containing_heading)` — enough for a boolean gate, not enough for a consumer.
- Phase 3b does not merely *detect*: it **materializes** options, writing
  `**Option A**`/`**Option B**` blocks into the issue file before Phase 4–7 scoring.
  A boolean gate therefore cannot replace the skill's pattern prose — which is why
  ENH-2939 (markdown-only) cannot absorb this work.

## Expected Behavior

- `ll-issues locate-options <id> [--json]` → `{id, count, pattern, heading, options: [{label, text, start_line, end_line}]}`,
  where `pattern` names which rule fired (`section_header` | `bold_label` | `numbered` |
  `bullet` | `provisional_a` … `provisional_e`) so the skill can branch on provenance
  without re-deriving it.
- `check-decidable` keeps its exit-code contract unchanged (FSM loops consume it) and is
  reimplemented over the same locator result — one code path, two frontends.
- decide-issue Phase 3/3b becomes: call `locate-options --json`; if `pattern` is a
  provisional (A–E) shape, materialize the returned spans into `**Option N**` blocks;
  proceed to Phase 4. The pattern *definitions* live only in `issue_parser.py`.

## Proposed Solution

Widen `locate_enumerable_options` (or add a sibling returning a richer dataclass) so the
span/label data the patterns already compute internally is returned rather than discarded.
`check_decidable.py` and the new subcommand both consume it. No pattern-semantics changes —
this is a return-shape widening plus a CLI frontend.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Current implementation locations** (`scripts/little_loops/issue_parser.py`):
  `_OPTION_PATTERNS` (428–435, the four regex tiers behind this issue's Patterns 1–4),
  `_OPTION_FALLBACK_SECTIONS` (437), `_count_options_in_text()` (440–446 — confirms this
  issue's "span data already computed, discarded" claim: it does
  `n = sum(1 for _ in pattern.finditer(text))`, throwing away every `re.Match` object
  instead of capturing `.group()`/`.start()`/`.end()`), `_iter_h2_sections()` (449–464,
  whole-document fallback char-offset spans), `_locate_directive_alternatives()` (507–542,
  Pattern E — hardcodes `return 2, heading` with no per-alternative label/text extraction
  at all), `locate_enumerable_options()` itself at **545–583** (the Summary section above
  cites L527–565 — that anchor has drifted; 545–583 is current), `count_enumerable_options()`
  (586–595, thin wrapper: `count, _ = locate_enumerable_options(content); return count`).
- **Existing 2-tuple call sites that must move to `.count`/`.heading` attribute access**:
  `cli/issues/check_decidable.py:34` (`count, heading = locate_enumerable_options(...)`,
  the exact function this issue says to reimplement over the widened result), plus 4+ sites
  in `scripts/tests/test_issue_parser_unresolved.py` (`TestCountEnumerableOptions` class,
  ~L19–68).
- **Serialization convention**: `issue_parser.py` result dataclasses use a hand-written
  `to_dict()` method, never `dataclasses.asdict()` — see `FormatGaps` (164–212), `QuestionGaps`
  (215–235, docstring: "Mirror of `FormatGaps`" — the established idiom for spinning up a new
  sibling result dataclass), `ProductImpact` (826–868, also has `from_dict()`).
  `EpicProgress.to_dict()` (`issue_progress.py:17–48`) is the closest precedent for a dataclass
  with a *nested* object field — it manually flattens rather than nesting the full child
  dataclass, relevant for serializing `LocatedOptions.options: list[LocatedOption]`.
  `cli/code.py:160` shows the codebase's one `dataclasses.asdict()` precedent (per-item, inside
  a hand-built envelope dict) as a fallback if `to_dict()` proves awkward for the nested list.
- **CLI `--json` subcommand template**: `cli/issues/path_cmd.py`'s `cmd_path()` (full 43-line
  file) is the simplest end-to-end model — resolve issue, then
  `if getattr(args, "json", False): print_json({...}); return 0`. `check-decidable`'s own
  subparser registration (`cli/issues/__init__.py:655–661`, dispatch at 892–893) is the more
  directly adjacent template — currently no `--json` flag, unlike `show`/`path`/`impact-effort`
  which all register `--json`/`-j` as `action="store_true"` at subparser construction.
  `print_json()` lives at `cli/output.py:215–217`.
- **Test precedent for the parity acceptance criterion**:
  `scripts/tests/test_ll_issues_check_decidable.py` (235 lines) — class-per-scenario structure
  (`TestCheckDecidableHappyPath`, `TestCheckDecidableWidenedOptions`,
  `TestCheckDecidablePatternEDirective`), subprocess-based via `_invoke()`/`_write_issue()`
  helpers, `TestCliRegistration` asserts `--help` output contains the subcommand name. No
  `@pytest.mark.parametrize` is used for this function anywhere today — each pattern gets its
  own test class/method; new Pattern 1–5/A–E fixture tests should follow that convention rather
  than parametrizing.

## Implementation Steps

1. Introduce `LocatedOptions` dataclass and return it from the locator; adapt
   `count_enumerable_options` / `check-decidable` call sites (behavior-preserving).
2. Add `locate-options` subparser with `--json`.
3. Rewrite decide-issue Phase 3/3b to consume the JSON; delete the pattern regexes and
   their prose restatements (~120 lines). Keep the materialization step and Phase 4–7.
4. Tests: fixture issues per pattern (1–4, A–E) asserting identical `count` to today's
   `check-decidable` exit code, plus span correctness for the provisional shapes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update the internal `count, _ = locate_enumerable_options(content)` call site inside
   `count_enumerable_options()` (`issue_parser.py:594`) to `.count` attribute access, and
   update the `locate_unresolved_options()`/`count_unresolved_options()` "Mirrors ..."
   docstrings to note the return-shape divergence from their sibling.
6. Rewrite `scripts/tests/test_decide_issue_skill.py`'s structural assertions against the
   deleted Phase 3/Phase 3b headings (`content.index("## Phase 3...")` boundaries and
   `Pattern 1-4`/`Pattern D`/`Pattern E` wording checks) to match whatever prose survives
   the `locate-options --json` rewrite.
7. Regenerate host mirrors (`.kimi-code/skills/decide-issue/SKILL.md`,
   `.gemini/skills/decide-issue/SKILL.md`) via `ll-adapt --host <host> --apply` after the
   canonical `skills/decide-issue/SKILL.md` change lands.
8. Add a `#### ll-issues locate-options` section to `docs/reference/CLI.md`, update the
   stale Phase 3/3b narrative in `docs/reference/COMMANDS.md` (`/ll:decide-issue` entry)
   and `docs/guides/DECISIONS_LOG_GUIDE.md`, and add a `locate_enumerable_options`/
   `LocatedOptions` entry to `docs/reference/API.md`.
9. Add a `locate-options` line to the `cli/issues/__init__.py` epilog subcommand listing
   (separate from the `add_parser` subparser registration in step 2).

## Program Design

### Types

- `LocatedOption: dataclass`
  - `label: str`
  - `text: str`
  - `start_line: int`
  - `end_line: int`
- `LocatedOptions: dataclass`
  - `count: int`
  - `pattern: str | None`
  - `heading: str | None`
  - `options: list[LocatedOption]`

### Signatures

- `locate_enumerable_options(content: str) -> LocatedOptions`
- `locate_options(issue_id: str, issues_dir: Path) -> LocatedOptions`

Widened return; existing `(count, heading)` consumers read `.count` / `.heading`. New
`locate-options` subparser wired in `scripts/little_loops/cli/issues/__init__.py`.

### Call Path

- `check_decidable()` (existing, `cli/issues/check_decidable.py`) -> `locate_enumerable_options()` (existing, `issue_parser.py`)
- `locate_options()` (new) -> `locate_enumerable_options()` -> `parse_frontmatter()` (existing, `issue_parser.py`)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_parser.py:594` — internal call site inside `count_enumerable_options()` itself (`count, _ = locate_enumerable_options(content)`); must move to `.count` alongside the two call sites already named in Codebase Research Findings [Agent 2 finding]
- `scripts/little_loops/issue_parser.py` — `locate_unresolved_options()`/`count_unresolved_options()` docstrings self-describe as "Mirrors `locate_enumerable_options`"/"Mirrors `count_enumerable_options`"; once the mirrored function's return type diverges (tuple → dataclass) those docstrings become inaccurate and should be updated to note the shape difference, even though the sibling functions' own tuple-returning code is unaffected [Agent 2 finding]
- `scripts/little_loops/cli/issues/check_open_questions.py:48-50` — imports `count_open_questions_in_sections`/`locate_unresolved_options`, the sibling option-detection family; not a call-site break but worth a read-through to confirm no cross-import of the widened function [Agent 1 finding]
- `scripts/tests/test_decide_issue_skill.py` — imports `count_enumerable_options` (multiple call sites) AND contains extensive structural assertions against the exact Phase 3/Phase 3b SKILL.md prose this issue deletes: `content.index("## Phase 3: Extract Options")` / `content.index("## Phase 3b")` string-slice boundaries (~L326-327, 445, 474-475, 555, 596) that raise `ValueError` the moment those headings are deleted, plus assertions on `"Pattern 1"`-`"Pattern 4"`, `"Pattern D"`, `"Pattern E"`, `"Phase 3b-i"`, `"NO_ACTIONABLE_DECISIONS"` wording (~L53-80, 220-312, 317-350, 546-693). This file needs substantial rewriting, not just an import-shape fix — the single largest test-collateral surface of this issue [Agent 2 + Agent 3 finding]
- `.kimi-code/skills/decide-issue/SKILL.md`, `.gemini/skills/decide-issue/SKILL.md` — `ll-adapt`-generated host mirrors of `skills/decide-issue/SKILL.md`; both currently contain the full Phase 3/3b prose being deleted. Not hand-edited — require `ll-adapt --host kimi-code --apply` / `--host gemini --apply` (or equivalent) after the canonical SKILL.md change lands, or the mirrors silently drift stale [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `count_enumerable_options` doc block explicitly describes it as re-implementing "Phase 3's option-extraction patterns" and walks through the precedence tiers; goes stale once Phase 3/3b prose is deleted from SKILL.md. Add a `locate_enumerable_options`/`LocatedOptions` API entry (verify one doesn't already exist under a different anchor before assuming) [Agent 2 finding]
- `docs/reference/CLI.md:1616-1628` — add a new `#### ll-issues locate-options` section (Argument table, Examples, FSM loop use note) following the `check-decidable` section's existing pattern; also cross-check the adjacent `check-open-questions` section (~L1634) for any needed `locate-options` mention [Agent 2 finding]
- `docs/reference/COMMANDS.md` (~L252, `/ll:decide-issue` entry) — describes "Phase 2.5 counts enumerable options... Phase 3 → Phase 3b's inline provisional-language scan... Pattern E (ENH-2936)... FSM callers use `ll-issues check-decidable`" — directly stale once Phase 3/3b prose is deleted [Agent 2 finding]
- `docs/guides/DECISIONS_LOG_GUIDE.md` (~L198, "The structural-vs-semantic gap (ENH-2443)") — narrates decide-issue Phase 2.5/3/3b behavior including Pattern E in detail; needs a matching rewrite once the skill's prose is replaced with a `locate-options --json` call [Agent 2 finding]
- `scripts/little_loops/cli/issues/__init__.py` epilog (~L81-107, `RawDescriptionHelpFormatter` epilog hand-listing every subcommand with a one-line description) — add a `locate-options` line matching the existing `check-decidable` convention; this is a second, separate spot from the `add_parser` subparser registration already named in Program Design [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser_unresolved.py` — 10 call sites (not just the class already named) do `count, heading = locate_enumerable_options(content)` and will break on the tuple→dataclass change: L33, 51, 65, 326, 340, 355, 368, 382, 395, 413 [Agent 3 finding]
- New test file `scripts/tests/test_issues_locate_options.py` modeled on `scripts/tests/test_issues_path.py::TestPathJsonFlag` (L176-227) — the closest precedent for in-process argv/capsys `--json` dict-shape assertions on a new `ll-issues` subcommand; pair with a `TestCliRegistration`-style help-text check modeled on `test_ll_issues_check_decidable.py:228-235` [Agent 3 finding]
- New dataclass unit test for `LocatedOptions`/`LocatedOption` field values and `to_dict()` output — no existing `FormatGaps`/`QuestionGaps`/`ProductImpact` precedent tests `to_dict()` in isolation (all three are exercised only indirectly through their CLI's `--json`/`--format json` path), so this establishes the first direct dataclass-shape test in this family; append to `test_issue_parser_unresolved.py` or a small new test class [Agent 3 finding]

## Scope Boundaries

- In scope: locator return-shape widening, the `locate-options` subcommand, decide-issue
  Phase 3/3b prose deletion.
- Out of scope: changing which shapes count as decidable (that is ENH-2936/ENH-2443
  territory), decide-issue Phases 4–7 scoring, `check-decidable`'s exit-code contract.

## Impact

- **Priority**: P1 - Wave 1; removes the epic's most recently-*re-created* prose/Python duplication (ENH-2936 landed Pattern E twice in one commit)
- **Effort**: Small - Return-shape widening plus a thin subcommand
- **Risk**: Low - Behavior-preserving for existing consumers; exit-code contract untouched

## Status

**Open** | Created: 2026-07-31 | Priority: P1

## Acceptance Criteria

- [ ] `ll-issues locate-options <id> --json` returns count, firing pattern, and option spans
- [ ] `check-decidable`'s exit code is unchanged for every existing fixture (parity test)
- [ ] `skills/decide-issue/SKILL.md` contains no option-detection regexes or pattern definitions; it materializes from CLI output
- [ ] Pattern precedence is defined in exactly one place (`issue_parser.py`)
- [ ] pytest coverage in `scripts/tests/`

## Notes

Split out of ENH-2939, whose markdown-only scope could not absorb it: Phase 3b writes
option blocks into the file, so a boolean gate is insufficient.


## Session Log
- `/ll:manage-issue` - 2026-08-01T03:06:17 - `a8b52052-a0ab-45ac-8352-3b276f3697e8.jsonl`
- `/ll:ready-issue` - 2026-08-01T02:37:48 - `63307b74-3ee2-46f6-990f-4a93da9b7ff5.jsonl`
- `/ll:confidence-check` - 2026-08-01T02:35:16 - `c1a769ef-df25-48f2-8f59-4094cc5b0dbe.jsonl`
- `/ll:wire-issue` - 2026-08-01T02:33:15 - `29c7a853-4f89-46ec-af6e-8ddb4fd9fa82.jsonl`
- `/ll:refine-issue` - 2026-08-01T02:26:58 - `d8d856af-d10a-43bc-a5e5-6022a4c9d05f.jsonl`

---
id: BUG-3225
type: BUG
title: 'll-issues normalize: malformed_filename findings for underscored slugs are
  self-referential no-ops, permanently failing --check'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:38:23Z'
labels:
- issue-management
- normalize-issues
confidence_score: 92
outcome_confidence: 94
score_complexity: 24
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 23
---

# BUG-3225: ll-issues normalize: malformed_filename findings for underscored slugs are self-referential no-ops, permanently failing --check

## Summary

`ll-issues normalize`'s `malformed_filename` finding is a self-referential no-op for any issue whose slug contains an underscore: `is_normalized()` (`scripts/little_loops/issue_parser.py:135`) requires the slug to match `[a-z0-9-]+`, which rejects underscores, but the "fix" computed for the finding (`_slug_for()` → `slugify()`, `scripts/little_loops/issue_parser.py:1634`) uses `re.sub(r"[^\w\s-]", "", text)`, and `\w` includes underscores — so `slugify()` never strips them. `proposed_path` therefore equals `path` for every affected file, `--auto` correctly detects the no-op and skips applying it (`applied: []`), but the finding is reported every run with no way to clear it.

## Current Behavior

On the little-loops corpus itself, `ll-issues normalize` reports ~29 `malformed_filename` findings, nearly all of them files with a legitimately-formed filename whose slug happens to contain an underscore (e.g. `P2-BUG-3216-ll-logs-telemetry-digest-refresh_corpus-passes-unregistered-quiet-and-omits-required-extract-target-loop-dies-on-first-state.md`). `--auto` is a no-op for these (`applied: 0`), and per the `--check`/`--strict` table in `commands/normalize-issues.md`, `malformed_filename` gates non-strict `--check` — so any project with an underscored slug in its history fails the deterministic FSM gate permanently, with no fix available.

## Expected Behavior

Either `is_normalized()`'s slug pattern should accept underscores (matching what `slugify()` actually produces), or `slugify()`/`_slug_for()` should strip underscores (matching what `is_normalized()` requires) so the two functions agree and `malformed_filename` findings are always resolvable by `--auto`.

## Proposed Solution

Prefer widening `_NORMALIZED_RE` to allow underscores (`[a-z0-9_-]+`) over tightening `slugify()`, since `slugify()` is the general-purpose slug function used elsewhere (title→filename generation) and existing filenames across the corpus already contain underscores by convention (e.g. `history_session_guidemd`, `subagent_runs`) — retroactively stripping them via `--auto` would trigger a large one-time mass-rename with no functional benefit.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/issue_parser.py:50` — `_NORMALIZED_RE`'s slug character class `[a-z0-9-]+` is the narrower of the two definitions; widening it to include `_` (or tightening `slugify()`, the alternative the issue rejects) is the fix surface.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/normalize.py:335` — `scan_normalize()`'s finding-emission gate: `if is_normalized(path.name): continue`
- `scripts/little_loops/cli/issues/normalize.py:341` — `proposed_path` built via `_slug_for(path.name)` → `slugify()`
- `scripts/little_loops/cli/issues/normalize.py:432-474` — `apply_normalize()`; no-op detection is `if finding.proposed_path.exists(): continue`
- `scripts/little_loops/cli/issues/normalize.py:544-595` — `cmd_normalize()`; `malformed_filename` is unconditionally in `AUTO_FIXABLE_KINDS`/`relevant_kinds` (not gated behind `--strict`)
- `scripts/little_loops/cli/issues/show.py:307` — `is_normalized()` drives the ✓/✗ checkmark in single-issue detail view
- `scripts/little_loops/cli/issues/refine_status.py:337,362,441` — `is_normalized()` drives the `"normalized"` JSON field and table checkmark column

### Conventions in Force
- `slugify()` is the codebase's single generator for "slug": every other slug consumer imports and calls it rather than reimplementing slug logic (`worker_pool.py:1913`, `issue_lifecycle.py:836`, `scaffold_epic.py:89,105`, `create.py:400,444`, `scaffold_verify.py:266`, `ctx_stats.py:677,701`, `learning_tests/__init__.py:122`, `learning_tests/extractor.py:239`, `cli/learning_tests.py`, `session_store/writers.py:1603,1671`, `history_reader.py:1450`). `slugify()`'s output contract (`\w` includes underscore, asserted by the hypothesis property test `test_issue_parser_properties.py:19-42::test_slugify_only_word_chars_and_hyphens`) is therefore the codebase-wide definition of "slug" — `_NORMALIZED_RE` is the outlier independently re-deriving a narrower one.
- When two regexes are intentionally coupled elsewhere in `issue_parser.py`, the coupling is made explicit — either a cross-reference comment (`_ANCHORED_FILENAME_RE` at `issue_parser.py:54-58` documents its relationship to `_FILENAME_ID_RE`) or deriving one pattern from the other via interpolation (`_FINDINGS_H3_RE` at `issue_parser.py:859` is built from `_FINDINGS_SUB_HEADING` rather than a duplicated literal). No such coupling exists today between `_NORMALIZED_RE` and `slugify()`.

### Tests
- `scripts/tests/test_ll_issues_normalize.py:155` — `TestMalformedFilename`, the only existing `malformed_filename` test; covers a missing-priority-prefix case, not underscore. Pattern: write a fixture into `normalize_dir`, call `scan_normalize(config)` directly, assert on `findings[0]` fields and `to_dict()`.
- `scripts/tests/test_issue_parser.py:30-62` — `TestSlugify` (8 example-based cases); none exercise underscore input.
- `scripts/tests/test_issue_parser_properties.py:19-42` — `TestSlugifyProperties.test_slugify_only_word_chars_and_hyphens`; already documents (but doesn't enforce against `_NORMALIZED_RE`) that underscores survive `slugify()`.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

### Types
N/A — no new data shape introduced; `NormalizeFinding` is unchanged.

### Signatures
- `_NORMALIZED_RE: re.Pattern[str]` — defined at `scripts/little_loops/issue_parser.py:50`; current value `re.compile(r"^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}-[a-z0-9-]+\.md$")`
- `is_normalized(filename: str) -> bool` — defined at `scripts/little_loops/issue_parser.py:135`; sole caller of `_NORMALIZED_RE.match`
- `slugify(text: str) -> str` — defined at `scripts/little_loops/issue_parser.py:1634`; current char filter `re.sub(r"[^\w\s-]", "", text)`
- `_slug_for(filename: str) -> str` — defined at `scripts/little_loops/cli/issues/normalize.py:124`; delegates to `slugify()`

### Call Path
`scan_normalize()` (defined at `normalize.py:333-353`) calls `is_normalized()` (defined at `issue_parser.py:135`; gate at `normalize.py:335`) then `_slug_for()` (`normalize.py:341`) then `slugify()` (`issue_parser.py:1634`), producing `proposed_path`, which `apply_normalize()` (defined at `normalize.py:432-474`) checks via `finding.proposed_path.exists()`, gated at `--check`/`--strict` time by `cmd_normalize()` (defined at `normalize.py:544-595`) through `AUTO_FIXABLE_KINDS`/`relevant_kinds`.

### Decision Rules
N/A — no new decision logic; this fix reconciles two existing regex character classes, it does not introduce a gap kind, gate, threshold, or keyword list.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

1. `_NORMALIZED_RE`'s slug character class (`scripts/little_loops/issue_parser.py:50`) accepts the same characters `slugify()` (`scripts/little_loops/issue_parser.py:1634`) actually produces, so `is_normalized()` and the `--auto` fix-computation agree for every existing corpus filename — including files with underscored slugs.
2. `_slug_for()`'s call chain (`scripts/little_loops/cli/issues/normalize.py:124-131`) and `scan_normalize()`'s finding-emission gate (`normalize.py:335`) remain consistent with the updated `_NORMALIZED_RE`; no other code path depends on the slug's character set (confirmed: `_ANCHORED_FILENAME_RE`, `_FILENAME_ID_RE`, and `_ISSUE_TYPE_RE` only match the `TYPE-NNN-` prefix token, never the trailing slug).
3. `TestMalformedFilename` (`scripts/tests/test_ll_issues_normalize.py:155`) and `TestSlugify` (`scripts/tests/test_issue_parser.py:30-62`) gain coverage for an underscored-slug filename, confirming `is_normalized()` accepts it and `scan_normalize()` emits no `malformed_filename` finding for it.
4. `python -m pytest scripts/tests/test_issue_parser.py scripts/tests/test_ll_issues_normalize.py scripts/tests/test_issue_parser_properties.py -v` passes.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Root Cause

Two independent normalizations of "slug" drifted apart:
- `_NORMALIZED_RE`'s slug group: `[a-z0-9-]+` (no underscore)
- `slugify()`'s character filter: `re.sub(r"[^\w\s-]", "", text)` (`\w` = `[a-zA-Z0-9_]`, underscore survives)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

### Exact definitions
- `_NORMALIZED_RE` (`scripts/little_loops/issue_parser.py:50`): `re.compile(r"^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}-[a-z0-9-]+\.md$")`
- `slugify()` (`scripts/little_loops/issue_parser.py:1634-1645`): `text = re.sub(r"[^\w\s-]", "", text)`, then `text = re.sub(r"[-\s]+", "-", text)`, then `.strip("-").lower()`. `\w` = `[A-Za-z0-9_]`, so underscores pass through both substitutions untouched.

### Call chain producing the no-op
`scan_normalize()` (`scripts/little_loops/cli/issues/normalize.py:333-353`) → `is_normalized(path.name)` gate (line 335, `False` for an underscored slug under the narrow regex) → finding emitted → `proposed_path` built via `_slug_for(path.name)` (line 341) → `_slug_for()` (`normalize.py:124-131`) strips priority/type/number tokens then calls `slugify()` → `slugify()` returns the underscore-containing slug unchanged → `proposed_path` byte-identical to `path`.

`apply_normalize()` (`normalize.py:432-474`): `if finding.proposed_path.exists(): continue` — trivially true since `proposed_path == path`, so the file itself satisfies the "already exists" no-op check, silently dropping the finding from `applied` with no signal distinguishing it from a genuinely-already-fixed case.

`cmd_normalize()` (`normalize.py:544-595`): `AUTO_FIXABLE_KINDS` includes `malformed_filename` unconditionally (not gated behind `--strict`), so `gate_failed` is `True` every run for any corpus containing an underscored-slug filename — `--check` returns exit 1 permanently.

## Status

**Open** | Created: 2026-08-16 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-17T00:58:43 - `a037325c-9566-4955-97cc-2bea551a22bc.jsonl`
- `/ll:refine-issue` - 2026-08-17T00:14:16 - `7f601de8-8324-466e-9daf-f07f549bd4be.jsonl`

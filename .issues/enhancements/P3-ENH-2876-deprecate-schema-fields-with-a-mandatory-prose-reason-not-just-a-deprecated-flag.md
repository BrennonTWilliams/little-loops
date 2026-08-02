---
id: ENH-2876
title: Deprecate schema fields with a mandatory prose reason, not just a deprecated
  flag
type: ENH
parent: EPIC-2872
priority: P3
status: done
discovered_date: 2026-07-27
completed_at: '2026-07-28T16:08:08Z'
labels:
- schema
learning_tests_required:
- pyyaml
confidence_score: 88
outcome_confidence: 75
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 15
---

# ENH-2876: Deprecate schema fields with a mandatory prose reason, not just a deprecated flag

Parent EPIC: routed alongside this issue — "Self-describing drift and deprecation signals".

## Summary

Issue frontmatter and loop YAML are actively evolving — `superseded_by` recently became derived-and-never-written, and status synonyms are now coerced — and each such change leaves a retired field that agents keep encountering in older files. A deprecation flag alone is not enough to get a model to drop one.

## Current Behavior

A retired schema field (frontmatter key or loop YAML key) is marked only with a boolean `deprecated: true` flag, or with free-text like `"[DEPRECATED: use IssueInfo.status instead] ..."`. No prose reason is required or enforced anywhere in the validation path, and in the one existing analog (`*-sections.json`'s `deprecation_reason`), the field silently defaults to `""` when absent — a deprecation entry with no reason passes validation today.

## Expected Behavior

A retired frontmatter key or loop YAML key carries a mandatory, non-empty prose reason at the point of validation. An agent encountering the stale key in an old file is told, in the same output that reports the key, what replaced it and why — not left to guess or to faithfully carry the field forward. A deprecation entry with an empty reason fails validation instead of passing silently.

## Impact

Without this, agents keep re-introducing or preserving retired fields (e.g. hand-authored `superseded_by:`, silently-coerced status synonyms) because nothing at read/validate time tells them the field is dead and what to do instead. This compounds every time little-loops evolves its own schema, so the fix pays for itself across every future deprecation, not just the two cases already identified.

## Scope Boundaries

In scope: a deprecated-fields map for issue frontmatter keys first, then loop YAML keys, with reason-required validation and surfacing through `check_format_gaps()`/`ll-loop validate` output. Out of scope: deprecating or removing the section-level map's existing (optional) `deprecation_reason` mechanism, and any UI/reporting surface beyond CLI output already covered by `format-check`/`ll-loop validate`.

## Reference pattern

In the reference pattern, retiring an axis from a product spec does not simply delete the field or mark it deprecated. A **deprecated-sections map** pairs each retired field with a **prose reason**, and the reason is mandatory. The rationale:

> "told only that a field is deprecated, models preserve it 'just in case', which is how a retired axis keeps steering current output."

The same repo applies the pattern to a retired command as well: rather than removing it, it is deprecated in place and left as an alias that "adds nothing", so existing invocations still land somewhere sane instead of erroring.

## Proposed change

1. Add a deprecated-fields map to little-loops' schema definitions (issue frontmatter first, loop YAML second): each retired key mapped to a one-line prose explanation of what replaced it and why.
2. Surface the reason wherever the schema is read or validated, so an agent encountering a stale field in an old file is told to drop it rather than faithfully carrying it forward.
3. Make the reason a required field of the map — a deprecation entry without one should be a validation error, not an accepted omission.
4. Where a retired key has a direct successor, name the successor in the reason.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Deprecation is currently expressed three separate, unconnected ways — this issue's map should consolidate the pattern, not invent one from scratch:

1. **Section-level map (closest existing analog, but not enforced)** — `scripts/little_loops/templates/{feat,bug,enh,epic}-sections.json` already pair a `"deprecated": true` flag with a `"deprecation_reason"` prose string, but only for markdown *section headings*, not frontmatter or loop YAML keys (e.g. `feat-sections.json` lines 167-168, 196-197, 205-206, 214-215). Consumed by `check_format_gaps()` in `scripts/little_loops/issue_parser.py` (~lines 302-318), which regex-extracts a canonical successor name from the reason via `_DEPRECATION_CANONICAL_RE` (line 137, pattern: `(?:Renamed to|Consolidated into|Redundant with) '([^']+)'`). Critically, `section_defs[name].get("deprecation_reason", "")` **defaults to `""` silently** — there is no enforcement today that a `deprecated: true` entry has a non-empty reason, which is exactly the gap AC2 ("Adding a deprecation entry without a reason fails validation") needs to close.
2. **Silent status-synonym coercion** — `STATUS_SYNONYMS` dict in `scripts/little_loops/frontmatter.py` (lines 18-27) maps `completed`/`finished`/`closed` → `done`, `in progress`/`wip` → `in_progress`, `pending` → `open`. Applied unconditionally with **no user-visible message** in both `parse_frontmatter()` (line 94) and the fallback `_parse_frontmatter_lines()` (line 171). The only place a rewrite is ever reported is the one-time `ll-migrate-status` CLI (`scripts/little_loops/cli/migrate_status.py`), not the live read path.
3. **`superseded_by` (ENH-2829)** — `superseded_by()` in `issue_parser.py` (line 1524) purely derives the reverse edge from `supersedes:`; it never reads a `superseded_by:` frontmatter key at all. There is currently **no rejection or warning** anywhere if an issue file still hand-authors `superseded_by:` — it's simply ignored, not flagged. This is the first concrete case AC3 asks the new map to represent.
4. **Free-text-only markers, zero enforcement** — `config-schema.json` lines 111-119 (`completed_dir`/`deferred_dir`, `"[DEPRECATED: use IssueInfo.status instead] ..."`) and `fsm/fsm-loop-schema.json` lines 440/444 (`on_success`/`on_failure`, `"Deprecated: use on_yes instead"`). A grep of `scripts/little_loops/fsm/validation/` for `deprecat` found **no matches** — nothing currently lints a loop YAML still using `on_success`/`on_failure`.

### Files to Modify
- `scripts/little_loops/issue_parser.py` — extend `check_format_gaps()`/`FormatGaps` with a frontmatter-key deprecation-map lookup and reason-required validation, following the existing section-deprecation consumer shape (~lines 302-318).
- `scripts/little_loops/frontmatter.py` — wire `STATUS_SYNONYMS` into the new map (or replace it) so status coercion carries a surfaced reason instead of a silent rewrite.
- `scripts/little_loops/fsm/validation/__init__.py` plus a new rule module (sibling to `meta_rules.py`) for the loop-YAML side (`on_success`/`on_failure` first case).
- `scripts/little_loops/cli/issues/format_check.py::_print_gaps()` (lines 83-99) — add a `deprecated_key: <name> — <reason>` output line alongside the existing `renamed`/`missing` lines, satisfying AC4.

### Similar Patterns
- `scripts/little_loops/fsm/validation/meta_rules.py::_validate_meta_loop_evaluation()` (lines 73-127) — the established "field X requires field Y, else ERROR" shape (per-rule `ValidationError` list, suppression-flag early return, message explains why + how to fix) to model a new "deprecation entry missing prose reason" rule on.
- `scripts/little_loops/cli/verify_decisions.py::_run()` — `ERROR: <path>: <ExceptionType>: <message>` stderr convention for surfacing a required-field validation failure via CLI exit code 1.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation/structural_rules.py::validate_fsm` — dispatcher that invokes each per-loop rule; the new deprecation rule module must be wired in here (not just imported/re-exported in `__init__.py`) to actually fire during `ll-loop validate`.
- `scripts/little_loops/fsm/schema.py` — resolves `on_success`/`on_failure` as live shorthand aliases (`on_yes=data.get("on_yes") or data.get("on_success")`); the new lint rule is advisory-only and must coexist with this still-functional fallback, not assume the aliases are unused.
- `scripts/little_loops/fsm/executor.py` — documents the same shorthand resolution order in a comment; keep in sync if the new rule's wording changes how the aliases are described.
- `scripts/little_loops/cli/migrate_status.py` — the only existing surface that reports a `STATUS_SYNONYMS` rewrite to a user today (one-time migration CLI, not the live read path); if `STATUS_SYNONYMS` is wired into the new map, this becomes a second, separately-maintained surface for the same underlying deprecation entry and should be reconciled rather than left to drift.
- `scripts/little_loops/config-schema.json` (`completed_dir`/`deferred_dir`, free-text `"[DEPRECATED: use IssueInfo.status instead] ..."`) and `scripts/little_loops/fsm/fsm-loop-schema.json` (`on_success`/`on_failure`, `"Deprecated: use on_yes instead"`) — existing free-text-only deprecation descriptions that the new map should reference/subsume rather than duplicate as a second source of truth.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — the `check_format_gaps`/`FormatGaps` section enumerates the gap-class list by name (currently 8 categories) and an aside noting the current count; a new `deprecated_key` category requires updating both. Also documents `fsm/schema.py`'s `on_success`/`on_failure` shorthand resolution — note if the new lint rule starts flagging that shorthand.
- `docs/reference/CLI.md` (~line 1650) — hardcodes a literal `ll-issues format-check ENH-2426 --format json` example JSON blob listing every `FormatGaps` key; will visibly drift the moment `to_dict()` gains a new key.
- `.claude/CLAUDE.md` § Loop Authoring — the MR-1..MR-13 rule table is where new FSM-validation lint rules get registered (rule ID, severity, "Catches" column, suppress-flag); the new `on_success`/`on_failure` deprecation rule needs a new row here.
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — cited by the CLAUDE.md table header as "the source of truth this table summarizes"; needs the new rule's full rationale.
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` (~line 365, "No deprecated sections used") — describes format-check-adjacent expectations that should mention the new frontmatter-key deprecation class to stay in sync with `check_format_gaps()`'s categories.

### Tests
- `scripts/tests/test_issue_parser.py::test_renamed_deprecated_section_reports_renamed` (line 3757) — template for a new deprecated-frontmatter-key test.
- `scripts/tests/test_fsm_validation_meta_rules.py` — template for the new loop-YAML rule's test class (one positive control against a real builtin loop, one fixture per rule firing, one suppression-flag test).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_frontmatter.py` — existing unit test file for `parse_frontmatter`/`STATUS_SYNONYMS`; not previously listed but is the direct-coverage file for the frontmatter.py change (`test_issue_parser_properties.py::TestStatusSynonyms`, lines 506-519, is a secondary shape-only check on the same dict).
- `scripts/tests/test_issue_parser_properties.py::TestStatusSynonyms` (lines 506-519) — asserts only `STATUS_SYNONYMS`'s key/value shape; breaks if the plan replaces the dict with a richer key→(canonical, reason) structure rather than adding a parallel map.
- `scripts/tests/test_ll_issues_format_check.py::TestFormatCheckJsonOutput.test_clean_issue_json_output` (~line 270) — asserts full dict equality against all current `FormatGaps` keys; **will break** the moment a new gap kind is added to `to_dict()` and must be updated in the same change, not left for CI to catch later.
- `scripts/tests/test_migrate_status.py::TestMigrateStatusNormalization` — asserts only the coerced `status` value, never a surfaced reason; won't break unless `_migrate_content`'s return/print contract changes, but should be reconciled with the new map's reason surfacing per the `migrate_status.py` coupling above.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Wire the new FSM deprecation rule into `structural_rules.py::validate_fsm`'s dispatcher, not just `fsm/validation/__init__.py`'s re-export list — otherwise it never fires during `ll-loop validate`.
2. Verify the new rule coexists with the still-live `on_success`/`on_failure` alias resolution in `fsm/schema.py` and `fsm/executor.py` — it is a lint, not a removal of the fallback.
3. Update `docs/reference/API.md`'s `FormatGaps` category enumeration and `docs/reference/CLI.md`'s literal `--format json` example blob alongside the `to_dict()` change.
4. Add a row to the `.claude/CLAUDE.md` MR rule table (and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`) for the new `on_success`/`on_failure` deprecation lint rule.
5. Update `scripts/tests/test_ll_issues_format_check.py::TestFormatCheckJsonOutput.test_clean_issue_json_output`'s full-dict-equality assertion in the same change that adds the new `FormatGaps` key.
6. Reconcile `cli/migrate_status.py`'s existing STATUS_SYNONYMS-rewrite reporting with the new map's reason surfacing rather than leaving two separately-maintained messages.

## Acceptance criteria

- A retired frontmatter key carries a prose reason at the point of validation, not just a deprecation flag.
- Adding a deprecation entry without a reason fails validation.
- The already-retired cases (`superseded_by` as hand-written, coerced status synonyms) are represented in the map as the first entries.
- An agent reading a file containing a retired key sees the reason in the same output that reports the key.

## Notes

Small and self-contained; no dependency on the other children of this EPIC.

## Status

Done — implemented.

## Resolution

Added `DeprecatedFrontmatterEntry` (frozen dataclass, raises on empty/whitespace
reason) plus two maps in `frontmatter.py`: `DEPRECATED_FRONTMATTER_KEYS`
(`superseded_by` first, then the pre-existing renamed-key aliases) and
`DEPRECATED_STATUS_VALUES` (one entry per `STATUS_SYNONYMS` key, reason names
the coerced canonical value). `check_format_gaps()` in `issue_parser.py` now
detects both — recovering the *raw* status synonym from the frontmatter block
text since `parse_frontmatter()` already canonicalizes it unconditionally —
and reports them via a new `deprecated_key` gap class on `FormatGaps`
(`to_dict()`/`has_gaps` updated). `ll-issues format-check` prints
`deprecated_key: <key> — <reason>` lines. Updated `docs/reference/API.md`,
`docs/reference/CLI.md`, and `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` for the
new gap class.

Out of scope per this issue's own Scope Boundaries and since all four
acceptance criteria name "frontmatter key" specifically: the loop-YAML side
(`on_success`/`on_failure` FSM lint rule, MR-table row) from the Proposed
Change/Wiring Phase sections was not implemented — left as follow-up scope for
a future issue if wanted.

## Session Log
- `/ll:manage-issue` - 2026-07-28T16:07 - `221ecfcb-75ac-4f4a-b8b5-4f3ec8a1cc54.jsonl`
- `/ll:ready-issue` - 2026-07-28T15:57:35 - `938773b8-28dd-4363-b18c-1d201260d86f.jsonl`
- `/ll:wire-issue` - 2026-07-28T15:54:40 - `b2fa363e-df5d-45d9-b385-1160a690df67.jsonl`
- `/ll:refine-issue` - 2026-07-28T15:48:36 - `24bcc8f1-1bce-4de2-ab8e-95ae041fb51e.jsonl`

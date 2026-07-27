---
id: FEAT-2849
type: FEAT
priority: P2
status: done
parent: FEAT-2846
completed_at: '2026-07-27T03:39:07Z'
discovered_date: 2026-07-26
discovered_by: issue-size-review
labels:
- issues-cli
- dependency-graph
- linting
relates_to:
- FEAT-2842
- BUG-2848
confidence_score: 100
outcome_confidence: 80
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 20
---

# FEAT-2849: Prose dependency extractor + format-check gap taxonomy + skill wiring

## Summary

Add the shared prose-dependency extractor and wire it into
`check_format_gaps()`'s existing taxonomy as two new gap kinds
(`prose_dep_drift`, `stale_prose_dep`), then update `ll-issues format-check`
output and the refine/ready/wire skills to treat `prose_dep_drift` as a
blocking gap. This is the core detection mechanism; decomposed from
FEAT-2846.

## Parent Issue

Decomposed from FEAT-2846: Detect prose dependency claims that are missing
from frontmatter. Covers Implementation Steps 1, 2, 3, and 5 of the parent.

## Current Behavior

`DependencyGraph.from_issues()` (`dependency_graph.py:56-146`) reads only
structured frontmatter fields. Issue bodies routinely state dependencies in
prose ("Depends on FEAT-109") that never reach `blocked_by:`, so the
sequencer schedules blocked work as unblocked. See parent issue for the
9-issue drift probe in this repo.

## Expected Behavior

1. **`little_loops/issues/prose_deps.py`** — `extract_prose_deps(body) ->
   set[str]`. Frontmatter- and code-fence-aware (reuse `_CODE_FENCE` from
   `text_utils.py` and the fence-skipping pattern in
   `issues/anchor_sweep.py::_sweep_file()`). Canonical phrasings only:
   `Depends on <ID>`, `Blocked by <ID>`, `## Blocked By` section bodies,
   `Requires <ID>`. Strips `P\d-` prefixes and normalizes case. Deliberately
   conservative — recall matters less than not crying wolf.
2. Extend `check_format_gaps()` (`issue_parser.py:191-283`) and the
   `FormatGaps` dataclass (`issue_parser.py:136-165`) with:
   - `prose_dep_drift` — prose names an **active** issue absent from
     `blocked_by`/`depends_on`.
   - `stale_prose_dep` — prose names a `done`/`cancelled` issue. Distinct
     code; the remedy is deleting stale text, not adding an edge.
   `check_format_gaps` has no backlog/status lookup today — add an optional
   `issue_statuses: dict[str, str] | None` parameter (fails open when
   absent, matching this module's existing convention) for the status check
   `stale_prose_dep` needs.
3. Extend `cmd_format_check()` (`cli/issues/format_check.py:35-73`) text and
   `--json` rendering for the two new gap kinds. The taxonomy string is
   hardcoded twice in this file — the subparser `help=` (lines 19-20) and
   the `cmd_format_check()` docstring (line 36) — both need updating.
4. Wire `/ll:refine-issue`, `/ll:ready-issue`, `/ll:wire-issue` to call
   `format-check` and treat `prose_dep_drift` as blocking.
   `commands/ready-issue.md` (lines 214-221, outcome logic at 297/305) has
   its own independent `## Blocked By` prose check today — reconcile it with
   (not just supplement it with) the new `format-check` gap rather than
   running two parallel checks.

The converse case must not become a false positive: an issue whose prose
"Blocked By" section names an issue that has since shipped — that's what
`stale_prose_dep` is for.

## Root Cause

Issue templates and authoring skills accept prose dependency statements
without requiring the structured mirror, and no read path reconciles the
two.

## Integration Map

### Files to Modify
- `scripts/little_loops/issues/prose_deps.py` — **NEW**:
  `extract_prose_deps(body) -> set[str]`
- `scripts/little_loops/issue_parser.py:136-165,191-283` — extend
  `FormatGaps` dataclass and `check_format_gaps()`
- `scripts/little_loops/cli/issues/format_check.py:19-20,35-73` — extend
  `cmd_format_check()` text/JSON rendering and both hardcoded taxonomy
  strings
- `commands/refine-issue.md`, `commands/ready-issue.md`,
  `skills/wire-issue/SKILL.md` — wire to call `format-check` / treat
  `prose_dep_drift` as blocking
- `scripts/little_loops/cli/issues/__init__.py:104` — **Wiring pass added by
  `/ll:wire-issue`:** a third hardcoded taxonomy-summary string (the
  `format-check` subparser's top-level `add_parser(..., help=...)` in this
  file, distinct from `format_check.py`'s own subparser `help=` and
  docstring). Already stale re: `malformed_id` today, so it needs both a
  backfill and the two new gap kinds.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/dependency_graph.py:56-146` —
  `DependencyGraph.from_issues()`, the consumer this feature ultimately
  protects; needs no code change itself
- `commands/ready-issue.md:214-221,297,305` — independent `## Blocked By`
  prose check today, not routed through `ll-issues format-check`; needs
  explicit reconciliation
- `scripts/little_loops/cli/issues/__init__.py:53-56` — registers
  `cmd_format_check`/`add_format_check_parser`; confirms
  `check_format_gaps()`'s only production import chain runs through this
  file → `format_check.py` (single production call site:
  `format_check.py:51`)
- `scripts/tests/test_issue_parser_unresolved.py:245` — imports
  `FormatGaps` directly as the second production-tree importer; check
  whether it instantiates `FormatGaps()` positionally before adding new
  dataclass fields
- `scripts/tests/test_ready_issue_lint.py` — ready-issue's prose "Blocked
  By" lint tests; needs updates once `ready-issue.md`'s independent check
  is reconciled with `format-check`'s `prose_dep_drift`
- `scripts/tests/test_issue_parser.py:3719-3838`
  (`TestFormatGradedChecker`) — the 7 direct `check_format_gaps(...)` call
  sites (lines 3734,3752,3772,3792,3811,3829,3837) are safe from a
  `TypeError` only if the new `issue_statuses` param defaults to `None`.
  Each also asserts `has_gaps is False` on a clean fixture — stays correct
  only if that fixture body has no prose dependency phrasing.
- `scripts/little_loops/loops/rn-remediate.yaml:98-131` — **Wiring pass
  added by `/ll:wire-issue`:** the `ensure_formatted` FSM gate shells out to
  `ll-issues format-check "$ID"` and only branches on exit code, then routes
  to `/ll:format-issue` on failure (fail-open per ENH-2426). No code change
  needed, but confirm the two new gap kinds don't flip this gate's exit code
  for issues that previously passed (a `prose_dep_drift`/`stale_prose_dep`
  finding should not silently start blocking this remediation loop unless
  that's an intended side effect).

### Similar Patterns
- `scripts/little_loops/issues/anchor_sweep.py` — `_sweep_file()`: fence-span
  skip via `_CODE_FENCE` (`text_utils.py`); frontmatter is not
  regex-skipped in this module — a prose scanner should call
  `little_loops.frontmatter.parse_frontmatter()` first and scan only the
  body portion

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`parse_frontmatter()` alone does not isolate the body**: it returns only
  the frontmatter `dict[str, Any]` (`frontmatter.py:30-95`). The body-only
  text `extract_prose_deps()` needs to scan comes from the sibling function
  `strip_frontmatter(content: str) -> str` (`frontmatter.py:220-240`). Pair
  both calls — `parse_frontmatter()` for any existing `blocked_by`/
  `depends_on` structured fields, `strip_frontmatter()` for the text to
  regex-scan — rather than assuming one call does both.
- **The `_CODE_FENCE` fence-span-skip idiom (precompute spans, then an
  `_in_fence(start, end)` containment check) is duplicated three times**,
  not just once: `anchor_sweep.py:_sweep_file()`,
  `hooks/sweep_stale_refs.py` (imports the same `text_utils._CODE_FENCE`),
  and `dependency_mapper/analysis.py:28` (which independently redefines an
  identical `_CODE_FENCE` regex rather than importing it, and strips fences
  via `.sub("", content)` instead of the span-skip approach). The new
  extractor should import `text_utils._CODE_FENCE` and follow the
  span-skip idiom (matches `anchor_sweep.py`), not add a fourth
  independent regex copy.
- **ID normalization precedent already exists in two places** worth
  modeling directly: `issue_parser.py`'s own `malformed_id` gap
  (`check_format_gaps()` lines 274-281, strip + `.upper()` + compare to
  `_FILENAME_ID_RE`-derived canonical `TYPE-NNN`), and
  `cli/issues/show.py:_resolve_issue_id()` (lines 40-150), which handles
  the `P\d-TYPE-NNN` / `TYPE-NNN` / bare-numeric input forms via three
  fallback regexes. Either is a closer match for "strip `P\d-` prefix,
  normalize case" than writing new normalization logic from scratch.
- `scripts/little_loops/issue_parser.py:168-188` — `QuestionGaps`
  dataclass, documented as a "mirror" of `FormatGaps`'s shape — confirms
  the new gap kinds should follow the same two-field convention

### Tests
- `scripts/tests/test_ll_issues_format_check.py` — existing format-check
  tests; inline fixture-string convention, `format_check_dir` fixture,
  in-process `_invoke()` helper — model for the new gap-kind tests
- `scripts/tests/test_issue_parser.py` — `check_format_gaps`/`FormatGaps`
  unit tests
- **New test module needed** for `extract_prose_deps()`: fenced code
  containing `Depends on FEAT-1`, `P2-FEAT-109` prefix forms, `## Blocked
  By` sections, self-references, and IDs inside link targets — no existing
  end-to-end scanner test to copy (only `resolve_anchor()` is
  unit-tested, in `test_issues_anchors.py`)

### Tests (Wiring Phase)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_format_check.py::TestFormatCheckJsonOutput::test_clean_issue_json_output`
  (line ~246-270) — asserts **exact dict equality** on `--format json`
  output: `{"missing": [], "renamed": [], "empty": [], "boilerplate": [],
  "malformed_id": []}`. This is a distinct break site from the
  `test_issue_parser.py` unit tests already listed — it will fail with
  "unexpected keys" the moment `FormatGaps.to_dict()` gains
  `prose_dep_drift`/`stale_prose_dep`, even if the `issue_parser.py`-level
  tests are all updated. Must add the two new keys to this literal.
- `scripts/tests/test_ready_issue_lint.py::TestReadyIssueLintRule` — despite
  its name, this class does **not** test `## Blocked By` prose parsing; it
  reuses `anchor_sweep`'s `_CODE_FENCE`/`_FILE_LINE` regex to test an
  unrelated file:line-reference lint rule (ENH-1300). There is currently no
  test file that exercises `ready-issue.md`'s actual inline "Blocked By"
  prose check — the reconciliation work in Implementation Step 4 has no
  existing test to update and will need a new one (or confirmation the
  check has no dedicated test today).
- New test module for `extract_prose_deps()` (per Implementation Step 1)
  should follow `test_ready_issue_lint.py`'s fixture shape — module-level
  `CLEAN_ISSUE`/`CONTAMINATED_ISSUE`-style triple-quoted fixture strings
  plus a dedicated fence-skip test with a minimal fenced-code fixture —
  rather than inventing a new fixture convention.

### Documentation
- `docs/reference/CLI.md:1611` — taxonomy prose sentence ("reports gaps in
  five classes...") needs the two new classes appended
- `docs/reference/CLI.md:1621` — separate hardcoded `--format json` example
  showing the five-key JSON shape — a second, distinct edit site
- `docs/reference/API.md:843` — `check_format_gaps()` signature line;
  update for the new `issue_statuses` param
- `docs/reference/API.md:848-853` — five gap-class bullets; add
  `prose_dep_drift`/`stale_prose_dep`
- `docs/reference/API.md:859` — fail-open behavior sentence; fold in the
  new gap kinds' fail-open semantics
- `docs/reference/API.md:932-934` — **Wiring pass added by
  `/ll:wire-issue`:** `QuestionGaps` doc prose describes it as "mirroring
  the `FormatGaps` shape" / "Companion to `FormatGaps`" — check this
  cross-reference doesn't go stale once `FormatGaps` grows two fields that
  `QuestionGaps` doesn't mirror.
- `skills/decide-issue/SKILL.md:480-484` — **Wiring pass added by
  `/ll:wire-issue`:** documents `ll-issues format-check` as the precedent
  CLI-evaluator contract (ENH-2426) for `check-decidable`; prose reference
  only, but confirm it still reads accurately once the taxonomy grows to 7
  gap kinds.

## Implementation Steps

1. Write `prose_deps.py` with the extractor and a test corpus covering:
   fenced code containing `Depends on FEAT-1`, `P2-FEAT-109` prefix forms,
   `## Blocked By` sections, self-references, and IDs inside link targets.
2. Extend `check_format_gaps()` with the two new gap kinds; thread
   `issue_statuses` in.
3. Extend `ll-issues format-check` text and `--json` output.
4. Update `/ll:refine-issue`, `/ll:ready-issue`, `/ll:wire-issue` to call it
   and treat `prose_dep_drift` as blocking; reconcile `ready-issue.md`'s
   existing inline prose check with the new gap rather than running both.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included
in the implementation:_

5. Update `scripts/little_loops/cli/issues/__init__.py:104`'s format-check
   subparser `help=` taxonomy string — a third hardcoded location beyond
   `format_check.py`'s subparser help and docstring, already stale re:
   `malformed_id`.
6. Update `test_ll_issues_format_check.py::TestFormatCheckJsonOutput::test_clean_issue_json_output`'s
   exact 5-key dict-equality assertion to include the two new gap-kind keys
   — a distinct break site from the `issue_parser.py` unit tests.
7. Confirm `rn-remediate.yaml`'s `ensure_formatted` gate (lines 98-131)
   doesn't unintentionally start blocking on `prose_dep_drift`/
   `stale_prose_dep` for issues that previously passed format-check.
8. Write (or confirm absence of) a dedicated test for `ready-issue.md`'s
   inline "Blocked By" prose check before reconciling it — no existing test
   file covers that check today (`test_ready_issue_lint.py` tests an
   unrelated file:line lint rule despite its name).

## Use Case

As someone planning the next work item, I run `ll-issues sequence` and trust
that an issue shown as unblocked really is — because any issue whose body
claims a dependency it never recorded was caught by `format-check` during
refinement and either wired up or corrected.

## Acceptance Criteria

- [ ] `extract_prose_deps()` ignores IDs inside fenced code blocks and
      inside frontmatter.
- [ ] An issue with `Depends on FEAT-109` in prose and no `blocked_by`
      reports `prose_dep_drift` from `ll-issues format-check`.
- [ ] An issue whose prose names a `done` issue reports `stale_prose_dep`,
      not `prose_dep_drift`.
- [ ] `/ll:ready-issue` treats `prose_dep_drift` as a blocking gap and no
      longer runs a separate, unreconciled inline "Blocked By" check.

## Impact

- **Users**: `ll-issues sequence`, `next-issue`, and wave planning stop
  scheduling work whose prerequisites are unfinished.
- **Risk**: Low-Medium. The extractor will have false positives; keeping it
  a reported gap rather than an ordering input bounds the blast radius.
- **Effort**: Medium.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/issues/anchor_sweep.py` | Fence-skipping body scanner to reuse |
| `scripts/little_loops/issue_parser.py` — `check_format_gaps` | Gap taxonomy to extend |
| `scripts/little_loops/dependency_graph.py:56-146` | Why prose is invisible today |

## Context

Decomposed from FEAT-2846 by `/ll:issue-size-review` (score 11/11, Very
Large) to separate the core detection mechanism from the repo-wide sweep
(FEAT-2850) and the optional `--fix` backfill (FEAT-2851).

## Session Log
- `/ll:manage-issue` - 2026-07-27T03:38:38 - `8818c1a3-5217-4762-85da-cb36834ac30a.jsonl`
- `/ll:confidence-check` - 2026-07-27T03:19:25 - `98024b74-d3d8-4caa-9e34-cc16c0a675e1.jsonl`
- `/ll:wire-issue` - 2026-07-27T03:18:02 - `d29e0241-f1fd-44b1-9494-b1c56374d2ef.jsonl`
- `/ll:refine-issue` - 2026-07-27T03:11:08 - `1bdb0f3c-5506-4282-b352-b8c12211b10c.jsonl`
- `/ll:issue-size-review` - 2026-07-26T00:00:00 - `52f8c37a-8768-4813-8704-c3364dbd6e28.jsonl`

---

## Status

open

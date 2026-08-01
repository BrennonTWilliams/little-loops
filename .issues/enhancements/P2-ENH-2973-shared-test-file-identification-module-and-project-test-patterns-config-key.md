---
id: ENH-2973
title: Shared test-file identification module and project.test_patterns config key
type: ENH
priority: P2
status: done
discovered_by: epic-review
discovered_date: 2026-07-27
completed_at: '2026-07-28T16:33:50Z'
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
- config
blocks:
- ENH-2853
- ENH-2854
confidence_score: 100
outcome_confidence: 82
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 22
---

# ENH-2973: Shared test-file identification module and `project.test_patterns` config key

## Summary

Both ENH-2853 (pre-patch test-failure check) and ENH-2854 (test-file tamper
guard) need to classify a repo path as "a test file," and both currently propose
introducing the same new `project.test_patterns` config key and the same shared
identification module as part of their own scope. That made each issue depend on
the other and produced a circular `blocked_by` edge in the epic.

Extract the shared substrate into one small, independently landable issue: the
config key, its per-project-type template defaults, and a single identification
module. ENH-2853 and ENH-2854 then both depend on this and on nothing from each
other.

## Current Behavior

ENH-2853 and ENH-2854 each independently propose the same `project.test_patterns`
config key and the same test-file identification module as part of their own
scope. That produced a circular `blocked_by` edge between them (each needs the
other's proposed substrate) and, left unresolved, risks two independently
authored glob lists drifting apart silently.

## Expected Behavior

The config key, its per-project-type template defaults, and a single
identification module land once, in this issue, ahead of both consumers.
ENH-2853 and ENH-2854 each depend only on this issue and can be implemented
independently of each other, with no risk of divergent test-file classification
logic.

## Motivation

A false negative in test-file identification (a test file the checks don't know
about) is the failure mode that matters for both consumers — it silently
disables the guard. Two independently-authored glob lists would drift, and
divergence would be invisible: each check would still report "clean."

Landing identification once, ahead of both consumers, also unblocks the epic's
stated sequencing (both verification children ship first, independently) instead
of forcing an arbitrary serial order between them.

## Proposed Change

1. **Config key** — add `project.test_patterns` (array of globs) to
   `scripts/little_loops/config-schema.json`'s `project` block, following the
   `scan.focus_dirs` array-of-globs shape. The block is
   `additionalProperties: false`, so the key must be declared there or config is
   rejected.
2. **Config dataclass** — add `test_patterns: list[str]` to `ProjectConfig`
   (`scripts/little_loops/config/core.py`, alongside `test_cmd`), exported via
   `BRConfig` and resolvable through `resolve_variable()`.
3. **Template defaults** — per-project-type default globs across the nine
   `scripts/little_loops/templates/*.json` project-type templates.
4. **Shared module** — `scripts/little_loops/test_file_patterns.py`: resolves
   `project.test_patterns` and matches paths via the existing gitignore-style
   matcher `_file_matches_pattern()` in
   `scripts/little_loops/git_operations.py`. Single public predicate plus a
   filter over a path list.

## Design Notes

- **`conftest.py` must be in every default pattern set.** ENH-2853's error
  -category false-negative hole depends on it: if `conftest.py` isn't classified
  as a test file, a fixture it adds is absent from the pre-patch tree and the
  candidate test errors for infrastructure reasons that read as legitimate
  evidence. This is a correctness requirement of the defaults, not a nicety.
- Not introspected by `init/introspect.py`. `_COMMAND_FIELDS` covers
  `test_cmd`/`lint_cmd`/`format_cmd`/`type_cmd` — commands declared in repo
  manifests. `test_patterns` is a glob list with no manifest source, so
  template defaults are the whole story. Document this as a deliberate omission
  so a reviewer doesn't read it as a gap.
- Match on repo-relative POSIX paths so behavior is identical on all platforms
  and matches how `git diff --name-only` emits paths (the form both consumers
  feed in).
- Pure and deterministic: no git calls, no filesystem stat, no LLM. Path in,
  bool out — so both consumers can unit-test their own logic against it
  trivially.
- `_file_matches_pattern()` is private to `git_operations.py`. Rather than a
  cross-module private import, promote it to a public name (e.g.
  `file_matches_pattern`, keeping the underscore name as an alias for existing
  in-module callers) as part of this issue.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **A third call site exists beyond `git_operations.py`'s own two internal
  uses**: `scripts/little_loops/codequery/codegraph.py:131,133` imports
  `_file_matches_pattern` via a **function-local import** inside
  `_is_scan_relevant()` specifically to isolate this cross-module private
  dependency. That local-import call site is a candidate to repoint at the
  new shared module (or the promoted public name) directly, since it already
  signals "this import is a workaround."
- `_file_matches_pattern(file_path: str, pattern: str) -> bool` at
  `git_operations.py:266-321` matches one path against one pattern string
  (callers loop over pattern lists themselves) and is negation-agnostic — it
  strips a leading `!` for matching purposes but never inspects it, so
  negation semantics stay the caller's responsibility. The new module's
  predicate should decide once whether negation in `test_patterns` entries
  is supported or explicitly out of scope.
- **`resolve_variable()` is the wrong read path for this list.**
  `config/core.py:887-909` implements `resolve_variable()` as a dot-path
  walker that special-cases lists by space-joining them into one string
  (`" ".join(str(v) for v in value)`). Reading `project.test_patterns`
  through `resolve_variable()` would collapse the glob list into a single
  joined string, destroying the individual patterns. `test_file_patterns.py`
  should read `ProjectConfig.test_patterns` directly (via `BRConfig.project`,
  `core.py:265-268`) rather than through `resolve_variable()`.
- `ProjectConfig` dataclass and its `from_dict()` hydration live at
  `config/core.py:142-171` (`test_cmd: str = "pytest"` is the sibling field
  at line ~149); the aggregator `BRConfig._parse_config()` constructs it at
  line 219, and `to_dict()`'s project block (lines 621-632) is the other
  place a new field must be listed for it to be visible to `resolve_variable()`
  callers of *other* project keys (moot for `test_patterns` itself per the
  point above, but still required for consistency/introspection tooling).
- `scan.focus_dirs`'s exact schema shape to mirror is
  `config-schema.json:661-675`: `{"type": "array", "description": ...,
  "items": {"type": "string"}, "default": [...]}`, inside the `scan` object;
  the `project` block's own properties start at `config-schema.json:12`.
- Exact schema-presence test template: `test_config_schema.py:337-357`,
  `test_health_url_in_schema()` — asserts key presence in
  `data["properties"]["project"]["properties"]`, asserts type, and asserts
  default, with the issue ID cited in both docstring and assertion message.
  `test_project_test_patterns_in_schema()` should follow this exactly.
- Test-style precedent for the new pure module:
  `test_work_verification.py:24-143` (`TestExcludedDirectories`,
  `TestFilterExcludedFiles`) is the closer template than
  `test_git_operations.py` (which mocks subprocess calls) — no mocking, one
  `TestX` class per constant/function, one behavior per test method, and an
  explicit "looks similar but isn't" case
  (`test_similar_but_not_excluded_paths`) directly analogous to the
  `pytest_history_plugin.py` AC case here.
- Confirmed via search: no other "is this a test file" classifier exists
  anywhere in `scripts/little_loops/` outside the unrelated Learning-Test-Registry
  concept in `issue_history/` — this module is genuinely new consolidation,
  not a rename of a scattered existing check.

## Scope Boundaries

- **In scope**: `project.test_patterns` config key, `ProjectConfig` field,
  per-project-type template defaults, `test_file_patterns.py` module, and
  promoting `_file_matches_pattern()` to a public name.
- **Out of scope**: Wiring the module into ENH-2853's pre-patch check or
  ENH-2854's tamper guard — those consumers wire it in their own scope.

## Impact

- **Priority**: P2 - Blocks two verification-hardening issues (ENH-2853,
  ENH-2854); not itself user-facing but on the critical path for EPIC-2856's
  rework-reduction goal.
- **Effort**: Small - One new pure module, one config key with per-template
  defaults, and a promoted-to-public matcher function; no consumer wiring is in
  this issue's scope.
- **Risk**: Low - Purely additive (new config key + new module); no existing
  behavior changes, and `_file_matches_pattern()` keeps its private alias for
  existing in-module callers.
- **Breaking Change**: No

## Acceptance Criteria

- [x] `project.test_patterns` is declared in `config-schema.json`'s `project`
      block as an array of strings with a default, and a config carrying it
      validates.
- [x] `ProjectConfig.test_patterns` exists alongside `test_cmd` and resolves via
      `resolve_variable("project.test_patterns")`.
- [x] All nine project-type templates carry a language-appropriate default.
- [x] Every default pattern set includes `conftest.py` (or the ecosystem's
      equivalent shared-fixture file where one exists).
- [x] `scripts/little_loops/test_file_patterns.py` exposes a single
      identification predicate and a list filter, both pure and LLM-free.
- [x] Matching uses `git_operations`' existing gitignore-style matcher rather
      than a second glob implementation, and the matcher is promoted to a
      public name instead of being imported under its private `_`-prefixed one.
- [x] Paths are matched repo-relative and POSIX-normalized.
- [x] Tests cover: each template's default set, `conftest.py` classification,
      a non-test file that superficially resembles one (e.g.
      `scripts/little_loops/pytest_history_plugin.py`), and path normalization.
- [x] `docs/reference/CONFIGURATION.md`'s `### project` table gains a
      `test_patterns` row, noting the deliberate non-introspection.

## Integration Map

### Files to Modify
- `scripts/little_loops/config-schema.json` — `project` block; follow
  `scan.focus_dirs`'s array-of-globs shape
- `scripts/little_loops/config/core.py` — `ProjectConfig` (`test_cmd` is the
  sibling field), `BRConfig` export, `resolve_variable()`
- `scripts/little_loops/templates/*.json` — nine project-type templates
- `docs/reference/CONFIGURATION.md` — `### project` key/default/description
  table

### New Files
- `scripts/little_loops/test_file_patterns.py`

### Similar Patterns
- `scripts/little_loops/git_operations.py:_file_matches_pattern()`
  (lines 266-321) — the gitignore-style matcher to wrap rather than
  reimplement; existing internal call sites at lines 345 and 413
- `scripts/little_loops/codequery/codegraph.py:131,133` — a third,
  cross-module call site (`_is_scan_relevant()`, function-local import) worth
  repointing at the promoted public name or the new module directly
- `scripts/little_loops/work_verification.py:filter_excluded_files()` /
  `EXCLUDED_DIRECTORIES` (lines 18-41) — the closest existing "classify
  changed files" precedent; this module is its structural inverse (inclusion
  predicate)
- `scripts/tests/test_config_schema.py:test_health_url_in_schema()`
  (lines 337-357) — exact template for a new `project.*` schema-presence test
- `scripts/tests/test_work_verification.py:24-143` — test-style template for
  the new pure module (no mocking, one class per constant/function)

### Tests
- `scripts/tests/test_config_schema.py` — new `test_project_test_patterns_in_schema`
  following the one-test-per-key convention (mirror `test_health_url_in_schema`,
  lines 337-357; membership-style assertion, not exhaustive key-set)
- `scripts/tests/test_config.py` — `TestProjectConfig::test_from_dict_with_all_fields`
  and `::test_from_dict_with_defaults` (~L101-141) need `test_patterns` parity
  with `test_cmd`
- New `scripts/tests/test_test_file_patterns.py`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_gitignore_suggestions.py` — imports `_file_matches_pattern`
  by its private name (line 12) and asserts against it at lines 114, 285,
  287-289, 411-413. Only breaks if the promotion drops the private alias
  instead of keeping it (as the issue's Design Notes already specify) —
  confirm the alias is kept so this test needs no changes. [Agent 3 finding]
- `scripts/little_loops/codequery/codegraph.py:_is_scan_relevant()` (line 131,
  the function-local import) has zero direct test coverage anywhere in
  `scripts/tests/` — repointing it to the promoted public name is a pure
  coverage gap, not a regression risk, and needs no existing test update.
  [Agent 3 finding]
- `scripts/tests/test_init_core.py::TestTemplateCommandOptions` (lines
  2706-2735) — uses membership (`in`) checks over `_meta.command_options`,
  not exhaustive key-set equality, so adding `test_patterns` to all nine
  templates will not break this class; optionally extend it with a new
  parametrized assertion for `test_patterns` presence, following the same
  `TYPED_TEMPLATES` + `templates_dir` fixture pattern (fixture at line 59-61).
  [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:394-398` — a `ProjectConfig` dataclass code-block
  excerpt (`name`, `src_dir`, `test_dir`, `test_cmd`, `lint_cmd`, `type_cmd`)
  will drift out of sync with the real dataclass unless `test_patterns` is
  added to the excerpt. [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:307-310` — prose note lists which project
  keys are introspected on fresh `ll-init` (`src_dir`/`test_cmd`/`lint_cmd`/
  `format_cmd`/`type_cmd`/`scan.focus_dirs`); consider an explicit
  "not introspected" callout for `test_patterns` here so a reader doesn't
  read its absence as an oversight (the Design Notes already document this
  as deliberate, but this is the doc location a reader would actually
  check). [Agent 2 finding]

### Consumers (this issue blocks both)
- `ENH-2853` — pre-patch test-failure check
- `ENH-2854` — test-file tamper guard

## Status

**Open** | Created: 2026-07-27 | Priority: P2


## Session Log
- `/ll:manage-issue improve` - 2026-07-28T16:33:06 - `e4c5794d-4e37-4171-bea5-2b2eca6982ee.jsonl`
- `/ll:confidence-check` - 2026-07-28T00:00:00 - `89cb51b2-4a20-4e90-b654-857c039570e9.jsonl`
- `/ll:wire-issue` - 2026-07-28T16:18:39 - `5106e362-24eb-4783-8217-bdbd22e2c26d.jsonl`
- `/ll:refine-issue` - 2026-07-28T16:13:05 - `23c9adb4-eaf1-486a-b3a9-0b03f0bd32af.jsonl`
- `/ll:format-issue` - 2026-07-27T20:01:56 - `74d428f0-7103-4a58-9168-ff504878fb04.jsonl`

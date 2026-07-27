---
id: ENH-2865
title: Shared test-file identification module and project.test_patterns config key
type: ENH
priority: P2
status: open
discovered_by: epic-review
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
- config
blocks:
- ENH-2853
- ENH-2854
---

# ENH-2865: Shared test-file identification module and `project.test_patterns` config key

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

## Acceptance Criteria

- [ ] `project.test_patterns` is declared in `config-schema.json`'s `project`
      block as an array of strings with a default, and a config carrying it
      validates.
- [ ] `ProjectConfig.test_patterns` exists alongside `test_cmd` and resolves via
      `resolve_variable("project.test_patterns")`.
- [ ] All nine project-type templates carry a language-appropriate default.
- [ ] Every default pattern set includes `conftest.py` (or the ecosystem's
      equivalent shared-fixture file where one exists).
- [ ] `scripts/little_loops/test_file_patterns.py` exposes a single
      identification predicate and a list filter, both pure and LLM-free.
- [ ] Matching uses `git_operations._file_matches_pattern()` rather than a
      second glob implementation.
- [ ] Paths are matched repo-relative and POSIX-normalized.
- [ ] Tests cover: each template's default set, `conftest.py` classification,
      a non-test file that superficially resembles one (e.g.
      `scripts/little_loops/pytest_history_plugin.py`), and path normalization.
- [ ] `docs/reference/CONFIGURATION.md`'s `### project` table gains a
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
- `scripts/little_loops/git_operations.py:_file_matches_pattern()` — the
  gitignore-style matcher to wrap rather than reimplement
- `scripts/little_loops/work_verification.py:filter_excluded_files()` /
  `EXCLUDED_DIRECTORIES` — the closest existing "classify changed files"
  precedent; this module is its structural inverse (inclusion predicate)
- `scripts/tests/test_config_schema.py:test_health_url_in_schema()` — exact
  template for a new `project.*` schema-presence test

### Tests
- `scripts/tests/test_config_schema.py` — new `test_project_test_patterns_in_schema`
  following the one-test-per-key convention
- `scripts/tests/test_config.py` — `ProjectConfig` fixtures (~L107, L120, L135)
  need `test_patterns` parity with `test_cmd`
- New `scripts/tests/test_test_file_patterns.py`

### Consumers (this issue blocks both)
- `ENH-2853` — pre-patch test-failure check
- `ENH-2854` — test-file tamper guard

## Status

**Open** | Created: 2026-07-27 | Priority: P2

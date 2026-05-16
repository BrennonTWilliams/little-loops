---
discovered_date: 2026-04-16
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
size: Very Large
---

# ENH-1123: Configurable ll-issues next-issue Selection Behavior

## Summary

`ll-issues next-issue` currently uses a hardcoded sort key to pick the top active issue. There is no configuration surface in `config-schema.json` or `.ll/ll-config.json` to change the selection strategy, so projects that prefer priority-first ordering, different tie-breakers, or alternative signals must patch Python source.

## Current Behavior

At `scripts/little_loops/cli/issues/next_issue.py:33-39`, issues are sorted by a fixed tuple:

```python
issues.sort(
    key=lambda i: (
        -(i.outcome_confidence if i.outcome_confidence is not None else -1),
        -(i.confidence_score if i.confidence_score is not None else -1),
        i.priority_int,
    )
)
```

`config-schema.json` exposes `issues.priorities` (the allowed priority list) but has no `issues.next_issue` section. The only user-facing controls are the `--skip`, `--json`, and `--path` CLI flags.

## Expected Behavior

`.ll/ll-config.json` should support a `issues.next_issue` block that lets projects:

- choose an ordered list of sort keys (e.g., `priority`, `outcome_confidence`, `confidence_score`, `age`, `size`)
- set direction per key (asc/desc)
- optionally preset a named strategy (e.g., `"priority_first"`, `"confidence_first"` — current default)

The CLI continues to accept the existing flags; config provides the default when no flag overrides it.

## Motivation

Teams working in strict priority order (P0 before anything else) currently get surprised when a P3 issue with high outcome_confidence is returned ahead of an unready P1. Forcing a code edit to change this is a poor fit for a per-project workflow toolkit whose other selection knobs (priorities list, categories, duplicate thresholds) are already config-driven. One schema addition unblocks several downstream adopters without changing default behavior.

## Proposed Solution

1. Extend `config-schema.json` under `issues` with a `next_issue` object:
   - `strategy`: enum of named presets (default `"confidence_first"` preserves today's behavior)
   - `sort_keys`: array of `{key, direction}` objects for custom ordering (overrides `strategy` when present)
2. Add a resolver in `scripts/little_loops/config/features.py` (alongside `IssuesConfig` / `DuplicateDetectionConfig`) that turns the config into a sort-key function. Note: config is a package (`scripts/little_loops/config/`), not a single module — the original "`little_loops/config.py`" reference is stale.
3. Replace the hardcoded lambda in `cli/issues/next_issue.py:33-39` AND the byte-identical block in `cli/issues/next_issues.py:31-37` with that resolver, defaulting to the `confidence_first` preset when config is absent.
4. Validate unknown keys/strategies up front and surface a clear config error. Today the config layer silently accepts unknown keys (every `from_dict` uses `data.get(...)` with defaults) — this enhancement must introduce the first validating `from_dict`. Raise `ValueError` in `NextIssueConfig.from_dict` and let it propagate to the CLI's top-level error handler (mirror `cli/loop/run.py:46-48` which catches `ValueError` → `logger.error` → `return 1`).

Keep `--skip`, `--json`, `--path` unchanged. Consider a future `--strategy` CLI flag for one-off overrides, but that can be a follow-up.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Strong reuse candidate**: `scripts/little_loops/cli/issues/search.py:135-178` already implements `_sort_issues(items, sort_field, descending)` with string-dispatched sort fields (`priority`, `confidence`, `outcome`, plus fallback). The new resolver should either share this helper or be modelled on it directly.
- **Sortable IssueInfo fields available** (`scripts/little_loops/issue_parser.py:202-310`): `outcome_confidence` (int|None), `confidence_score` (int|None), `priority_int` (int property, line 251 — returns `99` for unknown), `priority` (str), `effort` (int|None, 1-3), `impact` (int|None, 1-3), `size` (str|None — no canonical int form), and four `score_*` sub-scores (`score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface`, each 0-25).
- **`age` is NOT a field on IssueInfo** — would require `path.stat().st_mtime` at sort time. Defer (Scope Boundaries already covers this).
- **None-handling divergence to resolve**: current `next_issue.py` lambda treats `None` as `-1` (sorts last after negation); `search.py` uses `9999` (sorts last in ascending). Pick one convention for the resolver and document it.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/next_issue.py:33-39` — replace hardcoded sort tuple with config-driven resolver call
- `scripts/little_loops/cli/issues/next_issues.py:31-37` — replace byte-identical sort tuple with the same resolver call
- `scripts/little_loops/config/features.py` — add `NextIssueConfig` dataclass next to `DuplicateDetectionConfig` (lines 43-56) and `IssuesConfig` (line 73); wire `next_issue: NextIssueConfig` field via `IssuesConfig.from_dict`. (Path correction: project uses a config **package**, not a single `config.py`.)
- `scripts/little_loops/config/__init__.py` — add `NextIssueConfig` to import block (~line 31) and `__all__` (~line 45)
- `config-schema.json` — add `issues.next_issue` block with `strategy` (enum) and `sort_keys` (array) properties; model after `issues.duplicate_detection` at lines 126-146
- `docs/reference/API.md` — document new config keys; CLI reference for `ll-issues next-issue` lives at lines 2953-3015
- `docs/reference/CLI.md:522-537` — sister CLI reference; keep in sync if behavior description changes

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py` — registers `next-issue` and `next-issues` subcommands; verify no assumptions about sort order
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:26` — shells out to `ll-issues next-issue`
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:31,33` — shells out to `ll-issues next-issue --skip`
- `scripts/little_loops/loops/lib/cli.yaml:55` — reusable `ll-issues next-issue` fragment (`ll_issues_next_issue`) shared across loops; documented in `docs/guides/LOOPS_GUIDE.md:2052`
- ~~`sprint-refine-and-implement.yaml`~~ — does NOT directly invoke `ll-issues next-issue`; sprint loops use their own ordering. Removed from prior listing.

### Similar Patterns
- `scripts/little_loops/cli/issues/search.py:135-178` — `_sort_issues(items, sort_field, descending)` is the closest existing template: string-dispatched multi-field sort with None-handling and a fallback. The new resolver should reuse or directly model on this helper.
- `scripts/little_loops/config/features.py:43-56` — `DuplicateDetectionConfig` is the canonical `@dataclass` + `@classmethod from_dict` pattern; mirror its shape for `NextIssueConfig`.
- `scripts/little_loops/config/automation.py:161-222` — `DependencyMappingConfig` shows nested-dataclass composition (it holds a `ScoringWeightsConfig` built via `ScoringWeightsConfig.from_dict(data.get(...))`). Use this if `sort_keys` items become their own dataclass.
- `scripts/little_loops/config/core.py:95-115` — `BRConfig._parse_config` shows how new top-level config sub-objects get wired in; not needed for `next_issue` (nested under existing `issues`) but worth referencing.
- Validation prior art: `scripts/little_loops/issue_template.py:68-69` (`raise ValueError(f"Unknown creation variant: {variant!r}")`) and `scripts/little_loops/fsm/evaluators.py:836` (unknown evaluator type) — same `ValueError` shape to use for unknown strategies / sort keys.

### Tests
- `scripts/tests/test_next_issue.py` — existing coverage for `next-issue`; extend with strategy / sort_keys cases
- `scripts/tests/test_next_issues.py` — existing coverage for plural variant; mirror new tests
- `scripts/tests/test_config.py`, `scripts/tests/test_config_schema.py` — extend with `NextIssueConfig` parsing and schema validation
- `scripts/tests/test_priority_queue.py` — sort/priority test patterns to model after
- **Test harness pattern** (`scripts/tests/conftest.py:55-121`): use `temp_project_dir` + `sample_config` fixtures, write config via `_write_config(temp_project_dir, sample_config)`, invoke CLI with `patch.object(sys, "argv", ["ll-issues", "next-issue", "--config", str(temp_project_dir)])` then `from little_loops.cli import main_issues; main_issues()`.
- Required cases: (a) no-config baseline matches today's hardcoded order (regression guard); (b) each named preset (`confidence_first`, `priority_first`, …); (c) custom `sort_keys` override; (d) validation error for unknown strategy and unknown sort key field.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_next_issue.py:58–197` (`TestNextIssueSorting`, 4 tests) — these assert the hardcoded `(-(oc or -1), -(cs or -1), priority_int)` sort tuple and **will break** when the lambda is replaced with a resolver call; update them to verify the `confidence_first` default produces the identical order (not just "extend with new cases")
- `scripts/tests/test_next_issues.py:58–143` (`TestNextIssuesRankedOrder`, 2 tests) — same issue; both assert ranked output order directly and will fail under any non-confidence-first resolver; update, don't add around them
- New class `TestNextIssueConfig` in `test_config.py` — mirror `TestDuplicateDetectionConfig` (lines 172–225): test defaults via direct instantiation, `from_dict` with values, `from_dict` with empty dict → defaults, `ValueError` on unknown strategy/key, and integration via `IssuesConfig.from_dict({"next_issue": {...}})` mirroring `test_issues_config_parses_duplicate_detection` at line 195

### Documentation
- `docs/reference/API.md:2953-3015` — `ll-issues next-issue` / `next-issues` reference; document new config block and strategies
- `docs/reference/CLI.md:522-537` — CLI reference; sync description (lines 526, 541 describe the hardcoded sort order verbatim — update to "config-driven, default: `confidence_first`")
- `docs/guides/LOOPS_GUIDE.md:2052` — mentions the `ll_issues_next_issue` fragment; note new config affects loop selection
- `config-schema.json` field `description`s — explain each strategy preset

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:25-41` — full `issues` config example needs a `next_issue` block; add a new `### issues.next_issue` subsection following the `### refine_status` (line 483) and `### dependency_mapping` (line 502) pattern
- `docs/reference/API.md:322-337` — `IssuesConfig` dataclass field table needs a `next_issue: NextIssueConfig` row (separate from the CLI reference section at 2953-3015)

### Configuration
- `.ll/ll-config.json` gains optional `issues.next_issue` block; no migration needed for existing configs (default preset reproduces today's tuple)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py:362-374` — `BRConfig.to_dict()` serializes the `issues` block but currently omits `duplicate_detection`; make an explicit decision: omit `next_issue` from `to_dict()` (consistent with `duplicate_detection` precedent) or include it to enable `{{config.issues.next_issue.*}}` template substitution in skills/commands. Recommended: omit (no existing skill uses `duplicate_detection` via template substitution).

## Implementation Steps

1. Design the `issues.next_issue` schema (strategies + custom `sort_keys`) and add it to `config-schema.json` next to `issues.duplicate_detection` (lines 126-146); use `additionalProperties: false`, enum for `strategy`, and an array-of-objects for `sort_keys` with `key` (enum of allowed `IssueInfo` fields) and `direction` (enum `["asc","desc"]`).
2. Add `NextIssueConfig` `@dataclass` in `scripts/little_loops/config/features.py` mirroring `DuplicateDetectionConfig` (lines 43-56); wire `next_issue: NextIssueConfig` into `IssuesConfig` (line 73) via `IssuesConfig.from_dict`. Export the new class from `scripts/little_loops/config/__init__.py`.
3. Implement the sort-key resolver — function that takes a `NextIssueConfig` and returns `Callable[[IssueInfo], tuple]`. Either reuse / extend the existing `_sort_issues` helper at `scripts/little_loops/cli/issues/search.py:135-178` or implement a sibling helper that follows the same string-dispatch shape. Pin a single None-handling convention.
4. Add validation in `NextIssueConfig.from_dict`: raise `ValueError(f"Unknown strategy: {strategy!r}")` / `ValueError(f"Unknown sort key: {key!r}")` for invalid values (pattern from `scripts/little_loops/issue_template.py:68-69`). Confirm CLI surfaces it cleanly (mirror `scripts/little_loops/cli/loop/run.py:46-48`).
5. Replace the hardcoded sort blocks at `scripts/little_loops/cli/issues/next_issue.py:33-39` and `scripts/little_loops/cli/issues/next_issues.py:31-37` with `issues.sort(key=build_sort_key(config.issues.next_issue))`.
6. Add unit tests in `scripts/tests/test_next_issue.py` and `scripts/tests/test_next_issues.py` using the `temp_project_dir` + `_write_config` pattern from `scripts/tests/conftest.py:55-121`. Cover: (a) no-config regression vs today's order, (b) each named preset, (c) custom `sort_keys`, (d) `ValueError` on invalid config. Add schema test in `scripts/tests/test_config_schema.py`.
7. Update `docs/reference/API.md:2953-3015`, `docs/reference/CLI.md:522-537` (lines 526, 541 describe sort order verbatim), and `docs/guides/LOOPS_GUIDE.md` with the new config block and a worked `priority_first` example. Update `docs/reference/CONFIGURATION.md`: add `next_issue` block to the full `issues` example (lines 25-41) and add a new `### issues.next_issue` subsection (model after `### refine_status` at line 483). Update `docs/reference/API.md:322-337` to add `next_issue: NextIssueConfig` to the `IssuesConfig` dataclass field table. Run `python -m pytest scripts/tests/test_next_issue.py scripts/tests/test_next_issues.py scripts/tests/test_config.py scripts/tests/test_config_schema.py -v` and `ruff check scripts/` before commit.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/tests/test_next_issue.py:58–197` and `scripts/tests/test_next_issues.py:58–143` — the 6 sort-order assertion tests (`TestNextIssueSorting` × 4, `TestNextIssuesRankedOrder` × 2) **will break** when the hardcoded lambda is replaced; update them to verify the `confidence_first` default resolver produces the same order as today, or set `strategy: confidence_first` explicitly in the test config fixture.
9. Add `TestNextIssueConfig` class to `test_config.py` mirroring `TestDuplicateDetectionConfig` (lines 172–225): standalone defaults, `from_dict` with values, `from_dict` empty → defaults, `ValueError` on unknown strategy/key, plus integration via `IssuesConfig.from_dict({"next_issue": {...}})` (mirror `test_issues_config_parses_duplicate_detection` at line 195).
10. Decide and document `BRConfig.to_dict()` behavior (`config/core.py:362-374`): recommendation is to omit `next_issue` from serialization (consistent with `duplicate_detection` precedent) since no skill currently uses `{{config.issues.*}}` template substitution for these sub-configs.

## Impact

- **Priority**: P3 - Quality-of-life improvement; no user is blocked, but the hardcoded behavior has already produced friction in loops that select by priority.
- **Effort**: Small - Isolated change: one CLI module, one config section, and tests. Existing patterns (priorities, duplicate thresholds) provide a template.
- **Risk**: Low - Default preset preserves current behavior; no schema field is required. Breakage limited to misconfigured `sort_keys`, caught by validation.
- **Breaking Change**: No

## API/Interface

```jsonc
// .ll/ll-config.json (excerpt)
{
  "issues": {
    "next_issue": {
      "strategy": "priority_first",
      // Optional custom order overrides strategy:
      "sort_keys": [
        {"key": "priority", "direction": "asc"},
        {"key": "outcome_confidence", "direction": "desc"},
        {"key": "confidence_score", "direction": "desc"}
      ]
    }
  }
}
```

## Scope Boundaries

- Out of scope: new sort signals beyond fields already parsed on issues (e.g., git age, sprint membership). Those can be added incrementally once the resolver exists.
- Out of scope: CLI flag for ad-hoc strategy override (`--strategy`). Track separately if demand emerges.
- Out of scope: changing `ll-issues next-issues` (plural) selection logic beyond mirroring the same resolver.

## Related Key Documentation

| Document | Category | Why relevant |
|----------|----------|--------------|
| `docs/reference/API.md` | architecture | CLI reference for `ll-issues` subcommands; must document new config keys |
| `.claude/CLAUDE.md` | guidelines | Mentions `ll-issues` as the issue management CLI; keep command surface description accurate |

## Labels

`enhancement`, `cli`, `config`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e7213c75-e1e1-4c35-8db2-872a26ac38fa.jsonl`
- `/ll:wire-issue` - 2026-04-16T19:37:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c53b4020-26e9-40f9-9abd-fd8badbf9710.jsonl`
- `/ll:refine-issue` - 2026-04-16T19:30:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a159601-ac7d-423a-a061-b791ecee841c.jsonl`

- `/ll:capture-issue` - 2026-04-16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/783ff1cd-1bba-41de-abf8-cb667d74e9da.jsonl`
- `/ll:issue-size-review` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed68bd1a-5a6f-4d92-94fd-8ff3a80f7d09.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-16
- **Reason**: Issue too large for single session (score 9/11)

### Decomposed Into
- ENH-1124: NextIssueConfig Schema Definition and Dataclass
- ENH-1125: Sort-Key Resolver and CLI Wiring for next-issue
- ENH-1126: Tests and Documentation for Configurable next-issue Selection

---

**Open** | Created: 2026-04-16 | Priority: P3

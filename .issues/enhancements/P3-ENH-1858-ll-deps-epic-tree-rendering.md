---
id: ENH-1858
type: ENH
priority: P3
status: open
captured_at: '2026-06-01T17:35:32Z'
discovered_date: '2026-06-01'
discovered_by: capture-issue
relates_to:
- ENH-1727
- FEAT-1855
decision_needed: false
implementation_order_risk: true
confidence_score: 100
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 25
size: Very Large
---

# ENH-1858: `ll-deps tree --epic EPIC-NNN` — render EPIC child hierarchy with dependency edges

## Summary

Extend `ll-deps` with a tree view rooted at an EPIC, showing child issues with their dependency edges (`blocked_by`, `depends_on`, `blocks`) and current status. Complements `ll-issues list --group-by epic` (flat per-bucket list) with a structural view that surfaces critical path and blockers within an EPIC.

## Current Behavior

`ll-deps` analyzes cross-issue dependencies project-wide but has no EPIC-rooted view. To see "what's blocking EPIC-1773's progress" the user must run `ll-deps` globally and manually filter to children of EPIC-1773 — or open files one by one.

`ll-issues list --group-by epic` shows children flat under each EPIC bucket but does not render dependency edges between them.

## Expected Behavior

```
$ ll-deps tree --epic EPIC-1773
EPIC-1773  Audit & simplify built-in FSM loops [open, 8/12 done]
├── ENH-1641  Extract shared fragments  [open, 24d stalled]
│   └── ⮡ blocks  ENH-1820  Migrate goal-cluster to fragments  [blocked]
├── FEAT-1820  Migrate goal-cluster to fragments  [blocked by ENH-1641]
├── ENH-1774  Wave 1: ll-commit shared fragments  [done]
└── ENH-1775  Wave 2: extract generator-evaluator  [done]
```

JSON output via `--format json` for tooling integration.

## Motivation

Within an EPIC, the question is rarely "what dependencies exist globally" — it's "what's the critical path inside this initiative, what's currently blocking forward progress, and which children are independent?". A scoped tree answers this in one glance.

This complements the FEAT-1855 progress aggregation (numbers) and FEAT-1856 review-epic skill (interpretation) with structural visibility.

## Proposed Solution

1. Add `tree` subparser to `main_deps()` in `deps.py` with `--epic EPIC-NNN` and `--format {text,json}` (matching the `analyze` subcommand's `--format` pattern; see `add_json_arg` in `cli_args.py` for the simpler `--json` flag alternative used by other subcommands).
2. **Resolve children directly** — do NOT use `SprintManager.load_or_resolve()` for the tree command. That method filters to `_ACTIVE_STATUSES = {"open", "in_progress", "blocked"}` only, but the tree must show done/deferred children to produce the `8/12 done` summary line. Instead: (a) parse the EPIC file's `relates_to:` list (forward refs) and (b) call `find_issues(config)` and filter `issue.parent == epic_id` (backward refs), then union both sets without status filtering.
3. Build a `DependencyGraph.from_issues(child_infos, completed_ids=done_child_ids, all_known_ids=all_child_ids)` restricted to the child set — this gives blocked_by/blocks/depends_on edges scoped to the EPIC's children.
4. Render as Unicode tree using the recursive `prefix` / `is_last` pattern (model: `doc_scraper.DocScraper._print_sitemap()`): `connector = "└── " if is_last else "├── "`, `extension = "    " if is_last else "│   "`. Annotate blocking edges inline (e.g., `⮡ blocks`, `[blocked by ENH-NNN]`). Color edge types using the `EDGE_COLOR` dict from `clusters.py` as reference.
5. JSON: emit `{"root": ..., "nodes": [...], "edges": [...]}` via `print_json()` from `cli/output.py`.

For rendering utilities, reuse `colorize()`, `TYPE_COLOR`, `PRIORITY_COLOR` from `scripts/little_loops/cli/output.py`. The recursive tree renderer should live in a new `scripts/little_loops/cli/deps/tree.py` (or as `format_epic_tree()` in `dependency_mapper/formatting.py`).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/deps.py` — add `tree` subparser in `main_deps()` alongside existing `analyze`, `validate`, `fix`, `apply` subparsers; dispatch to tree handler via `if args.command == "tree":` block
- `scripts/little_loops/dependency_mapper/formatting.py` — add `format_epic_tree(root, children, graph, ...)` function here, or create `scripts/little_loops/cli/deps/tree.py` as a new module

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py` — `find_issues(config)` + `IssueInfo.parent` for backward child lookup; `IssueParser.parse_file()` for forward refs from EPIC's `relates_to:` frontmatter
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph.from_issues(issues, completed_ids, all_known_ids)` builds the scoped edge graph; `get_execution_waves()` for topo ordering within tree
- `scripts/little_loops/cli/output.py` — `colorize()`, `BOX_ML` (`├`), `BOX_BL` (`└`), `BOX_V` (`│`), `TYPE_COLOR`, `PRIORITY_COLOR`, `print_json()`, `configure_output()`, `use_color_enabled()`
- `scripts/little_loops/cli_args.py` — `add_json_arg()` (alternative `--json` flag approach; use `--format {text,json}` pattern from `analyze` subcommand for consistency)
- `scripts/little_loops/cli/issues/list_cmd.py` — adjacent EPIC-grouping output (ENH-1727); same `parent:` scan logic is reused here

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/dependency_mapper/__init__.py` — public-exports module; if `format_epic_tree()` is added to `formatting.py`, export it here alongside `format_report` and `format_text_graph`

### Similar Patterns
- `scripts/doc_scraper.py:DocScraper._print_sitemap()` — the canonical `├──` / `└──` recursive indent pattern to model after; `connector = "└── " if is_last else "├── "`, `extension = "    " if is_last else "│   "`
- `scripts/little_loops/cli/issues/clusters.py:_render_cluster_diagram()` + `EDGE_COLOR` — edge type → ANSI color map (`"blocks": "31"`, `"blocked_by": "33"`, `"depends_on": "35"`); also the `▼`/`▲` arrow annotation approach
- `scripts/little_loops/dependency_mapper/formatting.py:format_text_graph()` — existing chain renderer; note it uses inline `──→` arrows, not indented tree — this shows what NOT to do (the tree needs indented box-drawing, not inline chains)
- `scripts/little_loops/cli/issues/list_cmd.py:cmd_list()` epic-grouping branch — how `parent:` field is used to bucket children, including the `issue.parent.split("-", 1)[0] == "EPIC"` guard

### Tests
- `scripts/tests/test_deps_cli.py` — new file with `TestDepsTree` class (does not exist yet):
  - EPIC with no children → clear message, exit 0
  - EPIC with linear chain → renders chain with `├──` / `└──`
  - EPIC with diamond dependency → renders correctly (shared node annotation)
  - EPIC not found → exit non-zero
  - `--format json` round-trips (nodes + edges structure)
- `scripts/tests/test_dependency_mapper.py:make_issue()` — existing factory helper; extend with `parent: str | None = None` parameter for EPIC child test setup
- `scripts/tests/test_issues_cli.py:issues_dir_with_epic_children()` — fixture that creates issues with `parent: EPIC-001` frontmatter; use this pattern for the tree test fixture (note: lives in `test_issues_cli.py`, not `conftest.py`, so must be duplicated or inlined in `test_deps_cli.py`)
- `scripts/tests/conftest.py` — `temp_project_dir`, `sample_config` (already has `epics` category), `issues_dir` shared fixtures

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_dependency_mapper.py:TestFormatEpicTree` — new unit-test class (within the existing file) for `format_epic_tree()` itself; the issue covers CLI-level tests in `test_deps_cli.py` but not unit tests for the rendering function — follow the `TestFormatTextGraph` pattern (lines 944–989): call `format_epic_tree(root_id, root_info, child_map, graph, use_color=False)` and assert on string content

### Documentation
- `docs/reference/CLI.md` — add `ll-deps tree` subcommand block with usage, `--epic`/`--format` args, and example output

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `### main_deps` section lists sub-commands as `validate, suggest, report` (stale); update to `analyze, validate, fix, apply, tree` [Agent 2 finding]

### Skills/Commands

_Wiring pass added by `/ll:wire-issue`:_
- `skills/map-dependencies/SKILL.md` — explicitly enumerates all `ll-deps` subcommands in `## How to Use` and `## Examples` tables; no catch-all; add `ll-deps tree --epic EPIC-NNN` row [Agent 2 finding]

### Configuration
- N/A — read-only command; no new config keys

## Implementation Steps

1. **Add `tree` subparser** in `main_deps()` in `scripts/little_loops/cli/deps.py`:
   ```python
   tree_parser = subparsers.add_parser("tree", help="Render EPIC child hierarchy")
   tree_parser.add_argument("--epic", required=True, metavar="EPIC-NNN")
   tree_parser.add_argument("-f", "--format", choices=["text", "json"], default="text")
   ```
   Then dispatch: `if args.command == "tree": return _cmd_tree(args, config, logger)`.

2. **Resolve children** in `_cmd_tree()`: parse the EPIC file via `IssueParser(config).parse_file(epic_path)` → `epic_info.relates_to` (forward refs). Then `all_issues = find_issues(config)` → filter `issue.parent == epic_id` (backward refs). Union both sets. Separate into `done_ids` (status in `{"done", "deferred"}`) and active.

3. **Build filtered `DependencyGraph`**: `graph = DependencyGraph.from_issues(child_issues, completed_ids=done_ids, all_known_ids=all_child_ids)`. Use `graph.topological_sort()` for tree ordering.

4. **Render tree** as a standalone function (e.g., `format_epic_tree(root_id, root_info, child_map, graph, use_color)`) following `DocScraper._print_sitemap()` recursive prefix pattern. Status badges: show `[done]` / `[blocked]` inline (suppress `[open]` for brevity, consistent with `list_cmd.py`). Annotate blocking edges as `⮡ blocks ISSUE-NNN` under the blocker's tree line. Use `colorize()` + `EDGE_COLOR` dict from `clusters.py` for edge color.

5. **JSON path**: build `{"root": root_id, "nodes": [{"id": ..., "title": ..., "status": ..., "parent": ...}], "edges": [{"from": ..., "to": ..., "kind": ...}]}` and emit via `print_json()` from `cli/output.py`.

6. **Tests** in new `scripts/tests/test_deps_cli.py`: create `TestDepsTree` class using `tmp_path` + `patch.object(sys, "argv", [...])` pattern from `test_dependency_mapper.py:TestMainCLI`. Extend `make_issue()` helper with `parent` param, or inline fixture files. Cover all five cases listed in Integration Map → Tests.

7. **Docs**: update `docs/reference/CLI.md` with `ll-deps tree` block.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Export `format_epic_tree()` from `scripts/little_loops/dependency_mapper/__init__.py` alongside `format_report` and `format_text_graph`
9. Update `docs/reference/API.md` `### main_deps` sub-commands list — correct stale `validate, suggest, report` → `analyze, validate, fix, apply, tree`
10. Update `skills/map-dependencies/SKILL.md` — add `ll-deps tree --epic EPIC-NNN` row to the `## Examples` table and a `### EPIC Tree View` usage section
11. Add `TestFormatEpicTree` class in `scripts/tests/test_dependency_mapper.py` for unit-testing `format_epic_tree()` — follow `TestFormatTextGraph` pattern (call the function directly with `IssueInfo` objects from `make_issue()`, assert string content)
12. **Structural note** (if `cli/deps/tree.py` module path is chosen): `deps.py` must become `cli/deps/__init__.py`; update `scripts/little_loops/cli/__init__.py` import and `docs/ARCHITECTURE.md` directory diagram to reflect the new subpackage

## Impact

- **Priority**: P3 — Useful but lower-leverage than FEAT-1855 (aggregation); answers a structural question (1855 answers a quantitative one).
- **Effort**: Small–Medium — Reuses `DependencyGraph` and existing issue-loading; primary work is tree rendering and child resolution.
- **Risk**: Low — New read-only subcommand; no mutation of existing behavior.
- **Breaking Change**: No

## Success Metrics

- Tree view appears in `ll-deps --help` and is documented in CLI reference.
- For EPICs with ≥3 children, tree output fits in a single terminal screen and is unambiguous about blockers.

## Scope Boundaries

- No mutation of issue files.
- No automatic edge inference from prose — only `blocked_by` / `depends_on` / `blocks` frontmatter.
- No Gantt or timeline rendering — that is a separate (deferred) follow-up.
- Does not modify `ll-deps`'s existing global view.
- `SprintManager.load_or_resolve()` is intentionally NOT used here — it filters to active statuses and returns an ordered Sprint, not the raw child+graph data needed for tree rendering.

## API/Interface

```
ll-deps tree --epic EPIC-NNN [--format {text,json}]
```

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `epics`, `cli`, `deps`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-01_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- **Moderate per-site complexity** for `format_epic_tree()` — recursive tree rendering requires correctly threading `prefix`/`extension` state across two child-resolution paths (forward `relates_to` refs + backward `parent` filter), edge annotation, and color. DocScraper pattern is the model; first implementation may need iteration on edge-case layouts.
- **Broad file surface** across 8 sites — mostly additive but coordination span (CLI, dependency_mapper, tests, docs, skills) increases the risk of partial completion or a missing wiring step.
- **No test coverage for `deps.py` CLI layer** — implement tests first so the tree renderer can be validated incrementally; all five `TestDepsTree` cases should be green before integrating the color/annotation pass.
- **File placement choice** (`formatting.py` vs `cli/deps/tree.py`): the `tree.py` path requires promoting `deps.py` to a package; recommend `formatting.py` to keep the change surface flat.

## Session Log
- `/ll:confidence-check` - 2026-06-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1b2c3d4e-5678-90ab-cdef-1234567890ab.jsonl`
- `/ll:wire-issue` - 2026-06-01T18:24:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/028ea300-f57a-416f-89b3-3b59a694635d.jsonl`
- `/ll:refine-issue` - 2026-06-01T18:18:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82ca77a3-3757-46eb-bd70-4bbff3c8fb0e.jsonl`
- `/ll:refine-issue` - 2026-06-01T00:00:00 - ``
- `/ll:format-issue` - 2026-06-01T17:45:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f9321137-9371-4510-85ad-95b0940c3c6f.jsonl`
- `/ll:capture-issue` - 2026-06-01T17:35:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/277dd3c5-ffef-46cb-bcc6-124409ce1225.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P3

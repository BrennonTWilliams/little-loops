---
id: ENH-1864
type: ENH
priority: P3
status: done
parent: ENH-1858
captured_at: '2026-06-01T00:00:00Z'
completed_at: '2026-06-01T19:06:02Z'
discovered_date: '2026-06-01'
discovered_by: issue-size-review
size: Large
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1864: `ll-deps tree` — core implementation (subparser, resolver, renderer, tests)

## Summary

Implement the core `ll-deps tree --epic EPIC-NNN` command: add the `tree` subparser to `main_deps()`, resolve EPIC children from forward (`relates_to`) and backward (`parent`) refs, build a scoped `DependencyGraph`, render the Unicode tree with inline blocking-edge annotations, and provide JSON output. Add both CLI-level and unit tests.

## Current Behavior

The `ll-deps` CLI offers `analyze`, `validate`, `fix`, and `apply` subcommands but no `tree` subcommand. Running `ll-deps tree` yields an unrecognized-arguments error. There is no way to visualize an EPIC's child hierarchy with inline dependency edges from the CLI.

## Parent Issue

Decomposed from ENH-1858: `ll-deps tree --epic EPIC-NNN` — render EPIC child hierarchy with dependency edges

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

JSON output via `--format json`.

## Proposed Solution

### Module placement
Use `formatting.py` for `format_epic_tree()` to keep the change surface flat (avoid promoting `deps.py` to a package). See Scope note re: `cli/deps/tree.py` alternative.

### Implementation Steps

1. **Add `tree` subparser** in `main_deps()` in `scripts/little_loops/cli/deps.py`:
   ```python
   tree_parser = subparsers.add_parser("tree", help="Render EPIC child hierarchy")
   tree_parser.add_argument("--epic", required=True, metavar="EPIC-NNN")
   tree_parser.add_argument("-f", "--format", choices=["text", "json"], default="text")
   ```
   Dispatch: `if args.command == "tree": return _cmd_tree(args, config, logger)`.

2. **Resolve children** in `_cmd_tree()`: parse EPIC file via `IssueParser(config).parse_file(epic_path)` → `epic_info.relates_to` (forward refs). Then:
   ```python
   all_issues = find_issues(
       config,
       status_filter={"open", "in_progress", "blocked", "deferred", "done"},
   )
   ```
   Filter `issue.parent == epic_id` (backward refs). Union with forward-ref set. Do NOT pass `status_filter=None` (the default) — it excludes `done` and `deferred` issues, which must appear in the tree. Do NOT use `SprintManager.load_or_resolve()` — it also filters to active statuses only. Do NOT call the internal `_load_issues()` helper in `deps.py` (lines 15–65) — it wraps `find_issues()` with the same active-only default. Separate results into `done_ids` (status in `{"done", "deferred"}`) and active.

3. **Build filtered `DependencyGraph`**: `graph = DependencyGraph.from_issues(child_issues, completed_ids=done_ids, all_known_ids=all_child_ids)`.

4. **Render tree** as `format_epic_tree(root_id, root_info, child_map, graph, use_color)` in `scripts/little_loops/dependency_mapper/formatting.py`. Follow `DocScraper._print_sitemap()` recursive prefix pattern: `connector = "└── " if is_last else "├── "`, `extension = "    " if is_last else "│   "`. Status badges: show `[done]` / `[blocked]` inline (suppress `[open]` for brevity). Annotate blocking edges as `⮡ blocks ISSUE-NNN` under the blocker's tree line. Use `colorize()` + `EDGE_COLOR` dict from `clusters.py` for edge color.

5. **JSON path**: build `{"root": root_id, "nodes": [{"id": ..., "title": ..., "status": ..., "parent": ...}], "edges": [{"from": ..., "to": ..., "kind": ...}]}` and emit via `print_json()` from `cli/output.py`.

6. **Tests** in new `scripts/tests/test_deps_cli.py` (confirmed: file does not yet exist; existing `ll-deps` CLI tests live in `test_dependency_mapper.py:TestMainCLI` at lines 1330–1863): create `TestDepsTree` class using `tmp_path` + `patch.object(sys, "argv", [...])` pattern (see `TestMainCLI.test_analyze_no_issues` for setup convention and `capsys.readouterr()` for output capture). Extend `make_issue()` helper in `test_dependency_mapper.py` (lines 33–56) with two new parameters: `parent: str | None = None` and `status: str = "open"` — `status` is needed to create done/deferred children for tree filtering tests. Cover:
   - EPIC with no children → clear message, exit 0
   - EPIC with linear chain → renders chain with `├──` / `└──`
   - EPIC with diamond dependency → renders correctly
   - EPIC not found → exit non-zero
   - `--format json` round-trips (nodes + edges structure)

7. **Unit tests** for `format_epic_tree()`: add `TestFormatEpicTree` class in `scripts/tests/test_dependency_mapper.py` following the `TestFormatTextGraph` pattern (lines 944–989). Call `format_epic_tree(root_id, root_info, child_map, graph, use_color=False)` and assert on string content.

8. **Update epilog** in `main_deps()` parser (lines 91–106 of `deps.py`): add a `tree` usage example alongside existing `analyze`, `validate`, `fix`, `apply` examples so `ll-deps --help` shows the new subcommand.

9. **Module path decision**: If `cli/deps/tree.py` is chosen instead of `formatting.py`, `deps.py` must become `cli/deps/__init__.py`; update `scripts/little_loops/cli/__init__.py` import and `docs/ARCHITECTURE.md` accordingly. Recommend `formatting.py` to keep change surface flat.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/deps.py` — add `tree` subparser in `main_deps()` (flat `if args.command` chain, lines 66+), dispatch to `_cmd_tree()`; update epilog (lines 90–107) with `tree` usage example
- `scripts/little_loops/dependency_mapper/formatting.py` — add `format_epic_tree()` function alongside `format_report()` (line 18) and `format_text_graph()` (line 142)
- `scripts/little_loops/dependency_mapper/__init__.py` — export `format_epic_tree` in the public API

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py` — `find_issues(config, status_filter=...)` (line 831) + `IssueInfo.parent` for backward child lookup; `IssueParser.parse_file()` (line 383) for forward refs; confirmed `IssueInfo` has `parent: str | None`, `relates_to: list[str]`, `status: str`, `issue_id: str`, `title: str`
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph.from_issues(issues, completed_ids, all_known_ids)` (line 55); `completed_ids` controls which IDs are skipped as active blockers; `all_known_ids` suppresses out-of-graph reference warnings
- `scripts/little_loops/cli/output.py` — `colorize()` (line 139), `print_json()` (line 146), `BOX_ML = "├"` (line 60), `BOX_BL = "└"` (line 58), `BOX_V = "│"` (line 55), `TYPE_COLOR` (line 80), `PRIORITY_COLOR` (line 72), `configure_output()` (line 88), `use_color_enabled()` (line 134); call `configure_output()` with no args (consistent with `deps.py` — env-var detection only, not `config.cli`)
- `scripts/little_loops/cli/deps.py` internal `_load_issues()` (lines 15–65) — do NOT use; it applies active-only `status_filter` by default

### Similar Patterns
- `scripts/doc_scraper.py:DocScraper._print_sitemap()` (line 824) — canonical recursive indent pattern: `connector = "└── " if is_last else "├── "`, `extension = "    " if is_last else "│   "`; `prefix` accumulates continuation columns, `connector` is the node's own branch character
- `scripts/little_loops/cli/issues/clusters.py:_render_cluster_diagram()` (line 215) + `EDGE_COLOR` (line 16) — `EDGE_COLOR` keys: `"blocks": "31"` (red), `"blocked_by": "33"` (yellow), `"depends_on": "35"` (magenta), `"relates_to": "37"` (white), `"parent": "34"` (blue), `"sibling": "36"` (cyan)
- `scripts/little_loops/dependency_mapper/formatting.py:format_text_graph()` (line 142) — existing chain renderer; uses ASCII arrows (`──→`, `-->`, `-.→`), NOT Unicode box-drawing — `format_epic_tree()` should use Unicode box chars from `output.py`

### Tests
- `scripts/tests/test_deps_cli.py` — new file (confirmed does not exist); `TestDepsTree` class
- `scripts/tests/test_dependency_mapper.py` — extend `make_issue()` (lines 33–56) with `parent` + `status` params; add `TestFormatEpicTree` following `TestFormatTextGraph` pattern (lines 944–990)
- `scripts/tests/conftest.py` — shared fixtures (`temp_project_dir`, `sample_config`, `issues_dir`)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `### ll-deps` section (around line 1184) lists `analyze`, `validate`, `fix`, `apply` subcommands; must add `tree --epic EPIC-NNN` entry — **tracked by ENH-1865**
- `docs/reference/API.md` — `### main_deps` section has stale subcommands list (`validate, suggest, report`); `## little_loops.dependency_mapper` sub-module bullet for `formatting` describes it as "report and graph formatting" (incomplete after `format_epic_tree` lands) — **tracked by ENH-1865**
- `skills/map-dependencies/SKILL.md` — `## How to Use` and `## Examples` table enumerate all `ll-deps` subcommands explicitly; `tree` is absent — **tracked by ENH-1865**

## Impact

- **Priority**: P3 - Low-urgency enhancement; dependency visualization is useful for EPIC oversight but not blocking other work
- **Effort**: Large - New subparser, child-resolution logic, Unicode tree renderer, JSON output path, CLI-level tests, and unit tests across multiple files
- **Risk**: Low - Purely additive; no existing subcommands or data structures are modified
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `deps`, `ll-deps`

## Scope Boundaries

- No mutation of issue files.
- No automatic edge inference from prose — only `blocked_by` / `depends_on` / `blocks` frontmatter.
- `SprintManager.load_or_resolve()` intentionally NOT used here.

## Session Log
- `/ll:ready-issue` - 2026-06-01T18:56:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a38dfe29-9c06-43e8-ade3-e040edecae62.jsonl`
- `/ll:refine-issue` - 2026-06-01T18:43:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8eeca893-3738-4d07-9997-b5b15ecc0bae.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b821a849-b0a9-44d9-97a9-a7d0507e8dea.jsonl`
- `/ll:wire-issue` - 2026-06-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8eeca893-3738-4d07-9997-b5b15ecc0bae.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c41ca909-db8c-449b-9875-0d6bc9aa84fa.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P3
